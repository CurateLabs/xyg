"""Explicit typed linked-state ownership. Rust owns every selection decision."""

from __future__ import annotations

import asyncio
import struct
import traceback
import weakref
from contextlib import suppress
from types import SimpleNamespace
from typing import Any

import numpy as np

from . import _geoscale as g
from ._geo_allocation_recovery import GeoAllocationAttempt, original_geo_allocation_issuer
from ._geo_retained import OwnedGeoData, _attach_frame, _owned_data_identity

_NATIVE_EXECUTE = g.execute
_NATIVE_READ = g.read

_AUTHORITY = object()
_BRIDGE_UNSET = object()
_STATE_AUTHORITIES: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_SCOPE_NONCES: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_SCOPE_ISSUERS: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _execute(command, **fields):
    return g.decode_reply(g.execute(g.encode_request(dict(command=command, **fields))))


async def _issue(bridge, request):
    raw, interrupted = await g._settle(asyncio.create_task(bridge.execute(request)))
    reply = g.decode_reply(raw)
    if interrupted:
        await g._settle(
            asyncio.create_task(
                bridge.execute(g.encode_request(dict(command=10, handle=reply["handle"])))
            )
        )
        raise asyncio.CancelledError
    return reply


def _state_payload(revision, ids, fill, budget):
    if (
        not isinstance(ids, np.ndarray)
        or ids.dtype != np.dtype("<u8")
        or ids.ndim != 1
        or not ids.flags.c_contiguous
        or len(ids) > 10000
    ):
        raise TypeError("exact bounded u64 ID plane required")
    rgba = g._bytes(fill)
    if len(rgba) != 4:
        raise TypeError("selected fill requires exact RGBA bytes")
    if 256 + 24 + len(ids) * 8 > g._budget(budget["processor_bytes"]):
        raise ValueError("selected framing exceeds budget")
    payload = bytearray(24 + len(ids) * 8)
    struct.pack_into("<Q", payload, 0, g._uint(revision))
    payload[8:12] = rgba
    struct.pack_into("<Q", payload, 16, len(ids))
    payload[24:] = memoryview(ids).cast("B")
    return payload


class _Owner:
    def __init__(self, handle, bridge=None, *, _token=None):
        if _token is not _AUTHORITY:
            raise TypeError("issued selected authority required")
        self._handle, self._live = handle, True
        self._bridge, self._disposal = bridge, None

    @property
    def handle(self):
        return self._handle

    def _check(self):
        if not self._live or self._disposal is not None:
            raise RuntimeError("selected owner unavailable")

    def close(self):
        if self._bridge is not None:
            raise RuntimeError("use aclose for asynchronous owner")
        if self._live:
            _execute(10, handle=self.handle)
            self._live = False

    async def aclose(self):
        if self._bridge is None:
            return self.close()
        if not self._live:
            return
        if self._disposal is None:
            self._disposal = asyncio.create_task(
                self._bridge.execute(g.encode_request(dict(command=10, handle=self.handle)))
            )
        try:
            _, interrupted = await g._settle(self._disposal)
        except BaseException:
            if self._disposal.done():
                self._disposal = None
            raise
        self._live = False
        if interrupted:
            raise asyncio.CancelledError


class GeoSelectedStateAttempt:
    """Known request retained through unknown allocation or cleanup outcomes."""

    def __init__(self, scope, request, revision, *, _token=None):
        if _token is not _AUTHORITY:
            raise TypeError("issued attempt required")
        self._scope, self._request, self._revision = scope, bytes(request), revision
        self._bridge = scope._bridge
        self._state = self._active = self._disposal = None
        self._closed = self._uncertain = False

    def _accept(self, raw):
        b = g._bytes(raw)
        if len(b) != 256 or b[:8] != b"XYGZ\x01\0\0\0" or any(b[12:16]) or any(b[32:]):
            raise ValueError("state ownership reply")
        code, handle, revision = struct.unpack_from("<I4xQQ", b, 8)
        if code not in (0, 20) or revision != self._revision:
            raise ValueError("state ownership reply")
        if code == 20:
            if handle:
                raise ValueError("retired state handle")
            authority = _STATE_AUTHORITIES.get(self._state) if self._state else None
            if authority and authority["busy"]:
                raise RuntimeError("selected State operation unsettled")
            if self._state is not None:
                self._state._consume()
            self._closed, self._request = True, b""
            return None
        if not handle or (self._state is not None and self._state.handle != handle):
            raise ValueError("state ownership handle")
        if self._state is None:
            self._state = GeoSelectedState(
                handle, self._scope, _token=_AUTHORITY, _captured_bridge=self._bridge
            )
        return self._state

    def _failure(self, error):
        from ._native import GeoNativeError

        if (
            not self._uncertain
            and self._state is None
            and isinstance(error, GeoNativeError)
            and error.status in (-9, -10, -13)
        ):
            self._closed, self._request = True, b""
        else:
            self._uncertain = True

    def _issue(self):
        if self._state is not None and not self._state._live:
            self._closed, self._request = True, b""
            return None
        try:
            return self._accept(g.execute(self._request))
        except BaseException as error:
            self._failure(error)
            raise

    def recover(self):
        if self._bridge is not None:
            raise RuntimeError("use recover_async for asynchronous attempt")
        if self._closed or self._disposal is not None:
            raise RuntimeError("state attempt unavailable")
        state = self._issue()
        if state is None:
            raise RuntimeError("state nonce retired")
        return state

    async def _recover_async(self):
        if self._state is not None and not self._state._live:
            self._closed, self._request = True, b""
            return None
        if self._active is None:
            self._active = asyncio.create_task(self._bridge.execute(self._request))
        task = self._active
        try:
            raw, interrupted = await g._settle(task)
            state = self._accept(raw)
            if interrupted:
                raise asyncio.CancelledError
            return state
        except BaseException as error:
            self._failure(error)
            raise
        finally:
            if task.done() and self._active is task:
                self._active = None

    async def recover_async(self):
        if self._bridge is None:
            return self.recover()
        if self._closed or self._disposal is not None:
            raise RuntimeError("state attempt unavailable")
        state = await self._recover_async()
        if state is None:
            raise RuntimeError("state nonce retired")
        return state

    def close(self):
        if self._bridge is not None:
            raise RuntimeError("use aclose for asynchronous attempt")
        if not self._closed:
            state = self._issue()
            if state is not None:
                state.close()
            self._closed, self._request = True, b""

    async def aclose(self):
        if self._bridge is None:
            return self.close()
        if self._closed:
            return

        async def cleanup():
            state = await self._recover_async()
            if state is not None:
                await state.aclose()
            self._closed, self._request = True, b""

        if self._disposal is None:
            self._disposal = asyncio.create_task(cleanup())
        task = self._disposal
        try:
            _, interrupted = await g._settle(task)
        finally:
            if task.done() and self._disposal is task:
                self._disposal = None
        if interrupted:
            raise asyncio.CancelledError


class GeoSelectedScope(_Owner):
    """Create from an immutable painted frame; close remains retryable if held."""

    def __init__(self, handle, bridge=None, *, _token=None):
        super().__init__(handle, bridge, _token=_token)
        try:
            reference = weakref.ref(bridge) if bridge is not None else None
        except TypeError:
            reference = False
        _SCOPE_ISSUERS[self] = (handle, reference)

    budget: dict

    @classmethod
    async def from_frame_async(cls, frame, *, namespace, layer_id):
        source = frame._source
        if source._bridge is None:
            return cls.from_frame(frame, namespace=namespace, layer_id=layer_id)
        request = g.encode_request(
            dict(
                command=32,
                handle=frame.handle,
                sequence=frame.data.identity["sequence"],
                budget=source.budget,
                payload=struct.pack("<QQ", g._uint(namespace), g._uint(layer_id)),
            )
        )
        result = await _issue(source._bridge, request)
        owner = cls(result["handle"], source._bridge, _token=_AUTHORITY)
        owner.budget = dict(source.budget)
        return owner

    @classmethod
    def from_frame(cls, frame, *, namespace, layer_id):
        _ = frame.data  # Reject disposed frame before transport.
        source = frame._source
        if source._bridge is not None:
            raise RuntimeError("synchronous selected scope requires native frame")
        payload = struct.pack("<QQ", g._uint(namespace), g._uint(layer_id))
        result = _execute(
            32,
            handle=frame.handle,
            sequence=frame.data.identity["sequence"],
            budget=source.budget,
            payload=payload,
        )
        owner = cls(result["handle"], _token=_AUTHORITY)
        owner.budget = dict(source.budget)
        return owner

    def begin_state(self, *, revision, ids, fill, budget=None, nonce=None):
        """Capture a private replayable allocation attempt before any transport call."""
        self._check()
        handle, reference = _SCOPE_ISSUERS[self]
        if (
            handle != self.handle
            or reference is False
            or (reference() if reference else None) is not self._bridge
        ):
            raise TypeError("Scope producer changed or does not support weak ownership")
        previous = _SCOPE_NONCES.get(self, 0)
        nonce = g._uint(previous + 1 if nonce is None else nonce)
        if not nonce or nonce <= previous:
            raise ValueError("state nonce must advance")
        request = bytearray(
            g.encode_request(
                dict(
                    command=33,
                    handle=self.handle,
                    budget=budget or self.budget,
                    payload=_state_payload(revision, ids, fill, budget or self.budget),
                )
            )
        )
        struct.pack_into("<Q", request, 24, nonce)
        _SCOPE_NONCES[self] = nonce
        return GeoSelectedStateAttempt(self, request, g._uint(revision), _token=_AUTHORITY)

    def state(self, *, revision, ids, fill, budget=None):
        self._check()
        if self._bridge is not None:
            raise RuntimeError("use state_async for asynchronous scope")
        payload = _state_payload(revision, ids, fill, budget or self.budget)
        result = _execute(33, handle=self.handle, budget=budget or self.budget, payload=payload)
        return GeoSelectedState(result["handle"], self, _token=_AUTHORITY)

    async def state_async(self, *, revision, ids, fill, budget=None):
        if self._bridge is None:
            return self.state(revision=revision, ids=ids, fill=fill, budget=budget)
        self._check()
        payload = _state_payload(revision, ids, fill, budget or self.budget)
        result = await _issue(
            self._bridge,
            g.encode_request(
                dict(command=33, handle=self.handle, budget=budget or self.budget, payload=payload)
            ),
        )
        return GeoSelectedState(result["handle"], self, _token=_AUTHORITY)

    async def link_async(self, state, *, revision, budget=None):
        if self._bridge is None:
            return self.link(state, revision=revision, budget=budget)
        self._check()
        state._check()
        if state._bridge is not self._bridge:
            raise TypeError("selected State belongs to another transport")
        result = await _issue(
            self._bridge,
            g.encode_request(
                dict(
                    command=34,
                    handle=self.handle,
                    budget=budget or self.budget,
                    payload=struct.pack("<QQ", state.handle, g._uint(revision)),
                )
            ),
        )
        return GeoSelectedState(result["handle"], self, _token=_AUTHORITY)

    def link(self, state, *, revision, budget=None):
        self._check()
        if self._bridge is not None:
            raise RuntimeError("use link_async for asynchronous scope")
        state._check()
        if state._bridge is not self._bridge:
            raise TypeError("selected State belongs to another transport")
        result = _execute(
            34,
            handle=self.handle,
            budget=budget or self.budget,
            payload=struct.pack("<QQ", state.handle, g._uint(revision)),
        )
        return GeoSelectedState(result["handle"], self, _token=_AUTHORITY)


class GeoSelectedState(_Owner):
    def __init__(self, handle, scope, *, _token=None, _captured_bridge=_BRIDGE_UNSET):
        bridge = scope._bridge if _captured_bridge is _BRIDGE_UNSET else _captured_bridge
        super().__init__(handle, bridge, _token=_token)
        self.scope = scope
        try:
            bridge = weakref.ref(self._bridge) if self._bridge is not None else None
        except TypeError:
            bridge = None
        _STATE_AUTHORITIES[self] = dict(
            handle=handle, bridge=bridge, bridge_id=id(self._bridge), live=True, busy=False
        )

    def _check(self):
        super()._check()
        record = _STATE_AUTHORITIES.get(self)
        if record is None or not record["live"] or record["busy"]:
            raise RuntimeError("selected State already consumed or active")

    def close(self):
        if _STATE_AUTHORITIES.get(self, {}).get("busy"):
            raise RuntimeError("selected State already active")
        return super().close()

    async def aclose(self):
        if _STATE_AUTHORITIES.get(self, {}).get("busy"):
            raise RuntimeError("selected State already active")
        return await super().aclose()

    def _consume(self):
        self._live = False
        record = _STATE_AUTHORITIES.get(self)
        if record is not None:
            record["live"] = False

    @property
    def pending_operation(self):
        return _STATE_AUTHORITIES.get(self, {}).get("mutation")

    def begin(self, source, query, *, sequence, indexed=False):
        attempt = GeoSelectedMutationAttempt(
            self, source, query, sequence, indexed, _token=_AUTHORITY
        )
        return attempt.recover()

    async def begin_async(self, source, query, *, sequence, indexed=False):
        if source._bridge is None:
            return self.begin(source, query, sequence=sequence, indexed=indexed)
        attempt = GeoSelectedMutationAttempt(
            self, source, query, sequence, indexed, _token=_AUTHORITY
        )
        return await attempt.recover_async()


class GeoSelectedMutationAttempt:
    """Private pre-dispatch State claim; exact mutation/confirmation survive uncertainty."""

    def __init__(self, state, source, query, sequence, indexed, *, _token=None):
        if _token is not _AUTHORITY or type(indexed) is not bool:
            raise TypeError("issued selected mutation required")
        state._check()
        original = original_geo_allocation_issuer(source)
        if original.bridge is not state._bridge:
            raise TypeError("selected State belongs to another transport")
        source._check(source._bridge is not None)
        self._state_ref, self._source, self._scope = weakref.ref(state), source, state.scope
        self._sequence, self._indexed = g._uint(sequence), indexed
        self._issuer, self._target = original.handle, state.handle if indexed else original.handle
        self._budget = dict(source.budget)
        self._bridge = original.bridge
        self._operation_context = SimpleNamespace(
            budget=self._budget,
            bridge=self._bridge,
            transport=(
                SimpleNamespace(execute=original.execute, read=original.read)
                if self._bridge is not None
                else None
            ),
            reader=source._reader,
            read_page=getattr(source, "_read_page", None),
            write_page=getattr(source, "_write_page", None),
        )
        self._operation = self._active = self._cleanup = None
        self._closed = False
        self._claim = claim_selected_state(state, self._bridge)
        try:
            self._request = g.encode_request(
                dict(
                    command=36 if indexed else 35,
                    handle=self._issuer,
                    sequence=self._sequence,
                    query=query,
                    budget=self._budget,
                    payload=struct.pack("<Q", self._claim.handle),
                )
            )
            bridge = original.bridge
            self._transport = SimpleNamespace(
                execute=original.execute if bridge is not None else None,
                native_execute=_NATIVE_EXECUTE,
            )
            self._attempt = GeoAllocationAttempt(
                source, self._transport, self._request, authenticated=True
            )
        except BaseException:
            self._claim.reject()
            raise
        _STATE_AUTHORITIES[state]["mutation"] = self

    def _validate(self, packet):
        magic, version, code, reserved, handle, sequence = struct.unpack_from("<IIIIQQ", packet)
        if magic != 0x5A475958 or version != 1 or reserved or sequence != self._sequence:
            raise ValueError("selected mutation ownership reply")
        if code == 10 and self._indexed:
            if handle != self._issuer or any(packet[32:48]) or any(packet[52:]):
                raise ValueError("selected fallback ownership reply")
            if struct.unpack_from("<I", packet, 48)[0] not in (1, 2):
                raise ValueError("selected fallback reason")
            return 0
        if code != 0 or handle != self._target or any(packet[32:]):
            raise ValueError("selected mutation ownership reply")
        return handle

    def _accept(self, packet):
        if packet is None:
            if self._attempt.rejected:
                self._claim.reject()
            else:
                self._claim.consume()
            self._closed = True
            return None
        if struct.unpack_from("<I", packet, 8)[0] == 10:
            self._claim.reject()
            self._closed = True
            return dict(
                fallback=True,
                reason=struct.unpack_from("<I", packet, 48)[0],
                state=self._state_ref(),
            )
        self._claim.consume()
        self._source._sequence = self._sequence
        if self._operation is None:
            self._operation = GeoSelectedOperation(
                self._source,
                self._sequence,
                self._request,
                self._scope,
                self._target,
                self._indexed,
                context=self._operation_context,
                _token=_AUTHORITY,
            )
            self._operation._mutation = self
        return self._operation

    def recover(self):
        if self._operation is not None and self._operation._publication_pending:
            raise RuntimeError("selected19 publication remains uncertain; guard retained")
        if self._bridge is not None:
            raise RuntimeError("use recover_async for asynchronous mutation")
        if self._closed or self._cleanup is not None:
            raise RuntimeError("selected mutation unavailable")
        try:
            return self._accept(self._attempt.recover(self._validate))
        except BaseException:
            if self._attempt.rejected:
                self._claim.reject()
                self._closed = True
            raise

    async def recover_async(self):
        if self._operation is not None and self._operation._publication_pending:
            raise RuntimeError("selected19 publication remains uncertain; guard retained")
        if self._bridge is None:
            return self.recover()
        if self._closed or self._cleanup is not None:
            raise RuntimeError("selected mutation unavailable")
        if self._active is None:

            async def run():
                try:
                    return self._accept(await self._attempt.recover_async(self._validate))
                except BaseException:
                    if self._attempt.rejected:
                        self._claim.reject()
                        self._closed = True
                    raise

            self._active = asyncio.create_task(run())
        task = self._active
        try:
            result, interrupted = await g._settle(task)
            if interrupted:
                raise asyncio.CancelledError
            return result
        finally:
            if task.done() and self._active is task:
                self._active = None

    def close(self):
        if self._bridge is not None:
            raise RuntimeError("use aclose for asynchronous mutation")
        if self._closed:
            return
        operation = self.recover()
        if operation is None or isinstance(operation, dict):
            return
        if operation._publication_pending:
            raise RuntimeError("selected19 publication remains uncertain; mutation guard retained")
        if self._attempt.probe_retirement(self._validate) is not None:
            if self._source._busy:
                raise RuntimeError("selected mutation read/ACK settlement pending")
            operation.cancel()
            if self._indexed:
                operation.close()
            if self._attempt.probe_retirement(self._validate) is not None:
                raise RuntimeError("selected mutation retirement pending")
        self._attempt.release()
        self._closed = True

    async def aclose(self):
        if self._bridge is None:
            return self.close()
        if self._closed:
            return
        if self._cleanup is None:
            self._cleanup = asyncio.create_task(self._close_async())
        task = self._cleanup
        try:
            _, interrupted = await g._settle(task)
            if interrupted:
                raise asyncio.CancelledError
        finally:
            if task.done() and self._cleanup is task:
                self._cleanup = None

    async def _close_async(self):
        if self._operation is not None and self._operation._publication_pending:
            raise RuntimeError("selected19 publication remains uncertain; guard retained")
        if self._active is not None:
            await g._settle(self._active)
        operation = self._accept(await self._attempt.recover_async(self._validate))
        if operation is None or isinstance(operation, dict):
            return
        if operation._publication_pending:
            raise RuntimeError("selected19 publication remains uncertain; mutation guard retained")
        if await self._attempt.probe_retirement_async(self._validate) is not None:
            active = self._source._active
            if active is not None and active is not asyncio.current_task():
                active.cancel()
                with suppress(asyncio.CancelledError):
                    await g._settle(active)
            await operation.cancel_async()
            if self._indexed:
                await operation.aclose()
            if await self._attempt.probe_retirement_async(self._validate) is not None:
                raise RuntimeError("selected mutation retirement pending")
        await self._attempt.release_async()
        self._closed = True


class _SelectedPublishedFrame(OwnedGeoData):
    """Same genuine Frame authority; disposal additionally settles its19 birth."""

    def __init__(self, publication, data):
        super().__init__(publication.handle, data, publication.bridge)
        self._publication_owner = publication
        self._frame_cleanup = None

    def close(self):
        identity = _owned_data_identity(self)
        if identity.bridge is not None:
            raise RuntimeError("use aclose for an asynchronous owner")
        if not self._closed:
            self._data = None
            self._publication_owner.close()
            identity.disposed = True
            for callback, _ in identity.hooks:
                callback()
            identity.hooks.clear()
            self._closed = True

    async def aclose(self):
        identity = _owned_data_identity(self)
        if identity.bridge is None:
            return self.close()
        if self._closed:
            return
        if self._frame_cleanup is None:

            async def run():
                self._data = None
                await self._publication_owner.aclose()
                identity.disposed = True
                while identity.hooks:
                    _, callback = identity.hooks[0]
                    await callback()
                    identity.hooks.pop(0)
                self._closed = True

            self._frame_cleanup = asyncio.create_task(run())
        cleanup = self._frame_cleanup
        try:
            _, interrupted = await g._settle(cleanup)
        finally:
            if cleanup.done() and self._frame_cleanup is cleanup:
                self._frame_cleanup = None
        if interrupted:
            raise asyncio.CancelledError


class _SelectedPublication:
    """Exact original304 request, retained before19 and through knownData cleanup."""

    def __init__(self, context, handle, sequence, style):
        self.handle, self.sequence, self.style = handle, sequence, style
        self.budget, self.bridge, self.transport = (
            dict(context.budget),
            context.bridge,
            context.transport,
        )
        self._execute = self.transport.execute if self.transport is not None else None
        self._read = self.transport.read if self.transport is not None else None
        self._frame, self._closed, self._active, self._cleanup = None, False, None, None
        request = g.encode_request(
            dict(command=19, handle=handle, sequence=sequence, budget=self.budget, payload=style)
        )
        self.attempt = GeoAllocationAttempt(
            self,
            SimpleNamespace(execute=self._execute, native_execute=_NATIVE_EXECUTE),
            request,
            authenticated=True,
        )

    def _validate(self, raw):
        magic, version, code, reserved, handle, sequence, length, source = struct.unpack_from(
            "<IIIIQQQQ", raw
        )
        if (
            len(raw) != 256
            or magic != 0x5A475958
            or version != 1
            or code
            or reserved
            or handle != self.handle
            or sequence != self.sequence
            or source != self.handle
            or length > g.MAX_PACKET
            or 4 * length > self.budget["processor_bytes"]
            or any(raw[48:])
        ):
            raise ValueError("selected publication binding mismatch")
        return handle

    def _read_frame(self, raw, packet):
        data = None
        try:
            reply = g.decode_reply(raw)
            if len(packet) != reply["data_length"]:
                raise ValueError("selected publication packet length")
            data = g.parse_scene_data(packet)
            if (
                data.identity["session_handle"] != self.handle
                or data.identity["sequence"] != self.sequence
            ):
                raise ValueError("selected publication packet identity")
            self._frame = _SelectedPublishedFrame(self, data)
            return self._frame
        except BaseException as error:
            packet = data = None
            traceback.clear_frames(error.__traceback__)
            raise

    def prepare(self):
        if self._closed:
            raise RuntimeError("selected publication closed")
        if self._frame is not None:
            return self._frame
        raw = self.attempt.recover(self._validate)
        if raw is None:
            raise RuntimeError("selected publication rejected or retired")
        packet = _NATIVE_READ(
            g.encode_request(dict(command=23, handle=self.handle)), self.budget["processor_bytes"]
        )
        return self._read_frame(raw, packet)

    async def prepare_async(self):
        reader = self._read
        if reader is None:
            raise RuntimeError("asynchronous publication requires captured reader")
        if self._closed:
            raise RuntimeError("selected publication closed")
        if self._frame is not None:
            return self._frame
        if self._active is None:

            async def run():
                raw = await self.attempt.recover_async(self._validate)
                if raw is None:
                    raise RuntimeError("selected publication rejected or retired")
                packet, interrupted = await g._settle(
                    asyncio.create_task(
                        reader(g.encode_request(dict(command=23, handle=self.handle)))
                    )
                )
                if interrupted:
                    packet = None
                    raise asyncio.CancelledError
                return self._read_frame(raw, packet)

            self._active = asyncio.create_task(run())
        task = self._active
        try:
            result, interrupted = await g._settle(task)
            if interrupted:
                raise asyncio.CancelledError
            return result
        finally:
            if task.done():
                self._active = None

    def close(self):
        if self._closed:
            return
        if self._frame is not None:
            self._frame._data = None
        if self.attempt._released:
            self.attempt.forget()
            self._closed, self._frame = True, None
            return
        known = self.attempt.recover(self._validate)
        if known is not None:
            try:
                raw = _NATIVE_EXECUTE(g.encode_request(dict(command=10, handle=self.handle)))
                from ._geo_retained import _confirm_data_disposal

                _confirm_data_disposal(raw, self.handle)
            except BaseException:
                if self.attempt.probe_retirement(self._validate) is not None:
                    raise
        if not self.attempt.rejected:
            if self.attempt.probe_retirement(self._validate) is not None:
                raise RuntimeError("selected Data retirement pending")
            self.attempt.release()
            self.attempt.forget()
        self._closed = True
        self._frame = None

    async def _close_async(self):
        if self._execute is None:
            return self.close()
        if self._closed:
            return
        interrupted = False
        if self._active is not None:
            # The exact known/uncertain attempt is settled below even if the
            # preparer rejected after its callback and read flight settled.
            with suppress(BaseException):
                _, interrupted = await g._settle(self._active)
        if self._frame is not None:
            self._frame._data = None
        if self.attempt._released:
            await self.attempt.forget_async()
            self._closed, self._frame = True, None
            return
        known = await self.attempt.recover_async(self._validate)
        if known is not None:
            try:
                raw, cancelled = await g._settle(
                    asyncio.create_task(
                        self._execute(g.encode_request(dict(command=10, handle=self.handle)))
                    )
                )
                interrupted |= cancelled
                from ._geo_retained import _confirm_data_disposal

                _confirm_data_disposal(raw, self.handle)
            except BaseException:
                if await self.attempt.probe_retirement_async(self._validate) is not None:
                    raise
        if not self.attempt.rejected:
            if await self.attempt.probe_retirement_async(self._validate) is not None:
                raise RuntimeError("selected Data retirement pending")
            await self.attempt.release_async()
            await self.attempt.forget_async()
        self._closed = True
        self._frame = None
        if interrupted:
            raise asyncio.CancelledError

    async def aclose(self):
        if self._closed:
            return
        if self._cleanup is None:
            self._cleanup = asyncio.create_task(self._close_async())
        task = self._cleanup
        try:
            _, interrupted = await g._settle(task)
            if interrupted:
                raise asyncio.CancelledError
        finally:
            if task.done():
                self._cleanup = None


class GeoSelectedOperation:
    def __init__(self, source, sequence, request, scope, handle, indexed, *, context, _token=None):
        if _token is not _AUTHORITY:
            raise TypeError("issued selected authority required")
        self._source, self._sequence, self._request, self._scope = source, sequence, request, scope
        self._handle, self._indexed, self._replaced = handle, indexed, False
        self._publication_pending = False
        self._publication = None
        self._closing = False
        self._publication_context = context
        self._mutation: GeoSelectedMutationAttempt | None = None
        # The pre-dispatch attempt owns these references; acceptance never
        # re-reads caller decorations after a mutation or recovery await.
        self._budget = context.budget
        self._reader, self._read_page, self._write_page = (
            context.reader,
            context.read_page,
            context.write_page,
        )
        self._bridge, self._transport = context.bridge, context.transport
        self._context: Any = SimpleNamespace(
            budget=self._budget, _bridge=self._transport, _reader=self._reader
        )

    @property
    def source(self):
        return self._source

    @property
    def sequence(self):
        return self._sequence

    @property
    def request(self):
        return self._request

    @property
    def scope(self):
        return self._scope

    @property
    def handle(self):
        return self._handle

    @property
    def indexed(self):
        return self._indexed

    def _published(self, reply):
        if reply["handle"] == self.handle and reply["sequence"] == self.sequence:
            self._replaced = True

    def drive(self):
        if self._publication_pending:
            raise RuntimeError("selected19 publication remains uncertain; guard retained")
        if self._replaced:
            raise RuntimeError("selected query replaced")
        if self.source._busy:
            raise RuntimeError("source operation already active")
        if not self.indexed and self.source._closed:
            raise RuntimeError("source disposed")
        self.source._busy = True
        try:
            if self.indexed:
                from ._geo_spatial import drive_index

                return drive_index(
                    self.handle,
                    self.sequence,
                    self._budget,
                    self._reader,
                    self._read_page,
                    self._write_page,
                )
            from ._geo_retained import RetainedGeoSource

            return RetainedGeoSource._drive(self._context, self.sequence, 4, handle=self.handle)
        finally:
            self.source._busy = False

    def prepare(self, style):
        if self._closing:
            raise RuntimeError("selected publication closing")
        if not self._publication_pending and self._replaced:
            raise RuntimeError("selected query replaced")
        if self.source._busy:
            raise RuntimeError("source operation already active")
        if not self.indexed and self.source._closed:
            raise RuntimeError("source disposed")
        view = g._bytes(style)
        if len(view) != 48:
            raise TypeError("exact style required")
        style = bytes(view)
        if self.indexed:
            if self._publication is not None and self._publication.style != style:
                raise ValueError("pending publication requires exact original style")
            if self._publication is None:
                self._publication = _SelectedPublication(
                    self._publication_context, self.handle, self.sequence, style
                )
            self._publication_pending = True
            try:
                frame = self._publication.prepare()
            except BaseException as error:
                traceback.clear_frames(error.__traceback__)
                if self._publication.attempt.rejected:
                    self._publication, self._publication_pending = None, False
                raise
            self._replaced = True
        else:
            from ._geo_retained import RetainedGeoSource

            frame = RetainedGeoSource._prepare(self._context, 11, self.handle, self.sequence, style)
        _attach_frame(self.source, frame, self.sequence, self.request, style, _bridge=self._bridge)
        self._publication_pending = False
        return frame

    def cancel(self):
        if self._publication_pending:
            raise RuntimeError("selected19 publication remains uncertain; guard retained")
        if self._replaced:
            raise RuntimeError("selected query replaced")
        g.decode_reply(
            _NATIVE_EXECUTE(
                g.encode_request(dict(command=9, handle=self.handle, sequence=self.sequence))
            )
        )
        mutation = getattr(self, "_mutation", None)
        if mutation is not None and mutation._attempt.probe_retirement(mutation._validate) is None:
            mutation._attempt.release()

    async def drive_async(self):
        if self._publication_pending:
            raise RuntimeError("selected19 publication remains uncertain; guard retained")
        if self._replaced:
            raise RuntimeError("selected query replaced")
        if self._bridge is None:
            return self.drive()
        if self.source._busy:
            raise RuntimeError("source operation already active")
        if not self.indexed and self.source._closed:
            raise RuntimeError("source disposed")
        self.source._busy, self.source._active = True, asyncio.current_task()
        try:
            if self.indexed:
                from ._geo_spatial import drive_index_async

                return await drive_index_async(
                    self._transport,
                    self.handle,
                    self.sequence,
                    self._budget,
                    self._reader,
                    self._read_page,
                    self._write_page,
                )
            return await g.drive_session(
                self._transport,
                handle=self.handle,
                sequence=self.sequence,
                budget=self._budget,
                read_chunk=self._reader,
            )
        finally:
            self.source._busy, self.source._active = False, None

    async def prepare_async(self, style):
        if self._closing:
            raise RuntimeError("selected publication closing")
        if self._bridge is None:
            return self.prepare(style)
        if self.source._busy:
            raise RuntimeError("source operation already active")
        if not self._publication_pending and self._replaced:
            raise RuntimeError("selected query replaced")
        view = g._bytes(style)
        if len(view) != 48:
            raise TypeError("exact style required")
        style = bytes(view)
        if self.indexed:
            if self._publication is not None and self._publication.style != style:
                raise ValueError("pending publication requires exact original style")
            if self._publication is None:
                self._publication = _SelectedPublication(
                    self._publication_context, self.handle, self.sequence, style
                )
            self._publication_pending = True
            try:
                frame = await self._publication.prepare_async()
                if self._closing:
                    raise RuntimeError("selected publication closing")
            except BaseException as error:
                traceback.clear_frames(error.__traceback__)
                if self._publication.attempt.rejected:
                    self._publication, self._publication_pending = None, False
                raise
            self._replaced = True
        else:
            lease = await g.prepare_scene_data(
                self._transport,
                handle=self.handle,
                sequence=self.sequence,
                budget=self._budget,
                style=style,
            )
            frame = OwnedGeoData(lease.handle, lease.data, self._transport)
            lease._data = None
        _attach_frame(self.source, frame, self.sequence, self.request, style, _bridge=self._bridge)
        self._publication_pending = False
        return frame

    async def cancel_async(self):
        if self._publication_pending:
            raise RuntimeError("selected19 publication remains uncertain; guard retained")
        if self._replaced:
            raise RuntimeError("selected query replaced")
        if self._bridge is None:
            return self.cancel()
        _, interrupted = await g._settle(
            asyncio.create_task(
                self._transport.execute(
                    g.encode_request(dict(command=9, handle=self.handle, sequence=self.sequence))
                )
            )
        )
        mutation = getattr(self, "_mutation", None)
        if (
            mutation is not None
            and await mutation._attempt.probe_retirement_async(mutation._validate) is None
        ):
            await mutation._attempt.release_async()
        if interrupted:
            raise asyncio.CancelledError

    async def aclose(self):
        if self._publication_pending:
            assert self._publication is not None
            self._closing = True
            await self._publication.aclose()
            self._publication_pending = False
            self._replaced = not self._publication.attempt.rejected
            return
        if self._bridge is None:
            return self.close()
        if not self.indexed:
            raise RuntimeError("canonical SourceSession remains caller-owned")
        if not self._replaced:
            _, interrupted = await g._settle(
                asyncio.create_task(
                    self._transport.execute(g.encode_request(dict(command=10, handle=self.handle)))
                )
            )
            self._replaced = True
            mutation = getattr(self, "_mutation", None)
            if (
                mutation is not None
                and await mutation._attempt.probe_retirement_async(mutation._validate) is None
            ):
                await mutation._attempt.release_async()
            if interrupted:
                raise asyncio.CancelledError

    def close(self):
        if self._publication_pending:
            assert self._publication is not None
            self._closing = True
            self._publication.close()
            self._publication_pending = False
            self._replaced = not self._publication.attempt.rejected
            return
        if not self.indexed:
            raise RuntimeError("canonical SourceSession remains caller-owned")
        if not self._replaced:
            g.decode_reply(_NATIVE_EXECUTE(g.encode_request(dict(command=10, handle=self.handle))))
            self._replaced = True
            mutation = getattr(self, "_mutation", None)
            if (
                mutation is not None
                and mutation._attempt.probe_retirement(mutation._validate) is None
            ):
                mutation._attempt.release()


def claim_selected_state(state, bridge):
    """Internal issued State guard; registry values never pin Scope/Source cycles."""
    record = _STATE_AUTHORITIES.get(state)
    if record is None or record["bridge_id"] != id(bridge):
        raise TypeError("issued selected State belongs to another transport")
    if record["bridge"] is not None and record["bridge"]() is not bridge:
        raise TypeError("issued selected State belongs to another transport")
    state._check()
    if not record["live"] or record["busy"]:
        raise RuntimeError("selected State already consumed or active")
    record["busy"] = True
    reference = weakref.ref(state)

    class Claim:
        handle = record["handle"]
        settled = False

        def reject(self):
            if not self.settled:
                self.settled = True
                record["busy"] = False

        def consume(self):
            if not self.settled:
                self.settled = True
                record["busy"], record["live"] = False, False
                original = reference()
                if original is not None:
                    original._live = False

    return Claim()
