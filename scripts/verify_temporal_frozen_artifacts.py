"""Independent retained-wire/vector/pixel oracles for the real Worker fixture."""

from __future__ import annotations

import math
import struct
import sys
from pathlib import Path

from PIL import Image

from xyg._graphforge_container import decode_container


def sdf(x, y, radius, shape):
    if shape == 0:
        return math.hypot(x, y) - radius
    if shape == 1:
        return max(abs(x), abs(y)) - radius
    if shape == 2:
        return abs(x) + abs(y) - radius
    if shape == 4:
        return min(
            max(abs(x) - 0.34 * radius, abs(y) - radius),
            max(abs(x) - radius, abs(y) - 0.34 * radius),
        )
    vertices = (
        [(0, -radius), (-radius, radius), (radius, radius)]
        if shape == 3
        else [
            (
                math.cos(-math.pi / 2 + i * math.pi / 3) * radius * 2 / math.sqrt(3),
                math.sin(-math.pi / 2 + i * math.pi / 3) * radius * 2 / math.sqrt(3),
            )
            for i in range(6)
        ]
    )
    distances, signs = [], []
    for a, b in zip(vertices, vertices[1:] + vertices[:1], strict=True):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = max(0, min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy)))
        distances.append(math.hypot(x - a[0] - t * dx, y - a[1] - t * dy))
        signs.append(dx * (y - a[1]) - dy * (x - a[0]))
    return min(distances) * (-1 if all(v >= 0 for v in signs) or all(v <= 0 for v in signs) else 1)


def verify(directory: Path) -> None:
    for snapshot in sorted(directory.glob("shape-*.xyfg")):
        m = decode_container(snapshot.read_bytes()[:-8], "XYFG")
        p = decode_container(m["render.publication", 0], "XYGR")
        scene = snapshot.with_suffix(".scene").read_bytes()
        count, styles = struct.unpack_from("<QQ", scene, 16)
        table = [
            (
                scene[160 + i * 16 : 164 + i * 16],
                scene[164 + i * 16 : 168 + i * 16],
                struct.unpack_from("<d", scene, 168 + i * 16)[0],
            )
            for i in range(styles)
        ]
        rows = []
        for i in range(count):
            at = 160 + styles * 16 + i * 56
            kind, visible, symbol, tag, style, identity = struct.unpack_from("<BBBBIQ", scene, at)
            assert visible == 1 and tag == 128
            rows.append(
                (kind, symbol, identity, table[style], struct.unpack_from("<5d", scene, at + 16))
            )
        assert struct.unpack_from("<6d", scene, 32) == (240, 180, 0, 0, 240, 180)
        # Every retained arrowhead remains an independent exact triangle.
        indices = p["paint.piece.index.u64", 0]
        geometry = p["paint.piece.geometry.f64", 0]
        expected_heads = []
        expected_segments = []
        edge_styles = p["paint.edge.style.bytes", 0]
        for piece in range(len(indices) // 2):
            edge, flags = map(int, indices[piece * 2 : piece * 2 + 2])
            g = list(geometry[piece * 14 : piece * 14 + 14])
            raw_style = edge_styles[edge * 60 : edge * 60 + 60]
            if flags & 2:
                expected_heads.extend(
                    ((2 << 48) + edge, tuple(g[i : i + 2]), raw_style[36:40]) for i in (8, 10, 12)
                )
            dx, dy = g[2] - g[0], g[3] - g[1]
            length = math.hypot(dx, dy)
            # Independent integer-period intersections, including nonzero trim phase.
            on, off, phase = g[5:8]
            ranges = [(0, length)]
            if on and off:
                period = on + off
                ranges = [
                    (max(0, k * period - phase), min(length, k * period + on - phase))
                    for k in range(
                        math.floor(phase / period) - 1, math.ceil((phase + length) / period) + 1
                    )
                ]
            layers = [
                (raw_style[28:32], struct.unpack_from("<f", raw_style, 40)[0]),
                (raw_style[32:36], struct.unpack_from("<f", raw_style, 44)[0]),
                (raw_style[36:40], struct.unpack_from("<f", raw_style, 16)[0]),
            ]
            for a, b in ranges:
                if b <= a or not length:
                    continue
                for color, width in layers:
                    if color[3] and width > 0:
                        for t in (a, b):
                            expected_segments.append(
                                (
                                    (2 << 48) + edge,
                                    (g[0] + dx * t / length, g[1] + dy * t / length),
                                    color,
                                    width,
                                )
                            )
        emphasis = p["render.edge_emphasis.u8", 0]
        for piece in range(len(indices) // 2):
            edge = int(indices[piece * 2])
            if not emphasis[edge] & 1:
                continue
            g = list(geometry[piece * 14 : piece * 14 + 14])
            dx, dy = g[2] - g[0], g[3] - g[1]
            length = math.hypot(dx, dy)
            on, off, phase = g[5:8]
            ranges = [(0, length)]
            if on and off:
                period = on + off
                ranges = [
                    (max(0, k * period - phase), min(length, k * period + on - phase))
                    for k in range(
                        math.floor(phase / period) - 1, math.ceil((phase + length) / period) + 1
                    )
                ]
            for a, b in ranges:
                if b <= a or not length:
                    continue
                for sign in (-1, 1):
                    offset = (g[4] + 1) * sign
                    for t in (a, b):
                        expected_segments.append(
                            (
                                (2 << 48) + edge,
                                (
                                    g[0] + dx * t / length - dy / length * offset,
                                    g[1] + dy * t / length + dx / length * offset,
                                ),
                                bytes(m["render.focus.rgba", 0]),
                                2.0,
                            )
                        )
        heads = [(r[2], r[4][:2], r[3][0]) for r in rows if r[0] == 6 and r[2] >= 2 << 48]
        assert heads == expected_heads
        shafts = [(r[2], r[4][:2], r[3][1], r[3][2]) for r in rows if r[0] == 7]
        assert len(shafts) == len(expected_segments)
        for actual, expected in zip(shafts, expected_segments, strict=True):
            assert actual[0] == expected[0] and actual[2:] == expected[2:]
            assert math.dist(actual[1], expected[1]) < 1e-12
        # Halo centers and literal identity mapping stay exactly in CSS space.
        centers = p["paint.node.center.f64", 0]
        node_styles = p["paint.node.style.bytes", 0]
        images = []
        for scale, suffix in [(1, ""), (2, ".scale2")]:
            image = Image.open(snapshot.with_suffix(suffix + ".png")).convert("RGBA")
            offline = Image.open(snapshot.with_suffix(suffix + ".offline.png")).convert("RGB")
            assert image.size == (480 * scale, 360 * scale)
            images.append((scale, image, offline))
        for node in range(3):
            x, y = centers[node * 2 : node * 2 + 2]
            style = node_styles[node * 60 : node * 60 + 60]
            halo = [r for r in rows if r[0] == 0 and r[2] == node + 1 and r[3][0] == style[28:32]]
            assert len(halo) == 1 and halo[0][4][:2] == (x, y)
            # Interior samples avoid AA boundaries and compare independent raw paint colors.
            radius, width = struct.unpack_from("<2f", style, 12)
            radius /= 2
            shape = style[24]
            inradius = [
                radius,
                radius,
                radius / math.sqrt(2),
                radius / math.sqrt(5),
                radius * 0.34,
                radius,
            ][shape]
            if abs(inradius - width) > 0.75:
                expected = tuple(style[32:36] if inradius > width else style[36:40])
                assert expected[3] == 255
                for scale, image, offline in images:
                    assert image.getpixel((int(x * 2 * scale), int(y * 2 * scale))) == expected, (
                        snapshot.name,
                        node,
                        scale,
                        expected,
                    )
                    assert offline.getpixel((int(x * scale), int(y * scale))) == expected[:3], (
                        snapshot.name,
                        node,
                        scale,
                        expected,
                    )
        # Focus geometry has the captured paint, independent of frame-time focus.kind=0.
        focus = bytes(m["render.focus.rgba", 0])
        focus_rows = [r for r in rows if r[3][0] == focus or r[3][1] == focus]
        assert focus_rows and any(r[0] == (7 if "edge" in snapshot.stem else 6) for r in focus_rows)
        frame_rows = [r for r in rows if r[2] == 3 << 48]
        assert len(frame_rows) == (8 if "parent" in snapshot.stem else 4)
        frame_geometry = p["paint.frame.geometry.f64", 0]
        bounds = list(frame_geometry[:4])
        expected_rects = []
        for half in [frame_geometry[4]] + (
            [frame_geometry[4] + 2] if "parent" in snapshot.stem else []
        ):
            x0, y0, x1, y1 = bounds
            outer = (x0 - half, y0 - half, x1 + half, y1 + half)
            inner = (x0 + half, y0 + half, x1 - half, y1 - half)
            expected_rects.extend(
                [
                    (outer[0], outer[1], outer[2], inner[1]),
                    (outer[0], inner[3], outer[2], outer[3]),
                    (outer[0], inner[1], inner[0], inner[3]),
                    (inner[2], inner[1], outer[2], inner[3]),
                ]
            )
        assert [r[4][:4] for r in frame_rows] == expected_rects
        for row in focus_rows:
            if row[0] != 6:
                continue
            node = row[2] - 1
            style = node_styles[node * 60 : node * 60 + 60]
            size = struct.unpack_from("<f", style, 12)[0]
            x, y = centers[node * 2 : node * 2 + 2]
            value = sdf(row[4][0] - x, row[4][1] - y, size / 2, style[24])
            assert 1 - 2e-5 <= value <= 3 + 2e-5, (snapshot.name, value)
        print(
            snapshot.name,
            "exact heads/layers/positions, phase-aware vectors and interior pixels passed",
        )


if __name__ == "__main__":
    verify(Path(sys.argv[1]))
