"""Stock Streamlit consumer of XYG's public composition and export APIs.

Run: uv run --group consumers streamlit run examples/streamlit/app.py
The iframe supports browser gestures; it does not return selection to Python.
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import xyg

GRAPHFORGE_KINDS = ("graphforge-property", "graphforge-pagerank")
KINDS = ("scatter", "line", "bar", "graph", *GRAPHFORGE_KINDS)
RESULTS = Path(__file__).resolve().parents[2] / "tests/fixtures/graphforge/results"


def build_graphforge_composition(kind: str) -> xyg.GraphForgeComposition:
    """Replay repository Core fixtures; XYG never computes PageRank itself."""
    if kind not in GRAPHFORGE_KINDS:
        raise ValueError("choose graphforge-property or graphforge-pagerank")
    manifest = json.loads((RESULTS / "manifest.json").read_text())
    base = manifest["bases"]["property" if kind == "graphforge-property" else "cyclic"]
    source = {
        "tables": [(RESULTS / f"{base[key]}.arrow").read_bytes() for key in ("nodes", "edges")],
        "generation": base["generation"],
    }
    if kind == "graphforge-property":
        # Deliberately omit layers: exercise the public property-graph defaults.
        return xyg.compose_graphforge(base=source)
    return xyg.compose_graphforge(
        base=source,
        layers=[
            {
                "result": (RESULTS / "pagerank.arrow").read_bytes(),
                "intent": "graph",
                "result_id": "pagerank",
                "generation": base["generation"],
            }
        ],
    )


def build_chart(kind: str, count: int = 8) -> xyg.Chart:
    """Deterministic small charts; canonical decisions remain in Rust."""
    if kind not in KINDS or count not in (8, 16, 24, 32):
        raise ValueError("choose a shipped example kind and 8, 16, 24, or 32 rows")
    if kind in GRAPHFORGE_KINDS:
        return xyg.graphforge_chart(
            build_graphforge_composition(kind), title=kind, width=720, height=360
        )
    x = list(range(count))
    y = [(i * 7) % 13 for i in x]
    if kind == "graph":
        nodes = [f"n{i}" for i in x]
        mark = xyg.graph(nodes, list(pairwise(nodes)), layout="circle")
    else:
        mark = getattr(xyg, kind)(x, y, color="#dc2626")
    return xyg.chart(mark, title=f"{kind} · {count} rows", width=720, height=360)


def main() -> None:
    st.set_page_config(page_title="XYG · Streamlit")
    st.title("XYG in Streamlit")
    st.caption("Pan, zoom and hover in the chart. Selection stays in the browser.")
    kind = st.selectbox("Chart", KINDS)
    count = (
        8
        if kind in GRAPHFORGE_KINDS
        else st.select_slider("Rows", options=(8, 16, 24, 32), value=8)
    )
    chart = build_chart(kind, count)
    st.caption(kind if kind in GRAPHFORGE_KINDS else f"{kind} · {count} rows")
    components.html(chart.to_html(), height=400, scrolling=False)
    svg, png = chart.to_svg(), chart.to_png()
    if kind in GRAPHFORGE_KINDS:
        with st.expander("Static exports"):
            st.image(png, caption="Native PNG export")
            st.image(svg, caption="Native SVG export")
    st.download_button(
        "Download SVG", svg, file_name="chart.svg", mime="image/svg+xml", on_click="ignore"
    )
    st.download_button(
        "Download PNG", png, file_name="chart.png", mime="image/png", on_click="ignore"
    )


if __name__ == "__main__":
    main()
