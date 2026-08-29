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
  xyPolarWedgePoints,
  xyPolarHeatmapInverseMap,
  xyRecutPolarPlot,
  xyTightLayoutSolve,
  xyCompatCombinePlot,
  xyTightLayoutFigureExtra,
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
  xyScenePackSceneExtrasFromSidecars,
  xyScenePackDensityGrid,
  xyScenePackPublicExport,
  xyScenePackFigureChrome,
  xyScenePackFigureChromeFromSidecars,
  xyScenePackTraceCompile,
  xyScenePackTraceAttach,
  xyScenePackTraceRows,
  xyScenePackTraceSidecars,
  xyScenePackStyleSidecars,
  xySceneSpliceAnnotations,
  xySceneEncodeAssembled,
  xySceneEncodeAssembledFromSidecars,
  xySceneEncodeProduct,
  xyScenePackAnnotationMarks,
  xySceneRasterCommands,
  xySceneStaticExport,
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
import { asF64Array, f64Ptr, legendBestLoc, legendNormalize, sceneDashAdmit, sceneLinecapAdmit, sceneMarkerPathAdmit, sceneAnnotationStyleAdmit, sceneRibbonColor2Classify, sceneScatterPaintChannelAdmit, sceneTickLabelStrategy, sceneTickAnchor, sceneFillGradientAdmit, sceneParseLinearGradient, sceneRectExtraFlags, sceneGradientDir, sceneLinearGradientPrefix, sceneGradientSpace, sceneHexbinReduceAdmit, sceneCurveClassify, sceneMarkerGlyphAdmit, sceneKindAdmit, sceneKindClass, sceneHexbinColormapPlaneAdmit, sceneHexbinPitchAdmit, sceneHexbinRgbaPlaneAdmit, sceneHeatmapExtentAdmit, sceneHeatmapColormapAdmit, sceneHeatmapShapeAdmit, sceneMeshPaintPlaneAdmit, sceneItemApplyOpacity, sceneItemWidthsAdmit, sceneItemFillT, shouldUseDensity, u32Ptr, u8Ptr, colormapNamedStops, colormapRgba } from "./encode.js";
import { cssColorRgba8, cssColorsToRgba8 } from "./color.js";

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
const XYAF_FACT_HAS_ROTATION = 1 << 18;
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

function annotationHasMarkup(annotation) {
  if (annotation == null || typeof annotation !== "object") return false;
  if (annotation.markup != null && annotation.markup !== "") return true;
  const style = annotation.style ?? {};
  return style != null && typeof style === "object" && style.markup != null && style.markup !== "";
}

const ANNOTATION_TYPOGRAPHY_STYLE_KEYS = new Set([
  "font_family", "font_size", "font_weight", "font_style",
  "fontFamily", "fontSize", "fontWeight", "fontStyle",
]);

function annotationHasCustomTypography(annotation) {
  if (annotation == null || typeof annotation !== "object") return false;
  const style = annotation.style != null && typeof annotation.style === "object" ? annotation.style : {};
  for (const key of ANNOTATION_TYPOGRAPHY_STYLE_KEYS) {
    if (style[key] != null && style[key] !== "" && style[key] !== false) return true;
    if (annotation[key] != null && annotation[key] !== "" && annotation[key] !== false) return true;
  }
  return false;
}

function packXyAf(annotation, index) {
  // ABI 184 packs cartesian unwrapped text dx/dy/anchor as XYAW wrap=0.
  // ABI 185 packs labelled cartesian marker dx/dy/anchor the same way in Rust.
  // ABI 187 packs cartesian unwrapped text rotation as XYAW wrap=0 (XYAW v2).
  // ABI 188 packs labelled cartesian marker rotation the same way (nums[8]).
  // Annotation html is XYFS OBS_ANNOTATION_HTML (#305); Scene owns literal text.
  // Annotation markup is XYFS OBS_ANNOTATION_MARKUP (#308).
  // Annotation custom typography is XYFS OBS_CUSTOM_FONT (#309).
  // Text/marker style.rotation lifts onto ABI 187/188 top-level rotation.
  annotation = { ...annotation };
  const kind = annotation.kind;
  const kindCode = XYAF_KIND_CODES[kind];
  if (kindCode == null) throw new RangeError(`Scene v12 annotations support rule, band, and unlabeled marker only; ${JSON.stringify(kind)} is deferred`);
  const style = { ...(annotation.style ?? {}) };
  if (["text", "marker"].includes(kind) && !Object.hasOwn(annotation, "rotation") && style.rotation != null) {
    annotation.rotation = style.rotation;
  }
  const authoredWrap = ["text", "callout"].includes(kind) && Object.hasOwn(annotation, "wrap");
  const layoutText = kind === "text" && ["dx", "dy", "anchor", "rotation"].some((key) => Object.hasOwn(annotation, key));
  const wrapped = authoredWrap || layoutText;
  const labelled = annotation.text != null && annotation.text !== "";
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
  const skipStyle = new Set(["markup", ...ANNOTATION_TYPOGRAPHY_STYLE_KEYS]);
  if (["text", "marker"].includes(kind)) skipStyle.add("rotation");
  const unsupported = Object.keys(style).filter((key) => !skipStyle.has(key) && style[key] != null && !sceneAnnotationStyleAdmit(kind, wrapped, labelled, key)).sort();
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
    nums[8] = Object.hasOwn(annotation, "wrap")
      ? annotationNumber(annotation, "wrap", undefined, "wrapped width")
      : 0;
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
  if (kind === "text" && Object.hasOwn(annotation, "rotation")) {
    nums[15] = annotationNumber(annotation, "rotation", undefined, "text rotation");
    facts |= XYAF_FACT_HAS_ROTATION;
    if (!Number.isFinite(nums[15])) throw new RangeError("Scene v16 text annotation rotation must be finite");
  }
  if (kind === "marker" && Object.hasOwn(annotation, "rotation")) {
    nums[8] = annotationNumber(annotation, "rotation", undefined, "marker rotation");
    facts |= XYAF_FACT_HAS_ROTATION;
    if (!Number.isFinite(nums[8])) throw new RangeError("Scene v16 marker annotation rotation must be finite");
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

function packTraceRowBytes(attached, columns) {
  const attachedBytes = attached instanceof Uint8Array ? attached : new Uint8Array();
  const columnsBytes = columns instanceof Uint8Array ? columns : new Uint8Array();
  let capacity = Math.max(65536, Math.floor(columnsBytes.length / 8) * 2 * 56 + 4096);
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const out = new Uint8Array(capacity);
    const code = xyScenePackTraceRows(
      attachedBytes.length ? u8Ptr(attachedBytes) : 0,
      BigInt(attachedBytes.length),
      columnsBytes.length ? u8Ptr(columnsBytes) : 0,
      BigInt(columnsBytes.length),
      u8Ptr(out),
      BigInt(out.length),
    );
    if (code === -4) {
      capacity *= 2;
      continue;
    }
    if (code < 0) {
      const failing = new DataView(out.buffer, out.byteOffset, 4).getUint32(0, true);
      raiseTraceRows(code, failing);
    }
    return out.subarray(0, code * 56);
  }
  raiseTraceRows(-4, 0);
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
  return sceneDashAdmit(value);
}

function parseSceneLinecap(value) {
  return sceneLinecapAdmit(value);
}

function validateMarkerPath(value) {
  return sceneMarkerPathAdmit(value);
}

function fillIsGradientAuthoring(fill) {
  if (fill != null && typeof fill === "object") return true;
  if (typeof fill !== "string") return false;
  return sceneLinearGradientPrefix(fill);
}

function parseLinearGradient(value, space = "mark") {
  if (typeof value !== "string") return null;
  return sceneParseLinearGradient(value, space);
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
  if (classifyRibbonColor2(trace) === "fail") return null;
  if (channel == null) return String(trace.style?.color ?? "#3987e5");
  if (typeof channel === "string") return channel;
  if (channel.mode === "constant" && (channel.constant != null || channel.color != null)) {
    return String(channel.constant ?? channel.color);
  }
  if (String(trace.kind ?? "") === "scatter" && scatterUsesDensity(trace)) {
    return String(trace.style?.color ?? "#3987e5");
  }
  return null;
}

function channelConstantCss(channel) {
  if (channel == null) return null;
  if (typeof channel === "string") return String(channel);
  if (typeof channel === "object" && !Array.isArray(channel) && !ArrayBuffer.isView(channel)) {
    if (channel.mode === "constant") {
      const css = channel.constant ?? channel.color;
      if (css != null) return String(css);
    }
  }
  return null;
}

function color2Channel(trace) {
  return trace.color2_ch ?? trace.color_target ?? trace.colorTarget ?? null;
}

function sourceColorCss(trace) {
  const css = channelConstantCss(trace.color_ch ?? trace.colorChannel ?? trace.color);
  if (css != null) return css;
  return String(trace.style?.color ?? "#3987e5");
}

function classifyRibbonColor2(trace) {
  const channel = color2Channel(trace);
  const hasColor2 = channel != null;
  const kindIsRibbon = String(trace.kind ?? "") === "ribbon";
  const target = hasColor2 ? channelConstantCss(channel) : null;
  const sourceConst = channelConstantCss(trace.color_ch ?? trace.colorChannel ?? trace.color);
  const sourcePaint = sourceColorCss(trace);
  const hasFill = Object.hasOwn(trace.style ?? {}, "fill");
  const bothConst = target != null && sourceConst != null;
  let hasEndPair = false;
  if (hasColor2 && kindIsRibbon && !bothConst && !hasFill) {
    hasEndPair = ribbonEndRgbaPair(trace) != null;
  }
  return sceneRibbonColor2Classify(
    hasColor2,
    kindIsRibbon,
    sourceConst,
    target,
    sourcePaint,
    hasFill,
    hasEndPair,
  );
}

function ribbonCount(trace) {
  const raw = trace.count;
  if (raw != null && Number.isFinite(Number(raw))) return Number(raw);
  const column = trace.x0;
  return column == null ? 0 : column.length;
}

function channelEndRgba8(channel, n, fallback) {
  if (!(n >= 1)) return null;
  const replicate = (css) => {
    try {
      const rgba = cssColorRgba8(String(css), 1);
      const out = new Uint8Array(n * 4);
      for (let i = 0; i < n; i += 1) out.set(rgba, i * 4);
      return out;
    } catch {
      return null;
    }
  };
  if (channel == null) return replicate(fallback);
  if (typeof channel === "string") return replicate(channel);
  if (Array.isArray(channel) || ArrayBuffer.isView(channel)) {
    if (channel.length === n * 4 && (channel instanceof Uint8Array || ArrayBuffer.isView(channel))) {
      return channel instanceof Uint8Array ? channel : Uint8Array.from(channel);
    }
    if (channel.length !== n) return null;
    try {
      return cssColorsToRgba8([...channel].map(String));
    } catch {
      return null;
    }
  }
  if (typeof channel === "object") {
    if (channel.mode === "constant") {
      const css = channel.constant ?? channel.color;
      if (css == null) return null;
      return replicate(css);
    }
    if (channel.mode === "direct_rgba" && channel.rgba != null) {
      const raw = channel.rgba;
      if (raw instanceof Uint8Array && raw.length === n * 4) return raw;
      if (Array.isArray(raw) && raw.length === n && Array.isArray(raw[0])) {
        const out = new Uint8Array(n * 4);
        for (let i = 0; i < n; i += 1) {
          const row = raw[i];
          out[i * 4] = Math.round(Math.min(1, Math.max(0, Number(row[0]))) * 255);
          out[i * 4 + 1] = Math.round(Math.min(1, Math.max(0, Number(row[1]))) * 255);
          out[i * 4 + 2] = Math.round(Math.min(1, Math.max(0, Number(row[2]))) * 255);
          out[i * 4 + 3] = Math.round(Math.min(1, Math.max(0, Number(row[3] ?? 1))) * 255);
        }
        return out;
      }
      if (ArrayBuffer.isView(raw) && raw.length === n * 4) return Uint8Array.from(raw);
    }
    if (channel.mode === "categorical" && channel.codes != null) {
      const codes = channel.codes;
      if (codes.length !== n) return null;
      const palette = [...(channel.palette ?? [])];
      const css = [];
      for (let i = 0; i < n; i += 1) {
        const code = Number(codes[i]);
        const slot = palette.length > 0 ? palette[((code % palette.length) + palette.length) % palette.length] : null;
        css.push(slot ?? fallback);
      }
      try {
        return cssColorsToRgba8(css);
      } catch {
        return null;
      }
    }
  }
  return null;
}

function ribbonEndRgbaPair(trace) {
  const n = ribbonCount(trace);
  if (n < 1) return null;
  const fallback = sourceColorCss(trace);
  const source = channelEndRgba8(trace.color_ch ?? trace.colorChannel ?? trace.color, n, fallback);
  const target = channelEndRgba8(color2Channel(trace), n, fallback);
  if (source == null || target == null) return null;
  return { source, target };
}

function ribbonPacksEndPaints(trace, polar = false) {
  if (polar || String(trace.kind ?? "") !== "ribbon") return false;
  return classifyRibbonColor2(trace) === "ends";
}

function ribbonColor2GradientSpec(trace) {
  if (classifyRibbonColor2(trace) !== "gradient") return null;
  const target = channelConstantCss(color2Channel(trace));
  if (target == null) return null;
  return {
    space: "mark",
    dir: "right",
    stops: [[0, sourceColorCss(trace)], [1, target]],
  };
}

function admitFillGradient(trace) {
  const fill = trace.style?.fill;
  if (!fillIsGradientAuthoring(fill)) return null;
  const spec = normalizeFillSpec(fill);
  const markColor = constantMarkColor(trace);
  if (spec == null || markColor == null) return null;
  if (!Array.isArray(spec.stops)) return null;
  const ts = [];
  const css = [];
  for (const stop of spec.stops) {
    if (!Array.isArray(stop) || stop.length !== 2) return null;
    ts.push(Number(stop[0]));
    css.push(String(stop[1]));
  }
  const rgba = sceneFillGradientAdmit(spec.space, spec.dir, ts, css, markColor);
  if (rgba == null) return null;
  return { space: spec.space, dir: spec.dir, stops: ts.map((t, i) => [t, rgba[i]]) };
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
    record[9] = gradient ? sceneGradientDir(gradient.dir) : 0;
    record[10] = gradient ? (sceneGradientSpace(gradient.space) === 1 ? 1 : 0) : 0;
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

function packSceneExtrasFromSidecars(polar, xysd, facts) {
  const polarBytes = polar instanceof Uint8Array ? polar : new Uint8Array();
  const xysdBytes = xysd instanceof Uint8Array ? xysd : new Uint8Array();
  const factsBytes = facts instanceof Uint8Array ? facts : new Uint8Array();
  if (!polarBytes.length && !xysdBytes.length && !factsBytes.length) return new Uint8Array();
  let capacity = Math.max(256, polarBytes.length + xysdBytes.length + factsBytes.length + 64);
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const out = new Uint8Array(capacity);
    const code = xyScenePackSceneExtrasFromSidecars(
      polarBytes.length ? u8Ptr(polarBytes) : 0,
      BigInt(polarBytes.length),
      xysdBytes.length ? u8Ptr(xysdBytes) : 0,
      BigInt(xysdBytes.length),
      factsBytes.length ? u8Ptr(factsBytes) : 0,
      BigInt(factsBytes.length),
      u8Ptr(out),
      BigInt(out.length),
    );
    if (code === -4) {
      capacity *= 2;
      continue;
    }
    if (code === -5) throw new RangeError("Scene extras polar or paint envelope is invalid");
    if (code === -6) throw new RangeError("Scene style sidecar facts are invalid");
    if (code < 0) throw new RangeError("invalid scene extras packing");
    return out.subarray(0, code);
  }
  throw new RangeError("invalid scene extras packing");
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

export function polarWedgePoints(
  metrics,
  theta0,
  theta1,
  r0,
  r1,
  {
    wedgeGap = 0,
    cornerRadius = 0,
    steps = 0,
    normalized = null,
  } = {},
) {
  const packed = metrics instanceof Float64Array ? metrics : Float64Array.from(metrics);
  const normLo = normalized == null ? Number.NaN : Number(normalized[0]);
  const normHi = normalized == null ? Number.NaN : Number(normalized[1]);
  const probed = xyPolarWedgePoints(
    packed.length ? f64Ptr(packed) : 0,
    packed.length,
    Number(theta0),
    Number(theta1),
    Number(r0),
    Number(r1),
    Number(wedgeGap),
    Number(cornerRadius),
    Number(steps),
    normLo,
    normHi,
    0,
    0,
    0,
  );
  if (probed === USIZE_MAX_64) throw new RangeError("invalid polar-wedge request");
  const n = Number(probed);
  if (n === 0) return [];
  const outX = new Float64Array(n);
  const outY = new Float64Array(n);
  const written = xyPolarWedgePoints(
    packed.length ? f64Ptr(packed) : 0,
    packed.length,
    Number(theta0),
    Number(theta1),
    Number(r0),
    Number(r1),
    Number(wedgeGap),
    Number(cornerRadius),
    Number(steps),
    normLo,
    normHi,
    f64Ptr(outX),
    f64Ptr(outY),
    n,
  );
  if (written === USIZE_MAX_64 || Number(written) !== n) {
    throw new RangeError("invalid polar-wedge request");
  }
  return Array.from({ length: n }, (_, index) => [outX[index], outY[index]]);
}

export function polarHeatmapInverseMap(
  metrics,
  plot,
  gridW,
  gridH,
  xRange,
  yRange,
  outputScale = 1,
) {
  const packed = metrics instanceof Float64Array ? metrics : Float64Array.from(metrics);
  const outW = new Uint32Array(1);
  const outH = new Uint32Array(1);
  const probed = xyPolarHeatmapInverseMap(
    packed.length ? f64Ptr(packed) : 0,
    packed.length,
    Number(plot.x ?? 0),
    Number(plot.y ?? 0),
    Number(plot.w ?? 0),
    Number(plot.h ?? 0),
    Number(gridW),
    Number(gridH),
    Number(xRange[0]),
    Number(yRange[0]),
    Number(xRange[1]),
    Number(yRange[1]),
    Number(outputScale),
    u32Ptr(outW),
    u32Ptr(outH),
    0,
    0,
    0,
    0,
  );
  if (probed === USIZE_MAX_64) throw new RangeError("invalid polar-heatmap inverse-map request");
  const capacity = Number(outW[0]) * Number(outH[0]);
  const rows = new Uint32Array(capacity);
  const cols = new Uint32Array(capacity);
  const source = new Uint32Array(capacity);
  const written = xyPolarHeatmapInverseMap(
    packed.length ? f64Ptr(packed) : 0,
    packed.length,
    Number(plot.x ?? 0),
    Number(plot.y ?? 0),
    Number(plot.w ?? 0),
    Number(plot.h ?? 0),
    Number(gridW),
    Number(gridH),
    Number(xRange[0]),
    Number(yRange[0]),
    Number(xRange[1]),
    Number(yRange[1]),
    Number(outputScale),
    u32Ptr(outW),
    u32Ptr(outH),
    capacity ? u32Ptr(rows) : 0,
    capacity ? u32Ptr(cols) : 0,
    capacity ? u32Ptr(source) : 0,
    capacity,
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid polar-heatmap inverse-map request");
  const n = Number(written);
  return {
    width: Number(outW[0]),
    height: Number(outH[0]),
    rows: rows.subarray(0, n),
    cols: cols.subarray(0, n),
    sourceIndices: source.subarray(0, n),
  };
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

export function compatCombinePlot(width, height, {
  authoredPadding = null,
  titleRoom = 0,
  xTopRoom = 0,
  xBottomRoom = 0,
  xMeasuredBottom = 0,
  colorbarKind = "none",
  colorbarHasLabel = false,
  colorbarPadZero = false,
  hasRightY = false,
  yLeftRoom = null,
  edgeLeft = null,
  edgeRight = null,
  xRoomsFinal = null,
  polar = null,
} = {}) {
  const code = COLORBAR_KINDS[colorbarKind];
  if (code === undefined) throw new RangeError("unknown colorbar layout kind");
  const pad = authoredPadding == null ? null : Float64Array.from(authoredPadding);
  if (pad != null && pad.length !== 4) {
    throw new RangeError("authoredPadding must be top, right, bottom, left");
  }
  const xFinal = xRoomsFinal == null ? null : Float64Array.from(xRoomsFinal);
  if (xFinal != null && xFinal.length !== 3) {
    throw new RangeError("xRoomsFinal must be top, bottom, measuredBottom");
  }
  const polarOn = polar != null;
  let side = 0;
  let legendRoom = 0;
  let labelRoom = 0;
  let authoredPaddingFlag = false;
  let yTitled = false;
  let keepsBottom = false;
  if (polarOn) {
    const legendSide = polar.legendSide ?? polar.legend_side ?? "";
    side = POLAR_LEGEND_SIDE_CODES[legendSide];
    if (side === undefined) throw new RangeError("legendSide must be '', left, right, or bottom");
    legendRoom = Number(polar.legendRoom ?? polar.legend_room ?? 0);
    labelRoom = Number(polar.polarLabelRoom ?? polar.polar_label_room ?? 0);
    authoredPaddingFlag = Boolean(polar.authoredPadding ?? polar.authored_padding);
    yTitled = Boolean(polar.yTitled ?? polar.y_titled);
    keepsBottom = Boolean(polar.keepsBottom ?? polar.keeps_bottom);
  }
  const out = new Float64Array(12);
  const written = xyCompatCombinePlot(
    Number(width),
    Number(height),
    pad == null ? 0 : f64Ptr(pad),
    Number(titleRoom),
    Number(xTopRoom),
    Number(xBottomRoom),
    Number(xMeasuredBottom),
    code,
    colorbarHasLabel ? 1 : 0,
    colorbarPadZero ? 1 : 0,
    hasRightY ? 1 : 0,
    yLeftRoom == null ? Number.NaN : Number(yLeftRoom),
    edgeLeft == null ? Number.NaN : Number(edgeLeft),
    edgeRight == null ? Number.NaN : Number(edgeRight),
    xFinal == null ? 0 : f64Ptr(xFinal),
    polarOn ? 1 : 0,
    side,
    legendRoom,
    labelRoom,
    authoredPaddingFlag ? 1 : 0,
    yTitled ? 1 : 0,
    keepsBottom ? 1 : 0,
    f64Ptr(out),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid static-export layout combination");
  const result = {
    x: out[0],
    y: out[1],
    w: out[2],
    h: out[3],
    titleRoom: out[4],
    titleWrapWidth: out[5],
    topAxisRoom: out[6],
    bottomAxisRoom: out[7],
  };
  if (Number.isFinite(out[8])) {
    result.legendBoxX = out[8];
    result.legendBoxY = out[9];
    result.legendBoxW = out[10];
    result.legendBoxH = out[11];
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

export function tightLayoutFigureExtra(canvasW, canvasH, {
  suptitleHeight = null,
  suptitleY = 0.98,
  xlabelSize = null,
  ylabelSize = null,
  legendBoxW = null,
} = {}) {
  const extra = new Float64Array(4);
  const written = xyTightLayoutFigureExtra(
    Number(canvasW),
    Number(canvasH),
    suptitleHeight == null ? Number.NaN : Number(suptitleHeight),
    Number(suptitleY),
    xlabelSize == null ? Number.NaN : Number(xlabelSize),
    ylabelSize == null ? Number.NaN : Number(ylabelSize),
    legendBoxW == null ? Number.NaN : Number(legendBoxW),
    f64Ptr(extra),
  );
  if (written === USIZE_MAX_64) throw new RangeError("invalid tight-layout figure-extra request");
  return { left: extra[0], right: extra[1], bottom: extra[2], top: extra[3] };
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

function packXyCh(figure) {
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
  return concatBytes([header, chart, plot, x, y]);
}

function figureChromeStyle(figure) {
  return resolveChromeStyle(packXyCh(figure));
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

const SCENE_STATIC_FORMATS = { svg: 0, png: 1, pdf: 2, jpeg: 3, webp: 4 };

export function sceneStaticExport(encoded, format, { scale = 1, width = 1, height = 1, quality = 90 } = {}) {
  const code = SCENE_STATIC_FORMATS[format];
  if (code == null) {
    throw new RangeError(`Scene public static format must be svg, png, pdf, jpeg, or webp, got ${String(format)}`);
  }
  let factor = Number(scale);
  if (format === "png" || format === "jpeg" || format === "webp") {
    if (!Number.isFinite(factor) || factor <= 0) throw new RangeError("scene raster scale must be positive and finite");
  } else if (!Number.isFinite(factor)) {
    factor = 1;
  }
  const w = Number(width);
  const h = Number(height);
  const q = Number(quality);
  if (!Number.isInteger(w) || w <= 0) throw new RangeError("scene static width must be a positive integer");
  if (!Number.isInteger(h) || h <= 0) throw new RangeError("scene static height must be a positive integer");
  if (!Number.isInteger(q)) throw new RangeError("quality must be an int in 1..100");
  return sceneOutput(encoded, xySceneStaticExport, "static export", [code, factor, BigInt(w), BigInt(h), q]);
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

const SCENE_KIND_CLASS_RECT = 1 << 0;
const SCENE_KIND_CLASS_BAND = 1 << 2;
const SCENE_KIND_CLASS_RIBBON = 1 << 3;
const SCENE_KIND_CLASS_POLYFILL = 1 << 4;
const SCENE_KIND_CLASS_HEXBIN = 1 << 5;
const SCENE_KIND_CLASS_HEATMAP = 1 << 6;
const SCENE_KIND_CLASS_SCATTER = 1 << 8;
const SCENE_KIND_CLASS_LINE = 1 << 9;
const SCENE_KIND_CLASS_OPACITY = SCENE_KIND_CLASS_BAND | SCENE_KIND_CLASS_RIBBON | SCENE_KIND_CLASS_RECT | SCENE_KIND_CLASS_HEATMAP | SCENE_KIND_CLASS_SCATTER | SCENE_KIND_CLASS_HEXBIN | SCENE_KIND_CLASS_POLYFILL;
const XYFS_TRACE_UNSUPPORTED_KIND = 1 << 0;
const XYFS_TRACE_NON_PRIMARY_AXIS = 1 << 1;
const XYFS_TRACE_HIDDEN_OR_PER_ITEM = 1 << 2;
const XYFS_TRACE_DENSITY = 1 << 3;
const XYFS_TRACE_DASHED_MARKERS = 1 << 4;
const XYFS_TRACE_RECT_GRADIENT = 1 << 5;
const XYFS_TRACE_CORNER_RADIUS = 1 << 6;
const XYFS_TRACE_WEDGE_GAP = 1 << 7;
const XYFS_TRACE_JOINED_FILL = 1 << 8; // reserved; ABI 182 no longer fail-closes this bit
const XYFS_TRACE_CUSTOM_HEX_REDUCE = 1 << 9;
const XYFS_TRACE_HEATMAP_COLORMAP = 1 << 10;
const XYFS_TRACE_NON_CSS_FILL = 1 << 11;

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

const SCENE_TICK_STRATEGY_NAMES = ["auto", "hide", "rotate", "stagger", "preserve", "none", "off"];

function sceneTickStrategy(options) {
  const raw = options?.tick_label_strategy ?? options?.tickLabelStrategy ?? options?.collision;
  const code = sceneTickLabelStrategy(String(raw ?? "auto"));
  return SCENE_TICK_STRATEGY_NAMES[code] ?? "auto";
}

const POLAR_COLLISION_KEYS = new Set([
  "tick_label_strategy",
  "tickLabelStrategy",
  "collision",
  "tick_label_min_gap",
  "tickLabelMinGap",
  "tick_label_angle",
  "tickLabelAngle",
  "tick_label_anchor",
  "tickLabelAnchor",
]);

function significantSceneAxisKeys(options, polar = false) {
  let keys = Object.entries(options ?? {})
    .filter(([, value]) => {
      if (value == null || value === false) return false;
      if (Array.isArray(value) && value.length === 0) return false;
      if (typeof value === "object" && !Array.isArray(value) && Object.keys(value).length === 0) return false;
      return true;
    })
    .map(([key]) => key);
  if (polar && ["none", "off", "auto"].includes(sceneTickStrategy(options))) {
    keys = keys.filter((key) => !POLAR_COLLISION_KEYS.has(key));
  }
  return keys;
}

function packFigureSupport(figure, { colorbarUnsupported = false } = {}) {
  const chromeStyles = figure.chromeStyles ?? figure.chrome_styles ?? {};
  const annotations = [...(figure.annotations ?? [])];
  let flags = 0;
  if (figure.coords !== "cartesian") flags |= 1 << 0;
  if (
    Object.values(chromeStyles).some((style) => style?.fontFamily != null || style?.["font-family"] != null)
    || annotations.some((annotation) => annotationHasCustomTypography(annotation))
  ) flags |= 1 << 1;
  // Scene static paint/measure is DejaVu Sans (#288). Custom font-family,
  // chart/theme CSS, and class_name are XYFS observations; Rust reports
  // CUSTOM_FONT / BROWSER_CSS. Live browser widgets still apply CSS.
  if (
    figure.className
    || figure.class_name
    || Object.keys(figure.classNames ?? figure.class_names ?? {}).length
    || Object.keys(chromeStyles).length
    || Object.keys(figure.style ?? {}).some((key) => !["background", "--chart-bg"].includes(key))
    || annotations.some((annotation) => annotation.className || annotation.class_name)
  ) flags |= 1 << 2;
  if (annotations.some((annotation) => annotation.html != null && annotation.html !== "")) flags |= 1 << 8;
  if (annotations.some((annotation) => annotation.collision != null && annotation.collision !== "")) flags |= 1 << 6;
  if (annotations.some((annotation) => annotationHasMarkup(annotation))) flags |= 1 << 9;
  if ((figure.traces ?? []).some((trace) => (
    classifyRibbonColor2(trace) === "fail"
    || (
      scatterHasNonConstantColor(trace)
      && !scatterUsesDensity(trace)
      && !hexbinPacksPaintPlane(trace)
      && !meshPacksPaintPlane(trace)
      && !scatterPacksPaintPlane(trace)
      && !(figure.coords !== "polar" && ribbonPacksEndPaints(trace))
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
    const keys = significantSceneAxisKeys(options, (flags & 1) !== 0);
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

function packPublicExportFromFacts(facts) {
  const factsBytes = facts instanceof Uint8Array ? facts : new Uint8Array();
  const out = new Uint8Array(Math.max(256, factsBytes.length + 64));
  const code = xyScenePackPublicExport(
    factsBytes.length ? u8Ptr(factsBytes) : 0,
    BigInt(factsBytes.length),
    u8Ptr(out),
    BigInt(out.length),
  );
  if (code === -2) throw new RangeError("invalid scene public export facts version");
  if (code < 0) throw new RangeError("invalid scene public export packing");
  return out.subarray(0, code);
}

function packF64s(values) {
  const out = new Uint8Array(values.length * 8);
  const view = new DataView(out.buffer);
  values.forEach((value, index) => view.setFloat64(index * 8, Number(value), true));
  return out;
}

function packTickLabels(labels) {
  if (labels == null) return new Uint8Array();
  const parts = [];
  for (const label of labels) {
    const encoded = encodeUtf8(String(label));
    const header = new Uint8Array(4);
    new DataView(header.buffer).setUint32(0, encoded.length, true);
    parts.push(header, encoded);
  }
  return concatBytes(parts);
}

function unpackXyTl(blob) {
  if (!blob.length) return null;
  if (blob.length < 12 || String.fromCharCode(...blob.subarray(0, 4)) !== "XYTL") {
    throw new RangeError("invalid scene chrome packing");
  }
  const view = new DataView(blob.buffer, blob.byteOffset, blob.byteLength);
  const count = view.getUint32(8, true);
  let at = 12;
  const labels = [];
  for (let i = 0; i < count; i++) {
    const length = view.getUint32(at, true);
    at += 4;
    labels.push(new TextDecoder().decode(blob.subarray(at, at + length)));
    at += length;
  }
  if (at !== blob.length) throw new RangeError("invalid scene chrome packing");
  return labels;
}

function unpackXyCc(blob) {
  if (blob.length < 160 || String.fromCharCode(...blob.subarray(0, 4)) !== "XYCC") {
    throw new RangeError("invalid scene chrome packing");
  }
  const view = new DataView(blob.buffer, blob.byteOffset, blob.byteLength);
  if (view.getUint32(4, true) !== 1) throw new RangeError("invalid scene chrome facts version");
  const margins = [view.getFloat64(16, true), view.getFloat64(24, true), view.getFloat64(32, true), view.getFloat64(40, true)];
  const lens = [];
  for (let i = 0; i < 16; i++) lens.push(view.getUint32(48 + i * 4, true));
  let at = 160;
  const take = (n) => { const chunk = blob.subarray(at, at + n); at += n; return chunk; };
  const takeF64 = (n) => {
    if (!n) return [];
    const raw = take(n * 8);
    const values = [];
    const data = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
    for (let i = 0; i < n; i++) values.push(data.getFloat64(i * 8, true));
    return values;
  };
  const chromeStyle = take(lens[0]);
  const title = new TextDecoder().decode(take(lens[1]));
  const xLabel = new TextDecoder().decode(take(lens[2]));
  const yLabel = new TextDecoder().decode(take(lens[3]));
  const xMajor = takeF64(lens[4]);
  const xMinor = takeF64(lens[6]);
  const yMajor = takeF64(lens[7]);
  const yMinor = takeF64(lens[9]);
  const xTickLabels = unpackXyTl(take(lens[10]));
  const yTickLabels = unpackXyTl(take(lens[11]));
  const xFormatB = take(lens[12]);
  const yFormatB = take(lens[13]);
  const legendInput = take(lens[14]);
  const colorbarInput = take(lens[15]);
  if (at !== blob.length) throw new RangeError("invalid scene chrome packing");
  return {
    margins,
    chromeStyle,
    title,
    xLabel,
    yLabel,
    xMajorTicks: lens[5] ? null : xMajor,
    xMinorTicks: xMinor,
    yMajorTicks: lens[8] ? null : yMajor,
    yMinorTicks: yMinor,
    xTickLabels,
    yTickLabels,
    xFormat: xFormatB.length ? new TextDecoder().decode(xFormatB) : null,
    yFormat: yFormatB.length ? new TextDecoder().decode(yFormatB) : null,
    legendInput,
    colorbarInput,
  };
}

function packFigureChrome(facts) {
  const factsBytes = facts instanceof Uint8Array ? facts : new Uint8Array();
  const out = new Uint8Array(Math.max(65536, factsBytes.length + 4096));
  const code = xyScenePackFigureChrome(
    factsBytes.length ? u8Ptr(factsBytes) : 0,
    BigInt(factsBytes.length),
    u8Ptr(out),
    BigInt(out.length),
  );
  if (code === -2) throw new RangeError("invalid scene chrome facts version");
  if (code === -5) throw new RangeError("invalid canonical scene plot layout");
  if (code === -7) throw new RangeError("Scene v12 primary legends do not yet encode anchors, multiple columns, or custom content");
  if (code === -8) throw new RangeError("Scene v12 primary legends are static; toggle and highlight must be false");
  if (code === -9) throw new RangeError("Scene v12 does not support legend location");
  if (code === -10) throw new RangeError("legend font sizes must be finite and in [1, 1000]");
  if (code === -11) throw new RangeError("Scene v12 legends support only background, color, font_size, and title_font_size");
  if (code === -12) throw new RangeError("Scene v19 colorbars require literal bounded RGBA stops");
  if (code === -13) throw new RangeError("Scene v19 colorbars require a two-value domain and 2–16 stops");
  if (code === -14) throw new RangeError("Scene v19 colorbar side is right or bottom");
  if (code === -15) throw new RangeError("scene axis tick lists are limited to 200 values");
  if (code < 0) throw new RangeError("invalid scene chrome packing");
  return out.subarray(0, code);
}

function packFigureChromeFromSidecars(facts, xysd) {
  const factsBytes = facts instanceof Uint8Array ? facts : new Uint8Array();
  const xysdBytes = xysd instanceof Uint8Array ? xysd : new Uint8Array();
  let capacity = Math.max(65536, factsBytes.length + xysdBytes.length + 4096);
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const out = new Uint8Array(capacity);
    const code = xyScenePackFigureChromeFromSidecars(
      factsBytes.length ? u8Ptr(factsBytes) : 0,
      BigInt(factsBytes.length),
      xysdBytes.length ? u8Ptr(xysdBytes) : 0,
      BigInt(xysdBytes.length),
      u8Ptr(out),
      BigInt(out.length),
    );
    if (code === -4) {
      capacity *= 2;
      continue;
    }
    if (code === -2) throw new RangeError("invalid scene chrome facts version");
    if (code === -5) throw new RangeError("invalid canonical scene plot layout");
    if (code === -7) throw new RangeError("Scene v12 primary legends do not yet encode anchors, multiple columns, or custom content");
    if (code === -8) throw new RangeError("Scene v12 primary legends are static; toggle and highlight must be false");
    if (code === -9) throw new RangeError("Scene v12 does not support legend location");
    if (code === -10) throw new RangeError("legend font sizes must be finite and in [1, 1000]");
    if (code === -11) throw new RangeError("Scene v12 legends support only background, color, font_size, and title_font_size");
    if (code === -12) throw new RangeError("Scene v19 colorbars require literal bounded RGBA stops");
    if (code === -13) throw new RangeError("Scene v19 colorbars require a two-value domain and 2–16 stops");
    if (code === -14) throw new RangeError("Scene v19 colorbar side is right or bottom");
    if (code === -15) throw new RangeError("scene axis tick lists are limited to 200 values");
    if (code < 0) throw new RangeError("invalid scene chrome packing");
    return out.subarray(0, code);
  }
  throw new RangeError("invalid scene chrome packing");
}

const XYTC_HAS_FILL = 1 << 0;
const XYTC_HAS_STROKE = 1 << 1;
const XYTC_HAS_LINE_COLOR = 1 << 2;
const XYTC_HAS_STROKE_WIDTH = 1 << 3;
const XYTC_HAS_WIDTH = 1 << 4;
const XYTC_HAS_LINE_WIDTH = 1 << 5;
const XYTC_HAS_SIZE = 1 << 6;
const XYTC_HAS_SIZE_CH = 1 << 7;
const XYTC_HAS_HEX = 1 << 8;
const XYTC_PERIMETER_TRUE = 1 << 9;
const XYTC_PERIMETER_INVALID = 1 << 10;
const XYTC_COLOR_CH = 1 << 11;
const XYTC_COLOR_CH_CONSTANT = 1 << 12;
const XYTC_COLOR2 = 1 << 13;
const XYTC_USE_DENSITY = 1 << 14;
const XYTC_SHOW_LEGEND = 1 << 15;
const XYTC_HAS_NAME = 1 << 16;
const XYTC_HAS_DASH_PATTERN = 1 << 17;
const XYTC_HAS_MARKER = 1 << 18;
const XYTC_HAS_GRADIENT_SPEC = 1 << 19;
const XYTC_HAS_FILL_DICT = 1 << 20;
const XYTC_SYMBOL_INT = 1 << 21;
const XYTC_HAS_CORNER_RADIUS = 1 << 22;
const XYTC_HAS_WEDGE_GAP = 1 << 23;
const XYTC_HAS_GLYPH = 1 << 24;
const XYTC_JOINED_FILL = 1 << 25;
const XYTO_LINECAP_NONE = 255;
const XYTA_HEATMAP = 1 << 0;
const XYTA_DENSITY = 1 << 1;
const XYTA_HAS_RGBA = 1 << 2;
const XYTA_HAS_RGBA_GRID = 1 << 3;
const XYTA_HAS_GRID = 1 << 4;
const XYTA_TRUECOLOR = 1 << 5;
const XYTA_HAS_NAMED_CMAP = 1 << 6;
const XYTA_HAS_STOPS = 1 << 7;
const XYTA_HAS_COLOR_CH = 1 << 8;
const XYTA_HAS_STYLE_COLOR = 1 << 9;
const XYTA_HAS_OPACITY = 1 << 10;
const XYTA_HAS_FILL_OPACITY = 1 << 11;
const XYTA_HAS_DOMAIN = 1 << 12;
const XYTA_SHAPE = 1 << 13;
const XYTA_RIBBON_ENDS = 1 << 14;
const XYTA_MESH_FACES = 1 << 15;
const XYTA_SCATTER_PAINT = 1 << 16;
const XYMG_MAX_UTF8 = 64;
const GRAD_DIR_FROM_CODE = { 0: "down", 1: "up", 2: "right", 3: "left" };

function admittedMarkerGlyph(glyph) {
  if (glyph == null) return null;
  const text = String(glyph);
  if (!sceneMarkerGlyphAdmit(text)) return null;
  return encodeUtf8(text);
}

function packMarkerBlob(value) {
  if (value == null || typeof value !== "object" || Array.isArray(value) || !Array.isArray(value.contours)) {
    return null;
  }
  const contours = value.contours;
  const parts = [new Uint8Array(8)];
  new DataView(parts[0].buffer).setUint32(0, contours.length, true);
  parts[0][4] = value.filled == null || value.filled ? 1 : 0;
  for (const contour of contours) {
    if (!Array.isArray(contour)) return null;
    const values = contour.map(Number);
    const header = new Uint8Array(4 + values.length * 8);
    const view = new DataView(header.buffer);
    view.setUint32(0, values.length, true);
    values.forEach((item, index) => view.setFloat64(4 + index * 8, item, true));
    parts.push(header);
  }
  return concatBytes(parts);
}

function packGradientSpec(fill) {
  const space = sceneGradientSpace(fill.space);
  const dir = sceneGradientDir(fill.dir);
  if (!Array.isArray(fill.stops)) return null;
  const parts = [new Uint8Array([space, dir, fill.stops.length & 0xff, 0])];
  for (const stop of fill.stops) {
    if (!Array.isArray(stop) || stop.length !== 2) return null;
    const css = encodeUtf8(String(stop[1]));
    const head = new Uint8Array(10);
    const view = new DataView(head.buffer);
    view.setFloat64(0, Number(stop[0]), true);
    view.setUint16(8, css.length, true);
    parts.push(head, css);
  }
  return concatBytes(parts);
}

function packXyTc(figure) {
  const traces = figure.traces ?? [];
  const records = [];
  const showLegend = figure.showLegend !== false;
  for (const trace of traces) {
    const style = trace.style ?? {};
    let flags = 0;
    const kindName = String(trace.kind ?? "");
    const kind = encodeUtf8(kindName);
    const kindClass = sceneKindClass(kindName);
    const name = trace.name != null && String(trace.name).length ? String(trace.name) : "";
    if (name) flags |= XYTC_HAS_NAME;
    const nameB = encodeUtf8(name);
    let symbolB = new Uint8Array();
    let symbolInt = 0;
    if (typeof style.symbol === "number") {
      flags |= XYTC_SYMBOL_INT;
      symbolInt = style.symbol;
    } else if (style.symbol != null) {
      symbolB = encodeUtf8(String(style.symbol));
    }
    const opacity = Number(style.opacity ?? 1);
    let fillOpacity = 1;
    let strokeOpacity = 1;
    let lineOpacity = 1;
    if (kindClass & SCENE_KIND_CLASS_OPACITY) {
      fillOpacity = Number(style.fill_opacity ?? style.fillOpacity ?? 1);
      strokeOpacity = Number(style.stroke_opacity ?? style.strokeOpacity ?? 1);
    }
    if (kindClass & SCENE_KIND_CLASS_BAND) {
      lineOpacity = Number(style.line_opacity ?? style.lineOpacity ?? 1);
    }
    let size = Number.NaN;
    if (Object.hasOwn(style, "size") || Object.hasOwn(style, "diameter")) {
      flags |= XYTC_HAS_SIZE;
      size = Number(style.size ?? style.diameter);
    }
    let sizeCh = Number.NaN;
    const sizeChannel = trace.size_ch ?? trace.sizeChannel;
    if (sizeChannel != null) {
      flags |= XYTC_HAS_SIZE_CH;
      if (sizeChannel.constant != null) sizeCh = Number(sizeChannel.constant);
    }
    let strokeWidth = 0;
    let width = 0;
    let lineWidth = 0;
    if (Object.hasOwn(style, "stroke_width") || Object.hasOwn(style, "strokeWidth")) {
      flags |= XYTC_HAS_STROKE_WIDTH;
      strokeWidth = Number(style.stroke_width ?? style.strokeWidth);
    }
    if (Object.hasOwn(style, "width")) {
      flags |= XYTC_HAS_WIDTH;
      width = Number(style.width);
    }
    if (Object.hasOwn(style, "line_width") || Object.hasOwn(style, "lineWidth")) {
      flags |= XYTC_HAS_LINE_WIDTH;
      lineWidth = Number(style.line_width ?? style.lineWidth);
    }
    let hexDx = Number.NaN;
    let hexDy = Number.NaN;
    if (kindClass & SCENE_KIND_CLASS_HEXBIN) {
      flags |= XYTC_HAS_HEX;
      if (style.hex_dx != null || style.dx != null) hexDx = Number(style.hex_dx ?? style.dx);
      if (style.hex_dy != null || style.dy != null) hexDy = Number(style.hex_dy ?? style.dy);
    }
    if (kindClass & SCENE_KIND_CLASS_BAND) {
      const hasPerimeter = Object.hasOwn(style, "stroke_perimeter") || Object.hasOwn(style, "strokePerimeter");
      if (hasPerimeter) {
        const perimeter = Object.hasOwn(style, "stroke_perimeter") ? style.stroke_perimeter : style.strokePerimeter;
        if (typeof perimeter !== "boolean") flags |= XYTC_PERIMETER_INVALID;
        else if (perimeter === true) flags |= XYTC_PERIMETER_TRUE;
      }
    }
    let dashB = new Uint8Array();
    let dashPattern = [];
    const dash = style.dash;
    if (typeof dash === "string") dashB = encodeUtf8(dash);
    else if (Array.isArray(dash)) {
      flags |= XYTC_HAS_DASH_PATTERN;
      dashPattern = dash.map(Number);
    }
    const linecapB = (style.linecap ?? style.lineCap) != null ? encodeUtf8(String(style.linecap ?? style.lineCap)) : new Uint8Array();
    const stepB = style.step != null ? encodeUtf8(String(style.step)) : new Uint8Array();
    const curveB = style.curve != null ? encodeUtf8(String(style.curve)) : new Uint8Array();
    let fillCss = new Uint8Array();
    let fillSpace = new Uint8Array();
    let gradientBlob = new Uint8Array();
    if (Object.hasOwn(style, "fill")) {
      flags |= XYTC_HAS_FILL;
      const fill = style.fill;
      if (typeof fill === "string") fillCss = encodeUtf8(fill);
      else if (fill != null && typeof fill === "object" && fill.space != null && fill.dir != null && Array.isArray(fill.stops)) {
        flags |= XYTC_HAS_GRADIENT_SPEC;
        gradientBlob = packGradientSpec(fill) ?? new Uint8Array();
      } else if (fill != null && typeof fill === "object") {
        flags |= XYTC_HAS_FILL_DICT;
        fillCss = encodeUtf8(String(fill.gradient ?? ""));
        fillSpace = encodeUtf8(String(fill.space ?? "mark"));
      }
    }
    let strokeCss = new Uint8Array();
    if (Object.hasOwn(style, "stroke")) {
      flags |= XYTC_HAS_STROKE;
      strokeCss = encodeUtf8(style.stroke);
    }
    let lineColor = new Uint8Array();
    if (Object.hasOwn(style, "line_color") || Object.hasOwn(style, "lineColor")) {
      flags |= XYTC_HAS_LINE_COLOR;
      lineColor = encodeUtf8(style.line_color ?? style.lineColor);
    }
    const colorCss = encodeUtf8(style.color ?? (typeof trace.color === "string" ? trace.color : trace.color?.color) ?? "");
    let colorMode = new Uint8Array();
    let colorConst = new Uint8Array();
    const channel = trace.color_ch ?? trace.colorChannel;
    if (typeof channel === "string") {
      flags |= XYTC_COLOR_CH | XYTC_COLOR_CH_CONSTANT;
      colorConst = encodeUtf8(channel);
    } else if (channel != null && typeof channel === "object" && !Array.isArray(channel) && !ArrayBuffer.isView(channel)) {
      flags |= XYTC_COLOR_CH;
      colorMode = encodeUtf8(String(channel.mode ?? ""));
      if (channel.mode === "constant" && (channel.constant != null || channel.color != null)) {
        flags |= XYTC_COLOR_CH_CONSTANT;
        colorConst = encodeUtf8(String(channel.constant ?? channel.color));
      }
    }
    const color2Class = classifyRibbonColor2(trace);
    if (color2Class === "fail") flags |= XYTC_COLOR2;
    else if (color2Class === "gradient") {
      if (flags & (XYTC_HAS_FILL | XYTC_HAS_GRADIENT_SPEC)) flags |= XYTC_COLOR2;
      else {
        const spec = ribbonColor2GradientSpec(trace);
        const packed = spec == null ? null : packGradientSpec(spec);
        if (packed && packed.length) {
          flags |= XYTC_HAS_FILL | XYTC_HAS_GRADIENT_SPEC;
          gradientBlob = packed;
        } else flags |= XYTC_COLOR2;
      }
    }
    if (scatterUsesDensity(trace)) flags |= XYTC_USE_DENSITY;
    if (showLegend) flags |= XYTC_SHOW_LEGEND;
    let markerBlob = new Uint8Array();
    if (trace.kind === "scatter" && style.marker_path != null) {
      const packed = packMarkerBlob(style.marker_path);
      if (packed) {
        flags |= XYTC_HAS_MARKER;
        markerBlob = packed;
      }
    } else if (trace.kind === "scatter") {
      const packedGlyph = admittedMarkerGlyph(style.marker_glyph);
      if (packedGlyph != null) {
        flags |= XYTC_HAS_GLYPH;
        markerBlob = packedGlyph;
      }
    }
    if (trace.kind === "triangle_mesh" && (style.joined_fill || style.joinedFill)) {
      flags |= XYTC_JOINED_FILL;
    }
    const prefix = new Uint8Array(160);
    const view = new DataView(prefix.buffer);
    prefix.set(encodeUtf8("XYTR").slice(0, 4), 0);
    view.setUint16(4, 1, true);
    view.setUint16(6, kind.length, true);
    view.setUint32(8, flags >>> 0, true);
    view.setUint16(12, nameB.length, true);
    view.setUint16(14, symbolB.length, true);
    view.setFloat64(16, opacity, true);
    view.setFloat64(24, fillOpacity, true);
    view.setFloat64(32, strokeOpacity, true);
    view.setFloat64(40, lineOpacity, true);
    view.setFloat64(48, size, true);
    view.setFloat64(56, sizeCh, true);
    view.setFloat64(64, strokeWidth, true);
    view.setFloat64(72, width, true);
    view.setFloat64(80, lineWidth, true);
    view.setFloat64(88, hexDx, true);
    view.setFloat64(96, hexDy, true);
    view.setUint16(104, dashB.length, true);
    view.setUint16(106, linecapB.length, true);
    view.setUint16(108, stepB.length, true);
    view.setUint16(110, curveB.length, true);
    view.setUint16(112, fillCss.length, true);
    view.setUint16(114, strokeCss.length, true);
    view.setUint16(116, lineColor.length, true);
    view.setUint16(118, colorCss.length, true);
    view.setUint16(120, colorMode.length, true);
    view.setUint16(122, colorConst.length, true);
    view.setUint16(124, fillSpace.length, true);
    view.setUint16(126, symbolInt, true);
    view.setUint32(128, dashPattern.length, true);
    view.setUint32(132, markerBlob.length, true);
    view.setUint32(136, gradientBlob.length, true);
    let rTip = 0;
    let rBase = 0;
    let wedgeGap = 0;
    if (trace.kind === "bar" || trace.kind === "column" || trace.kind === "histogram" || trace.kind === "heatmap" || trace.kind === "violin" || trace.kind === "box") {
      const radius = style.corner_radius ?? 0;
      if (Array.isArray(radius) && radius.length === 2) {
        rTip = Number(radius[0]);
        rBase = Number(radius[1]);
      } else {
        rTip = rBase = Number(radius || 0);
      }
      if (rTip || rBase) flags |= XYTC_HAS_CORNER_RADIUS;
      if (trace.kind === "bar" || trace.kind === "column" || trace.kind === "histogram") {
        wedgeGap = Number(style.wedge_gap ?? 0);
        if (wedgeGap) flags |= XYTC_HAS_WEDGE_GAP;
      }
    }
    view.setUint32(8, flags >>> 0, true);
    view.setFloat64(140, rTip, true);
    view.setFloat64(148, rBase, true);
    view.setFloat32(156, wedgeGap, true);
    const pattern = new Uint8Array(dashPattern.length * 8);
    const patternView = new DataView(pattern.buffer);
    dashPattern.forEach((value, index) => patternView.setFloat64(index * 8, value, true));
    records.push(prefix, kind, nameB, symbolB, dashB, linecapB, stepB, curveB, fillCss, strokeCss, lineColor, colorCss, colorMode, colorConst, fillSpace, pattern, markerBlob, gradientBlob);
  }
  const header = new Uint8Array(16);
  const headerView = new DataView(header.buffer);
  header.set(encodeUtf8("XYTC").slice(0, 4), 0);
  headerView.setUint32(4, 1, true);
  headerView.setUint32(8, traces.length, true);
  return concatBytes([header, ...records]);
}

function unpackMarkerBlob(blob) {
  if (blob.length < 8) return null;
  const view = new DataView(blob.buffer, blob.byteOffset, blob.byteLength);
  const nContours = view.getUint32(0, true);
  const filled = blob[4] !== 0;
  let at = 8;
  const contours = [];
  for (let i = 0; i < nContours; i += 1) {
    const nValues = view.getUint32(at, true);
    at += 4;
    const values = [];
    for (let j = 0; j < nValues; j += 1) {
      values.push(view.getFloat64(at, true));
      at += 8;
    }
    contours.push(values);
  }
  return { contours, filled: Boolean(filled) };
}

function unpackGradientBlob(blob) {
  if (blob.length < 4) return null;
  const view = new DataView(blob.buffer, blob.byteOffset, blob.byteLength);
  const space = blob[0];
  const dir = blob[1];
  const nStops = blob[2];
  let at = 4;
  const stops = [];
  for (let i = 0; i < nStops; i += 1) {
    const t = view.getFloat32(at, true);
    stops.push([t, [blob[at + 4], blob[at + 5], blob[at + 6], blob[at + 7]]]);
    at += 8;
  }
  return { space: space ? "plot" : "mark", dir: GRAD_DIR_FROM_CODE[dir] ?? "down", stops };
}

function unpackXyTo(blob) {
  if (blob.length < 16 || blob[0] !== 88 || blob[1] !== 89 || blob[2] !== 84 || blob[3] !== 79) {
    throw new RangeError("invalid scene trace compile packing");
  }
  const view = new DataView(blob.buffer, blob.byteOffset, blob.byteLength);
  if (view.getUint32(4, true) !== 1) throw new RangeError("invalid scene trace compile facts version");
  const nTraces = view.getUint32(8, true);
  let at = 16;
  const compiled = [];
  for (let i = 0; i < nTraces; i += 1) {
    if (blob[at] !== 88 || blob[at + 1] !== 89 || blob[at + 2] !== 84 || blob[at + 3] !== 79) {
      throw new RangeError("invalid scene trace compile packing");
    }
    const fillRgba = Array.from(blob.subarray(at + 8, at + 12));
    const strokeRgba = Array.from(blob.subarray(at + 12, at + 16));
    const strokeWidth = view.getFloat64(at + 16, true);
    const diameter = view.getFloat64(at + 24, true);
    const symbol = view.getUint16(at + 32, true);
    const legendKind = blob[at + 34];
    const legendInclude = blob[at + 35] !== 0;
    const legendSymbol = view.getUint16(at + 36, true);
    const authoredStep = view.getUint16(at + 38, true);
    const factBits = view.getUint32(at + 40, true);
    const dashCount = view.getUint32(at + 44, true);
    const linecap = blob[at + 48];
    const hasMarker = blob[at + 49];
    const hasGradient = blob[at + 50];
    const markerLen = view.getUint32(at + 52, true);
    const gradientLen = view.getUint32(at + 56, true);
    const hexDx = view.getFloat64(at + 60, true);
    const hexDy = view.getFloat64(at + 68, true);
    at += 160;
    let dash = null;
    if (dashCount) {
      dash = [];
      for (let j = 0; j < dashCount; j += 1) {
        dash.push(view.getFloat64(at, true));
        at += 8;
      }
    }
    const marker = blob.subarray(at, at + markerLen);
    at += markerLen;
    const gradient = blob.subarray(at, at + gradientLen);
    at += gradientLen;
    compiled.push({
      fillRgba, strokeRgba, strokeWidth, diameter, symbol, legendKind, legendInclude, legendSymbol,
      authoredStep, factBits, hexDx, hexDy,
      dash,
      linecap: linecap === XYTO_LINECAP_NONE ? null : linecap,
      markerPath: hasMarker && marker.length ? unpackMarkerBlob(marker) : null,
      fillGradient: hasGradient && gradient.length ? unpackGradientBlob(gradient) : null,
    });
  }
  if (at !== blob.length) throw new RangeError("invalid scene trace compile packing");
  return compiled;
}

function raiseTraceCompile(code, index, figure) {
  const trace = figure.traces?.[index];
  const style = trace?.style ?? {};
  if (code === -5) throw new RangeError("trace opacity must be in [0, 1]");
  if (code === -12) throw new RangeError("trace opacity channels must be in [0, 1]");
  if (code === -6) {
    const symbol = style.symbol ?? 0;
    throw new RangeError(`Scene v12 does not support scatter symbol ${typeof symbol === "string" ? JSON.stringify(symbol) : symbol}`);
  }
  if (code === -7) throw new RangeError(`Scene v12 does not support step mode ${JSON.stringify(style.step)}`);
  if (code === -8) throw new RangeError("Scene v25 area stroke_perimeter must be a boolean");
  if (code === -9) throw new RangeError("Scene v12 hexbin requires finite hex_dx/hex_dy cell pitch");
  if (code === -10) throw new RangeError("Scene v12 does not yet encode two-ended ribbon gradients");
  if (code === -11) throw new RangeError(`Scene v12 does not yet encode ${trace?.kind ?? "mark"} non-CSS fills`);
  if (code === -13) throw new RangeError("Scene v12 does not yet support data-driven paint channels");
  if (code === -2) throw new RangeError("invalid scene trace compile facts version");
  throw new RangeError("invalid scene trace compile packing");
}

function packTraceCompile(facts) {
  const factsBytes = facts instanceof Uint8Array ? facts : new Uint8Array();
  const out = new Uint8Array(Math.max(65536, factsBytes.length + 4096));
  const code = xyScenePackTraceCompile(
    factsBytes.length ? u8Ptr(factsBytes) : 0,
    BigInt(factsBytes.length),
    u8Ptr(out),
    BigInt(out.length),
  );
  if (code < 0) {
    const index = new DataView(out.buffer, out.byteOffset, 4).getUint32(0, true);
    const error = new RangeError("invalid scene trace compile packing");
    error.code = code;
    error.index = index;
    throw error;
  }
  return out.subarray(0, code);
}

function packXyTaColormap(trace) {
  const style = trace.style ?? {};
  const colormap = style.colormap ?? trace.colormap;
  const stopSource = style.colormapStops ?? trace.colormapStops;
  let flags = 0;
  let cmap = new Uint8Array();
  let stops = new Uint8Array();
  if (typeof colormap === "string") {
    flags |= XYTA_HAS_NAMED_CMAP;
    cmap = new TextEncoder().encode(colormap);
  } else if (colormap != null || stopSource != null) {
    flags |= XYTA_HAS_STOPS;
    stops = stopSource == null
      ? Uint8Array.from(colormap.flat ? colormap.flat() : colormap)
      : Uint8Array.from(stopSource);
  }
  return { flags, cmap, stops };
}

function packXyTa(figure, xDomain, yDomain) {
  const traces = figure.traces ?? [];
  const records = [new Uint8Array(16)];
  const header = new DataView(records[0].buffer);
  records[0].set(new TextEncoder().encode("XYTA"), 0);
  header.setUint32(4, 1, true);
  header.setUint32(8, traces.length, true);
  for (const [traceIndex, trace] of traces.entries()) {
    const style = trace.style ?? {};
    const kindClass = sceneKindClass(trace.kind);
    let flags = 0;
    let rows = 0;
    let cols = 0;
    let grid = new Uint8Array();
    let rgba = new Uint8Array();
    let rgbaGrid = new Uint8Array();
    let x = new Uint8Array();
    let y = new Uint8Array();
    let meanRgba = new Uint8Array();
    let idx = new Uint8Array();
    let lut = new Uint8Array();
    let cmap = new Uint8Array();
    let stops = new Uint8Array();
    let colorCh = new Uint8Array();
    let styleColor = new Uint8Array();
    let domainX0 = Number.NaN;
    let domainX1 = Number.NaN;
    let domainY0 = Number.NaN;
    let domainY1 = Number.NaN;
    let cmapLo = Number.NaN;
    let cmapHi = Number.NaN;
    let opacity = Number.NaN;
    let fillOpacity = Number.NaN;
    if (kindClass & SCENE_KIND_CLASS_HEATMAP) {
      flags |= XYTA_HEATMAP;
      const shape = trace.grid_shape;
      if (shape != null && shape.length === 2) {
        flags |= XYTA_SHAPE;
        const rawRows = Number(shape[0]);
        const rawCols = Number(shape[1]);
        if (sceneHeatmapShapeAdmit(rawRows, rawCols)) {
          rows = rawRows;
          cols = rawCols;
        }
      }
      if (trace.grid != null) {
        flags |= XYTA_HAS_GRID;
        grid = packF64Le(trace.grid);
      }
      if (trace.rgba != null) {
        flags |= XYTA_HAS_RGBA;
        const packed = trace.rgba;
        rgba = packed instanceof Uint8Array
          ? packed
          : packed.rgba instanceof Uint8Array
            ? packed.rgba
            : Uint8Array.from(packed);
      }
      if (trace.rgba_grid != null) {
        flags |= XYTA_HAS_RGBA_GRID;
        const planes = trace.rgba_grid;
        if (planes.length === 4 && rows > 0 && cols > 0) {
          const interleaved = new Float64Array(rows * cols * 4);
          for (let row = 0; row < rows; row += 1) {
            for (let col = 0; col < cols; col += 1) {
              const index = (row * cols + col) * 4;
              for (let channel = 0; channel < 4; channel += 1) {
                interleaved[index + channel] = Number(planes[channel][row * cols + col] ?? planes[channel][row]?.[col]);
              }
            }
          }
          rgbaGrid = new Uint8Array(interleaved.buffer);
        }
      }
      const packedCmap = packXyTaColormap(trace);
      flags |= packedCmap.flags;
      cmap = packedCmap.cmap;
      stops = packedCmap.stops;
      if (style.truecolor) flags |= XYTA_TRUECOLOR;
      const domain = style.domain;
      if (domain != null && domain.length === 2) {
        flags |= XYTA_HAS_DOMAIN;
        cmapLo = Number(domain[0]);
        cmapHi = Number(domain[1]);
      }
    } else if (kindClass & SCENE_KIND_CLASS_HEXBIN && hexbinPacksColormapPlane(trace)) {
      flags |= XYTA_HEATMAP | XYTA_SHAPE | XYTA_HAS_GRID;
      const channel = trace.color_ch ?? trace.colorChannel;
      const values = channel?.values ?? trace.metric;
      grid = packF64Le(values);
      rows = 1;
      cols = values.length;
      const packedCmap = packXyTaColormap({
        ...trace,
        style: { ...style, colormap: channel?.colormap ?? style.colormap },
      });
      flags |= packedCmap.flags;
      cmap = packedCmap.cmap;
      stops = packedCmap.stops;
      const domain = channel?.domain;
      if (domain != null && domain.length === 2) {
        flags |= XYTA_HAS_DOMAIN;
        cmapLo = Number(domain[0]);
        cmapHi = Number(domain[1]);
      }
    } else if (kindClass & SCENE_KIND_CLASS_HEXBIN && hexbinPacksRgbaPlane(trace)) {
      const packed = hexbinCellRgba8(trace);
      if (packed != null) {
        flags |= XYTA_HEATMAP | XYTA_SHAPE | XYTA_HAS_GRID | XYTA_HAS_RGBA;
        rows = 1;
        cols = packed.length / 4;
        grid = packF64Le(new Float64Array(cols));
        rgba = packed;
      }
    } else if (
      kindClass & SCENE_KIND_CLASS_RIBBON
      && figure.coords !== "polar"
      && ribbonPacksEndPaints(trace)
    ) {
      const ends = ribbonEndRgbaPair(trace);
      if (ends != null) {
        flags |= XYTA_RIBBON_ENDS | XYTA_SHAPE | XYTA_HAS_RGBA;
        rows = 1;
        cols = ends.source.length / 4;
        rgba = ends.source;
        meanRgba = ends.target;
      }
    } else if (meshPacksPaintPlane(trace)) {
      const packed = meshFacePaints(trace);
      if (packed != null) {
        flags |= XYTA_MESH_FACES | XYTA_SHAPE | XYTA_HAS_RGBA;
        rows = 1;
        cols = packed.fills.length / 4;
        rgba = packed.fills;
        meanRgba = packed.strokes;
        x = packed.widths;
      }
    } else if (scatterPacksPaintPlane(trace)) {
      const packed = scatterPointPaints(trace);
      if (packed != null) {
        flags |= XYTA_SCATTER_PAINT | XYTA_SHAPE | XYTA_HAS_RGBA;
        rows = 1;
        cols = packed.fills.length / 4;
        rgba = packed.fills;
        meanRgba = packed.strokes;
        x = packed.widths;
      }
    } else if ((trace.kind ?? "scatter") === "scatter" && scatterUsesDensity(trace)) {
      flags |= XYTA_DENSITY;
      if (trace.x != null) x = packF64Le(asF64Array(trace.x, "x"));
      if (trace.y != null) y = packF64Le(asF64Array(trace.y, "y"));
      domainX0 = Number(xDomain[0]);
      domainX1 = Number(xDomain[1]);
      domainY0 = Number(yDomain[0]);
      domainY1 = Number(yDomain[1]);
      const packedCmap = packXyTaColormap(trace);
      flags |= packedCmap.flags;
      cmap = packedCmap.cmap;
      stops = packedCmap.stops;
      const channel = trace.color_ch ?? trace.colorChannel;
      if (channel != null && channel.mode === "constant" && channel.constant != null) {
        flags |= XYTA_HAS_COLOR_CH;
        colorCh = new TextEncoder().encode(String(channel.constant));
      }
      if (style.color != null) {
        flags |= XYTA_HAS_STYLE_COLOR;
        styleColor = new TextEncoder().encode(String(style.color));
      }
      if (Object.hasOwn(style, "opacity")) {
        flags |= XYTA_HAS_OPACITY;
        opacity = Number(style.opacity);
      }
      if (Object.hasOwn(style, "fill_opacity") || Object.hasOwn(style, "fillOpacity")) {
        flags |= XYTA_HAS_FILL_OPACITY;
        fillOpacity = Number(style.fill_opacity ?? style.fillOpacity);
      }
      const source = resolveDensityBinColors(trace);
      if (source?.rgba != null) {
        meanRgba = source.rgba instanceof Uint8Array ? source.rgba : Uint8Array.from(source.rgba);
      } else if (source?.idx != null && source?.lut != null) {
        idx = source.idx instanceof Uint8Array ? source.idx : Uint8Array.from(source.idx);
        lut = source.lut instanceof Uint8Array ? source.lut : Uint8Array.from(source.lut);
      }
    }
    const prefix = new Uint8Array(128);
    const view = new DataView(prefix.buffer);
    view.setUint32(0, flags, true);
    view.setUint32(4, Number(trace.id ?? traceIndex) >>> 0, true);
    view.setInt32(8, rows, true);
    view.setInt32(12, cols, true);
    view.setUint32(16, grid.length / 8, true);
    view.setUint32(20, rgba.length, true);
    view.setUint32(24, rgbaGrid.length / 8, true);
    view.setUint32(28, x.length / 8, true);
    view.setUint32(32, y.length / 8, true);
    view.setUint32(36, meanRgba.length, true);
    view.setUint32(40, idx.length, true);
    view.setUint32(44, lut.length, true);
    view.setUint16(48, Math.min(cmap.length, 65535), true);
    view.setUint16(50, Math.min(stops.length, 65535), true);
    view.setUint16(52, Math.min(colorCh.length, 65535), true);
    view.setUint16(54, Math.min(styleColor.length, 65535), true);
    view.setFloat64(56, domainX0, true);
    view.setFloat64(64, domainX1, true);
    view.setFloat64(72, domainY0, true);
    view.setFloat64(80, domainY1, true);
    view.setFloat64(88, cmapLo, true);
    view.setFloat64(96, cmapHi, true);
    view.setFloat32(104, opacity, true);
    view.setFloat32(108, fillOpacity, true);
    records.push(
      prefix, grid, rgba, rgbaGrid,
      cmap.subarray(0, 65535), stops.subarray(0, 65535),
      colorCh.subarray(0, 65535), styleColor.subarray(0, 65535),
      x, y, meanRgba, idx, lut,
    );
  }
  return concatBytes(records);
}

function unpackXyTt(blob) {
  if (blob.length < 16 || blob[0] !== 88 || blob[1] !== 89 || blob[2] !== 84 || blob[3] !== 84) {
    throw new RangeError("invalid scene trace attach packing");
  }
  const view = new DataView(blob.buffer, blob.byteOffset, blob.byteLength);
  if (view.getUint32(4, true) !== 1) throw new RangeError("invalid scene trace attach facts version");
  const nTraces = view.getUint32(8, true);
  let at = 16;
  const attached = [];
  for (let i = 0; i < nTraces; i += 1) {
    if (blob[at] !== 88 || blob[at + 1] !== 89 || blob[at + 2] !== 84 || blob[at + 3] !== 79) {
      throw new RangeError("invalid scene trace attach packing");
    }
    const fillRgba = Array.from(blob.subarray(at + 8, at + 12));
    const strokeRgba = Array.from(blob.subarray(at + 12, at + 16));
    const strokeWidth = view.getFloat64(at + 16, true);
    const diameter = view.getFloat64(at + 24, true);
    const symbol = view.getUint16(at + 32, true);
    const legendKind = blob[at + 34];
    const legendInclude = blob[at + 35] !== 0;
    const legendSymbol = view.getUint16(at + 36, true);
    const authoredStep = view.getUint16(at + 38, true);
    const factBits = view.getUint32(at + 40, true);
    const dashCount = view.getUint32(at + 44, true);
    const linecap = blob[at + 48];
    const hasMarker = blob[at + 49];
    const hasGradient = blob[at + 50];
    const markerLen = view.getUint32(at + 52, true);
    const gradientLen = view.getUint32(at + 56, true);
    const hexDx = view.getFloat64(at + 60, true);
    const hexDy = view.getFloat64(at + 68, true);
    const heatmapLen = view.getUint32(at + 160, true);
    const densityLen = view.getUint32(at + 164, true);
    const gridRows = view.getUint32(at + 168, true);
    const gridCols = view.getUint32(at + 172, true);
    const rewriteX0 = view.getFloat64(at + 176, true);
    const rewriteX1 = view.getFloat64(at + 184, true);
    const rewriteY0 = view.getFloat64(at + 192, true);
    const rewriteY1 = view.getFloat64(at + 200, true);
    at += 208;
    let dash = null;
    if (dashCount) {
      dash = [];
      for (let j = 0; j < dashCount; j += 1) {
        dash.push(view.getFloat64(at, true));
        at += 8;
      }
    }
    const marker = blob.subarray(at, at + markerLen);
    at += markerLen;
    const gradient = blob.subarray(at, at + gradientLen);
    at += gradientLen;
    const heatmap = blob.subarray(at, at + heatmapLen);
    at += heatmapLen;
    const density = blob.subarray(at, at + densityLen);
    at += densityLen;
    attached.push({
      fillRgba, strokeRgba, strokeWidth, diameter, symbol, legendKind, legendInclude, legendSymbol,
      authoredStep, factBits, hexDx, hexDy,
      dash,
      linecap: linecap === XYTO_LINECAP_NONE ? null : linecap,
      markerPath: hasMarker && marker.length ? unpackMarkerBlob(marker) : null,
      fillGradient: hasGradient && gradient.length ? unpackGradientBlob(gradient) : null,
      heatmap: heatmapLen ? heatmap : new Uint8Array(),
      density: densityLen ? density : new Uint8Array(),
      gridRows,
      gridCols,
      packX: densityLen ? [rewriteX0, rewriteX1] : null,
      packY: densityLen ? [rewriteY0, rewriteY1] : null,
    });
  }
  if (at !== blob.length) throw new RangeError("invalid scene trace attach packing");
  return attached;
}

function raiseTraceAttach(code, index, figure) {
  const trace = figure.traces?.[index];
  if (code === -5) throw new RangeError("Scene v12 heatmap requires a rows x cols grid_shape");
  if (code === -6) throw new RangeError("Scene v12 heatmap requires a positive grid_shape");
  if (code === -7) throw new RangeError("heatmap Scene v12 compilation requires a scalar grid");
  if (code === -8) throw new RangeError("Scene v12 heatmap grid must match rows x cols");
  if (code === -9) throw new RangeError("Scene v12 does not yet encode missing-data breaks or nonfinite coordinates");
  if (code === -10) throw new RangeError("Scene heatmap RGBA plane must match rows x cols");
  if (code === -11) throw new RangeError("Scene heatmap truecolor requires four RGBA planes");
  if (code === -12) {
    const label = trace?.kind === "scatter" ? "density" : "heatmap";
    throw new RangeError(`Scene ${label} colormap requires RGB stops`);
  }
  if (code === -13) throw new RangeError("Scene density columns must have equal length");
  if (code === -14) throw new RangeError("Scene density mean-color source is invalid");
  if (code === -2) throw new RangeError("invalid scene trace attach facts version");
  throw new RangeError("invalid scene trace attach packing");
}

function packTraceAttach(compiled, attach) {
  const compiledBytes = compiled instanceof Uint8Array ? compiled : new Uint8Array();
  const attachBytes = attach instanceof Uint8Array ? attach : new Uint8Array();
  let capacity = Math.max(65536, compiledBytes.length + attachBytes.length + 32 + 512 * 384 * 5 + 4096);
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const out = new Uint8Array(capacity);
    const code = xyScenePackTraceAttach(
      compiledBytes.length ? u8Ptr(compiledBytes) : 0,
      BigInt(compiledBytes.length),
      attachBytes.length ? u8Ptr(attachBytes) : 0,
      BigInt(attachBytes.length),
      u8Ptr(out),
      BigInt(out.length),
    );
    if (code === -4) {
      capacity *= 2;
      continue;
    }
    if (code < 0) {
      const index = new DataView(out.buffer, out.byteOffset, 4).getUint32(0, true);
      const error = new RangeError("invalid scene trace attach packing");
      error.code = code;
      error.index = index;
      throw error;
    }
    return out.subarray(0, code);
  }
  const error = new RangeError("invalid scene trace attach packing");
  error.code = -4;
  error.index = 0;
  throw error;
}

function packXyCl(figure) {
  const traces = figure.traces ?? [];
  const coords = (figure.coords ?? "cartesian") === "polar" ? 1 : 0;
  const records = [new Uint8Array(16)];
  const header = new DataView(records[0].buffer);
  records[0][0] = 88; records[0][1] = 89; records[0][2] = 67; records[0][3] = 76; // XYCL
  header.setUint32(4, 1, true);
  header.setUint32(8, traces.length, true);
  for (const trace of traces) {
    const kind = new TextEncoder().encode(String(trace.kind ?? ""));
    const cols = [trace.x, trace.y, trace.x0, trace.y0, trace.x1, trace.y1, trace.base].map((column) => {
      if (column == null || column.length === 0) return new Uint8Array();
      const arr = asF64Array(column, "trace column");
      return new Uint8Array(arr.buffer, arr.byteOffset, arr.byteLength);
    });
    const prefix = new Uint8Array(48);
    const view = new DataView(prefix.buffer);
    view.setUint16(0, kind.length, true);
    prefix[2] = coords;
    view.setBigUint64(8, asU64(Number(trace.id), "stableIds value"), true);
    view.setUint32(16, cols[0].length / 8, true);
    view.setUint32(20, cols[1].length / 8, true);
    view.setUint32(24, cols[2].length / 8, true);
    view.setUint32(28, cols[3].length / 8, true);
    view.setUint32(32, cols[4].length / 8, true);
    view.setUint32(36, cols[5].length / 8, true);
    view.setUint32(40, cols[6].length / 8, true);
    records.push(prefix, kind, ...cols);
  }
  return concatBytes(records);
}

function raiseTraceRows(code, index) {
  if (code === -5) throw new RangeError("Scene v12 does not yet encode missing-data breaks or nonfinite coordinates");
  if (code === -6) throw new RangeError("Scene v12 does not support product kind");
  if (code === -1) throw new RangeError("invalid scene trace packing");
  if (code === -2) throw new RangeError("invalid scene trace column facts version");
  const error = new RangeError("invalid scene trace column packing");
  error.code = code;
  error.index = index;
  throw error;
}

function packTraceRows(attached, columns) {
  const packed = packTraceRowBytes(attached, columns);
  return decodePackedRows(packed, packed.length / 56);
}

function packXyNm(traces) {
  const records = [new Uint8Array(16)];
  const header = new DataView(records[0].buffer);
  records[0][0] = 88; records[0][1] = 89; records[0][2] = 78; records[0][3] = 77; // XYNM
  header.setUint32(4, 1, true);
  header.setUint32(8, traces.length, true);
  for (const trace of traces) {
    const raw = encodeUtf8(trace.name == null ? "" : String(trace.name));
    const prefix = new Uint8Array(2);
    new DataView(prefix.buffer).setUint16(0, raw.length, true);
    records.push(prefix, raw);
  }
  return concatBytes(records);
}

function unpackXySd(blob) {
  if (blob.length < 16 || blob[0] !== 88 || blob[1] !== 89 || blob[2] !== 83 || blob[3] !== 68) {
    throw new RangeError("invalid scene sidecar packing");
  }
  const view = new DataView(blob.buffer, blob.byteOffset, blob.byteLength);
  if (view.getUint32(4, true) !== 1) throw new RangeError("invalid scene sidecar facts version");
  const nTraces = view.getUint32(8, true);
  let at = 16;
  const styles = [];
  const dashes = [];
  const linecaps = [];
  const markerPaths = [];
  const fillGradients = [];
  const planes = [];
  const legend = [];
  for (let i = 0; i < nTraces; i += 1) {
    if (at + 48 > blob.length) throw new RangeError("invalid scene sidecar packing");
    const fillRgba = Array.from(blob.subarray(at, at + 4));
    const strokeRgba = Array.from(blob.subarray(at + 4, at + 8));
    const strokeWidth = view.getFloat64(at + 8, true);
    const linecap = blob[at + 16];
    const legendKind = blob[at + 17];
    const legendSymbol = view.getUint16(at + 18, true);
    const dashLen = view.getUint32(at + 20, true);
    const markerLen = view.getUint32(at + 24, true);
    const gradientLen = view.getUint32(at + 28, true);
    const planeLen = view.getUint32(at + 32, true);
    const nameLen = view.getUint32(at + 36, true);
    at += 48;
    if (at + dashLen + markerLen + gradientLen + planeLen + nameLen > blob.length) {
      throw new RangeError("invalid scene sidecar packing");
    }
    let dash = null;
    if (dashLen) {
      dash = [];
      for (let j = 0; j < dashLen / 8; j += 1) {
        dash.push(view.getFloat64(at + j * 8, true));
      }
    }
    at += dashLen;
    const marker = blob.subarray(at, at + markerLen);
    at += markerLen;
    const gradient = blob.subarray(at, at + gradientLen);
    at += gradientLen;
    const plane = blob.subarray(at, at + planeLen);
    at += planeLen;
    const name = blob.subarray(at, at + nameLen);
    at += nameLen;
    styles.push({ fillRgba, strokeRgba, strokeWidth });
    dashes.push(dash);
    linecaps.push(linecap === XYTO_LINECAP_NONE ? null : linecap);
    markerPaths.push(marker.length ? unpackMarkerBlob(marker) : null);
    fillGradients.push(gradient.length ? unpackGradientBlob(gradient) : null);
    if (plane.length) planes.push(Uint8Array.from(plane));
    if (name.length) {
      legend.push({
        styleRef: i,
        kind: legendKind,
        symbol: legendSymbol,
        label: new TextDecoder().decode(name),
      });
    }
  }
  if (at !== blob.length) throw new RangeError("invalid scene sidecar packing");
  return { styles, dashes, linecaps, markerPaths, fillGradients, planes, legend };
}

function raiseTraceSidecars(code, index) {
  if (code === -2) throw new RangeError("invalid scene sidecar facts version");
  const error = new RangeError("invalid scene sidecar packing");
  error.code = code;
  error.index = index;
  throw error;
}

function packTraceSidecars(attached, names) {
  const attachedBytes = attached instanceof Uint8Array ? attached : new Uint8Array();
  const namesBytes = names instanceof Uint8Array ? names : new Uint8Array();
  let capacity = Math.max(65536, attachedBytes.length + namesBytes.length + 4096);
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const out = new Uint8Array(capacity);
    const code = xyScenePackTraceSidecars(
      attachedBytes.length ? u8Ptr(attachedBytes) : 0,
      BigInt(attachedBytes.length),
      namesBytes.length ? u8Ptr(namesBytes) : 0,
      BigInt(namesBytes.length),
      u8Ptr(out),
      BigInt(out.length),
    );
    if (code === -4) {
      capacity *= 2;
      continue;
    }
    if (code < 0) {
      const failing = new DataView(out.buffer, out.byteOffset, 4).getUint32(0, true);
      raiseTraceSidecars(code, failing);
    }
    return out.subarray(0, code);
  }
  raiseTraceSidecars(-4, 0);
}

function packStyleSidecars(sidecars, annotations) {
  const sidecarBytes = sidecars instanceof Uint8Array ? sidecars : new Uint8Array();
  const annotationBytes = annotations instanceof Uint8Array ? annotations : new Uint8Array();
  let capacity = Math.max(65536, sidecarBytes.length + annotationBytes.length + 4096);
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const out = new Uint8Array(capacity);
    const code = xyScenePackStyleSidecars(
      sidecarBytes.length ? u8Ptr(sidecarBytes) : 0,
      BigInt(sidecarBytes.length),
      annotationBytes.length ? u8Ptr(annotationBytes) : 0,
      BigInt(annotationBytes.length),
      u8Ptr(out),
      BigInt(out.length),
    );
    if (code === -4) {
      capacity *= 2;
      continue;
    }
    if (code < 0) {
      const failing = new DataView(out.buffer, out.byteOffset, 4).getUint32(0, true);
      const error = new RangeError(code === -2 ? "invalid scene style sidecar facts version" : "invalid scene style sidecar packing");
      error.code = code;
      error.index = failing;
      throw error;
    }
    return out.subarray(0, code);
  }
  const error = new RangeError("invalid scene style sidecar packing");
  error.code = -4;
  error.index = 0;
  throw error;
}

function spliceAnnotations(rows, sidecars, annotations) {
  const rowBytes = rows instanceof Uint8Array ? rows : new Uint8Array();
  const sidecarBytes = sidecars instanceof Uint8Array ? sidecars : new Uint8Array();
  const annotationBytes = annotations instanceof Uint8Array ? annotations : new Uint8Array();
  let capacity = Math.max(65536, rowBytes.length + sidecarBytes.length + annotationBytes.length + 4096);
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const out = new Uint8Array(capacity);
    const code = xySceneSpliceAnnotations(
      rowBytes.length ? u8Ptr(rowBytes) : 0,
      BigInt(rowBytes.length),
      sidecarBytes.length ? u8Ptr(sidecarBytes) : 0,
      BigInt(sidecarBytes.length),
      annotationBytes.length ? u8Ptr(annotationBytes) : 0,
      BigInt(annotationBytes.length),
      u8Ptr(out),
      BigInt(out.length),
    );
    if (code === -4) {
      capacity *= 2;
      continue;
    }
    if (code < 0) {
      const failing = new DataView(out.buffer, out.byteOffset, 4).getUint32(0, true);
      const error = new RangeError(code === -2 ? "invalid scene annotation splice version" : "invalid scene annotation splice packing");
      error.code = code;
      error.index = failing;
      throw error;
    }
    return out.subarray(0, code);
  }
  const error = new RangeError("invalid scene annotation splice packing");
  error.code = -4;
  error.index = 0;
  throw error;
}

function encodeAssembled(xyas, chrome, extras, { viewport, xAxis, yAxis }) {
  if (!Array.isArray(viewport) || viewport.length !== 2) {
    throw new RangeError("viewport must contain two values");
  }
  const xyasBytes = xyas instanceof Uint8Array ? xyas : new Uint8Array();
  const chromeBytes = chrome instanceof Uint8Array ? chrome : new Uint8Array();
  const extrasBytes = extras instanceof Uint8Array ? extras : new Uint8Array();
  const xd = axisDescriptor(xAxis, "xAxis");
  const yd = axisDescriptor(yAxis, "yAxis");
  let capacity = Math.max(65536, xyasBytes.length + chromeBytes.length + extrasBytes.length + 4096);
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const out = new Uint8Array(capacity);
    const code = xySceneEncodeAssembled(
      xyasBytes.length ? u8Ptr(xyasBytes) : 0,
      BigInt(xyasBytes.length),
      chromeBytes.length ? u8Ptr(chromeBytes) : 0,
      BigInt(chromeBytes.length),
      extrasBytes.length ? u8Ptr(extrasBytes) : 0,
      BigInt(extrasBytes.length),
      Number(viewport[0]),
      Number(viewport[1]),
      ...xd,
      ...yd,
      u8Ptr(out),
      BigInt(out.length),
    );
    if (code === -4) {
      capacity *= 2;
      continue;
    }
    if (code < 0) {
      const failing = new DataView(out.buffer, out.byteOffset, 4).getUint32(0, true);
      const error = new RangeError(code === -2 ? "invalid scene encode assembled version" : "invalid canonical scene batch");
      error.code = code;
      error.index = failing;
      throw error;
    }
    return out.subarray(0, code);
  }
  const error = new RangeError("invalid canonical scene batch");
  error.code = -4;
  error.index = 0;
  throw error;
}

function encodeAssembledFromSidecars(xyas, chromeFacts, xysd, polar, extrasFacts) {
  const xyasBytes = xyas instanceof Uint8Array ? xyas : new Uint8Array();
  const chromeBytes = chromeFacts instanceof Uint8Array ? chromeFacts : new Uint8Array();
  const xysdBytes = xysd instanceof Uint8Array ? xysd : new Uint8Array();
  const polarBytes = polar instanceof Uint8Array ? polar : new Uint8Array();
  const extrasBytes = extrasFacts instanceof Uint8Array ? extrasFacts : new Uint8Array();
  let capacity = Math.max(
    65536,
    xyasBytes.length + chromeBytes.length + xysdBytes.length + polarBytes.length + extrasBytes.length + 4096,
  );
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const out = new Uint8Array(capacity);
    const code = xySceneEncodeAssembledFromSidecars(
      xyasBytes.length ? u8Ptr(xyasBytes) : 0,
      BigInt(xyasBytes.length),
      chromeBytes.length ? u8Ptr(chromeBytes) : 0,
      BigInt(chromeBytes.length),
      xysdBytes.length ? u8Ptr(xysdBytes) : 0,
      BigInt(xysdBytes.length),
      polarBytes.length ? u8Ptr(polarBytes) : 0,
      BigInt(polarBytes.length),
      extrasBytes.length ? u8Ptr(extrasBytes) : 0,
      BigInt(extrasBytes.length),
      u8Ptr(out),
      BigInt(out.length),
    );
    if (code === -4) {
      capacity *= 2;
      continue;
    }
    if (code === -2) throw new RangeError("invalid scene chrome facts version");
    if (code === -5) throw new RangeError("invalid canonical scene plot layout");
    if (code === -7) throw new RangeError("Scene v12 primary legends do not yet encode anchors, multiple columns, or custom content");
    if (code === -8) throw new RangeError("Scene v12 primary legends are static; toggle and highlight must be false");
    if (code === -9) throw new RangeError("Scene v12 does not support legend location");
    if (code === -10) throw new RangeError("legend font sizes must be finite and in [1, 1000]");
    if (code === -11) throw new RangeError("Scene v12 legends support only background, color, font_size, and title_font_size");
    if (code === -12) throw new RangeError("Scene v19 colorbars require literal bounded RGBA stops");
    if (code === -13) throw new RangeError("Scene v19 colorbars require a two-value domain and 2–16 stops");
    if (code === -14) throw new RangeError("Scene v19 colorbar side is right or bottom");
    if (code === -15) throw new RangeError("scene axis tick lists are limited to 200 values");
    if (code === -16) {
      const failing = new DataView(out.buffer, out.byteOffset, 4).getUint32(0, true);
      const error = new RangeError("invalid canonical scene batch");
      error.code = code;
      error.index = failing;
      throw error;
    }
    if (code === -20) throw new RangeError("Scene extras polar or paint envelope is invalid");
    if (code === -21) throw new RangeError("Scene style sidecar facts are invalid");
    if (code === -17 || code === -18 || code === -19) throw new RangeError("invalid scene extras packing");
    if (code < 0) throw new RangeError("invalid scene chrome packing");
    return out.subarray(0, code);
  }
  const error = new RangeError("invalid canonical scene batch");
  error.code = -4;
  error.index = 0;
  throw error;
}

function encodeProduct(
  compileFacts,
  attachFacts,
  names,
  columns,
  annotationFacts,
  styleRefBase,
  xDomain,
  yDomain,
  chromeFacts,
  polar,
  figureSupport,
) {
  const compileBytes = compileFacts instanceof Uint8Array ? compileFacts : new Uint8Array();
  const attachBytes = attachFacts instanceof Uint8Array ? attachFacts : new Uint8Array();
  const namesBytes = names instanceof Uint8Array ? names : new Uint8Array();
  const columnBytes = columns instanceof Uint8Array ? columns : new Uint8Array();
  const annotationBytes = annotationFacts instanceof Uint8Array ? annotationFacts : new Uint8Array();
  const chromeBytes = chromeFacts instanceof Uint8Array ? chromeFacts : new Uint8Array();
  const polarBytes = polar instanceof Uint8Array ? polar : new Uint8Array();
  const supportBytes = figureSupport instanceof Uint8Array ? figureSupport : new Uint8Array();
  let capacity = Math.max(
    65536,
    compileBytes.length
      + attachBytes.length
      + namesBytes.length
      + columnBytes.length
      + annotationBytes.length
      + chromeBytes.length
      + polarBytes.length
      + supportBytes.length
      + 32
      + 512 * 384 * 5
      + 4096,
  );
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const out = new Uint8Array(capacity);
    const code = xySceneEncodeProduct(
      compileBytes.length ? u8Ptr(compileBytes) : 0,
      BigInt(compileBytes.length),
      attachBytes.length ? u8Ptr(attachBytes) : 0,
      BigInt(attachBytes.length),
      namesBytes.length ? u8Ptr(namesBytes) : 0,
      BigInt(namesBytes.length),
      columnBytes.length ? u8Ptr(columnBytes) : 0,
      BigInt(columnBytes.length),
      annotationBytes.length ? u8Ptr(annotationBytes) : 0,
      BigInt(annotationBytes.length),
      styleRefBase >>> 0,
      Number(xDomain[0]),
      Number(xDomain[1]),
      Number(yDomain[0]),
      Number(yDomain[1]),
      chromeBytes.length ? u8Ptr(chromeBytes) : 0,
      BigInt(chromeBytes.length),
      polarBytes.length ? u8Ptr(polarBytes) : 0,
      BigInt(polarBytes.length),
      supportBytes.length ? u8Ptr(supportBytes) : 0,
      BigInt(supportBytes.length),
      u8Ptr(out),
      BigInt(out.length),
    );
    if (code === -4) {
      capacity *= 2;
      continue;
    }
    if (code === -801) {
      const n = new DataView(out.buffer, out.byteOffset, 4).getUint32(0, true);
      throw new RangeError(new TextDecoder("utf-8", { fatal: true }).decode(out.subarray(4, 4 + n)));
    }
    if (code === -802) throw new RangeError("invalid scene figure support envelope");
    const failing = new DataView(out.buffer, out.byteOffset, 4).getUint32(0, true);
    const magnitude = Math.abs(code);
    if (code < 0 && magnitude >= 100) {
      const error = new RangeError("invalid product encode");
      error.code = -(magnitude % 100);
      error.index = failing;
      error.stage = Math.floor(magnitude / 100);
      throw error;
    }
    if (code === -2) throw new RangeError("invalid scene chrome facts version");
    if (code === -5) throw new RangeError("invalid canonical scene plot layout");
    if (code === -7) throw new RangeError("Scene v12 primary legends do not yet encode anchors, multiple columns, or custom content");
    if (code === -8) throw new RangeError("Scene v12 primary legends are static; toggle and highlight must be false");
    if (code === -9) throw new RangeError("Scene v12 does not support legend location");
    if (code === -10) throw new RangeError("legend font sizes must be finite and in [1, 1000]");
    if (code === -11) throw new RangeError("Scene v12 legends support only background, color, font_size, and title_font_size");
    if (code === -12) throw new RangeError("Scene v19 colorbars require literal bounded RGBA stops");
    if (code === -13) throw new RangeError("Scene v19 colorbars require a two-value domain and 2–16 stops");
    if (code === -14) throw new RangeError("Scene v19 colorbar side is right or bottom");
    if (code === -15) throw new RangeError("scene axis tick lists are limited to 200 values");
    if (code === -16) {
      const error = new RangeError("invalid canonical scene batch");
      error.code = code;
      error.index = failing;
      throw error;
    }
    if (code === -20) throw new RangeError("Scene extras polar or paint envelope is invalid");
    if (code === -21) throw new RangeError("Scene style sidecar facts are invalid");
    if (code === -17 || code === -18 || code === -19) throw new RangeError("invalid scene extras packing");
    if (code < 0) throw new RangeError("invalid scene chrome packing");
    return out.subarray(0, code);
  }
  const error = new RangeError("invalid canonical scene batch");
  error.code = -4;
  error.index = 0;
  throw error;
}

function unpackXyAs(blob) {
  if (blob.length < 24 || blob[0] !== 88 || blob[1] !== 89 || blob[2] !== 65 || blob[3] !== 83) {
    throw new RangeError("invalid scene annotation splice packing");
  }
  const view = new DataView(blob.buffer, blob.byteOffset, blob.byteLength);
  if (view.getUint32(4, true) !== 1) throw new RangeError("invalid scene annotation splice version");
  const nStyles = view.getUint32(8, true);
  const nRows = view.getUint32(12, true);
  const xyadLen = view.getUint32(16, true);
  let at = 24;
  const need = nStyles * 16 + nRows * 56 + xyadLen;
  if (at + need > blob.length) throw new RangeError("invalid scene annotation splice packing");
  const styles = [];
  for (let i = 0; i < nStyles; i += 1) {
    styles.push({
      fillRgba: Array.from(blob.subarray(at, at + 4)),
      strokeRgba: Array.from(blob.subarray(at + 4, at + 8)),
      strokeWidth: view.getFloat64(at + 8, true),
    });
    at += 16;
  }
  const packed = blob.subarray(at, at + nRows * 56);
  at += nRows * 56;
  const xyad = blob.subarray(at, at + xyadLen);
  if (at + xyadLen !== blob.length) throw new RangeError("invalid scene annotation splice packing");
  const rows = nRows
    ? decodePackedRows(packed, nRows)
    : { kinds: [], stableIds: [], styleRefs: [], diameter: [], symbols: [], expansion: [], x0: [], y0: [], x1: [], y1: [] };
  return { styles, xyad, ...rows };
}

function packChromeFacts(figure, { width, height, margins = null, colorbarOk = true } = {}) {
  const FLAG_AUTHORED_MARGINS = 1 << 0, FLAG_PADDING = 1 << 1, FLAG_X_MAJOR_AUTO = 1 << 2, FLAG_Y_MAJOR_AUTO = 1 << 3;
  const FLAG_X_TICK_LABELS = 1 << 4, FLAG_Y_TICK_LABELS = 1 << 5, FLAG_HAS_CHROME = 1 << 6, FLAG_HAS_LEGEND = 1 << 7, FLAG_HAS_COLORBAR = 1 << 8;
  const LEGEND_AUTHORED_LOC = 1 << 0, LEGEND_AUTHORED_FONT = 1 << 1, LEGEND_AUTHORED_TITLE_FONT = 1 << 2;
  const LEGEND_AUTHORED_COLOR = 1 << 3, LEGEND_AUTHORED_BACKGROUND = 1 << 4, LEGEND_UNSUPPORTED_KEYS = 1 << 5;
  const LEGEND_TOGGLE = 1 << 6, LEGEND_HIGHLIGHT = 1 << 7, LEGEND_SHOW = 1 << 8, LEGEND_UNSUPPORTED_STYLE = 1 << 9;
  const CB_HORIZONTAL = 1 << 1, CB_MINOR = 1 << 2, CB_INVALID_SIDE = 1 << 4;
  let flags = FLAG_HAS_CHROME | FLAG_X_MAJOR_AUTO | FLAG_Y_MAJOR_AUTO;
  const xAxis = figure.xAxis ?? figure.x_axis ?? {};
  const yAxis = figure.yAxis ?? figure.y_axis ?? {};
  const xDomain = figure._range("x");
  const yDomain = figure._range("y");
  const kindCode = (kind) => kind === "log" ? 1 : kind === "symlog" ? 2 : 0;
  const authoredMargins = [0, 0, 0, 0];
  if (margins != null) {
    flags |= FLAG_AUTHORED_MARGINS;
    authoredMargins[0] = Number(margins[0]); authoredMargins[1] = Number(margins[1]);
    authoredMargins[2] = Number(margins[2]); authoredMargins[3] = Number(margins[3]);
  }
  const padding = [0, 0, 0, 0];
  const pad = figure.padding;
  if (Array.isArray(pad) && pad.length === 4) {
    flags |= FLAG_PADDING;
    padding[0] = Number(pad[0]); padding[1] = Number(pad[1]); padding[2] = Number(pad[2]); padding[3] = Number(pad[3]);
  }
  const title = encodeUtf8(String(figure.title ?? ""));
  const xLabel = encodeUtf8(String(figure.xLabel ?? figure.x_label ?? xAxis.label ?? ""));
  const yLabel = encodeUtf8(String(figure.yLabel ?? figure.y_label ?? yAxis.label ?? ""));
  const xFormat = xAxis.format == null ? new Uint8Array() : encodeUtf8(String(xAxis.format));
  const yFormat = yAxis.format == null ? new Uint8Array() : encodeUtf8(String(yAxis.format));
  let xMajor = [], yMajor = [];
  const xTicks = xAxis.tickValues ?? xAxis.tick_values;
  const yTicks = yAxis.tickValues ?? yAxis.tick_values;
  // ABI 199: Rust pack_figure_chrome filters authored majors through the tick window.
  if (xTicks != null) { flags &= ~FLAG_X_MAJOR_AUTO; xMajor = Array.from(xTicks, Number); }
  if (yTicks != null) { flags &= ~FLAG_Y_MAJOR_AUTO; yMajor = Array.from(yTicks, Number); }
  const xMinor = Array.from(xAxis.minorTickValues ?? xAxis.minor_tick_values ?? [], Number);
  const yMinor = Array.from(yAxis.minorTickValues ?? yAxis.minor_tick_values ?? [], Number);
  // ABI 200: Rust pack_figure_chrome filters authored minors through the tick window.
  // ABI 201: product encode passes packed XYPL so polar theta uses the modular sector.
  // ABI 202: hosts pack domain tick-kind (linear/time/category) in XYCF 154–155.
  // ABI 203: hosts pack ABI 123 collision strategy/anchor/gaps in XYCF 12–15.
  const xLabels = xAxis.tickLabels ?? xAxis.tick_labels ?? null;
  const yLabels = yAxis.tickLabels ?? yAxis.tick_labels ?? null;
  if (xLabels != null) flags |= FLAG_X_TICK_LABELS;
  if (yLabels != null) flags |= FLAG_Y_TICK_LABELS;
  const chrome = packXyCh(figure);
  let legendLoc = new Uint8Array(), legendTitle = new Uint8Array(), legendNcols = 1;
  let legendFont = 0, legendTitleFont = 0, legendFlags = 0;
  let legendTextRgba = new Uint8Array(4), legendFrameRgba = new Uint8Array(4);
  let legendMeta = new Uint8Array(), legendLens = [], legendBlob = new Uint8Array();
  let legendCount = 0;
  if (figure.showLegend !== false) {
    flags |= FLAG_HAS_LEGEND;
    legendFlags |= LEGEND_SHOW;
    const options = figure.legend ?? {};
    const allowed = new Set(["loc", "title", "ncols", "style", "highlight", "toggle"]);
    if (Object.keys(options).some((key) => !allowed.has(key))) legendFlags |= LEGEND_UNSUPPORTED_KEYS;
    legendNcols = Number(options.ncols ?? 1);
    if (Object.hasOwn(options, "toggle") && options.toggle !== false) legendFlags |= LEGEND_TOGGLE;
    if (Object.hasOwn(options, "highlight") && options.highlight !== false) legendFlags |= LEGEND_HIGHLIGHT;
    let loc = options.loc;
    if (loc != null) {
      legendFlags |= LEGEND_AUTHORED_LOC;
      legendLoc = encodeUtf8(String(loc));
    }
    const style = options.style ?? {};
    const allowedStyle = new Set(["background", "color", "font_size", "fontSize", "title_font_size", "titleFontSize"]);
    if (Object.keys(style).some((key) => !allowedStyle.has(key))) legendFlags |= LEGEND_UNSUPPORTED_STYLE;
    const authoredFont = style.font_size ?? style.fontSize;
    const authoredTitleFont = style.title_font_size ?? style.titleFontSize;
    if (authoredFont != null) { legendFlags |= LEGEND_AUTHORED_FONT; legendFont = Number(authoredFont); }
    if (authoredTitleFont != null) { legendFlags |= LEGEND_AUTHORED_TITLE_FONT; legendTitleFont = Number(authoredTitleFont); }
    legendTitle = encodeUtf8(String(options.title ?? ""));
    if (Object.hasOwn(style, "color")) { legendFlags |= LEGEND_AUTHORED_COLOR; legendTextRgba = rgba8(style.color, 1); }
    if (Object.hasOwn(style, "background")) { legendFlags |= LEGEND_AUTHORED_BACKGROUND; legendFrameRgba = rgba8(style.background, 1); }
  }
  let colorbarObs = 0, stopCount = 0, tickCount = 0, cbTitle = new Uint8Array();
  let cbLo = 0, cbHi = 0, cbText = Uint8Array.of(32, 32, 32, 255);
  let cbStops = [], cbTicks = [];
  const colorbar = figure.colorbarOptions ?? figure.colorbar_options;
  if (colorbarOk && colorbar) {
    flags |= FLAG_HAS_COLORBAR;
    cbLo = Number(colorbar.domain[0]); cbHi = Number(colorbar.domain[1]);
    cbStops = colorbar.stops.map((stop) => [Number(stop[0]), Uint8Array.from(stop[1])]);
    stopCount = cbStops.length;
    const side = colorbar.side ?? "right";
    if (side === "bottom") colorbarObs |= CB_HORIZONTAL;
    else if (side !== "right") colorbarObs |= CB_INVALID_SIDE;
    if (colorbar.minor_ticks) colorbarObs |= CB_MINOR;
    cbTitle = encodeUtf8(String(colorbar.title ?? ""));
    if (colorbar.text_rgba) cbText = Uint8Array.from(colorbar.text_rgba);
    if (colorbar.ticks != null) { cbTicks = Array.from(colorbar.ticks, Number); tickCount = cbTicks.length; }
  }
  const header = new Uint8Array(288);
  const view = new DataView(header.buffer);
  header.set(encodeUtf8("XYCF").slice(0, 4), 0);
  view.setUint32(4, 1, true);
  view.setUint32(8, flags >>> 0, true);
  view.setFloat64(16, Number(width), true);
  view.setFloat64(24, Number(height), true);
  authoredMargins.forEach((value, index) => view.setFloat64(32 + index * 8, value, true));
  padding.forEach((value, index) => view.setFloat64(64 + index * 8, value, true));
  view.setUint32(96, kindCode(xAxis.kind ?? xAxis.type ?? "linear"), true);
  view.setUint32(100, kindCode(yAxis.kind ?? yAxis.type ?? "linear"), true);
  view.setFloat64(104, Number(xDomain[0]), true);
  view.setFloat64(112, Number(xDomain[1]), true);
  view.setFloat64(120, Number(xAxis.constant ?? 1), true);
  view.setFloat64(128, Number(yDomain[0]), true);
  view.setFloat64(136, Number(yDomain[1]), true);
  view.setFloat64(144, Number(yAxis.constant ?? 1), true);
  header[152] = (xAxis.nonpositive ?? "clip") === "mask" ? 1 : 0;
  header[153] = (yAxis.nonpositive ?? "clip") === "mask" ? 1 : 0;
  const tickKind = (axis) => {
    const kind = axis.kind ?? axis.type;
    if (kind === "time") return 1;
    if (kind === "category") return 2;
    return 0;
  };
  header[154] = tickKind(xAxis);
  header[155] = tickKind(yAxis);
  const strategyCode = (options) => ({ auto: 0, hide: 1, rotate: 2, stagger: 3, preserve: 4, none: 5, off: 6 }[sceneTickStrategy(options)] ?? 0);
  const anchorCode = (options) => {
    const raw = options.tick_label_anchor ?? options.tickLabelAnchor;
    if (raw == null) return null;
    return sceneTickAnchor(raw);
  };
  const xAnchor = anchorCode(xAxis);
  const yAnchor = anchorCode(yAxis);
  const xGap = xAxis.tick_label_min_gap ?? xAxis.tickLabelMinGap;
  const yGap = yAxis.tick_label_min_gap ?? yAxis.tickLabelMinGap;
  const xAngle = xAxis.tick_label_angle ?? xAxis.tickLabelAngle;
  const yAngle = yAxis.tick_label_angle ?? yAxis.tickLabelAngle;
  const extras = xGap != null || yGap != null || xAngle != null || yAngle != null;
  let collisionFlags = extras ? 1 : 0;
  if ((xAxis.kind ?? xAxis.type) === "category") collisionFlags |= 1 << 1;
  if ((yAxis.kind ?? yAxis.type) === "category") collisionFlags |= 1 << 2;
  if (xAnchor != null) collisionFlags |= 1 << 3;
  if (yAnchor != null) collisionFlags |= 1 << 4;
  header[12] = strategyCode(xAxis);
  header[13] = strategyCode(yAxis);
  header[14] = (xAnchor ?? 0) | ((yAnchor ?? 0) << 4);
  header[15] = collisionFlags;
  const collisionExtra = extras ? (() => {
    const extra = new Uint8Array(32);
    const extraView = new DataView(extra.buffer);
    extraView.setFloat64(0, xGap == null ? 8 : Number(xGap), true);
    extraView.setFloat64(8, yGap == null ? 4 : Number(yGap), true);
    extraView.setFloat64(16, xAngle == null ? Number.NaN : Number(xAngle), true);
    extraView.setFloat64(24, yAngle == null ? Number.NaN : Number(yAngle), true);
    return extra;
  })() : new Uint8Array();
  view.setUint32(156, title.length, true);
  view.setUint32(160, xLabel.length, true);
  view.setUint32(164, yLabel.length, true);
  view.setUint32(168, xFormat.length, true);
  view.setUint32(172, yFormat.length, true);
  view.setUint32(176, xMajor.length, true);
  view.setUint32(180, xMinor.length, true);
  view.setUint32(184, yMajor.length, true);
  view.setUint32(188, yMinor.length, true);
  view.setUint32(192, xLabels == null ? 0 : xLabels.length, true);
  view.setUint32(196, yLabels == null ? 0 : yLabels.length, true);
  view.setUint32(200, chrome.length, true);
  view.setUint32(204, legendLoc.length, true);
  view.setUint32(208, legendTitle.length, true);
  view.setUint32(212, legendNcols, true);
  view.setFloat64(216, legendFont, true);
  view.setFloat64(224, legendTitleFont, true);
  view.setUint32(232, legendFlags >>> 0, true);
  view.setUint32(236, legendCount, true);
  header.set(legendTextRgba, 240);
  header.set(legendFrameRgba, 244);
  view.setUint32(248, colorbarObs >>> 0, true);
  view.setUint32(252, stopCount, true);
  view.setUint32(256, tickCount, true);
  view.setUint32(260, cbTitle.length, true);
  view.setFloat64(264, cbLo, true);
  view.setFloat64(272, cbHi, true);
  header.set(cbText, 280);
  const legendLensBytes = new Uint8Array(legendLens.length * 4);
  const lensView = new DataView(legendLensBytes.buffer);
  legendLens.forEach((len, index) => lensView.setUint32(index * 4, len, true));
  const stopBytes = concatBytes(cbStops.map(([value, rgba]) => {
    const row = new Uint8Array(12);
    new DataView(row.buffer).setFloat64(0, value, true);
    row.set(rgba, 8);
    return row;
  }));
  return concatBytes([
    header, title, xLabel, yLabel, xFormat, yFormat,
    packF64s(xMajor), packF64s(xMinor), packF64s(yMajor), packF64s(yMinor),
    packTickLabels(xLabels), packTickLabels(yLabels),
    chrome, legendLoc, legendTitle, legendMeta, legendLensBytes, legendBlob,
    stopBytes, packF64s(cbTicks), cbTitle, collisionExtra,
  ]);
}

function packPublicExportSupport(figure, { width = null, height = null } = {}) {
  const OBS_HAS_X = 1 << 0;
  const OBS_HAS_Y = 1 << 1;
  const OBS_X_FINITE = 1 << 2;
  const OBS_Y_FINITE = 1 << 3;
  const OBS_HAS_X0 = 1 << 4;
  const OBS_HAS_Y0 = 1 << 5;
  const OBS_HAS_X1 = 1 << 6;
  const OBS_HAS_Y1 = 1 << 7;
  const OBS_X0_FINITE = 1 << 8;
  const OBS_Y0_FINITE = 1 << 9;
  const OBS_X1_FINITE = 1 << 10;
  const OBS_Y1_FINITE = 1 << 11;
  const OBS_JOINED_FILL = 1 << 12;
  const OBS_HEATMAP_TRUECOLOR = 1 << 13;
  const OBS_HEATMAP_RGBA_GRID = 1 << 16;
  const OBS_HEATMAP_SHAPE_OK = 1 << 17;
  const OBS_HEATMAP_EXTENT_OK = 1 << 18;
  const OBS_HEATMAP_FINITE = 1 << 19;
  const OBS_STROKE_WIDTH_ONLY = 1 << 20;
  const OBS_COMPANION_XY_MATCH = 1 << 21;
  const OBS_COMPANION_AXES_MATCH = 1 << 22;
  const OBS_SYMBOL_NON_STRING = 1 << 23;
  const OBS_DENSITY_BLIT = 1 << 24;
  let flags = 0;
  if (width == null && !Number.isInteger(figure.width)) flags |= 1 << 0;
  if (height == null && !Number.isInteger(figure.height)) flags |= 1 << 1;
  const chrome = figure.chromeStyles ?? figure.chrome_styles;
  if (chrome && Object.keys(chrome).length) flags |= 1 << 2;
  const titleOptions = figure.titleOptions ?? figure.title_options;
  if (titleOptions && (Array.isArray(titleOptions) ? titleOptions.length : titleOptions)) flags |= 1 << 3;
  if ((figure.coords ?? "cartesian") === "polar") flags |= 1 << 4;
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
  parts[0].set([88, 89, 69, 70]);
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

  for (const annotation of annotations) {
    if (annotation == null || typeof annotation !== "object" || Array.isArray(annotation)) {
      parts.push(new Uint8Array(8));
      parts[parts.length - 1][0] = 1;
      continue;
    }
    const kindBytes = encodeUtf8(annotation.kind == null ? "" : String(annotation.kind)).slice(0, 256);
    const fields = Object.keys(annotation);
    if (annotationHasMarkup(annotation) && !fields.includes("markup")) fields.push("markup");
    const row = new Uint8Array(8);
    const view = new DataView(row.buffer);
    view.setUint16(4, kindBytes.length, true);
    view.setUint16(6, fields.length, true);
    parts.push(row, kindBytes);
    for (const key of fields) parts.push(encodeExportKey(key));
  }

  for (const [traceIndex, trace] of traces.entries()) {
    const style = trace.style ?? {};
    const opacity = Number(style.opacity ?? 1);
    if (!Number.isFinite(opacity) || opacity < 0 || opacity > 1) {
      throw new RangeError("trace opacity must be finite and in [0, 1]");
    }
    const prev = traceIndex ? traces[traceIndex - 1] : null;
    const prev2 = traceIndex >= 2 ? traces[traceIndex - 2] : null;
    const prev3 = traceIndex >= 3 ? traces[traceIndex - 3] : null;
    const xv = exportColumn(trace, "x");
    const yv = exportColumn(trace, "y");
    const x0 = exportColumn(trace, "x0");
    const y0 = exportColumn(trace, "y0");
    const x1 = exportColumn(trace, "x1");
    const y1 = exportColumn(trace, "y1");
    let obs = 0;
    if (xv != null) obs |= OBS_HAS_X;
    if (yv != null) obs |= OBS_HAS_Y;
    if (exportColumnFinite(xv)) obs |= OBS_X_FINITE;
    if (exportColumnFinite(yv)) obs |= OBS_Y_FINITE;
    if (x0 != null) obs |= OBS_HAS_X0;
    if (y0 != null) obs |= OBS_HAS_Y0;
    if (x1 != null) obs |= OBS_HAS_X1;
    if (y1 != null) obs |= OBS_HAS_Y1;
    if (exportColumnFinite(x0)) obs |= OBS_X0_FINITE;
    if (exportColumnFinite(y0)) obs |= OBS_Y0_FINITE;
    if (exportColumnFinite(x1)) obs |= OBS_X1_FINITE;
    if (exportColumnFinite(y1)) obs |= OBS_Y1_FINITE;
    if (style.joined_fill || style.joinedFill) obs |= OBS_JOINED_FILL;
    let heatmapRows = 0, heatmapCols = 0, heatmapValues = 0;
    if (trace.kind === "heatmap") {
      if (style.truecolor) obs |= OBS_HEATMAP_TRUECOLOR;
      if (trace.rgba_grid != null) obs |= OBS_HEATMAP_RGBA_GRID;
      const shape = trace.grid_shape ?? trace.gridShape;
      const grid = exportColumn(trace, "grid");
      const hx = xv, hy = yv;
      if (Array.isArray(shape) && shape.length === 2) {
        const rows = Number(shape[0]), cols = Number(shape[1]);
        if (sceneHeatmapShapeAdmit(rows, cols)) {
          heatmapRows = rows;
          heatmapCols = cols;
          obs |= OBS_HEATMAP_SHAPE_OK;
          if (grid != null) heatmapValues = grid.length;
          if (
            hx != null && hy != null && hx.length === 2 && hy.length === 2
            && sceneHeatmapExtentAdmit(Number(hx[0]), Number(hx[1]), Number(hy[0]), Number(hy[1]))
          ) obs |= OBS_HEATMAP_EXTENT_OK;
          if (grid != null && exportColumnFinite(grid)) obs |= OBS_HEATMAP_FINITE;
        }
      }
    }
    if ((style.stroke_width ?? style.strokeWidth) != null && style.stroke == null) obs |= OBS_STROKE_WIDTH_ONLY;
    const prevX1 = prev && exportColumn(prev, "x1");
    const prevY1 = prev && exportColumn(prev, "y1");
    if (prev != null && xv != null && yv != null && prevX1 != null && prevY1 != null && exportArraysEqual(xv, prevX1) && exportArraysEqual(yv, prevY1)) {
      obs |= OBS_COMPANION_XY_MATCH;
    }
    if (prev != null && (trace.x_axis ?? "x") === (prev.x_axis ?? "x") && (trace.y_axis ?? "y") === (prev.y_axis ?? "y")) {
      obs |= OBS_COMPANION_AXES_MATCH;
    }
    let symbol = style.symbol ?? "circle";
    if (typeof symbol !== "string") {
      obs |= OBS_SYMBOL_NON_STRING;
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
      obs |= OBS_DENSITY_BLIT;
    }
    const role = style.role == null ? "" : String(style.role);
    const reduce = style.reduce == null ? "" : String(style.reduce);
    let hexDx = Number.NaN, hexDy = Number.NaN;
    if (sceneKindClass(trace.kind) & SCENE_KIND_CLASS_HEXBIN) {
      hexDx = Number(style.hex_dx ?? style.hexDx ?? style.dx);
      hexDy = Number(style.hex_dy ?? style.hexDy ?? style.dy);
      if (!sceneHexbinPitchAdmit(hexDx, hexDy)) {
        hexDx = Number.NaN;
        hexDy = Number.NaN;
      }
    }
    const styleKeysTrace = Object.entries(style).filter(([, value]) => value != null).map(([key]) => canonicalExportKey(key));
    const kindBytes = encodeUtf8(trace.kind == null ? "" : String(trace.kind)).slice(0, 256);
    const stepBytes = encodeUtf8(style.step == null ? "" : String(style.step)).slice(0, 256);
    const roleBytes = encodeUtf8(role).slice(0, 256);
    const symbolBytes = encodeUtf8(symbol).slice(0, 256);
    const reduceBytes = encodeUtf8(reduce).slice(0, 256);
    const prevBytes = encodeUtf8(prev == null ? "" : String(prev.kind ?? "")).slice(0, 256);
    const prev2Bytes = encodeUtf8(prev2 == null ? "" : String(prev2.kind ?? "")).slice(0, 256);
    const prev3Bytes = encodeUtf8(prev3 == null ? "" : String(prev3.kind ?? "")).slice(0, 256);
    const row = new Uint8Array(80);
    const view = new DataView(row.buffer);
    view.setUint32(0, obs, true);
    view.setUint32(4, exportColumnLen(xv), true);
    view.setUint32(8, exportColumnLen(yv), true);
    view.setUint32(12, exportColumnLen(x0), true);
    view.setUint32(16, exportColumnLen(y0), true);
    view.setUint32(20, exportColumnLen(x1), true);
    view.setUint32(24, exportColumnLen(y1), true);
    view.setUint32(28, heatmapRows, true);
    view.setUint32(32, heatmapCols, true);
    view.setUint32(36, heatmapValues, true);
    view.setUint16(40, styleKeysTrace.length, true);
    view.setUint16(42, kindBytes.length, true);
    view.setUint16(44, stepBytes.length, true);
    view.setUint16(46, roleBytes.length, true);
    view.setUint16(48, symbolBytes.length, true);
    view.setUint16(50, reduceBytes.length, true);
    view.setUint16(52, prevBytes.length, true);
    view.setUint16(54, prev2Bytes.length, true);
    view.setUint16(56, prev3Bytes.length, true);
    view.setFloat64(64, hexDx, true);
    view.setFloat64(72, hexDy, true);
    parts.push(row, kindBytes, stepBytes, roleBytes, symbolBytes, reduceBytes, prevBytes, prev2Bytes, prev3Bytes);
    for (const key of styleKeysTrace) parts.push(encodeExportKey(key));
  }
  return packPublicExportFromFacts(concatBytes(parts));
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
  try {
    figureSceneV3(figure);
  } catch (err) {
    if (err instanceof RangeError) {
      if (err.message === "invalid canonical scene plot layout") return "XYG_SCENE_UNSUPPORTED_VIEWPORT";
      if (
        err.message.includes("axis tick lists are limited")
        || err.message === "legend font sizes must be finite and in [1, 1000]"
        || err.message === "invalid scene chrome packing"
        || err.message === "invalid scene chrome facts version"
      ) {
        throw err;
      }
      return err.message;
    }
    throw err;
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

function rectExtraFlags(style, kind, polar) {
  const gradientFail =
    style.fill != null && typeof style.fill === "object" && admitFillGradient({ style }) == null;
  const radius = style.corner_radius ?? 0;
  const radiusSeq = Array.isArray(radius);
  const values = radiusSeq ? radius.map(Number) : [Number(radius)];
  const gap = Number(style.wedge_gap ?? 0);
  return sceneRectExtraFlags(kind, polar, gradientFail, values, radiusSeq, gap);
}

function figureTraceSupport(figure, trace) {
  const style = trace.style ?? {};
  const kind = String(trace.kind ?? "mark");
  const kindClass = sceneKindClass(kind);
  let flags = 0;
  if (!sceneKindAdmit(kind)) flags |= XYFS_TRACE_UNSUPPORTED_KIND;
  if ((trace.x_axis ?? "x") !== "x" || (trace.y_axis ?? "y") !== "y") flags |= XYFS_TRACE_NON_PRIMARY_AXIS;
  if (
    trace.hidden
    || scatterHasDroppedPerItem(trace)
    || (scatterHasNonConstantColor(trace) && !scatterUsesDensity(trace))
    || scatterPacksPaintPlane(trace)
  ) flags |= XYFS_TRACE_HIDDEN_OR_PER_ITEM;
  if (style.marker_glyph != null) {
    if (kind !== "scatter" || style.marker_path != null || admittedMarkerGlyph(style.marker_glyph) == null) {
      flags |= XYFS_TRACE_DASHED_MARKERS;
    }
  }
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
    const curveCode = sceneCurveClassify(curve);
    if (curveCode === 1) {
      if (!(kindClass & (SCENE_KIND_CLASS_LINE | SCENE_KIND_CLASS_BAND))) flags |= XYFS_TRACE_DASHED_MARKERS;
    } else if (curveCode !== 0) {
      flags |= XYFS_TRACE_DASHED_MARKERS;
    }
  }
  const linecap = style.linecap ?? style.lineCap;
  if (linecap != null && parseSceneLinecap(linecap) === false) {
    flags |= XYFS_TRACE_DASHED_MARKERS;
  }
  if (style.dash != null && parseSceneDash(style.dash) === false) flags |= XYFS_TRACE_DASHED_MARKERS;
  if (kindClass & (SCENE_KIND_CLASS_RECT | SCENE_KIND_CLASS_HEATMAP)) flags |= rectExtraFlags(style, kind, figure.coords === "polar");
  if (kindClass & SCENE_KIND_CLASS_HEXBIN && !sceneHexbinReduceAdmit(style.reduce)) flags |= XYFS_TRACE_CUSTOM_HEX_REDUCE;
  if (
    kindClass & SCENE_KIND_CLASS_HEATMAP
    && sceneHeatmapColormapAdmit(
      style.truecolor ? 1 : 0,
      style.colormap != null ? 1 : 0,
      trace.rgba_grid != null ? 1 : 0,
      trace.rgba != null ? 1 : 0,
    )
  ) flags |= XYFS_TRACE_HEATMAP_COLORMAP;
  if (Object.hasOwn(style, "fill") && typeof style.fill !== "string") {
    if (admitFillGradient(trace) == null) flags |= XYFS_TRACE_NON_CSS_FILL;
  }
  return { flags, kind };
}

function hexbinPacksColormapPlane(trace) {
  if (!(sceneKindClass(trace.kind) & SCENE_KIND_CLASS_HEXBIN)) return false;
  const channel = trace.color_ch ?? trace.colorChannel;
  if (channel == null) return false;
  return sceneHexbinColormapPlaneAdmit(channel.mode, (channel.values ?? trace.metric) != null);
}

function hexbinCount(trace) {
  return trace.x?.length ?? 0;
}

function hexbinCellRgba8(trace) {
  return channelEndRgba8(
    trace.color_ch ?? trace.colorChannel,
    hexbinCount(trace),
    sourceColorCss(trace),
  );
}

function hexbinPacksRgbaPlane(trace) {
  if (!(sceneKindClass(trace.kind) & SCENE_KIND_CLASS_HEXBIN)) return false;
  const channel = trace.color_ch ?? trace.colorChannel;
  if (channel == null) return false;
  if (!sceneHexbinRgbaPlaneAdmit(channel.mode)) return false;
  return hexbinCellRgba8(trace) != null;
}

function hexbinPacksPaintPlane(trace) {
  return hexbinPacksColormapPlane(trace) || hexbinPacksRgbaPlane(trace);
}

function scatterPaintChannelNames(trace) {
  const names = [];
  const style = trace.style ?? {};
  const channels = trace.style_channels ?? trace.styleChannels ?? {};
  if (scatterHasNonConstantColor(trace)) names.push("color");
  const strokeCh = trace.stroke_ch ?? trace.strokeChannel;
  if (strokeCh != null && strokeCh.mode !== "constant" && strokeCh.mode !== "match_fill") {
    names.push("stroke");
  } else if (style.stroke_channel && strokeCh == null) {
    names.push("stroke");
  }
  if (channels.stroke_width || style.stroke_width_channel) names.push("stroke_width");
  if (channels.opacity || style.opacity_channel) names.push("opacity");
  if (channels.artist_alpha || style.artist_alpha_channel) names.push("artist_alpha");
  if (trace.size_ch || style.size_channel) names.push("size");
  if (channels.symbol || Array.isArray(style.symbol)) names.push("symbol");
  return names;
}

function scatterPacksPaintPlane(trace) {
  if ((trace.kind ?? "scatter") !== "scatter" || scatterUsesDensity(trace)) return false;
  const names = scatterPaintChannelNames(trace);
  if (!names.length) return false;
  return names.every((name) => sceneScatterPaintChannelAdmit(name));
}

function scatterCount(trace) {
  return trace.x?.length ?? trace.count ?? 0;
}

function itemApplyOpacity(trace, packed, n) {
  const channels = trace.style_channels ?? trace.styleChannels ?? {};
  const opacityCh = channels.opacity;
  const artistCh = channels.artist_alpha;
  if (opacityCh?.values == null && artistCh?.values == null) return packed;
  return sceneItemApplyOpacity(
    packed,
    n,
    artistCh?.values ?? null,
    opacityCh?.values ?? null,
  );
}

function itemFillRgba8(trace, n) {
  const fallback = sourceColorCss(trace);
  const channel = trace.color_ch ?? trace.colorChannel ?? trace.color;
  let packed = channelEndRgba8(channel, n, fallback);
  if (packed == null && channel != null && typeof channel === "object" && channel.mode === "continuous" && channel.values != null) {
    const values = [...channel.values].map(Number);
    const domain = channel.domain;
    const t = sceneItemFillT(
      values,
      n,
      Array.isArray(domain) && domain.length === 2 ? [Number(domain[0]), Number(domain[1])] : null,
    );
    if (t == null) return null;
    try {
      const stops = colormapNamedStops(channel.colormap ?? "viridis");
      packed = colormapRgba(t, n, 1, stops, 255).rgba;
    } catch {
      return null;
    }
  }
  if (packed == null) return null;
  return itemApplyOpacity(trace, packed, n);
}

function itemStrokeRgba8(trace, fills, n) {
  const strokeCh = trace.stroke_ch ?? trace.strokeChannel;
  if (strokeCh != null && strokeCh.mode === "match_fill") return fills;
  const fallback = String((trace.style ?? {}).stroke ?? "transparent");
  const packed = channelEndRgba8(strokeCh, n, fallback);
  if (packed != null) return packed;
  if (strokeCh == null) return channelEndRgba8(null, n, fallback);
  return null;
}

function itemWidths(trace, n) {
  const widthCh = (trace.style_channels ?? trace.styleChannels ?? {}).stroke_width;
  if (widthCh?.values != null) {
    const values = [...widthCh.values].map(Number);
    if (!sceneItemWidthsAdmit(values, n, 0)) return null;
    return packF64Le(values);
  }
  const width = Number((trace.style ?? {}).stroke_width ?? 0);
  if (!sceneItemWidthsAdmit(null, n, width)) return null;
  return packF64Le(new Float64Array(n).fill(width));
}

function scatterPointPaints(trace) {
  const n = scatterCount(trace);
  const packedFills = itemFillRgba8(trace, n);
  const strokeCh = trace.stroke_ch ?? trace.strokeChannel;
  let packedStrokes = itemStrokeRgba8(trace, packedFills, n);
  if (packedStrokes != null && !(strokeCh != null && strokeCh.mode === "match_fill")) {
    packedStrokes = itemApplyOpacity(trace, packedStrokes, n);
  }
  const packedWidths = itemWidths(trace, n);
  if (packedFills == null || packedStrokes == null || packedWidths == null) return null;
  return { fills: packedFills, strokes: packedStrokes, widths: packedWidths };
}

function meshCount(trace) {
  return trace.x0?.length ?? trace.count ?? 0;
}

function meshJoinedFill(trace) {
  const style = trace.style ?? {};
  return Boolean(style.joined_fill || style.joinedFill);
}

function meshHasPerItem(trace) {
  const style = trace.style ?? {};
  const channels = trace.style_channels ?? trace.styleChannels ?? {};
  return Boolean(
    scatterHasNonConstantColor(trace)
    || scatterHasDroppedPerItem(trace)
    || channels.opacity
    || channels.stroke_width
    || style.opacity_channel
    || style.stroke_width_channel
  );
}

function meshPacksPaintPlane(trace) {
  return sceneMeshPaintPlaneAdmit(
    String(trace.kind ?? ""),
    meshJoinedFill(trace),
    meshHasPerItem(trace),
  );
}

function meshFaceFillRgba8(trace) {
  return itemFillRgba8(trace, meshCount(trace));
}

function meshFaceStrokeRgba8(trace, fills) {
  return itemStrokeRgba8(trace, fills, meshCount(trace));
}

function meshFaceWidths(trace) {
  return itemWidths(trace, meshCount(trace));
}

function meshFacePaints(trace) {
  const fills = meshFaceFillRgba8(trace);
  const strokes = meshFaceStrokeRgba8(trace, fills);
  const widths = meshFaceWidths(trace);
  if (fills == null || strokes == null || widths == null) return null;
  return { fills, strokes, widths };
}

/** Compile migrated cartesian marks to Scene v12. */
export function figureSceneV3(figure, { margins = null } = {}) {
  let colorbarUnsupported = false;
  try { colorbarInput(figure); } catch { colorbarUnsupported = Boolean(figure.colorbarOptions ?? figure.colorbar_options); }
  const xDomain = figure._range("x");
  const yDomain = figure._range("y");
  const annotationParts = [];
  for (const [annotationIndex, annotation] of (figure.annotations ?? []).entries()) {
    annotationParts.push(packXyAf(annotation, annotationIndex));
  }
  try {
    return encodeProduct(
      packXyTc(figure),
      packXyTa(figure, xDomain, yDomain),
      packXyNm(figure.traces ?? []),
      packXyCl(figure),
      concatBytes(annotationParts),
      (figure.traces ?? []).length,
      xDomain,
      yDomain,
      packChromeFacts(figure, {
        width: figure.width, height: figure.height, margins, colorbarOk: !colorbarUnsupported,
      }),
      packPolarSceneInput(figure),
      packFigureSupport(figure, { colorbarUnsupported }),
    );
  } catch (error) {
    if (error.stage === 1) raiseTraceCompile(error.code, error.index ?? 0, figure);
    if (error.stage === 2) raiseTraceAttach(error.code, error.index ?? 0, figure);
    if (error.stage === 3) raiseTraceSidecars(error.code, error.index ?? 0);
    if (error.stage === 4) raiseTraceRows(error.code, error.index ?? 0);
    if (error.stage === 5) {
      if (error.code === -5) throw new RangeError("Scene annotation geometry must be finite");
      if (error.code === -6) throw new RangeError("Scene annotations require nonempty NUL-free text");
      if (error.code === -7) throw new RangeError("Scene v23 label border requires label_background");
      if (error.code === -3) throw new RangeError("Scene annotations are limited to 128 entries");
      throw new RangeError("invalid scene annotation packing");
    }
    if (error.stage === 6) {
      throw new RangeError(error.code === -2 ? "invalid scene style sidecar facts version" : "invalid scene style sidecar packing");
    }
    if (error.stage === 7) {
      throw new RangeError(error.code === -2 ? "invalid scene annotation splice version" : "invalid scene annotation splice packing");
    }
    throw error;
  }
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
