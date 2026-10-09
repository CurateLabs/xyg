"""Explicit retained geographic source owners; geographic policy is Rust-owned."""

from __future__ import annotations

import asyncio
import inspect
import math
import struct
import traceback
import weakref
from contextlib import suppress
from typing import Any

from . import _geoscale as g

_OWNED_DATA_IDENTITIES = weakref.WeakKeyDictionary()


class _OwnedDataIdentity:
    def __init__(self, handle, bridge):
        self.handle, self.bridge = handle, bridge
        self.execute = g.execute if bridge is None else bridge.execute
        self.disposed = False
        self.hooks = []


def on_owned_geo_data_disposed(owner, callback, callback_async):
    """Internal notification on a genuine frame's confirmed original disposal."""
    if retained_frame_issued_authority(owner) is None:
        raise ValueError("Privately issued retained frame required")
    token = _OWNED_DATA_IDENTITIES[owner]()
    if token is None or token.disposed:
        raise RuntimeError("Data disposal already admitted")
    token.hooks.append((callback, callback_async))


def _owned_data_identity(owner):
    token = _OWNED_DATA_IDENTITIES[owner]()
    if token is None:
        raise RuntimeError("Original Data issuer expired")
    return token


def _confirm_data_disposal(packet, handle):
    raw = bytes(g._bytes(packet))
    if (
        len(raw) != 256
        or struct.unpack_from("<4sIIIQQ", raw) != (b"XYGZ", 1, 0, 0, handle, 0)
        or any(raw[32:])
    ):
        raise ValueError("Data disposal acknowledgement mismatch")


class OwnedGeoData:
    """Drop all borrowed views and painters before close/aclose releases the lease."""

    def __init__(self, handle: int, data: Any, bridge: Any = None):
        self.handle, self._data, self._bridge = handle, data, bridge
        self._closed = False
        self._disposal = None
        self._disposal_identity = _OwnedDataIdentity(handle, bridge)
        _OWNED_DATA_IDENTITIES[self] = weakref.ref(self._disposal_identity)

    @property
    def data(self):
        if self._closed or self._data is None:
            raise RuntimeError("geographic data disposed")
        return self._data

    def close(self):
        identity = _owned_data_identity(self)
        if identity.bridge is not None:
            raise RuntimeError("use aclose for an asynchronous owner")
        if not self._closed:
            self._data = None
            if not identity.disposed:
                _confirm_data_disposal(
                    identity.execute(g.encode_request(dict(command=10, handle=identity.handle))),
                    identity.handle,
                )
                identity.disposed = True
            for callback, _ in identity.hooks:
                callback()
            identity.hooks.clear()
            self._closed = True

    async def dispose(self):
        await self.aclose()

    async def aclose(self):
        identity = _owned_data_identity(self)
        if identity.bridge is None:
            self.close()
        elif not self._closed:
            self._data = None
            if not identity.disposed:
                if self._disposal is None:
                    self._disposal = asyncio.create_task(
                        identity.execute(g.encode_request(dict(command=10, handle=identity.handle)))
                    )
                try:
                    raw, interrupted = await g._settle(self._disposal)
                    _confirm_data_disposal(raw, identity.handle)
                    identity.disposed = True
                except BaseException:
                    if self._disposal.done():
                        self._disposal = None
                    raise
            else:
                interrupted = False
            for _, callback_async in identity.hooks:
                await callback_async()
            identity.hooks.clear()
            self._closed = True
            if interrupted:
                raise asyncio.CancelledError


def parse_membership(packet: bytes, handle: int, sequence: int):
    """Borrow exact typed membership records; cursor remains opaque Rust bytes."""
    b = g._bytes(packet)
    if len(b) < 256 or bytes(b[:4]) != b"XYGZ" or struct.unpack_from("<II", b, 4) != (1, 2):
        raise ValueError("invalid membership frame")
    owner, seq, count = struct.unpack_from("<QQQ", b, 16)
    flag, cursor_bytes = struct.unpack_from("<II", b, 72)
    if (
        owner != handle
        or seq != sequence
        or count > 4096
        or flag > 1
        or cursor_bytes != flag * 208
        or len(b) != 256 + cursor_bytes + count * 32
        or any(b[248:256])
        or struct.unpack_from("<Q", b, 80)[0] != handle
    ):
        raise ValueError("invalid membership planes")
    _validate_key(b[88:248])
    if flag and (
        b[256:416] != b[88:248]
        or struct.unpack_from("<I", b, 416)[0] != struct.unpack_from("<I", b, 12)[0]
    ):
        raise ValueError("mismatched membership cursor")
    records = b[256 + cursor_bytes :]
    if any(records[i + 24 : i + 32] != b"\0" * 8 for i in range(0, len(records), 32)):
        raise ValueError("invalid membership record padding")
    return dict(
        packet=b,
        cell=struct.unpack_from("<I", b, 12)[0],
        cursor=bytes(b[256 : 256 + cursor_bytes]) if flag else None,
        records=records,
        count=count,
        key=b[88:248],
        projected_vertices=struct.unpack_from("<Q", b, 40)[0],
    )


class RetainedGeoSource:
    """One Point/MultiPoint source with explicit query/style and independent leases.

    Constructor and update are synchronous and work inside notebook event loops.
    Use create_async/aupdate for an asynchronous reader or transport.
    """

    def __init__(self, manifest: bytes, read_chunk, *, budget: dict):
        self._setup(read_chunk, budget, None)
        reply = g.decode_reply(
            g.execute(g.encode_request(dict(command=4, budget=budget, payload=manifest)))
        )
        self.handle = reply["handle"]
        try:
            self.info = self._drive(0, 3)["source"]
            self._check_kind()
        except BaseException:
            self.close()
            raise

    def _setup(self, reader, budget, bridge):
        if not callable(reader):
            raise TypeError("read_chunk must be callable")
        self._reader, self.budget, self._bridge = reader, dict(budget), bridge
        self._closed, self._busy, self._sequence = False, False, 0
        self._cancel_generation = 0
        self.current = None
        self._active = None
        self._disposal = None

    def _check_kind(self):
        if self.info["geometry"] not in (1, 4):
            raise ValueError("retained point source requires Point or MultiPoint")

    def _check(self, asynchronous=False):
        if self._closed or self._disposal is not None:
            raise RuntimeError("source disposed")
        if self._busy:
            raise RuntimeError("source operation already active")
        if asynchronous != (self._bridge is not None):
            raise RuntimeError("use the matching synchronous/asynchronous source method")

    def _drive(self, sequence, expected, handle=None):
        handle = self.handle if handle is None else handle
        while True:
            reply = g.decode_reply(
                g.execute(
                    g.encode_request(
                        dict(command=6, handle=handle, sequence=sequence, budget=self.budget)
                    )
                )
            )
            if reply["handle"] != handle or reply["sequence"] != sequence:
                raise ValueError("mismatched retained session reply")
            if reply["code"] != 1:
                if reply["code"] != expected:
                    raise RuntimeError("retained session did not complete")
                return reply
            ticket = reply["ticket"]
            authority = bytes(ticket["raw"])
            authorized_bytes = ticket["encoded_bytes"]
            chunk = payload = request = view = None
            try:
                chunk = self._reader({**ticket, "raw": memoryview(authority)})
                if inspect.isawaitable(chunk):
                    if inspect.iscoroutine(chunk):
                        chunk.close()
                    raise TypeError("synchronous source requires a synchronous reader")
                view = g._bytes(chunk)
                if len(view) != authorized_bytes or g._backing_bytes(view) != len(view):
                    raise ValueError("reader must return exact owning chunk storage")
                if 4 * (352 + len(view)) > self.budget["processor_bytes"]:
                    raise ValueError("read transfer exceeds peak budget")
                payload = bytearray(authority) + view
                request = g.encode_request(dict(command=7, handle=handle, payload=payload))
                payload = None
                g.execute(request)
            except BaseException as error:
                chunk = payload = request = view = None
                traceback.clear_frames(error.__traceback__)
                with suppress(Exception):
                    g.execute(g.encode_request(dict(command=9, handle=handle, sequence=sequence)))
                raise
            finally:
                chunk = payload = request = view = None
                g.execute(g.encode_request(dict(command=8, handle=handle, payload=authority)))

    def _prepare(self, command, handle, sequence, style=b"", *, _on_reply=None):
        reply = g.decode_reply(
            g.execute(
                g.encode_request(
                    dict(
                        command=command,
                        handle=handle,
                        sequence=sequence,
                        budget=self.budget,
                        payload=style,
                    )
                )
            )
        )
        if _on_reply is not None:
            _on_reply(reply)
        data_handle = reply["handle"]
        packet = data = None
        try:
            if (
                reply["source_handle"] != handle
                or reply["sequence"] != sequence
                or 4 * reply["data_length"] > self.budget["processor_bytes"]
            ):
                raise ValueError("invalid retained data reply")
            packet = g.read(
                g.encode_request(dict(command=23, handle=data_handle)),
                self.budget["processor_bytes"],
            )
            if len(packet) != reply["data_length"]:
                raise ValueError("mismatched retained packet length")
            data = (
                g.parse_scene_data(packet)
                if command in (11, 19, 26)
                else _parse_aux(command, packet, handle, sequence)
            )
            if command in (11, 19, 26) and (
                data.identity["session_handle"] != handle or data.identity["sequence"] != sequence
            ):
                raise ValueError("mismatched Scene identity")
            return OwnedGeoData(data_handle, data)
        except BaseException as error:
            packet = data = None
            traceback.clear_frames(error.__traceback__)
            g.execute(g.encode_request(dict(command=10, handle=data_handle)))
            raise

    def update(self, query: dict, *, sequence: int, style: bytes):
        self._check()
        if not isinstance(style, bytes) or len(style) != 48:
            raise ValueError("style must be exact 48-byte Rust framing")
        query_packet = g.encode_request(
            dict(command=5, handle=self.handle, sequence=sequence, budget=self.budget, query=query)
        )
        self._busy = True
        try:
            g.execute(query_packet)
            self._sequence = sequence
            self._drive(sequence, 4)
            frame = self._prepare(11, self.handle, sequence, style)
            _attach_frame(self, frame, sequence, query_packet, style)
            self.current = frame
            return frame
        finally:
            self._busy = False

    def membership(
        self,
        cell: int,
        *,
        sequence: int,
        max_projected_vertices: int,
        cursor: bytes | None = None,
        _owner=None,
    ):
        if self._bridge is not None:
            raise RuntimeError("use membership_async for asynchronous sources")
        _owner = _frame_owner(self, _owner)
        payload = _membership_payload(cell, max_projected_vertices, cursor)
        member = g.decode_reply(
            g.execute(
                g.encode_request(
                    dict(
                        command=12,
                        handle=_owner,
                        sequence=sequence,
                        budget=self.budget,
                        payload=payload,
                    )
                )
            )
        )["handle"]
        self._busy = True
        try:
            self._drive(sequence, 4, member)
            return self._prepare(13, member, sequence)
        finally:
            self._busy = False
            g.execute(g.encode_request(dict(command=10, handle=member)))

    def cancel(self):
        self._cancel_generation += 1
        if not self._closed:
            g.execute(
                g.encode_request(dict(command=9, handle=self.handle, sequence=self._sequence))
            )

    def close(self):
        if self._closed:
            return
        self._check()
        g.execute(g.encode_request(dict(command=10, handle=self.handle)))
        self._closed = True

    @classmethod
    async def create_async(cls, manifest, read_chunk, *, budget, bridge=None):
        self = cls.__new__(cls)
        self._setup(read_chunk, budget, bridge or g.NativeGeoScaleBridge(budget["processor_bytes"]))
        raw, interrupted = await g._settle(
            asyncio.create_task(
                self._bridge.execute(
                    g.encode_request(dict(command=4, budget=budget, payload=manifest))
                )
            )
        )
        reply = g.decode_reply(raw)
        self.handle = reply["handle"]
        try:
            if interrupted:
                raise asyncio.CancelledError
            reply = await g.drive_session(
                self._bridge,
                handle=self.handle,
                sequence=0,
                budget=self.budget,
                read_chunk=read_chunk,
            )
            if reply["code"] != 3:
                raise RuntimeError("source validation did not complete")
            self.info = reply["source"]
            self._check_kind()
            return self
        except BaseException:
            await self.aclose()
            raise

    async def aupdate(self, query, *, sequence, style):
        self._check(True)
        if not isinstance(style, bytes) or len(style) != 48:
            raise ValueError("style must be exact 48-byte Rust framing")
        query_packet = g.encode_request(
            dict(command=5, handle=self.handle, sequence=sequence, budget=self.budget, query=query)
        )
        self._busy, self._active = True, asyncio.current_task()
        try:
            _, interrupted = await g._settle(
                asyncio.create_task(self._bridge.execute(query_packet))
            )
            self._sequence = sequence
            if interrupted:
                await self.acancel()
                raise asyncio.CancelledError
            result = await g.drive_session(
                self._bridge,
                handle=self.handle,
                sequence=sequence,
                budget=self.budget,
                read_chunk=self._reader,
            )
            if result["code"] != 4:
                raise RuntimeError("retained update did not complete")
            prepared = await g.prepare_scene_data(
                self._bridge, handle=self.handle, sequence=sequence, budget=self.budget, style=style
            )
            frame = OwnedGeoData(prepared.handle, prepared.data, self._bridge)
            prepared = None
            _attach_frame(self, frame, sequence, query_packet, style)
            self.current = frame
            return frame
        finally:
            self._busy, self._active = False, None

    async def acancel(self):
        if self._active is not None and self._active is not asyncio.current_task():
            self._active.cancel()
        if not self._closed:
            await self._bridge.execute(
                g.encode_request(dict(command=9, handle=self.handle, sequence=self._sequence))
            )

    async def membership_async(self, cell, *, sequence, max_projected_vertices, cursor=None):
        return await _amembership(
            self,
            cell,
            sequence=sequence,
            max_projected_vertices=max_projected_vertices,
            cursor=cursor,
        )

    def pick(self, *, sequence, style, x, y, tolerance, mode, max_hits):
        return _pick(
            self,
            sequence=sequence,
            style=style,
            x=x,
            y=y,
            tolerance=tolerance,
            mode=mode,
            max_hits=max_hits,
        )

    async def pick_async(self, *, sequence, style, x, y, tolerance, mode, max_hits):
        return await _apick(
            self,
            sequence=sequence,
            style=style,
            x=x,
            y=y,
            tolerance=tolerance,
            mode=mode,
            max_hits=max_hits,
        )

    async def aclose(self):
        if self._bridge is None:
            self.close()
            return
        if self._disposal is None:
            self._disposal = asyncio.create_task(self._dispose_async())
        _, interrupted = await g._settle(self._disposal)
        if interrupted:
            raise asyncio.CancelledError

    async def _dispose_async(self):
        if self._closed:
            return
        if self._bridge is None:
            self.close()
            return
        active = self._active
        if active is not None and active is not asyncio.current_task():
            active.cancel()
            with suppress(BaseException):
                await g._settle(active)
        await g._settle(
            asyncio.create_task(
                self._bridge.execute(g.encode_request(dict(command=10, handle=self.handle)))
            )
        )
        self._closed = True


def _membership_payload(cell, max_projected_vertices, cursor):
    if cursor is not None and (not isinstance(cursor, bytes) or len(cursor) != 208):
        raise ValueError("membership cursor must be opaque 208 bytes")
    return struct.pack(
        "<IIQ", g._uint(cell, 32), int(cursor is not None), g._uint(max_projected_vertices)
    ) + (cursor or b"")


def _pick_payload(style, x, y, tolerance, mode, max_hits):
    if not isinstance(style, bytes) or len(style) != 48:
        raise ValueError("style must be exact 48 bytes")
    if any(isinstance(n, bool) or not isinstance(n, (int, float)) for n in (x, y, tolerance)):
        raise TypeError("pick coordinates must be real numbers")
    return style + struct.pack("<dddII", x, y, tolerance, g._uint(mode, 32), g._uint(max_hits, 32))


def parse_picks(packet, handle, sequence):
    b = g._bytes(packet)
    if len(b) < 256 or bytes(b[:4]) != b"XYGZ" or struct.unpack_from("<II", b, 4) != (1, 3):
        raise ValueError("invalid pick frame")
    count = struct.unpack_from("<Q", b, 32)[0]
    mode, cap = struct.unpack_from("<II", b, 40)
    if (
        struct.unpack_from("<QQ", b, 16) != (handle, sequence)
        or struct.unpack_from("<Q", b, 80)[0] != handle
        or mode > 1
        or not 1 <= cap <= 4096
        or count > cap
        or len(b) != 256 + count * 48
        or any(b[12:16])
        or any(b[72:80])
        or any(b[248:256])
    ):
        raise ValueError("invalid pick planes")
    _validate_key(b[88:248])
    if not all(math.isfinite(v) for v in struct.unpack_from("<3d", b, 48)):
        raise ValueError("nonfinite pick coordinates")
    records = b[256:]
    for at in range(0, len(records), 48):
        tag = struct.unpack_from("<I", records, at)[0]
        if tag > 1 or any(records[at + 36 : at + 40]):
            raise ValueError("invalid pick record")
        if tag == 0 and (any(records[at + 32 : at + 36]) or any(records[at + 40 : at + 48])):
            raise ValueError("invalid direct pick")
        if tag == 1 and (
            any(records[at + 4 : at + 32]) or struct.unpack_from("<Q", records, at + 40)[0] == 0
        ):
            raise ValueError("invalid cell pick")
    return dict(packet=b, count=count, records=records, key=b[88:248])


def _pick(self, *, sequence, style, x, y, tolerance, mode, max_hits, _owner=None):
    if self._bridge is not None:
        raise RuntimeError("use pick_async for asynchronous sources")
    _owner = _frame_owner(self, _owner)
    payload = _pick_payload(style, x, y, tolerance, mode, max_hits)
    return self._prepare(14, _owner, sequence, payload)


async def _aprepare(self, command, handle, sequence, payload=b"", *, _on_reply=None):
    raw, interrupted = await g._settle(
        asyncio.create_task(
            self._bridge.execute(
                g.encode_request(
                    dict(
                        command=command,
                        handle=handle,
                        sequence=sequence,
                        budget=self.budget,
                        payload=payload,
                    )
                )
            )
        )
    )
    reply = g.decode_reply(raw)
    if _on_reply is not None:
        _on_reply(reply)
    packet = data = None
    try:
        if interrupted:
            raise asyncio.CancelledError
        if (
            reply["source_handle"] != handle
            or reply["sequence"] != sequence
            or 4 * reply["data_length"] > self.budget["processor_bytes"]
        ):
            raise ValueError("invalid retained data reply")
        task = asyncio.create_task(
            self._bridge.read(g.encode_request(dict(command=23, handle=reply["handle"])))
        )
        packet, interrupted = await g._settle(task)
        task = None
        if interrupted:
            raise asyncio.CancelledError
        if len(packet) != reply["data_length"]:
            raise ValueError("invalid retained packet length")
        data = (
            g.parse_scene_data(packet)
            if command in (19, 26)
            else _parse_aux(command, packet, handle, sequence)
        )
        if command in (19, 26) and (
            data.identity["session_handle"] != handle or data.identity["sequence"] != sequence
        ):
            raise ValueError("mismatched Scene identity")
        return OwnedGeoData(reply["handle"], data, self._bridge)
    except BaseException as error:
        packet = data = task = None
        traceback.clear_frames(error.__traceback__)
        await g._settle(
            asyncio.create_task(
                self._bridge.execute(g.encode_request(dict(command=10, handle=reply["handle"])))
            )
        )
        raise


async def _amembership(self, cell, *, sequence, max_projected_vertices, cursor=None, _owner=None):
    if self._bridge is None:
        raise RuntimeError("use synchronous membership/pick for this source")
    _owner = _frame_owner(self, _owner)
    payload = _membership_payload(cell, max_projected_vertices, cursor)
    self._busy, self._active = True, asyncio.current_task()
    member = page = None
    try:
        raw, interrupted = await g._settle(
            asyncio.create_task(
                self._bridge.execute(
                    g.encode_request(
                        dict(
                            command=12,
                            handle=_owner,
                            sequence=sequence,
                            budget=self.budget,
                            payload=payload,
                        )
                    )
                )
            )
        )
        member = g.decode_reply(raw)["handle"]
        if interrupted:
            raise asyncio.CancelledError
        result = await g.drive_session(
            self._bridge,
            handle=member,
            sequence=sequence,
            budget=self.budget,
            read_chunk=self._reader,
        )
        if result["code"] != 4:
            raise RuntimeError("membership did not complete")
        page = await _aprepare(self, 13, member, sequence)
        return page
    finally:
        try:
            if member is not None:
                _, interrupted = await g._settle(
                    asyncio.create_task(
                        self._bridge.execute(g.encode_request(dict(command=10, handle=member)))
                    )
                )
                if interrupted:
                    if page is not None:
                        await page.aclose()
                    raise asyncio.CancelledError
        except BaseException:
            if page is not None:
                await page.aclose()
            raise
        finally:
            self._busy, self._active = False, None


async def _apick(self, *, sequence, style, x, y, tolerance, mode, max_hits, _owner=None):
    if self._bridge is None:
        raise RuntimeError("use synchronous membership/pick for this source")
    _owner = _frame_owner(self, _owner)
    payload = _pick_payload(style, x, y, tolerance, mode, max_hits)
    self._busy, self._active = True, asyncio.current_task()
    try:
        return await _aprepare(self, 14, _owner, sequence, payload)
    finally:
        self._busy, self._active = False, None


def _frame_owner(source, owner):
    if source._busy:
        raise RuntimeError("source operation already active")
    if owner is None:
        if source.current is None:
            raise RuntimeError("no published frame")
        _ = source.current.data
        return source.current.handle
    return owner


_FRAME_AUTHORITIES: weakref.WeakKeyDictionary[Any, tuple[Any, ...]] = weakref.WeakKeyDictionary()


def retained_frame_authority(frame):
    """Internal immutable producer/transport provenance; numeric handles are local."""
    record = _FRAME_AUTHORITIES.get(frame)
    if record is None:
        return None
    source = record[0]()
    if source is None or id(source._bridge) != record[2]:
        return None
    if record[1] is not None and record[1]() is not source._bridge:
        return None
    return source, source._bridge


def retained_frame_issued_authority(frame):
    """Private immutable numeric/publication framing; never public attribute authority."""
    producer = retained_frame_authority(frame)
    record = _FRAME_AUTHORITIES.get(frame)
    if producer is None or record is None:
        return None
    return (*producer, *record[3:])


def _attach_frame(source, frame, sequence, query_packet, style, _provenance=None):
    try:
        bridge = weakref.ref(source._bridge) if source._bridge is not None else None
    except TypeError:
        bridge = None
    _FRAME_AUTHORITIES[frame] = (
        weakref.ref(source),
        bridge,
        id(source._bridge),
        frame.handle,
        sequence,
        bytes(query_packet),
        frame.data.selection is not None,
        bytes(frame.data.packet[:256]),
    )
    if _provenance is not None:
        _provenance(frame)

    def membership(cell, *, max_projected_vertices, cursor=None):
        _ = frame.data
        return source.membership(
            cell,
            sequence=sequence,
            max_projected_vertices=max_projected_vertices,
            cursor=cursor,
            _owner=frame.handle,
        )

    def pick(*, style, x, y, tolerance, mode, max_hits):
        _ = frame.data
        return _pick(
            source,
            sequence=sequence,
            style=style,
            x=x,
            y=y,
            tolerance=tolerance,
            mode=mode,
            max_hits=max_hits,
            _owner=frame.handle,
        )

    async def membership_async(cell, *, max_projected_vertices, cursor=None):
        _ = frame.data
        return await _amembership(
            source,
            cell,
            sequence=sequence,
            max_projected_vertices=max_projected_vertices,
            cursor=cursor,
            _owner=frame.handle,
        )

    async def pick_async(*, style, x, y, tolerance, mode, max_hits):
        _ = frame.data
        return await _apick(
            source,
            sequence=sequence,
            style=style,
            x=x,
            y=y,
            tolerance=tolerance,
            mode=mode,
            max_hits=max_hits,
            _owner=frame.handle,
        )

    def export(format="png", **options):
        from ._geo_snapshot import export_frame

        return export_frame(frame, sequence, format, **options)

    async def export_async(format="png", **options):
        from ._geo_snapshot import export_frame_async

        return await export_frame_async(frame, sequence, format, **options)

    def retain():
        if source._bridge is not None:
            raise RuntimeError("use retain_async for an asynchronous owner")
        _ = frame.data
        owned = source._prepare(26, frame.handle, sequence)
        _attach_frame(source, owned, sequence, query_packet, style, _provenance)
        if hasattr(frame, "index_stats"):
            owned.index_stats = dict(frame.index_stats)
        return owned

    async def retain_async():
        _ = frame.data
        if source._bridge is None:
            return retain()
        owned = await _aprepare(source, 26, frame.handle, sequence)
        _attach_frame(source, owned, sequence, query_packet, style, _provenance)
        if hasattr(frame, "index_stats"):
            owned.index_stats = dict(frame.index_stats)
        return owned

    frame.retain, frame.retain_async = retain, retain_async
    frame._source = source
    frame._query_packet = query_packet
    frame._style = bytes(style)
    frame.export, frame.export_async = export, export_async
    frame.membership, frame.pick = membership, pick
    frame.membership_async, frame.pick_async = membership_async, pick_async
    rows_owner = frame.handle

    def rows():
        _ = frame.data
        return _rows(source, rows_owner, sequence)

    async def rows_async():
        _ = frame.data
        return await _arows(source, rows_owner, sequence)

    frame.rows, frame.rows_async = rows, rows_async

    def spatial_index(*, grid, max_vertices, read_page, write_page):
        from ._geo_spatial import GeoSpatialIndex

        return GeoSpatialIndex._from_frame(
            frame,
            source,
            grid=grid,
            max_vertices=max_vertices,
            read_page=read_page,
            write_page=write_page,
        )

    async def spatial_index_async(*, grid, max_vertices, read_page, write_page):
        from ._geo_spatial import GeoSpatialIndex

        return await GeoSpatialIndex._from_frame_async(
            frame,
            source,
            grid=grid,
            max_vertices=max_vertices,
            read_page=read_page,
            write_page=write_page,
        )

    frame.spatial_index, frame.spatial_index_async = spatial_index, spatial_index_async


def _validate_key(key):
    if len(key) != 160 or any(key[156:160]):
        raise ValueError("invalid geographic key framing")
    if (
        struct.unpack_from("<I", key, 24)[0] not in (4326, 3857)
        or struct.unpack_from("<I", key, 28)[0] not in (1, 4)
        or struct.unpack_from("<I", key, 56)[0] not in (4326, 3857)
        or struct.unpack_from("<I", key, 60)[0] > 1
        or struct.unpack_from("<I", key, 120)[0] > 2
        or struct.unpack_from("<I", key, 124)[0] > 1
        or struct.unpack_from("<I", key, 144)[0] > 1
        or not all(math.isfinite(n) for n in struct.unpack_from("<7d", key, 64))
    ):
        raise ValueError("invalid typed geographic key")


class GeoRowsData:
    """Borrowed bounded row planes; record extraction allocates only one row."""

    def __init__(self, packet, owner, sequence):
        b = g._bytes(packet)
        bad = "invalid geographic rows packet"
        if (
            len(b) < 256
            or bytes(b[:4]) != b"XYGZ"
            or (
                struct.unpack_from("<I", b, 4)[0] not in (1, 2)
                or struct.unpack_from("<I", b, 8)[0] != 4
            )
        ):
            raise ValueError(bad)

        def u32(at):
            return struct.unpack_from("<I", b, at)[0]

        def u64(at):
            return struct.unpack_from("<Q", b, at)[0]

        def signed(at):
            return struct.unpack_from("<q", b, at)[0]

        count, flag, source_rows = u64(32), u32(40), u64(104)
        footer_len = u64(248)
        if (
            u64(16) != owner
            or u64(24) != sequence
            or u64(80) != owner
            or count > 4096
            or flag > 1
            or len(b) != 256 + count * 64 + footer_len
            or source_rows > 1_000_000_000
            or not u64(96)
            or u32(112) not in range(1, 7)
            or u32(116) not in (4326, 3857)
            or u32(152) > 2
            or (u32(152) == 0 and (u64(160) or u64(168)))
            or (u32(152) == 1 and u64(168))
            or (u32(152) == 2 and signed(160) >= signed(168))
            or any(b[12:16])
            or any(b[44:48])
            or any(b[72:80])
            or any(b[156:160])
            or any(b[176:248])
            or (u32(4) == 1 and footer_len)
            or u32(64) > 65536
            or u32(68) > 65536
        ):
            raise ValueError(bad)
        previous = -1
        for i in range(count):
            at = 256 + i * 64
            flags = u32(at + 24)
            row = u64(at + 8)
            if (
                flags & ~(255 if u32(4) == 2 else 127)
                or row >= source_rows
                or row <= previous
                or u32(at + 16) >= 65536
                or u32(at + 20) >= 65536
                or bool(flags & 4) != (not bool(flags & 1) and bool(flags & 2))
                or (not flags & 8 and flags & 48)
                or (not flags & 16 and u64(at + 32))
                or (not flags & 32 and u64(at + 40))
                or (flags & 48 == 48 and signed(at + 32) >= signed(at + 40))
                or (not flags & 64 and u64(at + 48))
                or any(b[at + 28 : at + 32])
                or any(b[at + 56 : at + 64])
            ):
                raise ValueError(bad)
            previous = row
        self.selection = g.parse_selection_footer(b, 256 + count * 64, rows=True)
        if self.selection is not None:
            import numpy as np

            ids = self.selection["ids"]
            for i in range(count):
                feature = u64(256 + i * 64)
                pos = int(np.searchsorted(ids, np.uint64(feature)))
                selected = pos < len(ids) and int(ids[pos]) == feature
                if bool(u32(256 + i * 64 + 24) & 128) != selected:
                    raise ValueError("selected row intent mismatch")
        self.packet, self.records = b, b[256 : 256 + count * 64]
        self.count, self.has_next = count, bool(flag)
        self.key = b[88:176]
        self.rows_examined, self.bytes_read = u64(48), u64(56)
        self.chunks_read, self.chunks_considered = u32(64), u32(68)

    def record(self, index):
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < self.count:
            raise IndexError("geographic row index")
        at = index * 64
        feature, source_row, chunk, row, flags = struct.unpack_from("<QQIII", self.records, at)
        start, end, value = struct.unpack_from("<qqd", self.records, at + 32)
        return dict(
            feature_id=feature,
            source_row=source_row,
            chunk_index=chunk,
            row=row,
            selected=bool(flags & 128),
            geometry_null=bool(flags & 1),
            time_eligible=bool(flags & 2),
            eligible=bool(flags & 4),
            intervals_present=bool(flags & 8),
            interval_start=start if flags & 16 else None,
            interval_end=end if flags & 32 else None,
            value=value if flags & 64 else None,
        )


def _parse_aux(command, packet, owner, sequence):
    parser = {13: parse_membership, 14: parse_picks, 16: GeoRowsData}[command]
    return parser(packet, owner, sequence)


def _attach_rows(source, page, sequence):
    owner = page.handle

    def next_page():
        if not page.data.has_next:
            raise RuntimeError("no next geographic row page")
        return _rows(source, owner, sequence)

    async def next_page_async():
        if not page.data.has_next:
            raise RuntimeError("no next geographic row page")
        return await _arows(source, owner, sequence)

    page.next_page, page.next_page_async = next_page, next_page_async
    return page


def _rows(source, owner, sequence):
    if source._bridge is not None:
        raise RuntimeError("use rows_async for asynchronous sources")
    _frame_owner(source, owner)
    session = page = None
    source._busy = True
    try:
        created = g.decode_reply(
            g.execute(
                g.encode_request(
                    dict(
                        command=15,
                        handle=owner,
                        sequence=sequence,
                        budget=source.budget,
                    )
                )
            )
        )
        session = created["handle"]
        if created["sequence"] != sequence:
            raise ValueError("mismatched geographic rows sequence")
        source._drive(sequence, 4, session)
        page = _attach_rows(source, source._prepare(16, session, sequence), sequence)
        return page
    finally:
        try:
            if session is not None:
                try:
                    g.execute(g.encode_request(dict(command=10, handle=session)))
                except BaseException:
                    if page is not None:
                        page.close()
                    raise
        finally:
            source._busy = False


async def _arows(source, owner, sequence):
    if source._bridge is None:
        raise RuntimeError("use synchronous rows for this source")
    _frame_owner(source, owner)
    source._busy, source._active = True, asyncio.current_task()
    session = page = None
    try:
        raw, interrupted = await g._settle(
            asyncio.create_task(
                source._bridge.execute(
                    g.encode_request(
                        dict(command=15, handle=owner, sequence=sequence, budget=source.budget)
                    )
                )
            )
        )
        created = g.decode_reply(raw)
        session = created["handle"]
        if interrupted:
            raise asyncio.CancelledError
        if created["sequence"] != sequence:
            raise ValueError("mismatched geographic rows sequence")
        completed = await g.drive_session(
            source._bridge,
            handle=session,
            sequence=sequence,
            budget=source.budget,
            read_chunk=source._reader,
        )
        if completed["code"] != 4:
            raise RuntimeError("geographic rows did not complete")
        page = _attach_rows(source, await _aprepare(source, 16, session, sequence), sequence)
        return page
    finally:
        try:
            if session is not None:
                _, interrupted = await g._settle(
                    asyncio.create_task(
                        source._bridge.execute(g.encode_request(dict(command=10, handle=session)))
                    )
                )
                if interrupted:
                    if page is not None:
                        await page.aclose()
                    raise asyncio.CancelledError
        except BaseException:
            if page is not None:
                await page.aclose()
            raise
        finally:
            source._busy, source._active = False, None
