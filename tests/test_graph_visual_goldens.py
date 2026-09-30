"""Visual regression goldens for composed graph charts (#34).

Five committed PNGs cover the ordinary, dense, compound, selected, and
dark-theme states. The case inputs live in one JSON manifest that both hosts
build from; Python and Node must export the committed PNG bytes exactly
(``packages/xy-node/test/graph.test.mjs`` asserts the same manifest), and a
Chromium screenshot of the live chart must match the export (the browser and
static routes paint the same Rust planes).

Regenerate after an intended visual change with
``uv run python tests/test_graph_visual_goldens.py --write`` and review the
PNG diffs.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import xyg

FIXTURES = Path(__file__).parent / "fixtures"
MANIFEST = FIXTURES / "graph_visual_goldens.json"
GOLDENS = FIXTURES / "graph_visual"
WIDTH, HEIGHT = 560, 400


def _uuid(i: int) -> str:
    return str(uuid.UUID(int=i + 1))


def _cases() -> dict[str, dict[str, Any]]:
    # Ordinary: a small directed graph with labels and curved edges.
    ordinary = {
        "nodes": ["ingest", "parse", "model", "score", "report", "archive"],
        "edges": [
            ["ingest", "parse"],
            ["parse", "model"],
            ["model", "score"],
            ["score", "report"],
            ["parse", "archive"],
            ["report", "ingest"],
            ["model", "model"],
        ],
        "options": {
            "layout": "preset",
            "x": [0.0, 1.0, 2.0, 3.0, 4.0, 1.5],
            "y": [1.0, 1.6, 1.0, 1.6, 1.0, 0.0],
            "edge_curve": "curve",
        },
    }
    # Dense: 300 nodes on a sunflower spiral; the default label budget keeps
    # labels bounded and collision-free.
    n = 300
    golden = math.pi * (3.0 - math.sqrt(5.0))
    xs = [round(math.sqrt(i + 0.5) * math.cos(i * golden), 6) for i in range(n)]
    ys = [round(math.sqrt(i + 0.5) * math.sin(i * golden), 6) for i in range(n)]
    dense = {
        "nodes": [f"n{i}" for i in range(n)],
        "edges": [[f"n{i}", f"n{(i * 7 + 3) % n}"] for i in range(n)]
        + [[f"n{i}", f"n{i + 1}"] for i in range(0, n - 1, 2)],
        "options": {"layout": "preset", "x": xs, "y": ys},
    }
    # GraphForge-shaped compound graph: group A (a1, a2), group B (b1).
    parents = [None, 0, 0, None, 3, None]
    tables = {
        "nodes": {
            "node_uuid": [_uuid(i) for i in range(6)],
            "parent_uuid": [None if p is None else _uuid(p) for p in parents],
            "name": ["A", "a1", "a2", "B", "b1", "out"],
            "kind": [0, 1, 2, 3, 4, 5],
            "belief": [0, 1, 2, 0, 3, 1],
            "health": [1, 0, 2, 3, 0, 1],
            "score": [0.0, 2.5, 5.0, 7.5, 10.0, 1.0],
        },
        "edges": {
            "edge_uuid": [_uuid(100 + i) for i in range(5)],
            "src_uuid": [_uuid(1), _uuid(1), _uuid(2), _uuid(5), _uuid(4)],
            "dst_uuid": [_uuid(5), _uuid(2), _uuid(4), _uuid(0), _uuid(5)],
            "rel": [0, 1, 2, 3, 4],
            "evidence": [1, 0, 2, 3, 0],
            "state": [0, 1, 2, 3, 1],
        },
    }
    geometry = {
        "layout": "preset",
        "x": [0.0, 0.0, 1.0, 5.0, 5.0, 8.0],
        "y": [0.0, 1.0, 0.0, 0.0, 1.0, 3.0],
    }
    semantic = {
        "node_class": "kind",
        "node_epistemic": "belief",
        "node_status": "health",
        "node_metric": "score",
        "edge_class": "rel",
        "edge_epistemic": "evidence",
        "edge_status": "state",
        "semantic_legend": False,
    }
    compound = {**tables, "options": {**geometry, "node_class": "kind", "collapsed": [_uuid(3)]}}
    # Selected: a1 selected, a2 hovered; the rest take their resolved states.
    selected_tables = {
        "nodes": {**tables["nodes"], "flags": [0, 2, 1, 0, 0, 0]},
        "edges": tables["edges"],
    }
    selected = {
        **selected_tables,
        "options": {**geometry, **semantic, "visual_state_flags": "flags"},
    }
    dark = {
        **tables,
        "options": {**geometry, **semantic, "theme": "dark", "semantic_legend": True},
        "chart": {"style": {"background": "#0f172a", "--chart-text": "#e2e8f0"}},
    }
    return {
        "ordinary": ordinary,
        "dense": dense,
        "compound": compound,
        "selected": selected,
        "dark": dark,
    }


def _nodes_edges(case: dict[str, Any]) -> tuple[Any, Any]:
    nodes, edges = case["nodes"], case["edges"]
    if isinstance(edges, list):
        edges = [tuple(edge) for edge in edges]
    return nodes, edges


def chart(case: dict[str, Any], **overrides: Any) -> xyg.Chart:
    nodes, edges = _nodes_edges(case)
    options = {**case["options"], **overrides}
    return xyg.graph_chart(
        xyg.graph(nodes, edges, **options),
        width=WIDTH,
        height=HEIGHT,
        **case.get("chart", {}),
    )


def _manifest() -> dict[str, Any]:
    cases = {}
    for name, case in _cases().items():
        png = chart(case).to_png(scale=1)
        cases[name] = {**case, "png": f"graph_visual/{name}.png", "sha256": _sha(png)}
    return {
        "schema": "xyg.graph-visual-goldens/v1",
        "width": WIDTH,
        "height": HEIGHT,
        "cases": cases,
    }


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_is_current() -> None:
    manifest = _load()
    assert manifest == json.loads(json.dumps(_manifest()))


@pytest.mark.parametrize("name", list(_cases()))
def test_export_matches_the_committed_golden(name: str) -> None:
    case = _load()["cases"][name]
    png = chart(case).to_png(scale=1)
    golden = (FIXTURES / case["png"]).read_bytes()
    assert _sha(golden) == case["sha256"]
    assert png == golden, f"{name}: export differs from {case['png']}"


def _rgb(png: bytes) -> np.ndarray:
    from PIL import Image

    return np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), dtype=np.int16)


def _screenshot(chromium: str, html: str, path: Path) -> bytes:
    page = path.with_suffix(".html")
    page.write_text(html, encoding="utf-8")
    shot = path.with_suffix(".png")
    subprocess.run(
        [
            chromium,
            "--headless=new",
            "--no-sandbox",
            "--use-angle=swiftshader",
            "--enable-unsafe-swiftshader",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            f"--window-size={WIDTH},{HEIGHT}",
            "--virtual-time-budget=8000",
            f"--screenshot={shot}",
            page.as_uri(),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    return shot.read_bytes()


@pytest.mark.parametrize("name", list(_cases()))
def test_browser_paints_what_the_export_paints(name: str, tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    from xyg.export import find_chromium

    chromium = find_chromium()
    if chromium is None:
        pytest.skip("Chromium unavailable")
    # The HTML legend overlay is laid out by the browser, not the Scene, so
    # compare the data layers with the legend off.
    case = _load()["cases"][name]
    view = chart(case, semantic_legend=False) if "node_class" in case["options"] else chart(case)
    exported = _rgb(view.to_png(scale=1))
    browser = _rgb(_screenshot(chromium, view.to_html(), tmp_path / name))
    assert browser.shape == exported.shape
    diff = np.abs(browser - exported).max(axis=2)
    # Antialiasing and glyph rasterization differ by a pixel; geometry, paint,
    # frames, and labels must agree.
    assert diff.mean() < 3.5, (name, float(diff.mean()))
    assert (diff > 96).mean() < 0.01, (name, float((diff > 96).mean()))


if __name__ == "__main__":
    if sys.argv[1:] != ["--write"]:
        raise SystemExit("usage: test_graph_visual_goldens.py --write")
    GOLDENS.mkdir(exist_ok=True)
    for name, case in _cases().items():
        (GOLDENS / f"{name}.png").write_bytes(chart(case).to_png(scale=1))
    MANIFEST.write_text(json.dumps(_manifest(), indent=1) + "\n", encoding="utf-8")
    print(f"wrote {MANIFEST} and {len(_cases())} goldens")
