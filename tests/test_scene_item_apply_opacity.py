"""ABI 245 Scene item-apply-opacity — wrapper over xyg_scene_item_apply_opacity."""

from __future__ import annotations

from xyg import kernels


def test_scene_item_apply_opacity_table() -> None:
    packed = bytes([10, 20, 30, 40, 1, 2, 3, 80])
    identity = kernels.scene_item_apply_opacity(packed, 2, None, None)
    assert identity == packed
    artist = kernels.scene_item_apply_opacity(packed, 2, [-1.0, 0.5], None)
    assert artist is not None
    assert artist[:4] == bytes([10, 20, 30, 40])
    assert artist[4:] == bytes([1, 2, 3, 128])
    opacity = kernels.scene_item_apply_opacity(packed, 2, None, [0.5, 0.25])
    assert opacity is not None
    assert opacity[3] == 20
    assert opacity[7] == 20
    assert kernels.scene_item_apply_opacity(packed, 2, [0.5], None) is None
    assert kernels.scene_item_apply_opacity(b"", 0, None, None) == b""
