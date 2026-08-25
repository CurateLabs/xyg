from __future__ import annotations

from pathlib import Path


def test_wasm_packager_emits_deterministic_classic_inline_contract() -> None:
    source = (Path(__file__).resolve().parents[1] / "js" / "package-wasm.mjs").read_text()
    assert '"xyg-wasm-inline.js"' in source
    assert "globalThis.__xygInlineWasm" in source
    assert "classicWorkerSource" in source
    assert "xyg-inline-wasm-init" in source
    assert 'createHash("sha256")' in source
    assert "bytes.toString(\"base64\")" in source
