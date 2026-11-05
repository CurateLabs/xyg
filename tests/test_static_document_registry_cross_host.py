"""Runtime witnesses for the SAME Rust static-export registry (#875).

Dev before rebase: XYG_STATIC_EXPORT_REGISTRY=/absolute/path/to/generated.json.
There is deliberately no automatic fallback to another worktree.
"""

from __future__ import annotations

import ast
import base64
import io
import json
import os
import re
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path
from typing import Any

import pytest

Image = pytest.importorskip("PIL.Image")  # noqa: E402

import xyg  # noqa: E402
from xyg import _native  # noqa: E402
from xyg import _static_document as sd  # noqa: E402
from xyg._scene_v3 import figure_scene  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = Path(
    os.environ.get(
        "XYG_STATIC_EXPORT_REGISTRY", ROOT / "tests/fixtures/static_export_support_registry.json"
    )
)
DOCUMENT = json.loads(REGISTRY.read_text())["document"]
FORMATS = ("svg", "png", "pdf", "jpeg", "webp")


def _pdf_content(pdf: bytes) -> bytes:
    # Same bounded object/Flate parser contract as test_pdf_export._content;
    # no import of that legacy-renderer test module is needed.
    objects = {
        int(match[1]): match[2]
        for match in re.finditer(rb"(\d+) 0 obj\n(.*?)\nendobj\n", pdf, re.S)
    }
    page = next(body for body in objects.values() if re.search(rb"/Type /Page(?!s)", body))
    reference = re.search(rb"/Contents (\d+) 0 R", page)
    assert reference is not None
    header, _, stream = objects[int(reference[1])].partition(b"stream\n")
    assert b"/FlateDecode" in header
    return zlib.decompress(stream.rsplit(b"\nendstream", 1)[0])


# Literal XYCO facts (title bold, x title italic, y title bold, x tick bold
# italic, y tick italic, four paints), not a host-side renderer.
CHROME_TEXT = (
    2 | (1 << 2) | (2 << 4) | (3 << 6) | (1 << 8) | (0xF << 10),
    ((255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (10, 20, 30, 255)),
)


def _label_entry(
    size: float = 12.0,
    flags: int = 0,
    padding: tuple[float, float] | None = None,
    align: int = 0,
) -> bytes:
    """One per-label annotation entry (the XYAO label-table layout)."""
    pad_x, pad_y = padding or (0.0, 0.0)
    return struct.pack("<I3fBBxx", 1 | (2 if padding else 0), size, pad_x, pad_y, flags, align)


# Literal envelope facts, not a host-side renderer or layout implementation.
OPTIONS: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
    "document_title_x_center": ({}, {}),
    "document_panel_colorbar_log_scale": ({"colorbar_scale": "log"}, {}),
    "document_panel_colorbar_extend_min": ({"colorbar_extend": "min"}, {}),
    "document_panel_colorbar_extend_max": ({"colorbar_extend": "max"}, {}),
    "document_panel_colorbar_pyplot_label": ({"colorbar_pyplot_label": True}, {}),
    "document_colorbar_extend_both": ({"colorbar_extend": "both"}, {}),
    "document_annotation_baseline": ({"annotation_labels": _label_entry(align=0)}, {}),
    "document_annotation_top": ({"annotation_labels": _label_entry(align=1)}, {}),
    "document_annotation_bottom": ({"annotation_labels": _label_entry(align=2)}, {}),
    "document_annotation_center": ({"annotation_labels": _label_entry(align=3)}, {}),
    "document_axis_sides_none": ({"axis_sides": (0, 0)}, {}),
    "document_axis_sides_low": ({"axis_sides": (1, 1)}, {}),
    "document_axis_sides_high": ({"axis_sides": (2, 2)}, {}),
    "document_axis_sides_both": ({"axis_sides": (3, 3)}, {}),
    "document_grid_dash": ({"grid_dash": (1, 0, 0, 2)}, {}),
    "document_chrome_text": ({"chrome_text": CHROME_TEXT}, {}),
    "document_colorbar_fill_plot": ({"colorbar_fill_plot": True}, {}),
    "document_colorbar_discrete": (
        {
            "colorbar_pyplot_label": True,
            "colorbar_discrete": (True, ("one", "ten", "hundred"), None, None),
        },
        {},
    ),
    "document_colorbar_discrete_extend": (
        {
            "colorbar_pyplot_label": True,
            "colorbar_extend": "both",
            "colorbar_discrete": (False, (), (68, 1, 84, 255), (253, 231, 37, 255)),
        },
        {},
    ),
    "document_defaults": ({}, {}),
    "document_authored_frame": ({}, {}),
    "document_polar_annulus": ({}, {}),
    "document_scatter_colormap_alpha": ({}, {}),
    "document_background": ({}, {"background": "#ddeeff80"}),
    "document_optimized_png": ({}, {"optimize_png": True}),
    "document_tight_crop": ({}, {"tight_crop": True, "crop_padding": 3}),
    "document_panel_chrome": ({"chrome_metrics": (14, 16, 6, 13, 15, 5), "axis_sides": (3, 3)}, {}),
    "document_annotation_style": (
        {
            "annotation_labels": _label_entry(size=15.0, flags=3, padding=(5.0, 5.0), align=3),
            "arrow_metrics": (9, 2, 2),
        },
        {},
    ),
    "document_panel_title": ({"title_style": (18, "#654321")}, {}),
    "document_title_start": ({}, {"title_anchor": 0, "title_flags": 0}),
    "document_title_middle": ({}, {"title_anchor": 1, "title_flags": 1}),
    "document_title_end": ({}, {"title_anchor": 2, "title_flags": 2}),
    "document_title_bold_italic": ({}, {"title_flags": 3}),
    "document_labels_start_top": ({}, {}),
    "document_labels_middle_center": ({}, {}),
    "document_labels_end_bottom": ({}, {}),
    "document_labels_baseline_rotated": ({}, {}),
    "document_legend": ({}, {}),
    "document_legend_relabel": ({}, {}),
    "document_legend_frameless": ({}, {}),
    "document_signed_panels": ({}, {}),
    "document_overlap": ({}, {}),
    "document_overlap_red_blue": ({}, {"background": "white"}),
    "document_overlap_blue_red": ({}, {"background": "white"}),
    "document_colorbar_vertical": ({"colorbar_layout": (0.75, 0.5, 0.5)}, {}),
    "document_colorbar_horizontal": ({}, {}),
    "document_shared_colorbar": ({}, {"colorbar": "viridis"}),
    "document_half_scale": ({}, {}),
    "document_double_scale": ({}, {}),
    "document_jpeg_quality_low": ({}, {}),
    "document_jpeg_quality_high": ({}, {}),
}


def _scene(name: str) -> bytes:
    if name == "document_polar_annulus":
        return figure_scene(
            xyg.polar_chart(
                xyg.bar([30, 70], [3, 5], width=8, color="#ef4444", opacity=1),
                xyg.line([0, 180], [5, 5], color="#00cc88", width=9),
                xyg.theta_axis(unit="degrees", label="Time"),
                xyg.r_axis(hole=0.3, domain=(0, 5), label="Value"),
                xyg.legend(show=False),
                width=320,
                height=240,
                title="Panel",
            ).figure()
        )
    colorbar = "colorbar" in name and name != "document_shared_colorbar"
    children: list[xyg.Mark | xyg.Colorbar | xyg.Annotation] = (
        [xyg.scatter([0, 1, 2], [1, 3, 2], color=[1.0, 10.0, 100.0], color_domain=(1, 100), size=6)]
        if colorbar
        else [xyg.line([0, 1, 2], [1, 3, 2], color="#ef4444", width=2)]
    )
    if name == "document_scatter_colormap_alpha":
        children = [
            xyg.scatter(
                [0, 1, 2],
                [1, 3, 2],
                color=[0, 0.5, 1],
                color_domain=(0, 1),
                size=10,
                opacity=0.4,
                stroke_width=2,
            )
        ]
    if name.startswith("overlap_paint_"):
        color = "#ff000080" if name.endswith("red") else "#0000ff80"
        children = [xyg.bar([1], [4], width=2, color=color, opacity=1.0)]
    if colorbar:
        children.append(
            xyg.colorbar(
                title="Intensity",
                orientation="horizontal" if name.endswith("horizontal") else "vertical",
                ticks=[1, 10, 100],
            )
        )
    if "annotation" in name:
        children.extend(
            [
                xyg.text(
                    1,
                    3,
                    "note < & >",
                    dx=0,
                    dy=-6,
                    color="#654321",
                    style={"label_background": "#ffffff"},
                ),
                xyg.arrow(0.5, 1, 1.5, 2, color="#667085", width=1.5),
            ]
        )
    chart = xyg.chart(
        *children,
        xyg.x_axis(domain=(0, 2), label="Time"),
        xyg.y_axis(domain=(0, 4), label="Value"),
        xyg.legend(show=False),
        width=320,
        height=240,
        title="Panel",
    )
    return figure_scene(
        chart.figure(), margins=(46, 8, 32, 36) if name == "document_authored_frame" else None
    )


def _labels(name: str) -> list[dict]:
    anchor, vertical = {
        "document_labels_start_top": ("start", "top"),
        "document_labels_middle_center": ("middle", "center"),
        "document_labels_end_bottom": ("end", "bottom"),
        "document_labels_baseline_rotated": ("middle", "baseline"),
    }[name]
    return [
        {
            "text": "Label < & >",
            "x": 0.5,
            "y": 0.5,
            "size": 14,
            "color": "#654321",
            "anchor": anchor,
            "vertical_align": vertical,
            "rotation": 90 if name.endswith("rotated") else 0,
            "opacity": 0.6,
            "font_style": "italic",
            "weight": "bold",
        }
    ]


def _legend() -> dict:
    return {
        "loc": "upper right",
        "anchor": (0.9, 0.9),
        "ncols": 2,
        "title": "Kinds",
        "items": [
            {"name": "line", "kind": "line", "style": {"color": "#123456", "dash": True}},
            {"name": "scatter", "kind": "scatter", "style": {"color": "#654321", "size": 7}},
            {"name": "patch", "kind": "bar", "style": {"color": "#22aa44"}},
        ],
    }


def _build(name: str) -> tuple[bytes, list[bytes], float, int]:
    if name in {"document_legend_relabel", "document_legend_frameless"}:
        figure = xyg.chart(
            xyg.line([0, 1, 2], [1, 3, 2], name="Original", color="#ef4444", width=2),
            xyg.x_axis(domain=(0, 2), label="Time"),
            xyg.y_axis(domain=(0, 4), label="Value"),
            width=320,
            height=240,
            title="Panel",
        ).figure()
        figure.legend_options = {
            "items": [
                {"kind": "line", "name": "Relabelled", "style": {"color": "#ef4444", "width": 2}}
            ]
        }
        if name.endswith("frameless"):
            figure.legend_options["style"] = {
                "background": "transparent",
                "borderColor": "transparent",
            }
        document = sd.figure_document(figure, width=320, height=240)
        start = (
            64
            + 128
            + sum(struct.unpack_from("<I", document, offset)[0] for offset in (24, 52, 60, 164))
        )
        offset, length = struct.unpack_from("<2I", document, 80)
        return document, [document[start + offset : start + offset + length]], 1.0, 90
    panel, document = OPTIONS[name]
    document = dict(document)
    if name.startswith("document_title_"):
        document.update(title="Document < & >", title_x=160, title_y=20)
    if name == "document_title_x_center":
        document.pop("title_x")
    if name.startswith("document_labels_"):
        document["labels"] = _labels(name)
    if name == "document_legend":
        document["legend"] = _legend()
    scene = _scene(name)
    panels = [sd.Panel(scene, 0, 0, 320, 240, **panel)]
    if name in {"document_signed_panels", "document_overlap"}:
        panels = [
            sd.Panel(scene, -5, 0, 320, 240),
            sd.Panel(scene, 150 if name.endswith("overlap") else 320, 10, 320, 240),
        ]
    if name == "document_polar_annulus":
        panels = [sd.Panel(scene, 0, 0, 320, 240), sd.Panel(scene, 320, 0, 320, 240)]
    if name.startswith("document_overlap_"):
        colors = name.removeprefix("document_overlap_").split("_")
        panels = [
            sd.Panel(_scene("overlap_paint_" + color), index * 150, 0, 320, 240)
            for index, color in enumerate(colors)
        ]
    width, height = (640, 260) if len(panels) == 2 else (320, 240)
    if name == "document_title_x_center":
        width = 321
    scale = (
        0.5 if name == "document_half_scale" else 2.0 if name == "document_double_scale" else 1.0
    )
    quality = (
        1
        if name == "document_jpeg_quality_low"
        else 100
        if name == "document_jpeg_quality_high"
        else 90
    )
    return (
        sd.encode(panels, width=width, height=height, **document),
        [panel.scene for panel in panels],
        scale,
        quality,
    )


REJECTIONS = {
    "header_truncated",
    "version_unknown",
    "version_legacy_layout",
    "header_flags_unknown",
    "header_label_table_len_invalid",
    "panels_empty",
    "dimensions_zero",
    "panel_flags_unknown",
    "panel_retired_annotation_text_flags",
    "panel_retired_annotation_padding",
    "panel_retired_annotation_vertical_align",
    "panel_label_table_empty_present",
    "panel_inactive_nonzero",
    "panel_ranges_overlap",
    "panel_scene_corrupt",
    "title_invalid_utf8",
    "title_nul",
    "centered_title_x_nonzero",
    "title_anchor_unknown",
    "text_flags_unknown",
    "label_alignment_unknown",
    "label_opacity_invalid",
    "legend_kind_unknown",
    "legend_reserved_nonzero",
    "decoration_trailing_bytes",
    "document_trailing_bytes",
}


def _reject(name: str) -> bytes:
    seed = (
        "document_signed_panels"
        if name == "panel_ranges_overlap"
        else "document_title_start"
        if name.startswith("title_")
        else "document_labels_start_top"
        if name.startswith("label_") or name == "decoration_trailing_bytes"
        else "document_legend"
        if name.startswith("legend_")
        else "document_annotation_baseline"
        if name == "panel_label_table_empty_present"
        else "document_defaults"
    )
    data = bytearray(_build(seed)[0])
    count, title_len = struct.unpack_from("<2I", data, 20)
    decorations = 64 + count * 128 + title_len
    scene_at = decorations + struct.unpack_from("<I", data, 52)[0]
    if name == "header_truncated":
        return bytes(data[:63])
    offsets = {
        "version_unknown": (4, 99),
        "version_legacy_layout": (4, 1),
        "header_flags_unknown": (16, 16),
        "header_label_table_len_invalid": (60, 1),
        "panels_empty": (20, 0),
        "dimensions_zero": (8, 0),
        "panel_flags_unknown": (88, 1 << 16),
        # XYST v2's uniform annotation flags/padding/alignment are retired.
        "panel_retired_annotation_text_flags": (88, 1 << 6),
        "panel_retired_annotation_padding": (88, 1 << 7),
        "panel_retired_annotation_vertical_align": (88, 1 << 9),
        "panel_inactive_nonzero": (96, 1),
        "panel_ranges_overlap": (64 + 128 + 16, 0),
    }
    if name in offsets:
        struct.pack_into("<I", data, *offsets[name])
    elif name == "panel_label_table_empty_present":
        # Panel flag 3 with an explicitly empty table over a Scene that has an
        # annotation label: the flag demands exact label coverage.
        table_len = struct.unpack_from("<I", data, 60)[0]
        assert table_len == 20
        del data[scene_at : scene_at + table_len]
        struct.pack_into("<I", data, 60, 0)
        struct.pack_into("<I", data, 64 + 28, 0)
        struct.pack_into("<I", data, 64 + 84, 0)
    elif name == "centered_title_x_nonzero":
        struct.pack_into("<I", data, 16, struct.unpack_from("<I", data, 16)[0] | 8)
        struct.pack_into("<f", data, 40, 1)
    elif name == "panel_scene_corrupt":
        data[scene_at] = 0
    elif name in {"title_invalid_utf8", "title_nul"}:
        data[64 + count * 128] = 255 if name.endswith("utf8") else 0
    elif name == "title_anchor_unknown":
        data[48] = 3
    elif name == "text_flags_unknown":
        data[49] = 4
    elif name == "label_alignment_unknown":
        data[decorations + 32 + 25] = 4
    elif name == "label_opacity_invalid":
        struct.pack_into("<f", data, decorations + 32 + 16, 2)
    elif name == "legend_reserved_nonzero":
        data[decorations + 32 + 61] = 1
    elif name == "legend_kind_unknown":
        legend_at = decorations + 32
        title_bytes, loc_bytes = struct.unpack_from("<2I", data, legend_at + 4)
        data[legend_at + 64 + title_bytes + loc_bytes] = 3
    elif name == "decoration_trailing_bytes":
        data[scene_at:scene_at] = b"\0"
        struct.pack_into("<I", data, 52, scene_at - decorations + 1)
    elif name == "document_trailing_bytes":
        data.append(0)
    else:
        raise AssertionError(name)
    return bytes(data)


@pytest.fixture(scope="module")
def node_results():
    assert set(OPTIONS) == {row["name"] for row in DOCUMENT["cases"]}
    assert set(DOCUMENT["rejections"]) == REJECTIONS
    assert all(tuple(row["formats"]) == FORMATS for row in DOCUMENT["cases"])
    tree = ast.parse((ROOT / "tests/test_static_document_authored_cross_host.py").read_text())
    authored = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "CASES" for target in node.targets)
    )
    assert set(authored) == {row["name"] for row in DOCUMENT["authored_witnesses"]}
    if not shutil.which("node") or not (ROOT / "packages/xy-node/node_modules/koffi").exists():
        pytest.skip("Node/koffi unavailable")
    process = subprocess.run(
        ["node", str(ROOT / "packages/xy-node/scripts/static_document_registry_cross_host.mjs")],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=180,
        env={
            **os.environ,
            "XYG_NATIVE_LIB": str(_native._lib._name),
            "XYG_STATIC_EXPORT_REGISTRY": str(REGISTRY),
        },
    )
    assert process.returncode == 0, process.stdout + process.stderr
    result = json.loads(process.stdout)
    assert result["authoring"] == "independent-node-public-figure-explicit-xyst"
    assert set(result["cases"]) == set(OPTIONS)
    assert set(result["rejections"]) == REJECTIONS
    return result


@pytest.mark.parametrize("name", OPTIONS)
def test_registered_document_all_consumers(name, node_results):
    node = node_results["cases"][name]
    assert "error" not in node, node.get("error")
    document, scenes, scale, quality = _build(name)
    assert document == base64.b64decode(node["document"])
    if name == "document_title_x_center":
        assert struct.unpack_from("<I", document, 16)[0] & 8
        assert document[40:44] == b"\0" * 4
    assert scenes == [base64.b64decode(value) for value in node["scenes"]]
    assert [_native.scene_raster_commands(scene, scale=1.0) for scene in scenes] == [
        base64.b64decode(value) for value in node["sceneRaster"]
    ]
    for format in FORMATS:
        actual = _native.static_document_export(document, format, scale=scale, quality=quality)
        expected = base64.b64decode(node["outputs"][format])
        assert actual == expected
        if format in {"png", "jpeg", "webp"}:
            with Image.open(io.BytesIO(actual)) as left, Image.open(io.BytesIO(expected)) as right:
                assert (
                    left.format
                    == right.format
                    == {"png": "PNG", "jpeg": "JPEG", "webp": "WEBP"}[format]
                )
                assert left.size == right.size
                assert left.mode == right.mode
                width, height = struct.unpack_from("<2I", document, 8)
                if name == "document_tight_crop":
                    assert 0 < left.width <= width and 0 < left.height <= height
                else:
                    assert left.size == (int(width * scale), int(height * scale))
                rgba = left.convert("RGBA")
                assert rgba.tobytes() == right.convert("RGBA").tobytes()
                if format == "png" and name.startswith("document_overlap_"):
                    # Both 320px-wide panels cover this point. Swapping paint
                    # order must change source-over, never paste/erase a panel.
                    expected = (
                        (127, 63, 191, 255) if name.endswith("red_blue") else (191, 63, 127, 255)
                    )
                    assert rgba.getpixel((250, 100)) == expected
                pixels = rgba.tobytes()
                assert (
                    len(
                        set(
                            zip(pixels[0::4], pixels[1::4], pixels[2::4], pixels[3::4], strict=True)
                        )
                    )
                    > 8
                ), "empty/flat output"
        elif format == "svg":
            root = ET.fromstring(actual)
            assert root.tag.endswith("svg")
            assert "Time" in actual.decode() and "Value" in actual.decode()
            text = "".join(root.itertext())
            if name == "document_authored_frame":
                rect = root.find(".//{*}clipPath/{*}rect")
                assert rect is not None
                assert tuple(float(rect.attrib[key]) for key in ("x", "y", "width", "height")) == (
                    46,
                    32,
                    266,
                    172,
                )
            if name == "document_title_x_center":
                title = next(node for node in root.iter() if node.text == "Document < & >")
                assert float(title.attrib["x"]) == 160.5
            if "annotation" in name:
                assert "note < & >" in text
            if name.startswith("document_title_"):
                assert "Document < & >" in text
            if name.startswith("document_labels_"):
                assert "Label < & >" in text
            if name in {"document_legend_relabel", "document_legend_frameless"}:
                legend = root.find(".//{*}g[@data-xy-static-legend]")
                assert legend is not None and "Relabelled" in "".join(legend.itertext())
                assert "Original" not in "".join(legend.itertext())
                if name.endswith("frameless"):
                    rect = legend.find("{*}rect")
                    assert rect.attrib["fill"] == "rgba(0,0,0,0.000000)"
                    assert rect.attrib["stroke"] == "rgba(0,0,0,0.000000)"
            if name == "document_legend":
                assert all(label in text for label in ("Kinds", "line", "scatter", "patch"))
            if "colorbar" in name and name != "document_shared_colorbar":
                assert "Intensity" in text
            if name == "document_colorbar_extend_both":
                assert b"colorbar_extend_min" in actual and b"colorbar_extend_max" in actual
        else:
            assert actual.startswith(b"%PDF-") and b"%%EOF" in actual[-128:]
            content = _pdf_content(actual)
            assert b"BT" in content and b"ET" in content
            expected = None
            if name == "document_title_middle":
                expected = (b"Helvetica-Oblique", b"Document < & >")
            elif name == "document_title_bold_italic":
                expected = (b"Helvetica-BoldOblique", b"Document < & >")
            elif name == "document_annotation_style":
                expected = (b"Helvetica-BoldOblique", b"note < & >")
            elif name.startswith("document_labels_"):
                expected = (b"Helvetica-BoldOblique", b"Label < & >")
            if expected is not None:
                font, text = expected
                assert b"/BaseFont /" + font + b" /Encoding /WinAnsiEncoding" in actual
                assert text in content, "styled PDF text must remain searchable"


@pytest.mark.parametrize("name", sorted(REJECTIONS))
def test_registered_document_rejections(name, node_results):
    data = _reject(name)
    assert data == base64.b64decode(node_results["rejections"][name]["document"])
    for format in FORMATS:
        with pytest.raises((ValueError, RuntimeError)):
            _native.static_document_export(data, format)
        assert node_results["rejections"][name][format]["rejected"] is True


def test_registered_panel_flag_masks_cover_every_admitted_bit(node_results):
    """Bits 24 (explicit ``cax``) and 25 (discrete colorbar) are admitted and witnessed."""
    registry = DOCUMENT
    flags = {
        row["name"]: row["code"] for row in registry["vocabulary"] if row["family"] == "panel-flag"
    }
    assert flags["panel.colorbar-fill-plot"] == 1 << 24
    assert flags["panel.colorbar-discrete"] == 1 << 25
    mask = 0
    for code in flags.values():
        mask |= code
    assert mask == 0x0300FD3F
    for retired in (1 << 6, 1 << 7, 1 << 9):
        assert not mask & retired
    for source in (
        _build("document_colorbar_fill_plot")[0],
        base64.b64decode(node_results["cases"]["document_colorbar_fill_plot"]["document"]),
    ):
        assert struct.unpack_from("<I", source, 64 + 24)[0] & (1 << 24)
    for source in (
        _build("document_colorbar_discrete")[0],
        base64.b64decode(node_results["cases"]["document_colorbar_discrete"]["document"]),
    ):
        assert struct.unpack_from("<I", source, 64 + 24)[0] & (1 << 25)


def test_annulus_center_crossing_mark_uses_one_compound_clip():
    document, scenes, _, _ = _build("document_polar_annulus")
    svg = ET.fromstring(_native.static_document_export(document, "svg"))
    clips = svg.findall(".//{*}clipPath/{*}path")
    annulus = next(path for path in clips if path.attrib.get("clip-rule") == "evenodd")
    assert annulus.attrib["d"].count("M") == 2
    assert annulus.attrib["d"].count(" A ") == 4
    # A single compound path defines a hole in SVG as well as PDF. Distinct
    # clip children would instead be unioned by SVG, painting this center.
    for clip in svg.findall(".//{*}clipPath"):
        assert not (len(clip) == 2 and all(child.tag.endswith("circle") for child in clip))
    values = list(
        map(float, re.findall(r"[-+]?(?:\d*\.)?\d+(?:[eE][-+]?\d+)?", annulus.attrib["d"]))
    )
    cx, cy, radius = (values[0] + values[7]) / 2, values[1], values[2]
    png = _native.static_document_export(document, "png")
    with Image.open(io.BytesIO(png)) as image:
        rgba = image.convert("RGBA")
        for offset in (0, 320):
            assert rgba.getpixel((round(cx) + offset, round(cy))) == (255, 255, 255, 255)
            assert rgba.getpixel((round(cx + 0.65 * radius) + offset, round(cy))) == (
                0,
                204,
                136,
                255,
            )
    pdf = _native.static_document_export(document, "pdf")
    streams = []
    for payload in re.findall(rb"stream\n(.*?)\nendstream", pdf, re.S):
        try:
            streams.append(zlib.decompress(payload))
        except zlib.error:
            streams.append(payload)
    assert any(b"W*" in stream for stream in streams)
