"""ABI 274 payload_bar_compact_admit parity."""

from __future__ import annotations

import numpy as np

from xyg import kernels


def test_payload_bar_compact_admit_uniform_width_and_const_baseline() -> None:
    compact, width, has_value0_const, value0_const = kernels.payload_bar_compact_admit(
        np.array([0.8, 0.8, 0.8], dtype=np.float64),
        np.array([0.0, 0.0, 0.0], dtype=np.float64),
    )
    assert compact is True
    assert width == 0.8
    assert has_value0_const is True
    assert value0_const == 0.0


def test_payload_bar_compact_admit_empty_width_defaults() -> None:
    compact, width, has_value0_const, _value0_const = kernels.payload_bar_compact_admit(
        np.array([], dtype=np.float64),
        np.array([], dtype=np.float64),
    )
    assert compact is True
    assert width == 1.0
    assert has_value0_const is False


def test_payload_bar_compact_admit_rejects_non_uniform_width() -> None:
    compact, width, has_value0_const, _value0_const = kernels.payload_bar_compact_admit(
        np.array([0.8, 0.9], dtype=np.float64),
        np.array([], dtype=np.float64),
    )
    assert compact is False
    assert np.isnan(width)
    assert has_value0_const is False
