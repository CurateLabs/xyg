"""Heatmap mark — 2-D scalar or RGB(A) grid with optional categorical axes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from . import channels, styles
from ._trace import Trace

if TYPE_CHECKING:
    from ._figure import Figure


def heatmap(
    self: "Figure",
    z: Any,  # 2-D (rows, cols) or RGB(A) ArrayLike, or a DataFrame-like with .to_numpy()
    *,
    x: Optional[Any] = None,
    y: Optional[Any] = None,
    name: Optional[str] = None,
    color: Any = None,
    colormap: channels.ColormapLike = channels.DEFAULT_COLORMAP,
    domain: Optional[tuple[float, float]] = None,
    opacity: float = 0.95,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add a rectangular heatmap from a 2D value matrix.

    `z` is shaped `(rows, columns)`. Optional `x` and `y` arrays name the
    column/row centers; string/object arrays become categorical axes.
    A literal ``color`` keeps constant paint so regular Cartesian lattices
    can compile onto Scene Rects; omitted ``color`` keeps the metric
    colormap on the compatibility exporters.
    """
    css = styles.compile_mark_style("heatmap", style)
    opacity = css.get("opacity", opacity)
    name = self._optional_text(name, "heatmap name")
    opacity = self._opacity(opacity, "heatmap opacity")
    constant_color = color if isinstance(color, str) else None
    if hasattr(z, "to_numpy"):
        z = z.to_numpy()
    arr = np.asarray(z)
    truecolor = arr.ndim == 3 and arr.shape[-1] in (3, 4)
    if not truecolor and arr.ndim != 2:
        raise ValueError(f"heatmap z must be 2-D or RGB(A), got shape {arr.shape}")
    if truecolor:
        rgba = np.asarray(arr, dtype=np.float64)
        if np.nanmax(rgba[..., :3]) > 1.0:
            rgba[..., :3] /= 255.0
        if rgba.shape[-1] == 3:
            rgba = np.dstack((rgba, np.ones(rgba.shape[:2], dtype=np.float64)))
        rgba = np.clip(rgba, 0.0, 1.0)
        rows, cols = rgba.shape[:2]
        zv = rgba[..., 0]
    else:
        zv = self._real_float_array(arr, "heatmap z")
        rows, cols = zv.shape
    xpos = self._heatmap_axis_positions(x, cols, "x")
    ypos = self._heatmap_axis_positions(y, rows, "y")
    x_edges = self._cell_edges(xpos, "heatmap x")
    y_edges = self._cell_edges(ypos, "heatmap y")
    z_flat = zv.reshape(-1)
    if not truecolor:
        colormap = channels.resolve_colormap(colormap)
    explicit_domain = (
        None
        if truecolor or domain is None
        else self._finite_increasing_pair(domain, "heatmap domain")
    )
    checkpoint = self._checkpoint()
    try:
        self._commit_axis_positions(x, "x")
        self._commit_axis_positions(y, "y")
        grid = (
            self.store.ingest(z_flat)
            if explicit_domain is None
            else self.store.ingest(z_flat, defer_zone_maps=True)
        )
        if truecolor:
            lo, hi = 0.0, 1.0
        elif explicit_domain is None:
            bounds = (grid.min, grid.max)
            lo, hi = self._auto_domain(bounds if np.isfinite(bounds).all() else None)
        else:
            lo, hi = explicit_domain
        self.traces.append(
            Trace(
                id=len(self.traces),
                kind="heatmap",
                x=self.store.ingest(np.array([x_edges[0], x_edges[-1]], dtype=np.float64)),
                y=self.store.ingest(np.array([y_edges[0], y_edges[-1]], dtype=np.float64)),
                grid=grid,
                rgba_grid=(
                    (
                        # `grid` already holds this plane: `z_flat` is
                        # `rgba[..., 0].reshape(-1)`, and re-ingesting the
                        # expression built a second contiguous copy (the source
                        # is a strided view, so each reshape materializes one)
                        # that the store kept for the figure's lifetime — 8
                        # bytes per pixel of pure duplicate.
                        grid,
                        self.store.ingest(rgba[..., 1].reshape(-1)),
                        self.store.ingest(rgba[..., 2].reshape(-1)),
                        self.store.ingest(rgba[..., 3].reshape(-1)),
                    )
                    if truecolor
                    else None
                ),
                grid_shape=(rows, cols),
                count=int(z_flat.size),
                name=name,
                style={
                    "color": (
                        constant_color if constant_color is not None else self.next_series_color()
                    ),
                    "opacity": opacity,
                    "role": "heatmap",
                    "domain": [lo, hi],
                    "x_range": [float(x_edges[0]), float(x_edges[-1])],
                    "y_range": [float(y_edges[0]), float(y_edges[-1])],
                    **(
                        {}
                        if constant_color is not None and not truecolor
                        else {"colormap": colormap, "truecolor": truecolor}
                    ),
                    **styles._opacity_channels(css),
                },
            )
        )
    except Exception:
        self._rollback(checkpoint)
        raise
    return self
