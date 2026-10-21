"""Polar wedges export as exact SVG arcs; raster keeps the flattened polygon.

Rust tessellates every polar bar/column/histogram/heatmap wedge into a
PolyFill vertex run for the raster and browser painters. The Scene also carries
the wedge's exact circle geometry (`XYWA`, scene-ir.md "Polar wedge SVG arcs"),
so static SVG writes `M … A … L … A … Z` with the arc endpoints taken from the
flattened run, and the PDF converted from that SVG draws Bézier arcs. Native
PNG output is byte-identical to the pre-arc HEAD.
"""

from __future__ import annotations

import hashlib
import math
import re
import zlib

import numpy as np

import xyg
from xyg._pdf import svg_to_pdf

_PATH = re.compile(r'<path d="([^"]*)"')
_CLIP_CIRCLE = re.compile(r'<clipPath id="[^"]*"><circle cx="([^"]+)" cy="([^"]+)" r="([^"]+)"/>')

# Native PNG digests recorded from the pre-arc native core (this branch before XYWA):
# the exact-arc sidecar must never reach the raster path.
_HEAD_ROSE_PNG = "eaef5b30e2fa07399e0b837376fd57a3c3b91ee180b860e4a13c56d8934a8dbd"
_HEAD_POLAR_BAR_PNG = "c87d79ebb18af53d0a32402dd8ff27ec1cbcab39f2c25375b6e115000775212a"


def _rose() -> xyg.Chart:
    # Same observations as benchmarks/test_codspeed_polar.py.
    rng = np.random.default_rng(19)
    directions = rng.uniform(0.0, 360.0, 50_000)
    speeds = rng.gamma(2.0, 3.0, 50_000)
    return xyg.wind_rose(directions, speeds, sectors=16)


def _polar_bar() -> xyg.Chart:
    theta = np.array([0.0, 90.0, 180.0, 270.0])
    radius = np.array([1.0, 2.0, 3.0, 2.0])
    return xyg.polar_bar_chart(
        xyg.bar(theta, radius, width=22.5),
        xyg.theta_axis(unit="degrees"),
        width=240,
        height=240,
    )


def _wedge_paths(svg: str) -> list[list[str]]:
    return [d.split(" ") for d in _PATH.findall(svg)]


def _arcs(tokens: list[str]) -> list[tuple[float, float, float, float]]:
    """Every `A rx ry rot large sweep x y` as (radius, large, x, y)."""
    out = []
    for at, token in enumerate(tokens):
        if token == "A":
            rx, ry, rot, large, _sweep, x, y = tokens[at + 1 : at + 8]
            assert rx == ry and rot == "0"
            out.append((float(rx), float(large), float(x), float(y)))
    return out


def _clip_circle(svg: str) -> tuple[float, float, float]:
    match = _CLIP_CIRCLE.search(svg)
    assert match is not None
    cx, cy, r = (float(v) for v in match.groups())
    return cx, cy, r


def test_wind_rose_wedges_are_exact_arcs_through_their_flattened_ends() -> None:
    svg = _rose().figure().to_svg(width=720, height=720)
    paths = _wedge_paths(svg)
    assert len(paths) == 16 * 4
    cx, cy, _ = _clip_circle(svg)
    for tokens in paths:
        assert tokens[0] == "M" and tokens[-1] == "Z" and "L" in tokens
        arcs = _arcs(tokens)
        assert arcs, tokens
        for radius, large, x, y in arcs:
            # Sixteen sectors never need a large arc; every arc end sits on
            # its circle (two-decimal SVG rounding).
            assert large == 0.0
            assert math.isclose(math.hypot(x - cx, y - cy), radius, abs_tol=0.02)
    # The innermost band starts at the disc centre; outer bands are annular.
    centre = [tokens for tokens in paths if float(tokens[1]) == cx and float(tokens[2]) == cy]
    assert len(centre) == 16
    assert all(len(_arcs(tokens)) == 1 for tokens in centre)
    assert sum(len(_arcs(tokens)) == 2 for tokens in paths) == 48


def test_polar_bar_arc_radii_are_the_projected_outer_and_inner_radii() -> None:
    # Bars span base..base+value and the radial autorange ends at the largest
    # top (5), with the plot circle as its outer ring.
    chart = xyg.polar_bar_chart(
        xyg.bar(np.array([0.0, 120.0, 240.0]), np.array([4.0, 3.0, 2.0]), width=60.0, base=1.0),
        xyg.theta_axis(unit="degrees"),
        width=400,
        height=400,
    )
    svg = chart.figure().to_svg(width=400, height=400)
    cx, cy, plot_radius = _clip_circle(svg)
    paths = _wedge_paths(svg)
    assert len(paths) == 3
    for tokens, value in zip(paths, (4.0, 3.0, 2.0), strict=True):
        (outer, _, ox, oy), (inner, _, ix, iy) = _arcs(tokens)
        assert math.isclose(outer, plot_radius * (1.0 + value) / 5.0, abs_tol=0.011)
        assert math.isclose(inner, plot_radius * 1.0 / 5.0, abs_tol=0.011)
        assert math.isclose(math.hypot(ox - cx, oy - cy), outer, abs_tol=0.02)
        assert math.isclose(math.hypot(ix - cx, iy - cy), inner, abs_tol=0.02)
        # Outer arc forward, inner arc reversed: opposite sweep flags.
        sweeps = [tokens[at + 5] for at, token in enumerate(tokens) if token == "A"]
        assert sorted(sweeps) == ["0", "1"]


def test_full_turn_annulus_splits_each_circle_into_two_arcs() -> None:
    chart = xyg.polar_bar_chart(
        xyg.bar(np.array([180.0]), np.array([4.0]), width=360.0, base=2.0),
        xyg.theta_axis(unit="degrees"),
        width=400,
        height=400,
    )
    svg = chart.figure().to_svg(width=400, height=400)
    (tokens,) = _wedge_paths(svg)
    arcs = _arcs(tokens)
    assert len(arcs) == 4
    assert all(large == 0.0 for _, large, _, _ in arcs)
    cx, cy, plot_radius = _clip_circle(svg)
    # The ring spans base 2 to top 6 on a 0..6 radial axis.
    outer, inner = (radius for radius, *_ in arcs[::2])
    assert math.isclose(outer, plot_radius, abs_tol=0.011)
    assert math.isclose(inner, plot_radius / 3.0, abs_tol=0.011)
    # Each circle's halves meet at the antipode of the 0-degree start.
    assert math.isclose(arcs[0][2], cx - plot_radius, abs_tol=0.011)
    assert math.isclose(arcs[0][3], cy, abs_tol=0.011)


def test_native_png_keeps_the_flattened_polygons_byte_identical() -> None:
    rose = _rose().figure().to_png(engine=xyg.Engine.default, scale=1.0)
    bar = _polar_bar().figure().to_png(engine=xyg.Engine.default, scale=1.0)
    assert hashlib.sha256(rose).hexdigest() == _HEAD_ROSE_PNG
    assert hashlib.sha256(bar).hexdigest() == _HEAD_POLAR_BAR_PNG


def test_pdf_draws_wedge_arcs_as_curves() -> None:
    svg = _polar_bar().figure().to_svg(width=240, height=240)
    assert all(_arcs(tokens) for tokens in _wedge_paths(svg))
    pdf = svg_to_pdf(svg)
    assert pdf.startswith(b"%PDF-1.4")
    assert svg_to_pdf(svg) == pdf
    content = b"".join(
        zlib.decompress(stream)
        for stream in re.findall(rb"/FlateDecode[^>]*>>\nstream\n(.*?)\nendstream", pdf, re.S)
        if stream
    )
    assert re.search(rb"(?m)^(?:[-\d.]+ ){6}c$", content)
