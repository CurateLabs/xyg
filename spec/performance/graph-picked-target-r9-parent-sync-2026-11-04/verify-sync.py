"""Verify the reviewed parent sync without rebuilding qualified shipping assets."""

import hashlib
import json
import subprocess
from pathlib import Path

receipt = Path(__file__).resolve().parent
first = "f39edf76635e6e572aec64b6bcedc20cfed3f7eb"
second = "74195403ccd18c760e3d20a18f024daab95d711a"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args])


assert git("rev-parse", "HEAD").decode().strip() == first
assert git("rev-parse", "MERGE_HEAD").decode().strip() == second
assert git("diff", "--name-only", "--diff-filter=U") == b""
assert git("diff", "--name-only") == b""  # Tracked worktree matches its index.
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
assert len(prior) == 610
assert all(sha(Path(path).read_bytes()) == identity for path, identity in prior.items())
inputs = json.loads(
    Path(
        "spec/performance/graph-picked-target-r6-2026-11-04/r5-production-inputs-reuse.json"
    ).read_text()
)
assert len(inputs) == 285
assert all(sha(Path(path).read_bytes()) == identity["actual"] for path, identity in inputs.items())
artifacts = json.loads(
    Path("spec/performance/graph-picked-target-r8-2026-11-04/artifacts-before.json").read_text()
)
assert len(artifacts) == 15
assert all(
    sha(Path(path).read_bytes()) == identity["expected"] for path, identity in artifacts.items()
)
for path in ("spec/design/graph-interaction.md", "spec/process/production-readiness.md"):
    assert Path(path).read_bytes() == git("show", first + ":" + path)
path = "spec/design/graphforge-node-scheduling.md"
assert Path(path).read_bytes() == git("show", second + ":" + path)
snapshot = "spec/releases/0.6.0-api-inventory.json"
before = json.loads(git("show", first + ":" + snapshot))
current = json.loads(Path(snapshot).read_text())
assert before["contracts"] == current["contracts"]
assert len(before["gaps"]) == len(current["gaps"]) == 685
assert before["sourceSha256"] == current["sourceSha256"]
assert current["sourceProvenance"]["baseCommit"] == first
assert (
    git(
        "diff",
        "--name-only",
        "6e240f4bd3189640779fd684e97072923cbfb9c8",
        second,
        "--",
        ".",
        ":(exclude)spec/**",
    )
    == b""
)
changed = git("diff", "--name-only", first, "--", ".", ":(exclude)spec/performance/**")
assert changed.decode().splitlines() == [path, snapshot]
record = {
    "first_parent": first,
    "second_parent": second,
    "exact_mode_and_blob_counts": counts,
    "all_610_prior_R1_R9_receipt_files_SHA256_exact": True,
    "production_inputs_SHA256_exact": len(inputs),
    "qualified_artifacts_SHA256_exact": artifacts,
    "current_Node_scheduling_document_exact_incoming": True,
    "R9_CI_test_source_and_R7_inventory_guard_and_tests_exact_first_parent": True,
    "inventory_contracts_classifications_source_hashes_exact_first_parent": True,
    "preparation_gaps": 685,
    "production_rebuild_or_full_browser_rerun": False,
    "reused_R9_proof": "770 make check-ci, exact workspace/all-targets Clippy, 152 Rust tests; their non-spec source/test/workflow/toolchain files remain exact",
    "new_independent_combined_tip_review": "Required, parent owned; not performed",
}
with (receipt / "protected-identity.json").open("x") as stream:
    stream.write(json.dumps(record, indent=2) + "\n")
print(json.dumps(record, indent=2))
