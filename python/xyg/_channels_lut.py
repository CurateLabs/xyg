"""Channel LUT packing, normalization, and density bin color resolution."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional

import numpy as np
import numpy.typing as npt

from . import _native, kernels
from ._channels_types import ColorChannel, Colormap


def normalize_to_unit(values: npt.NDArray[np.float64], domain: tuple[float, float]) -> np.ndarray:
    """Map values to [0,1] over `domain` (for continuous color/size upload).
    Non-finite (NaN, ±inf) → domain floor so it never poisons a vertex
    (design dossier §19); the validity story tightens with real bitmaps
    later."""
    return kernels.normalize_f32(values, domain, nonfinite="zero")


def quantize_unit_u8(values: npt.NDArray[np.float64], domain: tuple[float, float]) -> np.ndarray:
    """Normalize over `domain` and quantize to u8 (0..255 spanning [0,1]).

    The lossy sibling of :func:`normalize_to_unit`, for wire paths where the
    value is only ever a GPU LUT/ramp coordinate (a colormap texture has 256
    texels; a size ramp spans ~16 px) and is never read back into a displayed
    number — 75% less traffic than f32, same rendered output (§29).
    """
    return kernels.quantize_unit_u8(np.ascontiguousarray(values, dtype=np.float64), domain)


def _colormap_stops_rgb(colormap: Colormap) -> npt.NDArray[np.uint8]:
    """RGB stop table for ``kernels.colormap_lut`` / exporter LUT sampling."""
    if isinstance(colormap, str):
        return np.asarray(_native.colormap_stops(colormap), dtype=np.uint8)
    return np.ascontiguousarray(colormap, dtype=np.uint8).reshape(-1, 3)


def colormap_lut_rgba8(colormap: Colormap) -> npt.NDArray[np.uint8]:
    """The client's 256-texel colormap LUT as (256, 4) straight-alpha RGBA8.

    Built from the same stop tables the SVG exporter mirrors from
    `js/src/10_colormaps.ts`, so a value binned through this LUT wears the
    byte-identical color its drawn point does. Packing is ABI 343
    ``xyg_colormap_lut_rgba8``; custom ramps pass resolved RGB stops."""
    if isinstance(colormap, str):
        return kernels.colormap_lut_rgba8(colormap)
    stops = np.asarray(colormap, dtype=np.uint8).reshape(-1, 3)
    return kernels.colormap_lut_rgba8(stops.reshape(-1))


def categorical_palette(palette: list[str], n_categories: int) -> list[str]:
    """The shipped `color.palette`: one color per category, repeating the base
    palette once its colors run out.

    The repeat rule is a wire contract — the client indexes this list by
    category code (and folds wide codes modulo it) — so it has exactly one
    definition, shared by every producer of a categorical color spec."""
    return kernels.categorical_palette(palette, n_categories)


def palette_rgba8(palette: list[str], n_categories: int) -> npt.NDArray[np.uint8]:
    """Categorical palette colors as straight-alpha RGBA8 LUT rows.

    One row per category up to 256; beyond that callers fold codes modulo the
    base palette instead (`resolve_bin_colors`), which is the same repeat rule
    `ship_color_channel` applies.

    This runs kernel-side, with no DOM: a `theme(palette=...)` entry that only a
    browser can resolve (`var()`, `oklch()`) has no fixed channels here. Those
    entries are legal — the browser paints them correctly on the direct tier —
    so the aggregate plane substitutes the built-in palette's color at the same
    index and *says so* (§28), rather than filling the cell black and letting a
    density surface disagree with the points it aggregates."""
    return palette_rows_rgba8(palette, kernels.category_palette_rows(n_categories))


def palette_rows_rgba8(palette: Sequence[str], rows: int) -> npt.NDArray[np.uint8]:
    """`rows` straight-alpha RGBA8 rows for an indexed categorical palette.

    The one place a palette is resolved without a DOM — shared by the density
    mean-color plane, the SVG writer, and the native rasterizer, so the three
    cannot drift. A `theme(palette=...)` entry only a browser can resolve
    (`var()`, `oklch()`) has no fixed channels here; it falls back to the
    built-in palette's color **at the same index**, never to one shared
    fallback, because a shared fallback collapses distinct categories into a
    single indistinguishable color. The substitution warns (§28).

    Row packing is ABI 342 ``xyg_palette_rows_rgba8``; ABI 346 entry-unresolved
    flags drive browser-only warnings without a second CSS parse pass."""
    entries = [str(entry) for entry in palette]
    lut, unresolved_count, entry_flags = kernels.palette_rows_rgba8(entries, rows)
    if unresolved_count:
        import warnings

        bad = [entry for entry, flag in zip(entries, entry_flags, strict=True) if flag]
        warnings.warn(
            f"palette entries {sorted(set(bad))} resolve only in a browser, so "
            "the aggregated density surface and static exports cannot paint them; "
            "those categories fall back to the built-in palette there. Pass literal "
            "colors (hex/rgb()/hsl()/named) for identical color across renderers.",
            RuntimeWarning,
            stacklevel=3,
        )
    return lut


def bins_mean_color(cc: Optional[ColorChannel]) -> bool:
    """Whether this channel aggregates to a mean-color density plane at
    Tier 2 (LOD doc §2) instead of being dropped. Cheap predicate — no
    arrays are touched — for warning/spec sites; `resolve_bin_colors` is
    gated on exactly this."""
    if cc is None:
        return False
    return kernels.density_mean_color_wire_admit(has_channel=True, mode=cc.mode)


# Chunk length for full-column color-source quantization. The math is
# element-wise, so chunking changes nothing but the transient footprint: a
# one-shot pipeline materializes several full-length f64 temporaries at once
# (~20 GB at 1e9 rows — the difference between a colored billion-point build
# fitting in RAM or not), while chunked passes keep every temporary at chunk
# size and the only N-sized allocation is the u8 result.
#
# The chunk is sized so a whole pass (one f32 normalize output + one f64 stage
# array + the u8 slice) stays inside a core's private cache rather than
# streaming through DRAM: at 2^18 rows that is ~3 MB of live temporary, versus
# ~50 MB at 2^22, where "chunked" still meant a 4M-row f64 pipeline for every
# real-world column (a 2.1M-row colored trace fit in a single chunk and paid
# the full one-shot peak). Bigger chunks buy nothing — the per-chunk Python
# overhead is already amortized thousands of elements ago.
_QUANTIZE_CHUNK = 1 << 18


def _quantized_lut_idx(values: npt.NDArray[np.float64], domain: tuple[float, float]) -> np.ndarray:
    """Continuous values -> u8 LUT texel indices via ``quantize_unit_u8``."""
    return quantize_unit_u8(values, domain)


def _quantized_rgba8(values: npt.NDArray[np.float64]) -> np.ndarray:
    """Float RGBA rows -> straight-alpha RGBA8 via ``xyg_clip_quantize_u8``."""
    flat = np.ascontiguousarray(values, dtype=np.float64).reshape(-1)
    return kernels.clip_quantize_u8(flat).reshape(values.shape)


def _folded_codes_u8(codes: np.ndarray, n_palette: int) -> np.ndarray:
    """Wide categorical codes -> u8 palette rows (mod fold)."""
    return kernels.fold_codes_u8(np.asarray(codes, dtype=np.uint32), n_palette)


def resolve_bin_colors(cc: Optional[ColorChannel], sel: Any) -> Optional[dict]:
    """Kernel color source for mean-color density binning (LOD doc §2).

    Returns `kernels.bin_2d_mean_color`-style kwargs — ``{"idx", "lut"}`` for
    palette/colormap channels, ``{"rgba"}`` for direct RGBA — resolved to the
    straight-alpha RGBA8 each point *draws* with, so the aggregated surface
    and the drawn marks share one color story. Constant channels return
    ``None``: their mean is the constant, so the count-only grid plus the
    client-side tint reproduces it exactly with no per-cell color plane.
    """
    if not bins_mean_color(cc):
        return None
    assert cc is not None
    if cc.mode == "direct_rgba":
        rgba = cc.rgba
        if rgba is None:
            raise ValueError("direct RGBA color channel missing values")
        values = rgba if sel is None else rgba[sel]
        return {"rgba": _quantized_rgba8(values)}
    if cc.mode == "continuous":
        values = cc.values
        domain = cc.domain
        if values is None or domain is None:
            raise ValueError("continuous color channel missing values or domain")
        vals = values if sel is None else values[sel]
        # Same normalization the wire ships, quantized to the nearest of the
        # client's 256 LUT texels (chunked: full-column calls keep transient
        # temporaries chunk-bounded instead of several × N).
        return {"idx": _quantized_lut_idx(vals, domain), "lut": colormap_lut_rgba8(cc.colormap)}
    code_values = cc.codes
    categories = cc.categories
    if code_values is None or categories is None:
        raise ValueError("categorical color channel missing codes or categories")
    codes = code_values if sel is None else code_values[sel]
    palette = cc.colors
    if codes.dtype == np.uint8:
        return {"idx": codes, "lut": palette_rgba8(palette, len(categories))}
    # >256 categories ship wide codes; palette colors repeat every
    # len(palette) categories, so folding the codes onto the base palette
    # bins each point with exactly the color it draws with.
    return {
        "idx": _folded_codes_u8(codes, len(palette)),
        "lut": palette_rgba8(palette, len(palette)),
    }
