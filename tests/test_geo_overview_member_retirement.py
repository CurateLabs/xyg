"""Known MemberData cleanup: genuine original sequence, never retired45 authority."""

import asyncio
import struct

import pytest

from test_geo_overview_source import build
from xyg import _geo_overview_members as members
from xyg._geo_overview_source import _transport


@pytest.mark.parametrize("corrupt", [False, True])
def test_lost_successful_member10_recovers_after_all_producers_gone(monkeypatch, corrupt):
    source, seed, index, q = build()
    frame = index.update(q, sequence=2)
    page = frame.members(136, sequence=10, max_vertices=1000)
    token, actual = _transport(frame), _transport(frame).native_execute
    handle, sequence = page.handle, page.sequence
    source.close()
    seed.close()
    index.close()
    frame.close()
    calls, lose = [], True

    def execute(packet):
        nonlocal lose
        command, owner = struct.unpack_from("<I4xQ", packet, 8)
        if owner == handle:
            calls.append((command, struct.unpack_from("<Q", packet, 24)[0]))
        result = actual(packet)
        if command == 10 and owner == handle and lose:
            lose = False
            if corrupt:
                bad = bytearray(result)
                bad[48] = 1
                return bytes(bad)
            raise RuntimeError("lost successful MemberData10")
        return result

    try:
        monkeypatch.setattr(token, "native_execute", execute)
        with pytest.raises((RuntimeError, ValueError)):
            page.close()
        assert not page._closed
        with pytest.raises(RuntimeError, match="disposed"):
            page.record(0)
        page.close()
        assert page._closed and members._PAGES[page][0] is None
        assert calls == [(10, 0), (6, sequence)]
        page.close()
        assert len(calls) == 2
    finally:
        monkeypatch.setattr(token, "native_execute", actual)
        page.close()
        frame.close()
        index.close()
        seed.close()
        source.close()


@pytest.mark.parametrize("saved_genuine", [False, True])
def test_fake_or_saved_wrongseq_stale_does_not_retire_live_memberdata(monkeypatch, saved_genuine):
    source, seed, index, q = build()
    frame = index.update(q, sequence=2)
    page = frame.members(136, sequence=10, max_vertices=1000)
    token, actual = _transport(frame), _transport(frame).native_execute
    try:
        try:
            actual(members.request(6, page.handle, page.sequence + 1))
        except BaseException as error:
            old = error
        fake = RuntimeError("XYG_GEO_SOURCE_STALE")
        fake.status, fake.code = -10, "XYG_GEO_SOURCE_STALE"
        pre = True

        def execute(packet):
            nonlocal pre
            command = struct.unpack_from("<I", packet, 8)[0]
            if command == 10 and pre:
                pre = False
                raise RuntimeError("before Rust10")
            result = actual(packet)
            if command == 6:
                raise old if saved_genuine else fake
            return result

        monkeypatch.setattr(token, "native_execute", execute)
        with pytest.raises(RuntimeError, match="before Rust10"):
            page.close()
        with pytest.raises(type(old) if saved_genuine else RuntimeError):
            page.close()
        assert not page._closed and members._PAGES[page][0] is not None
        live = members.reply(actual(members.request(6, page.handle, page.sequence)))
        assert live["source"] == page.handle and live["code"] == 0
        monkeypatch.setattr(token, "native_execute", actual)
        page.close()
        assert page._closed
    finally:
        monkeypatch.setattr(token, "native_execute", actual)
        page.close()
        frame.close()
        index.close()
        seed.close()
        source.close()


def test_async_notebook_close_singleflight_settles_probe_before_cancelled_waiter_returns():
    from test_geo_retained import fixture_manifest, style
    from test_geoscale import BUDGET, query
    from xyg._geo_overview_source import GeoOverviewIndex
    from xyg._geo_retained import RetainedGeoSource

    async def notebook():
        manifest, chunk = fixture_manifest()

        async def reader(_):
            return chunk

        source = await RetainedGeoSource.create_async(manifest, reader, budget=BUDGET)
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
            read_chunk=reader,
            read_page=read_page,
            write_page=write_page,
        )
        q = query(source.info)
        q.update(max_cells=0, max_projected_vertices=0, previous_direct=False)
        frame = await index.update_async(q, sequence=2)
        page = await frame.members_async(136, sequence=10, max_vertices=1000)
        token, actual = _transport(frame), _transport(frame).execute
        entered, release = asyncio.Event(), asyncio.Event()
        calls, lose = [], True

        async def execute(packet):
            nonlocal lose
            command, handle = struct.unpack_from("<I4xQ", packet, 8)
            if handle == page.handle:
                calls.append(command)
            if command == 6 and handle == page.handle:
                entered.set()
                await release.wait()
            result = await actual(packet)
            if command == 10 and handle == page.handle and lose:
                lose = False
                raise RuntimeError("lost successful MemberData10")
            return result

        try:
            token.execute = execute
            with pytest.raises(RuntimeError, match="lost successful"):
                await page.aclose()
            first = asyncio.create_task(page.aclose())
            second = asyncio.create_task(page.aclose())
            await entered.wait()
            first.cancel()
            first.cancel()
            await asyncio.sleep(0)
            assert not first.done() and not second.done() and not page._closed
            assert calls == [10, 6]
            release.set()
            outcomes = await asyncio.gather(first, second, return_exceptions=True)
            assert isinstance(outcomes[0], asyncio.CancelledError)
            assert outcomes[1] is None
            assert page._closed and members._PAGES[page][0] is None
            assert calls == [10, 6]
        finally:
            release.set()
            token.execute = actual
            await page.aclose()
            await frame.aclose()
            await index.aclose()
            await seed.aclose()
            await source.aclose()

    asyncio.run(notebook())


def test_spoofed_func_attribute_on_author_callable_cannot_grant_native_absence():
    from test_geo_retained import fixture_manifest, style
    from test_geoscale import BUDGET, query
    from xyg import _geoscale as g
    from xyg._geo_overview_source import GeoOverviewIndex
    from xyg._geo_retained import RetainedGeoSource
    from xyg._native import GeoNativeError

    async def notebook():
        manifest, chunk = fixture_manifest()
        bridge = g.NativeGeoScaleBridge(BUDGET["processor_bytes"])
        canonical = bridge.execute

        async def wrapped(packet):
            return await canonical(packet)

        # This is an ordinary function decoration, not an actual bound method.
        wrapped.__func__ = g.NativeGeoScaleBridge.execute
        bridge.execute = wrapped

        async def reader(_):
            return chunk

        source = await RetainedGeoSource.create_async(
            manifest, reader, budget=BUDGET, bridge=bridge
        )
        seed = await source.aupdate(query(source.info), sequence=1, style=style())
        storage = {}

        async def read_page(t):
            return storage[t["namespace"], t["page"]]

        async def write_page(t, b):
            storage[t["namespace"], t["page"]] = bytes(b)

        index = await GeoOverviewIndex.from_frame_async(
            seed,
            source,
            budget=BUDGET,
            max_vertices=1000,
            read_chunk=reader,
            read_page=read_page,
            write_page=write_page,
        )
        q = query(source.info)
        q.update(max_cells=0, max_projected_vertices=0, previous_direct=False)
        frame = await index.update_async(q, sequence=2)
        page = await frame.members_async(136, sequence=10, max_vertices=1000)
        token, actual = _transport(frame), _transport(frame).execute
        c = members._PAGES[page][0]
        assert members._CONTEXT_NATIVE_PRODUCERS[c] is False
        c.native_probe = True  # public decoration does not change private classification
        lost = True

        async def execute(packet):
            nonlocal lost
            result = await actual(packet)
            if struct.unpack_from("<I", packet, 8)[0] == 10 and lost:
                lost = False
                raise RuntimeError("lost actual10 on wrapped author producer")
            return result

        try:
            token.execute = execute
            with pytest.raises(RuntimeError, match="lost actual10"):
                await page.aclose()
            with pytest.raises(GeoNativeError):
                await page.aclose()
            assert not page._closed
            assert members._PAGES[page][0] is c
            # Rust Data is genuinely gone, but the generic author closure cannot
            # prove which registry owns its original frame. The guard stays.
            with pytest.raises(GeoNativeError):
                await canonical(members.request(6, page.handle, page.sequence))
        finally:
            token.execute = actual
            await frame.aclose()
            await index.aclose()
            await seed.aclose()
            await source.aclose()

    asyncio.run(notebook())


def test_failed_memberdata_read_then_lost10_keeps_known_operation_recovery(monkeypatch):
    source, seed, index, q = build()
    frame = index.update(q, sequence=2)
    token = _transport(frame)
    actual, read = token.native_execute, token.native_read
    lose = True
    guard = None

    def bad_read(packet, budget):
        raw = read(packet, budget)
        if struct.unpack_from("<I", packet, 8)[0] == 23:
            changed = bytearray(raw)
            changed[4] = 255
            return bytes(changed)
        return raw

    def execute(packet):
        nonlocal lose
        raw = actual(packet)
        if struct.unpack_from("<I", packet, 8)[0] == 10 and lose:
            lose = False
            raise RuntimeError("lost successful operation MemberData10")
        return raw

    try:
        monkeypatch.setattr(token, "native_read", bad_read)
        monkeypatch.setattr(token, "native_execute", execute)
        with pytest.raises(members.GeoOverviewMembershipCleanupPending) as caught:
            frame.members(136, sequence=10, max_vertices=1000)
        guard = caught.value.owner
        assert guard._phase == "data" and not guard._disposed
        monkeypatch.setattr(token, "native_read", read)
        monkeypatch.setattr(token, "native_execute", actual)
        guard.close()
        assert guard._phase == "closed"
        assert frame.data.count(136) == 2
    finally:
        monkeypatch.setattr(token, "native_read", read)
        monkeypatch.setattr(token, "native_execute", actual)
        if guard is not None:
            guard.close()
        frame.close()
        index.close()
        seed.close()
        source.close()
