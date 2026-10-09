"""Geographic lifecycle over real Reflex-configured ASGI/socket.io websocket.

This tests the installed Reflex backend transport, not a full compiled Reflex
frontend. The separate browser proof tests the shared painter.
"""

import struct

import pytest

from reflex_xy.registry import _figure_of, registry
from reflex_xy.tokens import build_state_token
from test_geo_host import chart_fixture
from test_geoscale import U64

from .test_socket_data_plane import CLIENT_TOKEN, Collector, connect_client, data_plane_server, run


def test_geographic_registry_reconnect_and_acknowledged_rebuild(_fresh_registry):
    source, chart = chart_fixture()
    token = build_state_token(CLIENT_TOKEN, "root.geo", "chart")
    adapters = []

    async def rebuild(_):
        facade = _figure_of(chart)
        adapters.append(facade)
        return facade

    async def main():
        async with data_plane_server(rebuild=rebuild) as (url, _):
            client = await connect_client(url)
            collector = Collector(client)
            await client.emit("sub", dict(fig=token, mid="panel"), namespace="/_xy")
            payload = await collector.next(collector.payloads)
            assert payload["spec"] == {"geo_host": True} and payload["buffers"] == []

            async def rpc(op, owner=0, seq=0, extra=b""):
                binary = struct.pack("<4sIIIQQ", b"XYGH", 1, op, 0, owner, seq) + extra
                await client.emit(
                    "msg",
                    dict(
                        fig=token,
                        mid="panel",
                        v=payload["version"],
                        m=dict(
                            type="geo_host", request=f"panel:{op}", mount="panel", buffer=binary
                        ),
                    ),
                    namespace="/_xy",
                )
                message = await collector.next(collector.messages)
                assert message["mid"] == "panel" and message["message"]["type"] == "geo_host"
                assert "error" not in message["message"], message
                return message["buffers"]

            buffers = await rpc(1)
            owner, seq = struct.unpack("<4sIIIQQ", buffers[0])[4:]
            frame = adapters[0]._frame
            assert frame.data.record(0)["feature_id"] == U64
            assert len(buffers) == 3 and isinstance(buffers[1], bytes)
            buffers = None
            with pytest.raises(RuntimeError, match="release mounted"):
                registry.release(token)
            # A transient websocket disconnect cannot certify buffer release.
            await client.disconnect()
            assert adapters[0].mounted and frame.data.record(0)["feature_id"] == U64
            client = await connect_client(url)
            collector = Collector(client)
            await client.emit("sub", dict(fig=token, mid="panel"), namespace="/_xy")
            payload = await collector.next(collector.payloads)
            assert len(adapters) == 1
            hits = await rpc(2, owner, seq, struct.pack("<3dII", 400, 300, 0, 1, 10))
            aux = struct.unpack("<4sIIIQQ", hits[0])[4]
            assert U64 in {
                struct.unpack_from("<Q", hits[1], at + 8)[0] for at in range(256, len(hits[1]), 48)
            }
            hits = None
            await rpc(5, aux, seq)
            await rpc(4, owner, seq)
            assert not adapters[0].mounted
            registry.release(token)
            await client.disconnect()
            # Same authenticated source, a fresh independently leased frame.
            client = await connect_client(url)
            collector = Collector(client)
            await client.emit("sub", dict(fig=token, mid="panel"), namespace="/_xy")
            payload = await collector.next(collector.payloads)
            buffers = await rpc(1)
            next_owner, next_seq = struct.unpack("<4sIIIQQ", buffers[0])[4:]
            assert len(adapters) == 2 and next_owner != owner
            assert adapters[1]._frame.data.record(0)["feature_id"] == U64
            buffers = None
            await rpc(4, next_owner, next_seq)
            await client.disconnect()
            registry.release(token)

    try:
        run(main())
    finally:
        for adapter in adapters:
            adapter.close()
        source.close()


def test_cancelled_geographic_handler_settles_native_thread_and_emit_before_release():
    """Cancellation is not proof that native work or sender buffers stopped."""
    import asyncio
    import threading

    from reflex_xy.namespace import XYNamespace
    from reflex_xy.registry import FigureRegistry
    from test_geo_host import request

    source, chart = chart_fixture()
    facade, replacement = chart.host(), chart.host()
    local = FigureRegistry()
    token = local.register(facade)
    entry = local.get(token)
    reader = source._reader
    entered, release = threading.Event(), threading.Event()

    def gated_reader(ticket):
        entered.set()
        if not release.wait(5):
            raise AssertionError("native reader gate did not settle")
        return reader(ticket)

    source._reader = gated_reader

    async def main():
        namespace = XYNamespace(local)
        emitting, finish_emit = asyncio.Event(), asyncio.Event()
        sent = []

        async def emit(event, envelope, **kwargs):
            assert event == "msg"
            if not envelope["buffers"]:
                assert envelope["message"]["request"] == "ack"
                return
            assert len(envelope["buffers"]) == 3
            emitting.set()
            await finish_emit.wait()
            # Save small framing only; no sender packet persists into its ACK.
            sent.append(struct.unpack("<4sIIIQQ", envelope["buffers"][0])[4:])

        namespace.emit = emit
        raw = struct.pack("<4sIIIQQ", b"XYGH", 1, 1, 0, 0, 0)
        data = dict(
            mid="cancelled", m=dict(type="geo_host", request="open", mount="cancelled", buffer=raw)
        )
        task = asyncio.create_task(namespace._on_geo_message("sid", token, entry, data, 1))
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            for _ in range(2):
                task.cancel()
                await asyncio.sleep(0)
            assert not task.done() and entry.lock.locked() and entry.active_operations == 1
            assert not facade.mounted  # Native open has not finished yet.
            with pytest.raises(RuntimeError, match="registry removal"):
                local.release(token)
            with pytest.raises(RuntimeError, match="registry replacement"):
                local.publish(token, replacement, broadcast=False)
            release.set()
            await asyncio.wait_for(emitting.wait(), 5)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done() and entry.lock.locked() and entry.active_operations == 1
            with pytest.raises(RuntimeError, match="registry removal"):
                local.release(token)
            # A real buffer ACK remains queued until sender publication settles.
            owner, sequence = facade._frame.handle, facade._sequence
            ack = struct.pack("<4sIIIQQ", b"XYGH", 1, 4, 0, owner, sequence)
            ack_data = dict(
                mid="cancelled",
                m=dict(type="geo_host", request="ack", mount="cancelled", buffer=ack),
            )
            acknowledge = asyncio.create_task(
                namespace._on_geo_message("sid", token, entry, ack_data, 1)
            )
            await asyncio.sleep(0)
            assert not acknowledge.done() and facade.mounted
            acknowledge.cancel()  # Also settle cancellation of a queued ACK.

            finish_emit.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            with pytest.raises(asyncio.CancelledError):
                await acknowledge
            assert sent == [(owner, sequence)]
            assert not facade.mounted and not entry.lock.locked() and entry.active_operations == 0
            local.release(token)
        finally:
            release.set()
            finish_emit.set()
            if not task.done():
                await task

    try:
        run(main())
    finally:
        release.set()
        if facade.mounted:
            request(facade, 4, mount="cancelled", owner=facade._frame.handle, sequence=1)
        facade.close()
        replacement.close()
        source.close()


def test_failed_rebuild_cleanup_preserves_inflight_and_mounted_native_owner():
    from reflex_xy.registry import FigureRegistry
    from test_geo_host import request

    source, chart = chart_fixture()
    facade = chart.host()
    local = FigureRegistry()
    token = "xyfig-native-rebuild"
    _, guard = local.begin_rebuild(token)
    entry, inserted = local.publish_if_missing(token, facade, guard=guard)
    assert inserted
    try:
        lease = local._acquire_operation(token)
        assert lease is entry
        assert not local.remove_if_current(token, entry, guard=guard)
        local._release_operation(lease)
        _, packets = request(facade, 1, mount="rebuild")
        owner, sequence = struct.unpack("<4sIIIQQ", packets[0])[4:]
        packets = None
        assert not local.remove_if_current(token, entry, guard=guard)
        assert local.get(token) is entry and facade._frame.data.record(0)["feature_id"] == U64
        request(facade, 4, mount="rebuild", owner=owner, sequence=sequence)
        assert local.remove_if_current(token, entry, guard=guard)
    finally:
        local.finish_rebuild(token, guard)
        facade.close()
        source.close()
