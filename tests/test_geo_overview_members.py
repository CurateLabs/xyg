"""Actual native original-row membership and callback/ownership proofs."""

import asyncio
import struct

import numpy as np
import pytest

from test_geo_overview_source import build
from test_geo_retained import fixture_manifest, style
from test_geoscale import BUDGET, query
from xyg import _geo_overview_members as members
from xyg import _geoscale as g
from xyg._geo_overview_source import GeoOverviewIndex, _transport
from xyg._geo_retained import RetainedGeoSource


def test_sync_notebook_pages_after_all_producers_and_frame_disposed():
    async def notebook():
        source, seed, index, q = build()
        frame = index.update(q, sequence=2)
        held = frame.retain()
        source.close()
        seed.close()
        index.close()
        frame.close()
        page = held.members(136, sequence=3, max_vertices=1000)
        held.close()
        try:
            assert page.count == 2 and not page.has_next
            assert page.cumulative_vertices == 2
            assert page.record(0)["feature_id"] == (1 << 64) - 1
            assert page.record(1)["source_row"] == 1
            assert page.temporal_exact and page.data_space and not page.final
            with pytest.raises(ValueError):
                page.next_page(sequence=4, max_vertices=1000)
        finally:
            page.close()
        with pytest.raises(RuntimeError, match="disposed"):
            _ = page.raw

    asyncio.run(notebook())


def test_lost46_known_probe_and_lost45_poison_oldframe(monkeypatch):
    source, seed, index, q = build()
    frame = index.update(q, sequence=2)
    token, actual = _transport(frame), _transport(frame).native_execute
    lost, attempts = [], []

    def execute(packet):
        code = struct.unpack_from("<I", packet, 8)[0]
        out = actual(packet)
        if code in (45, 46):
            attempts.append(code)
        if code == 46:
            raise RuntimeError("lost successful46")
        return out

    try:
        monkeypatch.setattr(token, "native_execute", execute)
        page = frame.members(136, sequence=3, max_vertices=1000)
        assert page.count == 2 and attempts.count(46) == 1
        page.close()

        def lose45(packet):
            out = actual(packet)
            if struct.unpack_from("<I", packet, 8)[0] == 45:
                lost.append(members.reply(out)["handle"])
                raise RuntimeError("lost successful45")
            return out

        monkeypatch.setattr(token, "native_execute", lose45)
        with pytest.raises(members.GeoOverviewMembershipUncertain) as caught:
            frame.members(136, sequence=4, max_vertices=1000)
        with pytest.raises(members.GeoOverviewMembershipUncertain) as second:
            frame.members(136, sequence=5, max_vertices=1000)
        assert second.value.owner is caught.value.owner and len(lost) == 1
        assert frame.data.count(136) == 2
        with pytest.raises(members.GeoOverviewMembershipUncertain):
            caught.value.owner.close()
    finally:
        monkeypatch.setattr(token, "native_execute", actual)
        for handle in lost:
            actual(members.request(10, handle, 4))  # Test-only real-receipt observer.
        frame.close()
        index.close()
        seed.close()
        source.close()


def test_ticket_mutation_does_not_change_authorized_length_or_ack(monkeypatch):
    source, seed, index, q = build()
    frame = index.update(q, sequence=2)
    context = members._CONTEXTS[frame]
    reader, token, actual = context.reader, _transport(frame), _transport(frame).native_execute
    calls = []

    def mutate(ticket):
        ticket["encoded_bytes"] = 2048
        ticket["digest"] = b"\0" * 8
        return bytes(2048)

    def observe(packet):
        calls.append(struct.unpack_from("<I", packet, 8)[0])
        return actual(packet)

    try:
        context.reader = mutate
        monkeypatch.setattr(token, "native_execute", observe)
        with pytest.raises(ValueError, match="Exact owning"):
            frame.members(136, sequence=3, max_vertices=1000)
        assert 7 not in calls and calls.count(8) == 1
        context.reader = reader
        page = frame.members(136, sequence=4, max_vertices=1000)
        page.close()
    finally:
        context.reader = reader
        monkeypatch.setattr(token, "native_execute", actual)
        frame.close()
        index.close()
        seed.close()
        source.close()


def test_rejected_ack_and_cleanup_are_guarded_and_retryable(monkeypatch):
    source, seed, index, q = build()
    frame = index.update(q, sequence=2)
    token, actual = _transport(frame), _transport(frame).native_execute
    acks, fail = [], True

    def reject(packet):
        if struct.unpack_from("<I", packet, 8)[0] == 8:
            acks.append(packet[256:])
            if fail:
                raise RuntimeError("ACK rejection")
        return actual(packet)

    try:
        monkeypatch.setattr(token, "native_execute", reject)
        with pytest.raises(members.GeoOverviewMembershipCleanupPending) as caught:
            frame.members(136, sequence=3, max_vertices=1000)
        fail = False
        caught.value.owner.close()
        assert len(acks) >= 3 and all(a == acks[0] for a in acks)
        page = frame.members(136, sequence=4, max_vertices=1000)
        rejected = False

        def reject10(packet):
            nonlocal rejected
            if struct.unpack_from("<I", packet, 8)[0] == 10 and not rejected:
                rejected = True
                raise RuntimeError("cleanup rejection")
            return actual(packet)

        monkeypatch.setattr(token, "native_execute", reject10)
        with pytest.raises(RuntimeError, match="cleanup rejection"):
            page.close()
        with pytest.raises(RuntimeError, match="disposed"):
            _ = page.raw
        page.close()
    finally:
        monkeypatch.setattr(token, "native_execute", actual)
        frame.close()
        index.close()
        seed.close()
        source.close()


def test_async_repeated_cancellation_settles_reader_before_exact_ack_and_recovery():
    async def proof():
        manifest, chunk = fixture_manifest()
        entered, release = asyncio.Event(), asyncio.Event()
        gated, events = False, []

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

        async def observe(packet):
            if struct.unpack_from("<I", packet, 8)[0] == 8:
                events.append("ack")
            return await actual(packet)

        token.execute = observe
        try:
            gated = True
            task = asyncio.create_task(frame.members_async(136, sequence=3, max_vertices=1000))
            await entered.wait()
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            assert events == ["read"] and not task.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert events == ["read", "settled", "ack"]
            assert frame.data.count(136) == 2
            gated = False
            page = await frame.members_async(136, sequence=4, max_vertices=1000)
            await page.aclose()
        finally:
            release.set()
            token.execute = actual
            await frame.aclose()
            await index.aclose()
            await seed.aclose()
            await source.aclose()

    asyncio.run(proof())


def test_lost_successful_ack_cancels_and_preserves_next_query(monkeypatch):
    source, seed, index, q = build()
    frame = index.update(q, sequence=2)
    token, actual = _transport(frame), _transport(frame).native_execute
    lost = False

    def execute(packet):
        nonlocal lost
        out = actual(packet)
        if struct.unpack_from("<I", packet, 8)[0] == 8 and not lost:
            lost = True
            raise RuntimeError("lost successful8")
        return out

    try:
        monkeypatch.setattr(token, "native_execute", execute)
        with pytest.raises(ValueError, match="not complete"):
            frame.members(136, sequence=3, max_vertices=1000)
        assert lost and frame.data.count(136) == 2
        page = frame.members(136, sequence=4, max_vertices=1000)
        page.close()
    finally:
        monkeypatch.setattr(token, "native_execute", actual)
        frame.close()
        index.close()
        seed.close()
        source.close()


def multipoint_build():
    """Independent ten-row/two-chunk source, with a null row and repeated IDs."""
    descriptor = bytearray(216)
    struct.pack_into("<4s5I5Q", descriptor, 0, b"XYGD", 1, 4, 4326, 1, 0, 5, 5, 6, 0, 0)
    struct.pack_into("<10d", descriptor, 64, 0, 0, 0, 0, -90, 0, 90, 0, 0, 0)
    descriptor[144:149] = bytes((1, 1, 1, 0, 1))
    struct.pack_into("<5Q", descriptor, 152, (1 << 64) - 1, (1 << 53) + 1, 7, 7, (1 << 64) - 1)
    struct.pack_into("<6I", descriptor, 192, 0, 2, 3, 4, 4, 5)
    chunk = g.read(
        g.encode_chunk_request(
            dict(
                descriptor=bytes(descriptor),
                rows=5,
                intervals=dict(
                    starts=np.array([-(1 << 63), 0, 10, 0, -(1 << 63)], dtype="<i8"),
                    ends=np.array([0, 10, 0, 0, 0], dtype="<i8"),
                    start_validity=np.array([0, 1, 1, 0, 0], dtype="u1"),
                    end_validity=np.array([1, 1, 0, 0, 1], dtype="u1"),
                ),
            ),
            BUDGET["processor_bytes"],
        ),
        BUDGET["processor_bytes"],
    )
    builder = g.decode_reply(g.execute(g.encode_request(dict(command=1))))["handle"]
    try:
        for _ in range(2):
            g.execute(g.encode_request(dict(command=2, handle=builder, payload=chunk)))
        g.execute(g.encode_request(dict(command=3, handle=builder, generation=(1 << 64) - 1)))
        manifest = g.read(
            g.encode_request(dict(command=21, handle=builder)), BUDGET["processor_bytes"]
        )
    finally:
        g.execute(g.encode_request(dict(command=10, handle=builder)))
    budget = {**BUDGET, "page_rows": 1}
    source = RetainedGeoSource(manifest, lambda _: chunk, budget=budget)
    q = query(source.info)
    q["time"] = {"kind": 0}
    seed = source.update(q, sequence=1, style=style())
    pages = {}
    index = GeoOverviewIndex.from_frame(
        seed,
        source,
        budget=budget,
        max_vertices=1000,
        read_chunk=lambda _: chunk,
        read_page=lambda t: pages[t["namespace"], t["page"]],
        write_page=lambda t, b: pages.__setitem__((t["namespace"], t["page"]), bytes(b)),
    )
    q.update(max_cells=0, max_projected_vertices=0, previous_direct=False)
    return source, seed, index, q


@pytest.mark.parametrize(
    "time,cell,expected",
    [
        ({"kind": 0}, 136, 6),
        ({"kind": 1, "instant": -(1 << 63)}, 136, 6),
        ({"kind": 2, "start": -(1 << 63), "end": 0}, 136, 6),
        ({"kind": 1, "instant": 0}, 132, 2),
        ({"kind": 1, "instant": 10}, 140, 2),
        ({"kind": 1, "instant": (1 << 63) - 1}, 140, 2),
        ({"kind": 2, "start": 10, "end": (1 << 63) - 1}, 140, 2),
    ],
)
def test_full_signed_time_multipoint_pages_after_producer_release(time, cell, expected):
    source, seed, index, q = multipoint_build()
    q["time"] = time
    frame = index.update(q, sequence=2)
    assert frame.data.count(cell) == expected
    page = frame.members(cell, sequence=10, max_vertices=1000)
    frame.close()
    index.close()
    seed.close()
    source.close()
    rows, counts = [], []
    try:
        sequence = 11
        while True:
            assert page.count <= 1
            assert page.raw.readonly
            for i in range(page.count):
                record = page.record(i)
                rows.append(record["source_row"])
                counts.append(record["matched_vertices"])
                assert record["feature_id"] == (
                    (1 << 64) - 1 if cell == 136 else (1 << 53) + 1 if cell == 132 else 7
                )
            if not page.has_next:
                break
            next_page = page.next_page(sequence=sequence, max_vertices=1000)
            sequence += 1
            page.close()
            page = next_page
        assert sum(counts) == expected == page.cumulative_vertices
        assert rows == ([0, 4, 5, 9] if cell == 136 else [1, 6] if cell == 132 else [2, 7])
        assert counts == ([2, 1, 2, 1] if cell == 136 else [1, 1])
    finally:
        page.close()


def test_resolved_rejected_or_malformed_disposal_preserves_retry(monkeypatch):
    source, seed, index, q = build()
    frame = index.update(q, sequence=2)
    page = frame.members(136, sequence=3, max_vertices=1000)
    token, actual = _transport(frame), _transport(frame).native_execute
    failures = 0

    def execute(packet):
        nonlocal failures
        if struct.unpack_from("<I", packet, 8)[0] == 10 and failures < 2:
            out = bytearray(256)
            struct.pack_into(
                "<4sII4xQQ", out, 0, b"XYGZ", 1, 2 if failures == 0 else 0, page.handle, 0
            )
            if failures == 1:
                out[48] = 1
            failures += 1
            return bytes(out)
        return actual(packet)

    try:
        monkeypatch.setattr(token, "native_execute", execute)
        with pytest.raises(ValueError, match="settlement"):
            page.close()
        with pytest.raises(ValueError, match="reserved"):
            page.close()
        assert members.reply(actual(members.request(6, page.handle, page.sequence)))["code"] == 0
        page.close()
        assert failures == 2
    finally:
        monkeypatch.setattr(token, "native_execute", actual)
        page.close()
        frame.close()
        index.close()
        seed.close()
        source.close()
