"""Rust-registry-driven Python/Node static-export identity (#857/#875)."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from typing import Any

import pytest

from xyg import _native
from xyg._figure import Figure
from xyg._scene_v3 import figure_scene, public_static_export, scene_export_support_reason

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "static_export_cross_host.mjs"
REGISTRY_FILE = ROOT / "tests" / "fixtures" / "static_export_support_registry.json"


def _native_lib() -> Path:
    if sys.platform == "win32":
        name = "xyg_core.dll"
    elif sys.platform == "darwin":
        name = "libxyg_core.dylib"
    else:
        name = "libxyg_core.so"
    return ROOT / "target" / "release" / name


@pytest.fixture(scope="module")
def registry() -> dict[str, Any]:
    payload = json.loads(REGISTRY_FILE.read_text())
    assert payload["schema"] == "xyg.static-export-support-registry/v1"
    return payload


@pytest.fixture(scope="module")
def node_static_exports() -> dict[str, Any]:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not found on PATH")
    native = _native_lib()
    if not native.is_file():
        pytest.skip(f"missing native core {native}")
    env = os.environ.copy()
    env.setdefault("XYG_NATIVE_LIB", str(native))
    proc = subprocess.run(
        [node, str(NODE_SCRIPT)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        pytest.fail(
            "Node static-export cross-host proof failed:\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "xyg.static-export-cross-host/v2"
    return payload


def _fixed_domains(figure: Figure) -> Figure:
    figure.axis_options["x"]["domain"] = (-2.0, 6.0)
    figure.axis_options["y"]["domain"] = (-2.0, 6.0)
    return figure


def _normalize_ids(figure: Figure) -> Figure:
    for trace_id, trace in enumerate(figure.traces):
        trace.id = trace_id
    return figure


def _base_figure(name: str) -> Figure:
    figure = Figure(width=320, height=240)
    if name == "scatter":
        figure.scatter(
            [0, 1, 2],
            [1, 3, 2],
            color="#3987e5",
            size=6,
            opacity=0.8,
            symbol="diamond",
        )
    elif name == "line":
        figure.line([0, 1, 2], [1, 3, 2], color="#ef4444", width=2)
    elif name == "step":
        figure.step([0, 1, 2], [1, 3, 2], where="post", color="#ef4444", width=2)
    elif name == "stairs":
        figure.stairs([1, 3, 2], [0, 1, 2, 3], where="post", color="#ef4444", width=2)
    elif name == "ecdf":
        figure.ecdf([3, 1, 2, 1, 3], color="#ef4444", width=2)
    elif name == "bar":
        figure.bar([0, 1], [1, 2], color="#22c55e", opacity=0.85)
    elif name == "column_bar":
        figure.column([0, 1], [1, 2], color="#22c55e", opacity=0.85)
    elif name == "histogram":
        figure.histogram([0, 1, 1, 2], bins=2, color="#7c3aed", opacity=0.85)
    elif name == "area":
        figure.area([0, 1, 2], [1, 3, 2], color="#0ea5e9", opacity=0.65)
    elif name == "errorbar":
        figure.errorbar([0, 1], [1, 2], yerr=[0.1, 0.2], color="#ef4444", cap_size=0)
    elif name == "box":
        figure.box([[1, 2, 3, 4], [2, 3, 4, 5]], color="#7c3aed", show_outliers=True)
    elif name == "violin":
        figure.violin([[1, 2, 2, 3, 4], [2, 2.5, 3.5]], bins=8, color="#7c3aed")
    elif name == "violin_horizontal":
        figure.violin(
            [[1, 2, 2, 3, 4], [2, 2.5, 3.5]],
            bins=8,
            color="#7c3aed",
            orientation="horizontal",
        )
    elif name == "hexbin":
        figure.hexbin(
            [0.5, 1.5, 2.5, 3.5, 1, 2, 3],
            [0.5, 0.5, 0.5, 0.5, 2, 2, 2],
            gridsize=(4, 4),
            color="#3987e5",
        )
    elif name == "segments":
        _fixed_domains(figure).segments([0, 1], [0, 1], [1, 2], [1, 2], color="#ef4444", width=2)
    elif name == "stem":
        _fixed_domains(figure).stem([0, 1], [1, 2], color="#22c55e")
    elif name == "error_band":
        _fixed_domains(figure).error_band(
            [0, 1, 2],
            [0.5, 1.5, 1],
            [1.5, 2.5, 2],
            color="#0ea5e9",
            opacity=0.6,
        )
    elif name == "ribbon":
        _fixed_domains(figure).ribbon([0], [2], [0], [1], [1], [2], color="#0ea5e9", opacity=0.6)
    elif name == "triangle_mesh":
        _fixed_domains(figure).triangle_mesh(
            [0, 2],
            [0, 0],
            [1, 3],
            [2, 2],
            [2, 4],
            [0, 0],
            color="#f59e0b",
            opacity=0.75,
        )
    elif name == "heatmap":
        _fixed_domains(figure).heatmap([[0, 1], [1, 0]], color="#3987e5")
    elif name == "contour":
        _fixed_domains(figure).contour(
            [[0, 1, 0], [1, 2, 1], [0, 1, 0]],
            levels=[0.5, 1.5],
            color="#ef4444",
            corner_mask=False,
        )
    else:  # pragma: no cover - registry drift reports the missing builder
        raise AssertionError(f"missing Python static-export builder for {name}")
    return _normalize_ids(figure)


def _edge_figure(name: str) -> Figure:
    figure = Figure(width=320, height=240)
    if name == "line_authored_style":
        _fixed_domains(figure).line([0, 1, 2], [1, 3, 2], color="#f97316", width=3, opacity=0.7)
    elif name == "scatter_single_log":
        figure.set_axis("x", type_="log")
        figure.scatter([2], [3], color="#3987e5", size=7)
    elif name == "step_nonfinite_authored":
        figure.set_axis("y", type_="log")
        figure.axis_options["x"]["domain"] = (0.5, 4.0)
        figure.axis_options["y"]["domain"] = (0.5, 4.0)
        figure.step([1, 2, 3], [1, float("nan"), 3], where="post", color="#ef4444")
    elif name == "bar_categorical_style":
        figure.bar(["a", "b", "a"], [1, 2, 3], color="#22c55e", opacity=0.7)
    elif name == "line_temporal_single":
        figure.set_axis("x", type_="time")
        figure.line([1000], [2], color="#ef4444")
    elif name == "scatter_empty_linear":
        figure.scatter([], [], color="#3987e5", size=6)
    elif name == "area_nonfinite_linear":
        _fixed_domains(figure)
        figure.area([0, 1, 2], [1, float("nan"), 2], color="#0ea5e9")
    elif name == "histogram_empty_categorical":
        figure._axis_categories["y"] = ["empty"]
        figure.histogram([], bins=2, color="#7c3aed")
    elif name == "step_temporal_log":
        figure.set_axis("x", type_="time")
        figure.set_axis("y", type_="log")
        figure.step([1000, 2000], [1, 10], where="mid", color="#ef4444")
    else:  # pragma: no cover - registry drift reports the missing builder
        raise AssertionError(f"missing Python static-export edge builder for {name}")
    return _normalize_ids(figure)


def _fail_close_figure(name: str) -> Figure:
    figure = Figure(width=320, height=240)
    figure.line([0, 1], [0, 1])
    if name == "fluid_viewport":
        figure.width = "100%"
    elif name == "browser_css":
        figure.class_name = "browser-only"
    elif name == "custom_font":
        figure.chrome_styles = {"title": {"font-family": "Example Sans"}}
    elif name == "title_options":
        figure.title_options = {"text": "title"}
    elif name == "extra_legend":
        figure.legend_options = {"ncols": 2}
    elif name == "alternate_axis":
        figure.traces[0].x_axis = "x2"
    elif name == "unsupported_symbol":
        figure.traces.clear()
        figure.scatter([0], [0])
        figure.traces[0].style["symbol"] = "not-a-symbol"
    elif name == "unsupported_mark":
        figure.traces[0].kind = "unknown"
    elif name == "violin_orientation_metadata":
        _fixed_domains(figure)
        figure.traces.clear()
        figure.violin([[1, 2, 2, 3]], bins=8)
        figure.traces[0].style["orientation"] = "diagonal"
    elif name == "layered_autorange":
        figure.bar([0], [1])
    elif name == "annotation_html":
        figure.annotations = [{"kind": "text", "x": 0.5, "y": 0.5, "text": "x", "html": "<b>x</b>"}]
    elif name == "annotation_collision":
        figure.annotations = [
            {"kind": "text", "x": 0.5, "y": 0.5, "text": "x", "collision": "avoid"}
        ]
    elif name == "annotation_markup":
        figure.annotations = [
            {"kind": "text", "x": 0.5, "y": 0.5, "text": "x", "markup": "markdown"}
        ]
    elif name == "invalid_annotation":
        figure.annotations = [{"kind": "bogus"}]
    elif name == "colorbar_option":
        figure.colorbar_options = {"bogus": True}
    elif name == "lod_limit":
        values = list(range(10_001))
        figure.traces.clear()
        figure.line(values, values)
    elif name == "band_shape":
        figure.traces.clear()
        figure.area([0], [1])
    elif name == "segment_shape":
        _fixed_domains(figure)
        figure.traces.clear()
        figure.segments([0, 1], [0, 1], [1, 2], [1, 2])
        figure.traces[0].x1 = figure.store.ingest([1])
    elif name == "triangle_mesh_limit":
        values = [0.0] * 1025
        _fixed_domains(figure)
        figure.traces.clear()
        figure.triangle_mesh(values, values, values, values, values, values)
    else:  # pragma: no cover - registry drift reports the missing builder
        raise AssertionError(f"missing Python fail-close builder for {name}")
    return figure


def _decode_png(encoded: bytes) -> tuple[int, int, int, bytearray]:
    """Decode the engine's 8-bit non-interlaced RGB/RGBA PNG using stdlib."""
    if encoded[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, width, height, channels, idat = 8, 0, 0, 0, b""
    while pos < len(encoded):
        (length,) = struct.unpack(">I", encoded[pos : pos + 4])
        kind = encoded[pos + 4 : pos + 8]
        body = encoded[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or interlace:
                raise ValueError("unsupported PNG variant")
            channels = {2: 3, 6: 4}[color]
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break
    raw = zlib.decompress(idat)
    stride = width * channels
    out = bytearray(width * height * channels)
    previous = bytearray(stride)
    source = 0
    for row in range(height):
        filter_kind = raw[source]
        source += 1
        line = bytearray(raw[source : source + stride])
        source += stride
        if filter_kind == 1:
            for index in range(channels, stride):
                line[index] = (line[index] + line[index - channels]) & 0xFF
        elif filter_kind == 2:
            for index in range(stride):
                line[index] = (line[index] + previous[index]) & 0xFF
        elif filter_kind == 3:
            for index in range(stride):
                left = line[index - channels] if index >= channels else 0
                line[index] = (line[index] + ((left + previous[index]) >> 1)) & 0xFF
        elif filter_kind == 4:
            for index in range(stride):
                left = line[index - channels] if index >= channels else 0
                above = previous[index]
                upper_left = previous[index - channels] if index >= channels else 0
                predictor = left + above - upper_left
                left_delta = abs(predictor - left)
                above_delta = abs(predictor - above)
                upper_left_delta = abs(predictor - upper_left)
                nearest = (
                    left
                    if left_delta <= above_delta and left_delta <= upper_left_delta
                    else above
                    if above_delta <= upper_left_delta
                    else upper_left
                )
                line[index] = (line[index] + nearest) & 0xFF
        elif filter_kind != 0:
            raise ValueError(f"unsupported PNG filter {filter_kind}")
        out[row * stride : (row + 1) * stride] = line
        previous = line
    return width, height, channels, out


def _png_contract(encoded: bytes) -> tuple[tuple[int, int], str, str]:
    width, height, channels, pixels = _decode_png(encoded)
    if channels == 4:
        rgba = pixels
    else:
        rgba = bytearray(width * height * 4)
        for source in range(0, len(pixels), 3):
            target = (source // 3) * 4
            rgba[target : target + 3] = pixels[source : source + 3]
            rgba[target + 3] = 255
    return (width, height), {3: "RGB", 4: "RGBA"}[channels], hashlib.sha256(rgba).hexdigest()


def test_checked_fixture_registry_matches_rust_authority() -> None:
    subprocess.run(
        [sys.executable, "scripts/static_export_support_registry.py"],
        cwd=ROOT,
        check=True,
    )


def test_registry_has_live_builder_for_every_declared_case(
    registry: dict[str, Any], node_static_exports: dict[str, Any]
) -> None:
    declared = {case["name"] for case in registry["shapes"]} | {
        case["name"] for case in registry["edge_cases"]
    }
    node_admitted = {case["name"] for case in node_static_exports["cases"]}
    node_rejected = {case["name"] for case in node_static_exports["edge_fail_close"]}
    assert node_admitted | node_rejected == declared

    node_cases = {case["name"]: case for case in node_static_exports["cases"]}
    for shape in registry["shapes"]:
        python_kinds = [trace.kind for trace in _base_figure(shape["name"]).traces]
        assert set(shape["trace_kinds"]).issubset(python_kinds), shape["name"]
        node_kinds = node_cases[shape["name"]]["trace_kinds"]
        if shape["name"] == "column_bar":
            assert python_kinds == ["column"] and node_kinds == ["bar"]
        else:
            assert node_kinds == python_kinds, shape["name"]


@pytest.mark.parametrize(
    "case_name",
    [case["name"] for case in json.loads(REGISTRY_FILE.read_text())["shapes"]]
    + [
        case["name"]
        for case in json.loads(REGISTRY_FILE.read_text())["edge_cases"]
        if not case["reason_prefix"]
    ],
)
def test_python_and_node_scene_svg_raster_and_decoded_png_are_identical(
    case_name: str, node_static_exports: dict[str, Any]
) -> None:
    node_case = {case["name"]: case for case in node_static_exports["cases"]}[case_name]
    figure = (
        _base_figure(case_name)
        if case_name in {case["name"] for case in json.loads(REGISTRY_FILE.read_text())["shapes"]}
        else _edge_figure(case_name)
    )

    assert scene_export_support_reason(figure) is None
    scene = figure_scene(figure)
    svg = public_static_export(figure, "svg")
    png = public_static_export(figure, "png")
    assert svg is not None
    assert png is not None and png.startswith(b"\x89PNG\r\n\x1a\n")

    node_scene = base64.b64decode(node_case["scene_b64"])
    node_svg = base64.b64decode(node_case["svg_b64"])
    node_raster = base64.b64decode(node_case["raster_b64"])
    node_png = base64.b64decode(node_case["png_b64"])
    node_document_svg = base64.b64decode(node_case["document_svg_b64"])
    node_document_png = base64.b64decode(node_case["document_png_b64"])
    assert node_scene == scene
    assert node_svg == svg
    assert node_document_svg == figure.to_svg().encode()
    assert node_raster == _native.scene_raster_commands(scene)
    assert node_png == png
    assert node_document_png == figure.to_png(scale=1)
    assert _png_contract(node_png) == _png_contract(png)
    assert _png_contract(png)[:2] == ((320, 240), "RGB")
    assert _png_contract(node_document_png)[:2] == ((320, 240), "RGBA")


def test_pairwise_edge_fail_close_reasons_match(
    registry: dict[str, Any], node_static_exports: dict[str, Any]
) -> None:
    node_cases = {case["name"]: case for case in node_static_exports["edge_fail_close"]}
    for case in registry["edge_cases"]:
        expected = case["reason_prefix"]
        if not expected:
            continue
        reason = scene_export_support_reason(_edge_figure(case["name"]))
        assert reason is not None and reason.startswith(expected), case["name"]
        assert reason == node_cases[case["name"]]["reason"]


def test_unsupported_feature_families_fail_closed_in_both_hosts(
    registry: dict[str, Any], node_static_exports: dict[str, Any]
) -> None:
    node_cases = {case["name"]: case for case in node_static_exports["fail_close"]}
    for case in registry["fail_close"]:
        reason = scene_export_support_reason(_fail_close_figure(case["name"]))
        assert reason is not None and reason.startswith(case["reason_prefix"]), case["name"]
        assert reason == node_cases[case["name"]]["reason"]
        assert public_static_export(_fail_close_figure(case["name"]), "svg") is None
