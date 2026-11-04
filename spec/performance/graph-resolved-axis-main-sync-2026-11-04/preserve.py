"""Prove exact reviewed source identity and both parents' immutable receipts."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent
HEAD = "8a5922af4b33bfd67f2aefe71f613847d6fdcb08"
MAIN = "3c66580731dde0b10a1f18465c0d0df9e73f8862"
CSS = "78b4b69f76b955ab19bd365f0492711cc3c06c1f"
REVIEWED_PARENT = "60cee1e58bc93766b954d7343b90ec19d676a8de"
ALLOWED = {"spec/design/graph-interaction.md", "spec/releases/0.6.0-api-inventory.json"}


def git(*args):
    return subprocess.check_output(["git", *args])


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tree(ref):
    result = {}
    for entry in git("ls-tree", "-rz", ref).split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, kind, blob = metadata.decode().split()
        assert kind == "blob"
        result[name.decode()] = {"mode": mode, "blob": blob}
    return result


def verify(name, entry):
    path = ROOT / name
    assert path.is_symlink() == (entry["mode"] == "120000"), name
    data = os.readlink(path).encode() if path.is_symlink() else path.read_bytes()
    blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    assert blob == entry["blob"], name
    return {**entry, "bytes": len(data), "sha256": sha(data)}


assert git("rev-parse", "HEAD").decode().strip() == HEAD
assert git("rev-parse", "MERGE_HEAD").decode().strip() == MAIN
assert git("rev-parse", "t3/fix-resolved-axis-css").decode().strip() == CSS
main_tree = git("rev-parse", f"{MAIN}^{{tree}}").decode().strip()
assert main_tree == "b9f1a546159ca949b62bb644f90e3139b58ba9fb"
assert main_tree == git("rev-parse", f"{REVIEWED_PARENT}^{{tree}}").decode().strip()
heads = {ref: tree(ref) for ref in (HEAD, MAIN)}
protected = {
    name: verify(name, entry)
    for name, entry in heads[HEAD].items()
    if not name.startswith("spec/performance/") and name not in ALLOWED
}
current_paths = set(git("ls-files", "-z").decode().strip("\0").split("\0"))
assert {
    name
    for name in current_paths
    if not name.startswith("spec/performance/") and name not in ALLOWED
} == set(protected)
prior = json.loads(
    (
        ROOT / "spec/performance/graph-resolved-axis-parent-sync-2026-11-03/preservation.json"
    ).read_text()
)
prior_inputs = prior["producerBuildAndBrowserTestInputs"]
assert len(prior_inputs) == 580
for name, blob in prior_inputs.items():
    assert protected[name]["blob"] == blob, name
histories = {}
for ref, entries in heads.items():
    records = {
        name: verify(name, entry)
        for name, entry in entries.items()
        if name.startswith("spec/performance/")
    }
    histories[ref] = {
        "count": len(records),
        "listingSha256": sha(json.dumps(records, sort_keys=True).encode()),
        "files": records,
    }
helper_path = "tests/browser/graph_property_default_export.mjs"
helper = (ROOT / helper_path).read_bytes()
assert len(helper) == 20079
assert helper == git("show", f"{CSS}:{helper_path}") == git("show", f"{HEAD}:{helper_path}")
inventory_path = "spec/releases/0.6.0-api-inventory.json"
old_inventory = json.loads(git("show", f"{HEAD}:{inventory_path}"))
current_inventory = json.loads((ROOT / inventory_path).read_bytes())
assert current_inventory["contracts"] == old_inventory["contracts"]
assert current_inventory["contractSha256"] == old_inventory["contractSha256"]
assert current_inventory["gaps"] == old_inventory["gaps"] and len(current_inventory["gaps"]) == 685
assert (
    current_inventory["acceptance"]
    == old_inventory["acceptance"]
    == "preparation-only-not-a-freeze"
)
assert current_inventory["sourceProvenance"]["baseCommit"] == HEAD
changed = git("diff", "--name-only", HEAD).decode().splitlines()
assert set(changed) <= ALLOWED, changed
result = {
    "firstParent": HEAD,
    "acceptedMainParent": MAIN,
    "acceptedMainMergedAt": "2026-11-04T00:40:06Z",
    "acceptedMainTree": main_tree,
    "reviewed1088HeadWithExactAcceptedTree": REVIEWED_PARENT,
    "preservedCssBranch": {"ref": "t3/fix-resolved-axis-css", "commit": CSS},
    "protectedNonreceiptFiles": {
        "count": len(protected),
        "listingSha256": sha(json.dumps(protected, sort_keys=True).encode()),
        "files": protected,
    },
    "priorReviewedProducerBuildAndBrowserTestInputs": {
        "count": len(prior_inputs),
        "allExact": True,
    },
    "propertyBrowserHelper": {
        "path": helper_path,
        "bytes": len(helper),
        "sha256": sha(helper),
        "exactTo78And8a": True,
    },
    "historicalReceipts": histories,
    "metadata": {
        "changedPaths": changed,
        "contractSha256": current_inventory["contractSha256"],
        "reviewGaps": 685,
        "classificationsAndAcceptanceUnchanged": True,
    },
    "conflictResolution": "The sole conflict was inventory provenance/body hash. Regenerated with the unchanged inspector; all declarations, classifications and 685 gaps remain unchanged. Reviewed property helper retained by the normal merge without modification.",
    "validationReuse": "Reuse qualified78/8a native/WASM/browser artifacts and previous visual/runtime results because every product/build/test source remains exact. No fresh native/browser build or browser/runtime qualification is claimed.",
}
path = OUT / "source-preservation.json"
assert not path.exists(), "append-only receipt"
path.write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {
            "protectedFiles": len(protected),
            "priorReviewedInputs": len(prior_inputs),
            "historicalFilesByParent": {ref: value["count"] for ref, value in histories.items()},
            "propertyBrowserHelper": result["propertyBrowserHelper"],
        },
        indent=2,
    )
)
