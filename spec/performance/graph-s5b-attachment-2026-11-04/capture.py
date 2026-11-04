"""Bind reused qualified Rust artifacts and freshly generated browser assets to source."""

import hashlib
import json
import subprocess
from pathlib import Path

root = Path.cwd()
receipt = Path(__file__).resolve().parent
base = "7e99ec5da586572d411996599cf37f25dc5566c7"
prior = root / "spec/performance/graph-property-default-package-2026-11-03"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


tracked = subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
files = [
    p
    for p in tracked
    if p
    and (
        p.startswith(("crates/", ".cargo/", "js/src/", "spec/wasm/"))
        or p
        in (
            "Cargo.toml",
            "Cargo.lock",
            "rust-toolchain.toml",
            "js/build.mjs",
            "js/optimize-wasm.mjs",
            "js/package-wasm.mjs",
            "js/tsconfig.json",
            "package.json",
            "package-lock.json",
        )
    )
]
inputs = {p: sha((root / p).read_bytes()) for p in sorted(files)}
prior_inputs = json.loads((prior / "build-inputs.json").read_text())["files"]
rust_inputs = {
    p: value
    for p, value in inputs.items()
    if p.startswith(("crates/", ".cargo/"))
    or p in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "js/optimize-wasm.mjs")
}
assert all(prior_inputs.get(p) == value for p, value in rust_inputs.items())
assert all(
    subprocess.check_output(["git", "show", f"{base}:{p}"]) == (root / p).read_bytes()
    for p in rust_inputs
)
artifacts = {}
for directory in ("packages/xy-client/dist", "python/xyg/static"):
    for name in (
        "index.js",
        "standalone.js",
        "wasm-worker.js",
        "xyg-wasm.wasm",
        "xyg-wasm-inline.js",
        "xyg-wasm.manifest.json",
    ):
        p = f"{directory}/{name}"
        data = (root / p).read_bytes()
        artifacts[p] = {"bytes": len(data), "sha256": sha(data)}
for p in (
    "target/release/libxyg_core.so",
    "target/wasm32-unknown-unknown/release/xyg_wasm.wasm",
    "packages/xy-client/dist/wasm-inline-worker.js",
):
    data = (root / p).read_bytes()
    artifacts[p] = {"bytes": len(data), "sha256": sha(data)}
qualified = json.loads((prior / "shipping-artifacts.json").read_text())
for p in (
    "target/release/libxyg_core.so",
    "target/wasm32-unknown-unknown/release/xyg_wasm.wasm",
    "packages/xy-client/dist/xyg-wasm.wasm",
):
    assert artifacts[p] == qualified["artifacts"][p]
module = (root / "packages/xy-client/dist/xyg-wasm.wasm").read_bytes()
packed = subprocess.check_output(
    [
        str(root / "target/task-tmp/node-v22.23.4-linux-x64/bin/node"),
        "-e",
        "process.stdout.write(require('node:zlib').gzipSync(require('node:fs').readFileSync(process.argv[1]), {level:6}))",
        str(root / "packages/xy-client/dist/xyg-wasm.wasm"),
    ]
)
assert sha(module) == "e8011f779e70f58416a751f0067f279d1b9aa9515004c246e2f44c95af192651"
assert len(module) == 1922561 and len(packed) == 783148
assert len(module) < 1878 * 1024 and len(packed) < 765 * 1024
for p in (
    subprocess.check_output(["git", "ls-tree", "-r", "--name-only", base, "spec/performance/"])
    .decode()
    .splitlines()
):
    assert subprocess.check_output(["git", "show", f"{base}:{p}"]) == (root / p).read_bytes(), p
for name, value in (
    (
        "source-inputs.json",
        {"files": inputs, "sha256": sha(json.dumps(inputs, sort_keys=True).encode())},
    ),
    (
        "artifacts.json",
        {
            "base": base,
            "reuse": {
                "qualified_receipt": str(prior.relative_to(root)),
                "qualified_source_sha256": qualified["source_sha256"],
                "exact_rust_build_inputs": rust_inputs,
                "copied_from": "/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836",
                "native_and_raw_wasm_match_qualified_artifacts": True,
                "all_historical_receipts_preserved": True,
                "scope": "Only exact Rust artifacts reused; browser build, normal shipping packager, paired validation and journeys run fresh.",
            },
            "artifacts": artifacts,
            "module": {
                "bytes": len(module),
                "sha256": sha(module),
                "gzip6": len(packed),
                "raw_headroom": 511,
                "gzip6_headroom": 212,
            },
            "versions": {"native": 399, "wasm": 35, "scene": 34, "painter": 17},
        },
    ),
):
    with (receipt / name).open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
with (receipt / "shipping-module.wasm.gz").open("xb") as stream:
    stream.write(packed)
print(
    f"qualified unchanged Rust inputs: {len(rust_inputs)}; complete current build inputs: {len(inputs)}"
)
print(f"shipping module {len(module)} raw / {len(packed)} gzip6; headroom 511 / 212")
