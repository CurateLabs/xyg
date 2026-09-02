"""Facet data subsetting and column factorization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from . import channels, kernels


def _subset_data(data: Any, mask: np.ndarray, n: int) -> Any:
    """Row-subset a table for one facet panel.

    Only 1-D columns of exactly `n` rows are masked; scalars and short config
    values pass through untouched. Multi-dimensional columns whose first axis
    happens to equal `n` are ambiguous (row-masking would corrupt e.g. a
    heatmap z matrix), so they raise instead of silently guessing.
    """
    if hasattr(data, "iloc"):
        return data.iloc[mask] if len(data) == n else data
    if isinstance(data, Mapping):
        out: dict[Any, Any] = {}
        for key, value in data.items():
            if hasattr(value, "to_numpy"):
                arr = value.to_numpy()
            elif isinstance(value, np.ndarray):
                arr = value
            elif isinstance(value, (list, tuple)):
                try:
                    arr = np.asarray(value)
                except ValueError as exc:
                    raise ValueError(
                        f"facet data column {key!r} is ragged and cannot be row-subset"
                    ) from exc
            else:
                out[key] = value  # scalar/config value, not row data
                continue
            if arr.ndim == 1 and len(arr) == n:
                out[key] = arr[mask]
            elif arr.ndim >= 2 and arr.shape[0] == n:
                raise ValueError(
                    f"facet data column {key!r} is {arr.ndim}-D with first axis {n}; "
                    "faceting cannot row-subset multi-dimensional columns"
                )
            else:
                out[key] = value
        return out
    raise TypeError("facet data must be a mapping or a pandas-like table")


def _label_codes(labels: Sequence[str]) -> tuple[np.ndarray, list[str]]:
    """Dedupe display labels in first-seen order; codes index the dedup list."""
    categories, codes = kernels.label_codes_first_seen(list(labels))
    return codes.astype(np.intp, copy=False), categories


def _facet_values(data: Any, by: Any) -> tuple[np.ndarray, list[str]]:
    """Factorize the facet column into per-row codes + first-seen labels.

    Fixed-width columns factorize in Rust on raw records; object columns
    canonicalize display labels then dedupe in first-seen order. Rows group by
    their `category_label` display string, matching categorical channels.
    """
    if isinstance(by, str):
        if isinstance(data, Mapping):
            if by not in data:
                raise KeyError(f"facet column {by!r} not found in data")
            raw = data[by]
        elif hasattr(data, "__getitem__"):
            try:
                raw = data[by]
            except Exception as exc:
                raise KeyError(f"facet column {by!r} not found in data") from exc
        else:
            raise TypeError("facet_chart by= as a string requires mapping/table data")
    else:
        raw = by
    if hasattr(raw, "to_numpy"):
        raw = raw.to_numpy()
    arr = np.asarray(raw)
    if arr.ndim != 1:
        raise ValueError("facet_chart by= must resolve to a 1-D column")
    if arr.dtype == object:
        return _label_codes(channels._category_labels(arr))
    raw_codes, unique_indices = kernels.factorize_fixed(arr)
    display_labels = channels._category_labels(arr[unique_indices])
    label_codes, labels = _label_codes(display_labels)
    codes = label_codes[raw_codes.astype(np.intp, copy=False)]
    return codes, labels
