"""Regression tests for the colorbar/colormap visual-parity fixes.

Each mirrors a defect confirmed by pixel comparison against Matplotlib 3.11
(PDSH ch.4 histograms/colorbars/contour notebooks): count-mappable colorbar
domains, nice colorbar ticks, opaque zero-count heatmap cells, reversed +
clamped imshow colormaps, discrete (resampled) colormaps, and the contour
auto-level count / dashed-negative / filled-band conventions.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest

import xyg.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _clean_state():
    yield
    plt.close("all")
    plt.rcdefaults()


def _svg():
    buffer = io.BytesIO()
    plt.savefig(buffer, format="svg")
    return buffer.getvalue().decode()


def _png():
    buffer = io.BytesIO()
    plt.savefig(buffer, format="png")
    data = buffer.getvalue()
    assert data[:4] == b"\x89PNG"
    return data


def _compiled_traces():
    ax = plt.gca()
    ax._chart = None
    return ax._build_chart(800, 600).figure().traces


def _blob(name: str) -> np.ndarray:
    """Compiled colorbar options for the current axes (after build)."""
    ax = plt.gca()
    ax._chart = None
    figure = ax._build_chart(800, 600).figure()
    return getattr(figure, name)


# -- defect 1/4: count-mappable colorbar domains ------------------------------


def test_hist2d_colorbar_domain_reflects_counts_not_unit_interval():
    np.random.seed(3)
    x, y = np.random.randn(2000), np.random.randn(2000)
    h, _xe, _ye, _im = plt.hist2d(x, y, bins=20)
    plt.colorbar()
    lo, hi = plt.gca()._colorbar["domain"]
    assert lo == 0.0
    assert hi == pytest.approx(float(h.max()))
    assert hi > 1.0  # regression: used to clamp to the 0..1 placeholder


def test_vertical_colorbar_label_does_not_expand_notebook_scroll_width():
    fig, _ax = plt.subplots()
    plt.hist2d(*np.random.default_rng(0).normal(size=(2, 200)), bins=10)
    colorbar = plt.colorbar()
    colorbar.set_label("counts in bin")

    html = fig._repr_html_()
    assert "top:50%;writing-mode:vertical-rl" in html
    assert "top:50%;transform:translateY(-50%) rotate(-90deg)" not in html
    assert "&quot;width&quot;:558" in html


def test_hexbin_colorbar_domain_autoscales_to_counts_at_build():
    np.random.seed(4)
    x, y = np.random.randn(3000), np.random.randn(3000)
    plt.hexbin(x, y, gridsize=20)
    plt.colorbar()
    # colorbar() cannot know binned counts yet, so it defers via _autoscale.
    assert plt.gca()._colorbar.get("_autoscale") is True
    options = _blob("colorbar_options")
    assert "_autoscale" not in options
    assert options["domain"][1] > 1.0


# -- defect 2: nice default colorbar ticks ------------------------------------


def test_default_colorbar_ticks_are_round_numbers():
    np.random.seed(5)
    x, y = np.random.randn(4000), np.random.randn(4000)
    plt.hist2d(x, y, bins=25)
    plt.colorbar()
    svg = _svg()
    # A count domain of ~[0, 40+] must tick on round multiples produced by the
    # nice-tick locator (0, 10, 20, ...), not the raw min/max endpoints only.
    assert ">10<" in svg
    assert ">20<" in svg


@pytest.mark.xfail(reason="XYST static route gap; tracked in #889.", strict=False)
def test_default_colorbar_ticks_are_dense_for_small_decimal_domains():
    image = plt.imshow([[0.0, 0.15], [0.05, 0.1]], vmin=0.0, vmax=0.15)
    plt.colorbar(image)
    svg = _svg()
    assert all(f">{value:.2f}<" in svg for value in (0.02, 0.04, 0.06, 0.08, 0.12, 0.14))
    # The Rust tick attachment owns the 48 px colorbar spacing budget (the
    # retired `_colorbar_tick_target` table moved into the engine); ChartView
    # only paints the returned positions and labels.
    client = ROOT / "js" / "src" / "49_wasm_ticks.ts"
    assert "barLength) / 48" in client.read_text(encoding="utf-8")


def test_explicit_colorbar_ticks_still_honored():
    np.random.seed(6)
    x, y = np.random.randn(2000), np.random.randn(2000)
    plt.hist2d(x, y, bins=20)
    plt.colorbar(ticks=[0, 7, 14])
    svg = _svg()
    assert ">7<" in svg and ">14<" in svg


# -- defect 3: zero-count heatmap cells paint the colormap floor --------------


def test_zero_value_heatmap_cell_is_opaque_colormap_floor():
    from xyg import _native, kernels

    stops = np.asarray(_native.colormap_stops("viridis"), dtype=np.uint8)
    # value 0 -> opaque floor color; NaN (masked/missing) -> transparent.
    rgba = kernels.heatmap_rgba(np.array([[0.0, np.nan]]), 2, 1, stops, 255)
    assert rgba[0, 0, 3] == 255  # zero is painted, not a white hole
    assert tuple(rgba[0, 0, :3]) == tuple(int(v) for v in stops[0])
    assert rgba[0, 1, 3] == 0  # only genuine NaN stays transparent


# -- defect 5: imshow cmap (reversed) + clim reach the raster -----------------


@pytest.mark.xfail(reason="XYST static route gap; tracked in #889.", strict=False)
def test_imshow_reversed_cmap_and_post_hoc_clim_reach_the_heatmap():
    from xyg import _native

    grid = np.linspace(-3, 3, 100).reshape(10, 10)
    plt.imshow(grid, cmap="RdBu")
    plt.colorbar()
    plt.clim(-1, 1)
    entry = plt.gca()._entries[-1]
    assert entry["kwargs"]["colormap"] == "rdbu"  # true ColorBrewer table, not a coolwarm alias
    assert entry["kwargs"]["domain"] == (-1.0, 1.0)

    # The reversed lookup table must differ from the viridis fallback.
    def stops(name):
        return [list(map(int, row)) for row in _native.colormap_stops(name)]

    assert stops("coolwarm_r") == list(reversed(stops("coolwarm")))
    _png()


# -- defect 6: discrete (resampled) colormaps ---------------------------------


def test_discrete_scatter_colormap_quantizes_into_n_bands():
    np.random.seed(7)
    x, y = np.random.randn(400), np.random.randn(400)
    plt.scatter(x, y, c=x, cmap=plt.get_cmap("viridis", 6))
    plt.colorbar()
    assert plt.gca()._colorbar["levels"] == 6
    scatter = next(t for t in _compiled_traces() if t.kind == "scatter")
    distinct = np.unique(scatter.color_ch.values)
    assert distinct.size <= 6  # quantized to <= N band representatives


def test_discrete_imshow_colormap_quantizes_and_survives_clim():
    grid = np.linspace(-3, 3, 100).reshape(10, 10)
    plt.imshow(grid, cmap=plt.get_cmap("Blues", 6))
    plt.colorbar(extend="both")
    plt.clim(-1, 1)
    assert plt.gca()._colorbar["levels"] == 6
    heatmap = next(t for t in _compiled_traces() if t.kind == "heatmap")
    finite = heatmap.grid.values[np.isfinite(heatmap.grid.values)]
    assert np.unique(finite).size <= 6


def test_discrete_colorbar_renders_solid_bands():
    np.random.seed(8)
    x, y = np.random.randn(300), np.random.randn(300)
    plt.scatter(x, y, c=y, cmap=plt.get_cmap("plasma", 4))
    plt.colorbar()
    assert _blob("colorbar_options")["levels"] == 4
    _svg()
    _png()


def test_boundary_norm_is_shared_by_imshow_pcolormesh_and_colorbar():
    pytest.importorskip("matplotlib")
    from matplotlib.colors import BoundaryNorm

    boundaries = [-3.0, -1.0, 0.0, 4.0]
    norm = BoundaryNorm(boundaries, ncolors=256)
    values = np.asarray([[-2.0, -0.5, 2.0]])

    fig, (image_ax, mesh_ax) = plt.subplots(1, 2)
    image = image_ax.imshow(values, norm=norm, cmap="RdYlBu")
    mesh = mesh_ax.pcolormesh(values, norm=norm, cmap="RdYlBu")

    for entry in (image._entry, mesh._entry):
        assert entry["discrete_levels"] == 3
        np.testing.assert_array_equal(entry["discrete_boundaries"], boundaries)
        assert np.asarray(entry["discrete_colors"]).shape == (3, 3)
        rendered = np.asarray(entry["z"] if "z" in entry else entry["args"][0])
        assert rendered.shape[-1] == 4

    fig.colorbar(
        image,
        ax=image_ax,
        spacing="proportional",
        ticks=boundaries,
        format=plt.FuncFormatter(lambda value, _position: f"{value:g} units"),
    )
    options = image_ax._colorbar
    assert options["spacing"] == "proportional"
    assert options["boundaries"] == boundaries
    assert options["tick_labels"] == ["-3 units", "-1 units", "0 units", "4 units"]
    assert len(options["band_colors"]) == 3

    svg = _svg()
    assert all(f">{value}<" in svg for value in options["tick_labels"])


def _colorbar_bands(svg: str) -> list[tuple[float, str]]:
    """``(height, fill)`` of each Rust-drawn colorbar band, bottom to top."""
    import re

    return [
        (float(height), fill)
        for height, fill in re.findall(
            r'data-xy-slot="colorbar_band"[^>]*height="([\d.]+)" fill="([^"]+)"', svg
        )
    ]


@pytest.mark.parametrize(
    ("spacing", "expected_ratio"),
    [("uniform", [1, 1, 1]), ("proportional", [2, 1, 4])],
)
def test_boundary_norm_colorbar_spacing_is_drawn_by_rust(spacing, expected_ratio):
    """Uniform bands are equal; proportional bands follow the boundary values."""
    pytest.importorskip("matplotlib")
    from matplotlib.colors import BoundaryNorm

    boundaries = [-3.0, -1.0, 0.0, 4.0]
    fig, ax = plt.subplots()
    image = ax.imshow(
        np.asarray([[-2.0, -0.5, 2.0]]), norm=BoundaryNorm(boundaries, 256), cmap="RdYlBu"
    )
    fig.colorbar(image, spacing=spacing, ticks=boundaries)
    bands = _colorbar_bands(_svg())
    assert len(bands) == 3
    heights = [height for height, _ in bands]
    assert heights == pytest.approx(
        [ratio * heights[0] / expected_ratio[0] for ratio in expected_ratio], abs=0.02
    )
    # Bands are literal solid colors, bottom (lowest) first: no interpolation.
    assert len({fill for _, fill in bands}) == 3
    assert [fill for _, fill in bands] == [
        f"rgba({r},{g},{b},1.000000)" for r, g, b in image._entry["discrete_colors"]
    ]


def _cap_fills(svg: str) -> dict[str, tuple[int, int, int]]:
    import re

    return {
        side: tuple(int(channel) for channel in re.findall(r"\d+", fill)[:3])
        for side, fill in re.findall(
            r'data-xy-slot="colorbar_extend_(min|max)"[^>]*fill="([^"]+)"', svg
        )
    }


def _matplotlib_cap_fills(artist, norm, cmap, extend):
    """Facecolors of the real Matplotlib colorbar's extension patches."""
    import matplotlib
    import matplotlib.pyplot as mpl_plt

    previous = matplotlib.get_backend()
    mpl_plt.switch_backend("Agg")
    try:
        fig, ax = mpl_plt.subplots()
        values = np.asarray([[0.5, 1.5, 2.5]])
        mappable = getattr(ax, artist)(values, norm=norm, cmap=cmap)
        colorbar = (
            fig.colorbar(mappable) if extend is None else fig.colorbar(mappable, extend=extend)
        )
        effective = norm.extend if extend is None else extend
        sides = [side for side in ("min", "max") if effective in ("both", side)]
        fills = {
            side: tuple(round(255 * channel) for channel in patch.get_facecolor()[:3])
            for side, patch in zip(sides, colorbar._extend_patches, strict=True)
        }
        mpl_plt.close(fig)
        return fills
    finally:
        mpl_plt.switch_backend(previous)


def _boundary_norm_cases():
    import matplotlib
    from matplotlib.colors import BoundaryNorm

    viridis = matplotlib.colormaps["viridis"]
    extremes = viridis.with_extremes(under="#ff0000", over="#00ff00")
    edges = [0.0, 1.0, 2.0, 3.0]
    return {
        # ncolors == cmap.N: cap indices are the LUT ends.
        "ncolors_eq_N": (lambda: BoundaryNorm(edges, 256), viridis),
        # ncolors < cmap.N: the over cap is the last of a resampled range.
        "ncolors_lt_N": (lambda: BoundaryNorm(edges, 4), viridis),
        # clip=True bypasses explicit extremes: caps are the endpoint LUT colors.
        "clip_with_extremes": (lambda: BoundaryNorm(edges, 256, clip=True), extremes),
        # clip=False with extremes and extend="neither": the extremes are drawn.
        "extremes_neither": (lambda: BoundaryNorm(edges, 256), extremes),
        # The norm's own extend resamples the LUT before the cap lookup.
        "norm_extend_both": (lambda: BoundaryNorm(edges, 256, extend="both"), extremes),
    }


@pytest.mark.parametrize("artist", ["imshow", "pcolormesh"])
@pytest.mark.parametrize("extend", ["both", "min", "max"])
@pytest.mark.parametrize(
    "case",
    ["ncolors_eq_N", "ncolors_lt_N", "clip_with_extremes", "extremes_neither", "norm_extend_both"],
)
def test_boundary_norm_colorbar_caps_match_matplotlib_extension_patches(case, extend, artist):
    """Caps are ``cmap(norm(value just beyond the edge))``, read off a real colorbar."""
    pytest.importorskip("matplotlib")
    make_norm, cmap = _boundary_norm_cases()[case]
    expected = _matplotlib_cap_fills(artist, make_norm(), cmap, extend)
    fig, ax = plt.subplots()
    mappable = getattr(ax, artist)(np.asarray([[0.5, 1.5, 2.5]]), norm=make_norm(), cmap=cmap)
    fig.colorbar(mappable, extend=extend)
    svg = _svg()
    assert _cap_fills(svg) == expected
    band_fills = {fill for _, fill in _colorbar_bands(svg)}
    assert len(band_fills) == 3


@pytest.mark.parametrize(
    ("new_ticks", "expected"),
    [
        ([0.0, 0.5, 2.5, 3.0], ["0.0 u", "0.5 u", "2.5 u", "3.0 u"]),
        ([0.0, 1.0, 3.0], ["0.0 u", "1.0 u", "3.0 u"]),
        ([0.0, 0.25, 1.5, 2.0, 2.75, 3.0], ["0.0 u", "0.2 u", "1.5 u", "2.0 u", "2.8 u", "3.0 u"]),
    ],
)
def test_boundary_norm_colorbar_labels_follow_set_ticks(new_ticks, expected):
    """A formatter is re-applied to the live ticks (equal, fewer and more ticks)."""
    import re

    pytest.importorskip("matplotlib")
    from matplotlib.colors import BoundaryNorm

    fig, ax = plt.subplots()
    image = ax.imshow(
        np.asarray([[0.5, 1.5, 2.5]]), norm=BoundaryNorm([0.0, 1.0, 2.0, 3.0], 256), cmap="viridis"
    )
    colorbar = fig.colorbar(image, ticks=[0, 1, 2, 3], format="%.1f u")
    colorbar.set_ticks(new_ticks)
    assert re.findall(r">([\d.]+ u)<", _svg()) == expected


def _contourf_with_explicit_levels():
    grid = np.linspace(0, 1, 12)
    fig, ax = plt.subplots()
    return fig, ax.contourf(np.add.outer(grid, grid * 3) * 3, levels=[0, 1, 3, 10], cmap="viridis")


def test_contourf_colorbar_without_band_colors_still_rejects_spacing():
    """Spacing belongs to the discrete path; a boundary-only ramp must not gain it.

    A plain colormapped contourf now carries band colors (#1046). A contourf
    mapped through a custom norm still has boundaries but no band colors, so it
    stays a continuous ramp; admitting ``spacing="proportional"`` there would
    export a smooth gradient where Matplotlib draws solid bands, so it keeps the
    ``XYG_STATIC_UNSUPPORTED_PANEL_COLORBAR_STYLE`` rejection.
    """
    pytest.importorskip("matplotlib")
    from matplotlib.colors import Normalize

    grid = np.linspace(0, 1, 12)
    fig, ax = plt.subplots()
    contour = ax.contourf(
        np.add.outer(grid, grid * 3) * 3, levels=[0, 1, 3, 10], norm=Normalize(0, 10)
    )
    fig.colorbar(contour, spacing="proportional")
    with pytest.raises(RuntimeError, match="XYG_STATIC_UNSUPPORTED_PANEL_COLORBAR_STYLE"):
        _svg()


def test_continuous_colorbar_with_formatted_ticks_is_rejected_with_a_stable_reason():
    """Authored tick labels need literal bands; a ramp has none, so it fails closed."""
    plt.imshow(np.arange(6.0).reshape(2, 3))
    plt.colorbar(ticks=[0, 2, 4], format=plt.FuncFormatter(lambda value, _: f"{value:g}u"))
    with pytest.raises(RuntimeError, match="XYG_STATIC_UNSUPPORTED_PANEL_COLORBAR_TICK_LABELS"):
        _svg()


def test_boundary_norm_colorbar_beyond_the_bounded_stop_budget_is_rejected():
    """Scene colorbars carry at most 16 literal stops (15 bands); more fails closed."""
    pytest.importorskip("matplotlib")
    from matplotlib.colors import BoundaryNorm

    plt.imshow(np.arange(6.0).reshape(2, 3), norm=BoundaryNorm(np.linspace(0, 10, 18), 256))
    plt.colorbar()
    with pytest.raises(RuntimeError, match="XYG_SCENE_UNSUPPORTED_COLORBAR"):
        _svg()


# -- defect 7: contour conventions --------------------------------------------


def _wiggle():
    def f(a, b):
        return np.sin(a) ** 10 + np.cos(10 + b * a) * np.cos(a)

    xg = np.linspace(0, 5, 50)
    yg = np.linspace(0, 5, 40)
    xx, yy = np.meshgrid(xg, yg)
    return xx, yy, f(xx, yy)


def test_auto_contour_level_count_matches_maxnlocator():
    xx, yy, zz = _wiggle()
    cs = plt.contour(xx, yy, zz)
    # MaxNLocator(N+1=8) over [-0.997, 1.05] -> 9 levels at 0.3 spacing.
    assert list(np.round(cs.levels, 3)) == [-1.2, -0.9, -0.6, -0.3, 0.0, 0.3, 0.6, 0.9, 1.2]


def test_monochrome_contour_dashes_negative_levels():
    xx, yy, zz = _wiggle()
    plt.contour(xx, yy, zz, colors="black")
    contours = [t for t in _compiled_traces() if t.kind == "contour"]
    assert len(contours) == 2
    expected_width = plt.rcParams["lines.linewidth"] * plt.rcParams["figure.dpi"] / 72.0
    dashed = [trace for trace in contours if trace.style.get("dash") is not None]
    solid = [trace for trace in contours if trace.style.get("dash") is None]
    assert len(dashed) == len(solid) == 1
    assert dashed[0].style["dash"] == pytest.approx([3.7 * expected_width, 1.6 * expected_width])
    assert all(t.style["width"] == pytest.approx(expected_width) for t in contours)
    assert all(t.style["opacity"] == pytest.approx(1.0) for t in contours)


def test_monochrome_contour_dashes_all_negative_levels_with_authored_widths():
    xx, yy, zz = _wiggle()
    widths = np.array([0.5, 2.0])
    levels = np.array([-0.9, -0.6, -0.3])
    _fig, ax = plt.subplots()
    ax.contour(xx, yy, zz, levels=levels, colors="black", linewidths=widths)

    contours = [
        trace for trace in ax._build_chart(640, 480).figure().traces if trace.kind == "contour"
    ]
    point_scale = plt.rcParams["figure.dpi"] / 72.0
    expected_widths = widths[np.arange(len(levels)) % len(widths)] * point_scale

    assert len(contours) == len(levels)
    for trace, expected_width in zip(contours, expected_widths, strict=True):
        assert trace.style["dash"] == pytest.approx([3.7 * expected_width, 1.6 * expected_width])
        assert trace.style_channels["width"].values == pytest.approx(expected_width)


def test_colormapped_contour_stays_solid():
    xx, yy, zz = _wiggle()
    plt.contour(xx, yy, zz, cmap="RdGy")
    contours = [t for t in _compiled_traces() if t.kind == "contour"]
    assert len(contours) == 1
    assert contours[0].style.get("dash") is None


def test_contourf_fills_discrete_bands_not_a_smooth_gradient():
    xx, yy, zz = _wiggle()
    contour_set = plt.contourf(xx, yy, zz, 20, cmap="RdGy")
    plt.colorbar()
    traces = _compiled_traces()
    heatmap = next(t for t in traces if t.kind == "heatmap")
    finite = heatmap.grid.values[np.isfinite(heatmap.grid.values)]
    assert heatmap.grid_shape[0] > zz.shape[0]
    assert heatmap.grid_shape[1] > zz.shape[1]
    # Piecewise-constant bands: far fewer distinct fill values than grid cells.
    assert np.unique(finite).size <= 21
    assert np.unique(finite).size < finite.size
    assert not any(t.kind == "contour" for t in traces)
    colorbar = _blob("colorbar_options")
    assert colorbar["levels"] == len(contour_set.levels) - 1
    assert colorbar["boundaries"] == pytest.approx(contour_set.levels)
    expected_ticks = contour_set.levels[1::3].copy()
    expected_ticks[np.abs(expected_ticks) < 1e-12] = 0.0
    assert colorbar["ticks"] == pytest.approx(expected_ticks)
    assert 0.0 in colorbar["ticks"]


def test_default_contourf_levels_trim_extended_locator_ends() -> None:
    x = np.linspace(-3.0, 5.0, 150)
    y = np.linspace(-3.0, 5.0, 120)
    z = np.cos(x[None, :]) + np.sin(y[:, None])

    _fig, ax = plt.subplots()
    contour = ax.contourf(
        x,
        y,
        z,
        hatches=["-", "/", "\\", "//"],
        cmap="gray",
        extend="both",
    )
    ax.figure.colorbar(contour)

    assert contour.levels == pytest.approx([-1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5])
    assert contour._entry["domain"] == pytest.approx((-1.5, 1.5))
    assert ax._colorbar["domain"] == pytest.approx((-1.5, 1.5))
    assert ax._colorbar["boundaries"] == pytest.approx(contour.levels)
    assert ax._colorbar["extend"] == "both"


def test_explicit_integer_contourf_levels_keep_full_locator_span() -> None:
    x = np.linspace(-3.0, 5.0, 150)
    y = np.linspace(-3.0, 5.0, 120)
    z = np.cos(x[None, :]) + np.sin(y[:, None])

    _fig, ax = plt.subplots()
    contour = ax.contourf(
        x,
        y,
        z,
        6,
        colors="none",
        hatches=[".", "/", "\\", None, "\\\\", "*"],
        extend="lower",
    )

    assert contour.levels == pytest.approx([-2.4, -1.8, -1.2, -0.6, 0.0, 0.6, 1.2, 1.8, 2.4])


def test_contourf_includes_samples_equal_to_the_final_level():
    values = np.array([[0.0, 1.0], [1.0, 2.0]])
    _fig, ax = plt.subplots()
    ax.contourf(values, levels=[0.0, 1.0, 2.0])

    heatmap = next(
        trace for trace in ax._build_chart(640, 480).figure().traces if trace.kind == "heatmap"
    )

    assert heatmap.grid.values.reshape(heatmap.grid_shape)[-1, -1] == 1.5


@pytest.mark.parametrize("origin", ["upper", "lower"])
def test_contourf_named_colormap_extensions_fill_the_image_domain(origin):
    values = np.arange(1.0, 10.0)
    field = values[:, None] * values[None, :]
    _fig, ax = plt.subplots()
    ax.contourf(
        field,
        levels=np.arange(5.0, 70.0, 5.0),
        extend="both",
        origin=origin,
    )

    figure = ax._build_chart(320, 320).figure()
    heatmap = next(trace for trace in figure.traces if trace.kind == "heatmap")
    assert np.isfinite(heatmap.grid.values).all()
    assert "<image " in figure.to_svg()
    assert figure.to_png(scale=1).startswith(b"\x89PNG\r\n\x1a\n")


def _matplotlib_contourf_colorbar(levels, extend, cmap="viridis", **colorbar_kwargs):
    """Band and extension-patch facecolors of a real Matplotlib contourf colorbar."""
    import matplotlib
    import matplotlib.pyplot as mpl_plt

    previous = matplotlib.get_backend()
    mpl_plt.switch_backend("Agg")
    try:
        fig, ax = mpl_plt.subplots()
        grid = np.linspace(-2.0, 6.0, 40).reshape(5, 8)
        mappable = ax.contourf(grid, levels=levels, cmap=cmap, extend=extend)
        colorbar = fig.colorbar(mappable, **colorbar_kwargs)
        fig.canvas.draw()

        def rgb(color):
            return tuple(round(255 * channel) for channel in color[:3])

        bands = [rgb(color) for color in colorbar.solids.get_facecolor()]
        sides = [side for side in ("min", "max") if extend in ("both", side)]
        caps = {
            side: rgb(patch.get_facecolor())
            for side, patch in zip(sides, colorbar._extend_patches, strict=True)
        }
        mpl_plt.close(fig)
        return bands, caps
    finally:
        mpl_plt.switch_backend(previous)


def _band_rgb(svg: str) -> list[tuple[int, int, int]]:
    import re

    return [
        tuple(int(channel) for channel in re.findall(r"\d+", fill)[:3])
        for _, fill in _colorbar_bands(svg)
    ]


#: Largest per-channel gap between xyg's built-in viridis table and Matplotlib 3.11's
#: (indices 139-253). Other maps drift more (jet 23, turbo 15, coolwarm 12,
#: inferno 9): a known pre-existing colormap-table gap, tracked separately.
_VIRIDIS_TABLE_DRIFT = 14


def _assert_bands_close(actual, expected, tolerance=_VIRIDIS_TABLE_DRIFT):
    """Same LUT entry as Matplotlib, up to the documented colormap-table drift."""
    assert len(actual) == len(expected)
    for got, want in zip(actual, expected, strict=True):
        assert max(abs(a - b) for a, b in zip(got, want, strict=True)) <= tolerance, (
            actual,
            expected,
        )
    assert len(set(actual)) == len(actual)


def _xyg_lut_bands(levels, cmap):
    """Band colors read from xyg's own LUT at Matplotlib's index ``floor(t * N)``."""
    from xyg._paint import colormap_lut
    from xyg.pyplot._colors import resolve_cmap

    levels = np.asarray(levels, dtype=np.float64)
    midpoints = (levels[:-1] + levels[1:]) * 0.5
    unit = (midpoints - levels[0]) / (levels[-1] - levels[0])
    index = np.minimum(np.floor(unit * 256), 255)
    rows = colormap_lut(resolve_cmap(cmap), index / 255.0)
    return [tuple(int(channel) for channel in row) for row in rows]


@pytest.mark.parametrize("cmap", ["viridis", "RdYlBu", "jet"])
def test_contourf_colorbar_bands_are_exact_against_the_xyg_lut(cmap):
    levels = [-1.0, 0.0, 1.5, 3.0, 5.0]
    fig, ax = plt.subplots()
    grid = np.linspace(-2.0, 6.0, 40).reshape(5, 8)
    fig.colorbar(ax.contourf(grid, levels=levels, cmap=cmap))
    assert _band_rgb(_svg()) == _xyg_lut_bands(levels, cmap)


@pytest.mark.parametrize("extend", ["neither", "min", "max", "both"])
def test_contourf_colorbar_draws_discrete_bands_like_matplotlib(extend):
    pytest.importorskip("matplotlib")
    levels = [-1.0, 0.0, 1.5, 3.0, 5.0]
    expected_bands, expected_caps = _matplotlib_contourf_colorbar(levels, extend, "viridis")
    fig, ax = plt.subplots()
    grid = np.linspace(-2.0, 6.0, 40).reshape(5, 8)
    fig.colorbar(ax.contourf(grid, levels=levels, cmap="viridis", extend=extend))
    svg = _svg()
    _assert_bands_close(_band_rgb(svg), expected_bands)
    assert _cap_fills(svg) == expected_caps


def test_contourf_colorbar_with_default_levels_matches_matplotlib():
    pytest.importorskip("matplotlib")
    import matplotlib
    import matplotlib.pyplot as mpl_plt

    grid = np.linspace(-2.0, 6.0, 40).reshape(5, 8)
    previous = matplotlib.get_backend()
    mpl_plt.switch_backend("Agg")
    try:
        mfig, max_ = mpl_plt.subplots()
        mpl_contour = max_.contourf(grid, cmap="viridis")
        mcbar = mfig.colorbar(mpl_contour)
        mfig.canvas.draw()
        expected = [
            tuple(round(255 * channel) for channel in color[:3])
            for color in mcbar.solids.get_facecolor()
        ]
        mpl_plt.close(mfig)
    finally:
        mpl_plt.switch_backend(previous)
    fig, ax = plt.subplots()
    fig.colorbar(ax.contourf(grid, cmap="viridis"))
    _assert_bands_close(_band_rgb(_svg()), expected)


def test_contourf_colorbar_admits_proportional_spacing_and_format():
    pytest.importorskip("matplotlib")
    levels = [0.0, 1.0, 3.0, 7.0]
    expected_bands, _ = _matplotlib_contourf_colorbar(
        levels, "neither", spacing="proportional", format="%.1f u"
    )
    fig, ax = plt.subplots()
    grid = np.linspace(0.0, 7.0, 40).reshape(5, 8)
    fig.colorbar(
        ax.contourf(grid, levels=levels, cmap="viridis"),
        spacing="proportional",
        format="%.1f u",
    )
    svg = _svg()
    _assert_bands_close(_band_rgb(svg), expected_bands)
    heights = [height for height, _ in _colorbar_bands(svg)]
    assert heights == pytest.approx([heights[0] * ratio for ratio in (1, 2, 4)], abs=0.02)
    assert ">3.0 u<" in svg


def test_boundary_norm_extend_is_inherited_by_default_and_overridable():
    pytest.importorskip("matplotlib")
    from matplotlib.colors import BoundaryNorm

    edges = [0.0, 1.0, 2.0, 3.0]
    values = np.asarray([[0.5, 1.5, 2.5]])
    for artist in ("imshow", "pcolormesh"):
        # Matplotlib's colorbar extend defaults to norm.extend; read the caps
        # off a real colorbar that is given no extend= either.
        expected = _matplotlib_cap_fills(
            artist, BoundaryNorm(edges, 256, extend="both"), "viridis", None
        )
        assert set(expected) == {"min", "max"}
        fig, ax = plt.subplots()
        mappable = getattr(ax, artist)(
            values, norm=BoundaryNorm(edges, 256, extend="both"), cmap="viridis"
        )
        fig.colorbar(mappable)
        assert ax._colorbar["extend"] == "both"
        assert _cap_fills(_svg()) == expected

        fig, ax = plt.subplots()
        mappable = getattr(ax, artist)(
            values, norm=BoundaryNorm(edges, 256, extend="both"), cmap="viridis"
        )
        fig.colorbar(mappable, extend="neither")
        assert "extend" not in ax._colorbar
        assert _cap_fills(_svg()) == {}


def test_scene_colorbar_stop_budget_matches_rust():
    """The pyplot band guard mirrors the Rust stop budgets; drift fails here."""
    import re

    from xyg.pyplot._plot_types import MAX_SCENE_COLORBAR_STOPS

    root = Path(__file__).resolve().parents[2] / "crates" / "xyg-engine" / "src"
    for name, pattern in (
        ("scene.rs", r"pub const MAX_SCENE_COLORBAR_STOPS: usize = (\d+);"),
        ("scene_chrome_pack.rs", r"const MAX_COLORBAR_STOPS: usize = (\d+);"),
    ):
        found = re.search(pattern, (root / name).read_text())
        assert found is not None, name
        assert int(found.group(1)) == MAX_SCENE_COLORBAR_STOPS, name


def test_contourf_colorbar_beyond_the_scene_stop_budget_keeps_the_ramp():
    """More than 15 bands exceed the Scene stop budget; export stays a ramp, not an error."""
    import hashlib

    grid = np.linspace(0, 1, 30)
    fig, ax = plt.subplots()
    fig.colorbar(ax.contourf(np.add.outer(grid, grid), levels=20, cmap="viridis"))
    buffer = io.BytesIO()
    fig.savefig(buffer, format="svg")
    svg = buffer.getvalue()
    # The ramp is sampled into many thin steps, not 20 level bands.
    assert len(_colorbar_bands(svg.decode())) > 20
    # Golden SHA-256 of the SVG captured from main b2705b73: output is unchanged.
    assert hashlib.sha256(svg).hexdigest() == (
        "a6937fcda700db3170ebc6c7c2503d9b67ddbc0759e880e5fc450c648c08f16c"
    )
