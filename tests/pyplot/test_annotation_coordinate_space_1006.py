"""Matplotlib 3.11 corpus case 53: annotation coordinate spaces and ``table()`` (#1006).

Static export used to reject any text with ``style["coordinate_space"]`` (even a
plain ``ax.text(..., transform=ax.transAxes)``), so the corpus ``table()`` cells
failed closed. Rust now owns the ``axes_fraction`` / ``xaxis_transform`` /
``yaxis_transform`` projection (``XYAW`` v3); pyplot only marshals the string.
``figure_fraction`` stays a stable, explicit gap because a panel Scene does not
own the figure rectangle.
"""

from __future__ import annotations

import io
import re

import pytest

import xyg.pyplot as plt
from xyg._static_document import UnsupportedStaticExport


def teardown_function() -> None:
    plt.close("all")


def _svg(fig) -> str:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="svg")
    return buffer.getvalue().decode()


def _position(svg: str, label: str) -> tuple[float, float]:
    match = re.search(rf"<text([^>]*)>{re.escape(label)}</text>", svg)
    assert match, f"{label!r} missing from the SVG"
    return tuple(
        float(re.search(rf' {axis}="([-\d.]+)"', match.group(1)).group(1)) for axis in "xy"
    )


def _axes():
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot([1, 10, 1000], [1, 3, 2])
    ax.set_xscale("log")
    ax.set_xlim(1, 1000)
    ax.set_ylim(0, 4)
    return fig, ax


def test_text_in_axes_fraction_lands_where_the_equivalent_data_point_lands() -> None:
    fig, ax = _axes()
    ax.text(0.5, 0.5, "frac", transform=ax.transAxes, ha="center")
    ax.text(1000**0.5, 2, "data", ha="center")
    svg = _svg(fig)
    assert _position(svg, "frac") == _position(svg, "data")


def test_mixed_axis_transforms_project_the_data_component_through_the_log_scale() -> None:
    fig, ax = _axes()
    ax.annotate("xx", xy=(10, 0.5), xycoords="xaxis transform", ha="center")
    ax.annotate("yy", xy=(0.25, 3), xycoords="yaxis transform", ha="center")
    ax.text(10, 2, "xd", ha="center")
    ax.text(1000**0.25, 3, "yd", ha="center")
    svg = _svg(fig)
    assert _position(svg, "xx") == _position(svg, "xd")
    assert _position(svg, "yy") == _position(svg, "yd")


def test_figure_fraction_text_fails_closed_with_a_stable_reason() -> None:
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3])
    ax.text(0.5, 0.5, "fig", transform=fig.transFigure)
    with pytest.raises(
        UnsupportedStaticExport, match="XYG_SCENE_UNSUPPORTED_ANNOTATION_COORDINATE_SPACE"
    ):
        _svg(fig)


def test_case_53_table_cells_render_below_the_axes_with_their_fills() -> None:
    fig, ax = plt.subplots(figsize=(4.5, 3.5))
    ax.table(
        cellText=[["north", 12], ["south", 18]],
        colLabels=["region", "value"],
        cellColours=[["#dbeafe", "#dbeafe"], ["#dcfce7", "#dcfce7"]],
    )
    svg = _svg(fig)
    for label in ("region", "value", "north", "12", "south", "18"):
        assert re.search(rf">{label}</text>", svg), label
    # Cell backgrounds are real Scene label boxes, not browser CSS.
    boxes = re.findall(r'<rect data-xy-slot="annotation_label_box"[^>]*fill="([^"]+)"', svg)
    assert boxes.count("rgba(219,234,254,1.000000)") == 2
    assert boxes.count("rgba(220,252,231,1.000000)") == 2
    assert "xy-mpl-table-cell" not in svg
    _x, header = _position(svg, "region")
    _x, last = _position(svg, "south")
    assert last > header  # rows run top-down in axes-fraction space
