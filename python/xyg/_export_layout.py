"""Shared static-export layout, gutter rooms, title bands, and polar recut."""

from __future__ import annotations

from typing import Any, Optional

from . import _native, _textblock
from ._columns import column as _column
from ._export_chrome import _TEXT, slot_styles
from ._export_legend import legend_items
from ._export_ticks import (
    _axis_tick_font_size,
    _axis_tick_label_layout,
    _axis_tick_label_offset,
    _axis_tick_label_sides,
    _axis_tick_label_strategy,
    _tick_label_anchor,
    _tick_text,
    axis_ticks,
)
from ._layout import _axes_by_id, _Scale
from ._paint import _css
from ._paint import paint_rgba8 as _paint_rgba8
from ._paint import px_size as _px_size

_Y_TITLE_TICK_GAP = 0.4


def _has_outside_y_title(axis: dict[str, Any]) -> bool:
    """Whether a y-axis title needs space outside the plot rectangle."""
    if not axis.get("label"):
        return False
    raw_position = axis.get("label_position")
    position = raw_position if isinstance(raw_position, str) else "center"
    return not position.replace("-", "_").startswith("inside_")


def _axis_text_paint_visible(
    axis: dict[str, Any],
    key: str,
    fallback_key: Optional[str] = None,
) -> bool:
    """Whether an axis text paint can contribute visible ink.

    Axis visibility shorthands are compiled to transparent CSS colors. Layout
    must not measure that invisible text back into an explicit zero padding,
    or ``show=False`` cannot produce the documented edge-to-edge sparkline.
    Unknown/browser-only paints stay conservative and reserve their room.
    """
    style = axis.get("style") or {}
    paint = style.get(key)
    if paint is None and fallback_key is not None:
        paint = style.get(fallback_key)
    if paint is None:
        return True
    return _paint_rgba8(_css(paint, _TEXT))[3] != 0


def _y_title_baseline(
    axis: dict[str, Any],
    plot: dict[str, float],
) -> Optional[float]:
    """Baseline x of a quarter-turned y-axis title, or None when it has none.

    Matplotlib positions a y title from the outer edge of the tick-label union,
    not from the canvas edge. A static exporter emits a baseline while the
    browser positions a centered line box; the returned coordinate includes
    that box-to-baseline correction.
    """
    if not _has_outside_y_title(axis):
        return None  # absent or drawn over the plot; it needs no gutter
    style = axis.get("style") or {}
    font_size = float(style.get("label_size", 12))
    side = axis.get("side", "left")
    block = _textblock.measure(axis["label"], font_size)
    ascent, descent = block.ascent, block.descent
    if side == "right":
        # Right-side axes still use the existing fixed 42/54 px reservation.
        # Keep their plot-relative placement unchanged; this repair only
        # measures the left gutter that can otherwise clip against x=0.
        angle = float(axis.get("label_angle", 90.0))
        shift = (ascent - descent) / 2 if abs(abs(angle) - 90.0) < 0.5 else 0.0
        return plot["x"] + plot["w"] + 40.0 - shift + float(axis.get("label_offset", 0.0))
    from . import _svg

    tick_offset, tick_room = (
        _svg._y_tick_label_room(axis, plot["h"])
        if "left" in _axis_tick_label_sides(axis, is_x=False)
        else (0.0, 0.0)
    )
    gap = float(axis.get("label_offset", _Y_TITLE_TICK_GAP * font_size))
    # For a -90 degree title, later lines move toward the plot. Pin the first
    # baseline so the whole block, not only line one, remains outside ticks.
    title_depth = descent + (block.line_count - 1) * block.line_step
    return plot["x"] - tick_offset - tick_room - gap - title_depth


def _y_tick_label_room(axis: dict[str, Any], plot_h: float) -> tuple[float, float]:
    """(offset from the spine, widest tick-label extent) for a y axis, in px.

    Hosts still skip none/off/invisible axes, format `_tick_text`, and resolve
    the spine offset. The rotated DejaVu extent lives in Rust (ABI 125).
    """
    if _axis_tick_label_strategy(axis) in {"none", "off"} or not _axis_text_paint_visible(
        axis, "tick_label_color", "tick_color"
    ):
        return 0.0, 0.0
    font_size = _axis_tick_font_size(axis)
    raw_angle = axis.get("tick_label_angle")
    angle = float(raw_angle or 0.0)
    _values, labels, step = axis_ticks(axis, plot_h, False)
    texts = [_tick_text(axis, value, step) for value in labels]
    return _axis_tick_label_offset(axis, 8.0), float(
        _native.y_tick_label_extent(texts, font_size, angle)
    )


def _y_axis_left_room(spec: dict[str, Any], plot_h: float) -> float:
    """Left gutter the y-axis text needs, measured rather than assumed.

    `layout()`'s fixed 46/62 px default fits ordinary numeric ticks under a
    12 px title. Matplotlib's rcParam fonts (13.89 px at 100 dpi), long category
    names, and authored tick labels all exceed it, and the shortfall lands as a
    title drawn on top of the tick labels — or off the canvas — instead of as a
    wider gutter.

    Right-side y axes deliberately keep the flat 42/54 px reservation above:
    ChartView pins a right title plot-relative (`plot-right+40`) rather than to
    a canvas inset, so widening only the static exporters' right gutter would
    move their title away from the browser's. That asymmetry is recorded in
    `spec/api/styling.md`, not silently fixed here.

    Hosts still iterate axes, skip sides, and resolve CSS visibility. Column
    combination of title + tick ink lives in Rust (ABI 125) so SVG, raster, and
    pyplot cannot drift. `_y_tick_label_room` stays a host seam so tests can
    pin the once-per-axis tick measure.
    """
    room = 0.0
    for axis_id, axis in _axes_by_id(spec).items():
        if not axis_id.startswith("y"):
            continue
        left_labels = "left" in _axis_tick_label_sides(axis, is_x=False)
        left_title = axis.get("side", "left") != "right"
        if not left_labels and not left_title:
            continue
        from . import _svg

        tick_offset, tick_room = (
            _svg._y_tick_label_room(axis, plot_h) if left_labels else (0.0, 0.0)
        )
        title_visible = (
            left_title
            and _has_outside_y_title(axis)
            and _axis_text_paint_visible(axis, "label_color")
        )
        title = str(axis.get("label") or "") if title_visible else ""
        label_size = float((axis.get("style") or {}).get("label_size", 12))
        gap = float(axis.get("label_offset", _Y_TITLE_TICK_GAP * label_size))
        room = max(
            room,
            float(_native.y_axis_left_room(tick_offset, tick_room, title, label_size, gap)),
        )
    return room


def _x_axis_title_room(axis: dict[str, Any]) -> float:
    """Outward room needed by an outside x-axis title.

    Hosts still skip inside/invisible titles. The baseline-conversion formula
    lives in Rust (ABI 125) so tight layout cannot stop at the historical
    36/42 px band while the title itself extends past the canvas.
    """
    if not axis.get("label") or not _axis_text_paint_visible(axis, "label_color"):
        return 0.0
    raw_position = axis.get("label_position")
    position = raw_position if isinstance(raw_position, str) else "center"
    if position.replace("-", "_").startswith("inside_"):
        return 0.0
    style = axis.get("style") or {}
    font_size = float(style.get("label_size", 12))
    offset = float(axis.get("label_offset", 0.0))
    return float(
        _native.x_axis_title_room(
            str(axis["label"]),
            font_size,
            offset,
            axis.get("side", "bottom") == "top",
        )
    )


def _x_tick_label_room(axis: dict[str, Any], plot_w: float) -> float:
    """Outward room needed by the x axis's final tick-label set and title.

    The old 32/42 px bands only fit horizontal labels. Hosts still keep the
    none/off/auto-horizontal shortcuts and call collision layout. The measured
    band combination lives in Rust (ABI 125).
    """
    strategy = _axis_tick_label_strategy(axis)
    if strategy == "none":
        return 0.0
    title_room = _x_axis_title_room(axis)
    if strategy == "off" or not _axis_text_paint_visible(axis, "tick_label_color", "tick_color"):
        return title_room
    if (
        strategy == "auto"
        and axis.get("tick_label_angle") is None
        and axis.get("tick_values") is None
        and axis.get("kind") != "category"
    ):
        # Numeric auto ticks are selected from the plot width and remain in the
        # established horizontal band. Only authored/category locations can
        # force rotation or staggering; avoid building and measuring the full
        # label layout merely to rediscover the ordinary zero-extra case. The
        # independently measured title can still exceed that fixed band.
        return title_room
    _ticks, values, step = axis_ticks(axis, plot_w, True)
    scale = _Scale(axis, 0.0, max(1.0, plot_w))
    items = _axis_tick_label_layout(axis, values, step, scale, True)
    if not items:
        return title_room
    has_adaptive_layout = any(float(item["angle"]) or int(item.get("row", 0)) for item in items)
    font_size = _axis_tick_font_size(axis)
    has_multiline_ticks = any(len(_textblock.split_lines(item["text"])) > 1 for item in items)
    if (
        not has_adaptive_layout
        and not has_multiline_ticks
        and strategy == "auto"
        and axis.get("tick_label_angle") is None
    ):
        # Preserve the long-standing flat band for ordinary horizontal text.
        # Measured bands are reserved for rotation, staggering, or multiline
        # chrome; ordinary auto ticks retain their historical geometry.
        return title_room
    side = axis.get("side", "bottom")
    label_offset = (
        _axis_tick_label_offset(axis, 7.0, 0.2)
        if side == "top"
        else _axis_tick_label_offset(axis, 16.0, 0.8)
    )
    return float(
        _native.x_tick_label_room(
            [item["text"] for item in items],
            [float(item["angle"]) for item in items],
            [int(item.get("row", 0)) for item in items],
            font_size,
            float(label_offset),
            title_room,
        )
    )


def _x_tick_label_edge_rooms(axes: dict[str, dict[str, Any]], plot_w: float) -> tuple[float, float]:
    """Canvas-edge room needed by x tick labels that overhang the plot.

    Hosts still skip none/off/invisible axes, format labels, and choose
    anchors. Per-axis rotated overhang lives in Rust (ABI 125).
    """
    left = right = 0.0
    for axis_id, axis in axes.items():
        if (
            not axis_id.startswith("x")
            or _axis_tick_label_strategy(axis) in {"none", "off"}
            or not _axis_text_paint_visible(axis, "tick_label_color", "tick_color")
        ):
            continue
        _ticks, values, step = axis_ticks(axis, plot_w, True)
        scale = _Scale(axis, 0.0, max(1.0, plot_w))
        font_size = _axis_tick_font_size(axis)
        explicit_anchor = _tick_label_anchor(axis, axis.get("style") or {}, "")
        for side in _axis_tick_label_sides(axis, is_x=True):
            side_axis = {**axis, "side": side}
            if (
                _axis_tick_label_strategy(axis) == "auto"
                and axis.get("tick_label_angle") is None
                and axis.get("tick_values") is None
                and axis.get("kind") != "category"
            ):
                items = [
                    {
                        "pos": float(scale(value)),
                        "text": _tick_text(axis, value, step),
                        "angle": 0.0,
                    }
                    for value in values
                ]
            else:
                items = _axis_tick_label_layout(side_axis, values, step, scale, True)
            if not items:
                continue
            anchors: list[str] = []
            for item in items:
                angle = float(item["angle"])
                anchor = explicit_anchor
                if not anchor:
                    if angle == 0:
                        anchor = "center"
                    elif (side == "bottom" and angle < 0) or (side == "top" and angle > 0):
                        anchor = "end"
                    else:
                        anchor = "start"
                anchors.append(str(anchor))
            left_i, right_i = _native.x_tick_label_edge_rooms(
                plot_w,
                [float(item["pos"]) for item in items],
                [str(item["text"]) for item in items],
                [float(item["angle"]) for item in items],
                anchors,
                font_size,
            )
            left = max(left, left_i)
            right = max(right, right_i)
    return float(left), float(right)


def _x_axis_rooms(
    axes: dict[str, dict[str, Any]], plot_w: float, compact: bool
) -> tuple[float, float, float]:
    """Shared ``(top, bottom, measured_bottom)`` x-axis bands.

    The fixed bottom band is metadata for colorbar placement.  It must not
    override an explicit figure ``padding`` authored by pyplot unless rotated
    or staggered labels actually require more room.
    """
    top = 0.0
    bottom = 0.0
    measured_bottom = 0.0
    for axis_id, axis in axes.items():
        if not axis_id.startswith("x") or _axis_tick_label_strategy(axis) == "none":
            continue
        title_side = axis.get("side", "bottom")
        room_sides = set(_axis_tick_label_sides(axis, is_x=True))
        if _axis_tick_label_strategy(axis) == "off" or axis.get("label"):
            room_sides.add(title_side)
        for side in room_sides:
            side_axis = {**axis, "side": side}
            if side != title_side:
                side_axis.pop("label", None)
            measured = _x_tick_label_room(side_axis, plot_w)
            room, measured_bottom_contrib = _native.compat_x_axis_side_room(
                compact, side == "top", measured
            )
            if side == "top":
                top = max(top, room)
            else:
                bottom = max(bottom, room)
                measured_bottom = max(measured_bottom, measured_bottom_contrib)
    return top, bottom, measured_bottom


def _title_entries(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalized independent axes-title slots, with legacy-title fallback."""
    authored = spec.get("title_options")
    if isinstance(authored, list) and authored:
        return [entry for entry in authored if isinstance(entry, dict) and entry.get("text")]
    if spec.get("title"):
        return [
            {
                "text": spec["title"],
                "loc": "center",
                "y": 1.0,
                "pad": 8.0,
                "automatic_y": True,
                "style": {},
            }
        ]
    return []


def _decode_title_geometry(spec: dict[str, Any], blob: bytes) -> dict[str, Any]:
    """Hydrate title placement from its raw-f32 wire column for static layout."""
    authored = spec.get("title_options")
    if not isinstance(authored, list) or not authored:
        return spec
    decoded = []
    changed = False
    for entry in authored:
        if not isinstance(entry, dict) or "geometry" not in entry:
            decoded.append(entry)
            continue
        values = _column(blob, spec["columns"][entry["geometry"]])
        hydrated = {**entry, "y": float(values[0]), "pad": float(values[1])}
        decoded.append(hydrated)
        changed = True
    return {**spec, "title_options": decoded} if changed else spec


def _title_wrap_width(width: float, left: float, right: float) -> float:
    """Width a chart title wraps at, in CSS px.

    Thin packer over Rust ``xyg_compat_title_wrap_width`` (ABI 126).
    """
    return float(_native.compat_title_wrap_width(width, left, right))


def _title_metrics(
    spec: dict[str, Any],
    entry: dict[str, Any],
    wrap_width: float | None = None,
) -> tuple[dict[str, Any], float, _textblock.TextBlock]:
    base = slot_styles(spec).get("title") or {}
    style = {**base, **(entry.get("style") or {})}
    size = _px_size(style.get("font-size"), 14.0)
    return style, size, _textblock.measure(entry["text"], size, max_width=wrap_width)


def _title_room(spec: dict[str, Any], compact: bool, wrap_width: float | None = None) -> float:
    room = 0.0
    for entry in _title_entries(spec):
        _style, _size, block = _title_metrics(spec, entry, wrap_width)
        pad = float(entry.get("pad", 8.0))
        room = max(
            room,
            float(
                _native.compat_title_room(
                    compact,
                    block.height,
                    pad,
                    bool(entry.get("automatic_y", True)),
                    float(entry.get("y", 1.0)),
                )
            ),
        )
    return room


_SCENE_SCALE_KINDS = {"linear": 0, "log": 1, "symlog": 2}


def _spec_has_custom_font(spec: dict[str, Any]) -> bool:
    """Whether chrome CSS asks for a face Scene cannot encode.

    Custom `font-family` stays fail-closed on Scene (#288 / #297). Measuring
    those figures with DejaVu would be a silent substitute.
    """
    for style in slot_styles(spec).values():
        family = style.get("font-family")
        if family not in (None, "", "DejaVu Sans"):
            return True
    for style in (spec.get("chrome_styles") or {}).values():
        if not isinstance(style, dict):
            continue
        family = style.get("font-family") or style.get("font_family")
        if family not in (None, "", "DejaVu Sans"):
            return True
    return False


def _scene_axis_pack(axis: dict[str, Any]) -> tuple[int, float, float, float, bool] | None:
    """Pack one primary cartesian axis for `xyg_scene_plot_layout`, or None."""
    kind = str(axis.get("scale") or axis.get("kind") or "linear")
    code = _SCENE_SCALE_KINDS.get(kind)
    if code is None:
        return None
    domain = axis.get("domain") or axis.get("range")
    if domain is None or len(domain) != 2:
        return None
    lo, hi = float(domain[0]), float(domain[1])
    constant = float(axis.get("linthresh") or axis.get("constant") or 1.0)
    mask = str(axis.get("nonpositive") or "") == "mask"
    return code, lo, hi, constant, mask


def scene_layout_rooms(
    spec: dict[str, Any],
) -> tuple[float, float, float, float] | None:
    """Rust cartesian gutters for default-font Scene-shaped specs (#297).

    Returns ``(left, right, top, bottom)`` from `xyg_scene_plot_layout` when the
    spec is primary cartesian linear/log/symlog with the default face.
    Polar, extra axes, top/right primary sides, outside legends, in-axes
    colorbars, category scales, and custom `font-family` return None so
    callers keep compatibility `_svg._*room` instead of a DejaVu substitute.
    """
    if spec.get("coords") not in (None, "cartesian"):
        return None
    if _spec_has_custom_font(spec):
        return None
    axes = _axes_by_id(spec)
    extra = [axis_id for axis_id in axes if axis_id not in {"x", "y"}]
    if extra:
        return None
    if axes["x"].get("side", "bottom") == "top" or axes["y"].get("side", "left") == "right":
        return None
    legend = spec.get("legend") or {}
    loc = str(legend.get("loc") or "")
    if spec.get("show_legend") and "outside" in loc:
        return None
    x_pack = _scene_axis_pack(axes["x"])
    y_pack = _scene_axis_pack(axes["y"])
    if x_pack is None or y_pack is None:
        return None
    width = spec.get("width")
    height = spec.get("height")
    width = 900 if not isinstance(width, (int, float)) else float(width)
    height = 420 if not isinstance(height, (int, float)) else float(height)
    pad = spec.get("padding")
    padding = None
    if isinstance(pad, list) and len(pad) == 4:
        padding = (float(pad[0]), float(pad[1]), float(pad[2]), float(pad[3]))
    entries = _title_entries(spec)
    title = str(entries[0]["text"]) if len(entries) == 1 else ""
    if len(entries) > 1:
        return None
    colorbar = spec.get("colorbar") or {}
    if colorbar.get("placement") == "axes":
        return None
    side = None
    if colorbar:
        side = "bottom" if colorbar.get("orientation") == "horizontal" else "right"
    x_format = axes["x"].get("format") or axes["x"].get("tick_format")
    y_format = axes["y"].get("format") or axes["y"].get("tick_format")
    try:
        return _native.scene_plot_layout(
            viewport=(width, height),
            x_axis=x_pack,
            y_axis=y_pack,
            title=title,
            x_label=str(axes["x"].get("label") or ""),
            y_label=str(axes["y"].get("label") or ""),
            x_format=str(x_format) if x_format else None,
            y_format=str(y_format) if y_format else None,
            padding=padding,
            colorbar_side=side,
        )
    except (TypeError, ValueError):
        return None


def layout(spec: dict[str, Any]) -> tuple[int, int, bool, dict[str, float]]:
    """Concrete pixel dimensions + plot rect from a spec — shared by the SVG and
    native-PNG exporters so their chrome/plot geometry stays identical.

    Hosts still iterate axes, format ticks, measure ABI 125 rooms, resolve CSS
    visibility, and decide polar legend reservation. Padding, title-band,
    colorbar extra, right-y, floors, and polar recut combination live in Rust
    (ABI 198).
    """
    width = spec.get("width")
    height = spec.get("height")
    # Fluid ("100%") figures need concrete export dimensions.
    width = 900 if not isinstance(width, (int, float)) else int(width)
    height = 420 if not isinstance(height, (int, float)) else int(height)

    compact = _native.compat_is_compact(width)
    pad = spec.get("padding")
    authored: tuple[float, float, float, float] | None
    if isinstance(pad, list) and len(pad) == 4:
        authored = (float(pad[0]), float(pad[1]), float(pad[2]), float(pad[3]))
        right, left = authored[1], authored[3]
    else:
        authored = None
        _, right, _, left = _native.compat_default_padding(compact)
    from . import _svg

    axes = _axes_by_id(spec)
    provisional_w = max(40.0, width - left - right)
    title_wrap_width = _title_wrap_width(width, left, right)
    title_room = _title_room(spec, compact, title_wrap_width)
    x_top_room, x_bottom_room, measured_bottom_room = _svg._x_axis_rooms(
        axes, provisional_w, compact
    )
    colorbar = spec.get("colorbar") or {}
    if colorbar:
        if colorbar.get("placement") == "axes":
            colorbar_kind = (
                "axes_horizontal"
                if colorbar.get("orientation") == "horizontal"
                else "axes_vertical"
            )
        elif colorbar.get("orientation") == "horizontal":
            colorbar_kind = "figure_horizontal"
        else:
            colorbar_kind = "figure_vertical"
    else:
        colorbar_kind = "none"
    has_right_y = any(
        axis_id.startswith("y")
        and (
            axis.get("side", "right") == "right"
            or "right" in _axis_tick_label_sides(axis, is_x=False)
        )
        and _axis_tick_label_strategy(axis) != "none"
        for axis_id, axis in axes.items()
    )
    combine_kw: dict[str, Any] = {
        "authored_padding": authored,
        "title_room": title_room,
        "x_top_room": x_top_room,
        "x_bottom_room": x_bottom_room,
        "x_measured_bottom": measured_bottom_room,
        "colorbar_kind": colorbar_kind,
        "colorbar_has_label": bool(colorbar.get("label")),
        "colorbar_pad_zero": colorbar.get("pad") == 0,
        "has_right_y": has_right_y,
    }
    preview = _native.compat_combine_plot(width, height, **combine_kw)
    y_left = _y_axis_left_room(spec, preview["h"])
    mid = _native.compat_combine_plot(width, height, y_left_room=y_left, **combine_kw)
    left = mid["x"]
    right = width - mid["x"] - mid["w"]
    for _pass in range(2):
        edge_left, edge_right = _x_tick_label_edge_rooms(
            axes,
            max(40.0, width - left - right),
        )
        widened_left = max(left, edge_left)
        widened_right = max(right, edge_right)
        if widened_left == left and widened_right == right:
            break
        left, right = widened_left, widened_right
    final_w = max(40.0, width - left - right)
    if final_w == provisional_w:
        x_final = (x_top_room, x_bottom_room, measured_bottom_room)
    else:
        x_final = _svg._x_axis_rooms(axes, final_w, compact)
    polar_kw = None
    if spec.get("coords") == "polar":
        polar_kw = _polar_combine_args(spec, width, compact)
    plot = _native.compat_combine_plot(
        width,
        height,
        y_left_room=y_left,
        edge_left=left,
        edge_right=right,
        x_rooms_final=x_final,
        polar=polar_kw,
        **combine_kw,
    )
    return width, height, compact, plot


def _polar_combine_args(spec: dict[str, Any], width: float, compact: bool) -> dict[str, Any]:
    """Host polar-recut observations for ``compat_combine_plot``."""
    theta_axis = spec.get("x_axis") or {}
    labels_hidden = theta_axis.get("tick_label_strategy") == "none"
    legend_side, legend_room = _polar_legend_reserve(spec, compact, width)
    room = 0.0 if labels_hidden else _polar_label_room(theta_axis)
    authored_pad = spec.get("padding")
    y_axis = spec.get("y_axis") or {}
    titled = bool(y_axis.get("label")) and _axis_text_paint_visible(y_axis, "label_color")
    x_axis = spec.get("x_axis") or {}
    x_titled = bool(x_axis.get("label")) and _axis_text_paint_visible(x_axis, "label_color")
    colorbar = spec.get("colorbar") or {}
    return {
        "legend_side": legend_side,
        "legend_room": legend_room,
        "polar_label_room": room,
        "authored_padding": isinstance(authored_pad, list) and len(authored_pad) == 4,
        "y_titled": titled,
        "keeps_bottom": x_titled or colorbar.get("orientation") == "horizontal",
    }


# Room reserved outside the outer ring for angular tick labels. Cartesian
# gutters are per-side because labels hug two edges; a polar chart carries them
# all the way around, so the allowance is uniform. The floor/ceiling live in
# Rust (`compat_layout::POLAR_LABEL_ROOM` / `POLAR_LABEL_ROOM_MAX`, ABI 126).
# Mirrored by POLAR_LABEL_ROOM in js/src/50_chartview.ts.
_POLAR_LABEL_ROOM = 30.0

# Gutter reserved for a legend beside a disc. A Cartesian legend overlays the
# plot because data rarely reaches a corner; a disc inscribed in its rect leaves
# no corner at all, so an inside legend lands on the marks — an `upper right` box
# covered a wind rose's whole north-east quadrant and the outer radial label
# under it. Both incumbents' answer is to move it out (Plotly puts polar legends
# in the figure margin), which needs room the disc gives back.
#
# A FRACTION OF THE CANVAS, clamped, rather than a measurement of the label set:
# every renderer knows the canvas width to the pixel, so all three reserve the
# identical box, while a measured reservation would drift with each renderer's
# font metrics (DejaVu here, system-ui in the browser). A flat constant was tried
# first and is the wrong shape — 96 px ellipsized `Partner  (30%)`, an ordinary
# pie slice's default name, while being a fifth of a phone canvas and a
# fifteenth of a wide one.
#
# The floor keeps a narrow chart's legend readable; the ceiling stops a wide one
# from spending 300 px on four short rows. A label still wider than the gutter
# ellipsizes with its full text in `title`/ARIA, exactly as the static exporters
# already ellipsize against the plot width. The fraction/clamp live in Rust
# (`compat_layout::polar_legend_room`, ABI 126).
# Mirrored by xyPolarLegendRoom in js/src/50_chartview.ts.


def _polar_legend_room(width: float) -> float:
    """Side-gutter width for a polar legend on a `width`-px canvas.

    Thin packer over Rust ``xyg_polar_legend_room`` (ABI 126).
    """
    return float(_native.polar_legend_room(width))


_POLAR_LEGEND_BAND = 64.0


def _polar_legend_reserve(spec: dict[str, Any], compact: bool, width: float) -> tuple[str, float]:
    """Side and px a polar legend gutter claims: ``("right", 158.0)`` etc.

    ``("", 0.0)`` when nothing is reserved — a non-polar figure, no legend rows,
    an authored ``anchor`` (an explicit plot-relative placement the author owns),
    or an authored 4-tuple ``padding`` (which already states the box the plot
    should occupy, and is the documented way to hand-reserve a caption band).

    Mirrored by `_polarLegendReserve` in js/src/50_chartview.ts.
    """
    if spec.get("coords") != "polar" or not spec.get("show_legend", True):
        return "", 0.0
    padding = spec.get("padding")
    if isinstance(padding, list) and len(padding) == 4:
        return "", 0.0
    options = spec.get("legend") or {}
    anchor = options.get("anchor")
    if anchor and len(anchor) in (2, 4):
        return "", 0.0
    rows = options.get("items") or legend_items(spec.get("traces") or [])
    if not rows and not (spec.get("extra_legends") or []):
        return "", 0.0
    loc = str(options.get("loc") or "upper right")
    return _native.polar_legend_reserve(compact, "left" in loc, width)


def _polar_label_room(theta_axis: dict[str, Any]) -> float:
    """Room outside the ring for the angular tick labels.

    Measured, not fixed: authored category names ("EAST-NORTH-EAST") are far
    wider than an angle, and a constant allowance hard-clipped them at the
    canvas edge. Only the widest AUTHORED label is measured — generated angle
    text is bounded and already fits the floor — and the result is capped so a
    pathological label shrinks the disc rather than erasing it.

    Mirrored by `polarLabelRoom` in js/src/50_chartview.ts.
    """
    labels = theta_axis.get("tick_labels")
    if not labels and theta_axis.get("kind") == "category":
        labels = theta_axis.get("categories")
    if not labels:
        return float(_native.polar_label_room(None))
    size = _axis_tick_font_size(theta_axis)
    widest = max((_textblock.measure(str(text), size).width for text in labels), default=0.0)
    return float(_native.polar_label_room(widest))


def _recut_polar_plot(
    spec: dict[str, Any],
    plot: dict[str, float],
    width: float,
    height: float,
    compact: bool = False,
) -> None:
    """Re-cut the plot rect for a disc, in place.

    Mirrored by `_recutPolarPlot` in js/src/50_chartview.ts — the two must agree
    or the same chart renders at a different size and centre in the browser than
    in an export.

    Two things happen here, both after the cartesian gutter passes have
    converged so they cannot perturb that fixed point.

    First, the cartesian tick-label gutters are given back. They exist to hold
    labels hugging the left and bottom edges; a polar chart carries its labels
    all the way around the rim instead, so leaving them reserved pushed the disc
    right and up (a 400x400 chart centred its circle at x=219) and shrank it for
    no reason. The horizontal and vertical reservations are symmetrised rather
    than simply zeroed, so a colorbar or right-side axis that genuinely claimed
    space still keeps it.

    Second, a uniform allowance is reserved all the way around for the angular
    tick labels. The radius is `min(w, h) / 2` with no fill factor
    (polar-axes.md §3), so that room has to come out of the rect rather than out
    of the transform — otherwise every renderer would need the same fudge factor
    and they would eventually disagree about it.

    Third, a legend gutter (`_polar_legend_reserve`) is taken off the rect and
    recorded as `plot["legend_box"]`, so the legend sits beside the disc instead
    of on top of it. `_legend_layout` places and bounds itself in that box.

    Hosts still resolve legend reservation, measure angular labels, and decide
    title/colorbar flags. The recut combination lives in Rust (ABI 126).
    """
    theta_axis = spec.get("x_axis") or {}
    labels_hidden = theta_axis.get("tick_label_strategy") == "none"
    legend_side, legend_room = _polar_legend_reserve(spec, compact, width)
    room = 0.0 if labels_hidden else _polar_label_room(theta_axis)
    authored_pad = spec.get("padding")
    y_axis = spec.get("y_axis") or {}
    titled = bool(y_axis.get("label")) and _axis_text_paint_visible(y_axis, "label_color")
    x_axis = spec.get("x_axis") or {}
    x_titled = bool(x_axis.get("label")) and _axis_text_paint_visible(x_axis, "label_color")
    colorbar = spec.get("colorbar") or {}
    recut = _native.recut_polar_plot(
        plot,
        width,
        height,
        legend_side=legend_side,
        legend_room=legend_room,
        polar_label_room=room,
        authored_padding=isinstance(authored_pad, list) and len(authored_pad) == 4,
        y_titled=titled,
        keeps_bottom=x_titled or colorbar.get("orientation") == "horizontal",
    )
    plot["x"] = recut["x"]
    plot["y"] = recut["y"]
    plot["w"] = recut["w"]
    plot["h"] = recut["h"]
    plot["top_axis_room"] = recut["top_axis_room"]
    for key in ("legend_box_x", "legend_box_y", "legend_box_w", "legend_box_h"):
        if key in recut:
            plot[key] = recut[key]
        else:
            plot.pop(key, None)
