"""Native immutable-frame public host lifecycle (real Rust, no numeric JSON)."""

import asyncio
import struct

import pytest

import xyg
from test_geo_retained import fixture_manifest, style
from test_geoscale import BUDGET, I64, U64, query
from xyg._geo_retained import RetainedGeoSource


def chart_fixture():
    manifest, chunk = fixture_manifest()
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    q = query(source.info)
    chart = xyg.geo_chart(
        xyg.geo_layer("points", source=source, layer_id=U64, query=q, sequence=1, style=style()),
        camera=q["camera"],
    )
    return source, chart


def request(adapter, op, *, mount="notebook", owner=0, sequence=0, payload=b""):
    raw = struct.pack("<4sIIIQQ", b"XYGH", 1, op, 0, owner, sequence) + payload
    return adapter.handle_host_message(
        dict(type="geo_host", request=f"{mount}:{op}", mount=mount), [raw]
    )


def test_public_geo_widget_inside_running_loop_release_ack_keeps_old_frame():
    async def notebook():
        source, chart = chart_fixture()
        widget = chart.widget()
        adapter = widget._adapter
        try:
            message, buffers = request(adapter, 1)
            assert "error" not in message
            assert len(buffers) == 3
            _, _, _, _, owner, sequence = struct.unpack("<4sIIIQQ", buffers[0])
            frame = adapter._frame
            assert buffers[1][:4] == b"XYGZ" and buffers[2][:4] == b"XYPB"
            assert frame.data.record(0)["feature_id"] == U64
            assert frame.data.identity["time"]["instant"] == I64
            with pytest.raises(ValueError):
                source.update(query(source.info), sequence=2, style=b"bad")
            assert request(adapter, 1, mount="second")[0]["error"]
            source.close()
            # A close request cannot prove that remote CPU/GPU buffers dropped.
            widget.close()
            assert adapter.mounted and frame.data.record(0)["feature_id"] == U64
            _, hits = request(
                adapter,
                2,
                owner=owner,
                sequence=sequence,
                payload=struct.pack("<3dII", 400, 300, 0, 1, 10),
            )
            aux = struct.unpack("<4sIIIQQ", hits[0])[4]
            assert U64 in {
                struct.unpack_from("<Q", hits[1], at + 8)[0] for at in range(256, len(hits[1]), 48)
            }
            assert request(adapter, 4, owner=owner, sequence=sequence)[0]["error"]
            hits = None
            assert "error" not in request(adapter, 5, owner=aux, sequence=sequence)[0]
            buffers = None
            assert "error" not in request(adapter, 4, owner=owner, sequence=sequence)[0]
            assert not adapter.mounted
            with pytest.raises(RuntimeError):
                _ = frame.data
            assert request(adapter, 1)[0]["error"]
        finally:
            widget.close()
            source.close()

    asyncio.run(notebook())


def test_remount_prepares_independent_data_same_authority_without_requery():
    source, chart = chart_fixture()
    adapter = chart.host()
    try:
        _, outgoing = request(adapter, 1)
        owner, seq = struct.unpack("<4sIIIQQ", outgoing[0])[4:]
        old = adapter._frame
        packet = outgoing[1]
        outgoing = None
        assert "error" not in request(adapter, 4, owner=owner, sequence=seq)[0]
        _, newer = request(adapter, 1, mount="reopened")
        newowner, seq = struct.unpack("<4sIIIQQ", newer[0])[4:]
        assert newowner != owner
        assert newer[1] == packet
        with pytest.raises(RuntimeError):
            _ = old.data
        assert request(adapter, 4, mount="reopened", owner=owner, sequence=seq)[0]["error"]
        newer = packet = None
        assert "error" not in request(adapter, 4, mount="reopened", owner=newowner, sequence=seq)[0]
    finally:
        adapter.close()
        source.close()


def test_host_canonical_identity_is_bounded_frozen_and_content_addressed():
    import reflex_xy
    from reflex_xy.registry import registry

    source, chart = chart_fixture()
    facade = chart.host()
    original = facade.build_payload()[1]
    try:
        assert len(original) == 304
        assert original[:4] == b"XYGQ"
        assert not any(original[16:24])  # Instance-local source handle is not authoring identity.
        token = reflex_xy.inline(chart)
        other = chart.host()
        assert other.build_payload()[1] == original
        assert registry.get(token).figure.build_payload()[1] == original
        # A caller mutation cannot alter an already authored host frame.
        chart.camera["center_x"] = 5.0
        assert facade.build_payload()[1] == original
        _, buffers = request(facade, 1)
        assert facade._frame.data.identity["camera"]["center_x"] == 0.0
        owner, sequence = struct.unpack("<4sIIIQQ", buffers[0])[4:]
        buffers = None
        request(facade, 4, owner=owner, sequence=sequence)
        registry.release(token)
        other.close()
    finally:
        facade.close()
        source.close()


def test_native_host_exact_aggregate_membership_and_work_bound():
    from test_geo_retained import aggregate_fixture

    manifest, chunk = aggregate_fixture()
    source = RetainedGeoSource(manifest, lambda _: chunk, budget={**BUDGET, "page_rows": 1})
    q = query(source.info)
    q.update(time=dict(kind=0), max_cells=1, previous_direct=False)
    facade = xyg.geo_chart(
        xyg.geo_layer("points", source=source, layer_id=U64, query=q, sequence=1, style=style()),
        camera=q["camera"],
    ).host()
    try:
        _, buffers = request(facade, 1)
        owner, sequence = struct.unpack("<4sIIIQQ", buffers[0])[4:]
        assert facade._frame.data.aggregate
        assert buffers[1] is facade._frame.data.packet.obj  # No extra backend packet copy.
        buffers = None
        assert request(
            facade, 3, owner=owner, sequence=sequence, payload=struct.pack("<IIQ", 0, 0, 1_000_001)
        )[0]["error"]
        _, page = request(
            facade, 3, owner=owner, sequence=sequence, payload=struct.pack("<IIQ", 0, 0, 1_000_000)
        )
        aux = struct.unpack("<4sIIIQQ", page[0])[4]
        assert struct.unpack_from("<Q", page[1], 464)[0] == U64
        assert len(page[1]) == 496  # 256-byte envelope, opaque 208-byte cursor, one record.
        page = None
        request(facade, 5, owner=aux, sequence=sequence)
        request(facade, 4, owner=owner, sequence=sequence)
    finally:
        facade.close()
        source.close()


def test_host_rejects_other_source_kinds_before_protocol_access(monkeypatch):
    from types import SimpleNamespace

    source, chart = chart_fixture()
    try:
        monkeypatch.setattr(
            type(chart), "_retained_layer", lambda self: SimpleNamespace(source=object())
        )
        with pytest.raises(
            ValueError, match="canonical RetainedGeoSource; indexed hosts are pending"
        ):
            chart.host()
    finally:
        source.close()
