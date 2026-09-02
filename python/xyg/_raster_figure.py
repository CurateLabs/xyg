"""Figure-level raster export entry points."""

from __future__ import annotations

from os import PathLike
from typing import Any, Optional

import numpy as np

from . import _png
from ._export_chrome import apply_export_background
from ._raster_render import render_raster


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
