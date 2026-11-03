"""Real single-primary-axis Scene; no supplied layout/plot/positions."""

from pathlib import Path

import xyg
from xyg import _native

out = Path(__file__).resolve().parent
chart = xyg.line_chart(
    xyg.line([0, 1], [0.2, 0.8], color="#ff0000"),
    xyg.x_axis(domain=(0, 1)),
    xyg.y_axis(domain=(0, 1)),
    xyg.legend(show=False),
    xyg.theme(background="#030712", plot_background="#111827"),
    width=320,
    height=240,
)
scene = chart.figure().to_scene()
(out / "slot.scene").write_bytes(scene)
(out / "slot.svg").write_bytes(_native.scene_static_export(scene, "svg"))
print("Real Rust Scene produced; only subsequent authored slot CSS changes geometry.")

# Native finite subpixel width that CSS used boxes quantize to 1/64 CSS px.
precision = (
    xyg.line_chart(
        xyg.line([0, 1], [0.2, 0.8], color="#ff0000"),
        xyg.x_axis(domain=(0, 1), style={"axis_width": 0.3, "tick_length": 0}),
        xyg.y_axis(domain=(0, 1), style={"axis_width": 0.3, "tick_length": 0}),
        xyg.legend(show=False),
        xyg.theme(background="#030712", plot_background="#111827"),
        width=320,
        height=240,
    )
    .figure()
    .to_scene()
)
(out / "precision.scene").write_bytes(precision)
(out / "precision.svg").write_bytes(_native.scene_static_export(precision, "svg"))
