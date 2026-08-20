"""Retired XY native identity must not reappear in current-product files."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = ROOT / "scripts" / "check_stale_names.py"
    spec = importlib.util.spec_from_file_location("check_stale_names", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


check_stale_names = _load()


def test_repository_has_no_stale_native_identity() -> None:
    assert check_stale_names.check_stale_names() == []


def test_flags_retired_artifact_and_env_names(tmp_path: Path) -> None:
    (tmp_path / "note.md").write_text("load libxy_core.so via XY_NATIVE_LIB\n", encoding="utf-8")
    errors = check_stale_names.check_stale_names(tmp_path)
    joined = "\n".join(errors)
    assert "libxy_core" in joined
    assert "XY_NATIVE_LIB" in joined


def test_flags_retired_python_import_path_and_public_modules(tmp_path: Path) -> None:
    (tmp_path / "example.py").write_text(
        "import xy\nfrom xy.kernels import BACKEND\n# python/xy/widget.py\n# see xy.export\n",
        encoding="utf-8",
    )
    errors = check_stale_names.check_stale_names(tmp_path)
    joined = "\n".join(errors)
    assert "import xy" in joined
    assert "python/xy package path" in joined
    assert "xy Python module reference" in joined


def test_explicit_line_allow_marker_preserves_compatibility_probe(tmp_path: Path) -> None:
    (tmp_path / "compat.py").write_text(
        "import xy  # xyg-stale-name: allow - rejected legacy import\n",
        encoding="utf-8",
    )
    assert check_stale_names.check_stale_names(tmp_path) == []


def test_flags_retired_public_name_in_python_error_or_docstring(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text(
        '"""Use xy.chart(...)."""\nraise ValueError("pass xy.animation(...)")\n',
        encoding="utf-8",
    )
    errors = check_stale_names.check_stale_names(tmp_path)
    assert sum("xy Python public reference" in error for error in errors) == 2


def test_allows_deferred_browser_global_in_python_template(tmp_path: Path) -> None:
    (tmp_path / "browser.py").write_text(
        'HTML = "xy.renderStandalone(host, spec, buf); xy.decodeFrame(frame)"\n',
        encoding="utf-8",
    )
    assert check_stale_names.check_stale_names(tmp_path) == []


def test_allows_never_publish_warning_and_crate_abi_path(tmp_path: Path) -> None:
    (tmp_path / "ok.md").write_text(
        "Bump ABI_VERSION in `crates/xyg-core/src/lib.rs`.\n"
        "The browser shell is `crates/xyg-wasm/src/lib.rs`.\n"
        "The in-tree directory stays packages/xy-node; never publish `@xy/node`.\n",
        encoding="utf-8",
    )
    assert check_stale_names.check_stale_names(tmp_path) == []


def test_flags_root_src_lib_as_abi_location(tmp_path: Path) -> None:
    (tmp_path / "bad.md").write_text("Bump ABI_VERSION in src/lib.rs\n", encoding="utf-8")
    errors = check_stale_names.check_stale_names(tmp_path)
    assert any("src/lib.rs ABI" in error for error in errors)
