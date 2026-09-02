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
    assert "python/xyg/_export_marks_svg.py" in paths
    assert "python/xyg/_scene_marshal.py" in paths
    assert "python/xyg/_payload.py" in paths
    assert "python/xyg/kernels.py" not in paths


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
    assert "Keep-host policy surface audit" in proc.stdout
    assert "Cross-host disposition parity" in proc.stdout
    assert "node-scene-migration files:" in proc.stdout
    assert "Residual host materialization" not in proc.stdout
    assert "do not mark M2 complete" not in proc.stdout
