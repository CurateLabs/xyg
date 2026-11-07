"""Rebind locally built artifacts; run from the repository root with explicit native.

This collector makes no timing, platform, or performance qualification claim.
"""

import datetime
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from xyg import _native, kernels

ROOT = Path.cwd()
OUT = ROOT / "spec/performance/filter-tier-c-linked-product-2026-11-07"
NODE = Path(
    os.environ.get(
        "XYG_NODE",
        "/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin/node",
    )
)
CHROME = Path(
    os.environ.get(
        "XYG_CHROMIUM", "/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome"
    )
)


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


assert kernels.BACKEND == "native"
assert Path(_native._lib._name).resolve() == (ROOT / "target/release/libxyg_core.so").resolve()
env = dict(
    capturedAt=datetime.datetime.now(datetime.UTC).isoformat(),
    platform=platform.platform(),
    python=sys.version,
    pythonExecutable=sys.executable,
    nativePath=_native._lib._name,
    nativeAbi=_native._lib.xyg_abi_version(),
    backend=kernels.BACKEND,
    rustc=run("/home/ubuntu/.cargo/bin/rustc", "-Vv"),
    cargo=run("/home/ubuntu/.cargo/bin/cargo", "-V"),
    node=run(str(NODE), "--version"),
    nodePath=str(NODE),
    chromium=run(str(CHROME), "--version"),
    chromiumPath=str(CHROME),
    workspace=str(ROOT),
    branch=run("git", "branch", "--show-current"),
    buildParent=run("git", "rev-parse", "HEAD"),
    integrationParents=run(
        "git", "show", "-s", "--format=%P", "514a2ac72a5b90ef53c8b8acc87e1afc345c9b5c"
    ).split(),
    requiredAcceptedM5="58960c7c6c814ed049209052cf66d77b5bb7ecfd",
    observedMainAtFetch="43c35f67b95ae4e78e3e96f200a0e6be8642199c",
    cargoBuildJobs=2,
    tmpdir="/var/tmp/xyg-f112",
    cpuAffinity=sorted(os.sched_getaffinity(0)),
    cpuCount=os.cpu_count(),
    buildEnvironment={
        k: os.environ.get(k)
        for k in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_TARGET_DIR", "RUSTUP_TOOLCHAIN")
    },
)
write("environment.json", env)

rust_paths = sorted(
    {
        *ROOT.glob("crates/**/*.rs"),
        ROOT / "Cargo.toml",
        ROOT / "Cargo.lock",
        ROOT / "rust-toolchain.toml",
        ROOT / ".cargo/config.toml",
        *ROOT.glob("crates/**/Cargo.toml"),
    }
)
write("rust-sources.json", {str(p.relative_to(ROOT)): sha(p) for p in rust_paths})
client_paths = sorted(
    {
        *ROOT.glob("js/src/*.ts"),
        ROOT / "js/build.mjs",
        ROOT / "js/package-wasm.mjs",
        ROOT / "js/optimize-wasm.mjs",
        ROOT / "package.json",
        ROOT / "package-lock.json",
        ROOT / "packages/xy-node/src/filter-protocol.js",
    }
)
write("client-sources.json", {str(p.relative_to(ROOT)): sha(p) for p in client_paths})

paths = [
    "target/release/libxyg_core.so",
    "target/wasm32-unknown-unknown/release/xyg_wasm.wasm",
    "packages/xy-client/dist/xyg-wasm.wasm",
    "packages/xy-client/dist/xyg-wasm.manifest.json",
    "packages/xy-client/dist/index.js",
    "packages/xy-client/dist/standalone.js",
    "packages/xy-client/dist/wasm-worker.js",
    "packages/xy-client/dist/wasm-inline-worker.js",
    "packages/xy-client/dist/xyg-wasm-inline.js",
    "python/xyg/static/xyg-wasm.wasm",
    "python/xyg/static/index.js",
    "python/xyg/static/standalone.js",
    "tests/fixtures/filter_tier_c/session.bin",
    "tests/fixtures/filter_tier_c/density.bin",
    "tests/fixtures/filter_tier_c/density.json",
]
files = {name: dict(bytes=(ROOT / name).stat().st_size, sha256=sha(ROOT / name)) for name in paths}
gzip_bytes = int(
    run(
        str(NODE),
        "-e",
        'const f=require("fs"),z=require("zlib");console.log(z.gzipSync(f.readFileSync("packages/xy-client/dist/xyg-wasm.wasm"),{level:9}).length)',
    )
)
raw = files["packages/xy-client/dist/xyg-wasm.wasm"]["bytes"]
assert raw <= 1882 * 1024 and gzip_bytes <= 768 * 1024
assert (
    files["packages/xy-client/dist/xyg-wasm.wasm"]["sha256"]
    == files["python/xyg/static/xyg-wasm.wasm"]["sha256"]
)
assert (
    files["packages/xy-client/dist/index.js"]["sha256"]
    == files["python/xyg/static/index.js"]["sha256"]
)
write(
    "artifacts.json",
    dict(
        nativeAbi=402,
        wasmAbi=36,
        sourceBindings=["rust-sources.json", "client-sources.json", "current-bindings.json"],
        files=files,
        wasmCaps=dict(raw=1882 * 1024, gzip=768 * 1024),
        wasmMeasured=dict(
            raw=raw,
            gzip=gzip_bytes,
            rawHeadroom=1882 * 1024 - raw,
            gzipHeadroom=768 * 1024 - gzip_bytes,
        ),
        qualification="bounded functional proof, not massive performance or compiler comparison",
    ),
)

foreign = {}
for path in [
    "packages/xy-node/src/force_scheduler.js",
    "packages/xy-node/test/force-worker-lifecycle.test.mjs",
    "packages/xy-node/test/graphforge-layout.test.mjs",
]:
    before = subprocess.check_output(
        ["git", "show", f"b91b8099ff1281f3740c8f8d4fde461509c332d0:{path}"]
    )
    foreign[path] = dict(
        reviewedB91Sha256=hashlib.sha256(before).hexdigest(),
        candidateSha256=sha(ROOT / path),
        unchanged=before == (ROOT / path).read_bytes(),
    )
write("worker-timing-source-bindings.json", foreign)
print(
    json.dumps(
        dict(
            native=files["target/release/libxyg_core.so"],
            wasm=files["packages/xy-client/dist/xyg-wasm.wasm"],
            raw=raw,
            gzip=gzip_bytes,
            client=files["packages/xy-client/dist/index.js"],
        )
    )
)
