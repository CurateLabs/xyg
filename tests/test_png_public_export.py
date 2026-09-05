"""Public PNG export contract and native encoder selection (M2 #873).

The legacy display-list renderer tests retired with `_raster.py`; the
surviving journeys run through the Rust StaticDocument kernel, and the
encoder unit tests keep pinning `_png.py`'s palette/compression policy.
"""

from __future__ import annotations

import numpy as np
import pytest

from xyg import _native, _png
from xyg._figure import Figure


def _ihdr(png: bytes) -> tuple[int, int, int]:
    import struct

    width, height = struct.unpack(">II", png[16:24])
    (color,) = struct.unpack("B", png[25:26])
    return width, height, color


def _decode_rgba(png: bytes) -> np.ndarray:
    from io import BytesIO

    Image = pytest.importorskip("PIL.Image")

    return np.asarray(Image.open(BytesIO(png)).convert("RGBA"))


def test_every_chart_kind_exports_valid_png() -> None:
    rng = np.random.default_rng(0)
    x = np.linspace(0.0, 10.0, 50)

    def fixed(figure, lo=-0.2, hi=0.2):
        figure.axis_options["x"]["domain"] = (0.0, 10.0)
        figure.axis_options["y"]["domain"] = (lo, hi)
        return figure

    figs = [
        fixed(Figure().line(x, np.sin(x), dash="dashed", curve="smooth")),
        fixed(Figure().area(x, np.abs(np.sin(x)))),
        fixed(Figure().scatter(x, np.cos(x), symbol="triangle", stroke="#111", color=np.sin(x))),
        fixed(
            Figure().bar(
                [0.0, 1.0, 2.0],
                [1.0, 3.0, 2.0],
                corner_radius=(4, 0),
                stroke="#123456",
                stroke_width=2,
            )
        ),
        fixed(Figure().histogram(rng.normal(size=500), corner_radius=2)),
        fixed(Figure().heatmap(rng.random((8, 6)))),
        fixed(Figure().scatter(rng.normal(size=9_000), rng.normal(size=9_000), density=True)),
    ]
    for fig in figs:
        png = fig.to_png(scale=1)
        w, h, _ = _ihdr(png)
        assert (w, h) == (900, 420)  # default figure size at scale 1


def test_scale_multiplies_pixels() -> None:
    fig = Figure(width=320, height=200).line([0.0, 1.0], [0.0, 1.0])
    for scale, dims in [(1, (320, 200)), (2, (640, 400)), (3, (960, 600))]:
        assert _ihdr(fig.to_png(scale=scale))[:2] == dims


def test_dimension_override_and_fluid() -> None:
    fig = Figure(width="100%", height="100%").line([0.0, 1.0], [0.0, 1.0])
    png = fig.to_png(width=500, height=300, scale=1)
    assert _ihdr(png)[:2] == (500, 300)


def test_flat_chart_is_indexed_gradient_chart_is_truecolor() -> None:
    # optimize=True retains the size-oriented palette selection path.
    flat = Figure(width=200, height=120).bar([0.0, 1.0], [1.0, 2.0], color="#2563eb")
    assert _ihdr(flat.to_png(scale=1, optimize=True))[2] in (3, 6)
    # A gradient + AA area blows past 256 colors → truecolor (color type 6).
    x = np.linspace(0.0, 6.0, 40)
    grad = Figure(width=400, height=200)
    grad.axis_options["x"]["domain"] = (0.0, 6.0)
    grad.axis_options["y"]["domain"] = (0.0, 1.5)
    grad.area(x, np.abs(np.sin(x)) + 0.2, fill="linear-gradient(#1e40af, #93c5fd)")
    assert _ihdr(grad.to_png(scale=1, optimize=True))[2] == 6


def test_public_native_png_defaults_fast_and_optimize_preserves_pixels() -> None:
    fig = Figure(width=320, height=180)
    fig.axis_options["x"]["domain"] = (0.0, 8.0)
    fig.axis_options["y"]["domain"] = (-1.0, 1.0)
    fig.line(np.linspace(0.0, 8.0, 200), np.sin(np.linspace(0.0, 8.0, 200)))

    fast = fig.to_png(scale=1)
    optimized = fig.to_png(scale=1, optimize=True)

    assert _ihdr(fast)[2] in (2, 6)
    np.testing.assert_array_equal(_decode_rgba(fast), _decode_rgba(optimized))


def test_png_is_screen_bounded_for_large_lines() -> None:
    n = 9_000
    y = np.cumsum(np.random.default_rng(1).normal(size=n))
    fig = Figure(width=950, height=420).line(np.arange(n, dtype=np.float64), y)
    png = fig.to_png(scale=1)
    # Screen-bounded: the source must not inflate the file. Generous
    # ceiling — a 950x420 chart with M4-decimated ink (2M+ points route to
    # the documented XYG_SCENE_UNSUPPORTED_PUBLIC_LOD fail-close).
    assert len(png) < 400_000, f"PNG not screen-bounded: {len(png)} bytes"
    spec, _ = fig.build_payload()
    assert spec["traces"][0]["n_points"] == n  # source size still recorded (§28)


def test_colormap_matches_lut() -> None:
    # The grid RGBA the rasterizer blits comes straight from `_lut`, so the
    # hottest heatmap cell is the colormap's top color (before blit/compositing).
    from xyg import _scene

    rng = np.random.default_rng(2)
    fig = Figure(width=300, height=300).heatmap(rng.random((8, 8)), colormap="viridis")
    spec, blob = fig.build_payload()
    hm = spec["traces"][0]["heatmap"]
    rgba, _xr, _yr = _scene.grid_rgba("heatmap", hm, blob, spec["columns"], {})
    viridis_top = np.array([253, 231, 37])  # last viridis stop (_svg.COLORMAP_STOPS)
    dist = np.abs(rgba[:, :, :3].astype(int) - viridis_top).sum(axis=2)
    assert int(dist.min()) < 20, f"hottest cell not viridis-top (dist {int(dist.min())})"


def test_png_encoder_selects_indexed_for_few_colors() -> None:
    few = np.zeros((10, 10, 4), np.uint8)
    few[:5] = [255, 0, 0, 255]
    few[5:] = [0, 0, 255, 255]
    assert _ihdr(_png.encode(few))[2] == 3
    many = (np.random.default_rng(3).random((20, 20, 4)) * 255).astype(np.uint8)
    assert _ihdr(_png.encode(many))[2] == 6


def test_png_encoder_uses_balanced_compression_level(monkeypatch) -> None:

    seen: list[tuple[int, int]] = []
    real = _native.encode_png

    def recording(pixels, *, mode: int = 0, compression: int = 6) -> bytes:
        seen.append((mode, compression))
        return real(pixels, mode=mode, compression=compression)

    monkeypatch.setattr(_native, "encode_png", recording)
    few = np.zeros((10, 10, 4), np.uint8)
    many = (np.random.default_rng(4).random((20, 20, 4)) * 255).astype(np.uint8)

    _png.encode(few)
    _png.encode(many)
    _png.png_truecolor(2, 2, np.zeros((2, 2, 4), np.uint8), compression_level=1)

    assert seen == [(0, 6), (0, 6), (1, 1)]


def test_png_encode_is_the_native_converter() -> None:

    few = np.zeros((8, 8, 4), np.uint8)
    few[:4] = [255, 0, 0, 255]
    few[4:] = [0, 0, 255, 128]
    assert _png.encode(few) == _native.encode_png(few, mode=0, compression=6)
    raw = np.ascontiguousarray(few)
    assert _png.png_truecolor(8, 8, raw) == _native.encode_png(raw, mode=1, compression=6)


def _dark_pixel_count(png: bytes, threshold: int = 60) -> int:
    rgba = _decode_rgba(png)
    rgb = rgba[..., :3].astype(np.int64)
    return int(((rgb < threshold).all(axis=-1) & (rgba[..., 3] > 200)).sum())


def mixed_anchor_legend_spec() -> tuple[dict, bytes]:
    """A figure carrying one anchored and one bounded legend box."""
    spec, blob = Figure().line([0.0, 1.0], [0.0, 1.0], name="a").build_payload()
    spec["show_legend"] = False
    spec["extra_legends"] = [
        {
            "title": "anchored",
            "loc": "lower left",
            "anchor": [0.0, 1.0],
            "items": [{"name": "outside", "kind": "line", "style": {}}],
        },
        {
            "title": "bounded",
            "loc": "upper right",
            "items": [{"name": "inside", "kind": "line", "style": {}}],
        },
    ]
    return spec, blob
