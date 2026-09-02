"""Shared LOD argument coercion helpers."""

from __future__ import annotations

import numbers
from typing import Any, cast

import numpy as np


def _integer_param(
    value: object,
    label: str,
    *,
    min_value: int = 0,
    max_value: int | None = None,
) -> int:
    bound = f" and <= {max_value}" if max_value is not None else ""
    message = f"{label} must be an integer >= {min_value}{bound}"
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Integral):
        raise ValueError(message)
    out = int(value)
    if out < min_value:
        raise ValueError(message)
    if max_value is not None and out > max_value:
        raise ValueError(message)
    return out


def _float_param(
    value: object,
    label: str,
    *,
    min_exclusive: float | None = None,
    min_inclusive: float | None = None,
    max_inclusive: float | None = None,
) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{label} must be finite")
    try:
        out = float(cast(Any, value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not np.isfinite(out):
        raise ValueError(f"{label} must be finite")
    if min_exclusive is not None and out <= min_exclusive:
        raise ValueError(f"{label} must be > {min_exclusive}")
    if min_inclusive is not None and out < min_inclusive:
        raise ValueError(f"{label} must be >= {min_inclusive}")
    if max_inclusive is not None and out > max_inclusive:
        raise ValueError(f"{label} must be <= {max_inclusive}")
    return out
