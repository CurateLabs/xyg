"""#1006: Matplotlib ``ax.table`` in native static export (corpus case 53).

Each table cell is one public boxed text annotation: its anchor is authored in
axes-fraction coordinates (Rust projects it against the panel's final plot
rectangle, XYAW byte 62) and its rectangle is an explicit label box (an XYAO v3
label-table entry Rust applies after Scene decoding). SVG, PNG, and PDF come
from the Rust StaticDocument consumer; there is no host renderer.

The pinned geometry is Matplotlib 3.11 (Agg, dpi 100) ``Cell.get_window_extent``
converted to top-left pixels; ``test_pinned_reference_matches_live_matplotlib``
recomputes it when the reference interpreter is available (the Matplotlib 3.11
CI job).
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zlib
from typing import Any

import numpy as np
import pytest

import xyg.pyplot as plt
from xyg import _native
from xyg import _static_document as sd

CELL_TEXT = [["north", "12"], ["south", "18"]]
COL_LABELS = ["region", "value"]
CELL_COLOURS = [["#dbeafe", "#dbeafe"], ["#dcfce7", "#dcfce7"]]
CANVAS = (640.0, 480.0)

# (left, top, right, bottom) px in a 640x480 canvas.
REFERENCE: dict[str, dict[str, Any]] = {
    "default": {
        "axes": (80.0, 57.6, 576.0, 427.2),
        "cells": {
            "region": (80.0, 427.2, 328.0, 443.87),
            "value": (328.0, 427.2, 576.0, 443.87),
            "north": (80.0, 443.87, 328.0, 460.53),
            "12": (328.0, 443.87, 576.0, 460.53),
            "south": (80.0, 460.53, 328.0, 477.2),
            "18": (328.0, 460.53, 576.0, 477.2),
        },
    },
    "tight": {
        "axes": (46.72, 15.0, 625.0, 415.0),
        "cells": {
            "region": (46.72, 415.0, 335.86, 433.04),
            "value": (335.86, 415.0, 625.0, 433.04),
            "north": (46.72, 433.04, 335.86, 451.08),
            "12": (335.86, 433.04, 625.0, 451.08),
            "south": (46.72, 451.08, 335.86, 469.11),
            "18": (335.86, 451.08, 625.0, 469.11),
        },
    },
    "bbox": {
        "axes": (80.0, 57.6, 576.0, 427.2),
        "cells": {
            "x": (129.6, 242.4, 253.6, 297.84),
            "y": (253.6, 242.4, 377.6, 297.84),
            "z": (377.6, 242.4, 501.6, 297.84),
            "a": (129.6, 297.84, 253.6, 353.28),
            "b": (253.6, 297.84, 377.6, 353.28),
            "c": (377.6, 297.84, 501.6, 353.28),
        },
    },
}


def _figure(case: str, module: Any = plt) -> tuple[Any, Any, Any]:
    fig, ax = module.subplots(figsize=(6.4, 4.8))
    ax.plot([0, 1], [0, 1])
    if case == "bbox":
        table = ax.table(
            cellText=[["a", "b", "c"]],
            colLabels=["x", "y", "z"],
            cellLoc="left",
            bbox=(0.1, 0.2, 0.75, 0.3),
        )
    else:
        table = ax.table(cellText=CELL_TEXT, colLabels=COL_LABELS, cellColours=CELL_COLOURS)
    if case == "tight":
        fig.tight_layout()
    return fig, ax, table


def _export(fig: Any, fmt: str, monkeypatch: pytest.MonkeyPatch) -> tuple[bytes, list[str]]:
    calls: list[str] = []
    native = _native.static_document_export

    def observe(document: bytes, format: str, **kwargs: Any) -> bytes:
        calls.append(format)
        return native(document, format, **kwargs)

    monkeypatch.setattr(_native, "static_document_export", observe)
    buffer = io.BytesIO()
    fig.savefig(buffer, format=fmt)
    return buffer.getvalue(), calls


def _svg_geometry(svg: bytes) -> tuple[tuple[float, ...], dict[str, tuple[float, ...]], dict]:
    """Canvas-space plot rectangle, cell boxes by text, and cell text anchors."""
    root = ET.fromstring(svg)
    panel = next(node for node in root.iter() if "data-xy-static-panel" in node.attrib)
    ox, oy = float(panel.attrib["x"]), float(panel.attrib["y"])
    clip = next(node for node in panel.iter() if node.tag.endswith("clipPath"))
    rect = next(iter(clip))
    x, y, w, h = (float(rect.attrib[key]) for key in ("x", "y", "width", "height"))
    x, y = x + ox, y + oy
    nodes = list(panel.iter())
    cells: dict[str, tuple[float, ...]] = {}
    texts: dict[str, tuple[float, str]] = {}
    for index, node in enumerate(nodes):
        if node.attrib.get("data-xy-slot") != "annotation_label_box":
            continue
        label = nodes[index + 1]
        assert label.tag.endswith("text"), "each cell box is followed by its text"
        bx, by, bw, bh = (float(node.attrib[key]) for key in ("x", "y", "width", "height"))
        bx, by = bx + ox, by + oy
        cells[label.text or ""] = (bx, by, bx + bw, by + bh)
        texts[label.text or ""] = (
            float(label.attrib["x"]) + ox,
            label.attrib.get("text-anchor", "start"),
        )
    return (x, y, x + w, y + h), cells, texts


def _pdf_content(pdf: bytes) -> bytes:
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


@pytest.mark.parametrize("case", ["default", "tight"])
def test_bottom_table_exports_svg_png_pdf_natively(
    case: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    fig, _ax, _table = _figure(case)
    svg, calls = _export(fig, "svg", monkeypatch)
    assert calls == ["svg"], "pyplot SVG must come from the Rust StaticDocument"
    plot, cells, _texts = _svg_geometry(svg)
    labels = [*COL_LABELS, *(value for row in CELL_TEXT for value in row)]
    assert sorted(cells) == sorted(labels), "every cell text is drawn with its box"
    for left, top, right, bottom in cells.values():
        assert 0.0 <= left < right <= CANVAS[0] and 0.0 <= top < bottom <= CANVAS[1]
    # loc="bottom": the header row starts at the axes bottom; rows tile down
    # the plot width without gaps.
    assert cells["region"][1] == pytest.approx(plot[3], abs=0.02)
    assert cells["region"][0] == pytest.approx(plot[0], abs=0.02)
    assert cells["value"][2] == pytest.approx(plot[2], abs=0.02)
    assert cells["region"][3] == pytest.approx(cells["north"][1], abs=0.02)
    assert cells["north"][3] == pytest.approx(cells["south"][1], abs=0.02)
    assert cells["region"][2] == pytest.approx(cells["value"][0], abs=0.02)
    assert b'fill="rgba(219,234,254,1.000000)"' in svg or b'fill="rgb(219,234,254)"' in svg
    assert b'fill="rgba(220,252,231,1.000000)"' in svg or b'fill="rgb(220,252,231)"' in svg

    png, calls = _export(fig, "png", monkeypatch)
    assert calls == ["png"]
    image = plt.imread(io.BytesIO(png))
    assert image.shape[:2] == (480, 640)
    rgb = np.asarray(image)[..., :3].astype(int)
    if np.asarray(image).dtype.kind == "f":
        rgb = np.round(np.asarray(image)[..., :3] * 255).astype(int)
    for name, color in (("north", (219, 234, 254)), ("south", (220, 252, 231))):
        left, top, right, bottom = cells[name]
        # A cell-interior pixel away from its right-aligned text (and from
        # the x tick labels the table covers) paints the face color.
        sample = rgb[int((top + bottom) / 2), int(left + 0.3 * (right - left))]
        assert tuple(sample) == pytest.approx(color, abs=2), name

    # The same Rust StaticDocument (captured from the native export) lowers
    # to PDF in Rust; every cell text stays searchable.
    documents: list[bytes] = []
    native = _native.static_document_export

    def capture(document: bytes, format: str, **kwargs: Any) -> bytes:
        documents.append(document)
        return native(document, format, **kwargs)

    monkeypatch.setattr(_native, "static_document_export", capture)
    fig.savefig(io.BytesIO(), format="svg")
    pdf = native(documents[-1], "pdf")
    assert pdf.startswith(b"%PDF-")
    content = _pdf_content(pdf)
    for label in labels:
        assert f"({label})".encode() in content
    # Cell rectangles are painted in the PDF too (filled face colors).
    assert (
        b"0.859 0.918 0.996 rg" in content
        or b"0.8588 0.9176 0.9961 rg" in content
        or (re.search(rb"0\.85\d* 0\.91\d* 0\.99\d* rg", content))
    )


@pytest.mark.parametrize("case", ["default", "bbox"])
def test_cell_rectangles_match_matplotlib(case: str, monkeypatch: pytest.MonkeyPatch) -> None:
    fig, _ax, _table = _figure(case)
    svg, _calls = _export(fig, "svg", monkeypatch)
    plot, cells, _texts = _svg_geometry(svg)
    reference = REFERENCE[case]
    assert plot == pytest.approx(reference["axes"], abs=0.05)
    assert sorted(cells) == sorted(reference["cells"])
    for name, expected in reference["cells"].items():
        assert cells[name] == pytest.approx(expected, abs=0.05), name
    if case == "bbox":
        # bbox= places the table inside the axes rectangle.
        for left, top, right, bottom in cells.values():
            assert plot[0] <= left and right <= plot[2] and plot[1] <= top and bottom <= plot[3]
    else:
        # loc="bottom" places the whole table below the axes.
        assert min(top for _left, top, _right, _bottom in cells.values()) >= plot[3] - 0.01


def test_cell_text_uses_matplotlib_cell_pad_alignment(monkeypatch: pytest.MonkeyPatch) -> None:
    fig, _ax, _table = _figure("default")
    svg, _calls = _export(fig, "svg", monkeypatch)
    _plot, cells, texts = _svg_geometry(svg)
    for name in ("north", "12"):  # cellLoc="right": 10% Cell.PAD inside the right edge
        left, _top, right, _bottom = cells[name]
        assert texts[name] == (pytest.approx(right - 0.1 * (right - left), abs=0.01), "end")
    for name in ("region", "value"):  # colLoc="center"
        left, _top, right, _bottom = cells[name]
        assert texts[name] == (pytest.approx((left + right) / 2, abs=0.01), "middle")

    fig, _ax, _table = _figure("bbox")
    svg, _calls = _export(fig, "svg", monkeypatch)
    _plot, cells, texts = _svg_geometry(svg)
    for name in ("a", "b", "c"):  # cellLoc="left"
        left, _top, right, _bottom = cells[name]
        assert texts[name][0] == pytest.approx(left + 0.1 * (right - left), abs=0.01)
        assert texts[name][1] == "start"


def test_tight_layout_table_hangs_from_axes_like_matplotlib(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """tight_layout differs between engines, so compare axes-relative boxes."""
    fig, _ax, _table = _figure("tight")
    svg, _calls = _export(fig, "svg", monkeypatch)
    plot, cells, _texts = _svg_geometry(svg)
    reference = REFERENCE["tight"]
    ref_left, _ref_top, ref_right, ref_bottom = reference["axes"]
    for name, (left, top, right, bottom) in reference["cells"].items():
        expected_x = (
            (left - ref_left) / (ref_right - ref_left),
            (right - ref_left) / (ref_right - ref_left),
        )
        actual = cells[name]
        width = plot[2] - plot[0]
        assert ((actual[0] - plot[0]) / width, (actual[2] - plot[0]) / width) == pytest.approx(
            expected_x, abs=1e-3
        )
        # Matplotlib rescales its axes-fraction rows with the post-layout axes
        # height; xyg keeps the pre-layout 12 pt row, within a few pixels.
        assert actual[1] - plot[3] == pytest.approx(top - ref_bottom, abs=3.5), name
        assert actual[3] - plot[3] == pytest.approx(bottom - ref_bottom, abs=4.5), name
    assert max(bottom for *_rest, bottom in cells.values()) <= CANVAS[1]


def test_tall_bottom_table_stays_inside_the_canvas(monkeypatch: pytest.MonkeyPatch) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    ax.bar([0, 1, 2], [3, 1, 2])
    rows = [[f"r{row}c{col}" for col in range(4)] for row in range(8)]
    ax.table(cellText=rows, colLabels=[f"h{col}" for col in range(4)], rowLabels=list("ABCDEFGH"))
    fig.tight_layout()
    svg, _calls = _export(fig, "svg", monkeypatch)
    plot, cells, _texts = _svg_geometry(svg)
    assert len(cells) == 4 + 8 * 4 + 8
    for left, top, right, bottom in cells.values():
        assert left >= 0.0 and right <= CANVAS[0] and top >= plot[3] - 0.01 and bottom <= CANVAS[1]
    # Row labels sit left of the table body, outside the axes.
    assert cells["A"][2] == pytest.approx(plot[0], abs=0.01)


@pytest.mark.parametrize("tight", [False, True])
def test_long_row_labels_reserve_left_room_on_the_canvas(
    tight: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Row labels hang left of the axes; the layout keeps them on the canvas."""
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    ax.table(cellText=[["1", "2"]], rowLabels=["a very long row label here"], colLabels=["x", "y"])
    if tight:
        fig.tight_layout()
    svg, _calls = _export(fig, "svg", monkeypatch)
    plot, cells, _texts = _svg_geometry(svg)
    label = cells["a very long row label here"]
    assert label[0] >= 0.0 and label[2] == pytest.approx(plot[0], abs=0.02)
    # The body still tiles the plot width exactly from the axes' left edge.
    assert cells["x"][0] == pytest.approx(plot[0], abs=0.02)
    assert cells["y"][2] == pytest.approx(plot[2], abs=0.02)
    assert cells["1"][0] == pytest.approx(plot[0], abs=0.02)


def test_empty_cells_keep_their_rectangles(monkeypatch: pytest.MonkeyPatch) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    ax.table(cellText=[["kept", ""]], cellColours=[["#fee2e2", "#dcfce7"]])
    svg, _calls = _export(fig, "svg", monkeypatch)
    _plot, cells, _texts = _svg_geometry(svg)
    assert sorted(cells) == [" ", "kept"]
    assert b"220,252,231" in svg


def test_axes_fraction_text_exports_beside_a_table(monkeypatch: pytest.MonkeyPatch) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    ax.table(cellText=[["a", "b"]])
    ax.text(0.02, 0.95, "(a)", transform=ax.transAxes)
    svg, _calls = _export(fig, "svg", monkeypatch)
    plot, _cells, _texts = _svg_geometry(svg)
    panel = next(
        node for node in ET.fromstring(svg).iter() if "data-xy-static-panel" in node.attrib
    )
    label = next(node for node in panel.iter() if node.tag.endswith("text") and node.text == "(a)")
    x = float(label.attrib["x"]) + float(panel.attrib["x"])
    y = float(label.attrib["y"]) + float(panel.attrib["y"])
    assert x == pytest.approx(plot[0] + 0.02 * (plot[2] - plot[0]), abs=0.02)
    assert y == pytest.approx(plot[3] - 0.95 * (plot[3] - plot[1]), abs=0.02)


def test_mixed_annotations_beside_a_table_export(monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-label facts (#1033): cells, a callout, and plain text coexist."""
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    ax.plot([0, 1], [0, 1])
    ax.table(cellText=[["a", "b"]])
    ax.annotate("tip", xy=(0.5, 0.5), xytext=(10, 10), textcoords="offset points")
    ax.text(0.2, 0.8, "big", fontsize=18)
    svg, calls = _export(fig, "svg", monkeypatch)
    assert calls == ["svg"]
    text = "".join(ET.fromstring(svg).itertext())
    assert all(word in text for word in ("a", "b", "tip", "big"))


def test_table_limits_fail_closed_with_stable_reasons() -> None:
    # 13 x 10 cells plus 10 headers exceed the 128-annotation panel bound.
    fig, ax = plt.subplots(figsize=(6.4, 9))
    ax.table(
        cellText=[[str(row * 10 + col) for col in range(10)] for row in range(13)],
        colLabels=[f"c{col}" for col in range(10)],
    )
    with pytest.raises(ValueError, match="XYG_STATIC_ANNOTATION_STYLE_LIMIT"):
        fig.savefig(io.BytesIO(), format="svg")

    # A cell Rust would place partly off the canvas is never clipped or moved
    # silently: the label-table application rejects the panel ...
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    ax.table(cellText=[["a", "b"]], bbox=(0.0, -0.15, 1.0, 0.3))
    with pytest.raises(_native.StaticDocumentRejected, match="XYG_STATIC_DOCUMENT_PANEL"):
        fig.savefig(io.BytesIO(), format="svg")
    # ... and a cell whose text itself is off the canvas fails the canonical
    # Scene's label bound first.
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    ax.table(cellText=[["a", "b"]], bbox=(0.0, -2.0, 1.0, 0.2))
    with pytest.raises(ValueError, match="invalid canonical scene batch"):
        fig.savefig(io.BytesIO(), format="svg")

    # Text in coordinate spaces the Scene does not project fails with one
    # stable reason (never silently placed in data coordinates).
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    ax.plot([0, 1], [0, 1])
    ax.text(0.5, 0.5, "figure", transform=fig.transFigure)
    with pytest.raises(
        sd.UnsupportedStaticExport,
        match="Scene text annotations support coordinate_space 'data' or 'axes_fraction' only",
    ):
        fig.savefig(io.BytesIO(), format="svg")


@pytest.mark.parametrize("loc", ["top", "upper right", "center", "best"])
def test_unsupported_table_locations_fail_loudly(loc: str) -> None:
    _fig, ax = plt.subplots()
    with pytest.raises(NotImplementedError, match=r"does not implement table\(loc=\.\.\.\)"):
        ax.table(cellText=[["a"]], loc=loc)


def _has_matplotlib_311() -> bool:
    try:
        import matplotlib
        from matplotlib.axes import Axes
    except ImportError:
        return False
    version = tuple(int(part) for part in matplotlib.__version__.split(".")[:2])
    return version >= (3, 11) and hasattr(Axes, "grouped_bar")


@pytest.mark.skipif(not _has_matplotlib_311(), reason="requires the Matplotlib 3.11 reference")
@pytest.mark.parametrize("case", sorted(REFERENCE))
def test_pinned_reference_matches_live_matplotlib(case: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as mpl

    fig, ax, table = _figure(case, mpl)
    try:
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        height = fig.bbox.height
        box = ax.bbox
        assert (box.x0, height - box.y1, box.x1, height - box.y0) == pytest.approx(
            REFERENCE[case]["axes"], abs=0.01
        )
        for cell in table.get_celld().values():
            extent = cell.get_window_extent(renderer)
            assert (extent.x0, height - extent.y1, extent.x1, height - extent.y0) == pytest.approx(
                REFERENCE[case]["cells"][cell.get_text().get_text()], abs=0.01
            )
    finally:
        mpl.close(fig)
