from __future__ import annotations

import numpy as np
import pytest

import xyg.pyplot as plt


def test_table_is_axes_fraction_geometry_and_does_not_affect_data_limits() -> None:
    fig, ax = plt.subplots()
    ax.bar([10.0, 20.0], [2.0, 3.0])
    limits_before = ax.get_xlim(), ax.get_ylim()

    table = ax.table(
        cellText=[["11.0", "22.0"], ["33.0", "44.0"]],
        rowLabels=["first", "second"],
        rowColours=["#fee2e2", "#dcfce7"],
        colLabels=["A", "B"],
        cellLoc="right",
        rowLoc="left",
        colLoc="center",
    )
    fig.subplots_adjust(bottom=0.2)

    assert (ax.get_xlim(), ax.get_ylim()) == limits_before
    assert sorted(table.get_celld()) == [
        (0, 0),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
        (2, -1),
        (2, 0),
        (2, 1),
    ]
    assert {entry["kind"] for entry in ax._entries[-8:]} == {"@table_cell"}
    assert all(
        entry["kwargs"]["style"]["coordinate_space"] == "axes_fraction"
        for entry in ax._entries[-8:]
    )

    spec, _buffers = ax._build_chart(640, 480).figure().build_payload_split()
    # #1006: one public boxed axes-fraction text annotation per cell; no
    # browser-only class or transparent placeholder box.
    table_annotations = [
        annotation
        for annotation in spec["annotations"]
        if "box_width" in (annotation.get("style") or {})
    ]
    assert len(table_annotations) == 8
    assert not any(annotation.get("class_name") for annotation in table_annotations)
    assert all(
        annotation["style"]["coordinate_space"] == "axes_fraction"
        and annotation["style"]["vertical_align"] == "center"
        for annotation in table_annotations
    )
    assert [annotation["anchor"] for annotation in table_annotations[:2]] == ["middle", "middle"]
    assert {annotation["anchor"] for annotation in table_annotations[2:6]} == {"start", "end"}
    # Body columns are plot-width percentages Rust resolves; the auto-width
    # row-label column is px, pinned to the axes' left edge (x=0) by ``dx``.
    body = [a for a in table_annotations if isinstance(a["style"]["box_width"], str)]
    row_labels = [a for a in table_annotations if not isinstance(a["style"]["box_width"], str)]
    assert {a["style"]["box_width"] for a in body} == {"50.0%"}
    assert [a["text"] for a in row_labels] == ["first", "second"]
    assert all(a["x"] == 0.0 and a["dx"] < 0.0 for a in row_labels)
    # Natural rows hang below the axes bottom (y=0) by positive px offsets.
    assert {annotation["y"] for annotation in table_annotations} == {0.0}
    assert min(annotation["dy"] for annotation in table_annotations) > 0.0
    assert spec["padding"][2] >= ax._table_bottom_points * ax._point_scale()
    assert spec["padding"][3] >= ax._table_left_points * ax._point_scale()

    table.remove()
    assert ax._table_bottom_points == 0.0
    assert ax._table_left_points == 0.0
    assert not any(entry["kind"] == "@table_cell" for entry in ax._entries)


def test_table_default_cells_are_readable_and_bbox_stays_inside_axes() -> None:
    _fig, ax = plt.subplots()
    ax.table(
        cellText=[["left", "center", "right"]],
        cellColours=[["#fee2e2", "#dcfce7", "#dbeafe"]],
        cellLoc="left",
        bbox=(0.1, 0.2, 0.75, 0.3),
        fontsize=9,
    )

    spec, _buffers = ax._build_chart(640, 480).figure().build_payload_split()
    cells = [
        annotation
        for annotation in spec["annotations"]
        if "box_width" in (annotation.get("style") or {})
    ]
    assert [cell["text"] for cell in cells] == ["left", "center", "right"]
    # cellLoc="left": Matplotlib's 10% Cell.PAD inset from each cell's left edge.
    np.testing.assert_allclose([cell["x"] for cell in cells], [0.125, 0.375, 0.625])
    np.testing.assert_allclose([cell["y"] for cell in cells], [0.35, 0.35, 0.35])
    np.testing.assert_allclose([cell["dy"] for cell in cells], [0.0, 0.0, 0.0])
    # bbox= cells are plot-rectangle percentages (Rust resolves them against
    # the final plot rectangle), and so is the Cell.PAD inset.
    np.testing.assert_allclose(
        [float(cell["style"]["box_width"].removesuffix("%")) for cell in cells], [25.0] * 3
    )
    np.testing.assert_allclose(
        [float(cell["style"]["box_height"].removesuffix("%")) for cell in cells], [30.0] * 3
    )
    assert {cell["style"]["padding"] for cell in cells} == {"0px 2.5%"}
    assert [cell["style"]["background"] for cell in cells] == [
        "#fee2e2",
        "#dcfce7",
        "#dbeafe",
    ]
    assert [cell["anchor"] for cell in cells] == ["start", "start", "start"]
    assert ax._table_bottom_points == 0.0


def test_table_remove_recomputes_host_padding_for_twin_axes() -> None:
    _fig, ax = plt.subplots()
    twin = ax.twinx()
    twin_table = twin.table(cellText=[["twin"]])
    host_table = ax.table(cellText=[["host"]])

    host_table.remove()
    assert ax._table_bottom_points > 0.0

    twin_table.remove()
    assert ax._table_bottom_points == 0.0


def test_table_bbox_does_not_mutate_col_widths_array() -> None:
    _fig, ax = plt.subplots()
    col_widths = np.array([1.0, 3.0], dtype=np.float64)

    ax.table(cellText=[["a", "b"]], colWidths=col_widths, bbox=(0.0, 0.0, 1.0, 1.0))

    np.testing.assert_array_equal(col_widths, [1.0, 3.0])


@pytest.mark.parametrize("keyword", ["cellLoc", "rowLoc", "colLoc"])
def test_table_alignment_rejects_unknown_values(keyword: str) -> None:
    _fig, ax = plt.subplots()
    with pytest.raises(ValueError, match=keyword):
        ax.table(cellText=[["a"]], **{keyword: "baseline"})


@pytest.mark.parametrize("edges", ["horizontal", "vertical", "BRTL", "typo"])
def test_table_rejects_unsupported_partial_edges(edges: str) -> None:
    _fig, ax = plt.subplots()

    with pytest.raises(NotImplementedError, match=r"table\(edges=.*closed.*open"):
        ax.table(cellText=[["a"]], edges=edges)
