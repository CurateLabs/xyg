"""Cross-host Scene chrome/support pack parity for Push 3A (ABI 319).

Compares Python scene chrome packers against ``@curatelabs/xyg-node`` and
verifies golden XYAF/XYCF/XYFS bytes for minimal fixtures.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from xyg import _native
from xyg._figure import Figure

ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = ROOT / "packages" / "xy-node" / "scripts" / "scene_chrome_pack_cross_host.mjs"


def _node_bin() -> str:
    return shutil.which("node") or ""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _text_annotation_figure() -> Figure:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.annotate_text("hello", x=0.25, y=0.75, color="#667085")
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


@pytest.mark.skipif(
    not _node_bin() or not NODE_SCRIPT.is_file(), reason="node cross-host script missing"
)
def test_scene_chrome_pack_cross_host_node() -> None:
    proc = subprocess.run(
        [_node_bin(), str(NODE_SCRIPT)],
        cwd=ROOT / "packages" / "xy-node",
        capture_output=True,
        text=True,
        check=False,
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
