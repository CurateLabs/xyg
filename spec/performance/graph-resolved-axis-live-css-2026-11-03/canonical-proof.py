"""Independent native SVG geometry and raw adjacent-pixel audit of real captures."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent
OLD = ROOT / "spec/performance/graph-resolved-axis-repair-2026-11-03"
sys.path.insert(0, str(ROOT / "tests"))
from test_graph_visual_goldens import _rgb  # noqa: E402


def rgba(css):
    v = [float(x) for x in re.findall(r"[0-9.]+", css)]
    return [*(round(x) for x in v[:3]), round((v[3] if len(v) == 4 else 1) * 255)]


after = json.loads((OUT / "matrix/matrix.json").read_text())
before = json.loads((OLD / "after/matrix.json").read_text())
assert len(after["cases"]) == 222 and not after["failures"]
checked = ordinary = spines = sample_matches = sample_count = 0
pixels = []
for case, old in zip(after["cases"], before["cases"], strict=True):
    assert case["key"] == old["key"]
    if case["lane"] == "ordinary":
        assert case == old, case["key"]
        ordinary += 1
        continue
    assert case["axisSpec"] == old["axisSpec"]
    svg = ET.parse(OLD / "inputs" / f"{case['item']['name']}.svg").getroot()
    rect = next(e for e in svg if e.get("data-xy-chrome") == "plot-background")
    p = {
        k: float(rect.get(a))
        for k, a in zip(("x", "y", "w", "h"), ("x", "y", "width", "height"), strict=True)
    }
    assert all(abs(case["plot"][k] - v) <= 0.01 for k, v in p.items()), case["key"]
    checked += 1
    lines = [
        e
        for e in next((e for e in svg if e.get("data-xy-chrome") == "axes"), [])
        if e.tag.endswith("}line")
    ]
    visible = case["item"]["width"] and case["item"]["paint"] in ("opaque", "alpha")
    assert len(lines) == (len(case["spines"]) if visible else 0)
    browser = _rgb((OUT / "matrix" / f"{case['key']}.png").read_bytes())
    canonical = _rgb((OUT / "matrix" / f"{case['key']}.native-svg.png").read_bytes())
    assert browser.shape == canonical.shape
    for spine in case["spines"]:
        a = spine["attributes"]
        actual = [float(a[k]) for k in ("x1", "y1", "x2", "y2")]
        vertical = spine["axis"].startswith("y")
        side = spine["side"]
        if vertical:
            x = p["x"] + (p["w"] if side == "right" else 0)
            expected = [x, p["y"], x, p["y"] + p["h"]]
        else:
            y = p["y"] + (p["h"] if side == "bottom" else 0)
            expected = [p["x"], y, p["x"] + p["w"], y]
        assert all(abs(x - y) <= 0.01 for x, y in zip(actual, expected, strict=True))
        spec = case["axisSpec"][spine["axis"]]
        assert float(a["stroke-width"]) == spec["style"]["axis_width"]
        assert a["stroke-linecap"] == "butt" and spine["boxPaint"] == "svg"
        axis_box = next(e for e in case["axes"] if e["axis"] == spine["axis"] and e["side"] == side)
        assert rgba(a["stroke"]) == rgba(axis_box["computed"]["backgroundColor"])
        if visible:
            native = next(
                e
                for e in lines
                if all(
                    abs(float(e.get(k)) - v) <= 0.01
                    for k, v in zip(("x1", "y1", "x2", "y2"), expected, strict=True)
                )
            )
            assert float(native.get("stroke-width")) == float(a["stroke-width"])
            assert rgba(native.get("stroke")) == rgba(a["stroke"])
        spines += 1
        # Interior samples (away from endpoints/ticks) are diagnostics only.
        # All full images are retained; these regions do not replace any gate.
        dpr = case["dpr"]
        midpoint = (
            [actual[0], actual[1] + (actual[3] - actual[1]) * 0.37]
            if vertical
            else [actual[0] + (actual[2] - actual[0]) * 0.37, actual[1]]
        )
        cx, cy = (int(v * dpr) for v in midpoint)
        samples = []
        for offset in range(-5, 6):
            x, y = (cx + offset, cy) if vertical else (cx, cy + offset)
            if 0 <= x < browser.shape[1] and 0 <= y < browser.shape[0]:
                b, n = browser[y, x], canonical[y, x]
                equal = bool(np.array_equal(b, n))
                sample_matches += equal
                sample_count += 1
                samples.append(
                    {
                        "pixel": [x, y],
                        "browser": b.tolist(),
                        "native_svg_browser": n.tolist(),
                        "equal": equal,
                    }
                )
        pixels.append(
            {
                "case": case["key"],
                "axis": spine["axis"],
                "side": side,
                "attributes": a,
                "samples": samples,
            }
        )
images = []
for p in sorted((OLD / "after").glob("*.ordinary.png")):
    assert p.read_bytes() == (OUT / "matrix" / p.name).read_bytes(), p.name
    images.append(p.name)
history = json.loads((OUT / "history-snapshot.json").read_text())
for name, sha in history.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha, name
result = {
    "status": "PASS",
    "native_svg_plot_cases": checked,
    "actual_svg_spines_checked": spines,
    "geometry_tolerance_css_pixels": 0.01,
    "ordinary_records_identical_to_188f": ordinary,
    "ordinary_screenshots_identical_to_188f": images,
    "historical_files_unchanged": len(history),
    "adjacent_raw_pixel_samples": sample_count,
    "exact_raw_sample_matches": sample_matches,
    "pixel_samples_are_diagnostics_not_a_new_gate": True,
    "endpoint_cap_parity_claimed": False,
}
(OUT / "canonical-proof.json").write_text(json.dumps(result, indent=2) + "\n")
(OUT / "canonical-pixel-samples.json").write_text(json.dumps(pixels, indent=2) + "\n")
print(json.dumps(result, indent=2))
