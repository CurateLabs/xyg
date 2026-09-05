"""Smoke tests for the python-scene-migration re-audit script."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


def _load():
    path = Path(__file__).resolve().parents[1] / "scripts" / "audit_python_host_core.py"
    spec = importlib.util.spec_from_file_location("audit_python_host_core", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_audit_lists_no_scene_migration_files():
    mod = _load()
    paths = mod._load_paths(mod.MANIFEST)
    assert len(paths) == 0
    assert "python/xyg/_payload.py" not in paths
    assert "python/xyg/_scene_v3.py" not in paths
    assert "python/xyg/_svg.py" not in paths


def test_keep_host_policy_paths_cover_export_emitters():
    mod = _load()
    manifest = mod._load_manifest(mod.MANIFEST)
    paths = mod._keep_host_policy_paths(manifest)
    # The compatibility emitters are retired; `_static_document.py` is the
    # bounded marshal adapter and `_layout.py` the compat measurement surface.
    assert "python/xyg/_static_document.py" in paths
    assert "python/xyg/_layout.py" in paths
    assert "python/xyg/_scene_marshal.py" in paths
    assert "python/xyg/_payload.py" in paths
    assert "python/xyg/kernels.py" not in paths
    assert not any(path.startswith("python/xyg/_export_") for path in paths)
    assert "python/xyg/_svg_render.py" not in paths
    assert "python/xyg/_raster_render.py" not in paths


def test_node_keep_host_policy_paths_cover_marshal_surfaces():
    mod = _load()
    manifest = mod._load_manifest(mod.MANIFEST)
    paths = mod._node_keep_host_policy_paths(manifest)
    assert "packages/xy-node/src/scene.js" in paths
    assert "packages/xy-node/src/marks/scatter.js" in paths
    assert "packages/xy-node/src/encode.js" in paths
    assert "packages/xy-node/src/abi.js" not in paths


def test_python_native_call_metrics_count_real_calls_not_imports(tmp_path):
    mod = _load()
    source = tmp_path / "host.py"
    source.write_text(
        "from xyg import _native\n"
        "from xyg.kernels import histogram_bins as bins\n"
        "unused = _native\n"
        "a = _native.scene_svg(b'x')\n"
        "b = _native.scene_svg(b'y')\n"
        "c = bins([], [])\n",
        encoding="utf-8",
    )
    metrics = mod._python_native_call_metrics(source)
    assert metrics.lines == 6
    assert metrics.calls == 3
    assert metrics.entries == frozenset({"_native.scene_svg", "bins"})
    assert metrics.calls_per_kloc == 500.0


def test_node_native_call_metrics_count_real_calls_not_imports(tmp_path):
    mod = _load()
    source = tmp_path / "host.js"
    source.write_text(
        'import { xySceneSvg, xyEncodePng as png, unused } from "./native.js";\n'
        'import { helper } from "./encode.js";\n'
        "const a = xySceneSvg(scene);\n"
        "const b = png(scene);\n"
        "const c = png(scene);\n"
        "const d = helper(scene);\n",
        encoding="utf-8",
    )
    metrics = mod._node_native_call_metrics(source)
    assert metrics.lines == 6
    assert metrics.calls == 3
    assert metrics.entries == frozenset({"xySceneSvg", "png"})
    assert metrics.calls_per_kloc == 500.0


def test_real_keep_host_inventory_is_nonempty_without_semantic_floors():
    mod = _load()
    manifest = mod._load_manifest(mod.MANIFEST)
    python_metrics = [
        mod._python_native_call_metrics(mod.ROOT / path)
        for path in mod._keep_host_policy_paths(manifest)
    ]
    node_metrics = [
        mod._node_native_call_metrics(mod.ROOT / path)
        for path in mod._node_keep_host_policy_paths(manifest)
    ]
    assert python_metrics
    assert node_metrics
    assert all(item.lines > 0 for item in python_metrics)
    assert all(item.lines > 0 for item in node_metrics)


def test_audit_cli_exits_zero():
    from xyg._abi_generated import ABI_VERSION

    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(root / "scripts" / "audit_python_host_core.py")],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "python-scene-migration core-logic re-audit" in proc.stdout
    assert "No python-scene-migration production files remain." in proc.stdout
    assert f"abi_version: {ABI_VERSION}" in proc.stdout
    assert "Merged scene lane on main" in proc.stdout
    assert "Merged payload stack on main" in proc.stdout
    assert "Merged payload orchestration on main" in proc.stdout
    assert "Merged scene orchestration on main" in proc.stdout
    assert "Merged payload gather/ship on main" in proc.stdout
    assert "Merged host materialization retirement" in proc.stdout
    assert "Host materialization retirement CLOSED" in proc.stdout
    assert "#768" in proc.stdout
    assert "xyg_payload_column_ship_plan" in proc.stdout
    assert "xyg_payload_channel_wire_encode" in proc.stdout
    assert "M2 close contract (#731 — CLOSED 2026-08-31)" in proc.stdout
    assert "#731 CLOSED" in proc.stdout
    assert "#733 CLOSED" in proc.stdout
    assert "xyg_payload_density_grid_ship_plan" in proc.stdout
    assert "#732 CLOSED" in proc.stdout
    assert "Remaining close blockers" in proc.stdout
    assert "#731 close checklist" in proc.stdout
    assert "Node stay-host TAP" in proc.stdout
    assert "Secondary §302" in proc.stdout
    assert "Advisory keep-host source inventory" in proc.stdout
    assert "node keep-host policy files:" in proc.stdout
    assert "syntactic native call expressions" in proc.stdout
    assert "referenced ABI entries" in proc.stdout
    assert "references/KLOC" in proc.stdout
    assert "not execution or ownership proof" in proc.stdout
    assert "delegate hooks" not in proc.stdout.split("Advisory keep-host source inventory", 1)[1]
    assert "Cross-host disposition parity" in proc.stdout
    assert "node-scene-migration files: 0" in proc.stdout
    assert "WASM / browser host parity inventory" in proc.stdout
    assert "Browser tick policy is closed by #869" in proc.stdout
    assert "browser-scene-migration files: 0" in proc.stdout
    assert "browser-scene-migration compatibility generators:" not in proc.stdout
    assert "browser-wasm-adapter modules:" in proc.stdout
    differential = proc.stdout.split("differential proof contracts:", 1)[1].split(
        "structural adapter contracts", 1
    )[0]
    assert "tests/test_wasm_ticks_chartview_contract.py" not in differential
    assert "tests/test_*cross_host*.py" in differential
    assert "tests/test_scene_trace_pack_abi.py" in differential
    assert "tests/test_scene_chrome_pack_abi.py" in differential
    assert "structural adapter contracts (not parity differentials):" in proc.stdout
    assert "tests/test_wasm_ticks_chartview_contract.py" in proc.stdout
    assert "Residual host materialization" not in proc.stdout
    assert "do not mark M2 complete" not in proc.stdout
