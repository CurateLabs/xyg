"""Hexbin mark — screen-bounded hexagonal density via kernels.hexbin."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from . import channels, columns, kernels, styles
from ._trace import Trace
from ._typing import ArrayLike, Scalar
from .config import DEFAULT_PALETTE

if TYPE_CHECKING:
    from ._figure import Figure


def hexbin(
    self: "Figure",
    x: ArrayLike,
    y: ArrayLike,
    *,
    gridsize: int | tuple[int, int] = 64,
    range: Optional[tuple[tuple[float, float], tuple[float, float]]] = None,
    bins: str = "count",
    C: Optional[ArrayLike] = None,
    reduce_C_function: Callable[[np.ndarray], Scalar] = np.mean,
    mincnt: Optional[int] = None,
    name: Optional[str] = None,
    color: Any = None,
    colormap: channels.ColormapLike = channels.DEFAULT_COLORMAP,
    opacity: float = 0.9,
    style: styles.StyleMapping | None = None,
) -> "Figure":
    """Add a screen-bounded hexagonal density plot.

    Binning is performed by the native ``xyg_hexbin`` kernel (count / mean /
    sum). Rust owns finite-pair filtering, automatic domain, default grid
    aspect, and lattice assignment. Custom ``reduce_C_function`` callables
    receive host-reduced groups from ``xyg_hexbin_groups``. Only threshold-passing
    bins are shipped as centers plus one scalar count/color channel. A literal
    ``color`` keeps constant paint so Cartesian native lattices compile onto
    shared-style Scene PolyFill; omitted ``color`` keeps the metric colormap
    and ABI 186 interns those fills through a 1×N XYHP plane. Polar hexbin,
    custom `reduce_C_function` (after Rust lattice groups), and categorical /
    `direct_rgba` cell paints intern the same way (ABI 194).
    """
    css = styles.compile_mark_style("hexbin", style)
    opacity = css.get("opacity", opacity)
    if isinstance(gridsize, (int, np.integer)) and not isinstance(gridsize, (bool, np.bool_)):
        resolved_gridsize: int | tuple[int, int] = int(gridsize)
        w = int(gridsize)
    elif isinstance(gridsize, (tuple, list)) and len(gridsize) == 2:
        if any(
            isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer))
            for value in gridsize
        ):
            raise ValueError("hexbin gridsize dimensions must be integers")
        w, h = int(gridsize[0]), int(gridsize[1])
        resolved_gridsize = (w, h)
        if h < 2:
            raise ValueError("hexbin gridsize dimensions must be >= 2")
        if h > 2048:
            raise ValueError("hexbin gridsize dimensions must be <= 2048")
    else:
        raise ValueError("hexbin gridsize must be a positive integer or (width, height)")
    if w < 2:
        raise ValueError("hexbin gridsize dimensions must be >= 2")
    if w > 2048:
        raise ValueError("hexbin gridsize dimensions must be <= 2048")
    if bins not in {"count", "log"}:
        raise ValueError("hexbin bins must be 'count' or 'log'")
    name = self._optional_text(name, "hexbin name")
    opacity = self._opacity(opacity, "hexbin opacity")
    colormap = channels.resolve_colormap(colormap)
    # Canonicalize WITHOUT ingesting: only occupied bin centers ship, so the
    # raw points must not stay resident in the figure's column store.
    x_all, _x_kind, _x_copies = columns._canonicalize(x)
    y_all, _y_kind, _y_copies = columns._canonicalize(y)
    if len(x_all) != len(y_all):
        raise ValueError(
            f"hexbin x and y must have equal length, got {len(x_all)} and {len(y_all)}"
        )
    n_points = len(x_all)
    c_all = None
    if C is not None:
        c_all, _c_kind, _c_copies = columns._canonicalize(C)
        if len(c_all) != len(x_all):
            raise ValueError("hexbin C must have the same length as x and y")
    authored_range = None
    if range is not None:
        if len(range) != 2:
            raise ValueError("hexbin range must be ((x0, x1), (y0, y1))")
        authored_range = (
            self._finite_increasing_pair(range[0], "hexbin x range"),
            self._finite_increasing_pair(range[1], "hexbin y range"),
        )
    # Matplotlib displays zero-count cells when C is absent and mincnt is not
    # specified, producing the full rectangular honeycomb. Reducer hexbins
    # cannot reduce an empty group and therefore default to one observation.
    threshold = (0 if c_all is None else 1) if mincnt is None else int(mincnt)
    if threshold < 0:
        raise ValueError("hexbin mincnt must be nonnegative")

    native_reduce: str | None
    if c_all is None:
        native_reduce = "count"
    elif reduce_C_function is np.mean or reduce_C_function is np.nanmean:
        native_reduce = "mean"
    elif reduce_C_function is np.sum or reduce_C_function is np.nansum:
        native_reduce = "sum"
    else:
        native_reduce = None

    if native_reduce is not None:
        try:
            centers_x, centers_y, metric, counts, dx, dy = kernels.hexbin(
                x_all,
                y_all,
                gridsize=resolved_gridsize,
                range=authored_range,
                mincnt=threshold,
                C=c_all,
                reduce=native_reduce,
            )
        except ValueError as exc:
            raise ValueError("hexbin x and y must contain at least one finite pair") from exc
        if len(counts) == 0:
            raise ValueError("hexbin range contains no finite points")
    else:
        # Custom reducers: Rust owns domain/aspect/lattice; host only reduces.
        try:
            centers_x, centers_y, counts, starts, lengths, indices, dx, dy = kernels.hexbin_groups(
                x_all,
                y_all,
                gridsize=resolved_gridsize,
                range=authored_range,
                mincnt=threshold,
                C=c_all,
            )
        except ValueError as exc:
            raise ValueError("hexbin x and y must contain at least one finite pair") from exc
        if len(counts) == 0:
            raise ValueError("hexbin range contains no finite points")
        assert c_all is not None
        reduced: list[float] = []
        for start, length in zip(starts, lengths, strict=True):
            values = c_all[indices[int(start) : int(start) + int(length)]]
            made = np.asarray(reduce_C_function(values))
            if made.ndim != 0 or not np.isfinite(made):
                raise ValueError("hexbin reduce_C_function must return one finite scalar per bin")
            reduced.append(float(made))
        metric = np.asarray(reduced, dtype=np.float64)

    if bins == "log":
        # Matplotlib's ``bins="log"`` is LogNorm over the original cell
        # values. Non-positive cells use the bad color (transparent by
        # default), so omitting them is the same static result while keeping
        # the continuous channel finite. The paint channel can remain the
        # engine's linear normalized scalar after applying log here; the
        # original domain is retained separately for count-space colorbars.
        positive = metric > 0.0
        centers_x, centers_y, metric = (
            centers_x[positive],
            centers_y[positive],
            metric[positive],
        )
        if not len(metric):
            raise ValueError("hexbin logarithmic colors require at least one positive cell value")
        colorbar_domain = (float(np.min(metric)), float(np.max(metric)))
        metric = np.log(metric)
    else:
        colorbar_domain = None
    # Constant ``color`` is the Scene-eligible shared-style paint path. Omitted
    # ``color`` keeps the metric colormap; ABI 186 interned those fills onto
    # HexCell PolyFills through a 1×N XYHP plane.
    paint = color if color is not None else metric
    color_ch = channels.resolve_color(
        paint, len(metric), colormap=colormap, default_constant=DEFAULT_PALETTE[0]
    )
    series_color = color if isinstance(color, str) else self.next_series_color()
    checkpoint = self._checkpoint()
    try:
        self.traces.append(
            Trace(
                id=len(self.traces),
                kind="hexbin",
                x=self.store.ingest(centers_x),
                y=self.store.ingest(centers_y),
                name=name,
                style={
                    "color": series_color,
                    "opacity": opacity,
                    "hex_dx": dx,
                    "hex_dy": dy,
                    "role": "hexbin",
                    "reduce": native_reduce or "custom",
                    **styles._opacity_channels(css),
                },
                color_ch=color_ch,
                colorbar_domain=colorbar_domain,
                colorbar_scale="log" if bins == "log" else "linear",
                size_ch=channels.SizeChannel(mode="constant", constant=8.0),
                count=int(n_points),
            )
        )
        return self
    except Exception:
        self._rollback(checkpoint)
        raise
