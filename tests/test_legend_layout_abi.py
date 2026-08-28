"""ABI 124 static legend box packing: Python host wrappers match the Rust goldens."""

from __future__ import annotations

from xyg import _native
from xyg._svg import _legend_layout, _legend_text_width


def test_titled_short_entries_keep_classes_prefix() -> None:
    plot = {"x": 0.0, "y": 0.0, "w": 560.0, "h": 400.0}
    native = _native.scene_legend_box_layout(
        plot=plot,
        names=["1", "2", "3", "4"],
        title="Classes",
        loc="lower left",
    )
    packed = _legend_layout(
        [{"name": name} for name in ("1", "2", "3", "4")],
        plot,
        {"loc": "lower left", "title": "Classes"},
    )
    assert native["visible_count"] == 4
    assert str(native["title"]).startswith("Clas")
    assert packed["title"] == native["title"]
    assert _legend_text_width(packed["title"]) <= packed["box_w"] - packed["pad"]


def test_wide_entries_keep_the_full_title() -> None:
    plot = {"x": 0.0, "y": 0.0, "w": 560.0, "h": 400.0}
    laid = _native.scene_legend_box_layout(
        plot=plot,
        names=["alpha", "beta", "gamma"],
        title="Classes",
        loc="lower left",
    )
    assert laid["title"] == "Classes"


def test_narrow_plot_ellipsizes_wide_labels() -> None:
    plot = {"x": 0.0, "y": 0.0, "w": 150.0, "h": 400.0}
    names = ["Wmmmmmmmmmmmmmmmmmmmm", "iiiiiiiiiiiiiiiiiiii"]
    laid = _legend_layout(
        [{"name": name} for name in names],
        plot,
        {"loc": "upper right"},
    )
    assert any(name.endswith("...") for name in laid["names"])
    text_x = laid["column_offsets"][0] + laid["handle"] + laid["gap"]
    for rendered in laid["names"]:
        assert text_x + _legend_text_width(rendered) <= laid["box_w"]


def test_upper_right_sits_in_the_inset_corner() -> None:
    plot = {"x": 10.0, "y": 20.0, "w": 200.0, "h": 160.0}
    laid = _native.scene_legend_box_layout(
        plot=plot,
        names=["a"],
        loc="upper right",
    )
    assert laid["x"] + laid["box_w"] == plot["x"] + plot["w"] - 6.0
    assert laid["y"] == plot["y"] + 6.0
