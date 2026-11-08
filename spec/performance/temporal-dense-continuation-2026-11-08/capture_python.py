"""Public Python composition bytes against the same authored Node/browser inputs."""

import hashlib
import json
import sys
from pathlib import Path

import xyg

output = Path(sys.argv[1])
output.mkdir()
captures = []
for kind in ["event", "interval", "gantt", "line", "bar", "scatter"]:
    chart = xyg.temporal_chart(
        kind,
        [(i, i + 1, 0, 2**63 + i) for i in range(10000)],
        domain=(0, 10000),
        timezone="UTC",
        dense=True,
        width=900,
        height=420,
    )
    metadata = chart.temporal_metadata()
    items = {
        "metadata": metadata,
        "members": chart.temporal_members(metadata, 0),
        "scene": chart.figure().to_scene(),
        "svg": chart.to_svg().encode(),
        "png": chart.to_png(),
    }
    if kind == "line":
        items["supports"] = chart.temporal_supports(metadata, 0)
    for name, value in items.items():
        path = output / f"{kind}.{name}"
        path.write_bytes(value)
        captures.append(
            {
                "kind": kind,
                "type": name,
                "path": path.name,
                "bytes": len(value),
                "sha256": hashlib.sha256(value).hexdigest(),
            }
        )
    chart.temporal_dispose()
(output / "captures.json").write_text(json.dumps(captures, indent=2) + "\n")
print(json.dumps(captures, indent=2))
