"""LOD tier planning and aggregation grid sizing."""

from __future__ import annotations

import numpy as np

from . import kernels
from ._lod_params import _float_param, _integer_param
from ._lod_types import LodPlan
from ._lod_viewport import ViewportRequest, screen_shape
from .config import DENSITY_TARGET_POINTS_PER_CELL, DRILL_EXIT_FACTOR


def drill_decision(
    visible: int, budget: float, in_drill: bool, exit_factor: float = DRILL_EXIT_FACTOR
) -> bool:
    """The render tier is a function of the *visible* point count (design
    dossier §5), hysteresis-guarded — once drilled down to real points, stay
    until the count clearly exceeds the budget again.

    Decision math lives in Rust (`xy_drill_decision`); this host only coerces
    arguments.
    """
    return bool(kernels.drill_decision(visible, budget, in_drill, exit_factor))


def plan_view_lod(
    request: ViewportRequest,
    visible: object,
    budget: object,
    in_drill: bool,
    *,
    direct_mode: str = "points",
    aggregate_mode: str = "density",
    aggregate_reduction: str = "count",
    target_per_cell: float = DENSITY_TARGET_POINTS_PER_CELL,
    exit_factor: float = DRILL_EXIT_FACTOR,
) -> LodPlan:
    """Build the reusable tier decision for a viewport.

    The exact-vs-aggregate decision is common across tiered chart kinds; the
    representation names differ. Scatter passes `points`/`density`, while
    future histograms or candlesticks can pass `bins`/`ohlc-buckets` without
    reimplementing validation, hysteresis, or screen-bounded grid sizing.
    """
    visible_i = _integer_param(visible, "visible")
    budget_f = _float_param(budget, "LOD budget", min_exclusive=0.0)
    if not isinstance(in_drill, (bool, np.bool_)):
        raise ValueError("in_drill must be True or False")
    for value, label in (
        (direct_mode, "direct_mode"),
        (aggregate_mode, "aggregate_mode"),
        (aggregate_reduction, "aggregate_reduction"),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(f"{label} must be a non-empty string")
    exit_f = _float_param(exit_factor, "exit_factor", min_exclusive=0.0)
    target_f = _float_param(target_per_cell, "target_per_cell", min_exclusive=0.0)
    # Rust owns the numeric decision; host maps mode ids onto wire strings.
    exact, _mode, gw, gh = kernels.lod_plan(
        visible_i,
        budget_f,
        bool(in_drill),
        exit_factor=exit_f,
        width=request.width,
        height=request.height,
        target_per_cell=target_f,
    )
    return LodPlan(
        mode=direct_mode if exact else aggregate_mode,
        tier="direct" if exact else aggregate_mode,
        visible=visible_i,
        budget=budget_f,
        grid_w=gw,
        grid_h=gh,
        reduction="none" if exact else aggregate_reduction,
        exact=exact,
    )


def grid_shape(
    w: int, h: int, visible: int, target_per_cell: float = DENSITY_TARGET_POINTS_PER_CELL
) -> tuple[int, int]:
    """Keep aggregation grids screen-bounded, but avoid one-pixel bins when
    the visible count is only barely over the direct budget. A few points per
    cell gives smoother drill-out aggregates and smaller updates.

    Host validates/clamps the screen shape; Rust owns the shrink math
    (`xy_lod_grid_shape`).
    """
    w, h = screen_shape(w, h)
    visible_i = _integer_param(visible, "visible")
    target_f = _float_param(target_per_cell, "target_per_cell", min_exclusive=0.0)
    return kernels.lod_grid_shape(w, h, visible_i, target_f)


def local_log_density(
    xs: np.ndarray,
    ys: np.ndarray,
    lo_x: float,
    hi_x: float,
    lo_y: float,
    hi_y: float,
    gw: int,
    gh: int,
) -> np.ndarray:
    """Per-point log-normalized local density in [0,1] — the LUT coordinate
    the client blends during the drill handoff so freshly drilled marks wear
    the aggregate's colormap (never a palette jump)."""
    if len(xs) and hi_x > lo_x and hi_y > lo_y:
        return kernels.local_log_density(xs, ys, lo_x, hi_x, lo_y, hi_y, gw, gh)
    return np.zeros(len(xs), dtype=np.float32)
