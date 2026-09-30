"""Compound graph frames and disclosure on the composed graph mark (#34).

Compound graphs (GraphForge ``parent_uuid``) paint a Rust frame around every
visible group: transitive bounds over all descendants, the semantic Scene's
paint, and a screen pad clearing the largest visible member marker.
``collapsed=`` collapses groups: the full graph is laid out once (Direct LOD),
then Rust hides descendants, routes crossing edges to the collapsed group,
drops newly internal edges, and propagates hidden interaction state; picking
a collapsed group reports its hidden members. The committed cross-host
fixture pins the composed result; ``packages/xy-node/test/graph.test.mjs``
asserts the same fixture.

Regenerate after an intended contract change with
``uv run python tests/test_graph_compound.py --write``.
"""

from __future__ import annotations

import functools
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import xyg
from xyg import _graph, _native, interaction
from xyg._figure import Figure

FIXTURE = Path(__file__).parent / "fixtures" / "graph_compound_cross_host.json"


def _uuid(i: int) -> str:
    return str(uuid.UUID(int=i + 1))


# 0 group A (children 1, 2), 3 group B (child 4), 5 outside.
PARENTS = [None, 0, 0, None, 3, None]
NAMES = ["A", "a1", "a2", "B", "b1", "out"]
EDGES = [[1, 5], [1, 2], [2, 4], [5, 0]]
X = [0.0, 0.0, 1.0, 5.0, 5.0, 9.0]
Y = [0.0, 1.0, 0.0, 0.0, 1.0, 5.0]
CASES: dict[str, dict[str, Any]] = {
    "expanded": {},
    "collapsed": {"collapsed": [_uuid(0)]},
    "collapsed_semantic": {
        "collapsed": [_uuid(0)],
        "node_class": [1, 2, 2, 3, 4, 5],
        # a1 is selected while hidden: A inherits the selection.
        "visual_state_flags": [0, 2, 0, 0, 0, 0],
    },
}


def _tables() -> tuple[dict[str, Any], dict[str, Any]]:
    nodes = {
        "node_uuid": [_uuid(i) for i in range(len(NAMES))],
        "parent_uuid": [None if p is None else _uuid(p) for p in PARENTS],
        "name": NAMES,
    }
    edges = {
        "edge_uuid": [_uuid(100 + i) for i in range(len(EDGES))],
        "src_uuid": [_uuid(s) for s, _ in EDGES],
        "dst_uuid": [_uuid(t) for _, t in EDGES],
    }
    return nodes, edges


def _figure(**kwargs: Any) -> Figure:
    nodes, edges = _tables()
    return Figure().graph(nodes, edges, layout="preset", x=X, y=Y, **kwargs)


def _composed(fig: Figure) -> dict[str, Any]:
    meta = fig._graph_meta[0]
    node = fig.traces[meta["node_trace"]]
    frame = node.style_channels.get("compound_frame")
    return {
        "ids": meta["ids"],
        "sources": meta["sources"],
        "targets": meta["targets"],
        "edge_ids": meta.get("edge_ids"),
        "compound_frames": meta.get("compound_frames"),
        "compound_collapsed": meta.get("compound_collapsed"),
        "visual_states": meta.get("visual_states"),
        "frame_rows": None if frame is None else [[float(v) for v in row] for row in frame.values],
        "pick": {
            str(i): {
                k: v
                for k, v in interaction.pick(fig, meta["node_trace"], i).items()
                if k.startswith("compound_")
            }
            for i in range(len(meta["ids"]))
        },
    }


def _expected() -> dict[str, Any]:
    nodes, edges = _tables()
    return {
        "schema": "xyg.graph-compound-cross-host/v1",
        "nodes": nodes,
        "edges": edges,
        "x": X,
        "y": Y,
        "cases": {
            name: {"options": opts, **_composed(_figure(**opts))} for name, opts in CASES.items()
        },
    }


def test_cross_host_fixture_is_current() -> None:
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == _expected()


def test_collapse_routes_edges_and_keeps_identity() -> None:
    out = _composed(_figure(collapsed=[_uuid(0)]))
    assert out["ids"] == [_uuid(0), _uuid(3), _uuid(4), _uuid(5)]
    # a1->out routes as A->out, a1->a2 is internal and drops, a2->b1 routes as
    # A->b1, out->A stays.
    assert list(zip(out["sources"], out["targets"], strict=True)) == [(0, 3), (0, 2), (3, 0)]
    assert out["edge_ids"] == [_uuid(100), _uuid(102), _uuid(103)]
    assert out["compound_collapsed"] == [_uuid(0)]
    assert out["pick"]["0"] == {
        "compound_collapsed": True,
        "compound_member_count": 2,
        "compound_members": [_uuid(1), _uuid(2)],
        "compound_members_truncated": False,
    }
    assert out["pick"]["1"] == {}


def test_hidden_selection_propagates_to_the_collapsed_group() -> None:
    out = _composed(_figure(**CASES["collapsed_semantic"]))
    selected = int(_native.graph_visual_states(np.array([2], dtype=np.uint32))[0])
    assert out["visual_states"][0] == selected


def test_frames_are_the_rust_frames() -> None:
    fig = _figure()
    out = _composed(fig)
    assert out["compound_frames"] == [_uuid(0), _uuid(3)]
    frames = _native.graph_compound_frames(
        X,
        Y,
        np.full(6, 4.0),
        [0, 0, 0, 0, 3, 0],
        [0, 1, 1, 0, 1, 0],
        [0] * 6,
        np.zeros((6, 4)),
        [1.0] * 6,
    )
    rows = out["frame_rows"]
    for node, bounds, rgba, pad in zip(
        frames["node"], frames["bounds"], frames["rgba"], frames["pad"], strict=True
    ):
        row = rows[int(node)]
        assert row[0] + X[int(node)] == pytest.approx(bounds[0])
        assert row[3] + Y[int(node)] == pytest.approx(bounds[3])
        assert row[4:8] == [float(c) for c in rgba]
        assert row[9] == pytest.approx(pad)
    assert rows[5][8] == 0.0  # no frame on a plain node


def test_per_row_arguments_follow_the_visible_rows() -> None:
    fig = _figure(
        collapsed=[_uuid(0)],
        color=["#ff0000", "#00ff00", "#00ff00", "#0000ff", "#0000ff", "#111111"],
    )
    node = fig.traces[fig._graph_meta[0]["node_trace"]]
    rgba = np.rint(np.asarray(node.color_ch.rgba) * 255).astype(int)
    assert rgba[:, :3].tolist() == [[255, 0, 0], [0, 0, 255], [0, 0, 255], [17, 17, 17]]


def test_disclosure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="not nodes"):
        _figure(collapsed=["nope"])
    with pytest.raises(ValueError, match="valid acyclic parent forest"):
        _figure(collapsed=[_uuid(5)])  # not a group
    with pytest.raises(ValueError, match="needs compound parents"):
        Figure().graph(
            ["a", "b"], [("a", "b")], layout="preset", x=[0, 1], y=[0, 1], collapsed=["a"]
        )
    monkeypatch.setattr(_graph, "run_layout", functools.partial(_graph.run_layout, node_budget=2))
    with pytest.raises(ValueError, match="Direct LOD"):
        _figure(collapsed=[_uuid(0)])
    # Frames need exact identity: Aggregate LOD records their omission.
    assert _figure()._graph_meta[0]["compound_frames"] == "omitted:aggregate"


def test_compound_frames_export_as_padded_frame_rects() -> None:
    nodes, edges = _tables()
    chart = xyg.graph_chart(xyg.graph(nodes, edges, layout="preset", x=X, y=Y))
    fig = chart.figure()
    rows = fig.traces[fig._graph_meta[0]["node_trace"]].style_channels["compound_frame"].values
    svg = chart.to_svg()
    # One stroked, unfilled rect per group, in the Rust frame paint.
    for row in (rows[0], rows[3]):
        paint = "rgb({},{},{})".format(*(int(c) for c in row[4:7]))
        assert re.search(rf'<rect [^>]*fill-opacity="0" stroke="{re.escape(paint)}"', svg), paint


_FRAME_PROBE = """
(async () => {
  try {
    const view = window.__fcProbeView;
    view._layout(); view._drawNow(); view._raf = null;
    const node = view.gpuTraces.find((t) => t.trace.id === __NODE_TRACE__);
    const ctx = view.chrome.getContext("2d");
    const read = ([x, y]) => Array.from(
      ctx.getImageData(Math.round(x * view.dpr), Math.round(y * view.dpr), 1, 1).data);
    // Group A spans (0,0)-(1,1); its frame sits PAD px outside that box.
    const lo = view._projectDataPoint(node.xAxis, node.yAxis, 0, 0, null);
    const hi = view._projectDataPoint(node.xAxis, node.yAxis, 1, 1, null);
    const midY = (lo[1] + hi[1]) / 2;
    document.body.setAttribute("data-xy-frame-probe", JSON.stringify({
      edge: read([Math.min(lo[0], hi[0]) - __PAD__, midY]),
      inside: read([(lo[0] + hi[0]) / 2, midY]),
    }));
  } catch (error) {
    document.body.setAttribute("data-xy-frame-probe-error", String((error && error.stack) || error));
  }
})();
"""


def test_browser_strokes_padded_frames_under_the_data(tmp_path: Path) -> None:
    from conftest import probe_document, run_browser_probe
    from xyg.export import find_chromium

    chromium = find_chromium()
    if chromium is None:
        pytest.skip("Chromium unavailable")
    nodes, edges = _tables()
    chart = xyg.graph_chart(
        xyg.graph(
            nodes,
            edges,
            layout="preset",
            x=[0.0, 0.0, 1.0, 20, 20, 30],
            y=[0.0, 1.0, 1.0, 20, 21, 30],
        ),
        width=640,
        height=480,
    )
    fig = chart.figure()
    meta = fig._graph_meta[0]
    row = fig.traces[meta["node_trace"]].style_channels["compound_frame"].values[0]
    script = _FRAME_PROBE.replace("__NODE_TRACE__", str(meta["node_trace"])).replace(
        "__PAD__", repr(float(row[9]))
    )
    result = run_browser_probe(
        chromium,
        probe_document(chart, f"<script>{script}</script>"),
        tmp_path / "graph-compound.html",
        "data-xy-frame-probe",
        label="graph compound frames",
    )
    # The frame line paints the Rust frame color (alpha-blended over the plot
    # background); the group's interior stays unpainted by the frame.
    assert result["edge"][3] > 0, result
    rgb = [int(c) for c in row[4:7]]
    assert max(abs(a - b) for a, b in zip(result["edge"][:3], rgb, strict=True)) < 90, (result, rgb)
    assert result["inside"][:3] != result["edge"][:3]


if __name__ == "__main__":
    if sys.argv[1:] != ["--write"]:
        raise SystemExit("usage: test_graph_compound.py --write")
    FIXTURE.write_text(json.dumps(_expected(), indent=1) + "\n", encoding="utf-8")
    print(f"wrote {FIXTURE}")
