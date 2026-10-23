"""Stock Streamlit consumer of XYG's public composition and export APIs.

Run: uv run --group consumers streamlit run examples/streamlit/app.py
The iframe supports browser gestures; it does not return selection to Python.
"""

from __future__ import annotations

from itertools import pairwise

import streamlit as st
import streamlit.components.v1 as components

import xyg

KINDS = ("scatter", "line", "bar", "graph")


def build_chart(kind: str, count: int = 8) -> xyg.Chart:
    """Deterministic small charts; canonical decisions remain in Rust."""
    if kind not in KINDS or count not in (8, 16, 24, 32):
        raise ValueError("choose a shipped example kind and 8, 16, 24, or 32 rows")
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
    count = st.select_slider("Rows", options=(8, 16, 24, 32), value=8)
    chart = build_chart(kind, count)
    st.caption(f"{kind} · {count} rows")
    components.html(chart.to_html(), height=400, scrolling=False)
    st.download_button("Download SVG", chart.to_svg(), file_name="chart.svg", mime="image/svg+xml")
    st.download_button("Download PNG", chart.to_png(), file_name="chart.png", mime="image/png")


if __name__ == "__main__":
    main()
