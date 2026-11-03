"""Bind the binding-count repair and its before/after proof to exact bytes."""

import gzip
import hashlib
import json
import subprocess
from pathlib import Path

receipt = Path(__file__).resolve().parent
root = receipt.parents[2]
base = "5840b4790660d8bafa59e9b5308b450c51f55713"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=root)


def sha(data):
    return hashlib.sha256(data).hexdigest()


history = git("ls-tree", "-r", base, "--", "spec/performance")
for line in history.decode().splitlines():
    metadata, name = line.split("\t", 1)
    raw = (root / name).read_bytes()
    blob = b"blob " + str(len(raw)).encode() + b"\0" + raw
    assert hashlib.sha1(blob).hexdigest() == metadata.split()[2], name

controls = json.loads((receipt / "package-controls.json").read_text())
for name, digest in controls["unchangedSources"].items():
    raw = (root / name).read_bytes()
    assert sha(raw) == digest and raw == git("show", f"{base}:{name}"), name

names = git("diff", "--name-only", base).decode().splitlines()
sources = {
    name: sha((root / name).read_bytes())
    for name in names
    if not name.startswith("spec/performance/") and (root / name).is_file()
}
assets = ["target/release/libxyg_core.so"]
for name in [
    "index.js",
    "standalone.js",
    "wasm-worker.js",
    "xyg-wasm.wasm",
    "xyg-wasm-inline.js",
    "xyg-wasm.manifest.json",
]:
    node, python = f"packages/xy-client/dist/{name}", f"python/xyg/static/{name}"
    assert (root / node).read_bytes() == (root / python).read_bytes(), name
    assets.extend([node, python])
module = json.loads((receipt / "module.json").read_text())
assert module["source"] == "production-dist" and module["diagnosticModule"] is False
assert module["sha256"] == sha((root / "packages/xy-client/dist/xyg-wasm.wasm").read_bytes())
foundation = json.loads((receipt / "foundation.json").read_text())
assert foundation["scope"] == "full-foundation" and foundation["status"] == "passed"
assert foundation["artifactCommit"] is None and foundation["externalRequests"] == []
assert len(foundation["densityNoRefinement"]) == 6
for case in foundation["densityNoRefinement"]:
    shot = case["screenshot"]
    assert sha((receipt / shot["file"]).read_bytes()) == shot["sha256"]

commands = {}
for path in sorted(receipt.glob("*.command.json")):
    record = json.loads(path.read_text())
    packed = (receipt / record["log"]).read_bytes()
    raw = gzip.decompress(packed)
    assert sha(packed) == record["gzipSha256"] and sha(raw) == record["rawSha256"], path
    assert raw == (receipt / f"{record['name']}.txt").read_bytes(), path
    commands[path.name] = record

result = {
    "base": base,
    "artifactCommit": None,
    "scope": "bound selection-count correction; no issue or release acceptance",
    "sources": sources,
    "nonreceiptDiffSha256": sha(
        git("diff", "--binary", "--full-index", base, "--", ".", ":!spec/performance")
    ),
    "artifacts": {
        name: {"bytes": (root / name).stat().st_size, "sha256": sha((root / name).read_bytes())}
        for name in assets
    },
    "historicalReceiptFilesUnchanged": len(history.decode().splitlines()),
    "historicalGitListingSha256": sha(history),
    "commands": commands,
    "module": module,
}
(receipt / "evidence.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"sources": len(sources), "commands": len(commands), "module": module}))
