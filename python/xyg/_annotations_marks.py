"""Annotation builders mixin fragments."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ._figure import Figure  # noqa: F401
    from ._hosts import FigureHost as _Host
else:
    _Host = object


class AnnotationsMarksMixin(_Host):
    def text(
        self: "Figure",
        x: Any,
        y: Any,
        text: str,
        *,
        dx: float = 6.0,
        dy: float = -6.0,
        wrap: float | None = None,
        color: Optional[str] = None,
        anchor: str = "start",
        rotation: float | None = None,
        class_name: Optional[str] = None,
        style: Optional[dict[str, Any]] = None,
    ) -> "Figure":
        """Add a text annotation anchored at a data coordinate."""
        text = self._required_text(text, "text annotation text")
        dx = self._finite_scalar(dx, "text annotation dx")
        dy = self._finite_scalar(dy, "text annotation dy")
        if anchor not in {"start", "middle", "end"}:
            raise ValueError("text annotation anchor must be 'start', 'middle', or 'end'")
        packed_style = dict(self._style_mapping(style or {}, "text annotation style"))
        color_css = self._optional_css_color(color, "text annotation color")
        if color_css is not None:
            packed_style["color"] = color_css
        self.annotations.append(
            {
                "kind": "text",
                "x": x,
                "y": y,
                "text": text,
                "dx": dx,
                "dy": dy,
                "anchor": anchor,
                **(
                    {"wrap": self._finite_scalar(wrap, "text annotation wrap")}
                    if wrap is not None
                    else {}
                ),
                **(
                    {"rotation": self._finite_scalar(rotation, "text annotation rotation")}
                    if rotation is not None
                    else {}
                ),
                "style": packed_style,
                "class_name": self._optional_text(class_name, "text annotation class_name"),
            }
        )
        return self

    def label(
        self: "Figure",
        x: Any,
        y: Any,
        text: str,
        *,
        dx: float = 6.0,
        dy: float = -6.0,
        color: Optional[str] = None,
        anchor: str = "start",
        rotation: float | None = None,
        class_name: Optional[str] = None,
        style: Optional[dict[str, Any]] = None,
    ) -> "Figure":
        """Alias for a positioned text annotation."""
        return self.text(
            x,
            y,
            text,
            dx=dx,
            dy=dy,
            color=color,
            anchor=anchor,
            rotation=rotation,
            class_name=class_name,
            style=style,
        )

    def marker(
        self: "Figure",
        x: Any,
        y: Any,
        *,
        text: Optional[str] = None,
        color: Optional[str] = "#2563eb",
        size: float = 8.0,
        symbol: str = "circle",
        stroke_color: Optional[str] = "#ffffff",
        stroke_width: float = 1.5,
        opacity: float = 1.0,
        dx: float = 8.0,
        dy: float = -8.0,
        anchor: str = "start",
        rotation: float | None = None,
        class_name: Optional[str] = None,
        style: Optional[dict[str, Any]] = None,
    ) -> "Figure":
        """Add a point marker annotation with an optional label."""
        size = self._positive_scalar(size, "marker size")
        stroke_width = self._nonnegative_scalar(stroke_width, "marker stroke_width")
        opacity = self._opacity(opacity, "marker opacity")
        dx = self._finite_scalar(dx, "marker dx")
        dy = self._finite_scalar(dy, "marker dy")
        symbol = self._annotation_symbol(symbol, "marker symbol")
        anchor = self._annotation_anchor(anchor, "marker anchor")
        packed_style = dict(self._style_mapping(style or {}, "marker style"))
        for key in ("color", "stroke_color"):
            if packed_style.get(key) is None:
                packed_style.pop(key, None)
        color_css = self._optional_css_color(color, "marker color")
        if color_css is not None:
            packed_style.setdefault("color", color_css)
        stroke_css = self._optional_css_color(stroke_color, "marker stroke_color")
        if stroke_css is not None:
            packed_style.setdefault("stroke_color", stroke_css)
        packed_style.setdefault("stroke_width", stroke_width)
        packed_style.setdefault("opacity", opacity)
        self.annotations.append(
            {
                "kind": "marker",
                "x": x,
                "y": y,
                "text": self._optional_text(text, "marker text"),
                "dx": dx,
                "dy": dy,
                "anchor": anchor,
                "size": size,
                "symbol": symbol,
                **(
                    {"rotation": self._finite_scalar(rotation, "marker annotation rotation")}
                    if rotation is not None
                    else {}
                ),
                "style": packed_style,
                "class_name": self._optional_text(class_name, "marker class_name"),
            }
        )
        return self

    def arrow(
        self: "Figure",
        x0: Any,
        y0: Any,
        x1: Any,
        y1: Any,
        *,
        text: Optional[str] = None,
        color: Optional[str] = "#667085",
        width: float = 1.5,
        opacity: float = 1.0,
        class_name: Optional[str] = None,
        style: Optional[dict[str, Any]] = None,
    ) -> "Figure":
        """Add an arrow annotation from (`x0`, `y0`) to (`x1`, `y1`)."""
        width = self._positive_scalar(width, "arrow width")
        opacity = self._opacity(opacity, "arrow opacity")
        self.annotations.append(
            {
                "kind": "arrow",
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "text": self._optional_text(text, "arrow text"),
                "style": {
                    "color": self._optional_css_color(color, "arrow color"),
                    "width": width,
                    "opacity": opacity,
                    **self._style_mapping(style or {}, "arrow style"),
                },
                "class_name": self._optional_text(class_name, "arrow class_name"),
            }
        )
        return self

    def callout(
        self: "Figure",
        x: Any,
        y: Any,
        text: str,
        *,
        dx: float = 36.0,
        dy: float = -30.0,
        wrap: float | None = None,
        color: Optional[str] = "#344054",
        width: float = 1.5,
        opacity: float = 1.0,
        anchor: str = "start",
        class_name: Optional[str] = None,
        style: Optional[dict[str, Any]] = None,
    ) -> "Figure":
        """Add a text callout offset from a data coordinate with a pointer arrow."""
        text = self._required_text(text, "callout text")
        dx = self._finite_scalar(dx, "callout dx")
        dy = self._finite_scalar(dy, "callout dy")
        width = self._positive_scalar(width, "callout width")
        opacity = self._opacity(opacity, "callout opacity")
        if anchor not in {"start", "middle", "end"}:
            raise ValueError("callout anchor must be 'start', 'middle', or 'end'")
        self.annotations.append(
            {
                "kind": "callout",
                "x": x,
                "y": y,
                "text": text,
                "dx": dx,
                "dy": dy,
                "anchor": anchor,
                **({"wrap": self._finite_scalar(wrap, "callout wrap")} if wrap is not None else {}),
                "style": {
                    "color": self._optional_css_color(color, "callout color"),
                    **({} if wrap is not None else {"width": width}),
                    "opacity": opacity,
                    **self._style_mapping(style or {}, "callout style"),
                },
                "class_name": self._optional_text(class_name, "callout class_name"),
            }
        )
        return self
