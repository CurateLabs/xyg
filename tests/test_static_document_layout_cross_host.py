"""XYSL layout geometry and malformed-frame parity at the native host seam."""

from __future__ import annotations

import base64
import json
import os
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from xyg import _native

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "packages/xy-node/scripts/static_document_layout_cross_host.mjs"
HEADER = struct.Struct("<4s9I3d")
PANEL = struct.Struct("<2I4d")
OUTPUT = struct.Struct("<4s5I3d")


def _frame(
    panels: list[tuple[int, int, tuple[float, ...]]],
    *,
    normalized: bool = False,
    title: str = "",
    colorbar: bool = False,
    title_y: float = 0.98,
) -> bytes:
    text = title.encode()
    count = len(panels)
    return (
        HEADER.pack(
            b"XYSL",
            1,
            int(normalized),
            0 if normalized else (count + 1) // 2,
            0 if normalized else min(count, 2),
            count,
            400 if normalized else 0,
            300 if normalized else 0,
            int(colorbar),
            len(text),
            16.0,
            0.5,
            title_y,
        )
        + b"".join(PANEL.pack(width, height, *fractions) for width, height, fractions in panels)
        + text
    )


def _node(frames: list[bytes]) -> list[dict[str, str]]:
    if shutil.which("node") is None or not (ROOT / "packages/xy-node/node_modules/koffi").exists():
        pytest.skip("Node host dependencies are not installed")
    process = subprocess.run(
        ["node", str(SCRIPT)],
        input=json.dumps([base64.b64encode(frame).decode() for frame in frames]),
        text=True,
        capture_output=True,
        check=True,
        cwd=ROOT,
        env={**os.environ, "XYG_NATIVE_LIB": str(_native._lib._name)},
    )
    return json.loads(process.stdout)


def test_static_layout_geometry_matches_across_hosts() -> None:
    frames = [
        _frame(
            [(100, 70, (0.0,) * 4), (80, 90, (0.0,) * 4), (130, 50, (0.0,) * 4)],
            title="first\nsecond",
            colorbar=True,
        ),
        _frame(
            [(140, 100, (-0.00625, 0.5, 0.35, 0.25)), (140, 100, (0.50625, 0.0, 0.35, 0.25))],
            normalized=True,
            title="title",
        ),
        _frame([(200, 150, (0.0,) * 4)], title="a\nb\nc", title_y=-1.0),
        _frame([(200, 150, (0.0,) * 4)]),
    ]
    expected = [
        ((210, 242), 50, 105.0, 19.84, [(0, 50), (130, 50), (0, 140)]),
        ((400, 300), 0, 200.0, 21.0, [(-2, 75), (202, 225)]),
        ((200, 220), 70, 100.0, 25.6, [(0, 70)]),
        ((200, 150), 0, 100.0, 15.0, [(0, 0)]),
    ]
    for frame, node, (dimensions, reserve, title_x, baseline, placements) in zip(
        frames, _node(frames), expected, strict=True
    ):
        output = _native.static_document_layout(frame)
        assert "error" not in node, node
        assert base64.b64decode(node["output"]) == output
        magic, version, width, height, count, actual_reserve, x, y, band = OUTPUT.unpack_from(
            output
        )
        assert (magic, version, width, height) == (b"XYLO", 1, *dimensions)
        assert count == len(placements)
        assert len(output) == OUTPUT.size + count * 8
        assert actual_reserve == reserve
        assert x == title_x
        assert y == pytest.approx(baseline, abs=1e-12)
        assert band == (reserve or height)
        assert list(struct.iter_unpack("<2i", output[OUTPUT.size :])) == placements


def test_static_layout_malformed_requests_fail_on_both_hosts() -> None:
    valid = _frame([(200, 150, (0.0,) * 4)], title="title")
    frames = [valid[:length] for length in (0, 3, 63, 64, 103, len(valid) - 1)]
    frames.append(valid + b"\0")
    for offset, value in ((4, 2), (8, 2), (12, 0), (20, 257), (24, 1), (32, 2), (64, 0)):
        frame = bytearray(valid)
        struct.pack_into("<I", frame, offset, value)
        frames.append(bytes(frame))
    for offset in (40, 48, 56, 72):
        frame = bytearray(valid)
        struct.pack_into("<d", frame, offset, float("nan"))
        frames.append(bytes(frame))
    frames.extend((valid[:-1] + b"\0", valid[:-1] + b"\xff"))
    for frame, node in zip(frames, _node(frames), strict=True):
        with pytest.raises(ValueError):
            _native.static_document_layout(frame)
        assert "error" in node, node
        assert "output" not in node


def _facet_frame(
    count: int, columns: int, width: int, height: int, gap: float, title: str
) -> bytes:
    text = title.encode()
    return (
        HEADER.pack(b"XYSL", 1, 2, 0, columns, count, width, height, 0, len(text), 16.0, 0.5, 0.98)
        + PANEL.pack(0, 0, gap, 0.0, 0.0, 0.0) * count
        + text
    )


def test_static_facet_layout_dimensions_and_placement_match_across_hosts() -> None:
    frames = [
        _facet_frame(4, 3, 901, 160, 12.0, "Facets"),
        _facet_frame(2, 2, 200, 100, 12.0, ""),
        _facet_frame(1, 3, 901, 100, 12.0, ""),
    ]
    expected = [
        (
            (901, 356, 24),
            [(0, 24, 292, 160), (304, 24, 292, 160), (608, 24, 292, 160), (0, 196, 292, 160)],
        ),
        ((200, 100, 0), [(0, 0, 120, 100), (132, 0, 120, 100)]),
        ((901, 100, 0), [(0, 0, 292, 100)]),
    ]
    for frame, node, (dimensions, panels) in zip(frames, _node(frames), expected, strict=True):
        output = _native.static_document_layout(frame)
        assert "error" not in node, node
        assert base64.b64decode(node["output"]) == output
        magic, version, width, height, count, reserve, x, y, band = OUTPUT.unpack_from(output)
        assert (magic, version) == (b"XYLO", 1)
        assert (width, height, reserve) == dimensions
        assert len(output) == OUTPUT.size + count * 16
        assert (x, y, band) == (width / 2, 16.0, reserve or height)
        assert list(struct.iter_unpack("<2i2I", output[OUTPUT.size :])) == panels


def test_static_facet_layout_rejects_inactive_and_inconsistent_facts_on_both_hosts() -> None:
    valid = _facet_frame(2, 3, 901, 160, 12.0, "Facets")
    frames = []
    for offset in (12, 32, 64, 68, 80, 88, 96):
        frame = bytearray(valid)
        frame[offset] = 1
        frames.append(bytes(frame))
    for gap in (-1.0, 0.5, float("nan"), float("inf"), 65_536.0):
        frames.append(_facet_frame(2, 3, 901, 160, gap, "Facets"))
    frame = bytearray(valid)
    struct.pack_into("<d", frame, HEADER.size + PANEL.size + 8, 13.0)
    frames.append(bytes(frame))
    frames.extend(
        (
            _facet_frame(2, 0, 901, 160, 12.0, ""),
            _facet_frame(2, 257, 901, 160, 12.0, ""),
            _facet_frame(2, 1, 901, 65_535, 12.0, ""),
            _facet_frame(3, 3, 200, 100, 12.0, ""),
        )
    )
    for frame, node in zip(frames, _node(frames), strict=True):
        with pytest.raises(ValueError):
            _native.static_document_layout(frame)
        assert "error" in node, node
        assert "output" not in node
