from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_chartview_wasm_ticks_are_a_lifecycle_adapter_not_a_generator() -> None:
    ticks = (ROOT / "js" / "src" / "49_wasm_ticks.ts").read_text(encoding="utf-8")
    chartview = (ROOT / "js" / "src" / "50_chartview.ts").read_text(encoding="utf-8")

    assert "export async function attachWasmTicks" in ticks
    assert "resolveWasmTicks(this.worker" in ticks
    assert "family," in ticks
    assert 'provenance: "automatic"' in ticks
    assert "linearTicks(" not in ticks
    assert "logTicks(" not in ticks
    assert "const wasmTicks = this._wasmTicks?.ticks?.(axisId)" in chartview
    assert "const wasmLabel = this._wasmTicks?.label?.(" in chartview


def test_chartview_wasm_ticks_are_latest_wins_and_destroy_safe() -> None:
    ticks = (ROOT / "js" / "src" / "49_wasm_ticks.ts").read_text(encoding="utf-8")
    chartview = (ROOT / "js" / "src" / "50_chartview.ts").read_text(encoding="utf-8")
    browser = (ROOT / "tests" / "browser" / "wasm_foundation_page.mjs").read_text(encoding="utf-8")

    assert "this.cancelActive()" in ticks
    assert "this.requestedKey !== frame.key" in ticks
    assert "this.frame().key === frame.key" in ticks
    assert "this.view._wasmTicks !== this" in ticks
    assert '"wasm_ticks_error"' in ticks
    assert "this._wasmTicks?.destroy?.();" in chartview
    assert "ChartView tick latest-wins admission" in browser
    assert 'retainedXTicks.source !== "wasm"' in browser


def test_chartview_wasm_tick_assets_and_scope_are_explicit() -> None:
    package = (ROOT / "packages" / "xy-client" / "package.json").read_text(encoding="utf-8")
    entries = (ROOT / "js" / "src" / "60_entries.ts").read_text(encoding="utf-8")
    api = (ROOT / "spec" / "api" / "browser-wasm.md").read_text(encoding="utf-8")
    design = (ROOT / "spec" / "design" / "browser-wasm.md").read_text(encoding="utf-8")

    assert '"./wasm-worker": "./dist/wasm-worker.js"' in package
    assert '"./xyg-wasm.wasm": "./dist/xyg-wasm.wasm"' in package
    assert "attachWasmTicks" in entries
    assert "XygWasmTicksHandle" in entries
    assert "xy:wasm_ticks_error" in api
    assert "Category, time, angular/polar" in api
    assert "Notebook, `to_html()`, Reflex" in api
    assert "Self-contained" in design
    assert "claims nor closes that issue" in design
