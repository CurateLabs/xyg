"""Line-derivative marks — step, stairs, ECDF, and stem."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Optional, Union

import numpy as np

from . import _validate, kernels, styles
from ._marks_style import stroke_geometry as _stroke_geometry
from ._typing import ArrayLike, Scalar

if TYPE_CHECKING:
    from ._figure import Figure


def step(
    self: "Figure",
    x: ArrayLike,
    y: ArrayLike,
    *,
    where: str = "post",
    name: Optional[str] = None,
    color: Optional[str] = None,
    width: float = 1.5,
    opacity: float = 1.0,
    dash: Union[str, Sequence[float], None] = None,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add a step line without expanding the canonical input columns."""
    if where not in {"pre", "post", "mid"}:
        raise ValueError("step where must be 'pre', 'post', or 'mid'")
    css = styles.compile_mark_style("step", style)
    self.line(
        x,
        y,
        name=name,
        color=css.get("color", color),
        width=css.get("width", width),
        opacity=css.get("opacity", opacity),
        dash=css.get("dash", dash),
    )
    self.traces[-1].style["step"] = where
    self.traces[-1].style.update(styles._opacity_channels(css))
    self.traces[-1].style.update(_stroke_geometry(css))
    return self


def stairs(
    self: "Figure",
    values: ArrayLike,
    edges: Optional[ArrayLike] = None,
    *,
    where: str = "post",
    name: Optional[str] = None,
    color: Optional[str] = None,
    width: float = 1.5,
    opacity: float = 1.0,
    dash: Union[str, Sequence[float], None] = None,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add a Matplotlib-style precomputed stairs series.

    Ships the compact canonical form — the k+1 edges as x plus k+1 values
    with one endpoint duplicated — and lets the step tag do all expansion
    client-side, so bins never pre-expand into polyline vertices. Every
    ``where`` renders bin i at height ``values[i]``; ``mid`` moves the risers
    to the bin centers.
    """
    if where not in {"pre", "post", "mid"}:
        raise ValueError("stairs where must be 'pre', 'post', or 'mid'")
    vals = self._as_1d_float(values, "stairs values")
    if len(vals) == 0:
        raise ValueError("stairs values must contain at least one value")
    if edges is None:
        edge_values = np.arange(len(vals) + 1, dtype=np.float64)
    else:
        edge_values = self._as_1d_float(edges, "stairs edges")
    if len(edge_values) != len(vals) + 1:
        raise ValueError(f"stairs edges must have length {len(vals) + 1}, got {len(edge_values)}")
    if not np.all(np.isfinite(edge_values)) or not np.all(np.diff(edge_values) > 0):
        raise ValueError("stairs edges must be finite and strictly increasing")
    # Step expansion holds each y from its riser onward: "pre" reads the value
    # right of each edge from the next point, so the first value repeats;
    # "post"/"mid" read it from the previous point, so the last value repeats.
    sy = np.concatenate((vals[:1], vals)) if where == "pre" else np.append(vals, vals[-1])
    return self.step(
        edge_values,
        sy,
        where=where,
        name=name,
        color=color,
        width=width,
        opacity=opacity,
        dash=dash,
        style=style,
    )


def ecdf(
    self: "Figure",
    values: ArrayLike,
    *,
    bins: Optional[int] = None,
    name: Optional[str] = None,
    color: Optional[str] = None,
    width: float = 1.5,
    opacity: float = 1.0,
    dash: Union[str, Sequence[float], None] = None,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add an empirical cumulative distribution function.

    Exact mode coalesces repeated values before shipping. ``bins`` provides a
    bounded approximation for very large distributions using the native
    binned-ECDF kernel.
    """
    raw_values = self._as_1d_float(values, "ecdf values")
    if bins is not None:
        if (
            isinstance(bins, (bool, np.bool_))
            or not isinstance(bins, (int, np.integer))
            or int(bins) <= 0
        ):
            raise ValueError("ecdf bins must be a positive integer or None")
        try:
            sx, sy = kernels.binned_ecdf(raw_values, int(bins))
        except ValueError:
            if not np.isfinite(raw_values).any():
                raise ValueError("ecdf values must contain at least one finite value") from None
            raise
        return self.step(
            sx,
            sy,
            where="post",
            name=name,
            color=color,
            width=width,
            opacity=opacity,
            dash=dash,
            style=style,
        )
    finite = np.isfinite(raw_values)
    if not finite.any():
        raise ValueError("ecdf values must contain at least one finite value")
    unique, cdf = kernels.weighted_ecdf(raw_values, np.ones(len(raw_values), dtype=np.float64))
    sx = np.concatenate(([unique[0]], unique))
    sy = np.concatenate(([0.0], cdf))
    return self.step(
        sx,
        sy,
        where="post",
        name=name,
        color=color,
        width=width,
        opacity=opacity,
        dash=dash,
        style=style,
    )


def stem(
    self: "Figure",
    x: ArrayLike,
    y: ArrayLike,
    *,
    base: Union[Scalar, ArrayLike] = 0.0,
    name: Optional[str] = None,
    color: Optional[str] = None,
    width: float = 1.2,
    opacity: float = 1.0,
    marker: bool = True,
    marker_size: float = 5.0,
    symbol: str = "circle",
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add vertical stem segments and optional point markers."""
    css = styles.compile_mark_style("stem", style)
    color = css.get("color", color)
    width = css.get("width", width)
    opacity = css.get("opacity", opacity)
    name = self._optional_text(name, "stem name")
    color = self._optional_css_color(color, "stem color")
    if color is None:
        color = self.next_series_color()
    width = self._positive_scalar(width, "stem width")
    opacity = self._opacity(opacity, "stem opacity")
    marker_size = self._nonnegative_scalar(marker_size, "stem marker_size")
    symbol = _validate.point_symbol(symbol, "stem symbol")
    checkpoint = self._checkpoint()
    try:
        xc, yc = self._ingest_xy(x, y, "stem")
        basev = self._broadcast_base(base, len(xc), "stem")
        self._append_segment_trace(
            "stem",
            xc.values,
            xc.values,
            basev,
            yc.values,
            name=name,
            color=color,
            opacity=opacity,
            width=width,
            role="stem",
            count=len(xc),
            extra_style=styles._opacity_channels(css),
        )
        if marker:
            self.scatter(
                xc.values,
                yc.values,
                name=None,
                color=color,
                size=marker_size,
                opacity=opacity,
                density=None,
                symbol=symbol,
            )
            # Retain the generated relationship for the bounded public Scene
            # exporter.  This is host provenance only: Rust still receives the
            # same ordinary scatter record after the stem record, preserving
            # paint order without adding a Scene schema feature.
            self.traces[-1].style["role"] = "stem-marker"
        return self
    except Exception:
        self._rollback(checkpoint)
        raise
