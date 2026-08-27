from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_chartview_wasm_ticks_are_a_lifecycle_adapter_not_a_generator() -> None:
    ticks = (ROOT / "js" / "src" / "49_wasm_ticks.ts").read_text(encoding="utf-8")
    chartview = (ROOT / "js" / "src" / "50_chartview.ts").read_text(encoding="utf-8")

    assert "export async function attachWasmTicks" in ticks
    assert "resolveWasmTicks(this.worker" in ticks
    assert "family," in ticks
    assert 'provenance: authored?.provenance ?? "automatic"' in ticks
    assert "authoredPlane" in ticks
    assert "authored_values" in ticks
    assert "authored_empty" in ticks
    assert "actual.provenance !== expected.provenance" in ticks
    assert "Array.isArray(axis.tick_values) || axis.theta_unit" not in ticks
    assert 'from "./30_ticks"' not in ticks
    assert "linearTicks(" not in ticks
    assert "logTicks(" not in ticks
    assert "fmtAxis(" not in ticks
    assert "const wasmTicks = this._wasmTicks?.ticks?.(axisId)" in chartview
    assert "this._wasmTicks?.label?.(axisId, Number(value))" in chartview
    assert "this._wasmTicks?.covers?.(axisId)" in chartview
    assert chartview.index("const wasmTicks = this._wasmTicks?.ticks?.(axisId)") < chartview.index(
        "if (Array.isArray(axis.tick_values))"
    )
    assert chartview.index("this._wasmTicks?.covers?.(axisId)") < chartview.index(
        "if (Array.isArray(axis.tick_values))"
    )
    assert "primarySlot" in ticks
    assert "slotEligible" in ticks
    assert "eligible(axisId: unknown)" in ticks
    assert 'source: "wasm"' in ticks
    assert "this.cache.has(slot)" in ticks
    assert (
        'return { ticks: Object.freeze([]), labels: Object.freeze([]), step: 1, source: "wasm" }'
        not in ticks
    )


def test_chartview_wasm_ticks_are_latest_wins_and_destroy_safe() -> None:
    ticks = (ROOT / "js" / "src" / "49_wasm_ticks.ts").read_text(encoding="utf-8")
    chartview = (ROOT / "js" / "src" / "50_chartview.ts").read_text(encoding="utf-8")
    browser = (ROOT / "tests" / "browser" / "wasm_foundation_page.mjs").read_text(encoding="utf-8")

    assert "this.cancelActive()" in ticks
    assert "this.requestedKey !== frame.key" in ticks
    assert "this.frame()?.key === frame.key" in ticks
    assert "ownsAttachment()" in ticks
    assert "!this.active || this.view._wasmTicks === this" in ticks
    assert "this.disposed || this.view._destroyed || !this.ownsAttachment()" in ticks
    assert "lastErrorKey" in ticks
    assert "failedKey" not in ticks
    assert (
        "frame.key === this.admittedKey || (frame.key === this.requestedKey && this.task)" in ticks
    )
    assert "this.view._layout()" not in ticks
    assert "this.view.draw()" in ticks
    assert '"wasm_ticks_error"' in ticks
    assert "this.view._wasmTicks === this" in ticks
    assert ticks.index("await handle.initialize();") < ticks.index("handle.activate();")
    assert ticks.index("handle.activate();") < ticks.index("view._wasmTicks = handle;")
    assert ticks.index("view._wasmTicks = handle;") < ticks.index("previous?.destroy?.();")
    assert "this._wasmTicks?.destroy?.();" in chartview
    assert "ChartView tick latest-wins admission" in browser
    assert 'retainedXTicks.source !== "wasm"' in browser
    assert "uncovered after attach does not emit" in browser
    assert "sequential ChartView tick re-attach replaces the previous handle" in browser
    assert "secondary ChartView axes stay on the compatibility tick path" in browser
    assert "newly eligible axis after attach does not paint empty wasm" in browser
    assert "primary Cartesian ChartView category and UTC-time ticks use Rust/WASM" in browser
    assert "primary Cartesian ChartView authored and authored-empty ticks use Rust/WASM" in browser
    assert "authored ChartView ticks on category and UTC-time axes use Rust/WASM" in browser
    assert "authored provenance switch after attach waits for a matching Rust cache" in browser
    assert "family switch after attach waits for a matching Rust cache" in browser
    assert "failed ChartView tick snapshot retries without a second event" in browser


def test_chartview_wasm_tick_assets_and_scope_are_explicit() -> None:
    ticks = (ROOT / "js" / "src" / "49_wasm_ticks.ts").read_text(encoding="utf-8")
    package = (ROOT / "packages" / "xy-client" / "package.json").read_text(encoding="utf-8")
    entries = (ROOT / "js" / "src" / "60_entries.ts").read_text(encoding="utf-8")
    api = (ROOT / "spec" / "api" / "browser-wasm.md").read_text(encoding="utf-8")
    design = (ROOT / "spec" / "design" / "browser-wasm.md").read_text(encoding="utf-8")

    assert '"./wasm-worker": "./dist/wasm-worker.js"' in package
    assert '"./xyg-wasm.wasm": "./dist/xyg-wasm.wasm"' in package
    assert "attachWasmTicks" in entries
    assert "XygWasmTicksHandle" in entries
    assert entries.split("// Public API.", 1)[1].count("attachWasmTicks") == 1
    assert "xy:wasm_ticks_error" in api
    assert "and ChartView may admit" in api
    assert "GL lifecycle" not in api
    assert "this.view._glLost" not in ticks
    assert "Angular/polar, secondary-axis" in api
    assert "authored-value, and authored-empty" in api
    assert "authored-value, and authored-empty" in design
    assert '"utc_time"' in ticks
    assert 'family === "category"' in ticks
    assert "slotIdentity" in ticks
    assert "this.cache.get(slot)?.identity === this.slotIdentity(slot)" in ticks
    assert "Hosted `to_html(" in api
    assert "xyg/static/" in api
    assert "Blob-worker HTML remains" in design
    assert "stays open" in design
    assert "attachHostWasmTicks" in entries
    assert "axis.theta_unit" in ticks
    assert 'if (eligible) throw new TypeError("tick range must be finite")' in ticks
    assert "return null;" in ticks
    assert "lastErrorKey" in api
    assert "`_layout()`" in api
    assert "eligible" in design
