"""Shared direct-paint, alpha, and static-export geometry for exporters."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np

from . import _native, kernels
from .config import DEFAULT_PALETTE

ColumnReader = Callable[[int], np.ndarray]


def _css(c: Any, fallback: str) -> str:
    """Resolve static colors after chart-level tokens have been expanded."""
    s = str(c or "").strip()
    if not s or s.lower() == "currentcolor" or s.lower().startswith("var("):
        return fallback
    return s


def paint_rgba8(css: Any, opacity: float = 1.0) -> tuple[int, int, int, int]:
    """Resolve a CSS paint to RGBA8 via ``xyg_css_color_rgba``.

    Same conversion as the compatibility raster exporter and Node
    ``cssColorRgba8``. Unresolved / browser-only values use the native
    never-invisible fallback.
    """
    return _native.css_color_rgba(str(css), float(opacity))


def rgba8(paint: Any) -> np.ndarray:
    """Format 0-1 RGBA rows as RGBA8 via ABI 251 ``xyg_clip_quantize_u8``."""
    arr = np.asarray(paint, dtype=np.float64)
    return np.ascontiguousarray(
        kernels.clip_quantize_u8(arr.reshape(-1)).reshape(arr.shape), dtype=np.uint8
    )


def solid_paint(css: Any) -> str | None:
    """A parseable solid CSS color string, or None when unset/unpaintable.

    ``var()`` and gradients are omitted rather than fallback-painted. Fully
    transparent colors (alpha 0) are pure no-op fills and are omitted as well.
    """
    s = _css(css, "")
    if not s:
        return None
    _status, rgba = kernels.css_check(kernels.CSS_COLOR, s)
    if rgba is None or rgba[3] == 0:
        return None
    return s


def fill_opacity(style: dict[str, Any], default: float = 1.0) -> float:
    """CSS whole-mark opacity multiplied by the fill-only channel."""
    return float(style.get("opacity", default)) * float(style.get("fill_opacity", 1.0))


def stroke_opacity(style: dict[str, Any], default: float = 1.0) -> float:
    """CSS whole-mark opacity multiplied by the stroke-only channel."""
    return float(style.get("opacity", default)) * float(style.get("stroke_opacity", 1.0))


def rgb_css(paint: Any) -> str:
    """Format 0-1 RGB as ``rgb(r,g,b)`` via ABI 251 ``xyg_clip_quantize_u8``."""
    u8 = kernels.clip_quantize_u8(np.asarray((paint[0], paint[1], paint[2]), dtype=np.float64))
    return f"rgb({int(u8[0])},{int(u8[1])},{int(u8[2])})"


def rgba8_hex(row: Any) -> str:
    """Format one RGBA8 row as ``#rrggbb`` for static legend swatches."""
    red, green, blue = int(row[0]), int(row[1]), int(row[2])
    return f"#{red:02x}{green:02x}{blue:02x}"


def colormap_stops(colormap: Any) -> list[tuple[int, int, int]]:
    """Evenly spaced RGB stops for a shipped colormap.

    Named maps resolve through ``xyg_colormap_stops`` (ABI 135). A sequence is
    an already-resolved custom ramp (`channels.resolve_colormap`) and is used
    verbatim.
    """
    if not isinstance(colormap, str):
        return [(int(r), int(g), int(b)) for r, g, b in colormap]
    return [(int(row[0]), int(row[1]), int(row[2])) for row in _native.colormap_stops(colormap)]


def colormap_lut(colormap: Any, t: np.ndarray) -> np.ndarray:
    """Vectorized colormap sample: t in [0,1] -> (n,3) uint8 via ABI 206."""
    values = np.asarray(t, dtype=np.float64).reshape(-1)
    stops = np.asarray(colormap_stops(colormap), dtype=np.uint8)
    return kernels.colormap_lut(values, stops)


def css_rgba8(css: Any, fallback: str, opacity: float = 1.0) -> tuple[int, int, int, int]:
    """Resolve one CSS paint token to RGBA8 after static var() fallback."""
    return paint_rgba8(_css(css, fallback), opacity)


def solid_rgba8(css: Any) -> tuple[int, int, int, int] | None:
    """Parseable solid CSS to RGBA8, or None when the fill must be omitted."""
    s = solid_paint(css)
    return None if s is None else paint_rgba8(s)


def physical_density_alpha(counts: Any, mean_alpha_u8: Any, style_opacity: float) -> np.ndarray:
    """Displayed alpha of a mean-color density cell (LOD doc §2 rule 1)."""
    counts_arr = np.asarray(counts, dtype=np.float64)
    alpha_u8 = np.asarray(mean_alpha_u8)
    a_pt = np.clip((alpha_u8.astype(np.float64) / 255.0) * float(style_opacity), 0.0, 1.0)
    coverage = np.zeros(a_pt.shape, dtype=np.float64)
    saturated = a_pt >= 1.0
    partial = ~saturated & (a_pt > 0.0)
    coverage[partial] = -np.expm1(counts_arr[partial] * np.log1p(-a_pt[partial]))
    coverage[saturated] = 1.0
    alpha = (np.clip(coverage, 0.0, 1.0) * 255.0).astype(np.uint8)
    alpha[(counts_arr <= 0) | (alpha_u8 == 0)] = 0
    return alpha


def grad_line(
    space: str,
    direction: str,
    bbox: tuple[float, float, float, float],
    plot: dict[str, float],
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Linear-gradient endpoints for mark or plot space."""
    x, y, w, h = bbox if space != "plot" else (plot["x"], plot["y"], plot["w"], plot["h"])
    cx, cy = x + w / 2, y + h / 2
    return {
        "down": ((cx, y), (cx, y + h)),
        "up": ((cx, y + h), (cx, y)),
        "right": ((x, cy), (x + w, cy)),
        "left": ((x + w, cy), (x, cy)),
    }.get(direction, ((cx, y), (cx, y + h)))


def grad_stops(fill_spec: dict[str, Any], mark_color: str) -> list[tuple[float, tuple[int, ...]]]:
    """Resolve gradient stop offsets and RGBA8 colors."""
    return [
        (float(offset), paint_rgba8(_css(color, mark_color)))
        for offset, color in fill_spec.get("stops", [])
    ]


def triangle_mesh_boundary(*vertices: np.ndarray) -> np.ndarray | None:
    """Recover one exterior walk from a connected tessellated polygon.

    ``Axes.fill`` reaches the shared triangle renderer for WebGL, but static
    exporters should paint its triangulation as one polygon. Otherwise each
    independently antialiased triangle leaks a hairline of background (and
    applies translucent alpha more than once) along internal diagonals.

    A filled strip can pinch where its two curves meet. Its boundary then has
    degree-four vertices rather than being a simple ring, and degenerate
    triangles at the pinch can repeat an edge twice. Retaining odd-count edges
    and following an Eulerian boundary walk preserves those touching lobes as
    one static fill without exposing the tessellation.
    """
    if len(vertices) != 6:
        raise ValueError("triangle mesh boundary requires six coordinate arrays")
    arrays = [np.asarray(values, dtype=np.float64).reshape(-1) for values in vertices]
    n = min((len(values) for values in arrays), default=0)
    if n == 0:
        return None
    coordinates = np.concatenate([values[:n] for values in arrays])
    if not np.isfinite(coordinates).all():
        return None
    span = float(coordinates.max() - coordinates.min())
    # Each triangle coordinate is transported in an independently offset
    # float32 column, so the same source vertex may decode a few ULPs apart in
    # x0/x1/x2. The joined-fill flag is only used for one simple polygon; a
    # generous relative bucket is still far below meaningful edge spacing.
    tolerance = max(span * 2e-5, 1e-12)

    # A single rounded bucket is not a proximity test: two float32-decoded
    # copies of one source vertex can straddle its boundary. Search the
    # neighboring cells and snap each copy to a stable representative instead.
    buckets: dict[tuple[int, int], list[int]] = {}
    points_by_key: list[tuple[float, float]] = []

    def vertex_key(point: tuple[float, float]) -> int:
        cell = (math.floor(point[0] / tolerance), math.floor(point[1] / tolerance))
        best: int | None = None
        best_distance = math.inf
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for candidate in buckets.get((cell[0] + dx, cell[1] + dy), ()):
                    other = points_by_key[candidate]
                    delta_x, delta_y = abs(point[0] - other[0]), abs(point[1] - other[1])
                    if delta_x <= tolerance and delta_y <= tolerance:
                        distance = delta_x * delta_x + delta_y * delta_y
                        if distance < best_distance:
                            best, best_distance = candidate, distance
        if best is not None:
            return best
        key = len(points_by_key)
        points_by_key.append(point)
        buckets.setdefault(cell, []).append(key)
        return key

    edge_counts: dict[tuple[int, int], int] = {}
    for index in range(n):
        points = (
            (float(arrays[0][index]), float(arrays[1][index])),
            (float(arrays[2][index]), float(arrays[3][index])),
            (float(arrays[4][index]), float(arrays[5][index])),
        )
        for start, end in zip(points, points[1:] + points[:1], strict=True):
            start_key, end_key = vertex_key(start), vertex_key(end)
            edge = (start_key, end_key) if start_key <= end_key else (end_key, start_key)
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
    # Internal edges occur an even number of times. Degenerate triangles can
    # contribute the same edge twice, so ``count == 1`` incorrectly removes a
    # real boundary edge after a curve touches its baseline.
    boundary = [edge for edge, count in edge_counts.items() if edge[0] != edge[1] and count % 2]
    if len(boundary) < 3:
        return None
    adjacency: dict[int, set[int]] = {}
    for start, end in boundary:
        adjacency.setdefault(start, set()).add(end)
        adjacency.setdefault(end, set()).add(start)
    if any(len(neighbors) % 2 for neighbors in adjacency.values()):
        return None

    # Hierholzer's algorithm also handles pinch vertices where two or more
    # boundary rings touch at one point. A disconnected boundary (for example,
    # a polygon with a hole) deliberately falls back to triangle rendering:
    # the current static fill command carries one walk and cannot preserve
    # multiple-subpath winding semantics.
    first = boundary[0][0]
    stack = [first]
    walk: list[int] = []
    while stack:
        current = stack[-1]
        if adjacency[current]:
            following = adjacency[current].pop()
            adjacency[following].remove(current)
            stack.append(following)
        else:
            walk.append(stack.pop())
    if len(walk) != len(boundary) + 1 or walk[0] != walk[-1]:
        return None
    walk.reverse()
    return np.asarray([points_by_key[key] for key in walk[:-1]], dtype=np.float64)


def polar_clip_line_segments(
    polar: Any,
    x0: np.ndarray,
    y0: np.ndarray,
    x1: np.ndarray,
    y1: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Clip line segments to polar radial and theta bounds in display space."""
    c0 = np.asarray(polar.r_scale.coord(y0), dtype=np.float64)
    c1 = np.asarray(polar.r_scale.coord(y1), dtype=np.float64)
    lo = min(polar.r_lo_coord, polar.r_hi_coord)
    hi = max(polar.r_lo_coord, polar.r_hi_coord)
    finite = np.isfinite(x0) & np.isfinite(x1) & np.isfinite(c0) & np.isfinite(c1)
    keep = finite & (np.maximum(c0, c1) >= lo) & (np.minimum(c0, c1) <= hi)
    dr = c1 - c0
    ta = np.zeros(len(x0), dtype=np.float64)
    tb = np.ones(len(x0), dtype=np.float64)
    moving = np.abs(dr) > 1e-30
    ta[moving] = (lo - c0[moving]) / dr[moving]
    tb[moving] = (hi - c0[moving]) / dr[moving]
    t0 = np.maximum(0.0, np.minimum(ta, tb))
    t1 = np.minimum(1.0, np.maximum(ta, tb))
    clipped_x0 = x0 + (x1 - x0) * t0
    clipped_x1 = x0 + (x1 - x0) * t1
    clipped_c0 = np.clip(c0 + dr * t0, lo, hi)
    clipped_c1 = np.clip(c0 + dr * t1, lo, hi)
    clipped_y0 = polar.r_scale.value(clipped_c0)
    clipped_y1 = polar.r_scale.value(clipped_c1)
    keep = keep & polar.theta_visible_mask(clipped_x0) & polar.theta_visible_mask(clipped_x1)
    px0, py0 = polar(clipped_x0, clipped_y0)
    px1, py1 = polar(clipped_x1, clipped_y1)
    return px0, py0, px1, py1, keep


def hexbin_ring(style: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """Data-space hexagon vertex offsets (6) for a hexbin trace's cell pitch."""
    return _native.hexbin_ring(float(style.get("hex_dx", 0.0)), float(style.get("hex_dy", 0.0)))


def step_arrays(xv: np.ndarray, yv: np.ndarray, where: str) -> tuple[np.ndarray, np.ndarray]:
    """Expand compact vertices into a step polyline via ABI 211."""
    mode = 1 if where == "pre" else 2 if where == "mid" else 3
    return _native.step_arrays(
        np.asarray(xv, dtype=np.float64), np.asarray(yv, dtype=np.float64), mode
    )


def authored_marker_points(
    unit_x: np.ndarray,
    unit_y: np.ndarray,
    cx: float,
    cy: float,
    scale: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Pixel-space authored marker vertices via ABI 212."""
    return _native.marker_path_scale(
        float(cx),
        float(cy),
        float(scale),
        np.asarray(unit_x, dtype=np.float64),
        np.asarray(unit_y, dtype=np.float64),
    )


_BEZIER_STEPS = 16


def curve_points(
    xv: np.ndarray,
    yv: np.ndarray,
    sx: Any,
    sy: Any,
    smooth: bool,
    *,
    bezier_steps: int = _BEZIER_STEPS,
) -> np.ndarray:
    """Pixel-space polyline; smooth uses Rust monotone-cubic flatten (ABI 121)."""
    px = np.asarray(sx(xv), dtype=np.float64)
    py = np.asarray(sy(yv), dtype=np.float64)
    if not smooth or len(xv) < 3 or not (sx.affine and sy.affine):
        return np.column_stack([px, py])
    data_x, data_y = kernels.curve_flatten(
        np.asarray(xv, dtype=np.float64),
        np.asarray(yv, dtype=np.float64),
        bezier_steps,
    )
    return np.column_stack(
        [np.asarray(sx(data_x), dtype=np.float64), np.asarray(sy(data_y), dtype=np.float64)]
    )


def corner_radii(style: dict[str, Any]) -> tuple[float, float]:
    """Resolve bar/rect tip and base corner radii from one style dict."""
    cr = style.get("corner_radius", 0)
    if isinstance(cr, (list, tuple)):
        return float(cr[0]), float(cr[1])
    value = float(cr or 0)
    return value, value


def rounded_rect_vertices(
    x: float,
    y: float,
    w: float,
    h: float,
    r_tip: float,
    r_base: float,
    tip_top: bool,
) -> list[tuple[float, float]]:
    """CW rounded-rect outline via ABI 121 ``xyg_rounded_rect_poly``."""
    xs, ys = kernels.rounded_rect_poly(x, y, w, h, r_tip, r_base, tip_top)
    return list(zip(xs.tolist(), ys.tolist(), strict=True))


def direct_rgba(channel: dict[str, Any], n: int, read_column: ColumnReader) -> np.ndarray | None:
    """Decode a packed normalized RGBA8 channel to canonical float RGBA."""
    if channel.get("mode") != "direct_rgba":
        return None
    raw = np.asarray(read_column(int(channel["buf"])), dtype=np.uint8).reshape(-1)
    expected = n * 4
    if len(raw) < expected:
        raise ValueError(f"direct RGBA buffer has {len(raw)} bytes; expected {expected}")
    return raw[:expected].reshape(n, 4).astype(np.float64) / 255.0


def style_values(
    trace: dict[str, Any],
    name: str,
    n: int,
    read_column: ColumnReader,
    default: float,
) -> np.ndarray:
    """Resolve one scalar/direct numeric style channel to N float values."""
    channel = (trace.get("channels") or {}).get(name)
    if channel is None:
        return np.full(n, float(trace.get("style", {}).get(name, default)), dtype=np.float64)
    raw = np.asarray(read_column(int(channel["buf"])), dtype=np.float64)
    components = int(channel.get("components", 1))
    expected = n * components
    if raw.size < expected:
        raise ValueError(f"{name} style buffer has {raw.size} values; expected {expected}")
    return raw[:expected].reshape(n, components)[:, 0]


def style_matrix(
    trace: dict[str, Any],
    name: str,
    n: int,
    read_column: ColumnReader,
) -> np.ndarray | None:
    """Return a direct style channel as its ``(N, components)`` matrix."""
    channel = (trace.get("channels") or {}).get(name)
    if channel is None:
        return None
    components = int(channel.get("components", 1))
    raw = np.asarray(read_column(int(channel["buf"])), dtype=np.float64)
    expected = n * components
    if raw.size < expected:
        raise ValueError(f"{name} style buffer has {raw.size} values; expected {expected}")
    return raw[:expected].reshape(n, components)


def effective_rgba(
    intrinsic: np.ndarray,
    trace: dict[str, Any],
    read_column: ColumnReader,
    *,
    component: str,
    default_opacity: float,
) -> np.ndarray:
    """Apply Matplotlib artist alpha and xy opacity in the documented order.

    Intrinsic paint alpha is replaced (not multiplied) when artist alpha is
    non-negative. Core opacity and the component-specific fill/stroke opacity
    remain multiplicative.
    """
    rgba = np.asarray(intrinsic, dtype=np.float64)
    if rgba.ndim != 2 or rgba.shape[1] != 4:
        raise ValueError(f"intrinsic paint must have shape (N, 4), got {rgba.shape}")
    n = len(rgba)
    style = trace.get("style") or {}
    artist = style_values(trace, "artist_alpha", n, read_column, -1.0)
    opacity = style_values(trace, "opacity", n, read_column, default_opacity)
    component_opacity = float(style.get(f"{component}_opacity", 1.0))
    return kernels.paint_effective_rgba(rgba, artist, opacity, component_opacity)


def trace_paint_rgba(
    trace: dict[str, Any],
    key: str,
    n: int,
    fallback: str,
    read: ColumnReader,
) -> np.ndarray:
    """Resolve one payload paint channel to intrinsic float RGBA."""
    channel = trace.get(key) or {}
    direct = direct_rgba(channel, n, read)
    if direct is not None:
        return direct
    rgba = np.empty((n, 4), dtype=np.float64)
    rgba[:, 3] = 1.0
    mode = channel.get("mode")
    if mode == "continuous":
        values = np.asarray(read(channel["buf"]), dtype=np.float64).reshape(-1)[:n]
        stops = np.asarray(colormap_stops(channel.get("colormap", "viridis")), dtype=np.uint8)
        rgba[:, :3] = kernels.colormap_lut(values, stops) / 255.0
    elif mode == "categorical":
        from . import channels as _channels

        codes = np.asarray(read(channel["buf"]), dtype=np.int64)[:n]
        palette = channel.get("palette") or DEFAULT_PALETTE
        # Per-index resolution (channels.palette_rows_rgba8), not css_color_rgba
        # per entry: browser-only entries must degrade to DISTINCT built-in
        # colors, or every var() category exports as the same fallback blue.
        table = _channels.palette_rows_rgba8(palette, len(palette)).astype(np.float64) / 255.0
        rgba[:] = table[codes % len(table)]
    else:
        rgba[:] = (
            np.asarray(
                _native.css_color_rgba(_css(channel.get("color"), fallback)), dtype=np.float64
            )
            / 255.0
        )
    return rgba


def trace_paint_rgb_css_list(
    trace: dict[str, Any],
    key: str,
    n: int,
    fallback: str,
    read: ColumnReader,
) -> list[str]:
    """Resolve one paint channel to static SVG ``rgb(r,g,b)`` strings."""
    rows = rgba8(trace_paint_rgba(trace, key, n, fallback, read))
    return [rgb_css(row[:3] / 255.0) for row in rows]


def effective_paint_rgba8(
    trace: dict[str, Any],
    key: str,
    n: int,
    fallback: str,
    read: ColumnReader,
    *,
    component: str,
    default_opacity: float,
) -> np.ndarray:
    """Resolve one paint channel to effective RGBA8 rows."""
    intrinsic = trace_paint_rgba(trace, key, n, fallback, read)
    return rgba8(
        effective_rgba(
            intrinsic,
            trace,
            read,
            component=component,
            default_opacity=default_opacity,
        )
    )


def effective_paint_rgba(
    trace: dict[str, Any],
    key: str,
    n: int,
    fallback: str,
    read: ColumnReader,
    *,
    component: str,
    default_opacity: float,
) -> np.ndarray:
    """Resolve one paint channel to effective 0-1 RGBA rows."""
    intrinsic = trace_paint_rgba(trace, key, n, fallback, read)
    return effective_rgba(
        intrinsic,
        trace,
        read,
        component=component,
        default_opacity=default_opacity,
    )


def trace_fill_and_stroke_rgba8(
    trace: dict[str, Any],
    style: dict[str, Any],
    n: int,
    fallback: str,
    read: ColumnReader,
    *,
    default_opacity: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Resolve face paint plus effective fill/stroke RGBA8 rows."""
    face = trace_paint_rgba(trace, "color", n, fallback, read)
    fills = rgba8(
        effective_rgba(face, trace, read, component="fill", default_opacity=default_opacity)
    )
    strokes = effective_stroke_rgba8(
        trace, style, n, fallback, read, face, default_opacity=default_opacity
    )
    return face, fills, strokes


def trace_fill_and_stroke_rgba(
    trace: dict[str, Any],
    style: dict[str, Any],
    n: int,
    fallback: str,
    read: ColumnReader,
    *,
    default_opacity: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Resolve face paint plus effective fill/stroke 0-1 RGBA rows."""
    face = trace_paint_rgba(trace, "color", n, fallback, read)
    fills = effective_rgba(face, trace, read, component="fill", default_opacity=default_opacity)
    strokes = effective_stroke_rgba(
        trace, style, n, fallback, read, face, default_opacity=default_opacity
    )
    return face, fills, strokes


def trace_stroke_intrinsic(
    trace: dict[str, Any],
    style: dict[str, Any],
    n: int,
    fallback: str,
    read: ColumnReader,
    fill_intrinsic: np.ndarray,
) -> np.ndarray:
    """Resolve intrinsic stroke RGBA rows before effective opacity."""
    if (trace.get("stroke") or {}).get("mode") == "match_fill":
        return np.asarray(fill_intrinsic, copy=True)
    if trace.get("stroke") is not None:
        return trace_paint_rgba(trace, "stroke", n, fallback, read)
    style_stroke = style.get("stroke")
    if style_stroke is not None:
        rgba = np.asarray(paint_rgba8(_css(style_stroke, fallback)), dtype=np.float64) / 255.0
        return np.tile(rgba, (n, 1))
    return np.asarray(fill_intrinsic, copy=True)


def effective_stroke_rgba8(
    trace: dict[str, Any],
    style: dict[str, Any],
    n: int,
    fallback: str,
    read: ColumnReader,
    fill_intrinsic: np.ndarray,
    *,
    default_opacity: float,
) -> np.ndarray:
    """Resolve stroke paint to effective RGBA8 rows."""
    return rgba8(
        effective_rgba(
            trace_stroke_intrinsic(trace, style, n, fallback, read, fill_intrinsic),
            trace,
            read,
            component="stroke",
            default_opacity=default_opacity,
        )
    )


def effective_stroke_rgba(
    trace: dict[str, Any],
    style: dict[str, Any],
    n: int,
    fallback: str,
    read: ColumnReader,
    fill_intrinsic: np.ndarray,
    *,
    default_opacity: float,
) -> np.ndarray:
    """Resolve stroke paint to effective 0-1 RGBA rows."""
    return effective_rgba(
        trace_stroke_intrinsic(trace, style, n, fallback, read, fill_intrinsic),
        trace,
        read,
        component="stroke",
        default_opacity=default_opacity,
    )


def trace_paint_css_constant(trace: dict[str, Any], key: str, fallback: str) -> tuple[str, bool]:
    """Return a paint channel CSS token and whether it is an opaque constant."""
    channel = trace.get(key) or {}
    css = _css(channel.get("color"), fallback)
    constant = channel.get("mode") in {None, "constant"} and paint_rgba8(css)[3] == 255
    return css, constant


def trace_stroke_css_meta(
    trace: dict[str, Any],
    style: dict[str, Any],
    fallback: str,
    face_css: str,
    face_css_constant: bool,
) -> tuple[str, bool]:
    """Return stroke CSS metadata for Scene fast-path SVG scatter."""
    if (trace.get("stroke") or {}).get("mode") == "match_fill":
        return face_css, face_css_constant
    if trace.get("stroke") is not None:
        stroke_css = _css((trace.get("stroke") or {}).get("color"), style.get("stroke") or face_css)
        stroke_css_constant = (trace.get("stroke") or {}).get("mode") in {
            None,
            "constant",
        } and paint_rgba8(stroke_css)[3] == 255
        return stroke_css, stroke_css_constant
    if style.get("stroke") is not None:
        stroke_css = _css(style.get("stroke"), face_css)
        return stroke_css, paint_rgba8(stroke_css)[3] == 255
    return face_css, face_css_constant


def scatter_radii(size_ch: dict[str, Any], read: ColumnReader, n: int) -> np.ndarray:
    """Resolve scatter marker radii from a size channel spec."""
    if size_ch.get("mode") == "continuous":
        values = np.asarray(read(int(size_ch["buf"])), dtype=np.float64).reshape(-1)[:n]
        r0, r1 = size_ch.get("range_px", [2, 18])
        return (r0 + (r1 - r0) * np.clip(values, 0, 1)) / 2
    return np.full(n, float(size_ch.get("size", 4.0)) / 2)


def scatter_grouped_artist_alpha(
    trace: dict[str, Any],
    style: dict[str, Any],
    face_intrinsic: np.ndarray,
) -> tuple[dict[str, Any], np.ndarray, bool, float | None]:
    """Normalize trace paint when matplotlib scalar artist_alpha groups on SVG."""
    scalar = style.get("artist_alpha")
    grouped = scalar is not None and not (trace.get("channels") or {}).get("artist_alpha")
    if not grouped:
        return trace, face_intrinsic, False, None
    face = np.asarray(face_intrinsic, copy=True)
    face[:, 3] = 1.0
    effective_trace = dict(trace)
    effective_style = dict(style)
    effective_style.pop("artist_alpha", None)
    effective_style["opacity"] = 1.0
    effective_style["fill_opacity"] = 1.0
    effective_style["stroke_opacity"] = 1.0
    effective_trace["style"] = effective_style
    return effective_trace, face, True, float(scalar)


def scatter_svg_paint(
    trace: dict[str, Any],
    style: dict[str, Any],
    effective_trace: dict[str, Any],
    face_intrinsic: np.ndarray,
    fallback: str,
    read: ColumnReader,
    *,
    default_opacity: float,
) -> tuple[np.ndarray, np.ndarray, str, bool, str, bool]:
    """Resolve SVG scatter face/stroke paint rows and opaque CSS metadata."""
    face_css, face_css_constant = trace_paint_css_constant(trace, "color", fallback)
    face_rgba = effective_rgba(
        face_intrinsic, effective_trace, read, component="fill", default_opacity=default_opacity
    )
    n = len(face_intrinsic)
    stroke_source = trace_stroke_intrinsic(trace, style, n, fallback, read, face_intrinsic)
    stroke_css, stroke_css_constant = trace_stroke_css_meta(
        trace, style, fallback, face_css, face_css_constant
    )
    stroke_rgba = effective_rgba(
        stroke_source, effective_trace, read, component="stroke", default_opacity=default_opacity
    )
    return face_rgba, stroke_rgba, face_css, face_css_constant, stroke_css, stroke_css_constant


def ribbon_fill_rgba(
    trace: dict[str, Any],
    n: int,
    fallback: str,
    read: ColumnReader,
    *,
    default_opacity: float = 1.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Resolve ribbon source paint and effective source/target fill rows."""
    source = trace_paint_rgba(trace, "color", n, fallback, read)
    fills = effective_rgba(source, trace, read, component="fill", default_opacity=default_opacity)
    if trace.get("color_target"):
        target = trace_paint_rgba(trace, "color_target", n, fallback, read)
        fills2 = effective_rgba(
            target, trace, read, component="fill", default_opacity=default_opacity
        )
    else:
        fills2 = fills
    return source, fills, fills2


def ribbon_fill_rgba8(
    trace: dict[str, Any],
    n: int,
    fallback: str,
    read: ColumnReader,
    *,
    default_opacity: float = 1.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Resolve ribbon source paint and effective source/target RGBA8 fills."""
    source, fills, fills2 = ribbon_fill_rgba(
        trace, n, fallback, read, default_opacity=default_opacity
    )
    return source, rgba8(fills), rgba8(fills2)
