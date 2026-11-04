"""Verify the metadata-only parent merge against both immutable inputs."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent
BASE = "8445c238c7115c5f20e8d3541cf9b81023c47ee5"
PARENT = "cc60fd8ca93a4afca3f7d634cba55e0086a7c06f"
PRIOR = Path("spec/performance/graph-s5b-attachment-r2-2026-11-04")
NAMING = {
    "scripts/check_stale_names.py",
    "tests/test_stale_names.py",
    "spec/design/xyg-naming.md",
}
ROADMAP = "spec/design/graph-interaction.md"
INVENTORY = "spec/releases/0.6.0-api-inventory.json"
ALLOWED = NAMING | {ROADMAP, INVENTORY}


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
assert all(blob(read(p)) == parent[p] for p in NAMING)
old_roadmap = git("show", f"{BASE}:{ROADMAP}").decode()
old_row = next(line for line in old_roadmap.splitlines() if line.startswith("| S5 |"))
landing = (
    "complete-selection publication and retained progressive-layout P1 follow-up merged as #1088 "
    "at 3c665807 on 2026-11-04, with the reviewed 1,838/751-KiB package gates; "
)
new_row = old_row.replace("experimental explicit S5b", landing + "experimental explicit S5b")
assert landing in git("show", f"{PARENT}:{ROADMAP}").decode()
assert read(ROADMAP).decode() == old_roadmap.replace(old_row, new_row)
old_inventory = json.loads(git("show", f"{BASE}:{INVENTORY}"))
new_inventory = json.loads(read(INVENTORY))
old_inventory["sourceProvenance"]["baseCommit"] = BASE
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
        "roadmapOnlyAddsActual1088Landing": True,
        "inventoryOnlyRefreshesBaseCommit": True,
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
proof_files = {p: h for p, h in proof["files"].items() if p not in {ROADMAP, INVENTORY}}
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
        "metadataExceptions": [ROADMAP, INVENTORY],
        "all28OriginalLogsAndExitsPreserved": commands,
        "historicalFailuresNotRequalified": ["contracts.command.json", "rust-fmt.command.json"],
    },
)
print(
    f"PASS: {len(unchanged)} exact nonreceipt files; three exact reviewed naming imports; "
    "roadmap and provenance only; 301 production inputs; 15 actual qualified R2 artifacts; "
    f"historical counts {[(ref, value['count']) for ref, value in historical.items()]}"
)
