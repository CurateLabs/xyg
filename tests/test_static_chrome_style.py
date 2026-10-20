"""Public native export of admitted chrome slot styling (#1004).

Every assertion goes through the public composition API and native export.
The Rust ``static_chrome_style`` projection owns sizes, paints and typography;
the ownership tests prove the host applies exactly what it returns.
"""

from __future__ import annotations

import hashlib
import re
import struct
import zlib
from io import BytesIO
from typing import Any

import numpy as np
import pytest

import xyg
from xyg import _native
from xyg import _static_document as sd

PIL_Image = pytest.importorskip("PIL.Image")


def _chart(
    styles: dict[str, Any] | None = None,
    *,
    root: dict[str, Any] | None = None,
    x_style: dict[str, Any] | None = None,
    y_style: dict[str, Any] | None = None,
) -> Any:
    return xyg.chart(
        xyg.line([0, 1], [0, 1], color="#ef4444", width=2),
        xyg.x_axis(domain=(0, 1), label="X", style=x_style),
        xyg.y_axis(domain=(0, 1), label="Y", style=y_style),
        styles=styles,
        style=root,
        title="Title",
        width=320,
        height=240,
    )


def _texts(svg: str) -> list[dict[str, str]]:
    """Every SVG text element's attributes plus its content."""
    found = []
    for match in re.finditer(r"<text ([^>]*)>([^<]*)</text>", svg):
        attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', match.group(1)))
        attrs["_text"] = match.group(2)
        found.append(attrs)
    return found


def _by_text(svg: str) -> dict[str, dict[str, str]]:
    return {item["_text"]: item for item in _texts(svg)}


def _pixels(data: bytes) -> np.ndarray:
    return np.asarray(PIL_Image.open(BytesIO(data)).convert("RGB")).astype(int)


def _pdf_content(pdf: bytes) -> bytes:
    objects = {
        int(m.group(1)): m.group(2)
        for m in re.finditer(rb"(\d+) 0 obj\n(.*?)\nendobj\n", pdf, re.S)
    }
    page = next(body for body in objects.values() if re.search(rb"/Type /Page(?!s)", body))
    ref = int(re.search(rb"/Contents (\d+) 0 R", page).group(1))
    rest = objects[ref].partition(b"stream\n")[2]
    return zlib.decompress(rest.rsplit(b"\nendstream", 1)[0])


TYPOGRAPHY = {
    "title": {"font-weight": "bold", "color": "#102030"},
    "axis_title": {"color": "#ff0000", "font-style": "italic", "font-size": "16px"},
    "tick_label": {"color": "#00ff00", "font-weight": "bold", "font-size": "10px"},
}


def test_reproducer_tick_label_size_reaches_svg_and_png() -> None:
    """Scenario 1: different tick-label sizes produce different native output."""
    small = _chart({"tick_label": {"font-size": "12px"}})
    large = _chart({"tick_label": {"font-size": "30px"}})
    assert (
        hashlib.sha256(small.to_svg().encode()).digest()
        != hashlib.sha256(large.to_svg().encode()).digest()
    )
    sizes = {t["font-size"] for t in _texts(large.to_svg()) if t["_text"] in {"0.0", "0.5", "1.0"}}
    assert sizes == {"30"}
    assert {t["font-size"] for t in _texts(small.to_svg()) if t["_text"] == "0.5"} == {"12"}
    assert _pixels(small.to_png()).shape == _pixels(large.to_png()).shape
    assert (_pixels(small.to_png()) != _pixels(large.to_png())).any()
    # The authored chart is not mutated by export.
    assert large.figure().chrome_styles == {"tick_label": {"font-size": "30px"}}
    assert large.to_svg() == large.to_svg()


def test_legacy_defaults_are_unchanged() -> None:
    svg = _chart().to_svg()
    assert svg == _chart({}).to_svg()
    texts = _by_text(svg)
    assert texts["Title"]["font-size"] == "14"
    assert texts["Title"]["font-weight"] == "400"
    assert texts["X"]["font-size"] == "12" and "font-style" not in texts["X"]
    assert texts["0.5"]["font-size"] == "12" and "font-weight" not in texts["0.5"]


def test_svg_carries_resolved_size_paint_weight_and_style() -> None:
    texts = _by_text(_chart(TYPOGRAPHY).to_svg())
    assert texts["Title"]["font-weight"] == "700"
    assert texts["Title"]["fill"] == "rgba(16,32,48,1.000000)"
    for axis in ("X", "Y"):
        assert texts[axis]["font-style"] == "italic"
        assert texts[axis]["fill"] == "rgba(255,0,0,1.000000)"
        assert texts[axis]["font-size"] == "16"
        assert "font-weight" not in texts[axis]
    for tick in ("0.0", "0.5", "1.0"):
        assert texts[tick]["font-weight"] == "700"
        assert texts[tick]["fill"] == "rgba(0,255,0,1.000000)"
        assert texts[tick]["font-size"] == "10"


@pytest.mark.parametrize("fmt", ["png", "jpeg", "webp"])
def test_raster_pixels_follow_resolved_text(fmt: str) -> None:
    base = _pixels(_chart().to_image(fmt))
    styled = _pixels(_chart(TYPOGRAPHY).to_image(fmt))
    assert base.shape == styled.shape
    assert (base != styled).any()


def test_png_text_paint_and_weight_decoded_pixels() -> None:
    def png(chart: Any) -> np.ndarray:
        return _pixels(chart.to_image("png", scale=1))

    def tick_row(chart: Any) -> np.ndarray:  # x tick labels
        return png(chart)[205:222, 40:320]

    green = tick_row(_chart({"tick_label": {"color": "#00ff00"}}))
    plain = tick_row(_chart())
    assert ((green[..., 1] > 200) & (green[..., 0] < 60) & (green[..., 2] < 60)).any()
    assert not ((plain[..., 1] > 200) & (plain[..., 0] < 60)).any()
    bold = tick_row(_chart({"tick_label": {"font-weight": "bold"}}))
    # Bold strokes ink strictly more of the same glyph cells.
    assert (255 - bold).sum() > (255 - plain).sum()
    italic = png(_chart({"title": {"font-style": "italic"}}))[0:24, 100:260]
    assert (italic != png(_chart())[0:24, 100:260]).any()
    title_bold = png(_chart({"title": {"font-weight": "bold"}}))[0:24, 100:260]
    assert (255 - title_bold).sum() > (255 - png(_chart())[0:24, 100:260]).sum()
    axis_red = png(_chart({"axis_title": {"color": "#ff0000"}}))[224:240, :]
    assert ((axis_red[..., 0] > 200) & (axis_red[..., 1] < 60)).any()


def test_pdf_has_searchable_text_and_font_resources() -> None:
    plain = _chart().to_image("pdf")
    styled = _chart(TYPOGRAPHY).to_image("pdf")
    content = _pdf_content(styled)
    for label in ("(Title) Tj", "(X) Tj", "(Y) Tj", "(0.5) Tj"):
        assert label.encode() in content
    assert b"/BaseFont /Helvetica-Bold" in styled  # title + tick labels
    assert b"/BaseFont /Helvetica-Oblique" in styled  # axis titles
    assert b"/BaseFont /Helvetica-Bold" not in plain
    assert b"/BaseFont /Helvetica-Oblique" not in plain
    assert b"1 0 0 rg" in content and b"0 1 0 rg" in content
    assert b"1 0 0 rg" not in _pdf_content(plain)


def test_precedence_axis_then_slot_then_root_then_default() -> None:
    chart = _chart(
        {"tick_label": {"font-size": "20px", "color": "#00ff00"}},
        root={"--chart-text": "#0000ff"},
        x_style={"tick-label-size": 9, "label-color": "#ff0000"},
    )
    texts = _by_text(chart.to_svg())
    x_ticks = [t for t in _texts(chart.to_svg()) if t["_text"] in {"0.0", "0.5", "1.0"}]
    x_sizes = {t["font-size"] for t in x_ticks if t["text-anchor"] == "middle"}
    y_sizes = {t["font-size"] for t in x_ticks if t["text-anchor"] == "end"}
    assert x_sizes == {"9"}  # axis override beats the slot
    assert y_sizes == {"20"}  # slot beats the default
    assert {t["fill"] for t in x_ticks} == {"rgba(0,255,0,1.000000)"}  # slot beats root
    assert texts["X"]["fill"] == "rgba(255,0,0,1.000000)"  # axis beats root
    assert texts["Y"]["fill"] == "rgba(0,0,255,1.000000)"  # root only
    assert texts["Title"]["fill"] == "rgba(0,0,255,1.000000)"


@pytest.mark.parametrize(
    ("styles", "reason"),
    [
        ({"tick_label": {"font-size": "2em"}}, "XYG_STATIC_UNSUPPORTED_CHROME_FONT_SIZE"),
        ({"tick_label": {"font-size": 12}}, "XYG_STATIC_UNSUPPORTED_CHROME_FONT_SIZE"),
        ({"tick_label": {"font-size": "0px"}}, "XYG_STATIC_UNSUPPORTED_CHROME_FONT_SIZE"),
        ({"title": {"font-weight": "600"}}, "XYG_STATIC_UNSUPPORTED_CHROME_FONT_WEIGHT"),
        ({"title": {"font-style": "oblique"}}, "XYG_STATIC_UNSUPPORTED_CHROME_FONT_STYLE"),
        ({"title": {"color": "var(--x)"}}, "XYG_STATIC_UNSUPPORTED_CHROME_COLOR"),
        ({"axis_title": {"color": "currentColor"}}, "XYG_STATIC_UNSUPPORTED_CHROME_COLOR"),
        ({"title": {"font-family": "Comic Sans"}}, "XYG_STATIC_UNSUPPORTED_CUSTOM_FONT"),
        ({"legend": {"font-size": "12px"}}, "XYG_STATIC_UNSUPPORTED_CHROME_STYLE"),
        ({"title": {"letter-spacing": "2px"}}, "XYG_STATIC_UNSUPPORTED_CHROME_STYLE"),
    ],
)
def test_malformed_or_browser_only_styles_fail_atomically(
    styles: dict[str, Any], reason: str
) -> None:
    chart = _chart({**TYPOGRAPHY, **styles})
    for fmt in ("svg", "png", "pdf", "jpeg", "webp"):
        with pytest.raises(sd.UnsupportedStaticExport, match=reason):
            chart.to_image(fmt)


def test_malformed_root_and_axis_facts_fail_with_stable_reasons() -> None:
    with pytest.raises(sd.UnsupportedStaticExport, match="XYG_STATIC_UNSUPPORTED_CHROME_COLOR"):
        _chart(root={"--chart-text": "var(--ink)"}).to_svg()
    with pytest.raises(sd.UnsupportedStaticExport, match="XYG_STATIC_UNSUPPORTED_CUSTOM_FONT"):
        _chart(root={"font-family": "Papyrus"}).to_svg()
    with pytest.raises(sd.UnsupportedStaticExport, match="XYG_STATIC_UNSUPPORTED_BROWSER_CSS"):
        _chart(root={"box-shadow": "none"}).to_svg()
    with pytest.raises(
        sd.UnsupportedStaticExport, match="XYG_STATIC_UNSUPPORTED_CHROME_AXIS_STYLE"
    ):
        _chart(y_style={"tick-label-size": 1e9}).to_svg()


def _xyco_override(output: bytes, **overrides: float) -> bytes:
    """Rewrite resolved XYCO sizes in place (tick/label/padding for x then y)."""
    names = ["x_tick", "x_label", "x_pad", "y_tick", "y_label", "y_pad"]
    patched = bytearray(output)
    for name, value in overrides.items():
        struct.pack_into("<d", patched, 44 + 8 * names.index(name), value)
    return bytes(patched)


def test_host_applies_exactly_the_native_projection_result(monkeypatch: Any) -> None:
    """Ownership: sizes the host did not receive from Rust cannot appear."""
    real = _native.static_chrome_style
    calls: list[bytes] = []

    def tampered(frame: bytes) -> bytes:
        calls.append(frame)
        return _xyco_override(real(frame), x_tick=7.0, y_tick=7.0)

    monkeypatch.setattr(_native, "static_chrome_style", tampered)
    svg = _chart({"tick_label": {"font-size": "30px"}}).to_svg()
    assert len(calls) == 1 and b"30px" in calls[0]
    sizes = {t["font-size"] for t in _texts(svg) if t["_text"] in {"0.0", "0.5", "1.0"}}
    assert sizes == {"7"}  # authored 30px is never re-read by the host


def test_discarding_the_native_result_loses_the_authored_style(monkeypatch: Any) -> None:
    real = _native.static_chrome_style
    authored = _chart({"tick_label": {"font-size": "30px"}, "title": {"font-weight": "bold"}})
    expected = authored.to_svg()
    default_frame = sd.resolve_chrome_style(
        has_title=True, root_style={}, chrome_styles={}, axis_options={}
    )
    assert default_frame.chrome_text is None

    # A host that ignored the projection (legacy defaults) cannot match it.
    monkeypatch.setattr(_native, "static_chrome_style", lambda frame: real(_empty_frame(frame)))
    assert authored.to_svg() != expected
    assert authored.to_svg() == _chart().to_svg()


def _empty_frame(frame: bytes) -> bytes:
    """The XYCS frame of a chart with no authored chrome style (title only)."""
    return (
        struct.pack("<4s3I", b"XYCS", 1, 1, 0)
        + struct.pack("<I", 0)  # root
        + struct.pack("<I", 0)  # slots
        + struct.pack("<4I", 0, 0, 0, 0)  # x/y style + minor
    )


def test_projection_is_called_once_per_export_with_marshaled_facts(monkeypatch: Any) -> None:
    real = _native.static_chrome_style
    frames: list[bytes] = []
    monkeypatch.setattr(
        _native, "static_chrome_style", lambda frame: (frames.append(frame), real(frame))[1]
    )
    _chart(
        TYPOGRAPHY,
        root={"--chart-text": "#0000ff"},
        x_style={"tick-label-size": 9},
    ).to_svg()
    assert len(frames) == 1
    frame = frames[0]
    assert frame[:4] == b"XYCS"
    for fact in (b"#102030", b"italic", b"--chart-text", b"tick_label_size", b"10px"):
        assert fact in frame


def _legacy_v1_document(document: bytes) -> bytes:
    """Re-lay a current document out as XYST v1 (108-byte panels, version 1)."""
    count = struct.unpack_from("<I", document, 20)[0]
    legacy = bytearray(document[:64])
    struct.pack_into("<I", legacy, 4, 1)
    tail = 64 + count * 128
    for index in range(count):
        record = bytearray(document[64 + index * 128 : 64 + (index + 1) * 128])
        struct.pack_into("<I", record, 24, struct.unpack_from("<I", record, 24)[0] & ~(1 << 15))
        legacy += record[:108]
    return bytes(legacy + document[tail:])


def test_xyst_version_bumped_and_legacy_layout_rejected_actionably() -> None:
    document = sd.figure_document(_chart(TYPOGRAPHY).figure(), width=320, height=240)
    assert struct.unpack_from("<I", document, 4)[0] == 4
    assert _native.static_document_export(document, "svg")
    # v1 (108-byte panels), v2 (uniform annotation facts) and v3 (no discrete
    # colorbar region) are all rejected.
    v2 = bytearray(document)
    struct.pack_into("<I", v2, 4, 2)
    v3 = bytearray(document)
    struct.pack_into("<I", v3, 4, 3)
    for legacy, version in (
        (_legacy_v1_document(document), 1),
        (bytes(v2), 2),
        (bytes(v3), 3),
    ):
        assert struct.unpack_from("<I", legacy, 4)[0] == version
        for fmt in ("svg", "png", "pdf", "jpeg", "webp"):
            with pytest.raises(_native.StaticDocumentRejected) as rejected:
                _native.static_document_export(legacy, fmt)
            assert rejected.value.code == "XYG_STATIC_DOCUMENT_VERSION"
            assert "re-encode" in str(rejected.value)


def test_title_style_paint_accepts_css_strings_and_rgba_only() -> None:
    def panel(paint: Any) -> bytes:
        figure = _chart().figure()
        base, _legend = sd.project_figure(figure, width=320, height=240)
        scene = base.scene
        return sd.encode(
            [sd.Panel(scene, 0, 0, 320, 240, title_style=(18.0, paint))],
            width=320,
            height=240,
        )

    expected = panel((0x65, 0x43, 0x21, 255))
    assert panel("#654321") == expected
    assert panel([0x65, 0x43, 0x21, 255]) == expected
    assert panel("#fff") == panel((255, 255, 255, 255))
    for bad in ((1, 2, 3), (1, 2, 3, 256), (1, 2, 3, True), 7, None, {"r": 1}, (1, 2, "3", 4)):
        with pytest.raises(ValueError, match="paint"):
            panel(bad)
