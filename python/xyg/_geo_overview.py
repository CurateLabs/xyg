"""Internal typed transport for Rust's nonfinal data-domain temporal overview."""

from __future__ import annotations

import asyncio
import math
import struct
import traceback
import weakref
from contextlib import suppress

from . import _geoscale as scale

COMMANDS = (6, 7, 8, 9, 10, 23, 26, 27, 28, 29, 30, 31)


class GeoOverviewUnsupportedSelected(RuntimeError):
    """The temporal index cannot retain sparse selected-frame authority."""


def builder_request(frame, *, budget, max_vertices):
    """Internal frame-aware ingress; raw numeric framing cannot inspect intent."""
    if frame.data.selection is not None:
        raise GeoOverviewUnsupportedSelected("Temporal overview does not retain selected authority")
    sequence = frame.data.identity["sequence"]
    if not scale._uint(max_vertices):
        raise ValueError("nonzero u64 overview vertex ceiling required")
    return request(
        27,
        frame.handle,
        sequence,
        budget=budget,
        payload=struct.pack("<Q", max_vertices),
    )


def request(command, handle, sequence, *, budget=None, query=None, payload=b""):
    """Frame shared headers; Rust owns all temporal and geometry decisions."""
    if command not in COMMANDS or (query is not None and command != 28):
        raise ValueError("invalid overview command/query")
    if command == 28 and (
        query is None
        or query["reduced_kind"] != 0
        or query["max_cells"] != 0
        or query["previous_direct"] is not False
        or query["max_projected_vertices"] != 0
    ):
        raise ValueError("overview requires explicit data-domain framing")
    fields = dict(command=5 if command == 28 else 6, handle=handle, sequence=sequence)
    if budget is not None:
        fields["budget"] = budget
    if query is not None:
        fields["query"] = query
    fields["payload"] = payload
    out = bytearray(scale.encode_request(fields))
    struct.pack_into("<I", out, 8, scale._uint(command, 32))
    return bytes(out)


def reply(packet):
    b = scale._bytes(packet)
    if len(b) != 256 or struct.unpack_from("<4sI", b) != (b"XYGZ", 1):
        raise ValueError("fixed overview reply required")
    code = struct.unpack_from("<I", b, 8)[0]
    if code not in (0, 1, 2, 7, 9, 13, 14, 15, 16, 17):
        raise ValueError("invalid overview reply")
    scale._zero(b, 12, 16)
    scale._zero(b, 192, 256)
    ticket = None
    if code in (1, 7) or (code == 2 and any(b[64:192])):
        raw = bytes(b[64:192])
        kind = struct.unpack_from("<I", raw, 32)[0]
        length = struct.unpack_from("<Q", raw, 48)[0]
        scale._zero(memoryview(raw), 36, 40)
        scale._zero(memoryview(raw), 104, 128)
        if (
            kind not in (1, 2, 3)
            or not 64 <= length <= (16 << 20 if kind == 1 else 65536)
            or (code == 7 and kind != 3)
            or (code == 1 and kind == 3)
        ):
            raise ValueError("invalid overview ticket")
        if kind != 1:
            scale._zero(memoryview(raw), 64, 104)
        ticket = dict(
            raw=raw,
            owner=struct.unpack_from("<Q", raw, 0)[0],
            namespace=struct.unpack_from("<Q", raw, 8)[0],
            page=struct.unpack_from("<Q", raw, 40)[0],
            kind=kind,
            encoded_bytes=length,
            chunk_index=struct.unpack_from("<I", raw, 72)[0],
        )
    else:
        scale._zero(b, 64, 192)
    handle, sequence, length, source_handle = struct.unpack_from("<4Q", b, 16)
    return dict(
        code=code,
        handle=handle,
        sequence=sequence,
        data_length=length,
        source_handle=source_handle,
        ticket=ticket,
    )


class OverviewData:
    """Borrowed, bounded counts/Scene; no source feature IDs or finality claim."""

    temporal_exact = True
    data_space = True
    final = False
    resolution = 16

    def __init__(self, packet):
        b = scale._bytes(packet)
        if not 2464 <= len(b) <= scale.MAX_PACKET or scale._backing_bytes(b) != len(b):
            raise ValueError("exact bounded overview storage required")
        if struct.unpack_from("<4s3I", b) != (b"XYOV", 1, 3, 16):
            raise ValueError("invalid nonfinal overview tier")

        def u64(at):
            return struct.unpack_from("<Q", b, at)[0]

        def u32(at):
            return struct.unpack_from("<I", b, at)[0]

        if u64(40) != 2048 or u64(32) != len(b) - 2304:
            raise ValueError("overview plane length mismatch")
        for start, end in ((104, 112), (168, 176), (216, 224), (228, 232), (248, 256)):
            scale._zero(b, start, end)
        if struct.unpack_from("<4sI", b, 2304) != (b"XYGS", 32):
            raise ValueError("invalid overview Scene32")
        if (
            u32(72) not in (4326, 3857)
            or u32(76) not in (1, 4)
            or u32(96) not in (4326, 3857)
            or u32(100) > 1
        ):
            raise ValueError("invalid overview CRS/geometry")
        camera = struct.unpack_from("<7d", b, 112)
        if not all(map(math.isfinite, camera)) or camera[3] <= 0 or camera[4] <= 0:
            raise ValueError("invalid overview camera")
        kind = u32(224)
        start, end = struct.unpack_from("<2q", b, 232)
        if (
            kind not in (0, 1, 2)
            or (kind == 0 and (start or end))
            or (kind == 1 and end)
            or (kind == 2 and start >= end)
            or not u64(16)
            or not u64(24)
        ):
            raise ValueError("invalid overview time/publication")
        total = sum(struct.unpack_from("<256Q", b, 256))
        if total > (1 << 64) - 1 or (u64(88) == 0 and total) or (u32(76) == 1 and total > u64(88)):
            raise ValueError("invalid overview source population")
        self.packet, self.scene = b, b[2304:]
        self.identity = dict(
            query_handle=u64(16),
            sequence=u64(24),
            overview_digest=bytes(b[48:56]),
            generation=u64(56),
            source_digest=bytes(b[64:72]),
            source_crs=u32(72),
            geometry=u32(76),
            layer_id=u64(80),
            source_rows=u64(88),
            camera=dict(
                crs=u32(96),
                world_wrap=bool(u32(100)),
                **dict(
                    zip(
                        ("center_x", "center_y", "zoom", "width", "height", "bearing", "pitch"),
                        camera,
                        strict=True,
                    )
                ),
            ),
            **dict(
                zip(
                    (
                        "camera_revision",
                        "time_revision",
                        "layer_revision",
                        "style_revision",
                        "state_revision",
                    ),
                    struct.unpack_from("<5Q", b, 176),
                    strict=True,
                )
            ),
            time=(
                dict(kind=0)
                if kind == 0
                else dict(kind=1, instant=start)
                if kind == 1
                else dict(kind=2, start=start, end=end)
            ),
        )

    def count(self, cell):
        if isinstance(cell, bool) or not isinstance(cell, int) or not 0 <= cell < 256:
            raise ValueError("domain cell must be 0..255")
        return struct.unpack_from("<Q", self.packet, 256 + cell * 8)[0]


def validate_mutation(raw, handle, sequence):
    receipt = reply(raw)
    if any(scale._bytes(raw)[32:256]):
        raise ValueError("nonzero overview mutation reserved bytes")
    if (
        receipt["code"] != 0
        or receipt["handle"] != handle
        or receipt["sequence"] != sequence
        or receipt["ticket"] is not None
        or receipt["data_length"] != 0
        or receipt["source_handle"] != 0
    ):
        raise ValueError("Overview mutation did not confirm settlement")
    return receipt


_PENDING_LOANS = weakref.WeakKeyDictionary()


async def settle_loan(bridge, handle, sequence):
    loans = _PENDING_LOANS.get(bridge)
    authority = loans.get((handle, sequence)) if loans is not None else None
    if authority is None:
        return
    command, ticket = authority
    try:
        raw, interrupted = await scale._settle(
            asyncio.create_task(bridge.execute(request(command, handle, sequence, payload=ticket)))
        )
        validate_mutation(raw, handle, sequence)
    except BaseException:
        raw, interrupted = await scale._settle(
            asyncio.create_task(bridge.execute(request(9, handle, sequence)))
        )
        validate_mutation(raw, handle, sequence)
        raw, interrupted = await scale._settle(
            asyncio.create_task(bridge.execute(request(6, handle, sequence)))
        )
        terminal = reply(raw)
        if terminal["code"] == 9 and any(scale._bytes(raw)[32:256]):
            raise ValueError("nonzero overview cancellation reserved bytes") from None
        if (
            terminal["code"] != 9
            or terminal["handle"] != handle
            or terminal["sequence"] != sequence
            or terminal["ticket"] is not None
        ):
            raise ValueError("Overview loan settlement remains pending") from None
    assert loans is not None
    del loans[handle, sequence]
    if interrupted:
        raise asyncio.CancelledError


async def drive(
    bridge,
    *,
    handle,
    sequence,
    budget,
    read_chunk,
    read_page,
    write_page,
    cancel_event=None,
):
    """Keep private tickets and charges until callbacks/transport settle and ACK."""
    cancellation = None

    def encode(command, payload=b""):
        return request(command, handle, sequence, budget=budget, payload=payload)

    def cancel_now():
        nonlocal cancellation
        if cancellation is None:
            cancellation = asyncio.create_task(bridge.execute(encode(9)))
        return cancellation

    async def cancel():
        raw, _ = await scale._settle(cancel_now())
        validate_mutation(raw, handle, sequence)

    def aborted(interrupted=False):
        return interrupted or (cancel_event is not None and cancel_event.is_set())

    async def watch():
        assert cancel_event is not None
        await cancel_event.wait()
        await cancel()

    watcher = asyncio.create_task(watch()) if cancel_event is not None else None
    try:
        await settle_loan(bridge, handle, sequence)
        while True:
            if aborted():
                await cancel()
                raise asyncio.CancelledError
            operation = asyncio.create_task(bridge.execute(encode(6)))
            raw, interrupted = await scale._settle(operation, cancel_now)
            operation = None
            step = reply(raw)
            raw = None
            if step["handle"] != handle or step["sequence"] != sequence:
                raise ValueError("mismatched overview operation")
            if step["code"] in (13, 14, 15):
                if aborted(interrupted):
                    await cancel()
                    raise asyncio.CancelledError
                return step
            if step["code"] not in (1, 7) or step["ticket"] is None:
                if aborted(interrupted):
                    await cancel()
                    raise asyncio.CancelledError
                raise ValueError("overview did not complete")
            private = step["ticket"]
            authority, kind, length = private["raw"], private["kind"], private["encoded_bytes"]
            _PENDING_LOANS.setdefault(bridge, {})[handle, sequence] = (
                31 if kind == 3 else 8,
                bytes(authority),
            )
            borrowed = view = payload = supply = operation = None
            try:
                if aborted(interrupted):
                    await cancel()
                    raise asyncio.CancelledError
                if 4 * (256 + 128 + length) > budget["processor_bytes"]:
                    raise ValueError("overview transfer exceeds budget")
                operation = asyncio.create_task(
                    bridge.read(encode(30, authority))
                    if kind == 3
                    else (read_chunk if kind == 1 else read_page)(dict(private))
                )
                borrowed, interrupted = await scale._settle(operation, cancel_now)
                operation = None
                view = scale._bytes(borrowed)
                if len(view) != length or scale._backing_bytes(view) != length:
                    raise ValueError("callback must return exact owning overview storage")
                if aborted(interrupted):
                    await cancel()
                    raise asyncio.CancelledError
                if kind == 3:
                    operation = asyncio.create_task(write_page(dict(private), view))
                else:
                    payload = bytearray(128 + length)
                    payload[:128], payload[128:] = authority, view
                    supply = encode(7, payload)
                    payload = None
                    operation = asyncio.create_task(bridge.execute(supply))
                response, interrupted = await scale._settle(operation, cancel_now)
                if kind != 3:
                    validate_mutation(response, handle, sequence)
                response = operation = None
                if aborted(interrupted):
                    await cancel()
                    raise asyncio.CancelledError
            except BaseException as error:
                borrowed = view = payload = supply = operation = None
                traceback.clear_frames(error.__traceback__)
                with suppress(Exception):
                    await cancel()
                raise
            finally:
                borrowed = view = payload = supply = operation = None
                try:
                    if cancellation is not None:
                        await scale._settle(cancellation)
                finally:
                    await settle_loan(bridge, handle, sequence)
    except BaseException:
        with suppress(Exception):
            await cancel()
        raise
    finally:
        if watcher is not None:
            if not watcher.done():
                watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
        if cancellation is not None:
            _, interrupted = await scale._settle(cancellation)
            if interrupted:
                raise asyncio.CancelledError


class OverviewLease:
    def __init__(self, bridge, handle, data):
        self._bridge, self.handle, self._data = bridge, handle, data
        self._disposal = None

    @property
    def data(self):
        if self._data is None:
            raise RuntimeError("overview Data disposed")
        return self._data

    async def dispose(self):
        self._data = None
        if self._disposal is None:
            self._disposal = asyncio.create_task(self._bridge.execute(request(10, self.handle, 0)))
        task = self._disposal
        try:
            raw, interrupted = await scale._settle(task)
            validate_mutation(raw, self.handle, 0)
        except BaseException:
            if task.done():
                self._disposal = None
            raise
        if interrupted:
            raise asyncio.CancelledError


async def prepare_data(bridge, *, handle, sequence, budget):
    """Read exactly one immutable owner; cancellation disposes unreturned Data."""
    operation = asyncio.create_task(bridge.execute(request(29, handle, sequence, budget=budget)))
    raw, interrupted = await scale._settle(operation)
    operation = None
    receipt = reply(raw)
    owner = OverviewLease(bridge, receipt["handle"], None)
    packet = data = None
    try:
        if interrupted:
            raise asyncio.CancelledError
        if (
            receipt["code"] != 16
            or receipt["source_handle"] != handle
            or receipt["sequence"] != sequence
            or receipt["data_length"] > scale.MAX_PACKET
            or 4 * receipt["data_length"] > budget["processor_bytes"]
        ):
            raise ValueError("invalid overview Data receipt")
        operation = asyncio.create_task(bridge.read(request(23, owner.handle, sequence)))
        packet, interrupted = await scale._settle(operation)
        operation = None
        if interrupted:
            raise asyncio.CancelledError
        if len(packet) != receipt["data_length"]:
            raise ValueError("overview Data length mismatch")
        data = OverviewData(packet)
        if data.identity["query_handle"] != handle or data.identity["sequence"] != sequence:
            raise ValueError("overview Data identity mismatch")
        owner._data = data
        return owner
    except BaseException as error:
        packet = data = operation = None
        traceback.clear_frames(error.__traceback__)
        await owner.dispose()
        raise
