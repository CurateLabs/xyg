/** Thin Node adapter for the versioned Rust-owned canonical scene IR. */
import {
  pointer,
  xySceneAxisTicks,
  xySceneTickLabelLayout,
  xyTickWindow,
  xyTickWindowFilter,
  xyTickFormat,
  xyLegendBoxLayout,
  xyTextBlockMeasure,
  xyTextBlockRotatedExtent,
  xyYTickLabelExtent,
  xyYAxisLeftRoom,
  xyXAxisTitleRoom,
  xyXTickLabelRoom,
  xyXTickLabelEdgeRooms,
  xyCompatIsCompact,
  xyCompatDefaultPadding,
  xyCompatTitleWrapWidth,
  xyCompatTitleRoom,
  xyCompatXAxisSideRoom,
  xyCompatColorbarExtra,
  xyCompatRightYRoom,
  xyPolarLegendRoom,
  xyPolarLegendReserve,
  xyPolarLabelRoom,
  xyPolarLayout,
  xyPolarProject,
  xyRecutPolarPlot,
  xyTightLayoutSolve,
  xySceneBatchEncode,
  xySceneBrowserPainter,
  xyScenePackAnnotations,
  xyScenePackColorbar,
  xyScenePackLegend,
  xyScenePlotLayout,
  xyScenePublicExportReason,
  xySceneFigureSupportReason,
  xyScenePackProduct,
  xyScenePackProductFacts,
  xyScenePackAnnotationFacts,
  xyScenePackHeatmapFacts,
  xyScenePackSceneExtras,
  xyScenePackDensityGrid,
  xyScenePackAnnotationMarks,
  xySceneRasterCommands,
  xySceneResolveChromeStyle,
  xySceneResolveMarkStyles,
  xySceneScaleMap,
  xySceneScatterSvg,
  xySceneSupportReason,
  xySceneSvg,
  xySvgToPdf,
  xyEncodeJpeg,
  xyEncodePng,
  xyEncodeWebp,
  xySceneVersion,
  polarAbiInputPointer,
} from "./native.js";
import { asF64Array, f64Ptr, legendBestLoc, legendNormalize, shouldUseDensity, u32Ptr, u8Ptr, colormapNamedStops } from "./encode.js";
import { cssColorRgba8 } from "./color.js";

const USIZE_MAX_64 = (1n << 64n) - 1n;
const MAX_SCENE_MARKS = 2_000_000;
const MAX_SCENE_STYLES = 65_536;
const MAX_SCENE_TEXT_BYTES = 4_096;
const SYMBOL_CODES = new Map([
  "circle", "square", "diamond", "triangle", "cross", "hexagon", "pentagon", "star",
  "triangle_down", "triangle_left", "triangle_right", "x", "point", "pixel",
  "thin_diamond", "plus_line", "x_line", "horizontal_line", "vertical_line",
].map((name, code) => [name, code]));

function columnArg(column) {
  if (column == null || column.length === 0) return { ptr: 0, n: 0, keep: null };
  const arr = asF64Array(column, "trace column");
  return { ptr: f64Ptr(arr), n: arr.length, keep: arr };
}

function decodePackedRows(out, code) {
  if (code === -5) throw new RangeError("Scene v12 does not yet encode missing-data breaks or nonfinite coordinates");
  if (code === -6) throw new RangeError("Scene v12 does not support product kind");
  if (code < 0) throw new RangeError("invalid scene trace packing");
  const view = new DataView(out.buffer, out.byteOffset, Math.max(code, 0) * 56);
  const rows = { kinds: [], stableIds: [], styleRefs: [], diameter: [], symbols: [], expansion: [], x0: [], y0: [], x1: [], y1: [] };
  for (let index = 0; index < code; index += 1) {
    const at = index * 56;
    rows.kinds.push(out[at]);
    rows.symbols.push(out[at + 1]);
    rows.expansion.push(out[at + 2]);
    rows.styleRefs.push(view.getUint32(at + 4, true));
    rows.stableIds.push(view.getBigUint64(at + 8, true));
    rows.diameter.push(view.getFloat64(at + 16, true));
    rows.x0.push(view.getFloat64(at + 24, true));
    rows.y0.push(view.getFloat64(at + 32, true));
    rows.x1.push(view.getFloat64(at + 40, true));
    rows.y1.push(view.getFloat64(at + 48, true));
  }
  return rows;
}

const FACT_STROKE_PERIMETER = 1;
const FACT_CURVE_SMOOTH = 2;
const FACT_DENSITY_PLANE = 4;
const FACT_HEATMAP_PAINT = 8;
const XYHF_FAMILY_HEATMAP = 0;
const XYHF_FAMILY_DENSITY = 1;
const XYHF_HAS_RGBA = 1 << 0;
const XYHF_HAS_RGBA_GRID = 1 << 1;
const XYHF_HAS_GRID = 1 << 2;
const XYHF_HAS_ENCODED = 1 << 3;
const XYHF_HAS_MEAN_RGBA = 1 << 4;
const XYHF_HAS_NAMED_CMAP = 1 << 5;
const XYHF_HAS_STOPS = 1 << 6;
const XYHF_HAS_TRUECOLOR = 1 << 7;
const XYHF_HAS_COLOR_CH = 1 << 8;
const XYHF_HAS_STYLE_COLOR = 1 << 9;
const XYHF_HAS_OPACITY = 1 << 10;
const XYHF_HAS_FILL_OPACITY = 1 << 11;
const XYHF_HAS_DOMAIN = 1 << 12;

function packProduct({
  kind, flags = 0, stepMode = 0, symbol = 0, styleRef = 0, traceId = 0,
  diameter = 0, extra0 = 0, extra1 = 0, x = null, y = null, x0 = null, y0 = null,
  x1 = null, y1 = null, base = null,
}) {
  const args = [x, y, x0, y0, x1, y1, base].map(columnArg);
  const packedId = asU64(traceId, "stableIds value");
  const nRows = Math.max(Math.max(...args.map((column) => column.n), 1) * 2, 2);
  const out = new Uint8Array(nRows * 56);
  const encoded = new TextEncoder().encode(String(kind));
  const code = xyScenePackProduct(
    encoded.length ? u8Ptr(encoded) : 0, BigInt(encoded.length),
    flags, stepMode, symbol, styleRef, packedId,
    Number(diameter), Number(extra0), Number(extra1),
    args[0].ptr, BigInt(args[0].n),
    args[1].ptr, BigInt(args[1].n),
    args[2].ptr, BigInt(args[2].n),
    args[3].ptr, BigInt(args[3].n),
    args[4].ptr, BigInt(args[4].n),
    args[5].ptr, BigInt(args[5].n),
    args[6].ptr, BigInt(args[6].n),
    u8Ptr(out), BigInt(out.length),
  );
  if (code === -6) throw new RangeError(`Scene v12 does not support product kind ${JSON.stringify(kind)}`);
  return decodePackedRows(out, code);
}

function curveIsSmooth(style) {
  const curve = style?.curve;
  return curve != null && String(curve).trim().toLowerCase() === "smooth";
}

function packXyPk({
  kind, styleRef = 0, coords = 0, symbol = 0, authoredStep = 0, facts = 0,
  traceId = 0, diameter = 0, hexDx = 0, hexDy = 0, gridRows = 0, gridCols = 0,
}) {
  const name = new TextEncoder().encode(String(kind));
  const out = new Uint8Array(64 + name.length);
  const view = new DataView(out.buffer);
  out[0] = 88; out[1] = 89; out[2] = 80; out[3] = 75; // XYPK
  view.setUint32(4, 1, true);
  view.setUint32(8, styleRef >>> 0, true);
  out[12] = coords;
  out[13] = symbol;
  out[14] = authoredStep;
  out[15] = facts;
  view.setBigUint64(16, asU64(traceId, "stableIds value"), true);
  view.setFloat64(24, Number(diameter), true);
  view.setFloat64(32, Number(hexDx), true);
  view.setFloat64(40, Number(hexDy), true);
  view.setFloat64(48, Number(gridRows), true);
  view.setFloat64(56, Number(gridCols), true);
  out.set(name, 64);
  return out;
}

function packProductFacts({
  facts, x = null, y = null, x0 = null, y0 = null, x1 = null, y1 = null, base = null,
}) {
  const args = [x, y, x0, y0, x1, y1, base].map(columnArg);
  const nRows = Math.max(Math.max(...args.map((column) => column.n), 1) * 2, 2);
  const out = new Uint8Array(nRows * 56);
  const payload = facts instanceof Uint8Array ? facts : new Uint8Array(facts ?? []);
  const code = xyScenePackProductFacts(
    payload.length ? u8Ptr(payload) : 0, BigInt(payload.length),
    args[0].ptr, BigInt(args[0].n),
    args[1].ptr, BigInt(args[1].n),
    args[2].ptr, BigInt(args[2].n),
    args[3].ptr, BigInt(args[3].n),
    args[4].ptr, BigInt(args[4].n),
    args[5].ptr, BigInt(args[5].n),
    args[6].ptr, BigInt(args[6].n),
    u8Ptr(out), BigInt(out.length),
  );
  if (code === -6) throw new RangeError("Scene v12 does not support product kind");
  return decodePackedRows(out, code);
}

const XYAF_KIND_CODES = { text: 0, arrow: 1, callout: 2, rule: 3, band: 4, marker: 5 };
const XYAF_FACT_HAS_WRAP = 1 << 0;
const XYAF_FACT_HAS_TEXT = 1 << 1;
const XYAF_FACT_HAS_DX = 1 << 3;
const XYAF_FACT_HAS_DY = 1 << 4;
const XYAF_FACT_HAS_X = 1 << 5;
const XYAF_FACT_HAS_Y = 1 << 6;
const XYAF_FACT_HAS_X0 = 1 << 7;
const XYAF_FACT_HAS_Y0 = 1 << 8;
const XYAF_FACT_HAS_X1 = 1 << 9;
const XYAF_FACT_HAS_Y1 = 1 << 10;
const XYAF_FACT_HAS_VALUE = 1 << 11;
const XYAF_FACT_HAS_START = 1 << 12;
const XYAF_FACT_HAS_END = 1 << 13;
const XYAF_FACT_HAS_SIZE = 1 << 14;
const XYAF_FACT_HAS_AXIS = 1 << 15;
const XYAF_FACT_HAS_SYMBOL = 1 << 16;
const XYAF_FACT_HAS_ANCHOR = 1 << 17;
const XYAF_STYLE_COLOR = 1 << 0;
const XYAF_STYLE_OPACITY = 1 << 1;
const XYAF_STYLE_WIDTH = 1 << 2;
const XYAF_STYLE_DASH = 1 << 3;
const XYAF_STYLE_LINECAP = 1 << 4;
const XYAF_STYLE_STROKE_COLOR = 1 << 5;
const XYAF_STYLE_STROKE_WIDTH = 1 << 6;
const XYAF_STYLE_LABEL_COLOR = 1 << 7;
const XYAF_STYLE_LABEL_OPACITY = 1 << 8;
const XYAF_STYLE_LABEL_BACKGROUND = 1 << 9;
const XYAF_STYLE_LABEL_BORDER_COLOR = 1 << 10;
const XYAF_STYLE_LABEL_BORDER_WIDTH = 1 << 11;

function annotationAllowedStyle(kind, wrapped, labelled) {
  const allowed = new Set(["color", "opacity"]);
  if (wrapped) return new Set(["color", "opacity", "label_background", "label_border_color", "label_border_width"]);
  if (kind === "arrow") { allowed.add("width"); return allowed; }
  if (kind === "callout" || kind === "text") {
    allowed.add("label_background"); allowed.add("label_border_color"); allowed.add("label_border_width");
    if (kind === "callout") allowed.add("width");
    return allowed;
  }
  if (kind === "rule") { allowed.add("width"); allowed.add("dash"); allowed.add("linecap"); }
  else if (kind === "marker") { allowed.add("stroke_color"); allowed.add("stroke_width"); }
  if (labelled && ["rule", "band", "marker"].includes(kind)) {
    allowed.add("label_color"); allowed.add("label_opacity"); allowed.add("label_background");
    allowed.add("label_border_color"); allowed.add("label_border_width");
  }
  return allowed;
}

function packXyAf(annotation, index) {
  const kind = annotation.kind;
  const kindCode = XYAF_KIND_CODES[kind];
  if (kindCode == null) throw new RangeError(`Scene v12 annotations support rule, band, and unlabeled marker only; ${JSON.stringify(kind)} is deferred`);
  const wrapped = ["text", "callout"].includes(kind) && Object.hasOwn(annotation, "wrap");
  const labelled = annotation.text != null && annotation.text !== "";
  if (annotation.class_name != null && annotation.class_name !== "") {
    if (kind === "arrow") throw new RangeError("Scene arrows do not encode class_name");
    if (kind === "callout") throw new RangeError("Scene callouts do not encode class_name");
    if (wrapped) throw new RangeError("Scene wrapped annotations do not encode class_name");
    throw new RangeError(sceneSupportReason(1n << 2n));
  }
  if (kind === "arrow" && labelled) throw new RangeError("Scene arrows do not encode text");
  let encoded = new Uint8Array();
  if (labelled) {
    if (typeof annotation.text !== "string" || annotation.text.includes("\0") || (wrapped && annotation.text.includes("\r"))) {
      throw new RangeError(wrapped ? "Scene wrapped annotations require nonempty NUL-free LF text" : kind === "text" ? "Scene v16 text annotations require nonempty NUL-free text" : kind === "callout" ? "Scene callouts require nonempty NUL-free text" : "Scene v16 annotation labels require nonempty NUL-free text");
    }
    encoded = new TextEncoder().encode(annotation.text);
    if (encoded.length > 4096) throw new RangeError("Scene annotations are limited to 4,096 UTF-8 bytes");
  } else if (kind === "text" || kind === "callout") {
    throw new RangeError(kind === "callout" ? "Scene callouts require nonempty NUL-free text" : "Scene v16 text annotations require nonempty NUL-free text");
  }
  const style = { ...(annotation.style ?? {}) };
  const allowed = annotationAllowedStyle(kind, wrapped, labelled);
  const unsupported = Object.keys(style).filter((key) => !allowed.has(key) && style[key] != null).sort();
  if (unsupported.length) {
    if (wrapped) throw new RangeError("Scene wrapped annotations do not encode class_name, custom fonts, CSS, markup, collision, or leader style");
    if (kind === "arrow") throw new RangeError(`Scene arrow style does not encode ${JSON.stringify(unsupported)}`);
    if (kind === "callout") throw new RangeError(`Scene callout style does not encode ${JSON.stringify(unsupported)}`);
    if (kind === "text") throw new RangeError("Scene v23 text annotations support only color, opacity, label_background, and label_border_*");
    throw new RangeError(`Scene v12 ${kind} annotation style does not encode ${JSON.stringify(unsupported)}`);
  }
  const nums = new Float64Array(18);
  nums.fill(Number.NaN);
  let facts = 0;
  let styleBits = 0;
  const zeros = new Uint8Array(4);
  let color = zeros, stroke = zeros, labelColor = zeros, labelFill = zeros, labelBorder = zeros;
  if (labelled) facts |= XYAF_FACT_HAS_TEXT;
  if (wrapped) {
    facts |= XYAF_FACT_HAS_WRAP;
    nums[8] = annotationNumber(annotation, "wrap", undefined, "wrapped width");
  }
  const required = wrapped
    ? [["x", 0, XYAF_FACT_HAS_X, "wrapped x"], ["y", 1, XYAF_FACT_HAS_Y, "wrapped y"]]
    : {
      arrow: [["x0", 2, XYAF_FACT_HAS_X0, "arrow x0"], ["y0", 3, XYAF_FACT_HAS_Y0, "arrow y0"], ["x1", 4, XYAF_FACT_HAS_X1, "arrow x1"], ["y1", 5, XYAF_FACT_HAS_Y1, "arrow y1"]],
      callout: [["x", 0, XYAF_FACT_HAS_X, "callout x"], ["y", 1, XYAF_FACT_HAS_Y, "callout y"]],
      text: [["x", 0, XYAF_FACT_HAS_X, "text x"], ["y", 1, XYAF_FACT_HAS_Y, "text y"]],
      rule: [["value", 9, XYAF_FACT_HAS_VALUE, "rule value"]],
      band: [["start", 10, XYAF_FACT_HAS_START, "band start"], ["end", 11, XYAF_FACT_HAS_END, "band end"]],
      marker: [["x", 0, XYAF_FACT_HAS_X, "marker x"], ["y", 1, XYAF_FACT_HAS_Y, "marker y"]],
    }[kind];
  for (const [key, slot, flag, label] of required) {
    nums[slot] = annotationNumber(annotation, key, undefined, label);
    facts |= flag;
  }
  for (const [key, slot, flag, label] of [["dx", 6, XYAF_FACT_HAS_DX, wrapped ? "wrapped dx" : "callout dx"], ["dy", 7, XYAF_FACT_HAS_DY, wrapped ? "wrapped dy" : "callout dy"], ["size", 12, XYAF_FACT_HAS_SIZE, "marker size"]]) {
    if (Object.hasOwn(annotation, key)) {
      nums[slot] = annotationNumber(annotation, key, undefined, label);
      facts |= flag;
    }
  }
  let axisCode = 0;
  if (kind === "rule" || kind === "band") {
    if (annotation.axis !== "x" && annotation.axis !== "y") throw new RangeError(`Scene v12 ${kind} annotation axis must be 'x' or 'y'`);
    axisCode = annotation.axis === "x" ? 1 : 2;
    facts |= XYAF_FACT_HAS_AXIS;
  }
  let symbol = 0;
  if (kind === "marker") {
    symbol = annotationSymbolCode(annotation.symbol ?? "circle");
    if (Object.hasOwn(annotation, "symbol")) facts |= XYAF_FACT_HAS_SYMBOL;
    if (Object.hasOwn(annotation, "size") && (!Number.isFinite(nums[12]) || nums[12] <= 0)) throw new RangeError("Scene v12 marker annotation size must be finite and positive");
  }
  let anchor = 255;
  if (Object.hasOwn(annotation, "anchor") || kind === "callout" || wrapped) {
    const anchorCode = { start: 0, middle: 1, end: 2 }[annotation.anchor ?? "start"];
    if (anchorCode == null) throw new RangeError(wrapped ? "Scene wrapped annotation anchor must be start, middle, or end" : "Scene callout anchor must be start, middle, or end");
    anchor = anchorCode;
    facts |= XYAF_FACT_HAS_ANCHOR;
  }
  const kindLabel = wrapped ? "wrapped" : kind;
  if (Object.hasOwn(style, "opacity")) {
    nums[13] = annotationNumber(style, "opacity", undefined, `${kindLabel} opacity`);
    styleBits |= XYAF_STYLE_OPACITY;
    if (!Number.isFinite(nums[13]) || nums[13] < 0 || nums[13] > 1) throw new RangeError(kind === "arrow" ? "Scene arrow opacity must be in [0, 1] and width must be positive" : wrapped ? "Scene wrapped annotation values are invalid" : kind === "callout" ? "Scene callout opacity must be in [0, 1] and width must be positive" : `Scene v12 ${kind} annotation opacity must be finite and in [0, 1]`);
  }
  if (Object.hasOwn(style, "width")) {
    nums[14] = annotationNumber(style, "width", undefined, `${kindLabel} width`);
    styleBits |= XYAF_STYLE_WIDTH;
    if ((kind === "arrow" || kind === "callout") && (!Number.isFinite(nums[14]) || nums[14] <= 0)) throw new RangeError(kind === "arrow" ? "Scene arrow opacity must be in [0, 1] and width must be positive" : "Scene callout opacity must be in [0, 1] and width must be positive");
    if (kind === "rule" && (!Number.isFinite(nums[14]) || nums[14] <= 0)) throw new RangeError("Scene v12 rule annotation width must be finite and nonnegative");
  }
  if (Object.hasOwn(style, "stroke_width")) {
    nums[15] = annotationNumber(style, "stroke_width", undefined, `${kind} width`);
    styleBits |= XYAF_STYLE_STROKE_WIDTH;
  }
  if (Object.hasOwn(style, "label_opacity")) {
    nums[16] = annotationNumber(style, "label_opacity", undefined, `${kind} label opacity`);
    styleBits |= XYAF_STYLE_LABEL_OPACITY;
  }
  if (Object.hasOwn(style, "label_border_width")) {
    nums[17] = annotationNumber(style, "label_border_width", undefined, `${kindLabel} label border width`);
    styleBits |= XYAF_STYLE_LABEL_BORDER_WIDTH;
    if (!Number.isFinite(nums[17]) || nums[17] <= 0) throw new RangeError("Scene v23 label border width must be positive and finite");
  }
  for (const [key, bit] of [["color", XYAF_STYLE_COLOR], ["stroke_color", XYAF_STYLE_STROKE_COLOR], ["label_color", XYAF_STYLE_LABEL_COLOR], ["label_background", XYAF_STYLE_LABEL_BACKGROUND], ["label_border_color", XYAF_STYLE_LABEL_BORDER_COLOR]]) {
    if (Object.hasOwn(style, key)) {
      const packed = rgba8(annotationColor(style, key, "", `${kindLabel} ${key.replaceAll("_", " ")}`), 1, kindLabel);
      styleBits |= bit;
      if (key === "color") color = packed;
      else if (key === "stroke_color") stroke = packed;
      else if (key === "label_color") labelColor = packed;
      else if (key === "label_background") labelFill = packed;
      else labelBorder = packed;
    }
  }
  if ((style.label_border_color == null) !== (style.label_border_width == null)) throw new RangeError(wrapped ? "Scene wrapped label border requires color and width" : "Scene v23 label border requires color and width");
  let parsedDash = null;
  let parsedCap = null;
  if (kind === "rule") {
    parsedDash = parseSceneDash(style.dash);
    if (parsedDash === false) throw new RangeError("Scene v12 rule annotation dash is not a constant pattern");
    if (parsedDash) styleBits |= XYAF_STYLE_DASH;
    parsedCap = parseSceneLinecap(style.linecap ?? style.lineCap);
    if (parsedCap === false) throw new RangeError("Scene v12 rule annotation linecap is not a Scene cap");
    if (parsedCap != null) styleBits |= XYAF_STYLE_LINECAP;
  }
  const out = new Uint8Array(232 + encoded.length);
  const view = new DataView(out.buffer);
  out[0] = 88; out[1] = 89; out[2] = 65; out[3] = 70; // XYAF
  view.setUint32(4, 1, true);
  view.setUint32(8, index >>> 0, true);
  out[12] = kindCode;
  out[13] = axisCode;
  out[14] = symbol;
  out[15] = anchor;
  view.setUint32(16, facts >>> 0, true);
  view.setUint32(20, styleBits >>> 0, true);
  out[24] = parsedCap == null ? 255 : parsedCap;
  out[25] = parsedDash ? parsedDash.length : 0;
  view.setUint32(28, encoded.length, true);
  for (let i = 0; i < 18; i += 1) view.setFloat64(32 + i * 8, nums[i], true);
  out.set(color, 176);
  out.set(stroke, 180);
  out.set(labelColor, 184);
  out.set(labelFill, 188);
  out.set(labelBorder, 192);
  if (parsedDash) {
    for (let i = 0; i < parsedDash.length; i += 1) view.setFloat32(200 + i * 4, Number(parsedDash[i]), true);
  }
  out.set(encoded, 232);
  return out;
}

function packAnnotationFacts(facts, styleRefBase, xDomain, yDomain) {
  const source = facts instanceof Uint8Array ? facts : new Uint8Array(facts ?? []);
  if (!source.length) return new Uint8Array();
  const out = new Uint8Array(Math.max(65536, source.length * 4));
  const code = xyScenePackAnnotationFacts(
    u8Ptr(source),
    BigInt(source.length),
    styleRefBase >>> 0,
    Number(xDomain[0]),
    Number(xDomain[1]),
    Number(yDomain[0]),
    Number(yDomain[1]),
    u8Ptr(out),
    BigInt(out.length),
  );
  if (code === -5) throw new RangeError("Scene annotation geometry must be finite");
  if (code === -6) throw new RangeError("Scene annotations require nonempty NUL-free text");
  if (code === -7) throw new RangeError("Scene v23 label border requires label_background");
  if (code === -3) throw new RangeError("Scene annotations are limited to 128 entries");
  if (code < 0) throw new RangeError("invalid scene annotation packing");
  return out.subarray(0, code);
}

function applyXyao(payload, kinds, stableIds, styleRefs, diameter, symbols, expansionModes, x0, y0, x1, y1, styles, dashes, linecaps) {
  if (!payload.length) return new Uint8Array();
  const view = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
  if (payload[0] !== 88 || payload[1] !== 89 || payload[2] !== 65 || payload[3] !== 79 || view.getUint32(4, true) !== 1) {
    throw new RangeError("invalid scene annotation packing");
  }
  const nStyles = view.getUint32(8, true);
  const nRows = view.getUint32(12, true);
  const xyadLen = view.getUint32(16, true);
  let at = 32;
  for (let i = 0; i < nStyles; i += 1) {
    const fill = [payload[at], payload[at + 1], payload[at + 2], payload[at + 3]];
    const stroke = [payload[at + 4], payload[at + 5], payload[at + 6], payload[at + 7]];
    const width = view.getFloat64(at + 8, true);
    const dashCount = payload[at + 16];
    const cap = payload[at + 17];
    const pattern = [];
    for (let d = 0; d < dashCount; d += 1) pattern.push(view.getFloat32(at + 24 + d * 4, true));
    styles.push({ fillRgba: fill, strokeRgba: stroke, strokeWidth: width });
    dashes.push(dashCount ? pattern : null);
    linecaps.push(cap === 255 ? null : cap);
    at += 56;
  }
  const packed = payload.subarray(at, at + nRows * 56);
  if (nRows) appendPacked(kinds, stableIds, styleRefs, diameter, symbols, expansionModes, x0, y0, x1, y1, decodePackedRows(packed, nRows));
  return payload.subarray(at + nRows * 56, at + nRows * 56 + xyadLen);
}

function packAnnotationMarks(rowBytes, xDomain, yDomain) {
  const source = rowBytes instanceof Uint8Array ? rowBytes : new Uint8Array(rowBytes ?? []);
  const nIn = Math.floor(source.length / 40);
  const out = new Uint8Array(Math.max(nIn * 2, 1) * 56);
  const code = xyScenePackAnnotationMarks(
    source.length ? u8Ptr(source) : 0,
    BigInt(source.length),
    Number(xDomain[0]),
    Number(xDomain[1]),
    Number(yDomain[0]),
    Number(yDomain[1]),
    u8Ptr(out),
    BigInt(out.length),
  );
  if (code === -5) throw new RangeError("Scene v12 annotation geometry must be finite");
  if (code < 0) throw new RangeError("invalid scene annotation packing");
  const view = new DataView(out.buffer, out.byteOffset, Math.max(code, 0) * 56);
  const rows = { kinds: [], stableIds: [], styleRefs: [], diameter: [], symbols: [], expansion: [], x0: [], y0: [], x1: [], y1: [] };
  for (let index = 0; index < code; index += 1) {
    const at = index * 56;
    rows.kinds.push(out[at]);
    rows.symbols.push(out[at + 1]);
    rows.expansion.push(out[at + 2]);
    rows.styleRefs.push(view.getUint32(at + 4, true));
    rows.stableIds.push(view.getBigUint64(at + 8, true));
    rows.diameter.push(view.getFloat64(at + 16, true));
    rows.x0.push(view.getFloat64(at + 24, true));
    rows.y0.push(view.getFloat64(at + 32, true));
    rows.x1.push(view.getFloat64(at + 40, true));
    rows.y1.push(view.getFloat64(at + 48, true));
  }
  return rows;
}

function annotationMarkRow(kind, axis, symbol, styleRef, index, value0, value1, size) {
  const row = new Uint8Array(40);
  const view = new DataView(row.buffer);
  row[0] = kind;
  row[1] = axis;
  row[2] = symbol;
  view.setUint32(4, styleRef >>> 0, true);
  view.setUint32(8, index >>> 0, true);
  view.setFloat64(16, Number(value0), true);
  view.setFloat64(24, Number(value1), true);
  view.setFloat64(32, Number(size), true);
  return row;
}

function appendPacked(kinds, stableIds, styleRefs, diameter, symbols, expansionModes, x0, y0, x1, y1, packed) {
  kinds.push(...packed.kinds);
  stableIds.push(...packed.stableIds);
  styleRefs.push(...packed.styleRefs);
  diameter.push(...packed.diameter);
  symbols.push(...packed.symbols);
  expansionModes.push(...packed.expansion);
  x0.push(...packed.x0);
  y0.push(...packed.y0);
  x1.push(...packed.x1);
  y1.push(...packed.y1);
}

function sceneSymbolCode(value) {
  if (typeof value === "string") {
    const code = SYMBOL_CODES.get(value);
    if (code == null) throw new RangeError(`Scene v12 does not support scatter symbol ${JSON.stringify(value)}`);
    return code;
  }
  if (!Number.isInteger(value) || value < 0 || value >= SYMBOL_CODES.size) {
    throw new RangeError("Scene v12 scatter symbol code must be an integer from 0 through 18");
  }
  return value;
}

function annotationSymbolCode(value) {
  if (typeof value !== "string") {
    throw new RangeError("Scene v12 annotation marker symbol must be a supported string name");
  }
  return sceneSymbolCode(value);
}

function asU8Array(value, name) {
  if (value instanceof Uint8Array) return value;
  if (value == null) return new Uint8Array(0);
  try {
    return Uint8Array.from(value, (item) => Number(item));
  } catch (error) {
    throw new TypeError(`${name} must be an array-like byte sequence`, { cause: error });
  }
}

function asUnsignedArray(value, name, max, TypedArray) {
  if (value instanceof TypedArray) return value;
  let items;
  try {
    items = Array.from(value);
  } catch (error) {
    throw new TypeError(`${name} must be an array-like unsigned integer sequence`, { cause: error });
  }
  for (const item of items) {
    if (typeof item !== "number" || !Number.isInteger(item) || item < 0 || item > max) {
      throw new RangeError(`${name} values must be integers from 0 through ${max}`);
    }
  }
  return TypedArray.from(items);
}

function asU64(value, name) {
  if (typeof value === "bigint") {
    if (value < 0n || value > USIZE_MAX_64) throw new RangeError(`${name} must be an unsigned 64-bit integer`);
    return value;
  }
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new RangeError(`${name} number must be a non-negative safe integer; use BigInt above 2^53 - 1`);
  }
  return BigInt(value);
}

function asStableIds(value) {
  if (value instanceof BigUint64Array) return value;
  let items;
  try {
    items = Array.from(value);
  } catch (error) {
    throw new TypeError("stableIds must be an array-like unsigned 64-bit integer sequence", { cause: error });
  }
  const converted = items.map((item) => asU64(item, "stableIds value"));
  return BigUint64Array.from(converted);
}

function requireLength(value, length, name) {
  if (value.length !== length) {
    throw new RangeError(`${name} must have length ${length}, got ${value.length}`);
  }
}

export function sceneVersion() {
  return xySceneVersion();
}

export function axisTicks({
  kind = "linear",
  lo,
  hi,
  target = 6,
  categories,
  unit,
  constant = 1,
}) {
  let kindCode = -1;
  let aux = 0;
  if (kind === "linear") kindCode = 0;
  else if (kind === "log") kindCode = 1;
  else if (kind === "category") {
    kindCode = 2;
    const count = Array.isArray(categories) ? categories.length : Number(categories);
    if (!Number.isFinite(count) || count < 1) {
      throw new RangeError("category ticks require a positive categories length");
    }
    aux = count;
  } else if (kind === "angular") {
    kindCode = unit === "degrees" ? 3 : unit === "radians" ? 4 : -1;
    if (kindCode < 0) throw new RangeError('angular unit must be "degrees" or "radians"');
  } else if (kind === "time") {
    kindCode = 5;
  } else if (kind === "symlog") {
    kindCode = 6;
    aux = Number(constant);
  }
  if (kindCode < 0) {
    throw new RangeError("kind must be linear, log, category, angular, time, or symlog");
  }
  // Calendar time ladders can emit up to ~1000 first-of-month ticks.
  const capacity = kindCode === 5 ? 1000 : 200;
  const ticks = new Float64Array(capacity);
  const labeled = new Float64Array(capacity);
  const labeledLength = new BigUint64Array(1);
  const step = new Float64Array(1);
  const rawWritten = xySceneAxisTicks(
    kindCode, Number(lo), Number(hi), BigInt(target), Number(aux),
    pointer(ticks, "double *"), pointer(labeled, "double *"),
    pointer(labeledLength, "size_t *"), pointer(step, "double *"), BigInt(capacity),
  );
  if (rawWritten === USIZE_MAX_64) throw new RangeError("invalid canonical axis tick request");
  const written = Number(rawWritten);
  const labels = Number(labeledLength[0]);
  if (!Number.isSafeInteger(written) || written > capacity || labels > written) {
    throw new RangeError("canonical axis ticks exceeded host output limits");
  }
  return { ticks: Array.from(ticks.subarray(0, written)), labeled: Array.from(labeled.subarray(0, labels)), step: step[0] };
}

const TICK_LAYOUT_KIND = new Map([
  ["auto", 0], ["hide", 1], ["rotate", 2], ["stagger", 3],
  ["preserve", 4], ["none", 5], ["off", 6],
]);
const TICK_LAYOUT_SIDE = new Map([["bottom", 0], ["top", 1], ["left", 2], ["right", 3]]);
const TICK_LAYOUT_ANCHOR = new Map([["start", 0], ["center", 1], ["end", 2]]);

function tickLayoutEnum(value, mapping, name) {
  if (typeof value === "string") {
    const key = value.trim().toLowerCase().replaceAll("-", "_");
    if (!mapping.has(key)) {
      throw new RangeError(`${name} must be one of ${[...mapping.keys()].join(", ")}`);
    }
    return mapping.get(key);
  }
  const code = Number(value);
  if (!Number.isInteger(code)) {
    throw new RangeError(`${name} must be a string or integer code`);
  }
  return code;
}

export function tickLabelLayout({
  positions,
  labels,
  kind = "auto",
  side = "bottom",
  anchor = "center",
  isX = true,
  category = false,
  fontSize = 11,
  minGap = 8,
  explicitAngle,
} = {}) {
  const pos = asF64Array(positions ?? [], "positions");
  const texts = Array.from(labels ?? [], (label) => String(label));
  if (pos.length !== texts.length) {
    throw new RangeError("positions and labels must have the same length");
  }
  const encoder = new TextEncoder();
  const encoded = texts.map((text) => encoder.encode(text));
  const packedLen = encoded.reduce((sum, bytes) => sum + bytes.length, 0);
  const packed = new Uint8Array(packedLen);
  const lens = new Uint32Array(texts.length);
  let at = 0;
  for (const [index, bytes] of encoded.entries()) {
    lens[index] = bytes.length;
    packed.set(bytes, at);
    at += bytes.length;
  }
  const n = pos.length;
  const outIndex = new Uint32Array(n);
  const outAngle = new Float64Array(n);
  const outRow = new Uint32Array(n);
  const angle = explicitAngle == null ? Number.NaN : Number(explicitAngle);
  const flags = (isX ? 1 : 0) | (category ? 2 : 0);
  const rawWritten = xySceneTickLabelLayout(
    f64Ptr(pos),
    BigInt(n),
    u32Ptr(lens),
    packedLen ? u8Ptr(packed) : 0,
    BigInt(packedLen),
    tickLayoutEnum(kind, TICK_LAYOUT_KIND, "kind"),
    tickLayoutEnum(side, TICK_LAYOUT_SIDE, "side"),
    tickLayoutEnum(anchor, TICK_LAYOUT_ANCHOR, "anchor"),
    flags,
    Number(fontSize),
    Number(minGap),
    angle,
    n ? u32Ptr(outIndex) : 0,
    n ? f64Ptr(outAngle) : 0,
    n ? u32Ptr(outRow) : 0,
    BigInt(n),
  );
  if (rawWritten === USIZE_MAX_64) throw new RangeError("invalid tick-label layout request");
  const written = Number(rawWritten);
  if (!Number.isSafeInteger(written) || written > n) {
    throw new RangeError("tick-label layout exceeded host output limits");
  }
  return Array.from({ length: written }, (_, index) => ({
    index: outIndex[index],
    angle: outAngle[index],
    row: outRow[index],
  }));
}

function thetaUnitCode(thetaUnit) {
  if (thetaUnit == null) return 0;
  return thetaUnit === "degrees" ? 1 : 2;
}

export function tickWindow({
  rangeLo,
  rangeHi,
  thetaUnit = null,
  kind = "linear",
  nCategories = 0,
  sectorLo = Number.NaN,
  sectorHi = Number.NaN,
} = {}) {
  const outLo = new Float64Array(1);
  const outHi = new Float64Array(1);
  const written = xyTickWindow(
    Number(rangeLo),
    Number(rangeHi),
    thetaUnitCode(thetaUnit),
    kind === "category" ? 1 : 0,
    Number(nCategories) >>> 0,
    Number(sectorLo),
    Number(sectorHi),
    f64Ptr(outLo),
    f64Ptr(outHi),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid tick-window request");
  return [outLo[0], outHi[0]];
}

export function tickWindowFilter({
  values,
  lo,
  hi,
  thetaUnit = null,
  kind = "linear",
  requireFinite = false,
} = {}) {
  const arr = asF64Array(values ?? [], "values");
  const n = arr.length;
  const out = new Float64Array(n);
  const written = xyTickWindowFilter(
    n ? f64Ptr(arr) : 0,
    BigInt(n),
    Number(lo),
    Number(hi),
    thetaUnitCode(thetaUnit),
    kind === "category" ? 1 : 0,
    requireFinite ? 1 : 0,
    n ? f64Ptr(out) : 0,
    BigInt(n),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid tick-window filter request");
  const kept = Number(written);
  if (!Number.isSafeInteger(kept) || kept > n) {
    throw new RangeError("tick-window filter exceeded host output limits");
  }
  return Array.from(out.subarray(0, kept));
}

function tickFormatKind(kind) {
  if (kind === "category") return 2;
  if (kind === "time") return 1;
  return 0;
}

export function tickFormat({
  value,
  step,
  kind = "linear",
  scale = null,
  thetaUnit = null,
  format = null,
  categories = [],
} = {}) {
  const cats = Array.from(categories ?? [], (item) => String(item));
  const encoder = new TextEncoder();
  const encoded = cats.map((item) => encoder.encode(item));
  const packed = new Uint8Array(encoded.reduce((sum, item) => sum + item.length, 0));
  let packedOffset = 0;
  for (const item of encoded) {
    packed.set(item, packedOffset);
    packedOffset += item.length;
  }
  const lens = new Uint32Array(encoded.map((item) => item.length));
  const formatBytes = format == null ? new Uint8Array() : encoder.encode(String(format));
  let out = new Uint8Array(256);
  let written = xyTickFormat(
    Number(value),
    Number(step),
    tickFormatKind(kind),
    scale === "log" ? 1 : 0,
    thetaUnitCode(thetaUnit),
    formatBytes.length ? u8Ptr(formatBytes) : 0,
    BigInt(formatBytes.length),
    BigInt(cats.length),
    cats.length ? u32Ptr(lens) : 0,
    packed.length ? u8Ptr(packed) : 0,
    BigInt(packed.length),
    u8Ptr(out),
    BigInt(out.length),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid tick-format request");
  let size = Number(written);
  if (!Number.isSafeInteger(size)) throw new RangeError("tick-format exceeded host output limits");
  if (size > out.length) {
    out = new Uint8Array(size);
    written = xyTickFormat(
      Number(value),
      Number(step),
      tickFormatKind(kind),
      scale === "log" ? 1 : 0,
      thetaUnitCode(thetaUnit),
      formatBytes.length ? u8Ptr(formatBytes) : 0,
      BigInt(formatBytes.length),
      BigInt(cats.length),
      cats.length ? u32Ptr(lens) : 0,
      packed.length ? u8Ptr(packed) : 0,
      BigInt(packed.length),
      u8Ptr(out),
      BigInt(out.length),
    );
    if (written === USIZE_MAX_64) throw new RangeError("invalid tick-format request");
    size = Number(written);
    if (!Number.isSafeInteger(size) || size > out.length) {
      throw new RangeError("tick-format exceeded host output limits");
    }
  }
  return new TextDecoder().decode(out.subarray(0, size));
}

export function legendBoxLayout({
  plot,
  names = [],
  title = null,
  loc = "upper right",
  fontSize = 11,
  handleLength,
  handleTextPad,
  handleHeight,
  ncols = 1,
  paddingEm = 0.4,
  rowGapEm = 0.5,
  anchor,
  borderAxesPad = 0,
} = {}) {
  if (plot == null || typeof plot !== "object") {
    throw new TypeError("plot must be an object with x, y, w, and h");
  }
  const texts = Array.from(names ?? [], (name) => String(name));
  const encoder = new TextEncoder();
  const encoded = texts.map((text) => encoder.encode(text));
  const packedLen = encoded.reduce((sum, bytes) => sum + bytes.length, 0);
  const packed = new Uint8Array(packedLen);
  const lens = new Uint32Array(texts.length);
  let at = 0;
  for (const [index, bytes] of encoded.entries()) {
    lens[index] = bytes.length;
    packed.set(bytes, at);
    at += bytes.length;
  }
  const titleBytes = encoder.encode(title == null ? "" : String(title));
  const locBytes = encoder.encode(loc == null || loc === "" ? "upper right" : String(loc));
  const n = texts.length;
  const colCap = Math.max(n, 1);
  const metrics = new Float64Array(17);
  const widths = new Float64Array(colCap);
  const offsets = new Float64Array(colCap);
  const nameLens = new Uint32Array(colCap);
  const namesCap = packedLen + 3 * n;
  const namesOut = new Uint8Array(Math.max(namesCap, 1));
  const titleCap = Math.max(titleBytes.length + 8, 1);
  const titleOut = new Uint8Array(titleCap);
  const titleLen = new BigUint64Array(1);
  let anchorArr = null;
  let anchorLen = 0;
  if (anchor != null) {
    const vals = Array.from(anchor, (value) => Number(value));
    if (vals.length !== 2 && vals.length !== 4) {
      throw new RangeError("legend anchor must have length 2 or 4");
    }
    anchorArr = Float64Array.from(vals);
    anchorLen = vals.length;
  }
  const nan = Number.NaN;
  const rawWritten = xyLegendBoxLayout(
    Number(plot.x),
    Number(plot.y),
    Number(plot.w),
    Number(plot.h),
    n ? u32Ptr(lens) : 0,
    packedLen ? u8Ptr(packed) : 0,
    BigInt(packedLen),
    BigInt(n),
    titleBytes.length ? u8Ptr(titleBytes) : 0,
    BigInt(titleBytes.length),
    locBytes.length ? u8Ptr(locBytes) : 0,
    BigInt(locBytes.length),
    Number(fontSize),
    handleLength == null ? nan : Number(handleLength),
    handleTextPad == null ? nan : Number(handleTextPad),
    handleHeight == null ? nan : Number(handleHeight),
    Math.max(1, Number(ncols) | 0),
    Number(paddingEm),
    Number(rowGapEm),
    anchorArr ? f64Ptr(anchorArr) : 0,
    BigInt(anchorLen),
    Number(borderAxesPad),
    f64Ptr(metrics),
    f64Ptr(widths),
    f64Ptr(offsets),
    BigInt(colCap),
    u32Ptr(nameLens),
    u8Ptr(namesOut),
    BigInt(namesOut.length),
    u8Ptr(titleOut),
    BigInt(titleOut.length),
    pointer(titleLen, "size_t *"),
  );
  if (rawWritten === USIZE_MAX_64) throw new RangeError("invalid legend box layout request");
  const visible = Number(rawWritten);
  if (!Number.isSafeInteger(visible) || visible < 0) {
    throw new RangeError("legend box layout exceeded host output limits");
  }
  const decoder = new TextDecoder();
  const outNames = [];
  let nameAt = 0;
  for (let index = 0; index < visible; index += 1) {
    const length = nameLens[index];
    outNames.push(decoder.decode(namesOut.subarray(nameAt, nameAt + length)));
    nameAt += length;
  }
  const titleText = decoder.decode(titleOut.subarray(0, Number(titleLen[0])));
  const ncolsOut = metrics[9] | 0;
  return {
    pad: metrics[0],
    handle: metrics[1],
    gap: metrics[2],
    columnGap: metrics[3],
    rowGap: metrics[4],
    fontSize: metrics[5],
    textH: metrics[6],
    lineH: metrics[7],
    swatchH: metrics[8],
    ncols: ncolsOut,
    title: titleText || null,
    titleH: metrics[10],
    cellW: metrics[11],
    columnWidths: Array.from(widths.subarray(0, ncolsOut)),
    columnOffsets: Array.from(offsets.subarray(0, ncolsOut)),
    boxW: metrics[12],
    boxH: metrics[13],
    x: metrics[14],
    y: metrics[15],
    visibleCount: visible,
    names: outNames,
  };
}

function packUtf8Strings(values) {
  const encoder = new TextEncoder();
  const encoded = Array.from(values ?? [], (value) => encoder.encode(String(value)));
  const packedLen = encoded.reduce((sum, bytes) => sum + bytes.length, 0);
  const packed = new Uint8Array(packedLen);
  const lens = new Uint32Array(encoded.length);
  let at = 0;
  for (const [index, bytes] of encoded.entries()) {
    lens[index] = bytes.length;
    packed.set(bytes, at);
    at += bytes.length;
  }
  return { lens, packed, n: encoded.length };
}

function unpackUtf8Strings(lens, packed, count) {
  const decoder = new TextDecoder();
  const out = [];
  let at = 0;
  for (let index = 0; index < count; index += 1) {
    const length = lens[index];
    out.push(decoder.decode(packed.subarray(at, at + length)));
    at += length;
  }
  return out;
}

const ANCHOR_CODES = { start: 0, center: 1, end: 2 };

export function textBlockMeasure(text, fontSize, lineHeight = 1.2, maxWidth = null) {
  const encoder = new TextEncoder();
  const textBytes = encoder.encode(String(text ?? ""));
  let lineCap = Math.max(textBytes.length + 8, 8);
  let packedCap = Math.max(textBytes.length + 8, 8);
  const metrics = new Float64Array(6);
  let written = USIZE_MAX_64;
  let lineLens = new Uint32Array(lineCap);
  let packed = new Uint8Array(packedCap);
  for (let attempt = 0; attempt < 4; attempt += 1) {
    lineLens = new Uint32Array(lineCap);
    packed = new Uint8Array(packedCap);
    written = xyTextBlockMeasure(
      textBytes.length ? u8Ptr(textBytes) : 0,
      BigInt(textBytes.length),
      Number(fontSize),
      Number(lineHeight),
      maxWidth == null ? Number.NaN : Number(maxWidth),
      f64Ptr(metrics),
      u32Ptr(lineLens),
      BigInt(lineCap),
      u8Ptr(packed),
      BigInt(packedCap),
    );
    if (written !== USIZE_MAX_64) break;
    lineCap *= 4;
    packedCap *= 4;
  }
  if (written === USIZE_MAX_64) throw new RangeError("invalid text-block measure request");
  const n = Number(written);
  if (!Number.isSafeInteger(n) || n < 0) {
    throw new RangeError("text-block measure exceeded host output limits");
  }
  return {
    lines: unpackUtf8Strings(lineLens, packed, n),
    width: metrics[0],
    height: metrics[1],
    lineStep: metrics[2],
    ascent: metrics[3],
    descent: metrics[4],
    lineCount: n,
  };
}

export function textBlockRotatedExtent(width, height, angleDegrees) {
  const outX = new Float64Array(1);
  const outY = new Float64Array(1);
  const written = xyTextBlockRotatedExtent(
    Number(width),
    Number(height),
    Number(angleDegrees),
    f64Ptr(outX),
    f64Ptr(outY),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid text-block rotation request");
  return [outX[0], outY[0]];
}

export function yTickLabelExtent(labels, fontSize, angle) {
  const { lens, packed, n } = packUtf8Strings(labels);
  const out = new Float64Array(1);
  const written = xyYTickLabelExtent(
    n ? u32Ptr(lens) : 0,
    packed.length ? u8Ptr(packed) : 0,
    BigInt(packed.length),
    BigInt(n),
    Number(fontSize),
    Number(angle),
    f64Ptr(out),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid y tick-label extent request");
  return out[0];
}

export function yAxisLeftRoom(tickOffset, tickRoom, title, titleFontSize, titleGap) {
  const titleBytes = new TextEncoder().encode(title == null ? "" : String(title));
  const out = new Float64Array(1);
  const written = xyYAxisLeftRoom(
    Number(tickOffset),
    Number(tickRoom),
    titleBytes.length ? u8Ptr(titleBytes) : 0,
    BigInt(titleBytes.length),
    Number(titleFontSize),
    Number(titleGap),
    f64Ptr(out),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid y-axis left-room request");
  return out[0];
}

export function xAxisTitleRoom(title, fontSize, offset, top) {
  const titleBytes = new TextEncoder().encode(title == null ? "" : String(title));
  const out = new Float64Array(1);
  const written = xyXAxisTitleRoom(
    titleBytes.length ? u8Ptr(titleBytes) : 0,
    BigInt(titleBytes.length),
    Number(fontSize),
    Number(offset),
    top ? 1 : 0,
    f64Ptr(out),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid x-axis title-room request");
  return out[0];
}

export function xTickLabelRoom(labels, angles, rows, fontSize, labelOffset, titleRoom) {
  const texts = Array.from(labels ?? [], (label) => String(label));
  const n = texts.length;
  if (n !== (angles?.length ?? 0) || n !== (rows?.length ?? 0)) {
    throw new RangeError("x tick-label room arrays must have equal length");
  }
  const { lens, packed } = packUtf8Strings(texts);
  const angleArr = Float64Array.from(angles ?? [], (angle) => Number(angle));
  const rowArr = Uint32Array.from(rows ?? [], (row) => Number(row) >>> 0);
  const out = new Float64Array(1);
  const written = xyXTickLabelRoom(
    n ? u32Ptr(lens) : 0,
    packed.length ? u8Ptr(packed) : 0,
    BigInt(packed.length),
    BigInt(n),
    n ? f64Ptr(angleArr) : 0,
    n ? u32Ptr(rowArr) : 0,
    Number(fontSize),
    Number(labelOffset),
    Number(titleRoom),
    f64Ptr(out),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid x tick-label room request");
  return out[0];
}

export function xTickLabelEdgeRooms(plotW, positions, labels, angles, anchors, fontSize) {
  const texts = Array.from(labels ?? [], (label) => String(label));
  const n = texts.length;
  if (n !== (positions?.length ?? 0) || n !== (angles?.length ?? 0) || n !== (anchors?.length ?? 0)) {
    throw new RangeError("x tick-label edge-room arrays must have equal length");
  }
  const { lens, packed } = packUtf8Strings(texts);
  const posArr = Float64Array.from(positions ?? [], (pos) => Number(pos));
  const angleArr = Float64Array.from(angles ?? [], (angle) => Number(angle));
  const anchorArr = new Uint32Array(n);
  for (let index = 0; index < n; index += 1) {
    const code = ANCHOR_CODES[String(anchors[index])];
    if (code === undefined) throw new RangeError("anchor must be start, center, or end");
    anchorArr[index] = code;
  }
  const outLeft = new Float64Array(1);
  const outRight = new Float64Array(1);
  const written = xyXTickLabelEdgeRooms(
    Number(plotW),
    n ? f64Ptr(posArr) : 0,
    BigInt(n),
    n ? u32Ptr(lens) : 0,
    packed.length ? u8Ptr(packed) : 0,
    BigInt(packed.length),
    n ? f64Ptr(angleArr) : 0,
    n ? u32Ptr(anchorArr) : 0,
    Number(fontSize),
    f64Ptr(outLeft),
    f64Ptr(outRight),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid x tick-label edge-room request");
  return [outLeft[0], outRight[0]];
}

const COLORBAR_KINDS = {
  none: 0,
  axes_horizontal: 1,
  axes_vertical: 2,
  figure_horizontal: 3,
  figure_vertical: 4,
};
const POLAR_LEGEND_SIDES = { 0: "", 1: "left", 2: "right", 3: "bottom" };
const POLAR_LEGEND_SIDE_CODES = { "": 0, left: 1, right: 2, bottom: 3 };

export function compatIsCompact(width) {
  const status = xyCompatIsCompact(Number(width));
  if (status === 1) return true;
  if (status === 0) return false;
  throw new RangeError("invalid compact-width request");
}

export function compatDefaultPadding(compact) {
  const out = new Float64Array(4);
  const written = xyCompatDefaultPadding(compact ? 1 : 0, f64Ptr(out));
  if (written === USIZE_MAX_64) throw new RangeError("invalid default-padding request");
  return [out[0], out[1], out[2], out[3]];
}

export function compatTitleWrapWidth(width, left, right) {
  const out = new Float64Array(1);
  const written = xyCompatTitleWrapWidth(Number(width), Number(left), Number(right), f64Ptr(out));
  if (written === USIZE_MAX_64) throw new RangeError("invalid title-wrap-width request");
  return out[0];
}

export function compatTitleRoom(compact, blockHeight, pad, automaticY, y) {
  const out = new Float64Array(1);
  const written = xyCompatTitleRoom(
    compact ? 1 : 0,
    Number(blockHeight),
    Number(pad),
    automaticY ? 1 : 0,
    Number(y),
    f64Ptr(out),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid title-room request");
  return out[0];
}

export function compatXAxisSideRoom(compact, top, measured) {
  const outRoom = new Float64Array(1);
  const outMeasured = new Float64Array(1);
  const written = xyCompatXAxisSideRoom(
    compact ? 1 : 0,
    top ? 1 : 0,
    Number(measured),
    f64Ptr(outRoom),
    f64Ptr(outMeasured),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid x-axis side-room request");
  return [outRoom[0], outMeasured[0]];
}

export function compatColorbarExtra(kind, hasLabel, padZero) {
  const code = COLORBAR_KINDS[kind];
  if (code === undefined) throw new RangeError("unknown colorbar layout kind");
  const outRight = new Float64Array(1);
  const outBottom = new Float64Array(1);
  const written = xyCompatColorbarExtra(
    code,
    hasLabel ? 1 : 0,
    padZero ? 1 : 0,
    f64Ptr(outRight),
    f64Ptr(outBottom),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid colorbar-extra request");
  return [outRight[0], outBottom[0]];
}

export function compatRightYRoom(compact) {
  const out = new Float64Array(1);
  const written = xyCompatRightYRoom(compact ? 1 : 0, f64Ptr(out));
  if (written === USIZE_MAX_64) throw new RangeError("invalid right-y-room request");
  return out[0];
}

export const POLAR_METRICS_LEN = 23;

const THETA_ZERO = {
  E: 0,
  N: Math.PI / 2,
  W: Math.PI,
  S: -Math.PI / 2,
};

function polarThetaUnit(unit = "radians") {
  return unit === "degrees" ? 1 : 0;
}

function polarThetaDirection(direction = "counterclockwise") {
  return direction === "clockwise" ? 1 : 0;
}

function polarThetaZero(zero = "E") {
  if (typeof zero === "string") return THETA_ZERO[zero] ?? 0;
  return Number(zero);
}

function polarRScale(axis = {}) {
  const scale = axis.scale ?? "";
  const kind = axis.kind ?? "linear";
  let code = 0;
  if (scale === "log" || kind === "log") code = 1;
  else if (scale === "symlog") code = 2;
  return {
    kind: code,
    constant: Number(axis.constant ?? 1),
    maskNonpositive: (axis.nonpositive ?? "clip") === "mask",
  };
}

export function packPolarSceneInput(figure) {
  if ((figure.coords ?? "cartesian") !== "polar") return new Uint8Array();
  const thetaAxis = figure.xAxis ?? figure.x_axis ?? figure.axis_options?.x ?? {};
  const rAxis = figure.yAxis ?? figure.y_axis ?? figure.axis_options?.y ?? {};
  const unit = thetaAxis.theta_unit ?? thetaAxis.thetaUnit ?? "radians";
  const turn = unit === "degrees" ? 360 : Math.PI * 2;
  const sector = thetaAxis.sector ?? [0, turn];
  const categories = thetaAxis.categories ?? [];
  const range = typeof figure._range === "function" ? figure._range("y") : (rAxis.range ?? [0, 1]);
  const [rLo, rHi] = range;
  const origin = rAxis.r_origin ?? rAxis.rOrigin;
  const scale = polarRScale(rAxis);
  const grid = thetaAxis.grid_shape ?? thetaAxis.gridShape ?? "circular";
  const out = new Uint8Array(92);
  const view = new DataView(out.buffer);
  out.set(encodeUtf8("XYPL").slice(0, 4), 0);
  view.setUint32(4, 1, true);
  view.setUint32(8, polarThetaUnit(unit), true);
  view.setUint32(12, polarThetaDirection(thetaAxis.theta_direction ?? thetaAxis.thetaDirection), true);
  view.setUint32(16, categories.length, true);
  view.setUint32(20, scale.kind, true);
  out[24] = grid === "linear" ? 1 : 0;
  out[25] = scale.maskNonpositive ? 1 : 0;
  view.setUint16(26, 0, true);
  view.setFloat64(28, polarThetaZero(thetaAxis.theta_zero ?? thetaAxis.thetaZero ?? "E"), true);
  view.setFloat64(36, Number(sector[0]), true);
  view.setFloat64(44, Number(sector[1]), true);
  view.setFloat64(52, Number(rLo), true);
  view.setFloat64(60, Number(rHi), true);
  view.setFloat64(68, origin == null ? Number.NaN : Number(origin), true);
  view.setFloat64(76, Number(rAxis.hole ?? 0), true);
  view.setFloat64(84, scale.constant, true);
  return out;
}

function encodeUtf8Magic(text) {
  return encodeUtf8(text).slice(0, 4);
}

function packXyHf({
  family, flags, stableId, rows, cols, lo, hi, opacity, fillOpacity, remainder,
}) {
  const extra = remainder ?? new Uint8Array();
  const out = new Uint8Array(64 + extra.length);
  const view = new DataView(out.buffer);
  out.set(encodeUtf8Magic("XYHF"), 0);
  view.setUint32(4, 1, true);
  view.setBigUint64(8, BigInt(stableId), true);
  view.setUint32(16, rows >>> 0, true);
  view.setUint32(20, cols >>> 0, true);
  view.setUint32(24, flags >>> 0, true);
  out[28] = family & 0xff;
  view.setFloat64(32, Number(lo), true);
  view.setFloat64(40, Number(hi), true);
  view.setFloat64(48, Number(opacity), true);
  view.setFloat64(56, Number(fillOpacity), true);
  out.set(extra, 64);
  return out;
}

function packXyHfPrefixed(payload) {
  const body = payload instanceof Uint8Array ? payload : new Uint8Array(payload ?? []);
  const out = new Uint8Array(4 + body.length);
  new DataView(out.buffer).setUint32(0, body.length, true);
  out.set(body, 4);
  return out;
}

function packF64Le(values) {
  const out = new Uint8Array(values.length * 8);
  const view = new DataView(out.buffer);
  for (let index = 0; index < values.length; index += 1) {
    view.setFloat64(index * 8, Number(values[index]), true);
  }
  return out;
}

function packHeatmapFacts(facts) {
  const source = facts instanceof Uint8Array ? facts : new Uint8Array(facts ?? []);
  if (!source.length) return new Uint8Array();
  const out = new Uint8Array(Math.max(256, source.length + 64));
  const code = xyScenePackHeatmapFacts(
    u8Ptr(source),
    BigInt(source.length),
    u8Ptr(out),
    BigInt(out.length),
  );
  if (code === -5) throw new RangeError("Scene heatmap or density plane shape is invalid");
  if (code === -6) throw new RangeError("Scene heatmap colormap requires RGB stops");
  if (code < 0) throw new RangeError("invalid scene heatmap packing");
  return out.subarray(0, code);
}

function heatmapPaintPlane(trace, rows, cols, stableId) {
  const style = trace.style ?? {};
  const packed = trace.rgba;
  const planes = trace.rgba_grid;
  const stops = style.colormapStops ?? trace.colormapStops;
  const colormap = style.colormap ?? trace.colormap;
  const grid = trace.grid;
  if (grid == null) throw new RangeError("heatmap Scene v12 compilation requires a scalar grid");
  let flags = XYHF_HAS_GRID;
  const parts = [packF64Le(grid)];
  if (packed != null) {
    flags |= XYHF_HAS_RGBA;
    const raw = packed instanceof Uint8Array
      ? packed
      : packed.rgba instanceof Uint8Array
        ? packed.rgba
        : Uint8Array.from(packed);
    if (raw.length !== rows * cols * 4) {
      throw new RangeError("Scene heatmap RGBA plane must match rows x cols");
    }
    parts.unshift(raw);
  }
  if (planes != null) {
    if (planes.length !== 4) {
      throw new RangeError("Scene heatmap truecolor requires four RGBA planes");
    }
    flags |= XYHF_HAS_RGBA_GRID;
    const interleaved = new Float64Array(rows * cols * 4);
    for (let row = 0; row < rows; row += 1) {
      for (let col = 0; col < cols; col += 1) {
        const index = (row * cols + col) * 4;
        for (let channel = 0; channel < 4; channel += 1) {
          interleaved[index + channel] = Number(planes[channel][row * cols + col] ?? planes[channel][row]?.[col]);
        }
      }
    }
    const rgbaOffset = packed != null ? 1 : 0;
    parts.splice(rgbaOffset, 0, new Uint8Array(interleaved.buffer));
  }
  if (typeof colormap === "string") {
    flags |= XYHF_HAS_NAMED_CMAP;
    parts.push(packXyHfPrefixed(new TextEncoder().encode(colormap)));
  } else if (colormap != null || stops != null) {
    flags |= XYHF_HAS_STOPS;
    const stopBytes = stops == null
      ? Uint8Array.from(colormap.flat ? colormap.flat() : colormap)
      : Uint8Array.from(stops);
    if (stopBytes.length < 3 || stopBytes.length % 3 !== 0) {
      throw new RangeError("Scene heatmap colormap requires RGB stops");
    }
    parts.push(packXyHfPrefixed(stopBytes));
  }
  if (style.truecolor) flags |= XYHF_HAS_TRUECOLOR;
  const domain = style.domain;
  const lo = domain == null || domain.length !== 2 ? Number.NaN : Number(domain[0]);
  const hi = domain == null || domain.length !== 2 ? Number.NaN : Number(domain[1]);
  if (domain != null && domain.length === 2) flags |= XYHF_HAS_DOMAIN;
  return packHeatmapFacts(packXyHf({
    family: XYHF_FAMILY_HEATMAP,
    flags,
    stableId,
    rows,
    cols,
    lo,
    hi,
    opacity: Number.NaN,
    fillOpacity: Number.NaN,
    remainder: concatBytes(parts),
  }));
}

function densityPaintPlane(trace, encoded, rows, cols, maximum, stableId, meanRgba = null) {
  const style = trace.style ?? {};
  const encodedBytes = encoded instanceof Uint8Array ? encoded : Uint8Array.from(encoded);
  if (encodedBytes.length !== rows * cols) {
    throw new RangeError("Scene density grid must match DENSITY_GRID");
  }
  let flags = XYHF_HAS_ENCODED;
  const parts = [encodedBytes];
  if (meanRgba != null) {
    const rgbaBytes = meanRgba instanceof Uint8Array ? meanRgba : Uint8Array.from(meanRgba);
    if (rgbaBytes.length !== rows * cols * 4) {
      throw new RangeError("Scene mean-color plane must match DENSITY_GRID");
    }
    flags |= XYHF_HAS_MEAN_RGBA;
    parts.push(rgbaBytes);
  }
  const colormap = style.colormap ?? trace.colormap;
  const stops = style.colormapStops ?? trace.colormapStops;
  if (typeof colormap === "string") {
    flags |= XYHF_HAS_NAMED_CMAP;
    parts.push(packXyHfPrefixed(new TextEncoder().encode(colormap)));
  } else if (colormap != null || stops != null) {
    flags |= XYHF_HAS_STOPS;
    const stopBytes = stops == null
      ? Uint8Array.from(colormap.flat ? colormap.flat() : colormap)
      : Uint8Array.from(stops);
    if (stopBytes.length < 3 || stopBytes.length % 3 !== 0) {
      throw new RangeError("Scene density colormap requires RGB stops");
    }
    parts.push(packXyHfPrefixed(stopBytes));
  }
  const channel = trace.color_ch ?? trace.colorChannel;
  if (channel != null && channel.mode === "constant" && channel.constant != null) {
    flags |= XYHF_HAS_COLOR_CH;
    parts.push(packXyHfPrefixed(new TextEncoder().encode(String(channel.constant))));
  }
  if (style.color != null) {
    flags |= XYHF_HAS_STYLE_COLOR;
    parts.push(packXyHfPrefixed(new TextEncoder().encode(String(style.color))));
  }
  let opacity = Number.NaN;
  let fillOpacity = Number.NaN;
  if (Object.hasOwn(style, "opacity")) {
    flags |= XYHF_HAS_OPACITY;
    opacity = Number(style.opacity);
  }
  if (Object.hasOwn(style, "fill_opacity") || Object.hasOwn(style, "fillOpacity")) {
    flags |= XYHF_HAS_FILL_OPACITY;
    fillOpacity = Number(style.fill_opacity ?? style.fillOpacity);
  }
  return packHeatmapFacts(packXyHf({
    family: XYHF_FAMILY_DENSITY,
    flags,
    stableId,
    rows,
    cols,
    lo: Number(maximum),
    hi: Number.NaN,
    opacity,
    fillOpacity,
    remainder: concatBytes(parts),
  }));
}

function packDensityGrid(x, y, x0, x1, y0, y1, source = null) {
  const xa = asF64Array(x, "x");
  const ya = asF64Array(y, "y");
  if (xa.length !== ya.length) throw new RangeError("Scene density columns must have equal length");
  if (!xa.length) return null;
  let idxPtr = 0;
  let rgbaPtr = 0;
  let lutPtr = 0;
  let lutLen = 0n;
  if (source?.rgba != null) {
    const rgba = source.rgba instanceof Uint8Array ? source.rgba : Uint8Array.from(source.rgba);
    if (rgba.length !== xa.length * 4) {
      throw new RangeError("Scene density mean-color rgba length must be 4 * n");
    }
    rgbaPtr = u8Ptr(rgba);
  } else if (source?.idx != null && source?.lut != null) {
    const idx = source.idx instanceof Uint8Array ? source.idx : Uint8Array.from(source.idx);
    const lut = source.lut instanceof Uint8Array ? source.lut : Uint8Array.from(source.lut);
    if (idx.length !== xa.length) throw new RangeError("Scene density mean-color idx length must match n");
    if (lut.length < 4 || lut.length % 4) throw new RangeError("Scene density mean-color lut must be RGBA8");
    idxPtr = u8Ptr(idx);
    lutPtr = u8Ptr(lut);
    lutLen = BigInt(lut.length / 4);
  }
  const out = new Uint8Array(32 + 512 * 384 * 5);
  const code = xyScenePackDensityGrid(
    f64Ptr(xa),
    f64Ptr(ya),
    BigInt(xa.length),
    Number(x0),
    Number(x1),
    Number(y0),
    Number(y1),
    idxPtr,
    rgbaPtr,
    lutPtr,
    lutLen,
    u8Ptr(out),
    BigInt(out.length),
  );
  if (code === -5) throw new RangeError("Scene density columns must have equal length");
  if (code === -6) throw new RangeError("Scene density mean-color source is invalid");
  if (code < 0) throw new RangeError("invalid scene density packing");
  if (code === 0) return null;
  const view = new DataView(out.buffer, out.byteOffset, out.byteLength);
  const cols = view.getUint32(8, true);
  const rows = view.getUint32(12, true);
  const flags = view.getUint32(16, true);
  const maximum = view.getFloat64(24, true);
  const cells = rows * cols;
  const encoded = out.subarray(32, 32 + cells);
  let meanRgba = null;
  if (flags & 1) meanRgba = out.subarray(32 + cells, 32 + cells + cells * 4);
  return { encoded, max: maximum, meanRgba, rows, cols };
}

function packXyhp(planes) {
  if (!planes.length) return new Uint8Array();
  const bodyLen = planes.reduce((sum, plane) => sum + plane.length, 0);
  const out = new Uint8Array(16 + bodyLen);
  const view = new DataView(out.buffer);
  out.set(encodeUtf8Magic("XYHP"), 0);
  view.setUint32(4, 1, true);
  view.setUint32(8, planes.length, true);
  view.setUint32(12, 0, true);
  let offset = 16;
  for (const plane of planes) {
    out.set(plane, offset);
    offset += plane.length;
  }
  return out;
}

function parseSceneDash(value) {
  if (value == null) return null;
  if (typeof value === "string") {
    const preset = SCENE_DASH_PRESETS[value.trim().toLowerCase()];
    if (Object.hasOwn(SCENE_DASH_PRESETS, value.trim().toLowerCase())) return preset;
    const parts = value.split(",").map((part) => part.trim()).filter(Boolean);
    const lengths = parts.map(Number);
    if (lengths.some((length) => !Number.isFinite(length))) return false;
    value = lengths;
  }
  if (!Array.isArray(value)) return false;
  if (value.length < 2 || value.length > 8) return false;
  const lengths = value.map(Number);
  if (lengths.some((length) => !Number.isFinite(length) || length <= 0)) return false;
  return lengths;
}

function parseSceneLinecap(value) {
  if (value == null) return null;
  const name = String(value).trim().toLowerCase();
  if (name === "butt") return 0;
  if (name === "square") return 2;
  if (name === "round") return null;
  return false;
}

function validateMarkerPath(value) {
  if (value == null || typeof value !== "object" || Array.isArray(value)) return null;
  const contours = value.contours;
  if (!Array.isArray(contours) || contours.length < 1 || contours.length > 32) return null;
  const result = [];
  let totalVertices = 0;
  for (const contour of contours) {
    if (!Array.isArray(contour)) return null;
    const values = contour.map(Number);
    if (values.length < 4 || values.length % 2) return null;
    if (values.some((item) => !Number.isFinite(item) || Math.abs(item) > 0.500001)) return null;
    totalVertices += values.length / 2;
    result.push(values);
  }
  if (totalVertices > 96) return null;
  return { contours: result, filled: value.filled == null ? true : Boolean(value.filled) };
}

const GRAD_DIR_CODES = { down: 0, up: 1, right: 2, left: 3 };
const GRADIENT_DIRS = { "to top": "up", "to bottom": "down", "to left": "left", "to right": "right" };

function fillIsGradientAuthoring(fill) {
  if (fill != null && typeof fill === "object") return true;
  return typeof fill === "string" && fill.trim().toLowerCase().startsWith("linear-gradient(");
}

function splitTopLevel(text) {
  const parts = [];
  let current = "";
  let depth = 0;
  for (const ch of text) {
    if (ch === "(") depth += 1;
    else if (ch === ")") depth = Math.max(0, depth - 1);
    if (ch === "," && depth === 0) {
      parts.push(current.trim());
      current = "";
      continue;
    }
    current += ch;
  }
  if (current.trim()) parts.push(current.trim());
  return parts;
}

function parseGradientStop(item) {
  const tokens = item.trim().split(/\s+/);
  if (tokens.length >= 2 && tokens[tokens.length - 1].endsWith("%")) {
    const pos = Number(tokens[tokens.length - 1].slice(0, -1)) / 100;
    if (!Number.isFinite(pos)) return null;
    return { t: Math.min(1, Math.max(0, pos)), color: tokens.slice(0, -1).join(" ") };
  }
  return { t: null, color: item.trim() };
}

function parseLinearGradient(value, space = "mark") {
  if (typeof value !== "string") return null;
  const text = value.trim();
  const lowered = text.toLowerCase();
  if (!lowered.startsWith("linear-gradient(") || !text.endsWith(")")) return null;
  let args = splitTopLevel(text.slice("linear-gradient(".length, -1));
  let dir = "down";
  if (args.length && Object.hasOwn(GRADIENT_DIRS, args[0].toLowerCase())) {
    dir = GRADIENT_DIRS[args[0].toLowerCase()];
    args = args.slice(1);
  } else if (args.length && (args[0].toLowerCase().startsWith("to ") || args[0].toLowerCase().endsWith("deg"))) {
    return null;
  }
  if ((dir === "left" || dir === "right") && space === "mark") return null;
  if (args.length < 2 || args.length > 8) return null;
  const parsed = args.map(parseGradientStop);
  if (parsed.some((item) => item == null || !item.color)) return null;
  const count = parsed.length;
  const anchors = new Map();
  parsed.forEach((item, index) => {
    if (item.t != null) anchors.set(index, item.t);
  });
  if (!anchors.has(0)) anchors.set(0, 0);
  if (!anchors.has(count - 1)) anchors.set(count - 1, 1);
  const keys = [...anchors.keys()].sort((a, b) => a - b);
  let prev = 0;
  for (const key of keys) {
    prev = Math.max(anchors.get(key), prev);
    anchors.set(key, prev);
  }
  const resolved = new Array(count).fill(0);
  for (let i = 0; i < keys.length - 1; i += 1) {
    const i0 = keys[i];
    const i1 = keys[i + 1];
    const v0 = anchors.get(i0);
    const v1 = anchors.get(i1);
    for (let k = i0; k < i1; k += 1) {
      resolved[k] = v0 + ((v1 - v0) * (k - i0)) / (i1 - i0);
    }
  }
  resolved[count - 1] = anchors.get(count - 1);
  return {
    space,
    dir,
    stops: parsed.map((item, index) => [resolved[index], item.color]),
  };
}

function normalizeFillSpec(fill) {
  if (fill != null && typeof fill === "object" && fill.space != null && fill.dir != null && Array.isArray(fill.stops)) {
    return fill;
  }
  if (fill != null && typeof fill === "object") {
    const keys = Object.keys(fill).filter((key) => key !== "gradient" && key !== "space");
    if (keys.length) return null;
    return parseLinearGradient(fill.gradient, fill.space ?? "mark");
  }
  return parseLinearGradient(fill, "mark");
}

function constantMarkColor(trace) {
  const channel = trace.color_ch ?? trace.colorChannel ?? trace.color;
  if (trace.color_target != null) return null;
  if (channel == null) return String(trace.style?.color ?? "#3987e5");
  if (typeof channel === "string") return channel;
  if (channel.mode === "constant" && channel.constant != null) return String(channel.constant);
  if (String(trace.kind ?? "") === "scatter" && scatterUsesDensity(trace)) {
    return String(trace.style?.color ?? "#3987e5");
  }
  return null;
}

function admitFillGradient(trace) {
  const fill = trace.style?.fill;
  if (!fillIsGradientAuthoring(fill)) return null;
  const spec = normalizeFillSpec(fill);
  const markColor = constantMarkColor(trace);
  if (spec == null || markColor == null) return null;
  if (!["mark", "plot"].includes(spec.space) || !Object.hasOwn(GRAD_DIR_CODES, spec.dir)) return null;
  if (!Array.isArray(spec.stops) || spec.stops.length < 2 || spec.stops.length > 8) return null;
  const resolved = [];
  let prevT = -1;
  for (const stop of spec.stops) {
    if (!Array.isArray(stop) || stop.length !== 2) return null;
    const t = Number(stop[0]);
    if (!Number.isFinite(t) || t < 0 || t > 1 || t < prevT) return null;
    let css = String(stop[1]).trim();
    const lowered = css.toLowerCase();
    if (lowered.includes("var(")) return null;
    if (lowered === "currentcolor" || css === "") css = markColor;
    const rgba = cssColorRgba8(css, 1);
    resolved.push([t, rgba]);
    prevT = t;
  }
  return { space: spec.space, dir: spec.dir, stops: resolved };
}

function gradientSolidCss(gradient) {
  for (const [, rgba] of gradient.stops) {
    if (rgba[3] > 0) return `rgb(${rgba[0]},${rgba[1]},${rgba[2]})`;
  }
  return "rgb(0,0,0)";
}

const XYSS_HAS_DASH = 1 << 0;
const XYSS_HAS_CAP = 1 << 1;
const XYSS_HAS_MARKER = 1 << 2;
const XYSS_HAS_GRAD = 1 << 3;

function packXySs(dashes, linecaps, markerPaths, gradients = []) {
  const nRecords = Math.max(dashes.length, linecaps.length, markerPaths.length, gradients.length);
  const records = [];
  for (let index = 0; index < nRecords; index += 1) {
    const pattern = dashes[index];
    const cap = linecaps[index];
    const path = markerPaths[index];
    const gradient = gradients[index];
    let flags = 0;
    let remainderLen = 0;
    if (pattern && pattern.length) {
      flags |= XYSS_HAS_DASH;
    }
    if (cap === 0 || cap === 2) flags |= XYSS_HAS_CAP;
    if (path) {
      flags |= XYSS_HAS_MARKER;
      remainderLen += path.contours.reduce((sum, contour) => sum + 8 + contour.length * 8, 0);
    }
    if (gradient) {
      flags |= XYSS_HAS_GRAD;
      remainderLen += gradient.stops.length * 8;
    }
    if (!flags) continue;
    const record = new Uint8Array(48 + remainderLen);
    const view = new DataView(record.buffer);
    view.setUint32(0, index, true);
    record[4] = flags;
    record[5] = pattern && pattern.length ? pattern.length : 0;
    record[6] = (cap === 0 || cap === 2) ? cap : 255;
    record[7] = path ? path.contours.length : 0;
    record[8] = gradient ? gradient.stops.length : 0;
    record[9] = gradient ? GRAD_DIR_CODES[gradient.dir] : 0;
    record[10] = gradient && gradient.space === "plot" ? 1 : 0;
    record[11] = path && path.filled === false ? 0 : (path ? 1 : 0);
    if (pattern && pattern.length) {
      for (let offset = 0; offset < pattern.length; offset += 1) {
        view.setFloat32(16 + offset * 4, pattern[offset], true);
      }
    }
    let cursor = 48;
    if (path) {
      for (const contour of path.contours) {
        view.setUint32(cursor, contour.length / 2, true);
        view.setUint32(cursor + 4, 0, true);
        cursor += 8;
        for (let vertex = 0; vertex < contour.length; vertex += 1) {
          view.setFloat64(cursor, contour[vertex], true);
          cursor += 8;
        }
      }
    }
    if (gradient) {
      for (const [t, rgba] of gradient.stops) {
        view.setFloat32(cursor, t, true);
        record[cursor + 4] = rgba[0];
        record[cursor + 5] = rgba[1];
        record[cursor + 6] = rgba[2];
        record[cursor + 7] = rgba[3];
        cursor += 8;
      }
    }
    records.push(record);
  }
  if (!records.length) return new Uint8Array();
  const out = new Uint8Array(16 + records.reduce((sum, record) => sum + record.length, 0));
  const view = new DataView(out.buffer);
  out.set(encodeUtf8Magic("XYSS"), 0);
  view.setUint32(4, 1, true);
  view.setUint32(8, records.length, true);
  view.setUint32(12, 0, true);
  let offset = 16;
  for (const record of records) {
    out.set(record, offset);
    offset += record.length;
  }
  return out;
}

function packSceneExtrasFromFacts(polar, paint, facts) {
  const polarBytes = polar instanceof Uint8Array ? polar : new Uint8Array();
  const paintBytes = paint instanceof Uint8Array ? paint : new Uint8Array();
  const factsBytes = facts instanceof Uint8Array ? facts : new Uint8Array();
  if (!polarBytes.length && !paintBytes.length && !factsBytes.length) return new Uint8Array();
  const out = new Uint8Array(Math.max(256, polarBytes.length + paintBytes.length + factsBytes.length + 64));
  const code = xyScenePackSceneExtras(
    polarBytes.length ? u8Ptr(polarBytes) : 0,
    BigInt(polarBytes.length),
    paintBytes.length ? u8Ptr(paintBytes) : 0,
    BigInt(paintBytes.length),
    factsBytes.length ? u8Ptr(factsBytes) : 0,
    BigInt(factsBytes.length),
    u8Ptr(out),
    BigInt(out.length),
  );
  if (code === -5) throw new RangeError("Scene extras polar or paint envelope is invalid");
  if (code === -6) throw new RangeError("Scene style sidecar facts are invalid");
  if (code < 0) throw new RangeError("invalid scene extras packing");
  return out.subarray(0, code);
}

export function polarLayout(thetaAxis = {}, rAxis = {}, plot = {}) {
  const unit = thetaAxis.theta_unit ?? thetaAxis.thetaUnit ?? "radians";
  const turn = unit === "degrees" ? 360 : Math.PI * 2;
  const sector = thetaAxis.sector ?? [0, turn];
  const categories = thetaAxis.categories ?? [];
  const [rLo, rHi] = rAxis.range ?? [0, 1];
  const origin = rAxis.r_origin ?? rAxis.rOrigin;
  const scale = polarRScale(rAxis);
  const metrics = new Float64Array(POLAR_METRICS_LEN);
  const written = xyPolarLayout(
    Number(plot.x ?? 0),
    Number(plot.y ?? 0),
    Number(plot.w ?? 0),
    Number(plot.h ?? 0),
    polarThetaUnit(unit),
    polarThetaZero(thetaAxis.theta_zero ?? thetaAxis.thetaZero ?? "E"),
    polarThetaDirection(thetaAxis.theta_direction ?? thetaAxis.thetaDirection),
    Number(sector[0]),
    Number(sector[1]),
    categories.length,
    Number(rLo),
    Number(rHi),
    origin == null ? Number.NaN : Number(origin),
    Number(rAxis.hole ?? 0),
    scale.kind,
    scale.constant,
    scale.maskNonpositive ? 1 : 0,
    f64Ptr(metrics),
    POLAR_METRICS_LEN,
  );
  if (written !== POLAR_METRICS_LEN) throw new RangeError("invalid polar-layout request");
  return metrics;
}

export function polarProject(metrics, theta, r) {
  const packed = metrics instanceof Float64Array ? metrics : Float64Array.from(metrics);
  const th = Float64Array.from(Array.isArray(theta) ? theta : [theta]);
  const rv = Float64Array.from(Array.isArray(r) ? r : [r]);
  if (th.length !== rv.length) throw new RangeError("theta and r must have the same length");
  const outX = new Float64Array(th.length);
  const outY = new Float64Array(th.length);
  const written = xyPolarProject(
    f64Ptr(packed),
    packed.length,
    f64Ptr(th),
    f64Ptr(rv),
    th.length,
    f64Ptr(outX),
    f64Ptr(outY),
  );
  if (written === USIZE_MAX_64 || written !== th.length) {
    throw new RangeError("invalid polar-project request");
  }
  if (!Array.isArray(theta)) return [outX[0], outY[0]];
  return [outX, outY];
}

export function polarLegendRoom(width) {
  const out = new Float64Array(1);
  const written = xyPolarLegendRoom(Number(width), f64Ptr(out));
  if (written === USIZE_MAX_64) throw new RangeError("invalid polar-legend-room request");
  return out[0];
}

export function polarLegendReserve(compact, locHasLeft, width) {
  const side = new Uint32Array(1);
  const room = new Float64Array(1);
  const written = xyPolarLegendReserve(
    compact ? 1 : 0,
    locHasLeft ? 1 : 0,
    Number(width),
    u32Ptr(side),
    f64Ptr(room),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid polar-legend-reserve request");
  return [POLAR_LEGEND_SIDES[side[0]], room[0]];
}

export function polarLabelRoom(widest = null) {
  const out = new Float64Array(1);
  const written = xyPolarLabelRoom(widest == null ? Number.NaN : Number(widest), f64Ptr(out));
  if (written === USIZE_MAX_64) throw new RangeError("invalid polar-label-room request");
  return out[0];
}

export function recutPolarPlot(plot, width, height, {
  legendSide = "",
  legendRoom = 0,
  polarLabelRoom: labelRoom = 0,
  authoredPadding = false,
  yTitled = false,
  keepsBottom = false,
} = {}) {
  const side = POLAR_LEGEND_SIDE_CODES[legendSide];
  if (side === undefined) throw new RangeError("legendSide must be '', left, right, or bottom");
  const incoming = Float64Array.from([
    Number(plot.x),
    Number(plot.y),
    Number(plot.w),
    Number(plot.h),
    Number(plot.top_axis_room ?? plot.topAxisRoom ?? 0),
  ]);
  const out = new Float64Array(9);
  const written = xyRecutPolarPlot(
    f64Ptr(incoming),
    Number(width),
    Number(height),
    side,
    Number(legendRoom),
    Number(labelRoom),
    authoredPadding ? 1 : 0,
    yTitled ? 1 : 0,
    keepsBottom ? 1 : 0,
    f64Ptr(out),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid polar-recut request");
  const result = { x: out[0], y: out[1], w: out[2], h: out[3], topAxisRoom: out[4] };
  if (Number.isFinite(out[5])) {
    result.legendBoxX = out[5];
    result.legendBoxY = out[6];
    result.legendBoxW = out[7];
    result.legendBoxH = out[8];
  }
  return result;
}

export function tightLayoutSolve({
  canvasW,
  canvasH,
  nrows,
  ncols,
  compact = false,
  panels = [],
  extra = [0, 0, 0, 0],
  pad = null,
  wPad = null,
  hPad = null,
  pointPx = 1,
  rect = [0, 0, 1, 1],
} = {}) {
  if (!Array.isArray(extra) || extra.length !== 4) {
    throw new RangeError("extra must be left, right, bottom, top");
  }
  if (!Array.isArray(rect) || rect.length !== 4) {
    throw new RangeError("rect must be left, bottom, right, top");
  }
  const packed = new Float64Array(panels.length * 8);
  for (let index = 0; index < panels.length; index += 1) {
    const panel = panels[index];
    const at = index * 8;
    packed[at] = Number(panel.row0);
    packed[at + 1] = Number(panel.row1);
    packed[at + 2] = Number(panel.col0);
    packed[at + 3] = Number(panel.col1);
    packed[at + 4] = Number(panel.left);
    packed[at + 5] = Number(panel.top);
    packed[at + 6] = Number(panel.right);
    packed[at + 7] = Number(panel.bottom);
  }
  const extraArr = Float64Array.from(extra, (value) => Number(value));
  const rectArr = Float64Array.from(rect, (value) => Number(value));
  const out = new Float64Array(6);
  const written = xyTightLayoutSolve(
    Number(canvasW),
    Number(canvasH),
    Number(nrows) >>> 0,
    Number(ncols) >>> 0,
    compact ? 1 : 0,
    packed.length ? f64Ptr(packed) : 0,
    BigInt(panels.length),
    f64Ptr(extraArr),
    pad == null ? Number.NaN : Number(pad),
    wPad == null ? Number.NaN : Number(wPad),
    hPad == null ? Number.NaN : Number(hPad),
    Number(pointPx),
    f64Ptr(rectArr),
    f64Ptr(out),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid tight-layout request");
  return { left: out[0], right: out[1], bottom: out[2], top: out[3], wspace: out[4], hspace: out[5] };
}

export function scaleMap({ values, kind = "linear", operation = "pixel", domain, range = [0, 1], constant = 1, nonpositive = "clip" }) {
  const kindCode = kind === "linear" ? 0 : kind === "log" ? 1 : kind === "symlog" ? 2 : -1;
  const operationCode = operation === "coord" ? 0 : operation === "pixel" ? 1 : operation === "value" ? 2 : -1;
  if (kindCode < 0) throw new RangeError("kind must be linear, log, or symlog");
  if (operationCode < 0) throw new RangeError("operation must be coord, pixel, or value");
  if (nonpositive !== "clip" && nonpositive !== "mask") {
    throw new RangeError("nonpositive must be clip or mask");
  }
  if (!Array.isArray(domain) || domain.length !== 2 || !Array.isArray(range) || range.length !== 2) {
    throw new RangeError("domain and range must each contain two values");
  }
  const source = asF64Array(values, "values");
  const output = new Float64Array(source.length);
  const status = xySceneScaleMap(
    f64Ptr(source), BigInt(source.length), kindCode, operationCode,
    Number(domain[0]), Number(domain[1]), Number(range[0]), Number(range[1]),
    Number(constant), nonpositive === "mask" ? 1 : 0, f64Ptr(output),
  );
  if (status !== 0) throw new RangeError("invalid canonical scene scale");
  return output;
}

function axisDescriptor(axis, name) {
  const { id, kind = "linear", domain, constant = 1, nonpositive = "clip" } = axis;
  const kindCode = kind === "linear" ? 0 : kind === "log" ? 1 : kind === "symlog" ? 2 : -1;
  if (kindCode < 0) throw new RangeError(`${name}.kind must be linear, log, or symlog`);
  if (nonpositive !== "clip" && nonpositive !== "mask") throw new RangeError(`${name}.nonpositive must be clip or mask`);
  if (!Array.isArray(domain) || domain.length !== 2) throw new RangeError(`${name}.domain must contain two values`);
  return [asU64(id, `${name}.id`), kindCode, Number(domain[0]), Number(domain[1]), Number(constant), nonpositive === "mask" ? 1 : 0];
}

const AXIS_STYLE_KEYS = new Set([
  "grid_color", "grid_width", "grid_opacity", "axis_color", "axis_width",
  "tick_color", "tick_width", "tick_length", "tick_direction", "tick_label_color", "label_color",
  "gridColor", "gridWidth", "gridOpacity", "axisColor", "axisWidth",
  "tickColor", "tickWidth", "tickLength", "tickDirection", "tickLabelColor", "labelColor",
]);

function styleHas(style, snake, camel) {
  return Object.hasOwn(style, snake) || (camel != null && Object.hasOwn(style, camel));
}

function styleValue(style, snake, camel, fallback) {
  if (Object.hasOwn(style, snake)) return style[snake];
  if (camel != null && Object.hasOwn(style, camel)) return style[camel];
  return fallback;
}

function packChromeAxis(axis, options, sides) {
  const style = options.style ?? {};
  const minor = options.minorStyle ?? options.minor_style ?? {};
  for (const [label, authored] of [["style", style], ["minor_style", minor]]) {
    const unsupported = Object.keys(authored).filter((key) => authored[key] != null && !AXIS_STYLE_KEYS.has(key));
    if (unsupported.length) {
      throw new RangeError(`Scene v12 does not yet encode ${axis} axis ${label} keys`);
    }
  }
  const side = options.side ?? sides[0];
  if (!sides.includes(side)) throw new RangeError(`Scene ${axis} axis side is invalid`);
  const sideCode = sides.indexOf(side);
  const mask = (values, name) => {
    if (values == null) return 1 << sideCode;
    return values.reduce((sum, value) => {
      const index = sides.indexOf(value);
      if (index < 0) throw new RangeError(`Scene ${axis} axis ${name} are invalid`);
      return sum | (1 << index);
    }, 0);
  };
  const direction = { out: 0, in: 1, inout: 2 };
  let paintFlags = 0;
  if (styleHas(style, "axis_color", "axisColor")) paintFlags |= 1 << 0;
  if (styleHas(style, "grid_color", "gridColor")) paintFlags |= 1 << 1;
  if (styleHas(style, "tick_color", "tickColor")) paintFlags |= 1 << 2;
  if (styleHas(minor, "grid_color", "gridColor")) paintFlags |= 1 << 3;
  if (styleHas(minor, "tick_color", "tickColor")) paintFlags |= 1 << 4;
  if (styleHas(style, "tick_label_color", "tickLabelColor") || styleHas(style, "label_color", "labelColor")) paintFlags |= 1 << 5;
  const widthSpecs = [
    [style, "axis_width", "axisWidth", 1],
    [style, "grid_width", "gridWidth", 1],
    [style, "tick_width", "tickWidth", 1],
    [style, "tick_length", "tickLength", 4],
    [minor, "grid_width", "gridWidth", 1],
    [minor, "tick_width", "tickWidth", 1],
    [minor, "tick_length", "tickLength", 0],
  ];
  let widthFlags = 0;
  const widths = widthSpecs.map(([source, snake, camel, fallback], index) => {
    if (styleHas(source, snake, camel)) {
      widthFlags |= 1 << index;
      return Number(styleValue(source, snake, camel, fallback));
    }
    return fallback;
  });
  const paints = [
    String(styleValue(style, "axis_color", "axisColor", "#202020")),
    String(styleValue(style, "grid_color", "gridColor", "#202020")),
    String(styleValue(style, "tick_color", "tickColor", "#202020")),
    String(styleValue(minor, "grid_color", "gridColor", "transparent")),
    String(styleValue(minor, "tick_color", "tickColor", "#202020")),
    String(styleValue(style, "tick_label_color", "tickLabelColor", styleValue(style, "label_color", "labelColor", "#202020"))),
  ].map(encodeUtf8);
  const prefix = new Uint8Array(84);
  const view = new DataView(prefix.buffer);
  prefix[0] = sideCode;
  prefix[1] = mask(options.tickSides ?? options.tick_sides, "tick_sides");
  prefix[2] = mask(options.tickLabelSides ?? options.tick_label_sides, "tick_label_sides");
  prefix[3] = direction[String(styleValue(style, "tick_direction", "tickDirection", "out"))] ?? 255;
  prefix[4] = direction[String(styleValue(minor, "tick_direction", "tickDirection", "out"))] ?? 255;
  prefix[5] = paintFlags;
  prefix[6] = widthFlags;
  view.setFloat32(8, Number(styleValue(style, "grid_opacity", "gridOpacity", 1)), true);
  view.setFloat32(12, Number(styleValue(minor, "grid_opacity", "gridOpacity", 1)), true);
  widths.forEach((value, index) => view.setFloat64(16 + index * 8, value, true));
  paints.forEach((bytes, index) => view.setUint16(72 + index * 2, bytes.length, true));
  return concatBytes([prefix, ...paints]);
}

function resolveChromeStyle(envelope) {
  const out = new Uint8Array(200);
  const code = xySceneResolveChromeStyle(u8Ptr(envelope), BigInt(envelope.length), u8Ptr(out), BigInt(out.length));
  if (code !== 200) throw new RangeError("invalid chrome style envelope");
  return out;
}

function defaultChromeStyle() {
  const envelope = new Uint8Array(16);
  envelope.set(encodeUtf8("XYCH").slice(0, 4), 0);
  new DataView(envelope.buffer).setUint32(4, 1, true);
  return resolveChromeStyle(envelope);
}

function figureChromeStyle(figure) {
  const figureStyle = figure.style ?? {};
  let flags = 2 << 8;
  let chart = new Uint8Array(0);
  let plot = new Uint8Array(0);
  if (figureStyle.background != null) {
    flags |= 1;
    chart = encodeUtf8(figureStyle.background || "transparent");
  }
  if (figureStyle["--chart-bg"] != null) {
    flags |= 2;
    plot = encodeUtf8(figureStyle["--chart-bg"] || "transparent");
  }
  const x = packChromeAxis("x", figure.xAxis ?? figure.x_axis ?? {}, ["bottom", "top"]);
  const y = packChromeAxis("y", figure.yAxis ?? figure.y_axis ?? {}, ["left", "right"]);
  const header = new Uint8Array(16);
  const view = new DataView(header.buffer);
  header.set(encodeUtf8("XYCH").slice(0, 4), 0);
  view.setUint32(4, 1, true);
  view.setUint32(8, flags >>> 0, true);
  view.setUint16(12, chart.length, true);
  view.setUint16(14, plot.length, true);
  return resolveChromeStyle(concatBytes([header, chart, plot, x, y]));
}

/** Encode the shared backend-neutral Scene v12 typed batch. */
export function sceneBatchEncode({
  viewport, margins, xAxis, yAxis, kinds, stableIds, styleRefs, styles, diameter, symbols, x0, y0, x1, y1,
  expansionModes = null,
  title = "", xLabel = "", yLabel = "", chromeStyle = null,
  xMajorTicks = null, xMinorTicks = [], yMajorTicks = null, yMinorTicks = [],
  xTickLabels = null, yTickLabels = null,
  xFormat = null, yFormat = null,
  legendInput = null, colorbarInput = null, authoredTextAnnotations = null,
  polarInput = null,
}) {
  if (!Array.isArray(viewport) || viewport.length !== 2 || !Array.isArray(margins) || margins.length !== 4) {
    throw new RangeError("viewport and margins must contain two and four values");
  }
  if (styles.length > MAX_SCENE_STYLES) {
    throw new RangeError(`scene style tables are limited to ${MAX_SCENE_STYLES} entries`);
  }
  const kindArray = asUnsignedArray(kinds, "kinds", 255, Uint8Array);
  if (kindArray.length > MAX_SCENE_MARKS) {
    throw new RangeError(`scene batches are limited to ${MAX_SCENE_MARKS} records`);
  }
  const ids = asStableIds(stableIds);
  const styleRefArray = asUnsignedArray(styleRefs, "styleRefs", 0xffff_ffff, Uint32Array);
  const diameters = asF64Array(diameter, "diameter");
  const symbolCodes = asUnsignedArray(symbols, "symbols", 255, Uint8Array);
  const expansionModeCodes = expansionModes == null
    ? new Uint8Array(kindArray.length)
    : asUnsignedArray(expansionModes, "expansionModes", 12, Uint8Array);
  const fills = new Uint8Array(styles.length * 4);
  const strokes = new Uint8Array(styles.length * 4);
  const widths = new Float64Array(styles.length);
  for (const [index, style] of styles.entries()) {
    const fill = asUnsignedArray(style.fillRgba, `styles[${index}].fillRgba`, 255, Uint8Array);
    const stroke = asUnsignedArray(style.strokeRgba, `styles[${index}].strokeRgba`, 255, Uint8Array);
    requireLength(fill, 4, `styles[${index}].fillRgba`);
    requireLength(stroke, 4, `styles[${index}].strokeRgba`);
    fills.set(fill, index * 4);
    strokes.set(stroke, index * 4);
    widths[index] = Number(style.strokeWidth ?? 0);
  }
  const coordinates = [x0, y0, x1, y1].map((value, index) => asF64Array(value, ["x0", "y0", "x1", "y1"][index]));
  const length = kindArray.length;
  for (const [value, name] of [[ids, "stableIds"], [styleRefArray, "styleRefs"], [diameters, "diameter"], [symbolCodes, "symbols"], [expansionModeCodes, "expansionModes"], ...coordinates.map((value, index) => [value, ["x0", "y0", "x1", "y1"][index]])]) requireLength(value, length, name);
  const xd = axisDescriptor(xAxis, "xAxis");
  const yd = axisDescriptor(yAxis, "yAxis");
  const titleBytes = new TextEncoder().encode(String(title ?? ""));
  const xLabelBytes = new TextEncoder().encode(String(xLabel ?? ""));
  const yLabelBytes = new TextEncoder().encode(String(yLabel ?? ""));
  if ([titleBytes, xLabelBytes, yLabelBytes].some((value) => value.length > MAX_SCENE_TEXT_BYTES)) {
    throw new RangeError(`scene title and axis labels are limited to ${MAX_SCENE_TEXT_BYTES} UTF-8 bytes each`);
  }
  const chrome = chromeStyle == null
    ? defaultChromeStyle()
    : asUnsignedArray(chromeStyle, "chromeStyle", 255, Uint8Array);
  requireLength(chrome, 200, "chromeStyle");
  const tickArrays = [xMajorTicks, xMinorTicks, yMajorTicks, yMinorTicks].map((value, index) => value == null ? null : asF64Array(value, ["xMajorTicks", "xMinorTicks", "yMajorTicks", "yMinorTicks"][index]));
  const frameTickLabels = (labels, name) => {
    if (labels == null) return new Uint8Array();
    if (!Array.isArray(labels) || labels.length > 200) throw new RangeError(`${name} must contain at most 200 strings`);
    const texts = labels.map((value) => new TextEncoder().encode(String(value)));
    if (texts.some((value) => value.length === 0 || value.includes(0)) || texts.reduce((sum, value) => sum + value.length, 0) > MAX_SCENE_TEXT_BYTES) throw new RangeError(`${name} must contain nonempty bounded UTF-8 strings`);
    const out = new Uint8Array(12 + texts.reduce((sum, value) => sum + 4 + value.length, 0)); const view = new DataView(out.buffer);
    out.set(new TextEncoder().encode("XYTL")); view.setUint32(4, 1, true); view.setUint32(8, texts.length, true); let at = 12;
    for (const text of texts) { view.setUint32(at, text.length, true); at += 4; out.set(text, at); at += text.length; }
    return out;
  };
  const xTickLabelBytes = frameTickLabels(xTickLabels, "xTickLabels");
  const yTickLabelBytes = frameTickLabels(yTickLabels, "yTickLabels");
  const frameAxisFormat = (value, name) => {
    if (value == null) return new Uint8Array();
    if (typeof value !== "string") throw new TypeError(`${name} must be a string or null`);
    const encoded = new TextEncoder().encode(value);
    if (encoded.length > 256 || encoded.includes(0)) throw new RangeError(`${name} must be NUL-free and at most 256 UTF-8 bytes`);
    return encoded;
  };
  const xFormatBytes = frameAxisFormat(xFormat, "xFormat");
  const yFormatBytes = frameAxisFormat(yFormat, "yFormat");
  const legend = legendInput == null ? new Uint8Array() : asUnsignedArray(legendInput, "legendInput", 255, Uint8Array);
  const colorbar = colorbarInput == null ? new Uint8Array() : asUnsignedArray(colorbarInput, "colorbarInput", 255, Uint8Array);
  const polar = polarInput == null || polarInput.length === 0
    ? new Uint8Array()
    : asUnsignedArray(polarInput, "polarInput", 255, Uint8Array);
  if (polar.length) {
    const magic = String.fromCharCode(...polar.subarray(0, 4));
    if (!["XYPL", "XYHP", "XYEX", "XYDS", "XYLC", "XYMP", "XYGR"].includes(magic)) {
      throw new RangeError("polarInput must be empty, XYPL, XYHP, XYEX, XYDS, XYLC, XYMP, or XYGR");
    }
    if (magic === "XYPL" && polar.length !== 92) {
      throw new RangeError("polarInput must be empty or a 92-byte XYPL v1 envelope");
    }
  }
  const authoredText = authoredTextAnnotations == null ? new Uint8Array() : asUnsignedArray(authoredTextAnnotations, "authoredTextAnnotations", 255, Uint8Array);
  const authoredInput = xFormatBytes.length || yFormatBytes.length ? (() => {
    const out = new Uint8Array(20 + xFormatBytes.length + yFormatBytes.length + authoredText.length);
    const view = new DataView(out.buffer);
    out.set(new TextEncoder().encode("XYAF"));
    view.setUint32(4, 1, true);
    view.setUint32(8, xFormatBytes.length, true);
    view.setUint32(12, yFormatBytes.length, true);
    view.setUint32(16, authoredText.length, true);
    out.set(xFormatBytes, 20);
    out.set(yFormatBytes, 20 + xFormatBytes.length);
    out.set(authoredText, 20 + xFormatBytes.length + yFormatBytes.length);
    return out;
  })() : authoredText;
  if (colorbar.length > 4_600) throw new RangeError("scene colorbar input is limited to 4,600 bytes");
  if (tickArrays.some((value) => value != null && value.length > 200)) throw new RangeError("scene axis tick lists are limited to 200 values");
  const polarView = polarAbiInputPointer(polar);
  let capacity = 160 + widths.length * 16 + length * 56 + 248 + titleBytes.length + xLabelBytes.length + yLabelBytes.length + xTickLabelBytes.length + yTickLabelBytes.length + authoredInput.length + legend.length + colorbar.length + tickArrays.reduce((sum, value) => sum + (value?.byteLength ?? 0), 0);
  for (;;) {
    const output = new Uint8Array(capacity);
    const rawWritten = xySceneBatchEncode(
      Number(viewport[0]), Number(viewport[1]), ...margins.map(Number), ...xd, ...yd,
      u8Ptr(chrome), BigInt(chrome.length),
      f64Ptr(tickArrays[0]), BigInt(tickArrays[0]?.length ?? 0), tickArrays[0] == null ? 1 : 0,
      f64Ptr(tickArrays[1]), BigInt(tickArrays[1]?.length ?? 0),
      f64Ptr(tickArrays[2]), BigInt(tickArrays[2]?.length ?? 0), tickArrays[2] == null ? 1 : 0,
      f64Ptr(tickArrays[3]), BigInt(tickArrays[3]?.length ?? 0),
      xTickLabelBytes.length ? u8Ptr(xTickLabelBytes) : 0, BigInt(xTickLabelBytes.length),
      yTickLabelBytes.length ? u8Ptr(yTickLabelBytes) : 0, BigInt(yTickLabelBytes.length),
      authoredInput.length ? u8Ptr(authoredInput) : 0, BigInt(authoredInput.length),
      u8Ptr(kindArray), pointer(ids, "uint64_t *"), u32Ptr(styleRefArray),
      u8Ptr(fills), u8Ptr(strokes), f64Ptr(widths), BigInt(widths.length),
      f64Ptr(diameters), u8Ptr(symbolCodes), u8Ptr(expansionModeCodes),
      ...coordinates.map(f64Ptr), BigInt(length),
      titleBytes.length ? u8Ptr(titleBytes) : 0, BigInt(titleBytes.length),
      xLabelBytes.length ? u8Ptr(xLabelBytes) : 0, BigInt(xLabelBytes.length),
      yLabelBytes.length ? u8Ptr(yLabelBytes) : 0, BigInt(yLabelBytes.length),
      legend.length ? u8Ptr(legend) : 0, BigInt(legend.length),
      colorbar.length ? u8Ptr(colorbar) : 0, BigInt(colorbar.length),
      polarView.ptr,
      u8Ptr(output), BigInt(capacity),
    );
    if (rawWritten === USIZE_MAX_64) throw new RangeError("invalid canonical scene batch");
    const written = Number(rawWritten);
    if (!Number.isSafeInteger(written) || written < 0) throw new RangeError("canonical scene batch exceeded host output limits");
    if (written <= capacity) return output.slice(0, written);
    capacity = written;
  }
}

function sceneOutput(encoded, call, name, extra = []) {
  const source = asU8Array(encoded, "encoded scene");
  if (source.length === 0) throw new RangeError("encoded scene must not be empty");
  let capacity = Math.max(256, source.length * 3);
  for (;;) {
    const output = new Uint8Array(capacity);
    const rawWritten = call(u8Ptr(source), BigInt(source.length), ...extra, u8Ptr(output), BigInt(capacity));
    if (rawWritten === USIZE_MAX_64) throw new RangeError(`invalid canonical scene for ${name}`);
    const written = Number(rawWritten);
    if (!Number.isSafeInteger(written) || written < 0) throw new RangeError(`${name} output exceeded host limits`);
    if (written <= capacity) return output.slice(0, written);
    capacity = written;
  }
}

export function sceneSvg(encoded) {
  return new TextDecoder().decode(sceneOutput(encoded, xySceneSvg, "SVG"));
}

export function svgToPdf(svg) {
  const text = String(svg);
  const source = new TextEncoder().encode(text);
  let capacity = Math.max(256, source.length * 2);
  for (;;) {
    const output = new Uint8Array(capacity);
    const rawWritten = xySvgToPdf(
      source.length ? u8Ptr(source) : 0,
      BigInt(source.length),
      u8Ptr(output),
      BigInt(capacity),
    );
    if (rawWritten === USIZE_MAX_64) {
      const end = output.indexOf(0);
      const message = new TextDecoder().decode(end >= 0 ? output.subarray(0, end) : output).trim()
        || "unsupported SVG feature";
      throw new RangeError(message);
    }
    const written = Number(rawWritten);
    if (!Number.isSafeInteger(written) || written < 0) {
      throw new RangeError("svgToPdf output exceeded host limits");
    }
    if (written <= capacity) return output.slice(0, written);
    capacity = written;
  }
}

function encodePixels(fn, pixels, width, height, channels, extra = [], label = "image") {
  const source = pixels instanceof Uint8Array ? pixels : new Uint8Array(pixels);
  const w = Number(width);
  const h = Number(height);
  const c = Number(channels);
  if (!Number.isInteger(w) || !Number.isInteger(h) || !Number.isInteger(c)) {
    throw new RangeError(`${label} dimensions must be integers`);
  }
  let capacity = Math.max(256, source.length);
  for (;;) {
    const output = new Uint8Array(capacity);
    const rawWritten = fn(
      source.length ? u8Ptr(source) : 0,
      BigInt(source.length),
      BigInt(w),
      BigInt(h),
      BigInt(c),
      ...extra,
      u8Ptr(output),
      BigInt(capacity),
    );
    if (rawWritten === USIZE_MAX_64) {
      const end = output.indexOf(0);
      const message = new TextDecoder().decode(end >= 0 ? output.subarray(0, end) : output).trim()
        || `invalid ${label} input`;
      throw new RangeError(message);
    }
    const written = Number(rawWritten);
    if (!Number.isSafeInteger(written) || written < 0) {
      throw new RangeError(`${label} output exceeded host limits`);
    }
    if (written <= capacity) return output.slice(0, written);
    capacity = written;
  }
}

export function encodeJpeg(pixels, width, height, channels, quality = 90) {
  const q = Number(quality);
  if (!Number.isInteger(q)) throw new RangeError("quality must be an int in 1..100");
  return encodePixels(xyEncodeJpeg, pixels, width, height, channels, [q], "JPEG");
}

export function encodeWebp(pixels, width, height, channels) {
  return encodePixels(xyEncodeWebp, pixels, width, height, channels, [], "WebP");
}

export function encodePng(pixels, width, height, channels, mode = 0, compression = 6) {
  const m = Number(mode);
  const c = Number(compression);
  if (!Number.isInteger(m) || (m !== 0 && m !== 1)) {
    throw new RangeError("PNG mode must be 0 (auto) or 1 (truecolor)");
  }
  if (!Number.isInteger(c) || c < 0 || c > 9) {
    throw new RangeError("PNG compression must be an int in 0..9");
  }
  return encodePixels(xyEncodePng, pixels, width, height, channels, [m, c], "PNG");
}

export function sceneRasterCommands(encoded, scale = 1) {
  const factor = Number(scale);
  if (!Number.isFinite(factor) || factor <= 0) throw new RangeError("scene raster scale must be positive and finite");
  return sceneOutput(encoded, xySceneRasterCommands, "raster commands", [factor]);
}

export function sceneBrowserPainter(encoded, maxBytes = 64 * 1024 * 1024) {
  const limit = Number(maxBytes);
  if (!Number.isSafeInteger(limit) || limit <= 0) throw new RangeError("scene painter byte limit must be a positive safe integer");
  return sceneOutput(encoded, xySceneBrowserPainter, "browser painter", [BigInt(limit)]);
}

function rgba8(css, opacity = 1) {
  return cssColorRgba8(css, opacity);
}

function annotationNumber(style, key, fallback, label) {
  const raw = Object.hasOwn(style, key) ? style[key] : fallback;
  if (raw == null || typeof raw === "boolean" || (typeof raw === "string" && raw.trim() === "")) throw new RangeError(`Scene v12 annotation ${label} must be numeric`);
  const value = Number(raw);
  if (!Number.isFinite(value)) throw new RangeError(`Scene v12 annotation ${label} must be numeric`);
  return value;
}

function annotationColor(style, key, fallback, label) {
  const raw = Object.hasOwn(style, key) ? style[key] : fallback;
  if (typeof raw !== "string" || raw.trim() === "") throw new RangeError(`Scene v12 annotation ${label} must be a nonempty CSS color`);
  return raw;
}

const RECT_KINDS = new Set(["bar", "column", "histogram", "violin", "box"]);
const SEGMENT_KINDS = new Set(["segments", "errorbar", "stem", "contour", "box_whisker", "box_median"]);
const BAND_KINDS = new Set(["area", "error_band"]);
const RIBBON_KINDS = new Set(["ribbon"]);
const POLYFILL_KINDS = new Set(["triangle_mesh"]);
const HEXBIN_KINDS = new Set(["hexbin"]);
const HEXBIN_REDUCES = new Set(["count", "mean", "sum"]);
const HEATMAP_KINDS = new Set(["heatmap"]);
const STROKE_KINDS = new Set(["line", "segments", "errorbar", "stem", "contour", "box_whisker", "box_median"]);
const SUPPORTED_KINDS = new Set([
  "scatter", "line", "bar", "column", "histogram", "violin", "box",
  "segments", "errorbar", "stem", "contour", "box_whisker", "box_median",
  "area", "error_band", "ribbon", "triangle_mesh", "hexbin", "heatmap",
]);
const XYFS_TRACE_UNSUPPORTED_KIND = 1 << 0;
const XYFS_TRACE_NON_PRIMARY_AXIS = 1 << 1;
const XYFS_TRACE_HIDDEN_OR_PER_ITEM = 1 << 2;
const XYFS_TRACE_DENSITY = 1 << 3;
const XYFS_TRACE_DASHED_MARKERS = 1 << 4;
const XYFS_TRACE_RECT_GRADIENT = 1 << 5;
const XYFS_TRACE_CORNER_RADIUS = 1 << 6;
const XYFS_TRACE_WEDGE_GAP = 1 << 7;
const XYFS_TRACE_JOINED_FILL = 1 << 8;
const XYFS_TRACE_CUSTOM_HEX_REDUCE = 1 << 9;
const XYFS_TRACE_HEATMAP_COLORMAP = 1 << 10;
const XYFS_TRACE_NON_CSS_FILL = 1 << 11;
const SCENE_DASH_PRESETS = {
  solid: null,
  dashed: [6, 4],
  dotted: [1.5, 3],
  dashdot: [6, 3, 1.5, 3],
};

/** Return Rust's stable diagnostic for authored Scene feature bits. */
export function sceneSupportReason(features, requestVersion = 1) {
  if (
    typeof requestVersion !== "number"
    || !Number.isInteger(requestVersion)
    || requestVersion < 0
    || requestVersion >= 0x1_0000_0000
  ) throw new TypeError("scene support requestVersion must be a u32 integer");
  if (
    typeof features !== "bigint"
    && (typeof features !== "number" || !Number.isSafeInteger(features) || features < 0)
  ) throw new TypeError("scene support features must be an exact nonnegative u64 integer");
  const mask = BigInt(features);
  if (mask < 0n || mask > 0xffff_ffff_ffff_ffffn) throw new RangeError("scene support features must be a u64 bit mask");
  const requiredRaw = xySceneSupportReason(Number(requestVersion), mask, 0, 0n);
  if (requiredRaw === USIZE_MAX_64) throw new RangeError("invalid Scene support request version or feature mask");
  const required = Number(requiredRaw);
  if (required === 0) return "";
  const output = new Uint8Array(required);
  const written = xySceneSupportReason(Number(requestVersion), mask, u8Ptr(output), BigInt(required));
  if (Number(written) !== required) throw new Error("native Scene support predicate returned an inconsistent length");
  return new TextDecoder("utf-8", { fatal: true }).decode(output);
}

function significantSceneAxisKeys(options) {
  return Object.entries(options ?? {})
    .filter(([, value]) => {
      if (value == null || value === false) return false;
      if (Array.isArray(value) && value.length === 0) return false;
      if (typeof value === "object" && !Array.isArray(value) && Object.keys(value).length === 0) return false;
      return true;
    })
    .map(([key]) => key);
}

function packFigureSupport(figure, { colorbarUnsupported = false } = {}) {
  const chromeStyles = figure.chromeStyles ?? figure.chrome_styles ?? {};
  const annotations = [...(figure.annotations ?? [])];
  let flags = 0;
  if (figure.coords !== "cartesian") flags |= 1 << 0;
  if (Object.values(chromeStyles).some((style) => style?.fontFamily != null || style?.["font-family"] != null)) flags |= 1 << 1;
  if (
    figure.className
    || figure.class_name
    || Object.keys(figure.classNames ?? figure.class_names ?? {}).length
    || Object.keys(chromeStyles).length
    || Object.keys(figure.style ?? {}).some((key) => !["background", "--chart-bg"].includes(key))
    || annotations.some((annotation) => annotation.className || annotation.class_name)
  ) flags |= 1 << 2;
  if ((figure.traces ?? []).some((trace) => (
    trace.color_target != null
    || (
      scatterHasNonConstantColor(trace)
      && !scatterUsesDensity(trace)
    )
    || (
      fillIsGradientAuthoring(trace.style?.fill)
      && admitFillGradient(trace) == null
    )
  ))) flags |= 1 << 3;
  if (colorbarUnsupported) flags |= 1 << 4;
  if ((figure.extraLegends ?? figure.extra_legends ?? []).length) flags |= 1 << 5;
  if (annotations.some((annotation) => !["callout", "arrow", "text"].includes(annotation.kind) && annotation.text != null && annotation.text !== "")) flags |= 1 << 7;
  const traces = [...(figure.traces ?? [])];
  const axisEntries = [];
  const seenAxes = new Set();
  const addAxis = (axisId, options) => {
    if (seenAxes.has(axisId)) return;
    seenAxes.add(axisId);
    axisEntries.push([axisId, options ?? {}]);
  };
  if (figure.axis_options && typeof figure.axis_options === "object") {
    for (const [axisId, options] of Object.entries(figure.axis_options)) addAxis(axisId, options);
  }
  addAxis("x", figure.xAxis ?? figure.x_axis ?? figure.axis_options?.x ?? {});
  addAxis("y", figure.yAxis ?? figure.y_axis ?? figure.axis_options?.y ?? {});
  const parts = [new Uint8Array(20)];
  const header = new DataView(parts[0].buffer);
  parts[0].set([88, 89, 70, 83]); // XYFS
  header.setUint32(4, 2, true);
  header.setUint32(8, flags, true);
  header.setUint32(12, axisEntries.length, true);
  header.setUint32(16, traces.length, true);
  for (const [axisId, options] of axisEntries) {
    const axisCode = axisId === "x" ? 0 : axisId === "y" ? 1 : 255;
    const keys = significantSceneAxisKeys(options);
    const axis = new Uint8Array(8);
    axis[0] = axisCode;
    new DataView(axis.buffer).setUint32(4, keys.length, true);
    parts.push(axis);
    for (const key of keys) parts.push(encodeExportKey(key));
  }
  for (const trace of traces) {
    const { flags: traceFlags, kind } = figureTraceSupport(figure, trace);
    const kindBytes = new TextEncoder().encode(kind.slice(0, 32));
    const row = new Uint8Array(8 + kindBytes.length);
    const view = new DataView(row.buffer);
    view.setUint16(0, traceFlags, true);
    row[2] = kindBytes.length;
    row.set(kindBytes, 8);
    parts.push(row);
  }
  return concatBytes(parts);
}

function sceneFigureSupportReason(figure, { colorbarUnsupported = false } = {}) {
  const envelope = packFigureSupport(figure, { colorbarUnsupported });
  const requiredRaw = xySceneFigureSupportReason(
    envelope.length ? u8Ptr(envelope) : 0,
    BigInt(envelope.length),
    0,
    0n,
  );
  if (requiredRaw === USIZE_MAX_64) throw new RangeError("invalid scene figure support envelope");
  const required = Number(requiredRaw);
  if (required === 0) return "";
  const output = new Uint8Array(required);
  const written = xySceneFigureSupportReason(
    envelope.length ? u8Ptr(envelope) : 0,
    BigInt(envelope.length),
    u8Ptr(output),
    BigInt(required),
  );
  if (Number(written) !== required) throw new Error("native Scene figure support predicate returned an inconsistent length");
  return new TextDecoder("utf-8", { fatal: true }).decode(output);
}

const PUBLIC_EXPORT_KIND_CODES = {
  scatter: 0, line: 1, bar: 2, column: 3, histogram: 4, violin: 5, box: 6,
  box_whisker: 7, box_median: 8, segments: 9, errorbar: 10, stem: 11, area: 12,
  error_band: 13, ribbon: 14, triangle_mesh: 15, hexbin: 16, heatmap: 17,
  contour: 18,
};
const STYLE_KIND_CODES = { ...PUBLIC_EXPORT_KIND_CODES, contour: 18 };
const MS_LINE_ONLY = 1 << 0;
const MS_HAS_FILL = 1 << 1;
const MS_HAS_STROKE = 1 << 2;
const MS_HAS_LINE_COLOR = 1 << 3;
const MS_HAS_STROKE_WIDTH = 1 << 5;
const MS_HAS_WIDTH = 1 << 6;
const MS_HAS_LINE_WIDTH = 1 << 7;

function encodeUtf8(value) {
  return new TextEncoder().encode(String(value ?? ""));
}

function packMarkStyleRecord(trace, opacity, fillOpacity, strokeOpacity, lineOpacity, symbolCode) {
  const style = trace.style ?? {};
  let flags = 0;
  if (trace.kind === "scatter" && symbolCode >= SYMBOL_CODES.get("plus_line")) flags |= MS_LINE_ONLY;
  const parts = [];
  let fill = new Uint8Array(0);
  if (Object.hasOwn(style, "fill")) {
    let fillValue = style.fill;
    if (typeof fillValue !== "string" || String(fillValue).trim().toLowerCase().startsWith("linear-gradient(")) {
      const admitted = admitFillGradient(trace);
      if (admitted == null) throw new RangeError(`Scene v12 does not yet encode ${trace.kind} non-CSS fills`);
      fillValue = gradientSolidCss(admitted);
    }
    flags |= MS_HAS_FILL;
    fill = encodeUtf8(fillValue);
  }
  let stroke = new Uint8Array(0);
  if (Object.hasOwn(style, "stroke")) {
    flags |= MS_HAS_STROKE;
    stroke = encodeUtf8(style.stroke);
  }
  let lineColor = new Uint8Array(0);
  if (Object.hasOwn(style, "line_color") || Object.hasOwn(style, "lineColor")) {
    flags |= MS_HAS_LINE_COLOR;
    lineColor = encodeUtf8(style.line_color ?? style.lineColor);
  }
  const color = style.color
    ?? (typeof trace.color === "string" ? trace.color : trace.color?.color)
    ?? "#3987e5";
  const colorBytes = encodeUtf8(color);
  let strokeWidth = 0;
  let width = 0;
  let lineWidth = 0;
  if (Object.hasOwn(style, "stroke_width") || Object.hasOwn(style, "strokeWidth")) {
    flags |= MS_HAS_STROKE_WIDTH;
    strokeWidth = Number(style.stroke_width ?? style.strokeWidth);
  }
  if (Object.hasOwn(style, "width")) {
    flags |= MS_HAS_WIDTH;
    width = Number(style.width);
  }
  if (Object.hasOwn(style, "line_width") || Object.hasOwn(style, "lineWidth")) {
    flags |= MS_HAS_LINE_WIDTH;
    lineWidth = Number(style.line_width ?? style.lineWidth);
  }
  const prefix = new Uint8Array(52);
  const view = new DataView(prefix.buffer);
  prefix[0] = STYLE_KIND_CODES[trace.kind] ?? 255;
  prefix[1] = flags;
  view.setFloat32(4, Number(opacity), true);
  view.setFloat32(8, Number(fillOpacity), true);
  view.setFloat32(12, Number(strokeOpacity), true);
  view.setFloat32(16, Number(lineOpacity), true);
  view.setFloat64(20, strokeWidth, true);
  view.setFloat64(28, width, true);
  view.setFloat64(36, lineWidth, true);
  view.setUint16(44, fill.length, true);
  view.setUint16(46, stroke.length, true);
  view.setUint16(48, lineColor.length, true);
  view.setUint16(50, colorBytes.length, true);
  parts.push(prefix, fill, stroke, lineColor, colorBytes);
  return concatBytes(parts);
}

function resolveMarkStyle(trace, opacity, fillOpacity, strokeOpacity, lineOpacity, symbolCode) {
  const record = packMarkStyleRecord(trace, opacity, fillOpacity, strokeOpacity, lineOpacity, symbolCode);
  const envelope = new Uint8Array(16 + record.length);
  const view = new DataView(envelope.buffer);
  envelope.set(encodeUtf8("XYMS").slice(0, 4), 0);
  view.setUint32(4, 1, true);
  view.setUint32(8, 1, true);
  envelope.set(record, 16);
  const out = new Uint8Array(16);
  const code = xySceneResolveMarkStyles(u8Ptr(envelope), BigInt(envelope.length), u8Ptr(out), BigInt(out.length));
  if (code !== 1) throw new RangeError("invalid mark style envelope");
  return {
    fillRgba: Array.from(out.subarray(0, 4)),
    strokeRgba: Array.from(out.subarray(4, 8)),
    strokeWidth: new DataView(out.buffer, out.byteOffset + 8, 8).getFloat64(0, true),
  };
}

function canonicalExportKey(key) {
  return String(key).replace(/[A-Z]/g, (ch) => `_${ch.toLowerCase()}`);
}

function encodeExportKey(key) {
  const bytes = new TextEncoder().encode(canonicalExportKey(key).slice(0, 256));
  const out = new Uint8Array(2 + bytes.length);
  out[0] = bytes.length & 0xff;
  out[1] = (bytes.length >> 8) & 0xff;
  out.set(bytes, 2);
  return out;
}

function concatBytes(parts) {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}

function exportColumn(trace, name) {
  const value = trace[name];
  if (value == null) return null;
  // TypedArrays expose a `.values()` iterator; do not treat that as a column wrapper.
  if (ArrayBuffer.isView(value) || Array.isArray(value)) return value;
  return value.values ?? value;
}

function exportColumnLen(column) {
  return column == null ? 0 : column.length;
}

function exportColumnFinite(column) {
  if (column == null) return false;
  for (let index = 0; index < column.length; index += 1) {
    if (!Number.isFinite(Number(column[index]))) return false;
  }
  return true;
}

function exportArraysEqual(left, right) {
  if (left == null || right == null || left.length !== right.length) return false;
  for (let index = 0; index < left.length; index += 1) {
    if (Number(left[index]) !== Number(right[index])) return false;
  }
  return true;
}

function significantExportKeys(record) {
  return Object.entries(record ?? {})
    .filter(([, value]) => value != null && value !== false)
    .map(([key]) => key);
}

function packPublicExportSupport(figure, { width = null, height = null } = {}) {
  let flags = 0;
  if (width == null && !Number.isInteger(figure.width)) flags |= 1 << 0;
  if (height == null && !Number.isInteger(figure.height)) flags |= 1 << 1;
  const chrome = figure.chromeStyles ?? figure.chrome_styles;
  if (chrome && Object.keys(chrome).length) flags |= 1 << 2;
  const titleOptions = figure.titleOptions ?? figure.title_options;
  if (Array.isArray(titleOptions) ? titleOptions.length : titleOptions) flags |= 1 << 3;
  const styleKeys = Object.keys(figure.style ?? {});
  const legend = figure.legend ?? figure.legend_options ?? {};
  const legendKeys = Object.keys(legend);
  const colorbar = figure.colorbarOptions ?? figure.colorbar_options ?? {};
  const colorbarKeys = Object.keys(colorbar ?? {});
  const annotations = [...(figure.annotations ?? [])];
  const traces = [...(figure.traces ?? [])];
  const axisEntries = [];
  const seenAxes = new Set();
  const addAxis = (axisId, options) => {
    if (seenAxes.has(axisId)) return;
    seenAxes.add(axisId);
    axisEntries.push([axisId, options ?? {}]);
  };
  if (figure.axis_options && typeof figure.axis_options === "object") {
    for (const [axisId, options] of Object.entries(figure.axis_options)) addAxis(axisId, options);
  }
  addAxis("x", figure.xAxis ?? figure.x_axis ?? figure.axis_options?.x ?? {});
  addAxis("y", figure.yAxis ?? figure.y_axis ?? figure.axis_options?.y ?? {});

  const parts = [new Uint8Array(36)];
  const header = new DataView(parts[0].buffer);
  parts[0].set([88, 89, 69, 80]);
  header.setUint32(4, 1, true);
  header.setUint32(8, flags, true);
  header.setUint32(12, styleKeys.length, true);
  header.setUint32(16, legendKeys.length, true);
  header.setUint32(20, colorbarKeys.length, true);
  header.setUint32(24, axisEntries.length, true);
  header.setUint32(28, annotations.length, true);
  header.setUint32(32, traces.length, true);
  for (const key of styleKeys) parts.push(encodeExportKey(key));
  for (const key of legendKeys) parts.push(encodeExportKey(key));
  for (const key of colorbarKeys) parts.push(encodeExportKey(key));

  for (const [axisId, options] of axisEntries) {
    const axisCode = axisId === "x" ? 0 : axisId === "y" ? 1 : 255;
    const authored = options.type;
    const authoredCode = authored == null ? 0 : authored === "linear" ? 1 : authored === "log" ? 2 : authored === "symlog" ? 3 : 255;
    const forced = options.type ?? options.kind;
    const resolvedCode = forced === "time" ? 1 : forced === "category" ? 2 : 0;
    const domain = options.domain ?? figure._axisRange?.[axisId];
    const side = options.side;
    const sideCode = side == null ? 0 : side === "bottom" ? 1 : side === "left" ? 2 : side === "top" ? 3 : side === "right" ? 4 : 255;
    const keys = significantExportKeys(options);
    const axis = new Uint8Array(8);
    axis[0] = axisCode;
    axis[1] = resolvedCode;
    axis[2] = authoredCode;
    axis[3] = Number(domain != null);
    axis[4] = sideCode;
    axis[5] = 0;
    axis[6] = keys.length & 0xff;
    axis[7] = (keys.length >> 8) & 0xff;
    parts.push(axis);
    for (const key of keys) parts.push(encodeExportKey(key));
  }

  const annotationKinds = { text: 1, rule: 2, band: 3, marker: 4, arrow: 5, callout: 6 };
  for (const annotation of annotations) {
    if (annotation == null || typeof annotation !== "object" || Array.isArray(annotation)) {
      const row = new Uint8Array(4);
      row[1] = 1 << 4;
      parts.push(row);
      continue;
    }
    const kindCode = annotationKinds[String(annotation.kind)] ?? 0;
    let flagsAnn = 0;
    if (Object.hasOwn(annotation, "wrap")) flagsAnn |= 1 << 0;
    if (Object.hasOwn(annotation, "dx")) flagsAnn |= 1 << 1;
    if (Object.hasOwn(annotation, "dy")) flagsAnn |= 1 << 2;
    if (Object.hasOwn(annotation, "anchor")) flagsAnn |= 1 << 3;
    const fields = Object.keys(annotation);
    const row = new Uint8Array(4);
    row[0] = kindCode;
    row[1] = flagsAnn;
    row[2] = fields.length & 0xff;
    row[3] = (fields.length >> 8) & 0xff;
    parts.push(row);
    for (const key of fields) parts.push(encodeExportKey(key));
  }

  for (const [traceIndex, trace] of traces.entries()) {
    const style = trace.style ?? {};
    const opacity = Number(style.opacity ?? 1);
    if (!Number.isFinite(opacity) || opacity < 0 || opacity > 1) {
      throw new RangeError("trace opacity must be finite and in [0, 1]");
    }
    const kindCode = PUBLIC_EXPORT_KIND_CODES[trace.kind] ?? 255;
    const step = { pre: 1, mid: 2, post: 3 }[style.step] ?? 0;
    const prev = traceIndex ? traces[traceIndex - 1] : null;
    const prev2 = traceIndex >= 2 ? traces[traceIndex - 2] : null;
    const prev3 = traceIndex >= 3 ? traces[traceIndex - 3] : null;
    const xv = exportColumn(trace, "x");
    const yv = exportColumn(trace, "y");
    const x0 = exportColumn(trace, "x0");
    const y0 = exportColumn(trace, "y0");
    const x1 = exportColumn(trace, "x1");
    const y1 = exportColumn(trace, "y1");
    const mesh = [x0, y0, x1, y1, xv, yv];
    let flagsTr = 0;
    if (xv != null) flagsTr |= 1 << 0;
    if (yv != null) flagsTr |= 1 << 1;
    if (xv != null && yv != null && exportColumnLen(xv) === exportColumnLen(yv)) flagsTr |= 1 << 2;
    if (exportColumnFinite(xv)) flagsTr |= 1 << 3;
    if (exportColumnFinite(yv)) flagsTr |= 1 << 4;
    if (x0 != null && y0 != null && x1 != null && y1 != null) {
      flagsTr |= 1 << 5;
      const lengths = new Set([exportColumnLen(x0), exportColumnLen(y0), exportColumnLen(x1), exportColumnLen(y1)]);
      if (lengths.size === 1) flagsTr |= 1 << 6;
    }
    if (mesh.every((column) => column != null)) {
      flagsTr |= 1 << 7;
      const meshLengths = new Set(mesh.map(exportColumnLen));
      if (meshLengths.size === 1) flagsTr |= 1 << 8;
      if (mesh.every(exportColumnFinite)) flagsTr |= 1 << 9;
    }
    if (style.joined_fill || style.joinedFill) flagsTr |= 1 << 10;
    let heatmapRows = 0, heatmapCols = 0, heatmapValues = 0;
    if (trace.kind === "heatmap") {
      if (style.truecolor || style.colormap != null || trace.rgba_grid != null || trace.rgba != null) {
        if (!heatmapTessellatesCellFills(trace)) {
          flagsTr |= 1 << 11;
        }
      }
      const shape = trace.grid_shape ?? trace.gridShape;
      const grid = exportColumn(trace, "grid");
      const hx = xv, hy = yv;
      if (Array.isArray(shape) && shape.length === 2) {
        const rows = Number(shape[0]), cols = Number(shape[1]);
        if (Number.isInteger(rows) && Number.isInteger(cols) && rows >= 1 && cols >= 1) {
          heatmapRows = rows;
          heatmapCols = cols;
          flagsTr |= 1 << 12;
          if (grid != null) heatmapValues = grid.length;
          if (
            hx != null && hy != null && hx.length === 2 && hy.length === 2
            && [hx[0], hx[1], hy[0], hy[1]].every((value) => Number.isFinite(Number(value)))
            && Number(hx[0]) < Number(hx[1]) && Number(hy[0]) < Number(hy[1])
          ) flagsTr |= 1 << 13;
          if (grid != null && exportColumnFinite(grid)) flagsTr |= 1 << 14;
        }
      }
    }
    if (xv != null && yv != null && exportColumnLen(xv) === exportColumnLen(yv)) flagsTr |= 1 << 15;
    if (exportColumnFinite(xv) && exportColumnFinite(yv)) flagsTr |= 1 << 16;
    if ((style.stroke_width ?? style.strokeWidth) != null && style.stroke == null) flagsTr |= 1 << 17;
    const prevX1 = prev && exportColumn(prev, "x1");
    const prevY1 = prev && exportColumn(prev, "y1");
    if (prev != null && xv != null && yv != null && prevX1 != null && prevY1 != null && exportArraysEqual(xv, prevX1) && exportArraysEqual(yv, prevY1)) {
      flagsTr |= 1 << 18;
    }
    if (prev != null && (trace.x_axis ?? "x") === (prev.x_axis ?? "x") && (trace.y_axis ?? "y") === (prev.y_axis ?? "y")) {
      flagsTr |= 1 << 19;
    }
    if (exportColumnFinite(xv) && exportColumnFinite(yv)) flagsTr |= 1 << 20;
    let symbol = style.symbol ?? "circle";
    if (typeof symbol !== "string") {
      flagsTr |= 1 << 21;
      symbol = "";
    }
    if (
      trace.kind === "scatter"
      && (figure.coords ?? "cartesian") === "cartesian"
      && shouldUseDensity(trace.x?.length ?? 0, {
        forceDensity: Boolean(trace.force_density ?? trace.forceDensity),
        forceDirect: Boolean(trace.force_direct ?? trace.forceDirect),
        coords: "cartesian",
        perItemChannels: style.color_channel != null
          || style.size_channel != null
          || style.stroke_channel != null
          || trace.color_ch != null
          || trace.size_ch != null
          || trace.stroke_ch != null,
      })
    ) {
      flagsTr |= 1 << 22;
    }
    const role = style.role == null ? "" : String(style.role);
    const reduce = style.reduce == null ? "" : String(style.reduce);
    let hexDx = Number.NaN, hexDy = Number.NaN;
    if (trace.kind === "hexbin") {
      hexDx = Number(style.hex_dx ?? style.hexDx ?? style.dx);
      hexDy = Number(style.hex_dy ?? style.hexDy ?? style.dy);
    }
    const styleKeysTrace = Object.entries(style).filter(([, value]) => value != null).map(([key]) => key);
    const roleBytes = new TextEncoder().encode(role);
    const symbolBytes = new TextEncoder().encode(symbol);
    const reduceBytes = new TextEncoder().encode(reduce);
    const nMesh = (flagsTr & (1 << 7)) ? exportColumnLen(xv) : 0;
    const row = new Uint8Array(72);
    const view = new DataView(row.buffer);
    row[0] = kindCode;
    row[1] = step;
    row[2] = prev == null ? 255 : (PUBLIC_EXPORT_KIND_CODES[prev.kind] ?? 255);
    row[3] = prev2 == null ? 255 : (PUBLIC_EXPORT_KIND_CODES[prev2.kind] ?? 255);
    row[4] = prev3 == null ? 255 : (PUBLIC_EXPORT_KIND_CODES[prev3.kind] ?? 255);
    view.setUint32(8, flagsTr, true);
    view.setUint32(12, xv != null ? exportColumnLen(xv) : nMesh, true);
    view.setUint32(16, exportColumnLen(yv), true);
    view.setUint32(20, exportColumnLen(x0), true);
    view.setUint32(24, exportColumnLen(y0), true);
    view.setUint32(28, exportColumnLen(x1), true);
    view.setUint32(32, exportColumnLen(y1), true);
    view.setUint32(36, heatmapRows, true);
    view.setUint32(40, heatmapCols, true);
    view.setUint32(44, heatmapValues, true);
    view.setUint16(48, styleKeysTrace.length, true);
    view.setUint16(50, roleBytes.length, true);
    view.setUint16(52, symbolBytes.length, true);
    view.setUint16(54, reduceBytes.length, true);
    view.setFloat64(56, hexDx, true);
    view.setFloat64(64, hexDy, true);
    parts.push(row, roleBytes, symbolBytes, reduceBytes);
    for (const key of styleKeysTrace) parts.push(encodeExportKey(key));
  }
  return concatBytes(parts);
}

/** Return Rust's public-export diagnostic, or null when the Scene route applies. */
export function sceneExportSupportReason(figure, { width = null, height = null } = {}) {
  const envelope = packPublicExportSupport(figure, { width, height });
  const requiredRaw = xyScenePublicExportReason(u8Ptr(envelope), BigInt(envelope.length), 0, 0n);
  if (requiredRaw === USIZE_MAX_64) throw new RangeError("invalid scene public export support envelope");
  const required = Number(requiredRaw);
  let reason = "";
  if (required !== 0) {
    const output = new Uint8Array(required);
    const written = xyScenePublicExportReason(u8Ptr(envelope), BigInt(envelope.length), u8Ptr(output), BigInt(required));
    if (Number(written) !== required) throw new Error("native Scene public export predicate returned an inconsistent length");
    reason = new TextDecoder("utf-8", { fatal: true }).decode(output);
  }
  if (reason) return reason;
  let publicTriangleMeshCount = 0;
  for (const trace of figure.traces ?? []) {
    if (POLYFILL_KINDS.has(trace.kind)) {
      const mesh = [trace.x0, trace.y0, trace.x1, trace.y1, trace.x, trace.y];
      if (mesh.every((column) => column != null)) publicTriangleMeshCount += mesh[0].length;
    } else if (HEXBIN_KINDS.has(trace.kind) && trace.x != null) {
      publicTriangleMeshCount += trace.x.length;
    }
  }
  let scene;
  try {
    scene = figureSceneV3(figure);
  } catch (err) {
    if (err instanceof RangeError) {
      if (err.message === "invalid canonical scene plot layout") return "XYG_SCENE_UNSUPPORTED_VIEWPORT";
      return err.message;
    }
    throw err;
  }
  if (publicTriangleMeshCount) {
    try {
      sceneBrowserPainter(scene);
    } catch (err) {
      if (err instanceof RangeError && err.message === "invalid canonical scene for browser painter") {
        return "XYG_SCENE_UNSUPPORTED_PUBLIC_TRIANGLE_MESH";
      }
      throw err;
    }
  }
  return null;
}

const LEGEND_LOCATIONS = new Map([["upper right", 0], ["upper left", 1], ["lower left", 2], ["lower right", 3], ["center right", 4], ["center left", 5], ["upper center", 6], ["lower center", 7], ["center", 8]]);

function legendColumnValues(column) {
  if (column == null) return null;
  if (ArrayBuffer.isView(column) || Array.isArray(column)) return asF64Array(column);
  if (column.values != null && typeof column.values !== "function") return asF64Array(column.values);
  return null;
}

function legendAxisSpec(figure, axisId) {
  const options = figure.axis_options?.[axisId] ?? figure[`${axisId}Axis`] ?? figure[`${axisId}_axis`] ?? {};
  let lo, hi;
  try {
    [lo, hi] = figure._range(axisId);
  } catch {
    return null;
  }
  const reverse = lo > hi;
  if (reverse) [lo, hi] = [hi, lo];
  if (!(Number.isFinite(lo) && Number.isFinite(hi)) || hi <= lo) return null;
  const scale = options.type ?? options.scale ?? options.kind ?? "linear";
  const constant = options.constant == null || Number(options.constant) === 0 ? 1 : Number(options.constant);
  return { domain: [lo, hi], reverse, scale, constant };
}

function resolveLegendBestLoc(figure) {
  const series = [];
  const labelLens = [];
  for (const trace of figure.traces ?? []) {
    if (trace.hidden) continue;
    if (trace.name != null && String(trace.name).length > 0) labelLens.push(String(trace.name).length);
    const xv = legendColumnValues(trace.x);
    const yv = legendColumnValues(trace.y);
    if (xv == null || yv == null || xv.length !== yv.length) continue;
    const xSpec = legendAxisSpec(figure, trace.x_axis ?? "x");
    const ySpec = legendAxisSpec(figure, trace.y_axis ?? "y");
    if (xSpec == null || ySpec == null) continue;
    const projected = legendNormalize(xv, yv, {
      xDomain: xSpec.domain,
      yDomain: ySpec.domain,
      xReverse: xSpec.reverse,
      yReverse: ySpec.reverse,
      xScale: xSpec.scale,
      yScale: ySpec.scale,
      xConstant: xSpec.constant,
      yConstant: ySpec.constant,
    });
    if (projected != null) series.push(projected);
  }
  return legendBestLoc(series, labelLens);
}

function legendInput(figure, entries, styles) {
  if (figure.showLegend === false || entries.length === 0) return new Uint8Array();
  const options = figure.legend ?? {};
  const allowed = new Set(["loc", "title", "ncols", "style", "highlight", "toggle"]);
  if (Object.keys(options).some((key) => !allowed.has(key)) || Number(options.ncols ?? 1) !== 1) throw new RangeError("Scene v12 primary legends do not yet encode anchors, multiple columns, or custom content");
  if (["toggle", "highlight"].some((key) => Object.hasOwn(options, key) && options[key] !== false)) throw new RangeError("Scene v12 primary legends are static; toggle and highlight must be false");
  const authoredLoc = options.loc;
  let loc = authoredLoc ?? "upper right";
  if (loc === "best") loc = resolveLegendBestLoc(figure);
  if (!LEGEND_LOCATIONS.has(loc)) throw new RangeError(`Scene v12 does not support legend location ${JSON.stringify(loc)}`);
  const style = options.style ?? {};
  const allowedStyle = new Set(["background", "color", "font_size", "fontSize", "title_font_size", "titleFontSize"]);
  if (Object.keys(style).some((key) => !allowedStyle.has(key))) throw new RangeError("Scene v12 legends support only background, color, font_size, and title_font_size");
  const authoredFontSize = style.font_size ?? style.fontSize, authoredTitleFontSize = style.title_font_size ?? style.titleFontSize;
  const fontSize = authoredFontSize == null ? 0 : Number(authoredFontSize), titleFontSize = authoredTitleFontSize == null ? 0 : Number(authoredTitleFontSize);
  if (!((authoredFontSize == null || (fontSize >= 1 && fontSize <= 1000)) && (authoredTitleFontSize == null || (titleFontSize >= 1 && titleFontSize <= 1000)))) throw new RangeError("legend font sizes must be finite and in [1, 1000]");
  const encoder = new TextEncoder(), title = encoder.encode(String(options.title ?? "")), labels = entries.map((entry) => encoder.encode(entry.label));
  const textLength = title.length + labels.reduce((sum, label) => sum + label.length, 0);
  if (entries.length > 128 || title.length > 4096 || textLength > 16384 || labels.some((label) => label.length === 0 || label.length > 4096)) throw new RangeError("Scene v12 legend text exceeds its bounded UTF-8 limits");
  const flags = Number(authoredLoc != null) | (Number(authoredFontSize != null) << 1) | (Number(authoredTitleFontSize != null) << 2) | (Number(Object.hasOwn(style, "color")) << 3) | (Number(Object.hasOwn(style, "background")) << 4);
  const textRgba = Object.hasOwn(style, "color") ? rgba8(style.color, 1, "legend color") : new Uint8Array(4);
  const frameFill = Object.hasOwn(style, "background") ? rgba8(style.background, 1, "legend background") : new Uint8Array(4);
  const meta = new Uint8Array(entries.length * 16);
  const metaView = new DataView(meta.buffer);
  const concatenated = new Uint8Array(textLength - title.length);
  const labelLens = new Uint32Array(entries.length);
  let labelAt = 0;
  for (const [index, entry] of entries.entries()) {
    const paint = styles[entry.styleRef];
    const offset = index * 16;
    metaView.setUint32(offset, entry.styleRef, true);
    meta[offset + 4] = entry.kind;
    meta[offset + 5] = entry.symbol;
    meta.set(paint.fillRgba, offset + 8);
    meta.set(paint.strokeRgba, offset + 12);
    const label = labels[index];
    labelLens[index] = label.length;
    concatenated.set(label, labelAt);
    labelAt += label.length;
  }
  const out = new Uint8Array(48 + entries.length * 24 + textLength);
  const code = xyScenePackLegend(
    LEGEND_LOCATIONS.get(loc),
    flags,
    fontSize,
    titleFontSize,
    u8Ptr(textRgba),
    u8Ptr(frameFill),
    title.length ? u8Ptr(title) : 0,
    BigInt(title.length),
    entries.length,
    meta.length ? u8Ptr(meta) : 0,
    BigInt(meta.length),
    u32Ptr(labelLens),
    concatenated.length ? u8Ptr(concatenated) : 0,
    BigInt(concatenated.length),
    u8Ptr(out),
    BigInt(out.length),
  );
  if (code === -5) throw new RangeError("legend font sizes must be finite and in [1, 1000]");
  if (code < 0) throw new RangeError("invalid scene legend packing");
  return out.subarray(0, code);
}

function colorbarInput(figure) {
  const options = figure.colorbarOptions ?? figure.colorbar_options;
  if (options == null) return new Uint8Array();
  if (typeof options !== "object" || Array.isArray(options)) throw new RangeError("Scene v19 colorbar requires literal RGBA stops");
  const allowed = new Set(["domain", "stops", "side", "title", "text_rgba", "ticks", "minor_ticks"]);
  if (Object.keys(options).some((key) => !allowed.has(key))) throw new RangeError("Scene v19 colorbar requires bounded literal RGBA stops");
  const domain = options.domain, stops = options.stops;
  if (!Array.isArray(domain) || domain.length !== 2 || !Array.isArray(stops) || stops.length < 2 || stops.length > 16) throw new RangeError("Scene v19 colorbar requires a domain and 2–16 stops");
  const lo = Number(domain[0]), hi = Number(domain[1]);
  const title = options.title ?? "";
  if (typeof title !== "string") throw new TypeError("Scene v19 colorbar title must be a string");
  const titleBytes = new TextEncoder().encode(title), text = asUnsignedArray(options.text_rgba ?? [32, 32, 32, 255], "colorbar text_rgba", 255, Uint8Array);
  requireLength(text, 4, "colorbar text_rgba"); if (titleBytes.length > 4096) throw new RangeError("Scene v19 colorbar title is limited to 4,096 UTF-8 bytes");
  const rawTicks = options.ticks;
  if (rawTicks != null && (!Array.isArray(rawTicks) || rawTicks.length > 32)) throw new RangeError("Scene v19 colorbar ticks are limited to 32 finite ordered values");
  const ticks = rawTicks == null ? [] : rawTicks.map(Number);
  const minorTicks = options.minor_ticks ?? false;
  if (typeof minorTicks !== "boolean") throw new TypeError("Scene v19 colorbar minor_ticks must be a boolean");
  const side = options.side ?? "right"; if (side !== "right" && side !== "bottom") throw new RangeError("Scene v19 colorbar side is right or bottom");
  const stopValues = new Float64Array(stops.length);
  const stopRgba = new Uint8Array(stops.length * 4);
  for (const [index, stop] of stops.entries()) {
    if (!Array.isArray(stop) || stop.length !== 2) throw new TypeError("colorbar stops are [value, RGBA]");
    stopValues[index] = Number(stop[0]);
    const rgba = asUnsignedArray(stop[1], `colorbar stops[${index}]`, 255, Uint8Array);
    requireLength(rgba, 4, `colorbar stops[${index}]`);
    stopRgba.set(rgba, index * 4);
  }
  const tickValues = Float64Array.from(ticks);
  const out = new Uint8Array(56 + stops.length * 12 + ticks.length * 8 + titleBytes.length);
  const code = xyScenePackColorbar(
    Number(side === "bottom") | (Number(minorTicks) << 2),
    lo,
    hi,
    u8Ptr(text),
    titleBytes.length ? u8Ptr(titleBytes) : 0,
    BigInt(titleBytes.length),
    stops.length,
    f64Ptr(stopValues),
    u8Ptr(stopRgba),
    BigInt(stopRgba.length),
    ticks.length,
    ticks.length ? f64Ptr(tickValues) : 0,
    u8Ptr(out),
    BigInt(out.length),
  );
  if (code === -5) throw new RangeError("Scene v19 colorbar domain must be finite and ordered");
  if (code === -6) throw new RangeError("colorbar stops must span the domain");
  if (code === -7) throw new RangeError("Scene v19 colorbar ticks are limited to 32 finite ordered values");
  if (code < 0) throw new RangeError("invalid scene colorbar packing");
  return out.subarray(0, code);
}

const MAX_SCENE_ANNOTATION_INPUT_BYTES = 28
  + 12 + 128 * 40 + 4096
  + 12 + 128 * 32 + 4096
  + 12 + 128 * 60
  + 12 + 128 * 76 + 8192
  + 12 + 128 * 68 + 8192;

function packAnnotationEnvelope({ texts, attached, arrows, callouts, wrapped }) {
  if (!texts.length && !attached.length && !arrows.length && !callouts.length && !wrapped.length) {
    return new Uint8Array();
  }
  const textMeta = new Uint8Array(texts.length * 40);
  const textView = new DataView(textMeta.buffer);
  const textLens = new Uint32Array(texts.length);
  texts.forEach((row, index) => {
    const at = index * 40;
    textView.setFloat64(at, row.x, true);
    textView.setFloat64(at + 8, row.y, true);
    textMeta.set(row.rgba, at + 16);
    textMeta.set(row.labelFill ?? [0, 0, 0, 0], at + 20);
    textMeta.set(row.labelBorder?.rgba ?? [0, 0, 0, 0], at + 24);
    textView.setFloat64(at + 28, row.labelBorder?.width ?? 0, true);
    textMeta[at + 36] = (row.labelFill ? 1 : 0) | (row.labelBorder ? 2 : 0);
    textLens[index] = row.text.length;
  });
  const textBytes = concatBytes(texts.map((row) => row.text));
  const attachedMeta = new Uint8Array(attached.length * 32);
  const attachedView = new DataView(attachedMeta.buffer);
  const attachedLens = new Uint32Array(attached.length);
  attached.forEach((row, index) => {
    const at = index * 32;
    attachedView.setBigUint64(at, row.stableId, true);
    attachedMeta.set(row.rgba, at + 8);
    attachedMeta.set(row.labelFill ?? [0, 0, 0, 0], at + 12);
    attachedMeta.set(row.labelBorder?.rgba ?? [0, 0, 0, 0], at + 16);
    attachedView.setFloat64(at + 20, row.labelBorder?.width ?? 0, true);
    attachedMeta[at + 28] = (row.labelFill ? 1 : 0) | (row.labelBorder ? 2 : 0);
    attachedLens[index] = row.text.length;
  });
  const attachedBytes = concatBytes(attached.map((row) => row.text));
  const arrowMeta = new Uint8Array(arrows.length * 60);
  const arrowView = new DataView(arrowMeta.buffer);
  arrows.forEach((row, index) => {
    const at = index * 60;
    arrowView.setBigUint64(at, row.stableId, true);
    arrowView.setFloat64(at + 8, row.x0, true);
    arrowView.setFloat64(at + 16, row.y0, true);
    arrowView.setFloat64(at + 24, row.x1, true);
    arrowView.setFloat64(at + 32, row.y1, true);
    arrowMeta.set(row.rgba, at + 40);
    arrowView.setFloat64(at + 44, row.opacity, true);
    arrowView.setFloat64(at + 52, row.width, true);
  });
  const calloutMeta = new Uint8Array(callouts.length * 76);
  const calloutView = new DataView(calloutMeta.buffer);
  const calloutLens = new Uint32Array(callouts.length);
  callouts.forEach((row, index) => {
    const at = index * 76;
    calloutView.setFloat64(at, row.x, true);
    calloutView.setFloat64(at + 8, row.y, true);
    calloutView.setFloat64(at + 16, row.dx, true);
    calloutView.setFloat64(at + 24, row.dy, true);
    calloutMeta.set(row.rgba, at + 32);
    calloutView.setFloat64(at + 36, row.opacity, true);
    calloutView.setFloat64(at + 44, row.width, true);
    calloutMeta[at + 52] = row.anchorCode;
    calloutMeta.set(row.labelFill ?? [0, 0, 0, 0], at + 56);
    calloutMeta.set(row.labelBorder?.rgba ?? [0, 0, 0, 0], at + 60);
    calloutView.setFloat64(at + 64, row.labelBorder?.width ?? 0, true);
    calloutMeta[at + 72] = (row.labelFill ? 1 : 0) | (row.labelBorder ? 2 : 0);
    calloutLens[index] = row.text.length;
  });
  const calloutBytes = concatBytes(callouts.map((row) => row.text));
  const wrappedMeta = new Uint8Array(wrapped.length * 64);
  const wrappedView = new DataView(wrappedMeta.buffer);
  const wrappedLens = new Uint32Array(wrapped.length);
  wrapped.forEach((row, index) => {
    const at = index * 64;
    wrappedView.setFloat64(at, row.x, true);
    wrappedView.setFloat64(at + 8, row.y, true);
    wrappedView.setFloat64(at + 16, row.dx, true);
    wrappedView.setFloat64(at + 24, row.dy, true);
    wrappedView.setFloat64(at + 32, row.wrap, true);
    wrappedMeta.set(rgba8(annotationColor(row.a.style ?? {}, "color", row.a.kind === "callout" ? "#344054" : "#667085", "wrapped color"), row.opacity, "wrapped"), at + 40);
    wrappedMeta.set(row.fill, at + 44);
    wrappedMeta.set(row.border?.rgba ?? [0, 0, 0, 0], at + 48);
    wrappedView.setFloat64(at + 52, row.border?.width ?? 0, true);
    wrappedMeta[at + 60] = row.a.kind === "callout" ? 1 : 0;
    wrappedMeta[at + 61] = row.anchor;
    wrappedLens[index] = row.text.length;
  });
  const wrappedBytes = concatBytes(wrapped.map((row) => row.text));
  const out = new Uint8Array(MAX_SCENE_ANNOTATION_INPUT_BYTES);
  const code = xyScenePackAnnotations(
    texts.length, textMeta.length ? u8Ptr(textMeta) : 0, BigInt(textMeta.length),
    texts.length ? u32Ptr(textLens) : 0, textBytes.length ? u8Ptr(textBytes) : 0, BigInt(textBytes.length),
    attached.length, attachedMeta.length ? u8Ptr(attachedMeta) : 0, BigInt(attachedMeta.length),
    attached.length ? u32Ptr(attachedLens) : 0, attachedBytes.length ? u8Ptr(attachedBytes) : 0, BigInt(attachedBytes.length),
    arrows.length, arrowMeta.length ? u8Ptr(arrowMeta) : 0, BigInt(arrowMeta.length),
    callouts.length, calloutMeta.length ? u8Ptr(calloutMeta) : 0, BigInt(calloutMeta.length),
    callouts.length ? u32Ptr(calloutLens) : 0, calloutBytes.length ? u8Ptr(calloutBytes) : 0, BigInt(calloutBytes.length),
    wrapped.length, wrappedMeta.length ? u8Ptr(wrappedMeta) : 0, BigInt(wrappedMeta.length),
    wrapped.length ? u32Ptr(wrappedLens) : 0, wrappedBytes.length ? u8Ptr(wrappedBytes) : 0, BigInt(wrappedBytes.length),
    u8Ptr(out), BigInt(out.length),
  );
  if (code === -5) throw new RangeError("Scene annotation geometry must be finite");
  if (code === -6) throw new RangeError("Scene annotations require nonempty NUL-free text");
  if (code === -7) throw new RangeError("Scene v23 label border requires label_background");
  if (code < 0) throw new RangeError("invalid scene annotation packing");
  return out.subarray(0, code);
}

function scatterHasNonConstantColor(trace) {
  const style = trace.style ?? {};
  if (style.color_channel != null) return true;
  const color = trace.color_ch ?? trace.colorChannel ?? trace.color;
  if (color == null || typeof color !== "object") return false;
  return color.mode !== "constant" || (color.color == null && color.constant == null);
}

function scatterHasDroppedPerItem(trace) {
  const style = trace.style ?? {};
  return Boolean(
    style.size_channel
    || style.stroke_channel
    || trace.size_ch
    || trace.stroke_ch
  );
}

function scatterUsesDensity(trace) {
  if ((trace.kind ?? "scatter") !== "scatter") return false;
  return shouldUseDensity(trace.x?.length ?? 0, {
    forceDensity: Boolean(trace.force_density ?? trace.forceDensity),
    forceDirect: Boolean(trace.force_direct ?? trace.forceDirect),
    coords: "cartesian",
    perItemChannels: scatterHasNonConstantColor(trace) || scatterHasDroppedPerItem(trace),
  });
}

function colormapLutRgba8(name) {
  const stopBytes = colormapNamedStops(name ?? "viridis");
  const n = stopBytes.length / 3;
  const lut = new Uint8Array(256 * 4);
  for (let i = 0; i < 256; i++) {
    const pos = n <= 1 ? 0 : (i / 255) * (n - 1);
    const lo = Math.floor(pos);
    const hi = Math.min(n - 1, lo + 1);
    const frac = pos - lo;
    for (let channel = 0; channel < 3; channel++) {
      const start = stopBytes[lo * 3 + channel];
      lut[i * 4 + channel] = Math.round(start + (stopBytes[hi * 3 + channel] - start) * frac);
    }
    lut[i * 4 + 3] = 255;
  }
  return lut;
}

function resolveDensityBinColors(trace) {
  const color = trace.color_ch ?? trace.colorChannel ?? trace.color ?? trace.style?.color_channel;
  if (color == null || typeof color !== "object") return null;
  if (color.mode === "direct_rgba" && color.rgba != null) {
    return { rgba: color.rgba instanceof Uint8Array ? color.rgba : Uint8Array.from(color.rgba) };
  }
  if (color.mode === "continuous" && color.values != null) {
    const values = color.values;
    const domain = color.domain ?? [0, 1];
    const lo = Number(domain[0]);
    const hi = Number(domain[1]);
    const span = hi - lo;
    const idx = new Uint8Array(values.length);
    for (let i = 0; i < values.length; i++) {
      const t = span === 0 ? 0 : (Number(values[i]) - lo) / span;
      idx[i] = Math.round(Math.min(1, Math.max(0, t)) * 255);
    }
    return { idx, lut: colormapLutRgba8(color.colormap ?? "viridis") };
  }
  return null;
}

function rectExtraFlags(style) {
  let flags = 0;
  if (style.fill != null && typeof style.fill === "object" && admitFillGradient({ style }) == null) flags |= XYFS_TRACE_RECT_GRADIENT;
  const radius = style.corner_radius ?? 0;
  if (Array.isArray(radius)) {
    if (radius.some((value) => Number(value) !== 0)) flags |= XYFS_TRACE_CORNER_RADIUS;
  } else if (Number(radius) !== 0) {
    flags |= XYFS_TRACE_CORNER_RADIUS;
  }
  if (Number(style.wedge_gap ?? 0) !== 0) flags |= XYFS_TRACE_WEDGE_GAP;
  return flags;
}

function figureTraceSupport(figure, trace) {
  const style = trace.style ?? {};
  const kind = String(trace.kind ?? "mark");
  let flags = 0;
  if (!SUPPORTED_KINDS.has(kind)) flags |= XYFS_TRACE_UNSUPPORTED_KIND;
  if ((trace.x_axis ?? "x") !== "x" || (trace.y_axis ?? "y") !== "y") flags |= XYFS_TRACE_NON_PRIMARY_AXIS;
  if (
    trace.hidden
    || scatterHasDroppedPerItem(trace)
    || (scatterHasNonConstantColor(trace) && !scatterUsesDensity(trace))
  ) flags |= XYFS_TRACE_HIDDEN_OR_PER_ITEM;
  if (style.marker_glyph != null) flags |= XYFS_TRACE_DASHED_MARKERS;
  if (style.marker_path != null) {
    if (kind !== "scatter") flags |= XYFS_TRACE_DASHED_MARKERS;
    else {
      const validated = validateMarkerPath(style.marker_path);
      if (validated == null || (validated.filled && validated.contours.some((contour) => contour.length < 6))) {
        flags |= XYFS_TRACE_DASHED_MARKERS;
      }
    }
  }
  if (style.smooth != null) flags |= XYFS_TRACE_DASHED_MARKERS;
  const curve = style.curve;
  if (curve != null) {
    const curveName = String(curve).trim().toLowerCase();
    if (curveName === "smooth") {
      if ((kind !== "line" && kind !== "area" && kind !== "error_band") || style.step != null) flags |= XYFS_TRACE_DASHED_MARKERS;
    } else if (curveName !== "linear") {
      flags |= XYFS_TRACE_DASHED_MARKERS;
    }
  }
  const linecap = style.linecap ?? style.lineCap;
  if (linecap != null && !["butt", "round", "square"].includes(String(linecap).trim().toLowerCase())) {
    flags |= XYFS_TRACE_DASHED_MARKERS;
  }
  if (style.dash != null && parseSceneDash(style.dash) === false) flags |= XYFS_TRACE_DASHED_MARKERS;
  if (RECT_KINDS.has(kind) || HEATMAP_KINDS.has(kind)) flags |= rectExtraFlags(style);
  if (POLYFILL_KINDS.has(kind) && style.joined_fill) flags |= XYFS_TRACE_JOINED_FILL;
  if (HEXBIN_KINDS.has(kind) && !HEXBIN_REDUCES.has(style.reduce)) flags |= XYFS_TRACE_CUSTOM_HEX_REDUCE;
  if (
    HEATMAP_KINDS.has(kind)
    && (style.truecolor || style.colormap != null || trace.rgba_grid != null || trace.rgba != null)
    && !heatmapTessellatesCellFills(trace)
  ) flags |= XYFS_TRACE_HEATMAP_COLORMAP;
  if (Object.hasOwn(style, "fill") && typeof style.fill !== "string") {
    if (admitFillGradient(trace) == null) flags |= XYFS_TRACE_NON_CSS_FILL;
  }
  return { flags, kind };
}

function heatmapTessellatesCellFills(trace) {
  const style = trace.style ?? {};
  if (trace.rgba_grid != null) return true;
  if (style.truecolor) return false;
  return style.colormap != null
    || style.colormapStops != null
    || trace.colormapStops != null
    || trace.rgba != null;
}

/** Compile migrated cartesian marks to Scene v12. */
export function figureSceneV3(figure, { margins = null } = {}) {
  let encodedColorbar = new Uint8Array(), colorbarUnsupported = false;
  try { encodedColorbar = colorbarInput(figure); } catch { colorbarUnsupported = Boolean(figure.colorbarOptions ?? figure.colorbar_options); }
  const reason = sceneFigureSupportReason(figure, { colorbarUnsupported });
  if (reason) throw new RangeError(reason);
  const kinds = [], stableIds = [], styleRefs = [], diameter = [], symbols = [], expansionModes = [], x0 = [], y0 = [], x1 = [], y1 = [], styles = [], dashes = [], linecaps = [], markerPaths = [], fillGradients = [], legendEntries = [], heatmapPaintPlanes = [];
  const xDomain = figure._range("x");
  const yDomain = figure._range("y");
  const sceneAxis = (axis, id, domain) => {
    const options = figure[`${axis}Axis`] ?? figure[`${axis}_axis`] ?? {};
    return {
      id,
      kind: options.kind ?? options.type ?? "linear",
      domain,
      constant: options.constant ?? 1,
      nonpositive: options.nonpositive ?? "clip",
      format: options.format ?? null,
    };
  };
  const xSceneAxis = sceneAxis("x", 1, xDomain);
  const ySceneAxis = sceneAxis("y", 2, yDomain);
  const xSceneDescriptor = axisDescriptor(xSceneAxis, "xAxis");
  const ySceneDescriptor = axisDescriptor(ySceneAxis, "yAxis");
  for (const trace of figure.traces) {
    const style = trace.style ?? {};
    const opacity = Number(style.opacity ?? 1);
    if (!Number.isFinite(opacity) || opacity < 0 || opacity > 1) throw new RangeError("trace opacity must be in [0, 1]");
    const fillOpacity = BAND_KINDS.has(trace.kind) || RIBBON_KINDS.has(trace.kind) ? Number(style.fill_opacity ?? 1) : 1;
    const strokeOpacity = BAND_KINDS.has(trace.kind) || RIBBON_KINDS.has(trace.kind) ? Number(style.stroke_opacity ?? 1) : 1;
    const lineOpacity = BAND_KINDS.has(trace.kind) ? Number(style.line_opacity ?? 1) : 1;
    if ((BAND_KINDS.has(trace.kind) || RIBBON_KINDS.has(trace.kind)) && [fillOpacity, strokeOpacity, lineOpacity].some((value) => !Number.isFinite(value) || value < 0 || value > 1)) {
      throw new RangeError("trace opacity channels must be in [0, 1]");
    }
    const symbolCode = sceneSymbolCode(style.symbol ?? 0);
    styles.push(resolveMarkStyle(trace, opacity, fillOpacity, strokeOpacity, lineOpacity, symbolCode));
    const parsedDash = parseSceneDash(style.dash);
    dashes.push(parsedDash === false ? null : parsedDash);
    const parsedCap = parseSceneLinecap(style.linecap ?? style.lineCap);
    linecaps.push(parsedCap === false ? null : parsedCap);
    let markerPath = null;
    if (trace.kind === "scatter" && style.marker_path != null) {
      markerPath = validateMarkerPath(style.marker_path);
      if (markerPath && markerPath.filled && markerPath.contours.some((contour) => contour.length < 6)) {
        markerPath = null;
      }
    }
    markerPaths.push(markerPath);
    fillGradients.push(admitFillGradient(trace));
    const styleRef = styles.length - 1;
    if (trace.name != null && String(trace.name).length > 0 && figure.showLegend !== false) {
      const legendKind = trace.kind === "scatter" ? 0 : STROKE_KINDS.has(trace.kind) ? 1 : 2;
      legendEntries.push({ styleRef, kind: legendKind, symbol: legendKind === 0 ? sceneSymbolCode(style.symbol ?? 0) : 0, label: String(trace.name) });
    }
    const id = Number(trace.id);

    if (RIBBON_KINDS.has(trace.kind) && trace.color_target != null) {
      throw new RangeError("Scene v12 does not yet encode two-ended ribbon gradients");
    }
    let packSymbol = 0;
    let packDiameter = 0;
    let packX = trace.x;
    let packY = trace.y;
    let authoredStep = 0;
    let factBits = 0;
    let hexDx = 0;
    let hexDy = 0;
    let gridRows = 0;
    let gridCols = 0;
    if (HEATMAP_KINDS.has(trace.kind)) {
      const shape = trace.grid_shape;
      if (shape == null || shape.length !== 2) {
        throw new RangeError("Scene v12 heatmap requires a rows x cols grid_shape");
      }
      const rows = Number(shape[0]);
      const cols = Number(shape[1]);
      if (!Number.isInteger(rows) || !Number.isInteger(cols) || rows < 1 || cols < 1) {
        throw new RangeError("Scene v12 heatmap requires a positive grid_shape");
      }
      const grid = trace.grid;
      if (grid == null) {
        throw new RangeError("heatmap Scene v12 compilation requires a scalar grid");
      }
      if (grid.length !== rows * cols) {
        throw new RangeError("Scene v12 heatmap grid must match rows x cols");
      }
      if (Array.from(grid).some((value) => !Number.isFinite(value))) {
        throw new RangeError("Scene v12 does not yet encode missing-data breaks or nonfinite coordinates");
      }
      gridRows = rows;
      gridCols = cols;
      const plane = heatmapPaintPlane(trace, rows, cols, id);
      if (plane.length) {
        heatmapPaintPlanes.push(plane);
        factBits |= FACT_HEATMAP_PAINT;
      }
    } else if (HEXBIN_KINDS.has(trace.kind)) {
      const dx = Number(style.hex_dx ?? style.dx);
      const dy = Number(style.hex_dy ?? style.dy);
      if (!Number.isFinite(dx) || !Number.isFinite(dy) || dx <= 0 || dy <= 0) {
        throw new RangeError("Scene v12 hexbin requires finite hex_dx/hex_dy cell pitch");
      }
      hexDx = dx;
      hexDy = dy;
    } else if (BAND_KINDS.has(trace.kind)) {
      const strokePerimeter = style.stroke_perimeter === undefined ? false : style.stroke_perimeter;
      if (typeof strokePerimeter !== "boolean") {
        throw new RangeError("Scene v25 area stroke_perimeter must be a boolean");
      }
      if (strokePerimeter) factBits |= FACT_STROKE_PERIMETER;
      if (curveIsSmooth(style)) factBits |= FACT_CURVE_SMOOTH;
    } else if (trace.kind === "line") {
      const where = style.step;
      if (where != null) {
        if (!["pre", "post", "mid"].includes(where)) {
          throw new RangeError(`Scene v12 does not support step mode ${JSON.stringify(where)}`);
        }
        authoredStep = { pre: 1, mid: 2, post: 3 }[where];
      }
      if (curveIsSmooth(style)) factBits |= FACT_CURVE_SMOOTH;
    } else if (trace.kind === "scatter") {
      packSymbol = sceneSymbolCode(style.symbol ?? 0);
      packDiameter = Number(style.size ?? style.diameter ?? 4);
      const perItem = style.color_channel != null
        || style.size_channel != null
        || style.stroke_channel != null
        || trace.color_ch != null
        || trace.size_ch != null
        || trace.stroke_ch != null;
      if (shouldUseDensity(trace.x?.length ?? 0, {
        forceDensity: Boolean(trace.force_density ?? trace.forceDensity),
        forceDirect: Boolean(trace.force_direct ?? trace.forceDirect),
        coords: "cartesian",
        perItemChannels: perItem,
      })) {
        const packed = packDensityGrid(
          trace.x, trace.y, xDomain[0], xDomain[1], yDomain[0], yDomain[1], resolveDensityBinColors(trace),
        );
        if (packed) {
          heatmapPaintPlanes.push(densityPaintPlane(
            trace, packed.encoded, packed.rows, packed.cols, packed.max, id, packed.meanRgba,
          ));
          gridRows = packed.rows;
          gridCols = packed.cols;
          factBits |= FACT_DENSITY_PLANE;
          packSymbol = 0;
          packDiameter = 0;
          packX = [xDomain[0], xDomain[1]];
          packY = [yDomain[0], yDomain[1]];
        }
      }
    }
    appendPacked(kinds, stableIds, styleRefs, diameter, symbols, expansionModes, x0, y0, x1, y1, packProductFacts({
      facts: packXyPk({
        kind: trace.kind,
        styleRef,
        coords: (figure.coords ?? "cartesian") === "polar" ? 1 : 0,
        symbol: packSymbol,
        authoredStep,
        facts: factBits,
        traceId: id,
        diameter: packDiameter,
        hexDx,
        hexDy,
        gridRows,
        gridCols,
      }),
      x: packX,
      y: packY,
      x0: trace.x0,
      y0: trace.y0,
      x1: trace.x1,
      y1: trace.y1,
      base: trace.base,
    }));
  }

  const annotationParts = [];
  for (const [annotationIndex, annotation] of (figure.annotations ?? []).entries()) {
    annotationParts.push(packXyAf(annotation, annotationIndex));
  }
  const annotationFacts = concatBytes(annotationParts);
  const authoredText = applyXyao(
    packAnnotationFacts(annotationFacts, styles.length, xDomain, yDomain),
    kinds, stableIds, styleRefs, diameter, symbols, expansionModes, x0, y0, x1, y1, styles, dashes, linecaps,
  );

  const title = figure.title ?? "";
  // `Figure.setAxis({ label })` is the public Node authoring form, matching
  // Python's `axis_options`; do not silently drop those bytes before the Rust
  // layout/Scene seam.
  const xLabel = figure.xLabel ?? figure.x_label ?? figure.xAxis?.label ?? figure.x_axis?.label ?? "";
  const yLabel = figure.yLabel ?? figure.y_label ?? figure.yAxis?.label ?? figure.y_axis?.label ?? "";
  let resolvedMargins = margins;
  if (resolvedMargins == null) {
    const out = new Float64Array(4);
    const titleBytes = new TextEncoder().encode(String(title));
    const xLabelBytes = new TextEncoder().encode(String(xLabel));
    const yLabelBytes = new TextEncoder().encode(String(yLabel));
    const xAxisOptions = figure.xAxis ?? figure.x_axis ?? {};
    const yAxisOptions = figure.yAxis ?? figure.y_axis ?? {};
    const xLayoutFormat = (xAxisOptions.tickLabels ?? xAxisOptions.tick_labels) == null ? xSceneAxis.format : null;
    const yLayoutFormat = (yAxisOptions.tickLabels ?? yAxisOptions.tick_labels) == null ? ySceneAxis.format : null;
    const xFormatBytes = xLayoutFormat == null ? new Uint8Array() : new TextEncoder().encode(String(xLayoutFormat));
    const yFormatBytes = yLayoutFormat == null ? new Uint8Array() : new TextEncoder().encode(String(yLayoutFormat));
    if ([xFormatBytes, yFormatBytes].some((value) => value.length > 256 || value.includes(0))) throw new RangeError("Scene axis format must be NUL-free and at most 256 UTF-8 bytes");
    const written = xyScenePlotLayout(
      Number(figure.width), Number(figure.height), 0,
      ...xSceneDescriptor.slice(1), ...ySceneDescriptor.slice(1),
      titleBytes.length ? u8Ptr(titleBytes) : 0, BigInt(titleBytes.length),
      xLabelBytes.length ? u8Ptr(xLabelBytes) : 0, BigInt(xLabelBytes.length),
      yLabelBytes.length ? u8Ptr(yLabelBytes) : 0, BigInt(yLabelBytes.length),
      xFormatBytes.length ? u8Ptr(xFormatBytes) : 0, BigInt(xFormatBytes.length),
      yFormatBytes.length ? u8Ptr(yFormatBytes) : 0, BigInt(yFormatBytes.length),
      encodedColorbar.length ? (encodedColorbar[8] & 1 ? 2 : 1) : 0,
      f64Ptr(out),
    );
    if (written !== 4n && written !== 4) throw new RangeError("invalid canonical scene plot layout");
    resolvedMargins = [out[0], out[1], out[2], out[3]];
  }
  return sceneBatchEncode({ viewport: [figure.width, figure.height], margins: resolvedMargins,
    xAxis: xSceneAxis, yAxis: ySceneAxis,
    kinds, stableIds, styleRefs, styles, diameter, symbols, expansionModes, x0, y0, x1, y1,
    title, xLabel, yLabel, chromeStyle: figureChromeStyle(figure), xMajorTicks: (figure.xAxis ?? figure.x_axis)?.tickValues ?? (figure.xAxis ?? figure.x_axis)?.tick_values ?? null, xMinorTicks: (figure.xAxis ?? figure.x_axis)?.minorTickValues ?? (figure.xAxis ?? figure.x_axis)?.minor_tick_values ?? [], yMajorTicks: (figure.yAxis ?? figure.y_axis)?.tickValues ?? (figure.yAxis ?? figure.y_axis)?.tick_values ?? null, yMinorTicks: (figure.yAxis ?? figure.y_axis)?.minorTickValues ?? (figure.yAxis ?? figure.y_axis)?.minor_tick_values ?? [], xTickLabels: (figure.xAxis ?? figure.x_axis)?.tickLabels ?? (figure.xAxis ?? figure.x_axis)?.tick_labels ?? null, yTickLabels: (figure.yAxis ?? figure.y_axis)?.tickLabels ?? (figure.yAxis ?? figure.y_axis)?.tick_labels ?? null, xFormat: xSceneAxis.format, yFormat: ySceneAxis.format, legendInput: legendInput(figure, legendEntries, styles), colorbarInput: encodedColorbar, authoredTextAnnotations: authoredText, polarInput: packSceneExtrasFromFacts(packPolarSceneInput(figure), packXyhp(heatmapPaintPlanes), packXySs(dashes, linecaps, markerPaths, fillGradients)),
  });
}

/** Serialize built-in scatter marks through the shared Rust scene schema. */
export function scatterSceneSvg({
  x,
  y,
  diameter,
  fillRgba,
  strokeRgba,
  strokeWidth,
  symbols,
  visible = null,
  fillCss = null,
  strokeCss = null,
}) {
  const xa = asF64Array(x, "x");
  const ya = asF64Array(y, "y");
  const diameters = asF64Array(diameter, "diameter");
  const widths = asF64Array(strokeWidth, "strokeWidth");
  const fills = asU8Array(fillRgba, "fillRgba");
  const strokes = asU8Array(strokeRgba, "strokeRgba");
  const symbolCodes = asU8Array(symbols, "symbols");
  const visibility = visible == null ? null : asU8Array(visible, "visible");
  const fillCssBytes = fillCss == null ? null : new TextEncoder().encode(String(fillCss));
  const strokeCssBytes = strokeCss == null ? null : new TextEncoder().encode(String(strokeCss));
  const length = xa.length;
  requireLength(ya, length, "y");
  requireLength(diameters, length, "diameter");
  requireLength(widths, length, "strokeWidth");
  requireLength(symbolCodes, length, "symbols");
  requireLength(fills, length * 4, "fillRgba");
  requireLength(strokes, length * 4, "strokeRgba");
  if (visibility != null) requireLength(visibility, length, "visible");

  let capacity = Math.max(32, length * 160);
  for (;;) {
    const output = new Uint8Array(capacity);
    const rawWritten = xySceneScatterSvg(
      f64Ptr(xa),
      f64Ptr(ya),
      f64Ptr(diameters),
      u8Ptr(fills),
      u8Ptr(strokes),
      f64Ptr(widths),
      u8Ptr(symbolCodes),
      u8Ptr(visibility),
      u8Ptr(fillCssBytes),
      BigInt(fillCssBytes?.length ?? 0),
      u8Ptr(strokeCssBytes),
      BigInt(strokeCssBytes?.length ?? 0),
      BigInt(length),
      pointer(output, "uint8_t *"),
      BigInt(capacity),
    );
    if (rawWritten === USIZE_MAX_64) {
      throw new RangeError("invalid canonical scatter scene");
    }
    const written = Number(rawWritten);
    if (!Number.isSafeInteger(written) || written < 0) {
      throw new RangeError("canonical scatter scene exceeded host output limits");
    }
    if (written <= capacity) {
      return new TextDecoder().decode(output.subarray(0, written));
    }
    capacity = written;
  }
}
