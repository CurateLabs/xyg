"""XYAS query parity and independent expected facts; not full authoring parity."""

from __future__ import annotations

import base64
import copy
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import xyg
from xyg import _native
from xyg import _static_document as sd

ROOT = Path(__file__).resolve().parents[1]


def _text(value: str | None) -> bytes:
    if value is None:
        return struct.pack("<I", 0xFFFFFFFF)
    data = value.encode()
    return struct.pack("<I", len(data)) + data


def _frame(rows: list[dict[str, Any]]) -> bytes:
    result = bytearray(struct.pack("<4s3I", b"XYAS", 2, len(rows), 0))
    for row in rows:
        style = row.get("style", {})
        result.extend(struct.pack("<2I", len(style), row.get("flags", 0)))
        result.extend(_text(row.get("text", "note")))
        result.extend(_text(row.get("kind", "text")))
        for key, value in style.items():
            result.extend(_text(key))
            if value is None:
                result.extend(struct.pack("<I", 0))
            elif isinstance(value, str):
                result.extend(struct.pack("<I", 1) + _text(value))
            elif isinstance(value, bool):
                result.extend(struct.pack("<2I", 3, value))
            elif isinstance(value, (int, float)):
                result.extend(struct.pack("<Id", 2, value))
            else:
                result.extend(struct.pack("<I", 4))
    return bytes(result)


def _styled(**style: Any) -> dict[str, Any]:
    return {"style": style}


VALID = {
    "empty": [],
    "default": [{}],
    "dropped": [{"text": "", "style": {"font_family": "Arial"}}],
    "max_count": [{}] * 128,
    "max_text": [{"text": "x" * 4096}],
    "null_alias": [_styled(font_family=None, fontFamily="Arial")],
    "opaque": [_styled(unknown={"original": [1, 2]}, other=float("nan"))],
    "nontext_size": [{"kind": "hline", "style": {"font_size": {"ignored": True}}}],
    "paint_box": [_styled(label_color="#12345680", background="white", border="2px solid red")],
    "padding_default": [
        _styled(background="white"),
        _styled(label_background="white", padding="3px"),
    ],
    "rotation": [_styled(rotation=-450)],
    "rotation_zero": [_styled(rotation=-360)],
    "size_string": [_styled(font_size=" 18 ")],
    # Heterogeneous typography and boxes are per-label facts, not rejections.
    "mixed_size": [{}, _styled(font_size=18)],
    "mixed_style": [{}, _styled(font_style="italic")],
    "mixed_vertical": [{}, _styled(vertical_align="top")],
    "mixed_padding": [
        _styled(background="white"),
        _styled(background="white", padding="5px"),
        _styled(background="white", padding="2px 6px"),
    ],
    "label_order": [
        {"kind": "callout", "style": {"font_size": 17}},
        {"flags": 1, "style": {"font_size": 22}},
        {"kind": "arrow", "text": None},
        {"kind": "rule", "style": {"font_size": 14}},
        {"flags": 2, "style": {"font_size": 24}},
        {"style": {"font_size": 23}},
    ],
    "zero_radius": [_styled(border_radius=0)],
}
for weight in (400, 600, 700, 800, 900, 700.0):
    VALID[f"weight_{weight}"] = [_styled(font_weight=weight)]
for style in ("normal", "ITALIC", "Oblique"):
    VALID[f"style_{style}"] = [_styled(font_style=style)]
for align in ("baseline", "top", "bottom", "center", "center_baseline"):
    VALID[f"align_{align}"] = [_styled(vertical_align=align)]


def _invalid() -> dict[str, tuple[bytes, str]]:
    result = {}
    for name, style, code in (
        ("font", {"font_family": "Arial"}, "CUSTOM_FONT"),
        ("math", {"math_italic_ranges": []}, "MATHTEXT_STYLE"),
        ("weight", {"font_weight": 500}, "ANNOTATION_TYPOGRAPHY"),
        ("weight_fraction", {"font_weight": 700.5}, "ANNOTATION_TYPOGRAPHY"),
        ("size_low", {"font_size": 0.99999999}, "ANNOTATION_TYPOGRAPHY"),
        ("size_high", {"font_size": 1000.00001}, "ANNOTATION_TYPOGRAPHY"),
        ("vertical", {"vertical_align": "middle"}, "ANNOTATION_VERTICAL_ALIGN"),
        ("paint", {"label_color": "var(--ink)"}, "ANNOTATION_STYLE"),
        ("border_underflow", {"border": "1e-50px solid red"}, "ANNOTATION_BBOX"),
        ("padding_negative", {"padding": "-1e-50px"}, "ANNOTATION_BBOX"),
        ("padding_three", {"padding": "1px 2px 3px"}, "ANNOTATION_BBOX"),
        ("round_box", {"background": "white", "border_radius": 5.0}, "ANNOTATION_BOXSTYLE"),
    ):
        result[name] = (_frame([{"style": style}]), "XYG_STATIC_UNSUPPORTED_" + code)
    for key in ("font_size", "font_weight", "rotation"):
        for tag, value in (("nan", float("nan")), ("inf", float("inf"))):
            code = "ANNOTATION_STYLE" if key == "rotation" else "ANNOTATION_TYPOGRAPHY"
            result[f"{key}_{tag}"] = (
                _frame([{"style": {key: value}}]),
                "XYG_STATIC_UNSUPPORTED_" + code,
            )
    good = _frame([{}])
    for name, offset, value, code in (
        ("version", 4, 1, "VERSION"),
        ("count", 8, 129, "LIMIT"),
        ("reserved", 12, 1, "FLAGS"),
        ("styles_count", 16, 65, "LIMIT"),
        ("row_flags", 20, 4, "FLAGS"),
    ):
        data = bytearray(good)
        struct.pack_into("<I", data, offset, value)
        result[name] = (bytes(data), "XYG_STATIC_ANNOTATION_STYLE_" + code)
    # Empty byte buffers are rejected by the generic host ABI transport before
    # reaching XYAS; the Rust module separately checks the zero-length prefix.
    for size in (3, 15, 24, len(good) - 1):
        result[f"truncated_{size}"] = (good[:size], "XYG_STATIC_ANNOTATION_STYLE_HEADER")
    result["empty_transport"] = (b"", "encoded scene must not be empty")
    result["trailing"] = (good + b"\0", "XYG_STATIC_ANNOTATION_STYLE_HEADER")
    result["nul"] = (_frame([{"text": "a\0b"}]), "XYG_STATIC_ANNOTATION_STYLE_TEXT")
    result["text_limit"] = (_frame([{"text": "x" * 4097}]), "XYG_STATIC_ANNOTATION_STYLE_LIMIT")
    return result


INVALID = _invalid()


@pytest.fixture(scope="module")
def node_results():
    if not shutil.which("node") or not (ROOT / "packages/xy-node/node_modules/koffi").exists():
        pytest.skip("Node/koffi unavailable")
    frames = {
        **{name: _frame(rows) for name, rows in VALID.items()},
        **{f"bad_{name}": row[0] for name, row in INVALID.items()},
    }
    process = subprocess.run(
        ["node", str(ROOT / "packages/xy-node/scripts/static_annotation_style_cross_host.mjs")],
        input=json.dumps({name: base64.b64encode(data).decode() for name, data in frames.items()}),
        text=True,
        capture_output=True,
        timeout=120,
        cwd=ROOT,
        env={**os.environ, "XYG_NATIVE_LIB": str(_native._lib._name)},
    )
    assert process.returncode == 0, process.stdout + process.stderr
    results = json.loads(process.stdout)
    assert set(results) == set(frames)
    return results


@pytest.mark.parametrize("name", VALID)
def test_annotation_query_bytes_and_expected_facts(name, node_results):
    result = _native.static_annotation_style(_frame(VALID[name]))
    assert result == base64.b64decode(node_results[name]["output"])
    rows = VALID[name]
    magic, version, count, label_count = struct.unpack_from("<4s3I", result)
    assert (magic, version, count) == (b"XYAO", 2, len(rows))
    table = result[len(result) - 20 * label_count :]
    entries = [struct.unpack_from("<I3f2B2x", table, 20 * i) for i in range(label_count)]
    if name == "empty":
        assert result == struct.pack("<4s3I", b"XYAO", 2, 0, 0)
    elif name == "dropped":
        assert entries == [] and result[16:] == struct.pack("<2I", 1, 0)
    elif name == "nontext_size":
        # An unknown kind yields no label, and its size is never interpreted.
        assert entries == []
    elif name == "label_order":
        # Scene label order: the labelled rule (XYAL), every text row in
        # authored order (XYAW, plain text included, #1024), then the callout
        # (XYAC); the arrow has no label.
        assert [entry[1] for entry in entries] == [14.0, 22.0, 24.0, 23.0, 17.0]
    elif name.startswith("mixed_"):
        sizes = [entry[1] for entry in entries]
        assert all(entry[0] & 1 for entry in entries)
        if name == "mixed_size":
            assert sizes == [12.0, 18.0]
        if name == "mixed_style":
            assert [entry[4] for entry in entries] == [0, 1]
        if name == "mixed_vertical":
            assert [entry[5] for entry in entries] == [0, 1]
        if name == "mixed_padding":
            assert [entry[0] for entry in entries] == [3, 3, 3]
            assert [entry[2:4] for entry in entries] == [(3.0, 3.0), (5.0, 5.0), (6.0, 2.0)]
    elif name != "zero_radius":
        assert entries[0][0] & 1 and entries[0][1] == (18 if name == "size_string" else 12)
    flags = entries[0][4] if entries else 0
    if name.startswith("weight_"):
        assert flags == (0 if VALID[name][0]["style"]["font_weight"] == 400 else 2)
    if name.startswith("style_"):
        assert flags == (0 if name == "style_normal" else 1)
    if name.startswith("align_"):
        assert (
            entries[0][5]
            == {"baseline": 0, "top": 1, "bottom": 2, "center": 3, "center_baseline": 3}[name[6:]]
        )
    if name in {"paint_box", "padding_default"}:
        assert entries[0][0] == 3 and entries[0][2:4] == (3.0, 3.0)
    if name == "paint_box":
        assert b"#12345680" in result and b"#ffffffff" in result and b"#ff0000ff" in result
    if name == "opaque":
        assert result[16:].startswith(struct.pack("<2I", 0, 0))
    if name.startswith("rotation"):
        assert struct.pack("<d", 270 if name == "rotation" else 0) in result


@pytest.mark.parametrize("name", INVALID)
def test_annotation_query_exact_errors(name, node_results):
    payload, reason = INVALID[name]
    with pytest.raises(ValueError, match=re.escape(reason)):
        _native.static_annotation_style(payload)
    assert reason in node_results[f"bad_{name}"]["error"]


@pytest.mark.parametrize("weight", [700, 700.0])
def test_public_annotation_observes_native_query_and_styled_output(weight):
    chart = xyg.chart(
        xyg.line([0, 1, 2], [1, 3, 2]),
        xyg.text(1, 2, "Native note", style={"font_weight": weight, "font_style": "italic"}),
        xyg.x_axis(domain=(0, 2)),
        xyg.y_axis(domain=(0, 4)),
        width=320,
        height=240,
    )
    calls = []
    previous = sys.getprofile()

    def observe(frame, event, _arg):
        if (
            event == "call"
            and frame.f_globals.get("__name__") == "xyg._native"
            and frame.f_code.co_name == "static_annotation_style"
        ):
            calls.append(frame.f_code.co_name)

    sys.setprofile(observe)
    try:
        svg = chart.to_svg()
    finally:
        sys.setprofile(previous)
    assert calls == ["static_annotation_style"]
    assert "Native note" in svg
    assert 'font-style="italic"' in svg and 'font-weight="bold"' in svg


def test_public_mixed_annotation_styles_render_per_annotation():
    chart = xyg.chart(
        xyg.line([0, 1, 2], [1, 3, 2]),
        xyg.x_axis(domain=(0, 2)),
        xyg.y_axis(domain=(0, 4)),
        xyg.text(0.5, 1, "Default"),
        xyg.text(1, 2, "Larger", style={"font_size": 18, "font_weight": "bold"}),
        xyg.text(1.5, 3, "Slanted", style={"font_style": "italic", "label_color": "#336699"}),
        width=320,
        height=240,
    )
    svg = chart.to_svg()
    texts = {
        match.group("text"): match.group("attrs")
        for match in re.finditer(
            r"<text(?P<attrs>[^>]*)>(?P<text>Default|Larger|Slanted)</text>", svg
        )
    }
    assert set(texts) == {"Default", "Larger", "Slanted"}
    assert 'font-size="12"' in texts["Default"]
    assert "font-style" not in texts["Default"] and "font-weight" not in texts["Default"]
    assert 'font-size="18"' in texts["Larger"] and 'font-weight="bold"' in texts["Larger"]
    assert 'font-style="italic"' in texts["Slanted"] and "rgba(51,102,153," in texts["Slanted"]


def test_host_patch_application_preserves_unknown_authoring_and_original():
    source = {
        "kind": "text",
        "text": "note",
        "x": 1,
        "y": 2,
        "style": {
            "unknown": {"original": [1, 2]},
            "font_family": None,
            "fontFamily": "Arial",
            "label_color": "#12345680",
            "rotation": -450,
        },
    }
    original = copy.deepcopy(source)
    resolved = sd.resolve_annotation_styles([source])
    assert source == original
    annotation = resolved.annotations[0]
    assert annotation["x"] == 1 and annotation["y"] == 2
    assert annotation["style"] == {
        "unknown": {"original": [1, 2]},
        "color": "#12345680",
        "rotation": 270,
    }
