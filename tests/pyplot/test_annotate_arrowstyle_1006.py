"""Matplotlib ``annotate(arrowprops=dict(arrowstyle=...))`` on the Rust Scene (#1006).

Corpus case 25 stopped static export with "Scene arrow style does not encode
['head_style', 'label_clear', 'start_offset']": the Scene arrow was a fixed
filled triangle drawn from the label anchor. The shim now maps ``arrowprops``
onto the public arrow facts and Rust draws the head, tail and label clearance
(`crates/xyg-engine/src/scene_arrow.rs`) for SVG, raster and PDF alike.
"""

from __future__ import annotations

import re
from io import BytesIO

import numpy as np
import pytest

import xyg.pyplot as plt
from xyg._static_document import UnsupportedStaticExport

TARGET_XY = (np.pi / 2, 1.0)
TEXT_XY = (2.5, 1.2)


def _annotated(arrowprops: dict, text: str = "peak", xy=TARGET_XY, xytext=TEXT_XY, **kwargs):
    x = np.linspace(0, 2 * np.pi, 100)
    fig, ax = plt.subplots()
    ax.plot(x, np.sin(x))
    ax.annotate(text, xy=xy, xytext=xytext, arrowprops=arrowprops, **kwargs)
    return fig


def _svg(fig) -> str:
    buffer = BytesIO()
    fig.savefig(buffer, format="svg")
    return buffer.getvalue().decode()


def _points(polyline: str) -> list[tuple[float, float]]:
    return [tuple(map(float, pair.split(","))) for pair in polyline.split()]


def _arrow_polyline(svg: str) -> list[tuple[float, float]]:
    # The data line is the long polyline; the arrow is the last one painted.
    return _points(re.findall(r'<polyline points="([^"]*)"', svg)[-1])


def _rect_distance(point, box) -> float:
    left, top, right, bottom = box
    dx = max(left - point[0], 0.0, point[0] - right)
    dy = max(top - point[1], 0.0, point[1] - bottom)
    return float(np.hypot(dx, dy))


def _label_box(svg: str, label: str) -> tuple[float, float, float, float]:
    element = re.search(rf"<text ([^>]*)>{re.escape(label)}</text>", svg)
    assert element, "label text not exported"
    attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', element.group(1)))
    x, y, size = float(attrs["x"]), float(attrs["y"]), float(attrs["font-size"])
    # Conservative ink box for a baseline-anchored, left-aligned label.
    return (x, y - 0.85 * size, x + 0.5 * size * len(label), y + 0.25 * size)


def test_open_arrowstyle_draws_a_v_head_not_a_filled_triangle() -> None:
    try:
        open_svg = _svg(_annotated(dict(arrowstyle="->")))
        filled_svg = _svg(_annotated(dict(arrowstyle="-|>")))
        points = _arrow_polyline(open_svg)
        # shaft, tip, wing, tip, wing: the head is two strokes meeting at the tip.
        assert len(points) == 5
        shaft_start, tip, wing_a, tip_again, wing_b = points
        assert tip == tip_again
        # The wings trail the tip symmetrically about the shaft axis.
        axis = np.subtract(tip, shaft_start)
        axis = axis / np.hypot(*axis)
        behind_a, behind_b = np.subtract(wing_a, tip), np.subtract(wing_b, tip)
        assert np.dot(behind_a, axis) < 0 and np.dot(behind_b, axis) < 0
        side = lambda v: axis[0] * v[1] - axis[1] * v[0]  # noqa: E731
        assert side(behind_a) == pytest.approx(-side(behind_b), abs=0.05)  # SVG rounds to 0.01 px
        assert np.hypot(*behind_a) == pytest.approx(np.hypot(*behind_b), abs=0.05)
        # No head polygon: `->` strokes only, while `-|>` fills one.
        assert open_svg.count('<path d="M ') + 1 == filled_svg.count('<path d="M ')
        assert len(_arrow_polyline(filled_svg)) == 2
    finally:
        plt.close("all")


def test_annotation_arrow_leaves_a_gap_to_its_label() -> None:
    try:
        svg = _svg(_annotated(dict(arrowstyle="->")))
        start = _arrow_polyline(svg)[0]
        # Matplotlib clips the arrow at the label patch plus a shrink margin; the
        # shaft must not start inside (or touching) the label's ink box.
        assert _rect_distance(start, _label_box(svg, "peak")) >= 2.0
        # A longer label pushes the start further from the label centre.
        wide = _svg(_annotated(dict(arrowstyle="->"), text="a much wider peak label"))
        assert (
            _rect_distance(_arrow_polyline(wide)[0], _label_box(wide, "a much wider peak label"))
            >= 2.0
        )
    finally:
        plt.close("all")


@pytest.mark.parametrize(
    ("arrowstyle", "vertices", "head_fills"),
    [("-", 2, 0), ("->", 5, 0), ("<-", 5, 0), ("<->", 8, 0), ("-|>", 2, 1)],
)
def test_common_arrowstyles_map_onto_the_scene_vocabulary(arrowstyle, vertices, head_fills) -> None:
    try:
        base = _svg(_annotated(dict(arrowstyle="-")))
        svg = _svg(_annotated(dict(arrowstyle=arrowstyle)))
        assert len(_arrow_polyline(svg)) == vertices
        assert svg.count('<path d="M ') - base.count('<path d="M ') == head_fills
    finally:
        plt.close("all")


@pytest.mark.parametrize(
    ("arrowprops", "reason"),
    [
        (dict(arrowstyle="fancy"), "XYG_STATIC_UNSUPPORTED_TAPERED_ANNOTATION_ARROW"),
        (dict(arrowstyle="simple"), "XYG_STATIC_UNSUPPORTED_TAPERED_ANNOTATION_ARROW"),
        (dict(arrowstyle="wedge"), "XYG_STATIC_UNSUPPORTED_TAPERED_ANNOTATION_ARROW"),
        (dict(arrowstyle="|-|"), "XYG_SCENE_UNSUPPORTED_ARROW_STYLE"),
        (dict(arrowstyle="<|-"), "XYG_SCENE_UNSUPPORTED_ARROW_STYLE"),
        (
            dict(arrowstyle="->", connectionstyle="arc3,rad=0.3"),
            "Scene arrow style does not encode",
        ),
    ],
)
def test_arrowstyles_outside_the_documented_set_fail_closed(arrowprops, reason) -> None:
    try:
        with pytest.raises((UnsupportedStaticExport, ValueError), match=reason):
            _svg(_annotated(arrowprops))
    finally:
        plt.close("all")


def _ends(**shrinks):
    # A long arrow (~300 px) so 40 pt + 30 pt of shrink still leave a shaft.
    svg = _svg(_annotated(dict(arrowstyle="-", **shrinks), xy=(0.5, 0.0), xytext=(5.5, 1.0)))
    points = _arrow_polyline(svg)
    return np.array(points[0]), np.array(points[-1])


def test_shrink_a_and_shrink_b_move_the_scene_arrow_ends_in_points() -> None:
    """shrinkA/shrinkB (points, default 2) were silently dropped (#1006 review)."""
    try:
        scale = 100.0 / 72.0  # pyplot's pt -> px at the default dpi
        zero_start, zero_tip = _ends(shrinkA=0, shrinkB=0)
        big_start, big_tip = _ends(shrinkA=40, shrinkB=30)
        default_start, default_tip = _ends()
        # shrinkB pulls the tip back along the shaft by exactly that many points.
        assert np.hypot(*(zero_tip - big_tip)) == pytest.approx(30 * scale, abs=0.05)
        assert np.hypot(*(zero_tip - default_tip)) == pytest.approx(2 * scale, abs=0.05)
        # shrinkA is added beyond the label patch edge (box extents grow by it),
        # so the shaft starts at least that much further out along its direction.
        assert np.hypot(*(zero_start - big_start)) >= 40 * scale - 0.5
        assert np.hypot(*(zero_start - default_start)) >= 2 * scale - 0.5
        # The 2 pt default is Matplotlib's: omitting the keys equals writing them.
        explicit_start, explicit_tip = _ends(shrinkA=2, shrinkB=2)
        assert np.allclose(default_start, explicit_start) and np.allclose(default_tip, explicit_tip)
    finally:
        plt.close("all")


@pytest.mark.parametrize("bad", [-1, float("nan"), "2"])
def test_invalid_shrink_values_fail_loudly(bad) -> None:
    try:
        with pytest.raises((TypeError, ValueError), match="shrink"):
            _svg(_annotated(dict(arrowstyle="->", shrinkA=bad)))
    finally:
        plt.close("all")


def test_shrink_that_consumes_the_shaft_fails_closed_instead_of_being_ignored() -> None:
    """Facts are honored exactly or the arrow is rejected (#1006 review)."""
    try:
        # ~130 px between label and target: 40 pt + 30 pt (~97 px) plus the label
        # clearance leaves nothing, and the Scene refuses rather than restoring
        # the untrimmed arrow.
        with pytest.raises(ValueError, match="invalid canonical scene batch"):
            _svg(_annotated(dict(arrowstyle="->", shrinkA=40, shrinkB=30)))
    finally:
        plt.close("all")
