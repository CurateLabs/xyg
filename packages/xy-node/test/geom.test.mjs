import assert from "node:assert/strict";
import test from "node:test";

import {
  F32_SAFE_MAG,
  curveFlatten,
  f32SafeScale,
  geometryOffset,
  hexbinRing,
  markerPathScale,
  arrowGeometry,
  arrowShaftPoints,
  pinsOffsetToZero,
  sceneDashAdmit,
  sceneLinecapAdmit,
  densityOverlayOpacity,
  sceneMarkerPathAdmit,
  sceneAnnotationStyleAdmit,
  sceneRibbonColor2Classify,
  sceneTickLabelStrategy,
  sceneTickAnchor,
  sceneFillGradientAdmit,
  sceneParseLinearGradient,
  sceneRectExtraFlags,
  sceneGradientDir,
  sceneLinearGradientPrefix,
  sceneGradientSpace,
  sceneHexbinReduceAdmit,
  sceneCurveClassify,
  sceneMarkerGlyphAdmit,
  sceneKindAdmit,
  sceneKindClass,
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
