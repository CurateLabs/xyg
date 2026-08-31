"""Cross-host buildPayload chrome parity: Python vs @curatelabs/xyg-node.

Compares top-level ``show_legend``, ``legend`` (from ``legend_options``),
``title_options``, ``colorbar`` (from ``colorbar_options``), ``extra_legends``,
``annotations``, ``padding``, and ``dom`` (``class_name``, ``class_names``,
``style``, and ``chrome_styles`` → ``dom.styles``).

Run::

    cargo build --release
    cd packages/xy-node && npm ci   # once
    XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so \\
      uv run pytest tests/test_payload_chrome_cross_host.py -q
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from xyg import _native
from xyg._figure import Figure
from xyg.config import PROTOCOL_VERSION

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "payload_chrome_cross_host.mjs"
FIXTURE_WRITER = (
    ROOT
    / "packages"
    / "xy-node"
    / "test"
    / "fixtures"
    / "write_payload_chrome_cross_host_fixtures.py"
)
FIXTURE_JSON = ROOT / "tests" / "fixtures" / "payload_chrome_cross_host.json"

CASE_NAMES = (
    "show_legend_default",
    "show_legend_false",
    "legend_loc_upper_right",
    "legend_loc_best",
    "title_options_center",
    "title_options_defaults",
    "colorbar_right",
    "colorbar_bottom_minor",
    "extra_legends_lower_left",
    "annotation_text",
    "annotation_rule",
    "dom_class_name",
    "dom_style",
    "dom_class_names",
    "dom_chrome_styles",
    "padding_explicit",
    "chrome_combined",
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


def _build_case(name: str) -> Figure:
    fig = Figure(width=240, height=160)
    if name in ("show_legend_false", "chrome_combined"):
        fig.show_legend = False
    if name == "legend_loc_upper_right":
        fig.legend_options = {"loc": "upper right", "title": "Series"}
    if name == "legend_loc_best":
        fig.legend_options = {"loc": "best"}
    if name == "title_options_center":
        fig.title_options = [{"text": "T", "loc": "center", "y": 1.0, "pad": 8.0}]
    if name == "title_options_defaults":
        fig.title_options = [{"text": "T"}]
    if name == "colorbar_right":
        fig.colorbar_options = {
            "domain": [0.0, 1.0],
            "stops": [[0.0, [0, 0, 0, 255]], [1.0, [255, 255, 255, 255]]],
            "title": "Scale",
        }
    if name == "colorbar_bottom_minor":
        fig.colorbar_options = {
            "domain": [0.0, 1.0],
            "stops": [[0.0, [0, 0, 0, 255]], [1.0, [255, 255, 255, 255]]],
            "side": "bottom",
            "minor_ticks": True,
        }
    if name == "extra_legends_lower_left":
        fig.extra_legends = [{"loc": "lower left", "title": "Extra"}]
    if name == "annotation_text":
        fig.annotations = [{"kind": "text", "text": "hi", "x": 0, "y": 1}]
    if name == "annotation_rule":
        fig.annotations = [
            {
                "kind": "rule",
                "axis": "x",
                "value": 1.0,
                "text": "line",
                "style": {"color": "#ff0000", "width": 2.0},
            }
        ]
    if name in ("dom_class_name", "chrome_combined"):
        fig.class_name = "root-node"
    if name == "dom_style":
        fig.style = {"width": "100%"}
    if name == "dom_class_names":
        fig.class_names = {"title": "t"}
    if name == "dom_chrome_styles":
        fig.chrome_styles = {"title": {"font-size": "18px", "color": "#333333"}}
    if name == "padding_explicit":
        fig.padding = [8.0, 8.0, 8.0, 8.0]
    if name == "chrome_combined":
        fig.style = {"height": "320px"}
        fig.class_names = {"canvas": "p"}
        fig.chrome_styles = {"title": {"font-weight": "bold"}}
    fig.scatter([0.0, 1.0, 2.0], [0.0, 1.0, 0.5])
    fig.traces[0].id = 7
    return fig


def _chrome_entry(spec: dict) -> dict:
    return {
        "show_legend": spec["show_legend"],
        "legend": spec.get("legend"),
        "title_options": spec.get("title_options"),
        "colorbar": spec.get("colorbar"),
        "extra_legends": spec.get("extra_legends"),
        "annotations": spec.get("annotations"),
        "padding": spec.get("padding"),
        "dom": spec.get("dom"),
    }


@pytest.fixture(scope="module")
def fixture() -> dict:
    return json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def node_chrome_golden() -> dict:
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
            f"node payload chrome cross-host golden failed:\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return json.loads(proc.stdout)


def test_fixture_contract(fixture: dict) -> None:
    assert fixture["schema"] == "xyg.payload-chrome-cross-host/v1"
    assert fixture["protocol"] == PROTOCOL_VERSION
    assert int(fixture["abi_version"]) == int(_native.ABI_VERSION)
    assert len(fixture["cases"]) == len(CASE_NAMES)
    assert {case["name"] for case in fixture["cases"]} == set(CASE_NAMES)


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_python_matches_checked_in_fixture(case_name: str, fixture: dict) -> None:
    entry = next(case for case in fixture["cases"] if case["name"] == case_name)
    spec, _ = _build_case(case_name).build_payload()
    assert _chrome_entry(spec) == {
        "show_legend": entry["show_legend"],
        "legend": entry.get("legend"),
        "title_options": entry.get("title_options"),
        "colorbar": entry.get("colorbar"),
        "extra_legends": entry.get("extra_legends"),
        "annotations": entry.get("annotations"),
        "padding": entry.get("padding"),
        "dom": entry["dom"],
    }


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_node_live_matches_python(case_name: str, node_chrome_golden: dict) -> None:
    node_case = next(case for case in node_chrome_golden["cases"] if case["name"] == case_name)
    spec, _ = _build_case(case_name).build_payload()
    assert _chrome_entry(spec) == {
        "show_legend": node_case["show_legend"],
        "legend": node_case.get("legend"),
        "title_options": node_case.get("title_options"),
        "colorbar": node_case.get("colorbar"),
        "extra_legends": node_case.get("extra_legends"),
        "annotations": node_case.get("annotations"),
        "padding": node_case.get("padding"),
        "dom": node_case["dom"],
    }


def test_write_fixtures_and_match_node(node_chrome_golden: dict) -> None:
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
            entry for entry in node_chrome_golden["cases"] if entry["name"] == case["name"]
        )
        assert case["show_legend"] == node_case["show_legend"]
        assert case.get("legend") == node_case.get("legend")
        assert case.get("title_options") == node_case.get("title_options")
        assert case.get("colorbar") == node_case.get("colorbar")
        assert case.get("extra_legends") == node_case.get("extra_legends")
        assert case.get("annotations") == node_case.get("annotations")
        assert case.get("padding") == node_case.get("padding")
        assert case["dom"] == node_case["dom"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
