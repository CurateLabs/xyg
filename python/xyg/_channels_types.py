"""Scatter channel dataclasses (wire spec shapes)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, TypeAlias

import numpy as np
import numpy.typing as npt

from . import config

DEFAULT_COLORMAP = "viridis"
Colormap: TypeAlias = "str | list[list[int]]"


@dataclass
class ColorChannel:
    """Resolved color encoding for a scatter trace."""

    mode: str  # "constant" | "continuous" | "categorical" | "direct_rgba" | "match_fill"
    # constant:
    constant: Optional[str] = None
    # continuous: per-point value normalized to [0,1] at ship time; domain kept
    # for the axis/legend readout (exact, f64 — never through f32, §16).
    values: Optional[npt.NDArray[np.float64]] = None
    domain: Optional[tuple[float, float]] = None
    # Built-in name, or explicit evenly spaced RGB stops (`resolve_colormap`).
    colormap: Colormap = DEFAULT_COLORMAP
    # Declarative source of the continuous values (the `color="temperature"`
    # column-name idiom). Legend/colorbar chrome uses it when the trace itself
    # is unnamed; with neither name nor label the encoding gets no legend row.
    label: Optional[str] = None
    # categorical: integer code per point + the category labels + palette.
    codes: Optional[npt.NDArray[np.uint8] | npt.NDArray[np.uint32]] = None
    categories: Optional[list[str]] = None
    # The categorical color cycle this channel was resolved against — the
    # chart's `xyg.theme(palette=...)`, else config.DEFAULT_PALETTE. Kept on the
    # channel so every consumer (ship, re-bin, legend, export) reads one source
    # instead of reaching for the module default.
    palette: Optional[list[str]] = None
    # Exact dense-code counts, fused into native compact factorization. They
    # let full-domain stratified sampling skip a source-sized recount.
    counts: Optional[npt.NDArray[np.uint64]] = None
    # direct_rgba: canonical straight-alpha float RGBA.  The wire uses packed
    # normalized RGBA8, while keeping the canonical values here lets pyplot
    # getters and post-hoc artist mutation retain Matplotlib semantics.
    rgba: Optional[npt.NDArray[np.float64]] = None
    # Append-only backing storage for streaming continuous channels. Kept out
    # of the wire/spec surface; values remains the exact-length view.
    _buffer: Optional[npt.NDArray[np.float64]] = field(
        default=None, init=False, repr=False, compare=False
    )

    @property
    def colors(self) -> list[str]:
        """The categorical cycle this channel paints with — its own palette
        when the chart set one, else the built-in CVD-safe default."""
        return self.palette or list(config.DEFAULT_PALETTE)

    def spec(self) -> dict[str, Any]:
        """The channel's resolved settings as a plain dict, exactly as
        shipped in the chart spec."""
        if self.mode == "constant":
            return {"mode": "constant", "color": self.constant}
        if self.mode == "continuous":
            spec: dict[str, Any] = {
                "mode": "continuous",
                "colormap": self.colormap,
                "domain": list(self.domain) if self.domain else None,
            }
            if self.label is not None:
                spec["label"] = self.label
            return spec
        if self.mode == "direct_rgba":
            return {"mode": "direct_rgba", "components": 4, "dtype": "u8"}
        if self.mode == "match_fill":
            return {"mode": "match_fill"}
        return {"mode": "categorical", "categories": self.categories}


@dataclass
class StyleChannel:
    """A direct per-mark style channel in final renderer units.

    ``values`` is always canonical f64 except for integer-coded symbols.  The
    payload compiler chooses compact f32/u8 transport and slices it with the
    same row selection as geometry and paint.
    """

    values: np.ndarray
    components: int = 1
    dtype: str = "f32"  # "f32" | "u8"

    def spec(self) -> dict[str, Any]:
        return {"mode": "direct", "components": self.components, "dtype": self.dtype}


@dataclass
class SizeChannel:
    """A resolved scatter size encoding: constant, or values mapped to a
    pixel range. Built by `resolve_size`."""

    mode: str  # "constant" | "continuous"
    constant: float = 4.0
    values: Optional[npt.NDArray[np.float64]] = None
    domain: Optional[tuple[float, float]] = None
    range_px: tuple[float, float] = (2.0, 18.0)
    # See ColorChannel._buffer.
    _buffer: Optional[npt.NDArray[np.float64]] = field(
        default=None, init=False, repr=False, compare=False
    )

    def spec(self) -> dict[str, Any]:
        """The channel's resolved settings as a plain dict, exactly as
        shipped in the chart spec."""
        if self.mode == "constant":
            return {"mode": "constant", "size": self.constant}
        return {
            "mode": "continuous",
            "range_px": list(self.range_px),
            "domain": list(self.domain) if self.domain else None,
        }
