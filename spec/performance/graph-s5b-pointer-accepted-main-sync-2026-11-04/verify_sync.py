"""Prove accepted-main squash-history sync preserves approved pointer bytes."""

import hashlib
import json
import subprocess
from pathlib import Path

receipt = Path(__file__).resolve().parent
root = receipt.parents[2]
before = json.loads((receipt / "before-sync.json").read_text())
qualified, incoming = before["parents"]
allowed = {
    "spec/design/graph-interaction.md",
    "spec/design/browser-wasm.md",
    "spec/releases/0.6.0-api-inventory.json",
}


def sha(path):
    return hashlib.sha256((root / path).read_bytes()).hexdigest()


def git_blob(path):
    data = (root / path).read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def committed(ref, path):
    return subprocess.check_output(["git", "show", ref + ":" + path])


changed = set(
    subprocess.check_output(
        ["git", "diff", "--name-only", qualified, "--", ".", ":!spec/performance/**"], text=True
    ).splitlines()
)
assert changed == allowed, changed
protected = {p: h for p, h in before["nonreceiptSha256"].items() if p not in allowed}
assert all(sha(p) == h for p, h in protected.items())
for ref in [incoming, before["reviewedController"]]:
    assert (
        subprocess.check_output(["git", "rev-parse", ref + "^{tree}"], text=True).strip()
        == "4cde4a0ea4f24125d5c2bdafc2c1bde72cd263eb"
    )
identity = before["qualifiedIdentity"]
assert len(identity["sourceInputs"]) == 301 and len(identity["artifacts"]) == 15
assert all(sha(p) == h for p, h in identity["sourceInputs"].items())
assert all(
    sha(p) == h["sha256"] and (root / p).stat().st_size == h["bytes"]
    for p, h in identity["artifacts"].items()
)
optimized = json.loads(
    subprocess.check_output(
        [
            "node",
            "--input-type=module",
            "-e",
            'import{readFileSync}from"node:fs";import{gzipSync}from"node:zlib";'
            'import{createHash}from"node:crypto";'
            'const b=readFileSync("packages/xy-client/dist/xyg-wasm.wasm"),g=gzipSync(b,{level:6});'
            'console.log(JSON.stringify({bytes:b.length,gzip6:g.length,sha256:createHash("sha256").update(b).digest("hex"),gzip6Sha256:createHash("sha256").update(g).digest("hex")}))',
        ],
        text=True,
    )
)
assert all(identity["optimized"][k] == v for k, v in optimized.items())
history_counts, union = {}, {}
for ref, tree in before["parentTrees"].items():
    history = {p: h for p, h in tree.items() if p.startswith("spec/performance/")}
    assert all(git_blob(p) == h for p, h in history.items()), ref
    history_counts[ref] = len(history)
    union.update({p: sha(p) for p in history})
inventory_path = "spec/releases/0.6.0-api-inventory.json"
old, inventory = (
    json.loads(committed(qualified, inventory_path)),
    json.loads((root / inventory_path).read_text()),
)
changed_keys = [k for k in old if old[k] != inventory[k]]
assert set(changed_keys) <= {"sourceProvenance", "sourceSha256"}, changed_keys
assert len(inventory["gaps"]) == 685
# Whitelist the complete actual status-prose changes, never product contracts.
expected_graph = (
    committed(qualified, "spec/design/graph-interaction.md")
    .decode()
    .replace(
        "is implemented on this branch; final native-input repair review, #1091 main acceptance and broader S5b and S6/S7 acceptance remain outstanding",
        "is implemented and independently reviewed on this branch; its base keyboard/GPU/companion attachment merged as #1091 at d6fcacfd on 2026-11-04 at 04:35:11Z. #1092 main acceptance, final accepted-main sync review and broader S5b and S6/S7 acceptance remain outstanding",
    )
    .replace(
        "experimental explicit S5b primary-click/keyboard/GPU/companion attachment implemented below, broader S5b runtime/visual acceptance remains open |",
        "base explicit keyboard/GPU/companion attachment merged as #1091 at d6fcacfd on 2026-11-04 at 04:35:11Z; experimental explicit S5b primary-click/keyboard/GPU/companion attachment implemented and independently reviewed below, #1092 main acceptance and broader S5b runtime/visual acceptance remain open |",
    )
)
assert (root / "spec/design/graph-interaction.md").read_text() == expected_graph
expected_browser = (
    committed(qualified, "spec/design/browser-wasm.md")
    .decode()
    .replace(
        "source. The bounded primary-click/keyboard/GPU/companion attachment is implemented\non this branch; final native-input repair review, #1091 main acceptance and\nbroader S5b/S6/S7 acceptance remain open.",
        """source. That base explicit keyboard/GPU/companion attachment merged through
main's queue as #1091 at `d6fcacfd482d425a731c5b1ebd492e32dc8a15b4` on
2026-11-04 at 04:35:11Z. Its entire accepted tree is byte-exact to reviewed
controller head `c3013b30`; the [pointer accepted-main sync receipt](../performance/graph-s5b-pointer-accepted-main-sync-2026-11-04/README.md)
records the normal squash-history merge while preserving the separately
reviewed native-input pointer source and qualified runtime evidence. The bounded
primary-click/keyboard/GPU/companion attachment is implemented and independently
reviewed on this branch; #1092 main acceptance, final accepted-main sync review
and broader S5b/S6/S7 acceptance remain open.""",
    )
)
assert (root / "spec/design/browser-wasm.md").read_text() == expected_browser
patch = subprocess.check_output(
    ["git", "diff", "--binary", "--full-index", qualified, "--", ".", ":!spec/performance/**"]
)
result = {
    "parents": before["parents"],
    "acceptedMainEqualsReviewedController": before["reviewedController"],
    "entireAcceptedTree": before["acceptedMainTree"],
    "landing": {"pr": 1091, "time": "2026-11-04T04:35:11Z", "commit": incoming},
    "changedNonreceiptPaths": sorted(changed),
    "protectedNonreceiptFilesByteExact": len(protected),
    "currentContractChange": False,
    "classificationOrCapabilityOrNamingPolicyChange": False,
    "inventoryChangedKeys": changed_keys,
    "preparationGaps": 685,
    "freezeAccepted": False,
    "qualifiedProductionInputsByteExact": 301,
    "qualifiedActualArtifactsByteExact": 15,
    "actualArtifacts": identity["artifacts"],
    "optimized": {
        **optimized,
        "limits": identity["optimized"]["limits"],
        "headroom": identity["optimized"]["headroom"],
    },
    "versions": identity["versions"],
    "historyFilesByParent": history_counts,
    "historicalUnionCount": len(union),
    "historicalUnionSha256": hashlib.sha256(
        json.dumps(union, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest(),
    "resolvedStatusAndInventoryPatchSha256": hashlib.sha256(patch).hexdigest(),
    "proofReuse": {
        "source": "graph-s5b-pointer-native-input-repair-2026-11-04",
        "browserJourneys": 69,
        "freshNativeCoordinateCapturedRequests": 19,
        "selectAt": 17,
        "completeNativeWasmBrowserXygrParity": True,
        "wireShippingTests": 26,
        "focusedContracts": 88,
        "fullUnfilteredFoundation": "passed",
        "condition": "exact approved production/helper/test source and actual artifact identity",
        "freshRuntimeBuildOrBrowserRerunClaim": False,
    },
    "pending": [
        "parent independent final sync review",
        "pre-push hooks",
        "#1092 main acceptance",
        "broader #35/#36/M4/#108 and S5b/S6/S7",
    ],
}
for name, data in [
    ("preservation.json", (json.dumps(result, indent=2) + "\n").encode()),
    ("resolved-status-inventory.patch", patch),
    ("history-union-sha256.json", (json.dumps(union, indent=2) + "\n").encode()),
]:
    path = receipt / name
    if path.exists():
        assert path.read_bytes() == data, name
    else:
        path.write_bytes(data)
print(json.dumps(result, indent=2))
