"""Bind exact metadata/source diffs, parent histories and qualified asset reuse."""

import gzip
import hashlib
import json
import subprocess
from pathlib import Path

root = Path.cwd()
out = Path(__file__).resolve().parent
head = "8a5922af4b33bfd67f2aefe71f613847d6fdcb08"
main = "3c66580731dde0b10a1f18465c0d0df9e73f8862"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def diff(ref, paths):
    data = subprocess.check_output(
        ["git", "diff", "--cached", "--binary", "--full-index", ref, "--", *paths]
    )
    return {"bytes": len(data), "sha256": sha(data)}


def file_record(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": sha(data)}


preservation = json.loads((out / "source-preservation.json").read_text())
artifacts = json.loads((out / "artifact-manifest.json").read_text())
for section in [
    preservation["protectedNonreceiptFiles"],
    *preservation["historicalReceipts"].values(),
]:
    for name, record in section["files"].items():
        path = root / name
        data = str(path.readlink()).encode() if path.is_symlink() else path.read_bytes()
        assert sha(data) == record["sha256"], name
for name, record in artifacts["artifacts"].items():
    assert file_record(root / name) == {key: record[key] for key in ("bytes", "sha256")}, name
commands = {}
for path in sorted(out.glob("*.json")):
    record = json.loads(path.read_text())
    if "argv" not in record:
        continue
    packed = (out / record["log"]).read_bytes()
    assert sha(packed) == record["gzipSha256"]
    assert sha(gzip.decompress(packed)) == record["rawSha256"]
    commands[path.stem] = {
        "recordSha256": sha(path.read_bytes()),
        "argv": record["argv"],
        "exitCode": record["exitCode"],
    }
required = (
    "source-proof",
    "artifact-reuse",
    "inventory-write",
    "inventory-check",
    "ownership",
    "native-declarations",
    "wasm-declarations",
    "typecheck",
    "metadata-tests",
    "hooks",
    "ruff-check",
    "ruff-format",
)
assert all(commands[name]["exitCode"] == 0 for name in required)
metadata = ["spec/design/graph-interaction.md", "spec/releases/0.6.0-api-inventory.json"]
all_paths = (
    subprocess.check_output(["git", "diff", "--cached", "--name-only", main]).decode().splitlines()
)
nonreceipt = [name for name in all_paths if not name.startswith("spec/performance/")]
assert subprocess.check_output(["git", "rev-parse", "MERGE_HEAD"]).decode().strip() == main
result = {
    "firstParent": head,
    "acceptedMainParent": main,
    "firstParentTree": subprocess.check_output(["git", "rev-parse", f"{head}^{{tree}}"])
    .decode()
    .strip(),
    "acceptedMainTree": preservation["acceptedMainTree"],
    "sourceIdentity": {
        "path": "source-preservation.json",
        **file_record(out / "source-preservation.json"),
    },
    "qualifiedArtifactReuse": {
        "path": "artifact-manifest.json",
        **file_record(out / "artifact-manifest.json"),
    },
    "metadataBinaryFullIndexDiffFrom8a": diff(head, metadata),
    "wholePrNonreceiptBinaryFullIndexDiffFromAcceptedMain": diff(main, nonreceipt),
    "metadataSources": {name: file_record(root / name) for name in metadata},
    "receiptTools": {
        p.name: file_record(p) for p in sorted(out.iterdir()) if p.suffix in (".py", ".mjs")
    },
    "commands": commands,
    "freshNativeWasmBrowserBuild": False,
    "freshBrowserRuntimeQualification": False,
    "independentReview": "Required after the final committed candidate; parent-owned, not claimed here",
}
path = out / "evidence.json"
assert not path.exists(), "append-only evidence"
path.write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {
            "status": "PASS",
            "metadataBinaryFullIndexDiffFrom8a": result["metadataBinaryFullIndexDiffFrom8a"],
            "wholePrNonreceiptBinaryFullIndexDiffFromAcceptedMain": result[
                "wholePrNonreceiptBinaryFullIndexDiffFromAcceptedMain"
            ],
        },
        indent=2,
    )
)
