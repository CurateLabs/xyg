#!/usr/bin/env python3
"""Generate/check #875's Rust-owned static-export fixture registry."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "static_export_support_registry.json"


def _from_rust() -> bytes:
    proc = subprocess.run(
        ["cargo", "run", "--quiet", "-p", "xyg-engine", "--example", "static_export_registry"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    payload = json.loads(proc.stdout)
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    expected = _from_rust()
    if args.write:
        FIXTURE.write_bytes(expected)
        print(f"wrote {FIXTURE.relative_to(ROOT)}")
        return 0
    if not FIXTURE.is_file() or FIXTURE.read_bytes() != expected:
        raise SystemExit(
            "static-export support registry is stale; run "
            "python3 scripts/static_export_support_registry.py --write"
        )
    print("static-export support registry: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
