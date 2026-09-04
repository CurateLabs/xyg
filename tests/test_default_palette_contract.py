from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from xyg import kernels
from xyg.config import DEFAULT_PALETTE, default_mark_color

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "default_palette_contract.json").read_text()
)


def test_python_lazy_proxy_reads_exact_native_palette_contract() -> None:
    version, colors, rgba = kernels.default_palette_contract()
    assert version == FIXTURE["version"]
    assert list(colors) == FIXTURE["colors"]
    np.testing.assert_array_equal(rgba, np.asarray(FIXTURE["rgba8"], dtype=np.uint8))
    assert list(DEFAULT_PALETTE) == FIXTURE["colors"]
    assert default_mark_color() == FIXTURE["default_mark_color"]


def test_host_production_sources_do_not_copy_default_palette_literals() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in ("python/xyg", "packages/xy-node/src", "crates/xyg-wasm/src"):
        for path in (root / relative).rglob("*"):
            if path.suffix in {".py", ".js", ".rs", ".ts"}:
                source = path.read_text().lower()
                copied = [color for color in FIXTURE["colors"] if color in source]
                assert not copied, (path.relative_to(root), copied)

    engine = root / "crates" / "xyg-engine" / "src"
    definitions = []
    for path in engine.rglob("*.rs"):
        for line in path.read_text().splitlines():
            if "pub const DEFAULT_PALETTE:" in line:
                definitions.append(path.relative_to(root).as_posix())
    assert definitions == ["crates/xyg-engine/src/kernels.rs"]
