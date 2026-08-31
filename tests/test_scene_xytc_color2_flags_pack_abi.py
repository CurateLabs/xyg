"""ABI 271 scene_xytc_color2_flags_pack parity."""

from __future__ import annotations

from xyg import kernels


def test_scene_xytc_color2_flags_pack_fail() -> None:
    assert kernels.scene_xytc_color2_flags_pack(4, 0, 0) == 1 << 13


def test_scene_xytc_color2_flags_pack_gradient_with_fill() -> None:
    assert kernels.scene_xytc_color2_flags_pack(2, 1 << 0, 0) == 1 << 13


def test_scene_xytc_color2_flags_pack_gradient_inject() -> None:
    assert kernels.scene_xytc_color2_flags_pack(2, 0, 1) == (1 << 0) | (1 << 19)


def test_scene_xytc_color2_flags_pack_gradient_missing_blob() -> None:
    assert kernels.scene_xytc_color2_flags_pack(2, 0, 0) == 1 << 13


def test_pack_xytc_color2_fail() -> None:
    from types import SimpleNamespace

    from xyg import _scene_v3 as scene

    trace = SimpleNamespace(
        kind="line",
        color2_ch=object(),
        color_ch=None,
        style={},
    )
    flags, blob = scene._pack_xytc_color2(trace, 0, b"")
    assert flags == 1 << 13
    assert blob == b""
