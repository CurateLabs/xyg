"""Mounted scheduler control races; native presentation is tested in host journeys."""

import asyncio
import json
import struct
from dataclasses import replace
from pathlib import Path

import pytest

import xyg
from test_geo_host import chart_fixture, request
from xyg._geo_temporal import _BINDINGS


def test_premount_latest_foreign_thread_close_and_shared_claim():
    async def run():
        source, chart = chart_fixture()
        layer = chart.layers[0]
        q = dict(layer.properties["query"], camera_revision=1, time_revision=1)
        chart = replace(
            chart, layers=(replace(layer, properties={**layer.properties, "query": q}),)
        )
        widget = chart.widget()
        sent = []
        widget.send = lambda message, buffers=(): sent.append((message, buffers))
        controller = xyg.TemporalController(instance_id=17, domain=(-(1 << 63), (1 << 63) - 1))
        binding = widget.bind_temporal(controller)
        try:
            with pytest.raises(RuntimeError, match="already"):
                chart.bind_temporal(controller)
            await asyncio.to_thread(controller.set_cursor, 123)
            await asyncio.sleep(0)
            assert not sent  # no frontend-ready handshake, no posted intent
            idle = asyncio.create_task(binding.when_idle())
            await binding.aclose()
            await idle
            assert source not in _BINDINGS
            other = chart.bind_temporal(controller)
            with pytest.raises(RuntimeError, match="already"):
                widget.bind_temporal(controller)
            await other.aclose()
        finally:
            await binding.aclose()
            widget.close()
            controller.close()
            source.close()

    asyncio.run(asyncio.wait_for(run(), 15))


def test_bounded_intents_exact_mount_supersession_and_retryable_drain():
    async def run():
        source, chart = chart_fixture()
        layer = chart.layers[0]
        q = dict(layer.properties["query"], camera_revision=1, time_revision=1)
        chart = replace(
            chart, layers=(replace(layer, properties={**layer.properties, "query": q}),)
        )
        widget = chart.widget()
        sent = []
        widget.send = lambda message, buffers=(): sent.append((message, buffers))
        controller = xyg.TemporalController(instance_id=18, domain=(-(1 << 63), (1 << 63) - 1))
        binding = widget.bind_temporal(controller)
        adapter = widget._adapter
        try:
            assert "error" not in request(adapter, 1, mount="real")[0]
            widget._on_geo_message(widget, dict(type="geo_host_ready", mount="foreign"), [])
            await asyncio.sleep(0)
            assert not sent
            widget._on_geo_message(widget, dict(type="geo_host_ready", mount="real"), [])
            await asyncio.sleep(0)
            fixture = json.loads(
                (Path(__file__).parent / "fixtures/geo_mounted_temporal.json").read_text()
            )
            assert sent[0][1][0].hex() == fixture["instantMin"]
            first = sent[0][0]
            for value in range(1000):
                controller.set_cursor(value)
            await asyncio.sleep(0)
            assert len(sent) == 2  # one active packet, one invalidate; latest stays at host
            assert struct.unpack("<4sIIIqq3Q", sent[1][1][0])[:3] == (b"XYHT", 1, 3)
            widget._on_geo_message(
                widget,
                {
                    **first,
                    "type": "geo_host_temporal_done",
                    "mount": "old",
                    "status": "accepted",
                    "drained": True,
                },
                [],
            )
            assert len(sent) == 2
            widget._on_geo_message(
                widget,
                {
                    **first,
                    "type": "geo_host_temporal_done",
                    "status": "superseded",
                    "drained": True,
                },
                [],
            )
            await asyncio.sleep(0)
            latest = sent[-1]
            assert struct.unpack("<4sIIIqq3Q", latest[1][0])[4:6] == (999, 0)
            closing = asyncio.create_task(binding.aclose())
            await asyncio.sleep(0)
            assert source in _BINDINGS
            widget._on_geo_message(
                widget,
                {
                    **latest[0],
                    "type": "geo_host_temporal_done",
                    "status": "failed",
                    "drained": False,
                    "error": "lost abort ACK",
                },
                [],
            )
            with pytest.raises(RuntimeError, match="lost abort"):
                await closing
            assert source in _BINDINGS
            retry = asyncio.create_task(binding.aclose())
            await asyncio.sleep(0)
            while struct.unpack_from("<I", sent[-1][1][0], 8)[0] != 4:
                await asyncio.sleep(0)
            widget._on_geo_message(
                widget,
                {
                    **latest[0],
                    "type": "geo_host_temporal_done",
                    "status": "superseded",
                    "drained": True,
                },
                [],
            )
            await retry
            assert source not in _BINDINGS
            await binding.aclose()
            frame = adapter._frame
            assert frame.data.record(0)["feature_id"] == (1 << 64) - 1
        finally:
            if adapter.mounted:
                frame = adapter._frame
                request(adapter, 4, mount="real", owner=frame.handle, sequence=adapter._sequence)
            widget.close()
            controller.close()
            source.close()

    asyncio.run(asyncio.wait_for(run(), 15))


@pytest.mark.parametrize("reader_cancel", [False, True])
def test_explicit_executor_drains_native_read_cancellation_and_keeps_default_thread(reader_cancel):
    import threading

    from test_geo_live_host import ack

    async def run():
        source, chart = chart_fixture()
        layer = chart.layers[0]
        q = dict(layer.properties["query"], camera_revision=1, time_revision=1)
        chart = replace(
            chart, layers=(replace(layer, properties={**layer.properties, "query": q}),)
        )
        widget = chart.widget()
        adapter = widget._adapter
        sent = []
        widget.send = lambda message, buffers=(): sent.append((message, buffers))
        controller = xyg.TemporalController(instance_id=19, domain=(-100, 100))
        reader = source._reader
        threads = []
        entered, release = threading.Event(), threading.Event()

        def read(ticket):
            threads.append(threading.get_ident())
            if entered.is_set():
                release.wait()
                if reader_cancel:
                    raise asyncio.CancelledError("reader-originated cancellation")
            return reader(ticket)

        source._reader = read
        try:
            # Unbound widgets keep their established synchronous callback thread.
            raw = struct.pack("<4sIIIQQ", b"XYGH", 1, 1, 0, 0, 0)
            widget._on_geo_message(
                widget, dict(type="geo_host", request="open", mount="notebook"), [raw]
            )
            assert threads == [threading.get_ident()]
            binding = widget.bind_temporal(controller)
            # No ready message: the binding owns intent, but has sent no query.
            # Build a valid preparation with the real native host's existing helper.
            from xyg import _geoviewport

            packet = bytearray(256)
            struct.pack_into(
                "<4sIIIQQ5QI4x2q",
                packet,
                0,
                b"XYGH",
                2,
                6,
                0,
                adapter._frame.handle,
                adapter._sequence,
                1,
                2,
                1,
                1,
                adapter._query["state_revision"],
                1,
                -(1 << 63),
                0,
            )
            packet[96:224] = _geoviewport.encode_request(adapter._query["camera"], 0)
            entered.set()
            message = dict(type="geo_host", request="prepare", mount="notebook")
            widget._on_geo_message(widget, message, [packet])
            while len(threads) < 2:
                await asyncio.sleep(0)
            assert threads[-1] != threading.get_ident()
            worker = widget._geo_rpc_task
            worker.cancel()
            worker.cancel()
            assert not worker.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await worker
            response, attachments = next(
                item for item in sent if item[0].get("request") == "prepare"
            )
            if reader_cancel:
                assert "cancel" in response["error"]
                assert response["prepareAbsent"] is True
                assert adapter._live_candidate.frame is None
            else:
                assert "error" not in response
                old = adapter._frame
                tag = attachments[0]
                attachments = None
                assert (
                    "error"
                    not in adapter.handle_host_message(
                        dict(type="geo_host", request="abort", mount="notebook"),
                        [ack(9, old.handle, adapter._sequence, tag)],
                    )[0]
                )
            await binding.aclose()
            assert source not in _BINDINGS
        finally:
            release.set()
            if adapter.mounted:
                old = adapter._frame
                request(adapter, 4, owner=old.handle, sequence=adapter._sequence)
            widget.close()
            if widget._geo_rpc_task is not None:
                await widget._geo_rpc_task
            source.close()
            controller.close()

    asyncio.run(asyncio.wait_for(run(), 15))


def test_comm_notifications_from_foreign_notebook_loop_dispatch_to_owner():
    async def run():
        asyncio.get_running_loop().set_debug(True)
        source, chart = chart_fixture()
        widget = chart.widget()
        controller = xyg.TemporalController(instance_id=20, domain=(-100, 100))
        widget.send = lambda *args, **kwargs: None
        binding = widget.bind_temporal(controller)
        try:
            assert "error" not in request(widget._adapter, 1, mount="foreign-loop")[0]
            await asyncio.to_thread(
                widget._on_geo_message,
                widget,
                dict(type="geo_host_ready", mount="foreign-loop"),
                [],
            )
            await asyncio.sleep(0)
            active = binding._active
            assert active is not None
            await asyncio.to_thread(
                widget._on_geo_message,
                widget,
                {**active, "type": "geo_host_temporal_done", "status": "accepted", "drained": True},
                [],
            )
            await binding.when_idle()
            await binding.aclose()
        finally:
            frame = widget._adapter._frame
            request(widget._adapter, 4, mount="foreign-loop", owner=frame.handle, sequence=1)
            widget.close()
            await widget._geo_rpc_task
            controller.close()
            source.close()

    asyncio.run(asyncio.wait_for(run(), 15))


def mounted_chart_fixture(*, spread=False):
    """Same canonical IDs with a finite end for visible half-open host checks."""
    import numpy as np

    from test_geo_retained import style
    from test_geoscale import BUDGET, I64, U64, query, source_fixture
    from xyg import _geoscale as g

    original, _ = source_fixture()
    descriptor = bytearray(original[288:408])
    if spread:
        struct.pack_into("<d", descriptor, 80, 45.0)
    chunk = g.read(
        g.encode_chunk_request(
            dict(
                descriptor=descriptor,
                rows=2,
                intervals=dict(
                    starts=np.array([I64, I64], dtype="<i8"),
                    ends=np.array([100000, 100000], dtype="<i8"),
                    start_validity=np.ones(2, dtype="u1"),
                    end_validity=np.ones(2, dtype="u1"),
                ),
                values=np.array([0.0, 1.0], dtype="<f8"),
            ),
            BUDGET["processor_bytes"],
        ),
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
    source = xyg.RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    q = dict(query(source.info), camera_revision=1, time_revision=1)
    return source, xyg.geo_chart(
        xyg.geo_layer("points", source=source, layer_id=U64, query=q, sequence=1, style=style()),
        camera=q["camera"],
    )


def mounted_indexed_chart_fixture(*, selected=False):
    """External native index with a matching caller-owned mount frame."""
    import numpy as np

    from test_geo_retained import style
    from test_geoscale import U64
    from xyg import _geoscale as g
    from xyg._geo_retained import _attach_frame
    from xyg._geo_selected import GeoSelectedScope

    source, base = mounted_chart_fixture(spread=True)
    q = {**base.layers[0].properties["query"], "state_revision": 1}
    canonical = source.update(q, sequence=1, style=style())
    pages = {}
    index = canonical.spatial_index(
        grid=16,
        max_vertices=1000000,
        read_page=lambda ticket: pages[ticket["page"]],
        write_page=lambda ticket, packet: pages.__setitem__(ticket["page"], bytes(packet)),
    )
    scope = None
    if selected:
        scope = GeoSelectedScope.from_frame(canonical, namespace=U64, layer_id=U64)
        state = scope.state(revision=1, ids=np.array([U64], dtype="<u8"), fill=b"\0\xff\0\xff")
        operation = state.begin(index, q, sequence=2, indexed=True)
        operation.drive()
        frame = operation.prepare(style())
        packet = g.encode_request(
            dict(
                command=36,
                handle=index.handle,
                sequence=2,
                query=q,
                budget=index.budget,
                payload=bytes(8),
            )
        )
        _attach_frame(index, frame, 2, packet, style())
        index._sequence = 2
        operation.close()
        state.close()
    else:
        frame = index.update(q, sequence=2, style=style())
    chart = xyg.geo_chart(
        xyg.geo_layer("points", source=index, layer_id=U64, query=q, sequence=2, style=style()),
        camera=q["camera"],
    )
    canonical.close()
    source.close()
    return index, chart, frame, scope


@pytest.mark.parametrize("selected", [False, True])
def test_indexed_mounted_admission_extreme_controls_and_retryable_drain(selected):
    async def run():
        source, chart, caller, scope = mounted_indexed_chart_fixture(selected=selected)
        with pytest.raises(ValueError, match="explicit matching initial frame"):
            chart.widget()
        widget = chart.widget(frame=caller, selected_scope=scope)
        sent = []
        widget.send = lambda message, buffers=(): sent.append((message, buffers))
        controller = xyg.TemporalController(instance_id=61, domain=(-(1 << 63), (1 << 63) - 1))
        source_class = type(source)

        class UnissuedSubclass(source_class):
            pass

        try:
            source.__class__ = UnissuedSubclass
            with pytest.raises(ValueError, match="spatial index"):
                widget.bind_temporal(controller)
        finally:
            source.__class__ = source_class
        binding = widget.bind_temporal(controller)
        adapter = widget._adapter
        try:
            assert "error" not in request(adapter, 1, mount="indexed")[0]
            widget._on_geo_message(widget, dict(type="geo_host_ready", mount="indexed"), [])
            await asyncio.sleep(0)
            first = sent[-1][0]
            assert struct.unpack_from("<q", sent[-1][1][0], 16)[0] == -(1 << 63)
            for value in range(1000):
                controller.set_cursor(value)
            await asyncio.sleep(0)
            assert len(sent) == 2
            widget._on_geo_message(
                widget,
                {
                    **first,
                    "type": "geo_host_temporal_done",
                    "status": "superseded",
                    "drained": True,
                },
                [],
            )
            await asyncio.sleep(0)
            latest = sent[-1][0]
            assert struct.unpack_from("<q", sent[-1][1][0], 16)[0] == 999
            widget._on_geo_message(
                widget,
                {
                    **latest,
                    "type": "geo_host_temporal_done",
                    "status": "failed",
                    "drained": False,
                    "error": "lost indexed abort ACK",
                },
                [],
            )
            await binding.when_idle()
            assert source in _BINDINGS
            closing = asyncio.create_task(binding.aclose())
            await asyncio.sleep(0)
            while struct.unpack_from("<I", sent[-1][1][0], 8)[0] != 4:
                await asyncio.sleep(0)
            assert sent[-1][0] == latest
            widget._on_geo_message(
                widget,
                {
                    **latest,
                    "type": "geo_host_temporal_done",
                    "status": "superseded",
                    "drained": True,
                },
                [],
            )
            await closing
            assert source not in _BINDINGS
            assert caller.data.record(0)["feature_id"] == (1 << 64) - 1
            if selected:
                assert caller.data.selection["namespace"] == (1 << 64) - 1
            assert adapter._frame.data.record(0)["feature_id"] == (1 << 64) - 1
        finally:
            if adapter.mounted:
                request(
                    adapter,
                    4,
                    mount="indexed",
                    owner=adapter._frame.handle,
                    sequence=adapter._sequence,
                )
            widget.close()
            await widget._geo_rpc_task
            await binding.aclose()
            caller.close()
            controller.close()
            source.close()
            if scope is not None:
                scope.close()

    asyncio.run(asyncio.wait_for(run(), 15))


@pytest.mark.parametrize("selected", [False, True])
def test_indexed_mounted_native_time_membership_fallback_and_fixed_caps(selected):
    from test_geo_live_host import ack, close, live
    from xyg import _geoviewport

    source, chart, caller, scope = mounted_indexed_chart_fixture(selected=selected)
    widget = chart.widget(frame=caller, selected_scope=scope)
    adapter = widget._adapter
    original_current = source.current
    canonical_reads = []
    source._reader = lambda ticket: canonical_reads.append(ticket)

    def prepare(sequence, kind, start, end=0):
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
            sequence,
            sequence,
            sequence,
            sequence,
            1,
            kind,
            start,
            end,
        )
        raw[96:224] = _geoviewport.encode_request(adapter._query["camera"], 0)
        return live(adapter, 6, raw)

    try:
        assert "error" not in request(adapter, 1)[0]
        extrema = [
            (1, -(1 << 63), 0, 2),
            (1, (1 << 63) - 1, 0, 0),
            (2, 99999, 100000, 2),
            (2, 100000, 100001, 0),
        ]
        for sequence in range(3, 31):
            kind, start, end, count = extrema[(sequence - 3) % len(extrema)]
            old, old_sequence = adapter._frame.handle, adapter._sequence
            message, packets = prepare(sequence, kind, start, end)
            assert "error" not in message, (sequence, message)
            assert "error" not in live(adapter, 7, ack(7, old, old_sequence, packets[0]))[0]
            assert "error" not in live(adapter, 8, ack(8, old, old_sequence, packets[0]))[0]
            assert adapter._frame.data.length == count
            if count:
                assert adapter._frame.data.record(0)["feature_id"] == (1 << 64) - 1
                assert adapter._frame.data.record(1)["feature_id"] == (1 << 53) + 1
            if selected:
                assert adapter._frame.data.selection["namespace"] == (1 << 64) - 1
        accepted = adapter._frame
        capacity = source.budget["max_chunks"]
        source.budget["max_chunks"] = 1
        assert "explicit canonical full-source scan" in prepare(31, 1, 0)[0]["error"]
        assert adapter._frame is accepted
        source.budget["max_chunks"] = capacity
        reader = source._read_page

        def failed_page(_):
            raise OSError("indexed page storage failure")

        source._read_page = failed_page
        assert "indexed page storage failure" in prepare(32, 1, 0)[0]["error"]
        assert adapter._frame is accepted
        source._read_page = reader
        assert caller.data.record(0)["feature_id"] == (1 << 64) - 1
        assert source.current is original_current
        assert canonical_reads == []
    finally:
        close(source, adapter)
        widget.close()
        caller.close()
        if scope is not None:
            scope.close()


@pytest.mark.parametrize("action", [0, 2])
@pytest.mark.parametrize("cleanup", [False, True])
def test_indexed_selected_birth_retirement_failure_keeps_exact_retry_and_claim(
    monkeypatch, action, cleanup
):
    import ctypes

    import numpy as np

    from test_geo_retained import style
    from xyg import _native

    async def run():
        source, chart, caller, scope = mounted_indexed_chart_fixture(selected=True)
        widget = chart.widget(frame=caller, selected_scope=scope)
        controller = xyg.TemporalController(instance_id=64, domain=(-100, 100))
        binding = widget.bind_temporal(controller)
        q = chart.layers[0].properties["query"]
        state = scope.state(
            revision=1, ids=np.array([(1 << 64) - 1], dtype="<u8"), fill=b"\0\xff\0\xff"
        )
        operation = state.begin(source, q, sequence=3, indexed=True)
        operation.drive()
        actual = _native._lib.xyg_geo_scale_execute
        requests = []
        armed = True

        def dispatch(request, length, out, capacity):
            nonlocal armed
            raw = ctypes.string_at(request, length)
            command = struct.unpack_from("<I", raw, 8)[0]
            if command == 47 and struct.unpack_from("<I", raw, 256)[0] == 36:
                requests.append(raw)
                code = actual(request, length, out, capacity)
                if armed and struct.unpack_from("<I", raw, 260)[0] == action:
                    armed = False
                    raise OSError("lost indexed mutation retirement acknowledgement")
                return code
            return actual(request, length, out, capacity)

        frame = None
        try:
            monkeypatch.setattr(_native._lib, "xyg_geo_scale_execute", dispatch)
            with pytest.raises(OSError, match="retirement acknowledgement"):
                operation.prepare(style())
            assert operation._publication_pending
            assert source in _BINDINGS
            with pytest.raises(RuntimeError, match="already"):
                widget.bind_temporal(controller)
            if cleanup:
                await operation.aclose()
                await operation.aclose()
            else:
                frame = operation.prepare(style())
                assert not operation._publication_pending
                assert frame.data.record(0)["feature_id"] == (1 << 64) - 1
                operation.close()
                assert frame.data.record(0)["feature_id"] == (1 << 64) - 1
            matching = [r for r in requests if struct.unpack_from("<I", r, 260)[0] == action]
            assert len(matching) >= 2 and matching[0] == matching[1]
            assert operation._mutation._attempt._released
            assert caller.data.record(0)["feature_id"] == (1 << 64) - 1
        finally:
            monkeypatch.setattr(_native._lib, "xyg_geo_scale_execute", actual)
            operation.close()
            if frame is not None:
                frame.close()
            state.pending_operation.close()
            await binding.aclose()
            widget.close()
            await widget._geo_rpc_task
            caller.close()
            controller.close()
            source.close()
            scope.close()

    asyncio.run(asyncio.wait_for(run(), 15))


@pytest.mark.parametrize("cleanup", [False, True])
def test_async_indexed_selected_birth_release_failure_retains_publication(cleanup):
    import numpy as np

    from test_geo_retained import fixture_manifest, style
    from test_geoscale import BUDGET, U64, query
    from xyg import _geoscale as g
    from xyg._geo_selected import GeoSelectedScope

    async def run():
        native = g.NativeGeoScaleBridge(BUDGET["processor_bytes"])

        class Bridge:
            armed = False

            def __init__(self):
                self.releases = []

            async def execute(self, packet):
                reply = await native.execute(packet)
                if struct.unpack_from("<I", packet, 8)[0] == 47 and struct.unpack_from(
                    "<2I", packet, 256
                ) == (36, 2):
                    self.releases.append(bytes(packet))
                    if self.armed:
                        self.armed = False
                        raise OSError("lost asynchronous indexed birth release")
                return reply

            async def read(self, packet):
                return await native.read(packet)

        bridge = Bridge()
        manifest, chunk = fixture_manifest()

        async def reader(_):
            return chunk

        source = await xyg.RetainedGeoSource.create_async(
            manifest, reader, budget=BUDGET, bridge=bridge
        )
        q = {**query(source.info), "state_revision": 1}
        original = await source.aupdate(q, sequence=1, style=style())
        pages = {}

        async def read_page(ticket):
            return pages[ticket["page"]]

        async def write_page(ticket, packet):
            pages[ticket["page"]] = bytes(packet)

        index = await original.spatial_index_async(
            grid=16, max_vertices=1000000, read_page=read_page, write_page=write_page
        )
        scope = await GeoSelectedScope.from_frame_async(original, namespace=U64, layer_id=U64)
        state = await scope.state_async(
            revision=1, ids=np.array([U64], dtype="<u8"), fill=b"\0\xff\0\xff"
        )
        operation = await state.begin_async(index, q, sequence=2, indexed=True)
        await operation.drive_async()
        frame = None
        try:
            bridge.armed = True
            with pytest.raises(OSError, match="asynchronous indexed birth release"):
                await operation.prepare_async(style())
            assert operation._publication_pending
            if cleanup:
                await operation.aclose()
                await operation.aclose()
            else:
                frame = await operation.prepare_async(style())
                await operation.aclose()
                assert frame.data.record(0)["feature_id"] == U64
            assert len(bridge.releases) == 2 and bridge.releases[0] == bridge.releases[1]
            assert operation._mutation._attempt._released
            assert original.data.record(0)["feature_id"] == U64
        finally:
            await operation.aclose()
            if frame is not None:
                await frame.aclose()
            await state.pending_operation.aclose()
            await index.aclose()
            await original.aclose()
            await source.aclose()
            await scope.aclose()

    asyncio.run(asyncio.wait_for(run(), 15))


def test_repeated_waiter_cancellation_and_controller_reentrancy_keep_claim_until_ack():
    async def run():
        source, chart = mounted_chart_fixture()
        widget = chart.widget()
        sent = []
        widget.send = lambda message, buffers=(): sent.append((message, buffers))
        controller = xyg.TemporalController(instance_id=21, domain=(-100, 100))
        stop = controller.subscribe_state(
            lambda state: controller.set_cursor(2) if state["cursor"] == 1 else None
        )
        binding = widget.bind_temporal(controller)
        try:
            assert "error" not in request(widget._adapter, 1, mount="cancel")[0]
            widget._on_geo_message(widget, dict(type="geo_host_ready", mount="cancel"), [])
            await asyncio.sleep(0)
            active = dict(binding._active)
            controller.set_cursor(1)
            assert controller.state["cursor"] == 2
            controller.close()
            closing = asyncio.create_task(binding.aclose())
            await asyncio.sleep(0)
            closing.cancel()
            await asyncio.sleep(0)
            closing.cancel()
            assert source in _BINDINGS
            assert not closing.done()
            widget._on_geo_message(
                widget,
                {
                    **active,
                    "type": "geo_host_temporal_done",
                    "status": "superseded",
                    "drained": True,
                },
                [],
            )
            with pytest.raises(asyncio.CancelledError):
                await closing
            await binding.aclose()
            assert source not in _BINDINGS
        finally:
            stop()
            frame = widget._adapter._frame
            request(widget._adapter, 4, mount="cancel", owner=frame.handle, sequence=1)
            widget.close()
            await widget._geo_rpc_task
            controller.close()
            source.close()

    asyncio.run(asyncio.wait_for(run(), 15))


def _notification_chart_fixture():
    source, chart = chart_fixture()
    layer = chart.layers[0]
    # The generic wire fixture deliberately uses max-u64 revisions. Notification
    # tests need room for actual native snapshot replacements, not exhaustion.
    query = dict(layer.properties["query"], camera_revision=1, time_revision=1)
    chart = replace(
        chart, layers=(replace(layer, properties={**layer.properties, "query": query}),)
    )
    return source, chart


@pytest.mark.parametrize("delivery_failures", [1, 2])
def test_failed_drain_retry_delivery_can_be_retried_until_ack(delivery_failures):
    async def run():
        source, chart = _notification_chart_fixture()
        widget = chart.widget()
        controller = xyg.TemporalController(instance_id=22, domain=(-100, 100))
        operations, tasks = [], []
        failures = delivery_failures

        def send(message, buffers=()):
            nonlocal failures
            if message["type"] == "geo_host_temporal":
                operation = struct.unpack_from("<I", buffers[0], 8)[0]
                operations.append(operation)
                if operation == 4 and failures:
                    failures -= 1
                    raise OSError("drain retry delivery failed")

        widget.send = send
        binding = widget.bind_temporal(controller)
        try:
            assert "error" not in request(widget._adapter, 1, mount="retry-delivery")[0]
            widget._on_geo_message(widget, dict(type="geo_host_ready", mount="retry-delivery"), [])
            await asyncio.sleep(0)
            active = dict(binding._active)
            binding._message({**active, "status": "failed", "drained": False})
            for _ in range(delivery_failures):
                attempt = asyncio.create_task(binding.aclose())
                tasks.append(attempt)
                for _ in range(20):
                    if attempt.done():
                        break
                    await asyncio.sleep(0)
                assert attempt.done(), "failed retry delivery must settle instead of hanging"
                with pytest.raises(OSError, match="drain retry delivery failed"):
                    await attempt
                assert all(
                    binding._active[key] == active[key]
                    for key in ("mount", "request", "generation")
                )
                assert _BINDINGS.get(source) is binding
            retry = asyncio.create_task(binding.aclose())
            tasks.append(retry)
            for _ in range(20):
                if operations.count(4) == delivery_failures + 1:
                    break
                await asyncio.sleep(0)
            assert operations.count(4) == delivery_failures + 1, "cleanup must resend the drain"
            assert not retry.done(), "delivery alone is not drain acknowledgement"
            assert all(
                binding._active[key] == active[key] for key in ("mount", "request", "generation")
            )
            assert _BINDINGS.get(source) is binding
            binding._message({**active, "status": "superseded", "drained": True})
            await retry
            assert source not in _BINDINGS
            await binding.aclose()
            replacement = chart.bind_temporal(controller)
            await replacement.aclose()
        finally:
            if widget._adapter.mounted:
                frame = widget._adapter._frame
                request(
                    widget._adapter,
                    4,
                    mount="retry-delivery",
                    owner=frame.handle,
                    sequence=widget._adapter._sequence,
                )
                widget._geo_mount = None
                binding._released("retry-delivery")
            await asyncio.gather(*tasks, return_exceptions=True)
            await binding.aclose()
            widget.close()
            if widget._geo_rpc_task is not None:
                await widget._geo_rpc_task
            controller.close()
            source.close()

    asyncio.run(asyncio.wait_for(run(), 15))


@pytest.mark.parametrize("binding_kind", ["mounted", "snapshot"])
@pytest.mark.parametrize("mode", ["cursor", "range"])
@pytest.mark.parametrize("owner_supersedes", [False, True])
def test_foreign_thread_burst_has_one_wakeup_and_latest_ordered_intent(
    mode, owner_supersedes, binding_kind
):
    import threading

    async def run():
        source, chart = _notification_chart_fixture()
        widget = chart.widget()
        widget.send = lambda *args, **kwargs: None
        controller = xyg.TemporalController(instance_id=23, domain=(-10000, 10000))
        binding = (
            widget.bind_temporal(controller, mode)
            if binding_kind == "mounted"
            else chart.bind_temporal(controller, mode)
        )
        errors = []

        def mutate(value):
            if mode == "cursor":
                controller.set_cursor(value)
            else:
                controller.set_range(value, value + 1)

        def flood():
            try:
                for value in range(1, 1001):
                    mutate(value)
            except BaseException as error:
                errors.append(error)

        try:
            await asyncio.sleep(0)
            initial_time = binding._time
            thread = threading.Thread(target=flood)
            thread.start()
            # Deliberately keep the owning loop busy during real native updates.
            thread.join(5)
            assert not thread.is_alive()
            assert errors == []
            assert binding._time == initial_time, "foreign ingress must not mutate owner intent"
            callbacks = [
                item
                for item in asyncio.get_running_loop()._ready
                if getattr(item._callback, "__self__", None) is binding
            ]
            if owner_supersedes:
                mutate(2001)
            await asyncio.sleep(0)
            value = 2001 if owner_supersedes else 1000
            if binding_kind == "mounted":
                assert binding._time == (
                    (1, value, 0) if mode == "cursor" else (2, value, value + 1)
                )
                assert binding._active is None  # Premount; no temporal request posted.
            else:
                await binding.when_idle()
                assert binding._time == (
                    dict(kind=1, instant=value)
                    if mode == "cursor"
                    else dict(kind=2, start=value, end=value + 1)
                )
                assert binding.error is None
                _, frame = await binding.snapshot()
                try:
                    assert frame.data.identity["time"] == binding._time
                finally:
                    await frame.aclose()
            assert len(callbacks) <= 1, "foreign updates must retain at most one wakeup"
        finally:
            await binding.aclose()
            widget.close()
            if widget._geo_rpc_task is not None:
                await widget._geo_rpc_task
            controller.close()
            source.close()

    asyncio.run(asyncio.wait_for(run(), 15))


@pytest.mark.parametrize("binding_kind", ["mounted", "snapshot"])
def test_queued_foreign_terminal_state_outranks_late_nonterminal_snapshot(binding_kind):
    import threading

    async def run():
        source, chart = _notification_chart_fixture()
        widget = chart.widget()
        sent, snapshots = [], []
        widget.send = lambda *args, **kwargs: sent.append(args)
        controller = xyg.TemporalController(instance_id=24, domain=(-10000, 10000))
        binding = (
            widget.bind_temporal(controller)
            if binding_kind == "mounted"
            else chart.bind_temporal(controller)
        )

        def close_after_updates():
            for value in range(1, 1001):
                controller.set_cursor(value)
            snapshots.append(controller.state)
            controller.close()

        try:
            await asyncio.sleep(0)
            thread = threading.Thread(target=close_after_updates)
            thread.start()
            thread.join(5)
            assert not thread.is_alive()
            # A previously captured native snapshot may arrive on the owner
            # before the queued foreign terminal notification is dispatched.
            binding._accept(snapshots[0])
            assert binding._closed
            await binding.aclose()
            assert source not in _BINDINGS
            assert sent == []
            binding._accept(snapshots[0])
            assert binding._closed
        finally:
            await binding.aclose()
            widget.close()
            if widget._geo_rpc_task is not None:
                await widget._geo_rpc_task
            controller.close()
            source.close()

    asyncio.run(asyncio.wait_for(run(), 15))


@pytest.mark.parametrize("binding_kind", ["mounted", "snapshot"])
def test_foreign_notification_wakeup_failure_allows_next_update(monkeypatch, binding_kind):
    import threading

    async def run():
        source, chart = _notification_chart_fixture()
        widget = chart.widget()
        widget.send = lambda *args, **kwargs: None
        controller = xyg.TemporalController(instance_id=25, domain=(-100, 100))
        binding = (
            widget.bind_temporal(controller)
            if binding_kind == "mounted"
            else chart.bind_temporal(controller)
        )
        loop = asyncio.get_running_loop()
        enqueue = loop.call_soon_threadsafe
        failures = []

        def enqueue_once(callback, *args, **kwargs):
            if getattr(callback, "__self__", None) is binding and not failures:
                failures.append("delivery failed")
                raise RuntimeError("notification enqueue failed")
            return enqueue(callback, *args, **kwargs)

        def mutate():
            controller.set_cursor(1)
            controller.set_cursor(2)

        try:
            await asyncio.sleep(0)
            monkeypatch.setattr(loop, "call_soon_threadsafe", enqueue_once)
            thread = threading.Thread(target=mutate)
            thread.start()
            thread.join(5)
            assert not thread.is_alive()
            assert failures == ["delivery failed"]
            await asyncio.sleep(0)
            assert binding._time == (
                (1, 2, 0) if binding_kind == "mounted" else dict(kind=1, instant=2)
            )
        finally:
            monkeypatch.setattr(loop, "call_soon_threadsafe", enqueue)
            await binding.aclose()
            widget.close()
            if widget._geo_rpc_task is not None:
                await widget._geo_rpc_task
            controller.close()
            source.close()

    asyncio.run(asyncio.wait_for(run(), 15))


def test_reentrant_drain_ack_survives_retry_delivery_exception():
    async def run():
        source, chart = _notification_chart_fixture()
        widget = chart.widget()
        controller = xyg.TemporalController(instance_id=26, domain=(-100, 100))
        binding = None

        def send(message, buffers=()):
            if (
                message["type"] == "geo_host_temporal"
                and struct.unpack_from("<I", buffers[0], 8)[0] == 4
            ):
                binding._message({**binding._active, "status": "superseded", "drained": True})
                raise OSError("delivery failed after drain acknowledgement")

        widget.send = send
        binding = widget.bind_temporal(controller)
        try:
            assert "error" not in request(widget._adapter, 1, mount="reentrant-drain")[0]
            widget._on_geo_message(widget, dict(type="geo_host_ready", mount="reentrant-drain"), [])
            await asyncio.sleep(0)
            binding._message({**binding._active, "status": "failed", "drained": False})
            with pytest.raises(OSError, match="after drain acknowledgement"):
                await binding.aclose()
            assert binding._active is None
            await binding.aclose()
            assert source not in _BINDINGS
        finally:
            if widget._adapter.mounted:
                frame = widget._adapter._frame
                request(
                    widget._adapter,
                    4,
                    mount="reentrant-drain",
                    owner=frame.handle,
                    sequence=widget._adapter._sequence,
                )
                widget._geo_mount = None
                binding._released("reentrant-drain")
            await binding.aclose()
            widget.close()
            if widget._geo_rpc_task is not None:
                await widget._geo_rpc_task
            controller.close()
            source.close()

    asyncio.run(asyncio.wait_for(run(), 15))


@pytest.mark.parametrize("mode", ["cursor", "range"])
def test_hierarchy_remount_keeps_cancelled_native_query_sequence(mode):
    from test_geo_live_hierarchy_host import fixture
    from test_geo_live_host import ack, live, prepare

    async def run():
        source, scope, lane, caller, chart, previous = fixture()
        previous.close()
        widget = chart.widget(frame=caller, selected_scope=scope, hierarchy_lane=lane)
        adapter = widget._adapter
        sent = []
        widget.send = lambda message, buffers=(): sent.append((message, buffers))
        controller = xyg.TemporalController(instance_id=62, domain=(-100, 100))
        controller.set_cursor(23)
        controller.set_range(23, 24)
        binding = None
        try:
            assert "error" not in request(adapter, 1)[0]
            accepted, sequence, source_sequence = (
                adapter._frame,
                adapter._sequence,
                source._sequence,
            )
            malformed = bytearray(256)
            struct.pack_into(
                "<4sIIIQQ5QI4x2q",
                malformed,
                0,
                b"XYGH",
                2,
                6,
                0,
                accepted.handle,
                sequence,
                1,
                (1 << 64) - 1,
                1,
                1,
                1,
                0,
                0,
                0,
            )
            assert "error" in live(adapter, 6, malformed)[0]
            assert adapter._live_candidate.sequence_floor == sequence
            message, packets = prepare(adapter, nonce=1, sequence=4)
            assert "error" not in message, message
            assert "error" not in live(adapter, 9, ack(9, accepted.handle, sequence, packets[0]))[0]
            assert source._sequence == source_sequence
            assert "error" not in request(adapter, 4, owner=accepted.handle, sequence=sequence)[0]
            assert "error" not in request(adapter, 1)[0]
            assert adapter._frame is accepted
            assert adapter._sequence == sequence
            binding = widget.bind_temporal(controller, mode)
            widget._on_geo_message(widget, dict(type="geo_host_ready", mount="notebook"), [])
            await asyncio.sleep(0)
            message, buffers = sent[-1]
            framing = json.loads(
                (Path(__file__).parent / "fixtures/geo_mounted_temporal.json").read_text()
            )
            key = "hierarchyAfterAbortCursor" if mode == "cursor" else "hierarchyAfterAbortRange"
            assert buffers[0].hex() == framing[key]
            floor = struct.unpack_from("<Q", buffers[0], 32)[0]
            assert floor == 4
            assert floor > adapter._sequence
            widget._on_geo_message(
                widget,
                {
                    **message,
                    "type": "geo_host_temporal_done",
                    "status": "superseded",
                    "drained": True,
                },
                [],
            )
            await binding.aclose()
            # Drive the same authoritative native lane above the advertised
            # floor. These acknowledgements settle real prepared native owners.
            message, packets = prepare(adapter, nonce=1, sequence=floor + 1)
            assert "error" not in message, message
            for operation in (7, 8):
                assert (
                    "error"
                    not in live(
                        adapter,
                        operation,
                        ack(operation, accepted.handle, sequence, packets[0]),
                    )[0]
                )
            assert adapter._frame.data.selection["ids"].tolist() == [(1 << 64) - 1]
        finally:
            # The synthetic control delivery owns no native operation; all
            # actual native preparations above have been aborted or retired.
            if binding is not None:
                if binding._active is not None:
                    active = binding._active
                    widget._on_geo_message(
                        widget,
                        dict(
                            type="geo_host_temporal_done",
                            mount=active["mount"],
                            request=active["request"],
                            status="superseded",
                            drained=True,
                        ),
                        [],
                    )
                await binding.aclose()
            if adapter.mounted:
                request(adapter, 4, owner=adapter._frame.handle, sequence=adapter._sequence)
            widget.close()
            if widget._geo_rpc_task is not None:
                await widget._geo_rpc_task
            caller.close()
            lane.close()
            source.close()
            scope.close()
            controller.close()

    asyncio.run(asyncio.wait_for(run(), 15))
