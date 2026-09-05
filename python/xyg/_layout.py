"""Shared static-export scale and polar projection helpers."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, Optional

import numpy as np

from . import _native, _textblock
from . import channels as _channels
from ._paint import _css
from ._paint import paint_rgba8 as _paint_rgba8
from ._paint import px_size as _px_size
from ._paint import rgba8_hex as _rgba8_hex
from .config import DEFAULT_PALETTE

# Shared static chrome token and tick-density constants (M2 #873 consolidation).
_MS = {"s": 1e3, "m": 6e4, "h": 36e5, "d": 864e5}
_Y_TITLE_TICK_GAP = 0.4
_SCENE_SCALE_KINDS = {"linear": 0, "log": 1, "symlog": 2}


class _Scale:
    """value -> px for one axis (linear / time-in-ms / log / category)."""

    _SCALAR_CACHE_LIMIT = 256

    def __init__(self, axis: dict[str, Any], px0: float, px1: float) -> None:
        self.kind = axis.get("kind", "linear")
        lo, hi = axis["range"]
        # ``kind`` describes the data domain (linear/time/category), while the
        # public axis option is serialized separately as ``scale``. Accept the
        # historical kind form too for old payloads.
        self.log = axis.get("scale") == "log" or self.kind == "log"
        self.nonpositive = axis.get("nonpositive", "clip")
        self.symlog = axis.get("scale") == "symlog"
        self.constant = float(axis.get("constant", 1.0))
        self.data_lo, self.data_hi = float(lo), float(hi)
        self.px0, self.px1 = px0, px1
        # Static exporters revisit the same ticks, baselines, and polar band
        # edges across grid, labels, marks, and clips. Rust remains the only
        # policy implementation; retain its scalar result so those consumers
        # do not cross the ABI again for an identical scale operation.
        self._scalar_cache: tuple[dict[str, float], ...] = ({}, {}, {})

    @property
    def _kind_code(self) -> int:
        return 1 if self.log else 2 if self.symlog else 0

    def _map(self, value: Any, operation: int) -> Any:
        scalar = np.ndim(value) == 0
        scalar_value = float(value) if scalar else 0.0
        cache_key = scalar_value.hex()
        cache = self._scalar_cache[operation]
        if scalar and cache_key in cache:
            return cache[cache_key]
        result = _native.scene_scale_map(
            value,
            self._kind_code,
            operation,
            self.data_lo,
            self.data_hi,
            self.px0,
            self.px1,
            self.constant,
            self.nonpositive == "mask",
        )
        if scalar and len(cache) < self._SCALAR_CACHE_LIMIT:
            cache[cache_key] = float(result)
        elif not scalar and np.size(value) <= self._SCALAR_CACHE_LIMIT:
            for source, mapped in zip(np.ravel(value), np.ravel(result), strict=True):
                key = float(source).hex()
                if key in cache:
                    continue
                if len(cache) >= self._SCALAR_CACHE_LIMIT:
                    break
                cache[key] = float(mapped)
        return result

    def coord(self, v: Any) -> Any:
        return self._map(v, 0)

    def __call__(self, v: Any) -> Any:
        return self._map(v, 1)

    def value(self, c: Any) -> Any:
        """Inverse of `coord`: scale coordinate back to a data value."""
        return self._map(c, 2)

    @property
    def affine(self) -> bool:
        return not (self.log or self.symlog)


# Direction that theta=0 points, as an angle in radians measured
# counterclockwise from due East. Mirrored by THETA_ZERO in
# js/src/50_chartview.ts.
THETA_ZERO = {"E": 0.0, "N": math.pi / 2.0, "W": math.pi, "S": -math.pi / 2.0}


class _PolarProjection:
    """(theta, r) -> px for a polar chart — spec/design/polar-axes.md §3.

    The joint replacement for the separable `_Scale` pair: polar position needs
    both coordinates at once, so this is *not* two 1-D maps. `theta` and `r`
    still arrive in scaled data space (a `_Scale.coord` has already applied any
    log/symlog), and this class only performs the final placement.

    Screen space grows downward, so the y term is a **subtraction**. The GLSL
    twin in `xyPolar` (js/src/40_gl.ts) adds instead, because clip space grows
    upward. `tests/test_polar_transform.py` binds both to the same fixtures.

    Layout, projection, and visibility masks are owned by Rust (ABI 131);
    wedge/ring/polygon helpers remain here and call native projection.
    """

    def __init__(
        self,
        theta_axis: dict[str, Any],
        r_axis: dict[str, Any],
        plot: dict[str, float],
    ) -> None:
        self.plot = plot
        self.theta_axis = theta_axis
        self.r_axis = r_axis
        self.unit = theta_axis.get("theta_unit", "radians")
        self.unit_scale = math.pi / 180.0 if self.unit == "degrees" else 1.0
        self.turn = 360.0 if self.unit == "degrees" else 2.0 * math.pi
        zero = theta_axis.get("theta_zero", "E")
        self.zero = THETA_ZERO[zero] if isinstance(zero, str) else float(zero)
        self.direction = theta_axis.get("theta_direction", "counterclockwise")
        self.dir = -1.0 if self.direction == "clockwise" else 1.0
        sector = theta_axis.get("sector") or (0.0, self.turn)
        self.sector_start, self.sector_end = (float(sector[0]), float(sector[1]))
        self.sector_span = self.sector_end - self.sector_start
        self.full_sector = self.sector_span >= self.turn * (1.0 - 1e-9)
        self.sector_a0 = self.zero + self.dir * self.unit_scale * self.sector_start
        self.sector_a1 = self.zero + self.dir * self.unit_scale * self.sector_end
        self.grid_shape = theta_axis.get("grid_shape", "circular")
        self.categories = tuple(theta_axis.get("categories") or ())
        self.category_count = len(self.categories)

        r_lo, r_hi = r_axis["range"]
        self.r_lo, self.r_hi = float(r_lo), float(r_hi)
        self.r_scale = _Scale(r_axis, 0.0, 1.0)
        self.r_lo_coord = float(self.r_scale.coord(self.r_lo))
        self.r_hi_coord = float(self.r_scale.coord(self.r_hi))
        origin = r_axis.get("r_origin")
        self.r_origin = self.r_lo if origin is None else float(origin)
        self.r_origin_coord = float(self.r_scale.coord(self.r_origin))
        self.hole = float(r_axis.get("hole") or 0.0)

        self._metrics = _native.polar_layout(theta_axis, r_axis, plot)
        self.cx = float(self._metrics[0])
        self.cy = float(self._metrics[1])
        self.radius = float(self._metrics[2])

    def theta_value(self, theta: Any) -> Any:
        """Category code or numeric theta -> angular value in declared units."""
        th = np.asarray(theta, dtype=np.float64)
        if not self.category_count:
            return th
        divisor = (
            float(self.category_count)
            if self.full_sector
            else float(max(self.category_count - 1, 1))
        )
        return self.sector_start + th * self.sector_span / divisor

    def angle(self, theta: Any) -> Any:
        """Data theta -> screen angle in radians, ccw from East."""
        th = self.theta_value(theta) * self.unit_scale
        return self.zero + self.dir * th

    def theta_from_angle(self, angle: Any, *, near: Optional[float] = None) -> Any:
        """Screen angle -> numeric theta/category code.

        The result is wrapped relative to the authored sector. ``near`` is a
        heatmap range start and selects the equivalent full-turn value nearest
        that grid, matching the fragment shader at the angular seam.
        """
        raw = (np.asarray(angle, dtype=np.float64) - self.zero) / (self.dir * self.unit_scale)
        anchor = self.sector_start if near is None else float(near)
        raw = anchor + np.mod(raw - anchor, self.turn)
        if not self.category_count:
            return raw
        divisor = (
            float(self.category_count)
            if self.full_sector
            else float(max(self.category_count - 1, 1))
        )
        return (raw - self.sector_start) * divisor / (self.sector_span or 1.0)

    def theta_visible_mask(self, theta: Any) -> np.ndarray:
        """Which angular values fall in the authored sector."""
        return _native.polar_theta_visible_mask(self._metrics, theta)

    def _angular_value_visible_mask(self, raw: Any) -> np.ndarray:
        raw = np.asarray(raw, dtype=np.float64)
        if self.full_sector:
            return np.isfinite(raw)
        offset = np.mod(raw - self.sector_start, self.turn)
        return np.isfinite(raw) & (offset <= self.sector_span + self.turn * 1e-9)

    def angle_visible(self, angle: float) -> bool:
        raw = (float(angle) - self.zero) / (self.dir * self.unit_scale)
        return bool(self._angular_value_visible_mask(raw))

    def filter_theta_values(self, values: Sequence[float]) -> list[float]:
        if not values:
            return []
        mask = self.theta_visible_mask(values)
        return [float(value) for value, keep in zip(values, mask, strict=True) if bool(keep)]

    def norm_radius(self, r: Any) -> Any:
        coord = np.asarray(self.r_scale.coord(r), dtype=np.float64)
        span = self.r_hi_coord - self.r_origin_coord
        if abs(span) <= 1e-30:
            return np.full_like(coord, np.nan, dtype=np.float64)
        base = (coord - self.r_origin_coord) / span
        return self.hole + (1.0 - self.hole) * base

    def radius_value(self, normalized: Any) -> Any:
        """Inverse of ``norm_radius`` back to radial data space."""
        normalized = np.asarray(normalized, dtype=np.float64)
        base = (normalized - self.hole) / max(1.0 - self.hole, 1e-30)
        coord = self.r_origin_coord + base * (self.r_hi_coord - self.r_origin_coord)
        return self.r_scale.value(coord)

    @property
    def inner_fraction(self) -> float:
        return max(0.0, min(1.0, float(self.norm_radius(self.r_lo))))

    @property
    def inner_radius(self) -> float:
        return self.inner_fraction * self.radius

    def visible_mask(self, r: Any) -> np.ndarray:
        """Which radii have an honest polar position — `xyPolarPos`'s cull."""
        return _native.polar_visible_mask(self._metrics, r)

    def position_mask(self, theta: Any, r: Any) -> np.ndarray:
        return _native.polar_position_mask(self._metrics, theta, r)

    def __call__(self, theta: Any, r: Any) -> tuple[Any, Any]:
        return _native.polar_project(self._metrics, theta, r)

    def ring(self, r: float, steps: int = 180) -> list[tuple[float, float]]:
        """A constant-r sector arc (a closed circle for a full turn)."""
        rn = float(self.norm_radius(r)) * self.radius
        count = steps if self.full_sector else steps + 1
        return [
            (
                self.cx
                + rn * math.cos(self.sector_a0 + (self.sector_a1 - self.sector_a0) * i / steps),
                self.cy
                - rn * math.sin(self.sector_a0 + (self.sector_a1 - self.sector_a0) * i / steps),
            )
            for i in range(count)
        ]

    def polygon_ring(self, r: float, theta_values: Sequence[float]) -> list[tuple[float, float]]:
        values = self.filter_theta_values(theta_values)
        if not values:
            return []
        values.sort(
            key=lambda value: float(
                np.mod(float(self.theta_value(value)) - self.sector_start, self.turn)
            )
        )
        values = [
            value
            for index, value in enumerate(values)
            if index == 0
            or not math.isclose(
                float(
                    np.mod(
                        float(self.theta_value(value)) - float(self.theta_value(values[index - 1])),
                        self.turn,
                    )
                ),
                0.0,
                rel_tol=0,
                abs_tol=self.turn * 1e-10,
            )
        ]
        if not self.full_sector:
            if not math.isclose(
                float(self.theta_value(values[0])), self.sector_start, rel_tol=0, abs_tol=1e-9
            ):
                values.insert(0, self._theta_data_for_sector(self.sector_start))
            if not math.isclose(
                float(self.theta_value(values[-1])), self.sector_end, rel_tol=0, abs_tol=1e-9
            ):
                values.append(self._theta_data_for_sector(self.sector_end))
        x, y = self(values, np.full(len(values), r, dtype=np.float64))
        return list(zip(np.asarray(x, dtype=float), np.asarray(y, dtype=float), strict=True))

    def _theta_data_for_sector(self, value: float) -> float:
        if not self.category_count:
            return value
        divisor = (
            float(self.category_count)
            if self.full_sector
            else float(max(self.category_count - 1, 1))
        )
        return (value - self.sector_start) * divisor / (self.sector_span or 1.0)

    def wedge_angles(self, theta0: float, theta1: float) -> Optional[tuple[float, float]]:
        """Visible screen-angle interval for an authored angular band."""
        raw0 = float(self.theta_value(theta0))
        raw1 = float(self.theta_value(theta1))
        if not (math.isfinite(raw0) and math.isfinite(raw1)):
            return None
        if self.full_sector:
            return (
                self.zero + self.dir * self.unit_scale * raw0,
                self.zero + self.dir * self.unit_scale * raw1,
            )

        low, high = min(raw0, raw1), max(raw0, raw1)
        midpoint = (low + high) / 2.0
        sector_midpoint = (self.sector_start + self.sector_end) / 2.0
        nearest_turn = round((sector_midpoint - midpoint) / self.turn)
        best: Optional[tuple[float, float]] = None
        best_span = -1.0
        for turn_index in (nearest_turn - 1, nearest_turn, nearest_turn + 1):
            shifted_low = low + turn_index * self.turn
            shifted_high = high + turn_index * self.turn
            clipped_low = max(self.sector_start, shifted_low)
            clipped_high = min(self.sector_end, shifted_high)
            span = clipped_high - clipped_low
            if span > best_span and span > 1e-12:
                best = (clipped_low, clipped_high)
                best_span = span
        if best is None:
            return None
        clipped0, clipped1 = best if raw0 <= raw1 else (best[1], best[0])
        return (
            self.zero + self.dir * self.unit_scale * clipped0,
            self.zero + self.dir * self.unit_scale * clipped1,
        )

    def frame_points(
        self, theta_values: Sequence[float] = (), steps: int = 180
    ) -> list[tuple[float, float]]:
        if self.grid_shape == "linear" and theta_values:
            return self.polygon_ring(self.r_hi, theta_values)
        return self.ring(self.r_hi, steps)

    @property
    def affine(self) -> bool:
        """Never affine — see `affine_fast_path`."""
        return False


def affine_fast_path(sx: _Scale, sy: _Scale, polar: Optional[_PolarProjection] = None) -> bool:
    """May an emitter bake a straight-line data->pixel map into Rust?

    Several emitters hand Rust two affine scales and let it project while
    painting. A polar chart on linear axes satisfies `sx.affine and sy.affine`
    while being emphatically non-affine, so every such gate must ask this
    instead — one predicate rather than a `polar is None` conjunct repeated at
    each site, which is how one gate got missed and shipped a colormapped polar
    scatter projected as cartesian (§6).
    """
    return polar is None and sx.affine and sy.affine


def warp_axis_indices(scale: _Scale, lo: float, hi: float, n_src: int) -> Optional[np.ndarray]:
    """Source-cell index per output cell for a data-uniform grid on a nonlinear axis."""
    if scale.affine:
        return None
    c0, c1 = float(scale.coord(lo)), float(scale.coord(hi))
    if not (np.isfinite(c0) and np.isfinite(c1)) or c0 == c1:
        return None
    px_span = abs(float(scale(hi)) - float(scale(lo)))
    n_out = int(np.clip(round(px_span), n_src, 4096))
    centers = c0 + (np.arange(n_out, dtype=np.float64) + 0.5) * ((c1 - c0) / n_out)
    values = np.asarray(scale.value(centers), dtype=np.float64)
    idx = np.floor((values - lo) / (hi - lo) * n_src).astype(np.int64)
    return np.clip(idx, 0, n_src - 1)


def warp_grid_rgba(
    rgba: np.ndarray, x_range: list, y_range: list, sx: _Scale, sy: _Scale
) -> np.ndarray:
    """Resample a data-uniform (h, w, 4) grid so it is uniform in scale coordinates."""
    h, w = rgba.shape[:2]
    cols = warp_axis_indices(sx, float(x_range[0]), float(x_range[1]), w)
    rows = warp_axis_indices(sy, float(y_range[0]), float(y_range[1]), h)
    if cols is not None:
        rgba = rgba[:, cols]
    if rows is not None:
        rgba = rgba[rows, :]
    return rgba


def _axes_by_id(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Named axes from a payload spec, including primary x/y."""
    axes = dict(spec.get("axes") or {})
    axes["x"] = spec["x_axis"]
    axes["y"] = spec["y_axis"]
    return axes


def _axis_scales(
    spec: dict[str, Any], plot: dict[str, float]
) -> tuple[
    dict[str, _Scale],
    dict[str, _Scale],
    _Scale,
    _Scale,
    list[tuple[str, dict[str, Any], _Scale]],
    list[tuple[str, dict[str, Any], _Scale]],
]:
    """Pixel scales for every configured axis plus the named-axis lists."""
    axes = _axes_by_id(spec)
    x_scales = {
        axis_id: _Scale(axis, plot["x"], plot["x"] + plot["w"])
        for axis_id, axis in axes.items()
        if axis_id.startswith("x")
    }
    y_scales = {
        axis_id: _Scale(axis, plot["y"] + plot["h"], plot["y"])
        for axis_id, axis in axes.items()
        if axis_id.startswith("y")
    }
    sx = x_scales["x"]
    sy = y_scales["y"]
    extra_x_axes = [
        (axis_id, axis, x_scales[axis_id])
        for axis_id, axis in axes.items()
        if axis_id != "x" and axis_id.startswith("x")
    ]
    extra_y_axes = [
        (axis_id, axis, y_scales[axis_id])
        for axis_id, axis in axes.items()
        if axis_id != "y" and axis_id.startswith("y")
    ]
    return x_scales, y_scales, sx, sy, extra_x_axes, extra_y_axes


def polar_wedge_points(
    polar: _PolarProjection,
    theta0: float,
    theta1: float,
    r0: float,
    r1: float,
    steps: Optional[int] = None,
    corner_radius: float = 0.0,
    wedge_gap: float = 0.0,
    normalized: Optional[tuple[float, float]] = None,
) -> list[tuple[float, float]]:
    """An annular sector as a closed polygon — the flattened twin of
    `_polar_wedge_path`, for the raster display list (no arc opcode).

    Both are driven by the same angles and radii, so the two exports agree to
    within the flattening. `steps` defaults to `config.polar_bar_segments` over
    this wedge's own sweep — a 22.5-degree wind-rose sector is flattened with six
    segments rather than the full-turn worst case of 96, at the same sagitta
    bound. Pass an explicit count only to pin one. Flattening is ABI 209
    (`xyg_polar_wedge_points`); this wrapper only packs metrics and optional
    host-normalized radial fractions.
    """
    return _native.polar_wedge_points(
        polar._metrics,
        float(theta0),
        float(theta1),
        float(r0),
        float(r1),
        wedge_gap=float(wedge_gap),
        corner_radius=float(corner_radius),
        steps=0 if steps is None else int(steps),
        normalized=normalized,
    )


# ---------------------------------------------------------------------------
# Compatibility axis measurement surface (pyplot non-Scene axes and legacy
# probes). Rust owns every layout/tick decision via ABI 121/123/125/126/198;
# these helpers only marshal authored facts and iterate host axes.
# ---------------------------------------------------------------------------


def _fmt_log(v: float) -> str:
    """Colorbar log tick labels — same magnitude policy as axis log ticks."""
    return _native.tick_format(float(v), 1.0, scale="log")


def _fmt_axis(axis: dict[str, Any], v: float, step: float) -> str:
    return _native.tick_format(
        float(v),
        float(step),
        kind=axis.get("kind"),
        scale=axis.get("scale"),
        theta_unit=axis.get("theta_unit"),
        format=axis.get("format"),
        categories=axis.get("categories"),
    )


def _tick_text(axis: dict[str, Any], value: float, step: float) -> str:
    values = axis.get("tick_values")
    labels = axis.get("tick_labels")
    if values is not None and labels is not None:
        for index, candidate in enumerate(values):
            if float(candidate) == value and index < len(labels):
                return str(labels[index])
    return _fmt_axis(axis, value, step)


def _tick_label_anchor(axis: dict[str, Any], style: dict[str, Any], default: str) -> str:
    """Canonical tick-label anchor (``start``/``center``/``end``) from the
    axis spec or its style — validators normalize the mpl aliases upstream —
    with ``default`` (the classic layout) when unset."""
    raw = axis.get("tick_label_anchor") or style.get("tick_label_anchor")
    return raw if raw in ("start", "center", "end") else default


def _tick_window(axis: dict[str, Any]) -> tuple[float, float]:
    """The value window ticks are drawn in — the sector for an angular axis."""
    lo, hi = (float(v) for v in axis["range"])
    sector = axis.get("sector")
    if sector:
        sector_lo, sector_hi = float(sector[0]), float(sector[1])
    else:
        sector_lo = sector_hi = float("nan")
    return _native.tick_window(
        lo,
        hi,
        theta_unit=axis.get("theta_unit"),
        kind="category" if axis.get("kind") == "category" else "linear",
        n_categories=len(axis.get("categories") or []),
        sector_lo=sector_lo,
        sector_hi=sector_hi,
    )


def _tick_window_filter(
    axis: dict[str, Any],
    lo: float,
    hi: float,
    values: Sequence[Any],
    *,
    require_finite: bool = False,
) -> list[float]:
    """Compact ``values`` that fall inside the axis window."""
    return _native.tick_window_filter(
        [float(v) for v in values],
        lo,
        hi,
        theta_unit=axis.get("theta_unit"),
        kind="category" if axis.get("kind") == "category" else "linear",
        require_finite=require_finite,
    )


def axis_ticks(
    axis: dict[str, Any], length_px: float, is_x: bool
) -> tuple[list[float], list[float], float]:
    """(ticks, labeled ticks, step) for an axis at a given pixel length — shared
    tick density so SVG and PNG label the same values."""
    kind = axis.get("kind")
    lo, hi = _tick_window(axis)
    if axis.get("tick_values") is not None:
        ticks = _tick_window_filter(axis, lo, hi, axis["tick_values"])
        step = abs(ticks[1] - ticks[0]) if len(ticks) > 1 else 1.0
        return ticks, ticks, step
    requested = axis.get("tick_count")
    if isinstance(requested, (int, float)) and not isinstance(requested, bool) and requested > 0:
        target = max(1, min(200, int(requested)))
    else:
        target = max(3, int(length_px / 80)) if is_x else max(3, int(length_px / 45))
    aux = 0.0
    if kind == "category":
        categories = axis.get("categories") or []
        if axis.get("theta_unit") is not None and requested is None:
            target = len(categories)
        rust_kind = 2
        aux = float(len(categories))
    elif axis.get("theta_unit") is not None:
        rust_kind = 3 if axis["theta_unit"] == "degrees" else 4
    elif axis.get("scale") == "log" or kind == "log":
        rust_kind = 1
    elif axis.get("scale") == "symlog":
        rust_kind = 6
        aux = float(axis.get("constant", 1.0))
    elif kind == "time":
        rust_kind = 5
    else:
        rust_kind = 0
    try:
        return _native.scene_axis_ticks(rust_kind, lo, hi, target, aux=aux)
    except ValueError:
        return [], [], _MS["d"] if rust_kind == 5 else 1.0


def minor_axis_ticks(axis: dict[str, Any]) -> list[float]:
    values = axis.get("minor_tick_values")
    if values is None:
        return []
    lo, hi = _tick_window(axis)
    return _tick_window_filter(axis, lo, hi, values, require_finite=True)


def _axis_tick_label_strategy(axis: dict[str, Any]) -> str:
    value = str(axis.get("tick_label_strategy") or "auto").replace("-", "_")
    return (
        value
        if value in {"auto", "hide", "rotate", "stagger", "preserve", "none", "off"}
        else "auto"
    )


def _axis_tick_font_size(axis: dict[str, Any]) -> float:
    style = axis.get("style") or {}
    default = 12 if style.get("_scene_public_chrome_defaults") else 11
    return max(8.0, float(style.get("tick_label_size", style.get("tick_size", default))))


def _axis_tick_geometry_authored(axis: dict[str, Any]) -> bool:
    """True when the axis authored tick geometry (label pad or mark length)."""
    style = axis.get("style") or {}
    if "tick_padding" in style:
        return True
    if "tick_length" not in style:
        return False
    return not (
        float(style.get("tick_length", 0)) == 0.0 and float(style.get("tick_width", 1)) == 0.0
    )


def _axis_tick_sides(axis: dict[str, Any], *, is_x: bool) -> list[str]:
    """Sides that paint tick marks, independent of the label-bearing side."""
    allowed = ("bottom", "top") if is_x else ("left", "right")
    authored = axis.get("tick_sides")
    if not isinstance(authored, list):
        return [axis.get("side", allowed[0])]
    return [side for side in allowed if side in authored]


def _axis_tick_label_sides(axis: dict[str, Any], *, is_x: bool) -> list[str]:
    """Sides that paint tick labels, independent of tick marks and titles."""
    allowed = ("bottom", "top") if is_x else ("left", "right")
    authored = axis.get("tick_label_sides")
    if not isinstance(authored, list):
        return [axis.get("side", allowed[0])]
    return [side for side in allowed if side in authored]


def _axis_tick_label_offset(axis: dict[str, Any], unstyled: float, font_room: float = 0.0) -> float:
    """Distance from the axis spine to a tick label's anchor point, in px."""
    if not _axis_tick_geometry_authored(axis):
        return unstyled
    style = axis.get("style") or {}
    length = max(0.0, float(style.get("tick_length", 0)))
    direction = str(style.get("tick_direction", "out"))
    outward = 0.0 if direction == "in" else length / 2 if direction == "inout" else length
    pad = outward + float(style.get("tick_padding", 4))
    return pad + _axis_tick_font_size(axis) * font_room


def _axis_tick_label_baseline_shift(axis: dict[str, Any]) -> float:
    """Baseline nudge that centers a y tick label on its tick, in px."""
    if not _axis_tick_geometry_authored(axis):
        return 4.0
    return _axis_tick_font_size(axis) * 0.35


def _axis_tick_label_layout(
    axis: dict[str, Any],
    values: list[float],
    step: float,
    scale: _Scale,
    is_x: bool,
) -> list[dict[str, Any]]:
    """Thin packer over Rust tick-label collision layout (ABI 123)."""
    strategy = _axis_tick_label_strategy(axis)
    font_size = _axis_tick_font_size(axis)
    min_gap = float(axis.get("tick_label_min_gap", 8 if is_x else 4))
    raw_angle = axis.get("tick_label_angle")
    explicit_angle = float(raw_angle) if raw_angle is not None else float("nan")
    axis_style = axis.get("style") or {}
    anchor = _tick_label_anchor(axis, axis_style, "center") if is_x else "center"
    positions = np.asarray(scale(values), dtype=np.float64)
    texts = [_tick_text(axis, value, step) for value in values]
    side_raw = str(axis.get("side") or "").strip().lower()
    side = side_raw if side_raw in {"bottom", "top", "left", "right"} else "bottom"
    kept = _native.scene_tick_label_layout(
        positions,
        texts,
        kind=strategy,
        side=side,
        anchor=anchor,
        is_x=is_x,
        category=axis.get("kind") == "category",
        font_size=font_size,
        min_gap=min_gap,
        explicit_angle=explicit_angle,
    )
    out: list[dict[str, Any]] = []
    for item in kept:
        index = int(item["index"])
        out.append(
            {
                "value": float(values[index]),
                "pos": float(positions[index]),
                "text": texts[index],
                "angle": float(item["angle"]),
                "row": int(item["row"]),
            }
        )
    return out


_TEXT = "rgba(32,32,32,0.85)"


def slot_styles(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """`styles={slot: {...}}` from the payload, normalized to kebab-case CSS."""
    raw = (spec.get("dom") or {}).get("styles") or {}
    out: dict[str, dict[str, Any]] = {}
    for slot, decls in raw.items():
        if not isinstance(decls, dict):
            continue
        out[str(slot)] = {
            (k if str(k).startswith("--") else str(k).replace("_", "-")): v
            for k, v in decls.items()
        }
    return out


def legend_items(traces: list[dict], palette: Sequence[str] = DEFAULT_PALETTE) -> list[dict]:
    """Legend rows for a trace list — shared by the SVG and raster exporters.

    A categorical `color=` channel is ONE trace carrying N categories, so the
    old `[t for t in traces if t.get("name")]` drew a single row bearing the
    trace's name and the trace's constant color: a legend that actively
    misdescribed the picture beside it. Expand those into one row per category,
    exactly as `ChartView._legend` does for the live client."""
    items: list[dict] = []
    for trace in traces:
        style = dict(trace.get("style") or {})
        use_trace_size = bool(style.pop("_legend_trace_size", False))
        size = trace.get("size") or {}
        if trace.get("kind") == "scatter" and use_trace_size and size.get("mode") == "constant":
            style["size"] = float(size.get("size", 8.0))
        color = trace.get("color") or {}
        if color.get("mode") == "categorical":
            categories = color.get("categories") or []
            entry_palette = list(color.get("palette") or palette) or list(palette)
            rows = _channels.palette_rows_rgba8(entry_palette, len(entry_palette))
            for index, category in enumerate(categories):
                item_style = dict(style)
                item_style["color"] = _rgba8_hex(rows[index % len(rows)])
                items.append(
                    {"name": str(category), "kind": trace.get("kind"), "style": item_style}
                )
        elif trace.get("name"):
            item = dict(trace)
            item["style"] = style
            items.append(item)
    return items


def _has_outside_y_title(axis: dict[str, Any]) -> bool:
    """Whether a y-axis title needs space outside the plot rectangle."""
    if not axis.get("label"):
        return False
    raw_position = axis.get("label_position")
    position = raw_position if isinstance(raw_position, str) else "center"
    return not position.replace("-", "_").startswith("inside_")


def _axis_text_paint_visible(
    axis: dict[str, Any],
    key: str,
    fallback_key: Optional[str] = None,
) -> bool:
    """Whether an axis text paint can contribute visible ink.

    Axis visibility shorthands are compiled to transparent CSS colors. Layout
    must not measure that invisible text back into an explicit zero padding,
    or ``show=False`` cannot produce the documented edge-to-edge sparkline.
    Unknown/browser-only paints stay conservative and reserve their room.
    """
    style = axis.get("style") or {}
    paint = style.get(key)
    if paint is None and fallback_key is not None:
        paint = style.get(fallback_key)
    if paint is None:
        return True
    return _paint_rgba8(_css(paint, _TEXT))[3] != 0


def _y_title_baseline(
    axis: dict[str, Any],
    plot: dict[str, float],
) -> Optional[float]:
    """Baseline x of a quarter-turned y-axis title, or None when it has none.

    Matplotlib positions a y title from the outer edge of the tick-label union,
    not from the canvas edge. A static exporter emits a baseline while the
    browser positions a centered line box; the returned coordinate includes
    that box-to-baseline correction.
    """
    if not _has_outside_y_title(axis):
        return None  # absent or drawn over the plot; it needs no gutter
    style = axis.get("style") or {}
    font_size = float(style.get("label_size", 12))
    side = axis.get("side", "left")
    block = _textblock.measure(axis["label"], font_size)
    ascent, descent = block.ascent, block.descent
    if side == "right":
        # Right-side axes still use the existing fixed 42/54 px reservation.
        # Keep their plot-relative placement unchanged; this repair only
        # measures the left gutter that can otherwise clip against x=0.
        angle = float(axis.get("label_angle", 90.0))
        shift = (ascent - descent) / 2 if abs(abs(angle) - 90.0) < 0.5 else 0.0
        return plot["x"] + plot["w"] + 40.0 - shift + float(axis.get("label_offset", 0.0))
    tick_offset, tick_room = (
        _y_tick_label_room(axis, plot["h"])
        if "left" in _axis_tick_label_sides(axis, is_x=False)
        else (0.0, 0.0)
    )
    gap = float(axis.get("label_offset", _Y_TITLE_TICK_GAP * font_size))
    # For a -90 degree title, later lines move toward the plot. Pin the first
    # baseline so the whole block, not only line one, remains outside ticks.
    title_depth = descent + (block.line_count - 1) * block.line_step
    return plot["x"] - tick_offset - tick_room - gap - title_depth


def _y_tick_label_room(axis: dict[str, Any], plot_h: float) -> tuple[float, float]:
    """(offset from the spine, widest tick-label extent) for a y axis, in px.

    Hosts still skip none/off/invisible axes, format `_tick_text`, and resolve
    the spine offset. The rotated DejaVu extent lives in Rust (ABI 125).
    """
    if _axis_tick_label_strategy(axis) in {"none", "off"} or not _axis_text_paint_visible(
        axis, "tick_label_color", "tick_color"
    ):
        return 0.0, 0.0
    font_size = _axis_tick_font_size(axis)
    raw_angle = axis.get("tick_label_angle")
    angle = float(raw_angle or 0.0)
    _values, labels, step = axis_ticks(axis, plot_h, False)
    texts = [_tick_text(axis, value, step) for value in labels]
    return _axis_tick_label_offset(axis, 8.0), float(
        _native.y_tick_label_extent(texts, font_size, angle)
    )


def _y_axis_left_room(spec: dict[str, Any], plot_h: float) -> float:
    """Left gutter the y-axis text needs, measured rather than assumed.

    `layout()`'s fixed 46/62 px default fits ordinary numeric ticks under a
    12 px title. Matplotlib's rcParam fonts (13.89 px at 100 dpi), long category
    names, and authored tick labels all exceed it, and the shortfall lands as a
    title drawn on top of the tick labels — or off the canvas — instead of as a
    wider gutter.

    Right-side y axes deliberately keep the flat 42/54 px reservation above:
    ChartView pins a right title plot-relative (`plot-right+40`) rather than to
    a canvas inset, so widening only the static exporters' right gutter would
    move their title away from the browser's. That asymmetry is recorded in
    `spec/api/styling.md`, not silently fixed here.

    Hosts still iterate axes, skip sides, and resolve CSS visibility. Column
    combination of title + tick ink lives in Rust (ABI 125) so SVG, raster, and
    pyplot cannot drift. `_y_tick_label_room` stays a host seam so tests can
    pin the once-per-axis tick measure.
    """
    room = 0.0
    for axis_id, axis in _axes_by_id(spec).items():
        if not axis_id.startswith("y"):
            continue
        left_labels = "left" in _axis_tick_label_sides(axis, is_x=False)
        left_title = axis.get("side", "left") != "right"
        if not left_labels and not left_title:
            continue
        tick_offset, tick_room = _y_tick_label_room(axis, plot_h) if left_labels else (0.0, 0.0)
        title_visible = (
            left_title
            and _has_outside_y_title(axis)
            and _axis_text_paint_visible(axis, "label_color")
        )
        title = str(axis.get("label") or "") if title_visible else ""
        label_size = float((axis.get("style") or {}).get("label_size", 12))
        gap = float(axis.get("label_offset", _Y_TITLE_TICK_GAP * label_size))
        room = max(
            room,
            float(_native.y_axis_left_room(tick_offset, tick_room, title, label_size, gap)),
        )
    return room


def _x_axis_title_room(axis: dict[str, Any]) -> float:
    """Outward room needed by an outside x-axis title.

    Hosts still skip inside/invisible titles. The baseline-conversion formula
    lives in Rust (ABI 125) so tight layout cannot stop at the historical
    36/42 px band while the title itself extends past the canvas.
    """
    if not axis.get("label") or not _axis_text_paint_visible(axis, "label_color"):
        return 0.0
    raw_position = axis.get("label_position")
    position = raw_position if isinstance(raw_position, str) else "center"
    if position.replace("-", "_").startswith("inside_"):
        return 0.0
    style = axis.get("style") or {}
    font_size = float(style.get("label_size", 12))
    offset = float(axis.get("label_offset", 0.0))
    return float(
        _native.x_axis_title_room(
            str(axis["label"]),
            font_size,
            offset,
            axis.get("side", "bottom") == "top",
        )
    )


def _x_tick_label_room(axis: dict[str, Any], plot_w: float) -> float:
    """Outward room needed by the x axis's final tick-label set and title.

    The old 32/42 px bands only fit horizontal labels. Hosts still keep the
    none/off/auto-horizontal shortcuts and call collision layout. The measured
    band combination lives in Rust (ABI 125).
    """
    strategy = _axis_tick_label_strategy(axis)
    if strategy == "none":
        return 0.0
    title_room = _x_axis_title_room(axis)
    if strategy == "off" or not _axis_text_paint_visible(axis, "tick_label_color", "tick_color"):
        return title_room
    if (
        strategy == "auto"
        and axis.get("tick_label_angle") is None
        and axis.get("tick_values") is None
        and axis.get("kind") != "category"
    ):
        # Numeric auto ticks are selected from the plot width and remain in the
        # established horizontal band. Only authored/category locations can
        # force rotation or staggering; avoid building and measuring the full
        # label layout merely to rediscover the ordinary zero-extra case. The
        # independently measured title can still exceed that fixed band.
        return title_room
    _ticks, values, step = axis_ticks(axis, plot_w, True)
    scale = _Scale(axis, 0.0, max(1.0, plot_w))
    items = _axis_tick_label_layout(axis, values, step, scale, True)
    if not items:
        return title_room
    has_adaptive_layout = any(float(item["angle"]) or int(item.get("row", 0)) for item in items)
    font_size = _axis_tick_font_size(axis)
    has_multiline_ticks = any(len(_textblock.split_lines(item["text"])) > 1 for item in items)
    if (
        not has_adaptive_layout
        and not has_multiline_ticks
        and strategy == "auto"
        and axis.get("tick_label_angle") is None
    ):
        # Preserve the long-standing flat band for ordinary horizontal text.
        # Measured bands are reserved for rotation, staggering, or multiline
        # chrome; ordinary auto ticks retain their historical geometry.
        return title_room
    side = axis.get("side", "bottom")
    label_offset = (
        _axis_tick_label_offset(axis, 7.0, 0.2)
        if side == "top"
        else _axis_tick_label_offset(axis, 16.0, 0.8)
    )
    return float(
        _native.x_tick_label_room(
            [item["text"] for item in items],
            [float(item["angle"]) for item in items],
            [int(item.get("row", 0)) for item in items],
            font_size,
            float(label_offset),
            title_room,
        )
    )


def _x_tick_label_edge_rooms(axes: dict[str, dict[str, Any]], plot_w: float) -> tuple[float, float]:
    """Canvas-edge room needed by x tick labels that overhang the plot.

    Hosts still skip none/off/invisible axes, format labels, and choose
    anchors. Per-axis rotated overhang lives in Rust (ABI 125).
    """
    left = right = 0.0
    for axis_id, axis in axes.items():
        if (
            not axis_id.startswith("x")
            or _axis_tick_label_strategy(axis) in {"none", "off"}
            or not _axis_text_paint_visible(axis, "tick_label_color", "tick_color")
        ):
            continue
        _ticks, values, step = axis_ticks(axis, plot_w, True)
        scale = _Scale(axis, 0.0, max(1.0, plot_w))
        font_size = _axis_tick_font_size(axis)
        explicit_anchor = _tick_label_anchor(axis, axis.get("style") or {}, "")
        for side in _axis_tick_label_sides(axis, is_x=True):
            side_axis = {**axis, "side": side}
            if (
                _axis_tick_label_strategy(axis) == "auto"
                and axis.get("tick_label_angle") is None
                and axis.get("tick_values") is None
                and axis.get("kind") != "category"
            ):
                items = [
                    {
                        "pos": float(scale(value)),
                        "text": _tick_text(axis, value, step),
                        "angle": 0.0,
                    }
                    for value in values
                ]
            else:
                items = _axis_tick_label_layout(side_axis, values, step, scale, True)
            if not items:
                continue
            anchors: list[str] = []
            for item in items:
                angle = float(item["angle"])
                anchor = explicit_anchor
                if not anchor:
                    if angle == 0:
                        anchor = "center"
                    elif (side == "bottom" and angle < 0) or (side == "top" and angle > 0):
                        anchor = "end"
                    else:
                        anchor = "start"
                anchors.append(str(anchor))
            left_i, right_i = _native.x_tick_label_edge_rooms(
                plot_w,
                [float(item["pos"]) for item in items],
                [str(item["text"]) for item in items],
                [float(item["angle"]) for item in items],
                anchors,
                font_size,
            )
            left = max(left, left_i)
            right = max(right, right_i)
    return float(left), float(right)


def _x_axis_rooms(
    axes: dict[str, dict[str, Any]], plot_w: float, compact: bool
) -> tuple[float, float, float]:
    """Shared ``(top, bottom, measured_bottom)`` x-axis bands.

    The fixed bottom band is metadata for colorbar placement.  It must not
    override an explicit figure ``padding`` authored by pyplot unless rotated
    or staggered labels actually require more room.
    """
    top = 0.0
    bottom = 0.0
    measured_bottom = 0.0
    for axis_id, axis in axes.items():
        if not axis_id.startswith("x") or _axis_tick_label_strategy(axis) == "none":
            continue
        title_side = axis.get("side", "bottom")
        room_sides = set(_axis_tick_label_sides(axis, is_x=True))
        if _axis_tick_label_strategy(axis) == "off" or axis.get("label"):
            room_sides.add(title_side)
        for side in room_sides:
            side_axis = {**axis, "side": side}
            if side != title_side:
                side_axis.pop("label", None)
            measured = _x_tick_label_room(side_axis, plot_w)
            room, measured_bottom_contrib = _native.compat_x_axis_side_room(
                compact, side == "top", measured
            )
            if side == "top":
                top = max(top, room)
            else:
                bottom = max(bottom, room)
                measured_bottom = max(measured_bottom, measured_bottom_contrib)
    return top, bottom, measured_bottom


def _title_entries(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalized independent axes-title slots, with legacy-title fallback."""
    authored = spec.get("title_options")
    if isinstance(authored, list) and authored:
        return [entry for entry in authored if isinstance(entry, dict) and entry.get("text")]
    if spec.get("title"):
        return [
            {
                "text": spec["title"],
                "loc": "center",
                "y": 1.0,
                "pad": 8.0,
                "automatic_y": True,
                "style": {},
            }
        ]
    return []


def _title_wrap_width(width: float, left: float, right: float) -> float:
    """Width a chart title wraps at, in CSS px.

    Thin packer over Rust ``xyg_compat_title_wrap_width`` (ABI 126).
    """
    return float(_native.compat_title_wrap_width(width, left, right))


def _title_metrics(
    spec: dict[str, Any],
    entry: dict[str, Any],
    wrap_width: float | None = None,
) -> tuple[dict[str, Any], float, _textblock.TextBlock]:
    base = slot_styles(spec).get("title") or {}
    style = {**base, **(entry.get("style") or {})}
    size = _px_size(style.get("font-size"), 14.0)
    return style, size, _textblock.measure(entry["text"], size, max_width=wrap_width)


def _title_room(spec: dict[str, Any], compact: bool, wrap_width: float | None = None) -> float:
    room = 0.0
    for entry in _title_entries(spec):
        _style, _size, block = _title_metrics(spec, entry, wrap_width)
        pad = float(entry.get("pad", 8.0))
        room = max(
            room,
            float(
                _native.compat_title_room(
                    compact,
                    block.height,
                    pad,
                    bool(entry.get("automatic_y", True)),
                    float(entry.get("y", 1.0)),
                )
            ),
        )
    return room


def _spec_has_custom_font(spec: dict[str, Any]) -> bool:
    """Whether chrome CSS asks for a face Scene cannot encode.

    Custom `font-family` stays fail-closed on Scene (#288 / #297). Measuring
    those figures with DejaVu would be a silent substitute.
    """
    for style in slot_styles(spec).values():
        family = style.get("font-family")
        if family not in (None, "", "DejaVu Sans"):
            return True
    for style in (spec.get("chrome_styles") or {}).values():
        if not isinstance(style, dict):
            continue
        family = style.get("font-family") or style.get("font_family")
        if family not in (None, "", "DejaVu Sans"):
            return True
    return False


def _scene_axis_pack(axis: dict[str, Any]) -> tuple[int, float, float, float, bool] | None:
    """Pack one primary cartesian axis for `xyg_scene_plot_layout`, or None."""
    kind = str(axis.get("scale") or axis.get("kind") or "linear")
    code = _SCENE_SCALE_KINDS.get(kind)
    if code is None:
        return None
    domain = axis.get("domain") or axis.get("range")
    if domain is None or len(domain) != 2:
        return None
    lo, hi = float(domain[0]), float(domain[1])
    constant = float(axis.get("linthresh") or axis.get("constant") or 1.0)
    mask = str(axis.get("nonpositive") or "") == "mask"
    return code, lo, hi, constant, mask


def scene_layout_rooms(
    spec: dict[str, Any],
) -> tuple[float, float, float, float] | None:
    """Rust cartesian gutters for default-font Scene-shaped specs (#297).

    Returns ``(left, right, top, bottom)`` from `xyg_scene_plot_layout` when the
    spec is primary cartesian linear/log/symlog with the default face.
    Polar, extra axes, top/right primary sides, outside legends, in-axes
    colorbars, category scales, and custom `font-family` return None so
    callers keep compatibility `_layout._*room` instead of a DejaVu substitute.
    """
    if spec.get("coords") not in (None, "cartesian"):
        return None
    if _spec_has_custom_font(spec):
        return None
    axes = _axes_by_id(spec)
    extra = [axis_id for axis_id in axes if axis_id not in {"x", "y"}]
    if extra:
        return None
    if axes["x"].get("side", "bottom") == "top" or axes["y"].get("side", "left") == "right":
        return None
    legend = spec.get("legend") or {}
    loc = str(legend.get("loc") or "")
    if spec.get("show_legend") and "outside" in loc:
        return None
    x_pack = _scene_axis_pack(axes["x"])
    y_pack = _scene_axis_pack(axes["y"])
    if x_pack is None or y_pack is None:
        return None
    width = spec.get("width")
    height = spec.get("height")
    width = 900 if not isinstance(width, (int, float)) else float(width)
    height = 420 if not isinstance(height, (int, float)) else float(height)
    pad = spec.get("padding")
    padding = None
    if isinstance(pad, list) and len(pad) == 4:
        padding = (float(pad[0]), float(pad[1]), float(pad[2]), float(pad[3]))
    entries = _title_entries(spec)
    title = str(entries[0]["text"]) if len(entries) == 1 else ""
    if len(entries) > 1:
        return None
    colorbar = spec.get("colorbar") or {}
    if colorbar.get("placement") == "axes":
        return None
    side = None
    if colorbar:
        side = "bottom" if colorbar.get("orientation") == "horizontal" else "right"
    x_format = axes["x"].get("format") or axes["x"].get("tick_format")
    y_format = axes["y"].get("format") or axes["y"].get("tick_format")
    try:
        return _native.scene_plot_layout(
            viewport=(width, height),
            x_axis=x_pack,
            y_axis=y_pack,
            title=title,
            x_label=str(axes["x"].get("label") or ""),
            y_label=str(axes["y"].get("label") or ""),
            x_format=str(x_format) if x_format else None,
            y_format=str(y_format) if y_format else None,
            padding=padding,
            colorbar_side=side,
        )
    except (TypeError, ValueError):
        return None


def layout(spec: dict[str, Any]) -> tuple[int, int, bool, dict[str, float]]:
    """Concrete pixel dimensions + plot rect from a spec — shared by the SVG and
    native-PNG exporters so their chrome/plot geometry stays identical.

    Hosts still iterate axes, format ticks, measure ABI 125 rooms, resolve CSS
    visibility, and decide polar legend reservation. Padding, title-band,
    colorbar extra, right-y, floors, and polar recut combination live in Rust
    (ABI 198).
    """
    width = spec.get("width")
    height = spec.get("height")
    # Fluid ("100%") figures need concrete export dimensions.
    width = 900 if not isinstance(width, (int, float)) else int(width)
    height = 420 if not isinstance(height, (int, float)) else int(height)

    compact = _native.compat_is_compact(width)
    pad = spec.get("padding")
    authored: tuple[float, float, float, float] | None
    if isinstance(pad, list) and len(pad) == 4:
        authored = (float(pad[0]), float(pad[1]), float(pad[2]), float(pad[3]))
        right, left = authored[1], authored[3]
    else:
        authored = None
        _, right, _, left = _native.compat_default_padding(compact)

    axes = _axes_by_id(spec)
    provisional_w = max(40.0, width - left - right)
    title_wrap_width = _title_wrap_width(width, left, right)
    title_room = _title_room(spec, compact, title_wrap_width)
    x_top_room, x_bottom_room, measured_bottom_room = _x_axis_rooms(axes, provisional_w, compact)
    colorbar = spec.get("colorbar") or {}
    if colorbar:
        if colorbar.get("placement") == "axes":
            colorbar_kind = (
                "axes_horizontal"
                if colorbar.get("orientation") == "horizontal"
                else "axes_vertical"
            )
        elif colorbar.get("orientation") == "horizontal":
            colorbar_kind = "figure_horizontal"
        else:
            colorbar_kind = "figure_vertical"
    else:
        colorbar_kind = "none"
    has_right_y = any(
        axis_id.startswith("y")
        and (
            axis.get("side", "right") == "right"
            or "right" in _axis_tick_label_sides(axis, is_x=False)
        )
        and _axis_tick_label_strategy(axis) != "none"
        for axis_id, axis in axes.items()
    )
    combine_kw: dict[str, Any] = {
        "authored_padding": authored,
        "title_room": title_room,
        "x_top_room": x_top_room,
        "x_bottom_room": x_bottom_room,
        "x_measured_bottom": measured_bottom_room,
        "colorbar_kind": colorbar_kind,
        "colorbar_has_label": bool(colorbar.get("label")),
        "colorbar_pad_zero": colorbar.get("pad") == 0,
        "has_right_y": has_right_y,
    }
    preview = _native.compat_combine_plot(width, height, **combine_kw)
    y_left = _y_axis_left_room(spec, preview["h"])
    mid = _native.compat_combine_plot(width, height, y_left_room=y_left, **combine_kw)
    left = mid["x"]
    right = width - mid["x"] - mid["w"]
    for _pass in range(2):
        edge_left, edge_right = _x_tick_label_edge_rooms(
            axes,
            max(40.0, width - left - right),
        )
        widened_left = max(left, edge_left)
        widened_right = max(right, edge_right)
        if widened_left == left and widened_right == right:
            break
        left, right = widened_left, widened_right
    final_w = max(40.0, width - left - right)
    if final_w == provisional_w:
        x_final = (x_top_room, x_bottom_room, measured_bottom_room)
    else:
        x_final = _x_axis_rooms(axes, final_w, compact)
    polar_kw = None
    if spec.get("coords") == "polar":
        polar_kw = _polar_combine_args(spec, width, compact)
    plot = _native.compat_combine_plot(
        width,
        height,
        y_left_room=y_left,
        edge_left=left,
        edge_right=right,
        x_rooms_final=x_final,
        polar=polar_kw,
        **combine_kw,
    )
    return width, height, compact, plot


def _polar_combine_args(spec: dict[str, Any], width: float, compact: bool) -> dict[str, Any]:
    """Host polar-recut observations for ``compat_combine_plot``."""
    theta_axis = spec.get("x_axis") or {}
    labels_hidden = theta_axis.get("tick_label_strategy") == "none"
    legend_side, legend_room = _polar_legend_reserve(spec, compact, width)
    room = 0.0 if labels_hidden else _polar_label_room(theta_axis)
    authored_pad = spec.get("padding")
    y_axis = spec.get("y_axis") or {}
    titled = bool(y_axis.get("label")) and _axis_text_paint_visible(y_axis, "label_color")
    x_axis = spec.get("x_axis") or {}
    x_titled = bool(x_axis.get("label")) and _axis_text_paint_visible(x_axis, "label_color")
    colorbar = spec.get("colorbar") or {}
    return {
        "legend_side": legend_side,
        "legend_room": legend_room,
        "polar_label_room": room,
        "authored_padding": isinstance(authored_pad, list) and len(authored_pad) == 4,
        "y_titled": titled,
        "keeps_bottom": x_titled or colorbar.get("orientation") == "horizontal",
    }


# Room reserved outside the outer ring for angular tick labels. Cartesian
# gutters are per-side because labels hug two edges; a polar chart carries them
# all the way around, so the allowance is uniform. The floor/ceiling live in
# Rust (`compat_layout::POLAR_LABEL_ROOM` / `POLAR_LABEL_ROOM_MAX`, ABI 126).
# Mirrored by POLAR_LABEL_ROOM in js/src/50_chartview.ts.

#: Uniform allowance around a disc for angular tick labels (px). The
#: floor/ceiling live in Rust (`compat_layout::POLAR_LABEL_ROOM`, ABI 126).
#: Mirrored by POLAR_LABEL_ROOM in js/src/50_chartview.ts.
_POLAR_LABEL_ROOM = 30.0

#: Gutter band reserved for a legend beside a disc. The fraction/clamp live in
#: Rust (`compat_layout::polar_legend_room`, ABI 126); mirrored by
#: xyPolarLegendRoom in js/src/50_chartview.ts.
_POLAR_LEGEND_BAND = 64.0


def _polar_legend_room(width: float) -> float:
    """Side-gutter width for a polar legend on a `width`-px canvas.

    Thin packer over Rust ``xyg_polar_legend_room`` (ABI 126).
    """
    return float(_native.polar_legend_room(width))


def _polar_legend_reserve(spec: dict[str, Any], compact: bool, width: float) -> tuple[str, float]:
    """Side and px a polar legend gutter claims: ``("right", 158.0)`` etc.

    ``("", 0.0)`` when nothing is reserved — a non-polar figure, no legend rows,
    an authored ``anchor`` (an explicit plot-relative placement the author owns),
    or an authored 4-tuple ``padding`` (which already states the box the plot
    should occupy, and is the documented way to hand-reserve a caption band).

    Mirrored by `_polarLegendReserve` in js/src/50_chartview.ts.
    """
    if spec.get("coords") != "polar" or not spec.get("show_legend", True):
        return "", 0.0
    padding = spec.get("padding")
    if isinstance(padding, list) and len(padding) == 4:
        return "", 0.0
    options = spec.get("legend") or {}
    anchor = options.get("anchor")
    if anchor and len(anchor) in (2, 4):
        return "", 0.0
    rows = options.get("items") or legend_items(spec.get("traces") or [])
    if not rows and not (spec.get("extra_legends") or []):
        return "", 0.0
    loc = str(options.get("loc") or "upper right")
    return _native.polar_legend_reserve(compact, "left" in loc, width)


def _polar_label_room(theta_axis: dict[str, Any]) -> float:
    """Room outside the ring for the angular tick labels.

    Measured, not fixed: authored category names ("EAST-NORTH-EAST") are far
    wider than an angle, and a constant allowance hard-clipped them at the
    canvas edge. Only the widest AUTHORED label is measured — generated angle
    text is bounded and already fits the floor — and the result is capped so a
    pathological label shrinks the disc rather than erasing it.

    Mirrored by `polarLabelRoom` in js/src/50_chartview.ts.
    """
    labels = theta_axis.get("tick_labels")
    if not labels and theta_axis.get("kind") == "category":
        labels = theta_axis.get("categories")
    if not labels:
        return float(_native.polar_label_room(None))
    size = _axis_tick_font_size(theta_axis)
    widest = max((_textblock.measure(str(text), size).width for text in labels), default=0.0)
    return float(_native.polar_label_room(widest))
