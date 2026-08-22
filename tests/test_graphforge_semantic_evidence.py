"""Exact cross-consumer evidence for the GraphForge semantic graph contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from xyg import _native

FIXTURE = Path(__file__).parent / "fixtures" / "graphforge" / "semantic_compound.json"


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text())


def _scene(fixture: dict[str, object], theme: str) -> bytes:
    nodes, edges = fixture["nodes"], fixture["edges"]
    assert isinstance(nodes, dict) and isinstance(edges, dict)
    return _native.graph_compound_scene(
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


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def test_graphforge_semantic_fixture_has_exact_cross_consumer_goldens() -> None:
    fixture = _fixture()
    for theme in ("light", "dark"):
        scene = _scene(fixture, theme)
        painter = _native.scene_browser_painter(scene)
        svg = _native.scene_svg(scene).encode()
        raster = _native.scene_raster_commands(scene)
        png = _native.rasterize_png(raster, int(fixture["width"]), int(fixture["height"]))
        expected = fixture["goldens"][theme]
        actual = {
            "scene_sha256": _sha(scene),
            "painter_sha256": _sha(painter),
            "svg_sha256": _sha(svg),
            "raster_sha256": _sha(raster),
            "png_sha256": _sha(png),
        }
        assert actual == expected
        assert b"Collapsed evidence group" in svg
        # The outside label is deliberately truncated by Rust's bounded label policy.
        assert b">\xe2\x80\xa6</text>" in svg
        assert b"Hidden child" not in svg and b"Hidden selected grandchild" not in svg
        assert b"omitted internal" not in svg
        assert b"remapped boundary" in svg
        assert b'data-xy-stable-id="4294967296"' in svg
        assert b'data-xy-stable-id="4294967300"' in svg
        assert b'data-xy-stable-id="2"' in svg
        pixels = _native.rasterize(raster, int(fixture["width"]), int(fixture["height"]))
        assert np.unique(pixels.reshape(-1, 4), axis=0).shape[0] >= 8


def test_graphforge_fixture_semantics_are_inspectable_and_complete() -> None:
    fixture = _fixture()
    nodes, edges = fixture["nodes"], fixture["edges"]
    assert fixture["contract"] == "graphforge-semantic-compound-v1"
    assert sorted(set(nodes["class"])) == [1, 2, 3, 4, 5]
    assert sorted(set(nodes["epistemic"])) == [0, 1, 2, 3, 4]
    assert sorted(set(nodes["status"])) == [0, 1, 2, 3, 4]
    assert nodes["state_flags"][2] == 2 and nodes["state_flags"][4] == 16
    assert nodes["parent_index"][2] == 1 and nodes["parent_index"][1] == 0
    assert edges["source_index"][:2] == [2, 2] and edges["target_index"][:2] == [3, 4]
