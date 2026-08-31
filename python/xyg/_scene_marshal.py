"""Figure observation marshaling for scene bulk packers (ABI 321-322)."""

from __future__ import annotations

import math
import struct
from typing import Any

from xyg import _native


def xych_from_xycf(xycf: bytes) -> bytes:
    """Extract the XYCH sidecar from packed XYCF v1 (ABI 319 wire layout)."""
    if len(xycf) < 288 or xycf[:4] != b"XYCF":
        raise ValueError("invalid scene chrome facts")
    title_len = struct.unpack_from("<I", xycf, 156)[0]
    x_label_len = struct.unpack_from("<I", xycf, 160)[0]
    y_label_len = struct.unpack_from("<I", xycf, 164)[0]
    x_format_len = struct.unpack_from("<I", xycf, 168)[0]
    y_format_len = struct.unpack_from("<I", xycf, 172)[0]
    x_major_len = struct.unpack_from("<I", xycf, 176)[0]
    x_minor_len = struct.unpack_from("<I", xycf, 180)[0]
    y_major_len = struct.unpack_from("<I", xycf, 184)[0]
    y_minor_len = struct.unpack_from("<I", xycf, 188)[0]
    x_label_count = struct.unpack_from("<I", xycf, 192)[0]
    y_label_count = struct.unpack_from("<I", xycf, 196)[0]
    chrome_len = struct.unpack_from("<I", xycf, 200)[0]
    at = 288
    at += title_len + x_label_len + y_label_len + x_format_len + y_format_len
    at += (x_major_len + x_minor_len + y_major_len + y_minor_len) * 8
    for _ in range(x_label_count):
        label_len = struct.unpack_from("<I", xycf, at)[0]
        at += 4 + label_len
    for _ in range(y_label_count):
        label_len = struct.unpack_from("<I", xycf, at)[0]
        at += 4 + label_len
    chrome = xycf[at : at + chrome_len]
    if len(chrome) != chrome_len or chrome[:4] != b"XYCH":
        raise ValueError("invalid scene chrome facts")
    return chrome


def scene_chrome_style(figure: Any) -> bytes:
    """Marshal chrome observations and resolve the 200-byte Scene style via Rust."""
    xycf = pack_chrome_facts(
        figure,
        width=int(figure.width),
        height=int(figure.height),
        margins=None,
        colorbar_ok=True,
    )
    return _native.scene_resolve_chrome_style(xych_from_xycf(xycf))


def pack_chrome_facts(
    figure: Any,
    *,
    width: int,
    height: int,
    margins: tuple[float, float, float, float] | None,
    colorbar_ok: bool,
) -> bytes:
    """Marshal figure chrome observations and bulk-pack XYCF via Rust (ABI 321)."""
    from xyg._scene_v3 import _SCENE_AXIS_STYLE_KEYS, UnsupportedSceneV3, _scene_side_mask

    xa = figure.axis_options["x"]
    ya = figure.axis_options["y"]
    kind_codes = {"linear": 0, "log": 1, "symlog": 2}
    tick_kind_code = {"linear": 0, "time": 1, "category": 2}
    x_lo, x_hi = (float(v) for v in figure._range("x"))
    y_lo, y_hi = (float(v) for v in figure._range("y"))
    pad = getattr(figure, "padding", None)
    has_padding = isinstance(pad, (list, tuple)) and len(pad) == 4
    figure_style = getattr(figure, "style", None) or {}
    legend_options = dict(getattr(figure, "legend_options", None) or {})
    legend_style = dict(legend_options.get("style") or {})
    allowed_legend = {"loc", "title", "ncols", "style", "highlight", "toggle"}
    colorbar = getattr(figure, "colorbar_options", None) if colorbar_ok else None
    colorbar_payload = None
    if colorbar:
        domain = colorbar.get("domain")
        stops = colorbar.get("stops") or []
        side = colorbar.get("side", "right")
        colorbar_payload = {
            "domain_lo": float(domain[0]),
            "domain_hi": float(domain[1]),
            "stops": [(float(s[0]), bytes(s[1])) for s in stops],
            "side_bottom": side == "bottom",
            "invalid_side": side not in {"right", "bottom"},
            "minor_ticks": bool(colorbar.get("minor_ticks")),
            "title": _optional_str(colorbar.get("title")),
            "text_rgba": bytes(colorbar.get("text_rgba", (32, 32, 32, 255))),
            "ticks": None
            if colorbar.get("ticks") is None
            else [float(v) for v in colorbar["ticks"]],
        }

    def marshal_axis_style(style: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in (
            "grid_color",
            "grid_width",
            "grid_opacity",
            "axis_color",
            "axis_width",
            "tick_color",
            "tick_width",
            "tick_length",
            "tick_direction",
            "tick_label_color",
            "label_color",
        ):
            if key not in style:
                continue
            raw = style[key]
            if key in {"grid_width", "axis_width", "tick_width", "tick_length"}:
                out[f"{key}_present"] = True
                out[key] = float(raw)
            elif key == "grid_opacity":
                out["grid_opacity_present"] = True
                out["grid_opacity"] = float(raw)
            else:
                out[key] = str(raw)
        return out

    def marshal_chrome_axis(axis_id: str, options: dict[str, Any]) -> dict[str, Any]:
        style = dict(options.get("style") or {})
        minor = dict(options.get("minor_style") or {})
        for label, authored in (("style", style), ("minor_style", minor)):
            unsupported = set(authored) - _SCENE_AXIS_STYLE_KEYS
            if unsupported:
                raise UnsupportedSceneV3(
                    f"Scene v12 does not yet encode {axis_id} axis {label} keys {sorted(unsupported)!r}"
                )
        side = options.get("side", "bottom" if axis_id == "x" else "left")
        allowed = ("bottom", "top") if axis_id == "x" else ("left", "right")
        if side not in allowed:
            raise UnsupportedSceneV3(
                f"Scene v12 {axis_id} axis side must be one of {list(allowed)!r}"
            )
        side_code = 0 if side in {"bottom", "left"} else 1
        return {
            "side_code": side_code,
            "tick_sides_mask": _scene_side_mask(
                options.get("tick_sides"), "tick_sides", axis_id, allowed, side_code
            ),
            "label_sides_mask": _scene_side_mask(
                options.get("tick_label_sides"), "tick_label_sides", axis_id, allowed, side_code
            ),
            "style": marshal_axis_style(style),
            "minor_style": marshal_axis_style(minor),
        }

    return _native.scene_chrome_pack(
        width=float(width),
        height=float(height),
        show_legend=bool(getattr(figure, "show_legend", True)),
        colorbar_ok=bool(colorbar_ok and colorbar_payload is not None),
        polar=str(getattr(figure, "coords", "cartesian") or "cartesian") == "polar",
        has_margins=margins is not None,
        margins=tuple(float(v) for v in margins) if margins is not None else (0.0, 0.0, 0.0, 0.0),
        has_padding=has_padding,
        padding=tuple(float(v) for v in pad) if has_padding else (0.0, 0.0, 0.0, 0.0),
        title=str(figure.title or ""),
        x_label=str(figure.x_label or xa.get("label") or ""),
        y_label=str(figure.y_label or ya.get("label") or ""),
        x_format=_optional_str(xa.get("format")),
        y_format=_optional_str(ya.get("format")),
        x_scale_kind=kind_codes[figure._axis_scale("x")],
        y_scale_kind=kind_codes[figure._axis_scale("y")],
        x_lo=x_lo,
        x_hi=x_hi,
        x_constant=float(xa.get("constant") or 1.0),
        y_lo=y_lo,
        y_hi=y_hi,
        y_constant=float(ya.get("constant") or 1.0),
        x_nonpositive_mask=1 if xa.get("nonpositive", "clip") == "mask" else 0,
        y_nonpositive_mask=1 if ya.get("nonpositive", "clip") == "mask" else 0,
        x_tick_kind=tick_kind_code.get(figure._axis_kind("x"), 0),
        y_tick_kind=tick_kind_code.get(figure._axis_kind("y"), 0),
        x_axis=marshal_chrome_axis("x", xa),
        y_axis=marshal_chrome_axis("y", ya),
        x_major=None if xa.get("tick_values") is None else [float(v) for v in xa["tick_values"]],
        y_major=None if ya.get("tick_values") is None else [float(v) for v in ya["tick_values"]],
        x_minor=[float(v) for v in (xa.get("minor_tick_values") or ())],
        y_minor=[float(v) for v in (ya.get("minor_tick_values") or ())],
        x_tick_labels=None
        if xa.get("tick_labels") is None
        else [str(v) for v in xa["tick_labels"]],
        y_tick_labels=None
        if ya.get("tick_labels") is None
        else [str(v) for v in ya["tick_labels"]],
        x_collision={
            "strategy": _optional_str(xa.get("tick_label_strategy")),
            "collision": _optional_str(xa.get("collision")),
            "anchor": _optional_str(xa.get("tick_label_anchor")),
            "min_gap": None
            if xa.get("tick_label_min_gap") is None
            else float(xa["tick_label_min_gap"]),
            "angle": None if xa.get("tick_label_angle") is None else float(xa["tick_label_angle"]),
            "tick_kind_category": figure._axis_kind("x") == "category",
        },
        y_collision={
            "strategy": _optional_str(ya.get("tick_label_strategy")),
            "collision": _optional_str(ya.get("collision")),
            "anchor": _optional_str(ya.get("tick_label_anchor")),
            "min_gap": None
            if ya.get("tick_label_min_gap") is None
            else float(ya["tick_label_min_gap"]),
            "angle": None if ya.get("tick_label_angle") is None else float(ya["tick_label_angle"]),
            "tick_kind_category": figure._axis_kind("y") == "category",
        },
        chart_background=_optional_str(figure_style.get("background")),
        plot_background=_optional_str(figure_style.get("--chart-bg")),
        legend={
            "unsupported_keys": bool(set(legend_options) - allowed_legend),
            "toggle": "toggle" in legend_options and legend_options["toggle"] is not False,
            "highlight": "highlight" in legend_options and legend_options["highlight"] is not False,
            "loc": _optional_str(legend_options.get("loc")),
            "title": _optional_str(
                str(legend_options.get("title")).lower()
                if isinstance(legend_options.get("title"), bool)
                else legend_options.get("title")
            ),
            "ncols": int(legend_options.get("ncols") or 1),
            "unsupported_style": bool(
                set(legend_style) - {"background", "color", "font_size", "title_font_size"}
            ),
            "font_size": legend_style.get("font_size"),
            "title_font_size": legend_style.get("title_font_size"),
            "color": _optional_str(legend_style.get("color")),
            "background": _optional_str(legend_style.get("background")),
        },
        colorbar=colorbar_payload,
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _marshal_trace_obs(trace: Any, *, polar: bool) -> dict[str, Any]:
    from xyg._scene_v3 import (
        _admitted_fill_gradient,
        _admitted_fill_gradient_from_fill,
        _classify_ribbon_color2,
        _density_aggregates_color,
        _hexbin_packs_paint_plane,
        _mesh_packs_paint_plane,
        _ribbon_packs_end_paints,
        _scatter_packs_paint_plane,
        _validated_marker_path,
    )

    kind = str(getattr(trace, "kind", "") or "mark")
    style = getattr(trace, "style", None) or {}
    fill = style.get("fill")
    radius = style.get("corner_radius", 0.0)
    if isinstance(radius, (list, tuple)):
        radius_values = [float(v) for v in radius]
        radius_seq = True
    else:
        radius_values = [float(radius)]
        radius_seq = False
    marker_path = style.get("marker_path")
    marker_path_valid = False
    marker_path_filled_small = False
    if marker_path is not None and kind == "scatter":
        try:
            validated = _validated_marker_path(marker_path)
            marker_path_valid = True
            marker_path_filled_small = any(len(c) < 6 for c in validated["contours"])
        except ValueError:
            marker_path_valid = False
    return {
        "kind": kind,
        "x_axis": str(getattr(trace, "x_axis", "x") or "x"),
        "y_axis": str(getattr(trace, "y_axis", "y") or "y"),
        "hidden": bool(getattr(trace, "hidden", False)),
        "has_per_item_channels": trace.has_per_item_channels(),
        "density_aggregates_color": _density_aggregates_color(trace),
        "marker_glyph_present": style.get("marker_glyph") is not None,
        "marker_glyph": _optional_str(style.get("marker_glyph")),
        "marker_path_present": marker_path is not None,
        "marker_path_valid": marker_path_valid,
        "marker_path_filled_small": marker_path_filled_small,
        "curve_present": style.get("curve") is not None,
        "curve": _optional_str(style.get("curve")),
        "linecap_present": style.get("linecap") is not None,
        "linecap": _optional_str(style.get("linecap")),
        "dash_present": style.get("dash") is not None,
        "dash_text": _optional_str(style.get("dash"))
        if not isinstance(style.get("dash"), (list, tuple))
        else None,
        "dash_is_array": isinstance(style.get("dash"), (list, tuple)),
        "fill_present": "fill" in style,
        "fill_is_string": isinstance(fill, str),
        "fill_gradient_admitted": _admitted_fill_gradient(trace) is not None,
        "hexbin_reduce": _optional_str(style.get("reduce")),
        "heatmap_truecolor": bool(getattr(trace, "truecolor", False)),
        "heatmap_has_colormap": getattr(trace, "colormap", None) is not None,
        "heatmap_has_rgba_grid": getattr(trace, "rgba_grid", None) is not None,
        "heatmap_has_rgba": getattr(trace, "rgba", None) is not None,
        "rect_gradient_fail": isinstance(fill, dict)
        and _admitted_fill_gradient_from_fill(fill, "#3987e5") is None,
        "corner_radius_values": radius_values,
        "corner_radius_seq": radius_seq,
        "wedge_gap": float(style.get("wedge_gap", 0.0) or 0.0),
        "ribbon_color2_fail": _classify_ribbon_color2(trace) == "fail",
        "color_channel_unsupported": (
            getattr(trace, "color_ch", None) is not None
            and (trace.color_ch.mode != "constant" or trace.color_ch.constant is None)
            and not (kind == "scatter" and trace.use_density())
            and not _hexbin_packs_paint_plane(trace)
            and not _mesh_packs_paint_plane(trace)
            and not _scatter_packs_paint_plane(trace)
            and not (not polar and _ribbon_packs_end_paints(trace))
        ),
    }


def pack_figure_support(
    figure: Any,
    annotations: list[Any],
    colorbar_unsupported: bool,
) -> bytes:
    """Marshal figure support observations and materialize XYFS via Rust (ABI 322)."""
    from xyg._scene_v3 import (
        _annotation_has_custom_typography,
        _annotation_has_markup,
        _significant_scene_axis_keys,
    )

    polar = str(getattr(figure, "coords", "cartesian") or "cartesian") == "polar"
    chrome_styles = getattr(figure, "chrome_styles", None) or {}
    ann_rows = []
    for annotation in annotations:
        kind = annotation.get("kind")
        ann_rows.append(
            {
                "has_html": annotation.get("html") not in (None, ""),
                "has_collision": annotation.get("collision") not in (None, ""),
                "has_markup": _annotation_has_markup(annotation),
                "has_custom_typography": _annotation_has_custom_typography(annotation),
                "has_class_name": annotation.get("class_name") not in (None, ""),
                "kind_is_supported_text": kind in {"callout", "arrow", "text"},
                "has_text": annotation.get("text") not in (None, ""),
            }
        )
    axes = []
    for axis_id, options in figure.axis_options.items():
        axis_code = 0 if axis_id == "x" else 1 if axis_id == "y" else 255
        axes.append(
            {
                "axis_code": axis_code,
                "keys": _significant_scene_axis_keys(options, polar=polar),
                "tick_label_strategy": _optional_str(options.get("tick_label_strategy")),
                "collision": _optional_str(options.get("collision")),
            }
        )
    traces = [
        _marshal_trace_obs(trace, polar=polar) for trace in getattr(figure, "traces", None) or []
    ]
    return _native.scene_figure_support_materialize(
        polar=polar,
        colorbar_unsupported=colorbar_unsupported,
        has_custom_font=any("font-family" in (style or {}) for style in chrome_styles.values())
        or any(_annotation_has_custom_typography(a) for a in annotations),
        has_browser_css=bool(
            getattr(figure, "class_name", None)
            or getattr(figure, "class_names", None)
            or chrome_styles
            or set(getattr(figure, "style", None) or {}) - {"background", "--chart-bg"}
            or any(a.get("class_name") not in (None, "") for a in annotations)
        ),
        has_extra_legends=bool(getattr(figure, "extra_legends", None)),
        annotations=ann_rows,
        axes=axes,
        traces=traces,
    )


def pack_polar_scene_input(figure: Any) -> bytes:
    """Marshal polar axis literals and pack XYPL via Rust (ABI 322)."""
    xa = figure.axis_options.get("x") or {}
    ya = figure.axis_options.get("y") or {}
    unit = str(xa.get("theta_unit", "radians"))
    turn = 360.0 if unit == "degrees" else 2.0 * math.pi
    sector = xa.get("sector") or (0.0, turn)
    r_lo, r_hi = figure._range("y")
    origin = ya.get("r_origin")
    scale_kind, constant, mask_nonpositive = _native._polar_r_scale(ya)
    grid = str(xa.get("grid_shape", "circular"))
    theta_zero = xa.get("theta_zero", "E")
    theta_zero_is_label = isinstance(theta_zero, str)
    return _native.scene_polar_input_pack(
        polar=str(getattr(figure, "coords", "cartesian") or "cartesian") == "polar",
        theta_unit=_native._polar_theta_unit(unit),
        theta_direction=_native._polar_theta_direction(xa.get("theta_direction")),
        n_categories=len(tuple(xa.get("categories") or ())),
        grid_shape=1 if grid == "linear" else 0,
        r_scale_kind=scale_kind,
        r_mask_nonpositive=mask_nonpositive,
        sector_start=float(sector[0]),
        sector_end=float(sector[1]),
        r_lo=float(r_lo),
        r_hi=float(r_hi),
        r_origin_is_nan=origin is None,
        r_origin=float("nan") if origin is None else float(origin),
        hole=float(ya.get("hole") or 0.0),
        r_constant=constant,
        theta_zero_is_label=theta_zero_is_label,
        theta_zero_label=str(theta_zero) if theta_zero_is_label else "",
        theta_zero_numeric=_native._polar_theta_zero(theta_zero),
    )
