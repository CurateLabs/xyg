"""Per-annotation label style and box facts, byte-identical across hosts (#1006).

Python authors through the public composition API and Node through the public
``Figure`` API with independent literals. The Rust annotation-style projection
decides every label's size, weight, style, alignment and box padding, and Rust
projects axes-fraction anchors and lays out explicit cell boxes (the pyplot
``table`` vocabulary); the hosts only marshal facts, so all five static formats
must match byte for byte.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

import xyg
from xyg import _native

ROOT = Path(__file__).resolve().parents[1]
FORMATS = ("svg", "png", "pdf", "jpeg", "webp")


def _text(x: float, y: float, value: str, **style: Any) -> xyg.Annotation:
    return xyg.text(x, y, value, dx=0, dy=-6, anchor="start", style=style)


def _chart(*annotations: xyg.Annotation) -> xyg.Chart:
    return xyg.chart(
        xyg.line([0, 1, 2], [1, 3, 2], color="#ef4444", width=2),
        *annotations,
        xyg.x_axis(domain=(0, 2), label="X"),
        xyg.y_axis(domain=(0, 4), label="Y"),
        xyg.legend(show=False),
        width=320,
        height=240,
    )


def _cell(x: float, y: float, value: str, anchor: str, **style: Any) -> xyg.Annotation:
    """One table-style cell: an axes-fraction anchor and an explicit box."""
    return xyg.text(
        x,
        y,
        value,
        dx=style.pop("dx", 0),
        dy=style.pop("dy", 0),
        anchor=anchor,
        style={
            "coordinate_space": "axes_fraction",
            "vertical_align": "center",
            "background": "#dbeafe",
            "border": "1.5px solid #000000",
            **style,
        },
    )


CASES = {
    "mixed_typography": _chart(
        _text(0.2, 1, "Default"),
        _text(0.7, 2, "Large bold", font_size=18, font_weight="bold", label_color="#336699"),
        _text(1.2, 3, "Slanted", font_style="italic", font_size=9, vertical_align="center"),
        _text(1.5, 1.5, "Top", font_weight=700, vertical_align="top", label_color="#aa0000"),
    ),
    "boxes": _chart(
        _text(0.2, 1, "Wide pad", background="#ffffff", border="1px solid #102030", padding="6px"),
        _text(
            0.2, 2, "Tall pad", background="#fff3cd", border="2px solid #664d03", padding="2px 9px"
        ),
        _text(0.2, 3, "Default pad", background="#e0f2fe", font_size=15),
        _text(1.2, 2, "Unboxed", font_size=14),
    ),
    # Matplotlib-table geometry: plot-width percentage columns with a 10%
    # Cell.PAD inset, a px row hanging below the axes, a px row-label column
    # pinned to the left axes edge, and a percentage-height bbox row.
    "table_cells": _chart(
        _cell(
            0.25,
            0,
            "region",
            "middle",
            box_width="50%",
            box_height=16,
            dy=8,
            padding="0px 5%",
            font_size=13,
        ),
        _cell(
            0.95,
            0,
            "value",
            "end",
            box_width="50%",
            box_height=16,
            dy=8,
            padding="0px 5%",
            background="#dcfce7",
        ),
        _cell(0, 0.5, "row", "start", box_width=40, box_height="20%", dx=-36, padding="0px 4px"),
        _cell(
            0.55,
            0.5,
            " ",
            "start",
            box_width="40%",
            box_height="20%",
            padding="0px 4%",
            background="#fee2e2",
        ),
    ),
    "axes_fraction_text": _chart(
        xyg.text(
            0.02,
            0.95,
            "(a)",
            dx=0,
            dy=0,
            anchor="start",
            style={"coordinate_space": "axes_fraction"},
        ),
        xyg.text(
            1,
            0,
            "corner",
            dx=-4,
            dy=-4,
            anchor="end",
            style={"coordinate_space": "axes_fraction", "font_weight": "bold"},
        ),
        _text(1, 2, "data"),
    ),
    "mixed_kinds": _chart(
        _text(0.2, 1, "Default"),
        xyg.hline(3, text="limit", style={"font_size": 9}),
        xyg.callout(1, 2, "peak", style={"font_size": 15, "font_weight": "bold"}),
        _text(1.4, 3.5, "Large", font_size=20, background="#ffffff", padding="4px 8px"),
    ),
}

FAILURES = {
    "round_box": (
        [_text(1, 2, "Round", background="#ffffff", border_radius=5)],
        "XYG_STATIC_UNSUPPORTED_ANNOTATION_BOXSTYLE",
    ),
    "padding_values": (
        [_text(1, 2, "Pad", background="#ffffff", padding="1px 2px 3px")],
        "XYG_STATIC_UNSUPPORTED_ANNOTATION_BBOX",
    ),
    "custom_font": (
        [_text(1, 2, "Font", font_family="Papyrus")],
        "XYG_STATIC_UNSUPPORTED_CUSTOM_FONT",
    ),
    "one_sided_box": (
        [_cell(0.5, 0.5, "cell", "middle", box_width=40)],
        "XYG_STATIC_UNSUPPORTED_ANNOTATION_BBOX",
    ),
    "uncentered_box": (
        [_cell(0.5, 0.5, "cell", "middle", box_width=40, box_height=16, vertical_align="top")],
        "XYG_STATIC_UNSUPPORTED_ANNOTATION_BBOX",
    ),
    "percent_box_in_data_space": (
        [
            _text(
                1,
                2,
                "cell",
                background="#ffffff",
                vertical_align="center",
                box_width="10%",
                box_height=16,
            )
        ],
        "XYG_STATIC_UNSUPPORTED_ANNOTATION_BBOX",
    ),
    "figure_fraction_text": (
        [xyg.text(0.5, 0.5, "fig", style={"coordinate_space": "figure_fraction"})],
        "Scene text annotations support coordinate_space 'data' or 'axes_fraction' only",
    ),
    "cell_off_canvas": (
        [_cell(0.5, 0, "cell", "middle", box_width=40, box_height=160, dy=20)],
        "XYG_STATIC_DOCUMENT_PANEL",
    ),
}


@pytest.fixture(scope="module")
def node_results() -> dict[str, Any]:
    if not shutil.which("node") or not (ROOT / "packages/xy-node/node_modules/koffi").exists():
        pytest.skip("Node/koffi unavailable")
    process = subprocess.run(
        ["node", str(ROOT / "packages/xy-node/scripts/static_annotation_labels_cross_host.mjs")],
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


def _svg_text(svg: str, label: str) -> str:
    match = re.search(rf"<text([^>]*)>{re.escape(label)}</text>", svg)
    assert match, f"{label!r} missing from the SVG"
    return match.group(1)


def test_every_annotation_carries_its_own_style() -> None:
    svg = CASES["mixed_typography"].to_svg()
    default = _svg_text(svg, "Default")
    assert 'font-size="12"' in default and "font-style" not in default
    assert "font-weight" not in default
    large = _svg_text(svg, "Large bold")
    assert 'font-size="18"' in large and 'font-weight="bold"' in large
    assert "rgba(51,102,153," in large
    slanted = _svg_text(svg, "Slanted")
    assert 'font-size="9"' in slanted and 'font-style="italic"' in slanted
    top = _svg_text(svg, "Top")
    assert 'font-weight="bold"' in top and "rgba(170,0,0," in top
    # Alignment is per label: baseline keeps y, top/center move it.
    y = {
        label: float(re.search(r' y="([\d.]+)"', _svg_text(svg, label)).group(1))
        for label in ("Default", "Large bold", "Slanted", "Top")
    }
    assert len(set(y.values())) == 4


def test_label_boxes_use_per_label_padding() -> None:
    svg = CASES["boxes"].to_svg()
    boxes = re.findall(
        r'<rect data-xy-slot="annotation_label_box"[^>]*? width="([\d.]+)" height="([\d.]+)"', svg
    )
    sizes = [(float(w), float(h)) for w, h in boxes]
    # "Wide pad" (6px) and "Tall pad" (2px 9px) and "Default pad" (3px, 15px
    # text) are three distinct boxes; "Unboxed" has none.
    assert len(sizes) == 3 and len(set(sizes)) == 3
    assert 'stroke-width="2"' in svg and 'stroke-width="1"' in svg


def _svg_cells(svg: str) -> dict[str, tuple[float, float, float, float]]:
    found = re.findall(
        r'<rect data-xy-slot="annotation_label_box"[^>]*? x="([-\d.]+)" y="([-\d.]+)" '
        r'width="([\d.]+)" height="([\d.]+)"[^>]*/><text[^>]*>([^<]*)</text>',
        svg,
    )
    return {text: tuple(map(float, box)) for *box, text in found}


def _plot_rect(svg: str) -> tuple[float, float, float, float]:
    match = re.search(
        r'<clipPath[^>]*><rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" '
        r'height="([\d.]+)"',
        svg,
    )
    assert match, "plot clip rectangle missing"
    return tuple(map(float, match.groups()))


def test_table_cells_are_laid_out_by_rust_against_the_plot_rect() -> None:
    svg = CASES["table_cells"].to_svg()
    px, py, pw, ph = _plot_rect(svg)
    cells = _svg_cells(svg)
    # The empty fourth cell keeps its rectangle under a one-space label.
    assert set(cells) == {"region", "value", "row", " "}
    # Percentage widths resolve against the final plot width: the two
    # header cells tile the plot exactly from the left edge.
    region, value = cells["region"], cells["value"]
    assert region[0] == pytest.approx(px, abs=0.01)
    assert region[2] == pytest.approx(0.5 * pw, abs=0.01)
    assert value[0] == pytest.approx(px + 0.5 * pw, abs=0.01)
    assert value[0] + value[2] == pytest.approx(px + pw, abs=0.01)
    # A 16px row hanging below the axes bottom (anchor y=0, dy=8).
    assert region[1] == pytest.approx(py + ph, abs=0.01) and region[3] == 16
    # The px row-label column ends exactly at the plot's left edge.
    row = cells["row"]
    assert row[2] == 40 and row[0] + row[2] == pytest.approx(px, abs=0.01)
    assert row[3] == pytest.approx(0.2 * ph, abs=0.01)


def test_axes_fraction_text_is_projected_against_the_plot_rect() -> None:
    svg = CASES["axes_fraction_text"].to_svg()
    px, py, pw, ph = _plot_rect(svg)
    position = {
        label: tuple(
            float(re.search(rf' {key}="([-\d.]+)"', _svg_text(svg, label)).group(1))
            for key in ("x", "y")
        )
        for label in ("(a)", "corner")
    }
    assert position["(a)"] == pytest.approx((px + 0.02 * pw, py + 0.05 * ph), abs=0.01)
    assert position["corner"] == pytest.approx((px + pw - 4, py + ph - 4), abs=0.01)


@pytest.mark.parametrize("name", sorted(FAILURES))
def test_hosts_reject_with_the_same_stable_reason(name: str, node_results: dict[str, Any]) -> None:
    annotations, reason = FAILURES[name]
    with pytest.raises(Exception, match=reason):
        _chart(*annotations).to_svg()
    assert reason in node_results["failures"][name]
