"""Figure column ingest, array coercion, and category-axis position helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from . import _validate, channels, columns

if TYPE_CHECKING:
    from ._figure import Figure


from .columns import Column


def ingest_xy(self: "Figure", x: Any, y: Any, kind: str) -> tuple[Column, Column]:
    """Ingest an (x, y) pair into the column store with the equal-length
    contract every xyg chart shares (line/scatter/area/bar/…)."""
    checkpoint = self.store.checkpoint()
    try:
        try:
            xc, yc = self.store.ingest_pair(x, y)
        except ValueError as error:
            if str(error).startswith("x and y must have equal length"):
                raise ValueError(f"{kind} {error}") from error
            raise
        return xc, yc
    except Exception:
        self.store.rollback(checkpoint)
        raise


def as_1d_float(values: Any, label: str) -> np.ndarray:
    if hasattr(values, "to_numpy"):
        values = values.to_numpy()
    arr = np.asarray(values)
    if arr.ndim != 1:
        raise ValueError(f"{label} must be 1-D, got shape {arr.shape}")
    return real_float_array(arr, label)


def as_float_array(values: Any, label: str) -> np.ndarray:
    arrow = columns._arrow_to_numpy(values)
    if arrow is not None:  # pyarrow channel input: nulls become NaN
        values = arrow[0]
    elif hasattr(values, "to_numpy"):
        values = values.to_numpy()
    arr = np.asarray(values)
    if arr.ndim not in (1, 2):
        raise ValueError(f"{label} must be 1-D or 2-D, got shape {arr.shape}")
    return real_float_array(arr, label)


def real_float_array(arr: np.ndarray, label: str) -> np.ndarray:
    return channels._as_real_array(arr, label)


def bar_value_matrix(values: Any, n_x: int, kind: str) -> np.ndarray:
    arr = as_float_array(values, f"{kind} y")
    if arr.ndim == 1:
        if len(arr) != n_x:
            raise ValueError(f"{kind} x and y must have equal length, got {n_x} and {len(arr)}")
        return arr.reshape(1, n_x)
    if arr.shape[1] == n_x:
        return arr
    if arr.shape[0] == n_x:
        return arr.T
    raise ValueError(
        f"{kind} 2-D y must have one dimension matching x length {n_x}, got {arr.shape}"
    )


def series_names(name: Optional[str], series: Optional[list[str]], n_series: int) -> list[str]:
    if series is not None:
        if len(series) != n_series:
            raise ValueError(f"series must have length {n_series}, got {len(series)}")
        names: list[str] = []
        for i, item in enumerate(series):
            if not isinstance(item, str):
                raise ValueError(f"series[{i}] must be a string")
            names.append(item)
        return names
    if n_series == 1:
        return [name or ""]
    prefix = f"{name} " if name else "series "
    return [f"{prefix}{i + 1}" for i in range(n_series)]


def series_colors(color: Any, colors: Optional[list[str]], n_series: int) -> list[Optional[str]]:
    if colors is not None:
        if len(colors) != n_series:
            raise ValueError(f"colors must have length {n_series}, got {len(colors)}")
        return [_validate.css_color(c, f"colors[{i}]") for i, c in enumerate(colors)]
    if isinstance(color, (list, tuple, np.ndarray)) and not isinstance(color, str):
        color_list: list[Optional[str]] = [
            _validate.css_color(str(c), f"color[{i}]") for i, c in enumerate(color)
        ]
        if len(color_list) != n_series:
            raise ValueError(f"color sequence must have length {n_series}, got {len(color_list)}")
        return color_list
    if color is not None:
        color = _validate.css_color(color, "color")
    return [color for _ in range(n_series)]


def is_category_like(values: Any) -> bool:
    if hasattr(values, "to_numpy"):
        try:
            values = values.to_numpy()
        except ValueError:
            # pyarrow Arrays with nulls refuse the default zero-copy
            # conversion (ArrowInvalid is a ValueError). This is only a
            # dtype probe, so inspect an empty slice instead of paying an
            # O(n) copy of the column.
            values = values[:0].to_numpy(zero_copy_only=False)
    arr = np.asarray(values)
    return channels._is_categorical(arr)


def category_axis_labels(values: Any, axis: str) -> list[str]:
    if hasattr(values, "to_numpy"):
        values = values.to_numpy()
    arr = np.asarray(values)
    if arr.ndim != 1:
        raise ValueError(f"{axis} categories must be 1-D, got shape {arr.shape}")
    if arr.dtype.kind == "U":
        # A unicode array cannot hold missing/bytes values, so
        # `category_label` reduces to `str` — and `tolist()` already
        # yields plain `str`. Skips two O(n) Python passes per axis.
        return arr.tolist()
    return channels._category_labels(arr)


def materialize_sequence(values: Any) -> Any:
    """Convert a plain list/tuple to an ndarray once, so the category
    probe and label extraction below don't each re-run the same O(n)
    conversion (`np.asarray` of an ndarray is free)."""
    if isinstance(values, (list, tuple)):
        return np.asarray(values)
    return values


def category_axis_id(self: "Figure", axis: str) -> str:
    """Resolve a mark channel dimension to its active declarative axis id."""
    return self._active_axis_ids.get(axis, axis)


def axis_positions(self: "Figure", values: Any, axis: str, *, commit: bool = True) -> np.ndarray:
    values = materialize_sequence(values)
    if not is_category_like(values):
        return as_1d_float(values, f"{axis} values")
    raw_labels = category_axis_labels(values, axis)
    axis_id = category_axis_id(self, axis)
    labels = (
        self._axis_categories.setdefault(axis_id, [])
        if commit
        else list(self._axis_categories.get(axis_id, []))
    )
    return category_positions(raw_labels, labels)


def category_positions(raw_labels: list[str], labels: list[str]) -> np.ndarray:
    """Positions for `raw_labels` against `labels`, provisioning new labels
    onto `labels` in first-appearance order (the category-axis contract)."""
    lookup = dict(zip(labels, range(len(labels)), strict=True))
    try:
        # Layered charts resolve the same categories once per mark, so the
        # every-label-known case is the hot one; it runs at C speed.
        return np.fromiter(map(lookup.__getitem__, raw_labels), np.float64, count=len(raw_labels))
    except KeyError:
        pass
    # `dict.fromkeys` dedupes at C speed preserving first appearance, so
    # provisioning touches each distinct new label once.
    new_labels = [label for label in dict.fromkeys(raw_labels) if label not in lookup]
    start = len(labels)
    lookup.update(zip(new_labels, range(start, start + len(new_labels)), strict=True))
    labels.extend(new_labels)
    return np.fromiter(map(lookup.__getitem__, raw_labels), np.float64, count=len(raw_labels))


def axis_positions_with_labels(
    self: "Figure", values: Any, axis: str
) -> tuple[np.ndarray, Optional[list[str]]]:
    """Uncommitted positions plus the normalized labels (None for numeric
    values), so validate-then-commit callers replay the commit as a label
    merge instead of re-running the O(n) conversion."""
    values = materialize_sequence(values)
    if not is_category_like(values):
        return as_1d_float(values, f"{axis} values"), None
    raw_labels = category_axis_labels(values, axis)
    axis_id = category_axis_id(self, axis)
    return category_positions(raw_labels, list(self._axis_categories.get(axis_id, []))), raw_labels


def commit_category_labels(self: "Figure", raw_labels: list[str], axis: str) -> None:
    axis_id = category_axis_id(self, axis)
    labels = self._axis_categories.setdefault(axis_id, [])
    # Insertion-ordered union: existing labels first, then new ones in
    # first-appearance order — identical to the provisioning loop above.
    merged = dict.fromkeys(labels)
    merged.update(dict.fromkeys(raw_labels))
    if len(merged) > len(labels):
        labels[:] = merged


def commit_axis_positions(self: "Figure", values: Any, axis: str) -> None:
    if values is None:
        return
    values = materialize_sequence(values)
    if is_category_like(values):
        commit_category_labels(self, category_axis_labels(values, axis), axis)


def broadcast_base(base: Any, n: int, kind: str) -> np.ndarray:
    if np.isscalar(base):
        return np.full(n, _validate.finite_scalar(base, f"{kind} base"), dtype=np.float64)
    arr = as_1d_float(base, f"{kind} base")
    if len(arr) != n:
        raise ValueError(f"{kind} base must have length {n}, got {len(arr)}")
    return arr


def heatmap_axis_positions(self: "Figure", values: Any, n: int, axis: str) -> np.ndarray:
    if values is None:
        return np.arange(n, dtype=np.float64)
    values = materialize_sequence(values)
    is_category = is_category_like(values)
    pos = axis_positions(self, values, axis, commit=False)
    if len(pos) != n:
        raise ValueError(f"heatmap {axis} must have length {n}, got {len(pos)}")
    if is_category:
        labels = category_axis_labels(values, axis)
        if len(set(labels)) != len(labels):
            raise ValueError(f"heatmap {axis} categories must be unique after normalization")
    return pos


def cell_edges(centers: np.ndarray, label: str) -> np.ndarray:
    centers = np.asarray(centers, dtype=np.float64)
    if centers.ndim != 1:
        raise ValueError(f"{label} centers must be 1-D")
    if len(centers) == 0:
        raise ValueError(f"{label} needs at least one center")
    if len(centers) == 1:
        return np.array([centers[0] - 0.5, centers[0] + 0.5], dtype=np.float64)
    diffs = np.diff(centers)
    if not np.all(np.isfinite(diffs)) or np.any(diffs <= 0):
        raise ValueError(f"{label} centers must be finite and strictly increasing")
    mids = (centers[:-1] + centers[1:]) / 2.0
    first = centers[0] - diffs[0] / 2.0
    last = centers[-1] + diffs[-1] / 2.0
    return np.concatenate(([first], mids, [last])).astype(np.float64, copy=False)
