from __future__ import annotations

import copy
import importlib.util
import json
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


def test_rust_decoder_consumes_generated_contract_without_wire_constants() -> None:
    source = (ROOT / "crates/xyg-wasm/src/compile.rs").read_text()
    assert "use crate::typed_series_abi_generated::*;" in source
    assert 'SERIES_MAGIC: &[u8; 4] = b"XYTS"' not in source
    assert "flags & !DESCRIPTOR_FLAG_KNOWN" in source
    assert "KIND_SCATTER | KIND_LINE | KIND_BAR | KIND_AREA" in source
