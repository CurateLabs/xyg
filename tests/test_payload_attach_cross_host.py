"""Cross-host buildPayload ABI 303 attach parity: Python vs @curatelabs/xyg-node.

Compares optional top-level attach fields governed by ``payload_build_plan``:
``wasm_density``, ``frame_sides``, ``show_modebar``, ``export``, ``show_tooltip``,
``tooltip``, ``mark_style``, ``interaction``, ``animation``, ``graph``, and ``palette``.

Run::

    cargo build --release
    cd packages/xy-node && npm ci   # once
    XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so \\
      uv run pytest tests/test_payload_attach_cross_host.py -q
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from xyg import _native
from xyg._figure import Figure
from xyg.config import PROTOCOL_VERSION

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "payload_attach_cross_host.mjs"
FIXTURE_WRITER = (
    ROOT
    / "packages"
    / "xy-node"
    / "test"
    / "fixtures"
    / "write_payload_attach_cross_host_fixtures.py"
)
FIXTURE_JSON = ROOT / "tests" / "fixtures" / "payload_attach_cross_host.json"

CASE_NAMES = (
    "wasm_density_automatic_split",
    "wasm_density_unsupported_split",
    "frame_sides_bottom_left",
    "show_modebar_false",
    "export_formats",
    "show_tooltip_false",
    "tooltip_fields",
    "mark_style_hover",
    "interaction_select",
    "animation_duration",
    "graph_meta",
    "palette_list",
    "palette_map",
)


def _native_lib() -> Path:
    if sys.platform == "win32":
        name = "xyg_core.dll"
    elif sys.platform == "darwin":
        name = "libxyg_core.dylib"
    else:
        name = "libxyg_core.so"
    return ROOT / "target" / "release" / name


LIB = _native_lib()


def _node_bin() -> str:
    return shutil.which("node") or ""


def _column_dtype(columns: dict[str, Any] | list[dict[str, Any]], col_ref: Any) -> str | None:
    if col_ref is None:
        return None
    if isinstance(columns, list):
        if not isinstance(col_ref, int) or col_ref < 0 or col_ref >= len(columns):
            return None
        return columns[col_ref].get("dtype")
    return columns.get(col_ref, {}).get("dtype")


def _wasm_density_meta(spec: dict[str, Any]) -> dict[str, Any] | None:
    wasm_density = spec.get("wasm_density")
    if wasm_density is None:
        return None
    source = wasm_density.get("source")
    columns = spec.get("columns") or {}
    source_meta = None
    if source is not None:
        source_meta = {
            "kind": source.get("kind"),
            "point_count": source.get("point_count"),
            "trace_id": source.get("trace_id"),
            "capacity": source.get("capacity"),
            "ownership": source.get("ownership"),
            "x_dtype": _column_dtype(columns, source.get("x")),
            "y_dtype": _column_dtype(columns, source.get("y")),
        }
    return {
        "automatic": wasm_density.get("automatic"),
        "unsupported": wasm_density.get("unsupported"),
        "source": source_meta,
    }


def _attach_entry(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "wasm_density": _wasm_density_meta(spec),
        "frame_sides": spec.get("frame_sides"),
        "show_modebar": spec.get("show_modebar"),
        "export": spec.get("export"),
        "show_tooltip": spec.get("show_tooltip"),
        "tooltip": spec.get("tooltip"),
        "mark_style": spec.get("mark_style"),
        "interaction": spec.get("interaction"),
        "animation": spec.get("animation"),
        "graph": spec.get("graph"),
        "palette": spec.get("palette"),
        "buffer_layout": spec.get("buffer_layout"),
    }


def _build_case(name: str) -> Figure:
    fig = Figure(width=240, height=160)
    if name == "wasm_density_automatic_split":
        fig.scatter([1.0, 10.0], [1.0, 10.0], density=True)
        fig.traces[0].id = 41
        return fig
    if name == "wasm_density_unsupported_split":
        fig.scatter([0.0, 1.0, 2.0], [0.0, 1.0, 0.5], density=True, color=[1, 2, 3])
        fig.traces[0].id = 42
        return fig
    if name == "frame_sides_bottom_left":
        fig.frame_sides = ["bottom", "left"]
    if name == "show_modebar_false":
        fig.show_modebar = False
    if name == "export_formats":
        fig.export_options = {"formats": ["png", "svg"]}
    if name == "show_tooltip_false":
        fig.show_tooltip = False
    if name == "tooltip_fields":
        fig.tooltip = {
            "fields": ["x", "y"],
            "title": "{x}",
            "format": {"x": ".2f"},
        }
    if name == "mark_style_hover":
        fig.set_mark_style(hover={"color": "#111111", "size": 10})
    if name == "interaction_select":
        fig.set_interaction(select=True)
    if name == "animation_duration":
        fig.animation_options = {"enabled": True, "duration": 250.0}
    if name == "graph_meta":
        fig._graph_meta = [{"layout": "force", "node_trace": 0, "edge_trace": 1}]  # noqa: SLF001
    if name == "palette_list":
        fig.palette = ["#ff0000", "#00ff00", "#0000ff"]
    if name == "palette_map":
        fig.palette = {"a": "#ff0000", "b": "#00ff00", "c": "#0000ff"}
    fig.scatter([0.0, 1.0, 2.0], [0.0, 1.0, 0.5])
    fig.traces[-1].id = 7
    return fig


def _build_case_payload(name: str) -> dict[str, Any]:
    fig = _build_case(name)
    if name.startswith("wasm_density_"):
        spec, _ = fig.build_payload_split()
    else:
        spec, _ = fig.build_payload()
    return _attach_entry(spec)


@pytest.fixture(scope="module")
def fixture() -> dict:
    return json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def node_attach_golden() -> dict:
    if not _node_bin():
        pytest.skip("node binary not on PATH")
    if not NODE_SCRIPT.is_file():
        pytest.skip(f"missing {NODE_SCRIPT}")
    if not LIB.is_file():
        pytest.skip(f"{LIB.name} missing; run `cargo build --release`")

    env = os.environ.copy()
    env.setdefault("XYG_NATIVE_LIB", str(LIB))
    proc = subprocess.run(
        [_node_bin(), str(NODE_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
    )
    if proc.returncode != 0:
        pytest.fail(
            "node payload attach cross-host golden failed:\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return json.loads(proc.stdout)


def test_fixture_contract(fixture: dict) -> None:
    assert fixture["schema"] == "xyg.payload-attach-cross-host/v1"
    assert fixture["protocol"] == PROTOCOL_VERSION
    assert int(fixture["abi_version"]) == int(_native.ABI_VERSION)
    assert len(fixture["cases"]) == len(CASE_NAMES)
    assert {case["name"] for case in fixture["cases"]} == set(CASE_NAMES)


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_python_matches_checked_in_fixture(case_name: str, fixture: dict) -> None:
    entry = next(case for case in fixture["cases"] if case["name"] == case_name)
    observed = _build_case_payload(case_name)
    expected = {key: entry.get(key) for key in observed}
    assert observed == expected


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_node_live_matches_python(case_name: str, node_attach_golden: dict) -> None:
    node_case = next(case for case in node_attach_golden["cases"] if case["name"] == case_name)
    observed = _build_case_payload(case_name)
    expected = {key: node_case.get(key) for key in observed}
    assert observed == expected


def test_write_fixtures_and_match_node(node_attach_golden: dict) -> None:
    if not FIXTURE_WRITER.is_file():
        pytest.skip("fixture writer missing")
    proc = subprocess.run(
        [sys.executable, str(FIXTURE_WRITER)],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    if proc.returncode != 0:
        pytest.fail(f"fixture writer failed:\n{proc.stderr}\n{proc.stdout}")
    fixture = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    for case in fixture["cases"]:
        node_case = next(
            entry for entry in node_attach_golden["cases"] if entry["name"] == case["name"]
        )
        for key in case:
            if key == "name":
                continue
            assert case[key] == node_case.get(key)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
