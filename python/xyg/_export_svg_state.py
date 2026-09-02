"""Mutable SVG document state for one static-export pass."""

from __future__ import annotations

from typing import Any, Optional

from ._export_svg_util import _num, escape
from ._paint import _css


class _Svg:
    """One export pass: collects defs + body elements, then assembles."""

    def __init__(self, id_prefix: str = "") -> None:
        self.defs: list[str] = []
        self.body: list[str] = []
        self._uid = 0
        # Composed documents (facet grids) nest several exports into one SVG;
        # the prefix keeps ids unique so url(#...) refs stay panel-local.
        self._id_prefix = id_prefix

    def uid(self, prefix: str) -> str:
        self._uid += 1
        return f"{self._id_prefix}{prefix}{self._uid}"

    def gradient(self, fill: dict[str, Any], mark_color: str, plot: Optional[dict] = None) -> str:
        """Register a <linearGradient> for a validated fill spec; returns url(#id).

        Mark space maps to each element's bounding box (exact for bars/rects;
        the area approximation is documented). Plot space maps to the plot rect.
        """
        gid = self.uid("g")
        direction = fill.get("dir", "down")
        # Gradient line start/end per CSS: "down" starts at the top.
        ends = {
            "down": (0, 0, 0, 1),
            "up": (0, 1, 0, 0),
            "right": (0, 0, 1, 0),
            "left": (1, 0, 0, 0),
        }[direction if direction in ("down", "up", "left", "right") else "down"]
        if fill.get("space") == "plot" and plot:
            x0 = plot["x"] + ends[0] * plot["w"]
            y0 = plot["y"] + ends[1] * plot["h"]
            x1 = plot["x"] + ends[2] * plot["w"]
            y1 = plot["y"] + ends[3] * plot["h"]
            units = f'gradientUnits="userSpaceOnUse" x1="{_num(x0)}" y1="{_num(y0)}" x2="{_num(x1)}" y2="{_num(y1)}"'
        else:
            units = f'x1="{ends[0]}" y1="{ends[1]}" x2="{ends[2]}" y2="{ends[3]}"'
        raw_stops = fill.get("stops", [])
        resolved = [_css(c, mark_color) for _t, c in raw_stops]
        stops_out: list[str] = []
        for index, ((t, raw_color), color) in enumerate(zip(raw_stops, resolved, strict=True)):
            offset = _num(t * 100)
            if str(raw_color).strip().lower() != "transparent":
                escaped = escape(color, {chr(34): "&quot;"})
                stops_out.append(f'<stop offset="{offset}%" stop-color="{escaped}"/>')
                continue

            # SVG interpolates stop RGB independently from stop opacity. A
            # literal `transparent` stop is transparent black, which makes a
            # colored fade pass through a muddy gray fringe. Give the zero-
            # opacity stop the adjacent visible hue instead, matching the
            # browser renderer's premultiplied-alpha interpolation. When a
            # transparent stop sits between two different colors, duplicate
            # it at the same offset; the invisible color switch preserves the
            # hue on both segments.
            previous = next(
                (
                    resolved[i]
                    for i in range(index - 1, -1, -1)
                    if str(raw_stops[i][1]).strip().lower() != "transparent"
                ),
                None,
            )
            following = next(
                (
                    resolved[i]
                    for i in range(index + 1, len(raw_stops))
                    if str(raw_stops[i][1]).strip().lower() != "transparent"
                ),
                None,
            )
            transparent_colors = [previous or following or mark_color]
            if previous and following and previous != following:
                transparent_colors.append(following)
            for transparent_color in transparent_colors:
                escaped = escape(transparent_color, {chr(34): "&quot;"})
                stops_out.append(
                    f'<stop offset="{offset}%" stop-color="{escaped}" stop-opacity="0"/>'
                )
        stops = "".join(stops_out)
        self.defs.append(f'<linearGradient id="{gid}" {units}>{stops}</linearGradient>')
        return f"url(#{gid})"

    def gradient_vector(
        self, x0: float, y0: float, x1: float, y1: float, stops: list[tuple[float, str, float]]
    ) -> str:
        """Register a two-point <linearGradient> in user space; returns url(#id).

        `gradient()` above is closed over four axis-aligned directions, which is
        the right vocabulary for a bar or an area but cannot express a ribbon's
        gradient — that one runs along the flow, from one face to the other, and
        every band in a diagram has its own. Hence an explicit endpoint pair.
        Each stop is ``(offset, color, opacity)``: per-stop opacity is how the
        alpha channel interpolates along the vector, exactly as the raster's
        RGBA stops and the client's `mix` do. `userSpaceOnUse` and
        `stop-opacity` are both in the PDF converter's allowlist, so this
        survives PDF export unchanged.
        """
        gid = self.uid("g")
        units = (
            f'gradientUnits="userSpaceOnUse" x1="{_num(x0)}" y1="{_num(y0)}" '
            f'x2="{_num(x1)}" y2="{_num(y1)}"'
        )
        parts = []
        for offset, color, opacity in stops:
            escaped = escape(color, {chr(34): "&quot;"})
            alpha = f' stop-opacity="{_num(opacity)}"' if opacity < 1 else ""
            parts.append(f'<stop offset="{_num(offset * 100)}%" stop-color="{escaped}"{alpha}/>')
        self.defs.append(f'<linearGradient id="{gid}" {units}>{"".join(parts)}</linearGradient>')
        return f"url(#{gid})"
