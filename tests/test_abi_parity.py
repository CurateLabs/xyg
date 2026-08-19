"""The C ABI manifest stays in lock-step with Rust, Python, Node, and smoke."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

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


def test_manifest_preserves_order_width_and_pointer_direction() -> None:
    manifest = gen_abi_manifest.generate_manifest()
    symbol = next(item for item in manifest["symbols"] if item["name"] == "xyg_encode_f32")
    assert [item["name"] for item in symbol["arguments"]] == [
        "data",
        "len",
        "offset",
        "scale",
        "out",
    ]
    expected = {
        "rust": "*const f64",
        "c": "const double *",
        "pointer_depth": 1,
        "direction": "in",
        "nullable": "contract-defined",
    }
    assert {key: symbol["arguments"][0]["type"][key] for key in expected} == expected
    assert symbol["arguments"][-1]["type"]["direction"] == "out"
    assert symbol["returns"]["bits"] == 32


def test_unsupported_rust_ffi_type_is_rejected() -> None:
    source = """
pub const ABI_VERSION: u32 = 1;
#[no_mangle]
pub extern "C" fn xyg_bad(value: bool) -> i32 { 0 }
"""
    with pytest.raises(ValueError, match="unsupported Rust FFI type 'bool'"):
        gen_abi_manifest.parse_rust_abi(source)


def test_signature_order_changes_contract_hash() -> None:
    prefix = "pub const ABI_VERSION: u32 = 1;\n#[no_mangle]\n"
    first = gen_abi_manifest.parse_rust_abi(
        prefix + 'pub extern "C" fn xyg_order(a: u32, b: u64) -> i32 { 0 }'
    )
    second = gen_abi_manifest.parse_rust_abi(
        prefix + 'pub extern "C" fn xyg_order(b: u64, a: u32) -> i32 { 0 }'
    )
    assert first["signature_sha256"] != second["signature_sha256"]
    assert first["symbols"][0]["arguments"] != second["symbols"][0]["arguments"]


def test_low_level_signatures_exist_only_in_generated_modules() -> None:
    python_host = (ROOT / "python/xy/_native.py").read_text(encoding="utf-8")
    node_host = (ROOT / "packages/xy-node/src/native.js").read_text(encoding="utf-8")
    generated_python = (ROOT / "python/xy/_abi_generated.py").read_text(encoding="utf-8")
    generated_node = (ROOT / "packages/xy-node/src/_abi_generated.js").read_text(encoding="utf-8")
    assert ".argtypes" not in python_host and ".restype" not in python_host
    assert "lib.func(" not in node_host
    assert ".argtypes" in generated_python and ".restype" in generated_python
    assert "lib.func(" in generated_node
    assert node_host.index("bindAbiVersion(lib)") < node_host.index("bindGeneratedAbi(lib)")
