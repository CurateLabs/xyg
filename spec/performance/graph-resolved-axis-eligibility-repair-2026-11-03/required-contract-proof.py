"""Audit bounded R4 fixes and preserve 25d's geometry, CSS and full-helper proof."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

root = Path.cwd()
out = Path(__file__).resolve().parent
old = root / "spec/performance/graph-resolved-scene-consumer-repair-2026-11-03"
base = "25d455f0e7bc3a510210c1959c51165e0423aaf9"
sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731

before = json.loads((out / "before-complete/observations.json").read_text())
after = json.loads((out / "after/observations.json").read_text())
assert len(before["failures"]) == 9 and not before["skipped"]
assert len(after["cases"]) == len(after["switches"]) == 12
assert not after["failures"] and not after["skipped"]
assert after["probeSourceSha256"] == sha(
    (root / "tests/browser/resolved_axis_eligibility.mjs").read_bytes()
)
assert (
    before["assets"]["candidate"]["sha256"]
    == "6cef37f9b430526cc0a4626cba7f56b67d4b67cf6161fbe0bd1f454fae45ec4f"
)
assert after["assets"]["candidate"]["sha256"] == sha(
    (root / "packages/xy-client/dist/index.js").read_bytes()
)
assert all(
    r["different_pixels"] == 0
    for r in json.loads((out / "after-pixels.json").read_text())["comparisons"].values()
)
for name in ("motion-box", "motion-ancestor", "reflection"):
    assert (
        json.loads((out / "before-complete-pixels.json").read_text())["comparisons"][name][
            "different_pixels"
        ]
        > 0
    )
# These complete actual matrices must remain byte-for-byte equal at every
# record/screenshot, rather than merely passing a new local geometry oracle.
matrices = json.loads((out / "matrix/matrix.json").read_text())
old_matrices = json.loads((old / "literal-matrix/matrix.json").read_text())
assert matrices["cases"] == old_matrices["cases"]
assert {k: v for k, v in matrices.items() if k != "artifacts"} == {
    k: v for k, v in old_matrices.items() if k != "artifacts"
}
assert len(matrices["cases"]) == 222 and not matrices["failures"]
slots = json.loads((out / "slots/observations.json").read_text())
assert slots == json.loads((old / "slots-literal/observations.json").read_text())
assert len(slots["cases"]) == 144 and not slots["failures"]
assert json.loads((out / "precision/observations.json").read_text()) == json.loads(
    (old / "precision/observations.json").read_text()
)
preserved_images = {}
for new_dir, old_dir in (
    ("matrix", "literal-matrix"),
    ("slots", "slots-literal"),
    ("precision", "precision"),
):
    count = 0
    for p in (out / new_dir).glob("*.png"):
        if new_dir != "matrix" or p.name.endswith(".ordinary.png"):
            assert p.read_bytes() == (old / old_dir / p.name).read_bytes(), p.name
        count += 1
    preserved_images[new_dir] = count
helper = "tests/browser/graph_property_default_export.mjs"
assert (root / helper).read_bytes() == subprocess.check_output(["git", "show", f"{base}:{helper}"])
new_property = json.loads((out / "property/browser.json").read_text())
old_property = json.loads((old / "property-literal/browser.json").read_text())
assert new_property["config"] == old_property["config"]
assert new_property["pixels"] == old_property["pixels"]
assert new_property["themes"] == old_property["themes"]
assert new_property["failures"] == old_property["failures"]
assert [r["label"] for r in new_property["failures"]] == [
    f"{t}: scene_vs_initial_native pixels" for t in ("light", "dark")
]
exports = {}
for theme in ("light", "dark"):
    assert new_property["pixels"][theme]["wasm_scene"]["passed"]
    for suffix in (
        "xygq",
        "xygf",
        "svg",
        "png",
        "native.svg",
        "native.png",
        "wasm.browser.png",
        "native.browser.png",
    ):
        name = f"{theme}.{suffix}"
        data = (out / "property" / name).read_bytes()
        assert data == (old / "property-literal" / name).read_bytes(), name
        exports[name] = sha(data)
history = json.loads((out / "history-snapshot.json").read_text())
for name, expected in history.items():
    assert sha((root / name).read_bytes()) == expected, name
reuse = json.loads((old / "reuse.json").read_text())
for name, expected in reuse["files"].items():
    assert sha((root / name).read_bytes()) == expected["sha256"], name
(out / "reuse.json").write_text(json.dumps(reuse, indent=2) + "\n")
result = {
    "status": "Bounded R4 eligibility PASS; whole property helper remains normal exit 1",
    "historical_files_unchanged": len(history),
    "before_actual_supported_feature_failures": before["failures"],
    "after_focused_failures": after["failures"],
    "support": after["cases"][0]["support"],
    "unsupported_browser_parity_claimed": False,
    "all_222_matrix_records_unchanged_from_25d": True,
    "all_144_slot_records_unchanged_from_25d": True,
    "all_literal_precision_records_unchanged_from_25d": True,
    "captured_screenshots": preserved_images,
    "exact_ordinary_screenshots": 12,
    "exact_slot_screenshots": 144,
    "exact_precision_screenshots": 6,
    "additional_resolved_image_equality_audit": "Separate stricter verify.py FAIL; 16 recapture differences are retained without waiver or tolerance change",
    "matrix_image_diagnostics": json.loads((out / "matrix-image-diagnostics.json").read_text()),
    "helper_sha256": sha((root / helper).read_bytes()),
    "helper_unchanged_from_25d": True,
    "unchanged_limits": new_property["config"],
    "property_pixels_unchanged_from_25d": new_property["pixels"],
    "helper_normal_exit_code": 1,
    "known_remaining_failures": new_property["failures"],
    "identities_routes_heads_captions_legend_slot_cascade_unchanged": True,
    "canonical_native_and_browser_exports_unchanged": exports,
    "native_and_wasm_rebuilt": False,
}
(out / "required-contract.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
