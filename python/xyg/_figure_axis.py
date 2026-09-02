"""Figure axis configuration, resolution, and payload spec assembly."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from . import _validate, kernels, styles

if TYPE_CHECKING:
    from ._figure import Figure
    from ._trace import Trace
    from .columns import Column


def set_axis(
    self,
    axis_id: str,
    *,
    label: Optional[str] = None,
    label_position: Optional[Any] = None,
    label_offset: Optional[float] = None,
    label_angle: Optional[float] = None,
    type_: Optional[str] = None,
    constant: Optional[float] = None,
    domain: Optional[tuple[float, float]] = None,
    margin: Optional[float] = None,
    bounds: Any = None,
    reverse: bool = False,
    format: Optional[str] = None,
    tick_count: Optional[int] = None,
    tick_values: Optional[Any] = None,
    minor_tick_values: Optional[Any] = None,
    tick_labels: Optional[Any] = None,
    tick_label_angle: Optional[float] = None,
    tick_label_strategy: Optional[str] = None,
    tick_label_anchor: Optional[str] = None,
    tick_label_min_gap: Optional[float] = None,
    side: Optional[str] = None,
    tick_sides: Optional[Any] = None,
    tick_label_sides: Optional[Any] = None,
    style: Optional[dict[str, Any]] = None,
    minor_style: Optional[dict[str, Any]] = None,
    nonpositive: Optional[str] = None,
    theta_unit: Optional[str] = None,
    theta_zero: Optional[Any] = None,
    theta_direction: Optional[str] = None,
    sector: Optional[tuple[float, float]] = None,
    grid_shape: Optional[str] = None,
    hole: Optional[float] = None,
    r_origin: Optional[float] = None,
) -> "Figure":
    axis_id = self._axis_id(axis_id, "axis id")
    axis_dim = self._axis_dim(axis_id)
    if type_ is not None and type_ not in {"linear", "time", "log", "symlog"}:
        raise ValueError("axis type_ must be one of None, 'linear', 'time', 'log', or 'symlog'")
    if constant is not None:
        constant = self._finite_scalar(constant, f"{axis_id} axis constant")
        if constant <= 0:
            raise ValueError(f"{axis_id} axis constant must be positive")
        if type_ != "symlog":
            raise ValueError(f"{axis_id} axis constant is only valid for a symlog axis")
    if domain is not None:
        domain = self._finite_increasing_pair(domain, f"{axis_id} axis domain")
        if type_ == "log" and domain[0] <= 0:
            raise ValueError(f"{axis_id} log axis domain must be positive")
    if margin is not None:
        margin = self._nonnegative_scalar(margin, f"{axis_id} axis margin")
    if isinstance(bounds, str):
        if bounds != "data":
            raise ValueError(f"{axis_id} axis bounds must be an increasing pair or 'data'")
    elif bounds is not None:
        bounds = self._finite_increasing_pair(bounds, f"{axis_id} axis bounds")
        if type_ == "log" and bounds[0] <= 0:
            raise ValueError(f"{axis_id} log axis bounds must be positive")
    if theta_unit is not None:
        theta_unit = _validate.theta_unit(theta_unit, f"{axis_id} axis theta_unit")
    if theta_direction is not None:
        theta_direction = _validate.theta_direction(
            theta_direction, f"{axis_id} axis theta_direction"
        )
    if theta_zero is not None:
        theta_zero = _validate.theta_zero(theta_zero, f"{axis_id} axis theta_zero")
    if sector is not None:
        sector = _validate.theta_sector(sector, f"{axis_id} axis sector")
    if grid_shape is not None:
        grid_shape = _validate.polar_grid_shape(grid_shape, f"{axis_id} axis grid_shape")
    if hole is not None:
        hole = _validate.polar_hole(hole, f"{axis_id} axis hole")
    if r_origin is not None:
        r_origin = self._finite_scalar(r_origin, f"{axis_id} axis r_origin")
    if hole is not None and r_origin is not None:
        raise ValueError(f"{axis_id} axis hole and r_origin are mutually exclusive")
    if axis_dim == "y" and any(
        option is not None
        for option in (theta_unit, theta_direction, theta_zero, sector, grid_shape)
    ):
        raise ValueError(
            f"{axis_id} axis: theta options describe the angular "
            "axis and belong on an x axis (xyg.theta_axis); the radial axis is the y axis"
        )
    if axis_dim == "x" and any(option is not None for option in (hole, r_origin)):
        raise ValueError(
            f"{axis_id} axis: hole/r_origin describe the radial axis and belong on a "
            "y axis (xyg.r_axis); the angular axis is the x axis"
        )
    if type_ == "log" and r_origin is not None and r_origin <= 0:
        raise ValueError(f"{axis_id} log axis r_origin must be positive")
    if sector is not None and self.coords == "polar":
        unit = theta_unit or "radians"
        turn = 360.0 if unit == "degrees" else 2.0 * math.pi
        if sector[1] - sector[0] > turn:
            raise ValueError(
                f"{axis_id} axis sector sweep must not exceed one full turn ({turn:g} {unit})"
            )
    if side is None:
        side = "bottom" if axis_dim == "x" else ("right" if axis_id != "y" else "left")
    elif axis_dim == "x" and side not in {"top", "bottom"}:
        raise ValueError("x axis side must be 'top' or 'bottom'")
    elif axis_dim == "y" and side not in {"left", "right"}:
        raise ValueError("y axis side must be 'left' or 'right'")
    if tick_sides is not None:
        if isinstance(tick_sides, (str, bytes)) or not isinstance(tick_sides, Sequence):
            raise ValueError(f"{axis_id} axis tick_sides must be a sequence")
        allowed_tick_sides = ("bottom", "top") if axis_dim == "x" else ("left", "right")
        tick_sides = list(tick_sides)
        if any(value not in allowed_tick_sides for value in tick_sides):
            raise ValueError(
                f"{axis_id} axis tick_sides must contain only {list(allowed_tick_sides)}"
            )
        tick_sides = [value for value in allowed_tick_sides if value in tick_sides]
    if tick_label_sides is not None:
        if isinstance(tick_label_sides, (str, bytes)) or not isinstance(tick_label_sides, Sequence):
            raise ValueError(f"{axis_id} axis tick_label_sides must be a sequence")
        allowed_label_sides = ("bottom", "top") if axis_dim == "x" else ("left", "right")
        tick_label_sides = list(tick_label_sides)
        if any(value not in allowed_label_sides for value in tick_label_sides):
            raise ValueError(
                f"{axis_id} axis tick_label_sides must contain only {list(allowed_label_sides)}"
            )
        tick_label_sides = [value for value in allowed_label_sides if value in tick_label_sides]
    values = (
        None
        if tick_values is None
        else [self._finite_scalar(value, f"{axis_id} tick value") for value in tick_values]
    )
    minor_values = (
        None
        if minor_tick_values is None
        else [
            self._finite_scalar(value, f"{axis_id} minor tick value") for value in minor_tick_values
        ]
    )
    if nonpositive is not None and (type_ != "log" or nonpositive not in {"clip", "mask"}):
        raise ValueError(f"{axis_id} axis nonpositive must be 'clip' or 'mask' on a log axis")
    labels = None if tick_labels is None else [str(value) for value in tick_labels]
    if labels is not None and (values is None or len(labels) != len(values)):
        raise ValueError(f"{axis_id} tick_labels must match tick_values")
    self.axis_options[axis_id] = {
        "label": self._optional_text(label, f"{axis_id} axis label"),
        "label_position": self._axis_label_position(
            label_position, f"{axis_id} axis label_position"
        ),
        "label_offset": self._optional_finite_scalar(label_offset, f"{axis_id} axis label_offset"),
        "label_angle": self._optional_finite_scalar(label_angle, f"{axis_id} axis label_angle"),
        "type": type_,
        "constant": constant,
        "domain": domain,
        "margin": margin,
        "bounds": bounds,
        "reverse": self._bool_param(reverse, f"{axis_id} axis reverse"),
        "format": self._optional_text(format, f"{axis_id} axis format"),
        "tick_count": self._optional_positive_int(tick_count, f"{axis_id} axis tick_count"),
        "tick_values": values,
        "minor_tick_values": minor_values,
        "tick_labels": labels,
        "tick_label_angle": self._optional_finite_scalar(
            tick_label_angle, f"{axis_id} axis tick_label_angle"
        ),
        "tick_label_strategy": self._axis_tick_label_strategy(
            tick_label_strategy, f"{axis_id} axis tick_label_strategy"
        ),
        "tick_label_anchor": self._axis_tick_label_anchor(
            tick_label_anchor, f"{axis_id} axis tick_label_anchor"
        ),
        "tick_label_min_gap": None
        if tick_label_min_gap is None
        else self._nonnegative_scalar(tick_label_min_gap, f"{axis_id} axis tick_label_min_gap"),
        "side": side,
        "tick_sides": tick_sides,
        "tick_label_sides": tick_label_sides,
        "style": styles.compile_axis_style(style, f"{axis_id} axis style"),
        "minor_style": styles.compile_axis_style(minor_style, f"{axis_id} minor axis style"),
        "nonpositive": nonpositive,
        # Polar angular configuration. Meaningless on a cartesian chart and
        # omitted from the wire there, so existing specs stay byte-identical.
        "theta_unit": theta_unit,
        "theta_zero": theta_zero,
        "theta_direction": theta_direction,
        "sector": sector,
        "grid_shape": grid_shape,
        "hole": hole,
        "r_origin": r_origin,
    }
    if axis_id == "x":
        self.x_label = self.axis_options[axis_id]["label"]
    elif axis_id == "y":
        self.y_label = self.axis_options[axis_id]["label"]
    return self


def _set_axis_domain(self, axis_id: str, domain: tuple[float, float]) -> "Figure":
    """Update only an axis domain, preserving every other configured option.

    Facet domain sharing must not reset `type_`/`label`/`reverse`/`format`/
    tick options the way a full `set_axis` replay from defaults would.
    """
    axis_id = self._axis_id(axis_id, "axis id")
    opts = self.axis_options.setdefault(axis_id, {})
    domain = self._finite_increasing_pair(domain, f"{axis_id} axis domain")
    if opts.get("type") == "log" and domain[0] <= 0:
        raise ValueError(f"{axis_id} log axis domain must be positive")
    opts["domain"] = domain
    return self


def _axis_dim(axis_id: str) -> str:
    return "x" if axis_id.startswith("x") else "y"


def _axis_policy(self, value: Any, name: str) -> list[str]:
    if not isinstance(value, (tuple, list)):
        raise ValueError(f"interaction {name} must be a tuple/list of declared axis IDs")
    axes = list(value)
    if not axes:
        raise ValueError(f"interaction {name} must contain at least one axis")
    unknown = [axis for axis in axes if axis not in self.axis_options]
    if unknown:
        raise ValueError(
            f"interaction {name} contains unknown axis IDs {unknown!r}; "
            f"declared axes are {list(self.axis_options)!r}"
        )
    out: list[str] = []
    for axis in axes:
        if axis not in out:
            out.append(axis)
    return out


def _axis_scale(self, axis_id: str) -> str:
    scale = self.axis_options.get(axis_id, {}).get("type")
    return scale if scale in {"log", "symlog"} else "linear"


def _axis_coord(self, axis_id: str, values: Any) -> np.ndarray:
    """Map values to axis coordinates for screen-space aggregation."""
    v = np.asarray(values, dtype=np.float64)
    scale = self._axis_scale(axis_id)
    if scale == "log":
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(v > 0.0, np.log10(v), np.nan)
    if scale == "symlog":
        constant = float(self.axis_options.get(axis_id, {}).get("constant") or 1.0)
        return np.sign(v) * np.log1p(np.abs(v) / constant)
    return v


def _axis_kind(self, axis_id: str) -> str:
    axis = self._axis_dim(axis_id)
    forced = self.axis_options.get(axis_id, {}).get("type")
    if forced == "time":
        return "time"
    if axis_id in self._axis_categories:
        return "category"
    for t in self.traces:
        if axis == "x" and t.x_axis != axis_id:
            continue
        if axis == "y" and t.y_axis != axis_id:
            continue
        col = t.x if axis == "x" else t.y
        if col.kind == "time_ms":
            return "time"
    return "linear"


def _axis_spec(self, axis_id: str, range_: tuple[float, float]) -> dict[str, Any]:
    axis = self._axis_dim(axis_id)
    opts = self.axis_options.get(axis_id, {})
    attach = kernels.payload_axis_spec_attach_plan(
        coords_cartesian=self.coords == "cartesian",
        axis_is_x=axis == "x",
    )
    if axis_id == "x":
        label = self.x_label
    elif axis_id == "y":
        label = self.y_label
    else:
        label = opts.get("label")
    label = self._optional_text(label, f"{axis}_label")
    label_position = self._axis_label_position(
        opts.get("label_position"), f"{axis_id} axis label_position"
    )
    label_offset = self._optional_finite_scalar(
        opts.get("label_offset"), f"{axis_id} axis label_offset"
    )
    label_angle = self._optional_finite_scalar(
        opts.get("label_angle"), f"{axis_id} axis label_angle"
    )
    tick_count = self._optional_positive_int(opts.get("tick_count"), f"{axis_id} axis tick_count")
    tick_label_angle = self._optional_finite_scalar(
        opts.get("tick_label_angle"), f"{axis_id} axis tick_label_angle"
    )
    tick_label_strategy = self._axis_tick_label_strategy(
        opts.get("tick_label_strategy"), f"{axis_id} axis tick_label_strategy"
    )
    tick_label_anchor = self._axis_tick_label_anchor(
        opts.get("tick_label_anchor"), f"{axis_id} axis tick_label_anchor"
    )
    tick_label_min_gap = (
        None
        if opts.get("tick_label_min_gap") is None
        else self._nonnegative_scalar(
            opts.get("tick_label_min_gap"), f"{axis_id} axis tick_label_min_gap"
        )
    )
    kind = self._axis_kind(axis_id)
    spec: dict[str, Any] = {}
    if attach["attach_id"]:
        spec["id"] = axis_id
    if attach["attach_kind"]:
        spec["kind"] = kind
    if attach["attach_label"]:
        spec["label"] = label
    if attach["attach_range"]:
        spec["range"] = list(range_)
    if attach["attach_side"]:
        spec["side"] = opts.get("side", "bottom" if axis == "x" else "left")
    if attach["attach_tick_sides"] and opts.get("tick_sides") is not None:
        spec["tick_sides"] = list(opts["tick_sides"])
    if attach["attach_tick_label_sides"] and opts.get("tick_label_sides") is not None:
        spec["tick_label_sides"] = list(opts["tick_label_sides"])
    if attach["attach_label_position"] and label_position is not None:
        spec["label_position"] = label_position
    if attach["attach_label_offset"] and label_offset is not None:
        spec["label_offset"] = label_offset
    if attach["attach_label_angle"] and label_angle is not None:
        spec["label_angle"] = label_angle
    if attach["attach_ticks"] and tick_count is not None:
        spec["tick_count"] = tick_count
    if attach["attach_ticks"] and opts.get("tick_values") is not None:
        spec["tick_values"] = list(opts["tick_values"])
    if attach["attach_ticks"] and opts.get("minor_tick_values") is not None:
        spec["minor_tick_values"] = list(opts["minor_tick_values"])
    if attach["attach_ticks"] and opts.get("tick_labels") is not None:
        spec["tick_labels"] = list(opts["tick_labels"])
    if attach["attach_tick_label_angle"] and tick_label_angle is not None:
        spec["tick_label_angle"] = tick_label_angle
    if attach["attach_tick_label_strategy"] and tick_label_strategy is not None:
        spec["tick_label_strategy"] = tick_label_strategy
    if attach["attach_tick_label_anchor"] and tick_label_anchor is not None:
        spec["tick_label_anchor"] = tick_label_anchor
    if attach["attach_tick_label_min_gap"] and tick_label_min_gap is not None:
        spec["tick_label_min_gap"] = tick_label_min_gap
    scale = self._axis_scale(axis_id)
    if attach["attach_scale"] and scale != "linear":
        spec["scale"] = scale
    if attach["attach_constant"] and scale == "symlog":
        spec["constant"] = opts.get("constant") or 1.0
    if attach["attach_nonpositive"] and scale == "log" and opts.get("nonpositive") is not None:
        spec["nonpositive"] = opts["nonpositive"]
    if attach["attach_reverse"] and opts.get("reverse"):
        spec["reverse"] = True
    if attach["attach_domain"] and opts.get("domain") is not None:
        spec["domain"] = list(opts["domain"])
    bounds = opts.get("bounds")
    if bounds == "data":
        # Resolve once on the Python side so the client receives concrete
        # limits even when an independent explicit domain sets view0.
        bounds = self._range(axis_id, use_domain=False)
    if attach["attach_bounds"] and bounds is not None:
        spec["bounds"] = sorted(bounds)
    if attach["attach_minor_style"] and opts.get("minor_style"):
        spec["minor_style"] = dict(opts["minor_style"])
    if attach["attach_format"] and opts.get("format") is not None:
        spec["format"] = opts["format"]
    style = styles.compile_axis_style(opts.get("style"), f"{axis_id} axis style")
    if attach["attach_style"] and style:
        spec["style"] = style
    if attach["attach_categories"] and kind == "category":
        spec["categories"] = list(self._axis_categories.get(axis_id, []))
    if attach["attach_theta_unit"]:
        # Angular configuration rides the x (theta) axis. Defaults are
        # spelled out rather than omitted so the client and both exporters
        # read one resolved value instead of each re-deriving a fallback.
        unit = opts.get("theta_unit") or "radians"
        spec["theta_unit"] = unit
        if attach["attach_theta_zero"]:
            spec["theta_zero"] = "E" if opts.get("theta_zero") is None else opts["theta_zero"]
        if attach["attach_theta_direction"]:
            spec["theta_direction"] = opts.get("theta_direction") or "counterclockwise"
        if attach["attach_sector"]:
            turn = 360.0 if unit == "degrees" else 2.0 * math.pi
            spec["sector"] = list(opts.get("sector") or (0.0, turn))
        if attach["attach_grid_shape"]:
            spec["grid_shape"] = opts.get("grid_shape") or "circular"
    if attach["attach_hole"]:
        # `hole` is always resolved on the wire. `r_origin` stays optional:
        # when absent, renderers use the current visible r_lo, so radial
        # zoom keeps the ordinary centre origin without a spec rewrite.
        spec["hole"] = opts.get("hole") or 0.0
        if attach["attach_r_origin"] and opts.get("r_origin") is not None:
            spec["r_origin"] = opts["r_origin"]
    return spec


def _range_columns(self, t: Trace, axis_id: str) -> list[Column]:
    axis = self._axis_dim(axis_id)
    if axis == "x" and t.x_axis != axis_id:
        return []
    if axis == "y" and t.y_axis != axis_id:
        return []
    if t.kind in {"area", "error_band"} and t.base is not None:
        return [t.x] if axis == "x" else [t.y, t.base]
    if (
        t.kind == "triangle_mesh"
        and t.x0 is not None
        and t.x1 is not None
        and t.y0 is not None
        and t.y1 is not None
    ):
        return [t.x0, t.x1, t.x] if axis == "x" else [t.y0, t.y1, t.y]
    if t.kind == "ribbon":
        # x is just the two faces; y needs all four span edges, two of
        # which ride in the `x`/`y` slots (ribbon geometry contract).
        if t.x0 is None or t.x1 is None or t.y0 is None or t.y1 is None:
            raise ValueError("ribbon trace missing geometry columns")
        return [t.x0, t.x1] if axis == "x" else [t.y0, t.y1, t.x, t.y]
    if t.x0 is not None and t.x1 is not None and t.y0 is not None and t.y1 is not None:
        return [t.x0, t.x1] if axis == "x" else [t.y0, t.y1]
    return [t.x if axis == "x" else t.y]
