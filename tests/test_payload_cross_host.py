"""Byte-identical payload parity: Python host vs @curatelabs/xyg-node.

Shells ``node packages/xy-node/scripts/payload_cross_host_golden.mjs`` and compares
packed §29 payload blobs against Python ``Figure.build_payload`` for high-value
mark families (scatter direct, line transition keys, histogram, segments).

Also regenerates ``tests/fixtures/payload_cross_host.json`` when the fixture writer
is available.

Run::

    cargo build --release
    cd packages/xy-node && npm ci   # once
    XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so \\
      uv run pytest tests/test_payload_cross_host.py -q
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from xyg import _native
from xyg._figure import Figure
from xyg.config import PROTOCOL_VERSION

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "payload_cross_host_golden.mjs"
FIXTURE_WRITER = (
    ROOT / "packages" / "xy-node" / "test" / "fixtures" / "write_payload_cross_host_fixtures.py"
)
FIXTURE_JSON = ROOT / "tests" / "fixtures" / "payload_cross_host.json"


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


def _build_case(name: str) -> tuple[Figure, dict[str, object]]:
    if name == "scatter_direct":
        fig = Figure(width=240, height=160)
        fig.scatter([0.0, 1.0, 2.0], [0.0, 1.0, 0.5])
        fig.traces[0].id = 7
        return fig, {}
    if name == "scatter_categorical_color":
        fig = Figure(width=240, height=160)
        fig.scatter([0.0, 1.0, 2.0], [0.0, 1.0, 0.5], color=["a", "b", "a"])
        fig.traces[0].id = 15
        return fig, {}
    if name == "scatter_style_channels":
        from xyg import channels

        fig = Figure(width=240, height=160)
        fig.scatter([0.0, 1.0], [0.0, 1.0])
        fig.traces[0].style_channels = {"stroke_width": channels.StyleChannel([2.0, 3.0])}
        fig.traces[0].id = 34
        return fig, {}
    if name == "scatter_color_ch":
        from xyg import channels

        fig = Figure(width=240, height=160)
        fig.scatter([0.0, 1.0], [0.0, 1.0], color="#112233")
        fig.traces[0].color_ch = channels.ColorChannel(mode="constant", constant="#445566")
        fig.traces[0].id = 36
        return fig, {}
    if name == "line_transition_keys":
        fig = Figure(width=240, height=160)
        fig.line([0.0, 1.0, 2.0], [0.0, 1.0, 0.5])
        fig.traces[0].id = 8
        fig.traces[0].transition_keys = np.array([[1, 2], [3, 4], [5, 6]], dtype=np.uint32)
        return fig, {}
    if name == "line_log_ship_scale":
        fig = Figure(width=240, height=160)
        fig.set_axis("x", type_="log")
        fig.line([1.0, 10.0], [1.0, 10.0])
        fig.traces[0].id = 40
        return fig, {}
    if name == "scatter_log_ship_scale":
        fig = Figure(width=240, height=160)
        fig.set_axis("x", type_="log")
        fig.scatter([1.0, 10.0], [1.0, 10.0])
        fig.traces[0].id = 41
        return fig, {}
    if name == "histogram_log_ship_scale":
        fig = Figure(width=240, height=160)
        fig.set_axis("x", type_="log")
        fig.histogram([1.0, 2.0, 10.0], bins=2, range=(1.0, 10.0))
        fig.traces[0].id = 44
        return fig, {}
    if name == "histogram_fixed_bins":
        fig = Figure(width=240, height=160)
        fig.histogram([0.0, 1.0, 1.0, 2.0, 3.0], bins=3, range=(0.0, 3.0))
        fig.traces[0].id = 10
        return fig, {}
    if name == "histogram_finite_sel":
        fig = Figure(width=240, height=160)
        fig._append_rect_trace(
            "histogram",
            np.array([0.0, 1.0]),
            np.array([1.0, 2.0]),
            np.array([0.0, 0.0]),
            np.array([1.0, np.nan]),
            name=None,
            color="#3987e5",
            opacity=0.85,
            role="histogram",
            count=4,
        )
        fig.traces[0].id = 17
        return fig, {}
    if name == "histogram_style_channels":
        from xyg import channels

        fig = Figure(width=240, height=160)
        fig.histogram([0.0, 1.0, 1.0, 2.0], bins=2, range=(0.0, 2.0))
        n = len(fig.traces[0].x0.values)
        fig.traces[0].style_channels = {
            "stroke_width": channels.StyleChannel(np.full(n, 2.0, dtype=np.float64))
        }
        fig.traces[0].id = 21
        return fig, {}
    if name == "histogram_stroke_ch":
        from xyg import channels

        fig = Figure(width=240, height=160)
        fig.histogram([0.0, 1.0, 1.0, 2.0], bins=2, range=(0.0, 2.0))
        rgba = np.array([[1, 0, 0, 1], [0, 1, 0, 1]], dtype=np.float64)
        fig.traces[0].stroke_ch = channels.resolve_color(rgba, 2, default_constant="transparent")
        fig.traces[0].id = 31
        return fig, {}
    if name == "histogram_color_ch":
        from xyg import channels

        fig = Figure(width=240, height=160)
        fig.histogram([0.0, 1.0, 1.0, 2.0], bins=2, range=(0.0, 2.0))
        fig.traces[0].color_ch = channels.ColorChannel(mode="constant", constant="#112233")
        fig.traces[0].id = 35
        return fig, {}
    if name == "segments_pass_through":
        fig = Figure(width=240, height=160)
        fig.segments([0.0, 1.0], [0.0, 1.0], [1.0, 2.0], [1.0, 0.0])
        fig.traces[0].id = 12
        return fig, {}
    if name == "segments_color_ch":
        from xyg import channels

        fig = Figure(width=240, height=160)
        fig.segments([0.0], [0.0], [1.0], [1.0], color="#112233")
        fig.traces[0].color_ch = channels.ColorChannel(mode="constant", constant="#445566")
        fig.traces[0].id = 22
        return fig, {}
    if name == "segments_style_channels":
        from xyg import channels

        fig = Figure(width=240, height=160)
        fig.segments([0.0, 1.0], [0.0, 1.0], [1.0, 2.0], [1.0, 0.0])
        n = len(fig.traces[0].x0.values)
        fig.traces[0].style_channels = {
            "stroke_width": channels.StyleChannel(np.full(n, 2.0, dtype=np.float64))
        }
        fig.traces[0].id = 33
        return fig, {}
    if name == "rect_color_ch":
        from xyg import channels

        fig = Figure(width=240, height=160)
        fig.bar([0.0, 1.0], [1.0, 2.0], color="#112233")
        fig.traces[0].color_ch = channels.ColorChannel(mode="constant", constant="#445566")
        fig.traces[0].id = 23
        return fig, {}
    if name == "rect_style_channels":
        from xyg import channels

        fig = Figure(width=240, height=160)
        fig.bar([0.0, 1.0], [1.0, 2.0])
        n = len(fig.traces[0].x0.values)
        fig.traces[0].style_channels = {
            "stroke_width": channels.StyleChannel(np.full(n, 2.0, dtype=np.float64))
        }
        fig.traces[0].id = 32
        return fig, {}
    if name == "mesh_style_channels":
        from xyg import channels

        fig = Figure(width=240, height=160)
        fig.triangle_mesh([0.0], [0.0], [1.0], [0.0], [0.5], [1.0])
        fig.traces[0].style_channels = {
            "stroke_width": channels.StyleChannel(np.full(1, 2.0, dtype=np.float64))
        }
        fig.traces[0].id = 24
        return fig, {}
    if name == "ribbon_style_channels":
        from xyg import channels

        fig = Figure(width=240, height=160)
        fig.ribbon([0.0], [1.0], [0.0], [1.0], [0.0], [1.0], color="#112233")
        fig.traces[0].style_channels = {
            "stroke_width": channels.StyleChannel(np.full(1, 2.0, dtype=np.float64))
        }
        fig.traces[0].id = 25
        return fig, {}
    if name == "rect_stroke_ch":
        from xyg import channels

        fig = Figure(width=240, height=160)
        fig.bar([0.0, 1.0], [1.0, 2.0])
        rgba = np.array([[1, 0, 0, 1], [0, 1, 0, 1]], dtype=np.float64)
        fig.traces[0].stroke_ch = channels.resolve_color(rgba, 2, default_constant="transparent")
        fig.traces[0].id = 26
        return fig, {}
    if name == "mesh_stroke_ch":
        from xyg import channels

        fig = Figure(width=240, height=160)
        fig.triangle_mesh([0.0], [0.0], [1.0], [0.0], [0.5], [1.0])
        rgba = np.array([[1, 0, 0, 1]], dtype=np.float64)
        fig.traces[0].stroke_ch = channels.resolve_color(rgba, 1, default_constant="transparent")
        fig.traces[0].id = 27
        return fig, {}
    if name == "ribbon_stroke_ch":
        from xyg import channels

        fig = Figure(width=240, height=160)
        fig.ribbon([0.0], [1.0], [0.0], [1.0], [0.0], [1.0], color="#112233")
        fig.traces[0].stroke_ch = channels.ColorChannel(mode="constant", constant="#445566")
        fig.traces[0].id = 28
        return fig, {}
    if name == "segments_stroke_ch":
        from xyg import channels

        fig = Figure(width=240, height=160)
        fig.segments([0.0, 1.0], [0.0, 1.0], [1.0, 2.0], [1.0, 0.0])
        rgba = np.array([[1, 0, 0, 1], [0, 1, 0, 1]], dtype=np.float64)
        fig.traces[0].stroke_ch = channels.resolve_color(rgba, 2, default_constant="transparent")
        fig.traces[0].id = 29
        return fig, {}
    if name == "mesh_color_ch":
        from xyg import channels

        fig = Figure(width=240, height=160)
        fig.triangle_mesh([0.0], [0.0], [1.0], [0.0], [0.5], [1.0], color="#112233")
        fig.traces[0].color_ch = channels.ColorChannel(mode="constant", constant="#445566")
        fig.traces[0].id = 30
        return fig, {}
    if name == "hexbin_colormap":
        fig = Figure(width=240, height=160)
        fig.axis_options["x"]["domain"] = (0.0, 4.0)
        fig.axis_options["y"]["domain"] = (0.0, 5.0)
        fig.hexbin(
            [0.5, 1.5, 2.5, 3.5, 1.0, 2.0, 3.0],
            [0.5, 0.5, 0.5, 0.5, 2.0, 2.0, 2.0],
            gridsize=(4, 4),
            range=((0.0, 4.0), (0.0, 5.0)),
            name="hex",
        )
        fig.traces[0].id = 14
        return fig, {}
    if name == "bar_compact":
        fig = Figure(width=240, height=160)
        fig.bar([0.0, 1.0], [1.0, 2.0])
        fig.traces[0].id = 9
        return fig, {}
    if name == "heatmap_colormap":
        fig = Figure(width=240, height=160)
        fig.heatmap([[0, 1], [1, 0]], colormap="viridis")
        fig.traces[0].id = 11
        return fig, {}
    if name == "triangle_mesh_single":
        fig = Figure(width=240, height=160)
        fig.triangle_mesh([0.0], [0.0], [1.0], [0.0], [0.5], [1.0])
        fig.traces[0].id = 20
        return fig, {}
    raise KeyError(name)


@pytest.fixture(scope="module")
def fixture() -> dict:
    return json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def node_payload_golden() -> dict:
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
            f"node payload cross-host golden failed:\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return json.loads(proc.stdout)


def test_fixture_contract(fixture: dict) -> None:
    assert fixture["schema"] == "xyg.payload-cross-host/v1"
    assert fixture["protocol"] == PROTOCOL_VERSION
    assert int(fixture["abi_version"]) == int(_native.ABI_VERSION)
    assert len(fixture["cases"]) == 29
    assert {case["name"] for case in fixture["cases"]} == {
        "scatter_direct",
        "scatter_categorical_color",
        "scatter_style_channels",
        "scatter_color_ch",
        "line_transition_keys",
        "line_log_ship_scale",
        "scatter_log_ship_scale",
        "histogram_log_ship_scale",
        "histogram_fixed_bins",
        "histogram_finite_sel",
        "histogram_style_channels",
        "histogram_stroke_ch",
        "histogram_color_ch",
        "segments_pass_through",
        "segments_color_ch",
        "segments_style_channels",
        "rect_color_ch",
        "rect_style_channels",
        "mesh_style_channels",
        "ribbon_style_channels",
        "rect_stroke_ch",
        "mesh_stroke_ch",
        "ribbon_stroke_ch",
        "segments_stroke_ch",
        "mesh_color_ch",
        "hexbin_colormap",
        "bar_compact",
        "heatmap_colormap",
        "triangle_mesh_single",
    }


@pytest.mark.parametrize(
    "case_name",
    [
        "scatter_direct",
        "scatter_categorical_color",
        "scatter_style_channels",
        "scatter_color_ch",
        "line_transition_keys",
        "line_log_ship_scale",
        "scatter_log_ship_scale",
        "histogram_log_ship_scale",
        "histogram_fixed_bins",
        "histogram_finite_sel",
        "histogram_style_channels",
        "histogram_stroke_ch",
        "histogram_color_ch",
        "segments_pass_through",
        "segments_color_ch",
        "segments_style_channels",
        "rect_color_ch",
        "rect_style_channels",
        "mesh_style_channels",
        "ribbon_style_channels",
        "rect_stroke_ch",
        "mesh_stroke_ch",
        "ribbon_stroke_ch",
        "segments_stroke_ch",
        "mesh_color_ch",
        "hexbin_colormap",
        "bar_compact",
        "heatmap_colormap",
        "triangle_mesh_single",
    ],
)
def test_python_matches_checked_in_fixture(case_name: str, fixture: dict) -> None:
    entry = next(case for case in fixture["cases"] if case["name"] == case_name)
    figure, _ = _build_case(case_name)
    _spec, blob = figure.build_payload()
    assert len(blob) == entry["payload_blob_len"]
    assert hashlib.sha256(blob).hexdigest() == entry["payload_blob_sha256"]
    assert blob.hex() == entry["payload_blob_hex"]


@pytest.mark.parametrize(
    "case_name",
    [
        "scatter_direct",
        "scatter_categorical_color",
        "scatter_style_channels",
        "scatter_color_ch",
        "line_transition_keys",
        "line_log_ship_scale",
        "scatter_log_ship_scale",
        "histogram_log_ship_scale",
        "histogram_fixed_bins",
        "histogram_finite_sel",
        "histogram_style_channels",
        "histogram_stroke_ch",
        "histogram_color_ch",
        "segments_pass_through",
        "segments_color_ch",
        "segments_style_channels",
        "rect_color_ch",
        "rect_style_channels",
        "mesh_style_channels",
        "ribbon_style_channels",
        "rect_stroke_ch",
        "mesh_stroke_ch",
        "ribbon_stroke_ch",
        "segments_stroke_ch",
        "mesh_color_ch",
        "hexbin_colormap",
        "bar_compact",
        "heatmap_colormap",
        "triangle_mesh_single",
    ],
)
def test_node_live_matches_python(case_name: str, node_payload_golden: dict) -> None:
    node_case = next(case for case in node_payload_golden["cases"] if case["name"] == case_name)
    figure, _ = _build_case(case_name)
    _spec, blob = figure.build_payload()
    assert hashlib.sha256(blob).hexdigest() == node_case["payload_blob_sha256"]
    assert blob.hex() == node_case["payload_blob_hex"]
    if node_case.get("trace_keys") is not None:
        assert node_case["keys_lo_hex"] is not None
        assert node_case["keys_hi_hex"] is not None


def test_write_fixtures_and_match_node(node_payload_golden: dict) -> None:
    """Fixture writer output matches the live node golden for shared contracts."""
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
            entry for entry in node_payload_golden["cases"] if entry["name"] == case["name"]
        )
        assert case["payload_blob_sha256"] == node_case["payload_blob_sha256"]
        assert case["payload_blob_hex"] == node_case["payload_blob_hex"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
