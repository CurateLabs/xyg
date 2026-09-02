"""Payload gather/materialize ABI smoke for Push 3B (ABI 320)."""

from __future__ import annotations

import numpy as np

from xyg import kernels


def test_payload_column_gather_materialize_offset_f32() -> None:
    x = np.array([0.0, 1.0, 2.0], dtype=np.float64)
    sel = np.array([0, 2], dtype=np.uint32)
    out = kernels.payload_column_gather_materialize(
        sel=sel,
        columns=[
            {
                "ship_method": "offset",
                "ship_scale": "x",
                "col_min": 0.0,
                "col_max": 2.0,
                "sticky_offset": 1.0,
            }
        ],
        values=[x],
        kinds=[b"float"],
        axis_scales=[b"linear"],
    )
    assert out[0]["meta"]["len"] == 2
    assert len(out[0]["bytes"]) == 8


def test_payload_channel_materialize_continuous() -> None:
    values = np.array([0.0, 0.5, 1.0], dtype=np.float64)
    out = kernels.payload_channel_materialize(
        role="color",
        mode="continuous",
        n_categories=0,
        style_dtype_u8=False,
        quantize_continuous=False,
        domain=(0.0, 1.0),
        n_palette=0,
        sel=None,
        values_f64=values,
        values_u8=None,
    )
    assert out["len"] == 3
    assert out["buf_kind"] == 2
