"""Actual native selected19 replay retains its distinct independent Data birth."""

import asyncio
import ctypes
import struct

import numpy as np
import pytest

from test_geo_retained import fixture_manifest, style
from test_geoscale import BUDGET, U64, query
from xyg import _geoscale as g
from xyg import _native
from xyg._geo_retained import RetainedGeoSource
from xyg._geo_selected import GeoSelectedScope


@pytest.mark.parametrize("fault", ["lost19", "lostconfirm", "lost10", "lostforget", "read23"])
def test_selected_publication_exact_recovery_and_independent_frame(monkeypatch, fault):
    manifest, chunk = fixture_manifest()
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    old = source.update({**query(source.info), "state_revision": 1}, sequence=1, style=style())
    pages = {}
    index = old.spatial_index(
        grid=16,
        max_vertices=1000000,
        read_page=lambda t: pages[t["page"]],
        write_page=lambda t, b: pages.__setitem__(t["page"], bytes(b)),
    )
    scope = GeoSelectedScope.from_frame(old, namespace=U64, layer_id=U64)
    state = scope.state(revision=2, ids=np.array([U64], dtype="<u8"), fill=bytes([0, 255, 0, 255]))
    operation = state.begin(
        index, {**query(index.info), "state_revision": 2}, sequence=2, indexed=True
    )
    operation.drive()
    actual = _native._lib.xyg_geo_scale_execute
    actual_read = _native._lib.xyg_geo_scale_read
    armed, requests, deleted = True, [], []

    def dispatch(request, length, out, capacity):
        nonlocal armed
        raw = ctypes.string_at(request, length)
        command, handle = struct.unpack_from("<I4xQ", raw, 8)
        if command == 19:
            requests.append(raw)
        if command == 10:
            deleted.append(handle)
        code = actual(request, length, out, capacity)
        action = struct.unpack_from("<I", raw, 260)[0] if command == 47 else -1
        if (
            armed
            and code == 0
            and (
                (fault == "lost19" and command == 19)
                or (fault == "lostconfirm" and command == 47 and action == 0)
                or (fault == "lost10" and command == 10 and handle == state.handle)
                or (
                    fault == "lostforget"
                    and command == 47
                    and action == 1
                    and struct.unpack_from("<I", raw, 256)[0] == 19
                )
            )
        ):
            armed = False
            raise OSError("lost " + fault)
        return code

    def read(request, length, budget, out, capacity, returned):
        nonlocal armed
        raw = ctypes.string_at(request, length)
        code = actual_read(request, length, budget, out, capacity, returned)
        if armed and fault == "read23" and struct.unpack_from("<I", raw, 8)[0] == 23 and capacity:
            armed = False
            raise OSError("lost read23")
        return code

    frame = None
    try:
        monkeypatch.setattr(_native._lib, "xyg_geo_scale_execute", dispatch)
        monkeypatch.setattr(_native._lib, "xyg_geo_scale_read", read)
        if fault in ("lost19", "lostconfirm", "read23"):
            with pytest.raises(OSError):
                operation.prepare(style())
            assert operation._publication_pending
            assert state.handle not in deleted
            with pytest.raises(RuntimeError, match="publication remains uncertain"):
                operation.cancel()
        frame = operation.prepare(style())
        assert frame.handle == state.handle
        if fault == "lost19":
            assert len(requests) == 2 and requests[0] == requests[1]
            assert len(requests[0]) == 304 and struct.unpack_from("<Q", requests[0], 240)[0] != 0
        operation.close()
        index.close()
        source.close()
        old.close()
        assert frame.data.record(0)["feature_id"] == U64
        assert frame.data.selection["visible_vertices"] == 1
        rows = frame.rows()
        assert rows.data.record(0)["selected"]
        rows.close()
        if fault == "lost19":
            from test_geo_hierarchy import storage
            from xyg._geo_hierarchy import GeoHierarchy

            hierarchy = GeoHierarchy.from_selected_frame(frame, index, **storage({}))
            hierarchy.close()
            retained = frame.retain()
            artifact = frame.export("svg")
            assert b"XYSE" in bytes(artifact.snapshot)
            artifact.close()
            frame.close()
            assert retained.data.selection["visible_vertices"] == 1
            retained.close()
        if fault == "lostforget":
            with pytest.raises(OSError):
                frame.close()
        frame.close()
        with pytest.raises(RuntimeError, match="disposed"):
            _ = frame.data
        assert source.handle not in deleted[:-1] or source._closed
    finally:
        monkeypatch.setattr(_native._lib, "xyg_geo_scale_execute", actual)
        monkeypatch.setattr(_native._lib, "xyg_geo_scale_read", actual_read)
        if frame is not None:
            frame.close()
        elif operation._publication_pending:
            operation.close()
        index.close()
        old.close()
        source.close()
        scope.close()


def test_async_repeated_cancel_and_close_hold_known_data_until_read_settles():
    async def run():
        manifest, chunk = fixture_manifest()
        native = g.NativeGeoScaleBridge(BUDGET["processor_bytes"])
        gate, entered = asyncio.Event(), asyncio.Event()

        class Bridge:
            def __init__(self):
                self.target = None
                self.deleted = []

            async def execute(self, request):
                command, handle = struct.unpack_from("<I4xQ", request, 8)
                reply = await native.execute(request)
                if command == 19:
                    self.target = g.decode_reply(reply)["handle"]
                if command == 10:
                    self.deleted.append(handle)
                return reply

            async def read(self, request):
                reply = await native.read(request)
                if (
                    struct.unpack_from("<I", request, 8)[0] == 23
                    and struct.unpack_from("<Q", request, 16)[0] == self.target
                ):
                    entered.set()
                    await gate.wait()
                return reply

        bridge = Bridge()

        async def reader(_):
            return chunk

        source = await RetainedGeoSource.create_async(
            manifest, reader, budget=BUDGET, bridge=bridge
        )
        q = {**query(source.info), "state_revision": 1}
        old = await source.aupdate(q, sequence=1, style=style())
        pages = {}

        async def read_page(t):
            return pages[t["page"]]

        async def write_page(t, b):
            pages[t["page"]] = bytes(b)

        index = await old.spatial_index_async(
            grid=16, max_vertices=1000000, read_page=read_page, write_page=write_page
        )
        scope = await GeoSelectedScope.from_frame_async(old, namespace=U64, layer_id=U64)
        state = await scope.state_async(
            revision=2, ids=np.array([U64], dtype="<u8"), fill=b"\0\xff\0\xff"
        )
        operation = await state.begin_async(
            index, {**q, "state_revision": 2}, sequence=2, indexed=True
        )
        await operation.drive_async()
        task = asyncio.create_task(operation.prepare_async(style()))
        try:
            await entered.wait()
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            closing = asyncio.create_task(operation.aclose())
            await asyncio.sleep(0)
            assert not task.done() and not closing.done()
            assert bridge.target not in bridge.deleted
            gate.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            await closing
            assert bridge.target in bridge.deleted
            assert source.handle not in bridge.deleted
            assert not operation._publication_pending
            await state.pending_operation.aclose()
            assert old.data.record(0)["feature_id"] == U64
        finally:
            gate.set()
            if not task.done():
                await asyncio.gather(task, return_exceptions=True)
            await operation.aclose()
            await index.aclose()
            await old.aclose()
            await source.aclose()
            await scope.aclose()

    asyncio.run(run())


def test_twenty_publications_and_canonical_authority_survive_public_context_edits():
    manifest, chunk = fixture_manifest()
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    q = {**query(source.info), "state_revision": 1}
    old = source.update(q, sequence=1, style=style())
    pages = {}
    index = old.spatial_index(
        grid=16,
        max_vertices=1000000,
        read_page=lambda t: pages[t["page"]],
        write_page=lambda t, b: pages.__setitem__(t["page"], bytes(b)),
    )
    scope = GeoSelectedScope.from_frame(old, namespace=U64, layer_id=U64)
    try:
        for sequence in range(2, 22):
            state = scope.state(revision=2, ids=np.array([U64], dtype="<u8"), fill=b"\0\xff\0\xff")
            operation = state.begin(
                index, {**q, "state_revision": 2}, sequence=sequence, indexed=True
            )
            operation.drive()
            saved = index.budget
            index.budget = {"processor_bytes": 256}
            try:
                frame = operation.prepare(style())
            finally:
                index.budget = saved
            assert frame.data.selection["visible_vertices"] == 1
            frame.close()
            state.pending_operation.close()
        assert old.data.record(0)["feature_id"] == U64
    finally:
        index.close()
        old.close()
        source.close()
        scope.close()


@pytest.mark.parametrize("hook_failure", [False, True])
def test_published_frame_close_coalesces_hooks_and_settles_repeated_cancellation(hook_failure):
    async def run():
        from xyg._geo_retained import _owned_data_identity

        manifest, chunk = fixture_manifest()
        bridge = g.NativeGeoScaleBridge(BUDGET["processor_bytes"])

        async def reader(_):
            return chunk

        source = await RetainedGeoSource.create_async(
            manifest, reader, budget=BUDGET, bridge=bridge
        )
        q = {**query(source.info), "state_revision": 1}
        old = await source.aupdate(q, sequence=1, style=style())
        pages = {}

        async def read_page(ticket):
            return pages[ticket["page"]]

        async def write_page(ticket, payload):
            pages[ticket["page"]] = bytes(payload)

        index = await old.spatial_index_async(
            grid=16, max_vertices=1000000, read_page=read_page, write_page=write_page
        )
        scope = await GeoSelectedScope.from_frame_async(old, namespace=U64, layer_id=U64)
        state = await scope.state_async(
            revision=2, ids=np.array([U64], dtype="<u8"), fill=b"\0\xff\0\xff"
        )
        operation = await state.begin_async(
            index, {**q, "state_revision": 2}, sequence=2, indexed=True
        )
        await operation.drive_async()
        frame = await operation.prepare_async(style())
        gate, entered = asyncio.Event(), asyncio.Event()
        calls = 0

        async def hook():
            nonlocal calls
            calls += 1
            entered.set()
            await gate.wait()
            if hook_failure and calls == 1:
                raise OSError("retry hook")

        _owned_data_identity(frame).hooks.append((lambda: None, hook))
        first, second = None, None
        try:
            first = asyncio.create_task(frame.aclose())
            await entered.wait()
            second = asyncio.create_task(frame.aclose())
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert calls == 1
            if hook_failure:
                gate.set()
                for task in (first, second):
                    with pytest.raises(OSError, match="retry hook"):
                        await task
                assert not frame._closed and calls == 1
                await frame.aclose()
                assert calls == 2
            else:
                first.cancel()
                second.cancel()
                await asyncio.sleep(0)
                first.cancel()
                second.cancel()
                await asyncio.sleep(0)
                assert not first.done() and not second.done()
                assert not frame._closed
                gate.set()
                for task in (first, second):
                    with pytest.raises(asyncio.CancelledError):
                        await task
                assert calls == 1
            assert frame._closed and not _owned_data_identity(frame).hooks
            await frame.aclose()
            assert calls == (2 if hook_failure else 1)
        finally:
            gate.set()
            await asyncio.gather(
                *(task for task in (first, second) if task), return_exceptions=True
            )
            await frame.aclose()
            await state.pending_operation.aclose()
            await index.aclose()
            await old.aclose()
            await source.aclose()
            await scope.aclose()

    asyncio.run(run())
