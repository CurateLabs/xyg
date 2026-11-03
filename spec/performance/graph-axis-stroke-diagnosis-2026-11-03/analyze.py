"""Diagnostic full-image counts and raw adjacent pixels; no acceptance changes."""

from __future__ import annotations

import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "tests"))
from test_graph_visual_goldens import _rgb  # noqa: E402

OUT = Path(sys.argv[1])
CAPTURES = OUT / sys.argv[2]
dom = json.loads((CAPTURES / "dom.json").read_text())
result = {
    "purpose": "DIAGNOSTIC ONLY; full product gate remains unchanged and fails",
    "limits": {"mean_exclusive": 3.5, "fraction_over_96_exclusive": 0.01},
    "captures": {},
}


def rgb(path: Path) -> np.ndarray:
    return _rgb(path.read_bytes()).astype(np.int16)


def counts(diff: np.ndarray) -> dict:
    bad = diff > 96
    rows = bad.sum(axis=1)
    columns = bad.sum(axis=0)
    return {
        "mean_max_channel_difference": float(diff.mean()),
        "fraction_over_96": float(bad.mean()),
        "pixels_over_96": int(bad.sum()),
        "shape": list(diff.shape),
        "top_rows": [
            {"y": int(i), "count": int(rows[i])} for i in np.argsort(-rows, kind="stable")[:16]
        ],
        "top_columns": [
            {"x": int(i), "count": int(columns[i])}
            for i in np.argsort(-columns, kind="stable")[:16]
        ],
    }


for key, observation in dom["captures"].items():
    theme, dpr_string = key.split(".dpr")
    dpr = int(dpr_string)
    images = {
        "native": rgb(CAPTURES / f"{key}.canonical.png"),
        "wasm": rgb(CAPTURES / f"{key}.wasm.png"),
        "canonical_svg_browser": rgb(CAPTURES / f"{key}.canonical-svg-browser.png"),
    }
    assert all(a.shape == (420 * dpr, 640 * dpr, 3) for a in images.values())
    diff = np.abs(images["native"] - images["wasm"]).max(axis=2)
    svg_diff = np.abs(images["native"] - images["canonical_svg_browser"]).max(axis=2)
    samples = {}
    samples["bottom_adjacent_rows_at_css_x300"] = [
        {
            "physical_pixel": [300 * dpr, y],
            "css_pixel_center": [(300 * dpr + 0.5) / dpr, (y + 0.5) / dpr],
            **{name: image[y, 300 * dpr].tolist() for name, image in images.items()},
        }
        for y in range(376 * dpr - 4, 376 * dpr + 4)
    ]
    samples["left_adjacent_columns_at_css_y200"] = [
        {
            "physical_pixel": [x, 200 * dpr],
            "css_pixel_center": [(x + 0.5) / dpr, (200 * dpr + 0.5) / dpr],
            **{name: image[200 * dpr, x].tolist() for name, image in images.items()},
        }
        for x in range(52 * dpr - 4, 52 * dpr + 4)
    ]
    # These observations identify error concentration only. They are never
    # excluded from a comparison, used as masks, or used to declare a pass.
    diagnostic_bands = {}
    for name, selector in {
        "bottom_adjacent_rows": (slice(375 * dpr, 377 * dpr), slice(None)),
        "left_adjacent_columns": (slice(None), slice(51 * dpr, 53 * dpr)),
    }.items():
        diagnostic_bands[name] = {
            "wasm_pixels_over_96": int((diff[selector] > 96).sum()),
            "canonical_svg_browser_pixels_over_96": int((svg_diff[selector] > 96).sum()),
        }
    if dpr == 1:
        baseline = OUT / "baseline" / f"{theme}.wasm.browser.png"
        previous = ROOT / "spec/performance/graph-resolved-legend-repair-2026-11-03/after"
        assert baseline.read_bytes() == (CAPTURES / f"{key}.wasm.png").read_bytes()
        assert baseline.read_bytes() == (previous / f"{theme}.wasm.browser.png").read_bytes()
        assert (OUT / "baseline" / f"{theme}.png").read_bytes() == (
            CAPTURES / f"{key}.canonical.png"
        ).read_bytes()
    svg = ET.parse(OUT / "baseline" / f"{theme}.svg").getroot()
    axes = next(e for e in svg if e.get("data-xy-chrome") == "axes")
    plot = observation["wasm"]["plot"]
    result["captures"][key] = {
        "unchanged_wasm_full_image": counts(diff),
        "canonical_svg_browser_control_full_image": counts(svg_diff),
        "diagnostic_bands_only": diagnostic_bands,
        "raw_samples": samples,
        "canonical_svg_axis_lines": [dict(e.attrib) for e in axes if e.tag.endswith("}line")],
        "plot": plot,
        "dom_axis_boxes": [e["box"] for e in observation["wasm"]["axes"]],
        "device_pixel_ratio": observation["wasm"]["devicePixelRatio"],
        "view_dpr": observation["wasm"]["viewDpr"],
        "canvas_ratios": [
            {"x": e["ratioX"], "y": e["ratioY"]} for e in observation["wasm"]["canvases"]
        ],
    }

result["artifacts"] = {
    str(p.relative_to(OUT)): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted(CAPTURES.iterdir())
    if p.is_file()
}
(OUT / "pixels.json").write_text(json.dumps(result, indent=2) + "\n")
for key, value in result["captures"].items():
    print(
        key,
        json.dumps(
            {k: v for k, v in value.items() if k not in ["raw_samples", "canonical_svg_axis_lines"]}
        ),
    )
    for name, values in value["raw_samples"].items():
        print(name, json.dumps(values))
