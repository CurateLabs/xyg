/** ctypes-compatible scene bulk packers (ABI 321-324). Mirrors python/xyg/_scene_bulk_native.py. */
import koffi from "koffi";
import { pointer } from "./native.js";
import { u8Ptr, f64Ptr, u32Ptr } from "./encode.js";
import {
  xySceneChromePack,
  xySceneFigureSupportMaterialize,
  xyScenePolarInputPack,
  xySceneXyafBulkPack,
  xySceneXytaTraceObservationsMaterialize,
  xySceneXytcTraceObservationsMaterialize,
} from "./native.js";

const SCENE_XYCF_PACK_MAX = 1 << 20;
const SCENE_FIGURE_SUPPORT_PACK_MAX = 1 << 18;
const SCENE_POLAR_INPUT_PACK_MAX = 92;
const SCENE_XYAF_BULK_PACK_MAX = 1 << 22;
const SCENE_XYTA_TRACE_OBSERVATIONS_MAX_BYTES = 1 << 22;
const SCENE_XYTC_TRACE_OBSERVATIONS_MAX_BYTES = 1 << 20;

const StringRef = koffi.struct("XygStringRef", {
  ptr: "const uint8_t *",
  len: "size_t",
});

const ChromeAxisStyleIn = koffi.struct("XygChromeAxisStyleIn", {
  grid_color: StringRef,
  grid_width_present: "int32_t",
  grid_width: "double",
  grid_opacity_present: "int32_t",
  grid_opacity: "float",
  axis_color: StringRef,
  axis_width_present: "int32_t",
  axis_width: "double",
  tick_color: StringRef,
  tick_width_present: "int32_t",
  tick_width: "double",
  tick_length_present: "int32_t",
  tick_length: "double",
  tick_direction: StringRef,
  tick_label_color: StringRef,
  label_color: StringRef,
});

const ChromeAxisIn = koffi.struct("XygChromeAxisIn", {
  side_code: "uint8_t",
  tick_sides_mask: "uint8_t",
  label_sides_mask: "uint8_t",
  style: ChromeAxisStyleIn,
  minor_style: ChromeAxisStyleIn,
});

const ChromeCollisionAxisIn = koffi.struct("XygChromeCollisionAxisIn", {
  strategy: StringRef,
  collision: StringRef,
  anchor: StringRef,
  min_gap_present: "int32_t",
  min_gap: "double",
  angle_present: "int32_t",
  angle: "double",
  tick_kind_category: "int32_t",
});

const ChromeLegendIn = koffi.struct("XygChromeLegendIn", {
  unsupported_keys: "int32_t",
  toggle: "int32_t",
  highlight: "int32_t",
  loc: StringRef,
  title: StringRef,
  ncols: "uint32_t",
  unsupported_style: "int32_t",
  font_size_present: "int32_t",
  font_size: "double",
  title_font_size_present: "int32_t",
  title_font_size: "double",
  color: StringRef,
  background: StringRef,
});

const ChromeColorbarIn = koffi.struct("XygChromeColorbarIn", {
  domain_lo: "double",
  domain_hi: "double",
  stop_count: "uint32_t",
  side_bottom: "int32_t",
  invalid_side: "int32_t",
  minor_ticks: "int32_t",
  title: StringRef,
  text_rgba: "uint8_t[4]",
  tick_count: "uint32_t",
});

const SceneChromePackIn = koffi.struct("XygSceneChromePackIn", {
  width: "double",
  height: "double",
  show_legend: "int32_t",
  colorbar_ok: "int32_t",
  polar: "int32_t",
  has_margins: "int32_t",
  margin_left: "double",
  margin_right: "double",
  margin_top: "double",
  margin_bottom: "double",
  has_padding: "int32_t",
  pad_left: "double",
  pad_right: "double",
  pad_top: "double",
  pad_bottom: "double",
  title: StringRef,
  x_label: StringRef,
  y_label: StringRef,
  x_format: StringRef,
  y_format: StringRef,
  x_scale_kind: "uint32_t",
  y_scale_kind: "uint32_t",
  x_lo: "double",
  x_hi: "double",
  x_constant: "double",
  y_lo: "double",
  y_hi: "double",
  y_constant: "double",
  x_nonpositive_mask: "uint8_t",
  y_nonpositive_mask: "uint8_t",
  x_tick_kind: "uint8_t",
  y_tick_kind: "uint8_t",
  x_axis: ChromeAxisIn,
  y_axis: ChromeAxisIn,
  x_major_len: "size_t",
  y_major_len: "size_t",
  x_minor_len: "size_t",
  y_minor_len: "size_t",
  x_tick_label_count: "uint32_t",
  y_tick_label_count: "uint32_t",
  x_collision: ChromeCollisionAxisIn,
  y_collision: ChromeCollisionAxisIn,
  chart_background: StringRef,
  plot_background: StringRef,
  legend: ChromeLegendIn,
  colorbar_present: "int32_t",
  colorbar: ChromeColorbarIn,
});

const FigureSupportAnnotationObs = koffi.struct("XygFigureSupportAnnotationObs", {
  has_html: "int32_t",
  has_collision: "int32_t",
  has_markup: "int32_t",
  has_custom_typography: "int32_t",
  has_class_name: "int32_t",
  kind_is_supported_text: "int32_t",
  has_text: "int32_t",
});

const FigureSupportAxisObsIn = koffi.struct("XygFigureSupportAxisObsIn", {
  axis_code: "uint8_t",
  key_count: "uint32_t",
  strategy: StringRef,
  collision: StringRef,
});

const FigureSupportTraceObsIn = koffi.struct("XygFigureSupportTraceObsIn", {
  kind: StringRef,
  x_axis: StringRef,
  y_axis: StringRef,
  hidden: "int32_t",
  has_per_item_channels: "int32_t",
  density_aggregates_color: "int32_t",
  marker_glyph_present: "int32_t",
  marker_glyph: StringRef,
  marker_path_present: "int32_t",
  marker_path_valid: "int32_t",
  marker_path_filled_small: "int32_t",
  curve_present: "int32_t",
  curve: StringRef,
  linecap_present: "int32_t",
  linecap: StringRef,
  dash_present: "int32_t",
  dash_text: StringRef,
  dash_is_array: "int32_t",
  fill_present: "int32_t",
  fill_is_string: "int32_t",
  fill_gradient_admitted: "int32_t",
  hexbin_reduce: StringRef,
  heatmap_truecolor: "int32_t",
  heatmap_has_colormap: "int32_t",
  heatmap_has_rgba_grid: "int32_t",
  heatmap_has_rgba: "int32_t",
  rect_gradient_fail: "int32_t",
  corner_radius_len: "size_t",
  corner_radius_seq: "int32_t",
  wedge_gap: "double",
  ribbon_color2_fail: "int32_t",
  color_channel_unsupported: "int32_t",
});

const ScenePolarInputPackIn = koffi.struct("XygScenePolarInputPackIn", {
  polar: "int32_t",
  theta_unit: "uint32_t",
  theta_direction: "uint32_t",
  n_categories: "uint32_t",
  grid_shape: "uint8_t",
  r_scale_kind: "uint32_t",
  r_mask_nonpositive: "int32_t",
  sector_start: "double",
  sector_end: "double",
  r_lo: "double",
  r_hi: "double",
  r_origin_is_nan: "int32_t",
  r_origin: "double",
  hole: "double",
  r_constant: "double",
  theta_zero_is_label: "int32_t",
  theta_zero_label: StringRef,
  theta_zero_numeric: "double",
});

function stringRef(value, keep) {
  if (value == null || value === "") {
    return { ptr: 0n, len: 0n };
  }
  const bytes = new TextEncoder().encode(String(value));
  keep.push(bytes);
  return { ptr: u8Ptr(bytes), len: BigInt(bytes.length) };
}

function optionalStringRef(value, keep) {
  if (value == null) return { ptr: 0n, len: 0n };
  const text = String(value);
  if (!text) return { ptr: 0n, len: 0n };
  return stringRef(text, keep);
}

function chromeAxisStyle(style = {}) {
  const keep = [];
  const pick = (key) => optionalStringRef(style[key], keep);
  return {
    style: {
      grid_color: pick("grid_color"),
      grid_width_present: Object.hasOwn(style, "grid_width") ? 1 : 0,
      grid_width: Number(style.grid_width ?? 0),
      grid_opacity_present: Object.hasOwn(style, "grid_opacity") ? 1 : 0,
      grid_opacity: Number(style.grid_opacity ?? 0),
      axis_color: pick("axis_color"),
      axis_width_present: Object.hasOwn(style, "axis_width") ? 1 : 0,
      axis_width: Number(style.axis_width ?? 0),
      tick_color: pick("tick_color"),
      tick_width_present: Object.hasOwn(style, "tick_width") ? 1 : 0,
      tick_width: Number(style.tick_width ?? 0),
      tick_length_present: Object.hasOwn(style, "tick_length") ? 1 : 0,
      tick_length: Number(style.tick_length ?? 0),
      tick_direction: pick("tick_direction"),
      tick_label_color: pick("tick_label_color"),
      label_color: pick("label_color"),
    },
    keep,
  };
}

function chromeAxis(axis) {
  const stylePack = chromeAxisStyle(axis.style ?? {});
  const minorPack = chromeAxisStyle(axis.minor_style ?? {});
  return {
    axis: {
      side_code: Number(axis.side_code) & 0xff,
      tick_sides_mask: Number(axis.tick_sides_mask) & 0xff,
      label_sides_mask: Number(axis.label_sides_mask) & 0xff,
      style: stylePack.style,
      minor_style: minorPack.style,
    },
    keep: [...stylePack.keep, ...minorPack.keep],
  };
}

function collisionAxis(collision, keep) {
  return {
    strategy: optionalStringRef(collision.strategy, keep),
    collision: optionalStringRef(collision.collision, keep),
    anchor: optionalStringRef(collision.anchor, keep),
    min_gap_present: collision.min_gap == null ? 0 : 1,
    min_gap: Number(collision.min_gap ?? 0),
    angle_present: collision.angle == null ? 0 : 1,
    angle: Number(collision.angle ?? 0),
    tick_kind_category: collision.tick_kind_category ? 1 : 0,
  };
}

/** Bulk-pack XYCF v1 chrome facts via `xyg_scene_chrome_pack` (ABI 321). */
export function sceneChromePack(kwargs) {
  const keep = [];
  const legendKw = kwargs.legend ?? {};
  const cbPayload = kwargs.colorbar;
  let colorbarPresent = 0;
  let colorbar = {
    domain_lo: 0,
    domain_hi: 0,
    stop_count: 0,
    side_bottom: 0,
    invalid_side: 0,
    minor_ticks: 0,
    title: { ptr: 0n, len: 0n },
    text_rgba: Uint8Array.of(32, 32, 32, 255),
    tick_count: 0,
  };
  let colorbarStops = new Uint8Array(0);
  let colorbarTicks = new Float64Array(0);
  if (cbPayload) {
    colorbarPresent = 1;
    const stops = cbPayload.stops ?? [];
    const stopBytes = new Uint8Array(stops.length * 12);
    const stopView = new DataView(stopBytes.buffer);
    for (let index = 0; index < stops.length; index += 1) {
      const [value, rgba] = stops[index];
      stopView.setFloat64(index * 12, Number(value), true);
      stopBytes.set(rgba.slice(0, 4), index * 12 + 8);
    }
    colorbarStops = stopBytes;
    if (cbPayload.ticks != null) {
      colorbarTicks = Float64Array.from(cbPayload.ticks, Number);
    }
    colorbar = {
      domain_lo: Number(cbPayload.domain_lo),
      domain_hi: Number(cbPayload.domain_hi),
      stop_count: stops.length,
      side_bottom: cbPayload.side_bottom ? 1 : 0,
      invalid_side: cbPayload.invalid_side ? 1 : 0,
      minor_ticks: cbPayload.minor_ticks ? 1 : 0,
      title: optionalStringRef(cbPayload.title, keep),
      text_rgba: Uint8Array.from(cbPayload.text_rgba ?? [32, 32, 32, 255]).slice(0, 4),
      tick_count: colorbarTicks.length,
    };
  }
  const xAxisPack = chromeAxis(kwargs.x_axis);
  const yAxisPack = chromeAxis(kwargs.y_axis);
  keep.push(...xAxisPack.keep, ...yAxisPack.keep);
  const xMajor = kwargs.x_major == null ? new Float64Array(0) : Float64Array.from(kwargs.x_major, Number);
  const yMajor = kwargs.y_major == null ? new Float64Array(0) : Float64Array.from(kwargs.y_major, Number);
  const xMinor = Float64Array.from(kwargs.x_minor ?? [], Number);
  const yMinor = Float64Array.from(kwargs.y_minor ?? [], Number);
  const xTickLabels = kwargs.x_tick_labels ?? [];
  const yTickLabels = kwargs.y_tick_labels ?? [];
  const xLabelRefs = xTickLabels.map((label) => stringRef(label, keep));
  const yLabelRefs = yTickLabels.map((label) => stringRef(label, keep));
  const margins = kwargs.margins ?? [0, 0, 0, 0];
  const padding = kwargs.padding ?? [0, 0, 0, 0];
  const pack = {
    width: Number(kwargs.width),
    height: Number(kwargs.height),
    show_legend: kwargs.show_legend === false ? 0 : 1,
    colorbar_ok: kwargs.colorbar_ok ? 1 : 0,
    polar: kwargs.polar ? 1 : 0,
    has_margins: kwargs.has_margins ? 1 : 0,
    margin_left: Number(margins[0]),
    margin_right: Number(margins[1]),
    margin_top: Number(margins[2]),
    margin_bottom: Number(margins[3]),
    has_padding: kwargs.has_padding ? 1 : 0,
    pad_left: Number(padding[0]),
    pad_right: Number(padding[1]),
    pad_top: Number(padding[2]),
    pad_bottom: Number(padding[3]),
    title: stringRef(kwargs.title ?? "", keep),
    x_label: stringRef(kwargs.x_label ?? "", keep),
    y_label: stringRef(kwargs.y_label ?? "", keep),
    x_format: optionalStringRef(kwargs.x_format, keep),
    y_format: optionalStringRef(kwargs.y_format, keep),
    x_scale_kind: Number(kwargs.x_scale_kind ?? 0),
    y_scale_kind: Number(kwargs.y_scale_kind ?? 0),
    x_lo: Number(kwargs.x_lo),
    x_hi: Number(kwargs.x_hi),
    x_constant: Number(kwargs.x_constant ?? 1),
    y_lo: Number(kwargs.y_lo),
    y_hi: Number(kwargs.y_hi),
    y_constant: Number(kwargs.y_constant ?? 1),
    x_nonpositive_mask: Number(kwargs.x_nonpositive_mask ?? 0),
    y_nonpositive_mask: Number(kwargs.y_nonpositive_mask ?? 0),
    x_tick_kind: Number(kwargs.x_tick_kind ?? 0),
    y_tick_kind: Number(kwargs.y_tick_kind ?? 0),
    x_axis: xAxisPack.axis,
    y_axis: yAxisPack.axis,
    x_major_len: BigInt(xMajor.length),
    y_major_len: BigInt(yMajor.length),
    x_minor_len: BigInt(xMinor.length),
    y_minor_len: BigInt(yMinor.length),
    x_tick_label_count: xTickLabels.length,
    y_tick_label_count: yTickLabels.length,
    x_collision: collisionAxis(kwargs.x_collision ?? {}, keep),
    y_collision: collisionAxis(kwargs.y_collision ?? {}, keep),
    chart_background: optionalStringRef(kwargs.chart_background, keep),
    plot_background: optionalStringRef(kwargs.plot_background, keep),
    legend: {
      unsupported_keys: legendKw.unsupported_keys ? 1 : 0,
      toggle: legendKw.toggle ? 1 : 0,
      highlight: legendKw.highlight ? 1 : 0,
      loc: legendKw.loc == null ? { ptr: 0n, len: 0n } : stringRef(String(legendKw.loc), keep),
      title: optionalStringRef(legendKw.title, keep),
      ncols: Number(legendKw.ncols ?? 1),
      unsupported_style: legendKw.unsupported_style ? 1 : 0,
      font_size_present: legendKw.font_size == null ? 0 : 1,
      font_size: Number(legendKw.font_size ?? 0),
      title_font_size_present: legendKw.title_font_size == null ? 0 : 1,
      title_font_size: Number(legendKw.title_font_size ?? 0),
      color: optionalStringRef(legendKw.color, keep),
      background: optionalStringRef(legendKw.background, keep),
    },
    colorbar_present: colorbarPresent,
    colorbar,
  };
  const inputBuf = Buffer.alloc(koffi.sizeof(SceneChromePackIn));
  koffi.encode(inputBuf, SceneChromePackIn, pack);
  const xLabelBuf = Buffer.alloc(Math.max(1, xLabelRefs.length * 16));
  const yLabelBuf = Buffer.alloc(Math.max(1, yLabelRefs.length * 16));
  for (let index = 0; index < xLabelRefs.length; index += 1) {
    koffi.encode(xLabelBuf, index * 16, StringRef, xLabelRefs[index]);
  }
  for (let index = 0; index < yLabelRefs.length; index += 1) {
    koffi.encode(yLabelBuf, index * 16, StringRef, yLabelRefs[index]);
  }
  const out = new Uint8Array(SCENE_XYCF_PACK_MAX);
  const outLen = new BigUint64Array(1);
  const code = Number(xySceneChromePack(
    koffi.as(inputBuf, "const void *"),
    xMajor.length ? f64Ptr(xMajor) : 0,
    yMajor.length ? f64Ptr(yMajor) : 0,
    xMinor.length ? f64Ptr(xMinor) : 0,
    yMinor.length ? f64Ptr(yMinor) : 0,
    xLabelRefs.length ? koffi.as(xLabelBuf, "const void *") : 0,
    yLabelRefs.length ? koffi.as(yLabelBuf, "const void *") : 0,
    colorbarStops.length ? u8Ptr(colorbarStops) : 0,
    colorbarTicks.length ? f64Ptr(colorbarTicks) : 0,
    u8Ptr(out),
    BigInt(out.length),
    pointer(outLen, "size_t *"),
  ));
  if (code === -2) throw new RangeError("sceneChromePack output buffer too small");
  if (code !== 0) throw new RangeError("invalid sceneChromePack arguments");
  return out.subarray(0, Number(outLen[0]));
}

/** Materialize XYFS v2 figure support via `xyg_scene_figure_support_materialize` (ABI 322). */
export function sceneFigureSupportMaterialize({
  polar = false,
  colorbarUnsupported = false,
  hasCustomFont = false,
  hasBrowserCss = false,
  hasExtraLegends = false,
  annotations = [],
  axes = [],
  traces = [],
} = {}) {
  const keep = [];
  const annRows = annotations.map((row) => ({
    has_html: row.has_html ? 1 : 0,
    has_collision: row.has_collision ? 1 : 0,
    has_markup: row.has_markup ? 1 : 0,
    has_custom_typography: row.has_custom_typography ? 1 : 0,
    has_class_name: row.has_class_name ? 1 : 0,
    kind_is_supported_text: row.kind_is_supported_text ? 1 : 0,
    has_text: row.has_text ? 1 : 0,
  }));
  const axisKeysBlob = [];
  const axisRows = axes.map((row) => {
    const keys = row.keys ?? [];
    for (const key of keys) {
      const encoded = new TextEncoder().encode(String(key));
      axisKeysBlob.push(encoded.length & 0xff, (encoded.length >> 8) & 0xff, ...encoded);
    }
    return {
      axis_code: Number(row.axis_code) & 0xff,
      key_count: keys.length,
      strategy: optionalStringRef(row.tick_label_strategy, keep),
      collision: optionalStringRef(row.collision, keep),
    };
  });
  const axisKeys = Uint8Array.from(axisKeysBlob);
  const cornerRadius = [];
  const traceRows = traces.map((row) => {
    const radius = (row.corner_radius_values ?? [0]).map(Number);
    cornerRadius.push(...radius);
    return {
      kind: stringRef(row.kind ?? "mark", keep),
      x_axis: stringRef(row.x_axis ?? "x", keep),
      y_axis: stringRef(row.y_axis ?? "y", keep),
      hidden: row.hidden ? 1 : 0,
      has_per_item_channels: row.has_per_item_channels ? 1 : 0,
      density_aggregates_color: row.density_aggregates_color ? 1 : 0,
      marker_glyph_present: row.marker_glyph_present ? 1 : 0,
      marker_glyph: optionalStringRef(row.marker_glyph, keep),
      marker_path_present: row.marker_path_present ? 1 : 0,
      marker_path_valid: row.marker_path_valid ? 1 : 0,
      marker_path_filled_small: row.marker_path_filled_small ? 1 : 0,
      curve_present: row.curve_present ? 1 : 0,
      curve: optionalStringRef(row.curve, keep),
      linecap_present: row.linecap_present ? 1 : 0,
      linecap: optionalStringRef(row.linecap, keep),
      dash_present: row.dash_present ? 1 : 0,
      dash_text: optionalStringRef(row.dash_text, keep),
      dash_is_array: row.dash_is_array ? 1 : 0,
      fill_present: row.fill_present ? 1 : 0,
      fill_is_string: row.fill_is_string ? 1 : 0,
      fill_gradient_admitted: row.fill_gradient_admitted ? 1 : 0,
      hexbin_reduce: optionalStringRef(row.hexbin_reduce, keep),
      heatmap_truecolor: row.heatmap_truecolor ? 1 : 0,
      heatmap_has_colormap: row.heatmap_has_colormap ? 1 : 0,
      heatmap_has_rgba_grid: row.heatmap_has_rgba_grid ? 1 : 0,
      heatmap_has_rgba: row.heatmap_has_rgba ? 1 : 0,
      rect_gradient_fail: row.rect_gradient_fail ? 1 : 0,
      corner_radius_len: BigInt(radius.length),
      corner_radius_seq: row.corner_radius_seq ? 1 : 0,
      wedge_gap: Number(row.wedge_gap ?? 0),
      ribbon_color2_fail: row.ribbon_color2_fail ? 1 : 0,
      color_channel_unsupported: row.color_channel_unsupported ? 1 : 0,
    };
  });
  const annBuf = Buffer.alloc(Math.max(1, annRows.length * koffi.sizeof(FigureSupportAnnotationObs)));
  for (let index = 0; index < annRows.length; index += 1) {
    koffi.encode(annBuf, index * koffi.sizeof(FigureSupportAnnotationObs), FigureSupportAnnotationObs, annRows[index]);
  }
  const axisBuf = Buffer.alloc(Math.max(1, axisRows.length * koffi.sizeof(FigureSupportAxisObsIn)));
  for (let index = 0; index < axisRows.length; index += 1) {
    koffi.encode(axisBuf, index * koffi.sizeof(FigureSupportAxisObsIn), FigureSupportAxisObsIn, axisRows[index]);
  }
  const traceBuf = Buffer.alloc(Math.max(1, traceRows.length * koffi.sizeof(FigureSupportTraceObsIn)));
  for (let index = 0; index < traceRows.length; index += 1) {
    koffi.encode(traceBuf, index * koffi.sizeof(FigureSupportTraceObsIn), FigureSupportTraceObsIn, traceRows[index]);
  }
  const radiusArr = Float64Array.from(cornerRadius, Number);
  const out = new Uint8Array(SCENE_FIGURE_SUPPORT_PACK_MAX);
  const outLen = new BigUint64Array(1);
  const code = Number(xySceneFigureSupportMaterialize(
    polar ? 1 : 0,
    colorbarUnsupported ? 1 : 0,
    hasCustomFont ? 1 : 0,
    hasBrowserCss ? 1 : 0,
    hasExtraLegends ? 1 : 0,
    annRows.length ? koffi.as(annBuf, "const void *") : 0,
    BigInt(annotations.length),
    axisRows.length ? koffi.as(axisBuf, "const void *") : 0,
    BigInt(axes.length),
    axisKeys.length ? u8Ptr(axisKeys) : 0,
    BigInt(axisKeys.length),
    traceRows.length ? koffi.as(traceBuf, "const void *") : 0,
    BigInt(traces.length),
    radiusArr.length ? f64Ptr(radiusArr) : 0,
    u8Ptr(out),
    BigInt(out.length),
    pointer(outLen, "size_t *"),
  ));
  if (code === -2) throw new RangeError("sceneFigureSupportMaterialize output buffer too small");
  if (code !== 0) throw new RangeError("invalid sceneFigureSupportMaterialize arguments");
  return out.subarray(0, Number(outLen[0]));
}

const SceneXytaColorChannelDesc = koffi.struct("XygSceneXytaColorChannelDesc", {
  present: "int32_t",
  mode_len: "size_t",
  constant_len: "size_t",
  colormap_len: "size_t",
  has_domain: "int32_t",
  domain_lo: "double",
  domain_hi: "double",
  values_f64_len: "size_t",
  rgba_u8_len: "size_t",
  codes_u8_len: "size_t",
  codes_i64_len: "size_t",
  palette_count: "size_t",
  n_categories: "size_t",
});

const SceneXytaStyleChannelDesc = koffi.struct("XygSceneXytaStyleChannelDesc", {
  present: "int32_t",
  values_f64_len: "size_t",
});

const SceneXytaTraceObservationsIn = koffi.struct("XygSceneXytaTraceObservationsIn", {
  trace_id: "uint32_t",
  pack_heatmap: "int32_t",
  pack_hexbin_colormap: "int32_t",
  pack_hexbin_rgba: "int32_t",
  pack_ribbon_ends: "int32_t",
  pack_mesh_faces: "int32_t",
  pack_scatter_paint: "int32_t",
  pack_density: "int32_t",
  domain_x0: "double",
  domain_x1: "double",
  domain_y0: "double",
  domain_y1: "double",
  point_count: "size_t",
  fallback_color_len: "size_t",
  style_color_len: "size_t",
  style_stroke_len: "size_t",
  style_stroke_width: "double",
  has_style_stroke_width: "int32_t",
  style_opacity: "float",
  has_style_opacity: "int32_t",
  style_fill_opacity: "float",
  has_style_fill_opacity: "int32_t",
  style_truecolor: "int32_t",
  style_domain_lo: "double",
  style_domain_hi: "double",
  has_style_domain: "int32_t",
  style_colormap_mode: "int32_t",
  style_colormap_named_len: "size_t",
  style_colormap_stops_len: "size_t",
  grid_shape_rows: "double",
  grid_shape_cols: "double",
  has_grid_shape: "int32_t",
  grid_values_len: "size_t",
  rgba_u8_len: "size_t",
  rgba_grid_f64_len: "size_t",
  x_values_len: "size_t",
  y_values_len: "size_t",
});

const SceneXytaTraceObservationsOut = koffi.struct("XygSceneXytaTraceObservationsOut", {
  trace_id: "uint32_t",
  pack_heatmap: "int32_t",
  pack_hexbin_colormap: "int32_t",
  pack_hexbin_rgba: "int32_t",
  pack_ribbon_ends: "int32_t",
  pack_mesh_faces: "int32_t",
  pack_scatter_paint: "int32_t",
  pack_density: "int32_t",
  grid_shape_rows: "double",
  grid_shape_cols: "double",
  has_grid_shape: "int32_t",
  has_grid: "int32_t",
  has_rgba: "int32_t",
  has_rgba_grid: "int32_t",
  truecolor: "int32_t",
  has_cmap_domain: "int32_t",
  cmap_lo: "double",
  cmap_hi: "double",
  has_color_ch: "int32_t",
  has_style_color: "int32_t",
  has_opacity: "int32_t",
  has_fill_opacity: "int32_t",
  opacity: "float",
  fill_opacity: "float",
  domain_x0: "double",
  domain_x1: "double",
  domain_y0: "double",
  domain_y1: "double",
  cmap_flags: "uint32_t",
  rows: "int32_t",
  cols: "int32_t",
  grid_len: "size_t",
  rgba_len: "size_t",
  rgba_grid_len: "size_t",
  x_len: "size_t",
  y_len: "size_t",
  mean_rgba_len: "size_t",
  idx_len: "size_t",
  lut_len: "size_t",
  cmap_len: "size_t",
  stops_len: "size_t",
  color_ch_len: "size_t",
  style_color_len: "size_t",
  grid_off: "size_t",
  rgba_off: "size_t",
  rgba_grid_off: "size_t",
  x_off: "size_t",
  y_off: "size_t",
  mean_rgba_off: "size_t",
  idx_off: "size_t",
  lut_off: "size_t",
  cmap_off: "size_t",
  stops_off: "size_t",
  color_ch_off: "size_t",
  style_color_off: "size_t",
});

const SceneXytcTraceObservationsIn = koffi.struct("XygSceneXytcTraceObservationsIn", {
  show_legend: "int32_t",
  has_name: "int32_t",
  marker_path_present: "int32_t",
  use_density: "int32_t",
  joined_fill: "int32_t",
  symbol_is_int: "int32_t",
  symbol_int: "uint16_t",
  opacity: "double",
  fill_opacity: "double",
  stroke_opacity: "double",
  line_opacity: "double",
  has_stroke: "int32_t",
  has_line_color: "int32_t",
  has_color: "int32_t",
  has_size: "int32_t",
  size: "double",
  has_size_ch: "int32_t",
  has_size_ch_constant: "int32_t",
  size_ch_constant: "double",
  has_stroke_width: "int32_t",
  stroke_width: "double",
  has_width: "int32_t",
  width: "double",
  has_line_width: "int32_t",
  line_width: "double",
  has_hex_dx: "int32_t",
  hex_dx: "double",
  has_hex_dy: "int32_t",
  hex_dy: "double",
  has_stroke_perimeter: "int32_t",
  stroke_perimeter_is_bool: "int32_t",
  stroke_perimeter_true: "int32_t",
  wedge_gap_raw: "double",
  dash_is_array: "int32_t",
  has_fill: "int32_t",
  fill_is_string: "int32_t",
  fill_has_full_spec: "int32_t",
  fill_stop_count: "size_t",
  marker_path_filled: "int32_t",
  marker_contour_count: "size_t",
  has_color2: "int32_t",
  kind_is_ribbon: "int32_t",
  has_end_pair: "int32_t",
  corner_radius_seq: "int32_t",
  corner_radius_r0: "double",
  corner_radius_r1: "double",
  color_ch_present: "int32_t",
  color_ch_has_constant: "int32_t",
  kind_len: "size_t",
  name_len: "size_t",
  symbol_len: "size_t",
  stroke_len: "size_t",
  line_color_len: "size_t",
  color_css_len: "size_t",
  dash_len: "size_t",
  dash_values_len: "size_t",
  fill_string_len: "size_t",
  fill_space_len: "size_t",
  fill_dir_len: "size_t",
  fill_stop_t_len: "size_t",
  fill_stop_css_len: "size_t",
  fill_stop_css_lens_len: "size_t",
  fill_dict_gradient_len: "size_t",
  fill_dict_space_len: "size_t",
  marker_values_len: "size_t",
  marker_lens_len: "size_t",
  marker_glyph_len: "size_t",
  source_paint_len: "size_t",
  color2_source_const_len: "size_t",
  color2_target_const_len: "size_t",
  color_mode_len: "size_t",
  color_const_len: "size_t",
  linecap_len: "size_t",
  step_len: "size_t",
  curve_len: "size_t",
});

const SceneXytcTraceObservationsOut = koffi.struct("XygSceneXytcTraceObservationsOut", {
  show_legend: "int32_t",
  has_name: "int32_t",
  marker_path_present: "int32_t",
  use_density: "int32_t",
  joined_fill: "int32_t",
  marker_packed: "int32_t",
  glyph_packed: "int32_t",
  color2_class: "int32_t",
  color2_gradient_packed: "int32_t",
  symbol_is_int: "int32_t",
  symbol_int: "uint16_t",
  opacity: "double",
  fill_opacity: "double",
  stroke_opacity: "double",
  line_opacity: "double",
  has_stroke: "int32_t",
  has_line_color: "int32_t",
  has_size: "int32_t",
  size: "double",
  has_size_ch: "int32_t",
  has_size_ch_constant: "int32_t",
  size_ch_constant: "double",
  has_stroke_width: "int32_t",
  stroke_width: "double",
  has_width: "int32_t",
  width: "double",
  has_line_width: "int32_t",
  line_width: "double",
  has_hex_dx: "int32_t",
  hex_dx: "double",
  has_hex_dy: "int32_t",
  hex_dy: "double",
  has_stroke_perimeter: "int32_t",
  stroke_perimeter_is_bool: "int32_t",
  stroke_perimeter_true: "int32_t",
  dash_is_array: "int32_t",
  has_fill: "int32_t",
  fill_kind: "int32_t",
  color_ch_present: "int32_t",
  color_ch_has_constant: "int32_t",
  radius_seq: "int32_t",
  r0: "double",
  r1: "double",
  wedge_gap_raw: "double",
  kind_len: "size_t",
  name_len: "size_t",
  marker_blob_len: "size_t",
  color2_gradient_len: "size_t",
  symbol_len: "size_t",
  dash_len: "size_t",
  dash_pattern_len: "size_t",
  linecap_len: "size_t",
  step_len: "size_t",
  curve_len: "size_t",
  fill_css_len: "size_t",
  fill_space_len: "size_t",
  fill_gradient_len: "size_t",
  stroke_len: "size_t",
  line_color_len: "size_t",
  color_css_len: "size_t",
  color_mode_len: "size_t",
  color_const_len: "size_t",
  kind_off: "size_t",
  name_off: "size_t",
  marker_blob_off: "size_t",
  color2_gradient_off: "size_t",
  symbol_off: "size_t",
  dash_off: "size_t",
  dash_pattern_off: "size_t",
  linecap_off: "size_t",
  step_off: "size_t",
  curve_off: "size_t",
  fill_css_off: "size_t",
  fill_space_off: "size_t",
  fill_gradient_off: "size_t",
  stroke_off: "size_t",
  line_color_off: "size_t",
  color_css_off: "size_t",
  color_mode_off: "size_t",
  color_const_off: "size_t",
});

function i64Ptr(arr) {
  if (arr == null || arr.length === 0) return 0;
  const view = arr instanceof BigInt64Array
    ? arr
    : BigInt64Array.from(arr, (value) => BigInt(value));
  return pointer(view, "const int64_t *");
}

function xytaPalettePtrs(palette, keep) {
  if (!palette?.length) return { ptrs: 0, lens: 0 };
  const ptrBuf = Buffer.alloc(palette.length * 8);
  const lenBuf = Buffer.alloc(palette.length * 8);
  for (let index = 0; index < palette.length; index += 1) {
    const encoded = new TextEncoder().encode(String(palette[index]));
    keep.push(encoded);
    ptrBuf.writeBigUInt64LE(BigInt(u8Ptr(encoded)), index * 8);
    lenBuf.writeBigUInt64LE(BigInt(encoded.length), index * 8);
  }
  return {
    ptrs: koffi.as(ptrBuf, "const uint8_t *const *"),
    lens: koffi.as(lenBuf, "const size_t *"),
  };
}

function xytaColorChannelSide(channel, keep) {
  const mode = new TextEncoder().encode(String(channel?.mode ?? ""));
  const constant = channel?.constant == null ? new Uint8Array() : new TextEncoder().encode(String(channel.constant));
  const colormap = channel?.colormap == null || typeof channel.colormap !== "string"
    ? new Uint8Array()
    : new TextEncoder().encode(String(channel.colormap));
  const valuesF64 = channel?.values_f64 instanceof Float64Array
    ? channel.values_f64
    : Float64Array.from(channel?.values_f64 ?? []);
  const rgbaU8 = channel?.rgba_u8 instanceof Uint8Array ? channel.rgba_u8 : Uint8Array.from(channel?.rgba_u8 ?? []);
  const codesU8 = channel?.codes_u8 instanceof Uint8Array ? channel.codes_u8 : Uint8Array.from(channel?.codes_u8 ?? []);
  const codesI64 = channel?.codes_i64 instanceof BigInt64Array
    ? channel.codes_i64
    : BigInt64Array.from(channel?.codes_i64 ?? [], (value) => BigInt(value));
  const palette = (channel?.palette ?? []).map(String);
  const palettePtrs = xytaPalettePtrs(palette, keep);
  keep.push(mode, constant, colormap, rgbaU8, codesU8);
  const descBuf = Buffer.alloc(koffi.sizeof(SceneXytaColorChannelDesc));
  koffi.encode(descBuf, SceneXytaColorChannelDesc, {
    present: channel?.present ? 1 : 0,
    mode_len: BigInt(mode.length),
    constant_len: BigInt(constant.length),
    colormap_len: BigInt(colormap.length),
    has_domain: channel?.has_domain ? 1 : 0,
    domain_lo: Number(channel?.domain_lo ?? 0),
    domain_hi: Number(channel?.domain_hi ?? 0),
    values_f64_len: BigInt(valuesF64.length),
    rgba_u8_len: BigInt(rgbaU8.length),
    codes_u8_len: BigInt(codesU8.length),
    codes_i64_len: BigInt(codesI64.length),
    palette_count: BigInt(palette.length),
    n_categories: BigInt(channel?.n_categories ?? 0),
  });
  return {
    desc: koffi.as(descBuf, "const void *"),
    mode,
    constant,
    colormap,
    valuesF64,
    rgbaU8,
    codesU8,
    codesI64,
    palettePtrs,
  };
}

function xytaStyleChannelSide(channel) {
  const valuesF64 = channel?.values_f64 instanceof Float64Array
    ? channel.values_f64
    : Float64Array.from(channel?.values_f64 ?? []);
  const descBuf = Buffer.alloc(koffi.sizeof(SceneXytaStyleChannelDesc));
  koffi.encode(descBuf, SceneXytaStyleChannelDesc, {
    present: channel?.present ? 1 : 0,
    values_f64_len: BigInt(valuesF64.length),
  });
  return { desc: koffi.as(descBuf, "const void *"), valuesF64 };
}

function sliceBlob(blob, off, len) {
  return len ? blob.subarray(Number(off), Number(off) + Number(len)) : new Uint8Array();
}

/** Materialize XYTA trace observations via `xyg_scene_xyta_trace_observations_materialize` (ABI 323). */
export function sceneXytaTraceObservationsMaterialize(obs) {
  const keep = [];
  const dispatch = obs.dispatch;
  const fallback = new TextEncoder().encode(String(obs.fallback_color ?? ""));
  const styleColor = obs.style_color == null ? new Uint8Array() : new TextEncoder().encode(String(obs.style_color));
  const styleStroke = obs.style_stroke == null ? new Uint8Array() : new TextEncoder().encode(String(obs.style_stroke));
  const styleColormapMode = Number(obs.style_colormap_mode ?? 0);
  const styleColormapNamed = new TextEncoder().encode(String(obs.style_colormap_named ?? ""));
  const styleColormapStops = obs.style_colormap_stops instanceof Uint8Array
    ? obs.style_colormap_stops
    : Uint8Array.from(obs.style_colormap_stops ?? []);
  const gridValues = obs.grid_values instanceof Float64Array
    ? obs.grid_values
    : Float64Array.from(obs.grid_values ?? []);
  const rgbaU8 = obs.rgba_u8 instanceof Uint8Array ? obs.rgba_u8 : Uint8Array.from(obs.rgba_u8 ?? []);
  const rgbaGridF64 = obs.rgba_grid_f64 instanceof Float64Array
    ? obs.rgba_grid_f64
    : Float64Array.from(obs.rgba_grid_f64 ?? []);
  const xValues = obs.x_values instanceof Float64Array ? obs.x_values : Float64Array.from(obs.x_values ?? []);
  const yValues = obs.y_values instanceof Float64Array ? obs.y_values : Float64Array.from(obs.y_values ?? []);
  const styleDomain = obs.style_domain;
  const hasStyleDomain = styleDomain != null && styleDomain.length === 2;
  const inputBuf = Buffer.alloc(koffi.sizeof(SceneXytaTraceObservationsIn));
  koffi.encode(inputBuf, SceneXytaTraceObservationsIn, {
    trace_id: Number(obs.trace_id ?? 0) >>> 0,
    pack_heatmap: dispatch.packHeatmap ? 1 : 0,
    pack_hexbin_colormap: dispatch.packHexbinColormap ? 1 : 0,
    pack_hexbin_rgba: dispatch.packHexbinRgba ? 1 : 0,
    pack_ribbon_ends: dispatch.packRibbonEnds ? 1 : 0,
    pack_mesh_faces: dispatch.packMeshFaces ? 1 : 0,
    pack_scatter_paint: dispatch.packScatterPaint ? 1 : 0,
    pack_density: dispatch.packDensity ? 1 : 0,
    domain_x0: Number(obs.domain_x0 ?? Number.NaN),
    domain_x1: Number(obs.domain_x1 ?? Number.NaN),
    domain_y0: Number(obs.domain_y0 ?? Number.NaN),
    domain_y1: Number(obs.domain_y1 ?? Number.NaN),
    point_count: BigInt(obs.point_count ?? 0),
    fallback_color_len: BigInt(fallback.length),
    style_color_len: BigInt(styleColor.length),
    style_stroke_len: BigInt(styleStroke.length),
    style_stroke_width: Number(obs.style_stroke_width ?? 0),
    has_style_stroke_width: obs.has_style_stroke_width ? 1 : 0,
    style_opacity: Number(obs.style_opacity ?? Number.NaN),
    has_style_opacity: obs.has_style_opacity ? 1 : 0,
    style_fill_opacity: Number(obs.style_fill_opacity ?? Number.NaN),
    has_style_fill_opacity: obs.has_style_fill_opacity ? 1 : 0,
    style_truecolor: obs.style_truecolor ? 1 : 0,
    style_domain_lo: hasStyleDomain ? Number(styleDomain[0]) : 0,
    style_domain_hi: hasStyleDomain ? Number(styleDomain[1]) : 0,
    has_style_domain: hasStyleDomain ? 1 : 0,
    style_colormap_mode: styleColormapMode,
    style_colormap_named_len: styleColormapMode === 1 ? BigInt(styleColormapNamed.length) : 0n,
    style_colormap_stops_len: styleColormapMode === 2 ? BigInt(styleColormapStops.length) : 0n,
    grid_shape_rows: Number(obs.grid_shape_rows ?? 0),
    grid_shape_cols: Number(obs.grid_shape_cols ?? 0),
    has_grid_shape: obs.has_grid_shape ? 1 : 0,
    grid_values_len: BigInt(gridValues.length),
    rgba_u8_len: BigInt(rgbaU8.length),
    rgba_grid_f64_len: BigInt(rgbaGridF64.length),
    x_values_len: BigInt(xValues.length),
    y_values_len: BigInt(yValues.length),
  });
  const color = xytaColorChannelSide(obs.color_ch, keep);
  const stroke = xytaColorChannelSide(obs.stroke_ch, keep);
  const color2 = xytaColorChannelSide(obs.color2_ch, keep);
  const opacity = xytaStyleChannelSide(obs.opacity_ch);
  const artist = xytaStyleChannelSide(obs.artist_alpha_ch);
  const strokeWidth = xytaStyleChannelSide(obs.stroke_width_ch);
  keep.push(fallback, styleColor, styleStroke, styleColormapNamed, styleColormapStops, rgbaU8);
  const summaryBuf = Buffer.alloc(koffi.sizeof(SceneXytaTraceObservationsOut));
  const out = new Uint8Array(SCENE_XYTA_TRACE_OBSERVATIONS_MAX_BYTES);
  const outLen = new BigUint64Array(1);
  const code = Number(xySceneXytaTraceObservationsMaterialize(
    koffi.as(inputBuf, "const void *"),
    fallback.length ? u8Ptr(fallback) : 0,
    styleColor.length ? u8Ptr(styleColor) : 0,
    styleStroke.length ? u8Ptr(styleStroke) : 0,
    styleColormapMode === 1 && styleColormapNamed.length ? u8Ptr(styleColormapNamed) : 0,
    styleColormapMode === 2 && styleColormapStops.length ? u8Ptr(styleColormapStops) : 0,
    gridValues.length ? f64Ptr(gridValues) : 0,
    rgbaU8.length ? u8Ptr(rgbaU8) : 0,
    rgbaGridF64.length ? f64Ptr(rgbaGridF64) : 0,
    xValues.length ? f64Ptr(xValues) : 0,
    yValues.length ? f64Ptr(yValues) : 0,
    color.desc,
    color.mode.length ? u8Ptr(color.mode) : 0,
    color.constant.length ? u8Ptr(color.constant) : 0,
    color.colormap.length ? u8Ptr(color.colormap) : 0,
    color.valuesF64.length ? f64Ptr(color.valuesF64) : 0,
    color.rgbaU8.length ? u8Ptr(color.rgbaU8) : 0,
    color.codesU8.length ? u8Ptr(color.codesU8) : 0,
    color.codesI64.length ? i64Ptr(color.codesI64) : 0,
    color.palettePtrs.ptrs,
    color.palettePtrs.lens,
    stroke.desc,
    stroke.mode.length ? u8Ptr(stroke.mode) : 0,
    stroke.constant.length ? u8Ptr(stroke.constant) : 0,
    stroke.colormap.length ? u8Ptr(stroke.colormap) : 0,
    stroke.valuesF64.length ? f64Ptr(stroke.valuesF64) : 0,
    stroke.rgbaU8.length ? u8Ptr(stroke.rgbaU8) : 0,
    stroke.codesU8.length ? u8Ptr(stroke.codesU8) : 0,
    stroke.codesI64.length ? i64Ptr(stroke.codesI64) : 0,
    stroke.palettePtrs.ptrs,
    stroke.palettePtrs.lens,
    color2.desc,
    color2.mode.length ? u8Ptr(color2.mode) : 0,
    color2.constant.length ? u8Ptr(color2.constant) : 0,
    color2.colormap.length ? u8Ptr(color2.colormap) : 0,
    color2.valuesF64.length ? f64Ptr(color2.valuesF64) : 0,
    color2.rgbaU8.length ? u8Ptr(color2.rgbaU8) : 0,
    color2.codesU8.length ? u8Ptr(color2.codesU8) : 0,
    color2.codesI64.length ? i64Ptr(color2.codesI64) : 0,
    color2.palettePtrs.ptrs,
    color2.palettePtrs.lens,
    opacity.desc,
    opacity.valuesF64.length ? f64Ptr(opacity.valuesF64) : 0,
    artist.desc,
    artist.valuesF64.length ? f64Ptr(artist.valuesF64) : 0,
    strokeWidth.desc,
    strokeWidth.valuesF64.length ? f64Ptr(strokeWidth.valuesF64) : 0,
    koffi.as(summaryBuf, "void *"),
    u8Ptr(out),
    BigInt(out.length),
    pointer(outLen, "size_t *"),
  ));
  if (code === -2) throw new RangeError("sceneXytaTraceObservationsMaterialize output buffer too small");
  if (code !== 0) throw new RangeError("invalid sceneXytaTraceObservationsMaterialize arguments");
  const summary = koffi.decode(summaryBuf, SceneXytaTraceObservationsOut);
  const blob = out.subarray(0, Number(outLen[0]));
  const nan = Number.NaN;
  return {
    traceId: Number(summary.trace_id) >>> 0,
    packHeatmap: summary.pack_heatmap !== 0,
    packHexbinColormap: summary.pack_hexbin_colormap !== 0,
    packHexbinRgba: summary.pack_hexbin_rgba !== 0,
    packRibbonEnds: summary.pack_ribbon_ends !== 0,
    packMeshFaces: summary.pack_mesh_faces !== 0,
    packScatterPaint: summary.pack_scatter_paint !== 0,
    packDensity: summary.pack_density !== 0,
    gridShapeRows: Number(summary.grid_shape_rows),
    gridShapeCols: Number(summary.grid_shape_cols),
    hasGridShape: summary.has_grid_shape !== 0,
    hasGrid: summary.has_grid !== 0,
    hasRgba: summary.has_rgba !== 0,
    hasRgbaGrid: summary.has_rgba_grid !== 0,
    truecolor: summary.truecolor !== 0,
    hasCmapDomain: summary.has_cmap_domain !== 0,
    cmapLo: summary.has_cmap_domain !== 0 ? Number(summary.cmap_lo) : nan,
    cmapHi: summary.has_cmap_domain !== 0 ? Number(summary.cmap_hi) : nan,
    hasColorCh: summary.has_color_ch !== 0,
    hasStyleColor: summary.has_style_color !== 0,
    hasOpacity: summary.has_opacity !== 0,
    hasFillOpacity: summary.has_fill_opacity !== 0,
    opacity: summary.has_opacity !== 0 ? Number(summary.opacity) : nan,
    fillOpacity: summary.has_fill_opacity !== 0 ? Number(summary.fill_opacity) : nan,
    domainX0: Number(summary.domain_x0),
    domainX1: Number(summary.domain_x1),
    domainY0: Number(summary.domain_y0),
    domainY1: Number(summary.domain_y1),
    cmapFlags: Number(summary.cmap_flags) >>> 0,
    rows: Number(summary.rows),
    cols: Number(summary.cols),
    grid: sliceBlob(blob, summary.grid_off, summary.grid_len),
    rgba: sliceBlob(blob, summary.rgba_off, summary.rgba_len),
    rgbaGrid: sliceBlob(blob, summary.rgba_grid_off, summary.rgba_grid_len),
    x: sliceBlob(blob, summary.x_off, summary.x_len),
    y: sliceBlob(blob, summary.y_off, summary.y_len),
    meanRgba: sliceBlob(blob, summary.mean_rgba_off, summary.mean_rgba_len),
    idx: sliceBlob(blob, summary.idx_off, summary.idx_len),
    lut: sliceBlob(blob, summary.lut_off, summary.lut_len),
    cmap: sliceBlob(blob, summary.cmap_off, summary.cmap_len),
    stops: sliceBlob(blob, summary.stops_off, summary.stops_len),
    colorCh: sliceBlob(blob, summary.color_ch_off, summary.color_ch_len),
    styleColor: sliceBlob(blob, summary.style_color_off, summary.style_color_len),
  };
}

function xytcFillStopSide(fill) {
  const stops = fill?.stops;
  if (!Array.isArray(stops)) return { stopT: [], stopCss: new Uint8Array(), stopCssLens: new Uint32Array() };
  const stopT = [];
  const cssParts = [];
  const stopCssLens = [];
  try {
    for (const stop of stops) {
      if (!Array.isArray(stop) || stop.length !== 2) {
        return { stopT: [], stopCss: new Uint8Array(), stopCssLens: new Uint32Array() };
      }
      stopT.push(Number(stop[0]));
      const css = new TextEncoder().encode(String(stop[1]));
      cssParts.push(css);
      stopCssLens.push(css.length);
    }
  } catch {
    return { stopT: [], stopCss: new Uint8Array(), stopCssLens: new Uint32Array() };
  }
  const total = cssParts.reduce((sum, part) => sum + part.length, 0);
  const stopCss = new Uint8Array(total);
  let at = 0;
  for (const part of cssParts) {
    stopCss.set(part, at);
    at += part.length;
  }
  return {
    stopT,
    stopCss,
    stopCssLens: Uint32Array.from(stopCssLens),
  };
}

function xytcMarkerPathSide(markerPath) {
  if (markerPath == null || typeof markerPath !== "object") {
    return { filled: 1, values: new Float64Array(), lens: new Uint32Array(), count: 0 };
  }
  const contours = markerPath.contours;
  if (!Array.isArray(contours)) {
    return { filled: 1, values: new Float64Array(), lens: new Uint32Array(), count: 0 };
  }
  const values = [];
  const lens = [];
  try {
    for (const contour of contours) {
      if (!Array.isArray(contour)) {
        return { filled: 1, values: new Float64Array(), lens: new Uint32Array(), count: 0 };
      }
      const floats = contour.map((item) => Number(item));
      values.push(...floats);
      lens.push(floats.length);
    }
  } catch {
    return { filled: 1, values: new Float64Array(), lens: new Uint32Array(), count: 0 };
  }
  return {
    filled: markerPath.filled === false ? 0 : 1,
    values: Float64Array.from(values),
    lens: Uint32Array.from(lens),
    count: lens.length,
  };
}

/** Materialize XYTC trace observations via `xyg_scene_xytc_trace_observations_materialize` (ABI 325). */
export function sceneXyTcTraceObservationsMaterialize(obs) {
  const keep = [];
  const enc = new TextEncoder();
  const kind = enc.encode(String(obs.kind ?? ""));
  const name = obs.name == null || String(obs.name).length === 0 ? new Uint8Array() : enc.encode(String(obs.name));
  const symbol = obs.symbol_text == null ? new Uint8Array() : enc.encode(String(obs.symbol_text));
  const stroke = obs.stroke == null ? new Uint8Array() : enc.encode(String(obs.stroke));
  const lineColor = obs.line_color == null ? new Uint8Array() : enc.encode(String(obs.line_color));
  const colorCss = obs.color == null ? new Uint8Array() : enc.encode(String(obs.color));
  const dash = obs.dash_text == null ? new Uint8Array() : enc.encode(String(obs.dash_text));
  const dashValues = obs.dash_values instanceof Float64Array
    ? obs.dash_values
    : Float64Array.from(obs.dash_values ?? []);
  const fill = obs.fill;
  let fillString = new Uint8Array();
  let fillIsString = 0;
  let fillHasFullSpec = 0;
  let fillSpace = new Uint8Array();
  let fillDir = new Uint8Array();
  let fillStopT = new Float64Array();
  let fillStopCss = new Uint8Array();
  let fillStopCssLens = new Uint32Array();
  let fillDictGradient = new Uint8Array();
  let fillDictSpace = new Uint8Array();
  const hasFill = obs.has_fill ? 1 : 0;
  if (hasFill && typeof fill === "string") {
    fillIsString = 1;
    fillString = enc.encode(fill);
  } else if (hasFill && fill != null && typeof fill === "object") {
    if (fill.space != null && fill.dir != null && Array.isArray(fill.stops)) {
      fillHasFullSpec = 1;
      fillSpace = enc.encode(String(fill.space ?? ""));
      fillDir = enc.encode(String(fill.dir ?? ""));
      const packed = xytcFillStopSide(fill);
      fillStopT = Float64Array.from(packed.stopT);
      fillStopCss = packed.stopCss;
      fillStopCssLens = packed.stopCssLens;
    } else {
      fillDictGradient = enc.encode(String(fill.gradient ?? ""));
      fillDictSpace = enc.encode(String(fill.space ?? "mark"));
    }
  }
  const marker = xytcMarkerPathSide(obs.marker_path);
  const markerGlyph = obs.marker_glyph == null ? new Uint8Array() : enc.encode(String(obs.marker_glyph));
  const sourcePaint = enc.encode(String(obs.source_paint ?? "#3987e5"));
  const color2Source = obs.color2_source_const == null ? new Uint8Array() : enc.encode(String(obs.color2_source_const));
  const color2Target = obs.color2_target_const == null ? new Uint8Array() : enc.encode(String(obs.color2_target_const));
  const colorMode = obs.color_ch_mode == null ? new Uint8Array() : enc.encode(String(obs.color_ch_mode));
  const colorConst = obs.color_ch_constant == null ? new Uint8Array() : enc.encode(String(obs.color_ch_constant));
  const linecap = obs.linecap == null ? new Uint8Array() : enc.encode(String(obs.linecap));
  const step = obs.step == null ? new Uint8Array() : enc.encode(String(obs.step));
  const curve = obs.curve == null ? new Uint8Array() : enc.encode(String(obs.curve));
  const inputBuf = Buffer.alloc(koffi.sizeof(SceneXytcTraceObservationsIn));
  koffi.encode(inputBuf, SceneXytcTraceObservationsIn, {
    show_legend: obs.show_legend ? 1 : 0,
    has_name: obs.has_name ? 1 : 0,
    marker_path_present: obs.marker_path_present ? 1 : 0,
    use_density: obs.use_density ? 1 : 0,
    joined_fill: obs.joined_fill ? 1 : 0,
    symbol_is_int: Number(obs.symbol_is_int ?? 0),
    symbol_int: Number(obs.symbol_int ?? 0) & 0xffff,
    opacity: Number(obs.opacity ?? 1),
    fill_opacity: Number(obs.fill_opacity ?? 1),
    stroke_opacity: Number(obs.stroke_opacity ?? 1),
    line_opacity: Number(obs.line_opacity ?? 1),
    has_stroke: obs.has_stroke ? 1 : 0,
    has_line_color: obs.has_line_color ? 1 : 0,
    has_color: obs.has_color ? 1 : 0,
    has_size: obs.has_size ? 1 : 0,
    size: Number(obs.size ?? Number.NaN),
    has_size_ch: obs.has_size_ch ? 1 : 0,
    has_size_ch_constant: obs.has_size_ch_constant ? 1 : 0,
    size_ch_constant: Number(obs.size_ch_constant ?? Number.NaN),
    has_stroke_width: obs.has_stroke_width ? 1 : 0,
    stroke_width: Number(obs.stroke_width ?? 0),
    has_width: obs.has_width ? 1 : 0,
    width: Number(obs.width ?? 0),
    has_line_width: obs.has_line_width ? 1 : 0,
    line_width: Number(obs.line_width ?? 0),
    has_hex_dx: obs.has_hex_dx ? 1 : 0,
    hex_dx: Number(obs.hex_dx ?? Number.NaN),
    has_hex_dy: obs.has_hex_dy ? 1 : 0,
    hex_dy: Number(obs.hex_dy ?? Number.NaN),
    has_stroke_perimeter: obs.has_stroke_perimeter ? 1 : 0,
    stroke_perimeter_is_bool: Number(obs.stroke_perimeter_is_bool ?? 0),
    stroke_perimeter_true: Number(obs.stroke_perimeter_true ?? 0),
    wedge_gap_raw: Number(obs.wedge_gap_raw ?? 0),
    dash_is_array: obs.dash_is_array ? 1 : 0,
    has_fill: hasFill,
    fill_is_string: fillIsString,
    fill_has_full_spec: fillHasFullSpec,
    fill_stop_count: BigInt(fillStopT.length),
    marker_path_filled: marker.filled,
    marker_contour_count: BigInt(marker.count),
    has_color2: obs.has_color2 ? 1 : 0,
    kind_is_ribbon: obs.kind_is_ribbon ? 1 : 0,
    has_end_pair: obs.has_end_pair ? 1 : 0,
    corner_radius_seq: Number(obs.corner_radius_seq ?? 1),
    corner_radius_r0: Number(obs.corner_radius_r0 ?? 0),
    corner_radius_r1: Number(obs.corner_radius_r1 ?? 0),
    color_ch_present: obs.color_ch_present ? 1 : 0,
    color_ch_has_constant: obs.color_ch_has_constant ? 1 : 0,
    kind_len: BigInt(kind.length),
    name_len: BigInt(name.length),
    symbol_len: BigInt(symbol.length),
    stroke_len: BigInt(stroke.length),
    line_color_len: BigInt(lineColor.length),
    color_css_len: BigInt(colorCss.length),
    dash_len: BigInt(dash.length),
    dash_values_len: BigInt(dashValues.length),
    fill_string_len: BigInt(fillString.length),
    fill_space_len: BigInt(fillSpace.length),
    fill_dir_len: BigInt(fillDir.length),
    fill_stop_t_len: BigInt(fillStopT.length),
    fill_stop_css_len: BigInt(fillStopCss.length),
    fill_stop_css_lens_len: BigInt(fillStopCssLens.length),
    fill_dict_gradient_len: BigInt(fillDictGradient.length),
    fill_dict_space_len: BigInt(fillDictSpace.length),
    marker_values_len: BigInt(marker.values.length),
    marker_lens_len: BigInt(marker.lens.length),
    marker_glyph_len: BigInt(markerGlyph.length),
    source_paint_len: BigInt(sourcePaint.length),
    color2_source_const_len: BigInt(color2Source.length),
    color2_target_const_len: BigInt(color2Target.length),
    color_mode_len: BigInt(colorMode.length),
    color_const_len: BigInt(colorConst.length),
    linecap_len: BigInt(linecap.length),
    step_len: BigInt(step.length),
    curve_len: BigInt(curve.length),
  });
  keep.push(kind, name, symbol, stroke, lineColor, colorCss, dash, fillString, fillSpace, fillDir, fillStopCss, fillDictGradient, fillDictSpace, markerGlyph, sourcePaint, color2Source, color2Target, colorMode, colorConst, linecap, step, curve);
  const summaryBuf = Buffer.alloc(koffi.sizeof(SceneXytcTraceObservationsOut));
  const out = new Uint8Array(SCENE_XYTC_TRACE_OBSERVATIONS_MAX_BYTES);
  const outLen = new BigUint64Array(1);
  const code = Number(xySceneXytcTraceObservationsMaterialize(
    koffi.as(inputBuf, "const void *"),
    kind.length ? u8Ptr(kind) : 0,
    name.length ? u8Ptr(name) : 0,
    symbol.length ? u8Ptr(symbol) : 0,
    stroke.length ? u8Ptr(stroke) : 0,
    lineColor.length ? u8Ptr(lineColor) : 0,
    colorCss.length ? u8Ptr(colorCss) : 0,
    dash.length ? u8Ptr(dash) : 0,
    dashValues.length ? f64Ptr(dashValues) : 0,
    fillString.length ? u8Ptr(fillString) : 0,
    fillSpace.length ? u8Ptr(fillSpace) : 0,
    fillDir.length ? u8Ptr(fillDir) : 0,
    fillStopT.length ? f64Ptr(fillStopT) : 0,
    fillStopCss.length ? u8Ptr(fillStopCss) : 0,
    fillStopCssLens.length ? u32Ptr(fillStopCssLens) : 0,
    fillDictGradient.length ? u8Ptr(fillDictGradient) : 0,
    fillDictSpace.length ? u8Ptr(fillDictSpace) : 0,
    marker.values.length ? f64Ptr(marker.values) : 0,
    marker.lens.length ? u32Ptr(marker.lens) : 0,
    markerGlyph.length ? u8Ptr(markerGlyph) : 0,
    u8Ptr(sourcePaint),
    color2Source.length ? u8Ptr(color2Source) : 0,
    color2Target.length ? u8Ptr(color2Target) : 0,
    colorMode.length ? u8Ptr(colorMode) : 0,
    colorConst.length ? u8Ptr(colorConst) : 0,
    linecap.length ? u8Ptr(linecap) : 0,
    step.length ? u8Ptr(step) : 0,
    curve.length ? u8Ptr(curve) : 0,
    koffi.as(summaryBuf, "void *"),
    u8Ptr(out),
    BigInt(out.length),
    pointer(outLen, "size_t *"),
  ));
  if (code === -2) throw new RangeError("sceneXyTcTraceObservationsMaterialize output buffer too small");
  if (code !== 0) throw new RangeError("invalid sceneXyTcTraceObservationsMaterialize arguments");
  const summary = koffi.decode(summaryBuf, SceneXytcTraceObservationsOut);
  const blob = out.subarray(0, Number(outLen[0]));
  const f64Slice = (off, count) => {
    if (!count) return [];
    const chunk = blob.subarray(Number(off), Number(off) + count * 8);
    return [...new Float64Array(chunk.buffer, chunk.byteOffset, count)];
  };
  const style = {
    symbolIsInt: summary.symbol_is_int,
    symbolInt: summary.symbol_int,
    opacity: summary.opacity,
    fillOpacity: summary.fill_opacity,
    strokeOpacity: summary.stroke_opacity,
    lineOpacity: summary.line_opacity,
    hasStroke: summary.has_stroke,
    hasLineColor: summary.has_line_color,
    hasSize: summary.has_size,
    size: summary.size,
    hasSizeCh: summary.has_size_ch,
    hasSizeChConstant: summary.has_size_ch_constant,
    sizeChConstant: summary.size_ch_constant,
    hasStrokeWidth: summary.has_stroke_width,
    strokeWidth: summary.stroke_width,
    hasWidth: summary.has_width,
    width: summary.width,
    hasLineWidth: summary.has_line_width,
    lineWidth: summary.line_width,
    hasHexDx: summary.has_hex_dx,
    hexDx: summary.hex_dx,
    hasHexDy: summary.has_hex_dy,
    hexDy: summary.hex_dy,
    hasStrokePerimeter: summary.has_stroke_perimeter,
    strokePerimeterIsBool: summary.stroke_perimeter_is_bool,
    strokePerimeterTrue: summary.stroke_perimeter_true,
    dashIsArray: summary.dash_is_array,
    hasFill: summary.has_fill,
    fillKind: summary.fill_kind,
    colorChPresent: summary.color_ch_present,
    colorChHasConstant: summary.color_ch_has_constant,
    radiusSeq: summary.radius_seq,
    r0: summary.r0,
    r1: summary.r1,
    wedgeGapRaw: summary.wedge_gap_raw,
  };
  return {
    showLegend: summary.show_legend !== 0,
    kind: sliceBlob(blob, summary.kind_off, summary.kind_len),
    hasName: summary.has_name !== 0,
    name: sliceBlob(blob, summary.name_off, summary.name_len),
    markerPathPresent: summary.marker_path_present !== 0,
    useDensity: summary.use_density !== 0,
    joinedFill: summary.joined_fill !== 0,
    markerPacked: summary.marker_packed !== 0,
    glyphPacked: summary.glyph_packed !== 0,
    markerBlob: sliceBlob(blob, summary.marker_blob_off, summary.marker_blob_len),
    color2Class: summary.color2_class,
    color2GradientBlob: sliceBlob(blob, summary.color2_gradient_off, summary.color2_gradient_len),
    color2GradientPacked: summary.color2_gradient_packed !== 0,
    style,
    symbolB: sliceBlob(blob, summary.symbol_off, summary.symbol_len),
    dashB: sliceBlob(blob, summary.dash_off, summary.dash_len),
    dashPattern: f64Slice(summary.dash_pattern_off, Number(summary.dash_pattern_len)),
    linecapB: sliceBlob(blob, summary.linecap_off, summary.linecap_len),
    stepB: sliceBlob(blob, summary.step_off, summary.step_len),
    curveB: sliceBlob(blob, summary.curve_off, summary.curve_len),
    fillCss: sliceBlob(blob, summary.fill_css_off, summary.fill_css_len),
    fillSpace: sliceBlob(blob, summary.fill_space_off, summary.fill_space_len),
    fillGradientBlob: sliceBlob(blob, summary.fill_gradient_off, summary.fill_gradient_len),
    strokeCss: sliceBlob(blob, summary.stroke_off, summary.stroke_len),
    lineColor: sliceBlob(blob, summary.line_color_off, summary.line_color_len),
    colorCss: sliceBlob(blob, summary.color_css_off, summary.color_css_len),
    colorMode: sliceBlob(blob, summary.color_mode_off, summary.color_mode_len),
    colorConst: sliceBlob(blob, summary.color_const_off, summary.color_const_len),
  };
}

/** Pack XYPL v1 polar authoring via `xyg_scene_polar_input_pack` (ABI 322). */
export function scenePolarInputPack(kwargs) {
  const keep = [];
  const inputBuf = Buffer.alloc(koffi.sizeof(ScenePolarInputPackIn));
  koffi.encode(inputBuf, ScenePolarInputPackIn, {
    polar: kwargs.polar ? 1 : 0,
    theta_unit: Number(kwargs.theta_unit ?? 0),
    theta_direction: Number(kwargs.theta_direction ?? 0),
    n_categories: Number(kwargs.n_categories ?? 0),
    grid_shape: Number(kwargs.grid_shape ?? 0) & 0xff,
    r_scale_kind: Number(kwargs.r_scale_kind ?? 0),
    r_mask_nonpositive: kwargs.r_mask_nonpositive ? 1 : 0,
    sector_start: Number(kwargs.sector_start ?? 0),
    sector_end: Number(kwargs.sector_end ?? 0),
    r_lo: Number(kwargs.r_lo ?? 0),
    r_hi: Number(kwargs.r_hi ?? 0),
    r_origin_is_nan: kwargs.r_origin_is_nan ? 1 : 0,
    r_origin: Number(kwargs.r_origin ?? Number.NaN),
    hole: Number(kwargs.hole ?? 0),
    r_constant: Number(kwargs.r_constant ?? 1),
    theta_zero_is_label: kwargs.theta_zero_is_label ? 1 : 0,
    theta_zero_label: stringRef(kwargs.theta_zero_label ?? "", keep),
    theta_zero_numeric: Number(kwargs.theta_zero_numeric ?? 0),
  });
  const out = new Uint8Array(SCENE_POLAR_INPUT_PACK_MAX);
  const outLen = new BigUint64Array(1);
  const code = Number(xyScenePolarInputPack(
    koffi.as(inputBuf, "const void *"),
    u8Ptr(out),
    BigInt(out.length),
    pointer(outLen, "size_t *"),
  ));
  if (code === -2) throw new RangeError("scenePolarInputPack output buffer too small");
  if (code !== 0) throw new RangeError("invalid scenePolarInputPack arguments");
  return out.subarray(0, Number(outLen[0]));
}

const ADMITTED_XYAF_STYLE_KEYS = new Set([
  "color", "stroke_color", "label_color", "label_background", "label_border_color",
  "dash", "linecap", "opacity", "width", "stroke_width", "label_opacity", "label_border_width", "rotation",
]);

const XyafBulkStyleIn = koffi.struct("XygXyafBulkStyleIn", {
  color: StringRef,
  stroke_color: StringRef,
  label_color: StringRef,
  label_background: StringRef,
  label_border_color: StringRef,
  dash: StringRef,
  linecap: StringRef,
  opacity_present: "int32_t",
  opacity: "double",
  width_present: "int32_t",
  width: "double",
  stroke_width_present: "int32_t",
  stroke_width: "double",
  label_opacity_present: "int32_t",
  label_opacity: "double",
  label_border_width_present: "int32_t",
  label_border_width: "double",
  rotation_present: "int32_t",
  rotation: "double",
  extra_style_key_count: "uint32_t",
});

const XyafBulkAnnotationIn = koffi.struct("XygXyafBulkAnnotationIn", {
  kind: StringRef,
  text: StringRef,
  x_present: "int32_t",
  x: "double",
  y_present: "int32_t",
  y: "double",
  x0_present: "int32_t",
  x0: "double",
  y0_present: "int32_t",
  y0: "double",
  x1_present: "int32_t",
  x1: "double",
  y1_present: "int32_t",
  y1: "double",
  value_present: "int32_t",
  value: "double",
  start_present: "int32_t",
  start: "double",
  end_present: "int32_t",
  end: "double",
  dx_present: "int32_t",
  dx: "double",
  dy_present: "int32_t",
  dy: "double",
  size_present: "int32_t",
  size: "double",
  wrap_present: "int32_t",
  wrap: "double",
  rotation_present: "int32_t",
  rotation: "double",
  anchor_present: "int32_t",
  anchor: StringRef,
  axis_present: "int32_t",
  axis: StringRef,
  symbol_present: "int32_t",
  symbol: StringRef,
  index_override_present: "int32_t",
  index_override: "uint32_t",
  style: XyafBulkStyleIn,
});

function marshalXyafStyle(style, keep, { skipRotation = false } = {}) {
  const typography = new Set([
    "font_family", "font_size", "font_weight", "font_style",
    "fontFamily", "fontSize", "fontWeight", "fontStyle",
  ]);
  const extraKeys = [];
  const extraBlob = [];
  for (const [key, value] of Object.entries(style ?? {})) {
    if (value == null || key === "markup" || typography.has(key) || (skipRotation && key === "rotation")) continue;
    if (!ADMITTED_XYAF_STYLE_KEYS.has(key)) extraKeys.push(key);
  }
  extraKeys.sort();
  for (const key of extraKeys) {
    const encoded = new TextEncoder().encode(key);
    extraBlob.push(encoded.length & 0xff, (encoded.length >> 8) & 0xff, ...encoded);
  }
  const num = (key) => (Object.hasOwn(style, key) && style[key] != null ? [1, Number(style[key])] : [0, 0]);
  const [opacityPresent, opacity] = num("opacity");
  const [widthPresent, width] = num("width");
  const [strokeWidthPresent, strokeWidth] = num("stroke_width");
  const [labelOpacityPresent, labelOpacity] = num("label_opacity");
  const [labelBorderWidthPresent, labelBorderWidth] = num("label_border_width");
  const [rotationPresent, rotation] = num("rotation");
  return {
    style: {
      color: stringRef(typeof style.color === "string" ? style.color : null, keep),
      stroke_color: stringRef(typeof style.stroke_color === "string" ? style.stroke_color : null, keep),
      label_color: stringRef(typeof style.label_color === "string" ? style.label_color : null, keep),
      label_background: stringRef(typeof style.label_background === "string" ? style.label_background : null, keep),
      label_border_color: stringRef(typeof style.label_border_color === "string" ? style.label_border_color : null, keep),
      dash: stringRef(typeof style.dash === "string" ? style.dash : null, keep),
      linecap: stringRef(style.linecap != null ? String(style.linecap) : null, keep),
      opacity_present: opacityPresent,
      opacity,
      width_present: widthPresent,
      width,
      stroke_width_present: strokeWidthPresent,
      stroke_width: strokeWidth,
      label_opacity_present: labelOpacityPresent,
      label_opacity: labelOpacity,
      label_border_width_present: labelBorderWidthPresent,
      label_border_width: labelBorderWidth,
      rotation_present: skipRotation ? 0 : rotationPresent,
      rotation,
      extra_style_key_count: extraKeys.length,
    },
    extraBlob: new Uint8Array(extraBlob),
  };
}

function marshalXyafAnnotation(annotation, { indexOverride = null } = {}) {
  const keep = [];
  const ann = { ...annotation };
  const kind = String(ann.kind ?? "");
  const style = { ...(ann.style ?? {}) };
  if (["text", "marker"].includes(kind) && !Object.hasOwn(ann, "rotation") && style.rotation != null) {
    ann.rotation = style.rotation;
  }
  const { style: styleIn, extraBlob } = marshalXyafStyle(style, keep, { skipRotation: ["text", "marker"].includes(kind) });
  const num = (key) => (Object.hasOwn(ann, key) ? [1, Number(ann[key])] : [0, 0]);
  const text = ann.text != null && ann.text !== "" ? String(ann.text) : "";
  const row = {
    kind: stringRef(kind, keep),
    text: stringRef(text, keep),
    x_present: num("x")[0], x: num("x")[1],
    y_present: num("y")[0], y: num("y")[1],
    x0_present: num("x0")[0], x0: num("x0")[1],
    y0_present: num("y0")[0], y0: num("y0")[1],
    x1_present: num("x1")[0], x1: num("x1")[1],
    y1_present: num("y1")[0], y1: num("y1")[1],
    value_present: num("value")[0], value: num("value")[1],
    start_present: num("start")[0], start: num("start")[1],
    end_present: num("end")[0], end: num("end")[1],
    dx_present: num("dx")[0], dx: num("dx")[1],
    dy_present: num("dy")[0], dy: num("dy")[1],
    size_present: num("size")[0], size: num("size")[1],
    wrap_present: num("wrap")[0], wrap: num("wrap")[1],
    rotation_present: num("rotation")[0], rotation: num("rotation")[1],
    anchor_present: Object.hasOwn(ann, "anchor") ? 1 : 0,
    anchor: Object.hasOwn(ann, "anchor") ? stringRef(String(ann.anchor), keep) : stringRef("", keep),
    axis_present: Object.hasOwn(ann, "axis") ? 1 : 0,
    axis: Object.hasOwn(ann, "axis") ? stringRef(String(ann.axis), keep) : stringRef("", keep),
    symbol_present: Object.hasOwn(ann, "symbol") ? 1 : 0,
    symbol: Object.hasOwn(ann, "symbol") ? stringRef(String(ann.symbol), keep) : stringRef("", keep),
    index_override_present: indexOverride == null ? 0 : 1,
    index_override: indexOverride == null ? 0 : Number(indexOverride) >>> 0,
    style: styleIn,
  };
  return { row, extraBlob, keep };
}

/** Bulk-pack authored annotations via `xyg_scene_xyaf_bulk_pack` (ABI 324). */
export function sceneXyafBulkPack(annotations, { indices = null } = {}) {
  if (indices != null && indices.length !== annotations.length) {
    throw new RangeError("xyaf bulk pack indices length mismatch");
  }
  if (!annotations.length) return new Uint8Array();
  const rows = [];
  const extraParts = [];
  const keepAll = [];
  for (let pos = 0; pos < annotations.length; pos += 1) {
    const { row, extraBlob, keep } = marshalXyafAnnotation(annotations[pos], {
      indexOverride: indices == null ? null : Number(indices[pos]),
    });
    rows.push(row);
    extraParts.push(extraBlob);
    keepAll.push(...keep);
  }
  const annSize = koffi.sizeof(XyafBulkAnnotationIn);
  const annBuf = Buffer.alloc(annSize * rows.length);
  for (let i = 0; i < rows.length; i += 1) {
    koffi.encode(annBuf.subarray(i * annSize, (i + 1) * annSize), XyafBulkAnnotationIn, rows[i]);
  }
  const extraBlob = concatBytes(extraParts);
  const out = new Uint8Array(SCENE_XYAF_BULK_PACK_MAX);
  const outLen = new BigUint64Array(1);
  const errorIndex = new Uint32Array(1);
  const code = Number(xySceneXyafBulkPack(
    rows.length ? koffi.as(annBuf, "const void *") : 0,
    BigInt(annotations.length),
    extraBlob.length ? u8Ptr(extraBlob) : 0,
    BigInt(extraBlob.length),
    u8Ptr(out),
    BigInt(out.length),
    pointer(outLen, "size_t *"),
    pointer(errorIndex, "uint32_t *"),
  ));
  if (code === -2) throw new RangeError("sceneXyafBulkPack output buffer too small");
  if (code !== 0) {
    const err = new RangeError(`sceneXyafBulkPack failed: code=${code} index=${errorIndex[0]}`);
    err.code = code;
    err.index = Number(errorIndex[0]);
    throw err;
  }
  return out.subarray(0, Number(outLen[0]));
}

function concatBytes(parts) {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const out = new Uint8Array(total);
  let at = 0;
  for (const part of parts) {
    out.set(part, at);
    at += part.length;
  }
  return out;
}
