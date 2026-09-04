#!/usr/bin/env python3
"""Run host-parity landing gates for the M2 close bar.

Stdlib-only orchestrator. Proves the branch meets the ownership + ABI +
cross-host Scene/static-output bar documented in ``spec/process/m2-close.md``
without running the full pytest suite or browser smokes.

Exit 0 when every step passes; non-zero on the first failure.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CROSS_HOST_TESTS = sorted(
    {
        *ROOT.glob("tests/test_*cross_host*.py"),
        ROOT / "tests" / "test_scene_trace_pack_abi.py",
        ROOT / "tests" / "test_scene_chrome_pack_abi.py",
    }
)

STEPS: tuple[tuple[list[str], str], ...] = (
    (["python3", "scripts/verify_ownership.py"], "ownership ledger"),
    (["python3", "scripts/audit_python_host_core.py"], "host inventory audit"),
    (["python3", "scripts/abi_smoke.py"], "ABI smoke"),
    (
        [
            "uv",
            "run",
            "pytest",
            "tests/test_audit_python_host_core.py",
            "-q",
            "--tb=short",
        ],
        "audit contract tests",
    ),
    (
        ["python3", "scripts/host_delegation_corpus.py"],
        "executable Python/Node delegation corpus",
    ),
    (
        [
            "uv",
            "run",
            "pytest",
            "tests/test_wasm_ticks_chartview_contract.py",
            "-q",
            "--tb=short",
        ],
        "browser adapter structural contract (non-differential)",
    ),
    (
        [
            "uv",
            "run",
            "pytest",
            *[str(path.relative_to(ROOT)) for path in CROSS_HOST_TESTS],
            "-q",
            "--tb=line",
        ],
        "cross-host Scene, static-export, payload, and WASM differential tests",
    ),
)


def main(argv: list[str] | None = None) -> int:
    del argv
    for cmd, label in STEPS:
        print(f"==> {label}", flush=True)
        proc = subprocess.run(cmd, cwd=ROOT, check=False)
        if proc.returncode != 0:
            print(f"host-parity landing gate failed: {label}", file=sys.stderr)
            return proc.returncode
        print(flush=True)
    print("host-parity landing gates: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
