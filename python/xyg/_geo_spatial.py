"""Native spatial-index owners with explicit external page storage.

All candidate admission, projection, time predicates and tier policy are Rust-owned.
"""

from __future__ import annotations

import asyncio
import inspect
import struct
import traceback
from contextlib import suppress
from typing import Any

from . import _geoscale as g
from ._geo_retained import RetainedGeoSource, _aprepare, _attach_frame


class GeoSpatialFullScanRequired(RuntimeError):
    """Rust requires explicit canonical fallback; no indexed query was started."""

    def __init__(self, reason_code):
        self.reason_code = reason_code
        super().__init__(
            "Rust requires explicit canonical full-source scan "
            + ("(frontier limit)" if reason_code == 1 else "(leaf work budget)")
        )


def _request(command, handle, sequence=0, **fields):
    return g.encode_request(
        dict(
            command=command,
            handle=handle,
            **({"sequence": sequence} if command in (6, 9, 17, 18, 19, 24, 25) else {}),
            **fields,
        )
    )


def _exact(value, length, budget):
    view = g._bytes(value)
    if len(view) != length or g._backing_bytes(view) > length:
        raise ValueError("index callback must return exact bounded storage")
    if 4 * (352 + length) > budget["processor_bytes"]:
        raise ValueError("index transfer exceeds peak budget")
    return view


def _sync_result(value):
    if inspect.isawaitable(value):
        if inspect.iscoroutine(value):
            value.close()
        raise TypeError("asynchronous storage requires spatial_index_async/aupdate")
    return value


def drive_index(
    handle, sequence, budget, read_chunk, read_page, write_page, execute=g.execute, read=None
):
    """Service only exact Rust-issued tickets; release borrowed storage before ACK."""
    if read is None:

        def read(request):
            return g.read(request, budget["processor_bytes"])

    while True:
        reply = g.decode_reply(execute(_request(6, handle, sequence, budget=budget)))
        if reply["handle"] != handle or reply["sequence"] != sequence:
            raise ValueError("mismatched index step authority")
        if reply["code"] in (11, 12):
            return reply
        ticket = reply["ticket"]
        if reply["code"] not in (1, 7) or ticket is None:
            raise RuntimeError("index operation did not complete")
        authority, size, kind = bytes(ticket["raw"]), ticket["encoded_bytes"], ticket["kind"]
        ack = 24 if kind == 3 else 8
        borrowed = view = payload = supply = None
        try:
            if 4 * (352 + size) > budget["processor_bytes"]:
                raise MemoryError("index transfer exceeds peak budget")
            if kind == 3:
                borrowed = read(_request(25, handle, sequence, payload=authority))
                view = _exact(borrowed, size, budget).toreadonly()
                _sync_result(write_page(dict(ticket), view))
            else:
                borrowed = _sync_result((read_page if kind == 2 else read_chunk)(dict(ticket)))
                view = _exact(borrowed, size, budget)
                payload = authority + view.tobytes()
                supply = _request(7, handle, payload=payload)
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


async def drive_index_async(bridge, handle, sequence, budget, read_chunk, read_page, write_page):
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
            reply = g.decode_reply(raw)
            if reply["handle"] != handle or reply["sequence"] != sequence:
                raise ValueError("mismatched index step authority")
            if reply["code"] in (11, 12):
                if interrupted:
                    raise asyncio.CancelledError
                return reply
            ticket = reply["ticket"]
            if reply["code"] not in (1, 7) or ticket is None:
                raise RuntimeError("index operation did not complete")
            authority, size, kind = bytes(ticket["raw"]), ticket["encoded_bytes"], ticket["kind"]
            ack = 24 if kind == 3 else 8
            borrowed = view = payload = supply = task = None
            try:
                if interrupted:
                    raise asyncio.CancelledError
                if 4 * (352 + size) > budget["processor_bytes"]:
                    raise MemoryError("index transfer exceeds peak budget")
                if kind == 3:
                    task = asyncio.create_task(
                        bridge.read(_request(25, handle, sequence, payload=authority))
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
                        callback(read_page if kind == 2 else read_chunk, dict(ticket))
                    )
                    borrowed, interrupted = await g._settle(task, cancel_now)
                    task = None
                    if interrupted:
                        raise asyncio.CancelledError
                    view = _exact(borrowed, size, budget)
                    payload = authority + view.tobytes()
                    supply = _request(7, handle, payload=payload)
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


class GeoSpatialIndex(RetainedGeoSource):
    """Index authority. External storage owns durable pages, independent frames own paint."""

    _origin_source: Any
    _read_page: Any
    _write_page: Any

    @classmethod
    def _owner(cls, frame, source, read_page, write_page, bridge):
        _ = frame.data
        self = cls.__new__(cls)
        self._setup(source._reader, source.budget, bridge)
        self._origin_source = getattr(source, "_origin_source", source)
        self._read_page, self._write_page = read_page, write_page
        identity = frame.data.identity
        self.info = dict(
            generation=identity["generation"],
            digest=bytes(identity["source_digest"]),
            rows=identity["source_rows"],
            geometry=identity["geometry"],
            crs=identity["source_crs"],
        )
        self.handle = None
        return self

    @classmethod
    def _from_frame(cls, frame, source, *, grid, max_vertices, read_page, write_page):
        if source._bridge is not None:
            raise RuntimeError("use spatial_index_async for an asynchronous transport")
        self = cls._owner(frame, source, read_page, write_page, None)
        payload = struct.pack("<IIQ", g._uint(grid, 32), 0, g._uint(max_vertices))
        reply = g.decode_reply(
            g.execute(
                _request(
                    17,
                    frame.handle,
                    frame.data.identity["sequence"],
                    budget=self.budget,
                    payload=payload,
                )
            )
        )
        self.handle = reply["handle"]
        from ._geo_allocation_recovery import register_geo_allocation_issuer

        register_geo_allocation_issuer(self, self.handle, self._bridge)
        try:
            result = drive_index(
                self.handle, reply["sequence"], self.budget, self._reader, read_page, write_page
            )
            self.page_count = result["data_length"]
            return self
        except BaseException:
            g.execute(_request(10, self.handle))
            raise

    @classmethod
    async def _from_frame_async(cls, frame, source, *, grid, max_vertices, read_page, write_page):
        bridge = source._bridge or g.NativeGeoScaleBridge(source.budget["processor_bytes"])
        self = cls._owner(frame, source, read_page, write_page, bridge)
        original_reader = self._reader

        async def async_reader(ticket):
            value = original_reader(ticket)
            return await value if inspect.isawaitable(value) else value

        self._reader = async_reader
        payload = struct.pack("<IIQ", g._uint(grid, 32), 0, g._uint(max_vertices))
        raw, interrupted = await g._settle(
            asyncio.create_task(
                bridge.execute(
                    _request(
                        17,
                        frame.handle,
                        frame.data.identity["sequence"],
                        budget=self.budget,
                        payload=payload,
                    )
                )
            )
        )
        reply = g.decode_reply(raw)
        self.handle = reply["handle"]
        from ._geo_allocation_recovery import register_geo_allocation_issuer

        register_geo_allocation_issuer(self, self.handle, self._bridge)
        try:
            if interrupted:
                raise asyncio.CancelledError
            result = await drive_index_async(
                bridge,
                self.handle,
                reply["sequence"],
                self.budget,
                self._reader,
                read_page,
                write_page,
            )
            self.page_count = result["data_length"]
            return self
        except BaseException:
            await g._settle(asyncio.create_task(bridge.execute(_request(10, self.handle))))
            raise

    def update(self, query, *, sequence, style):
        self._check()
        if not isinstance(style, bytes) or len(style) != 48:
            raise ValueError("style must be exact 48-byte Rust framing")
        packet = _request(18, self.handle, sequence, budget=self.budget, query=query)
        self._busy = True
        handle = None
        try:
            reply = g.decode_reply(g.execute(packet))
            if reply["code"] == 10:
                raise GeoSpatialFullScanRequired(reply["fallback_reason_code"])
            handle = reply["handle"]
            self._sequence = sequence
            result = drive_index(
                handle, sequence, self.budget, self._reader, self._read_page, self._write_page
            )
            frame = self._prepare(19, handle, sequence, style)
            _attach_frame(self, frame, sequence, packet, style)
            frame.index_stats = result["index_stats"]
        finally:
            try:
                if handle is not None:
                    g.execute(_request(10, handle))
            except BaseException:
                if "frame" in locals():
                    frame.close()
                raise
            finally:
                self._busy = False
        self.current = frame
        return frame

    async def aupdate(self, query, *, sequence, style):
        self._check(True)
        if not isinstance(style, bytes) or len(style) != 48:
            raise ValueError("style must be exact 48-byte Rust framing")
        packet = _request(18, self.handle, sequence, budget=self.budget, query=query)
        self._busy, self._active = True, asyncio.current_task()
        handle = frame = None
        try:
            raw, interrupted = await g._settle(asyncio.create_task(self._bridge.execute(packet)))
            reply = g.decode_reply(raw)
            if reply["code"] == 10:
                if interrupted:
                    raise asyncio.CancelledError
                raise GeoSpatialFullScanRequired(reply["fallback_reason_code"])
            handle = reply["handle"]
            self._sequence = sequence
            if interrupted:
                raise asyncio.CancelledError
            result = await drive_index_async(
                self._bridge,
                handle,
                sequence,
                self.budget,
                self._reader,
                self._read_page,
                self._write_page,
            )
            frame = await _aprepare(self, 19, handle, sequence, style)
            _attach_frame(self, frame, sequence, packet, style)
            frame.index_stats = result["index_stats"]
        finally:
            try:
                if handle is not None:
                    _, interrupted = await g._settle(
                        asyncio.create_task(self._bridge.execute(_request(10, handle)))
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

    def cancel(self):
        if self._busy:
            raise RuntimeError(
                "synchronous storage cannot be cancelled concurrently; fail its callback"
            )

    async def acancel(self):
        if self._active is not None and self._active is not asyncio.current_task():
            self._active.cancel()
