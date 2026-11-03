"""Audit the bounded projection repair without changing any historical receipt."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent
BASE = "f006d413c25177e65f60cbcb21a8f0e9ead5138b"
sys.path.insert(0, str(ROOT / "tests"))
from test_graph_visual_goldens import _rgb  # noqa: E402


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n")


diagnosis = ROOT / "spec/performance/graph-axis-stroke-diagnosis-2026-11-03"
snapshot = json.loads((OUT / "diagnosis-snapshot.json").read_text())
assert {str(p.relative_to(diagnosis)) for p in diagnosis.rglob("*") if p.is_file()} == set(snapshot)
for name, expected in snapshot.items():
    assert digest((diagnosis / name).read_bytes()) == expected, name
before = json.loads((OUT / "before/matrix.json").read_text())
after = json.loads((OUT / "after/matrix.json").read_text())
assert len(before["failures"]) == 111 and all(
    f["name"].endswith(".resolved") for f in before["failures"]
)
assert len(after["cases"]) == 222 and after["failures"] == []


def rgba8(css: str) -> list[int]:
    values = [float(v) for v in re.findall(r"[0-9.]+", css)]
    return [*(round(v) for v in values[:3]), round((values[3] if len(values) == 4 else 1) * 255)]


canonical_spines_checked = 0
canonical_plot_failures = []
before_cases = {case["key"]: case for case in before["cases"]}
for case in after["cases"]:
    if case["lane"] != "resolved":
        continue
    item = case["item"]
    svg = ET.parse(OUT / "inputs" / f"{item['name']}.svg").getroot()
    plot = next(e for e in svg if e.get("data-xy-chrome") == "plot-background")
    native_plot = dict(
        zip(
            ("x", "y", "w", "h"),
            (float(plot.get(k)) for k in ("x", "y", "width", "height")),
            strict=True,
        )
    )
    if any(abs(case["plot"][k] - v) > 0.01 for k, v in native_plot.items()):
        assert before_cases[case["key"]]["plot"] == case["plot"]
        canonical_plot_failures.append(
            {
                "case": case["key"],
                "native_svg_plot": native_plot,
                "f006_browser_plot": before_cases[case["key"]]["plot"],
                "repaired_browser_plot": case["plot"],
            }
        )
    axes = next((e for e in svg if e.get("data-xy-chrome") == "axes"), [])
    lines = [e for e in axes if e.tag.endswith("}line")]
    visible = (
        item["width"] is not None and item["width"] > 0 and item["paint"] in ("opaque", "alpha")
    )
    assert len(lines) == (len(case["axes"]) if visible else 0)
    for axis in case["axes"]:
        spec = case["axisSpec"][axis["axis"]]
        assert spec["tick_resolution"] == "rust_scene"
        assert spec["style"]["axis_width"] == (item["width"] or 0)
        expected_rgba = (
            [229, 231, 235, {"opaque": 255, "alpha": 128, "transparent": 0}.get(item["paint"], 0)]
            if item["paint"] != "hidden"
            else [0, 0, 0, 0]
        )
        assert rgba8(axis["computed"]["backgroundColor"]) == expected_rgba
        if not visible:
            continue
        p = native_plot
        if axis["axis"].startswith("y"):
            x = p["x"] + (p["w"] if axis["side"] == "right" else 0)
            endpoints = [x, p["y"], x, p["y"] + p["h"]]
        else:
            y = p["y"] + (p["h"] if axis["side"] == "bottom" else 0)
            endpoints = [p["x"], y, p["x"] + p["w"], y]
        line = next(
            e
            for e in lines
            if all(
                abs(float(e.get(k)) - v) <= 0.01
                for k, v in zip(("x1", "y1", "x2", "y2"), endpoints, strict=True)
            )
        )
        assert float(line.get("stroke-width")) == spec["style"]["axis_width"]
        assert rgba8(line.get("stroke")) == expected_rgba
        canonical_spines_checked += 1
ordinary = []
for old, new in zip(before["cases"], after["cases"], strict=True):
    assert old["key"] == new["key"]
    if old["lane"] == "ordinary":
        assert old == new, old["key"]
        ordinary.append(old["key"])
    assert old["plot"] == new["plot"]
    assert old["axisSpec"] == new["axisSpec"]
    for a, b in zip(old["axes"], new["axes"], strict=True):
        assert a["computed"] == b["computed"]
        assert a["resolvedPaint"] == b["resolvedPaint"]
ordinary_images = []
for p in sorted((OUT / "before").glob("*.ordinary.png")):
    assert p.read_bytes() == (OUT / "after" / p.name).read_bytes()
    ordinary_images.append(p.name)
old_property = ROOT / "spec/performance/graph-resolved-legend-repair-2026-11-03/after"
exports = {}
for theme in ("light", "dark"):
    for suffix in ("xygq", "xygf", "svg", "png", "native.svg", "native.png"):
        name = f"{theme}.{suffix}"
        a, b = (old_property / name).read_bytes(), (OUT / "property" / name).read_bytes()
        assert a == b, name
        exports[name] = digest(b)
old = json.loads((old_property / "browser.json").read_text())
new = json.loads((OUT / "property/browser.json").read_text())
assert [f["label"] for f in new["failures"]] == [f["label"] for f in old["failures"]]
for theme in ("light", "dark"):
    for key in ("painted", "points", "routes", "labels", "legend", "slotCascade"):
        assert old["themes"][theme]["wasm"][key] == new["themes"][theme]["wasm"][key]
    assert old["themes"][theme]["native"] == new["themes"][theme]["native"]
    for key in ("native_chart", "scene_vs_initial_native"):
        assert old["pixels"][theme][key] == new["pixels"][theme][key]
helper = "tests/browser/graph_property_default_export.mjs"
assert (ROOT / helper).read_bytes() == subprocess.check_output(["git", "show", f"{BASE}:{helper}"])
# Record the remaining coverage gap from actual images and actual DOM boxes.
post = OUT / "post-projection-captures"
dom = json.loads((post / "dom.json").read_text())
coverage = {}
for theme in ("light", "dark"):
    for dpr in (1, 2):
        key = f"{theme}.dpr{dpr}"
        images = {
            name: _rgb((post / f"{key}.{suffix}.png").read_bytes())
            for name, suffix in (
                ("native", "canonical"),
                ("wasm", "wasm"),
                ("canonical_svg_browser", "canonical-svg-browser"),
            )
        }
        diff = np.abs(images["native"] - images["wasm"]).max(axis=2)
        samples = []
        for x, y in [
            *((300 * dpr, y) for y in range(376 * dpr - 3, 376 * dpr + 3)),
            *((x, 200 * dpr) for x in range(52 * dpr - 3, 52 * dpr + 3)),
        ]:
            samples.append({"pixel": [x, y], **{n: a[y, x].tolist() for n, a in images.items()}})
        coverage[key] = {
            "purpose": "diagnostic only; no pixel omitted and no acceptance waiver",
            "mean_max_channel_diff": float(diff.mean()),
            "fraction_over_96": float((diff > 96).mean()),
            "pixels_over_96": int((diff > 96).sum()),
            "axis_boxes": [e["box"] for e in dom["captures"][key]["wasm"]["axes"]],
            "device_pixel_ratio": dom["captures"][key]["wasm"]["devicePixelRatio"],
            "samples": samples,
        }
write("remaining-coverage.json", coverage)
write(
    "canonical-contract.json",
    {
        "status": "FAIL" if canonical_plot_failures else "PASS",
        "geometry_tolerance_css_pixels": 0.01,
        "failed_cases": canonical_plot_failures,
        "scope": "independent native SVG plot comparison; pre-existing failures retained, no layout repair or waiver",
    },
)
write(
    "integrity.json",
    {
        "status": "bounded local projection/preservation passes; canonical authored plot and full-image AC fail",
        "diagnosis_files_unchanged": len(snapshot),
        "ordinary_case_records_unchanged": len(ordinary),
        "visible_authored_spines_checked_against_actual_native_svg": canonical_spines_checked,
        "all_111_resolved_authored_width_and_rgba_checks_pass": True,
        "canonical_plot_failure_count": len(canonical_plot_failures),
        "canonical_plot_failures_are_unchanged_from_f006": True,
        "ordinary_screenshots_unchanged": ordinary_images,
        "all_case_plots_axis_specs_and_paints_unchanged": True,
        "canonical_and_native_exports_unchanged": exports,
        "untouched_property_helper_sha256": digest((ROOT / helper).read_bytes()),
        "full_helper_expected_actual_exit": 1,
        "full_helper_failure_labels": [f["label"] for f in new["failures"]],
    },
)
# Generated HTML and raw build logs are retained losslessly, not sanitized.
for p in [*(OUT / "property").glob("*.native.html"), OUT / "client-build.txt"]:
    if p.exists():
        p.with_name(p.name + ".gz").write_bytes(gzip.compress(p.read_bytes(), mtime=0))
        p.unlink()
source_paths = [
    "js/src/50_chartview.ts",
    "spec/design/browser-wasm.md",
    "tests/browser/resolved_axis_spines.py",
    "tests/browser/resolved_axis_spines.mjs",
]
diff = subprocess.check_output(
    ["git", "diff", "--cached", "--binary", "--full-index", BASE, "--", *source_paths]
)
assert diff
(OUT / "source.diff.gz").write_bytes(gzip.compress(diff, mtime=0))
write(
    "source.json",
    {
        "base": BASE,
        "branch": subprocess.check_output(["git", "branch", "--show-current"], text=True).strip(),
        "worktree": str(ROOT),
        "source_diff_argv": [
            "git",
            "diff",
            "--cached",
            "--binary",
            "--full-index",
            BASE,
            "--",
            *source_paths,
        ],
        "source_diff_sha256": digest(diff),
        "source_diff_excludes_receipts": True,
        "source_files": {name: digest((ROOT / name).read_bytes()) for name in source_paths},
        "reuse": json.loads((OUT / "reuse.json").read_text()),
    },
)
write(
    "artifacts.json",
    {
        str(p.relative_to(OUT)): {"bytes": p.stat().st_size, "sha256": digest(p.read_bytes())}
        for p in sorted(OUT.rglob("*"))
        if p.is_file()
        and (
            p.suffix in (".png", ".scene", ".svg", ".bin", ".xygf", ".xygq", ".gz")
            or p.name in ("matrix.json", "dom.json", "remaining-coverage.json")
        )
    },
)
print(
    "Diagnosis and ordinary geometry/images preserved; authored widths/paint, exports, identities, routes, captions and helper immutability verified. Canonical plot/full-image failures retained."
)

if canonical_plot_failures:
    print(
        f"Canonical authored plot comparison FAIL: {len(canonical_plot_failures)} pre-existing mismatches; normal exit 1."
    )
    sys.exit(1)
