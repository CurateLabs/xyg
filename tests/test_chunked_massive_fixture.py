"""Only bounded format/oracle controls run in CI; the 72 GB journey is manual."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from xyg import ChunkedColumns

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "massive_fixture", ROOT / "scripts/chunked_massive_fixture.py"
)
assert SPEC and SPEC.loader
FIXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURE)


def test_materialized_fixture_and_independent_scan_match_native(tmp_path):
    path = tmp_path / "small.xygc"
    generated = FIXTURE.generate(path, 10003, 1000)
    assert generated["allocatedBytes"] >= generated["rows"] * 16
    queries = [{"x": [700, 1400], "y": [900, 19000]}, {"x": [9990, 10002], "y": None}]
    expected = FIXTURE.verify(path, queries)
    assert expected["everyDetailRowVerified"] and expected["rowsScanned"] == 10003
    with ChunkedColumns(path) as source:
        for generation, result in enumerate(expected["ranges"], 1):
            query = result["query"]
            chart = source.chart(tuple(query["x"]), query["y"], generation=generation)
            assert list(map(int, chart.source_row_ids)) == [row[0] for row in result["rows"]]
            trace = chart.figure().traces[0]
            assert list(trace.x.values) == [row[1] for row in result["rows"]]
            assert list(trace.y.values) == [row[2] for row in result["rows"]]
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        FIXTURE.generate(path, 10003, 1000)
    assert path.read_bytes() == original


def test_manual_generator_admits_metadata_before_allocating(tmp_path):
    with pytest.raises(ValueError, match="metadata exceeds"):
        FIXTURE.generate(tmp_path / "too-many-chunks.xygc", 1_000_000, 1)
    assert not list(tmp_path.iterdir())


def test_fixture_install_cannot_overwrite_a_concurrent_writer(tmp_path, monkeypatch):
    path = tmp_path / "concurrent.xygc"
    link = FIXTURE.os.link

    def competing_writer(source, destination):
        path.write_bytes(b"other writer")
        link(source, destination)

    monkeypatch.setattr(FIXTURE.os, "link", competing_writer)
    with pytest.raises(FileExistsError):
        FIXTURE.generate(path, 8, 4)
    assert path.read_bytes() == b"other writer"
    assert path.with_name(path.name + ".partial").exists()
