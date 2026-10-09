"""Actual native private hierarchy tickets and independent retained frames."""

import asyncio

import pytest

from test_geo_retained import style
from test_geo_spatial import setup
from test_geoscale import U64, query
from xyg._geo_hierarchy import GeoHierarchy, is_hierarchy_frame


def storage(pages, **extra):
    return dict(
        grid=1024,
        max_vertices=1000000,
        max_write_bytes=64 << 20,
        read_page=lambda t: pages[(t["namespace"], t["page"])],
        write_page=lambda t, b: pages.__setitem__((t["namespace"], t["page"]), bytes(b)),
        **extra,
    )


def test_frame_exact_scene_disposal_independent_rows_pick_and_retain():
    source, old, _ = setup()
    index = frame = retained = None
    try:
        index = GeoHierarchy.from_frame(old, source, **storage({}))
        source.close()
        frame = index.update(query(index.info), sequence=2, style=style())
        assert frame.data.scene == old.data.scene
        assert frame.data.record(0)["feature_id"] == U64
        assert frame._source is source
        assert is_hierarchy_frame(frame)
        assert not is_hierarchy_frame(old)
        assert frame.hierarchy_stats["passes"] == 1
        retained = frame.retain()
        assert is_hierarchy_frame(retained)
        index.close()
        frame.close()
        rows = retained.rows()
        assert rows.data.record(0)["feature_id"] == U64
        rows.close()
        hit = retained.pick(style=style(), x=400, y=300, tolerance=0, mode=0, max_hits=4)
        assert hit.data["count"] == 1
        hit.close()
    finally:
        if retained:
            retained.close()
        if frame:
            frame.close()
        if index:
            index.close()
        old.close()
        source.close()


def test_callback_mutation_and_backing_budget_preserve_old_frame():
    source, old, _ = setup()
    pages = {}
    options = storage(pages)

    def write(t, b):
        t["raw"] = b"\0" * 128
        t["namespace"] = 0
        t["encoded_bytes"] *= 2
        raise OSError("storage failed")

    options["write_page"] = write
    try:
        with pytest.raises(OSError, match="storage failed"):
            GeoHierarchy.from_frame(old, source, **options)
        assert old.data.record(0)["feature_id"] == U64
        index = GeoHierarchy.from_frame(old, source, **storage(pages))
        try:
            frame = index.update(query(index.info), sequence=2, style=style())
            frame.close()
        finally:
            index.close()
    finally:
        old.close()
        source.close()


def test_async_cancel_write_settles_before_exact_ack():
    async def run():
        source, old, _ = setup()
        entered, release = asyncio.Event(), asyncio.Event()

        async def write(t, b):
            entered.set()
            await release.wait()

        options = storage({})
        options["write_page"] = write
        pending = asyncio.create_task(GeoHierarchy.from_frame_async(old, source, **options))
        try:
            await entered.wait()
            pending.cancel()
            await asyncio.sleep(0.01)
            assert not pending.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await pending
            assert old.data.record(0)["feature_id"] == U64
        finally:
            release.set()
            old.close()
            source.close()

    asyncio.run(run())


def test_explicit_static_host_mount_retains_authentic_hierarchy_frame():
    import struct

    import xyg
    from test_geo_host import request

    source, old, _ = setup()
    index = GeoHierarchy.from_frame(old, source, **storage({}))
    q = query(index.info)
    frame = index.update(q, sequence=2, style=style())
    chart = xyg.geo_chart(
        xyg.geo_layer("points", source=source, layer_id=U64, query=q, sequence=2, style=style()),
        camera=q["camera"],
    )
    adapter = chart.host(frame=frame)
    try:
        assert is_hierarchy_frame(adapter._anchor)
        frame.close()
        index.close()
        source.close()
        message, buffers = request(adapter, 1)
        assert "error" not in message
        owner, sequence = struct.unpack("<4sIIIQQ", buffers[0])[4:]
        assert adapter._frame.data.record(0)["feature_id"] == U64
        # Static host has no hierarchy-aware live route: unknown update fails closed.
        assert request(adapter, 6, owner=owner, sequence=sequence)[0]["error"]
        buffers = None
        assert "error" not in request(adapter, 4, owner=owner, sequence=sequence)[0]
    finally:
        adapter.close()
        frame.close()
        index.close()
        old.close()
        source.close()


def test_async_frame_retained_clone_marks_exact_provenance_after_owner_disposal():
    async def run():
        source, old, _ = setup()
        index = await GeoHierarchy.from_frame_async(old, source, **storage({}))
        frame = retained = None
        try:
            frame = await index.aupdate(query(index.info), sequence=2, style=style())
            retained = await frame.retain_async()
            assert is_hierarchy_frame(frame)
            assert is_hierarchy_frame(retained)
            await index.aclose()
            await frame.aclose()
            source.close()
            rows = retained.rows()
            assert rows.data.record(0)["feature_id"] == U64
            rows.close()
        finally:
            if retained:
                await retained.aclose()
            if frame:
                await frame.aclose()
            await index.aclose()
            old.close()
            source.close()

    asyncio.run(run())


@pytest.mark.parametrize("multi", [False, True])
def test_reduced_exact_membership_nulls_empty_geometry_and_duplicate_ids(multi):
    import struct

    from test_geoscale import BUDGET
    from xyg import _geoscale as g
    from xyg._geo_retained import RetainedGeoSource

    accepted = 16385 if multi else 32769
    rows, vertices = accepted + 2, accepted * (2 if multi else 1)
    validity = (rows + 7) & ~7
    offsets = (((rows + 1) * 4 + 7) & ~7) if multi else 0
    descriptor = bytearray(64 + vertices * 16 + validity + rows * 8 + offsets)
    struct.pack_into(
        "<4s5I5Q",
        descriptor,
        0,
        b"XYGD",
        1,
        4 if multi else 1,
        4326,
        1,
        0,
        rows,
        vertices,
        rows + 1 if multi else 0,
        0,
        0,
    )
    descriptor[64 + vertices * 16 : 64 + vertices * 16 + accepted + int(multi)] = b"\1" * (
        accepted + int(multi)
    )
    ids = 64 + vertices * 16 + validity
    for i in range(rows):
        struct.pack_into("<Q", descriptor, ids + i * 8, U64 - i if i % 7 else U64)
    if multi:
        for i in range(rows + 1):
            struct.pack_into("<I", descriptor, ids + rows * 8 + i * 4, min(i, accepted) * 2)
    chunk = g.read(
        g.encode_chunk_request(dict(descriptor=descriptor, rows=rows), BUDGET["processor_bytes"]),
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
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    q = dict(query(source.info), time=dict(kind=0), max_cells=1)
    old = source.update(q, sequence=1, style=style())
    index = frame = None
    try:
        index = GeoHierarchy.from_frame(old, source, **storage({}))
        frame = index.update(q, sequence=2, style=style())
        assert frame.data.scene == old.data.scene
        assert frame.hierarchy_stats["passes"] == 2
        source.close()
        index.close()
        old.close()
        cursor, total = None, 0
        while True:
            page = frame.membership(0, max_projected_vertices=1000000, cursor=cursor)
            try:
                data = page.data
                for i in range(data["count"]):
                    feature_id, source_row = struct.unpack_from("<QQ", data["records"], i * 32)
                    assert source_row == total + i
                    assert feature_id == (U64 - total - i if (total + i) % 7 else U64)
                total += data["count"]
                cursor = data["cursor"]
            finally:
                page.close()
            if cursor is None:
                break
        assert total == accepted
    finally:
        if frame:
            frame.close()
        if index:
            index.close()
        old.close()
        source.close()


def test_authentic_selected_frame_rejects_before_index_admission():
    import struct

    from xyg import _geoscale as g
    from xyg._geo_hierarchy import GeoHierarchyUnsupportedSelected
    from xyg._geo_retained import _attach_frame

    def extension(command, handle, sequence=0, payload=b"", q=None):
        fields = dict(
            command=5 if q is not None else 6,
            handle=handle,
            sequence=sequence,
            payload=payload,
            budget=source.budget,
        )
        if q is not None:
            fields["query"] = q
        request = bytearray(g.encode_request(fields))
        struct.pack_into("<I", request, 8, command)
        return bytes(request)

    source, old, _ = setup()
    scope = selected = state = None
    try:
        scope = g.decode_reply(
            g.execute(extension(32, old.handle, 1, struct.pack("<QQ", 777, U64)))
        )["handle"]
        state = g.decode_reply(
            g.execute(
                extension(33, scope, 0, struct.pack("<Q4sIQQ", U64, b"\0\xff\0\xff", 0, 1, U64))
            )
        )["handle"]
        q = dict(query(source.info), state_revision=U64)
        g.execute(extension(35, source.handle, 2, struct.pack("<Q", state), q))
        state = None
        source._drive(2, 4)
        selected = source._prepare(11, source.handle, 2, style())
        _attach_frame(source, selected, 2, extension(35, source.handle, 2, b"", q), style())
        assert selected.data.selection is not None
        with pytest.raises(GeoHierarchyUnsupportedSelected):
            GeoHierarchy.from_frame(selected, source, **storage({}))
        assert old.data.record(0)["feature_id"] == U64
        assert not is_hierarchy_frame(selected)
    finally:
        if selected:
            selected.close()
        source.close()
        if state:
            g.execute(g.encode_request(dict(command=10, handle=state)))
        if scope:
            g.execute(g.encode_request(dict(command=10, handle=scope)))
        old.close()


def test_async_cancelled_canonical_read_settles_private_ticket_before_ack():
    async def run():
        source, old, _ = setup()
        original = source._reader
        entered, release = asyncio.Event(), asyncio.Event()

        async def reader(ticket):
            entered.set()
            await release.wait()
            ticket["raw"] = bytes(128)
            ticket["encoded_bytes"] *= 2
            return original(ticket)

        source._reader = reader
        pending = asyncio.create_task(GeoHierarchy.from_frame_async(old, source, **storage({})))
        try:
            await entered.wait()
            pending.cancel()
            await asyncio.sleep(0.01)
            assert not pending.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await pending
            assert old.data.record(0)["feature_id"] == U64
        finally:
            release.set()
            source._reader = original
            old.close()
            source.close()

    asyncio.run(run())


def test_private_source_provenance_rejects_foreign_source_without_transport(monkeypatch):
    from xyg import _geoscale as g

    source, old, _ = setup()
    other, frame, _ = setup(True)
    try:
        old._source = other

        def forbidden(_):
            raise AssertionError("foreign frame must reject before native dispatch")

        with monkeypatch.context() as patch:
            patch.setattr(g, "execute", forbidden)
            with pytest.raises(ValueError, match="another source or transport"):
                GeoHierarchy.from_frame(old, other, **storage({}))
        assert old.data.record(0)["feature_id"] == U64
    finally:
        old.close()
        frame.close()
        source.close()
        other.close()


def test_private_provenance_registry_does_not_pin_source_frame_cycle():
    import gc
    import weakref

    source, frame, _ = setup()
    refs = weakref.ref(source), weakref.ref(frame)
    source.close()
    frame.close()
    del source, frame
    gc.collect()
    assert all(ref() is None for ref in refs)


def test_async_owner_and_frame_disposal_failures_retry_after_settlement():
    from xyg import _geoscale as g

    async def run():
        source, old, _ = setup()
        native = g.NativeGeoScaleBridge(source.budget["processor_bytes"])

        class Bridge:
            target = None
            failed = False

            async def execute(self, request):
                import struct

                if (
                    struct.unpack_from("<I", request, 8)[0] == 10
                    and struct.unpack_from("<Q", request, 16)[0] == self.target
                    and not self.failed
                ):
                    self.failed = True
                    raise OSError("pre-Rust cleanup failure")
                return await native.execute(request)

            async def read(self, request):
                return await native.read(request)

        # Producer transport is registered by the actual canonical async owner.
        from test_geo_retained import fixture_manifest
        from xyg._geo_retained import RetainedGeoSource

        manifest, chunk = fixture_manifest()
        bridge = Bridge()

        async def read_chunk(_):
            return chunk

        asynchronous = await RetainedGeoSource.create_async(
            manifest, read_chunk, budget=source.budget, bridge=bridge
        )
        initial = await asynchronous.aupdate(query(asynchronous.info), sequence=1, style=style())
        index = frame = None
        try:
            index = await GeoHierarchy.from_frame_async(initial, asynchronous, **storage({}))
            frame = await index.aupdate(query(index.info), sequence=2, style=style())
            bridge.target = frame.handle
            with pytest.raises(OSError, match="cleanup failure"):
                await frame.aclose()
            with pytest.raises(RuntimeError, match="disposed"):
                _ = frame.data
            await frame.aclose()
            bridge.target, bridge.failed = index.handle, False
            with pytest.raises(OSError, match="cleanup failure"):
                await index.aclose()
            await index.aclose()
            assert index._closed
            assert old.data.record(0)["feature_id"] == U64
        finally:
            bridge.failed = True
            if frame:
                await frame.aclose()
            if index:
                await index.aclose()
            await initial.aclose()
            await asynchronous.aclose()
            old.close()
            source.close()

    asyncio.run(run())
