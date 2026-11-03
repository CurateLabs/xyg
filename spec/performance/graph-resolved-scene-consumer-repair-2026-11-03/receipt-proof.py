"""Preservation, slot-image, producer and untouched full-gate evidence audit."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent
BASE = "188f7450bff332e0be6a80bf97b15b86e74b48ae"
OLD = ROOT / "spec/performance/graph-resolved-axis-repair-2026-11-03"
sys.path.insert(0, str(ROOT / "tests"))
from test_graph_visual_goldens import _rgb  # noqa: E402


def sha(data):
    return hashlib.sha256(data).hexdigest()


helper = "tests/browser/graph_property_default_export.mjs"
assert (ROOT / helper).read_bytes() == subprocess.check_output(["git", "show", f"{BASE}:{helper}"])
reuse = json.loads((OLD / "reuse.json").read_text())
for name, expected in reuse["files"].items():
    assert sha((ROOT / name).read_bytes()) == expected["sha256"], name
(OUT / "reuse.json").write_text(json.dumps(reuse, indent=2) + "\n")
old = json.loads((OLD / "property/browser.json").read_text())
new = json.loads((OUT / "property-final/browser.json").read_text())
assert [f["label"] for f in new["failures"]] == [
    f"{t}: scene_vs_initial_native pixels" for t in ("light", "dark")
]
assert new["config"] == old["config"]
exports = {}
for theme in ("light", "dark"):
    for suffix in ("xygq", "xygf", "svg", "png", "native.svg", "native.png"):
        name = f"{theme}.{suffix}"
        data = (OUT / "property-final" / name).read_bytes()
        assert data == (OLD / "property" / name).read_bytes(), name
        exports[name] = sha(data)
    for key in ("painted", "points", "routes", "labels", "legend", "slotCascade", "legendDom"):
        assert old["themes"][theme]["wasm"][key] == new["themes"][theme]["wasm"][key], (theme, key)
    assert old["themes"][theme]["native"] == new["themes"][theme]["native"]
    for key in ("native_chart", "scene_vs_initial_native"):
        assert old["pixels"][theme][key] == new["pixels"][theme][key]
    assert new["pixels"][theme]["wasm_scene"]["passed"]
slots = json.loads((OUT / "slots-complete/observations.json").read_text())
assert len(slots["cases"]) == 144 and not slots["failures"]
fallbacks = solids = 0
slot_samples = {}
for case in slots["cases"]:
    if case["lane"] != "after":
        continue
    before = next(
        c
        for c in slots["cases"]
        if c["name"] == case["name"] and c["dpr"] == case["dpr"] and c["lane"] == "before"
    )
    a = _rgb((OUT / "slots-complete" / f"{before['key']}.png").read_bytes())
    b = _rgb((OUT / "slots-complete" / f"{case['key']}.png").read_bytes())
    delta = np.abs(a - b).max(axis=2)
    if case["expected"] == "html":
        assert not delta.any(), case["key"]
        fallbacks += 1
    else:
        solids += 1
    dpr = case["dpr"]
    pixel = [int(40 * dpr), int(22 * dpr)]
    slot_samples[case["key"]] = {
        "pixels_different": int((delta > 0).sum()),
        "max_channel_diff": int(delta.max()),
        "pixel": pixel,
        "before": a[pixel[1], pixel[0]].tolist(),
        "after": b[pixel[1], pixel[0]].tolist(),
    }
# Integer authored solid/alpha boxes match the HTML baseline too: in particular
# alpha cannot pass this equality if both HTML and SVG are visibly painted.
for name in ("solid", "alpha", "inline", "important", "visibility"):
    for dpr in (1, 1.25, 2):
        assert slot_samples[f"{name}.dpr{dpr}.after"]["pixels_different"] == 0
(OUT / "slot-pixel-proof.json").write_text(json.dumps(slot_samples, indent=2) + "\n")
result = {
    "status": "PASS within bounded consumer scope; whole property helper remains FAIL",
    "helper_sha256": sha((ROOT / helper).read_bytes()),
    "helper_unchanged_from_188f": True,
    "unchanged_limits": new["config"],
    "property_before": old["pixels"],
    "property_after": new["pixels"],
    "normal_helper_exit_code": 1,
    "remaining_failures": new["failures"],
    "native_exports_byte_identical": exports,
    "identities_routes_heads_captions_legend_and_slot_cascade_unchanged": True,
    "slot_captures": len(slots["cases"]),
    "live_switch_runs": len(slots["switches"]),
    "html_fallback_screenshots_identical_to_188f": fallbacks,
    "solid_projection_screenshots_identical_to_188f": solids,
    "native_and_wasm_rebuilt": False,
}
(OUT / "integrity.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
