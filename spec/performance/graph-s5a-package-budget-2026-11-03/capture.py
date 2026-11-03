"""Bind the explicit package decision to actual source, assets and raw evidence."""

import gzip
import hashlib
import json
import subprocess
from pathlib import Path

receipt = Path(__file__).resolve().parent
root = receipt.parents[2]
base = "030c79062138bb8287df2dc93ab6fdc0ecc8747b"


def command(*argv):
    return subprocess.check_output(argv, cwd=root)


def sha(data):
    return hashlib.sha256(data).hexdigest()


history = command("git", "ls-tree", "-r", base, "--", "spec/performance")
for line in history.decode().splitlines():
    metadata, name = line.split("\t", 1)
    raw = (root / name).read_bytes()
    blob = b"blob " + str(len(raw)).encode() + b"\0" + raw
    assert hashlib.sha1(blob).hexdigest() == metadata.split()[2], name

old = root / "spec/performance/graph-s5a-local-2026-10-31"
for path in old.iterdir():
    relative = path.relative_to(root).as_posix()
    assert path.read_bytes() == command(
        "git", "show", f"629101e0e750dadb68bab2750d4c5e87191789cd:{relative}"
    ), relative

names = command("git", "diff", "--name-only", base).decode().splitlines()
sources = {
    name: sha((root / name).read_bytes())
    for name in names
    if not name.startswith("spec/performance/") and (root / name).is_file()
}
locations = ["packages/xy-client/dist", "python/xyg/static"]
members = [
    "index.js",
    "standalone.js",
    "wasm-worker.js",
    "xyg-wasm.wasm",
    "xyg-wasm-inline.js",
    "xyg-wasm.manifest.json",
]
for name in members:
    assert (root / locations[0] / name).read_bytes() == (root / locations[1] / name).read_bytes(), (
        name
    )
module = (root / locations[0] / "xyg-wasm.wasm").read_bytes()
decision = json.loads((receipt / "decision.json").read_text())
assert sha(module) == decision["optimizedSha256"]
assert len(module) == decision["rawBytes"] <= decision["rawLimit"]
foundation = json.loads((receipt / "foundation.json").read_text())
assert foundation["scope"] == "full-foundation" and foundation["status"] == "passed"
assert foundation["artifactCommit"] is None
assert foundation["externalRequests"] == []
assert len(foundation["densityNoRefinement"]) == 6
for case in foundation["densityNoRefinement"]:
    shot = case["screenshot"]
    assert sha((receipt / shot["file"]).read_bytes()) == shot["sha256"]
commands = {}
for directory in [receipt.parent / "graph-s5a-integration-2026-11-03", receipt]:
    for path in sorted(directory.glob("*.command.json")):
        record = json.loads(path.read_text())
        packed = (directory / record["log"]).read_bytes()
        raw = gzip.decompress(packed)
        assert sha(packed) == record["gzipSha256"], path
        assert sha(raw) == record["rawSha256"], path
        assert raw == path.with_name(record["name"] + ".txt").read_bytes(), path
        commands[str(path.relative_to(receipt.parent))] = record

artifacts = [
    "target/release/libxyg_core.so",
    "target/wasm32-unknown-unknown/release/xyg_wasm.wasm",
    "target/task-tmp/s5a-integration-diagnostic.wasm",
    "packages/xy-client/dist/wasm-inline-worker.js",
    *(f"{location}/{name}" for location in locations for name in members),
]
result = {
    "scope": "S5a actual producer, paired assets and full strict-CSP foundation",
    "acceptedMain": base,
    "artifactCommit": None,
    "headAtCapture": command("git", "rev-parse", "HEAD").decode().strip(),
    "nonreceiptDiffSha256": sha(
        command("git", "diff", "--binary", "--full-index", base, "--", ".", ":!spec/performance")
    ),
    "sources": sources,
    "artifacts": {
        name: {"bytes": (root / name).stat().st_size, "sha256": sha((root / name).read_bytes())}
        for name in artifacts
    },
    "historicalMainReceiptFilesUnchanged": len(history.decode().splitlines()),
    "historicalChildReceiptFilesUnchanged": len(list(old.iterdir())),
    "historicalGitListingSha256": sha(history),
    "commands": commands,
    "environment": {
        "rustc": command("rustc", "-Vv").decode(),
        "node": command("node", "-v").decode().strip(),
        "python": command("uv", "run", "python", "-V").decode().strip(),
        "uname": command("uname", "-a").decode().strip(),
    },
    "releaseAcceptance": False,
}
(receipt / "evidence.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"module": sha(module), "sources": len(sources), "commands": len(commands)}))
