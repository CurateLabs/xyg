"""Import-only paged hierarchy owner. All geographic product policy is Rust-owned."""

from __future__ import annotations

import asyncio
import inspect
import struct
import traceback
import weakref
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, replace
from types import MappingProxyType, SimpleNamespace
from typing import Any

from . import _geoscale as g
from ._geo_allocation_recovery import (
    GeoAllocationAttempt,
    forget_geo_allocation_issuer,
    forget_geo_allocation_issuer_async,
    register_geo_allocation_issuer,
)
from ._geo_retained import OwnedGeoData, RetainedGeoSource, _attach_frame, retained_frame_authority

_FRAMES: weakref.WeakSet = weakref.WeakSet()
_LANES: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_CONTEXTS: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


@dataclass(frozen=True)
class _LaneContext:
    handle: int
    source: Any
    issuer: Any
    transport: Any
    execute: Any
    read: Any
    native_execute: Any
    budget: Mapping[str, Any]
    read_chunk: Any
    read_page: Any
    write_page: Any


def _lane_context(lane):
    reference = _CONTEXTS.get(lane)
    context = reference() if reference is not None else None
    if context is None:
        raise TypeError("issued hierarchy lane required")
    return context


def _capture_lane_context(lane):
    issuer = lane._issuer_bridge
    budget = MappingProxyType(dict(lane.budget))
    native_read, native_execute = g.read, g.execute
    execute = issuer.execute if issuer is not None else native_execute
    read = (
        issuer.read
        if issuer is not None
        else lambda request: native_read(request, budget["processor_bytes"])
    )
    if issuer is None and lane._bridge is not None:

        async def execute_async(request):
            return await asyncio.to_thread(native_execute, request)

        async def read_async(request):
            return await asyncio.to_thread(native_read, request, budget["processor_bytes"])

        execute, read = execute_async, read_async
    transport = SimpleNamespace(execute=execute, read=read) if lane._bridge is not None else None
    context = _LaneContext(
        lane.handle,
        lane._origin_source,
        issuer,
        transport,
        execute,
        read,
        native_execute,
        budget,
        lane._reader,
        lane._read_page,
        lane._write_page,
    )
    return context


def _register_lane(lane):
    context = replace(lane._context, handle=lane.handle)
    lane._context = context
    _CONTEXTS[lane] = weakref.ref(context)
    register_geo_allocation_issuer(lane, context.handle, context.issuer)
    bridge = weakref.ref(lane._issuer_bridge) if lane._issuer_bridge is not None else None
    _LANES[lane] = (
        weakref.ref(lane._origin_source),
        bridge,
        id(lane._issuer_bridge),
        lane._creation_sequence,
        lane._selected_mode,
    )


def hierarchy_lane_authority(lane):
    """Read-only captured issuer; values cannot globally pin Source/Frame cycles."""
    record = _LANES.get(lane)
    if record is None:
        return None
    source = record[0]()
    bridge = record[1]() if record[1] is not None else None
    if source is None or id(bridge) != record[2]:
        return None
    return source, bridge, record[3], record[4]


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
    if command not in (6, 7, 8, 9, 10, 37, 38, 39, 40, 41, 42, 43, 44):
        raise ValueError("unknown hierarchy command")
    request = bytearray(
        g.encode_request(
            dict(
                command=5 if command in (38, 43) else 6, handle=handle, sequence=sequence, **fields
            )
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
    _selected_mode: bool
    _pending_operation: GeoSelectedHierarchyOperation | None
    _issuer_bridge: Any
    _context: _LaneContext

    @classmethod
    def _owner(cls, frame, source, read_page, write_page, bridge, selected=False):
        _ = frame.data
        authority = retained_frame_authority(frame)
        if authority is None or authority[0] is not source or authority[1] is not source._bridge:
            raise ValueError("frame belongs to another source or transport")
        if not selected and frame.data.selection is not None:
            raise GeoHierarchyUnsupportedSelected()
        if selected and frame.data.selection is None:
            raise ValueError("selected hierarchy requires authentic selected frame")
        if not callable(read_page) or not callable(write_page):
            raise TypeError("explicit immutable page storage required")
        self = cls.__new__(cls)
        self._setup(source._reader, source.budget, bridge)
        self._origin_source = getattr(source, "_origin_source", source)
        self._read_page, self._write_page = read_page, write_page
        self.info = dict(source.info)
        self.handle = None
        self._selected_mode, self._pending_operation = selected, None
        self._issuer_bridge = source._bridge
        self._creation_sequence = frame.data.identity["sequence"]
        self._context = _capture_lane_context(self)
        return self

    @classmethod
    def from_frame(cls, frame, source, **options):
        return cls._from_frame(frame, source, **options)

    @classmethod
    def from_selected_frame(cls, frame, source, **options):
        return cls._from_frame(frame, source, selected=True, **options)

    @classmethod
    async def from_frame_async(cls, frame, source, **options):
        return await cls._from_frame_async(frame, source, **options)

    @classmethod
    async def from_selected_frame_async(cls, frame, source, **options):
        return await cls._from_frame_async(frame, source, selected=True, **options)

    @property
    def cancel_generation(self):
        return self._cancel_generation

    @property
    def pending_operation(self):
        return self._pending_operation

    @property
    def selected(self):
        return self._selected_mode

    @classmethod
    def _from_frame(
        cls,
        frame,
        source,
        *,
        grid,
        max_vertices,
        max_write_bytes,
        read_page,
        write_page,
        selected=False,
    ):
        if source._bridge is not None:
            raise RuntimeError("use from_frame_async for an asynchronous transport")
        self = cls._owner(frame, source, read_page, write_page, None, selected)
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
            _register_lane(self)
            return self
        except BaseException:
            g.execute(_request(10, self.handle, self._creation_sequence))
            raise

    @classmethod
    async def _from_frame_async(
        cls,
        frame,
        source,
        *,
        grid,
        max_vertices,
        max_write_bytes,
        read_page,
        write_page,
        selected=False,
    ):
        bridge = source._bridge or g.NativeGeoScaleBridge(source.budget["processor_bytes"])
        self = cls._owner(frame, source, read_page, write_page, bridge, selected)
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
            _register_lane(self)
            return self
        except BaseException:
            await g._settle(
                asyncio.create_task(
                    bridge.execute(_request(10, self.handle, self._creation_sequence))
                )
            )
            raise

    def _hierarchy_frame(
        self,
        handle,
        sequence,
        style,
        *,
        command=39,
        on_attempt=None,
        on_receipt=None,
        on_release=None,
        budget=None,
        _context=None,
    ):
        phase_budget = self.budget if budget is None else budget
        execute = g.execute if _context is None else _context.execute
        read = g.read if _context is None else lambda request, _budget: _context.read(request)
        if on_attempt:
            on_attempt()
        reply = decode_reply(
            execute(_request(command, handle, sequence, budget=phase_budget, payload=style))
        )
        if command == 44 and (
            reply["code"] != 0
            or reply["handle"] != handle
            or reply["source_handle"] != handle
            or reply["sequence"] != sequence
        ):
            raise ValueError("invalid same-handle publication receipt")
        data_handle = reply["handle"]
        if on_receipt:
            on_receipt()
        packet = data = None
        try:
            if (
                reply["code"] != 0
                or reply["source_handle"] != handle
                or reply["sequence"] != sequence
                or 4 * reply["data_length"] > phase_budget["processor_bytes"]
            ):
                raise ValueError("invalid hierarchy Scene receipt")
            packet = read(
                g.encode_request(dict(command=23, handle=data_handle)),
                phase_budget["processor_bytes"],
            )
            if len(packet) != reply["data_length"]:
                raise ValueError("invalid Scene length")
            data = g.parse_scene_data(packet)
            if data.identity["session_handle"] != handle or data.identity["sequence"] != sequence:
                raise ValueError("mismatched Scene identity")
            return OwnedGeoData(data_handle, data)
        except BaseException as error:
            packet = data = None
            traceback.clear_frames(error.__traceback__)
            execute(g.encode_request(dict(command=10, handle=data_handle)))
            if on_release:
                on_release()
            raise

    async def _hierarchy_frame_async(
        self,
        handle,
        sequence,
        style,
        *,
        command=39,
        on_attempt=None,
        on_receipt=None,
        on_release=None,
        budget=None,
        _context=None,
    ):
        phase_budget = self.budget if budget is None else budget
        transport = self._bridge if _context is None else _context.transport
        if on_attempt:
            on_attempt()
        raw, interrupted = await g._settle(
            asyncio.create_task(
                transport.execute(
                    _request(command, handle, sequence, budget=phase_budget, payload=style)
                )
            )
        )
        reply = decode_reply(raw)
        if command == 44 and (
            reply["code"] != 0
            or reply["handle"] != handle
            or reply["source_handle"] != handle
            or reply["sequence"] != sequence
        ):
            raise ValueError("invalid same-handle publication receipt")
        data_handle = reply["handle"]
        if on_receipt:
            on_receipt()
        packet = data = None
        try:
            if interrupted:
                raise asyncio.CancelledError
            if (
                reply["code"] != 0
                or reply["source_handle"] != handle
                or reply["sequence"] != sequence
                or 4 * reply["data_length"] > phase_budget["processor_bytes"]
            ):
                raise ValueError("invalid hierarchy Scene receipt")
            packet, interrupted = await g._settle(
                asyncio.create_task(
                    transport.read(g.encode_request(dict(command=23, handle=data_handle)))
                )
            )
            if interrupted:
                raise asyncio.CancelledError
            if len(packet) != reply["data_length"]:
                raise ValueError("invalid Scene length")
            data = g.parse_scene_data(packet)
            if data.identity["session_handle"] != handle or data.identity["sequence"] != sequence:
                raise ValueError("mismatched Scene identity")
            return OwnedGeoData(data_handle, data, transport)
        except BaseException as error:
            packet = data = None
            traceback.clear_frames(error.__traceback__)
            await g._settle(
                asyncio.create_task(
                    transport.execute(g.encode_request(dict(command=10, handle=data_handle)))
                )
            )
            if on_release:
                on_release()
            raise

    def update(self, query, *, sequence, style):
        self._check()
        if self._selected_mode:
            raise GeoHierarchyUnsupportedSelected()
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
        if self._selected_mode:
            raise GeoHierarchyUnsupportedSelected()
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
        self._cancel_generation += 1
        if self._bridge is not None:
            raise RuntimeError("use aclose for an asynchronous owner")
        if self._busy:
            raise RuntimeError("hierarchy operation already active")
        if self._closed:
            return
        if self._pending_operation is not None:
            self._pending_operation.close()
        context = _lane_context(self)
        if not getattr(self, "_index_disposed", False):
            reply = decode_reply(
                context.execute(_request(10, context.handle, self._creation_sequence))
            )
            if (
                reply["code"] != 0
                or reply["handle"] != context.handle
                or reply["sequence"] != self._creation_sequence
            ):
                raise ValueError("hierarchy disposal receipt")
            self._index_disposed = True
        forget_geo_allocation_issuer(self)
        self._closed = True

    async def aclose(self):
        self._cancel_generation += 1
        if self._bridge is None:
            return self.close()
        if self._active is not None and self._active is not asyncio.current_task():
            self._active.cancel()
            with suppress(BaseException):
                await g._settle(self._active)
        if self._closed:
            return
        if self._disposal is None:

            async def dispose():
                if self._pending_operation is not None:
                    await self._pending_operation.aclose()
                context = _lane_context(self)
                if not getattr(self, "_index_disposed", False):
                    raw = await context.execute(
                        _request(10, context.handle, self._creation_sequence)
                    )
                    reply = decode_reply(raw)
                    if (
                        reply["code"] != 0
                        or reply["handle"] != context.handle
                        or reply["sequence"] != self._creation_sequence
                    ):
                        raise ValueError("hierarchy disposal receipt")
                    self._index_disposed = True
                await forget_geo_allocation_issuer_async(self)
                self._closed = True

            self._disposal = asyncio.create_task(dispose())
        task = self._disposal
        try:
            _, interrupted = await g._settle(task)
        except BaseException:
            if self._disposal is task:
                self._disposal = None
            raise
        if interrupted:
            raise asyncio.CancelledError

    def cancel(self):
        self._cancel_generation += 1
        if self._busy or (self._pending_operation is not None and self._pending_operation._busy):
            raise RuntimeError("synchronous storage cancellation requires callback failure")

    async def acancel(self):
        self._cancel_generation += 1
        if self._pending_operation is not None:
            await self._pending_operation.cancel_async()
        if self._active is not None and self._active is not asyncio.current_task():
            self._active.cancel()
            with suppress(BaseException):
                await g._settle(self._active)

    def _fork_owner(self, handle):
        lane = type(self).__new__(type(self))
        lane._setup(self._reader, self.budget, self._bridge)
        lane.handle, lane.info = handle, dict(self.info)
        lane._origin_source, lane._issuer_bridge = self._origin_source, self._issuer_bridge
        lane._read_page, lane._write_page = self._read_page, self._write_page
        lane._selected_mode, lane._pending_operation = self._selected_mode, None
        lane._creation_sequence = self._creation_sequence
        lane._context = _lane_context(self)
        _register_lane(lane)
        return lane

    def fork(self):
        self._check()
        if self._bridge is not None:
            raise RuntimeError("use fork_async for asynchronous hierarchy")
        reply = decode_reply(
            g.execute(_request(42, self.handle, self._creation_sequence, budget=self.budget))
        )
        if reply["code"] != 0 or reply["sequence"] != self._creation_sequence:
            raise ValueError("invalid hierarchy fork")
        return self._fork_owner(reply["handle"])

    async def fork_async(self):
        if self._bridge is None:
            return self.fork()
        self._check(True)
        raw, interrupted = await g._settle(
            asyncio.create_task(
                self._bridge.execute(
                    _request(42, self.handle, self._creation_sequence, budget=self.budget)
                )
            )
        )
        reply = decode_reply(raw)
        if reply["code"] != 0 or reply["sequence"] != self._creation_sequence:
            raise ValueError("invalid hierarchy fork")
        lane = self._fork_owner(reply["handle"])
        if interrupted:
            await lane.aclose()
            raise asyncio.CancelledError
        return lane

    def _selected_operation(self, state, query, sequence):
        from ._geo_selected import claim_selected_state

        context = _lane_context(self)
        if not hierarchy_lane_authority(self)[3]:
            raise GeoHierarchyUnsupportedSelected()
        if self._pending_operation is not None:
            raise RuntimeError("selected hierarchy operation still owned")
        authority = hierarchy_lane_authority(self)
        if authority is None:
            raise TypeError("issued hierarchy lane required")
        claim = claim_selected_state(state, authority[1])
        try:
            request = _request(
                43,
                context.handle,
                sequence,
                query=query,
                budget=context.budget,
                payload=struct.pack("<Q", claim.handle),
            )
            operation = GeoSelectedHierarchyOperation(
                self, claim.handle, sequence, request, claim, _token=_OPERATION
            )
        except BaseException:
            claim.reject()
            raise
        self._pending_operation = operation
        return claim, operation

    def begin_selected(self, state, query, *, sequence):
        self._check()
        if _lane_context(self).transport is not None:
            raise RuntimeError("use begin_selected_async for asynchronous hierarchy")
        claim, operation = self._selected_operation(state, query, sequence)
        return operation.recover()

    async def begin_selected_async(self, state, query, *, sequence):
        if _lane_context(self).transport is None:
            return self.begin_selected(state, query, sequence=sequence)
        self._check(True)
        _, operation = self._selected_operation(state, query, sequence)
        return await operation.recover_async()

    def update_selected(self, state, query, *, sequence, style):
        operation = self.begin_selected(state, query, sequence=sequence)
        try:
            operation.drive()
            return operation.prepare(style)
        finally:
            operation.close()

    async def aupdate_selected(self, state, query, *, sequence, style):
        operation = await self.begin_selected_async(state, query, sequence=sequence)
        try:
            await operation.drive_async()
            return await operation.prepare_async(style)
        finally:
            await operation.aclose()


_OPERATION = object()


def _rust_failure(error):
    from ._native import GeoNativeError

    return isinstance(error, GeoNativeError)


class GeoHierarchyPublicationUncertain(RuntimeError):
    """Successful publication may have replaced Query; never retry44 blindly."""


class GeoSelectedHierarchyOperation:
    """An issued State becomes Query then Data; exact cleanup retains ambiguity."""

    def __init__(self, owner, handle, sequence, request, claim, *, _token=None):
        if _token is not _OPERATION:
            raise TypeError("issued selected hierarchy operation required")
        self._owner, self._handle, self._sequence = owner, handle, sequence
        self._context = _lane_context(owner)
        self._request, self._phase, self._stats = bytes(request), "begin-uncertain", None
        self._claim, self._allocation = claim, None
        self._recovery, self._closing, self._retired, self._query_disposed = (
            None,
            False,
            False,
            False,
        )
        self._busy, self._active, self._disposal = False, None, None
        self._data_disposed = False

    @property
    def handle(self):
        return self._handle

    @property
    def sequence(self):
        return self._sequence

    @property
    def request(self):
        return self._request

    @property
    def closed(self):
        return self._phase == "closed"

    @property
    def hierarchy_stats(self):
        return self._stats

    def _closed(self):
        self._phase = "closed"
        if self._owner._pending_operation is self:
            self._owner._pending_operation = None

    def _allocation_attempt(self):
        if self._allocation is None:
            if self._closing:
                self._claim.reject()
                self._closed()
                raise RuntimeError("selected hierarchy operation closing")
            transport = SimpleNamespace(
                execute=self._context.execute, native_execute=self._context.native_execute
            )
            try:
                self._allocation = GeoAllocationAttempt(
                    self._owner, transport, self.request, self.sequence, authenticated=True
                )
            except BaseException:
                self._claim.reject()
                self._closed()
                raise
        return self._allocation

    def _validate_admission(self, raw):
        reply = decode_reply(raw)
        if (
            reply["code"] != 0
            or reply["handle"] != self.handle
            or reply["sequence"] != self.sequence
        ):
            raise ValueError("selected hierarchy begin ownership reply")
        return self.handle

    def _admitted(self, raw):
        self._claim.consume()
        self._retired = raw is None
        self._phase = "query"
        return self

    def _admission_failed(self):
        if self.closed:
            return
        if self._allocation is not None and self._allocation.rejected:
            self._claim.reject()
            self._closed()
        else:
            self._claim.consume()

    def recover(self):
        if self._context.transport is not None:
            raise RuntimeError("use recover_async for asynchronous operation")
        if self._closing or self.closed:
            raise RuntimeError("selected hierarchy operation closing")
        return self._recover()

    def _recover(self):
        if self._phase == "query":
            return self
        try:
            return self._admitted(self._allocation_attempt().recover(self._validate_admission))
        except BaseException:
            self._admission_failed()
            raise

    async def recover_async(self):
        if self._context.transport is None:
            return self.recover()
        if self._closing or self.closed:
            raise RuntimeError("selected hierarchy operation closing")
        return await self._recover_async()

    async def _recover_async(self):
        if self._phase == "query":
            return self
        if self._recovery is None:

            async def run():
                try:
                    return self._admitted(
                        await self._allocation_attempt().recover_async(self._validate_admission)
                    )
                except BaseException:
                    self._admission_failed()
                    raise

            self._recovery = asyncio.create_task(run())
        task = self._recovery
        try:
            result, interrupted = await g._settle(task)
        finally:
            if task.done() and self._recovery is task:
                self._recovery = None
        if interrupted:
            raise asyncio.CancelledError
        return result

    def _release_birth(self):
        if self._allocation is not None:
            if self._allocation.probe_retirement(self._validate_admission) is not None:
                raise RuntimeError("hierarchy admission phase remains live")
            self._allocation.release()

    async def _release_birth_async(self):
        if self._allocation is not None:
            if await self._allocation.probe_retirement_async(self._validate_admission) is not None:
                raise RuntimeError("hierarchy admission phase remains live")
            await self._allocation.release_async()

    def _check(self):
        if (
            self._closing
            or self.closed
            or self._phase == "data"
            or self._busy
            or self._disposal is not None
        ):
            raise RuntimeError("selected hierarchy operation unavailable")

    def drive(self):
        self._check()
        if self._context.transport is not None:
            raise RuntimeError("use drive_async for asynchronous operation")
        if self._phase != "query" or self._retired:
            raise GeoHierarchyPublicationUncertain()
        self._busy = True
        try:
            complete = drive_hierarchy(
                self.handle,
                self.sequence,
                self._context.budget,
                self._context.read_chunk,
                self._context.read_page,
                self._context.write_page,
                execute=self._context.execute,
                read=self._context.read,
            )
            self._stats = complete["hierarchy_stats"]
            return complete
        finally:
            self._busy = False

    async def drive_async(self):
        if self._context.transport is None:
            return self.drive()
        self._check()
        if self._phase != "query" or self._retired:
            raise GeoHierarchyPublicationUncertain()
        self._busy, self._active = True, asyncio.current_task()
        try:
            complete = await drive_hierarchy_async(
                self._context.transport,
                self.handle,
                self.sequence,
                self._context.budget,
                self._context.read_chunk,
                self._context.read_page,
                self._context.write_page,
            )
            self._stats = complete["hierarchy_stats"]
            return complete
        finally:
            self._busy, self._active = False, None

    def _prepared(self, frame, style):
        _attach_frame(
            self._context.source,
            frame,
            self.sequence,
            self.request,
            style,
            _FRAMES.add,
            _bridge=self._context.issuer,
        )
        frame.hierarchy_stats = self._stats
        self._owner.current = frame
        return frame

    def _attempt(self):
        self._phase = "publication-uncertain"

    def _receipt(self):
        self._phase = "data"

    def _data_released(self):
        self._data_disposed = True

    def _confirm(self, reply):
        if (
            reply["code"] != 19
            or reply["handle"] != self.handle
            or reply["sequence"] != self.sequence
        ):
            raise GeoHierarchyPublicationUncertain()
        self._phase, self._stats = "query", reply["hierarchy_stats"]

    def prepare(self, style, *, budget=None):
        self._check()
        if self._context.transport is not None:
            raise RuntimeError("use prepare_async for asynchronous operation")
        if not isinstance(style, bytes) or len(style) != 48:
            raise ValueError("exact48-byte style required")
        if self._phase == "begin-uncertain" or self._retired:
            raise GeoHierarchyPublicationUncertain()
        if self._phase == "publication-uncertain":
            try:
                self._confirm(
                    decode_reply(
                        self._context.execute(
                            _request(6, self.handle, self.sequence, budget=self._context.budget)
                        )
                    )
                )
            except BaseException as error:
                raise GeoHierarchyPublicationUncertain() from error
        if self._stats is None:
            raise RuntimeError("drive must complete before prepare")
        self._busy = True
        try:
            frame = self._owner._hierarchy_frame(
                self.handle,
                self.sequence,
                style,
                command=44,
                on_attempt=self._attempt,
                on_receipt=self._receipt,
                on_release=self._data_released,
                budget=self._context.budget if budget is None else dict(budget),
                _context=self._context,
            )
            self._release_birth()
            self._closed()
            return self._prepared(frame, style)
        finally:
            self._busy = False

    async def prepare_async(self, style, *, budget=None):
        if self._context.transport is None:
            return self.prepare(style, budget=budget)
        self._check()
        if not isinstance(style, bytes) or len(style) != 48:
            raise ValueError("exact48-byte style required")
        if self._phase == "begin-uncertain" or self._retired:
            raise GeoHierarchyPublicationUncertain()
        self._busy, self._active = True, asyncio.current_task()
        try:
            if self._phase == "publication-uncertain":
                try:
                    raw, interrupted = await g._settle(
                        asyncio.create_task(
                            self._context.transport.execute(
                                _request(6, self.handle, self.sequence, budget=self._context.budget)
                            )
                        )
                    )
                    self._confirm(decode_reply(raw))
                    if interrupted:
                        raise asyncio.CancelledError
                except asyncio.CancelledError:
                    raise
                except BaseException as error:
                    raise GeoHierarchyPublicationUncertain() from error
            if self._stats is None:
                raise RuntimeError("drive must complete before prepare")
            frame = await self._owner._hierarchy_frame_async(
                self.handle,
                self.sequence,
                style,
                command=44,
                on_attempt=self._attempt,
                on_receipt=self._receipt,
                on_release=self._data_released,
                budget=self._context.budget if budget is None else dict(budget),
                _context=self._context,
            )
            await self._release_birth_async()
            self._closed()
            return self._prepared(frame, style)
        finally:
            self._busy, self._active = False, None

    def close(self):
        if self._context.transport is not None:
            raise RuntimeError("use aclose for asynchronous operation")
        if self._busy:
            raise RuntimeError("selected hierarchy operation active")
        if self.closed:
            return
        self._closing = True
        if self._phase == "begin-uncertain":
            self._recover()
        if self.closed:
            return
        if self._phase in ("publication-uncertain", "data"):
            try:
                if not self._data_disposed:
                    reply = decode_reply(self._context.execute(_request(10, self.handle)))
                    if (
                        reply["code"] != 0
                        or reply["handle"] != self.handle
                        or reply["sequence"] != 0
                    ):
                        raise RuntimeError("cleanup awaiting release")
                    self._data_disposed = True
                self._release_birth()
                self._closed()
                return
            except BaseException as error:
                if self._data_disposed or not _rust_failure(error):
                    raise
        if not self._query_disposed:
            reply = decode_reply(self._context.execute(_request(10, self.handle, self.sequence)))
            if (
                reply["code"] != 0
                or reply["handle"] != self.handle
                or reply["sequence"] != self.sequence
            ):
                raise RuntimeError("cleanup awaiting release")
            self._query_disposed = True
        self._release_birth()
        self._closed()

    async def aclose(self):
        if self._context.transport is None:
            return self.close()
        self._closing = True
        active_interrupted = False
        if self._recovery is not None:
            with suppress(BaseException):
                _, active_interrupted = await g._settle(self._recovery)
            current = asyncio.current_task()
            active_interrupted |= current is not None and current.cancelling() > 0
        if self._active is not None and self._active is not asyncio.current_task():
            active = self._active
            active.cancel()
            with suppress(BaseException):
                _, active_interrupted = await g._settle(active)
            current = asyncio.current_task()
            active_interrupted |= current is not None and current.cancelling() > 0
        if self.closed:
            if active_interrupted:
                raise asyncio.CancelledError
            return
        if self._disposal is None:
            self._disposal = asyncio.create_task(self._dispose_async())
        task = self._disposal
        try:
            _, interrupted = await g._settle(task)
        except BaseException:
            if self._disposal is task:
                self._disposal = None
            raise
        if interrupted or active_interrupted:
            raise asyncio.CancelledError

    async def _dispose_async(self):
        if self._phase == "begin-uncertain":
            await self._recover_async()
        if self.closed:
            return
        if self._phase in ("publication-uncertain", "data"):
            try:
                if not self._data_disposed:
                    raw = await self._context.transport.execute(_request(10, self.handle))
                    reply = decode_reply(raw)
                    if (
                        reply["code"] != 0
                        or reply["handle"] != self.handle
                        or reply["sequence"] != 0
                    ):
                        raise RuntimeError("cleanup awaiting release")
                    self._data_disposed = True
                await self._release_birth_async()
                self._closed()
                return
            except BaseException as error:
                if self._data_disposed or not _rust_failure(error):
                    raise
        if not self._query_disposed:
            raw = await self._context.transport.execute(_request(10, self.handle, self.sequence))
            reply = decode_reply(raw)
            if (
                reply["code"] != 0
                or reply["handle"] != self.handle
                or reply["sequence"] != self.sequence
            ):
                raise RuntimeError("cleanup awaiting release")
            self._query_disposed = True
        await self._release_birth_async()
        self._closed()

    async def cancel_async(self):
        if self._active is not None and self._active is not asyncio.current_task():
            self._active.cancel()
            with suppress(BaseException):
                await g._settle(self._active)
        elif self._phase == "query":
            await g._settle(
                asyncio.create_task(
                    self._context.transport.execute(_request(9, self.handle, self.sequence))
                )
            )
