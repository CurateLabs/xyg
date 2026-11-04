"""Verify the metadata-only parent merge against both immutable inputs."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent
BASE = "11e2aa4defd76c6d5f6aeaa40ecf4af806c33d38"
PARENT = "68ee59f1475068d6782790a410b7da7878e0ff39"
PRIOR = Path("spec/performance/graph-s5b-attachment-r2-2026-11-04")
NAMING = {
    "scripts/check_stale_names.py",
    "tests/test_stale_names.py",
    "spec/design/xyg-naming.md",
}
ROADMAP = "spec/design/graph-interaction.md"
INVENTORY = "spec/releases/0.6.0-api-inventory.json"
BROWSER = "spec/design/browser-wasm.md"
ALLOWED = {BROWSER, INVENTORY}


def git(*args):
    return subprocess.check_output(["git", *args])


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    p = Path(path)
    return os.readlink(p).encode() if p.is_symlink() else p.read_bytes()


def tree(ref):
    result = {}
    for row in git("ls-tree", "-rz", ref).split(b"\0"):
        if row:
            meta, path = row.split(b"\t", 1)
            result[path.decode()] = meta.split()[2].decode()
    return result


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def write(name, value):
    p = OUT / name
    assert not p.exists(), f"append-only receipt: {p}"
    p.write_text(json.dumps(value, indent=2) + "\n")


base, parent = tree(BASE), tree(PARENT)
current = git("ls-files", "-z").decode().strip("\0").split("\0")
unchanged = {
    p: oid for p, oid in base.items() if not p.startswith("spec/performance/") and p not in ALLOWED
}
assert not [p for p in current if p not in base and not p.startswith("spec/performance/")]
assert all(blob(read(p)) == oid for p, oid in unchanged.items())
changed = {
    p: sha(read(p))
    for p, oid in base.items()
    if not p.startswith("spec/performance/") and blob(read(p)) != oid
}
assert set(changed) == ALLOWED
assert all(blob(read(p)) == parent[p] == base[p] for p in NAMING)
old_browser = git("show", f"{BASE}:{BROWSER}").decode()
old_paragraph = (
    "not asserted. Native property-graph initial home-view, caption and theme\n"
    "failures remain separately owned by #935. The [consumer repair receipt]"
)
new_paragraph = (
    "not asserted. The #1089 consumer receipts retain the historical native\n"
    "property-graph initial home-view, caption and theme failures. The subsequent\n"
    "[property-default qualification](../performance/graph-property-default-package-2026-11-03/README.md)\n"
    "records all six unmasked image pairs passing for the current property source;\n"
    "broader #935 intent/digest/safe-pair scope remains open. The [consumer repair receipt]"
)
parent_browser = git("show", f"{PARENT}:{BROWSER}").decode()
assert new_paragraph in parent_browser
landing_start = parent_browser.index(
    "The resolved Scene plot/axis and live CSS repairs merged as #1089 at\n"
)
landing_end = parent_browser.index("\n\n", landing_start)
landing = parent_browser[landing_start:landing_end]
assert "a0636c27ec48c50eb1eafa2c99122d165d266c28" in landing
assert "02:22:11Z" in landing
assert landing.endswith("S5b controller acceptance remains planned.")
landing = landing.replace(
    "presentation source. S5b controller acceptance remains planned.",
    "presentation source. The bounded experimental S5b keyboard/GPU/companion\n"
    "attachment is implemented above; broader S5b runtime/visual acceptance remains open.",
)
anchor = "The authored collision header at bytes 76-79 is zeroed in the painter."
assert old_browser.count(old_paragraph) == old_browser.count(anchor) == 1
expected_browser = old_browser.replace(old_paragraph, new_paragraph).replace(
    anchor, landing + "\n\n" + anchor
)
assert read(BROWSER).decode() == expected_browser
old_inventory = json.loads(git("show", f"{BASE}:{INVENTORY}"))
new_inventory = json.loads(read(INVENTORY))
old_inventory["sourceProvenance"]["baseCommit"] = BASE
old_inventory["sourceSha256"][BROWSER] = sha(read(BROWSER))
assert old_inventory == new_inventory
assert len(new_inventory["gaps"]) == 685
assert new_inventory["acceptance"] == "preparation-only-not-a-freeze"
write(
    "approved-source-preservation.json",
    {
        "approved": BASE,
        "parent": PARENT,
        "unchangedNonreceiptCount": len(unchanged),
        "unchangedNonreceiptGitBlobs": unchanged,
        "changedNonreceiptSha256": changed,
        "exactParentNamingImports": sorted(NAMING),
        "browserOnlyAddsHistoricalFailureClarificationAndActual1089Landing": True,
        "controllerBoundedStatusPreserved": True,
        "inventoryOnlyRefreshesBaseCommitAndBrowserSpecBodyHash": True,
        "inventoryGaps": len(new_inventory["gaps"]),
        "acceptance": new_inventory["acceptance"],
    },
)
historical = {}
for ref, entries in ((BASE, base), (PARENT, parent)):
    receipts = {p: oid for p, oid in entries.items() if p.startswith("spec/performance/")}
    assert all(blob(read(p)) == oid for p, oid in receipts.items())
    historical[ref] = {"count": len(receipts), "gitBlobs": receipts}
write("historical-preservation.json", historical)
qualified = json.loads((PRIOR / "artifacts.json").read_text())
assert len(qualified["sourceInputs"]) == 301
assert all(sha(read(p)) == value for p, value in qualified["sourceInputs"].items())
assert len(qualified["artifacts"]) == 15
assert all(
    {"bytes": len(read(p)), "sha256": sha(read(p))} == value
    for p, value in qualified["artifacts"].items()
)
module = read("packages/xy-client/dist/xyg-wasm.wasm")
packed = subprocess.check_output(
    [
        "node",
        "--input-type=module",
        "-e",
        'import {readFileSync} from "node:fs"; import {gzipSync} from "node:zlib"; '
        'process.stdout.write(gzipSync(readFileSync("packages/xy-client/dist/xyg-wasm.wasm"), {level:6}));',
    ]
)
optimized = qualified["optimized"]
assert len(module) == optimized["bytes"] and sha(module) == optimized["sha256"]
assert len(packed) == optimized["gzip6"] and sha(packed) == optimized["gzip6Sha256"]
assert packed == (PRIOR / "shipping-module.wasm.gz").read_bytes()
assert optimized["limits"] == {"raw": 1923072, "gzip6": 783360}
write(
    "source-artifact-preservation.json",
    {
        "qualification": str(PRIOR),
        "qualificationManifestSha256": sha((PRIOR / "artifacts.json").read_bytes()),
        "reuseOnlyNoFreshBuildPackageOrBrowserClaim": True,
        "sourceInputs": qualified["sourceInputs"],
        "sourceSha256": qualified["sourceSha256"],
        "artifacts": qualified["artifacts"],
        "optimized": optimized,
        "versions": qualified["versions"],
    },
)
proof = json.loads((PRIOR / "proof-inputs.json").read_text())
proof_files = {p: h for p, h in proof["files"].items() if p not in {ROADMAP, INVENTORY, BROWSER}}
assert len(proof["files"]) == 27
assert all(sha(read(p)) == value for p, value in proof_files.items())
commands = {}
for name, value in proof["commands"].items():
    record_bytes = (PRIOR / name).read_bytes()
    record = json.loads(record_bytes)
    log = PRIOR / name.replace(".command.json", ".log")
    assert sha(record_bytes) == value["recordSha256"]
    assert sha(log.read_bytes()) == value["logSha256"] == record["log_sha256"]
    assert record["exit"] == value["exit"]
    commands[name] = {**value, "argv": record["argv"]}
assert len(commands) == 28
write(
    "reused-qualification.json",
    {
        "qualification": str(PRIOR),
        "reuseOnly": True,
        "unchangedProofFiles": proof_files,
        "metadataExceptions": [ROADMAP, INVENTORY, BROWSER],
        "roadmapMetadataExceptionWasAlreadyPresentInApproved11e2": True,
        "all28OriginalLogsAndExitsPreserved": commands,
        "historicalFailuresNotRequalified": ["contracts.command.json", "rust-fmt.command.json"],
    },
)
print(
    f"PASS: {len(unchanged)} exact nonreceipt files; three exact reviewed naming imports; "
    "browser prose and provenance only; 301 production inputs; 15 actual qualified R2 artifacts; "
    f"historical counts {[(ref, value['count']) for ref, value in historical.items()]}"
)
