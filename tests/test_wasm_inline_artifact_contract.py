from __future__ import annotations

from pathlib import Path


def test_wasm_packager_emits_deterministic_classic_inline_contract() -> None:
    source = (Path(__file__).resolve().parents[1] / "js" / "package-wasm.mjs").read_text()
    assert '"xyg-wasm-inline.js"' in source
    assert "globalThis.__xygInlineWasm" in source
    assert "classicWorkerSource" in source
    assert '"wasm-inline-worker.js"' in source
    assert 'createHash("sha256")' in source
    assert 'bytes.toString("base64")' in source


def test_offline_fixture_forbids_network_or_module_worker_loading() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "tests" / "browser" / "inline_wasm_worker_fixture.mjs"
    ).read_text()
    assert "verifyInlineWasmWorker" in source
    assert "inline WASM classic worker is not offline-safe" in source
    assert "worker.terminate()" in source


def test_inline_classic_worker_keeps_aggregate_protocol_out_of_modules() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "js" / "src" / "wasm_inline_worker.ts"
    ).read_text(encoding="utf-8")
    assert 'message?.type === "aggregate.bin2d"' in source
    assert "xyg_wasm_aggregate_step" in source
    assert "XYG_WASM_AGGREGATE_CHECKPOINT_POINTS" in source
    assert 'message?.type === "cancel"' in source
    assert 'message?.type === "diagnostics"' in source
    assert "fetch(" not in source
    assert "importScripts(" not in source
