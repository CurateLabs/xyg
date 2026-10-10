"""Actual native durable45 fault controls; requires the issued-attempt dependency."""

import struct

import pytest

from test_geo_overview_source import build
from xyg import _geo_overview_members as members
from xyg._geo_overview_source import _transport


@pytest.mark.parametrize("corrupt", [False, True])
def test_lost_or_corrupt45_exact_recovery_after_all_producers_disposed(monkeypatch, corrupt):
    source, seed, index, query = build()
    frame = index.update(query, sequence=2)
    token, actual = _transport(frame), _transport(frame).native_execute
    births, requests, acks = [], [], []
    fail = True

    def execute(packet):
        nonlocal fail
        command = struct.unpack_from("<I", packet, 8)[0]
        out = actual(packet)
        if command == 45:
            requests.append(bytes(packet))
            births.append(struct.unpack_from("<Q", out, 16)[0])
            assert struct.unpack_from("<Q", packet, 240)[0] > 0
            if fail:
                fail = False
                if corrupt:
                    broken = bytearray(out)
                    broken[0] ^= 1
                    return bytes(broken)
                raise RuntimeError("lost successful45")
        if command == 47:
            acks.append(
                (struct.unpack_from("<Q", packet, 24)[0], struct.unpack_from("<I", packet, 260)[0])
            )
        return out

    page = guard = None
    try:
        monkeypatch.setattr(token, "native_execute", execute)
        with pytest.raises(members.GeoOverviewMembershipUncertain) as error:
            frame.members(136, sequence=10, max_vertices=1000)
        guard = error.value.owner
        frame.close()
        index.close()
        seed.close()
        source.close()
        page = guard.recover()
        assert page.count == 2 and page.cumulative_vertices == 2
        assert page.record(0)["feature_id"] == (1 << 64) - 1
        assert len(requests) == 2 and requests[0] == requests[1]
        assert births[0] == births[1] != 0
        assert (10, 0) in acks  # Returned operation sequence, not parent publication2.
        page.close()
        page = None
        assert (10, 2) in acks and (10, 1) in acks
    finally:
        monkeypatch.setattr(token, "native_execute", actual)
        if page is not None:
            page.close()
        if guard is not None:
            guard.close()
        frame.close()
        index.close()
        seed.close()
        source.close()


def test_lost_confirm_recovery_retries_only47_and_preserves_old_frame(monkeypatch):
    source, seed, index, query = build()
    frame = index.update(query, sequence=2)
    token, actual = _transport(frame), _transport(frame).native_execute
    calls, fail = [], True

    def execute(packet):
        nonlocal fail
        command = struct.unpack_from("<I", packet, 8)[0]
        calls.append(command)
        out = actual(packet)
        if command == 47 and struct.unpack_from("<I", packet, 260)[0] == 0 and fail:
            fail = False
            raise RuntimeError("lost successful Confirm")
        return out

    page = guard = None
    try:
        monkeypatch.setattr(token, "native_execute", execute)
        with pytest.raises(members.GeoOverviewMembershipUncertain) as error:
            frame.members(136, sequence=10, max_vertices=1000)
        guard = error.value.owner
        assert frame.data.count(136) == 2 and 6 not in calls
        page = guard.recover()
        assert calls.count(45) == 1
        assert calls[:3] == [45, 47, 47]
        assert page.count == 2
        page.close()
        page = None
    finally:
        monkeypatch.setattr(token, "native_execute", actual)
        if page is not None:
            page.close()
        if guard is not None:
            guard.close()
        frame.close()
        index.close()
        seed.close()
        source.close()


def test_async_notebook_recovery_is_singleflight_and_close_waits_reader():
    import asyncio

    from test_geo_retained import fixture_manifest, style
    from test_geoscale import BUDGET, query
    from xyg._geo_overview_source import GeoOverviewIndex
    from xyg._geo_retained import RetainedGeoSource

    async def notebook():
        manifest, chunk = fixture_manifest()
        entered, release = asyncio.Event(), asyncio.Event()
        gated = False
        events = []

        async def read_chunk(_):
            if gated:
                events.append("read")
                entered.set()
                await release.wait()
                events.append("settled")
            return chunk

        source = await RetainedGeoSource.create_async(manifest, read_chunk, budget=BUDGET)
        seed = await source.aupdate(query(source.info), sequence=1, style=style())
        pages = {}

        async def read_page(t):
            return pages[t["namespace"], t["page"]]

        async def write_page(t, b):
            pages[t["namespace"], t["page"]] = bytes(b)

        index = await GeoOverviewIndex.from_frame_async(
            seed,
            source,
            budget=BUDGET,
            max_vertices=1000,
            read_chunk=read_chunk,
            read_page=read_page,
            write_page=write_page,
        )
        q = query(source.info)
        q.update(max_cells=0, max_projected_vertices=0, previous_direct=False)
        frame = await index.update_async(q, sequence=2)
        token, actual = _transport(frame), _transport(frame).execute
        fail = True

        async def execute(packet):
            nonlocal fail
            code = struct.unpack_from("<I", packet, 8)[0]
            result = await actual(packet)
            if code == 45 and fail:
                fail = False
                raise RuntimeError("lost45")
            if code == 8:
                events.append("ack")
            return result

        token.execute = execute
        guard = None
        try:
            with pytest.raises(members.GeoOverviewMembershipUncertain) as caught:
                await frame.members_async(136, sequence=10, max_vertices=1000)
            guard = caught.value.owner
            gated = True
            first = asyncio.create_task(guard.recover_async())
            second = asyncio.create_task(guard.recover_async())
            await entered.wait()
            closing = asyncio.create_task(guard.aclose())
            await asyncio.sleep(0)
            assert not closing.done() and events == ["read"]
            release.set()
            outcomes = await asyncio.gather(first, second, return_exceptions=True)
            assert all(isinstance(v, BaseException) for v in outcomes)
            await closing
            assert events == ["read", "settled", "ack"]
            assert guard._phase == "closed" and frame.data.count(136) == 2
            gated = False
            page = await frame.members_async(136, sequence=11, max_vertices=1000)
            await page.aclose()
        finally:
            release.set()
            if guard is not None:
                await guard.aclose()
            await frame.aclose()
            await index.aclose()
            await seed.aclose()
            await source.aclose()

    asyncio.run(notebook())


def test_retired_original45_is_confirmed_without_query_resurrection(monkeypatch):
    source, seed, index, query = build()
    frame = index.update(query, sequence=2)
    token, actual = _transport(frame), _transport(frame).native_execute
    fail = True
    guard = page = None

    def execute(packet):
        nonlocal fail
        result = actual(packet)
        if struct.unpack_from("<I", packet, 8)[0] == 45 and fail:
            fail = False
            actual(members.request(10, members.reply(result)["handle"], 10))
            raise RuntimeError("lost original after Query retirement")
        return result

    try:
        monkeypatch.setattr(token, "native_execute", execute)
        with pytest.raises(members.GeoOverviewMembershipUncertain) as caught:
            frame.members(136, sequence=10, max_vertices=1000)
        guard = caught.value.owner
        with pytest.raises(RuntimeError, match="retired"):
            guard.recover()
        assert guard._phase == "closed"
        guard.close()
        page = frame.members(136, sequence=11, max_vertices=1000)
        assert page.record(0)["feature_id"] == (1 << 64) - 1
    finally:
        if page is not None:
            page.close()
        if guard is not None:
            guard.close()
        frame.close()
        index.close()
        seed.close()
        source.close()


@pytest.mark.parametrize("cancel_all", [False, True])
def test_shared_recover_cancelled_waiters_preserve_delivery_or_close(cancel_all):
    import asyncio

    from test_geo_retained import fixture_manifest, style
    from test_geoscale import BUDGET, query
    from xyg._geo_overview_source import GeoOverviewIndex
    from xyg._geo_retained import RetainedGeoSource

    async def notebook():
        manifest, chunk = fixture_manifest()
        entered, release = asyncio.Event(), asyncio.Event()
        cleanup_entered, cleanup_release = asyncio.Event(), asyncio.Event()
        gated = False
        events = []

        async def read_chunk(_):
            if gated:
                events.append("read")
                entered.set()
                await release.wait()
                events.append("settled")
            return chunk

        source = await RetainedGeoSource.create_async(manifest, read_chunk, budget=BUDGET)
        seed = await source.aupdate(query(source.info), sequence=1, style=style())
        pages = {}

        async def read_page(t):
            return pages[t["namespace"], t["page"]]

        async def write_page(t, b):
            pages[t["namespace"], t["page"]] = bytes(b)

        index = await GeoOverviewIndex.from_frame_async(
            seed,
            source,
            budget=BUDGET,
            max_vertices=1000,
            read_chunk=read_chunk,
            read_page=read_page,
            write_page=write_page,
        )
        q = query(source.info)
        q.update(max_cells=0, max_projected_vertices=0, previous_direct=False)
        frame = await index.update_async(q, sequence=2)
        token, actual = _transport(frame), _transport(frame).execute
        fail = True

        async def execute(packet):
            nonlocal fail
            code = struct.unpack_from("<I", packet, 8)[0]
            if code == 10 and gated and cancel_all and struct.unpack_from("<Q", packet, 24)[0] == 0:
                cleanup_entered.set()
                await cleanup_release.wait()
            result = await actual(packet)
            if code == 45 and fail:
                fail = False
                raise RuntimeError("lost45")
            if code == 8:
                events.append("ack")
            return result

        token.execute = execute
        guard = None
        try:
            with pytest.raises(members.GeoOverviewMembershipUncertain) as caught:
                await frame.members_async(136, sequence=10, max_vertices=1000)
            guard = caught.value.owner
            gated = True
            first = asyncio.create_task(guard.recover_async())
            second = asyncio.create_task(guard.recover_async())
            await entered.wait()
            first.cancel()
            if cancel_all:
                second.cancel()
            await asyncio.sleep(0)
            release.set()
            if cancel_all:
                await cleanup_entered.wait()
                with pytest.raises(RuntimeError, match="closed"):
                    await guard.recover_async()
                cleanup_release.set()
            outcomes = await asyncio.gather(first, second, return_exceptions=True)
            assert isinstance(outcomes[0], asyncio.CancelledError)
            if cancel_all:
                assert isinstance(outcomes[1], asyncio.CancelledError)
                assert guard._page is not None and guard._page._closed
            else:
                assert not isinstance(outcomes[1], BaseException), outcomes[1]
                page = outcomes[1]
                assert page.record(0)["feature_id"] == (1 << 64) - 1
                await page.aclose()
            gated = False
            page = await frame.members_async(136, sequence=11, max_vertices=1000)
            await page.aclose()
        finally:
            release.set()
            cleanup_release.set()
            if guard is not None:
                await guard.aclose()
            await frame.aclose()
            await index.aclose()
            await seed.aclose()
            await source.aclose()

    asyncio.run(notebook())


def test_overlapping_admission_has_one_acceptance_flight():
    import asyncio

    from test_geo_retained import fixture_manifest, style
    from test_geoscale import BUDGET, query
    from xyg._geo_overview_source import GeoOverviewIndex
    from xyg._geo_retained import RetainedGeoSource

    async def notebook():
        manifest, chunk = fixture_manifest()
        entered, release = asyncio.Event(), asyncio.Event()
        gated = False
        events = []

        async def read_chunk(_):
            if gated:
                events.append("read")
                entered.set()
                await release.wait()
                events.append("settled")
            return chunk

        source = await RetainedGeoSource.create_async(manifest, read_chunk, budget=BUDGET)
        seed = await source.aupdate(query(source.info), sequence=1, style=style())
        pages = {}

        async def read_page(t):
            return pages[t["namespace"], t["page"]]

        async def write_page(t, b):
            pages[t["namespace"], t["page"]] = bytes(b)

        index = await GeoOverviewIndex.from_frame_async(
            seed,
            source,
            budget=BUDGET,
            max_vertices=1000,
            read_chunk=read_chunk,
            read_page=read_page,
            write_page=write_page,
        )
        q = query(source.info)
        q.update(max_cells=0, max_projected_vertices=0, previous_direct=False)
        frame = await index.update_async(q, sequence=2)
        token, actual = _transport(frame), _transport(frame).execute
        fail = True

        async def execute(packet):
            nonlocal fail
            code = struct.unpack_from("<I", packet, 8)[0]
            result = await actual(packet)
            if code == 45 and fail:
                fail = False
                raise RuntimeError("lost45")
            if code == 45 and gated:
                events.append("admit")
                entered.set()
                await release.wait()
            if code == 8:
                events.append("ack")
            return result

        token.execute = execute
        guard = None
        try:
            with pytest.raises(members.GeoOverviewMembershipUncertain) as caught:
                await frame.members_async(136, sequence=10, max_vertices=1000)
            guard = caught.value.owner
            gated = True
            first = asyncio.create_task(guard.admit_async())
            second = asyncio.create_task(guard.admit_async())
            await entered.wait()
            assert guard._phase == "uncertain"
            release.set()
            await asyncio.gather(first, second)
            assert events == ["admit"] and guard._phase == "query"
            gated = False
            page = await guard.recover_async()
            assert page.record(0)["feature_id"] == (1 << 64) - 1
            await page.aclose()
            gated = False
            page = await frame.members_async(136, sequence=11, max_vertices=1000)
            await page.aclose()
        finally:
            release.set()
            if guard is not None:
                await guard.aclose()
            await frame.aclose()
            await index.aclose()
            await seed.aclose()
            await source.aclose()

    asyncio.run(notebook())
