#!/usr/bin/env python3
"""Capture one authorized sync command without overwriting evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("label")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    destination = OUT / f"{args.label}.command.json"
    if destination.exists():
        raise SystemExit(f"receipt exists: {destination}; choose a new label")
    start = dt.datetime.now(dt.UTC).isoformat()
    began = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
    outputs = {"stdout": result.stdout, "stderr": result.stderr}
    for suffix, data in outputs.items():
        (OUT / f"{args.label}.{suffix}").write_bytes(data)
    receipt = {
        "argv": command,
        "captureScriptSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cwd": str(ROOT),
        "started": start,
        "finished": dt.datetime.now(dt.UTC).isoformat(),
        "elapsedSeconds": time.monotonic() - began,
        "exitCode": result.returncode,
        "environment": {
            name: os.environ.get(name)
            for name in (
                "PATH",
                "XYG_NATIVE_LIB",
                "XYG_CHROMIUM",
                "XYG_NODE_NATIVE_ORIGIN_RECORD",
                "PYTHONPATH",
                "CARGO_TARGET_DIR",
                "RUSTFLAGS",
                "UV_PROJECT_ENVIRONMENT",
            )
        },
        "outputSha256": {k: hashlib.sha256(v).hexdigest() for k, v in outputs.items()},
    }
    destination.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"label": args.label, "exitCode": result.returncode}))
    print(result.stdout.decode(errors="replace"))
    print(result.stderr.decode(errors="replace"))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
