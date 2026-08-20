"""Tests for scripts/verify_node_packages.py (#52)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "verify_node_packages.py"


def _load():
    spec = importlib.util.spec_from_file_location("verify_node_packages", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_verify_passes_on_checkout() -> None:
    mod = _load()
    inventory = mod.verify(require_native=False)
    assert inventory["ok"] is True
    assert inventory["errors"] == []
    assert inventory["facade"]["name"] == "@curatelabs/xyg-node"
    assert set(inventory["platforms"]) == {
        "darwin-arm64",
        "darwin-x64",
        "linux-x64",
        "linux-arm64",
        "win32-x64",
    }
    for _plat_id, entry in inventory["platforms"].items():
        assert entry["native"] is None  # not staged in a clean checkout
        assert entry["package_json_sha256"]
        assert entry["index_sha256"]


def test_cli_write_inventory(tmp_path: Path) -> None:
    mod = _load()
    out = tmp_path / "inventory.json"
    assert mod.main(["--write", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["ok"] is True
    assert "facade" in data


def test_require_native_fails_without_staged_libs() -> None:
    mod = _load()
    inventory = mod.verify(require_native=True)
    assert inventory["ok"] is False
    assert any("required native missing" in err for err in inventory["errors"])
