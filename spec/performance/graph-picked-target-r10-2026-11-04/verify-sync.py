"""Bind accepted-main sync proof to exact source, history and shipping bytes."""

import hashlib
import json
import subprocess
from pathlib import Path

receipt = Path(__file__).resolve().parent
first = "c318a0cb2a25bd18d21dc925eb234340b06ddbbb"
second = "40c0cc5af2fead54684197c0ef90affbbff53519"
reviewed = "74195403ccd18c760e3d20a18f024daab95d711a"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args])


assert git("rev-parse", "HEAD").decode().strip() == first
assert git("rev-parse", "MERGE_HEAD").decode().strip() == second
assert git("rev-parse", second + "^{tree}") == git("rev-parse", reviewed + "^{tree}")
assert git("diff", "--name-only", "--diff-filter=U") == b""
assert git("diff", "--name-only") == b""  # Tracked working bytes equal staged bytes.
index = {}
for item in git("ls-files", "-s", "-z").split(b"\0"):
    if item:
        meta, path = item.split(b"\t", 1)
        mode, blob, stage = meta.decode().split()
        assert stage == "0"
        index[path.decode()] = {"mode": mode, "blob": blob}
counts = {}
for name in ("before-nonspec", "before-history", "incoming-history"):
    expected = json.loads((receipt / (name + ".json")).read_text())
    assert all(index[path] == identity for path, identity in expected.items()), name
    counts[name] = len(expected)
prior = json.loads((receipt / "prior-receipts-before.json").read_text())
assert len(prior) == 658
assert all(sha(Path(path).read_bytes()) == identity for path, identity in prior.items())
inputs = json.loads(
    Path(
        "spec/performance/graph-picked-target-r6-2026-11-04/r5-production-inputs-reuse.json"
    ).read_text()
)
assert len(inputs) == 285
assert all(sha(Path(path).read_bytes()) == identity["actual"] for path, identity in inputs.items())
artifacts = json.loads((receipt / "artifacts-before.json").read_text())
assert len(artifacts) == 15
assert all(
    sha(Path(path).read_bytes()) == identity["expected"] for path, identity in artifacts.items()
)
for path in ("spec/design/graph-interaction.md", "spec/process/production-readiness.md"):
    assert Path(path).read_bytes() == git("show", first + ":" + path)
snapshot = "spec/releases/0.6.0-api-inventory.json"
before = json.loads(git("show", first + ":" + snapshot))
current = json.loads(Path(snapshot).read_text())
assert before["contracts"] == current["contracts"]
assert len(before["gaps"]) == len(current["gaps"]) == 685
assert before["sourceSha256"] == current["sourceSha256"]
assert current["sourceProvenance"]["baseCommit"] == first
changed = git("diff", "--name-only", first, "--", ".", ":(exclude)spec/performance/**")
assert changed.decode().splitlines() == [
    "spec/design/graphforge-node-scheduling.md",
    snapshot,
]
record = {
    "first_parent": first,
    "accepted_main": second,
    "accepted_main_tree_exact_reviewed_741954": True,
    "exact_mode_and_blob_counts": counts,
    "prior_R1_R9_receipt_files_SHA256_exact": len(prior),
    "production_inputs_SHA256_exact": len(inputs),
    "qualified_artifacts_SHA256_exact": artifacts,
    "all_source_build_tests_CI_and_R7_guard_ownership_exact_c318": True,
    "inventory_contracts_classifications_and_source_hashes_exact_c318": True,
    "only_nonreceipt_changes": changed.decode().splitlines(),
    "preparation_gaps": 685,
    "freeze": "UNACCEPTED",
    "production_rebuild_or_browser_rerun": False,
    "reused_R9_local_proof": "770 make check-ci, exact workspace/all-targets Clippy, 152 Rust tests; all relevant non-spec files remain exact",
    "remote_CI": "Parent reports completed SUCCESS for pre-sync c318; R10 fresh main-based CI is still required",
    "new_independent_final_combined_tip_review": "Required, parent owned; not inferred from prior approval",
}
with (receipt / "protected-identity.json").open("x") as stream:
    stream.write(json.dumps(record, indent=2) + "\n")
print(json.dumps(record, indent=2))
