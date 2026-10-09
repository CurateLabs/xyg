"""Explicit typed linked-state ownership. Rust owns every selection decision."""

from __future__ import annotations

import asyncio
import struct
import weakref

import numpy as np

from . import _geoscale as g
from ._geo_retained import _aprepare, _attach_frame

_AUTHORITY = object()
_STATE_AUTHORITIES: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


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


class GeoSelectedScope(_Owner):
    """Create from an immutable painted frame; close remains retryable if held."""

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
    def __init__(self, handle, scope, *, _token=None):
        super().__init__(handle, scope._bridge, _token=_token)
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

    def begin(self, source, query, *, sequence, indexed=False):
        """Consume only after successful canonical begin; caller drives explicitly."""
        self._check()
        if source._bridge is not self._bridge:
            raise TypeError("selected State belongs to another transport")
        if type(indexed) is not bool:
            raise TypeError("indexed must be boolean")
        source._check()
        request = g.encode_request(
            dict(
                command=36 if indexed else 35,
                handle=source.handle,
                sequence=sequence,
                query=query,
                budget=source.budget,
                payload=struct.pack("<Q", self.handle),
            )
        )
        reply = g.decode_reply(g.execute(request))
        if reply["code"] == 10:
            return dict(fallback=True, reason=reply["fallback_reason_code"], state=self)
        if (
            reply["code"] != 0
            or reply["handle"] != (self.handle if indexed else source.handle)
            or reply["sequence"] != sequence
        ):
            raise ValueError("selected begin ownership reply")
        self._consume()
        source._sequence = sequence
        return GeoSelectedOperation(
            source, sequence, request, self.scope, reply["handle"], indexed, _token=_AUTHORITY
        )

    async def begin_async(self, source, query, *, sequence, indexed=False):
        if source._bridge is None:
            return self.begin(source, query, sequence=sequence, indexed=indexed)
        self._check()
        if source._bridge is not self._bridge:
            raise TypeError("selected State belongs to another transport")
        if type(indexed) is not bool:
            raise TypeError("indexed must be boolean")
        source._check(True)
        request = g.encode_request(
            dict(
                command=36 if indexed else 35,
                handle=source.handle,
                sequence=sequence,
                query=query,
                budget=source.budget,
                payload=struct.pack("<Q", self.handle),
            )
        )
        raw, interrupted = await g._settle(asyncio.create_task(source._bridge.execute(request)))
        reply = g.decode_reply(raw)
        if reply["code"] == 10:
            if interrupted:
                raise asyncio.CancelledError
            return dict(fallback=True, reason=reply["fallback_reason_code"], state=self)
        if (
            reply["code"] != 0
            or reply["handle"] != (self.handle if indexed else source.handle)
            or reply["sequence"] != sequence
        ):
            raise ValueError("selected begin ownership reply")
        self._consume()
        source._sequence = sequence
        operation = GeoSelectedOperation(
            source, sequence, request, self.scope, reply["handle"], indexed, _token=_AUTHORITY
        )
        if interrupted:
            try:
                await operation.cancel_async()
            finally:
                if indexed:
                    await operation.aclose()
            raise asyncio.CancelledError
        return operation


class GeoSelectedOperation:
    def __init__(self, source, sequence, request, scope, handle, indexed, *, _token=None):
        if _token is not _AUTHORITY:
            raise TypeError("issued selected authority required")
        self.source, self.sequence, self.request, self.scope = source, sequence, request, scope
        self.handle, self.indexed, self._replaced = handle, indexed, False

    def _published(self, reply):
        if reply["handle"] == self.handle and reply["sequence"] == self.sequence:
            self._replaced = True

    def drive(self):
        if self._replaced:
            raise RuntimeError("selected query replaced")
        self.source._check()
        self.source._busy = True
        try:
            if self.indexed:
                from ._geo_spatial import drive_index

                return drive_index(
                    self.handle,
                    self.sequence,
                    self.source.budget,
                    self.source._reader,
                    self.source._read_page,
                    self.source._write_page,
                )
            return self.source._drive(self.sequence, 4)
        finally:
            self.source._busy = False

    def prepare(self, style):
        if self._replaced:
            raise RuntimeError("selected query replaced")
        self.source._check()
        view = g._bytes(style)
        if len(view) != 48:
            raise TypeError("exact style required")
        style = bytes(view)
        frame = self.source._prepare(
            19 if self.indexed else 11,
            self.handle,
            self.sequence,
            style,
            _on_reply=self._published if self.indexed else None,
        )
        if self.indexed:
            self._replaced = True
        _attach_frame(self.source, frame, self.sequence, self.request, style)
        return frame

    def cancel(self):
        if self._replaced:
            raise RuntimeError("selected query replaced")
        _execute(9, handle=self.handle, sequence=self.sequence)

    async def drive_async(self):
        if self._replaced:
            raise RuntimeError("selected query replaced")
        if self.source._bridge is None:
            return self.drive()
        self.source._check(True)
        self.source._busy, self.source._active = True, asyncio.current_task()
        try:
            if self.indexed:
                from ._geo_spatial import drive_index_async

                return await drive_index_async(
                    self.source._bridge,
                    self.handle,
                    self.sequence,
                    self.source.budget,
                    self.source._reader,
                    self.source._read_page,
                    self.source._write_page,
                )
            return await g.drive_session(
                self.source._bridge,
                handle=self.handle,
                sequence=self.sequence,
                budget=self.source.budget,
                read_chunk=self.source._reader,
            )
        finally:
            self.source._busy, self.source._active = False, None

    async def prepare_async(self, style):
        if self.source._bridge is None:
            return self.prepare(style)
        self.source._check(True)
        if self._replaced:
            raise RuntimeError("selected query replaced")
        view = g._bytes(style)
        if len(view) != 48:
            raise TypeError("exact style required")
        style = bytes(view)
        if self.indexed:
            frame = await _aprepare(
                self.source, 19, self.handle, self.sequence, style, _on_reply=self._published
            )
            self._replaced = True
        else:
            lease = await g.prepare_scene_data(
                self.source._bridge,
                handle=self.handle,
                sequence=self.sequence,
                budget=self.source.budget,
                style=style,
            )
            from ._geo_retained import OwnedGeoData

            frame = OwnedGeoData(lease.handle, lease.data, self.source._bridge)
            lease._data = None  # Ownership transfer, no disposal or packet copy.
        _attach_frame(self.source, frame, self.sequence, self.request, style)
        return frame

    async def cancel_async(self):
        if self._replaced:
            raise RuntimeError("selected query replaced")
        if self.source._bridge is None:
            return self.cancel()
        _, interrupted = await g._settle(
            asyncio.create_task(
                self.source._bridge.execute(
                    g.encode_request(dict(command=9, handle=self.handle, sequence=self.sequence))
                )
            )
        )
        if interrupted:
            raise asyncio.CancelledError

    async def aclose(self):
        if self.source._bridge is None:
            return self.close()
        if not self.indexed:
            raise RuntimeError("canonical SourceSession remains caller-owned")
        if not self._replaced:
            _, interrupted = await g._settle(
                asyncio.create_task(
                    self.source._bridge.execute(
                        g.encode_request(dict(command=10, handle=self.handle))
                    )
                )
            )
            self._replaced = True
            if interrupted:
                raise asyncio.CancelledError

    def close(self):
        if not self.indexed:
            raise RuntimeError("canonical SourceSession remains caller-owned")
        if not self._replaced:
            _execute(10, handle=self.handle)
            self._replaced = True


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
