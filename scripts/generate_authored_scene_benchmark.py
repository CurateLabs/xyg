#!/usr/bin/env python3
"""Generate the deterministic authored-Scene workload used by #116 evidence.

This is deliberately a fixture, not a timing harness.  The CodSpeed and
browser evidence jobs own measurement; they import this workload so every
surface exercises the same public Python chart construction and Scene bytes.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import numpy as np

from xyg import _native, _scene_v3, kernels
from xyg._figure import Figure

COUNTS = (100, 10_000, 100_000, 1_000_000)
SCENE_VERSION = 26
_FINAL_SCENE_CHUNKS = (b"XYLG", b"XYCB", b"XYLB")

# One shared, declarative Cartesian chrome workload. The Node parity test reads
# the same value from ``tests/fixtures/authored_scene_v20.json``; keep all
# layout-affecting literals here rather than letting either host inherit an
# unrelated default.
AUTHORED_AXES = {
    "x": {
        "domain": (0.0, 1.0),
        "label": "Fraction",
        "side": "top",
        "tick_sides": ("bottom", "top"),
        "tick_label_sides": ("top",),
        "tick_values": (0.0, 0.5, 1.0),
        "minor_tick_values": (0.25, 0.75),
        "style": {
            "axis_color": "#0b0c0d",
            "grid_color": "#0e0f10",
            "tick_color": "#111213",
            "axis_width": 2.0,
            "grid_width": 1.25,
            "tick_width": 2.5,
            "tick_length": 7.0,
        },
        "minor_style": {
            "grid_color": "#141516",
            "tick_color": "#171819",
            "grid_width": 0.5,
            "tick_width": 1.25,
            "tick_length": 3.0,
            "tick_direction": "in",
        },
    },
    "y": {
        "domain": (-1.0, 1.0),
        "label": "Signal",
        "side": "right",
        "tick_sides": ("left", "right"),
        "tick_label_sides": ("right",),
        "tick_values": (-1.0, 0.0, 1.0),
        "minor_tick_values": (-0.5, 0.5),
        "style": {
            "axis_color": "#0b0c0d",
            "grid_color": "#0e0f10",
            "tick_color": "#111213",
            "axis_width": 2.0,
            "grid_width": 1.25,
            "tick_width": 2.5,
            "tick_length": 7.0,
        },
        "minor_style": {
            "grid_color": "#141516",
            "tick_color": "#171819",
            "grid_width": 0.5,
            "tick_width": 1.25,
            "tick_length": 3.0,
            "tick_direction": "in",
        },
    },
}

AUTHORED_AUTHORING = {
    "viewport": [960, 540],
    "title": "Authored Scene evidence",
    "style": {"background": "#f0f8ff", "--chart-bg": "#f8fafc"},
    "axes": AUTHORED_AXES,
    "scatter": {
        "id": 0,
        "color": "#3987e5",
        "size": 4.0,
        "opacity": 0.8,
        "symbol": "diamond",
        "name": "observations",
    },
    # A second, deliberately small direct series proves that symbol selection
    # remains authored data rather than host-side Scene chrome policy. Keeping
    # it bounded makes the four evidence tiers exercise identical structure.
    "circle_scatter": {
        "id": 1,
        "x": [0.1, 0.5, 0.9],
        "y": [-0.8, 0.0, 0.8],
        "color": "#e11d48",
        "size": 7.0,
        "opacity": 1.0,
        "symbol": "circle",
        "name": "reference",
    },
    "legend": {"loc": "upper right", "title": "Series", "highlight": False, "toggle": False},
    "colorbar": {
        "domain": [0.0, 1.0],
        "stops": [[0.0, [15, 23, 42, 255]], [0.5, [14, 165, 233, 255]], [1.0, [253, 224, 71, 255]]],
        "ticks": [0.0, 0.5, 1.0],
        "minor_ticks": True,
        "title": "Intensity",
    },
    "callout": {
        "x": 0.75,
        "y": 0.5,
        "text": "representative callout",
        "style": {"label_background": "#ffffff"},
    },
    "wrapped_callout": {
        "x": 0.2,
        "y": -0.35,
        "text": "wrapped annotation evidence\nsecond line",
        "wrap": 128.0,
        "style": {
            "label_background": "#fff3cd",
            "label_border_color": "#a16207",
            "label_border_width": 1.0,
        },
    },
}


def authored_scene_figure(count: int) -> Figure:
    """Build one representative, entirely deterministic public Figure.

    The workload intentionally includes ordinary scatter data plus each
    migrated static-chrome path: a named legend, literal colorbar stops with
    resolved ticks/minors, and a callout label background.  Its domains are
    fixed so the byte shape does not vary by benchmark tier.
    """
    if count not in COUNTS:
        raise ValueError(f"count must be one of {COUNTS}, got {count}")

    # arange avoids platform-dependent PRNG streams; the modular y pattern
    # keeps the same bounded data distribution at every evidence tier.
    indices = np.arange(count, dtype=np.float64)
    x = indices / float(count - 1)
    y = ((indices * 37.0) % 997.0) / 498.0 - 1.0

    figure = Figure(width=960, height=540, title="Authored Scene evidence")
    figure.style = dict(AUTHORED_AUTHORING["style"])
    for axis, options in AUTHORED_AXES.items():
        figure.set_axis(axis, **options)
    figure.scatter(
        x,
        y,
        color=AUTHORED_AUTHORING["scatter"]["color"],
        size=AUTHORED_AUTHORING["scatter"]["size"],
        opacity=AUTHORED_AUTHORING["scatter"]["opacity"],
        symbol=AUTHORED_AUTHORING["scatter"]["symbol"],
        name=AUTHORED_AUTHORING["scatter"]["name"],
        density=False,
    )
    # The shared Node authoring fixture pins identity explicitly; defaults are
    # host-local allocation detail, not canonical Scene policy.
    figure.traces[-1].id = 0
    figure.scatter(
        AUTHORED_AUTHORING["circle_scatter"]["x"],
        AUTHORED_AUTHORING["circle_scatter"]["y"],
        color=AUTHORED_AUTHORING["circle_scatter"]["color"],
        size=AUTHORED_AUTHORING["circle_scatter"]["size"],
        opacity=AUTHORED_AUTHORING["circle_scatter"]["opacity"],
        symbol=AUTHORED_AUTHORING["circle_scatter"]["symbol"],
        name=AUTHORED_AUTHORING["circle_scatter"]["name"],
        density=False,
    )
    figure.traces[-1].id = AUTHORED_AUTHORING["circle_scatter"]["id"]
    figure.legend_options = dict(AUTHORED_AUTHORING["legend"])
    figure.colorbar_options = {
        **AUTHORED_AUTHORING["colorbar"],
        "stops": [tuple(stop) for stop in AUTHORED_AUTHORING["colorbar"]["stops"]],
    }
    figure.callout(
        0.75,
        0.5,
        "representative callout",
        style={"label_background": "#ffffff"},
    )
    figure.callout(
        AUTHORED_AUTHORING["wrapped_callout"]["x"],
        AUTHORED_AUTHORING["wrapped_callout"]["y"],
        AUTHORED_AUTHORING["wrapped_callout"]["text"],
        wrap=AUTHORED_AUTHORING["wrapped_callout"]["wrap"],
        style=dict(AUTHORED_AUTHORING["wrapped_callout"]["style"]),
    )
    return figure


def _authored_annotation_input(figure: Figure) -> bytes:
    """Capture the exact XYAD boundary frame before Rust lowers it to XYLB."""
    captured: list[bytes] = []
    real_encode = _scene_v3._native.scene_batch_encode

    def capture_encode(**kwargs: object) -> bytes:
        annotation_input = kwargs["authored_text_annotations"]
        assert isinstance(annotation_input, bytes)
        captured.append(annotation_input)
        return b"captured"

    with patch.object(_scene_v3._native, "scene_batch_encode", capture_encode):
        assert _scene_v3.figure_scene(figure) == b"captured"
    # Keep an explicit reference so test doubles cannot accidentally hide a
    # changed call path that skips the normal native compiler entry point.
    assert _scene_v3._native.scene_batch_encode is real_encode
    assert len(captured) == 1
    return captured[0]


def authored_scene(count: int) -> bytes:
    """Return a validated Scene 25 workload for one canonical evidence tier."""
    figure = authored_scene_figure(count)
    annotation_input = _authored_annotation_input(figure)
    if not annotation_input.startswith(b"XYAD\x03\x00\x00\x00") or b"XYAW" not in annotation_input:
        raise AssertionError(
            "authored Scene workload must frame wrapped annotations as XYAD v3/XYAW"
        )

    scene = figure.to_scene()
    if scene[:4] != b"XYGS" or int.from_bytes(scene[4:8], "little") != SCENE_VERSION:
        raise AssertionError("authored Scene workload must compile as Scene 25")
    missing = [chunk.decode("ascii") for chunk in _FINAL_SCENE_CHUNKS if chunk not in scene]
    if missing:
        raise AssertionError(f"authored Scene workload is missing resolved chunks: {missing}")
    return scene


def scenes(counts: tuple[int, ...] = COUNTS) -> Iterator[tuple[int, bytes]]:
    """Yield each canonical workload after checking its Scene contract."""
    for count in counts:
        yield count, authored_scene(count)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, choices=COUNTS, action="append")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="write deterministic Scene/Rust-rendered fixtures and authored-scene-manifest.json here",
    )
    parser.add_argument(
        "--write-browser-fixture",
        type=Path,
        help="regenerate the strict-CSP browser fixture from the public Figure workload",
    )
    args = parser.parse_args()
    selected = tuple(args.count) if args.count else COUNTS
    generated = list(scenes(selected))
    if args.write_browser_fixture:
        if selected != (100,):
            raise ValueError("--write-browser-fixture requires exactly --count 100")
        args.write_browser_fixture.write_text(
            json.dumps(
                {
                    "schema": "xyg-authored-scene-v26-fixture-v1",
                    "count": 100,
                    "authoring": AUTHORED_AUTHORING,
                    "scene_base64": base64.b64encode(generated[0][1]).decode("ascii"),
                    "scene_sha256": hashlib.sha256(generated[0][1]).hexdigest(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    report = []
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
    for count, scene in generated:
        filename = f"authored-scene-{count}.bin"
        svg_filename = f"authored-scene-{count}.svg"
        png_filename = f"authored-scene-{count}.png"
        svg = _native.scene_svg(scene)
        png = kernels.rasterize_png(_native.scene_raster_commands(scene), 960, 540)
        # The manifest is deliberately checked alongside Node's independently
        # authored output.  Keeping the digest here means the retained
        # four-tier artifact is useful without checking in its 1M-point blob.
        report.append(
            {
                "count": count,
                "file": filename,
                "sceneBytes": len(scene),
                "sceneSha256": hashlib.sha256(scene).hexdigest(),
                "svgFile": svg_filename,
                "svgSha256": hashlib.sha256(svg.encode()).hexdigest(),
                "pngFile": png_filename,
                "pngSha256": hashlib.sha256(png).hexdigest(),
            }
        )
        if args.output_dir:
            (args.output_dir / filename).write_bytes(scene)
            (args.output_dir / svg_filename).write_text(svg, encoding="utf-8")
            (args.output_dir / png_filename).write_bytes(png)
    result = {"schema": "xyg-authored-scene-workload-v1", "measurements": report}
    if args.output_dir:
        (args.output_dir / "authored-scene-manifest.json").write_text(
            json.dumps(result, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
