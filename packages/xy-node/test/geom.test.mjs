import assert from "node:assert/strict";
import test from "node:test";

import {
  F32_SAFE_MAG,
  curveFlatten,
  clipQuantizeU8,
  colormapLut,
  colormapLutRgba8,
  colormapNamedStops,
  encodeF32Values,
  encodedColumnMeta,
  f32SafeScale,
  geometryOffset,
  hexbinRing,
  hexbinCellRgba8,
  hexbinPacksColormapPlane,
  hexbinPacksRgbaPlane,
  itemApplyOpacity,
  itemFillRgba8,
  itemStrokeRgba8,
  itemWidths,
  legendStyleFontSizes,
  legendAxisScale,
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
  scatterPointStrokeRgba8,
  scatterUsesDensity,
  sceneTickLabelStrategy,
  sceneTickAnchor,
  sceneFillGradientAdmit,
  sceneFiniteAll,
  sceneParseLinearGradient,
  sceneRectExtraFlags,
  rectExtraFlags,
  resolveDensityBinColors,
  ribbonEndRgbaPair,
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
  meshJoinedFill,
  packXyAfLinecap,
  packXyTaColormap,
  packXyTaDensityColorCh,
  packXyTaFillOpacity,
  packXyTaGrid,
  packXyTaRgba,
  packXyTaRgbaGrid,
  packXyTcColorChannel,
  packXyTcFillOpacity,
  packXyTcJoinedFill,
  packXyTcLineColor,
  packXyTcLinecap,
  packXyTcLineOpacity,
  packXyTcLineWidth,
  packXyTcSize,
  packXyTcSizeChannel,
  packXyTcStrokeOpacity,
  packXyTcStrokePerimeter,
  packXyTcStrokeWidth,
  hexbinXyTaColorChannel,
  hexbinXyTaColormap,
  hexbinStylePitch,
  heatmapGridShape,
  polarGridShape,
  polarCollisionKeys,
  polarAxisThetaUnit,
  polarAxisThetaZero,
  polarAxisROrigin,
  polarAxisHole,
  polarAxisSector,
  packPolarSceneInput,
  axisTickValues,
  axisScaleName,
  axisMinorTickValues,
  axisTickLabels,
  axisTickLabelAnchor,
  axisTickLabelAngle,
  axisTickLabelMinGap,
  axisTickLabelStrategy,
  figureXLabel,
  figureChromeStyles,
  chromeAxisMinorStyle,
  chromeAxisStyleHas,
  chromeAxisStyleKeys,
  chromeAxisStyleValue,
  chromeAxisTickKind,
  chromeAxisTickSides,
  chromeAxisTickLabelSides,
  chromeStyleHasFontFamily,
  figureClassName,
  figureClassNames,
  figureExtraLegends,
  figureTitleOptions,
  figureLegendOptions,
  figureColorbarOptions,
  figureShowLegend,
  figureAxisOptions,
  figureAutorangeAxisOptions,
  figureAutorangeAxisScale,
  figureAxisKind,
  figureAutorangeThetaUnit,
  figureAutorangeCategories,
  figureAutorangeDomain,
  figureAxisIsLog,
  figure,
  scatterPayloadForceBin2d,
  scatterPayloadForceDensity,
  scatterPayloadForceDirect,
  scatterPayloadForcePyramid,
  scatterPayloadNoRescan,
  annotationClassName,
  figureYLabel,
  plotTopAxisRoom,
  polarAxisThetaDirection,
  constantMarkColor,
  xyHfColormap,
  channelConstantCss,
  channelEndRgba8,
  classifyRibbonColor2,
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
  sceneXytcFigurePlan,
  sceneXytcTraceDispatchPlan,
  sceneXytaFigurePlan,
  sceneXytaTraceDispatchPlan,
  sceneFigureSupportFigurePlan,
  sceneFigureSupportTraceDispatchPlan,
  scenePublicExportFigurePlan,
  scenePublicExportTraceDispatchPlan,
  sceneXyafAnnotationDispatchPlan,
  sceneXycfFigurePlan,
  sceneXyclFigurePlan,
  sceneXynmFigurePlan,
  figureTraceSupport,
  fillIsGradientAuthoring,
  xyEfJoinedFill,
  xyEfResolvedKind,
  xyEfStrokeWidthOnly,
  monotoneTangents,
  ribbonEdge,
  ribbonPolygon,
  roundedRectPoly,
  stepArrays,
} from "../src/index.js";
import { packArrowStyle } from "../src/encode.js";

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

test("encodeF32Values packs EncodedColumn meta from the kernel", () => {
  const omitted = encodedColumnMeta(0, 0, 0, null);
  const empty = encodeF32Values([], 0, 0, 0);
  const packed = encodedColumnMeta(0, -1, 1, "float");
  const column = encodeF32Values([-1, 0, 1], 0, -1, 1, { kind: "float" });
  const emptyKindPacked = encodedColumnMeta(1, 0, 2, "");
  const emptyKind = encodeF32Values([1], 1, 0, 2, { kind: "" });
  const huge = F32_SAFE_MAG * 10;
  const hugePacked = encodedColumnMeta(0, -huge, huge, "float");
  const hugeColumn = encodeF32Values([0], 0, -huge, huge, { kind: "float" });

  assert.equal(omitted.hasKind, false);
  assert.deepEqual(empty.meta, { offset: omitted.offset, scale: omitted.scale });
  assert.equal(packed.hasKind, true);
  assert.deepEqual(column.meta, { offset: packed.offset, scale: packed.scale, kind: "float" });
  assert.equal(emptyKindPacked.hasKind, true);
  assert.deepEqual(emptyKind.meta, {
    offset: emptyKindPacked.offset,
    scale: emptyKindPacked.scale,
    kind: "",
  });
  assert.equal(hugeColumn.meta.offset, hugePacked.offset);
  assert.equal(hugeColumn.meta.scale, hugePacked.scale);
  assert.ok(Math.abs(hugePacked.scale - 0.1) < 1e-12);
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

test("packArrowStyle ignores malformed start_offset CSV", () => {
  for (const bad of ["", "5", "5,x", "1,", "1,2,3"]) {
    const packed = packArrowStyle({ start_offset: bad });
    assert.equal(packed.length, 12);
    assert.ok(Number.isNaN(packed[0]));
    assert.ok(Number.isNaN(packed[1]));
    const geom = arrowGeometry(0, 0, 300, 0, { start_offset: bad });
    assert.deepEqual(geom.p0, [0, 0]);
  }
  const ok = packArrowStyle({ start_offset: "50,-7" });
  assert.equal(ok[0], 50);
  assert.equal(ok[1], -7);
});

test("packArrowStyle ignores malformed label_clear CSV", () => {
  for (const bad of ["", "1,2,3", "1,2,3,x", "1,2,3,-4"]) {
    const packed = packArrowStyle({ label_clear: bad });
    assert.ok(Number.isNaN(packed[7]));
    assert.ok(Number.isNaN(packed[8]));
    assert.ok(Number.isNaN(packed[9]));
    assert.ok(Number.isNaN(packed[10]));
  }
  const ok = packArrowStyle({ label_clear: "2.8,90,2.8,17" });
  assert.equal(ok[7], 2.8);
  assert.equal(ok[8], 90);
  assert.equal(ok[9], 2.8);
  assert.equal(ok[10], 17);
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


test("packXyTaDensityColorCh uses color_ch only like Python", () => {
  const missing = packXyTaDensityColorCh({});
  assert.equal(missing.flags, 0);
  assert.equal(missing.bytes.length, 0);
  const camel = packXyTaDensityColorCh({
    colorChannel: { mode: "constant", constant: "#ff0000" },
  });
  assert.equal(camel.flags, 0);
  const snake = packXyTaDensityColorCh({
    color_ch: { mode: "constant", constant: "#ff0000" },
  });
  assert.equal(snake.flags, 1 << 8);
  assert.deepEqual([...snake.bytes], [...new TextEncoder().encode("#ff0000")]);
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

test("packXyTcSize uses size only like Python", () => {
  const missing = packXyTcSize({});
  assert.equal(missing.flags, 0);
  assert.equal(Number.isNaN(missing.value), true);
  const camel = packXyTcSize({ diameter: 12 });
  assert.equal(camel.flags, 0);
  assert.equal(Number.isNaN(camel.value), true);
  const snake = packXyTcSize({ size: 12 });
  assert.equal(snake.flags, 1 << 6);
  assert.equal(snake.value, 12);
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

test("packXyTcJoinedFill uses joined_fill only like Python", () => {
  assert.equal(packXyTcJoinedFill({ kind: "scatter", style: { joined_fill: true } }), 0);
  assert.equal(packXyTcJoinedFill({ kind: "triangle_mesh", style: { joinedFill: true } }), 0);
  assert.equal(packXyTcJoinedFill({ kind: "triangle_mesh", style: { joined_fill: false } }), 0);
  assert.equal(packXyTcJoinedFill({ kind: "triangle_mesh", style: {} }), 0);
  assert.equal(packXyTcJoinedFill({ kind: "triangle_mesh", style: { joined_fill: true } }), 1 << 25);
});

test("packXyTcLineColor uses line_color only like Python", () => {
  const missing = packXyTcLineColor({});
  assert.equal(missing.flags, 0);
  assert.equal(missing.bytes.length, 0);
  const camel = packXyTcLineColor({ lineColor: "#ff0000" });
  assert.equal(camel.flags, 0);
  assert.equal(camel.bytes.length, 0);
  const snake = packXyTcLineColor({ line_color: "#ff0000" });
  assert.equal(snake.flags, 1 << 2);
  assert.deepEqual([...snake.bytes], [...new TextEncoder().encode("#ff0000")]);
});

test("packXyTcLinecap uses linecap only like Python", () => {
  assert.equal(packXyTcLinecap({}).length, 0);
  assert.equal(packXyTcLinecap({ lineCap: "butt" }).length, 0);
  assert.deepEqual(
    [...packXyTcLinecap({ linecap: "butt" })],
    [...new TextEncoder().encode("butt")],
  );
});

test("packXyAfLinecap uses linecap only like Python", () => {
  assert.equal(packXyAfLinecap({}), null);
  assert.equal(packXyAfLinecap({ lineCap: "square" }), null);
  assert.equal(packXyAfLinecap({ lineCap: "nope" }), null);
  assert.equal(packXyAfLinecap({ linecap: "square" }), 2);
  assert.equal(packXyAfLinecap({ linecap: "nope" }), false);
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

test("packXyTcSizeChannel uses size_ch only like Python", () => {
  const missing = packXyTcSizeChannel({});
  assert.equal(missing.flags, 0);
  assert.equal(Number.isNaN(missing.value), true);
  const camel = packXyTcSizeChannel({ sizeChannel: { constant: 4 } });
  assert.equal(camel.flags, 0);
  assert.equal(Number.isNaN(camel.value), true);
  const snake = packXyTcSizeChannel({ size_ch: { constant: 4 } });
  assert.equal(snake.flags, 1 << 7);
  assert.equal(snake.value, 4);
  const present = packXyTcSizeChannel({ size_ch: { mode: "identity" } });
  assert.equal(present.flags, 1 << 7);
  assert.equal(Number.isNaN(present.value), true);
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

test("packXyTcColorChannel uses color_ch only like Python", () => {
  const utf8 = new TextEncoder();
  const missing = packXyTcColorChannel({});
  assert.equal(missing.flags, 0);
  assert.deepEqual([...missing.mode], []);
  assert.deepEqual([...missing.constant], []);
  const camel = packXyTcColorChannel({ colorChannel: { mode: "constant", constant: "red" } });
  assert.equal(camel.flags, 0);
  const asString = packXyTcColorChannel({ color_ch: "red" });
  assert.equal(asString.flags, 0);
  const snake = packXyTcColorChannel({ color_ch: { mode: "constant", constant: "red" } });
  assert.equal(snake.flags, (1 << 11) | (1 << 12));
  assert.deepEqual([...snake.mode], [...utf8.encode("constant")]);
  assert.deepEqual([...snake.constant], [...utf8.encode("red")]);
});

test("packXyTcStrokePerimeter uses stroke_perimeter only like Python", () => {
  const area = sceneKindClass("area");
  const scatter = sceneKindClass("scatter");
  assert.equal(packXyTcStrokePerimeter({}, area), 0);
  assert.equal(packXyTcStrokePerimeter({ strokePerimeter: true }, area), 0);
  assert.equal(packXyTcStrokePerimeter({ stroke_perimeter: true }, scatter), 0);
  assert.equal(packXyTcStrokePerimeter({ stroke_perimeter: false }, area), 0);
  assert.equal(packXyTcStrokePerimeter({ stroke_perimeter: true }, area), 1 << 9);
  assert.equal(packXyTcStrokePerimeter({ stroke_perimeter: "yes" }, area), 1 << 10);
});

test("sceneXytcFigurePlan passes showLegend like Python", () => {
  assert.equal(sceneXytcFigurePlan({ showLegend: true }).showLegend, true);
  assert.equal(sceneXytcFigurePlan({ showLegend: false }).showLegend, false);
});

test("sceneXytcTraceDispatchPlan scatter density and glyph routing", () => {
  const plan = sceneXytcTraceDispatchPlan({
    kind: "scatter",
    markerPathPresent: false,
    useDensity: true,
    joinedFill: false,
  });
  assert.equal(plan.kindClass, sceneKindClass("scatter"));
  assert.equal(plan.packOpacity, true);
  assert.equal(plan.packHexPitch, false);
  assert.equal(plan.markerGlyphBranch, true);
  assert.equal(plan.metaUseDensity, true);
});

test("sceneXytcTraceDispatchPlan ribbon color2 and area perimeter", () => {
  const ribbon = sceneXytcTraceDispatchPlan({ kind: "ribbon" });
  assert.equal(ribbon.packColor2, true);
  const area = sceneXytcTraceDispatchPlan({ kind: "area" });
  assert.equal(area.packStrokePerimeter, true);
  assert.equal(area.packColor2, false);
});

test("sceneXytaFigurePlan passes polar like Python", () => {
  assert.equal(sceneXytaFigurePlan({ polar: true }).polar, true);
  assert.equal(sceneXytaFigurePlan({ polar: false }).polar, false);
});

test("sceneXytaTraceDispatchPlan heatmap hexbin ribbon and density routing", () => {
  const heatmap = sceneXytaTraceDispatchPlan({
    kind: "heatmap",
    hexbinColormapPlane: true,
    hexbinRgbaPlaneReady: true,
    ribbonColor2Class: 3,
    meshPaintPlane: true,
    scatterPaintPlane: true,
  });
  assert.equal(heatmap.packHeatmap, true);
  assert.equal(heatmap.packHexbinColormap, false);

  const hexCmap = sceneXytaTraceDispatchPlan({
    kind: "hexbin",
    hexbinColormapPlane: true,
    hexbinRgbaPlaneReady: true,
  });
  assert.equal(hexCmap.packHexbinColormap, true);
  assert.equal(hexCmap.packHexbinRgba, false);

  const ribbon = sceneXytaTraceDispatchPlan({
    kind: "ribbon",
    ribbonColor2Class: 3,
  });
  assert.equal(ribbon.packRibbonEnds, true);

  const density = sceneXytaTraceDispatchPlan({
    kind: "scatter",
    useDensity: true,
  });
  assert.equal(density.packDensity, true);
});

test("sceneFigureSupportTraceDispatchPlan bar and scatter routing", () => {
  const bar = sceneFigureSupportTraceDispatchPlan({ kind: "bar" });
  assert.equal(bar.probeRectExtra, true);
  assert.equal(bar.probeCurveSmooth, false);

  const scatter = sceneFigureSupportTraceDispatchPlan({
    kind: "scatter",
    markerGlyphPresent: true,
    fillPresent: true,
  });
  assert.equal(scatter.probeMarkerGlyph, true);
  assert.equal(scatter.probeNonCssFill, true);
  assert.equal(scatter.probeCurveSmooth, false);

  assert.equal(sceneFigureSupportFigurePlan({ polar: true }).polar, true);
  assert.equal(sceneXyclFigurePlan({ polar: true }).polar, true);
  assert.equal(sceneXynmFigurePlan({ showLegend: false }).showLegend, false);
});

test("scene chrome export orchestration routes legend density and wrapped XYAF", () => {
  const chrome = sceneXycfFigurePlan({ showLegend: true, colorbarOk: true, polar: false });
  assert.equal(chrome.attachLegend, true);
  assert.equal(chrome.attachColorbar, true);

  const rule = sceneXyafAnnotationDispatchPlan({ kind: "rule" });
  assert.equal(rule.packRuleDash, true);
  assert.equal(rule.wrapped, false);

  const text = sceneXyafAnnotationDispatchPlan({ kind: "text", layoutText: true });
  assert.equal(text.wrapped, true);

  const exportFigure = scenePublicExportFigurePlan({ polar: true, hasChromeStyles: true });
  assert.equal(exportFigure.polar, true);
  assert.equal(
    scenePublicExportTraceDispatchPlan({
      kind: "scatter",
      polar: false,
      useDensity: true,
    }).packDensityBlit,
    true,
  );
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
  assert.equal(
    hexbinXyTaColormap({
      colorChannel: { values: [1, 2], colormap: "plasma" },
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
  assert.equal(
    constantMarkColor({ colorChannel: { mode: "constant", constant: "red" } }),
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
  assert.equal(
    sourceColorCss({ colorChannel: { mode: "constant", constant: "red" } }),
    "#3987e5",
  );
});

test("sourceColorCss empty style.color stays unlike Python or-default", () => {
  // Python `_trace_source_color_css` uses `.get("color") or "#3987e5"`.
  // Node `??` keeps the empty string.
  assert.equal(sourceColorCss({ style: { color: "" } }), "");
});

test("color2Channel uses color2_ch only like Python", () => {
  const ch = { mode: "constant", constant: "red" };
  assert.equal(color2Channel({ color2_ch: ch }), ch);
  assert.equal(color2Channel({ color_target: ch }), null);
  assert.equal(color2Channel({ colorTarget: ch }), null);
});

test("itemFillRgba8 null style.color uses sourceColorCss unlike Python get", () => {
  // Python `_item_fill_rgba8` uses style.get("color", default); a None
  // value stringifies and fail-closes. Node sourceColorCss `??` uses the
  // default CSS.
  const missing = itemFillRgba8({}, 1);
  const nulled = itemFillRgba8({ style: { color: null } }, 1);
  assert.deepEqual([...nulled], [...missing]);
});

test("itemFillRgba8 uses color_ch only like Python", () => {
  const fromCh = itemFillRgba8({ color_ch: { mode: "constant", constant: "#ff0000" } }, 1);
  const fromColor = itemFillRgba8({ color: { mode: "constant", constant: "#ff0000" } }, 1);
  const fallback = itemFillRgba8({}, 1);
  assert.equal(fromCh.length, 4);
  assert.deepEqual([...fromColor], [...fallback]);
  const fromBoth = itemFillRgba8({
    color_ch: { mode: "constant", constant: "#ff0000" },
    colorChannel: { mode: "constant", constant: "#0000ff" },
  }, 1);
  assert.deepEqual([...fromBoth], [...fromCh]);
  const fromCamel = itemFillRgba8({
    colorChannel: { mode: "constant", constant: "#ff0000" },
  }, 1);
  assert.deepEqual([...fromCamel], [...fallback]);
});

test("itemStrokeRgba8 empty style.stroke stays unlike Python or-default", () => {
  // Python `_item_stroke_rgba8` uses `.get("stroke") or "transparent"`.
  // Node `??` keeps the empty string, which is not the transparent fallback.
  const fills = new Uint8Array([1, 2, 3, 4]);
  const missing = itemStrokeRgba8({}, fills, 1);
  const empty = itemStrokeRgba8({ style: { stroke: "" } }, fills, 1);
  assert.notDeepEqual([...empty], [...missing]);
});

test("itemStrokeRgba8 uses stroke_ch only like Python", () => {
  const fills = new Uint8Array([1, 2, 3, 4]);
  assert.equal(itemStrokeRgba8({ stroke_ch: { mode: "match_fill" } }, fills, 1), fills);
  const camelMatch = itemStrokeRgba8({ strokeChannel: { mode: "match_fill" } }, fills, 1);
  const fallback = itemStrokeRgba8({}, fills, 1);
  assert.notEqual(camelMatch, fills);
  assert.deepEqual([...camelMatch], [...fallback]);
  const fromCh = itemStrokeRgba8(
    { stroke_ch: { mode: "constant", constant: "#ff0000" } },
    fills,
    1,
  );
  const fromCamel = itemStrokeRgba8(
    { strokeChannel: { mode: "constant", constant: "#ff0000" } },
    fills,
    1,
  );
  assert.deepEqual([...fromCamel], [...fallback]);
  const fromBoth = itemStrokeRgba8(
    {
      stroke_ch: { mode: "constant", constant: "#ff0000" },
      strokeChannel: { mode: "constant", constant: "#0000ff" },
    },
    fills,
    1,
  );
  assert.deepEqual([...fromBoth], [...fromCh]);
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
  assert.deepEqual(
    scatterPaintChannelNames({ colorChannel: { mode: "continuous", values: [0, 1] } }),
    [],
  );
  assert.deepEqual(
    scatterPaintChannelNames({ strokeChannel: { mode: "continuous", values: [0, 1] } }),
    [],
  );
  assert.deepEqual(
    scatterPaintChannelNames({ sizeChannel: { mode: "continuous", values: [0, 1] } }),
    [],
  );
  assert.deepEqual(
    scatterPaintChannelNames({ styleChannels: { opacity: { values: [0.5] } } }),
    [],
  );
  assert.deepEqual(
    scatterPaintChannelNames({ style_channels: { opacity: { values: [0.5] } } }),
    ["opacity"],
  );
});

test("scatterPointStrokeRgba8 uses stroke_ch only like Python", () => {
  const fills = new Uint8Array([10, 20, 30, 40]);
  const opacity = { x: [0], style_channels: { opacity: { values: [0.5] } } };
  const snake = scatterPointStrokeRgba8(
    { ...opacity, stroke_ch: { mode: "match_fill" } },
    fills,
  );
  const camel = scatterPointStrokeRgba8(
    { ...opacity, strokeChannel: { mode: "match_fill" } },
    fills,
  );
  assert.deepEqual([...snake], [...fills]);
  assert.notDeepEqual([...camel], [...fills]);
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
  assert.equal(
    scatterHasNonConstantColor({ colorChannel: { mode: "continuous", values: [0, 1] } }),
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
  assert.equal(resolveDensityBinColors({ colorChannel: ch }), null);
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
  assert.equal(figureTraceSupport({}, { kind: "line", style: { lineCap: "nope" } }).flags & dashed, 0);
  assert.equal(figureTraceSupport({}, { kind: "line", style: { linecap: "nope" } }).flags & dashed, dashed);
});

test("xyEfJoinedFill uses joined_fill only like Python", () => {
  assert.equal(xyEfJoinedFill({}), false);
  assert.equal(xyEfJoinedFill({ joinedFill: true }), false);
  assert.equal(xyEfJoinedFill({ joined_fill: true }), true);
  assert.equal(xyEfJoinedFill({ joined_fill: 1 }), true);
});

test("xyEfStrokeWidthOnly uses stroke_width only like Python", () => {
  assert.equal(xyEfStrokeWidthOnly({}), false);
  assert.equal(xyEfStrokeWidthOnly({ strokeWidth: 2 }), false);
  assert.equal(xyEfStrokeWidthOnly({ stroke_width: 2 }), true);
  assert.equal(xyEfStrokeWidthOnly({ stroke_width: 2, stroke: "#000" }), false);
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


test("hexbinCellRgba8 null style.color uses sourceColorCss unlike Python get", () => {
  // Python `_hexbin_cell_rgba8` uses style.get("color", default); a None
  // value stringifies and fail-closes. Node sourceColorCss `??` uses the
  // default CSS.
  const missing = hexbinCellRgba8({ x: [0] });
  const nulled = hexbinCellRgba8({ x: [0], style: { color: null } });
  assert.deepEqual([...nulled], [...missing]);
});

test("hexbinCellRgba8 uses color_ch only like Python", () => {
  const rgba = new Uint8Array([255, 0, 0, 255]);
  const fromCh = hexbinCellRgba8({
    x: [0],
    color_ch: { mode: "direct_rgba", rgba },
  });
  assert.deepEqual([...fromCh], [255, 0, 0, 255]);
  const fromCamel = hexbinCellRgba8({
    x: [0],
    colorChannel: { mode: "direct_rgba", rgba },
  });
  const fallback = hexbinCellRgba8({ x: [0] });
  assert.deepEqual([...fromCamel], [...fallback]);
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
  assert.equal(
    hexbinXyTaColorChannel({ colorChannel: { values: [1, 2, 3] } }),
    undefined,
  );
  assert.deepEqual(
    hexbinXyTaColorChannel({ color_ch: { values: [1, 2, 3] } }).values,
    [1, 2, 3],
  );
});

test("legendStyleFontSizes uses font_size only like Python", () => {
  assert.deepEqual(legendStyleFontSizes({}), {
    font_size: undefined,
    title_font_size: undefined,
  });
  assert.deepEqual(legendStyleFontSizes({ fontSize: 14, titleFontSize: 18 }), {
    font_size: undefined,
    title_font_size: undefined,
  });
  assert.deepEqual(legendStyleFontSizes({ font_size: 14, title_font_size: 18 }), {
    font_size: 14,
    title_font_size: 18,
  });
});

test("heatmapGridShape uses grid_shape only like Python", () => {
  assert.equal(heatmapGridShape({}), undefined);
  assert.equal(heatmapGridShape({ gridShape: [2, 3] }), undefined);
  assert.deepEqual(heatmapGridShape({ grid_shape: [2, 3] }), [2, 3]);
});

test("hexbinStylePitch uses hex_dx then dx like Python", () => {
  assert.deepEqual(hexbinStylePitch({}), { hex_dx: undefined, hex_dy: undefined });
  assert.deepEqual(hexbinStylePitch({ hexDx: 1, hexDy: 2 }), { hex_dx: undefined, hex_dy: undefined });
  assert.deepEqual(hexbinStylePitch({ hex_dx: 1, hex_dy: 2 }), { hex_dx: 1, hex_dy: 2 });
  assert.deepEqual(hexbinStylePitch({ dx: 3, dy: 4 }), { hex_dx: 3, hex_dy: 4 });
});

test("polarGridShape uses grid_shape only like Python", () => {
  assert.equal(polarGridShape({}), "circular");
  assert.equal(polarGridShape({ gridShape: "linear" }), "circular");
  assert.equal(polarGridShape({ grid_shape: "linear" }), "linear");
});

test("polarAxisThetaUnit uses theta_unit only like Python", () => {
  assert.equal(polarAxisThetaUnit({}), "radians");
  assert.equal(polarAxisThetaUnit({ thetaUnit: "degrees" }), "radians");
  assert.equal(polarAxisThetaUnit({ theta_unit: "degrees" }), "degrees");
});

test("polarAxisThetaZero uses theta_zero only like Python", () => {
  assert.equal(polarAxisThetaZero({}), "E");
  assert.equal(polarAxisThetaZero({ thetaZero: "N" }), "E");
  assert.equal(polarAxisThetaZero({ theta_zero: "N" }), "N");
});

test("polarAxisThetaDirection uses theta_direction only like Python", () => {
  assert.equal(polarAxisThetaDirection({}), undefined);
  assert.equal(polarAxisThetaDirection({ thetaDirection: "clockwise" }), undefined);
  assert.equal(polarAxisThetaDirection({ theta_direction: "clockwise" }), "clockwise");
});

test("polarAxisROrigin uses r_origin only like Python", () => {
  assert.equal(polarAxisROrigin({}), undefined);
  assert.equal(polarAxisROrigin({ rOrigin: 1 }), undefined);
  assert.equal(polarAxisROrigin({ r_origin: 1 }), 1);
});

test("polarAxisHole uses hole only like Python", () => {
  assert.equal(polarAxisHole({}), undefined);
  assert.equal(polarAxisHole({ Hole: 0.25 }), undefined);
  assert.equal(polarAxisHole({ hole: 0.25 }), 0.25);
});

test("polarAxisSector uses sector only like Python", () => {
  assert.equal(polarAxisSector({}), undefined);
  assert.equal(polarAxisSector({ Sector: [0, 1] }), undefined);
  assert.deepEqual(polarAxisSector({ sector: [0, 1] }), [0, 1]);
});

test("axisTickValues uses tick_values only like Python", () => {
  assert.equal(axisTickValues({}), undefined);
  assert.equal(axisTickValues({ tickValues: [0, 1] }), undefined);
  assert.deepEqual(axisTickValues({ tick_values: [0, 1] }), [0, 1]);
});

test("axisScaleName uses type only like Python", () => {
  assert.equal(axisScaleName({}), "linear");
  assert.equal(axisScaleName({ kind: "log" }), "linear");
  assert.equal(axisScaleName({ type: "log" }), "log");
  assert.equal(axisScaleName({ type: "symlog" }), "symlog");
  assert.equal(axisScaleName({ type: "time" }), "linear");
});

test("legendAxisScale uses type only like Python _axis_scale", () => {
  assert.equal(legendAxisScale({}), "linear");
  assert.equal(legendAxisScale({ kind: "log" }), "linear");
  assert.equal(legendAxisScale({ scale: "log" }), "linear");
  assert.equal(legendAxisScale({ type: "log" }), "log");
  assert.equal(legendAxisScale({ type: "symlog" }), "symlog");
});

test("axisMinorTickValues uses minor_tick_values only like Python", () => {
  assert.equal(axisMinorTickValues({}), undefined);
  assert.equal(axisMinorTickValues({ minorTickValues: [0.25] }), undefined);
  assert.deepEqual(axisMinorTickValues({ minor_tick_values: [0.25] }), [0.25]);
});

test("axisTickLabels uses tick_labels only like Python", () => {
  assert.equal(axisTickLabels({}), undefined);
  assert.equal(axisTickLabels({ tickLabels: ["a"] }), undefined);
  assert.deepEqual(axisTickLabels({ tick_labels: ["a"] }), ["a"]);
});

test("axisTickLabelAnchor uses tick_label_anchor only like Python", () => {
  assert.equal(axisTickLabelAnchor({}), undefined);
  assert.equal(axisTickLabelAnchor({ tickLabelAnchor: "end" }), undefined);
  assert.equal(axisTickLabelAnchor({ tick_label_anchor: "end" }), "end");
});

test("axisTickLabelAngle uses tick_label_angle only like Python", () => {
  assert.equal(axisTickLabelAngle({}), undefined);
  assert.equal(axisTickLabelAngle({ tickLabelAngle: -30 }), undefined);
  assert.equal(axisTickLabelAngle({ tick_label_angle: -30 }), -30);
});

test("axisTickLabelMinGap uses tick_label_min_gap only like Python", () => {
  assert.equal(axisTickLabelMinGap({}), undefined);
  assert.equal(axisTickLabelMinGap({ tickLabelMinGap: 4 }), undefined);
  assert.equal(axisTickLabelMinGap({ tick_label_min_gap: 4 }), 4);
});

test("axisTickLabelStrategy uses tick_label_strategy then collision like Python", () => {
  assert.equal(axisTickLabelStrategy({}), undefined);
  assert.equal(axisTickLabelStrategy({ tickLabelStrategy: "hide" }), undefined);
  assert.equal(axisTickLabelStrategy({ tick_label_strategy: "hide" }), "hide");
  assert.equal(axisTickLabelStrategy({ collision: "rotate" }), "rotate");
  assert.equal(axisTickLabelStrategy({ tick_label_strategy: "hide", collision: "rotate" }), "hide");
});

test("polarCollisionKeys uses snake-case keys only like Python", () => {
  const keys = polarCollisionKeys();
  assert.equal(keys.has("tick_label_strategy"), true);
  assert.equal(keys.has("collision"), true);
  assert.equal(keys.has("tick_label_min_gap"), true);
  assert.equal(keys.has("tick_label_angle"), true);
  assert.equal(keys.has("tick_label_anchor"), true);
  assert.equal(keys.has("tickLabelStrategy"), false);
  assert.equal(keys.has("tickLabelMinGap"), false);
  assert.equal(keys.has("tickLabelAngle"), false);
  assert.equal(keys.has("tickLabelAnchor"), false);
});

test("figureChromeStyles uses chrome_styles only like Python", () => {
  assert.equal(figureChromeStyles({}), undefined);
  assert.equal(figureChromeStyles({ chromeStyles: { x: { color: "red" } } }), undefined);
  assert.deepEqual(figureChromeStyles({ chrome_styles: { x: { color: "red" } } }), { x: { color: "red" } });
});

test("chromeAxisMinorStyle uses minor_style only like Python", () => {
  assert.equal(chromeAxisMinorStyle({}), undefined);
  assert.equal(chromeAxisMinorStyle({ minorStyle: { tick_width: 1 } }), undefined);
  assert.deepEqual(chromeAxisMinorStyle({ minor_style: { tick_width: 1 } }), { tick_width: 1 });
});

test("chromeAxisTickSides uses tick_sides only like Python", () => {
  assert.equal(chromeAxisTickSides({}), undefined);
  assert.deepEqual(chromeAxisTickSides({ tickSides: ["top"] }), undefined);
  assert.deepEqual(chromeAxisTickSides({ tick_sides: ["top"] }), ["top"]);
});

test("chromeAxisTickLabelSides uses tick_label_sides only like Python", () => {
  assert.equal(chromeAxisTickLabelSides({}), undefined);
  assert.deepEqual(chromeAxisTickLabelSides({ tickLabelSides: ["top"] }), undefined);
  assert.deepEqual(chromeAxisTickLabelSides({ tick_label_sides: ["top"] }), ["top"]);
});

test("chromeAxisStyleKeys admits snake-case keys only like Python", () => {
  const keys = chromeAxisStyleKeys();
  assert.equal(keys.has("grid_color"), true);
  assert.equal(keys.has("grid_width"), true);
  assert.equal(keys.has("grid_opacity"), true);
  assert.equal(keys.has("axis_color"), true);
  assert.equal(keys.has("axis_width"), true);
  assert.equal(keys.has("tick_color"), true);
  assert.equal(keys.has("tick_width"), true);
  assert.equal(keys.has("tick_length"), true);
  assert.equal(keys.has("tick_direction"), true);
  assert.equal(keys.has("tick_label_color"), true);
  assert.equal(keys.has("label_color"), true);
  assert.equal(keys.has("gridColor"), false);
  assert.equal(keys.has("gridWidth"), false);
  assert.equal(keys.has("gridOpacity"), false);
  assert.equal(keys.has("axisColor"), false);
  assert.equal(keys.has("axisWidth"), false);
  assert.equal(keys.has("tickColor"), false);
  assert.equal(keys.has("tickWidth"), false);
  assert.equal(keys.has("tickLength"), false);
  assert.equal(keys.has("tickDirection"), false);
  assert.equal(keys.has("tickLabelColor"), false);
  assert.equal(keys.has("labelColor"), false);
});

test("chromeAxisStyleHas and chromeAxisStyleValue read snake-case keys only like Python", () => {
  assert.equal(chromeAxisStyleHas({}, "axis_color"), false);
  assert.equal(chromeAxisStyleHas({ axisColor: "#f00" }, "axis_color"), false);
  assert.equal(chromeAxisStyleHas({ axis_color: "#f00" }, "axis_color"), true);
  assert.equal(chromeAxisStyleValue({}, "grid_color", "#202020"), "#202020");
  assert.equal(chromeAxisStyleValue({ gridColor: "#0f0" }, "grid_color", "#202020"), "#202020");
  assert.equal(chromeAxisStyleValue({ grid_color: "#0f0" }, "grid_color", "#202020"), "#0f0");
});

test("chromeStyleHasFontFamily uses font-family key only like Python", () => {
  assert.equal(chromeStyleHasFontFamily({}), false);
  assert.equal(chromeStyleHasFontFamily({ fontFamily: "Example Sans" }), false);
  assert.equal(chromeStyleHasFontFamily({ "font-family": "Example Sans" }), true);
  assert.equal(chromeStyleHasFontFamily({ "font-family": "" }), true);
});

test("figureClassName uses class_name only like Python", () => {
  assert.equal(figureClassName({}), undefined);
  assert.equal(figureClassName({ className: "browser-only" }), undefined);
  assert.equal(figureClassName({ class_name: "browser-only" }), "browser-only");
});

test("figureClassNames uses class_names only like Python", () => {
  assert.equal(figureClassNames({}), undefined);
  assert.equal(figureClassNames({ classNames: { title: "x" } }), undefined);
  assert.deepEqual(figureClassNames({ class_names: { title: "x" } }), { title: "x" });
});

test("annotationClassName uses class_name only like Python", () => {
  assert.equal(annotationClassName({}), undefined);
  assert.equal(annotationClassName({ className: "custom" }), undefined);
  assert.equal(annotationClassName({ class_name: "custom" }), "custom");
});

test("figureExtraLegends uses extra_legends only like Python", () => {
  assert.equal(figureExtraLegends({}), undefined);
  assert.equal(figureExtraLegends({ extraLegends: [{}] }), undefined);
  assert.deepEqual(figureExtraLegends({ extra_legends: [{}] }), [{}]);
});

test("figureTitleOptions uses title_options only like Python", () => {
  assert.equal(figureTitleOptions({}), undefined);
  assert.equal(figureTitleOptions({ titleOptions: { text: "T" } }), undefined);
  assert.deepEqual(figureTitleOptions({ title_options: { text: "T" } }), { text: "T" });
});

test("figureLegendOptions uses legend_options only like Python", () => {
  assert.equal(figureLegendOptions({}), undefined);
  assert.equal(figureLegendOptions({ legend: { loc: "best" } }), undefined);
  assert.deepEqual(figureLegendOptions({ legend_options: { loc: "best" } }), { loc: "best" });
});

test("figureColorbarOptions uses colorbar_options only like Python", () => {
  assert.equal(figureColorbarOptions({}), undefined);
  assert.equal(figureColorbarOptions({ colorbarOptions: { domain: [0, 1] } }), undefined);
  assert.deepEqual(figureColorbarOptions({ colorbar_options: { domain: [0, 1] } }), { domain: [0, 1] });
});

test("figureShowLegend uses show_legend only like Python", () => {
  assert.equal(figureShowLegend({}), undefined);
  assert.equal(figureShowLegend({ showLegend: false }), undefined);
  assert.equal(figureShowLegend({ show_legend: false }), false);
});

test("figureAxisOptions uses axis_options only like Python", () => {
  assert.equal(figureAxisOptions({}), undefined);
  assert.equal(figureAxisOptions({ xAxis: { label: "X" } }), undefined);
  assert.equal(figureAxisOptions({ x_axis: { label: "X" } }), undefined);
  assert.deepEqual(figureAxisOptions({ axis_options: { x: { label: "X" } } }), { x: { label: "X" } });
});

test("figureAutorangeAxisOptions uses axis_options only like Python", () => {
  assert.deepEqual(figureAutorangeAxisOptions({}, "x"), {});
  assert.deepEqual(figureAutorangeAxisOptions({ xAxis: { type: "log" } }, "x"), {});
  assert.deepEqual(figureAutorangeAxisOptions({ axis_options: { x: { type: "log" } } }, "x"), { type: "log" });
});

test("figureAutorangeAxisScale uses type only like Python _axis_scale", () => {
  assert.equal(figureAutorangeAxisScale({}), "linear");
  assert.equal(figureAutorangeAxisScale({ kind: "log" }), "linear");
  assert.equal(figureAutorangeAxisScale({ type: "log" }), "log");
  assert.equal(figureAutorangeAxisScale({ type: "symlog" }), "symlog");
  assert.equal(figureAutorangeAxisScale({ type: "time" }), "linear");
});

test("figureAxisKind Node scatter f64 stays linear unlike Python Column.kind", () => {
  // Python Column infers time_ms. Node scatter() stores f64, so the
  // time_ms scan is a no-op on typical traces.
  const fig = figure();
  fig.scatter([1, 2], [3, 4]);
  assert.equal(fig.traces[0].x.kind, undefined);
  assert.equal(figureAxisKind(fig, "x"), "linear");
});

test("figureAxisKind matches Python _axis_kind", () => {
  assert.equal(figureAxisKind({}, "x"), "linear");
  assert.equal(figureAxisKind({ axis_options: { x: { kind: "time" } } }, "x"), "linear");
  assert.equal(figureAxisKind({ axis_options: { x: { type: "time" } } }, "x"), "time");
  assert.equal(figureAxisKind({ _axis_categories: { x: [] } }, "x"), "category");
  assert.equal(figureAxisKind({
    traces: [{ x_axis: "x", y_axis: "y", x: { kind: "time_ms" }, y: { kind: "float" } }],
  }, "x"), "time");
  assert.equal(figureAxisKind({
    traces: [{ x_axis: "x", y_axis: "y", x: { kind: "time_ms" }, y: { kind: "float" } }],
  }, "y"), "linear");
});

test("chromeAxisTickKind uses Figure._axisKind like Python", () => {
  const fig = figure();
  assert.equal(chromeAxisTickKind(fig, "x"), 0);
  fig.setAxis("x", { kind: "time" });
  assert.equal(chromeAxisTickKind(fig, "x"), 0);
  const timed = figure();
  timed.setAxis("x", { type: "time" });
  assert.equal(chromeAxisTickKind(timed, "x"), 1);
  const cat = figure();
  cat._axis_categories = { x: [] };
  assert.equal(chromeAxisTickKind(cat, "x"), 2);
});

test("xyEfResolvedKind uses Figure._axisKind like Python", () => {
  const fig = figure();
  assert.equal(xyEfResolvedKind(fig, "x"), 0);
  fig.setAxis("x", { kind: "time" });
  assert.equal(xyEfResolvedKind(fig, "x"), 0);
  const timed = figure();
  timed.setAxis("x", { type: "time" });
  assert.equal(xyEfResolvedKind(timed, "x"), 1);
  const cat = figure();
  cat._axis_categories = { x: [] };
  assert.equal(xyEfResolvedKind(cat, "x"), 2);
});

test("figureAutorangeThetaUnit uses theta_unit only like Python", () => {
  assert.equal(figureAutorangeThetaUnit({}), undefined);
  assert.equal(figureAutorangeThetaUnit({ thetaUnit: "degrees" }), undefined);
  assert.equal(figureAutorangeThetaUnit({ theta_unit: "degrees" }), "degrees");
});

test("setPolarMeta writes axis theta_unit like Python set_axis", () => {
  const fig = figure();
  fig.setPolarMeta({ thetaUnit: "degrees" });
  assert.equal(figureAutorangeThetaUnit(figureAutorangeAxisOptions(fig, "x")), "degrees");
  const leftover = figure();
  leftover._polarMeta = { thetaUnit: "degrees" };
  leftover.coords = "polar";
  assert.equal(figureAutorangeThetaUnit(figureAutorangeAxisOptions(leftover, "x")), undefined);
});

test("setPolarMeta writes axis theta_zero like Python set_axis", () => {
  const fig = figure();
  fig.setPolarMeta({ thetaZero: "N" });
  assert.equal(polarAxisThetaZero(figureAutorangeAxisOptions(fig, "x")), "N");
  const leftover = figure();
  leftover._polarMeta = { thetaZero: "N" };
  leftover.coords = "polar";
  assert.equal(polarAxisThetaZero(figureAutorangeAxisOptions(leftover, "x")), "E");
});

test("setPolarMeta writes axis theta_direction like Python set_axis", () => {
  const fig = figure();
  fig.setPolarMeta({ thetaDirection: "clockwise" });
  assert.equal(polarAxisThetaDirection(figureAutorangeAxisOptions(fig, "x")), "clockwise");
  const leftover = figure();
  leftover._polarMeta = { thetaDirection: "clockwise" };
  leftover.coords = "polar";
  assert.equal(polarAxisThetaDirection(figureAutorangeAxisOptions(leftover, "x")), undefined);
});

test("setPolarMeta writes axis grid_shape like Python set_axis", () => {
  const fig = figure();
  fig.setPolarMeta({ gridShape: "linear" });
  assert.equal(polarGridShape(figureAutorangeAxisOptions(fig, "x")), "linear");
  const leftover = figure();
  leftover._polarMeta = { gridShape: "linear" };
  leftover.coords = "polar";
  assert.equal(polarGridShape(figureAutorangeAxisOptions(leftover, "x")), "circular");
});

test("setPolarMeta writes axis hole like Python set_axis", () => {
  const fig = figure();
  fig.setPolarMeta({ hole: 0.25 });
  assert.equal(figureAutorangeAxisOptions(fig, "y").hole, 0.25);
  const leftover = figure();
  leftover._polarMeta = { hole: 0.25 };
  leftover.coords = "polar";
  assert.equal(figureAutorangeAxisOptions(leftover, "y").hole, undefined);
});

test("setPolarMeta writes axis sector like Python set_axis", () => {
  const fig = figure();
  fig.setPolarMeta({ sector: [0, Math.PI] });
  assert.deepEqual(figureAutorangeAxisOptions(fig, "x").sector, [0, Math.PI]);
  const leftover = figure();
  leftover._polarMeta = { sector: [0, Math.PI] };
  leftover.coords = "polar";
  assert.equal(figureAutorangeAxisOptions(leftover, "x").sector, undefined);
});

test("_polarAxisSpecs empty theta_unit uses Python or-default", () => {
  const fig = figure();
  fig.setPolarMeta({ thetaUnit: "" });
  assert.equal(fig._polarAxisSpecs([0, 1], [0, 1]).x.theta_unit, "radians");
});

test("_polarAxisSpecs uses axis theta_unit like Python _axis_spec", () => {
  const fig = figure();
  fig.setPolarMeta({ thetaUnit: "degrees" });
  assert.equal(fig._polarAxisSpecs([0, 1], [0, 1]).x.theta_unit, "degrees");
  const leftover = figure();
  leftover.coords = "polar";
  leftover._polarMeta = { thetaUnit: "degrees" };
  assert.equal(leftover._polarAxisSpecs([0, 1], [0, 1]).x.theta_unit, "radians");
});

test("_polarAxisSpecs uses axis theta_zero like Python _axis_spec", () => {
  const fig = figure();
  fig.setPolarMeta({ thetaZero: "N" });
  assert.equal(fig._polarAxisSpecs([0, 1], [0, 1]).x.theta_zero, "N");
  const leftover = figure();
  leftover.coords = "polar";
  leftover._polarMeta = { thetaZero: "N" };
  assert.equal(leftover._polarAxisSpecs([0, 1], [0, 1]).x.theta_zero, "E");
});

test("_polarAxisSpecs empty theta_direction uses Python or-default", () => {
  const fig = figure();
  fig.setPolarMeta({ thetaDirection: "" });
  assert.equal(fig._polarAxisSpecs([0, 1], [0, 1]).x.theta_direction, "counterclockwise");
});

test("_polarAxisSpecs uses axis theta_direction like Python _axis_spec", () => {
  const fig = figure();
  fig.setPolarMeta({ thetaDirection: "clockwise" });
  assert.equal(fig._polarAxisSpecs([0, 1], [0, 1]).x.theta_direction, "clockwise");
  const leftover = figure();
  leftover.coords = "polar";
  leftover._polarMeta = { thetaDirection: "clockwise" };
  assert.equal(leftover._polarAxisSpecs([0, 1], [0, 1]).x.theta_direction, "counterclockwise");
});

test("_polarAxisSpecs empty grid_shape uses Python or-default", () => {
  const fig = figure();
  fig.setPolarMeta({ gridShape: "" });
  assert.equal(fig._polarAxisSpecs([0, 1], [0, 1]).x.grid_shape, "circular");
});

test("_polarAxisSpecs uses axis grid_shape like Python _axis_spec", () => {
  const fig = figure();
  fig.setPolarMeta({ gridShape: "linear" });
  assert.equal(fig._polarAxisSpecs([0, 1], [0, 1]).x.grid_shape, "linear");
  const leftover = figure();
  leftover.coords = "polar";
  leftover._polarMeta = { gridShape: "linear" };
  assert.equal(leftover._polarAxisSpecs([0, 1], [0, 1]).x.grid_shape, "circular");
});

test("_polarAxisSpecs empty sector uses Python or-default", () => {
  const fig = figure();
  fig.setPolarMeta({ sector: [] });
  assert.deepEqual(fig._polarAxisSpecs([0, 1], [0, 1]).x.sector, [0, 2 * Math.PI]);
});

test("_polarAxisSpecs uses axis sector like Python _axis_spec", () => {
  const fig = figure();
  fig.setPolarMeta({ sector: [0, Math.PI] });
  assert.deepEqual(fig._polarAxisSpecs([0, 1], [0, 1]).x.sector, [0, Math.PI]);
  const leftover = figure();
  leftover.coords = "polar";
  leftover._polarMeta = { sector: [0, Math.PI] };
  assert.deepEqual(leftover._polarAxisSpecs([0, 1], [0, 1]).x.sector, [0, 2 * Math.PI]);
});

test("_polarAxisSpecs empty hole uses Python or-default", () => {
  const fig = figure();
  fig.setPolarMeta({ hole: "" });
  assert.equal(fig._polarAxisSpecs([0, 1], [0, 1]).y.hole, 0.0);
});

test("_polarAxisSpecs uses axis hole like Python _axis_spec", () => {
  const fig = figure();
  fig.setPolarMeta({ hole: 0.25 });
  assert.equal(fig._polarAxisSpecs([0, 1], [0, 1]).y.hole, 0.25);
  const leftover = figure();
  leftover.coords = "polar";
  leftover._polarMeta = { hole: 0.25 };
  assert.equal(leftover._polarAxisSpecs([0, 1], [0, 1]).y.hole, 0.0);
});

test("_polarAxisSpecs uses axis r_origin like Python _axis_spec", () => {
  const fig = figure();
  fig.coords = "polar";
  fig.setAxis("y", { r_origin: -1 });
  assert.equal(fig._polarAxisSpecs([0, 1], [0, 1]).y.r_origin, -1);
  const leftover = figure();
  leftover.coords = "polar";
  leftover._polarMeta = { rOrigin: -1 };
  assert.equal(leftover._polarAxisSpecs([0, 1], [0, 1]).y.r_origin, undefined);
});

test("packPolarSceneInput uses figure _range like Python _pack_polar_scene_input", () => {
  const fig = figure();
  fig.setPolarMeta({});
  fig.scatter([0, 1], [2, 8]);
  const packed = packPolarSceneInput(fig);
  const view = new DataView(packed.buffer, packed.byteOffset, packed.byteLength);
  const [ylo, yhi] = fig._range("y");
  assert.equal(view.getFloat64(52, true), ylo);
  assert.equal(view.getFloat64(60, true), yhi);
  const leftover = figure();
  leftover.coords = "polar";
  leftover.axis_options = { x: {}, y: { range: [10, 20] } };
  leftover.scatter([0, 1], [2, 8]);
  const leftoverPacked = packPolarSceneInput(leftover);
  const leftoverView = new DataView(
    leftoverPacked.buffer,
    leftoverPacked.byteOffset,
    leftoverPacked.byteLength,
  );
  const [lo, hi] = leftover._range("y");
  assert.equal(leftoverView.getFloat64(52, true), lo);
  assert.equal(leftoverView.getFloat64(60, true), hi);
  assert.notEqual(lo, 10);
  assert.notEqual(hi, 20);
});

test("figureAxisIsLog uses axis type only like Python _axis_scale log", () => {
  assert.equal(figureAxisIsLog({}, "x"), false);
  assert.equal(figureAxisIsLog({ xAxis: { type: "log" } }, "x"), false);
  assert.equal(figureAxisIsLog({ axis_options: { x: { scale: "log" } } }, "x"), false);
  assert.equal(figureAxisIsLog({ axis_options: { x: { type: "symlog" } } }, "x"), false);
  assert.equal(figureAxisIsLog({ axis_options: { x: { type: "log" } } }, "x"), true);
});

test("figureAutorangeCategories uses _axis_categories only like Python", () => {
  assert.equal(figureAutorangeCategories({
    coords: "polar",
    axis_options: { x: { categories: ["a"] } },
  }, "x"), undefined);
  assert.deepEqual(figureAutorangeCategories({
    coords: "polar",
    _axis_categories: { x: ["a"] },
  }, "x"), ["a"]);
  assert.equal(figureAutorangeCategories({
    coords: "cartesian",
    _axis_categories: { x: ["a"] },
  }, "x"), undefined);
});

test("figureAutorangeDomain uses axis domain only like Python", () => {
  assert.equal(figureAutorangeDomain({}), undefined);
  assert.deepEqual(figureAutorangeDomain({ domain: [0, 1] }), [0, 1]);
  assert.equal(figureAutorangeDomain(figureAutorangeAxisOptions({
    _axisRange: { x: [0, 1] },
    axis_options: { x: {} },
  }, "x")), undefined);
  const fig = figure();
  fig.setAxisDomain("x", [1, 0]);
  assert.deepEqual(figureAutorangeDomain(figureAutorangeAxisOptions(fig, "x")), [0, 1]);
});

test("scatterPayloadForceBin2d uses force_bin2d only like Python", () => {
  assert.equal(scatterPayloadForceBin2d({}), undefined);
  assert.equal(scatterPayloadForceBin2d({ style: { force_bin2d: true } }), undefined);
  assert.equal(scatterPayloadForceBin2d({ force_bin2d: true }), true);
});

test("scatterPayloadForceDensity uses force_density tri-state like Python", () => {
  assert.equal(scatterPayloadForceDensity({}), -1);
  assert.equal(scatterPayloadForceDensity({ style: { force_density: true } }), -1);
  assert.equal(scatterPayloadForceDensity({ force_density: true }), 1);
  assert.equal(scatterPayloadForceDensity({ force_density: false }), 0);
});

test("scatterPayloadForceDirect uses force_direct only like Python", () => {
  assert.equal(scatterPayloadForceDirect({}), undefined);
  assert.equal(scatterPayloadForceDirect({ style: { force_direct: true } }), undefined);
  assert.equal(scatterPayloadForceDirect({ force_direct: true }), true);
});

test("scatterPayloadForcePyramid uses force_pyramid only like Python", () => {
  assert.equal(scatterPayloadForcePyramid({}), undefined);
  assert.equal(scatterPayloadForcePyramid({ style: { force_pyramid: true } }), undefined);
  assert.equal(scatterPayloadForcePyramid({ force_pyramid: true }), true);
});

test("scatterPayloadNoRescan uses no_rescan only like Python", () => {
  assert.equal(scatterPayloadNoRescan({}), undefined);
  assert.equal(scatterPayloadNoRescan({ style: { no_rescan: true } }), undefined);
  assert.equal(scatterPayloadNoRescan({ no_rescan: true }), true);
});

test("figureXLabel uses x_label then axis label like Python", () => {
  assert.equal(figureXLabel({}, {}), undefined);
  assert.equal(figureXLabel({ xLabel: "X" }, {}), undefined);
  assert.equal(figureXLabel({ x_label: "X" }, {}), "X");
  assert.equal(figureXLabel({}, { label: "X" }), "X");
});

test("figureXLabel empty x_label stays unlike Python or-fallthrough", () => {
  // Python `_pack_figure_chrome` uses `figure.x_label or axis label`.
  // Node `??` keeps the empty string.
  assert.equal(figureXLabel({ x_label: "" }, { label: "X" }), "");
});

test("figureYLabel uses y_label then axis label like Python", () => {
  assert.equal(figureYLabel({}, {}), undefined);
  assert.equal(figureYLabel({ yLabel: "Y" }, {}), undefined);
  assert.equal(figureYLabel({ y_label: "Y" }, {}), "Y");
  assert.equal(figureYLabel({}, { label: "Y" }), "Y");
});

test("figureYLabel empty y_label stays unlike Python or-fallthrough", () => {
  // Python `_pack_figure_chrome` uses `figure.y_label or axis label`.
  // Node `??` keeps the empty string.
  assert.equal(figureYLabel({ y_label: "" }, { label: "Y" }), "");
});

test("plotTopAxisRoom uses top_axis_room only like Python", () => {
  assert.equal(plotTopAxisRoom({}), undefined);
  assert.equal(plotTopAxisRoom({ topAxisRoom: 10 }), undefined);
  assert.equal(plotTopAxisRoom({ top_axis_room: 10 }), 10);
});

test("hexbinPacksRgbaPlane uses color_ch only like Python", () => {
  const rgba = new Uint8Array([255, 0, 0, 255]);
  assert.equal(
    hexbinPacksRgbaPlane({
      kind: "hexbin",
      x: [0],
      color_ch: { mode: "direct_rgba", rgba },
    }),
    true,
  );
  assert.equal(
    hexbinPacksRgbaPlane({
      kind: "hexbin",
      x: [0],
      colorChannel: { mode: "direct_rgba", rgba },
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

test("meshJoinedFill uses joined_fill only like Python", () => {
  assert.equal(meshJoinedFill({}), false);
  assert.equal(meshJoinedFill({ style: { joinedFill: true } }), false);
  assert.equal(meshJoinedFill({ style: { joined_fill: true } }), true);
  assert.equal(meshJoinedFill({ style: { joined_fill: 1 } }), true);
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
  const camelOnly = itemWidths(
    {
      styleChannels: { stroke_width: { values: [1.5, 2.5] } },
      style: { stroke_width: 3 },
    },
    2,
  );
  assert.equal(camelOnly.length, 16);
  const camelView = new DataView(camelOnly.buffer, camelOnly.byteOffset, camelOnly.byteLength);
  assert.equal(camelView.getFloat64(0, true), 3);
  assert.equal(camelView.getFloat64(8, true), 3);
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
  const camelOnly = itemApplyOpacity(
    { styleChannels: { opacity: { values: [0.5, 0.5] } } },
    packed,
    2,
  );
  assert.equal(camelOnly, packed);
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
  assert.equal(
    scatterUsesDensity({ kind: "scatter", x: { length: 10 }, forceDensity: true }),
    false,
  );
  assert.equal(
    scatterUsesDensity({ kind: "scatter", x: { length: 10 }, force_density: true }),
    true,
  );
  assert.equal(
    scatterUsesDensity({ kind: "scatter", x: { length: 200_001 }, forceDirect: true }),
    true,
  );
  assert.equal(
    scatterUsesDensity({ kind: "scatter", x: { length: 200_001 }, force_direct: true }),
    true,
  );
});

test("sceneHeatmapShapeAdmit matches host table", () => {
  assert.equal(sceneHeatmapShapeAdmit(1, 2), true);
  assert.equal(sceneHeatmapShapeAdmit(0, 2), false);
  assert.equal(sceneHeatmapShapeAdmit(1, 0), false);
  assert.equal(sceneHeatmapShapeAdmit(1.5, 2), false);
  assert.equal(sceneHeatmapShapeAdmit(Number.NaN, 2), false);
  assert.equal(sceneHeatmapShapeAdmit(Number.POSITIVE_INFINITY, 2), false);
});


test("ribbonEndRgbaPair uses color_ch only like Python", () => {
  const pair = ribbonEndRgbaPair({
    count: 1,
    color_ch: { mode: "constant", constant: "#ff0000" },
    colorChannel: { mode: "constant", constant: "#0000ff" },
    color2_ch: { mode: "constant", constant: "#00ff00" },
  });
  assert.ok(pair != null);
  assert.deepEqual([...pair.source], [255, 0, 0, 255]);
  assert.deepEqual([...pair.target], [0, 255, 0, 255]);
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

test("classifyRibbonColor2 uses color_ch only like Python", () => {
  assert.equal(
    classifyRibbonColor2({
      kind: "ribbon",
      color_ch: { mode: "constant", constant: "#336699" },
      colorChannel: { mode: "constant", constant: "#111111" },
      color2_ch: { mode: "constant", constant: "#336699" },
    }),
    "solid",
  );
});

test("roundedRectPoly zero radii is four corners", () => {
  const { x, y } = roundedRectPoly(0, 0, 4, 3, 0, 0, true);
  assert.deepEqual([...x], [0, 4, 4, 0]);
  assert.deepEqual([...y], [0, 0, 3, 3]);
});
