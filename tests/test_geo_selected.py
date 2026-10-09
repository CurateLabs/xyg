"""Real native selected authority and borrowed v2 intent, including original rows."""

import asyncio

import numpy as np
import pytest

from test_geo_retained import fixture_manifest, style
from test_geoscale import BUDGET, U64, query
from xyg import _geoscale as g
from xyg._geo_retained import RetainedGeoSource
from xyg._geo_selected import GeoSelectedScope
from xyg._native import GeoNativeError


def test_native_selected_frame_retains_full_intent_and_rows_after_source_disposal():
    manifest, chunk = fixture_manifest()
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    q = {**query(source.info), "state_revision": 1}
    original = source.update(q, sequence=1, style=style())
    scope = GeoSelectedScope.from_frame(original, namespace=U64, layer_id=q["layer_id"])
    state = scope.state(
        revision=2, ids=np.array([U64, U64], dtype="<u8"), fill=bytes([0, 255, 0, 255])
    )
    frame = None
    try:
        operation = state.begin(source, {**q, "state_revision": 2}, sequence=2)
        with pytest.raises(RuntimeError, match="unavailable"):
            state.begin(source, q, sequence=3)
        operation.drive()
        frame = operation.prepare(style())
        assert frame.data.selection["ids"].tolist() == [U64]
        assert frame.data.selection["namespace"] == U64
        assert frame.data.selection["visible_vertices"] == 1
        assert frame.data.selection["raw"].obj is frame.data.packet.obj
        with pytest.raises(ValueError):
            bad = bytearray(frame.data.packet)
            bad[-72] ^= 1  # Full source digest binding, not merely fingerprint.
            g.SceneData(bad)
        original.close()
        source.close()
        page = frame.rows()
        try:
            assert page.data.selection["ids"].tolist() == [U64]
            assert page.data.record(0)["selected"]
        finally:
            page.close()
        artifact = frame.export("svg")
        try:
            assert bytes(artifact.snapshot[:8]) == b"XYGX\x03\0\0\0"
            assert b"XYSE" in bytes(artifact.snapshot)
            assert bytes(artifact.bytes).startswith(b"<svg")
        finally:
            artifact.close()
        with pytest.raises(GeoNativeError):
            scope.close()  # Live immutable selected frame still owns scope.
    finally:
        if frame is not None:
            frame.close()
        original.close()
        source.close()
        state.close()
        scope.close()


def test_actual_async_native_selected_rows_and_retry_release_in_notebook_loop():
    async def run():
        manifest, chunk = fixture_manifest()
        raw = g.NativeGeoScaleBridge(BUDGET["processor_bytes"])

        class Bridge:
            armed = False
            attempts = 0

            async def execute(self, request):
                if self.armed and int.from_bytes(request[8:12], "little") == 10:
                    self.attempts += 1
                    if self.attempts == 1:
                        raise RuntimeError("transient release")
                return await raw.execute(request)

            async def read(self, request):
                return await raw.read(request)

        bridge = Bridge()

        async def read(_):
            return chunk

        source = await RetainedGeoSource.create_async(manifest, read, budget=BUDGET, bridge=bridge)
        q = {**query(source.info), "state_revision": 1}
        original = await source.aupdate(q, sequence=1, style=style())
        scope = await GeoSelectedScope.from_frame_async(
            original, namespace=U64, layer_id=q["layer_id"]
        )
        state = await scope.state_async(
            revision=2, ids=np.array([U64], dtype="<u8"), fill=bytes([0, 255, 0, 255])
        )
        frame = None
        try:
            operation = await state.begin_async(source, {**q, "state_revision": 2}, sequence=2)
            await operation.drive_async()
            frame = await operation.prepare_async(style())
            assert frame.data.selection["ids"].tolist() == [U64]
            page = await frame.rows_async()
            assert page.data.record(0)["selected"]
            await page.aclose()
            bridge.armed = True
            with pytest.raises(RuntimeError, match="transient"):
                await frame.aclose()
            with pytest.raises(RuntimeError, match="disposed"):
                _ = frame.data
            await frame.aclose()
            assert bridge.attempts == 2
            bridge.armed = False
            with pytest.raises(GeoNativeError):
                await raw.read(g.encode_request(dict(command=23, handle=frame.handle)))
        finally:
            bridge.armed = False
            if frame is not None:
                await frame.aclose()
            await original.aclose()
            await source.aclose()
            await state.aclose()
            await scope.aclose()

    asyncio.run(run())


def test_native_selected_index_query_replaces_owner_and_preserves_explicit_scope():
    from test_geo_spatial import setup

    source, original, _ = setup(spread=True)
    q = query(source.info)
    scope = GeoSelectedScope.from_frame(original, namespace=11, layer_id=q["layer_id"])
    pages = {}
    index = original.spatial_index(
        grid=16,
        max_vertices=1000000,
        read_page=lambda ticket: pages[ticket["page"]],
        write_page=lambda ticket, data: pages.__setitem__(ticket["page"], bytes(data)),
    )
    state = scope.state(
        revision=U64, ids=np.array([U64], dtype="<u8"), fill=bytes([0, 255, 0, 255])
    )
    frame = None
    try:
        original_budget = index.budget
        index.budget = {**original_budget, "max_chunks": 1}
        fallback = state.begin(index, {**q, "state_revision": U64}, sequence=2, indexed=True)
        assert fallback["fallback"] and fallback["reason"] == 2
        assert fallback["state"] is state
        index.budget = original_budget
        operation = state.begin(index, {**q, "state_revision": U64}, sequence=2, indexed=True)
        operation.drive()
        frame = operation.prepare(style())
        assert frame.handle == state.handle
        assert frame.data.selection["visible_vertices"] == 1
        index.close()
        original.close()
        source.close()
        page = frame.rows()
        assert page.data.record(0)["selected"]
        page.close()
        operation.close()  # Replaced query cannot dispose its independent frame.
        assert frame.data.record(0)["feature_id"] == U64
    finally:
        if frame is not None:
            frame.close()
        state.close()
        index.close()
        original.close()
        source.close()
        scope.close()


def test_sync_reader_cannot_expand_private_ticket_or_replace_release_authority(monkeypatch):
    manifest, chunk = fixture_manifest()
    attacking = False

    def reader(ticket):
        if attacking:
            ticket["encoded_bytes"] *= 2
            ticket["raw"] = memoryview(bytes(96))
            return chunk + chunk
        return chunk

    source = RetainedGeoSource(manifest, reader, budget=BUDGET)
    q = {**query(source.info), "state_revision": 1}
    original = source.update(q, sequence=1, style=style())
    scope = GeoSelectedScope.from_frame(original, namespace=33, layer_id=q["layer_id"])
    state = scope.state(revision=2, ids=np.array([U64], dtype="<u8"), fill=bytes([0, 255, 0, 255]))
    execute = g.execute
    commands = []

    def observed(request):
        commands.append(int.from_bytes(request[8:12], "little"))
        return execute(request)

    monkeypatch.setattr(g, "execute", observed)
    frame = None
    try:
        operation = state.begin(source, {**q, "state_revision": 2}, sequence=2)
        commands.clear()
        attacking = True
        with pytest.raises(ValueError, match="exact owning"):
            operation.drive()
        assert 7 not in commands and commands.count(8) == 1
        assert source.current is original
        assert original.data.record(0)["feature_id"] == U64
        attacking = False
        retry = scope.state(
            revision=2, ids=np.array([U64], dtype="<u8"), fill=bytes([0, 255, 0, 255])
        )
        operation = retry.begin(source, {**q, "state_revision": 2}, sequence=3)
        operation.drive()
        frame = operation.prepare(style())
        assert frame.data.selection["visible_vertices"] == 1
        retry.close()
    finally:
        if frame is not None:
            frame.close()
        original.close()
        source.close()
        state.close()
        scope.close()


def test_full_original_rows_selection_includes_null_offscreen_and_time_excluded_intent():
    from test_geo_rows import row_query, rows_fixture

    manifest, chunk = rows_fixture()
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    q = {**row_query(source.info), "state_revision": 1}
    original = source.update(q, sequence=1, style=style())
    scope = GeoSelectedScope.from_frame(original, namespace=55, layer_id=q["layer_id"])
    state = scope.state(
        revision=2, ids=np.array([1 << 63, U64, 7], dtype="<u8"), fill=bytes([0, 255, 0, 255])
    )
    frame = None
    try:
        operation = state.begin(source, {**q, "state_revision": 2}, sequence=2)
        operation.drive()
        frame = operation.prepare(style())
        assert frame.data.selection["visible_vertices"] == 0
        original.close()
        source.close()
        page = frame.rows()
        try:
            assert [page.data.record(i)["selected"] for i in range(5)] == [
                True,
                True,
                True,
                True,
                False,
            ]
            assert not page.data.record(0)["time_eligible"]
            assert page.data.record(2)["geometry_null"]
            bad = bytearray(page.data.packet)
            bad[256 + 24] ^= 128
            from xyg._geo_retained import GeoRowsData

            with pytest.raises(ValueError, match="intent mismatch"):
                GeoRowsData(bad, int.from_bytes(page.data.packet[16:24], "little"), 2)
        finally:
            page.close()
    finally:
        if frame is not None:
            frame.close()
        original.close()
        source.close()
        state.close()
        scope.close()


def test_ordinary_scene_lease_retry_and_repeated_outer_cancel_settle_one_release():
    async def run():
        manifest, chunk = fixture_manifest()
        source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
        original = source.update(query(source.info), sequence=1, style=style())
        raw = g.NativeGeoScaleBridge(BUDGET["processor_bytes"])

        class Bridge:
            fail = False
            hold = False
            attempts = 0
            entered = asyncio.Event()
            release = asyncio.Event()

            async def execute(self, request):
                if int.from_bytes(request[8:12], "little") == 10:
                    self.attempts += 1
                    if self.fail:
                        self.fail = False
                        raise RuntimeError("release not sent")
                    if self.hold:
                        self.entered.set()
                        await self.release.wait()
                return await raw.execute(request)

            async def read(self, request):
                return await raw.read(request)

        bridge = Bridge()
        first = second = None
        try:
            first = await g.prepare_scene_data(
                bridge, handle=source.handle, sequence=1, budget=BUDGET, style=style()
            )
            bridge.fail = True
            with pytest.raises(RuntimeError, match="not sent"):
                await first.dispose()
            with pytest.raises(RuntimeError, match="disposed"):
                _ = first.data
            await first.dispose()
            assert bridge.attempts == 2
            second = await g.prepare_scene_data(
                bridge, handle=source.handle, sequence=1, budget=BUDGET, style=style()
            )
            bridge.hold = True
            pending = asyncio.create_task(second.dispose())
            await bridge.entered.wait()
            pending.cancel()
            await asyncio.sleep(0)
            pending.cancel()
            concurrent = asyncio.create_task(second.dispose())
            await asyncio.sleep(0)
            assert not pending.done() and not concurrent.done()
            assert bridge.attempts == 3
            assert original.data.record(0)["feature_id"] == U64
            bridge.release.set()
            with pytest.raises(asyncio.CancelledError):
                await pending
            await concurrent
            await second.dispose()
            assert bridge.attempts == 3
            with pytest.raises(GeoNativeError):
                await raw.read(g.encode_request(dict(command=23, handle=second.handle)))
        finally:
            bridge.fail = bridge.hold = False
            bridge.release.set()
            if first is not None:
                await first.dispose()
            if second is not None:
                await second.dispose()
            original.close()
            source.close()

    asyncio.run(run())
