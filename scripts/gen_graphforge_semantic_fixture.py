#!/usr/bin/env python3
"""Regenerate exact Rust-owned GraphForge semantic Scene consumer hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from xyg import _native

FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/graphforge/semantic_compound.json"


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _goldens(fixture: dict[str, object], theme: str) -> dict[str, str]:
    nodes, edges = fixture["nodes"], fixture["edges"]
    assert isinstance(nodes, dict) and isinstance(edges, dict)
    scene = _native.graph_compound_scene(
        width=fixture["width"],
        height=fixture["height"],
        theme=0 if theme == "light" else 1,
        title=fixture["title"],
        x=nodes["x"],
        y=nodes["y"],
        node_classes=nodes["class"],
        node_epistemic=nodes["epistemic"],
        node_statuses=nodes["status"],
        node_metric=nodes["metric"],
        node_flags=nodes["state_flags"],
        node_labels=nodes["label"],
        sources=edges["source_index"],
        targets=edges["target_index"],
        edge_classes=edges["class"],
        edge_epistemic=edges["epistemic"],
        edge_statuses=edges["status"],
        edge_metric=edges["metric"],
        edge_flags=edges["state_flags"],
        edge_labels=edges["label"],
        parents=nodes["parent_index"],
        parent_validity=nodes["parent_validity"],
        collapsed=nodes["collapsed"],
    )
    painter = _native.scene_browser_painter(scene)
    svg = _native.scene_svg(scene).encode()
    raster = _native.scene_raster_commands(scene)
    png = _native.rasterize_png(raster, int(fixture["width"]), int(fixture["height"]))
    return {
        "scene_sha256": _sha(scene),
        "painter_sha256": _sha(painter),
        "svg_sha256": _sha(svg),
        "raster_sha256": _sha(raster),
        "png_sha256": _sha(png),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="replace fixture hashes")
    args = parser.parse_args()
    fixture = json.loads(FIXTURE.read_text())
    actual = {theme: _goldens(fixture, theme) for theme in ("light", "dark")}
    if not args.write:
        if fixture.get("goldens") != actual:
            raise SystemExit("semantic fixture hashes drifted; rerun with --write")
        print(f"checked {FIXTURE}")
        return
    fixture["goldens"] = actual
    FIXTURE.write_text(json.dumps(fixture, indent=2) + "\n")
    print(f"wrote {FIXTURE}")


if __name__ == "__main__":
    main()
