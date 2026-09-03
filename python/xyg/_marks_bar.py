"""Bar/column mark family — grouped / stacked / normalized rects via kernels.bar_stack."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Optional, Union

import numpy as np

from . import channels, kernels, styles
from ._typing import ArrayLike, Scalar
from .config import DEFAULT_PALETTE

if TYPE_CHECKING:
    from ._figure import Figure


def series_direct_paints(
    value: Any,
    n_series: int,
    n_items: int,
    label: str,
) -> Optional[list[channels.ColorChannel]]:
    """Resolve numeric bar paint arrays without confusing CSS sequences.

    A one-series bar accepts ``(N, 3|4)`` and a multi-series bar accepts
    ``(S, N, 3|4)``.  Returning ``None`` leaves scalar/per-series CSS color
    handling to the existing palette resolver.
    """
    if value is None or isinstance(value, str):
        return None
    arr = np.asarray(value)
    if not np.issubdtype(arr.dtype, np.number):
        return None
    if n_series == 1 and arr.shape in {(n_items, 3), (n_items, 4)}:
        return [channels.resolve_color(arr, n_items, default_constant=DEFAULT_PALETTE[0])]
    if arr.ndim == 3 and arr.shape[:2] == (n_series, n_items) and arr.shape[2] in (3, 4):
        return [
            channels.resolve_color(
                arr[index], n_items, default_constant=DEFAULT_PALETTE[index % len(DEFAULT_PALETTE)]
            )
            for index in range(n_series)
        ]
    raise ValueError(
        f"{label} numeric paint must have shape ({n_items}, 3|4) for one series "
        f"or ({n_series}, {n_items}, 3|4), got {arr.shape}"
    )


def series_style_values(
    value: Any,
    n_series: int,
    n_items: int,
    label: str,
    key: str,
    *,
    default: float,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> tuple[list[float], list[dict[str, channels.StyleChannel]]]:
    """Resolve scalar, ``(N,)``, or ``(S,N)`` bar style values."""
    if value is None or np.isscalar(value):
        constant, _ = channels.resolve_style_channel(
            value, n_items, label, minimum=minimum, maximum=maximum
        )
        resolved = default if constant is None else float(constant)
        return [resolved] * n_series, [{} for _ in range(n_series)]
    arr = np.asarray(value)
    if n_series == 1 and arr.shape == (n_items,):
        rows = [arr]
    elif arr.shape == (n_series, n_items):
        rows = [arr[index] for index in range(n_series)]
    else:
        raise ValueError(
            f"{label} array must have shape ({n_items},) for one series or "
            f"({n_series}, {n_items}), got {arr.shape}"
        )
    out: list[dict[str, channels.StyleChannel]] = []
    for row in rows:
        _, channel = channels.resolve_style_channel(
            row, n_items, label, minimum=minimum, maximum=maximum
        )
        assert channel is not None
        out.append({key: channel})
    constant = 1.0 if key == "opacity" else default
    return [constant] * n_series, out


def series_corner_radius(
    value: Any,
    n_series: int,
    n_items: int,
    label: str,
) -> tuple[Any, list[dict[str, channels.StyleChannel]]]:
    """Resolve constant radius/pair or direct per-bar radii."""
    arr = np.asarray(value)
    # A plain two-scalar tuple/list remains the existing constant (tip, base)
    # form.  Numeric ndarrays are direct channels, including shape (N, 2).
    if (
        np.isscalar(value)
        or isinstance(value, tuple)
        or (
            isinstance(value, (tuple, list))
            and len(value) == 2
            and all(np.isscalar(item) for item in value)
        )
    ):
        return value, [{} for _ in range(n_series)]
    if n_series == 1 and arr.shape == (n_items,):
        rows, components = [arr], 1
    elif n_series == 1 and arr.shape == (n_items, 2):
        rows, components = [arr], 2
    elif arr.shape == (n_series, n_items):
        rows, components = [arr[index] for index in range(n_series)], 1
    elif arr.shape == (n_series, n_items, 2):
        rows, components = [arr[index] for index in range(n_series)], 2
    else:
        raise ValueError(
            f"{label} array must have shape ({n_items},), ({n_items}, 2), "
            f"({n_series}, {n_items}), or ({n_series}, {n_items}, 2); got {arr.shape}"
        )
    result: list[dict[str, channels.StyleChannel]] = []
    for row in rows:
        _, channel = channels.resolve_style_channel(
            row, n_items, label, minimum=0.0, components=components
        )
        assert channel is not None
        result.append({"corner_radius": channel})
    return 0.0, result


def bar_like(
    self: "Figure",
    kind: str,
    x: ArrayLike,
    y: ArrayLike,
    *,
    name: Optional[str],
    color: Any,
    colors: Optional[list[str]],
    width: Any,
    base: Union[Scalar, ArrayLike],
    mode: str,
    orientation: str,
    series: Optional[list[str]],
    opacity: Any,
    corner_radius: Any = 0.0,
    wedge_gap: float = 0.0,
    stroke: Any = None,
    stroke_width: Any = 0.0,
    artist_alpha: Any = None,
    fill: Union[str, dict[str, str], None] = None,
    style_extra: Optional[dict[str, Any]] = None,
) -> "Figure":
    name = self._optional_text(name, f"{kind} name")
    if mode not in {"grouped", "stacked", "normalized"}:
        raise ValueError(f"{kind} mode must be 'grouped', 'stacked', or 'normalized'")
    if orientation not in {"vertical", "horizontal"}:
        raise ValueError(f"{kind} orientation must be 'vertical' or 'horizontal'")
    if orientation == "horizontal" and getattr(self, "coords", "cartesian") == "polar":
        # A polar bar is an annular sector: the position column is the ANGLE and
        # the value column is the RADIUS. "Horizontal" swaps those roles, which
        # a disc has no meaning for — the renderers all read `pos` as theta
        # regardless, so the bar came out transposed rather than rotated.
        # Refuse it rather than draw a plausible wrong picture (§28).
        raise ValueError(
            f"coords='polar' does not support {kind} orientation='horizontal'; "
            "a polar bar's position is its angle and its value is its radius, "
            "so the orientation is fixed. See spec/design/polar-axes.md."
        )
    category_axis = "x" if orientation == "vertical" else "y"
    pos, category_labels = self._axis_positions_with_labels(x, category_axis)
    # Zero is legal and draws nothing, like the library-wide `line_width=0` rule.
    # A bar of no size is an ordinary DATA state, not an author error: a 0%
    # progress ring, an empty category in aggregated output, and the first frame
    # of a grow animation all produce one. Refusing it made every hand-rolled
    # wedge recipe — the pie/gauge compositions the docs show — die at exactly
    # 0% with "bar width must be positive", a message about the author's code
    # from a value that came out of their data. Negative and non-finite widths
    # are still refused: they are not degenerate, they are meaningless.
    if np.isscalar(width):
        # Scalar widths are overwhelmingly the common path. Preserve the
        # established scalar validator (including bool rejection) without
        # allocating two temporary NumPy arrays for every bar chart.
        try:
            width_values: float | np.ndarray = self._nonnegative_scalar(width, f"{kind} width")
        except ValueError as exc:
            if isinstance(width, (str, bytes)):
                raise ValueError(f"{kind} width must be scalar or contain numeric values") from exc
            raise
    elif isinstance(width, np.ndarray) and width.ndim == 0:
        if np.issubdtype(width.dtype, np.bool_):
            raise ValueError(f"{kind} width must be scalar or contain numeric values")
        width_values = self._nonnegative_scalar(width.item(), f"{kind} width")
    else:
        try:
            raw_width_array = np.asarray(width)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{kind} width must be scalar or contain numeric values") from exc
        if np.issubdtype(raw_width_array.dtype, np.bool_):
            raise ValueError(f"{kind} width must be scalar or contain numeric values")
        try:
            width_array = raw_width_array.astype(np.float64, copy=False)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{kind} width must be scalar or contain numeric values") from exc
        try:
            width_values = np.broadcast_to(width_array, (len(pos),)).astype(np.float64, copy=False)
        except ValueError:
            raise ValueError(
                f"{kind} width must be scalar or broadcast to the {len(pos)} bars"
            ) from None
        if not np.isfinite(width_values).all() or np.any(width_values < 0.0):
            raise ValueError(f"{kind} width values must be finite and non-negative")
    vals = self._bar_value_matrix(y, len(pos), kind)
    n_series, n_items = vals.shape
    if mode == "normalized" and np.any(vals < 0):
        raise ValueError(
            f"{kind} mode='normalized' requires non-negative values; "
            "normalizing mixed-sign stacks is ambiguous"
        )
    base_vals = self._broadcast_base(base, len(pos), kind)
    series_names = self._series_names(name, series, n_series)
    direct_colors = series_direct_paints(color, n_series, n_items, f"{kind} color")
    series_colors = (
        [None] * n_series
        if direct_colors is not None
        else self._series_colors(color, colors, n_series)
    )
    if direct_colors is None:
        # One palette slot per *series* the mark emits — a grouped bar with
        # three series takes three, and each bakes its color here rather than
        # at payload time, where only the trace index is left to cycle on.
        series_colors = [self.next_series_color() if c is None else c for c in series_colors]
    direct_strokes = series_direct_paints(stroke, n_series, n_items, f"{kind} stroke")
    scalar_stroke = stroke if direct_strokes is None else None
    opacity_values, opacity_channels = series_style_values(
        opacity,
        n_series,
        n_items,
        f"{kind} opacity",
        "opacity",
        default=0.85,
        minimum=0.0,
        maximum=1.0,
    )
    stroke_width_values, stroke_width_channels = series_style_values(
        stroke_width,
        n_series,
        n_items,
        f"{kind} stroke_width",
        "stroke_width",
        default=0.0,
        minimum=0.0,
    )
    constant_radius, radius_channels = series_corner_radius(
        corner_radius, n_series, n_items, f"{kind} corner_radius"
    )
    alpha_values, alpha_channels = series_style_values(
        artist_alpha,
        n_series,
        n_items,
        f"{kind} alpha",
        "artist_alpha",
        default=-1.0,
        minimum=-1.0,
        maximum=1.0,
    )
    series_styles: list[dict[str, Any]] = []
    series_channels: list[dict[str, channels.StyleChannel]] = []
    for index in range(n_series):
        mark_style = self._rect_mark_style(
            kind,
            constant_radius,
            scalar_stroke,
            stroke_width_values[index],
            fill,
            wedge_gap,
        )
        mark_style.update(style_extra or {})
        merged_channels = {
            **opacity_channels[index],
            **stroke_width_channels[index],
            **radius_channels[index],
            **alpha_channels[index],
        }
        if alpha_values[index] >= 0.0:
            # Constants remain spec-only. -1 means use intrinsic paint alpha.
            mark_style["artist_alpha"] = alpha_values[index]
        series_styles.append(mark_style)
        series_channels.append(merged_channels)
    if direct_strokes is None and direct_colors is not None:
        resolved_strokes: list[Optional[channels.ColorChannel]] = [
            (
                channels.ColorChannel(mode="match_fill")
                if stroke_width_values[index] or "stroke_width" in series_channels[index]
                else None
            )
            for index in range(n_series)
        ]
    else:
        resolved_strokes = [None] * n_series if direct_strokes is None else list(direct_strokes)
    checkpoint = self._checkpoint()
    try:
        if category_labels is not None:
            self._commit_category_labels(category_labels, category_axis)
        # Width may be scalar or per-category; Rust broadcasts length-1.
        # ``np.isscalar`` does not narrow ``float | ndarray`` for ty.
        width_for_native: float | np.ndarray = (
            width_values if isinstance(width_values, np.ndarray) else float(width_values)
        )
        # Offsets (grouped / stacked / normalized) live in xyg_bar_stack so
        # Python and Node share one layout decision (§28 / dual-host).
        x0s, x1s, y0s, y1s = kernels.bar_stack(
            pos,
            vals,
            width_for_native,
            base_vals,
            mode=mode,
            orientation=orientation,
        )
        for i in range(n_series):
            if n_series == 1:
                role = f"{kind}-normalized" if mode == "normalized" else kind
            elif mode == "grouped":
                role = f"{kind}-grouped"
            else:
                role = f"{kind}-{mode}"
            self._append_rect_trace(
                kind,
                x0s[i],
                x1s[i],
                y0s[i],
                y1s[i],
                name=name if n_series == 1 else series_names[i],
                color=series_colors[i],
                opacity=opacity_values[i],
                role=role,
                orientation=orientation,
                extra_style=series_styles[i],
                color_ch=None if direct_colors is None else direct_colors[i],
                stroke_ch=resolved_strokes[i],
                style_channels=series_channels[i],
            )
    except Exception:
        self._rollback(checkpoint)
        raise
    return self


def bar(
    self: "Figure",
    x: ArrayLike,
    y: ArrayLike,
    *,
    name: Optional[str] = None,
    color: Any = None,
    colors: Optional[list[str]] = None,
    width: Any = 0.8,
    base: Union[Scalar, ArrayLike] = 0.0,
    mode: str = "grouped",
    orientation: str = "vertical",
    series: Optional[list[str]] = None,
    opacity: Any = 0.85,
    corner_radius: Any = 0.0,
    wedge_gap: float = 0.0,
    stroke: Any = None,
    stroke_width: Any = 0.0,
    _artist_alpha: Any = None,
    fill: Union[str, dict[str, str], None] = None,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add vertical bars. 2D y values render grouped, stacked, or
    normalized (per-category fractions summing to 1) series.

    `corner_radius`/`stroke`/`stroke_width` are the CSS border analogues
    rendered into the mark; `fill` accepts a CSS `linear-gradient(...)`
    (spec/api/styling.md#styling-the-marks)."""
    css = styles.compile_mark_style("bar", style)
    color = css.get("color", color)
    opacity = css.get("opacity", opacity)
    corner_radius = css.get("corner_radius", corner_radius)
    wedge_gap = css.get("wedge_gap", wedge_gap)
    stroke = css.get("stroke", stroke)
    stroke_width = css.get("stroke_width", stroke_width)
    fill = css.get("fill", fill)
    return bar_like(
        self,
        "bar",
        x,
        y,
        name=name,
        color=color,
        colors=colors,
        width=width,
        base=base,
        mode=mode,
        orientation=orientation,
        series=series,
        opacity=opacity,
        corner_radius=corner_radius,
        wedge_gap=wedge_gap,
        stroke=stroke,
        stroke_width=stroke_width,
        artist_alpha=_artist_alpha,
        fill=fill,
        style_extra=styles._opacity_channels(css),
    )


def column(
    self: "Figure",
    x: ArrayLike,
    y: ArrayLike,
    *,
    name: Optional[str] = None,
    color: Union[str, Sequence[str], None] = None,
    colors: Optional[list[str]] = None,
    width: Any = 0.8,
    base: Union[Scalar, ArrayLike] = 0.0,
    mode: str = "grouped",
    orientation: str = "vertical",
    series: Optional[list[str]] = None,
    opacity: float = 0.85,
    corner_radius: Union[float, tuple[float, float]] = 0.0,
    wedge_gap: float = 0.0,
    stroke: Optional[str] = None,
    stroke_width: float = 0.0,
    fill: Union[str, dict[str, str], None] = None,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Alias for vertical column charts; shares the bar/rect renderer."""
    css = styles.compile_mark_style("column", style)
    color = css.get("color", color)
    opacity = css.get("opacity", opacity)
    corner_radius = css.get("corner_radius", corner_radius)
    wedge_gap = css.get("wedge_gap", wedge_gap)
    stroke = css.get("stroke", stroke)
    stroke_width = css.get("stroke_width", stroke_width)
    fill = css.get("fill", fill)
    return bar_like(
        self,
        "column",
        x,
        y,
        name=name,
        color=color,
        colors=colors,
        width=width,
        base=base,
        mode=mode,
        orientation=orientation,
        series=series,
        opacity=opacity,
        corner_radius=corner_radius,
        wedge_gap=wedge_gap,
        stroke=stroke,
        stroke_width=stroke_width,
        fill=fill,
        style_extra=styles._opacity_channels(css),
    )
