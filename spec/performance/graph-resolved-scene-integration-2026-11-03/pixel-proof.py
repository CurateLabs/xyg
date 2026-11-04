"""Whole-image CSS compatibility diagnostics; no masks or tolerance policy."""

import json
import sys
from pathlib import Path

import numpy as np

root = Path.cwd()
out = Path(__file__).resolve().parent
sys.path.insert(0, str(root / "tests"))
from test_graph_visual_goldens import _rgb  # noqa: E402

phase = sys.argv[1]
source = out / phase
rows = json.loads((source / "observations.json").read_text())
result = {}
for p in sorted(source.glob("*.candidate.png")):
    name = p.name.removesuffix(".candidate.png")
    baseline = _rgb((source / f"{name}.baseline.png").read_bytes())
    candidate = _rgb(p.read_bytes())
    diff = np.abs(candidate - baseline).max(axis=2)
    result[name] = {
        "all_pixels": int(diff.size),
        "different_pixels": int((diff > 0).sum()),
        "max_channel_difference": int(diff.max()),
        "mean_max_channel_difference": float(diff.mean()),
        "baseline_exact_red_pixels": int((baseline == [255, 0, 0]).all(axis=2).sum()),
        "candidate_exact_red_pixels": int((candidate == [255, 0, 0]).all(axis=2).sum()),
    }
value = {
    "phase": phase,
    "support": rows["cases"][0]["support"],
    "candidate_asset": rows["assets"]["candidate"],
    "comparisons": result,
    "purpose": "Every pixel compared; feature-specific counts are diagnostics only",
}
(out / f"{phase}-pixels.json").write_text(json.dumps(value, indent=2) + "\n")
print(json.dumps(value, indent=2))
if phase == "after":
    assert all(row["different_pixels"] == 0 for row in result.values())
