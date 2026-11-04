"""Compare every unmasked pixel of actual before, after and HTML references."""

import json
import sys
from pathlib import Path

import numpy as np

root = Path.cwd()
out = Path(__file__).resolve().parent
sys.path.insert(0, str(root / "tests"))
from test_graph_visual_goldens import _rgb  # noqa: E402

rows = {}
for image in sorted((out / "proof-after").glob("*.png")):
    reference = _rgb((out / "html-reference" / image.name).read_bytes())
    before = _rgb((out / "proof-before" / image.name).read_bytes())
    after = _rgb(image.read_bytes())
    record = {}
    for name, candidate in (("before", before), ("after", after)):
        diff = np.abs(candidate - reference).max(axis=2)
        record[name] = {
            "all_pixels": int(diff.size),
            "different_pixels": int((diff > 0).sum()),
            "max_channel_difference": int(diff.max()),
            "mean_max_channel_difference": float(diff.mean()),
        }
    rows[image.name] = record
value = {
    "masks": [],
    "reference": "independent 188f browser-owned HTML, same authored slot CSS",
    "comparisons": rows,
}
(out / "pixel-proof.json").write_text(json.dumps(value, indent=2) + "\n")
assert len(rows) == 60
assert all(row["after"]["different_pixels"] == 0 for row in rows.values())
for name in (
    "hover-enter",
    "focus-within",
    "keyboard-active-down",
    "active-down",
    "host-hidden-normal",
    "host-hidden-important",
    "host-paint-width-normal",
    "host-paint-width-important",
    "effect-hover",
):
    for dpr in (1, 1.25, 2):
        assert rows[f"{name}.dpr{dpr}.png"]["before"]["different_pixels"] > 0
print(
    "PASS: all 60 complete after screenshots equal independent browser-owned HTML; required before failures visibly differ at every DPR"
)
