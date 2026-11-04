"""Produce authored canonical Scenes and ordinary live payloads for the browser seam."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import xyg
from xyg import _native

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
cases = []
for width in (0, 0.5, 1, 1.5, 2, 3):
    for sides in ("bottom-left", "top-right"):
        for paint in ("opaque", "alpha", "transparent"):
            name = f"w{width}-{sides}-{paint}"
            color = {
                "opaque": "#e5e7eb",
                "alpha": "rgba(229,231,235,0.5)",
                "transparent": "rgba(229,231,235,0)",
            }[paint]
            style = {"axis_width": width, "axis_color": color, "tick_length": 0}
            xside, yside = sides.split("-")
            marks = [xyg.line([0, 1], [0.2, 0.8], color="#ff0000")]
            axes = [
                xyg.x_axis(domain=(0, 1), side=xside, style=style),
                xyg.y_axis(domain=(0, 1), side=yside, style=style),
            ]
            if sides == "bottom-left":
                marks.append(xyg.line([0, 1], [0.8, 0.2], y_axis="y2"))
                axes.append(xyg.y_axis(id="y2", domain=(0, 1), side="right", style=style))
            chart = xyg.line_chart(
                *marks,
                *axes,
                xyg.theme(background="#030712", plot_background="#111827"),
                xyg.legend(show=False),
                width=320,
                height=240,
            )
            figure = chart.figure()
            scene = figure.to_scene()
            (out / f"{name}.scene").write_bytes(scene)
            (out / f"{name}.svg").write_bytes(_native.scene_static_export(scene, "svg"))
            spec, payload = figure.build_payload()
            (out / f"{name}.json").write_text(json.dumps(spec) + "\n")
            (out / f"{name}.bin").write_bytes(payload)
            cases.append({"name": name, "width": width, "sides": sides, "paint": paint})
# Hidden-axis authoring is distinct from transparent paint and zero width.
chart = xyg.line_chart(
    xyg.line([0, 1], [0.2, 0.8]),
    xyg.x_axis(domain=(0, 1), show=False),
    xyg.y_axis(domain=(0, 1), show=False),
    xyg.legend(show=False),
    xyg.theme(background="#030712", plot_background="#111827"),
    width=320,
    height=240,
)
figure = chart.figure()
scene = figure.to_scene()
(out / "hidden.scene").write_bytes(scene)
(out / "hidden.svg").write_bytes(_native.scene_static_export(scene, "svg"))
spec, payload = figure.build_payload()
(out / "hidden.json").write_text(json.dumps(spec) + "\n")
(out / "hidden.bin").write_bytes(payload)
cases.append({"name": "hidden", "width": None, "sides": "bottom-left", "paint": "hidden"})
(out / "cases.json").write_text(json.dumps(cases, indent=2) + "\n")
print(f"Produced {len(cases)} authored Scenes and ordinary live payloads; no layout overrides.")
