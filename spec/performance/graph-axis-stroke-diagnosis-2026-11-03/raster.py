"""Inspect actual Rust display-list spine records, without changing geometry."""

import json
import re
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import xyg
from xyg import _native

out = Path(sys.argv[1])
result = {}
for theme in ("light", "dark"):
    scene = xyg.decode_graphforge_document((out / "baseline" / f"{theme}.xygf").read_bytes())
    svg = ET.parse(out / "baseline" / f"{theme}.svg").getroot()
    plot = next(e for e in svg if e.get("data-xy-chrome") == "plot-background")
    left, top = float(plot.get("x")), float(plot.get("y"))
    right = left + float(plot.get("width"))
    bottom = top + float(plot.get("height"))
    axes = next(e for e in svg if e.get("data-xy-chrome") == "axes")
    spines = []
    for e in axes:
        if not e.tag.endswith("}line"):
            continue
        points = [float(e.get(k)) for k in ("x1", "y1", "x2", "y2")]
        if points in ([left, bottom, right, bottom], [left, top, left, bottom]):
            spines.append((points, float(e.get("stroke-width")), e.get("stroke")))
    assert len(spines) == 2
    for scale in (1, 2):
        commands = _native.scene_raster_commands(scene.scene["bytes"], scale=scale)
        (out / f"{theme}.scale{scale}.raster.bin").write_bytes(commands)
        records = []
        for points, width, color in spines:
            components = [float(v) for v in re.findall(r"[0-9.]+", color)]
            rgba = bytes([*(int(v) for v in components[:3]), round(components[3] * 255)])
            # OP_STROKE, two points, width, RGBA8, open, no dash, round cap.
            record = (
                struct.pack("<BI5f", 3, 2, *(v * scale for v in points), width * scale)
                + rgba
                + struct.pack("<BIB", 0, 0, 1)
            )
            offset = commands.find(record)
            assert offset >= 0, (theme, scale, points)
            records.append(
                {
                    "byte_offset": offset,
                    "css_points": points,
                    "physical_points": [v * scale for v in points],
                    "physical_width": width * scale,
                    "rgba": list(rgba),
                    "cap": "round (1)",
                    "raw_record_hex": record.hex(),
                }
            )
        result[f"{theme}.scale{scale}"] = records
(out / "raster.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
