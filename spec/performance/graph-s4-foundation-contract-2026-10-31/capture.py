"""Bind the harness-only ABI repair, real reports and unchanged shipping assets."""

import gzip
import hashlib
import json
import subprocess
from pathlib import Path

receipt = Path(__file__).resolve().parent
root = receipt.parents[2]
base = "93cb8570e72d9d21cb48def6679728b10396e3cc"


def command(*args: str) -> bytes:
    return subprocess.check_output(args, cwd=root)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


assert (
    command(
        "git",
        "diff",
        base,
        "--",
        "crates",
        "js",
        "packages",
        "python",
        "spec/abi",
        "spec/wasm",
        ".github",
    )
    == b""
)
names = command("git", "diff", "--name-only", base).decode().splitlines()
sources = {p: sha((root / p).read_bytes()) for p in names if not p.startswith("spec/performance/")}
prior = json.loads(
    (root / "spec/performance/graph-s4-ci-repair-2026-10-31/evidence.json").read_text()
)
for name, expected in prior["artifacts"].items():
    assert sha((root / name).read_bytes()) == expected["sha256"], name
historical = command("git", "ls-tree", "-r", base, "--", "spec/performance").decode().splitlines()
for row in historical:
    metadata, name = row.split("\t", 1)
    data = (root / name).read_bytes()
    assert (
        hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        == metadata.split()[2]
    ), name
commands = {p.name: json.loads(p.read_text()) for p in sorted(receipt.glob("*.command.json"))}
for c in commands.values():
    assert c["exitCode"] == (1 if c["name"] == "before" else 0), c
    packed = (receipt / c["log"]).read_bytes()
    raw = gzip.decompress(packed)
    assert sha(packed) == c["gzipSha256"] and sha(raw) == c["rawSha256"], c
    assert raw == (receipt / f"{c['name']}.txt").read_bytes()
selected = json.loads((receipt / "selected-report.json").read_text())
overview = json.loads((receipt / "overview-report.json").read_text())
assert selected["native"]["abi"] == 398 and selected["wasm"]["abi"] == 35
assert selected["wasm"]["scene"] == 34 and selected["wasm"]["painter"] == 17
assert overview["abi"] == {"native": 398, "wasm": 35}
record = {
    "scope": "harness-only foundation contract repair; no runtime or acceptance change",
    "parent": base,
    "sources": sources,
    "nonreceiptDiffSha256": sha(
        command("git", "diff", "--binary", "--full-index", base, "--", ".", ":!spec/performance")
    ),
    "shippingArtifactsUnchanged": prior["artifacts"],
    "historicalFilesUnchanged": len(historical),
    "commands": commands,
    "reports": {
        p.name: sha(p.read_bytes())
        for p in sorted(receipt.glob("*.json"))
        if p.name.endswith("-ci.json") or p.name in {"selected-report.json", "overview-report.json"}
    },
    "ciJobLogGzipSha256": sha((receipt / "ci-job.log.gz").read_bytes()),
    "workflowSha256": sha((root / ".github/workflows/ci.yml").read_bytes()),
    "copiedStepSha256": sha((receipt / "ci-step.sh").read_bytes()),
}
(receipt / "evidence.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps({"sources": len(sources), "commands": len(commands), "history": len(historical)}))
