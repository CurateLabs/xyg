"""Figure runtime interaction delegates (widget comm path)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from . import interaction

if TYPE_CHECKING:
    pass


def density_view(
    self, trace_id: int, x0: float, x1: float, y0: float, y1: float, w: int, h: int
) -> tuple[dict[str, Any], list[bytes]]:
    """Re-bin a density-mode scatter's aggregation grid for a new viewport."""
    return interaction.density_view(self, trace_id, x0, x1, y0, y1, w, h)


def pick(
    self, trace_id: int, index: int, drill_seq: Optional[int] = None
) -> Optional[dict[str, Any]]:
    """Exact source-row readout for a hover/pick; `index` is a shipped
    vertex index, translated to a canonical row when NaN rows were dropped
    at ship time. Pass the client's `drill_seq` to reject a pick that
    raced a drill update (wrong index space → None, never a wrong row)."""
    return interaction.pick(self, trace_id, index, drill_seq)


def select_range(
    self, x0: float, x1: float, y0: float, y1: float, trace_id: Optional[int] = None
) -> dict[int, np.ndarray]:
    """Box-select: the canonical row indices inside the box, per scatter trace."""
    return interaction.select_range(self, x0, x1, y0, y1, trace_id)


def select_polygon(self, points: Any, trace_id: Optional[int] = None) -> dict[int, np.ndarray]:
    """Lasso-select → canonical indices per scatter trace."""
    return interaction.select_polygon(self, points, trace_id)


def to_shipped_indices(self, trace_id: int, canonical: np.ndarray) -> np.ndarray:
    """Canonical rows → shipped vertex positions (the client's mask space)."""
    return interaction.to_shipped_indices(self, trace_id, canonical)


def decimate_view(self, x0: float, x1: float, px_width: int) -> tuple[dict[str, Any], list[bytes]]:
    """Re-decimate the visible line windows on zoom, re-centering the
    f32 upload offsets so precision holds at deep zoom."""
    return interaction.decimate_view(self, x0, x1, px_width)


def legend_toggle(self, trace_id: int, hidden: bool, category: Optional[int] = None) -> None:
    """Record a legend visibility toggle: whole trace, or one categorical
    code. Selections, decimation, and density re-bins honor it (§34)."""
    interaction.legend_toggle(self, trace_id, hidden, category)


def append(
    self,
    trace_id: int,
    x: Any,
    y: Any,
    *,
    color: Any = None,
    size: Any = None,
    stroke: Any = None,
    opacity: Any = None,
    alpha: Any = None,
    stroke_width: Any = None,
    symbol: Any = None,
) -> tuple[dict[str, Any], list[memoryview]]:
    """Streaming append: extend a scatter/line trace's canonical columns
    and get the client refresh message back. The widget's `append` sends
    it; headless callers can inspect or discard it. Payloads stay
    screen-bounded, so this is O(pixels) on the wire regardless of how
    much data has accumulated."""
    return interaction.append_data(
        self,
        trace_id,
        x,
        y,
        color,
        size,
        stroke,
        opacity,
        alpha,
        stroke_width,
        symbol,
    )
