"""Segments mark — independent line segments through the instanced renderer."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Optional, Union

from . import _validate, channels, styles
from ._typing import ArrayLike

if TYPE_CHECKING:
    from ._figure import Figure


def segments(
    self: "Figure",
    x0: ArrayLike,
    y0: ArrayLike,
    x1: ArrayLike,
    y1: ArrayLike,
    *,
    name: Optional[str] = None,
    color: Union[str, ArrayLike, None] = None,
    colormap: channels.ColormapLike = channels.DEFAULT_COLORMAP,
    domain: Optional[tuple[float, float]] = None,
    width: Any = 1.2,
    opacity: Any = 1.0,
    dash: Union[str, Sequence[float], None] = None,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add independent line segments through the shared instanced renderer."""
    css = styles.compile_mark_style("segments", style)
    color = css.get("color", color)
    width = css.get("width", width)
    opacity = css.get("opacity", opacity)
    dash = css.get("dash", dash)
    arrays = [self._as_1d_float(values, "segments color geometry") for values in (x0, y0, x1, y1)]
    if len({len(values) for values in arrays}) != 1:
        raise ValueError("segments coordinate columns must have equal length")
    color_ch = channels.resolve_color(
        color,
        len(arrays[0]),
        colormap=colormap,
        default_constant=self.next_series_color,
        palette=self.palette,
    )
    if domain is not None:
        if color_ch.mode != "continuous":
            raise ValueError("segments domain requires a continuous numeric color array")
        color_ch.domain = self._finite_increasing_pair(domain, "segments domain")
    constant = color_ch.constant if color_ch.mode == "constant" else None
    dash_spec = _validate.dash(dash, "segments dash")
    self._append_segment_trace(
        "segments",
        arrays[0],
        arrays[2],
        arrays[1],
        arrays[3],
        name=name,
        color=constant,
        opacity=opacity,
        width=width,
        role="segments",
        dash=dash_spec,
        color_ch=None if color_ch.mode == "constant" else color_ch,
        extra_style=styles._opacity_channels(css),
    )
    return self
