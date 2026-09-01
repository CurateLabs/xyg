"""Stdlib-only smoke test for the native C ABI (no numpy required).

cargo tests cover the kernels; this covers the *boundary* — ctypes signatures,
pointer/struct layout, sentinel values — which is where the Python/Rust seam is
most likely to break and which the Rust tests can't reach. Uses the builtin
`array` module for contiguous typed buffers.

Runs in CI as an early gate before the numpy-backed suite, and is the one
verification that works even when PyPI is unreachable.
"""

from __future__ import annotations

import ctypes
import math
import os
import sys
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _expected_abi_version() -> int:
    """Read ABI_VERSION from the generated ctypes declarations, stdlib-only."""
    path = ROOT / "python" / "xyg" / "_abi_generated.py"
    try:
        source = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(
            f"{path.relative_to(ROOT)} is missing; run "
            "`python3 scripts/gen_abi_manifest.py --write`"
        ) from None
    for line in source.splitlines():
        if line.startswith("ABI_VERSION = "):
            return int(line.split("=", 1)[1].strip())
    raise SystemExit(f"ABI_VERSION not found in {path.relative_to(ROOT)}")


ABI_VERSION = _expected_abi_version()


class CZoneMap(ctypes.Structure):
    _fields_ = [
        ("min", ctypes.c_double),
        ("max", ctypes.c_double),
        ("positive_min", ctypes.c_double),
        ("positive_max", ctypes.c_double),
        ("count", ctypes.c_uint64),
        ("null_count", ctypes.c_uint64),
        ("sum", ctypes.c_double),
        ("sum_sq", ctypes.c_double),
    ]


class PayloadColumnShipEntry(ctypes.Structure):
    _fields_ = [
        ("registry_key", ctypes.c_int32),
        ("trace_slot", ctypes.c_int32),
        ("ship_method", ctypes.c_int32),
        ("ship_scale", ctypes.c_int32),
        ("gather", ctypes.c_uint32),
    ]


class PayloadChannelShipEntry(ctypes.Structure):
    _fields_ = [
        ("registry_key", ctypes.c_int32),
        ("trace_slot", ctypes.c_int32),
        ("ship_method", ctypes.c_int32),
    ]


class PayloadDensityGridBufferEntry(ctypes.Structure):
    _fields_ = [
        ("registry_key", ctypes.c_int32),
        ("buffer_slot", ctypes.c_int32),
        ("ship_method", ctypes.c_int32),
    ]


class PayloadDensityGridAttachEntry(ctypes.Structure):
    _fields_ = [("attach_kind", ctypes.c_int32)]


class SceneXytcTraceStyleIn(ctypes.Structure):
    _fields_ = [
        ("symbol_is_int", ctypes.c_int32),
        ("symbol_int", ctypes.c_uint16),
        ("opacity", ctypes.c_double),
        ("fill_opacity", ctypes.c_double),
        ("stroke_opacity", ctypes.c_double),
        ("line_opacity", ctypes.c_double),
        ("has_stroke", ctypes.c_int32),
        ("has_line_color", ctypes.c_int32),
        ("has_size", ctypes.c_int32),
        ("size", ctypes.c_double),
        ("has_size_ch", ctypes.c_int32),
        ("has_size_ch_constant", ctypes.c_int32),
        ("size_ch_constant", ctypes.c_double),
        ("has_stroke_width", ctypes.c_int32),
        ("stroke_width", ctypes.c_double),
        ("has_width", ctypes.c_int32),
        ("width", ctypes.c_double),
        ("has_line_width", ctypes.c_int32),
        ("line_width", ctypes.c_double),
        ("has_hex_dx", ctypes.c_int32),
        ("hex_dx", ctypes.c_double),
        ("has_hex_dy", ctypes.c_int32),
        ("hex_dy", ctypes.c_double),
        ("has_stroke_perimeter", ctypes.c_int32),
        ("stroke_perimeter_is_bool", ctypes.c_int32),
        ("stroke_perimeter_true", ctypes.c_int32),
        ("dash_is_array", ctypes.c_int32),
        ("has_fill", ctypes.c_int32),
        ("fill_kind", ctypes.c_int32),
        ("color_ch_present", ctypes.c_int32),
        ("color_ch_has_constant", ctypes.c_int32),
        ("radius_seq", ctypes.c_int32),
        ("r0", ctypes.c_double),
        ("r1", ctypes.c_double),
        ("wedge_gap_raw", ctypes.c_double),
        ("symbol_len", ctypes.c_size_t),
        ("dash_len", ctypes.c_size_t),
        ("dash_pattern_len", ctypes.c_size_t),
        ("linecap_len", ctypes.c_size_t),
        ("step_len", ctypes.c_size_t),
        ("curve_len", ctypes.c_size_t),
        ("fill_css_len", ctypes.c_size_t),
        ("fill_space_len", ctypes.c_size_t),
        ("fill_gradient_len", ctypes.c_size_t),
        ("stroke_css_len", ctypes.c_size_t),
        ("line_color_len", ctypes.c_size_t),
        ("color_css_len", ctypes.c_size_t),
        ("color_mode_len", ctypes.c_size_t),
        ("color_const_len", ctypes.c_size_t),
    ]


class SceneXytcTracePackIn(ctypes.Structure):
    _fields_ = [
        ("show_legend", ctypes.c_int32),
        ("has_name", ctypes.c_int32),
        ("marker_path_present", ctypes.c_int32),
        ("use_density", ctypes.c_int32),
        ("joined_fill", ctypes.c_int32),
        ("marker_packed", ctypes.c_int32),
        ("glyph_packed", ctypes.c_int32),
        ("color2_class", ctypes.c_int32),
        ("color2_gradient_packed", ctypes.c_int32),
        ("kind_len", ctypes.c_size_t),
        ("name_len", ctypes.c_size_t),
        ("marker_blob_len", ctypes.c_size_t),
        ("color2_gradient_len", ctypes.c_size_t),
        ("style", SceneXytcTraceStyleIn),
    ]


class SceneXytaTracePackIn(ctypes.Structure):
    _fields_ = [
        ("trace_id", ctypes.c_uint32),
        ("pack_heatmap", ctypes.c_int32),
        ("pack_hexbin_colormap", ctypes.c_int32),
        ("pack_hexbin_rgba", ctypes.c_int32),
        ("pack_ribbon_ends", ctypes.c_int32),
        ("pack_mesh_faces", ctypes.c_int32),
        ("pack_scatter_paint", ctypes.c_int32),
        ("pack_density", ctypes.c_int32),
        ("grid_shape_rows", ctypes.c_double),
        ("grid_shape_cols", ctypes.c_double),
        ("has_grid_shape", ctypes.c_int32),
        ("has_grid", ctypes.c_int32),
        ("has_rgba", ctypes.c_int32),
        ("has_rgba_grid", ctypes.c_int32),
        ("truecolor", ctypes.c_int32),
        ("has_cmap_domain", ctypes.c_int32),
        ("cmap_lo", ctypes.c_double),
        ("cmap_hi", ctypes.c_double),
        ("has_color_ch", ctypes.c_int32),
        ("has_style_color", ctypes.c_int32),
        ("has_opacity", ctypes.c_int32),
        ("has_fill_opacity", ctypes.c_int32),
        ("opacity", ctypes.c_float),
        ("fill_opacity", ctypes.c_float),
        ("domain_x0", ctypes.c_double),
        ("domain_x1", ctypes.c_double),
        ("domain_y0", ctypes.c_double),
        ("domain_y1", ctypes.c_double),
        ("cmap_flags", ctypes.c_uint32),
        ("rows", ctypes.c_int32),
        ("cols", ctypes.c_int32),
        ("grid_len", ctypes.c_size_t),
        ("rgba_len", ctypes.c_size_t),
        ("rgba_grid_len", ctypes.c_size_t),
        ("x_len", ctypes.c_size_t),
        ("y_len", ctypes.c_size_t),
        ("mean_rgba_len", ctypes.c_size_t),
        ("idx_len", ctypes.c_size_t),
        ("lut_len", ctypes.c_size_t),
        ("cmap_len", ctypes.c_size_t),
        ("stops_len", ctypes.c_size_t),
        ("color_ch_len", ctypes.c_size_t),
        ("style_color_len", ctypes.c_size_t),
    ]


def _lib_name() -> str:
    if sys.platform == "win32":
        return "xyg_core.dll"
    if sys.platform == "darwin":
        return "libxyg_core.dylib"
    return "libxyg_core.so"


def load() -> ctypes.CDLL:
    name = _lib_name()
    candidates = []
    env = os.environ.get("XYG_NATIVE_LIB")
    if env:
        candidates.append(Path(env))
    candidates.extend((ROOT / "target" / "release" / name, ROOT / "target" / "debug" / name))
    for cand in candidates:
        if cand.exists():
            lib = ctypes.CDLL(str(cand))
            break
    else:
        raise SystemExit(
            f"{name} not built; run `cargo build --release` "
            f"or set XYG_NATIVE_LIB (looked in {[str(c) for c in candidates]})"
        )

    F64P = ctypes.POINTER(ctypes.c_double)
    F32P = ctypes.POINTER(ctypes.c_float)
    U64P = ctypes.POINTER(ctypes.c_uint64)
    U32P = ctypes.POINTER(ctypes.c_uint32)
    U8P = ctypes.POINTER(ctypes.c_uint8)

    lib.xyg_abi_version.restype = ctypes.c_uint32
    lib.xyg_abi_version.argtypes = []
    got = lib.xyg_abi_version()
    if got != ABI_VERSION:
        raise SystemExit(
            f"xyg native ABI mismatch: wrapper expects {ABI_VERSION}, "
            f"library reports {got}. Rebuild with `cargo build --release`."
        )
    lib.xyg_factorize_fixed.restype = ctypes.c_size_t
    lib.xyg_factorize_fixed.argtypes = [U8P, ctypes.c_size_t, ctypes.c_size_t, U32P, U32P]
    lib.xyg_factorize_fixed_u8.restype = ctypes.c_size_t
    lib.xyg_factorize_fixed_u8.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        U8P,
        U32P,
        ctypes.c_size_t,
    ]
    lib.xyg_factorize_fixed_u8_counts.restype = ctypes.c_size_t
    lib.xyg_factorize_fixed_u8_counts.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        U8P,
        U32P,
        U64P,
        ctypes.c_size_t,
    ]
    lib.xyg_factorize_unicode1_u8_counts.restype = ctypes.c_size_t
    lib.xyg_factorize_unicode1_u8_counts.argtypes = [
        U32P,
        ctypes.c_size_t,
        ctypes.c_int32,
        U8P,
        U32P,
        U64P,
        ctypes.c_size_t,
    ]
    lib.xyg_transition_keys_fixed.restype = ctypes.c_int32
    lib.xyg_transition_keys_fixed.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_uint32,
        ctypes.c_int32,
        U32P,
        U32P,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    lib.xyg_remap_u8.restype = ctypes.c_int32
    lib.xyg_remap_u8.argtypes = [U8P, ctypes.c_size_t, U8P, ctypes.c_size_t]
    lib.xyg_fold_codes_u8.restype = ctypes.c_int32
    lib.xyg_fold_codes_u8.argtypes = [
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_size_t,
        ctypes.c_uint32,
        U8P,
    ]
    lib.xyg_factorize_display_labels.restype = ctypes.c_size_t
    lib.xyg_factorize_display_labels.argtypes = [
        U32P,
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        U32P,
        U32P,
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
    ]
    lib.xyg_label_codes_first_seen.restype = ctypes.c_size_t
    lib.xyg_label_codes_first_seen.argtypes = [
        U32P,
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        U32P,
        U32P,
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
    ]
    lib.xyg_sorted_display_label_remap.restype = ctypes.c_size_t
    lib.xyg_sorted_display_label_remap.argtypes = [
        U32P,
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        U64P,
        U8P,
        ctypes.c_size_t,
        U32P,
        U32P,
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        U64P,
        ctypes.c_size_t,
    ]
    lib.xyg_factorize_use_native_probe.restype = ctypes.c_int32
    lib.xyg_factorize_use_native_probe.argtypes = [
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
    ]
    lib.xyg_factorize_use_native_fixed.restype = ctypes.c_int32
    lib.xyg_factorize_use_native_fixed.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.c_uint32,
    ]
    lib.xyg_category_labels_packed.restype = ctypes.c_size_t
    lib.xyg_category_labels_packed.argtypes = [
        U8P,
        U32P,
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        U32P,
        U8P,
        ctypes.c_size_t,
    ]
    lib.xyg_object_rows_all_stringlike.restype = ctypes.c_int32
    lib.xyg_object_rows_all_stringlike.argtypes = [U8P, ctypes.c_size_t]
    lib.xyg_object_rows_all_real_numeric.restype = ctypes.c_int32
    lib.xyg_object_rows_all_real_numeric.argtypes = [U8P, ctypes.c_size_t]
    lib.xyg_encode_f32.restype = ctypes.c_int32
    lib.xyg_encode_f32.argtypes = [F64P, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, F32P]
    lib.xyg_geometry_offset.restype = ctypes.c_int32
    lib.xyg_geometry_offset.argtypes = [
        ctypes.c_int32,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
    ]
    lib.xyg_f32_safe_scale.restype = ctypes.c_int32
    lib.xyg_f32_safe_scale.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
    ]
    lib.xyg_m4_indices.restype = ctypes.c_size_t
    lib.xyg_m4_indices.argtypes = [
        F64P,
        F64P,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_size_t,
        U32P,
    ]
    lib.xyg_zone_maps.restype = ctypes.c_size_t
    lib.xyg_zone_maps.argtypes = [F64P, ctypes.c_size_t, ctypes.c_size_t] + [
        F64P,
        F64P,
        U64P,
        U64P,
        F64P,
        F64P,
        F64P,
        F64P,
    ]
    lib.xyg_zone_maps_pair.restype = ctypes.c_size_t
    lib.xyg_zone_maps_pair.argtypes = [
        F64P,
        F64P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.POINTER(CZoneMap),
        ctypes.POINTER(CZoneMap),
    ]
    lib.xyg_min_max.restype = ctypes.c_int32
    lib.xyg_min_max.argtypes = [F64P, ctypes.c_size_t, F64P, F64P]
    lib.xyg_css_is_functional.restype = ctypes.c_int32
    lib.xyg_css_is_functional.argtypes = [U8P, ctypes.c_size_t]
    lib.xyg_scale_pins_offset.restype = ctypes.c_int32
    lib.xyg_scale_pins_offset.argtypes = [U8P, ctypes.c_size_t]
    lib.xyg_encoded_column_meta.restype = ctypes.c_int32
    lib.xyg_encoded_column_meta.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        U8P,
        ctypes.c_size_t,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_scene_dash_admit.restype = ctypes.c_int32
    lib.xyg_scene_dash_admit.argtypes = [
        U8P,
        ctypes.c_size_t,
        F64P,
        ctypes.c_size_t,
        ctypes.c_int32,
        F64P,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    lib.xyg_scene_linecap_admit.restype = ctypes.c_int32
    lib.xyg_scene_linecap_admit.argtypes = [U8P, ctypes.c_size_t]
    lib.xyg_density_overlay_opacity.restype = ctypes.c_int32
    lib.xyg_density_overlay_opacity.argtypes = [ctypes.c_double, F64P]
    lib.xyg_scene_marker_path_admit.restype = ctypes.c_int32
    lib.xyg_scene_marker_path_admit.argtypes = [F64P, ctypes.c_size_t, U32P, ctypes.c_size_t]
    lib.xyg_scene_annotation_style_admit.restype = ctypes.c_int32
    lib.xyg_scene_annotation_style_admit.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.c_uint8,
        ctypes.c_uint8,
        U8P,
        ctypes.c_size_t,
    ]
    lib.xyg_scene_ribbon_color2_classify.restype = ctypes.c_int32
    lib.xyg_scene_ribbon_color2_classify.argtypes = [
        ctypes.c_uint8,
        ctypes.c_uint8,
        ctypes.c_uint8,
        U8P,
        ctypes.c_size_t,
        ctypes.c_uint8,
        U8P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        ctypes.c_uint8,
        ctypes.c_uint8,
    ]
    lib.xyg_scene_tick_label_strategy.restype = ctypes.c_int32
    lib.xyg_scene_tick_label_strategy.argtypes = [U8P, ctypes.c_size_t]
    lib.xyg_scene_tick_anchor.restype = ctypes.c_int32
    lib.xyg_scene_tick_anchor.argtypes = [U8P, ctypes.c_size_t]
    lib.xyg_scene_fill_gradient_admit.restype = ctypes.c_int32
    lib.xyg_scene_fill_gradient_admit.argtypes = [
        U8P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        F64P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        U32P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
    ]
    lib.xyg_scene_parse_linear_gradient.restype = ctypes.c_int32
    lib.xyg_scene_parse_linear_gradient.argtypes = [
        U8P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        U8P,
        F64P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        U32P,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    lib.xyg_scene_rect_extra_flags.restype = ctypes.c_int32
    lib.xyg_scene_rect_extra_flags.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        F64P,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_double,
    ]
    lib.xyg_scene_gradient_dir.restype = ctypes.c_int32
    lib.xyg_scene_gradient_dir.argtypes = [U8P, ctypes.c_size_t]
    lib.xyg_scene_linear_gradient_prefix.restype = ctypes.c_int32
    lib.xyg_scene_linear_gradient_prefix.argtypes = [U8P, ctypes.c_size_t]
    lib.xyg_scene_gradient_space.restype = ctypes.c_int32
    lib.xyg_scene_gradient_space.argtypes = [U8P, ctypes.c_size_t]
    lib.xyg_scene_hexbin_reduce_admit.restype = ctypes.c_int32
    lib.xyg_scene_hexbin_reduce_admit.argtypes = [U8P, ctypes.c_size_t]
    lib.xyg_scene_curve_classify.restype = ctypes.c_int32
    lib.xyg_scene_curve_classify.argtypes = [U8P, ctypes.c_size_t]
    lib.xyg_scene_marker_glyph_admit.restype = ctypes.c_int32
    lib.xyg_scene_marker_glyph_admit.argtypes = [U8P, ctypes.c_size_t]
    lib.xyg_scene_kind_admit.restype = ctypes.c_int32
    lib.xyg_scene_kind_admit.argtypes = [U8P, ctypes.c_size_t]
    lib.xyg_scene_kind_class.restype = ctypes.c_int32
    lib.xyg_scene_kind_class.argtypes = [U8P, ctypes.c_size_t]
    lib.xyg_scene_hexbin_pitch_admit.restype = ctypes.c_int32
    lib.xyg_scene_hexbin_pitch_admit.argtypes = [ctypes.c_double, ctypes.c_double]
    lib.xyg_scene_heatmap_extent_admit.restype = ctypes.c_int32
    lib.xyg_scene_heatmap_extent_admit.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
    ]
    lib.xyg_scene_heatmap_colormap_admit.restype = ctypes.c_int32
    lib.xyg_scene_heatmap_colormap_admit.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
    ]
    lib.xyg_scene_xyta_colormap_pack.restype = ctypes.c_int32
    lib.xyg_scene_xyta_colormap_pack.argtypes = [
        ctypes.c_int32,
        U8P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint32),
        U8P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
    ]
    lib.xyg_scene_xyhf_colormap_pack.restype = ctypes.c_int32
    lib.xyg_scene_xyhf_colormap_pack.argtypes = [
        ctypes.c_int32,
        U8P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint32),
        U8P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
    ]
    lib.xyg_scene_gradient_spec_pack.restype = ctypes.c_int32
    lib.xyg_scene_gradient_spec_pack.argtypes = [
        U8P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        F64P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        U32P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
    ]
    lib.xyg_scene_marker_blob_pack.restype = ctypes.c_int32
    lib.xyg_scene_marker_blob_pack.argtypes = [
        ctypes.c_int32,
        F64P,
        ctypes.c_size_t,
        U32P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
    ]
    lib.xyg_scene_xytc_dash_pattern_pack.restype = ctypes.c_int32
    lib.xyg_scene_xytc_dash_pattern_pack.argtypes = [
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    lib.xyg_scene_xytc_paint_presence_pack.restype = ctypes.c_int32
    lib.xyg_scene_xytc_paint_presence_pack.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    lib.xyg_scene_xytc_meta_flags_pack.restype = ctypes.c_int32
    lib.xyg_scene_xytc_meta_flags_pack.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        U8P,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    lib.xyg_scene_xytc_figure_plan.restype = ctypes.c_int32
    lib.xyg_scene_xytc_figure_plan.argtypes = [
        ctypes.c_int32,
        ctypes.c_void_p,
    ]
    lib.xyg_scene_xytc_trace_dispatch_plan.restype = ctypes.c_int32
    lib.xyg_scene_xytc_trace_dispatch_plan.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_void_p,
    ]
    lib.xyg_scene_xyta_figure_plan.restype = ctypes.c_int32
    lib.xyg_scene_xyta_figure_plan.argtypes = [
        ctypes.c_int32,
        ctypes.c_void_p,
    ]
    lib.xyg_scene_xyta_trace_dispatch_plan.restype = ctypes.c_int32
    lib.xyg_scene_xyta_trace_dispatch_plan.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_void_p,
    ]
    lib.xyg_scene_xytc_trace_pack.restype = ctypes.c_int32
    lib.xyg_scene_xytc_trace_pack.argtypes = [
        ctypes.POINTER(SceneXytcTracePackIn),
        U8P,
        U8P,
        U8P,
        U8P,
        F64P,
        U8P,
        U8P,
        U8P,
        U8P,
        U8P,
        U8P,
        U8P,
        U8P,
        U8P,
        U8P,
        U8P,
        U8P,
        U8P,
        U8P,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    lib.xyg_scene_xyta_trace_pack.restype = ctypes.c_int32
    lib.xyg_scene_xyta_trace_pack.argtypes = [
        ctypes.POINTER(SceneXytaTracePackIn),
        U8P,
        U8P,
        U8P,
        U8P,
        U8P,
        U8P,
        U8P,
        U8P,
        U8P,
        U8P,
        U8P,
        U8P,
        U8P,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    lib.xyg_scene_figure_support_figure_plan.restype = ctypes.c_int32
    lib.xyg_scene_figure_support_figure_plan.argtypes = [
        ctypes.c_int32,
        ctypes.c_void_p,
    ]
    lib.xyg_scene_figure_support_trace_dispatch_plan.restype = ctypes.c_int32
    lib.xyg_scene_figure_support_trace_dispatch_plan.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_void_p,
    ]
    lib.xyg_scene_xycl_figure_plan.restype = ctypes.c_int32
    lib.xyg_scene_xycl_figure_plan.argtypes = [
        ctypes.c_int32,
        ctypes.c_void_p,
    ]
    lib.xyg_scene_xynm_figure_plan.restype = ctypes.c_int32
    lib.xyg_scene_xynm_figure_plan.argtypes = [
        ctypes.c_int32,
        ctypes.c_void_p,
    ]
    lib.xyg_scene_xycf_figure_plan.restype = ctypes.c_int32
    lib.xyg_scene_xycf_figure_plan.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_void_p,
    ]
    lib.xyg_scene_xyaf_annotation_dispatch_plan.restype = ctypes.c_int32
    lib.xyg_scene_xyaf_annotation_dispatch_plan.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_void_p,
    ]
    lib.xyg_scene_public_export_figure_plan.restype = ctypes.c_int32
    lib.xyg_scene_public_export_figure_plan.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_void_p,
    ]
    lib.xyg_scene_public_export_trace_dispatch_plan.restype = ctypes.c_int32
    lib.xyg_scene_public_export_trace_dispatch_plan.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_void_p,
    ]
    lib.xyg_scene_polar_figure_plan.restype = ctypes.c_int32
    lib.xyg_scene_polar_figure_plan.argtypes = [
        ctypes.c_int32,
        ctypes.c_void_p,
    ]
    lib.xyg_scene_encode_product_attach_plan.restype = ctypes.c_int32
    lib.xyg_scene_encode_product_attach_plan.argtypes = [
        ctypes.c_int32,
        ctypes.c_void_p,
    ]
    lib.xyg_scene_xytc_color2_flags_pack.restype = ctypes.c_int32
    lib.xyg_scene_xytc_color2_flags_pack.argtypes = [
        ctypes.c_int32,
        ctypes.c_uint32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    lib.xyg_scene_xytc_symbol_int_pack.restype = ctypes.c_int32
    lib.xyg_scene_xytc_symbol_int_pack.argtypes = [
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    lib.xyg_scene_xytc_opacity_pack.restype = ctypes.c_int32
    lib.xyg_scene_xytc_opacity_pack.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
        F64P,
        F64P,
    ]
    lib.xyg_scene_xytc_hex_pitch_pack.restype = ctypes.c_int32
    lib.xyg_scene_xytc_hex_pitch_pack.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.POINTER(ctypes.c_uint32),
        F64P,
        F64P,
    ]
    lib.xyg_scene_xytc_stroke_perimeter_pack.restype = ctypes.c_int32
    lib.xyg_scene_xytc_stroke_perimeter_pack.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    lib.xyg_scene_xytc_numeric_style_pack.restype = ctypes.c_int32
    lib.xyg_scene_xytc_numeric_style_pack.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.POINTER(ctypes.c_uint32),
        F64P,
        F64P,
        F64P,
        F64P,
        F64P,
    ]
    lib.xyg_scene_xytc_color_channel_pack.restype = ctypes.c_int32
    lib.xyg_scene_xytc_color_channel_pack.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    lib.xyg_scene_xytc_radius_pack.restype = ctypes.c_int32
    lib.xyg_scene_xytc_radius_pack.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.POINTER(ctypes.c_uint32),
        F64P,
        F64P,
        F64P,
    ]
    lib.xyg_scene_heatmap_shape_admit.restype = ctypes.c_int32
    lib.xyg_scene_heatmap_shape_admit.argtypes = [ctypes.c_double, ctypes.c_double]
    lib.xyg_scene_scatter_paint_channel_admit.restype = ctypes.c_int32
    lib.xyg_scene_scatter_paint_channel_admit.argtypes = [U8P, ctypes.c_size_t]
    lib.xyg_scene_hexbin_colormap_plane_admit.restype = ctypes.c_int32
    lib.xyg_scene_hexbin_colormap_plane_admit.argtypes = [U8P, ctypes.c_size_t, ctypes.c_int32]
    lib.xyg_scene_hexbin_rgba_plane_admit.restype = ctypes.c_int32
    lib.xyg_scene_hexbin_rgba_plane_admit.argtypes = [U8P, ctypes.c_size_t]
    lib.xyg_scene_mesh_paint_plane_admit.restype = ctypes.c_int32
    lib.xyg_scene_mesh_paint_plane_admit.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
    ]
    lib.xyg_scene_item_apply_opacity.restype = ctypes.c_int32
    lib.xyg_scene_item_apply_opacity.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        F64P,
        ctypes.c_size_t,
        ctypes.c_int32,
        F64P,
        ctypes.c_size_t,
        ctypes.c_int32,
        U8P,
        ctypes.c_size_t,
    ]
    lib.xyg_scene_item_widths_admit.restype = ctypes.c_int32
    lib.xyg_scene_item_widths_admit.argtypes = [
        F64P,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_size_t,
        ctypes.c_double,
    ]
    lib.xyg_scene_item_fill_t.restype = ctypes.c_int32
    lib.xyg_scene_item_fill_t.argtypes = [
        F64P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_int32,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_scene_finite_all.restype = ctypes.c_int32
    lib.xyg_scene_finite_all.argtypes = [F64P, ctypes.c_size_t]
    lib.xyg_scene_gradient_solid_css.restype = ctypes.c_int32
    lib.xyg_scene_gradient_solid_css.argtypes = [U8P, ctypes.c_size_t, U8P, ctypes.c_size_t]
    lib.xyg_scene_arrays_equal.restype = ctypes.c_int32
    lib.xyg_scene_arrays_equal.argtypes = [F64P, ctypes.c_size_t, F64P, ctypes.c_size_t]
    lib.xyg_scene_constant_color_admit.restype = ctypes.c_int32
    lib.xyg_scene_constant_color_admit.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
    ]
    lib.xyg_scene_hidden_or_per_item_admit.restype = ctypes.c_int32
    lib.xyg_scene_hidden_or_per_item_admit.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
    ]
    lib.xyg_scene_channel_constant_css.restype = ctypes.c_int32
    lib.xyg_scene_channel_constant_css.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.c_int32,
        U8P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
    ]
    lib.xyg_clip_quantize_u8.restype = ctypes.c_int32
    lib.xyg_clip_quantize_u8.argtypes = [F64P, ctypes.c_size_t, U8P, ctypes.c_size_t]
    lib.xyg_quantize_unit_u8.restype = ctypes.c_int32
    lib.xyg_quantize_unit_u8.argtypes = [
        F64P,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        U8P,
    ]
    lib.xyg_continuous_domain.restype = ctypes.c_int32
    lib.xyg_continuous_domain.argtypes = [F64P, ctypes.c_size_t, F64P, F64P]
    lib.xyg_direct_rgba_admit.restype = ctypes.c_size_t
    lib.xyg_direct_rgba_admit.argtypes = [
        F64P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_is_sorted.restype = ctypes.c_int32
    lib.xyg_is_sorted.argtypes = [F64P, ctypes.c_size_t]
    lib.xyg_argsort_stable.restype = ctypes.c_size_t
    lib.xyg_argsort_stable.argtypes = [F64P, ctypes.c_size_t, U32P, ctypes.c_size_t]
    D = ctypes.c_double
    Z = ctypes.c_size_t
    lib.xyg_bin_2d.restype = ctypes.c_int32
    lib.xyg_bin_2d.argtypes = [F64P, F64P, Z, D, D, D, D, Z, Z, F32P]
    lib.xyg_bin_2d_indices.restype = ctypes.c_size_t
    lib.xyg_bin_2d_indices.argtypes = [F64P, F64P, Z, D, D, D, D, Z, Z, F32P, U32P]
    lib.xyg_bin_2d_sample_range.restype = ctypes.c_size_t
    lib.xyg_bin_2d_sample_range.argtypes = [
        F64P,
        F64P,
        Z,
        D,
        D,
        D,
        D,
        Z,
        Z,
        ctypes.c_uint64,
        ctypes.c_uint64,
        F32P,
        U32P,
        Z,
    ]
    lib.xyg_bin_2d_stratified_sample_range_u8_counted.restype = ctypes.c_size_t
    lib.xyg_bin_2d_stratified_sample_range_u8_counted.argtypes = [
        F64P,
        F64P,
        ctypes.POINTER(ctypes.c_uint8),
        Z,
        U64P,
        Z,
        D,
        D,
        D,
        D,
        Z,
        Z,
        ctypes.c_uint64,
        D,
        ctypes.c_uint64,
        F32P,
        U32P,
        Z,
    ]
    lib.xyg_histogram_uniform.restype = ctypes.c_size_t
    lib.xyg_histogram_uniform.argtypes = [
        F64P,
        ctypes.c_size_t,
        D,
        D,
        ctypes.c_size_t,
        ctypes.c_int32,
        F64P,
    ]
    lib.xyg_normalize_f32.restype = ctypes.c_int32
    lib.xyg_normalize_f32.argtypes = [F64P, ctypes.c_size_t, D, D, ctypes.c_int32, F32P]
    lib.xyg_valid_indices_f64.restype = ctypes.c_size_t
    lib.xyg_valid_indices_f64.argtypes = [ctypes.POINTER(F64P), Z, Z, ctypes.c_uint64, U32P, Z]
    lib.xyg_range_indices.restype = ctypes.c_size_t
    lib.xyg_range_indices.argtypes = [F64P, F64P, ctypes.c_size_t, D, D, D, D, U32P]
    lib.xyg_sample_mask.restype = ctypes.c_int32
    lib.xyg_sample_mask.argtypes = [
        U64P,
        ctypes.c_size_t,
        ctypes.c_uint64,
        ctypes.c_uint64,
        ctypes.POINTER(ctypes.c_uint8),
    ]
    lib.xyg_sample_mask_u32.restype = ctypes.c_int32
    lib.xyg_sample_mask_u32.argtypes = [
        U32P,
        ctypes.c_size_t,
        ctypes.c_uint64,
        ctypes.c_uint64,
        ctypes.POINTER(ctypes.c_uint8),
    ]
    lib.xyg_sample_threshold.restype = ctypes.c_uint64
    lib.xyg_sample_threshold.argtypes = [D]
    lib.xyg_hash_row_ids.restype = ctypes.c_int32
    lib.xyg_hash_row_ids.argtypes = [U64P, ctypes.c_size_t, ctypes.c_uint64, U64P]
    lib.xyg_sample_fraction.restype = D
    lib.xyg_sample_fraction.argtypes = [ctypes.c_int64, D, D]
    lib.xyg_screen_shape.restype = ctypes.c_int32
    lib.xyg_screen_shape.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
    ]
    lib.xyg_normalize_window.restype = ctypes.c_int32
    lib.xyg_normalize_window.argtypes = [D, D, D, D, ctypes.c_int32, F64P]
    lib.xyg_view_visible_mask.restype = ctypes.c_size_t
    lib.xyg_view_visible_mask.argtypes = [
        F64P,
        F64P,
        ctypes.c_size_t,
        D,
        D,
        D,
        D,
        U8P,
    ]
    lib.xyg_sample_range_indices.restype = ctypes.c_size_t
    lib.xyg_sample_range_indices.argtypes = [
        ctypes.c_size_t,
        ctypes.c_uint64,
        ctypes.c_uint64,
        U32P,
        ctypes.c_size_t,
    ]
    lib.xyg_stratified_sample_range_u8.restype = ctypes.c_size_t
    lib.xyg_stratified_sample_range_u8.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_uint64,
        ctypes.c_double,
        ctypes.c_uint64,
        U32P,
        ctypes.c_size_t,
    ]
    lib.xyg_stratified_sample_range_u8_counted.restype = ctypes.c_size_t
    lib.xyg_stratified_sample_range_u8_counted.argtypes = [
        U8P,
        ctypes.c_size_t,
        U64P,
        ctypes.c_size_t,
        ctypes.c_uint64,
        ctypes.c_double,
        ctypes.c_uint64,
        U32P,
        ctypes.c_size_t,
    ]
    lib.xyg_stratified_sample_mask.restype = ctypes.c_int32
    lib.xyg_stratified_sample_mask.argtypes = [
        U64P,
        U32P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_uint64,
        ctypes.c_double,
        ctypes.c_uint64,
        ctypes.POINTER(ctypes.c_uint8),
    ]
    lib.xyg_stratified_sample_mask_u32.restype = ctypes.c_int32
    lib.xyg_stratified_sample_mask_u32.argtypes = [
        U32P,
        U32P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_uint64,
        ctypes.c_double,
        ctypes.c_uint64,
        ctypes.POINTER(ctypes.c_uint8),
    ]
    lib.xyg_rasterize.restype = ctypes.c_int32
    lib.xyg_rasterize.argtypes = [U8P, ctypes.c_size_t, U8P, ctypes.c_size_t, ctypes.c_size_t]
    lib.xyg_rasterize_png.restype = ctypes.c_size_t
    lib.xyg_rasterize_png.argtypes = [
        U8P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_size_t,
    ]
    lib.xyg_rasterize_data.restype = ctypes.c_int32
    lib.xyg_rasterize_data.argtypes = [
        U8P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
    ]
    lib.xyg_rasterize_png_data.restype = ctypes.c_size_t
    lib.xyg_rasterize_png_data.argtypes = [
        U8P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_size_t,
    ]
    lib.xyg_rasterize_spans.restype = ctypes.c_int32
    lib.xyg_rasterize_spans.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.POINTER(U8P),
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
    ]
    lib.xyg_rasterize_png_spans.restype = ctypes.c_size_t
    lib.xyg_rasterize_png_spans.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.POINTER(U8P),
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_size_t,
    ]
    lib.xyg_heatmap_rgba.restype = ctypes.c_int32
    lib.xyg_heatmap_rgba.argtypes = [
        F64P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        ctypes.c_uint8,
        U8P,
    ]
    lib.xyg_colormap_rgba.restype = ctypes.c_int32
    lib.xyg_colormap_rgba.argtypes = [
        F64P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        ctypes.c_uint8,
        U8P,
    ]
    lib.xyg_colormap_rgba_canonical.restype = ctypes.c_int32
    lib.xyg_colormap_rgba_canonical.argtypes = [
        F64P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        U8P,
        ctypes.c_size_t,
        ctypes.c_uint8,
        U8P,
    ]
    lib.xyg_density_rgba.restype = ctypes.c_int32
    lib.xyg_density_rgba.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_double,
        U8P,
        ctypes.c_size_t,
        ctypes.c_double,
        U8P,
    ]
    lib.xyg_colormap_lut.restype = ctypes.c_int32
    lib.xyg_colormap_lut.argtypes = [
        F64P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        U8P,
    ]
    lib.xyg_density_rgba_linear.restype = ctypes.c_int32
    lib.xyg_density_rgba_linear.argtypes = [
        F64P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_double,
        U8P,
        ctypes.c_size_t,
        ctypes.c_double,
        U8P,
    ]
    lib.xyg_paint_effective_rgba.restype = ctypes.c_int32
    lib.xyg_paint_effective_rgba.argtypes = [
        F64P,
        ctypes.c_size_t,
        F64P,
        F64P,
        ctypes.c_double,
        F64P,
    ]
    lib.xyg_density_log_u8.restype = ctypes.c_int32
    lib.xyg_density_log_u8.argtypes = [F32P, ctypes.c_size_t, U8P, F64P]
    lib.xyg_local_log_density.restype = ctypes.c_int32
    lib.xyg_local_log_density.argtypes = [
        F64P,
        F64P,
        ctypes.c_size_t,
        D,
        D,
        D,
        D,
        Z,
        Z,
        F32P,
    ]
    lib.xyg_graph_layout.restype = ctypes.c_int32
    lib.xyg_graph_layout.argtypes = [
        ctypes.c_uint32,
        ctypes.c_uint64,
        ctypes.c_uint64,
        U64P,
        U64P,
        F64P,
        F64P,
        U64P,
        ctypes.c_uint64,
        ctypes.c_uint64,
        F64P,
        F64P,
    ]
    lib.xyg_graph_lod_decision.restype = ctypes.c_int32
    lib.xyg_graph_lod_decision.argtypes = [
        ctypes.c_uint64,
        ctypes.c_uint64,
        ctypes.c_uint64,
        ctypes.c_uint64,
        U32P,
        U64P,
    ]
    lib.xyg_graph_cluster_aggregate.restype = ctypes.c_int32
    lib.xyg_graph_cluster_aggregate.argtypes = [
        ctypes.c_uint64,
        ctypes.c_uint64,
        F64P,
        F64P,
        ctypes.c_uint64,
        ctypes.c_uint64,
        F64P,
        F64P,
        U64P,
        U64P,
        U32P,
        U64P,
    ]
    lib.xyg_graph_build_render.restype = ctypes.c_int32
    lib.xyg_graph_build_render.argtypes = [
        ctypes.c_uint64,
        ctypes.c_uint64,
        F64P,
        F64P,
        U64P,
        U64P,
        ctypes.c_uint64,
        ctypes.c_uint64,
        ctypes.c_int32,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
        F64P,
        U64P,
        U64P,
        U64P,
        U64P,
        U64P,
        U32P,
        U64P,
    ]
    lib.xyg_graph_sample_edges.restype = ctypes.c_uint64
    lib.xyg_graph_sample_edges.argtypes = [ctypes.c_uint64, ctypes.c_uint64, U64P]
    lib.xyg_graph_build_csr.restype = ctypes.c_int32
    lib.xyg_graph_build_csr.argtypes = [
        ctypes.c_uint64,
        ctypes.c_uint64,
        U64P,
        U64P,
        ctypes.c_int32,
        U64P,
        U64P,
        ctypes.c_uint64,
        U64P,
    ]
    lib.xyg_sankey_layout.restype = ctypes.c_int32
    lib.xyg_sankey_layout.argtypes = [
        ctypes.c_uint64,
        ctypes.c_uint64,
        U64P,
        U64P,
        F64P,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_uint32,
        ctypes.c_uint32,
        F64P,
        F64P,
        F64P,
        F64P,
        U32P,
        F64P,
        F64P,
        F64P,
        F64P,
        F64P,
        U32P,
        U64P,
        U64P,
    ]
    lib.xyg_hexbin.restype = ctypes.c_size_t
    lib.xyg_hexbin.argtypes = [
        F64P,
        F64P,
        F64P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_int32,
        ctypes.c_size_t,
        ctypes.c_int32,
        F64P,
        F64P,
        F64P,
        F64P,
        ctypes.c_size_t,
        F64P,
        F64P,
    ]
    lib.xyg_hexbin_ingress.restype = ctypes.c_int32
    lib.xyg_hexbin_ingress.argtypes = [
        F64P,
        F64P,
        F64P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_int32,
        F64P,
        F64P,
        F64P,
        F64P,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    lib.xyg_hexbin_ring.restype = ctypes.c_size_t
    lib.xyg_hexbin_ring.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        F64P,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_violin_density.restype = ctypes.c_int32
    lib.xyg_violin_density.argtypes = [
        F64P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        F64P,
        F64P,
    ]
    lib.xyg_histogram_edges.restype = ctypes.c_size_t
    lib.xyg_histogram_edges.argtypes = [
        F64P,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_int32,
        ctypes.c_int32,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_histogram_mark_edges.restype = ctypes.c_size_t
    lib.xyg_histogram_mark_edges.argtypes = [
        F64P,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_size_t,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_contour_levels.restype = ctypes.c_size_t
    lib.xyg_contour_levels.argtypes = [
        F64P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_legend_normalize.restype = ctypes.c_size_t
    lib.xyg_legend_normalize.argtypes = [
        F64P,
        F64P,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_legend_best_loc.restype = ctypes.c_int32
    lib.xyg_legend_best_loc.argtypes = [
        F64P,
        F64P,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_size_t,
        U32P,
        ctypes.c_size_t,
    ]
    lib.xyg_ribbon_edge.restype = ctypes.c_size_t
    lib.xyg_ribbon_edge.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_size_t,
        F64P,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_ribbon_polygon.restype = ctypes.c_size_t
    lib.xyg_ribbon_polygon.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_size_t,
        F64P,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_monotone_tangents.restype = ctypes.c_size_t
    lib.xyg_monotone_tangents.argtypes = [
        F64P,
        F64P,
        ctypes.c_size_t,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_curve_flatten.restype = ctypes.c_size_t
    lib.xyg_curve_flatten.argtypes = [
        F64P,
        F64P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        F64P,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_step_arrays.restype = ctypes.c_size_t
    lib.xyg_step_arrays.argtypes = [
        F64P,
        F64P,
        ctypes.c_size_t,
        ctypes.c_uint8,
        F64P,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_marker_path_scale.restype = ctypes.c_size_t
    lib.xyg_marker_path_scale.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
        F64P,
        ctypes.c_size_t,
        F64P,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_arrow_geometry.restype = ctypes.c_int32
    lib.xyg_arrow_geometry.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
        ctypes.c_size_t,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_arrow_shaft_points.restype = ctypes.c_size_t
    lib.xyg_arrow_shaft_points.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_size_t,
        F64P,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_arrow_end_decoration.restype = ctypes.c_size_t
    lib.xyg_arrow_end_decoration.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        U8P,
        ctypes.c_size_t,
        ctypes.c_double,
        F64P,
        F64P,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_int32),
    ]
    lib.xyg_arrow_taper_polygon.restype = ctypes.c_size_t
    lib.xyg_arrow_taper_polygon.argtypes = [
        F64P,
        F64P,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_arrow_trim_polyline_end.restype = ctypes.c_size_t
    lib.xyg_arrow_trim_polyline_end.argtypes = [
        F64P,
        F64P,
        ctypes.c_size_t,
        ctypes.c_double,
        F64P,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_arrow_shapes.restype = ctypes.c_size_t
    lib.xyg_arrow_shapes.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.c_size_t,
        F64P,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_rounded_rect_poly.restype = ctypes.c_size_t
    lib.xyg_rounded_rect_poly.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_int32,
        F64P,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_payload_tier.restype = ctypes.c_int32
    lib.xyg_payload_tier.argtypes = [
        ctypes.c_int32,
        ctypes.c_uint64,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
    ]
    lib.xyg_payload_visible_needed.restype = ctypes.c_int32
    lib.xyg_payload_visible_needed.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
    ]
    lib.xyg_payload_visible_mask.restype = ctypes.c_size_t
    lib.xyg_payload_visible_mask.argtypes = [
        F64P,
        F64P,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        F64P,
        ctypes.c_int32,
        U8P,
        ctypes.c_size_t,
    ]
    lib.xyg_payload_m4_indices.restype = ctypes.c_size_t
    lib.xyg_payload_m4_indices.argtypes = [
        ctypes.c_uint64,
        ctypes.c_int32,
        F64P,
        F64P,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_size_t,
        F64P,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.POINTER(ctypes.c_int32),
        U32P,
        ctypes.c_size_t,
    ]
    lib.xyg_payload_visible_indices.restype = ctypes.c_size_t
    lib.xyg_payload_visible_indices.argtypes = [
        F64P,
        F64P,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        F64P,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        U32P,
        ctypes.c_size_t,
    ]
    lib.xyg_payload_even_indices.restype = ctypes.c_size_t
    lib.xyg_payload_even_indices.argtypes = [
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_int32),
        U32P,
        ctypes.c_size_t,
    ]
    lib.xyg_payload_segment_budget.restype = ctypes.c_size_t
    lib.xyg_payload_segment_budget.argtypes = [ctypes.c_double]
    lib.xyg_payload_errorbar_indices.restype = ctypes.c_size_t
    lib.xyg_payload_errorbar_indices.argtypes = [
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_int32),
        U32P,
        ctypes.c_size_t,
    ]
    lib.xyg_payload_errorbar_role_keys.restype = ctypes.c_size_t
    lib.xyg_payload_errorbar_role_keys.argtypes = [
        ctypes.c_size_t,
        ctypes.c_size_t,
        U32P,
        U32P,
        U32P,
        U32P,
        U32P,
        U32P,
        ctypes.POINTER(ctypes.c_int32),
    ]
    lib.xyg_payload_errorbar_role_maps.restype = ctypes.c_int32
    lib.xyg_payload_errorbar_role_maps.argtypes = [
        ctypes.c_size_t,
        ctypes.c_size_t,
        U32P,
        U32P,
        ctypes.POINTER(ctypes.c_int32),
    ]
    lib.xyg_payload_bar_compact_admit.restype = ctypes.c_int32
    lib.xyg_payload_bar_compact_admit.argtypes = [
        ctypes.c_size_t,
        F64P,
        ctypes.c_size_t,
        F64P,
        F64P,
        F64P,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
    ]
    lib.xyg_payload_transition_keys_admit.restype = ctypes.c_int32
    lib.xyg_payload_transition_keys_admit.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_size_t,
    ]
    lib.xyg_payload_trace_channels_ship_attach.restype = ctypes.c_int32
    lib.xyg_payload_trace_channels_ship_attach.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
    ]
    lib.xyg_payload_transition_entry_attach.restype = ctypes.c_int32
    lib.xyg_payload_transition_entry_attach.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
    ]
    lib.xyg_payload_base_entry_plan.restype = ctypes.c_int32
    lib.xyg_payload_base_entry_plan.argtypes = [
        ctypes.c_int32,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
    ]
    lib.xyg_payload_nonxy_emit_plan.restype = ctypes.c_int32
    lib.xyg_payload_nonxy_emit_plan.argtypes = [
        ctypes.c_int32,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
    ]
    lib.xyg_payload_bar_hist_emit_plan.restype = ctypes.c_int32
    lib.xyg_payload_bar_hist_emit_plan.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
    ]
    lib.xyg_payload_heatmap_emit_plan.restype = ctypes.c_int32
    lib.xyg_payload_heatmap_emit_plan.argtypes = [
        ctypes.c_int32,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
    ]
    lib.xyg_payload_mesh_emit_plan.restype = ctypes.c_int32
    lib.xyg_payload_mesh_emit_plan.argtypes = [
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
    ]

    lib.xyg_payload_column_ship_plan.restype = ctypes.c_int32
    lib.xyg_payload_column_ship_plan.argtypes = [
        ctypes.c_char_p,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,  # orientation (ABI 313; ignored except bar_compact)
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(PayloadColumnShipEntry),
        ctypes.c_size_t,
    ]
    lib.xyg_payload_density_grid_ship_plan.restype = ctypes.c_int32
    lib.xyg_payload_density_grid_ship_plan.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(PayloadDensityGridBufferEntry),
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(PayloadDensityGridAttachEntry),
        ctypes.c_size_t,
    ]
    lib.xyg_payload_channel_ship_plan.restype = ctypes.c_int32
    lib.xyg_payload_channel_ship_plan.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(PayloadChannelShipEntry),
        ctypes.c_size_t,
    ]
    lib.xyg_payload_channel_wire_encode.restype = ctypes.c_int32
    lib.xyg_payload_channel_wire_encode.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
    ]
    lib.xyg_payload_ribbon_emit_plan.restype = ctypes.c_int32
    lib.xyg_payload_ribbon_emit_plan.argtypes = [
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
    ]
    lib.xyg_payload_segments_emit_plan.restype = ctypes.c_int32
    lib.xyg_payload_segments_emit_plan.argtypes = [
        ctypes.c_char_p,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
    ]
    lib.xyg_payload_scatter_emit_plan.restype = ctypes.c_int32
    lib.xyg_payload_scatter_emit_plan.argtypes = [
        ctypes.c_uint64,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
    ]
    lib.xyg_payload_density_trace_emit_plan.restype = ctypes.c_int32
    lib.xyg_payload_density_trace_emit_plan.argtypes = [
        ctypes.c_int32,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_uint64,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_void_p,
    ]
    lib.xyg_payload_build_plan.restype = ctypes.c_int32
    lib.xyg_payload_build_plan.argtypes = [
        ctypes.c_int32,
        ctypes.c_uint64,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_void_p,
    ]
    lib.xyg_payload_axis_spec_attach_plan.restype = ctypes.c_int32
    lib.xyg_payload_axis_spec_attach_plan.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_void_p,
    ]
    lib.xyg_density_color_classify.restype = ctypes.c_int32
    lib.xyg_density_color_classify.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
    ]
    lib.xyg_density_trace_color_classify.restype = ctypes.c_int32
    lib.xyg_density_trace_color_classify.argtypes = [
        ctypes.c_int32,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.POINTER(ctypes.c_int32),
    ]
    lib.xyg_density_bin_coord_endpoints.restype = ctypes.c_int32
    lib.xyg_density_bin_coord_endpoints.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
    ]
    lib.xyg_density_uses_channel_colormap.restype = ctypes.c_int32
    lib.xyg_density_uses_channel_colormap.argtypes = [
        ctypes.c_int32,
        ctypes.c_void_p,
        ctypes.c_size_t,
    ]
    lib.xyg_density_reduction_kind.restype = ctypes.c_int32
    lib.xyg_density_reduction_kind.argtypes = [
        ctypes.c_void_p,
        ctypes.c_size_t,
    ]
    lib.xyg_density_overlay_omitted_wire.restype = ctypes.c_size_t
    lib.xyg_density_overlay_omitted_wire.argtypes = [
        ctypes.c_uint32,
        ctypes.c_int32,
        ctypes.c_void_p,
        ctypes.c_size_t,
    ]
    lib.xyg_density_grid_path_identity_state.restype = ctypes.c_int32
    lib.xyg_density_grid_path_identity_state.argtypes = [ctypes.c_int32]
    lib.xyg_density_constant_color_wire_admit.restype = ctypes.c_int32
    lib.xyg_density_constant_color_wire_admit.argtypes = [
        ctypes.c_int32,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_int32,
    ]
    lib.xyg_density_categorical_color_wire_admit.restype = ctypes.c_int32
    lib.xyg_density_categorical_color_wire_admit.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
    ]
    lib.xyg_density_mean_color_wire_admit.restype = ctypes.c_int32
    lib.xyg_density_mean_color_wire_admit.argtypes = [
        ctypes.c_int32,
        ctypes.c_void_p,
        ctypes.c_size_t,
    ]
    lib.xyg_density_channels_dropped_compat.restype = ctypes.c_int32
    lib.xyg_density_channels_dropped_compat.argtypes = [ctypes.c_int32]
    lib.xyg_density_dropped_channel_wire_admit.restype = ctypes.c_int32
    lib.xyg_density_dropped_channel_wire_admit.argtypes = [
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_int32,
    ]
    lib.xyg_density_mean_color_rgba_wire_admit.restype = ctypes.c_int32
    lib.xyg_density_mean_color_rgba_wire_admit.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
    ]
    lib.xyg_density_wasm_source_admit.restype = ctypes.c_int32
    lib.xyg_density_wasm_source_admit.argtypes = [ctypes.c_int32, ctypes.c_int32]
    lib.xyg_density_wasm_density_wire_kind.restype = ctypes.c_int32
    lib.xyg_density_wasm_density_wire_kind.argtypes = [
        ctypes.c_int32,
        ctypes.c_uint64,
        ctypes.c_int32,
    ]
    lib.xyg_payload_sample_target_indices.restype = ctypes.c_size_t
    lib.xyg_payload_sample_target_indices.argtypes = [
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_uint64,
        ctypes.c_uint32,
        ctypes.c_double,
        ctypes.POINTER(ctypes.c_int32),
        U32P,
        ctypes.c_size_t,
    ]
    lib.xyg_density_bin_window.restype = ctypes.c_size_t
    lib.xyg_density_bin_window.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
    ]
    lib.xyg_density_full_identity.restype = ctypes.c_int32
    lib.xyg_density_full_identity.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
    ]
    lib.xyg_density_pyramid_preflight.restype = ctypes.c_size_t
    lib.xyg_density_pyramid_preflight.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_uint64,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        U32P,
    ]
    lib.xyg_density_grid_path.restype = ctypes.c_int32
    lib.xyg_density_grid_path.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
    ]
    lib.xyg_density_format_binning.restype = ctypes.c_size_t
    lib.xyg_density_format_binning.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        U8P,
        ctypes.c_size_t,
    ]
    lib.xyg_density_emit_meta.restype = ctypes.c_int32
    lib.xyg_density_emit_meta.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_uint64,
        ctypes.c_void_p,
    ]
    lib.xyg_density_wasm_eligible.restype = ctypes.c_int32
    lib.xyg_density_wasm_eligible.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_uint64,
    ]
    lib.xyg_scene_tick_label_layout.restype = ctypes.c_size_t
    lib.xyg_scene_tick_label_layout.argtypes = [
        F64P,
        ctypes.c_size_t,
        U32P,
        U8P,
        ctypes.c_size_t,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        U32P,
        F64P,
        U32P,
        ctypes.c_size_t,
    ]
    lib.xyg_legend_box_layout.restype = ctypes.c_size_t
    lib.xyg_legend_box_layout.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        U32P,
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_uint32,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
        ctypes.c_size_t,
        ctypes.c_double,
        F64P,
        F64P,
        F64P,
        ctypes.c_size_t,
        U32P,
        U8P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    lib.xyg_text_block_measure.restype = ctypes.c_size_t
    lib.xyg_text_block_measure.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
        U32P,
        ctypes.c_size_t,
        U8P,
        ctypes.c_size_t,
    ]
    lib.xyg_text_block_rotated_extent.restype = ctypes.c_size_t
    lib.xyg_text_block_rotated_extent.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
        F64P,
    ]
    lib.xyg_y_tick_label_extent.restype = ctypes.c_size_t
    lib.xyg_y_tick_label_extent.argtypes = [
        U32P,
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
    ]
    lib.xyg_y_axis_left_room.restype = ctypes.c_size_t
    lib.xyg_y_axis_left_room.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        U8P,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
    ]
    lib.xyg_x_axis_title_room.restype = ctypes.c_size_t
    lib.xyg_x_axis_title_room.argtypes = [
        U8P,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_int32,
        F64P,
    ]
    lib.xyg_x_tick_label_room.restype = ctypes.c_size_t
    lib.xyg_x_tick_label_room.argtypes = [
        U32P,
        U8P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        F64P,
        U32P,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
    ]
    lib.xyg_x_tick_label_edge_rooms.restype = ctypes.c_size_t
    lib.xyg_x_tick_label_edge_rooms.argtypes = [
        ctypes.c_double,
        F64P,
        ctypes.c_size_t,
        U32P,
        U8P,
        ctypes.c_size_t,
        F64P,
        U32P,
        ctypes.c_double,
        F64P,
        F64P,
    ]
    lib.xyg_compat_is_compact.restype = ctypes.c_int32
    lib.xyg_compat_is_compact.argtypes = [ctypes.c_double]
    lib.xyg_compat_default_padding.restype = ctypes.c_size_t
    lib.xyg_compat_default_padding.argtypes = [ctypes.c_int32, F64P]
    lib.xyg_compat_title_wrap_width.restype = ctypes.c_size_t
    lib.xyg_compat_title_wrap_width.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
    ]
    lib.xyg_compat_title_room.restype = ctypes.c_size_t
    lib.xyg_compat_title_room.argtypes = [
        ctypes.c_int32,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_int32,
        ctypes.c_double,
        F64P,
    ]
    lib.xyg_compat_x_axis_side_room.restype = ctypes.c_size_t
    lib.xyg_compat_x_axis_side_room.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_double,
        F64P,
        F64P,
    ]
    lib.xyg_compat_colorbar_extra.restype = ctypes.c_size_t
    lib.xyg_compat_colorbar_extra.argtypes = [
        ctypes.c_uint32,
        ctypes.c_int32,
        ctypes.c_int32,
        F64P,
        F64P,
    ]
    lib.xyg_compat_right_y_room.restype = ctypes.c_size_t
    lib.xyg_compat_right_y_room.argtypes = [ctypes.c_int32, F64P]
    lib.xyg_polar_legend_room.restype = ctypes.c_size_t
    lib.xyg_polar_legend_room.argtypes = [ctypes.c_double, F64P]
    lib.xyg_polar_legend_reserve.restype = ctypes.c_size_t
    lib.xyg_polar_legend_reserve.argtypes = [
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_double,
        ctypes.POINTER(ctypes.c_uint32),
        F64P,
    ]
    lib.xyg_polar_label_room.restype = ctypes.c_size_t
    lib.xyg_polar_label_room.argtypes = [ctypes.c_double, F64P]
    lib.xyg_recut_polar_plot.restype = ctypes.c_size_t
    lib.xyg_recut_polar_plot.argtypes = [
        F64P,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_uint32,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        F64P,
    ]
    lib.xyg_compat_combine_plot.restype = ctypes.c_size_t
    lib.xyg_compat_combine_plot.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        F64P,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_uint32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
        ctypes.c_int32,
        ctypes.c_uint32,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
        F64P,
    ]
    lib.xyg_tight_layout_solve.restype = ctypes.c_size_t
    lib.xyg_tight_layout_solve.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_int32,
        F64P,
        ctypes.c_size_t,
        F64P,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
        F64P,
    ]
    lib.xyg_tight_layout_figure_extra.restype = ctypes.c_size_t
    lib.xyg_tight_layout_figure_extra.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
    ]
    lib.xyg_tick_window.restype = ctypes.c_size_t
    lib.xyg_tick_window.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
        F64P,
    ]
    lib.xyg_tick_window_filter.restype = ctypes.c_size_t
    lib.xyg_tick_window_filter.argtypes = [
        F64P,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_int32,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_tick_format.restype = ctypes.c_size_t
    lib.xyg_tick_format.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_size_t,
    ]
    lib.xyg_polar_layout.restype = ctypes.c_size_t
    lib.xyg_polar_layout.argtypes = [
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_uint32,
        ctypes.c_double,
        ctypes.c_uint32,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_uint32,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_uint32,
        ctypes.c_double,
        ctypes.c_int32,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_polar_project.restype = ctypes.c_size_t
    lib.xyg_polar_project.argtypes = [
        F64P,
        ctypes.c_size_t,
        F64P,
        F64P,
        ctypes.c_size_t,
        F64P,
        F64P,
    ]
    lib.xyg_polar_wedge_points.restype = ctypes.c_size_t
    lib.xyg_polar_wedge_points.argtypes = [
        F64P,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_uint32,
        ctypes.c_double,
        ctypes.c_double,
        F64P,
        F64P,
        ctypes.c_size_t,
    ]
    lib.xyg_polar_heatmap_inverse_map.restype = ctypes.c_size_t
    lib.xyg_polar_heatmap_inverse_map.argtypes = [
        F64P,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        U32P,
        U32P,
        U32P,
        U32P,
        U32P,
        ctypes.c_size_t,
    ]
    lib.xyg_hexbin_groups.restype = ctypes.c_size_t
    lib.xyg_hexbin_groups.argtypes = [
        F64P,
        F64P,
        F64P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_int32,
        ctypes.c_size_t,
        F64P,
        F64P,
        F64P,
        U32P,
        U32P,
        ctypes.c_size_t,
        U32P,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
        F64P,
        F64P,
    ]
    lib.xyg_wind_rose_bins.restype = ctypes.c_size_t
    lib.xyg_wind_rose_bins.argtypes = [
        F64P,
        F64P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        F64P,
        ctypes.c_size_t,
        F64P,
        ctypes.c_size_t,
        F64P,
        F64P,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    lib.xyg_contourf_densify.restype = ctypes.c_int32
    lib.xyg_contourf_densify.argtypes = [
        F64P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        F64P,
        F64P,
        F64P,
        F64P,
        F64P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    lib.xyg_bar_stack.restype = ctypes.c_int32
    lib.xyg_bar_stack.argtypes = [
        F64P,
        ctypes.c_size_t,
        F64P,
        ctypes.c_size_t,
        F64P,
        ctypes.c_size_t,
        F64P,
        ctypes.c_size_t,
        ctypes.c_uint32,
        ctypes.c_uint32,
        F64P,
        F64P,
        F64P,
        F64P,
    ]
    lib.xyg_contourf_bands.restype = ctypes.c_size_t
    lib.xyg_contourf_bands.argtypes = [
        F64P,
        ctypes.c_size_t,
        ctypes.c_size_t,
        F64P,
        F64P,
        F64P,
        ctypes.c_size_t,
        ctypes.c_uint8,
        ctypes.c_uint8,
        F64P,
        F64P,
        F64P,
        F64P,
        F64P,
        F64P,
        ctypes.POINTER(ctypes.c_int64),
        ctypes.c_size_t,
    ]
    lib.xyg_stream_new.restype = ctypes.c_uint64
    lib.xyg_stream_new.argtypes = [F64P, ctypes.c_size_t]
    lib.xyg_stream_append.restype = ctypes.c_int32
    lib.xyg_stream_append.argtypes = [ctypes.c_uint64, F64P, ctypes.c_size_t]
    lib.xyg_stream_seal.restype = ctypes.c_int32
    lib.xyg_stream_seal.argtypes = [ctypes.c_uint64]
    lib.xyg_stream_free.restype = ctypes.c_int32
    lib.xyg_stream_free.argtypes = [ctypes.c_uint64]
    lib.xyg_stream_len.restype = ctypes.c_size_t
    lib.xyg_stream_len.argtypes = [ctypes.c_uint64]
    lib.xyg_stream_capacity.restype = ctypes.c_size_t
    lib.xyg_stream_capacity.argtypes = [ctypes.c_uint64]
    lib.xyg_stream_copy.restype = ctypes.c_int32
    lib.xyg_stream_copy.argtypes = [ctypes.c_uint64, F64P, ctypes.c_size_t]
    lib.xyg_stream_data.restype = ctypes.c_int32
    lib.xyg_stream_data.argtypes = [
        ctypes.c_uint64,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    lib.xyg_stream_zone_maps.restype = ctypes.c_size_t
    lib.xyg_stream_zone_maps.argtypes = [ctypes.c_uint64] + [
        F64P,
        F64P,
        U64P,
        U64P,
        F64P,
        F64P,
        F64P,
        F64P,
    ]

    lib.xyg_geo_column_new.restype = ctypes.c_uint64
    lib.xyg_geo_column_new.argtypes = [
        ctypes.c_uint32,
        ctypes.c_uint32,
        F64P,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_int32),
    ]
    lib.xyg_geo_column_free.restype = ctypes.c_int32
    lib.xyg_geo_column_free.argtypes = [ctypes.c_uint64]
    lib.xyg_geo_column_len.restype = ctypes.c_size_t
    lib.xyg_geo_column_len.argtypes = [ctypes.c_uint64]
    lib.xyg_geo_column_vertex_count.restype = ctypes.c_size_t
    lib.xyg_geo_column_vertex_count.argtypes = [ctypes.c_uint64]
    lib.xyg_geo_column_geometry.restype = ctypes.c_uint32
    lib.xyg_geo_column_geometry.argtypes = [ctypes.c_uint64]
    lib.xyg_geo_column_crs.restype = ctypes.c_uint32
    lib.xyg_geo_column_crs.argtypes = [ctypes.c_uint64]
    lib.xyg_pyramid_build_from_stream.restype = ctypes.c_uint64
    lib.xyg_pyramid_build_from_stream.argtypes = [
        ctypes.c_uint64,
        ctypes.c_uint64,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_uint32,
    ]
    lib.xyg_pyramid_append_from_stream.restype = ctypes.c_int32
    lib.xyg_pyramid_append_from_stream.argtypes = [
        ctypes.c_uint64,
        ctypes.c_uint64,
        ctypes.c_uint64,
        ctypes.c_size_t,
    ]
    return lib


def _ptr(a: array, ct):  # noqa: ANN001
    addr, _ = a.buffer_info()
    return ctypes.cast(addr, ctypes.POINTER(ct))


def main() -> None:
    lib = load()
    checks = 0
    size_max = ctypes.c_size_t(-1).value
    factorize_capacity_exceeded = size_max - 1
    F64P = ctypes.POINTER(ctypes.c_double)
    F32P = ctypes.POINTER(ctypes.c_float)
    U64P = ctypes.POINTER(ctypes.c_uint64)
    U32P = ctypes.POINTER(ctypes.c_uint32)
    U8P = ctypes.POINTER(ctypes.c_uint8)
    null_f64 = F64P()
    null_f32 = F32P()
    null_u64 = U64P()
    null_u32 = U32P()
    null_u8 = U8P()

    def ok(cond: bool, msg: str) -> None:
        nonlocal checks
        if not cond:
            raise SystemExit(f"FAIL: {msg}")
        checks += 1

    ok(lib.xyg_abi_version() == ABI_VERSION, "abi version")
    ok(ctypes.sizeof(CZoneMap) == 64, "ZoneMap repr(C) size")

    graph_x = array("d", [0.0]) * 4
    graph_y = array("d", [0.0]) * 4
    ok(
        lib.xyg_graph_layout(
            2,
            4,
            0,
            null_u64,
            null_u64,
            null_f64,
            null_f64,
            null_u64,
            0,
            0,
            _ptr(graph_x, ctypes.c_double),
            _ptr(graph_y, ctypes.c_double),
        )
        == 0,
        "graph_layout circle ok",
    )
    ok(
        abs(graph_x[0] - 4.0) < 1e-12
        and abs(graph_y[0]) < 1e-12
        and abs(graph_x[1]) < 1e-12
        and abs(graph_y[1] - 4.0) < 1e-12,
        "graph_layout circle positions four nodes",
    )
    graph_tier = ctypes.c_uint32()
    graph_kept = ctypes.c_uint64()
    ok(
        lib.xyg_graph_lod_decision(
            100,
            10_000,
            50_000,
            1_000,
            ctypes.byref(graph_tier),
            ctypes.byref(graph_kept),
        )
        == 0
        and graph_tier.value == 1
        and graph_kept.value == 1_000,
        "graph_lod_decision edge sample",
    )
    cluster_x = array("d", [0.0, 1.0, 0.0, 100.0, 101.0, 100.0])
    cluster_y = array("d", [0.0, 0.0, 1.0, 100.0, 100.0, 101.0])
    cluster_out_x = array("d", [0.0]) * 2
    cluster_out_y = array("d", [0.0]) * 2
    cluster_member = array("Q", [99]) * 6
    cluster_count = ctypes.c_uint64()
    cluster_tier = ctypes.c_uint32()
    cluster_kept = ctypes.c_uint64()
    ok(
        lib.xyg_graph_cluster_aggregate(
            6,
            3,
            _ptr(cluster_x, ctypes.c_double),
            _ptr(cluster_y, ctypes.c_double),
            2,
            500,
            _ptr(cluster_out_x, ctypes.c_double),
            _ptr(cluster_out_y, ctypes.c_double),
            ctypes.byref(cluster_count),
            _ptr(cluster_member, ctypes.c_uint64),
            ctypes.byref(cluster_tier),
            ctypes.byref(cluster_kept),
        )
        == 0
        and cluster_count.value == 2
        and cluster_tier.value == 2
        and list(cluster_member) == [0, 0, 0, 1, 1, 1],
        "graph_cluster_aggregate grid centroids + recorded tier",
    )
    render_sources = array("Q", [0, 1, 3, 4, 0])
    render_targets = array("Q", [1, 2, 4, 5, 3])
    render_out_x = array("d", [0.0]) * 2
    render_out_y = array("d", [0.0]) * 2
    render_member = array("Q", [99]) * 6
    render_es = array("Q", [99]) * 4
    render_et = array("Q", [99]) * 4
    render_n = ctypes.c_uint64()
    render_e = ctypes.c_uint64()
    render_tier = ctypes.c_uint32()
    render_kept = ctypes.c_uint64()
    ok(
        lib.xyg_graph_build_render(
            6,
            5,
            _ptr(cluster_x, ctypes.c_double),
            _ptr(cluster_y, ctypes.c_double),
            _ptr(render_sources, ctypes.c_uint64),
            _ptr(render_targets, ctypes.c_uint64),
            2,
            4,
            0,
            0.0,
            0.0,
            0.0,
            0.0,
            _ptr(render_out_x, ctypes.c_double),
            _ptr(render_out_y, ctypes.c_double),
            _ptr(render_member, ctypes.c_uint64),
            _ptr(render_es, ctypes.c_uint64),
            _ptr(render_et, ctypes.c_uint64),
            ctypes.byref(render_n),
            ctypes.byref(render_e),
            ctypes.byref(render_tier),
            ctypes.byref(render_kept),
        )
        == 0
        and render_n.value <= 2
        and render_e.value <= 4
        and render_tier.value == 2
        and list(render_member) == [0, 0, 0, 1, 1, 1],
        "graph_build_render budgets + recorded tier",
    )
    graph_sample = array("Q", [99]) * 3
    ok(
        lib.xyg_graph_sample_edges(10, 3, _ptr(graph_sample, ctypes.c_uint64)) == 3
        and list(graph_sample) == [0, 3, 6],
        "graph_sample_edges deterministic stride",
    )
    csr_sources = array("Q", [0, 1])
    csr_targets = array("Q", [1, 2])
    csr_offsets = array("Q", [99]) * 4
    csr_neighbors = array("Q", [99]) * 4
    csr_len = ctypes.c_uint64()
    ok(
        lib.xyg_graph_build_csr(
            3,
            2,
            _ptr(csr_sources, ctypes.c_uint64),
            _ptr(csr_targets, ctypes.c_uint64),
            0,
            _ptr(csr_offsets, ctypes.c_uint64),
            _ptr(csr_neighbors, ctypes.c_uint64),
            len(csr_neighbors),
            ctypes.byref(csr_len),
        )
        == 0
        and list(csr_offsets) == [0, 1, 3, 4]
        and csr_len.value == 4
        and sorted(csr_neighbors[: csr_len.value]) == [0, 1, 1, 2],
        "graph_build_csr undirected",
    )
    sankey_sources = array("Q", [0])
    sankey_targets = array("Q", [1])
    sankey_values = array("d", [1.0])
    sankey_x0 = array("d", [0.0]) * 2
    sankey_y0 = array("d", [0.0]) * 2
    sankey_x1 = array("d", [0.0]) * 2
    sankey_y1 = array("d", [0.0]) * 2
    sankey_layer = array("I", [99]) * 2
    sankey_node_value = array("d", [0.0]) * 2
    sankey_source_y0 = array("d", [0.0])
    sankey_source_y1 = array("d", [0.0])
    sankey_target_y0 = array("d", [0.0])
    sankey_target_y1 = array("d", [0.0])
    sankey_layers = array("I", [0])
    sankey_err_nodes = array("Q", [99]) * 2
    sankey_err_n = ctypes.c_uint64()
    ok(
        lib.xyg_sankey_layout(
            2,
            1,
            _ptr(sankey_sources, ctypes.c_uint64),
            _ptr(sankey_targets, ctypes.c_uint64),
            _ptr(sankey_values, ctypes.c_double),
            0.05,
            0.0,
            0,
            1,
            _ptr(sankey_x0, ctypes.c_double),
            _ptr(sankey_y0, ctypes.c_double),
            _ptr(sankey_x1, ctypes.c_double),
            _ptr(sankey_y1, ctypes.c_double),
            _ptr(sankey_layer, ctypes.c_uint32),
            _ptr(sankey_node_value, ctypes.c_double),
            _ptr(sankey_source_y0, ctypes.c_double),
            _ptr(sankey_source_y1, ctypes.c_double),
            _ptr(sankey_target_y0, ctypes.c_double),
            _ptr(sankey_target_y1, ctypes.c_double),
            _ptr(sankey_layers, ctypes.c_uint32),
            _ptr(sankey_err_nodes, ctypes.c_uint64),
            ctypes.byref(sankey_err_n),
        )
        == 0
        and list(sankey_layer) == [0, 1]
        and list(sankey_node_value) == [1.0, 1.0]
        and sankey_layers[0] == 2,
        "sankey_layout simple A to B",
    )

    ok(
        lib.xyg_factorize_fixed(null_u8, 0, 0, null_u32, null_u32) == 0,
        "factorize_fixed empty/null returns zero",
    )
    ok(
        lib.xyg_factorize_fixed(null_u8, 1, 3, null_u32, null_u32) == size_max,
        "factorize_fixed non-empty/null sentinel",
    )
    records = array("B", b"ab\0xy\0ab\0abxxy\0")
    factor_codes = array("I", [99] * 5)
    factor_unique = array("I", [99] * 5)
    factor_count = lib.xyg_factorize_fixed(
        _ptr(records, ctypes.c_uint8),
        5,
        3,
        _ptr(factor_codes, ctypes.c_uint32),
        _ptr(factor_unique, ctypes.c_uint32),
    )
    ok(factor_count == 3, "factorize_fixed unique count")
    ok(
        list(factor_codes) == [0, 1, 0, 2, 1] and list(factor_unique[:3]) == [0, 1, 3],
        "factorize_fixed codes and first rows",
    )
    compact_codes = array("B", [99] * 5)
    compact_unique = array("I", [99] * 3)
    compact_count = lib.xyg_factorize_fixed_u8(
        _ptr(records, ctypes.c_uint8),
        5,
        3,
        _ptr(compact_codes, ctypes.c_uint8),
        _ptr(compact_unique, ctypes.c_uint32),
        3,
    )
    ok(compact_count == 3, "factorize_fixed_u8 unique count")
    ok(
        list(compact_codes) == [0, 1, 0, 2, 1] and list(compact_unique) == [0, 1, 3],
        "factorize_fixed_u8 compact codes",
    )
    compact_counts = array("Q", [99] * 3)
    compact_count = lib.xyg_factorize_fixed_u8_counts(
        _ptr(records, ctypes.c_uint8),
        5,
        3,
        _ptr(compact_codes, ctypes.c_uint8),
        _ptr(compact_unique, ctypes.c_uint32),
        _ptr(compact_counts, ctypes.c_uint64),
        3,
    )
    ok(
        compact_count == 3 and list(compact_counts) == [2, 2, 1],
        "factorize_fixed_u8_counts exact counts",
    )
    unicode_records = array("I", [ord("β"), ord("a"), ord("β"), 0, ord("é")])
    unicode_codes = array("B", [99] * 5)
    unicode_unique = array("I", [99] * 5)
    unicode_counts = array("Q", [99] * 5)
    unicode_count = lib.xyg_factorize_unicode1_u8_counts(
        _ptr(unicode_records, ctypes.c_uint32),
        5,
        0,
        _ptr(unicode_codes, ctypes.c_uint8),
        _ptr(unicode_unique, ctypes.c_uint32),
        _ptr(unicode_counts, ctypes.c_uint64),
        5,
    )
    ok(
        unicode_count == 4
        and list(unicode_codes) == [0, 1, 0, 2, 3]
        and list(unicode_unique[:4]) == [0, 1, 3, 4]
        and list(unicode_counts[:4]) == [2, 1, 1, 1],
        "factorize_unicode1_u8_counts direct codepoints",
    )
    swapped_unicode = array(
        "I",
        [
            int.from_bytes(
                value.to_bytes(4, sys.byteorder), "big" if sys.byteorder == "little" else "little"
            )
            for value in unicode_records
        ],
    )
    swapped_count = lib.xyg_factorize_unicode1_u8_counts(
        _ptr(swapped_unicode, ctypes.c_uint32),
        5,
        1,
        _ptr(unicode_codes, ctypes.c_uint8),
        _ptr(unicode_unique, ctypes.c_uint32),
        _ptr(unicode_counts, ctypes.c_uint64),
        5,
    )
    ok(
        swapped_count == 4 and list(unicode_codes) == [0, 1, 0, 2, 3],
        "factorize_unicode1_u8_counts swapped endian",
    )
    display_lens = array("I", [1, 9, 1, 9, 1])
    display_texts = array("B", b"b(missing)a(missing)1")
    display_codes = array("B", [99] * 20)
    display_width = array("I", [99])
    display_category_lens = array("I", [99] * 8)
    display_category_texts = array("B", [0] * 32)
    display_count = lib.xyg_factorize_display_labels(
        _ptr(display_lens, ctypes.c_uint32),
        _ptr(display_texts, ctypes.c_uint8),
        len(display_texts),
        5,
        _ptr(display_codes, ctypes.c_uint8),
        len(display_codes),
        _ptr(display_width, ctypes.c_uint32),
        _ptr(display_category_lens, ctypes.c_uint32),
        _ptr(display_category_texts, ctypes.c_uint8),
        len(display_category_texts),
        8,
    )
    ok(display_count == 4 and display_width[0] == 1, "factorize_display_labels mixed-object width")
    ok(list(display_codes[:5]) == [3, 0, 2, 0, 1], "factorize_display_labels mixed-object codes")
    cat_blob = bytes(display_category_texts[: sum(display_category_lens[:4])])
    ok(
        cat_blob == b"(missing)1ab",
        "factorize_display_labels sorted categories",
    )
    first_seen_lens = array("I", [1, 1, 1, 9, 1])
    first_seen_texts = array("B", b"bab(missing)a")
    first_seen_codes = array("B", [99] * 20)
    first_seen_width = array("I", [99])
    first_seen_category_lens = array("I", [99] * 8)
    first_seen_category_texts = array("B", [0] * 32)
    first_seen_count = lib.xyg_label_codes_first_seen(
        _ptr(first_seen_lens, ctypes.c_uint32),
        _ptr(first_seen_texts, ctypes.c_uint8),
        len(first_seen_texts),
        5,
        _ptr(first_seen_codes, ctypes.c_uint8),
        len(first_seen_codes),
        _ptr(first_seen_width, ctypes.c_uint32),
        _ptr(first_seen_category_lens, ctypes.c_uint32),
        _ptr(first_seen_category_texts, ctypes.c_uint8),
        len(first_seen_category_texts),
        8,
    )
    ok(
        first_seen_count == 3 and first_seen_width[0] == 1,
        "label_codes_first_seen mixed-object width",
    )
    ok(
        list(first_seen_codes[:5]) == [0, 1, 0, 2, 1],
        "label_codes_first_seen mixed-object codes",
    )
    first_seen_blob = bytes(first_seen_category_texts[: sum(first_seen_category_lens[:3])])
    ok(
        first_seen_blob == b"ba(missing)",
        "label_codes_first_seen first-seen categories",
    )
    sorted_remap_lens = array("I", [1, 1, 1])
    sorted_remap_texts = array("B", b"bab")
    sorted_remap_out = array("B", [99] * 12)
    sorted_remap_width = array("I", [99])
    sorted_remap_category_lens = array("I", [99] * 4)
    sorted_remap_category_texts = array("B", [0] * 16)
    sorted_remap_in_counts = array("Q", [2, 1, 3])
    sorted_remap_out_counts = array("Q", [0] * 4)
    sorted_remap_count = lib.xyg_sorted_display_label_remap(
        _ptr(sorted_remap_lens, ctypes.c_uint32),
        _ptr(sorted_remap_texts, ctypes.c_uint8),
        len(sorted_remap_texts),
        3,
        _ptr(sorted_remap_in_counts, ctypes.c_uint64),
        _ptr(sorted_remap_out, ctypes.c_uint8),
        len(sorted_remap_out),
        _ptr(sorted_remap_width, ctypes.c_uint32),
        _ptr(sorted_remap_category_lens, ctypes.c_uint32),
        _ptr(sorted_remap_category_texts, ctypes.c_uint8),
        len(sorted_remap_category_texts),
        4,
        _ptr(sorted_remap_out_counts, ctypes.c_uint64),
        4,
    )
    ok(
        sorted_remap_count == 2 and sorted_remap_width[0] == 1,
        "sorted_display_label_remap width",
    )
    ok(
        list(sorted_remap_out[:3]) == [1, 0, 1],
        "sorted_display_label_remap remap",
    )
    ok(
        list(sorted_remap_out_counts[:2]) == [1, 5],
        "sorted_display_label_remap counts",
    )
    ok(
        lib.xyg_factorize_use_native_probe(100, 4096, 4) == 1,
        "factorize_use_native_probe low distinct",
    )
    ok(
        lib.xyg_factorize_use_native_probe(4096, 4096, 4) == 0,
        "factorize_use_native_probe near-unique narrow",
    )
    ok(
        lib.xyg_factorize_use_native_probe(3890, 4096, 64) == 1,
        "factorize_use_native_probe wide below ratio",
    )
    ok(
        lib.xyg_factorize_use_native_probe(512, 4096, 0) == -1,
        "factorize_use_native_probe invalid width",
    )
    repetitive = (ctypes.c_uint32 * 50_000)(*[(i % 100) for i in range(50_000)])
    repetitive_u8 = ctypes.cast(repetitive, ctypes.POINTER(ctypes.c_uint8))
    ok(
        lib.xyg_factorize_use_native_fixed(
            repetitive_u8,
            len(repetitive),
            4,
        )
        == 1,
        "factorize_use_native_fixed repetitive column",
    )
    near_unique = (ctypes.c_uint32 * 5000)(*range(5000))
    near_unique_u8 = ctypes.cast(near_unique, ctypes.POINTER(ctypes.c_uint8))
    ok(
        lib.xyg_factorize_use_native_fixed(
            near_unique_u8,
            len(near_unique),
            4,
        )
        == 0,
        "factorize_use_native_fixed near-unique column",
    )
    ok(
        lib.xyg_factorize_use_native_fixed(None, 0, 4) == 1,
        "factorize_use_native_fixed empty column",
    )
    ok(
        lib.xyg_factorize_use_native_fixed(None, 0, 0) == -1,
        "factorize_use_native_fixed invalid width",
    )
    category_kinds = array("B", [1, 0, 1, 0, 1])
    category_in_lens = array("I", [1, 0, 1, 0, 1])
    category_in_texts = array("B", b"ba1")
    category_out_lens = array("I", [0, 0, 0, 0, 0])
    category_out_texts = array("B", [0] * 32)
    category_written = lib.xyg_category_labels_packed(
        _ptr(category_kinds, ctypes.c_uint8),
        _ptr(category_in_lens, ctypes.c_uint32),
        _ptr(category_in_texts, ctypes.c_uint8),
        len(category_in_texts),
        5,
        _ptr(category_out_lens, ctypes.c_uint32),
        _ptr(category_out_texts, ctypes.c_uint8),
        len(category_out_texts),
    )
    ok(category_written == 5, "category_labels_packed row count")
    category_blob = bytes(category_out_texts[: sum(category_out_lens)])
    ok(category_blob == b"b(missing)a(missing)1", "category_labels_packed labels")
    stringlike_tags = array("B", [1, 0, 2, 3])
    ok(
        lib.xyg_object_rows_all_stringlike(_ptr(stringlike_tags, ctypes.c_uint8), 3) == 1,
        "object_rows_all_stringlike accepts missing/text/bytes",
    )
    ok(
        lib.xyg_object_rows_all_stringlike(_ptr(stringlike_tags, ctypes.c_uint8), 4) == 0,
        "object_rows_all_stringlike rejects other rows",
    )
    ok(
        lib.xyg_object_rows_all_stringlike(_ptr(stringlike_tags, ctypes.c_uint8), 0) == 1,
        "object_rows_all_stringlike empty column",
    )
    real_numeric_tags = array("B", [1, 0, 4])
    ok(
        lib.xyg_object_rows_all_real_numeric(_ptr(real_numeric_tags, ctypes.c_uint8), 3) == 1,
        "object_rows_all_real_numeric accepts numeric/coercible rows",
    )
    ok(
        lib.xyg_object_rows_all_real_numeric(_ptr(real_numeric_tags, ctypes.c_uint8), 0) == 0,
        "object_rows_all_real_numeric empty column",
    )
    real_numeric_mixed = array("B", [1, 3])
    ok(
        lib.xyg_object_rows_all_real_numeric(_ptr(real_numeric_mixed, ctypes.c_uint8), 2) == 0,
        "object_rows_all_real_numeric rejects text rows",
    )
    transition_low = array("I", [99, 99])
    transition_high = array("I", [99, 99])
    transition_first = ctypes.c_size_t(size_max)
    transition_index = ctypes.c_size_t(size_max)
    transition_records = array("B", b"a\0\0a\0b")
    status = lib.xyg_transition_keys_fixed(
        _ptr(transition_records, ctypes.c_uint8),
        2,
        3,
        1,
        0,
        _ptr(transition_low, ctypes.c_uint32),
        _ptr(transition_high, ctypes.c_uint32),
        ctypes.byref(transition_first),
        ctypes.byref(transition_index),
    )
    ok(status == 0, "transition_keys_fixed success status")
    ok(
        list(transition_low) == [0x5B3B753B, 0xB1A7FF88]
        and list(transition_high) == [0xE1379B39, 0x9D296CBA],
        "transition_keys_fixed personalized digest words",
    )
    duplicate_records = array("B", b"a\0\0b\0\0a\0\0")
    duplicate_low = array("I", [99, 99, 99])
    duplicate_high = array("I", [99, 99, 99])
    status = lib.xyg_transition_keys_fixed(
        _ptr(duplicate_records, ctypes.c_uint8),
        3,
        3,
        1,
        0,
        _ptr(duplicate_low, ctypes.c_uint32),
        _ptr(duplicate_high, ctypes.c_uint32),
        ctypes.byref(transition_first),
        ctypes.byref(transition_index),
    )
    ok(
        status == 2 and transition_first.value == 0 and transition_index.value == 2,
        "transition_keys_fixed duplicate rows",
    )
    ok(
        lib.xyg_transition_keys_fixed(
            null_u8,
            0,
            1,
            1,
            0,
            null_u32,
            null_u32,
            ctypes.byref(transition_first),
            ctypes.byref(transition_index),
        )
        == 0,
        "transition_keys_fixed empty/null succeeds",
    )
    ok(
        lib.xyg_transition_keys_fixed(
            null_u8,
            1,
            1,
            1,
            0,
            null_u32,
            null_u32,
            ctypes.byref(transition_first),
            ctypes.byref(transition_index),
        )
        == 4,
        "transition_keys_fixed non-empty/null is an argument error",
    )
    nonfinite_records = array("d", [float("inf")])
    nonfinite_low = array("I", [99])
    nonfinite_high = array("I", [99])
    transition_first = ctypes.c_size_t(size_max)
    transition_index = ctypes.c_size_t(size_max)
    ok(
        lib.xyg_transition_keys_fixed(
            _ptr(nonfinite_records, ctypes.c_uint8),
            1,
            8,
            5,
            0,
            _ptr(nonfinite_low, ctypes.c_uint32),
            _ptr(nonfinite_high, ctypes.c_uint32),
            ctypes.byref(transition_first),
            ctypes.byref(transition_index),
        )
        == 1
        and transition_first.value == 0,
        "transition_keys_fixed declines non-finite data with its row",
    )
    ok(
        lib.xyg_transition_keys_fixed(
            _ptr(nonfinite_records, ctypes.c_uint8),
            1,
            3,
            0,
            0,
            _ptr(nonfinite_low, ctypes.c_uint32),
            _ptr(nonfinite_high, ctypes.c_uint32),
            ctypes.byref(transition_first),
            ctypes.byref(transition_index),
        )
        == 4,
        "transition_keys_fixed bad layout is an argument error",
    )
    small_unique = array("I", [99] * 2)
    ok(
        lib.xyg_factorize_fixed_u8(
            _ptr(records, ctypes.c_uint8),
            5,
            3,
            _ptr(compact_codes, ctypes.c_uint8),
            _ptr(small_unique, ctypes.c_uint32),
            2,
        )
        == factorize_capacity_exceeded,
        "factorize_fixed_u8 capacity sentinel",
    )
    remap = array("B", [2, 0, 1])
    ok(
        lib.xyg_remap_u8(
            _ptr(compact_codes, ctypes.c_uint8),
            len(compact_codes),
            _ptr(remap, ctypes.c_uint8),
            len(remap),
        )
        == 1
        and list(compact_codes) == [2, 0, 2, 1, 0],
        "remap_u8 in-place codebook",
    )
    fold_in = (ctypes.c_uint32 * 5)(0, 9, 10, 257, 300)
    fold_out = array("B", [0] * 5)
    ok(
        lib.xyg_fold_codes_u8(fold_in, 5, 10, _ptr(fold_out, ctypes.c_uint8)) == 1
        and list(fold_out) == [0, 9, 0, 7, 0],
        "fold_codes_u8 wide categorical fold",
    )
    ok(
        lib.xyg_fold_codes_u8(None, 0, 10, None) == 1,
        "fold_codes_u8 empty column",
    )

    # Boundary guardrails: empty inputs may carry null pointers; invalid
    # non-empty null inputs must return sentinels/flags rather than crash.
    off = ctypes.c_double()
    ok(
        lib.xyg_geometry_offset(1, 10.0, 20.0, ctypes.byref(off)) == 1 and off.value == 0.0,
        "geometry_offset pin_zero",
    )
    ok(
        lib.xyg_geometry_offset(0, 10.0, 20.0, ctypes.byref(off)) == 1 and off.value == 15.0,
        "geometry_offset midpoint",
    )
    ok(lib.xyg_geometry_offset(0, 10.0, 20.0, null_f64) == 0, "geometry_offset null out")
    ok(lib.xyg_geometry_offset(2, 10.0, 20.0, ctypes.byref(off)) == 0, "geometry_offset bad pin")
    log_name = array("B", b"log")
    linear_name = array("B", b"linear")
    ok(
        lib.xyg_scale_pins_offset(_ptr(log_name, ctypes.c_uint8), len(log_name)) == 1,
        "scale_pins_offset log",
    )
    ok(
        lib.xyg_scale_pins_offset(_ptr(linear_name, ctypes.c_uint8), len(linear_name)) == 0,
        "scale_pins_offset linear",
    )
    ok(lib.xyg_scale_pins_offset(null_u8, 0) == 0, "scale_pins_offset empty")
    meta_out = array("d", [0.0, 0.0])
    kind_name = array("B", b"float")
    dummy_kind = array("B", [0])
    ok(
        lib.xyg_encoded_column_meta(0.0, -1.0, 1.0, null_u8, 0, _ptr(meta_out, ctypes.c_double), 2)
        == 0
        and meta_out[0] == 0.0
        and meta_out[1] == 1.0,
        "encoded_column_meta omitted kind",
    )
    ok(
        lib.xyg_encoded_column_meta(
            0.0,
            -1.0,
            1.0,
            _ptr(kind_name, ctypes.c_uint8),
            len(kind_name),
            _ptr(meta_out, ctypes.c_double),
            2,
        )
        == 1
        and meta_out[0] == 0.0
        and meta_out[1] == 1.0,
        "encoded_column_meta present kind",
    )
    ok(
        lib.xyg_encoded_column_meta(
            1.0,
            0.0,
            2.0,
            _ptr(dummy_kind, ctypes.c_uint8),
            0,
            _ptr(meta_out, ctypes.c_double),
            2,
        )
        == 1,
        "encoded_column_meta empty present kind",
    )
    ok(
        lib.xyg_encoded_column_meta(0.0, -1.0, 1.0, null_u8, 0, null_f64, 2) == -2,
        "encoded_column_meta null out",
    )
    dashed_name = array("B", b"dashed")
    dash_out = array("d", [0.0] * 8)
    dash_n = ctypes.c_size_t(0)
    ok(
        lib.xyg_scene_dash_admit(
            _ptr(dashed_name, ctypes.c_uint8),
            len(dashed_name),
            null_f64,
            0,
            0,
            _ptr(dash_out, ctypes.c_double),
            8,
            ctypes.byref(dash_n),
        )
        == 1
        and dash_n.value == 2
        and dash_out[0] == 6.0
        and dash_out[1] == 4.0,
        "scene_dash_admit dashed",
    )
    bad_dash = array("B", b"6,foo,4")
    ok(
        lib.xyg_scene_dash_admit(
            _ptr(bad_dash, ctypes.c_uint8),
            len(bad_dash),
            null_f64,
            0,
            0,
            _ptr(dash_out, ctypes.c_double),
            8,
            ctypes.byref(dash_n),
        )
        == -1,
        "scene_dash_admit rejects bad tokens",
    )
    ok(
        lib.xyg_scene_dash_admit(
            null_u8,
            0,
            null_f64,
            0,
            1,
            _ptr(dash_out, ctypes.c_double),
            8,
            ctypes.byref(dash_n),
        )
        == -1,
        "scene_dash_admit empty list",
    )
    ok(
        lib.xyg_scene_dash_admit(
            null_u8,
            0,
            null_f64,
            0,
            0,
            _ptr(dash_out, ctypes.c_double),
            8,
            ctypes.byref(dash_n),
        )
        == 0,
        "scene_dash_admit omitted",
    )
    butt_name = array("B", b"butt")
    ok(
        lib.xyg_scene_linecap_admit(_ptr(butt_name, ctypes.c_uint8), len(butt_name)) == 0,
        "scene_linecap_admit butt",
    )
    square_name = array("B", b"SQUARE")
    ok(
        lib.xyg_scene_linecap_admit(_ptr(square_name, ctypes.c_uint8), len(square_name)) == 2,
        "scene_linecap_admit square",
    )
    round_name = array("B", b" round ")
    ok(
        lib.xyg_scene_linecap_admit(_ptr(round_name, ctypes.c_uint8), len(round_name)) == 255,
        "scene_linecap_admit round",
    )
    ok(lib.xyg_scene_linecap_admit(null_u8, 0) == 255, "scene_linecap_admit omitted")
    bad_cap = array("B", b"foo")
    ok(
        lib.xyg_scene_linecap_admit(_ptr(bad_cap, ctypes.c_uint8), len(bad_cap)) == -1,
        "scene_linecap_admit rejects unknown",
    )
    overlay = ctypes.c_double()
    ok(
        lib.xyg_density_overlay_opacity(0.8, ctypes.byref(overlay)) == 1 and overlay.value == 0.55,
        "density_overlay_opacity default cap",
    )
    ok(
        lib.xyg_density_overlay_opacity(0.3, ctypes.byref(overlay)) == 1 and overlay.value == 0.3,
        "density_overlay_opacity below cap",
    )
    ok(
        lib.xyg_density_overlay_opacity(float("nan"), ctypes.byref(overlay)) == 1
        and overlay.value == 0.55,
        "density_overlay_opacity nan",
    )
    ok(lib.xyg_density_overlay_opacity(0.8, null_f64) == 0, "density_overlay_opacity null out")
    marker_vals = array("d", [-0.5, -0.5, 0.5, -0.5, 0.0, 0.5])
    marker_lens = array("I", [6])
    ok(
        lib.xyg_scene_marker_path_admit(
            _ptr(marker_vals, ctypes.c_double),
            len(marker_vals),
            _ptr(marker_lens, ctypes.c_uint32),
            len(marker_lens),
        )
        == 1,
        "scene_marker_path_admit triangle",
    )
    bad_marker = array("d", [0.0, 0.0])
    bad_lens = array("I", [2])
    ok(
        lib.xyg_scene_marker_path_admit(
            _ptr(bad_marker, ctypes.c_double),
            len(bad_marker),
            _ptr(bad_lens, ctypes.c_uint32),
            len(bad_lens),
        )
        == 0,
        "scene_marker_path_admit short contour",
    )
    ok(
        lib.xyg_scene_marker_path_admit(null_f64, 0, null_u32, 0) == 0,
        "scene_marker_path_admit empty",
    )
    arrow_kind = array("B", b"arrow")
    width_key = array("B", b"width")
    dash_key = array("B", b"dash")
    color_key = array("B", b"color")
    ok(
        lib.xyg_scene_annotation_style_admit(
            _ptr(arrow_kind, ctypes.c_uint8),
            len(arrow_kind),
            0,
            0,
            _ptr(width_key, ctypes.c_uint8),
            len(width_key),
        )
        == 1,
        "scene_annotation_style_admit arrow width",
    )
    ok(
        lib.xyg_scene_annotation_style_admit(
            _ptr(arrow_kind, ctypes.c_uint8),
            len(arrow_kind),
            0,
            0,
            _ptr(dash_key, ctypes.c_uint8),
            len(dash_key),
        )
        == 0,
        "scene_annotation_style_admit arrow dash",
    )
    ok(
        lib.xyg_scene_annotation_style_admit(
            null_u8, 0, 0, 0, _ptr(color_key, ctypes.c_uint8), len(color_key)
        )
        == 1,
        "scene_annotation_style_admit empty kind color",
    )
    ok(
        lib.xyg_scene_annotation_style_admit(null_u8, 0, 0, 0, null_u8, 0) == 0,
        "scene_annotation_style_admit empty key",
    )
    paint = array("B", b"#336699")
    other = array("B", b"#34d399")
    ok(
        lib.xyg_scene_ribbon_color2_classify(
            0, 1, 0, null_u8, 0, 0, null_u8, 0, _ptr(paint, ctypes.c_uint8), len(paint), 0, 0
        )
        == 0,
        "scene_ribbon_color2_classify absent",
    )
    ok(
        lib.xyg_scene_ribbon_color2_classify(
            1,
            1,
            1,
            _ptr(paint, ctypes.c_uint8),
            len(paint),
            1,
            _ptr(other, ctypes.c_uint8),
            len(other),
            _ptr(paint, ctypes.c_uint8),
            len(paint),
            0,
            0,
        )
        == 2,
        "scene_ribbon_color2_classify gradient",
    )
    ok(
        lib.xyg_scene_ribbon_color2_classify(
            1, 1, 0, null_u8, 0, 0, null_u8, 0, _ptr(paint, ctypes.c_uint8), len(paint), 0, 0
        )
        == 4,
        "scene_ribbon_color2_classify ends fail",
    )
    hide_name = array("B", b"hide")
    ok(
        lib.xyg_scene_tick_label_strategy(_ptr(hide_name, ctypes.c_uint8), len(hide_name)) == 1,
        "scene_tick_label_strategy hide",
    )
    overlap_name = array("B", b"hide-overlap")
    ok(
        lib.xyg_scene_tick_label_strategy(_ptr(overlap_name, ctypes.c_uint8), len(overlap_name))
        == 0,
        "scene_tick_label_strategy hide-overlap",
    )
    ok(lib.xyg_scene_tick_label_strategy(null_u8, 0) == 0, "scene_tick_label_strategy empty")
    start_name = array("B", b"start")
    ok(
        lib.xyg_scene_tick_anchor(_ptr(start_name, ctypes.c_uint8), len(start_name)) == 0,
        "scene_tick_anchor start",
    )
    middle_name = array("B", b"middle")
    ok(
        lib.xyg_scene_tick_anchor(_ptr(middle_name, ctypes.c_uint8), len(middle_name)) == 1,
        "scene_tick_anchor middle",
    )
    ok(lib.xyg_scene_tick_anchor(null_u8, 0) == -1, "scene_tick_anchor empty")
    grad_space = array("B", b"mark")
    grad_dir = array("B", b"down")
    grad_t = array("d", [0.0, 1.0])
    grad_a = b"#336699"
    grad_b = b"#34d399"
    grad_css = array("B", grad_a + grad_b)
    grad_lens = array("I", [len(grad_a), len(grad_b)])
    grad_mark = array("B", b"#3987e5")
    grad_out = array("B", [0] * 8)
    ok(
        lib.xyg_scene_fill_gradient_admit(
            _ptr(grad_space, ctypes.c_uint8),
            len(grad_space),
            _ptr(grad_dir, ctypes.c_uint8),
            len(grad_dir),
            _ptr(grad_t, ctypes.c_double),
            2,
            _ptr(grad_css, ctypes.c_uint8),
            len(grad_css),
            _ptr(grad_lens, ctypes.c_uint32),
            2,
            _ptr(grad_mark, ctypes.c_uint8),
            len(grad_mark),
            _ptr(grad_out, ctypes.c_uint8),
            8,
        )
        == 1,
        "scene_fill_gradient_admit pair",
    )
    grad_var_a = b"var(--accent)"
    grad_var_b = b"#ffffff"
    grad_var = array("B", grad_var_a + grad_var_b)
    grad_var_lens = array("I", [len(grad_var_a), len(grad_var_b)])
    ok(
        lib.xyg_scene_fill_gradient_admit(
            _ptr(grad_space, ctypes.c_uint8),
            len(grad_space),
            _ptr(grad_dir, ctypes.c_uint8),
            len(grad_dir),
            _ptr(grad_t, ctypes.c_double),
            2,
            _ptr(grad_var, ctypes.c_uint8),
            len(grad_var),
            _ptr(grad_var_lens, ctypes.c_uint32),
            2,
            _ptr(grad_mark, ctypes.c_uint8),
            len(grad_mark),
            _ptr(grad_out, ctypes.c_uint8),
            8,
        )
        == 0,
        "scene_fill_gradient_admit var reject",
    )
    parse_css = array("B", b"linear-gradient(red, blue)")
    parse_space = array("B", b"mark")
    parse_dir = ctypes.c_uint8(255)
    parse_t = array("d", [0.0] * 8)
    parse_css_out = array("B", [0] * 256)
    parse_lens = array("I", [0] * 8)
    parse_n = ctypes.c_size_t(0)
    ok(
        lib.xyg_scene_parse_linear_gradient(
            _ptr(parse_css, ctypes.c_uint8),
            len(parse_css),
            _ptr(parse_space, ctypes.c_uint8),
            len(parse_space),
            ctypes.byref(parse_dir),
            _ptr(parse_t, ctypes.c_double),
            8,
            _ptr(parse_css_out, ctypes.c_uint8),
            len(parse_css_out),
            _ptr(parse_lens, ctypes.c_uint32),
            8,
            ctypes.byref(parse_n),
        )
        == 1
        and parse_dir.value == 0
        and parse_n.value == 2
        and abs(parse_t[0] - 0.0) < 1e-15
        and abs(parse_t[1] - 1.0) < 1e-15,
        "scene_parse_linear_gradient pair",
    )
    parse_deg = array("B", b"linear-gradient(45deg, red, blue)")
    ok(
        lib.xyg_scene_parse_linear_gradient(
            _ptr(parse_deg, ctypes.c_uint8),
            len(parse_deg),
            _ptr(parse_space, ctypes.c_uint8),
            len(parse_space),
            ctypes.byref(parse_dir),
            _ptr(parse_t, ctypes.c_double),
            8,
            _ptr(parse_css_out, ctypes.c_uint8),
            len(parse_css_out),
            _ptr(parse_lens, ctypes.c_uint32),
            8,
            ctypes.byref(parse_n),
        )
        == 3,
        "scene_parse_linear_gradient degree reject",
    )
    parse_left = array("B", b"linear-gradient(to left, red, blue)")
    ok(
        lib.xyg_scene_parse_linear_gradient(
            _ptr(parse_left, ctypes.c_uint8),
            len(parse_left),
            _ptr(parse_space, ctypes.c_uint8),
            len(parse_space),
            ctypes.byref(parse_dir),
            _ptr(parse_t, ctypes.c_double),
            8,
            _ptr(parse_css_out, ctypes.c_uint8),
            len(parse_css_out),
            _ptr(parse_lens, ctypes.c_uint32),
            8,
            ctypes.byref(parse_n),
        )
        == 4,
        "scene_parse_linear_gradient mark axis",
    )
    ok(
        lib.xyg_scene_parse_linear_gradient(
            null_u8,
            0,
            _ptr(parse_space, ctypes.c_uint8),
            len(parse_space),
            ctypes.byref(parse_dir),
            _ptr(parse_t, ctypes.c_double),
            8,
            _ptr(parse_css_out, ctypes.c_uint8),
            len(parse_css_out),
            _ptr(parse_lens, ctypes.c_uint32),
            8,
            ctypes.byref(parse_n),
        )
        == 0,
        "scene_parse_linear_gradient empty",
    )
    bar_kind = array("B", b"bar")
    zero_r = array("d", [0.0])
    ok(
        lib.xyg_scene_rect_extra_flags(
            _ptr(bar_kind, ctypes.c_uint8),
            len(bar_kind),
            0,
            0,
            _ptr(zero_r, ctypes.c_double),
            1,
            0,
            0.0,
        )
        == 0,
        "scene_rect_extra_flags clean bar",
    )
    ok(
        lib.xyg_scene_rect_extra_flags(
            _ptr(bar_kind, ctypes.c_uint8),
            len(bar_kind),
            0,
            1,
            _ptr(zero_r, ctypes.c_double),
            1,
            0,
            0.0,
        )
        == (1 << 5),
        "scene_rect_extra_flags gradient fail",
    )
    pair_r = array("d", [1.0])
    ok(
        lib.xyg_scene_rect_extra_flags(
            _ptr(bar_kind, ctypes.c_uint8),
            len(bar_kind),
            0,
            0,
            _ptr(pair_r, ctypes.c_double),
            1,
            1,
            0.0,
        )
        == (1 << 6),
        "scene_rect_extra_flags seq radius",
    )
    ok(
        lib.xyg_scene_rect_extra_flags(
            _ptr(bar_kind, ctypes.c_uint8),
            len(bar_kind),
            1,
            0,
            _ptr(zero_r, ctypes.c_double),
            1,
            0,
            0.2,
        )
        == 0,
        "scene_rect_extra_flags polar wedge",
    )
    ok(
        lib.xyg_scene_rect_extra_flags(null_u8, 0, 0, 0, null_f64, 0, 0, 0.2) == (1 << 7),
        "scene_rect_extra_flags empty kind wedge",
    )
    down_name = array("B", b"down")
    up_name = array("B", b"up")
    right_name = array("B", b"right")
    left_name = array("B", b"left")
    down_upper = array("B", b"DOWN")
    to_bottom = array("B", b"to bottom")
    ok(
        lib.xyg_scene_gradient_dir(_ptr(down_name, ctypes.c_uint8), len(down_name)) == 0,
        "scene_gradient_dir down",
    )
    ok(
        lib.xyg_scene_gradient_dir(_ptr(up_name, ctypes.c_uint8), len(up_name)) == 1,
        "scene_gradient_dir up",
    )
    ok(
        lib.xyg_scene_gradient_dir(_ptr(right_name, ctypes.c_uint8), len(right_name)) == 2,
        "scene_gradient_dir right",
    )
    ok(
        lib.xyg_scene_gradient_dir(_ptr(left_name, ctypes.c_uint8), len(left_name)) == 3,
        "scene_gradient_dir left",
    )
    ok(lib.xyg_scene_gradient_dir(null_u8, 0) == 255, "scene_gradient_dir empty")
    ok(
        lib.xyg_scene_gradient_dir(_ptr(down_upper, ctypes.c_uint8), len(down_upper)) == 255,
        "scene_gradient_dir DOWN",
    )
    ok(
        lib.xyg_scene_gradient_dir(_ptr(to_bottom, ctypes.c_uint8), len(to_bottom)) == 255,
        "scene_gradient_dir to bottom",
    )
    grad_css = array("B", b"linear-gradient(red, blue)")
    grad_upper = array("B", b"  LINEAR-GRADIENT(red, blue)  ")
    radial_css = array("B", b"radial-gradient(red, blue)")
    ok(
        lib.xyg_scene_linear_gradient_prefix(_ptr(grad_css, ctypes.c_uint8), len(grad_css)) == 1,
        "scene_linear_gradient_prefix css",
    )
    ok(
        lib.xyg_scene_linear_gradient_prefix(_ptr(grad_upper, ctypes.c_uint8), len(grad_upper))
        == 1,
        "scene_linear_gradient_prefix upper",
    )
    ok(
        lib.xyg_scene_linear_gradient_prefix(_ptr(radial_css, ctypes.c_uint8), len(radial_css))
        == 0,
        "scene_linear_gradient_prefix radial",
    )
    ok(lib.xyg_scene_linear_gradient_prefix(null_u8, 0) == 0, "scene_linear_gradient_prefix empty")
    mark_name = array("B", b"mark")
    plot_name = array("B", b"plot")
    mark_upper = array("B", b"MARK")
    ok(
        lib.xyg_scene_gradient_space(_ptr(mark_name, ctypes.c_uint8), len(mark_name)) == 0,
        "scene_gradient_space mark",
    )
    ok(
        lib.xyg_scene_gradient_space(_ptr(plot_name, ctypes.c_uint8), len(plot_name)) == 1,
        "scene_gradient_space plot",
    )
    ok(lib.xyg_scene_gradient_space(null_u8, 0) == 255, "scene_gradient_space empty")
    ok(
        lib.xyg_scene_gradient_space(_ptr(mark_upper, ctypes.c_uint8), len(mark_upper)) == 255,
        "scene_gradient_space MARK",
    )
    count_name = array("B", b"count")
    mean_name = array("B", b"mean")
    count_upper = array("B", b"COUNT")
    ok(
        lib.xyg_scene_hexbin_reduce_admit(_ptr(count_name, ctypes.c_uint8), len(count_name)) == 1,
        "scene_hexbin_reduce_admit count",
    )
    ok(
        lib.xyg_scene_hexbin_reduce_admit(_ptr(mean_name, ctypes.c_uint8), len(mean_name)) == 1,
        "scene_hexbin_reduce_admit mean",
    )
    ok(lib.xyg_scene_hexbin_reduce_admit(null_u8, 0) == 0, "scene_hexbin_reduce_admit empty")
    ok(
        lib.xyg_scene_hexbin_reduce_admit(_ptr(count_upper, ctypes.c_uint8), len(count_upper)) == 0,
        "scene_hexbin_reduce_admit COUNT",
    )
    linear_name = array("B", b"linear")
    smooth_name = array("B", b"smooth")
    smooth_upper = array("B", b"SMOOTH")
    ok(
        lib.xyg_scene_curve_classify(_ptr(linear_name, ctypes.c_uint8), len(linear_name)) == 0,
        "scene_curve_classify linear",
    )
    ok(
        lib.xyg_scene_curve_classify(_ptr(smooth_name, ctypes.c_uint8), len(smooth_name)) == 1,
        "scene_curve_classify smooth",
    )
    ok(lib.xyg_scene_curve_classify(null_u8, 0) == 255, "scene_curve_classify empty")
    ok(
        lib.xyg_scene_curve_classify(_ptr(smooth_upper, ctypes.c_uint8), len(smooth_upper)) == 1,
        "scene_curve_classify SMOOTH",
    )
    glyph_ok = array("B", b"A")
    glyph_nl = array("B", b"a\nb")
    glyph_long = array("B", b"x" * 65)
    ok(
        lib.xyg_scene_marker_glyph_admit(_ptr(glyph_ok, ctypes.c_uint8), len(glyph_ok)) == 1,
        "scene_marker_glyph_admit A",
    )
    ok(lib.xyg_scene_marker_glyph_admit(null_u8, 0) == 0, "scene_marker_glyph_admit empty")
    ok(
        lib.xyg_scene_marker_glyph_admit(_ptr(glyph_nl, ctypes.c_uint8), len(glyph_nl)) == 0,
        "scene_marker_glyph_admit newline",
    )
    ok(
        lib.xyg_scene_marker_glyph_admit(_ptr(glyph_long, ctypes.c_uint8), len(glyph_long)) == 0,
        "scene_marker_glyph_admit over-cap",
    )
    scatter_kind = array("B", b"scatter")
    mark_kind = array("B", b"mark")
    scatter_upper = array("B", b"SCATTER")
    ok(
        lib.xyg_scene_kind_admit(_ptr(scatter_kind, ctypes.c_uint8), len(scatter_kind)) == 1,
        "scene_kind_admit scatter",
    )
    ok(lib.xyg_scene_kind_admit(null_u8, 0) == 0, "scene_kind_admit empty")
    ok(
        lib.xyg_scene_kind_admit(_ptr(mark_kind, ctypes.c_uint8), len(mark_kind)) == 0,
        "scene_kind_admit mark",
    )
    ok(
        lib.xyg_scene_kind_admit(_ptr(scatter_upper, ctypes.c_uint8), len(scatter_upper)) == 0,
        "scene_kind_admit SCATTER",
    )
    bar_kind = array("B", b"bar")
    ok(
        lib.xyg_scene_kind_class(_ptr(bar_kind, ctypes.c_uint8), len(bar_kind)) == 1,
        "scene_kind_class bar",
    )
    ok(
        lib.xyg_scene_kind_class(_ptr(scatter_kind, ctypes.c_uint8), len(scatter_kind)) == 1 << 8,
        "scene_kind_class scatter",
    )
    ok(lib.xyg_scene_kind_class(null_u8, 0) == 0, "scene_kind_class empty")
    ok(
        lib.xyg_scene_kind_class(_ptr(mark_kind, ctypes.c_uint8), len(mark_kind)) == 0,
        "scene_kind_class mark",
    )
    ok(lib.xyg_scene_hexbin_pitch_admit(1.0, 2.0) == 1, "scene_hexbin_pitch_admit ok")
    ok(lib.xyg_scene_hexbin_pitch_admit(0.0, 1.0) == 0, "scene_hexbin_pitch_admit zero")
    ok(
        lib.xyg_scene_hexbin_pitch_admit(float("nan"), 1.0) == 0,
        "scene_hexbin_pitch_admit nan",
    )
    ok(
        lib.xyg_scene_heatmap_extent_admit(0.0, 1.0, 0.0, 1.0) == 1,
        "scene_heatmap_extent_admit ok",
    )
    ok(
        lib.xyg_scene_heatmap_extent_admit(0.0, 0.0, 0.0, 1.0) == 0,
        "scene_heatmap_extent_admit equal",
    )
    ok(
        lib.xyg_scene_heatmap_extent_admit(float("nan"), 1.0, 0.0, 1.0) == 0,
        "scene_heatmap_extent_admit nan",
    )
    ok(
        lib.xyg_scene_heatmap_colormap_admit(0, 0, 0, 0) == 0,
        "scene_heatmap_colormap_admit none",
    )
    ok(
        lib.xyg_scene_heatmap_colormap_admit(1, 0, 0, 0) == 1,
        "scene_heatmap_colormap_admit truecolor",
    )
    ok(
        lib.xyg_scene_heatmap_colormap_admit(0, 1, 0, 0) == 1,
        "scene_heatmap_colormap_admit colormap",
    )
    ok(lib.xyg_scene_heatmap_shape_admit(1.0, 2.0) == 1, "scene_heatmap_shape_admit ok")
    ok(lib.xyg_scene_heatmap_shape_admit(0.0, 2.0) == 0, "scene_heatmap_shape_admit zero")
    ok(
        lib.xyg_scene_heatmap_shape_admit(1.5, 2.0) == 0,
        "scene_heatmap_shape_admit fractional",
    )
    color_ch = array("B", b"color")
    stroke_upper = array("B", b"STROKE")
    color_pad = array("B", b" color")
    ok(
        lib.xyg_scene_scatter_paint_channel_admit(_ptr(color_ch, ctypes.c_uint8), len(color_ch))
        == 1,
        "scene_scatter_paint_channel_admit color",
    )
    ok(
        lib.xyg_scene_scatter_paint_channel_admit(null_u8, 0) == 0,
        "scene_scatter_paint_channel_admit empty",
    )
    ok(
        lib.xyg_scene_scatter_paint_channel_admit(
            _ptr(stroke_upper, ctypes.c_uint8), len(stroke_upper)
        )
        == 0,
        "scene_scatter_paint_channel_admit STROKE",
    )
    ok(
        lib.xyg_scene_scatter_paint_channel_admit(_ptr(color_pad, ctypes.c_uint8), len(color_pad))
        == 0,
        "scene_scatter_paint_channel_admit padded color",
    )
    continuous_mode = array("B", b"continuous")
    ok(
        lib.xyg_scene_hexbin_colormap_plane_admit(
            _ptr(continuous_mode, ctypes.c_uint8), len(continuous_mode), 1
        )
        == 1,
        "scene_hexbin_colormap_plane_admit continuous values",
    )
    ok(
        lib.xyg_scene_hexbin_colormap_plane_admit(
            _ptr(continuous_mode, ctypes.c_uint8), len(continuous_mode), 0
        )
        == 0,
        "scene_hexbin_colormap_plane_admit continuous empty",
    )
    ok(
        lib.xyg_scene_hexbin_colormap_plane_admit(null_u8, 0, 1) == 0,
        "scene_hexbin_colormap_plane_admit empty mode",
    )
    categorical_mode = array("B", b"categorical")
    ok(
        lib.xyg_scene_hexbin_rgba_plane_admit(
            _ptr(categorical_mode, ctypes.c_uint8), len(categorical_mode)
        )
        == 1,
        "scene_hexbin_rgba_plane_admit categorical",
    )
    ok(
        lib.xyg_scene_hexbin_rgba_plane_admit(null_u8, 0) == 0,
        "scene_hexbin_rgba_plane_admit empty",
    )
    mesh_kind = array("B", b"triangle_mesh")
    ok(
        lib.xyg_scene_mesh_paint_plane_admit(_ptr(mesh_kind, ctypes.c_uint8), len(mesh_kind), 0, 1)
        == 1,
        "scene_mesh_paint_plane_admit triangle_mesh",
    )
    ok(
        lib.xyg_scene_mesh_paint_plane_admit(_ptr(mesh_kind, ctypes.c_uint8), len(mesh_kind), 1, 1)
        == 0,
        "scene_mesh_paint_plane_admit joined_fill",
    )
    ok(
        lib.xyg_scene_mesh_paint_plane_admit(null_u8, 0, 0, 1) == 0,
        "scene_mesh_paint_plane_admit empty",
    )
    item_packed = array("B", [10, 20, 30, 40])
    item_out = array("B", [0, 0, 0, 0])
    item_artist = array("d", [0.5])
    ok(
        lib.xyg_scene_item_apply_opacity(
            _ptr(item_packed, ctypes.c_uint8),
            4,
            1,
            _ptr(item_artist, ctypes.c_double),
            1,
            1,
            null_f64,
            0,
            0,
            _ptr(item_out, ctypes.c_uint8),
            4,
        )
        == 1
        and item_out[3] == 128,
        "scene_item_apply_opacity artist",
    )
    ok(
        lib.xyg_scene_item_apply_opacity(null_u8, 0, 0, null_f64, 0, 0, null_f64, 0, 0, null_u8, 0)
        == 1,
        "scene_item_apply_opacity empty",
    )
    item_widths = array("d", [0.0, 1.5])
    ok(
        lib.xyg_scene_item_widths_admit(_ptr(item_widths, ctypes.c_double), 2, 1, 2, 0.0) == 1,
        "scene_item_widths_admit values",
    )
    ok(
        lib.xyg_scene_item_widths_admit(null_f64, 0, 0, 3, 2.5) == 1,
        "scene_item_widths_admit scalar",
    )
    ok(
        lib.xyg_scene_item_widths_admit(null_f64, 0, 0, 3, -1.0) == 0,
        "scene_item_widths_admit scalar reject",
    )
    item_fill_values = array("d", [0.0, 10.0])
    item_fill_out = array("d", [0.0, 0.0])
    ok(
        lib.xyg_scene_item_fill_t(
            _ptr(item_fill_values, ctypes.c_double),
            2,
            2,
            0.0,
            10.0,
            1,
            _ptr(item_fill_out, ctypes.c_double),
            2,
        )
        == 1
        and item_fill_out[0] == 0.0
        and item_fill_out[1] == 1.0,
        "scene_item_fill_t domain",
    )
    ok(
        lib.xyg_scene_item_fill_t(null_f64, 0, 1, 0.0, 1.0, 0, null_f64, 0) == 0,
        "scene_item_fill_t empty reject",
    )
    ok(lib.xyg_scene_finite_all(null_f64, 0) == 1, "scene_finite_all empty")
    finite_all = array("d", [0.0, 1.5])
    ok(
        lib.xyg_scene_finite_all(_ptr(finite_all, ctypes.c_double), 2) == 1,
        "scene_finite_all finite",
    )
    nan_all = array("d", [float("nan")])
    ok(
        lib.xyg_scene_finite_all(_ptr(nan_all, ctypes.c_double), 1) == 0,
        "scene_finite_all nan",
    )
    solid_out = array("B", [0] * 16)
    ok(
        lib.xyg_scene_gradient_solid_css(null_u8, 0, _ptr(solid_out, ctypes.c_uint8), 16) == 10
        and bytes(solid_out[:10]) == b"rgb(0,0,0)",
        "scene_gradient_solid_css empty",
    )
    solid_rgba = array("B", [1, 2, 3, 0, 10, 20, 30, 255])
    ok(
        lib.xyg_scene_gradient_solid_css(
            _ptr(solid_rgba, ctypes.c_uint8), 8, _ptr(solid_out, ctypes.c_uint8), 16
        )
        == 13
        and bytes(solid_out[:13]) == b"rgb(10,20,30)",
        "scene_gradient_solid_css first opaque",
    )
    odd_rgba = array("B", [1, 2, 3])
    ok(
        lib.xyg_scene_gradient_solid_css(
            _ptr(odd_rgba, ctypes.c_uint8), 3, _ptr(solid_out, ctypes.c_uint8), 16
        )
        == 0,
        "scene_gradient_solid_css odd reject",
    )
    ok(
        lib.xyg_scene_arrays_equal(null_f64, 0, null_f64, 0) == 1,
        "scene_arrays_equal empty",
    )
    equal_left = array("d", [1.0, 2.0])
    equal_right = array("d", [1.0, 2.0])
    ok(
        lib.xyg_scene_arrays_equal(
            _ptr(equal_left, ctypes.c_double), 2, _ptr(equal_right, ctypes.c_double), 2
        )
        == 1,
        "scene_arrays_equal match",
    )
    mismatch = array("d", [1.0])
    ok(
        lib.xyg_scene_arrays_equal(
            _ptr(equal_left, ctypes.c_double), 2, _ptr(mismatch, ctypes.c_double), 1
        )
        == 0,
        "scene_arrays_equal len",
    )
    nan_eq = array("d", [float("nan")])
    ok(
        lib.xyg_scene_arrays_equal(
            _ptr(nan_eq, ctypes.c_double), 1, _ptr(nan_eq, ctypes.c_double), 1
        )
        == 0,
        "scene_arrays_equal nan",
    )
    ok(
        lib.xyg_scene_constant_color_admit(0, 0, 0, 0) == 1,
        "scene_constant_color_admit fallback",
    )
    ok(
        lib.xyg_scene_constant_color_admit(1, 1, 0, 0) == 2,
        "scene_constant_color_admit constant",
    )
    ok(
        lib.xyg_scene_constant_color_admit(1, 0, 0, 0) == 0,
        "scene_constant_color_admit fail",
    )
    ok(
        lib.xyg_scene_hidden_or_per_item_admit(0, 0, 0) == 0,
        "scene_hidden_or_per_item_admit none",
    )
    ok(
        lib.xyg_scene_hidden_or_per_item_admit(0, 1, 1) == 0,
        "scene_hidden_or_per_item_admit density",
    )
    ok(
        lib.xyg_scene_hidden_or_per_item_admit(0, 1, 0) == 1,
        "scene_hidden_or_per_item_admit per-item",
    )
    css_mode = array("B", b"constant")
    css_red = array("B", b"red")
    css_out = array("B", [0] * 8)
    ok(
        lib.xyg_scene_channel_constant_css(
            _ptr(css_mode, ctypes.c_uint8),
            len(css_mode),
            1,
            _ptr(css_red, ctypes.c_uint8),
            len(css_red),
            _ptr(css_out, ctypes.c_uint8),
            len(css_out),
        )
        == 3
        and bytes(css_out[:3]) == b"red",
        "scene_channel_constant_css constant",
    )
    ok(
        lib.xyg_scene_channel_constant_css(
            _ptr(css_mode, ctypes.c_uint8),
            len(css_mode),
            0,
            _ptr(css_red, ctypes.c_uint8),
            len(css_red),
            _ptr(css_out, ctypes.c_uint8),
            len(css_out),
        )
        == -1,
        "scene_channel_constant_css missing",
    )
    css_direct = array("B", b"direct_rgba")
    ok(
        lib.xyg_scene_channel_constant_css(
            _ptr(css_direct, ctypes.c_uint8),
            len(css_direct),
            1,
            _ptr(css_red, ctypes.c_uint8),
            len(css_red),
            _ptr(css_out, ctypes.c_uint8),
            len(css_out),
        )
        == -1,
        "scene_channel_constant_css mode",
    )
    ok(
        lib.xyg_clip_quantize_u8(null_f64, 0, null_u8, 0) == 1,
        "clip_quantize_u8 empty",
    )
    quant_in = array("d", [0.0, 0.5, 1.0, 1.5])
    quant_out = array("B", [0] * 4)
    ok(
        lib.xyg_clip_quantize_u8(
            _ptr(quant_in, ctypes.c_double), 4, _ptr(quant_out, ctypes.c_uint8), 4
        )
        == 1
        and list(quant_out) == [0, 128, 255, 255],
        "clip_quantize_u8 table",
    )
    nan_q = array("d", [float("nan")])
    nan_out = array("B", [255])
    ok(
        lib.xyg_clip_quantize_u8(_ptr(nan_q, ctypes.c_double), 1, _ptr(nan_out, ctypes.c_uint8), 1)
        == 1
        and nan_out[0] == 0,
        "clip_quantize_u8 nan",
    )
    unit_in = array("d", [0.0, 5.0, 10.0])
    unit_out = array("B", [0] * 3)
    ok(
        lib.xyg_quantize_unit_u8(
            _ptr(unit_in, ctypes.c_double),
            len(unit_in),
            0.0,
            10.0,
            _ptr(unit_out, ctypes.c_uint8),
        )
        == 1
        and list(unit_out) == [0, 128, 255],
        "quantize_unit_u8 basic",
    )
    ok(
        lib.xyg_quantize_unit_u8(null_f64, 0, 0.0, 1.0, null_u8) == 1,
        "quantize_unit_u8 empty",
    )
    bad_domain_out = array("B", [99])
    ok(
        lib.xyg_quantize_unit_u8(
            _ptr(array("d", [1.0]), ctypes.c_double),
            1,
            5.0,
            5.0,
            _ptr(bad_domain_out, ctypes.c_uint8),
        )
        == 1
        and list(bad_domain_out) == [0],
        "quantize_unit_u8 bad domain",
    )
    arrow_style = array("d", [float("nan")] * 12)
    arrow_style[7] = 2.8
    arrow_style[8] = 90.0
    arrow_style[9] = 2.8
    arrow_style[10] = 17.0
    arrow_out = array("d", [0.0] * 11)
    ok(
        lib.xyg_arrow_geometry(
            0.0,
            0.0,
            300.0,
            0.0,
            _ptr(arrow_style, ctypes.c_double),
            12,
            _ptr(arrow_out, ctypes.c_double),
            11,
        )
        == 1
        and abs(arrow_out[0] - 90.0) < 1e-12,
        "arrow_geometry label_clear",
    )
    ok(
        lib.xyg_arrow_geometry(
            0.0,
            0.0,
            10.0,
            0.0,
            null_f64,
            0,
            _ptr(arrow_out, ctypes.c_double),
            11,
        )
        == 1
        and arrow_out[0] == 0.0
        and arrow_out[2] == 10.0,
        "arrow_geometry empty style",
    )
    ok(
        lib.xyg_arrow_shaft_points(
            0.0,
            0.0,
            10.0,
            0.0,
            0.0,
            0.0,
            0,
            0,
            0,
            null_f64,
            null_f64,
            0,
        )
        == 2,
        "arrow_shaft linear probe",
    )
    arrow_meta = array("i", [0] * 6)
    head_style = array("B", b"triangle")
    tail_style = array("B", b"none")
    arrow_probe = lib.xyg_arrow_shapes(
        0.0,
        0.0,
        100.0,
        0.0,
        null_f64,
        0,
        _ptr(head_style, ctypes.c_uint8),
        len(head_style),
        _ptr(tail_style, ctypes.c_uint8),
        len(tail_style),
        float("nan"),
        float("nan"),
        float("nan"),
        0,
        _ptr(arrow_meta, ctypes.c_int32),
        6,
        null_f64,
        null_f64,
        0,
    )
    ok(arrow_probe == 5 and arrow_meta[0] == 2 and arrow_meta[3] == 3, "arrow_shapes probe")
    xyta_flags = ctypes.c_uint32(0)
    named = array("B", b"viridis")
    stop_rgb = array("B", [255, 0, 0, 0, 255, 0])
    cmap_out = array("B", [0] * len(named))
    stops_out = array("B", [0] * len(stop_rgb))
    ok(
        lib.xyg_scene_xyta_colormap_pack(
            1,
            _ptr(named, ctypes.c_uint8),
            len(named),
            null_u8,
            0,
            ctypes.byref(xyta_flags),
            _ptr(cmap_out, ctypes.c_uint8),
            len(cmap_out),
            null_u8,
            0,
        )
        == 1
        and xyta_flags.value == (1 << 6)
        and bytes(cmap_out) == b"viridis",
        "scene_xyta_colormap_pack named",
    )
    xyta_flags = ctypes.c_uint32(0)
    ok(
        lib.xyg_scene_xyta_colormap_pack(
            2,
            null_u8,
            0,
            _ptr(stop_rgb, ctypes.c_uint8),
            len(stop_rgb),
            ctypes.byref(xyta_flags),
            null_u8,
            0,
            _ptr(stops_out, ctypes.c_uint8),
            len(stops_out),
        )
        == 1
        and xyta_flags.value == (1 << 7)
        and bytes(stops_out) == bytes(stop_rgb),
        "scene_xyta_colormap_pack stops",
    )
    xyhf_flags = ctypes.c_uint32(0)
    xyhf_stops_out = array("B", [0] * len(stop_rgb))
    ok(
        lib.xyg_scene_xyhf_colormap_pack(
            2,
            null_u8,
            0,
            _ptr(stop_rgb, ctypes.c_uint8),
            len(stop_rgb),
            ctypes.byref(xyhf_flags),
            null_u8,
            0,
            _ptr(xyhf_stops_out, ctypes.c_uint8),
            len(xyhf_stops_out),
        )
        == 1
        and xyhf_flags.value == (1 << 6)
        and bytes(xyhf_stops_out) == bytes(stop_rgb),
        "scene_xyhf_colormap_pack stops",
    )
    grad_space = array("B", b"mark")
    grad_dir = array("B", b"right")
    grad_t = array("d", [0.0, 1.0])
    grad_css = array("B", b"#7c3aed#34d399")
    grad_lens = array("I", [7, 7])
    grad_out = array("B", [0] * 64)
    grad_n = lib.xyg_scene_gradient_spec_pack(
        _ptr(grad_space, ctypes.c_uint8),
        len(grad_space),
        _ptr(grad_dir, ctypes.c_uint8),
        len(grad_dir),
        _ptr(grad_t, ctypes.c_double),
        len(grad_t),
        _ptr(grad_css, ctypes.c_uint8),
        len(grad_css),
        _ptr(grad_lens, ctypes.c_uint32),
        len(grad_lens),
        _ptr(grad_out, ctypes.c_uint8),
        len(grad_out),
    )
    ok(
        grad_n == 4 + 2 * 10 + 14 and bytes(grad_out[:4]) == bytes([0, 2, 2, 0]),
        "scene_gradient_spec_pack mark-right",
    )
    marker_vals = array("d", [0.0, 0.5, 0.5, 0.0, 0.0, -0.5, -0.5, 0.0, 0.0, 0.5])
    marker_lens = array("I", [10])
    marker_out = array("B", [0] * 128)
    marker_n = lib.xyg_scene_marker_blob_pack(
        1,
        _ptr(marker_vals, ctypes.c_double),
        len(marker_vals),
        _ptr(marker_lens, ctypes.c_uint32),
        len(marker_lens),
        _ptr(marker_out, ctypes.c_uint8),
        len(marker_out),
    )
    ok(
        marker_n == 92 and bytes(marker_out[:8]) == bytes([1, 0, 0, 0, 1, 0, 0, 0]),
        "scene_marker_blob_pack diamond",
    )
    xytc_dash_flags = ctypes.c_uint32(0)
    ok(
        lib.xyg_scene_xytc_dash_pattern_pack(1, ctypes.byref(xytc_dash_flags)) == 1
        and xytc_dash_flags.value == (1 << 17),
        "scene_xytc_dash_pattern_pack array",
    )
    xytc_paint_flags = ctypes.c_uint32(0)
    ok(
        lib.xyg_scene_xytc_paint_presence_pack(
            1,
            2,
            1,
            1,
            ctypes.byref(xytc_paint_flags),
        )
        == 1
        and xytc_paint_flags.value == ((1 << 0) | (1 << 1) | (1 << 2) | (1 << 19)),
        "scene_xytc_paint_presence_pack gradient+stroke+line",
    )
    xytc_meta_flags = ctypes.c_uint32(0)
    scatter_kind = array("B", b"scatter")
    ok(
        lib.xyg_scene_xytc_meta_flags_pack(
            1,
            1,
            _ptr(scatter_kind, ctypes.c_uint8),
            len(scatter_kind),
            1,
            0,
            0,
            0,
            0,
            ctypes.byref(xytc_meta_flags),
        )
        == 1
        and xytc_meta_flags.value == ((1 << 16) | (1 << 15) | (1 << 14)),
        "scene_xytc_meta_flags_pack scatter density",
    )
    xytc_color2_flags = ctypes.c_uint32(0)
    ok(
        lib.xyg_scene_xytc_color2_flags_pack(2, 0, 1, ctypes.byref(xytc_color2_flags)) == 1
        and xytc_color2_flags.value == ((1 << 0) | (1 << 19)),
        "scene_xytc_color2_flags_pack gradient inject",
    )
    xytc_symbol_flags = ctypes.c_uint32(0)
    ok(
        lib.xyg_scene_xytc_symbol_int_pack(1, ctypes.byref(xytc_symbol_flags)) == 1
        and xytc_symbol_flags.value == (1 << 21),
        "scene_xytc_symbol_int_pack numeric",
    )
    xytc_fill = ctypes.c_double(0.0)
    xytc_stroke = ctypes.c_double(0.0)
    xytc_line = ctypes.c_double(0.0)
    ok(
        lib.xyg_scene_xytc_opacity_pack(
            1,
            1,
            0.5,
            0.6,
            0.7,
            ctypes.byref(xytc_fill),
            ctypes.byref(xytc_stroke),
            ctypes.byref(xytc_line),
        )
        == 1
        and xytc_fill.value == 0.5
        and xytc_stroke.value == 0.6
        and xytc_line.value == 0.7,
        "scene_xytc_opacity_pack band+opacity",
    )
    xytc_hex_flags = ctypes.c_uint32(0)
    xytc_hex_dx = ctypes.c_double(0.0)
    xytc_hex_dy = ctypes.c_double(0.0)
    ok(
        lib.xyg_scene_xytc_hex_pitch_pack(
            1,
            1,
            1,
            1.0,
            2.0,
            ctypes.byref(xytc_hex_flags),
            ctypes.byref(xytc_hex_dx),
            ctypes.byref(xytc_hex_dy),
        )
        == 1
        and xytc_hex_flags.value == (1 << 8)
        and xytc_hex_dx.value == 1.0
        and xytc_hex_dy.value == 2.0,
        "scene_xytc_hex_pitch_pack hexbin",
    )
    xytc_perimeter_flags = ctypes.c_uint32(0)
    ok(
        lib.xyg_scene_xytc_stroke_perimeter_pack(
            1,
            1,
            1,
            1,
            ctypes.byref(xytc_perimeter_flags),
        )
        == 1
        and xytc_perimeter_flags.value == (1 << 9),
        "scene_xytc_stroke_perimeter_pack true",
    )
    xytc_num_flags = ctypes.c_uint32(0)
    xytc_num_size = ctypes.c_double(0.0)
    xytc_num_size_ch = ctypes.c_double(0.0)
    xytc_num_stroke = ctypes.c_double(0.0)
    xytc_num_width = ctypes.c_double(0.0)
    xytc_num_line = ctypes.c_double(0.0)
    ok(
        lib.xyg_scene_xytc_numeric_style_pack(
            1,
            1,
            1,
            1,
            0,
            1,
            4.0,
            2.5,
            1.0,
            0.0,
            3.0,
            ctypes.byref(xytc_num_flags),
            ctypes.byref(xytc_num_size),
            ctypes.byref(xytc_num_size_ch),
            ctypes.byref(xytc_num_stroke),
            ctypes.byref(xytc_num_width),
            ctypes.byref(xytc_num_line),
        )
        == 1
        and xytc_num_flags.value == ((1 << 3) | (1 << 5) | (1 << 6) | (1 << 7))
        and xytc_num_size.value == 4.0
        and xytc_num_size_ch.value == 2.5
        and xytc_num_stroke.value == 1.0
        and xytc_num_line.value == 3.0,
        "scene_xytc_numeric_style_pack scatter-ish",
    )
    xytc_color_flags = ctypes.c_uint32(0)
    ok(
        lib.xyg_scene_xytc_color_channel_pack(
            1,
            1,
            ctypes.byref(xytc_color_flags),
        )
        == 1
        and xytc_color_flags.value == ((1 << 11) | (1 << 12)),
        "scene_xytc_color_channel_pack constant",
    )
    xytc_flags = ctypes.c_uint32(0)
    xytc_tip = ctypes.c_double(0.0)
    xytc_base = ctypes.c_double(0.0)
    xytc_gap = ctypes.c_double(0.0)
    bar_kind = array("B", b"bar")
    ok(
        lib.xyg_scene_xytc_radius_pack(
            _ptr(bar_kind, ctypes.c_uint8),
            len(bar_kind),
            2,
            1.0,
            2.0,
            0.5,
            ctypes.byref(xytc_flags),
            ctypes.byref(xytc_tip),
            ctypes.byref(xytc_base),
            ctypes.byref(xytc_gap),
        )
        == 1
        and xytc_flags.value == ((1 << 22) | (1 << 23))
        and xytc_tip.value == 1.0
        and xytc_base.value == 2.0
        and xytc_gap.value == 0.5,
        "scene_xytc_radius_pack bar",
    )
    scale = ctypes.c_double()
    ok(
        lib.xyg_f32_safe_scale(0.0, -1.0, 1.0, ctypes.byref(scale)) == 1 and scale.value == 1.0,
        "f32_safe_scale normal",
    )
    ok(lib.xyg_f32_safe_scale(0.0, -1.0, 1.0, null_f64) == 0, "f32_safe_scale null out")
    ok(lib.xyg_encode_f32(null_f64, 0, 0.0, 1.0, null_f32) == 1, "encode_f32 empty/null ok status")
    tiny_f = array("f", [123.0])
    status = lib.xyg_encode_f32(null_f64, 1, 0.0, 1.0, _ptr(tiny_f, ctypes.c_float))
    ok(
        status == 0 and tiny_f[0] == 123.0,
        "encode_f32 rejects null input with 0 status, without writing",
    )
    ok(
        lib.xyg_m4_indices(null_f64, null_f64, 0, 0.0, 1.0, 4, null_u32) == 0,
        "m4 empty/null returns zero",
    )
    ok(
        lib.xyg_m4_indices(null_f64, null_f64, 1, 0.0, 1.0, 4, null_u32) == size_max,
        "m4 non-empty/null sentinel",
    )
    ok(
        lib.xyg_zone_maps(
            null_f64,
            0,
            65_536,
            null_f64,
            null_f64,
            null_u64,
            null_u64,
            null_f64,
            null_f64,
            null_f64,
            null_f64,
        )
        == 0,
        "zone_maps empty/null returns zero",
    )
    ok(
        lib.xyg_zone_maps(
            null_f64,
            1,
            65_536,
            null_f64,
            null_f64,
            null_u64,
            null_u64,
            null_f64,
            null_f64,
            null_f64,
            null_f64,
        )
        == size_max,
        "zone_maps non-empty/null sentinel",
    )
    ok(
        lib.xyg_min_max(
            null_f64, 0, ctypes.byref(ctypes.c_double()), ctypes.byref(ctypes.c_double())
        )
        == 0,
        "min_max empty/null returns zero",
    )
    ok(lib.xyg_is_sorted(null_f64, 0) == 1, "is_sorted empty is sorted")
    ok(lib.xyg_is_sorted(null_f64, 2) == 0, "is_sorted null non-empty returns unsorted")
    sorted_pair = array("d", [1.0, 2.0])
    unsorted_pair = array("d", [2.0, 1.0])
    nan_pair = array("d", [1.0, float("nan")])
    ok(lib.xyg_is_sorted(_ptr(sorted_pair, ctypes.c_double), 2) == 1, "is_sorted sorted pair")
    ok(lib.xyg_is_sorted(_ptr(unsorted_pair, ctypes.c_double), 2) == 0, "is_sorted unsorted pair")
    ok(lib.xyg_is_sorted(_ptr(nan_pair, ctypes.c_double), 2) == 0, "is_sorted NaN poisons")
    empty_grid = array("f", [99.0]) * 4
    ok(
        lib.xyg_bin_2d(
            null_f64, null_f64, 0, 0.0, 1.0, 0.0, 1.0, 2, 2, _ptr(empty_grid, ctypes.c_float)
        )
        == 1
        and list(empty_grid) == [0.0, 0.0, 0.0, 0.0],
        "bin_2d empty/null zeroes grid",
    )
    ok(
        lib.xyg_bin_2d(
            null_f64, null_f64, 1, 0.0, 1.0, 0.0, 1.0, 2, 2, _ptr(empty_grid, ctypes.c_float)
        )
        == 0,
        "bin_2d non-empty/null error flag",
    )
    empty_hist = array("d", [99.0]) * 4
    ok(
        lib.xyg_histogram_uniform(null_f64, 0, 0.0, 1.0, 4, 0, _ptr(empty_hist, ctypes.c_double))
        == 0
        and list(empty_hist) == [0.0, 0.0, 0.0, 0.0],
        "histogram empty/null zeroes counts",
    )
    ok(
        lib.xyg_histogram_uniform(null_f64, 1, 0.0, 1.0, 4, 0, _ptr(empty_hist, ctypes.c_double))
        == size_max,
        "histogram non-empty/null sentinel",
    )
    ok(
        lib.xyg_normalize_f32(null_f64, 0, 0.0, 1.0, 0, null_f32) == 1,
        "normalize_f32 empty/null ok status",
    )
    tiny_norm = array("f", [123.0])
    status = lib.xyg_normalize_f32(null_f64, 1, 0.0, 1.0, 0, _ptr(tiny_norm, ctypes.c_float))
    ok(
        status == 0 and tiny_norm[0] == 123.0,
        "normalize_f32 rejects null input with 0 status, without writing",
    )
    one_val = array("d", [0.5])
    status = lib.xyg_normalize_f32(
        _ptr(one_val, ctypes.c_double), 1, 1.0, 0.0, 0, _ptr(tiny_norm, ctypes.c_float)
    )
    ok(
        status == 0 and tiny_norm[0] == 123.0,
        "normalize_f32 inverted domain now signals 0 (was a silent void)",
    )
    ok(
        lib.xyg_range_indices(null_f64, null_f64, 0, 0.0, 1.0, 0.0, 1.0, null_u32) == 0,
        "range_indices empty/null returns zero",
    )
    ok(
        lib.xyg_range_indices(null_f64, null_f64, 1, 0.0, 1.0, 0.0, 1.0, null_u32) == size_max,
        "range_indices non-empty/null sentinel",
    )
    # bin_2d_indices: fused grid + visible-row scan. A point exactly on the
    # inclusive hi edge appears in the index list (range_indices semantics)
    # but not in any grid cell (bin_2d's half-open semantics).
    bx = array("d", [0.25, 1.0])
    by = array("d", [0.25, 0.5])
    bgrid = array("f", [9.0]) * 4
    bidx = array("I", [7, 7])
    written = lib.xyg_bin_2d_indices(
        _ptr(bx, ctypes.c_double),
        _ptr(by, ctypes.c_double),
        2,
        0.0,
        1.0,
        0.0,
        1.0,
        2,
        2,
        _ptr(bgrid, ctypes.c_float),
        _ptr(bidx, ctypes.c_uint32),
    )
    ok(written == 2 and list(bidx) == [0, 1], "bin_2d_indices inclusive index list")
    ok(sum(bgrid) == 1.0, "bin_2d_indices half-open grid excludes hi edge")
    ok(
        lib.xyg_bin_2d_indices(
            null_f64, null_f64, 0, 0.0, 1.0, 0.0, 1.0, 2, 2, _ptr(bgrid, ctypes.c_float), null_u32
        )
        == 0
        and sum(bgrid) == 0.0,
        "bin_2d_indices empty/null zeroes grid, returns zero",
    )
    ok(
        lib.xyg_bin_2d_indices(
            null_f64, null_f64, 1, 0.0, 1.0, 0.0, 1.0, 2, 2, _ptr(bgrid, ctypes.c_float), null_u32
        )
        == size_max,
        "bin_2d_indices non-empty/null sentinel",
    )
    # Full-view fused grid + implicit-id sample. A zero-capacity query still
    # writes the exact grid and reports the required row count; retrying with
    # that capacity returns the same ascending sample as the standalone ABI.
    sample_grid = array("f", [9.0]) * 4
    required = lib.xyg_bin_2d_sample_range(
        _ptr(bx, ctypes.c_double),
        _ptr(by, ctypes.c_double),
        2,
        0.0,
        1.0,
        0.0,
        1.0,
        2,
        2,
        0,
        ctypes.c_uint64(2**64 - 1),
        _ptr(sample_grid, ctypes.c_float),
        null_u32,
        0,
    )
    ok(required == 2 and sum(sample_grid) == 1.0, "bin_2d_sample_range query")
    sample_rows = array("I", [7, 7])
    repeated = lib.xyg_bin_2d_sample_range(
        _ptr(bx, ctypes.c_double),
        _ptr(by, ctypes.c_double),
        2,
        0.0,
        1.0,
        0.0,
        1.0,
        2,
        2,
        0,
        ctypes.c_uint64(2**64 - 1),
        _ptr(sample_grid, ctypes.c_float),
        _ptr(sample_rows, ctypes.c_uint32),
        2,
    )
    ok(repeated == required and list(sample_rows) == [0, 1], "bin_2d_sample_range retry")
    sample_groups = array("B", [0, 1])
    sample_counts = array("Q", [1, 1])
    categorical_rows = array("I", [7, 7])
    categorical_written = lib.xyg_bin_2d_stratified_sample_range_u8_counted(
        _ptr(bx, ctypes.c_double),
        _ptr(by, ctypes.c_double),
        _ptr(sample_groups, ctypes.c_uint8),
        2,
        _ptr(sample_counts, ctypes.c_uint64),
        2,
        0.0,
        1.0,
        0.0,
        1.0,
        2,
        2,
        0,
        1.0,
        1,
        _ptr(sample_grid, ctypes.c_float),
        _ptr(categorical_rows, ctypes.c_uint32),
        2,
    )
    ok(
        categorical_written == 2 and list(categorical_rows) == [0, 1],
        "bin_2d categorical counted sample",
    )
    valid_columns = (F64P * 2)(
        _ptr(bx, ctypes.c_double),
        _ptr(by, ctypes.c_double),
    )
    ok(
        lib.xyg_valid_indices_f64(valid_columns, 2, 2, 0b11, null_u32, 0) == 2,
        "valid_indices_f64 all-valid query",
    )
    validity_x = array("d", [1.0, float("nan"), -1.0])
    validity_y = array("d", [1.0, 2.0, 3.0])
    filtered_columns = (F64P * 2)(
        _ptr(validity_x, ctypes.c_double),
        _ptr(validity_y, ctypes.c_double),
    )
    filtered_rows = array("I", [7, 7, 7])
    ok(
        lib.xyg_valid_indices_f64(
            filtered_columns,
            2,
            3,
            0b01,
            _ptr(filtered_rows, ctypes.c_uint32),
            3,
        )
        == 1
        and filtered_rows[0] == 0,
        "valid_indices_f64 filtered write",
    )
    # sample_mask: SplitMix64(id + seed) <= threshold, one byte per row.
    ids = array("Q", [0, 1, 2, 3])
    mask = array("B", [9, 9, 9, 9])
    lib.xyg_sample_mask(
        _ptr(ids, ctypes.c_uint64),
        4,
        ctypes.c_uint64(0),
        ctypes.c_uint64(2**64 - 1),
        _ptr(mask, ctypes.c_uint8),
    )
    ok(list(mask) == [1, 1, 1, 1], "sample_mask threshold=max keeps all")
    lib.xyg_sample_mask(
        _ptr(ids, ctypes.c_uint64),
        4,
        ctypes.c_uint64(0),
        ctypes.c_uint64(0),
        _ptr(mask, ctypes.c_uint8),
    )
    ok(list(mask) == [0, 0, 0, 0], "sample_mask threshold=0 keeps none")
    # SplitMix64(0+0) reference value — must match lod.hash_row_ids bit-for-bit.
    lib.xyg_sample_mask(
        _ptr(ids, ctypes.c_uint64),
        1,
        ctypes.c_uint64(0),
        ctypes.c_uint64(0xE220A8397B1DCDAF),
        _ptr(mask, ctypes.c_uint8),
    )
    ok(mask[0] == 1, "sample_mask splitmix64(0) reference vector inclusive")
    lib.xyg_sample_mask(
        _ptr(ids, ctypes.c_uint64),
        1,
        ctypes.c_uint64(0),
        ctypes.c_uint64(0xE220A8397B1DCDAF - 1),
        _ptr(mask, ctypes.c_uint8),
    )
    ok(mask[0] == 0, "sample_mask splitmix64(0) reference vector exclusive")
    mask_null = array("B", [7])
    status = lib.xyg_sample_mask(
        null_u64, 1, ctypes.c_uint64(0), ctypes.c_uint64(1), _ptr(mask_null, ctypes.c_uint8)
    )
    ok(
        status == 0 and mask_null[0] == 7,
        "sample_mask rejects null input with 0 status, without writing",
    )
    ok(
        lib.xyg_sample_mask(
            null_u64, 0, ctypes.c_uint64(0), ctypes.c_uint64(1), ctypes.POINTER(ctypes.c_uint8)()
        )
        == 1,
        "sample_mask empty/null ok status",
    )
    ok(
        lib.xyg_sample_threshold(0.5) == 9_223_372_036_854_775_808,
        "sample_threshold half fraction reference",
    )
    ok(
        lib.xyg_sample_threshold(1.0) == 2**64 - 1,
        "sample_threshold unity keeps all rows",
    )
    hashes = array("Q", [0, 0, 0])
    lib.xyg_hash_row_ids(
        _ptr(ids, ctypes.c_uint64),
        2,
        ctypes.c_uint64(0),
        _ptr(hashes, ctypes.c_uint64),
    )
    ok(
        list(hashes[:2]) == [0xE220A8397B1DCDAF, 0x910A2DEC89025CC1],
        "hash_row_ids splitmix64 reference vectors",
    )
    hashes_null = array("Q", [7])
    status = lib.xyg_hash_row_ids(
        null_u64, 1, ctypes.c_uint64(0), _ptr(hashes_null, ctypes.c_uint64)
    )
    ok(
        status == 0 and hashes_null[0] == 7,
        "hash_row_ids rejects null input with 0 status, without writing",
    )
    ok(
        lib.xyg_hash_row_ids(null_u64, 0, ctypes.c_uint64(0), ctypes.POINTER(ctypes.c_uint64)())
        == 1,
        "hash_row_ids empty/null ok status",
    )
    ok(
        abs(lib.xyg_sample_fraction(2, 0.25, 2.0) - 1.0) < 1e-12,
        "sample_fraction level-2 reference",
    )
    ok(
        abs(lib.xyg_sample_fraction(0, 1.0, 2.0) - 1.0) < 1e-12,
        "sample_fraction saturated base",
    )
    out_w = ctypes.c_int32()
    out_h = ctypes.c_int32()
    ok(
        lib.xyg_screen_shape(640, 360, ctypes.byref(out_w), ctypes.byref(out_h)) == 1,
        "screen_shape default dimensions",
    )
    ok(out_w.value == 640 and out_h.value == 360, "screen_shape default output")
    ok(
        lib.xyg_screen_shape(8, 10, ctypes.byref(out_w), ctypes.byref(out_h)) == 1,
        "screen_shape low clamp",
    )
    ok(out_w.value == 16 and out_h.value == 16, "screen_shape low clamp output")
    norm_out = array("d", [0.0, 0.0, 0.0, 0.0])
    ok(
        lib.xyg_normalize_window(5.0, 1.0, 4.0, 2.0, 1, _ptr(norm_out, ctypes.c_double)) == 1,
        "normalize_window ordered",
    )
    ok(
        tuple(norm_out) == (1.0, 5.0, 2.0, 4.0),
        "normalize_window ordered output",
    )
    ok(
        lib.xyg_normalize_window(1.0, 1.0, 2.0, 3.0, 0, _ptr(norm_out, ctypes.c_double)) == 1,
        "normalize_window degenerate allowed",
    )
    ok(
        lib.xyg_normalize_window(1.0, 1.0, 2.0, 3.0, 1, _ptr(norm_out, ctypes.c_double)) == -1,
        "normalize_window zero area rejected",
    )
    view_x = array("d", [0.0, 1.0, 2.0, float("nan"), 5.0])
    view_y = array("d", [0.0, 1.0, 2.0, 3.0, 5.0])
    view_mask = array("B", [9, 9, 9, 9, 9])
    ok(
        lib.xyg_view_visible_mask(
            _ptr(view_x, ctypes.c_double),
            _ptr(view_y, ctypes.c_double),
            5,
            0.5,
            4.5,
            0.5,
            4.5,
            _ptr(view_mask, ctypes.c_uint8),
        )
        == 5,
        "view_visible_mask row count",
    )
    ok(list(view_mask) == [0, 1, 1, 0, 0], "view_visible_mask values")
    ids32 = array("I", [0, 1, 2, 3])
    mask32 = array("B", [9, 9, 9, 9])
    lib.xyg_sample_mask_u32(
        _ptr(ids32, ctypes.c_uint32),
        1,
        ctypes.c_uint64(0),
        ctypes.c_uint64(0xE220A8397B1DCDAF),
        _ptr(mask32, ctypes.c_uint8),
    )
    ok(mask32[0] == 1, "sample_mask_u32 matches the u64 reference vector")
    lib.xyg_sample_mask_u32(
        _ptr(ids32, ctypes.c_uint32),
        4,
        ctypes.c_uint64(0),
        ctypes.c_uint64(0),
        _ptr(mask32, ctypes.c_uint8),
    )
    ok(list(mask32) == [0, 0, 0, 0], "sample_mask_u32 threshold=0 keeps none")
    sampled = array("I", [999]) * 4
    written = lib.xyg_sample_range_indices(
        4,
        ctypes.c_uint64(0),
        ctypes.c_uint64(2**64 - 1),
        _ptr(sampled, ctypes.c_uint32),
        len(sampled),
    )
    ok(written == 4 and list(sampled) == [0, 1, 2, 3], "sample_range_indices implicit parity")
    ok(
        lib.xyg_sample_range_indices(0, ctypes.c_uint64(0), ctypes.c_uint64(1), null_u32, 0) == 0,
        "sample_range_indices empty/null returns zero",
    )
    # Compact full-domain categorical sampler: implicit ids + u8 groups.
    range_groups = array("B", [0, 0, 0, 1])
    stratified_rows = array("I", [999]) * 4
    written = lib.xyg_stratified_sample_range_u8(
        _ptr(range_groups, ctypes.c_uint8),
        4,
        2,
        ctypes.c_uint64(0),
        ctypes.c_double(1.0),
        ctypes.c_uint64(1),
        _ptr(stratified_rows, ctypes.c_uint32),
        len(stratified_rows),
    )
    ok(
        written == 4 and list(stratified_rows) == [0, 1, 2, 3],
        "stratified_sample_range_u8 implicit parity",
    )
    range_counts = array("Q", [3, 1])
    written = lib.xyg_stratified_sample_range_u8_counted(
        _ptr(range_groups, ctypes.c_uint8),
        4,
        _ptr(range_counts, ctypes.c_uint64),
        2,
        ctypes.c_uint64(0),
        ctypes.c_double(1.0),
        ctypes.c_uint64(1),
        _ptr(stratified_rows, ctypes.c_uint32),
        len(stratified_rows),
    )
    ok(
        written == 4 and list(stratified_rows) == [0, 1, 2, 3],
        "stratified_sample_range_u8_counted parity",
    )
    bad_range_counts = array("Q", [2, 1])
    ok(
        lib.xyg_stratified_sample_range_u8_counted(
            _ptr(range_groups, ctypes.c_uint8),
            4,
            _ptr(bad_range_counts, ctypes.c_uint64),
            2,
            ctypes.c_uint64(0),
            ctypes.c_double(0.5),
            ctypes.c_uint64(1),
            _ptr(stratified_rows, ctypes.c_uint32),
            len(stratified_rows),
        )
        == ctypes.c_size_t(-1).value,
        "stratified_sample_range_u8_counted rejects inconsistent counts",
    )
    too_small = array("I", [777])
    written = lib.xyg_stratified_sample_range_u8(
        _ptr(range_groups, ctypes.c_uint8),
        4,
        2,
        ctypes.c_uint64(0),
        ctypes.c_double(1.0),
        ctypes.c_uint64(1),
        _ptr(too_small, ctypes.c_uint32),
        1,
    )
    ok(
        written == 4 and too_small[0] == 777,
        "stratified_sample_range_u8 reports capacity without partial write",
    )
    bad_range_groups = array("B", [0, 2])
    ok(
        lib.xyg_stratified_sample_range_u8(
            _ptr(bad_range_groups, ctypes.c_uint8),
            2,
            2,
            ctypes.c_uint64(0),
            ctypes.c_double(0.5),
            ctypes.c_uint64(1),
            _ptr(stratified_rows, ctypes.c_uint32),
            len(stratified_rows),
        )
        == ctypes.c_size_t(-1).value,
        "stratified_sample_range_u8 rejects out-of-range group codes",
    )
    ok(
        lib.xyg_stratified_sample_range_u8(
            ctypes.POINTER(ctypes.c_uint8)(),
            0,
            1,
            ctypes.c_uint64(0),
            ctypes.c_double(0.5),
            ctypes.c_uint64(1),
            null_u32,
            0,
        )
        == 0,
        "stratified_sample_range_u8 empty/null returns zero",
    )
    # stratified_sample_mask: per-category thresholds + lowest-hash floor.
    sgroups = array("I", [0, 0, 0, 1])
    smask = array("B", [9, 9, 9, 9])
    status = lib.xyg_stratified_sample_mask(
        _ptr(ids, ctypes.c_uint64),
        _ptr(sgroups, ctypes.c_uint32),
        4,
        2,
        ctypes.c_uint64(0),
        ctypes.c_double(1.0),
        ctypes.c_uint64(1),
        _ptr(smask, ctypes.c_uint8),
    )
    ok(
        status == 1 and list(smask) == [1, 1, 1, 1],
        "stratified_sample_mask fraction=1 keeps all",
    )
    status = lib.xyg_stratified_sample_mask(
        _ptr(ids, ctypes.c_uint64),
        _ptr(sgroups, ctypes.c_uint32),
        4,
        2,
        ctypes.c_uint64(0),
        ctypes.c_double(1e-18),
        ctypes.c_uint64(1),
        _ptr(smask, ctypes.c_uint8),
    )
    ok(
        status == 1 and sum(smask) == 2 and smask[3] == 1,
        "stratified_sample_mask floor pins one row per category",
    )
    smask32 = array("B", [9, 9, 9, 9])
    status = lib.xyg_stratified_sample_mask_u32(
        _ptr(ids32, ctypes.c_uint32),
        _ptr(sgroups, ctypes.c_uint32),
        4,
        2,
        ctypes.c_uint64(0),
        ctypes.c_double(1e-18),
        ctypes.c_uint64(1),
        _ptr(smask32, ctypes.c_uint8),
    )
    ok(
        status == 1 and list(smask32) == list(smask),
        "stratified_sample_mask_u32 matches u64 ids",
    )
    smask_bad = array("B", [7, 7, 7, 7])
    bad_groups = array("I", [0, 0, 0, 5])  # 5 >= n_groups
    ok(
        lib.xyg_stratified_sample_mask(
            _ptr(ids, ctypes.c_uint64),
            _ptr(bad_groups, ctypes.c_uint32),
            4,
            2,
            ctypes.c_uint64(0),
            ctypes.c_double(0.5),
            ctypes.c_uint64(1),
            _ptr(smask_bad, ctypes.c_uint8),
        )
        == 0,
        "stratified_sample_mask rejects out-of-range group codes",
    )
    ok(
        lib.xyg_stratified_sample_mask(
            null_u64,
            _ptr(sgroups, ctypes.c_uint32),
            4,
            2,
            ctypes.c_uint64(0),
            ctypes.c_double(0.5),
            ctypes.c_uint64(1),
            _ptr(smask_bad, ctypes.c_uint8),
        )
        == 0,
        "stratified_sample_mask rejects null ids with 0 status",
    )
    ok(
        lib.xyg_stratified_sample_mask(
            null_u64,
            null_u32,
            0,
            1,
            ctypes.c_uint64(0),
            ctypes.c_double(0.5),
            ctypes.c_uint64(1),
            ctypes.POINTER(ctypes.c_uint8)(),
        )
        == 1,
        "stratified_sample_mask empty/null ok status",
    )
    ok(
        lib.xyg_local_log_density(null_f64, null_f64, 0, 0.0, 1.0, 0.0, 1.0, 2, 2, null_f32) == 1,
        "local_log_density empty/null ok",
    )
    ok(
        lib.xyg_local_log_density(
            null_f64,
            null_f64,
            1,
            0.0,
            1.0,
            0.0,
            1.0,
            2,
            2,
            _ptr(tiny_norm, ctypes.c_float),
        )
        == 0,
        "local_log_density non-empty/null error flag",
    )

    # encode_f32: the §16 precision claim, verified through the real ABI.
    t0 = 1.6e12
    x = array("d", [t0 + i for i in range(1000)])
    offset = t0 + 500.0
    out = array("f", [0.0]) * len(x)
    lib.xyg_encode_f32(_ptr(x, ctypes.c_double), len(x), offset, 1.0, _ptr(out, ctypes.c_float))
    worst = max(abs((out[i] + offset) - x[i]) for i in range(len(x)))
    ok(worst < 1e-3, f"offset-encoded precision worst={worst}")

    # Control: naive f32 (offset 0) is visibly wrong.
    naive = array("f", [0.0]) * len(x)
    lib.xyg_encode_f32(_ptr(x, ctypes.c_double), len(x), 0.0, 1.0, _ptr(naive, ctypes.c_float))
    ok(max(abs(naive[i] - x[i]) for i in range(len(x))) > 1.0, "naive f32 corrupts")

    # m4_indices: spike preservation + first/last, through the ABI.
    n = 10_000
    xs = array("d", [float(i) for i in range(n)])
    ys = array("d", [math.sin(i * 0.01) for i in range(n)])
    ys[5432] = 100.0
    ys[7891] = -100.0
    buckets = 100
    idx_buf = array("I", [0]) * (buckets * 4)
    written = lib.xyg_m4_indices(
        _ptr(xs, ctypes.c_double),
        _ptr(ys, ctypes.c_double),
        n,
        0.0,
        float(n),
        buckets,
        _ptr(idx_buf, ctypes.c_uint32),
    )
    idx = set(idx_buf[:written])
    ok(5432 in idx and 7891 in idx, "m4 preserves spikes")
    ok(0 in idx and (n - 1) in idx, "m4 keeps first/last")
    ok(written <= buckets * 4, "m4 bounded output")

    # m4 invalid-arg sentinel (usize::MAX).
    bad = lib.xyg_m4_indices(
        _ptr(xs, ctypes.c_double),
        _ptr(ys, ctypes.c_double),
        n,
        5.0,
        5.0,
        buckets,
        _ptr(idx_buf, ctypes.c_uint32),
    )
    ok(bad == (2**64 - 1), "m4 invalid-arg sentinel")

    # zone_maps: stats + NaN-as-null, through the ABI.
    data = array("d", [float(i) for i in range(10)])
    data[3] = float("nan")
    nchunks = 1
    zm = [array("d", [0.0]) * nchunks for _ in range(6)]  # min,max,sum,sumsq,+positive min/max
    cnt = array("Q", [0]) * nchunks
    nul = array("Q", [0]) * nchunks
    wrote = lib.xyg_zone_maps(
        _ptr(data, ctypes.c_double),
        len(data),
        65536,
        _ptr(zm[0], ctypes.c_double),
        _ptr(zm[1], ctypes.c_double),
        _ptr(cnt, ctypes.c_uint64),
        _ptr(nul, ctypes.c_uint64),
        _ptr(zm[2], ctypes.c_double),
        _ptr(zm[3], ctypes.c_double),
        _ptr(zm[4], ctypes.c_double),
        _ptr(zm[5], ctypes.c_double),
    )
    ok(wrote == 1, "zone_maps chunk count")
    ok(cnt[0] == 9 and nul[0] == 1, "zone_maps counts NaN as null")
    ok(zm[0][0] == 0.0 and zm[1][0] == 9.0, "zone_maps min/max skip NaN")
    ok(zm[4][0] == 1.0 and zm[5][0] == 9.0, "zone_maps positive min/max")
    pair_y = array("d", [float(9 - i) for i in range(10)])
    pair_x_out = (CZoneMap * 1)()
    pair_y_out = (CZoneMap * 1)()
    wrote = lib.xyg_zone_maps_pair(
        _ptr(data, ctypes.c_double),
        _ptr(pair_y, ctypes.c_double),
        10,
        65536,
        pair_x_out,
        pair_y_out,
    )
    ok(wrote == 1, "zone_maps_pair chunk count")
    ok(
        pair_x_out[0].min == 0.0
        and pair_x_out[0].max == 9.0
        and pair_x_out[0].count == 9
        and pair_x_out[0].null_count == 1,
        "zone_maps_pair x parity",
    )
    ok(
        pair_y_out[0].min == 0.0 and pair_y_out[0].max == 9.0 and pair_y_out[0].count == 10,
        "zone_maps_pair y statistics",
    )

    # inf must be treated as null too (§19 hardening): min/max stay finite.
    idata = array("d", [1.0, float("inf"), float("-inf"), 3.0])
    izm = [array("d", [0.0]) for _ in range(6)]
    icnt = array("Q", [0])
    inul = array("Q", [0])
    lib.xyg_zone_maps(
        _ptr(idata, ctypes.c_double),
        4,
        65536,
        _ptr(izm[0], ctypes.c_double),
        _ptr(izm[1], ctypes.c_double),
        _ptr(icnt, ctypes.c_uint64),
        _ptr(inul, ctypes.c_uint64),
        _ptr(izm[2], ctypes.c_double),
        _ptr(izm[3], ctypes.c_double),
        _ptr(izm[4], ctypes.c_double),
        _ptr(izm[5], ctypes.c_double),
    )
    ok(icnt[0] == 2 and inul[0] == 2, "zone_maps counts inf as null")
    ok(izm[0][0] == 1.0 and izm[1][0] == 3.0, "zone_maps min/max skip inf")
    ok(izm[4][0] == 1.0 and izm[5][0] == 3.0, "zone_maps positive skip inf")

    # min_max sentinel path.
    lo = ctypes.c_double()
    hi = ctypes.c_double()
    got = lib.xyg_min_max(
        _ptr(data, ctypes.c_double), len(data), ctypes.byref(lo), ctypes.byref(hi)
    )
    ok(got == 1 and lo.value == 0.0 and hi.value == 9.0, "min_max ok")
    allnan = array("d", [float("nan")])
    ok(
        lib.xyg_min_max(_ptr(allnan, ctypes.c_double), 1, ctypes.byref(lo), ctypes.byref(hi)) == 0,
        "min_max all-NaN returns 0",
    )
    dlo = ctypes.c_double()
    dhi = ctypes.c_double()
    ok(
        lib.xyg_continuous_domain(
            _ptr(data, ctypes.c_double),
            len(data),
            ctypes.byref(dlo),
            ctypes.byref(dhi),
        )
        == 0
        and dlo.value == 0.0
        and dhi.value == 9.0,
        "continuous domain span",
    )
    equal = array("d", [0.0, 0.0])
    ok(
        lib.xyg_continuous_domain(
            _ptr(equal, ctypes.c_double),
            2,
            ctypes.byref(dlo),
            ctypes.byref(dhi),
        )
        == 0
        and abs(dlo.value + 0.5) < 1e-15
        and abs(dhi.value - 0.5) < 1e-15,
        "continuous domain zero pad",
    )
    hex_css = array("B", b"#ff0000")
    ok(
        lib.xyg_css_is_functional(_ptr(hex_css, ctypes.c_uint8), len(hex_css)) == 1,
        "css is functional hex",
    )
    named = array("B", b"red")
    ok(
        lib.xyg_css_is_functional(_ptr(named, ctypes.c_uint8), len(named)) == 0,
        "css named is category",
    )
    rgb = array("d", [0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    rgb_n = lib.xyg_direct_rgba_admit(
        _ptr(rgb, ctypes.c_double),
        2,
        3,
        null_f64,
        0,
    )
    rgb_out = array("d", [0.0]) * 8
    rgb_filled = lib.xyg_direct_rgba_admit(
        _ptr(rgb, ctypes.c_double),
        2,
        3,
        _ptr(rgb_out, ctypes.c_double),
        8,
    )
    ok(
        rgb_n == 8
        and rgb_filled == 8
        and abs(rgb_out[3] - 1.0) < 1e-15
        and abs(rgb_out[4] - 0.4) < 1e-15,
        "direct rgba admit rgb",
    )

    # bin_2d: 4 points, one per quadrant of a 2×2 grid; count conserved, row0 bottom.
    bx = array("d", [0.25, 0.75, 0.25, 0.75])
    by = array("d", [0.25, 0.25, 0.75, 0.75])
    grid = array("f", [0.0]) * 4
    got = lib.xyg_bin_2d(
        _ptr(bx, ctypes.c_double),
        _ptr(by, ctypes.c_double),
        4,
        0.0,
        1.0,
        0.0,
        1.0,
        2,
        2,
        _ptr(grid, ctypes.c_float),
    )
    ok(got == 1, "bin_2d ok flag")
    ok(list(grid) == [1.0, 1.0, 1.0, 1.0], "bin_2d one per quadrant")
    ok(sum(grid) == 4.0, "bin_2d conserves count")
    # A dense cluster in one cell dominates.
    cx = array("d", [0.1] * 500 + [0.9])
    cy = array("d", [0.1] * 500 + [0.9])
    g2 = array("f", [0.0]) * 4
    lib.xyg_bin_2d(
        _ptr(cx, ctypes.c_double),
        _ptr(cy, ctypes.c_double),
        501,
        0.0,
        1.0,
        0.0,
        1.0,
        2,
        2,
        _ptr(g2, ctypes.c_float),
    )
    ok(g2[0] == 500.0 and g2[3] == 1.0, "bin_2d density hotspot")

    # histogram_uniform: fixed-bin counts, last edge closed.
    hx = array("d", [0.0, 0.2, 0.9, 1.0, 1.1, float("nan"), float("inf")])
    hist = array("d", [0.0]) * 4
    total = lib.xyg_histogram_uniform(
        _ptr(hx, ctypes.c_double),
        len(hx),
        0.0,
        1.0,
        4,
        0,
        _ptr(hist, ctypes.c_double),
    )
    ok(total == 4, "histogram valid total")
    ok(list(hist) == [2.0, 0.0, 0.0, 2.0], "histogram counts")

    # histogram_edges: NumPy auto on 1..10 → 5 bins / 6 edges.
    he_data = array("d", [float(i) for i in range(1, 11)])
    he_out = array("d", [0.0]) * 16
    he_n = lib.xyg_histogram_edges(
        _ptr(he_data, ctypes.c_double),
        len(he_data),
        0.0,
        0.0,
        0,
        0,
        _ptr(he_out, ctypes.c_double),
        len(he_out),
    )
    ok(
        he_n == 6 and abs(he_out[0] - 1.0) < 1e-12 and abs(he_out[5] - 10.0) < 1e-12,
        "histogram_edges auto",
    )

    as_data = array("d", [3.0, 1.0, 2.0])
    as_out = (ctypes.c_uint32 * 3)()
    as_n = lib.xyg_argsort_stable(_ptr(as_data, ctypes.c_double), 3, as_out, 3)
    ok(as_n == 3 and list(as_out) == [1, 2, 0], "argsort_stable")

    hm_out = array("d", [0.0]) * 16
    hm_n = lib.xyg_histogram_mark_edges(
        null_f64,
        0,
        0.0,
        0.0,
        0,
        0,
        0,
        _ptr(hm_out, ctypes.c_double),
        len(hm_out),
    )
    ok(
        hm_n == 11 and abs(hm_out[0]) < 1e-12 and abs(hm_out[10] - 1.0) < 1e-12,
        "histogram_mark_edges empty auto",
    )

    cl_z = array("d", [0.0, 10.0])
    cl_out = array("d", [0.0]) * 8
    cl_n = lib.xyg_contour_levels(
        _ptr(cl_z, ctypes.c_double), 2, 3, _ptr(cl_out, ctypes.c_double), 8
    )
    ok(cl_n == 3 and abs(cl_out[1] - 5.0) < 1e-12, "contour_levels auto")

    lg_x = array("d", [0.0, 0.5, 1.0])
    lg_ox = array("d", [0.0]) * 8
    lg_oy = array("d", [0.0]) * 8
    lg_n = lib.xyg_legend_normalize(
        _ptr(lg_x, ctypes.c_double),
        _ptr(lg_x, ctypes.c_double),
        3,
        0.0,
        1.0,
        0.0,
        1.0,
        0,
        0,
        0,
        0,
        1.0,
        1.0,
        _ptr(lg_ox, ctypes.c_double),
        _ptr(lg_oy, ctypes.c_double),
        8,
    )
    lg_starts = (ctypes.c_size_t * 1)(0)
    lg_lens = (ctypes.c_uint32 * 1)(1)
    lg_loc = lib.xyg_legend_best_loc(
        _ptr(lg_ox, ctypes.c_double),
        _ptr(lg_oy, ctypes.c_double),
        lg_n,
        lg_starts,
        1,
        lg_lens,
        1,
    )
    ok(lg_n == 3 and lg_loc == 1, "legend_normalize/best_loc diagonal")

    rb_ox = array("d", [0.0]) * 9
    rb_oy = array("d", [0.0]) * 9
    rb_n = lib.xyg_ribbon_edge(
        0.0,
        10.0,
        1.0,
        3.0,
        8,
        _ptr(rb_ox, ctypes.c_double),
        _ptr(rb_oy, ctypes.c_double),
        9,
    )
    ok(
        rb_n == 9 and abs(rb_ox[4] - 5.0) < 1e-12 and abs(rb_oy[4] - 2.0) < 1e-12,
        "ribbon_edge midpoint",
    )
    ok(lib.xyg_payload_tier(0, 10_001, 0, -1, 0, 0) == 1, "payload_tier line M4")
    ok(lib.xyg_payload_tier(0, 10_001, 1, -1, 0, 0) == 0, "payload_tier polar direct")
    ok(lib.xyg_payload_tier(1, 200_000, 0, -1, 0, 0) == 0, "payload_tier scatter eq direct")
    ok(lib.xyg_payload_tier(1, 200_001, 0, -1, 0, 0) == 2, "payload_tier scatter density")
    ok(lib.xyg_payload_visible_needed(1, 0, 1, 0, 0, 0, 0) == 1, "payload_visible_needed log")
    px = array("d", [1.0, -2.0, 3.0, 0.0, 5.0])
    py = array("d", [1.0, 2.0, 3.0, 4.0, 5.0])
    pmask = array("B", [0]) * 5
    pn = lib.xyg_payload_visible_mask(
        _ptr(px, ctypes.c_double),
        _ptr(py, ctypes.c_double),
        5,
        1,
        0,
        null_f64,
        0,
        _ptr(pmask, ctypes.c_uint8),
        5,
    )
    ok(pn == 3 and list(pmask) == [1, 0, 1, 0, 1], "payload_visible_mask log x")
    m4x = array("d", [float(i) for i in range(10_001)])
    m4y = array("d", [1.0] * 10_001)
    m4_tier = ctypes.c_int32(-1)
    m4_out = array("I", [0]) * (64 * 4)
    m4_n = lib.xyg_payload_m4_indices(
        10_001,
        1,
        _ptr(m4x, ctypes.c_double),
        _ptr(m4y, ctypes.c_double),
        10_001,
        0.0,
        10_000.0,
        64,
        null_f64,
        0.0,
        0.0,
        ctypes.byref(m4_tier),
        _ptr(m4_out, ctypes.c_uint32),
        64 * 4,
    )
    ok(m4_n == 0 and m4_tier.value == 0, "payload_m4_indices polar direct")
    m4_n = lib.xyg_payload_m4_indices(
        10_001,
        0,
        _ptr(m4x, ctypes.c_double),
        _ptr(m4y, ctypes.c_double),
        10_001,
        0.0,
        10_000.0,
        64,
        null_f64,
        0.0,
        0.0,
        ctypes.byref(m4_tier),
        _ptr(m4_out, ctypes.c_uint32),
        64 * 4,
    )
    ok(
        m4_n > 0 and m4_n != ctypes.c_size_t(-1).value and m4_tier.value == 1,
        "payload_m4_indices cartesian",
    )
    vis_keep = ctypes.c_int32(-1)
    vis_out = array("I", [0]) * 5
    vis_n = lib.xyg_payload_visible_indices(
        _ptr(px, ctypes.c_double),
        _ptr(py, ctypes.c_double),
        5,
        1,
        0,
        null_f64,
        0,
        1,
        0,
        0,
        0,
        ctypes.byref(vis_keep),
        _ptr(vis_out, ctypes.c_uint32),
        5,
    )
    ok(
        vis_keep.value == 0 and vis_n == 3 and list(vis_out[:3]) == [0, 2, 4],
        "payload_visible_indices log x",
    )
    even_keep = ctypes.c_int32(-1)
    even_out = array("I", [0]) * 4
    even_n = lib.xyg_payload_even_indices(
        11, 4, ctypes.byref(even_keep), _ptr(even_out, ctypes.c_uint32), 4
    )
    ok(
        even_keep.value == 0 and even_n == 4 and list(even_out) == [0, 3, 6, 10],
        "payload_even_indices linspace",
    )
    even_all = ctypes.c_int32(-1)
    even_n = lib.xyg_payload_even_indices(
        4, 10, ctypes.byref(even_all), _ptr(even_out, ctypes.c_uint32), 4
    )
    ok(even_all.value == 1 and even_n == 0, "payload_even_indices keep-all")
    ok(
        lib.xyg_payload_segment_budget(100.0) == 1024
        and lib.xyg_payload_segment_budget(257.0) == 1028
        and lib.xyg_payload_segment_budget(float("nan")) == ctypes.c_size_t(-1).value,
        "payload_segment_budget floor and sentinel",
    )
    err_keep = ctypes.c_int32(-1)
    err_out = array("I", [0]) * 12
    err_n = lib.xyg_payload_errorbar_indices(
        33, 11, 4, ctypes.byref(err_keep), _ptr(err_out, ctypes.c_uint32), 12
    )
    ok(
        err_keep.value == 0
        and err_n == 12
        and list(err_out) == [0, 3, 6, 10, 11, 14, 17, 21, 22, 25, 28, 32],
        "payload_errorbar_indices role expand",
    )
    role_lo = array("I", [10, 20])
    role_hi = array("I", [30, 40])
    role_sources = array("I", [0, 1, 0, 1])
    role_roles = array("I", [0, 0, 1, 1])
    role_out_lo = array("I", [0, 0, 0, 0])
    role_out_hi = array("I", [0, 0, 0, 0])
    role_collision = ctypes.c_int32(-1)
    role_n = lib.xyg_payload_errorbar_role_keys(
        2,
        4,
        _ptr(role_lo, ctypes.c_uint32),
        _ptr(role_hi, ctypes.c_uint32),
        _ptr(role_sources, ctypes.c_uint32),
        _ptr(role_roles, ctypes.c_uint32),
        _ptr(role_out_lo, ctypes.c_uint32),
        _ptr(role_out_hi, ctypes.c_uint32),
        ctypes.byref(role_collision),
    )
    ok(
        role_n == 4
        and role_collision.value == 0
        and role_out_lo[2] == (10 ^ 0x9E3779B9)
        and role_out_hi[3] == (40 ^ 0x85EBCA6B),
        "payload_errorbar_role_keys xor mix",
    )
    role_map_sources = (ctypes.c_uint32 * 6)(*([0] * 6))
    role_map_roles = (ctypes.c_uint32 * 6)(*([0] * 6))
    role_map_applicable = ctypes.c_int32(-1)
    ok(
        lib.xyg_payload_errorbar_role_maps(
            6,
            3,
            role_map_sources,
            role_map_roles,
            ctypes.byref(role_map_applicable),
        )
        == 1
        and role_map_applicable.value == 1
        and list(role_map_sources) == [0, 1, 2, 0, 1, 2]
        and list(role_map_roles) == [0, 0, 0, 1, 1, 1],
        "payload_errorbar_role_maps tile repeat",
    )
    bar_widths = array("d", [0.8, 0.8, 0.8])
    bar_value0 = array("d", [0.0, 0.0, 0.0])
    bar_out_width = ctypes.c_double(0.0)
    bar_out_value0 = ctypes.c_double(0.0)
    bar_has_value0 = ctypes.c_int32(-1)
    bar_compact = ctypes.c_int32(-1)
    ok(
        lib.xyg_payload_bar_compact_admit(
            3,
            _ptr(bar_widths, ctypes.c_double),
            3,
            _ptr(bar_value0, ctypes.c_double),
            ctypes.byref(bar_out_width),
            ctypes.byref(bar_out_value0),
            ctypes.byref(bar_has_value0),
            ctypes.byref(bar_compact),
        )
        == 1
        and bar_compact.value == 1
        and abs(bar_out_width.value - 0.8) < 1e-12
        and bar_has_value0.value == 1
        and bar_out_value0.value == 0.0,
        "payload_bar_compact_admit uniform width",
    )
    ok(
        lib.xyg_payload_transition_keys_admit(1, 0, 10, 10, 200_000) == 1,
        "payload_transition_keys_admit snap aggregate",
    )
    ok(
        lib.xyg_payload_transition_keys_admit(1, 1, 10, 10, 200_000) == 0,
        "payload_transition_keys_admit ship",
    )
    ship_color = ctypes.c_int32(-1)
    ship_size = ctypes.c_int32(-1)
    ship_stroke = ctypes.c_int32(-1)
    ship_style = ctypes.c_int32(-1)
    ok(
        lib.xyg_payload_trace_channels_ship_attach(
            0,
            1,
            0,
            1,
            1,
            ctypes.byref(ship_color),
            ctypes.byref(ship_size),
            ctypes.byref(ship_stroke),
            ctypes.byref(ship_style),
        )
        == 1
        and ship_color.value == 1
        and ship_size.value == 1
        and ship_stroke.value == 1
        and ship_style.value == 1,
        "payload_trace_channels_ship_attach scatter always",
    )
    ok(
        lib.xyg_payload_trace_channels_ship_attach(
            0,
            0,
            0,
            1,
            1,
            ctypes.byref(ship_color),
            ctypes.byref(ship_size),
            ctypes.byref(ship_stroke),
            ctypes.byref(ship_style),
        )
        == 1
        and ship_color.value == 1
        and ship_stroke.value == 0
        and ship_style.value == 0,
        "payload_trace_channels_ship_attach hexbin skips trace styles",
    )
    ok(
        lib.xyg_payload_trace_channels_ship_attach(
            1,
            1,
            0,
            1,
            0,
            ctypes.byref(ship_color),
            ctypes.byref(ship_size),
            ctypes.byref(ship_stroke),
            ctypes.byref(ship_style),
        )
        == 1
        and ship_color.value == 0
        and ship_stroke.value == 1
        and ship_style.value == 0,
        "payload_trace_channels_ship_attach geometry if color",
    )
    attach_animation = ctypes.c_int32(-1)
    attempt_keys = ctypes.c_int32(-1)
    filter_keys = ctypes.c_int32(-1)
    ship_keys = ctypes.c_int32(-1)
    animation_fallback = ctypes.c_int32(-1)
    attach_tooltip = ctypes.c_int32(-1)
    filter_tooltip = ctypes.c_int32(-1)
    tooltip_ok = ctypes.c_int32(-1)
    ok(
        lib.xyg_payload_transition_entry_attach(
            1,
            0,
            1,
            0,
            0,
            1,
            10,
            10,
            0,
            0,
            200_000,
            0,
            0,
            0,
            ctypes.byref(attach_animation),
            ctypes.byref(attempt_keys),
            ctypes.byref(filter_keys),
            ctypes.byref(ship_keys),
            ctypes.byref(animation_fallback),
            ctypes.byref(attach_tooltip),
            ctypes.byref(filter_tooltip),
            ctypes.byref(tooltip_ok),
        )
        == 1
        and attach_animation.value == 1
        and attempt_keys.value == 1
        and ship_keys.value == 1
        and animation_fallback.value == 0,
        "payload_transition_entry_attach ship keys",
    )
    ok(
        lib.xyg_payload_transition_entry_attach(
            0,
            0,
            1,
            0,
            1,
            1,
            3,
            5,
            0,
            3,
            200_000,
            1,
            5,
            5,
            ctypes.byref(attach_animation),
            ctypes.byref(attempt_keys),
            ctypes.byref(filter_keys),
            ctypes.byref(ship_keys),
            ctypes.byref(animation_fallback),
            ctypes.byref(attach_tooltip),
            ctypes.byref(filter_tooltip),
            ctypes.byref(tooltip_ok),
        )
        == 1
        and filter_keys.value == 1
        and attach_tooltip.value == 1
        and filter_tooltip.value == 1
        and tooltip_ok.value == 1,
        "payload_transition_entry_attach filter keys and tooltip",
    )
    base_attach_animation = ctypes.c_int32(-1)
    base_n_marks = ctypes.c_size_t(0)
    base_apply_palette = ctypes.c_int32(-1)
    base_x_scale = ctypes.c_int32(-1)
    base_y_scale = ctypes.c_int32(-1)
    ok(
        lib.xyg_payload_base_entry_plan(
            1,
            42,
            1,
            1,
            2,
            ctypes.byref(base_attach_animation),
            ctypes.byref(base_n_marks),
            ctypes.byref(base_apply_palette),
            ctypes.byref(base_x_scale),
            ctypes.byref(base_y_scale),
        )
        == 1
        and base_attach_animation.value == 1
        and base_n_marks.value == 42
        and base_apply_palette.value == 1
        and base_x_scale.value == 1
        and base_y_scale.value == 2,
        "payload_base_entry_plan animation and scales",
    )
    nonxy_tier_direct = ctypes.c_int32(-1)
    nonxy_n_marks = ctypes.c_size_t(0)
    nonxy_apply_palette = ctypes.c_int32(-1)
    nonxy_x_scale = ctypes.c_int32(-1)
    nonxy_y_scale = ctypes.c_int32(-1)
    nonxy_channel_slot = ctypes.c_int32(-1)
    nonxy_include_styles = ctypes.c_int32(-1)
    nonxy_attach_transition = ctypes.c_int32(-1)
    ok(
        lib.xyg_payload_nonxy_emit_plan(
            0,
            7,
            1,
            1,
            0,
            ctypes.byref(nonxy_tier_direct),
            ctypes.byref(nonxy_n_marks),
            ctypes.byref(nonxy_apply_palette),
            ctypes.byref(nonxy_x_scale),
            ctypes.byref(nonxy_y_scale),
            ctypes.byref(nonxy_channel_slot),
            ctypes.byref(nonxy_include_styles),
            ctypes.byref(nonxy_attach_transition),
        )
        == 1
        and nonxy_tier_direct.value == 1
        and nonxy_n_marks.value == 7
        and nonxy_apply_palette.value == 1
        and nonxy_x_scale.value == 1
        and nonxy_y_scale.value == 0
        and nonxy_channel_slot.value == 1
        and nonxy_include_styles.value == 1
        and nonxy_attach_transition.value == 1,
        "payload_nonxy_emit_plan rect skeleton",
    )
    bar_hist_emit_bar = ctypes.c_int32(-1)
    bar_hist_tier_direct = ctypes.c_int32(-1)
    bar_hist_n_marks = ctypes.c_size_t(0)
    bar_hist_apply_palette = ctypes.c_int32(-1)
    bar_hist_x_scale = ctypes.c_int32(-1)
    bar_hist_y_scale = ctypes.c_int32(-1)
    bar_hist_pos_scale = ctypes.c_int32(-1)
    bar_hist_value_scale = ctypes.c_int32(-1)
    bar_hist_value_axis = ctypes.c_int32(-1)
    bar_hist_channel_slot = ctypes.c_int32(-1)
    bar_hist_include_styles = ctypes.c_int32(-1)
    bar_hist_attach_transition = ctypes.c_int32(-1)
    ok(
        lib.xyg_payload_bar_hist_emit_plan(
            0,
            1,
            5,
            1,
            1,
            0,
            0,
            ctypes.byref(bar_hist_emit_bar),
            ctypes.byref(bar_hist_tier_direct),
            ctypes.byref(bar_hist_n_marks),
            ctypes.byref(bar_hist_apply_palette),
            ctypes.byref(bar_hist_x_scale),
            ctypes.byref(bar_hist_y_scale),
            ctypes.byref(bar_hist_pos_scale),
            ctypes.byref(bar_hist_value_scale),
            ctypes.byref(bar_hist_value_axis),
            ctypes.byref(bar_hist_channel_slot),
            ctypes.byref(bar_hist_include_styles),
            ctypes.byref(bar_hist_attach_transition),
        )
        == 1
        and bar_hist_emit_bar.value == 0
        and bar_hist_tier_direct.value == 1
        and bar_hist_n_marks.value == 5
        and bar_hist_apply_palette.value == 1
        and bar_hist_x_scale.value == 1
        and bar_hist_y_scale.value == 0
        and bar_hist_channel_slot.value == 1
        and bar_hist_attach_transition.value == 1,
        "payload_bar_hist_emit_plan histogram skeleton",
    )
    heatmap_path = ctypes.c_int32(-1)
    heatmap_tier_direct = ctypes.c_int32(-1)
    heatmap_n_marks = ctypes.c_size_t(0)
    heatmap_attach_color = ctypes.c_int32(-1)
    heatmap_borrow_canonical = ctypes.c_int32(-1)
    heatmap_attach_encoding = ctypes.c_int32(-1)
    heatmap_use_fallback = ctypes.c_int32(-1)
    ok(
        lib.xyg_payload_heatmap_emit_plan(
            0,
            4,
            5,
            0,
            1,
            ctypes.byref(heatmap_path),
            ctypes.byref(heatmap_tier_direct),
            ctypes.byref(heatmap_n_marks),
            ctypes.byref(heatmap_attach_color),
            ctypes.byref(heatmap_borrow_canonical),
            ctypes.byref(heatmap_attach_encoding),
            ctypes.byref(heatmap_use_fallback),
        )
        == 1
        and heatmap_path.value == 1
        and heatmap_tier_direct.value == 1
        and heatmap_n_marks.value == 20
        and heatmap_attach_color.value == 1
        and heatmap_borrow_canonical.value == 1
        and heatmap_attach_encoding.value == 1
        and heatmap_use_fallback.value == 0,
        "payload_heatmap_emit_plan grid borrow skeleton",
    )
    mesh_tier_direct = ctypes.c_int32(-1)
    mesh_n_marks = ctypes.c_size_t(0)
    mesh_apply_palette = ctypes.c_int32(-1)
    mesh_x_scale = ctypes.c_int32(-1)
    mesh_y_scale = ctypes.c_int32(-1)
    mesh_channel_slot = ctypes.c_int32(-1)
    mesh_include_styles = ctypes.c_int32(-1)
    mesh_attach_transition = ctypes.c_int32(-1)
    mesh_attempt_gather = ctypes.c_int32(-1)
    mesh_gather_color = ctypes.c_int32(-1)
    ok(
        lib.xyg_payload_mesh_emit_plan(
            7,
            1,
            1,
            0,
            1,
            1,
            0,
            ctypes.byref(mesh_tier_direct),
            ctypes.byref(mesh_n_marks),
            ctypes.byref(mesh_apply_palette),
            ctypes.byref(mesh_x_scale),
            ctypes.byref(mesh_y_scale),
            ctypes.byref(mesh_channel_slot),
            ctypes.byref(mesh_include_styles),
            ctypes.byref(mesh_attach_transition),
            ctypes.byref(mesh_attempt_gather),
            ctypes.byref(mesh_gather_color),
        )
        == 1
        and mesh_tier_direct.value == 1
        and mesh_n_marks.value == 7
        and mesh_apply_palette.value == 1
        and mesh_x_scale.value == 1
        and mesh_y_scale.value == 0
        and mesh_channel_slot.value == 1
        and mesh_attach_transition.value == 1
        and mesh_attempt_gather.value == 1
        and mesh_gather_color.value == 1,
        "payload_mesh_emit_plan gather skeleton",
    )
    col_gather = ctypes.c_int32(-1)
    col_gather_color = ctypes.c_int32(-1)
    col_n = ctypes.c_size_t(0)
    col_x_scale = ctypes.c_int32(-1)
    col_y_scale = ctypes.c_int32(-1)
    col_entries = (PayloadColumnShipEntry * 8)()
    ok(
        lib.xyg_payload_column_ship_plan(
            b"ribbon",
            6,
            1,
            2,
            0,  # orientation ignored for ribbon
            ctypes.byref(col_gather),
            ctypes.byref(col_gather_color),
            ctypes.byref(col_n),
            ctypes.byref(col_x_scale),
            ctypes.byref(col_y_scale),
            col_entries,
            8,
        )
        == 1
        and col_gather.value == 3
        and col_n.value == 6
        and col_x_scale.value == 1
        and col_y_scale.value == 2
        and col_entries[4].registry_key == 9
        and col_entries[4].trace_slot == 0
        and col_entries[4].ship_scale == 1,
        "payload_column_ship_plan ribbon registry",
    )
    ok(
        lib.xyg_payload_column_ship_plan(
            b"density_wasm_source",
            19,
            1,
            2,
            0,
            ctypes.byref(col_gather),
            ctypes.byref(col_gather_color),
            ctypes.byref(col_n),
            ctypes.byref(col_x_scale),
            ctypes.byref(col_y_scale),
            col_entries,
            8,
        )
        == 1
        and col_gather.value == 0
        and col_n.value == 2
        and col_entries[0].registry_key == 0
        and col_entries[0].ship_method == 2
        and col_entries[0].gather == 0
        and col_entries[1].ship_method == 2,
        "payload_column_ship_plan density_wasm_source f64",
    )
    ok(
        lib.xyg_payload_column_ship_plan(
            b"density_sample",
            14,
            0,
            1,
            0,
            ctypes.byref(col_gather),
            ctypes.byref(col_gather_color),
            ctypes.byref(col_n),
            ctypes.byref(col_x_scale),
            ctypes.byref(col_y_scale),
            col_entries,
            8,
        )
        == 1
        and col_gather.value == 0
        and col_n.value == 2
        and col_entries[0].ship_method == 1
        and col_entries[0].gather == 0,
        "payload_column_ship_plan density_sample values",
    )
    grid_n_buf = ctypes.c_size_t(0)
    grid_n_attach = ctypes.c_size_t(0)
    grid_bufs = (PayloadDensityGridBufferEntry * 2)()
    grid_attach = (PayloadDensityGridAttachEntry * 10)()
    ok(
        lib.xyg_payload_density_grid_ship_plan(
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            ctypes.byref(grid_n_buf),
            grid_bufs,
            2,
            ctypes.byref(grid_n_attach),
            grid_attach,
            10,
        )
        == 1
        and grid_n_buf.value == 1
        and grid_bufs[0].registry_key == 0
        and grid_bufs[0].buffer_slot == 0
        and grid_bufs[0].ship_method == 0
        and grid_n_attach.value == 2
        and grid_attach[0].attach_kind == 3
        and grid_attach[1].attach_kind == 4,
        "payload_density_grid_ship_plan count-only registry",
    )
    ok(
        lib.xyg_payload_density_grid_ship_plan(
            1,
            1,
            1,
            1,
            1,
            0,
            0,
            1,
            ctypes.byref(grid_n_buf),
            grid_bufs,
            2,
            ctypes.byref(grid_n_attach),
            grid_attach,
            10,
        )
        == 1
        and grid_n_buf.value == 2
        and grid_bufs[1].registry_key == 1
        and grid_n_attach.value == 8
        and grid_attach[0].attach_kind == 0
        and grid_attach[7].attach_kind == 9,
        "payload_density_grid_ship_plan full overlay attach order",
    )
    chan_n = ctypes.c_size_t(0)
    chan_entries = (PayloadChannelShipEntry * 5)()
    ok(
        lib.xyg_payload_channel_ship_plan(
            1,
            1,
            1,
            1,
            0,
            0,
            ctypes.byref(chan_n),
            chan_entries,
            5,
        )
        == 1
        and chan_n.value == 2
        and chan_entries[0].registry_key == 4
        and chan_entries[0].trace_slot == 4
        and chan_entries[0].ship_method == 1
        and chan_entries[1].registry_key == 0
        and chan_entries[1].ship_method == 0,
        "payload_channel_ship_plan ribbon color2 before color_size",
    )
    wire_buf = ctypes.c_int32(-1)
    wire_xform = ctypes.c_int32(-1)
    wire_dtype_u8 = ctypes.c_int32(-1)
    wire_palette = ctypes.c_int32(-1)
    wire_set_n = ctypes.c_int32(-1)
    ok(
        lib.xyg_payload_channel_wire_encode(
            0,
            2,
            256,
            0,
            0,
            ctypes.byref(wire_buf),
            ctypes.byref(wire_xform),
            ctypes.byref(wire_dtype_u8),
            ctypes.byref(wire_palette),
            ctypes.byref(wire_set_n),
        )
        == 1
        and wire_buf.value == 1
        and wire_xform.value == 4
        and wire_dtype_u8.value == 1
        and wire_palette.value == 1
        and lib.xyg_payload_channel_wire_encode(
            0,
            2,
            257,
            0,
            0,
            ctypes.byref(wire_buf),
            ctypes.byref(wire_xform),
            ctypes.byref(wire_dtype_u8),
            ctypes.byref(wire_palette),
            ctypes.byref(wire_set_n),
        )
        == 1
        and wire_buf.value == 2
        and wire_xform.value == 4
        and wire_dtype_u8.value == 0,
        "payload_channel_wire_encode categorical u8 vs f32",
    )
    ribbon_tier_direct = ctypes.c_int32(-1)
    ribbon_n_marks = ctypes.c_size_t(0)
    ribbon_apply_palette = ctypes.c_int32(-1)
    ribbon_x_scale = ctypes.c_int32(-1)
    ribbon_y_scale = ctypes.c_int32(-1)
    ribbon_channel_slot = ctypes.c_int32(-1)
    ribbon_include_styles = ctypes.c_int32(-1)
    ribbon_attach_transition = ctypes.c_int32(-1)
    ribbon_attempt_gather = ctypes.c_int32(-1)
    ribbon_attach_color2 = ctypes.c_int32(-1)
    ok(
        lib.xyg_payload_ribbon_emit_plan(
            5,
            1,
            1,
            0,
            1,
            1,
            ctypes.byref(ribbon_tier_direct),
            ctypes.byref(ribbon_n_marks),
            ctypes.byref(ribbon_apply_palette),
            ctypes.byref(ribbon_x_scale),
            ctypes.byref(ribbon_y_scale),
            ctypes.byref(ribbon_channel_slot),
            ctypes.byref(ribbon_include_styles),
            ctypes.byref(ribbon_attach_transition),
            ctypes.byref(ribbon_attempt_gather),
            ctypes.byref(ribbon_attach_color2),
        )
        == 1
        and ribbon_tier_direct.value == 1
        and ribbon_n_marks.value == 5
        and ribbon_apply_palette.value == 1
        and ribbon_x_scale.value == 1
        and ribbon_y_scale.value == 0
        and ribbon_channel_slot.value == 1
        and ribbon_attach_transition.value == 1
        and ribbon_attempt_gather.value == 1
        and ribbon_attach_color2.value == 1,
        "payload_ribbon_emit_plan gather skeleton",
    )
    segments_n_marks = ctypes.c_size_t(0)
    segments_apply_palette = ctypes.c_int32(-1)
    segments_x_scale = ctypes.c_int32(-1)
    segments_y_scale = ctypes.c_int32(-1)
    segments_channel_slot = ctypes.c_int32(-1)
    segments_include_styles = ctypes.c_int32(-1)
    segments_attach_transition = ctypes.c_int32(-1)
    segments_attempt_gather = ctypes.c_int32(-1)
    segments_attempt_role_keys = ctypes.c_int32(-1)
    ok(
        lib.xyg_payload_segments_emit_plan(
            b"errorbar",
            8,
            33,
            1,
            1,
            0,
            1,
            ctypes.byref(segments_n_marks),
            ctypes.byref(segments_apply_palette),
            ctypes.byref(segments_x_scale),
            ctypes.byref(segments_y_scale),
            ctypes.byref(segments_channel_slot),
            ctypes.byref(segments_include_styles),
            ctypes.byref(segments_attach_transition),
            ctypes.byref(segments_attempt_gather),
            ctypes.byref(segments_attempt_role_keys),
        )
        == 1
        and segments_n_marks.value == 33
        and segments_apply_palette.value == 1
        and segments_x_scale.value == 1
        and segments_y_scale.value == 0
        and segments_channel_slot.value == 1
        and segments_attach_transition.value == 1
        and segments_attempt_gather.value == 1
        and segments_attempt_role_keys.value == 1,
        "payload_segments_emit_plan gather skeleton",
    )
    scatter_emit_density = ctypes.c_int32(-1)
    scatter_clear_sel = ctypes.c_int32(-1)
    scatter_drill_false = ctypes.c_int32(-1)
    scatter_set_sel = ctypes.c_int32(-1)
    scatter_tier_direct = ctypes.c_int32(-1)
    scatter_n_marks = ctypes.c_size_t(0)
    scatter_apply_palette = ctypes.c_int32(-1)
    scatter_attach_anim = ctypes.c_int32(-1)
    scatter_x_scale = ctypes.c_int32(-1)
    scatter_y_scale = ctypes.c_int32(-1)
    scatter_channel_slot = ctypes.c_int32(-1)
    scatter_include_styles = ctypes.c_int32(-1)
    scatter_attach_transition = ctypes.c_int32(-1)
    scatter_attach_tooltip = ctypes.c_int32(-1)
    scatter_filter_tooltip = ctypes.c_int32(-1)
    scatter_tooltip_ok = ctypes.c_int32(-1)
    ok(
        lib.xyg_payload_scatter_emit_plan(
            200_001,
            0,
            -1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            ctypes.byref(scatter_emit_density),
            ctypes.byref(scatter_clear_sel),
            ctypes.byref(scatter_drill_false),
            ctypes.byref(scatter_set_sel),
            ctypes.byref(scatter_tier_direct),
            ctypes.byref(scatter_n_marks),
            ctypes.byref(scatter_apply_palette),
            ctypes.byref(scatter_attach_anim),
            ctypes.byref(scatter_x_scale),
            ctypes.byref(scatter_y_scale),
            ctypes.byref(scatter_channel_slot),
            ctypes.byref(scatter_include_styles),
            ctypes.byref(scatter_attach_transition),
            ctypes.byref(scatter_attach_tooltip),
            ctypes.byref(scatter_filter_tooltip),
            ctypes.byref(scatter_tooltip_ok),
        )
        == 1
        and scatter_emit_density.value == 1
        and scatter_clear_sel.value == 1
        and scatter_drill_false.value == 1
        and scatter_attach_transition.value == 1,
        "payload_scatter_emit_plan density tier skeleton",
    )
    ok(
        lib.xyg_payload_scatter_emit_plan(
            100,
            0,
            -1,
            0,
            0,
            50,
            1,
            1,
            0,
            1,
            1,
            100,
            ctypes.byref(scatter_emit_density),
            ctypes.byref(scatter_clear_sel),
            ctypes.byref(scatter_drill_false),
            ctypes.byref(scatter_set_sel),
            ctypes.byref(scatter_tier_direct),
            ctypes.byref(scatter_n_marks),
            ctypes.byref(scatter_apply_palette),
            ctypes.byref(scatter_attach_anim),
            ctypes.byref(scatter_x_scale),
            ctypes.byref(scatter_y_scale),
            ctypes.byref(scatter_channel_slot),
            ctypes.byref(scatter_include_styles),
            ctypes.byref(scatter_attach_transition),
            ctypes.byref(scatter_attach_tooltip),
            ctypes.byref(scatter_filter_tooltip),
            ctypes.byref(scatter_tooltip_ok),
        )
        == 1
        and scatter_emit_density.value == 0
        and scatter_set_sel.value == 1
        and scatter_n_marks.value == 50
        and scatter_channel_slot.value == 0
        and scatter_include_styles.value == 1
        and scatter_attach_transition.value == 1
        and scatter_attach_tooltip.value == 1,
        "payload_scatter_emit_plan direct tier skeleton",
    )
    trace_mode_bytes = b"categorical"
    dt_plan = (ctypes.c_byte * 152)()
    ok(
        lib.xyg_payload_density_trace_emit_plan(
            1,
            trace_mode_bytes,
            len(trace_mode_bytes),
            1,
            1,
            1,
            0,
            1,
            1,
            1,
            0,
            0,
            1,
            0,
            512,
            384,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0.0,
            1.0,
            0.0,
            1.0,
            0.0,
            1.0,
            0.0,
            1.0,
            0.0,
            1.0,
            0.0,
            1.0,
            10_000,
            0,
            0,
            2,
            ctypes.byref(dt_plan),
        )
        == 1,
        "payload_density_trace_emit_plan identity grid orchestration",
    )
    dt_view = memoryview(dt_plan)
    dt_attach_transition = int.from_bytes(dt_view[92:96], "little")
    dt_n_marks = int.from_bytes(dt_view[96:104], "little")
    dt_visible_init = int.from_bytes(dt_view[104:108], "little")
    dt_attach_sample = int.from_bytes(dt_view[108:112], "little")
    dt_ship_categorical = int.from_bytes(dt_view[132:136], "little")
    dt_channels_dropped = int.from_bytes(dt_view[148:152], "little")
    ok(
        dt_attach_transition == 1
        and dt_n_marks == 512 * 384
        and dt_visible_init == 1
        and dt_attach_sample == 1
        and dt_ship_categorical == 1
        and dt_channels_dropped == 1,
        "payload_density_trace_emit_plan packed fields",
    )
    build_plan = (ctypes.c_byte * 88)()
    ok(
        lib.xyg_payload_build_plan(
            1,
            0,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            ctypes.byref(build_plan),
        )
        == 1,
        "payload_build_plan split density unsupported",
    )
    bp_view = memoryview(build_plan)
    ok(
        int.from_bytes(bp_view[0:4], "little") == 1
        and int.from_bytes(bp_view[4:8], "little", signed=True) == 2
        and int.from_bytes(bp_view[8:12], "little") == 1,
        "payload_build_plan show_legend and wasm_density attach",
    )
    axis_attach = (ctypes.c_uint32 * 32)()
    ok(
        lib.xyg_payload_axis_spec_attach_plan(1, 1, ctypes.byref(axis_attach)) == 1
        and axis_attach[0] == 1
        and axis_attach[1] == 1
        and axis_attach[25] == 0
        and axis_attach[30] == 0,
        "payload_axis_spec_attach_plan cartesian core no polar",
    )
    ok(
        lib.xyg_payload_axis_spec_attach_plan(0, 1, ctypes.byref(axis_attach)) == 1
        and axis_attach[25] == 1
        and axis_attach[30] == 0,
        "payload_axis_spec_attach_plan polar theta on x",
    )
    ok(
        lib.xyg_payload_axis_spec_attach_plan(0, 0, ctypes.byref(axis_attach)) == 1
        and axis_attach[25] == 0
        and axis_attach[30] == 1
        and axis_attach[31] == 1,
        "payload_axis_spec_attach_plan polar r on y",
    )
    xytc_figure = (ctypes.c_uint32 * 1)()
    ok(
        lib.xyg_scene_xytc_figure_plan(1, ctypes.byref(xytc_figure)) == 1 and xytc_figure[0] == 1,
        "scene_xytc_figure_plan show_legend",
    )
    xytc_dispatch = (ctypes.c_uint32 * 10)()
    scatter_kind = array("B", b"scatter")
    ok(
        lib.xyg_scene_xytc_trace_dispatch_plan(
            _ptr(scatter_kind, ctypes.c_uint8),
            len(scatter_kind),
            0,
            1,
            0,
            ctypes.byref(xytc_dispatch),
        )
        == 1
        and xytc_dispatch[1] == 1
        and xytc_dispatch[2] == 0
        and xytc_dispatch[4] == 0
        and xytc_dispatch[7] == 1
        and xytc_dispatch[8] == 1,
        "scene_xytc_trace_dispatch_plan scatter density glyph",
    )
    ribbon_kind = array("B", b"ribbon")
    ok(
        lib.xyg_scene_xytc_trace_dispatch_plan(
            _ptr(ribbon_kind, ctypes.c_uint8),
            len(ribbon_kind),
            0,
            0,
            0,
            ctypes.byref(xytc_dispatch),
        )
        == 1
        and xytc_dispatch[4] == 1
        and xytc_dispatch[3] == 0,
        "scene_xytc_trace_dispatch_plan ribbon color2",
    )
    xyta_figure = (ctypes.c_uint32 * 1)()
    ok(
        lib.xyg_scene_xyta_figure_plan(1, ctypes.byref(xyta_figure)) == 1 and xyta_figure[0] == 1,
        "scene_xyta_figure_plan polar",
    )
    xyta_dispatch = (ctypes.c_uint32 * 8)()
    heatmap_kind = array("B", b"heatmap")
    ok(
        lib.xyg_scene_xyta_trace_dispatch_plan(
            _ptr(heatmap_kind, ctypes.c_uint8),
            len(heatmap_kind),
            0,
            0,
            1,
            1,
            3,
            1,
            1,
            ctypes.byref(xyta_dispatch),
        )
        == 1
        and xyta_dispatch[1] == 1
        and xyta_dispatch[2] == 0
        and xyta_dispatch[7] == 0,
        "scene_xyta_trace_dispatch_plan heatmap wins",
    )
    scatter_kind = array("B", b"scatter")
    ok(
        lib.xyg_scene_xyta_trace_dispatch_plan(
            _ptr(scatter_kind, ctypes.c_uint8),
            len(scatter_kind),
            0,
            1,
            0,
            0,
            0,
            0,
            0,
            ctypes.byref(xyta_dispatch),
        )
        == 1
        and xyta_dispatch[7] == 1
        and xyta_dispatch[6] == 0,
        "scene_xyta_trace_dispatch_plan scatter density",
    )
    scatter_kind_pack = array("B", b"scatter")
    symbol_b = array("B", b"circle")
    xytc_style = SceneXytcTraceStyleIn(
        0,
        0,
        1.0,
        1.0,
        1.0,
        1.0,
        0,
        0,
        0,
        float("nan"),
        0,
        0,
        float("nan"),
        0,
        0.0,
        0,
        0.0,
        0,
        0.0,
        0,
        float("nan"),
        0,
        float("nan"),
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        0.0,
        0.0,
        0.0,
        len(symbol_b),
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )
    xytc_pack = SceneXytcTracePackIn(
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        len(scatter_kind_pack),
        0,
        0,
        0,
        xytc_style,
    )
    xytc_out = (ctypes.c_uint8 * 512)()
    xytc_out_len = ctypes.c_size_t(0)
    ok(
        lib.xyg_scene_xytc_trace_pack(
            ctypes.byref(xytc_pack),
            _ptr(scatter_kind_pack, ctypes.c_uint8),
            None,
            _ptr(symbol_b, ctypes.c_uint8),
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            xytc_out,
            len(xytc_out),
            ctypes.byref(xytc_out_len),
        )
        == 0
        and xytc_out_len.value >= 4
        and bytes(xytc_out[:4]) == b"XYTR",
        "scene_xytc_trace_pack scatter default",
    )
    xyta_pack = SceneXytaTracePackIn(
        7,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        0.0,
        0.0,
        0,
        0,
        0,
        0,
        0,
        0,
        0.0,
        1.0,
        0,
        0,
        0,
        0,
        1.0,
        1.0,
        0.0,
        1.0,
        0.0,
        1.0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )
    xyta_out = (ctypes.c_uint8 * 256)()
    xyta_out_len = ctypes.c_size_t(0)
    ok(
        lib.xyg_scene_xyta_trace_pack(
            ctypes.byref(xyta_pack),
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            xyta_out,
            len(xyta_out),
            ctypes.byref(xyta_out_len),
        )
        == 0
        and xyta_out_len.value >= 4
        and int.from_bytes(bytes(xyta_out[:4]), "little") & (1 << 1) != 0,
        "scene_xyta_trace_pack density branch",
    )
    xyfs_figure = (ctypes.c_uint32 * 1)()
    ok(
        lib.xyg_scene_figure_support_figure_plan(1, ctypes.byref(xyfs_figure)) == 1
        and xyfs_figure[0] == 1,
        "scene_figure_support_figure_plan polar",
    )
    xyfs_dispatch = (ctypes.c_uint32 * 8)()
    bar_kind = array("B", b"bar")
    ok(
        lib.xyg_scene_figure_support_trace_dispatch_plan(
            _ptr(bar_kind, ctypes.c_uint8),
            len(bar_kind),
            0,
            0,
            0,
            0,
            ctypes.byref(xyfs_dispatch),
        )
        == 1
        and xyfs_dispatch[4] == 1
        and xyfs_dispatch[3] == 0,
        "scene_figure_support_trace_dispatch_plan bar rect extra",
    )
    xycl_figure = (ctypes.c_uint32 * 1)()
    ok(
        lib.xyg_scene_xycl_figure_plan(1, ctypes.byref(xycl_figure)) == 1 and xycl_figure[0] == 1,
        "scene_xycl_figure_plan polar",
    )
    xynm_figure = (ctypes.c_uint32 * 1)()
    ok(
        lib.xyg_scene_xynm_figure_plan(0, ctypes.byref(xynm_figure)) == 1 and xynm_figure[0] == 0,
        "scene_xynm_figure_plan show_legend",
    )
    xycf_figure = (ctypes.c_uint32 * 4)()
    ok(
        lib.xyg_scene_xycf_figure_plan(1, 1, 0, ctypes.byref(xycf_figure)) == 1
        and xycf_figure[0] == 1
        and xycf_figure[1] == 1
        and xycf_figure[2] == 1
        and xycf_figure[3] == 0,
        "scene_xycf_figure_plan legend and colorbar attach",
    )
    xyaf_dispatch = (ctypes.c_uint32 * 5)()
    rule_kind = array("B", b"rule")
    ok(
        lib.xyg_scene_xyaf_annotation_dispatch_plan(
            _ptr(rule_kind, ctypes.c_uint8),
            len(rule_kind),
            0,
            0,
            ctypes.byref(xyaf_dispatch),
        )
        == 1
        and xyaf_dispatch[0] == 0
        and xyaf_dispatch[1] == 1
        and xyaf_dispatch[3] == 1,
        "scene_xyaf_annotation_dispatch_plan rule dash and axis",
    )
    xyef_figure = (ctypes.c_uint32 * 3)()
    ok(
        lib.xyg_scene_public_export_figure_plan(1, 1, 0, ctypes.byref(xyef_figure)) == 1
        and xyef_figure[0] == 1
        and xyef_figure[1] == 1
        and xyef_figure[2] == 0,
        "scene_public_export_figure_plan polar and chrome styles",
    )
    xyef_dispatch = (ctypes.c_uint32 * 3)()
    scatter_kind = array("B", b"scatter")
    ok(
        lib.xyg_scene_public_export_trace_dispatch_plan(
            _ptr(scatter_kind, ctypes.c_uint8),
            len(scatter_kind),
            0,
            1,
            ctypes.byref(xyef_dispatch),
        )
        == 1
        and xyef_dispatch[1] == 1
        and xyef_dispatch[2] == 0,
        "scene_public_export_trace_dispatch_plan scatter density blit",
    )
    polar_figure = (ctypes.c_uint32 * 2)()
    ok(
        lib.xyg_scene_polar_figure_plan(1, ctypes.byref(polar_figure)) == 1
        and polar_figure[0] == 1
        and polar_figure[1] == 1,
        "scene_polar_figure_plan attach xypl",
    )
    encode_attach = (ctypes.c_uint32 * 10)()
    ok(
        lib.xyg_scene_encode_product_attach_plan(1, ctypes.byref(encode_attach)) == 1
        and encode_attach[1] == 1
        and encode_attach[2] == 1
        and encode_attach[3] == 2
        and encode_attach[8] == 7
        and encode_attach[9] == 8,
        "scene_encode_product_attach_plan pack order",
    )
    density_color_mode = ctypes.c_int32(-1)
    density_categorical = ctypes.c_int32(-1)
    density_compact = ctypes.c_int32(-1)
    density_stratified = ctypes.c_int32(-1)
    ok(
        lib.xyg_density_color_classify(
            2,
            1,
            1,
            1,
            ctypes.byref(density_color_mode),
            ctypes.byref(density_categorical),
            ctypes.byref(density_compact),
            ctypes.byref(density_stratified),
        )
        == 1
        and density_color_mode.value == 2
        and density_categorical.value == 1
        and density_compact.value == 1
        and density_stratified.value == 1,
        "density_color_classify stratified categorical",
    )
    trace_mode = b"categorical"
    trace_color_mode = ctypes.c_int32(-1)
    trace_categorical = ctypes.c_int32(-1)
    trace_compact = ctypes.c_int32(-1)
    trace_stratified = ctypes.c_int32(-1)
    ok(
        lib.xyg_density_trace_color_classify(
            1,
            trace_mode,
            len(trace_mode),
            1,
            1,
            1,
            ctypes.byref(trace_color_mode),
            ctypes.byref(trace_categorical),
            ctypes.byref(trace_compact),
            ctypes.byref(trace_stratified),
        )
        == 1
        and trace_color_mode.value == 2
        and trace_categorical.value == 1
        and trace_stratified.value == 1,
        "density_trace_color_classify categorical mode",
    )
    bin_x_c0 = ctypes.c_double(0.0)
    bin_x_c1 = ctypes.c_double(0.0)
    bin_y_c0 = ctypes.c_double(0.0)
    bin_y_c1 = ctypes.c_double(0.0)
    ok(
        lib.xyg_density_bin_coord_endpoints(
            1,
            0,
            0.0,
            10.0,
            1.0,
            9.0,
            2.0,
            8.0,
            3.0,
            7.0,
            ctypes.byref(bin_x_c0),
            ctypes.byref(bin_x_c1),
            ctypes.byref(bin_y_c0),
            ctypes.byref(bin_y_c1),
        )
        == 1
        and abs(bin_x_c0.value - 0.0) < 1e-12
        and abs(bin_x_c1.value - 10.0) < 1e-12
        and abs(bin_y_c0.value - 3.0) < 1e-12
        and abs(bin_y_c1.value - 7.0) < 1e-12,
        "density_bin_coord_endpoints linear x",
    )
    ok(
        lib.xyg_density_uses_channel_colormap(1, b"continuous", 10) == 1
        and lib.xyg_density_uses_channel_colormap(1, b"categorical", 11) == 0,
        "density_uses_channel_colormap admit",
    )
    ok(
        lib.xyg_density_reduction_kind(b"exact", 5) == 0
        and lib.xyg_density_reduction_kind(b"pyramid-L2", 10) == 1,
        "density_reduction_kind prefix",
    )
    overlay_buf = ctypes.create_string_buffer(32)
    ok(
        lib.xyg_density_overlay_omitted_wire(1, 1, overlay_buf, 32) == 15
        and overlay_buf.raw[:15] == b"rows_exceed_u32"
        and lib.xyg_density_overlay_omitted_wire(2, 0, overlay_buf, 32) == 13
        and overlay_buf.raw[:13] == b"static_raster",
        "density_overlay_omitted_wire labels",
    )
    ok(
        lib.xyg_density_grid_path_identity_state(1) == 1
        and lib.xyg_density_grid_path_identity_state(5) == 0
        and lib.xyg_density_grid_path_identity_state(99) == -1,
        "density_grid_path_identity_state",
    )
    ok(
        lib.xyg_density_constant_color_wire_admit(1, b"constant", 8, 1) == 1
        and lib.xyg_density_constant_color_wire_admit(1, b"continuous", 10, 1) == 0,
        "density_constant_color_wire_admit",
    )
    ok(
        lib.xyg_density_categorical_color_wire_admit(1, 1) == 1
        and lib.xyg_density_categorical_color_wire_admit(0, 1) == 0
        and lib.xyg_density_categorical_color_wire_admit(1, 0) == 0,
        "density_categorical_color_wire_admit",
    )
    ok(
        lib.xyg_density_mean_color_wire_admit(1, b"continuous", 10) == 1
        and lib.xyg_density_mean_color_wire_admit(1, b"constant", 8) == 0
        and lib.xyg_density_mean_color_wire_admit(0, b"categorical", 11) == 0,
        "density_mean_color_wire_admit",
    )
    ok(
        lib.xyg_density_channels_dropped_compat(0) == 0
        and lib.xyg_density_channels_dropped_compat(2) == 1,
        "density_channels_dropped_compat",
    )
    ok(
        lib.xyg_density_dropped_channel_wire_admit(b"color", 5, 1) == 0
        and lib.xyg_density_dropped_channel_wire_admit(b"size", 4, 1) == 1
        and lib.xyg_density_dropped_channel_wire_admit(b"color", 5, 0) == 1,
        "density_dropped_channel_wire_admit",
    )
    ok(
        lib.xyg_density_mean_color_rgba_wire_admit(1, 0) == 1
        and lib.xyg_density_mean_color_rgba_wire_admit(0, 1) == 1
        and lib.xyg_density_mean_color_rgba_wire_admit(0, 0) == 0,
        "density_mean_color_rgba_wire_admit",
    )
    ok(
        lib.xyg_density_wasm_source_admit(1, 1) == 1
        and lib.xyg_density_wasm_source_admit(0, 1) == 0,
        "density_wasm_source_admit",
    )
    ok(
        lib.xyg_density_wasm_density_wire_kind(1, 1, 0) == 1
        and lib.xyg_density_wasm_density_wire_kind(1, 0, 1) == 2
        and lib.xyg_density_wasm_density_wire_kind(0, 1, 1) == 0,
        "density_wasm_density_wire_kind",
    )
    sample_keep = ctypes.c_int32(-1)
    sample_n = lib.xyg_payload_sample_target_indices(
        100,
        8192,
        0,
        0,
        2.0,
        ctypes.byref(sample_keep),
        _ptr(even_out, ctypes.c_uint32),
        4,
    )
    ok(sample_keep.value == 1 and sample_n == 0, "payload_sample_target_indices keep-all")
    bin_out = array("d", [0.0, 0.0, 0.0, 0.0])
    bw_n = lib.xyg_density_bin_window(
        1, 1, 0.0, 2.0, 0.0, 3.0, 0.0, 0.0, 0.0, 0.0, _ptr(bin_out, ctypes.c_double)
    )
    ok(bw_n == 4 and list(bin_out) == [0.0, 2.0, 0.0, 3.0], "density_bin_window linear")
    ok(
        lib.xyg_density_full_identity(0, 0, 0, 0, 0.0, 1.0, 0.0, 1.0, 0.0, 2.0, 0.0, 2.0) == 1,
        "density_full_identity",
    )
    ok(lib.xyg_density_grid_path(0, 1, 0, 0, 0) == 1, "density_grid_path identity grid")
    binning_buf = array("B", [0]) * 32
    binning_n = lib.xyg_density_format_binning(1, 0, 0, 0, _ptr(binning_buf, ctypes.c_uint8), 32)
    ok(binning_n == 5 and bytes(binning_buf[:5]) == b"exact", "density_format_binning exact")
    ok(lib.xyg_density_wasm_eligible(1, 1, 1, 1, 0, 0, 100) == 1, "density_wasm_eligible")
    tick_pos = array("d", [100.0 + i * 90.0 for i in range(9)])
    tick_labels = [f"Category_Name_{i:02d}".encode() for i in range(9)]
    tick_packed = b"".join(tick_labels)
    tick_lens = array("I", [len(item) for item in tick_labels])
    tick_bytes = array("B", tick_packed)
    tick_index = array("I", [0] * 9)
    tick_angle = array("d", [0.0] * 9)
    tick_row = array("I", [0] * 9)
    tick_n = lib.xyg_scene_tick_label_layout(
        _ptr(tick_pos, ctypes.c_double),
        9,
        _ptr(tick_lens, ctypes.c_uint32),
        _ptr(tick_bytes, ctypes.c_uint8),
        len(tick_packed),
        2,
        0,
        2,
        1,
        11.0,
        8.0,
        -30.0,
        _ptr(tick_index, ctypes.c_uint32),
        _ptr(tick_angle, ctypes.c_double),
        _ptr(tick_row, ctypes.c_uint32),
        9,
    )
    ok(
        tick_n == 9
        and list(tick_index) == list(range(9))
        and abs(tick_angle[0] + 30.0) < 1e-12
        and list(tick_row) == [0] * 9,
        "tick_label_layout end-anchor rotate keeps all",
    )
    lg_labels = [b"1", b"2", b"3", b"4"]
    lg_packed = b"".join(lg_labels)
    lg_lens = array("I", [len(item) for item in lg_labels])
    lg_bytes = array("B", lg_packed)
    lg_title = array("B", b"Classes")
    lg_loc = array("B", b"lower left")
    lg_metrics = array("d", [0.0] * 17)
    lg_widths = array("d", [0.0] * 4)
    lg_offsets = array("d", [0.0] * 4)
    lg_name_lens = array("I", [0] * 4)
    lg_names = array("B", [0] * 64)
    lg_title_out = array("B", [0] * 32)
    lg_title_len = ctypes.c_size_t(0)
    lg_n = lib.xyg_legend_box_layout(
        0.0,
        0.0,
        560.0,
        400.0,
        _ptr(lg_lens, ctypes.c_uint32),
        _ptr(lg_bytes, ctypes.c_uint8),
        len(lg_packed),
        4,
        _ptr(lg_title, ctypes.c_uint8),
        len(lg_title),
        _ptr(lg_loc, ctypes.c_uint8),
        len(lg_loc),
        11.0,
        float("nan"),
        float("nan"),
        float("nan"),
        1,
        0.4,
        0.5,
        null_f64,
        0,
        0.0,
        _ptr(lg_metrics, ctypes.c_double),
        _ptr(lg_widths, ctypes.c_double),
        _ptr(lg_offsets, ctypes.c_double),
        4,
        _ptr(lg_name_lens, ctypes.c_uint32),
        _ptr(lg_names, ctypes.c_uint8),
        len(lg_names),
        _ptr(lg_title_out, ctypes.c_uint8),
        len(lg_title_out),
        ctypes.byref(lg_title_len),
    )
    lg_title_text = bytes(lg_title_out[: lg_title_len.value]).decode()
    ok(
        lg_n == 4 and lg_title_text.startswith("Clas") and lg_metrics[12] > 0.0,
        "legend_box_layout keeps Classes title prefix",
    )
    tb_text = array("B", b"first\r\nsecond")
    tb_metrics = array("d", [0.0] * 6)
    tb_lens = array("I", [0, 0, 0, 0])
    tb_packed = array("B", [0] * 64)
    tb_n = lib.xyg_text_block_measure(
        _ptr(tb_text, ctypes.c_uint8),
        len(tb_text),
        12.0,
        float("nan"),
        float("nan"),
        _ptr(tb_metrics, ctypes.c_double),
        _ptr(tb_lens, ctypes.c_uint32),
        4,
        _ptr(tb_packed, ctypes.c_uint8),
        len(tb_packed),
    )
    tb_rot_x = ctypes.c_double()
    tb_rot_y = ctypes.c_double()
    tb_rot = lib.xyg_text_block_rotated_extent(
        10.0,
        4.0,
        90.0,
        ctypes.byref(tb_rot_x),
        ctypes.byref(tb_rot_y),
    )
    y_title = array("B", b"Y")
    y_room = ctypes.c_double()
    y_n = lib.xyg_y_axis_left_room(
        7.0,
        23.0,
        _ptr(y_title, ctypes.c_uint8),
        len(y_title),
        12.0,
        4.8,
        ctypes.byref(y_room),
    )
    ok(
        tb_n == 2
        and tb_metrics[5] == 2.0
        and bytes(tb_packed[:5]) == b"first"
        and tb_rot == 2
        and abs(tb_rot_x.value - 4.0) < 1e-12
        and y_n == 1
        and y_room.value > 23.0,
        "text_block_measure CRLF and titled y room",
    )
    pad = array("d", [0.0] * 4)
    pad_n = lib.xyg_compat_default_padding(1, _ptr(pad, ctypes.c_double))
    recut_in = array("d", [0.0, 0.0, 200.0, 200.0, 10.0])
    recut_out = array("d", [0.0] * 9)
    recut_n = lib.xyg_recut_polar_plot(
        _ptr(recut_in, ctypes.c_double),
        200.0,
        200.0,
        0,
        0.0,
        30.0,
        1,
        0,
        0,
        _ptr(recut_out, ctypes.c_double),
    )
    ok(
        pad_n == 4
        and pad[0] == 6.0
        and pad[1] == 8.0
        and pad[2] == 36.0
        and pad[3] == 46.0
        and recut_n == 9
        and recut_out[0] == 30.0
        and recut_out[1] == 30.0
        and recut_out[2] == 140.0
        and recut_out[3] == 140.0
        and recut_out[4] == 40.0,
        "compat default padding and authored-padding polar recut",
    )
    tight_extra = array("d", [0.0] * 4)
    tight_rect = array("d", [0.0, 0.0, 1.0, 1.0])
    tight_out = array("d", [0.0] * 6)
    tight_n = lib.xyg_tight_layout_solve(
        800.0,
        600.0,
        1,
        1,
        0,
        None,
        0,
        _ptr(tight_extra, ctypes.c_double),
        float("nan"),
        float("nan"),
        float("nan"),
        1.0,
        _ptr(tight_rect, ctypes.c_double),
        _ptr(tight_out, ctypes.c_double),
    )
    ok(
        tight_n == 6 and abs(tight_out[0] - 62.0 / 800.0) < 1e-12,
        "tight_layout_solve empty wide defaults",
    )
    combine_out = array("d", [0.0] * 12)
    combine_n = lib.xyg_compat_combine_plot(
        900.0,
        420.0,
        None,
        0.0,
        0.0,
        0.0,
        0.0,
        0,
        0,
        0,
        0,
        float("nan"),
        float("nan"),
        float("nan"),
        None,
        0,
        0,
        0.0,
        0.0,
        0,
        0,
        0,
        _ptr(combine_out, ctypes.c_double),
    )
    extra_out = array("d", [0.0] * 4)
    extra_n = lib.xyg_tight_layout_figure_extra(
        800.0,
        600.0,
        20.0,
        0.98,
        float("nan"),
        12.0,
        80.0,
        _ptr(extra_out, ctypes.c_double),
    )
    ok(
        combine_n == 12
        and combine_out[0] == 62.0
        and combine_out[1] == 10.0
        and combine_out[2] == 824.0
        and extra_n == 4
        and extra_out[0] == 20.0
        and extra_out[1] == 92.0,
        "compat_combine_plot default padding and tight figure extras",
    )
    tick_lo = ctypes.c_double()
    tick_hi = ctypes.c_double()
    tick_window_n = lib.xyg_tick_window(
        0.0,
        360.0,
        1,
        0,
        0,
        300.0,
        420.0,
        ctypes.byref(tick_lo),
        ctypes.byref(tick_hi),
    )
    tick_values = array("d", [300.0, 330.0, 0.0, 30.0, 60.0, 200.0])
    tick_out = array("d", [0.0] * 6)
    tick_n = lib.xyg_tick_window_filter(
        _ptr(tick_values, ctypes.c_double),
        6,
        tick_lo.value,
        tick_hi.value,
        1,
        0,
        0,
        _ptr(tick_out, ctypes.c_double),
        6,
    )
    ok(
        tick_window_n == 2
        and tick_lo.value == 300.0
        and tick_hi.value == 420.0
        and tick_n == 5
        and list(tick_out[:5]) == [300.0, 330.0, 0.0, 30.0, 60.0],
        "tick_window seam-crossing degree sector",
    )
    linear_values = array("d", [0.0, 45.0, 90.0, 200.0, -10.0, float("nan")])
    linear_out = array("d", [0.0] * 6)
    linear_n = lib.xyg_tick_window_filter(
        _ptr(linear_values, ctypes.c_double),
        6,
        0.0,
        180.0,
        0,
        0,
        0,
        _ptr(linear_out, ctypes.c_double),
        6,
    )
    ok(linear_n == 3 and list(linear_out[:3]) == [0.0, 45.0, 90.0], "tick_window linear reject")
    tick_label = (ctypes.c_char * 32)()
    tick_fmt = b"$,.1f ms"
    tick_fmt_n = lib.xyg_tick_format(
        12345.678,
        1.0,
        0,
        0,
        0,
        tick_fmt,
        len(tick_fmt),
        0,
        None,
        None,
        0,
        tick_label,
        len(tick_label),
    )
    ok(
        tick_fmt_n == len(b"$12,345.7 ms") and tick_label.value == b"$12,345.7 ms",
        "tick_format number spec",
    )
    polar_metrics = array("d", [0.0]) * 23
    polar_layout_n = lib.xyg_polar_layout(
        0.0,
        0.0,
        400.0,
        400.0,
        0,
        0.0,
        0,
        0.0,
        6.283185307179586,
        0,
        0.0,
        1.0,
        float("nan"),
        0.0,
        0,
        1.0,
        0,
        _ptr(polar_metrics, ctypes.c_double),
        23,
    )
    polar_theta = array("d", [0.0, 1.5707963267948966])
    polar_r = array("d", [1.0, 1.0])
    polar_px = array("d", [0.0, 0.0])
    polar_py = array("d", [0.0, 0.0])
    polar_proj_n = lib.xyg_polar_project(
        _ptr(polar_metrics, ctypes.c_double),
        23,
        _ptr(polar_theta, ctypes.c_double),
        _ptr(polar_r, ctypes.c_double),
        2,
        _ptr(polar_px, ctypes.c_double),
        _ptr(polar_py, ctypes.c_double),
    )
    ok(
        polar_layout_n == 23
        and polar_proj_n == 2
        and abs(polar_px[0] - 400.0) < 1e-6
        and abs(polar_py[0] - 200.0) < 1e-6
        and abs(polar_px[1] - 200.0) < 1e-6
        and abs(polar_py[1] - 0.0) < 1e-6,
        "polar default-cardinals",
    )
    polar_wedge_n = lib.xyg_polar_wedge_points(
        _ptr(polar_metrics, ctypes.c_double),
        23,
        0.0,
        1.5707963267948966,
        0.5,
        1.0,
        0.0,
        0.0,
        8,
        float("nan"),
        float("nan"),
        null_f64,
        null_f64,
        0,
    )
    polar_wx = array("d", [0.0]) * 32
    polar_wy = array("d", [0.0]) * 32
    polar_wedge_filled = lib.xyg_polar_wedge_points(
        _ptr(polar_metrics, ctypes.c_double),
        23,
        0.0,
        1.5707963267948966,
        0.5,
        1.0,
        0.0,
        0.0,
        8,
        float("nan"),
        float("nan"),
        _ptr(polar_wx, ctypes.c_double),
        _ptr(polar_wy, ctypes.c_double),
        32,
    )
    ok(
        polar_wedge_n == 18
        and polar_wedge_filled == 18
        and abs(polar_wx[0] - 400.0) < 1e-6
        and abs(polar_wy[0] - 200.0) < 1e-6,
        "polar wedge flatten",
    )
    ok(
        lib.xyg_polar_wedge_points(
            _ptr(polar_metrics, ctypes.c_double),
            23,
            0.0,
            1.5707963267948966,
            0.5,
            1.0,
            0.0,
            0.0,
            4097,
            float("nan"),
            float("nan"),
            null_f64,
            null_f64,
            0,
        )
        == size_max,
        "polar wedge overcap",
    )
    step_x = array("d", [0.0, 1.0, 2.0])
    step_y = array("d", [10.0, 20.0, 30.0])
    step_n = lib.xyg_step_arrays(
        _ptr(step_x, ctypes.c_double),
        _ptr(step_y, ctypes.c_double),
        3,
        1,
        null_f64,
        null_f64,
        0,
    )
    step_ox = array("d", [0.0]) * 8
    step_oy = array("d", [0.0]) * 8
    step_filled = lib.xyg_step_arrays(
        _ptr(step_x, ctypes.c_double),
        _ptr(step_y, ctypes.c_double),
        3,
        1,
        _ptr(step_ox, ctypes.c_double),
        _ptr(step_oy, ctypes.c_double),
        8,
    )
    ok(
        step_n == 5
        and step_filled == 5
        and abs(step_ox[0] - 0.0) < 1e-15
        and abs(step_oy[1] - 20.0) < 1e-15
        and abs(step_ox[4] - 2.0) < 1e-15,
        "step arrays pre expand",
    )
    ok(
        lib.xyg_step_arrays(
            _ptr(step_x, ctypes.c_double),
            _ptr(step_y, ctypes.c_double),
            3,
            0,
            null_f64,
            null_f64,
            0,
        )
        == size_max,
        "step arrays invalid mode",
    )
    marker_x = array("d", [0.0, 0.5, 0.0, -0.5])
    marker_y = array("d", [0.5, 0.0, -0.5, 0.0])
    marker_n = lib.xyg_marker_path_scale(
        10.0,
        20.0,
        8.0,
        _ptr(marker_x, ctypes.c_double),
        _ptr(marker_y, ctypes.c_double),
        4,
        null_f64,
        null_f64,
        0,
    )
    marker_ox = array("d", [0.0]) * 4
    marker_oy = array("d", [0.0]) * 4
    marker_filled = lib.xyg_marker_path_scale(
        10.0,
        20.0,
        8.0,
        _ptr(marker_x, ctypes.c_double),
        _ptr(marker_y, ctypes.c_double),
        4,
        _ptr(marker_ox, ctypes.c_double),
        _ptr(marker_oy, ctypes.c_double),
        4,
    )
    ok(
        marker_n == 4
        and marker_filled == 4
        and abs(marker_ox[0] - 10.0) < 1e-15
        and abs(marker_oy[0] - 16.0) < 1e-15
        and abs(marker_ox[1] - 14.0) < 1e-15
        and abs(marker_oy[2] - 24.0) < 1e-15,
        "marker path scale diamond",
    )
    ok(
        lib.xyg_marker_path_scale(
            10.0,
            20.0,
            8.0,
            _ptr(marker_x, ctypes.c_double),
            _ptr(marker_y, ctypes.c_double),
            4,
            _ptr(marker_ox, ctypes.c_double),
            _ptr(marker_oy, ctypes.c_double),
            2,
        )
        == size_max,
        "marker path scale short buffer",
    )
    polar_small = array("d", [0.0]) * 23
    polar_small_n = lib.xyg_polar_layout(
        0.0,
        0.0,
        8.0,
        8.0,
        0,
        0.0,
        0,
        0.0,
        6.283185307179586,
        0,
        0.0,
        1.0,
        float("nan"),
        0.0,
        0,
        1.0,
        0,
        _ptr(polar_small, ctypes.c_double),
        23,
    )
    polar_out_w = ctypes.c_uint32()
    polar_out_h = ctypes.c_uint32()
    polar_map_n = lib.xyg_polar_heatmap_inverse_map(
        _ptr(polar_small, ctypes.c_double),
        23,
        0.0,
        0.0,
        8.0,
        8.0,
        2,
        2,
        0.0,
        0.0,
        6.283185307179586,
        1.0,
        1.0,
        ctypes.byref(polar_out_w),
        ctypes.byref(polar_out_h),
        null_u32,
        null_u32,
        null_u32,
        0,
    )
    polar_hits = array("I", [0]) * 64
    polar_cols = array("I", [0]) * 64
    polar_src = array("I", [0]) * 64
    polar_filled = lib.xyg_polar_heatmap_inverse_map(
        _ptr(polar_small, ctypes.c_double),
        23,
        0.0,
        0.0,
        8.0,
        8.0,
        2,
        2,
        0.0,
        0.0,
        6.283185307179586,
        1.0,
        1.0,
        ctypes.byref(polar_out_w),
        ctypes.byref(polar_out_h),
        _ptr(polar_hits, ctypes.c_uint32),
        _ptr(polar_cols, ctypes.c_uint32),
        _ptr(polar_src, ctypes.c_uint32),
        64,
    )
    ok(
        polar_small_n == 23
        and polar_map_n == 0
        and polar_out_w.value == 8
        and polar_out_h.value == 8
        and polar_filled > 0
        and polar_filled <= 64
        and polar_src[0] < 4,
        "polar heatmap inverse map",
    )
    cf_x = array("d", [0.0, 1.0, 2.0, 3.0, 4.0])
    cf_y = array("d", [0.0, 1.0, 0.5, 2.0, 1.5])
    cf_m = array("d", [0.0]) * 5
    mt_n = lib.xyg_monotone_tangents(
        _ptr(cf_x, ctypes.c_double),
        _ptr(cf_y, ctypes.c_double),
        5,
        _ptr(cf_m, ctypes.c_double),
        5,
    )
    ok(mt_n == 5 and abs(cf_m[0] - 1.0) < 1e-12 and abs(cf_m[4] + 0.5) < 1e-12, "monotone_tangents")
    rr_ox = array("d", [0.0]) * 20
    rr_oy = array("d", [0.0]) * 20
    rr_n = lib.xyg_rounded_rect_poly(
        0.0,
        0.0,
        4.0,
        3.0,
        0.0,
        0.0,
        1,
        _ptr(rr_ox, ctypes.c_double),
        _ptr(rr_oy, ctypes.c_double),
        20,
    )
    ok(rr_n == 4 and rr_ox[1] == 4.0 and rr_oy[2] == 3.0, "rounded_rect_poly square")

    # violin_density: constant sample expands ±0.5 and yields positive density.
    vd = array("d", [3.0, 3.0, 3.0])
    vd_edges = array("d", [0.0]) * 5
    vd_dens = array("d", [0.0]) * 4
    ok(
        lib.xyg_violin_density(
            _ptr(vd, ctypes.c_double),
            len(vd),
            4,
            _ptr(vd_edges, ctypes.c_double),
            _ptr(vd_dens, ctypes.c_double),
        )
        == 1
        and abs(vd_edges[0] - 2.5) < 1e-12
        and abs(vd_edges[4] - 3.5) < 1e-12
        and all(v > 0.0 for v in vd_dens),
        "violin_density constant span",
    )

    # hexbin: four points, mincnt=1, count reduce.
    hx_x = array("d", [0.1, 0.5, 0.9, 0.2])
    hx_y = array("d", [0.1, 0.5, 0.9, 0.8])
    hx_cap = (4 + 1) * (4 + 1) + 4 * 4
    hx_cx = array("d", [0.0]) * hx_cap
    hx_cy = array("d", [0.0]) * hx_cap
    hx_m = array("d", [0.0]) * hx_cap
    hx_c = array("d", [0.0]) * hx_cap
    hx_dx = ctypes.c_double()
    hx_dy = ctypes.c_double()
    hx_n = lib.xyg_hexbin(
        _ptr(hx_x, ctypes.c_double),
        _ptr(hx_y, ctypes.c_double),
        null_f64,
        len(hx_x),
        4,
        4,
        0.0,
        1.0,
        0.0,
        1.0,
        1,
        1,
        0,
        _ptr(hx_cx, ctypes.c_double),
        _ptr(hx_cy, ctypes.c_double),
        _ptr(hx_m, ctypes.c_double),
        _ptr(hx_c, ctypes.c_double),
        hx_cap,
        ctypes.byref(hx_dx),
        ctypes.byref(hx_dy),
    )
    ok(
        hx_n == 4 and abs(hx_dx.value - 0.25) < 1e-12 and sum(hx_c[:hx_n]) == 4.0,
        "hexbin count cells",
    )

    hx_in_x0 = ctypes.c_double()
    hx_in_x1 = ctypes.c_double()
    hx_in_y0 = ctypes.c_double()
    hx_in_y1 = ctypes.c_double()
    hx_in_w = ctypes.c_size_t()
    hx_in_h = ctypes.c_size_t()
    hx_in_xs = array("d", [10.0, float("nan")])
    hx_in_ys = array("d", [4.0, 1.0])
    hx_in_ok = lib.xyg_hexbin_ingress(
        _ptr(hx_in_xs, ctypes.c_double),
        _ptr(hx_in_ys, ctypes.c_double),
        null_f64,
        2,
        16,
        0,
        0.0,
        0.0,
        0.0,
        0.0,
        0,
        ctypes.byref(hx_in_x0),
        ctypes.byref(hx_in_x1),
        ctypes.byref(hx_in_y0),
        ctypes.byref(hx_in_y1),
        ctypes.byref(hx_in_w),
        ctypes.byref(hx_in_h),
    )
    ok(
        hx_in_ok == 1
        and hx_in_w.value == 16
        and hx_in_h.value == 9
        and abs(hx_in_x0.value - 9.5) < 1e-12
        and abs(hx_in_y0.value - 3.8) < 1e-12,
        "hexbin ingress auto domain and aspect",
    )
    hx_ring_n = lib.xyg_hexbin_ring(6.0, 12.0, null_f64, null_f64, 0)
    hx_rx = array("d", [0.0]) * 6
    hx_ry = array("d", [0.0]) * 6
    hx_ring_filled = lib.xyg_hexbin_ring(
        6.0,
        12.0,
        _ptr(hx_rx, ctypes.c_double),
        _ptr(hx_ry, ctypes.c_double),
        6,
    )
    ok(
        hx_ring_n == 6
        and hx_ring_filled == 6
        and abs(hx_rx[0] - 0.0) < 1e-15
        and abs(hx_ry[0] + 4.0) < 1e-15
        and abs(hx_rx[1] - 3.0) < 1e-15
        and abs(hx_ry[1] + 2.0) < 1e-15,
        "hexbin ring scale",
    )
    ok(
        lib.xyg_hexbin_ring(float("nan"), 1.0, null_f64, null_f64, 0) == size_max,
        "hexbin ring nonfinite",
    )

    # wind_rose_bins: three bearings into a 4-sector rose, one speed band.
    wr_dir = array("d", [0.0, 0.0, 90.0])
    wr_spd = array("d", [1.0, 1.0, 1.0])
    wr_edges_in = array("d", [2.0])
    wr_edges = array("d", [0.0]) * 4
    wr_centres = array("d", [0.0]) * 4
    wr_counts = array("d", [0.0]) * 4
    wr_n_obs = ctypes.c_size_t()
    wr_n = lib.xyg_wind_rose_bins(
        _ptr(wr_dir, ctypes.c_double),
        _ptr(wr_spd, ctypes.c_double),
        len(wr_dir),
        4,
        _ptr(wr_edges_in, ctypes.c_double),
        len(wr_edges_in),
        _ptr(wr_edges, ctypes.c_double),
        len(wr_edges),
        _ptr(wr_centres, ctypes.c_double),
        _ptr(wr_counts, ctypes.c_double),
        len(wr_counts),
        ctypes.byref(wr_n_obs),
    )
    ok(
        wr_n == 1
        and wr_n_obs.value == 3
        and list(wr_centres) == [0.0, 90.0, 180.0, 270.0]
        and list(wr_counts) == [2.0, 1.0, 0.0, 0.0],
        "wind_rose_bins centred sectors",
    )

    # contourf_densify: 2×2 field densifies to at least 256 on each axis.
    cf_z = array("d", [0.0, 1.0, 2.0, 3.0])
    cf_x = array("d", [0.0, 1.0])
    cf_y = array("d", [0.0, 1.0])
    cf_out_rows = 256
    cf_out_cols = 256
    cf_out_z = array("d", [0.0]) * (cf_out_rows * cf_out_cols)
    cf_out_x = array("d", [0.0]) * cf_out_cols
    cf_out_y = array("d", [0.0]) * cf_out_rows
    cf_rows = ctypes.c_size_t()
    cf_cols = ctypes.c_size_t()
    ok(
        lib.xyg_contourf_densify(
            _ptr(cf_z, ctypes.c_double),
            2,
            2,
            _ptr(cf_x, ctypes.c_double),
            _ptr(cf_y, ctypes.c_double),
            _ptr(cf_out_z, ctypes.c_double),
            _ptr(cf_out_x, ctypes.c_double),
            _ptr(cf_out_y, ctypes.c_double),
            len(cf_out_z),
            len(cf_out_x),
            len(cf_out_y),
            ctypes.byref(cf_rows),
            ctypes.byref(cf_cols),
        )
        == 1
        and cf_rows.value == 256
        and cf_cols.value == 256
        and abs(cf_out_z[0] - 0.0) < 1e-12
        and abs(cf_out_z[256 * 256 - 1] - 3.0) < 1e-12,
        "contourf_densify 2x2",
    )

    # bar_stack: two series grouped over two categories, width 0.8.
    bs_pos = array("d", [0.0, 1.0])
    bs_vals = array("d", [1.0, 2.0, 3.0, 4.0])
    bs_width = array("d", [0.8])
    bs_base = array("d", [0.0])
    bs_x0 = array("d", [0.0]) * 4
    bs_x1 = array("d", [0.0]) * 4
    bs_y0 = array("d", [0.0]) * 4
    bs_y1 = array("d", [0.0]) * 4
    ok(
        lib.xyg_bar_stack(
            _ptr(bs_pos, ctypes.c_double),
            2,
            _ptr(bs_vals, ctypes.c_double),
            2,
            _ptr(bs_width, ctypes.c_double),
            1,
            _ptr(bs_base, ctypes.c_double),
            1,
            0,
            0,
            _ptr(bs_x0, ctypes.c_double),
            _ptr(bs_x1, ctypes.c_double),
            _ptr(bs_y0, ctypes.c_double),
            _ptr(bs_y1, ctypes.c_double),
        )
        == 1
        and abs(bs_x0[0] + 0.4) < 1e-12
        and abs(bs_x1[0]) < 1e-12
        and list(bs_y1) == [1.0, 2.0, 3.0, 4.0],
        "bar_stack grouped",
    )

    # contourf_bands: one-masked-corner cell → 3 triangles.
    cb_z = array("d", [float("nan"), 1.0, 0.0, 0.0])
    cb_x = array("d", [0.0, 1.0])
    cb_y = array("d", [0.0, 1.0])
    cb_edges = array("d", [-1.0, 0.5, 2.0])
    cb_need = lib.xyg_contourf_bands(
        _ptr(cb_z, ctypes.c_double),
        2,
        2,
        _ptr(cb_x, ctypes.c_double),
        _ptr(cb_y, ctypes.c_double),
        _ptr(cb_edges, ctypes.c_double),
        3,
        0,
        0,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        0,
    )
    ok(cb_need == 3, "contourf_bands count query")

    # normalize_f32: clamp finite values, route non-finite values by mode.
    nx = array("d", [-1.0, 0.0, 5.0, 10.0, 11.0, float("nan"), float("inf")])
    norm = array("f", [0.0]) * len(nx)
    lib.xyg_normalize_f32(
        _ptr(nx, ctypes.c_double),
        len(nx),
        0.0,
        10.0,
        0,
        _ptr(norm, ctypes.c_float),
    )
    ok(list(norm) == [0.0, 0.0, 0.5, 1.0, 1.0, 0.0, 0.0], "normalize zero mode")
    lib.xyg_normalize_f32(
        _ptr(nx, ctypes.c_double),
        len(nx),
        0.0,
        10.0,
        1,
        _ptr(norm, ctypes.c_float),
    )
    ok(math.isnan(norm[5]) and math.isnan(norm[6]), "normalize nan mode")

    # range_indices: canonical inclusive rectangular selection.
    rx = array("d", [0.0, 1.0, 2.0, 3.0, float("nan")])
    ry = array("d", [0.0, 1.5, 2.5, 4.0, 1.0])
    ridx = array("I", [0]) * len(rx)
    written = lib.xyg_range_indices(
        _ptr(rx, ctypes.c_double),
        _ptr(ry, ctypes.c_double),
        len(rx),
        1.0,
        3.0,
        1.0,
        3.0,
        _ptr(ridx, ctypes.c_uint32),
    )
    ok(written == 2 and list(ridx[:written]) == [1, 2], "range_indices")

    # local_log_density: per-point density stays normalized and hotspot wins.
    lx = array("d", [0.1, 0.1, 0.1, 0.9])
    ly = array("d", [0.1, 0.1, 0.1, 0.9])
    lout = array("f", [0.0]) * len(lx)
    got = lib.xyg_local_log_density(
        _ptr(lx, ctypes.c_double),
        _ptr(ly, ctypes.c_double),
        len(lx),
        0.0,
        1.0,
        0.0,
        1.0,
        2,
        2,
        _ptr(lout, ctypes.c_float),
    )
    ok(got == 1, "local_log_density ok flag")
    ok(0.0 <= min(lout) <= max(lout) <= 1.0, "local_log_density normalized")
    ok(lout[0] == lout[1] == lout[2] and lout[0] > lout[3], "local_log_density hotspot")

    # tile pyramid (§5 Tier 3): build → count → compose → free, plus stale
    # handle semantics, through the real ABI.
    n_p = 64
    px = array("d", [float(i % 8) + 0.5 for i in range(n_p)])
    py = array("d", [float(i // 8) + 0.5 for i in range(n_p)])
    lib.xyg_pyramid_build.restype = ctypes.c_uint64
    lib.xyg_pyramid_build.argtypes = [
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_size_t,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_uint32,
    ]
    lib.xyg_pyramid_append.restype = ctypes.c_int32
    lib.xyg_pyramid_append.argtypes = [
        ctypes.c_uint64,
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_size_t,
    ]
    lib.xyg_pyramid_count.restype = ctypes.c_int32
    lib.xyg_pyramid_count.argtypes = [
        ctypes.c_uint64,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.POINTER(ctypes.c_double),
    ]
    lib.xyg_pyramid_compose.restype = ctypes.c_int32
    lib.xyg_pyramid_compose.argtypes = [
        ctypes.c_uint64,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_size_t,
        ctypes.c_size_t,
        ctypes.c_size_t,  # max_upsample: cap on per-axis upsample before refusing
        ctypes.POINTER(ctypes.c_float),
    ]
    lib.xyg_pyramid_free.restype = ctypes.c_int32
    lib.xyg_pyramid_free.argtypes = [ctypes.c_uint64]
    handle = lib.xyg_pyramid_build(
        _ptr(px, ctypes.c_double), _ptr(py, ctypes.c_double), n_p, 0.0, 8.0, 0.0, 8.0, 8
    )
    ok(handle != 0, "pyramid build returns a handle")
    cnt = ctypes.c_double(0.0)
    ok(
        lib.xyg_pyramid_count(ctypes.c_uint64(handle), 0.0, 8.0, 0.0, 8.0, ctypes.byref(cnt)) == 1,
        "pyramid count ok",
    )
    ok(cnt.value == float(n_p), "pyramid count is exact on the full window")
    append_x = array("d", [1.5, 6.5])
    append_y = array("d", [1.5, 6.5])
    ok(
        lib.xyg_pyramid_append(
            ctypes.c_uint64(handle),
            _ptr(append_x, ctypes.c_double),
            _ptr(append_y, ctypes.c_double),
            len(append_x),
        )
        == 1,
        "pyramid append updates a stable domain",
    )
    ok(
        lib.xyg_pyramid_count(ctypes.c_uint64(handle), 0.0, 8.0, 0.0, 8.0, ctypes.byref(cnt)) == 1
        and cnt.value == float(n_p + len(append_x)),
        "pyramid append conserves the new total",
    )
    outside_x = array("d", [8.0])
    outside_y = array("d", [4.0])
    ok(
        lib.xyg_pyramid_append(
            ctypes.c_uint64(handle),
            _ptr(outside_x, ctypes.c_double),
            _ptr(outside_y, ctypes.c_double),
            1,
        )
        == 0,
        "pyramid append rejects domain growth",
    )
    grid_p = array("f", bytes(4 * 8 * 8))
    lvl = lib.xyg_pyramid_compose(
        ctypes.c_uint64(handle), 0.0, 8.0, 0.0, 8.0, 8, 8, 2, _ptr(grid_p, ctypes.c_float)
    )
    ok(lvl == 0, "full-window compose uses level 0")
    ok(sum(grid_p) == float(n_p + len(append_x)), "compose conserves the appended count")
    tiny = array("f", bytes(4 * 64 * 64))
    ok(
        lib.xyg_pyramid_compose(
            ctypes.c_uint64(handle), 3.0, 3.1, 3.0, 3.1, 64, 64, 2, _ptr(tiny, ctypes.c_float)
        )
        == -2,
        "outresolving window is refused at max_upsample=2, not faked",
    )
    ok(lib.xyg_pyramid_free(ctypes.c_uint64(handle)) == 1, "pyramid free")
    ok(lib.xyg_pyramid_free(ctypes.c_uint64(handle)) == 0, "double free is an error code")

    # Phase-4 tile store (roadmap D1-D7, ABI 73): spill -> fetch -> compose
    # golden vs the in-RAM pyramid, dirty-tile append, residency stats, and
    # handle lifecycle — all through the real ABI, MB-scale fixtures only.
    lib.xyg_pyramid_spill.restype = ctypes.c_uint64
    lib.xyg_pyramid_spill.argtypes = [ctypes.c_uint64]
    lib.xyg_tile_store_fetch.restype = ctypes.c_int32
    lib.xyg_tile_store_fetch.argtypes = [
        ctypes.c_uint64,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint16),
    ]
    lib.xyg_tile_store_compose.restype = ctypes.c_int32
    lib.xyg_tile_store_compose.argtypes = list(lib.xyg_pyramid_compose.argtypes)
    lib.xyg_tile_store_append.restype = ctypes.c_int32
    lib.xyg_tile_store_append.argtypes = list(lib.xyg_pyramid_append.argtypes)
    lib.xyg_tile_store_stats.restype = ctypes.c_int32
    lib.xyg_tile_store_stats.argtypes = [ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint64)]
    lib.xyg_tile_budget_set.restype = ctypes.c_int32
    lib.xyg_tile_budget_set.argtypes = [ctypes.c_uint64]
    lib.xyg_tile_store_free.restype = ctypes.c_int32
    lib.xyg_tile_store_free.argtypes = [ctypes.c_uint64]

    ok(lib.xyg_pyramid_spill(ctypes.c_uint64(handle)) == 0, "spill refuses a stale pyramid handle")
    # base 512 puts 2x2 tiles on the finest level, so multi-tile gather and
    # the zero-padded small-level slabs are both exercised (~3 MB spill file).
    pyr = lib.xyg_pyramid_build(
        _ptr(px, ctypes.c_double), _ptr(py, ctypes.c_double), n_p, 0.0, 8.0, 0.0, 8.0, 512
    )
    ok(pyr != 0, "tile-store fixture pyramid builds")
    ok(lib.xyg_tile_budget_set(0) == 1, "tile budget set (0 restores the 512 MiB default)")
    store = lib.xyg_pyramid_spill(ctypes.c_uint64(pyr))
    ok(store != 0, "pyramid spill returns a store handle")

    tile_counts = (ctypes.c_uint32 * (256 * 256))()
    spilled_total = 0
    for ty in range(2):
        for tx in range(2):
            ok(
                lib.xyg_tile_store_fetch(ctypes.c_uint64(store), 0, tx, ty, tile_counts, None) == 1,
                f"tile fetch (0, {tx}, {ty})",
            )
            spilled_total += sum(tile_counts)
    ok(spilled_total == n_p, "finest-level tiles conserve the total count")
    ok(
        lib.xyg_tile_store_fetch(ctypes.c_uint64(store), 0, 2, 0, tile_counts, None) == 0,
        "tile fetch refuses an out-of-range key",
    )
    tile_color = (ctypes.c_uint16 * (256 * 256 * 4))()
    ok(
        lib.xyg_tile_store_fetch(ctypes.c_uint64(store), 0, 0, 0, tile_counts, tile_color) == 0,
        "count-only store refuses a color-plane fetch",
    )

    grid_ram = array("f", bytes(4 * 64 * 64))
    grid_tiles = array("f", bytes(4 * 64 * 64))
    lvl_ram = lib.xyg_pyramid_compose(
        ctypes.c_uint64(pyr), 0.0, 8.0, 0.0, 8.0, 64, 64, 2, _ptr(grid_ram, ctypes.c_float)
    )
    lvl_tiles = lib.xyg_tile_store_compose(
        ctypes.c_uint64(store), 0.0, 8.0, 0.0, 8.0, 64, 64, 2, _ptr(grid_tiles, ctypes.c_float)
    )
    ok(lvl_tiles == lvl_ram >= 0, "tile compose picks the in-RAM level")
    ok(list(grid_tiles) == list(grid_ram), "tile compose is bit-identical to in-RAM compose")
    ok(
        lib.xyg_tile_store_compose(
            ctypes.c_uint64(store), 3.0, 3.001, 3.0, 3.001, 64, 64, 2, _ptr(tiny, ctypes.c_float)
        )
        == -2,
        "outresolving window is refused by the tile store too",
    )

    # Count-only dirty-tile append (D4): mirror the batch into the pyramid
    # and the store; composed grids must stay identical.
    ok(
        lib.xyg_tile_store_append(
            ctypes.c_uint64(store),
            _ptr(append_x, ctypes.c_double),
            _ptr(append_y, ctypes.c_double),
            len(append_x),
        )
        == 1,
        "tile store append updates a stable domain",
    )
    ok(
        lib.xyg_pyramid_append(
            ctypes.c_uint64(pyr),
            _ptr(append_x, ctypes.c_double),
            _ptr(append_y, ctypes.c_double),
            len(append_x),
        )
        == 1,
        "fixture pyramid mirrors the appended batch",
    )
    ok(
        lib.xyg_tile_store_append(
            ctypes.c_uint64(store),
            _ptr(outside_x, ctypes.c_double),
            _ptr(outside_y, ctypes.c_double),
            1,
        )
        == 0,
        "tile store append rejects domain growth (caller invalidates)",
    )
    lvl_ram = lib.xyg_pyramid_compose(
        ctypes.c_uint64(pyr), 0.0, 8.0, 0.0, 8.0, 64, 64, 2, _ptr(grid_ram, ctypes.c_float)
    )
    lvl_tiles = lib.xyg_tile_store_compose(
        ctypes.c_uint64(store), 0.0, 8.0, 0.0, 8.0, 64, 64, 2, _ptr(grid_tiles, ctypes.c_float)
    )
    ok(
        lvl_tiles == lvl_ram and list(grid_tiles) == list(grid_ram),
        "appended tile compose equals the appended in-RAM compose",
    )
    ok(sum(grid_tiles) == float(n_p + len(append_x)), "tile compose conserves the appended count")

    stats = (ctypes.c_uint64 * 6)()
    ok(lib.xyg_tile_store_stats(ctypes.c_uint64(store), stats) == 1, "tile store stats ok")
    ok(stats[1] > 0, "stats record tile misses (disk faults)")
    ok(stats[3] > 0, "stats record spill-file bytes")
    ok(stats[4] == 512 * 2**20, "stats report the default 512 MiB budget")
    ok(stats[5] == 0, "a working set under budget records over_budget = 0")

    ok(lib.xyg_tile_store_free(ctypes.c_uint64(store)) == 1, "tile store free")
    ok(lib.xyg_tile_store_free(ctypes.c_uint64(store)) == 0, "tile store double free is an error")

    # Canonical stream store (engine doc §5): new → append → seal → copy →
    # zone maps match xyg_zone_maps over the concatenated column; pyramid
    # build/append can read through the handles; stale free is an error.
    seed = array("d", [1.0, 2.0, 3.0])
    tail = array("d", [4.0, float("nan"), 6.0])
    sh = lib.xyg_stream_new(_ptr(seed, ctypes.c_double), len(seed))
    ok(sh != 0, "stream_new returns a handle")
    ok(
        lib.xyg_stream_append(ctypes.c_uint64(sh), _ptr(tail, ctypes.c_double), len(tail)) == 1,
        "stream_append",
    )
    ok(lib.xyg_stream_seal(ctypes.c_uint64(sh)) == 1, "stream_seal")
    ok(int(lib.xyg_stream_len(ctypes.c_uint64(sh))) == 6, "stream_len after append")
    ok(int(lib.xyg_stream_capacity(ctypes.c_uint64(sh))) >= 6, "stream_capacity has slack")
    copied = array("d", [0.0] * 6)
    ok(
        lib.xyg_stream_copy(ctypes.c_uint64(sh), _ptr(copied, ctypes.c_double), 6) == 1,
        "stream_copy",
    )
    ok(list(copied)[:4] == [1.0, 2.0, 3.0, 4.0] and list(copied)[5:] == [6.0], "copied prefix")
    ok(copied[4] != copied[4], "copied NaN")
    n_chunks = lib.xyg_stream_zone_maps(
        ctypes.c_uint64(sh),
        (ctypes.c_double * 1)(),
        (ctypes.c_double * 1)(),
        (ctypes.c_uint64 * 1)(),
        (ctypes.c_uint64 * 1)(),
        (ctypes.c_double * 1)(),
        (ctypes.c_double * 1)(),
        (ctypes.c_double * 1)(),
        (ctypes.c_double * 1)(),
    )
    ok(n_chunks == 1, "sealed stream has one zone-map chunk")
    sy = lib.xyg_stream_new(_ptr(seed, ctypes.c_double), len(seed))
    ok(
        lib.xyg_stream_append(ctypes.c_uint64(sy), _ptr(tail, ctypes.c_double), len(tail)) == 1,
        "y stream_append",
    )
    ok(lib.xyg_stream_seal(ctypes.c_uint64(sy)) == 1, "y stream_seal")
    ph = lib.xyg_pyramid_build_from_stream(
        ctypes.c_uint64(sh), ctypes.c_uint64(sy), 0.0, 10.0, 0.0, 10.0, 8
    )
    ok(ph != 0, "pyramid_build_from_stream")
    extra = array("d", [5.0])
    ok(
        lib.xyg_stream_append(ctypes.c_uint64(sh), _ptr(extra, ctypes.c_double), 1) == 1,
        "stream append extra x",
    )
    ok(
        lib.xyg_stream_append(ctypes.c_uint64(sy), _ptr(extra, ctypes.c_double), 1) == 1,
        "stream append extra y",
    )
    ok(
        lib.xyg_pyramid_append_from_stream(
            ctypes.c_uint64(ph), ctypes.c_uint64(sh), ctypes.c_uint64(sy), 1
        )
        == 1,
        "pyramid_append_from_stream in-domain",
    )
    ok(lib.xyg_pyramid_free(ctypes.c_uint64(ph)) == 1, "free stream-backed pyramid")
    ok(lib.xyg_stream_free(ctypes.c_uint64(sh)) == 1, "stream_free")
    ok(lib.xyg_stream_free(ctypes.c_uint64(sh)) == 0, "stale stream free")
    ok(lib.xyg_stream_free(ctypes.c_uint64(sy)) == 1, "free y stream")
    empty = lib.xyg_stream_new(None, 0)
    ok(empty != 0, "empty stream_new")
    ok(lib.xyg_stream_free(ctypes.c_uint64(empty)) == 1, "free empty stream")

    # Geographic column descriptor ingest (#47).
    xy = (ctypes.c_double * 2)(-104.9903, 39.7392)
    validity = (ctypes.c_uint8 * 1)(1)
    err = ctypes.c_int32(0)
    gh = lib.xyg_geo_column_new(
        1,  # point
        4326,
        xy,
        2,
        validity,
        1,
        None,
        None,
        0,
        None,
        0,
        None,
        0,
        ctypes.byref(err),
    )
    ok(gh != 0 and err.value == 0, "geo_column_new point")
    ok(int(lib.xyg_geo_column_len(ctypes.c_uint64(gh))) == 1, "geo_column_len")
    ok(int(lib.xyg_geo_column_vertex_count(ctypes.c_uint64(gh))) == 1, "geo_column_vertex_count")
    ok(int(lib.xyg_geo_column_geometry(ctypes.c_uint64(gh))) == 1, "geo_column_geometry")
    ok(int(lib.xyg_geo_column_crs(ctypes.c_uint64(gh))) == 4326, "geo_column_crs")
    ok(lib.xyg_geo_column_free(ctypes.c_uint64(gh)) == 1, "geo_column_free")
    ok(lib.xyg_geo_column_free(ctypes.c_uint64(gh)) == 0, "stale geo_column_free")
    bad = lib.xyg_geo_column_new(
        1,
        9999,
        xy,
        2,
        validity,
        1,
        None,
        None,
        0,
        None,
        0,
        None,
        0,
        ctypes.byref(err),
    )
    ok(bad == 0 and err.value == -2, "geo_column_new rejects unsupported CRS")

    # Mean-color density (LOD doc §2): per-cell mean point color + count-only
    # alpha. One red and one blue point per side of a 2x1 grid, then both in
    # one cell: pure cells keep exact colors, the mixed cell averages in
    # linear light (255,0,0)+(0,0,255) -> (188,0,188).
    ZZ = ctypes.c_size_t
    DD = ctypes.c_double
    lib.xyg_bin_2d_mean_color.restype = ctypes.c_int32
    lib.xyg_bin_2d_mean_color.argtypes = [
        F64P,
        F64P,
        ZZ,
        U8P,
        U8P,
        U8P,
        ZZ,
        DD,
        DD,
        DD,
        DD,
        ZZ,
        ZZ,
        U8P,
    ]
    mc_x = array("d", [0.25, 0.75])
    mc_y = array("d", [0.5, 0.5])
    mc_idx = array("B", [0, 1])
    mc_lut = array("B", [255, 0, 0, 255, 0, 0, 255, 255])
    mc_out = array("B", bytes(2 * 1 * 4))
    ok(
        lib.xyg_bin_2d_mean_color(
            _ptr(mc_x, ctypes.c_double),
            _ptr(mc_y, ctypes.c_double),
            2,
            _ptr(mc_idx, ctypes.c_uint8),
            U8P(),
            _ptr(mc_lut, ctypes.c_uint8),
            2,
            0.0,
            1.0,
            0.0,
            1.0,
            2,
            1,
            _ptr(mc_out, ctypes.c_uint8),
        )
        == 1,
        "bin_2d_mean_color ok flag",
    )
    ok(list(mc_out[0:4]) == [255, 0, 0, 255], "mean color pure red cell")
    ok(list(mc_out[4:8]) == [0, 0, 255, 255], "mean color pure blue cell")
    mc_y_one = array("d", [0.5, 0.5])
    mc_x_one = array("d", [0.5, 0.5])
    mc_one = array("B", bytes(4))
    ok(
        lib.xyg_bin_2d_mean_color(
            _ptr(mc_x_one, ctypes.c_double),
            _ptr(mc_y_one, ctypes.c_double),
            2,
            _ptr(mc_idx, ctypes.c_uint8),
            U8P(),
            _ptr(mc_lut, ctypes.c_uint8),
            2,
            0.0,
            1.0,
            0.0,
            1.0,
            1,
            1,
            _ptr(mc_one, ctypes.c_uint8),
        )
        == 1
        and list(mc_one) == [188, 0, 188, 255],
        "mean color mixed cell averages in linear light",
    )
    ok(
        lib.xyg_bin_2d_mean_color(
            _ptr(mc_x_one, ctypes.c_double),
            _ptr(mc_y_one, ctypes.c_double),
            2,
            _ptr(mc_idx, ctypes.c_uint8),
            _ptr(mc_lut, ctypes.c_uint8),  # both sources set: invalid
            _ptr(mc_lut, ctypes.c_uint8),
            2,
            0.0,
            1.0,
            0.0,
            1.0,
            1,
            1,
            _ptr(mc_one, ctypes.c_uint8),
        )
        == 0,
        "mean color rejects ambiguous color source",
    )

    # Colored pyramid: same counts as the plain build, mean-color plane on
    # compose, appends refused (colors unknown; caller rebuilds lazily).
    lib.xyg_pyramid_build_color.restype = ctypes.c_uint64
    lib.xyg_pyramid_build_color.argtypes = [
        F64P,
        F64P,
        ZZ,
        U8P,
        U8P,
        U8P,
        ZZ,
        DD,
        DD,
        DD,
        DD,
        ctypes.c_uint32,
    ]
    lib.xyg_pyramid_compose_color.restype = ctypes.c_int32
    lib.xyg_pyramid_compose_color.argtypes = [
        ctypes.c_uint64,
        DD,
        DD,
        DD,
        DD,
        ZZ,
        ZZ,
        ZZ,  # max_upsample
        F32P,
        U8P,
    ]
    pc_idx = array("B", [1 if px[i] >= 4.0 else 0 for i in range(n_p)])
    chandle = lib.xyg_pyramid_build_color(
        _ptr(px, ctypes.c_double),
        _ptr(py, ctypes.c_double),
        n_p,
        _ptr(pc_idx, ctypes.c_uint8),
        U8P(),
        _ptr(mc_lut, ctypes.c_uint8),
        2,
        0.0,
        8.0,
        0.0,
        8.0,
        8,
    )
    ok(chandle != 0, "colored pyramid build returns a handle")
    cgrid = array("f", bytes(4 * 8 * 8))
    crgba = array("B", bytes(8 * 8 * 4))
    ok(
        lib.xyg_pyramid_compose_color(
            ctypes.c_uint64(chandle),
            0.0,
            8.0,
            0.0,
            8.0,
            8,
            8,
            2,
            _ptr(cgrid, ctypes.c_float),
            _ptr(crgba, ctypes.c_uint8),
        )
        == 0,
        "colored compose full window uses level 0",
    )
    ok(sum(cgrid) == float(n_p), "colored compose conserves the count")
    left_ok = all(
        list(crgba[(r * 8 + c) * 4 : (r * 8 + c) * 4 + 4]) == [255, 0, 0, 255]
        for r in range(8)
        for c in range(4)
    )
    right_ok = all(
        list(crgba[(r * 8 + c) * 4 : (r * 8 + c) * 4 + 4]) == [0, 0, 255, 255]
        for r in range(8)
        for c in range(4, 8)
    )
    ok(left_ok and right_ok, "colored compose keeps per-side colors exact")
    ok(
        lib.xyg_pyramid_append(
            ctypes.c_uint64(chandle),
            _ptr(append_x, ctypes.c_double),
            _ptr(append_y, ctypes.c_double),
            len(append_x),
        )
        == 0,
        "colored pyramid refuses appends (rebuilds lazily)",
    )
    ok(
        lib.xyg_pyramid_compose(
            ctypes.c_uint64(chandle), 0.0, 8.0, 0.0, 8.0, 8, 8, 2, _ptr(grid_p, ctypes.c_float)
        )
        == 0,
        "count-only compose still serves a colored pyramid",
    )
    ok(lib.xyg_pyramid_free(ctypes.c_uint64(chandle)) == 1, "colored pyramid free")

    # rasterize: caller-owned RGBA8 framebuffer; empty command buffer clears to
    # transparent, a malformed op is rejected, and a null out is refused.
    null_u8 = U8P()
    fb = array("B", [9]) * (2 * 2 * 4)
    ok(
        lib.xyg_rasterize(null_u8, 0, _ptr(fb, ctypes.c_uint8), 2, 2) == 1
        and all(v == 0 for v in fb),
        "rasterize empty buffer clears framebuffer",
    )
    bad = array("B", [1, 9, 9, 9, 9])  # FILL_POLY claiming a huge point count
    ok(
        lib.xyg_rasterize(_ptr(bad, ctypes.c_uint8), len(bad), _ptr(fb, ctypes.c_uint8), 2, 2) == 0,
        "rasterize rejects a malformed command buffer",
    )
    ok(lib.xyg_rasterize(null_u8, 0, null_u8, 2, 2) == 0, "rasterize refuses a null framebuffer")

    png = array("B", [0]) * 1024
    png_len = lib.xyg_rasterize_png(null_u8, 0, _ptr(png, ctypes.c_uint8), len(png), 2, 2)
    ok(
        png_len < len(png) and bytes(png[:8]) == b"\x89PNG\r\n\x1a\n",
        "fused raster-to-PNG emits a valid signature",
    )
    ok(
        lib.xyg_rasterize_data(null_u8, 0, null_u8, 0, _ptr(fb, ctypes.c_uint8), 2, 2) == 1,
        "external-arena rasterizer accepts an empty arena",
    )
    ok(
        lib.xyg_rasterize_data(null_u8, 0, null_u8, 1, _ptr(fb, ctypes.c_uint8), 2, 2) == 0,
        "external-arena rasterizer rejects a non-empty null arena",
    )
    png_len = lib.xyg_rasterize_png_data(
        null_u8, 0, null_u8, 0, _ptr(png, ctypes.c_uint8), len(png), 2, 2
    )
    ok(
        png_len < len(png) and bytes(png[:8]) == b"\x89PNG\r\n\x1a\n",
        "external-arena raster-to-PNG emits a valid signature",
    )
    ok(
        lib.xyg_rasterize_spans(null_u8, 0, None, None, 0, _ptr(fb, ctypes.c_uint8), 2, 2) == 1,
        "multi-span rasterizer accepts zero spans",
    )
    ok(
        lib.xyg_rasterize_spans(null_u8, 0, None, None, 1, _ptr(fb, ctypes.c_uint8), 2, 2) == 0,
        "multi-span rasterizer rejects missing descriptor arrays",
    )
    png_len = lib.xyg_rasterize_png_spans(
        null_u8, 0, None, None, 0, _ptr(png, ctypes.c_uint8), len(png), 2, 2
    )
    ok(
        png_len < len(png) and bytes(png[:8]) == b"\x89PNG\r\n\x1a\n",
        "multi-span raster-to-PNG emits a valid signature",
    )

    # NaN marks a missing cell; a real 0.0 now paints the colormap floor
    # (matplotlib semantics — see the visual-parity changelog entry).
    heat_values = array("d", [1.0 / 255.0, 128.0 / 255.0, 1.0, float("nan")])
    heat_stops = array("B", [0, 10, 20, 100, 110, 120])
    heat_rgba = array("B", [0]) * 16
    ok(
        lib.xyg_heatmap_rgba(
            _ptr(heat_values, ctypes.c_double),
            2,
            2,
            _ptr(heat_stops, ctypes.c_uint8),
            2,
            200,
            _ptr(heat_rgba, ctypes.c_uint8),
        )
        == 1
        and list(heat_rgba[:4]) == [100, 110, 120, 200]
        and heat_rgba[7] == 0,
        "native heatmap colormap maps, flips, and preserves missing alpha",
    )
    cmap_values = array("d", [0.0, 0.5, 1.0, float("nan")])
    cmap_stops = array("B", [0, 10, 20, 100, 110, 120])
    cmap_rgba = array("B", [0]) * 16
    ok(
        lib.xyg_colormap_rgba(
            _ptr(cmap_values, ctypes.c_double),
            2,
            2,
            _ptr(cmap_stops, ctypes.c_uint8),
            2,
            200,
            _ptr(cmap_rgba, ctypes.c_uint8),
        )
        == 1
        and list(cmap_rgba[:4]) == [100, 110, 120, 200]
        and cmap_rgba[7] == 0
        and list(cmap_rgba[12:16]) == [50, 60, 70, 200],
        "native direct colormap maps, flips, and preserves missing alpha",
    )
    interior = array("d", [0.5])
    interior_stops = array("B", [0, 0, 0, 254, 0, 0])
    colormap_pixel = array("B", [0]) * 4
    heatmap_pixel = array("B", [0]) * 4
    ok(
        lib.xyg_colormap_rgba(
            _ptr(interior, ctypes.c_double),
            1,
            1,
            _ptr(interior_stops, ctypes.c_uint8),
            2,
            255,
            _ptr(colormap_pixel, ctypes.c_uint8),
        )
        == 1
        and lib.xyg_heatmap_rgba(
            _ptr(interior, ctypes.c_double),
            1,
            1,
            _ptr(interior_stops, ctypes.c_uint8),
            2,
            255,
            _ptr(heatmap_pixel, ctypes.c_uint8),
        )
        == 1
        and colormap_pixel[0] == 127
        and heatmap_pixel[0] != colormap_pixel[0],
        "native direct colormap differs from heatmap remap at interior values",
    )
    density_codes = array("B", [0, 255, 128, 1])
    density_rgba = array("B", [0]) * 16
    ok(
        lib.xyg_density_rgba(
            _ptr(density_codes, ctypes.c_uint8),
            2,
            2,
            100.0,
            _ptr(heat_stops, ctypes.c_uint8),
            2,
            0.85,
            _ptr(density_rgba, ctypes.c_uint8),
        )
        == 1
        and density_rgba[3] > 0
        and density_rgba[11] == 0
        and density_rgba[12:16] == array("B", [100, 110, 120, 216]),
        "native density colormap maps, flips, and preserves empty alpha",
    )
    lut_t = array("d", [0.0, 1.0])
    lut_rgb = array("B", [0]) * 6
    ok(
        lib.xyg_colormap_lut(
            _ptr(lut_t, ctypes.c_double),
            2,
            _ptr(heat_stops, ctypes.c_uint8),
            2,
            _ptr(lut_rgb, ctypes.c_uint8),
        )
        == 1
        and lut_rgb[:3] == array("B", [0, 10, 20])
        and lut_rgb[3:] == array("B", [100, 110, 120]),
        "colormap_lut 1d samples",
    )
    lin_counts = array("d", [0.0, 100.0, 50.0, 0.0])
    lin_rgba = array("B", [0]) * 16
    ok(
        lib.xyg_density_rgba_linear(
            _ptr(lin_counts, ctypes.c_double),
            2,
            2,
            100.0,
            _ptr(heat_stops, ctypes.c_uint8),
            2,
            0.85,
            _ptr(lin_rgba, ctypes.c_uint8),
        )
        == 1
        and lin_rgba[11] == 0
        and lin_rgba[12:16] == array("B", [100, 110, 120, 216]),
        "density_rgba_linear maps, flips, and preserves empty alpha",
    )
    paint_in = array("d", [0.2, 0.3, 0.4, 0.8])
    paint_artist = array("d", [-1.0])
    paint_op = array("d", [0.5])
    paint_out = array("d", [0.0]) * 4
    ok(
        lib.xyg_paint_effective_rgba(
            _ptr(paint_in, ctypes.c_double),
            1,
            _ptr(paint_artist, ctypes.c_double),
            _ptr(paint_op, ctypes.c_double),
            1.0,
            _ptr(paint_out, ctypes.c_double),
        )
        == 1
        and abs(paint_out[3] - 0.4) < 1e-12,
        "paint_effective_rgba replace-then-multiply",
    )
    density = array("f", [0.0, 1.0, 10.0, 100.0])
    encoded = array("B", [0]) * len(density)
    density_max = ctypes.c_double(-1.0)
    ok(
        lib.xyg_density_log_u8(
            _ptr(density, ctypes.c_float),
            len(density),
            _ptr(encoded, ctypes.c_uint8),
            ctypes.byref(density_max),
        )
        == 1
        and density_max.value == 100.0
        and encoded[0] == 0
        and encoded[-1] == 255,
        "density log-u8 encoding preserves zero and maximum",
    )

    print(f"ABI smoke: {checks} checks passed against {_lib_name()}")


if __name__ == "__main__":
    main()
