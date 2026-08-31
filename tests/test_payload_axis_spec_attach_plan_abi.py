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


def test_axis_spec_cartesian_tick_labels_cross_host_fixture() -> None:
    """Node buildPayload axis tick_labels parity when attach_ticks is set."""
    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    fig.set_axis("x", tick_values=[0.0, 1.0], tick_labels=["a", "b"])
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["tick_labels"] == ["a", "b"]
    assert "tick_labels" not in spec["y_axis"]


def test_axis_spec_cartesian_tick_count_cross_host_fixture() -> None:
    """Node buildPayload axis tick_count parity when attach_ticks is set."""
    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    fig.set_axis("x", tick_count=4)
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["tick_count"] == 4
    assert "tick_count" not in spec["y_axis"]


def test_axis_spec_cartesian_reverse_cross_host_fixture() -> None:
    """Node buildPayload axis reverse parity when attach_reverse is set."""
    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    fig.set_axis("x", reverse=True)
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["reverse"] is True
    assert "reverse" not in spec["y_axis"]


def test_axis_spec_cartesian_domain_cross_host_fixture() -> None:
    """Node buildPayload axis domain parity when attach_domain is set."""
    fig = Figure(width=240, height=160)
    fig.scatter([1.0, 2.0], [1.0, 2.0])
    fig.set_axis("x", domain=[0.0, 3.0])
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["domain"] == [0.0, 3.0]
    assert "domain" not in spec["y_axis"]


def test_axis_spec_cartesian_format_cross_host_fixture() -> None:
    """Node buildPayload axis format parity when attach_format is set."""
    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    fig.set_axis("x", format=".2f")
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["format"] == ".2f"
    assert "format" not in spec["y_axis"]


def test_axis_spec_cartesian_bounds_cross_host_fixture() -> None:
    """Node buildPayload axis bounds parity when attach_bounds is set."""
    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    fig.set_axis("x", bounds=(0.0, 2.0))
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["bounds"] == [0.0, 2.0]
    assert "bounds" not in spec["y_axis"]


def test_axis_spec_cartesian_tick_sides_cross_host_fixture() -> None:
    """Node buildPayload axis tick_sides parity when attach_tick_sides is set."""
    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    fig.set_axis("x", tick_sides=["bottom"])
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["tick_sides"] == ["bottom"]
    assert "tick_sides" not in spec["y_axis"]


def test_axis_spec_polar_tick_sides_cross_host_fixture() -> None:
    """Node buildPayload polar axis tick_sides parity when attach_tick_sides is set."""
    fig = Figure(coords="polar", width=240, height=160)
    fig.set_axis("x", tick_sides=["bottom"])
    fig.scatter([0.0, 1.0], [1.0, 2.0])
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["tick_sides"] == ["bottom"]


def test_axis_spec_cartesian_tick_label_sides_cross_host_fixture() -> None:
    """Node buildPayload axis tick_label_sides parity when attach_tick_label_sides is set."""
    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    fig.set_axis("x", tick_label_sides=["bottom"])
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["tick_label_sides"] == ["bottom"]
    assert "tick_label_sides" not in spec["y_axis"]


def test_axis_spec_polar_tick_label_sides_cross_host_fixture() -> None:
    """Node buildPayload polar axis tick_label_sides parity when attach_tick_label_sides is set."""
    fig = Figure(coords="polar", width=240, height=160)
    fig.set_axis("x", tick_label_sides=["bottom"])
    fig.scatter([0.0, 1.0], [1.0, 2.0])
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["tick_label_sides"] == ["bottom"]


def test_axis_spec_cartesian_label_position_cross_host_fixture() -> None:
    """Node buildPayload axis label_position parity when attach_label_position is set."""
    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    fig.set_axis("x", label_position="end")
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["label_position"] == "end"
    assert "label_position" not in spec["y_axis"]


def test_axis_spec_polar_label_position_cross_host_fixture() -> None:
    """Node buildPayload polar axis label_position parity when attach_label_position is set."""
    fig = Figure(coords="polar", width=240, height=160)
    fig.set_axis("x", label_position="end")
    fig.scatter([0.0, 1.0], [1.0, 2.0])
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["label_position"] == "end"


def test_axis_spec_cartesian_label_offset_cross_host_fixture() -> None:
    """Node buildPayload axis label_offset parity when attach_label_offset is set."""
    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    fig.set_axis("x", label_offset=8.0)
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["label_offset"] == 8.0
    assert "label_offset" not in spec["y_axis"]


def test_axis_spec_polar_label_offset_cross_host_fixture() -> None:
    """Node buildPayload polar axis label_offset parity when attach_label_offset is set."""
    fig = Figure(coords="polar", width=240, height=160)
    fig.set_axis("x", label_offset=4.0)
    fig.scatter([0.0, 1.0], [1.0, 2.0])
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["label_offset"] == 4.0


def test_axis_spec_cartesian_label_angle_cross_host_fixture() -> None:
    """Node buildPayload axis label_angle parity when attach_label_angle is set."""
    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    fig.set_axis("x", label_angle=45.0)
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["label_angle"] == 45.0
    assert "label_angle" not in spec["y_axis"]


def test_axis_spec_polar_label_angle_cross_host_fixture() -> None:
    """Node buildPayload polar axis label_angle parity when attach_label_angle is set."""
    fig = Figure(coords="polar", width=240, height=160)
    fig.set_axis("x", label_angle=15.0)
    fig.scatter([0.0, 1.0], [1.0, 2.0])
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["label_angle"] == 15.0


def test_axis_spec_cartesian_tick_label_angle_cross_host_fixture() -> None:
    """Node buildPayload axis tick_label_angle parity when attach_tick_label_angle is set."""
    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    fig.set_axis("x", tick_label_angle=30.0)
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["tick_label_angle"] == 30.0
    assert "tick_label_angle" not in spec["y_axis"]


def test_axis_spec_polar_tick_label_angle_cross_host_fixture() -> None:
    """Node buildPayload polar axis tick_label_angle parity when attach_tick_label_angle is set."""
    fig = Figure(coords="polar", width=240, height=160)
    fig.set_axis("x", tick_label_angle=20.0)
    fig.scatter([0.0, 1.0], [1.0, 2.0])
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["tick_label_angle"] == 20.0


def test_axis_spec_cartesian_tick_label_strategy_cross_host_fixture() -> None:
    """Node buildPayload axis tick_label_strategy parity when attach_tick_label_strategy is set."""
    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    fig.set_axis("x", tick_label_strategy="rotate")
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["tick_label_strategy"] == "rotate"
    assert "tick_label_strategy" not in spec["y_axis"]


def test_axis_spec_polar_tick_label_strategy_cross_host_fixture() -> None:
    """Node buildPayload polar axis tick_label_strategy parity when attach_tick_label_strategy is set."""
    fig = Figure(coords="polar", width=240, height=160)
    fig.set_axis("x", tick_label_strategy="stagger")
    fig.scatter([0.0, 1.0], [1.0, 2.0])
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["tick_label_strategy"] == "stagger"


def test_axis_spec_cartesian_tick_label_anchor_cross_host_fixture() -> None:
    """Node buildPayload axis tick_label_anchor parity when attach_tick_label_anchor is set."""
    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    fig.set_axis("x", tick_label_anchor="end")
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["tick_label_anchor"] == "end"
    assert "tick_label_anchor" not in spec["y_axis"]


def test_axis_spec_polar_tick_label_anchor_cross_host_fixture() -> None:
    """Node buildPayload polar axis tick_label_anchor parity when attach_tick_label_anchor is set."""
    fig = Figure(coords="polar", width=240, height=160)
    fig.set_axis("x", tick_label_anchor="center")
    fig.scatter([0.0, 1.0], [1.0, 2.0])
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["tick_label_anchor"] == "center"


def test_axis_spec_cartesian_tick_label_min_gap_cross_host_fixture() -> None:
    """Node buildPayload axis tick_label_min_gap parity when attach_tick_label_min_gap is set."""
    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    fig.set_axis("x", tick_label_min_gap=9.0)
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["tick_label_min_gap"] == 9.0
    assert "tick_label_min_gap" not in spec["y_axis"]


def test_axis_spec_polar_tick_label_min_gap_cross_host_fixture() -> None:
    """Node buildPayload polar axis tick_label_min_gap parity when attach_tick_label_min_gap is set."""
    fig = Figure(coords="polar", width=240, height=160)
    fig.set_axis("x", tick_label_min_gap=12.0)
    fig.scatter([0.0, 1.0], [1.0, 2.0])
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["tick_label_min_gap"] == 12.0


def test_axis_spec_cartesian_minor_style_cross_host_fixture() -> None:
    """Node buildPayload axis minor_style parity when attach_minor_style is set."""
    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    fig.set_axis("x", minor_style={"tick_color": "#888"})
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["minor_style"]["tick_color"] == "#888"
    assert "minor_style" not in spec["y_axis"]


def test_axis_spec_polar_minor_style_cross_host_fixture() -> None:
    """Node buildPayload polar axis minor_style parity when attach_minor_style is set."""
    fig = Figure(coords="polar", width=240, height=160)
    fig.set_axis("x", minor_style={"tick_color": "#111"})
    fig.scatter([0.0, 1.0], [1.0, 2.0])
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["minor_style"]["tick_color"] == "#111"


def test_axis_spec_cartesian_style_cross_host_fixture() -> None:
    """Node buildPayload axis style parity when attach_style is set."""
    fig = Figure(width=240, height=160)
    fig.scatter([0.0, 1.0], [0.0, 1.0])
    fig.set_axis("x", style={"tick_color": "#111"})
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["style"]["tick_color"] == "#111"
    assert "style" not in spec["y_axis"]


def test_axis_spec_polar_style_cross_host_fixture() -> None:
    """Node buildPayload polar axis style parity when attach_style is set."""
    fig = Figure(coords="polar", width=240, height=160)
    fig.set_axis("x", style={"tick_color": "#222"})
    fig.scatter([0.0, 1.0], [1.0, 2.0])
    spec, _ = fig.build_payload()
    assert spec["x_axis"]["style"]["tick_color"] == "#222"


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
