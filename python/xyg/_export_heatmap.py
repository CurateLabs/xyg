"""Shared static-export polar heatmap inverse-raster sampling."""

from __future__ import annotations

from typing import Any

import numpy as np

from . import _native, kernels
from ._layout import _PolarProjection
from ._paint import colormap_stops as _colormap_stops
from ._paint import fill_opacity as _fill_opacity

_POLAR_HEATMAP_MAX_DIMENSION = 4096


def polar_heatmap_rgba(
    hm: dict[str, Any],
    blob: bytes,
    cols: list[dict[str, Any]],
    style: dict[str, Any],
    polar: _PolarProjection,
    borrowed: tuple[np.ndarray, ...] = (),
    *,
    output_scale: float = 1.0,
) -> np.ndarray:
    """Inverse-raster a regular heatmap into the visible annular sector.

    The returned image is top-first RGBA and covers ``polar.plot``. Rust (ABI
    207) owns the inverse map; this wrapper colors only the returned source
    cells via ``_heatmap_rgba_samples`` so work stays bounded by output pixels,
    not source cells. ``output_scale`` lets native raster export sample once
    per device pixel; SVG uses the default one sample per logical pixel.
    """
    source_w, source_h = int(hm["w"]), int(hm["h"])
    out_w, out_h, rows, cols_i, source_indices = _native.polar_heatmap_inverse_map(
        polar._metrics,
        polar.plot,
        source_w,
        source_h,
        hm["x_range"],
        hm["y_range"],
        output_scale,
    )
    if out_w > _POLAR_HEATMAP_MAX_DIMENSION or out_h > _POLAR_HEATMAP_MAX_DIMENSION:
        raise ValueError("polar heatmap output exceeds the screen-bounded cap")
    out = np.zeros((out_h, out_w, 4), dtype=np.uint8)
    if len(source_indices):
        out[rows, cols_i] = _heatmap_rgba_samples(
            hm,
            source_indices.astype(np.int64, copy=False),
            blob,
            cols,
            style,
            borrowed,
        )
    return out


def _heatmap_sample_column(
    meta: dict[str, Any],
    indices: np.ndarray,
    blob: bytes,
    borrowed: tuple[np.ndarray, ...],
) -> np.ndarray:
    """Decode only selected rows from one heatmap source column.

    Polar inverse-raster output is screen-bounded. Expanding a source grid
    before sampling defeats that contract (and the raster payload's borrowed
    canonical-f64 path), so this helper indexes the wire/canonical storage
    first and widens only the selected values.
    """
    dtype_name = str(meta.get("dtype", "f32"))
    dtype = {"u8": np.uint8, "f32": np.dtype("<f4"), "f64": np.dtype("<f8")}.get(dtype_name)
    if dtype is None:
        raise ValueError(f"unsupported heatmap column dtype {dtype_name!r}")
    span = int(meta.get("span", 0))
    if span:
        # Do not pass dtype= here: a defensive metadata/array mismatch would
        # cast the *entire* borrowed source before we sample it, defeating the
        # source-bounded contract. Index first, then cast only selected cells.
        values = np.asarray(borrowed[span - 1]).reshape(-1)[: int(meta["len"])]
        selected = values[indices].astype(dtype, copy=False)
    else:
        values = np.frombuffer(
            blob,
            dtype=dtype,
            count=int(meta["len"]),
            offset=int(meta.get("byte_offset", 0)),
        )
        selected = values[indices]
    selected = selected.astype(np.float64, copy=False)
    return selected / (meta.get("scale") or 1.0) + meta.get("offset", 0.0)


def _heatmap_rgba_samples(
    hm: dict[str, Any],
    indices: np.ndarray,
    blob: bytes,
    cols: list[dict[str, Any]],
    style: dict[str, Any],
    borrowed: tuple[np.ndarray, ...],
) -> np.ndarray:
    """Color selected flat heatmap cells without expanding the source grid."""
    from . import _svg

    count = len(indices)
    if "rgba_bufs" in hm:
        rgba = np.empty((count, 4), dtype=np.uint8)
        for channel, column_index in enumerate(hm["rgba_bufs"]):
            values = _svg._heatmap_sample_column(cols[column_index], indices, blob, borrowed)
            rgba[:, channel] = np.clip(values * 255.0, 0.0, 255.0).astype(np.uint8)
        rgba[:, 3] = (rgba[:, 3].astype(np.float64) * _fill_opacity(style)).astype(np.uint8)
        return rgba

    values = _svg._heatmap_sample_column(cols[hm["buf"]], indices, blob, borrowed)
    stops = np.asarray(_colormap_stops(hm.get("colormap", "viridis")), dtype=np.uint8)
    alpha = int(255 * _fill_opacity(style, 0.95))
    if hm.get("enc") == "canonical-f64":
        d0, d1 = (float(value) for value in hm["domain"])
        rgba = kernels.colormap_rgba_canonical(values, len(indices), 1, (d0, d1), stops, alpha)
    else:
        rgba = kernels.colormap_rgba(values, len(indices), 1, stops, alpha)
    return rgba[:, 0, :]
