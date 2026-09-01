"""Trace and figure observation helpers for Scene marshal paths.

Hosts read authored Figure/Trace state here before calling Rust materialize
kernels (ABI 322–325). Kept separate from ``_scene_v3`` so ``_scene_marshal``
does not circular-import the pack entry module.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from . import _native, channels

_SCENE_KIND_CLASS_HEXBIN = 1 << 5

_SCENE_AXIS_STYLE_KEYS = frozenset(
    {
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
    }
)

_SCENE_TICK_STRATEGY_NAMES = (
    "auto",
    "hide",
    "rotate",
    "stagger",
    "preserve",
    "none",
    "off",
)

_POLAR_COLLISION_KEYS = {
    "tick_label_strategy",
    "collision",
    "tick_label_min_gap",
    "tick_label_angle",
    "tick_label_anchor",
}

_ANNOTATION_TYPOGRAPHY_STYLE_KEYS = frozenset(
    {
        "font_family",
        "font_size",
        "font_weight",
        "font_style",
        "fontFamily",
        "fontSize",
        "fontWeight",
        "fontStyle",
    }
)


class UnsupportedSceneV3(ValueError):
    """The figure uses a feature outside the currently migrated Scene subset."""


def _trace_column(trace: Any, name: str) -> np.ndarray | None:
    """Return one authored f64 column, or None when the host did not set it."""
    value = getattr(trace, name, None)
    if value is None:
        return None
    return np.asarray(getattr(value, "values", value), dtype=np.float64)


def _parse_scene_dash(value: Any) -> list[float] | None | bool:
    """Return a 2–8 length pattern, None for solid, False if unusable on Scene."""
    if value is None:
        return None
    if isinstance(value, str):
        if not value:
            return False
        return _native.scene_dash_admit(value)
    if isinstance(value, (list, tuple)):
        try:
            lengths = [float(part) for part in value]
        except (TypeError, ValueError):
            return False
        return _native.scene_dash_admit("", lengths, use_lengths=True)
    return False


def _channel_constant_css(channel: Any) -> str | None:
    if channel is None:
        return None
    mode = getattr(channel, "mode", None)
    constant = getattr(channel, "constant", None)
    return _native.scene_channel_constant_css(
        None if mode is None else str(mode),
        constant is not None,
        None if constant is None else str(constant),
    )


def _trace_source_color_css(trace: Any) -> str:
    css = _channel_constant_css(getattr(trace, "color_ch", None))
    if css is not None:
        return css
    return str((getattr(trace, "style", None) or {}).get("color") or "#3987e5")


def _channel_end_rgba8(channel: Any, n: int, fallback: str) -> bytes | None:
    """Pack n RGBA8 pixels from a constant or direct_rgba channel."""
    if n < 1:
        return None
    if channel is None:
        rgba = _native.css_color_rgba(fallback, 1.0)
        return bytes(rgba) * n
    mode = getattr(channel, "mode", None)
    if mode == "constant":
        css = getattr(channel, "constant", None)
        if css is None:
            return None
        try:
            rgba = _native.css_color_rgba(str(css), 1.0)
        except ValueError:
            return None
        return bytes(rgba) * n
    if mode == "direct_rgba":
        packed = getattr(channel, "rgba", None)
        if packed is None:
            return None
        values = np.asarray(packed)
        if values.ndim == 1 and values.size == n * 4:
            values = values.reshape(n, 4)
        if values.shape != (n, 4):
            return None
        if values.dtype == np.uint8:
            return np.ascontiguousarray(values).tobytes()
        return np.ascontiguousarray(channels._quantized_rgba8(values.astype(np.float64))).tobytes()
    if mode == "categorical":
        try:
            resolved = channels.resolve_direct_rgba(channel)
        except (TypeError, ValueError):
            return None
        return _channel_end_rgba8(resolved, n, fallback)
    return None


def _item_apply_opacity(trace: Any, packed: bytes, n: int) -> bytes | None:
    channels_map = getattr(trace, "style_channels", None) or {}
    opacity_ch = channels_map.get("opacity")
    artist_ch = channels_map.get("artist_alpha")
    if opacity_ch is None and artist_ch is None:
        return packed
    artist = None
    if artist_ch is not None:
        artist = np.asarray(getattr(artist_ch, "values", None), dtype=np.float64).reshape(-1)
    opacity = None
    if opacity_ch is not None:
        opacity = np.asarray(getattr(opacity_ch, "values", None), dtype=np.float64).reshape(-1)
    return _native.scene_item_apply_opacity(packed, n, artist, opacity)


def _item_fill_rgba8(trace: Any, n: int) -> bytes | None:
    fallback = str((getattr(trace, "style", None) or {}).get("color", "#3987e5"))
    channel = getattr(trace, "color_ch", None)
    packed = _channel_end_rgba8(channel, n, fallback)
    if packed is None and channel is not None and getattr(channel, "mode", None) == "continuous":
        values = getattr(channel, "values", None)
        if values is None:
            return None
        scalars = np.ascontiguousarray(np.asarray(values, dtype=np.float64).reshape(-1))
        domain = getattr(channel, "domain", None)
        domain_pair = None
        if domain is not None and len(domain) == 2:
            domain_pair = (float(domain[0]), float(domain[1]))
        t = _native.scene_item_fill_t(scalars, n, domain_pair)
        if t is None:
            return None
        cmap = getattr(channel, "colormap", None) or "viridis"
        try:
            stops = _native.colormap_stops(str(cmap))
            image = _native.colormap_rgba(t, n, 1, stops, 255)
        except (TypeError, ValueError):
            return None
        packed = np.ascontiguousarray(image).reshape(-1).tobytes()
    if packed is None:
        return None
    return _item_apply_opacity(trace, packed, n)


def _item_stroke_rgba8(trace: Any, fills: bytes, n: int) -> bytes | None:
    stroke_ch = getattr(trace, "stroke_ch", None)
    if stroke_ch is not None and getattr(stroke_ch, "mode", None) == "match_fill":
        return fills
    fallback = str((getattr(trace, "style", None) or {}).get("stroke") or "transparent")
    packed = _channel_end_rgba8(stroke_ch, n, fallback)
    if packed is not None:
        return packed
    if stroke_ch is None:
        return _channel_end_rgba8(None, n, fallback)
    return None


def _hexbin_count(trace: Any) -> int:
    column = _trace_column(trace, "x")
    return 0 if column is None else int(len(column))


def _hexbin_packs_colormap_plane(trace: Any) -> bool:
    """Return whether hosts should pack this hexbin's metric as an XYTA plane."""
    if not (
        _native.scene_kind_class(str(getattr(trace, "kind", "") or "")) & _SCENE_KIND_CLASS_HEXBIN
    ):
        return False
    channel = getattr(trace, "color_ch", None)
    if channel is None:
        return False
    return _native.scene_hexbin_colormap_plane_admit(
        getattr(channel, "mode", None),
        1 if getattr(channel, "values", None) is not None else 0,
    )


def _hexbin_cell_rgba8(trace: Any) -> bytes | None:
    """Pack one RGBA8 pixel per occupied hex cell."""
    n = _hexbin_count(trace)
    fallback = str((getattr(trace, "style", None) or {}).get("color", "#3987e5"))
    return _channel_end_rgba8(getattr(trace, "color_ch", None), n, fallback)


def _hexbin_packs_rgba_plane(trace: Any) -> bool:
    """Return whether hosts should pack this hexbin's per-cell RGBA as XYTA."""
    if not (
        _native.scene_kind_class(str(getattr(trace, "kind", "") or "")) & _SCENE_KIND_CLASS_HEXBIN
    ):
        return False
    channel = getattr(trace, "color_ch", None)
    if channel is None:
        return False
    if not _native.scene_hexbin_rgba_plane_admit(getattr(channel, "mode", None)):
        return False
    return _hexbin_cell_rgba8(trace) is not None


def _hexbin_packs_paint_plane(trace: Any) -> bool:
    return _hexbin_packs_colormap_plane(trace) or _hexbin_packs_rgba_plane(trace)


def _scatter_count(trace: Any) -> int:
    column = _trace_column(trace, "x")
    return 0 if column is None else int(len(column))


def _scatter_packs_paint_plane(trace: Any) -> bool:
    """Return whether hosts should pack per-point scatter paint as XYTA."""
    if str(getattr(trace, "kind", "") or "") != "scatter":
        return False
    if getattr(trace, "use_density", lambda: False)():
        return False
    names = set(getattr(trace, "per_item_channel_names", lambda: ())())
    if not names:
        return False
    return all(_native.scene_scatter_paint_channel_admit(name) for name in names)


def _mesh_count(trace: Any) -> int:
    column = _trace_column(trace, "x0")
    return 0 if column is None else int(len(column))


def _mesh_joined_fill(trace: Any) -> bool:
    return bool((getattr(trace, "style", None) or {}).get("joined_fill"))


def _mesh_packs_paint_plane(trace: Any) -> bool:
    """Return whether hosts should pack per-face mesh paint as XYTA."""
    return _native.scene_mesh_paint_plane_admit(
        str(getattr(trace, "kind", "") or ""),
        1 if _mesh_joined_fill(trace) else 0,
        1 if bool(getattr(trace, "has_per_item_channels", lambda: False)()) else 0,
    )


def _ribbon_count(trace: Any) -> int:
    raw = getattr(trace, "count", None)
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    column = _trace_column(trace, "x0")
    return 0 if column is None else int(len(column))


def _ribbon_end_rgba_pair(trace: Any) -> tuple[bytes, bytes] | None:
    n = _ribbon_count(trace)
    if n < 1:
        return None
    fallback = _trace_source_color_css(trace)
    source = _channel_end_rgba8(getattr(trace, "color_ch", None), n, fallback)
    target = _channel_end_rgba8(getattr(trace, "color2_ch", None), n, fallback)
    if source is None or target is None:
        return None
    return source, target


def _classify_ribbon_color2(trace: Any) -> str:
    """Classify two-ended ribbon paint: absent, solid, gradient, ends, or fail."""
    color2 = getattr(trace, "color2_ch", None)
    has_color2 = color2 is not None
    kind_is_ribbon = str(getattr(trace, "kind", "") or "") == "ribbon"
    target = _channel_constant_css(color2) if has_color2 else None
    source_const = _channel_constant_css(getattr(trace, "color_ch", None))
    source_paint = _trace_source_color_css(trace)
    has_fill = "fill" in (getattr(trace, "style", None) or {})
    both_const = target is not None and source_const is not None
    has_end_pair = False
    if has_color2 and kind_is_ribbon and not both_const and not has_fill:
        has_end_pair = _ribbon_end_rgba_pair(trace) is not None
    return _native.scene_ribbon_color2_classify(
        has_color2,
        kind_is_ribbon,
        source_const,
        target,
        source_paint,
        has_fill,
        has_end_pair,
    )


def _ribbon_color2_class_code(trace: Any) -> int:
    """Return ribbon color2 classify code (0–4) for XYTA dispatch."""
    names = ("absent", "solid", "gradient", "ends", "fail")
    return names.index(_classify_ribbon_color2(trace))


def _ribbon_packs_end_paints(trace: Any, polar: bool = False) -> bool:
    """Return whether hosts should pack this ribbon's source/target RGBA8 ends."""
    if polar or str(getattr(trace, "kind", "") or "") != "ribbon":
        return False
    return _classify_ribbon_color2(trace) == "ends"


def _constant_color(trace: Any, fallback: str) -> str:
    channel = trace.color_ch
    if _classify_ribbon_color2(trace) == "fail":
        raise UnsupportedSceneV3("Scene v12 does not yet encode two-ended ribbon gradients")
    has_channel = channel is not None and not isinstance(channel, str)
    constant_ok = (
        has_channel
        and getattr(channel, "mode", None) == "constant"
        and getattr(channel, "constant", None) is not None
    )
    scatter_density = str(getattr(trace, "kind", "") or "") == "scatter" and bool(
        getattr(trace, "use_density", lambda: False)()
    )
    packs_paint = (
        _hexbin_packs_paint_plane(trace)
        or _ribbon_packs_end_paints(trace)
        or _mesh_packs_paint_plane(trace)
        or _scatter_packs_paint_plane(trace)
    )
    code = _native.scene_constant_color_admit(
        has_channel, constant_ok, scatter_density, packs_paint
    )
    if code == 2:
        assert channel is not None
        return str(channel.constant)
    if code == 1:
        return str((getattr(trace, "style", None) or {}).get("color", fallback))
    raise UnsupportedSceneV3("Scene v12 does not yet support data-driven paint channels")


def _fill_is_gradient_authoring(fill: Any) -> bool:
    if isinstance(fill, dict):
        return True
    if not isinstance(fill, str):
        return False
    return _native.scene_linear_gradient_prefix(fill)


def _admitted_fill_gradient_from_fill(fill: Any, mark_color: str) -> dict[str, Any] | None:
    """Return a resolved XYGR payload, or None to keep the fill fail-closed."""
    spec: dict[str, Any] | None
    if isinstance(fill, dict) and {"space", "dir", "stops"} <= set(fill):
        spec = fill
    elif isinstance(fill, dict):
        extra = [key for key in fill if key not in {"gradient", "space"}]
        if extra:
            return None
        gradient = fill.get("gradient")
        if not isinstance(gradient, str):
            return None
        raw_space = fill.get("space", "mark")
        space = "mark" if raw_space is None else str(raw_space)
        code, spec = _native.scene_parse_linear_gradient(gradient, space)
        if code != 1:
            return None
    elif isinstance(fill, str):
        code, spec = _native.scene_parse_linear_gradient(fill, "mark")
        if code != 1:
            return None
    else:
        return None
    if not spec:
        return None
    space = spec.get("space")
    direction = spec.get("dir")
    stops = spec.get("stops")
    if not isinstance(stops, (list, tuple)):
        return None
    ts: list[float] = []
    css_stops: list[str] = []
    for stop in stops:
        if not isinstance(stop, (list, tuple)) or len(stop) != 2:
            return None
        try:
            ts.append(float(stop[0]))
        except (TypeError, ValueError):
            return None
        css_stops.append(str(stop[1]))
    rgba = _native.scene_fill_gradient_admit(
        str(space),
        str(direction),
        ts,
        css_stops,
        mark_color,
    )
    if rgba is None:
        return None
    resolved = [(ts[i], rgba[i]) for i in range(len(ts))]
    return {"space": space, "dir": direction, "stops": resolved}


def _admitted_fill_gradient(trace: Any) -> dict[str, Any] | None:
    fill = (getattr(trace, "style", None) or {}).get("fill")
    if fill is None or not _fill_is_gradient_authoring(fill):
        return None
    try:
        mark_color = _constant_color(trace, "#3987e5")
    except UnsupportedSceneV3:
        return None
    return _admitted_fill_gradient_from_fill(fill, mark_color)


def _density_aggregates_color(trace: Any) -> bool:
    """LOD doc §2: density scatter aggregates a color channel into the blit."""
    if str(getattr(trace, "kind", "") or "") != "scatter" or not trace.use_density():
        return False
    return set(trace.per_item_channel_names()) <= {"color"}


def _xyta_hexbin_plane_observations(trace: Any) -> tuple[bool, bool]:
    """Return hexbin colormap-plane and rgba-plane-ready host observations."""
    channel = getattr(trace, "color_ch", None)
    if channel is None:
        return False, False
    colormap = bool(
        _native.scene_hexbin_colormap_plane_admit(
            getattr(channel, "mode", None),
            1 if getattr(channel, "values", None) is not None else 0,
        )
    )
    rgba_ready = False
    if _native.scene_hexbin_rgba_plane_admit(getattr(channel, "mode", None)):
        rgba_ready = _hexbin_cell_rgba8(trace) is not None
    return colormap, rgba_ready


def _scene_tick_label_strategy(options: dict[str, Any]) -> str:
    raw = options.get("tick_label_strategy")
    if raw is None:
        raw = options.get("collision")
    code = _native.scene_tick_label_strategy(str(raw or "auto"))
    if 0 <= code < len(_SCENE_TICK_STRATEGY_NAMES):
        return _SCENE_TICK_STRATEGY_NAMES[code]
    return "auto"


def _significant_scene_axis_keys(options: dict[str, Any], *, polar: bool = False) -> list[str]:
    keys = [str(key) for key, value in options.items() if value not in (None, False, [], {})]
    if polar and _scene_tick_label_strategy(options) in {"none", "off", "auto"}:
        keys = [key for key in keys if key not in _POLAR_COLLISION_KEYS]
    return keys


def _annotation_has_markup(annotation: Any) -> bool:
    if not isinstance(annotation, dict):
        return False
    if annotation.get("markup") not in (None, ""):
        return True
    style = annotation.get("style") or {}
    return isinstance(style, dict) and style.get("markup") not in (None, "")


def _annotation_has_custom_typography(annotation: Any) -> bool:
    if not isinstance(annotation, dict):
        return False
    style = annotation.get("style") or {}
    if not isinstance(style, dict):
        style = {}
    for key in _ANNOTATION_TYPOGRAPHY_STYLE_KEYS:
        if style.get(key) not in (None, "", False):
            return True
        if annotation.get(key) not in (None, "", False):
            return True
    return False


def _scene_side_mask(
    values: Any,
    name: str,
    axis_id: str,
    allowed: tuple[str, str],
    side_code: int,
) -> int:
    if values is None:
        return 1 << side_code
    if any(value not in allowed for value in values):
        raise UnsupportedSceneV3(
            f"Scene v12 {axis_id} axis {name} must contain only {list(allowed)!r}"
        )
    return sum(1 << index for index, candidate in enumerate(allowed) if candidate in values)
