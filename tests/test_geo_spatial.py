"""Actual native indexed ownership, explicit storage and cancellation release."""

import asyncio
import struct

import pytest

from test_geo_retained import fixture_manifest, style
from test_geoscale import BUDGET, U64, query, source_fixture
from xyg import _geoscale as g
from xyg._geo_retained import RetainedGeoSource
from xyg._geo_spatial import GeoSpatialFullScanRequired, drive_index


def setup(spread=False):
    manifest, chunk = fixture_manifest()
    if spread:
        request = bytearray(source_fixture()[0])
        struct.pack_into("<d", request, 256 + 32 + 64 + 16, 45.0)
        chunk = g.read(bytes(request), BUDGET["processor_bytes"])
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
    frame = source.update(query(source.info), sequence=1, style=style())
    return source, frame, chunk


def test_indexed_native_frame_inside_notebook_loop_and_independent_authority():
    async def notebook():
        source, old, chunk = setup()
        pages = {}
        index = old.spatial_index(
            grid=16,
            max_vertices=1000000,
            read_page=lambda t: pages[t["page"]],
            write_page=lambda t, b: pages.__setitem__(t["page"], bytes(b)),
        )
        canonical = bytearray(old.data.packet)
        canonical[16:32] = bytes(16)
        source.close()
        old.close()
        frame = index.update(query(index.info), sequence=2, style=style())
        try:
            indexed = bytearray(frame.data.packet)
            indexed[16:32] = bytes(16)
            assert indexed == canonical
            assert frame.data.record(0)["feature_id"] == U64
            assert frame.data.record(1)["feature_id"] == (1 << 53) + 1
            assert frame.index_stats["pages_read"] == len(pages)
            assert frame.index_stats["passes"] == 1
            index.close()
            rows = frame.rows()
            assert rows.data.record(0)["feature_id"] == U64
            rows.close()
            hit = frame.pick(style=style(), x=400, y=300, tolerance=0, mode=0, max_hits=4)
            assert hit.data["count"] == 1
            hit.close()
            artifact = frame.export("svg")
            assert b"<svg" in artifact.bytes
            artifact.close()
        finally:
            frame.close()
            index.close()

    asyncio.run(notebook())


def test_failed_index_write_releases_session_and_old_frame_recovers():
    source, frame, chunk = setup()

    def fail(ticket, b):
        assert b.readonly and len(b) == ticket["encoded_bytes"]
        raise OSError("durable storage failed")

    try:
        for _ in range(10):
            with pytest.raises(OSError, match="durable"):
                frame.spatial_index(
                    grid=16, max_vertices=1000000, read_page=lambda _: b"", write_page=fail
                )
        assert source.current is frame and frame.data.record(0)["feature_id"] == U64
        pages = {}
        index = frame.spatial_index(
            grid=16,
            max_vertices=1000000,
            read_page=lambda t: pages[t["page"]],
            write_page=lambda t, b: pages.__setitem__(t["page"], bytes(b)),
        )
        newer = index.update(query(index.info), sequence=2, style=style())
        assert newer.data.record(0)["feature_id"] == U64
        pages_bad = dict(pages)
        index._read_page = lambda t: b"\0" * len(pages_bad[t["page"]])
        with pytest.raises(ValueError):
            index.update(query(index.info), sequence=3, style=style())
        assert index.current is newer
        index._read_page = lambda t: pages[t["page"]]
        recovery = index.update(query(index.info), sequence=4, style=style())
        recovery.close()
        newer.close()
        index.close()
    finally:
        frame.close()
        source.close()


def test_callback_cannot_mutate_authorized_index_read_capacity():
    source, frame, _ = setup()
    pages = {}

    def read(ticket):
        value = pages[ticket["page"]]
        ticket["encoded_bytes"] *= 2
        return value + value

    index = frame.spatial_index(
        grid=16,
        max_vertices=1000000,
        read_page=read,
        write_page=lambda t, b: pages.__setitem__(t["page"], bytes(b)),
    )
    try:
        with pytest.raises(ValueError, match="bounded storage"):
            index.update(query(index.info), sequence=2, style=style())
        assert index.current is None
    finally:
        index.close()
        frame.close()
        source.close()


def test_async_cancel_pending_index_write_settles_before_ack_and_releases():
    async def run():
        source, frame, _ = setup()
        started, release = asyncio.Event(), asyncio.Event()
        writes = []

        async def write(ticket, data):
            writes.append(bytes(data))
            started.set()
            await release.wait()

        task = asyncio.create_task(
            frame.spatial_index_async(
                grid=16, max_vertices=1000000, read_page=lambda _: b"", write_page=write
            )
        )
        await asyncio.wait_for(started.wait(), 5)
        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert source.current is frame and writes
        pages = {}
        index = await frame.spatial_index_async(
            grid=16,
            max_vertices=1000000,
            read_page=lambda t: pages[t["page"]],
            write_page=lambda t, b: pages.__setitem__(t["page"], bytes(b)),
        )
        newer = await index.aupdate(query(index.info), sequence=2, style=style())
        await index.aclose()
        rows = await newer.rows_async()
        assert rows.data.record(0)["feature_id"] == U64
        await rows.aclose()
        await newer.aclose()
        frame.close()
        source.close()

    asyncio.run(run())


def test_full_scan_frontier_is_explicit_and_does_not_advance_or_replace_frame():
    count = 1024
    descriptor = bytearray(64 + count * 16 + count + 7 + count * 8)
    struct.pack_into("<4s5I5Q", descriptor, 0, b"XYGD", 1, 1, 4326, 1, 0, count, count, 0, 0, 0)
    for i in range(count):
        struct.pack_into(
            "<dd", descriptor, 64 + i * 16, -179 + (i % 32) * 358 / 31, -84 + (i // 32) * 168 / 31
        )
    at = 64 + count * 16
    descriptor[at : at + count] = bytes([1]) * count
    id_at = (at + count + 7) // 8 * 8
    for i in range(count):
        struct.pack_into("<Q", descriptor, id_at + i * 8, i)
    descriptor = descriptor[: id_at + count * 8]
    chunk = g.read(
        g.encode_chunk_request(dict(descriptor=descriptor, rows=count), BUDGET["processor_bytes"]),
        BUDGET["processor_bytes"],
    )
    builder = g.decode_reply(g.execute(g.encode_request(dict(command=1))))["handle"]
    try:
        g.execute(g.encode_request(dict(command=2, handle=builder, payload=chunk)))
        g.execute(g.encode_request(dict(command=3, handle=builder, generation=1)))
        manifest = g.read(
            g.encode_request(dict(command=21, handle=builder)), BUDGET["processor_bytes"]
        )
    finally:
        g.execute(g.encode_request(dict(command=10, handle=builder)))
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    q = {**query(source.info), "time": dict(kind=0)}
    frame = source.update(q, sequence=1, style=style())
    pages = {}
    index = frame.spatial_index(
        grid=32,
        max_vertices=1000000,
        read_page=lambda t: pages[t["page"]],
        write_page=lambda t, b: pages.__setitem__(t["page"], bytes(b)),
    )
    try:
        for _ in range(2):
            with pytest.raises(GeoSpatialFullScanRequired):
                index.update(q, sequence=2, style=style())
            assert index.current is None and source.current is frame
    finally:
        index.close()
        frame.close()
        source.close()


def test_sync_driver_acknowledges_failed_write_after_cancellation():
    events = []
    ticket = bytearray(96)
    struct.pack_into("<QQQII", ticket, 0, 17, 42, 1, 0, 3)
    struct.pack_into("<Q", ticket, 56, 64)

    def execute(request):
        command = struct.unpack_from("<I", request, 8)[0]
        events.append(command)
        if command == 6:
            reply = bytearray(256)
            struct.pack_into("<4sII", reply, 0, b"XYGZ", 1, 7)
            struct.pack_into("<QQ", reply, 16, 9, 1)
            reply[64:160] = ticket
            return bytes(reply)
        return b""

    def fail(t, b):
        raise OSError("write")

    with pytest.raises(OSError):
        drive_index(9, 1, BUDGET, lambda _: b"", lambda _: b"", fail, execute, lambda _: bytes(64))
    assert events == [6, 9, 24]


@pytest.mark.parametrize("delayed", ["read", "dispose"])
def test_async_unreturned_indexed_frame_cancelled_during_transport_cleanup(delayed):
    async def run():
        source, frame, _ = setup()
        pages = {}
        index = await frame.spatial_index_async(
            grid=16,
            max_vertices=1000000,
            read_page=lambda t: pages[t["page"]],
            write_page=lambda t, b: pages.__setitem__(t["page"], bytes(b)),
        )
        old = await index.aupdate(query(index.info), sequence=2, style=style())
        original = index._bridge
        started, release = asyncio.Event(), asyncio.Event()
        state = {}

        class Delayed:
            async def execute(self, request):
                command, handle = (
                    struct.unpack_from("<I", request, 8)[0],
                    struct.unpack_from("<Q", request, 16)[0],
                )
                if delayed == "dispose" and command == 10 and handle == state.get("query"):
                    started.set()
                    await release.wait()
                reply = await original.execute(request)
                if command == 18:
                    state["query"] = g.decode_reply(reply)["handle"]
                if command == 19:
                    state["data"] = g.decode_reply(reply)["handle"]
                return reply

            async def read(self, request):
                reply = await original.read(request)
                if delayed == "read" and struct.unpack_from("<I", request, 8)[0] == 23:
                    started.set()
                    await release.wait()
                return reply

        index._bridge = Delayed()
        task = asyncio.create_task(index.aupdate(query(index.info), sequence=3, style=style()))
        await asyncio.wait_for(started.wait(), 5)
        await index.acancel()
        await asyncio.sleep(0.01)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert index.current is old and old.data.record(0)["feature_id"] == U64
        with pytest.raises(ValueError):
            g.read(
                g.encode_request(dict(command=23, handle=state["data"])), BUDGET["processor_bytes"]
            )
        index._bridge = original
        recovery = await index.aupdate(query(index.info), sequence=4, style=style())
        await recovery.aclose()
        await old.aclose()
        await index.aclose()
        frame.close()
        source.close()

    asyncio.run(run())


def test_existing_public_chart_composition_routes_indexed_compile_and_owned_export():
    import xyg

    source, initial, _ = setup()
    pages = {}
    index = initial.spatial_index(
        grid=16,
        max_vertices=1000000,
        read_page=lambda t: pages[t["page"]],
        write_page=lambda t, b: pages.__setitem__(t["page"], bytes(b)),
    )
    q = query(index.info)
    chart = xyg.geo_chart(
        xyg.geo_layer("points", source=index, layer_id=U64, query=q, sequence=2, style=style()),
        camera=q["camera"],
    )
    frame = chart.compile()
    try:
        assert index.current is frame and frame.data.record(0)["feature_id"] == U64
        artifact = chart.to_image("svg", frame=frame)
        assert b"<svg" in artifact.bytes
        artifact.close()
    finally:
        frame.close()
        index.close()
        initial.close()
        source.close()


def test_leaf_work_fallback_is_explicit_and_same_sequence_can_retry():
    source, initial, _ = setup(spread=True)
    pages = {}
    index = initial.spatial_index(
        grid=16,
        max_vertices=1000000,
        read_page=lambda t: pages[t["page"]],
        write_page=lambda t, b: pages.__setitem__(t["page"], bytes(b)),
    )
    try:
        assert len(pages) > 1
        index.budget["max_chunks"] = 1
        with pytest.raises(GeoSpatialFullScanRequired) as error:
            index.update(query(index.info), sequence=2, style=style())
        assert error.value.reason_code == 2 and index.current is None
        index.budget["max_chunks"] = BUDGET["max_chunks"]
        frame = index.update(query(index.info), sequence=2, style=style())
        assert frame.data.record(0)["feature_id"] == U64
        frame.close()
    finally:
        index.close()
        initial.close()
        source.close()
