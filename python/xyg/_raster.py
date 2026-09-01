"""Native PNG export: build a display-list command buffer from a chart spec and
paint it with the Rust rasterizer (`kernels.rasterize`, `crates/xyg-engine/src/raster.rs`), then
encode PNG. Browser-free and screen-bounded — the same decimated payload the SVG
exporter consumes.

Reuses `_svg`'s layout/scale/tick/colormap math and ABI 121 tessellation
kernels so the raster matches the SVG (and the live chart). Shared CSS and
trace paint resolution live in `_paint.py`. Compatibility `_scene.py`
wrappers stay for tests; this emitter calls `kernels` directly (#310).
"""

from __future__ import annotations

from os import PathLike
from typing import Any, Optional

import numpy as np

from . import _png, _textblock
from ._export_axis_grid_raster import _raster_axis_grid
from ._export_baseline_raster import _raster_baselines
from ._export_chrome import (
    _AXIS,
    _GRID,
    _TEXT,
    apply_export_background,
)
from ._export_chrome import resolve_static_css_vars as _resolve_static_css_vars
from ._export_chrome_raster import _raster_chrome
from ._export_layout import (
    _decode_title_geometry,
    layout,  # noqa: F401
)
from ._export_legend_raster import _emit_colorbar, _emit_legend  # noqa: F401
from ._export_marks_raster import (
    _emit_annotations,  # noqa: F401
    _emit_grid,  # noqa: F401
    _emit_text_box,  # noqa: F401
    _raster_trace_marks,
)
from ._export_raster_cmd import (
    _FILL,  # noqa: F401
    _STROKE,  # noqa: F401
    _STYLED_TEXT,  # noqa: F401
    _SYMBOLS,  # noqa: F401
    _TEXT_BOLD,  # noqa: F401
    _TEXT_OP,  # noqa: F401
    _TEXT_ROT_CCW,  # noqa: F401
    _TEXT_ROT_CW,  # noqa: F401
    _Cmd,
    _rect_pts,
)
from ._export_ticks import (
    _preserve_scene_chrome_for_axis_visibility,
    axis_ticks,
    minor_axis_ticks,
)
from ._layout import (
    _axis_scales,
    _PolarProjection,
)
from ._paint import (
    _css,
)
from ._paint import (
    paint_rgba8 as _parse_color,  # noqa: F401
)
from ._paint import (
    solid_rgba8 as _solid_color,
)
from .config import DEFAULT_PALETTE


@_textblock.cached_measurements
def render_raster(
    spec: dict[str, Any],
    blob: bytes,
    scale: float = 2.0,
    *,
    fast_png: bool = False,
    borrowed: tuple[np.ndarray, ...] = (),
) -> np.ndarray | bytes:
    """Paint `spec` into an ``(h, w, 4)`` RGBA8 image via the native rasterizer."""
    spec = _decode_title_geometry(spec, blob)
    spec = _resolve_static_css_vars(spec)
    spec = _preserve_scene_chrome_for_axis_visibility(spec)
    width, height, compact, plot = layout(spec)
    xa, ya = spec["x_axis"], spec["y_axis"]
    x_scales, y_scales, sx, sy, extra_x_axes, extra_y_axes = _axis_scales(spec, plot)
    # Polar reinterprets the same two axes: x carries theta, y carries r. The
    # projection comes from _svg so the vector and raster exports cannot drift.
    polar = (
        _PolarProjection(spec["x_axis"], spec["y_axis"], plot)
        if spec.get("coords") == "polar"
        else None
    )
    cols = spec["columns"]
    cmd = _Cmd(scale)

    dom_style = (spec.get("dom") or {}).get("style") or {}

    # Figure patch (mpl figure.facecolor): `theme(background=)` lands on the
    # root element's CSS background, painted over the whole canvas so the
    # margins match the browser. Gradients stay browser-only (skipped).
    figure_background = _solid_color(dom_style.get("background"))

    # The fused PNG path initializes its native canvas white, avoiding a second
    # full-frame memory pass. Raw RGBA callers still receive an explicit fill —
    # skipped when an opaque figure background would fully cover it anyway
    # (a translucent one keeps the white underlay to composite over, matching
    # the browser's white host page).
    if not fast_png and (figure_background is None or figure_background[3] < 255):
        cmd.fill(
            _rect_pts(0, 0, width, height),
            _parse_color(spec.get("canvas_background", "#ffffff")),
        )
    if figure_background is not None:
        cmd.fill(_rect_pts(0, 0, width, height), figure_background)

    # Static exports honor the same axes background token as HTML/SVG.  This
    # is deliberately a plot-rect fill rather than a canvas fill: the latter
    # is the Figure patch, composed above (or by pyplot's grid exporter). An
    # unset token keeps the plot rect transparent when a figure background is
    # present — matching the browser, where the root shows through — and
    # falls back to the classic white fill otherwise.
    plot_css = _css(dom_style.get("--chart-bg"), "")
    if plot_css:
        plot_background = _parse_color(plot_css)
    elif figure_background is None:
        plot_background = _parse_color("#ffffff")
    else:
        plot_background = None
    if plot_background is not None:
        cmd.fill(
            _rect_pts(plot["x"], plot["y"], plot["x"] + plot["w"], plot["y"] + plot["h"]),
            plot_background,
        )

    xt, xlab, xstep = axis_ticks(xa, plot["w"], True)
    yt, ylab, ystep = axis_ticks(ya, plot["h"], False)
    xmt, ymt = minor_axis_ticks(xa), minor_axis_ticks(ya)
    extra_x_ticks = {
        axis_id: axis_ticks(axis, plot["w"], True) for axis_id, axis, _axis_scale in extra_x_axes
    }
    extra_y_ticks = {
        axis_id: axis_ticks(axis, plot["h"], False) for axis_id, axis, _axis_scale in extra_y_axes
    }
    xstyle, ystyle = xa.get("style") or {}, ya.get("style") or {}
    xmstyle, ymstyle = xa.get("minor_style") or {}, ya.get("minor_style") or {}
    default_grid = _css(dom_style.get("--chart-grid"), _GRID)
    default_axis = _css(dom_style.get("--chart-axis"), _AXIS)
    default_text = _css(dom_style.get("--chart-text"), _TEXT)
    px0, py0 = plot["x"], plot["y"]
    px1, py1 = plot["x"] + plot["w"], plot["y"] + plot["h"]

    hide_x = xa.get("tick_label_strategy") == "none"
    hide_y = ya.get("tick_label_strategy") == "none"

    cmd.clip(px0, py0, plot["w"], plot["h"])
    _raster_axis_grid(
        cmd,
        polar,
        sx,
        sy,
        xt=xt,
        yt=yt,
        xmt=xmt,
        ymt=ymt,
        xstyle=xstyle,
        ystyle=ystyle,
        xmstyle=xmstyle,
        ymstyle=ymstyle,
        default_grid=default_grid,
        hide_x=hide_x,
        hide_y=hide_y,
        px0=px0,
        py0=py0,
        px1=px1,
        py1=py1,
    )

    # Grid/frame chrome is drawn before the shaped clip. Marks then share one
    # analytic annular-sector clip in the native painter, matching SVG's
    # polar clipPath without flattening every mark at the boundary.
    if polar is not None:
        cmd.polar_clip(polar)

    _raster_trace_marks(
        cmd,
        spec,
        blob,
        cols,
        plot,
        sx,
        sy,
        x_scales,
        y_scales,
        polar,
        borrowed=borrowed,
    )

    _emit_annotations(cmd, spec.get("annotations") or [], sx, sy, plot, width, height, polar=polar)

    # Chrome (unclipped): baselines, labels, title, legend.
    cmd.clip(0, 0, width, height)
    # Text annotations are unclipped like matplotlib Text (clip_on=False):
    # margin titles and edge labels may live outside the plot rectangle.
    _emit_annotations(
        cmd,
        spec.get("annotations") or [],
        sx,
        sy,
        plot,
        width,
        height,
        phase="text",
        polar=polar,
    )
    _raster_baselines(
        cmd,
        spec,
        xa,
        ya,
        sx,
        sy,
        extra_x_axes,
        extra_y_axes,
        polar,
        px0=px0,
        py0=py0,
        px1=px1,
        py1=py1,
        xt=xt,
        yt=yt,
        xmt=xmt,
        ymt=ymt,
        extra_x_ticks=extra_x_ticks,
        extra_y_ticks=extra_y_ticks,
        hide_x=hide_x,
        hide_y=hide_y,
        default_axis=default_axis,
        xstyle=xstyle,
        ystyle=ystyle,
        xmstyle=xmstyle,
        ymstyle=ymstyle,
    )

    _raster_chrome(
        cmd,
        spec,
        plot,
        width,
        height,
        xa,
        ya,
        sx,
        sy,
        extra_x_axes,
        extra_y_axes,
        polar,
        compact=compact,
        px0=px0,
        py0=py0,
        px1=px1,
        py1=py1,
        xlab=xlab,
        ylab=ylab,
        xstep=xstep,
        ystep=ystep,
        extra_x_ticks=extra_x_ticks,
        extra_y_ticks=extra_y_ticks,
        hide_x=hide_x,
        hide_y=hide_y,
        default_text=default_text,
        spec_palette=spec.get("palette") or DEFAULT_PALETTE,
    )

    w_px, h_px = max(1, round(width * scale)), max(1, round(height * scale))
    from . import _native

    spans = (blob, *borrowed)
    # The command buffer ships as a borrowed buffer, not a `bytes` copy: the
    # ctypes seam wraps it with `np.frombuffer` and the native rasterizer only
    # reads it, so freezing it would duplicate a display list that is O(marks)
    # (megabytes on a direct-tier scatter) for nothing.
    if fast_png:
        return _native.rasterize_png_spans(cmd.buf, spans, w_px, h_px)
    return _native.rasterize_spans(cmd.buf, spans, w_px, h_px)


def _export_payload(
    fig: Any,
    width: Optional[int],
    height: Optional[int],
    background: Optional[str],
) -> tuple[dict[str, Any], bytes, tuple[np.ndarray, ...]]:
    """Build the raster payload with export-time size/background overrides."""
    eff_w = (
        int(width)
        if width is not None
        else (fig.width if isinstance(fig.width, (int, float)) else 900)
    )
    spec, blob, borrowed = fig._build_raster_payload(px_width=max(256, int(eff_w)))
    if width is not None:
        spec["width"] = int(width)
    if height is not None:
        spec["height"] = int(height)
    apply_export_background(spec, background)
    return spec, blob, borrowed


def to_rgba(
    fig: Any,
    *,
    width: Optional[int] = None,
    height: Optional[int] = None,
    scale: float = 2.0,
    background: Optional[str] = None,
) -> np.ndarray:
    """Render `fig` to an ``(h, w, 4)`` RGBA8 array (no encode).

    The shared pixel source for every native raster format: PNG keeps its
    fused Rust encode path in `to_png`, while JPEG/WebP export encodes this
    array. `background` overrides the figure canvas color ("transparent"
    yields alpha-0 pixels outside the plot rect)."""
    spec, blob, borrowed = _export_payload(fig, width, height, background)
    rendered = render_raster(spec, blob, float(scale), borrowed=borrowed)
    assert isinstance(rendered, np.ndarray)  # fast_png=False never returns bytes
    return rendered


def to_png(
    fig: Any,
    path: Optional[str | PathLike[str]] = None,
    *,
    width: Optional[int] = None,
    height: Optional[int] = None,
    scale: float = 2.0,
    fast: bool = False,
    background: Optional[str] = None,
) -> bytes:
    """Render `fig` to PNG bytes with the native rasterizer (no browser)."""
    # The fused Rust PNG path initializes an opaque white canvas, so any
    # non-default background must take the raw-RGBA encode branch.
    fast = fast and background is None
    spec, blob, borrowed = _export_payload(fig, width, height, background)
    rendered = render_raster(spec, blob, float(scale), fast_png=fast, borrowed=borrowed)
    data = rendered if isinstance(rendered, bytes) else _png.encode(rendered)
    if path is not None:
        with open(path, "wb") as f:
            f.write(data)
    return data
