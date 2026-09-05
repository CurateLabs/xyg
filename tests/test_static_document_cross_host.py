from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from xyg import _native, _static_document
from xyg._figure import Figure
from xyg._scene_v3 import figure_scene

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "static_document_cross_host.mjs"


def _native_lib() -> Path:
    return ROOT / "target" / "release" / "libxyg_core.so"


def _scenes() -> list[bytes]:
    figures = [
        Figure(width=160, height=120).line([0, 1, 2], [1, 3, 2]),
        Figure(width=160, height=120).scatter([0, 1, 2], [2, 1, 3]),
    ]
    return [figure_scene(figure) for figure in figures]


def test_python_and_node_share_static_document_bytes_and_consumers() -> None:
    if shutil.which("node") is None or not (ROOT / "packages/xy-node/node_modules/koffi").exists():
        pytest.skip("Node host dependencies are not installed")
    scenes = _scenes()
    document = _static_document.encode(
        [
            _static_document.Panel(
                scene,
                index * 160 - 5,
                0,
                160,
                120,
                (12, 13, 4, 12, 13, 4),
            )
            for index, scene in enumerate(scenes)
        ],
        width=320,
        height=120,
        title="A & B",
        title_color="#123456",
        title_size=13,
        title_x=160,
        title_y=14,
    )
    request = {
        "scenes": [base64.b64encode(scene).decode() for scene in scenes],
        "panelWidth": 160,
        "panelHeight": 120,
        "title": "A & B",
        "titleColor": "#123456",
        "titleSize": 13,
        "titleX": 160,
        "titleY": 14,
    }
    process = subprocess.run(
        ["node", str(SCRIPT)],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=True,
        cwd=ROOT,
        env={**os.environ, "XYG_NATIVE_LIB": str(_native_lib())},
    )
    node = json.loads(process.stdout)
    assert base64.b64decode(node["document"]) == document
    for format in ("svg", "png", "pdf", "jpeg", "webp"):
        expected = _native.static_document_export(document, format, scale=1, quality=90)
        assert base64.b64decode(node["outputs"][format]) == expected


def test_python_and_node_share_static_document_decoration_bytes() -> None:
    if shutil.which("node") is None or not (ROOT / "packages/xy-node/node_modules/koffi").exists():
        pytest.skip("Node host dependencies are not installed")
    scene = _scenes()[0]
    labels = [
        {
            "text": "shared label",
            "x": 0.5,
            "y": 0.1,
            "size": 12,
            "color": "#654321",
            "anchor": "middle",
            "vertical_align": "center",
            "font_style": "italic",
            "weight": "bold",
        }
    ]
    legend = {
        "title": "Kinds",
        "loc": "upper right",
        "ncols": 2,
        "items": [
            {"name": "line", "kind": "line", "style": {"color": "#123456", "dash": True}},
            {
                "name": "point",
                "kind": "scatter",
                "style": {"color": "#654321", "symbol": "circle", "size": 7},
            },
        ],
    }
    document = _static_document.encode(
        [
            _static_document.Panel(
                scene,
                -5,
                0,
                160,
                120,
                (12, 13, 4, 12, 13, 4),
                annotation_font_size=15,
            )
        ],
        width=160,
        height=120,
        title="A & B",
        title_color="#123456",
        title_size=13,
        title_x=80,
        title_y=14,
        title_flags=3,
        labels=labels,
        legend=legend,
    )
    request = {
        "scenes": [base64.b64encode(scene).decode()],
        "panelWidth": 160,
        "panelHeight": 120,
        "title": "A & B",
        "titleColor": "#123456",
        "titleSize": 13,
        "titleX": 80,
        "titleY": 14,
        "titleFlags": 3,
        "annotationFontSize": 15,
        "labels": labels,
        "legend": legend,
        "encodeOnly": True,
    }
    process = subprocess.run(
        ["node", str(SCRIPT)],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=True,
        cwd=ROOT,
        env={**os.environ, "XYG_NATIVE_LIB": str(_native_lib())},
    )
    assert base64.b64decode(json.loads(process.stdout)["document"]) == document


def test_static_document_rejects_unknown_version_without_output() -> None:
    scene = _scenes()[0]
    document = bytearray(
        _static_document.encode(
            [_static_document.Panel(scene, 0, 0, 160, 120)],
            width=160,
            height=120,
        )
    )
    document[4:8] = (99).to_bytes(4, "little")
    with pytest.raises(ValueError, match="StaticDocument export"):
        _native.static_document_export(bytes(document), "svg")


@pytest.mark.parametrize("field_offset", [32, 44, 56])
def test_static_document_rejects_nonzero_inactive_panel_facts(field_offset: int) -> None:
    scene = _scenes()[0]
    document = bytearray(
        _static_document.encode(
            [_static_document.Panel(scene, 0, 0, 160, 120)],
            width=160,
            height=120,
        )
    )
    document[64 + field_offset : 64 + field_offset + 4] = b"\x00\x00\xc0\x7f"
    with pytest.raises(ValueError, match="StaticDocument export"):
        _native.static_document_export(bytes(document), "svg")
