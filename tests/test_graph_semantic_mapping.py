"""Public GraphForge semantic mapping on the composed graph mark (#34).

``node_class`` / ``node_epistemic`` / ``node_status`` / ``node_metric`` and the
``edge_*`` equivalents resolve through Rust's versioned semantic style contract
(``_native.graph_semantic_styles``); the graph mark only maps the resolved rows
onto its existing scatter and segments channels. Fields are source-row
indexed, so they paint where render identity is exact and are omitted (and
recorded) under Aggregate LOD. The committed cross-host fixture pins the
painted values; ``packages/xy-node/test/graph.test.mjs`` asserts the same
fixture so Python and Node agree.

Regenerate after an intended contract change with
``uv run python tests/test_graph_semantic_mapping.py --write``.
"""

from __future__ import annotations

import functools
import json
import sys
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import xyg
from xyg import _graph, _native, interaction
from xyg._figure import Figure

FIXTURE = Path(__file__).parent / "fixtures" / "graph_semantic_mapping_cross_host.json"
SHAPES = ["circle", "square", "diamond", "triangle", "cross", "hexagon"]


def _uuid(i: int) -> str:
    return str(uuid.UUID(int=i + 1))


X = [0.0, 0.1, 100.0, 100.1, 50.0, 50.0]
Y = [0.0, 0.1, 100.0, 100.1, 0.0, 100.0]
EDGES = [(0, 2), (0, 2), (2, 0), (0, 0), (0, 1), (1, 3), (3, 1), (4, 5)]
NODE_COLUMNS = {
    "kind": [0, 1, 2, 3, 4, 5],
    "belief": [0, 1, 2, 0, 3, 1],
    "health": [1, 0, 2, 3, 0, 1],
    "score": [0.0, 2.5, 5.0, 7.5, 10.0, 1.0],
    # hovered, selected, filtered, disabled, pinned, normal
    "flags": [1 << 0, 1 << 1, 1 << 3, 1 << 6, 1 << 4, 0],
}
EDGE_COLUMNS = {
    "rel": [0, 1, 2, 3, 4, 5, 6, 7],
    "evidence": [1, 0, 2, 3, 1, 0, 2, 3],
    "state": [0, 1, 0, 2, 3, 0, 1, 0],
    "weight": [1.0, 4.0, 2.0, 8.0, 0.5, 3.0, 6.0, 5.0],
}
CASES = {
    "direct": {"node_budget": 100, "edge_budget": 100, "edge_curve": "straight"},
    "direct_curved": {"node_budget": 100, "edge_budget": 100, "edge_curve": "curve"},
    "edge_sample": {"node_budget": 100, "edge_budget": 3, "edge_curve": "straight"},
    "aggregate": {"node_budget": 3, "edge_budget": 100, "edge_curve": "straight"},
}
SEMANTIC = {
    "node_class": "kind",
    "node_epistemic": "belief",
    "node_status": "health",
    "node_metric": "score",
    "visual_state_flags": "flags",
    "edge_class": "rel",
    "edge_epistemic": "evidence",
    "edge_status": "state",
    "edge_metric": "weight",
}


def _tables() -> tuple[dict[str, Any], dict[str, Any]]:
    nodes = {"node_uuid": [_uuid(i) for i in range(len(X))], **NODE_COLUMNS}
    edges = {
        "edge_uuid": [_uuid(1000 + i) for i in range(len(EDGES))],
        "src_uuid": [_uuid(s) for s, _ in EDGES],
        "dst_uuid": [_uuid(t) for _, t in EDGES],
        **EDGE_COLUMNS,
    }
    return nodes, edges


def _figure(
    *, node_budget: int, edge_budget: int, edge_curve: str, theme: str = "light", **extra: Any
) -> Figure:
    # The public graph mark has no budget knobs; bound run_layout forces a tier.
    original = _graph.run_layout
    _graph.run_layout = functools.partial(
        original, node_budget=node_budget, edge_budget=edge_budget
    )
    try:
        nodes, edges = _tables()
        kwargs = {**SEMANTIC, **extra}
        return Figure().graph(
            nodes,
            edges,
            layout="preset",
            x=X,
            y=Y,
            edge_curve=edge_curve,
            theme=theme,
            **kwargs,
        )
    finally:
        _graph.run_layout = original


def _floats(values: Any) -> list[float]:
    return [float(v) for v in np.asarray(values, dtype=np.float64).ravel()]


def _u8(rgba: Any) -> list[list[int]]:
    # Python direct-RGBA channels hold [0, 1] floats quantized to u8 on ship.
    return np.rint(np.asarray(rgba, dtype=np.float64) * 255.0).astype(int).tolist()


def _painted(fig: Figure) -> dict[str, Any]:
    meta = fig._graph_meta[0]
    node = fig.traces[meta["node_trace"]]
    edge = fig.traces[meta["edge_trace"]]
    contract = meta["style_contract"]
    out: dict[str, Any] = {"tier_name": meta["tier_name"], "style_contract": contract}
    out["nodes"] = None
    if contract["nodes"] == "resolved":
        n = len(node.x)
        size = node.size_ch
        sizes = size.values if size.values is not None else np.full(n, size.constant)
        stroke = getattr(node, "stroke_ch", None)
        assert stroke is not None
        out["nodes"] = {
            "fill_rgba": _u8(node.color_ch.rgba),
            "stroke_rgba": _u8(stroke.rgba),
            "size": _floats(sizes),
            "symbol": [SHAPES[int(c)] for c in node.style_channels["symbol"].values],
            "opacity": _floats(node.style_channels["opacity"].values),
            "stroke_width": _floats(node.style_channels["stroke_width"].values),
        }
    out["edges"] = None
    if contract["edges"] == "resolved":
        out["edges"] = {
            "rgba": _u8(edge.color_ch.rgba),
            "width": _floats(edge.style_channels["width"].values),
            "opacity": _floats(edge.style_channels["opacity"].values),
        }
    return out


def _expected() -> dict[str, Any]:
    return {
        "schema": "xyg.graph-semantic-mapping-cross-host/v1",
        "x": X,
        "y": Y,
        "edges": [list(edge) for edge in EDGES],
        "node_columns": NODE_COLUMNS,
        "edge_columns": EDGE_COLUMNS,
        "node_uuid": [_uuid(i) for i in range(len(X))],
        "edge_uuid": [_uuid(1000 + i) for i in range(len(EDGES))],
        "cases": {name: {**opts, **_painted(_figure(**opts))} for name, opts in CASES.items()},
    }


def _close(actual: Any, expected: Any) -> None:
    if isinstance(expected, float):
        assert actual == pytest.approx(expected, rel=1e-6, abs=1e-6)
    elif isinstance(expected, dict):
        assert set(actual) == set(expected)
        for key in expected:
            _close(actual[key], expected[key])
    elif isinstance(expected, list):
        assert len(actual) == len(expected)
        for a, e in zip(actual, expected, strict=True):
            _close(a, e)
    else:
        assert actual == expected


def test_cross_host_fixture_is_current() -> None:
    _close(json.loads(FIXTURE.read_text(encoding="utf-8")), _expected())


def test_node_paint_is_the_rust_resolved_contract() -> None:
    fig = _figure(**CASES["direct"])
    resolved = _native.graph_semantic_styles(
        np.array(NODE_COLUMNS["kind"]),
        np.array(NODE_COLUMNS["belief"]),
        np.array(NODE_COLUMNS["health"]),
        np.array(NODE_COLUMNS["score"]),
        np.array(NODE_COLUMNS["flags"], dtype=np.uint32),
    )
    painted = _painted(fig)["nodes"]
    assert painted["fill_rgba"] == resolved["fill_rgba"].astype(int).tolist()
    assert painted["stroke_rgba"] == resolved["stroke_rgba"].astype(int).tolist()
    assert painted["size"] == pytest.approx(_floats(resolved["size"]))
    assert painted["opacity"] == pytest.approx(_floats(resolved["opacity"]))
    assert painted["stroke_width"] == pytest.approx(_floats(resolved["width"]))
    assert painted["symbol"] == [SHAPES[int(c)] for c in resolved["shape"]]
    # Filtered and disabled nodes fade; the contract, not the host, decides.
    assert painted["opacity"][2] == pytest.approx(0.08)
    assert painted["opacity"][3] == pytest.approx(0.28)
    meta = fig._graph_meta[0]
    assert meta["style_contract"]["node_metric_domain"] == [0.0, 10.0]
    # Edge trims use the semantic diameters and outlines.
    ends = fig.traces[meta["edge_trace"]].style_channels["edge_ends"].values
    first = meta["render_edge_index"].index(0)
    assert ends[first, 2] == pytest.approx(resolved["size"][0] / 2)


@pytest.mark.parametrize("case", ["direct", "direct_curved", "edge_sample"])
def test_every_routed_segment_paints_its_own_source_edge(case: str) -> None:
    fig = _figure(**CASES[case])
    meta = fig._graph_meta[0]
    zeros = np.zeros(len(EDGES), dtype=np.uint32)
    resolved = _native.graph_semantic_styles(
        np.array(EDGE_COLUMNS["rel"]),
        np.array(EDGE_COLUMNS["evidence"]),
        np.array(EDGE_COLUMNS["state"]),
        np.array(EDGE_COLUMNS["weight"]),
        zeros,
        edge=True,
    )
    painted = _painted(fig)["edges"]
    for segment in range(len(meta["render_edge_index"])):
        (row,) = interaction.pick(fig, meta["edge_trace"], segment)["source_edges"]
        assert painted["rgba"][segment] == resolved["stroke_rgba"][row].astype(int).tolist()
        assert painted["width"][segment] == pytest.approx(float(resolved["width"][row]))
        assert painted["opacity"][segment] == pytest.approx(float(resolved["opacity"][row]))
    # EdgeSample keeps the source metric domain, so a kept edge's width does
    # not change when others are sampled away.
    assert meta["style_contract"]["edge_metric_domain"] == [0.5, 8.0]


def test_aggregate_lod_omits_source_row_styling_and_records_it() -> None:
    fig = _figure(**CASES["aggregate"])
    contract = fig._graph_meta[0]["style_contract"]
    assert fig._graph_meta[0]["tier_name"] == "aggregate"
    assert contract["nodes"] == "omitted:aggregate"
    assert contract["edges"] == "omitted:aggregate"
    assert "node_halo" in contract["pending_layers"]


def test_themes_resolve_different_palettes() -> None:
    light = _painted(_figure(**CASES["direct"]))
    dark = _painted(_figure(**CASES["direct"], theme="dark"))
    assert dark["style_contract"]["theme"] == "dark"
    assert light["nodes"]["fill_rgba"] != dark["nodes"]["fill_rgba"]
    with pytest.raises(ValueError, match="theme"):
        _figure(**CASES["direct"], theme="sepia")


def test_semantic_fields_fail_closed() -> None:
    with pytest.raises(ValueError, match="replace color"):
        _figure(**CASES["direct"], color="#ff0000")
    with pytest.raises(ValueError, match="replace edge_color"):
        _figure(**CASES["direct"], edge_color="#ff0000")
    with pytest.raises(ValueError, match="unknown node column"):
        _figure(**CASES["direct"], node_class="missing")
    with pytest.raises(ValueError, match="integer codes"):
        _figure(**CASES["direct"], node_class=[0.5] * len(X))
    with pytest.raises(ValueError, match=r"0\.\.7"):
        _figure(**CASES["direct"], node_class=[8] * len(X))
    with pytest.raises(ValueError, match="edge count"):
        _figure(**CASES["direct"], edge_class=[0, 1])


def test_codes_validate_even_when_aggregate_omits_paint() -> None:
    with pytest.raises(ValueError, match=r"0\.\.7"):
        _figure(**CASES["aggregate"], node_class=[9] * len(X))
    with pytest.raises(ValueError, match=r"0\.\.7"):
        _figure(**CASES["aggregate"], edge_status=[0] * (len(EDGES) - 1) + [8])


@pytest.mark.parametrize(
    ("style", "side"),
    [
        ({"opacity": 0.5}, "node"),
        ({"fill": "red"}, "node"),
        ({"marker-shape": "square"}, "node"),
        ({"stroke-width": 2}, "node"),
    ],
)
def test_style_cannot_override_semantic_paint(style: dict[str, Any], side: str) -> None:
    with pytest.raises(ValueError, match=f"graph {side} semantic fields own paint"):
        _figure(**CASES["direct"], style=style)


def test_semantic_nodes_never_fall_into_the_density_tier() -> None:
    fig = _figure(**CASES["direct"])
    node = fig.traces[fig._graph_meta[0]["node_trace"]]
    assert node.force_density is False


def test_public_composition_api_forwards_semantic_fields() -> None:
    nodes, edges = _tables()
    chart = xyg.graph_chart(
        nodes=nodes, edges=edges, layout="preset", x=X, y=Y, theme="dark", **SEMANTIC
    )
    contract = chart.figure()._graph_meta[0]["style_contract"]
    assert (contract["nodes"], contract["edges"], contract["theme"]) == (
        "resolved",
        "resolved",
        "dark",
    )


def test_unstyled_graph_records_no_contract() -> None:
    nodes, edges = _tables()
    fig = Figure().graph(nodes, edges, layout="preset", x=X, y=Y)
    assert "style_contract" not in fig._graph_meta[0]


_PIXEL_PROBE = """
(async () => {
  try {
    const view = window.__fcProbeView;
    view._layout(); view._drawNow(); view._raf = null;
    const node = view.gpuTraces.find((t) => t.trace.id === NODE_TRACE);
    const read = (x, y) => {
      const px = new Uint8Array(4);
      const dpr = view.dpr;
      view.gl.readPixels(
        Math.round((x - view.plot.x) * dpr),
        Math.round(view.canvas.height - (y - view.plot.y) * dpr),
        1, 1, view.gl.RGBA, view.gl.UNSIGNED_BYTE, px);
      return Array.from(px);
    };
    const out = POINTS.map(([x, y]) => {
      const p = view._projectDataPoint(node.xAxis, node.yAxis, x, y, null);
      return read(p[0], p[1]);
    });
    document.body.setAttribute("data-xy-semantic-probe", JSON.stringify(out));
  } catch (error) {
    document.body.setAttribute("data-xy-semantic-probe-error", String((error && error.stack) || error));
  }
})();
"""


def test_browser_paints_resolved_node_fills(tmp_path: Path) -> None:
    from conftest import probe_document, run_browser_probe
    from xyg.export import find_chromium

    chromium = find_chromium()
    if chromium is None:
        pytest.skip("Chromium unavailable")
    # Well-separated nodes without state flags paint their opaque class fill.
    xs, ys = [0.0, 4.0, 0.0, 4.0], [0.0, 0.0, 3.0, 3.0]
    nodes = {
        "node_uuid": [_uuid(i) for i in range(4)],
        "kind": [1, 2, 3, 4],
        "score": [10.0, 10.0, 10.0, 10.0],
    }
    chart = xyg.graph_chart(
        xyg.graph(
            nodes,
            {"edge_uuid": [], "src_uuid": [], "dst_uuid": []},
            layout="preset",
            x=xs,
            y=ys,
            node_class="kind",
            node_metric="score",
        ),
        width=640,
        height=480,
    )
    fig = chart.figure()
    meta = fig._graph_meta[0]
    expected = np.asarray(_u8(fig.traces[meta["node_trace"]].color_ch.rgba))
    script = _PIXEL_PROBE.replace("NODE_TRACE", str(meta["node_trace"])).replace(
        "POINTS", json.dumps(list(zip(xs, ys, strict=True)))
    )
    result = run_browser_probe(
        chromium,
        probe_document(chart, f"<script>{script}</script>"),
        tmp_path / "graph-semantic.html",
        "data-xy-semantic-probe",
        label="graph semantic fills",
    )
    for pixel, rgba in zip(result, expected, strict=True):
        assert all(abs(int(p) - int(e)) <= 3 for p, e in zip(pixel[:3], rgba[:3], strict=True)), (
            pixel,
            rgba.tolist(),
        )


if __name__ == "__main__":
    if sys.argv[1:] != ["--write"]:
        raise SystemExit("usage: test_graph_semantic_mapping.py --write")
    FIXTURE.write_text(json.dumps(_expected(), indent=1) + "\n", encoding="utf-8")
    print(f"wrote {FIXTURE}")
