from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = (
    "packages/xy-client/dist/index.js",
    "packages/xy-client/dist/standalone.js",
    "packages/xy-client/dist/xyg-wasm.wasm",
)


@pytest.mark.parametrize("missing", ["native", *ASSETS])
def test_graph_gate_rejects_missing_build_inputs_before_running_tests(
    tmp_path: Path, missing: str
) -> None:
    (tmp_path / "Makefile").write_text((ROOT / "Makefile").read_text(encoding="utf-8"))
    native = tmp_path / "explicit-release-core.so"
    if missing != "native":
        native.touch()
    for asset in ASSETS:
        path = tmp_path / asset
        path.parent.mkdir(parents=True, exist_ok=True)
        if missing != asset:
            path.touch()
    result = subprocess.run(
        ["make", "check-graph", "PYTHON=must-not-run-python"],
        cwd=tmp_path,
        env={**os.environ, "XYG_NATIVE_LIB": str(native)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert (
        "Build the release core first" in result.stderr
        if missing == "native"
        else (f"Missing {missing}" in result.stderr)
    )
    assert "must-not-run-python" not in result.stdout
