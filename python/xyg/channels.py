"""Scatter data channels: color and size (§36c — data-driven styling is
spec-level, resolved on the GPU, never CSS).

Transport principle (§2/§29): a per-point channel ships as one compact scalar
plus a small lookup table in the spec — f32 for normalized continuous values,
or u8 for categorical palette indices when the client LUT can represent every
category. Never per-point RGBA (4×) when a scalar + LUT does. So a categorical,
sized scatter is ~13 bytes/point on the wire (x, y, color-code, size-scalar),
matching the §2 "typical scatter ≤ 24 B/pt" budget with headroom.
"""

from __future__ import annotations

from . import _channels_labels as _labels
from . import _channels_lut as _lut
from . import _channels_resolve as _resolve
from . import _channels_ship as _ship
from . import kernels  # noqa: F401 — re-export for test monkeypatch
from ._channels_colormap import COLORMAPS, ColormapLike, is_colormap, resolve_colormap
from ._channels_labels import MAX_CATEGORIES
from ._channels_lut import _QUANTIZE_CHUNK  # noqa: F401
from ._channels_types import (
    DEFAULT_COLORMAP,
    ColorChannel,
    Colormap,
    SizeChannel,
    StyleChannel,
)

append_continuous = _resolve.append_continuous
resolve_color = _resolve.resolve_color
resolve_size = _resolve.resolve_size
resolve_style_channel = _resolve.resolve_style_channel

_is_categorical = _labels._is_categorical
_literal_color_rgba = _labels._literal_color_rgba
_category_label_payload = _labels._category_label_payload
_category_label_kind_and_bytes = _labels._category_label_kind_and_bytes
category_label = _labels.category_label
_category_labels = _labels._category_labels
_value_probe = _labels._value_probe
_object_column_is_stringlike = _labels._object_column_is_stringlike
_use_native_fixed_factorizer = _labels._use_native_fixed_factorizer
_factorize_categories = _labels._factorize_categories
_object_array_is_real_numeric = _labels._object_array_is_real_numeric
_as_real_array = _labels._as_real_array
_size_range = _labels._size_range
_continuous_domain = _labels._continuous_domain

normalize_to_unit = _lut.normalize_to_unit
quantize_unit_u8 = _lut.quantize_unit_u8
_colormap_stops_rgb = _lut._colormap_stops_rgb
colormap_lut_rgba8 = _lut.colormap_lut_rgba8
categorical_palette = _lut.categorical_palette
palette_rgba8 = _lut.palette_rgba8
palette_rows_rgba8 = _lut.palette_rows_rgba8
bins_mean_color = _lut.bins_mean_color
_quantized_lut_idx = _lut._quantized_lut_idx
_quantized_rgba8 = _lut._quantized_rgba8
_folded_codes_u8 = _lut._folded_codes_u8
resolve_bin_colors = _lut.resolve_bin_colors

_wire_encode_plan = _ship._wire_encode_plan
_ship_wire_buffer = _ship._ship_wire_buffer
ship_registry_attach = _ship.ship_registry_attach
ship_channels = _ship.ship_channels
resolve_direct_rgba = _ship.resolve_direct_rgba
ship_color_channel = _ship.ship_color_channel
ship_style_channels = _ship.ship_style_channels

__all__ = [
    "COLORMAPS",
    "DEFAULT_COLORMAP",
    "MAX_CATEGORIES",
    "ColorChannel",
    "Colormap",
    "ColormapLike",
    "SizeChannel",
    "StyleChannel",
    "append_continuous",
    "bins_mean_color",
    "categorical_palette",
    "category_label",
    "colormap_lut_rgba8",
    "is_colormap",
    "normalize_to_unit",
    "palette_rgba8",
    "palette_rows_rgba8",
    "quantize_unit_u8",
    "resolve_bin_colors",
    "resolve_color",
    "resolve_colormap",
    "resolve_direct_rgba",
    "resolve_size",
    "resolve_style_channel",
    "ship_channels",
    "ship_color_channel",
    "ship_registry_attach",
    "ship_style_channels",
]
