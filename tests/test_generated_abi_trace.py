"""Privacy and fail-closed tests for generated ABI boundary tracing (#874)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PALETTE_SYMBOLS = {
    "xyg_default_palette_version",
    "xyg_default_palette_rows",
    "xyg_default_palette_utf8",
    "xyg_default_palette_rgba8",
}


def _native_library() -> Path:
    if sys.platform == "win32":
        name = "xyg_core.dll"
    elif sys.platform == "darwin":
        name = "libxyg_core.dylib"
    else:
        name = "libxyg_core.so"
    return ROOT / "target" / "release" / name


class _FakeFunction:
    def __init__(self, result: int = 7) -> None:
        self.result = result
        self.calls: list[tuple[object, ...]] = []
        self.restype: object = None
        self.argtypes: list[object] = []

    def __call__(self, *args: object) -> int:
        self.calls.append(args)
        return self.result


class _FakeLibrary:
    def __init__(self) -> None:
        self.functions: dict[str, _FakeFunction] = {}

    def __getattr__(self, name: str) -> _FakeFunction:
        return self.functions.setdefault(name, _FakeFunction())


def test_python_generated_trace_records_shapes_without_values() -> None:
    from xyg._abi_generated import bind_generated_abi, trace_generated_abi

    library = _FakeLibrary()
    bind_generated_abi(library)  # type: ignore[arg-type]
    events: list[dict[str, object]] = []
    traced = trace_generated_abi(library, events.append)

    assert traced.xyg_argsort_stable(123456, 4, 654321, 9) == 7
    assert library.functions["xyg_argsort_stable"].calls == [(123456, 4, 654321, 9)]
    assert events == [
        {
            "call_index": 1,
            "symbol": "xyg_argsort_stable",
            "arguments": {
                "data": {"kind": "pointer", "present": True},
                "len": {"kind": "size", "value": "4"},
                "out": {"kind": "pointer", "present": True},
                "capacity": {"kind": "size", "value": "9"},
            },
            "outcome": "ok",
            "returned_size": "7",
        }
    ]
    assert "123456" not in json.dumps(events)
    assert "654321" not in json.dumps(events)


def test_python_generated_trace_fault_is_observed_and_propagates() -> None:
    from xyg._abi_generated import (
        GeneratedAbiTraceFault,
        bind_generated_abi,
        trace_generated_abi,
    )

    library = _FakeLibrary()
    bind_generated_abi(library)  # type: ignore[arg-type]
    events: list[dict[str, object]] = []
    traced = trace_generated_abi(library, events.append, {"xyg_argsort_stable"})

    with pytest.raises(GeneratedAbiTraceFault, match="XYG_ABI_TRACE_FAULT"):
        traced.xyg_argsort_stable(None, 0, None, 0)

    assert library.functions["xyg_argsort_stable"].calls == []
    assert events[0]["outcome"] == "injected_fault"


def test_dead_python_call_does_not_create_an_event() -> None:
    from xyg._abi_generated import bind_generated_abi, trace_generated_abi

    library = _FakeLibrary()
    bind_generated_abi(library)  # type: ignore[arg-type]
    events: list[dict[str, object]] = []
    traced = trace_generated_abi(library, events.append)

    def unreachable() -> int:
        return traced.xyg_argsort_stable(None, 0, None, 0)

    assert callable(unreachable)
    assert events == []


def test_node_generated_trace_uses_live_bindings_and_restores_raw_call() -> None:
    generated = (ROOT / "packages/xy-node/src/_abi_generated.js").as_uri()
    source = f"""
import * as abi from {json.dumps(generated)};
const calls = [];
const lib = {{ func(signature) {{
  return (...args) => {{ calls.push([signature, args]); return 7; }};
}} }};
abi.bindGeneratedAbi(lib);
const events = [];
abi._testConfigureGeneratedAbiTrace((event) => events.push(event));
const value = abi.xyArgsortStable(new Uint8Array([19]), 4, new Uint8Array([23]), 9);
abi._testConfigureGeneratedAbiTrace(null);
abi.xyArgsortStable(null, 0, null, 0);
process.stdout.write(JSON.stringify({{ value, events, calls: calls.length }}));
"""
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", source],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["value"] == 7
    assert result["calls"] == 2
    assert result["events"] == [
        {
            "call_index": 1,
            "symbol": "xyg_argsort_stable",
            "arguments": {
                "data": {"kind": "pointer", "present": True},
                "len": {"kind": "size", "value": "4"},
                "out": {"kind": "pointer", "present": True},
                "capacity": {"kind": "size", "value": "9"},
            },
            "outcome": "ok",
            "returned_size": "7",
        }
    ]


def test_node_generated_trace_fault_propagates_before_raw_call() -> None:
    generated = (ROOT / "packages/xy-node/src/_abi_generated.js").as_uri()
    source = f"""
import * as abi from {json.dumps(generated)};
let calls = 0;
const lib = {{ func() {{ return () => {{ calls += 1; return 7; }}; }} }};
abi.bindGeneratedAbi(lib);
const events = [];
abi._testConfigureGeneratedAbiTrace((event) => events.push(event), ["xyg_argsort_stable"]);
let error = null;
try {{ abi.xyArgsortStable(null, 0, null, 0); }} catch (caught) {{
  error = {{ name: caught.name, message: caught.message }};
}}
process.stdout.write(JSON.stringify({{ calls, events, error }}));
"""
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", source],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["calls"] == 0
    assert result["events"][0]["outcome"] == "injected_fault"
    assert result["error"] == {
        "name": "GeneratedAbiTraceFault",
        "message": "XYG_ABI_TRACE_FAULT:xyg_argsort_stable",
    }


def test_generator_emits_private_trace_hooks_without_changing_abi_version() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import gen_abi_manifest
    finally:
        sys.path.pop(0)

    manifest = gen_abi_manifest.generate_manifest()
    python = gen_abi_manifest.render_python_bindings(manifest)
    node = gen_abi_manifest.render_node_bindings(manifest)
    assert "trace_generated_abi" in python
    assert "_testConfigureGeneratedAbiTrace" in node
    assert "'kind': 'pointer'" in python
    assert 'kind: "pointer", present:' in node
    from xyg._abi_generated import ABI_VERSION

    assert manifest["abi_version"] == ABI_VERSION


def test_default_palette_journey_is_a_cross_host_versioned_byte_proof() -> None:
    corpus = json.loads((ROOT / "spec" / "design" / "host-delegation-corpus.json").read_text())
    journeys = [item for item in corpus["journeys"] if item["id"] == "default-palette"]
    assert len(journeys) == 1
    journey = journeys[0]
    assert set(journey["hosts"]) == {"python", "node"}
    assert set(journey["required_shared_symbols"]) == PALETTE_SYMBOLS
    assert journey["commands"] == [
        [
            "uv",
            "run",
            "pytest",
            "tests/test_default_palette_contract.py",
            "-q",
            "--tb=short",
        ],
        ["node", "--test", "packages/xy-node/test/default-palette-contract.test.mjs"],
    ]
    assert "tests/fixtures/default_palette_contract.json" in journey["output_oracle"]
    assert "xyg.default-palette/v1" in journey["output_oracle"]


@pytest.mark.parametrize("host", ["python", "node"])
def test_real_product_fault_injection_fails_before_canonical_output(
    host: str, tmp_path: Path
) -> None:
    native = _native_library()
    if not native.is_file():
        pytest.skip(f"missing {native}; run cargo build --release")
    trace = tmp_path / f"{host}.jsonl"
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "python"),
        "XYG_NATIVE_LIB": str(native),
        "XYG_ABI_TRACE_FILE": str(trace),
        "XYG_ABI_TRACE_JOURNEY": "fault-control",
        "XYG_ABI_TRACE_FAULT": "xyg_payload_build_plan",
    }
    if host == "python":
        command = [
            sys.executable,
            "-c",
            "import xyg; xyg.scatter_chart(xyg.scatter(x=[0,1], y=[1,2])).figure().build_payload()",
        ]
    else:
        node = shutil.which("node")
        if not node:
            pytest.skip("node is not available")
        command = [
            node,
            "--input-type=module",
            "-e",
            "import('./packages/xy-node/src/index.js').then(x => "
            "x.scatterChart(new Float64Array([0,1]), new Float64Array([1,2])).buildPayload())",
        ]
    proc = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode != 0
    events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    faults = [event for event in events if event["outcome"] == "injected_fault"]
    assert [event["symbol"] for event in faults] == ["xyg_payload_build_plan"]


def test_semantic_verifier_rejects_dead_call_and_host_local_fixture() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        from host_delegation_corpus import DelegationFailure, verify_journey
    finally:
        sys.path.pop(0)

    contract = {
        "id": "negative",
        "hosts": ["python", "node"],
        "required_shared_symbols": ["xyg_payload_build_plan"],
        "surfaces": ["fixture"],
        "output_oracle": "negative control",
    }
    with pytest.raises(DelegationFailure, match="no executed ABI calls"):
        verify_journey(contract, [])

    host_local = [
        {
            "journey": "negative",
            "host": "python",
            "type": "host_fallback",
            "outcome": "ok",
            "symbol": "host_local_canonical_sort",
        },
        {
            "journey": "negative",
            "host": "node",
            "outcome": "ok",
            "symbol": "xyg_payload_build_plan",
        },
    ]
    with pytest.raises(DelegationFailure, match="host-local canonical fallback"):
        verify_journey(contract, host_local)
