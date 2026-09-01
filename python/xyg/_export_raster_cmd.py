"""Native raster display-list command buffer."""

from __future__ import annotations

import math
import struct
from collections.abc import Sequence
from typing import TYPE_CHECKING

import numpy as np

from . import _textblock
from ._paint import colormap_stops as _colormap_stops
from .config import DEFAULT_PALETTE

if TYPE_CHECKING:
    from ._layout import _PolarProjection

(
    _CLIP,
    _FILL,
    _GRAD,
    _STROKE,
    _POINT,
    _IMAGE,
    _TEXT_OP,
    _POINTS,
    _SEGMENTS,
    _RECTS,
    _TRIANGLES,
    _SMOOTH_STROKE,
    _DENSITY_IMAGE,
    _HEATMAP_IMAGE,
    _AFFINE_POINTS,
    _AFFINE_CHANNEL_POINTS,
    _STROKED_TRIANGLES,
    _STYLED_TEXT,
    _POLAR_CLIP,
) = range(19)
# Anchor-byte rotation flags — must match TEXT_ROTATED/TEXT_ROTATED_CW in
# crates/xyg-engine/src/raster.rs. CCW reads bottom-to-top (y-axis titles), CW top-to-bottom
# (right-margin titles, matplotlib rotation=270).
_TEXT_ROT_CCW = 0x80
_TEXT_ROT_CW = 0x40
_TEXT_ITALIC = 0x01
_TEXT_BOLD = 0x02
# stroke-linecap — must match CAP_* in crates/xyg-engine/src/raster.rs. XYG's default is round,
# which is the geometry the rasterizer's capsule distance field has always
# drawn. Joins are always round and carry no wire field.
_CAP_CODES = {"butt": 0, "round": 1, "square": 2}
_SYMBOLS = {
    "circle": 0,
    "square": 1,
    "diamond": 2,
    "triangle": 3,
    "cross": 4,
    "hexagon": 5,
    "pentagon": 6,
    "star": 7,
    "triangle_down": 8,
    "triangle_left": 9,
    "triangle_right": 10,
    "x": 11,
    "point": 12,
    "pixel": 13,
    "thin_diamond": 14,
    "plus_line": 15,
    "x_line": 16,
    "horizontal_line": 17,
    "vertical_line": 18,
}


# cmd.text anchor codes (must match crates/xyg-engine/src/raster.rs): start/center/end of string.
_TEXT_ANCHOR_CODES = {"start": 0, "center": 1, "end": 2}


class _Cmd:
    """Little-endian display-list writer. All coordinates/sizes are multiplied
    by `scale` on emit so a single logical layout renders at any DPI."""

    def __init__(self, scale: float) -> None:
        self.buf = bytearray()
        self.s = scale

    def _f(self, v: float) -> None:
        self.buf += struct.pack("<f", v * self.s)

    def _raw_f(self, v: float) -> None:
        self.buf += struct.pack("<f", v)

    def _raw_d(self, v: float) -> None:
        self.buf += struct.pack("<d", v)

    def _u32(self, v: int) -> None:
        self.buf += struct.pack("<I", v)

    def _u64(self, v: int) -> None:
        self.buf += struct.pack("<Q", v)

    def _rgba(self, c: tuple[int, ...]) -> None:
        self.buf += bytes(c)

    def clip(self, x: float, y: float, w: float, h: float) -> None:
        self.buf.append(_CLIP)
        self._f(x)
        self._f(y)
        self._f(w)
        self._f(h)

    def polar_clip(self, polar: _PolarProjection) -> None:
        """Clip subsequent commands to one annular sector.

        Coordinates/radii follow the display list's device-scale convention;
        angles remain dimensionless. A later rectangular ``clip`` resets this
        state, matching the marks→chrome transition in ``render_raster``.
        """
        self.buf.append(_POLAR_CLIP)
        self._f(polar.cx)
        self._f(polar.cy)
        self._f(polar.inner_radius)
        self._f(polar.radius)
        self._raw_f(polar.sector_a0)
        self._raw_f(polar.sector_a1 - polar.sector_a0)

    def fill(self, pts: Sequence[tuple[float, float]], color: tuple[int, ...]) -> None:
        if len(pts) < 3:
            return
        self.buf.append(_FILL)
        self._u32(len(pts))
        for x, y in pts:
            self._f(x)
            self._f(y)
        self._rgba(color)

    def grad(
        self,
        pts: Sequence[tuple[float, float]],
        g0: tuple[float, float],
        g1: tuple[float, float],
        stops: Sequence[tuple[float, tuple[int, ...]]],
    ) -> None:
        if len(pts) < 3 or not stops:
            return
        self.buf.append(_GRAD)
        self._u32(len(pts))
        for x, y in pts:
            self._f(x)
            self._f(y)
        self._f(g0[0])
        self._f(g0[1])
        self._f(g1[0])
        self._f(g1[1])
        self._u32(len(stops))
        for off, col in stops:
            self._raw_f(off)
            self._rgba(col)

    def stroke(
        self,
        pts: np.ndarray | Sequence[tuple[float, float]],
        width: float,
        color: tuple[int, ...],
        closed: bool = False,
        dash: Sequence[float] | None = None,
        cap: str = "round",
    ) -> None:
        if len(pts) < 2 or width <= 0:
            return
        self.buf.append(_STROKE)
        self._u32(len(pts))
        if isinstance(pts, np.ndarray):
            scaled = np.asarray(pts, dtype=np.float64) * self.s
            self.buf += scaled.astype("<f4").tobytes()
        else:
            for x, y in pts:
                self._f(x)
                self._f(y)
        self._f(width)
        self._rgba(color)
        self.buf.append(1 if closed else 0)
        dash = dash or []
        self._u32(len(dash))
        for d in dash:
            self._f(d)
        self.buf.append(_CAP_CODES[cap])

    def point(
        self,
        cx: float,
        cy: float,
        r: float,
        symbol: int,
        fill: tuple[int, ...],
        sw: float,
        stroke: tuple[int, ...],
    ) -> None:
        self.buf.append(_POINT)
        self._f(cx)
        self._f(cy)
        self._f(r)
        self.buf.append(symbol)
        self._rgba(fill)
        self._f(sw)
        self._rgba(stroke)

    def points(
        self,
        cx: np.ndarray,
        cy: np.ndarray,
        r: np.ndarray,
        fills: np.ndarray,
        symbol: int,
        sw: float,
        stroke: tuple[int, ...],
    ) -> None:
        """Batched marks, struct-of-arrays: whole NumPy columns are packed in
        one shot (`cx`/`cy`/`r` arrays, `fills` as `(n, 4)` RGBA8) and the
        native side loops — pixel-identical to per-mark `point()` calls,
        without the per-point Python byte-packing that dominated PNG export."""
        n = len(cx)
        if n == 0:
            return
        self.buf.append(_POINTS)
        self._u32(n)
        self.buf.append(symbol)
        self._f(sw)
        self._rgba(stroke)
        for arr in (cx, cy, r):
            scaled = np.asarray(arr, dtype=np.float64) * self.s
            self.buf += scaled.astype("<f4").tobytes()
        self.buf += np.ascontiguousarray(fills, dtype=np.uint8).tobytes()

    def affine_points(
        self,
        x_meta: dict[str, Any],
        y_meta: dict[str, Any],
        sx: _Scale,
        sy: _Scale,
        radius: float,
        fill: tuple[int, ...],
        symbol: int,
        sw: float,
        stroke: tuple[int, ...],
    ) -> None:
        """Borrow offset-encoded f32 x/y columns and project them in Rust.

        This private static-export command is the zero-copy counterpart of
        :meth:`points` for constant-style marks on affine axes.  The native
        reader repeats the exact f64 decode/project/f32 conversion order used
        by ``_column`` + ``_Scale`` + ``points``; the general command remains
        the fallback for log axes and data-driven color/size channels.
        """
        n = int(x_meta["len"])
        if n == 0:
            return
        if int(y_meta["len"]) != n:
            raise ValueError("scatter x/y payload columns must have equal lengths")
        self.buf.append(_AFFINE_POINTS)
        self._u32(n)
        self.buf.append(symbol)
        self._f(sw)
        self._rgba(stroke)
        self._f(radius)
        self._rgba(fill)
        for meta in (x_meta, y_meta):
            self._u32(int(meta.get("span", 0)))
            self._u64(int(meta["byte_offset"]))
            self._raw_d(float(meta.get("scale") or 1.0))
            self._raw_d(float(meta.get("offset", 0.0)))
        for axis in (sx, sy):
            for value in (axis.data_lo, axis.data_hi, axis.px0, axis.px1):
                self._raw_d(float(value))
        self._raw_d(float(self.s))

    def affine_channel_points(
        self,
        x_meta: dict[str, Any],
        y_meta: dict[str, Any],
        sx: _Scale,
        sy: _Scale,
        color_channel: dict[str, Any],
        size_channel: dict[str, Any],
        fill: tuple[int, ...],
        symbol: int,
        sw: float,
        stroke: tuple[int, ...],
        columns: list[dict[str, Any]],
    ) -> None:
        """Borrow affine geometry plus data-driven color/size channels.

        Rust materializes only compact screen-space scratch arrays for the
        synchronous paint. Log axes and unsupported channel modes stay on the
        expanded ``points`` command, preserving one general fallback.
        """
        n = int(x_meta["len"])
        if n == 0:
            return
        if int(y_meta["len"]) != n:
            raise ValueError("scatter x/y payload columns must have equal lengths")

        self.buf.append(_AFFINE_CHANNEL_POINTS)
        self._u32(n)
        self.buf.append(symbol)
        self._f(sw)
        self._rgba(stroke)
        for meta in (x_meta, y_meta):
            self._u32(int(meta.get("span", 0)))
            self._u64(int(meta["byte_offset"]))
            self._raw_d(float(meta.get("scale") or 1.0))
            self._raw_d(float(meta.get("offset", 0.0)))
        for axis in (sx, sy):
            for value in (axis.data_lo, axis.data_hi, axis.px0, axis.px1):
                self._raw_d(float(value))
        self._raw_d(float(self.s))

        color_mode = color_channel.get("mode")
        encoded_color_mode = {"continuous": 1, "categorical": 2}.get(color_mode, 0)
        self.buf.append(encoded_color_mode)
        self._rgba(fill)
        if encoded_color_mode:
            meta = columns[color_channel["buf"]]
            if int(meta["len"]) != n:
                raise ValueError("scatter color payload must match geometry length")
            # Private display-list tag: categorical browser payloads may now
            # borrow lossless u8 codes, while continuous and >256-category
            # channels retain f32.  Rust consumes either without expansion.
            color_encoding = 1 if meta.get("dtype") == "u8" else 0
            if encoded_color_mode == 1 and color_encoding != 0:
                raise ValueError("continuous scatter color payload must be f32")
            self.buf.append(color_encoding)
            self._u32(int(meta.get("span", 0)))
            self._u64(int(meta["byte_offset"]))
            if encoded_color_mode == 1:
                entries = _colormap_stops(color_channel.get("colormap", "viridis"))
            else:
                # Per-index fallback for browser-only entries (shared with the
                # SVG writer and the density plane), so distinct categories do
                # not collapse onto one static fallback color.
                from . import channels as _channels

                palette = color_channel.get("palette") or DEFAULT_PALETTE
                entries = _channels.palette_rows_rgba8(palette, len(palette))[:, :3].tolist()
            self._u32(len(entries))
            self.buf += np.ascontiguousarray(entries, dtype=np.uint8).reshape(-1).tobytes()

        size_mode = size_channel.get("mode")
        self.buf.append(1 if size_mode == "continuous" else 0)
        if size_mode == "continuous":
            meta = columns[size_channel["buf"]]
            if int(meta["len"]) != n:
                raise ValueError("scatter size payload must match geometry length")
            self._u32(int(meta.get("span", 0)))
            self._u64(int(meta["byte_offset"]))
            r0, r1 = size_channel.get("range_px", [2, 18])
            self._raw_d(float(r0))
            self._raw_d(float(r1))
        else:
            self._f(float(size_channel.get("size", 4.0)) / 2)

    def segments(
        self,
        x0: np.ndarray,
        y0: np.ndarray,
        x1: np.ndarray,
        y1: np.ndarray,
        width: float,
        colors: np.ndarray,
    ) -> None:
        n = len(x0)
        if n == 0 or width <= 0:
            return
        self.buf.append(_SEGMENTS)
        self._u32(n)
        self._f(width)
        for arr in (x0, y0, x1, y1):
            scaled = np.asarray(arr, dtype=np.float64) * self.s
            self.buf += scaled.astype("<f4").tobytes()
        self.buf += np.ascontiguousarray(colors, dtype=np.uint8).tobytes()

    def rects(
        self,
        x0: np.ndarray,
        y0: np.ndarray,
        x1: np.ndarray,
        y1: np.ndarray,
        fills: np.ndarray,
    ) -> None:
        n = len(x0)
        if n == 0:
            return
        self.buf.append(_RECTS)
        self._u32(n)
        for arr in (x0, y0, x1, y1):
            scaled = np.asarray(arr, dtype=np.float64) * self.s
            self.buf += scaled.astype("<f4").tobytes()
        self.buf += np.ascontiguousarray(fills, dtype=np.uint8).tobytes()

    def triangles(
        self,
        x0: np.ndarray,
        y0: np.ndarray,
        x1: np.ndarray,
        y1: np.ndarray,
        x2: np.ndarray,
        y2: np.ndarray,
        fills: np.ndarray,
        sw: float = 0.0,
        stroke: tuple[int, ...] | None = None,
    ) -> None:
        n = len(x0)
        if n == 0:
            return
        stroked = sw > 0
        self.buf.append(_STROKED_TRIANGLES if stroked else _TRIANGLES)
        self._u32(n)
        if stroked:
            self._f(sw)
            self._rgba(stroke or (0, 0, 0, 0))
        for arr in (x0, y0, x1, y1, x2, y2):
            scaled = np.asarray(arr, dtype=np.float64) * self.s
            self.buf += scaled.astype("<f4").tobytes()
        self.buf += np.ascontiguousarray(fills, dtype=np.uint8).tobytes()

    def smooth_stroke(
        self,
        xv: np.ndarray,
        yv: np.ndarray,
        sx: _Scale,
        sy: _Scale,
        width: float,
        color: tuple[int, ...],
        dash: Sequence[float] | None = None,
        cap: str = "round",
    ) -> None:
        """Native monotone-Hermite flattening + stroke for affine axes."""
        n = len(xv)
        if n < 2 or width <= 0:
            return
        self.buf.append(_SMOOTH_STROKE)
        self._u32(n)
        for value in (
            sx.data_lo,
            sx.data_hi,
            sx.px0 * self.s,
            sx.px1 * self.s,
            sy.data_lo,
            sy.data_hi,
            sy.px0 * self.s,
            sy.px1 * self.s,
        ):
            self.buf += struct.pack("<d", value)
        self.buf += np.ascontiguousarray(xv, dtype="<f8").tobytes()
        self.buf += np.ascontiguousarray(yv, dtype="<f8").tobytes()
        self._f(width)
        self._rgba(color)
        dash = dash or []
        self._u32(len(dash))
        for value in dash:
            self._f(value)
        self.buf.append(_CAP_CODES[cap])

    def image(
        self,
        dx: float,
        dy: float,
        dw: float,
        dh: float,
        iw: int,
        ih: int,
        rgba_bytes: bytes,
        *,
        nearest: bool = False,
    ) -> None:
        self.buf.append(_IMAGE)
        self._f(dx)
        self._f(dy)
        self._f(dw)
        self._f(dh)
        self._u32(iw)
        self._u32(ih)
        self.buf.append(1 if nearest else 0)
        self.buf += rgba_bytes

    def density_image(
        self,
        dx: float,
        dy: float,
        dw: float,
        dh: float,
        iw: int,
        ih: int,
        byte_offset: int,
        maximum: float,
        stops: np.ndarray,
        opacity: float,
        *,
        span: int = 0,
    ) -> None:
        """Reference a compact log-u8 density grid in the payload data arena."""
        self.buf.append(_DENSITY_IMAGE)
        self._f(dx)
        self._f(dy)
        self._f(dw)
        self._f(dh)
        self._u32(iw)
        self._u32(ih)
        self._u32(span)
        self._u64(byte_offset)
        self._raw_d(maximum)
        self._raw_d(opacity)
        stops = np.ascontiguousarray(stops, dtype=np.uint8).reshape(-1, 3)
        self._u32(len(stops))
        self.buf += stops.tobytes()

    def heatmap_image(
        self,
        dx: float,
        dy: float,
        dw: float,
        dh: float,
        iw: int,
        ih: int,
        byte_offset: int,
        stops: np.ndarray,
        alpha: int,
        *,
        span: int = 0,
        canonical: bool = False,
        domain: tuple[float, float] = (0.0, 1.0),
    ) -> None:
        """Reference normalized f32 heatmap values in the payload data arena."""
        self.buf.append(_HEATMAP_IMAGE)
        self._f(dx)
        self._f(dy)
        self._f(dw)
        self._f(dh)
        self._u32(iw)
        self._u32(ih)
        self._u32(span)
        self._u64(byte_offset)
        self.buf.append(1 if canonical else 0)
        self._raw_d(domain[0])
        self._raw_d(domain[1])
        self.buf.append(alpha)
        stops = np.ascontiguousarray(stops, dtype=np.uint8).reshape(-1, 3)
        self._u32(len(stops))
        self.buf += stops.tobytes()

    def text(
        self,
        x: float,
        y: float,
        anchor: int,
        size: float,
        color: tuple[int, ...],
        s: str,
        *,
        angle: float = 0.0,
        italic: bool = False,
        bold: bool = False,
        italic_ranges: Sequence[tuple[int, int]] = (),
    ) -> None:
        data = str(s).encode("utf-8")
        if angle or italic or bold or italic_ranges:
            self.buf.append(_STYLED_TEXT)
            self._f(x)
            self._f(y)
            self.buf.append(anchor & 0x03)
            self._f(size)
            self._raw_f(angle)
            self.buf.append((_TEXT_ITALIC if italic else 0) | (_TEXT_BOLD if bold else 0))
            self._u32(len(italic_ranges))
            for start, end in italic_ranges:
                self._u32(start)
                self._u32(end)
            self._rgba(color)
            self._u32(len(data))
            self.buf += data
            return
        self.buf.append(_TEXT_OP)
        self._f(x)
        self._f(y)
        self.buf.append(anchor)
        self._f(size)
        self._rgba(color)
        self._u32(len(data))
        self.buf += data


def _emit_text_block(
    cmd: _Cmd,
    x: float,
    first_baseline: float,
    anchor: int,
    size: float,
    color: tuple[int, ...],
    text: object,
    *,
    angle: float = 0.0,
    italic: bool = False,
    bold: bool = False,
) -> None:
    """Emit lines using the same block geometry SVG and layout measure."""
    block = _textblock.measure(text, size)
    radians = math.radians(float(angle))
    for index, line in enumerate(block.lines):
        local_y = index * block.line_step
        line_x = x - local_y * math.sin(radians)
        line_y = first_baseline + local_y * math.cos(radians)
        args = (line_x, line_y, anchor, size, color, line)
        normalized = float(angle) % 360.0
        quarter_flag = (
            _TEXT_ROT_CW
            if abs(normalized - 90.0) < 1e-9
            else _TEXT_ROT_CCW
            if abs(normalized - 270.0) < 1e-9
            else 0
        )
        if quarter_flag and not italic and not bold:
            cmd.text(line_x, line_y, anchor | quarter_flag, size, color, line)
        elif angle or italic or bold:
            cmd.text(*args, angle=angle, italic=italic, bold=bold)
        else:
            cmd.text(*args)


def _rect_pts(x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float]]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _round_rect_pts(
    x0: float, y0: float, x1: float, y1: float, radius: float, *, steps: int = 4
) -> list[tuple[float, float]]:
    """A rounded rectangle as a closed polygon, corners arc-approximated.

    The rasterizer draws polygons, not paths, so a `boxstyle="round"` bbox is
    flattened here: `steps` segments per quarter turn is enough that a 5–8 px
    corner reads as round at export scale. Degenerate radii fall back to the
    square rect so callers never special-case it.
    """
    radius = max(0.0, min(radius, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
    if radius <= 0.0:
        return _rect_pts(x0, y0, x1, y1)
    pts: list[tuple[float, float]] = []
    # (center, start angle) per corner, walking clockwise in screen space
    # (y down) from the top-left so the winding matches _rect_pts.
    corners = (
        ((x0 + radius, y0 + radius), math.pi),
        ((x1 - radius, y0 + radius), -math.pi / 2.0),
        ((x1 - radius, y1 - radius), 0.0),
        ((x0 + radius, y1 - radius), math.pi / 2.0),
    )
    for (cx, cy), start in corners:
        for i in range(steps + 1):
            angle = start + (math.pi / 2.0) * (i / steps)
            pts.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return pts
