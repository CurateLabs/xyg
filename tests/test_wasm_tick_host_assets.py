from __future__ import annotations

import json
from pathlib import Path

import pytest

from xyg import export
from xyg._figure import Figure

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "python" / "xyg" / "static"
CLIENT = ROOT / "packages" / "xy-client" / "dist"

# `node js/build.mjs` copies wasm-worker.js; the module itself needs
# `node js/package-wasm.mjs` after a wasm32 build. Floor/Test CI only run
# the ordinary client build, so packaging-identity tests stay conditional.
_PACKAGED_WASM = (STATIC / export.WASM_TICK_WASM).is_file() and (
    CLIENT / export.WASM_TICK_WASM
).is_file()
requires_packaged_wasm = pytest.mark.skipif(
    not _PACKAGED_WASM,
    reason="xyg-wasm.wasm not packaged (run node js/package-wasm.mjs)",
)


@requires_packaged_wasm
def test_packaged_tick_assets_match_the_browser_package() -> None:
    assets = export.bundled_wasm_tick_assets()
    worker = assets["worker"]
    wasm = assets["wasm"]
    assert worker == STATIC / export.WASM_TICK_WORKER
    assert wasm == STATIC / export.WASM_TICK_WASM
    assert worker.read_bytes() == (CLIENT / export.WASM_TICK_WORKER).read_bytes()
    assert wasm.read_bytes() == (CLIENT / export.WASM_TICK_WASM).read_bytes()
    assert wasm.read_bytes()[:4] == b"\0asm"


def test_to_html_default_does_not_guess_tick_assets() -> None:
    html = Figure().line([0.0, 1.0, 2.0], [1.0, 2.0, 3.0]).to_html()
    spec_js = html.rsplit("const spec = ", 1)[1].split(";\n  const buf", 1)[0]
    spec = json.loads(spec_js)
    assert "wasm_ticks" not in spec
    assert "connect-src 'none'" in html
    assert "worker-src blob:" in html
    assert "./wasm-worker.js" not in spec_js


def test_to_html_true_requires_a_destination_path() -> None:
    with pytest.raises(ValueError, match="destination path"):
        Figure().line([0.0, 1.0], [1.0, 2.0]).to_html(wasm_ticks=True)


@requires_packaged_wasm
def test_to_html_true_writes_sidecars_and_explicit_urls(tmp_path: Path) -> None:
    target = tmp_path / "chart.html"
    html = Figure().line([0.0, 1.0, 2.0], [0.0, 1.0, 0.0]).to_html(target, wasm_ticks=True)
    worker = tmp_path / export.WASM_TICK_WORKER
    wasm = tmp_path / export.WASM_TICK_WASM
    assert worker.is_file()
    assert wasm.is_file()
    assert worker.read_bytes() == (STATIC / export.WASM_TICK_WORKER).read_bytes()
    assert wasm.read_bytes() == (STATIC / export.WASM_TICK_WASM).read_bytes()
    assert '"wasm_ticks":{"workerUrl":"./wasm-worker.js","wasm":"./xyg-wasm.wasm"}' in html
    assert "connect-src 'self'" in html
    assert "worker-src 'self'" in html
    assert "blob:" not in html.split("Content-Security-Policy", 1)[1].split(">", 1)[0]
    assert target.read_text(encoding="utf-8") == html


def test_to_html_mapping_requires_explicit_urls_and_rejects_blob() -> None:
    fig = Figure().line([0.0, 1.0], [1.0, 2.0])
    with pytest.raises(ValueError, match="worker_url and wasm"):
        fig.to_html(wasm_ticks={"worker_url": "./wasm-worker.js"})
    with pytest.raises(ValueError, match="same-origin"):
        fig.to_html(wasm_ticks={"worker_url": "blob:abc", "wasm": "./xyg-wasm.wasm"})
    with pytest.raises(ValueError, match="same-origin"):
        fig.to_html(wasm_ticks={"worker_url": "./wasm-worker.js", "wasm": "//cdn.example/xyg.wasm"})
    html = fig.to_html(
        wasm_ticks={"worker_url": "/assets/xyg/wasm-worker.js", "wasm": "/assets/xyg/xyg-wasm.wasm"}
    )
    assert '"workerUrl":"/assets/xyg/wasm-worker.js"' in html
    assert '"wasm":"/assets/xyg/xyg-wasm.wasm"' in html
    assert "connect-src 'self'" in html


@requires_packaged_wasm
def test_copy_wasm_tick_assets_writes_exact_packaged_bytes(tmp_path: Path) -> None:
    written = export.copy_wasm_tick_assets(tmp_path)
    assert written["worker"].read_bytes() == (STATIC / export.WASM_TICK_WORKER).read_bytes()
    assert written["wasm"].read_bytes() == (STATIC / export.WASM_TICK_WASM).read_bytes()


def test_polar_live_smoke_requires_real_same_origin_wasm_ticks() -> None:
    source = (ROOT / "scripts" / "polar_phase7_smoke.py").read_text(encoding="utf-8")
    interaction = (ROOT / "benchmarks" / "bench_interaction.py").read_text(encoding="utf-8")
    dashboard = (ROOT / "benchmarks" / "bench_dashboard.py").read_text(encoding="utf-8")

    assert "copy_wasm_tick_assets(output_dir)" in source
    assert '"workerUrl": "./wasm-worker.js"' in source
    assert '"wasm": "./xyg-wasm.wasm"' in source
    assert "http.server.ThreadingHTTPServer" in source
    assert "globalThis.__xygStandaloneObserver" in source
    assert 'event.phase === "ticks_error"' in source
    assert '"ticks_ready", "ticks_error"' in source
    assert "data-xy-polar-smoke" in source
    assert '"workerUrl": "./wasm-worker.js"' in interaction
    assert '"wasm": "./xyg-wasm.wasm"' in interaction
    assert "const tickEvent = await ticksReady" in interaction
    assert "hosted=True" in interaction
    assert "wasm_ticks=True" in interaction
    assert '"workerUrl": "./wasm-worker.js"' in dashboard
    assert '"wasm": "./xyg-wasm.wasm"' in dashboard
    assert 'event.phase !== "ticks_ready"' in dashboard
    assert "tick_ready_charts" in dashboard
    assert "hosted=True" in dashboard
    assert "wasm_ticks=True" in dashboard


def test_bundled_wasm_tick_assets_fail_closed_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "static"
    empty.mkdir()
    monkeypatch.setattr(export, "_STATIC", empty)
    with pytest.raises(FileNotFoundError, match="packaged WASM tick assets missing"):
        export.bundled_wasm_tick_assets()


def test_client_and_export_contract_stay_fail_closed() -> None:
    entries = (ROOT / "js" / "src" / "60_entries.ts").read_text(encoding="utf-8")
    export_src = (ROOT / "python" / "xyg" / "export.py").read_text(encoding="utf-8")
    reflex = (ROOT / "python" / "reflex_xy" / "assets" / "__init__.py").read_text(encoding="utf-8")
    assert "function attachHostWasmTicks" in entries
    assert "attachHostWasmTicks(view, spec)" in entries
    assert entries.count("attachHostWasmTicks(view, spec)") == 2
    assert "blob:|data:|javascript:" in entries
    assert "copy_wasm_tick_assets" in export_src
    assert "resolve_wasm_tick_assets" in export_src
    assert "wasm-worker.js" in reflex
    assert "xyg-wasm.wasm" in reflex
    assert "reflex_wasm_tick_urls" in reflex
    assert "follow-up" not in reflex
    jsx = (ROOT / "python" / "reflex_xy" / "assets" / "XYChart.jsx").read_text(encoding="utf-8")
    assert "attachHostWasmTicks" in jsx
    assert 'new URL("./wasm-worker.js", import.meta.url)' in jsx
    assert 'new URL("./xyg-wasm.wasm", import.meta.url)' in jsx
    assert "attachHostWasmTicks(view, spec)" in jsx


def test_exported_spec_roundtrips_wasm_tick_urls() -> None:
    html = (
        Figure()
        .scatter([0.0, 1.0], [1.0, 0.0])
        .to_html(wasm_ticks={"worker_url": "./wasm-worker.js", "wasm": "./xyg-wasm.wasm"})
    )
    spec_js = html.rsplit("const spec = ", 1)[1].split(";\n  const buf", 1)[0]
    spec = json.loads(spec_js)
    assert spec["wasm_ticks"] == {"workerUrl": "./wasm-worker.js", "wasm": "./xyg-wasm.wasm"}
