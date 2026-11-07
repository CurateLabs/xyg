"""Public exact temporal catalog regressions; no host timestamp float ingress."""

import struct

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
