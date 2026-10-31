"""Retain exact local commands, exits, timings and deterministic gzip raw logs."""

import gzip
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

receipt = Path(__file__).resolve().parent
root = receipt.parents[2]
name, *command = sys.argv[1:]
env = os.environ.copy()
env["PATH"] = (
    "/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/"
    "node-v22.23.4-linux-x64/bin:/home/ubuntu/.cargo/bin:" + env["PATH"]
)
env["TMPDIR"] = str(root / "target/task-tmp")
env["XYG_NATIVE_LIB"] = str(root / "target/release/libxyg_core.so")
env["XYG_CHROMIUM"] = "/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome"
env["UV_OFFLINE"] = "1"
start = time.monotonic()
result = subprocess.run(command, cwd=root, env=env, capture_output=True)
raw = result.stdout + result.stderr
packed = gzip.compress(raw, mtime=0)
(receipt / f"{name}.txt.gz").write_bytes(packed)
record = {
    "name": name,
    "command": command,
    "exitCode": result.returncode,
    "seconds": round(time.monotonic() - start, 3),
    "rawSha256": hashlib.sha256(raw).hexdigest(),
    "log": f"{name}.txt.gz",
    "gzipSha256": hashlib.sha256(packed).hexdigest(),
}
(receipt / f"{name}.command.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record))
print(raw.decode(errors="replace")[-6000:])
sys.exit(result.returncode)
