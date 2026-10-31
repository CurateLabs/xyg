"""Capture source/artifact bindings without attributing uncommitted proof to a commit."""

from __future__ import annotations

import gzip
import hashlib
import json
import platform
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def run(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


paths = set(run("git", "diff", "--name-only", "HEAD").splitlines())
paths.update(run("git", "ls-files", "--others", "--exclude-standard").splitlines())
source = {
    name: digest((ROOT / name).read_bytes())
    for name in sorted(paths)
    if name != "TASKS.md"
    and not name.startswith("spec/performance/graph-s4-local-2026-10-31/")
    and (ROOT / name).is_file()
}
artifacts = {}
for name in [
    "target/release/libxyg_core.so",
    "target/wasm32-unknown-unknown/release/xyg_wasm.wasm",
    "target/task-tmp/s4-diagnostic-assets/packages/xy-client/dist/xyg-wasm.wasm",
]:
    path = ROOT / name
    if path.is_file():
        data = path.read_bytes()
        artifacts[name] = {"bytes": len(data), "sha256": digest(data)}
        if name.endswith("xyg-wasm.wasm"):
            packed = gzip.compress(data, mtime=0, compresslevel=6)
            artifacts[name]["pythonDiagnosticGzip6Bytes"] = len(packed)
node = "/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin/node"
receipt = {
    "artifactCommit": None,
    "parentCommit": "6a42e73be1ae75effb847c875fa3d26ff2d0a4e6",
    "checkoutHead": run("git", "rev-parse", "HEAD"),
    "branch": run("git", "branch", "--show-current"),
    "checkout": str(ROOT),
    "sourceFiles": source,
    "sourceInventorySha256": digest(json.dumps(source, sort_keys=True).encode()),
    "sourceInventoryScope": "changed product/spec/test files; receipt and TASKS.md excluded to avoid self-reference",
    "artifacts": artifacts,
    "environment": {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "node": run(node, "--version"),
        "nodePath": node,
        "cargo": run("/home/ubuntu/.cargo/bin/cargo", "--version"),
        "rustc": run("/home/ubuntu/.cargo/bin/rustc", "-vV"),
        "chromium": run(
            "/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome", "--version"
        ),
    },
    "commands": [json.loads(p.read_text()) for p in sorted(HERE.glob("*.command.json"))],
}
(HERE / "evidence.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt["artifacts"], indent=2))
