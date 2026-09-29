"""Border-aware graph edge ends and screen-space arrowheads (#33).

Rust routes each edge with per-endpoint node border radii and outline shapes
(``graph_edge_route_ends``). The static Scene trims each edge and adds its
arrowhead in pixel space; the WebGL segment shader applies the same rule every
frame, so arrow tips meet circle, square, and diamond node outlines at every
zoom in both the export and the live chart.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
import pytest

import xyg
from xyg import _native

SHAPES = {"circle": 0, "square": 1, "diamond": 2}
EDGE = "#ff0000"
NODE = "#00aa00"
SIZE = 16.0  # px diameter -> 8 px radius


def _border(shape: str, radius: float, ux: float, uy: float) -> float:
    ax, ay = abs(ux), abs(uy)
    if shape == "square":
        return radius / max(ax, ay)
    if shape == "diamond":
        return math.sqrt(2.0) * radius / (ax + ay)
    return radius


def _chart(symbol: str, *, x=(0.0, 4.0), y=(0.0, 3.0)) -> xyg.Chart:
    return xyg.graph_chart(
        xyg.graph(
            ["a", "b"],
            [("a", "b")],
            layout="preset",
            x=list(x),
            y=list(y),
            size=SIZE,
            symbol=symbol,
            color=NODE,
            edge_color=EDGE,
        ),
        width=640,
        height=480,
    )


def test_route_ends_report_centers_radii_shapes_and_heads() -> None:
    x = np.array([0.0, 4.0, 2.0])
    y = np.array([0.0, 0.0, 3.0])
    sources = np.array([0, 2], dtype=np.uint64)
    targets = np.array([1, 2], dtype=np.uint64)
    x0, y0, *_, index, ends = _native.graph_edge_route_ends(
        x,
        y,
        sources,
        targets,
        node_radius_px=np.array([4.0, 6.0, 3.0]),
        node_symbol=np.array([0, 1, 2], dtype=np.uint8),
    )
    assert index.tolist() == [0, 1, 1, 1]
    assert ends.shape == (4, 7)
    # a -> b: source/target centers relative to the piece start, radii, and
    # head + terminal + square target / circle source.
    assert (x0[0] + ends[0, 0], y0[0] + ends[0, 1]) == (0.0, 0.0)
    assert (x0[0] + ends[0, 3], y0[0] + ends[0, 4]) == (4.0, 0.0)
    assert ends[0, [2, 5, 6]].tolist() == [4.0, 6.0, float(0x40 | 0x20 | 1)]
    # Self-loop on the diamond: every side names that node; the last side is
    # terminal.
    loop_flags = [int(flag) for flag in ends[1:, 6]]
    assert loop_flags == [0x40 | (2 << 2) | 2] * 2 + [0x40 | 0x20 | (2 << 2) | 2]
    undirected = _native.graph_edge_route_ends(x, y, sources, targets, directed=False)[5]
    assert not any(int(flag) & 0x40 for flag in undirected[:, 6])


def _svg_heads(svg: str) -> list[tuple[float, float]]:
    return [
        (float(a), float(b))
        for a, b in re.findall(
            r'<path d="M ([\d.]+) ([\d.]+) L [\d. L]+Z" fill="rgb\(255,0,0\)"', svg
        )
    ]


def test_offset_parallel_edges_tip_on_the_circle_outline() -> None:
    # Three parallel/reciprocal edges between large nodes: their shafts are
    # offset from the centers, so a center-radius trim would stop short.
    svg = xyg.graph_chart(
        xyg.graph(
            ["a", "b"],
            [("a", "b"), ("a", "b"), ("b", "a")],
            layout="preset",
            # A 2-D layout keeps the 0.08-unit parallel offsets to a few px,
            # inside the 20 px radius (collinear nodes would make the offsets
            # set the y extent).
            x=[0.0, 4.0],
            y=[0.0, 3.0],
            size=40.0,
            color=NODE,
            edge_color=EDGE,
        ),
        width=640,
        height=480,
    ).to_svg()
    centers = _node_centers(svg, "circle")
    heads = _svg_heads(svg)
    assert len(heads) == 3, svg
    for tip in heads:
        nearest = min(math.hypot(tip[0] - cx, tip[1] - cy) for cx, cy in centers)
        assert nearest == pytest.approx(20.0, abs=0.05)


def test_curved_edges_never_start_inside_large_nodes() -> None:
    svg = xyg.graph_chart(
        xyg.graph(
            ["a", "b", "c"],
            [("a", "b"), ("b", "a"), ("a", "c"), ("c", "b")],
            layout="preset",
            x=[0.0, 1.0, 0.5],
            y=[0.0, 0.0, 0.6],
            size=90.0,
            edge_curve="curve",
            color=NODE,
            edge_color=EDGE,
        ),
        width=480,
        height=360,
    ).to_svg()
    centers = _node_centers(svg, "circle")
    points = [
        (float(a), float(b))
        for poly in re.findall(r'<polyline points="([^"]+)"[^>]*stroke="rgb\(255,0,0\)"', svg)
        for a, b in (pair.split(",") for pair in poly.split())
    ]
    assert points
    for px, py in points:
        assert min(math.hypot(px - cx, py - cy) for cx, cy in centers) >= 45.0 - 0.05


@pytest.mark.parametrize("symbol", sorted(SHAPES))
def test_static_arrow_tips_touch_node_outlines(symbol: str) -> None:
    svg = _chart(symbol).to_svg()
    centers = [
        (float(a), float(b))
        for a, b in re.findall(r'data-xy-stable-id="\d+"[^>]*?cx="([\d.]+)" cy="([\d.]+)"', svg)
    ] or _node_centers(svg, symbol)
    heads = re.findall(r'<path d="M ([\d.]+) ([\d.]+) L [\d. L]+Z" fill="rgb\(255,0,0\)"', svg)
    assert len(heads) == 1, svg
    tip = tuple(float(v) for v in heads[0])
    (ax, ay), (bx, by) = centers
    length = math.hypot(bx - ax, by - ay)
    ux, uy = (bx - ax) / length, (by - ay) / length
    expected = _border(symbol, SIZE / 2, ux, uy)
    assert math.hypot(bx - tip[0], by - tip[1]) == pytest.approx(expected, abs=0.02)


def _node_centers(svg: str, symbol: str) -> list[tuple[float, float]]:
    if symbol == "circle":
        return [
            (float(a), float(b)) for a, b in re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)"', svg)
        ]
    if symbol == "square":
        rects = re.findall(
            r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" fill="rgb\(0,170,0\)"',
            svg,
        )
        return [(float(x) + float(w) / 2, float(y) + float(h) / 2) for x, y, w, h in rects]
    paths = re.findall(
        r'<path d="M ([\d.]+) ([\d.]+) L ([\d.]+) ([\d.]+) L ([\d.]+) ([\d.]+) L ([\d.]+) ([\d.]+) Z" fill="rgb\(0,170,0\)"',
        svg,
    )
    centers = []
    for values in paths:
        xs = [float(v) for v in values[0::2]]
        ys = [float(v) for v in values[1::2]]
        centers.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2))
    return centers


_PIXEL_PROBE = """
(async () => {
  try {
    const view = window.__fcProbeView;
    view._layout(); view._drawNow(); view._raf = null;
    const node = view.gpuTraces.find((t) => t.trace.id === NODE_TRACE);
    const border = (ux, uy) => {
      const ax = Math.abs(ux), ay = Math.abs(uy), r = RADIUS;
      if (SHAPE === 1) return r / Math.max(ax, ay);
      if (SHAPE === 2) return Math.SQRT2 * r / (ax + ay);
      return r;
    };
    const sample = () => {
      view._drawNow();
      const a = view._projectDataPoint(node.xAxis, node.yAxis, X0, Y0, null);
      const b = view._projectDataPoint(node.xAxis, node.yAxis, X1, Y1, null);
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
      const ux = (b[0] - a[0]) / len, uy = (b[1] - a[1]) / len;
      const t = border(ux, uy);
      // The WebGL canvas spans the plot rect; projections are chart CSS px.
      const read = (x, y) => {
        const px = new Uint8Array(4);
        const dpr = view.dpr;
        view.gl.readPixels(
          Math.round((x - view.plot.x) * dpr),
          Math.round(view.canvas.height - (y - view.plot.y) * dpr),
          1, 1, view.gl.RGBA, view.gl.UNSIGNED_BYTE, px);
        return Array.from(px);
      };
      // 6 px behind the tip and 2 px off-axis is inside a head whose tip is on
      // the outline, but empty if the head sat at the node center.
      const behind = t + 6;
      return {
        head: read(b[0] - ux * behind - uy * 2, b[1] - uy * behind + ux * 2),
        inside: read(b[0] - ux * (t - 2), b[1] - uy * (t - 2)),
      };
    };
    const initial = sample();
    view._setView({ ranges: { x: [2.5, 4.5], y: [1.5, 3.5] } }, { animate: false, source: "programmatic" });
    const zoomed = sample();
    document.body.setAttribute("data-xy-ends-probe", JSON.stringify({ initial, zoomed }));
  } catch (error) {
    document.body.setAttribute("data-xy-ends-probe-error", String((error && error.stack) || error));
  }
})();
"""


@pytest.mark.parametrize("symbol", sorted(SHAPES))
def test_browser_arrow_tips_touch_node_outlines_at_every_zoom(symbol: str, tmp_path: Path) -> None:
    from conftest import probe_document, run_browser_probe
    from xyg.export import find_chromium

    chromium = find_chromium()
    if chromium is None:
        pytest.skip("Chromium unavailable")
    chart = _chart(symbol)
    meta = chart.figure()._graph_meta[0]
    script = (
        _PIXEL_PROBE.replace("NODE_TRACE", str(meta["node_trace"]))
        .replace("RADIUS", json.dumps(SIZE / 2))
        .replace("SHAPE", str(SHAPES[symbol]))
        .replace("X0", "0.0")
        .replace("Y0", "0.0")
        .replace("X1", "4.0")
        .replace("Y1", "3.0")
    )
    result = run_browser_probe(
        chromium,
        probe_document(chart, f"<script>{script}</script>"),
        tmp_path / f"edge-ends-{symbol}.html",
        "data-xy-ends-probe",
        label=f"edge ends {symbol}",
    )
    for view_name in ("initial", "zoomed"):
        head = result[view_name]["head"]
        inside = result[view_name]["inside"]
        assert head[0] > 150 and head[1] < 100, (view_name, head)  # red arrowhead
        assert inside[1] > 120 and inside[0] < 100, (view_name, inside)  # green node


def test_edge_ends_ship_as_host_side_geometry_channel() -> None:
    chart = _chart("circle")
    fig = chart.figure()
    edges = fig.traces[fig._graph_meta[0]["edge_trace"]]
    channel = edges.style_channels["edge_ends"]
    assert channel.components == 7
    # Geometry annotation, not per-item paint: static export stays admitted.
    assert "edge_ends" not in edges.per_item_channel_names()
    assert chart.to_png()[:4] == b"\x89PNG"
