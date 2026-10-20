"""#1006: line-handle marker swatches and per-panel legends in static documents."""

from __future__ import annotations

import io
import re

import numpy as np
import pytest

import xyg.pyplot as plt


def _svg(fig) -> str:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="svg")
    return buffer.getvalue().decode()


def _legends(svg: str) -> list[str]:
    return re.findall(r'<g data-xy-static-legend="">(.*?)</g>', svg, re.S)


def _frame_x(legend: str) -> float:
    return float(re.search(r'<rect x="([\d.]+)"', legend).group(1))


@pytest.fixture(autouse=True)
def _close():
    yield
    plt.close("all")


def test_line_with_marker_draws_a_line_and_marker_swatch():
    x = np.arange(6)
    plt.plot(x, x, marker="s", color="m", label="marked")
    plt.plot(x, x + 1, color="b", label="plain")
    plt.legend()
    marked, plain = _legends(_svg(plt.gcf()))[0].split("<line")[1:]
    assert "<rect" in marked and "<rect" not in plain.split("<text")[0]


def test_each_axes_legend_is_anchored_to_its_own_panel():
    fig, axes = plt.subplots(1, 2, figsize=(8, 3))
    x = np.arange(5)
    axes[0].plot(x, x, label="left")
    axes[1].plot(x, x, label="right")
    for axis in axes:
        axis.legend(loc="upper left")
    legends = _legends(_svg(fig))
    assert len(legends) == 2
    width = fig.get_size_inches()[0] * fig.dpi
    assert _frame_x(legends[0]) < width / 2 < _frame_x(legends[1])


def test_a_single_panel_legend_among_several_exports():
    fig, axes = plt.subplots(1, 2, figsize=(8, 3))
    x = np.arange(5)
    axes[0].plot(x, x, label="only")
    axes[1].plot(x, x)
    axes[0].legend()
    assert len(_legends(_svg(fig))) == 1


def test_unstroked_marker_keeps_a_borderless_legend_swatch():
    x = np.arange(5)
    plt.plot(x, x, marker="o", markeredgecolor="none", label="a")
    plt.legend()
    legend = _legends(_svg(plt.gcf()))[0]
    circle = re.search(r"<circle[^>]*>", legend).group(0)
    assert "stroke-width" not in circle


def _rects(svg: str, tag: str) -> list[tuple[float, float, float, float]]:
    return [
        tuple(float(v) for v in match)
        for match in re.findall(
            rf'data-xy-chrome="{tag}"[^>]*?x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"',
            svg,
        )
    ]


def _legend_frames(svg: str) -> list[tuple[float, float, float, float]]:
    return [
        tuple(
            float(v)
            for v in re.search(
                r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"', legend
            ).groups()
        )
        for legend in _legends(svg)
    ]


@pytest.mark.parametrize(
    "loc", ["upper left", "upper right", "lower left", "lower right", "center", "best"]
)
def test_single_panel_legend_loc_is_placed_inside_the_axes_plot_box(loc):
    x = np.arange(8)
    plt.figure(figsize=(6, 4))
    plt.plot(x, x, label="series")
    plt.legend(loc=loc)
    svg = _svg(plt.gcf())
    ((lx, ly, lw, lh),) = _legend_frames(svg)
    # The axes plot box is the Scene's plot-background rectangle.
    px, py, pw, ph = _rects(svg, "plot-background")[0]
    assert px <= lx and lx + lw <= px + pw + 1e-6, (loc, lx, lw, px, pw)
    assert py <= ly and ly + lh <= py + ph + 1e-6, (loc, ly, lh, py, ph)
    if loc != "best":
        center_x, center_y = lx + lw / 2, ly + lh / 2
        want_left, want_top = ("left" in loc), ("upper" in loc)
        if loc == "center":
            assert abs(center_x - (px + pw / 2)) < 1 and abs(center_y - (py + ph / 2)) < 1
        else:
            assert (center_x < px + pw / 2) is want_left
            assert (center_y < py + ph / 2) is want_top


def test_polar_panel_legends_stay_inside_the_canvas():
    theta = np.linspace(0.0, 2.0 * np.pi, 17)
    radius = 0.6 + 0.3 * np.cos(4.0 * theta)
    fig, axes = plt.subplots(1, 2, figsize=(8, 4), subplot_kw={"projection": "polar"})
    axes[0].plot(theta, radius, color="tab:blue", label="response")
    axes[0].fill(theta, radius, color="tab:blue")
    axes[0].scatter(theta[::2], radius[::2], color="tab:orange", s=24)
    axes[0].set_theta_zero_location("N")
    axes[0].set_theta_direction(-1)
    axes[0].set_rlim(0.0, 1.0)
    axes[0].legend()
    axes[1].bar(np.arange(0.0, 2.0 * np.pi, np.pi / 4.0), [3, 5, 4, 7, 6, 4, 2, 3], width=0.6)
    svg = _svg(fig)
    width, height = (float(v) for v in re.search(r'width="(\d+)" height="(\d+)"', svg).groups())
    frames = _legend_frames(svg)
    assert len(frames) == 1
    for x, y, w, h in frames:
        assert x >= 0 and x + w <= width / 2 and y >= 0 and y + h <= height, (x, y, w, h)


def test_marker_legend_alpha_matches_the_plotted_data_alpha():
    """``plot(marker=..., alpha=0.5)``: line and marker swatch carry the data alpha."""
    x = np.arange(5)
    plt.plot(x, x, marker="s", color="m", alpha=0.5, label="a")
    plt.legend()
    svg = _svg(plt.gcf())
    legend = _legends(svg)[0]
    line_alpha = float(re.search(r'<line[^>]*stroke="rgba\([\d,]+,([\d.]+)\)"', legend).group(1))
    marker = re.search(r'<rect[^>]*fill-opacity="([\d.]+)"', legend)
    assert marker is not None
    assert line_alpha == pytest.approx(0.5, abs=5e-3)
    assert float(marker.group(1)) == pytest.approx(0.5, abs=5e-3)
    # The plotted series uses the same alpha.
    assert 'stroke-opacity="0.5"' in svg.split("data-xy-static-legend", 1)[0]
