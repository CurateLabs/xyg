"""Figure autorange — XYAR packing and Rust `figure_autorange` dispatch."""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING, Optional

import numpy as np

from . import _native

if TYPE_CHECKING:
    from ._figure import Figure

AUTORANGE_KIND = {
    "scatter": 0,
    "line": 1,
    "bar": 2,
    "column": 3,
    "histogram": 4,
    "violin": 5,
    "box": 6,
    "box_whisker": 7,
    "box_median": 8,
    "segments": 9,
    "errorbar": 10,
    "stem": 11,
    "area": 12,
    "error_band": 13,
    "ribbon": 14,
    "triangle_mesh": 15,
    "hexbin": 16,
    "heatmap": 17,
}
AUTORANGE_ROLES = (
    ("x", 0),
    ("y", 1),
    ("x0", 2),
    ("x1", 3),
    ("y0", 4),
    ("y1", 5),
    ("base", 6),
)


def auto_domain(bounds: Optional[tuple[float, float]]) -> tuple[float, float]:
    """Finite increasing domain for auto-scaled scalar marks.

    Kernels require `hi > lo`; user data does not owe us variance. Expand a
    degenerate domain the same way autorange does so constant histograms and
    heatmaps render instead of tripping an internal precondition. Rust owns
    the pad; this method only forwards the optional bounds.
    """
    return _native.auto_domain(bounds)


def x_range(self: "Figure") -> tuple[float, float]:
    return range_(self, "x")


def y_range(self: "Figure") -> tuple[float, float]:
    return range_(self, "y")


def range_(self: "Figure", axis_id: str, *, use_domain: bool = True) -> tuple[float, float]:
    try:
        return _native.figure_autorange(pack_autorange(self, axis_id, use_domain=use_domain))
    except ValueError as error:
        if "log axis requires" in str(error):
            raise ValueError(f"{axis_id} log axis requires at least one positive value") from error
        raise


def pack_autorange(self: "Figure", axis_id: str, *, use_domain: bool = True) -> bytes:
    """Pack literal axis/trace extents for Rust's XYAR autorange ABI."""
    opts = self.axis_options.get(axis_id, {})
    flags = 0
    if use_domain:
        flags |= 1 << 0
    if opts.get("reverse"):
        flags |= 1 << 1
    domain = opts.get("domain")
    if domain is not None:
        flags |= 1 << 2
    configured_margin = opts.get("margin")
    if configured_margin is not None:
        flags |= 1 << 3
    if self.coords == "polar":
        flags |= 1 << 4
    axis_dim = self._axis_dim(axis_id)
    if axis_dim == "x":
        flags |= 1 << 5
    scale = self._axis_scale(axis_id)
    scale_code = 1 if scale == "log" else 2 if scale == "symlog" else 0
    kind = self._axis_kind(axis_id)
    kind_code = 1 if kind == "time" else 2 if kind == "category" else 0
    theta_unit = 1 if (opts.get("theta_unit") or "radians") == "degrees" else 0
    categories = self._axis_categories.get(axis_id) if self.coords == "polar" else None
    n_categories = len(categories) if categories else 0
    domain_lo, domain_hi = (
        (float(domain[0]), float(domain[1])) if domain is not None else (0.0, 0.0)
    )
    margin = 0.0 if configured_margin is None else float(configured_margin)
    payload = bytearray(
        struct.pack(
            "<4sIIBBBBHHI3d",
            b"XYAR",
            1,
            flags,
            scale_code,
            kind_code,
            theta_unit,
            0,
            len(self.traces),
            n_categories,
            0,
            domain_lo,
            domain_hi,
            margin,
        )
    )
    for t in self.traces:
        if t.kind == "ribbon" and (t.x0 is None or t.x1 is None or t.y0 is None or t.y1 is None):
            raise ValueError("ribbon trace missing geometry columns")
        trace_flags = 0
        if t.x_axis == axis_id:
            trace_flags |= 1 << 0
        if t.y_axis == axis_id:
            trace_flags |= 1 << 1
        has_endpoints = t.x0 is not None and t.x1 is not None and t.y0 is not None and t.y1 is not None
        if has_endpoints:
            trace_flags |= 1 << 2
        if t.base is not None:
            trace_flags |= 1 << 3
        columns: list[bytes] = []
        for name, role in AUTORANGE_ROLES:
            col = getattr(t, name, None)
            if col is None:
                continue
            zone = col.zone
            pos_min = float(zone.positive_min)
            pos_max = float(zone.positive_max)
            if not np.isfinite(pos_min):
                pos_min = float("nan")
            if not np.isfinite(pos_max):
                pos_max = float("nan")
            columns.append(
                struct.pack(
                    "<B7xdddd",
                    role,
                    float(col.min),
                    float(col.max),
                    pos_min,
                    pos_max,
                )
            )
        zb = 0xFF
        if t.kind in {"bar", "column", "histogram"} and has_endpoints:
            base = t.x0.values if axis_dim == "x" else t.y0.values
            value = t.x1.values if axis_dim == "x" else t.y1.values
            zb = _native.rect_zero_baseline_flags(base, value)
        payload.append(AUTORANGE_KIND.get(t.kind, 255))
        payload.append(trace_flags)
        payload.append(len(columns))
        payload.append(zb)
        for packed in columns:
            payload.extend(packed)
    return bytes(payload)


def zero_baseline_anchor(self: "Figure", axis_id: str) -> Optional[str]:
    """Pin zero to the plot edge for positive/negative rectangle charts.

    Histograms and bars encode their baseline as a rectangle edge. Padding
    away from that edge makes the bars visually float above the axis, so the
    value axis keeps zero flush when every mark extends in one direction.
    """
    axis = self._axis_dim(axis_id)
    for t in self.traces:
        # Only rectangle families have a sticky zero edge. Segment-based
        # marks such as stem/errorbar also carry x0/x1/y0/y1 columns, but
        # Matplotlib pads their baseline like ordinary line data.
        if t.kind not in {"bar", "column", "histogram"}:
            continue
        if axis == "x" and t.x_axis != axis_id:
            continue
        if axis == "y" and t.y_axis != axis_id:
            continue
        if t.x0 is None or t.x1 is None or t.y0 is None or t.y1 is None:
            continue
        base = t.x0.values if axis == "x" else t.y0.values
        value = t.x1.values if axis == "x" else t.y1.values
        # Ask the questions as masked predicates rather than compacting
        # `base`/`value` down to their finite rows first: the compaction
        # allocates and copies two full columns per axis per build, and
        # every question here is a single "does any row violate this?".
        finite = np.isfinite(base) & np.isfinite(value)
        if not finite.any():
            continue
        flags = _native.rect_zero_baseline_flags(base, value)
        if flags == 0xFF or flags & 1 == 0:
            continue
        if flags & 2:
            continue
        if flags & 4 == 0:
            return "lo"
        if flags & 8 == 0:
            return "hi"
    return None
