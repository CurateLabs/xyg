"""Verify metadata-only continuation against both immutable local inputs."""

import gzip
import hashlib
import json
import os
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent
BASE = "7e99ec5da586572d411996599cf37f25dc5566c7"
PARENT = "909dfe303b4f18f4b6332d9a4c13d68b7d2c3e74"
PRIOR = Path("spec/performance/graph-property-default-package-2026-11-03")
ALLOWED = {
    "spec/design/graph-interaction.md",
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
        "qualification": "Reuse actual 81 production/paired-assets/inline/shipping/foundation/property/scoped-preservation qualification, preserved and independently reviewed at 7e99. No fresh production build or browser qualification in this parent synchronization.",
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
nonreceipt = sha(
    git(
        "diff",
        *flags,
        "3c66580731dde0b10a1f18465c0d0df9e73f8862",
        PARENT,
        "--",
        ".",
        ":!spec/performance/**",
    )
)
assert whole == "c28d535efe848bbf95995674b165653644bc4c7055a7c5710ee662ca1212bc4b"
assert nonreceipt == "50f33afee6481e6db3c018ad00cf59bc0126028acc0ed39f80c783e2c7ea5ecc"
write(
    "parent-review.json",
    {
        "reviewer_reported_by_parent": "s5a_final_review",
        "reviewed_commit": PARENT,
        "disposition_reported_by_parent": "APPROVED",
        "verified_whole_pr_vs_accepted_main_sha256": whole,
        "verified_nonreceipt_pr_vs_accepted_main_sha256": nonreceipt,
        "current_integrated_review": "Pending new independent parent review; implementer does not approve final integrated diff.",
    },
)
print(
    f"PASS: {len(inputs)} complete nonreceipt paths, {len(old_inputs['files'])} shipping inputs, {len(artifacts['artifacts'])} artifacts; all historical receipts from both inputs exact"
)

# Inventory resolution changes only generation-time base provenance.
snapshot = "spec/releases/0.6.0-api-inventory.json"
before = json.loads(git("show", f"{BASE}:{snapshot}"))
after = json.loads(read(snapshot))
old_provenance = before["sourceProvenance"].pop("baseCommit")
new_provenance = after["sourceProvenance"].pop("baseCommit")
assert before == after
assert new_provenance == BASE
assert len(after["gaps"]) == 685
assert after["contracts"]["cAbi"]["abiVersion"] == 399
assert len(after["contracts"]["cAbi"]["symbols"]) == 538
accepted_main = "3c66580731dde0b10a1f18465c0d0df9e73f8862"
reviewed_main = "60cee1e58bc93766b954d7343b90ec19d676a8de"
assert git("rev-parse", accepted_main + "^{tree}") == git("rev-parse", reviewed_main + "^{tree}")
helper = "tests/browser/graph_property_default_export.mjs"
helper_bytes = read(helper)
assert helper_bytes == git("show", f"{BASE}:{helper}")
metadata_diff = git("diff", *flags, BASE, "--", ".", ":!spec/performance/**")
write(
    "metadata-resolution.json",
    {
        "conflict": "Only inventory sourceProvenance.baseCommit; retained full ABI399 property contract and regenerated with unchanged inspector",
        "inventory_before_base": old_provenance,
        "inventory_after_base": new_provenance,
        "all_other_snapshot_fields_exact_7e99": True,
        "explicit_review_gaps": len(after["gaps"]),
        "acceptance": after["acceptance"],
        "ownership_metadata_and_classifications_exact_7e99": True,
        "property_presentation_specs_exact_7e99": True,
        "property_helper": {
            "bytes": len(helper_bytes),
            "sha256": sha(helper_bytes),
            "complete_bytes_exact_7e99": True,
        },
        "accepted_main": accepted_main,
        "accepted_main_tree": git("rev-parse", accepted_main + "^{tree}").decode().strip(),
        "accepted_main_tree_exact_reviewed_60cee": True,
        "parent_parents": git("show", "-s", "--format=%P", PARENT).decode().strip().split(),
        "merge_metadata_nonreceipt_diff_vs_7e99_sha256": sha(metadata_diff),
        "parent_reported_property_review": "m4_defaults_audit APPROVED 7e99; Greptile 5/5 no findings; prior PR rollup complete with applicable successes and normal conditional/disabled skips",
        "current_candidate_review": "New independent parent review required; no actual #1089 or #1090 main acceptance claimed",
    },
)
