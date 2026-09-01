"""Figure rectangle trace assembly — rect marks, finite-row selection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from . import _validate, kernels
from ._trace import Trace
from .channels import ColorChannel, SizeChannel

if TYPE_CHECKING:
    from ._figure import Figure


def rect_mark_style(
    self: "Figure",
    kind: str,
    corner_radius: Any,
    stroke: Optional[str],
    stroke_width: float,
    fill: Any,
    wedge_gap: float = 0.0,
) -> dict[str, Any]:
    """Validate the rect-family mark styling (rounded corners, border,
    gradient fill) into the sparse style keys the client renders.

    `corner_radius` is a px float for all four corners, or a `(tip, base)`
    pair in mark space — `(6, 0)` rounds only the value end of each bar
    (the top of a vertical bar), which stays correct for horizontal and
    negative bars. Setting `stroke` alone implies a 1px border, matching
    CSS expectations; the client defaults a widthed border with no color
    to the mark color."""
    style: dict[str, Any] = {}
    if isinstance(corner_radius, (tuple, list)):
        if len(corner_radius) != 2:
            raise ValueError(f"{kind} corner_radius pair must be (tip, base)")
        tip = self._nonnegative_scalar(corner_radius[0], f"{kind} corner_radius tip")
        base = self._nonnegative_scalar(corner_radius[1], f"{kind} corner_radius base")
        if tip or base:
            style["corner_radius"] = [tip, base]
    else:
        radius = self._nonnegative_scalar(corner_radius, f"{kind} corner_radius")
        if radius:
            style["corner_radius"] = radius
    gap = self._nonnegative_scalar(wedge_gap, f"{kind} wedge_gap")
    if gap:
        # Gap between neighbouring polar wedges, in PX — an angular pad's
        # gap is `r · dtheta` wide and so tapers to nothing at the hole.
        # Meaningless under cartesian coords, where bars have their own
        # width; recorded on the style and read only by the wedge paths.
        style["wedge_gap"] = gap
    stroke = self._optional_css_color(stroke, f"{kind} stroke")
    stroke_width = self._nonnegative_scalar(stroke_width, f"{kind} stroke_width")
    if stroke is not None and stroke_width == 0.0:
        stroke_width = 1.0
    fill_spec = _validate.mark_fill(fill, f"{kind} fill")
    if stroke is not None:
        style["stroke"] = stroke
    if stroke_width:
        style["stroke_width"] = stroke_width
    if fill_spec is not None:
        style["fill"] = fill_spec
    return style


def append_bar_rect(
    self: "Figure",
    kind: str,
    orientation: str,
    pos0: np.ndarray,
    pos1: np.ndarray,
    value0: np.ndarray,
    value1: np.ndarray,
    *,
    name: Optional[str],
    color: Optional[str],
    opacity: float,
    role: str,
    extra_style: Optional[dict[str, Any]] = None,
    color_ch: Optional[ColorChannel] = None,
    stroke_ch: Optional[ColorChannel] = None,
    style_channels: Optional[dict[str, Any]] = None,
) -> None:
    if orientation == "vertical":
        append_rect_trace(
            self,
            kind,
            pos0,
            pos1,
            value0,
            value1,
            name=name,
            color=color,
            opacity=opacity,
            role=role,
            orientation=orientation,
            extra_style=extra_style,
            color_ch=color_ch,
            stroke_ch=stroke_ch,
            style_channels=style_channels,
        )
    else:
        append_rect_trace(
            self,
            kind,
            value0,
            value1,
            pos0,
            pos1,
            name=name,
            color=color,
            opacity=opacity,
            role=role,
            orientation=orientation,
            extra_style=extra_style,
            color_ch=color_ch,
            stroke_ch=stroke_ch,
            style_channels=style_channels,
        )


def append_rect_trace(
    self: "Figure",
    kind: str,
    x0: Any,
    x1: Any,
    y0: Any,
    y1: Any,
    *,
    name: Optional[str],
    color: Optional[str],
    opacity: float,
    role: str,
    orientation: Optional[str] = None,
    color_ch: Optional[ColorChannel] = None,
    stroke_ch: Optional[ColorChannel] = None,
    size_ch: Optional[SizeChannel] = None,
    style_channels: Optional[dict[str, Any]] = None,
    count: Optional[int] = None,
    extra_style: Optional[dict[str, Any]] = None,
) -> None:
    name = self._optional_text(name, f"{kind} name")
    opacity = self._opacity(opacity, f"{kind} opacity")
    lengths = {
        rect_edge_len(x0, f"{kind} x0"),
        rect_edge_len(x1, f"{kind} x1"),
        rect_edge_len(y0, f"{kind} y0"),
        rect_edge_len(y1, f"{kind} y1"),
    }
    if len(lengths) != 1:
        raise ValueError(f"{kind} rectangle columns must have equal length")
    checkpoint = self._checkpoint()
    try:
        x0c = self.store.ingest(x0)
        x1c = self.store.ingest(x1)
        y0c = self.store.ingest(y0)
        y1c = self.store.ingest(y1)
        xc = self.store.ingest(x0c.values + (x1c.values - x0c.values) / 2.0)
        yc = self.store.ingest(y1c.values)
        style: dict[str, Any] = {"color": color, "opacity": opacity, "role": role}
        if orientation is not None:
            style["orientation"] = orientation
        if extra_style is not None:
            style.update(extra_style)
        self.traces.append(
            Trace(
                id=len(self.traces),
                kind=kind,
                x=xc,
                y=yc,
                x0=x0c,
                x1=x1c,
                y0=y0c,
                y1=y1c,
                name=name,
                style=style,
                color_ch=color_ch,
                stroke_ch=stroke_ch,
                size_ch=size_ch,
                style_channels=style_channels or {},
                count=count,
            )
        )
    except Exception:
        self._rollback(checkpoint)
        raise


def rect_edge_len(values: Any, label: str) -> int:
    if hasattr(values, "to_numpy"):
        values = values.to_numpy()
    arr = np.asarray(values)
    if arr.ndim != 1:
        raise ValueError(f"{label} must be 1-D, got shape {arr.shape}")
    return len(arr)


def rect_finite_sel(
    self: "Figure",
    t: Trace,
    x0v: np.ndarray,
    x1v: np.ndarray,
    y0v: np.ndarray,
    y1v: np.ndarray,
) -> Optional[np.ndarray]:
    """Rows that can safely become rectangle vertices, or None for all rows."""
    geometry = (t.x0, t.x1, t.y0, t.y1)
    if any(column is None for column in geometry):
        raise ValueError(f"{t.kind} trace missing rectangle columns")
    # Zone maps already prove most generated rectangles fully finite. Scan
    # only columns that can actually reject a row; the native query keeps
    # this allocation-free when all candidates remain valid.
    candidates = [
        values
        for column, values in zip(geometry, (x0v, x1v, y0v, y1v), strict=True)
        if column is not None and column.zone.null_count
    ]
    if t.color_ch and t.color_ch.mode == "continuous":
        values = t.color_ch.values
        if values is None:
            raise ValueError(f"{t.kind} continuous color channel missing values")
        candidates.append(values)
    elif t.color_ch and t.color_ch.mode == "categorical":
        codes = t.color_ch.codes
        if codes is None:
            raise ValueError(f"{t.kind} categorical color channel missing codes")
        # Resolved categorical codes are u8/u32 and therefore always
        # finite; no source-sized pass is needed for them.
    if not candidates:
        return None
    return kernels.valid_indices_f64(tuple(candidates))
