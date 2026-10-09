"""Real native overview host ownership; domain ordinals are never source IDs."""

import asyncio
import struct

import pytest

import xyg
from test_geo_host import request
from test_geo_live_host import ack, live, prepare


def fixture(*, split_time=False, read_page=None):
    from test_geo_retained import fixture_manifest, style
    from test_geoscale import BUDGET
    from test_geoscale import query as author_query
    from xyg._geo_overview_source import GeoOverviewIndex
    from xyg._geo_retained import RetainedGeoSource

    manifest, chunk = fixture_manifest()
    if split_time:
        from test_geoscale import U64, source_fixture
        from xyg import _geoscale as g

        author, _ = source_fixture()
        author = bytearray(author)
        time_at = 288 + struct.unpack_from("<Q", author, 256)[0]
        struct.pack_into("<q", author, time_at + 8, 0)
        struct.pack_into("<q", author, time_at + 16, 0)
        chunk = g.read(bytes(author), BUDGET["processor_bytes"])
        builder = g.decode_reply(g.execute(g.encode_request(dict(command=1))))["handle"]
        try:
            g.execute(g.encode_request(dict(command=2, handle=builder, payload=chunk)))
            g.execute(g.encode_request(dict(command=3, handle=builder, generation=U64)))
            manifest = g.read(
                g.encode_request(dict(command=21, handle=builder)), BUDGET["processor_bytes"]
            )
        finally:
            g.execute(g.encode_request(dict(command=10, handle=builder)))
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    query = author_query(source.info)
    for name in ("camera_revision", "time_revision", "state_revision"):
        query[name] = 1
    seed = source.update(query, sequence=1, style=style())
    pages = {}
    index = GeoOverviewIndex.from_frame(
        seed,
        source,
        budget=BUDGET,
        max_vertices=1000,
        read_chunk=lambda _: chunk,
        read_page=lambda t: read_page(t, pages) if read_page else pages[t["namespace"], t["page"]],
        write_page=lambda t, b: pages.__setitem__((t["namespace"], t["page"]), bytes(b)),
    )
    query.update(max_cells=0, max_projected_vertices=0, previous_direct=False)
    chart = xyg.geo_chart(
        xyg.geo_layer("density", source=index, layer_id=query["layer_id"], query=query, sequence=2),
        camera=query["camera"],
    )
    return source, seed, index, chart


def cleanup(source, seed, index, adapter):
    c = adapter._live_candidate
    if c.frame is not None:
        old = c.retired if c.committed else adapter._frame
        old_sequence = c.retired_sequence if c.committed else adapter._sequence
        tag = struct.pack(
            "<4sIIIQQ3Q8x",
            b"XYGH",
            2,
            6,
            0,
            old.handle,
            old_sequence,
            c.nonce,
            c.frame.handle,
            c.sequence,
        )
        live(
            adapter,
            8 if c.committed else 9,
            ack(8 if c.committed else 9, old.handle, old_sequence, tag),
        )
    if adapter.mounted:
        request(
            adapter,
            4,
            owner=adapter._frame.handle,
            sequence=adapter._sequence,
            mount=adapter._mount,
        )
    adapter.close()
    index.close()
    seed.close()
    source.close()


def test_overview_stage_cas_exact_retirement_keeps_caller_current_independent():
    source, seed, index, chart = fixture()
    caller = chart.compile()
    adapter = chart.host(frame=caller)
    try:
        message, buffers = request(adapter, 1)
        assert "error" not in message
        assert buffers[1][:4] == b"XYOV" and buffers[2][:4] == b"XYPB"
        old = adapter._frame
        assert old is not caller and index.current is caller
        total = sum(old.data.count(i) for i in range(256))
        message, candidate = prepare(adapter, sequence=3)
        assert "error" not in message
        assert adapter._frame is old
        assert sum(caller.data.count(i) for i in range(256)) == total
        tag = candidate[0]
        candidate = buffers = None
        assert "error" not in live(adapter, 7, ack(7, old.handle, 2, tag))[0]
        assert index.current is caller
        assert adapter._frame.data.final is False
        assert live(adapter, 8, ack(8, old.handle + 1, 2, tag))[0]["error"]
        assert "error" not in live(adapter, 8, ack(8, old.handle, 2, tag))[0]
        with pytest.raises(RuntimeError):
            _ = old.data
        assert sum(caller.data.count(i) for i in range(256)) == total
        caller.close()
        assert adapter._frame.data.identity["sequence"] == 3
    finally:
        caller.close()
        cleanup(source, seed, index, adapter)


def test_overview_widget_in_running_loop_retains_private_frame_until_browser_ack():
    async def journey():
        source, seed, index, chart = fixture()
        widget = chart.widget()
        adapter = widget._adapter
        try:
            message, buffers = request(adapter, 1)
            assert "error" not in message and buffers[1][:4] == b"XYOV"
            frame = adapter._frame
            assert index.current is None
            assert frame.data.final is False
            assert request(adapter, 1, mount="second")[0]["error"]
            owner, sequence = frame.handle, frame.sequence
            assert request(
                adapter,
                2,
                owner=owner,
                sequence=sequence,
                payload=struct.pack("<3dII", 400, 300, 0, 1, 10),
            )[0]["error"]
            assert adapter._aux is None
            source.close()
            seed.close()
            index.close()
            closed_query, _ = prepare(adapter, sequence=3)
            assert closed_query["error"] and closed_query["prepareAbsent"] is True
            assert adapter._frame is frame
            widget.close()
            assert adapter.mounted and frame.data.count(0) >= 0
            buffers = None
            assert "error" not in request(adapter, 4, owner=owner, sequence=sequence)[0]
            assert not adapter.mounted
            with pytest.raises(RuntimeError):
                _ = frame.data
        finally:
            cleanup(source, seed, index, adapter)

    asyncio.run(journey())


def test_overview_abort_replay_and_same_private_anchor_remount():
    source, seed, index, chart = fixture()
    adapter = chart.host()
    try:
        assert "error" not in request(adapter, 1)[0]
        old = adapter._frame
        message, buffers = prepare(adapter, sequence=3)
        assert "error" not in message
        tag = buffers[0]
        buffers = None
        assert "error" not in live(adapter, 9, ack(9, old.handle, 2, tag))[0]
        assert "error" not in live(adapter, 9, ack(9, old.handle, 2, tag))[0]
        assert adapter._frame is old and index.current is None
        assert "error" not in request(adapter, 4, owner=old.handle, sequence=2)[0]
        assert "error" not in request(adapter, 1, mount="replacement")[0]
        assert adapter._frame is old
    finally:
        cleanup(source, seed, index, adapter)


def test_host_canonical_capture_ignores_public_overview_method_replacement(monkeypatch):
    from xyg import _geo_overview_source as owner

    source, seed, index, chart = fixture()
    caller = chart.compile()
    adapter = chart.host()

    def changed(*args, **kwargs):
        raise AssertionError("public method redirected host ownership")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(owner.GeoOverviewFrame, "retain", changed)
            patch.setattr(owner.GeoOverviewFrame, "close", changed)
            patch.setattr(owner, "update_overview_index", changed)
            patch.setattr(owner, "overview_frame_authority", changed)
            patch.setattr(index, "update", changed)
            assert "error" not in request(adapter, 1)[0]
            assert adapter._frame is not caller
            prepared, buffers = prepare(adapter, sequence=3)
            assert "error" not in prepared
            tag, old = buffers[0], adapter._frame
            buffers = None
            assert "error" not in live(adapter, 7, ack(7, old.handle, 2, tag))[0]
            assert "error" not in live(adapter, 8, ack(8, old.handle, 2, tag))[0]
            assert index.current is caller
    finally:
        caller.close()
        cleanup(source, seed, index, adapter)


def test_medium_native_overview_mount_keeps_fixed_count_packet_and_declared_caps():
    from test_geo_retained import aggregate_fixture, style
    from test_geoscale import BUDGET, query
    from xyg._geo_overview_source import GeoOverviewIndex
    from xyg._geo_retained import RetainedGeoSource

    manifest, chunk = aggregate_fixture()
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    q = query(source.info)
    q.update(time={"kind": 0}, max_cells=1, previous_direct=False)
    seed = source.update(q, sequence=1, style=style())
    pages = {}
    index = GeoOverviewIndex.from_frame(
        seed,
        source,
        budget=BUDGET,
        max_vertices=32769,
        read_chunk=lambda _: chunk,
        read_page=lambda t: pages[t["namespace"], t["page"]],
        write_page=lambda t, b: pages.__setitem__((t["namespace"], t["page"]), bytes(b)),
    )
    q.update(max_cells=0, max_projected_vertices=0)
    chart = xyg.geo_chart(
        xyg.geo_layer("density", source=index, layer_id=q["layer_id"], query=q, sequence=2),
        camera=q["camera"],
    )
    adapter = chart.host()
    try:
        message, buffers = request(adapter, 1)
        assert "error" not in message
        assert len(buffers[1]) < 1 << 20
        assert sum(adapter._frame.data.count(i) for i in range(256)) == 32769
        assert adapter._frame.data.identity["source_rows"] == 32769
        assert index.current is None
        buffers = None
    finally:
        cleanup(source, seed, index, adapter)


@pytest.mark.parametrize("supplied", [False, True])
def test_lost_retained_copy_keeps_private_guard_before_host_error(monkeypatch, supplied):
    from xyg._geo_overview_source import GeoOverviewUncertainAllocation, _transport

    source, seed, index, chart = fixture()
    caller = chart.compile()
    adapter = None if supplied else chart.host()
    transport = _transport(index)
    actual = transport.native_execute
    copies = []
    lose = True

    def lost_copy(packet):
        result = actual(packet)
        if struct.unpack_from("<I", packet, 8)[0] == 26:
            copies.append(struct.unpack_from("<Q", result, 16)[0])
            if lose:
                raise OSError("lost after real retained-copy allocation")
        return result

    try:
        monkeypatch.setattr(transport, "native_execute", lost_copy)
        if supplied:
            with pytest.raises(GeoOverviewUncertainAllocation) as caught:
                chart.host(frame=caller)
            guard = caught.value.owner
            assert caller._retention is guard
        else:
            message, buffers = request(adapter, 1)
            assert message["error"] and not buffers
            guard = adapter._live_candidate.cleanup_operation
            assert guard is caller._retention
            assert not adapter.mounted
            assert request(adapter, 1)[0]["error"]
        assert len(copies) == 1
        assert caller.data.final is False
        lose = False
        monkeypatch.setattr(transport, "native_execute", actual)
        if supplied:
            guard.close()
        else:
            adapter.close()
            assert adapter._live_candidate.cleanup_operation is None
        assert guard._phase == "closed"
        assert len(set(copies)) == 1
        assert caller.data.final is False
    finally:
        lose = False
        monkeypatch.setattr(transport, "native_execute", actual)
        if caller._retention is not None:
            caller._retention.close()
        if adapter is not None:
            cleanup(source, seed, index, adapter)
        else:
            index.close()
            seed.close()
            source.close()
        caller.close()


def test_public_overview_inspection_cannot_retag_native_host_frame():
    source, seed, index, chart = fixture()
    caller = chart.compile()
    adapter = private = buffers = exact = None
    try:
        caller.data.scene = memoryview(bytes(160))
        caller.data.packet = memoryview(bytes(2464))
        caller.data.count = lambda _: (1 << 64) - 1
        adapter = chart.host(frame=caller)
        message, buffers = request(adapter, 1)
        assert "error" not in message
        assert buffers[1][:4] == b"XYOV" and buffers[2][:4] == b"XYPB"
        held = adapter._frame
        private = adapter._owner_data(held)
        assert sum(private.count(i) for i in range(256)) == 2
        exact = buffers[1]
        buffers = None
        assert "error" not in request(adapter, 4, owner=held.handle, sequence=held.sequence)[0]
        message, buffers = request(adapter, 1, mount="remounted")
        assert "error" not in message
        assert buffers[1] == exact and adapter._frame is held
        assert adapter._owner_data(held) is private
        private = buffers = exact = None
    finally:
        private = buffers = exact = None
        caller.close()
        if adapter is not None:
            cleanup(source, seed, index, adapter)
        else:
            index.close()
            seed.close()
            source.close()


def test_public_budget_mutation_before_open_and_during_borrow_cannot_retag_admission(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from xyg import _geoviewport as viewport
    from xyg._geo_overview_source import GeoOverviewIndex

    entered, settle = Event(), Event()
    armed = False

    def reader(ticket, pages):
        if armed:
            entered.set()
            assert settle.wait(10), "native overview page borrower never settled"
        return pages[ticket["namespace"], ticket["page"]]

    source, seed, index, chart = fixture(split_time=True, read_page=reader)
    adapter = chart.host()
    original_budget = GeoOverviewIndex.budget
    bad_budget = {**index.budget, "processor_bytes": 1}
    buffers = None
    try:
        monkeypatch.setattr(GeoOverviewIndex, "budget", property(lambda _: bad_budget))
        message, buffers = request(adapter, 1)
        assert "error" not in message
        old = adapter._frame
        assert sum(adapter._owner_data(old).count(i) for i in range(256)) == 1
        buffers = None
        monkeypatch.setattr(GeoOverviewIndex, "budget", original_budget)
        armed = True
        raw = bytearray(256)
        struct.pack_into(
            "<4sIIIQQ5QI4x2q",
            raw,
            0,
            b"XYGH",
            2,
            6,
            0,
            old.handle,
            2,
            1,
            3,
            3,
            3,
            1,
            1,
            -1,
            0,
        )
        raw[96:224] = viewport.encode_request(adapter._query["camera"], 3, (1.0, 0.0))
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(live, adapter, 6, raw)
            try:
                assert entered.wait(10), "query did not issue its genuine page read"
                monkeypatch.setattr(GeoOverviewIndex, "budget", property(lambda _: bad_budget))
                assert adapter._frame is old
            finally:
                settle.set()
            message, buffers = pending.result(timeout=10)
        assert "error" not in message
        assert adapter._frame is old
        tag = buffers[0]
        buffers = None
        assert "error" not in live(adapter, 7, ack(7, old.handle, 2, tag))[0]
        assert "error" not in live(adapter, 8, ack(8, old.handle, 2, tag))[0]
        assert sum(adapter._owner_data(adapter._frame).count(i) for i in range(256)) == 1
    finally:
        settle.set()
        buffers = None
        monkeypatch.setattr(GeoOverviewIndex, "budget", original_budget)
        cleanup(source, seed, index, adapter)
