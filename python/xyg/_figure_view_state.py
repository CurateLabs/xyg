"""Figure durable view-state cache and state_patch wire messages."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

if TYPE_CHECKING:
    pass

# "selection not passed" sentinel for state_patch_message: None is meaningful
# there (clear the selection), so absence needs its own marker.
_STATE_UNSET: Any = object()


def validated_state_ranges(self, ranges: Any) -> dict[str, list[float]]:
    """Validate a partial ranges mapping against the declared axes.

    Boundary rules match the §2 state document: exact axis IDs only,
    finite ``[lo, hi]`` pairs, no coercion of NaN/infinity.
    """
    if not isinstance(ranges, dict) or not ranges:
        raise ValueError("ranges must be a non-empty mapping of axis id to (lo, hi)")
    out: dict[str, list[float]] = {}
    for axis_id, pair in ranges.items():
        if axis_id not in self.axis_options:
            raise ValueError(f"unknown axis id {axis_id!r}")
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError(f"range for axis {axis_id!r} must be a (lo, hi) pair")
        lo, hi = float(pair[0]), float(pair[1])
        if not math.isfinite(lo) or not math.isfinite(hi) or lo == hi:
            raise ValueError(f"range for axis {axis_id!r} must be finite and non-empty")
        out[axis_id] = [lo, hi]
    return out


def validated_state_selection(range: Any = None, polygon: Any = None) -> Optional[dict[str, Any]]:
    """Normalize a geometric selection to its §2 wire shape (or None)."""
    if range is not None and polygon is not None:
        raise ValueError("pass range= or polygon=, not both")
    if range is not None:
        if isinstance(range, dict):
            try:
                values = [float(range[key]) for key in ("x0", "x1", "y0", "y1")]
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("selection range must supply finite x0, x1, y0, y1") from exc
        else:
            try:
                values = [float(v) for v in range]
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "selection range must be a (x0, x1, y0, y1) tuple or dict"
                ) from exc
            if len(values) != 4:
                raise ValueError("selection range must have exactly x0, x1, y0, y1")
        if not all(math.isfinite(v) for v in values):
            raise ValueError("selection range must be finite")
        x0, x1, y0, y1 = values
        return {"range": {"x0": x0, "x1": x1, "y0": y0, "y1": y1}}
    if polygon is not None:
        try:
            points = [[float(p[0]), float(p[1])] for p in polygon]
        except (TypeError, ValueError, IndexError) as exc:
            raise ValueError("selection polygon must be a sequence of (x, y)") from exc
        if len(points) < 3:
            raise ValueError("selection polygon needs at least 3 points")
        if not all(math.isfinite(v) for point in points for v in point):
            raise ValueError("selection polygon must be finite")
        return {"polygon": points}
    return None


def state_patch_message(
    self,
    *,
    ranges: Any = None,
    selection: Any = _STATE_UNSET,
    animate: bool = True,
    history: bool = True,
) -> dict[str, Any]:
    """Build one §8 ``state_patch`` message (merge-patch semantics: absent
    keys leave that facet of the client state alone)."""
    state: dict[str, Any] = {"v": 1}
    if ranges is not None:
        state["ranges"] = self._validated_state_ranges(ranges)
    if selection is not _STATE_UNSET:
        state["selection"] = selection
    if "ranges" not in state and "selection" not in state:
        raise ValueError("state patch must change ranges or selection")
    return {
        "type": "state_patch",
        "state": state,
        "animate": bool(animate),
        "history": bool(history),
    }


def view_nav_message(self, axes: Any = None) -> dict[str, Any]:
    """Build the §8 ``view_nav`` reset message (axes=None → the client's
    configured reset_axes)."""
    message: dict[str, Any] = {"type": "view_nav", "op": "reset"}
    if axes is not None:
        message["axes"] = self._axis_policy(tuple(axes), "reset axes")
    return message


def selection_rows_message(self, rows: Any) -> tuple[dict[str, Any], list[bytes]]:
    """Kernel-resolve a per-trace row-index selection into the same binary
    mask buffers the gesture selection path ships (§5.1). Rows-selections
    are non-durable by design; the client applies them outside history."""
    if rows is None:
        raise ValueError("rows selection requires per-trace row indices")
    if not isinstance(rows, dict):
        rows = {0: rows}
    traces: list[dict[str, Any]] = []
    out: list[bytes] = []
    total = 0
    for trace_id, indices in rows.items():
        tid = int(trace_id)
        if not 0 <= tid < len(self.traces):
            raise ValueError(f"unknown trace id {trace_id!r}")
        raw = np.asarray(indices)
        # Canonical row indices are validated here, before the uint32
        # wire encoding: a negative or oversized value would otherwise
        # wrap/ship silently (-1 -> 4294967295) and inflate `total`
        # while the browser highlights nothing (staff-review finding).
        integral = raw.size == 0 or (
            raw.dtype != np.bool_
            and (
                np.issubdtype(raw.dtype, np.integer)
                or (
                    np.issubdtype(raw.dtype, np.floating)
                    and bool(np.all(np.isfinite(raw)))
                    and bool(np.all(np.equal(np.mod(raw, 1), 0)))
                )
            )
        )
        if not integral:
            raise ValueError(f"row indices for trace {tid} must be integers, got dtype {raw.dtype}")
        idx = np.unique(np.asarray(raw, dtype=np.int64).ravel())
        n_rows = len(self.traces[tid].x)
        if idx.size and (int(idx[0]) < 0 or int(idx[-1]) >= n_rows):
            raise ValueError(
                f"row indices for trace {tid} must be in [0, {n_rows}), "
                f"got {int(idx[0])}..{int(idx[-1])}"
            )
        wire_idx = self.to_shipped_indices(tid, idx)
        traces.append(
            {
                "id": tid,
                "count": int(len(wire_idx)),
                "buf": len(out),
                "drill_seq": self.traces[tid].drill_seq,
            }
        )
        out.append(wire_idx.tobytes())
        # Deduplicated, validated canonical rows — not the raw request
        # length and not only the currently-shipped subset.
        total += int(idx.size)
    return {"type": "selection_rows", "traces": traces, "total": total}, out


def view_state(self) -> dict[str, Any]:
    """The last committed durable state (§5.1). Served from the kernel's
    event-fed cache — no client round-trip; reads are eventually
    consistent and start at the home ranges before any event arrives."""
    if self._view_state_ranges is not None:
        ranges = {axis_id: list(pair) for axis_id, pair in self._view_state_ranges.items()}
    else:
        ranges = {axis_id: list(self._range(axis_id)) for axis_id in self.axis_options}
    selection = self._view_state_selection
    if isinstance(selection, dict):
        selection = dict(selection)
    return {"v": 1, "ranges": ranges, "selection": selection}


def record_view_ranges(self, ranges: dict[str, list[float]]) -> None:
    """Fold a committed view event's ranges into the state cache."""
    if self._view_state_ranges is None:
        self._view_state_ranges = {
            axis_id: list(self._range(axis_id)) for axis_id in self.axis_options
        }
    for axis_id, pair in ranges.items():
        if axis_id in self.axis_options:
            self._view_state_ranges[axis_id] = [float(pair[0]), float(pair[1])]


def record_selection(self, selection: Optional[dict[str, Any]]) -> None:
    """Fold a committed selection into the state cache; rows-selections
    are recorded only as the opaque ``{"rows": true}`` marker (§2)."""
    self._view_state_selection = selection
