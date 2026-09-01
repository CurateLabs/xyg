"""Native PNG export: build a display-list command buffer from a chart spec and
paint it with the Rust rasterizer (`kernels.rasterize`, `crates/xyg-engine/src/raster.rs`), then
encode PNG. Browser-free and screen-bounded — the same decimated payload the SVG
exporter consumes.

Reuses `_svg`'s layout/scale/tick/colormap math and ABI 121 tessellation
kernels so the raster matches the SVG (and the live chart). Shared CSS and
trace paint resolution live in `_paint.py`. Compatibility `_scene.py`
wrappers stay for tests; this emitter calls `kernels` directly (#310).
"""

from __future__ import annotations  # noqa: F401

from os import PathLike  # noqa: F401
from typing import Any, Optional  # noqa: F401

from . import _png, _textblock  # noqa: F401
from ._export_axis_grid_raster import _raster_axis_grid  # noqa: F401
from ._export_baseline_raster import _raster_baselines  # noqa: F401
from ._export_chrome import (  # noqa: F401
    _AXIS,
    _GRID,
    _TEXT,
    apply_export_background,
)
from ._export_chrome import resolve_static_css_vars as _resolve_static_css_vars  # noqa: F401
from ._export_chrome_raster import _raster_chrome  # noqa: F401
from ._export_layout import (  # noqa: F401
    _decode_title_geometry,
    layout,  # noqa: F401
)
from ._export_legend_raster import _emit_colorbar, _emit_legend  # noqa: F401
from ._export_marks_raster import (  # noqa: F401
    _emit_annotations,  # noqa: F401
    _emit_grid,  # noqa: F401
    _emit_text_box,  # noqa: F401
    _raster_trace_marks,
)
from ._export_raster_cmd import (  # noqa: F401
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
from ._export_ticks import (  # noqa: F401
    _preserve_scene_chrome_for_axis_visibility,
    axis_ticks,
    minor_axis_ticks,
)
from ._layout import (  # noqa: F401
    _axis_scales,
    _PolarProjection,
)
from ._paint import (  # noqa: F401
    _css,
)
from ._paint import (  # noqa: F401
    paint_rgba8 as _parse_color,  # noqa: F401
)
from ._paint import (  # noqa: F401
    solid_rgba8 as _solid_color,
)
from ._raster_figure import _export_payload, to_png, to_rgba  # noqa: F401
from ._raster_render import render_raster  # noqa: F401
from .config import DEFAULT_PALETTE  # noqa: F401
