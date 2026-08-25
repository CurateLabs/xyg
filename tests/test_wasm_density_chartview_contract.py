from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_direct_wasm_density_is_a_chartview_lifecycle_adapter_not_a_second_algorithm() -> None:
    source = (ROOT / "js" / "src" / "49_wasm_density.ts").read_text(encoding="utf-8")
    assert "aggregateWasmBin2d" in source
    assert "decodeWasmAggregateOutput" in source
    assert "_applySampleRebinGrid" in source
    assert "_uploadGrid" in source
    assert "xyCreateRebinWorker" not in source
    assert "new Float32Array(w * h)" not in source


def test_standalone_retained_sample_can_create_an_explicit_local_wasm_adapter() -> None:
    source = (ROOT / "js" / "src" / "49_wasm_density.ts").read_text(encoding="utf-8")
    kernel = (ROOT / "js" / "src" / "54_kernel.ts").read_text(encoding="utf-8")
    browser = (ROOT / "tests" / "browser" / "wasm_foundation_page.mjs").read_text(encoding="utf-8")
    assert "attachStandaloneWasmDensity" in source
    assert "createXygWasmWorker(options)" in source
    assert "sampleRebin: targets.length === 1" in source
    assert "XY_REBIN_WORKER_SRC" not in source
    assert "if (this._wasmDensity) return this._wasmDensity.schedule(viewOverride, opts);" in kernel
    assert "kernel-less retained-sample density uses local Rust/WASM" in browser
    assert "attachStandaloneWasmDensity(standaloneDensityView" in browser
    assert "_rebinWorker" not in browser


def test_direct_wasm_density_rejects_stale_work_and_chart_destroy_disposes_it() -> None:
    source = (ROOT / "js" / "src" / "49_wasm_density.ts").read_text(encoding="utf-8")
    chartview = (ROOT / "js" / "src" / "50_chartview.ts").read_text(encoding="utf-8")
    kernel = (ROOT / "js" / "src" / "54_kernel.ts").read_text(encoding="utf-8")
    assert "this.task?.cancel()" in source
    assert "sequence !== this.sequence" in source
    assert "this.view._wasmDensity !== this" in source
    assert '"wasm_density_error"' in source
    assert "this._wasmDensity?.destroy?.();" in chartview
    assert "if (this._wasmDensity) return this._wasmDensity.schedule(viewOverride, opts);" in kernel


def test_direct_wasm_density_is_public_and_documents_explicit_trace_sources() -> None:
    entries = (ROOT / "js" / "src" / "60_entries.ts").read_text(encoding="utf-8")
    doc = (ROOT / "spec" / "design" / "browser-wasm.md").read_text(encoding="utf-8")
    api = (ROOT / "spec" / "api" / "browser-wasm.md").read_text(encoding="utf-8")
    assert "attachWasmDensity" in entries
    assert "XygWasmDensityHandle" in entries
    assert "attached kernel-backed scatter workload" in doc
    assert "provisionKernelWasmDensity" in entries
    assert "automatic source provisioning" in doc
    assert "## ChartView density refinement" in api
    assert "xy:wasm_density_error" in api


def test_self_contained_density_uses_only_the_inline_classic_wasm_contract() -> None:
    entries = (ROOT / "js" / "src" / "60_entries.ts").read_text(encoding="utf-8")
    density = (ROOT / "js" / "src" / "49_wasm_density.ts").read_text(encoding="utf-8")
    export = (ROOT / "python" / "xyg" / "export.py").read_text(encoding="utf-8")
    api = (ROOT / "spec" / "api" / "browser-wasm.md").read_text(encoding="utf-8")
    assert "attachInlineStandaloneWasmDensity" in entries
    assert "__xygInlineWasm" in entries
    assert "inline standalone density" in density
    assert '_bundled_js("xyg-wasm-inline")' in export
    assert "inputs" in api
    assert "distinct trace ids" in api
    assert "kernel `density_view` fallback" in api
    assert "automatic source provisioning" in api
    assert "no JavaScript density aggregation fallback" in api


def test_direct_wasm_density_multitrace_keeps_rust_as_the_only_aggregator() -> None:
    source = (ROOT / "js" / "src" / "49_wasm_density.ts").read_text(encoding="utf-8")
    assert "private readonly inputs" in source
    assert "for (const input of this.inputs)" in source
    assert "this.view._axisRange(g.xAxis, snapshot)" in source
    assert "aggregateWasmBin2d(this.worker" in source
    assert "xyCreateRebinWorker" not in source


def test_legacy_density_worker_is_absent_and_unsupported_exports_are_explicit() -> None:
    kernel = (ROOT / "js" / "src" / "54_kernel.ts").read_text(encoding="utf-8")
    entries = (ROOT / "js" / "src" / "60_entries.ts").read_text(encoding="utf-8")
    assert not (ROOT / "js" / "src" / "46_worker.ts").exists()
    for marker in (
        "xyCreateRebinWorker",
        "_rebinWorker",
        "_rebinInit",
        "_requestSampleRebin",
        "_onRebinResult",
    ):
        assert marker not in kernel
    assert '"wasm_density_no_refinement"' in kernel
    assert "XYG_WASM_SOURCE_UNAVAILABLE" in entries
    assert "XYG_WASM_UNAVAILABLE" in entries


def test_kernel_backed_density_automatically_provisions_one_supported_typed_source() -> None:
    source = (ROOT / "js" / "src" / "49_wasm_density.ts").read_text(encoding="utf-8")
    kernel = (ROOT / "js" / "src" / "54_kernel.ts").read_text(encoding="utf-8")
    browser = (ROOT / "tests" / "browser" / "wasm_foundation_page.mjs").read_text(encoding="utf-8")
    assert "function retainedSampleInput" in source
    assert "export function provisionKernelWasmDensity" in source
    assert "view.spec?.wasm_density?.automatic !== true" in source
    assert 'workerOwnership: "own"' in source
    assert "provisionKernelWasmDensity(this, viewOverride, opts)" in kernel
    assert "automatic kernel-backed WASM density lifecycle" in browser


def test_kernel_backed_typed_source_contract_streams_replayable_full_source_without_removing_sample_support() -> (
    None
):
    source = (ROOT / "js" / "src" / "49_wasm_density.ts").read_text(encoding="utf-8")
    assert "const typedInputs = inputs as XygWasmDensityInput[]" in source
    assert "worker, inputs: typedInputs" in source
    assert "const full = fullSourceInput(view)" in source
    assert "if (!full && !targets.length) return null" in source
    assert "this.worker.aggregateStream" in source
    assert "streamSource: full !== null" in source
    assert "installAggregateSource" not in source
    assert "retireTransferredFullSource" not in source


def test_standalone_adapter_accepts_supported_multi_trace_sources_without_js_aggregation() -> None:
    source = (ROOT / "js" / "src" / "49_wasm_density.ts").read_text(encoding="utf-8")
    assert "inputs: inputs as XygWasmDensityInput[]" in source
    assert "sampleRebin: targets.length === 1" in source
