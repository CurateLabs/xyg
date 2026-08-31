"""ABI 227 Scene linear-gradient CSS parse — wrapper over xyg_scene_parse_linear_gradient."""

from __future__ import annotations

from xyg import kernels
from xyg._scene_v3 import _admitted_fill_gradient_from_fill
from xyg._validate import mark_fill


def test_scene_parse_linear_gradient_table() -> None:
    code, spec = kernels.scene_parse_linear_gradient(
        "linear-gradient(currentColor, transparent)", "mark"
    )
    assert code == 1
    assert spec is not None
    assert spec["dir"] == "down"
    assert spec["stops"] == [[0.0, "currentColor"], [1.0, "transparent"]]
    plot_code, plot = kernels.scene_parse_linear_gradient(
        "linear-gradient(to right, red 10%, blue)", "plot"
    )
    assert plot_code == 1
    assert plot is not None
    assert plot["dir"] == "right"
    assert plot["stops"] == [[0.1, "red"], [1.0, "blue"]]
    nested_code, nested = kernels.scene_parse_linear_gradient(
        "linear-gradient(rgba(1,2,3,.5), var(--mid), rgb(9,9,9))", "mark"
    )
    assert nested_code == 1
    assert nested is not None
    assert nested["stops"] == [
        [0.0, "rgba(1,2,3,.5)"],
        [0.5, "var(--mid)"],
        [1.0, "rgb(9,9,9)"],
    ]
    assert kernels.scene_parse_linear_gradient("radial-gradient(red, blue)", "mark")[0] == 0
    assert kernels.scene_parse_linear_gradient("linear-gradient(45deg, red, blue)", "mark")[0] == 3
    assert (
        kernels.scene_parse_linear_gradient("linear-gradient(to left, red, blue)", "mark")[0] == 4
    )
    assert kernels.scene_parse_linear_gradient("linear-gradient(red)", "mark")[0] == 5


def test_mark_fill_uses_kernel_and_keeps_error_text() -> None:
    spec = mark_fill("linear-gradient(currentColor, transparent)", "area fill")
    assert spec is not None
    assert spec["stops"][0][1] == "currentColor"
    try:
        mark_fill("linear-gradient(45deg, red, blue)", "area fill")
    except ValueError as exc:
        assert "angles unsupported" in str(exc)
    else:
        raise AssertionError("expected angles unsupported")


def test_admitted_fill_gradient_parses_css_without_mark_fill() -> None:
    admitted = _admitted_fill_gradient_from_fill(
        "linear-gradient(to bottom, #336699, #34d399)", "#3987e5"
    )
    assert admitted is not None
    assert admitted["dir"] == "down"
    assert len(admitted["stops"]) == 2
    rejected = _admitted_fill_gradient_from_fill("linear-gradient(45deg, red, blue)", "#3987e5")
    assert rejected is None
