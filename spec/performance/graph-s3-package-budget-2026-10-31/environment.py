"""Capture local toolchain and actual native/Node module provenance; no secrets."""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from xyg import _native
from xyg.kernels import BACKEND

root = Path.cwd()
receipt = Path(__file__).resolve().parent
commands = {
    "node": ["node", "--version"],
    "npm": ["npm", "--version"],
    "rustc": ["rustc", "--version", "--verbose"],
    "cargo": ["cargo", "--version"],
    "uv": ["uv", "--version"],
    "chromium": [os.environ["XYG_CHROMIUM"], "--version"],
}
files = [
    "target/release/libxyg_core.so",
    "target/wasm32-unknown-unknown/release/xyg_wasm.wasm",
    "Cargo.toml",
    "Cargo.lock",
    ".cargo/config.toml",
    "rust-toolchain.toml",
    "package-lock.json",
    "packages/xy-node/package.json",
    "packages/xy-node/package-lock.json",
    "packages/xy-node/node_modules/koffi/package.json",
    "node_modules/binaryen/package.json",
    "node_modules/playwright/package.json",
]
files += [str(p) for p in sorted(Path("packages/xy-node/src").rglob("*")) if p.is_file()]
files += [str(p) for p in sorted(Path("packages/xy-node/node_modules").rglob("*.node"))]
files += [os.environ["XYG_CHROMIUM"], shutil.which("node")]
report = {
    "platform": platform.platform(),
    "machine": platform.machine(),
    "python": sys.version,
    "pythonExecutable": sys.executable,
    "backend": BACKEND,
    "nativeAbi": _native.ABI_VERSION,
    "nativePath": os.environ["XYG_NATIVE_LIB"],
    "tmpdir": os.environ["TMPDIR"],
    "toolchain": {
        name: {
            "command": argv,
            "executable": shutil.which(argv[0]),
            "output": subprocess.check_output(argv, text=True).strip(),
        }
        for name, argv in commands.items()
    },
    "files": {
        name: {
            "bytes": (root / name).stat().st_size,
            "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
        }
        for name in files
    },
}
(receipt / "environment.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
