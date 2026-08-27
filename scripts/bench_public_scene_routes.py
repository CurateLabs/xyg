#!/usr/bin/env python3
"""Local time/memory/payload baselines for public Scene static-export routes.

This is a reproduction contract, not a CodSpeed or CI timing gate. It compiles
the same golden public hexbin and heatmap fixtures used by Python/Node Scene
tests, plus a small set of already-public Cartesian routes, through
``try_public_*``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import statistics
import sys
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "benchmarks"))

from environment import collect_environment_metadata  # noqa: E402
from xyg import _native, kernels  # noqa: E402
from xyg._figure import Figure  # noqa: E402
from xyg._scene_v3 import (  # noqa: E402
    figure_scene,
    scene_export_support_reason,
    try_public_pdf,
    try_public_png,
    try_public_svg,
)

FIXTURE = ROOT / "tests" / "fixtures" / "figure_scene_v3.json"
HEXBIN_X = [0.5, 1.5, 2.5, 3.5, 1.0, 2.0, 3.0]
HEXBIN_Y = [0.5, 0.5, 0.5, 0.5, 2.0, 2.0, 2.0]
HEXBIN_C = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
HEATMAP_Z = [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]]
HEATMAP_X = [1.0, 2.0, 3.0]
HEATMAP_Y = [1.0, 3.0]


def _hexbin(reduce: str) -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    options: dict[str, object] = {
        "gridsize": (4, 4),
        "range": ((0.0, 4.0), (0.0, 5.0)),
        "color": "#3987e5",
        "opacity": 0.75,
        "name": "hex",
    }
    if reduce == "count":
        figure.hexbin(HEXBIN_X, HEXBIN_Y, **options)
    elif reduce == "mean":
        figure.hexbin(HEXBIN_X, HEXBIN_Y, C=HEXBIN_C, reduce_C_function=np.mean, **options)
    else:
        figure.hexbin(HEXBIN_X, HEXBIN_Y, C=HEXBIN_C, reduce_C_function=np.sum, **options)
    figure.traces[-1].id = 0
    return figure


def _scatter() -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    figure.scatter([1, 2], [2, 3], color="#3987e5", size=6, opacity=0.8)
    return figure


def _heatmap() -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    figure.heatmap(
        HEATMAP_Z,
        x=HEATMAP_X,
        y=HEATMAP_Y,
        color="#3987e5",
        opacity=0.75,
        name="heat",
    )
    figure.traces[-1].id = 0
    return figure


def _literal_geometry() -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 4.0)
    figure.axis_options["y"]["domain"] = (0.0, 5.0)
    figure.line([0, 1, 2], [1, 3, 2], color="#ef4444", width=2)
    figure.traces[-1].id = 0
    figure.bar([0.5, 1.5], [2, 3], color="#22c55e", opacity=0.8)
    figure.traces[-1].id = 1
    return figure


def _triangle_mesh() -> Figure:
    figure = Figure(width=360, height=260)
    figure.axis_options["x"]["domain"] = (0.0, 2.0)
    figure.axis_options["y"]["domain"] = (0.0, 2.0)
    figure.triangle_mesh(
        [-0.25, 1.0],
        [0.25, 0.5],
        [0.75, 2.25],
        [0.25, 0.5],
        [0.25, 1.5],
        [1.25, 1.75],
        name="literal mesh",
        color="#22c55e",
        opacity=0.75,
    )
    figure.traces[-1].id = 0
    return figure


def _violin() -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (-1.0, 5.0)
    figure.axis_options["y"]["domain"] = (-1.0, 5.0)
    figure.violin(
        [[1, 2, 2, 3, 4], [2, 2.5, 3.5]],
        bins=8,
        width=0.7,
        orientation="vertical",
        color="#7c3aed",
        opacity=0.6,
        style={"fill": "#22c55e"},
    )
    figure.traces[-1].id = 0
    return figure


def _box() -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (-2.0, 102.0)
    figure.axis_options["y"]["domain"] = (-2.0, 102.0)
    figure.box(
        [[1, 2, 3, 100], [2, 3, 4, 5]],
        orientation="vertical",
        width=0.7,
        color="#7c3aed",
        opacity=0.6,
        name="dist",
    )
    for trace_id, trace in enumerate(figure.traces):
        trace.id = trace_id
    return figure


ROUTES: tuple[tuple[str, Callable[[], Figure], str | None], ...] = (
    ("hexbin_count", lambda: _hexbin("count"), "public_hexbin_sha256.count"),
    ("hexbin_mean", lambda: _hexbin("mean"), "public_hexbin_sha256.mean"),
    ("hexbin_sum", lambda: _hexbin("sum"), "public_hexbin_sha256.sum"),
    ("heatmap", _heatmap, "public_heatmap_sha256"),
    ("scatter", _scatter, None),
    ("literal_geometry", _literal_geometry, "public_literal_geometry_sha256"),
    ("triangle_mesh", _triangle_mesh, "public_triangle_mesh_sha256"),
    ("violin_vertical", _violin, "public_violin_sha256.vertical"),
    ("box_vertical", _box, "public_box_sha256.vertical"),
)


def _fixture_sha(fixture: dict[str, object], path: str) -> str:
    value: object = fixture
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise SystemExit(f"fixture is missing {path}")
        value = value[part]
    if not isinstance(value, str) or len(value) != 64:
        raise SystemExit(f"fixture {path} is not a SHA-256 hex digest")
    return value


def _median_ms(samples: list[float]) -> float:
    return float(statistics.median(samples))


def _time_ms(fn: Callable[[], object], *, warmups: int, reps: int) -> tuple[float, object]:
    result: object = None
    for _ in range(warmups):
        result = fn()
    samples: list[float] = []
    for _ in range(reps):
        started = time.perf_counter()
        result = fn()
        samples.append((time.perf_counter() - started) * 1_000.0)
    return _median_ms(samples), result


def _measure_route(
    name: str,
    factory: Callable[[], Figure],
    expected_sha: str | None,
    *,
    warmups: int,
    reps: int,
) -> dict[str, object]:
    figure = factory()
    reason = scene_export_support_reason(figure)
    if reason is not None:
        raise SystemExit(f"{name} is not a public Scene route: {reason}")

    scene_ms, scene = _time_ms(lambda: figure_scene(figure), warmups=warmups, reps=reps)
    if not isinstance(scene, (bytes, bytearray)):
        raise SystemExit(f"{name} Scene compile did not return bytes")
    digest = hashlib.sha256(scene).hexdigest()
    if expected_sha is not None and digest != expected_sha:
        raise SystemExit(f"{name} Scene SHA-256 {digest} != golden {expected_sha}")

    svg_ms, svg = _time_ms(lambda: try_public_svg(figure), warmups=warmups, reps=reps)
    png_ms, png = _time_ms(lambda: try_public_png(figure, scale=1), warmups=warmups, reps=reps)
    pdf_ms, pdf = _time_ms(lambda: try_public_pdf(figure), warmups=warmups, reps=reps)
    if not isinstance(svg, str) or not isinstance(png, (bytes, bytearray)):
        raise SystemExit(f"{name} public SVG/PNG export returned compatibility None")
    if not isinstance(pdf, (bytes, bytearray)):
        raise SystemExit(f"{name} public PDF export returned compatibility None")
    painter = _native.scene_browser_painter(scene)
    raster = _native.scene_raster_commands(scene)
    native_png = kernels.rasterize_png(raster, figure.width, figure.height)
    if bytes(png) != native_png:
        raise SystemExit(f"{name} public PNG is not the Rust Scene raster consumer")

    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "route": name,
        "public": True,
        "width": figure.width,
        "height": figure.height,
        "scene_sha256": digest,
        "expected_scene_sha256": expected_sha,
        "scene_bytes": len(scene),
        "svg_bytes": len(svg.encode("utf-8")),
        "png_bytes": len(png),
        "pdf_bytes": len(pdf),
        "painter_bytes": len(painter),
        "raster_command_bytes": len(raster),
        "scene_ms_median": scene_ms,
        "svg_ms_median": svg_ms,
        "png_ms_median": png_ms,
        "pdf_ms_median": pdf_ms,
        "peak_rss_kb": int(usage.ru_maxrss),
        "painter_magic": painter[:4].decode("ascii"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--reps", type=int, default=7)
    args = parser.parse_args()
    fixture = json.loads(FIXTURE.read_text())
    tracemalloc.start()
    rows = []
    for name, factory, sha_path in ROUTES:
        expected = _fixture_sha(fixture, sha_path) if sha_path else None
        rows.append(_measure_route(name, factory, expected, warmups=args.warmups, reps=args.reps))
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    report = {
        "kind": "public-scene-export-local",
        "schema": "xyg-public-scene-export-v1",
        "measurement_scope": "public-scene-static-export-baseline",
        "warmups": args.warmups,
        "reps": args.reps,
        "environment": collect_environment_metadata(),
        "tracemalloc_current_bytes": current,
        "tracemalloc_peak_bytes": peak,
        "rows": rows,
    }
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
