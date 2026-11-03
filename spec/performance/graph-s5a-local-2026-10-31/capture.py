"""Bind S5a source, failed shipping measurements and diagnostic-only proof."""

import hashlib
import json
import subprocess
from pathlib import Path

receipt = Path(__file__).resolve().parent
root = receipt.parents[2]
base = "1044cdf2175d57dbed2c5088f747f812a982dc08"


def command(*argv):
    return subprocess.check_output(argv, cwd=root)


def sha(data):
    return hashlib.sha256(data).hexdigest()


history = command("git", "ls-tree", "-r", base, "--", "spec/performance")
count = 0
for line in history.decode().splitlines():
    metadata, name = line.split("\t", 1)
    expected = metadata.split()[2]
    raw = (root / name).read_bytes()
    assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == expected, (
        name
    )
    count += 1
names = command("git", "diff", "--name-only", base).decode().splitlines()
sources = {
    name: sha((root / name).read_bytes())
    for name in names
    if not name.startswith("spec/performance/") and (root / name).is_file()
}
artifacts = [
    "target/release/libxyg_core.so",
    "target/wasm32-unknown-unknown/release/xyg_wasm.wasm",
    "target/task-tmp/s5a-diagnostic.wasm",
    "target/task-tmp/s5a-parent-target/release/libxyg_core.so",
    "packages/xy-client/dist/index.js",
    "packages/xy-client/dist/standalone.js",
    "python/xyg/static/index.js",
    "python/xyg/static/standalone.js",
]
diagnostic = json.loads((root / "target/task-tmp/s5a-diagnostic.json").read_text())
assert diagnostic["diagnosticOnly"] and not diagnostic["shippingGatePassed"]
assert diagnostic["exactManifestSignatures"] == 65
assert diagnostic["optimizedSha256"] == sha(
    (root / "target/task-tmp/s5a-diagnostic.wasm").read_bytes()
)
for name in ["index.js", "standalone.js"]:
    assert (root / "packages/xy-client/dist" / name).read_bytes() == (
        root / "python/xyg/static" / name
    ).read_bytes()
record = {
    "scope": "bounded S5a Rust GPU publication/results; shipping gates FAIL; diagnostic functional proof only",
    "base": base,
    "artifactCommit": None,
    "headAtCapture": command("git", "rev-parse", "HEAD").decode().strip(),
    "branch": command("git", "branch", "--show-current").decode().strip(),
    "nonreceiptBinaryFullIndexDiffSha256": sha(
        command("git", "diff", "--binary", "--full-index", base, "--", ".", ":!spec/performance")
    ),
    "productionDiffSha256": sha(
        command(
            "git",
            "diff",
            "--binary",
            "--full-index",
            base,
            "--",
            "crates/xyg-engine/src/graphforge/interaction.rs",
            "crates/xyg-engine/src/graphforge/interaction/gpu.rs",
            "crates/xyg-engine/src/graphforge/interaction/wire.rs",
        )
    ),
    "sources": sources,
    "historicalReceiptFilesUnchanged": count,
    "historicalReceiptGitListingSha256": sha(history),
    "artifacts": {
        name: {"bytes": (root / name).stat().st_size, "sha256": sha((root / name).read_bytes())}
        for name in artifacts
    },
    "module": diagnostic,
    "packageGatesChanged": False,
    "sizeExperiments": 0,
    "pairedWasmAssets": "not emitted: failed shipping gate",
    "fullFoundation": "not run: shipping gate failed; no diagnostic substitute",
    "commands": {p.name: json.loads(p.read_text()) for p in sorted(receipt.glob("*.command.json"))},
    "environment": {
        "rustc": command("rustc", "-Vv").decode(),
        "node": command("node", "-v").decode().strip(),
        "python": command("uv", "run", "python", "-V").decode().strip(),
        "uname": command("uname", "-a").decode().strip(),
    },
}
(receipt / "evidence.json").write_text(json.dumps(record, indent=2) + "\n")
print(
    json.dumps(
        {
            "historicalFilesUnchanged": count,
            "sources": len(sources),
            "module": diagnostic["optimizedSha256"],
            "productionDiffSha256": record["productionDiffSha256"],
        }
    )
)
