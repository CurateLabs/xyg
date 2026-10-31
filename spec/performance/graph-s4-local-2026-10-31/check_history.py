"""Prove historical S1/S2/S3 receipts and protected build inputs unchanged."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = "6a42e73be1ae75effb847c875fa3d26ff2d0a4e6"
PARENT = "bd57eb7c692b658d9428109103f4da47dd5eb144"


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


records = {}
for name in git("ls-files", "spec/performance").decode().splitlines():
    if not any(f"/graph-s{i}-" in name for i in (1, 2, 3)):
        continue
    ref = PARENT if "/graph-s3-aggregate-style-repair-2026-10-31/" in name else BASE
    expected = git("show", f"{ref}:{name}")
    actual = (ROOT / name).read_bytes()
    assert actual == expected, name
    records[name] = hashlib.sha256(actual).hexdigest()
protected = {}
for name in (
    "Cargo.toml",
    "Cargo.lock",
    "rust-toolchain.toml",
    ".cargo/config.toml",
    "package-lock.json",
    "js/package-wasm.mjs",
    "js/optimize-wasm.mjs",
):
    actual = (ROOT / name).read_bytes()
    assert actual == git("show", f"{BASE}:{name}"), name
    protected[name] = hashlib.sha256(actual).hexdigest()
result = {
    "status": "pass",
    "historicalReceiptFiles": len(records),
    "historicalInventorySha256": hashlib.sha256(
        json.dumps(records, sort_keys=True).encode()
    ).hexdigest(),
    "protectedBuildInputs": protected,
}
(HERE / "history.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
