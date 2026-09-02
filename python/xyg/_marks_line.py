"""Line and area marks — sorted ingest, curve/dash styling, polar sort guard."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Union

import numpy as np

from . import _validate, kernels, styles
from ._marks_style import stroke_geometry as _stroke_geometry
from ._trace import Trace
from ._typing import ArrayLike, Scalar

if TYPE_CHECKING:
    from ._figure import Figure


def line(
    self: "Figure",
    x: ArrayLike,
    y: ArrayLike,
    *,
    name: Optional[str] = None,
    color: Optional[str] = None,
    width: float = 1.5,
    opacity: float = 1.0,
    curve: str = "linear",
    dash: Union[str, tuple[float, ...], list[float], None] = None,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add a line series. Very long series are automatically downsampled for
    display without changing the drawn shape.

    ``curve="smooth"`` renders a monotone cubic; ``dash`` dashes the line.
    """
    css = styles.compile_mark_style("line", style)
    color = css.get("color", color)
    width = css.get("width", width)
    opacity = css.get("opacity", opacity)
    dash = css.get("dash", dash)
    name = self._optional_text(name, "line name")
    color = self._optional_css_color(color, "line color")
    if color is None:
        color = self.next_series_color()
    width = self._positive_scalar(width, "line width")
    opacity = self._opacity(opacity, "line opacity")
    curve = _validate.curve(curve, "line curve")
    dash_spec = _validate.dash(dash, "line dash")
    checkpoint = self._checkpoint()
    try:
        xc, yc = self._ingest_xy(x, y, "line")
        # Polar keeps the caller's sequence. Theta is the order marks are
        # JOINED in, not a domain to be scanned: sorting it redrew a path that
        # crosses the 0/turn seam (350 -> 10) or doubles back as an
        # ascending-angle fan instead of the authored track. Safe because polar
        # forces tier="direct" (config.py: "M4 decimation buckets on a
        # monotonic screen-x column, which a spiral is not"), so the sorted
        # precondition the sort exists to satisfy never applies here.
        if self.coords != "polar" and not kernels.is_sorted(xc.values):
            # LOD contract (§28): line x must be sorted; the engine sorts once
            # at ingest, and says so. The predicate is NaN-safe on purpose:
            # a NaN fails its pairs, so a NaN-carrying x cannot skip the sort
            # and violate M4's sorted precondition.
            # argsort places NaNs last, where the m4 window excludes them.
            order = kernels.argsort_stable(xc.values)
            xc = self.store.ingest(xc.values[order])
            yc = self.store.ingest(yc.values[order])
        style: dict[str, Any] = {"color": color, "width": width, "opacity": opacity}
        style.update(styles._opacity_channels(css))
        style.update(_stroke_geometry(css))
        if curve != "linear":
            style["curve"] = curve
        if dash_spec is not None:
            style["dash"] = dash_spec
        self.traces.append(
            Trace(
                id=len(self.traces),
                kind="line",
                x=xc,
                y=yc,
                name=name,
                style=style,
            )
        )
        return self
    except Exception:
        self._rollback(checkpoint)
        raise


def area(
    self: "Figure",
    x: ArrayLike,
    y: ArrayLike,
    *,
    base: Union[Scalar, ArrayLike] = 0.0,
    name: Optional[str] = None,
    color: Optional[str] = None,
    opacity: float = 0.35,
    line_color: Optional[str] = None,
    line_width: float = 1.2,
    line_opacity: float = 1.0,
    stroke_perimeter: bool = False,
    fill: Union[str, dict[str, str], None] = None,
    curve: str = "linear",
    dash: Union[str, tuple[float, ...], list[float], None] = None,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add a filled area trace between `y` and `base`.

    `base` may be a scalar or a length-N array, which covers both the common
    zero-baseline area chart and future stacked-area construction.
    `fill` accepts a CSS `linear-gradient(...)` (see spec/api/styling.md);
    `curve="smooth"` renders a monotone cubic through the points; `dash`
    dashes the outline.
    """
    css = styles.compile_mark_style("area", style)
    color = css.get("color", color)
    opacity = css.get("opacity", opacity)
    line_color = css.get("line_color", line_color)
    line_width = css.get("line_width", line_width)
    line_opacity = css.get("line_opacity", line_opacity)
    fill = css.get("fill", fill)
    dash = css.get("dash", dash)
    name = self._optional_text(name, "area name")
    color = self._optional_css_color(color, "area color")
    if color is None:
        color = self.next_series_color()
    opacity = self._opacity(opacity, "area opacity")
    line_color = self._optional_css_color(line_color, "area line_color")
    line_width = self._nonnegative_scalar(line_width, "area line_width")
    line_opacity = self._opacity(line_opacity, "area line_opacity")
    stroke_perimeter = _validate.bool_param(stroke_perimeter, "area stroke_perimeter")
    fill_spec = _validate.mark_fill(fill, "area fill")
    curve = _validate.curve(curve, "area curve")
    dash_spec = _validate.dash(dash, "area dash")
    checkpoint = self._checkpoint()
    try:
        xc, yc = self._ingest_xy(x, y, "area")
        bc = (
            self.store.ingest(np.full(len(xc), self._finite_scalar(base, "area base")))
            if np.isscalar(base)
            else self.store.ingest(base)
        )
        if len(bc) != len(xc):
            raise ValueError(f"area base must have length {len(xc)}, got {len(bc)}")
        if self.coords != "polar" and not kernels.is_sorted(xc.values):
            order = kernels.argsort_stable(xc.values)
            xc = self.store.ingest(xc.values[order])
            yc = self.store.ingest(yc.values[order])
            bc = self.store.ingest(bc.values[order])
        style: dict[str, Any] = {
            "color": color,
            "opacity": opacity,
            "line_width": line_width,
            "line_opacity": line_opacity,
            "stroke_perimeter": stroke_perimeter,
        }
        style.update(styles._opacity_channels(css))
        if line_color is not None:
            style["line_color"] = line_color
        if fill_spec is not None:
            style["fill"] = fill_spec
        if curve != "linear":
            style["curve"] = curve
        if dash_spec is not None:
            style["dash"] = dash_spec
        self.traces.append(
            Trace(
                id=len(self.traces),
                kind="area",
                x=xc,
                y=yc,
                base=bc,
                name=name,
                style=style,
            )
        )
        return self
    except Exception:
        self._rollback(checkpoint)
        raise
