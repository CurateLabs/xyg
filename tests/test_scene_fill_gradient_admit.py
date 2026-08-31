"""ABI 226 Scene fill-gradient admit — wrapper over xyg_scene_fill_gradient_admit."""

from __future__ import annotations

from xyg import kernels
from xyg._scene_v3 import _admitted_fill_gradient_from_fill


def test_scene_fill_gradient_admit_table() -> None:
    admitted = kernels.scene_fill_gradient_admit(
        "mark",
        "down",
        [0.0, 1.0],
        ["#336699", "#34d399"],
        "#3987e5",
    )
    assert admitted is not None
    assert len(admitted) == 2
    assert (
        kernels.scene_fill_gradient_admit(
            "mark",
            "down",
            [0.0, 1.0],
            ["var(--accent)", "#ffffff"],
            "#3987e5",
        )
        is None
    )
    current = kernels.scene_fill_gradient_admit(
        "plot",
        "up",
        [0.0, 1.0],
        ["currentcolor", ""],
        "#3987e5",
    )
    assert current is not None
    fallback = kernels.css_color_rgba("#3987e5", 1.0)
    assert current[0] == fallback
    assert current[1] == fallback
    assert (
        kernels.scene_fill_gradient_admit(
            "data",
            "down",
            [0.0, 1.0],
            ["#336699", "#34d399"],
            "#3987e5",
        )
        is None
    )


def test_admitted_fill_gradient_host_coercion() -> None:
    spec = {
        "space": "mark",
        "dir": "down",
        "stops": [[0.0, "#000000"], [1.0, "#ffffff"]],
    }
    admitted = _admitted_fill_gradient_from_fill(spec, "#3987e5")
    assert admitted is not None
    assert admitted["space"] == "mark"
    assert admitted["dir"] == "down"
    rejected = _admitted_fill_gradient_from_fill(
        {"space": "mark", "dir": "down", "stops": [[0.0, "var(--accent)"], [1.0, "#ffffff"]]},
        "#3987e5",
    )
    assert rejected is None
