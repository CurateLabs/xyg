"""Cross-cutting mark style coercion and segment trace assembly."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from . import _validate, channels, kernels, styles
from ._trace import Trace
from ._typing import ArrayLike

if TYPE_CHECKING:
    from ._figure import Figure

SYMBOL_CODES = {
    name: index
    for index, name in enumerate(
        (
            "circle",
            "square",
            "diamond",
            "triangle",
            "cross",
            "hexagon",
            "pentagon",
            "star",
            "triangle_down",
            "triangle_left",
            "triangle_right",
            "x",
            "point",
            "pixel",
            "thin_diamond",
            "plus_line",
            "x_line",
            "horizontal_line",
            "vertical_line",
        )
    )
}


def direct_style(
    value: Any,
    n: int,
    label: str,
    style_channels: dict[str, channels.StyleChannel],
    key: str,
    *,
    default: float,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    constant, channel = channels.resolve_style_channel(
        value, n, label, minimum=minimum, maximum=maximum
    )
    if channel is not None:
        style_channels[key] = channel
        # Opacity channels multiply the scalar renderer uniform; keep that
        # uniform neutral so the vector is applied exactly once. Width-like
        # channels select over their scalar fallback instead.
        return 1.0 if key == "opacity" else default
    return default if constant is None else float(constant)


def direct_symbols(value: Any, n: int, style_channels: dict[str, channels.StyleChannel]) -> str:
    if isinstance(value, str):
        return _validate.point_symbol(value, "scatter symbol")
    arr = np.asarray(value, dtype=object)
    if arr.shape != (n,):
        raise ValueError(f"scatter symbol array must have shape {(n,)}, got {arr.shape}")
    codes = np.empty(n, dtype=np.uint8)
    for index, raw in enumerate(arr):
        symbol = _validate.point_symbol(raw, f"scatter symbol[{index}]")
        codes[index] = SYMBOL_CODES[symbol]
    style_channels["symbol"] = channels.StyleChannel(codes, dtype="u8")
    return "circle"


def validated_marker_path(value: Any) -> dict[str, Any]:
    """Validate the private, bounded pyplot authored-marker contract."""
    if not isinstance(value, dict):
        raise ValueError("scatter authored marker path must be a mapping")
    contours = value.get("contours")
    if not isinstance(contours, (list, tuple)):
        raise ValueError("scatter authored marker path must have 1-32 contours")
    packed: list[float] = []
    lengths: list[int] = []
    result: list[list[float]] = []
    for index, contour in enumerate(contours):
        try:
            values = np.asarray(contour, dtype=np.float64).reshape(-1)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"scatter authored marker contour {index} must be numeric") from exc
        packed.extend(float(item) for item in values)
        lengths.append(len(values))
        result.append([float(item) for item in values])
    if not kernels.scene_marker_path_admit(packed, lengths):
        raise ValueError("scatter authored marker path is not a Scene marker path")
    return {"contours": result, "filled": bool(value.get("filled", True))}


def stroke_geometry(css: Mapping[str, Any]) -> dict[str, str]:
    """The polyline cap key from compiled CSS, omitted at its default.

    Every renderer already draws XYG's default `round`, so a spec that never
    asks for another cap stays byte-identical to one built before the property
    existed.
    """
    value = css.get("linecap")
    if value is None or value == styles.DEFAULT_LINE_CAP:
        return {}
    return {"linecap": str(value)}


def stroke_channel(
    value: Any, n: int, label: str
) -> tuple[Optional[str], Optional[channels.ColorChannel]]:
    if value is None:
        return None, None
    if isinstance(value, str):
        return _validate.css_color(value, label), None
    resolved = channels.resolve_color(value, n, default_constant="transparent")
    if resolved.mode != "direct_rgba":
        raise ValueError(f"{label} arrays must be numeric RGB/RGBA with shape ({n}, 3|4)")
    return None, resolved


def append_segment_trace(
    figure: "Figure",
    kind: str,
    x0: ArrayLike,
    x1: ArrayLike,
    y0: ArrayLike,
    y1: ArrayLike,
    *,
    name: Optional[str],
    color: Optional[str],
    opacity: Any,
    width: Any,
    role: str,
    color_ch: Optional[channels.ColorChannel] = None,
    count: Optional[int] = None,
    dash: Optional[list[float]] = None,
    extra_style: Optional[dict[str, Any]] = None,
) -> None:
    """Append a compact instanced line-segment trace.

    Error bars, stems, box whiskers, and contour isolines all have the same
    transport shape. Keeping that shape here avoids one trace/object per
    segment while allowing the browser and static exporters to share one
    renderer.
    """
    name = figure._optional_text(name, f"{kind} name")
    arrays = [
        figure._as_1d_float(v, f"{kind} {label}")
        for label, v in (("x0", x0), ("x1", x1), ("y0", y0), ("y1", y1))
    ]
    if len({len(v) for v in arrays}) != 1:
        raise ValueError(f"{kind} segment columns must have equal length")
    n = len(arrays[0])
    style_channels: dict[str, channels.StyleChannel] = {}
    opacity_value = direct_style(
        opacity,
        n,
        f"{kind} opacity",
        style_channels,
        "opacity",
        default=1.0,
        minimum=0.0,
        maximum=1.0,
    )
    width_value = direct_style(
        width,
        n,
        f"{kind} width",
        style_channels,
        "width",
        default=1.2,
        minimum=0.0,
    )
    checkpoint = figure._checkpoint()
    try:
        x0c, x1c, y0c, y1c = [figure.store.ingest(v) for v in arrays]
        figure.traces.append(
            Trace(
                id=len(figure.traces),
                kind=kind,
                # Segment payloads and autorange use the explicit endpoint
                # columns. Reuse x0/y0 for common row-count bookkeeping rather
                # than allocating, scanning, and storing two unused midpoint
                # columns for every contour/errorbar/stem trace.
                x=x0c,
                y=y0c,
                x0=x0c,
                x1=x1c,
                y0=y0c,
                y1=y1c,
                name=name,
                style={
                    "color": color,
                    "opacity": opacity_value,
                    "width": width_value,
                    "role": role,
                    **({"dash": dash} if dash else {}),
                    **(extra_style or {}),
                },
                color_ch=color_ch,
                style_channels=style_channels,
                count=count,
            )
        )
    except Exception:
        figure._rollback(checkpoint)
        raise
