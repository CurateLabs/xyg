"""Verify metadata-only continuation against both immutable local inputs."""

import gzip
import hashlib
import json
import os
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent
BASE = "9b05f31778f623a030ed96551d52ba5ae7a2196d"
PARENT = "46c2573c285075eeb03d651966b511c866bd2ffb"
PRIOR = Path("spec/performance/graph-property-default-package-2026-11-03")
ALLOWED = {
    "scripts/check_stale_names.py",
    "tests/test_stale_names.py",
    "spec/design/xyg-naming.md",
}


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


base = tree(BASE)
current = git("ls-files", "-z").decode().strip("\0").split("\0")
inputs = {
    p: oid for p, oid in base.items() if not p.startswith("spec/performance/") and p not in ALLOWED
}
assert not [p for p in current if p not in base and not p.startswith("spec/performance/")]
assert all(blob(read(p)) == oid for p, oid in inputs.items())
changed = [
    p for p, oid in base.items() if not p.startswith("spec/performance/") and blob(read(p)) != oid
]
assert set(changed) <= ALLOWED
old_inputs = json.loads((PRIOR / "build-inputs.json").read_text())
assert all(sha(read(p)) == h for p, h in old_inputs["files"].items())
artifacts = json.loads((PRIOR / "shipping-artifacts.json").read_text())
assert all(
    {"bytes": len(read(p)), "sha256": sha(read(p))} == v for p, v in artifacts["artifacts"].items()
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
assert {"bytes": len(packed), "sha256": sha(packed)} == artifacts["gzip6"]
assert len(module) <= artifacts["limits"]["raw"]
assert len(packed) <= artifacts["limits"]["gzip6"]
write(
    "source-artifact-preservation.json",
    {
        "qualified_source_commit": BASE,
        "merged_parent": PARENT,
        "merge_first_parent": git("rev-parse", "HEAD").decode().strip(),
        "proof_scope": "Every tracked nonreceipt path at qualified source except the three explicitly listed reviewed naming files; includes all production, build, toolchain, dependencies, scripts, tests and native/WASM wire declarations, plus other unchanged specs/docs. No nonreceipt paths added.",
        "allowed_reviewed_naming_paths": sorted(ALLOWED),
        "actual_changed_nonreceipt_paths": sorted(changed),
        "complete_unchanged_nonreceipt_path_count": len(inputs),
        "complete_unchanged_git_blob_manifest_sha256": sha(
            json.dumps(inputs, sort_keys=True).encode()
        ),
        "shipping_build_input_count": len(old_inputs["files"]),
        "shipping_build_source_sha256": old_inputs["source_sha256"],
        "all_shipping_inputs_exact": True,
        "all_15_shipping_artifacts_exact": artifacts["artifacts"],
        "actual_raw": {"bytes": len(module), "sha256": sha(module)},
        "actual_gzip6": {"bytes": len(packed), "sha256": sha(packed)},
        "gzip_producer": {
            "authority": "Same Node gzipSync level 6 as unchanged shipping packager",
            "versions": json.loads(
                subprocess.check_output(["node", "-p", "JSON.stringify(process.versions)"])
            ),
        },
        "limits": artifacts["limits"],
        "headroom": {
            "raw": artifacts["limits"]["raw"] - len(module),
            "gzip6": artifacts["limits"]["gzip6"] - len(packed),
        },
        "qualification": "Reuse actual 81 shipping/browser qualification preserved through 7e99 and 9b05 by exact source/artifact identity; no fresh production build or browser qualification in this naming synchronization.",
    },
)
history = {}
for ref in (BASE, PARENT):
    files = {p: oid for p, oid in tree(ref).items() if p.startswith("spec/performance/")}
    assert all(blob(read(p)) == oid for p, oid in files.items())
    history[ref] = {
        "historical_file_count": len(files),
        "git_blob_manifest_sha256": sha(json.dumps(files, sort_keys=True).encode()),
        "every_file_byte_exact": True,
    }
write("historical-preservation.json", history)
labels = (
    "native-build",
    "wasm-build",
    "client-build",
    "shipping-package",
    "shipping-tests",
    "paired-assets",
    "foundation",
    "inline-file-smoke",
    "property-python",
    "property-browser",
    "preservation",
    "scoped-crosshost-python",
    "scoped-crosshost-node",
    "focused-package-contracts",
    "native-abi-smoke",
)
reused = {}
for label in labels:
    record = json.loads((PRIOR / f"{label}.command.json").read_text())
    assert record["exit"] == 0
    raw = gzip.decompress((PRIOR / f"{label}.log.gz").read_bytes())
    assert sha(raw) == record["log_sha256"]
    reused[label] = {
        "record": str(PRIOR / f"{label}.command.json"),
        "argv": record["argv"],
        "exit": record["exit"],
        "log_sha256": sha(raw),
    }
write(
    "reused-qualification.json",
    {
        "source_and_artifact_identity_required": True,
        "all_prior_logs_integrity_verified": True,
        "commands": reused,
    },
)
flags = (
    "--no-color",
    "--no-ext-diff",
    "--no-textconv",
    "--binary",
    "--full-index",
    "--src-prefix=a/",
    "--dst-prefix=b/",
)
whole = sha(git("diff", *flags, "3c66580731dde0b10a1f18465c0d0df9e73f8862", PARENT))
previous = git("rev-parse", PARENT + "^").decode().strip()
source_increment = sha(git("diff", *flags, previous, PARENT, "--", ".", ":!spec/performance/**"))
assert whole == "7b27d371c25bbacc3199720a912c1b9075b80486a80e78c9fadb3966d2285812"
assert source_increment == "d3b8328ae10ff053a557a05aa65fb1799f404ec62c544653207eb24f3fb0c19d"
write(
    "parent-review.json",
    {
        "reviewer_reported_by_parent": "s5a_final_review",
        "reviewed_commit": PARENT,
        "disposition_reported_by_parent": "APPROVED corrected complete-token boundaries; no blockers",
        "verified_whole_pr_vs_accepted_main_sha256": whole,
        "initial_repair_commit": previous,
        "verified_final_source_increment_vs_initial_repair_sha256": source_increment,
        "current_integrated_review": "New independent parent review required; no self-approval or CI acceptance claimed",
    },
)
imported = {}
for path in sorted(ALLOWED):
    data = read(path)
    assert data == git("show", f"{PARENT}:{path}")
    imported[path] = {"bytes": len(data), "sha256": sha(data), "git_blob": blob(data)}
assert set(changed) == ALLOWED
snapshot = "spec/releases/0.6.0-api-inventory.json"
assert read(snapshot) == git("show", f"{BASE}:{snapshot}")
inventory = json.loads(read(snapshot))
assert len(inventory["gaps"]) == 685
assert inventory["contracts"]["cAbi"]["abiVersion"] == 399
assert len(inventory["contracts"]["cAbi"]["symbols"]) == 538
helper = "tests/browser/graph_property_default_export.mjs"
assert read(helper) == git("show", f"{BASE}:{helper}")
write(
    "reviewed-import.json",
    {
        "exact_imported_files": imported,
        "entire_inventory_byte_exact_9b05": True,
        "explicit_gaps": len(inventory["gaps"]),
        "acceptance": inventory["acceptance"],
        "property_helper": {
            "bytes": len(read(helper)),
            "sha256": sha(read(helper)),
            "entire_file_exact_9b05": True,
        },
        "other_metadata_changes": [],
        "nonreceipt_merge_increment_vs_9b05_sha256": sha(
            git("diff", *flags, BASE, "--", ".", ":!spec/performance/**")
        ),
    },
)
print(
    f"PASS: {len(inputs)} protected files, {len(old_inputs['files'])} shipping inputs, 15 artifacts; reviewed imports and both historical sets exact"
)
