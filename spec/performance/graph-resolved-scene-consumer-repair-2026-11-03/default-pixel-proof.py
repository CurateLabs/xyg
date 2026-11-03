"""Raw default-graph axis samples before/after; never a masked acceptance gate."""

import json
import sys
from pathlib import Path

import numpy as np

root = Path.cwd()
out = Path(__file__).resolve().parent
sys.path.insert(0, str(root / "tests"))
from test_graph_visual_goldens import _rgb  # noqa: E402

old = root / "spec/performance/graph-resolved-axis-repair-2026-11-03/property"
result = {}
for theme in ("light", "dark"):
    images = {
        "native": _rgb((out / "property-final" / f"{theme}.png").read_bytes()),
        "before": _rgb((old / f"{theme}.wasm.browser.png").read_bytes()),
        "after": _rgb((out / "property-final" / f"{theme}.wasm.browser.png").read_bytes()),
    }
    samples = []
    for x, y in [*((300, y) for y in range(372, 380)), *((x, 200) for x in range(48, 56))]:
        samples.append({"pixel": [x, y], **{k: a[y, x].tolist() for k, a in images.items()}})
    result[theme] = {"device_pixel_ratio": 1, "raw_samples": samples}
(out / "default-pixel-samples.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
# This additional diagnostic asks for exact RGB at four locations. It is
# deliberately stricter than the untouched product helper, not a replacement
# gate or a relaxed tolerance. Preserve its normal FAIL for light's ±1 AA.
for theme, row in result.items():
    for sample in row["raw_samples"]:
        if sample["pixel"] in ([300, 375], [300, 376], [51, 200], [52, 200]):
            assert np.array_equal(sample["native"], sample["after"]), (theme, sample)
