"""ABI 304 payload_axis_spec_attach_plan parity."""

from __future__ import annotations

import math

from xyg import kernels
from xyg._figure import Figure


def test_payload_axis_spec_attach_plan_cartesian_core() -> None:
    plan = kernels.payload_axis_spec_attach_plan(
        coords_cartesian=True,
        axis_is_x=True,
    )
    assert plan["attach_id"] is True
    assert plan["attach_kind"] is True
    assert plan["attach_side"] is True
    assert plan["attach_label"] is True
    assert plan["attach_range"] is True
    assert plan["attach_scale"] is True
    assert plan["attach_ticks"] is True
    assert plan["attach_domain"] is True
    assert plan["attach_format"] is True
    assert plan["attach_bounds"] is True
    assert plan["attach_theta_unit"] is False
    assert plan["attach_hole"] is False
    assert plan["attach_r_origin"] is False


def test_payload_axis_spec_attach_plan_polar_theta_on_x() -> None:
    plan = kernels.payload_axis_spec_attach_plan(
        coords_cartesian=False,
        axis_is_x=True,
    )
    assert plan["attach_theta_unit"] is True
    assert plan["attach_theta_zero"] is True
    assert plan["attach_theta_direction"] is True
    assert plan["attach_sector"] is True
    assert plan["attach_grid_shape"] is True
    assert plan["attach_hole"] is False


def test_payload_axis_spec_attach_plan_polar_r_on_y() -> None:
    plan = kernels.payload_axis_spec_attach_plan(
        coords_cartesian=False,
        axis_is_x=False,
    )
    assert plan["attach_theta_unit"] is False
    assert plan["attach_hole"] is True
    assert plan["attach_r_origin"] is True


def test_axis_spec_uses_kernel_attach_plan_cartesian() -> None:
    fig = Figure()
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    fig.set_axis("x", tick_values=[0.0, 0.5, 1.0], domain=[0.0, 1.0], format=".2f")
    spec, _ = fig.build_payload()
    axis = spec["x_axis"]
    assert axis["id"] == "x"
    assert axis["kind"] == "linear"
    assert axis["tick_values"] == [0.0, 0.5, 1.0]
    assert axis["domain"] == [0.0, 1.0]
    assert axis["format"] == ".2f"
    assert "theta_unit" not in axis


def test_axis_spec_cartesian_meta_cross_host_fixture() -> None:
    """Node buildPayload axis id/kind/side/label parity for scatter_direct."""
    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0, 2.0], [0.0, 1.0, 0.5])
    fig.traces[0].id = 7
    spec, _ = fig.build_payload()
    for axis_id in ("x", "y"):
        axis = spec[f"{axis_id}_axis"]
        assert axis["id"] == axis_id
        assert axis["kind"] == "linear"
        assert axis["label"] is None
        assert "scale" not in axis
    assert spec["x_axis"]["side"] == "bottom"
    assert spec["y_axis"]["side"] == "left"


def test_axis_spec_cartesian_tick_values_cross_host_fixture() -> None:
    """Node buildPayload axis tick_values parity when attach_ticks is set."""
    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    fig.set_axis("x", tick_values=[0.0, 0.5, 1.0], domain=[0.0, 1.0], format=".2f")
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["tick_values"] == [0.0, 0.5, 1.0]
    assert "tick_values" not in spec["y_axis"]


def test_axis_spec_cartesian_minor_tick_values_cross_host_fixture() -> None:
    """Node buildPayload axis minor_tick_values parity when attach_ticks is set."""
    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    fig.set_axis("x", minor_tick_values=[0.25, 0.75])
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["minor_tick_values"] == [0.25, 0.75]
    assert "minor_tick_values" not in spec["y_axis"]


def test_axis_spec_omits_linear_scale() -> None:
    fig = Figure()
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    spec, _ = fig.build_payload()
    assert "scale" not in spec["x_axis"]
    assert "scale" not in spec["y_axis"]


def test_axis_spec_ships_log_scale() -> None:
    fig = Figure()
    fig.set_axis("x", type_="log")
    fig.scatter([1.0, 10.0], [1.0, 10.0])
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["scale"] == "log"
    assert "scale" not in spec["y_axis"]


def test_axis_spec_uses_kernel_attach_plan_polar() -> None:
    fig = Figure(coords="polar")
    fig.scatter([0.0, math.pi / 2], [0.0, 1.0])
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["theta_unit"] == "radians"
    assert spec["y_axis"]["hole"] == 0.0
    assert "theta_unit" not in spec["y_axis"]
