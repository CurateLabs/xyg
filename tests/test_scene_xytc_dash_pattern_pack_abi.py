"""ABI 268 scene_xytc_dash_pattern_pack parity."""

from __future__ import annotations

from xyg import kernels


def test_scene_xytc_dash_pattern_pack_not_array() -> None:
    assert kernels.scene_xytc_dash_pattern_pack(0) == 0


def test_scene_xytc_dash_pattern_pack_array() -> None:
    assert kernels.scene_xytc_dash_pattern_pack(1) == 1 << 17
