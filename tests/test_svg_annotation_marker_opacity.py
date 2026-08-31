from __future__ import annotations

import xml.etree.ElementTree as ET

import xyg

# ABI 185 admits labelled cartesian markers onto Scene SVG (`rgb()`, omit unit
# opacity). Compatibility `_svg.py` still serializes the authored hex and always
# writes `fill-opacity`.
_MARKER_STROKES = frozenset({"#dc2626", "rgb(220,38,38)"})


def _marker_shape(opacity: float) -> ET.Element:
    svg = (
        xyg.chart(
            xyg.scatter(x=[0.0, 1.0], y=[0.0, 1.0]),
            xyg.marker(
                0.5,
                0.5,
                color="#2563eb",
                stroke_color="#dc2626",
                stroke_width=2.0,
                opacity=opacity,
            ),
            width=320,
            height=240,
        )
        .figure()
        .to_svg()
    )
    root = ET.fromstring(svg)
    return next(element for element in root.iter() if element.get("stroke") in _MARKER_STROKES)


def test_annotation_marker_opacity_applies_to_fill_and_stroke() -> None:
    marker = _marker_shape(0.25)

    assert marker.get("fill-opacity") == "0.25"
    assert marker.get("stroke-opacity") == "0.25"


def test_opaque_annotation_marker_keeps_implicit_stroke_opacity() -> None:
    marker = _marker_shape(1.0)

    assert marker.get("fill-opacity") in (None, "1")
    assert marker.get("stroke-opacity") is None
