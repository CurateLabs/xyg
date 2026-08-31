"""ABI 309 scene polar / encode-product orchestration parity."""

from __future__ import annotations

import xyg._scene_v3 as scene
from xyg import kernels
from xyg._figure import Figure


def test_scene_polar_figure_plan_attach_xypl() -> None:
    plan = kernels.scene_polar_figure_plan(polar=True)
    assert plan["polar"] is True
    assert plan["attach_xypl"] is True
    plan = kernels.scene_polar_figure_plan(polar=False)
    assert plan["attach_xypl"] is False


def test_scene_encode_product_attach_plan_order() -> None:
    plan = kernels.scene_encode_product_attach_plan(polar=True)
    assert plan["attach_xypl"] is True
    assert plan["step_xytc"] == 1
    assert plan["step_xyta"] == 2
    assert plan["step_xynm"] == 3
    assert plan["step_xycl"] == 4
    assert plan["step_xyaf"] == 5
    assert plan["step_xycf"] == 6
    assert plan["step_xypl"] == 7
    assert plan["step_xyfs"] == 8

    cartesian = kernels.scene_encode_product_attach_plan(polar=False)
    assert cartesian["attach_xypl"] is False


def test_pack_polar_and_figure_scene_use_orchestration() -> None:
    cartesian = Figure()
    cartesian.scatter([0.0, 1.0], [0.0, 1.0])
    assert scene._pack_polar_scene_input(cartesian) == b""
    assert scene.figure_scene(cartesian)[:4] == b"XYGS"

    polar = Figure(width=400, height=400, coords="polar")
    polar.scatter([0.0, 90.0, 180.0], [1.0, 2.0, 3.0])
    packed = scene._pack_polar_scene_input(polar)
    assert packed.startswith(b"XYPL")
    assert scene.figure_scene(polar)[:4] == b"XYGS"
