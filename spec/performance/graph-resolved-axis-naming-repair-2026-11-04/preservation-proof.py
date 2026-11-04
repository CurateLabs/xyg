"""Verify narrow rule/test changes, immutable history and qualified runtime reuse."""

import ast
import gzip
import hashlib
import json
import subprocess
from pathlib import Path

root = Path.cwd()
out = Path(__file__).resolve().parent
base = "909dfe303b4f18f4b6332d9a4c13d68b7d2c3e74"
allowed = {"scripts/check_stale_names.py", "tests/test_stale_names.py", "spec/design/xyg-naming.md"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args])


protected = []
history = []
for entry in git("ls-tree", "-rz", base).split(b"\0"):
    if not entry:
        continue
    meta, raw_name = entry.split(b"\t", 1)
    mode, kind, blob = meta.decode().split()
    name = raw_name.decode()
    assert kind == "blob"
    if name in allowed:
        continue
    path = root / name
    data = str(path.readlink()).encode() if path.is_symlink() else path.read_bytes()
    assert hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest() == blob, name
    record = {"path": name, "blob": blob, "sha256": sha(data), "bytes": len(data), "mode": mode}
    (history if name.startswith("spec/performance/") else protected).append(record)
# The inspector does not include this naming document/checker among its inputs.
# Keep the complete preparation snapshot exact, including provenance and gaps.
inventory = json.loads((root / "spec/releases/0.6.0-api-inventory.json").read_text())
assert len(inventory["gaps"]) == 685
assert inventory["acceptance"] == "preparation-only-not-a-freeze"
# Every existing test/helper body remains unchanged; only imports/new cases add.
test_path = "tests/test_stale_names.py"
old_tests = ast.parse(git("show", f"{base}:{test_path}"))
new_tests = ast.parse((root / test_path).read_bytes())
new_functions = {node.name: node for node in new_tests.body if isinstance(node, ast.FunctionDef)}
existing_tests = 0
for node in old_tests.body:
    if isinstance(node, ast.FunctionDef):
        assert ast.dump(node) == ast.dump(new_functions[node.name]), node.name
        existing_tests += node.name.startswith("test_")
checker_path = "scripts/check_stale_names.py"
old_checker = ast.parse(git("show", f"{base}:{checker_path}"))
new_checker = ast.parse((root / checker_path).read_bytes())
assert len(old_checker.body) == len(new_checker.body)
for old, new in zip(old_checker.body, new_checker.body, strict=True):
    if isinstance(old, ast.FunctionDef) and old.name == "_allowed_src_lib_rs":
        assert ast.dump(old.body[0]) == ast.dump(new.body[0])
        assert ast.dump(old.body[-1]) == ast.dump(new.body[-1])
    else:
        assert ast.dump(old) == ast.dump(new)
qualified_path = (
    root / "spec/performance/graph-resolved-axis-main-sync-2026-11-04/artifact-manifest.json"
)
qualified = json.loads(qualified_path.read_text())
artifacts = {}
for name, record in qualified["artifacts"].items():
    data = (root / name).read_bytes()
    assert len(data) == record["bytes"] and sha(data) == record["sha256"], name
    artifacts[name] = {"bytes": len(data), "sha256": sha(data)}
ledger = json.dumps({"protected": protected, "history": history}, sort_keys=True).encode()
ledger_path = out / "verified-files.json.gz"
assert not ledger_path.exists()
ledger_path.write_bytes(gzip.compress(ledger, mtime=0))
result = {
    "base": base,
    "intendedChangedPaths": sorted(allowed),
    "protectedNonreceiptFiles": len(protected),
    "historicalReceiptFiles": len(history),
    "verifiedFileLedger": {
        "path": ledger_path.name,
        "rawSha256": sha(ledger),
        "gzipSha256": sha(ledger_path.read_bytes()),
    },
    "allPreexistingReceiptsByteExact": True,
    "existingTestBodiesUnchanged": existing_tests,
    "checkerOtherFunctionsAndTargetsExact": True,
    "checkerPreviousPrefixAndReturnExact": True,
    "inventorySnapshotByteExact": True,
    "inventoryReviewGaps": len(inventory["gaps"]),
    "qualifiedArtifactManifest": {
        "path": str(qualified_path.relative_to(root)),
        "sha256": sha(qualified_path.read_bytes()),
    },
    "artifacts": artifacts,
    "module": qualified["module"],
    "runtimeBuildOrQualificationRerun": False,
}
path = out / "preservation.json"
assert not path.exists()
path.write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {
            key: result[key]
            for key in (
                "protectedNonreceiptFiles",
                "historicalReceiptFiles",
                "existingTestBodiesUnchanged",
                "inventoryReviewGaps",
                "runtimeBuildOrQualificationRerun",
            )
        },
        indent=2,
    )
)
