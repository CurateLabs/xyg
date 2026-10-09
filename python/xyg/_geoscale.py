"""Thin binary adapters for Rust-owned retained geographic sources and sessions.

This internal module exposes framing and lifecycle helpers, not a chart API.
SceneData views/copies and painters must be dropped before disposing their lease.
"""

from __future__ import annotations

import asyncio
import ctypes
import struct
import traceback
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any, Protocol

import numpy as np

HEADER = 256
MAX_PACKET = 32 * 1024 * 1024
MAX_PROCESSOR = 128 * 1024 * 1024


def _uint(value: int, bits: int = 64) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, np.integer))
        or not 0 <= value < 1 << bits
    ):
        raise TypeError(f"expected u{bits}")
    return int(value)


def _i64(value: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, np.integer))
        or not -(1 << 63) <= value < 1 << 63
    ):
        raise TypeError("expected i64")
    return int(value)


def _budget(value: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not HEADER <= value <= MAX_PROCESSOR
    ):
        raise ValueError("invalid processor budget")
    return value


def _bytes(value: bytes | bytearray | memoryview) -> memoryview:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise TypeError("expected raw bytes")
    view = memoryview(value)
    if not view.c_contiguous:
        raise TypeError("bytes must be contiguous")
    return view.cast("B")


def _backing_bytes(view: memoryview) -> int:
    value = view.obj
    while isinstance(value, memoryview) or (
        isinstance(value, np.ndarray) and value.base is not None
    ):
        value = value.obj if isinstance(value, memoryview) else value.base
    if value is None:
        raise TypeError("read storage has no owning buffer")
    return memoryview(value).nbytes


def encode_request(input: dict[str, Any]) -> bytes:
    """Frame one fixed-header request; Rust validates every product decision."""
    command = _uint(input["command"], 32)
    if command not in (*range(1, 15), 20, 21, 23):
        raise ValueError("unknown geographic command")
    payload = _bytes(input.get("payload", b""))
    length = HEADER + len(payload)
    budget = input.get("budget")
    if length > MAX_PACKET or (budget and length > _budget(budget["processor_bytes"])):
        raise ValueError("request exceeds framing budget")
    if (
        ("query" in input and command != 5)
        or ("generation" in input and command != 3)
        or ("sequence" in input and command not in (5, 6, 9, 11, 12, 13, 14))
    ):
        raise ValueError("field does not belong to command")
    out = bytearray(length)
    struct.pack_into("<4sII", out, 0, b"XYGQ", 1, command)
    struct.pack_into("<QQ", out, 16, _uint(input.get("handle", 0)), _uint(input.get("sequence", 0)))
    if budget is not None:
        struct.pack_into(
            "<QQQII",
            out,
            32,
            _budget(budget["processor_bytes"]),
            _uint(budget["max_rows_examined"]),
            _uint(budget["max_read_bytes"]),
            _uint(budget["max_chunks"], 32),
            _uint(budget["page_rows"], 32),
        )
    if command == 3:
        struct.pack_into("<Q", out, 144, _uint(input.get("generation", 0)))
    if command == 5:
        query = input["query"]
        camera = query["camera"]
        if not isinstance(camera["world_wrap"], bool) or not isinstance(
            query["previous_direct"], bool
        ):
            raise TypeError("query flags must be explicit booleans")
        digest = _bytes(query["source_digest"])
        if len(digest) != 8:
            raise ValueError("source digest must have eight bytes")
        struct.pack_into("<I", out, 12, camera["world_wrap"])
        struct.pack_into(
            "<4I",
            out,
            64,
            _uint(camera["crs"], 32),
            _uint(query["reduced_kind"], 32),
            _uint(query["max_cells"], 32),
            query["previous_direct"],
        )
        struct.pack_into(
            "<7d",
            out,
            80,
            *(
                camera[k]
                for k in ("center_x", "center_y", "zoom", "width", "height", "bearing", "pitch")
            ),
        )
        out[136:144] = digest
        struct.pack_into(
            "<7Q",
            out,
            144,
            *(
                _uint(query[k])
                for k in (
                    "generation",
                    "layer_id",
                    "camera_revision",
                    "time_revision",
                    "layer_revision",
                    "style_revision",
                    "state_revision",
                )
            ),
        )
        time = query["time"]
        kind = _uint(time["kind"], 32)
        if kind not in (0, 1, 2):
            raise ValueError("unknown time predicate")
        struct.pack_into("<I", out, 200, kind)
        if kind == 1:
            struct.pack_into("<q", out, 208, _i64(time["instant"]))
        elif kind == 2:
            struct.pack_into("<qq", out, 208, _i64(time["start"]), _i64(time["end"]))
        struct.pack_into("<Q", out, 224, _uint(query["max_projected_vertices"]))
    struct.pack_into("<Q", out, 232, len(payload))
    out[HEADER:] = payload
    return bytes(out)


def encode_style(style: dict[str, Any]) -> bytes:
    out = bytearray(48)
    for name, at in (("fill", 0), ("stroke", 4)):
        paint = _bytes(style[name])
        if len(paint) != 4:
            raise ValueError("paint must be RGBA8")
        out[at : at + 4] = paint
    struct.pack_into("<3d", out, 8, style["stroke_width"], style["diameter"], style["opacity"])
    out[32] = _uint(style["symbol"], 8)
    return bytes(out)


def _reply(data: bytes | bytearray | memoryview) -> memoryview:
    b = _bytes(data)
    if (
        not HEADER <= len(b) <= MAX_PACKET
        or bytes(b[:4]) != b"XYGZ"
        or struct.unpack_from("<I", b, 4)[0] != 1
    ):
        raise ValueError("invalid geographic reply")
    return b


def _zero(data: memoryview, start: int, end: int) -> None:
    if any(data[start:end]):
        raise ValueError("nonzero reserved bytes")


def _ticket(data: memoryview) -> dict[str, Any]:
    _zero(data, 28, 32)
    _zero(data, 72, 96)
    session_id, read_id, sequence, pass_ = struct.unpack_from("<QQQI", data)
    generation, chunk_index, rows, first_row, encoded_bytes = struct.unpack_from("<QIIQQ", data, 32)
    if encoded_bytes > 16 * 1024 * 1024:
        raise ValueError("read ticket exceeds framing")
    return dict(
        raw=data,
        session_id=session_id,
        read_id=read_id,
        sequence=sequence,
        pass_=pass_,
        generation=generation,
        chunk_index=chunk_index,
        rows=rows,
        first_row=first_row,
        encoded_bytes=encoded_bytes,
        digest=data[64:72],
    )


def decode_reply(data: bytes | bytearray | memoryview) -> dict[str, Any]:
    b = _reply(data)
    code = struct.unpack_from("<I", b, 8)[0]
    if len(b) != HEADER or code > 6:
        raise ValueError("mutation reply must be fixed size")
    _zero(b, 12, 16)
    if code == 4:
        if struct.unpack_from("<Q", b, 160)[0] > 4096 or struct.unpack_from("<I", b, 168)[0] > 1:
            raise ValueError("invalid membership reply")
        _zero(b, 176, 256)
    else:
        _zero(b, 160, 256)
    handle, sequence, data_length, source_handle, source_rows = struct.unpack_from("<5Q", b, 16)
    geometry, crs = struct.unpack_from("<II", b, 56)
    return dict(
        code=code,
        handle=handle,
        sequence=sequence,
        data_length=data_length,
        source_handle=source_handle,
        source=dict(
            generation=data_length, digest=b[40:48], rows=source_rows, geometry=geometry, crs=crs
        ),
        ticket=_ticket(b[64:160]) if code in (1, 2) else None,
    )


def encode_chunk_request(input: dict[str, Any], budget: int) -> bytes:
    """Encode exact XYGD/i64/f64 planes for Rust's canonical XYGK encoder."""
    _budget(budget)
    descriptor, rows = _bytes(input["descriptor"]), _uint(input["rows"], 32)
    if rows > 65536:
        raise ValueError("chunk row count exceeds framing")
    intervals, values = input.get("intervals"), input.get("values")
    planes = []
    if intervals is not None:
        planes.extend(
            (intervals[name], dtype)
            for name, dtype in (
                ("starts", "<i8"),
                ("ends", "<i8"),
                ("start_validity", "u1"),
                ("end_validity", "u1"),
            )
        )
    if values is not None:
        planes.append((values, "<f8"))
    for plane, dtype in planes:
        if (
            not isinstance(plane, np.ndarray)
            or plane.ndim != 1
            or plane.dtype != np.dtype(dtype)
            or not plane.flags.c_contiguous
            or len(plane) != rows
        ):
            raise TypeError("chunk requires exact contiguous typed planes")
    size = (
        32
        + len(descriptor)
        + rows * ((18 if intervals is not None else 0) + (8 if values is not None else 0))
    )
    if size > 16 * 1024 * 1024 or 6 * size + 32768 + HEADER > budget:
        raise ValueError("chunk exceeds peak framing budget")
    payload = bytearray(size)
    struct.pack_into(
        "<QI",
        payload,
        0,
        len(descriptor),
        (1 if intervals is not None else 0) | (2 if values is not None else 0),
    )
    struct.pack_into("<Q", payload, 16, rows)
    payload[32 : 32 + len(descriptor)] = descriptor
    at = 32 + len(descriptor)
    for plane, _ in planes:
        payload[at : at + plane.nbytes] = memoryview(plane).cast("B")
        at += plane.nbytes
    return encode_request(dict(command=20, payload=payload))


class SceneData:
    """Borrowed binary views of a Rust Scene plus exact direct/reduced metadata."""

    def __init__(self, packet: bytes | bytearray | memoryview) -> None:
        b = _reply(packet)
        aggregate, self.dropped_channels = struct.unpack_from("<II", b, 8)
        (
            session_handle,
            sequence,
            scene_len,
            metadata_len,
            self.visible_vertices,
            self.projected_vertices,
        ) = struct.unpack_from("<6Q", b, 16)
        self.columns, self.rows, capped = struct.unpack_from("<III", b, 64)
        time_kind, reduced_kind = struct.unpack_from("<II", b, 208)
        if (
            aggregate > 1
            or capped > 1
            or time_kind > 2
            or reduced_kind > 1
            or self.dropped_channels & ~7
            or HEADER + scene_len + metadata_len != len(b)
            or scene_len < 160
        ):
            raise ValueError("malformed SceneData framing")
        _zero(b, 76, 80)
        _zero(b, 248, 256)
        self.packet, self.scene = b, b[HEADER : HEADER + scene_len]
        if bytes(self.scene[:4]) != b"XYGS" or struct.unpack_from("<I", self.scene, 4)[0] != 32:
            raise ValueError("invalid Scene32 packet")
        self.aggregate, self.grid_capped = bool(aggregate), bool(capped)
        self._stride = 24 if aggregate else 40
        self.metadata = b[HEADER + scene_len :]
        self.length = metadata_len // self._stride
        if metadata_len % self._stride or (aggregate and self.columns * self.rows != self.length):
            raise ValueError("invalid provenance framing")
        for i in range(self.length):
            at = i * self._stride
            if aggregate:
                if not all(
                    np.isfinite(x) for x in struct.unpack_from("<dd", self.metadata, at + 8)
                ):
                    raise ValueError("invalid reduced coordinates")
            else:
                _zero(self.metadata, at + 28, at + 40)
        crs, wrap = struct.unpack_from("<II", b, 80)
        camera_values = struct.unpack_from("<7d", b, 88)
        geometry, source_crs = struct.unpack_from("<II", b, 240)
        if (
            crs not in (4326, 3857)
            or source_crs not in (4326, 3857)
            or wrap > 1
            or not all(np.isfinite(x) for x in camera_values)
        ):
            raise ValueError("invalid camera/source framing")
        if time_kind == 0:
            _zero(b, 216, 232)
            time = dict(kind=0)
        elif time_kind == 1:
            _zero(b, 224, 232)
            time = dict(kind=1, instant=struct.unpack_from("<q", b, 216)[0])
        else:
            start, end = struct.unpack_from("<qq", b, 216)
            time = dict(kind=2, start=start, end=end)
        camera = dict(
            zip(
                ("center_x", "center_y", "zoom", "width", "height", "bearing", "pitch"),
                camera_values,
                strict=True,
            ),
            crs=crs,
            world_wrap=bool(wrap),
        )
        self.identity = dict(
            session_handle=session_handle,
            sequence=sequence,
            camera=camera,
            source_digest=b[144:152],
            time=time,
            reduced_kind=reduced_kind,
            source_rows=struct.unpack_from("<Q", b, 232)[0],
            geometry=geometry,
            source_crs=source_crs,
        )
        self.identity.update(
            zip(
                (
                    "generation",
                    "layer_id",
                    "camera_revision",
                    "time_revision",
                    "layer_revision",
                    "style_revision",
                    "state_revision",
                ),
                struct.unpack_from("<7Q", b, 152),
                strict=True,
            )
        )

    def record(self, index: int) -> dict[str, Any]:
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < self.length:
            raise IndexError("provenance index")
        at = index * self._stride
        if self.aggregate:
            count, x, y = struct.unpack_from("<Qdd", self.metadata, at)
            return dict(count=count, x=x, y=y)
        feature_id, source_row, chunk_index, chunk_row, vertex = struct.unpack_from(
            "<QQIII", self.metadata, at
        )
        return dict(
            feature_id=feature_id,
            source_row=source_row,
            chunk_index=chunk_index,
            chunk_row=chunk_row,
            vertex=vertex,
        )


def parse_scene_data(packet: bytes | bytearray | memoryview) -> SceneData:
    return SceneData(packet)


def execute(request: bytes) -> bytes:
    """One mutation, always with fixed output capacity (never a size probe)."""
    from . import _native

    if not isinstance(request, bytes) or not HEADER <= len(request) <= MAX_PACKET:
        raise ValueError("invalid geographic request size")
    source, out = ctypes.create_string_buffer(request), ctypes.create_string_buffer(HEADER)
    code = _native._lib.xyg_geo_scale_execute(source, len(request), out, HEADER)
    if code:
        raise _native.GeoNativeError(code)
    return out.raw


def read(request: bytes, budget: int) -> bytes:
    """Pure two-call read; size discovery consumes no retained Data read slot."""
    from . import _native

    _budget(budget)
    if not isinstance(request, bytes) or not HEADER <= len(request) <= min(MAX_PACKET, budget):
        raise ValueError("invalid geographic read request size")
    source, length = ctypes.create_string_buffer(request), ctypes.c_size_t()
    function = _native._lib.xyg_geo_scale_read
    code = function(source, len(request), budget, None, 0, ctypes.byref(length))
    if code:
        raise _native.GeoNativeError(code)
    if length.value > MAX_PACKET or 4 * length.value > budget:
        raise _native.GeoNativeError(-9)
    out = ctypes.create_string_buffer(length.value)
    code = function(source, len(request), budget, out, len(out), ctypes.byref(length))
    if code:
        raise _native.GeoNativeError(code)
    if length.value != len(out):
        raise ValueError("read length changed")
    return out.raw


class GeoScaleBridge(Protocol):
    async def execute(self, request: bytes) -> bytes: ...
    async def read(self, request: bytes) -> bytes: ...


class NativeGeoScaleBridge:
    def __init__(self, budget: int) -> None:
        self.budget = _budget(budget)

    async def execute(self, request: bytes) -> bytes:
        return execute(request)

    async def read(self, request: bytes) -> bytes:
        return read(request, self.budget)


async def _settle(
    task: asyncio.Task, on_cancel: Callable[[], Any] | None = None
) -> tuple[Any, bool]:
    """Wait even through repeated outer cancellation; never cancel transport."""
    interrupted = False
    while True:
        try:
            return await asyncio.shield(task), interrupted
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            interrupted = True
            if on_cancel is not None:
                on_cancel()


async def drive_session(
    bridge: GeoScaleBridge,
    *,
    handle: int,
    sequence: int,
    budget: dict[str, Any],
    read_chunk: Callable[[dict[str, Any]], Awaitable[bytes | bytearray | memoryview]],
    cancel_event: asyncio.Event | None = None,
) -> dict[str, Any]:
    """Service Rust-issued tickets; caller explicitly creates/begins operations.

    Read and transport tasks settle before cancellation releases their charges.
    Callbacks must return exact-size owning storage and not retain other copies.
    """
    cancellation: asyncio.Task | None = None

    def cancel_now() -> asyncio.Task:
        nonlocal cancellation
        if cancellation is None:
            cancellation = asyncio.create_task(
                bridge.execute(encode_request(dict(command=9, handle=handle, sequence=sequence)))
            )
        return cancellation

    async def cancel() -> None:
        await _settle(cancel_now())

    async def watch() -> None:
        assert cancel_event is not None
        await cancel_event.wait()
        await cancel()

    watcher = asyncio.create_task(watch()) if cancel_event is not None else None
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                await cancel()
                raise asyncio.CancelledError
            step = asyncio.create_task(
                bridge.execute(
                    encode_request(dict(command=6, handle=handle, sequence=sequence, budget=budget))
                )
            )
            raw, interrupted = await _settle(step, cancel_now)
            reply = decode_reply(raw)
            if reply["handle"] != handle or reply["sequence"] != sequence:
                raise ValueError("mismatched session reply")
            ticket = reply["ticket"]
            if reply["code"] in (3, 4, 5, 6):
                if interrupted or (cancel_event is not None and cancel_event.is_set()):
                    await cancel()
                    raise asyncio.CancelledError
                return reply
            if reply["code"] != 1 or ticket is None:
                raise ValueError("unowned outstanding read")
            borrowed = chunk = payload = supply = None
            try:
                if interrupted or (cancel_event is not None and cancel_event.is_set()):
                    await cancel()
                    raise asyncio.CancelledError

                async def read_owned_chunk(
                    authority: dict[str, Any],
                ) -> bytes | bytearray | memoryview:
                    return await read_chunk(authority)

                read_task = asyncio.create_task(read_owned_chunk(dict(ticket)))
                borrowed, interrupted = await _settle(read_task, cancel_now)
                read_task = None
                if interrupted:
                    await cancel()
                    raise asyncio.CancelledError
                chunk = _bytes(borrowed)
                if (
                    len(chunk) != ticket["encoded_bytes"]
                    or _backing_bytes(chunk) > ticket["encoded_bytes"]
                ):
                    raise ValueError("read callback must return exact bounded storage")
                if cancel_event is not None and cancel_event.is_set():
                    await cancel()
                    raise asyncio.CancelledError
                if 3 * (352 + len(chunk)) > budget["processor_bytes"]:
                    raise ValueError("read transfer exceeds peak budget")
                payload = bytearray(96 + len(chunk))
                payload[:96], payload[96:] = ticket["raw"], chunk
                supply = encode_request(dict(command=7, handle=handle, payload=payload))
                payload = None
                mutation = asyncio.create_task(bridge.execute(supply))
                _, interrupted = await _settle(mutation, cancel_now)
                mutation = None
                if interrupted:
                    raise asyncio.CancelledError
            except BaseException as error:
                # Exceptions retain completed callback/decoder frames. Clear their
                # local buffer references before acknowledging the Rust charge.
                borrowed = chunk = payload = supply = read_task = mutation = None
                traceback.clear_frames(error.__traceback__)
                # Preserve the primary error; release is still required.
                with suppress(Exception):
                    await cancel()
                raise
            finally:
                borrowed = chunk = payload = supply = None
                try:
                    if cancellation is not None:
                        await _settle(cancellation)
                finally:
                    _, interrupted = await _settle(
                        asyncio.create_task(
                            bridge.execute(
                                encode_request(
                                    dict(command=8, handle=handle, payload=ticket["raw"])
                                )
                            )
                        ),
                        cancel_now,
                    )
                    if interrupted:
                        await cancel()
                        raise asyncio.CancelledError
    finally:
        if watcher is not None:
            if not watcher.done():
                watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
        if cancellation is not None:
            _, interrupted = await _settle(cancellation)
            if interrupted:
                raise asyncio.CancelledError


class SceneDataLease:
    """Explicit retained-data owner. Drop borrowed copies/painters before dispose."""

    def __init__(self, bridge: GeoScaleBridge, handle: int, data: SceneData) -> None:
        self._bridge, self.handle, self._data = bridge, handle, data
        self._disposal: asyncio.Task | None = None

    @property
    def data(self) -> SceneData:
        if self._data is None:
            raise RuntimeError("SceneData disposed")
        return self._data

    async def dispose(self) -> None:
        self._data = None
        if self._disposal is None:
            self._disposal = asyncio.create_task(
                self._bridge.execute(encode_request(dict(command=10, handle=self.handle)))
            )
        _, interrupted = await _settle(self._disposal)
        if interrupted:
            raise asyncio.CancelledError


async def prepare_scene_data(
    bridge: GeoScaleBridge, *, handle: int, sequence: int, budget: dict[str, Any], style: bytes
) -> SceneDataLease:
    if not isinstance(style, bytes) or len(style) != 48:
        raise ValueError("style must be exact 48-byte Rust framing")
    task = asyncio.create_task(
        bridge.execute(
            encode_request(
                dict(command=11, handle=handle, sequence=sequence, budget=budget, payload=style)
            )
        )
    )
    raw, interrupted = await _settle(task)
    reply = decode_reply(raw)
    data_handle = reply["handle"]
    packet = data = None
    try:
        if interrupted:
            raise asyncio.CancelledError
        if (
            reply["source_handle"] != handle
            or reply["sequence"] != sequence
            or reply["data_length"] > MAX_PACKET
            or 4 * reply["data_length"] > budget["processor_bytes"]
        ):
            raise ValueError("invalid leased data reply")
        task = asyncio.create_task(
            bridge.read(encode_request(dict(command=23, handle=data_handle)))
        )
        packet, interrupted = await _settle(task)
        if interrupted:
            raise asyncio.CancelledError
        if len(packet) != reply["data_length"]:
            raise ValueError("mismatched leased data size")
        data = parse_scene_data(packet)
        if data.identity["session_handle"] != handle or data.identity["sequence"] != sequence:
            raise ValueError("mismatched leased data identity")
        return SceneDataLease(bridge, data_handle, data)
    except BaseException as error:
        packet = data = task = None
        traceback.clear_frames(error.__traceback__)
        await _settle(
            asyncio.create_task(
                bridge.execute(encode_request(dict(command=10, handle=data_handle)))
            )
        )
        raise
