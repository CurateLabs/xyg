"""Bind corrected token boundaries, rejected review and preservation evidence."""

import gzip
import hashlib
import json
import subprocess
from pathlib import Path

root = Path.cwd()
out = Path(__file__).resolve().parent
base = "47d4d6514671b12c8f263a3d640416af1983621c"
main = "3c66580731dde0b10a1f18465c0d0df9e73f8862"
paths = ["scripts/check_stale_names.py", "tests/test_stale_names.py", "spec/design/xyg-naming.md"]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_record(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": sha(data)}


def diff(ref, names):
    data = subprocess.check_output(
        ["git", "diff", "--cached", "--binary", "--full-index", ref, "--", *names]
    )
    return {"bytes": len(data), "sha256": sha(data)}


proof = json.loads((out / "preservation.json").read_text())
ledger_record = proof["verifiedFileLedger"]
ledger_bytes = (out / ledger_record["path"]).read_bytes()
assert sha(ledger_bytes) == ledger_record["gzipSha256"]
raw_ledger = gzip.decompress(ledger_bytes)
assert sha(raw_ledger) == ledger_record["rawSha256"]
for records in json.loads(raw_ledger).values():
    for record in records:
        path = root / record["path"]
        data = str(path.readlink()).encode() if path.is_symlink() else path.read_bytes()
        assert sha(data) == record["sha256"], record["path"]
for name, record in proof["artifacts"].items():
    assert file_record(root / name) == record, name
review = json.loads((out / "review-request.json").read_text())
packed_review = (out / review["log"]).read_bytes()
assert sha(packed_review) == review["gzipSha256"]
assert sha(gzip.decompress(packed_review)) == review["rawSha256"]
commands = {}
for path in sorted(out.glob("*.json")):
    record = json.loads(path.read_text())
    if "argv" not in record:
        continue
    packed = (out / record["log"]).read_bytes()
    assert sha(packed) == record["gzipSha256"]
    assert sha(gzip.decompress(packed)) == record["rawSha256"]
    commands[path.stem] = {
        "argv": record["argv"],
        "exitCode": record["exitCode"],
        "recordSha256": sha(path.read_bytes()),
    }
assert commands["guards-before"]["exitCode"] == 1
for name in (
    "guards-after",
    "focused-tests",
    "inventory-check",
    "ownership",
    "preservation-check",
    "hooks",
    "ruff-check",
    "ruff-format",
):
    assert commands[name]["exitCode"] == 0, name
all_changed = (
    subprocess.check_output(["git", "diff", "--cached", "--name-only", main]).decode().splitlines()
)
nonreceipt = [name for name in all_changed if not name.startswith("spec/performance/")]
result = {
    "base": base,
    "acceptedMain": main,
    "scope": "Explicit complete-token boundaries for the auxiliary helper allowance; no other target or runtime change",
    "sourceBinaryFullIndexDiff": diff(base, paths),
    "wholePrNonreceiptBinaryFullIndexDiff": diff(main, nonreceipt),
    "sources": {name: file_record(root / name) for name in paths},
    "receiptTools": {p.name: file_record(p) for p in sorted(out.iterdir()) if p.suffix == ".py"},
    "preservation": {"path": "preservation.json", **file_record(out / "preservation.json")},
    "rejectedReview": review,
    "commands": commands,
    "runtimeQualificationReused": True,
    "ciRetryPerformed": False,
    "independentReview": "New final review is parent-owned and required before push; not claimed here",
}
path = out / "evidence.json"
assert not path.exists(), "append-only evidence"
path.write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {
            key: result[key]
            for key in (
                "sourceBinaryFullIndexDiff",
                "wholePrNonreceiptBinaryFullIndexDiff",
                "ciRetryPerformed",
            )
        },
        indent=2,
    )
)
