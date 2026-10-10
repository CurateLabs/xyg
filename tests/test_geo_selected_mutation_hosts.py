"""Actual native selected mutation uncertainty; no recreated State or guessed Source cleanup."""

import asyncio
import ctypes
import struct
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from test_geo_retained import fixture_manifest, style
from test_geoscale import BUDGET, U64, query
from xyg import _geoscale as g
from xyg import _native
from xyg._geo_retained import RetainedGeoSource
from xyg._geo_selected import GeoSelectedScope


def test_lost_actual35_keeps_state_claim_and_recovers_same_mutation(monkeypatch):
    manifest, chunk = fixture_manifest()
    source = RetainedGeoSource(manifest, lambda _, chunk=chunk: chunk, budget=BUDGET)
    q = {**query(source.info), "state_revision": 1}
    old = source.update(q, sequence=1, style=style())
    scope = GeoSelectedScope.from_frame(old, namespace=U64, layer_id=U64)
    state = scope.state(revision=2, ids=np.array([U64], dtype="<u8"), fill=bytes([0, 255, 0, 255]))
    actual = _native._lib.xyg_geo_scale_execute
    lost, calls, deleted = True, [], []

    def dispatch(request, length, out, capacity):
        nonlocal lost
        raw = ctypes.string_at(request, length)
        op, handle = struct.unpack_from("<I4xQ", raw, 8)
        if op == 10:
            deleted.append(handle)
        code = actual(request, length, out, capacity)
        if op == 35:
            calls.append(raw)
            if lost:
                lost = False
                assert code == 0
                raise OSError("lost after actual35 mutation")
        return code

    try:
        monkeypatch.setattr(_native._lib, "xyg_geo_scale_execute", dispatch)
        with pytest.raises(OSError):
            state.begin(source, {**q, "state_revision": 2}, sequence=2)
        with pytest.raises(RuntimeError, match=r"active|unsettled|pending"):
            state._check()
        attempt = state.pending_operation
        assert attempt is not None
        operation = attempt.recover()
        assert operation.handle == source.handle
        for name, value in (("handle", old.handle), ("sequence", 1), ("source", old)):
            with pytest.raises(AttributeError):
                setattr(operation, name, value)
        assert len(calls) == 2 and calls[0] == calls[1]
        assert struct.unpack_from("<Q", calls[0], 240)[0] > 0
        operation.drive()
        operation.cancel()
        attempt.close()
        assert source.handle not in deleted
        assert old.data.record(0)["feature_id"] == U64
    finally:
        monkeypatch.setattr(_native._lib, "xyg_geo_scale_execute", actual)
        old.close()
        source.close()
        scope.close()


def test_reentrant_later_native_dispatch_failure_invalidates_prior_success(monkeypatch):
    manifest, chunk = fixture_manifest()
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    q = {**query(source.info), "state_revision": 1}
    old = source.update(q, sequence=1, style=style())
    scope = GeoSelectedScope.from_frame(old, namespace=U64, layer_id=U64)
    state = scope.state(revision=2, ids=np.array([U64], dtype="<u8"), fill=bytes([0, 255, 0, 255]))
    actual = _native._lib.xyg_geo_scale_execute
    depth, armed = 0, True

    def dispatch(request, length, out, capacity):
        nonlocal depth, armed
        raw = ctypes.string_at(request, length)
        code = actual(request, length, out, capacity)
        if struct.unpack_from("<I", raw, 8)[0] == 35 and armed:
            assert code == 0
            if depth:
                raise OSError("later actual replay lost")
            depth += 1
            try:
                with pytest.raises(OSError):
                    g.execute(raw)
            finally:
                depth -= 1
                armed = False
        return code

    try:
        monkeypatch.setattr(_native._lib, "xyg_geo_scale_execute", dispatch)
        with pytest.raises(ValueError, match="genuine native outcome"):
            state.begin(source, {**q, "state_revision": 2}, sequence=2)
        with pytest.raises(RuntimeError, match="active"):
            state._check()
        operation = state.pending_operation.recover()
        operation.cancel()
        state.pending_operation.close()
        assert old.data.record(0)["feature_id"] == U64
    finally:
        monkeypatch.setattr(_native._lib, "xyg_geo_scale_execute", actual)
        old.close()
        source.close()
        scope.close()


def test_forged_fallback_after_actual36_stays_claimed_until_exact_replay():
    async def run():
        manifest, chunk = fixture_manifest()
        native = g.NativeGeoScaleBridge(BUDGET["processor_bytes"])

        class Bridge:
            def __init__(self):
                self.armed = False
                self.requests = []

            async def execute(self, request):
                raw = await native.execute(request)
                if struct.unpack_from("<I", request, 8)[0] == 36:
                    self.requests.append(bytes(request))
                    if self.armed:
                        self.armed = False
                        forged = bytearray(raw)
                        struct.pack_into("<I", forged, 8, 10)
                        forged[16:24] = request[16:24]
                        struct.pack_into("<I", forged, 48, 2)
                        return bytes(forged)
                return raw

            async def read(self, request):
                return await native.read(request)

        bridge = Bridge()

        async def read(_):
            return chunk

        source = await RetainedGeoSource.create_async(manifest, read, budget=BUDGET, bridge=bridge)
        q = {**query(source.info), "state_revision": 1}
        original = await source.aupdate(q, sequence=1, style=style())
        scope = await GeoSelectedScope.from_frame_async(
            original, namespace=U64, layer_id=q["layer_id"]
        )
        pages = {}

        async def read_page(ticket):
            return pages[ticket["page"]]

        async def write_page(ticket, data):
            pages[ticket["page"]] = bytes(data)

        index = await original.spatial_index_async(
            grid=16, max_vertices=1000000, read_page=read_page, write_page=write_page
        )
        state = await scope.state_async(
            revision=2, ids=np.array([U64], dtype="<u8"), fill=bytes([0, 255, 0, 255])
        )
        frame = None
        try:
            bridge.armed = True
            with pytest.raises(ValueError, match="genuine native outcome"):
                await state.begin_async(index, {**q, "state_revision": 2}, sequence=2, indexed=True)
            with pytest.raises(RuntimeError, match="active"):
                state._check()
            attempt = state.pending_operation
            operation = await attempt.recover_async()
            assert len(bridge.requests) == 2 and bridge.requests[0] == bridge.requests[1]
            await operation.drive_async()
            frame = await operation.prepare_async(style())
            assert frame.handle == state.handle and frame.data.selection["ids"].tolist() == [U64]
            await attempt.aclose()  # 36 Query birth retired; must not dispose same-handle Data.
            assert frame.data.record(0)["feature_id"] == U64
        finally:
            if frame is not None:
                await frame.aclose()
            await index.aclose()
            await original.aclose()
            await source.aclose()
            await state.aclose()
            await scope.aclose()

    asyncio.run(run())


def test_two_states_share_original_issuer_nonce_and_scope_cleanup_reclaims_capacity():
    for _ in range(20):
        manifest, chunk = fixture_manifest()
        source = RetainedGeoSource(manifest, lambda _, chunk=chunk: chunk, budget=BUDGET)
        q = {**query(source.info), "state_revision": 1}
        old = source.update(q, sequence=1, style=style())
        scope = GeoSelectedScope.from_frame(old, namespace=U64, layer_id=U64)
        first = scope.state(revision=2, ids=np.array([], dtype="<u8"), fill=bytes([0, 255, 0, 255]))
        second = None
        try:
            op = first.begin(source, {**q, "state_revision": 2}, sequence=2)
            op.cancel()
            second = scope.state(
                revision=3, ids=np.array([U64], dtype="<u8"), fill=bytes([0, 255, 0, 255])
            )
            newer = second.begin(source, {**q, "state_revision": 3}, sequence=3)
            assert struct.unpack_from("<Q", first.pending_operation._attempt._request, 240)[0] == 1
            assert struct.unpack_from("<Q", second.pending_operation._attempt._request, 240)[0] == 2
            newer.cancel()
        finally:
            old.close()
            source.close()
            first.close()
            if second is not None:
                second.close()
            scope.close()


def test_index_disposal_preserves_admitted_selected_query_and_immutable_budget():
    from test_geo_spatial import setup

    source, old, _ = setup()
    q = query(source.info)
    scope = GeoSelectedScope.from_frame(old, namespace=U64, layer_id=q["layer_id"])
    pages = {}
    index = old.spatial_index(
        grid=16,
        max_vertices=1000000,
        read_page=lambda t: pages[t["page"]],
        write_page=lambda t, b: pages.__setitem__(t["page"], bytes(b)),
    )
    state = scope.state(
        revision=U64, ids=np.array([U64], dtype="<u8"), fill=bytes([0, 255, 0, 255])
    )
    frame = None
    try:
        operation = state.begin(index, q, sequence=2, indexed=True)
        index.close()
        index.budget = {**BUDGET, "processor_bytes": 256}
        operation.drive()
        frame = operation.prepare(style())
        assert frame.data.selection["visible_vertices"] == 1
        state.pending_operation.close()
        assert frame.data.record(0)["feature_id"] == U64
    finally:
        if frame is not None:
            frame.close()
        index.close()
        source.close()
        old.close()
        state.close()
        scope.close()


def test_repeated_cancel_keeps_selected_birth_until_reader_and_exact_ack_settle():
    async def run():
        manifest, chunk = fixture_manifest()
        native = g.NativeGeoScaleBridge(BUDGET["processor_bytes"])
        reading, reader_done, acking, ack_done = (asyncio.Event() for _ in range(4))
        gated = False
        releases = 0

        class Bridge:
            async def execute(self, request):
                nonlocal releases
                command = struct.unpack_from("<I", request, 8)[0]
                if gated and command == 8:
                    acking.set()
                    await ack_done.wait()
                if command == 47 and struct.unpack_from("<I", request, 260)[0] == 2:
                    releases += 1
                return await native.execute(request)

            async def read(self, request):
                return await native.read(request)

        bridge = Bridge()

        async def reader(_):
            if gated:
                reading.set()
                await reader_done.wait()
            return chunk

        source = await RetainedGeoSource.create_async(
            manifest, reader, budget=BUDGET, bridge=bridge
        )
        q = {**query(source.info), "state_revision": 1}
        old = await source.aupdate(q, sequence=1, style=style())
        scope = await GeoSelectedScope.from_frame_async(old, namespace=U64, layer_id=U64)
        state = await scope.state_async(
            revision=2, ids=np.array([U64], dtype="<u8"), fill=bytes([0, 255, 0, 255])
        )
        try:
            operation = await state.begin_async(source, {**q, "state_revision": 2}, sequence=2)
            gated = True
            driving = asyncio.create_task(operation.drive_async())
            await reading.wait()
            closing = asyncio.create_task(state.pending_operation.aclose())
            await asyncio.sleep(0)
            closing.cancel()
            await asyncio.sleep(0)
            closing.cancel()
            assert not closing.done() and releases == 0
            reader_done.set()
            await acking.wait()
            assert not closing.done() and releases == 0
            closing.cancel()
            ack_done.set()
            with pytest.raises(asyncio.CancelledError):
                await closing
            with pytest.raises(asyncio.CancelledError):
                await driving
            assert releases == 1
            await state.pending_operation.aclose()
            assert old.data.record(0)["feature_id"] == U64
        finally:
            gated = False
            reader_done.set()
            ack_done.set()
            await old.aclose()
            await source.aclose()
            await state.aclose()
            await scope.aclose()

    asyncio.run(run())


def _selected_ack(issuer, action):
    request = bytearray(
        g.encode_request(
            dict(
                command=6,
                handle=issuer,
                sequence=2,
                payload=struct.pack("<IIQ", 35, action, issuer),
            )
        )
    )
    struct.pack_into("<I", request, 8, 47)
    struct.pack_into("<Q", request, 240, 1)
    return bytes(request)


def _full_receipt_bank():
    held = []
    for _ in range(16):
        manifest, chunk = fixture_manifest()
        source = RetainedGeoSource(manifest, lambda _, chunk=chunk: chunk, budget=BUDGET)
        q = {**query(source.info), "state_revision": 1}
        old = source.update(q, sequence=1, style=style())
        scope = GeoSelectedScope.from_frame(old, namespace=U64, layer_id=U64)
        state = scope.state(
            revision=2, ids=np.array([U64], dtype="<u8"), fill=bytes([0, 255, 0, 255])
        )
        try:
            request = bytearray(
                g.encode_request(
                    dict(
                        command=35,
                        handle=source.handle,
                        sequence=2,
                        query={**q, "state_revision": 2},
                        budget=BUDGET,
                        payload=struct.pack("<Q", state.handle),
                    )
                )
            )
            struct.pack_into("<Q", request, 240, 1)
            g.execute(bytes(request))
            g.execute(_selected_ack(source.handle, 0))
            source._sequence = 2
            source.cancel()
            g.execute(_selected_ack(source.handle, 2))
            held.append(source.handle)
        finally:
            source.close()
            old.close()
            scope.close()
    return held


@pytest.mark.parametrize(
    "dispatch", ["prior-call", "same-call-clone", "new-thread", "nested-capture"]
)
def test_older_genuine_error_cannot_clear_latest_success_even_with_cloned_request(dispatch):
    prior_call = dispatch == "prior-call"

    async def run():
        from xyg._native import GeoNativeError

        held = _full_receipt_bank()
        manifest, chunk = fixture_manifest()
        native = g.NativeGeoScaleBridge(BUDGET["processor_bytes"])
        saved = None
        armed = True

        class Bridge:
            async def execute(self, request):
                nonlocal saved, armed
                if armed and struct.unpack_from("<I", request, 8)[0] == 35:
                    armed = False
                    if not prior_call:
                        try:
                            await native.execute(request)
                        except GeoNativeError as error:
                            assert error.status == -9
                            saved = error
                        assert saved is not None
                        await native.execute(_selected_ack(held.pop(), 1))
                    if dispatch == "new-thread":
                        with ThreadPoolExecutor(max_workers=1) as executor:
                            executor.submit(g.execute, bytes(bytearray(request))).result()
                    elif dispatch == "nested-capture":
                        with g._capture_native_mutation(request):
                            await native.execute(bytes(bytearray(request)))
                    else:
                        await native.execute(bytes(bytearray(request)))
                    raise saved
                return await native.execute(request)

            async def read(self, request):
                return await native.read(request)

        bridge = Bridge()

        async def reader(_):
            return chunk

        source = await RetainedGeoSource.create_async(
            manifest, reader, budget=BUDGET, bridge=bridge
        )
        q = {**query(source.info), "state_revision": 1}
        old = await source.aupdate(q, sequence=1, style=style())
        scope = await GeoSelectedScope.from_frame_async(old, namespace=U64, layer_id=U64)
        state = await scope.state_async(
            revision=2, ids=np.array([U64], dtype="<u8"), fill=bytes([0, 255, 0, 255])
        )
        try:
            if prior_call:
                request = bytearray(
                    g.encode_request(
                        dict(
                            command=35,
                            handle=source.handle,
                            sequence=2,
                            query={**q, "state_revision": 2},
                            budget=BUDGET,
                            payload=struct.pack("<Q", state.handle),
                        )
                    )
                )
                struct.pack_into("<Q", request, 240, 1)
                try:
                    await native.execute(bytes(request))
                except GeoNativeError as error:
                    assert error.status == -9
                    saved = error
                assert saved is not None
                await native.execute(_selected_ack(held.pop(), 1))
            with pytest.raises(GeoNativeError):
                await state.begin_async(source, {**q, "state_revision": 2}, sequence=2)
            with pytest.raises(RuntimeError, match="active"):
                state._check()
            op = await state.pending_operation.recover_async()
            await op.cancel_async()
            await state.pending_operation.aclose()
            assert old.data.record(0)["feature_id"] == U64
        finally:
            await old.aclose()
            await source.aclose()
            await state.aclose()
            await scope.aclose()
            for issuer in held:
                await native.execute(_selected_ack(issuer, 1))

    asyncio.run(run())


def test_async_response_decoration_cannot_rebind_admitted_operation():
    async def run():
        manifest, chunk = fixture_manifest()
        native = g.NativeGeoScaleBridge(BUDGET["processor_bytes"])
        admitted, resume = asyncio.Event(), asyncio.Event()
        armed = False
        reads = 0

        class Bridge:
            async def execute(self, request):
                packet = await native.execute(request)
                if armed and struct.unpack_from("<I", request, 8)[0] == 35:
                    admitted.set()
                    await resume.wait()
                return packet

            async def read(self, request):
                return await native.read(request)

        bridge = Bridge()

        async def reader(_):
            nonlocal reads
            reads += 1
            return chunk

        async def poison(_):
            raise AssertionError("caller decoration redirected admitted operation")

        source = await RetainedGeoSource.create_async(
            manifest, reader, budget=BUDGET, bridge=bridge
        )
        q = {**query(source.info), "state_revision": 1}
        old = await source.aupdate(q, sequence=1, style=style())
        scope = await GeoSelectedScope.from_frame_async(old, namespace=U64, layer_id=U64)
        state = await scope.state_async(
            revision=2, ids=np.array([U64], dtype="<u8"), fill=bytes([0, 255, 0, 255])
        )
        frame = None
        original_execute, original_read = bridge.execute, bridge.read
        try:
            armed = True
            pending = asyncio.create_task(
                state.begin_async(source, {**q, "state_revision": 2}, sequence=2)
            )
            await admitted.wait()
            source.budget = {**BUDGET, "processor_bytes": 256}
            source._reader = source._read_page = source._write_page = poison
            source._bridge = object()
            bridge.execute = bridge.read = poison
            resume.set()
            operation = await pending
            before = reads
            await operation.drive_async()
            assert reads > before
            frame = await operation.prepare_async(style())
            assert frame.data.selection["visible_vertices"] == 1
            await operation.cancel_async()
            await state.pending_operation.aclose()
            assert old.data.record(0)["feature_id"] == U64
        finally:
            resume.set()
            bridge.execute, bridge.read = original_execute, original_read
            source._bridge, source._reader, source.budget = bridge, reader, dict(BUDGET)
            if frame is not None:
                await frame.aclose()
            await old.aclose()
            await source.aclose()
            await state.aclose()
            await scope.aclose()

    asyncio.run(run())
