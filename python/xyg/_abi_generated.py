"""Generated ctypes declarations. Do not edit; run scripts/gen_abi_manifest.py --write."""

from __future__ import annotations

import ctypes
import json
import os
from typing import Any, TypedDict

# fmt: off

class _AbiTraceMetadata(TypedDict):
    node_name: str
    arguments: list[tuple[int, str, str]]
    returns_size: bool


ABI_VERSION = 360
SIGNATURE_SHA256 = "9ab4cec3823938e163c1156677d8ceeac242cea52ab3c3e77be97642143a4827"
ABI_TRACE_METADATA: dict[str, _AbiTraceMetadata] = {'xyg_aligned_window': {'node_name': 'xyAlignedWindow', 'arguments': [(5, 'out_lo', 'pointer'), (6, 'out_hi', 'pointer')], 'returns_size': False}, 'xyg_argsort_stable': {'node_name': 'xyArgsortStable', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size'), (2, 'out', 'pointer'), (3, 'capacity', 'size')], 'returns_size': True}, 'xyg_array_is_categorical': {'node_name': 'xyArrayIsCategorical', 'arguments': [], 'returns_size': False}, 'xyg_arrow_end_decoration': {'node_name': 'xyArrowEndDecoration', 'arguments': [(4, 'style', 'pointer'), (5, 'style_len', 'size'), (7, 'out_x', 'pointer'), (8, 'out_y', 'pointer'), (9, 'capacity', 'size'), (10, 'out_kind', 'pointer')], 'returns_size': True}, 'xyg_arrow_geometry': {'node_name': 'xyArrowGeometry', 'arguments': [(4, 'style', 'pointer'), (5, 'style_len', 'size'), (6, 'out', 'pointer'), (7, 'out_len', 'size')], 'returns_size': False}, 'xyg_arrow_shaft_points': {'node_name': 'xyArrowShaftPoints', 'arguments': [(9, 'out_x', 'pointer'), (10, 'out_y', 'pointer'), (11, 'capacity', 'size')], 'returns_size': True}, 'xyg_arrow_shapes': {'node_name': 'xyArrowShapes', 'arguments': [(4, 'style', 'pointer'), (5, 'style_len', 'size'), (6, 'head_style', 'pointer'), (7, 'head_style_len', 'size'), (8, 'tail_style', 'pointer'), (9, 'tail_style_len', 'size'), (14, 'out_meta', 'pointer'), (15, 'meta_len', 'size'), (16, 'out_x', 'pointer'), (17, 'out_y', 'pointer'), (18, 'capacity', 'size')], 'returns_size': True}, 'xyg_arrow_style_pack': {'node_name': 'xyArrowStylePack', 'arguments': [(0, 'start_offset', 'pointer'), (1, 'start_offset_len', 'size'), (7, 'label_clear', 'pointer'), (8, 'label_clear_len', 'size'), (10, 'out', 'pointer'), (11, 'out_len', 'size')], 'returns_size': False}, 'xyg_arrow_taper_polygon': {'node_name': 'xyArrowTaperPolygon', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'n', 'size'), (5, 'out_x', 'pointer'), (6, 'out_y', 'pointer'), (7, 'capacity', 'size')], 'returns_size': True}, 'xyg_arrow_trim_polyline_end': {'node_name': 'xyArrowTrimPolylineEnd', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'n', 'size'), (4, 'out_x', 'pointer'), (5, 'out_y', 'pointer'), (6, 'capacity', 'size')], 'returns_size': True}, 'xyg_auto_domain': {'node_name': 'xyAutoDomain', 'arguments': [(3, 'out_lo', 'pointer'), (4, 'out_hi', 'pointer')], 'returns_size': False}, 'xyg_bar_stack': {'node_name': 'xyBarStack', 'arguments': [(0, 'pos', 'pointer'), (1, 'n_items', 'size'), (2, 'values', 'pointer'), (3, 'n_series', 'size'), (4, 'width', 'pointer'), (5, 'width_len', 'size'), (6, 'base', 'pointer'), (7, 'base_len', 'size'), (10, 'out_x0', 'pointer'), (11, 'out_x1', 'pointer'), (12, 'out_y0', 'pointer'), (13, 'out_y1', 'pointer')], 'returns_size': False}, 'xyg_bin_2d': {'node_name': 'xyBin2d', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size'), (7, 'w', 'size'), (8, 'h', 'size'), (9, 'out', 'pointer')], 'returns_size': False}, 'xyg_bin_2d_f32': {'node_name': 'xyBin2dF32', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size'), (7, 'w', 'size'), (8, 'h', 'size'), (9, 'out', 'pointer')], 'returns_size': False}, 'xyg_bin_2d_indices': {'node_name': 'xyBin2dIndices', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size'), (7, 'w', 'size'), (8, 'h', 'size'), (9, 'grid', 'pointer'), (10, 'idx', 'pointer')], 'returns_size': True}, 'xyg_bin_2d_mean_color': {'node_name': 'xyBin2dMeanColor', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size'), (3, 'idx', 'pointer'), (4, 'rgba', 'pointer'), (5, 'lut', 'pointer'), (6, 'lut_len', 'size'), (11, 'w', 'size'), (12, 'h', 'size'), (13, 'out', 'pointer'), (14, 'out_capacity', 'size')], 'returns_size': False}, 'xyg_bin_2d_sample_range': {'node_name': 'xyBin2dSampleRange', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size'), (7, 'w', 'size'), (8, 'h', 'size'), (11, 'grid', 'pointer'), (12, 'out', 'pointer'), (13, 'capacity', 'size')], 'returns_size': True}, 'xyg_bin_2d_stratified_sample_range_u8_counted': {'node_name': 'xyBin2dStratifiedSampleRangeU8Counted', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'groups', 'pointer'), (3, 'len', 'size'), (4, 'counts', 'pointer'), (5, 'n_groups', 'size'), (10, 'w', 'size'), (11, 'h', 'size'), (14, 'min_count', 'size'), (15, 'grid', 'pointer'), (16, 'out', 'pointer'), (17, 'capacity', 'size')], 'returns_size': True}, 'xyg_binned_ecdf': {'node_name': 'xyBinnedEcdf', 'arguments': [(0, 'values', 'pointer'), (1, 'len', 'size'), (6, 'out_x', 'pointer'), (7, 'out_cumulative', 'pointer'), (8, 'capacity', 'size')], 'returns_size': True}, 'xyg_box_geometry': {'node_name': 'xyBoxGeometry', 'arguments': [(0, 'values', 'pointer'), (1, 'values_len', 'size'), (2, 'offsets', 'pointer'), (3, 'offsets_len', 'size'), (4, 'centers', 'pointer'), (5, 'centers_len', 'size'), (9, 'out_n_outliers', 'pointer'), (10, 'active_groups', 'pointer'), (11, 'group_records', 'pointer'), (12, 'outlier_offsets', 'pointer'), (13, 'outlier_records', 'pointer'), (14, 'group_cap', 'size'), (15, 'outlier_cap', 'size')], 'returns_size': True}, 'xyg_box_stats': {'node_name': 'xyBoxStats', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size'), (2, 'out_stats', 'pointer'), (3, 'out_outliers', 'pointer'), (4, 'outliers_cap', 'size'), (5, 'out_n_outliers', 'pointer')], 'returns_size': False}, 'xyg_categorical_palette': {'node_name': 'xyCategoricalPalette', 'arguments': [(0, 'entry_lens', 'pointer'), (1, 'entry_texts', 'pointer'), (2, 'entry_texts_len', 'size'), (5, 'out_lens', 'pointer'), (6, 'out_texts', 'pointer'), (7, 'out_texts_cap', 'size')], 'returns_size': True}, 'xyg_categorical_palette_map_resolve': {'node_name': 'xyCategoricalPaletteMapResolve', 'arguments': [(0, 'category_lens', 'pointer'), (1, 'category_texts', 'pointer'), (2, 'category_texts_len', 'size'), (4, 'map_key_lens', 'pointer'), (5, 'map_key_texts', 'pointer'), (6, 'map_key_texts_len', 'size'), (7, 'map_value_lens', 'pointer'), (8, 'map_value_texts', 'pointer'), (9, 'map_value_texts_len', 'size'), (11, 'default_lens', 'pointer'), (12, 'default_texts', 'pointer'), (13, 'default_texts_len', 'size'), (15, 'out_lens', 'pointer'), (16, 'out_texts', 'pointer'), (17, 'out_texts_cap', 'size'), (18, 'out_unmapped', 'pointer'), (19, 'out_map_exhausted', 'pointer')], 'returns_size': True}, 'xyg_category_code_width': {'node_name': 'xyCategoryCodeWidth', 'arguments': [], 'returns_size': False}, 'xyg_category_label_kind_from_probe': {'node_name': 'xyCategoryLabelKindFromProbe', 'arguments': [], 'returns_size': False}, 'xyg_category_label_kinds_from_probes': {'node_name': 'xyCategoryLabelKindsFromProbes', 'arguments': [(0, 'probes', 'pointer'), (1, 'n', 'size'), (2, 'out', 'pointer')], 'returns_size': False}, 'xyg_category_labels_packed': {'node_name': 'xyCategoryLabelsPacked', 'arguments': [(0, 'kinds', 'pointer'), (1, 'in_lens', 'pointer'), (2, 'in_texts', 'pointer'), (3, 'in_texts_len', 'size'), (4, 'n', 'size'), (5, 'out_lens', 'pointer'), (6, 'out_texts', 'pointer'), (7, 'out_texts_cap', 'size')], 'returns_size': True}, 'xyg_category_palette_rows': {'node_name': 'xyCategoryPaletteRows', 'arguments': [], 'returns_size': False}, 'xyg_chunked_columns_cancel_before': {'node_name': 'xyChunkedColumnsCancelBefore', 'arguments': [], 'returns_size': False}, 'xyg_chunked_columns_free': {'node_name': 'xyChunkedColumnsFree', 'arguments': [], 'returns_size': False}, 'xyg_chunked_columns_open': {'node_name': 'xyChunkedColumnsOpen', 'arguments': [(0, 'path', 'pointer'), (1, 'path_len', 'size')], 'returns_size': False}, 'xyg_chunked_columns_overview': {'node_name': 'xyChunkedColumnsOverview', 'arguments': [(1, 'max_points', 'size'), (2, 'out_rows', 'pointer'), (3, 'out_x', 'pointer'), (4, 'out_y', 'pointer'), (5, 'out_stats', 'pointer')], 'returns_size': True}, 'xyg_chunked_columns_read': {'node_name': 'xyChunkedColumnsRead', 'arguments': [(6, 'budget_bytes', 'size'), (8, 'out_x', 'pointer'), (9, 'out_y', 'pointer'), (10, 'capacity', 'size'), (11, 'out_stats', 'pointer')], 'returns_size': True}, 'xyg_chunked_columns_read_page': {'node_name': 'xyChunkedColumnsReadPage', 'arguments': [(6, 'budget_bytes', 'size'), (9, 'out_x', 'pointer'), (10, 'out_y', 'pointer'), (11, 'capacity', 'size'), (12, 'out_stats', 'pointer')], 'returns_size': True}, 'xyg_chunked_columns_rows': {'node_name': 'xyChunkedColumnsRows', 'arguments': [], 'returns_size': False}, 'xyg_clip_quantize_u8': {'node_name': 'xyClipQuantizeU8', 'arguments': [(0, 'values', 'pointer'), (1, 'values_len', 'size'), (2, 'out', 'pointer'), (3, 'out_len', 'size')], 'returns_size': False}, 'xyg_color_channel_direct_rgba_f64_categorical': {'node_name': 'xyColorChannelDirectRgbaF64Categorical', 'arguments': [(0, 'codes', 'pointer'), (1, 'n', 'size'), (2, 'entry_lens', 'pointer'), (3, 'entry_texts', 'pointer'), (4, 'entry_texts_len', 'size'), (6, 'out', 'pointer'), (7, 'out_cap', 'size')], 'returns_size': True}, 'xyg_color_channel_direct_rgba_f64_continuous': {'node_name': 'xyColorChannelDirectRgbaF64Continuous', 'arguments': [(0, 'values', 'pointer'), (1, 'n', 'size'), (4, 'stops', 'pointer'), (5, 'stop_count', 'size'), (6, 'out', 'pointer'), (7, 'out_cap', 'size')], 'returns_size': True}, 'xyg_colormap_custom_stops_resolve_gradient': {'node_name': 'xyColormapCustomStopsResolveGradient', 'arguments': [(0, 'css', 'pointer'), (1, 'css_len', 'size'), (2, 'out', 'pointer'), (3, 'out_cap', 'size')], 'returns_size': False}, 'xyg_colormap_custom_stops_resolve_list': {'node_name': 'xyColormapCustomStopsResolveList', 'arguments': [(0, 'css_lens', 'pointer'), (1, 'css_texts', 'pointer'), (2, 'css_texts_len', 'size'), (3, 'positions', 'pointer'), (4, 'n', 'size'), (5, 'out', 'pointer'), (6, 'out_cap', 'size')], 'returns_size': False}, 'xyg_colormap_is_builtin': {'node_name': 'xyColormapIsBuiltin', 'arguments': [(0, 'name', 'pointer'), (1, 'name_len', 'size')], 'returns_size': False}, 'xyg_colormap_lut': {'node_name': 'xyColormapLut', 'arguments': [(0, 't', 'pointer'), (1, 'n', 'size'), (2, 'stops', 'pointer'), (3, 'stop_count', 'size'), (4, 'out', 'pointer')], 'returns_size': False}, 'xyg_colormap_lut_rgba8': {'node_name': 'xyColormapLutRgba8', 'arguments': [(0, 'name', 'pointer'), (1, 'name_len', 'size'), (2, 'custom_stops', 'pointer'), (3, 'custom_stop_count', 'size'), (5, 'out_rgba', 'pointer'), (6, 'out_cap', 'size')], 'returns_size': False}, 'xyg_colormap_resolved_stops_admit': {'node_name': 'xyColormapResolvedStopsAdmit', 'arguments': [(0, 'stops', 'pointer'), (1, 'stop_count', 'size')], 'returns_size': False}, 'xyg_colormap_rgba': {'node_name': 'xyColormapRgba', 'arguments': [(0, 'raw', 'pointer'), (1, 'w', 'size'), (2, 'h', 'size'), (3, 'stops', 'pointer'), (4, 'stop_count', 'size'), (6, 'out', 'pointer'), (7, 'out_capacity', 'size')], 'returns_size': False}, 'xyg_colormap_rgba_canonical': {'node_name': 'xyColormapRgbaCanonical', 'arguments': [(0, 'raw', 'pointer'), (1, 'w', 'size'), (2, 'h', 'size'), (5, 'stops', 'pointer'), (6, 'stop_count', 'size'), (8, 'out', 'pointer'), (9, 'out_capacity', 'size')], 'returns_size': False}, 'xyg_colormap_stops': {'node_name': 'xyColormapStops', 'arguments': [(0, 'name', 'pointer'), (1, 'name_len', 'size'), (2, 'out', 'pointer'), (3, 'cap', 'size')], 'returns_size': False}, 'xyg_compat_colorbar_extra': {'node_name': 'xyCompatColorbarExtra', 'arguments': [(3, 'out_right', 'pointer'), (4, 'out_bottom', 'pointer')], 'returns_size': True}, 'xyg_compat_combine_plot': {'node_name': 'xyCompatCombinePlot', 'arguments': [(2, 'authored_padding', 'pointer'), (14, 'x_rooms_final', 'pointer'), (22, 'out', 'pointer')], 'returns_size': True}, 'xyg_compat_default_padding': {'node_name': 'xyCompatDefaultPadding', 'arguments': [(1, 'out_pad', 'pointer')], 'returns_size': True}, 'xyg_compat_is_compact': {'node_name': 'xyCompatIsCompact', 'arguments': [], 'returns_size': False}, 'xyg_compat_right_y_room': {'node_name': 'xyCompatRightYRoom', 'arguments': [(1, 'out_room', 'pointer')], 'returns_size': True}, 'xyg_compat_title_room': {'node_name': 'xyCompatTitleRoom', 'arguments': [(5, 'out_room', 'pointer')], 'returns_size': True}, 'xyg_compat_title_wrap_width': {'node_name': 'xyCompatTitleWrapWidth', 'arguments': [(3, 'out_width', 'pointer')], 'returns_size': True}, 'xyg_compat_x_axis_side_room': {'node_name': 'xyCompatXAxisSideRoom', 'arguments': [(3, 'out_room', 'pointer'), (4, 'out_measured_bottom', 'pointer')], 'returns_size': True}, 'xyg_continuous_domain': {'node_name': 'xyContinuousDomain', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size'), (2, 'out_lo', 'pointer'), (3, 'out_hi', 'pointer')], 'returns_size': False}, 'xyg_contour_levels': {'node_name': 'xyContourLevels', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size'), (3, 'out', 'pointer'), (4, 'capacity', 'size')], 'returns_size': True}, 'xyg_contourf_bands': {'node_name': 'xyContourfBands', 'arguments': [(0, 'z', 'pointer'), (1, 'rows', 'size'), (2, 'cols', 'size'), (3, 'xpos', 'pointer'), (4, 'ypos', 'pointer'), (5, 'edges', 'pointer'), (9, 'out_x0', 'pointer'), (10, 'out_y0', 'pointer'), (11, 'out_x1', 'pointer'), (12, 'out_y1', 'pointer'), (13, 'out_x2', 'pointer'), (14, 'out_y2', 'pointer'), (15, 'out_slots', 'pointer'), (16, 'capacity', 'size')], 'returns_size': True}, 'xyg_contourf_densify': {'node_name': 'xyContourfDensify', 'arguments': [(0, 'z', 'pointer'), (1, 'rows', 'size'), (2, 'cols', 'size'), (3, 'xpos', 'pointer'), (4, 'ypos', 'pointer'), (5, 'out_z', 'pointer'), (6, 'out_x', 'pointer'), (7, 'out_y', 'pointer'), (8, 'out_z_cap', 'size'), (9, 'out_x_cap', 'size'), (10, 'out_y_cap', 'size'), (11, 'out_rows', 'pointer'), (12, 'out_cols', 'pointer')], 'returns_size': False}, 'xyg_correlation': {'node_name': 'xyCorrelation', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size'), (5, 'out_lag', 'pointer'), (6, 'out_correlation', 'pointer')], 'returns_size': False}, 'xyg_css_check': {'node_name': 'xyCssCheck', 'arguments': [(1, 'prop', 'pointer'), (2, 'prop_len', 'size'), (3, 'value', 'pointer'), (4, 'value_len', 'size'), (5, 'out_rgba', 'pointer')], 'returns_size': False}, 'xyg_css_color_rgba': {'node_name': 'xyCssColorRgba', 'arguments': [(0, 'css', 'pointer'), (1, 'len', 'size'), (3, 'out_rgba', 'pointer')], 'returns_size': False}, 'xyg_css_is_functional': {'node_name': 'xyCssIsFunctional', 'arguments': [(0, 'css', 'pointer'), (1, 'len', 'size')], 'returns_size': False}, 'xyg_curve_flatten': {'node_name': 'xyCurveFlatten', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'n', 'size'), (4, 'out_x', 'pointer'), (5, 'out_y', 'pointer'), (6, 'capacity', 'size')], 'returns_size': True}, 'xyg_default_palette_rgba8': {'node_name': 'xyDefaultPaletteRgba8', 'arguments': [(0, 'out', 'pointer'), (1, 'out_cap', 'size')], 'returns_size': True}, 'xyg_default_palette_rows': {'node_name': 'xyDefaultPaletteRows', 'arguments': [], 'returns_size': True}, 'xyg_default_palette_utf8': {'node_name': 'xyDefaultPaletteUtf8', 'arguments': [(0, 'out', 'pointer'), (1, 'out_cap', 'size')], 'returns_size': True}, 'xyg_default_palette_version': {'node_name': 'xyDefaultPaletteVersion', 'arguments': [], 'returns_size': False}, 'xyg_delaunay_triangles': {'node_name': 'xyDelaunayTriangles', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size'), (3, 'out', 'pointer'), (4, 'capacity', 'size')], 'returns_size': True}, 'xyg_density_bin_coord_endpoints': {'node_name': 'xyDensityBinCoordEndpoints', 'arguments': [(10, 'out_x_c0', 'pointer'), (11, 'out_x_c1', 'pointer'), (12, 'out_y_c0', 'pointer'), (13, 'out_y_c1', 'pointer')], 'returns_size': False}, 'xyg_density_bin_window': {'node_name': 'xyDensityBinWindow', 'arguments': [(10, 'out', 'pointer')], 'returns_size': True}, 'xyg_density_categorical_color_wire_admit': {'node_name': 'xyDensityCategoricalColorWireAdmit', 'arguments': [], 'returns_size': False}, 'xyg_density_channels_dropped_compat': {'node_name': 'xyDensityChannelsDroppedCompat', 'arguments': [(0, 'dropped_count', 'size')], 'returns_size': False}, 'xyg_density_color_classify': {'node_name': 'xyDensityColorClassify', 'arguments': [(4, 'out_color_mode', 'pointer'), (5, 'out_categorical', 'pointer'), (6, 'out_compact_categorical', 'pointer'), (7, 'out_stratified_counts', 'pointer')], 'returns_size': False}, 'xyg_density_constant_color_wire_admit': {'node_name': 'xyDensityConstantColorWireAdmit', 'arguments': [(1, 'mode', 'pointer'), (2, 'mode_len', 'size')], 'returns_size': False}, 'xyg_density_dropped_channel_wire_admit': {'node_name': 'xyDensityDroppedChannelWireAdmit', 'arguments': [(0, 'channel', 'pointer'), (1, 'channel_len', 'size')], 'returns_size': False}, 'xyg_density_emit_meta': {'node_name': 'xyDensityEmitMeta', 'arguments': [(28, 'n_points', 'size'), (29, 'out', 'pointer')], 'returns_size': False}, 'xyg_density_format_binning': {'node_name': 'xyDensityFormatBinning', 'arguments': [(4, 'out', 'pointer'), (5, 'out_cap', 'size')], 'returns_size': True}, 'xyg_density_full_identity': {'node_name': 'xyDensityFullIdentity', 'arguments': [], 'returns_size': False}, 'xyg_density_grid_path': {'node_name': 'xyDensityGridPath', 'arguments': [], 'returns_size': False}, 'xyg_density_grid_path_identity_state': {'node_name': 'xyDensityGridPathIdentityState', 'arguments': [], 'returns_size': False}, 'xyg_density_log_u8': {'node_name': 'xyDensityLogU8', 'arguments': [(0, 'grid', 'pointer'), (1, 'len', 'size'), (2, 'out', 'pointer'), (3, 'out_max', 'pointer')], 'returns_size': False}, 'xyg_density_mean_color_rgba_wire_admit': {'node_name': 'xyDensityMeanColorRgbaWireAdmit', 'arguments': [], 'returns_size': False}, 'xyg_density_mean_color_wire_admit': {'node_name': 'xyDensityMeanColorWireAdmit', 'arguments': [(1, 'mode', 'pointer'), (2, 'mode_len', 'size')], 'returns_size': False}, 'xyg_density_overlay_omitted_wire': {'node_name': 'xyDensityOverlayOmittedWire', 'arguments': [(2, 'out', 'pointer'), (3, 'out_cap', 'size')], 'returns_size': True}, 'xyg_density_overlay_opacity': {'node_name': 'xyDensityOverlayOpacity', 'arguments': [(1, 'out', 'pointer')], 'returns_size': False}, 'xyg_density_pyramid_preflight': {'node_name': 'xyDensityPyramidPreflight', 'arguments': [(2, 'n_points', 'size'), (8, 'out', 'pointer')], 'returns_size': True}, 'xyg_density_reduction_kind': {'node_name': 'xyDensityReductionKind', 'arguments': [(0, 'binning', 'pointer'), (1, 'binning_len', 'size')], 'returns_size': False}, 'xyg_density_rgba': {'node_name': 'xyDensityRgba', 'arguments': [(0, 'encoded', 'pointer'), (1, 'w', 'size'), (2, 'h', 'size'), (4, 'stops', 'pointer'), (5, 'stop_count', 'size'), (7, 'out', 'pointer'), (8, 'out_capacity', 'size')], 'returns_size': False}, 'xyg_density_rgba_linear': {'node_name': 'xyDensityRgbaLinear', 'arguments': [(0, 'counts', 'pointer'), (1, 'w', 'size'), (2, 'h', 'size'), (4, 'stops', 'pointer'), (5, 'stop_count', 'size'), (7, 'out', 'pointer'), (8, 'out_capacity', 'size')], 'returns_size': False}, 'xyg_density_trace_color_classify': {'node_name': 'xyDensityTraceColorClassify', 'arguments': [(1, 'mode', 'pointer'), (2, 'mode_len', 'size'), (6, 'out_color_mode', 'pointer'), (7, 'out_categorical', 'pointer'), (8, 'out_compact_categorical', 'pointer'), (9, 'out_stratified_counts', 'pointer')], 'returns_size': False}, 'xyg_density_uses_channel_colormap': {'node_name': 'xyDensityUsesChannelColormap', 'arguments': [(1, 'mode', 'pointer'), (2, 'mode_len', 'size')], 'returns_size': False}, 'xyg_density_wasm_density_wire_kind': {'node_name': 'xyDensityWasmDensityWireKind', 'arguments': [(1, 'wasm_source_count', 'size')], 'returns_size': False}, 'xyg_density_wasm_eligible': {'node_name': 'xyDensityWasmEligible', 'arguments': [(6, 'n_points', 'size')], 'returns_size': False}, 'xyg_density_wasm_source_admit': {'node_name': 'xyDensityWasmSourceAdmit', 'arguments': [], 'returns_size': False}, 'xyg_direct_rgba_admit': {'node_name': 'xyDirectRgbaAdmit', 'arguments': [(0, 'values', 'pointer'), (1, 'n', 'size'), (3, 'out', 'pointer'), (4, 'capacity', 'size')], 'returns_size': True}, 'xyg_drill_decision': {'node_name': 'xyDrillDecision', 'arguments': [(4, 'out_exact', 'pointer')], 'returns_size': False}, 'xyg_encode_f32': {'node_name': 'xyEncodeF32', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size'), (4, 'out', 'pointer')], 'returns_size': False}, 'xyg_encode_jpeg': {'node_name': 'xyEncodeJpeg', 'arguments': [(0, 'pixels', 'pointer'), (1, 'n', 'size'), (2, 'width', 'size'), (3, 'height', 'size'), (6, 'out', 'pointer'), (7, 'out_cap', 'size')], 'returns_size': True}, 'xyg_encode_png': {'node_name': 'xyEncodePng', 'arguments': [(0, 'pixels', 'pointer'), (1, 'n', 'size'), (2, 'width', 'size'), (3, 'height', 'size'), (7, 'out', 'pointer'), (8, 'out_cap', 'size')], 'returns_size': True}, 'xyg_encode_webp': {'node_name': 'xyEncodeWebp', 'arguments': [(0, 'pixels', 'pointer'), (1, 'n', 'size'), (2, 'width', 'size'), (3, 'height', 'size'), (5, 'out', 'pointer'), (6, 'out_cap', 'size')], 'returns_size': True}, 'xyg_encoded_column_meta': {'node_name': 'xyEncodedColumnMeta', 'arguments': [(3, 'kind', 'pointer'), (4, 'kind_len', 'size'), (5, 'out', 'pointer'), (6, 'out_cap', 'size')], 'returns_size': False}, 'xyg_f32_safe_scale': {'node_name': 'xyF32SafeScale', 'arguments': [(3, 'out_scale', 'pointer')], 'returns_size': False}, 'xyg_factorize_display_labels': {'node_name': 'xyFactorizeDisplayLabels', 'arguments': [(0, 'label_lens', 'pointer'), (1, 'label_texts', 'pointer'), (2, 'label_texts_len', 'size'), (3, 'n', 'size'), (4, 'out_codes', 'pointer'), (5, 'out_codes_cap', 'size'), (6, 'out_code_width', 'pointer'), (7, 'out_category_lens', 'pointer'), (8, 'out_category_texts', 'pointer'), (9, 'out_category_texts_cap', 'size'), (10, 'category_lens_cap', 'size')], 'returns_size': True}, 'xyg_factorize_fixed': {'node_name': 'xyFactorizeFixed', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size'), (2, 'width', 'size'), (3, 'out_codes', 'pointer'), (4, 'out_unique_indices', 'pointer')], 'returns_size': True}, 'xyg_factorize_fixed_u8': {'node_name': 'xyFactorizeFixedU8', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size'), (2, 'width', 'size'), (3, 'out_codes', 'pointer'), (4, 'out_unique_indices', 'pointer'), (5, 'unique_capacity', 'size')], 'returns_size': True}, 'xyg_factorize_fixed_u8_counts': {'node_name': 'xyFactorizeFixedU8Counts', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size'), (2, 'width', 'size'), (3, 'out_codes', 'pointer'), (4, 'out_unique_indices', 'pointer'), (5, 'out_counts', 'pointer'), (6, 'unique_capacity', 'size')], 'returns_size': True}, 'xyg_factorize_unicode1_u8_counts': {'node_name': 'xyFactorizeUnicode1U8Counts', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size'), (3, 'out_codes', 'pointer'), (4, 'out_unique_indices', 'pointer'), (5, 'out_counts', 'pointer'), (6, 'unique_capacity', 'size')], 'returns_size': True}, 'xyg_factorize_use_native_fixed': {'node_name': 'xyFactorizeUseNativeFixed', 'arguments': [(0, 'data', 'pointer'), (1, 'n_rows', 'size'), (2, 'record_width', 'size')], 'returns_size': False}, 'xyg_factorize_use_native_probe': {'node_name': 'xyFactorizeUseNativeProbe', 'arguments': [(1, 'probe_len', 'size'), (2, 'record_width', 'size')], 'returns_size': False}, 'xyg_figure_autorange': {'node_name': 'xyFigureAutorange', 'arguments': [(0, 'input', 'pointer'), (1, 'len', 'size'), (2, 'out_lo', 'pointer'), (3, 'out_hi', 'pointer')], 'returns_size': False}, 'xyg_fold_codes_u8': {'node_name': 'xyFoldCodesU8', 'arguments': [(0, 'codes', 'pointer'), (1, 'n', 'size'), (3, 'out', 'pointer')], 'returns_size': False}, 'xyg_geo_column_crs': {'node_name': 'xyGeoColumnCrs', 'arguments': [], 'returns_size': False}, 'xyg_geo_column_free': {'node_name': 'xyGeoColumnFree', 'arguments': [], 'returns_size': False}, 'xyg_geo_column_geometry': {'node_name': 'xyGeoColumnGeometry', 'arguments': [], 'returns_size': False}, 'xyg_geo_column_len': {'node_name': 'xyGeoColumnLen', 'arguments': [], 'returns_size': True}, 'xyg_geo_column_new': {'node_name': 'xyGeoColumnNew', 'arguments': [(2, 'xy', 'pointer'), (3, 'xy_len', 'size'), (4, 'validity', 'pointer'), (5, 'validity_len', 'size'), (6, 'feature_ids', 'pointer'), (7, 'offsets0', 'pointer'), (8, 'offsets0_len', 'size'), (9, 'offsets1', 'pointer'), (10, 'offsets1_len', 'size'), (11, 'offsets2', 'pointer'), (12, 'offsets2_len', 'size'), (13, 'out_error', 'pointer')], 'returns_size': False}, 'xyg_geo_column_vertex_count': {'node_name': 'xyGeoColumnVertexCount', 'arguments': [], 'returns_size': True}, 'xyg_geometry_offset': {'node_name': 'xyGeometryOffset', 'arguments': [(3, 'out_offset', 'pointer')], 'returns_size': False}, 'xyg_graph_build_csr': {'node_name': 'xyGraphBuildCsr', 'arguments': [(2, 'sources', 'pointer'), (3, 'targets', 'pointer'), (5, 'out_offsets', 'pointer'), (6, 'out_neighbors', 'pointer'), (7, 'neighbors_cap', 'size'), (8, 'out_neighbor_len', 'pointer')], 'returns_size': False}, 'xyg_graph_build_render': {'node_name': 'xyGraphBuildRender', 'arguments': [(2, 'x', 'pointer'), (3, 'y', 'pointer'), (4, 'sources', 'pointer'), (5, 'targets', 'pointer'), (13, 'out_node_x', 'pointer'), (14, 'out_node_y', 'pointer'), (15, 'out_member_of', 'pointer'), (16, 'out_edge_sources', 'pointer'), (17, 'out_edge_targets', 'pointer'), (18, 'out_n_nodes', 'pointer'), (19, 'out_n_edges', 'pointer'), (20, 'out_tier', 'pointer'), (21, 'out_edges_kept', 'pointer')], 'returns_size': False}, 'xyg_graph_cluster_aggregate': {'node_name': 'xyGraphClusterAggregate', 'arguments': [(2, 'x', 'pointer'), (3, 'y', 'pointer'), (6, 'out_x', 'pointer'), (7, 'out_y', 'pointer'), (8, 'out_count', 'pointer'), (9, 'out_member_of', 'pointer'), (10, 'out_tier', 'pointer'), (11, 'out_edges_kept', 'pointer')], 'returns_size': False}, 'xyg_graph_compound_bounds': {'node_name': 'xyGraphCompoundBounds', 'arguments': [(0, 'n', 'size'), (1, 'x', 'pointer'), (2, 'y', 'pointer'), (3, 'parents', 'pointer'), (4, 'validity', 'pointer'), (5, 'parent_of', 'pointer'), (6, 'is_compound', 'pointer'), (7, 'xmin', 'pointer'), (8, 'xmax', 'pointer'), (9, 'ymin', 'pointer'), (10, 'ymax', 'pointer')], 'returns_size': False}, 'xyg_graph_compound_scene': {'node_name': 'xyGraphCompoundScene', 'arguments': [(0, 'descriptor', 'pointer'), (1, 'out', 'pointer'), (2, 'out_cap', 'size')], 'returns_size': True}, 'xyg_graph_compound_transition': {'node_name': 'xyGraphCompoundTransition', 'arguments': [(0, 'n', 'size'), (1, 'node_ids', 'pointer'), (2, 'parents', 'pointer'), (3, 'validity', 'pointer'), (4, 'collapsed', 'pointer'), (8, 'out', 'pointer'), (9, 'out_changed', 'pointer')], 'returns_size': False}, 'xyg_graph_edge_route_segments': {'node_name': 'xyGraphEdgeRouteSegments', 'arguments': [(2, 'x', 'pointer'), (3, 'y', 'pointer'), (4, 'sources', 'pointer'), (5, 'targets', 'pointer'), (10, 'out_x0', 'pointer'), (11, 'out_y0', 'pointer'), (12, 'out_x1', 'pointer'), (13, 'out_y1', 'pointer'), (14, 'out_edge_index', 'pointer'), (15, 'out_n_segments', 'pointer')], 'returns_size': False}, 'xyg_graph_force_create': {'node_name': 'xyGraphForceCreate', 'arguments': [(2, 'sources', 'pointer'), (3, 'targets', 'pointer'), (4, 'in_x', 'pointer'), (5, 'in_y', 'pointer'), (8, 'out_handle', 'pointer')], 'returns_size': False}, 'xyg_graph_force_create_cose': {'node_name': 'xyGraphForceCreateCose', 'arguments': [(0, 'descriptor', 'pointer'), (3, 'sources', 'pointer'), (4, 'targets', 'pointer'), (6, 'out_handle', 'pointer')], 'returns_size': False}, 'xyg_graph_force_destroy': {'node_name': 'xyGraphForceDestroy', 'arguments': [], 'returns_size': False}, 'xyg_graph_force_tick': {'node_name': 'xyGraphForceTick', 'arguments': [(3, 'out_x', 'pointer'), (4, 'out_y', 'pointer'), (5, 'out_alpha', 'pointer')], 'returns_size': False}, 'xyg_graph_label_accept': {'node_name': 'xyGraphLabelAccept', 'arguments': [(0, 'n', 'size'), (1, 'priorities', 'pointer'), (4, 'out', 'pointer'), (5, 'out_count', 'pointer')], 'returns_size': False}, 'xyg_graph_layout': {'node_name': 'xyGraphLayout', 'arguments': [(3, 'sources', 'pointer'), (4, 'targets', 'pointer'), (5, 'in_x', 'pointer'), (6, 'in_y', 'pointer'), (7, 'roots', 'pointer'), (10, 'out_x', 'pointer'), (11, 'out_y', 'pointer')], 'returns_size': False}, 'xyg_graph_lod_decision': {'node_name': 'xyGraphLodDecision', 'arguments': [(4, 'out_tier', 'pointer'), (5, 'out_edges_kept', 'pointer')], 'returns_size': False}, 'xyg_graph_projection_copy_edge_ids': {'node_name': 'xyGraphProjectionCopyEdgeIds', 'arguments': [(1, 'output', 'pointer'), (2, 'capacity', 'size')], 'returns_size': False}, 'xyg_graph_projection_copy_endpoints': {'node_name': 'xyGraphProjectionCopyEndpoints', 'arguments': [(1, 'out_sources', 'pointer'), (2, 'out_targets', 'pointer'), (3, 'capacity', 'size')], 'returns_size': False}, 'xyg_graph_projection_copy_node_ids': {'node_name': 'xyGraphProjectionCopyNodeIds', 'arguments': [(1, 'output', 'pointer'), (2, 'capacity', 'size')], 'returns_size': False}, 'xyg_graph_projection_copy_parents': {'node_name': 'xyGraphProjectionCopyParents', 'arguments': [(1, 'out_parents', 'pointer'), (2, 'out_validity', 'pointer'), (3, 'capacity', 'size')], 'returns_size': False}, 'xyg_graph_projection_counts': {'node_name': 'xyGraphProjectionCounts', 'arguments': [(1, 'out_nodes', 'pointer'), (2, 'out_edges', 'pointer'), (3, 'out_directed', 'pointer')], 'returns_size': False}, 'xyg_graph_projection_create': {'node_name': 'xyGraphProjectionCreate', 'arguments': [(0, 'descriptor', 'pointer'), (1, 'out_handle', 'pointer')], 'returns_size': False}, 'xyg_graph_projection_destroy': {'node_name': 'xyGraphProjectionDestroy', 'arguments': [], 'returns_size': False}, 'xyg_graph_sample_edges': {'node_name': 'xyGraphSampleEdges', 'arguments': [(2, 'out_indices', 'pointer')], 'returns_size': False}, 'xyg_graph_semantic_legend': {'node_name': 'xyGraphSemanticLegend', 'arguments': [(2, 'n', 'size'), (3, 'classes', 'pointer'), (4, 'epistemic', 'pointer'), (5, 'statuses', 'pointer'), (6, 'capacity', 'size'), (7, 'out_field', 'pointer'), (8, 'out_value', 'pointer'), (9, 'out_rgba', 'pointer'), (10, 'out_shape', 'pointer'), (11, 'out_count', 'pointer')], 'returns_size': False}, 'xyg_graph_semantic_style_resolve': {'node_name': 'xyGraphSemanticStyleResolve', 'arguments': [(2, 'n', 'size'), (3, 'classes', 'pointer'), (4, 'epistemic', 'pointer'), (5, 'statuses', 'pointer'), (6, 'metric', 'pointer'), (7, 'flags', 'pointer'), (9, 'fill_rgba', 'pointer'), (10, 'stroke_rgba', 'pointer'), (11, 'halo_rgba', 'pointer'), (12, 'size', 'pointer'), (13, 'width', 'pointer'), (14, 'opacity', 'pointer'), (15, 'shape', 'pointer'), (16, 'dash', 'pointer'), (17, 'arrow', 'pointer'), (18, 'state', 'pointer'), (19, 'out_domain_lo', 'pointer'), (20, 'out_domain_hi', 'pointer')], 'returns_size': False}, 'xyg_graph_visual_state_resolve': {'node_name': 'xyGraphVisualStateResolve', 'arguments': [(0, 'n', 'size'), (1, 'flags', 'pointer'), (2, 'out', 'pointer')], 'returns_size': False}, 'xyg_hash_row_ids': {'node_name': 'xyHashRowIds', 'arguments': [(0, 'ids', 'pointer'), (1, 'len', 'size'), (3, 'out', 'pointer')], 'returns_size': False}, 'xyg_heatmap_rgba': {'node_name': 'xyHeatmapRgba', 'arguments': [(0, 'raw', 'pointer'), (1, 'w', 'size'), (2, 'h', 'size'), (3, 'stops', 'pointer'), (4, 'stop_count', 'size'), (6, 'out', 'pointer'), (7, 'out_capacity', 'size')], 'returns_size': False}, 'xyg_hexbin': {'node_name': 'xyHexbin', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'c', 'pointer'), (3, 'len', 'size'), (4, 'grid_w', 'size'), (5, 'grid_h', 'size'), (13, 'out_cx', 'pointer'), (14, 'out_cy', 'pointer'), (15, 'out_metric', 'pointer'), (16, 'out_counts', 'pointer'), (17, 'capacity', 'size'), (18, 'out_dx', 'pointer'), (19, 'out_dy', 'pointer')], 'returns_size': True}, 'xyg_hexbin_groups': {'node_name': 'xyHexbinGroups', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'c', 'pointer'), (3, 'len', 'size'), (4, 'grid_w', 'size'), (5, 'grid_h', 'size'), (12, 'out_cx', 'pointer'), (13, 'out_cy', 'pointer'), (14, 'out_counts', 'pointer'), (15, 'out_starts', 'pointer'), (16, 'out_lens', 'pointer'), (17, 'cell_capacity', 'size'), (18, 'out_indices', 'pointer'), (19, 'index_capacity', 'size'), (20, 'out_n_indices', 'pointer'), (21, 'out_dx', 'pointer'), (22, 'out_dy', 'pointer')], 'returns_size': True}, 'xyg_hexbin_ingress': {'node_name': 'xyHexbinIngress', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'c', 'pointer'), (3, 'len', 'size'), (4, 'grid_w', 'size'), (5, 'grid_h', 'size'), (11, 'out_x0', 'pointer'), (12, 'out_x1', 'pointer'), (13, 'out_y0', 'pointer'), (14, 'out_y1', 'pointer'), (15, 'out_grid_w', 'pointer'), (16, 'out_grid_h', 'pointer')], 'returns_size': False}, 'xyg_hexbin_ring': {'node_name': 'xyHexbinRing', 'arguments': [(2, 'out_x', 'pointer'), (3, 'out_y', 'pointer'), (4, 'capacity', 'size')], 'returns_size': True}, 'xyg_histogram2d': {'node_name': 'xyHistogram2d', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'weights', 'pointer'), (3, 'len', 'size'), (4, 'x_edges', 'pointer'), (5, 'x_edge_len', 'size'), (6, 'y_edges', 'pointer'), (7, 'y_edge_len', 'size'), (8, 'out', 'pointer')], 'returns_size': False}, 'xyg_histogram_bins': {'node_name': 'xyHistogramBins', 'arguments': [(0, 'values', 'pointer'), (1, 'len', 'size'), (2, 'edges', 'pointer'), (3, 'edge_len', 'size'), (6, 'out_counts', 'pointer')], 'returns_size': True}, 'xyg_histogram_edges': {'node_name': 'xyHistogramEdges', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size'), (6, 'out_edges', 'pointer'), (7, 'capacity', 'size')], 'returns_size': True}, 'xyg_histogram_mark_edges': {'node_name': 'xyHistogramMarkEdges', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size'), (7, 'out_edges', 'pointer'), (8, 'capacity', 'size')], 'returns_size': True}, 'xyg_histogram_uniform': {'node_name': 'xyHistogramUniform', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size'), (6, 'out_counts', 'pointer')], 'returns_size': True}, 'xyg_indexed_triangles': {'node_name': 'xyIndexedTriangles', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'vertex_count', 'size'), (3, 'triangles', 'pointer'), (4, 'face_count', 'size'), (5, 'values', 'pointer'), (6, 'value_len', 'size'), (8, 'out_x0', 'pointer'), (9, 'out_y0', 'pointer'), (10, 'out_x1', 'pointer'), (11, 'out_y1', 'pointer'), (12, 'out_x2', 'pointer'), (13, 'out_y2', 'pointer'), (14, 'out_values', 'pointer')], 'returns_size': True}, 'xyg_is_sorted': {'node_name': 'xyIsSorted', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size')], 'returns_size': False}, 'xyg_label_codes_first_seen': {'node_name': 'xyLabelCodesFirstSeen', 'arguments': [(0, 'label_lens', 'pointer'), (1, 'label_texts', 'pointer'), (2, 'label_texts_len', 'size'), (3, 'n', 'size'), (4, 'out_codes', 'pointer'), (5, 'out_codes_cap', 'size'), (6, 'out_code_width', 'pointer'), (7, 'out_category_lens', 'pointer'), (8, 'out_category_texts', 'pointer'), (9, 'out_category_texts_cap', 'size'), (10, 'category_lens_cap', 'size')], 'returns_size': True}, 'xyg_legend_best_loc': {'node_name': 'xyLegendBestLoc', 'arguments': [(0, 'xs', 'pointer'), (1, 'ys', 'pointer'), (2, 'n', 'size'), (3, 'starts', 'pointer'), (4, 'n_series', 'size'), (5, 'label_lens', 'pointer')], 'returns_size': False}, 'xyg_legend_box_layout': {'node_name': 'xyLegendBoxLayout', 'arguments': [(4, 'label_lens', 'pointer'), (5, 'labels', 'pointer'), (6, 'labels_len', 'size'), (7, 'n', 'size'), (8, 'title', 'pointer'), (9, 'title_len', 'size'), (10, 'loc', 'pointer'), (11, 'loc_len', 'size'), (19, 'anchor', 'pointer'), (20, 'anchor_len', 'size'), (22, 'out_metrics', 'pointer'), (23, 'out_column_widths', 'pointer'), (24, 'out_column_offsets', 'pointer'), (25, 'col_cap', 'size'), (26, 'out_name_lens', 'pointer'), (27, 'out_names', 'pointer'), (28, 'names_cap', 'size'), (29, 'out_title', 'pointer'), (30, 'title_cap', 'size'), (31, 'out_title_len', 'pointer')], 'returns_size': True}, 'xyg_legend_normalize': {'node_name': 'xyLegendNormalize', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size'), (13, 'out_x', 'pointer'), (14, 'out_y', 'pointer'), (15, 'capacity', 'size')], 'returns_size': True}, 'xyg_literal_color_rgba_f64': {'node_name': 'xyLiteralColorRgbaF64', 'arguments': [(0, 'entry_lens', 'pointer'), (1, 'entry_texts', 'pointer'), (2, 'entry_texts_len', 'size'), (4, 'out_rgba', 'pointer'), (5, 'out_cap', 'size')], 'returns_size': True}, 'xyg_local_log_density': {'node_name': 'xyLocalLogDensity', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size'), (7, 'w', 'size'), (8, 'h', 'size'), (9, 'out', 'pointer')], 'returns_size': False}, 'xyg_lod_grid_shape': {'node_name': 'xyLodGridShape', 'arguments': [(0, 'px_w', 'size'), (1, 'px_h', 'size'), (4, 'out_w', 'pointer'), (5, 'out_h', 'pointer')], 'returns_size': False}, 'xyg_lod_plan': {'node_name': 'xyLodPlan', 'arguments': [(4, 'px_w', 'size'), (5, 'px_h', 'size'), (7, 'out_exact', 'pointer'), (8, 'out_mode', 'pointer'), (9, 'out_grid_w', 'pointer'), (10, 'out_grid_h', 'pointer')], 'returns_size': False}, 'xyg_m4_indices': {'node_name': 'xyM4Indices', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size'), (6, 'out', 'pointer')], 'returns_size': True}, 'xyg_m4_points': {'node_name': 'xyM4Points', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size'), (6, 'out_x', 'pointer'), (7, 'out_y', 'pointer')], 'returns_size': True}, 'xyg_marching_squares': {'node_name': 'xyMarchingSquares', 'arguments': [(0, 'z', 'pointer'), (1, 'rows', 'size'), (2, 'cols', 'size'), (3, 'x_coords', 'pointer'), (4, 'y_coords', 'pointer'), (5, 'levels', 'pointer'), (8, 'out_x0', 'pointer'), (9, 'out_x1', 'pointer'), (10, 'out_y0', 'pointer'), (11, 'out_y1', 'pointer'), (12, 'out_levels', 'pointer'), (13, 'capacity', 'size')], 'returns_size': True}, 'xyg_marching_triangles': {'node_name': 'xyMarchingTriangles', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'z', 'pointer'), (3, 'vertex_count', 'size'), (4, 'triangles', 'pointer'), (5, 'face_count', 'size'), (6, 'levels', 'pointer'), (7, 'level_count', 'size'), (8, 'out_x0', 'pointer'), (9, 'out_x1', 'pointer'), (10, 'out_y0', 'pointer'), (11, 'out_y1', 'pointer'), (12, 'out_levels', 'pointer'), (13, 'capacity', 'size')], 'returns_size': True}, 'xyg_marker_path_scale': {'node_name': 'xyMarkerPathScale', 'arguments': [(3, 'x', 'pointer'), (4, 'y', 'pointer'), (5, 'n', 'size'), (6, 'out_x', 'pointer'), (7, 'out_y', 'pointer'), (8, 'capacity', 'size')], 'returns_size': True}, 'xyg_min_max': {'node_name': 'xyMinMax', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size'), (2, 'out_min', 'pointer'), (3, 'out_max', 'pointer')], 'returns_size': False}, 'xyg_monotone_tangents': {'node_name': 'xyMonotoneTangents', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'n', 'size'), (3, 'out_m', 'pointer'), (4, 'capacity', 'size')], 'returns_size': True}, 'xyg_normalize_f32': {'node_name': 'xyNormalizeF32', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size'), (5, 'out', 'pointer')], 'returns_size': False}, 'xyg_normalize_window': {'node_name': 'xyNormalizeWindow', 'arguments': [(5, 'out', 'pointer')], 'returns_size': False}, 'xyg_object_row_real_numeric_tag_from_probe': {'node_name': 'xyObjectRowRealNumericTagFromProbe', 'arguments': [], 'returns_size': False}, 'xyg_object_row_real_numeric_tags_from_probes': {'node_name': 'xyObjectRowRealNumericTagsFromProbes', 'arguments': [(0, 'probes', 'pointer'), (1, 'n', 'size'), (2, 'out', 'pointer')], 'returns_size': False}, 'xyg_object_row_stringlike_tag_from_probe': {'node_name': 'xyObjectRowStringlikeTagFromProbe', 'arguments': [], 'returns_size': False}, 'xyg_object_row_stringlike_tags_from_probes': {'node_name': 'xyObjectRowStringlikeTagsFromProbes', 'arguments': [(0, 'probes', 'pointer'), (1, 'n', 'size'), (2, 'out', 'pointer')], 'returns_size': False}, 'xyg_object_rows_all_real_numeric': {'node_name': 'xyObjectRowsAllRealNumeric', 'arguments': [(0, 'row_tags', 'pointer'), (1, 'n', 'size')], 'returns_size': False}, 'xyg_object_rows_all_stringlike': {'node_name': 'xyObjectRowsAllStringlike', 'arguments': [(0, 'row_tags', 'pointer'), (1, 'n', 'size')], 'returns_size': False}, 'xyg_paint_effective_rgba': {'node_name': 'xyPaintEffectiveRgba', 'arguments': [(0, 'intrinsic', 'pointer'), (1, 'n', 'size'), (2, 'artist_alpha', 'pointer'), (3, 'opacity', 'pointer'), (5, 'out', 'pointer')], 'returns_size': False}, 'xyg_palette_rows_rgba8': {'node_name': 'xyPaletteRowsRgba8', 'arguments': [(0, 'entry_lens', 'pointer'), (1, 'entry_texts', 'pointer'), (2, 'entry_texts_len', 'size'), (4, 'rows', 'size'), (5, 'out_rgba', 'pointer'), (6, 'out_cap', 'size'), (7, 'out_unresolved', 'pointer'), (8, 'out_entry_unresolved', 'pointer'), (9, 'entry_unresolved_cap', 'size')], 'returns_size': True}, 'xyg_payload_axis_spec_attach_plan': {'node_name': 'xyPayloadAxisSpecAttachPlan', 'arguments': [(2, 'out', 'pointer')], 'returns_size': False}, 'xyg_payload_bar_compact_admit': {'node_name': 'xyPayloadBarCompactAdmit', 'arguments': [(1, 'widths', 'pointer'), (3, 'value0', 'pointer'), (4, 'out_width', 'pointer'), (5, 'out_value0_const', 'pointer'), (6, 'out_has_value0_const', 'pointer'), (7, 'out_compact', 'pointer')], 'returns_size': False}, 'xyg_payload_bar_hist_emit_plan': {'node_name': 'xyPayloadBarHistEmitPlan', 'arguments': [(2, 'n_marks', 'size'), (7, 'out_emit_bar', 'pointer'), (8, 'out_tier_direct', 'pointer'), (9, 'out_n_marks', 'pointer'), (10, 'out_apply_palette_default', 'pointer'), (11, 'out_x_ship_scale', 'pointer'), (12, 'out_y_ship_scale', 'pointer'), (13, 'out_pos_ship_scale', 'pointer'), (14, 'out_value_ship_scale', 'pointer'), (15, 'out_value_axis', 'pointer'), (16, 'out_channel_slot', 'pointer'), (17, 'out_include_trace_styles', 'pointer'), (18, 'out_attach_transition', 'pointer')], 'returns_size': False}, 'xyg_payload_base_entry_plan': {'node_name': 'xyPayloadBaseEntryPlan', 'arguments': [(5, 'out_attach_animation', 'pointer'), (6, 'out_n_marks', 'pointer'), (7, 'out_apply_palette_default', 'pointer'), (8, 'out_x_ship_scale', 'pointer'), (9, 'out_y_ship_scale', 'pointer')], 'returns_size': False}, 'xyg_payload_build_plan': {'node_name': 'xyPayloadBuildPlan', 'arguments': [(1, 'wasm_source_count', 'size'), (22, 'out', 'pointer')], 'returns_size': False}, 'xyg_payload_channel_materialize': {'node_name': 'xyPayloadChannelMaterialize', 'arguments': [(8, 'sel', 'pointer'), (9, 'sel_len', 'size'), (10, 'values_f64', 'pointer'), (11, 'values_f64_len', 'size'), (12, 'values_u8', 'pointer'), (13, 'values_u8_len', 'size'), (14, 'out', 'pointer'), (15, 'out_cap', 'size'), (16, 'out_meta', 'pointer')], 'returns_size': False}, 'xyg_payload_channel_ship_plan': {'node_name': 'xyPayloadChannelShipPlan', 'arguments': [(1, 'include_trace_styles', 'size'), (6, 'out_n_channels', 'pointer'), (7, 'out_channels', 'pointer'), (8, 'capacity', 'size')], 'returns_size': False}, 'xyg_payload_channel_wire_encode': {'node_name': 'xyPayloadChannelWireEncode', 'arguments': [(5, 'out_buf_kind', 'pointer'), (6, 'out_transform', 'pointer'), (7, 'out_mark_dtype_u8', 'pointer'), (8, 'out_ship_palette', 'pointer'), (9, 'out_set_n', 'pointer')], 'returns_size': False}, 'xyg_payload_column_gather_materialize': {'node_name': 'xyPayloadColumnGatherMaterialize', 'arguments': [(0, 'sel', 'pointer'), (1, 'sel_len', 'size'), (2, 'columns', 'pointer'), (4, 'values', 'pointer'), (5, 'kinds', 'pointer'), (6, 'axis_scales', 'pointer'), (7, 'out', 'pointer'), (8, 'out_bytes', 'pointer'), (9, 'out_bytes_cap', 'size'), (10, 'out_bytes_len', 'pointer')], 'returns_size': False}, 'xyg_payload_column_ship_plan': {'node_name': 'xyPayloadColumnShipPlan', 'arguments': [(0, 'kind', 'pointer'), (1, 'kind_len', 'size'), (5, 'out_gather_policy', 'pointer'), (6, 'out_gather_include_color', 'pointer'), (7, 'out_n_columns', 'pointer'), (8, 'out_x_ship_scale', 'pointer'), (9, 'out_y_ship_scale', 'pointer'), (10, 'out_columns', 'pointer'), (11, 'capacity', 'size')], 'returns_size': False}, 'xyg_payload_density_grid_materialize': {'node_name': 'xyPayloadDensityGridMaterialize', 'arguments': [(0, 'input', 'pointer'), (1, 'x_raw', 'pointer'), (2, 'y_raw', 'pointer'), (3, 'bx', 'pointer'), (4, 'by', 'pointer'), (5, 'color_codes', 'pointer'), (6, 'color_counts', 'pointer'), (7, 'color_idx', 'pointer'), (8, 'color_rgba', 'pointer'), (9, 'color_lut', 'pointer'), (10, 'out_binning', 'pointer'), (11, 'out_encoded', 'pointer'), (12, 'out_rgba', 'pointer'), (13, 'out_sample_sel', 'pointer'), (14, 'out_visible_sel', 'pointer'), (15, 'out', 'pointer')], 'returns_size': False}, 'xyg_payload_density_grid_ship_plan': {'node_name': 'xyPayloadDensityGridShipPlan', 'arguments': [(5, 'overlay_wire_rows_exceed', 'size'), (8, 'out_n_buffers', 'pointer'), (9, 'out_buffers', 'pointer'), (10, 'buffer_capacity', 'size'), (11, 'out_n_attach', 'pointer'), (12, 'out_attach', 'pointer'), (13, 'attach_capacity', 'size')], 'returns_size': False}, 'xyg_payload_density_trace_emit_plan': {'node_name': 'xyPayloadDensityTraceEmitPlan', 'arguments': [(1, 'mode', 'pointer'), (2, 'mode_len', 'size'), (14, 'grid_w', 'size'), (15, 'grid_h', 'size'), (35, 'n_points', 'size'), (38, 'dropped_count', 'size'), (39, 'out', 'pointer')], 'returns_size': False}, 'xyg_payload_errorbar_indices': {'node_name': 'xyPayloadErrorbarIndices', 'arguments': [(1, 'n_points', 'size'), (3, 'out_keep_all', 'pointer'), (4, 'out', 'pointer'), (5, 'capacity', 'size')], 'returns_size': True}, 'xyg_payload_errorbar_role_keys': {'node_name': 'xyPayloadErrorbarRoleKeys', 'arguments': [(0, 'n_points', 'size'), (2, 'point_keys_lo', 'pointer'), (3, 'point_keys_hi', 'pointer'), (4, 'segment_sources', 'pointer'), (5, 'segment_roles', 'pointer'), (6, 'out_lo', 'pointer'), (7, 'out_hi', 'pointer'), (8, 'out_collision', 'pointer')], 'returns_size': True}, 'xyg_payload_errorbar_role_maps': {'node_name': 'xyPayloadErrorbarRoleMaps', 'arguments': [(1, 'n_points', 'size'), (2, 'out_sources', 'pointer'), (3, 'out_roles', 'pointer'), (4, 'out_applicable', 'pointer')], 'returns_size': False}, 'xyg_payload_even_indices': {'node_name': 'xyPayloadEvenIndices', 'arguments': [(0, 'n', 'size'), (1, 'count', 'size'), (2, 'out_keep_all', 'pointer'), (3, 'out', 'pointer'), (4, 'capacity', 'size')], 'returns_size': True}, 'xyg_payload_heatmap_emit_plan': {'node_name': 'xyPayloadHeatmapEmitPlan', 'arguments': [(1, 'grid_rows', 'size'), (2, 'grid_cols', 'size'), (5, 'out_path', 'pointer'), (6, 'out_tier_direct', 'pointer'), (7, 'out_n_marks', 'pointer'), (8, 'out_attach_color', 'pointer'), (9, 'out_borrow_canonical', 'pointer'), (10, 'out_attach_encoding', 'pointer'), (11, 'out_use_constant_colormap_fallback', 'pointer')], 'returns_size': False}, 'xyg_payload_m4_indices': {'node_name': 'xyPayloadM4Indices', 'arguments': [(0, 'n_points', 'size'), (2, 'x', 'pointer'), (3, 'y', 'pointer'), (4, 'n', 'size'), (8, 'bin_x', 'pointer'), (11, 'out_tier', 'pointer'), (12, 'out', 'pointer'), (13, 'capacity', 'size')], 'returns_size': True}, 'xyg_payload_mesh_emit_plan': {'node_name': 'xyPayloadMeshEmitPlan', 'arguments': [(0, 'n_marks', 'size'), (7, 'out_tier_direct', 'pointer'), (8, 'out_n_marks', 'pointer'), (9, 'out_apply_palette_default', 'pointer'), (10, 'out_x_ship_scale', 'pointer'), (11, 'out_y_ship_scale', 'pointer'), (12, 'out_channel_slot', 'pointer'), (13, 'out_include_trace_styles', 'pointer'), (14, 'out_attach_transition', 'pointer'), (15, 'out_attempt_gather', 'pointer'), (16, 'out_gather_include_color', 'pointer')], 'returns_size': False}, 'xyg_payload_nonxy_emit_plan': {'node_name': 'xyPayloadNonxyEmitPlan', 'arguments': [(1, 'n_marks', 'size'), (5, 'out_tier_direct', 'pointer'), (6, 'out_n_marks', 'pointer'), (7, 'out_apply_palette_default', 'pointer'), (8, 'out_x_ship_scale', 'pointer'), (9, 'out_y_ship_scale', 'pointer'), (10, 'out_channel_slot', 'pointer'), (11, 'out_include_trace_styles', 'pointer'), (12, 'out_attach_transition', 'pointer')], 'returns_size': False}, 'xyg_payload_ribbon_emit_plan': {'node_name': 'xyPayloadRibbonEmitPlan', 'arguments': [(0, 'n_marks', 'size'), (6, 'out_tier_direct', 'pointer'), (7, 'out_n_marks', 'pointer'), (8, 'out_apply_palette_default', 'pointer'), (9, 'out_x_ship_scale', 'pointer'), (10, 'out_y_ship_scale', 'pointer'), (11, 'out_channel_slot', 'pointer'), (12, 'out_include_trace_styles', 'pointer'), (13, 'out_attach_transition', 'pointer'), (14, 'out_attempt_gather', 'pointer'), (15, 'out_attach_color2', 'pointer')], 'returns_size': False}, 'xyg_payload_sample_target_indices': {'node_name': 'xyPayloadSampleTargetIndices', 'arguments': [(0, 'n', 'size'), (5, 'out_keep_all', 'pointer'), (6, 'out', 'pointer'), (7, 'capacity', 'size')], 'returns_size': True}, 'xyg_payload_scatter_emit_plan': {'node_name': 'xyPayloadScatterEmitPlan', 'arguments': [(0, 'n_points', 'size'), (5, 'n_marks', 'size'), (10, 'has_tooltip_rows', 'size'), (11, 'n_tooltip_rows', 'size'), (12, 'out_emit_density', 'pointer'), (13, 'out_clear_shipped_sel', 'pointer'), (14, 'out_drill_mode_false', 'pointer'), (15, 'out_set_shipped_sel', 'pointer'), (16, 'out_tier_direct', 'pointer'), (17, 'out_n_marks', 'pointer'), (18, 'out_apply_palette_default', 'pointer'), (19, 'out_attach_animation', 'pointer'), (20, 'out_x_ship_scale', 'pointer'), (21, 'out_y_ship_scale', 'pointer'), (22, 'out_channel_slot', 'pointer'), (23, 'out_include_trace_styles', 'pointer'), (24, 'out_attach_transition', 'pointer'), (25, 'out_attach_tooltip', 'pointer'), (26, 'out_filter_tooltip_by_sel', 'pointer'), (27, 'out_tooltip_length_ok', 'pointer')], 'returns_size': False}, 'xyg_payload_segment_budget': {'node_name': 'xyPayloadSegmentBudget', 'arguments': [], 'returns_size': True}, 'xyg_payload_segments_emit_gather': {'node_name': 'xyPayloadSegmentsEmitGather', 'arguments': [(0, 'kind', 'pointer'), (1, 'kind_len', 'size'), (3, 'n_points', 'size'), (5, 'out_tier', 'pointer'), (6, 'out_role_maps', 'pointer'), (7, 'out_keep_all', 'pointer'), (8, 'out_indices', 'pointer'), (9, 'out_sources', 'pointer'), (10, 'out_roles', 'pointer'), (11, 'capacity', 'size')], 'returns_size': True}, 'xyg_payload_segments_emit_plan': {'node_name': 'xyPayloadSegmentsEmitPlan', 'arguments': [(0, 'kind', 'pointer'), (1, 'kind_len', 'size'), (2, 'n_marks', 'size'), (7, 'out_n_marks', 'pointer'), (8, 'out_apply_palette_default', 'pointer'), (9, 'out_x_ship_scale', 'pointer'), (10, 'out_y_ship_scale', 'pointer'), (11, 'out_channel_slot', 'pointer'), (12, 'out_include_trace_styles', 'pointer'), (13, 'out_attach_transition', 'pointer'), (14, 'out_attempt_gather', 'pointer'), (15, 'out_attempt_role_keys', 'pointer')], 'returns_size': False}, 'xyg_payload_tier': {'node_name': 'xyPayloadTier', 'arguments': [(1, 'n_points', 'size')], 'returns_size': False}, 'xyg_payload_trace_channels_ship_attach': {'node_name': 'xyPayloadTraceChannelsShipAttach', 'arguments': [(1, 'include_trace_styles', 'size'), (5, 'out_ship_color', 'pointer'), (6, 'out_ship_size', 'pointer'), (7, 'out_ship_stroke', 'pointer'), (8, 'out_ship_style_channels', 'pointer')], 'returns_size': False}, 'xyg_payload_trace_emit_materialize': {'node_name': 'xyPayloadTraceEmitMaterialize', 'arguments': [(0, 'emit_in', 'pointer'), (1, 'kind', 'pointer'), (2, 'x_axis_scale', 'pointer'), (3, 'y_axis_scale', 'pointer'), (4, 'orientation', 'pointer'), (5, 'columns', 'pointer'), (6, 'column_values', 'pointer'), (7, 'column_kinds', 'pointer'), (8, 'color_ch', 'pointer'), (9, 'stroke_ch', 'pointer'), (10, 'color2_ch', 'pointer'), (11, 'size_ch', 'pointer'), (12, 'style_channels', 'pointer'), (13, 'color_f64', 'pointer'), (14, 'stroke_f64', 'pointer'), (15, 'color2_f64', 'pointer'), (16, 'size_f64', 'pointer'), (17, 'style_f64', 'pointer'), (18, 'color_u8', 'pointer'), (19, 'stroke_u8', 'pointer'), (20, 'color2_u8', 'pointer'), (21, 'size_u8', 'pointer'), (22, 'style_u8', 'pointer'), (23, 'transition_lo', 'pointer'), (24, 'transition_hi', 'pointer'), (25, 'bin_x', 'pointer'), (26, 'grid_values', 'pointer'), (27, 'summary', 'pointer'), (28, 'geom_out', 'pointer'), (29, 'geom_cap', 'size'), (30, 'chan_out', 'pointer'), (31, 'chan_cap', 'size'), (32, 'out_bytes', 'pointer'), (33, 'out_bytes_cap', 'size'), (34, 'out_bytes_len', 'pointer')], 'returns_size': False}, 'xyg_payload_transition_entry_attach': {'node_name': 'xyPayloadTransitionEntryAttach', 'arguments': [(6, 'n_marks', 'size'), (7, 'n_trace_key_rows', 'size'), (8, 'n_key_value_rows', 'size'), (9, 'n_sel_rows', 'size'), (10, 'max_rows', 'size'), (11, 'has_tooltip_rows', 'size'), (12, 'n_tooltip_rows', 'size'), (13, 'n_points', 'size'), (14, 'out_attach_animation', 'pointer'), (15, 'out_attempt_keys', 'pointer'), (16, 'out_filter_keys_by_sel', 'pointer'), (17, 'out_ship_keys', 'pointer'), (18, 'out_animation_fallback', 'pointer'), (19, 'out_attach_tooltip', 'pointer'), (20, 'out_filter_tooltip_by_sel', 'pointer'), (21, 'out_tooltip_length_ok', 'pointer')], 'returns_size': False}, 'xyg_payload_transition_keys_admit': {'node_name': 'xyPayloadTransitionKeysAdmit', 'arguments': [(3, 'n_marks', 'size'), (4, 'max_rows', 'size')], 'returns_size': False}, 'xyg_payload_visible_indices': {'node_name': 'xyPayloadVisibleIndices', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'n', 'size'), (5, 'base', 'pointer'), (11, 'out_keep_all', 'pointer'), (12, 'out', 'pointer'), (13, 'capacity', 'size')], 'returns_size': True}, 'xyg_payload_visible_mask': {'node_name': 'xyPayloadVisibleMask', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'n', 'size'), (5, 'base', 'pointer'), (7, 'out', 'pointer'), (8, 'capacity', 'size')], 'returns_size': True}, 'xyg_payload_visible_needed': {'node_name': 'xyPayloadVisibleNeeded', 'arguments': [], 'returns_size': False}, 'xyg_polar_heatmap_inverse_map': {'node_name': 'xyPolarHeatmapInverseMap', 'arguments': [(0, 'metrics', 'pointer'), (1, 'metrics_len', 'size'), (6, 'grid_w', 'size'), (7, 'grid_h', 'size'), (13, 'out_w', 'pointer'), (14, 'out_h', 'pointer'), (15, 'out_row', 'pointer'), (16, 'out_col', 'pointer'), (17, 'out_source', 'pointer'), (18, 'capacity', 'size')], 'returns_size': True}, 'xyg_polar_label_room': {'node_name': 'xyPolarLabelRoom', 'arguments': [(1, 'out_room', 'pointer')], 'returns_size': True}, 'xyg_polar_layout': {'node_name': 'xyPolarLayout', 'arguments': [(17, 'out_metrics', 'pointer'), (18, 'out_cap', 'size')], 'returns_size': True}, 'xyg_polar_legend_reserve': {'node_name': 'xyPolarLegendReserve', 'arguments': [(3, 'out_side', 'pointer'), (4, 'out_room', 'pointer')], 'returns_size': True}, 'xyg_polar_legend_room': {'node_name': 'xyPolarLegendRoom', 'arguments': [(1, 'out_room', 'pointer')], 'returns_size': True}, 'xyg_polar_position_mask': {'node_name': 'xyPolarPositionMask', 'arguments': [(0, 'metrics', 'pointer'), (1, 'metrics_len', 'size'), (2, 'theta', 'pointer'), (3, 'r', 'pointer'), (4, 'n', 'size'), (5, 'out', 'pointer'), (6, 'out_cap', 'size')], 'returns_size': True}, 'xyg_polar_project': {'node_name': 'xyPolarProject', 'arguments': [(0, 'metrics', 'pointer'), (1, 'metrics_len', 'size'), (2, 'theta', 'pointer'), (3, 'r', 'pointer'), (4, 'n', 'size'), (5, 'out_x', 'pointer'), (6, 'out_y', 'pointer')], 'returns_size': True}, 'xyg_polar_theta_visible_mask': {'node_name': 'xyPolarThetaVisibleMask', 'arguments': [(0, 'metrics', 'pointer'), (1, 'metrics_len', 'size'), (2, 'theta', 'pointer'), (3, 'n', 'size'), (4, 'out', 'pointer'), (5, 'out_cap', 'size')], 'returns_size': True}, 'xyg_polar_visible_mask': {'node_name': 'xyPolarVisibleMask', 'arguments': [(0, 'metrics', 'pointer'), (1, 'metrics_len', 'size'), (2, 'r', 'pointer'), (3, 'n', 'size'), (4, 'out', 'pointer'), (5, 'out_cap', 'size')], 'returns_size': True}, 'xyg_polar_wedge_points': {'node_name': 'xyPolarWedgePoints', 'arguments': [(0, 'metrics', 'pointer'), (1, 'metrics_len', 'size'), (11, 'out_x', 'pointer'), (12, 'out_y', 'pointer'), (13, 'capacity', 'size')], 'returns_size': True}, 'xyg_polygon_select': {'node_name': 'xyPolygonSelect', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size'), (3, 'rows', 'pointer'), (4, 'n_rows', 'size'), (5, 'poly_x', 'pointer'), (6, 'poly_y', 'pointer'), (8, 'out', 'pointer')], 'returns_size': True}, 'xyg_polygon_triangles': {'node_name': 'xyPolygonTriangles', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size'), (3, 'out', 'pointer'), (4, 'capacity', 'size')], 'returns_size': True}, 'xyg_pyramid_append': {'node_name': 'xyPyramidAppend', 'arguments': [(1, 'x', 'pointer'), (2, 'y', 'pointer'), (3, 'len', 'size')], 'returns_size': False}, 'xyg_pyramid_append_from_stream': {'node_name': 'xyPyramidAppendFromStream', 'arguments': [(3, 'tail_len', 'size')], 'returns_size': False}, 'xyg_pyramid_build': {'node_name': 'xyPyramidBuild', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size')], 'returns_size': False}, 'xyg_pyramid_build_color': {'node_name': 'xyPyramidBuildColor', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size'), (3, 'idx', 'pointer'), (4, 'rgba', 'pointer'), (5, 'lut', 'pointer'), (6, 'lut_len', 'size')], 'returns_size': False}, 'xyg_pyramid_build_from_stream': {'node_name': 'xyPyramidBuildFromStream', 'arguments': [], 'returns_size': False}, 'xyg_pyramid_compose': {'node_name': 'xyPyramidCompose', 'arguments': [(5, 'w', 'size'), (6, 'h', 'size'), (8, 'out', 'pointer')], 'returns_size': False}, 'xyg_pyramid_compose_color': {'node_name': 'xyPyramidComposeColor', 'arguments': [(5, 'w', 'size'), (6, 'h', 'size'), (8, 'out', 'pointer'), (9, 'out_capacity', 'size'), (10, 'out_rgba', 'pointer'), (11, 'out_rgba_capacity', 'size')], 'returns_size': False}, 'xyg_pyramid_count': {'node_name': 'xyPyramidCount', 'arguments': [(5, 'out_count', 'pointer')], 'returns_size': False}, 'xyg_pyramid_free': {'node_name': 'xyPyramidFree', 'arguments': [], 'returns_size': False}, 'xyg_pyramid_spill': {'node_name': 'xyPyramidSpill', 'arguments': [], 'returns_size': False}, 'xyg_quad_mesh_triangles': {'node_name': 'xyQuadMeshTriangles', 'arguments': [(0, 'x', 'pointer'), (1, 'x_len', 'size'), (2, 'y', 'pointer'), (3, 'y_len', 'size'), (4, 'values', 'pointer'), (5, 'cell_rows', 'size'), (6, 'cell_cols', 'size'), (8, 'out_x0', 'pointer'), (9, 'out_y0', 'pointer'), (10, 'out_x1', 'pointer'), (11, 'out_y1', 'pointer'), (12, 'out_x2', 'pointer'), (13, 'out_y2', 'pointer'), (14, 'out_values', 'pointer')], 'returns_size': True}, 'xyg_quantiles': {'node_name': 'xyQuantiles', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size'), (2, 'probs', 'pointer'), (4, 'out', 'pointer')], 'returns_size': True}, 'xyg_quantize_unit_u8': {'node_name': 'xyQuantizeUnitU8', 'arguments': [(0, 'values', 'pointer'), (1, 'values_len', 'size'), (4, 'out', 'pointer')], 'returns_size': False}, 'xyg_range_indices': {'node_name': 'xyRangeIndices', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size'), (7, 'out', 'pointer')], 'returns_size': True}, 'xyg_range_indices_rows': {'node_name': 'xyRangeIndicesRows', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size'), (3, 'rows', 'pointer'), (4, 'n_rows', 'size'), (9, 'out', 'pointer')], 'returns_size': True}, 'xyg_rasterize': {'node_name': 'xyRasterize', 'arguments': [(0, 'cmd', 'pointer'), (1, 'cmd_len', 'size'), (2, 'out', 'pointer'), (3, 'out_capacity', 'size'), (4, 'w', 'size'), (5, 'h', 'size')], 'returns_size': False}, 'xyg_rasterize_data': {'node_name': 'xyRasterizeData', 'arguments': [(0, 'cmd', 'pointer'), (1, 'cmd_len', 'size'), (2, 'data', 'pointer'), (3, 'data_len', 'size'), (4, 'out', 'pointer'), (5, 'out_capacity', 'size'), (6, 'w', 'size'), (7, 'h', 'size')], 'returns_size': False}, 'xyg_rasterize_png': {'node_name': 'xyRasterizePng', 'arguments': [(0, 'cmd', 'pointer'), (1, 'cmd_len', 'size'), (2, 'out', 'pointer'), (3, 'out_capacity', 'size'), (4, 'w', 'size'), (5, 'h', 'size')], 'returns_size': True}, 'xyg_rasterize_png_data': {'node_name': 'xyRasterizePngData', 'arguments': [(0, 'cmd', 'pointer'), (1, 'cmd_len', 'size'), (2, 'data', 'pointer'), (3, 'data_len', 'size'), (4, 'out', 'pointer'), (5, 'out_capacity', 'size'), (6, 'w', 'size'), (7, 'h', 'size')], 'returns_size': True}, 'xyg_rasterize_png_spans': {'node_name': 'xyRasterizePngSpans', 'arguments': [(0, 'cmd', 'pointer'), (1, 'cmd_len', 'size'), (2, 'span_ptrs', 'pointer'), (3, 'span_lens', 'pointer'), (4, 'span_count', 'size'), (5, 'out', 'pointer'), (6, 'out_capacity', 'size'), (7, 'w', 'size'), (8, 'h', 'size')], 'returns_size': True}, 'xyg_rasterize_rgb': {'node_name': 'xyRasterizeRgb', 'arguments': [(0, 'cmd', 'pointer'), (1, 'cmd_len', 'size'), (2, 'out', 'pointer'), (3, 'out_capacity', 'size'), (4, 'w', 'size'), (5, 'h', 'size')], 'returns_size': False}, 'xyg_rasterize_spans': {'node_name': 'xyRasterizeSpans', 'arguments': [(0, 'cmd', 'pointer'), (1, 'cmd_len', 'size'), (2, 'span_ptrs', 'pointer'), (3, 'span_lens', 'pointer'), (4, 'span_count', 'size'), (5, 'out', 'pointer'), (6, 'out_capacity', 'size'), (7, 'w', 'size'), (8, 'h', 'size')], 'returns_size': False}, 'xyg_real_numeric_dtype_admit': {'node_name': 'xyRealNumericDtypeAdmit', 'arguments': [], 'returns_size': False}, 'xyg_rect_zero_baseline_flags': {'node_name': 'xyRectZeroBaselineFlags', 'arguments': [(0, 'base', 'pointer'), (1, 'value', 'pointer'), (2, 'n', 'size')], 'returns_size': False}, 'xyg_recut_polar_plot': {'node_name': 'xyRecutPolarPlot', 'arguments': [(0, 'in_plot', 'pointer'), (9, 'out_plot', 'pointer')], 'returns_size': True}, 'xyg_remap_u8': {'node_name': 'xyRemapU8', 'arguments': [(0, 'values', 'pointer'), (1, 'len', 'size'), (2, 'mapping', 'pointer'), (3, 'mapping_len', 'size')], 'returns_size': False}, 'xyg_rfft': {'node_name': 'xyRfft', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size'), (4, 'out_frequency', 'pointer'), (5, 'out_real', 'pointer'), (6, 'out_imag', 'pointer')], 'returns_size': False}, 'xyg_ribbon_edge': {'node_name': 'xyRibbonEdge', 'arguments': [(5, 'out_x', 'pointer'), (6, 'out_y', 'pointer'), (7, 'capacity', 'size')], 'returns_size': True}, 'xyg_ribbon_polygon': {'node_name': 'xyRibbonPolygon', 'arguments': [(7, 'out_x', 'pointer'), (8, 'out_y', 'pointer'), (9, 'capacity', 'size')], 'returns_size': True}, 'xyg_rounded_rect_poly': {'node_name': 'xyRoundedRectPoly', 'arguments': [(7, 'out_x', 'pointer'), (8, 'out_y', 'pointer'), (9, 'capacity', 'size')], 'returns_size': True}, 'xyg_sample_fraction': {'node_name': 'xySampleFraction', 'arguments': [], 'returns_size': False}, 'xyg_sample_mask': {'node_name': 'xySampleMask', 'arguments': [(0, 'ids', 'pointer'), (1, 'len', 'size'), (4, 'out', 'pointer')], 'returns_size': False}, 'xyg_sample_mask_u32': {'node_name': 'xySampleMaskU32', 'arguments': [(0, 'ids', 'pointer'), (1, 'len', 'size'), (4, 'out', 'pointer')], 'returns_size': False}, 'xyg_sample_range_indices': {'node_name': 'xySampleRangeIndices', 'arguments': [(3, 'out', 'pointer'), (4, 'capacity', 'size')], 'returns_size': True}, 'xyg_sample_threshold': {'node_name': 'xySampleThreshold', 'arguments': [], 'returns_size': False}, 'xyg_sankey_layout': {'node_name': 'xySankeyLayout', 'arguments': [(2, 'sources', 'pointer'), (3, 'targets', 'pointer'), (4, 'values', 'pointer'), (9, 'out_x0', 'pointer'), (10, 'out_y0', 'pointer'), (11, 'out_x1', 'pointer'), (12, 'out_y1', 'pointer'), (13, 'out_layer', 'pointer'), (14, 'out_value', 'pointer'), (15, 'out_source_y0', 'pointer'), (16, 'out_source_y1', 'pointer'), (17, 'out_target_y0', 'pointer'), (18, 'out_target_y1', 'pointer'), (19, 'out_layers', 'pointer'), (20, 'out_err_nodes', 'pointer'), (21, 'out_err_n', 'pointer')], 'returns_size': False}, 'xyg_scale_pins_offset': {'node_name': 'xyScalePinsOffset', 'arguments': [(0, 'scale', 'pointer'), (1, 'len', 'size')], 'returns_size': False}, 'xyg_scene_annotation_style_admit': {'node_name': 'xySceneAnnotationStyleAdmit', 'arguments': [(0, 'kind', 'pointer'), (1, 'kind_len', 'size'), (4, 'key', 'pointer'), (5, 'key_len', 'size')], 'returns_size': False}, 'xyg_scene_arrays_equal': {'node_name': 'xySceneArraysEqual', 'arguments': [(0, 'left', 'pointer'), (1, 'left_len', 'size'), (2, 'right', 'pointer'), (3, 'right_len', 'size')], 'returns_size': False}, 'xyg_scene_axis_ticks': {'node_name': 'xySceneAxisTicks', 'arguments': [(5, 'out_ticks', 'pointer'), (6, 'out_labeled', 'pointer'), (7, 'out_labeled_len', 'pointer'), (8, 'out_step', 'pointer'), (9, 'out_cap', 'size')], 'returns_size': True}, 'xyg_scene_batch_encode': {'node_name': 'xySceneBatchEncode', 'arguments': [(18, 'chrome_style', 'pointer'), (19, 'chrome_style_len', 'size'), (20, 'x_major_ticks', 'pointer'), (21, 'x_major_count', 'size'), (23, 'x_minor_ticks', 'pointer'), (24, 'x_minor_count', 'size'), (25, 'y_major_ticks', 'pointer'), (26, 'y_major_count', 'size'), (28, 'y_minor_ticks', 'pointer'), (29, 'y_minor_count', 'size'), (30, 'x_tick_labels', 'pointer'), (31, 'x_tick_labels_len', 'size'), (32, 'y_tick_labels', 'pointer'), (33, 'y_tick_labels_len', 'size'), (34, 'authored_text_annotations', 'pointer'), (35, 'authored_text_annotations_len', 'size'), (36, 'kinds', 'pointer'), (37, 'stable_ids', 'pointer'), (38, 'style_refs', 'pointer'), (39, 'fill_rgba', 'pointer'), (40, 'stroke_rgba', 'pointer'), (41, 'stroke_width', 'pointer'), (42, 'style_count', 'size'), (43, 'diameter', 'pointer'), (44, 'symbols', 'pointer'), (45, 'expansion_modes', 'pointer'), (46, 'x0', 'pointer'), (47, 'y0', 'pointer'), (48, 'x1', 'pointer'), (49, 'y1', 'pointer'), (50, 'len', 'size'), (51, 'title', 'pointer'), (52, 'title_len', 'size'), (53, 'x_label', 'pointer'), (54, 'x_label_len', 'size'), (55, 'y_label', 'pointer'), (56, 'y_label_len', 'size'), (57, 'legend_input', 'pointer'), (58, 'legend_input_len', 'size'), (59, 'colorbar_input', 'pointer'), (60, 'colorbar_input_len', 'size'), (61, 'polar_input', 'pointer'), (62, 'out', 'pointer'), (63, 'out_cap', 'size')], 'returns_size': True}, 'xyg_scene_browser_painter': {'node_name': 'xySceneBrowserPainter', 'arguments': [(0, 'encoded', 'pointer'), (1, 'encoded_len', 'size'), (2, 'max_bytes', 'size'), (3, 'out', 'pointer'), (4, 'out_cap', 'size')], 'returns_size': True}, 'xyg_scene_channel_constant_css': {'node_name': 'xySceneChannelConstantCss', 'arguments': [(0, 'mode', 'pointer'), (1, 'mode_len', 'size'), (3, 'constant', 'pointer'), (4, 'constant_len', 'size'), (5, 'out', 'pointer'), (6, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_chrome_pack': {'node_name': 'xySceneChromePack', 'arguments': [(0, 'input', 'pointer'), (1, 'x_major', 'pointer'), (2, 'y_major', 'pointer'), (3, 'x_minor', 'pointer'), (4, 'y_minor', 'pointer'), (5, 'x_tick_labels', 'pointer'), (6, 'y_tick_labels', 'pointer'), (7, 'colorbar_stops', 'pointer'), (8, 'colorbar_ticks', 'pointer'), (9, 'out', 'pointer'), (10, 'out_cap', 'size'), (11, 'out_len', 'pointer')], 'returns_size': False}, 'xyg_scene_constant_color_admit': {'node_name': 'xySceneConstantColorAdmit', 'arguments': [], 'returns_size': False}, 'xyg_scene_curve_classify': {'node_name': 'xySceneCurveClassify', 'arguments': [(0, 'text', 'pointer'), (1, 'text_len', 'size')], 'returns_size': False}, 'xyg_scene_dash_admit': {'node_name': 'xySceneDashAdmit', 'arguments': [(0, 'text', 'pointer'), (1, 'text_len', 'size'), (2, 'lengths', 'pointer'), (3, 'n', 'size'), (5, 'out', 'pointer'), (6, 'out_cap', 'size'), (7, 'out_n', 'pointer')], 'returns_size': False}, 'xyg_scene_encode_assembled': {'node_name': 'xySceneEncodeAssembled', 'arguments': [(0, 'xyas', 'pointer'), (1, 'xyas_len', 'size'), (2, 'chrome', 'pointer'), (3, 'chrome_len', 'size'), (4, 'extras', 'pointer'), (5, 'extras_len', 'size'), (20, 'out', 'pointer'), (21, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_encode_assembled_from_sidecars': {'node_name': 'xySceneEncodeAssembledFromSidecars', 'arguments': [(0, 'xyas', 'pointer'), (1, 'xyas_len', 'size'), (2, 'chrome_facts', 'pointer'), (3, 'chrome_facts_len', 'size'), (4, 'xysd', 'pointer'), (5, 'xysd_len', 'size'), (6, 'polar', 'pointer'), (7, 'polar_len', 'size'), (8, 'extras_facts', 'pointer'), (9, 'extras_facts_len', 'size'), (10, 'out', 'pointer'), (11, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_encode_product': {'node_name': 'xySceneEncodeProduct', 'arguments': [(0, 'xytc', 'pointer'), (1, 'xytc_len', 'size'), (2, 'xyta', 'pointer'), (3, 'xyta_len', 'size'), (4, 'xynm', 'pointer'), (5, 'xynm_len', 'size'), (6, 'xycl', 'pointer'), (7, 'xycl_len', 'size'), (8, 'xyaf', 'pointer'), (9, 'xyaf_len', 'size'), (15, 'xycf', 'pointer'), (16, 'xycf_len', 'size'), (17, 'polar', 'pointer'), (18, 'polar_len', 'size'), (19, 'xyfs', 'pointer'), (20, 'xyfs_len', 'size'), (21, 'out', 'pointer'), (22, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_encode_product_attach_plan': {'node_name': 'xySceneEncodeProductAttachPlan', 'arguments': [(1, 'out', 'pointer')], 'returns_size': False}, 'xyg_scene_figure_support_figure_plan': {'node_name': 'xySceneFigureSupportFigurePlan', 'arguments': [(1, 'out', 'pointer')], 'returns_size': False}, 'xyg_scene_figure_support_materialize': {'node_name': 'xySceneFigureSupportMaterialize', 'arguments': [(5, 'annotations', 'pointer'), (6, 'annotation_count', 'size'), (7, 'axes', 'pointer'), (8, 'axis_count', 'size'), (9, 'axis_keys_blob', 'pointer'), (10, 'axis_keys_len', 'size'), (11, 'traces', 'pointer'), (12, 'trace_count', 'size'), (13, 'corner_radius', 'pointer'), (14, 'out', 'pointer'), (15, 'out_cap', 'size'), (16, 'out_len', 'pointer')], 'returns_size': False}, 'xyg_scene_figure_support_pack': {'node_name': 'xySceneFigureSupportPack', 'arguments': [(1, 'axes_blob', 'pointer'), (2, 'axes_len', 'size'), (3, 'traces_blob', 'pointer'), (4, 'traces_len', 'size'), (5, 'out', 'pointer'), (6, 'out_cap', 'size'), (7, 'out_len', 'pointer')], 'returns_size': False}, 'xyg_scene_figure_support_reason': {'node_name': 'xySceneFigureSupportReason', 'arguments': [(0, 'input', 'pointer'), (1, 'len', 'size'), (2, 'out', 'pointer'), (3, 'out_cap', 'size')], 'returns_size': True}, 'xyg_scene_figure_support_trace_dispatch_plan': {'node_name': 'xySceneFigureSupportTraceDispatchPlan', 'arguments': [(0, 'kind', 'pointer'), (1, 'kind_len', 'size'), (6, 'out', 'pointer')], 'returns_size': False}, 'xyg_scene_fill_gradient_admit': {'node_name': 'xySceneFillGradientAdmit', 'arguments': [(0, 'space', 'pointer'), (1, 'space_len', 'size'), (2, 'dir', 'pointer'), (3, 'dir_len', 'size'), (4, 't', 'pointer'), (6, 'css', 'pointer'), (7, 'css_len', 'size'), (8, 'css_lens', 'pointer'), (10, 'mark_color', 'pointer'), (11, 'mark_len', 'size'), (12, 'out_rgba', 'pointer'), (13, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_finite_all': {'node_name': 'xySceneFiniteAll', 'arguments': [(0, 'values', 'pointer'), (1, 'values_len', 'size')], 'returns_size': False}, 'xyg_scene_gradient_dir': {'node_name': 'xySceneGradientDir', 'arguments': [(0, 'text', 'pointer'), (1, 'text_len', 'size')], 'returns_size': False}, 'xyg_scene_gradient_solid_css': {'node_name': 'xySceneGradientSolidCss', 'arguments': [(0, 'rgba', 'pointer'), (1, 'rgba_len', 'size'), (2, 'out', 'pointer'), (3, 'out_len', 'size')], 'returns_size': False}, 'xyg_scene_gradient_space': {'node_name': 'xySceneGradientSpace', 'arguments': [(0, 'text', 'pointer'), (1, 'text_len', 'size')], 'returns_size': False}, 'xyg_scene_gradient_spec_pack': {'node_name': 'xySceneGradientSpecPack', 'arguments': [(0, 'space', 'pointer'), (1, 'space_len', 'size'), (2, 'dir', 'pointer'), (3, 'dir_len', 'size'), (4, 'stop_t', 'pointer'), (6, 'css', 'pointer'), (7, 'css_len', 'size'), (8, 'css_lens', 'pointer'), (10, 'out', 'pointer'), (11, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_heatmap_colormap_admit': {'node_name': 'xySceneHeatmapColormapAdmit', 'arguments': [], 'returns_size': False}, 'xyg_scene_heatmap_extent_admit': {'node_name': 'xySceneHeatmapExtentAdmit', 'arguments': [], 'returns_size': False}, 'xyg_scene_heatmap_shape_admit': {'node_name': 'xySceneHeatmapShapeAdmit', 'arguments': [], 'returns_size': False}, 'xyg_scene_hexbin_colormap_plane_admit': {'node_name': 'xySceneHexbinColormapPlaneAdmit', 'arguments': [(0, 'text', 'pointer'), (1, 'text_len', 'size')], 'returns_size': False}, 'xyg_scene_hexbin_pitch_admit': {'node_name': 'xySceneHexbinPitchAdmit', 'arguments': [], 'returns_size': False}, 'xyg_scene_hexbin_reduce_admit': {'node_name': 'xySceneHexbinReduceAdmit', 'arguments': [(0, 'text', 'pointer'), (1, 'text_len', 'size')], 'returns_size': False}, 'xyg_scene_hexbin_rgba_plane_admit': {'node_name': 'xySceneHexbinRgbaPlaneAdmit', 'arguments': [(0, 'text', 'pointer'), (1, 'text_len', 'size')], 'returns_size': False}, 'xyg_scene_hidden_or_per_item_admit': {'node_name': 'xySceneHiddenOrPerItemAdmit', 'arguments': [], 'returns_size': False}, 'xyg_scene_item_apply_opacity': {'node_name': 'xySceneItemApplyOpacity', 'arguments': [(0, 'packed', 'pointer'), (1, 'packed_len', 'size'), (2, 'n', 'size'), (3, 'artist', 'pointer'), (4, 'artist_len', 'size'), (6, 'opacity', 'pointer'), (7, 'opacity_len', 'size'), (9, 'out', 'pointer'), (10, 'out_len', 'size')], 'returns_size': False}, 'xyg_scene_item_fill_t': {'node_name': 'xySceneItemFillT', 'arguments': [(0, 'values', 'pointer'), (1, 'values_len', 'size'), (2, 'n', 'size'), (6, 'out', 'pointer'), (7, 'out_len', 'size')], 'returns_size': False}, 'xyg_scene_item_widths_admit': {'node_name': 'xySceneItemWidthsAdmit', 'arguments': [(0, 'values', 'pointer'), (1, 'values_len', 'size'), (3, 'n', 'size')], 'returns_size': False}, 'xyg_scene_kind_admit': {'node_name': 'xySceneKindAdmit', 'arguments': [(0, 'text', 'pointer'), (1, 'text_len', 'size')], 'returns_size': False}, 'xyg_scene_kind_class': {'node_name': 'xySceneKindClass', 'arguments': [(0, 'text', 'pointer'), (1, 'text_len', 'size')], 'returns_size': False}, 'xyg_scene_linear_gradient_prefix': {'node_name': 'xySceneLinearGradientPrefix', 'arguments': [(0, 'text', 'pointer'), (1, 'text_len', 'size')], 'returns_size': False}, 'xyg_scene_linecap_admit': {'node_name': 'xySceneLinecapAdmit', 'arguments': [(0, 'text', 'pointer'), (1, 'text_len', 'size')], 'returns_size': False}, 'xyg_scene_marker_blob_pack': {'node_name': 'xySceneMarkerBlobPack', 'arguments': [(1, 'values', 'pointer'), (3, 'contour_lens', 'pointer'), (5, 'out', 'pointer'), (6, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_marker_glyph_admit': {'node_name': 'xySceneMarkerGlyphAdmit', 'arguments': [(0, 'text', 'pointer'), (1, 'text_len', 'size')], 'returns_size': False}, 'xyg_scene_marker_path_admit': {'node_name': 'xySceneMarkerPathAdmit', 'arguments': [(0, 'values', 'pointer'), (2, 'lengths', 'pointer')], 'returns_size': False}, 'xyg_scene_mesh_paint_plane_admit': {'node_name': 'xySceneMeshPaintPlaneAdmit', 'arguments': [(0, 'text', 'pointer'), (1, 'text_len', 'size')], 'returns_size': False}, 'xyg_scene_pack_annotation_facts': {'node_name': 'xyScenePackAnnotationFacts', 'arguments': [(0, 'facts', 'pointer'), (1, 'facts_len', 'size'), (7, 'out', 'pointer'), (8, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_pack_annotation_marks': {'node_name': 'xyScenePackAnnotationMarks', 'arguments': [(0, 'rows', 'pointer'), (1, 'rows_len', 'size'), (6, 'out', 'pointer'), (7, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_pack_annotations': {'node_name': 'xyScenePackAnnotations', 'arguments': [(1, 'text_meta', 'pointer'), (2, 'text_meta_len', 'size'), (3, 'text_lens', 'pointer'), (4, 'texts', 'pointer'), (5, 'texts_len', 'size'), (7, 'attached_meta', 'pointer'), (8, 'attached_meta_len', 'size'), (9, 'attached_lens', 'pointer'), (10, 'attached_texts', 'pointer'), (11, 'attached_texts_len', 'size'), (13, 'arrow_meta', 'pointer'), (14, 'arrow_meta_len', 'size'), (16, 'callout_meta', 'pointer'), (17, 'callout_meta_len', 'size'), (18, 'callout_lens', 'pointer'), (19, 'callout_texts', 'pointer'), (20, 'callout_texts_len', 'size'), (22, 'wrapped_meta', 'pointer'), (23, 'wrapped_meta_len', 'size'), (24, 'wrapped_lens', 'pointer'), (25, 'wrapped_texts', 'pointer'), (26, 'wrapped_texts_len', 'size'), (27, 'out', 'pointer'), (28, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_pack_colorbar': {'node_name': 'xyScenePackColorbar', 'arguments': [(3, 'text_rgba', 'pointer'), (4, 'title', 'pointer'), (5, 'title_len', 'size'), (7, 'stop_values', 'pointer'), (8, 'stop_rgba', 'pointer'), (9, 'stop_rgba_len', 'size'), (11, 'ticks', 'pointer'), (12, 'out', 'pointer'), (13, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_pack_density_grid': {'node_name': 'xyScenePackDensityGrid', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size'), (7, 'idx', 'pointer'), (8, 'rgba', 'pointer'), (9, 'lut', 'pointer'), (10, 'lut_len', 'size'), (11, 'out', 'pointer'), (12, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_pack_figure_chrome': {'node_name': 'xyScenePackFigureChrome', 'arguments': [(0, 'facts', 'pointer'), (1, 'facts_len', 'size'), (2, 'out', 'pointer'), (3, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_pack_figure_chrome_from_sidecars': {'node_name': 'xyScenePackFigureChromeFromSidecars', 'arguments': [(0, 'facts', 'pointer'), (1, 'facts_len', 'size'), (2, 'xysd', 'pointer'), (3, 'xysd_len', 'size'), (4, 'out', 'pointer'), (5, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_pack_heatmap_facts': {'node_name': 'xyScenePackHeatmapFacts', 'arguments': [(0, 'facts', 'pointer'), (1, 'facts_len', 'size'), (2, 'out', 'pointer'), (3, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_pack_legend': {'node_name': 'xyScenePackLegend', 'arguments': [(4, 'text_rgba', 'pointer'), (5, 'frame_fill_rgba', 'pointer'), (6, 'title', 'pointer'), (7, 'title_len', 'size'), (9, 'entry_meta', 'pointer'), (10, 'entry_meta_len', 'size'), (11, 'label_lens', 'pointer'), (12, 'labels', 'pointer'), (13, 'labels_len', 'size'), (14, 'out', 'pointer'), (15, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_pack_product': {'node_name': 'xyScenePackProduct', 'arguments': [(0, 'kind', 'pointer'), (1, 'kind_len', 'size'), (10, 'col0', 'pointer'), (12, 'col1', 'pointer'), (14, 'col2', 'pointer'), (16, 'col3', 'pointer'), (18, 'col4', 'pointer'), (20, 'col5', 'pointer'), (22, 'col6', 'pointer'), (24, 'out', 'pointer'), (25, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_pack_product_facts': {'node_name': 'xyScenePackProductFacts', 'arguments': [(0, 'facts', 'pointer'), (1, 'facts_len', 'size'), (2, 'col0', 'pointer'), (4, 'col1', 'pointer'), (6, 'col2', 'pointer'), (8, 'col3', 'pointer'), (10, 'col4', 'pointer'), (12, 'col5', 'pointer'), (14, 'col6', 'pointer'), (16, 'out', 'pointer'), (17, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_pack_public_export': {'node_name': 'xyScenePackPublicExport', 'arguments': [(0, 'facts', 'pointer'), (1, 'facts_len', 'size'), (2, 'out', 'pointer'), (3, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_pack_scene_extras': {'node_name': 'xyScenePackSceneExtras', 'arguments': [(0, 'polar', 'pointer'), (1, 'polar_len', 'size'), (2, 'paint', 'pointer'), (3, 'paint_len', 'size'), (4, 'facts', 'pointer'), (5, 'facts_len', 'size'), (6, 'out', 'pointer'), (7, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_pack_scene_extras_from_sidecars': {'node_name': 'xyScenePackSceneExtrasFromSidecars', 'arguments': [(0, 'polar', 'pointer'), (1, 'polar_len', 'size'), (2, 'xysd', 'pointer'), (3, 'xysd_len', 'size'), (4, 'facts', 'pointer'), (5, 'facts_len', 'size'), (6, 'out', 'pointer'), (7, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_pack_style_sidecars': {'node_name': 'xyScenePackStyleSidecars', 'arguments': [(0, 'sidecars', 'pointer'), (1, 'sidecars_len', 'size'), (2, 'annotations', 'pointer'), (3, 'annotations_len', 'size'), (4, 'out', 'pointer'), (5, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_pack_trace': {'node_name': 'xyScenePackTrace', 'arguments': [(9, 'col0', 'pointer'), (11, 'col1', 'pointer'), (13, 'col2', 'pointer'), (15, 'col3', 'pointer'), (17, 'col4', 'pointer'), (19, 'col5', 'pointer'), (21, 'out', 'pointer'), (22, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_pack_trace_attach': {'node_name': 'xyScenePackTraceAttach', 'arguments': [(0, 'compiled', 'pointer'), (1, 'compiled_len', 'size'), (2, 'attach', 'pointer'), (3, 'attach_len', 'size'), (4, 'out', 'pointer'), (5, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_pack_trace_compile': {'node_name': 'xyScenePackTraceCompile', 'arguments': [(0, 'facts', 'pointer'), (1, 'facts_len', 'size'), (2, 'out', 'pointer'), (3, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_pack_trace_rows': {'node_name': 'xyScenePackTraceRows', 'arguments': [(0, 'attached', 'pointer'), (1, 'attached_len', 'size'), (2, 'columns', 'pointer'), (3, 'columns_len', 'size'), (4, 'out', 'pointer'), (5, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_pack_trace_sidecars': {'node_name': 'xyScenePackTraceSidecars', 'arguments': [(0, 'attached', 'pointer'), (1, 'attached_len', 'size'), (2, 'names', 'pointer'), (3, 'names_len', 'size'), (4, 'out', 'pointer'), (5, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_parse_linear_gradient': {'node_name': 'xySceneParseLinearGradient', 'arguments': [(0, 'css', 'pointer'), (1, 'css_len', 'size'), (2, 'space', 'pointer'), (3, 'space_len', 'size'), (4, 'out_dir', 'pointer'), (5, 'out_t', 'pointer'), (6, 'out_t_cap', 'size'), (7, 'out_css', 'pointer'), (8, 'out_css_cap', 'size'), (9, 'out_css_lens', 'pointer'), (10, 'out_lens_cap', 'size'), (11, 'out_n', 'pointer')], 'returns_size': False}, 'xyg_scene_plot_layout': {'node_name': 'xyScenePlotLayout', 'arguments': [(2, 'authored_padding', 'pointer'), (13, 'title', 'pointer'), (14, 'title_len', 'size'), (15, 'x_label', 'pointer'), (16, 'x_label_len', 'size'), (17, 'y_label', 'pointer'), (18, 'y_label_len', 'size'), (19, 'x_format', 'pointer'), (20, 'x_format_len', 'size'), (21, 'y_format', 'pointer'), (22, 'y_format_len', 'size'), (24, 'out_margins', 'pointer')], 'returns_size': True}, 'xyg_scene_polar_figure_plan': {'node_name': 'xyScenePolarFigurePlan', 'arguments': [(1, 'out', 'pointer')], 'returns_size': False}, 'xyg_scene_polar_input_pack': {'node_name': 'xyScenePolarInputPack', 'arguments': [(0, 'input', 'pointer'), (1, 'out', 'pointer'), (2, 'out_cap', 'size'), (3, 'out_len', 'pointer')], 'returns_size': False}, 'xyg_scene_public_export_figure_plan': {'node_name': 'xyScenePublicExportFigurePlan', 'arguments': [(1, 'has_chrome_styles', 'size'), (3, 'out', 'pointer')], 'returns_size': False}, 'xyg_scene_public_export_reason': {'node_name': 'xyScenePublicExportReason', 'arguments': [(0, 'input', 'pointer'), (1, 'len', 'size'), (2, 'out', 'pointer'), (3, 'out_cap', 'size')], 'returns_size': True}, 'xyg_scene_public_export_trace_dispatch_plan': {'node_name': 'xyScenePublicExportTraceDispatchPlan', 'arguments': [(0, 'kind', 'pointer'), (1, 'kind_len', 'size'), (4, 'out', 'pointer')], 'returns_size': False}, 'xyg_scene_raster_commands': {'node_name': 'xySceneRasterCommands', 'arguments': [(0, 'encoded', 'pointer'), (1, 'encoded_len', 'size'), (3, 'out', 'pointer'), (4, 'out_cap', 'size')], 'returns_size': True}, 'xyg_scene_rect_extra_flags': {'node_name': 'xySceneRectExtraFlags', 'arguments': [(0, 'kind', 'pointer'), (1, 'kind_len', 'size'), (4, 'radius', 'pointer')], 'returns_size': False}, 'xyg_scene_resolve_chrome_style': {'node_name': 'xySceneResolveChromeStyle', 'arguments': [(0, 'input', 'pointer'), (1, 'len', 'size'), (2, 'out', 'pointer'), (3, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_resolve_mark_styles': {'node_name': 'xySceneResolveMarkStyles', 'arguments': [(0, 'input', 'pointer'), (1, 'len', 'size'), (2, 'out', 'pointer'), (3, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_resolve_pack_kind': {'node_name': 'xySceneResolvePackKind', 'arguments': [(0, 'kind', 'pointer'), (1, 'kind_len', 'size')], 'returns_size': False}, 'xyg_scene_ribbon_color2_classify': {'node_name': 'xySceneRibbonColor2Classify', 'arguments': [(3, 'source_css', 'pointer'), (4, 'source_len', 'size'), (6, 'target_css', 'pointer'), (7, 'target_len', 'size'), (8, 'source_paint', 'pointer'), (9, 'source_paint_len', 'size')], 'returns_size': False}, 'xyg_scene_scale_map': {'node_name': 'xySceneScaleMap', 'arguments': [(0, 'values', 'pointer'), (1, 'len', 'size'), (10, 'out', 'pointer')], 'returns_size': False}, 'xyg_scene_scatter_paint_channel_admit': {'node_name': 'xySceneScatterPaintChannelAdmit', 'arguments': [(0, 'text', 'pointer'), (1, 'text_len', 'size')], 'returns_size': False}, 'xyg_scene_scatter_svg': {'node_name': 'xySceneScatterSvg', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'diameter', 'pointer'), (3, 'fill_rgba', 'pointer'), (4, 'stroke_rgba', 'pointer'), (5, 'stroke_width', 'pointer'), (6, 'symbols', 'pointer'), (7, 'visible', 'pointer'), (8, 'fill_css', 'pointer'), (9, 'fill_css_len', 'size'), (10, 'stroke_css', 'pointer'), (11, 'stroke_css_len', 'size'), (12, 'len', 'size'), (13, 'out', 'pointer'), (14, 'out_cap', 'size')], 'returns_size': True}, 'xyg_scene_splice_annotations': {'node_name': 'xySceneSpliceAnnotations', 'arguments': [(0, 'rows', 'pointer'), (1, 'rows_len', 'size'), (2, 'sidecars', 'pointer'), (3, 'sidecars_len', 'size'), (4, 'annotations', 'pointer'), (5, 'annotations_len', 'size'), (6, 'out', 'pointer'), (7, 'out_cap', 'size')], 'returns_size': False}, 'xyg_scene_static_export': {'node_name': 'xySceneStaticExport', 'arguments': [(0, 'encoded', 'pointer'), (1, 'encoded_len', 'size'), (4, 'width', 'size'), (5, 'height', 'size'), (7, 'out', 'pointer'), (8, 'out_cap', 'size')], 'returns_size': True}, 'xyg_scene_support_reason': {'node_name': 'xySceneSupportReason', 'arguments': [(2, 'out', 'pointer'), (3, 'out_cap', 'size')], 'returns_size': True}, 'xyg_scene_svg': {'node_name': 'xySceneSvg', 'arguments': [(0, 'encoded', 'pointer'), (1, 'encoded_len', 'size'), (2, 'out', 'pointer'), (3, 'out_cap', 'size')], 'returns_size': True}, 'xyg_scene_tick_anchor': {'node_name': 'xySceneTickAnchor', 'arguments': [(0, 'text', 'pointer'), (1, 'text_len', 'size')], 'returns_size': False}, 'xyg_scene_tick_label_layout': {'node_name': 'xySceneTickLabelLayout', 'arguments': [(0, 'positions', 'pointer'), (1, 'n', 'size'), (2, 'label_lens', 'pointer'), (3, 'labels', 'pointer'), (4, 'labels_len', 'size'), (12, 'out_index', 'pointer'), (13, 'out_angle', 'pointer'), (14, 'out_row', 'pointer'), (15, 'out_cap', 'size')], 'returns_size': True}, 'xyg_scene_tick_label_strategy': {'node_name': 'xySceneTickLabelStrategy', 'arguments': [(0, 'text', 'pointer'), (1, 'text_len', 'size')], 'returns_size': False}, 'xyg_scene_version': {'node_name': 'xySceneVersion', 'arguments': [], 'returns_size': False}, 'xyg_scene_xyaf_annotation_dispatch_plan': {'node_name': 'xySceneXyafAnnotationDispatchPlan', 'arguments': [(0, 'kind', 'pointer'), (1, 'kind_len', 'size'), (4, 'out', 'pointer')], 'returns_size': False}, 'xyg_scene_xyaf_bulk_pack': {'node_name': 'xySceneXyafBulkPack', 'arguments': [(0, 'annotations', 'pointer'), (1, 'annotation_count', 'size'), (2, 'extra_style_keys_blob', 'pointer'), (3, 'extra_style_keys_len', 'size'), (4, 'out', 'pointer'), (5, 'out_cap', 'size'), (6, 'out_len', 'pointer'), (7, 'error_index', 'pointer')], 'returns_size': False}, 'xyg_scene_xyaf_pack': {'node_name': 'xySceneXyafPack', 'arguments': [(0, 'input', 'pointer'), (1, 'text', 'pointer'), (2, 'out', 'pointer'), (3, 'out_cap', 'size'), (4, 'out_len', 'pointer')], 'returns_size': False}, 'xyg_scene_xycf_figure_plan': {'node_name': 'xySceneXycfFigurePlan', 'arguments': [(3, 'out', 'pointer')], 'returns_size': False}, 'xyg_scene_xycf_pack': {'node_name': 'xySceneXycfPack', 'arguments': [(0, 'input', 'pointer'), (1, 'title', 'pointer'), (2, 'x_label', 'pointer'), (3, 'y_label', 'pointer'), (4, 'x_format', 'pointer'), (5, 'y_format', 'pointer'), (6, 'x_major', 'pointer'), (7, 'x_minor', 'pointer'), (8, 'y_major', 'pointer'), (9, 'y_minor', 'pointer'), (10, 'x_labels_blob', 'pointer'), (11, 'y_labels_blob', 'pointer'), (12, 'chrome', 'pointer'), (13, 'legend_loc', 'pointer'), (14, 'legend_title', 'pointer'), (15, 'legend_meta', 'pointer'), (16, 'legend_lens', 'pointer'), (17, 'legend_blob', 'pointer'), (18, 'colorbar_stops_blob', 'pointer'), (19, 'colorbar_ticks', 'pointer'), (20, 'colorbar_title', 'pointer'), (21, 'collision_extra', 'pointer'), (22, 'out', 'pointer'), (23, 'out_cap', 'size'), (24, 'out_len', 'pointer')], 'returns_size': False}, 'xyg_scene_xycl_figure_plan': {'node_name': 'xySceneXyclFigurePlan', 'arguments': [(1, 'out', 'pointer')], 'returns_size': False}, 'xyg_scene_xyhf_colormap_pack': {'node_name': 'xySceneXyhfColormapPack', 'arguments': [(1, 'named', 'pointer'), (2, 'named_len', 'size'), (3, 'stop_rgb', 'pointer'), (4, 'stop_len', 'size'), (5, 'out_flags', 'pointer'), (6, 'out_cmap', 'pointer'), (7, 'cmap_cap', 'size'), (8, 'out_stops', 'pointer'), (9, 'stops_cap', 'size')], 'returns_size': False}, 'xyg_scene_xynm_figure_plan': {'node_name': 'xySceneXynmFigurePlan', 'arguments': [(1, 'out', 'pointer')], 'returns_size': False}, 'xyg_scene_xyta_colormap_pack': {'node_name': 'xySceneXytaColormapPack', 'arguments': [(1, 'named', 'pointer'), (2, 'named_len', 'size'), (3, 'stop_rgb', 'pointer'), (4, 'stop_len', 'size'), (5, 'out_flags', 'pointer'), (6, 'out_cmap', 'pointer'), (7, 'cmap_cap', 'size'), (8, 'out_stops', 'pointer'), (9, 'stops_cap', 'size')], 'returns_size': False}, 'xyg_scene_xyta_figure_plan': {'node_name': 'xySceneXytaFigurePlan', 'arguments': [(1, 'out', 'pointer')], 'returns_size': False}, 'xyg_scene_xyta_trace_dispatch_plan': {'node_name': 'xySceneXytaTraceDispatchPlan', 'arguments': [(0, 'kind', 'pointer'), (1, 'kind_len', 'size'), (9, 'out', 'pointer')], 'returns_size': False}, 'xyg_scene_xyta_trace_observations_materialize': {'node_name': 'xySceneXytaTraceObservationsMaterialize', 'arguments': [(0, 'input', 'pointer'), (1, 'fallback_color', 'pointer'), (2, 'style_color', 'pointer'), (3, 'style_stroke', 'pointer'), (4, 'style_colormap_named', 'pointer'), (5, 'style_colormap_stops', 'pointer'), (6, 'grid_values', 'pointer'), (7, 'rgba_u8', 'pointer'), (8, 'rgba_grid_f64', 'pointer'), (9, 'x_values', 'pointer'), (10, 'y_values', 'pointer'), (11, 'color_ch', 'pointer'), (12, 'color_mode', 'pointer'), (13, 'color_constant', 'pointer'), (14, 'color_colormap', 'pointer'), (15, 'color_values_f64', 'pointer'), (16, 'color_rgba_u8', 'pointer'), (17, 'color_codes_u8', 'pointer'), (18, 'color_codes_i64', 'pointer'), (19, 'color_palette_ptrs', 'pointer'), (20, 'color_palette_lens', 'pointer'), (21, 'stroke_ch', 'pointer'), (22, 'stroke_mode', 'pointer'), (23, 'stroke_constant', 'pointer'), (24, 'stroke_colormap', 'pointer'), (25, 'stroke_values_f64', 'pointer'), (26, 'stroke_rgba_u8', 'pointer'), (27, 'stroke_codes_u8', 'pointer'), (28, 'stroke_codes_i64', 'pointer'), (29, 'stroke_palette_ptrs', 'pointer'), (30, 'stroke_palette_lens', 'pointer'), (31, 'color2_ch', 'pointer'), (32, 'color2_mode', 'pointer'), (33, 'color2_constant', 'pointer'), (34, 'color2_colormap', 'pointer'), (35, 'color2_values_f64', 'pointer'), (36, 'color2_rgba_u8', 'pointer'), (37, 'color2_codes_u8', 'pointer'), (38, 'color2_codes_i64', 'pointer'), (39, 'color2_palette_ptrs', 'pointer'), (40, 'color2_palette_lens', 'pointer'), (41, 'opacity_ch', 'pointer'), (42, 'opacity_values', 'pointer'), (43, 'artist_ch', 'pointer'), (44, 'artist_values', 'pointer'), (45, 'stroke_width_ch', 'pointer'), (46, 'stroke_width_values', 'pointer'), (47, 'summary', 'pointer'), (48, 'out_bytes', 'pointer'), (49, 'out_cap', 'size'), (50, 'out_len', 'pointer')], 'returns_size': False}, 'xyg_scene_xyta_trace_pack': {'node_name': 'xySceneXytaTracePack', 'arguments': [(0, 'input', 'pointer'), (1, 'grid', 'pointer'), (2, 'rgba', 'pointer'), (3, 'rgba_grid', 'pointer'), (4, 'x', 'pointer'), (5, 'y', 'pointer'), (6, 'mean_rgba', 'pointer'), (7, 'idx', 'pointer'), (8, 'lut', 'pointer'), (9, 'cmap', 'pointer'), (10, 'stops', 'pointer'), (11, 'color_ch', 'pointer'), (12, 'style_color', 'pointer'), (13, 'out', 'pointer'), (14, 'out_cap', 'size'), (15, 'out_len', 'pointer')], 'returns_size': False}, 'xyg_scene_xytc_color2_flags_pack': {'node_name': 'xySceneXytcColor2FlagsPack', 'arguments': [(3, 'out_flags', 'pointer')], 'returns_size': False}, 'xyg_scene_xytc_color_channel_pack': {'node_name': 'xySceneXytcColorChannelPack', 'arguments': [(2, 'out_flags', 'pointer')], 'returns_size': False}, 'xyg_scene_xytc_dash_pattern_pack': {'node_name': 'xySceneXytcDashPatternPack', 'arguments': [(1, 'out_flags', 'pointer')], 'returns_size': False}, 'xyg_scene_xytc_figure_plan': {'node_name': 'xySceneXytcFigurePlan', 'arguments': [(1, 'out', 'pointer')], 'returns_size': False}, 'xyg_scene_xytc_hex_pitch_pack': {'node_name': 'xySceneXytcHexPitchPack', 'arguments': [(5, 'out_flags', 'pointer'), (6, 'out_hex_dx', 'pointer'), (7, 'out_hex_dy', 'pointer')], 'returns_size': False}, 'xyg_scene_xytc_meta_flags_pack': {'node_name': 'xySceneXytcMetaFlagsPack', 'arguments': [(2, 'kind', 'pointer'), (3, 'kind_len', 'size'), (9, 'out_flags', 'pointer')], 'returns_size': False}, 'xyg_scene_xytc_numeric_style_pack': {'node_name': 'xySceneXytcNumericStylePack', 'arguments': [(3, 'has_stroke_width', 'size'), (4, 'has_width', 'size'), (5, 'has_line_width', 'size'), (11, 'out_flags', 'pointer'), (12, 'out_size', 'pointer'), (13, 'out_size_ch_value', 'pointer'), (14, 'out_stroke_width', 'pointer'), (15, 'out_width', 'pointer'), (16, 'out_line_width', 'pointer')], 'returns_size': False}, 'xyg_scene_xytc_opacity_pack': {'node_name': 'xySceneXytcOpacityPack', 'arguments': [(5, 'out_fill', 'pointer'), (6, 'out_stroke', 'pointer'), (7, 'out_line', 'pointer')], 'returns_size': False}, 'xyg_scene_xytc_paint_presence_pack': {'node_name': 'xySceneXytcPaintPresencePack', 'arguments': [(4, 'out_flags', 'pointer')], 'returns_size': False}, 'xyg_scene_xytc_radius_pack': {'node_name': 'xySceneXytcRadiusPack', 'arguments': [(0, 'kind', 'pointer'), (1, 'kind_len', 'size'), (6, 'out_flags', 'pointer'), (7, 'out_r_tip', 'pointer'), (8, 'out_r_base', 'pointer'), (9, 'out_wedge_gap', 'pointer')], 'returns_size': False}, 'xyg_scene_xytc_stroke_perimeter_pack': {'node_name': 'xySceneXytcStrokePerimeterPack', 'arguments': [(4, 'out_flags', 'pointer')], 'returns_size': False}, 'xyg_scene_xytc_symbol_int_pack': {'node_name': 'xySceneXytcSymbolIntPack', 'arguments': [(1, 'out_flags', 'pointer')], 'returns_size': False}, 'xyg_scene_xytc_trace_dispatch_plan': {'node_name': 'xySceneXytcTraceDispatchPlan', 'arguments': [(0, 'kind', 'pointer'), (1, 'kind_len', 'size'), (5, 'out', 'pointer')], 'returns_size': False}, 'xyg_scene_xytc_trace_observations_materialize': {'node_name': 'xySceneXytcTraceObservationsMaterialize', 'arguments': [(0, 'input', 'pointer'), (1, 'kind', 'pointer'), (2, 'name', 'pointer'), (3, 'symbol', 'pointer'), (4, 'stroke', 'pointer'), (5, 'line_color', 'pointer'), (6, 'color_css', 'pointer'), (7, 'dash', 'pointer'), (8, 'dash_values', 'pointer'), (9, 'fill_string', 'pointer'), (10, 'fill_space', 'pointer'), (11, 'fill_dir', 'pointer'), (12, 'fill_stop_t', 'pointer'), (13, 'fill_stop_css', 'pointer'), (14, 'fill_stop_css_lens', 'pointer'), (15, 'fill_dict_gradient', 'pointer'), (16, 'fill_dict_space', 'pointer'), (17, 'marker_values', 'pointer'), (18, 'marker_lens', 'pointer'), (19, 'marker_glyph', 'pointer'), (20, 'source_paint', 'pointer'), (21, 'color2_source_const', 'pointer'), (22, 'color2_target_const', 'pointer'), (23, 'color_mode', 'pointer'), (24, 'color_const', 'pointer'), (25, 'linecap', 'pointer'), (26, 'step', 'pointer'), (27, 'curve', 'pointer'), (28, 'summary', 'pointer'), (29, 'out_bytes', 'pointer'), (30, 'out_cap', 'size'), (31, 'out_len', 'pointer')], 'returns_size': False}, 'xyg_scene_xytc_trace_pack': {'node_name': 'xySceneXytcTracePack', 'arguments': [(0, 'input', 'pointer'), (1, 'kind', 'pointer'), (2, 'name', 'pointer'), (3, 'symbol_b', 'pointer'), (4, 'dash_b', 'pointer'), (5, 'dash_pattern', 'pointer'), (6, 'linecap_b', 'pointer'), (7, 'step_b', 'pointer'), (8, 'curve_b', 'pointer'), (9, 'fill_css', 'pointer'), (10, 'fill_space', 'pointer'), (11, 'fill_gradient_blob', 'pointer'), (12, 'stroke_css', 'pointer'), (13, 'line_color', 'pointer'), (14, 'color_css', 'pointer'), (15, 'color_mode', 'pointer'), (16, 'color_const', 'pointer'), (17, 'marker_blob', 'pointer'), (18, 'color2_gradient_blob', 'pointer'), (19, 'out', 'pointer'), (20, 'out_cap', 'size'), (21, 'out_len', 'pointer')], 'returns_size': False}, 'xyg_screen_shape': {'node_name': 'xyScreenShape', 'arguments': [(0, 'px_w', 'size'), (1, 'px_h', 'size'), (2, 'out_w', 'pointer'), (3, 'out_h', 'pointer')], 'returns_size': False}, 'xyg_sector_triangles': {'node_name': 'xySectorTriangles', 'arguments': [(0, 'values', 'pointer'), (1, 'len', 'size'), (2, 'explode', 'pointer'), (10, 'out_x0', 'pointer'), (11, 'out_y0', 'pointer'), (12, 'out_x1', 'pointer'), (13, 'out_y1', 'pointer'), (14, 'out_x2', 'pointer'), (15, 'out_y2', 'pointer'), (16, 'out_sector', 'pointer'), (17, 'capacity', 'size')], 'returns_size': True}, 'xyg_size_range_admit': {'node_name': 'xySizeRangeAdmit', 'arguments': [(2, 'out_lo', 'pointer'), (3, 'out_hi', 'pointer')], 'returns_size': False}, 'xyg_sorted_display_label_remap': {'node_name': 'xySortedDisplayLabelRemap', 'arguments': [(0, 'label_lens', 'pointer'), (1, 'label_texts', 'pointer'), (2, 'label_texts_len', 'size'), (3, 'n', 'size'), (4, 'in_counts', 'pointer'), (5, 'out_remap', 'pointer'), (6, 'out_remap_cap', 'size'), (7, 'out_code_width', 'pointer'), (8, 'out_category_lens', 'pointer'), (9, 'out_category_texts', 'pointer'), (10, 'out_category_texts_cap', 'size'), (11, 'category_lens_cap', 'size'), (12, 'out_category_counts', 'pointer'), (13, 'out_category_counts_cap', 'size')], 'returns_size': True}, 'xyg_spectrogram': {'node_name': 'xySpectrogram', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size'), (5, 'out_frequency', 'pointer'), (6, 'out_time', 'pointer'), (7, 'out_power', 'pointer')], 'returns_size': False}, 'xyg_stacked_bounds': {'node_name': 'xyStackedBounds', 'arguments': [(0, 'values', 'pointer'), (1, 'rows', 'size'), (2, 'cols', 'size'), (4, 'out_lower', 'pointer'), (5, 'out_upper', 'pointer')], 'returns_size': False}, 'xyg_step_arrays': {'node_name': 'xyStepArrays', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'n', 'size'), (4, 'out_x', 'pointer'), (5, 'out_y', 'pointer'), (6, 'capacity', 'size')], 'returns_size': True}, 'xyg_stratified_sample_mask': {'node_name': 'xyStratifiedSampleMask', 'arguments': [(0, 'ids', 'pointer'), (1, 'groups', 'pointer'), (2, 'len', 'size'), (3, 'n_groups', 'size'), (6, 'min_count', 'size'), (7, 'out', 'pointer')], 'returns_size': False}, 'xyg_stratified_sample_mask_u32': {'node_name': 'xyStratifiedSampleMaskU32', 'arguments': [(0, 'ids', 'pointer'), (1, 'groups', 'pointer'), (2, 'len', 'size'), (3, 'n_groups', 'size'), (6, 'min_count', 'size'), (7, 'out', 'pointer')], 'returns_size': False}, 'xyg_stratified_sample_range_plan': {'node_name': 'xyStratifiedSampleRangePlan', 'arguments': [(0, 'n_rows', 'size'), (1, 'n_groups', 'size'), (7, 'out_fraction', 'pointer'), (8, 'out_seed', 'pointer'), (9, 'out_min_count', 'pointer'), (10, 'out_capacity', 'pointer'), (11, 'out_keep_all', 'pointer')], 'returns_size': False}, 'xyg_stratified_sample_range_u8': {'node_name': 'xyStratifiedSampleRangeU8', 'arguments': [(0, 'groups', 'pointer'), (1, 'len', 'size'), (2, 'n_groups', 'size'), (5, 'min_count', 'size'), (6, 'out', 'pointer'), (7, 'capacity', 'size')], 'returns_size': True}, 'xyg_stratified_sample_range_u8_counted': {'node_name': 'xyStratifiedSampleRangeU8Counted', 'arguments': [(0, 'groups', 'pointer'), (1, 'len', 'size'), (2, 'counts', 'pointer'), (3, 'n_groups', 'size'), (6, 'min_count', 'size'), (7, 'out', 'pointer'), (8, 'capacity', 'size')], 'returns_size': True}, 'xyg_stream_append': {'node_name': 'xyStreamAppend', 'arguments': [(1, 'data', 'pointer'), (2, 'len', 'size')], 'returns_size': False}, 'xyg_stream_capacity': {'node_name': 'xyStreamCapacity', 'arguments': [], 'returns_size': True}, 'xyg_stream_copy': {'node_name': 'xyStreamCopy', 'arguments': [(1, 'out', 'pointer'), (2, 'len', 'size')], 'returns_size': False}, 'xyg_stream_data': {'node_name': 'xyStreamData', 'arguments': [(1, 'out_ptr', 'pointer'), (2, 'out_len', 'pointer')], 'returns_size': False}, 'xyg_stream_free': {'node_name': 'xyStreamFree', 'arguments': [], 'returns_size': False}, 'xyg_stream_len': {'node_name': 'xyStreamLen', 'arguments': [], 'returns_size': True}, 'xyg_stream_new': {'node_name': 'xyStreamNew', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size')], 'returns_size': False}, 'xyg_stream_seal': {'node_name': 'xyStreamSeal', 'arguments': [], 'returns_size': False}, 'xyg_stream_zone_maps': {'node_name': 'xyStreamZoneMaps', 'arguments': [(1, 'out_min', 'pointer'), (2, 'out_max', 'pointer'), (3, 'out_count', 'pointer'), (4, 'out_null_count', 'pointer'), (5, 'out_sum', 'pointer'), (6, 'out_sum_sq', 'pointer'), (7, 'out_positive_min', 'pointer'), (8, 'out_positive_max', 'pointer')], 'returns_size': True}, 'xyg_streamlines': {'node_name': 'xyStreamlines', 'arguments': [(0, 'x_coords', 'pointer'), (1, 'cols', 'size'), (2, 'y_coords', 'pointer'), (3, 'rows', 'size'), (4, 'u', 'pointer'), (5, 'v', 'pointer'), (8, 'out_x0', 'pointer'), (9, 'out_x1', 'pointer'), (10, 'out_y0', 'pointer'), (11, 'out_y1', 'pointer'), (12, 'capacity', 'size')], 'returns_size': True}, 'xyg_svg_poly_path': {'node_name': 'xySvgPolyPath', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size'), (3, 'out', 'pointer'), (4, 'out_cap', 'size')], 'returns_size': True}, 'xyg_svg_to_pdf': {'node_name': 'xySvgToPdf', 'arguments': [(0, 'svg', 'pointer'), (1, 'svg_len', 'size'), (2, 'out', 'pointer'), (3, 'out_cap', 'size')], 'returns_size': True}, 'xyg_temporal_column_copy': {'node_name': 'xyTemporalColumnCopy', 'arguments': [(1, 'out_values', 'pointer'), (2, 'out_validity', 'pointer'), (3, 'capacity', 'size')], 'returns_size': False}, 'xyg_temporal_column_create': {'node_name': 'xyTemporalColumnCreate', 'arguments': [(0, 'descriptor', 'pointer'), (1, 'out_handle', 'pointer')], 'returns_size': False}, 'xyg_temporal_column_destroy': {'node_name': 'xyTemporalColumnDestroy', 'arguments': [], 'returns_size': False}, 'xyg_temporal_column_meta': {'node_name': 'xyTemporalColumnMeta', 'arguments': [(1, 'out_len', 'pointer'), (2, 'out_precision', 'pointer'), (3, 'out_timezone_len', 'pointer')], 'returns_size': False}, 'xyg_temporal_column_timezone': {'node_name': 'xyTemporalColumnTimezone', 'arguments': [(1, 'out_timezone', 'pointer'), (2, 'capacity', 'size')], 'returns_size': False}, 'xyg_temporal_controller_apply_event': {'node_name': 'xyTemporalControllerApplyEvent', 'arguments': [(8, 'selection', 'pointer'), (9, 'selection_count', 'size'), (10, 'out_applied', 'pointer')], 'returns_size': False}, 'xyg_temporal_controller_create': {'node_name': 'xyTemporalControllerCreate', 'arguments': [(0, 'descriptor', 'pointer'), (1, 'out_handle', 'pointer')], 'returns_size': False}, 'xyg_temporal_controller_destroy': {'node_name': 'xyTemporalControllerDestroy', 'arguments': [], 'returns_size': False}, 'xyg_temporal_controller_dispose': {'node_name': 'xyTemporalControllerDispose', 'arguments': [], 'returns_size': False}, 'xyg_temporal_controller_pause': {'node_name': 'xyTemporalControllerPause', 'arguments': [], 'returns_size': False}, 'xyg_temporal_controller_play': {'node_name': 'xyTemporalControllerPlay', 'arguments': [], 'returns_size': False}, 'xyg_temporal_controller_poll_event': {'node_name': 'xyTemporalControllerPollEvent', 'arguments': [(1, 'out_has_event', 'pointer'), (2, 'out_group_id', 'pointer'), (3, 'out_source_instance', 'pointer'), (4, 'out_revision', 'pointer'), (5, 'out_range_start', 'pointer'), (6, 'out_range_end', 'pointer'), (7, 'out_cursor', 'pointer'), (8, 'out_window', 'pointer'), (9, 'out_selection', 'pointer'), (10, 'selection_capacity', 'size'), (11, 'out_selection_count', 'pointer')], 'returns_size': False}, 'xyg_temporal_controller_set_cursor': {'node_name': 'xyTemporalControllerSetCursor', 'arguments': [], 'returns_size': False}, 'xyg_temporal_controller_set_direction': {'node_name': 'xyTemporalControllerSetDirection', 'arguments': [], 'returns_size': False}, 'xyg_temporal_controller_set_loop': {'node_name': 'xyTemporalControllerSetLoop', 'arguments': [], 'returns_size': False}, 'xyg_temporal_controller_set_range': {'node_name': 'xyTemporalControllerSetRange', 'arguments': [], 'returns_size': False}, 'xyg_temporal_controller_set_rate_milli': {'node_name': 'xyTemporalControllerSetRateMilli', 'arguments': [], 'returns_size': False}, 'xyg_temporal_controller_set_reduced_motion': {'node_name': 'xyTemporalControllerSetReducedMotion', 'arguments': [], 'returns_size': False}, 'xyg_temporal_controller_set_selection': {'node_name': 'xyTemporalControllerSetSelection', 'arguments': [(1, 'ids', 'pointer'), (2, 'count', 'size')], 'returns_size': False}, 'xyg_temporal_controller_state': {'node_name': 'xyTemporalControllerState', 'arguments': [(1, 'out_instance_id', 'pointer'), (2, 'out_group_id', 'pointer'), (3, 'out_domain_start', 'pointer'), (4, 'out_domain_end', 'pointer'), (5, 'out_range_start', 'pointer'), (6, 'out_range_end', 'pointer'), (7, 'out_cursor', 'pointer'), (8, 'out_window', 'pointer'), (9, 'out_step', 'pointer'), (10, 'out_direction', 'pointer'), (11, 'out_rate_milli', 'pointer'), (12, 'out_loop_enabled', 'pointer'), (13, 'out_playing', 'pointer'), (14, 'out_reduced_motion', 'pointer'), (15, 'out_revision', 'pointer'), (16, 'out_disposed', 'pointer'), (17, 'out_selection', 'pointer'), (18, 'selection_capacity', 'size'), (19, 'out_selection_count', 'pointer')], 'returns_size': False}, 'xyg_temporal_controller_step': {'node_name': 'xyTemporalControllerStep', 'arguments': [], 'returns_size': False}, 'xyg_temporal_controller_tick': {'node_name': 'xyTemporalControllerTick', 'arguments': [(2, 'out_advanced', 'pointer')], 'returns_size': False}, 'xyg_temporal_coordinate_deliver': {'node_name': 'xyTemporalCoordinateDeliver', 'arguments': [(7, 'selection', 'pointer'), (8, 'selection_count', 'size'), (9, 'out_applied', 'pointer')], 'returns_size': False}, 'xyg_temporal_events_in_range': {'node_name': 'xyTemporalEventsInRange', 'arguments': [(0, 'event_micros', 'pointer'), (1, 'event_valid', 'pointer'), (2, 'event_len', 'size'), (7, 'out_visibility', 'pointer'), (8, 'capacity', 'size'), (10, 'cancel_flag', 'pointer')], 'returns_size': False}, 'xyg_temporal_graph_cancel': {'node_name': 'xyTemporalGraphCancel', 'arguments': [], 'returns_size': False}, 'xyg_temporal_graph_create': {'node_name': 'xyTemporalGraphCreate', 'arguments': [(0, 'descriptor', 'pointer'), (1, 'out_handle', 'pointer')], 'returns_size': False}, 'xyg_temporal_graph_destroy': {'node_name': 'xyTemporalGraphDestroy', 'arguments': [], 'returns_size': False}, 'xyg_temporal_graph_frame': {'node_name': 'xyTemporalGraphFrame', 'arguments': [], 'returns_size': False}, 'xyg_temporal_graph_required_budget': {'node_name': 'xyTemporalGraphRequiredBudget', 'arguments': [(1, 'out_budget', 'pointer')], 'returns_size': False}, 'xyg_temporal_graph_set_focus': {'node_name': 'xyTemporalGraphSetFocus', 'arguments': [(2, 'id', 'pointer')], 'returns_size': False}, 'xyg_temporal_graph_set_pinned': {'node_name': 'xyTemporalGraphSetPinned', 'arguments': [(1, 'node_ids', 'pointer'), (2, 'node_count', 'size')], 'returns_size': False}, 'xyg_temporal_graph_set_selection': {'node_name': 'xyTemporalGraphSetSelection', 'arguments': [(1, 'node_ids', 'pointer'), (2, 'node_count', 'size'), (3, 'edge_ids', 'pointer'), (4, 'edge_count', 'size')], 'returns_size': False}, 'xyg_temporal_graph_snapshot_copy': {'node_name': 'xyTemporalGraphSnapshotCopy', 'arguments': [(2, 'buffers', 'pointer')], 'returns_size': False}, 'xyg_temporal_graph_snapshot_meta': {'node_name': 'xyTemporalGraphSnapshotMeta', 'arguments': [(1, 'out_meta', 'pointer')], 'returns_size': False}, 'xyg_temporal_interval_index_create': {'node_name': 'xyTemporalIntervalIndexCreate', 'arguments': [(0, 'descriptor', 'pointer'), (1, 'out_handle', 'pointer')], 'returns_size': False}, 'xyg_temporal_interval_index_destroy': {'node_name': 'xyTemporalIntervalIndexDestroy', 'arguments': [], 'returns_size': False}, 'xyg_temporal_interval_index_len': {'node_name': 'xyTemporalIntervalIndexLen', 'arguments': [(1, 'out_len', 'pointer')], 'returns_size': False}, 'xyg_temporal_interval_visibility_at': {'node_name': 'xyTemporalIntervalVisibilityAt', 'arguments': [(2, 'out_visibility', 'pointer'), (3, 'capacity', 'size'), (5, 'cancel_flag', 'pointer')], 'returns_size': False}, 'xyg_temporal_selection_limit': {'node_name': 'xyTemporalSelectionLimit', 'arguments': [], 'returns_size': False}, 'xyg_text_block_measure': {'node_name': 'xyTextBlockMeasure', 'arguments': [(0, 'text', 'pointer'), (1, 'text_len', 'size'), (5, 'out_metrics', 'pointer'), (6, 'out_line_lens', 'pointer'), (7, 'line_cap', 'size'), (8, 'out_lines', 'pointer'), (9, 'lines_cap', 'size')], 'returns_size': True}, 'xyg_text_block_rotated_extent': {'node_name': 'xyTextBlockRotatedExtent', 'arguments': [(3, 'out_x', 'pointer'), (4, 'out_y', 'pointer')], 'returns_size': True}, 'xyg_tick_format': {'node_name': 'xyTickFormat', 'arguments': [(5, 'format', 'pointer'), (6, 'format_len', 'size'), (8, 'category_lens', 'pointer'), (9, 'category_texts', 'pointer'), (10, 'category_texts_len', 'size'), (11, 'out', 'pointer'), (12, 'out_cap', 'size')], 'returns_size': True}, 'xyg_tick_window': {'node_name': 'xyTickWindow', 'arguments': [(7, 'out_lo', 'pointer'), (8, 'out_hi', 'pointer')], 'returns_size': True}, 'xyg_tick_window_filter': {'node_name': 'xyTickWindowFilter', 'arguments': [(0, 'values', 'pointer'), (1, 'n', 'size'), (7, 'out', 'pointer'), (8, 'out_cap', 'size')], 'returns_size': True}, 'xyg_tight_layout_figure_extra': {'node_name': 'xyTightLayoutFigureExtra', 'arguments': [(7, 'out_extra', 'pointer')], 'returns_size': True}, 'xyg_tight_layout_solve': {'node_name': 'xyTightLayoutSolve', 'arguments': [(5, 'in_panels', 'pointer'), (7, 'extra', 'pointer'), (12, 'rect', 'pointer'), (13, 'out', 'pointer')], 'returns_size': True}, 'xyg_tile_budget_set': {'node_name': 'xyTileBudgetSet', 'arguments': [(0, 'bytes', 'size')], 'returns_size': False}, 'xyg_tile_store_append': {'node_name': 'xyTileStoreAppend', 'arguments': [(1, 'x', 'pointer'), (2, 'y', 'pointer'), (3, 'len', 'size')], 'returns_size': False}, 'xyg_tile_store_compose': {'node_name': 'xyTileStoreCompose', 'arguments': [(5, 'w', 'size'), (6, 'h', 'size'), (8, 'out', 'pointer')], 'returns_size': False}, 'xyg_tile_store_compose_color': {'node_name': 'xyTileStoreComposeColor', 'arguments': [(5, 'w', 'size'), (6, 'h', 'size'), (8, 'out', 'pointer'), (9, 'out_capacity', 'size'), (10, 'out_rgba', 'pointer'), (11, 'out_rgba_capacity', 'size')], 'returns_size': False}, 'xyg_tile_store_fetch': {'node_name': 'xyTileStoreFetch', 'arguments': [(4, 'out_counts', 'pointer'), (5, 'out_color', 'pointer')], 'returns_size': False}, 'xyg_tile_store_free': {'node_name': 'xyTileStoreFree', 'arguments': [], 'returns_size': False}, 'xyg_tile_store_stats': {'node_name': 'xyTileStoreStats', 'arguments': [(1, 'out', 'pointer')], 'returns_size': False}, 'xyg_transition_keys_fixed': {'node_name': 'xyTransitionKeysFixed', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size'), (2, 'width', 'size'), (5, 'out_lo', 'pointer'), (6, 'out_hi', 'pointer'), (7, 'out_error_first', 'pointer'), (8, 'out_error_index', 'pointer')], 'returns_size': False}, 'xyg_triangle_edges': {'node_name': 'xyTriangleEdges', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'vertex_count', 'size'), (3, 'triangles', 'pointer'), (4, 'face_count', 'size'), (5, 'out_x0', 'pointer'), (6, 'out_x1', 'pointer'), (7, 'out_y0', 'pointer'), (8, 'out_y1', 'pointer')], 'returns_size': True}, 'xyg_valid_indices_f64': {'node_name': 'xyValidIndicesF64', 'arguments': [(0, 'columns', 'pointer'), (2, 'len', 'size'), (4, 'out', 'pointer'), (5, 'capacity', 'size')], 'returns_size': True}, 'xyg_vector_segments': {'node_name': 'xyVectorSegments', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'u', 'pointer'), (3, 'v', 'pointer'), (4, 'len', 'size'), (8, 'out_x0', 'pointer'), (9, 'out_x1', 'pointer'), (10, 'out_y0', 'pointer'), (11, 'out_y1', 'pointer')], 'returns_size': True}, 'xyg_view_visible_mask': {'node_name': 'xyViewVisibleMask', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'n', 'size'), (7, 'out', 'pointer')], 'returns_size': True}, 'xyg_violin_density': {'node_name': 'xyViolinDensity', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size'), (3, 'out_edges', 'pointer'), (4, 'out_density', 'pointer')], 'returns_size': False}, 'xyg_violin_rects': {'node_name': 'xyViolinRects', 'arguments': [(0, 'values', 'pointer'), (1, 'values_len', 'size'), (2, 'offsets', 'pointer'), (3, 'offsets_len', 'size'), (4, 'centers', 'pointer'), (5, 'centers_len', 'size'), (9, 'out_x0', 'pointer'), (10, 'out_y0', 'pointer'), (11, 'out_x1', 'pointer'), (12, 'out_y1', 'pointer'), (13, 'out_groups', 'pointer'), (14, 'out_edges', 'pointer'), (15, 'out_density', 'pointer'), (16, 'out_cap', 'size')], 'returns_size': True}, 'xyg_weighted_ecdf': {'node_name': 'xyWeightedEcdf', 'arguments': [(0, 'values', 'pointer'), (1, 'weights', 'pointer'), (2, 'len', 'size'), (3, 'out_values', 'pointer'), (4, 'out_cumulative', 'pointer')], 'returns_size': True}, 'xyg_welch_spectra': {'node_name': 'xyWelchSpectra', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size'), (6, 'out_frequency', 'pointer'), (7, 'out_pxx', 'pointer'), (8, 'out_pyy', 'pointer'), (9, 'out_pxy_real', 'pointer'), (10, 'out_pxy_imag', 'pointer')], 'returns_size': False}, 'xyg_wind_rose_bins': {'node_name': 'xyWindRoseBins', 'arguments': [(0, 'directions', 'pointer'), (1, 'speeds', 'pointer'), (2, 'len', 'size'), (4, 'speed_edges', 'pointer'), (6, 'out_edges', 'pointer'), (7, 'capacity_edges', 'size'), (8, 'out_centres', 'pointer'), (9, 'out_counts', 'pointer'), (10, 'capacity_counts', 'size'), (11, 'out_n_obs', 'pointer')], 'returns_size': True}, 'xyg_x_axis_title_room': {'node_name': 'xyXAxisTitleRoom', 'arguments': [(0, 'title', 'pointer'), (1, 'title_len', 'size'), (5, 'out_room', 'pointer')], 'returns_size': True}, 'xyg_x_tick_label_edge_rooms': {'node_name': 'xyXTickLabelEdgeRooms', 'arguments': [(1, 'positions', 'pointer'), (2, 'n', 'size'), (3, 'label_lens', 'pointer'), (4, 'labels', 'pointer'), (5, 'labels_len', 'size'), (6, 'angles', 'pointer'), (7, 'anchors', 'pointer'), (9, 'out_left', 'pointer'), (10, 'out_right', 'pointer')], 'returns_size': True}, 'xyg_x_tick_label_room': {'node_name': 'xyXTickLabelRoom', 'arguments': [(0, 'label_lens', 'pointer'), (1, 'labels', 'pointer'), (2, 'labels_len', 'size'), (3, 'n', 'size'), (4, 'angles', 'pointer'), (5, 'rows', 'pointer'), (9, 'out_room', 'pointer')], 'returns_size': True}, 'xyg_y_axis_left_room': {'node_name': 'xyYAxisLeftRoom', 'arguments': [(2, 'title', 'pointer'), (3, 'title_len', 'size'), (6, 'out_room', 'pointer')], 'returns_size': True}, 'xyg_y_tick_label_extent': {'node_name': 'xyYTickLabelExtent', 'arguments': [(0, 'label_lens', 'pointer'), (1, 'labels', 'pointer'), (2, 'labels_len', 'size'), (3, 'n', 'size'), (6, 'out_extent', 'pointer')], 'returns_size': True}, 'xyg_zone_maps': {'node_name': 'xyZoneMaps', 'arguments': [(0, 'data', 'pointer'), (1, 'len', 'size'), (3, 'out_min', 'pointer'), (4, 'out_max', 'pointer'), (5, 'out_count', 'pointer'), (6, 'out_null_count', 'pointer'), (7, 'out_sum', 'pointer'), (8, 'out_sum_sq', 'pointer'), (9, 'out_positive_min', 'pointer'), (10, 'out_positive_max', 'pointer')], 'returns_size': True}, 'xyg_zone_maps_pair': {'node_name': 'xyZoneMapsPair', 'arguments': [(0, 'x', 'pointer'), (1, 'y', 'pointer'), (2, 'len', 'size'), (4, 'out_x', 'pointer'), (5, 'out_y', 'pointer')], 'returns_size': True}}


class GeneratedAbiTraceFault(RuntimeError):
    """Sentinel raised only by the generated test trace proxy."""


def _trace_pointer_present(value: Any) -> bool:
    if value is None:
        return False
    scalar = getattr(value, 'value', value)
    return scalar is not None and scalar != 0


def _trace_size_value(value: Any) -> str:
    return str(int(getattr(value, 'value', value)))


class _GeneratedAbiTraceProxy:
    def __init__(self, lib: Any, observer: Any, fault_symbols: Any) -> None:
        self._lib = lib
        self._observer = observer
        self._fault_symbols = frozenset(fault_symbols)
        self._call_index = 0

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._lib, name)
        metadata = ABI_TRACE_METADATA.get(name)
        if metadata is None:
            return target

        def traced(*args: Any) -> Any:
            self._call_index += 1
            shaped = {}
            for index, argument_name, kind in metadata['arguments']:
                value = args[index]
                if kind == 'pointer':
                    shaped[argument_name] = {
                        'kind': 'pointer',
                        'present': _trace_pointer_present(value),
                    }
                else:
                    shaped[argument_name] = {
                        'kind': 'size',
                        'value': _trace_size_value(value),
                    }
            event = {
                'call_index': self._call_index,
                'symbol': name,
                'arguments': shaped,
            }
            if name in self._fault_symbols:
                event['outcome'] = 'injected_fault'
                self._observer(event)
                raise GeneratedAbiTraceFault(f'XYG_ABI_TRACE_FAULT:{name}')
            try:
                result = target(*args)
            except BaseException as exc:
                event['outcome'] = 'error'
                event['error_type'] = type(exc).__name__
                self._observer(event)
                raise
            event['outcome'] = 'ok'
            if metadata['returns_size']:
                event['returned_size'] = str(int(result))
            self._observer(event)
            return result

        return traced


def trace_generated_abi(lib: Any, observer: Any, fault_symbols: Any = ()) -> Any:
    """Wrap a bound library for privacy-bounded test-only ABI tracing."""

    return _GeneratedAbiTraceProxy(lib, observer, fault_symbols)


def trace_generated_abi_from_env(lib: Any) -> Any:
    """Enable JSONL tracing only when the executable-proof env is set."""

    path = os.environ.get('XYG_ABI_TRACE_FILE')
    if not path:
        return lib
    journey = os.environ.get('XYG_ABI_TRACE_JOURNEY', 'unclassified')
    faults = filter(None, os.environ.get('XYG_ABI_TRACE_FAULT', '').split(','))

    def observe(event: dict[str, Any]) -> None:
        record = {'host': 'python', 'journey': journey, **event}
        payload = (json.dumps(record, sort_keys=True, separators=(',', ':')) + '\n').encode()
        fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)

    return trace_generated_abi(lib, observe, faults)


def bind_abi_version(lib: ctypes.CDLL):
    function = lib.xyg_abi_version
    function.restype = ctypes.c_uint32
    function.argtypes = []
    return function


def bind_generated_abi(lib: ctypes.CDLL) -> None:
    # int32_t xyg_aligned_window(double lo, double hi, double extent_lo, double extent_hi, double pad, double * out_lo, double * out_hi)
    function = lib.xyg_aligned_window
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_argsort_stable(const double * data, size_t len, uint32_t * out, size_t capacity)
    function = lib.xyg_argsort_stable
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_array_is_categorical(uint8_t dtype_kind, int32_t object_real_numeric)
    function = lib.xyg_array_is_categorical
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint8, ctypes.c_int32]
    # size_t xyg_arrow_end_decoration(double px, double py, double dx, double dy, const uint8_t * style, size_t style_len, double head, double * out_x, double * out_y, size_t capacity, int32_t * out_kind)
    function = lib.xyg_arrow_end_decoration
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_arrow_geometry(double x0, double y0, double x1, double y1, const double * style, size_t style_len, double * out, size_t out_len)
    function = lib.xyg_arrow_geometry
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_arrow_shaft_points(double p0x, double p0y, double p1x, double p1y, double cx, double cy, int32_t has_control, int32_t elbow, size_t samples, double * out_x, double * out_y, size_t capacity)
    function = lib.xyg_arrow_shaft_points
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_int32, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_arrow_shapes(double x0, double y0, double x1, double y1, const double * style, size_t style_len, const uint8_t * head_style, size_t head_style_len, const uint8_t * tail_style, size_t tail_style_len, double head_size, double width_start, double width_end, int32_t elbow_authoring, int32_t * out_meta, size_t meta_len, double * out_x, double * out_y, size_t capacity)
    function = lib.xyg_arrow_shapes
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_arrow_style_pack(const uint8_t * start_offset, size_t start_offset_len, double start_angle, double end_angle, double curve, double gap_start, double gap_end, const uint8_t * label_clear, size_t label_clear_len, double elbow, double * out, size_t out_len)
    function = lib.xyg_arrow_style_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_arrow_taper_polygon(const double * x, const double * y, size_t n, double width_start, double width_end, double * out_x, double * out_y, size_t capacity)
    function = lib.xyg_arrow_taper_polygon
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_arrow_trim_polyline_end(const double * x, const double * y, size_t n, double trim, double * out_x, double * out_y, size_t capacity)
    function = lib.xyg_arrow_trim_polyline_end
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_auto_domain(uint32_t has_bounds, double lo, double hi, double * out_lo, double * out_hi)
    function = lib.xyg_auto_domain
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_bar_stack(const double * pos, size_t n_items, const double * values, size_t n_series, const double * width, size_t width_len, const double * base, size_t base_len, uint32_t mode, uint32_t orientation, double * out_x0, double * out_x1, double * out_y0, double * out_y1)
    function = lib.xyg_bar_stack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_bin_2d(const double * x, const double * y, size_t len, double x0, double x1, double y0, double y1, size_t w, size_t h, float * out)
    function = lib.xyg_bin_2d
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_bin_2d_f32(const float * x, const float * y, size_t len, double x0, double x1, double y0, double y1, size_t w, size_t h, float * out)
    function = lib.xyg_bin_2d_f32
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_bin_2d_indices(const double * x, const double * y, size_t len, double x0, double x1, double y0, double y1, size_t w, size_t h, float * grid, uint32_t * idx)
    function = lib.xyg_bin_2d_indices
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # Buffer contract: out: out_capacity >= checked(w * h * 4) bytes and total bytes <= isize::MAX; null output, zero dimensions, arithmetic overflow, impossible slice size, or short capacity returns 0 before output access; success returns 1
    # int32_t xyg_bin_2d_mean_color(const double * x, const double * y, size_t len, const uint8_t * idx, const uint8_t * rgba, const uint8_t * lut, size_t lut_len, double x0, double x1, double y0, double y1, size_t w, size_t h, uint8_t * out, size_t out_capacity)
    function = lib.xyg_bin_2d_mean_color
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_bin_2d_sample_range(const double * x, const double * y, size_t len, double x0, double x1, double y0, double y1, size_t w, size_t h, uint64_t seed, uint64_t threshold, float * grid, uint32_t * out, size_t capacity)
    function = lib.xyg_bin_2d_sample_range
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_bin_2d_stratified_sample_range_u8_counted(const double * x, const double * y, const uint8_t * groups, size_t len, const uint64_t * counts, size_t n_groups, double x0, double x1, double y0, double y1, size_t w, size_t h, uint64_t seed, double fraction, uint64_t min_count, float * grid, uint32_t * out, size_t capacity)
    function = lib.xyg_bin_2d_stratified_sample_range_u8_counted
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_double, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_binned_ecdf(const double * values, size_t len, size_t n_bins, double lo, double hi, int32_t use_range, double * out_x, double * out_cumulative, size_t capacity)
    function = lib.xyg_binned_ecdf
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_box_geometry(const double * values, size_t values_len, const size_t * offsets, size_t offsets_len, const double * centers, size_t centers_len, double width, uint32_t orientation, int32_t show_outliers, size_t * out_n_outliers, uint32_t * active_groups, double * group_records, size_t * outlier_offsets, double * outlier_records, size_t group_cap, size_t outlier_cap)
    function = lib.xyg_box_geometry
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_uint32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t]
    # int32_t xyg_box_stats(const double * data, size_t len, double * out_stats, double * out_outliers, size_t outliers_cap, size_t * out_n_outliers)
    function = lib.xyg_box_stats
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_categorical_palette(const uint32_t * entry_lens, const uint8_t * entry_texts, size_t entry_texts_len, size_t n_entries, size_t n_categories, uint32_t * out_lens, uint8_t * out_texts, size_t out_texts_cap)
    function = lib.xyg_categorical_palette
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_categorical_palette_map_resolve(const uint32_t * category_lens, const uint8_t * category_texts, size_t category_texts_len, size_t n_categories, const uint32_t * map_key_lens, const uint8_t * map_key_texts, size_t map_key_texts_len, const uint32_t * map_value_lens, const uint8_t * map_value_texts, size_t map_value_texts_len, size_t n_map, const uint32_t * default_lens, const uint8_t * default_texts, size_t default_texts_len, size_t n_default, uint32_t * out_lens, uint8_t * out_texts, size_t out_texts_cap, uint32_t * out_unmapped, uint32_t * out_map_exhausted)
    function = lib.xyg_categorical_palette_map_resolve
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # uint32_t xyg_category_code_width(uint64_t n_categories)
    function = lib.xyg_category_code_width
    function.restype = ctypes.c_uint32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_category_label_kind_from_probe(uint8_t probe)
    function = lib.xyg_category_label_kind_from_probe
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint8]
    # int32_t xyg_category_label_kinds_from_probes(const uint8_t * probes, size_t n, uint8_t * out)
    function = lib.xyg_category_label_kinds_from_probes
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_category_labels_packed(const uint8_t * kinds, const uint32_t * in_lens, const uint8_t * in_texts, size_t in_texts_len, size_t n, uint32_t * out_lens, uint8_t * out_texts, size_t out_texts_cap)
    function = lib.xyg_category_labels_packed
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # uint64_t xyg_category_palette_rows(uint64_t n_categories)
    function = lib.xyg_category_palette_rows
    function.restype = ctypes.c_uint64
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_chunked_columns_cancel_before(uint64_t store, uint64_t generation)
    function = lib.xyg_chunked_columns_cancel_before
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64]
    # int32_t xyg_chunked_columns_free(uint64_t store)
    function = lib.xyg_chunked_columns_free
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # uint64_t xyg_chunked_columns_open(const uint8_t * path, size_t path_len)
    function = lib.xyg_chunked_columns_open
    function.restype = ctypes.c_uint64
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_chunked_columns_overview(uint64_t store, size_t max_points, uint64_t * out_rows, double * out_x, double * out_y, uint64_t * out_stats)
    function = lib.xyg_chunked_columns_overview
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_uint64, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_chunked_columns_read(uint64_t store, double x0, double x1, double y0, double y1, int32_t use_y, uint64_t budget_bytes, uint64_t generation, double * out_x, double * out_y, size_t capacity, uint64_t * out_stats)
    function = lib.xyg_chunked_columns_read
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_uint64, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_chunked_columns_read_page(uint64_t store, double x0, double x1, double y0, double y1, int32_t use_y, uint64_t budget_bytes, uint64_t generation, uint32_t cursor, double * out_x, double * out_y, size_t capacity, uint64_t * out_stats)
    function = lib.xyg_chunked_columns_read_page
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_uint64, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # uint64_t xyg_chunked_columns_rows(uint64_t store)
    function = lib.xyg_chunked_columns_rows
    function.restype = ctypes.c_uint64
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_clip_quantize_u8(const double * values, size_t values_len, uint8_t * out, size_t out_len)
    function = lib.xyg_clip_quantize_u8
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_color_channel_direct_rgba_f64_categorical(const uint32_t * codes, size_t n, const uint32_t * entry_lens, const uint8_t * entry_texts, size_t entry_texts_len, size_t n_entries, double * out, size_t out_cap)
    function = lib.xyg_color_channel_direct_rgba_f64_categorical
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_color_channel_direct_rgba_f64_continuous(const double * values, size_t n, double lo, double hi, const uint8_t * stops, size_t stop_count, double * out, size_t out_cap)
    function = lib.xyg_color_channel_direct_rgba_f64_continuous
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_colormap_custom_stops_resolve_gradient(const uint8_t * css, size_t css_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_colormap_custom_stops_resolve_gradient
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_colormap_custom_stops_resolve_list(const uint32_t * css_lens, const uint8_t * css_texts, size_t css_texts_len, const double * positions, size_t n, uint8_t * out, size_t out_cap)
    function = lib.xyg_colormap_custom_stops_resolve_list
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_colormap_is_builtin(const uint8_t * name, size_t name_len)
    function = lib.xyg_colormap_is_builtin
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_colormap_lut(const double * t, size_t n, const uint8_t * stops, size_t stop_count, uint8_t * out)
    function = lib.xyg_colormap_lut
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_colormap_lut_rgba8(const uint8_t * name, size_t name_len, const uint8_t * custom_stops, size_t custom_stop_count, size_t n_texels, uint8_t * out_rgba, size_t out_cap)
    function = lib.xyg_colormap_lut_rgba8
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_colormap_resolved_stops_admit(const uint8_t * stops, size_t stop_count)
    function = lib.xyg_colormap_resolved_stops_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # Buffer contract: out: out_capacity >= checked(w * h * 4) bytes and total bytes <= isize::MAX; null output, zero dimensions, arithmetic overflow, impossible slice size, or short capacity returns 0 before output access; success returns 1
    # int32_t xyg_colormap_rgba(const double * raw, size_t w, size_t h, const uint8_t * stops, size_t stop_count, uint8_t alpha, uint8_t * out, size_t out_capacity)
    function = lib.xyg_colormap_rgba
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint8, ctypes.c_void_p, ctypes.c_size_t]
    # Buffer contract: out: out_capacity >= checked(w * h * 4) bytes and total bytes <= isize::MAX; null output, zero dimensions, arithmetic overflow, impossible slice size, or short capacity returns 0 before output access; success returns 1
    # int32_t xyg_colormap_rgba_canonical(const double * raw, size_t w, size_t h, double domain_lo, double domain_hi, const uint8_t * stops, size_t stop_count, uint8_t alpha, uint8_t * out, size_t out_capacity)
    function = lib.xyg_colormap_rgba_canonical
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint8, ctypes.c_void_p, ctypes.c_size_t]
    # uint32_t xyg_colormap_stops(const uint8_t * name, size_t name_len, uint8_t * out, size_t cap)
    function = lib.xyg_colormap_stops
    function.restype = ctypes.c_uint32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_compat_colorbar_extra(uint32_t kind, int32_t has_label, int32_t pad_zero, double * out_right, double * out_bottom)
    function = lib.xyg_compat_colorbar_extra
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_uint32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_compat_combine_plot(double width, double height, const double * authored_padding, double title_room, double x_top_room, double x_bottom_room, double x_measured_bottom, uint32_t colorbar_kind, int32_t colorbar_has_label, int32_t colorbar_pad_zero, int32_t has_right_y, double y_left_room, double edge_left, double edge_right, const double * x_rooms_final, int32_t polar, uint32_t legend_side, double legend_room, double polar_label_room, int32_t authored_padding_flag, int32_t y_titled, int32_t keeps_bottom, double * out)
    function = lib.xyg_compat_combine_plot
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_uint32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p]
    # size_t xyg_compat_default_padding(int32_t compact, double * out_pad)
    function = lib.xyg_compat_default_padding
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_compat_is_compact(double width)
    function = lib.xyg_compat_is_compact
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_double]
    # size_t xyg_compat_right_y_room(int32_t compact, double * out_room)
    function = lib.xyg_compat_right_y_room
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_int32, ctypes.c_void_p]
    # size_t xyg_compat_title_room(int32_t compact, double block_height, double pad, int32_t automatic_y, double y, double * out_room)
    function = lib.xyg_compat_title_room
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_double, ctypes.c_void_p]
    # size_t xyg_compat_title_wrap_width(double width, double left, double right, double * out_width)
    function = lib.xyg_compat_title_wrap_width
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p]
    # size_t xyg_compat_x_axis_side_room(int32_t compact, int32_t top, double measured, double * out_room, double * out_measured_bottom)
    function = lib.xyg_compat_x_axis_side_room
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_continuous_domain(const double * data, size_t len, double * out_lo, double * out_hi)
    function = lib.xyg_continuous_domain
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_contour_levels(const double * data, size_t len, size_t n_levels, double * out, size_t capacity)
    function = lib.xyg_contour_levels
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_contourf_bands(const double * z, size_t rows, size_t cols, const double * xpos, const double * ypos, const double * edges, size_t n_edges, uint8_t extend_min, uint8_t extend_max, double * out_x0, double * out_y0, double * out_x1, double * out_y1, double * out_x2, double * out_y2, int64_t * out_slots, size_t capacity)
    function = lib.xyg_contourf_bands
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_contourf_densify(const double * z, size_t rows, size_t cols, const double * xpos, const double * ypos, double * out_z, double * out_x, double * out_y, size_t out_z_cap, size_t out_x_cap, size_t out_y_cap, size_t * out_rows, size_t * out_cols)
    function = lib.xyg_contourf_densify
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_correlation(const double * x, const double * y, size_t len, size_t max_lag, int32_t normalize, double * out_lag, double * out_correlation)
    function = lib.xyg_correlation
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_css_check(uint32_t kind, const uint8_t * prop, size_t prop_len, const uint8_t * value, size_t value_len, float * out_rgba)
    function = lib.xyg_css_check
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_css_color_rgba(const uint8_t * css, size_t len, float opacity, uint8_t * out_rgba)
    function = lib.xyg_css_color_rgba
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_float, ctypes.c_void_p]
    # int32_t xyg_css_is_functional(const uint8_t * css, size_t len)
    function = lib.xyg_css_is_functional
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_curve_flatten(const double * x, const double * y, size_t n, size_t bezier_steps, double * out_x, double * out_y, size_t capacity)
    function = lib.xyg_curve_flatten
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # Buffer contract: out: query-first packed straight-alpha RGBA8 rows; out_cap >= checked(xyg_default_palette_rows * 4) bytes; null with zero capacity queries the required count; short capacity returns that count without writing; null with nonzero capacity returns usize::MAX
    # size_t xyg_default_palette_rgba8(uint8_t * out, size_t out_cap)
    function = lib.xyg_default_palette_rgba8
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_default_palette_rows()
    function = lib.xyg_default_palette_rows
    function.restype = ctypes.c_size_t
    function.argtypes = []
    # Buffer contract: out: query-first concatenated fixed-width lowercase #rrggbb rows; out_cap >= checked(xyg_default_palette_rows * 7) bytes; null with zero capacity queries the required count; short capacity returns that count without writing; null with nonzero capacity returns usize::MAX
    # size_t xyg_default_palette_utf8(uint8_t * out, size_t out_cap)
    function = lib.xyg_default_palette_utf8
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # uint32_t xyg_default_palette_version()
    function = lib.xyg_default_palette_version
    function.restype = ctypes.c_uint32
    function.argtypes = []
    # size_t xyg_delaunay_triangles(const double * x, const double * y, size_t len, int64_t * out, size_t capacity)
    function = lib.xyg_delaunay_triangles
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_density_bin_coord_endpoints(int32_t x_linear, int32_t y_linear, double xr0, double xr1, double yr0, double yr1, double bx0, double bx1, double by0, double by1, double * out_x_c0, double * out_x_c1, double * out_y_c0, double * out_y_c1)
    function = lib.xyg_density_bin_coord_endpoints
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_density_bin_window(int32_t x_linear, int32_t y_linear, double xr0, double xr1, double yr0, double yr1, double x_c0, double x_c1, double y_c0, double y_c1, double * out)
    function = lib.xyg_density_bin_window
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p]
    # int32_t xyg_density_categorical_color_wire_admit(int32_t categorical, int32_t has_channel)
    function = lib.xyg_density_categorical_color_wire_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32]
    # int32_t xyg_density_channels_dropped_compat(int32_t dropped_count)
    function = lib.xyg_density_channels_dropped_compat
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32]
    # int32_t xyg_density_color_classify(int32_t channel_mode, int32_t codes_present, int32_t codes_u8, int32_t has_counts, int32_t * out_color_mode, int32_t * out_categorical, int32_t * out_compact_categorical, int32_t * out_stratified_counts)
    function = lib.xyg_density_color_classify
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_density_constant_color_wire_admit(int32_t has_channel, const uint8_t * mode, size_t mode_len, int32_t has_constant)
    function = lib.xyg_density_constant_color_wire_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32]
    # int32_t xyg_density_dropped_channel_wire_admit(const uint8_t * channel, size_t channel_len, int32_t mean_color_aggregates)
    function = lib.xyg_density_dropped_channel_wire_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32]
    # int32_t xyg_density_emit_meta(int32_t cartesian, int32_t x_linear, int32_t y_linear, int32_t categorical, int32_t compact_categorical, int32_t stratified_counts, int32_t x_has_nulls, int32_t y_has_nulls, int32_t point_overlay, int32_t grid_from_pyramid, int32_t x_memmapped, int32_t y_memmapped, int32_t has_pyramid_resource, int32_t force_bin2d, int32_t force_pyramid, int32_t color_mode, double x_min, double x_max, double y_min, double y_max, double xr0, double xr1, double yr0, double yr1, double x_c0, double x_c1, double y_c0, double y_c1, uint64_t n_points, void * out)
    function = lib.xyg_density_emit_meta
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_uint64, ctypes.c_void_p]
    # size_t xyg_density_format_binning(int32_t exact, int32_t level, int32_t tiles, int32_t upsampled, uint8_t * out, size_t out_cap)
    function = lib.xyg_density_format_binning
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_density_full_identity(int32_t categorical, int32_t compact_categorical, int32_t x_has_nulls, int32_t y_has_nulls, double x_min, double x_max, double y_min, double y_max, double xr0, double xr1, double yr0, double yr1)
    function = lib.xyg_density_full_identity
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double]
    # int32_t xyg_density_grid_path(int32_t oversized, int32_t full_identity, int32_t point_overlay, int32_t compact_categorical, int32_t stratified_counts)
    function = lib.xyg_density_grid_path
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    # int32_t xyg_density_grid_path_identity_state(int32_t grid_path)
    function = lib.xyg_density_grid_path_identity_state
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32]
    # int32_t xyg_density_log_u8(const float * grid, size_t len, uint8_t * out, double * out_max)
    function = lib.xyg_density_log_u8
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_density_mean_color_rgba_wire_admit(int32_t has_pyramid_rgba, int32_t has_bin_colors)
    function = lib.xyg_density_mean_color_rgba_wire_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32]
    # int32_t xyg_density_mean_color_wire_admit(int32_t has_channel, const uint8_t * mode, size_t mode_len)
    function = lib.xyg_density_mean_color_wire_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_density_overlay_omitted_wire(uint32_t overlay_omitted, int32_t point_overlay, uint8_t * out, size_t out_cap)
    function = lib.xyg_density_overlay_omitted_wire
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_uint32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_density_overlay_opacity(double authored, double * out)
    function = lib.xyg_density_overlay_opacity
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_double, ctypes.c_void_p]
    # size_t xyg_density_pyramid_preflight(int32_t x_linear, int32_t y_linear, uint64_t n_points, int32_t has_pyramid_resource, int32_t x_memmapped, int32_t y_memmapped, int32_t force_pyramid, int32_t force_bin2d, uint32_t * out)
    function = lib.xyg_density_pyramid_preflight
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_uint64, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_density_reduction_kind(const uint8_t * binning, size_t binning_len)
    function = lib.xyg_density_reduction_kind
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # Buffer contract: out: out_capacity >= checked(w * h * 4) bytes and total bytes <= isize::MAX; null output, zero dimensions, arithmetic overflow, impossible slice size, or short capacity returns 0 before output access; success returns 1
    # int32_t xyg_density_rgba(const uint8_t * encoded, size_t w, size_t h, double maximum, const uint8_t * stops, size_t stop_count, double opacity, uint8_t * out, size_t out_capacity)
    function = lib.xyg_density_rgba
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t]
    # Buffer contract: out: out_capacity >= checked(w * h * 4) bytes and total bytes <= isize::MAX; null output, zero dimensions, arithmetic overflow, impossible slice size, or short capacity returns 0 before output access; success returns 1
    # int32_t xyg_density_rgba_linear(const double * counts, size_t w, size_t h, double maximum, const uint8_t * stops, size_t stop_count, double opacity, uint8_t * out, size_t out_capacity)
    function = lib.xyg_density_rgba_linear
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_density_trace_color_classify(int32_t has_channel, const uint8_t * mode, size_t mode_len, int32_t codes_present, int32_t codes_u8, int32_t has_counts, int32_t * out_color_mode, int32_t * out_categorical, int32_t * out_compact_categorical, int32_t * out_stratified_counts)
    function = lib.xyg_density_trace_color_classify
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_density_uses_channel_colormap(int32_t has_channel, const uint8_t * mode, size_t mode_len)
    function = lib.xyg_density_uses_channel_colormap
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_density_wasm_density_wire_kind(int32_t split_payload, uint64_t wasm_source_count, int32_t has_density_tier)
    function = lib.xyg_density_wasm_density_wire_kind
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_uint64, ctypes.c_int32]
    # int32_t xyg_density_wasm_eligible(int32_t cartesian, int32_t x_linear, int32_t y_linear, int32_t color_mode, int32_t x_has_nulls, int32_t y_has_nulls, uint64_t n_points)
    function = lib.xyg_density_wasm_eligible
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_uint64]
    # int32_t xyg_density_wasm_source_admit(int32_t split_payload, int32_t wasm_eligible)
    function = lib.xyg_density_wasm_source_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32]
    # size_t xyg_direct_rgba_admit(const double * values, size_t n, size_t components, double * out, size_t capacity)
    function = lib.xyg_direct_rgba_admit
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_drill_decision(uint64_t visible, double budget, int32_t in_drill, double exit_factor, int32_t * out_exact)
    function = lib.xyg_drill_decision
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_double, ctypes.c_int32, ctypes.c_double, ctypes.c_void_p]
    # int32_t xyg_encode_f32(const double * data, size_t len, double offset, double scale, float * out)
    function = lib.xyg_encode_f32
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_void_p]
    # size_t xyg_encode_jpeg(const uint8_t * pixels, size_t n, size_t width, size_t height, size_t channels, int32_t quality, uint8_t * out, size_t out_cap)
    function = lib.xyg_encode_jpeg
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_encode_png(const uint8_t * pixels, size_t n, size_t width, size_t height, size_t channels, int32_t mode, int32_t compression, uint8_t * out, size_t out_cap)
    function = lib.xyg_encode_png
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_encode_webp(const uint8_t * pixels, size_t n, size_t width, size_t height, size_t channels, uint8_t * out, size_t out_cap)
    function = lib.xyg_encode_webp
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_encoded_column_meta(double offset, double lo, double hi, const uint8_t * kind, size_t kind_len, double * out, size_t out_cap)
    function = lib.xyg_encoded_column_meta
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_f32_safe_scale(double offset, double lo, double hi, double * out_scale)
    function = lib.xyg_f32_safe_scale
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p]
    # size_t xyg_factorize_display_labels(const uint32_t * label_lens, const uint8_t * label_texts, size_t label_texts_len, size_t n, uint8_t * out_codes, size_t out_codes_cap, uint32_t * out_code_width, uint32_t * out_category_lens, uint8_t * out_category_texts, size_t out_category_texts_cap, size_t category_lens_cap)
    function = lib.xyg_factorize_display_labels
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t]
    # size_t xyg_factorize_fixed(const uint8_t * data, size_t len, size_t width, uint32_t * out_codes, uint32_t * out_unique_indices)
    function = lib.xyg_factorize_fixed
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_factorize_fixed_u8(const uint8_t * data, size_t len, size_t width, uint8_t * out_codes, uint32_t * out_unique_indices, size_t unique_capacity)
    function = lib.xyg_factorize_fixed_u8
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_factorize_fixed_u8_counts(const uint8_t * data, size_t len, size_t width, uint8_t * out_codes, uint32_t * out_unique_indices, uint64_t * out_counts, size_t unique_capacity)
    function = lib.xyg_factorize_fixed_u8_counts
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_factorize_unicode1_u8_counts(const uint32_t * data, size_t len, int32_t swap_endian, uint8_t * out_codes, uint32_t * out_unique_indices, uint64_t * out_counts, size_t unique_capacity)
    function = lib.xyg_factorize_unicode1_u8_counts
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_factorize_use_native_fixed(const uint8_t * data, size_t n_rows, uint32_t record_width)
    function = lib.xyg_factorize_use_native_fixed
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32]
    # int32_t xyg_factorize_use_native_probe(uint32_t distinct, uint32_t probe_len, uint32_t record_width)
    function = lib.xyg_factorize_use_native_probe
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32]
    # int32_t xyg_figure_autorange(const uint8_t * input, size_t len, double * out_lo, double * out_hi)
    function = lib.xyg_figure_autorange
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_fold_codes_u8(const uint32_t * codes, size_t n, uint32_t n_palette, uint8_t * out)
    function = lib.xyg_fold_codes_u8
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_void_p]
    # uint32_t xyg_geo_column_crs(uint64_t handle)
    function = lib.xyg_geo_column_crs
    function.restype = ctypes.c_uint32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_geo_column_free(uint64_t handle)
    function = lib.xyg_geo_column_free
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # uint32_t xyg_geo_column_geometry(uint64_t handle)
    function = lib.xyg_geo_column_geometry
    function.restype = ctypes.c_uint32
    function.argtypes = [ctypes.c_uint64]
    # size_t xyg_geo_column_len(uint64_t handle)
    function = lib.xyg_geo_column_len
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_uint64]
    # uint64_t xyg_geo_column_new(uint32_t geometry, uint32_t crs, const double * xy, size_t xy_len, const uint8_t * validity, size_t validity_len, const uint64_t * feature_ids, const uint32_t * offsets0, size_t offsets0_len, const uint32_t * offsets1, size_t offsets1_len, const uint32_t * offsets2, size_t offsets2_len, int32_t * out_error)
    function = lib.xyg_geo_column_new
    function.restype = ctypes.c_uint64
    function.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_geo_column_vertex_count(uint64_t handle)
    function = lib.xyg_geo_column_vertex_count
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_geometry_offset(int32_t pin_zero, double lo, double hi, double * out_offset)
    function = lib.xyg_geometry_offset
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_void_p]
    # int32_t xyg_graph_build_csr(uint64_t n_nodes, uint64_t n_edges, const uint64_t * sources, const uint64_t * targets, int32_t directed, uint64_t * out_offsets, uint64_t * out_neighbors, uint64_t neighbors_cap, uint64_t * out_neighbor_len)
    function = lib.xyg_graph_build_csr
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_graph_build_render(uint64_t n_nodes, uint64_t n_edges, const double * x, const double * y, const uint64_t * sources, const uint64_t * targets, uint64_t node_budget, uint64_t edge_budget, int32_t viewport_enabled, double vp_x0, double vp_y0, double vp_x1, double vp_y1, double * out_node_x, double * out_node_y, uint64_t * out_member_of, uint64_t * out_edge_sources, uint64_t * out_edge_targets, uint64_t * out_n_nodes, uint64_t * out_n_edges, uint32_t * out_tier, uint64_t * out_edges_kept)
    function = lib.xyg_graph_build_render
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_graph_cluster_aggregate(uint64_t n_nodes, uint64_t n_edges, const double * x, const double * y, uint64_t node_budget, uint64_t edge_budget, double * out_x, double * out_y, uint64_t * out_count, uint64_t * out_member_of, uint32_t * out_tier, uint64_t * out_edges_kept)
    function = lib.xyg_graph_cluster_aggregate
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_graph_compound_bounds(uint64_t n, const double * x, const double * y, const uint64_t * parents, const uint8_t * validity, uint64_t * parent_of, uint8_t * is_compound, double * xmin, double * xmax, double * ymin, double * ymax)
    function = lib.xyg_graph_compound_bounds
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_graph_compound_scene(const void * descriptor, uint8_t * out, size_t out_cap)
    function = lib.xyg_graph_compound_scene
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_graph_compound_transition(uint64_t n, const uint64_t * node_ids, const uint64_t * parents, const uint8_t * validity, const uint8_t * collapsed, uint64_t target_id, uint32_t action, uint32_t lod_tier, uint8_t * out, uint8_t * out_changed)
    function = lib.xyg_graph_compound_transition
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_graph_edge_route_segments(uint64_t n_nodes, uint64_t n_edges, const double * x, const double * y, const uint64_t * sources, const uint64_t * targets, int32_t directed, double separation, double loop_radius, double arrow_size, double * out_x0, double * out_y0, double * out_x1, double * out_y1, uint64_t * out_edge_index, uint64_t * out_n_segments)
    function = lib.xyg_graph_edge_route_segments
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_graph_force_create(uint64_t n_nodes, uint64_t n_edges, const uint64_t * sources, const uint64_t * targets, const double * in_x, const double * in_y, uint64_t seed, uint32_t algorithm, uint64_t * out_handle)
    function = lib.xyg_graph_force_create
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint32, ctypes.c_void_p]
    # int32_t xyg_graph_force_create_cose(const void * descriptor, uint64_t n_nodes, uint64_t n_edges, const uint64_t * sources, const uint64_t * targets, uint64_t seed, uint64_t * out_handle)
    function = lib.xyg_graph_force_create_cose
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_graph_force_destroy(uint64_t handle)
    function = lib.xyg_graph_force_destroy
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_graph_force_tick(uint64_t handle, uint64_t n_nodes, uint32_t steps, double * out_x, double * out_y, double * out_alpha)
    function = lib.xyg_graph_force_tick
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_graph_label_accept(uint64_t n, const double * priorities, uint64_t budget, double floor, uint8_t * out, uint64_t * out_count)
    function = lib.xyg_graph_label_accept
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_graph_layout(uint32_t layout, uint64_t n_nodes, uint64_t n_edges, const uint64_t * sources, const uint64_t * targets, const double * in_x, const double * in_y, const uint64_t * roots, uint64_t n_roots, uint64_t seed, double * out_x, double * out_y)
    function = lib.xyg_graph_layout
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint32, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_graph_lod_decision(uint64_t n_nodes, uint64_t n_edges, uint64_t node_budget, uint64_t edge_budget, uint32_t * out_tier, uint64_t * out_edges_kept)
    function = lib.xyg_graph_lod_decision
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_graph_projection_copy_edge_ids(uint64_t handle, uint8_t * output, uint64_t capacity)
    function = lib.xyg_graph_projection_copy_edge_ids
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_uint64]
    # int32_t xyg_graph_projection_copy_endpoints(uint64_t handle, uint64_t * out_sources, uint64_t * out_targets, uint64_t capacity)
    function = lib.xyg_graph_projection_copy_endpoints
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64]
    # int32_t xyg_graph_projection_copy_node_ids(uint64_t handle, uint8_t * output, uint64_t capacity)
    function = lib.xyg_graph_projection_copy_node_ids
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_uint64]
    # int32_t xyg_graph_projection_copy_parents(uint64_t handle, uint64_t * out_parents, uint8_t * out_validity, uint64_t capacity)
    function = lib.xyg_graph_projection_copy_parents
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64]
    # int32_t xyg_graph_projection_counts(uint64_t handle, uint64_t * out_nodes, uint64_t * out_edges, uint32_t * out_directed)
    function = lib.xyg_graph_projection_counts
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_graph_projection_create(const void * descriptor, uint64_t * out_handle)
    function = lib.xyg_graph_projection_create
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_graph_projection_destroy(uint64_t handle)
    function = lib.xyg_graph_projection_destroy
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # uint64_t xyg_graph_sample_edges(uint64_t n_edges, uint64_t budget, uint64_t * out_indices)
    function = lib.xyg_graph_sample_edges
    function.restype = ctypes.c_uint64
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_graph_semantic_legend(uint32_t version, uint32_t theme, uint64_t n, const uint8_t * classes, const uint8_t * epistemic, const uint8_t * statuses, uint64_t capacity, uint8_t * out_field, uint8_t * out_value, uint8_t * out_rgba, uint8_t * out_shape, uint64_t * out_count)
    function = lib.xyg_graph_semantic_legend
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_graph_semantic_style_resolve(uint32_t version, uint32_t theme, uint64_t n, const uint8_t * classes, const uint8_t * epistemic, const uint8_t * statuses, const double * metric, const uint32_t * flags, int32_t edge, uint8_t * fill_rgba, uint8_t * stroke_rgba, uint8_t * halo_rgba, float * size, float * width, float * opacity, uint8_t * shape, uint8_t * dash, uint8_t * arrow, uint8_t * state, double * out_domain_lo, double * out_domain_hi)
    function = lib.xyg_graph_semantic_style_resolve
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_graph_visual_state_resolve(uint64_t n, const uint32_t * flags, uint8_t * out)
    function = lib.xyg_graph_visual_state_resolve
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_hash_row_ids(const uint64_t * ids, size_t len, uint64_t seed, uint64_t * out)
    function = lib.xyg_hash_row_ids
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_void_p]
    # Buffer contract: out: out_capacity >= checked(w * h * 4) bytes and total bytes <= isize::MAX; null output, zero dimensions, arithmetic overflow, impossible slice size, or short capacity returns 0 before output access; success returns 1
    # int32_t xyg_heatmap_rgba(const double * raw, size_t w, size_t h, const uint8_t * stops, size_t stop_count, uint8_t alpha, uint8_t * out, size_t out_capacity)
    function = lib.xyg_heatmap_rgba
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint8, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_hexbin(const double * x, const double * y, const double * c, size_t len, size_t grid_w, size_t grid_h, double x0, double x1, double y0, double y1, int32_t use_range, size_t mincnt, int32_t reduce, double * out_cx, double * out_cy, double * out_metric, double * out_counts, size_t capacity, double * out_dx, double * out_dy)
    function = lib.xyg_hexbin
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_size_t, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_hexbin_groups(const double * x, const double * y, const double * c, size_t len, size_t grid_w, size_t grid_h, double x0, double x1, double y0, double y1, int32_t use_range, size_t mincnt, double * out_cx, double * out_cy, double * out_counts, uint32_t * out_starts, uint32_t * out_lens, size_t cell_capacity, uint32_t * out_indices, size_t index_capacity, size_t * out_n_indices, double * out_dx, double * out_dy)
    function = lib.xyg_hexbin_groups
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_hexbin_ingress(const double * x, const double * y, const double * c, size_t len, size_t grid_w, size_t grid_h, double x0, double x1, double y0, double y1, int32_t use_range, double * out_x0, double * out_x1, double * out_y0, double * out_y1, size_t * out_grid_w, size_t * out_grid_h)
    function = lib.xyg_hexbin_ingress
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_hexbin_ring(double dx, double dy, double * out_x, double * out_y, size_t capacity)
    function = lib.xyg_hexbin_ring
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_histogram2d(const double * x, const double * y, const double * weights, size_t len, const double * x_edges, size_t x_edge_len, const double * y_edges, size_t y_edge_len, double * out)
    function = lib.xyg_histogram2d
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_histogram_bins(const double * values, size_t len, const double * edges, size_t edge_len, int32_t density, int32_t cumulative, double * out_counts)
    function = lib.xyg_histogram_bins
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p]
    # size_t xyg_histogram_edges(const double * data, size_t len, double lo, double hi, int32_t use_range, int32_t method, double * out_edges, size_t capacity)
    function = lib.xyg_histogram_edges
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_histogram_mark_edges(const double * data, size_t len, double lo, double hi, int32_t use_range, int32_t method, size_t n_bins, double * out_edges, size_t capacity)
    function = lib.xyg_histogram_mark_edges
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_int32, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_histogram_uniform(const double * data, size_t len, double lo, double hi, size_t n_bins, int32_t density, double * out_counts)
    function = lib.xyg_histogram_uniform
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_int32, ctypes.c_void_p]
    # size_t xyg_indexed_triangles(const double * x, const double * y, size_t vertex_count, const int64_t * triangles, size_t face_count, const double * values, size_t value_len, uint32_t value_mode, double * out_x0, double * out_y0, double * out_x1, double * out_y1, double * out_x2, double * out_y2, double * out_values)
    function = lib.xyg_indexed_triangles
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_is_sorted(const double * data, size_t len)
    function = lib.xyg_is_sorted
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_label_codes_first_seen(const uint32_t * label_lens, const uint8_t * label_texts, size_t label_texts_len, size_t n, uint8_t * out_codes, size_t out_codes_cap, uint32_t * out_code_width, uint32_t * out_category_lens, uint8_t * out_category_texts, size_t out_category_texts_cap, size_t category_lens_cap)
    function = lib.xyg_label_codes_first_seen
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t]
    # int32_t xyg_legend_best_loc(const double * xs, const double * ys, size_t n, const size_t * starts, size_t n_series, const uint32_t * label_lens, size_t n_labels)
    function = lib.xyg_legend_best_loc
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_legend_box_layout(double plot_x, double plot_y, double plot_w, double plot_h, const uint32_t * label_lens, const uint8_t * labels, size_t labels_len, size_t n, const uint8_t * title, size_t title_len, const uint8_t * loc, size_t loc_len, double font_size, double handlelength, double handletextpad, double handleheight, uint32_t ncols, double padding_em, double row_gap_em, const double * anchor, size_t anchor_len, double border_axes_pad, double * out_metrics, double * out_column_widths, double * out_column_offsets, size_t col_cap, uint32_t * out_name_lens, uint8_t * out_names, size_t names_cap, uint8_t * out_title, size_t title_cap, size_t * out_title_len)
    function = lib.xyg_legend_box_layout
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_legend_normalize(const double * x, const double * y, size_t len, double xlo, double xhi, double ylo, double yhi, int32_t x_reverse, int32_t y_reverse, int32_t x_scale, int32_t y_scale, double x_constant, double y_constant, double * out_x, double * out_y, size_t capacity)
    function = lib.xyg_legend_normalize
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_literal_color_rgba_f64(const uint32_t * entry_lens, const uint8_t * entry_texts, size_t entry_texts_len, size_t n_entries, double * out_rgba, size_t out_cap)
    function = lib.xyg_literal_color_rgba_f64
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_local_log_density(const double * x, const double * y, size_t len, double lo_x, double hi_x, double lo_y, double hi_y, size_t w, size_t h, float * out)
    function = lib.xyg_local_log_density
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_lod_grid_shape(int32_t px_w, int32_t px_h, uint64_t visible, double target_per_cell, int32_t * out_w, int32_t * out_h)
    function = lib.xyg_lod_grid_shape
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_uint64, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_lod_plan(uint64_t visible, double budget, int32_t in_drill, double exit_factor, int32_t px_w, int32_t px_h, double target_per_cell, int32_t * out_exact, uint32_t * out_mode, int32_t * out_grid_w, int32_t * out_grid_h)
    function = lib.xyg_lod_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_double, ctypes.c_int32, ctypes.c_double, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_m4_indices(const double * x, const double * y, size_t len, double x0, double x1, size_t n_buckets, uint32_t * out)
    function = lib.xyg_m4_indices
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_m4_points(const double * x, const double * y, size_t len, double x0, double x1, size_t n_buckets, double * out_x, double * out_y)
    function = lib.xyg_m4_points
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_marching_squares(const double * z, size_t rows, size_t cols, const double * x_coords, const double * y_coords, const double * levels, size_t n_levels, uint8_t corner_mask, double * out_x0, double * out_x1, double * out_y0, double * out_y1, double * out_levels, size_t capacity)
    function = lib.xyg_marching_squares
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint8, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_marching_triangles(const double * x, const double * y, const double * z, size_t vertex_count, const int64_t * triangles, size_t face_count, const double * levels, size_t level_count, double * out_x0, double * out_x1, double * out_y0, double * out_y1, double * out_levels, size_t capacity)
    function = lib.xyg_marching_triangles
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_marker_path_scale(double cx, double cy, double scale, const double * x, const double * y, size_t n, double * out_x, double * out_y, size_t capacity)
    function = lib.xyg_marker_path_scale
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_min_max(const double * data, size_t len, double * out_min, double * out_max)
    function = lib.xyg_min_max
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_monotone_tangents(const double * x, const double * y, size_t n, double * out_m, size_t capacity)
    function = lib.xyg_monotone_tangents
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_normalize_f32(const double * data, size_t len, double lo, double hi, int32_t nan_mode, float * out)
    function = lib.xyg_normalize_f32
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_normalize_window(double x0, double x1, double y0, double y1, int32_t require_area, double * out)
    function = lib.xyg_normalize_window
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_object_row_real_numeric_tag_from_probe(uint8_t probe)
    function = lib.xyg_object_row_real_numeric_tag_from_probe
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint8]
    # int32_t xyg_object_row_real_numeric_tags_from_probes(const uint8_t * probes, size_t n, uint8_t * out)
    function = lib.xyg_object_row_real_numeric_tags_from_probes
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_object_row_stringlike_tag_from_probe(uint8_t probe)
    function = lib.xyg_object_row_stringlike_tag_from_probe
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint8]
    # int32_t xyg_object_row_stringlike_tags_from_probes(const uint8_t * probes, size_t n, uint8_t * out)
    function = lib.xyg_object_row_stringlike_tags_from_probes
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_object_rows_all_real_numeric(const uint8_t * row_tags, size_t n)
    function = lib.xyg_object_rows_all_real_numeric
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_object_rows_all_stringlike(const uint8_t * row_tags, size_t n)
    function = lib.xyg_object_rows_all_stringlike
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_paint_effective_rgba(const double * intrinsic, size_t n, const double * artist_alpha, const double * opacity, double component_opacity, double * out)
    function = lib.xyg_paint_effective_rgba
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double, ctypes.c_void_p]
    # size_t xyg_palette_rows_rgba8(const uint32_t * entry_lens, const uint8_t * entry_texts, size_t entry_texts_len, size_t n_entries, size_t rows, uint8_t * out_rgba, size_t out_cap, uint32_t * out_unresolved, uint8_t * out_entry_unresolved, size_t entry_unresolved_cap)
    function = lib.xyg_palette_rows_rgba8
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_payload_axis_spec_attach_plan(int32_t coords_cartesian, int32_t axis_is_x, void * out)
    function = lib.xyg_payload_axis_spec_attach_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_payload_bar_compact_admit(size_t n_widths, const double * widths, size_t n_value0, const double * value0, double * out_width, double * out_value0_const, int32_t * out_has_value0_const, int32_t * out_compact)
    function = lib.xyg_payload_bar_compact_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_payload_bar_hist_emit_plan(int32_t kind, int32_t compact, size_t n_marks, int32_t style_color_is_none, int32_t x_axis_type, int32_t y_axis_type, int32_t orientation, int32_t * out_emit_bar, int32_t * out_tier_direct, size_t * out_n_marks, int32_t * out_apply_palette_default, int32_t * out_x_ship_scale, int32_t * out_y_ship_scale, int32_t * out_pos_ship_scale, int32_t * out_value_ship_scale, int32_t * out_value_axis, int32_t * out_channel_slot, int32_t * out_include_trace_styles, int32_t * out_attach_transition)
    function = lib.xyg_payload_bar_hist_emit_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_payload_base_entry_plan(int32_t has_trace_animation, size_t n_xv, int32_t style_color_is_none, int32_t x_axis_type, int32_t y_axis_type, int32_t * out_attach_animation, size_t * out_n_marks, int32_t * out_apply_palette_default, int32_t * out_x_ship_scale, int32_t * out_y_ship_scale)
    function = lib.xyg_payload_base_entry_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_payload_build_plan(int32_t split_payload, uint64_t wasm_source_count, int32_t has_density_tier, int32_t coords_cartesian, int32_t has_title_options, int32_t has_palette, int32_t has_legend_options, int32_t legend_loc_best, int32_t has_extra_legends, int32_t has_frame_sides, int32_t has_colorbar_options, int32_t show_modebar_is_false, int32_t has_export_options, int32_t show_tooltip_is_false, int32_t has_padding, int32_t has_dom, int32_t has_tooltip, int32_t has_mark_style, int32_t has_interaction, int32_t has_annotations, int32_t has_animation_options, int32_t has_graph_meta, void * out)
    function = lib.xyg_payload_build_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_uint64, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_payload_channel_materialize(int32_t role, int32_t mode, size_t n_categories, int32_t style_dtype_u8, int32_t quantize_continuous, double domain_lo, double domain_hi, size_t n_palette, const uint32_t * sel, size_t sel_len, const double * values_f64, size_t values_f64_len, const uint8_t * values_u8, size_t values_u8_len, uint8_t * out, size_t out_cap, int32_t * out_meta)
    function = lib.xyg_payload_channel_materialize
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_payload_channel_ship_plan(int32_t slot, int32_t include_trace_styles, int32_t has_color2_ch, int32_t has_color_ch, int32_t has_stroke_ch, int32_t has_style_channels, size_t * out_n_channels, void * out_channels, size_t capacity)
    function = lib.xyg_payload_channel_ship_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_payload_channel_wire_encode(int32_t role, int32_t mode, size_t n_categories, int32_t style_dtype_u8, int32_t quantize_continuous, int32_t * out_buf_kind, int32_t * out_transform, int32_t * out_mark_dtype_u8, int32_t * out_ship_palette, int32_t * out_set_n)
    function = lib.xyg_payload_channel_wire_encode
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_payload_column_gather_materialize(const uint32_t * sel, size_t sel_len, const void * columns, size_t n_columns, const double *const * values, const uint8_t *const * kinds, const uint8_t *const * axis_scales, void * out, uint8_t * out_bytes, size_t out_bytes_cap, size_t * out_bytes_len)
    function = lib.xyg_payload_column_gather_materialize
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_payload_column_ship_plan(const uint8_t * kind, size_t kind_len, int32_t x_axis_type, int32_t y_axis_type, int32_t orientation, int32_t * out_gather_policy, int32_t * out_gather_include_color, size_t * out_n_columns, int32_t * out_x_ship_scale, int32_t * out_y_ship_scale, void * out_columns, size_t capacity)
    function = lib.xyg_payload_column_ship_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_payload_density_grid_materialize(const void * input, const double * x_raw, const double * y_raw, const double * bx, const double * by, const uint8_t * color_codes, const uint64_t * color_counts, const uint8_t * color_idx, const uint8_t * color_rgba, const uint8_t * color_lut, uint8_t * out_binning, uint8_t * out_encoded, uint8_t * out_rgba, uint32_t * out_sample_sel, uint32_t * out_visible_sel, void * out)
    function = lib.xyg_payload_density_grid_materialize
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_payload_density_grid_ship_plan(int32_t ship_mean_color_rgba, int32_t ship_wasm_source, int32_t attach_sample, int32_t has_tiles, int32_t ship_constant_color, int32_t overlay_wire_rows_exceed, int32_t overlay_wire_static_raster, int32_t ship_categorical_entry_color, size_t * out_n_buffers, void * out_buffers, size_t buffer_capacity, size_t * out_n_attach, void * out_attach, size_t attach_capacity)
    function = lib.xyg_payload_density_grid_ship_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_payload_density_trace_emit_plan(int32_t has_channel, const uint8_t * mode, size_t mode_len, int32_t codes_present, int32_t codes_u8, int32_t has_counts, int32_t has_constant, int32_t cartesian, int32_t x_linear, int32_t y_linear, int32_t x_has_nulls, int32_t y_has_nulls, int32_t point_overlay, int32_t split_payload, uint32_t grid_w, uint32_t grid_h, int32_t grid_from_pyramid, int32_t has_pyramid_resource, int32_t grid_present, int32_t force_bin2d, int32_t force_pyramid, int32_t x_memmapped, int32_t y_memmapped, double x_min, double x_max, double y_min, double y_max, double xr0, double xr1, double yr0, double yr1, double bx0, double bx1, double by0, double by1, uint64_t n_points, int32_t has_pyramid_rgba, int32_t has_bin_colors, int32_t dropped_count, void * out)
    function = lib.xyg_payload_density_trace_emit_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_uint64, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p]
    # size_t xyg_payload_errorbar_indices(size_t n_segments, size_t n_points, size_t budget, int32_t * out_keep_all, uint32_t * out, size_t capacity)
    function = lib.xyg_payload_errorbar_indices
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_payload_errorbar_role_keys(size_t n_points, size_t n_output, const uint32_t * point_keys_lo, const uint32_t * point_keys_hi, const uint32_t * segment_sources, const uint32_t * segment_roles, uint32_t * out_lo, uint32_t * out_hi, int32_t * out_collision)
    function = lib.xyg_payload_errorbar_role_keys
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_payload_errorbar_role_maps(size_t n_segments, size_t n_points, uint32_t * out_sources, uint32_t * out_roles, int32_t * out_applicable)
    function = lib.xyg_payload_errorbar_role_maps
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_payload_even_indices(size_t n, size_t count, int32_t * out_keep_all, uint32_t * out, size_t capacity)
    function = lib.xyg_payload_even_indices
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_payload_heatmap_emit_plan(int32_t has_rgba_grid, size_t grid_rows, size_t grid_cols, int32_t style_colormap_is_none, int32_t borrow_heatmaps, int32_t * out_path, int32_t * out_tier_direct, size_t * out_n_marks, int32_t * out_attach_color, int32_t * out_borrow_canonical, int32_t * out_attach_encoding, int32_t * out_use_constant_colormap_fallback)
    function = lib.xyg_payload_heatmap_emit_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_payload_m4_indices(uint64_t n_points, int32_t polar, const double * x, const double * y, size_t n, double x0, double x1, size_t n_buckets, const double * bin_x, double bin_x0, double bin_x1, int32_t * out_tier, uint32_t * out, size_t capacity)
    function = lib.xyg_payload_m4_indices
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_uint64, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_payload_mesh_emit_plan(size_t n_marks, int32_t style_color_is_none, int32_t x_axis_type, int32_t y_axis_type, int32_t any_geometry_nulls, int32_t has_continuous_color, int32_t continuous_color_values_missing, int32_t * out_tier_direct, size_t * out_n_marks, int32_t * out_apply_palette_default, int32_t * out_x_ship_scale, int32_t * out_y_ship_scale, int32_t * out_channel_slot, int32_t * out_include_trace_styles, int32_t * out_attach_transition, int32_t * out_attempt_gather, int32_t * out_gather_include_color)
    function = lib.xyg_payload_mesh_emit_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_payload_nonxy_emit_plan(int32_t kind, size_t n_marks, int32_t style_color_is_none, int32_t x_axis_type, int32_t y_axis_type, int32_t * out_tier_direct, size_t * out_n_marks, int32_t * out_apply_palette_default, int32_t * out_x_ship_scale, int32_t * out_y_ship_scale, int32_t * out_channel_slot, int32_t * out_include_trace_styles, int32_t * out_attach_transition)
    function = lib.xyg_payload_nonxy_emit_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_payload_ribbon_emit_plan(size_t n_marks, int32_t style_color_is_none, int32_t x_axis_type, int32_t y_axis_type, int32_t any_geometry_nulls, int32_t has_color2_ch, int32_t * out_tier_direct, size_t * out_n_marks, int32_t * out_apply_palette_default, int32_t * out_x_ship_scale, int32_t * out_y_ship_scale, int32_t * out_channel_slot, int32_t * out_include_trace_styles, int32_t * out_attach_transition, int32_t * out_attempt_gather, int32_t * out_attach_color2)
    function = lib.xyg_payload_ribbon_emit_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_payload_sample_target_indices(size_t n, size_t target, uint64_t seed, uint32_t level, double growth, int32_t * out_keep_all, uint32_t * out, size_t capacity)
    function = lib.xyg_payload_sample_target_indices
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_uint32, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_payload_scatter_emit_plan(uint64_t n_points, int32_t polar, int32_t force_density, int32_t force_direct, int32_t per_item, size_t n_marks, int32_t has_trace_animation, int32_t x_axis_type, int32_t y_axis_type, int32_t has_transition_keys, int32_t has_tooltip_rows, size_t n_tooltip_rows, int32_t * out_emit_density, int32_t * out_clear_shipped_sel, int32_t * out_drill_mode_false, int32_t * out_set_shipped_sel, int32_t * out_tier_direct, size_t * out_n_marks, int32_t * out_apply_palette_default, int32_t * out_attach_animation, int32_t * out_x_ship_scale, int32_t * out_y_ship_scale, int32_t * out_channel_slot, int32_t * out_include_trace_styles, int32_t * out_attach_transition, int32_t * out_attach_tooltip, int32_t * out_filter_tooltip_by_sel, int32_t * out_tooltip_length_ok)
    function = lib.xyg_payload_scatter_emit_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_payload_segment_budget(double px_width)
    function = lib.xyg_payload_segment_budget
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double]
    # size_t xyg_payload_segments_emit_gather(const uint8_t * kind, size_t kind_len, size_t n_segments, size_t n_points, double px_width, int32_t * out_tier, int32_t * out_role_maps, int32_t * out_keep_all, uint32_t * out_indices, uint32_t * out_sources, uint32_t * out_roles, size_t capacity)
    function = lib.xyg_payload_segments_emit_gather
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_payload_segments_emit_plan(const uint8_t * kind, size_t kind_len, size_t n_marks, int32_t style_color_is_none, int32_t x_axis_type, int32_t y_axis_type, int32_t has_transition_keys, size_t * out_n_marks, int32_t * out_apply_palette_default, int32_t * out_x_ship_scale, int32_t * out_y_ship_scale, int32_t * out_channel_slot, int32_t * out_include_trace_styles, int32_t * out_attach_transition, int32_t * out_attempt_gather, int32_t * out_attempt_role_keys)
    function = lib.xyg_payload_segments_emit_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_payload_tier(int32_t kind, uint64_t n_points, int32_t polar, int32_t force_density, int32_t force_direct, int32_t per_item)
    function = lib.xyg_payload_tier
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_uint64, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    # int32_t xyg_payload_trace_channels_ship_attach(int32_t slot, int32_t include_trace_styles, int32_t has_color_ch, int32_t has_stroke_ch, int32_t has_style_channels, int32_t * out_ship_color, int32_t * out_ship_size, int32_t * out_ship_stroke, int32_t * out_ship_style_channels)
    function = lib.xyg_payload_trace_channels_ship_attach
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_payload_trace_emit_materialize(const void * emit_in, const uint8_t * kind, const uint8_t * x_axis_scale, const uint8_t * y_axis_scale, const uint8_t * orientation, const void * columns, const double *const * column_values, const uint8_t *const * column_kinds, const void * color_ch, const void * stroke_ch, const void * color2_ch, const void * size_ch, const void * style_channels, const double * color_f64, const double * stroke_f64, const double * color2_f64, const double * size_f64, const double * style_f64, const uint8_t * color_u8, const uint8_t * stroke_u8, const uint8_t * color2_u8, const uint8_t * size_u8, const uint8_t * style_u8, const uint32_t * transition_lo, const uint32_t * transition_hi, const double * bin_x, const double * grid_values, void * summary, void * geom_out, size_t geom_cap, void * chan_out, size_t chan_cap, uint8_t * out_bytes, size_t out_bytes_cap, size_t * out_bytes_len)
    function = lib.xyg_payload_trace_emit_materialize
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_payload_transition_entry_attach(int32_t has_trace_animation, int32_t entry_has_animation, int32_t has_trace_keys, int32_t has_key_values, int32_t has_sel, int32_t tier_direct, size_t n_marks, size_t n_trace_key_rows, size_t n_key_value_rows, size_t n_sel_rows, size_t max_rows, int32_t has_tooltip_rows, size_t n_tooltip_rows, size_t n_points, int32_t * out_attach_animation, int32_t * out_attempt_keys, int32_t * out_filter_keys_by_sel, int32_t * out_ship_keys, int32_t * out_animation_fallback, int32_t * out_attach_tooltip, int32_t * out_filter_tooltip_by_sel, int32_t * out_tooltip_length_ok)
    function = lib.xyg_payload_transition_entry_attach
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_int32, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_payload_transition_keys_admit(int32_t has_keys, int32_t tier_direct, size_t n_keys, size_t n_marks, size_t max_rows)
    function = lib.xyg_payload_transition_keys_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t]
    # size_t xyg_payload_visible_indices(const double * x, const double * y, size_t n, int32_t x_log, int32_t y_log, const double * base, int32_t has_base, int32_t prefiltered, int32_t x_has_nulls, int32_t y_has_nulls, int32_t base_has_nulls, int32_t * out_keep_all, uint32_t * out, size_t capacity)
    function = lib.xyg_payload_visible_indices
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_payload_visible_mask(const double * x, const double * y, size_t n, int32_t x_log, int32_t y_log, const double * base, int32_t has_base, uint8_t * out, size_t capacity)
    function = lib.xyg_payload_visible_mask
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_payload_visible_needed(int32_t x_log, int32_t y_log, int32_t prefiltered, int32_t x_has_nulls, int32_t y_has_nulls, int32_t has_base, int32_t base_has_nulls)
    function = lib.xyg_payload_visible_needed
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    # size_t xyg_polar_heatmap_inverse_map(const double * metrics, size_t metrics_len, double plot_x, double plot_y, double plot_w, double plot_h, uint32_t grid_w, uint32_t grid_h, double x0, double y0, double x1, double y1, double output_scale, uint32_t * out_w, uint32_t * out_h, uint32_t * out_row, uint32_t * out_col, uint32_t * out_source, size_t capacity)
    function = lib.xyg_polar_heatmap_inverse_map
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_polar_label_room(double widest, double * out_room)
    function = lib.xyg_polar_label_room
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_void_p]
    # size_t xyg_polar_layout(double plot_x, double plot_y, double plot_w, double plot_h, uint32_t theta_unit, double theta_zero, uint32_t theta_direction, double sector_start, double sector_end, uint32_t n_categories, double r_lo, double r_hi, double r_origin, double hole, uint32_t r_scale_kind, double r_constant, int32_t r_mask_nonpositive, double * out_metrics, size_t out_cap)
    function = lib.xyg_polar_layout
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_uint32, ctypes.c_double, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_uint32, ctypes.c_double, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_polar_legend_reserve(int32_t compact, int32_t loc_has_left, double width, uint32_t * out_side, double * out_room)
    function = lib.xyg_polar_legend_reserve
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_polar_legend_room(double width, double * out_room)
    function = lib.xyg_polar_legend_room
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_void_p]
    # size_t xyg_polar_position_mask(const double * metrics, size_t metrics_len, const double * theta, const double * r, size_t n, uint8_t * out, size_t out_cap)
    function = lib.xyg_polar_position_mask
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_polar_project(const double * metrics, size_t metrics_len, const double * theta, const double * r, size_t n, double * out_x, double * out_y)
    function = lib.xyg_polar_project
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_polar_theta_visible_mask(const double * metrics, size_t metrics_len, const double * theta, size_t n, uint8_t * out, size_t out_cap)
    function = lib.xyg_polar_theta_visible_mask
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_polar_visible_mask(const double * metrics, size_t metrics_len, const double * r, size_t n, uint8_t * out, size_t out_cap)
    function = lib.xyg_polar_visible_mask
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_polar_wedge_points(const double * metrics, size_t metrics_len, double theta0, double theta1, double r0, double r1, double wedge_gap, double corner_radius, uint32_t steps, double norm_lo, double norm_hi, double * out_x, double * out_y, size_t capacity)
    function = lib.xyg_polar_wedge_points
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_polygon_select(const double * x, const double * y, size_t len, const uint32_t * rows, size_t n_rows, const double * poly_x, const double * poly_y, size_t n_poly, uint32_t * out)
    function = lib.xyg_polygon_select
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_polygon_triangles(const double * x, const double * y, size_t len, int64_t * out, size_t capacity)
    function = lib.xyg_polygon_triangles
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_pyramid_append(uint64_t handle, const double * x, const double * y, size_t len)
    function = lib.xyg_pyramid_append
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_pyramid_append_from_stream(uint64_t handle, uint64_t x_handle, uint64_t y_handle, size_t tail_len)
    function = lib.xyg_pyramid_append_from_stream
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_size_t]
    # uint64_t xyg_pyramid_build(const double * x, const double * y, size_t len, double x0, double x1, double y0, double y1, uint32_t base_dim)
    function = lib.xyg_pyramid_build
    function.restype = ctypes.c_uint64
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_uint32]
    # uint64_t xyg_pyramid_build_color(const double * x, const double * y, size_t len, const uint8_t * idx, const uint8_t * rgba, const uint8_t * lut, size_t lut_len, double x0, double x1, double y0, double y1, uint32_t base_dim)
    function = lib.xyg_pyramid_build_color
    function.restype = ctypes.c_uint64
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_uint32]
    # uint64_t xyg_pyramid_build_from_stream(uint64_t x_handle, uint64_t y_handle, double x0, double x1, double y0, double y1, uint32_t base_dim)
    function = lib.xyg_pyramid_build_from_stream
    function.restype = ctypes.c_uint64
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_uint32]
    # int32_t xyg_pyramid_compose(uint64_t handle, double lo_x, double hi_x, double lo_y, double hi_y, size_t w, size_t h, size_t max_upsample, float * out)
    function = lib.xyg_pyramid_compose
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p]
    # Buffer contract: out: out_capacity >= checked(w * h) elements and total bytes <= isize::MAX; null output, zero dimensions, arithmetic overflow, impossible slice size, or short capacity returns -1 before output access; success returns nonnegative_level
    # Buffer contract: out_rgba: out_rgba_capacity >= checked(w * h * 4) bytes and total bytes <= isize::MAX; null output, zero dimensions, arithmetic overflow, impossible slice size, or short capacity returns -1 before output access; success returns nonnegative_level
    # int32_t xyg_pyramid_compose_color(uint64_t handle, double lo_x, double hi_x, double lo_y, double hi_y, size_t w, size_t h, size_t max_upsample, float * out, size_t out_capacity, uint8_t * out_rgba, size_t out_rgba_capacity)
    function = lib.xyg_pyramid_compose_color
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_pyramid_count(uint64_t handle, double lo_x, double hi_x, double lo_y, double hi_y, double * out_count)
    function = lib.xyg_pyramid_count
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p]
    # int32_t xyg_pyramid_free(uint64_t handle)
    function = lib.xyg_pyramid_free
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # uint64_t xyg_pyramid_spill(uint64_t handle)
    function = lib.xyg_pyramid_spill
    function.restype = ctypes.c_uint64
    function.argtypes = [ctypes.c_uint64]
    # size_t xyg_quad_mesh_triangles(const double * x, size_t x_len, const double * y, size_t y_len, const double * values, size_t cell_rows, size_t cell_cols, uint32_t layout, double * out_x0, double * out_y0, double * out_x1, double * out_y1, double * out_x2, double * out_y2, double * out_values)
    function = lib.xyg_quad_mesh_triangles
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_quantiles(const double * data, size_t len, const double * probs, size_t n_probs, double * out)
    function = lib.xyg_quantiles
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_quantize_unit_u8(const double * values, size_t values_len, double lo, double hi, uint8_t * out)
    function = lib.xyg_quantize_unit_u8
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_void_p]
    # size_t xyg_range_indices(const double * x, const double * y, size_t len, double lo_x, double hi_x, double lo_y, double hi_y, uint32_t * out)
    function = lib.xyg_range_indices
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p]
    # size_t xyg_range_indices_rows(const double * x, const double * y, size_t len, const uint32_t * rows, size_t n_rows, double lo_x, double hi_x, double lo_y, double hi_y, uint32_t * out)
    function = lib.xyg_range_indices_rows
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p]
    # Buffer contract: out: out_capacity >= checked(w * h * 4) bytes and total bytes <= isize::MAX; null output, zero dimensions, arithmetic overflow, impossible slice size, or short capacity returns 0 before output access; success returns 1
    # int32_t xyg_rasterize(const uint8_t * cmd, size_t cmd_len, uint8_t * out, size_t out_capacity, size_t w, size_t h)
    function = lib.xyg_rasterize
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t]
    # Buffer contract: out: out_capacity >= checked(w * h * 4) bytes and total bytes <= isize::MAX; null output, zero dimensions, arithmetic overflow, impossible slice size, or short capacity returns 0 before output access; success returns 1
    # int32_t xyg_rasterize_data(const uint8_t * cmd, size_t cmd_len, const uint8_t * data, size_t data_len, uint8_t * out, size_t out_capacity, size_t w, size_t h)
    function = lib.xyg_rasterize_data
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t]
    # Buffer contract: out: out_capacity must be 1..=isize::MAX bytes; null output, zero capacity, or impossible slice size returns usize::MAX before output access; success returns encoded_byte_count
    # size_t xyg_rasterize_png(const uint8_t * cmd, size_t cmd_len, uint8_t * out, size_t out_capacity, size_t w, size_t h)
    function = lib.xyg_rasterize_png
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t]
    # Buffer contract: out: out_capacity must be 1..=isize::MAX bytes; null output, zero capacity, or impossible slice size returns usize::MAX before output access; success returns encoded_byte_count
    # size_t xyg_rasterize_png_data(const uint8_t * cmd, size_t cmd_len, const uint8_t * data, size_t data_len, uint8_t * out, size_t out_capacity, size_t w, size_t h)
    function = lib.xyg_rasterize_png_data
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t]
    # Buffer contract: out: out_capacity must be 1..=isize::MAX bytes; null output, zero capacity, or impossible slice size returns usize::MAX before output access; success returns encoded_byte_count
    # size_t xyg_rasterize_png_spans(const uint8_t * cmd, size_t cmd_len, const uint8_t *const * span_ptrs, const size_t * span_lens, size_t span_count, uint8_t * out, size_t out_capacity, size_t w, size_t h)
    function = lib.xyg_rasterize_png_spans
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t]
    # Buffer contract: out: out_capacity >= checked(w * h * 3) bytes and total bytes <= isize::MAX; null output, zero dimensions, arithmetic overflow, impossible slice size, or short capacity returns 0 before output access; success returns 1
    # int32_t xyg_rasterize_rgb(const uint8_t * cmd, size_t cmd_len, uint8_t * out, size_t out_capacity, size_t w, size_t h)
    function = lib.xyg_rasterize_rgb
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t]
    # Buffer contract: out: out_capacity >= checked(w * h * 4) bytes and total bytes <= isize::MAX; null output, zero dimensions, arithmetic overflow, impossible slice size, or short capacity returns 0 before output access; success returns 1
    # int32_t xyg_rasterize_spans(const uint8_t * cmd, size_t cmd_len, const uint8_t *const * span_ptrs, const size_t * span_lens, size_t span_count, uint8_t * out, size_t out_capacity, size_t w, size_t h)
    function = lib.xyg_rasterize_spans
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t]
    # int32_t xyg_real_numeric_dtype_admit(uint8_t dtype_kind)
    function = lib.xyg_real_numeric_dtype_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint8]
    # uint8_t xyg_rect_zero_baseline_flags(const double * base, const double * value, size_t n)
    function = lib.xyg_rect_zero_baseline_flags
    function.restype = ctypes.c_uint8
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_recut_polar_plot(const double * in_plot, double width, double height, uint32_t legend_side, double legend_room, double polar_label_room, int32_t authored_padding, int32_t y_titled, int32_t keeps_bottom, double * out_plot)
    function = lib.xyg_recut_polar_plot
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_remap_u8(uint8_t * values, size_t len, const uint8_t * mapping, size_t mapping_len)
    function = lib.xyg_remap_u8
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_rfft(const double * data, size_t len, size_t nfft, double sample_rate, double * out_frequency, double * out_real, double * out_imag)
    function = lib.xyg_rfft
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_ribbon_edge(double x0, double x1, double ya, double yb, size_t steps, double * out_x, double * out_y, size_t capacity)
    function = lib.xyg_ribbon_edge
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_ribbon_polygon(double x0, double x1, double src_lo, double src_hi, double dst_lo, double dst_hi, size_t steps, double * out_x, double * out_y, size_t capacity)
    function = lib.xyg_ribbon_polygon
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_rounded_rect_poly(double x, double y, double w, double h, double r_tip, double r_base, int32_t tip_top, double * out_x, double * out_y, size_t capacity)
    function = lib.xyg_rounded_rect_poly
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # double xyg_sample_fraction(int64_t level, double base_fraction, double growth)
    function = lib.xyg_sample_fraction
    function.restype = ctypes.c_double
    function.argtypes = [ctypes.c_int64, ctypes.c_double, ctypes.c_double]
    # int32_t xyg_sample_mask(const uint64_t * ids, size_t len, uint64_t seed, uint64_t threshold, uint8_t * out)
    function = lib.xyg_sample_mask
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_sample_mask_u32(const uint32_t * ids, size_t len, uint64_t seed, uint64_t threshold, uint8_t * out)
    function = lib.xyg_sample_mask_u32
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p]
    # size_t xyg_sample_range_indices(size_t size, uint64_t seed, uint64_t threshold, uint32_t * out, size_t capacity)
    function = lib.xyg_sample_range_indices
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_size_t, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t]
    # uint64_t xyg_sample_threshold(double fraction)
    function = lib.xyg_sample_threshold
    function.restype = ctypes.c_uint64
    function.argtypes = [ctypes.c_double]
    # int32_t xyg_sankey_layout(uint64_t n_nodes, uint64_t n_links, const uint64_t * sources, const uint64_t * targets, const double * values, double node_width, double node_padding, uint32_t align, uint32_t iterations, double * out_x0, double * out_y0, double * out_x1, double * out_y1, uint32_t * out_layer, double * out_value, double * out_source_y0, double * out_source_y1, double * out_target_y0, double * out_target_y1, uint32_t * out_layers, uint64_t * out_err_nodes, uint64_t * out_err_n)
    function = lib.xyg_sankey_layout
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_scale_pins_offset(const uint8_t * scale, size_t len)
    function = lib.xyg_scale_pins_offset
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_annotation_style_admit(const uint8_t * kind, size_t kind_len, uint8_t wrapped, uint8_t labelled, const uint8_t * key, size_t key_len)
    function = lib.xyg_scene_annotation_style_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_arrays_equal(const double * left, size_t left_len, const double * right, size_t right_len)
    function = lib.xyg_scene_arrays_equal
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_scene_axis_ticks(uint32_t kind, double lo, double hi, size_t target, double aux, double * out_ticks, double * out_labeled, size_t * out_labeled_len, double * out_step, size_t out_cap)
    function = lib.xyg_scene_axis_ticks
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_scene_batch_encode(double viewport_width, double viewport_height, double margin_left, double margin_right, double margin_top, double margin_bottom, uint64_t x_axis_id, uint32_t x_kind, double x_lo, double x_hi, double x_constant, int32_t x_mask_nonpositive, uint64_t y_axis_id, uint32_t y_kind, double y_lo, double y_hi, double y_constant, int32_t y_mask_nonpositive, const uint8_t * chrome_style, size_t chrome_style_len, const double * x_major_ticks, size_t x_major_count, int32_t x_major_auto, const double * x_minor_ticks, size_t x_minor_count, const double * y_major_ticks, size_t y_major_count, int32_t y_major_auto, const double * y_minor_ticks, size_t y_minor_count, const uint8_t * x_tick_labels, size_t x_tick_labels_len, const uint8_t * y_tick_labels, size_t y_tick_labels_len, const uint8_t * authored_text_annotations, size_t authored_text_annotations_len, const uint8_t * kinds, const uint64_t * stable_ids, const uint32_t * style_refs, const uint8_t * fill_rgba, const uint8_t * stroke_rgba, const double * stroke_width, size_t style_count, const double * diameter, const uint8_t * symbols, const uint8_t * expansion_modes, const double * x0, const double * y0, const double * x1, const double * y1, size_t len, const uint8_t * title, size_t title_len, const uint8_t * x_label, size_t x_label_len, const uint8_t * y_label, size_t y_label_len, const uint8_t * legend_input, size_t legend_input_len, const uint8_t * colorbar_input, size_t colorbar_input_len, const uint8_t * polar_input, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_batch_encode
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_uint64, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_uint64, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_scene_browser_painter(const uint8_t * encoded, size_t encoded_len, size_t max_bytes, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_browser_painter
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_channel_constant_css(const uint8_t * mode, size_t mode_len, int32_t has_constant, const uint8_t * constant, size_t constant_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_channel_constant_css
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_chrome_pack(const void * input, const double * x_major, const double * y_major, const double * x_minor, const double * y_minor, const void * x_tick_labels, const void * y_tick_labels, const uint8_t * colorbar_stops, const double * colorbar_ticks, uint8_t * out, size_t out_cap, size_t * out_len)
    function = lib.xyg_scene_chrome_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_scene_constant_color_admit(int32_t has_channel, int32_t constant_ok, int32_t scatter_density, int32_t packs_paint_plane)
    function = lib.xyg_scene_constant_color_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    # int32_t xyg_scene_curve_classify(const uint8_t * text, size_t text_len)
    function = lib.xyg_scene_curve_classify
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_dash_admit(const uint8_t * text, size_t text_len, const double * lengths, size_t n, int32_t use_lengths, double * out, size_t out_cap, size_t * out_n)
    function = lib.xyg_scene_dash_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_scene_encode_assembled(const uint8_t * xyas, size_t xyas_len, const uint8_t * chrome, size_t chrome_len, const uint8_t * extras, size_t extras_len, double viewport_width, double viewport_height, uint64_t x_axis_id, uint32_t x_kind, double x_lo, double x_hi, double x_constant, int32_t x_mask_nonpositive, uint64_t y_axis_id, uint32_t y_kind, double y_lo, double y_hi, double y_constant, int32_t y_mask_nonpositive, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_encode_assembled
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_uint64, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_uint64, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_encode_assembled_from_sidecars(const uint8_t * xyas, size_t xyas_len, const uint8_t * chrome_facts, size_t chrome_facts_len, const uint8_t * xysd, size_t xysd_len, const uint8_t * polar, size_t polar_len, const uint8_t * extras_facts, size_t extras_facts_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_encode_assembled_from_sidecars
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_encode_product(const uint8_t * xytc, size_t xytc_len, const uint8_t * xyta, size_t xyta_len, const uint8_t * xynm, size_t xynm_len, const uint8_t * xycl, size_t xycl_len, const uint8_t * xyaf, size_t xyaf_len, uint32_t style_ref_base, double x_lo, double x_hi, double y_lo, double y_hi, const uint8_t * xycf, size_t xycf_len, const uint8_t * polar, size_t polar_len, const uint8_t * xyfs, size_t xyfs_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_encode_product
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_encode_product_attach_plan(int32_t polar, void * out)
    function = lib.xyg_scene_encode_product_attach_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_scene_figure_support_figure_plan(int32_t polar, void * out)
    function = lib.xyg_scene_figure_support_figure_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_scene_figure_support_materialize(int32_t polar, int32_t colorbar_unsupported, int32_t has_custom_font, int32_t has_browser_css, int32_t has_extra_legends, const void * annotations, size_t annotation_count, const void * axes, size_t axis_count, const uint8_t * axis_keys_blob, size_t axis_keys_len, const void * traces, size_t trace_count, const double * corner_radius, uint8_t * out, size_t out_cap, size_t * out_len)
    function = lib.xyg_scene_figure_support_materialize
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_scene_figure_support_pack(uint32_t flags, const uint8_t * axes_blob, size_t axes_len, const uint8_t * traces_blob, size_t traces_len, uint8_t * out, size_t out_cap, size_t * out_len)
    function = lib.xyg_scene_figure_support_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_scene_figure_support_reason(const uint8_t * input, size_t len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_figure_support_reason
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_figure_support_trace_dispatch_plan(const uint8_t * kind, size_t kind_len, int32_t marker_glyph_present, int32_t marker_path_present, int32_t curve_present, int32_t fill_present, void * out)
    function = lib.xyg_scene_figure_support_trace_dispatch_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_scene_fill_gradient_admit(const uint8_t * space, size_t space_len, const uint8_t * dir, size_t dir_len, const double * t, size_t n_stops, const uint8_t * css, size_t css_len, const uint32_t * css_lens, size_t n_css, const uint8_t * mark_color, size_t mark_len, uint8_t * out_rgba, size_t out_cap)
    function = lib.xyg_scene_fill_gradient_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_finite_all(const double * values, size_t values_len)
    function = lib.xyg_scene_finite_all
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_gradient_dir(const uint8_t * text, size_t text_len)
    function = lib.xyg_scene_gradient_dir
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_gradient_solid_css(const uint8_t * rgba, size_t rgba_len, uint8_t * out, size_t out_len)
    function = lib.xyg_scene_gradient_solid_css
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_gradient_space(const uint8_t * text, size_t text_len)
    function = lib.xyg_scene_gradient_space
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_gradient_spec_pack(const uint8_t * space, size_t space_len, const uint8_t * dir, size_t dir_len, const double * stop_t, size_t n_stops, const uint8_t * css, size_t css_len, const uint32_t * css_lens, size_t n_lens, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_gradient_spec_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_heatmap_colormap_admit(int32_t truecolor, int32_t has_colormap, int32_t has_rgba_grid, int32_t has_rgba)
    function = lib.xyg_scene_heatmap_colormap_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    # int32_t xyg_scene_heatmap_extent_admit(double x0, double x1, double y0, double y1)
    function = lib.xyg_scene_heatmap_extent_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double]
    # int32_t xyg_scene_heatmap_shape_admit(double rows, double cols)
    function = lib.xyg_scene_heatmap_shape_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_double, ctypes.c_double]
    # int32_t xyg_scene_hexbin_colormap_plane_admit(const uint8_t * text, size_t text_len, int32_t has_values)
    function = lib.xyg_scene_hexbin_colormap_plane_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32]
    # int32_t xyg_scene_hexbin_pitch_admit(double dx, double dy)
    function = lib.xyg_scene_hexbin_pitch_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_double, ctypes.c_double]
    # int32_t xyg_scene_hexbin_reduce_admit(const uint8_t * text, size_t text_len)
    function = lib.xyg_scene_hexbin_reduce_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_hexbin_rgba_plane_admit(const uint8_t * text, size_t text_len)
    function = lib.xyg_scene_hexbin_rgba_plane_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_hidden_or_per_item_admit(int32_t hidden, int32_t has_per_item, int32_t density_aggregates)
    function = lib.xyg_scene_hidden_or_per_item_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    # int32_t xyg_scene_item_apply_opacity(const uint8_t * packed, size_t packed_len, size_t n, const double * artist, size_t artist_len, int32_t has_artist, const double * opacity, size_t opacity_len, int32_t has_opacity, uint8_t * out, size_t out_len)
    function = lib.xyg_scene_item_apply_opacity
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_item_fill_t(const double * values, size_t values_len, size_t n, double domain_lo, double domain_hi, int32_t has_domain, double * out, size_t out_len)
    function = lib.xyg_scene_item_fill_t
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_item_widths_admit(const double * values, size_t values_len, int32_t has_values, size_t n, double scalar)
    function = lib.xyg_scene_item_widths_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_size_t, ctypes.c_double]
    # int32_t xyg_scene_kind_admit(const uint8_t * text, size_t text_len)
    function = lib.xyg_scene_kind_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_kind_class(const uint8_t * text, size_t text_len)
    function = lib.xyg_scene_kind_class
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_linear_gradient_prefix(const uint8_t * text, size_t text_len)
    function = lib.xyg_scene_linear_gradient_prefix
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_linecap_admit(const uint8_t * text, size_t text_len)
    function = lib.xyg_scene_linecap_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_marker_blob_pack(int32_t filled, const double * values, size_t n_values, const uint32_t * contour_lens, size_t n_contours, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_marker_blob_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_marker_glyph_admit(const uint8_t * text, size_t text_len)
    function = lib.xyg_scene_marker_glyph_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_marker_path_admit(const double * values, size_t n_values, const uint32_t * lengths, size_t n_contours)
    function = lib.xyg_scene_marker_path_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_mesh_paint_plane_admit(const uint8_t * text, size_t text_len, int32_t joined_fill, int32_t has_per_item)
    function = lib.xyg_scene_mesh_paint_plane_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32]
    # int32_t xyg_scene_pack_annotation_facts(const uint8_t * facts, size_t facts_len, uint32_t style_ref_base, double x0, double x1, double y0, double y1, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_pack_annotation_facts
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_pack_annotation_marks(const uint8_t * rows, size_t rows_len, double x0, double x1, double y0, double y1, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_pack_annotation_marks
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_pack_annotations(uint32_t n_text, const uint8_t * text_meta, size_t text_meta_len, const uint32_t * text_lens, const uint8_t * texts, size_t texts_len, uint32_t n_attached, const uint8_t * attached_meta, size_t attached_meta_len, const uint32_t * attached_lens, const uint8_t * attached_texts, size_t attached_texts_len, uint32_t n_arrows, const uint8_t * arrow_meta, size_t arrow_meta_len, uint32_t n_callouts, const uint8_t * callout_meta, size_t callout_meta_len, const uint32_t * callout_lens, const uint8_t * callout_texts, size_t callout_texts_len, uint32_t n_wrapped, const uint8_t * wrapped_meta, size_t wrapped_meta_len, const uint32_t * wrapped_lens, const uint8_t * wrapped_texts, size_t wrapped_texts_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_pack_annotations
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_pack_colorbar(uint8_t flags, double lo, double hi, const uint8_t * text_rgba, const uint8_t * title, size_t title_len, uint32_t n_stops, const double * stop_values, const uint8_t * stop_rgba, size_t stop_rgba_len, uint32_t n_ticks, const double * ticks, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_pack_colorbar
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint8, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_pack_density_grid(const double * x, const double * y, size_t len, double x0, double x1, double y0, double y1, const uint8_t * idx, const uint8_t * rgba, const uint8_t * lut, size_t lut_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_pack_density_grid
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_pack_figure_chrome(const uint8_t * facts, size_t facts_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_pack_figure_chrome
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_pack_figure_chrome_from_sidecars(const uint8_t * facts, size_t facts_len, const uint8_t * xysd, size_t xysd_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_pack_figure_chrome_from_sidecars
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_pack_heatmap_facts(const uint8_t * facts, size_t facts_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_pack_heatmap_facts
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_pack_legend(uint8_t loc, uint8_t flags, double font_size, double title_font_size, const uint8_t * text_rgba, const uint8_t * frame_fill_rgba, const uint8_t * title, size_t title_len, uint32_t n_entries, const uint8_t * entry_meta, size_t entry_meta_len, const uint32_t * label_lens, const uint8_t * labels, size_t labels_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_pack_legend
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint8, ctypes.c_uint8, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_pack_product(const uint8_t * kind, size_t kind_len, uint8_t flags, uint8_t step_mode, uint8_t symbol, uint32_t style_ref, uint64_t trace_id, double diameter, double extra0, double extra1, const double * col0, size_t n0, const double * col1, size_t n1, const double * col2, size_t n2, const double * col3, size_t n3, const double * col4, size_t n4, const double * col5, size_t n5, const double * col6, size_t n6, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_pack_product
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint32, ctypes.c_uint64, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_pack_product_facts(const uint8_t * facts, size_t facts_len, const double * col0, size_t n0, const double * col1, size_t n1, const double * col2, size_t n2, const double * col3, size_t n3, const double * col4, size_t n4, const double * col5, size_t n5, const double * col6, size_t n6, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_pack_product_facts
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_pack_public_export(const uint8_t * facts, size_t facts_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_pack_public_export
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_pack_scene_extras(const uint8_t * polar, size_t polar_len, const uint8_t * paint, size_t paint_len, const uint8_t * facts, size_t facts_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_pack_scene_extras
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_pack_scene_extras_from_sidecars(const uint8_t * polar, size_t polar_len, const uint8_t * xysd, size_t xysd_len, const uint8_t * facts, size_t facts_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_pack_scene_extras_from_sidecars
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_pack_style_sidecars(const uint8_t * sidecars, size_t sidecars_len, const uint8_t * annotations, size_t annotations_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_pack_style_sidecars
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_pack_trace(uint8_t pack_kind, uint8_t flags, uint8_t step_mode, uint8_t symbol, uint32_t style_ref, uint64_t trace_id, double diameter, double extra0, double extra1, const double * col0, size_t n0, const double * col1, size_t n1, const double * col2, size_t n2, const double * col3, size_t n3, const double * col4, size_t n4, const double * col5, size_t n5, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_pack_trace
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint32, ctypes.c_uint64, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_pack_trace_attach(const uint8_t * compiled, size_t compiled_len, const uint8_t * attach, size_t attach_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_pack_trace_attach
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_pack_trace_compile(const uint8_t * facts, size_t facts_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_pack_trace_compile
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_pack_trace_rows(const uint8_t * attached, size_t attached_len, const uint8_t * columns, size_t columns_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_pack_trace_rows
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_pack_trace_sidecars(const uint8_t * attached, size_t attached_len, const uint8_t * names, size_t names_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_pack_trace_sidecars
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_parse_linear_gradient(const uint8_t * css, size_t css_len, const uint8_t * space, size_t space_len, uint8_t * out_dir, double * out_t, size_t out_t_cap, uint8_t * out_css, size_t out_css_cap, uint32_t * out_css_lens, size_t out_lens_cap, size_t * out_n)
    function = lib.xyg_scene_parse_linear_gradient
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_scene_plot_layout(double viewport_width, double viewport_height, const double * authored_padding, uint32_t x_kind, double x_lo, double x_hi, double x_constant, int32_t x_mask_nonpositive, uint32_t y_kind, double y_lo, double y_hi, double y_constant, int32_t y_mask_nonpositive, const uint8_t * title, size_t title_len, const uint8_t * x_label, size_t x_label_len, const uint8_t * y_label, size_t y_label_len, const uint8_t * x_format, size_t x_format_len, const uint8_t * y_format, size_t y_format_len, uint32_t colorbar_side, double * out_margins)
    function = lib.xyg_scene_plot_layout
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_void_p]
    # int32_t xyg_scene_polar_figure_plan(int32_t polar, void * out)
    function = lib.xyg_scene_polar_figure_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_scene_polar_input_pack(const void * input, uint8_t * out, size_t out_cap, size_t * out_len)
    function = lib.xyg_scene_polar_input_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_scene_public_export_figure_plan(int32_t polar, int32_t has_chrome_styles, int32_t has_title_options, void * out)
    function = lib.xyg_scene_public_export_figure_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p]
    # size_t xyg_scene_public_export_reason(const uint8_t * input, size_t len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_public_export_reason
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_public_export_trace_dispatch_plan(const uint8_t * kind, size_t kind_len, int32_t polar, int32_t use_density, void * out)
    function = lib.xyg_scene_public_export_trace_dispatch_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p]
    # size_t xyg_scene_raster_commands(const uint8_t * encoded, size_t encoded_len, double scale, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_raster_commands
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_rect_extra_flags(const uint8_t * kind, size_t kind_len, int32_t polar, int32_t gradient_fail, const double * radius, size_t n_radius, int32_t radius_seq, double wedge_gap)
    function = lib.xyg_scene_rect_extra_flags
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_double]
    # int32_t xyg_scene_resolve_chrome_style(const uint8_t * input, size_t len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_resolve_chrome_style
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_resolve_mark_styles(const uint8_t * input, size_t len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_resolve_mark_styles
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_resolve_pack_kind(const uint8_t * kind, size_t kind_len, uint8_t flags)
    function = lib.xyg_scene_resolve_pack_kind
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint8]
    # int32_t xyg_scene_ribbon_color2_classify(uint8_t has_color2, uint8_t kind_is_ribbon, uint8_t has_source_css, const uint8_t * source_css, size_t source_len, uint8_t has_target_css, const uint8_t * target_css, size_t target_len, const uint8_t * source_paint, size_t source_paint_len, uint8_t has_fill, uint8_t has_end_pair)
    function = lib.xyg_scene_ribbon_color2_classify
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint8, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint8, ctypes.c_uint8]
    # int32_t xyg_scene_scale_map(const double * values, size_t len, uint32_t kind, uint32_t operation, double lo, double hi, double px0, double px1, double constant, int32_t mask_nonpositive, double * out)
    function = lib.xyg_scene_scale_map
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_scene_scatter_paint_channel_admit(const uint8_t * text, size_t text_len)
    function = lib.xyg_scene_scatter_paint_channel_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_scene_scatter_svg(const double * x, const double * y, const double * diameter, const uint8_t * fill_rgba, const uint8_t * stroke_rgba, const double * stroke_width, const uint8_t * symbols, const uint8_t * visible, const uint8_t * fill_css, size_t fill_css_len, const uint8_t * stroke_css, size_t stroke_css_len, size_t len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_scatter_svg
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_splice_annotations(const uint8_t * rows, size_t rows_len, const uint8_t * sidecars, size_t sidecars_len, const uint8_t * annotations, size_t annotations_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_splice_annotations
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_scene_static_export(const uint8_t * encoded, size_t encoded_len, uint32_t format, double scale, size_t width, size_t height, int32_t quality, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_static_export
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_scene_support_reason(uint32_t request_version, uint64_t features, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_support_reason
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_uint32, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_scene_svg(const uint8_t * encoded, size_t encoded_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_scene_svg
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_tick_anchor(const uint8_t * text, size_t text_len)
    function = lib.xyg_scene_tick_anchor
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_scene_tick_label_layout(const double * positions, size_t n, const uint32_t * label_lens, const uint8_t * labels, size_t labels_len, uint32_t kind, uint32_t side, uint32_t anchor, uint32_t flags, double font_size, double min_gap, double explicit_angle, uint32_t * out_index, double * out_angle, uint32_t * out_row, size_t out_cap)
    function = lib.xyg_scene_tick_label_layout
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_tick_label_strategy(const uint8_t * text, size_t text_len)
    function = lib.xyg_scene_tick_label_strategy
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # uint32_t xyg_scene_version()
    function = lib.xyg_scene_version
    function.restype = ctypes.c_uint32
    function.argtypes = []
    # int32_t xyg_scene_xyaf_annotation_dispatch_plan(const uint8_t * kind, size_t kind_len, int32_t authored_wrap, int32_t layout_text, void * out)
    function = lib.xyg_scene_xyaf_annotation_dispatch_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_scene_xyaf_bulk_pack(const void * annotations, size_t annotation_count, const uint8_t * extra_style_keys_blob, size_t extra_style_keys_len, uint8_t * out, size_t out_cap, size_t * out_len, uint32_t * error_index)
    function = lib.xyg_scene_xyaf_bulk_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_scene_xyaf_pack(const void * input, const uint8_t * text, uint8_t * out, size_t out_cap, size_t * out_len)
    function = lib.xyg_scene_xyaf_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_scene_xycf_figure_plan(int32_t show_legend, int32_t colorbar_ok, int32_t polar, void * out)
    function = lib.xyg_scene_xycf_figure_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_scene_xycf_pack(const void * input, const uint8_t * title, const uint8_t * x_label, const uint8_t * y_label, const uint8_t * x_format, const uint8_t * y_format, const double * x_major, const double * x_minor, const double * y_major, const double * y_minor, const uint8_t * x_labels_blob, const uint8_t * y_labels_blob, const uint8_t * chrome, const uint8_t * legend_loc, const uint8_t * legend_title, const uint8_t * legend_meta, const uint32_t * legend_lens, const uint8_t * legend_blob, const uint8_t * colorbar_stops_blob, const double * colorbar_ticks, const uint8_t * colorbar_title, const uint8_t * collision_extra, uint8_t * out, size_t out_cap, size_t * out_len)
    function = lib.xyg_scene_xycf_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_scene_xycl_figure_plan(int32_t polar, void * out)
    function = lib.xyg_scene_xycl_figure_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_scene_xyhf_colormap_pack(int32_t mode, const uint8_t * named, size_t named_len, const uint8_t * stop_rgb, size_t stop_len, uint32_t * out_flags, uint8_t * out_cmap, size_t cmap_cap, uint8_t * out_stops, size_t stops_cap)
    function = lib.xyg_scene_xyhf_colormap_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_xynm_figure_plan(int32_t show_legend, void * out)
    function = lib.xyg_scene_xynm_figure_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_scene_xyta_colormap_pack(int32_t mode, const uint8_t * named, size_t named_len, const uint8_t * stop_rgb, size_t stop_len, uint32_t * out_flags, uint8_t * out_cmap, size_t cmap_cap, uint8_t * out_stops, size_t stops_cap)
    function = lib.xyg_scene_xyta_colormap_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_scene_xyta_figure_plan(int32_t polar, void * out)
    function = lib.xyg_scene_xyta_figure_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_scene_xyta_trace_dispatch_plan(const uint8_t * kind, size_t kind_len, int32_t polar, int32_t use_density, int32_t hexbin_colormap_plane, int32_t hexbin_rgba_plane_ready, int32_t ribbon_color2_class, int32_t mesh_paint_plane, int32_t scatter_paint_plane, void * out)
    function = lib.xyg_scene_xyta_trace_dispatch_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_scene_xyta_trace_observations_materialize(const void * input, const uint8_t * fallback_color, const uint8_t * style_color, const uint8_t * style_stroke, const uint8_t * style_colormap_named, const uint8_t * style_colormap_stops, const double * grid_values, const uint8_t * rgba_u8, const double * rgba_grid_f64, const double * x_values, const double * y_values, const void * color_ch, const uint8_t * color_mode, const uint8_t * color_constant, const uint8_t * color_colormap, const double * color_values_f64, const uint8_t * color_rgba_u8, const uint8_t * color_codes_u8, const int64_t * color_codes_i64, const uint8_t *const * color_palette_ptrs, const size_t * color_palette_lens, const void * stroke_ch, const uint8_t * stroke_mode, const uint8_t * stroke_constant, const uint8_t * stroke_colormap, const double * stroke_values_f64, const uint8_t * stroke_rgba_u8, const uint8_t * stroke_codes_u8, const int64_t * stroke_codes_i64, const uint8_t *const * stroke_palette_ptrs, const size_t * stroke_palette_lens, const void * color2_ch, const uint8_t * color2_mode, const uint8_t * color2_constant, const uint8_t * color2_colormap, const double * color2_values_f64, const uint8_t * color2_rgba_u8, const uint8_t * color2_codes_u8, const int64_t * color2_codes_i64, const uint8_t *const * color2_palette_ptrs, const size_t * color2_palette_lens, const void * opacity_ch, const double * opacity_values, const void * artist_ch, const double * artist_values, const void * stroke_width_ch, const double * stroke_width_values, void * summary, uint8_t * out_bytes, size_t out_cap, size_t * out_len)
    function = lib.xyg_scene_xyta_trace_observations_materialize
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_scene_xyta_trace_pack(const void * input, const uint8_t * grid, const uint8_t * rgba, const uint8_t * rgba_grid, const uint8_t * x, const uint8_t * y, const uint8_t * mean_rgba, const uint8_t * idx, const uint8_t * lut, const uint8_t * cmap, const uint8_t * stops, const uint8_t * color_ch, const uint8_t * style_color, uint8_t * out, size_t out_cap, size_t * out_len)
    function = lib.xyg_scene_xyta_trace_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_scene_xytc_color2_flags_pack(int32_t color2_class, uint32_t paint_flags, int32_t gradient_packed, uint32_t * out_flags)
    function = lib.xyg_scene_xytc_color2_flags_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_uint32, ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_scene_xytc_color_channel_pack(int32_t present, int32_t has_constant, uint32_t * out_flags)
    function = lib.xyg_scene_xytc_color_channel_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_scene_xytc_dash_pattern_pack(int32_t is_array, uint32_t * out_flags)
    function = lib.xyg_scene_xytc_dash_pattern_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_scene_xytc_figure_plan(int32_t show_legend, void * out)
    function = lib.xyg_scene_xytc_figure_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_scene_xytc_hex_pitch_pack(int32_t hexbin, int32_t has_dx, int32_t has_dy, double dx, double dy, uint32_t * out_flags, double * out_hex_dx, double * out_hex_dy)
    function = lib.xyg_scene_xytc_hex_pitch_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_scene_xytc_meta_flags_pack(int32_t has_name, int32_t show_legend, const uint8_t * kind, size_t kind_len, int32_t use_density, int32_t joined_fill, int32_t marker_path_present, int32_t marker_packed, int32_t glyph_packed, uint32_t * out_flags)
    function = lib.xyg_scene_xytc_meta_flags_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_scene_xytc_numeric_style_pack(int32_t has_size, int32_t has_size_ch, int32_t has_size_ch_constant, int32_t has_stroke_width, int32_t has_width, int32_t has_line_width, double size, double size_ch_constant, double stroke_width, double width, double line_width, uint32_t * out_flags, double * out_size, double * out_size_ch_value, double * out_stroke_width, double * out_width, double * out_line_width)
    function = lib.xyg_scene_xytc_numeric_style_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_scene_xytc_opacity_pack(int32_t has_opacity_class, int32_t has_band_class, double authored_fill, double authored_stroke, double authored_line, double * out_fill, double * out_stroke, double * out_line)
    function = lib.xyg_scene_xytc_opacity_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_scene_xytc_paint_presence_pack(int32_t has_fill, int32_t fill_kind, int32_t has_stroke, int32_t has_line_color, uint32_t * out_flags)
    function = lib.xyg_scene_xytc_paint_presence_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_scene_xytc_radius_pack(const uint8_t * kind, size_t kind_len, int32_t radius_seq, double r0, double r1, double wedge_gap_raw, uint32_t * out_flags, double * out_r_tip, double * out_r_base, double * out_wedge_gap)
    function = lib.xyg_scene_xytc_radius_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_scene_xytc_stroke_perimeter_pack(int32_t band, int32_t present, int32_t perimeter_is_bool, int32_t perimeter_true, uint32_t * out_flags)
    function = lib.xyg_scene_xytc_stroke_perimeter_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_scene_xytc_symbol_int_pack(int32_t symbol_is_int, uint32_t * out_flags)
    function = lib.xyg_scene_xytc_symbol_int_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_scene_xytc_trace_dispatch_plan(const uint8_t * kind, size_t kind_len, int32_t marker_path_present, int32_t use_density, int32_t joined_fill, void * out)
    function = lib.xyg_scene_xytc_trace_dispatch_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p]
    # int32_t xyg_scene_xytc_trace_observations_materialize(const void * input, const uint8_t * kind, const uint8_t * name, const uint8_t * symbol, const uint8_t * stroke, const uint8_t * line_color, const uint8_t * color_css, const uint8_t * dash, const double * dash_values, const uint8_t * fill_string, const uint8_t * fill_space, const uint8_t * fill_dir, const double * fill_stop_t, const uint8_t * fill_stop_css, const uint32_t * fill_stop_css_lens, const uint8_t * fill_dict_gradient, const uint8_t * fill_dict_space, const double * marker_values, const uint32_t * marker_lens, const uint8_t * marker_glyph, const uint8_t * source_paint, const uint8_t * color2_source_const, const uint8_t * color2_target_const, const uint8_t * color_mode, const uint8_t * color_const, const uint8_t * linecap, const uint8_t * step, const uint8_t * curve, void * summary, uint8_t * out_bytes, size_t out_cap, size_t * out_len)
    function = lib.xyg_scene_xytc_trace_observations_materialize
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_scene_xytc_trace_pack(const void * input, const uint8_t * kind, const uint8_t * name, const uint8_t * symbol_b, const uint8_t * dash_b, const double * dash_pattern, const uint8_t * linecap_b, const uint8_t * step_b, const uint8_t * curve_b, const uint8_t * fill_css, const uint8_t * fill_space, const uint8_t * fill_gradient_blob, const uint8_t * stroke_css, const uint8_t * line_color, const uint8_t * color_css, const uint8_t * color_mode, const uint8_t * color_const, const uint8_t * marker_blob, const uint8_t * color2_gradient_blob, uint8_t * out, size_t out_cap, size_t * out_len)
    function = lib.xyg_scene_xytc_trace_pack
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # int32_t xyg_screen_shape(int32_t px_w, int32_t px_h, int32_t * out_w, int32_t * out_h)
    function = lib.xyg_screen_shape
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_sector_triangles(const double * values, size_t len, const double * explode, double center_x, double center_y, double radius, double inner_radius, double start_degrees, int32_t counterclockwise, int32_t normalize, double * out_x0, double * out_y0, double * out_x1, double * out_y1, double * out_x2, double * out_y2, double * out_sector, size_t capacity)
    function = lib.xyg_sector_triangles
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_size_range_admit(double lo, double hi, double * out_lo, double * out_hi)
    function = lib.xyg_size_range_admit
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_sorted_display_label_remap(const uint32_t * label_lens, const uint8_t * label_texts, size_t label_texts_len, size_t n, const uint64_t * in_counts, uint8_t * out_remap, size_t out_remap_cap, uint32_t * out_code_width, uint32_t * out_category_lens, uint8_t * out_category_texts, size_t out_category_texts_cap, size_t category_lens_cap, uint64_t * out_category_counts, size_t out_category_counts_cap)
    function = lib.xyg_sorted_display_label_remap
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_spectrogram(const double * data, size_t len, size_t nfft, size_t noverlap, double sample_rate, double * out_frequency, double * out_time, double * out_power)
    function = lib.xyg_spectrogram
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_stacked_bounds(const double * values, size_t rows, size_t cols, uint32_t baseline, double * out_lower, double * out_upper)
    function = lib.xyg_stacked_bounds
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_step_arrays(const double * x, const double * y, size_t n, uint8_t mode, double * out_x, double * out_y, size_t capacity)
    function = lib.xyg_step_arrays
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint8, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_stratified_sample_mask(const uint64_t * ids, const uint32_t * groups, size_t len, size_t n_groups, uint64_t seed, double fraction, uint64_t min_count, uint8_t * out)
    function = lib.xyg_stratified_sample_mask
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_double, ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_stratified_sample_mask_u32(const uint32_t * ids, const uint32_t * groups, size_t len, size_t n_groups, uint64_t seed, double fraction, uint64_t min_count, uint8_t * out)
    function = lib.xyg_stratified_sample_mask_u32
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_double, ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_stratified_sample_range_plan(size_t n_rows, uint32_t n_groups, uint32_t target, int64_t level, double growth, uint64_t seed, uint32_t min_per_category, double * out_fraction, uint64_t * out_seed, uint32_t * out_min_count, size_t * out_capacity, uint32_t * out_keep_all)
    function = lib.xyg_stratified_sample_range_plan
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int64, ctypes.c_double, ctypes.c_uint64, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_stratified_sample_range_u8(const uint8_t * groups, size_t len, size_t n_groups, uint64_t seed, double fraction, uint64_t min_count, uint32_t * out, size_t capacity)
    function = lib.xyg_stratified_sample_range_u8
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_double, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_stratified_sample_range_u8_counted(const uint8_t * groups, size_t len, const uint64_t * counts, size_t n_groups, uint64_t seed, double fraction, uint64_t min_count, uint32_t * out, size_t capacity)
    function = lib.xyg_stratified_sample_range_u8_counted
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_double, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_stream_append(uint64_t handle, const double * data, size_t len)
    function = lib.xyg_stream_append
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_stream_capacity(uint64_t handle)
    function = lib.xyg_stream_capacity
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_stream_copy(uint64_t handle, double * out, size_t len)
    function = lib.xyg_stream_copy
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_stream_data(uint64_t handle, const double ** out_ptr, size_t * out_len)
    function = lib.xyg_stream_data
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_stream_free(uint64_t handle)
    function = lib.xyg_stream_free
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # size_t xyg_stream_len(uint64_t handle)
    function = lib.xyg_stream_len
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_uint64]
    # uint64_t xyg_stream_new(const double * data, size_t len)
    function = lib.xyg_stream_new
    function.restype = ctypes.c_uint64
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_stream_seal(uint64_t handle)
    function = lib.xyg_stream_seal
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # size_t xyg_stream_zone_maps(uint64_t handle, double * out_min, double * out_max, uint64_t * out_count, uint64_t * out_null_count, double * out_sum, double * out_sum_sq, double * out_positive_min, double * out_positive_max)
    function = lib.xyg_stream_zone_maps
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_streamlines(const double * x_coords, size_t cols, const double * y_coords, size_t rows, const double * u, const double * v, double density, size_t max_steps, double * out_x0, double * out_x1, double * out_y0, double * out_y1, size_t capacity)
    function = lib.xyg_streamlines
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_svg_poly_path(const double * x, const double * y, size_t len, uint8_t * out, size_t out_cap)
    function = lib.xyg_svg_poly_path
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_svg_to_pdf(const uint8_t * svg, size_t svg_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_svg_to_pdf
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_temporal_column_copy(uint64_t handle, int64_t * out_values, uint8_t * out_validity, uint64_t capacity)
    function = lib.xyg_temporal_column_copy
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64]
    # int32_t xyg_temporal_column_create(const void * descriptor, uint64_t * out_handle)
    function = lib.xyg_temporal_column_create
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_temporal_column_destroy(uint64_t handle)
    function = lib.xyg_temporal_column_destroy
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_temporal_column_meta(uint64_t handle, uint64_t * out_len, uint32_t * out_precision, uint32_t * out_timezone_len)
    function = lib.xyg_temporal_column_meta
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_temporal_column_timezone(uint64_t handle, uint8_t * out_timezone, uint32_t capacity)
    function = lib.xyg_temporal_column_timezone
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_uint32]
    # int32_t xyg_temporal_controller_apply_event(uint64_t handle, uint64_t group_id, uint64_t source_instance, uint64_t revision, int64_t range_start, int64_t range_end, int64_t cursor, int64_t window, const uint64_t * selection, uint64_t selection_count, uint32_t * out_applied)
    function = lib.xyg_temporal_controller_apply_event
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_int64, ctypes.c_int64, ctypes.c_int64, ctypes.c_int64, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_temporal_controller_create(const void * descriptor, uint64_t * out_handle)
    function = lib.xyg_temporal_controller_create
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_temporal_controller_destroy(uint64_t handle)
    function = lib.xyg_temporal_controller_destroy
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_temporal_controller_dispose(uint64_t handle)
    function = lib.xyg_temporal_controller_dispose
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_temporal_controller_pause(uint64_t handle)
    function = lib.xyg_temporal_controller_pause
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_temporal_controller_play(uint64_t handle)
    function = lib.xyg_temporal_controller_play
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_temporal_controller_poll_event(uint64_t handle, uint32_t * out_has_event, uint64_t * out_group_id, uint64_t * out_source_instance, uint64_t * out_revision, int64_t * out_range_start, int64_t * out_range_end, int64_t * out_cursor, int64_t * out_window, uint64_t * out_selection, uint64_t selection_capacity, uint64_t * out_selection_count)
    function = lib.xyg_temporal_controller_poll_event
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_temporal_controller_set_cursor(uint64_t handle, int64_t cursor)
    function = lib.xyg_temporal_controller_set_cursor
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_int64]
    # int32_t xyg_temporal_controller_set_direction(uint64_t handle, int32_t direction)
    function = lib.xyg_temporal_controller_set_direction
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_int32]
    # int32_t xyg_temporal_controller_set_loop(uint64_t handle, uint32_t enabled)
    function = lib.xyg_temporal_controller_set_loop
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint32]
    # int32_t xyg_temporal_controller_set_range(uint64_t handle, int64_t start, int64_t end)
    function = lib.xyg_temporal_controller_set_range
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_int64, ctypes.c_int64]
    # int32_t xyg_temporal_controller_set_rate_milli(uint64_t handle, uint32_t rate_milli)
    function = lib.xyg_temporal_controller_set_rate_milli
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint32]
    # int32_t xyg_temporal_controller_set_reduced_motion(uint64_t handle, uint32_t enabled)
    function = lib.xyg_temporal_controller_set_reduced_motion
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint32]
    # int32_t xyg_temporal_controller_set_selection(uint64_t handle, const uint64_t * ids, uint64_t count)
    function = lib.xyg_temporal_controller_set_selection
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_uint64]
    # int32_t xyg_temporal_controller_state(uint64_t handle, uint64_t * out_instance_id, uint64_t * out_group_id, int64_t * out_domain_start, int64_t * out_domain_end, int64_t * out_range_start, int64_t * out_range_end, int64_t * out_cursor, int64_t * out_window, int64_t * out_step, int32_t * out_direction, uint32_t * out_rate_milli, uint32_t * out_loop_enabled, uint32_t * out_playing, uint32_t * out_reduced_motion, uint64_t * out_revision, uint32_t * out_disposed, uint64_t * out_selection, uint64_t selection_capacity, uint64_t * out_selection_count)
    function = lib.xyg_temporal_controller_state
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_temporal_controller_step(uint64_t handle)
    function = lib.xyg_temporal_controller_step
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_temporal_controller_tick(uint64_t handle, int64_t dt_micros, uint32_t * out_advanced)
    function = lib.xyg_temporal_controller_tick
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_int64, ctypes.c_void_p]
    # int32_t xyg_temporal_coordinate_deliver(uint64_t group_id, uint64_t source_instance, uint64_t revision, int64_t range_start, int64_t range_end, int64_t cursor, int64_t window, const uint64_t * selection, uint64_t selection_count, uint32_t * out_applied)
    function = lib.xyg_temporal_coordinate_deliver
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_int64, ctypes.c_int64, ctypes.c_int64, ctypes.c_int64, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_temporal_events_in_range(const int64_t * event_micros, const uint8_t * event_valid, uint64_t event_len, int64_t range_start, uint32_t range_start_valid, int64_t range_end, uint32_t range_end_valid, uint8_t * out_visibility, uint64_t capacity, uint64_t budget, const uint32_t * cancel_flag)
    function = lib.xyg_temporal_events_in_range
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_int64, ctypes.c_uint32, ctypes.c_int64, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_temporal_graph_cancel(uint64_t handle)
    function = lib.xyg_temporal_graph_cancel
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_temporal_graph_create(const void * descriptor, uint64_t * out_handle)
    function = lib.xyg_temporal_graph_create
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_temporal_graph_destroy(uint64_t handle)
    function = lib.xyg_temporal_graph_destroy
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_temporal_graph_frame(uint64_t handle, uint64_t revision, int64_t cursor_micros, int64_t range_start_micros, int64_t range_end_micros, uint64_t budget)
    function = lib.xyg_temporal_graph_frame
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_int64, ctypes.c_int64, ctypes.c_int64, ctypes.c_uint64]
    # int32_t xyg_temporal_graph_required_budget(uint64_t handle, uint64_t * out_budget)
    function = lib.xyg_temporal_graph_required_budget
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_temporal_graph_set_focus(uint64_t handle, uint32_t kind, const uint8_t * id)
    function = lib.xyg_temporal_graph_set_focus
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint32, ctypes.c_void_p]
    # int32_t xyg_temporal_graph_set_pinned(uint64_t handle, const uint8_t * node_ids, uint64_t node_count)
    function = lib.xyg_temporal_graph_set_pinned
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_uint64]
    # int32_t xyg_temporal_graph_set_selection(uint64_t handle, const uint8_t * node_ids, uint64_t node_count, const uint8_t * edge_ids, uint64_t edge_count)
    function = lib.xyg_temporal_graph_set_selection
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_uint64]
    # int32_t xyg_temporal_graph_snapshot_copy(uint64_t handle, uint64_t expected_revision, const void * buffers)
    function = lib.xyg_temporal_graph_snapshot_copy
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_temporal_graph_snapshot_meta(uint64_t handle, void * out_meta)
    function = lib.xyg_temporal_graph_snapshot_meta
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_temporal_interval_index_create(const void * descriptor, uint64_t * out_handle)
    function = lib.xyg_temporal_interval_index_create
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_temporal_interval_index_destroy(uint64_t handle)
    function = lib.xyg_temporal_interval_index_destroy
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_temporal_interval_index_len(uint64_t handle, uint64_t * out_len)
    function = lib.xyg_temporal_interval_index_len
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_temporal_interval_visibility_at(uint64_t handle, int64_t instant_micros, uint8_t * out_visibility, uint64_t capacity, uint64_t budget, const uint32_t * cancel_flag)
    function = lib.xyg_temporal_interval_visibility_at
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_int64, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_void_p]
    # uint64_t xyg_temporal_selection_limit()
    function = lib.xyg_temporal_selection_limit
    function.restype = ctypes.c_uint64
    function.argtypes = []
    # size_t xyg_text_block_measure(const uint8_t * text, size_t text_len, double font_size, double line_height, double max_width, double * out_metrics, uint32_t * out_line_lens, size_t line_cap, uint8_t * out_lines, size_t lines_cap)
    function = lib.xyg_text_block_measure
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_text_block_rotated_extent(double width, double height, double angle_degrees, double * out_x, double * out_y)
    function = lib.xyg_text_block_rotated_extent
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_tick_format(double value, double step, uint32_t kind, uint32_t scale, uint32_t theta_unit, const uint8_t * format, size_t format_len, uint32_t n_categories, const uint32_t * category_lens, const uint8_t * category_texts, size_t category_texts_len, uint8_t * out, size_t out_cap)
    function = lib.xyg_tick_format
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_tick_window(double range_lo, double range_hi, uint32_t theta_unit, uint32_t kind, uint32_t n_categories, double sector_lo, double sector_hi, double * out_lo, double * out_hi)
    function = lib.xyg_tick_window
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_tick_window_filter(const double * values, size_t n, double lo, double hi, uint32_t theta_unit, uint32_t kind, int32_t require_finite, double * out, size_t out_cap)
    function = lib.xyg_tick_window_filter
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_tight_layout_figure_extra(double canvas_w, double canvas_h, double suptitle_height, double suptitle_y, double xlabel_size, double ylabel_size, double legend_box_w, double * out_extra)
    function = lib.xyg_tight_layout_figure_extra
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p]
    # size_t xyg_tight_layout_solve(double canvas_w, double canvas_h, uint32_t nrows, uint32_t ncols, int32_t compact, const double * in_panels, size_t n_panels, const double * extra, double pad, double w_pad, double h_pad, double point_px, const double * rect, double * out)
    function = lib.xyg_tight_layout_solve
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_tile_budget_set(uint64_t bytes)
    function = lib.xyg_tile_budget_set
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_tile_store_append(uint64_t store, const double * x, const double * y, size_t len)
    function = lib.xyg_tile_store_append
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_tile_store_compose(uint64_t store, double lo_x, double hi_x, double lo_y, double hi_y, size_t w, size_t h, size_t max_upsample, float * out)
    function = lib.xyg_tile_store_compose
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p]
    # Buffer contract: out: out_capacity >= checked(w * h) elements and total bytes <= isize::MAX; null output, zero dimensions, arithmetic overflow, impossible slice size, or short capacity returns -1 before output access; success returns nonnegative_level
    # Buffer contract: out_rgba: out_rgba_capacity >= checked(w * h * 4) bytes and total bytes <= isize::MAX; null output, zero dimensions, arithmetic overflow, impossible slice size, or short capacity returns -1 before output access; success returns nonnegative_level
    # int32_t xyg_tile_store_compose_color(uint64_t store, double lo_x, double hi_x, double lo_y, double hi_y, size_t w, size_t h, size_t max_upsample, float * out, size_t out_capacity, uint8_t * out_rgba, size_t out_rgba_capacity)
    function = lib.xyg_tile_store_compose_color
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    # int32_t xyg_tile_store_fetch(uint64_t store, uint32_t level, uint32_t tx, uint32_t ty, uint32_t * out_counts, uint16_t * out_color)
    function = lib.xyg_tile_store_fetch
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_tile_store_free(uint64_t store)
    function = lib.xyg_tile_store_free
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64]
    # int32_t xyg_tile_store_stats(uint64_t store, uint64_t * out)
    function = lib.xyg_tile_store_stats
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_uint64, ctypes.c_void_p]
    # int32_t xyg_transition_keys_fixed(const uint8_t * data, size_t len, size_t width, uint32_t kind, int32_t swap_endian, uint32_t * out_lo, uint32_t * out_hi, size_t * out_error_first, size_t * out_error_index)
    function = lib.xyg_transition_keys_fixed
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_triangle_edges(const double * x, const double * y, size_t vertex_count, const int64_t * triangles, size_t face_count, double * out_x0, double * out_x1, double * out_y0, double * out_y1)
    function = lib.xyg_triangle_edges
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_valid_indices_f64(const double *const * columns, size_t n_columns, size_t len, uint64_t positive_mask, uint32_t * out, size_t capacity)
    function = lib.xyg_valid_indices_f64
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_vector_segments(const double * x, const double * y, const double * u, const double * v, size_t len, double scale, uint32_t pivot, double head_ratio, double * out_x0, double * out_x1, double * out_y0, double * out_y1)
    function = lib.xyg_vector_segments
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_uint32, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_view_visible_mask(const double * x, const double * y, size_t n, double lo_x, double hi_x, double lo_y, double hi_y, uint8_t * out)
    function = lib.xyg_view_visible_mask
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p]
    # int32_t xyg_violin_density(const double * data, size_t len, size_t n_bins, double * out_edges, double * out_density)
    function = lib.xyg_violin_density
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_violin_rects(const double * values, size_t values_len, const size_t * offsets, size_t offsets_len, const double * centers, size_t centers_len, size_t bins, double width, uint32_t orientation, double * out_x0, double * out_y0, double * out_x1, double * out_y1, uint32_t * out_groups, double * out_edges, double * out_density, size_t out_cap)
    function = lib.xyg_violin_rects
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_double, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
    # size_t xyg_weighted_ecdf(const double * values, const double * weights, size_t len, double * out_values, double * out_cumulative)
    function = lib.xyg_weighted_ecdf
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
    # int32_t xyg_welch_spectra(const double * x, const double * y, size_t len, size_t nfft, size_t noverlap, double sample_rate, double * out_frequency, double * out_pxx, double * out_pyy, double * out_pxy_real, double * out_pxy_imag)
    function = lib.xyg_welch_spectra
    function.restype = ctypes.c_int32
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_wind_rose_bins(const double * directions, const double * speeds, size_t len, size_t sectors, const double * speed_edges, size_t n_speed_edges, double * out_edges, size_t capacity_edges, double * out_centres, double * out_counts, size_t capacity_counts, size_t * out_n_obs)
    function = lib.xyg_wind_rose_bins
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    # size_t xyg_x_axis_title_room(const uint8_t * title, size_t title_len, double font_size, double offset, int32_t top, double * out_room)
    function = lib.xyg_x_axis_title_room
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_void_p]
    # size_t xyg_x_tick_label_edge_rooms(double plot_w, const double * positions, size_t n, const uint32_t * label_lens, const uint8_t * labels, size_t labels_len, const double * angles, const uint32_t * anchors, double font_size, double * out_left, double * out_right)
    function = lib.xyg_x_tick_label_edge_rooms
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_x_tick_label_room(const uint32_t * label_lens, const uint8_t * labels, size_t labels_len, size_t n, const double * angles, const uint32_t * rows, double font_size, double label_offset, double title_room, double * out_room)
    function = lib.xyg_x_tick_label_room
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_void_p]
    # size_t xyg_y_axis_left_room(double tick_offset, double tick_room, const uint8_t * title, size_t title_len, double title_font_size, double title_gap, double * out_room)
    function = lib.xyg_y_axis_left_room
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_void_p]
    # size_t xyg_y_tick_label_extent(const uint32_t * label_lens, const uint8_t * labels, size_t labels_len, size_t n, double font_size, double angle, double * out_extent)
    function = lib.xyg_y_tick_label_extent
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_double, ctypes.c_double, ctypes.c_void_p]
    # size_t xyg_zone_maps(const double * data, size_t len, size_t chunk_size, double * out_min, double * out_max, uint64_t * out_count, uint64_t * out_null_count, double * out_sum, double * out_sum_sq, double * out_positive_min, double * out_positive_max)
    function = lib.xyg_zone_maps
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    # size_t xyg_zone_maps_pair(const double * x, const double * y, size_t len, size_t chunk_size, void * out_x, void * out_y)
    function = lib.xyg_zone_maps_pair
    function.restype = ctypes.c_size_t
    function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p]
