"""Static SVG/PNG export of graph charts (#33).

Graph charts paint exactly their edge ``segments`` and node ``scatter`` traces,
so the static Scene consumes the same Rust autorange the browser uses. The
committed cross-host fixture pins SVG and PNG bytes; ``packages/xy-node/test/
graph.test.mjs`` asserts the same fixture so Python and Node agree.

Regenerate after an intended contract change with
``uv run python tests/test_graph_static_export.py --write``.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

import xyg
from xyg._static_document import UnsupportedStaticExport

FIXTURE = Path(__file__).parent / "fixtures" / "graph_static_export_cross_host.json"
NODES = ["a", "b", "c"]
EDGES = [["a", "b"], ["a", "b"], ["b", "a"], ["b", "c"], ["c", "c"], ["a", "c"]]
X = [0.0, 4.0, 2.0]
Y = [0.0, 0.0, 3.0]
# Explicit colors: default graph colors differ between hosts today and are a
# separate product decision; this fixture pins geometry and export bytes.
COLORS = {"color": "#1f77b4", "edge_color": "#888888"}
CASES = {"straight": "straight", "curved": "curve"}


def _chart(edge_curve: str) -> xyg.Chart:
    return xyg.graph_chart(
        xyg.graph(
            NODES,
            [tuple(edge) for edge in EDGES],
            layout="preset",
            x=X,
            y=Y,
            edge_curve=edge_curve,
            **COLORS,
        ),
        width=640,
        height=480,
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _expected() -> dict[str, Any]:
    cases = {}
    for name, curve in CASES.items():
        chart = _chart(curve)
        cases[name] = {
            "edge_curve": curve,
            "svg_sha256": _sha(chart.to_svg().encode()),
            "png_scale1_sha256": _sha(chart.to_png(scale=1)),
        }
    return {
        "schema": "xyg.graph-static-export-cross-host/v1",
        "width": 640,
        "height": 480,
        "nodes": NODES,
        "edges": EDGES,
        "x": X,
        "y": Y,
        **COLORS,
        "cases": cases,
    }


def test_graph_chart_exports_svg_and_png() -> None:
    for curve in CASES.values():
        chart = _chart(curve)
        svg = chart.to_svg()
        assert svg.count("<circle") == len(NODES)
        # Every routed segment paints: 6 edges incl. arrows, loop sides, curves.
        assert svg.count("<polyline") >= len(EDGES)
        png = chart.to_png()
        assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_graphforge_graph_exports() -> None:
    nodes = {"node_uuid": [f"00000000-0000-0000-0000-00000000000{i}" for i in (1, 2, 3)]}
    edges = {
        "edge_uuid": [f"00000000-0000-0000-0000-00000000010{i}" for i in (1, 2)],
        "src_uuid": [nodes["node_uuid"][0], nodes["node_uuid"][1]],
        "dst_uuid": [nodes["node_uuid"][1], nodes["node_uuid"][2]],
    }
    chart = xyg.graph_chart(xyg.graph(nodes, edges, layout="preset", x=X, y=Y))
    assert chart.to_svg().count("<circle") == 3


def test_graph_mixed_with_other_marks_stays_fail_closed() -> None:
    # The graph admission covers graph marks only; extra literal geometry
    # still needs an authored domain.
    chart = xyg.graph_chart(
        xyg.graph(NODES, [tuple(edge) for edge in EDGES], layout="preset", x=X, y=Y),
        xyg.line(x=[0.0, 4.0], y=[0.0, 3.0]),
    )
    with pytest.raises(UnsupportedStaticExport, match="XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS"):
        chart.to_svg()


def test_cross_host_fixture_matches_python_export() -> None:
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == _expected()


_BROWSER_PROBE = """
(async () => {
  try {
    const view = window.__fcProbeView;
    view._layout();
    view._drawNow();
    view._raf = null;
    const g = view.gpuTraces.find((trace) => trace.trace.id === NODE_TRACE);
    const points = XS.map((x, i) => view._projectDataPoint(g.xAxis, g.yAxis, x, YS[i], null));
    document.body.setAttribute("data-xy-graph-export-probe", JSON.stringify({points}));
  } catch (error) {
    document.body.setAttribute(
      "data-xy-graph-export-probe-error", String((error && error.stack) || error)
    );
  }
})();
"""


def test_browser_node_positions_match_static_export(tmp_path: Path) -> None:
    from conftest import probe_document, run_browser_probe
    from xyg.export import find_chromium

    chromium = find_chromium()
    if chromium is None:
        pytest.skip("Chromium unavailable")
    chart = _chart("curve")
    svg = chart.to_svg()
    exported = [
        (float(cx), float(cy)) for cx, cy in re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)"', svg)
    ]
    meta = chart.figure()._graph_meta[0]
    script = (
        _BROWSER_PROBE.replace("NODE_TRACE", str(meta["node_trace"]))
        .replace("XS", json.dumps(X))
        .replace("YS", json.dumps(Y))
    )
    result = run_browser_probe(
        chromium,
        probe_document(chart, f"<script>{script}</script>"),
        tmp_path / "graph-export.html",
        "data-xy-graph-export-probe",
        label="graph export vs browser",
    )
    browser = [(float(px), float(py)) for px, py, *_ in result["points"]]
    assert len(browser) == len(exported) == len(NODES)
    for (bx, by), (sx, sy) in zip(browser, exported, strict=True):
        assert bx == pytest.approx(sx, abs=0.01)
        assert by == pytest.approx(sy, abs=0.01)


if __name__ == "__main__":
    if sys.argv[1:] != ["--write"]:
        raise SystemExit("usage: test_graph_static_export.py --write")
    FIXTURE.write_text(json.dumps(_expected(), indent=1) + "\n", encoding="utf-8")
    print(f"wrote {FIXTURE}")
