"""View-dependent LOD machinery shared by aggregated chart kinds (§5/§28).

Everything here is chart-agnostic — nothing knows about scatter. It covers the
mechanics every tiered chart repeats:

- the visible-window mask (§19: non-finite rows never enter a subset),
- the hysteresis-guarded drill decision (§5: tier = f(visible_count)),
- drilled-subset bookkeeping on a Trace (shipped_sel / drill_mode / drill_seq,
  the §16/§17 index-space versioning),
- §16 window-centered offset encoding for shipped geometry,
- the screen-derived aggregation grid shape,
- per-point local log-density (the drill handoff's LUT coordinate),
- wire-buffer packing (typed f32/u8 scalars, §29).

`interaction.density_view` wires these together for scatter; a future
heatmap/histogram tier reuses them with a different aggregate kernel — the
per-chart-kind rules live in the LOD/Tiling Contract (§28).
"""

from __future__ import annotations

import numpy as np

from . import _lod_drill as _drill
from . import _lod_encode as _encode
from . import _lod_plan as _plan
from . import _lod_sample as _sample
from . import _lod_viewport as _viewport
from . import kernels  # noqa: F401 — re-export for test monkeypatch
from ._lod_encode import F32_SAFE_MAG
from ._lod_sample import _sample_threshold  # noqa: F401
from ._lod_types import EncodedColumn, LodPlan
from ._lod_viewport import ViewportRequest

# viewport
normalize_window = _viewport.normalize_window
screen_shape = _viewport.screen_shape
visible_mask = _viewport.visible_mask
aligned_window = _viewport.aligned_window

# plan
drill_decision = _plan.drill_decision
plan_view_lod = _plan.plan_view_lod
grid_shape = _plan.grid_shape
local_log_density = _plan.local_log_density

# sample
hash_row_ids = _sample.hash_row_ids
sample_keep_mask = _sample.sample_keep_mask
stratified_sample_keep_mask = _sample.stratified_sample_keep_mask
sample_rows_for_target = _sample.sample_rows_for_target
sample_row_range_for_target = _sample.sample_row_range_for_target
bin_2d_sample_row_range_for_target = _sample.bin_2d_sample_row_range_for_target
stratified_sample_row_range_for_target = _sample.stratified_sample_row_range_for_target
bin_2d_stratified_sample_row_range_for_target = (
    _sample.bin_2d_stratified_sample_row_range_for_target
)

# drill
enter_drill = _drill.enter_drill
exit_drill = _drill.exit_drill
drill_history = _drill.drill_history
clear_drill_history = _drill.clear_drill_history

# encode
BufferWriter = _encode.BufferWriter
f32_safe_scale = _encode.f32_safe_scale
encode_f32_values = _encode.encode_f32_values
pins_offset_to_zero = _encode.pins_offset_to_zero
geometry_offset = _encode.geometry_offset
encode_window_xy_columns = _encode.encode_window_xy_columns


def add_window_xy(
    writer: _encode.BufferWriter,
    xs: np.ndarray,
    ys: np.ndarray,
    lo_x: float,
    hi_x: float,
    lo_y: float,
    hi_y: float,
    x_scale: str | None = None,
    y_scale: str | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Hub wrapper so monkeypatch on ``lod.encode_window_xy_columns`` applies."""
    x_col, y_col = encode_window_xy_columns(
        xs, ys, lo_x, hi_x, lo_y, hi_y, x_scale=x_scale, y_scale=y_scale
    )
    return writer.add_encoded(x_col), writer.add_encoded(y_col)


__all__ = [
    "F32_SAFE_MAG",
    "BufferWriter",
    "EncodedColumn",
    "LodPlan",
    "ViewportRequest",
    "add_window_xy",
    "aligned_window",
    "bin_2d_sample_row_range_for_target",
    "bin_2d_stratified_sample_row_range_for_target",
    "clear_drill_history",
    "drill_decision",
    "drill_history",
    "encode_f32_values",
    "encode_window_xy_columns",
    "enter_drill",
    "exit_drill",
    "f32_safe_scale",
    "geometry_offset",
    "grid_shape",
    "hash_row_ids",
    "local_log_density",
    "normalize_window",
    "pins_offset_to_zero",
    "plan_view_lod",
    "sample_keep_mask",
    "sample_row_range_for_target",
    "sample_rows_for_target",
    "screen_shape",
    "stratified_sample_keep_mask",
    "stratified_sample_row_range_for_target",
    "visible_mask",
]
