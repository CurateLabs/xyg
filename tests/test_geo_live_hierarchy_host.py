"""Actual native selected hierarchy updates through the existing host transaction."""

import struct

import numpy as np
import pytest

import xyg
from test_geo_hierarchy import storage
from test_geo_host import request
from test_geo_live_host import ack, live, prepare
from test_geo_retained import fixture_manifest, style
from test_geoscale import BUDGET, U64, query
from xyg import _geoscale as g
from xyg._geo_hierarchy import GeoHierarchy
from xyg._geo_retained import RetainedGeoSource
from xyg._geo_selected import GeoSelectedScope


def fixture(*, null_second=False):
    manifest, chunk = fixture_manifest()
    intent = [U64]
    if null_second:
        descriptor = bytearray(104)
        struct.pack_into("<4s5I5Q", descriptor, 0, b"XYGD", 1, 1, 4326, 1, 0, 2, 1, 0, 0, 0)
        struct.pack_into("<2d", descriptor, 64, 0.0, 0.0)
        descriptor[80:82] = b"\x01\x00"
        struct.pack_into("<2Q", descriptor, 88, U64, (1 << 53) + 1)
        chunk = g.read(
            g.encode_chunk_request(dict(descriptor=descriptor, rows=2), BUDGET["processor_bytes"]),
            BUDGET["processor_bytes"],
        )
        builder = g.decode_reply(g.execute(g.encode_request(dict(command=1))))["handle"]
        try:
            g.execute(g.encode_request(dict(command=2, handle=builder, payload=chunk)))
            g.execute(g.encode_request(dict(command=3, handle=builder, generation=U64)))
            manifest = g.read(
                g.encode_request(dict(command=21, handle=builder)), BUDGET["processor_bytes"]
            )
        finally:
            g.execute(g.encode_request(dict(command=10, handle=builder)))
        intent.append((1 << 53) + 1)
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    q = dict(query(source.info), camera_revision=1, time_revision=1, state_revision=1)
    original = source.update(q, sequence=1, style=style())
    scope = GeoSelectedScope.from_frame(original, namespace=777, layer_id=U64)
    selected_state = scope.state(
        revision=1, ids=np.array(intent, dtype="<u8"), fill=b"\0\xff\0\xff"
    )
    operation = selected_state.begin(source, q, sequence=2)
    operation.drive()
    selected = operation.prepare(style())
    selected_state.close()
    lane = GeoHierarchy.from_selected_frame(selected, source, **storage({}))
    state = scope.state(revision=1, ids=np.array(intent, dtype="<u8"), fill=b"\0\xff\0\xff")
    operation = lane.begin_selected(state, q, sequence=3)
    operation.drive()
    frame = operation.prepare(style())
    state.close()
    chart = xyg.geo_chart(
        xyg.geo_layer("points", source=source, layer_id=U64, query=q, sequence=3, style=style()),
        camera=q["camera"],
    )
    adapter = chart.host(frame=frame, selected_scope=scope, hierarchy_lane=lane)
    original.close()
    selected.close()
    source.close()
    return source, scope, lane, frame, chart, adapter


def cleanup(scope, lane, frame, adapter):
    c = adapter._live_candidate
    if c.frame is not None:
        op = 8 if c.committed else 9
        old = c.retired if c.committed else adapter._frame
        live(
            adapter,
            op,
            struct.pack(
                "<4sIIIQQ3Q8x",
                b"XYGH",
                2,
                op,
                0,
                old.handle,
                c.retired_sequence if c.committed else adapter._sequence,
                c.nonce,
                c.frame.handle,
                c.sequence,
            ),
        )
    if adapter.mounted:
        request(adapter, 4, owner=adapter._frame.handle, sequence=adapter._sequence)
    adapter.close()
    frame.close()
    lane.close()
    scope.close()


def test_selected_hierarchy_camera_time_route_after_original_source_disposal(monkeypatch):
    calls = []
    execute = g.execute
    active = False

    def tracked(packet):
        command = struct.unpack_from("<I", packet, 8)[0]
        if active:
            calls.append(command)
            assert command not in (5, 18, 35, 36, 38, 39), "implicit alternate query route"
        return execute(packet)

    monkeypatch.setattr(g, "execute", tracked)
    source, scope, lane, frame, _, adapter = fixture()
    frame.close()  # Caller original is independent of the adapter anchor.
    request(adapter, 1)
    active = True
    try:
        for sequence in (4, 5):
            old, old_seq = adapter._frame, adapter._sequence
            reply, packets = prepare(adapter, nonce=sequence, sequence=sequence)
            assert "error" not in reply, reply
            assert adapter._frame is old
            assert "error" not in live(adapter, 7, ack(7, old.handle, old_seq, packets[0]))[0]
            accepted = adapter._frame
            assert accepted.data.selection["ids"].tolist() == [U64]
            assert accepted.data.record(0)["feature_id"] == U64
            assert "error" not in live(adapter, 8, ack(8, old.handle, old_seq, packets[0]))[0]
            page = accepted.rows()
            assert page.data.record(0)["feature_id"] == U64
            page.close()
        assert calls.count(43) == calls.count(44) == 2
        assert lane._creation_sequence == 2
        assert source._closed
    finally:
        active = False
        cleanup(scope, lane, frame, adapter)


def test_lane_exclusive_claim_and_closed_lane_preserve_static_frame():
    _, scope, lane, frame, chart, adapter = fixture()
    try:
        with pytest.raises(RuntimeError, match="another live adapter"):
            chart.host(frame=frame, selected_scope=scope, hierarchy_lane=lane)
        request(adapter, 1)
        accepted = adapter._frame
        lane.close()
        reply, packets = prepare(adapter, sequence=4)
        assert reply["prepareAbsent"] is True
        assert packets == [] and adapter._frame is accepted
        assert accepted.data.selection["ids"].tolist() == [U64]
    finally:
        cleanup(scope, lane, frame, adapter)


@pytest.mark.parametrize("mutation", (33, 43, 44))
def test_lost_mutation_confirmation_settles_issued_operation_without_alternate_query(
    monkeypatch, mutation
):
    execute = g.execute
    lose = True
    active = False

    def interrupted(packet):
        nonlocal lose
        result = execute(packet)
        if struct.unpack_from("<I", packet, 8)[0] == mutation and lose and active:
            lose = False
            raise OSError("lost mutation confirmation")
        return result

    monkeypatch.setattr(g, "execute", interrupted)
    _, scope, lane, frame, _, adapter = fixture()
    request(adapter, 1)
    old = adapter._frame
    active = True
    try:
        reply, packets = prepare(adapter, sequence=4)
        assert reply["prepareAbsent"] is True
        assert packets == [] and adapter._frame is old
        assert lane.pending_operation is None
        active = False
        monkeypatch.setattr(g, "execute", execute)
        reply, _ = prepare(adapter, sequence=5)
        assert "error" not in reply, reply
    finally:
        active = False
        monkeypatch.setattr(g, "execute", execute)
        cleanup(scope, lane, frame, adapter)


def test_exact_max_signed_time_excludes_paint_without_losing_original_row_intent():
    _, scope, lane, frame, _, adapter = fixture()
    request(adapter, 1)
    try:
        raw = bytearray(256)
        struct.pack_into(
            "<4sIIIQQ5QI4x2q",
            raw,
            0,
            b"XYGH",
            2,
            6,
            0,
            adapter._frame.handle,
            adapter._sequence,
            1,
            4,
            4,
            4,
            1,
            1,
            (1 << 63) - 1,
            0,
        )
        from xyg import _geoviewport as viewport

        raw[96:224] = viewport.encode_request(adapter._frame.data.identity["camera"])
        old = adapter._frame
        reply, packets = live(adapter, 6, raw)
        assert "error" not in reply, reply
        assert "error" not in live(adapter, 7, ack(7, old.handle, 3, packets[0]))[0]
        accepted = adapter._frame
        assert accepted.data.selection["ids"].tolist() == [U64]
        assert accepted.data.selection["visible_vertices"] == 0
        rows = accepted.rows()
        try:
            records = [rows.data.record(i) for i in range(rows.data.count)]
            assert len(records) == 2
            assert records[0]["selected"] is True
            assert all(not r["time_eligible"] for r in records)
        finally:
            rows.close()
        assert "error" not in live(adapter, 8, ack(8, old.handle, 3, packets[0]))[0]
    finally:
        cleanup(scope, lane, frame, adapter)


def test_null_original_row_intent_survives_live_camera_change_without_geometry_mask():
    _, scope, lane, frame, _, adapter = fixture(null_second=True)
    request(adapter, 1)
    try:
        old = adapter._frame
        reply, packets = prepare(adapter, sequence=4)
        assert "error" not in reply, reply
        assert "error" not in live(adapter, 7, ack(7, old.handle, 3, packets[0]))[0]
        accepted = adapter._frame
        assert accepted.data.selection["ids"].tolist() == [(1 << 53) + 1, U64]
        rows = accepted.rows()
        try:
            row = rows.data.record(1)
            assert row["feature_id"] == (1 << 53) + 1
            assert row["geometry_null"] is True
            assert row["selected"] is True
            assert row["eligible"] is False
        finally:
            rows.close()
        assert "error" not in live(adapter, 8, ack(8, old.handle, 3, packets[0]))[0]
    finally:
        cleanup(scope, lane, frame, adapter)


def test_sync_cancel_generation_after_real44_releases_candidate_and_keeps_old_paint(monkeypatch):
    execute = g.execute
    cancel = True
    active = False

    def interrupted(packet):
        nonlocal cancel
        result = execute(packet)
        if struct.unpack_from("<I", packet, 8)[0] == 44 and cancel and active:
            cancel = False
            # Sync callbacks cannot be interrupted, but admission cancellation
            # advances synchronously and rejects the just-prepared candidate.
            with pytest.raises(RuntimeError, match="callback failure"):
                lane.cancel()
        return result

    monkeypatch.setattr(g, "execute", interrupted)
    _, scope, lane, frame, _, adapter = fixture()
    request(adapter, 1)
    active = True
    try:
        old = adapter._frame
        reply, packets = prepare(adapter, sequence=4)
        assert reply["prepareAbsent"] is True
        assert packets == [] and adapter._frame is old
        assert lane.pending_operation is None
        assert adapter._live_candidate.cleanup_frame is None
        active = False
        monkeypatch.setattr(g, "execute", execute)
        assert "error" not in prepare(adapter, sequence=5)[0]
    finally:
        active = False
        monkeypatch.setattr(g, "execute", execute)
        cleanup(scope, lane, frame, adapter)


def selected_fixture(indexed):
    manifest, chunk = fixture_manifest()
    origin = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    q = dict(query(origin.info), camera_revision=1, time_revision=1, state_revision=1)
    original = origin.update(q, sequence=1, style=style())
    pages = {}
    source = (
        original.spatial_index(
            grid=16,
            max_vertices=1000000,
            read_page=lambda t: pages[t["page"]],
            write_page=lambda t, b: pages.__setitem__(t["page"], bytes(b)),
        )
        if indexed
        else origin
    )
    scope = GeoSelectedScope.from_frame(original, namespace=777, layer_id=U64)
    state = scope.state(revision=1, ids=np.array([U64], dtype="<u8"), fill=b"\0\xff\0\xff")
    operation = state.begin(source, q, sequence=2, indexed=indexed)
    operation.drive()
    frame = operation.prepare(style())
    if indexed:
        operation.close()
    state.close()
    chart = xyg.geo_chart(
        xyg.geo_layer("points", source=source, layer_id=U64, query=q, sequence=2, style=style()),
        camera=q["camera"],
    )
    adapter = chart.host(frame=frame, selected_scope=scope)
    original.close()
    frame.close()
    return origin, source, scope, adapter


@pytest.mark.parametrize("route", ("canonical", "indexed", "hierarchy"))
@pytest.mark.parametrize("mode", ("lost", "corrupt", "cleanup_rejected"))
def test_state_allocation_reply_and_cleanup_recover_exact_owner(monkeypatch, route, mode):
    if route == "hierarchy":
        source, scope, lane, frame, _, adapter = fixture()
        origin = source
    else:
        origin, source, scope, adapter = selected_fixture(route == "indexed")
    request(adapter, 1)
    old = adapter._frame
    sequence = adapter._sequence + 1
    execute = g.execute
    fail = True
    cleanup_failures = 3 if mode == "cleanup_rejected" else 0
    receipts = []

    def interrupted(packet):
        nonlocal fail, cleanup_failures
        command = struct.unpack_from("<I", packet, 8)[0]
        if command == 10 and cleanup_failures:
            cleanup_failures -= 1
            raise OSError("injected State cleanup rejection")
        result = execute(packet)
        if command == 33:
            receipts.append(
                (g.decode_reply(result)["handle"], struct.unpack_from("<Q", packet, 24)[0])
            )
            if fail:
                fail = False
                if mode == "corrupt":
                    broken = bytearray(result)
                    broken[0] ^= 1
                    return bytes(broken)
                raise OSError("lost State allocation confirmation")
        return result

    monkeypatch.setattr(g, "execute", interrupted)
    try:
        reply, packets = prepare(adapter, sequence=sequence)
        assert reply["error"] and packets == [] and adapter._frame is old
        if mode == "cleanup_rejected":
            assert "prepareAbsent" not in reply
            assert adapter._live_candidate.cleanup_allocation is not None
            assert request(adapter, 4, owner=old.handle, sequence=adapter._sequence)[0]["error"]
            monkeypatch.setattr(g, "execute", execute)
            reply, _ = prepare(adapter, sequence=sequence)
        assert reply["prepareAbsent"] is True
        assert adapter._live_candidate.cleanup_allocation is None
        assert len(receipts) == 2 and receipts[0] == receipts[1] and receipts[0][1] > 0
        monkeypatch.setattr(g, "execute", execute)
        reply, packets = prepare(adapter, sequence=sequence + 1)
        assert "error" not in reply, reply
        assert "error" not in live(adapter, 9, ack(9, old.handle, adapter._sequence, packets[0]))[0]
        assert old.data.selection["ids"].tolist() == [U64]
    finally:
        monkeypatch.setattr(g, "execute", execute)
        if route == "hierarchy":
            cleanup(scope, lane, frame, adapter)
        else:
            from test_geo_live_host import close

            close(source, adapter)
            origin.close()
            scope.close()
