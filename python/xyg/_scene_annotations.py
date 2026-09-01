"""Colorbar and XYAF annotation marshal paths for Scene compile.

Hosts validate authored annotation/colorbar literals here before calling
Rust bulk packers (ABI 111 colorbar, ABI 324 XYAF). Kept separate from
``_scene_v3`` so the pack entry module stays thin.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from . import _native
from ._scene_observations import (
    _ANNOTATION_TYPOGRAPHY_STYLE_KEYS,
    UnsupportedSceneV3,
)
from .marks import _SYMBOL_CODES


def colorbar_input(figure: Any) -> bytes:
    """Frame only the small literal XYCB subset; Rust resolves all policy."""
    options = getattr(figure, "colorbar_options", None)
    if not options:
        return b""
    if not isinstance(options, dict) or set(options) - {
        "domain",
        "stops",
        "side",
        "title",
        "text_rgba",
        "ticks",
        "minor_ticks",
    }:
        raise UnsupportedSceneV3("Scene v19 colorbars require literal bounded RGBA stops")
    domain = options.get("domain")
    stops = options.get("stops")
    if not (
        isinstance(domain, (list, tuple))
        and len(domain) == 2
        and isinstance(stops, (list, tuple))
        and 2 <= len(stops) <= 16
    ):
        raise UnsupportedSceneV3(
            "Scene v19 colorbars require a two-value domain and 2-16 literal stops"
        )
    try:
        lo, hi = (float(domain[0]), float(domain[1]))
        parsed = [(float(item[0]), bytes(item[1])) for item in stops]
    except (TypeError, ValueError, IndexError):
        raise UnsupportedSceneV3(
            "Scene v19 colorbar stops are (finite value, RGBA[4]) pairs"
        ) from None
    if any(len(rgba) != 4 for _, rgba in parsed):
        raise UnsupportedSceneV3(
            "Scene v19 colorbar values must be finite and RGBA literals exactly four bytes"
        )
    horizontal = options.get("side", "right") == "bottom"
    if options.get("side", "right") not in {"right", "bottom"}:
        raise UnsupportedSceneV3("Scene v19 colorbars support only right or bottom placement")
    title = options.get("title", "")
    if not isinstance(title, str):
        raise UnsupportedSceneV3("Scene v19 colorbar title must be a string")
    title_b = title.encode("utf-8")
    try:
        text_rgba = bytes(options.get("text_rgba", (32, 32, 32, 255)))
    except (TypeError, ValueError):
        raise UnsupportedSceneV3(
            "Scene v19 colorbar text is bounded and uses literal RGBA"
        ) from None
    if len(title_b) > 4096 or len(text_rgba) != 4:
        raise UnsupportedSceneV3("Scene v19 colorbar text is bounded and uses literal RGBA")
    raw_ticks = options.get("ticks")
    if raw_ticks is None:
        ticks: list[float] = []
    elif not isinstance(raw_ticks, (list, tuple)) or len(raw_ticks) > 32:
        raise UnsupportedSceneV3("Scene v19 colorbar ticks are limited to 32 finite ordered values")
    else:
        try:
            ticks = [float(value) for value in raw_ticks]
        except (TypeError, ValueError):
            raise UnsupportedSceneV3(
                "Scene v19 colorbar ticks are limited to 32 finite ordered values"
            ) from None
    minor_ticks = options.get("minor_ticks", False)
    if not isinstance(minor_ticks, bool):
        raise UnsupportedSceneV3("Scene v19 colorbar minor_ticks must be a boolean")
    flags = int(horizontal) | (int(minor_ticks) << 2)
    stop_rgba = b"".join(rgba for _, rgba in parsed)
    try:
        return _native.scene_pack_colorbar(
            flags=flags,
            lo=lo,
            hi=hi,
            text_rgba=text_rgba,
            title=title_b,
            stop_values=[value for value, _ in parsed],
            stop_rgba=stop_rgba,
            ticks=ticks,
        )
    except ValueError as error:
        raise UnsupportedSceneV3(str(error)) from error


def annotation_allowed_style(kind: str, wrapped: bool, labelled: bool) -> set[str]:
    keys = (
        "color",
        "opacity",
        "width",
        "dash",
        "linecap",
        "stroke_color",
        "stroke_width",
        "label_color",
        "label_opacity",
        "label_background",
        "label_border_color",
        "label_border_width",
    )
    return {
        key for key in keys if _native.scene_annotation_style_admit(kind, wrapped, labelled, key)
    }


def _annotation_number(values: dict[str, Any], key: str, default: Any, label: str) -> float:
    raw = values.get(key, default)
    if (
        raw is None
        or isinstance(raw, (bool, np.bool_))
        or (isinstance(raw, str) and not raw.strip())
    ):
        raise ValueError(f"Scene v12 annotation {label} must be numeric")
    try:
        value = float(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Scene v12 annotation {label} must be numeric") from error
    return value


def _annotation_color(style: dict[str, Any], key: str, default: str, label: str) -> str:
    raw = style.get(key, default)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"Scene v12 annotation {label} must be a nonempty CSS color")
    return raw


def _xyaf_dispatch(annotation: dict[str, Any]) -> tuple[str, dict[str, Any], bool, bool, str]:
    kind = str(annotation.get("kind", ""))
    style = dict(annotation.get("style") or {})
    authored_wrap = kind in {"text", "callout"} and "wrap" in annotation
    layout_text = kind == "text" and any(
        key in annotation for key in ("dx", "dy", "anchor", "rotation")
    )
    dispatch = _native.scene_xyaf_annotation_dispatch_plan(
        kind=kind,
        authored_wrap=authored_wrap,
        layout_text=layout_text,
    )
    wrapped = bool(dispatch["wrapped"])
    labelled = annotation.get("text") not in (None, "")
    kind_label = "wrapped" if wrapped else kind
    return kind, style, wrapped, labelled, kind_label


def _validate_xyaf_annotation_style(annotation: dict[str, Any]) -> None:
    """Fail closed on style keys the Scene admit table rejects (matches legacy _pack_xyaf)."""
    kind, style, wrapped, labelled, _kind_label = _xyaf_dispatch(annotation)
    skip_style = {"markup"} | _ANNOTATION_TYPOGRAPHY_STYLE_KEYS
    if kind in {"text", "marker"}:
        skip_style = skip_style | {"rotation"}
    unsupported = sorted(
        key
        for key, value in style.items()
        if key not in skip_style
        and value is not None
        and not _native.scene_annotation_style_admit(kind, wrapped, labelled, str(key))
    )
    if unsupported:
        if wrapped:
            raise UnsupportedSceneV3(f"Scene wrapped annotations do not encode {unsupported!r}")
        if kind == "arrow":
            raise UnsupportedSceneV3(f"Scene arrow style does not encode {unsupported!r}")
        if kind == "callout":
            raise UnsupportedSceneV3(f"Scene callout style does not encode {unsupported!r}")
        if kind == "text":
            raise UnsupportedSceneV3(
                "Scene v23 text annotations support only color, opacity, label_background, and label_border_*"
            )
        raise UnsupportedSceneV3(
            f"Scene v12 {kind} annotation style does not encode {unsupported!r}"
        )


def _validate_xyaf_annotation_values(annotation: dict[str, Any]) -> None:
    """Fail closed on authored annotation geometry/style values (matches legacy _pack_xyaf)."""
    kind, style, wrapped, labelled, kind_label = _xyaf_dispatch(annotation)
    if kind == "arrow" and labelled:
        raise UnsupportedSceneV3("Scene arrows do not encode text or class_name")
    required = {
        "arrow": (
            ("x0", "arrow x0"),
            ("y0", "arrow y0"),
            ("x1", "arrow x1"),
            ("y1", "arrow y1"),
        ),
        "callout": (("x", "callout x"), ("y", "callout y")),
        "text": (("x", "text x"), ("y", "text y")),
        "rule": (("value", "rule value"),),
        "band": (("start", "band start"), ("end", "band end")),
        "marker": (("x", "marker x"), ("y", "marker y")),
    }.get(kind, ())
    if wrapped:
        required = (("x", "wrapped x"), ("y", "wrapped y"))
    for key, label in required:
        _annotation_number(annotation, key, None, label)
    for key, label in (
        ("dx", "wrapped dx" if wrapped else "callout dx"),
        ("dy", "wrapped dy" if wrapped else "callout dy"),
        ("size", "marker size"),
    ):
        if key in annotation:
            value = _annotation_number(annotation, key, None, label)
            if kind == "marker" and key == "size" and (not np.isfinite(value) or value <= 0):
                raise ValueError("Scene v12 marker annotation size must be finite and positive")
    if kind == "text" and "rotation" in annotation:
        rotation = _annotation_number(annotation, "rotation", None, "text rotation")
        if not np.isfinite(rotation):
            raise ValueError("Scene v16 text annotation rotation must be finite")
    if kind == "marker" and "rotation" in annotation:
        rotation = _annotation_number(annotation, "rotation", None, "marker rotation")
        if not np.isfinite(rotation):
            raise ValueError("Scene v16 marker annotation rotation must be finite")
    if kind in {"rule", "band"}:
        axis_name = annotation.get("axis")
        if axis_name not in {"x", "y"}:
            raise ValueError(f"Scene v12 {kind} annotation axis must be 'x' or 'y'")
    if kind == "marker" and "symbol" in annotation:
        symbol_name = annotation.get("symbol")
        if not isinstance(symbol_name, str):
            raise ValueError("Scene v12 annotation marker symbol must be a supported string name")
        if symbol_name not in _SYMBOL_CODES:
            raise UnsupportedSceneV3(f"Scene v12 does not support marker symbol {symbol_name!r}")
    if "anchor" in annotation or kind == "callout" or wrapped:
        anchor_name = annotation.get("anchor", "start")
        if anchor_name not in {"start", "middle", "end"}:
            raise UnsupportedSceneV3(
                "Scene wrapped annotation anchor must be start, middle, or end"
                if wrapped
                else "Scene callout anchor must be start, middle, or end"
            )
    for key in (
        "color",
        "stroke_color",
        "label_color",
        "label_background",
        "label_border_color",
    ):
        if key in style:
            _annotation_color(style, key, "", f"{kind_label} {key.replace('_', ' ')}")
    if "opacity" in style:
        opacity = _annotation_number(style, "opacity", None, f"{kind_label} opacity")
        if not np.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
            if kind == "arrow":
                raise ValueError("Scene arrow opacity must be in [0, 1] and width must be positive")
            if wrapped:
                raise ValueError("Scene wrapped annotation opacity must be in [0, 1]")
            if kind == "callout":
                raise ValueError(
                    "Scene callout opacity must be in [0, 1] and width must be positive"
                )
            raise ValueError(f"Scene v12 {kind} annotation opacity must be finite and in [0, 1]")
    if "width" in style:
        width = _annotation_number(style, "width", None, f"{kind_label} width")
        if kind in {"arrow", "callout"} and (not np.isfinite(width) or width <= 0):
            raise ValueError(
                "Scene arrow opacity must be in [0, 1] and width must be positive"
                if kind == "arrow"
                else "Scene callout opacity must be in [0, 1] and width must be positive"
            )
        if kind == "rule" and (not np.isfinite(width) or width <= 0):
            raise ValueError("Scene v12 rule annotation width must be finite and nonnegative")
    if "stroke_width" in style:
        stroke_width = _annotation_number(style, "stroke_width", None, f"{kind} width")
        if not np.isfinite(stroke_width) or stroke_width < 0:
            raise ValueError(f"Scene v12 {kind} annotation width must be finite and nonnegative")
    if "label_opacity" in style:
        label_opacity = _annotation_number(style, "label_opacity", None, f"{kind} label opacity")
        if not np.isfinite(label_opacity) or not 0.0 <= label_opacity <= 1.0:
            raise ValueError(
                f"Scene v16 {kind} annotation label opacity must be finite and in [0, 1]"
            )
    if "label_border_width" in style:
        border_width = _annotation_number(
            style, "label_border_width", None, f"{kind_label} label border width"
        )
        if not np.isfinite(border_width) or border_width <= 0:
            raise ValueError("Scene v23 label border width must be positive and finite")


def _raise_xyaf_bulk_error(error: _native.SceneXyafBulkPackError, annotations: list[Any]) -> None:
    code = int(error.code)
    index = int(error.index)
    annotation = annotations[index] if 0 <= index < len(annotations) else {}
    kind = str(annotation.get("kind", ""))
    if code == -3:
        raise UnsupportedSceneV3(
            f"Scene v12 annotations support rule, band, and unlabeled marker only; {kind!r} is deferred"
        )
    if code == -7:
        raise UnsupportedSceneV3("Scene arrows do not encode text or class_name")
    if code == -5:
        if kind == "callout":
            raise UnsupportedSceneV3("Scene callouts require nonempty NUL-free text")
        if kind == "text":
            raise UnsupportedSceneV3("Scene v16 text annotations require nonempty NUL-free text")
        raise UnsupportedSceneV3("Scene v16 annotation labels require nonempty NUL-free text")
    if code == -4:
        raise UnsupportedSceneV3(
            "Scene v23 text annotations support only color, opacity, label_background, and label_border_*"
            if kind == "text"
            else f"Scene v12 {kind} annotation style does not encode unsupported keys"
        )
    if code == -8:
        raise UnsupportedSceneV3("Scene v12 rule annotation dash is not a constant pattern")
    if code == -9:
        raise UnsupportedSceneV3("Scene v12 rule annotation linecap is not a Scene cap")
    if code == -10:
        symbol_name = str(annotation.get("symbol", "circle"))
        raise UnsupportedSceneV3(f"Scene v12 does not support marker symbol {symbol_name!r}")
    if code == -11:
        raise UnsupportedSceneV3("Scene callout anchor must be start, middle, or end")
    if code == -12:
        raise UnsupportedSceneV3("Scene v23 label border requires color and width")
    if code == -13:
        raise ValueError(f"Scene v12 {kind} annotation axis must be 'x' or 'y'")
    if code == -6:
        style = dict(annotation.get("style") or {})
        if "label_opacity" in style:
            raise ValueError(
                f"Scene v16 {kind} annotation label opacity must be finite and in [0, 1]"
            )
        if "opacity" in style:
            raise ValueError(f"Scene v12 {kind} annotation opacity must be finite and in [0, 1]")
        if "label_border_width" in style:
            raise ValueError("Scene v23 label border width must be positive and finite")
        if "width" in style and kind == "rule":
            raise ValueError("Scene v12 rule annotation width must be finite and nonnegative")
        raise ValueError(f"Scene v12 annotation values are invalid at index {index}")
    raise ValueError("invalid scene annotation packing")


def pack_xyaf_bulk(annotations: list[Any]) -> bytes:
    """Marshal annotations and bulk-pack XYAF via Rust (ABI 324)."""
    if not annotations:
        return b""
    normalized: list[dict[str, Any]] = []
    for annotation in annotations:
        ann = dict(annotation)
        kind = str(ann.get("kind", ""))
        style = dict(ann.get("style") or {})
        if (
            kind in {"text", "marker"}
            and "rotation" not in ann
            and style.get("rotation") is not None
        ):
            ann["rotation"] = style["rotation"]
        _validate_xyaf_annotation_style(ann)
        _validate_xyaf_annotation_values(ann)
        normalized.append(ann)
    try:
        return _native.scene_xyaf_bulk_pack(normalized)
    except _native.SceneXyafBulkPackError as error:
        _raise_xyaf_bulk_error(error, normalized)


def pack_xyaf(annotation: dict[str, Any], index: int) -> bytes:
    """Pack one authored annotation as XYAF v1 via ``xyg_scene_xyaf_bulk_pack`` (ABI 324).

    Annotation ``class_name`` is an XYFS observation (ABI 165 / #306), not an
    XYAF field. Scene SVG/raster do not encode CSS classes. Product encode
    reports ``XYG_SCENE_UNSUPPORTED_BROWSER_CSS``.
    Annotation ``collision`` is XYFS ``OBS_ANNOTATION_COLLISION`` (#307);
    Scene does not encode annotation collision. Product encode reports
    ``XYG_SCENE_UNSUPPORTED_ANNOTATION_COLLISION``.
    Annotation ``markup`` is XYFS ``OBS_ANNOTATION_MARKUP`` (#308); Scene
    owns literal text only. Product encode reports
    ``XYG_SCENE_UNSUPPORTED_ANNOTATION_MARKUP``.
    Annotation custom typography is XYFS ``OBS_CUSTOM_FONT`` (#309); Scene
    SVG/raster use the built-in default font. Product encode reports
    ``XYG_SCENE_UNSUPPORTED_CUSTOM_FONT``. Text/marker ``style.rotation``
    lifts onto the ABI 187/188 top-level rotation field.
    Annotation ``html`` is XYFS ``OBS_ANNOTATION_HTML`` (#305); Scene SVG/raster
    own literal text only. Product encode reports
    ``XYG_SCENE_UNSUPPORTED_ANNOTATION_HTML``.
    """
    annotation = dict(annotation)
    kind = annotation.get("kind")
    style = dict(annotation.get("style") or {})
    if (
        str(kind) in {"text", "marker"}
        and "rotation" not in annotation
        and style.get("rotation") is not None
    ):
        annotation["rotation"] = style["rotation"]
    try:
        return _native.scene_xyaf_bulk_pack([annotation], indices=[int(index)])
    except _native.SceneXyafBulkPackError as error:
        _raise_xyaf_bulk_error(error, [annotation])
