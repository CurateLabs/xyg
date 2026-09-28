"""Graph edge identity through routing and LOD (#33).

Every painted edge segment resolves to the exact GraphForge edge UUID when its
render edge is one source edge (Direct / EdgeSample), or to the deterministic
Aggregate membership — never to an unrelated edge. The committed cross-host
fixture pins the pick reply for every segment; ``packages/xy-node/test/
graph.test.mjs`` asserts the same fixture so Python and Node agree.

Regenerate after an intended contract change with
``uv run python tests/test_graph_edge_identity.py --write``.
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

from xyg import _graph, _native, interaction
from xyg._figure import Figure

FIXTURE = Path(__file__).parent / "fixtures" / "graph_edge_identity_cross_host.json"
PICK_KEYS = ("render_edge", "edge_count", "source_edges", "members_truncated", "edge_ids")


def _uuid(i: int) -> str:
    return str(uuid.UUID(int=i + 1))


def _graphforge(n_nodes: int, edges: list[tuple[int, int]]) -> tuple[dict, dict]:
    nodes = {"node_uuid": [_uuid(i) for i in range(n_nodes)]}
    table = {
        "edge_uuid": [_uuid(1000 + i) for i in range(len(edges))],
        "src_uuid": [_uuid(s) for s, _ in edges],
        "dst_uuid": [_uuid(t) for _, t in edges],
    }
    return nodes, table


# Two tight node pairs far apart: parallels, a reciprocal, a self-loop, an
# intra-pair edge, and cross-pair edges in both directions.
X = [0.0, 0.1, 100.0, 100.1]
Y = [0.0, 0.1, 100.0, 100.1]
EDGES = [(0, 2), (0, 2), (2, 0), (0, 0), (0, 1), (1, 3), (3, 1)]
CASES = {
    "direct": {"node_budget": 100, "edge_budget": 100, "edge_curve": "straight"},
    "direct_curved": {"node_budget": 100, "edge_budget": 100, "edge_curve": "curve"},
    "edge_sample": {"node_budget": 100, "edge_budget": 3, "edge_curve": "straight"},
    "aggregate": {"node_budget": 2, "edge_budget": 100, "edge_curve": "straight"},
}


def _figure(
    monkeypatch: pytest.MonkeyPatch | None,
    *,
    node_budget: int,
    edge_budget: int,
    edge_curve: str,
    edges: list[tuple[int, int]] = EDGES,
    x: list[float] = X,
    y: list[float] = Y,
) -> Figure:
    # The public graph mark has no budget knobs; bound run_layout forces a tier.
    original = _graph.run_layout
    layout = functools.partial(original, node_budget=node_budget, edge_budget=edge_budget)
    if monkeypatch is not None:
        monkeypatch.setattr(_graph, "run_layout", layout)
    else:
        _graph.run_layout = layout
    try:
        nodes, table = _graphforge(len(x), edges)
        return Figure().graph(nodes, table, layout="preset", x=x, y=y, edge_curve=edge_curve)
    finally:
        if monkeypatch is None:
            _graph.run_layout = original


def _picks(fig: Figure) -> list[dict[str, Any]]:
    meta = fig._graph_meta[0]
    n_segments = len(meta["render_edge_index"])
    out = []
    for segment in range(n_segments):
        reply = interaction.pick(fig, meta["edge_trace"], segment)
        assert reply is not None
        out.append({key: reply[key] for key in PICK_KEYS if key in reply})
    return out


def _expected() -> dict[str, Any]:
    cases = {}
    for name, opts in CASES.items():
        fig = _figure(None, **opts)
        meta = fig._graph_meta[0]
        cases[name] = {
            **opts,
            "tier_name": meta["tier_name"],
            "edge_ids": meta.get("edge_ids"),
            "picks": _picks(fig),
        }
    return {
        "schema": "xyg.graph-edge-identity-cross-host/v1",
        "x": X,
        "y": Y,
        "node_uuid": [_uuid(i) for i in range(len(X))],
        "edges": [
            {"edge_uuid": _uuid(1000 + i), "src": s, "dst": t} for i, (s, t) in enumerate(EDGES)
        ],
        "cases": cases,
    }


def test_native_membership_is_exact_at_every_tier() -> None:
    x = np.asarray(X)
    y = np.asarray(Y)
    sources = np.asarray([s for s, _ in EDGES], dtype=np.uint64)
    targets = np.asarray([t for _, t in EDGES], dtype=np.uint64)
    for node_budget, edge_budget in ((100, 100), (100, 3), (2, 100)):
        render, (offsets, members) = _native.graph_build_render_with_membership(
            x, y, sources, targets, node_budget=node_budget, edge_budget=edge_budget
        )
        _, _, member_of, edge_s, edge_t, tier, _ = render
        assert len(offsets) == len(edge_s) + 1
        assert int(offsets[-1]) == len(members)
        assert len(set(members.tolist())) == len(members)
        for r in range(len(edge_s)):
            group = members[int(offsets[r]) : int(offsets[r + 1])]
            assert len(group) >= 1
            assert np.all(np.diff(group.astype(np.int64)) > 0)
            for e in group.tolist():
                # Every member's endpoints collapse onto its render edge.
                assert member_of[sources[e]] == edge_s[r]
                assert member_of[targets[e]] == edge_t[r]
            if tier < 2:
                assert len(group) == 1


def test_direct_pick_returns_exact_edge_uuid_for_every_routed_segment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fig = _figure(monkeypatch, **CASES["direct"])
    meta = fig._graph_meta[0]
    assert meta["tier_name"] == "direct"
    edge_uuids = [_uuid(1000 + i) for i in range(len(EDGES))]
    assert meta["edge_ids"] == edge_uuids
    for segment, source in enumerate(meta["render_edge_index"]):
        reply = interaction.pick(fig, meta["edge_trace"], segment)
        assert reply["edge_count"] == 1
        # Loop sides, arrow wings, and parallel/reciprocal siblings all name
        # their own source edge.
        assert reply["edge_ids"] == [edge_uuids[source]]
        assert reply["edge_id"] == edge_uuids[source]


def test_aggregate_pick_reports_membership_never_one_invented_edge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fig = _figure(monkeypatch, **CASES["aggregate"])
    meta = fig._graph_meta[0]
    assert meta["tier_name"] == "aggregate"
    assert "edge_ids" not in meta
    assert "edge_tooltip_rows" in meta
    edge_trace = fig.traces[meta["edge_trace"]]
    rows = edge_trace.tooltip_rows
    assert rows is not None and all("edge_id" not in row for row in rows)
    seen: set[int] = set()
    for segment in range(len(meta["render_edge_index"])):
        reply = interaction.pick(fig, meta["edge_trace"], segment)
        assert reply["edge_count"] == len(reply["source_edges"]) >= 1
        assert "edge_id" not in reply
        assert reply["edge_ids"] == [_uuid(1000 + e) for e in reply["source_edges"]]
        seen.update(reply["source_edges"])
    # Cross-pair edges only: the self-loop (3) and intra-pair edge (4) are
    # not painted at Aggregate and are never attributed.
    assert seen == {0, 1, 2, 5, 6}


def test_membership_stays_host_side() -> None:
    fig = _figure(None, **CASES["aggregate"])
    for meta in fig._graph_meta:
        assert not any(key.startswith("render_edge_member") for key in meta)


def test_pick_membership_truncates_deterministically(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = _graph.GRAPH_EDGE_PICK_MEMBER_CAP
    many = [(0, 2)] * (cap + 5)
    fig = _figure(
        monkeypatch,
        node_budget=2,
        edge_budget=100,
        edge_curve="straight",
        edges=many,
    )
    meta = fig._graph_meta[0]
    reply = interaction.pick(fig, meta["edge_trace"], 0)
    assert reply["edge_count"] == cap + 5
    assert reply["members_truncated"] is True
    assert reply["source_edges"] == list(range(cap))
    assert len(reply["edge_ids"]) == cap


def test_cross_host_fixture_matches_python_pick_replies() -> None:
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == _expected()


_BROWSER_PROBE = """
(async () => {
  try {
    const view = window.__fcProbeView;
    if (!view) throw new Error("chart view was not captured");
    view._layout();
    view._drawNow();
    view._raf = null;
    const g = view.gpuTraces.find((trace) => trace.trace.id === EDGE_TRACE);
    if (!g || !g._segmentCpu) throw new Error("graph edge trace missing");
    const geom = view._polarGeometry();
    const hits = [];
    for (let i = 0; i < g.n; i++) {
      const [[x0, y0], [x1, y1]] = view._projectSegmentEndpoints(g, g._segmentCpu, i, geom);
      const hit = view._hoverAt((x0 + x1) / 2 - view.plot.x, (y0 + y1) / 2 - view.plot.y);
      if (!hit || hit.g !== g) continue;
      const row = view._localRow(hit);
      hits.push({index: hit.index, edge_id: row.edge_id ?? null, edge_count: row.edge_count ?? null});
    }
    document.body.setAttribute("data-xy-edge-probe", JSON.stringify({hits}));
  } catch (error) {
    document.body.setAttribute(
      "data-xy-edge-probe-error", String((error && error.stack) || error)
    );
  }
})();
"""


@pytest.mark.parametrize("case", ["direct", "aggregate"])
def test_browser_edge_hover_rows_carry_host_identity(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import xyg
    from conftest import probe_document, run_browser_probe
    from xyg.export import find_chromium

    chromium = find_chromium()
    if chromium is None:
        pytest.skip("Chromium unavailable")
    opts = CASES[case]
    original = _graph.run_layout
    monkeypatch.setattr(
        _graph,
        "run_layout",
        functools.partial(
            original, node_budget=opts["node_budget"], edge_budget=opts["edge_budget"]
        ),
    )
    # A narrow x span keeps parallel/reciprocal offsets several pixels apart.
    x = [0.0, 0.1, 4.0, 4.1]
    y = [0.0, 0.1, 4.0, 4.1]
    nodes, table = _graphforge(len(x), EDGES)
    chart = xyg.graph_chart(
        xyg.graph(nodes, table, layout="preset", x=x, y=y), width=640, height=480
    )
    fig = chart.figure()
    meta = fig._graph_meta[0]
    host = {
        i: interaction.pick(fig, meta["edge_trace"], i)
        for i in range(len(meta["render_edge_index"]))
    }
    script = _BROWSER_PROBE.replace("EDGE_TRACE", str(meta["edge_trace"]))
    result = run_browser_probe(
        chromium,
        probe_document(chart, f"<script>{script}</script>"),
        tmp_path / f"graph-edge-{case}.html",
        "data-xy-edge-probe",
        label=f"graph edge identity {case}",
    )
    hits = result["hits"]
    assert hits, result
    for hit in hits:
        expected = host[hit["index"]]
        if case == "direct":
            assert hit["edge_id"] == expected["edge_ids"][0], (hit, expected)
            assert hit["edge_count"] is None
        else:
            assert hit["edge_id"] is None, hit
            assert hit["edge_count"] == expected["edge_count"], (hit, expected)
    if case == "direct":
        # Every edge, including reciprocal/parallel siblings and the self-loop,
        # is hoverable and resolves to its own UUID.
        assert {hit["edge_id"] for hit in hits} == {_uuid(1000 + i) for i in range(len(EDGES))}
    else:
        assert {hit["edge_count"] for hit in hits} == {2, 3}, hits


if __name__ == "__main__":
    if sys.argv[1:] != ["--write"]:
        raise SystemExit("usage: test_graph_edge_identity.py --write")
    FIXTURE.write_text(json.dumps(_expected(), indent=1) + "\n", encoding="utf-8")
    print(f"wrote {FIXTURE}")
