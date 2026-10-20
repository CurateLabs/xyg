"""Matplotlib 3.11 corpus cases 25 and 53: per-annotation style and bbox (#1006).

Static export used to carry one panel-wide annotation size, weight/style,
alignment and box padding, so a panel mixing ``annotate``, ``text``,
``bar_label``/``pie_label`` and ``bbox=`` boxes failed closed with
``XYG_STATIC_UNSUPPORTED_HETEROGENEOUS_ANNOTATION_STYLE`` /
``..._ANNOTATION_BBOX``. Rust now resolves a per-label table
(``static_annotation_style.rs``); pyplot only marshals matplotlib facts. These
programs are the corpus programs' annotation surface; the arrow head
vocabulary and the empty ``bxp`` fliers are separate Scene gaps, not
annotation style; the table ``axes_fraction`` space is covered by
``test_annotation_coordinate_space_1006.py``.
"""

from __future__ import annotations

import io
import re

import numpy as np
import pytest

import xyg.pyplot as plt
from xyg._static_document import UnsupportedStaticExport


def teardown_function() -> None:
    plt.close("all")


def _svg(fig) -> str:
    out = io.BytesIO()
    fig.savefig(out, format="svg")
    return out.getvalue().decode()


def _labels(svg: str) -> dict[str, dict[str, str]]:
    found = {}
    for match in re.finditer(r"<text([^>]*data-xy-slot=\"graph_label\"[^>]*)>([^<]*)</text>", svg):
        found[match.group(2)] = dict(re.findall(r'([\w-]+)="([^"]*)"', match.group(1)))
    return found


def _boxes(svg: str) -> list[dict[str, str]]:
    return [
        dict(re.findall(r'([\w-]+)="([^"]*)"', match))
        for match in re.findall(r'<rect data-xy-slot="annotation_label_box"([^>]*)/>', svg)
    ]


def test_case_25_annotate_and_text_keep_their_own_size_and_color() -> None:
    x = np.linspace(0, 2 * np.pi, 100)
    fig, ax = plt.subplots()
    ax.plot(x, np.sin(x))
    ax.annotate("peak", xy=(np.pi / 2, 1.0), xytext=(2.5, 1.2))
    ax.text(4.0, -0.5, "trough region", fontsize=9, ha="center", color="tab:gray")

    labels = _labels(_svg(fig))

    assert float(labels["peak"]["font-size"]) == pytest.approx(13.89, abs=0.01)
    assert labels["peak"]["fill"] == "rgba(0,0,0,1.000000)"
    assert float(labels["trough region"]["font-size"]) == 12.5
    assert labels["trough region"]["fill"] == "rgba(127,127,127,1.000000)"


def test_case_25_weight_and_style_are_per_annotation() -> None:
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax.text(0.2, 0.2, "plain")
    ax.text(0.4, 0.4, "heavy", fontweight="bold")
    ax.text(0.6, 0.6, "slanted", fontstyle="italic")

    labels = _labels(_svg(fig))

    assert "font-weight" not in labels["plain"] and "font-style" not in labels["plain"]
    assert labels["heavy"]["font-weight"] == "bold" and "font-style" not in labels["heavy"]
    assert labels["slanted"]["font-style"] == "italic" and "font-weight" not in labels["slanted"]


def test_case_53_bbox_fill_edge_and_pad_are_per_annotation() -> None:
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax.text(
        0.1,
        0.8,
        "wide",
        bbox={"boxstyle": "square,pad=0.6", "fc": "#ffeeaa", "ec": "#664400", "lw": 2},
    )
    ax.text(
        0.6,
        0.3,
        "tight",
        fontsize=14,
        bbox={"boxstyle": "square,pad=0.1", "fc": "#ddeeff", "ec": "none"},
    )

    svg = _svg(fig)
    wide, tight = _boxes(svg)

    assert wide["fill"] == "rgba(255,238,170,1.000000)"
    assert wide["stroke"] == "rgba(102,68,0,1.000000)" and wide["stroke-width"] == "2"
    assert tight["fill"] == "rgba(221,238,255,1.000000)" and "stroke" not in tight
    assert float(wide["width"]) > float(tight["width"]) - 12


def test_case_53_bar_labels_and_a_boxed_note_share_one_panel() -> None:
    fig, ax = plt.subplots()
    grouped = ax.grouped_bar(
        [[2, 4, 3], [3, 2, 5]], tick_labels=["A", "B", "C"], labels=["before", "after"]
    )
    for container in grouped.bar_containers:
        ax.bar_label(container, fmt="%.0f")
    ax.legend()
    ax.text(0.3, 4.6, "note", fontsize=11, bbox={"boxstyle": "square,pad=0.4", "fc": "#fff8dc"})

    svg = _svg(fig)
    labels = _labels(svg)

    assert {"2", "4", "3", "5", "note"} <= set(labels)
    assert labels["note"]["font-size"] != labels["4"]["font-size"]
    assert len(_boxes(svg)) == 1


def test_round_bbox_fails_closed_with_a_stable_reason() -> None:
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax.text(0.5, 0.5, "round", bbox={"boxstyle": "round", "fc": "white"})

    with pytest.raises(UnsupportedStaticExport, match="XYG_STATIC_UNSUPPORTED_ANNOTATION_BOXSTYLE"):
        _svg(fig)
