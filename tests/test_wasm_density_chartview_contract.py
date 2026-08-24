from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_direct_wasm_density_is_a_chartview_lifecycle_adapter_not_a_second_algorithm() -> None:
    source = (ROOT / "js" / "src" / "49_wasm_density.ts").read_text(encoding="utf-8")
    assert 'import { aggregateWasmBin2d } from "./49_wasm_aggregate";' in source
    assert "_applySampleRebinGrid" in source
    assert "_uploadGrid" in source
    assert "xyCreateRebinWorker" not in source
    assert "for (let index" not in source


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


def test_direct_wasm_density_is_public_and_documented_as_one_explicit_trace() -> None:
    entries = (ROOT / "js" / "src" / "60_entries.ts").read_text(encoding="utf-8")
    doc = (ROOT / "spec" / "design" / "browser-wasm.md").read_text(encoding="utf-8")
    api = (ROOT / "spec" / "api" / "browser-wasm.md").read_text(encoding="utf-8")
    assert "attachWasmDensity" in entries
    assert "XygWasmDensityHandle" in entries
    assert "attached kernel-backed scatter workload" in doc
    assert "automatic source provisioning" in doc
    assert "## Opt-in ChartView density refinement" in api
    assert "xy:wasm_density_error" in api
    assert "multiple traces" in api
    assert "kernel `density_view` fallback" in api
    assert "automatic source provisioning" in api
    assert "fallback deletion" in api
