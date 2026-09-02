"""Built-in colormap names and custom ramp resolution."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TypeAlias

import numpy as np

from . import _validate, kernels
from ._channels_types import Colormap

ColormapLike: TypeAlias = "str | Sequence[Any]"

COLORMAPS = (
    "viridis",
    "magma",
    "plasma",
    "inferno",
    "cividis",
    "autumn",
    "gray",
    "turbo",
    "coolwarm",
    "blues",
    "rdylgn",
    "rainbow",
    "spectral",
    "piyg",
    "purples",
    "pubu",
    "prgn",
    "rdgy",
    "rdbu",
    "jet",
    "binary",
    "flag",
    "reds",
    "bone",
    "winter",
    "bupu",
    "rdylbu",
    "ylgn",
    "wistia",
    "puor",
)


def is_colormap(name: Any) -> bool:
    return isinstance(name, str) and kernels.colormap_is_builtin(name)


def _is_resolved_stops(value: Any) -> bool:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        return False
    try:
        flat = np.asarray(value, dtype=np.uint8).reshape(-1)
    except (TypeError, ValueError):
        return False
    return kernels.colormap_resolved_stops_admit(flat) > 0


def resolve_colormap(value: ColormapLike, label: str = "colormap") -> Colormap:
    if isinstance(value, str) and is_colormap(value):
        return value
    if _is_resolved_stops(value):
        return [[int(c) for c in stop] for stop in value]  # type: ignore[union-attr]
    if isinstance(value, str) and not value.strip().lower().startswith("linear-gradient("):
        raise ValueError(
            f"unknown colormap {value!r}; expected one of {COLORMAPS}, a "
            "'linear-gradient(...)' string, or a sequence of CSS colors"
        )
    if value is None or isinstance(value, (int, float, bool)):
        raise ValueError(
            f"{label} must be a built-in name, a 'linear-gradient(...)' string, or a "
            f"sequence of CSS colors, got {value!r}"
        )
    return _validate.colormap_stops(value, label)
