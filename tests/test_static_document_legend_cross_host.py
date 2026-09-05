"""XYDL query parity and independently authored document-legend delegation."""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Any

import pytest

import xyg
from xyg import _native
from xyg import _static_document as sd
from xyg._scene_v3 import figure_scene

ROOT = Path(__file__).resolve().parents[1]
HEADER = struct.Struct("<4s3IiI5d")
TEXT_FIELDS = (
    "title",
    "loc",
    "figure_loc",
    "fontSize",
    "padding",
    "rowGap",
    "color",
    "background",
    "borderColor",
    "alpha",
    "fontFamily",
)


def _text(value: str | None) -> bytes:
    if value is None:
        return struct.pack("<I", 0xFFFFFFFF)
    encoded = value.encode()
    return struct.pack("<I", len(encoded)) + encoded


def _frame(items: list[dict[str, Any]] | None = None, /, **facts: Any) -> bytes:
    if items is None:
        items = [{}]
    flags = sum(
        bit
        for key, bit in (("ncols", 1), ("handle", 2), ("pad", 4), ("border", 8), ("anchor", 16))
        if key in facts
    )
    anchor = facts.get("anchor", (0, 0))
    data = bytearray(
        HEADER.pack(
            b"XYDL",
            1,
            flags,
            len(items),
            facts.get("ncols", 0),
            0,
            facts.get("handle", 0),
            facts.get("pad", 0),
            facts.get("border", 0),
            *anchor,
        )
    )
    for key in TEXT_FIELDS:
        data.extend(_text(facts.get(key)))
    for item in items:
        flags = sum(
            bit
            for key, bit in (("width", 1), ("stroke_width", 2), ("size", 4), ("opacity", 8))
            if key in item
        ) | (16 if item.get("dash") else 0)
        data.extend(
            struct.pack(
                "<2I4d",
                flags,
                0,
                *(item.get(key, 0) for key in ("width", "stroke_width", "size", "opacity")),
            )
        )
        for key in ("kind", "name", "color", "symbol"):
            data.extend(_text(item.get(key)))
    return bytes(data)


VALID = {
    "default": _frame(),
    "empty": _frame([]),
    "glyphs": _frame(
        [
            {"kind": kind, "name": kind}
            for kind in ("line", "segments", "step", "stairs", "errorbar", "stem", "scatter", "bar")
        ]
    ),
    "half_alpha_even_down": _frame(alpha=str(0.5 / 255)),
    "half_alpha_even_up": _frame(alpha=str(1.5 / 255)),
    "styles": _frame(
        [
            {
                "width": 4,
                "stroke_width": 9,
                "size": 7,
                "opacity": 2,
                "dash": True,
                "color": "#12345680",
            }
        ],
        ncols=-2,
        handle=3,
        pad=1,
        border=-5,
        anchor=(-0.5, 1.5),
        title="Kinds < & >",
        loc="lower left",
        figure_loc="outside right upper",
        fontSize="14px",
        padding="0.6em",
        rowGap="0.7em",
        background="#ffffff",
        alpha="0.5",
    ),
    "fallback_units": _frame(fontSize="2em", padding="3px", rowGap="bogusem"),
    "clamped_opacity": _frame([{"opacity": -2}], alpha="-1"),
    "max_items": _frame([{}] * 256),
    "max_name": _frame([{"name": "a" * 4096}]),
}


def _bad_frames() -> dict[str, tuple[bytes, str]]:
    good = _frame()
    rows = {f"truncated_{i}": (good[:i], "HEADER") for i in (1, 3, 63, 64, len(good) - 1)}
    for name, offset, value, reason in (
        ("version", 4, 2, "VERSION"),
        ("flags", 8, 32, "FLAGS"),
        ("count", 12, 257, "LIMIT"),
        ("reserved", 20, 1, "FLAGS"),
    ):
        data = bytearray(good)
        struct.pack_into("<I", data, offset, value)
        rows[name] = (bytes(data), reason)
    data = bytearray(good)
    struct.pack_into("<d", data, 24, -0.0)
    rows["inactive_negative_zero"] = (bytes(data), "FLAGS")
    for name, offset, value in (("item_flags", 108, 32), ("item_reserved", 112, 1)):
        data = bytearray(good)
        struct.pack_into("<I", data, offset, value)
        rows[name] = (bytes(data), "FLAGS")
    data = bytearray(good)
    struct.pack_into("<d", data, 116, -0.0)
    rows["item_inactive_negative_zero"] = (bytes(data), "FLAGS")
    data = bytearray(_frame(title="A"))
    data[68] = 255
    rows["invalid_utf8"] = (bytes(data), "TEXT")
    rows["nonfinite_frame_alpha"] = (_frame(alpha="nan"), "STYLE")
    for name, facts, reason in (
        ("nan_handle", {"handle": float("nan")}, "STYLE"),
        ("infinite_anchor", {"anchor": (float("inf"), 0)}, "ANCHOR"),
        ("f32_anchor_overflow", {"anchor": (1e300, 0)}, "ANCHOR"),
        ("ncols", {"ncols": 257}, "LIMIT"),
        ("custom_font", {"fontFamily": "Fancy"}, "STYLE"),
        ("browser_color", {"color": "var(--ink)"}, "STYLE"),
        ("nan_css", {"fontSize": "nanpx"}, "STYLE"),
        ("empty_location", {"loc": ""}, "STYLE"),
        ("nul_title", {"title": "a\0b"}, "TEXT"),
    ):
        rows[name] = (_frame(**facts), reason)
    rows["noncircle_scatter"] = (_frame([{"kind": "scatter", "symbol": "diamond"}]), "STYLE")
    rows["nonfinite_opacity"] = (_frame([{"opacity": float("inf")}]), "STYLE")
    rows["long_name"] = (_frame([{"name": "a" * 4097}]), "LIMIT")
    rows["oversized_input"] = (good + bytes(2 * 1024 * 1024), "LIMIT")
    rows["trailing"] = (good + b"\0", "HEADER")
    return rows


INVALID = _bad_frames()


def _reason(code: str) -> str:
    return {
        "STYLE": "XYG_STATIC_UNSUPPORTED_FIGURE_LEGEND_STYLE",
        "ANCHOR": "XYG_STATIC_UNSUPPORTED_PANEL_LEGEND_ANCHOR",
    }.get(code, f"XYG_STATIC_DOCUMENT_LEGEND_{code}")


PUBLIC: dict[str, dict[str, Any]] = {
    "default": {"items": [{"name": "Line"}]},
    "styled": {
        "title": "Kinds < & >",
        "ncols": 2,
        "anchor": (0.9, 0.9),
        "handlelength": 3,
        "handletextpad": 1,
        "border_pad": 2,
        "style": {
            "fontSize": "13px",
            "padding": "0.6em",
            "rowGap": "0.7em",
            "color": "#123456",
            "background": "#ffffff",
            "borderColor": "#222222",
            "--xy-legend-frame-alpha": str(1.5 / 255),
        },
        "items": [
            {
                "kind": "line",
                "name": "Line",
                "style": {"width": 4, "stroke_width": 9, "dash": True, "color": "#123456"},
            },
            {
                "kind": "scatter",
                "name": "Point",
                "style": {"size": 7, "opacity": 2, "color": "#654321"},
            },
            {"kind": "bar", "name": "Patch", "style": {"color": "#22aa44"}},
        ],
    },
}


@pytest.fixture(scope="module")
def node_results():
    if not shutil.which("node") or not (ROOT / "packages/xy-node/node_modules/koffi").exists():
        pytest.skip("Node/koffi unavailable")
    frames = {**VALID, **{f"bad_{key}": value[0] for key, value in INVALID.items()}}
    process = subprocess.run(
        ["node", str(ROOT / "packages/xy-node/scripts/static_document_legend_cross_host.mjs")],
        input=json.dumps({key: base64.b64encode(value).decode() for key, value in frames.items()}),
        text=True,
        capture_output=True,
        timeout=120,
        cwd=ROOT,
        env={**os.environ, "XYG_NATIVE_LIB": str(_native._lib._name)},
    )
    assert process.returncode == 0, process.stdout + process.stderr
    result = json.loads(process.stdout)
    assert set(result["queries"]) == set(frames)
    assert set(result["public"]) == set(PUBLIC)
    return result


@pytest.mark.parametrize("name", VALID)
def test_raw_legend_query_bytes_and_policy(name, node_results):
    actual = _native.static_document_legend(VALID[name])
    assert actual == base64.b64decode(node_results["queries"][name]["output"])
    if name == "empty":
        assert actual == b""
    elif name.startswith("half_alpha"):
        assert actual[47] == actual[51] == (0 if name.endswith("down") else 2)
    elif name == "default":
        assert struct.unpack_from("<4I", actual) == (1, 0, 11, 1)
        assert actual[44:48] == bytes([128, 128, 128, 20])
        assert struct.unpack_from("<3f", actual, 64 + 11 + 8) == (1.5, 8.0, 1.0)
    elif name == "styles":
        title_len, loc_len = struct.unpack_from("<2I", actual, 4)
        assert actual[64 + title_len : 64 + title_len + loc_len] == b"upper right"
        assert struct.unpack_from("<2f", actual, 52) == (-0.5, 1.5)
        assert struct.unpack_from("<3f", actual, 64 + title_len + loc_len + 8) == (4.0, 7.0, 1.0)
    elif name == "glyphs":
        offset = 64 + struct.unpack_from("<I", actual, 8)[0]
        kinds = []
        while offset < len(actual):
            kinds.append(actual[offset])
            offset += 28 + struct.unpack_from("<I", actual, offset + 20)[0]
        assert kinds == [0, 0, 0, 0, 0, 0, 1, 2]


@pytest.mark.parametrize("name", INVALID)
def test_raw_legend_query_stable_errors(name, node_results):
    data, code = INVALID[name]
    reason = _reason(code)
    with pytest.raises(ValueError, match=re.escape(reason)):
        _native.static_document_legend(data)
    assert reason in node_results["queries"][f"bad_{name}"]["error"]


def _legend_block(document: bytes) -> bytes:
    panels, title = struct.unpack_from("<2I", document, 20)
    at = 64 + panels * 104 + title
    assert document[at : at + 4] == b"XYDD"
    assert struct.unpack_from("<I", document, at + 8)[0] == 0
    length = struct.unpack_from("<I", document, at + 12)[0]
    return document[at + 32 : at + 32 + length]


@pytest.mark.parametrize("name", PUBLIC)
def test_public_document_packers_delegate_and_match(name, node_results, monkeypatch):
    scene = figure_scene(
        xyg.chart(
            xyg.line([0, 1, 2], [1, 3, 2], color="#ef4444", width=2),
            xyg.x_axis(domain=(0, 2)),
            xyg.y_axis(domain=(0, 4)),
            xyg.legend(show=False),
            width=320,
            height=240,
        ).figure()
    )
    calls = []
    native = _native.static_document_legend

    def observe(payload):
        output = native(payload)
        calls.append((bytes(payload), bytes(output)))
        return output

    monkeypatch.setattr(_native, "static_document_legend", observe)
    document = sd.encode(
        [sd.Panel(scene, 0, 0, 320, 240)], width=320, height=240, legend=PUBLIC[name]
    )
    assert len(calls) == 1, "public document packer bypassed Rust legend query"
    assert calls[0][0][:4] == b"XYDL"
    assert _legend_block(document) == calls[0][1]
    node = node_results["public"][name]
    assert scene == base64.b64decode(node["scene"])
    assert document == base64.b64decode(node["document"])
    assert _legend_block(document) == base64.b64decode(node["legend"])
    assert _native.static_document_export(document, "svg") == base64.b64decode(node["svg"])
