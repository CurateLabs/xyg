"""Issued temporal-overview data sources for the existing geographic composition.

Dossier §27/§29/§34. Counts are temporal-exact data-domain populations, not final
screen cells or source feature IDs. Rust alone owns every count and paint policy.
"""

from __future__ import annotations

import asyncio
import struct
import traceback
import weakref
from contextlib import suppress
from types import MappingProxyType, SimpleNamespace
from typing import Any

from . import _geo_overview as wire
from . import _geo_overview_members as members_wire
from . import _geoscale as g
from ._geo_retained import retained_frame_issued_authority

_INDEX = weakref.WeakKeyDictionary()
_FRAME = weakref.WeakKeyDictionary()
_TRANSPORTS = weakref.WeakKeyDictionary()
_IDENTITIES = weakref.WeakKeyDictionary()
_REQUESTS = weakref.WeakKeyDictionary()
_PARENTS = weakref.WeakKeyDictionary()
_BUDGETS = weakref.WeakKeyDictionary()


def _parent(owner):
    index = _PARENTS[owner]()
    if index is None:
        raise RuntimeError("Issued overview index expired")
    return index


class _IssuedTransport:
    def __init__(self, bridge):
        self.bridge = bridge
        self.execute = bridge.execute if bridge is not None else None
        self.read = bridge.read if bridge is not None else None
        self.native_execute, self.native_read = g.execute, g.read


def _transport(owner):
    token = _TRANSPORTS[owner]()
    if token is None:
        raise RuntimeError("Issued overview producer expired")
    return token


def _bind_transport(owner, token):
    owner._issued_transport = token
    _TRANSPORTS[owner] = weakref.ref(token)


class GeoOverviewUncertainAllocation(RuntimeError):
    """The issued guard remains reachable; no unknown numeric owner is guessed."""

    def __init__(self, owner):
        self.owner = owner
        super().__init__(
            "Overview allocation confirmation uncertain; protocol recovery is required"
        )


class GeoOverviewCleanupPending(RuntimeError):
    def __init__(self, owner):
        self.owner = owner
        super().__init__("Overview Data cleanup remains pending; retry owner.close/aclose")


class GeoOverviewUnsupportedDomain(RuntimeError):
    pass


def overview_index_authority(index):
    a = _INDEX.get(index)
    return None if a is None else (a[0]().bridge, *a[1:])


def overview_frame_authority(frame):
    a = _FRAME.get(frame)
    return None if a is None else (a[0](), a[1]().bridge, *a[2:])


def _sync_drive(owner):
    """Blocking native callbacks, including in a running notebook event loop."""

    def command(op, payload=b""):
        return wire.request(op, owner.handle, owner.sequence, budget=owner.budget, payload=payload)

    while True:
        receipt = wire.reply(_transport(owner).native_execute(command(6)))
        if receipt["handle"] != owner.handle or receipt["sequence"] != owner.sequence:
            raise ValueError("mismatched overview operation")
        if receipt["code"] in (13, 14, 15):
            return receipt
        if receipt["code"] not in (1, 7) or receipt["ticket"] is None:
            raise RuntimeError("overview did not complete")
        ticket = receipt["ticket"]
        authority, kind, length = bytes(ticket["raw"]), ticket["kind"], ticket["encoded_bytes"]
        owner._pending_loan = (31 if kind == 3 else 8, authority)
        borrowed = view = packet = None
        try:
            if 4 * (256 + 128 + length) > owner.budget["processor_bytes"]:
                raise ValueError("overview transfer exceeds budget")
            if kind == 3:
                borrowed = _transport(owner).native_read(
                    command(30, authority), owner.budget["processor_bytes"]
                )
                view = g._bytes(borrowed)
                if len(view) != length or g._backing_bytes(view) != length:
                    raise ValueError("exact owning overview write required")
                owner._storage[2](dict(ticket), view)
            else:
                borrowed = owner._storage[0 if kind == 1 else 1](dict(ticket))
                view = g._bytes(borrowed)
                if len(view) != length or g._backing_bytes(view) != length:
                    raise ValueError("exact owning overview read required")
                packet = authority + bytes(view)
                wire.validate_mutation(
                    _transport(owner).native_execute(command(7, packet)),
                    owner.handle,
                    owner.sequence,
                )
        except BaseException as error:
            borrowed = view = packet = None
            traceback.clear_frames(error.__traceback__)
            wire.validate_mutation(
                _transport(owner).native_execute(command(9)), owner.handle, owner.sequence
            )
            raise
        finally:
            borrowed = view = packet = None
            _settle_sync_loan(owner)


def _settle_sync_loan(owner):
    loan = getattr(owner, "_pending_loan", None)
    if loan is not None:
        command, authority = loan
        try:
            wire.validate_mutation(
                _transport(owner).native_execute(
                    wire.request(command, owner.handle, owner.sequence, payload=authority)
                ),
                owner.handle,
                owner.sequence,
            )
        except BaseException:
            wire.validate_mutation(
                _transport(owner).native_execute(wire.request(9, owner.handle, owner.sequence)),
                owner.handle,
                owner.sequence,
            )
            raw = _transport(owner).native_execute(wire.request(6, owner.handle, owner.sequence))
            terminal = wire.reply(raw)
            if terminal["code"] == 9 and any(g._bytes(raw)[32:256]):
                raise ValueError("nonzero overview cancellation reserved bytes") from None
            if (
                terminal["code"] != 9
                or terminal["handle"] != owner.handle
                or terminal["sequence"] != owner.sequence
                or terminal["ticket"] is not None
            ):
                raise ValueError("Overview loan settlement remains pending") from None
        owner._pending_loan = None


async def _close_known(owner, bridge, packet, finish):
    await wire.settle_loan(
        bridge, struct.unpack_from("<Q", packet, 16)[0], struct.unpack_from("<Q", packet, 24)[0]
    )
    if owner._disposal is None:
        owner._disposal = asyncio.create_task(bridge.execute(packet))
    task = owner._disposal
    try:
        raw, interrupted = await g._settle(task)
        wire.validate_mutation(
            raw, struct.unpack_from("<Q", packet, 16)[0], struct.unpack_from("<Q", packet, 24)[0]
        )
    except BaseException:
        if task.done():
            owner._disposal = None
        raise
    finish()
    if interrupted:
        raise asyncio.CancelledError


class GeoOverviewIndex:
    """One issued immutable index, with independent explicit query snapshots."""

    _bridge: Any
    _budget: dict[str, Any]
    _sequence: int
    _request: bytes
    _issued_transport: _IssuedTransport
    _disposal: Any
    _active: GeoOverviewQuery | None
    _current: GeoOverviewFrame | None
    _storage: Any

    def __init__(self):
        raise TypeError("use GeoOverviewIndex.from_frame or from_frame_async")

    @classmethod
    def _capture(cls, frame, source, *, budget, max_vertices, read_chunk, read_page, write_page):
        authority = retained_frame_issued_authority(frame)
        if authority is None or authority[0] is not source:
            raise ValueError("overview requires its privately issued retained source frame")
        _, bridge, handle, sequence, request, selected, header = authority
        if frame.handle != handle or frame._query_packet != request:
            raise ValueError("mutated frame owner or authoring request")
        if selected:
            raise wire.GeoOverviewUnsupportedSelected("Temporal overview cannot retain selection")
        if not g._uint(max_vertices):
            raise ValueError("nonzero u64 vertex ceiling required")
        owner = object.__new__(cls)
        owner._bridge, owner._budget = (
            bridge,
            {
                key: budget[key]
                for key in (
                    "processor_bytes",
                    "max_rows_examined",
                    "max_read_bytes",
                    "max_chunks",
                    "page_rows",
                )
            },
        )
        owner._storage = (read_chunk, read_page, write_page)
        owner._sequence = sequence
        owner._handle, owner._phase = 0, "building"
        owner._active, owner._current, owner._disposal = None, None, None
        owner._request = wire.request(
            27, handle, sequence, budget=owner._budget, payload=struct.pack("<Q", max_vertices)
        )
        _BUDGETS[owner] = MappingProxyType(dict(owner._budget))
        _IDENTITIES[owner] = (0, sequence)
        _REQUESTS[owner] = bytes(owner._request)
        _bind_transport(owner, _IssuedTransport(bridge))
        _INDEX[owner] = (weakref.ref(owner._issued_transport), sequence, bytes(header))
        return owner

    @classmethod
    def from_frame(cls, frame, source, **options):
        owner = cls._capture(frame, source, **options)
        if _transport(owner).bridge is not None:
            raise RuntimeError("use from_frame_async with an asynchronous producer")
        try:
            owner._admitted(wire.reply(_transport(owner).native_execute(_REQUESTS[owner])))
        except BaseException as error:
            owner._phase = "uncertain"
            raise GeoOverviewUncertainAllocation(owner) from error
        try:
            if _sync_drive(owner)["code"] != 13:
                raise RuntimeError("overview builder did not become a validated index")
            owner._phase = "ready"
            return owner
        except BaseException:
            owner.close()
            raise

    @classmethod
    async def from_frame_async(cls, frame, source, **options):
        owner = cls._capture(frame, source, **options)
        if _transport(owner).bridge is None:
            return cls.from_frame(frame, source, **options)
        try:
            raw, interrupted = await g._settle(
                asyncio.create_task(_transport(owner).execute(_REQUESTS[owner]))
            )
            owner._admitted(wire.reply(raw))
            if interrupted:
                raise asyncio.CancelledError
        except BaseException as error:
            if not owner._handle:
                owner._phase = "uncertain"
                raise GeoOverviewUncertainAllocation(owner) from error
            await owner.aclose()
            raise
        try:
            result = await wire.drive(
                _transport(owner),
                handle=owner.handle,
                sequence=owner.sequence,
                budget=_BUDGETS[owner],
                read_chunk=owner._storage[0],
                read_page=owner._storage[1],
                write_page=owner._storage[2],
            )
            if result["code"] != 13:
                raise RuntimeError("overview builder did not become a validated index")
            owner._phase = "ready"
            return owner
        except BaseException:
            await owner.aclose()
            raise

    def _admitted(self, receipt):
        if receipt["code"] != 0 or not receipt["handle"] or receipt["sequence"] != self.sequence:
            raise ValueError("invalid overview builder receipt")
        self._handle = receipt["handle"]
        _IDENTITIES[self] = (self._handle, self.sequence)

    @property
    def handle(self):
        return _IDENTITIES[self][0]

    @property
    def sequence(self):
        return _IDENTITIES[self][1]

    @property
    def budget(self):
        return dict(_BUDGETS[self])

    @property
    def current(self):
        return self._current

    @property
    def pending_operation(self):
        return self if self._phase == "uncertain" else self._active

    def _begin(self, query, sequence):
        if self._phase != "ready" or self._active is not None:
            raise RuntimeError("Overview index closed, busy or has unresolved allocation")
        packet = wire.request(28, self.handle, sequence, budget=_BUDGETS[self], query=query)
        operation = GeoOverviewQuery(self, packet, sequence)
        self._active = operation
        return operation

    def update(self, query, *, sequence):
        if _transport(self).bridge is not None:
            raise RuntimeError("use update_async for an asynchronous producer")
        operation = self._begin(query, sequence)
        frame = None
        try:
            operation.admit()
            result = _sync_drive(operation)
            if result["code"] == 15:
                raise GeoOverviewUnsupportedDomain("No source scan was substituted")
            if result["code"] != 14:
                raise RuntimeError("overview query did not complete")
            operation._phase = "complete"
            frame = operation.prepare()
            operation.close()
            self._current = frame
            return frame
        except BaseException:
            if frame is not None:
                try:
                    frame.close()
                except BaseException as error:
                    raise GeoOverviewCleanupPending(frame) from error
            if operation._phase != "uncertain":
                operation.close()
            raise

    async def update_async(self, query, *, sequence, cancel_event=None):
        if _transport(self).bridge is None:
            return self.update(query, sequence=sequence)
        operation = self._begin(query, sequence)
        frame = None
        operation._processing = asyncio.current_task()
        try:
            await operation.admit_async()
            result = await wire.drive(
                _transport(self),
                handle=operation.handle,
                sequence=sequence,
                budget=_BUDGETS[self],
                read_chunk=self._storage[0],
                read_page=self._storage[1],
                write_page=self._storage[2],
                cancel_event=cancel_event,
            )
            if result["code"] == 15:
                raise GeoOverviewUnsupportedDomain("No source scan was substituted")
            if result["code"] != 14:
                raise RuntimeError("overview query did not complete")
            if self._phase != "ready" or (cancel_event is not None and cancel_event.is_set()):
                raise asyncio.CancelledError
            operation._phase = "complete"
            frame = await operation.prepare_async()
            await operation.aclose()
            if self._phase != "ready" or (cancel_event is not None and cancel_event.is_set()):
                await frame.aclose()
                raise asyncio.CancelledError
            self._current = frame
            return frame
        except BaseException:
            if frame is not None:
                try:
                    await frame.aclose()
                except BaseException as error:
                    raise GeoOverviewCleanupPending(frame) from error
            if operation._phase != "uncertain":
                await operation.aclose()
            raise
        finally:
            operation._processing = None

    def _finished_close(self):
        self._phase = "closed"
        self._storage = None

    def close(self):
        if self._phase == "closed":
            return
        if self._phase == "uncertain":
            raise GeoOverviewUncertainAllocation(self)
        if _transport(self).bridge is not None:
            raise RuntimeError("use aclose")
        self._phase = "closing"
        if self._active is not None:
            self._active.close()
        _settle_sync_loan(self)
        wire.validate_mutation(
            _transport(self).native_execute(wire.request(10, self.handle, self.sequence)),
            self.handle,
            self.sequence,
        )
        self._phase = "closed"
        self._storage = None

    async def aclose(self):
        if _transport(self).bridge is None:
            return self.close()
        if self._phase == "closed":
            return
        if self._phase == "uncertain":
            raise GeoOverviewUncertainAllocation(self)
        self._phase = "closing"
        if self._active is not None:
            await self._active.aclose()
        await _close_known(
            self,
            _transport(self),
            wire.request(10, self.handle, self.sequence),
            self._finished_close,
        )


class GeoOverviewQuery:
    def __init__(self, index, request, sequence):
        self._index, self._request, self._sequence = index, request, sequence
        self._issued_parent = index
        _PARENTS[self] = weakref.ref(index)
        _BUDGETS[self] = _BUDGETS[index]
        _bind_transport(self, _transport(index))
        _IDENTITIES[self] = (0, sequence)
        _REQUESTS[self] = bytes(request)
        self._handle, self._phase = 0, "admitting"
        self._disposal = self._admission = self._processing = None
        self._publication = None
        self._storage, self._budget = index._storage, index._budget

    @property
    def handle(self):
        return _IDENTITIES[self][0]

    @property
    def sequence(self):
        return _IDENTITIES[self][1]

    @property
    def budget(self):
        return dict(_BUDGETS[self])

    def _admitted(self, raw):
        if self._phase == "closed":
            return
        receipt = wire.reply(raw)
        if receipt["code"] != 0 or not receipt["handle"] or receipt["sequence"] != self.sequence:
            raise ValueError("invalid overview query receipt")
        self._handle, self._phase = receipt["handle"], "issued"
        _IDENTITIES[self] = (self._handle, self.sequence)

    def admit(self):
        try:
            self._admitted(_transport(self).native_execute(_REQUESTS[self]))
        except BaseException as error:
            self._phase = "uncertain"
            raise GeoOverviewUncertainAllocation(self) from error

    async def admit_async(self):
        try:
            if self._admission is None:
                self._admission = asyncio.create_task(_transport(self).execute(_REQUESTS[self]))
            raw, interrupted = await g._settle(self._admission)
            self._admitted(raw)
            if interrupted:
                raise asyncio.CancelledError
        except BaseException as error:
            if not self.handle:
                self._phase = "uncertain"
                raise GeoOverviewUncertainAllocation(self) from error
            raise

    def prepare(self):
        if self._phase != "complete":
            raise RuntimeError("Overview query is not complete")
        if self._publication is not None:
            raise RuntimeError("Frame publication already attempted")
        frame = self._publication = GeoOverviewFrame(_parent(self), self.sequence, _REQUESTS[self])
        try:
            frame._publish(self.handle)
        except BaseException:
            if frame._phase == "uncertain":
                self._phase = "uncertain"
            raise
        return frame

    async def prepare_async(self):
        if self._phase != "complete":
            raise RuntimeError("Overview query is not complete")
        if self._publication is not None:
            raise RuntimeError("Frame publication already attempted")
        frame = self._publication = GeoOverviewFrame(_parent(self), self.sequence, _REQUESTS[self])
        try:
            await frame._publish_async(self.handle)
        except BaseException:
            if frame._phase == "uncertain":
                self._phase = "uncertain"
            raise
        return frame

    def close(self):
        if self._phase == "closed":
            return
        if self._phase == "uncertain":
            raise GeoOverviewUncertainAllocation(self)
        _settle_sync_loan(self)
        wire.validate_mutation(
            _transport(self).native_execute(wire.request(10, self.handle, self.sequence)),
            self.handle,
            self.sequence,
        )
        self._phase = "closed"
        self._storage = self._publication = None
        if _parent(self)._active is self:
            _parent(self)._active = None

    async def aclose(self):
        if self._admission is not None:
            with suppress(BaseException):
                raw, _ = await g._settle(self._admission)
                if self._phase == "admitting":
                    self._admitted(raw)
        if _transport(self).bridge is None:
            return self.close()
        if self._phase == "closed":
            return
        if self._phase == "uncertain":
            raise GeoOverviewUncertainAllocation(self)

        if self._processing is not None and self._processing is not asyncio.current_task():
            raw, _ = await g._settle(
                asyncio.create_task(
                    _transport(self).execute(wire.request(9, self.handle, self.sequence))
                )
            )
            wire.validate_mutation(raw, self.handle, self.sequence)
            with suppress(BaseException):
                await g._settle(self._processing)
            if self._phase == "closed":
                return
            if self._phase == "uncertain":
                raise GeoOverviewUncertainAllocation(self)

        if self._publication is not None and self._publication not in _FRAME:
            await self._publication.aclose()

        def finished():
            self._phase = "closed"
            self._storage = self._publication = None
            if _parent(self)._active is self:
                _parent(self)._active = None

        await _close_known(
            self, _transport(self), wire.request(10, self.handle, self.sequence), finished
        )


class GeoOverviewFrame:
    def __init__(self, index, sequence, request):
        self._index, self._bridge = index, _transport(index).bridge
        self._issued_parent = index
        _PARENTS[self] = weakref.ref(index)
        _BUDGETS[self] = _BUDGETS[index]
        _bind_transport(self, _transport(index))
        self._sequence, self._request = sequence, bytes(request)
        _IDENTITIES[self] = (0, sequence)
        _REQUESTS[self] = bytes(request)
        self._handle, self._phase, self._data = 0, "new", None
        self._disposal = self._retention = None
        self._freeze_command = 6
        self._membership_reader = index._storage[0] if index._storage is not None else None

    @property
    def handle(self):
        return _IDENTITIES[self][0]

    @property
    def sequence(self):
        return _IDENTITIES[self][1]

    @property
    def data(self):
        if self._data is None:
            raise RuntimeError("Overview frame disposed or unpublished")
        return self._data

    def _receipt(self, raw, expected, source):
        receipt = wire.reply(raw)
        if (
            receipt["code"] != expected
            or not receipt["handle"]
            or receipt["sequence"] != self.sequence
            or receipt["source_handle"] != source
            or receipt["data_length"] > g.MAX_PACKET
            or 4 * receipt["data_length"] > _BUDGETS[self]["processor_bytes"]
        ):
            raise ValueError("invalid overview Data receipt")
        self._handle, self._phase = receipt["handle"], "owned"
        _IDENTITIES[self] = (self._handle, self.sequence)
        return receipt["data_length"]

    def _parsed(self, packet, length, source):
        if len(packet) != length:
            raise ValueError("overview Data length mismatch")
        view = g._bytes(packet)
        for actual, expected, length in (
            (96, 64, 4),
            (100, 12, 4),
            (112, 80, 56),
            (64, 136, 8),
            (56, 144, 8),
            (80, 152, 8),
            (176, 160, 40),
            (224, 200, 4),
            (232, 208, 16),
        ):
            if (
                bytes(view[actual : actual + length])
                != _REQUESTS[self][expected : expected + length]
            ):
                raise ValueError("Overview Data differs from its private query snapshot")
        source_header = _INDEX[_parent(self)][2]
        for actual, expected, length in ((88, 232, 8), (76, 240, 4), (72, 244, 4)):
            if bytes(view[actual : actual + length]) != source_header[expected : expected + length]:
                raise ValueError("Overview Data differs from its private source snapshot")
        data = wire.OverviewData(packet)
        if data.identity["query_handle"] != source or data.identity["sequence"] != self.sequence:
            raise ValueError("overview Data identity mismatch")
        self._data = data
        _FRAME[self] = (
            weakref.ref(_parent(self)),
            weakref.ref(_transport(self)),
            self.handle,
            self.sequence,
            _REQUESTS[self],
            bytes(data.packet[:2304]),
        )
        members_wire.register(
            self,
            _transport(self),
            self._membership_reader,
            _BUDGETS[self],
            bytes(data.packet[:2304]),
            self.handle,
            self.sequence,
        )
        self._membership_reader = None

    def _issue(self, command, source):
        try:
            length = self._receipt(
                _transport(self).native_execute(
                    wire.request(command, source, self.sequence, budget=_BUDGETS[self])
                ),
                0 if command == 26 else 16,
                source,
            )
        except BaseException as error:
            self._phase = "uncertain"
            raise GeoOverviewUncertainAllocation(self) from error
        try:
            self._parsed(
                _transport(self).native_read(
                    wire.request(23, self.handle, self.sequence),
                    _BUDGETS[self]["processor_bytes"],
                ),
                length,
                source,
            )
        except BaseException as failure:
            self._data = None
            _FRAME.pop(self, None)
            traceback.clear_frames(failure.__traceback__)
            try:
                self.close()
            except BaseException as error:
                raise GeoOverviewCleanupPending(self) from error
            raise

    def _publish(self, source):
        self._issue(29, source)

    async def _issue_async(self, command, source):
        try:
            raw, interrupted = await g._settle(
                asyncio.create_task(
                    _transport(self).execute(
                        wire.request(command, source, self.sequence, budget=_BUDGETS[self])
                    )
                )
            )
            length = self._receipt(raw, 0 if command == 26 else 16, source)
        except BaseException as error:
            self._phase = "uncertain"
            raise GeoOverviewUncertainAllocation(self) from error
        try:
            if interrupted:
                raise asyncio.CancelledError
            packet, interrupted = await g._settle(
                asyncio.create_task(
                    _transport(self).read(wire.request(23, self.handle, self.sequence))
                )
            )
            if interrupted:
                raise asyncio.CancelledError
            self._parsed(packet, length, source)
        except BaseException as failure:
            packet = raw = None
            self._data = None
            _FRAME.pop(self, None)
            traceback.clear_frames(failure.__traceback__)
            try:
                await self.aclose()
            except BaseException as error:
                raise GeoOverviewCleanupPending(self) from error
            raise

    async def _publish_async(self, source):
        await self._issue_async(29, source)

    def retain(self):
        _ = self.data
        if _transport(self).bridge is not None:
            raise RuntimeError("use retain_async")
        if self._retention is not None and self._retention._phase == "closed":
            self._retention = None
        if self._retention is not None:
            raise GeoOverviewUncertainAllocation(self._retention)
        copy = self._retention = GeoOverviewFrame(_parent(self), self.sequence, _REQUESTS[self])
        copy._issue(26, self.handle)
        members_wire.copy_context(self, copy, copy.handle, copy.sequence)
        self._retention = None
        return copy

    async def retain_async(self):
        if _transport(self).bridge is None:
            return self.retain()
        _ = self.data
        if self._retention is not None and self._retention._phase == "closed":
            self._retention = None
        if self._retention is not None:
            raise GeoOverviewUncertainAllocation(self._retention)
        copy = self._retention = GeoOverviewFrame(_parent(self), self.sequence, _REQUESTS[self])
        await copy._issue_async(26, self.handle)
        members_wire.copy_context(self, copy, copy.handle, copy.sequence)
        self._retention = None
        return copy

    def close(self):
        if self._phase == "closed":
            return
        if self._phase == "uncertain":
            raise GeoOverviewUncertainAllocation(self)
        if _transport(self).bridge is not None:
            raise RuntimeError("use aclose")
        self._data = None
        _FRAME.pop(self, None)
        members_wire.drop_context(self)
        wire.validate_mutation(
            _transport(self).native_execute(wire.request(10, self.handle, 0)), self.handle, 0
        )
        self._phase = "closed"

    async def aclose(self):
        if _transport(self).bridge is None:
            return self.close()
        if self._phase == "closed":
            return
        if self._phase == "uncertain":
            raise GeoOverviewUncertainAllocation(self)
        self._data = None
        _FRAME.pop(self, None)
        members_wire.drop_context(self)
        await _close_known(
            self,
            _transport(self),
            wire.request(10, self.handle, 0),
            lambda: setattr(self, "_phase", "closed"),
        )

    def members(self, cell, *, sequence, max_vertices):
        _ = self.data
        return members_wire.members(self, cell, sequence=sequence, max_vertices=max_vertices)

    async def members_async(self, cell, *, sequence, max_vertices):
        _ = self.data
        return await members_wire.members_async(
            self, cell, sequence=sequence, max_vertices=max_vertices
        )

    def export(self, format="png", **options):
        from ._geo_snapshot import export_frame

        a = overview_frame_authority(self)
        if a is None:
            raise RuntimeError("Overview frame disposed or unpublished")
        proxy = SimpleNamespace(handle=a[2], data=True, _freeze_command=6, _bridge=a[1])
        return export_frame(proxy, a[3], format, **options)

    async def export_async(self, format="png", **options):
        from ._geo_snapshot import export_frame_async

        a = overview_frame_authority(self)
        if a is None:
            raise RuntimeError("Overview frame disposed or unpublished")
        proxy = SimpleNamespace(handle=a[2], data=True, _freeze_command=6, _bridge=a[1])
        return await export_frame_async(proxy, a[3], format, **options)
