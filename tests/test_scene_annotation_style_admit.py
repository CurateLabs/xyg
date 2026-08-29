"""ABI 222 Scene annotation style admit — wrapper over xyg_scene_annotation_style_admit."""

from __future__ import annotations

from xyg import kernels
from xyg._scene_v3 import _annotation_allowed_style


def test_scene_annotation_style_admit_table() -> None:
    assert kernels.scene_annotation_style_admit("arrow", False, False, "width") is True
    assert kernels.scene_annotation_style_admit("arrow", False, False, "dash") is False
    assert kernels.scene_annotation_style_admit("arrow", False, True, "label_color") is False
    assert kernels.scene_annotation_style_admit("callout", False, False, "width") is True
    assert kernels.scene_annotation_style_admit("text", False, False, "width") is False
    assert kernels.scene_annotation_style_admit("text", True, True, "width") is False
    assert kernels.scene_annotation_style_admit("text", True, True, "label_background") is True
    assert kernels.scene_annotation_style_admit("rule", False, False, "dash") is True
    assert kernels.scene_annotation_style_admit("rule", False, False, "label_color") is False
    assert kernels.scene_annotation_style_admit("rule", False, True, "label_color") is True
    assert kernels.scene_annotation_style_admit("band", False, False, "label_color") is False
    assert kernels.scene_annotation_style_admit("band", False, True, "label_color") is True
    assert kernels.scene_annotation_style_admit("marker", False, False, "stroke_width") is True
    assert kernels.scene_annotation_style_admit("foo", False, True, "width") is False
    assert kernels.scene_annotation_style_admit("", False, False, "color") is True
    assert kernels.scene_annotation_style_admit("rule", False, False, "") is False


def test_annotation_allowed_style_host_wrapper() -> None:
    assert _annotation_allowed_style("arrow", False, False) == {"color", "opacity", "width"}
    assert "label_color" not in _annotation_allowed_style("rule", False, False)
    assert "label_color" in _annotation_allowed_style("rule", False, True)
    assert "width" not in _annotation_allowed_style("text", True, True)
    assert "label_background" in _annotation_allowed_style("text", True, True)
