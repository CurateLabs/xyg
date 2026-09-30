"""Series palette cursor cross-host parity: Python vs @curatelabs/xyg-node (#918).

Verifies that Node resolves default series colors from the figure's palette
cycle in the same order as Python, for scatter, line, histogram, bar
(multi-series), segments, errorbar, and graph marks (#918).

Run::

    cargo build --release
    cd packages/xy-node && npm ci   # once
    XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so \\
      uv run pytest tests/test_series_palette_cross_host.py -q

Regenerate the checked-in fixture after intentional behavior changes::

    uv run python tests/test_series_palette_cross_host.py --write
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from xyg import _native
from xyg._figure import Figure
from xyg.config import PROTOCOL_VERSION

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "series_palette_cross_host.mjs"
FIXTURE = ROOT / "tests" / "fixtures" / "series_palette_cross_host.json"


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


def _resolve_spec_color(t: dict[str, Any]) -> str | None:
    """Extract the constant color string from a payload trace dict.

    Ribbon color is always None: Python ships ribbon paint as a constant or
    direct-RGBA channel (both implementation-specific); cross-host cursor
    behavior is verified through the subsequent trace instead (#918).
    """
    if t.get("kind") == "ribbon":
        return None
    c = t.get("color")
    if c and isinstance(c, dict) and c.get("mode") == "constant":
        return c.get("color")
    style = t.get("style") or {}
    v = style.get("color")
    return v if isinstance(v, str) else None


def _build_case(name: str) -> list[dict[str, Any]]:
    """Build a Figure for the named case and return trace_colors list."""
    if name == "builtin_cursor_scatter_line_hist":
        fig = Figure(width=240, height=160)
        fig.scatter([0, 1], [0, 1])
        fig.line([0, 1], [0, 1])
        fig.histogram([1, 2, 3, 4])
    elif name == "builtin_cursor_bar_2series":
        fig = Figure(width=240, height=160)
        fig.bar([0, 1, 2], [[1, 2, 3], [4, 5, 6]])
    elif name == "builtin_cursor_segments_errorbar":
        fig = Figure(width=240, height=160)
        fig.segments([0, 1], [0, 1], [1, 2], [1, 2])
        fig.errorbar([0, 1], [0.5, 1.5], yerr=0.1)
    elif name == "custom_palette_cursor":
        fig = Figure(width=240, height=160)
        fig.palette = ["#aa0000", "#00aa00", "#0000aa"]
        fig.scatter([0, 1], [0, 1])
        fig.line([0, 1], [0, 1])
        fig.histogram([1, 2, 3, 4])
    elif name == "custom_palette_wrap":
        fig = Figure(width=240, height=160)
        fig.palette = ["#ff0000", "#00ff00"]
        fig.scatter([0, 1], [0, 1])
        fig.line([0, 1], [0, 1])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            fig.histogram([1, 2, 3])
    elif name == "explicit_color_no_cursor":
        # Explicit color= bypasses the cursor; the line takes slot 0.
        fig = Figure(width=240, height=160)
        fig.palette = ["#aa0000", "#00aa00"]
        fig.scatter([0, 1], [0, 1], color="#abcdef")
        fig.line([0, 1], [0, 1])
    elif name == "graph_node_cursor_edge_neutral":
        # Graph edges paint the Rust neutral and take no slot (#898); the node
        # scatter takes slot 1 (the pre-graph scatter took slot 0).
        fig = Figure(width=240, height=160)
        fig.scatter([0, 1], [0, 1])
        fig.graph(["a", "b", "c"], [("a", "b"), ("b", "c")])
    elif name == "graph_custom_palette_node":
        # Custom palette; the graph node takes slot 0 from it.
        fig = Figure(width=240, height=160)
        fig.palette = ["#aa0000", "#00aa00"]
        fig.graph(["a", "b", "c"], [("a", "b"), ("b", "c")])
    elif name == "heatmap_string_color":
        # Explicit string color= skips cursor; following line takes slot 0.
        fig = Figure(width=240, height=160)
        fig.palette = ["#aa0000", "#00aa00"]
        fig.heatmap([[1, 2], [3, 4]], color="#ff00ff")
        fig.line([0, 1], [0, 1])
    elif name == "heatmap_no_color":
        # No explicit color → cursor advances; scatter gets slot 1.
        fig = Figure(width=240, height=160)
        fig.heatmap([[1, 2], [3, 4]])
        fig.scatter([0, 1], [0, 1])
    elif name == "heatmap_nonstring_color":
        # Non-string color (array) → cursor advances, matching string-less path.
        # Python: isinstance(array, str) is False → next_series_color() is called.
        fig = Figure(width=240, height=160)
        fig.palette = ["#aa0000", "#00aa00"]
        fig.scatter([0, 1], [0, 1])
        fig.heatmap([[1, 2], [3, 4]], color=np.array([1.0, 0.0, 0.0]))
    elif name == "hexbin_cursor":
        # Hexbin takes one cursor slot (colormap background color).
        fig = Figure(width=240, height=160)
        fig.hexbin(list(range(10)), list(range(10)))
        fig.scatter([0, 1], [0, 1])
    elif name == "ribbon_no_color":
        # Ribbon without explicit color consumes cursor slot 0; scatter gets slot 1.
        # Ribbon's own color is always returned as None by _resolve_spec_color
        # (shipped as direct RGBA, not a CSS constant).
        fig = Figure(width=240, height=160)
        fig.palette = ["#aa0000", "#00aa00"]
        fig.ribbon([0, 1], [1, 2], [0, 1], [0.5, 1.5], [0, 1], [0.5, 1.5])
        fig.scatter([0, 1], [0, 1])
    elif name == "ribbon_style_color":
        # Python ribbon does not accept color via style= (only via color=).
        # Explicit color= is equivalent: cursor NOT advanced; scatter takes slot 0.
        # In Node, the same behavior is triggered via style: {color: ...} (finding 4).
        fig = Figure(width=240, height=160)
        fig.palette = ["#aa0000", "#00aa00"]
        fig.ribbon(
            [0, 1],
            [1, 2],
            [0, 1],
            [0.5, 1.5],
            [0, 1],
            [0.5, 1.5],
            color="#ff1234",
        )
        fig.scatter([0, 1], [0, 1])
    elif name == "area_cursor":
        fig = Figure(width=240, height=160)
        fig.area([0, 1, 2], [0, 1, 0])
        fig.scatter([0, 1], [0, 1])
    elif name == "step_cursor":
        # step() delegates to line(); the emitted trace kind is "line".
        fig = Figure(width=240, height=160)
        fig.step([0, 1, 2], [0, 1, 0])
        fig.scatter([0, 1], [0, 1])
    elif name == "box_cursor":
        # box() takes one slot; all sub-traces (whisker, box, median) share it.
        fig = Figure(width=240, height=160)
        fig.box(np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
        fig.scatter([0, 1], [0, 1])
    elif name == "violin_cursor":
        fig = Figure(width=240, height=160)
        fig.violin(np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
        fig.scatter([0, 1], [0, 1])
    elif name == "stem_cursor":
        # stem() takes one slot; the segment trace and scatter marker share it.
        fig = Figure(width=240, height=160)
        fig.stem([0, 1, 2], [1.0, 2.0, 3.0])
        fig.scatter([0, 1], [0, 1])
    elif name == "triangle_mesh_cursor":
        fig = Figure(width=240, height=160)
        fig.triangle_mesh([0.0], [0.0], [1.0], [0.0], [0.5], [1.0])
        fig.scatter([0, 1], [0, 1])
    elif name == "scatter_style_color_explicit":
        # Python scatter does not accept color via style= (only via color=).
        # Explicit color= is equivalent: cursor NOT advanced; line takes slot 0.
        # In Node, the same behavior is triggered via style: {color: ...} (finding 2).
        fig = Figure(width=240, height=160)
        fig.palette = ["#aa0000", "#00aa00"]
        fig.scatter([0, 1], [0, 1], color="#aabbcc")
        fig.line([0, 1], [0, 1])
    elif name == "bar_style_color_explicit":
        # Python bar does not accept color via style= (only via color=).
        # Explicit color= is equivalent: cursor NOT advanced; scatter takes slot 0.
        # In Node, the same behavior is triggered via style: {color: ...} (finding 2).
        fig = Figure(width=240, height=160)
        fig.palette = ["#aa0000", "#00aa00"]
        fig.bar([0, 1, 2], [1.0, 2.0, 3.0], color="#ff0000")
        fig.scatter([0, 1], [0, 1])
    elif name == "bar_flat_multi_series":
        # Python uses a 2-D numpy array (shape 2×3); Node uses an equivalent
        # flat Float64Array that composeBar detects as 2 series (#918 finding 1).
        fig = Figure(width=240, height=160)
        fig.bar([0, 1, 2], np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]))
    else:
        raise KeyError(name)

    spec, _ = fig.build_payload()
    return [{"kind": t["kind"], "color": _resolve_spec_color(t)} for t in spec["traces"]]


CASE_NAMES = (
    "builtin_cursor_scatter_line_hist",
    "builtin_cursor_bar_2series",
    "builtin_cursor_segments_errorbar",
    "custom_palette_cursor",
    "custom_palette_wrap",
    "explicit_color_no_cursor",
    "graph_node_cursor_edge_neutral",
    "graph_custom_palette_node",
    # New cases for findings 1–4 and coverage of all changed marks (#918)
    "heatmap_string_color",
    "heatmap_no_color",
    "heatmap_nonstring_color",
    "hexbin_cursor",
    "ribbon_no_color",
    "ribbon_style_color",
    "area_cursor",
    "step_cursor",
    "box_cursor",
    "violin_cursor",
    "stem_cursor",
    "triangle_mesh_cursor",
    "scatter_style_color_explicit",
    "bar_style_color_explicit",
    "bar_flat_multi_series",
)


def _expected() -> dict[str, Any]:
    cases = []
    for name in CASE_NAMES:
        palette: list[str] | None = None
        if name in ("custom_palette_cursor",):
            palette = ["#aa0000", "#00aa00", "#0000aa"]
        elif name in ("custom_palette_wrap",):
            palette = ["#ff0000", "#00ff00"]
        elif name in (
            "explicit_color_no_cursor",
            "graph_custom_palette_node",
            "heatmap_string_color",
            "heatmap_nonstring_color",
            "ribbon_no_color",
            "ribbon_style_color",
            "scatter_style_color_explicit",
            "bar_style_color_explicit",
        ):
            palette = ["#aa0000", "#00aa00"]

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            trace_colors = _build_case(name)

        cases.append({"name": name, "palette": palette, "trace_colors": trace_colors})

    return {
        "schema": "xyg.series-palette-cross-host/v1",
        "authority": (
            "packages/xy-node/src/figure.js nextSeriesColor + "
            "Python Figure.next_series_color (#918)"
        ),
        "protocol": PROTOCOL_VERSION,
        "abi_version": _native.ABI_VERSION,
        "cases": cases,
    }


@pytest.fixture(scope="module")
def fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def node_golden() -> dict[str, Any]:
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
            "series-palette-cross-host Node golden failed:\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return json.loads(proc.stdout)


def test_fixture_contract(fixture: dict[str, Any]) -> None:
    assert fixture["schema"] == "xyg.series-palette-cross-host/v1"
    assert fixture["protocol"] == PROTOCOL_VERSION
    assert int(fixture["abi_version"]) == int(_native.ABI_VERSION)
    assert {c["name"] for c in fixture["cases"]} == set(CASE_NAMES)


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_python_matches_checked_in_fixture(case_name: str, fixture: dict[str, Any]) -> None:
    entry = next(c for c in fixture["cases"] if c["name"] == case_name)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        trace_colors = _build_case(case_name)
    assert trace_colors == entry["trace_colors"], (
        f"Python trace colors for {case_name!r} differ from fixture"
    )


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_node_live_matches_python(case_name: str, node_golden: dict[str, Any]) -> None:
    """Node series-palette cursor output matches Python's fixture for every case."""
    node_case = next(c for c in node_golden["cases"] if c["name"] == case_name)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        py_colors = _build_case(case_name)
    node_colors = node_case["trace_colors"]
    assert len(py_colors) == len(node_colors), (
        f"trace count mismatch for {case_name!r}: "
        f"Python {len(py_colors)} vs Node {len(node_colors)}"
    )
    for i, (py_t, node_t) in enumerate(zip(py_colors, node_colors, strict=True)):
        assert py_t["kind"] == node_t["kind"], (
            f"{case_name!r} trace[{i}] kind: Python={py_t['kind']!r}, Node={node_t['kind']!r}"
        )
        assert py_t["color"] == node_t["color"], (
            f"{case_name!r} trace[{i}] ({py_t['kind']!r}) color: "
            f"Python={py_t['color']!r}, Node={node_t['color']!r}"
        )


if __name__ == "__main__":
    if sys.argv[1:] != ["--write"]:
        raise SystemExit("usage: test_series_palette_cross_host.py --write")
    data = _expected()
    FIXTURE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {FIXTURE}")
