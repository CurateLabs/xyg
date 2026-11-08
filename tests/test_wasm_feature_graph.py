"""The shipping browser admits shared PNG while excluding native raster policy."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "wasm_feature_check", ROOT / "scripts/check_wasm_features.py"
)
assert SPEC and SPEC.loader
FEATURES = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = FEATURES
SPEC.loader.exec_module(FEATURES)
TREE = (
    f"xyg-wasm v0.1.0 ({ROOT}/crates/xyg-wasm)|\n"
    f"xyg-engine v0.1.0 ({ROOT}/crates/xyg-engine)|frozen-raster\n"
    f"png v0.18.1 ({ROOT}/vendor/png)|\n"
    "flate2 v1.1.9|any_impl,default,miniz_oxide,rust_backend\n"
    "miniz_oxide v0.8.9|default,with-alloc\n"
)


def test_shared_frozen_png_admitted_without_full_native_raster():
    FEATURES.check(TREE)
    # Cargo deduplicates common descendants; repeated package facts stay equal.
    FEATURES.check(TREE + "flate2 v1.1.9|any_impl,default,miniz_oxide,rust_backend (*)\n")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("|frozen-raster", "|default,frozen-raster,raster"),
        ("|frozen-raster", "|frozen-raster,raster"),
        ("|frozen-raster", "|"),
        ("|frozen-raster", "|frozen-raster,unknown"),
        ("xyg-wasm v0.1.0", "xyg-core v0.1.0"),
        ("png v0.18.1", "png v0.18.2"),
        (f"png v0.18.1 ({ROOT}/vendor/png)|", "png v0.18.1|"),
        (f"({ROOT}/vendor/png)|", f"({ROOT}/vendor/png)|unstable"),
        (f"({ROOT}/crates/xyg-engine)", "(/unexpected/engine)"),
        ("|frozen-raster", ""),
        (TREE, ""),
        (TREE, TREE + "xyg-core v0.1.0|\n"),
        (TREE, TREE + f"xyg-engine v0.1.1 ({ROOT}/crates/xyg-engine)|frozen-raster\n"),
        (TREE, TREE + f"png v0.17.0 ({ROOT}/vendor/png)|\n"),
    ],
)
def test_native_or_unbound_dependency_graph_rejected(old, new):
    with pytest.raises(ValueError):
        FEATURES.check(TREE.replace(old, new))
