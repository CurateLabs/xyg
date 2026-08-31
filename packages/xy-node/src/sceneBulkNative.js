/** ctypes-compatible scene bulk packers (ABI 321-324). Mirrors python/xyg/_scene_bulk_native.py. */
import koffi from "koffi";
import { pointer } from "./native.js";
import { u8Ptr, f64Ptr } from "./encode.js";
import {
  xySceneChromePack,
  xySceneFigureSupportMaterialize,
  xyScenePolarInputPack,
  xySceneXyafBulkPack,
} from "./native.js";

const SCENE_XYCF_PACK_MAX = 1 << 20;
const SCENE_FIGURE_SUPPORT_PACK_MAX = 1 << 18;
const SCENE_POLAR_INPUT_PACK_MAX = 92;
const SCENE_XYAF_BULK_PACK_MAX = 1 << 22;

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
      loc: optionalStringRef(legendKw.loc, keep),
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
  const kind = String(annotation.kind ?? "");
  const style = { ...(annotation.style ?? {}) };
  const { style: styleIn, extraBlob } = marshalXyafStyle(style, keep, { skipRotation: ["text", "marker"].includes(kind) });
  const num = (key) => (Object.hasOwn(annotation, key) ? [1, Number(annotation[key])] : [0, 0]);
  const text = annotation.text != null && annotation.text !== "" ? String(annotation.text) : "";
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
    anchor_present: Object.hasOwn(annotation, "anchor") ? 1 : 0,
    anchor: Object.hasOwn(annotation, "anchor") ? stringRef(String(annotation.anchor), keep) : stringRef("", keep),
    axis_present: Object.hasOwn(annotation, "axis") ? 1 : 0,
    axis: Object.hasOwn(annotation, "axis") ? stringRef(String(annotation.axis), keep) : stringRef("", keep),
    symbol_present: Object.hasOwn(annotation, "symbol") ? 1 : 0,
    symbol: Object.hasOwn(annotation, "symbol") ? stringRef(String(annotation.symbol), keep) : stringRef("", keep),
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
