"""Capture actual local inputs and generated artifacts; no synthetic results."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
NODE = Path(
    "/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin/node"
)


def run(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def digest(path: Path) -> dict[str, str | int]:
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


paths = [
    *ROOT.glob("crates/**/*.rs"),
    *ROOT.glob("crates/**/Cargo.toml"),
    *ROOT.glob("js/src/*.ts"),
    ROOT / "Cargo.toml",
    ROOT / "Cargo.lock",
    ROOT / "rust-toolchain.toml",
    ROOT / "package-lock.json",
    ROOT / "js/build.mjs",
    ROOT / "js/package-wasm.mjs",
    ROOT / "tests/browser/wasm_foundation_page.mjs",
    ROOT / "scripts/wasm_foundation_smoke.mjs",
    ROOT / "tests/test_temporal_graph_native.py",
    ROOT / "tests/fixtures/temporal/assertion-history.json",
]
artifacts = [
    *sorted((ROOT / "packages/xy-client/dist").glob("*")),
    ROOT / "target/release/libxyg_core.so",
]
report = {
    "workspace": str(ROOT),
    "branch": run("git", "branch", "--show-current"),
    "preImplementationMerge": run("git", "rev-parse", "HEAD"),
    "acceptedMain": "80e841542462eaf5509ac90e1f17a80cae974164",
    "environment": {
        "node": run(str(NODE), "--version"),
        "projectPython": run("uv", "run", "python", "--version"),
        "systemPython": run("python3", "--version"),
        "cargo": run("/home/ubuntu/.cargo/bin/cargo", "--version"),
        "rustc": run("/home/ubuntu/.cargo/bin/rustc", "--version"),
        "CARGO_BUILD_JOBS": 2,
        "chromium": "/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome",
    },
    "sources": {str(p.relative_to(ROOT)): digest(p) for p in sorted(set(paths))},
    "artifacts": {str(p.relative_to(ROOT)): digest(p) for p in artifacts if p.is_file()},
    "node22Gzip6Bytes": int(
        run(
            str(NODE),
            "--input-type=module",
            "-e",
            "import{readFileSync}from'node:fs';import{gzipSync}from'node:zlib';console.log(gzipSync(readFileSync('packages/xy-client/dist/xyg-wasm.wasm'),{level:6}).length)",
        )
    ),
    "rawLogs": {p.name: digest(p) for p in sorted([*OUT.glob("*.log"), *OUT.glob("*.log.gz")])},
}
(OUT / "inputs-artifacts.json").write_text(json.dumps(report, indent=2) + "\n")
