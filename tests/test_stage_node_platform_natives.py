"""Tests for scripts/stage_node_platform_natives.py (#52)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "stage_node_platform_natives.py"


def _load():
    spec = importlib.util.spec_from_file_location("stage_node_platform_natives", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_platform_matrix_matches_five_supported_packages() -> None:
    mod = _load()
    assert set(mod.PLATFORM_PACKAGES) == {
        ("darwin", "arm64"),
        ("darwin", "x64"),
        ("linux", "x64"),
        ("linux", "arm64"),
        ("win32", "x64"),
    }
    for (plat, arch), (pkg, lib_name) in mod.PLATFORM_PACKAGES.items():
        assert pkg == f"xyg-node-{plat}-{arch}"
        assert (REPO / "packages" / pkg / "package.json").is_file()
        if plat == "win32":
            assert lib_name == "xyg_core.dll"
        elif plat == "darwin":
            assert lib_name == "libxyg_core.dylib"
        else:
            assert lib_name == "libxyg_core.so"


def test_stage_copies_into_platform_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load()
    packages = tmp_path / "packages"
    pkg = packages / "xyg-node-linux-x64"
    pkg.mkdir(parents=True)
    lib = tmp_path / "libxyg_core.so"
    lib.write_bytes(b"native-bytes")
    monkeypatch.setattr(mod, "PACKAGES", packages)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    written = mod.stage(
        node_platform="linux",
        arch="x64",
        lib=lib,
        also_facade=True,
        dry_run=False,
    )
    assert written[0] == pkg / "libxyg_core.so"
    assert written[0].read_bytes() == b"native-bytes"
    facade = packages / "xy-node" / "_native_lib" / "libxyg_core.so"
    assert facade.read_bytes() == b"native-bytes"


def test_stage_rejects_wrong_basename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    monkeypatch.setattr(mod, "PACKAGES", tmp_path / "packages")
    lib = tmp_path / "wrong.so"
    lib.write_bytes(b"x")
    with pytest.raises(SystemExit, match="does not match"):
        mod.stage(
            node_platform="linux",
            arch="x64",
            lib=lib,
            also_facade=False,
            dry_run=False,
        )


def test_list_cli_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    mod = _load()
    assert mod.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "@curatelabs/xyg-node-linux-x64" in out
    assert "win32-x64" in out
