"""Shared multi-group helpers for box / violin (Node ``marks/distribution.js``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from . import kernels, styles
from ._typing import ArrayLike

if TYPE_CHECKING:
    from ._figure import Figure


def split_by_positions(
    vals: np.ndarray, positions: np.ndarray
) -> tuple[list[np.ndarray], np.ndarray]:
    """Single-pass factorized grouping over per-row positions.

    Output matches ``[vals[positions == p] for p in np.unique(positions)]`` —
    groups in sorted-position order, within-group input order preserved —
    without the O(n·k) rescan. NaN positions keep the mask semantics: NaN never
    compares equal, so a NaN key carries an empty group.
    """
    unique, inverse = np.unique(positions, return_inverse=True)
    order = np.argsort(inverse, kind="stable")
    bounds = np.searchsorted(inverse[order], np.arange(1, len(unique)))
    groups = np.split(vals[order], bounds)
    for i in np.flatnonzero(np.isnan(unique)):
        groups[i] = vals[:0]
    return groups, unique


def distribution_stats(group: np.ndarray) -> tuple[float, float, float, float, float, np.ndarray]:
    """Compatibility helper for one Rust-owned Tukey summary."""
    return kernels.box_stats(np.asarray(group, dtype=np.float64))


def distribution_groups(
    figure: "Figure",
    values: Any,  # 1-D/2-D ArrayLike or a ragged sequence of 1-D datasets
    x: Optional[ArrayLike],
    group: Optional[ArrayLike],
    kind: str,
    category_axis: str = "x",
) -> tuple[list[np.ndarray], np.ndarray]:
    """Return finite value groups and their category/position coordinates.

    Axis categories are resolved with ``commit=False``; callers commit them
    inside their checkpointed try (the `_bar_like` pattern) so a failing build
    leaves no category residue on the figure.
    """
    if x is not None and group is not None:
        raise ValueError(f"{kind} accepts either x or group, not both")
    arr: Optional[np.ndarray] = None
    groups: Optional[list[np.ndarray]] = None
    if (
        isinstance(values, (list, tuple))
        and len(values)
        and all(not isinstance(v, str) and np.ndim(v) == 1 for v in values)
    ):
        # Sequence-of-datasets shape used by column-oriented statistical APIs:
        # one group per item, ragged lengths allowed.
        groups = [figure._as_1d_float(v, f"{kind} values") for v in values]
    else:
        arr = figure._as_float_array(values, f"{kind} values")
        if arr.ndim == 2:
            # Column-oriented, per the box/violin docstrings: one group per column.
            groups = [arr[:, i] for i in range(arr.shape[1])]
    if groups is not None:
        if group is not None:
            raise ValueError(f"{kind} group is only valid with 1-D values")
        if x is None:
            return groups, np.arange(len(groups), dtype=np.float64)
        if np.ndim(x) == 0:
            raise ValueError(f"{kind} x must be 1-D with one label per group")
        positions = figure._axis_positions(x, category_axis, commit=False)
        if len(positions) != len(groups):
            raise ValueError(f"{kind} x must have one label per group")
        return groups, positions
    vals = figure._as_1d_float(arr, f"{kind} values")
    key, key_name = (group, "group") if group is not None else (x, "x")
    if key is None:
        return [vals], np.array([0.0])
    positions = figure._axis_positions(key, category_axis, commit=False)
    if len(positions) != len(vals):
        raise ValueError(f"{kind} {key_name} must have length {len(vals)}, got {len(positions)}")
    return split_by_positions(vals, positions)


def box(
    self: "Figure",
    values: ArrayLike,
    *,
    x: Optional[ArrayLike] = None,
    group: Optional[ArrayLike] = None,
    name: Optional[str] = None,
    color: Optional[str] = None,
    width: float = 0.6,
    opacity: float = 0.85,
    orientation: str = "vertical",
    show_outliers: bool = True,
    outlier_size: float = 4.0,
    style: styles.StyleMapping | None = None,
    whisker_style: styles.StyleMapping | None = None,
    median_style: styles.StyleMapping | None = None,
    outlier_style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add grouped Tukey box plots with independently styleable parts."""
    css = styles.compile_mark_style("box", style)
    whisker_css = styles.compile_mark_style("segments", whisker_style, "box whisker_style")
    median_css = styles.compile_mark_style("segments", median_style, "box median_style")
    styles.compile_mark_style("scatter", outlier_style, "box outlier_style")
    color = css.get("color", color)
    opacity = css.get("opacity", opacity)
    if orientation not in {"vertical", "horizontal"}:
        raise ValueError("box orientation must be 'vertical' or 'horizontal'")
    name = self._optional_text(name, "box name")
    color = self._optional_css_color(color, "box color")
    if color is None:
        color = self.next_series_color()
    width = self._positive_scalar(width, "box width")
    opacity = self._opacity(opacity, "box opacity")
    show_outliers = self._bool_param(show_outliers, "box show_outliers")
    outlier_size = self._nonnegative_scalar(outlier_size, "box outlier_size")
    category_axis = "x" if orientation == "vertical" else "y"
    groups, positions = distribution_groups(
        self, values, x, group, "box", category_axis=category_axis
    )
    offsets = np.empty(len(groups) + 1, dtype=np.uintp)
    offsets[0] = 0
    for index, group_values in enumerate(groups):
        offsets[index + 1] = offsets[index] + len(group_values)
    flat = np.concatenate(groups) if groups else np.empty(0, dtype=np.float64)
    if not np.isfinite(flat).any():
        raise ValueError("box values must contain at least one finite group")
    try:
        geometry = kernels.box_geometry(
            flat,
            offsets,
            np.asarray(positions, dtype=np.float64),
            width,
            orientation,
            show_outliers,
        )
    except ValueError as exc:
        raise ValueError("invalid bounded box geometry") from exc
    checkpoint = self._checkpoint()
    try:
        self._commit_axis_positions(x if x is not None else group, category_axis)
        bx0, by0, bx1, by1 = geometry["body"]
        wx0, wy0, wx1, wy1 = geometry["whiskers"]
        mx0, my0, mx1, my1 = geometry["medians"]
        self._append_segment_trace(
            "box_whisker",
            wx0,
            wx1,
            wy0,
            wy1,
            name=None,
            color=whisker_css.get("color", color),
            opacity=whisker_css.get("opacity", opacity),
            width=whisker_css.get("width", 1.0),
            role="box-whisker",
            extra_style=styles._opacity_channels(whisker_css),
        )
        self._append_rect_trace(
            "box",
            bx0,
            bx1,
            by0,
            by1,
            name=name,
            color=color,
            opacity=opacity,
            role="box",
            extra_style={
                "stroke_width": css.get("stroke_width", 1.0),
                "box_orientation": orientation,
                **({"stroke": css["stroke"]} if "stroke" in css else {}),
                **styles._opacity_channels(css),
            },
        )
        self._append_segment_trace(
            "box_median",
            mx0,
            mx1,
            my0,
            my1,
            name=None,
            color=median_css.get("color", color),
            opacity=median_css.get("opacity", opacity),
            width=median_css.get("width", 1.4),
            role="box-median",
            extra_style=styles._opacity_channels(median_css),
        )
        if show_outliers and len(geometry["outlier_x"]):
            self.scatter(
                geometry["outlier_x"],
                geometry["outlier_y"],
                name=None,
                color=color,
                size=outlier_size,
                opacity=opacity,
                density=None,
                symbol="circle",
                style=outlier_style,
            )
            self.traces[-1].style["role"] = "box-outlier"
        return self
    except Exception:
        self._rollback(checkpoint)
        raise


def violin(
    self: "Figure",
    values: ArrayLike,
    *,
    x: Optional[ArrayLike] = None,
    group: Optional[ArrayLike] = None,
    name: Optional[str] = None,
    color: Optional[str] = None,
    width: float = 0.8,
    bins: int = 64,
    opacity: float = 0.55,
    orientation: str = "vertical",
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add bounded-resolution violin distributions.

    Density estimation and bounded rectangle geometry are computed once in the
    native core (`xyg_violin_rects`); each group ships its fixed ``bins``-sized
    band set. The client draws the bands through the shared instanced
    rectangle path, so input cardinality does not become DOM/GPU object
    cardinality.
    """
    css = styles.compile_mark_style("violin", style)
    color = css.get("color", color)
    opacity = css.get("opacity", opacity)
    if orientation not in {"vertical", "horizontal"}:
        raise ValueError("violin orientation must be 'vertical' or 'horizontal'")
    if (
        isinstance(bins, (bool, np.bool_))
        or not isinstance(bins, (int, np.integer))
        or int(bins) < 4
        or int(bins) > 1024
    ):
        raise ValueError("violin bins must be an integer between 4 and 1024")
    name = self._optional_text(name, "violin name")
    color = self._optional_css_color(color, "violin color")
    if color is None:
        color = self.next_series_color()
    width = self._positive_scalar(width, "violin width")
    opacity = self._opacity(opacity, "violin opacity")
    category_axis = "x" if orientation == "vertical" else "y"
    groups, positions = distribution_groups(
        self, values, x, group, "violin", category_axis=category_axis
    )
    n_bins = int(bins)
    offsets = np.empty(len(groups) + 1, dtype=np.uintp)
    offsets[0] = 0
    for index, group_values in enumerate(groups):
        offsets[index + 1] = offsets[index] + len(group_values)
    flat = np.concatenate(groups) if groups else np.empty(0, dtype=np.float64)
    try:
        rect_x0, rect_y0, rect_x1, rect_y1, _active, _edges, _density = kernels.violin_rects(
            flat, offsets, np.asarray(positions, dtype=np.float64), n_bins, width, orientation
        )
    except ValueError as exc:
        raise ValueError("violin values must contain at least one finite group") from exc
    checkpoint = self._checkpoint()
    try:
        self._commit_axis_positions(x if x is not None else group, category_axis)
        self._append_rect_trace(
            "violin",
            rect_x0,
            rect_x1,
            rect_y0,
            rect_y1,
            name=name,
            color=color,
            opacity=opacity,
            role="violin",
            extra_style=styles._opacity_channels(css),
        )
    except Exception:
        self._rollback(checkpoint)
        raise
    return self
