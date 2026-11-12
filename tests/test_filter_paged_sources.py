"""Issued XYGC planes use the ordinary native filter/count/membership engine."""

from __future__ import annotations

import math
import struct

import pytest

import xyg
from test_chunked_columns import _artifact
from xyg.filter_session import FilterTierCError


def _same(a, b):
    a, b = bytearray(a["packet"]), bytearray(b["packet"])
    a[80:96] = b[80:96] = bytes(16)  # resident storage and peak workspace differ
    assert a == b


def test_paged_source_five_density_views_exact_planes_identity_and_rebuild(tmp_path):
    rows = [(float(i), float(i % 19)) for i in range(4099)]
    path = tmp_path / "source.xygc"
    _artifact(path, rows, chunk_rows=128)
    rows[32] = (float("nan"), 4.0)
    rows[65] = (65.0, float("inf"))
    with path.open("r+b") as file:
        file.seek(24)
        offset = struct.unpack("<Q", file.read(8))[0]
        for row in (32, 65):
            file.seek(offset + row * 16)
            file.write(struct.pack("<2d", *rows[row]))
    source = xyg.ChunkedColumns(path)
    chart = xyg.scatter_chart(xyg.scatter(x=[0.0], y=[0.0]))
    options = dict(source_id=77, first_row=(1 << 63) + 17, budget_bytes=1 << 20)
    first = options["first_row"]
    active = dict(id=1, dimension="x", cuts=[1024, 2048, 3072])
    views = [
        dict(id=i, x="x", y="y", width=8, height=4, x_range=[0, 4100], y_range=[0, 20])
        for i in range(1, 6)
    ]
    with chart.filter_session(
        {"x": source.column("x"), "y": source.column("y")}, **options
    ) as paged:
        # The Rust source lease is independent of the public viewport owner.
        source.close()
        with chart.filter_session(
            {"x": [r[0] for r in rows], "y": [r[1] for r in rows]}, **options
        ) as memory:
            _same(paged.configure_density(active, views), memory.configure_density(active, views))
            _same(paged.range(1024, 2047), memory.range(1024, 2047))
            disk, ram = paged.paint(), memory.paint()
            _same(disk, ram)
            assert disk["selected_count"] == 1024
            assert disk["rows_read"] == 0 and disk["tier"] == 3
            counts = [0] * 32
            selected = [0] * 32
            for x, y in rows:
                if not math.isfinite(x) or not math.isfinite(y):
                    continue
                cell = min(3, int(y * 4 / 20)) * 8 + min(7, int(x * 8 / 4100))
                counts[cell] += 1
                selected[cell] += int(1024 <= x <= 2047)
            for density in disk["density"]:
                assert list(density["totals"]) == counts
                assert list(density["selected"]) == selected
            member = paged.membership(first + 30, 2050)
            _same(member, memory.membership(first + 30, 2050))
            for i, (x, _) in enumerate(rows[30:2080]):
                assert bool(member["membership"][i // 8] & (1 << (i % 8))) == (1024 <= x <= 2047)
            _same(paged.evict(), memory.evict())
            _same(paged.rebuild(), memory.rebuild())
            _same(
                paged.range(1100.25, 2090.5, exact=True), memory.range(1100.25, 2090.5, exact=True)
            )
            before = paged.membership(first, len(rows))
            with pytest.raises(FilterTierCError) as error:
                paged.append({"x": [4100.0], "y": [1.0]})
            assert error.value.status == 7
            after = paged.membership(first, len(rows))
            assert after["membership"] == before["membership"]
            assert after["filter_hash"] == before["filter_hash"]


def test_paged_source_rejects_invalid_lease_schema_and_mixed_ingress(tmp_path):
    chart = xyg.scatter_chart(xyg.scatter(x=[0.0], y=[0.0]))
    a, b = tmp_path / "a.xygc", tmp_path / "b.xygc"
    _artifact(a, [(float(i), float(i)) for i in range(8)])
    _artifact(b, [(float(i), float(i)) for i in range(4)])
    with xyg.ChunkedColumns(a) as left, xyg.ChunkedColumns(b) as right:
        with pytest.raises(ValueError, match="plane"):
            left.column("other")
        with pytest.raises(TypeError, match="all arrays or all issued"):
            chart.filter_session({"x": left.column("x"), "y": [0.0] * 8}, source_id=1)
        with pytest.raises(FilterTierCError) as error:
            chart.filter_session({"x": left.column("x"), "y": right.column("y")}, source_id=1)
        assert error.value.status == 7
        ref = left.column("x")
    with pytest.raises(FilterTierCError) as error:
        chart.filter_session({"x": ref}, source_id=1)
    assert error.value.status == 7


def test_paged_source_admits_workspace_before_read_and_preserves_state(tmp_path):
    rows = [(float(i), float(i % 3)) for i in range(5000)]
    path = tmp_path / "source.xygc"
    _artifact(path, rows, chunk_rows=128)
    chart = xyg.scatter_chart(xyg.scatter(x=[0.0], y=[0.0]))
    with (
        xyg.ChunkedColumns(path) as source,
        chart.filter_session({"x": source.column("x")}, source_id=5, budget_bytes=32768) as session,
    ):
        path.write_bytes(b"")  # distinguish pre-I/O admission from a failed read
        with pytest.raises(FilterTierCError) as error:
            session.configure(
                dict(id=1, dimension="x", cuts=[1000]), [dict(id=2, dimension="x", cuts=[1000])]
            )
        assert error.value.status == 2
        # No index or intent was published by the refused build.
        assert session._handle
        with pytest.raises(FilterTierCError) as error:
            session.range(0, 1)
        assert error.value.status == 5
