"""Import-only paged hierarchy owner. All geographic product policy is Rust-owned."""

from __future__ import annotations

import asyncio
import inspect
import struct
import traceback
import weakref
from contextlib import suppress
from typing import Any

from . import _geoscale as g
from ._geo_retained import OwnedGeoData, RetainedGeoSource, _attach_frame, retained_frame_authority

_FRAMES: weakref.WeakSet = weakref.WeakSet()


def is_hierarchy_frame(frame):
    """Internal authentic-frame provenance; static identity is not live capability."""
    return frame in _FRAMES


class GeoHierarchyFallback(RuntimeError):
    """Explicit Rust fallback; old immutable frames remain valid."""

    def __init__(self, reason_code):
        self.reason_code = reason_code
        super().__init__(f"Rust hierarchy requires explicit canonical fallback ({reason_code})")


class GeoHierarchyUnsupportedSelected(RuntimeError):
    """Selected authority is not supported by this hierarchy processor."""


def _request(command, handle, sequence=0, **fields):
    if command not in (6, 7, 8, 9, 10, 37, 38, 39, 40, 41):
        raise ValueError("unknown hierarchy command")
    request = bytearray(
        g.encode_request(
            dict(command=5 if command == 38 else 6, handle=handle, sequence=sequence, **fields)
        )
    )
    struct.pack_into("<I", request, 8, command)
    return bytes(request)


def decode_reply(data):
    b = g._reply(data)
    if len(b) != 256:
        raise ValueError("fixed hierarchy reply required")
    code = struct.unpack_from("<I", b, 8)[0]
    g._zero(b, 12, 16)
    if code in (0, 6, 10):
        return g.decode_reply(data)
    if code not in (1, 2, 7, 9, 17, 18, 19):
        raise ValueError("invalid hierarchy reply code")
    handle, sequence = struct.unpack_from("<QQ", b, 16)
    ticket = None
    if code in (1, 2, 7):
        g._zero(b, 32, 64)
        g._zero(b, 192, 256)
        raw = bytes(b[64:192])
        if any(raw):
            owner, namespace, serial, seq = struct.unpack_from("<4Q", raw)
            kind = struct.unpack_from("<I", raw, 32)[0]
            size = struct.unpack_from("<Q", raw, 48)[0]
            g._zero(memoryview(raw), 36, 40)
            g._zero(memoryview(raw), 104, 128)
            if (
                kind not in (1, 2, 3, 4, 5)
                or not 0 < size <= (16 * 1024 * 1024 if kind == 1 else 65536)
                or seq != sequence
                or (code == 1 and kind == 3)
                or (code == 7 and kind != 3)
            ):
                raise ValueError("invalid hierarchy ticket")
            if kind == 1:
                if (
                    struct.unpack_from("<I", raw, 76)[0] > 65536
                    or struct.unpack_from("<Q", raw, 88)[0] != size
                    or raw[96:104] != raw[56:64]
                ):
                    raise ValueError("mismatched canonical ticket")
            else:
                g._zero(memoryview(raw), 64, 104)
            ticket = dict(
                raw=raw,
                owner=owner,
                namespace=namespace,
                serial=serial,
                sequence=seq,
                kind=kind,
                page=struct.unpack_from("<Q", raw, 40)[0],
                encoded_bytes=size,
                digest=raw[56:64],
                generation=struct.unpack_from("<Q", raw, 64)[0],
                chunk_index=struct.unpack_from("<I", raw, 72)[0],
                rows=struct.unpack_from("<I", raw, 76)[0],
                first_row=struct.unpack_from("<Q", raw, 80)[0],
            )
        elif code != 2:
            raise ValueError("missing hierarchy ticket")
    elif code == 18:
        g._zero(b, 32, 40)
        g._zero(b, 56, 256)
    elif code == 19:
        g._zero(b, 32, 160)
        g._zero(b, 200, 256)
        if (
            struct.unpack_from("<I", b, 192)[0] not in (1, 2)
            or struct.unpack_from("<I", b, 196)[0] > 256
        ):
            raise ValueError("invalid hierarchy stats")
    else:
        g._zero(b, 32, 256)
    return dict(
        code=code,
        handle=handle,
        sequence=sequence,
        ticket=ticket,
        hierarchy_stats=dict(
            zip(
                (
                    "directory_reads",
                    "leaf_reads",
                    "bytes_read",
                    "decoded_vertices",
                    "passes",
                    "cells",
                ),
                struct.unpack_from("<4Q2I", b, 160),
                strict=True,
            )
        )
        if code == 19
        else None,
    )


def _exact(value, length, budget):
    view = g._bytes(value)
    if len(view) != length or g._backing_bytes(view) > length:
        raise ValueError("hierarchy callback must return exact bounded storage")
    if 4 * (384 + length) > budget["processor_bytes"]:
        raise ValueError("hierarchy transfer exceeds peak budget")
    return view


def _sync_result(value):
    if inspect.isawaitable(value):
        if inspect.iscoroutine(value):
            value.close()
        raise TypeError("asynchronous storage requires spatial_hierarchy_async/aupdate")
    return value


def drive_hierarchy(
    handle, sequence, budget, read_chunk, read_page, write_page, execute=g.execute, read=None
):
    """Service only exact Rust-issued tickets; release borrowed storage before ACK."""
    if read is None:

        def read(request):
            return g.read(request, budget["processor_bytes"])

    while True:
        reply = decode_reply(execute(_request(6, handle, sequence, budget=budget)))
        if reply["handle"] != handle or reply["sequence"] != sequence:
            raise ValueError("mismatched hierarchy step authority")
        if reply["code"] in (18, 19):
            return reply
        if reply["code"] == 10:
            raise GeoHierarchyFallback(reply["fallback_reason_code"])
        ticket = reply["ticket"]
        if reply["code"] not in (1, 7) or ticket is None:
            raise RuntimeError("hierarchy operation did not complete")
        authority, size, kind = bytes(ticket["raw"]), ticket["encoded_bytes"], ticket["kind"]
        ack = 41 if kind == 3 else 8
        borrowed = view = payload = supply = None
        try:
            if 4 * (384 + size) > budget["processor_bytes"]:
                raise MemoryError("hierarchy transfer exceeds peak budget")
            if kind == 3:
                borrowed = read(_request(40, handle, sequence, payload=authority))
                view = _exact(borrowed, size, budget).toreadonly()
                _sync_result(write_page(dict(ticket), view))
            else:
                borrowed = _sync_result((read_chunk if kind == 1 else read_page)(dict(ticket)))
                view = _exact(borrowed, size, budget)
                payload = authority + view.tobytes()
                supply = _request(7, handle, sequence, payload=payload)
                execute(supply)
        except BaseException as error:
            borrowed = view = payload = supply = None
            traceback.clear_frames(error.__traceback__)
            with suppress(Exception):
                execute(_request(9, handle, sequence))
            raise
        finally:
            borrowed = view = payload = supply = None
            execute(_request(ack, handle, sequence, payload=authority))


async def drive_hierarchy_async(
    bridge, handle, sequence, budget, read_chunk, read_page, write_page
):
    """Shield storage and transport until settled, then release its issued ticket."""
    cancellation = None

    def cancel_now():
        nonlocal cancellation
        if cancellation is None:
            cancellation = asyncio.create_task(bridge.execute(_request(9, handle, sequence)))
        return cancellation

    async def cancel():
        with suppress(Exception):
            await g._settle(cancel_now())

    async def callback(fn, *args):
        result = fn(*args)
        return await result if inspect.isawaitable(result) else result

    try:
        while True:
            raw, interrupted = await g._settle(
                asyncio.create_task(bridge.execute(_request(6, handle, sequence, budget=budget))),
                cancel_now,
            )
            reply = decode_reply(raw)
            if reply["handle"] != handle or reply["sequence"] != sequence:
                raise ValueError("mismatched hierarchy step authority")
            if reply["code"] in (18, 19):
                if interrupted:
                    raise asyncio.CancelledError
                return reply
            if reply["code"] == 10:
                if interrupted:
                    raise asyncio.CancelledError
                raise GeoHierarchyFallback(reply["fallback_reason_code"])
            ticket = reply["ticket"]
            if reply["code"] not in (1, 7) or ticket is None:
                raise RuntimeError("hierarchy operation did not complete")
            authority, size, kind = bytes(ticket["raw"]), ticket["encoded_bytes"], ticket["kind"]
            ack = 41 if kind == 3 else 8
            borrowed = view = payload = supply = task = None
            try:
                if interrupted:
                    raise asyncio.CancelledError
                if 4 * (384 + size) > budget["processor_bytes"]:
                    raise MemoryError("hierarchy transfer exceeds peak budget")
                if kind == 3:
                    task = asyncio.create_task(
                        bridge.read(_request(40, handle, sequence, payload=authority))
                    )
                    borrowed, interrupted = await g._settle(task, cancel_now)
                    task = None
                    if interrupted:
                        raise asyncio.CancelledError
                    view = _exact(borrowed, size, budget).toreadonly()
                    task = asyncio.create_task(callback(write_page, dict(ticket), view))
                    _, interrupted = await g._settle(task, cancel_now)
                else:
                    task = asyncio.create_task(
                        callback(read_chunk if kind == 1 else read_page, dict(ticket))
                    )
                    borrowed, interrupted = await g._settle(task, cancel_now)
                    task = None
                    if interrupted:
                        raise asyncio.CancelledError
                    view = _exact(borrowed, size, budget)
                    payload = authority + view.tobytes()
                    supply = _request(7, handle, sequence, payload=payload)
                    task = asyncio.create_task(bridge.execute(supply))
                    _, interrupted = await g._settle(task, cancel_now)
                task = None
                if interrupted:
                    raise asyncio.CancelledError
            except BaseException as error:
                borrowed = view = payload = supply = task = None
                traceback.clear_frames(error.__traceback__)
                await cancel()
                raise
            finally:
                borrowed = view = payload = supply = task = None
                _, interrupted = await g._settle(
                    asyncio.create_task(
                        bridge.execute(_request(ack, handle, sequence, payload=authority))
                    ),
                    cancel_now,
                )
                if interrupted:
                    await cancel()
                    raise asyncio.CancelledError
    finally:
        if cancellation is not None:
            with suppress(Exception):
                await g._settle(cancellation)


class GeoHierarchy(RetainedGeoSource):
    """Private hierarchy lifetime; explicit storage owns immutable external pages."""

    _origin_source: Any
    _read_page: Any
    _write_page: Any
    _creation_sequence: int

    @classmethod
    def _owner(cls, frame, source, read_page, write_page, bridge):
        _ = frame.data
        authority = retained_frame_authority(frame)
        if authority is None or authority[0] is not source or authority[1] is not source._bridge:
            raise ValueError("frame belongs to another source or transport")
        if not callable(read_page) or not callable(write_page):
            raise TypeError("explicit immutable page storage required")
        self = cls.__new__(cls)
        self._setup(source._reader, source.budget, bridge)
        self._origin_source = getattr(source, "_origin_source", source)
        self._read_page, self._write_page = read_page, write_page
        self.info = dict(source.info)
        self.handle = None
        self._creation_sequence = frame.data.identity["sequence"]
        return self

    @classmethod
    def from_frame(
        cls, frame, source, *, grid, max_vertices, max_write_bytes, read_page, write_page
    ):
        if source._bridge is not None:
            raise RuntimeError("use from_frame_async for an asynchronous transport")
        self = cls._owner(frame, source, read_page, write_page, None)
        payload = struct.pack(
            "<IIQQ", g._uint(grid, 32), 0, g._uint(max_vertices), g._uint(max_write_bytes)
        )
        reply = decode_reply(
            g.execute(
                _request(
                    37, frame.handle, self._creation_sequence, budget=self.budget, payload=payload
                )
            )
        )
        if reply["code"] == 17:
            raise GeoHierarchyUnsupportedSelected(
                "Rust hierarchy does not support selected authority"
            )
        if reply["code"] != 0 or reply["sequence"] != self._creation_sequence:
            raise ValueError("invalid hierarchy creation")
        self.handle = reply["handle"]
        try:
            complete = drive_hierarchy(
                self.handle,
                self._creation_sequence,
                self.budget,
                self._reader,
                read_page,
                write_page,
            )
            if complete["code"] != 18:
                raise ValueError("hierarchy build did not complete")
            return self
        except BaseException:
            g.execute(_request(10, self.handle, self._creation_sequence))
            raise

    @classmethod
    async def from_frame_async(
        cls, frame, source, *, grid, max_vertices, max_write_bytes, read_page, write_page
    ):
        bridge = source._bridge or g.NativeGeoScaleBridge(source.budget["processor_bytes"])
        self = cls._owner(frame, source, read_page, write_page, bridge)
        payload = struct.pack(
            "<IIQQ", g._uint(grid, 32), 0, g._uint(max_vertices), g._uint(max_write_bytes)
        )
        raw, interrupted = await g._settle(
            asyncio.create_task(
                bridge.execute(
                    _request(
                        37,
                        frame.handle,
                        self._creation_sequence,
                        budget=self.budget,
                        payload=payload,
                    )
                )
            )
        )
        reply = decode_reply(raw)
        if reply["code"] == 17:
            if interrupted:
                raise asyncio.CancelledError
            raise GeoHierarchyUnsupportedSelected(
                "Rust hierarchy does not support selected authority"
            )
        if reply["code"] != 0 or reply["sequence"] != self._creation_sequence:
            raise ValueError("invalid hierarchy creation")
        self.handle = reply["handle"]
        try:
            if interrupted:
                raise asyncio.CancelledError
            complete = await drive_hierarchy_async(
                bridge,
                self.handle,
                self._creation_sequence,
                self.budget,
                self._reader,
                read_page,
                write_page,
            )
            if complete["code"] != 18:
                raise ValueError("hierarchy build did not complete")
            return self
        except BaseException:
            await g._settle(
                asyncio.create_task(
                    bridge.execute(_request(10, self.handle, self._creation_sequence))
                )
            )
            raise

    def _hierarchy_frame(self, handle, sequence, style):
        reply = decode_reply(
            g.execute(_request(39, handle, sequence, budget=self.budget, payload=style))
        )
        data_handle = reply["handle"]
        packet = data = None
        try:
            if (
                reply["code"] != 0
                or reply["source_handle"] != handle
                or reply["sequence"] != sequence
                or 4 * reply["data_length"] > self.budget["processor_bytes"]
            ):
                raise ValueError("invalid hierarchy Scene receipt")
            packet = g.read(
                g.encode_request(dict(command=23, handle=data_handle)),
                self.budget["processor_bytes"],
            )
            if len(packet) != reply["data_length"]:
                raise ValueError("invalid Scene length")
            data = g.parse_scene_data(packet)
            if data.identity["session_handle"] != handle or data.identity["sequence"] != sequence:
                raise ValueError("mismatched Scene identity")
            return OwnedGeoData(data_handle, data)
        except BaseException:
            packet = data = None
            g.execute(g.encode_request(dict(command=10, handle=data_handle)))
            raise

    async def _hierarchy_frame_async(self, handle, sequence, style):
        raw, interrupted = await g._settle(
            asyncio.create_task(
                self._bridge.execute(
                    _request(39, handle, sequence, budget=self.budget, payload=style)
                )
            )
        )
        reply = decode_reply(raw)
        data_handle = reply["handle"]
        packet = data = None
        try:
            if interrupted:
                raise asyncio.CancelledError
            if (
                reply["code"] != 0
                or reply["source_handle"] != handle
                or reply["sequence"] != sequence
                or 4 * reply["data_length"] > self.budget["processor_bytes"]
            ):
                raise ValueError("invalid hierarchy Scene receipt")
            packet, interrupted = await g._settle(
                asyncio.create_task(
                    self._bridge.read(g.encode_request(dict(command=23, handle=data_handle)))
                )
            )
            if interrupted:
                raise asyncio.CancelledError
            if len(packet) != reply["data_length"]:
                raise ValueError("invalid Scene length")
            data = g.parse_scene_data(packet)
            if data.identity["session_handle"] != handle or data.identity["sequence"] != sequence:
                raise ValueError("mismatched Scene identity")
            return OwnedGeoData(data_handle, data, self._bridge)
        except BaseException:
            packet = data = None
            await g._settle(
                asyncio.create_task(
                    self._bridge.execute(g.encode_request(dict(command=10, handle=data_handle)))
                )
            )
            raise

    def update(self, query, *, sequence, style):
        self._check()
        if not isinstance(style, bytes) or len(style) != 48:
            raise ValueError("exact48-byte style required")
        request = _request(38, self.handle, sequence, budget=self.budget, query=query)
        attachment = request
        self._busy = True
        handle = frame = None
        try:
            reply = decode_reply(g.execute(request))
            if reply["code"] != 0 or reply["sequence"] != sequence:
                raise ValueError("invalid hierarchy query creation")
            handle = reply["handle"]
            complete = drive_hierarchy(
                handle, sequence, self.budget, self._reader, self._read_page, self._write_page
            )
            frame = self._hierarchy_frame(handle, sequence, style)
            _attach_frame(self._origin_source, frame, sequence, attachment, style, _FRAMES.add)
            frame.hierarchy_stats = complete["hierarchy_stats"]
        finally:
            try:
                if handle is not None:
                    g.execute(_request(10, handle, sequence))
            except BaseException:
                if frame is not None:
                    frame.close()
                raise
            finally:
                self._busy = False
        self.current = frame
        return frame

    async def aupdate(self, query, *, sequence, style):
        self._check(True)
        if not isinstance(style, bytes) or len(style) != 48:
            raise ValueError("exact48-byte style required")
        request = _request(38, self.handle, sequence, budget=self.budget, query=query)
        attachment = request
        self._busy, self._active = True, asyncio.current_task()
        handle = frame = None
        try:
            raw, interrupted = await g._settle(asyncio.create_task(self._bridge.execute(request)))
            reply = decode_reply(raw)
            if reply["code"] != 0 or reply["sequence"] != sequence:
                raise ValueError("invalid hierarchy query creation")
            handle = reply["handle"]
            if interrupted:
                raise asyncio.CancelledError
            complete = await drive_hierarchy_async(
                self._bridge,
                handle,
                sequence,
                self.budget,
                self._reader,
                self._read_page,
                self._write_page,
            )
            frame = await self._hierarchy_frame_async(handle, sequence, style)
            _attach_frame(self._origin_source, frame, sequence, attachment, style, _FRAMES.add)
            frame.hierarchy_stats = complete["hierarchy_stats"]
        finally:
            try:
                if handle is not None:
                    _, interrupted = await g._settle(
                        asyncio.create_task(self._bridge.execute(_request(10, handle, sequence)))
                    )
                    if interrupted:
                        raise asyncio.CancelledError
            except BaseException:
                if frame is not None:
                    await g._settle(asyncio.create_task(frame.aclose()))
                raise
            finally:
                self._busy, self._active = False, None
        self.current = frame
        return frame

    def close(self):
        if self._bridge is not None:
            raise RuntimeError("use aclose for an asynchronous owner")
        if self._busy:
            raise RuntimeError("hierarchy operation already active")
        if not self._closed:
            g.execute(_request(10, self.handle, self._creation_sequence))
            self._closed = True

    async def aclose(self):
        if self._bridge is None:
            self.close()
            return
        if self._active is not None and self._active is not asyncio.current_task():
            self._active.cancel()
            with suppress(BaseException):
                await g._settle(self._active)
        if not self._closed:
            if self._disposal is None:
                self._disposal = asyncio.create_task(
                    self._bridge.execute(_request(10, self.handle, self._creation_sequence))
                )
            task = self._disposal
            try:
                _, interrupted = await g._settle(task)
            except BaseException:
                if self._disposal is task:
                    self._disposal = None
                raise
            self._closed = True
            if interrupted:
                raise asyncio.CancelledError

    def cancel(self):
        if self._busy:
            raise RuntimeError("synchronous storage cancellation requires callback failure")

    async def acancel(self):
        if self._active is not None and self._active is not asyncio.current_task():
            self._active.cancel()
            with suppress(BaseException):
                await g._settle(self._active)
