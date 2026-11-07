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


def mounted_chart_fixture():
    """Same canonical IDs with a finite end for visible half-open host checks."""
    import numpy as np

    from test_geo_retained import style
    from test_geoscale import BUDGET, I64, U64, query, source_fixture
    from xyg import _geoscale as g

    original, _ = source_fixture()
    chunk = g.read(
        g.encode_chunk_request(
            dict(
                descriptor=original[288:408],
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
