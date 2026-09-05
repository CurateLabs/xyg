"""XYDA admission and independent public document-label delegation proofs."""

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
NUMBERS = ("x", "y", "size", "rotation", "opacity")
STRINGS = ("text", "family", "anchor", "vertical_align", "font_style", "weight", "color")


def _frame(labels: list[dict[str, Any]]) -> bytes:
    data = bytearray(struct.pack("<4s3I", b"XYDA", 1, len(labels), 0))
    for label in labels:
        flags = sum(1 << i for i, key in enumerate(NUMBERS) if key in label)
        data.extend(struct.pack("<2I5d", flags, 0, *(label.get(key, 0) for key in NUMBERS)))
        for key in STRINGS:
            value = label.get(key)
            if value is None:
                data.extend(struct.pack("<I", 0xFFFFFFFF))
            else:
                encoded = str(value).encode()
                data.extend(struct.pack("<I", len(encoded)))
                data.extend(encoded)
    return bytes(data)


VALID: dict[str, list[dict[str, Any]]] = {
    "default": [{}],
    "empty": [],
    "max_count": [{}] * 64,
    "max_text": [{"text": "a" * 4096}],
    "outside_rotation": [{"x": -0.5, "y": 1.5, "size": 4096, "rotation": 450, "opacity": 0.25}],
    "unicode_color": [
        {
            "text": "雪 & é",
            "color": "#01020380",
            "family": "DejaVu Sans",
            "font_style": "Oblique",
            "weight": "BOLD",
        }
    ],
}
for anchor in ("start", "middle", "end"):
    for vertical in ("top", "baseline", "bottom", "center", "center_baseline"):
        VALID[f"alignment_{anchor}_{vertical}"] = [{"anchor": anchor, "vertical_align": vertical}]
for weight in (
    "normal",
    "regular",
    "book",
    "400",
    "bold",
    "semibold",
    "demibold",
    "heavy",
    "black",
    "600",
    "700",
    "800",
    "900",
):
    VALID[f"weight_{weight}"] = [{"weight": weight, "font_style": "ITALIC"}]
for family in (" system-ui, sans-serif ", "SANS-SERIF"):
    VALID[f"family_{family}"] = [{"family": family}]


def _invalid() -> dict[str, tuple[bytes, str]]:
    good = _frame([{}])
    rows = {f"truncated_{i}": (good[:i], "HEADER") for i in (1, 3, 15, 16, 63, len(good) - 1)}
    for name, at, value, reason in (
        ("version", 4, 2, "VERSION"),
        ("count", 8, 65, "LIMIT"),
        ("reserved", 12, 1, "FLAGS"),
        ("label_flags", 16, 32, "FLAGS"),
        ("label_reserved", 20, 1, "FLAGS"),
    ):
        data = bytearray(good)
        struct.pack_into("<I", data, at, value)
        rows[name] = (bytes(data), reason)
    for i, key in enumerate(NUMBERS):
        data = bytearray(good)
        struct.pack_into("<d", data, 24 + i * 8, -0.0)
        rows[f"inactive_{key}"] = (bytes(data), "FLAGS")
        for tag, value in (("nan", float("nan")), ("inf", float("inf")), ("overflow", 1e300)):
            rows[f"{key}_{tag}"] = (_frame([{key: value}]), "STYLE")
    for name, label in (
        ("size_low", {"size": 0}),
        ("size_high", {"size": 4097}),
        ("opacity_low", {"opacity": -0.1}),
        ("opacity_high", {"opacity": 1.1}),
        ("size_round_low", {"size": 0.99999999}),
        ("size_round_high", {"size": 4096.0001}),
        ("opacity_round_high", {"opacity": 1.00000001}),
        ("opacity_underflow", {"opacity": -1e-50}),
        ("font", {"family": "Arial"}),
        ("empty_family", {"family": ""}),
        ("anchor", {"anchor": "left"}),
        ("vertical", {"vertical_align": "middle"}),
        ("style", {"font_style": "slanted"}),
        ("weight", {"weight": "500"}),
        ("browser_paint", {"color": "var(--ink)"}),
    ):
        rows[name] = (_frame([label]), "STYLE")
    rows["long_text"] = (_frame([{"text": "x" * 4097}]), "LIMIT")
    rows["nul"] = (_frame([{"text": "a\0b"}]), "TEXT")
    data = bytearray(_frame([{"text": "x"}]))
    data[68] = 255
    rows["utf8"] = (bytes(data), "TEXT")
    rows["trailing"] = (good + b"\0", "HEADER")
    rows["total_limit"] = (good + bytes(2 * 1024 * 1024), "LIMIT")
    return rows


INVALID = _invalid()
PUBLIC: dict[str, list[dict[str, Any]]] = {
    "default": [{"text": "Default < & >"}],
    "styled": [
        {
            "text": "Italic < & >",
            "x": 0.4,
            "y": 0.6,
            "size": 14,
            "rotation": 90,
            "opacity": 0.5,
            "family": "DejaVu Sans",
            "anchor": "end",
            "vertical_align": "top",
            "font_style": "Oblique",
            "weight": "SEMIBOLD",
            "color": "#654321",
        },
        {
            "text": "Normal",
            "x": 0.7,
            "y": 0.3,
            "anchor": "start",
            "vertical_align": "baseline",
            "family": "sans-serif",
        },
    ],
}


@pytest.fixture(scope="module")
def node_results():
    if not shutil.which("node") or not (ROOT / "packages/xy-node/node_modules/koffi").exists():
        pytest.skip("Node/koffi unavailable")
    frames = {
        **{name: _frame(value) for name, value in VALID.items()},
        **{f"bad_{name}": value[0] for name, value in INVALID.items()},
    }
    process = subprocess.run(
        ["node", str(ROOT / "packages/xy-node/scripts/static_document_labels_cross_host.mjs")],
        input=json.dumps(
            {name: base64.b64encode(value).decode() for name, value in frames.items()}
        ),
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
def test_label_query_bytes_and_native_policy(name, node_results):
    actual = _native.static_document_labels(_frame(VALID[name]))
    assert actual == base64.b64decode(node_results["queries"][name]["output"])
    if name == "empty":
        assert actual == b""
    elif name == "default":
        assert actual == struct.pack(
            "<5f8B3I", 0.5, 0.5, 12, 0, 1, 38, 38, 38, 255, 1, 3, 0, 0, 0, 0, 0
        )
    elif name.startswith("alignment_"):
        label = VALID[name][0]
        assert actual[24] == {"start": 0, "middle": 1, "end": 2}[label["anchor"]]
        assert (
            actual[25]
            == {"top": 0, "baseline": 1, "bottom": 2, "center": 3, "center_baseline": 3}[
                label["vertical_align"]
            ]
        )
    elif name.startswith("weight_"):
        assert actual[26] == (
            1 if VALID[name][0]["weight"] in {"normal", "regular", "book", "400"} else 3
        )
    elif name == "unicode_color":
        assert actual[20:24] == bytes([1, 2, 3, 128])
        assert actual[40:] == "雪 & é".encode()
    elif name == "outside_rotation":
        assert struct.unpack_from("<5f", actual) == (-0.5, 1.5, 4096, 450, 0.25)


@pytest.mark.parametrize("name", INVALID)
def test_label_query_stable_errors(name, node_results):
    frame, code = INVALID[name]
    reason = (
        "XYG_STATIC_UNSUPPORTED_FIGURE_LABEL_STYLE"
        if code == "STYLE"
        else f"XYG_STATIC_DOCUMENT_LABELS_{code}"
    )
    with pytest.raises(ValueError, match=re.escape(reason)):
        _native.static_document_labels(frame)
    assert reason in node_results["queries"][f"bad_{name}"]["error"]


def _label_block(document: bytes) -> bytes:
    count, title_length = struct.unpack_from("<2I", document, 20)
    at = 64 + count * 104 + title_length
    assert document[at : at + 4] == b"XYDD"
    labels = struct.unpack_from("<I", document, at + 8)[0]
    start = at + 32
    end = start
    for _ in range(labels):
        end += 40 + struct.unpack_from("<I", document, end + 28)[0]
    return document[start:end]


@pytest.mark.parametrize("name", PUBLIC)
def test_public_label_packers_execute_query_and_match(name, node_results, monkeypatch):
    chart = xyg.chart(
        xyg.line([0, 1, 2], [1, 3, 2], color="#ef4444", width=2),
        xyg.x_axis(domain=(0, 2)),
        xyg.y_axis(domain=(0, 4)),
        xyg.legend(show=False),
        width=320,
        height=240,
    )
    scene = figure_scene(chart.figure())
    native = _native.static_document_labels
    calls = []

    def observe(payload):
        output = native(payload)
        calls.append((bytes(payload), bytes(output)))
        return output

    monkeypatch.setattr(_native, "static_document_labels", observe)
    document = sd.encode(
        [sd.Panel(scene, 0, 0, 320, 240)], width=320, height=240, labels=PUBLIC[name]
    )
    assert len(calls) == 1, "public labels bypassed the Rust authoring query"
    assert calls[0][0][:4] == b"XYDA"
    assert _label_block(document) == calls[0][1]
    node = node_results["public"][name]
    assert scene == base64.b64decode(node["scene"])
    assert document == base64.b64decode(node["document"])
    assert _label_block(document) == base64.b64decode(node["labels"])
    assert _native.static_document_export(document, "svg") == base64.b64decode(node["svg"])
