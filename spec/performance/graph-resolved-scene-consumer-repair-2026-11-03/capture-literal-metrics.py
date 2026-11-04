"""Additional all-pixel diagnostics at three DPRs; no replacement acceptance gate."""

import json
import sys
from pathlib import Path

import numpy as np

root = Path.cwd()
out = Path(__file__).resolve().parent
sys.path.insert(0, str(root / "tests"))
from test_graph_visual_goldens import _rgb  # noqa: E402

captures = out / "default-literal-captures"
dom = json.loads((captures / "dom.json").read_text())
result = {}
for key, row in dom["captures"].items():
    images = {
        name: _rgb((captures / f"{key}.{name}.png").read_bytes())
        for name in ("canonical", "wasm", "canonical-svg-browser")
    }
    diff = np.abs(images["canonical"] - images["wasm"]).max(axis=2)
    wasm = row["wasm"]
    assert wasm["plot"] == {"x": 52, "y": 24, "w": 572, "h": 352}
    assert len(wasm["axes"]) == len(wasm["spines"]) == 2
    assert all(a["computed"]["clipPath"] == "inset(100%)" for a in wasm["axes"])
    for spine in wasm["spines"]:
        assert any(
            all(
                float(spine["line"]["attributes"][attr]) == float(native["attributes"][attr])
                for attr in ("x1", "y1", "x2", "y2", "stroke-width")
            )
            for native in row["canonicalSvgBrowser"]["axes"]
        )
    dpr = wasm["devicePixelRatio"]
    samples = []
    for x, y in [
        *((int(300 * dpr), y) for y in range(int(376 * dpr) - 4, int(376 * dpr) + 4)),
        *((x, int(200 * dpr)) for x in range(int(52 * dpr) - 4, int(52 * dpr) + 4)),
    ]:
        samples.append({"pixel": [x, y], **{k: a[y, x].tolist() for k, a in images.items()}})
    result[key] = {
        "purpose": "additional full-image diagnostic; untouched property helper is authoritative at DPR 1",
        "devicePixelRatio": dpr,
        "mean_max_channel_diff": float(diff.mean()),
        "fraction_over_96": float((diff > 96).mean()),
        "plot": wasm["plot"],
        "svg_attrs_equal_to_actual_native_svg": True,
        "samples": samples,
    }
(out / "capture-literal-metrics.json").write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {k: {a: v for a, v in row.items() if a != "samples"} for k, row in result.items()}, indent=2
    )
)
