"""ABI 267 density_grid_path_identity_state parity."""

from __future__ import annotations

from xyg import kernels


def test_density_grid_path_identity_state_identity_paths() -> None:
    for path in (0, 1, 2, 3, 4):
        assert kernels.density_grid_path_identity_state(grid_path=path) is True


def test_density_grid_path_identity_state_range_indices() -> None:
    assert kernels.density_grid_path_identity_state(grid_path=5) is False
