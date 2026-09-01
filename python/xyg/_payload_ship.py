"""Column registry gather + ship helpers for payload emit (ABI 310/314)."""

from __future__ import annotations

from typing import Any

import numpy as np

from . import kernels
from ._payload_writer import PayloadWriter
from ._trace import Trace
from .columns import Column


def column_ship_scale_axis(col: dict[str, Any], plan: dict[str, Any]) -> str:
    """Map a resolved column ship scale name to the x/y axis slot for gather materialize."""
    x_name = str(plan["x_ship_scale"])
    y_name = str(plan["y_ship_scale"])
    name = str(col["ship_scale"])
    if name == x_name and name != y_name:
        return "x"
    if name == y_name and name != x_name:
        return "y"
    slot = str(col["trace_slot"])
    if slot.startswith("y") or slot in {
        "base",
        "value1",
        "value0",
        "target_y0",
        "target_y1",
    }:
        return "y"
    return "x"


def ship_registry_columns(
    figure: Any,
    entry: dict[str, Any],
    t: Trace,
    pw: PayloadWriter,
    column_plan: dict[str, Any],
    arrays: dict[str, np.ndarray],
    *,
    skip_keys: frozenset[str] | None = None,
    nested_keys: frozenset[str] | None = None,
    sel: np.ndarray | None = None,
) -> None:
    """Ship gathered geometry arrays into ``entry`` per the column registry."""
    cols = [
        col
        for col in column_plan["columns"]
        if skip_keys is None or col["registry_key"] not in skip_keys
    ]
    if not cols:
        return
    x_scale = figure._axis_scale(t.x_axis).encode("utf-8")
    y_scale = figure._axis_scale(t.y_axis).encode("utf-8")
    descriptors: list[dict[str, Any]] = []
    values: list[np.ndarray] = []
    kinds: list[bytes] = []
    scales: list[bytes] = []
    for col in cols:
        key = col["registry_key"]
        slot = col["trace_slot"]
        source = getattr(t, slot, None)
        if sel is not None and isinstance(source, Column):
            raw_arr = source.values
        else:
            raw_arr = arrays[key] if key in arrays else arrays[slot]
        column = source if isinstance(source, Column) else getattr(t, slot, None)
        if col["ship_method"] == "offset" and isinstance(column, Column):
            col_min, col_max = float(column.min), float(column.max)
            sticky = float(column.suggest_offset())
            kind_b = str(column.kind).encode("utf-8")
        elif col["ship_method"] == "values":
            bounds = kernels.min_max(raw_arr)
            col_min, col_max = bounds if bounds is not None else (0.0, 0.0)
            sticky = 0.0
            kind_b = str(column.kind if column is not None else "float").encode("utf-8")
        else:
            col_min, col_max = 0.0, 0.0
            sticky = 0.0
            kind_b = b""
        descriptors.append(
            {
                "registry_key": key,
                "ship_method": col["ship_method"],
                "ship_scale": column_ship_scale_axis(col, column_plan),
                "col_min": col_min,
                "col_max": col_max,
                "sticky_offset": sticky,
            }
        )
        values.append(np.ascontiguousarray(raw_arr, dtype=np.float64).reshape(-1))
        kinds.append(kind_b)
        axis_slot = column_ship_scale_axis(col, column_plan)
        scales.append(x_scale if axis_slot == "x" else y_scale)
    materialized = kernels.payload_column_gather_materialize(
        sel=sel,
        columns=descriptors,
        values=values,
        kinds=kinds,
        axis_scales=scales,
    )
    for col, mat in zip(cols, materialized, strict=True):
        key = col["registry_key"]
        enc = np.frombuffer(mat["bytes"], dtype="<f4" if mat["dtype_code"] == 0 else "<f8")
        col_idx = pw.append_from_materialized(enc, mat["meta"])
        if nested_keys is not None and key in nested_keys:
            entry[key] = {"col": col_idx, **pw.columns[col_idx]}
        else:
            entry[key] = col_idx
