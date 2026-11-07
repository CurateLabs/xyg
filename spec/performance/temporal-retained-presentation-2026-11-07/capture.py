"""Capture exact source, archived artifacts, checked results and environment."""

from __future__ import annotations

import gzip
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
NODE = "/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin/node"
BASE = "2c799612191793cd2392b597dbdf9050a24e1cee"


def command(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def digest(path: Path) -> dict[str, int | str]:
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


# Rust was not edited in this slice. Reuse is admitted only by every producer
# input and the actual native/WASM artifact hash from the preceding receipt.
prior_path = ROOT / "spec/performance/temporal-graph-controller-2026-11-07/inputs-artifacts.json"
prior = json.loads(prior_path.read_text())
producer_inputs = {
    name: expected
    for name, expected in prior["sources"].items()
    if name.startswith("crates/") or name in {"Cargo.toml", "Cargo.lock", "rust-toolchain.toml"}
}
for name, expected in producer_inputs.items():
    assert digest(ROOT / name) == expected, name
for name in ("target/release/libxyg_core.so", "packages/xy-client/dist/xyg-wasm.wasm"):
    assert digest(ROOT / name) == prior["artifacts"][name], name

sources = set(ROOT.glob("js/src/*.ts")) | set(ROOT.glob("crates/**/*.rs"))
sources |= set(ROOT.glob("crates/**/Cargo.toml"))
sources |= {
    ROOT / name
    for name in [
        "Cargo.toml",
        "Cargo.lock",
        "rust-toolchain.toml",
        "package-lock.json",
        "js/build.mjs",
        "js/package-wasm.mjs",
        "js/tsconfig.json",
        "scripts/graph_session_controller_wasm_smoke.mjs",
        "scripts/wasm_foundation_smoke.mjs",
        "tests/browser/graph_session_controller_page.mjs",
        "tests/browser/wasm_foundation_page.mjs",
        "tests/fixtures/temporal/assertion-history.json",
        "tests/test_temporal_graph_native.py",
        "packages/xy-node/test/graph-session-wire.test.mjs",
        "packages/xy-node/test/graph-session-replay-helpers.mjs",
        "scripts/gen_capability_matrix.py",
        "spec/releases/0.6.0-api-inventory.json",
        "spec/api/browser-wasm.md",
        "spec/design/temporal-graph.md",
        "spec/design/temporal-controller.md",
        "spec/design/graph-interaction.md",
        "spec/design/browser-wasm.md",
        "spec/design/build-ci.md",
        "spec/design/ownership-audit.md",
        "spec/design/ownership-audit.json",
    ]
}
artifacts = [
    *sorted((ROOT / "packages/xy-client/dist").glob("*")),
    ROOT / "target/release/libxyg_core.so",
]
archive = OUT / "artifacts"
archive.mkdir(exist_ok=True)
artifact_records = {}
for path in artifacts:
    if not path.is_file():
        continue
    target = archive / (path.name + ".gz")
    target.write_bytes(gzip.compress(path.read_bytes(), compresslevel=9, mtime=0))
    assert gzip.decompress(target.read_bytes()) == path.read_bytes()
    artifact_records[str(path.relative_to(ROOT))] = {
        **digest(path),
        "archive": str(target.relative_to(OUT)),
        "archiveDigest": digest(target),
    }

report = {
    "workspace": str(ROOT),
    "branch": command("git", "branch", "--show-current"),
    "base": BASE,
    "sourceMeaning": "generation-time working-tree bytes; exact hashes below",
    "environment": {
        "projectPython": sys.version,
        "projectPythonExecutable": sys.executable,
        "systemPython": command("/usr/bin/python3", "--version"),
        "systemPythonExecutable": "/usr/bin/python3",
        "node": command(NODE, "--version"),
        "rustc": command("/home/ubuntu/.cargo/bin/rustc", "--version"),
        "cargo": command("/home/ubuntu/.cargo/bin/cargo", "--version"),
        "platform": platform.platform(),
        "CARGO_BUILD_JOBS": 2,
        "chromium": "/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome",
    },
    "rustReuse": {
        "priorReceipt": str(prior_path.relative_to(ROOT)),
        "receiptDigest": digest(prior_path),
        "checkedInputs": len(producer_inputs),
        "allMatch": True,
        "nativeAndWasmArtifactDigestsMatch": True,
    },
    "sources": {str(path.relative_to(ROOT)): digest(path) for path in sorted(sources)},
    "artifacts": artifact_records,
    "wasmManifest": json.loads(
        (ROOT / "packages/xy-client/dist/xyg-wasm.manifest.json").read_text()
    ),
    "node22Gzip6Bytes": int(
        command(
            NODE,
            "--input-type=module",
            "-e",
            "import{readFileSync}from'node:fs';import{gzipSync}from'node:zlib';console.log(gzipSync(readFileSync('packages/xy-client/dist/xyg-wasm.wasm'),{level:6}).length)",
        )
    ),
    "evidence": {
        str(path.relative_to(OUT)): digest(path)
        for path in sorted(OUT.rglob("*"))
        if path.is_file() and path.name != "inputs-artifacts.json"
    },
}
(OUT / "inputs-artifacts.json").write_text(json.dumps(report, indent=2) + "\n")
print(
    f"Captured {len(sources)} source inputs; {len(producer_inputs)} Rust producer inputs and both reused artifacts match"
)
