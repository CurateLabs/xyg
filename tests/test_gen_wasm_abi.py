from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gen_wasm_abi", ROOT / "scripts" / "gen_wasm_abi.py")
assert SPEC and SPEC.loader
GEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GEN)


def manifest() -> dict[str, object]:
    return json.loads((ROOT / "spec/wasm/abi.json").read_text())


def rejected(change) -> None:
    value = copy.deepcopy(manifest())
    change(value)
    with pytest.raises(SystemExit):
        GEN.validate_typed_series(value)


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value["typed_series"].update(extra=1),
        lambda value: value["typed_series"].pop("kinds"),
        lambda value: value["typed_series"].update(request_magic="AB"),
        lambda value: value["typed_series"].update(request_magic="AB🔥D"),
        lambda value: value["typed_series"]["header_offsets"].update(width=41),
        lambda value: value["typed_series"]["header_offsets"].update(width=True),
        lambda value: value["typed_series"]["header_offsets"].update(width="40"),
        lambda value: value["typed_series"]["header_offsets"].update(width=40.0),
        lambda value: value["typed_series"]["header_offsets"].update(height=40),
        lambda value: value["typed_series"]["descriptor_offsets"].update(diameters=96),
        lambda value: value["typed_series"]["descriptor_offsets"].pop("symbol"),
        lambda value: value["typed_series"]["header_flags"].update(auto_domain=3),
        lambda value: value["typed_series"]["header_flags"].update(auto_domain=True),
        lambda value: value["typed_series"]["flags"].update(y0="2"),
        lambda value: value["typed_series"]["flags"].update(y0=2.0),
        lambda value: value["typed_series"]["flags"].update(y0=1),
        lambda value: value["typed_series"]["flags"].update(y0=1 << 32),
        lambda value: value["typed_series"].update(
            kinds={"scatter": 0, "line": 1, "bar": 2, "area": 4}
        ),
        lambda value: value["typed_series"].update(
            kinds={"scatter": False, "line": 1, "bar": 2, "area": 3}
        ),
        lambda value: value.update(typed_series_version=True),
        lambda value: value.update(typed_series_header_bytes="192"),
        lambda value: value.update(typed_series_peak_bytes_per_record=256.0),
    ],
)
def test_typed_series_manifest_mutations_fail_closed(change) -> None:
    rejected(change)


def test_generated_typescript_and_rust_contracts_are_exact() -> None:
    value = manifest()
    GEN.validate_typed_series(value)
    assert (ROOT / "js/src/wasm_abi_generated.ts").read_text() == GEN.render(value)
    assert (
        ROOT / "crates/xyg-wasm/src/typed_series_abi_generated.rs"
    ).read_text() == GEN.render_typed_series_rust(value)
    assert (
        ROOT / "python/xyg/_wasm_aggregate_generated.py"
    ).read_text() == GEN.render_python_aggregate(value)


def test_rust_decoder_consumes_generated_contract_without_wire_constants() -> None:
    source = (ROOT / "crates/xyg-wasm/src/compile.rs").read_text()
    assert "use crate::typed_series_abi_generated::*;" in source
    assert 'SERIES_MAGIC: &[u8; 4] = b"XYTS"' not in source
    assert "flags & !DESCRIPTOR_FLAG_KNOWN" in source
    assert "KIND_SCATTER | KIND_LINE | KIND_BAR | KIND_AREA" in source


@pytest.mark.parametrize(
    ("suffix", "before", "after"),
    [
        (
            "crates/xyg-wasm/src/compound.rs",
            "OUTPUT_CHANGED_OFFSET: usize = 12",
            "OUTPUT_CHANGED_OFFSET: usize = 13",
        ),
        (
            "crates/xyg-engine/src/graph_style.rs",
            "COMPOUND_ACTION_TOGGLE: u8 = 2",
            "COMPOUND_ACTION_TOGGLE: u8 = 3",
        ),
        (
            "crates/xyg-engine/src/graph_style.rs",
            "GRAPH_LOD_DIRECT: u8 = 0",
            "GRAPH_LOD_DIRECT: u8 = 1",
        ),
        (
            "crates/xyg-engine/src/graph_style.rs",
            "MAX_COMPOUND_TRANSITION_NODES: usize = 1_024",
            "MAX_COMPOUND_TRANSITION_NODES: usize = 2_048",
        ),
    ],
)
def test_check_rejects_compound_rust_protocol_drift(
    monkeypatch: pytest.MonkeyPatch, suffix: str, before: str, after: str
) -> None:
    original = Path.read_text

    def drifted(path: Path, *args, **kwargs) -> str:
        source = original(path, *args, **kwargs)
        if str(path).endswith(suffix):
            assert before in source
            return source.replace(before, after, 1)
        return source

    monkeypatch.setattr(Path, "read_text", drifted)
    monkeypatch.setattr(sys, "argv", ["gen_wasm_abi.py", "--check"])
    with pytest.raises(SystemExit):
        GEN.main()


def test_dashboard_planner_export_is_generated_and_signature_checked() -> None:
    value = manifest()
    export = next(item for item in value["exports"] if item["name"] == "xyg_wasm_dashboard_plan")
    assert export == {
        "name": "xyg_wasm_dashboard_plan",
        "params": ["u32", "u32", "usize", "usize"],
        "result": "i32",
    }
    generated = (ROOT / "js/src/wasm_abi_generated.ts").read_text()
    assert (
        "xyg_wasm_dashboard_plan(arg0: number, arg1: number, arg2: number, arg3: number): number;"
        in generated
    )
    assert "raw.xyg_wasm_dashboard_plan" in generated


def test_streaming_aggregate_manifest_is_count_only_and_generated() -> None:
    value = manifest()
    aggregate = value["aggregate"]
    assert aggregate["stream_magic"] == "XYAS"
    assert aggregate["stream_version"] == 1
    assert aggregate["stream_header_bytes"] == 64
    assert aggregate["stream_header_offsets"] == aggregate["request_offsets"]
    assert aggregate["stream_chunk_points"] == aggregate["checkpoint_points"]
    assert aggregate["stream_chunk_bytes"] == aggregate["stream_chunk_points"] * 16
    assert aggregate["stream_chunk_copy_factor"] == 2
    exports = {item["name"]: item for item in value["exports"]}
    assert exports["xyg_wasm_aggregate_stream_begin"] == {
        "name": "xyg_wasm_aggregate_stream_begin",
        "params": ["u32", "u32", "usize", "usize"],
        "result": "i32",
    }
    assert exports["xyg_wasm_aggregate_stream_push"] == {
        "name": "xyg_wasm_aggregate_stream_push",
        "params": ["u32", "u32", "usize", "usize"],
        "result": "i32",
    }
    assert exports["xyg_wasm_aggregate_stream_finish"] == {
        "name": "xyg_wasm_aggregate_stream_finish",
        "params": ["u32", "u32"],
        "result": "i32",
    }
    generated = (ROOT / "js/src/wasm_abi_generated.ts").read_text()
    assert 'XYG_WASM_AGGREGATE_STREAM_MAGIC = "XYAS"' in generated
    assert "raw.xyg_wasm_aggregate_stream_push" in generated
    assert (
        "WASM_AGGREGATE_MAX_POINTS = 8000000"
        in (ROOT / "python/xyg/_wasm_aggregate_generated.py").read_text()
    )
