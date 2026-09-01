"""Shared static-export chrome slot and CSS token helpers."""

from __future__ import annotations

import re
from typing import Any, Optional

from ._paint import _css, px_size

# Light-theme chrome colors (the client derives these from currentColor).
_TEXT = "rgba(32,32,32,0.85)"
_GRID = "rgba(32,32,32,0.14)"
_AXIS = "rgba(32,32,32,0.55)"
_AXIS_GRID_DASHES = {
    "solid": None,
    "dashed": [6.0, 4.0],
    "dotted": [1.0, 3.0],
    "dashdot": [6.0, 3.0, 1.0, 3.0],
}

#: The `colorbar` slot's own font size, from its stylesheet rule in
#: `js/src/20_theme.ts`. Every writer names it so none of them inherits a
#: different one from its document root.
COLORBAR_FONT_SIZE = 10.0

#: `styles={"legend": ...}` is CSS; `xyg.legend(style=...)` reaches the writers
#: under the browser's camelCase property spelling. Same declaration, two
#: spellings — the writers key on the second, so the first is translated.
_LEGEND_SLOT_ALIASES: dict[str, str] = {
    "background-color": "background",
    "box-shadow": "boxShadow",
    "border-radius": "borderRadius",
    "row-gap": "rowGap",
}

_CSS_VAR_RE = re.compile(
    r"^var\(\s*(--[A-Za-z_][A-Za-z0-9_-]*)\s*(?:,\s*(.+))?\)$",
    re.DOTALL | re.IGNORECASE,
)
_STATIC_PAINT_KEYS = frozenset(
    {
        "axis_color",
        "background",
        "canvas_background",
        "color",
        "fill",
        "grid_color",
        "label_color",
        "line_color",
        "stroke",
        "stroke_color",
        "tick_color",
    }
)


def slot_styles(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """`styles={slot: {...}}` from the payload, normalized to kebab-case CSS."""
    raw = (spec.get("dom") or {}).get("styles") or {}
    out: dict[str, dict[str, Any]] = {}
    for slot, decls in raw.items():
        if not isinstance(decls, dict):
            continue
        out[str(slot)] = {
            (k if str(k).startswith("--") else str(k).replace("_", "-")): v
            for k, v in decls.items()
        }
    return out


def legend_options_with_slot(spec: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    """Fold chart-level legend styling into one legend's options."""
    slot = slot_styles(spec).get("legend") or {}
    token = (spec.get("dom") or {}).get("style", {}).get("--chart-legend-bg")
    own = options.get("style") or {}
    if not slot and token is None and not own:
        return options

    def canonical(style: dict[str, Any]) -> dict[str, Any]:
        return {_LEGEND_SLOT_ALIASES.get(str(key), str(key)): value for key, value in style.items()}

    folded: dict[str, Any] = {}
    if token is not None:
        folded["background"] = token
    folded.update(canonical(slot))
    folded.update(canonical(own))
    return {**options, "style": folded}


def slot_text_color(style: dict[str, Any], fallback: str) -> str:
    """A slot's resolved text paint. `fill` wins over CSS `color`."""
    for prop in ("fill", "color"):
        value = style.get(prop)
        if value is not None:
            resolved = _css(value, "")
            if resolved:
                return resolved
    return fallback


def slot_font_size(style: dict[str, Any], default: float) -> float:
    """A slot's resolved font size in px, or `default`."""
    return px_size(style.get("font-size"), default) if "font-size" in style else default


def apply_export_background(spec: dict[str, Any], background: Optional[str]) -> None:
    """Apply the unified export API's `background=` override to a payload spec."""
    if background is None:
        return
    spec["canvas_background"] = background
    dom = spec.setdefault("dom", {})
    if isinstance(dom, dict):
        style = dom.setdefault("style", {})
        if isinstance(style, dict):
            style.pop("background", None)
            style["--chart-bg"] = "transparent"


def _resolve_css_var(value: Any, variables: dict[str, Any], seen: tuple[str, ...] = ()) -> Any:
    """Resolve a complete ``var(--token[, fallback])`` static paint value."""
    if not isinstance(value, str):
        return value
    match = _CSS_VAR_RE.fullmatch(value.strip())
    if match is None:
        return value
    name, fallback = match.groups()
    if name in seen:
        return fallback.strip() if fallback is not None else value
    replacement = variables.get(name, fallback)
    if replacement is None:
        return value
    if isinstance(replacement, str):
        replacement = replacement.strip()
    return _resolve_css_var(replacement, variables, (*seen, name))


def resolve_static_css_vars(spec: dict[str, Any]) -> dict[str, Any]:
    """Resolve chart-level color tokens with a copy-on-write spec traversal."""
    dom_style = (spec.get("dom") or {}).get("style") or {}
    variables = {key: value for key, value in dom_style.items() if key.startswith("--")}

    def resolve_stops(value: Any) -> Any:
        if not isinstance(value, list):
            return value
        changed = False
        out: list[Any] = []
        for stop in value:
            if isinstance(stop, (list, tuple)) and len(stop) >= 2:
                paint = _resolve_css_var(stop[1], variables)
                if paint != stop[1]:
                    changed = True
                    copied = list(stop)
                    copied[1] = paint
                    out.append(copied if isinstance(stop, list) else tuple(copied))
                    continue
            out.append(stop)
        return out if changed else value

    def rewrite(value: Any) -> Any:
        if isinstance(value, dict):
            changed = False
            out: dict[Any, Any] = {}
            for key, item in value.items():
                if key == "stops":
                    resolved = resolve_stops(item)
                elif isinstance(item, str) and (
                    key in _STATIC_PAINT_KEYS
                    or (isinstance(key, str) and (key.startswith("--") or key.endswith("_color")))
                ):
                    resolved = _resolve_css_var(item, variables)
                else:
                    resolved = rewrite(item)
                changed = changed or resolved is not item
                out[key] = resolved
            return out if changed else value
        if isinstance(value, list):
            out = [rewrite(item) for item in value]
            return (
                out if any(new is not old for new, old in zip(out, value, strict=True)) else value
            )
        return value

    return rewrite(spec)
