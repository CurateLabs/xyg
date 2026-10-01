"""GraphForge result compositions on the Python host (xyg#37).

The same Rust composition the Node and browser hosts run: request and document
bytes are pinned against Node by tests/fixtures/graphforge/cross_host.json, and
the Python helpers paint the Rust planes with the ordinary components.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pytest

import xyg
from xyg._graphforge import compose_graphforge_request
from xyg._tooltip_columns import decode_tooltip_rows

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "tests" / "fixtures" / "graphforge" / "results"
DERIVED = ROOT / "tests" / "fixtures" / "graphforge" / "derived"
MANIFEST = json.loads((RESULTS / "manifest.json").read_text(encoding="utf-8"))
EXPECT = json.loads(
    (ROOT / "tests" / "fixtures" / "graphforge" / "composition_expectations.json").read_text(
        encoding="utf-8"
    )
)
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _arrow(name: str) -> bytes:
    return (RESULTS / f"{name}.arrow").read_bytes()


def _base(name: str) -> dict:
    spec = MANIFEST["bases"][name]
    return {
        "tables": [_arrow(spec["nodes"]), _arrow(spec["edges"])],
        "generation": spec["generation"],
    }


def _gen(name: str) -> str:
    return MANIFEST["bases"][name]["generation"]


def _compose(*names: str, **layer: object) -> xyg.GraphForgeComposition:
    return xyg.compose_graphforge(
        base=_base("cyclic"),
        layers=[
            {"result": _arrow(n), "intent": "graph", "generation": _gen("cyclic"), **layer}
            for n in names
        ],
    )


def _generator():
    path = ROOT / "scripts" / "gen_graphforge_cross_host.py"
    spec = importlib.util.spec_from_file_location("gen_graphforge_cross_host", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_python_reproduces_the_cross_host_bytes_for_every_case() -> None:
    gen = _generator()
    fixture = json.loads((ROOT / "tests/fixtures/graphforge/cross_host.json").read_text())
    assert len(fixture["cases"]) == len(gen.cases()) >= 99
    for case in fixture["cases"]:
        request = gen.build_request(case)
        assert hashlib.sha256(request).hexdigest() == case["request_sha256"], case["name"]
        document = compose_graphforge_request(request)
        assert hashlib.sha256(document).hexdigest() == case["document_sha256"], case["name"]


def test_pagerank_joins_by_uuid_with_provenance() -> None:
    c = _compose("pagerank", result_id="rank-1")
    expected = EXPECT["layers"]["pagerank"]["rows"]
    layer = c.layers[0]
    k = len(layer["value_names"])
    score = layer["value_names"].index("score")
    for uuid, want in expected.items():
        i = c.node_index(uuid)
        assert i >= 0
        assert layer["node_values"][i * k + score] == pytest.approx(want["score"])
        identity = c.identify("node", i)
        assert identity["uuid"] == uuid
        assert identity["layers"] == [{"layer": 0, "result_id": "rank-1", "row": want["row"]}]


def test_derived_edges_are_distinct_and_carry_no_fake_identity() -> None:
    c = _compose("pagerank", "node_similarity")
    derived = [j for j in range(c.edges.count) if c.edges.derived[j]]
    assert derived
    for j in derived:
        identity = c.identify("edge", j)
        assert identity["uuid"] is None and identity["derived"] is True
    persisted = next(j for j in range(c.edges.count) if not c.edges.derived[j])
    assert c.edge_index(c.edges.uuid[persisted]) == persisted
    assert c.select([c.nodes.uuid[1], c.edges.uuid[persisted]]) == {
        "nodes": [1],
        "edges": [persisted],
    }


def test_failures_carry_stable_codes() -> None:
    with pytest.raises(xyg.GraphForgeCompositionError) as stale:
        xyg.compose_graphforge(
            base=_base("cyclic"),
            layers=[{"result": _arrow("pagerank"), "intent": "graph", "generation": _gen("dag")}],
        )
    assert stale.value.code == "GF_COMPOSE_GENERATION_STALE"
    with pytest.raises(xyg.GraphForgeCompositionError) as needs:
        xyg.compose_graphforge(
            layers=[{"result": _arrow("node2vec"), "intent": "embedding-coordinates"}]
        )
    assert needs.value.code == "GF_COMPOSE_COORDINATES_REQUIRED"
    with pytest.raises(xyg.GraphForgeCompositionError) as malformed:
        xyg.compose_graphforge(layers=[{"result": _arrow("pagerank")[:200], "intent": "graph"}])
    assert malformed.value.code == "GF_ARROW_MALFORMED"
    with pytest.raises(xyg.GraphForgeCompositionError) as bad:
        xyg.compose_graphforge(layers=[{"result": b"x", "intent": "graph", "generation": "nope"}])
    assert bad.value.code == "GF_COMPOSE_REQUEST_INVALID"


def test_diagnostics_never_carry_identities() -> None:
    c = _compose("pagerank", "louvain")
    text = json.dumps(c.diagnostics())
    assert not UUID.search(text)
    assert c.diagnostics()["nodes"] == c.nodes.count


def test_graph_chart_paints_rust_planes_with_typed_hover_rows() -> None:
    c = _compose("pagerank", "node_similarity")
    chart = xyg.graphforge_chart(c, width=480, height=320, title="GraphForge")
    fig = chart.figure()
    assert [row["name"] for row in fig.legend_options["items"]] == [
        r["text"] for r in c.legend["rows"]
    ]
    spec, blob = fig.build_payload()
    edges, nodes = spec["traces"][0], spec["traces"][1]
    # Every hover row ships as typed columns, never JSON numbers.
    assert "tooltip_columns" in edges and "tooltip_columns" in nodes
    node_rows = decode_tooltip_rows(spec, blob, nodes)
    assert [r["id"] for r in node_rows] == c.nodes.uuid
    edge_rows = decode_tooltip_rows(spec, blob, edges)
    derived = [r for r in edge_rows if r["edge_id"].startswith("derived:")]
    assert derived and all("provenance_row" not in r for r in derived)
    svg = fig.to_svg()
    assert "<svg" in (svg.decode() if isinstance(svg, bytes) else svg)


def test_table_and_bar_chart_compositions() -> None:
    table = xyg.compose_graphforge(
        layers=[{"result": _arrow("chromatic_number"), "intent": "table"}]
    )
    assert table.kind == "table" and table.table["columns"] == ["chromatic_number"]
    html = xyg.graphforge_table_html(table)
    assert '<th scope="col">chromatic_number</th>' in html and "<script" not in html
    with pytest.raises(TypeError, match="graphforge_table_html"):
        xyg.graphforge_chart(table)

    census = xyg.compose_graphforge(
        layers=[{"result": _arrow("triad_census"), "intent": "bar-chart"}]
    )
    chart = xyg.graphforge_chart(census, width=480, height=320)
    fig = chart.figure()
    k = len(census.chart["categories"])
    assert fig.axis_options["x"]["tick_labels"] == census.chart["categories"]
    assert list(fig.axis_options["x"]["domain"]) == [-0.5, k - 0.5]
    assert (
        fig.traces[0].tooltip_rows[0][census.chart["category_name"]]
        == census.chart["categories"][0]
    )
    svg = fig.to_svg()
    svg = svg.decode() if isinstance(svg, bytes) else svg
    for category in census.chart["categories"]:
        assert f">{category}<" in svg


def test_embedding_views_never_plot_raw_dimensions() -> None:
    parallel = xyg.compose_graphforge(
        layers=[{"result": _arrow("node2vec"), "intent": "parallel-coordinates"}]
    )
    fig = xyg.graphforge_chart(parallel).figure()
    dims = parallel.vectors["dimensions"]
    assert fig.traces[0].kind == "segments"
    assert len(fig.traces[0].tooltip_rows) == len(parallel.vectors["uuid"]) * (dims - 1)
    placed = xyg.compose_graphforge(
        layers=[
            {
                "result": _arrow("node2vec"),
                "intent": "embedding-coordinates",
                "coordinates": (DERIVED / "node2vec-coordinates.arrow").read_bytes(),
            }
        ]
    )
    fig = xyg.graphforge_chart(placed).figure()
    assert fig.traces[0].kind == "scatter"
    assert [r["id"] for r in fig.traces[0].tooltip_rows] == placed.points["uuid"]


def test_ledger_and_render_scene() -> None:
    ledger = xyg.graphforge_ledger()
    assert {"schema", "version", "disposition", "composition", "intents", "fields"} <= set(
        ledger[0]
    )
    assert any(row["intents"] == ["graph"] for row in ledger)
    c = xyg.compose_graphforge(
        base=_base("cyclic"),
        layers=[{"result": _arrow("pagerank"), "intent": "graph", "generation": _gen("cyclic")}],
        render={"width": 480, "height": 320, "theme": "light"},
    )
    assert c.scene is not None and c.scene["node_stable_id_base"] == 2**32
    assert len(c.scene["x"]) == c.nodes.count


def test_large_parallel_coordinates_keep_every_segment_identity() -> None:
    from types import SimpleNamespace

    import numpy as np

    n, dims = 25_001, 5  # 100,004 segments: past the old 100k hover-row cap
    uuids = [f"01a0f3fd-0000-7000-8000-{i:012x}" for i in range(n)]
    composition = SimpleNamespace(
        kind="parallel-coordinates",
        vectors={
            "dimensions": dims,
            "uuid": uuids,
            "name": [""] * n,
            "values": np.random.default_rng(0).random(n * dims),
            "domain": [0.0, dims - 1.0, 0.0, 1.0],
        },
    )
    fig = xyg.graphforge_chart(composition).figure()
    rows = fig.traces[0].tooltip_rows
    assert len(rows) == n * (dims - 1)
    assert rows[-1] == {"id": uuids[-1], "dimension": dims - 2}
    spec, blob = fig.build_payload()
    assert "tooltip_columns" in spec["traces"][0]
