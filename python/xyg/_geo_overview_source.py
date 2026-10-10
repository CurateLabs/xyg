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
from types import MappingProxyType, MethodType, SimpleNamespace
from typing import Any

from . import _geo_overview as wire
from . import _geo_overview_members as members_wire
from . import _geoscale as g
from ._geo_allocation_recovery import (
    GeoAllocationAttempt,
    forget_geo_allocation_issuer,
    forget_geo_allocation_issuer_async,
)
from ._geo_retained import on_owned_geo_data_disposed, retained_frame_issued_authority

_CANONICAL_NATIVE_EXECUTE = g.execute
_CANONICAL_NATIVE_BRIDGE_EXECUTE = g.NativeGeoScaleBridge.execute
_NATIVE_MEMBER_PRODUCERS = weakref.WeakKeyDictionary()


def _native_member_probe(transport):
    return _NATIVE_MEMBER_PRODUCERS.get(transport, False)


_INDEX = weakref.WeakKeyDictionary()
_FRAME = weakref.WeakKeyDictionary()
_TRANSPORTS = weakref.WeakKeyDictionary()
_IDENTITIES = weakref.WeakKeyDictionary()
_REQUESTS = weakref.WeakKeyDictionary()
_PARENTS = weakref.WeakKeyDictionary()
_BUDGETS = weakref.WeakKeyDictionary()
_ATTEMPTS = weakref.WeakKeyDictionary()
_OWNER = object()
_SEED_HOOKS = weakref.WeakSet()
_ISSUED_KINDS = weakref.WeakKeyDictionary()
_ADMITTED_PACKETS = weakref.WeakKeyDictionary()
_HOST_INSPECTED = weakref.WeakSet()


def _capture_attempt(owner, issuer, request):
    owner._allocation_attempt = GeoAllocationAttempt(issuer, _transport(owner), request)
    _ATTEMPTS[owner] = weakref.ref(owner._allocation_attempt)


def _allocation(owner):
    value = _ATTEMPTS[owner]()
    if value is None:
        raise RuntimeError("Allocation attempt expired")
    return value


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
        _NATIVE_MEMBER_PRODUCERS[self] = (
            bridge is None and self.native_execute is _CANONICAL_NATIVE_EXECUTE
        ) or (
            bridge is not None
            and isinstance(bridge, g.NativeGeoScaleBridge)
            and isinstance(self.execute, MethodType)
            and self.execute.__self__ is bridge
            and self.execute.__func__ is _CANONICAL_NATIVE_BRIDGE_EXECUTE
            and g.execute is _CANONICAL_NATIVE_EXECUTE
        )


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
        _ISSUED_KINDS[owner] = "index"
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
        owner._recovery = None
        owner._closing = False
        owner._request = wire.request(
            27, handle, sequence, budget=owner._budget, payload=struct.pack("<Q", max_vertices)
        )
        _BUDGETS[owner] = MappingProxyType(dict(owner._budget))
        _IDENTITIES[owner] = (0, sequence)
        _REQUESTS[owner] = bytes(owner._request)
        _bind_transport(owner, _IssuedTransport(bridge))
        _INDEX[owner] = (weakref.ref(owner._issued_transport), sequence, bytes(header))
        _capture_attempt(owner, frame, _REQUESTS[owner])
        if frame not in _SEED_HOOKS:
            on_owned_geo_data_disposed(
                frame,
                lambda: forget_geo_allocation_issuer(frame),
                lambda: forget_geo_allocation_issuer_async(frame),
            )
            _SEED_HOOKS.add(frame)
        owner._disposed = owner._dispose_attempted = False
        return owner

    @classmethod
    def from_frame(cls, frame, source, **options):
        owner = cls._capture(frame, source, **options)
        if _transport(owner).bridge is not None:
            raise RuntimeError("use from_frame_async with an asynchronous producer")
        try:
            owner._recover_allocation()
        except BaseException as error:
            if _allocation(owner).rejected:
                owner._phase = "closed"
                raise
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
            await owner._recover_allocation_async()
        except BaseException as error:
            if _allocation(owner).rejected:
                owner._phase = "closed"
                raise
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

    def _validate_allocation(self, raw):
        receipt = wire.reply(raw)
        if receipt["code"] != 0 or not receipt["handle"] or receipt["sequence"] != self.sequence:
            raise ValueError("invalid overview allocation receipt")
        return receipt["handle"]

    def _recover_allocation(self):
        raw = _allocation(self).recover(self._validate_allocation)
        if raw is None:
            self._phase = "closed"
            return
        self._admitted(wire.reply(raw))
        if self._phase == "uncertain":
            self._phase = "building"

    async def _recover_allocation_async(self):
        raw = await _allocation(self).recover_async(self._validate_allocation)
        if raw is None:
            self._phase = "closed"
            return
        self._admitted(wire.reply(raw))
        if self._phase == "uncertain":
            self._phase = "building"

    def recover(self):
        if _transport(self).bridge is not None:
            raise RuntimeError("use recover_async")
        if self._phase in ("closed", "closing"):
            raise RuntimeError("Overview index closed")
        if self._phase == "uncertain":
            self._recover_allocation()
        if self._phase == "closed":
            raise RuntimeError("Overview allocation retired")
        if self._phase == "building":
            if _sync_drive(self)["code"] != 13:
                raise RuntimeError("Overview build did not complete")
            self._phase = "ready"
        return self

    async def recover_async(self):
        if _transport(self).bridge is None:
            return self.recover()
        if self._recovery is None:
            self._recovery = asyncio.create_task(self._recover_whole_async())
        task = self._recovery
        try:
            result, interrupted = await g._settle(task)
            if interrupted:
                raise asyncio.CancelledError
            return result
        finally:
            if task.done() and self._recovery is task:
                self._recovery = None

    async def _recover_whole_async(self):
        if _transport(self).bridge is None:
            return self.recover()
        if self._closing or self._phase in ("closed", "closing"):
            raise RuntimeError("Overview index closed")
        if self._phase == "uncertain":
            await self._recover_allocation_async()
        if self._phase == "closed":
            raise RuntimeError("Overview allocation retired")
        if self._phase == "building":
            result = await wire.drive(
                _transport(self),
                handle=self.handle,
                sequence=self.sequence,
                budget=_BUDGETS[self],
                read_chunk=self._storage[0],
                read_page=self._storage[1],
                write_page=self._storage[2],
            )
            if result["code"] != 13:
                raise RuntimeError("Overview build did not complete")
            if self._closing:
                raise RuntimeError("Overview index closing")
            self._phase = "ready"
        return self

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
        operation = GeoOverviewQuery(self, packet, sequence, _cap=_OWNER)
        self._active = operation
        return operation

    def update(self, query, *, sequence, _cap=None, on_issued=None):
        if _transport(self).bridge is not None:
            raise RuntimeError("use update_async for an asynchronous producer")
        operation = self._begin(query, sequence)
        frame = None
        try:
            if on_issued is not None:
                on_issued(operation)
            _CANONICAL_QUERY_ADMIT(operation)
            result = _sync_drive(operation)
            if result["code"] == 15:
                raise GeoOverviewUnsupportedDomain("No source scan was substituted")
            if result["code"] != 14:
                raise RuntimeError("overview query did not complete")
            operation._phase = "complete"
            frame = _CANONICAL_QUERY_PREPARE(operation)
            _CANONICAL_QUERY_CLOSE(operation)
            if _cap is not _OWNER:
                self._current = frame
            return frame
        except BaseException:
            if frame is not None:
                try:
                    _CANONICAL_FRAME_CLOSE(frame)
                except BaseException as error:
                    operation._cleanup_publication = frame
                    raise GeoOverviewCleanupPending(frame) from error
            if operation._phase != "uncertain":
                _CANONICAL_QUERY_CLOSE(operation)
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
                    operation._cleanup_publication = frame
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
            forget_geo_allocation_issuer(self)
            return
        if _transport(self).bridge is not None:
            raise RuntimeError("use aclose")
        if self._phase == "uncertain":
            self._recover_allocation()
            if self._phase == "closed":
                return
        self._phase = "closing"
        if self._active is not None:
            self._active.close()
        _settle_sync_loan(self)
        if (
            self._dispose_attempted
            and not self._disposed
            and _allocation(self).probe_retirement(self._validate_allocation) is None
        ):
            self._disposed = True
        if not self._disposed:
            self._dispose_attempted = True
            wire.validate_mutation(
                _transport(self).native_execute(wire.request(10, self.handle, self.sequence)),
                self.handle,
                self.sequence,
            )
            self._disposed = True
        _allocation(self).release()
        forget_geo_allocation_issuer(self)
        self._finished_close()

    async def aclose(self):
        if _transport(self).bridge is None:
            return self.close()
        if self._phase == "closed":
            await forget_geo_allocation_issuer_async(self)
            return
        self._closing = True
        if self._recovery is not None and self._recovery is not asyncio.current_task():
            with suppress(BaseException):
                await g._settle(self._recovery)
        if self._phase == "closed":
            return
        if self._phase == "uncertain":
            await self._recover_allocation_async()
            if self._phase == "closed":
                return
        self._phase = "closing"
        if self._active is not None:
            await self._active.aclose()
        if (
            self._dispose_attempted
            and not self._disposed
            and await _allocation(self).probe_retirement_async(self._validate_allocation) is None
        ):
            self._disposed = True
        if not self._disposed:
            self._dispose_attempted = True
            await _close_known(
                self,
                _transport(self),
                wire.request(10, self.handle, self.sequence),
                lambda: setattr(self, "_disposed", True),
            )
        await _allocation(self).release_async()
        await forget_geo_allocation_issuer_async(self)
        self._finished_close()


class GeoOverviewQuery:
    _storage: Any

    def __init__(self, index, request, sequence, *, _cap=None):
        if _cap is not _OWNER:
            raise TypeError("Private issued overview query required")
        _ISSUED_KINDS[self] = "query"
        self._index, self._request, self._sequence = index, request, sequence
        self._issued_parent = index
        _PARENTS[self] = weakref.ref(index)
        _BUDGETS[self] = _BUDGETS[index]
        _bind_transport(self, _transport(index))
        _IDENTITIES[self] = (0, sequence)
        _REQUESTS[self] = bytes(request)
        self._handle, self._phase = 0, "admitting"
        self._disposal = self._admission = self._processing = None
        self._cleanup_publication = None
        self._publication = None
        self._closing = False
        self._consumed = self._disposed = self._dispose_attempted = False
        _capture_attempt(self, index, _REQUESTS[self])
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

    def _validate_allocation(self, raw):
        receipt = wire.reply(raw)
        if receipt["code"] != 0 or not receipt["handle"] or receipt["sequence"] != self.sequence:
            raise ValueError("invalid overview query receipt")
        return receipt["handle"]

    def admit(self):
        try:
            raw = _allocation(self).recover(self._validate_allocation)
            if raw is None:
                self._finish_close()
            else:
                self._admitted(raw)
        except BaseException as error:
            if _allocation(self).rejected:
                self._finish_close()
                raise
            self._phase = "uncertain"
            raise GeoOverviewUncertainAllocation(self) from error

    async def admit_async(self):
        try:
            raw = await _allocation(self).recover_async(self._validate_allocation)
            if raw is None:
                self._finish_close()
            else:
                self._admitted(raw)
        except BaseException as error:
            if _allocation(self).rejected:
                self._finish_close()
                raise
            self._phase = "uncertain"
            raise GeoOverviewUncertainAllocation(self) from error

    def drive(self):
        if _transport(self).bridge is not None:
            raise RuntimeError("use drive_async")
        if self._closing or self._phase != "issued":
            raise RuntimeError("Overview query is not issued")
        result = _sync_drive(self)
        if result["code"] == 15:
            raise GeoOverviewUnsupportedDomain("No source scan substituted")
        if result["code"] != 14:
            raise RuntimeError("Overview query did not complete")
        self._phase = "complete"

    async def drive_async(self, *, cancel_event=None):
        if _transport(self).bridge is None:
            return self.drive()
        if self._closing or self._phase != "issued":
            raise RuntimeError("Overview query is not issued")
        self._processing = asyncio.current_task()
        try:
            result = await wire.drive(
                _transport(self),
                handle=self.handle,
                sequence=self.sequence,
                budget=_BUDGETS[self],
                read_chunk=self._storage[0],
                read_page=self._storage[1],
                write_page=self._storage[2],
                cancel_event=cancel_event,
            )
            if result["code"] == 15:
                raise GeoOverviewUnsupportedDomain("No source scan substituted")
            if result["code"] != 14:
                raise RuntimeError("Overview query did not complete")
            self._phase = "complete"
        finally:
            self._processing = None

    def recover(self):
        if self._closing or self._phase == "closed":
            raise RuntimeError("Overview query closed")
        if self._publication is not None:
            frame = self._publication.recover()
            self._consumed, self._phase = frame._consumed, "complete"
            return frame
        self.admit()
        if self._phase == "closed":
            raise RuntimeError("Overview allocation retired")
        return self

    async def recover_async(self):
        if _transport(self).bridge is None:
            return self.recover()
        if self._closing or self._phase == "closed":
            raise RuntimeError("Overview query closed")
        if self._publication is not None:
            frame = await self._publication.recover_async()
            if self._closing or self._phase == "closed":
                raise RuntimeError("Overview query closed")
            self._consumed, self._phase = frame._consumed, "complete"
            return frame
        await self.admit_async()
        if self._phase == "closed":
            raise RuntimeError("Overview allocation retired")
        return self

    def prepare(self):
        if self._closing or self._phase != "complete":
            raise RuntimeError("Overview query is not complete")
        if self._publication is not None:
            raise RuntimeError("Frame publication already attempted")
        frame = self._publication = GeoOverviewFrame(
            _parent(self), self.sequence, _REQUESTS[self], _cap=_OWNER
        )
        try:
            frame._publish(self.handle, self)
        except BaseException:
            if _allocation(frame).rejected:
                self._publication = None
                self._phase = "complete"
            elif frame._phase == "uncertain":
                self._phase = "uncertain"
            raise
        finally:
            self._consumed = frame._consumed
        return frame

    async def prepare_async(self):
        if self._closing or self._phase != "complete":
            raise RuntimeError("Overview query is not complete")
        if self._publication is not None:
            raise RuntimeError("Frame publication already attempted")
        frame = self._publication = GeoOverviewFrame(
            _parent(self), self.sequence, _REQUESTS[self], _cap=_OWNER
        )
        try:
            await frame._publish_async(self.handle, self)
        except BaseException:
            if _allocation(frame).rejected:
                self._publication = None
                self._phase = "complete"
            elif frame._phase == "uncertain":
                self._phase = "uncertain"
            raise
        finally:
            self._consumed = frame._consumed
        return frame

    def _finish_close(self):
        self._phase = "closed"
        self._storage = self._publication = None
        if _parent(self)._active is self:
            _parent(self)._active = None

    def close(self):
        if self._cleanup_publication is not None:
            self._cleanup_publication.close()
            self._cleanup_publication = None
        if self._phase == "closed":
            return
        self._closing = True
        if self._phase == "admitting":
            self.admit()
        if self._phase == "uncertain":
            if self._publication is not None:
                if self._publication not in _FRAME:
                    self._publication.close()
                self._consumed = self._publication._consumed
            else:
                self.admit()
                if self._phase == "closed":
                    return
        if self._publication is not None and self._publication not in _FRAME:
            self._publication.close()
            self._consumed = self._publication._consumed
        if (
            not self._consumed
            and self._dispose_attempted
            and not self._disposed
            and _allocation(self).probe_retirement(self._validate_allocation) is None
        ):
            self._disposed = True
        if not self._consumed and not self._disposed:
            self._dispose_attempted = True
            _settle_sync_loan(self)
            wire.validate_mutation(
                _transport(self).native_execute(wire.request(10, self.handle, self.sequence)),
                self.handle,
                self.sequence,
            )
            self._disposed = True
        _allocation(self).release()
        forget_geo_allocation_issuer(self)
        self._finish_close()

    async def aclose(self):
        if _transport(self).bridge is None:
            return self.close()
        if self._cleanup_publication is not None:
            await self._cleanup_publication.aclose()
            self._cleanup_publication = None
        if self._phase == "closed":
            return
        self._closing = True
        if self._phase == "admitting":
            await self.admit_async()
        if self._processing is not None and self._processing is not asyncio.current_task():
            if self.handle and not self._publication:
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
            if self._publication is not None:
                if self._publication not in _FRAME:
                    await self._publication.aclose()
                self._consumed = self._publication._consumed
            else:
                await self.admit_async()
                if self._phase == "closed":
                    return
        if self._publication is not None and self._publication not in _FRAME:
            await self._publication.aclose()
            self._consumed = self._publication._consumed
        if (
            not self._consumed
            and self._dispose_attempted
            and not self._disposed
            and await _allocation(self).probe_retirement_async(self._validate_allocation) is None
        ):
            self._disposed = True
        if not self._consumed and not self._disposed:
            self._dispose_attempted = True
            await _close_known(
                self,
                _transport(self),
                wire.request(10, self.handle, self.sequence),
                lambda: setattr(self, "_disposed", True),
            )
        await _allocation(self).release_async()
        await forget_geo_allocation_issuer_async(self)
        self._finish_close()


class GeoOverviewFrame:
    def __init__(self, index, sequence, request, *, _cap=None):
        if _cap is not _OWNER:
            raise TypeError("Private issued overview frame required")
        _ISSUED_KINDS[self] = "frame"
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
        self._recovery = None
        self._issuance = None
        self._closing = False
        self._freeze_command = 6
        self._membership_reader = index._storage[0] if index._storage is not None else None
        self._membership_capture = None
        self._consumed = self._disposed = self._dispose_attempted = False
        self._command, self._source = 0, 0

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
        _ADMITTED_PACKETS[self] = bytes(view)
        self._data = data
        _FRAME[self] = (
            weakref.ref(_parent(self)),
            weakref.ref(_transport(self)),
            self.handle,
            self.sequence,
            _REQUESTS[self],
            bytes(data.packet[:2304]),
        )
        if self._membership_capture is not None:
            members_wire.install_context(self._membership_capture, self, self.handle, self.sequence)
            self._membership_capture = None
        else:
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

    def _validate_allocation(self, raw):
        receipt = wire.reply(raw)
        if (
            receipt["code"] != (0 if self._command == 26 else 16)
            or not receipt["handle"]
            or receipt["sequence"] != self.sequence
            or receipt["source_handle"] != self._source
            or receipt["data_length"] > 32 * 1024 * 1024
            or 4 * receipt["data_length"] > _BUDGETS[self]["processor_bytes"]
        ):
            raise ValueError("Invalid overview Data allocation receipt")
        return receipt["handle"]

    def _accept_recovered(self, raw):
        if raw is None:
            self._phase = "closed"
            self._consumed = self._command == 29 and _allocation(self).retired
            return None
        self._consumed = self._command == 29
        return self._receipt(raw, 0 if self._command == 26 else 16, self._source)

    def _issue(self, command, source, issuer):
        if self._closing or self._phase == "closed":
            raise RuntimeError("Overview frame closing")
        self._command, self._source = command, source
        _capture_attempt(
            self, issuer, wire.request(command, source, self.sequence, budget=_BUDGETS[self])
        )
        try:
            length = self._accept_recovered(_allocation(self).recover(self._validate_allocation))
        except BaseException as error:
            if _allocation(self).rejected:
                self._phase = "closed"
                raise
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
            _ADMITTED_PACKETS.pop(self, None)
            _FRAME.pop(self, None)
            members_wire.drop_context(self)
            traceback.clear_frames(failure.__traceback__)
            try:
                self.close()
            except BaseException as error:
                raise GeoOverviewCleanupPending(self) from error
            raise

    def _publish(self, source, issuer):
        self._issue(29, source, issuer)

    async def _issue_async(self, command, source, issuer):
        self._issuance = asyncio.current_task()
        try:
            await self._issue_async_once(command, source, issuer)
        finally:
            self._issuance = None

    async def _issue_async_once(self, command, source, issuer):
        if self._closing or self._phase == "closed":
            raise RuntimeError("Overview frame closing")
        self._command, self._source = command, source
        _capture_attempt(
            self, issuer, wire.request(command, source, self.sequence, budget=_BUDGETS[self])
        )
        try:
            raw = await _allocation(self).recover_async(self._validate_allocation)
            interrupted = False
            length = self._accept_recovered(raw)
        except BaseException as error:
            if _allocation(self).rejected:
                self._phase = "closed"
                raise
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
            if self._closing:
                raise RuntimeError("Overview frame closing")
            self._parsed(packet, length, source)
        except BaseException as failure:
            packet = raw = None
            self._data = None
            _ADMITTED_PACKETS.pop(self, None)
            _FRAME.pop(self, None)
            members_wire.drop_context(self)
            traceback.clear_frames(failure.__traceback__)
            try:
                await self.aclose()
            except BaseException as error:
                raise GeoOverviewCleanupPending(self) from error
            raise

    async def _publish_async(self, source, issuer):
        await self._issue_async(29, source, issuer)

    def recover(self):
        if _transport(self).bridge is not None:
            raise RuntimeError("use recover_async")
        if self._closing or self._dispose_attempted or self._disposed or self._phase == "closed":
            raise RuntimeError("Overview frame closed")
        if self._data is not None:
            return self
        length = self._accept_recovered(_allocation(self).recover(self._validate_allocation))
        if self._phase == "closed":
            raise RuntimeError("Overview allocation retired")
        try:
            self._parsed(
                _transport(self).native_read(
                    wire.request(23, self.handle, self.sequence), _BUDGETS[self]["processor_bytes"]
                ),
                length,
                self._source,
            )
        except BaseException as failure:
            self._data = None
            _ADMITTED_PACKETS.pop(self, None)
            _FRAME.pop(self, None)
            members_wire.drop_context(self)
            traceback.clear_frames(failure.__traceback__)
            self.close()
            raise
        return self

    async def recover_async(self):
        if _transport(self).bridge is None:
            return self.recover()
        if self._issuance is not None and self._issuance is not asyncio.current_task():
            _, interrupted = await g._settle(self._issuance)
            if interrupted:
                raise asyncio.CancelledError
            if self._closing or self._phase == "closed":
                raise RuntimeError("Overview frame closing")
            return self
        if self._recovery is None:
            self._recovery = asyncio.create_task(self._recover_whole_async())
        task = self._recovery
        try:
            result, interrupted = await g._settle(task)
            if interrupted:
                raise asyncio.CancelledError
            return result
        finally:
            if task.done() and self._recovery is task:
                self._recovery = None

    async def _recover_whole_async(self):
        if _transport(self).bridge is None:
            return self.recover()
        if self._closing or self._dispose_attempted or self._disposed or self._phase == "closed":
            raise RuntimeError("Overview frame closed")
        if self._data is not None:
            return self
        length = self._accept_recovered(
            await _allocation(self).recover_async(self._validate_allocation)
        )
        if self._phase == "closed":
            raise RuntimeError("Overview allocation retired")
        packet = None
        try:
            packet, interrupted = await g._settle(
                asyncio.create_task(
                    _transport(self).read(wire.request(23, self.handle, self.sequence))
                )
            )
            if interrupted:
                raise asyncio.CancelledError
            self._parsed(packet, length, self._source)
            if self._closing:
                raise RuntimeError("Overview frame closing")
        except BaseException as failure:
            packet = None
            self._data = None
            _ADMITTED_PACKETS.pop(self, None)
            _FRAME.pop(self, None)
            members_wire.drop_context(self)
            traceback.clear_frames(failure.__traceback__)
            self._recovery = None
            await self.aclose()
            raise
        return self

    def retain(self, *, _cap=None, on_issued=None):
        if self._closing or self._phase == "closed":
            raise RuntimeError("Overview frame closing")
        _ = self.data
        if _transport(self).bridge is not None:
            raise RuntimeError("use retain_async")
        if self._retention is not None and (
            self._retention._phase == "closed" or self._retention in _FRAME
        ):
            self._retention = None
        if self._retention is not None:
            raise GeoOverviewUncertainAllocation(self._retention)
        copy = self._retention = GeoOverviewFrame(
            _parent(self), self.sequence, _REQUESTS[self], _cap=_OWNER
        )
        copy._membership_capture = members_wire.capture_context(self)
        if _cap is _OWNER and on_issued is not None:
            on_issued(copy)
        copy._issue(26, self.handle, self)
        self._retention = None
        return copy

    async def retain_async(self, *, _cap=None, on_issued=None):
        if _transport(self).bridge is None:
            return self.retain()
        if self._closing or self._phase == "closed":
            raise RuntimeError("Overview frame closing")
        _ = self.data
        if self._retention is not None and (
            self._retention._phase == "closed" or self._retention in _FRAME
        ):
            self._retention = None
        if self._retention is not None:
            raise GeoOverviewUncertainAllocation(self._retention)
        copy = self._retention = GeoOverviewFrame(
            _parent(self), self.sequence, _REQUESTS[self], _cap=_OWNER
        )
        copy._membership_capture = members_wire.capture_context(self)
        if _cap is _OWNER and on_issued is not None:
            on_issued(copy)
        await copy._issue_async(26, self.handle, self)
        self._retention = None
        return copy

    def close(self):
        if self._phase == "closed":
            forget_geo_allocation_issuer(self)
            return
        if _transport(self).bridge is not None:
            raise RuntimeError("use aclose")
        self._closing = True
        if self._phase == "new" and self._issuance is None:
            self._phase = "closed"
            return
        if self._phase == "uncertain":
            self._accept_recovered(_allocation(self).recover(self._validate_allocation))
            if self._phase == "closed":
                _allocation(self).release()
                return
        self._data = None
        _ADMITTED_PACKETS.pop(self, None)
        _FRAME.pop(self, None)
        members_wire.drop_context(self)
        if (
            self._dispose_attempted
            and not self._disposed
            and _allocation(self).probe_retirement(self._validate_allocation) is None
        ):
            self._disposed = True
        if not self._disposed:
            self._dispose_attempted = True
            wire.validate_mutation(
                _transport(self).native_execute(wire.request(10, self.handle, 0)), self.handle, 0
            )
            self._disposed = True
        _allocation(self).release()
        forget_geo_allocation_issuer(self)
        self._phase = "closed"

    async def aclose(self):
        if _transport(self).bridge is None:
            return self.close()
        if self._phase == "closed":
            await forget_geo_allocation_issuer_async(self)
            return
        self._closing = True
        if self._phase == "new" and self._issuance is None:
            self._phase = "closed"
            return
        if self._issuance is not None and self._issuance is not asyncio.current_task():
            with suppress(BaseException):
                await g._settle(self._issuance)
        if self._recovery is not None and self._recovery is not asyncio.current_task():
            with suppress(BaseException):
                await g._settle(self._recovery)
        if self._phase == "closed":
            return
        if self._phase == "uncertain":
            self._accept_recovered(await _allocation(self).recover_async(self._validate_allocation))
            if self._phase == "closed":
                await _allocation(self).release_async()
                return
        self._data = None
        _ADMITTED_PACKETS.pop(self, None)
        _FRAME.pop(self, None)
        members_wire.drop_context(self)
        if (
            self._dispose_attempted
            and not self._disposed
            and await _allocation(self).probe_retirement_async(self._validate_allocation) is None
        ):
            self._disposed = True
        if not self._disposed:
            self._dispose_attempted = True
            await _close_known(
                self,
                _transport(self),
                wire.request(10, self.handle, 0),
                lambda: setattr(self, "_disposed", True),
            )
        await _allocation(self).release_async()
        await forget_geo_allocation_issuer_async(self)
        self._phase = "closed"

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


_CANONICAL_INDEX_UPDATE = GeoOverviewIndex.update
_CANONICAL_QUERY_ADMIT = GeoOverviewQuery.admit


def is_native_overview_index(index):
    return index in _INDEX and _transport(index).bridge is None


def update_overview_index(index, query, *, sequence, on_issued=None):
    """Internal native host publication: no alias to caller-owned current."""
    if not is_native_overview_index(index):
        raise TypeError("Privately issued native overview index required")
    return _CANONICAL_INDEX_UPDATE(
        index, query, sequence=sequence, on_issued=on_issued, _cap=_OWNER
    )


def retain_overview_frame(frame, *, on_issued=None):
    if frame not in _FRAME:
        raise TypeError("Privately issued overview frame required")
    return _CANONICAL_FRAME_RETAIN(frame, _cap=_OWNER, on_issued=on_issued)


_CANONICAL_FRAME_RETAIN = GeoOverviewFrame.retain

_CANONICAL_QUERY_PREPARE = GeoOverviewQuery.prepare
_CANONICAL_QUERY_CLOSE = GeoOverviewQuery.close
_CANONICAL_FRAME_CLOSE = GeoOverviewFrame.close


def close_overview_owner(owner):
    kind = _issued_kind(owner)
    if kind == "index":
        return _CANONICAL_INDEX_CLOSE(owner)
    if kind == "query":
        return _CANONICAL_QUERY_CLOSE(owner)
    if kind == "frame":
        return _CANONICAL_FRAME_CLOSE(owner)
    raise TypeError("Privately issued overview owner required")


async def aclose_overview_owner(owner):
    kind = _issued_kind(owner)
    if kind == "index":
        return await _CANONICAL_INDEX_ACLOSE(owner)
    if kind == "query":
        return await _CANONICAL_QUERY_ACLOSE(owner)
    if kind == "frame":
        return await _CANONICAL_FRAME_ACLOSE(owner)
    raise TypeError("Privately issued overview owner required")


def overview_frame_data(frame):
    if _issued_kind(frame) != "frame":
        raise TypeError("Privately issued overview frame required")
    packet = _ADMITTED_PACKETS.get(frame)
    if packet is None or frame._closing or frame in _HOST_INSPECTED:
        raise RuntimeError("Private overview inspection unavailable")
    _HOST_INSPECTED.add(frame)
    return wire.OverviewData(bytes(memoryview(packet)))


_CANONICAL_INDEX_CLOSE = GeoOverviewIndex.close
_CANONICAL_INDEX_ACLOSE = GeoOverviewIndex.aclose
_CANONICAL_QUERY_ACLOSE = GeoOverviewQuery.aclose
_CANONICAL_FRAME_ACLOSE = GeoOverviewFrame.aclose


async def retain_overview_frame_async(frame, *, on_issued=None):
    if frame not in _FRAME:
        raise TypeError("Privately issued overview frame required")
    return await _CANONICAL_FRAME_RETAIN_ASYNC(frame, _cap=_OWNER, on_issued=on_issued)


_CANONICAL_FRAME_RETAIN_ASYNC = GeoOverviewFrame.retain_async


def _issued_kind(owner):
    try:
        return _ISSUED_KINDS.get(owner)
    except TypeError:
        return None
