"""The composed graph home view (#910).

Graph charts used to autorange to node centers, clipping markers, halos,
labels, and compound frames at the plot edge. Rust now pads the node-center
autorange (``xyg_graph_home_domain``) so everything drawn around a node fits
the plot of the hidden-axis graph shell; hosts set it as the hidden axes'
domain, so the browser and static export share it. The visual goldens pin the
domain in both hosts (``tests/fixtures/graph_visual_goldens.json``).
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

import pytest

import xyg
from test_graph_visual_goldens import _load, chart
from xyg import _graph_static, _native

EPS = 1e-6


def _plot_rect(fig: Any) -> tuple[float, float, float, float]:
    x, y = fig.axis_options["x"]["domain"], fig.axis_options["y"]["domain"]
    left, right, top, bottom = _native.scene_plot_layout(
        viewport=(float(fig.width), float(fig.height)),
        x_axis=(0, x[0], x[1], 1.0, False),
        y_axis=(0, y[0], y[1], 1.0, False),
        title=str(fig.title or ""),
        x_label="",
        y_label="",
        x_format=None,
        y_format=None,
        padding=None,
        colorbar_side=None,
    )
    return left, top, fig.width - left - right, fig.height - top - bottom


def _boxes(fig: Any) -> list[tuple[str, float, float, float, float]]:
    """Every drawn extent as (what, left, top, right, bottom) in plot px."""
    planes = _graph_static.composed_graph_planes(copy.deepcopy(fig))
    assert planes is not None
    (x0, x1), (y0, y1) = fig.axis_options["x"]["domain"], fig.axis_options["y"]["domain"]
    _, _, w, h = _plot_rect(fig)

    def px(x: float, y: float) -> tuple[float, float]:
        return (x - x0) / (x1 - x0) * w, (y1 - y) / (y1 - y0) * h

    out = []
    for i in range(len(planes["x"])):
        # Diamonds (2) and thin diamonds (14) reach sqrt(2) further along
        # the axes, like every renderer draws them.
        scale = math.sqrt(2.0) if int(planes["symbol"][i]) in (2, 14) else 1.0
        r = 0.5 * planes["diameter"][i] * scale + 0.5 * planes["stroke_width"][i]
        if "halo" in planes and planes["halo"][i][3] > 0:
            r = max(r, 0.5 * planes["halo_diameter"][i])
        cx, cy = px(planes["x"][i], planes["y"][i])
        out.append(("node", cx - r, cy - r, cx + r, cy + r))
        if "frames" in planes and planes["frames"][i][8] > 0:
            row = planes["frames"][i]
            pad = row[9] + 0.5 * row[8]
            fx0, fy0 = px(planes["x"][i] + row[0], planes["y"][i] + row[3])
            fx1, fy1 = px(planes["x"][i] + row[1], planes["y"][i] + row[2])
            out.append(("frame", fx0 - pad, fy0 - pad, fx1 + pad, fy1 + pad))
    scale = min(w / (x1 - x0), h / (y1 - y0))
    if "node_label_plan" in planes:
        for i, (text, row) in enumerate(
            zip(planes["node_labels"], planes["node_label_plan"], strict=True)
        ):
            if text is None or not 0.0 <= row[0] <= scale:
                continue
            ax, ay = px(planes["x"][i], planes["y"][i])
            left, baseline = ax + row[1], ay + row[2]
            out.append(("label", left, baseline - row[4], left + row[3], baseline + 2.0))
    return out


@pytest.mark.parametrize("name", ["ordinary", "dense", "compound", "selected", "dark"])
def test_everything_drawn_around_a_node_fits_the_home_view(name: str) -> None:
    fig = chart(_load()["cases"][name]).figure()
    _, _, w, h = _plot_rect(fig)
    for what, left, top, right, bottom in _boxes(fig):
        assert left >= -EPS and top >= -EPS, (name, what, left, top)
        assert right <= w + EPS and bottom <= h + EPS, (name, what, right - w, bottom - h)


def test_home_view_contains_the_autorange_and_authored_axes_keep_it() -> None:
    case = _load()["cases"]["selected"]
    fig = chart(case).figure()
    plain = copy.deepcopy(fig)
    plain.axis_options["x"]["domain"] = plain.axis_options["y"]["domain"] = None
    (bx0, bx1), (by0, by1) = plain.x_range(), plain.y_range()
    (x0, x1), (y0, y1) = fig.axis_options["x"]["domain"], fig.axis_options["y"]["domain"]
    assert x0 <= bx0 and x1 >= bx1 and y0 <= by0 and y1 >= by1
    assert (x0, x1, y0, y1) != (bx0, bx1, by0, by1)
    nodes, edges = case["nodes"], case["edges"]
    authored = xyg.graph_chart(
        xyg.graph(nodes, edges, **case["options"]), xyg.x_axis(show=False, grid=True)
    ).figure()
    assert authored.axis_options["x"]["domain"] is None


_PROBE = """
(async () => {
  try {
    const view = window.__fcProbeView;
    view._layout(); view._drawNow(); view._raf = null;
    const node = view.gpuTraces.find((t) => t.trace.id === __NODE_TRACE__);
    const points = __POINTS__.map(([x, y]) => view._projectDataPoint(node.xAxis, node.yAxis, x, y, null));
    document.body.setAttribute("data-xy-home-probe", JSON.stringify({
      plot: view.plot, points, labels: view._graphLabelsDrawn || [] }));
  } catch (error) {
    document.body.setAttribute("data-xy-home-probe-error", String((error && error.stack) || error));
  }
})();
"""


def test_browser_home_view_keeps_nodes_and_labels_in_the_plot(tmp_path: Path) -> None:
    from conftest import probe_document, run_browser_probe
    from xyg.export import find_chromium

    chromium = find_chromium()
    if chromium is None:
        pytest.skip("Chromium unavailable")
    case = _load()["cases"]["ordinary"]
    view = chart(case)
    fig = view.figure()
    meta = fig._graph_meta[0]
    node = fig.traces[meta["node_trace"]]
    points = [[float(x), float(y)] for x, y in zip(node.x.values, node.y.values, strict=True)]
    script = _PROBE.replace("__NODE_TRACE__", str(meta["node_trace"])).replace(
        "__POINTS__", json.dumps(points)
    )
    result = run_browser_probe(
        chromium,
        probe_document(view, f"<script>{script}</script>"),
        tmp_path / "graph-home.html",
        "data-xy-home-probe",
        label="graph home view",
    )
    plot = result["plot"]
    x_lo, y_lo = plot["x"], plot["y"]
    x_hi, y_hi = x_lo + plot["w"], y_lo + plot["h"]
    radius = 0.5 * float(node.size_ch.constant or 8.0) + 1.0
    for px, py, *_ in result["points"]:
        assert x_lo + radius - 0.5 <= px <= x_hi - radius + 0.5, (px, plot)
        assert y_lo + radius - 0.5 <= py <= y_hi - radius + 0.5, (py, plot)
    # Every label the browser paints at the home view lies inside the plot
    # (the Rust box model: baseline -12 .. +2).
    assert result["labels"], "no labels painted"
    for label in result["labels"]:
        assert label["x"] >= x_lo - 0.5 and label["x"] + label["width"] <= x_hi + 0.5, (label, plot)
        assert label["y"] - 12.0 >= y_lo - 0.5 and label["y"] + 2.0 <= y_hi + 0.5, (label, plot)
    assert {label["text"] for label in result["labels"]} >= {"report", "ingest"}
