"""Bind review scope and exact production identities without rebuilding."""

import hashlib
import json
import subprocess
from pathlib import Path

r = Path(__file__).resolve().parent
r6 = r.parent / "graph-picked-target-r6-2026-11-04"


def sha(b):
    return hashlib.sha256(b).hexdigest()


a = json.loads((r6 / "r5-artifacts-after.json").read_text())
art = {
    p: {"expected": v["actual_sha256"], "actual": sha(Path(p).read_bytes())} for p, v in a.items()
}
assert len(art) == 15 and all(v["expected"] == v["actual"] for v in art.values())
inputs = json.loads((r6 / "r5-production-inputs-reuse.json").read_text())
assert all(sha(Path(p).read_bytes()) == v["actual"] for p, v in inputs.items())
fixture = "crates/xyg-engine/src/graphforge/interaction/tests/wire/picked_checkpoint.rs"
old = subprocess.check_output(
    ["git", "show", "01f1072985b891d75015290999381f66d901d049:" + fixture]
)
assert Path(fixture).read_bytes() == b"#![cfg(test)]\n\n" + old
base = "eb9ea4c78a5acec192cd6fd98d9edb86fa3ae48c"
head = "01f1072985b891d75015290999381f66d901d049"
whole = subprocess.check_output(["git", "diff", "--binary", "--full-index", base, head])
non = subprocess.check_output(
    [
        "git",
        "diff",
        "--binary",
        "--full-index",
        base,
        head,
        "--",
        ".",
        ":(exclude)spec/performance/**",
    ]
)
assert sha(whole) == "d8a613b265350e11752a3b85d627adb31601858d6be5687806f3ae16266ba101"
assert sha(non) == "c626343fe2f7ce4ad8a51511a68036128b2448650b7c007127d226ab17eff746"
base_inventory = json.loads(
    subprocess.check_output(["git", "show", head + ":spec/releases/0.6.0-api-inventory.json"])
)
current = json.loads(Path("spec/releases/0.6.0-api-inventory.json").read_text())
assert base_inventory["contracts"] == current["contracts"]
assert len(base_inventory["gaps"]) == len(current["gaps"]) == 685
prior = json.loads((r / "prior-receipts-before.json").read_text())
assert all(sha(Path(p).read_bytes()) == value for p, value in prior.items())
record = {
    "reviewed_head": head,
    "reviewed_base": base,
    "prior_whole_diff_sha256": sha(whole),
    "prior_nonreceipt_diff_sha256": sha(non),
    "15_artifacts": art,
    "exact_production_input_count": len(inputs),
    "separate_test_source_change": {
        "path": fixture,
        "change": "leading module-wide cfg(test) plus blank line only; prior body byte-exact",
        "old_sha256": sha(old),
        "current_sha256": sha(Path(fixture).read_bytes()),
        "release_authority": "parent cfg(test) declaration unchanged; new inner guard also test-only",
    },
    "inventory_contracts_unchanged": True,
    "preparation_gaps": 685,
    "historical_receipt_files_exact": len(prior),
    "qualification_reuse": "R6 runtime/shipping/CSP/capture/parity proof reused only for unchanged production inputs and exact artifacts; new inspector/test guard have fresh scoped proof",
    "no_release_or_browser_rebuild": True,
}
(r / "protected-identity-and-review-scope.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record, indent=2))
