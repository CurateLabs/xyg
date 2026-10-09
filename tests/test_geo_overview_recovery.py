"""Actual Rust allocations behind captured host callbacks, including lost replies."""

import gc
import struct

import pytest

from test_geo_overview_source import build
from xyg import _geoscale as g
from xyg._geo_overview_source import GeoOverviewUncertainAllocation
from xyg._native import GeoNativeError


@pytest.fixture
def control(monkeypatch):
    actual = g.execute
    state = {"fault": None, "calls": []}

    def execute(packet):
        command = struct.unpack_from("<I", packet, 8)[0]
        action = struct.unpack_from("<I", packet, 260)[0] if command == 47 else None
        state["calls"].append((command, action, bytes(packet)))
        fault = state["fault"]
        if fault is not None:
            return fault(packet, actual)
        return actual(packet)

    monkeypatch.setattr(g, "execute", execute)
    yield state
    state["fault"] = None


def lose_once(state, command, action=None, corrupt=False):
    fired = False

    def fault(packet, actual):
        nonlocal fired
        result = actual(packet)
        matched = struct.unpack_from("<I", packet, 8)[0] == command
        if command == 47:
            matched = matched and struct.unpack_from("<I", packet, 260)[0] == action
        if matched and not fired:
            fired = True
            if corrupt:
                return bytes(256)
            raise RuntimeError("lost after actual mutation")
        return result

    state["fault"] = fault


@pytest.mark.parametrize("corrupt", [False, True])
def test_lost28_replays_same_private_allocation_then_publishes_known_handle(control, corrupt):
    source, seed, index, query = build()
    old = index.update(query, sequence=2)
    recovered = None
    try:
        lose_once(control, 28, corrupt=corrupt)
        with pytest.raises(GeoOverviewUncertainAllocation) as caught:
            index.update(query, sequence=3)
        operation = caught.value.owner
        assert index.pending_operation is operation
        operation.recover()
        operation.drive()
        recovered = operation.prepare()
        assert recovered.handle == operation.handle
        operation.close()
        calls = [
            raw
            for cmd, _, raw in control["calls"]
            if cmd == 28 and struct.unpack_from("<Q", raw, 24)[0] == 3
        ]
        assert len(calls) == 2 and calls[0] == calls[1]
        assert sum(recovered.data.count(i) for i in range(256)) == 2
        assert old.data.final is False
    finally:
        control["fault"] = None
        if recovered is not None:
            recovered.close()
        if index.pending_operation is not None:
            index.pending_operation.close()
        old.close()
        index.close()
        seed.close()
        source.close()


def test_lost47_ack_retries_ack_without_reallocating(control):
    source, seed, index, query = build()
    try:
        lose_once(control, 47, 0)
        with pytest.raises(GeoOverviewUncertainAllocation) as caught:
            index.update(query, sequence=2)
        operation = caught.value.owner
        operation.recover()
        assert sum(cmd == 28 for cmd, _, _ in control["calls"]) == 1
        operation.close()
    finally:
        control["fault"] = None
        if index.pending_operation is not None:
            index.pending_operation.close()
        index.close()
        seed.close()
        source.close()


@pytest.mark.parametrize("command", [26, 29])
def test_lost_data_reply_and_oldest_dispose_survive_newer_nonce(control, command):
    source, seed, index, query = build()
    original = index.update(query, sequence=2)
    held = []
    try:
        lose_once(control, command)
        with pytest.raises(GeoOverviewUncertainAllocation) as caught:
            if command == 26:
                original.retain()
            else:
                index.update(query, sequence=3)
        frame = caught.value.owner.recover()
        held.append(frame)
        if index.pending_operation is not None:
            index.pending_operation.close()
        for _ in range(4):
            held.append(original.retain())
        lose_once(control, 10)
        with pytest.raises(RuntimeError, match="lost"):
            held[0].close()
        held[0].close()
        assert held[0]._phase == "closed"
        assert sum(original.data.count(i) for i in range(256)) == 2
    finally:
        control["fault"] = None
        for frame in held:
            frame.close()
        if index.pending_operation is not None:
            index.pending_operation.close()
        original.close()
        index.close()
        seed.close()
        source.close()


def test_definite29_admission_rejection_preserves_complete_query_for_retry(control):
    source, seed, index, query = build()
    operation = index._begin(query, 2)
    frame = None
    try:
        operation.admit()
        operation.drive()

        def reject(packet, actual):
            if struct.unpack_from("<I", packet, 8)[0] == 29:
                raise GeoNativeError(-9)
            return actual(packet)

        control["fault"] = reject
        with pytest.raises(GeoNativeError):
            operation.prepare()
        assert operation._phase == "complete"
        control["fault"] = None
        frame = operation.prepare()
        assert frame.handle == operation.handle
        operation.close()
    finally:
        control["fault"] = None
        operation.close()
        if frame is not None:
            frame.close()
        index.close()
        seed.close()
        source.close()


def test_discarded_target_does_not_discard_issuer_cleanup_receipt(control):
    for _ in range(20):
        source, seed, index, _ = build()
        index.close()
        del index
        gc.collect()
        before = sum(action == 1 for cmd, action, _ in control["calls"] if cmd == 47)
        seed.close()
        after = sum(action == 1 for cmd, action, _ in control["calls"] if cmd == 47)
        assert after == before + 1
        source.close()


def test_retired_original_reply_settles_zero_target_before_next_nonce(control):
    source, seed, index, query = build()
    original = index.update(query, sequence=2)
    held = None
    fired = False

    def fault(packet, actual):
        nonlocal fired
        result = actual(packet)
        if struct.unpack_from("<I", packet, 8)[0] == 26 and not fired:
            fired = True
            target = struct.unpack_from("<Q", result, 16)[0]
            actual(g.encode_request(dict(command=10, handle=target)))
            raise RuntimeError("lost original after actual retirement")
        return result

    try:
        control["fault"] = fault
        with pytest.raises(GeoOverviewUncertainAllocation) as caught:
            original.retain()
        with pytest.raises(RuntimeError, match="retired"):
            caught.value.owner.recover()
        caught.value.owner.close()
        zero_actions = [
            struct.unpack_from("<IQ", raw, 260)
            for command, _, raw in control["calls"]
            if command == 47
        ]
        assert (0, 0) in zero_actions and (2, 0) in zero_actions
        held = original.retain()
    finally:
        control["fault"] = None
        if held is not None:
            held.close()
        original.close()
        index.close()
        seed.close()
        source.close()


def test_lost_birth_release_ack_does_not_repeat_known_data_disposal(control):
    source, seed, index, query = build()
    frame = index.update(query, sequence=2)
    try:
        lose_once(control, 47, 2)
        before = len(control["calls"])
        with pytest.raises(RuntimeError, match="lost"):
            frame.close()
        frame.close()
        disposals = [
            raw
            for cmd, _, raw in control["calls"][before:]
            if cmd == 10 and struct.unpack_from("<Q", raw, 16)[0] == frame.handle
        ]
        assert len(disposals) == 1
    finally:
        control["fault"] = None
        frame.close()
        index.close()
        seed.close()
        source.close()


def test_retained_membership_capture_survives_original_and_index_disposal(control):
    source, seed, index, query = build()
    original = index.update(query, sequence=2)
    held = None
    try:
        lose_once(control, 26)
        with pytest.raises(GeoOverviewUncertainAllocation) as caught:
            original.retain()
        original.close()
        index.close()
        held = caught.value.owner.recover()
        cell = next(i for i in range(256) if held.data.count(i))
        page = held.members(cell, sequence=3, max_vertices=1000)
        assert page.count > 0
        page.close()
    finally:
        control["fault"] = None
        if held is not None:
            held.close()
        original.close()
        index.close()
        seed.close()
        source.close()


def test_corrupt_release22_does_not_allow_nonce_replacement(control):
    source, seed, index, query = build()
    original = index.update(query, sequence=2)
    held = None
    fired = False
    corrupt = True

    def fault(packet, actual):
        nonlocal fired
        result = actual(packet)
        command = struct.unpack_from("<I", packet, 8)[0]
        if command == 26 and not fired:
            fired = True
            target = struct.unpack_from("<Q", result, 16)[0]
            actual(g.encode_request(dict(command=10, handle=target)))
            raise RuntimeError("lost retired target")
        if command == 47 and struct.unpack_from("<I", packet, 260)[0] == 2 and corrupt:
            result = bytearray(result)
            struct.pack_into("<I", result, 8, 22)
            return bytes(result)
        return result

    try:
        control["fault"] = fault
        with pytest.raises(GeoOverviewUncertainAllocation) as caught:
            original.retain()
        with pytest.raises(ValueError, match="Release acknowledgement"):
            caught.value.owner.recover()
        with pytest.raises(GeoOverviewUncertainAllocation):
            original.retain()
        corrupt = False
        caught.value.owner.close()
        held = original.retain()
    finally:
        corrupt = False
        control["fault"] = None
        if held is not None:
            held.close()
        original.close()
        index.close()
        seed.close()
        source.close()


@pytest.mark.parametrize("kind", ["index", "frame", "initial"])
@pytest.mark.parametrize("closing", [False, True])
def test_async_entire_recovery_singleflight_and_close_settles_loan(kind, closing):
    import asyncio

    from test_geo_retained import fixture_manifest, style
    from test_geoscale import BUDGET
    from test_geoscale import query as source_query
    from xyg._geo_overview_source import GeoOverviewIndex
    from xyg._geo_retained import RetainedGeoSource

    async def proof():
        entered, release = asyncio.Event(), asyncio.Event()
        active = False
        lost = False
        reads = 0
        command = 27 if kind == "index" else 26

        class Bridge(g.NativeGeoScaleBridge):
            async def execute(self, packet):
                nonlocal lost
                result = await super().execute(packet)
                if active and not lost and struct.unpack_from("<I", packet, 8)[0] == command:
                    lost = True
                    raise RuntimeError("lost allocation")
                return result

            async def read(self, packet):
                nonlocal reads
                result = await super().read(packet)
                if active and lost and kind in ("frame", "initial"):
                    reads += 1
                    entered.set()
                    await release.wait()
                return result

        bridge = Bridge(BUDGET["processor_bytes"])
        manifest, chunk = fixture_manifest()

        async def read_chunk(_):
            nonlocal reads
            if active and lost and kind == "index":
                reads += 1
                entered.set()
                await release.wait()
            return chunk

        pages = {}

        async def read_page(ticket):
            return pages[ticket["namespace"], ticket["page"]]

        async def write_page(ticket, data):
            pages[ticket["namespace"], ticket["page"]] = bytes(data)

        source = await RetainedGeoSource.create_async(
            manifest, read_chunk, budget=BUDGET, bridge=bridge
        )
        seed = await source.aupdate(source_query(source.info), sequence=1, style=style())
        index = original = owner = None
        options = dict(
            budget=BUDGET,
            max_vertices=1000,
            read_chunk=read_chunk,
            read_page=read_page,
            write_page=write_page,
        )
        try:
            if kind == "index":
                active = True
                with pytest.raises(GeoOverviewUncertainAllocation) as caught:
                    await GeoOverviewIndex.from_frame_async(seed, source, **options)
                owner = caught.value.owner
            else:
                index = await GeoOverviewIndex.from_frame_async(seed, source, **options)
                q = source_query(source.info)
                q.update(max_cells=0, max_projected_vertices=0, previous_direct=False)
                original = await index.update_async(q, sequence=2)
                active = True
                if kind == "initial":
                    from xyg._geo_overview_source import retain_overview_frame_async

                    lost = True
                    issued = []
                    first = asyncio.create_task(
                        retain_overview_frame_async(original, on_issued=issued.append)
                    )
                    await entered.wait()
                    owner = issued[0]
                else:
                    with pytest.raises(GeoOverviewUncertainAllocation) as caught:
                        await original.retain_async()
                    owner = caught.value.owner
            if kind != "initial":
                first = asyncio.create_task(owner.recover_async())
            second = asyncio.create_task(owner.recover_async())
            await entered.wait()
            assert reads == 1
            closed = asyncio.create_task(owner.aclose()) if closing else None
            await asyncio.sleep(0)
            if closed is not None:
                assert not closed.done()
            release.set()
            results = await asyncio.gather(first, second, return_exceptions=True)
            if closing:
                assert all(isinstance(result, BaseException) for result in results)
                await closed
                assert owner._phase == "closed"
            else:
                assert results == [owner, owner]
            assert reads == 1
        finally:
            active = False
            release.set()
            if owner is not None:
                await owner.aclose()
            if original is not None:
                await original.aclose()
            if index is not None:
                await index.aclose()
            await seed.aclose()
            await source.aclose()

    asyncio.run(proof())


def test_lost_forget_ack_retries_without_data_disposal_or_allocation(control):
    source, seed, index, query = build()
    frame = index.update(query, sequence=2)
    try:
        held = frame.retain()
        held.close()
        lose_once(control, 47, 1)
        with pytest.raises(RuntimeError, match="lost"):
            frame.close()
        at = len(control["calls"])
        frame.close()
        assert all(command == 47 for command, _, _ in control["calls"][at:])
    finally:
        control["fault"] = None
        frame.close()
        index.close()
        seed.close()
        source.close()


def test_internal_retained_copy_hook_captures_private_guard_before26(control):
    from xyg._geo_overview_source import retain_overview_frame

    source, seed, index, query = build()
    original = index.update(query, sequence=2)
    issued = []
    try:
        lose_once(control, 26)
        with pytest.raises(GeoOverviewUncertainAllocation):
            retain_overview_frame(original, on_issued=issued.append)
        assert len(issued) == 1 and issued[0].handle == 0
        control["fault"] = None
        issued[0].close()
        assert original.data.final is False
    finally:
        control["fault"] = None
        for owner in issued:
            owner.close()
        original.close()
        index.close()
        seed.close()
        source.close()


def test_resolved_forget22_retains_cleanup_descriptor_until_strict_ack(control):
    source, seed, index, query = build()
    frame = index.update(query, sequence=2)
    corrupt = True

    def fault(packet, actual):
        result = actual(packet)
        if (
            corrupt
            and struct.unpack_from("<I", packet, 8)[0] == 47
            and struct.unpack_from("<I", packet, 260)[0] == 1
        ):
            result = bytearray(result)
            struct.pack_into("<I", result, 8, 22)
            return bytes(result)
        return result

    try:
        control["fault"] = fault
        with pytest.raises(ValueError, match="Forget acknowledgement"):
            frame.close()
        at = len(control["calls"])
        corrupt = False
        frame.close()
        assert control["calls"][at:]
        assert all(command == 47 for command, _, _ in control["calls"][at:])
    finally:
        corrupt = False
        control["fault"] = None
        frame.close()
        index.close()
        seed.close()
        source.close()


def test_exclusive_native_update_captures_canonical_nested_methods(control):
    from xyg._geo_overview_source import update_overview_index

    source, seed, index, query = build()
    frame = None

    def issued(operation):
        def edited(*args, **kwargs):
            raise AssertionError("public edited method dispatched")

        operation.prepare = operation.close = edited

    try:
        frame = update_overview_index(index, query, sequence=2, on_issued=issued)
        assert index.current is None and frame.data.final is False
    finally:
        if frame is not None:
            frame.close()
        index.close()
        seed.close()
        source.close()


def test_predispatch_retained_copy_close_has_no_allocating_or_cleanup_mutation(control):
    from xyg._geo_overview_source import close_overview_owner, retain_overview_frame

    source, seed, index, query = build()
    original = index.update(query, sequence=2)
    try:
        before = len(control["calls"])
        with pytest.raises(RuntimeError, match="closing"):
            retain_overview_frame(original, on_issued=close_overview_owner)
        assert control["calls"][before:] == []
        assert original.data.final is False
    finally:
        original.close()
        index.close()
        seed.close()
        source.close()


def test_canonical_owner_close_ignores_public_methods_for_all_issued_kinds(control):
    from xyg._geo_overview_source import (
        close_overview_owner,
        overview_frame_data,
        retain_overview_frame,
    )

    source, seed, index, query = build()
    issued = []
    frame = index.update(query, sequence=2)

    def edited(*args, **kwargs):
        raise AssertionError("edited public method dispatched")

    try:
        frame.close = edited
        assert overview_frame_data(frame).final is False
        lose_once(control, 26)
        with pytest.raises(GeoOverviewUncertainAllocation):
            retain_overview_frame(frame, on_issued=issued.append)
        issued[0].close = edited
        control["fault"] = None
        close_overview_owner(issued[0])
        operation = index._begin(query, 3)
        operation.admit()
        operation.close = edited
        close_overview_owner(operation)
        close_overview_owner(frame)
        index.close = edited
        close_overview_owner(index)
        with pytest.raises(TypeError, match="Privately issued"):
            close_overview_owner(object())
    finally:
        control["fault"] = None
        for owner in [*issued, frame, index]:
            close_overview_owner(owner)
        seed.close()
        source.close()


def test_native_host_inspection_reconstructs_private_immutable_admitted_packet(control):
    from xyg._geo_overview_source import overview_frame_data

    source, seed, index, query = build()
    frame = index.update(query, sequence=2)
    try:
        packet = bytes(frame.data.packet)
        counts = [frame.data.count(i) for i in range(256)]
        frame.data.scene = memoryview(b"")
        frame.data.packet = memoryview(bytes(len(packet)))
        frame.data.identity["layer_id"] = 0
        frame.data.count = lambda _: 0
        copy = overview_frame_data(frame)
        assert bytes(copy.packet) == packet
        assert [copy.count(i) for i in range(256)] == counts
        assert copy.identity["layer_id"] != 0
        with pytest.raises(RuntimeError, match="inspection unavailable"):
            overview_frame_data(frame)
    finally:
        frame.close()
        index.close()
        seed.close()
        source.close()
