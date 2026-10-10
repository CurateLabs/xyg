"""Private exact allocation attempts. Geometry/count policy stays in Rust (§27/29)."""

from __future__ import annotations

import asyncio
import struct
import weakref

from . import _geoscale as g

_ISSUERS = weakref.WeakKeyDictionary()
_ORIGINAL_ISSUERS = weakref.WeakKeyDictionary()
_NATIVE_EXECUTE = g.execute


class _OriginalIssuer:
    def __init__(self, handle, bridge):
        self.handle, self.bridge = handle, bridge
        self.execute = bridge.execute if bridge is not None else _NATIVE_EXECUTE
        self.read = bridge.read if bridge is not None else None


def register_geo_allocation_issuer(owner, handle, bridge):
    original = _OriginalIssuer(g._uint(handle), bridge)
    owner._geo_allocation_original = original
    _ORIGINAL_ISSUERS[owner] = weakref.ref(original)


def original_geo_allocation_issuer(owner):
    reference = _ORIGINAL_ISSUERS.get(owner)
    original = reference() if reference is not None else None
    if original is None:
        raise TypeError("Original retained Source/Index issuer required")
    return original


class _IssuerReceipts:
    def __init__(self):
        self.commands = {}


def _issuer_receipts(owner, create=False):
    issued = _ISSUERS.get(owner)
    if issued is not None:
        token = issued()
        if token is None:
            raise RuntimeError("Original allocation issuer receipts expired")
        return token.commands
    if not create:
        return {}
    token = _IssuerReceipts()
    owner._geo_allocation_receipts = token
    _ISSUERS[owner] = weakref.ref(token)
    return token.commands


def _terminal(packet, sequence, target=None):
    view = g._bytes(packet)
    if len(view) != 256:
        raise ValueError("Fixed allocation acknowledgement required")
    raw = bytes(view)
    magic, version, code, reserved, handle, returned = struct.unpack_from("<IIIIQQ", raw)
    if (
        magic != 0x5A475958
        or version != 1
        or code not in (0, 22)
        or reserved
        or returned != sequence
        or any(raw[32:])
        or (code == 22 and handle != 0)
        or (code == 0 and target is not None and handle != target)
    ):
        raise ValueError("Allocation acknowledgement binding mismatch")
    return code


def _rejection(error):
    from ._native import GeoNativeError

    return isinstance(error, GeoNativeError) and getattr(error, "status", None) in (-9, -10, -13)


class GeoAllocationAttempt:
    """Captured before dispatch; exact confirmation settles before phase advance."""

    def __init__(self, owner, transport, request, operation_sequence=None, *, authenticated=False):
        if not 256 <= len(request) <= 304:
            raise ValueError("Bounded allocation request required")
        raw = bytes(request)
        command = struct.unpack_from("<I", raw, 8)[0]
        if (
            command not in (19, 26, 27, 28, 29, 35, 36, 43, 45)
            or struct.unpack_from("<Q", raw, 240)[0]
        ):
            raise ValueError("Canonical allocation request required")
        if command in (35, 36, 43) and (len(raw) != 264 or not authenticated):
            raise ValueError("selected mutations require authenticated exact framing")
        if command == 19 and (len(raw) != 304 or not authenticated):
            raise ValueError("selected publication requires authenticated exact framing")
        commands = _issuer_receipts(owner, True)
        slot = commands.setdefault(command, {"nonce": 0, "dead": False, "attempt": None})
        prior = slot["attempt"]
        tracked = slot.setdefault("selected_attempts", [])
        tracked[:] = [
            a for a in tracked if not a._released and not a._rejected and a._fallback is None
        ]
        if authenticated and len(tracked) >= 16:
            raise RuntimeError("Selected allocation birth tracking capacity exhausted")
        if slot["dead"] or (prior is not None and not prior.settled):
            raise RuntimeError("Allocation issuer closed or prior confirmation pending")
        nonce = slot["nonce"] + 1
        g._uint(nonce)
        request = bytearray(raw)
        struct.pack_into("<Q", request, 240, nonce)
        self._request = bytes(request)
        self._command, self._nonce = command, nonce
        self._issuer = struct.unpack_from("<Q", raw, 16)[0]
        self._sequence = (
            struct.unpack_from("<Q", raw, 24)[0]
            if operation_sequence is None
            else g._uint(operation_sequence)
        )
        self._execute = transport.execute
        self._native_execute = transport.native_execute
        self._slot = slot
        self._target = 0
        self._receipt = None
        self._confirmed = self._retired = self._rejected = self._uncertain = False
        self._released = False
        self._active = None
        self._authenticated, self._fallback = authenticated, None
        slot["nonce"], slot["attempt"] = nonce, self
        if authenticated:
            tracked.append(self)

    @property
    def settled(self):
        return (
            self._rejected
            or self._fallback is not None
            or (self._confirmed and (not self._retired or self._released))
        )

    @property
    def retired(self):
        return self._retired

    @property
    def rejected(self):
        return self._rejected

    def _ack(self, action):
        request = bytearray(
            g.encode_request(
                dict(
                    command=6,
                    handle=self._issuer,
                    sequence=self._sequence,
                    payload=struct.pack("<IIQ", self._command, action, self._target),
                )
            )
        )
        struct.pack_into("<I", request, 8, 47)
        struct.pack_into("<Q", request, 240, self._nonce)
        return bytes(request)

    def _accept(self, packet, validate):
        view = g._bytes(packet)
        if len(view) != 256:
            raise ValueError("Fixed allocation receipt required")
        raw = bytes(view)
        if self._command == 36 and struct.unpack_from("<I", raw, 8)[0] == 10:
            if validate(raw) != 0:
                raise ValueError("nonjournaled fallback requires no target")
            self._fallback = raw
        elif len(raw) == 256 and struct.unpack_from("<I", raw, 8)[0] == 22:
            _terminal(raw, self._sequence)
            self._retired = True
        else:
            target = validate(raw)
            if not target or (self._target and target != self._target):
                raise ValueError("Allocation target changed")
            self._target, self._receipt = target, raw
        return raw

    def _confirmed_reply(self, raw):
        if _terminal(raw, self._sequence, self._target) == 22:
            self._retired = True
        self._confirmed = True
        self._slot["journal_nonce"], self._slot["journal_attempt"] = self._nonce, self
        return None if self._retired else self._receipt

    def _failed(self, error, outcome=None):
        rejected = (
            outcome is not None and outcome.get("status") in (-9, -10, -13)
            if self._authenticated
            else _rejection(error)
        )
        if not self._uncertain and not self._target and not self._retired and rejected:
            self._rejected = True
        else:
            self._uncertain = True

    def _call(self, request):
        if not self._authenticated:
            return self._native_execute(request)
        with g._capture_native_mutation(request) as capture:
            try:
                raw = self._native_execute(request)
            except BaseException as error:
                self._failed(error, capture.outcome(error))
                raise
            if capture.outcome(raw) is None:
                self._uncertain = True
                raise ValueError("selected mutation lacks genuine native outcome")
            return raw

    async def _acall(self, request):
        if not self._authenticated:
            return await self._execute(request)
        with g._capture_native_mutation(request) as capture:
            try:
                raw = await self._execute(request)
            except BaseException as error:
                self._failed(error, capture.outcome(error))
                raise
            if capture.outcome(raw) is None:
                self._uncertain = True
                raise ValueError("selected mutation lacks genuine native outcome")
            return raw

    def recover(self, validate):
        if self._fallback is not None:
            return self._fallback
        if self._rejected:
            return None
        if self._retired and self._confirmed:
            self.release()
            return None
        try:
            self._accept(self._receipt or self._call(self._request), validate)
            if self._fallback is not None:
                return self._fallback
            result = self._confirmed_reply(self._call(self._ack(0)))
            if self._retired:
                self.release()
            return result
        except BaseException as error:
            if not self._rejected:
                self._failed(error)
            raise

    async def recover_async(self, validate):
        if self._fallback is not None:
            return self._fallback
        if self._rejected:
            return None
        if self._retired and self._confirmed:
            await self.release_async()
            return None
        if self._active is None:

            async def run():
                try:
                    packet = self._receipt
                    if packet is None:
                        packet = await self._acall(self._request)
                    self._accept(packet, validate)
                    if self._fallback is not None:
                        return self._fallback
                    result = self._confirmed_reply(await self._acall(self._ack(0)))
                    if self._retired:
                        await self.release_async()
                    return result
                except BaseException as error:
                    if not self._rejected:
                        self._failed(error)
                    raise

            self._active = asyncio.create_task(run())
        task = self._active
        try:
            raw, interrupted = await g._settle(task)
            if interrupted:
                raise asyncio.CancelledError
            return raw
        finally:
            if task.done():
                self._active = None

    def probe_retirement(self, validate):
        if self._confirmed and self._target:
            if _terminal(self._call(self._ack(0)), self._sequence, self._target) == 22:
                self._retired = True
                return None
            return self._receipt
        self._receipt = None
        return self.recover(validate)

    async def probe_retirement_async(self, validate):
        if self._confirmed and self._target:
            raw, interrupted = await g._settle(asyncio.create_task(self._acall(self._ack(0))))
            if _terminal(raw, self._sequence, self._target) == 22:
                self._retired = True
                return None
            if interrupted:
                raise asyncio.CancelledError
            return self._receipt
        self._receipt = None
        return await self.recover_async(validate)

    def _forget_request(self):
        if (
            not self._released
            or self._rejected
            or self._slot.get("journal_nonce", self._slot["nonce"]) != self._nonce
        ):
            return None
        if not self._confirmed:
            raise RuntimeError("Unconfirmed allocation cannot be forgotten")
        return self._ack(1)

    def forget(self):
        request = self._forget_request()
        if request is not None:
            if _terminal(self._call(request), self._sequence, 0) != 0:
                raise ValueError("Forget acknowledgement must be successful")
            self._slot["attempt"] = None

    async def forget_async(self):
        request = self._forget_request()
        if request is not None:
            raw, interrupted = await g._settle(asyncio.create_task(self._acall(request)))
            if _terminal(raw, self._sequence, 0) != 0:
                raise ValueError("Forget acknowledgement must be successful")
            self._slot["attempt"] = None
            if interrupted:
                raise asyncio.CancelledError

    def release(self):
        if not self._released and not self._rejected:
            if not self._confirmed:
                raise RuntimeError("Allocation confirmation unsettled")
            if _terminal(self._call(self._ack(2)), self._sequence, 0) != 0:
                raise ValueError("Release acknowledgement must be successful")
            self._released = True
        if self._slot["dead"]:
            self.forget()

    async def release_async(self):
        if not self._released and not self._rejected:
            if not self._confirmed:
                raise RuntimeError("Allocation confirmation unsettled")
            raw, interrupted = await g._settle(asyncio.create_task(self._acall(self._ack(2))))
            if _terminal(raw, self._sequence, 0) != 0:
                raise ValueError("Release acknowledgement must be successful")
            self._released = True
            if interrupted:
                raise asyncio.CancelledError
        if self._slot["dead"]:
            await self.forget_async()


def forget_geo_allocation_issuer(owner):
    for slot in _issuer_receipts(owner).values():
        slot["dead"] = True
        for attempt in slot.get("selected_attempts", []):
            if attempt._fallback is not None or attempt._rejected or attempt._released:
                continue
            if (
                attempt.probe_retirement(lambda raw: struct.unpack_from("<Q", raw, 16)[0])
                is not None
            ):
                continue  # Index disposal does not retire independently owned Query births.
            attempt.release()
        attempt = slot.get("journal_attempt", slot["attempt"])
        if attempt is not None:
            attempt.forget()


async def forget_geo_allocation_issuer_async(owner):
    for slot in _issuer_receipts(owner).values():
        slot["dead"] = True
        for attempt in slot.get("selected_attempts", []):
            if attempt._fallback is not None or attempt._rejected or attempt._released:
                continue
            if (
                await attempt.probe_retirement_async(
                    lambda raw: struct.unpack_from("<Q", raw, 16)[0]
                )
                is not None
            ):
                continue  # Index disposal does not retire independently owned Query births.
            await attempt.release_async()
        attempt = slot.get("journal_attempt", slot["attempt"])
        if attempt is not None:
            await attempt.forget_async()
