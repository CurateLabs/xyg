from __future__ import annotations

import base64
import hashlib
import json
import struct
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

import xyg._scene_v3 as scene_v3
from xyg import _native, _svg
from xyg._figure import Figure
from xyg._scene_v3 import UnsupportedSceneV3, _colorbar_input
from xyg.channels import ColorChannel


def _xyad_from_figure(figure: Figure) -> bytes:
    compiled = _native.scene_pack_trace_compile(scene_v3._pack_xytc(figure))
    attached = _native.scene_pack_trace_attach(compiled, scene_v3._pack_xyta(figure))
    sidecars = _native.scene_pack_trace_sidecars(attached, scene_v3._pack_xynm(figure))
    rows = _native.scene_pack_trace_row_bytes(attached, scene_v3._pack_xycl(figure))
    facts = bytearray()
    for index, annotation in enumerate(list(getattr(figure, "annotations", None) or [])):
        facts.extend(scene_v3._pack_xyaf(annotation, index))
    output = (
        _native.scene_pack_annotation_facts(
            bytes(facts),
            style_ref_base=len(figure.traces),
            x_domain=tuple(float(value) for value in figure._range("x")),
            y_domain=tuple(float(value) for value in figure._range("y")),
        )
        if facts
        else b""
    )
    return scene_v3._unpack_xyas(_native.scene_splice_annotations(rows, sidecars, output))["xyad"]


EXPECTED_SCATTER = (
    '<g><circle cx="10" cy="11" r="3" fill="rgb(37,99,235)" '
    'stroke="rgb(0,0,0)" stroke-width="2"/><path d="M 15.5 21 H 24.5 '
    'M 20 16.5 V 25.5" fill="none" stroke="rgb(17,24,39)" '
    'stroke-opacity="0.25" stroke-width="1"/></g>'
)

AXIS_TICK_FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "axis_ticks.json").read_text())


def test_strict_csp_authored_scene_fixture_is_public_figure_bytes() -> None:
    """Keep the direct-browser full-chrome proof tied to public authoring."""
    from scripts.generate_authored_scene_benchmark import authored_scene

    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "authored_scene_v20.json").read_text()
    )
    assert fixture["schema"] == "xyg-authored-scene-v25-fixture-v1"
    assert fixture["count"] == 100
    scene = base64.b64decode(fixture["scene_base64"], validate=True)
    assert scene == authored_scene(100)
    assert fixture["scene_sha256"] == hashlib.sha256(scene).hexdigest()
    assert fixture["authoring"]["axes"]["x"]["side"] == "top"
    assert fixture["authoring"]["axes"]["y"]["side"] == "right"
    assert fixture["authoring"]["scatter"]["symbol"] == "diamond"
    assert fixture["authoring"]["wrapped_callout"]["wrap"] == 128.0
    assert '<path d="M ' in _native.scene_svg(scene)  # canonical Rust diamond geometry
    assert all(chunk in scene for chunk in (b"XYGS", b"XYLG", b"XYCB", b"XYLB"))


@pytest.mark.parametrize("count", (100, 10_000, 100_000, 1_000_000))
def test_authored_scene_evidence_tiers_keep_rust_chrome_consumers(count: int) -> None:
    """#116 retains one deterministic public workload at every evidence tier."""
    from scripts.generate_authored_scene_benchmark import authored_scene

    scene = authored_scene(count)
    assert scene == authored_scene(count)
    svg = _native.scene_svg(scene)
    raster = _native.scene_raster_commands(scene)
    painter = _native.scene_browser_painter(scene)
    for text in (
        "Authored Scene evidence",
        "Fraction",
        "Signal",
        "Series",
        "observations",
        "Intensity",
        "representative callout",
        "wrapped annotation",
        "evidence",
        "second line",
    ):
        assert text in svg
        assert text.encode() in raster
        assert text.encode() in painter
    assert all(chunk in painter for chunk in (b"XYLG", b"XYCB", b"XYLB"))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("class_name", "browser-only", "BROWSER_CSS|class_name"),
        ("style", {"font_family": "Example Sans"}, "font_family"),
        ("style", {"markup": "<b>rich</b>"}, "markup"),
        ("style", {"collision": "avoid"}, "collision"),
    ],
)
def test_scene_v25_wrapped_annotations_fail_closed_for_host_layout_features(
    field: str,
    value: object,
    message: str,
) -> None:
    """Wrapping is Rust layout, never a host markup/typography/collision seam."""
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.callout(0.5, 0.5, "wrapped annotation", wrap=96.0)
    figure.annotations[0][field] = value
    with pytest.raises(UnsupportedSceneV3, match=message):
        figure.to_scene()


def test_rust_scene_support_predicate_is_stable_and_fail_closed() -> None:
    assert _native.scene_support_reason(0) == ""
    assert _native.scene_support_reason((1 << 6) | (1 << 1)) == (
        "XYG_SCENE_UNSUPPORTED_CUSTOM_FONT: Scene v12 does not encode custom font resources"
    )
    with pytest.raises(ValueError, match="version or feature mask"):
        _native.scene_support_reason(1 << 63)
    for invalid_features in (True, "1", -1, 1.0, 1 << 64):
        with pytest.raises(ValueError, match="features must be a u64 bit mask"):
            _native.scene_support_reason(invalid_features)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="version or feature mask"):
        _native.scene_support_reason(0, request_version=2)
    for invalid in (True, -1, 1.5, 1 << 32):
        with pytest.raises(ValueError, match="request_version must be a u32 integer"):
            _native.scene_support_reason(0, request_version=invalid)  # type: ignore[arg-type]

    polar = Figure(coords="polar").line([0.0, 1.0], [0.0, 1.0])
    scene = polar.to_scene()
    assert scene[4:8] == (31).to_bytes(4, "little")
    svg = _native.scene_svg(scene)
    assert 'data-xy-grid="ring"' in svg or "<circle" in svg
    assert '<clipPath id="xy-scene-plot"><rect' not in svg

    polar_bar = Figure(coords="polar")
    polar_bar.bar([0.0, 1.0], [0.5, 0.8])
    bar_scene = polar_bar.to_scene()
    assert bar_scene[4:8] == (31).to_bytes(4, "little")
    bar_svg = _native.scene_svg(bar_scene)
    assert "<path" in bar_svg and 'd="M' in bar_svg
    polar_heatmap = Figure(coords="polar")
    polar_heatmap.heatmap([[1.0, 2.0], [3.0, 4.0]])
    heat_scene = polar_heatmap.to_scene()
    assert heat_scene[4:8] == (31).to_bytes(4, "little")
    heat_svg = _native.scene_svg(heat_scene)
    assert "<image" in heat_svg
    assert 'data-xy-polar-heatmap="true"' in heat_svg
    assert "<rect x=" not in heat_svg
    polar_contour = Figure(coords="polar")
    polar_contour.contour([[1.0, 2.0], [3.0, 4.0]], levels=2, color="#3987e5")
    contour_scene = polar_contour.to_scene()
    assert contour_scene[4:8] == (31).to_bytes(4, "little")
    contour_svg = _native.scene_svg(contour_scene)
    assert "<polyline" in contour_svg or "<path" in contour_svg

    custom_font = Figure().line([0.0, 1.0], [0.0, 1.0])
    custom_font.chrome_styles = {"title": {"font-family": "Example Sans"}}
    with pytest.raises(UnsupportedSceneV3, match="XYG_SCENE_UNSUPPORTED_CUSTOM_FONT"):
        custom_font.to_scene()

    browser_css = Figure().line([0.0, 1.0], [0.0, 1.0])
    browser_css.marker(0.5, 0.5, class_name="browser-only")
    with pytest.raises(UnsupportedSceneV3, match="XYG_SCENE_UNSUPPORTED_BROWSER_CSS"):
        browser_css.to_scene()

    data_color = Figure().scatter([0.0, 1.0], [0.0, 1.0], color=[0.0, 1.0])
    with pytest.raises(UnsupportedSceneV3, match="XYG_SCENE_UNSUPPORTED_GRADIENT"):
        data_color.to_scene()

    missing_constant = Figure().scatter([0.0], [0.0])
    missing_constant.traces[0].color_ch = ColorChannel(mode="constant", constant=None)
    with pytest.raises(UnsupportedSceneV3, match="XYG_SCENE_UNSUPPORTED_GRADIENT"):
        missing_constant.to_scene()


def test_figure_support_axis_allowlist_is_rust_owned() -> None:
    figure = Figure().line([0.0, 1.0], [0.0, 1.0])
    figure.axis_options["x"]["collision"] = "hide"
    with pytest.raises(UnsupportedSceneV3, match="tick formatting"):
        figure.to_scene()
    extra = Figure().line([0.0, 1.0], [0.0, 1.0])
    extra.axis_options["z"] = {"label": "z"}
    with pytest.raises(UnsupportedSceneV3, match="exactly x/y"):
        extra.to_scene()


def test_scene_v19_colorbar_python_framer_matches_literal_stop_contract() -> None:
    figure = Figure()
    figure.colorbar_options = {
        "domain": [0.0, 1.0],
        "stops": [(0.0, [0, 0, 0, 255]), (1.0, [255, 255, 255, 128])],
    }
    assert _colorbar_input(figure)[:4] == b"XYCB"

    for stops in (
        [(0.1, [0, 0, 0, 255]), (1.0, [255, 255, 255, 255])],
        [(0.0, [0, 0, 0, 255]), (0.0, [255, 255, 255, 255])],
        [(0.0, [0, 0, 0, 255]), (0.9, [255, 255, 255, 255])],
    ):
        figure.colorbar_options["stops"] = stops
        with pytest.raises(UnsupportedSceneV3, match="strictly increasing"):
            _colorbar_input(figure)
    figure.colorbar_options = {
        "domain": [0.0, 1.0],
        "stops": [(0.0, [0, 0, 0, 255]), (1.0, [255, 255, 255, 255])],
        "text_rgba": object(),
    }
    with pytest.raises(UnsupportedSceneV3, match="uses literal RGBA"):
        _colorbar_input(figure)


def test_python_callout_label_background_uses_xyac_v2_only_when_requested() -> None:
    plain = Figure().callout(0.5, 0.5, "plain")
    assert scene_v3.figure_scene(plain)[:4] == b"XYGS"
    v1 = _xyad_from_figure(plain)
    xyac_start = 24 + sum(struct.unpack_from("<IIII", v1, 8)[:3])
    assert v1[xyac_start : xyac_start + 8] == b"XYAC\x01\x00\x00\x00"
    assert len(v1) - xyac_start == 12 + 60 + len(b"plain")

    mixed = Figure().callout(0.25, 0.25, "clear")
    mixed.callout(0.75, 0.75, "filled", style={"label_background": "#123456"})
    assert scene_v3.figure_scene(mixed)[:4] == b"XYGS"
    v2 = _xyad_from_figure(mixed)
    xyac_start = 24 + sum(struct.unpack_from("<IIII", v2, 8)[:3])
    assert v2[xyac_start : xyac_start + 8] == b"XYAC\x02\x00\x00\x00"
    first = xyac_start + 12
    second = first + 64 + len(b"clear")
    assert v2[first + 60 : first + 64] == b"\0\0\0\0"
    assert v2[second + 60 : second + 64] == bytes((18, 52, 86, 255))

    invalid = Figure().callout(0.5, 0.5, "bad", style={"label_background": 7})
    with pytest.raises(ValueError, match="label background"):
        scene_v3.figure_scene(invalid)


def test_python_label_borders_select_v23_frames_and_reject_partial_style() -> None:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    style = {
        "color": "#667085",
        "label_background": "#ffffff",
        "label_border_color": "#123456",
        "label_border_width": 1.5,
    }
    figure.text(0.25, 0.25, "text", style=style)
    figure.marker(0.5, 0.5, text="attached", style=style)
    figure.callout(0.75, 0.75, "callout", dx=-20, dy=-20, style=style)
    assert scene_v3.figure_scene(figure)[:4] == b"XYGS"
    envelope = _xyad_from_figure(figure)
    assert envelope[:8] == b"XYAD\x03\x00\x00\x00"
    lengths = struct.unpack_from("<IIIII", envelope, 8)
    at = 28
    assert envelope[at : at + 8] == b"XYAT\x01\x00\x00\x00"
    at += lengths[0]
    assert envelope[at : at + 8] == b"XYAL\x02\x00\x00\x00"
    at += lengths[1] + lengths[2]
    assert envelope[at : at + 8] == b"XYAC\x03\x00\x00\x00"
    at += lengths[3]
    assert envelope[at : at + 12] == b"XYAW\x01\x00\x00\x00\x02\x00\x00\x00"
    invalid = Figure().text(
        0.5, 0.5, "bad", style={"color": "#667085", "label_border_color": "#000"}
    )
    with pytest.raises(UnsupportedSceneV3, match="requires color and width"):
        scene_v3.figure_scene(invalid)


def test_scene_v19_colorbar_python_framer_encodes_bounded_ticks_and_minor_flag() -> None:
    figure = Figure()
    figure.colorbar_options = {
        "domain": [0.0, 1.0],
        "stops": [(0.0, [0, 0, 0, 255]), (1.0, [255, 255, 255, 255])],
        "ticks": [0.0, 0.5, 1.0],
        "minor_ticks": True,
    }
    encoded = _colorbar_input(figure)
    assert int.from_bytes(encoded[4:8], "little") == 2
    assert encoded[8] == 0b1110
    assert int.from_bytes(encoded[16:20], "little") == 3
    assert struct.unpack_from("<3d", encoded, 80) == (0.0, 0.5, 1.0)

    figure.colorbar_options["ticks"] = []
    assert _colorbar_input(figure)[8] == 0b0110
    figure.colorbar_options["ticks"] = [0.0, 0.0]
    with pytest.raises(UnsupportedSceneV3, match="ticks"):
        _colorbar_input(figure)
    figure.colorbar_options["ticks"] = [0.0, 1.0]
    figure.colorbar_options["minor_ticks"] = 1
    with pytest.raises(UnsupportedSceneV3, match="minor_ticks"):
        _colorbar_input(figure)


def test_scene_v19_colorbar_maximum_frame_reaches_the_browser_painter() -> None:
    figure = Figure(width=640, height=480).scatter([0.0, 1.0], [0.0, 1.0])
    figure.colorbar_options = {
        "domain": [0.0, 1.0],
        "stops": [(index / 15.0, [index, 0, 0, 255]) for index in range(16)],
        "ticks": [index / 31.0 for index in range(32)],
        "minor_ticks": True,
        "title": "x" * 4096,
    }
    painter = _native.scene_browser_painter(figure.to_scene())
    colorbar_length = int.from_bytes(painter[284:288], "little")
    assert colorbar_length > 4600
    assert b"XYCB" in painter and b"XYCT" in painter


def test_scene_v11_primary_annotations_are_canonical_and_ordered() -> None:
    figure = Figure(width=320, height=240).scatter([0.0, 1.0], [0.0, 1.0])
    figure.vline(0.25, color="#ff0000", width=2.0)
    figure.y_band(0.2, 0.4, color="#00ff00", opacity=0.25)
    figure.marker(0.75, 0.8, color="#0000ff", size=10.0, symbol="diamond")
    encoded = figure.to_scene()
    assert encoded[:4] == b"XYGS"
    assert int.from_bytes(encoded[4:8], "little") == 31
    svg = _native.scene_svg(encoded)
    assert svg.index("rgb(255,0,0)") < svg.index("rgb(0,255,0)") < svg.index("rgb(0,0,255)")
    assert "rgb(255,0,0)" in svg
    assert "rgb(0,255,0)" in svg
    assert "rgb(0,0,255)" in svg
    assert _native.scene_raster_commands(encoded)

    annotation_only = Figure(width=320, height=240)
    annotation_only.axis_options["x"]["domain"] = (0.0, 1.0)
    annotation_only.axis_options["y"]["domain"] = (0.0, 1.0)
    annotation_only.vline(0.25, color="#ff0000", width=2.0)
    annotation_only.y_band(0.2, 0.4, color="#00ff00", opacity=0.25)
    annotation_only.marker(0.75, 0.8, color="#0000ff", size=10.0, symbol="diamond")
    fixture = json.loads((Path(__file__).parent / "fixtures" / "figure_scene_v3.json").read_text())
    assert (
        hashlib.sha256(annotation_only.to_scene()).hexdigest()
        == fixture["primary_annotations_sha256"]
    )


def test_scene_v16_annotations_attach_bounded_labels_and_reject_richer_content() -> None:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    figure.vline(0.25, text="rule")
    figure.x_band(0.2, 0.4, text="band")
    figure.marker(0.75, 0.8, text="marker")
    scene = figure.to_scene()
    painter = _native.scene_browser_painter(scene)
    assert all(value in painter for value in (b"rule", b"band", b"marker"))


def test_scene_v17_native_boundary_accepts_two_bounded_text_frames_and_straight_arrows() -> None:
    figure = Figure(width=320, height=240)
    figure.axis_options["x"]["domain"] = (0.0, 1.0)
    figure.axis_options["y"]["domain"] = (0.0, 1.0)
    text = "x" * 4096
    figure.text(0.5, 0.5, text, color="#667085")
    figure.marker(0.5, 0.5, text=text)
    scene = figure.to_scene()
    assert _native.scene_svg(scene).count(text) == 2
    arrow_scene = Figure().arrow(0.0, 0.0, 1.0, 1.0).to_scene()
    assert "rgb(102,112,133)" in _native.scene_svg(arrow_scene)
    callout_scene = Figure().callout(0.5, 0.5, "label").to_scene()
    callout_svg = _native.scene_svg(callout_scene)
    assert "label" in callout_svg
    assert 'data-xy-stable-id="6366126145334673408"' in callout_svg
    dashed_rule = Figure().vline(1.0, style={"dash": "2,2"}).to_scene()
    assert b"XYDS" in dashed_rule
    assert 'stroke-dasharray="2,2"' in _native.scene_svg(dashed_rule)


@pytest.mark.parametrize(
    "style",
    [
        {"color": ""},
        {"color": None},
        {"opacity": None},
        {"opacity": ""},
        {"opacity": "opaque"},
        {"width": None},
        {"width": False},
    ],
)
def test_scene_v10_annotation_style_falsey_values_do_not_become_defaults(
    style: dict[str, object],
) -> None:
    figure = Figure().vline(1.0)
    figure.annotations[0]["style"] = style
    with pytest.raises(ValueError, match="Scene v12"):
        figure.to_scene()


@pytest.mark.parametrize(
    "annotation",
    [
        {"kind": "rule", "axis": "x", "value": None},
        {"kind": "rule", "axis": "x", "value": ""},
        {"kind": "rule", "axis": "x", "value": False},
        {"kind": "band", "axis": "x", "start": " ", "end": 1.0},
        {"kind": "marker", "x": "not-a-number", "y": 1.0},
        {"kind": "marker", "x": 0.0, "y": 1.0, "size": None},
        {"kind": "marker", "x": 0.0, "y": 1.0, "symbol": 2},
    ],
)
def test_scene_v10_annotation_geometry_is_strict_across_hosts(
    annotation: dict[str, object],
) -> None:
    figure = Figure()
    figure.annotations = [annotation]
    with pytest.raises(ValueError, match="Scene v12"):
        figure.to_scene()


def test_python_scene_v3_matches_shared_scatter_line_bar_axis_bytes() -> None:
    fixture = json.loads((Path(__file__).parent / "fixtures" / "scene_v3.json").read_text())
    encoded = _native.scene_batch_encode(
        viewport=tuple(fixture["viewport"]),
        margins=tuple(fixture["margins"]),
        x_axis=tuple(fixture["x_axis"]),
        y_axis=tuple(fixture["y_axis"]),
        kinds=fixture["kinds"],
        stable_ids=fixture["stable_ids"],
        style_refs=fixture["style_refs"],
        fill_rgba=[channel for style in fixture["styles"] for channel in style["fill_rgba"]],
        stroke_rgba=[channel for style in fixture["styles"] for channel in style["stroke_rgba"]],
        stroke_width=[style["stroke_width"] for style in fixture["styles"]],
        diameter=fixture["diameter"],
        symbols=fixture["symbols"],
        x0=fixture["x0"],
        y0=fixture["y0"],
        x1=fixture["x1"],
        y1=fixture["y1"],
    )
    assert hashlib.sha256(encoded).hexdigest() == fixture["expected_sha256"]
    assert encoded[:4] == b"XYGS"
    assert int.from_bytes(encoded[4:8], "little") == 31
    records = 160 + len(fixture["styles"]) * 16
    assert encoded[records + 1] == 1  # center is outside, marker extent overlaps
    assert encoded[records + 2] == 2  # diamond
    assert np.frombuffer(encoded, dtype="<f8", count=1, offset=records + 48)[0] == 16.0
    line0 = records + 56
    line1 = line0 + 56
    rect = line1 + 56
    assert int.from_bytes(encoded[line0 + 8 : line0 + 16], "little") == 201
    assert int.from_bytes(encoded[line1 + 8 : line1 + 16], "little") == 201
    np.testing.assert_array_equal(
        np.frombuffer(encoded, dtype="<f8", count=2, offset=line0 + 32), 0
    )
    np.testing.assert_allclose(
        np.frombuffer(encoded, dtype="<f8", count=4, offset=rect + 16),
        [156.0, 142.0, 272.0, 318.0],
    )


def test_legacy_native_batch_reserves_annotation_identity_prefix() -> None:
    fixture = json.loads((Path(__file__).parent / "fixtures" / "scene_v3.json").read_text())
    fixture["stable_ids"][0] = 0x5859010000000001
    with pytest.raises(ValueError, match="invalid canonical scene batch"):
        _native.scene_batch_encode(
            viewport=tuple(fixture["viewport"]),
            margins=tuple(fixture["margins"]),
            x_axis=tuple(fixture["x_axis"]),
            y_axis=tuple(fixture["y_axis"]),
            kinds=fixture["kinds"],
            stable_ids=fixture["stable_ids"],
            style_refs=fixture["style_refs"],
            fill_rgba=[channel for style in fixture["styles"] for channel in style["fill_rgba"]],
            stroke_rgba=[
                channel for style in fixture["styles"] for channel in style["stroke_rgba"]
            ],
            stroke_width=[style["stroke_width"] for style in fixture["styles"]],
            diameter=fixture["diameter"],
            symbols=fixture["symbols"],
            x0=fixture["x0"],
            y0=fixture["y0"],
            x1=fixture["x1"],
            y1=fixture["y1"],
        )


def test_python_scene_v8_authored_chrome_matches_node_fixture_bytes() -> None:
    fixture = json.loads((Path(__file__).parent / "fixtures" / "scene_v3.json").read_text())
    encoded = _native.scene_batch_encode(
        viewport=(100, 80),
        margins=(10, 10, 10, 10),
        x_axis=(1, 0, 0, 1, 1, False),
        y_axis=(2, 0, 0, 1, 1, False),
        kinds=[0],
        stable_ids=[9],
        style_refs=[0],
        fill_rgba=[1, 2, 3, 255],
        stroke_rgba=[0, 0, 0, 0],
        stroke_width=[0],
        diameter=[6],
        symbols=[0],
        x0=[0.5],
        y0=[0.5],
        x1=[0],
        y1=[0],
        chrome_style=bytes.fromhex(fixture["authored_chrome_style_hex"]),
        x_major_ticks=[0, 0.5, 1],
        x_minor_ticks=[0.25, 0.75],
        y_major_ticks=[],
        y_minor_ticks=[0.5],
    )
    assert hashlib.sha256(encoded).hexdigest() == fixture["authored_chrome_sha256"]
    svg = _native.scene_svg(encoded)
    assert 'data-xy-chrome="chart-background"' in svg
    assert 'stroke="rgba(23,24,25,1.000000)"' in svg


def test_python_figure_authored_chrome_matches_node_figure_fixture_bytes() -> None:
    fixture = json.loads((Path(__file__).parent / "fixtures" / "scene_v3.json").read_text())[
        "figure_authored_chrome"
    ]
    figure = Figure(width=fixture["viewport"][0], height=fixture["viewport"][1])
    figure.style = fixture["style"]
    figure.set_axis("x", **fixture["x_axis"])
    figure.set_axis("y", **fixture["y_axis"])
    figure.scatter(fixture["scatter"]["x"], fixture["scatter"]["y"])
    figure.traces[-1].id = fixture["scatter"]["id"]
    assert (
        hashlib.sha256(scene_v3.figure_scene(figure, margins=tuple(fixture["margins"]))).hexdigest()
        == fixture["sha256"]
    )


def test_python_scene_v3_rejects_malformed_batches() -> None:
    options = dict(
        viewport=(100.0, 80.0),
        margins=(10.0, 10.0, 10.0, 10.0),
        x_axis=(1, 0, 0.0, 1.0, 1.0, False),
        y_axis=(2, 0, 0.0, 1.0, 1.0, False),
        kinds=[0],
        stable_ids=[1],
        style_refs=[0],
        fill_rgba=[0, 0, 0, 255],
        stroke_rgba=[0, 0, 0, 255],
        stroke_width=[1.0],
        diameter=[8.0],
        symbols=[0],
        x0=[0.5],
        y0=[0.5],
        x1=[0.5],
        y1=[0.5],
    )
    with np.testing.assert_raises_regex(ValueError, "equal length"):
        _native.scene_batch_encode(**(options | {"stable_ids": []}))
    with np.testing.assert_raises_regex(ValueError, "invalid canonical scene batch"):
        _native.scene_batch_encode(**(options | {"kinds": [9]}))
    with np.testing.assert_raises_regex(ValueError, "invalid canonical scene batch"):
        _native.scene_batch_encode(**(options | {"style_refs": [1]}))
    with np.testing.assert_raises_regex(ValueError, "invalid canonical scene batch"):
        _native.scene_batch_encode(**(options | {"margins": (60.0, 40.0, 10.0, 10.0)}))
    with np.testing.assert_raises_regex(ValueError, "4,096 UTF-8 bytes"):
        _native.scene_batch_encode(**(options | {"title": "x" * 4_097}))
    with np.testing.assert_raises_regex(ValueError, "19,504 bytes"):
        _native.scene_batch_encode(
            **(options | {"legend_input": bytes(_native.MAX_SCENE_LEGEND_INPUT_BYTES + 1)})
        )


def test_python_scene_v3_rejects_unsigned_values_before_coercion() -> None:
    options = dict(
        viewport=(100.0, 80.0),
        margins=(10.0, 10.0, 10.0, 10.0),
        x_axis=(1, 0, 0.0, 1.0, 1.0, False),
        y_axis=(2, 0, 0.0, 1.0, 1.0, False),
        kinds=[0],
        stable_ids=[1],
        style_refs=[0],
        fill_rgba=[0, 0, 0, 255],
        stroke_rgba=[0, 0, 0, 255],
        stroke_width=[0.0],
        diameter=[8.0],
        symbols=[0],
        x0=[0.5],
        y0=[0.5],
        x1=[0.0],
        y1=[0.0],
    )
    assert _native.scene_batch_encode(
        **(
            options
            | {
                "x_axis": (2**64 - 1, 0, 0.0, 1.0, 1.0, False),
                "y_axis": (2**64 - 1, 0, 0.0, 1.0, 1.0, False),
                "stable_ids": [2**64 - 1],
                "fill_rgba": [0, 255, 0, 255],
            }
        )
    )
    for field, values in (
        ("kinds", [-1]),
        ("kinds", [256]),
        ("kinds", [1.5]),
        ("symbols", [-1]),
        ("symbols", [256]),
        ("style_refs", [-1]),
        ("style_refs", [2**32]),
        ("stable_ids", [-1]),
        ("stable_ids", [2**64]),
        ("fill_rgba", [-1, 0, 0, 255]),
        ("stroke_rgba", [0, 0, 0, 256]),
    ):
        with np.testing.assert_raises_regex(ValueError, "unsigned"):
            _native.scene_batch_encode(**(options | {field: values}))
    for axis in ("x_axis", "y_axis"):
        for invalid_id in (-1, 2**64, 1.5):
            value = (invalid_id, 0, 0.0, 1.0, 1.0, False)
            with np.testing.assert_raises_regex(ValueError, f"scene {axis} id"):
                _native.scene_batch_encode(**(options | {axis: value}))


def test_python_scene_v3_log_mask_ignores_reserved_coordinates_and_breaks_lines() -> None:
    encoded = _native.scene_batch_encode(
        viewport=(100.0, 100.0),
        margins=(10.0, 10.0, 10.0, 10.0),
        x_axis=(1, 1, 1.0, 10.0, 1.0, True),
        y_axis=(2, 1, 1.0, 10.0, 1.0, True),
        kinds=[0, 1, 1, 1, 2, 2],
        stable_ids=[1, 20, 20, 20, 30, 31],
        style_refs=[0] * 6,
        fill_rgba=[0, 0, 0, 255],
        stroke_rgba=[0, 0, 0, 255],
        stroke_width=[0.0],
        diameter=[6.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        symbols=[0] * 6,
        x0=[2.0, 2.0, 0.0, 4.0, 2.0, 2.0],
        y0=[2.0] * 6,
        x1=[0.0, 0.0, 0.0, 0.0, 8.0, 0.0],
        y1=[0.0, 0.0, 0.0, 0.0, 8.0, 8.0],
    )
    records = 176
    assert [encoded[records + index * 56 + 1] for index in range(6)] == [1, 1, 0, 1, 1, 0]
    assert encoded[records + 32 : records + 48] == bytes(16)
    assert encoded[records + 88 : records + 104] == bytes(16)


def test_linear_and_log_ticks_are_consumed_from_the_rust_scene(monkeypatch) -> None:
    calls: list[tuple[int, float, float, int]] = []
    original = _native.scene_axis_ticks

    def recording(kind: int, lo: float, hi: float, target: int, aux: float = 0.0):
        calls.append((kind, lo, hi, target))
        return original(kind, lo, hi, target, aux=aux)

    monkeypatch.setattr(_native, "scene_axis_ticks", recording)
    assert _svg.axis_ticks(
        {"kind": "linear", "range": [-0.9, 5.1], "tick_count": 6}, 480.0, True
    ) == ([0.0, 1.0, 2.0, 3.0, 4.0, 5.0], [0.0, 1.0, 2.0, 3.0, 4.0, 5.0], 1.0)
    assert _svg.axis_ticks({"kind": "log", "range": [0.1, 100.0], "tick_count": 6}, 480.0, True)[
        1
    ] == [0.1, 1.0, 10.0, 100.0]
    assert calls == [(0, -0.9, 5.1, 6), (1, 0.1, 100.0, 6)]


def test_time_ticks_are_consumed_from_the_rust_scene(monkeypatch) -> None:
    calls: list[tuple[int, float, float, int]] = []
    original = _native.scene_axis_ticks

    def recording(kind: int, lo: float, hi: float, target: int, aux: float = 0.0):
        calls.append((kind, lo, hi, target))
        return original(kind, lo, hi, target, aux=aux)

    monkeypatch.setattr(_native, "scene_axis_ticks", recording)
    hour = 3_600_000.0
    assert _svg.axis_ticks(
        {"kind": "time", "range": [0.0, 3.0 * hour], "tick_count": 6}, 480.0, True
    ) == (
        [0.0, 0.5 * hour, hour, 1.5 * hour, 2.0 * hour, 2.5 * hour, 3.0 * hour],
        [0.0, 0.5 * hour, hour, 1.5 * hour, 2.0 * hour, 2.5 * hour, 3.0 * hour],
        0.5 * hour,
    )
    lo = datetime(2020, 1, 1, tzinfo=UTC).timestamp() * 1e3
    hi = datetime(2022, 1, 1, tzinfo=UTC).timestamp() * 1e3
    ticks, labeled, step = _svg.axis_ticks(
        {"kind": "time", "range": [lo, hi], "tick_count": 6}, 480.0, True
    )
    assert step == 6.0 * 30.0 * 86_400_000.0
    assert ticks == [
        lo,
        datetime(2020, 7, 1, tzinfo=UTC).timestamp() * 1e3,
        datetime(2021, 1, 1, tzinfo=UTC).timestamp() * 1e3,
        datetime(2021, 7, 1, tzinfo=UTC).timestamp() * 1e3,
        hi,
    ]
    assert labeled == ticks
    assert calls == [(5, 0.0, 3.0 * hour, 6), (5, lo, hi, 6)]


def test_symlog_ticks_are_consumed_from_the_rust_scene(monkeypatch) -> None:
    calls: list[tuple[int, float, float, int, float]] = []
    original = _native.scene_axis_ticks

    def recording(kind: int, lo: float, hi: float, target: int, aux: float = 0.0):
        calls.append((kind, lo, hi, target, aux))
        return original(kind, lo, hi, target, aux=aux)

    monkeypatch.setattr(_native, "scene_axis_ticks", recording)
    ticks, labeled, step = _svg.axis_ticks(
        {"kind": "linear", "scale": "symlog", "constant": 2.0, "range": [-10.0, 10.0]},
        320.0,
        True,
    )
    assert ticks == labeled == pytest.approx([-3.43656365691809, 0.0, 3.43656365691809])
    assert step == pytest.approx(3.43656365691809)
    assert calls == [(6, -10.0, 10.0, 4, 2.0)]


def test_all_axis_tick_families_match_the_shared_cross_host_fixture() -> None:
    assert AXIS_TICK_FIXTURE["schema"] == "xyg-axis-ticks-v1"
    kind_codes = {"linear": 0, "log": 1, "category": 2, "time": 5, "symlog": 6}
    for case in AXIS_TICK_FIXTURE["cases"]:
        kind = case["kind"]
        if kind == "angular":
            code = 3 if case["unit"] == "degrees" else 4
            aux = 0.0
        else:
            code = kind_codes[kind]
            aux = float(case.get("categories", case.get("constant", 0.0)))
        ticks, labeled, step = _native.scene_axis_ticks(
            code, case["lo"], case["hi"], case["target"], aux=aux
        )
        actual = {"ticks": ticks, "labeled": labeled, "step": step}
        tolerance = case.get("tolerance")
        if tolerance is None:
            assert actual == case["expected"], case["name"]
        else:
            assert actual["ticks"] == pytest.approx(
                case["expected"]["ticks"], rel=tolerance, abs=tolerance
            ), case["name"]
            assert actual["labeled"] == pytest.approx(
                case["expected"]["labeled"], rel=tolerance, abs=tolerance
            ), case["name"]
            assert actual["step"] == pytest.approx(
                case["expected"]["step"], rel=tolerance, abs=tolerance
            ), case["name"]


@pytest.mark.parametrize(
    ("lo", "hi", "target", "constant"),
    [
        (-1.0, 1.0, 0, 1.0),
        (-1.0, 1.0, 201, 1.0),
        (-1.0, 1.0, 6, 0.0),
        (-1.0, 1.0, 6, -1.0),
        (-1.0, 1.0, 6, float("nan")),
        (-1.0, 1.0, 6, float("inf")),
        (float("nan"), 1.0, 6, 1.0),
        (-1.0, float("inf"), 6, 1.0),
    ],
)
def test_symlog_tick_abi_fails_closed_on_invalid_bounds(
    lo: float, hi: float, target: int, constant: float
) -> None:
    with pytest.raises(ValueError, match="invalid canonical axis tick request"):
        _native.scene_axis_ticks(6, lo, hi, target, aux=constant)


def test_symlog_tick_abi_accepts_the_200_tick_target_ceiling() -> None:
    ticks, labeled, step = _native.scene_axis_ticks(6, -1e12, 1e12, 200, aux=1.0)
    assert 0 < len(ticks) <= 200
    assert ticks == labeled
    assert step > 0.0


def test_static_scale_consumes_rust_scene_policy_for_all_numeric_kinds(monkeypatch) -> None:
    calls: list[tuple[int, int]] = []
    original = _native.scene_scale_map

    def recording(values, kind, operation, *args, **kwargs):
        calls.append((kind, operation))
        return original(values, kind, operation, *args, **kwargs)

    monkeypatch.setattr(_native, "scene_scale_map", recording)
    linear = _svg._Scale({"kind": "linear", "range": [0.0, 10.0]}, 20.0, 120.0)
    np.testing.assert_allclose(linear([0.0, 5.0, 10.0]), [20.0, 70.0, 120.0])
    log = _svg._Scale({"kind": "linear", "scale": "log", "range": [0.1, 100.0]}, 0.0, 300.0)
    np.testing.assert_allclose(log([0.1, 1.0, 100.0]), [0.0, 100.0, 300.0])
    symlog = _svg._Scale(
        {"kind": "linear", "scale": "symlog", "constant": 2.0, "range": [-10.0, 10.0]}, 0.0, 100.0
    )
    coordinates = symlog.coord([-4.0, 0.0, 4.0])
    np.testing.assert_allclose(symlog.value(coordinates), [-4.0, 0.0, 4.0])
    assert {(0, 1), (1, 1), (2, 0), (2, 2)} <= set(calls)


def test_static_log_scale_preserves_clip_mask_and_nan_behavior() -> None:
    clipped = _svg._Scale({"range": [0.1, 10.0], "scale": "log"}, 0.0, 100.0)
    masked = _svg._Scale({"range": [0.1, 10.0], "scale": "log", "nonpositive": "mask"}, 0.0, 100.0)
    clipped_values = np.asarray(clipped.coord([-1.0, 0.0, np.nan]))
    assert clipped_values[:2].tolist() == [-300.0, -300.0]
    assert np.isnan(clipped_values[2])
    assert np.isnan(masked.coord(0.0))


def test_static_scale_reuses_rust_scalar_results_across_export_consumers(monkeypatch) -> None:
    calls = 0
    original = _native.scene_scale_map

    def recording(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(_native, "scene_scale_map", recording)
    scale = _svg._Scale({"range": [0.0, 10.0]}, 20.0, 120.0)
    assert scale(5.0) == scale(5.0) == 70.0
    assert scale.coord(5.0) == scale.coord(5.0) == 5.0
    assert scale.value(5.0) == scale.value(5.0) == 5.0
    # One Rust call per distinct scalar operation; repeated consumers are
    # cache hits. Rust owns transformed-domain preparation inside each batch.
    assert calls == 3


def test_static_scale_batches_vectors_and_seeds_followup_scalar_consumers(monkeypatch) -> None:
    shapes: list[tuple[int, ...]] = []
    original = _native.scene_scale_map

    def recording(values, *args, **kwargs):
        shapes.append(np.shape(values))
        return original(values, *args, **kwargs)

    monkeypatch.setattr(_native, "scene_scale_map", recording)
    scale = _svg._Scale({"range": [0.0, 10.0]}, 20.0, 120.0)
    np.testing.assert_allclose(scale([2.0, 4.0, 6.0]), [40.0, 60.0, 80.0])
    # Tick/grid/label consumers revisit these positions individually. The
    # vector's Rust results seed the bounded cache, so none adds an ABI call.
    assert [scale(value) for value in (2.0, 4.0, 6.0)] == [40.0, 60.0, 80.0]
    assert shapes == [(3,)]


def test_static_scale_vector_cache_never_exceeds_its_per_operation_bound() -> None:
    scale = _svg._Scale({"range": [0.0, 1000.0]}, 0.0, 1000.0)
    scale(np.arange(250.0))
    scale(np.concatenate((np.arange(240.0, 250.0), np.arange(250.0, 496.0))))
    assert len(scale._scalar_cache[1]) == scale._SCALAR_CACHE_LIMIT

    # A disjoint vector at the per-call limit cannot grow a full cache. Other
    # operations retain independent hard bounds rather than sharing capacity.
    scale(np.arange(1000.0, 1256.0))
    scale.coord(np.arange(512.0))
    scale.value(np.arange(512.0, 768.0))
    assert all(len(cache) <= scale._SCALAR_CACHE_LIMIT for cache in scale._scalar_cache)


def test_python_consumes_the_versioned_rust_scatter_scene() -> None:
    assert _native.scene_version() == 31


def test_scene_authored_tick_labels_keep_their_explicit_tick_pairing() -> None:
    figure = Figure(width=300, height=200).scatter([0.0, 1.0], [0.0, 1.0])
    figure.axis_options["x"].update(
        domain=(0.0, 1.0),
        tick_values=[-1.0, 0.0],
        tick_labels=["off-domain-long-label", "zero"],
    )
    scene = figure.to_scene()
    svg = _native.scene_svg(scene)
    raster = _native.scene_raster_commands(scene)
    painter = _native.scene_browser_painter(scene)
    for output in (svg.encode(), raster, painter):
        assert b"zero" in output
        assert b"off-domain-long-label" not in output
    assert (
        _native.scene_scatter_svg(
            [10.0, 20.0],
            [11.0, 21.0],
            [8.0, 10.0],
            np.array([[37, 99, 235, 255], [239, 68, 68, 128]], dtype=np.uint8),
            np.array([[0, 0, 0, 255], [17, 24, 39, 64]], dtype=np.uint8),
            [2.0, 0.0],
            [0, 15],
        )
        == EXPECTED_SCATTER
    )


def test_public_svg_diamond_routes_through_the_whole_scene_consumer(monkeypatch) -> None:
    original = _native.scene_static_export
    calls: list[bytes] = []

    def record(*args, **kwargs):
        calls.append(args[0][:4])
        return original(*args, **kwargs)

    monkeypatch.setattr(_native, "scene_static_export", record)
    svg = Figure().scatter([0.0, 1.0], [1.0, 0.0], symbol="diamond").to_svg()

    assert calls == [b"XYGS"]
    assert '<path d="M ' in svg
    assert 'fill="rgb(57,135,229)" fill-opacity="0.8"' in svg


def test_scene_plot_layout_owns_cartesian_gutters() -> None:
    left, right, top, bottom = _native.scene_plot_layout(
        viewport=(320, 240),
        x_axis=(0, 0.0, 4.0, 1.0, False),
        y_axis=(0, 0.0, 5.0, 1.0, False),
    )
    assert left >= 46.0 and right >= 8.0 and top >= 6.0 and bottom >= 36.0
    scene = Figure(width=320, height=240).scatter([1.0], [2.0]).to_scene()
    view = memoryview(scene)
    assert float(np.frombuffer(view[48:56], dtype="<f8")[0]) == left


def test_scene_plot_layout_validates_and_measures_numeric_formats() -> None:
    axes = {
        "viewport": (640, 360),
        "x_axis": (0, 0.0, 1.0, 1.0, False),
        "y_axis": (0, 0.0, 100_000.0, 1.0, False),
    }
    plain = _native.scene_plot_layout(**axes)
    formatted = _native.scene_plot_layout(**axes, x_format=".1%", y_format="$,.0f USD")
    assert formatted[0] > plain[0]
    with pytest.raises(ValueError, match="256 UTF-8 bytes"):
        _native.scene_plot_layout(**axes, x_format="x" * 257)
    with pytest.raises(ValueError, match="NUL-free"):
        _native.scene_plot_layout(**axes, y_format="$.1f\0USD")
    with pytest.raises(TypeError, match="string or None"):
        _native.scene_plot_layout(**axes, x_format=1)  # type: ignore[arg-type]


def test_scene_colorbar_side_is_framed_before_rust_resolves_gutters() -> None:
    for side, edge_offset, viewport in (("right", 64, 320.0), ("bottom", 72, 240.0)):
        figure = Figure(width=320, height=240).scatter([0.0, 1.0], [0.0, 1.0])
        figure.colorbar_options = {
            "domain": [0.0, 1.0],
            "stops": [(0.0, [0, 0, 0, 255]), (1.0, [255, 255, 255, 128])],
            "side": side,
        }
        scene = figure.to_scene()
        edge = np.frombuffer(scene[edge_offset : edge_offset + 8], dtype="<f8")[0]
        assert viewport - edge >= 42.0


def test_scene_rejects_malformed_host_arrays() -> None:
    with np.testing.assert_raises_regex(ValueError, "one record per mark"):
        _native.scene_scatter_svg(
            [1.0],
            [],
            [4.0],
            [0, 0, 0, 255],
            [0, 0, 0, 0],
            [0.0],
            [0],
        )
    with np.testing.assert_raises_regex(ValueError, "invalid canonical scatter scene"):
        _native.scene_scatter_svg(
            [np.nan],
            [1.0],
            [4.0],
            [0, 0, 0, 255],
            [0, 0, 0, 0],
            [0.0],
            [0],
        )
