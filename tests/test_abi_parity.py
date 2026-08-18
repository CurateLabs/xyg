"""The C ABI manifest stays in lock-step with Rust, Python, Node, and smoke."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str):
    path = ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gen_abi_manifest = _load("gen_abi_manifest", "gen_abi_manifest.py")
check_abi_parity = _load("check_abi_parity", "check_abi_parity.py")


def test_checked_in_manifest_matches_rust_exports() -> None:
    assert gen_abi_manifest.main(["--check"]) == 0


def test_host_declarations_match_rust_symbol_set() -> None:
    errors = check_abi_parity.check_abi_parity()
    assert errors == []


def test_abi_version_is_59() -> None:
    manifest = gen_abi_manifest.generate_manifest()
    assert manifest["abi_version"] == 59
    assert manifest["artifact"] == "xyg_core"
    assert all(item["name"].startswith("xyg_") for item in manifest["symbols"])
    assert any(item["name"] == "xyg_abi_version" for item in manifest["symbols"])
