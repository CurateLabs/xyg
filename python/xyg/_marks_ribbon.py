"""Ribbon mark — flow bands with two-ended colour gradients (Sankey primitive)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Union

from . import channels, styles
from ._marks_style import stroke_channel as _stroke_channel
from ._trace import Trace
from ._typing import ArrayLike

if TYPE_CHECKING:
    from ._figure import Figure


def ribbon(
    self: "Figure",
    x0: ArrayLike,
    x1: ArrayLike,
    source_lo: ArrayLike,
    source_hi: ArrayLike,
    target_lo: ArrayLike,
    target_hi: ArrayLike,
    *,
    color: Union[str, ArrayLike, None] = None,
    color_target: Union[str, ArrayLike, None] = None,
    colormap: channels.ColormapLike = channels.DEFAULT_COLORMAP,
    name: Optional[str] = None,
    opacity: Any = 1.0,
    stroke: Any = None,
    stroke_width: Any = 0.0,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add flow bands: a span at `x0` joined to a span at `x1` by a cubic.

    The primitive behind Sankey, and the reason it is a primitive rather than a
    composition: each band carries a colour at *each* end and the gradient runs
    along the flow, which no existing mark can express (see the ribbon geometry
    contract in spec/api/chart-kind-contract.md).

    `color`/`color_target` take a CSS colour, per-band colours (RGBA rows carry
    per-band alpha), or numeric values sampled through `colormap`; every
    encoding resolves to concrete per-band paint before shipping. `opacity`,
    `stroke` and `stroke_width` are per-trace scalars — per-band styling rides
    the colour channels, nowhere else.
    """
    css = styles.compile_mark_style("ribbon", style)
    color = css.get("color", color)
    opacity = css.get("opacity", opacity)
    stroke = css.get("stroke", stroke)
    stroke_width = css.get("stroke_width", stroke_width)
    name = self._optional_text(name, "ribbon name")
    arrays = [
        self._as_1d_float(values, f"ribbon {label}")
        for label, values in (
            ("x0", x0),
            ("x1", x1),
            ("source_lo", source_lo),
            ("source_hi", source_hi),
            ("target_lo", target_lo),
            ("target_hi", target_hi),
        )
    ]
    lengths = {len(values) for values in arrays}
    if len(lengths) != 1:
        raise ValueError(f"ribbon columns must be the same length; got {sorted(lengths)}")
    n = int(arrays[0].size)
    # Ribbon styles are per-trace scalars, refused as arrays rather than
    # silently flattened: the ribbon program's a_rgba2 shares its attribute
    # slot with a_style, so the standard per-instance style route cannot
    # coexist with the two-ended gradient, and a capability one renderer
    # cannot draw is absent everywhere (parity is identity). Per-band alpha
    # is not lost — RGBA rows in `color`/`color_target` carry it, and every
    # renderer interpolates all four channels along the band.
    opacity_constant, opacity_channel = channels.resolve_style_channel(
        opacity, n, "ribbon opacity", minimum=0.0, maximum=1.0
    )
    if opacity_channel is not None:
        raise ValueError(
            "ribbon opacity is per-trace; put per-band alpha in the color "
            "arrays instead (RGBA rows interpolate along each band)"
        )
    opacity_value = 1.0 if opacity_constant is None else float(opacity_constant)
    stroke_value, stroke_ch = _stroke_channel(stroke, n, "ribbon stroke")
    if stroke_ch is not None:
        raise ValueError(
            "ribbon stroke is per-trace; omit it to outline each band with "
            "its own fill color (edgecolors='face')"
        )
    width_constant, width_channel = channels.resolve_style_channel(
        stroke_width, n, "ribbon stroke_width", minimum=0.0
    )
    if width_channel is not None:
        raise ValueError("ribbon stroke_width is per-trace")
    stroke_width_value = 0.0 if width_constant is None else float(width_constant)
    # Ribbon ships resolved paints only (constant or direct RGBA): numeric
    # `color=` encodings are sampled through the shared exporter LUT here,
    # once, instead of teaching the two-ended ribbon program a cval path it
    # has no attribute slot for (ribbon geometry contract).
    color_ch = channels.resolve_direct_rgba(
        channels.resolve_color(
            color,
            n,
            colormap=colormap,
            default_constant=self.next_series_color,
            palette=self.palette,
        )
    )
    # No target colour means a flat band. Resolving one anyway would ship a
    # second buffer and turn every plain ribbon into a two-stop gradient in
    # three renderers for no visible difference.
    color2_ch = (
        None
        if color_target is None
        else channels.resolve_direct_rgba(
            channels.resolve_color(
                color_target,
                n,
                colormap=colormap,
                default_constant=self.next_series_color,
                palette=self.palette,
            )
        )
    )
    checkpoint = self._checkpoint()
    try:
        x0c, x1c, slo, shi, tlo, thi = [self.store.ingest(values) for values in arrays]
        style_dict: dict[str, Any] = {"opacity": opacity_value, "role": "ribbon"}
        style_dict.update(styles._opacity_channels(css))
        if stroke_value is not None:
            style_dict["stroke"] = stroke_value
        if stroke_width_value:
            style_dict["stroke_width"] = stroke_width_value
        self.traces.append(
            Trace(
                id=len(self.traces),
                kind="ribbon",
                # The six geometry slots are saturated: `x`/`y` carry the
                # TARGET span's y values, which is why `_range_columns` needs a
                # ribbon branch to autorange them on the y axis.
                x=tlo,
                y=thi,
                x0=x0c,
                x1=x1c,
                y0=slo,
                y1=shi,
                name=name,
                style=style_dict,
                color_ch=color_ch,
                color2_ch=color2_ch,
                count=n,
            )
        )
        return self
    except Exception:
        self._rollback(checkpoint)
        raise
