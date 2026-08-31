"""ABI 266 scene_xytc_hex_pitch_pack parity."""

from __future__ import annotations

import math

from xyg import kernels


def test_scene_xytc_hex_pitch_pack_non_hexbin() -> None:
    flags, dx, dy = kernels.scene_xytc_hex_pitch_pack(0, 1, 1, 1.0, 2.0)
    assert flags == 0
    assert math.isnan(dx)
    assert math.isnan(dy)


def test_scene_xytc_hex_pitch_pack_hexbin_no_pitch() -> None:
    flags, dx, dy = kernels.scene_xytc_hex_pitch_pack(1, 0, 0, float("nan"), float("nan"))
    assert flags == 1 << 8
    assert math.isnan(dx)
    assert math.isnan(dy)


def test_scene_xytc_hex_pitch_pack_hexbin_with_pitch() -> None:
    flags, dx, dy = kernels.scene_xytc_hex_pitch_pack(1, 1, 1, 1.0, 2.0)
    assert flags == 1 << 8
    assert (dx, dy) == (1.0, 2.0)


def test_pack_xytc_hex_pitch_delegates_to_kernel() -> None:
    from xyg import _scene_v3 as scene

    flags, dx, dy = scene._pack_xytc_hex_pitch(
        scene._SCENE_KIND_CLASS_HEXBIN,
        {"hex_dx": 1.5, "dy": 2.5},
    )
    assert flags == 1 << 8
    assert dx == 1.5
    assert dy == 2.5
