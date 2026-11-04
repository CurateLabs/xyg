"""Verify the normal parent sync preserves the qualified native-input repair."""

import hashlib
import json
import subprocess
from pathlib import Path

receipt = Path(__file__).resolve().parent
root = receipt.parents[2]
before = json.loads((receipt / "before-sync.json").read_text())
qualified, incoming = before["parents"]


def sha(path):
    return hashlib.sha256((root / path).read_bytes()).hexdigest()


def blob(path):
    data = (root / path).read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


allowed = {
    "spec/design/browser-wasm.md",
    "spec/design/graph-interaction.md",
    "spec/releases/0.6.0-api-inventory.json",
    "scripts/check_stale_names.py",
    "tests/test_stale_names.py",
    "spec/design/xyg-naming.md",
}
changed = set(
    subprocess.check_output(
        ["git", "diff", "--name-only", qualified, "--", ".", ":!spec/performance/**"], text=True
    ).splitlines()
)
assert changed == allowed, changed
assert all(sha(p) == h for p, h in before["protectedNonreceiptFiles"].items() if p not in allowed)
identity = before["productionIdentity"]
assert len(identity["sourceInputs"]) == 301 and len(identity["artifacts"]) == 15
assert all(sha(p) == h for p, h in identity["sourceInputs"].items())
assert all(sha(p) == h["sha256"] for p, h in identity["artifacts"].items())
history = {}
for ref, tree in before["parentTrees"].items():
    paths = {p: h for p, h in tree.items() if p.startswith("spec/performance/")}
    assert all(blob(p) == h for p, h in paths.items()), ref
    history[ref] = len(paths)
union = {
    p: sha(p)
    for tree in before["parentTrees"].values()
    for p in tree
    if p.startswith("spec/performance/")
}
path = "spec/releases/0.6.0-api-inventory.json"
old = json.loads(subprocess.check_output(["git", "show", qualified + ":" + path]))
current = json.loads((root / path).read_text())
keys = [k for k in old if old[k] != current[k]]
assert set(keys) <= {"sourceProvenance", "sourceSha256"}, keys
assert len(current["gaps"]) == 685
assert (
    subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            "7c751db1ba216005fe0f3eaf81922d44b4d01157",
            incoming,
        ],
        check=False,
    ).returncode
    == 0
)
assert (root / "spec/design/graph-interaction.md").read_text().split(
    "Primary single clicks on the painter canvas", 1
)[1] == subprocess.check_output(
    ["git", "show", qualified + ":spec/design/graph-interaction.md"], text=True
).split("Primary single clicks on the painter canvas", 1)[1]
assert (root / "spec/design/browser-wasm.md").read_text().split(
    "Trusted native clicks must target", 1
)[1].split("Exact hover/picked ref publication", 1)[0] == subprocess.check_output(
    ["git", "show", qualified + ":spec/design/browser-wasm.md"], text=True
).split("Trusted native clicks must target", 1)[1].split("Exact hover/picked ref publication", 1)[0]
patch = subprocess.check_output(
    ["git", "diff", "--binary", "--full-index", qualified, "--", ".", ":!spec/performance/**"]
)
result = {
    "qualifiedNativeRepair": qualified,
    "incomingControllerParent": incoming,
    "acceptedPropertyMainAncestor": "7c751db1ba216005fe0f3eaf81922d44b4d01157",
    "controller1091MainAccepted": False,
    "changedNonreceiptPaths": sorted(changed),
    "protectedNonreceiptFilesExact": sum(
        p not in allowed for p in before["protectedNonreceiptFiles"]
    ),
    "authorizedNamingPolicyChange": "Only exact double-quoted browser-evidence JSON tag-value match occurrence; all other matches/needles remain scanned",
    "qualifiedProductionInputsExact": 301,
    "qualifiedActualArtifactsExact": 15,
    "coreAndModuleFreshRebuildClaim": False,
    "runtimeProof": {
        "source": "graph-s5b-pointer-native-input-repair-2026-11-04",
        "browserJourneys": 69,
        "nativeWasmReplay": "fresh19 requests/17 SelectAt; full XYGR/native event oracle",
        "wireShippingTests": 26,
        "focusedContracts": 88,
        "fullUnfilteredFoundation": "passed",
        "reuse": "Exact qualified production/artifact identity, no fresh post-sync browser/build claim",
    },
    "historicalFileCountsByParent": history,
    "historicalUnionCount": len(union),
    "historicalUnionSha256": hashlib.sha256(
        json.dumps(union, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest(),
    "inventoryChangedKeys": keys,
    "gaps": 685,
    "resolvedMetadataDiffSha256": hashlib.sha256(patch).hexdigest(),
    "optimizedModule": identity["optimized"],
    "versions": identity["versions"],
}
for filename, data in [
    ("preservation-final.json", (json.dumps(result, indent=2) + "\n").encode()),
    ("resolved-metadata-and-policy.patch", patch),
]:
    dest = receipt / filename
    if dest.exists():
        assert dest.read_bytes() == data, filename
    else:
        dest.write_bytes(data)
print(json.dumps(result, indent=2))
