"""Issued original-row domain membership, not final screen picking (§27/§29/§34)."""

from __future__ import annotations

import asyncio
import struct
import traceback
import weakref
from contextlib import suppress
from types import MappingProxyType

from . import _geoscale as g
from ._geo_allocation_recovery import (
    GeoAllocationAttempt,
    forget_geo_allocation_issuer,
    forget_geo_allocation_issuer_async,
)

_CONTEXTS = weakref.WeakKeyDictionary()
_CONTEXT_NATIVE_PRODUCERS = weakref.WeakKeyDictionary()
_CAPTURED_CONTEXTS = weakref.WeakKeyDictionary()
_PENDING = weakref.WeakKeyDictionary()
_OPS = weakref.WeakKeyDictionary()
_PAGES = weakref.WeakKeyDictionary()
_CAP = object()
MAX_PACKET = 256 + 4096 * 32


class _Context:
    def __init__(self, transport, reader, budget, header, handle, sequence):
        from ._geo_overview_source import _native_member_probe

        _CONTEXT_NATIVE_PRODUCERS[self] = _native_member_probe(transport)
        self.handle, self.sequence = handle, sequence
        self.transport, self.reader = transport, reader
        self.budget = MappingProxyType(dict(budget))
        self.header = bytes(header)


class _ContextCapture:
    def __init__(self, context, cap):
        if cap is not _CAP:
            raise TypeError("Private membership context capture required")
        self._context = context
        _CAPTURED_CONTEXTS[self] = weakref.ref(context)


def _context(owner):
    reference = _CONTEXTS.get(owner)
    return None if reference is None else reference()


def _attach_context(owner, context):
    owner._issued_membership_context = context
    _CONTEXTS[owner] = weakref.ref(context)


def register(frame, transport, reader, budget, header, handle, sequence):
    _attach_context(frame, _Context(transport, reader, budget, header, handle, sequence))


def capture_context(original):
    context = _context(original)
    if context is None:
        raise TypeError("Issued overview membership context required")
    return _ContextCapture(context, _CAP)


def install_context(token, copy, handle, sequence):
    reference = _CAPTURED_CONTEXTS.get(token)
    c = None if reference is None else reference()
    if c is None or not g._uint(handle) or not g._uint(sequence):
        raise TypeError("Issued retained membership capture required")
    _attach_context(copy, _Context(c.transport, c.reader, c.budget, c.header, handle, sequence))


def copy_context(original, copy, handle, sequence):
    install_context(capture_context(original), copy, handle, sequence)


def drop_context(frame):
    _CONTEXTS.pop(frame, None)
    frame._issued_membership_context = None


def request(command, handle, sequence, budget=None, payload=b""):
    if command not in (6, 7, 8, 9, 10, 23, 45, 46):
        raise ValueError("Unknown domain-member command")
    fields = dict(command=6, handle=handle, sequence=sequence, payload=payload)
    if budget is not None:
        fields["budget"] = budget
    b = bytearray(g.encode_request(fields))
    struct.pack_into("<I", b, 8, command)
    return bytes(b)


def _known_data_reply(raw, handle, sequence):
    r = reply(raw)
    if (
        r["code"] != 0
        or r["handle"] != handle
        or r["sequence"] != sequence
        or r["source"] != handle
        or not 256 <= r["length"] <= MAX_PACKET
    ):
        raise ValueError("Known MemberData probe kind/receipt mismatch")
    return False


def _known_data_absent(c, handle, sequence):
    # Only private known46 Data after unresolved attempted10, never45 birth.
    if not _CONTEXT_NATIVE_PRODUCERS.get(c, False):
        return False
    canonical = request(6, handle, sequence)
    with g._capture_native_member_data(canonical) as capture:
        try:
            raw = c.transport.native_execute(canonical)
            if capture.outcome(raw) is None:
                raise ValueError("MemberData probe lacks genuine current producer outcome")
            return _known_data_reply(raw, handle, sequence)
        except BaseException as error:
            proof = capture.outcome(error)
            if proof is not None and proof.get("status") == -10:
                return True
            raise


async def _aknown_data_absent(c, handle, sequence):
    if not _CONTEXT_NATIVE_PRODUCERS.get(c, False):
        return False
    canonical = request(6, handle, sequence)
    with g._capture_native_member_data(canonical) as capture:
        try:
            raw, interrupted = await g._settle(asyncio.create_task(c.transport.execute(canonical)))
            if capture.outcome(raw) is None:
                raise ValueError("MemberData probe lacks genuine current producer outcome")
            absent = _known_data_reply(raw, handle, sequence)
        except BaseException as error:
            proof = capture.outcome(error)
            if proof is not None and proof.get("status") == -10:
                return True
            raise
        if interrupted:
            raise asyncio.CancelledError
        return absent


def _zero(b, a, z):
    if any(b[a:z]):
        raise ValueError("Nonzero domain-member reserved bytes")


def reply(packet):
    if len(packet) != 256:
        raise ValueError("Fixed domain-member reply required")
    b = bytes(packet)
    magic, version, code = struct.unpack_from("<4sII", b)
    if magic != b"XYGZ" or version != 1 or code not in (0, 1, 2, 9, 21):
        raise ValueError("Invalid domain-member reply")
    _zero(b, 12, 16)
    ticket = None
    if code == 1 or (code == 2 and any(b[64:192])):
        _zero(b, 32, 64)
        _zero(b, 192, 256)
        ticket = b[64:192]
        if (
            struct.unpack_from("<I", ticket, 24)[0] != 1
            or not 64 <= struct.unpack_from("<Q", ticket, 56)[0] <= 16 << 20
            or not struct.unpack_from("<I", ticket, 44)[0]
        ):
            raise ValueError("Invalid membership cookie")
        _zero(ticket, 28, 32)
        _zero(ticket, 72, 128)
    elif code == 21:
        if struct.unpack_from("<Q", b, 32)[0] > 4096 or struct.unpack_from("<I", b, 56)[0] > 1:
            raise ValueError("Invalid membership completion")
        _zero(b, 60, 64)
        _zero(b, 88, 256)
    else:
        _zero(b, 48, 256)
        if code != 0:
            _zero(b, 32, 48)
    return dict(
        code=code,
        handle=struct.unpack_from("<Q", b, 16)[0],
        sequence=struct.unpack_from("<Q", b, 24)[0],
        length=struct.unpack_from("<Q", b, 32)[0],
        source=struct.unpack_from("<Q", b, 40)[0],
        ticket=ticket,
        raw=b,
    )


def mutation(packet, handle, sequence):
    r = reply(packet)
    if (r["code"], r["handle"], r["sequence"]) != (0, handle, sequence):
        raise ValueError("Membership mutation did not confirm settlement")
    _zero(r["raw"], 32, 256)
    return r


class GeoOverviewMembershipUncertain(RuntimeError):
    def __init__(self, owner):
        self.owner = owner
        super().__init__("Membership45 confirmation uncertain; recover the exact issued allocation")


class GeoOverviewMembershipCleanupPending(RuntimeError):
    def __init__(self, owner):
        self.owner = owner
        super().__init__("Membership cleanup pending; retry owner.close/aclose")


class GeoOverviewMembershipPublicationPending(RuntimeError):
    def __init__(self, owner):
        self.owner = owner
        super().__init__(
            "Membership publication deferred; known Query confirmed, retry prepare/prepare_async or close"
        )


def _new(
    owner, context, handle, sequence, cell, operation_sequence, max_vertices, prior=0, after=-1
):
    if type(cell) is not int or not 0 <= cell < 256:
        raise ValueError("Domain cell must be0..255")
    if not g._uint(operation_sequence) or not g._uint(max_vertices):
        raise ValueError("Nonzero u64 sequence/vertex ceiling required")
    previous = _PENDING.get(owner)
    if previous is not None and previous._phase != "closed":
        raise GeoOverviewMembershipUncertain(previous)
    op = GeoOverviewMembershipOperation(_CAP, context, cell, operation_sequence, prior, after)
    packet = request(
        45,
        handle,
        sequence,
        context.budget,
        struct.pack("<QIIQ", operation_sequence, cell, 0, max_vertices),
    )
    op._attempt = GeoAllocationAttempt(owner, context.transport, packet, operation_sequence)
    _PENDING[owner] = op
    return op, packet


def members(frame, cell, *, sequence, max_vertices):
    c = _context(frame)
    if c is None:
        raise ValueError("Privately issued overview frame required")
    return _run(frame, c, c.handle, c.sequence, cell, sequence, max_vertices)


async def members_async(frame, cell, *, sequence, max_vertices):
    c = _context(frame)
    if c is None:
        raise ValueError("Privately issued overview frame required")
    return await _arun(frame, c, c.handle, c.sequence, cell, sequence, max_vertices)


def _run(owner, c, handle, publication, cell, sequence, max_vertices, prior=0, after=-1):
    if c.transport.bridge is not None:
        raise RuntimeError("Use members_async/next_page_async with an async producer")
    op, packet = _new(owner, c, handle, publication, cell, sequence, max_vertices, prior, after)
    try:
        op.admit(packet)
        op.drive()
        page = op.prepare()
        _PENDING.pop(owner, None)
        return page
    except BaseException as failure:
        if (
            op._phase == "complete"
            and op._publish_attempted
            and not isinstance(failure, asyncio.CancelledError)
        ):
            raise GeoOverviewMembershipPublicationPending(op) from failure
        if op._phase != "uncertain":
            try:
                op.close()
                _PENDING.pop(owner, None)
            except BaseException as error:
                raise GeoOverviewMembershipCleanupPending(op) from error
        raise


async def _arun(owner, c, handle, publication, cell, sequence, max_vertices, prior=0, after=-1):
    if c.transport.bridge is None:
        return _run(owner, c, handle, publication, cell, sequence, max_vertices, prior, after)
    op, packet = _new(owner, c, handle, publication, cell, sequence, max_vertices, prior, after)
    op._processing = asyncio.current_task()
    try:
        await op.admit_async(packet)
        await op.drive_async()
        page = await op.prepare_async()
        _PENDING.pop(owner, None)
        return page
    except BaseException as failure:
        if (
            op._phase == "complete"
            and op._publish_attempted
            and not isinstance(failure, asyncio.CancelledError)
        ):
            raise GeoOverviewMembershipPublicationPending(op) from failure
        if op._phase != "uncertain":
            try:
                await op.aclose()
                _PENDING.pop(owner, None)
            except BaseException as error:
                raise GeoOverviewMembershipCleanupPending(op) from error
        raise
    finally:
        op._processing = None


class _RecoveryFlight:
    def __init__(self, task):
        self.task = task
        self.waiters = 0
        self.delivered = False


class GeoOverviewMembershipOperation:
    def __init__(self, cap, c, cell, sequence, prior, after):
        if cap is not _CAP:
            raise ValueError("Private membership operation required")
        _OPS[self] = (c, 0, sequence, cell, prior, after)
        self._phase = "admitting"
        self._publish_attempted = False
        self._loan = self._admission = self._processing = self._disposal = self._completion = None
        self._publication = self._page = self._data_reply = None
        self._closing = False
        self._attempt: GeoAllocationAttempt
        self._recovery = None
        self._disposed = self._dispose_attempted = False

    @property
    def handle(self):
        return _OPS[self][1]

    @property
    def sequence(self):
        return _OPS[self][2]

    def _request(self, command, payload=b""):
        return request(command, _OPS[self][1], _OPS[self][2], _OPS[self][0].budget, payload)

    def _exec(self, command, payload=b""):
        return _OPS[self][0].transport.native_execute(self._request(command, payload))

    async def _aexec(self, command, payload=b""):
        raw, interrupted = await g._settle(
            asyncio.create_task(_OPS[self][0].transport.execute(self._request(command, payload)))
        )
        return raw, interrupted

    def _admitted(self, packet):
        r = reply(packet)
        if (
            not r["handle"]
            or r["code"]
            or r["sequence"] != _OPS[self][2]
            or r["length"]
            or r["source"]
        ):
            raise ValueError("Invalid membership allocation receipt")
        a = _OPS[self]
        _OPS[self] = (a[0], r["handle"], *a[2:])
        self._phase = "query"

    def _validate_allocation(self, packet):
        r = reply(packet)
        if not r["handle"] or (r["code"], r["sequence"], r["length"], r["source"]) != (
            0,
            self.sequence,
            0,
            0,
        ):
            raise ValueError("Invalid membership allocation receipt")
        return r["handle"]

    def _accept_allocation(self, packet):
        if packet is None:
            self._phase = "closed"
            return
        self._admitted(packet)

    def admit(self, packet=None):
        try:
            self._accept_allocation(self._attempt.recover(self._validate_allocation))
        except BaseException as error:
            self._phase = "closed" if self._attempt.rejected else "uncertain"
            if self._attempt.rejected:
                raise
            raise GeoOverviewMembershipUncertain(self) from error

    async def admit_async(self, packet=None):
        if self._admission is None or self._admission.done():
            self._admission = asyncio.create_task(self._admit_async())
        _, interrupted = await g._settle(self._admission)
        if interrupted:
            raise asyncio.CancelledError

    async def _admit_async(self):
        try:
            raw = await self._attempt.recover_async(self._validate_allocation)
            self._accept_allocation(raw)
        except BaseException as error:
            self._phase = "closed" if self._attempt.rejected else "uncertain"
            if self._attempt.rejected:
                raise
            raise GeoOverviewMembershipUncertain(self) from error

    def recover(self):
        if _OPS[self][0].transport.bridge is not None:
            raise RuntimeError("Use recover_async with an async producer")
        if self._closing or self._phase == "closed":
            raise RuntimeError("Membership operation closed")
        if self._phase in ("admitting", "uncertain"):
            self.admit()
        if self._phase == "closed":
            raise RuntimeError("Membership allocation retired")
        if self._phase == "query":
            self.drive()
        return self.prepare()

    async def recover_async(self):
        if _OPS[self][0].transport.bridge is None:
            return self.recover()
        if self._recovery is None:
            # Delivery belongs to this flight: cancelling one waiter must not
            # dispose the Page handed to another waiter of the same task.
            self._recovery = _RecoveryFlight(asyncio.create_task(self._recover_async()))
        flight = self._recovery
        flight.waiters += 1
        page = None
        interrupted = False
        try:
            page, interrupted = await g._settle(flight.task)
            if interrupted:
                raise asyncio.CancelledError
            flight.delivered = True
            return page
        finally:
            flight.waiters -= 1
            if flight.waiters == 0:
                # Detach before awaited orphan cleanup: a late caller must not
                # join the completed flight while its Page is being disposed.
                if self._recovery is flight:
                    self._recovery = None
                try:
                    if page is not None and interrupted and not flight.delivered:
                        try:
                            await g._settle(asyncio.create_task(page.aclose()))
                        except BaseException as error:
                            self._page, self._phase = page, "data"
                            raise GeoOverviewMembershipCleanupPending(self) from error
                finally:
                    if self._recovery is flight:
                        self._recovery = None

    async def _recover_async(self):
        if self._closing or self._phase == "closed":
            raise RuntimeError("Membership operation closed")
        self._processing = asyncio.current_task()
        try:
            if self._phase in ("admitting", "uncertain"):
                await self.admit_async()
            if self._phase == "closed":
                raise RuntimeError("Membership allocation retired")
            if self._phase == "query":
                await self.drive_async()
            return await self.prepare_async()
        finally:
            self._processing = None

    def _cancelled(self, raw):
        r = reply(raw)
        if (
            r["handle"] != _OPS[self][1]
            or r["sequence"] != _OPS[self][2]
            or r["code"] not in (2, 9)
        ):
            raise ValueError("Membership cancel unconfirmed")
        if r["code"] == 2 and (self._loan is None or r["ticket"] != self._loan):
            raise ValueError("Membership cancel loan mismatch")
        return r

    def _settle(self):
        if self._loan is not None:
            try:
                mutation(self._exec(8, self._loan), self.handle, self.sequence)
            except BaseException:
                terminal = self._cancelled(self._exec(9))
                if terminal["code"] != 9:
                    raise
                _zero(terminal["raw"], 32, 256)
            self._loan = None

    async def _asettle(self):
        if self._loan is not None:
            try:
                raw, interrupted = await self._aexec(8, self._loan)
                mutation(raw, self.handle, self.sequence)
            except BaseException:
                raw, interrupted = await self._aexec(9)
                terminal = self._cancelled(raw)
                if terminal["code"] != 9:
                    raise
                _zero(terminal["raw"], 32, 256)
            self._loan = None
            if interrupted:
                raise asyncio.CancelledError

    def _ticket(self, r):
        if r["handle"] != _OPS[self][1] or r["sequence"] != _OPS[self][2]:
            raise ValueError("Membership operation mismatch")
        if r["code"] == 21:
            self._completion, self._phase = r["raw"], "complete"
            return None
        if r["code"] != 1 or r["ticket"] is None:
            raise ValueError("Membership query not complete")
        t = bytes(r["ticket"])
        context = _OPS[self][0]
        if (
            struct.unpack_from("<Q", t, 0)[0] == 0
            or struct.unpack_from("<Q", t, 16)[0] != _OPS[self][2]
            or struct.unpack_from("<Q", t, 32)[0] != struct.unpack_from("<Q", context.header, 56)[0]
            or struct.unpack_from("<Q", t, 48)[0] + struct.unpack_from("<I", t, 44)[0]
            > struct.unpack_from("<Q", context.header, 88)[0]
        ):
            raise ValueError("Membership cookie identity mismatch")
        self._loan = t
        return dict(
            raw=bytes(t),
            kind=1,
            owner=struct.unpack_from("<Q", t)[0],
            serial=struct.unpack_from("<Q", t, 8)[0],
            sequence=_OPS[self][2],
            generation=struct.unpack_from("<Q", t, 32)[0],
            chunk_index=struct.unpack_from("<I", t, 40)[0],
            rows=struct.unpack_from("<I", t, 44)[0],
            first_row=struct.unpack_from("<Q", t, 48)[0],
            encoded_bytes=struct.unpack_from("<Q", t, 56)[0],
            digest=t[64:72],
        )

    def _chunk(self, borrowed, length):
        if 4 * (256 + 128 + length) > _OPS[self][0].budget["processor_bytes"]:
            raise ValueError("Membership transfer exceeds budget")
        view = g._bytes(borrowed)
        if len(view) != length or g._backing_bytes(view) != length:
            raise ValueError("Exact owning membership chunk required")
        assert self._loan is not None
        return self._loan + bytes(view)

    def drive(self):
        self._settle()
        while self._phase == "query":
            ticket = self._ticket(reply(self._exec(6)))
            if ticket is None:
                return
            length = ticket["encoded_bytes"]
            borrowed = packet = None
            try:
                if 4 * (256 + 128 + length) > _OPS[self][0].budget["processor_bytes"]:
                    raise ValueError("Membership transfer exceeds budget")
                borrowed = _OPS[self][0].reader(dict(ticket))
                packet = self._chunk(borrowed, length)
                mutation(self._exec(7, packet), _OPS[self][1], _OPS[self][2])
            except BaseException as error:
                borrowed = packet = None
                traceback.clear_frames(error.__traceback__)
                self._cancelled(self._exec(9))
                raise
            finally:
                borrowed = packet = None
                self._settle()

    async def drive_async(self):
        await self._asettle()
        while self._phase == "query":
            raw, interrupted = await self._aexec(6)
            ticket = self._ticket(reply(raw))
            if interrupted:
                self._cancelled((await self._aexec(9))[0])
                raise asyncio.CancelledError
            if ticket is None:
                return
            length = ticket["encoded_bytes"]
            borrowed = packet = task = None
            try:
                if 4 * (256 + 128 + length) > _OPS[self][0].budget["processor_bytes"]:
                    raise ValueError("Membership transfer exceeds budget")
                task = asyncio.create_task(_OPS[self][0].reader(dict(ticket)))
                borrowed, interrupted = await g._settle(task)
                if interrupted:
                    raise asyncio.CancelledError
                packet = self._chunk(borrowed, length)
                raw, interrupted = await self._aexec(7, packet)
                mutation(raw, _OPS[self][1], _OPS[self][2])
                if interrupted:
                    raise asyncio.CancelledError
            except BaseException as error:
                borrowed = packet = task = None
                traceback.clear_frames(error.__traceback__)
                self._cancelled((await self._aexec(9))[0])
                raise
            finally:
                borrowed = packet = task = None
                await self._asettle()

    def _probe(self, raw):
        r = reply(raw)
        if (r["handle"], r["sequence"]) != (_OPS[self][1], _OPS[self][2]):
            raise ValueError("Membership publication probe mismatch")
        if r["code"] == 21:
            self._phase = "complete"
            return None
        self._data_receipt(r)
        return r

    def _data_receipt(self, r):
        if (r["code"], r["handle"], r["sequence"], r["source"]) != (
            0,
            _OPS[self][1],
            _OPS[self][2],
            _OPS[self][1],
        ) or not 256 <= r["length"] <= MAX_PACKET:
            raise ValueError("Invalid membership Data receipt")
        self._phase = "data"
        self._data_reply = r

    def prepare(self):
        if self._closing:
            raise RuntimeError("Membership operation closing")
        if self._phase == "data" and self._data_reply is not None:
            return self._read(self._data_reply)
        if self._phase == "publication":
            r = self._probe(self._exec(6))
            if r is not None:
                return self._read(r)
        if self._phase != "complete":
            raise RuntimeError("Membership query not complete")
        self._publish_attempted = True
        self._phase = "publication"
        try:
            r = reply(self._exec(46))
            self._data_receipt(r)
        except BaseException:
            r = self._probe(self._exec(6))
            if r is None:
                raise
        return self._read(r)

    def _read(self, r):
        self._attempt.release()
        packet = None
        try:
            if 4 * r["length"] > _OPS[self][0].budget["processor_bytes"]:
                raise ValueError("Membership output exceeds budget")
            packet = _OPS[self][0].transport.native_read(
                self._request(23), _OPS[self][0].budget["processor_bytes"]
            )
            if len(packet) != r["length"]:
                raise ValueError("Membership output length mismatch")
            page = GeoOverviewMembershipPage(
                _CAP,
                _OPS[self][0],
                _OPS[self][1],
                _OPS[self][2],
                _OPS[self][3],
                _OPS[self][4],
                packet,
                self._completion,
                _OPS[self][5],
            )
            self._phase = "closed"
            return page
        except BaseException as error:
            packet = None
            traceback.clear_frames(error.__traceback__)
            raise

    async def prepare_async(self):
        if self._closing:
            raise RuntimeError("Membership operation closing")
        if self._publication is None:
            self._publication = asyncio.create_task(self._prepare_async())
        task = self._publication
        try:
            page, interrupted = await g._settle(task)
        except BaseException:
            if task.done():
                self._publication = None
            raise
        if interrupted:
            try:
                await g._settle(asyncio.create_task(page.aclose()))
            except BaseException as error:
                self._page, self._phase = page, "data"
                raise GeoOverviewMembershipCleanupPending(self) from error
            raise asyncio.CancelledError
        return page

    async def _prepare_async(self):
        if self._phase == "data" and self._data_reply is not None:
            return await self._aread(self._data_reply)
        if self._phase == "publication":
            raw, interrupted = await self._aexec(6)
            r = self._probe(raw)
            if interrupted:
                raise asyncio.CancelledError
            if r is not None:
                return await self._aread(r)
        if self._phase != "complete":
            raise RuntimeError("Membership query not complete")
        self._publish_attempted = True
        self._phase = "publication"
        try:
            raw, interrupted = await self._aexec(46)
            r = reply(raw)
            self._data_receipt(r)
        except BaseException:
            raw, interrupted = await self._aexec(6)
            r = self._probe(raw)
            if r is None:
                raise
        if interrupted:
            raise asyncio.CancelledError
        return await self._aread(r)

    async def _aread(self, r):
        await self._attempt.release_async()
        packet = task = None
        try:
            if 4 * r["length"] > _OPS[self][0].budget["processor_bytes"]:
                raise ValueError("Membership output exceeds budget")
            task = asyncio.create_task(_OPS[self][0].transport.read(self._request(23)))
            packet, interrupted = await g._settle(task)
            if interrupted:
                raise asyncio.CancelledError
            if len(packet) != r["length"]:
                raise ValueError("Membership output length mismatch")
            page = GeoOverviewMembershipPage(
                _CAP,
                _OPS[self][0],
                _OPS[self][1],
                _OPS[self][2],
                _OPS[self][3],
                _OPS[self][4],
                packet,
                self._completion,
                _OPS[self][5],
            )
            self._page = page
            if self._closing:
                await page.aclose()
                self._phase = "closed"
                raise asyncio.CancelledError
            self._phase = "closed"
            return page
        except BaseException as error:
            packet = task = None
            traceback.clear_frames(error.__traceback__)
            raise

    def close(self):
        if self._phase == "closed":
            return
        self._closing = True
        if self._phase == "uncertain":
            self.admit()
            if self._phase == "closed":
                return
        self._settle()
        if self._phase == "publication":
            self._probe(self._exec(6))
        sequence = 0 if self._phase == "data" else _OPS[self][2]
        if not sequence and self._dispose_attempted and not self._disposed:
            self._disposed = _known_data_absent(_OPS[self][0], _OPS[self][1], _OPS[self][2])
        if (
            sequence
            and self._dispose_attempted
            and not self._disposed
            and self._attempt.probe_retirement(self._validate_allocation) is None
        ):
            self._disposed = True
        if not self._disposed:
            self._dispose_attempted = True
            mutation(
                _OPS[self][0].transport.native_execute(request(10, _OPS[self][1], sequence)),
                _OPS[self][1],
                sequence,
            )
            self._disposed = True
        self._attempt.release()
        self._phase = "closed"

    async def aclose(self):
        if _OPS[self][0].transport.bridge is None:
            return self.close()
        if self._phase == "closed":
            return
        self._closing = True
        if self._publication is not None:
            with suppress(BaseException):
                await g._settle(self._publication)
        if self._phase == "closed":
            return
        if self._admission is not None:
            with suppress(BaseException):
                await g._settle(self._admission)
        if self._phase == "closed":
            return
        if self._phase == "uncertain":
            await self.admit_async()
            if self._phase == "closed":
                return
        if self._processing is not None and self._processing is not asyncio.current_task():
            self._cancelled((await self._aexec(9))[0])
            with suppress(BaseException):
                await g._settle(self._processing)
            if self._phase == "closed":
                return
        await self._asettle()
        if self._phase == "publication":
            self._probe((await self._aexec(6))[0])
        if self._page is not None:
            await self._page.aclose()
            self._phase = "closed"
            return
        sequence = 0 if self._phase == "data" else _OPS[self][2]
        if self._disposal is None:
            self._disposal = asyncio.create_task(self._finish_close(sequence))
        task = self._disposal
        try:
            _, interrupted = await g._settle(task)
        except BaseException:
            if task.done():
                self._disposal = None
            raise
        if interrupted:
            raise asyncio.CancelledError

    async def _finish_close(self, sequence):
        if not sequence and self._dispose_attempted and not self._disposed:
            self._disposed = await _aknown_data_absent(_OPS[self][0], _OPS[self][1], _OPS[self][2])
        if (
            sequence
            and self._dispose_attempted
            and not self._disposed
            and await self._attempt.probe_retirement_async(self._validate_allocation) is None
        ):
            self._disposed = True
        if not self._disposed:
            self._dispose_attempted = True
            raw = await _OPS[self][0].transport.execute(request(10, _OPS[self][1], sequence))
            mutation(raw, _OPS[self][1], sequence)
            self._disposed = True
        await self._attempt.release_async()
        self._phase = "closed"


class GeoOverviewMembershipPage:
    temporal_exact = data_space = True
    final = False

    def __init__(self, cap, c, handle, sequence, cell, prior, packet, completion, after=-1):
        if cap is not _CAP:
            raise ValueError("Private membership Page required")
        count, has_next, cumulative, after = parse(
            packet, c.header, handle, sequence, cell, prior, completion, after
        )
        self._packet = bytes(packet)
        _PAGES[self] = (c, handle, sequence, cell, count, has_next, cumulative, after)
        self._disposal = None
        self._closed = False
        self._dispose_attempted = False

    @property
    def handle(self):
        return _PAGES[self][1]

    @property
    def sequence(self):
        return _PAGES[self][2]

    @property
    def raw(self):
        if self._packet is None:
            raise RuntimeError("Membership Page views disposed")
        return memoryview(self._packet)

    @property
    def count(self):
        _ = self.raw
        return _PAGES[self][4]

    @property
    def has_next(self):
        _ = self.raw
        return _PAGES[self][5]

    @property
    def cumulative_vertices(self):
        _ = self.raw
        return _PAGES[self][6]

    def record(self, i):
        if type(i) is not int or not 0 <= i < _PAGES[self][4]:
            raise IndexError("Membership record index")
        fid, source_row, chunk, row, matched = struct.unpack_from("<QQIIQ", self.raw, 256 + i * 32)
        return dict(
            feature_id=fid,
            source_row=source_row,
            chunk_index=chunk,
            row=row,
            matched_vertices=matched,
        )

    def next_page(self, *, sequence, max_vertices):
        _ = self.raw
        if not _PAGES[self][5] or sequence <= _PAGES[self][2]:
            raise ValueError("Nonterminal issued Page and newer sequence required")
        return _run(
            self,
            _PAGES[self][0],
            _PAGES[self][1],
            _PAGES[self][2],
            _PAGES[self][3],
            sequence,
            max_vertices,
            _PAGES[self][6],
            _PAGES[self][7],
        )

    async def next_page_async(self, *, sequence, max_vertices):
        _ = self.raw
        if not _PAGES[self][5] or sequence <= _PAGES[self][2]:
            raise ValueError("Nonterminal issued Page and newer sequence required")
        return await _arun(
            self,
            _PAGES[self][0],
            _PAGES[self][1],
            _PAGES[self][2],
            _PAGES[self][3],
            sequence,
            max_vertices,
            _PAGES[self][6],
            _PAGES[self][7],
        )

    def close(self):
        if _PAGES[self][0] is None:
            return
        self._packet = None
        if not self._closed and self._dispose_attempted:
            self._closed = _known_data_absent(_PAGES[self][0], _PAGES[self][1], _PAGES[self][2])
        if not self._closed:
            self._dispose_attempted = True
            mutation(
                _PAGES[self][0].transport.native_execute(request(10, _PAGES[self][1], 0)),
                _PAGES[self][1],
                0,
            )
            self._closed = True
        forget_geo_allocation_issuer(self)
        a = _PAGES[self]
        _PAGES[self] = (None, *a[1:])

    async def aclose(self):
        if _PAGES[self][0] is None:
            return
        if _PAGES[self][0].transport.bridge is None:
            return self.close()
        self._packet = None
        if self._disposal is None:
            self._disposal = asyncio.create_task(self._finish_close())
        task = self._disposal
        try:
            _, interrupted = await g._settle(task)
        except BaseException:
            if task.done():
                self._disposal = None
            raise
        if interrupted:
            raise asyncio.CancelledError

    async def _finish_close(self):
        if not self._closed and self._dispose_attempted:
            self._closed = await _aknown_data_absent(
                _PAGES[self][0], _PAGES[self][1], _PAGES[self][2]
            )
        if not self._closed:
            self._dispose_attempted = True
            raw = await _PAGES[self][0].transport.execute(request(10, _PAGES[self][1], 0))
            mutation(raw, _PAGES[self][1], 0)
            self._closed = True
        await forget_geo_allocation_issuer_async(self)
        a = _PAGES[self]
        _PAGES[self] = (None, *a[1:])


def parse(packet, header, handle, sequence, cell, prior, completion=None, after=-1):
    if not 256 <= len(packet) <= MAX_PACKET:
        raise ValueError("Bounded XYOM required")
    b = g._bytes(packet)
    magic, version, flags, resolution, owner, published, count, domain_cell, has_next = (
        struct.unpack_from("<4sIIIQQQII", b)
    )
    if (
        (magic, version, flags, resolution, owner, published, domain_cell)
        != (b"XYOM", 1, 3, 16, handle, sequence, cell)
        or count > 4096
        or len(b) != 256 + count * 32
        or has_next > 1
    ):
        raise ValueError("Invalid exact domain-member header")
    _zero(b, 220, 224)
    _zero(b, 248, 256)
    for actual, expected, length in (
        (64, 88, 8),
        (72, 56, 8),
        (80, 64, 8),
        (88, 48, 8),
        (96, 80, 8),
        (104, 72, 8),
        (112, 96, 8),
        (120, 112, 56),
        (176, 176, 40),
        (216, 224, 4),
        (224, 232, 16),
    ):
        if bytes(b[actual : actual + length]) != header[expected : expected + length]:
            raise ValueError("Membership differs from private overview snapshot")
    expected = struct.unpack_from("<Q", header, 256 + cell * 8)[0]
    claimed, cumulative = struct.unpack_from("<QQ", b, 48)
    if (
        claimed != expected
        or not prior <= cumulative <= expected
        or (not has_next and cumulative != expected)
    ):
        raise ValueError("Membership counts mismatch")
    total, last = 0, after
    for i in range(count):
        _, source_row, _, _, matched = struct.unpack_from("<QQIIQ", b, 256 + i * 32)
        if (
            source_row <= last
            or source_row >= struct.unpack_from("<Q", header, 88)[0]
            or not matched
            or (struct.unpack_from("<I", header, 76)[0] == 1 and matched != 1)
        ):
            raise ValueError("Invalid physical membership row")
        last, total = source_row, total + matched
    if total != struct.unpack_from("<Q", b, 240)[0] or total + prior != cumulative:
        raise ValueError("Matched vertex count mismatch")
    if completion is not None and (count, expected, cumulative, has_next) != (
        *struct.unpack_from("<QQQ", completion, 32),
        struct.unpack_from("<I", completion, 56)[0],
    ):
        raise ValueError("Membership completion mismatch")
    return count, bool(has_next), cumulative, last
