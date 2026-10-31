"""Bind final nonreceipt source, generated seams, artifacts and command logs."""

import hashlib
import json
import platform
import subprocess
from pathlib import Path

receipt = Path(__file__).resolve().parent
root = receipt.parents[2]
base = "dee3ea37540a7126c3082ae59624bb02881bb00f"


def command(*argv: str) -> bytes:
    return subprocess.check_output(argv, cwd=root)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


names = set(command("git", "diff", "--name-only", base).decode().splitlines())
names.update(command("git", "ls-files", "--others", "--exclude-standard").decode().splitlines())
sources = {
    name: digest((root / name).read_bytes())
    for name in sorted(names)
    if not name.startswith("spec/performance/") and (root / name).is_file()
}
patch = command(
    "git", "diff", "--binary", "--full-index", base, "--", ".", f":!{receipt.relative_to(root)}"
)
(receipt / "source.patch").write_bytes(patch)
bindings = [
    "spec/abi/xyg-abi.json",
    "spec/abi/xyg.h",
    "spec/wasm/abi.json",
    "python/xyg/_native.py",
    "python/xyg/_abi_generated.py",
    "packages/xy-node/src/native.js",
    "packages/xy-node/src/abi.js",
    "packages/xy-node/src/_abi_generated.js",
    "js/src/wasm_abi_generated.ts",
    "js/src/49_wasm_graphforge.ts",
]
artifacts = [
    "target/release/libxyg_core.so",
    "target/wasm32-unknown-unknown/release/xyg_wasm.wasm",
    "target/task-tmp/s4-review-repair-diagnostic-assets/packages/xy-client/dist/xyg-wasm.wasm",
    "target/task-tmp/s4-review-repair-diagnostic-assets/packages/xy-client/dist/xyg-wasm-inline.js",
    "packages/xy-client/dist/index.js",
    "packages/xy-client/dist/standalone.js",
]
record = {
    "scope": "final local repair; optimized assets explicitly diagnostic, shipping gates FAIL",
    "artifactCommit": None,
    "parent": base,
    "branch": command("git", "branch", "--show-current").decode().strip(),
    "path": str(root),
    "nonreceiptBinaryFullIndexDiffSha256": digest(patch),
    "sources": sources,
    "bindings": {name: digest((root / name).read_bytes()) for name in bindings},
    "artifacts": {
        name: {"bytes": (root / name).stat().st_size, "sha256": digest((root / name).read_bytes())}
        for name in artifacts
    },
    "commands": {
        path.name: json.loads(path.read_text()) for path in sorted(receipt.glob("*.command.json"))
    },
    "environment": {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "rustc": command("rustc", "-Vv").decode(),
        "cargo": command("cargo", "-V").decode().strip(),
        "node": command("node", "--version").decode().strip(),
        "chromium": command(
            "/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome", "--version"
        )
        .decode()
        .strip(),
    },
}
for name in ("packages/xy-client/dist/xyg-wasm.wasm", "python/xyg/static/xyg-wasm.wasm"):
    assert not (root / name).exists(), "failed producer must withhold shipping WASM"
selected = json.loads((receipt / "experiment-b.artifact.json").read_text())
assert digest((root / artifacts[1]).read_bytes()) == selected["rawCompiler"]["sha256"]
assert digest((root / artifacts[2]).read_bytes()) == selected["optimized"]["sha256"]
(receipt / "evidence.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps({"sourceCount": len(sources), "artifacts": record["artifacts"]}, indent=2))
