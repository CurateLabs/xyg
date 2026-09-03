"""Color, size, and style channel resolution."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Optional, Union

import numpy as np
import numpy.typing as npt

from . import _channels_labels as _labels
from . import _validate, config, kernels
from ._channels_colormap import ColormapLike, resolve_colormap
from ._channels_labels import MAX_CATEGORIES
from ._channels_types import DEFAULT_COLORMAP, ColorChannel, SizeChannel, StyleChannel

_finite_scalar = _validate.finite_scalar
_is_categorical = _labels._is_categorical
_literal_color_rgba = _labels._literal_color_rgba
_factorize_categories = _labels._factorize_categories
_as_real_array = _labels._as_real_array
_continuous_domain = _labels._continuous_domain
_size_range = _labels._size_range


def append_continuous(channel: Any, values: npt.NDArray[np.float64], label: str) -> None:
    """Append a continuous channel in amortized O(tail) time.

    Geometry columns already use a capacity-doubling buffer for streaming;
    channel arrays need the same contract. The domain expands monotonically so
    a newly appended value is not silently clamped to the old color/size scale.
    Non-finite values remain valid channel inputs and are handled by the
    existing normalization policy; they do not expand the domain.
    """
    if channel.mode != "continuous" or channel.values is None:
        raise ValueError(f"{label} channel is not continuous")
    tail = np.ascontiguousarray(values, dtype=np.float64).ravel()
    if len(tail) == 0:
        return
    current = channel.values
    n_old = len(current)
    n_new = n_old + len(tail)
    buffer = channel._buffer
    if buffer is None or len(buffer) < n_new:
        capacity = max(n_new, n_old * 2, 1024)
        buffer = np.empty(capacity, dtype=np.float64)
        buffer[:n_old] = current
        channel._buffer = buffer
    elif not (
        np.shares_memory(current, buffer)
        and current.ndim == 1
        and current.size == n_old
        and current.strides == buffer.strides
        and current.__array_interface__["data"][0] == buffer.__array_interface__["data"][0]
    ):
        # `values` is expected to remain the exact prefix view of `_buffer`.
        # Re-copy if a future caller rebinds it, so a stale capacity buffer
        # cannot silently corrupt the retained prefix.
        buffer[:n_old] = current
    buffer[n_old:n_new] = tail
    channel.values = buffer[:n_new]

    finite = tail[np.isfinite(tail)]
    if len(finite):
        lo, hi = channel.domain or _continuous_domain(current)
        channel.domain = (min(lo, float(finite.min())), max(hi, float(finite.max())))


def resolve_color(
    color: Any,
    n: int,
    *,
    colormap: ColormapLike = DEFAULT_COLORMAP,
    default_constant: Union[str, Callable[[], str]],
    domain: Optional[tuple[float, float]] = None,
    palette: Union[list[str], dict[str, str], None] = None,
) -> ColorChannel:
    """Interpret the `color=` argument.

    - `None` / a CSS color string → constant.
    - a length-n array of numbers → continuous (normalized + colormap).
    - a length-n array of strings/categories → categorical (factorized + palette).

    `domain` pins the continuous normalization window (matplotlib's
    vmin/vmax); values outside clip to the colormap ends. `palette` is the
    categorical color cycle (the chart's `xyg.theme(palette=...)`, else the
    built-in CVD-safe default).

    `default_constant` may be a callable, invoked only on the branch that
    actually needs it. Marks pass `Figure.next_series_color` that way so a
    mark given an explicit `color=` never takes a palette slot.
    """
    colormap = resolve_colormap(colormap)
    palette_map = palette if isinstance(palette, dict) else None
    cycle = list(palette_map.values()) if palette_map is not None else list(palette or ())
    cycle = cycle or list(config.DEFAULT_PALETTE)
    if domain is not None:
        lo, hi = float(domain[0]), float(domain[1])
        if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
            raise ValueError(f"color domain must be finite (lo, hi) with lo < hi, got {domain!r}")
        domain = (lo, hi)

    # Constant channels keep the colormap too: it still drives the density
    # ramp when the trace aggregates (§5 Tier 2), and a typo'd name must
    # error here rather than render a silently wrong ramp.
    if color is None:
        constant = default_constant if isinstance(default_constant, str) else default_constant()
        return ColorChannel(mode="constant", constant=constant, colormap=colormap)
    if isinstance(color, str):
        # Literal constant color: validated against the native CSS grammar so
        # a typo errors here instead of rendering a silently wrong mark.
        return ColorChannel(
            mode="constant", constant=_validate.css_color(color, "color"), colormap=colormap
        )

    if hasattr(color, "to_numpy"):
        color = color.to_numpy()
    arr = np.asarray(color)
    if arr.ndim == 2 and arr.shape in {(n, 3), (n, 4)}:
        try:
            flat = np.ascontiguousarray(arr, dtype=np.float64).reshape(-1)
        except (TypeError, ValueError) as exc:
            raise ValueError("direct RGB/RGBA colors must be real numeric") from exc
        try:
            packed = kernels.direct_rgba_admit(flat, int(arr.shape[1]))
        except ValueError as exc:
            raise ValueError(
                "direct RGB/RGBA colors must contain finite values between 0 and 1"
            ) from exc
        rgba = np.ascontiguousarray(packed.reshape(n, 4))
        return ColorChannel(mode="direct_rgba", rgba=rgba)

    if arr.ndim != 1 or len(arr) != n:
        raise ValueError(f"color array must be 1-D length {n}, got shape {arr.shape}")

    if _is_categorical(arr):
        literal = _literal_color_rgba(arr)
        if literal is not None:
            # A list of CSS colors is a per-point paint, not a set of category
            # labels. Factorizing it turned `["#ff0000", "#00ff00"]` into two
            # categories sorted alphabetically and repainted them from the
            # palette — the user asked for red and green and got blue and
            # green, in the wrong order, with a legend of hex codes.
            return ColorChannel(mode="direct_rgba", rgba=literal)
        cats, codes, counts = _factorize_categories(arr)
        if kernels.category_code_width(len(cats)) == 4:
            import warnings

            # The client's palette LUT is 256-wide; beyond that, codes collide
            # in the shader. A categorical scatter with >256 distinct values is
            # rarely legible anyway — warn loudly rather than mis-color silently.
            warnings.warn(
                f"categorical color has {len(cats)} categories; only the first "
                f"{MAX_CATEGORIES} get distinct palette slots (the rest collide). "
                "Consider grouping rare categories or a continuous encoding.",
                RuntimeWarning,
                stacklevel=3,
            )
        elif palette_map is None and len(cats) > len(cycle):
            import warnings

            # The default palette is deliberately eight slots (its adjacency
            # order is the CVD-safety gate; see config.DEFAULT_PALETTE), so
            # category colors repeat modulo its length — as does any shorter
            # `xyg.theme(palette=...)`. Allowed, never silent (§28).
            warnings.warn(
                f"categorical color has {len(cats)} categories but the palette "
                f"has {len(cycle)} colors; colors repeat every {len(cycle)} "
                f"categories (category {len(cycle) + 1} wears category 1's "
                "color). Pass a longer palette, group rare categories, or use a "
                "continuous encoding.",
                RuntimeWarning,
                stacklevel=3,
            )
        if palette_map is not None:
            resolved = kernels.categorical_palette_map_resolve(
                cats,
                palette_map,
                default_palette=list(config.DEFAULT_PALETTE),
            )
            if resolved["unmapped_count"]:
                import warnings

                unmapped = [category for category in cats if category not in palette_map]
                warnings.warn(
                    f"{len(unmapped)} categor{'y' if len(unmapped) == 1 else 'ies'} "
                    f"({', '.join(map(repr, unmapped[:4]))}"
                    f"{', ...' if len(unmapped) > 4 else ''}) are not in the "
                    "xyg.theme(palette={...}) map and fall back to the cycle. Add "
                    "them to the map to pin their colors."
                    + (
                        " The map already pins every built-in color, so those "
                        "fallbacks repeat a color the map assigned to another "
                        "category."
                        if resolved["map_exhausted"]
                        else ""
                    ),
                    RuntimeWarning,
                    stacklevel=3,
                )
            palette_out = resolved["colors"]
        else:
            palette_out = cycle
        return ColorChannel(
            mode="categorical",
            codes=codes,
            categories=cats,
            counts=counts,
            palette=palette_out,
        )

    vals = _as_real_array(arr, "color array")
    return ColorChannel(
        mode="continuous",
        values=vals,
        domain=domain if domain is not None else _continuous_domain(vals),
        colormap=colormap,
    )


def resolve_size(size: Any, n: int, *, range_px: tuple[float, float] = (2.0, 18.0)) -> SizeChannel:
    """Resolve a scatter ``size`` input into a `SizeChannel`.

    A scalar (or None) becomes a constant size; a length-``n`` numeric
    array maps linearly onto ``range_px`` pixels.
    """
    if size is None:
        return SizeChannel(mode="constant")
    if np.isscalar(size):
        constant = _finite_scalar(size, "size")
        if constant < 0:
            raise ValueError("size must be non-negative")
        return SizeChannel(mode="constant", constant=constant)

    if hasattr(size, "to_numpy"):
        size = size.to_numpy()
    arr = np.asarray(size)
    if arr.ndim != 1 or len(arr) != n:
        raise ValueError(f"size array must be 1-D length {n}, got shape {arr.shape}")
    vals = _as_real_array(arr, "size array")
    return SizeChannel(
        mode="continuous",
        values=vals,
        domain=_continuous_domain(vals),
        range_px=_size_range(range_px),
    )


def resolve_style_channel(
    value: Any,
    n: int,
    label: str,
    *,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
    components: int = 1,
) -> tuple[Any, Optional[StyleChannel]]:
    """Return ``(constant, channel)`` for a scalar-or-direct numeric style."""
    if value is None or (np.isscalar(value) and components == 1):
        if value is None:
            return None, None
        constant = _finite_scalar(value, label)
        if minimum is not None and constant < minimum:
            raise ValueError(f"{label} must be at least {minimum}")
        if maximum is not None and constant > maximum:
            raise ValueError(f"{label} must be at most {maximum}")
        return constant, None
    arr = np.asarray(value)
    expected = (n,) if components == 1 else (n, components)
    if arr.shape != expected:
        raise ValueError(f"{label} array must have shape {expected}, got {arr.shape}")
    values = _as_real_array(arr.reshape(-1), f"{label} array").reshape(expected)
    if not kernels.scene_finite_all(values):
        raise ValueError(f"{label} array must contain only finite values")
    if minimum is not None and np.any(values < minimum):
        raise ValueError(f"{label} array values must be at least {minimum}")
    if maximum is not None and np.any(values > maximum):
        raise ValueError(f"{label} array values must be at most {maximum}")
    return None, StyleChannel(np.ascontiguousarray(values), components=components)
