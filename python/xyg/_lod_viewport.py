"""Viewport validation and visible-window helpers."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import kernels


@dataclass(frozen=True)
class ViewportRequest:
    """Normalized client viewport shared by every tiered chart kind.

    Browser and adapter events can send reversed ranges, non-integer screen
    sizes, or malicious non-finite values. This object is the single checked
    boundary before kernels, drill state, or tile caches see a request.
    """

    lo_x: float
    hi_x: float
    lo_y: float
    hi_y: float
    width: int
    height: int

    @classmethod
    def from_client(
        cls,
        x0: float,
        x1: float,
        y0: float,
        y1: float,
        width: int,
        height: int,
        *,
        require_area: bool = True,
    ) -> "ViewportRequest":
        """Build a validated viewport from raw client window/screen values."""
        lo_x, hi_x, lo_y, hi_y = normalize_window(x0, x1, y0, y1, require_area=require_area)
        w, h = screen_shape(width, height)
        return cls(lo_x=lo_x, hi_x=hi_x, lo_y=lo_y, hi_y=hi_y, width=w, height=h)

    @property
    def x_range(self) -> tuple[float, float]:
        """The x window as an ascending ``(lo, hi)``."""
        return (self.lo_x, self.hi_x)

    @property
    def y_range(self) -> tuple[float, float]:
        """The y window as an ascending ``(lo, hi)``."""
        return (self.lo_y, self.hi_y)


def normalize_window(
    x0: float, x1: float, y0: float, y1: float, *, require_area: bool = True
) -> tuple[float, float, float, float]:
    """Order a possibly-flipped request window as (lo_x, hi_x, lo_y, hi_y).

    Browser events are untrusted input at this boundary: reject NaN/inf before
    native kernels see them, and before a failed LOD request can mutate drill
    state.
    """
    if any(isinstance(v, (bool, np.bool_)) for v in (x0, x1, y0, y1)):
        raise ValueError("view window bounds must be finite")
    try:
        vals = [float(v) for v in (x0, x1, y0, y1)]
    except (TypeError, ValueError) as e:
        raise ValueError("view window bounds must be finite") from e
    return kernels.normalize_window(*vals, require_area=require_area)


def screen_shape(w: int, h: int) -> tuple[int, int]:
    """Validate and clamp a browser/client screen shape.

    The floor avoids zero-size canvases causing invisible aggregate grids; the
    cap prevents a hostile client request from allocating an enormous density
    texture. This is shared by scatter density, line re-decimation, and future
    tiered chart kinds.
    """
    if isinstance(w, (bool, np.bool_)) or isinstance(h, (bool, np.bool_)):
        raise ValueError("screen dimensions must be finite")
    try:
        wf = float(w)
        hf = float(h)
    except (TypeError, ValueError) as e:
        raise ValueError("screen dimensions must be finite") from e
    if not np.isfinite(wf) or not np.isfinite(hf):
        raise ValueError("screen dimensions must be finite")
    return kernels.screen_shape(int(wf), int(hf))


def visible_mask(
    xv: np.ndarray, yv: np.ndarray, lo_x: float, hi_x: float, lo_y: float, hi_y: float
) -> np.ndarray:
    """Boolean mask of rows inside the window. NaN/±inf compare False on
    either side, so non-finite rows never enter a drilled subset
    (non-finite must never reach a vertex buffer; design dossier §19)."""
    return kernels.view_visible_mask(xv, yv, lo_x, hi_x, lo_y, hi_y)


def aligned_window(
    lo: float, hi: float, extent_lo: float, extent_hi: float, pad: float
) -> tuple[float, float]:
    """Snap a 1-D window outward to the power-of-two grid over its extent.

    The grid level is a pure function of the extent and the window's span
    bucket: one block spans ``extent / 2**level``, the coarsest level with a
    block no wider than ``pad × span``, and the window's bounds snap outward
    to block edges. Every request whose span falls in the same power-of-two
    bucket therefore resolves to the SAME aligned bounds regardless of pan
    position — full-point buffers aligned by dimension, so client caches can
    key, dedupe, and reuse them (LOD doc T13). The result always CONTAINS the
    input window (client request elision needs containment, and a view panned
    past the data extent must stay contained even though nothing lives there);
    the snapped span stays within ``(1 + 2·pad) × span`` of the input window.

    Decision math lives in Rust (`xyg_aligned_window`, ABI 326); this host only
    coerces arguments.
    """
    return kernels.aligned_window(
        float(lo), float(hi), float(extent_lo), float(extent_hi), float(pad)
    )
