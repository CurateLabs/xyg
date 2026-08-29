"""ABI 251 clip-quantize u8 — wrapper over xyg_clip_quantize_u8."""

from __future__ import annotations

import numpy as np

from xyg import kernels


def test_clip_quantize_u8_table() -> None:
    assert kernels.clip_quantize_u8([]).tolist() == []
    assert kernels.clip_quantize_u8([0.0, 0.5, 1.0, 1.5]).tolist() == [0, 128, 255, 255]
    assert kernels.clip_quantize_u8([float("nan")]).tolist() == [0]
    assert kernels.clip_quantize_u8([1.5 / 255.0]).tolist() == [2]


def test_clip_quantize_u8_matches_historical_numpy() -> None:
    values = np.array([0.0, 0.5, 1.0, 1.5, -0.1, 2.5 / 255.0, float("nan")])
    with np.errstate(invalid="ignore"):
        historical = np.clip(values, 0.0, 1.0)
        historical = historical * 255.0
        np.rint(historical, out=historical)
        historical_u8 = historical.astype(np.uint8)
    np.testing.assert_array_equal(kernels.clip_quantize_u8(values), historical_u8)
