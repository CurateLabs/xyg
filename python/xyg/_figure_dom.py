"""Figure DOM class inventory and payload dom spec assembly."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .dom import validate_dom_slots

if TYPE_CHECKING:
    pass


def dom_class_strings(self) -> list[str]:
    """Every DOM class string this figure emits, deduped in insertion order.

    Contract: this is the *complete* set of class strings that can reach
    the DOM — the chart root (``class_name``), the chrome slots
    (``class_names`` values, including component-local classes merged into
    those slots), and annotation labels (``annotation["class_name"]`` when
    the annotation has text).
    Per-trace mark ``class_name`` values are adapter-only metadata for
    canvas geometry and do not create DOM nodes. The Reflex adapter joins
    this inventory into the Tailwind scan manifest for static charts (XYBF
    payloads are opaque to Tailwind's source scan), so this method must be
    extended whenever a new DOM class-carrying surface is added.
    """
    class_strings: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        if isinstance(value, str) and value.strip() and value not in seen:
            seen.add(value)
            class_strings.append(value)

    add(self.class_name)
    for value in self.class_names.values():
        add(value)
    for annotation in self.annotations:
        if annotation.get("text"):
            add(annotation.get("class_name"))
    return class_strings


def _dom_spec(self) -> dict[str, Any]:
    dom: dict[str, Any] = {}
    class_name = self._optional_text(self.class_name, "class_name")
    if class_name:
        dom["class_name"] = class_name
    class_names = self._string_mapping(self.class_names, "class_names")
    validate_dom_slots(class_names, "class_names")
    if class_names:
        dom["class_names"] = class_names
    validate_dom_slots(self.chrome_styles, "chrome_styles")
    style = self._style_mapping(self.style, "style")
    if style:
        dom["style"] = style
    chrome_slot_styles = {
        slot: self._style_mapping(slot_style, f"chrome_styles[{slot!r}]")
        for slot, slot_style in self.chrome_styles.items()
    }
    chrome_slot_styles = {
        slot: slot_style for slot, slot_style in chrome_slot_styles.items() if slot_style
    }
    if chrome_slot_styles:
        dom["styles"] = chrome_slot_styles
    return dom
