"""Scatter mark — per-point color/size/symbol with density fallback."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, Optional, Union

from . import channels, kernels, styles
from ._marks_style import (
    direct_style,
    direct_symbols,
    stroke_channel,
    validated_marker_path,
)
from ._trace import Trace
from ._typing import ArrayLike, Scalar
from .config import DIRECT_SOFT_CEILING

if TYPE_CHECKING:
    from ._figure import Figure


def scatter(
    self: "Figure",
    x: ArrayLike,
    y: ArrayLike,
    *,
    name: Optional[str] = None,
    color: Union[str, ArrayLike, None] = None,
    size: Union[Scalar, ArrayLike, None] = 4.0,
    opacity: Any = 0.8,
    zoom_size_factor: float = 1.0,
    zoom_opacity: Optional[float] = None,
    zoom_emphasis: float = 16.0,
    colormap: channels.ColormapLike = channels.DEFAULT_COLORMAP,
    color_domain: Optional[tuple[float, float]] = None,
    size_range: tuple[float, float] = (2.0, 18.0),
    density: Optional[bool] = None,
    pyramid_spill: Optional[bool] = None,
    symbol: Any = "circle",
    stroke: Any = None,
    stroke_width: Any = 0.0,
    _artist_alpha: Any = None,
    _marker_path: Optional[dict[str, Any]] = None,
    _marker_glyph: Optional[str] = None,
    _legend_trace_size: bool = False,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add a scatter trace.

    `color` may be a CSS color (constant), a numeric array (continuous →
    colormap), or a categorical array (factorized → palette). `size` may be
    a scalar or a numeric array (mapped to `size_range` px). `symbol` picks
    one of the 19 renderer-backed marker shapes; `stroke` / `stroke_width`
    draw a point border. Large scatters automatically switch to an aggregated
    density surface; pass `density=True/False` to force or disable it.
    `pyramid_spill=True` forces its pyramid into the bounded disk-backed tile
    store; `None` retains automatic budget policy.

    `zoom_size_factor` multiplies marker sizes and `zoom_opacity` sets their
    target opacity at `zoom_emphasis` times the initial view scale. The client
    interpolates both in logarithmic zoom space and clamps at the target.
    Defaults keep marker styling fixed at every zoom level.
    """
    css = styles.compile_mark_style("scatter", style)
    color = css.get("color", color)
    opacity = css.get("opacity", opacity)
    stroke = css.get("stroke", stroke)
    stroke_width = css.get("stroke_width", stroke_width)
    symbol = css.get("symbol", symbol)
    name = self._optional_text(name, "scatter name")
    zoom_size_factor = self._nonnegative_scalar(zoom_size_factor, "scatter zoom_size_factor")
    if zoom_size_factor == 0.0:
        raise ValueError("scatter zoom_size_factor must be > 0")
    if zoom_opacity is not None:
        zoom_opacity = self._opacity(zoom_opacity, "scatter zoom_opacity")
    zoom_emphasis = self._nonnegative_scalar(zoom_emphasis, "scatter zoom_emphasis")
    if zoom_emphasis <= 1.0:
        raise ValueError("scatter zoom_emphasis must be > 1")
    density = self._optional_bool(density, "scatter density")
    pyramid_spill = self._optional_bool(pyramid_spill, "scatter pyramid_spill")
    checkpoint = self._checkpoint()
    try:
        xc, yc = self._ingest_xy(x, y, "scatter")
        n = len(xc)
        style_channels: dict[str, channels.StyleChannel] = {}
        opacity_value = direct_style(
            opacity,
            n,
            "scatter opacity",
            style_channels,
            "opacity",
            default=0.8,
            minimum=0.0,
            maximum=1.0,
        )
        artist_alpha_value: Optional[float] = None
        if _artist_alpha is not None:
            alpha_value, alpha_ch = channels.resolve_style_channel(
                _artist_alpha, n, "scatter alpha", minimum=0.0, maximum=1.0
            )
            if alpha_ch is not None:
                style_channels["artist_alpha"] = alpha_ch
            elif alpha_value is not None:
                artist_alpha_value = float(alpha_value)
        symbol_value = direct_symbols(symbol, n, style_channels)
        stroke_value, stroke_ch = stroke_channel(stroke, n, "scatter stroke")
        stroke_width_value = direct_style(
            stroke_width,
            n,
            "scatter stroke_width",
            style_channels,
            "stroke_width",
            default=0.0,
            minimum=0.0,
        )
        if (
            (stroke_value is not None or stroke_ch is not None)
            and not stroke_width_value
            and ("stroke_width" not in style_channels)
        ):
            stroke_width_value = 1.0
        if (
            stroke_value is None
            and stroke_ch is None
            and (stroke_width_value or "stroke_width" in style_channels)
        ):
            stroke_ch = channels.ColorChannel(mode="match_fill")
        color_ch = channels.resolve_color(
            color,
            n,
            colormap=colormap,
            default_constant=self.next_series_color,
            domain=color_domain,
            palette=self.palette,
        )
        size_ch = channels.resolve_size(size, n, range_px=size_range)

        point_style: dict[str, Any] = {"opacity": opacity_value}
        if _marker_path is not None and _marker_glyph is not None:
            raise ValueError("scatter accepts only one authored marker representation")
        if _marker_path is not None:
            point_style["marker_path"] = validated_marker_path(_marker_path)
        if _marker_glyph is not None:
            if (
                not isinstance(_marker_glyph, str)
                or not _marker_glyph
                or "\0" in _marker_glyph
                or "\n" in _marker_glyph
                or "\r" in _marker_glyph
                or len(_marker_glyph.encode("utf-8")) > 64
            ):
                raise ValueError(
                    "scatter authored marker glyph must be nonempty UTF-8 of at most 64 bytes"
                )
            point_style["marker_glyph"] = _marker_glyph
        if _legend_trace_size:
            # Pyplot's scalar ``s=`` is an authored marker area, and its
            # automatic legend must keep the resulting diameter. Native xy
            # legends retain their fixed swatch semantics unless this private
            # shim flag opts the trace into size derivation.
            point_style["_legend_trace_size"] = True
        if artist_alpha_value is not None:
            point_style["artist_alpha"] = artist_alpha_value
        if zoom_size_factor != 1.0:
            point_style["zoom_size_factor"] = zoom_size_factor
        if zoom_opacity is not None:
            point_style["zoom_opacity"] = zoom_opacity
        if zoom_size_factor != 1.0 or zoom_opacity is not None:
            point_style["zoom_emphasis"] = zoom_emphasis
        point_style.update(styles._opacity_channels(css))
        if symbol_value != "circle":
            point_style["symbol"] = symbol_value
        if stroke_value is not None:
            point_style["stroke"] = stroke_value
        if stroke_width_value:
            point_style["stroke_width"] = stroke_width_value

        trace = Trace(
            id=len(self.traces),
            kind="scatter",
            x=xc,
            y=yc,
            name=name,
            style=point_style,
            color_ch=color_ch,
            stroke_ch=stroke_ch,
            size_ch=size_ch,
            style_channels=style_channels,
            force_density=density,
            pyramid_spill=pyramid_spill,
        )

        # The color channel survives aggregation as the density surface's
        # per-cell mean point color (LOD doc §2); every other per-item
        # channel is dropped at Tier 2 — allowed, never silent (§28).
        color_aggregates = channels.bins_mean_color(trace.color_ch)
        dropped_channels = tuple(
            name
            for name in trace.per_item_channel_names()
            if kernels.density_dropped_channel_wire_admit(
                channel=name,
                mean_color_aggregates=color_aggregates,
            )
        )
        mean_color_note = (
            " The color channel is kept as the surface's per-cell mean point color"
            " (composited at the points' own alpha)."
            if color_aggregates
            else ""
        )
        if density is None and dropped_channels and n > DIRECT_SOFT_CEILING:
            warnings.warn(
                f"scatter has {n:,} points with per-point styles — above the "
                f"direct ceiling ({DIRECT_SOFT_CEILING:,}). Falling back to a "
                f"density surface; dropped channels: {', '.join(dropped_channels)} "
                "(aggregating arbitrary instance styles needs the §5-F5 aggregation algebra, not yet "
                f"implemented).{mean_color_note} "
                "Pass density=False to keep direct draw at your risk.",
                RuntimeWarning,
                stacklevel=2,
            )
            trace.force_density = True
        elif density is None and n > DIRECT_SOFT_CEILING:
            warnings.warn(
                f"scatter has {n:,} points above the soft ceiling "
                f"({DIRECT_SOFT_CEILING:,}); using a density surface for the "
                f"initial render.{mean_color_note}",
                RuntimeWarning,
                stacklevel=2,
            )
        elif density is False and n > DIRECT_SOFT_CEILING:
            # §28: opting out of aggregation above the ceiling is allowed but
            # never silent — fill-rate and the ~1 GB allocation cliff are real (§5 F3).
            warnings.warn(
                f"density=False with {n:,} points forces direct draw above the "
                f"ceiling ({DIRECT_SOFT_CEILING:,}); expect fill-rate-bound frames "
                "and possible buffer-allocation failure.",
                RuntimeWarning,
                stacklevel=2,
            )

        self.traces.append(trace)
        return self
    except Exception:
        self._rollback(checkpoint)
        raise
