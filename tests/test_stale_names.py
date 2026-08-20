"""Legacy native identity must not reappear in current-product files."""

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


def test_flags_retired_artifact_and_backticked_api_docs(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text(
        "WHEEL=/tmp/xy.whl\n# call `xy.legend()`\n",
        encoding="utf-8",
    )
    errors = check_stale_names.check_stale_names(tmp_path)
    joined = "\n".join(errors)
    assert "xy wheel artifact" in joined
    assert "backticked xy Python API" in joined


def test_flags_artifact_glob_pip_show_and_corrupted_upstream(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text(
        "verify dist/xy-*.whl dist/xy-*.tar.gz\n"
        "python -m pip show xy\n"
        "upstream XYG policy at reflex-dev/XYG\n",
        encoding="utf-8",
    )
    errors = "\n".join(check_stale_names.check_stale_names(tmp_path))
    assert errors.count("xy artifact glob") == 2
    assert "pip show xy" in errors
    assert errors.count("corrupted upstream XYG") == 2


def test_allows_exact_upstream_and_historical_identifiers(tmp_path: Path) -> None:
    (tmp_path / "history.md").write_text(
        "upstream XY came from " + "reflex-dev/" + "xy\nXY-vs-XYG policy retains XY-SEC-2026-03\n",
        encoding="utf-8",
    )
    assert check_stale_names.check_stale_names(tmp_path) == []


def test_flags_product_wording_across_runtime_docs_and_workflows(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "graph.md").write_text("## xy-native inputs\n", encoding="utf-8")
    (tmp_path / "runtime.ts").write_text(
        'throw new Error("Update the xy package");\n', encoding="utf-8"
    )
    (tmp_path / "workflow.yml").write_text(
        "# build the editable xy dependency\n"
        "run: bench --packages xy,plotly && pip install 'xy[reflex]'\n",
        encoding="utf-8",
    )
    errors = check_stale_names.check_stale_names(tmp_path)
    joined = "\n".join(errors)
    assert "xy-native product wording" in joined
    assert joined.count("retired xy product description") == 2
    assert "retired xy benchmark target" in joined
    assert "retired xy distribution constraint" in joined


def test_flags_current_brand_and_user_facing_alias(tmp_path: Path) -> None:
    (tmp_path / "example.py").write_text(
        '"""Build an XY chart."""\nimport xyg as xy\n', encoding="utf-8"
    )
    errors = "\n".join(check_stale_names.check_stale_names(tmp_path))
    assert "current product XY brand" in errors
    assert "user-facing xyg alias" in errors


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


def test_repository_module_descriptions_reject_ambiguous_xy_product_wording(
    tmp_path: Path,
) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "bench.py").write_text('"""Benchmark for the xy package."""\n', encoding="utf-8")
    errors = check_stale_names._module_description_errors(
        scripts / "bench.py", "scripts/bench.py", (scripts / "bench.py").read_text()
    )
    assert any("product/API wording" in error for error in errors)


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
