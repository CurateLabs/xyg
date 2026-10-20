"""Python/Node identity for the native secondary right-hand y axis (#1006).

`packages/xy-node/scripts/static_dual_axis_cross_host.mjs` builds the same
public dual-axis charts through Node; the XYST document (which embeds the Scene
and its `XYY2` block), SVG, PNG and PDF bytes must match, as must Rust's stable
rejection reasons.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import xyg.components as c
from xyg._scene_v3 import scene_export_support_reason
from xyg._static_document import export_figure, figure_document

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "static_dual_axis_cross_host.mjs"
WIDTH = 480
HEIGHT = 320


@pytest.fixture(scope="module")
def node_exports() -> dict[str, Any]:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not found on PATH")
    name = "xyg_core.dll" if sys.platform == "win32" else "libxyg_core.so"
    native = (
        ROOT / "target" / "release" / (name if sys.platform != "darwin" else "libxyg_core.dylib")
    )
    if not native.is_file():
        pytest.skip(f"missing native core {native}")
    env = {**os.environ, "XYG_NATIVE_LIB": os.environ.get("XYG_NATIVE_LIB", str(native))}
    proc = subprocess.run(
        [node, str(NODE_SCRIPT)], cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        pytest.fail(f"Node proof failed:\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
    return json.loads(proc.stdout)


def _dual(*, y=None, y2=None, y2_values=(100, 200, 300), y2_side="right", raw_y2=None):
    """The public dual-axis chart; `raw_y2` sets axis options the component validators
    would refuse (or do not expose), so the host-to-Rust path sees them untouched."""
    figure = c.line_chart(
        c.line(x=[1, 2, 3], y=[1, 2, 3]),
        c.line(x=[1, 2, 3], y=list(y2_values), y_axis="y2"),
        c.x_axis(domain=(0, 4)),
        c.y_axis(domain=(0, 4), label="L", **(y or {})),
        c.y_axis(id="y2", side=y2_side, **{"label": "R", "domain": (0, 400), **(y2 or {})}),
        width=WIDTH,
        height=HEIGHT,
    ).figure()
    figure.axis_options["y2"].update(raw_y2 or {})
    return figure


CASES: dict[str, dict[str, Any]] = {
    "dual": {},
    "styled": {
        "y": {"style": {"label_color": "#1f77b4"}},
        "y2": {
            "style": {"label_color": "#d62728", "tick_label_size": 20, "tick_padding": 12},
            "tick_values": [0, 200, 400],
            "tick_labels": ["zero", "two hundred", "four hundred"],
        },
    },
    "log": {"y2": {"type_": "log", "domain": (10, 1000)}, "y2_values": (10, 100, 1000)},
    "symlog": {
        "y2": {"type_": "symlog", "constant": 2, "domain": (-100, 100)},
        "y2_values": (-50, 0, 50),
    },
    "gap": {"y2": {"tick_label_min_gap": 200}},
    "preserve": {"y2": {"tick_label_min_gap": 200, "tick_label_strategy": "preserve"}},
    "collision_key": {"y2": {"tick_label_min_gap": 200}, "raw_y2": {"collision": "preserve"}},
    "strategy_wins": {
        "y2": {"tick_label_min_gap": 200, "tick_label_strategy": "preserve"},
        "raw_y2": {"collision": "hide"},
    },
}

INVALID: dict[str, dict[str, Any]] = {
    "constant_zero": {"type": "symlog", "constant": 0},
    "constant_negative": {"type": "symlog", "constant": -2},
    "domain_infinite": {"domain": (0, float("inf"))},
    "angle_infinite": {"tick_label_angle": float("inf")},
    "angle_negative_infinite": {"tick_label_angle": float("-inf")},
}


def _case(name: str):
    figure = _dual(**CASES[name])
    for index, trace in enumerate(figure.traces):
        trace.id = index
    return figure


def _reason_or_message(figure: Any) -> str | None:
    """Rust's reason, whether the host returns it or raises it."""
    try:
        return scene_export_support_reason(figure)
    except ValueError as error:
        return str(error)


@pytest.mark.parametrize("name", list(CASES))
def test_python_and_node_export_identical_bytes(name: str, node_exports: dict[str, Any]) -> None:
    node = node_exports["cases"][name]
    figure = _case(name)
    document = figure_document(figure, width=WIDTH, height=HEIGHT)
    assert base64.b64decode(node["xyst_b64"]) == document
    for fmt in ("svg", "png", "pdf"):
        assert base64.b64decode(node[f"{fmt}_b64"]) == export_figure(
            figure, fmt, width=WIDTH, height=HEIGHT
        ), fmt


def test_python_and_node_report_the_same_rust_reasons(node_exports: dict[str, Any]) -> None:
    x2 = c.line_chart(
        c.line(x=[1, 2, 3], y=[1, 2, 3]), c.x_axis(domain=(0, 4)), c.y_axis(domain=(0, 4))
    ).figure()
    x2.axis_options["x2"] = {"side": "top"}
    colorbar = _dual()
    colorbar.colorbar_options = {"title": "c"}
    polar = _dual()
    polar.coords = "polar"
    python = {
        "left_y2": scene_export_support_reason(_dual(y2_side="left")),
        "x2": scene_export_support_reason(x2),
        "y2_colorbar": scene_export_support_reason(colorbar),
        "y2_polar": scene_export_support_reason(polar),
        "y2_category": scene_export_support_reason(_dual(raw_y2={"type": "category"})),
    }
    assert python == node_exports["reasons"]
    assert all(reason and reason.startswith("XYG_SCENE_UNSUPPORTED_") for reason in python.values())


def test_invalid_authored_y2_values_get_the_same_rust_rejection(
    node_exports: dict[str, Any],
) -> None:
    python = {name: _reason_or_message(_dual(raw_y2=raw)) for name, raw in INVALID.items()}
    assert python == node_exports["invalid"]
    # Rust rejects each one; no host substitutes a default and exports anyway.
    assert all(python.values()), python
