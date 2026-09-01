"""Shared multi-group helpers for box / violin (Node ``marks/distribution.js``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from . import kernels
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
