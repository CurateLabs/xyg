#!/usr/bin/env python3
"""Generate the deterministic authored-Scene workload used by #116 evidence.

This is deliberately a fixture, not a timing harness.  The CodSpeed and
browser evidence jobs own measurement; they import this workload so every
surface exercises the same public Python chart construction and Scene bytes.
"""

from __future__ import annotations

import argparse
import base64
import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import numpy as np

from xyg import _scene_v3
from xyg._figure import Figure

COUNTS = (100, 10_000, 100_000, 1_000_000)
SCENE_VERSION = 23
_FINAL_SCENE_CHUNKS = (b"XYLG", b"XYCB", b"XYLB")


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
    figure.style = {"background": "#f0f8ff", "--chart-bg": "#f8fafc"}
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (-1.0, 1.0)
    figure.scatter(
        x,
        y,
        color="#3987e5",
        size=4.0,
        opacity=0.8,
        name="observations",
        density=False,
    )
    figure.legend_options = {
        "loc": "upper right",
        "title": "Series",
        # The Scene subset is static; do not let interactive legend policy
        # make this representative fixture fail closed.
        "highlight": False,
        "toggle": False,
    }
    figure.colorbar_options = {
        "domain": [0.0, 1.0],
        "stops": [
            (0.0, [15, 23, 42, 255]),
            (0.5, [14, 165, 233, 255]),
            (1.0, [253, 224, 71, 255]),
        ],
        "ticks": [0.0, 0.5, 1.0],
        "minor_ticks": True,
        "title": "Intensity",
    }
    figure.callout(
        0.75,
        0.5,
        "representative callout",
        style={"label_background": "#ffffff"},
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
    """Return a validated Scene 22 workload for one canonical evidence tier."""
    figure = authored_scene_figure(count)
    annotation_input = _authored_annotation_input(figure)
    if not annotation_input.startswith(b"XYAD\x02\x00\x00\x00"):
        raise AssertionError("authored Scene workload must frame annotations as XYAD v2")

    scene = figure.to_scene()
    if scene[:4] != b"XYGS" or int.from_bytes(scene[4:8], "little") != SCENE_VERSION:
        raise AssertionError("authored Scene workload must compile as Scene 22")
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
        help="write deterministic .bin fixtures and authored-scene-manifest.json here",
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
                    "schema": "xyg-authored-scene-v20-fixture-v1",
                    "count": 100,
                    "scene_base64": base64.b64encode(generated[0][1]).decode("ascii"),
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
        report.append({"count": count, "file": filename, "sceneBytes": len(scene)})
        if args.output_dir:
            (args.output_dir / filename).write_bytes(scene)
    result = {"schema": "xyg-authored-scene-workload-v1", "measurements": report}
    if args.output_dir:
        (args.output_dir / "authored-scene-manifest.json").write_text(
            json.dumps(result, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
