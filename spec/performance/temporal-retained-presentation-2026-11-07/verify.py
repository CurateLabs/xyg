"""Reproduce bounded retained presentation checks with checked exits and raw logs."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
NODE_BIN = "/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin"
env = dict(os.environ)
env.update(
    PATH=NODE_BIN + ":/home/ubuntu/.cargo/bin:" + env["PATH"],
    CARGO_BUILD_JOBS="2",
    XYG_CHROMIUM="/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome",
    XYG_NATIVE_LIB=str(ROOT / "target/release/libxyg_core.so"),
)
checks = [
    ("client", ["node", "js/build.mjs"], {}),
    ("assets", ["uv", "run", "python", "scripts/verify_wasm_assets.py"], {}),
    ("ownership", ["uv", "run", "python", "scripts/verify_ownership.py"], {}),
    ("inventory", ["uv", "run", "python", "scripts/check_release_inventory.py"], {}),
    ("native-wasm", ["node", "--test", "packages/xy-node/test/graph-session-wire.test.mjs"], {}),
    (
        "python",
        [
            "uv",
            "run",
            "pytest",
            "-q",
            "tests/test_temporal_controller.py",
            "tests/test_temporal_graph_native.py",
            "tests/test_release_inventory.py",
            "tests/test_capability_registry.py",
            "tests/test_verify_wasm_assets.py",
        ],
        {},
    ),
    (
        "foundation",
        ["node", "scripts/wasm_foundation_smoke.mjs"],
        {"XYG_WASM_FOUNDATION_REPORT": str(OUT / "ci-foundation.json")},
    ),
    (
        "existing-browser",
        ["node", "scripts/graph_session_controller_wasm_smoke.mjs"],
        {"XYG_GRAPH_SESSION_REPORT": str(OUT / "ci-existing.json")},
    ),
]
results = []
for name, command, extra in checks:
    started = time.monotonic()
    with (OUT / f"checked-{name}.log").open("wb") as log:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env={**env, **extra},
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    results.append(
        {
            "name": name,
            "command": command,
            "environmentOverrides": extra,
            "exitCode": completed.returncode,
            "seconds": time.monotonic() - started,
        }
    )
    (OUT / "checked-exits.json").write_text(
        json.dumps({"recordedAt": dt.datetime.now(dt.UTC).isoformat(), "checks": results}, indent=2)
        + "\n"
    )
    print(f"{name}: exit {completed.returncode}", flush=True)
    if completed.returncode:
        raise SystemExit(completed.returncode)
