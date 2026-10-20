"""Python/Node agreement for the Rust chrome-style projection (#1004).

Both hosts author the same chart literals independently and export every
admitted format through the shared native projection; raw XYCS frames must
resolve to identical XYCO bytes or identical stable reasons.
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
from typing import Any

import pytest

import xyg
from xyg import _native

ROOT = Path(__file__).resolve().parents[1]
FORMATS = ("svg", "png", "pdf", "jpeg", "webp")


def _chart(
    styles: dict[str, Any] | None = None,
    root: dict[str, Any] | None = None,
    x_style: dict[str, Any] | None = None,
) -> Any:
    return xyg.chart(
        xyg.line([0, 1], [0, 1], color="#ef4444", width=2),
        xyg.x_axis(domain=(0, 1), label="X", style=x_style),
        xyg.y_axis(domain=(0, 1), label="Y"),
        styles=styles,
        style=root,
        title="Title",
        width=320,
        height=240,
    )


CASES = {
    "default": _chart(),
    "tick_30": _chart({"tick_label": {"font-size": "30px"}}),
    "typography": _chart(
        {
            "title": {"font-weight": "bold", "color": "#102030"},
            "axis_title": {"color": "#ff0000", "font-style": "italic", "font-size": "16px"},
            "tick_label": {"color": "#00ff00", "font-weight": "bold", "font-size": "10px"},
        }
    ),
    "precedence": _chart(
        {"tick_label": {"font-size": "20px", "color": "#00ff00"}},
        {"--chart-text": "#0000ff"},
        {"tick-label-size": 9, "label-color": "#ff0000"},
    ),
}

FAILURES = {
    "bad_size": ({"tick_label": {"font-size": "2em"}}, "XYG_STATIC_UNSUPPORTED_CHROME_FONT_SIZE"),
    "bad_weight": ({"title": {"font-weight": "600"}}, "XYG_STATIC_UNSUPPORTED_CHROME_FONT_WEIGHT"),
    "bad_color": ({"title": {"color": "var(--x)"}}, "XYG_STATIC_UNSUPPORTED_CHROME_COLOR"),
    "bad_slot": ({"legend": {"font-size": "12px"}}, "XYG_STATIC_UNSUPPORTED_CHROME_STYLE"),
    "bad_font": ({"title": {"font-family": "Comic Sans"}}, "XYG_STATIC_UNSUPPORTED_CUSTOM_FONT"),
}


def _text(value: str) -> bytes:
    data = value.encode()
    return struct.pack("<I", len(data)) + data


def _frame(
    *,
    title: bool = True,
    root: dict[str, str] | None = None,
    slots: dict[str, dict[str, str]] | None = None,
    x: dict[str, str] | None = None,
) -> bytes:
    def entries(mapping: dict[str, str] | None) -> bytes:
        mapping = mapping or {}
        out = struct.pack("<I", len(mapping))
        for key, value in sorted(mapping.items()):
            out += _text(key) + struct.pack("<I", 1) + _text(value)
        return out

    slots = slots or {}
    out = struct.pack("<4s3I", b"XYCS", 1, int(title), 0) + entries(root)
    out += struct.pack("<I", len(slots))
    for name, style in sorted(slots.items()):
        out += _text(name) + entries(style)
    return out + entries(x) + entries(None) + entries(None) + entries(None)


FRAMES = {
    "empty": _frame(),
    "slots": _frame(slots={"tick_label": {"font-size": "30px", "color": "#123456"}}),
    "root_axis": _frame(root={"--chart-text": "#0000ff"}, x={"label_color": "#ff0000"}),
    "bad_header": b"NOPE" + _frame()[4:],
    "bad_version": _frame()[:4] + struct.pack("<I", 9) + _frame()[8:],
    "truncated": _frame()[:-1],
    "trailing": _frame() + b"\0",
    "bad_slot": _frame(slots={"legend": {}}),
    "bad_font": _frame(slots={"title": {"font-family": "Papyrus"}}),
}


@pytest.fixture(scope="module")
def node_results() -> dict[str, Any]:
    if not shutil.which("node") or not (ROOT / "packages/xy-node/node_modules/koffi").exists():
        pytest.skip("Node/koffi unavailable")
    process = subprocess.run(
        [
            "node",
            str(ROOT / "packages/xy-node/scripts/static_chrome_style_cross_host.mjs"),
            "--frames",
        ],
        input=json.dumps({k: base64.b64encode(v).decode() for k, v in FRAMES.items()}),
        text=True,
        capture_output=True,
        timeout=300,
        cwd=ROOT,
        env={**os.environ, "XYG_NATIVE_LIB": str(_native._lib._name)},
    )
    assert process.returncode == 0, process.stdout + process.stderr
    return json.loads(process.stdout)


@pytest.mark.parametrize("name", sorted(CASES))
@pytest.mark.parametrize("fmt", FORMATS)
def test_hosts_export_identical_bytes(name: str, fmt: str, node_results: dict[str, Any]) -> None:
    expected = node_results["cases"][name][fmt]
    options = {"quality": 90} if fmt == "jpeg" else {}
    data = CASES[name].to_image(fmt, scale=1, **options)
    if fmt == "svg":
        assert data.decode() == expected["text"]
    else:
        assert hashlib.sha256(data).hexdigest() == expected["sha256"]


def test_authored_styles_change_every_format(node_results: dict[str, Any]) -> None:
    for fmt in FORMATS:
        base = node_results["cases"]["default"][fmt]
        for name in ("tick_30", "typography", "precedence"):
            assert node_results["cases"][name][fmt] != base, (name, fmt)


@pytest.mark.parametrize("name", sorted(FAILURES))
def test_hosts_reject_with_the_same_stable_reason(name: str, node_results: dict[str, Any]) -> None:
    styles, reason = FAILURES[name]
    with pytest.raises(Exception, match=reason):
        _chart(styles).to_svg()
    assert reason in node_results["failures"][name]


@pytest.mark.parametrize("name", sorted(FRAMES))
def test_raw_frames_resolve_identically(name: str, node_results: dict[str, Any]) -> None:
    node = node_results["frames"][name]
    try:
        python = _native.static_chrome_style(FRAMES[name])
    except Exception as error:
        assert "error" in node, name
        assert str(error) == node["error"] or str(error) in node["error"]
        return
    assert base64.b64decode(node["output"]) == python


def test_hosts_carry_no_chrome_style_policy() -> None:
    """The duplicated admission/precedence tables are deleted from the hosts."""
    banned = (
        "XYG_STATIC_UNSUPPORTED_CHROME_STYLE",
        "XYG_STATIC_UNSUPPORTED_BROWSER_CSS",
        "XYG_STATIC_UNSUPPORTED_CUSTOM_FONT",
        '"tick_padding"',
        '"tick_label_size"',
    )
    # pyplot's document-level suptitle keeps its own (separate) font admission.
    title_only = ("XYG_STATIC_UNSUPPORTED_TITLE_STYLE", "dejavusans")
    hosts = (
        "python/xyg/_static_document.py",
        "python/xyg/pyplot/_grid.py",
        "python/xyg/_facets_grid.py",
        "packages/xy-node/src/scene.js",
    )
    for host in hosts:
        source = (ROOT / host).read_text()
        for token in banned + (() if host.endswith("_grid.py") else title_only):
            assert token not in source, f"{host} still carries chrome-style policy {token!r}"
