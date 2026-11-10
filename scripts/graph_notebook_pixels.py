"""Small-fixture mark oracle using canonical native positions and public ranges.

This is a test witness, not a renderer. It projects the four connected property
nodes with an independent linear formula and checks their screenshot regions.
It makes no shape, full-image antialiasing, performance or scale claim.
"""

from __future__ import annotations

import io
import math
from statistics import median

from PIL import Image


def mark_witness(raw, positions, ranges):
    with Image.open(io.BytesIO(raw)) as image:
        if image.format != "PNG" or image.width * image.height > 4_194_304:
            raise ValueError("invalid mark screenshot")
        image = image.convert("RGB")
    x0, x1 = ranges["x"]
    y0, y1 = ranges["y"]
    if (
        not all(type(value) in (int, float) and math.isfinite(value) for value in (x0, x1, y0, y1))
        or x0 == x1
        or y0 == y1
    ):
        raise ValueError("finite nondegenerate linear view ranges required")
    if len(positions["x"]) != 5 or len(positions["y"]) != 5:
        raise ValueError("canonical five-node fixture required")
    witnesses = []
    for index in range(4):
        x, y = positions["x"][index], positions["y"][index]
        if not all(type(value) in (int, float) and math.isfinite(value) for value in (x, y)):
            raise ValueError("finite native source position required")
        px = (x - x0) / (x1 - x0) * image.width
        py = (y1 - y) / (y1 - y0) * image.height
        if not 13 <= px < image.width - 13 or not 13 <= py < image.height - 13:
            raise ValueError("connected canonical point is outside the admitted pixel region")
        cx, cy = round(px), round(py)
        ambient = [
            image.getpixel((cx + dx, cy + dy))
            for dx, dy in [
                (-12, -12),
                (0, -12),
                (12, -12),
                (-12, 0),
                (12, 0),
                (-12, 12),
                (0, 12),
                (12, 12),
            ]
        ]
        background = [median(row[channel] for row in ambient) for channel in range(3)]
        contrast = [
            max(abs(color[channel] - background[channel]) for channel in range(3))
            for color in [
                image.getpixel((cx + dx, cy + dy)) for dx in range(-2, 3) for dy in range(-2, 3)
            ]
        ]
        covered = sum(value >= 12 for value in contrast)
        if covered < 4:
            raise ValueError(f"missing rendered mark at canonical connected node {index}")
        witnesses.append(
            {
                "index": index,
                "pixel": [px, py],
                "background": background,
                "contrastingPixels": covered,
            }
        )
    return witnesses
