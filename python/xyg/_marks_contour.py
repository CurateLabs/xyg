"""Contour isolines and filled bands — marching-squares via kernels."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Union

import numpy as np

from . import channels, kernels, styles
from ._typing import ArrayLike
from .config import MAX_CONTOUR_WORK

if TYPE_CHECKING:
    from ._figure import Figure


def contour_segments(
    z: np.ndarray,
    x_coords: np.ndarray,
    y_coords: np.ndarray,
    levels: np.ndarray,
    *,
    corner_mask: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Extract flat contour segments through the native marching-squares kernel."""
    return kernels.marching_squares(z, x_coords, y_coords, levels, corner_mask=corner_mask)


def interpolate_contourf_grid(
    arr: np.ndarray,
    xpos: np.ndarray,
    ypos: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bilinearly densify a contour field before assigning discrete bands."""
    return kernels.contourf_densify(arr, xpos, ypos)


def contourf_corner_triangles(
    arr: np.ndarray,
    xpos: np.ndarray,
    ypos: np.ndarray,
    edges: np.ndarray,
    *,
    extend_min: bool,
    extend_max: bool,
) -> tuple[tuple[np.ndarray, ...], np.ndarray]:
    """Clip one-masked-corner cells into exact ContourPy-style band triangles."""
    return kernels.contourf_bands(
        arr,
        xpos,
        ypos,
        edges,
        extend_min=extend_min,
        extend_max=extend_max,
    )


def contour(
    self: "Figure",
    z: ArrayLike,
    *,
    x: Optional[ArrayLike] = None,
    y: Optional[ArrayLike] = None,
    levels: Union[int, ArrayLike] = 10,
    filled: bool = False,
    name: Optional[str] = None,
    colormap: channels.ColormapLike = channels.DEFAULT_COLORMAP,
    color: Any = None,
    width: Any = 1.1,
    opacity: float = 0.9,
    dash_negative: bool = False,
    extend: str = "neither",
    corner_mask: bool = False,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add regular-grid contour isolines, optionally over a filled heatmap.

    `dash_negative` renders negative-level isolines dashed for a single-color
    contour (Matplotlib's monochrome convention); it is ignored when a colormap
    drives per-level color.
    """
    css = styles.compile_mark_style("contour", style)
    color = css.get("color", color)
    width = css.get("width", width)
    opacity = css.get("opacity", opacity)
    arr = self._as_float_array(z, "contour z")
    if arr.ndim != 2 or min(arr.shape) < 2:
        raise ValueError(
            f"contour z must be a 2-D matrix with at least 2 rows/columns, got {arr.shape}"
        )
    rows, cols = arr.shape
    xpos = self._heatmap_axis_positions(x, cols, "x")
    ypos = self._heatmap_axis_positions(y, rows, "y")
    finite = arr[np.isfinite(arr)]
    if len(finite) == 0:
        raise ValueError("contour z must contain at least one finite value")
    if isinstance(levels, (int, np.integer)) and not isinstance(levels, (bool, np.bool_)):
        n_levels = int(levels)
        if n_levels <= 0 or n_levels > 256:
            raise ValueError("contour levels must be between 1 and 256")
        try:
            level_values = kernels.contour_levels(finite, n_levels)
        except ValueError as exc:
            raise ValueError("contour z must contain at least one finite value") from exc
    else:
        authored = self._as_1d_float(levels, "contour levels")
        try:
            level_values = kernels.contour_levels(authored, 0)
        except ValueError as exc:
            raise ValueError("contour levels must contain 1 to 256 finite values") from exc
    work = (rows - 1) * (cols - 1) * len(level_values)
    if work > MAX_CONTOUR_WORK:
        raise ValueError(
            f"contour grid x levels exceeds the bounded work budget ({MAX_CONTOUR_WORK:,})"
        )
    colormap = channels.resolve_colormap(colormap)
    name = self._optional_text(name, "contour name")
    if extend not in ("neither", "min", "max", "both"):
        raise ValueError("contour extend must be 'neither', 'min', 'max', or 'both'")
    extend_min = filled and extend in ("min", "both")
    extend_max = filled and extend in ("max", "both")
    color_table: Optional[np.ndarray]
    if color is None or isinstance(color, str):
        color = self._optional_css_color(color, "contour color")
        color_table = None
    else:
        expected = (
            len(level_values) - 1 + int(extend_min) + int(extend_max)
            if filled
            else len(level_values)
        )
        color_channel = channels.resolve_color(
            color,
            expected,
            colormap=colormap,
            default_constant=self.palette_color(len(self.traces)),
            palette=self.palette,
        )
        if color_channel.mode != "direct_rgba" or color_channel.rgba is None:
            raise ValueError("contour color arrays must contain direct RGB/RGBA rows")
        color_table = color_channel.rgba
        color = None
    width_array = np.asarray(width)
    if width_array.ndim == 0:
        # Unwrap before scalar validation so a 0-D boolean array remains a
        # boolean (and is rejected) instead of coercing silently to 0.0/1.0.
        width = self._positive_scalar(width_array.item(), "contour width")
        width_values = None
    else:
        width_values = self._as_1d_float(width, "contour width")
        if (
            not len(width_values)
            or not np.isfinite(width_values).all()
            or np.any(width_values <= 0)
        ):
            raise ValueError("contour width must contain positive finite values")
        width = float(width_values[0])
    opacity = self._opacity(opacity, "contour opacity")
    if not isinstance(corner_mask, (bool, np.bool_)):
        raise TypeError("contour corner_mask must be boolean")
    # Checkpoint spans the optional filled heatmap too: a level set that never
    # intersects the grid must not leave a stray heatmap trace behind.
    checkpoint = self._checkpoint()
    try:
        if filled:
            # Matplotlib's contourf paints piecewise-constant bands *between*
            # consecutive levels, not a smooth ramp. Interpolate the scalar
            # field before snapping samples to band midpoints so boundaries
            # cross between source points instead of following square cells.
            # Values outside the level range stay unpainted (extend='neither').
            edges = np.asarray(level_values, dtype=np.float64)
            if len(edges) >= 2 and edges[0] < edges[-1]:
                dense, dense_x, dense_y = interpolate_contourf_grid(arr, xpos, ypos)
                band = np.searchsorted(edges, dense, side="right") - 1
                # Matplotlib includes the final level in the final filled
                # interval; only values strictly above it are outside.
                band[np.isfinite(dense) & (dense == edges[-1])] = len(edges) - 2
                mids = (edges[:-1] + edges[1:]) * 0.5
                inside = np.isfinite(dense) & (band >= 0) & (band < len(edges) - 1)
                finite_dense = np.isfinite(dense)
                if color_table is None:
                    banded = np.full(dense.shape, np.nan, dtype=np.float64)
                    banded[inside] = mids[np.clip(band, 0, len(edges) - 2)][inside]
                    if extend_min:
                        banded[finite_dense & (dense < edges[0])] = edges[0]
                    if extend_max:
                        banded[finite_dense & (dense > edges[-1])] = edges[-1]
                    self.heatmap(
                        banded,
                        x=dense_x,
                        y=dense_y,
                        name=name,
                        colormap=colormap,
                        domain=(float(edges[0]), float(edges[-1])),
                        opacity=min(opacity, 0.9),
                    )
                else:
                    # Listed contour colors are discrete paint, not a request
                    # for the named colormap.  Carry exact RGBA through the
                    # truecolor heatmap path so every renderer sees the same
                    # per-band cycle.
                    rgba = np.zeros(dense.shape + (4,), dtype=np.float64)
                    offset = int(extend_min)
                    rgba[inside] = color_table[offset + band[inside]]
                    if extend_min:
                        rgba[finite_dense & (dense < edges[0])] = color_table[0]
                    if extend_max:
                        rgba[finite_dense & (dense > edges[-1])] = color_table[-1]
                    self.heatmap(
                        rgba,
                        x=dense_x,
                        y=dense_y,
                        name=name,
                        opacity=opacity,
                    )
                if corner_mask:
                    triangle_columns, triangle_slots = contourf_corner_triangles(
                        arr,
                        xpos,
                        ypos,
                        edges,
                        extend_min=extend_min,
                        extend_max=extend_max,
                    )
                    if len(triangle_slots):
                        if color_table is None:
                            paints = np.concatenate(
                                (
                                    [edges[0]] if extend_min else [],
                                    mids,
                                    [edges[-1]] if extend_max else [],
                                )
                            )
                            triangle_colors: Any = paints[triangle_slots]
                            triangle_domain = (float(edges[0]), float(edges[-1]))
                        else:
                            triangle_colors = color_table[triangle_slots]
                            triangle_domain = None
                        self.triangle_mesh(
                            *triangle_columns,
                            color=triangle_colors,
                            colormap=colormap,
                            domain=triangle_domain,
                            opacity=min(opacity, 0.9) if color_table is None else opacity,
                            _joined_fill=True,
                        )
            else:
                self.heatmap(
                    arr,
                    x=x,
                    y=y,
                    name=name,
                    colormap=colormap,
                    opacity=min(opacity, 0.7),
                )
        contour_level_values = level_values
        x0, x1, y0, y1, segment_levels = contour_segments(
            arr,
            xpos,
            ypos,
            contour_level_values,
            corner_mask=bool(corner_mask),
        )
        if len(x0) == 0:
            raise ValueError("contour levels do not intersect the finite grid")
        domain = self._auto_domain((float(np.min(segment_levels)), float(np.max(segment_levels))))
        if color_table is not None and not filled:
            level_indices = np.searchsorted(contour_level_values, segment_levels)
            level_indices = np.clip(level_indices, 0, len(contour_level_values) - 1)
            color_ch = channels.ColorChannel(
                mode="direct_rgba",
                rgba=np.ascontiguousarray(color_table[level_indices]),
            )
        else:
            color_ch = (
                channels.ColorChannel(
                    mode="continuous", values=segment_levels, domain=domain, colormap=colormap
                )
                if color is None and color_table is None
                else None
            )
        # contourf paints bands without outlining their boundaries. Users can
        # explicitly overlay contour() when isolines are desired.
        if not filled:
            # Matplotlib dashes negative isolines for a single-color contour. Split
            # the segment set by level sign so the negative group ships dashed; a
            # colormapped contour keeps every level solid.
            lv = np.asarray(segment_levels)
            if width_values is not None:
                level_indices = np.searchsorted(contour_level_values, lv)
                level_indices = np.clip(level_indices, 0, len(contour_level_values) - 1)
                segment_widths = width_values[level_indices % len(width_values)]
            else:
                segment_widths = width
            if dash_negative and color is not None and np.any(lv < 0):
                # Matplotlib's dashed preset is scaled by the contour linewidth:
                # 3.7 on / 1.6 off times the rendered width.
                if width_values is None:
                    groups = []
                    if np.any(lv >= 0):
                        groups.append((lv >= 0, None))
                    groups.append((lv < 0, [3.7 * width, 1.6 * width]))
                else:
                    # Dash lengths are part of the trace style, so levels with
                    # different authored widths need independent negative
                    # groups. This also keeps tuple/list linewidths faithful
                    # instead of shrinking every dash to 3.7/1.6 pixels.
                    groups = []
                    if np.any(lv >= 0):
                        groups.append((lv >= 0, None))
                    for level_index, level in enumerate(contour_level_values):
                        if level >= 0:
                            continue
                        level_mask = np.isclose(lv, level, rtol=0.0, atol=0.0)
                        rendered_width = float(width_values[level_index % len(width_values)])
                        groups.append(
                            (
                                level_mask,
                                [3.7 * rendered_width, 1.6 * rendered_width],
                            )
                        )
            else:
                groups = ((np.ones(len(lv), dtype=bool), None),)
            for mask, dash in groups:
                self._append_segment_trace(
                    "contour",
                    x0[mask],
                    x1[mask],
                    y0[mask],
                    y1[mask],
                    name=name if dash is None else None,
                    color=color,
                    opacity=opacity,
                    width=(
                        np.asarray(segment_widths, dtype=np.float64)[mask]
                        if isinstance(segment_widths, np.ndarray)
                        else segment_widths
                    ),
                    role="contour",
                    color_ch=color_ch,
                    dash=dash,
                    extra_style=styles._opacity_channels(css),
                )
    except Exception:
        self._rollback(checkpoint)
        raise
    return self
