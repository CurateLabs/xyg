"""Independent public authoring, not Python-produced Scene replay (#873/#875).

Python uses only public composition constructors. The Node program independently
authors its own Figures and public StaticDocument envelopes and receives no
input. Capturing Python's Rust-bound document is observation of a public export,
not an alternate authoring path. See static_document_authored_coverage.md for
the deliberately explicit Node envelope API and unsupported high-level gaps.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

import xyg
from xyg import _native

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "packages/xy-node/scripts/static_document_authored_cross_host.mjs"
CASES = (
    "styled_line",
    "styled_scatter",
    "text_annotation",
    "anchored_legend",
    "continuous_colorbar",
    "facet_panels",
)
FORMATS = ("svg", "png", "pdf", "jpeg", "webp")
# Decode only: v1 XYST header/panel geometry, independently checked against output.
PANEL = struct.Struct("<2i6I12fII2f4B2I")


def _axes() -> tuple[xyg.Axis, xyg.Axis]:
    return (
        xyg.x_axis(domain=(0, 2), label="Time", format=".1f"),
        xyg.y_axis(domain=(0, 4), label="Value", format=".1f"),
    )


def _line(name: str | None = None) -> xyg.Mark:
    return xyg.line(
        [0, 1, 2],
        [1, 3, 2],
        name=name,
        color="#ef4444",
        width=2,
        opacity=0.75,
        dash=[5, 3],
    )


def _scatter(name: str | None = None, symbol: str = "diamond") -> xyg.Mark:
    return xyg.scatter(
        [0, 1, 2],
        [2, 1, 3],
        name=name,
        color="#3987e5",
        size=6,
        opacity=0.8,
        symbol=symbol,
        stroke="#123456",
        stroke_width=1.5,
    )


def _chart(name: str) -> xyg.Chart | xyg.FacetChart:
    if name == "facet_panels":
        return xyg.facet_chart(
            xyg.line("x", "y", color="#ef4444", width=2),
            *_axes(),
            xyg.legend(show=False),
            data={"x": [0, 1, 0, 1], "y": [1, 3, 2, 4], "group": ["A", "A", "B", "B"]},
            by="group",
            cols=2,
            gap=12,
            share_x=False,
            share_y=False,
            width=332,
            height=160,
            title="Panels & grid",
        )
    children: list[xyg.Mark | xyg.Annotation | xyg.Legend | xyg.Colorbar] = [
        _scatter() if name == "styled_scatter" else _line()
    ]
    if name == "text_annotation":
        children.append(xyg.text(1, 3, "peak < & >", dx=0, dy=-6, color="#654321"))
    if name == "continuous_colorbar":
        children = [
            xyg.scatter(
                [0, 1, 2], [1, 3, 2], color=[0.0, 0.5, 1.0], color_domain=(0.0, 1.0), size=6
            ),
            xyg.colorbar(title="Intensity", ticks=[0.0, 0.5, 1.0]),
        ]
    if name == "anchored_legend":
        children = [_line("Trend"), _scatter("Observed", "circle")]
        children.append(xyg.legend(loc="upper right", anchor=(1.0, 1.0), title="Series"))
    else:
        children.append(xyg.legend(show=False))
    return xyg.chart(*children, *_axes(), width=320, height=240)


@pytest.fixture(scope="module")
def node_authored_documents() -> dict[str, dict]:
    node = shutil.which("node")
    if node is None or not (ROOT / "packages/xy-node/node_modules/koffi").exists():
        pytest.skip("Node host dependencies are not installed")
    process = subprocess.run(
        [node, str(SCRIPT)],
        stdin=subprocess.DEVNULL,
        cwd=ROOT,
        env={**os.environ, "XYG_NATIVE_LIB": str(_native._lib._name)},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    result = json.loads(process.stdout)
    assert result["schema"] == "xyg.static-document-public-authored/v1"
    assert result["authoring"] == "independent Node literals; no input from Python"
    assert [case["name"] for case in result["cases"]] == list(CASES)
    return {case["name"]: case for case in result["cases"]}


def _document_scenes(document: bytes) -> list[bytes]:
    assert document[:4] == b"XYST"
    version, _width, _height, _flags, count, title_bytes = struct.unpack_from("<6I", document, 4)
    assert version == 1
    decoration_bytes = struct.unpack_from("<I", document, 52)[0]
    scenes_at = 64 + count * PANEL.size + title_bytes + decoration_bytes
    scenes = []
    for index in range(count):
        _x, _y, width, height, offset, length = struct.unpack_from(
            "<2i4I", document, 64 + index * PANEL.size
        )
        assert width > 0 and height > 0 and length > 0
        scene = document[scenes_at + offset : scenes_at + offset + length]
        assert len(scene) == length and scene[:4] == b"XYGS"
        scenes.append(scene)
    return scenes


@pytest.mark.parametrize("case_name", CASES)
def test_public_authored_scenes_documents_and_five_exports_match(
    case_name: str,
    node_authored_documents: dict[str, dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    node = node_authored_documents[case_name]
    assert "error" not in node, node.get("error")
    chart = _chart(case_name)
    documents: list[bytes] = []
    native_export = _native.static_document_export

    def capture(
        document: bytes,
        format: str,
        *,
        scale: float = 1.0,
        quality: int = 90,
    ) -> bytes:
        documents.append(bytes(document))
        return native_export(document, format, scale=scale, quality=quality)

    monkeypatch.setattr(_native, "static_document_export", capture)
    node_document = base64.b64decode(node["document"])
    node_scenes = [base64.b64decode(scene) for scene in node["scenes"]]
    assert len(node_scenes) == (2 if case_name == "facet_panels" else 1)
    for format in FORMATS:
        before = len(documents)
        options = {"quality": 90} if format == "jpeg" else {}
        output = chart.to_image(format, engine=xyg.Engine.default, scale=1, **options)
        assert len(documents) == before + 1, "public export did not select Rust StaticDocument"
        assert _document_scenes(documents[-1]) == node_scenes
        assert documents[-1] == node_document
        expected = node["outputs"][format]
        assert len(output) == expected["bytes"]
        assert output[:16].hex() == expected["prefix"]
        assert hashlib.sha256(output).hexdigest() == expected["sha256"]
        if format == "svg":
            assert output.decode() == expected["text"]
            for label in ("Time", "Value"):
                assert label in expected["text"]
            if case_name == "text_annotation":
                assert "peak &lt; &amp; &gt;" in expected["text"]
            if case_name == "anchored_legend":
                for label in ("Trend", "Observed", "Series"):
                    assert label in expected["text"]
            if case_name == "facet_panels":
                assert "Panels &amp; grid" in expected["text"]
            if case_name == "continuous_colorbar":
                assert "Intensity" in expected["text"]
