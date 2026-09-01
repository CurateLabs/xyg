"""Shared static-export scale and polar projection helpers."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, Optional

import numpy as np

from . import _native


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
