"""Scene arrow vocabulary: Python and Node author identical bytes (#1006).

Every admitted head/tail/shrink/clearance style is authored through the public
composition API in Python and through the public Node `Figure`, and the two
hosts must produce byte-identical Scenes (and therefore SVG, raster, and PDF).
Styles outside the documented table must fail closed with the same stable reason
on both hosts instead of falling back to a different arrow.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import xyg
from xyg import _native
from xyg._scene_v3 import figure_scene

ROOT = Path(__file__).resolve().parents[1]

# Matplotlib arrowstyle -> (head_style, tail_style) facts the pyplot shim emits.
ADMITTED = {
    "default": {},
    "-|>": {"head_style": "triangle"},
    "->": {"head_style": "v"},
    "<-": {"head_style": "none", "tail_style": "v"},
    "<->": {"head_style": "v", "tail_style": "v"},
    "-": {"head_style": "none"},
    "label-attach": {
        "head_style": "v",
        "start_offset": "6,-4",
        "label_clear": "20,20,8,8",
        "gap_start": 1.0,
        "gap_end": 3.0,
    },
    # A 60 px end gap on a ~170 px shaft is honored exactly (not discarded).
    "large-gap": {"head_style": "none", "gap_end": 60.0},
}
# Facts that no pixel geometry can satisfy: the Scene refuses instead of
# restoring the untrimmed arrow (shared canonical-scene rejection on both hosts).
GEOMETRY_REJECTED = {
    "gap-consumes-shaft": {"head_style": "none", "gap_end": 400.0},
    "clearance-swallows-shaft": {"head_style": "none", "label_clear": "400,400,400,400"},
    "gaps-sum-past-shaft": {"head_style": "none", "gap_start": 100.0, "gap_end": 100.0},
}
VOCABULARY_REJECTED = {
    "bar-head": {"head_style": "bar"},
    "triangle-tail": {"tail_style": "triangle"},
    "unknown-head": {"head_style": "fancy"},
    "short-offset": {"start_offset": "1"},
    "text-offset": {"start_offset": "1,x"},
    "short-clear": {"label_clear": "1,2,3"},
    "negative-clear": {"label_clear": "1,2,3,-4"},
    "negative-gap": {"gap_start": -1.0},
}
KEY_REJECTED = {
    "curve": {"curve": 0.2},
    "elbow": {"elbow": 1.0},
    "angle": {"angle_a": 90.0, "angle_b": 0.0},
    "tapered-shaft": {"shaft_width_start": 3.0},
    "bar-size": {"head_size": 6.0},
}
VOCABULARY_REASON = "XYG_SCENE_UNSUPPORTED_ARROW_STYLE"


def _scene(style: dict) -> bytes:
    chart = xyg.chart(
        xyg.line([0, 1, 2], [1, 3, 2], color="#ef4444", width=2),
        xyg.arrow(0.4, 3.4, 1.5, 1.2, color="#667085", width=1.5, style=style),
        xyg.x_axis(domain=(0, 2), label="Time"),
        xyg.y_axis(domain=(0, 4), label="Value"),
        xyg.legend(show=False),
        width=320,
        height=240,
        title="Panel",
    )
    return figure_scene(chart.figure())


@pytest.fixture(scope="module")
def node_results():
    if not shutil.which("node") or not (ROOT / "packages/xy-node/node_modules/koffi").exists():
        pytest.skip("Node/koffi unavailable")
    cases = {**ADMITTED, **VOCABULARY_REJECTED, **KEY_REJECTED, **GEOMETRY_REJECTED}
    process = subprocess.run(
        ["node", str(ROOT / "packages/xy-node/scripts/arrow_style_cross_host.mjs")],
        cwd=ROOT,
        input=json.dumps({"cases": cases}),
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, "XYG_NATIVE_LIB": str(_native._lib._name)},
    )
    assert process.returncode == 0, process.stdout + process.stderr
    return json.loads(process.stdout)


@pytest.mark.parametrize("name", ADMITTED)
def test_admitted_arrow_styles_are_byte_identical_across_hosts(name, node_results):
    node = node_results[name]
    assert "error" not in node, node.get("error")
    scene = _scene(ADMITTED[name])
    assert scene == base64.b64decode(node["scene"])
    assert _native.scene_svg(scene) == node["svg"]


def _arrow_paint(style: dict) -> tuple[int, int]:
    """(arrow polyline vertex count, filled head polygons) from the exported SVG."""
    svg = _native.scene_svg(_scene(style))
    plain = _native.scene_svg(
        figure_scene(
            xyg.chart(
                xyg.line([0, 1, 2], [1, 3, 2], color="#ef4444", width=2),
                xyg.x_axis(domain=(0, 2), label="Time"),
                xyg.y_axis(domain=(0, 4), label="Value"),
                xyg.legend(show=False),
                width=320,
                height=240,
                title="Panel",
            ).figure()
        )
    )
    polylines = re.findall(r'<polyline points="([^"]*)"', svg)
    assert len(polylines) == len(re.findall(r'<polyline points="([^"]*)"', plain)) + 1
    return len(polylines[-1].split()), svg.count('<path d="M ') - plain.count('<path d="M ')


def test_each_admitted_style_paints_its_own_arrow():
    # (vertices of the one arrow polyline, filled head polygons) per arrowstyle.
    assert _arrow_paint(ADMITTED["default"]) == (2, 1)
    assert _arrow_paint(ADMITTED["-|>"]) == (2, 1)
    assert _arrow_paint(ADMITTED["->"]) == (5, 0)
    assert _arrow_paint(ADMITTED["<-"]) == (5, 0)
    assert _arrow_paint(ADMITTED["<->"]) == (8, 0)
    assert _arrow_paint(ADMITTED["-"]) == (2, 0)
    assert _native.scene_svg(_scene({})) == _native.scene_svg(_scene(ADMITTED["-|>"]))
    shapes = {
        name: _native.scene_svg(_scene(style)) for name, style in ADMITTED.items() if name != "-|>"
    }
    assert len(set(shapes.values())) == len(shapes)


@pytest.mark.parametrize("name", VOCABULARY_REJECTED)
def test_unadmitted_arrow_style_values_fail_closed_with_one_stable_reason(name, node_results):
    node = node_results[name]
    assert VOCABULARY_REASON in node.get("error", ""), node
    with pytest.raises(ValueError, match=VOCABULARY_REASON):
        _scene(VOCABULARY_REJECTED[name])


@pytest.mark.parametrize("name", KEY_REJECTED)
def test_unadmitted_arrow_style_keys_fail_closed_on_both_hosts(name, node_results):
    node = node_results[name]
    assert "Scene arrow style does not encode" in node.get("error", ""), node
    with pytest.raises(ValueError, match="Scene arrow style does not encode"):
        _scene(KEY_REJECTED[name])


@pytest.mark.parametrize("name", GEOMETRY_REJECTED)
def test_unsatisfiable_shrink_is_rejected_on_both_hosts(name, node_results):
    assert "invalid canonical scene batch" in node_results[name].get("error", ""), node_results[
        name
    ]
    with pytest.raises(ValueError, match="invalid canonical scene batch"):
        _scene(GEOMETRY_REJECTED[name])


def test_large_gap_end_shortens_the_shaft_exactly():
    plain = _arrow_paint({"head_style": "none"})
    assert plain == _arrow_paint(ADMITTED["-"]) == (2, 0)
    svg = _native.scene_svg(_scene({"head_style": "none"}))
    gapped = _native.scene_svg(_scene(ADMITTED["large-gap"]))
    full = re.findall(r'<polyline points="([^"]*)"', svg)[-1].split()
    cut = re.findall(r'<polyline points="([^"]*)"', gapped)[-1].split()
    (fx, fy), (cx, cy) = (
        tuple(map(float, full[-1].split(","))),
        tuple(map(float, cut[-1].split(","))),
    )
    assert full[0] == cut[0]
    assert ((fx - cx) ** 2 + (fy - cy) ** 2) ** 0.5 == pytest.approx(60.0, abs=0.05)


def test_arrow_beside_styled_annotation_labels_keeps_the_painter_label_table_below_v7():
    """Labels beside arrows compose with `SceneLabel::annotation` provenance.

    XYLB v7 (annotation provenance) is a Scene-wire fact; the browser painter's
    label table must stay at the versions the TS decoder reads (<= 5) while the
    arrow run still reaches the painter as ordinary traces.
    """
    chart = xyg.chart(
        xyg.line([0, 1, 2], [1, 3, 2], color="#ef4444", width=2),
        xyg.text(1, 3, "styled note", dx=0, dy=-6, style={"label_background": "#ffffff"}),
        xyg.arrow(0.4, 3.4, 1.5, 1.2, style={"head_style": "v", "tail_style": "v"}),
        xyg.x_axis(domain=(0, 2), label="Time"),
        xyg.y_axis(domain=(0, 4), label="Value"),
        xyg.legend(show=False),
        width=320,
        height=240,
        title="Panel",
    )
    scene = figure_scene(chart.figure())
    painter = _native.scene_browser_painter(scene)
    at = painter.find(b"XYLB")
    assert at >= 0 and b"styled note" in painter
    assert int.from_bytes(painter[at + 4 : at + 8], "little") <= 5
    assert _native.scene_svg(scene).count("<polyline") >= 2
