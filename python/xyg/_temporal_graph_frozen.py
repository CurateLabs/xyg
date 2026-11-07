"""Owned native temporal snapshot; host code only frames and reads Rust bytes."""

from __future__ import annotations

import ctypes as ct
import struct
from types import MappingProxyType

from . import _native
from ._graphforge_container import decode_container

_ISSUED = object()

MAX_BYTES = 24 * 1024 * 1024
MAX_PEAK = 384 * 1024 * 1024


def _check(status):
    _native._temporal_controller_status(status)


class FrozenTemporalGraph:
    """Immutable canonical XYFG snapshot with an independent native lifetime.

    Use ``close`` or a context manager. This checkpoint stores provenance and
    optional retained publication planes and renders through canonical Scenes.
    Imported bytes are offline provenance and never restore a live graph handle.
    """

    __slots__ = ("__handle",)

    def __init__(self, token, handle):
        if token is not _ISSUED:
            raise TypeError("use TemporalGraph.freeze or FrozenTemporalGraph.from_bytes")
        self.__handle = handle

    @classmethod
    def from_bytes(cls, data: bytes, *, budget_bytes: int = MAX_PEAK):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("data must be a byte buffer")
        if memoryview(data).nbytes > MAX_BYTES:
            raise _native.TemporalNativeError(-2)
        raw = bytes(data)
        buf = (ct.c_uint8 * len(raw)).from_buffer_copy(raw)
        handle = ct.c_uint64()
        _check(
            _native._lib.xyg_temporal_graph_frozen_import(
                buf, len(raw), _native._temporal_u64(budget_bytes, "budget_bytes"), ct.byref(handle)
            )
        )
        return cls(_ISSUED, handle.value)

    def to_bytes(self) -> bytes:
        if self.__handle is None:
            raise RuntimeError("FrozenTemporalGraph is closed")
        length = ct.c_uint64()
        status = _native._lib.xyg_temporal_graph_frozen_copy(
            self.__handle, None, 0, ct.byref(length)
        )
        if status != -9:
            _check(status)
        buf = (ct.c_uint8 * length.value)()
        _check(
            _native._lib.xyg_temporal_graph_frozen_copy(
                self.__handle, buf, len(buf), ct.byref(length)
            )
        )
        return bytes(buf)

    def export(self, format, *, focus_rgba=None, scale=1.0, budget_bytes=MAX_PEAK):
        """Render captured paint; v1 snapshots require an explicit focus override."""
        formats = {"svg": 0, "png": 1, "html": 2, "scene": 3, "painter": 4}
        client = b""
        if format == "html":
            from .export import _bundled_js

            client = _bundled_js().encode("utf-8")
        return _execute(
            self.to_bytes(), 1, formats[format], scale, focus_rgba, budget_bytes, client
        )

    def capture_focus(self, focus_rgba, *, budget_bytes=MAX_PEAK):
        """Return v2 provenance with an explicit resolved display color."""
        return self.from_bytes(
            _execute(self.to_bytes(), 3, 0, 1.0, focus_rgba, budget_bytes),
            budget_bytes=budget_bytes,
        )

    @classmethod
    def from_artifact(cls, data, *, budget_bytes=MAX_PEAK):
        """Validate the complete rendered artifact and recover its exact XYFG."""
        client = b""
        if memoryview(data).cast("B")[:15].tobytes() == b"<!doctype html>":
            from .export import _bundled_js

            client = _bundled_js().encode("utf-8")
        return cls.from_bytes(
            _execute(data, 2, 0, 1.0, None, budget_bytes, client), budget_bytes=budget_bytes
        )

    @property
    def metadata(self):
        """Read-only inspection of validated bytes; UUID planes are immutable bytes."""
        fields = decode_container(self.to_bytes()[:-8], "XYFG")
        result = {}
        for (name, _index), value in fields.items():
            if hasattr(value, "tolist"):
                value = tuple(value.tolist())
            result[name] = value
        return MappingProxyType(result)

    def close(self):
        handle, self.__handle = self.__handle, None
        if handle is not None:
            _check(_native._lib.xyg_temporal_graph_frozen_destroy(handle))

    def __enter__(self):
        if self.__handle is None:
            raise RuntimeError("FrozenTemporalGraph is closed")
        return self

    def __exit__(self, *_args):
        self.close()

    def __del__(self):
        handle = getattr(self, "_FrozenTemporalGraph__handle", None)
        if handle is not None:
            _native._lib.xyg_temporal_graph_frozen_destroy(handle)


def freeze(
    graph,
    *,
    revision,
    window=None,
    timezone,
    session=None,
    render_revision=0,
    budget_bytes=MAX_PEAK,
):
    if not isinstance(timezone, str):
        raise TypeError("timezone must be a string")
    raw = timezone.encode("utf-8")
    if len(raw) > 128:
        raise _native.TemporalNativeError(-4)
    if window is not None and (not isinstance(window, tuple) or len(window) != 2):
        raise ValueError("window must be None or a (start, end) tuple")
    start, end = (0, 0) if window is None else window
    # Coerce before obtaining handles; callbacks in integer conversion may close sources.
    revision = _native._temporal_u64(revision, "revision")
    start, end = (
        _native._temporal_i64(start, "window start"),
        _native._temporal_i64(end, "window end"),
    )
    render_revision = _native._temporal_u64(render_revision, "render_revision")
    if render_revision > 0xFFFFFFFF:
        raise ValueError("render_revision must fit u32")
    budget = _native._temporal_u64(budget_bytes, "budget_bytes")
    zone = (ct.c_uint8 * len(raw)).from_buffer_copy(raw)
    handle = ct.c_uint64()
    _check(
        _native._lib.xyg_temporal_graph_freeze(
            graph._open_handle(),
            revision,
            int(window is not None),
            start,
            end,
            zone,
            len(raw),
            0 if session is None else session._require_handle(),
            render_revision,
            budget,
            ct.byref(handle),
        )
    )
    return FrozenTemporalGraph(_ISSUED, handle.value)


def _execute(data, operation, format, scale, focus, budget, client=b""):
    if focus is not None and (
        len(focus) != 4 or any(type(v) is not int or not 0 <= v <= 255 for v in focus)
    ):
        raise ValueError("focus_rgba requires four integer bytes")
    view = memoryview(data)
    if view.nbytes + len(client) > MAX_PEAK // 4 or (
        operation in (1, 3, 4) and view.nbytes > MAX_BYTES
    ):
        raise ValueError("frozen input exceeds admission limit")
    data = bytes(view)
    packet = bytearray(64)
    packet[:4] = b"XYFX"
    struct.pack_into(
        "<IIIIIdQQQ",
        packet,
        4,
        1,
        operation,
        format,
        int.from_bytes(bytes(focus or (0, 0, 0, 0)), "little"),
        int(focus is not None),
        scale,
        len(data),
        len(client),
        budget,
    )
    packet.extend(data)
    packet.extend(client)
    buf = (ct.c_uint8 * len(packet)).from_buffer_copy(packet)
    size = ct.c_uint64()

    def call(out, cap):
        return _native._lib.xyg_temporal_graph_frozen_execute(
            buf, len(buf), budget, out, cap, ct.byref(size)
        )

    status = call(None, 0)
    if status != -9:
        _check(status)
    out = (ct.c_uint8 * size.value)()
    _check(call(out, len(out)))
    return bytes(out)
