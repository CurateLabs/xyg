"""Payload column decode shared by static export emitters."""

from __future__ import annotations

from typing import Any

import numpy as np


def column(blob: bytes, meta: dict[str, Any]) -> np.ndarray:
    dtype = np.uint8 if meta.get("dtype") == "u8" else np.float32
    raw = np.frombuffer(blob, dtype=dtype, count=meta["len"], offset=meta["byte_offset"])
    return raw.astype(np.float64) / (meta.get("scale") or 1.0) + meta.get("offset", 0.0)


def column_ref(blob: bytes, cols: list[Any], ref: Any) -> np.ndarray:
    """Resolve a payload column reference (registry index or nested bar descriptor)."""
    if isinstance(ref, dict):
        if "byte_offset" in ref:
            return column(blob, ref)
        if "col" in ref:
            return column(blob, cols[ref["col"]])
        raise TypeError(f"invalid column reference: {ref!r}")
    return column(blob, cols[ref])


def density_column(blob: bytes, meta: dict[str, Any], density: dict[str, Any]) -> np.ndarray:
    """Decode either legacy f32 counts or the compact log-u8 density wire."""
    if density.get("enc") != "log-u8":
        return column(blob, meta)
    values = np.frombuffer(
        blob, dtype=np.uint8, count=meta["len"], offset=meta["byte_offset"]
    ).astype(np.float64)
    maximum = float(density.get("max") or 0.0)
    if maximum <= 0.0:
        return np.zeros(len(values), dtype=np.float64)
    return np.expm1((values / 255.0) * np.log1p(maximum))
