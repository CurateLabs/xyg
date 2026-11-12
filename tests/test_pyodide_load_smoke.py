from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


def _load_smoke_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "pyodide_load_smoke.py"
    spec = importlib.util.spec_from_file_location("pyodide_load_smoke", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pyodide_load_smoke = _load_smoke_module()


def test_remote_wheel_url_is_installed_directly(monkeypatch, tmp_path: Path) -> None:
    url = (
        "https://files.pythonhosted.org/packages/example/"
        "xyg-0.0.3-py3-none-pyemscripten_2026_0_wasm32.whl"
    )
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["driver"] = Path(command[1]).read_text(encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='RESULT {"ok":true,"backend":"native","abi":88,"min":1,"max":3,"cases":3,"sceneVersion":11,"painterVersion":8,"filesystemStubs":15,"filterPackets":47,"filterCooperative":true}\n',
            stderr="",
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pyodide_load_smoke.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["pyodide_load_smoke.py", url])

    assert pyodide_load_smoke.main() == 0
    assert observed["command"][2] == url
    assert observed["command"][3].endswith("tests/fixtures/xyts_cross_host.json")
    assert observed["command"][4].endswith("tests/fixtures/filter_tier_c/session.bin")
    assert "await micropip.install(wheelPath)" in observed["driver"]
    assert "offline XYTS fixture attempted fetch" in observed["driver"]
    assert "scene_browser_painter" in observed["driver"]
    assert "xyg_chunked_columns_read_page" in observed["driver"]
    assert not (tmp_path / "_pyodide_load_driver.mjs").exists()


@pytest.mark.parametrize(
    "proof",
    [
        {},
        {"filterPackets": 46, "filterCooperative": True},
        {"filterPackets": 47, "filterCooperative": False},
        {"filterPackets": 47, "filterCooperative": 1},
    ],
)
def test_incomplete_filter_transport_proof_fails(monkeypatch, tmp_path, capsys, proof):
    import json

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 0, stdout="RESULT " + json.dumps({"ok": True, **proof}) + "\n", stderr=""
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pyodide_load_smoke.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["pyodide_load_smoke.py", "https://example.test/xyg.whl"])
    assert pyodide_load_smoke.main() == 1
    assert "filter transport proof missing or incomplete" in capsys.readouterr().out
    assert not (tmp_path / "_pyodide_load_driver.mjs").exists()


def test_pyodide_filter_body_uses_real_native_transport():
    import struct

    from xyg import _native

    body = pyodide_load_smoke._DRIVER.split("lib = _native._lib\n", 1)[1].split("# ABI 396", 1)[0]
    fixture = Path(__file__).parent / "fixtures/filter_tier_c/session.bin"
    body = body.replace('"/fixtures/filter_session.bin"', repr(str(fixture)))
    result = {"lib": _native._lib, "struct": struct}
    exec(compile(body, "<real Pyodide filter probe>", "exec"), result)
    assert result["filter_packets"] == 47
    assert result["filter_progress"] > 0
    assert result["filter_cooperative"] is True
