"""Static export takes the browser payload's LOD tiers (#1006, dossier §28).

A line above ``DECIMATION_THRESHOLD`` exports as the browser's M4 rows (same
``payload_m4_indices`` kernel, same bucket count, same x window); a scatter
the browser ships direct exports one marker per point; a scatter the browser
ships as density exports one density Image. Small charts are unchanged.
"""

from __future__ import annotations

import hashlib
import io
import re

import numpy as np
import pytest

import xyg
from xyg import _native
from xyg._scene_v3 import scene_export_support_reason

WIDTH = 720
HEIGHT = 420
_POLYLINE = re.compile(r'<polyline points="([^"]*)"')


def _line(n: int) -> tuple[np.ndarray, np.ndarray]:
    i = np.arange(n, dtype=np.float64)
    return i * 0.25, ((i * 7919.0) % 1009.0) / 10.0 - (i % 97.0)


def _polyline_points(svg: str) -> np.ndarray:
    (points,) = _POLYLINE.findall(svg)
    return np.asarray(
        [[float(v) for v in pair.split(",")] for pair in points.split()], dtype=np.float64
    )


def _browser_m4(figure, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    x0, x1 = (float(v) for v in figure._range("x"))
    tier, idx = _native.payload_m4_indices(len(x), x, y, min(x0, x1), max(x0, x1), WIDTH)
    assert tier == 1
    return idx.astype(np.int64)


def _browser_payload_rows(figure, x_step: float, x_origin: float = 0.0) -> np.ndarray:
    """Source rows the browser's first-paint payload actually ships.

    The line fixtures place row ``i`` at ``x_origin + i * x_step``, so the
    offset-f32 x column of ``build_payload`` decodes back to exact row indices.
    """
    spec, blob = figure.build_payload(WIDTH)
    (trace,) = spec["traces"]
    assert trace["tier"] == "decimated"
    assert trace["decimation_px"] == WIDTH
    column = spec["columns"][trace["x"]]
    assert column["kind"] == "float"
    values = np.frombuffer(blob, dtype="<f4", count=column["len"], offset=column["byte_offset"])
    decoded = values.astype(np.float64) * column["scale"] + column["offset"]
    rows = np.rint((decoded - x_origin) / x_step).astype(np.int64)
    assert np.abs(decoded - (x_origin + rows * x_step)).max() < x_step / 4
    return rows


# Recorded from the pre-change main (8ce49667) native core before any change:
# charts at or below the thresholds must stay byte-identical.
_HEAD_10K_LINE_SVG = "2c5d6aa0824087ae4249eb5b3a952e398bc98ab56f3736dd3b47df17a95f34a6"
_HEAD_10K_LINE_PNG = "c37a53a174eb869828bb4d49a3605d790e3af6955cb78f53ca7da6bd4a6c352d"
_HEAD_10K_SCATTER_SVG = "9ca3a2bab240ded3408b7270e4a54efd31d4d51fc4505fb4eda46d2b9fc67bbd"


def test_ten_thousand_point_line_and_scatter_are_byte_identical_to_before() -> None:
    x, y = _line(10_000)
    line = xyg.chart(xyg.line(x=x, y=y)).figure()
    svg = line.to_svg(width=WIDTH, height=HEIGHT)
    assert hashlib.sha256(svg.encode()).hexdigest() == _HEAD_10K_LINE_SVG
    assert len(_polyline_points(svg)) == 10_000
    png = line.to_png(width=WIDTH, height=HEIGHT, scale=1.0)
    assert hashlib.sha256(png).hexdigest() == _HEAD_10K_LINE_PNG
    scatter = xyg.chart(xyg.scatter(x=x, y=y)).figure()
    svg = scatter.to_svg(width=WIDTH, height=HEIGHT)
    assert hashlib.sha256(svg.encode()).hexdigest() == _HEAD_10K_SCATTER_SVG


@pytest.mark.parametrize("n", [100_000, 1_000_000])
def test_large_line_exports_the_browser_m4_rows(n: int) -> None:
    x, y = _line(n)
    figure = xyg.chart(xyg.line(x=x, y=y)).figure()
    assert scene_export_support_reason(figure, width=WIDTH, height=HEIGHT) is None
    svg = figure.to_svg(width=WIDTH, height=HEIGHT)
    points = _polyline_points(svg)
    idx = _browser_m4(figure, x, y)

    # Same rows as the browser payload at this width, at most 4 per bucket:
    # the shipped first-paint x column decodes to exactly these source rows.
    assert len(points) == len(idx) <= 4 * WIDTH
    np.testing.assert_array_equal(_browser_payload_rows(figure, 0.25), idx)

    # Each vertex is the affine image of exactly that source row.
    ax = np.polyfit(x[idx], points[:, 0], 1)
    ay = np.polyfit(y[idx], points[:, 1], 1)
    assert np.abs(np.polyval(ax, x[idx]) - points[:, 0]).max() < 0.011
    assert np.abs(np.polyval(ay, y[idx]) - points[:, 1]).max() < 0.011

    # Independently: every bucket's first/last/min/max row survives.
    x0, x1 = (float(v) for v in figure._range("x"))
    bucket = np.minimum(
        ((x - x0) * (WIDTH / ((x1 + np.finfo(float).eps) - x0))).astype(np.int64), WIDTH - 1
    )
    kept = set(idx.tolist())
    starts = np.flatnonzero(np.r_[True, bucket[1:] != bucket[:-1]])
    ends = np.r_[starts[1:], n]
    for lo, hi in zip(starts, ends, strict=True):
        segment = y[lo:hi]
        for row in (lo, hi - 1, lo + int(np.argmin(segment)), lo + int(np.argmax(segment))):
            assert row in kept

    png = figure.to_png(width=WIDTH, height=HEIGHT, scale=1.0)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert figure.to_image("pdf", width=WIDTH, height=HEIGHT).startswith(b"%PDF")


def test_decimated_line_paints_like_a_line_of_its_m4_rows() -> None:
    """SVG and PNG pixels equal a direct chart of the kept rows."""
    x, y = _line(100_000)
    figure = xyg.chart(xyg.line(x=x, y=y)).figure()
    idx = _browser_m4(figure, x, y)
    domains = [tuple(float(v) for v in figure._range(axis)) for axis in ("x", "y")]
    direct = xyg.chart(
        xyg.line(x=x[idx], y=y[idx]),
        xyg.x_axis(domain=domains[0]),
        xyg.y_axis(domain=domains[1]),
    ).figure()
    assert direct.to_svg(width=WIDTH, height=HEIGHT) == figure.to_svg(width=WIDTH, height=HEIGHT)
    assert direct.to_png(width=WIDTH, height=HEIGHT, scale=2.0) == figure.to_png(
        width=WIDTH, height=HEIGHT, scale=2.0
    )


def test_log_x_line_bins_in_axis_coordinates_like_the_browser() -> None:
    """Log x: the static Scene keeps the browser payload's log-space M4 rows."""
    n = 200_000
    i = np.arange(n, dtype=np.float64)
    x = 1.0 + i * 0.25
    y = ((i * 7919.0) % 1009.0) / 10.0 + 1.0
    # A log axis is domain-shaping, so static export needs an authored domain.
    axes = (xyg.x_axis(type_="log", domain=(1.0, float(x[-1]))), xyg.y_axis(domain=(0.0, 102.0)))
    figure = xyg.chart(xyg.line(x=x, y=y), *axes).figure()
    assert scene_export_support_reason(figure, width=WIDTH, height=HEIGHT) is None
    rows = _browser_payload_rows(figure, 0.25, 1.0)
    # Log binning concentrates buckets at small x, so it differs from linear.
    assert len(rows) != len(_browser_m4(figure, x, y))
    direct = xyg.chart(xyg.line(x=x[rows], y=y[rows]), *axes).figure()
    assert direct.to_svg(width=WIDTH, height=HEIGHT) == figure.to_svg(width=WIDTH, height=HEIGHT)


def test_large_step_line_decimates_before_step_expansion() -> None:
    x, y = _line(50_000)
    figure = xyg.chart(xyg.step(x=x, y=y, where="post")).figure()
    svg = figure.to_svg(width=WIDTH, height=HEIGHT)
    idx = _browser_m4(figure, x, y)
    # A post step draws one corner between consecutive kept rows.
    assert len(_polyline_points(svg)) == 2 * len(idx) - 1


def test_large_line_fails_closed_where_the_m4_tier_does_not_hold() -> None:
    x, y = _line(20_000)
    gap = y.copy()
    gap[123] = np.nan
    nonfinite = xyg.chart(xyg.line(x=x, y=gap)).figure()
    assert scene_export_support_reason(nonfinite, width=WIDTH, height=HEIGHT) == (
        "Scene v12 does not yet encode missing-data breaks or nonfinite coordinates"
    )
    # Line marks sort x at ingest (§28); a mutated trace that is no longer
    # ascending cannot be M4-binned, so it fails closed instead.
    unsorted = xyg.chart(xyg.line(x=x, y=y)).figure()
    unsorted.traces[0].x = unsorted.store.ingest(x[::-1].copy())
    assert (
        scene_export_support_reason(unsorted, width=WIDTH, height=HEIGHT)
        == "XYG_SCENE_UNSUPPORTED_PUBLIC_LOD"
    )
    polar = xyg.polar_chart(xyg.line(x=np.linspace(0, 1, 10_001), y=np.ones(10_001))).figure()
    assert scene_export_support_reason(polar, width=WIDTH, height=HEIGHT) == (
        "XYG_SCENE_UNSUPPORTED_PUBLIC_LOD"
    )


def test_direct_tier_scatter_exports_one_marker_per_point() -> None:
    rng = np.random.default_rng(1004)
    x, y = rng.normal(size=100_000), rng.normal(size=100_000)
    figure = xyg.chart(xyg.scatter(x=x, y=y)).figure()
    assert not figure.traces[0].use_density()
    spec, _ = figure.build_payload(WIDTH)
    assert spec["traces"][0]["tier"] == "direct"
    assert spec["traces"][0]["n_marks"] == 100_000
    svg = figure.to_svg(width=WIDTH, height=HEIGHT)
    assert svg.count("<circle") == 100_000
    assert "<image" not in svg
    png = figure.to_png(width=WIDTH, height=HEIGHT, scale=1.0)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_categorical_scatter_keeps_per_item_paint_on_the_direct_tier() -> None:
    n = 100_000
    rng = np.random.default_rng(7)
    groups = np.asarray([f"group-{i % 8}" for i in range(n)])
    figure = xyg.chart(
        xyg.scatter(x=rng.normal(size=n), y=rng.normal(size=n), color=groups)
    ).figure()
    assert figure.traces[0].has_per_item_channels() and not figure.traces[0].use_density()
    svg = figure.to_svg(width=WIDTH, height=HEIGHT)
    assert svg.count("<circle") == n
    assert len(set(re.findall(r'<circle [^>]*fill="([^"]+)"', svg))) == 8


def test_density_tier_scatter_exports_one_density_image() -> None:
    rng = np.random.default_rng(1004)
    x, y = rng.normal(size=300_000), rng.normal(size=300_000)
    figure = xyg.chart(xyg.scatter(x=x, y=y)).figure()
    assert figure.traces[0].use_density()
    spec, _ = figure.build_payload(WIDTH)
    assert spec["traces"][0]["tier"] == "density"
    svg = figure.to_svg(width=WIDTH, height=HEIGHT)
    assert svg.count("<image") == 1
    assert "<circle" not in svg
    assert len(svg) < 200_000


def test_pyplot_large_line_savefig_uses_the_m4_tier() -> None:
    from xyg import pyplot as plt

    x, y = _line(100_000)
    plt.close("all")
    fig, ax = plt.subplots()
    ax.plot(x, y)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="svg")
    svg = buffer.getvalue().decode()
    plt.close("all")
    assert 0 < len(_polyline_points(svg)) <= 4 * 4096
