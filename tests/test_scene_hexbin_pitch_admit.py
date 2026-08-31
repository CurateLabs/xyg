"""ABI 237 Scene hexbin pitch admit — wrapper over xyg_scene_hexbin_pitch_admit."""

from __future__ import annotations

from xyg import kernels


def test_scene_hexbin_pitch_admit_table() -> None:
    assert kernels.scene_hexbin_pitch_admit(1.0, 2.0) is True
    assert kernels.scene_hexbin_pitch_admit(0.0, 1.0) is False
    assert kernels.scene_hexbin_pitch_admit(1.0, 0.0) is False
    assert kernels.scene_hexbin_pitch_admit(-1.0, 1.0) is False
    assert kernels.scene_hexbin_pitch_admit(float("nan"), 1.0) is False
    assert kernels.scene_hexbin_pitch_admit(1.0, float("inf")) is False
