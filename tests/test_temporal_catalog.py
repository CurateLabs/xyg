"""Public exact temporal catalog regressions; no host timestamp float ingress."""

import struct
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

import pytest

import xyg
from xyg import _temporal_scene


@pytest.mark.parametrize("kind", _temporal_scene.KINDS)
def test_public_catalog_exports(kind):
    origin = (1 << 63) - 100
    rows = [(origin + 1, origin + 4, 1, (1 << 64) - 1), (origin + 5, None, 2, 42)]
    chart = xyg.temporal_chart(kind, rows, domain=(origin, origin + 10), timezone="UTC")
    scene = chart.figure().to_scene()
    assert scene[:4] == b"XYGS"
    svg = chart.to_svg()
    assert str(origin) in svg
    assert chart.to_svg() == svg
    assert chart.to_png()[:8] == b"\x89PNG\r\n\x1a\n"
    assert "hydrateWasmPainter" in chart.to_html()
    assert rows[0][0] == origin + 1


def test_exact_packet_and_no_float_timestamps():
    packet = _temporal_scene.request(
        "event",
        [(-1, None, 2, 42)],
        domain=(-3, 3),
        timezone="UTC",
        precision=3,
        title="",
        width=900,
        height=420,
        cursor=-1,
        color=(1, 2, 3, 255),
        stroke=(1, 2, 3, 255),
        stroke_width=1,
    )
    assert struct.unpack_from("<q", packet, 131)[0] == -1
    assert struct.unpack_from("<q", packet, 32)[0] == -3
    with pytest.raises(TypeError):
        xyg.temporal_chart("event", [(1.0, None, 1, 42)], domain=(0, 3), timezone="UTC").to_svg()


@pytest.mark.parametrize(
    "rows,zone,code",
    [
        ([(2, 1, 0, 1)], "UTC", -7),
        ([(None, None, 0, 1)], "Europe/London", -12),
        ([(1, None, 0, 1), (2, None, 0, 1)], "UTC", -1),
    ],
)
def test_invalid_refused(rows, zone, code):
    with pytest.raises(ValueError, match=rf"\({code}\)"):
        xyg.temporal_chart("interval", rows, domain=(0, 10), timezone=zone).to_svg()


def test_empty_and_unbounded():
    assert "svg" in xyg.temporal_chart("event", [], domain=(-10, 10), timezone="UTC").to_svg()
    assert (
        "svg"
        in xyg.temporal_chart(
            "gantt", [(None, None, 1, 42)], domain=(-10, 10), timezone="UTC"
        ).to_svg()
    )


def test_controller_snapshot_export_is_frozen():
    with xyg.TemporalController(instance_id=46001, domain=(-10, 10)) as controller:
        chart = xyg.temporal_chart(
            "event",
            [(-1, None, 1, 42)],
            domain=(-10, 10),
            timezone="UTC",
            controller=controller,
        )
        frozen = chart.figure().to_scene()
        before = chart.to_svg()
        controller.set_cursor(3)
        assert chart.figure().to_scene() != frozen
        assert chart.to_svg() != before
        assert chart.to_svg() == chart.to_svg()
        assert chart.rows == ((-1, None, 1, 42),)


@pytest.mark.parametrize(
    "css",
    [
        "</style><script>globalThis.__cssInjected=1</script><style>",
        "< /StYlE >",
        "<!--hidden",
    ],
)
def test_temporal_html_rejects_style_breakout_before_writing(css, tmp_path):
    chart = xyg.temporal_chart("event", [(1, None, 1, 42)], domain=(0, 10), timezone="UTC")
    path = tmp_path / "temporal.html"
    with pytest.raises(ValueError, match="custom_css must not contain"):
        chart.to_html(path, custom_css=css)
    assert not path.exists()


def test_temporal_html_uses_standalone_script_and_style_safeguards(monkeypatch):
    from xyg import export

    class Scripts(HTMLParser):
        def __init__(self):
            super().__init__()
            self.count = 0

        def handle_starttag(self, tag, attrs):
            self.count += tag == "script"

    source = 'globalThis.__embedded="</script><script>globalThis.__injected=1</script>";'
    monkeypatch.setattr(export, "_bundled_js", lambda _: source)
    title = "</title><script>globalThis.__titleInjected=1</script>"
    chart = xyg.temporal_chart(
        "event", [(1, None, 1, 42)], domain=(0, 10), timezone="UTC", title=title
    )
    css = "#chart { background: #123456; }"
    html = chart.to_html(custom_css=css)
    parsed = Scripts()
    parsed.feed(html)
    assert parsed.count == 2  # Bundled code plus the ordinary painter bootstrap.
    assert export._javascript_for_inline_script(source) in html
    assert export._custom_css_block(css) in html
    assert title not in html
    assert "&lt;/title&gt;&lt;script&gt;" in html
    assert f'content="{export._standalone_csp(wasm_ticks=False, density=False)}"' in html
    with pytest.raises(TypeError, match="custom_css must be a string"):
        chart.to_html(custom_css=123)


def test_temporal_transport_budget_refuses_before_copying_rows():
    class OversizedRows:
        def __len__(self):
            return _temporal_scene.MAX_BYTES // 40 + 1

        def __iter__(self):
            raise AssertionError("over-budget rows must not be materialized")

    with pytest.raises(ValueError, match="temporal request exceeds framing budget"):
        _temporal_scene.request(
            "event",
            OversizedRows(),
            domain=(-3, 3),
            timezone="UTC",
            precision=2,
            title="",
            width=900,
            height=420,
            cursor=-1,
            color=(1, 2, 3, 255),
            stroke=(1, 2, 3, 255),
            stroke_width=1,
        )


@pytest.mark.parametrize(
    "values",
    [
        (-1e308, 0, 1e308),
        (-float.fromhex("0x1.fffffffffffffp1023"), 0, float.fromhex("0x1.fffffffffffffp1023")),
    ],
)
@pytest.mark.parametrize("kind", ["event", "scatter"])
def test_extreme_finite_values_preserve_visible_positions(values, kind):
    chart = xyg.temporal_chart(
        kind,
        [(i + 1, None, value, i + 1) for i, value in enumerate(values)],
        domain=(0, 10),
        timezone="UTC",
    )
    circles = ET.fromstring(chart.to_svg()).findall(".//{http://www.w3.org/2000/svg}circle")
    assert len(circles) == 3
    assert [float(circle.attrib["cy"]) for circle in circles] == [372, 210, 48]
    assert all(float(circle.attrib["r"]) > 0 for circle in circles)
    assert chart.to_png().startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize("constructor", [xyg.temporal_chart, xyg.TemporalChart])
def test_public_constructor_refuses_sized_overflow_before_iteration(constructor):
    class Oversized:
        def __len__(self):
            return _temporal_scene.MAX_BYTES // 40 + 1

        def __iter__(self):
            raise AssertionError("public constructor copied oversized source")

    with pytest.raises(ValueError, match="framing budget"):
        constructor("event", Oversized(), domain=(0, 10), timezone="UTC")


def test_public_constructor_bounds_unsized_and_understated_sources(monkeypatch):
    # Two rows fit exactly after the UTF-8 title; a third row is never copied.
    title = "é"
    monkeypatch.setattr(_temporal_scene, "MAX_BYTES", 128 + 3 + 2 + 2 * 40)
    rows = [[1, None, 1, 1], [2, None, 2, 2]]
    chart = xyg.temporal_chart("event", iter(rows), domain=(0, 10), timezone="UTC", title=title)
    rows[0][2] = 99
    assert chart.rows == ((1, None, 1, 1), (2, None, 2, 2))

    class NeverCopy:
        def __iter__(self):
            raise AssertionError("over-budget row was copied")

    class Understated:
        def __len__(self):
            return 1

        def __iter__(self):
            yield from rows
            yield NeverCopy()

    for source in (Understated(), (row for row in [*rows, NeverCopy()])):
        with pytest.raises(ValueError, match="framing budget"):
            xyg.temporal_chart("event", source, domain=(0, 10), timezone="UTC", title=title)
    with pytest.raises(ValueError, match="framing budget"):
        xyg.temporal_chart("event", rows, domain=(0, 10), timezone="UTC", title=title + "é")
