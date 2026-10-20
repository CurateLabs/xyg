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


def test_top_side_heatmap_axes_export_with_the_first_row_on_top() -> None:
    """matshow/spy put the x axis on top; the public Scene admits it (corpus 51/54).

    ``spy`` must also draw row 0 at the top: a diagonal matrix runs from the
    top-left to the bottom-right corner, not through the other diagonal.
    """
    try:
        fig, ax = plt.subplots(figsize=(3, 3))
        ax.spy(np.eye(6), markersize=None)
        pixels = _png_rgb(fig).mean(axis=-1)
        height, width = pixels.shape
        inner = pixels[int(height * 0.3) : int(height * 0.85), int(width * 0.3) : int(width * 0.85)]
        rows, cols = np.nonzero(inner < 0.2)
        assert len(rows)
        # The identity diagonal runs top-left to bottom-right.
        assert np.corrcoef(rows, cols)[0, 1] > 0.8

        fig, ax = plt.subplots()
        ax.matshow(np.arange(16.0).reshape(4, 4))
        assert _blank_ratio(_png_rgb(fig)) < 0.9
    finally:
        plt.close("all")


def test_colormapped_contour_lines_export_as_literal_level_colors() -> None:
    """contour/tricontour with cmap= lower to per-level literal strokes (corpus 49/54)."""
    xx, yy = np.meshgrid(np.linspace(-2, 2, 40), np.linspace(-2, 2, 40))
    try:
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.contour(xx, yy, np.exp(-(xx**2 + yy**2)), levels=6, cmap="viridis")
        pixels = _png_rgb(fig)
        hues = {tuple(np.round(p, 1)) for p in pixels.reshape(-1, 3) if p.max() - p.min() > 0.25}
        assert len(hues) >= 4  # several distinct level colors, not one flat stroke
    finally:
        plt.close("all")


def test_pie_labels_do_not_create_a_legend_in_multi_panel_figures() -> None:
    """Pie wedge labels name artists; only ``legend()`` draws a legend (corpus 50)."""
    try:
        fig, axes = plt.subplots(1, 2, figsize=(6, 3))
        axes[0].pie([2, 3, 5], labels=["A", "B", "C"])
        axes[1].pie([4, 2, 3], labels=["x", "y", "z"], wedgeprops={"width": 0.4})
        assert _blank_ratio(_png_rgb(fig)) < 0.95
    finally:
        plt.close("all")


def test_scalar_alpha_replaces_translucent_paint_and_keeps_no_paint_absent() -> None:
    """Matplotlib's alpha *replaces* a color's own alpha and never fills ``"none"``.

    Pinned against 3.11: ``c="#ff000080", alpha=0.5`` draws face alpha 0.5 (a
    multiply would give 0.25), and ``c="none"`` keeps the face absent.
    """
    try:
        fig, ax = plt.subplots(figsize=(2, 2))
        ax.scatter([0.5], [0.5], s=4000, c="#ff000080", alpha=0.5, edgecolors="none")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        pixels = _png_rgb(fig)
        centre = pixels[pixels.shape[0] // 2, pixels.shape[1] // 2]
        assert 0.4 < centre[1] < 0.6  # replace: 0.5; multiply would be ~0.75

        fig, ax = plt.subplots(figsize=(2, 2))
        ax.scatter([0.5], [0.5], s=4000, c="none", alpha=0.5, edgecolors="red")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        pixels = _png_rgb(fig)
        centre = pixels[pixels.shape[0] // 2, pixels.shape[1] // 2]
        assert centre.min() > 0.98  # no fill appears
        assert np.any((pixels[..., 0] > 0.9) & (pixels[..., 1] < 0.8))  # the edge is drawn
    finally:
        plt.close("all")


def test_clabel_supersedes_the_native_contour_trace_instead_of_exporting_it() -> None:
    """clabel's hidden native contour is dropped at its source, not by opacity (corpus 54)."""
    z = np.arange(16.0).reshape(4, 4)
    try:
        fig, ax = plt.subplots(figsize=(3, 3))
        contours = ax.contour(z)
        ax.clabel(contours)
        assert _blank_ratio(_png_rgb(fig)) < 0.95
        assert any(entry.get("_superseded_by_segments") for entry in ax._entries)
        built = ax._build_chart(300, 300).figure()
        assert not any(
            trace.kind == "contour" and trace.style.get("opacity") == 0.0 for trace in built.traces
        )
    finally:
        plt.close("all")
