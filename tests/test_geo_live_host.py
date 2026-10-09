"""Real native candidate/CAS/retirement proofs, independent of browser policy."""

import struct

import pytest

import xyg
from test_geo_host import request
from test_geo_retained import fixture_manifest, style
from test_geoscale import BUDGET, U64, query
from xyg import _geoviewport as viewport
from xyg._geo_retained import RetainedGeoSource


def fixture():
    manifest, chunk = fixture_manifest()
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    q = query(source.info)
    for name in ("camera_revision", "time_revision", "state_revision"):
        q[name] = 1
    chart = xyg.geo_chart(
        xyg.geo_layer("points", source=source, layer_id=U64, query=q, sequence=1, style=style()),
        camera=q["camera"],
    )
    return source, chart.host()


def live(adapter, op, raw):
    return adapter.handle_host_message(
        dict(type="geo_host", request=f"notebook:live{op}", mount="notebook"), [raw]
    )


def prepare(adapter, nonce=1, sequence=2, camera=None):
    a = adapter
    raw = bytearray(256)
    struct.pack_into(
        "<4sIIIQQ5QI4x2q",
        raw,
        0,
        b"XYGH",
        2,
        6,
        0,
        a._frame.handle,
        a._sequence,
        nonce,
        sequence,
        sequence,
        sequence,
        1,
        0,
        0,
        0,
    )
    raw[96:224] = viewport.encode_request(camera or a._query["camera"], 3, (1.0, 0.0))
    return live(a, 6, raw)


def ack(op, old, old_sequence, tag):
    return struct.pack("<4sIIIQQ", b"XYGH", 2, op, 0, old, old_sequence) + tag[32:64]


def close(source, adapter):
    if adapter._live_candidate.frame is not None:
        c = adapter._live_candidate
        if c.committed:
            live(
                adapter,
                8,
                struct.pack(
                    "<4sIIIQQ3Q8x",
                    b"XYGH",
                    2,
                    8,
                    0,
                    c.retired.handle,
                    c.retired_sequence,
                    c.nonce,
                    c.frame.handle,
                    c.sequence,
                ),
            )
        else:
            live(
                adapter,
                9,
                struct.pack(
                    "<4sIIIQQ3Q8x",
                    b"XYGH",
                    2,
                    9,
                    0,
                    adapter._frame.handle,
                    adapter._sequence,
                    c.nonce,
                    c.frame.handle,
                    c.sequence,
                ),
            )
    request(adapter, 4, owner=adapter._frame.handle, sequence=adapter._sequence)
    adapter.close()
    source.close()


def test_actual_candidate_has_no_visual_commit_and_requires_exact_retire_ack():
    source, adapter = fixture()
    request(adapter, 1)
    old = adapter._frame
    try:
        message, buffers = prepare(adapter)
        assert "error" not in message
        assert adapter._frame is old and source.current is old
        assert adapter._query["time"]["kind"] == 1
        tag = buffers[0]
        assert "error" not in live(adapter, 7, ack(7, old.handle, 1, tag))[0]
        accepted = adapter._frame
        assert accepted is not old and accepted.data.identity["time"] == {"kind": 0}
        assert old.data.record(0)["feature_id"] == U64
        assert live(adapter, 8, ack(8, old.handle + 1, 1, tag))[0]["error"]
        assert accepted.data.record(0)["feature_id"] == U64
        buffers = None
        assert "error" not in live(adapter, 8, ack(8, old.handle, 1, tag))[0]
        with pytest.raises(RuntimeError):
            _ = old.data
        assert "error" not in live(adapter, 8, ack(8, old.handle, 1, tag))[0]
    finally:
        close(source, adapter)


def test_process_candidate_slot_and_camera_authority_fail_closed():
    first, a = fixture()
    second, b = fixture()
    request(a, 1)
    request(b, 1)
    try:
        bad = {**a._query["camera"], "center_x": 1.0}
        assert prepare(a, camera=bad)[0]["error"]
        message, buffers = prepare(a)
        assert "error" not in message
        assert prepare(b)[0]["error"]
        assert b._frame.data.record(0)["feature_id"] == U64
        tag = buffers[0]
        assert "error" not in live(a, 9, ack(9, a._frame.handle, 1, tag))[0]
        assert "error" not in prepare(b)[0]
    finally:
        close(first, a)
        close(second, b)


def test_gated_native_read_cancel_settles_callback_before_exact_ack_and_recovers(monkeypatch):
    import concurrent.futures
    import threading

    from xyg import _geoscale as g

    source, adapter = fixture()
    request(adapter, 1)
    old = adapter._frame
    reader = source._reader
    entered, finish = threading.Event(), threading.Event()
    authority, acknowledgments = [], []
    execute = g.execute

    def tracked(raw):
        if struct.unpack_from("<I", raw, 8)[0] == 8:
            assert finish.is_set()
            acknowledgments.append(bytes(raw[256:]))
        return execute(raw)

    def gated(ticket):
        authority.append(bytes(ticket["raw"]))
        entered.set()
        assert finish.wait(5)
        return reader(ticket)

    monkeypatch.setattr(g, "execute", tracked)
    source._reader = gated
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(prepare, adapter)
            assert entered.wait(5)
            source.cancel()
            assert not pending.done() and not acknowledgments
            assert old.data.record(0)["feature_id"] == U64
            finish.set()
            message, attachments = pending.result(timeout=5)
            assert message["error"] and not attachments
        assert acknowledgments == authority
        assert adapter._frame is old and adapter._live_candidate.frame is None
        source._reader = reader
        assert "error" not in prepare(adapter, nonce=2, sequence=3)[0]
    finally:
        finish.set()
        source._reader = reader
        close(source, adapter)


def test_two_serial_pan_deltas_compose_against_each_new_accepted_camera():
    source, adapter = fixture()
    request(adapter, 1)
    initial = adapter._frame.data.identity["camera"]
    try:
        for nonce, sequence in ((1, 2), (2, 3)):
            old, old_sequence = adapter._frame.handle, adapter._sequence
            message, buffers = prepare(adapter, nonce=nonce, sequence=sequence)
            assert "error" not in message
            tag = buffers[0]
            assert "error" not in live(adapter, 7, ack(7, old, old_sequence, tag))[0]
            buffers = None
            assert "error" not in live(adapter, 8, ack(8, old, old_sequence, tag))[0]
        expected = viewport.geo_viewport(initial, 3, (2.0, 0.0))["camera"]
        assert adapter._frame.data.identity["camera"] == expected
    finally:
        close(source, adapter)


def test_explicit_selected_frame_preserves_full_intent_through_live_update():
    from xyg._geo_selected import GeoSelectedScope

    source, old_adapter = fixture()
    request(old_adapter, 1)
    original = old_adapter._frame
    q = dict(old_adapter._query)
    scope = GeoSelectedScope.from_frame(original, namespace=U64, layer_id=U64)
    import numpy as np

    state = scope.state(revision=1, ids=np.array([U64], dtype="<u8"), fill=bytes([0, 255, 0, 255]))
    operation = state.begin(source, q, sequence=2)
    operation.drive()
    selected = operation.prepare(style())
    chart = xyg.geo_chart(
        xyg.geo_layer("points", source=source, layer_id=U64, query=q, sequence=2, style=style()),
        camera=q["camera"],
    )
    authored = selected._query_packet
    changed_length = bytearray(authored)
    struct.pack_into("<Q", changed_length, 232, 0)
    changed_camera = bytearray(authored)
    changed_camera[80] ^= 1
    for invalid in (authored[:256], bytes(changed_length), bytes(changed_camera)):
        selected._query_packet = invalid
        with pytest.raises(ValueError):
            chart.host(frame=selected, selected_scope=scope)
    selected._query_packet = authored
    adapter = chart.host(frame=selected, selected_scope=scope)
    selected.close()
    request(old_adapter, 4, owner=original.handle, sequence=1)
    old_adapter.close()
    request(adapter, 1)
    try:
        assert adapter._frame.data.selection["ids"].tolist() == [U64]
        message, buffers = prepare(adapter, sequence=3)
        assert "error" not in message
        old, seq, tag = adapter._frame.handle, adapter._sequence, buffers[0]
        assert "error" not in live(adapter, 7, ack(7, old, seq, tag))[0]
        assert adapter._frame.data.selection["ids"].tolist() == [U64]
        assert bytes(adapter._frame.data.selection["fill"]) == bytes([0, 255, 0, 255])
        buffers = None
        assert "error" not in live(adapter, 8, ack(8, old, seq, tag))[0]
    finally:
        close(source, adapter)
        scope.close()


def test_cancel_after_native_data_creation_drops_candidate(monkeypatch):
    import threading

    source, adapter = fixture()
    request(adapter, 1)
    old = adapter._frame
    entered, resume = threading.Event(), threading.Event()
    original = source._prepare

    def gated(*args):
        frame = original(*args)
        entered.set()
        assert resume.wait(5)
        return frame

    monkeypatch.setattr(source, "_prepare", gated)
    replies = []
    thread = threading.Thread(target=lambda: replies.append(prepare(adapter)))
    try:
        thread.start()
        assert entered.wait(5)
        source.cancel()
        resume.set()
        thread.join(5)
        assert not thread.is_alive()
        assert "cancel" in replies[0][0]["error"].lower()
        assert adapter._live_candidate.frame is None
        assert adapter._frame is old
        assert old.data.record(0)["feature_id"] == U64
        monkeypatch.setattr(source, "_prepare", original)
        assert "error" not in prepare(adapter, sequence=3)[0]
    finally:
        resume.set()
        thread.join(5)
        close(source, adapter)


def test_widget_binary_updates_have_bounded_future_completion(monkeypatch):
    from concurrent.futures import Future

    from geo_live_fixture import live_chart_fixture

    source, chart = live_chart_fixture()
    widget = chart.widget()
    sent = []
    monkeypatch.setattr(
        widget, "send", lambda message, buffers=None: sent.append((message, buffers))
    )
    try:
        futures = [
            widget.update(
                operation=0,
                args=[],
                sequence=n,
                camera_revision=n,
                time_revision=n,
                state_revision=1,
                time={"kind": 1, "instant": -(1 << 63)},
            )
            for n in range(2, 18)
        ]
        assert all(isinstance(f, Future) and not f.done() for f in futures)
        assert len(sent) == 16 and len(sent[0][1][0]) == 128
        assert struct.unpack_from("<q", sent[0][1][0], 96)[0] == -(1 << 63)
        with pytest.raises(RuntimeError, match="queue"):
            widget.update(
                operation=0,
                args=[],
                sequence=18,
                camera_revision=18,
                time_revision=18,
                state_revision=1,
                time={"kind": 0},
            )
        widget._on_geo_message(widget, {"type": "geo_host_updated", "request": "unknown"}, [])
        assert not futures[0].done()
        widget._on_geo_message(
            widget, {"type": "geo_host_updated", "request": sent[0][0]["request"]}, []
        )
        assert futures[0].result() is None
        widget.close()
        assert all(f.done() for f in futures)
        assert all(isinstance(f.exception(), RuntimeError) for f in futures[1:])
    finally:
        widget.close()
        source.close()


@pytest.mark.parametrize("selected", [False, True])
def test_live_indexed_repeated_updates_keep_exact_intent(selected):
    import numpy as np

    from xyg._geo_selected import GeoSelectedScope

    manifest, chunk = fixture_manifest()
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    q = query(source.info)
    for key in ("camera_revision", "time_revision", "state_revision"):
        q[key] = 1
    canonical = source.update(q, sequence=1, style=style())
    pages = {}
    index = canonical.spatial_index(
        grid=16,
        max_vertices=1000000,
        read_page=lambda t: pages[t["page"]],
        write_page=lambda t, b: pages.__setitem__(t["page"], bytes(b)),
    )
    scope = (
        GeoSelectedScope.from_frame(canonical, namespace=U64, layer_id=U64) if selected else None
    )
    frame = None
    adapter = None
    try:
        if selected:
            state = scope.state(
                revision=1,
                ids=np.array([U64], dtype="<u8"),
                fill=bytes((0, 255, 0, 255)),
                budget=BUDGET,
            )
            operation = state.begin(index, q, sequence=2, indexed=True)
            operation.drive()
            frame = operation.prepare(style())
            operation.close()
            state.close()
        else:
            frame = index.update(q, sequence=2, style=style())
        chart = xyg.geo_chart(
            xyg.geo_layer("points", source=index, layer_id=U64, query=q, sequence=2, style=style()),
            camera=q["camera"],
        )
        adapter = chart.host(frame=frame, selected_scope=scope)
        frame.close()
        request(adapter, 1)
        for seq in (3, 4):
            old = adapter._frame
            message, out = prepare(adapter, nonce=seq, sequence=seq)
            assert "error" not in message, message
            live(adapter, 7, ack(7, old.handle, seq - 1, out[0]))
            live(adapter, 8, ack(8, old.handle, seq - 1, out[0]))
            assert adapter._frame.data.record(0)["feature_id"] == U64
            if selected:
                assert tuple(adapter._frame.data.selection["ids"]) == (U64,)
    finally:
        if adapter:
            close(index, adapter)
        else:
            index.close()
        if frame:
            frame.close()
        canonical.close()
        source.close()
        if scope:
            scope.close()


@pytest.mark.parametrize("error_type", [OSError, LookupError])
def test_reader_exception_is_a_terminal_reply_and_higher_sequence_recovers(error_type):
    source, adapter = fixture()
    request(adapter, 1)
    old, reader = adapter._frame, source._reader

    def fail(_ticket):
        raise error_type("source reader failed")

    source._reader = fail
    try:
        message, attachments = prepare(adapter)
        assert message["error"] == "source reader failed"
        assert message["prepareAbsent"] is True
        assert not attachments
        assert adapter._frame is old and old.data.record(0)["feature_id"] == U64
        assert adapter._live_candidate.frame is None
        assert adapter._live_candidate.cleanup_frame is None
        source._reader = reader
        recovered, attachments = prepare(adapter, nonce=2, sequence=3)
        assert "error" not in recovered and len(attachments) == 3
    finally:
        source._reader = reader
        close(source, adapter)


def test_hierarchy_static_mount_rejects_live_update_before_canonical_read():
    from test_geo_hierarchy import storage
    from test_geo_spatial import setup
    from xyg._geo_hierarchy import GeoHierarchy

    source, old, _ = setup()
    index = GeoHierarchy.from_frame(old, source, **storage({}))
    q = query(index.info)
    frame = index.update(q, sequence=2, style=style())
    chart = xyg.geo_chart(
        xyg.geo_layer("points", source=source, layer_id=U64, query=q, sequence=2, style=style()),
        camera=q["camera"],
    )
    adapter = chart.host(frame=frame)
    reader = source._reader

    def forbidden(_):
        raise AssertionError("hierarchy live update must not scan canonical source")

    try:
        request(adapter, 1)
        source._reader = forbidden
        accepted = adapter._frame
        reply, attachments = prepare(adapter, sequence=3)
        assert "explicit hierarchy route" in reply["error"]
        assert reply["prepareAbsent"] is True and not attachments
        assert adapter._frame is accepted and accepted.data.record(0)["feature_id"] == U64
        assert adapter._live_candidate.frame is None
    finally:
        source._reader = reader
        close(source, adapter)
        frame.close()
        index.close()
        old.close()
