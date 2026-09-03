"""Annotation builders mixin fragments."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ._figure import Figure  # noqa: F401
    from ._hosts import FigureHost as _Host
else:
    _Host = object


class AnnotationsRulesMixin(_Host):
    def vline(
        self: "Figure",
        x: Any,
        *,
        text: Optional[str] = None,
        color: Optional[str] = "#667085",
        width: float = 1.5,
        opacity: float = 1.0,
        class_name: Optional[str] = None,
        style: Optional[dict[str, Any]] = None,
    ) -> "Figure":
        """Add a vertical rule annotation at data coordinate `x`.

        Rules live in the chart chrome layer: they stay crisp during pan/zoom
        and annotate the current plot without adding a data trace or legend row.
        """
        return self._append_rule_annotation(
            "x",
            x,
            text=text,
            color=color,
            width=width,
            opacity=opacity,
            class_name=class_name,
            style=style,
        )

    def hline(
        self: "Figure",
        y: Any,
        *,
        text: Optional[str] = None,
        color: Optional[str] = "#667085",
        width: float = 1.5,
        opacity: float = 1.0,
        class_name: Optional[str] = None,
        style: Optional[dict[str, Any]] = None,
    ) -> "Figure":
        """Add a horizontal rule annotation at data coordinate `y`."""
        return self._append_rule_annotation(
            "y",
            y,
            text=text,
            color=color,
            width=width,
            opacity=opacity,
            class_name=class_name,
            style=style,
        )

    def threshold(
        self: "Figure",
        value: Any,
        *,
        axis: str = "y",
        text: Optional[str] = None,
        color: Optional[str] = "#e11d48",
        width: float = 1.5,
        opacity: float = 1.0,
        class_name: Optional[str] = None,
        style: Optional[dict[str, Any]] = None,
    ) -> "Figure":
        """Add a semantic threshold rule on the x or y axis."""
        axis = self._annotation_axis(axis, "threshold axis")
        if axis == "x":
            return self.vline(
                value,
                text=text,
                color=color,
                width=width,
                opacity=opacity,
                class_name=class_name,
                style=style,
            )
        return self.hline(
            value,
            text=text,
            color=color,
            width=width,
            opacity=opacity,
            class_name=class_name,
            style=style,
        )

    def x_band(
        self: "Figure",
        x0: Any,
        x1: Any,
        *,
        text: Optional[str] = None,
        color: Optional[str] = "#64748b",
        opacity: float = 0.14,
        class_name: Optional[str] = None,
        style: Optional[dict[str, Any]] = None,
    ) -> "Figure":
        """Add a vertical span annotation from `x0` to `x1`."""
        return self._append_band_annotation(
            "x",
            x0,
            x1,
            text=text,
            color=color,
            opacity=opacity,
            class_name=class_name,
            style=style,
        )

    def y_band(
        self: "Figure",
        y0: Any,
        y1: Any,
        *,
        text: Optional[str] = None,
        color: Optional[str] = "#64748b",
        opacity: float = 0.14,
        class_name: Optional[str] = None,
        style: Optional[dict[str, Any]] = None,
    ) -> "Figure":
        """Add a horizontal span annotation from `y0` to `y1`."""
        return self._append_band_annotation(
            "y",
            y0,
            y1,
            text=text,
            color=color,
            opacity=opacity,
            class_name=class_name,
            style=style,
        )

    def threshold_zone(
        self: "Figure",
        start: Any,
        end: Any,
        *,
        axis: str = "y",
        text: Optional[str] = None,
        color: Optional[str] = "#e11d48",
        opacity: float = 0.12,
        class_name: Optional[str] = None,
        style: Optional[dict[str, Any]] = None,
    ) -> "Figure":
        """Add a semantic threshold band on the x or y axis."""
        axis = self._annotation_axis(axis, "threshold_zone axis")
        if axis == "x":
            return self.x_band(
                start,
                end,
                text=text,
                color=color,
                opacity=opacity,
                class_name=class_name,
                style=style,
            )
        return self.y_band(
            start,
            end,
            text=text,
            color=color,
            opacity=opacity,
            class_name=class_name,
            style=style,
        )

    def _append_rule_annotation(
        self: "Figure",
        axis: str,
        value: Any,
        *,
        text: Optional[str],
        color: Optional[str],
        width: float,
        opacity: float,
        class_name: Optional[str],
        style: Optional[dict[str, Any]],
    ) -> "Figure":
        width = self._positive_scalar(width, f"{axis} rule width")
        opacity = self._opacity(opacity, f"{axis} rule opacity")
        self.annotations.append(
            {
                "kind": "rule",
                "axis": axis,
                "value": value,
                "text": self._optional_text(text, f"{axis} rule text"),
                "style": {
                    "color": self._optional_css_color(color, f"{axis} rule color"),
                    "width": width,
                    "opacity": opacity,
                    **self._style_mapping(style or {}, f"{axis} rule style"),
                },
                "class_name": self._optional_text(class_name, f"{axis} rule class_name"),
            }
        )
        return self

    def _append_band_annotation(
        self: "Figure",
        axis: str,
        start: Any,
        end: Any,
        *,
        text: Optional[str],
        color: Optional[str],
        opacity: float,
        class_name: Optional[str],
        style: Optional[dict[str, Any]],
    ) -> "Figure":
        opacity = self._opacity(opacity, f"{axis} band opacity")
        self.annotations.append(
            {
                "kind": "band",
                "axis": axis,
                "start": start,
                "end": end,
                "text": self._optional_text(text, f"{axis} band text"),
                "style": {
                    "color": self._optional_css_color(color, f"{axis} band color"),
                    "opacity": opacity,
                    **self._style_mapping(style or {}, f"{axis} band style"),
                },
                "class_name": self._optional_text(class_name, f"{axis} band class_name"),
            }
        )
        return self
