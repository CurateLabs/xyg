"""Actual native overview transport: temporal truth, private loans and cleanup."""

import asyncio
import struct

import pytest

from test_geoscale import BUDGET, I64, U64, query, source_fixture
from xyg import _geo_overview as overview
from xyg import _geoscale as scale


class Fixture:
    def __init__(self):
        self.bridge = scale.NativeGeoScaleBridge(BUDGET["processor_bytes"])
        self.handles = []
        self.sequences = {}
        self.pages = {}

    def close(self, handle):
        scale.execute(overview.request(10, handle, self.sequences.get(handle, 0)))
        self.handles.remove(handle)

    async def initialize(self):
        _, self.chunk = source_fixture()
        builder = scale.decode_reply(scale.execute(scale.encode_request(dict(command=1))))["handle"]
        self.handles.append(builder)
        scale.execute(scale.encode_request(dict(command=2, handle=builder, payload=self.chunk)))
        scale.execute(scale.encode_request(dict(command=3, handle=builder, generation=U64)))
        manifest = scale.read(scale.encode_request(dict(command=21, handle=builder)), 128 << 20)
        source = scale.decode_reply(
            scale.execute(scale.encode_request(dict(command=4, budget=BUDGET, payload=manifest)))
        )["handle"]
        self.handles.append(source)
        info = (
            await scale.drive_session(
                self.bridge, handle=source, sequence=0, budget=BUDGET, read_chunk=self.read_chunk
            )
        )["source"]
        self.query = query(info)
        scale.execute(
            scale.encode_request(
                dict(command=5, handle=source, sequence=1, budget=BUDGET, query=self.query)
            )
        )
        await scale.drive_session(
            self.bridge, handle=source, sequence=1, budget=BUDGET, read_chunk=self.read_chunk
        )
        frame = await scale.prepare_scene_data(
            self.bridge,
            handle=source,
            sequence=1,
            budget=BUDGET,
            style=scale.encode_style(
                dict(
                    fill=b"\xff\0\0\xff",
                    stroke=bytes(4),
                    stroke_width=0.0,
                    diameter=6.0,
                    opacity=1.0,
                    symbol=0,
                )
            ),
        )
        self.index = overview.reply(
            await self.bridge.execute(
                overview.request(
                    27, frame.handle, 1, budget=BUDGET, payload=struct.pack("<Q", 1000)
                )
            )
        )["handle"]
        self.handles.append(self.index)
        self.sequences[self.index] = 1
        await frame.dispose()
        self.close(source)
        self.close(builder)

    async def read_chunk(self, _ticket):
        return self.chunk

    async def read_page(self, ticket):
        key = ticket["namespace"], ticket["page"]
        value = self.pages[key]
        ticket.update(raw=bytes(128), encoded_bytes=1, namespace=0, kind=99)
        return value

    async def write_page(self, ticket, view):
        self.pages[ticket["namespace"], ticket["page"]] = bytes(view)
        ticket.update(raw=bytes(128), encoded_bytes=1, namespace=0, kind=99)

    async def drive(self, handle, sequence, **kwargs):
        return await overview.drive(
            self.bridge,
            handle=handle,
            sequence=sequence,
            budget=BUDGET,
            read_chunk=self.read_chunk,
            read_page=self.read_page,
            write_page=self.write_page,
            **kwargs,
        )

    async def begin(self, sequence, time):
        q = dict(
            self.query, time=time, max_cells=0, previous_direct=False, max_projected_vertices=0
        )
        handle = overview.reply(
            await self.bridge.execute(
                overview.request(28, self.index, sequence, budget=BUDGET, query=q)
            )
        )["handle"]
        self.handles.append(handle)
        self.sequences[handle] = sequence
        return handle

    async def dispose(self):
        for handle in self.handles[:]:
            self.close(handle)


def test_actual_temporal_counts_immutable_owners_and_retry_recovers_eight_data_quota():
    async def run():
        f = Fixture()
        owners = []
        try:
            await f.initialize()
            assert (await f.drive(f.index, 1))["code"] == 13
            times = [
                dict(kind=0),
                dict(kind=1, instant=I64),
                dict(kind=1, instant=0),
                dict(kind=1, instant=U64 >> 1),
                dict(kind=2, start=I64, end=I64 + 1),
                dict(kind=2, start=0, end=1),
                dict(kind=2, start=I64, end=U64 >> 1),
                dict(kind=1, instant=(U64 >> 1) - 1),
            ]

            class RetryBridge:
                failed = False
                attempts = 0

                async def execute(self, packet):
                    if struct.unpack_from("<I", packet, 8)[0] == 10:
                        self.attempts += 1
                        if not self.failed:
                            self.failed = True
                            raise RuntimeError("transient overview disposal rejection")
                    return await f.bridge.execute(packet)

                async def read(self, packet):
                    return await f.bridge.read(packet)

            retry = RetryBridge()
            for i, time in enumerate(times):
                sequence = i + 2
                handle = await f.begin(sequence, time)
                assert (await f.drive(handle, sequence))["code"] == 14
                owner = await overview.prepare_data(
                    retry if i == 0 else f.bridge, handle=handle, sequence=sequence, budget=BUDGET
                )
                owners.append(owner)
                data = owner.data
                assert (data.temporal_exact, data.data_space, data.final) == (True, True, False)
                assert data.identity["generation"] == U64
                assert data.identity["layer_id"] == U64
                assert data.identity["time"] == time
                assert sum(data.count(c) for c in range(256)) == (0 if i == 3 else 2)
                for at, value in (
                    (0, 0),
                    (4, 2),
                    (8, 7),
                    (12, 32),
                    (40, 0),
                    (104, 1),
                    (224, 3),
                    (2308, 99),
                ):
                    bad = bytearray(data.packet)
                    struct.pack_into("<I", bad, at, value)
                    with pytest.raises(ValueError):
                        overview.OverviewData(bad)
                with pytest.raises(ValueError):
                    overview.OverviewData(bytes(data.packet[:-1]))
                with pytest.raises(ValueError):
                    data.count(True)
                data = None
                f.close(handle)
            extra = await f.begin(100, dict(kind=0))
            await f.drive(extra, 100)
            with pytest.raises(ValueError):
                await overview.prepare_data(f.bridge, handle=extra, sequence=100, budget=BUDGET)
            with pytest.raises(RuntimeError, match="transient"):
                await owners[0].dispose()
            with pytest.raises(RuntimeError, match="disposed"):
                _ = owners[0].data
            with pytest.raises(ValueError):
                await overview.prepare_data(f.bridge, handle=extra, sequence=100, budget=BUDGET)
            await owners[0].dispose()
            await owners[0].dispose()
            assert retry.attempts == 2
            owners.append(
                await overview.prepare_data(f.bridge, handle=extra, sequence=100, budget=BUDGET)
            )
            f.close(extra)
            f.close(f.index)
            for owner in owners[1:]:
                # A second real copy survives all query/source/index disposal.
                sequence = owner.data.identity["sequence"]
                assert scale.read(overview.request(23, owner.handle, sequence), 128 << 20)
                with pytest.raises(ValueError):
                    scale.read(overview.request(23, owner.handle, sequence), 128 << 20)
        finally:
            for owner in owners:
                await owner.dispose()
            await f.dispose()

    asyncio.run(run())


@pytest.mark.parametrize("write", [False, True])
def test_actual_cancelled_read_or_write_settles_before_exact_ack(write):
    async def run():
        f = Fixture()
        try:
            await f.initialize()
            if write:
                handle, sequence = f.index, 1
            else:
                await f.drive(f.index, 1)
                sequence = 2
                handle = await f.begin(sequence, dict(kind=1, instant=0))
            entered, gate, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
            settled = acked = False

            async def held_read(ticket):
                nonlocal settled
                value = f.pages[ticket["namespace"], ticket["page"]]
                entered.set()
                await gate.wait()
                settled = True
                return value

            async def held_write(ticket, value):
                nonlocal settled
                entered.set()
                await gate.wait()
                f.pages[ticket["namespace"], ticket["page"]] = bytes(value)
                settled = True

            class Guarded:
                async def execute(self, packet):
                    nonlocal acked
                    cmd = struct.unpack_from("<I", packet, 8)[0]
                    if cmd == (31 if write else 8):
                        assert settled
                        acked = True
                    return await f.bridge.execute(packet)

                async def read(self, packet):
                    return await f.bridge.read(packet)

            task = asyncio.create_task(
                overview.drive(
                    Guarded(),
                    handle=handle,
                    sequence=sequence,
                    budget=BUDGET,
                    read_chunk=f.read_chunk,
                    read_page=held_read,
                    write_page=held_write,
                    cancel_event=cancelled,
                )
            )
            await entered.wait()
            cancelled.set()
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            assert (
                overview.reply(await f.bridge.execute(overview.request(10, handle, sequence)))[
                    "code"
                ]
                == 2
            )
            assert not acked
            gate.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert acked
        finally:
            await f.dispose()

    asyncio.run(run())


def test_actual_abort_during_delayed_terminal_reply_rejects_success():
    async def run():
        f = Fixture()
        try:
            await f.initialize()
            await f.drive(f.index, 1)
            handle = await f.begin(2, dict(kind=0))
            await f.drive(handle, 2)
            entered, gate, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()

            class Delayed:
                async def execute(self, packet):
                    result = await f.bridge.execute(packet)
                    if struct.unpack_from("<I", packet, 8)[0] == 6:
                        assert overview.reply(result)["code"] == 14
                        entered.set()
                        await gate.wait()
                    return result

                async def read(self, packet):
                    raise AssertionError("terminal must not read")

            task = asyncio.create_task(
                overview.drive(
                    Delayed(),
                    handle=handle,
                    sequence=2,
                    budget=BUDGET,
                    read_chunk=f.read_chunk,
                    read_page=f.read_page,
                    write_page=f.write_page,
                    cancel_event=cancelled,
                )
            )
            await entered.wait()
            cancelled.set()
            gate.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            await f.dispose()

    asyncio.run(run())


@pytest.mark.parametrize("phase", ["receipt", "read"])
def test_actual_prepare_data_cancellation_disposes_unreturned_owner(phase):
    async def run():
        f = Fixture()
        entered, gate = asyncio.Event(), asyncio.Event()
        holder = {}
        try:
            await f.initialize()
            await f.drive(f.index, 1)
            handle = await f.begin(70, dict(kind=0))
            await f.drive(handle, 70)

            class HeldBridge:
                async def execute(self, packet):
                    result = await f.bridge.execute(packet)
                    if struct.unpack_from("<I", packet, 8)[0] == 29:
                        holder["handle"] = overview.reply(result)["handle"]
                        if phase == "receipt":
                            entered.set()
                            await gate.wait()
                    return result

                async def read(self, packet):
                    result = await f.bridge.read(packet)
                    if phase == "read":
                        entered.set()
                        await gate.wait()
                    return result

            task = asyncio.create_task(
                overview.prepare_data(HeldBridge(), handle=handle, sequence=70, budget=BUDGET)
            )
            await entered.wait()
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            assert not task.done()
            gate.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            with pytest.raises(ValueError):
                scale.read(overview.request(23, holder["handle"], 70), 128 << 20)
            owner = await overview.prepare_data(f.bridge, handle=handle, sequence=70, budget=BUDGET)
            await owner.dispose()
        finally:
            gate.set()
            await f.dispose()

    asyncio.run(run())
