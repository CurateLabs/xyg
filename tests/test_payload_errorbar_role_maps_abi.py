"""ABI 261 payload_errorbar_role_maps parity."""

from __future__ import annotations

import numpy as np

from xyg import kernels


def test_payload_errorbar_role_maps_tile_repeat() -> None:
    sources, roles = kernels.payload_errorbar_role_maps(6, 3)
    assert sources is not None and roles is not None
    np.testing.assert_array_equal(sources, [0, 1, 2, 0, 1, 2])
    np.testing.assert_array_equal(roles, [0, 0, 0, 1, 1, 1])


def test_payload_errorbar_role_maps_not_applicable() -> None:
    assert kernels.payload_errorbar_role_maps(10, 3) is None


def test_payload_errorbar_role_maps_matches_numpy() -> None:
    n_points = 11
    seg_per = 3
    n_segments = n_points * seg_per
    sources, roles = kernels.payload_errorbar_role_maps(n_segments, n_points)
    assert sources is not None and roles is not None
    expected_sources = np.tile(np.arange(n_points, dtype=np.uint32), seg_per)
    expected_roles = np.repeat(np.arange(seg_per, dtype=np.uint32), n_points)
    np.testing.assert_array_equal(sources, expected_sources)
    np.testing.assert_array_equal(roles, expected_roles)
