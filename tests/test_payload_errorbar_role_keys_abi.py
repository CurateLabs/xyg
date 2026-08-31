"""ABI 273 payload_errorbar_role_keys parity."""

from __future__ import annotations

import numpy as np
import pytest

from xyg import kernels


def test_payload_errorbar_role_keys_xor_mix() -> None:
    keys = kernels.payload_errorbar_role_keys(
        np.array([10, 20], dtype=np.uint32),
        np.array([30, 40], dtype=np.uint32),
        np.array([0, 1, 0, 1], dtype=np.uint32),
        np.array([0, 0, 1, 1], dtype=np.uint32),
    )
    assert keys.shape == (4, 2)
    assert keys[0, 0] == 10
    assert keys[1, 0] == 20
    assert keys[2, 0] == 10 ^ np.uint32(0x9E3779B9)
    assert keys[3, 0] == 20 ^ np.uint32(0x9E3779B9)


def test_payload_errorbar_role_keys_collision() -> None:
    with pytest.raises(ValueError, match="role-qualified animation key collision"):
        kernels.payload_errorbar_role_keys(
            np.array([0, 0x9E3779B9], dtype=np.uint32),
            np.array([0, 0x85EBCA6B], dtype=np.uint32),
            np.array([1, 0], dtype=np.uint32),
            np.array([0, 1], dtype=np.uint32),
        )
