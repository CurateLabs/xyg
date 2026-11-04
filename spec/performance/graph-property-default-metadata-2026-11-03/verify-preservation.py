"""Verify metadata-only continuation against both immutable local inputs."""

import gzip
import hashlib
import json
import os
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent
BASE = "81c9f7f170f448e7b8b98e2bd1cd613ee56f38f1"
PARENT = "8a5922af4b33bfd67f2aefe71f613847d6fdcb08"
PRIOR = Path("spec/performance/graph-property-default-package-2026-11-03")
ALLOWED = {
    "spec/design/graph-interaction.md",
    "spec/design/ownership-audit.json",
    "spec/design/ownership-audit.md",
    "spec/releases/0.6.0-api-inventory.json",
    "spec/releases/api-inventory.md",
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
        "merge_commit": git("rev-parse", "HEAD").decode().strip(),
        "proof_scope": "Every tracked nonreceipt path at qualified source except the five explicitly listed metadata paths; includes all production, build, toolchain, dependencies, scripts, tests and native/WASM wire declarations, plus other unchanged specs/docs. No nonreceipt paths added.",
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
        "qualification": "Reuse exact 81 production/paired-assets/inline/shipping/foundation/property/scoped-preservation evidence; no production rebuild or browser rerun in this metadata continuation.",
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
whole = sha(git("diff", *flags, "78b4b69f76b955ab19bd365f0492711cc3c06c1f", PARENT))
nonreceipt = sha(
    git(
        "diff",
        *flags,
        "78b4b69f76b955ab19bd365f0492711cc3c06c1f",
        PARENT,
        "--",
        ".",
        ":!spec/performance/**",
    )
)
assert whole == "1b8142d54f6b1178a0f15c26dc74e864c7d65969d59ecdcafb1cef9e330b4613"
assert nonreceipt == "0941542d96987bdb97372d77f9be72c56ba446b637943cb646f2943f4679a0c7"
write(
    "parent-review.json",
    {
        "reviewer_reported_by_parent": "s5a_final_review",
        "reviewed_commit": PARENT,
        "disposition_reported_by_parent": "APPROVED",
        "verified_whole_increment_vs_78_sha256": whole,
        "verified_nonreceipt_increment_vs_78_sha256": nonreceipt,
        "current_integrated_review": "Pending new independent parent review; implementer does not approve final integrated diff.",
    },
)
print(
    f"PASS: {len(inputs)} complete nonreceipt paths, {len(old_inputs['files'])} shipping inputs, {len(artifacts['artifacts'])} artifacts; all historical receipts from both inputs exact"
)
