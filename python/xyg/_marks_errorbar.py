"""Error bar and error band marks — segment instancing via shared helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Union

import numpy as np

from . import _validate, kernels, styles
from ._figure_ingest import as_float_array
from ._trace import Trace
from ._typing import ArrayLike, Scalar

if TYPE_CHECKING:
    from ._figure import Figure


def error_extent(
    value: Union[Scalar, ArrayLike], n: int, center: np.ndarray, label: str
) -> tuple[np.ndarray, np.ndarray]:
    """Normalize scalar, symmetric, or ``(lower, upper)`` error input."""
    if value is None:
        raise ValueError(f"{label} must not be None")
    if np.isscalar(value):
        amount = _validate.finite_scalar(value, label)
        if amount < 0:
            raise ValueError(f"{label} must be non-negative")
        amount_arr = np.full(n, amount, dtype=np.float64)
        return center - amount_arr, center + amount_arr
    arr = as_float_array(value, label)
    if arr.ndim == 1:
        if len(arr) != n:
            raise ValueError(f"{label} must have length {n}, got {len(arr)}")
        lower_amount, upper_amount = arr, arr
    elif arr.shape == (2, n):
        lower_amount, upper_amount = arr[0], arr[1]
    elif arr.shape == (n, 2):
        lower_amount, upper_amount = arr[:, 0], arr[:, 1]
    else:
        raise ValueError(f"{label} must be a scalar, length-{n} array, or a 2x{n} array")
    # Non-finite extents must never reach vertex buffers (§19), and NaN
    # slips past a `< 0` comparison — reject it here with the input's name.
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{label} must be finite")
    if np.any(arr < 0):
        raise ValueError(f"{label} must be non-negative")
    return center - lower_amount, center + upper_amount


def auto_cap_size(positions: np.ndarray) -> float:
    """Auto cap half-width in data units for error bars.

    0.25x the median adjacent spacing of the distinct finite positions along
    the cap's axis; 0.4 when fewer than two are distinct (no spacing exists).

    The positions an error bar carries are usually an ordered independent
    variable, and `np.unique` sorts unconditionally — an O(N log N) pass over
    the whole column to answer a question about adjacent gaps. One O(N) diff
    both proves the column is already non-decreasing and yields those gaps
    directly; only an out-of-order column pays for the sort. Same distinct
    values in the same order either way, so the median is identical.
    """
    finite = positions[np.isfinite(positions)]
    if len(finite) >= 2:
        gaps = np.diff(finite)
        if (gaps >= 0.0).all():
            positive = gaps[gaps != 0.0]
            return 0.25 * float(np.median(positive)) if len(positive) else 0.4
    distinct = np.unique(finite)
    if len(distinct) < 2:
        return 0.4
    return 0.25 * float(np.median(np.diff(distinct)))


def error_band(
    self: "Figure",
    x: ArrayLike,
    lower: ArrayLike,
    upper: ArrayLike,
    *,
    name: Optional[str] = None,
    color: Optional[str] = None,
    opacity: float = 0.22,
    line_width: float = 0.0,
    line_opacity: float = 0.0,
    fill: Union[str, dict[str, str], None] = None,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add an uncertainty/confidence band between ``lower`` and ``upper``.

    The band is one filled strip, not one rectangle per observation. It uses
    the same M4 reduction and WebGL area path as a large area series.
    """
    css = styles.compile_mark_style("error_band", style)
    color = css.get("color", color)
    opacity = css.get("opacity", opacity)
    line_width = css.get("line_width", line_width)
    line_opacity = css.get("line_opacity", line_opacity)
    fill = css.get("fill", fill)
    name = self._optional_text(name, "error_band name")
    color = self._optional_css_color(color, "error_band color")
    if color is None:
        color = self.next_series_color()
    opacity = self._opacity(opacity, "error_band opacity")
    line_width = self._nonnegative_scalar(line_width, "error_band line_width")
    line_opacity = self._opacity(line_opacity, "error_band line_opacity")
    fill_spec = _validate.mark_fill(fill, "error_band fill")
    checkpoint = self._checkpoint()
    try:
        xc, lc = self._ingest_xy(x, lower, "error_band")
        uc = self.store.ingest(self._as_1d_float(upper, "error_band upper"))
        if len(uc) != len(xc):
            raise ValueError(f"error_band upper must have length {len(xc)}, got {len(uc)}")
        if self.coords != "polar" and not kernels.is_sorted(xc.values):
            order = kernels.argsort_stable(xc.values)
            xc = self.store.ingest(xc.values[order])
            lc = self.store.ingest(lc.values[order])
            uc = self.store.ingest(uc.values[order])
        style: dict[str, Any] = {
            "color": color,
            "opacity": opacity,
            "line_width": line_width,
            "line_opacity": line_opacity,
            "role": "error-band",
        }
        style.update(styles._opacity_channels(css))
        if fill_spec is not None:
            style["fill"] = fill_spec
        self.traces.append(
            Trace(
                id=len(self.traces),
                kind="error_band",
                x=xc,
                y=uc,
                base=lc,
                name=name,
                style=style,
            )
        )
        return self
    except Exception:
        self._rollback(checkpoint)
        raise


def errorbar(
    self: "Figure",
    x: ArrayLike,
    y: ArrayLike,
    *,
    yerr: Union[Scalar, ArrayLike, None] = None,
    xerr: Union[Scalar, ArrayLike, None] = None,
    name: Optional[str] = None,
    color: Optional[str] = None,
    width: float = 1.2,
    cap_size: Optional[float] = None,
    opacity: float = 1.0,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add vertical and/or horizontal error bars as instanced segments.

    ``yerr`` and ``xerr`` accept symmetric lengths or a ``(lower, upper)``
    pair. ``cap_size`` is expressed in the perpendicular data-axis units,
    which makes the geometry stable in both notebook and static exports.
    The default (``None``) auto-sizes caps to 0.25x the median adjacent
    spacing of the distinct positions along that axis (0.4 when fewer than
    two are distinct); ``cap_size=0`` omits the caps entirely.
    """
    css = styles.compile_mark_style("errorbar", style)
    color = css.get("color", color)
    width = css.get("width", width)
    opacity = css.get("opacity", opacity)
    if yerr is None and xerr is None:
        raise ValueError("errorbar requires yerr, xerr, or both")
    name = self._optional_text(name, "errorbar name")
    color = self._optional_css_color(color, "errorbar color")
    if color is None:
        color = self.next_series_color()
    width = self._positive_scalar(width, "errorbar width")
    if cap_size is not None:
        cap_size = self._nonnegative_scalar(cap_size, "errorbar cap_size")
    opacity = self._opacity(opacity, "errorbar opacity")
    checkpoint = self._checkpoint()
    try:
        xc, yc = self._ingest_xy(x, y, "errorbar")
        n = len(xc)
        xvals, yvals = xc.values, yc.values
        emitted = False
        if yerr is not None:
            low, high = error_extent(yerr, n, yvals, "errorbar yerr")
            cap = auto_cap_size(xvals) if cap_size is None else cap_size
            if cap > 0.0:
                x0 = np.concatenate((xvals, xvals - cap, xvals - cap))
                x1 = np.concatenate((xvals, xvals + cap, xvals + cap))
                y0 = np.concatenate((low, low, high))
                y1 = np.concatenate((high, low, high))
            else:
                # No caps: ship only the n main segments, not 2n degenerate ones.
                x0, x1, y0, y1 = xvals, xvals, low, high
            self._append_segment_trace(
                "errorbar",
                x0,
                x1,
                y0,
                y1,
                name=name,
                color=color,
                opacity=opacity,
                width=width,
                role="y-errorbar",
                count=n,
                extra_style=styles._opacity_channels(css),
            )
            emitted = True
        if xerr is not None:
            low, high = error_extent(xerr, n, xvals, "errorbar xerr")
            cap = auto_cap_size(yvals) if cap_size is None else cap_size
            if cap > 0.0:
                x0 = np.concatenate((low, low, high))
                x1 = np.concatenate((high, low, high))
                y0 = np.concatenate((yvals, yvals - cap, yvals - cap))
                y1 = np.concatenate((yvals, yvals + cap, yvals + cap))
            else:
                x0, x1, y0, y1 = low, high, yvals, yvals
            self._append_segment_trace(
                "errorbar",
                x0,
                x1,
                y0,
                y1,
                name=None if emitted else name,
                color=color,
                opacity=opacity,
                width=width,
                role="x-errorbar",
                count=n,
                extra_style=styles._opacity_channels(css),
            )
        return self
    except Exception:
        self._rollback(checkpoint)
        raise
