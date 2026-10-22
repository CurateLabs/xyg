"""The #888 evidence probe rejects shared SVG/PNG rendering errors."""

from __future__ import annotations

import io
import math
import xml.etree.ElementTree as ET

import pytest

Image = pytest.importorskip("PIL.Image")
ImageDraw = pytest.importorskip("PIL.ImageDraw")
pytest.importorskip("matplotlib")
from scripts import compare_named_colorbar_domains as probe  # noqa: E402


@pytest.mark.parametrize(
    ("corruption", "reason"),
    [
        ("missing_band", "canonical XYCB requires 10 literal bands, got 9"),
        ("uniform_paint", "band 1 paint differs from canonical XYCB stop"),
    ],
)
def test_probe_rejects_matching_but_incorrect_svg_and_png(
    tmp_path, monkeypatch, corruption, reason
):
    # Start from actual native output and canonical XYCB bytes, not a hand-built
    # palette or a mock of the new validation logic.
    original = probe.xyg_probe(probe.DOMAINS["ordinary"], tmp_path, "original")
    root = ET.fromstring((tmp_path / original["svg"]["file"]).read_text())
    bands = [node for node in root.iter() if node.get("data-xy-slot") == "colorbar_band"]
    with Image.open(tmp_path / original["png"]["file"]) as image:
        pixels = image.convert("RGBA")
    draw = ImageDraw.Draw(pixels)

    def repaint(band, rgba):
        x, y, width, height = (float(band.get(key)) for key in ("x", "y", "width", "height"))
        draw.rectangle(
            (math.floor(x), math.floor(y), math.ceil(x + width) - 1, math.ceil(y + height) - 1),
            fill=rgba,
        )

    if corruption == "missing_band":
        removed = bands.pop()
        for parent in root.iter():
            if removed in list(parent):
                parent.remove(removed)
                break
        repaint(removed, pixels.getpixel((0, 0)))
    else:
        for band in bands:
            band.set("fill", bands[0].get("fill"))
            repaint(band, tuple(original["stop_rgba"][0]))
    broken_svg = ET.tostring(root, encoding="unicode")
    stream = io.BytesIO()
    pixels.save(stream, format="PNG")

    # These corruptions satisfy the old pairwise agreement check. In particular,
    # PNG sampling alone cannot discover the omitted or incorrectly painted band.
    assert bands
    for band in bands:
        center = tuple(
            int(float(band.get(position)) + float(band.get(length)) / 2)
            for position, length in (("x", "width"), ("y", "height"))
        )
        expected_rgb = tuple(int(channel) for channel in band.get("fill")[5:-1].split(",")[:3])
        assert pixels.getpixel(center)[:3] == expected_rgb

    monkeypatch.setattr(probe._native, "scene_svg", lambda _scene: broken_svg)
    monkeypatch.setattr(
        probe._native, "scene_static_export", lambda *_args, **_kwargs: stream.getvalue()
    )
    with pytest.raises(AssertionError, match=reason):
        probe.xyg_probe(probe.DOMAINS["ordinary"], tmp_path, "corrupted")
