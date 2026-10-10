"""Actual native selected hierarchy State→Query→Data and failure ownership."""

import asyncio
import weakref

import numpy as np
import pytest

from test_geo_hierarchy import storage
from test_geo_retained import fixture_manifest, style
from test_geoscale import BUDGET, U64, query
from xyg import _geoscale as g
from xyg._geo_hierarchy import (
    GeoHierarchy,
    GeoHierarchyPublicationUncertain,
    GeoHierarchyUnsupportedSelected,
    hierarchy_lane_authority,
    is_hierarchy_frame,
)
from xyg._geo_retained import RetainedGeoSource
from xyg._geo_selected import GeoSelectedScope
from xyg._native import GeoNativeError


def setup():
    manifest, chunk = fixture_manifest()
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=BUDGET)
    q = {**query(source.info), "state_revision": 1}
    original = source.update(q, sequence=1, style=style())
    scope = GeoSelectedScope.from_frame(original, namespace=U64, layer_id=q["layer_id"])
    issue = lambda: scope.state(  # noqa: E731
        revision=2, ids=np.array([U64], dtype="<u8"), fill=b"\0\xff\0\xff"
    )
    op = issue().begin(source, {**q, "state_revision": 2}, sequence=2)
    op.drive()
    selected = op.prepare(style())
    return source, original, scope, selected, {**q, "state_revision": 2}, issue


def test_private_lane_fork_exact_scene_original_rows_retained_and_frozen():
    source, original, scope, old, q, issue = setup()
    root = lane = frame = retained = None
    try:
        with pytest.raises(GeoHierarchyUnsupportedSelected):
            GeoHierarchy.from_frame(old, source, **storage({}))
        root = GeoHierarchy.from_selected_frame(old, source, **storage({}))
        assert hierarchy_lane_authority(root) == (source, None, 2, True)
        assert hierarchy_lane_authority(GeoHierarchy.__new__(GeoHierarchy)) is None
        lane = root.fork()
        assert hierarchy_lane_authority(lane) == (source, None, 2, True)
        state = issue()
        op = lane.begin_selected(state, q, sequence=3)
        assert op.handle == state.handle
        with pytest.raises(RuntimeError):
            state._check()
        op.drive()
        frame = op.prepare(style())
        assert op.closed and lane.pending_operation is None
        assert frame.data.scene == old.data.scene
        assert frame.data.selection["ids"].tolist() == [U64]
        assert is_hierarchy_frame(frame)
        assert int.from_bytes(frame._query_packet[8:12], "little") == 43
        retained = frame.retain()
        assert is_hierarchy_frame(retained)
        root.close()
        lane.close()
        source.close()
        rows = frame.rows()
        try:
            assert rows.data.record(0)["selected"]
            assert not rows.data.record(1)["selected"]
        finally:
            rows.close()
        artifact = frame.export("svg")
        try:
            assert b"XYSE" in bytes(artifact.snapshot)
            assert bytes(artifact.bytes).startswith(b"<svg")
        finally:
            artifact.close()
        frame.close()
        assert retained.data.record(0)["feature_id"] == U64
    finally:
        for owner in (retained, frame, lane, root, old, original, source, scope):
            if owner is not None:
                owner.close()


def test_rust_rejected_state_reusable_and_failed44_confirmed_query_retry():
    source, original, scope, old, q, issue = setup()
    root = frame = None
    try:
        root = GeoHierarchy.from_selected_frame(old, source, **storage({}))
        state = issue()
        with pytest.raises(GeoNativeError):
            root.begin_selected(state, {**q, "state_revision": 1}, sequence=3)
        assert root.pending_operation is None
        op = root.begin_selected(state, q, sequence=3)
        op.drive()
        with pytest.raises(GeoNativeError):
            op.prepare(style(), budget={**BUDGET, "processor_bytes": 4096})
        frame = op.prepare(style())
        assert frame.handle == state.handle
        assert old.data.record(0)["feature_id"] == U64
    finally:
        for owner in (frame, root, old, original, source, scope):
            if owner is not None:
                owner.close()


def test_async_lost_corrupt43_44_keeps_retryable_exact_cleanup_guard():
    async def run():
        manifest, chunk = fixture_manifest()
        raw = g.NativeGeoScaleBridge(BUDGET["processor_bytes"])

        class BorrowedPacket(bytearray):
            pass

        class Bridge:
            borrowed = None
            command = 0
            mode = ""
            cleanup_fail = False
            publications = 0

            async def execute(self, request):
                command = int.from_bytes(request[8:12], "little")
                if command == 10 and self.borrowed is not None:
                    assert self.borrowed() is None, (
                        "parser traceback retained packet across disposal"
                    )
                if command == 10 and self.cleanup_fail:
                    self.cleanup_fail = False
                    raise RuntimeError("pre-Rust cleanup failure")
                reply = await raw.execute(request)
                if command == 44:
                    self.publications += 1
                if command == self.command:
                    if self.mode == "lost":
                        raise RuntimeError("lost successful reply")
                    if self.mode == "corrupt":
                        return b"\0" + reply[1:]
                return reply

            async def read(self, request):
                packet = await raw.read(request)
                if self.mode == "corrupt-read":
                    borrowed = BorrowedPacket(packet)
                    borrowed[-1] ^= 1
                    self.borrowed = weakref.ref(borrowed)
                    return borrowed
                return packet

        bridge = Bridge()

        async def read_chunk(_):
            return chunk

        source = await RetainedGeoSource.create_async(
            manifest, read_chunk, bridge=bridge, budget=BUDGET
        )
        q = {**query(source.info), "state_revision": 1}
        original = await source.aupdate(q, sequence=1, style=style())
        scope = await GeoSelectedScope.from_frame_async(
            original, namespace=U64, layer_id=q["layer_id"]
        )

        async def issue():
            return await scope.state_async(
                revision=2, ids=np.array([U64], dtype="<u8"), fill=b"\0\xff\0\xff"
            )

        q["state_revision"] = 2
        op = await (await issue()).begin_async(source, q, sequence=2)
        await op.drive_async()
        old = await op.prepare_async(style())
        root = await GeoHierarchy.from_selected_frame_async(old, source, **storage({}))
        frame = None
        try:
            for seq, command, mode in (
                (3, 43, "lost"),
                (4, 43, "corrupt"),
                (5, 44, "lost"),
                (6, 44, "corrupt"),
            ):
                bridge.command, bridge.mode = command, mode
                if command == 43:
                    with pytest.raises((RuntimeError, ValueError)):
                        await root.begin_selected_async(await issue(), q, sequence=seq)
                    pending = root.pending_operation
                else:
                    pending = await root.begin_selected_async(await issue(), q, sequence=seq)
                    await pending.drive_async()
                    with pytest.raises((RuntimeError, ValueError)):
                        await pending.prepare_async(style())
                    previous = bridge.publications
                    with pytest.raises(GeoHierarchyPublicationUncertain):
                        await pending.prepare_async(style())
                    assert bridge.publications == previous
                assert pending is not None
                if command == 43:
                    with pytest.raises((RuntimeError, ValueError)):
                        await pending.recover_async()
                    assert root.pending_operation is pending
                    bridge.mode = ""
                bridge.cleanup_fail = True
                with pytest.raises(RuntimeError, match="pre-Rust"):
                    await pending.aclose()
                assert root.pending_operation is pending
                await pending.aclose()
                assert root.pending_operation is None
                assert old.data.record(0)["feature_id"] == U64
            bridge.command, bridge.mode = 0, "corrupt-read"
            pending = await root.begin_selected_async(await issue(), q, sequence=7)
            await pending.drive_async()
            bridge.cleanup_fail = True
            with pytest.raises(RuntimeError, match="pre-Rust"):
                await pending.prepare_async(style())
            assert root.pending_operation is pending
            assert bridge.borrowed() is None
            await pending.aclose()
            bridge.mode = ""
            frame = await root.aupdate_selected(await issue(), q, sequence=8, style=style())
            assert frame.data.selection["visible_vertices"] == 1
        finally:
            bridge.command, bridge.cleanup_fail = 0, False
            if frame:
                await frame.aclose()
            await root.aclose()
            await old.aclose()
            await original.aclose()
            await source.aclose()
            await scope.aclose()

    asyncio.run(run())


def test_async_repeated_cancel_waits_borrower_and_exact_ack_before_cleanup():
    async def run():
        manifest, chunk = fixture_manifest()
        raw = g.NativeGeoScaleBridge(BUDGET["processor_bytes"])
        read_entered, release_read = asyncio.Event(), asyncio.Event()
        ack_entered, release_ack = asyncio.Event(), asyncio.Event()

        class Bridge:
            gated = False

            async def execute(self, request):
                if self.gated and int.from_bytes(request[8:12], "little") == 8:
                    ack_entered.set()
                    await release_ack.wait()
                return await raw.execute(request)

            async def read(self, request):
                return await raw.read(request)

        bridge = Bridge()

        async def chunk_reader(_):
            return chunk

        source = await RetainedGeoSource.create_async(
            manifest, chunk_reader, budget=BUDGET, bridge=bridge
        )
        q = {**query(source.info), "state_revision": 1}
        original = await source.aupdate(q, sequence=1, style=style())
        scope = await GeoSelectedScope.from_frame_async(
            original, namespace=U64, layer_id=q["layer_id"]
        )

        async def issue():
            return await scope.state_async(
                revision=2, ids=np.array([U64], dtype="<u8"), fill=b"\0\xff\0\xff"
            )

        q["state_revision"] = 2
        op = await (await issue()).begin_async(source, q, sequence=2)
        await op.drive_async()
        old = await op.prepare_async(style())
        pages = {}
        options = storage(pages)

        async def read_page(t):
            data = pages[(t["namespace"], t["page"])]
            if bridge.gated:
                read_entered.set()
                t["raw"] = b"\0" * 128
                t["encoded_bytes"], t["namespace"], t["kind"] = 0, 0, 5
                await release_read.wait()
            return data

        options["read_page"] = read_page
        root = await GeoHierarchy.from_selected_frame_async(old, source, **options)
        pending = None
        frame = None
        try:
            pending = await root.begin_selected_async(await issue(), q, sequence=3)
            bridge.gated = True
            task = asyncio.create_task(pending.drive_async())
            await read_entered.wait()
            cleanup = asyncio.create_task(pending.aclose())
            task.cancel()
            task.cancel()
            await asyncio.sleep(0.01)
            assert not task.done()
            assert not cleanup.done()
            release_read.set()
            await ack_entered.wait()
            task.cancel()
            await asyncio.sleep(0.01)
            assert not task.done()
            assert root.pending_operation is pending
            release_ack.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            await cleanup
            assert pending.closed
            assert root.pending_operation is None
            assert old.data.record(0)["feature_id"] == U64
            bridge.gated = False
            frame = await root.aupdate_selected(await issue(), q, sequence=4, style=style())
            assert frame.data.selection["visible_vertices"] == 1
        finally:
            release_read.set()
            release_ack.set()
            bridge.gated = False
            if pending:
                await pending.aclose()
            if frame:
                await frame.aclose()
            await root.aclose()
            await old.aclose()
            await original.aclose()
            await source.aclose()
            await scope.aclose()

    asyncio.run(run())


def test_explicit_static_composition_mounts_retained_selected_hierarchy_frame():
    import xyg

    source, original, scope, old, q, issue = setup()
    root = frame = host = None
    try:
        root = GeoHierarchy.from_selected_frame(old, source, **storage({}))
        frame = root.update_selected(issue(), q, sequence=3, style=style())
        chart = xyg.geo_chart(
            xyg.geo_layer(
                "points", source=source, layer_id=U64, query=q, sequence=3, style=style()
            ),
            camera=q["camera"],
        )
        host = chart.host(frame=frame)
        assert host._anchor.data.scene == frame.data.scene
        assert host._anchor.data.selection["ids"].tolist() == [U64]
        assert is_hierarchy_frame(host._anchor)
        frame.close()
        root.close()
        source.close()
        assert host._anchor.data.record(0)["feature_id"] == U64
    finally:
        for owner in (host, frame, root, old, original, source, scope):
            if owner is not None:
                owner.close()


def test_issued_operation_uses_captured_lane_transport_storage_and_budget(monkeypatch):
    source, original, scope, old, q, issue = setup()
    root = operation = frame = None
    try:
        root = GeoHierarchy.from_selected_frame(old, source, **storage({}))
        operation = root.begin_selected(issue(), q, sequence=3)
        authored = operation.request
        saved = (root.handle, root.budget, root._reader, root._read_page, root._origin_source)

        def foreign(*_args, **_kwargs):
            raise AssertionError("public decoration redirected an issued operation")

        with monkeypatch.context() as patch:
            patch.setattr(g, "execute", foreign)
            root.handle = U64
            root.budget = {"processor_bytes": 1}
            root._reader = root._read_page = foreign
            root._origin_source = object()
            operation.drive()
            assert operation.request == authored
        frame = operation.prepare(style())
        assert frame.data.selection is not None
        assert frame.data.identity["sequence"] == 3
        root.handle, root.budget, root._reader, root._read_page, root._origin_source = saved
    finally:
        if frame is not None:
            frame.close()
        if operation is not None:
            operation.close()
        if root is not None:
            root.close()
        old.close()
        original.close()
        source.close()
        scope.close()


def test_predispatch_capacity_failure_restores_state_and_clears_pending(monkeypatch):
    from xyg import _geo_hierarchy as h

    source, original, scope, old, q, issue = setup()
    root = frame = None
    try:
        root = GeoHierarchy.from_selected_frame(old, source, **storage({}))
        state = issue()
        actual = h.GeoAllocationAttempt

        def capped(*args, **kwargs):
            raise RuntimeError("bounded host receipt capacity")

        monkeypatch.setattr(h, "GeoAllocationAttempt", capped)
        with pytest.raises(RuntimeError, match="capacity"):
            root.begin_selected(state, q, sequence=3)
        assert root.pending_operation is None
        state._check()
        monkeypatch.setattr(h, "GeoAllocationAttempt", actual)
        frame = root.update_selected(state, q, sequence=3, style=style())
    finally:
        if frame:
            frame.close()
        if root:
            root.close()
        old.close()
        original.close()
        source.close()
        scope.close()


def test_twenty_distinct_disposed_lanes_reclaim_receipts():
    source, original, scope, old, q, issue = setup()
    root = None
    try:
        root = GeoHierarchy.from_selected_frame(old, source, **storage({}))
        for _ in range(20):
            lane = root.fork()
            operation = lane.begin_selected(issue(), q, sequence=3)
            operation.close()
            lane.close()
        assert old.data.record(0)["feature_id"] == U64
    finally:
        if root:
            root.close()
        old.close()
        original.close()
        source.close()
        scope.close()


def test_async_close_waits_admission_confirm_then_reraises_repeated_cancellation():
    async def run():
        raw = g.NativeGeoScaleBridge(BUDGET["processor_bytes"])
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []

        class Bridge:
            armed = False

            async def execute(self, request):
                command = int.from_bytes(request[8:12], "little")
                calls.append((command, int.from_bytes(request[24:32], "little")))
                reply = await raw.execute(request)
                if self.armed and command == 43:
                    entered.set()
                    await release.wait()
                return reply

            async def read(self, request):
                return await raw.read(request)

        bridge = Bridge()
        manifest, chunk = fixture_manifest()
        source = await RetainedGeoSource.create_async(
            manifest, lambda _: asyncio.sleep(0, result=chunk), bridge=bridge, budget=BUDGET
        )
        q = {**query(source.info), "state_revision": 1}
        original = await source.aupdate(q, sequence=1, style=style())
        scope = await GeoSelectedScope.from_frame_async(
            original, namespace=U64, layer_id=q["layer_id"]
        )

        async def issue():
            return await scope.state_async(
                revision=2, ids=np.array([U64], dtype="<u8"), fill=b"\0\xff\0\xff"
            )

        q["state_revision"] = 2
        seed_op = await (await issue()).begin_async(source, q, sequence=2)
        await seed_op.drive_async()
        old = await seed_op.prepare_async(style())
        root = await GeoHierarchy.from_selected_frame_async(old, source, **storage({}))
        try:
            bridge.armed = True
            beginning = asyncio.create_task(root.begin_selected_async(await issue(), q, sequence=3))
            await entered.wait()
            pending = root.pending_operation
            closing = asyncio.create_task(pending.aclose())
            for _ in range(3):
                await asyncio.sleep(0)
                closing.cancel()
            assert not closing.done()
            assert root.pending_operation is pending
            assert (10, 3) not in calls
            release.set()
            await beginning
            with pytest.raises(asyncio.CancelledError):
                await closing
            assert pending.closed and root.pending_operation is None
            assert (10, 3) in calls
            assert old.data.record(0)["feature_id"] == U64
        finally:
            release.set()
            await root.aclose()
            await old.aclose()
            await original.aclose()
            await source.aclose()
            await scope.aclose()

    asyncio.run(run())
