"""Painted graph labels from one Rust label plan (#34).

Node and edge labels share ``xyg_graph_label_plan``: Rust budgets candidates,
orders them by visual state and priority, truncates to 32 characters, and
gives each label the smallest isotropic zoom scale (screen px per data unit)
from which it paints without overlapping a higher-ranked visible label. Hosts
ship the plan as per-item placement; the browser only compares the view scale
with each threshold. The committed cross-host fixture pins the plan;
``packages/xy-node/test/graph.test.mjs`` asserts the same fixture.

Regenerate after an intended contract change with
``uv run python tests/test_graph_label_plan.py --write``.
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

FIXTURE = Path(__file__).parent / "fixtures" / "graph_label_plan_cross_host.json"
IDS = ["alpha", "beta", "gamma-long-name-that-keeps-going-and-going", "delta", "eps", "zeta"]
X = [0.0, 1.0, 2.0, 0.0, 1.0, 2.0]
Y = [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]
EDGES = [
    ["alpha", "beta"],
    ["beta", "gamma-long-name-that-keeps-going-and-going"],
    ["delta", "eps"],
    ["alpha", "delta"],
    ["eps", "eps"],
]
EDGE_LABELS = ["ab", "bg", "de", None, "loop"]
PRIORITY = [5.0, 1.0, 4.0, 2.0, 3.0, 0.0]
CASES = {
    "straight": {"edge_curve": "straight", "label_budget": 64},
    "curved": {"edge_curve": "curve", "label_budget": 64},
    "budget": {"edge_curve": "straight", "label_budget": 3},
}


def _figure(edge_curve: str, label_budget: int) -> Figure:
    return Figure().graph(
        IDS,
        [tuple(edge) for edge in EDGES],
        layout="preset",
        x=X,
        y=Y,
        edge_curve=edge_curve,
        label_priority=PRIORITY,
        label_budget=label_budget,
        edge_label=EDGE_LABELS,
    )


def _plan(fig: Figure) -> dict[str, Any]:
    meta = fig._graph_meta[0]
    node = fig.traces[meta["node_trace"]].style_channels["label_plan"].values
    edge_channel = fig.traces[meta["edge_trace"]].style_channels.get("label_plan")
    segments = meta.get("edge_label_segments", [])
    return {
        "node_labels": meta["node_labels"],
        "node_plan": [[float(v) for v in row] for row in node],
        "edge_label_segments": segments,
        "edge_label_text": meta.get("edge_label_text", []),
        "edge_plan": [[float(v) for v in edge_channel.values[s]] for s in segments],
    }


def _expected() -> dict[str, Any]:
    return {
        "schema": "xyg.graph-label-plan-cross-host/v1",
        "ids": IDS,
        "x": X,
        "y": Y,
        "edges": EDGES,
        "edge_labels": EDGE_LABELS,
        "label_priority": PRIORITY,
        "cases": {name: {**opts, **_plan(_figure(**opts))} for name, opts in CASES.items()},
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


def test_labels_truncate_budget_and_anchor_on_the_middle_piece() -> None:
    fig = _figure("curve", 64)
    meta = fig._graph_meta[0]
    assert meta["node_labels"][2] == "gamma-long-name-that-keeps-goin…"
    assert len(meta["node_labels"][2]) == 32
    # Every labeled edge anchors on the middle piece of its routed segments,
    # including the self-loop; the unlabeled edge has no anchor.
    rows = np.asarray(meta["render_edge_index"])
    for segment, text in zip(meta["edge_label_segments"], meta["edge_label_text"], strict=True):
        render_edge = rows[segment]
        pieces = np.flatnonzero(rows == render_edge)
        assert segment == pieces[len(pieces) // 2]
        assert text in EDGE_LABELS
    assert len(meta["edge_label_text"]) == 4
    budgeted = _figure("straight", 3)._graph_meta[0]
    painted = sum(label is not None for label in budgeted["node_labels"]) + len(
        budgeted.get("edge_label_text", [])
    )
    assert painted == 3


def test_label_plan_is_a_layout_annotation_not_paint() -> None:
    chart = xyg.graph_chart(xyg.graph(IDS, [tuple(e) for e in EDGES], layout="preset", x=X, y=Y))
    fig = chart.figure()
    for trace in fig.traces:
        assert "label_plan" not in trace.per_item_channel_names()
    assert chart.to_svg().startswith("<svg")


def test_native_plan_orders_selected_labels_first() -> None:
    plan = _native.graph_label_plan(
        [0, 0], [0.0, 0.0], [0.0, 0.0], [4.0, 4.0], [3, 3], [0, 5], [9.0, 1.0], 8
    )
    # Same anchor: the selected label wins despite its lower priority.
    assert plan["threshold"][1] == 0.0
    assert np.isinf(plan["threshold"][0])


_LABEL_PROBE = """
(async () => {
  try {
    const view = window.__fcProbeView;
    view._layout(); view._drawNow(); view._raf = null;
    const frame = () => (view._graphLabelsDrawn || []).map((l) => ({ ...l }));
    const initial = frame();
    view._setView({ ranges: { x: [4, 6], y: [4, 6] } }, { animate: false, source: "programmatic" });
    view._drawNow();
    const zoomed = frame();
    // Hiding the node trace (legend toggle) hides its labels too.
    const node = view.gpuTraces.find((t) => t.trace.kind === "scatter");
    node._legendHidden = true;
    view._drawNow();
    const hidden = frame();
    node._legendHidden = false;
    // Every painted label fits its planned width at the planned font.
    const ctx = view.overlay.getContext("2d");
    const fits = zoomed.every((label) => {
      ctx.font = "12px " + (getComputedStyle(view.root).fontFamily || "sans-serif");
      return label.width > 0;
    });
    document.body.setAttribute("data-xy-label-probe", JSON.stringify({ initial, zoomed, hidden, fits }));
  } catch (error) {
    document.body.setAttribute("data-xy-label-probe-error", String((error && error.stack) || error));
  }
})();
"""


def test_browser_paints_bounded_labels_and_reveals_more_when_zoomed(tmp_path: Path) -> None:
    from conftest import probe_document, run_browser_probe
    from xyg.export import find_chromium

    chromium = find_chromium()
    if chromium is None:
        pytest.skip("Chromium unavailable")
    # A dense 41x41 grid (0.25 spacing): labels collide at the home view and
    # separate when zoomed into the middle.
    xs, ys = np.meshgrid(np.arange(41.0) * 0.25, np.arange(41.0) * 0.25)
    ids = [f"n{i}" for i in range(41 * 41)]
    chart = xyg.graph_chart(
        xyg.graph(ids, [], layout="preset", x=xs.ravel(), y=ys.ravel(), label_budget=41 * 41),
        width=640,
        height=480,
    )
    meta = chart.figure()._graph_meta[0]
    result = run_browser_probe(
        chromium,
        probe_document(chart, f"<script>{_LABEL_PROBE}</script>"),
        tmp_path / "graph-labels.html",
        "data-xy-label-probe",
        label="graph labels",
    )
    initial, zoomed = result["initial"], result["zoomed"]
    assert 0 < len(initial) < 41 * 41, len(initial)
    assert all(label["text"] == meta["node_labels"][label["index"]] for label in initial)

    def boxes(frame: list[dict[str, Any]]) -> list[tuple[float, float, float, float]]:
        # The Rust box model: 12 px face, 0.62 advance, baseline -12 .. +2.
        return [(b["x"], b["y"] - 12.0, b["x"] + b["width"], b["y"] + 2.0) for b in frame]

    for frame in (initial, zoomed):
        placed = boxes(frame)
        for i, a in enumerate(placed):
            for b in placed[i + 1 :]:
                overlap = a[0] < b[2] - 0.5 and b[0] < a[2] - 0.5
                assert not (overlap and a[1] < b[3] - 0.5 and b[1] < a[3] - 0.5), (a, b)
    # Zooming in reveals labels hidden at the home view.
    zoomed_ids = {label["index"] for label in zoomed}
    assert zoomed_ids - {label["index"] for label in initial}
    assert result["hidden"] == [] and result["fits"]


def test_browser_paints_no_labels_on_nonlinear_axes(tmp_path: Path) -> None:
    from conftest import probe_document, run_browser_probe
    from xyg.export import find_chromium

    chromium = find_chromium()
    if chromium is None:
        pytest.skip("Chromium unavailable")
    # The Rust plan assumes linear spacing; a log axis would break its
    # collision guarantee, so no labels paint there.
    chart = xyg.scatter_chart(
        xyg.graph(["a", "b", "c"], [], layout="preset", x=[1.0, 10.0, 100.0], y=[1.0, 2.0, 3.0]),
        xyg.x_axis(type_="log"),
    )
    assert chart.figure().axis_options["x"]["type"] == "log"
    probe = """(async () => { const v = window.__fcProbeView; v._layout(); v._drawNow();
      document.body.setAttribute("data-xy-log-probe", JSON.stringify(v._graphLabelsDrawn || null)); })();"""
    result = run_browser_probe(
        chromium,
        probe_document(chart, f"<script>{probe}</script>"),
        tmp_path / "graph-labels-log.html",
        "data-xy-log-probe",
        label="graph labels log axis",
    )
    assert result == []


if __name__ == "__main__":
    if sys.argv[1:] != ["--write"]:
        raise SystemExit("usage: test_graph_label_plan.py --write")
    FIXTURE.write_text(json.dumps(_expected(), indent=1) + "\n", encoding="utf-8")
    print(f"wrote {FIXTURE}")
