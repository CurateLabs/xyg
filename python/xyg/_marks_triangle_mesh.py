"""Triangle mesh mark — instanced filled triangles with optional stroke."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Union

from . import channels, styles
from ._marks_style import direct_style as _direct_style
from ._marks_style import stroke_channel as _stroke_channel
from ._trace import Trace
from ._typing import ArrayLike

if TYPE_CHECKING:
    from ._figure import Figure


def triangle_mesh(
    self: "Figure",
    x0: ArrayLike,
    y0: ArrayLike,
    x1: ArrayLike,
    y1: ArrayLike,
    x2: ArrayLike,
    y2: ArrayLike,
    *,
    color: Union[str, ArrayLike, None] = None,
    colormap: channels.ColormapLike = channels.DEFAULT_COLORMAP,
    domain: Optional[tuple[float, float]] = None,
    name: Optional[str] = None,
    opacity: Any = 1.0,
    stroke: Any = None,
    stroke_width: Any = 0.0,
    _joined_fill: bool = False,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add independently colored filled triangles as one instanced mesh."""
    css = styles.compile_mark_style("triangle_mesh", style)
    color = css.get("color", color)
    opacity = css.get("opacity", opacity)
    stroke = css.get("stroke", stroke)
    stroke_width = css.get("stroke_width", stroke_width)
    name = self._optional_text(name, "triangle_mesh name")
    arrays = [
        self._as_1d_float(values, f"triangle_mesh {label}")
        for label, values in (
            ("x0", x0),
            ("y0", y0),
            ("x1", x1),
            ("y1", y1),
            ("x2", x2),
            ("y2", y2),
        )
    ]
    if len({len(values) for values in arrays}) != 1:
        raise ValueError("triangle_mesh coordinate columns must have equal length")
    n = len(arrays[0])
    style_channels: dict[str, channels.StyleChannel] = {}
    opacity_value = _direct_style(
        opacity,
        n,
        "triangle_mesh opacity",
        style_channels,
        "opacity",
        default=1.0,
        minimum=0.0,
        maximum=1.0,
    )
    stroke_value, stroke_ch = _stroke_channel(stroke, n, "triangle_mesh stroke")
    stroke_width_value = _direct_style(
        stroke_width,
        n,
        "triangle_mesh stroke_width",
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
    color_ch = channels.resolve_color(
        color,
        n,
        colormap=colormap,
        default_constant=self.next_series_color,
        palette=self.palette,
    )
    if domain is not None:
        if color_ch.mode != "continuous":
            raise ValueError("triangle_mesh domain requires a continuous numeric color array")
        color_ch.domain = self._finite_increasing_pair(domain, "triangle_mesh domain")
    # A width without an explicit stroke means "outline in the face color".
    # Constant paints already get that fallback from the renderer; direct and
    # semantic color channels need the explicit buffer-free match mode.
    if (
        stroke_value is None
        and stroke_ch is None
        and color_ch.mode != "constant"
        and (stroke_width_value or "stroke_width" in style_channels)
    ):
        stroke_ch = channels.ColorChannel(mode="match_fill")
    checkpoint = self._checkpoint()
    try:
        x0c, y0c, x1c, y1c, x2c, y2c = [self.store.ingest(values) for values in arrays]
        style: dict[str, Any] = {"opacity": opacity_value, "role": "triangle-mesh"}
        if _joined_fill:
            style["joined_fill"] = True
        style.update(styles._opacity_channels(css))
        if stroke_value is not None:
            style["stroke"] = stroke_value
        if stroke_width_value:
            style["stroke_width"] = stroke_width_value
        self.traces.append(
            Trace(
                id=len(self.traces),
                kind="triangle_mesh",
                x=x2c,
                y=y2c,
                x0=x0c,
                x1=x1c,
                y0=y0c,
                y1=y1c,
                name=name,
                style=style,
                color_ch=color_ch,
                stroke_ch=stroke_ch,
                style_channels=style_channels,
                count=n,
            )
        )
        return self
    except Exception:
        self._rollback(checkpoint)
        raise
