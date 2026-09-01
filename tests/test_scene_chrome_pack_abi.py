"""Cross-host Scene chrome/support pack parity for Push 3A (ABI 319+) and bulk packers (ABI 321-324)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from xyg import _native
from xyg._figure import Figure
from xyg._scene_bulk_native import (
    scene_chrome_pack,
    scene_figure_support_materialize,
    scene_xyaf_bulk_pack,
)

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "scene_chrome_pack_cross_host.mjs"
BULK_NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "scene_bulk_pack_cross_host.mjs"
BULK_FIXTURE = ROOT / "tests" / "fixtures" / "scene_bulk_pack_minimal.json"
LIB = (
    ROOT
    / "target"
    / "release"
    / ("libxyg_core.dylib" if sys.platform == "darwin" else "libxyg_core.so")
)


def _node_bin() -> str:
    return shutil.which("node") or ""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _text_annotation_figure() -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.annotations.append(
        {
            "kind": "text",
            "text": "hello",
            "x": 0.25,
            "y": 0.75,
            "style": {"color": "#667085"},
        }
    )
    return figure


def test_scene_xyaf_pack_roundtrip_bytes() -> None:
    packed = _native.scene_xyaf_pack(
        index=0,
        kind_code=0,
        axis_code=0,
        symbol=0,
        anchor=255,
        facts=(1 << 5) | (1 << 6) | (1 << 1),
        style_bits=1,
        linecap=255,
        dash_count=0,
        nums=[0.5, 0.25] + [float("nan")] * 16,
        color=bytes([102, 112, 133, 255]),
        stroke=bytes(4),
        label_color=bytes(4),
        label_fill=bytes(4),
        label_border=bytes(4),
        dash=[0.0] * 8,
        text=b"hi",
    )
    assert packed[:4] == b"XYAF"
    assert packed[232:] == b"hi"


def test_scene_figure_support_pack_minimal() -> None:
    axes_blob = bytes(
        [
            0,
            0,
            0,
            0,
            2,
            0,
            0,
            0,
            5,
            0,
            ord("l"),
            ord("a"),
            ord("b"),
            ord("e"),
            ord("l"),
            4,
            0,
            ord("s"),
            ord("i"),
            ord("d"),
            ord("e"),
        ]
    )
    traces_blob = bytes([0, 0, 7, 0, 0, 0, 0, 0, *b"scatter"])
    packed = _native.scene_figure_support_pack(
        flags=0,
        axes_blob=axes_blob,
        traces_blob=traces_blob,
    )
    assert packed[:4] == b"XYFS"
    assert int.from_bytes(packed[4:8], "little") == 2


def test_scene_xyaf_bulk_pack_text_annotation() -> None:
    annotation = {
        "kind": "text",
        "text": "hello",
        "x": 0.5,
        "y": 0.25,
        "style": {"color": "#667085"},
    }
    packed = scene_xyaf_bulk_pack([annotation])
    assert packed[:4] == b"XYAF"
    assert packed[232:] == b"hello"


def test_scene_xyaf_bulk_pack_matches_low_level_pack() -> None:
    annotation = {
        "kind": "text",
        "text": "hi",
        "x": 0.5,
        "y": 0.25,
        "style": {"color": "#667085"},
    }
    bulk = scene_xyaf_bulk_pack([annotation])
    low = _native.scene_xyaf_pack(
        index=0,
        kind_code=0,
        axis_code=0,
        symbol=0,
        anchor=255,
        facts=(1 << 5) | (1 << 6) | (1 << 1),
        style_bits=1,
        linecap=255,
        dash_count=0,
        nums=[0.5, 0.25] + [float("nan")] * 16,
        color=bytes([102, 112, 133, 255]),
        stroke=bytes(4),
        label_color=bytes(4),
        label_fill=bytes(4),
        label_border=bytes(4),
        dash=[0.0] * 8,
        text=b"hi",
    )
    assert bulk == low


def test_scene_xyaf_bulk_pack_index_override() -> None:
    annotation = {
        "kind": "text",
        "text": "hi",
        "x": 0.5,
        "y": 0.25,
        "style": {"color": "#667085"},
    }
    packed = scene_xyaf_bulk_pack([annotation], indices=[7])
    assert int.from_bytes(packed[8:12], "little") == 7


def test_scene_xyaf_bulk_pack_via_scene_v3_helper() -> None:
    from xyg._scene_v3 import _pack_xyaf_bulk

    packed = _pack_xyaf_bulk(_text_annotation_figure().annotations)
    assert packed[:4] == b"XYAF"
    assert packed[232:] == b"hello"


@pytest.mark.skipif(
    not _node_bin() or not NODE_SCRIPT.is_file(), reason="node cross-host script missing"
)
def test_scene_chrome_pack_cross_host_node() -> None:
    env = os.environ.copy()
    env.setdefault("XYG_NATIVE_LIB", str(LIB))
    proc = subprocess.run(
        [_node_bin(), str(NODE_SCRIPT)],
        cwd=ROOT / "packages" / "xy-node",
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    py_xyaf = _native.scene_xyaf_pack(
        index=0,
        kind_code=0,
        axis_code=0,
        symbol=0,
        anchor=255,
        facts=(1 << 5) | (1 << 6) | (1 << 1),
        style_bits=1,
        linecap=255,
        dash_count=0,
        nums=[0.5, 0.25] + [float("nan")] * 16,
        color=bytes([102, 112, 133, 255]),
        stroke=bytes(4),
        label_color=bytes(4),
        label_fill=bytes(4),
        label_border=bytes(4),
        dash=[0.0] * 8,
        text=b"hi",
    )
    axes_blob = bytes(
        [
            0,
            0,
            0,
            0,
            2,
            0,
            0,
            0,
            5,
            0,
            ord("l"),
            ord("a"),
            ord("b"),
            ord("e"),
            ord("l"),
            4,
            0,
            ord("s"),
            ord("i"),
            ord("d"),
            ord("e"),
        ]
    )
    traces_blob = bytes([0, 0, 7, 0, 0, 0, 0, 0, *b"scatter"])
    py_xyfs = _native.scene_figure_support_pack(
        flags=0, axes_blob=axes_blob, traces_blob=traces_blob
    )
    assert _sha256(py_xyaf) == payload["xyaf_sha256"]
    assert _sha256(py_xyfs) == payload["xyfs_sha256"]


def _bulk_fixture() -> dict:
    return json.loads(BULK_FIXTURE.read_text(encoding="utf-8"))


def test_scene_bulk_pack_minimal_fixture_bytes() -> None:
    fixture = _bulk_fixture()
    chrome = fixture["chrome"]
    support = fixture["figure_support"]
    xycf = scene_chrome_pack(**chrome)
    xyfs = scene_figure_support_materialize(
        polar=support["polar"],
        colorbar_unsupported=support["colorbar_unsupported"],
        has_custom_font=support["has_custom_font"],
        has_browser_css=support["has_browser_css"],
        has_extra_legends=support["has_extra_legends"],
        annotations=support["annotations"],
        axes=support["axes"],
        traces=support["traces"],
    )
    assert xycf[:4] == b"XYCF"
    assert xyfs[:4] == b"XYFS"
    assert len(xycf) == 564


@pytest.mark.skipif(
    not _node_bin() or not BULK_NODE_SCRIPT.is_file(), reason="node bulk cross-host script missing"
)
def test_scene_bulk_pack_cross_host_node() -> None:
    fixture = _bulk_fixture()
    env = os.environ.copy()
    env.setdefault("XYG_NATIVE_LIB", str(LIB))
    proc = subprocess.run(
        [_node_bin(), str(BULK_NODE_SCRIPT)],
        cwd=ROOT / "packages" / "xy-node",
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    chrome = fixture["chrome"]
    support = fixture["figure_support"]
    py_xycf = scene_chrome_pack(**chrome)
    py_xyfs = scene_figure_support_materialize(
        polar=support["polar"],
        colorbar_unsupported=support["colorbar_unsupported"],
        has_custom_font=support["has_custom_font"],
        has_browser_css=support["has_browser_css"],
        has_extra_legends=support["has_extra_legends"],
        annotations=support["annotations"],
        axes=support["axes"],
        traces=support["traces"],
    )
    assert _sha256(py_xycf) == payload["xycf_sha256"]
    assert _sha256(py_xyfs) == payload["xyfs_sha256"]
    py_xyaf = scene_xyaf_bulk_pack(
        [
            {
                "kind": "text",
                "text": "hello",
                "x": 0.5,
                "y": 0.25,
                "style": {"color": "#667085"},
            }
        ]
    )
    assert _sha256(py_xyaf) == payload["xyaf_sha256"]
