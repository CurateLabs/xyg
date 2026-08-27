"""Reflex XYChart auto-attach of packaged WASM tick assets.

Skip the whole module when Reflex is not installed (plain ``xyg`` must never
require it). Browser E2E of the attach is later evidence.
"""

from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("reflex")
pytest.importorskip("reflex_xy")

from reflex_xy.assets import (  # noqa: E402
    _EXTERNAL_SUBDIR,
    _WASM_TICK_ASSETS,
    _link_client,
    _wasm_tick_sources,
    reflex_wasm_tick_urls,
)
from xyg.export import WASM_TICK_WASM, WASM_TICK_WORKER, resolve_wasm_tick_assets  # noqa: E402

ADAPTER_ASSETS = pathlib.Path(__file__).resolve().parents[2] / "python" / "reflex_xy" / "assets"


def test_reflex_wasm_tick_urls_match_export_contract():
    """Sibling URLs go through resolve_wasm_tick_assets — no guessed paths."""
    urls = reflex_wasm_tick_urls()
    sources = _wasm_tick_sources()
    if sources is None:
        assert urls is None
        return
    expected = resolve_wasm_tick_assets(
        {
            "worker_url": f"./{WASM_TICK_WORKER}",
            "wasm": f"./{WASM_TICK_WASM}",
        }
    )
    assert urls == expected
    assert urls == {"workerUrl": "./wasm-worker.js", "wasm": "./xyg-wasm.wasm"}
    assert set(_WASM_TICK_ASSETS) == {WASM_TICK_WORKER, WASM_TICK_WASM}


def test_reflex_wasm_tick_urls_fail_closed_when_missing(monkeypatch):
    monkeypatch.setattr("reflex_xy.assets._wasm_tick_sources", lambda: None)
    assert reflex_wasm_tick_urls() is None


def test_reflex_wasm_tick_urls_reject_blob_and_cdn():
    with pytest.raises(ValueError, match="same-origin"):
        resolve_wasm_tick_assets(
            {"worker_url": "blob:abc", "wasm": "./xyg-wasm.wasm"},
        )
    with pytest.raises(ValueError, match="same-origin"):
        resolve_wasm_tick_assets(
            {"worker_url": "./wasm-worker.js", "wasm": "//cdn.example/xyg.wasm"},
        )


def test_link_client_links_tick_assets_as_a_pair(tmp_path, monkeypatch):
    """A missing sibling leaves both unlinked — never a partial pair."""
    dest = tmp_path / _EXTERNAL_SUBDIR
    monkeypatch.setattr("reflex_xy.assets._wasm_tick_sources", lambda: None)
    _link_client(tmp_path)
    assert not (dest / WASM_TICK_WORKER).exists()
    assert not (dest / WASM_TICK_WASM).exists()

    worker = tmp_path / WASM_TICK_WORKER
    wasm = tmp_path / WASM_TICK_WASM
    worker.write_text("export {}", encoding="utf-8")
    wasm.write_bytes(b"\0asm")
    pair = {WASM_TICK_WORKER: worker, WASM_TICK_WASM: wasm}
    monkeypatch.setattr("reflex_xy.assets._wasm_tick_sources", lambda: pair)
    _link_client(tmp_path)
    assert (dest / WASM_TICK_WORKER).resolve() == worker.resolve()
    assert (dest / WASM_TICK_WASM).resolve() == wasm.resolve()


def test_xychart_auto_attaches_explicit_sibling_tick_urls():
    jsx = (ADAPTER_ASSETS / "XYChart.jsx").read_text(encoding="utf-8")
    assert 'from "./xy_client.js"' in jsx
    assert "attachHostWasmTicks" in jsx
    assert "withWasmTicks" in jsx
    assert "reflexWasmTickAssets" in jsx
    assert 'new URL("./wasm-worker.js", import.meta.url)' in jsx
    assert 'new URL("./xyg-wasm.wasm", import.meta.url)' in jsx
    assert "wasm_ticks: reflexWasmTickAssets()" in jsx
    # Live ChartView construction attaches after the view exists; updatePayload
    # keeps the existing handle and must not re-attach.
    fresh_mount = jsx.split("view = new ChartView(", 1)[1]
    assert fresh_mount.index("attachHostWasmTicks(view, spec)") < fresh_mount.index(
        "mountTooltipSlot(view)"
    )
    assert jsx.count("attachHostWasmTicks(view, spec)") == 1
    in_place = jsx.split("view?.updatePayload?.", 1)[1].split("reclaimTooltipSlot();", 1)[0]
    assert "attachHostWasmTicks" not in in_place
    # Static path injects wasm_ticks so renderStandalone's attachHostWasmTicks runs.
    assert (
        "renderStandalone(\n"
        "          el, withHoverFlag(withWasmTicks(fitSpecToElement(frame.message))), "
        "frame.buffers[0])"
    ) in jsx
    assert "const spec = withHoverFlag(withWasmTicks(eventSpec(data.spec, cbRef.current)))" in jsx
    # Fail-closed: no Blob/CDN/eval/path probing in the wrapper attach.
    assert "blob:" not in jsx.lower()
    assert "cdn" not in jsx.lower()
    assert "eval(" not in jsx


def test_xychart_does_not_guess_tick_asset_paths():
    jsx = (ADAPTER_ASSETS / "XYChart.jsx").read_text(encoding="utf-8")
    assets = (ADAPTER_ASSETS / "__init__.py").read_text(encoding="utf-8")
    assert "https://" not in jsx
    assert "http://" not in jsx
    assert "unpkg" not in jsx
    assert "jsdelivr" not in jsx
    assert "resolve_wasm_tick_assets" in assets
    assert "never invent" in assets
    assert "follow-up" not in assets
