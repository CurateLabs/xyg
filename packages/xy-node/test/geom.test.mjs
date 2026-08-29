import assert from "node:assert/strict";
import test from "node:test";

import {
  F32_SAFE_MAG,
  curveFlatten,
  clipQuantizeU8,
  colormapLut,
  colormapLutRgba8,
  colormapNamedStops,
  f32SafeScale,
  geometryOffset,
  hexbinRing,
  hexbinPacksColormapPlane,
  itemApplyOpacity,
  itemFillRgba8,
  itemWidths,
  markerPathScale,
  arrowGeometry,
  arrowShaftPoints,
  pinsOffsetToZero,
  quantizeUnitU8,
  sceneDashAdmit,
  sceneLinecapAdmit,
  densityOverlayOpacity,
  sceneMarkerPathAdmit,
  sceneAnnotationStyleAdmit,
  sceneArraysEqual,
  sceneConstantColorAdmit,
  sceneHiddenOrPerItemAdmit,
  sceneRibbonColor2Classify,
  sceneScatterPaintChannelAdmit,
  scatterHasNonConstantColor,
  scatterPacksPaintPlane,
  scatterPaintChannelNames,
  scatterPerItemChannels,
  scatterUsesDensity,
  sceneTickLabelStrategy,
  sceneTickAnchor,
  sceneFillGradientAdmit,
  sceneFiniteAll,
  sceneParseLinearGradient,
  sceneRectExtraFlags,
  rectExtraFlags,
  resolveDensityBinColors,
  sceneGradientDir,
  sceneLinearGradientPrefix,
  sceneGradientSpace,
  sceneGradientSolidCss,
  sceneHeatmapColormapAdmit,
  sceneHeatmapExtentAdmit,
  sceneHeatmapShapeAdmit,
  sceneHexbinColormapPlaneAdmit,
  sceneHexbinPitchAdmit,
  sceneHexbinReduceAdmit,
  sceneHexbinRgbaPlaneAdmit,
  meshHasPerItem,
  packXyTaColormap,
  packXyTaFillOpacity,
  packXyTaGrid,
  packXyTaRgba,
  packXyTaRgbaGrid,
  packXyTcFillOpacity,
  packXyTcLineOpacity,
  packXyTcLineWidth,
  packXyTcStrokeOpacity,
  packXyTcStrokeWidth,
  hexbinXyTaColormap,
  constantMarkColor,
  xyHfColormap,
  channelConstantCss,
  channelEndRgba8,
  color2Channel,
  sourceColorCss,
  sceneMeshPaintPlaneAdmit,
  sceneItemApplyOpacity,
  sceneItemWidthsAdmit,
  sceneItemFillT,
  sceneCurveClassify,
  sceneMarkerGlyphAdmit,
  admittedMarkerGlyph,
  sceneKindAdmit,
  sceneKindClass,
  figureTraceSupport,
  fillIsGradientAuthoring,
  monotoneTangents,
  ribbonEdge,
  ribbonPolygon,
  roundedRectPoly,
  stepArrays,
} from "../src/index.js";

test("geometryOffset pins log family and nonfinite to zero", () => {
  assert.equal(pinsOffsetToZero("log"), true);
  assert.equal(pinsOffsetToZero("symlog"), true);
  assert.equal(pinsOffsetToZero("linear"), false);
  assert.equal(pinsOffsetToZero("Log"), false);
  assert.equal(pinsOffsetToZero(""), false);
  assert.equal(pinsOffsetToZero(null), false);
  assert.equal(geometryOffset("log", 10, 20), 0);
  assert.equal(geometryOffset("symlog", 10, 20), 0);
  assert.equal(geometryOffset("linear", 10, 20), 15);
  assert.equal(geometryOffset("linear", Number.NaN, 20), 0);
  assert.equal(f32SafeScale(0, -1, 1), 1);
  const huge = F32_SAFE_MAG * 10;
  assert.ok(Math.abs(f32SafeScale(0, -huge, huge) - 0.1) < 1e-12);
});

test("arrowGeometry trims label_clear and samples shafts", () => {
  const geom = arrowGeometry(0, 0, 300, 0, { label_clear: "2.8,90,2.8,17" });
  assert.ok(Math.abs(geom.p0[0] - 90) < 1e-12);
  assert.equal(geom.p0[1], 0);
  assert.deepEqual(geom.p1, [300, 0]);
  const short = arrowGeometry(0, 0, 50, 0, { label_clear: "2.8,90,2.8,17" });
  assert.deepEqual(short.p0, [0, 0]);
  const elbow = arrowGeometry(0, 0, 10, 10, { angle_a: 0, angle_b: 90, elbow: true });
  assert.equal(arrowShaftPoints(elbow).length, 3);
  const curved = arrowGeometry(0, 0, 10, 10, { curve: 0.3 });
  assert.equal(arrowShaftPoints(curved).length, 25);
});

test("hexbinRing scales the canonical pointy-top fractions", () => {
  const { x, y } = hexbinRing(6, 12);
  assert.equal(x.length, 6);
  assert.equal(y.length, 6);
  assert.equal(x[0], 0);
  assert.equal(y[0], -4);
  assert.equal(x[1], 3);
  assert.equal(y[1], -2);
  assert.throws(() => hexbinRing(Number.NaN, 1), /invalid hexbin-ring request/);
});

test("ribbonEdge midpoint matches Python golden", () => {
  const { x, y } = ribbonEdge(0, 10, 1, 3, 8);
  assert.equal(x.length, 9);
  assert.equal(x[0], 0);
  assert.equal(y[0], 1);
  assert.equal(x[4], 5);
  assert.equal(y[4], 2);
  assert.equal(x[8], 10);
  assert.equal(y[8], 3);
});

test("ribbonPolygon is upper then reversed lower", () => {
  const { x, y } = ribbonPolygon(0, 10, 0, 1, 2, 4, 4);
  assert.equal(x.length, 10);
  assert.equal(y[0], 1);
  assert.equal(y[4], 4);
  assert.equal(y[5], 2);
  assert.equal(y[9], 0);
});

test("monotoneTangents zero interiors on sign change", () => {
  const m = monotoneTangents([0, 1, 2, 3, 4], [0, 1, 0.5, 2, 1.5]);
  assert.deepEqual([...m], [1, 0, 0, 0, -0.5]);
});

test("curveFlatten keeps knots and 15 interiors per span", () => {
  const { x, y } = curveFlatten([0, 1, 2, 3, 4], [0, 1, 0.5, 2, 1.5]);
  assert.equal(x.length, 65);
  assert.equal(x[0], 0);
  assert.equal(y[16], 1);
  assert.equal(x[64], 4);
  assert.equal(y[64], 1.5);
});

test("stepArrays expands pre mid and post vertices", () => {
  const pre = stepArrays([0, 1, 2], [10, 20, 30], "pre");
  assert.deepEqual([...pre.x], [0, 0, 1, 1, 2]);
  assert.deepEqual([...pre.y], [10, 20, 20, 30, 30]);
  const mid = stepArrays([0, 1, 2], [10, 20, 30], "mid");
  assert.deepEqual([...mid.x], [0, 0.5, 0.5, 1, 1.5, 1.5, 2]);
  assert.deepEqual([...mid.y], [10, 10, 20, 20, 20, 30, 30]);
  const post = stepArrays([0, 1, 2], [10, 20, 30], "post");
  assert.deepEqual([...post.x], [0, 1, 1, 2, 2]);
  assert.deepEqual([...post.y], [10, 10, 20, 20, 30]);
  const identity = stepArrays([7], [9], "pre");
  assert.deepEqual([...identity.x], [7]);
  assert.deepEqual([...identity.y], [9]);
  assert.throws(() => stepArrays([0, 1], [10], "post"), /equal length/);
});

test("markerPathScale flips y and matches host vertices", () => {
  const scaled = markerPathScale(10, 20, 8, [0, 0.5, 0, -0.5], [0.5, 0, -0.5, 0]);
  assert.deepEqual([...scaled.x], [10, 14, 10, 6]);
  assert.deepEqual([...scaled.y], [16, 20, 24, 20]);
  const empty = markerPathScale(10, 20, 8, [], []);
  assert.deepEqual([...empty.x], []);
  assert.deepEqual([...empty.y], []);
  assert.throws(() => markerPathScale(10, 20, 8, [0, 1], [0]), /equal length/);
});

test("sceneDashAdmit presets reject bad tokens and empty lists", () => {
  assert.deepEqual(sceneDashAdmit("dashed"), [6, 4]);
  assert.deepEqual(sceneDashAdmit("dotted"), [1.5, 3]);
  assert.equal(sceneDashAdmit("solid"), null);
  assert.equal(sceneDashAdmit(null), null);
  assert.equal(sceneDashAdmit(""), false);
  assert.equal(sceneDashAdmit("6,foo,4"), false);
  assert.deepEqual(sceneDashAdmit([6, 4]), [6, 4]);
  assert.equal(sceneDashAdmit([]), false);
});

test("sceneLinecapAdmit names reject unknown and whitespace", () => {
  assert.equal(sceneLinecapAdmit("butt"), 0);
  assert.equal(sceneLinecapAdmit("square"), 2);
  assert.equal(sceneLinecapAdmit("round"), null);
  assert.equal(sceneLinecapAdmit(null), null);
  assert.equal(sceneLinecapAdmit(""), false);
  assert.equal(sceneLinecapAdmit("  "), false);
  assert.equal(sceneLinecapAdmit("foo"), false);
  assert.equal(sceneLinecapAdmit("Butt"), 0);
});

test("densityOverlayOpacity caps finite and maps non-finite to 0.55", () => {
  assert.equal(densityOverlayOpacity(0.8), 0.55);
  assert.equal(densityOverlayOpacity(0.3), 0.3);
  assert.equal(densityOverlayOpacity(Number.NaN), 0.55);
  assert.equal(densityOverlayOpacity(Number.POSITIVE_INFINITY), 0.55);
});

test("sceneMarkerPathAdmit bounds and host coercion", () => {
  const diamond = { contours: [[-0.4, 0, 0, 0.4, 0.4, 0, 0, -0.4]] };
  const admitted = sceneMarkerPathAdmit(diamond);
  assert.equal(admitted.filled, true);
  assert.equal(admitted.contours.length, 1);
  assert.equal(sceneMarkerPathAdmit(null), null);
  assert.equal(sceneMarkerPathAdmit({ contours: [[0, 0]] }), null);
  assert.equal(sceneMarkerPathAdmit({ contours: [] }), null);
  assert.equal(sceneMarkerPathAdmit({ contours: [[0, 0, 0.6, 0]] }), null);
});

test("sceneAnnotationStyleAdmit matches host allowlist table", () => {
  assert.equal(sceneAnnotationStyleAdmit("arrow", false, false, "width"), true);
  assert.equal(sceneAnnotationStyleAdmit("arrow", false, false, "dash"), false);
  assert.equal(sceneAnnotationStyleAdmit("arrow", false, true, "label_color"), false);
  assert.equal(sceneAnnotationStyleAdmit("callout", false, false, "width"), true);
  assert.equal(sceneAnnotationStyleAdmit("text", false, false, "width"), false);
  assert.equal(sceneAnnotationStyleAdmit("text", true, true, "width"), false);
  assert.equal(sceneAnnotationStyleAdmit("text", true, true, "label_background"), true);
  assert.equal(sceneAnnotationStyleAdmit("rule", false, false, "dash"), true);
  assert.equal(sceneAnnotationStyleAdmit("rule", false, false, "label_color"), false);
  assert.equal(sceneAnnotationStyleAdmit("rule", false, true, "label_color"), true);
  assert.equal(sceneAnnotationStyleAdmit("band", false, false, "label_color"), false);
  assert.equal(sceneAnnotationStyleAdmit("band", false, true, "label_color"), true);
  assert.equal(sceneAnnotationStyleAdmit("marker", false, false, "stroke_width"), true);
  assert.equal(sceneAnnotationStyleAdmit("foo", false, true, "width"), false);
});

test("sceneTickLabelStrategy matches host table", () => {
  assert.equal(sceneTickLabelStrategy("auto"), 0);
  assert.equal(sceneTickLabelStrategy("hide"), 1);
  assert.equal(sceneTickLabelStrategy("rotate"), 2);
  assert.equal(sceneTickLabelStrategy("stagger"), 3);
  assert.equal(sceneTickLabelStrategy("preserve"), 4);
  assert.equal(sceneTickLabelStrategy("none"), 5);
  assert.equal(sceneTickLabelStrategy("off"), 6);
  assert.equal(sceneTickLabelStrategy("hide-overlap"), 0);
  assert.equal(sceneTickLabelStrategy(""), 0);
  assert.equal(sceneTickLabelStrategy("foo"), 0);
  assert.equal(sceneTickLabelStrategy("HIDE"), 0);
});

test("sceneTickAnchor matches host table", () => {
  assert.equal(sceneTickAnchor("start"), 0);
  assert.equal(sceneTickAnchor("center"), 1);
  assert.equal(sceneTickAnchor("middle"), 1);
  assert.equal(sceneTickAnchor("end"), 2);
  assert.equal(sceneTickAnchor(""), null);
  assert.equal(sceneTickAnchor("foo"), null);
  assert.equal(sceneTickAnchor("START"), null);
  assert.equal(sceneTickAnchor("left"), null);
});

test("sceneFillGradientAdmit matches host table", () => {
  const admitted = sceneFillGradientAdmit("mark", "down", [0, 1], ["#336699", "#34d399"], "#3987e5");
  assert.equal(admitted.length, 2);
  assert.equal(sceneFillGradientAdmit("mark", "down", [0, 1], ["var(--accent)", "#ffffff"], "#3987e5"), null);
  const current = sceneFillGradientAdmit("plot", "up", [0, 1], ["currentcolor", ""], "#3987e5");
  assert.equal(current.length, 2);
  assert.equal(sceneFillGradientAdmit("data", "down", [0, 1], ["#336699", "#34d399"], "#3987e5"), null);
});

test("sceneParseLinearGradient matches host table", () => {
  const parsed = sceneParseLinearGradient("linear-gradient(currentColor, transparent)", "mark");
  assert.equal(parsed.dir, "down");
  assert.deepEqual(parsed.stops, [[0, "currentColor"], [1, "transparent"]]);
  const plot = sceneParseLinearGradient("linear-gradient(to right, red 10%, blue)", "plot");
  assert.equal(plot.dir, "right");
  assert.deepEqual(plot.stops, [[0.1, "red"], [1, "blue"]]);
  assert.equal(sceneParseLinearGradient("radial-gradient(red, blue)", "mark"), null);
  assert.equal(sceneParseLinearGradient("linear-gradient(45deg, red, blue)", "mark"), null);
  assert.equal(sceneParseLinearGradient("linear-gradient(to left, red, blue)", "mark"), null);
  assert.equal(sceneParseLinearGradient("linear-gradient(red)", "mark"), null);
});

test("sceneRectExtraFlags matches host table", () => {
  assert.equal(sceneRectExtraFlags("bar", false, false, [0], false, 0), 0);
  assert.equal(sceneRectExtraFlags("bar", false, true, [0], false, 0), 1 << 5);
  assert.equal(sceneRectExtraFlags("bar", false, false, [1, 2], true, 0), 0);
  assert.equal(sceneRectExtraFlags("bar", false, false, [1], true, 0), 1 << 6);
  assert.equal(sceneRectExtraFlags("line", false, false, [3], false, 0), 1 << 6);
  assert.equal(sceneRectExtraFlags("bar", false, false, [0], false, 0.2), 1 << 7);
  assert.equal(sceneRectExtraFlags("bar", true, false, [0], false, 0.2), 0);
  assert.equal(sceneRectExtraFlags("heatmap", true, false, [0], false, 0.2), 1 << 7);
});

test("rectExtraFlags array fill matches Python dict-only", () => {
  assert.equal(rectExtraFlags({ fill: ["linear-gradient(red, blue)"] }, "bar", false), 0);
  assert.equal(rectExtraFlags({ fill: "linear-gradient(red, blue)" }, "bar", false), 0);
  assert.equal(rectExtraFlags({ fill: { gradient: "radial-gradient(red, blue)" } }, "bar", false), 1 << 5);
});

test("sceneGradientDir matches host table", () => {
  assert.equal(sceneGradientDir("down"), 0);
  assert.equal(sceneGradientDir("up"), 1);
  assert.equal(sceneGradientDir("right"), 2);
  assert.equal(sceneGradientDir("left"), 3);
  assert.equal(sceneGradientDir(""), 255);
  assert.equal(sceneGradientDir("foo"), 255);
  assert.equal(sceneGradientDir("DOWN"), 255);
  assert.equal(sceneGradientDir("to bottom"), 255);
});

test("sceneLinearGradientPrefix matches host table", () => {
  assert.equal(sceneLinearGradientPrefix("linear-gradient(red, blue)"), true);
  assert.equal(sceneLinearGradientPrefix("  LINEAR-GRADIENT(red, blue)  "), true);
  assert.equal(sceneLinearGradientPrefix("linear-gradient(45deg, red, blue)"), true);
  assert.equal(sceneLinearGradientPrefix("radial-gradient(red, blue)"), false);
  assert.equal(sceneLinearGradientPrefix("linear-gradient"), false);
  assert.equal(sceneLinearGradientPrefix(""), false);
});

test("fillIsGradientAuthoring host coercion matches Python dict-only", () => {
  assert.equal(fillIsGradientAuthoring({ space: "mark", dir: "down", stops: [] }), true);
  assert.equal(fillIsGradientAuthoring("linear-gradient(red, blue)"), true);
  assert.equal(fillIsGradientAuthoring("  LINEAR-GRADIENT(red, blue)"), true);
  assert.equal(fillIsGradientAuthoring("radial-gradient(red, blue)"), false);
  assert.equal(fillIsGradientAuthoring("#3987e5"), false);
  assert.equal(fillIsGradientAuthoring(null), false);
  assert.equal(fillIsGradientAuthoring(["linear-gradient(red, blue)"]), false);
});

test("packXyTaColormap uses style.colormap only like Python", () => {
  const named = packXyTaColormap({ style: { colormap: "viridis" } });
  assert.equal(named.flags, 1 << 6);
  assert.deepEqual([...named.cmap], [...new TextEncoder().encode("viridis")]);
  assert.equal(packXyTaColormap({ colormap: "viridis" }).flags, 0);
  assert.equal(packXyTaColormap({ style: {}, colormapStops: [[0, 0, 0]] }).flags, 0);
  assert.equal(packXyTaColormap({ colormapStops: [[0, 0, 0]] }).flags, 0);
});

test("packXyTaColormap stop bytes require RGB rows like Python", () => {
  const rgb = packXyTaColormap({ style: { colormap: [[255, 0, 0], [0, 255, 0]] } });
  assert.equal(rgb.flags, 1 << 7);
  assert.deepEqual([...rgb.stops], [255, 0, 0, 0, 255, 0]);
  const flat = packXyTaColormap({ style: { colormap: [255, 0, 0] } });
  assert.equal(flat.flags, 1 << 7);
  assert.equal(flat.stops.length, 0);
  const rgba = packXyTaColormap({ style: { colormap: [[255, 0, 0, 255]] } });
  assert.equal(rgba.flags, 1 << 7);
  assert.equal(rgba.stops.length, 0);
});

test("packXyTaFillOpacity uses fill_opacity only like Python", () => {
  const missing = packXyTaFillOpacity({});
  assert.equal(missing.flags, 0);
  assert.equal(Number.isNaN(missing.value), true);
  const camel = packXyTaFillOpacity({ fillOpacity: 0.25 });
  assert.equal(camel.flags, 0);
  assert.equal(Number.isNaN(camel.value), true);
  const snake = packXyTaFillOpacity({ fill_opacity: 0.5 });
  assert.equal(snake.flags, 1 << 11);
  assert.equal(snake.value, 0.5);
});

test("packXyTcStrokeWidth uses stroke_width only like Python", () => {
  const missing = packXyTcStrokeWidth({});
  assert.equal(missing.flags, 0);
  assert.equal(missing.value, 0);
  const camel = packXyTcStrokeWidth({ strokeWidth: 2.5 });
  assert.equal(camel.flags, 0);
  assert.equal(camel.value, 0);
  const snake = packXyTcStrokeWidth({ stroke_width: 2.5 });
  assert.equal(snake.flags, 1 << 3);
  assert.equal(snake.value, 2.5);
});

test("packXyTcLineWidth uses line_width only like Python", () => {
  const missing = packXyTcLineWidth({});
  assert.equal(missing.flags, 0);
  assert.equal(missing.value, 0);
  const camel = packXyTcLineWidth({ lineWidth: 2.5 });
  assert.equal(camel.flags, 0);
  assert.equal(camel.value, 0);
  const snake = packXyTcLineWidth({ line_width: 2.5 });
  assert.equal(snake.flags, 1 << 5);
  assert.equal(snake.value, 2.5);
});

test("packXyTaGrid flattens plane.values like Python", () => {
  const direct = packXyTaGrid([1, 2]);
  const view = new Float64Array(direct.buffer, direct.byteOffset, direct.byteLength / 8);
  assert.deepEqual([...view], [1, 2]);
  const nested = packXyTaGrid([[1, 2], [3, 4]]);
  const nestedView = new Float64Array(nested.buffer, nested.byteOffset, nested.byteLength / 8);
  assert.deepEqual([...nestedView], [1, 2, 3, 4]);
  const fromValues = packXyTaGrid({ values: [5, 6] });
  const valuesView = new Float64Array(fromValues.buffer, fromValues.byteOffset, fromValues.byteLength / 8);
  assert.deepEqual([...valuesView], [5, 6]);
});

test("packXyTaRgba ignores nested .rgba like Python", () => {
  assert.deepEqual([...packXyTaRgba(new Uint8Array([1, 2, 3, 4]))], [1, 2, 3, 4]);
  assert.deepEqual([...packXyTaRgba([5, 6, 7, 8])], [5, 6, 7, 8]);
  const nested = packXyTaRgba({ rgba: new Uint8Array([9, 8, 7, 6]) });
  assert.equal(nested.length, 0);
});

test("packXyTaRgbaGrid stacks flattened planes like Python", () => {
  const packed = packXyTaRgbaGrid([[1, 2], [3, 4], [5, 6], [7, 8]]);
  const view = new Float64Array(packed.buffer, packed.byteOffset, packed.byteLength / 8);
  assert.deepEqual([...view], [1, 3, 5, 7, 2, 4, 6, 8]);
  const nested = packXyTaRgbaGrid([[[1, 2]], [[3, 4]], [[5, 6]], [[7, 8]]]);
  const nestedView = new Float64Array(nested.buffer, nested.byteOffset, nested.byteLength / 8);
  assert.deepEqual([...nestedView], [1, 3, 5, 7, 2, 4, 6, 8]);
  const fromValues = packXyTaRgbaGrid([
    { values: [1, 2] },
    { values: [3, 4] },
    { values: [5, 6] },
    { values: [7, 8] },
  ]);
  const valuesView = new Float64Array(fromValues.buffer, fromValues.byteOffset, fromValues.byteLength / 8);
  assert.deepEqual([...valuesView], [1, 3, 5, 7, 2, 4, 6, 8]);
  assert.equal(packXyTaRgbaGrid([[1], [2], [3]]).length, 0);
});

test("packXyTcFillOpacity uses fill_opacity only like Python", () => {
  const scatter = sceneKindClass("scatter");
  const line = sceneKindClass("line");
  assert.equal(packXyTcFillOpacity({}, scatter), 1);
  assert.equal(packXyTcFillOpacity({ fillOpacity: 0.25 }, scatter), 1);
  assert.equal(packXyTcFillOpacity({ fill_opacity: 0.5 }, scatter), 0.5);
  assert.equal(packXyTcFillOpacity({ fill_opacity: 0.5 }, line), 1);
  assert.equal(packXyTcFillOpacity({ fill_opacity: 0.5 }, 0), 1);
});

test("packXyTcLineOpacity uses line_opacity only like Python", () => {
  const area = sceneKindClass("area");
  const scatter = sceneKindClass("scatter");
  assert.equal(packXyTcLineOpacity({}, area), 1);
  assert.equal(packXyTcLineOpacity({ lineOpacity: 0.25 }, area), 1);
  assert.equal(packXyTcLineOpacity({ line_opacity: 0.5 }, area), 0.5);
  assert.equal(packXyTcLineOpacity({ line_opacity: 0.5 }, scatter), 1);
  assert.equal(packXyTcLineOpacity({ line_opacity: 0.5 }, 0), 1);
});

test("packXyTcStrokeOpacity uses stroke_opacity only like Python", () => {
  const scatter = sceneKindClass("scatter");
  const line = sceneKindClass("line");
  assert.equal(packXyTcStrokeOpacity({}, scatter), 1);
  assert.equal(packXyTcStrokeOpacity({ strokeOpacity: 0.25 }, scatter), 1);
  assert.equal(packXyTcStrokeOpacity({ stroke_opacity: 0.5 }, scatter), 0.5);
  assert.equal(packXyTcStrokeOpacity({ stroke_opacity: 0.5 }, line), 1);
  assert.equal(packXyTcStrokeOpacity({ stroke_opacity: 0.5 }, 0), 1);
});

test("hexbinXyTaColormap uses channel.colormap only like Python", () => {
  const fromChannel = hexbinXyTaColormap({
    color_ch: { values: [1, 2], colormap: "plasma" },
    style: { colormap: "viridis" },
  });
  assert.equal(fromChannel.flags, 1 << 6);
  assert.deepEqual([...fromChannel.cmap], [...new TextEncoder().encode("plasma")]);
  assert.equal(
    hexbinXyTaColormap({
      color_ch: { values: [1, 2] },
      style: { colormap: "viridis" },
    }).flags,
    0,
  );
});

test("xyHfColormap uses style.colormap only like Python", () => {
  const named = xyHfColormap({ colormap: "viridis" });
  assert.equal(named.flags, 1 << 5);
  assert.deepEqual([...named.bytes], [...new TextEncoder().encode("viridis")]);
  assert.equal(xyHfColormap({ colormap: "viridis", colormapStops: [[0, 0, 0]] }).flags, 1 << 5);
  assert.equal(xyHfColormap({}), null);
  assert.equal(xyHfColormap({ colormapStops: [[0, 0, 0]] }), null);
});

test("xyHfColormap stop bytes require RGB rows like Python", () => {
  const rgb = xyHfColormap({ colormap: [[255, 0, 0], [0, 255, 0]] });
  assert.equal(rgb.flags, 1 << 6);
  assert.deepEqual([...rgb.bytes], [255, 0, 0, 0, 255, 0]);
  const flat = xyHfColormap({ colormap: [255, 0, 0] });
  assert.equal(flat.flags, 1 << 6);
  assert.equal(flat.bytes.length, 0);
  const rgba = xyHfColormap({ colormap: [[255, 0, 0, 255]] });
  assert.equal(rgba.flags, 1 << 6);
  assert.equal(rgba.bytes.length, 0);
});

test("constantMarkColor uses color_ch.constant only like Python", () => {
  assert.equal(
    constantMarkColor({ color_ch: { mode: "constant", constant: "red" } }),
    "red",
  );
  assert.equal(constantMarkColor({ color_ch: "red" }), null);
  assert.equal(
    constantMarkColor({ color_ch: { mode: "constant", color: "red" } }),
    null,
  );
  assert.equal(
    constantMarkColor({ color: { mode: "constant", constant: "blue" } }),
    "#3987e5",
  );
});

test("channelConstantCss uses channel.constant only like Python", () => {
  assert.equal(channelConstantCss({ mode: "constant", constant: "red" }), "red");
  assert.equal(channelConstantCss("red"), null);
  assert.equal(channelConstantCss({ mode: "constant", color: "red" }), null);
  assert.equal(channelConstantCss({ mode: "direct_rgba", constant: "red" }), null);
  assert.equal(channelConstantCss(null), null);
});

test("channelEndRgba8 constant uses .constant only like Python", () => {
  const packed = channelEndRgba8({ mode: "constant", constant: "#ff0000" }, 1, "#000000");
  assert.equal(packed.length, 4);
  assert.equal(channelEndRgba8("red", 1, "#000000"), null);
  assert.equal(channelEndRgba8({ mode: "constant", color: "red" }, 1, "#000000"), null);
});

test("channelEndRgba8 ignores array channels like Python", () => {
  assert.equal(channelEndRgba8(["#ff0000"], 1, "#000000"), null);
  assert.equal(channelEndRgba8(new Uint8Array([255, 0, 0, 255]), 1, "#000000"), null);
});

test("channelEndRgba8 categorical uses DEFAULT_PALETTE like Python", () => {
  const packed = channelEndRgba8({ mode: "categorical", codes: [0], palette: [] }, 1, "#000000");
  const expected = channelEndRgba8({ mode: "constant", constant: "#3987e5" }, 1, "#000000");
  assert.deepEqual([...packed], [...expected]);
  assert.equal(channelEndRgba8({ mode: "categorical", palette: ["#ff0000"] }, 1, "#000000"), null);
  assert.equal(
    channelEndRgba8({ mode: "categorical", codes: [0, 1], palette: ["#ff0000"] }, 1, "#000000"),
    null,
  );
});

test("sourceColorCss uses color_ch only like Python", () => {
  assert.equal(
    sourceColorCss({ color_ch: { mode: "constant", constant: "red" } }),
    "red",
  );
  assert.equal(
    sourceColorCss({ color: { mode: "constant", constant: "blue" } }),
    "#3987e5",
  );
  assert.equal(sourceColorCss({ style: { color: "#123456" } }), "#123456");
});

test("color2Channel uses color2_ch only like Python", () => {
  const ch = { mode: "constant", constant: "red" };
  assert.equal(color2Channel({ color2_ch: ch }), ch);
  assert.equal(color2Channel({ color_target: ch }), null);
  assert.equal(color2Channel({ colorTarget: ch }), null);
});

test("itemFillRgba8 uses color_ch only like Python", () => {
  const fromCh = itemFillRgba8({ color_ch: { mode: "constant", constant: "#ff0000" } }, 1);
  const fromColor = itemFillRgba8({ color: { mode: "constant", constant: "#ff0000" } }, 1);
  const fallback = itemFillRgba8({}, 1);
  assert.equal(fromCh.length, 4);
  assert.deepEqual([...fromColor], [...fallback]);
});

test("scatterPaintChannelNames uses color_ch only like Python", () => {
  assert.deepEqual(
    scatterPaintChannelNames({ color_ch: { mode: "continuous", values: [0, 1] } }),
    ["color"],
  );
  assert.deepEqual(
    scatterPaintChannelNames({ color: { mode: "continuous", values: [0, 1] } }),
    [],
  );
  assert.deepEqual(
    scatterPaintChannelNames({ style: { color_channel: { mode: "continuous" } } }),
    [],
  );
});

test("scatterHasNonConstantColor uses color_ch only like Python", () => {
  assert.equal(
    scatterHasNonConstantColor({ color_ch: { mode: "continuous", values: [0, 1] } }),
    true,
  );
  assert.equal(
    scatterHasNonConstantColor({ color: { mode: "continuous", values: [0, 1] } }),
    false,
  );
  assert.equal(
    scatterHasNonConstantColor({ style: { color_channel: { mode: "continuous" } } }),
    false,
  );
  assert.equal(
    scatterHasNonConstantColor({ color_ch: { mode: "constant", color: "red" } }),
    true,
  );
  assert.equal(
    scatterHasNonConstantColor({ color_ch: { mode: "constant", constant: "red" } }),
    false,
  );
});

test("scatterPerItemChannels ignores style.color_channel like Python", () => {
  assert.equal(scatterPerItemChannels({ color_ch: { mode: "constant" } }), false);
  assert.equal(
    scatterPerItemChannels({ color_ch: { mode: "continuous", values: [0, 1] } }),
    true,
  );
  assert.equal(scatterPerItemChannels({ stroke_ch: { mode: "match_fill" } }), false);
  assert.equal(scatterPerItemChannels({ style_channels: { opacity: { mode: "continuous" } } }), true);
  assert.equal(scatterPerItemChannels({ style: { color_channel: { mode: "continuous" } } }), false);
  assert.equal(scatterPerItemChannels({ style: { size_channel: { mode: "continuous" } } }), false);
  assert.equal(scatterPerItemChannels({ style: { stroke_channel: { mode: "continuous" } } }), false);
});

test("resolveDensityBinColors uses color_ch only like Python", () => {
  const ch = { mode: "direct_rgba", rgba: new Uint8Array([255, 0, 0, 255, 0, 255, 0, 255]) };
  const fromCh = resolveDensityBinColors({ color_ch: ch });
  const fromColor = resolveDensityBinColors({ color: ch });
  const fromStyle = resolveDensityBinColors({ style: { color_channel: ch } });
  assert.ok(fromCh != null && fromCh.rgba != null);
  assert.equal(fromColor, null);
  assert.equal(fromStyle, null);
});

test("sceneGradientSpace matches host table", () => {
  assert.equal(sceneGradientSpace("mark"), 0);
  assert.equal(sceneGradientSpace("plot"), 1);
  assert.equal(sceneGradientSpace(""), 255);
  assert.equal(sceneGradientSpace("foo"), 255);
  assert.equal(sceneGradientSpace("MARK"), 255);
});

test("sceneHexbinReduceAdmit matches host table", () => {
  assert.equal(sceneHexbinReduceAdmit("count"), true);
  assert.equal(sceneHexbinReduceAdmit("mean"), true);
  assert.equal(sceneHexbinReduceAdmit("sum"), true);
  assert.equal(sceneHexbinReduceAdmit("custom"), true);
  assert.equal(sceneHexbinReduceAdmit(""), false);
  assert.equal(sceneHexbinReduceAdmit("foo"), false);
  assert.equal(sceneHexbinReduceAdmit("COUNT"), false);
});

test("sceneCurveClassify matches host table", () => {
  assert.equal(sceneCurveClassify("linear"), 0);
  assert.equal(sceneCurveClassify("smooth"), 1);
  assert.equal(sceneCurveClassify("LINEAR"), 0);
  assert.equal(sceneCurveClassify("SMOOTH"), 1);
  assert.equal(sceneCurveClassify("  Smooth  "), 1);
  assert.equal(sceneCurveClassify(""), 255);
  assert.equal(sceneCurveClassify("foo"), 255);
  assert.equal(sceneCurveClassify("step"), 255);
});

test("sceneMarkerGlyphAdmit matches host table", () => {
  assert.equal(sceneMarkerGlyphAdmit("A"), true);
  assert.equal(sceneMarkerGlyphAdmit("α"), true);
  assert.equal(sceneMarkerGlyphAdmit(""), false);
  assert.equal(sceneMarkerGlyphAdmit("a\0b"), false);
  assert.equal(sceneMarkerGlyphAdmit("a\nb"), false);
  assert.equal(sceneMarkerGlyphAdmit("a\rb"), false);
  assert.equal(sceneMarkerGlyphAdmit("x".repeat(64)), true);
  assert.equal(sceneMarkerGlyphAdmit("x".repeat(65)), false);
});

test("admittedMarkerGlyph host coercion matches Python str-only", () => {
  assert.deepEqual([...admittedMarkerGlyph("A")], [65]);
  assert.equal(admittedMarkerGlyph(123), null);
  assert.equal(admittedMarkerGlyph(["A"]), null);
  assert.equal(admittedMarkerGlyph(null), null);
});

test("sceneKindAdmit matches host table", () => {
  for (const name of [
    "scatter",
    "line",
    "bar",
    "column",
    "histogram",
    "violin",
    "box",
    "segments",
    "errorbar",
    "stem",
    "contour",
    "box_whisker",
    "box_median",
    "area",
    "error_band",
    "ribbon",
    "triangle_mesh",
    "hexbin",
    "heatmap",
  ]) {
    assert.equal(sceneKindAdmit(name), true, name);
  }
  assert.equal(sceneKindAdmit(""), false);
  assert.equal(sceneKindAdmit("mark"), false);
  assert.equal(sceneKindAdmit("SCATTER"), false);
  assert.equal(sceneKindAdmit("pie"), false);
  assert.equal(sceneKindAdmit(" scatter"), false);
});

test("figureTraceSupport empty kind matches Python or mark", () => {
  assert.equal(figureTraceSupport({}, { kind: "" }).kind, "mark");
  assert.equal(figureTraceSupport({}, {}).kind, "mark");
  assert.equal(figureTraceSupport({}, { kind: "scatter" }).kind, "scatter");
});

test("figureTraceSupport ignores style.smooth like Python", () => {
  const dashed = 1 << 4;
  assert.equal(figureTraceSupport({}, { kind: "line", style: { smooth: true } }).flags & dashed, 0);
  assert.equal(figureTraceSupport({}, { kind: "scatter", style: { curve: "smooth" } }).flags & dashed, dashed);
});

test("sceneKindClass matches host table", () => {
  assert.equal(sceneKindClass("bar"), 1 << 0);
  assert.equal(sceneKindClass("segments"), (1 << 1) | (1 << 7));
  assert.equal(sceneKindClass("area"), 1 << 2);
  assert.equal(sceneKindClass("ribbon"), 1 << 3);
  assert.equal(sceneKindClass("triangle_mesh"), 1 << 4);
  assert.equal(sceneKindClass("hexbin"), 1 << 5);
  assert.equal(sceneKindClass("heatmap"), 1 << 6);
  assert.equal(sceneKindClass("scatter"), 1 << 8);
  assert.equal(sceneKindClass("line"), (1 << 9) | (1 << 7));
  assert.equal(sceneKindClass(""), 0);
  assert.equal(sceneKindClass("mark"), 0);
  assert.equal(sceneKindClass("SCATTER"), 0);
  assert.equal(sceneKindClass("BAR"), 0);
});

test("sceneHexbinColormapPlaneAdmit matches host table", () => {
  assert.equal(sceneHexbinColormapPlaneAdmit("continuous", 1), true);
  assert.equal(sceneHexbinColormapPlaneAdmit("continuous", 0), false);
  assert.equal(sceneHexbinColormapPlaneAdmit("", 1), false);
  assert.equal(sceneHexbinColormapPlaneAdmit("CONTINUOUS", 1), false);
  assert.equal(sceneHexbinColormapPlaneAdmit("categorical", 1), false);
  assert.equal(sceneHexbinColormapPlaneAdmit("direct_rgba", 1), false);
});

test("hexbinPacksColormapPlane matches Python channel.values only", () => {
  assert.equal(
    hexbinPacksColormapPlane({
      kind: "hexbin",
      color_ch: { mode: "continuous" },
      metric: [1, 2, 3],
    }),
    false,
  );
  assert.equal(
    hexbinPacksColormapPlane({
      kind: "hexbin",
      color_ch: { mode: "continuous", values: [1, 2, 3] },
    }),
    true,
  );
  assert.equal(
    hexbinPacksColormapPlane({
      kind: "hexbin",
      colorChannel: { mode: "continuous", values: [1, 2, 3] },
    }),
    false,
  );
});

test("sceneHexbinRgbaPlaneAdmit matches host table", () => {
  assert.equal(sceneHexbinRgbaPlaneAdmit("categorical"), true);
  assert.equal(sceneHexbinRgbaPlaneAdmit("direct_rgba"), true);
  assert.equal(sceneHexbinRgbaPlaneAdmit(""), false);
  assert.equal(sceneHexbinRgbaPlaneAdmit("CATEGORICAL"), false);
  assert.equal(sceneHexbinRgbaPlaneAdmit("continuous"), false);
  assert.equal(sceneHexbinRgbaPlaneAdmit("direct-rgba"), false);
});

test("sceneMeshPaintPlaneAdmit matches host table", () => {
  assert.equal(sceneMeshPaintPlaneAdmit("triangle_mesh", 0, 1), true);
  assert.equal(sceneMeshPaintPlaneAdmit("triangle_mesh", 1, 1), false);
  assert.equal(sceneMeshPaintPlaneAdmit("triangle_mesh", 0, 0), false);
  assert.equal(sceneMeshPaintPlaneAdmit("", 0, 1), false);
  assert.equal(sceneMeshPaintPlaneAdmit("TRIANGLE_MESH", 0, 1), false);
  assert.equal(sceneMeshPaintPlaneAdmit("scatter", 0, 1), false);
  assert.equal(sceneMeshPaintPlaneAdmit(" triangle_mesh", 0, 1), false);
});

test("meshHasPerItem matches Python has_per_item_channels", () => {
  assert.equal(meshHasPerItem({ kind: "triangle_mesh" }), false);
  assert.equal(
    meshHasPerItem({
      kind: "triangle_mesh",
      stroke_ch: { mode: "constant", constant: "#111827" },
    }),
    false,
  );
  assert.equal(
    meshHasPerItem({
      kind: "triangle_mesh",
      color_ch: { mode: "continuous", values: [0, 1] },
    }),
    true,
  );
  assert.equal(
    meshHasPerItem({
      kind: "triangle_mesh",
      style_channels: { opacity: { values: [0.5, 1] } },
    }),
    true,
  );
});

test("sceneItemApplyOpacity matches host table", () => {
  const packed = Uint8Array.from([10, 20, 30, 40, 1, 2, 3, 80]);
  const identity = sceneItemApplyOpacity(packed, 2, null, null);
  assert.deepEqual([...identity], [...packed]);
  const artist = sceneItemApplyOpacity(packed, 2, [-1, 0.5], null);
  assert.deepEqual([...artist.slice(0, 4)], [10, 20, 30, 40]);
  assert.deepEqual([...artist.slice(4)], [1, 2, 3, 128]);
  const bad = sceneItemApplyOpacity(packed, 2, [0.5], null);
  assert.equal(bad, null);
});

test("sceneItemWidthsAdmit matches host table", () => {
  assert.equal(sceneItemWidthsAdmit([0.0, 1.5], 2, 0), true);
  assert.equal(sceneItemWidthsAdmit([], 0, 0), true);
  assert.equal(sceneItemWidthsAdmit([0.0], 2, 0), false);
  assert.equal(sceneItemWidthsAdmit([-0.1], 1, 0), false);
  assert.equal(sceneItemWidthsAdmit([Number.NaN], 1, 0), false);
  assert.equal(sceneItemWidthsAdmit(null, 3, 0), true);
  assert.equal(sceneItemWidthsAdmit(null, 3, 2.5), true);
  assert.equal(sceneItemWidthsAdmit(null, 3, -1), false);
  assert.equal(sceneItemWidthsAdmit(null, 3, Number.POSITIVE_INFINITY), false);
});

test("itemWidths missing values fail-closes like Python", () => {
  assert.equal(itemWidths({ style_channels: { stroke_width: {} } }, 2), null);
  assert.equal(itemWidths({ style_channels: { stroke_width: { values: null } } }, 1), null);
  const packed = itemWidths({ style_channels: { stroke_width: { values: [1.5, 2.5] } } }, 2);
  assert.equal(packed.length, 16);
  const view = new DataView(packed.buffer, packed.byteOffset, packed.byteLength);
  assert.equal(view.getFloat64(0, true), 1.5);
  assert.equal(view.getFloat64(8, true), 2.5);
  const scalar = itemWidths({ style: { stroke_width: 3 } }, 2);
  assert.equal(scalar.length, 16);
  const scalarView = new DataView(scalar.buffer, scalar.byteOffset, scalar.byteLength);
  assert.equal(scalarView.getFloat64(0, true), 3);
  assert.equal(scalarView.getFloat64(8, true), 3);
});

test("itemApplyOpacity missing values fail-closes like Python", () => {
  const packed = new Uint8Array([10, 20, 30, 255, 40, 50, 60, 255]);
  assert.equal(itemApplyOpacity({}, packed, 2), packed);
  assert.equal(itemApplyOpacity({ style_channels: { opacity: {} } }, packed, 2), null);
  assert.equal(itemApplyOpacity({ style_channels: { artist_alpha: { values: null } } }, packed, 1), null);
  const out = itemApplyOpacity({ style_channels: { opacity: { values: [0.5, 0.5] } } }, packed, 2);
  assert.equal(out[0], 10);
  assert.equal(out[3], 128);
  assert.equal(out[7], 128);
});

test("sceneItemFillT matches host table", () => {
  assert.deepEqual([...sceneItemFillT([0, 10], 2, [0, 10])], [0, 1]);
  assert.deepEqual([...sceneItemFillT([5, 5], 2, null)], [0, 0]);
  assert.equal(sceneItemFillT([Number.NaN], 1, null), null);
  assert.equal(sceneItemFillT([0], 2, null), null);
  assert.equal(sceneItemFillT([-1], 1, [0, 1])[0], 0);
  assert.equal(sceneItemFillT([2], 1, [0, 1])[0], 1);
});

test("sceneFiniteAll matches host table", () => {
  assert.equal(sceneFiniteAll([]), true);
  assert.equal(sceneFiniteAll([0, 1.5]), true);
  assert.equal(sceneFiniteAll([Number.NaN]), false);
  assert.equal(sceneFiniteAll([Number.POSITIVE_INFINITY]), false);
  assert.equal(sceneFiniteAll([Number.NEGATIVE_INFINITY]), false);
  assert.equal(sceneFiniteAll([0, Number.NaN]), false);
});

test("sceneGradientSolidCss matches host table", () => {
  assert.equal(sceneGradientSolidCss([]), "rgb(0,0,0)");
  assert.equal(sceneGradientSolidCss([1, 2, 3, 0, 10, 20, 30, 255]), "rgb(10,20,30)");
  assert.equal(sceneGradientSolidCss([255, 0, 0, 1]), "rgb(255,0,0)");
  assert.equal(sceneGradientSolidCss([1, 2, 3, 0]), "rgb(0,0,0)");
  assert.equal(sceneGradientSolidCss([1, 2, 3]), null);
});

test("sceneArraysEqual matches host table", () => {
  assert.equal(sceneArraysEqual([], []), true);
  assert.equal(sceneArraysEqual([1, 2], [1, 2]), true);
  assert.equal(sceneArraysEqual([1], [1, 2]), false);
  assert.equal(sceneArraysEqual([1], [2]), false);
  assert.equal(sceneArraysEqual([Number.NaN], [Number.NaN]), false);
  assert.equal(sceneArraysEqual([0], [-0]), true);
});

test("clipQuantizeU8 matches host table", () => {
  assert.deepEqual([...clipQuantizeU8([])], []);
  assert.deepEqual([...clipQuantizeU8([0, 0.5, 1, 1.5])], [0, 128, 255, 255]);
  assert.deepEqual([...clipQuantizeU8([Number.NaN])], [0]);
  assert.deepEqual([...clipQuantizeU8([1.5 / 255])], [2]);
});

test("sceneConstantColorAdmit matches host table", () => {
  assert.equal(sceneConstantColorAdmit(false, false, false, false), 1);
  assert.equal(sceneConstantColorAdmit(true, true, false, false), 2);
  assert.equal(sceneConstantColorAdmit(true, false, true, false), 1);
  assert.equal(sceneConstantColorAdmit(true, false, false, true), 1);
  assert.equal(sceneConstantColorAdmit(true, false, false, false), 0);
  assert.equal(sceneConstantColorAdmit(true, true, true, true), 2);
});

test("sceneHiddenOrPerItemAdmit matches host table", () => {
  assert.equal(sceneHiddenOrPerItemAdmit(false, false, false), false);
  assert.equal(sceneHiddenOrPerItemAdmit(true, false, false), true);
  assert.equal(sceneHiddenOrPerItemAdmit(false, true, false), true);
  assert.equal(sceneHiddenOrPerItemAdmit(false, true, true), false);
  assert.equal(sceneHiddenOrPerItemAdmit(true, true, true), true);
  assert.equal(sceneHiddenOrPerItemAdmit(false, false, true), false);
});

test("quantizeUnitU8 matches normalize then clip-quantize", () => {
  assert.deepEqual([...quantizeUnitU8([0, 5, 10], 0, 10)], [0, 128, 255]);
  assert.deepEqual([...quantizeUnitU8([Number.POSITIVE_INFINITY], 0, 1)], [0]);
  assert.deepEqual([...quantizeUnitU8([Number.NaN], 0, 1)], [0]);
  assert.deepEqual([...quantizeUnitU8([1], 5, 5)], [0]);
});

test("colormapLutRgba8 matches ABI 206 RGB plus opaque alpha", () => {
  const lut = colormapLutRgba8("viridis");
  assert.equal(lut.length, 256 * 4);
  const t = Float64Array.from({ length: 256 }, (_, i) => i / 255);
  const rgb = colormapLut(t, colormapNamedStops("viridis"));
  for (let i = 0; i < 256; i++) {
    assert.equal(lut[i * 4], rgb[i * 3]);
    assert.equal(lut[i * 4 + 1], rgb[i * 3 + 1]);
    assert.equal(lut[i * 4 + 2], rgb[i * 3 + 2]);
    assert.equal(lut[i * 4 + 3], 255);
  }
  assert.equal(colormapLutRgba8(null).length, 256 * 4);
});

test("sceneHexbinPitchAdmit matches host table", () => {
  assert.equal(sceneHexbinPitchAdmit(1, 2), true);
  assert.equal(sceneHexbinPitchAdmit(0, 1), false);
  assert.equal(sceneHexbinPitchAdmit(1, 0), false);
  assert.equal(sceneHexbinPitchAdmit(-1, 1), false);
  assert.equal(sceneHexbinPitchAdmit(Number.NaN, 1), false);
  assert.equal(sceneHexbinPitchAdmit(1, Number.POSITIVE_INFINITY), false);
});

test("sceneHeatmapExtentAdmit matches host table", () => {
  assert.equal(sceneHeatmapExtentAdmit(0, 1, 0, 1), true);
  assert.equal(sceneHeatmapExtentAdmit(0, 0, 0, 1), false);
  assert.equal(sceneHeatmapExtentAdmit(0, 1, 0, 0), false);
  assert.equal(sceneHeatmapExtentAdmit(1, 0, 0, 1), false);
  assert.equal(sceneHeatmapExtentAdmit(Number.NaN, 1, 0, 1), false);
  assert.equal(sceneHeatmapExtentAdmit(0, Number.POSITIVE_INFINITY, 0, 1), false);
});

test("sceneHeatmapColormapAdmit matches host table", () => {
  assert.equal(sceneHeatmapColormapAdmit(0, 0, 0, 0), false);
  assert.equal(sceneHeatmapColormapAdmit(1, 0, 0, 0), true);
  assert.equal(sceneHeatmapColormapAdmit(0, 1, 0, 0), true);
  assert.equal(sceneHeatmapColormapAdmit(0, 0, 1, 0), true);
  assert.equal(sceneHeatmapColormapAdmit(0, 0, 0, 1), true);
});

test("sceneScatterPaintChannelAdmit matches host table", () => {
  for (const name of ["color", "stroke", "stroke_width", "opacity", "artist_alpha"]) {
    assert.equal(sceneScatterPaintChannelAdmit(name), true, name);
  }
  assert.equal(sceneScatterPaintChannelAdmit(""), false);
  assert.equal(sceneScatterPaintChannelAdmit("STROKE"), false);
  assert.equal(sceneScatterPaintChannelAdmit(" color"), false);
  assert.equal(sceneScatterPaintChannelAdmit("size"), false);
  assert.equal(sceneScatterPaintChannelAdmit("symbol"), false);
});

test("scatterPaintChannelNames matches Python per_item_channel_names", () => {
  assert.deepEqual(scatterPaintChannelNames({ kind: "scatter" }), []);
  assert.deepEqual(
    scatterPaintChannelNames({
      kind: "scatter",
      size_ch: { mode: "constant", constant: 8 },
      color_ch: { mode: "continuous", values: [0, 1] },
    }),
    ["color"],
  );
  assert.deepEqual(
    scatterPaintChannelNames({
      kind: "scatter",
      size_ch: { mode: "constant" },
    }),
    [],
  );
  assert.deepEqual(
    scatterPaintChannelNames({
      kind: "scatter",
      style_channels: { opacity: { values: [0.5, 1] } },
    }),
    ["opacity"],
  );
});

test("scatterPacksPaintPlane missing kind matches Python empty not scatter", () => {
  const perItem = {
    color_ch: { mode: "continuous", values: [0, 1] },
    x: [0, 1],
  };
  assert.equal(scatterPacksPaintPlane({ ...perItem, kind: "scatter" }), true);
  assert.equal(scatterPacksPaintPlane({ ...perItem }), false);
  assert.equal(scatterPacksPaintPlane({ ...perItem, kind: "" }), false);
  assert.equal(scatterUsesDensity({ x: { length: 200_001 } }), false);
  assert.equal(scatterUsesDensity({ kind: "line", x: { length: 200_001 } }), false);
});

test("sceneHeatmapShapeAdmit matches host table", () => {
  assert.equal(sceneHeatmapShapeAdmit(1, 2), true);
  assert.equal(sceneHeatmapShapeAdmit(0, 2), false);
  assert.equal(sceneHeatmapShapeAdmit(1, 0), false);
  assert.equal(sceneHeatmapShapeAdmit(1.5, 2), false);
  assert.equal(sceneHeatmapShapeAdmit(Number.NaN, 2), false);
  assert.equal(sceneHeatmapShapeAdmit(Number.POSITIVE_INFINITY, 2), false);
});

test("sceneRibbonColor2Classify matches host table", () => {
  assert.equal(sceneRibbonColor2Classify(false, true, null, null, "#3987e5", false, false), "absent");
  assert.equal(sceneRibbonColor2Classify(true, false, null, null, "#3987e5", false, false), "fail");
  assert.equal(sceneRibbonColor2Classify(true, true, "#336699", "#336699", "#336699", false, false), "solid");
  assert.equal(sceneRibbonColor2Classify(true, true, "#336699", "#34d399", "#336699", false, false), "gradient");
  assert.equal(sceneRibbonColor2Classify(true, true, "#336699", "#34d399", "#336699", true, false), "fail");
  assert.equal(sceneRibbonColor2Classify(true, true, null, "#34d399", "#336699", false, true), "ends");
  assert.equal(sceneRibbonColor2Classify(true, true, null, null, "#336699", false, false), "fail");
});

test("roundedRectPoly zero radii is four corners", () => {
  const { x, y } = roundedRectPoly(0, 0, 4, 3, 0, 0, true);
  assert.deepEqual([...x], [0, 4, 4, 0]);
  assert.deepEqual([...y], [0, 0, 3, 3]);
});
