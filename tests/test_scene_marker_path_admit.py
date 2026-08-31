"""ABI 221 Scene marker-path admit — Python host wrapper over xyg_scene_marker_path_admit."""

from __future__ import annotations

import pytest

from xyg import kernels
from xyg.marks import _validated_marker_path


def test_scene_marker_path_admit_bounds() -> None:
    assert kernels.scene_marker_path_admit([-0.5, -0.5, 0.5, -0.5, 0.0, 0.5], [6]) is True
    assert kernels.scene_marker_path_admit([0.0, 0.0, 0.5, 0.0], [4]) is True
    assert kernels.scene_marker_path_admit([0.0, 0.0], [2]) is False
    assert kernels.scene_marker_path_admit([0.0, 0.0, float("nan"), 0.0], [4]) is False
    assert kernels.scene_marker_path_admit([0.0, 0.0, 0.6, 0.0], [4]) is False
    assert kernels.scene_marker_path_admit([0.0, 0.0, 0.5, 0.0], []) is False


def test_validated_marker_path_host_coercion() -> None:
    diamond = {"contours": [[-0.4, 0.0, 0.0, 0.4, 0.4, 0.0, 0.0, -0.4]]}
    assert _validated_marker_path(diamond)["filled"] is True
    with pytest.raises(ValueError, match="mapping"):
        _validated_marker_path([0, 0])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Scene marker path"):
        _validated_marker_path({"contours": [[0.0, 0.0]]})
    with pytest.raises(ValueError, match="Scene marker path"):
        _validated_marker_path({"contours": []})
