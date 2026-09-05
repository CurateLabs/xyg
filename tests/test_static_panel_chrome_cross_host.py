"""Execute the same bounded panel-chrome query through Python and Node."""

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
SCRIPT = ROOT / "packages/xy-node/scripts/static_panel_chrome_cross_host.mjs"
HEADER = struct.Struct("<4s13I8x17d")
OUTPUT = struct.Struct("<4s3I9d")


def _frame(*, multiline: bool = False, measured: bool = False) -> bytes:
    x_label = "first\nsecond" if multiline else ""
    x_ticks = ["alpha\nbeta"] if multiline else []
    titles = [(14.0, 6.0, 1.0, True, "Title")] if multiline else []
    flags = 1 | (4 if multiline else 0) | (16 if measured else 0)
    measurements = (100.0, 60.0, 140.0, 170.0) if measured else (0.0,) * 4
    header = HEADER.pack(
        b"XYPC",
        1,
        flags,
        2,
        len(x_ticks),
        0,
        len(titles),
        len(x_label.encode()),
        0,
        0,
        0,
        4 if multiline else 0,
        3 if multiline else 0,
        0,
        300.0,
        600.0,
        72.0,
        0.0,
        11.0,
        0.0,
        12.0,
        11.0,
        0.0,
        12.0,
        0.0,
        4.0,
        0.0,
        *measurements,
    )
    out = bytearray(header + x_label.encode())
    for label in x_ticks:
        text = label.encode()
        out.extend(struct.pack("<I", len(text)))
        out.extend(text)
    for size, pad, y, automatic, title in titles:
        text = title.encode()
        out.extend(struct.pack("<3d2I", size, pad, y, int(automatic), len(text)))
        out.extend(text)
    return bytes(out)


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


def test_panel_chrome_layout_bytes_and_geometry_match_across_hosts() -> None:
    frames = [_frame(), _frame(multiline=True), _frame(measured=True)]
    expected = [
        (46.0, 6.0, 8.0, 36.0, 0.0, 0.0, 0.0, 354.0, 300.0),
        (46.0, 32.0, 130.0, 50.4, 26.0, 122.0, 14.4, 476.0, 300.0),
        (100.0, 60.0, 140.0, 170.0, 0.0, 0.0, 0.0, 354.0, 300.0),
    ]
    for frame, node, geometry in zip(frames, _node(frames), expected, strict=True):
        output = _native.static_panel_chrome(frame)
        assert "error" not in node, node
        assert base64.b64decode(node["output"]) == output
        assert len(output) == OUTPUT.size
        magic, version, compact, reserved, *actual = OUTPUT.unpack(output)
        assert (magic, version, compact, reserved) == (b"XYPO", 1, 1, 0)
        assert actual == pytest.approx(geometry, abs=1e-12)


@pytest.mark.parametrize(
    ("unsupported", "reason"),
    [(1, "XYG_STATIC_UNSUPPORTED_BROWSER_CHROME"), (2, "XYG_STATIC_UNSUPPORTED_CUSTOM_FONT")],
)
def test_panel_chrome_unsupported_facts_have_shared_stable_reasons(
    unsupported: int, reason: str
) -> None:
    frame = bytearray(_frame())
    struct.pack_into("<I", frame, 36, unsupported)
    node = _node([bytes(frame)])[0]
    with pytest.raises((ValueError, RuntimeError), match=reason):
        _native.static_panel_chrome(bytes(frame))
    assert reason in node["error"]
    assert "output" not in node


def test_panel_chrome_malformed_requests_reject_without_output_on_both_hosts() -> None:
    valid = _frame(multiline=True)
    frames = [valid[:length] for length in (0, 3, 199, 200, len(valid) - 1)]
    frames.append(valid + b"\0")
    for offset, value in ((4, 2), (8, 32), (12, 257), (24, 4), (40, 3), (44, 5), (52, 3), (56, 1)):
        frame = bytearray(valid)
        struct.pack_into("<I", frame, offset, value)
        frames.append(bytes(frame))
    for offset in (64, 96, 136, 160, 168):
        frame = bytearray(valid)
        struct.pack_into("<d", frame, offset, float("nan"))
        frames.append(bytes(frame))
    frames.extend((valid[:-1] + b"\0", valid[:-1] + b"\xff"))
    for frame, node in zip(frames, _node(frames), strict=True):
        with pytest.raises((ValueError, RuntimeError)):
            _native.static_panel_chrome(frame)
        assert "error" in node, node
        assert "output" not in node
