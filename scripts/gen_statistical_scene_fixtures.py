#!/usr/bin/env python3
"""Regenerate statistical Scene goldens from canonical Python/Node authoring.

XYG_NATIVE_LIB=target/release/libxyg_core.dylib uv run python \
    scripts/gen_statistical_scene_fixtures.py --write
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests" / f"test_{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("canonical fixture authoring module unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def generate(name: str) -> dict[str, str]:
    module = load(name)
    node_scenes = module._node_scenes()
    if name == "exact_ecdf_scene":
        cases = {"mixed": [3.0, float("nan"), 1.0, 3.0, 2.0, float("inf")], "singleton": [7.0]}
        figures = {key: module._figure(value) for key, value in cases.items()}
    else:
        figures = {key: module._figure(*value) for key, value in module.CASES.items()}
    digests = {}
    for key, figure in figures.items():
        scene = figure.to_scene()
        if scene != node_scenes[key]:
            raise RuntimeError(f"{name}/{key}: Python/Node canonical Scene bytes disagree")
        digests[key] = hashlib.sha256(scene).hexdigest()
    return digests


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write validated canonical fixtures")
    args = parser.parse_args()
    for name in ("binned_ecdf_scene", "exact_ecdf_scene", "histogram_auto_scene"):
        fixture = ROOT / "tests" / "fixtures" / f"{name}.json"
        expected = generate(name)
        if args.write:
            fixture.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
        elif json.loads(fixture.read_text()) != expected:
            raise RuntimeError(f"stale canonical fixture: {fixture.name}; run --write")
        print(f"{name}: {len(expected)} Python/Node exact-byte cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
