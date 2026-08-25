"""The C ABI manifest stays in lock-step with Rust, Python, Node, and smoke."""

from __future__ import annotations

import importlib.util
import subprocess
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
abi_smoke = _load("abi_smoke_for_tests", "abi_smoke.py")


def test_checked_in_manifest_matches_rust_exports() -> None:
    assert gen_abi_manifest.main(["--check"]) == 0


def test_host_declarations_match_rust_symbol_set() -> None:
    errors = check_abi_parity.check_abi_parity()
    assert errors == []


def test_abi_version_is_97() -> None:
    manifest = gen_abi_manifest.generate_manifest()
    assert manifest["abi_version"] == 97
    assert manifest["artifact"] == "xyg_core"
    assert all(item["name"].startswith("xyg_") for item in manifest["symbols"])
    assert any(item["name"] == "xyg_abi_version" for item in manifest["symbols"])
    names = {item["name"] for item in manifest["symbols"]}
    assert "xyg_graph_force_create_cose" in names
    assert "xyg_graph_compound_transition" in names
    assert {
        "xyg_chunked_columns_cancel_before",
        "xyg_chunked_columns_free",
        "xyg_chunked_columns_open",
        "xyg_chunked_columns_overview",
        "xyg_chunked_columns_read",
        "xyg_chunked_columns_read_page",
        "xyg_chunked_columns_rows",
    } <= names
    assert any(item["name"] == "xyg_temporal_controller_create" for item in manifest["symbols"])
    assert any(item["name"] == "xyg_scene_plot_layout" for item in manifest["symbols"])
    assert any(item["name"] == "xyg_geo_column_new" for item in manifest["symbols"])
    assert any(item["name"] == "xyg_pyramid_spill" for item in manifest["symbols"])
    assert any(item["name"] == "xyg_tile_store_compose" for item in manifest["symbols"])
    assert any(item["name"] == "xyg_graph_label_accept" for item in manifest["symbols"])
    assert any(item["name"] == "xyg_graph_compound_bounds" for item in manifest["symbols"])
    assert any(item["name"] == "xyg_graph_visual_state_resolve" for item in manifest["symbols"])


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


def test_signature_drift_names_symbol_and_old_new_signatures() -> None:
    prefix = "pub const ABI_VERSION: u32 = 1;\n#[no_mangle]\n"
    previous = gen_abi_manifest.parse_rust_abi(
        prefix + 'pub extern "C" fn xyg_order(a: u32, b: u64) -> i32 { 0 }'
    )
    current = gen_abi_manifest.parse_rust_abi(
        prefix + 'pub extern "C" fn xyg_order(b: u64, a: u32) -> i32 { 0 }'
    )

    assert check_abi_parity.describe_signature_changes(previous, current) == [
        "xyg_order: `int32_t xyg_order(uint32_t a, uint64_t b)` -> "
        "`int32_t xyg_order(uint64_t b, uint32_t a)`"
    ]


def test_abi_history_scan_is_not_revision_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []

    def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(check_abi_parity.subprocess, "run", fake_run)

    assert list(check_abi_parity.iter_prior_abi_contracts(ROOT)) == []
    assert commands and "-n" not in commands[0]


def test_missing_generated_consumers_return_actionable_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    generated = {"abi_version": 1, "signature_sha256": "hash", "symbols": []}
    generated_py = tmp_path / "python/xyg/_abi_generated.py"
    generated_js = tmp_path / "packages/xy-node/src/_abi_generated.js"
    monkeypatch.setattr(check_abi_parity, "generate_manifest", lambda _root: generated)
    monkeypatch.setattr(check_abi_parity, "render_manifest", lambda _manifest: "{}\n")
    monkeypatch.setattr(
        check_abi_parity,
        "generated_outputs",
        lambda _root: {generated_py: "", generated_js: ""},
    )

    errors = check_abi_parity.check_abi_parity(tmp_path)

    assert any("python/xyg/_abi_generated.py is stale" in error for error in errors)
    assert any("packages/xy-node/src/_abi_generated.js is stale" in error for error in errors)
    assert any("scripts/abi_smoke.py is missing" in error for error in errors)


def test_abi_smoke_reports_missing_generated_declarations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(abi_smoke, "ROOT", tmp_path)

    with pytest.raises(SystemExit, match=r"gen_abi_manifest\.py --write"):
        abi_smoke._expected_abi_version()


def test_bazel_abi_lookup_falls_back_when_generated_constant_is_unparseable(
    tmp_path: Path,
) -> None:
    generated = tmp_path / "python/xyg/_abi_generated.py"
    generated.parent.mkdir(parents=True)
    generated.write_text("ABI_VERSION: int = 59\n", encoding="utf-8")
    rust = tmp_path / "crates/xyg-core/src/lib.rs"
    rust.parent.mkdir(parents=True)
    rust.write_text("pub const ABI_VERSION: u32 = 59;\n", encoding="utf-8")

    result = subprocess.run(
        [
            "/bin/bash",
            "-c",
            'source "$1"; expected_abi_from_source "$2"',
            "bazel-abi-test",
            str(ROOT / "tools/bazel/common.sh"),
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "59"


def test_low_level_signatures_exist_only_in_generated_modules() -> None:
    python_host = (ROOT / "python/xyg/_native.py").read_text(encoding="utf-8")
    node_host = (ROOT / "packages/xy-node/src/native.js").read_text(encoding="utf-8")
    generated_python = (ROOT / "python/xyg/_abi_generated.py").read_text(encoding="utf-8")
    generated_node = (ROOT / "packages/xy-node/src/_abi_generated.js").read_text(encoding="utf-8")
    assert ".argtypes" not in python_host and ".restype" not in python_host
    assert "lib.func(" not in node_host
    assert ".argtypes" in generated_python and ".restype" in generated_python
    assert "lib.func(" in generated_node
    assert node_host.index("bindAbiVersion(lib)") < node_host.index("bindGeneratedAbi(lib)")
