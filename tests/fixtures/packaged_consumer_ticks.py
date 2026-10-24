"""Export hosted tick cases using only the selected installed Python package."""

import sys
from pathlib import Path

import xyg

destination = Path(sys.argv[1])
destination.mkdir()
secondary = xyg.chart(
    xyg.line([1, 2, 3], [1, 2, 3], color="#dc2626"),
    xyg.line([1, 2, 3], [100, 200, 300], y_axis="y2", color="#2563eb"),
    xyg.x_axis(domain=(0, 4)),
    xyg.y_axis(domain=(0, 4)),
    xyg.y_axis(id="y2", domain=(0, 400), side="right"),
    width=480,
    height=360,
)
polar = xyg.chart(
    xyg.line([0, 90, 180, 270, 360], [0.5, 0.8, 0.6, 0.9, 0.5], color="#dc2626"),
    xyg.theta_axis(unit="degrees", domain=(0, 360)),
    xyg.r_axis(domain=(0, 1)),
    coords="polar",
    width=480,
    height=360,
)
secondary.to_html(destination / "secondary.html", wasm_ticks=True)
polar.to_html(destination / "polar.html", wasm_ticks=True)
# Valid HTML/Worker framing: only the module bytes differ, reaching the real
# WebAssembly.compile rejection rather than an unavailable-bootstrap branch.
(destination / "corrupt.wasm").write_bytes(bytes([0, 1, 2, 3]))
for name in ("missing", "corrupt"):
    secondary.to_html(
        destination / f"{name}.html",
        wasm_ticks={"worker_url": "./wasm-worker.js", "wasm": f"./{name}.wasm"},
    )
