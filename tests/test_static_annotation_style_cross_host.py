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
    result = bytearray(struct.pack("<4s3I", b"XYAS", 1, len(rows), 0))
    for row in rows:
        style = row.get("style", {})
        result.extend(struct.pack("<2I", len(style), 0))
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
    ):
        result[name] = (_frame([{"style": style}]), "XYG_STATIC_UNSUPPORTED_" + code)
    for key in ("font_size", "font_weight", "rotation"):
        for tag, value in (("nan", float("nan")), ("inf", float("inf"))):
            code = "ANNOTATION_STYLE" if key == "rotation" else "ANNOTATION_TYPOGRAPHY"
            result[f"{key}_{tag}"] = (
                _frame([{"style": {key: value}}]),
                "XYG_STATIC_UNSUPPORTED_" + code,
            )
    for name, rows in (
        ("size", [{}, _styled(font_size=18)]),
        ("style", [{}, _styled(font_style="italic")]),
        ("vertical", [{}, _styled(vertical_align="top")]),
        ("padding", [_styled(background="white"), _styled(background="white", padding="5px")]),
        (
            "canonical_padding",
            [_styled(label_background="white"), _styled(background="white", padding="5px")],
        ),
    ):
        result[f"heterogeneous_{name}"] = (
            _frame(rows),
            "XYG_STATIC_UNSUPPORTED_HETEROGENEOUS_ANNOTATION_STYLE",
        )
    good = _frame([{}])
    for name, offset, value, code in (
        ("version", 4, 2, "VERSION"),
        ("count", 8, 129, "LIMIT"),
        ("reserved", 12, 1, "FLAGS"),
        ("styles_count", 16, 65, "LIMIT"),
        ("row_reserved", 20, 1, "FLAGS"),
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
    magic, version, count, presence, size, padding, flags, vertical = struct.unpack_from(
        "<4s3I2f2I", result
    )
    assert (magic, version, count) == (b"XYAO", 1, len(VALID[name]))
    if name == "empty":
        assert result == struct.pack("<4s3I2f2I", b"XYAO", 1, 0, 0, 0, 0, 0, 0)
    elif name == "dropped":
        assert presence == 0 and result[32:] == struct.pack("<2I", 1, 0)
    elif name == "nontext_size":
        assert presence == 0
    else:
        assert presence & 11 == 11
        assert size == (18 if name == "size_string" else 12)
    if name.startswith("weight_"):
        assert flags == (0 if VALID[name][0]["style"]["font_weight"] == 400 else 2)
    if name.startswith("style_"):
        assert flags == (0 if name == "style_normal" else 1)
    if name.startswith("align_"):
        assert (
            vertical
            == {"baseline": 0, "top": 1, "bottom": 2, "center": 3, "center_baseline": 3}[name[6:]]
        )
    if name in {"paint_box", "padding_default"}:
        assert presence == 15 and padding == 3
    if name == "paint_box":
        assert b"#12345680" in result and b"#ffffffff" in result and b"#ff0000ff" in result
    if name == "opaque":
        assert result[32:] == struct.pack("<2I", 0, 0)
    if name.startswith("rotation"):
        assert result.endswith(struct.pack("<d", 270 if name == "rotation" else 0))


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


def test_public_mixed_annotation_styles_reject_in_native_query():
    chart = xyg.chart(
        xyg.line([0, 1, 2], [1, 3, 2]),
        xyg.text(0, 1, "Default"),
        xyg.text(1, 2, "Larger", style={"font_size": 18}),
    )
    with pytest.raises(
        sd.UnsupportedStaticExport,
        match="XYG_STATIC_UNSUPPORTED_HETEROGENEOUS_ANNOTATION_STYLE",
    ):
        chart.to_svg()


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
