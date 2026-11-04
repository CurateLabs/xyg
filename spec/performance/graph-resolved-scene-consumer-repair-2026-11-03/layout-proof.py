"""Independent canonical layout proof; no supplied geometry or image exclusions."""

import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

out = Path(sys.argv[1])
root = Path.cwd()
old = root / "spec/performance/graph-resolved-axis-repair-2026-11-03"
after = json.loads((out / "layout-matrix/matrix.json").read_text())
before = json.loads((old / "after/matrix.json").read_text())
assert len(after["cases"]) == 222 and not after["failures"]
checked = 0
ordinary = 0
errors = []
for a, b in zip(after["cases"], before["cases"], strict=True):
    assert a["key"] == b["key"]
    if a["lane"] == "ordinary":
        assert a == b, a["key"]
        ordinary += 1
        continue
    svg = ET.parse(old / "inputs" / f"{a['item']['name']}.svg").getroot()
    p = next(e for e in svg if e.get("data-xy-chrome") == "plot-background")
    expected = dict(
        zip(
            ("x", "y", "w", "h"),
            (float(p.get(k)) for k in ("x", "y", "width", "height")),
            strict=True,
        )
    )
    error = max(abs(a["plot"][k] - v) for k, v in expected.items())
    checked += 1
    if error > 0.01:
        errors.append({"case": a["key"], "native_svg": expected, "browser": a["plot"]})
images = []
for p in sorted((old / "after").glob("*.ordinary.png")):
    assert p.read_bytes() == (out / "layout-matrix" / p.name).read_bytes(), p.name
    images.append(p.name)
snapshot = json.loads((out / "history-snapshot.json").read_text())
for name, expected in snapshot.items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
result = {
    "canonical_svg_plot_cases": checked,
    "canonical_failures": errors,
    "ordinary_case_records_identical_to_188f": ordinary,
    "ordinary_screenshots_identical_to_188f": images,
    "historical_files_unchanged": len(snapshot),
    "scope": "layout-only candidate; product SVG paint pending compatibility decision",
}
(out / "layout-proof.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
assert not errors
