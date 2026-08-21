"""Thin Python parity for Rust-owned ordered Tier-3 range reads (#110)."""

from __future__ import annotations

import struct

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
