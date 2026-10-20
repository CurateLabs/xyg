"""Panel-owned document legends and the line-handle marker: Python and Node agree."""

from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np
import pytest

import xyg
from xyg import _native
from xyg import _static_document as sd
from xyg._scene_v3 import figure_scene

ROOT = Path(__file__).resolve().parents[1]
MARKER = {"symbol": "square", "color": "#cc00cc", "size": 6, "stroke_width": 1}
PANEL_LEGENDS = [
    (
        0,
        {
            "loc": "upper left",
            "items": [
                {
                    "kind": "line",
                    "name": "marked",
                    "style": {"color": "#cc00cc", "width": 2, "legend_marker": MARKER},
                },
                {"kind": "line", "name": "plain", "style": {"color": "#1f77b4", "width": 2}},
                {"kind": "scatter", "name": "points", "style": {"color": "#2ca02c", "size": 8}},
            ],
        },
    ),
    (
        1,
        {
            "loc": "lower right",
            "items": [
                {
                    "kind": "line",
                    "name": "second",
                    "style": {
                        "color": "#d62728",
                        "width": 2,
                        "legend_marker": {"symbol": "triangle", "size": 9},
                    },
                }
            ],
        },
    ),
]


def _scene() -> bytes:
    return figure_scene(
        xyg.chart(
            xyg.line([0, 1, 2], [1, 3, 2], color="#ef4444", width=2),
            xyg.x_axis(domain=(0, 2)),
            xyg.y_axis(domain=(0, 4)),
            xyg.legend(show=False),
            width=200,
            height=160,
        ).figure()
    )


def _document(panel_legends) -> bytes:
    scene = _scene()
    return sd.encode(
        [sd.Panel(scene, 0, 0, 200, 160), sd.Panel(scene, 200, 0, 200, 160)],
        width=400,
        height=160,
        panel_legends=panel_legends,
    )


@pytest.fixture(scope="module")
def node_result():
    if not shutil.which("node") or not (ROOT / "packages/xy-node/node_modules/koffi").exists():
        pytest.skip("Node/koffi unavailable")
    process = subprocess.run(
        [
            "node",
            str(ROOT / "packages/xy-node/scripts/static_document_panel_legend_cross_host.mjs"),
        ],
        text=True,
        capture_output=True,
        timeout=120,
        cwd=ROOT,
        env={**os.environ, "XYG_NATIVE_LIB": str(_native._lib._name)},
    )
    assert process.returncode == 0, process.stdout + process.stderr
    return json.loads(process.stdout)


def test_python_and_node_pack_identical_panel_legend_documents(node_result):
    document = _document(PANEL_LEGENDS)
    assert base64.b64decode(node_result["scenes"][0]) == _scene()
    assert document == base64.b64decode(node_result["document"])
    for fmt in ("svg", "png"):
        assert _native.static_document_export(document, fmt) == base64.b64decode(node_result[fmt])


def test_each_legend_is_laid_out_against_its_own_panel_plot_box():
    svg = _native.static_document_export(_document(PANEL_LEGENDS), "svg").decode()
    groups = re.findall(r'<g data-xy-static-legend="">(.*?)</g>', svg, re.S)
    assert len(groups) == 2
    first_x, second_x = (float(re.search(r'<rect x="([\d.]+)"', g).group(1)) for g in groups)
    assert first_x < 200 <= second_x, (first_x, second_x)
    # The marker overlay is a native glyph drawn over the line handle.
    assert "<rect" in groups[0].split("<line", 1)[1]
    assert groups[0].count("<line") == 2 and "<circle" in groups[0]
    assert "<path" in groups[1]  # triangle marker


def test_panel_legend_index_must_name_a_panel():
    with pytest.raises(Exception, match="XYG_STATIC_DOCUMENT_PANEL"):
        _native.static_document_export(_document([(5, PANEL_LEGENDS[1][1])]), "svg")


MATRIX_LOCS = ["upper left", "upper right", "lower left", "lower right", "center"]
MARKER_FACTS = {
    "empty": {},
    "size_only": {"size": 0.5},
    "stroke_only": {"stroke_width": 2, "color": "#00aa00"},
}


def _single(legend) -> bytes:
    return sd.encode(
        [sd.Panel(_scene(), 0, 0, 200, 160)],
        width=200,
        height=160,
        panel_legends=[(0, legend)],
    )


def _plot_box(svg: str) -> tuple[float, float, float, float]:
    match = re.search(
        r'data-xy-chrome="plot-background"[^>]*?x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"',
        svg,
    )
    return tuple(float(v) for v in match.groups())


@pytest.mark.parametrize("loc", MATRIX_LOCS)
def test_legend_location_matrix_agrees_across_hosts_and_stays_in_the_plot_box(loc, node_result):
    document = _single(
        {
            "loc": loc,
            "items": [
                {"kind": "line", "name": "series", "style": {"color": "#1f77b4", "width": 2}}
            ],
        }
    )
    node = node_result["matrix"][loc]
    assert document == base64.b64decode(node["document"])
    svg = _native.static_document_export(document, "svg")
    assert svg == base64.b64decode(node["svg"])
    text = svg.decode()
    frame = re.search(
        r'data-xy-static-legend="">.*?<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"',
        text,
        re.S,
    )
    x, y, w, h = (float(v) for v in frame.groups())
    px, py, pw, ph = _plot_box(text)
    assert px <= x and x + w <= px + pw and py <= y and y + h <= py + ph


@pytest.mark.parametrize("name", MARKER_FACTS)
def test_marker_presence_semantics_match_across_hosts(name, node_result):
    legend = {
        "items": [
            {
                "kind": "line",
                "name": name,
                "style": {"color": "#1f77b4", "width": 2, "legend_marker": MARKER_FACTS[name]},
            }
        ]
    }
    document = _single(legend)
    node = node_result["markers"][name]
    assert document == base64.b64decode(node["document"])
    svg = _native.static_document_export(document, "svg")
    assert svg == base64.b64decode(node["svg"])
    # An authored marker object, even an empty one, draws a marker over the line.
    assert b"<circle" in svg


def test_xydd_version_one_is_rejected():
    document = bytearray(_document(PANEL_LEGENDS))
    panels, title = struct.unpack_from("<2I", document, 20)
    at = 64 + panels * 128 + title
    assert document[at : at + 4] == b"XYDD"
    assert struct.unpack_from("<I", document, at + 4)[0] == 2
    struct.pack_into("<I", document, at + 4, 1)
    with pytest.raises(Exception, match="XYG_STATIC_DOCUMENT_PANEL"):
        _native.static_document_export(bytes(document), "svg")


def _png_pixels(png: bytes) -> np.ndarray:
    import xyg.pyplot as plt

    return np.asarray(plt.imread(io.BytesIO(png)))


def test_marker_pixels_are_drawn_over_the_handle_line():
    """Independent of PNG parity: the marker's own colour sits at the handle centre."""
    legend = {
        "items": [
            {
                "kind": "line",
                "name": "m",
                "style": {
                    "color": "#0000ff",
                    "width": 2,
                    "legend_marker": {"symbol": "square", "color": "#ff0000", "size": 9},
                },
            }
        ]
    }
    document = _single(legend)
    svg = _native.static_document_export(document, "svg").decode()
    x1, y1, x2, y2 = (
        float(v)
        for v in re.search(
            r'data-xy-static-legend="">.*?<line x1="([\d.]+)" y1="([\d.]+)" x2="([\d.]+)" y2="([\d.]+)"',
            svg,
            re.S,
        ).groups()
    )
    pixels = _png_pixels(_native.static_document_export(document, "png"))
    pixels = pixels[..., :3] if pixels.dtype != np.uint8 else pixels[..., :3] / 255.0
    cx, cy = round((x1 + x2) / 2), round(y1)
    assert np.allclose(pixels[cy, cx], (1.0, 0.0, 0.0), atol=0.05), pixels[cy, cx]
    # Away from the marker the handle is the blue line.
    near_start = pixels[cy, round(x1) + 1]
    assert near_start[2] > 0.8 and near_start[0] < 0.2, near_start
    red = np.all(np.abs(pixels - (1.0, 0.0, 0.0)) < 0.05, axis=-1)
    assert 40 <= red.sum() <= 120  # a 9px square, not a stray pixel


def test_item_opacity_applies_to_the_marker_paint():
    """Nested marker paint follows the item's opacity (plot(..., alpha=...) parity)."""
    legend = {
        "items": [
            {
                "kind": "line",
                "name": "a",
                "style": {
                    "color": "#1f77b4",
                    "width": 2,
                    "opacity": 0.5,
                    "legend_marker": {"symbol": "square", "color": "#ff0000", "size": 6},
                },
            }
        ]
    }
    svg = _native.static_document_export(_single(legend), "svg").decode()
    rect = re.findall(r'<rect[^>]*fill="rgb\(255,0,0\)" fill-opacity="([\d.]+)"', svg)
    line = re.findall(r'<line[^>]*stroke="rgba\(31,119,180,([\d.]+)\)"', svg)
    assert rect and line, (rect, line)
    assert float(rect[0]) == pytest.approx(float(line[0]), abs=5e-3)


def test_a_legend_that_leaves_the_canvas_is_rejected_not_clipped():
    def legend(anchor):
        return {
            "loc": "upper left",
            "anchor": anchor,
            "items": [{"kind": "line", "name": "a", "style": {}}],
        }

    _native.static_document_export(_single(legend((0.5, 0.5))), "svg")
    with pytest.raises(Exception, match="XYG_STATIC_UNSUPPORTED_FIGURE_LEGEND_BOUNDS"):
        _native.static_document_export(_single(legend((5.0, 5.0))), "svg")
