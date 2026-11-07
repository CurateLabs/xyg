"""Capture native checkpoint identities and successor source bindings, locally."""

from __future__ import annotations

import gzip
import hashlib
import json
import platform
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PREVIOUS = [
    "spec/performance/pr1110-main-integration-2026-11-07/current-bindings.json",
    "spec/performance/temporal-graph-main-integration-2026-11-07/current-bindings.json",
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    prior = json.loads((ROOT / PREVIOUS[0]).read_text())
    names = set()
    historical = dict(prior["historicalBindings"])
    for name in PREVIOUS:
        old = json.loads((ROOT / name).read_text())
        names.update(old["sourceSha256"])
        historical[name] = digest(ROOT / name)
    changed = (
        subprocess.check_output(["git", "diff", "--name-only", "HEAD"], cwd=ROOT)
        .decode()
        .splitlines()
    )
    added = (
        subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT)
        .decode()
        .splitlines()
    )
    names.update(name for name in changed + added if not name.startswith("spec/performance/"))
    names.add(str(Path(__file__).resolve().relative_to(ROOT)))
    bound = {name: digest(ROOT / name) for name in sorted(names) if (ROOT / name).is_file()}
    successor = dict(
        prior,
        sourceIdentity="ABI402 native frozen graph checkpoint; authentic historical producers retained",
        sourceSha256=bound,
        historicalBindings=historical,
    )
    (HERE / "current-bindings.json").write_text(json.dumps(successor, indent=2) + "\n")
    sources = {}
    for crate in ("xyg-engine", "xyg-core", "xyg-wasm"):
        for p in sorted((ROOT / "crates" / crate).rglob("*")):
            if p.is_file() and p.suffix in {".rs", ".toml"}:
                sources[str(p.relative_to(ROOT))] = digest(p)
    paths = [
        "target/release/libxyg_core.so",
        "packages/xy-client/dist/xyg-wasm.wasm",
        "packages/xy-client/dist/index.js",
        "packages/xy-client/dist/standalone.js",
        "packages/xy-client/dist/wasm-worker.js",
        "packages/xy-client/dist/wasm-inline-worker.js",
        "packages/xy-client/dist/xyg-wasm.manifest.json",
    ]
    artifacts = {
        name: {"sha256": digest(ROOT / name), "bytes": (ROOT / name).stat().st_size}
        for name in paths
    }
    wasm = ROOT / paths[1]
    script = "const fs=require('fs'),z=require('zlib');process.stdout.write(String(z.gzipSync(fs.readFileSync(process.argv[1]),{level:6}).length));"
    artifacts[paths[1]]["node22Gzip6Bytes"] = int(
        subprocess.check_output(["node", "-e", script, str(wasm)])
    )
    assert artifacts[paths[1]]["bytes"] <= 1882 * 1024
    assert artifacts[paths[1]]["node22Gzip6Bytes"] <= 768 * 1024
    native = ROOT / paths[0]
    (HERE / "libxyg_core.so.gz").write_bytes(gzip.compress(native.read_bytes(), mtime=0))
    records = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "node": subprocess.check_output(["node", "--version"]).decode().strip(),
        "rustc": subprocess.check_output(["rustc", "--version"]).decode().strip(),
        "nativeAbi": json.loads((ROOT / "spec/abi/xyg-abi.json").read_text())["abi_version"],
        "shippingWasmFreezeApi": False,
        "renderedExportAcceptance": False,
        "acceptedBase": "084b3c1b7c393e135476aab9610bf8334767b2ac",
        "acceptedMain": "ae104cf3",
        "reviewedAbi401LocallyMerged": "2cb7f0a13ec0af3a00b9dcfd2b104a2c579b7ac9",
        "implementationBase": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
        .decode()
        .strip(),
        "artifacts": artifacts,
        "rustSourceSha256": sources,
        "snapshots": {
            p.name: {"sha256": digest(p), "bytes": p.stat().st_size}
            for p in sorted(HERE.glob("*.xyfg"))
        },
    }
    (HERE / "identities.json").write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    main()
