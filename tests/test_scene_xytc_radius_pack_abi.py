"""ABI 262 scene_xytc_radius_pack parity."""

from __future__ import annotations

from xyg import kernels


def test_scene_xytc_radius_pack_bar_pair() -> None:
    flags, tip, base, gap = kernels.scene_xytc_radius_pack("bar", 2, 1.0, 2.0, 0.0)
    assert flags == 1 << 22
    assert (tip, base, gap) == (1.0, 2.0, 0.0)


def test_scene_xytc_radius_pack_bar_scalar_and_gap() -> None:
    flags, tip, base, gap = kernels.scene_xytc_radius_pack("bar", 1, 3.0, 0.0, 0.5)
    assert flags == (1 << 22) | (1 << 23)
    assert (tip, base, gap) == (3.0, 3.0, 0.5)


def test_scene_xytc_radius_pack_scatter_ignored() -> None:
    flags, tip, base, gap = kernels.scene_xytc_radius_pack("scatter", 1, 3.0, 0.0, 0.5)
    assert flags == 0
    assert (tip, base, gap) == (0.0, 0.0, 0.0)


def test_pack_xytc_radius_delegates_to_kernel() -> None:
    from xyg import _scene_v3 as scene

    class Trace:
        kind = "bar"

    flags, tip, base, gap = scene._pack_xytc_radius(
        Trace(),
        {"corner_radius": [1.0, 2.0], "wedge_gap": 0.25},
    )
    assert flags == (1 << 22) | (1 << 23)
    assert (tip, base, gap) == (1.0, 2.0, 0.25)
