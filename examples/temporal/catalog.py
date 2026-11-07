"""Six ordinary public compositions over exact UTC microseconds.

Run: uv run python examples/temporal/catalog.py
"""

from pathlib import Path

import xyg

output = Path("target/temporal-catalog")
output.mkdir(parents=True, exist_ok=True)
for family in ("event", "interval", "gantt", "line", "bar", "scatter"):
    chart = xyg.temporal_chart(
        family,
        [(-1, 2, 1, 42), (3, None, 2, 2**64 - 1)],
        domain=(-5, 10),
        timezone="UTC",
        title=family,
    )
    chart.to_html(output / f"{family}.html")
    chart.to_svg(output / f"{family}.svg")
    chart.to_png(str(output / f"{family}.png"))
