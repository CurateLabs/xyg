"""Thin Python parity for Rust-owned ordered Tier-3 range reads (#110)."""

from __future__ import annotations

import struct
from itertools import pairwise

import pytest

from xyg import ChunkedColumns


def _artifact(path, rows, chunk_rows=4):
    chunks = [rows[i : i + chunk_rows] for i in range(0, len(rows), chunk_rows)]
    data_offset = 64 + 48 * len(chunks)
    header = bytearray(64)
    struct.pack_into(
        "<4sIQIIQ", header, 0, b"XYGC", 1, len(rows), chunk_rows, len(chunks), data_offset
    )
    with path.open("wb") as f:
        f.write(header)
        start = 0
        for chunk in chunks:
            xs, ys = zip(*chunk, strict=True)
            f.write(struct.pack("<QII4d", start, len(chunk), 0, min(xs), max(xs), min(ys), max(ys)))
            start += len(chunk)
        for x, y in rows:
            f.write(struct.pack("<2d", x, y))


def _artifact_with_overview(path, rows, chunk_rows=4, overview_indices=None):
    chunks = [rows[i : i + chunk_rows] for i in range(0, len(rows), chunk_rows)]
    data_offset = 64 + 48 * len(chunks)
    indices = range(len(rows)) if overview_indices is None else overview_indices
    overview = [(i, *rows[i]) for i in indices]
    header = bytearray(64)
    struct.pack_into(
        "<4sIQIIQQI",
        header,
        0,
        b"XYGC",
        2,
        len(rows),
        chunk_rows,
        len(chunks),
        data_offset,
        data_offset + 16 * len(rows),
        len(overview),
    )
    with path.open("wb") as f:
        f.write(header)
        start = 0
        for chunk in chunks:
            xs, ys = zip(*chunk, strict=True)
            f.write(struct.pack("<QII4d", start, len(chunk), 0, min(xs), max(xs), min(ys), max(ys)))
            start += len(chunk)
        for x, y in rows:
            f.write(struct.pack("<2d", x, y))
        for row, x, y in overview:
            f.write(struct.pack("<Q2d", row, x, y))


def test_exact_range_and_provenance(tmp_path):
    rows = [(float(i), float(i % 3)) for i in range(20)]
    path = tmp_path / "ordered.xygc"
    _artifact(path, rows)
    with ChunkedColumns(path) as columns:
        x, y, provenance = columns.read((5.0, 11.0), (1.0, 2.0), budget_bytes=1024, generation=9)
    assert list(zip(x, y, strict=True)) == [p for p in rows if 5 <= p[0] <= 11 and 1 <= p[1] <= 2]
    assert provenance == {
        "generation": 9,
        "first_chunk": 1,
        "chunks_considered": 2,
        "chunks_read": 2,
        "bytes_read": 128,
    }


def test_corrupt_budget_and_stale_handle_are_actionable(tmp_path):
    path = tmp_path / "ordered.xygc"
    _artifact(path, [(float(i), float(i)) for i in range(8)])
    columns = ChunkedColumns(path)
    with pytest.raises(ValueError, match="needs 128 bytes, exceeding the 16-byte read budget"):
        columns.read((0.0, 7.0), budget_bytes=16, generation=1)
    with pytest.raises(ValueError, match="generation must be"):
        columns.read((0.0, 7.0), generation=-1)
    # Invalid input must not poison the monotonic cancellation watermark.
    columns.read((0.0, 1.0), generation=2)
    with pytest.raises(ValueError, match="cancelled by newer viewport"):
        columns.read((0.0, 1.0), generation=1)
    columns.close()
    with pytest.raises(ValueError, match="stale chunked-column handle"):
        columns.cancel_before(2)
    path.write_bytes(b"broken")
    with pytest.raises(ValueError, match="cannot open checked XYGC"):
        ChunkedColumns(path)


def test_precomputed_overview_is_bounded_and_keeps_row_identity(tmp_path):
    rows = [(float(i), float((i * 7) % 13)) for i in range(20)]
    path = tmp_path / "overview.xygc"
    _artifact_with_overview(path, rows)
    with ChunkedColumns(path) as columns:
        row_ids, x, y, provenance = columns.overview(max_points=7)
    assert len(row_ids) == len(x) == len(y) == 7
    assert row_ids[0] == 0 and row_ids[-1] == 19
    assert [(xv, yv) for xv, yv in zip(x, y, strict=True)] == [rows[int(i)] for i in row_ids]
    assert provenance == {"available_points": 20, "source_rows": 20, "detail_rows_read": 0}


def test_pull_driven_pages_are_bounded_and_match_full_scan(tmp_path):
    rows = [(float(i), float(i % 5)) for i in range(120)]
    path = tmp_path / "pages.xygc"
    _artifact(path, rows)
    with ChunkedColumns(path) as columns:
        pages = list(columns.pages((7.0, 111.0), (1.0, 3.0), page_bytes=64, generation=12))
    got = [(x, y) for page_x, page_y, _ in pages for x, y in zip(page_x, page_y, strict=True)]
    assert got == [(x, y) for x, y in rows if 7 <= x <= 111 and 1 <= y <= 3]
    assert len(pages) > 20
    assert all(progress["bytes_read"] <= 64 for _, _, progress in pages)
    assert pages[-1][2]["done"] is True
    assert all(
        page[2]["next_cursor"] < next_page[2]["next_cursor"] for page, next_page in pairwise(pages)
    )


def test_pages_report_budget_cancel_and_host_bounds(tmp_path):
    path = tmp_path / "page-errors.xygc"
    _artifact(path, [(float(i), float(i)) for i in range(8)])
    with ChunkedColumns(path) as columns:
        with pytest.raises(ValueError, match="needs 64 bytes, exceeding the 16-byte page budget"):
            next(columns.pages((0.0, 7.0), page_bytes=16, generation=1))
        columns.cancel_before(3)
        with pytest.raises(ValueError, match="cancelled by newer viewport"):
            next(columns.pages((0.0, 7.0), page_bytes=64, generation=2))
        with pytest.raises(ValueError, match=r"page budget.*\[16, 2\^64\)"):
            next(columns.pages((0.0, 7.0), page_bytes=1 << 64, generation=4))
        with pytest.raises(ValueError, match=r"generation.*\[0, 2\^64\)"):
            next(columns.pages((0.0, 7.0), page_bytes=64, generation=True))


@pytest.mark.parametrize("paged", [False, True])
def test_fetched_detail_corruption_is_rejected_by_native_reader(tmp_path, paged):
    path = tmp_path / "corrupt-detail.xygc"
    _artifact(path, [(float(i), float(i)) for i in range(8)])
    with ChunkedColumns(path) as columns:
        # Mutate the already-open source, preserving length and metadata.
        with path.open("r+b") as source:
            source.seek(64 + 48 * 2 + 16 + 8)
            source.write(struct.pack("<d", 99.0))
        with pytest.raises(ValueError, match="corrupt artifact"):
            if paged:
                next(columns.pages((0.0, 7.0), page_bytes=64, generation=1))
            else:
                columns.read((0.0, 7.0), budget_bytes=128, generation=1)


def test_empty_range_cannot_publish_an_old_generation(tmp_path):
    path = tmp_path / "empty-stale.xygc"
    _artifact(path, [(float(i), float(i)) for i in range(8)])
    with ChunkedColumns(path) as columns:
        columns.cancel_before(3)
        with pytest.raises(ValueError, match="cancelled by newer viewport"):
            columns.read((20.0, 30.0), budget_bytes=128, generation=2)


def test_resident_overlap_reuses_native_chunks_across_read_modes(tmp_path):
    path = tmp_path / "reuse.xygc"
    rows = [(float(i), float(i % 3)) for i in range(20)]
    _artifact(path, rows)
    with ChunkedColumns(path) as columns:
        columns.read((0.0, 7.0), budget_bytes=192, generation=1)
        x, y, stats = columns.read((4.0, 11.0), budget_bytes=192, generation=2)
        assert list(zip(x, y, strict=True)) == rows[4:12]
        assert stats["chunks_read"] == 1
        assert stats["bytes_read"] == 64
        pages = list(columns.pages((4.0, 11.0), page_bytes=192, generation=3))
        assert len(pages) == 1
        assert pages[0][2]["bytes_read"] == 0
        with pytest.raises(ValueError, match="needs 128 bytes"):
            columns.read((4.0, 11.0), budget_bytes=64, generation=4)


def test_chart_overview_viewport_pan_and_disposal(tmp_path):
    rows = [(float(i), float((i * 7) % 13)) for i in range(40)]
    path = tmp_path / "chart.xygc"
    _artifact_with_overview(path, rows)
    with ChunkedColumns(path) as columns:
        overview = columns.chart(max_points=7)
        assert len(overview.source_row_ids) == 7
        assert overview.source_provenance["detail_rows_read"] == 0
        overview.figure().build_payload_split()
        for generation, bounds in enumerate([(5, 15), (9, 19), (10, 11)], 1):
            chart = columns.chart(bounds, page_bytes=256, budget_bytes=1024, generation=generation)
            ids = [i for i, (x, _) in enumerate(rows) if bounds[0] <= x <= bounds[1]]
            assert list(chart.source_row_ids) == ids
            assert list(chart.children[0].x) == [rows[i][0] for i in ids]
            chart.figure().build_payload_split()
        warm = columns.chart((10, 11), page_bytes=256, budget_bytes=1024, generation=4)
        assert warm.source_provenance["bytes_read"] == 0
        with pytest.raises(ValueError, match="cancelled by newer viewport"):
            columns.chart((10, 11), generation=3)
        with pytest.raises(ValueError, match="exceeding"):
            columns.chart((0, 39), budget_bytes=64, page_bytes=64, generation=5)
    with pytest.raises(ValueError, match="stale chunked-column handle"):
        columns.chart()


def test_rendered_chart_snapshot_navigation(tmp_path):
    import os

    chromium = os.environ.get("XYG_TEST_CHROMIUM")
    if not chromium:
        if os.environ.get("XY_REQUIRE_BROWSER") == "1":
            pytest.fail("required chunked chart snapshot browser is not configured")
        pytest.skip("set XYG_TEST_CHROMIUM for the headless chart snapshot proof")
    from scripts.chunked_chart_evidence import run

    report = run(tmp_path, chromium)
    assert len(report["requests"]) == 4
    assert all(request["exact_pixel_match"] for request in report["requests"])


def test_chart_overview_rejects_stale_generation_without_changing_static_overview(tmp_path):
    path = tmp_path / "overview-generation.xygc"
    _artifact_with_overview(path, [(float(i), float(i % 3)) for i in range(12)])
    with ChunkedColumns(path) as columns:
        columns.cancel_before(5)
        with pytest.raises(ValueError, match="cancelled by newer viewport"):
            columns.chart(generation=4, max_points=5)
        current = columns.chart(generation=5, max_points=5)
        assert current.source_provenance["generation"] == 5
        assert current.source_provenance["detail_rows_read"] == 0
        assert len(current.source_row_ids) == 5
        columns.cancel_before(6)
        with pytest.raises(ValueError, match="cancelled by newer viewport"):
            columns.chart(generation=5, max_points=5)
        # The explicit static metadata API has no viewport generation contract.
        assert len(columns.overview(max_points=5)[0]) == 5


@pytest.mark.parametrize("page_bytes", [64, 128, 192])
def test_chart_counts_distinct_candidate_chunks_across_page_boundaries(tmp_path, page_bytes):
    path = tmp_path / "distinct-chunks.xygc"
    rows = [(float(i), float(i // 4)) for i in range(12)]
    _artifact_with_overview(path, rows)
    with ChunkedColumns(path) as columns:
        chart = columns.chart((0, 11), budget_bytes=192, page_bytes=page_bytes)
        assert chart.source_provenance["chunks_considered"] == 3
        assert list(chart.source_row_ids) == list(range(12))
        pruned = columns.chart((0, 11), (1, 1), budget_bytes=192, page_bytes=page_bytes)
        assert pruned.source_provenance["chunks_considered"] == 3
        assert list(pruned.source_row_ids) == [4, 5, 6, 7]


def test_no_browser_skips_before_importing_optional_render_dependencies():
    import os
    import subprocess
    import sys

    script = """
import importlib.abc
import sys
import pytest
class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "resource" or fullname == "PIL" or fullname.startswith("PIL."):
            raise ModuleNotFoundError("optional render dependency unavailable: " + fullname)
sys.meta_path.insert(0, BlockOptional())
code = pytest.main(["tests/test_chunked_columns.py::test_rendered_chart_snapshot_navigation", "-q"])
assert "scripts.chunked_chart_evidence" not in sys.modules
raise SystemExit(code)
"""
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    env.pop("XYG_TEST_CHROMIUM", None)
    env.pop("XY_REQUIRE_BROWSER", None)
    result = subprocess.run(
        [sys.executable, "-c", script], env=env, text=True, capture_output=True, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 skipped" in result.stdout
