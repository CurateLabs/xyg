#!/usr/bin/env python3
"""Validate retained #116 Python/Node authored Scene artifacts and Rust consumers."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from xyg import _native

COUNTS = [100, 10_000, 100_000, 1_000_000]
CHROME_TEXT = (
    "Authored Scene evidence",
    "Fraction",
    "Signal",
    "Series",
    "observations",
    "Intensity",
    "representative callout",
)


def read_manifest(directory: Path) -> dict[int, dict[str, object]]:
    value = json.loads((directory / "authored-scene-manifest.json").read_text())
    if value.get("schema") != "xyg-authored-scene-workload-v1":
        raise SystemExit(f"{directory}: unexpected authored Scene manifest schema")
    rows = value.get("measurements")
    if (
        not isinstance(rows, list)
        or [row.get("count") for row in rows if isinstance(row, dict)] != COUNTS
    ):
        raise SystemExit(f"{directory}: authored Scene manifest is missing a canonical tier")
    return {int(row["count"]): row for row in rows if isinstance(row, dict)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("python_dir", type=Path)
    parser.add_argument("node_dir", type=Path)
    args = parser.parse_args()
    python = read_manifest(args.python_dir)
    node = read_manifest(args.node_dir)
    evidence: list[dict[str, object]] = []
    for count in COUNTS:
        py_row, node_row = python[count], node[count]
        filename = str(py_row.get("file"))
        if filename != node_row.get("file"):
            raise SystemExit(f"{count}: Python and Node artifact names differ")
        py_scene = (args.python_dir / filename).read_bytes()
        node_scene = (args.node_dir / filename).read_bytes()
        digest = hashlib.sha256(py_scene).hexdigest()
        if py_scene != node_scene:
            raise SystemExit(f"{count}: public Python and Node Scene bytes differ")
        if digest != py_row.get("sceneSha256") or digest != node_row.get("sceneSha256"):
            raise SystemExit(f"{count}: Scene digest does not match retained manifest")
        if len(py_scene) != py_row.get("sceneBytes") or len(py_scene) != node_row.get("sceneBytes"):
            raise SystemExit(f"{count}: Scene byte count does not match retained manifest")
        svg = _native.scene_svg(py_scene)
        raster = _native.scene_raster_commands(py_scene)
        painter = _native.scene_browser_painter(py_scene)
        for text in CHROME_TEXT:
            encoded = text.encode()
            if text not in svg or encoded not in raster or encoded not in painter:
                raise SystemExit(
                    f"{count}: Rust direct consumer lost authored chrome text {text!r}"
                )
        if not (b"XYLG" in painter and b"XYCB" in painter and b"XYLB" in painter):
            raise SystemExit(f"{count}: browser painter lost resolved authored chrome")
        evidence.append(
            {
                "count": count,
                "sceneBytes": len(py_scene),
                "sceneSha256": digest,
                "svgBytes": len(svg.encode()),
                "rasterBytes": len(raster),
                "painterBytes": len(painter),
                # Native outputs are byte-exact. Browser comparison allows one device pixel
                # because the WebGL canvas is rasterized at device scale.
                "nativeVisualTolerancePx": 0,
                "browserVisualTolerancePx": 1,
            }
        )
    print(
        json.dumps(
            {"schema": "xyg-authored-scene-evidence-v1", "measurements": evidence}, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
