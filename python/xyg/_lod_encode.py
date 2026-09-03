"""Offset-encoded geometry columns and wire buffer packing."""

from __future__ import annotations

from typing import Any

import numpy as np

from . import kernels
from ._lod_types import EncodedColumn


class BufferWriter:
    """Accumulates a view-update's binary buffers (typed scalars, never JSON
    numbers). The update spec references entries by index — the same shape
    every tiered chart's incremental updates use."""

    def __init__(self) -> None:
        self.buffers: list[bytes] = []

    def add_f32(self, arr: np.ndarray) -> int:
        """Append ``arr`` as a contiguous f32 buffer; returns its index."""
        self.buffers.append(np.ascontiguousarray(arr, dtype=np.float32).tobytes())
        return len(self.buffers) - 1

    def add_u8(self, arr: np.ndarray) -> int:
        """Append ``arr`` as a flat u8 buffer; returns its index."""
        self.buffers.append(np.ascontiguousarray(arr, dtype=np.uint8).reshape(-1).tobytes())
        return len(self.buffers) - 1

    def add_raw(self, raw: bytes) -> int:
        """Append pre-encoded bytes untouched; returns their index."""
        self.buffers.append(raw)
        return len(self.buffers) - 1

    def add_encoded(self, column: EncodedColumn) -> dict[str, Any]:
        """Append an `EncodedColumn` and return the common `{buf, len, ...meta}` ref."""
        return {"buf": self.add_f32(column.values), "len": column.length, **column.meta}


# Encoded extremes stay well inside f32 (max ~3.4e38); the margin also keeps
# the client's 1/(span*scale) map uniforms clear of f32 subnormals.
F32_SAFE_MAG = 1e37


def f32_safe_scale(offset: float, lo: float, hi: float) -> float:
    """Scale for offset-encoding so finite f64 can never overflow f32
    (nothing non-finite may reach a vertex buffer — a 1e300-magnitude domain
    would otherwise encode to ±inf; design dossier §19). Exactly 1.0 for every
    normal domain, so the common path is unchanged; only absurd magnitudes
    normalize."""
    return float(kernels.f32_safe_scale(float(offset), float(lo), float(hi)))


def encode_f32_values(
    values: Any,
    offset: float,
    lo: float,
    hi: float,
    *,
    kind: str | None = None,
) -> EncodedColumn:
    """Shared offset-encoded geometry primitive for every wire path.

    `offset` chooses the precision center, while `lo`/`hi` describe the
    expected numeric domain used to pick an f32-safe scale. Windowed updates
    usually pass viewport bounds; first-payload columns pass canonical column
    bounds. The optional `kind` rides only in first-payload column tables.
    Offset, scale, and kind presence are ABI 255 ``xyg_encoded_column_meta``.
    """
    vals = np.ascontiguousarray(np.asarray(values, dtype=np.float64).ravel())
    offset_f, scale, has_kind = kernels.encoded_column_meta(
        float(offset), float(lo), float(hi), None if kind is None else str(kind)
    )
    enc = (
        np.empty(0, dtype=np.float32)
        if len(vals) == 0
        else kernels.encode_f32(vals, offset_f, scale)
    )
    meta: dict[str, Any] = {"offset": offset_f, "scale": scale}
    if has_kind:
        meta["kind"] = kind
    return EncodedColumn(meta=meta, values=enc)


def pins_offset_to_zero(scale: str | None) -> bool:
    """Whether `scale` requires the zero origin `geometry_offset` gives it.

    Admission is ABI 216 ``xyg_scale_pins_offset`` (`log` / `symlog`).
    """
    if scale is None:
        return False
    return bool(kernels.scale_pins_offset(scale))


def geometry_offset(scale: str | None, lo: float, hi: float) -> float:
    """Precision center for offset-encoded geometry (§4/§16).

    Linear axes re-center on the window/domain midpoint so f32 precision
    follows the viewport. Log-family axes (log, symlog) pin the offset to
    0.0: the shader applies the transform *after* decoding, and with a large
    midpoint offset the f32 subtraction collapses exactly the values the
    scale exists to separate (symlog's linear hole around zero, log's small
    decades). With offset 0 the encode error is a ~2⁻²⁴ *relative* error,
    which the log-family transform maps to a bounded sub-pixel coordinate
    error at every magnitude."""
    return float(kernels.geometry_offset(pins_offset_to_zero(scale), float(lo), float(hi)))


def encode_window_xy_columns(
    xs: np.ndarray,
    ys: np.ndarray,
    lo_x: float,
    hi_x: float,
    lo_y: float,
    hi_y: float,
    x_scale: str | None = None,
    y_scale: str | None = None,
) -> tuple[EncodedColumn, EncodedColumn]:
    """Window-centered x/y encoding shared by drilled or sampled point updates."""
    x_off = geometry_offset(x_scale, lo_x, hi_x)
    y_off = geometry_offset(y_scale, lo_y, hi_y)
    return (
        encode_f32_values(xs, x_off, lo_x, hi_x),
        encode_f32_values(ys, y_off, lo_y, hi_y),
    )


def add_window_xy(
    writer: BufferWriter,
    xs: np.ndarray,
    ys: np.ndarray,
    lo_x: float,
    hi_x: float,
    lo_y: float,
    hi_y: float,
    x_scale: str | None = None,
    y_scale: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Append a viewport-centered x/y pair to a shared LOD buffer writer.

    Sample overlays, drilldown points, and future point-like bucket expansions
    should share this path so deep-zoom f32 precision and `{buf, len, offset,
    scale}` wire metadata stay identical across tiered chart kinds.
    """
    x_col, y_col = encode_window_xy_columns(xs, ys, lo_x, hi_x, lo_y, hi_y, x_scale, y_scale)
    return writer.add_encoded(x_col), writer.add_encoded(y_col)
