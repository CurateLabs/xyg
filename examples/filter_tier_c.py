"""Bounded shared-source filtering through the public composition API.

Run: uv run python examples/filter_tier_c.py
Browser binding: examples/vanilla-ts/filter-linked.ts. Massive qualification is open.
"""

import xyg

columns = {"a": [0.0, 0.25, 0.5, 1.0], "b": [1.0, 0.5, 0.0, -1.0], "c": [-1.0, 0.0, 0.5, 1.0]}
charts = [
    xyg.scatter_chart(xyg.scatter(x=columns[x], y=columns[y], density=True), title=f"{x} vs {y}")
    for x, y in [("a", "b"), ("b", "c"), ("c", "a")]
]
views = [
    dict(id=i + 1, x=x, y=y, width=4, height=4, x_range=[-2.0, 2.0], y_range=[-2.0, 2.0])
    for i, (x, y) in enumerate([("a", "b"), ("b", "c"), ("c", "a")])
]
with charts[0].filter_session(columns, source_id=112, epoch=1, first_row=1 << 53) as session:
    session.configure_density(dict(id=1, dimension="a", cuts=[0.0, 1.0]), views)
    session.range(0.1, 0.6, exact=True)  # explicit boundary work, never silent snapping
    frame = session.paint(exact=True)
    print("selected", frame["selected_count"], "tier", frame["tier"], "rows", frame["rows_read"])
    print("exact selected planes", [v["selected"] for v in frame["density"]])
    session.begin_edit()
    session.configure_density(dict(id=2, dimension="b", cuts=[-1.0, 0.0, 1.0]), views)
    session.range(0.0, 0.5, exact=True)  # A-range AND B-range, shared canonical rows
    print("composed selected", session.paint(exact=True)["selected_count"])
    session.cancel_edit()
    print("restored selected", session.paint(exact=True)["selected_count"])
