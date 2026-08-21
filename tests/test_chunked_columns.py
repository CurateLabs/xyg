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


def _artifact_with_overview(path, rows, chunk_rows=4):
    chunks = [rows[i : i + chunk_rows] for i in range(0, len(rows), chunk_rows)]
    data_offset = 64 + 48 * len(chunks)
    overview = [(i, x, y) for i, (x, y) in enumerate(rows)]
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
