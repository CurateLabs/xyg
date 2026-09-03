"""Histogram marks — bin edges via kernels, rect trace assembly."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Union

import numpy as np

from . import channels, kernels, styles
from ._marks_bar import series_corner_radius as _series_corner_radius
from ._marks_bar import series_style_values as _series_style_values
from ._marks_style import stroke_channel as _stroke_channel
from ._typing import ArrayLike
from .config import DEFAULT_PALETTE

if TYPE_CHECKING:
    from ._figure import Figure


def histogram(
    self: "Figure",
    values: ArrayLike,
    *,
    bins: Union[int, str, ArrayLike] = "auto",
    range: Optional[tuple[float, float]] = None,
    density: bool = False,
    cumulative: bool = False,
    name: Optional[str] = None,
    color: Any = None,
    opacity: Any = 0.85,
    corner_radius: Any = 0.0,
    stroke: Any = None,
    stroke_width: Any = 0.0,
    _artist_alpha: Any = None,
    fill: Union[str, dict[str, str], None] = None,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add a 1D histogram backed by the shared rectangle primitive.

    `cumulative=True` accumulates bins left-to-right: with the default
    count mode the last bin equals the number of in-range values; combined
    with `density=True` it becomes the empirical CDF (last bin ~1.0).
    """
    css = styles.compile_mark_style("histogram", style)
    color = css.get("color", color)
    opacity = css.get("opacity", opacity)
    corner_radius = css.get("corner_radius", corner_radius)
    stroke = css.get("stroke", stroke)
    stroke_width = css.get("stroke_width", stroke_width)
    fill = css.get("fill", fill)
    name = self._optional_text(name, "histogram name")
    density = self._bool_param(density, "histogram density")
    cumulative = self._bool_param(cumulative, "histogram cumulative")
    vals = self._as_1d_float(values, "histogram values")
    if density and not np.isfinite(vals).any():
        raise ValueError("histogram density requires at least one finite value")
    hist_range = None if range is None else self._finite_increasing_pair(range, "histogram range")
    if isinstance(bins, (int, np.integer)) and not isinstance(bins, bool):
        n_bins = int(bins)
        if n_bins <= 0:
            raise ValueError("histogram bins must be positive")
        try:
            edges = kernels.histogram_mark_edges(
                vals, range=hist_range, method="uniform", n_bins=n_bins
            )
        except ValueError as exc:
            raise ValueError("histogram could not produce finite bins") from exc
    elif isinstance(bins, str) and bins.lower() in {"auto", "sturges"}:
        try:
            edges = kernels.histogram_mark_edges(vals, range=hist_range, method=bins.lower())
        except ValueError as exc:
            raise ValueError("invalid histogram_edges arguments") from exc
    else:
        finite = vals[np.isfinite(vals)]
        if len(finite) == 0 and isinstance(bins, str):
            try:
                edges = kernels.histogram_mark_edges(vals, range=hist_range, method="auto")
            except ValueError as exc:
                raise ValueError("histogram could not produce finite bins") from exc
        else:
            edges = np.asarray(bins, dtype=np.float64)
            if edges.ndim != 1 or edges.size < 2:
                raise ValueError("histogram bins must be a 1-D increasing sequence")
    try:
        counts = kernels.histogram_bins(vals, edges, density=density, cumulative=cumulative)
    except ValueError as exc:
        raise ValueError("histogram could not produce finite bins") from exc
    n_bins = len(counts)
    direct_color = (
        channels.resolve_color(color, n_bins, default_constant=DEFAULT_PALETTE[0])
        if color is not None and not isinstance(color, str)
        else None
    )
    color_value = color if direct_color is None else None
    if direct_color is None and color_value is None:
        color_value = self.next_series_color()
    stroke_value, stroke_channel = _stroke_channel(stroke, n_bins, "histogram stroke")
    opacity_value, opacity_channels = _series_style_values(
        opacity,
        1,
        n_bins,
        "histogram opacity",
        "opacity",
        default=0.85,
        minimum=0.0,
        maximum=1.0,
    )
    width_value, width_channels = _series_style_values(
        stroke_width,
        1,
        n_bins,
        "histogram stroke_width",
        "stroke_width",
        default=0.0,
        minimum=0.0,
    )
    constant_radius, radius_channels = _series_corner_radius(
        corner_radius, 1, n_bins, "histogram corner_radius"
    )
    _, alpha_channels = _series_style_values(
        _artist_alpha,
        1,
        n_bins,
        "histogram alpha",
        "artist_alpha",
        default=-1.0,
        minimum=-1.0,
        maximum=1.0,
    )
    mark_style = self._rect_mark_style(
        "histogram", constant_radius, stroke_value, width_value[0], fill
    )
    mark_style.update(styles._opacity_channels(css))
    style_channels = {
        **opacity_channels[0],
        **width_channels[0],
        **radius_channels[0],
        **alpha_channels[0],
    }
    zeros = np.zeros_like(counts, dtype=np.float64)
    self._append_rect_trace(
        "histogram",
        edges[:-1],
        edges[1:],
        zeros,
        counts,
        name=name,
        color=color_value,
        opacity=opacity_value[0],
        role="histogram",
        count=int(len(vals)),
        extra_style={"cumulative": cumulative, "density": density, **mark_style},
        color_ch=direct_color,
        stroke_ch=stroke_channel,
        style_channels=style_channels,
    )
    return self


def hist(
    self: "Figure",
    values: ArrayLike,
    *,
    bins: Union[int, str, ArrayLike] = "auto",
    range: Optional[tuple[float, float]] = None,
    density: bool = False,
    cumulative: bool = False,
    name: Optional[str] = None,
    color: Any = None,
    opacity: Any = 0.85,
    corner_radius: Any = 0.0,
    stroke: Any = None,
    stroke_width: Any = 0.0,
    _artist_alpha: Any = None,
    fill: Union[str, dict[str, str], None] = None,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Short alias for `histogram(...)`, matching common Python chart APIs."""
    return self.histogram(
        values,
        bins=bins,
        range=range,
        density=density,
        cumulative=cumulative,
        name=name,
        color=color,
        opacity=opacity,
        corner_radius=corner_radius,
        stroke=stroke,
        stroke_width=stroke_width,
        _artist_alpha=_artist_alpha,
        fill=fill,
        style=style,
    )
