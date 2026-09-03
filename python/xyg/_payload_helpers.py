"""Thin payload emit helpers delegated to Rust ABI kernels."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from . import channels, kernels
from ._payload_writer import PayloadWriter
from ._trace import Trace
from .columns import Column
from .config import MAX_ANIMATION_MATCH_ROWS


def transition_entry(
    entry: dict[str, Any],
    t: Trace,
    pw: PayloadWriter,
    sel: Optional[np.ndarray] = None,
    key_values: Optional[np.ndarray] = None,
) -> dict[str, Any]:
    """Attach bounded declarative transition metadata to one trace spec."""
    plan = kernels.payload_transition_entry_attach(
        has_trace_animation=t.animation is not None,
        entry_has_animation="animation" in entry,
        has_trace_keys=t.transition_keys is not None,
        has_key_values=key_values is not None,
        has_sel=sel is not None,
        tier_direct=entry.get("tier") == "direct",
        n_marks=int(entry.get("n_marks", 0)),
        n_trace_key_rows=len(t.transition_keys) if t.transition_keys is not None else 0,
        n_key_value_rows=len(key_values) if key_values is not None else 0,
        n_sel_rows=len(sel) if sel is not None else 0,
        max_rows=MAX_ANIMATION_MATCH_ROWS,
        has_tooltip_rows=False,
        n_tooltip_rows=0,
        n_points=t.n_points,
    )
    if plan["attach_animation"]:
        animation = t.animation
        if animation is not None:
            entry["animation"] = dict(animation)
    if not plan["attempt_keys"]:
        return entry
    keys = t.transition_keys if key_values is None else key_values
    keys = np.asarray(keys, dtype=np.uint32)
    values = keys[sel] if plan["filter_keys_by_sel"] else keys
    if not plan["ship_keys"]:
        entry["animation_fallback"] = plan["animation_fallback"]
        return entry
    entry["keys"] = {
        "lo": pw.ship_u32(values[:, 0]),
        "hi": pw.ship_u32(values[:, 1]),
    }
    return entry


def attach_tooltip_rows(entry: dict[str, Any], t: Trace, sel: Optional[np.ndarray]) -> None:
    """Ship optional semantic hover rows (Sankey / graph props), filtered with geometry."""
    plan = kernels.payload_transition_entry_attach(
        has_trace_animation=False,
        entry_has_animation=False,
        has_trace_keys=False,
        has_key_values=False,
        has_sel=sel is not None,
        tier_direct=False,
        n_marks=0,
        n_trace_key_rows=0,
        n_key_value_rows=0,
        n_sel_rows=len(sel) if sel is not None else 0,
        max_rows=MAX_ANIMATION_MATCH_ROWS,
        has_tooltip_rows=t.tooltip_rows is not None,
        n_tooltip_rows=len(t.tooltip_rows) if t.tooltip_rows is not None else 0,
        n_points=t.n_points,
    )
    if not plan["attach_tooltip"]:
        if t.tooltip_rows is not None and not plan["tooltip_length_ok"]:
            raise ValueError(
                f"{t.kind} tooltip rows must match geometry ({len(t.tooltip_rows)} != {t.n_points})"
            )
        return
    tooltip_rows = t.tooltip_rows
    if tooltip_rows is None:
        return
    if not plan["filter_tooltip_by_sel"]:
        indices = range(len(tooltip_rows))
    else:
        if sel is None:
            return
        indices = (int(i) for i in sel)
    entry["tooltip_rows"] = [dict(tooltip_rows[i]) for i in indices]


def visible_mask_needed(
    figure: Any,
    t: Trace,
    *,
    prefiltered: bool,
    base_column: Optional[Column] = None,
) -> bool:
    """Whether ``log_visible_mask`` can drop any row for this trace."""
    return kernels.payload_visible_needed(
        x_log=figure._axis_scale(t.x_axis) == "log",
        y_log=figure._axis_scale(t.y_axis) == "log",
        prefiltered=prefiltered,
        x_has_nulls=bool(t.x.zone.null_count),
        y_has_nulls=bool(t.y.zone.null_count),
        has_base=base_column is not None,
        base_has_nulls=bool(base_column.zone.null_count) if base_column is not None else False,
    )


def log_visible_mask(
    figure: Any,
    t: Trace,
    xv: np.ndarray,
    yv: np.ndarray,
    base: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Rows this trace may actually ship."""
    return kernels.payload_visible_mask(
        xv,
        yv,
        x_log=figure._axis_scale(t.x_axis) == "log",
        y_log=figure._axis_scale(t.y_axis) == "log",
        base=base,
    )


def visible_sel(
    figure: Any,
    t: Trace,
    xv: np.ndarray,
    yv: np.ndarray,
    *,
    base: Optional[np.ndarray] = None,
    prefiltered: bool = False,
    base_column: Optional[Column] = None,
) -> Optional[np.ndarray]:
    """Keep-all (``None``) vs original-row keep indices (ABI 205)."""
    keep_all, idx = kernels.payload_visible_indices(
        xv,
        yv,
        x_log=figure._axis_scale(t.x_axis) == "log",
        y_log=figure._axis_scale(t.y_axis) == "log",
        base=base,
        prefiltered=prefiltered,
        x_has_nulls=bool(t.x.zone.null_count),
        y_has_nulls=bool(t.y.zone.null_count),
        has_base=base is not None or base_column is not None,
        base_has_nulls=(bool(base_column.zone.null_count) if base_column is not None else False),
    )
    if keep_all:
        return None
    return idx


def binning_coords(
    figure: Any,
    axis_id: str,
    values: np.ndarray,
    bounds: tuple[float, float],
) -> tuple[np.ndarray, tuple[float, float]]:
    """Column values and window bounds in the axis's binning space."""
    if figure._axis_scale(axis_id) == "linear":
        return values, (float(bounds[0]), float(bounds[1]))
    c0, c1 = (float(v) for v in figure._axis_coord(axis_id, bounds))
    if not (np.isfinite(c0) and np.isfinite(c1) and c1 > c0):
        return values, (float(bounds[0]), float(bounds[1]))
    return figure._axis_coord(axis_id, values), (c0, c1)


def ship_trace_channel_attach(
    entry: dict[str, Any],
    t: Trace,
    sel,
    pw: PayloadWriter,
    slot: int,
    *,
    include_trace_styles: bool,
    has_color2_ch: bool = False,
) -> None:  # noqa: ANN001
    """Attach paint/style channels per Rust-owned channel ship registry (ABI 311)."""
    plan = kernels.payload_channel_ship_plan(
        slot,
        include_trace_styles=include_trace_styles,
        has_color2_ch=has_color2_ch,
        has_color_ch=t.color_ch is not None,
        has_stroke_ch=t.stroke_ch is not None,
        has_style_channels=bool(t.style_channels),
    )
    channels.ship_registry_attach(entry, t, sel, pw.ship_scalar, pw.ship_u8, plan)


def payload_column_ship_plan(
    figure: Any,
    t: Trace,
    *,
    kind: Optional[str] = None,
    orientation: Optional[str] = None,
) -> dict:
    """Rust-owned geometry column registry and gather policy (ABI 310/314)."""
    return kernels.payload_column_ship_plan(
        kind=kind or t.kind,
        x_axis_scale=figure._axis_scale(t.x_axis),
        y_axis_scale=figure._axis_scale(t.y_axis),
        orientation=orientation,
    )
