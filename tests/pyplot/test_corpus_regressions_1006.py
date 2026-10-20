"""Focused regressions for the Matplotlib 3.11 reference corpus restore (#1006).

Each test pins one distinct root cause behind a failing corpus program, through
the public ``xyg.pyplot`` surface and the canonical Rust Scene/XYST export.
"""

from __future__ import annotations

from io import BytesIO

import numpy as np

import xyg.pyplot as plt


def test_tight_layout_measures_intrinsic_chrome_not_the_allocated_frame() -> None:
    """tight_layout must not collapse panels to slivers (corpus 27).

    The probe chart carries frame padding derived from the axes' current figure
    rectangle; echoing that padding back as measured chrome made every panel
    reserve its whole allocation as margin.
    """
    fig, axs = plt.subplots(2, 2, figsize=(8, 6))
    x = np.linspace(0, 5, 60)
    axs[0, 0].plot(x, np.sin(x))
    axs[0, 0].set_title("line")
    axs[1, 0].bar(["a", "b", "c"], [3, 7, 2])
    fig.tight_layout()
    try:
        for axes in axs.ravel():
            _x, _y, width, height = axes.get_position().bounds
            assert width > 0.3
            assert height > 0.3
    finally:
        plt.close("all")


def _png_rgb(fig: object) -> np.ndarray:
    buffer = BytesIO()
    fig.savefig(buffer, format="png")  # type: ignore[attr-defined]
    return np.asarray(plt.imread(BytesIO(buffer.getvalue())))[..., :3].astype(np.float64) / 255.0


def _blank_ratio(pixels: np.ndarray) -> float:
    return float(np.mean(np.all(pixels > 0.98, axis=-1)))


def test_empty_artists_draw_nothing_and_keep_their_legend_entry() -> None:
    """Empty line/scatter artists must export (corpus 47 boxplot fliers).

    Matplotlib draws nothing for an empty artist; Scene compile rejects a
    zero-point trace, so the static projection drops it after lifting the
    legend entry of a labelled proxy.
    """
    try:
        _fig, ax = plt.subplots()
        ax.boxplot([np.arange(10.0), np.arange(5.0, 15.0)])  # no fliers
        pixels = _png_rgb(ax.figure)
        assert _blank_ratio(pixels) < 0.99

        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        ax.plot([], [], color="tab:red", label="proxy")
        ax.legend()
        with_proxy = _png_rgb(fig)
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        without_proxy = _png_rgb(fig)
        assert with_proxy.shape == without_proxy.shape
        assert not np.array_equal(with_proxy, without_proxy)
    finally:
        plt.close("all")


def test_polar_explicit_ticks_export_without_cartesian_label_strategy() -> None:
    """set_thetagrids/set_rticks must not author "preserve" on polar axes (corpus 55)."""
    theta = np.linspace(0.0, 2.0 * np.pi, 17)
    try:
        fig, ax = plt.subplots(subplot_kw={"projection": "polar"})
        ax.plot(theta, 0.6 + 0.3 * np.cos(4.0 * theta))
        ax.set_thetagrids([0, 90, 180, 270], ["N", "E", "S", "W"])
        ax.set_rticks([0.25, 0.5, 0.75, 1.0])
        assert _blank_ratio(_png_rgb(fig)) < 0.99
    finally:
        plt.close("all")


def test_scalar_alpha_replaces_paint_alpha_for_constant_and_per_item_paint() -> None:
    """Scalar ``alpha=`` reaches Scene as the paint alpha (corpus 11/12, polar bars)."""
    try:
        fig, ax = plt.subplots(figsize=(2, 2))
        ax.scatter([0.5], [0.5], s=4000, c="red", alpha=0.5, edgecolors="none")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        constant = _png_rgb(fig)
        centre = constant[constant.shape[0] // 2, constant.shape[1] // 2]
        assert centre[0] > 0.98
        assert 0.4 < centre[1] < 0.6

        fig, ax = plt.subplots(figsize=(2, 2))
        ax.scatter([0.5], [0.5], s=4000, c=[0.7], cmap="Reds", vmin=0.0, vmax=1.0, alpha=0.5)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        mapped = _png_rgb(fig)
        centre = mapped[mapped.shape[0] // 2, mapped.shape[1] // 2]
        assert centre.min() > 0.3  # half-transparent over white, not opaque
    finally:
        plt.close("all")
