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


@pytest.mark.parametrize("kind", _temporal_scene.KINDS)
def test_dense_exact_public_membership_and_paint(kind):
    # Independent rational-time oracle; source identities intentionally exceed 2**53.
    count = 100_000
    rows = [(i, i + 11, i % 7 - 3, (1 << 63) + i) for i in range(count)]
    chart = xyg.temporal_chart(kind, rows, domain=(0, count), timezone="UTC", dense=True, width=900)
    meta = chart.temporal_metadata()
    assert meta[:4] == b"XYTL"
    assert struct.unpack_from("<Q", meta, 44)[0] == count
    columns = (900 - 89) // 4
    lanes = 1 if kind in ("line", "bar") else 16
    records = [struct.unpack_from("<QQQdd", meta, at) for at in range(64, len(meta), 40)]
    assert len(records) <= columns * lanes
    for key, members, _, low, high in records[:: max(1, len(records) // 7)]:
        column, lane = divmod(key, lanes)
        expected = []
        for start, end, value, identity in rows:
            if min(int((value + 3) / 6 * lanes), lanes - 1) != lane:
                continue
            if kind in ("interval", "gantt"):
                included = start * columns < (column + 1) * count and end * columns > column * count
            else:
                included = start * columns // count == column
            if included:
                expected.append(identity)
        assert members == len(expected)
        actual = []
        for offset in range(0, len(expected), 256):
            page = chart.temporal_members(meta, key, offset=offset)
            assert struct.unpack_from("<I", page, 60)[0] == len(expected)
            actual.extend(struct.unpack_from("<Q", page, at)[0] for at in range(64, len(page), 8))
        assert actual == expected
        # Mutate an actual reply while retaining the independently scanned oracle.
        # Loss, duplication and a stale foreign identity must each be detected.
        for mutated in [actual[:-1], actual + actual[:1], [0] + actual[1:]]:
            with pytest.raises(AssertionError):
                assert mutated == expected
        values = [rows[identity - (1 << 63)][2] for identity in expected]
        assert low == min(values)
        assert high == max(values)
    scene = chart.figure().to_scene()
    assert len(scene) < 2_000_000
    assert "<rect" in chart.to_svg()
    chart.temporal_viewport((1, count))
    with pytest.raises(ValueError):
        chart.temporal_members(meta, records[0][0])
    chart.temporal_dispose()
    with pytest.raises(ValueError, match="disposed"):
        chart.figure().to_scene()


def test_dense_atomic_admission_and_source_mutation():
    rows = [(i, i + 1, 1, i) for i in range(1000)]
    chart = xyg.temporal_chart("line", rows, domain=(0, 1000), timezone="UTC", dense=True)
    meta = chart.temporal_metadata()
    other = xyg.temporal_chart("line", rows[:-1], domain=(0, 1000), timezone="UTC", dense=True)
    with pytest.raises(ValueError):
        other.temporal_members(meta, 0)
    # A 1M-row source does not fit the declared 64MiB source/staging/scratch model.
    # Repeated immutable tuples bound test-side memory; duplicate validation must
    # never start because admission refuses before any source/index allocation.
    large = xyg.temporal_chart(
        "event", [rows[0]] * 1_000_000, domain=(0, 1000), timezone="UTC", dense=True
    )
    with pytest.raises(ValueError, match="rejected"):
        large.figure().to_scene()


@pytest.mark.parametrize("kind", _temporal_scene.KINDS)
def test_dense_extreme_null_empty_and_invalid(kind):
    lo, hi = -(1 << 63), (1 << 63) - 1
    rows = [(None, None, -1e308, 1), (lo, lo + 1, 0, 2), (hi - 1, hi, 1e308, (1 << 64) - 1)]
    chart = xyg.temporal_chart(kind, rows, domain=(lo, hi), timezone="UTC", dense=True)
    meta = chart.temporal_metadata()
    assert b"NaN" not in chart.to_svg().encode()
    assert struct.unpack_from("<Q", meta, 44)[0] == 3
    empty = xyg.temporal_chart(kind, [], domain=(lo, hi), timezone="UTC", dense=True)
    assert len(empty.temporal_metadata()) == 64
    assert empty.figure().to_scene()[:4] == b"XYGS"
    for invalid in [float("nan"), float("inf"), -float("inf")]:
        with pytest.raises(ValueError):
            xyg.temporal_chart(
                kind, [(0, 1, invalid, 1)], domain=(lo, hi), timezone="UTC", dense=True
            ).to_svg()
    with pytest.raises(ValueError):
        xyg.temporal_chart(
            kind, [(0, 1, 0, 1)] * 2, domain=(lo, hi), timezone="UTC", dense=True
        ).to_svg()


def test_dense_output_capacity_is_atomic():
    import ctypes

    from xyg import _native

    packet = _temporal_scene.request(
        "event",
        [(0, 1, 0, 42)],
        domain=(0, 10),
        timezone="UTC",
        precision=2,
        title="",
        width=900,
        height=420,
        cursor=0,
        color=(1, 2, 3, 255),
        stroke=(1, 2, 3, 255),
        stroke_width=1,
        dense=True,
    )
    source = ctypes.create_string_buffer(packet)
    sentinel = (ctypes.c_uint8 * 64)(*([0xA5] * 64))
    length = ctypes.c_size_t()
    status = _native._lib.xyg_temporal_scene_compile(
        source, len(packet), 64 * 1024 * 1024, sentinel, 64, ctypes.byref(length)
    )
    assert status != 0
    assert bytes(sentinel) == bytes([0xA5] * 64)
