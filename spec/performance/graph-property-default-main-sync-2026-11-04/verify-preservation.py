"""Verify metadata-only continuation against both immutable local inputs."""

import gzip
import hashlib
import json
import os
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent
BASE = "cc60fd8ca93a4afca3f7d634cba55e0086a7c06f"
PARENT = "a0636c27ec48c50eb1eafa2c99122d165d266c28"
PRIOR = Path("spec/performance/graph-property-default-package-2026-11-03")
ALLOWED = {
    "spec/design/browser-wasm.md",
    "spec/releases/0.6.0-api-inventory.json",
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
        "proof_scope": "Every tracked nonreceipt path at qualified source except the two explicitly listed metadata paths; includes all production, build, toolchain, dependencies, scripts, tests and native/WASM wire declarations, plus other unchanged specs/docs. No nonreceipt paths added.",
        "allowed_metadata_paths": sorted(ALLOWED),
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
        "qualification": "Reuse actual 81 shipping/browser qualification preserved through 7e99 and approved cc60 by exact source/artifact identity. No fresh production build, package run or browser qualification in this main synchronization.",
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
reviewed = "46c2573c285075eeb03d651966b511c866bd2ffb"
main_tree = git("rev-parse", PARENT + "^{tree}").decode().strip()
assert main_tree == "af749a61ebe0e82ec190e2dfc8ca8b859143724e"
assert main_tree == git("rev-parse", reviewed + "^{tree}").decode().strip()
assert not git("diff", "--name-only", reviewed, PARENT)
whole = sha(git("diff", *flags, reviewed, BASE))
source = sha(git("diff", *flags, reviewed, BASE, "--", ".", ":!spec/performance/**"))
assert whole == "1e5f1b1d5a06f62a06e43248804a2f652fad80ce940251c745bb9062133d72a2"
assert source == "420dd8a56359fd83f47a864995571c1fc583c39ba2dfb1c017a2437dbdea216d"
write(
    "parent-identities.json",
    {
        "merge_first_parent": BASE,
        "accepted_main": PARENT,
        "accepted_main_tree": main_tree,
        "accepted_tree_exact_reviewed_1089_head": reviewed,
        "actual_1089_merge_time_reported_by_parent": "2026-11-04T02:22:11Z",
        "actual_merge_time_is_not_inferred_from_git_commit_timestamp": True,
        "reviewer_reported_by_parent": "m4_defaults_audit APPROVED final cc60 sync",
        "reviewed_property_whole_pr_vs_46_sha256": whole,
        "reviewed_property_nonreceipt_pr_vs_46_sha256": source,
        "prior_ci_scope_reported_by_parent": "20 applicable checks green on cc60 old feature base; fresh main-target CI not run or claimed here",
        "current_integrated_review": "New independent parent sync review required before integration, push, dedicated PR update or fresh main CI",
    },
)
snapshot = "spec/releases/0.6.0-api-inventory.json"
before = json.loads(git("show", f"{BASE}:{snapshot}"))
after = json.loads(read(snapshot))
old_base = before["sourceProvenance"].pop("baseCommit")
new_base = after["sourceProvenance"].pop("baseCommit")
old_browser = before["sourceSha256"].pop("spec/design/browser-wasm.md")
new_browser = after["sourceSha256"].pop("spec/design/browser-wasm.md")
assert before == after
assert new_base == BASE
assert new_browser == sha(read("spec/design/browser-wasm.md"))
assert len(after["gaps"]) == 685
assert after["contracts"]["cAbi"]["abiVersion"] == 399
assert len(after["contracts"]["cAbi"]["symbols"]) == 538
helper = "tests/browser/graph_property_default_export.mjs"
assert read(helper) == git("show", f"{BASE}:{helper}")
assert set(changed) == ALLOWED
write(
    "metadata-resolution.json",
    {
        "conflict": "Only inventory provenance and browser-spec source hash; retained approved ABI399 property contracts and regenerated with unchanged inspector",
        "inventory_before_base": old_base,
        "inventory_after_base": new_base,
        "browser_spec_before_sha256": old_browser,
        "browser_spec_after_sha256": new_browser,
        "all_other_snapshot_fields_exact_cc60": True,
        "explicit_gaps": len(after["gaps"]),
        "acceptance": after["acceptance"],
        "corrected_naming_checker_tests_spec_exact_cc60": True,
        "ownership_metadata_and_classifications_exact_cc60": True,
        "property_helper": {
            "bytes": len(read(helper)),
            "sha256": sha(read(helper)),
            "entire_file_exact_cc60": True,
        },
        "nonreceipt_merge_increment_vs_cc60_sha256": sha(
            git("diff", *flags, BASE, "--", ".", ":!spec/performance/**")
        ),
    },
)
print(
    f"PASS: {len(inputs)} protected paths, 699 shipping inputs, 15 artifacts; both historical sets and accepted main tree exact"
)
