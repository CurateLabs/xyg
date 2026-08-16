"""Python force-directed org graph — labels, node/edge properties, selection panel.

Run from the repo root:

    uv run python demo/python_graph_demo.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from xy._figure import Figure
from write_graph_page import write_graph_page

ROOT = Path(__file__).resolve().parent
DATA = json.loads((ROOT / "org_graph_data.json").read_text(encoding="utf-8"))

HIDDEN_AXIS = {
    "axis_width": 0.0,
    "axis_color": "#00000000",
    "tick_length": 0.0,
    "tick_width": 0.0,
    "grid_opacity": 0.0,
    "tick_label_color": "#00000000",
    "label_color": "#00000000",
}


def build_figure() -> tuple[Figure, dict]:
    nodes = DATA["nodes"]
    edges = DATA["edges"]
    team_colors = DATA["team_colors"]
    relation_colors = DATA["relation_colors"]

    node_ids = [n["id"] for n in nodes]
    edge_pairs = [(e["source"], e["target"]) for e in edges]
    node_colors = [team_colors[n["team"]] for n in nodes]
    node_sizes = [float(n["weight"]) for n in nodes]
    edge_colors = [relation_colors[e["relation"]] for e in edges]

    fig = Figure(
        width=900,
        height=640,
        title=None,
        padding=(28, 28, 28, 28),
    )
    fig.graph(
        node_ids,
        edge_pairs,
        layout=DATA["layout"],
        seed=DATA["seed"],
        iterations=DATA["iterations"],
        directed=True,
        color=node_colors,
        size=node_sizes,
        edge_color=edge_colors,
        edge_width=3.2,
        opacity=1.0,
        name="org",
    )
    # White halo so nodes read on pale edges; match JS size encoding range.
    fig.traces[-1].style["stroke"] = "#ffffff"
    fig.traces[-1].style["stroke_width"] = 2.4
    fig.traces[-1].style["opacity"] = 1.0
    if fig.traces[-1].size_ch is not None:
        fig.traces[-1].size_ch.range_px = (10.0, 24.0)
    fig.traces[-2].style["opacity"] = 0.9

    fig.traces[-1].tooltip_rows = [
        {
            "label": n["label"],
            "id": n["id"],
            "role": n["role"],
            "team": n["team"],
            "weight": n["weight"],
        }
        for n in nodes
    ]
    fig.traces[-2].tooltip_rows = [
        {
            "label": f"{e['source']} → {e['target']}",
            "source": e["source"],
            "target": e["target"],
            "relation": e["relation"],
            "weight": e["weight"],
        }
        for e in edges
    ]

    xs = np.asarray(fig.traces[-1].x.values, dtype=np.float64)
    ys = np.asarray(fig.traces[-1].y.values, dtype=np.float64)
    cx = float((xs.min() + xs.max()) * 0.5)
    cy = float((ys.min() + ys.max()) * 0.5)
    radius = float(max(xs.max() - xs.min(), ys.max() - ys.min()) * 0.5 * 1.28)
    domain = (cx - radius, cx + radius)
    fig.set_axis("x", domain=domain, style=dict(HIDDEN_AXIS))
    fig.set_axis("y", domain=domain, style=dict(HIDDEN_AXIS))

    for i, n in enumerate(nodes):
        fig.text(
            float(xs[i]),
            float(ys[i]),
            n["label"],
            dx=12.0,
            dy=0.0,
            anchor="start",
            color="#0f172a",
            style={"font_size": 13, "font_weight": 600},
        )

    fig.tooltip = {
        "title": "{label}",
        "fields": ["role", "team", "weight", "source", "target", "relation"],
        "labels": {
            "role": "Role",
            "team": "Team",
            "weight": "Weight",
            "source": "From",
            "target": "To",
            "relation": "Relation",
        },
    }
    fig.set_interaction(hover=True, click=True)
    fig.show_legend = False
    return fig, {
        "team_colors": team_colors,
        "relation_colors": relation_colors,
    }


def main() -> None:
    fig, meta = build_figure()
    spec, blob = fig.build_payload()
    out = ROOT / "python_graph_demo.html"
    write_graph_page(
        path=out,
        title=DATA["title"] + " (Python)",
        host="Python host",
        spec=spec,
        blob=bytes(blob),
        meta=meta,
    )
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
