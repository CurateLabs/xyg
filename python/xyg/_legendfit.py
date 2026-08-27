"""Least-occupied legend placement — the host seam behind ``loc="best"``.

`best` is Matplotlib's default `loc`, so it is the spelling users reach for
first. XYG resolves it **at payload-build time** into one of the concrete
locations, which is what makes the three renderers agree: the browser client,
the SVG writer and the raster writer all receive a settled `loc` and none of
them needs its own occupancy model. §28 — the choice is recorded on the wire
rather than made three times behind the user's back.

Occupancy scoring lives in Rust (ABI 120, `xyg_legend_normalize` /
`xyg_legend_best_loc`). This module walks a figure's traces, packs columns and
label lengths, and forwards those envelopes so Python and Node cannot drift.

`xyg.pyplot._axes.Axes._best_legend_loc` carries a second, measured copy of
this scoring that runs against the shim's own entry arrays. The two are pinned
to agree by `tests/test_legend_best_placement.py`; folding the shim onto this
module is a follow-up held back only because the compat stack is rewriting that
method.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional

import numpy as np

from . import kernels

#: Every Matplotlib candidate, in Matplotlib's own preference order (corners,
#: then the mid-edges, then dead center) so a tie keeps the first. Each entry is
#: `(name, x_lo, x_hi, y_lo, y_hi)` in the normalized [0, 1] plot box with y up.
#: Including the centered edges is what lets a full-amplitude oscillation park
#: the legend on its sparse zero-crossing band.
_CANDIDATE_ORDER: tuple[str, ...] = (
    "upper right",
    "upper left",
    "lower left",
    "lower right",
    "center right",
    "center left",
    "lower center",
    "upper center",
    "center",
)

#: Below this spread in mean occupancy two boxes count as tied. Matplotlib's
#: integer badness makes near-equal boxes exact ties broken by candidate order;
#: a continuous metric would otherwise let a sub-percent sampling difference
#: override that order.
_TIE_BAND = 0.02

_FALLBACK = "upper right"

_SCALE_CODE = {"log": 1, "symlog": 2}


def candidate_boxes(
    box_w: float, box_h: float
) -> tuple[tuple[str, float, float, float, float], ...]:
    """The candidate rectangles for a legend of this normalized footprint."""
    cx_lo, cx_hi = 0.5 - box_w / 2.0, 0.5 + box_w / 2.0
    cy_lo, cy_hi = 0.5 - box_h / 2.0, 0.5 + box_h / 2.0
    geometry = {
        "upper right": (1.0 - box_w, 1.0, 1.0 - box_h, 1.0),
        "upper left": (0.0, box_w, 1.0 - box_h, 1.0),
        "lower left": (0.0, box_w, 0.0, box_h),
        "lower right": (1.0 - box_w, 1.0, 0.0, box_h),
        "center right": (1.0 - box_w, 1.0, cy_lo, cy_hi),
        "center left": (0.0, box_w, cy_lo, cy_hi),
        "lower center": (cx_lo, cx_hi, 0.0, box_h),
        "upper center": (cx_lo, cx_hi, 1.0 - box_h, 1.0),
        "center": (cx_lo, cx_hi, cy_lo, cy_hi),
    }
    return tuple((name, *geometry[name]) for name in _CANDIDATE_ORDER)


def legend_footprint(labels: Sequence[str]) -> tuple[float, float]:
    """Fractional footprint of the legend box, grown by row count and the
    longest label, so a crowded legend guards a larger corner region."""
    rows = max(1, len(labels))
    max_len = max((len(str(text)) for text in labels), default=4)
    return min(0.6, 0.12 + 0.03 * max_len), min(0.6, 0.10 + 0.07 * rows)


def display_transform(
    values: np.ndarray, scale: Optional[str], constant: float = 1.0
) -> np.ndarray:
    """Value -> display position, matching `_svg._Scale`.

    Occupancy has to be measured where the marks are *drawn*, not where their
    values sit on a number line: on a log axis 1..10000 is four evenly spaced
    decades, while raw subtraction crushes all but the last into the first 10%
    of the box and would hand `best` the wrong corner.
    """
    if scale == "log":
        return np.log10(np.maximum(values, 1e-300))
    if scale == "symlog":
        return np.sign(values) * np.log1p(np.abs(values) / (constant or 1.0))
    return values


def _scale_code(scale: Optional[str]) -> int:
    return _SCALE_CODE.get(str(scale) if scale is not None else "", 0)


def normalize(
    xv: np.ndarray,
    yv: np.ndarray,
    x_domain: tuple[float, float],
    y_domain: tuple[float, float],
    *,
    x_reverse: bool = False,
    y_reverse: bool = False,
    x_scale: Optional[str] = None,
    y_scale: Optional[str] = None,
    x_constant: float = 1.0,
    y_constant: float = 1.0,
) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """Sample a series down and project it into the normalized plot box.

    Samples outside the displayed domain are **dropped, not clamped**: the
    renderers clip them away, so folding them onto an edge would invent
    occupancy in a corner that is visibly empty. Returns None when the series
    has no finite, visible pair to score.
    """
    try:
        xv, yv = np.broadcast_arrays(
            np.asarray(xv, dtype=np.float64), np.asarray(yv, dtype=np.float64)
        )
    except (TypeError, ValueError):
        return None
    xv, yv = xv.reshape(-1), yv.reshape(-1)
    return kernels.legend_normalize(
        xv,
        yv,
        x_domain,
        y_domain,
        x_reverse=x_reverse,
        y_reverse=y_reverse,
        x_scale=_scale_code(x_scale),
        y_scale=_scale_code(y_scale),
        x_constant=x_constant,
        y_constant=y_constant,
    )


def best_loc(series: Sequence[tuple[np.ndarray, np.ndarray]], labels: Sequence[str]) -> str:
    """The least occupied candidate location for these normalized series."""
    xs_parts: list[np.ndarray] = []
    ys_parts: list[np.ndarray] = []
    starts: list[int] = []
    n = 0
    for xn, yn in series:
        xv = np.asarray(xn, dtype=np.float64).reshape(-1)
        yv = np.asarray(yn, dtype=np.float64).reshape(-1)
        if len(xv) != len(yv):
            raise ValueError("legend series x and y must have equal length")
        starts.append(n)
        xs_parts.append(xv)
        ys_parts.append(yv)
        n += len(xv)
    xs = np.concatenate(xs_parts) if xs_parts else np.empty(0, dtype=np.float64)
    ys = np.concatenate(ys_parts) if ys_parts else np.empty(0, dtype=np.float64)
    start_arr = np.asarray(starts, dtype=np.uintp)
    label_lens = np.asarray([len(str(text)) for text in labels], dtype=np.uint32)
    return _CANDIDATE_ORDER[kernels.legend_best_loc(xs, ys, start_arr, label_lens)]


def resolve_for_figure(figure: Any) -> str:
    """Resolve `loc="best"` against a built `Figure`'s own trace arrays."""
    series: list[tuple[np.ndarray, np.ndarray]] = []
    labels: list[str] = []
    for trace in getattr(figure, "traces", ()):
        if getattr(trace, "hidden", False):
            continue
        name = getattr(trace, "name", None)
        if name:
            labels.append(str(name))
        # A trace holds canonical `Column`s, not bare arrays (§27).
        xv, yv = (
            _column_values(getattr(trace, "x", None)),
            _column_values(getattr(trace, "y", None)),
        )
        if xv is None or yv is None:
            continue
        domains = _figure_domains(figure, trace)
        if domains is None:
            continue
        (x_domain, x_reverse, x_scale, x_const), (y_domain, y_reverse, y_scale, y_const) = domains
        projected = normalize(
            xv,
            yv,
            x_domain,
            y_domain,
            x_reverse=x_reverse,
            y_reverse=y_reverse,
            x_scale=x_scale,
            y_scale=y_scale,
            x_constant=x_const,
            y_constant=y_const,
        )
        if projected is not None:
            series.append(projected)
    return best_loc(series, labels)


def _column_values(column: Any) -> Optional[np.ndarray]:
    """The f64 array behind a canonical `Column`, or a bare array unchanged."""
    if column is None:
        return None
    values = getattr(column, "values", column)
    return values if isinstance(values, np.ndarray) else None


def _figure_domains(figure: Any, trace: Any) -> Optional[tuple[tuple, tuple]]:
    """The displayed x/y limits a trace is drawn against, or None if unknown.

    `Figure._range` already resolves a fixed `domain=` against autorange and
    encodes `reverse=` by returning the pair descending, so read the direction
    back off the ordering rather than re-deriving it from the axis options.
    """
    axis_ids = (
        getattr(trace, "x_axis", None) or "x",
        getattr(trace, "y_axis", None) or "y",
    )
    options = getattr(figure, "axis_options", {}) or {}
    out: list[tuple[tuple[float, float], bool, Optional[str], float]] = []
    for axis_id in axis_ids:
        try:
            lo, hi = (float(v) for v in figure._range(axis_id))
        except Exception:  # noqa: BLE001 — an unrangeable axis simply is not scored
            return None
        reverse = lo > hi
        if reverse:
            lo, hi = hi, lo
        if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
            return None
        # The public axis option is `type_=`, stored as `type`; `_svg._Scale`
        # reads the same names off the serialized axis.
        axis = options.get(axis_id) or {}
        scale = axis.get("type") or axis.get("scale")
        constant = axis.get("constant")
        out.append(((lo, hi), reverse, scale, float(constant) if constant else 1.0))
    return out[0], out[1]
