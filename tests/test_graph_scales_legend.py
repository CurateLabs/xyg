"""Graph color scales and the semantic legend (#34).

``color_scale`` / ``edge_color_scale`` add diverging (Rust centers the domain
on a midpoint) and ordinal (Rust samples one colormap color per ordered level)
scales beside linear and categorical ones. Semantic graphs show the Rust
semantic legend: one row per class/epistemic/status value, in the semantic
Scene's order, with Rust-owned text. The committed cross-host fixture pins the
resolved channels and legend; ``packages/xy-node/test/graph.test.mjs`` asserts
the same fixture.

Regenerate after an intended contract change with
``uv run python tests/test_graph_scales_legend.py --write``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import xyg
from xyg import _native
from xyg._figure import Figure

FIXTURE = Path(__file__).parent / "fixtures" / "graph_scales_legend_cross_host.json"
IDS = ["a", "b", "c", "d"]
EDGES = [["a", "b"], ["b", "c"], ["c", "d"]]
X = [0.0, 1.0, 2.0, 3.0]
Y = [0.0, 1.0, 0.0, 1.0]
CASES: dict[str, dict[str, Any]] = {
    "ordinal_diverging": {
        "color": ["low", "high", "mid", "low"],
        "color_scale": {"type": "ordinal", "order": ["low", "mid", "high"], "colormap": "viridis"},
        "edge_color": [-2.0, 1.0, 5.0],
        "edge_color_scale": {"type": "diverging", "midpoint": 1.0},
    },
    "linear_categorical": {
        "color": [0.0, 2.0, 4.0, 8.0],
        "color_scale": {"type": "linear", "colormap": "magma", "domain": [0.0, 10.0]},
        "edge_color": ["x", "y", "x"],
        "edge_color_scale": {"type": "categorical", "palette": ["#112233", "#445566"]},
    },
    "semantic_legend": {
        "node_class": [0, 1, 2, 1],
        "node_epistemic": [0, 3, 0, 0],
        "edge_status": [0, 1, 2],
        "theme": "dark",
    },
}


def _figure(**kwargs: Any) -> Figure:
    return Figure().graph(IDS, [tuple(edge) for edge in EDGES], layout="preset", x=X, y=Y, **kwargs)


def _channel(ch: Any) -> dict[str, Any]:
    if ch.mode == "categorical":
        return {
            "mode": "categorical",
            "categories": list(ch.categories),
            "codes": [int(c) for c in ch.codes],
            "palette": list(ch.palette)[: len(ch.categories)],
        }
    return {
        "mode": ch.mode,
        "domain": [float(v) for v in ch.domain],
        "colormap": ch.colormap,
    }


def _resolved(fig: Figure) -> dict[str, Any]:
    meta = fig._graph_meta[0]
    out: dict[str, Any] = {}
    node = fig.traces[meta["node_trace"]].color_ch
    edge = fig.traces[meta["edge_trace"]].color_ch
    if node is not None and node.mode in ("categorical", "continuous"):
        out["node_color"] = _channel(node)
    if edge is not None and edge.mode in ("categorical", "continuous"):
        out["edge_color"] = _channel(edge)
    if fig.legend_options.get("items"):
        out["legend"] = {
            "title": fig.legend_options["title"],
            "items": fig.legend_options["items"],
        }
    return out


def _expected() -> dict[str, Any]:
    return {
        "schema": "xyg.graph-scales-legend-cross-host/v1",
        "ids": IDS,
        "edges": EDGES,
        "x": X,
        "y": Y,
        "cases": {
            name: {"options": opts, **_resolved(_figure(**opts))} for name, opts in CASES.items()
        },
    }


def test_cross_host_fixture_is_current() -> None:
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == _expected()


def test_ordinal_and_diverging_scales_come_from_rust() -> None:
    out = _resolved(_figure(**CASES["ordinal_diverging"]))
    assert out["node_color"]["categories"] == ["low", "mid", "high"]
    assert out["node_color"]["codes"] == [0, 2, 1, 0]
    assert out["node_color"]["palette"] == _native.graph_ordinal_colors("viridis", 3)
    assert out["edge_color"]["domain"] == list(_native.graph_diverging_domain([-2, 1, 5], 1.0))
    assert out["edge_color"]["domain"] == [-3.0, 5.0]
    assert out["edge_color"]["colormap"] == "rdbu"


def test_linear_and_categorical_scales_pin_domain_and_palette() -> None:
    out = _resolved(_figure(**CASES["linear_categorical"]))
    assert out["node_color"] == {"mode": "continuous", "domain": [0.0, 10.0], "colormap": "magma"}
    assert out["edge_color"]["palette"] == ["#112233", "#445566"]


def test_semantic_legend_matches_the_rust_rows() -> None:
    out = _resolved(_figure(**CASES["semantic_legend"]))
    rows = _native.graph_semantic_legend(
        np.array([0, 1, 2, 1, 0, 0, 0]),
        np.array([0, 3, 0, 0, 0, 0, 0]),
        np.array([0, 0, 0, 0, 0, 1, 2]),
        theme="dark",
    )
    assert out["legend"]["title"] == "Graph semantics"
    assert [item["name"] for item in out["legend"]["items"]] == [
        _native.graph_semantic_legend_text(int(f), int(v))
        for f, v in zip(rows["field"], rows["value"], strict=True)
    ]
    assert out["legend"]["items"][0]["style"]["symbol"] == "circle"
    assert out["legend"]["items"][1]["style"]["symbol"] == "square"


def test_semantic_legend_can_be_disabled_and_never_replaces_authored_items() -> None:
    off = _figure(**CASES["semantic_legend"], semantic_legend=False)
    assert not off.legend_options.get("items")
    fig = Figure()
    fig.legend_options = {"items": [{"kind": "scatter", "name": "mine", "style": {}}]}
    fig.graph(IDS, [tuple(e) for e in EDGES], layout="preset", x=X, y=Y, node_class=[0, 1, 2, 1])
    assert [item["name"] for item in fig.legend_options["items"]] == ["mine"]


def test_chart_legend_places_the_semantic_rows() -> None:
    # A chart-level legend sets placement and styling; the graph's Rust rows
    # and title survive it (Node merges the same way).
    chart = xyg.graph_chart(
        xyg.graph(
            IDS, [tuple(e) for e in EDGES], layout="preset", x=X, y=Y, node_class=[0, 1, 2, 1]
        ),
        xyg.legend(loc="lower left"),
    )
    options = chart.figure().legend_options
    assert options["loc"] == "lower left"
    assert options["title"] == "Graph semantics"
    assert [item["name"] for item in options["items"]] == [
        item["name"] for item in _figure(node_class=[0, 1, 2, 1]).legend_options["items"]
    ]
    titled = xyg.graph_chart(
        xyg.graph(
            IDS, [tuple(e) for e in EDGES], layout="preset", x=X, y=Y, node_class=[0, 1, 2, 1]
        ),
        xyg.legend(title="Kinds"),
    )
    assert titled.figure().legend_options["title"] == "Kinds"


def test_semantic_legend_respects_authored_options_and_merges_graphs() -> None:
    # A hidden legend stays hidden, and an authored title survives.
    fig = Figure()
    fig.show_legend = False
    fig.legend_options = {"title": "My title"}
    fig.graph(IDS, [tuple(e) for e in EDGES], layout="preset", x=X, y=Y, node_class=[0, 1, 1, 1])
    assert fig.show_legend is False
    assert fig.legend_options["title"] == "My title"
    first = [item["name"] for item in fig.legend_options["items"]]
    # A second semantic graph adds its values; rows follow Rust's merged order.
    fig.graph(IDS, [tuple(e) for e in EDGES], layout="preset", x=X, y=Y, node_class=[2, 3, 3, 3])
    merged = [item["name"] for item in fig.legend_options["items"]]
    rows = _native.graph_semantic_legend(
        np.array([0, 1, 1, 1, 0, 0, 0, 2, 3, 3, 3, 0, 0, 0]),
        np.zeros(14, dtype=np.int64),
        np.zeros(14, dtype=np.int64),
        theme="light",
    )
    assert merged == [
        _native.graph_semantic_legend_text(int(f), int(v))
        for f, v in zip(rows["field"], rows["value"], strict=True)
    ]
    assert set(first) < set(merged)


def test_short_categorical_palette_warns() -> None:
    with pytest.warns(RuntimeWarning, match="colors repeat every 2"):
        _figure(
            color=["x", "y", "z", "x"],
            color_scale={"type": "categorical", "palette": ["#111111", "#222222"]},
        )


def test_scales_fail_closed() -> None:
    with pytest.raises(ValueError, match="not in the ordinal order"):
        _figure(color=["a", "z", "a", "a"], color_scale={"type": "ordinal", "order": ["a"]})
    with pytest.raises(ValueError, match="unique"):
        _figure(color=["a", "a", "a", "a"], color_scale={"type": "ordinal", "order": ["a", "a"]})
    with pytest.raises(ValueError, match="unknown colormap"):
        _figure(
            color=["a"] * 4, color_scale={"type": "ordinal", "order": ["a"], "colormap": "nope"}
        )
    with pytest.raises(ValueError, match="does not accept"):
        _figure(color=[1.0] * 4, color_scale={"type": "linear", "midpoint": 0})
    with pytest.raises(ValueError, match="must be a dict"):
        _figure(color=[1.0] * 4, color_scale={"type": "log"})
    with pytest.raises(ValueError, match="per-item color"):
        _figure(color="#ff0000", color_scale={"type": "linear"})
    with pytest.raises(ValueError, match="representable in f64"):
        _figure(
            color=[0.0, 1.0, 2.0, 3.0],
            color_scale={"type": "diverging", "midpoint": float(np.finfo(np.float64).max)},
        )
    with pytest.raises(ValueError, match="replace color_scale"):
        _figure(node_class=[0, 1, 2, 1], color_scale={"type": "linear"})


_LEGEND_PROBE = """
(async () => {
  try {
    const view = window.__fcProbeView;
    view._layout(); view._drawNow(); view._raf = null;
    const rows = [...document.querySelectorAll('[data-xy-slot="legend_item"]')]
      .map((row) => row.textContent.trim());
    const title = document.querySelector('[data-xy-slot="legend_title"]');
    const node = view.gpuTraces.find((t) => t.trace.id === __NODE_TRACE__);
    const read = ([x, y]) => {
      const px = new Uint8Array(4);
      view.gl.readPixels(
        Math.round((x - view.plot.x) * view.dpr),
        Math.round(view.canvas.height - (y - view.plot.y) * view.dpr),
        1, 1, view.gl.RGBA, view.gl.UNSIGNED_BYTE, px);
      return Array.from(px);
    };
    const pixels = __POINTS__.map(([x, y]) => read(view._projectDataPoint(node.xAxis, node.yAxis, x, y, null)));
    document.body.setAttribute("data-xy-legend-probe", JSON.stringify({
      rows, title: title && title.textContent.trim(), pixels }));
  } catch (error) {
    document.body.setAttribute("data-xy-legend-probe-error", String((error && error.stack) || error));
  }
})();
"""


@pytest.mark.parametrize("case", ["ordinal_diverging", "semantic_legend"])
def test_browser_paints_scale_colors_and_legend_rows(case: str, tmp_path: Path) -> None:
    from conftest import probe_document, run_browser_probe
    from xyg.export import find_chromium

    chromium = find_chromium()
    if chromium is None:
        pytest.skip("Chromium unavailable")
    chart = xyg.graph_chart(
        xyg.graph(IDS, [tuple(e) for e in EDGES], layout="preset", x=X, y=Y, **CASES[case]),
        width=640,
        height=480,
    )
    fig = chart.figure()
    meta = fig._graph_meta[0]
    script = _LEGEND_PROBE.replace("__NODE_TRACE__", str(meta["node_trace"])).replace(
        "__POINTS__", json.dumps(list(zip(X, Y, strict=True)))
    )
    result = run_browser_probe(
        chromium,
        probe_document(chart, f"<script>{script}</script>"),
        tmp_path / f"graph-legend-{case}.html",
        "data-xy-legend-probe",
        label=f"graph legend {case}",
    )
    resolved = _resolved(fig)
    if case == "semantic_legend":
        assert result["title"] == "Graph semantics"
        assert result["rows"] == [item["name"] for item in resolved["legend"]["items"]]
        return
    # Ordinal nodes paint their level's Rust color; the legend lists levels
    # in scale order.
    palette = resolved["node_color"]["palette"]
    for pixel, code in zip(result["pixels"], resolved["node_color"]["codes"], strict=True):
        expected = [int(palette[code][i : i + 2], 16) for i in (1, 3, 5)]
        assert all(abs(p - e) <= 3 for p, e in zip(pixel[:3], expected, strict=True)), (
            pixel,
            palette[code],
        )


if __name__ == "__main__":
    if sys.argv[1:] != ["--write"]:
        raise SystemExit("usage: test_graph_scales_legend.py --write")
    FIXTURE.write_text(json.dumps(_expected(), indent=1) + "\n", encoding="utf-8")
    print(f"wrote {FIXTURE}")
