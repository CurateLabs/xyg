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
from xyg._static_document import UnsupportedStaticExport

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


_LOD = "XYG_SCENE_UNSUPPORTED_PUBLIC_LOD"


def _per_item_scatters(n: int) -> dict[str, xyg.Chart]:
    i = np.arange(n, dtype=np.float64)
    x = ((i * 7919.0) % 1009.0) / 1009.0
    y = ((i * 104729.0) % 997.0) / 997.0
    groups = np.asarray([f"g{k}" for k in range(8)])[(i % 8).astype(np.int64)]
    return {
        "numeric color": xyg.chart(xyg.scatter(x=x, y=y, color=x * y)),
        "categorical color": xyg.chart(xyg.scatter(x=x, y=y, color=groups)),
        "size": xyg.chart(xyg.scatter(x=x, y=y, size=1.0 + 4.0 * x)),
    }


@pytest.mark.parametrize("channel", ["numeric color", "categorical color", "size"])
def test_per_item_scatter_above_the_xyta_plane_budget_fails_closed(channel: str) -> None:
    """A 300k per-item scatter's paint plane exceeds one 4 MiB XYTA record.

    Rust refuses it in the public predicate with the stable LOD reason before
    any host materializes the plane (#1006); it used to escape as a host
    ``ValueError: ... output buffer too small``.
    """
    chart = _per_item_scatters(300_000)[channel]
    figure = chart.figure()
    assert figure.traces[0].has_per_item_channels() and not figure.traces[0].use_density()
    assert scene_export_support_reason(figure, width=WIDTH, height=HEIGHT) == _LOD
    for export in (
        lambda: chart.to_svg(width=WIDTH, height=HEIGHT),
        lambda: chart.to_png(width=WIDTH, height=HEIGHT, scale=1),
    ):
        with pytest.raises(UnsupportedStaticExport, match=_LOD):
            export()


@pytest.mark.parametrize("channel", ["numeric color", "categorical color", "size"])
def test_per_item_scatter_within_the_xyta_plane_budget_exports_every_point(channel: str) -> None:
    chart = _per_item_scatters(150_000)[channel]
    svg = chart.to_svg(width=WIDTH, height=HEIGHT)
    assert svg.count("<circle") == 150_000


def test_scene_mark_ceiling_counts_every_trace_before_packing() -> None:
    """Packed rows of all traces share MAX_SCENE_MARKS (#1006).

    A decimated line counts at most 4 x 4,096 rows, so the figure fails closed
    with the LOD reason instead of escaping as a row-packing ValueError.
    """
    rng = np.random.default_rng(1006)
    for scatter_n, line in ((1_999_000, 9_000), (1_990_000, 50_000)):
        lx = np.arange(line, dtype=np.float64)
        chart = xyg.chart(
            xyg.scatter(x=rng.normal(size=scatter_n), y=rng.normal(size=scatter_n), density=False),
            xyg.line(x=lx, y=np.sin(lx)),
        )
        figure = chart.figure()
        assert scene_export_support_reason(figure, width=WIDTH, height=HEIGHT) == _LOD
        with pytest.raises(UnsupportedStaticExport, match=_LOD):
            chart.to_png(width=WIDTH, height=HEIGHT, scale=1)


def test_log_y_nonpositive_rows_follow_each_side_of_the_decimation_threshold() -> None:
    """Pins the documented split for log-y lines with y <= 0 (#1006).

    Above ``DECIMATION_THRESHOLD`` the static Scene keeps exactly the browser
    payload's M4 rows after its decimated log prefilter, so non-positive rows
    are dropped and the line bridges them. At or below the threshold the static
    Scene keeps every authored row and applies the axis's own ``nonpositive``
    policy, as it did before; the browser's direct tier drops those rows, a
    pre-existing static/browser difference recorded in scene-ir.md.
    """
    for n in (5_000, 20_000):
        i = np.arange(n, dtype=np.float64)
        y = np.sin(i / 50.0) * 10.0
        axes = (xyg.x_axis(domain=(0.0, float(n))), xyg.y_axis(type_="log", domain=(0.1, 10.0)))
        figure = xyg.chart(xyg.line(x=i, y=y), *axes, width=WIDTH, height=HEIGHT).figure()
        spec, _ = figure.build_payload(WIDTH)
        browser_rows = spec["traces"][0]["n_marks"]
        assert browser_rows < n  # the browser drops y <= 0 at both sizes
        points = sum(
            len(p.split()) for p in _POLYLINE.findall(figure.to_svg(width=WIDTH, height=HEIGHT))
        )
        if n <= 10_000:
            assert points == n
        else:
            rows = _browser_payload_rows(figure, 1.0)
            assert points == browser_rows == len(rows)
            assert (y[rows] > 0).all()


def test_xyta_record_budget_backstop_is_the_lod_reason_without_the_predicate(monkeypatch) -> None:
    """A host that omits XYEF bit 25 still gets the stable LOD reason (#1006).

    Rust's XYTA materializer returns its distinct over-budget code (-3) when a
    per-item paint plane does not fit one 4 MiB record, and the host relays it
    as ``XYG_SCENE_UNSUPPORTED_PUBLIC_LOD`` instead of a buffer ValueError.
    """
    from xyg import _scene_marshal
    from xyg._scene_observations import UnsupportedSceneV3
    from xyg._scene_v3 import figure_scene

    chart = _per_item_scatters(300_000)["numeric color"]
    figure = chart.figure()
    with pytest.raises(UnsupportedSceneV3, match=_LOD):
        figure_scene(figure, width=WIDTH, height=HEIGHT)
    monkeypatch.setattr(_scene_marshal, "_XYEF_OBS_ITEM_PAINT_PLANE", 0)
    assert scene_export_support_reason(figure, width=WIDTH, height=HEIGHT) == _LOD
    with pytest.raises(UnsupportedStaticExport, match=_LOD):
        chart.to_svg(width=WIDTH, height=HEIGHT)
