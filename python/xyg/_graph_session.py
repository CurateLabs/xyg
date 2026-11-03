"""Private native XYGI/XYGR byte transport; no graph policy or wire codec.

See spec/design/graph-session-python-transport.md. This is an internal S6
foundation, not a public chart, widget, or notebook session API.
"""

from __future__ import annotations

import ctypes as ct
import operator
import sys
import threading
from enum import IntEnum

from . import _native

# Serializes the entire query/copy transaction with create and destroy, including
# native OPEN retries which can return the same handle to different wrappers.
_lifecycle_lock = threading.Lock()
_MAX_BUFFER = min(sys.maxsize, ct.c_size_t(-1).value)


class GraphSessionStatus(IntEnum):
    """Existing native interaction statuses (graph-interaction.md §3)."""

    OK = 0
    STALE = -1
    UNLINKED = -2
    INVALID = -3
    BUDGET = -4
    CAPACITY = -5
    SELF_ECHO = -6
    STALE_REMOTE = -7
    SELECTION_TOO_LARGE = -8
    COMPOUND_TOO_LARGE = -9
    UNBOUND = -10
    REVISION_EXHAUSTED = -11


class GraphSessionError(RuntimeError):
    """Value-free private failure; ``status`` is the native code, or None locally."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _check_status(status: int) -> None:
    if status != GraphSessionStatus.OK:
        raise GraphSessionError("native graph session request failed", status=status)


def _u64(value: int) -> int:
    if isinstance(value, bool):
        raise TypeError("graph session identity must be an unsigned 64-bit integer")
    try:
        result = operator.index(value)
    except TypeError:
        raise TypeError("graph session identity must be an unsigned 64-bit integer") from None
    if not 0 <= result < 1 << 64:
        raise ValueError("graph session identity must be an unsigned 64-bit integer")
    return result


def _input(data: bytes | bytearray | memoryview) -> ct.Array:
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("graph session input must be a byte buffer")
    try:
        view = memoryview(data)
    except ValueError:
        raise ValueError("graph session input buffer is unavailable") from None
    if view.ndim != 1 or view.itemsize != 1 or not view.c_contiguous:
        raise ValueError("graph session input must be a contiguous one-dimensional byte buffer")
    if view.nbytes > _MAX_BUFFER:
        raise ValueError("graph session input exceeds host buffer bounds")
    # One private snapshot survives every native call, even for mutable input.
    return (ct.c_uint8 * view.nbytes).from_buffer_copy(view)


class GraphSession:
    """Own a native handle, forwarding opaque requests and complete reply bytes.

    Use a context manager or explicit close. Native byte-identical OPEN retries
    alias the same lifetime: closing either wrapper revokes that native handle.
    """

    def __init__(
        self,
        document: bytes | bytearray | memoryview,
        opening: bytes | bytearray | memoryview,
        *,
        instance_id: int,
        group_id: int,
    ) -> None:
        self._handle: int | None = None
        with _lifecycle_lock:
            instance, group = _u64(instance_id), _u64(group_id)
            document_input, opening_input = _input(document), _input(opening)
            handle = ct.c_uint64()
            _check_status(
                _native._lib.xyg_graphforge_session_create(
                    document_input,
                    len(document_input),
                    opening_input,
                    len(opening_input),
                    instance,
                    group,
                    ct.byref(handle),
                )
            )
            self._handle = handle.value

    def _require_handle(self) -> int:
        if self._handle is None:
            raise GraphSessionError("graph session is closed")
        return self._handle

    def _command(self, symbol: str, request: bytes | bytearray | memoryview) -> bytes:
        with _lifecycle_lock:
            handle = self._require_handle()
            data = _input(request)
            function = getattr(_native._lib, symbol)
            output = None
            capacity = 0
            while True:
                length = ct.c_size_t()
                status = function(handle, data, len(data), output, capacity, ct.byref(length))
                if status == GraphSessionStatus.CAPACITY:
                    # No guessed growth or replay synthesis: use the native length
                    # exactly. A non-growing refusal cannot be retried usefully.
                    if length.value <= capacity:
                        _check_status(status)
                    if length.value > _MAX_BUFFER:
                        raise GraphSessionError(
                            "native graph session reply exceeds host buffer bounds"
                        )
                    capacity = length.value
                    output = None
                    output = (ct.c_uint8 * capacity)()
                    continue
                _check_status(status)
                if length.value > capacity:
                    raise GraphSessionError("native graph session reply length is invalid")
                return ct.string_at(output, length.value) if output is not None else b""

    def update(self, request: bytes | bytearray | memoryview) -> bytes:
        return self._command("xyg_graphforge_session_update", request)

    def render(self, request: bytes | bytearray | memoryview) -> bytes:
        return self._command("xyg_graphforge_session_render", request)

    def interact(self, request: bytes | bytearray | memoryview) -> bytes:
        return self._command("xyg_graphforge_session_interact", request)

    def poll_event(self, request: bytes | bytearray | memoryview) -> bytes:
        return self._command("xyg_graphforge_session_poll_event", request)

    def bind_temporal(self, request: bytes | bytearray | memoryview) -> bytes:
        return self._command("xyg_graphforge_session_bind_temporal", request)

    def unbind_temporal(self, request: bytes | bytearray | memoryview) -> bytes:
        """Forward the caller's Bind request with temporal.u64[0], unchanged."""
        return self._command("xyg_graphforge_session_bind_temporal", request)

    def coordinate_deliver(self, request: bytes | bytearray | memoryview) -> bytes:
        return self._command("xyg_graphforge_coordinate_deliver", request)

    def close(self) -> None:
        with _lifecycle_lock:
            if self._handle is None:
                return
            status = _native._lib.xyg_graphforge_session_destroy(self._handle)
            if status != GraphSessionStatus.UNBOUND:
                _check_status(status)
            self._handle = None

    def __enter__(self) -> GraphSession:
        with _lifecycle_lock:
            self._require_handle()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
