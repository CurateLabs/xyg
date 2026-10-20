"""pyplot `twinx()` on the native Scene secondary y axis (#1006, corpus case 26).

The twin's right-hand y axis is the public composition API's `y2` axis; pyplot
seeds its rc tick styling from `ytick.*` exactly as for the left axis.
"""

from __future__ import annotations

import io
import re

import numpy as np
import pytest

import xyg.pyplot as plt

BLUE = "rgba(31,119,180,1.000000)"
RED = "rgba(214,39,40,1.000000)"


def _twin_figure():
    t = np.arange(0, 10, 0.5)
    fig, ax1 = plt.subplots()
    ax1.plot(t, np.exp(t / 5), color="tab:blue", label="growth")
    ax1.set_ylabel("growth", color="tab:blue")
    ax2 = ax1.twinx()
    ax2.plot(t, np.sin(t), color="tab:red")
    ax2.set_ylabel("oscillation", color="tab:red")
    return fig


def _svg(fig) -> str:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="svg")
    return buffer.getvalue().decode("utf-8")


def _texts(svg: str) -> list[tuple[dict[str, str], str]]:
    return [
        (dict(re.findall(r'([\w-]+)="([^"]*)"', attrs)), body)
        for attrs, body in re.findall(r"<text([^>]*)>([^<]*)</text>", svg)
    ]


def _plot_box(svg: str) -> tuple[float, float]:
    match = re.search(
        r'data-xy-chrome="plot-background" x="([\d.]+)" y="[\d.]+" width="([\d.]+)"', svg
    )
    assert match is not None
    left, width = float(match.group(1)), float(match.group(2))
    return left, left + width


def _canvas_width(svg: str) -> float:
    return float(re.search(r'<svg[^>]*width="([\d.]+)"', svg).group(1))


def _right_tick_lengths(svg: str) -> list[float]:
    _left, right = _plot_box(svg)
    lengths = []
    for attrs in re.findall(r"<line([^>]*)/>", svg):
        d = {key: float(value) for key, value in re.findall(r'(x1|x2|y1|y2)="([-\d.]+)"', attrs)}
        if d["y1"] == d["y2"] and min(d["x1"], d["x2"]) == pytest.approx(right, abs=0.01):
            lengths.append(abs(d["x1"] - d["x2"]))
    return lengths


def test_twin_titles_keep_their_authored_colors() -> None:
    texts = _texts(_svg(_twin_figure()))
    assert next(a for a, t in texts if t == "growth")["fill"] == BLUE
    assert next(a for a, t in texts if t == "oscillation")["fill"] == RED


def test_twin_tick_labels_keep_the_default_rc_color() -> None:
    texts = _texts(_svg(_twin_figure()))
    right = [a for a, t in texts if a.get("text-anchor") == "start"]
    assert right
    # Only the title was authored red; ticks follow ytick.labelcolor (black).
    assert {a["fill"] for a in right} == {"rgba(0,0,0,1.000000)"}
    assert {a["font-size"] for a in right} == {"13.89"}


def test_twin_labels_sit_in_the_right_gutter_inside_the_canvas() -> None:
    svg = _svg(_twin_figure())
    _left, right_edge = _plot_box(svg)
    texts = _texts(svg)
    right = [a for a, t in texts if a.get("text-anchor") == "start"]
    assert all(float(a["x"]) > right_edge for a in right)
    title = next(a for a, t in texts if t == "oscillation")
    assert float(title["x"]) > max(float(a["x"]) for a in right)
    assert all(float(a["x"]) < _canvas_width(svg) for a, _t in texts)


def test_twin_shares_one_x_ladder() -> None:
    texts = _texts(_svg(_twin_figure()))
    x_labels = [t for a, t in texts if a.get("text-anchor") == "middle" and "transform" not in a]
    assert x_labels == ["0", "2", "4", "6", "8"]


def test_twin_axis_is_seeded_from_the_ytick_rc() -> None:
    default = _right_tick_lengths(_svg(_twin_figure()))
    assert default
    assert default == pytest.approx([3.5 * 100 / 72] * len(default), abs=0.01)
    with plt.rc_context({"ytick.major.size": 8.0, "ytick.labelcolor": "green"}):
        svg = _svg(_twin_figure())
    assert _right_tick_lengths(svg) == pytest.approx([8.0 * 100 / 72] * len(default), abs=0.01)
    right = [a for a, t in _texts(svg) if a.get("text-anchor") == "start"]
    assert {a["fill"] for a in right} == {"rgba(0,128,0,1.000000)"}


def test_clearing_a_twin_reseeds_its_right_axis_from_the_current_rc() -> None:
    fig = _twin_figure()
    ax2 = fig.axes[0]._twin
    assert ax2 is not None
    with plt.rc_context({"ytick.major.size": 8.0}):
        ax2.clear()
    ax2.plot([0, 1], [0, 1])
    # `clear()` drops the authored red title and re-seeds the tick geometry.
    assert "label_color" not in fig.axes[0]._axis["y2"]["style"]
    lengths = _right_tick_lengths(_svg(fig))
    assert lengths
    assert lengths == pytest.approx([8.0 * 100 / 72] * len(lengths), abs=0.01)
    assert fig.axes[0]._axis["y2"]["style"]["tick_length"] == pytest.approx(8.0 * 100 / 72)


def test_clearing_the_host_drops_the_twin_and_a_new_twin_is_seeded() -> None:
    fig = _twin_figure()
    ax1 = fig.axes[0]
    ax1.clear()
    assert ax1._twin is None
    with plt.rc_context({"ytick.major.size": 8.0}):
        ax2 = ax1.twinx()
    ax1.plot([0, 1], [0, 1])
    ax2.plot([0, 1], [0, 1])
    assert ax1._axis["y2"]["style"]["tick_length"] == pytest.approx(8.0 * 100 / 72)
