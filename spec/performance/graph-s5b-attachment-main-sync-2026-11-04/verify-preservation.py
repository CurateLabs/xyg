"""Verify the metadata-only parent merge against both immutable inputs."""

import gzip
import hashlib
import json
import os
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent
BASE = "5a5da8d936112467db8e1c676c131fc67edea0c8"
PARENT = "7c751db1ba216005fe0f3eaf81922d44b4d01157"
PRIOR = Path("spec/performance/graph-s5b-attachment-r2-2026-11-04")
NAMING = {
    "scripts/check_stale_names.py",
    "tests/test_stale_names.py",
    "spec/design/xyg-naming.md",
}
ROADMAP = "spec/design/graph-interaction.md"
INVENTORY = "spec/releases/0.6.0-api-inventory.json"
BROWSER = "spec/design/browser-wasm.md"
ALLOWED = {BROWSER, ROADMAP, INVENTORY}


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
assert git("rev-parse", f"{PARENT}^{{tree}}") == git(
    "rev-parse", "68ee59f1475068d6782790a410b7da7878e0ff39^{tree}"
)
old_browser = git("show", f"{BASE}:{BROWSER}").decode()
anchor = "\nThe authored collision header at bytes 76-79 is zeroed in the painter."
landing = (
    "\nThe subsequent property-default presentation merged as #1090 at\n"
    "`7c751db1ba216005fe0f3eaf81922d44b4d01157` on 2026-11-04 at 03:26:23Z.\n"
    "Its accepted main tree is byte-exact to reviewed property head `68ee59f1`;\n"
    "the [controller main-sync receipt](../performance/graph-s5b-attachment-main-sync-2026-11-04/README.md)\n"
    "records that identity while preserving the separately reviewed R2 controller\n"
    "source. The bounded keyboard/GPU/companion attachment is implemented on this\n"
    "branch; #1091 main acceptance and broader S5b/S6/S7 acceptance remain open.\n"
)
assert old_browser.count(anchor) == 1
assert read(BROWSER).decode() == old_browser.replace(anchor, landing + anchor)
old_roadmap = git("show", f"{BASE}:{ROADMAP}").decode()
old_status = next(line for line in old_roadmap.splitlines() if line.startswith("Status: "))
new_status = (
    "Status: **S1\u2013S4 and the bounded S5a Rust GPU/result foundation are merged; "
    "property-default presentation merged as #1090 at 7c751db1 on 2026-11-04. "
    "One experimental explicit S5b keyboard/GPU/companion attachment is implemented "
    "and independently reviewed on this branch; #1091 main acceptance and broader "
    "S5b and S6/S7 acceptance remain outstanding** (see [Implementation status](#implementation-status))."
)
row_anchor = (
    "; experimental explicit S5b keyboard/GPU/companion attachment implemented below, "
    "broader S5b runtime/visual acceptance remains open |"
)
row_landing = (
    "; property-default native/WASM presentation merged as #1090 at 7c751db1 on "
    "2026-11-04, with the reviewed 1,878/765-KiB gates"
)
assert old_roadmap.count(row_anchor) == 1
assert read(ROADMAP).decode() == old_roadmap.replace(old_status, new_status).replace(
    row_anchor, row_landing + row_anchor
)
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
        "reviewedNamingFilesRemainExactToBothInputs": sorted(NAMING),
        "browserOnlyAddsActual1090Landing": True,
        "roadmapOnlyUpdatesCurrentStatusAndS5RowFor1090Landing": True,
        "controllerBoundedStatusPreserved": True,
        "inventoryOnlyRefreshesBaseCommitAndBrowserSpecBodyHash": True,
        "inventoryGaps": len(new_inventory["gaps"]),
        "acceptance": new_inventory["acceptance"],
    },
)
metadata_diff = git("diff", "--binary", "--full-index", BASE, "--", *sorted(ALLOWED))
compressed = gzip.compress(metadata_diff, mtime=0)
metadata_path = OUT / "metadata.diff.gz"
assert not metadata_path.exists()
metadata_path.write_bytes(compressed)
write(
    "metadata-diff.json",
    {
        "base": BASE,
        "argv": ["git", "diff", "--binary", "--full-index", BASE, "--", *sorted(ALLOWED)],
        "bytes": len(metadata_diff),
        "sha256": sha(metadata_diff),
        "compressedPath": str(metadata_path),
        "compressedSha256": sha(compressed),
        "compressedBytes": len(compressed),
        "nonreceiptPaths": sorted(ALLOWED),
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
        "threeMetadataExceptionsIndependentlyValidatedAgainstApprovedBase": True,
        "all28OriginalLogsAndExitsPreserved": commands,
        "historicalFailuresNotRequalified": ["contracts.command.json", "rust-fmt.command.json"],
    },
)
print(
    f"PASS: {len(unchanged)} exact nonreceipt files; reviewed naming unchanged; "
    "browser prose, roadmap and provenance only; 301 production inputs; 15 actual qualified R2 artifacts; "
    f"historical counts {[(ref, value['count']) for ref, value in historical.items()]}"
)
