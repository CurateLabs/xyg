"""Annotation builders mixin fragments."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from . import channels, columns

if TYPE_CHECKING:
    from ._figure import Figure  # noqa: F401
    from ._hosts import FigureHost as _Host
else:
    _Host = object


class AnnotationsSpecMixin(_Host):
    def _annotation_specs(self) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        for i, annotation in enumerate(self.annotations):
            kind = annotation.get("kind")
            label = f"annotation[{i}]"
            if kind == "rule":
                axis = self._annotation_axis(annotation.get("axis"), f"{label}.axis")
                specs.append(
                    self._annotation_common(annotation)
                    | {
                        "kind": "rule",
                        "axis": axis,
                        "value": self._annotation_value(
                            annotation.get("value"), axis, f"{label}.value"
                        ),
                    }
                )
            elif kind == "band":
                axis = self._annotation_axis(annotation.get("axis"), f"{label}.axis")
                start = self._annotation_value(annotation.get("start"), axis, f"{label}.start")
                end = self._annotation_value(annotation.get("end"), axis, f"{label}.end")
                if end <= start:
                    raise ValueError(f"{label} end must be greater than start")
                specs.append(
                    self._annotation_common(annotation)
                    | {"kind": "band", "axis": axis, "start": start, "end": end}
                )
            elif kind == "text":
                specs.append(
                    self._annotation_common(annotation)
                    | {
                        "kind": "text",
                        "x": self._annotation_value(annotation.get("x"), "x", f"{label}.x"),
                        "y": self._annotation_value(annotation.get("y"), "y", f"{label}.y"),
                        "text": self._required_text(annotation.get("text"), f"{label}.text"),
                        "dx": self._finite_scalar(annotation.get("dx", 0.0), f"{label}.dx"),
                        "dy": self._finite_scalar(annotation.get("dy", 0.0), f"{label}.dy"),
                        "anchor": self._annotation_anchor(
                            annotation.get("anchor", "start"), f"{label}.anchor"
                        ),
                    }
                )
            elif kind == "marker":
                specs.append(
                    self._annotation_common(annotation)
                    | {
                        "kind": "marker",
                        "x": self._annotation_value(annotation.get("x"), "x", f"{label}.x"),
                        "y": self._annotation_value(annotation.get("y"), "y", f"{label}.y"),
                        "size": self._positive_scalar(annotation.get("size", 8.0), f"{label}.size"),
                        "symbol": self._annotation_symbol(
                            annotation.get("symbol", "circle"), f"{label}.symbol"
                        ),
                        "dx": self._finite_scalar(annotation.get("dx", 0.0), f"{label}.dx"),
                        "dy": self._finite_scalar(annotation.get("dy", 0.0), f"{label}.dy"),
                        "anchor": self._annotation_anchor(
                            annotation.get("anchor", "start"), f"{label}.anchor"
                        ),
                    }
                )
            elif kind == "arrow":
                specs.append(
                    self._annotation_common(annotation)
                    | {
                        "kind": "arrow",
                        "x0": self._annotation_value(annotation.get("x0"), "x", f"{label}.x0"),
                        "y0": self._annotation_value(annotation.get("y0"), "y", f"{label}.y0"),
                        "x1": self._annotation_value(annotation.get("x1"), "x", f"{label}.x1"),
                        "y1": self._annotation_value(annotation.get("y1"), "y", f"{label}.y1"),
                    }
                )
            elif kind == "callout":
                specs.append(
                    self._annotation_common(annotation)
                    | {
                        "kind": "callout",
                        "x": self._annotation_value(annotation.get("x"), "x", f"{label}.x"),
                        "y": self._annotation_value(annotation.get("y"), "y", f"{label}.y"),
                        "text": self._required_text(annotation.get("text"), f"{label}.text"),
                        "dx": self._finite_scalar(annotation.get("dx", 0.0), f"{label}.dx"),
                        "dy": self._finite_scalar(annotation.get("dy", 0.0), f"{label}.dy"),
                        "anchor": self._annotation_anchor(
                            annotation.get("anchor", "start"), f"{label}.anchor"
                        ),
                    }
                )
            else:
                raise ValueError(
                    f"{label} kind must be 'rule', 'band', 'text', 'marker', 'arrow', or 'callout'"
                )
        return specs

    def _annotation_common(self, annotation: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        text = self._optional_text(annotation.get("text"), "annotation text")
        if text is not None:
            out["text"] = text
        class_name = self._optional_text(annotation.get("class_name"), "annotation class_name")
        if class_name is not None:
            out["class_name"] = class_name
        raw_style = annotation.get("style", {})
        if not isinstance(raw_style, dict):
            raise ValueError("annotation style must be a dict[str, str | int | float]")
        raw_style = {key: value for key, value in raw_style.items() if value is not None}
        style = self._style_mapping(raw_style, "annotation style")
        if "label_opacity" in style:
            style["label_opacity"] = self._opacity(
                style["label_opacity"], "annotation style label_opacity"
            )
        if style:
            out["style"] = style
        return out

    @staticmethod
    def _annotation_axis(axis: Any, label: str) -> str:
        if axis not in {"x", "y"}:
            raise ValueError(f"{label} must be 'x' or 'y'")
        return axis

    @staticmethod
    def _annotation_anchor(anchor: Any, label: str) -> str:
        if anchor not in {"start", "middle", "end"}:
            raise ValueError(f"{label} must be 'start', 'middle', or 'end'")
        return anchor

    @staticmethod
    def _annotation_symbol(symbol: Any, label: str) -> str:
        allowed = {"circle", "square", "diamond", "cross"}
        if symbol not in allowed:
            raise ValueError(f"{label} must be one of {sorted(allowed)}")
        return symbol

    def _annotation_value(self, value: Any, axis: str, label: str) -> float:
        categories = self._axis_categories.get(axis)
        if isinstance(value, str) and categories is not None:
            normalized = channels.category_label(value)
            try:
                return float(categories.index(normalized))
            except ValueError as e:
                raise ValueError(
                    f"{label} category {value!r} is not present on the {axis}-axis"
                ) from e
        if isinstance(value, str):
            raise ValueError(
                f"{label} must be a finite coordinate; string coordinates require "
                f"a categorical {axis}-axis"
            )
        try:
            arr, _kind, _copies = columns._canonicalize([value])
        except ValueError as e:
            raise ValueError(f"{label} must be a finite coordinate") from e
        out = float(arr[0])
        if not np.isfinite(out):
            raise ValueError(f"{label} must be finite")
        return out
