"""Release staging contracts for the host-neutral XYG browser package."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts import stage_browser_package as stage_browser


def _dist(path: Path) -> Path:
    path.mkdir()
    for name in stage_browser.ASSETS:
        payload = b"\0asm\x01\0\0\0" if name.endswith(".wasm") else b"export const xyg=true;\n"
        (path / name).write_bytes(payload)
    return path


def test_stage_browser_package_is_exact_versioned_offline_inventory(tmp_path: Path) -> None:
    source = _dist(tmp_path / "dist")
    staged = stage_browser.stage(dist=source, output=tmp_path / "out", version="1.2.3-rc.4")
    package = json.loads((staged / "package.json").read_text())
    assets = json.loads((staged / "ASSET-MANIFEST.json").read_text())

    assert package["name"] == "@curatelabs/xyg"
    assert package["version"] == "1.2.3-rc.4"
    assert "private" not in package
    assert package["files"] == ["dist", "ASSET-MANIFEST.json", "README.md", "NOTICE", "LICENSE"]
    assert package["exports"] == stage_browser.EXPECTED_EXPORTS
    assert not any(
        package.get(field) for field in ("dependencies", "optionalDependencies", "peerDependencies")
    )
    assert assets["package"] == "@curatelabs/xyg"
    assert assets["packageVersion"] == "1.2.3-rc.4"
    assert set(assets["assets"]) == set(stage_browser.ASSETS)
    assert assets["wireProtocolVersion"] > 0
    assert assets["wasmAbiVersion"] > 0
    assert assets["sceneVersion"] > 0
    assert assets["painterVersion"] > 0
    assert (staged / "NOTICE").is_file()
    assert (staged / "LICENSE").is_file()


@pytest.mark.parametrize("extra", ["bundle.js.map", "legacy-xy.js"])
def test_stage_rejects_undeclared_or_source_map_assets(tmp_path: Path, extra: str) -> None:
    source = _dist(tmp_path / "dist")
    (source / extra).write_text("unexpected")
    with pytest.raises(ValueError, match="inventory must be exactly"):
        stage_browser.stage(dist=source, output=tmp_path / "out", version="1.2.3")


@pytest.mark.parametrize(
    "reference", ["https://cdn.example/x.js", "python/xyg/static/index.js", "@xy/client"]
)
def test_stage_rejects_network_repo_and_fork_origin_references(
    tmp_path: Path, reference: str
) -> None:
    source = _dist(tmp_path / "dist")
    (source / "index.js").write_text(f"export const source={reference!r};\n")
    with pytest.raises(ValueError, match=r"forbidden (network URL|offline reference)"):
        stage_browser.stage(dist=source, output=tmp_path / "out", version="1.2.3")


def test_stage_allows_dom_namespace_uris(tmp_path: Path) -> None:
    source = _dist(tmp_path / "dist")
    (source / "index.js").write_text(
        "export const svg='http://www.w3.org/2000/svg';"
        "export const html='http://www.w3.org/1999/xhtml';\n"
    )
    stage_browser.stage(dist=source, output=tmp_path / "out", version="1.2.3")


def test_stage_rejects_invalid_wasm(tmp_path: Path) -> None:
    source = _dist(tmp_path / "dist")
    (source / "xyg-wasm.wasm").write_bytes(b"not wasm")
    with pytest.raises(ValueError, match="invalid module header"):
        stage_browser.stage(dist=source, output=tmp_path / "out", version="1.2.3")
