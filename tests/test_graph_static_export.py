"""Static SVG/PNG export of graph charts (#33, #34).

Graph charts paint exactly their edge ``segments`` and node ``scatter`` traces,
so the static Scene consumes the same Rust autorange the browser uses. Composed
graphs (semantic layers, compound frames, labels, color scales, legend) export
through ``xyg_graph_composed_scene``: Rust rebuilds the plain graph Scene from
the resolved per-item planes the browser paints. The committed cross-host
fixture pins SVG and PNG bytes; ``packages/xy-node/test/graph.test.mjs``
asserts the same fixture so Python and Node agree.

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
# Explicit colors pin geometry and export bytes; the "default_colors" case pins
# the Rust-owned graph defaults (#898: neutral edges, palette nodes).
COLORS = {"color": "#1f77b4", "edge_color": "#888888"}
CASES = {"straight": "straight", "curved": "curve", "default_colors": "straight"}


def _uuid(i: int) -> str:
    return f"00000000-0000-0000-0000-{i + 1:012d}"


# A GraphForge-shaped compound graph: groups A (children a1, a2) and B (b1).
COMPOSED_NODES: dict[str, Any] = {
    "node_uuid": [_uuid(i) for i in range(6)],
    "parent_uuid": [None, _uuid(0), _uuid(0), None, _uuid(3), None],
    "name": ["A", "a1", "a2", "B", "b1", "out"],
    "kind": [0, 1, 2, 3, 4, 5],
    "belief": [0, 1, 2, 0, 3, 1],
    "health": [1, 0, 2, 3, 0, 1],
    "score": [0.0, 2.5, 5.0, 7.5, 10.0, 1.0],
    "flags": [0, 2, 1, 0, 8, 0],
}
COMPOSED_EDGES: dict[str, Any] = {
    "edge_uuid": [_uuid(100 + i) for i in range(4)],
    "src_uuid": [_uuid(1), _uuid(1), _uuid(2), _uuid(5)],
    "dst_uuid": [_uuid(5), _uuid(2), _uuid(4), _uuid(0)],
    "rel": [0, 1, 2, 3],
    "evidence": [1, 0, 2, 3],
    "state": [0, 1, 2, 3],
    "weight": [1.0, 4.0, 2.0, 8.0],
}
COMPOSED_X = [0.0, 0.0, 1.0, 5.0, 5.0, 9.0]
COMPOSED_Y = [0.0, 1.0, 0.0, 0.0, 1.0, 5.0]
_SEMANTIC = {
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
# Every composed layer the browser paints: semantic halo/body/dash/heads and
# the semantic legend (light and dark), compound frames and disclosure,
# painted labels, and ordinal/diverging color scales.
COMPOSED_CASES: dict[str, dict[str, Any]] = {
    "semantic": _SEMANTIC,
    "semantic_dark": {**_SEMANTIC, "theme": "dark"},
    "compound_collapsed": {"collapsed": [_uuid(0)], "node_class": "kind"},
    "sizes": {"size": [1.0, 5.0, 9.0, 2.0, 3.0, 4.0], "symbol": "square"},
    "labels_scales": {
        "edge_curve": "curve",
        "label_priority": [5.0, 1.0, 4.0, 2.0, 3.0, 0.0],
        "edge_label": ["x", None, "long edge label", "loop"],
        "color": ["low", "high", "mid", "low", "mid", "high"],
        "color_scale": {"type": "ordinal", "order": ["low", "mid", "high"]},
        "edge_color": [-2.0, 1.0, 5.0, 0.0],
        "edge_color_scale": {"type": "diverging", "midpoint": 1.0},
    },
}


def _chart(edge_curve: str, *, colors: bool = True) -> xyg.Chart:
    return xyg.graph_chart(
        xyg.graph(
            NODES,
            [tuple(edge) for edge in EDGES],
            layout="preset",
            x=X,
            y=Y,
            edge_curve=edge_curve,
            **(COLORS if colors else {}),
        ),
        width=640,
        height=480,
    )


COMPOSED_LEGEND = {"loc": "lower left"}


def _composed_chart(options: dict[str, Any], legend: dict[str, Any] | None = None) -> xyg.Chart:
    return xyg.graph_chart(
        xyg.graph(
            COMPOSED_NODES, COMPOSED_EDGES, layout="preset", x=COMPOSED_X, y=COMPOSED_Y, **options
        ),
        *([xyg.legend(**legend)] if legend else []),
        width=640,
        height=480,
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hashes(chart: xyg.Chart) -> dict[str, str]:
    return {
        "svg_sha256": _sha(chart.to_svg().encode()),
        "png_scale1_sha256": _sha(chart.to_png(scale=1)),
        "png_scale2_sha256": _sha(chart.to_png(scale=2)),
    }


def _expected() -> dict[str, Any]:
    cases = {}
    for name, curve in CASES.items():
        chart = _chart(curve, colors=name != "default_colors")
        cases[name] = {"edge_curve": curve, "colors": name != "default_colors", **_hashes(chart)}
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
        "composed": {
            "nodes": COMPOSED_NODES,
            "edges": COMPOSED_EDGES,
            "x": COMPOSED_X,
            "y": COMPOSED_Y,
            "cases": {
                **{
                    name: {"options": options, **_hashes(_composed_chart(options))}
                    for name, options in COMPOSED_CASES.items()
                },
                # The chart-level legend placement the browser honors.
                "legend_lower_left": {
                    "options": _SEMANTIC,
                    "legend": COMPOSED_LEGEND,
                    **_hashes(_composed_chart(_SEMANTIC, COMPOSED_LEGEND)),
                },
            },
        },
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


def test_composed_graphs_export_their_labels_and_semantic_legend() -> None:
    svg = _composed_chart(COMPOSED_CASES["semantic"]).to_svg()
    assert ">Graph semantics<" in svg
    assert ">Class 5<" in svg
    # Labels that paint at the home view export as text (node names).
    assert ">a1<" in svg
    labeled = _composed_chart(COMPOSED_CASES["labels_scales"]).to_svg()
    assert ">long edge label<" in labeled


def test_edgeless_graph_exports() -> None:
    # The Scene admits no empty trace; the base pass drops the empty edges.
    chart = xyg.graph_chart(
        xyg.graph(["a", "b"], [], layout="preset", x=[0.0, 1.0], y=[0.0, 1.0]),
        width=320,
        height=240,
    )
    assert chart.to_svg().count("<circle") == 2


def test_graph_legend_placement_matches_the_browser_or_fails_closed() -> None:
    default = _composed_chart(_SEMANTIC).to_svg()
    moved = _composed_chart(_SEMANTIC, COMPOSED_LEGEND)
    options = moved.figure().legend_options
    # The chart-level legend places the graph's semantic rows; it keeps them.
    assert options["loc"] == "lower left"
    assert options["title"] == "Graph semantics" and len(options["items"]) == 14
    assert moved.to_svg() != default
    # Placements without a fixed static position fail closed.
    with pytest.raises(UnsupportedStaticExport, match="XYG_STATIC_UNSUPPORTED_GRAPH"):
        _composed_chart(_SEMANTIC, {"loc": "best"}).to_svg()


def test_a_legend_taller_than_the_plot_fails_with_the_footprint_reason() -> None:
    # The browser scrolls a tall legend; a static image cannot, so export
    # reports the same footprint reason as every static legend.
    short = xyg.graph_chart(
        xyg.graph(
            COMPOSED_NODES,
            COMPOSED_EDGES,
            layout="preset",
            x=COMPOSED_X,
            y=COMPOSED_Y,
            **_SEMANTIC,
        ),
        width=480,
        height=240,
    )
    with pytest.raises(UnsupportedStaticExport, match="XYG_STATIC_UNSUPPORTED_LEGEND_FOOTPRINT"):
        short.to_svg()


def test_cross_host_fixture_matches_python_export() -> None:
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == _expected()


def test_default_png_export_scale_is_2x() -> None:
    """The default to_png() scale is 2x (sourced from xyg_default_png_export_scale ABI 370)."""
    import struct

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for name, case in fixture["cases"].items():
        chart = _chart(case["edge_curve"], colors=case.get("colors", True))
        png = chart.to_png()  # default scale
        w = struct.unpack(">I", png[16:20])[0]
        h = struct.unpack(">I", png[20:24])[0]
        assert w == fixture["width"] * 2, f"{name}: expected width {fixture['width'] * 2}, got {w}"
        assert h == fixture["height"] * 2, (
            f"{name}: expected height {fixture['height'] * 2}, got {h}"
        )
        assert _sha(png) == case["png_scale2_sha256"], (
            f"{name}: default PNG bytes differ from fixture"
        )


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


def test_default_graph_colors_are_the_rust_contract() -> None:
    from xyg import _native

    fig = _chart("straight", colors=False).figure()
    meta = fig._graph_meta[0]
    edges, nodes = fig.traces[meta["edge_trace"]], fig.traces[meta["node_trace"]]
    assert edges.style["color"] == _native.graph_default_edge_color() == "#888888"
    assert nodes.color_ch.constant == _native.default_palette_contract()[1][0]


@pytest.mark.parametrize("kind", ["text", "hline", "vline", "arrow"])
def test_graph_annotations_fail_closed_instead_of_disappearing(kind: str) -> None:
    # The composed rebuild re-emits only the graph; authored annotations are
    # refused rather than silently dropped.
    annotation = {
        "text": lambda: xyg.text(0.5, 0.5, "NOTE"),
        "hline": lambda: xyg.hline(0.25),
        "vline": lambda: xyg.vline(0.5),
        "arrow": lambda: xyg.arrow(0.0, 0.0, 1.0, 1.0),
    }[kind]()
    # Authored domains pass the axis admission, so the rebuild itself decides.
    chart = xyg.graph_chart(
        xyg.graph(["a", "b"], [("a", "b")], layout="preset", x=[0.0, 1.0], y=[0.0, 1.0]),
        annotation,
        xyg.x_axis(show=False, domain=(-1.0, 2.0)),
        xyg.y_axis(show=False, domain=(-1.0, 2.0)),
    )
    with pytest.raises(UnsupportedStaticExport, match="XYG_STATIC_UNSUPPORTED_GRAPH"):
        chart.to_svg()


def test_graph_on_an_authored_log_axis_exports_screen_space_shapes() -> None:
    # Arrowheads and dash spans follow screen px on a log axis (#909): the
    # head's tip sits on the target outline, one head length past the shaft.
    svg = xyg.graph_chart(
        xyg.graph(
            ["a", "b"],
            [("a", "b")],
            layout="preset",
            x=[1.0, 100.0],
            y=[0.0, 0.0],
            directed=True,
        ),
        xyg.x_axis(type_="log", domain=(1.0, 1000.0)),
        width=400,
        height=300,
    ).to_svg()
    shaft = re.search(r'<polyline points="\s*([\d.]+),([\d.]+) ([\d.]+),([\d.]+)"', svg)
    head = re.search(r'<path d="M ([\d.]+) ([\d.]+) L ([\d.]+) ([\d.]+) L ([\d.]+) ', svg)
    assert shaft is not None and head is not None, svg
    shaft_end = float(shaft.group(3))
    tip, base_a, base_b = float(head.group(1)), float(head.group(3)), float(head.group(5))
    # A horizontal edge: the shaft ends exactly at the head's base, short of
    # the tip (no stroke under or past the head).
    assert tip > shaft_end
    assert base_a == pytest.approx(shaft_end, abs=0.02)
    assert base_b == pytest.approx(shaft_end, abs=0.02)


def test_graph_chart_kwargs_with_a_graph_child_belong_to_the_chart() -> None:
    # A chart style next to a graph child reaches the chart (it used to be
    # dropped as a mark kwarg); a mark kwarg there fails loudly.
    style = {"background": "#0f172a", "--chart-text": "#e2e8f0"}
    chart = xyg.graph_chart(
        xyg.graph(["a", "b"], [("a", "b")], layout="preset", x=[0.0, 1.0], y=[0.0, 1.0]),
        style=style,
    )
    assert chart.figure().style == style
    with pytest.raises(TypeError, match="node_class"):
        xyg.graph_chart(
            xyg.graph(["a"], [], layout="preset", x=[0.0], y=[0.0]), node_class=[1]
        ).figure()


def test_graph_chart_keeps_authored_axes() -> None:
    # #909: graph_chart's hidden default axes no longer replace authored ones.
    chart = xyg.graph_chart(
        xyg.graph(["a", "b"], [("a", "b")], layout="preset", x=[1.0, 100.0], y=[0.0, 1.0]),
        xyg.x_axis(type_="log", domain=(1.0, 1000.0)),
    )
    options = chart.figure().axis_options
    assert options["x"]["type"] == "log"
    assert options["x"]["domain"] == (1.0, 1000.0)
    assert options["y"]["style"]["axis_width"] == 0.0  # y keeps the hidden default
    # Static export honors the authored log domain: 1, 10, 100 sit at 0, 1/3,
    # 2/3 of the plot width; the hidden y axis keeps the graph autorange.
    svg = xyg.graph_chart(
        xyg.graph(
            ["a", "b", "c"],
            [("a", "b"), ("b", "c")],
            layout="preset",
            x=[1.0, 10.0, 100.0],
            y=[0.0, 1.0, 0.0],
        ),
        xyg.x_axis(type_="log", domain=(1.0, 1000.0)),
        width=400,
        height=300,
    ).to_svg()
    left, width = (
        float(v)
        for v in re.search(
            r'<clipPath[^>]*><rect x="([\d.]+)" y="[\d.]+" width="([\d.]+)"', svg
        ).groups()
    )
    xs = [float(cx) for cx in re.findall(r'<circle cx="([\d.]+)"', svg)]
    assert xs == pytest.approx([left, left + width / 3, left + 2 * width / 3], abs=0.01)


if __name__ == "__main__":
    if sys.argv[1:] != ["--write"]:
        raise SystemExit("usage: test_graph_static_export.py --write")
    FIXTURE.write_text(json.dumps(_expected(), indent=1) + "\n", encoding="utf-8")
    print(f"wrote {FIXTURE}")
