import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import test from "node:test";

import { axisTicks, tickLabelLayout, tickWindow, tickWindowFilter, legendBoxLayout, textBlockMeasure, textBlockRotatedExtent, yAxisLeftRoom, compatIsCompact, compatDefaultPadding, compatTitleWrapWidth, compatColorbarExtra, polarLegendRoom, polarLabelRoom, recutPolarPlot, tightLayoutSolve, encodeJpeg, encodePng, encodeWebp, scaleMap, scatterSceneSvg, sceneBatchEncode, sceneBrowserPainter, sceneExportSupportReason, sceneSupportReason, sceneVersion, svgToPdf } from "../src/index.js";
import { Figure, sceneRasterCommands, sceneSvg } from "../src/index.js";

const sceneFixture = JSON.parse(fs.readFileSync(new URL("../../../tests/fixtures/scene_v3.json", import.meta.url), "utf8"));
const figureSceneFixture = JSON.parse(fs.readFileSync(new URL("../../../tests/fixtures/figure_scene_v3.json", import.meta.url), "utf8"));
const authoredSceneFixture = JSON.parse(fs.readFileSync(new URL("../../../tests/fixtures/authored_scene_v20.json", import.meta.url), "utf8"));
const axisVisibilityFixture = JSON.parse(fs.readFileSync(new URL("../../../tests/fixtures/public_axis_visibility_scene.json", import.meta.url), "utf8"));
const axisTickFixture = JSON.parse(fs.readFileSync(new URL("../../../tests/fixtures/axis_ticks.json", import.meta.url), "utf8"));
const BUILTIN_SYMBOLS = [
  "circle", "square", "diamond", "triangle", "cross", "hexagon", "pentagon", "star",
  "triangle_down", "triangle_left", "triangle_right", "x", "point", "pixel",
  "thin_diamond", "plus_line", "x_line", "horizontal_line", "vertical_line",
];

test("Node projects Rust-owned Scene support decisions verbatim", () => {
  assert.equal(sceneSupportReason(0), "");
  assert.equal(
    sceneSupportReason((1n << 6n) | (1n << 1n)),
    "XYG_SCENE_UNSUPPORTED_CUSTOM_FONT: Scene v12 does not encode custom font resources",
  );
  assert.throws(() => sceneSupportReason(1n << 63n), /version or feature mask/);
  assert.throws(() => sceneSupportReason(0, 2), /version or feature mask/);
  for (const features of [true, "1", -1, -1n, Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(() => sceneSupportReason(features), /exact nonnegative u64 integer|u64 bit mask/);
  }
  assert.throws(() => sceneSupportReason(1n << 64n), /u64 bit mask/);
  for (const version of [true, -1, 1.5, 2 ** 32]) {
    assert.throws(() => sceneSupportReason(0, version), /requestVersion must be a u32 integer/);
  }

  const polar = new Figure({ coords: "polar" }); polar.line([0, 1], [0, 1]);
  assert.throws(() => polar.toScene(), /XYG_SCENE_UNSUPPORTED_POLAR/);
  const customFont = new Figure(); customFont.line([0, 1], [0, 1]);
  customFont.chromeStyles = { title: { fontFamily: "Example Sans" } };
  assert.throws(() => customFont.toScene(), /XYG_SCENE_UNSUPPORTED_CUSTOM_FONT/);
  const browserCss = new Figure(); browserCss.line([0, 1], [0, 1]); browserCss.className = "browser-only";
  assert.throws(() => browserCss.toScene(), /XYG_SCENE_UNSUPPORTED_BROWSER_CSS/);
  const gradient = new Figure(); gradient.bar([0], [1]); gradient.traces[0].style.fill = { type: "linear", colors: ["#000", "#fff"] };
  assert.throws(() => gradient.toScene(), /XYG_SCENE_UNSUPPORTED_GRADIENT/);
  for (const color of [
    { mode: "continuous", values: new Float64Array([0, 1]) },
    { mode: "direct_rgba", rgba: new Uint8Array(8) },
    { mode: "constant" },
  ]) {
    const colorChannel = new Figure(); colorChannel.scatter([0, 1], [0, 1]);
    colorChannel.traces[0].color = color;
    assert.throws(() => colorChannel.toScene(), /XYG_SCENE_UNSUPPORTED_GRADIENT/);
  }
  const constantColor = new Figure(); constantColor.scatter([0], [0]);
  constantColor.traces[0].color = { mode: "constant", color: "#3987e5" };
  assert.doesNotThrow(() => constantColor.toScene());
  const collision = new Figure(); collision.line([0, 1], [0, 1]);
  collision.setAxis("x", { collision: "hide" });
  assert.throws(() => collision.toScene(), /tick formatting/);
  const extraAxis = new Figure(); extraAxis.line([0, 1], [0, 1]);
  extraAxis.axis_options = { x: extraAxis.xAxis ?? {}, y: extraAxis.yAxis ?? {}, z: { label: "z" } };
  assert.throws(() => extraAxis.toScene(), /exactly x\/y/);
});

test("Node packs public-export eligibility through the shared Rust predicate", () => {
  const supported = new Figure({ width: 320, height: 240 });
  supported.setAxis("x", { domain: [0, 4] });
  supported.setAxis("y", { domain: [0, 5] });
  supported.scatter([1, 2], [2, 3], { style: { color: "#3987e5", size: 6, opacity: 0.8 } });
  assert.equal(sceneExportSupportReason(supported), null);

  const fluid = new Figure({ width: 320, height: 240 });
  fluid.width = "100%";
  fluid.scatter([1], [2]);
  assert.equal(sceneExportSupportReason(fluid), "XYG_SCENE_UNSUPPORTED_FLUID_VIEWPORT");

  const extraStyle = new Figure({ width: 320, height: 240 });
  extraStyle.setAxis("x", { domain: [0, 4] });
  extraStyle.setAxis("y", { domain: [0, 5] });
  extraStyle.scatter([1], [2], { style: { color: "#3987e5" } });
  extraStyle.style = { background: "#fff", "font-family": "Example Sans" };
  assert.equal(sceneExportSupportReason(extraStyle), "XYG_SCENE_UNSUPPORTED_PUBLIC_STYLE");

  const lineNoDomain = new Figure({ width: 320, height: 240 });
  lineNoDomain.line([0, 1], [0, 1]);
  assert.equal(sceneExportSupportReason(lineNoDomain), "XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS");
});

test("Node encodes Scene PDF through the shared Rust SVG→PDF converter", () => {
  const supported = new Figure({ width: 320, height: 240 });
  supported.setAxis("x", { domain: [0, 4] });
  supported.setAxis("y", { domain: [0, 5] });
  supported.scatter([1, 2], [2, 3], { style: { color: "#3987e5", size: 6, opacity: 0.8 } });
  const pdf = supported.toScenePdf();
  assert.equal(Buffer.compare(pdf.subarray(0, 8), Buffer.from("%PDF-1.4")), 0);
  assert.equal(Buffer.compare(pdf, svgToPdf(supported.toSceneSvg())), 0);
  assert.throws(() => svgToPdf("<svg><foreignObject/></svg>"), /unsupported SVG feature/);
});

test("Node encodes JPEG, PNG, and WebP through the shared Rust image encoders", () => {
  const rgb = Uint8Array.from([10, 20, 30, 40, 50, 60]);
  const jpeg = encodeJpeg(rgb, 2, 1, 3, 90);
  assert.equal(Buffer.compare(jpeg.subarray(0, 2), Buffer.from([0xff, 0xd8])), 0);
  assert.equal(Buffer.compare(jpeg.subarray(jpeg.length - 2), Buffer.from([0xff, 0xd9])), 0);
  const webp = encodeWebp(Uint8Array.from([10, 20, 30, 255]), 1, 1, 4);
  assert.equal(Buffer.compare(webp.subarray(0, 4), Buffer.from("RIFF")), 0);
  assert.equal(Buffer.compare(webp.subarray(8, 12), Buffer.from("WEBP")), 0);
  const png = encodePng(Uint8Array.from([255, 0, 0, 255, 0, 0, 255, 255]), 2, 1, 4, 0, 6);
  assert.equal(Buffer.compare(png.subarray(0, 8), Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])), 0);
  assert.equal(png[25], 3); // indexed palette for two colors
  assert.throws(() => encodeJpeg(rgb, 2, 1, 3, 0), /quality/);
  assert.throws(() => encodePng(rgb, 2, 1, 3, 2, 6), /mode/);
});

test("Node figure compiles the exact shared scatter, line, bar Scene v4 fixture", () => {
  const figure = new Figure({ width: 320, height: 240 });
  figure.setAxisDomain("x", [0, 4]); figure.setAxisDomain("y", [0, 5]);
  figure.scatter([1, 2], [2, 3], { id: 0, style: { color: "#3987e5", size: 6, opacity: 0.8, symbol: "diamond" } });
  figure.line([1, 2, 3], [1, 4, 2], { id: 1, color: "#ef4444", width: 2 });
  figure.bar([1, 2], [3, 2], { id: 2, color: "#22c55e", opacity: 0.85 });
  const encoded = figure.toScene();
  assert.equal(crypto.createHash("sha256").update(encoded).digest("hex"), figureSceneFixture.expected_sha256);
  assert.equal(encoded[160 + 3 * 16 + 2], 2); // canonical diamond symbol code
  const svg = sceneSvg(encoded);
  assert.match(svg, /^<svg xmlns=/);
  assert.match(svg, /data-xy-chrome="grid"/);
  assert.match(svg, /data-xy-chrome="axes"/);
  assert.equal((svg.match(/<text /g) ?? []).length, 6);
  assert.ok(sceneRasterCommands(encoded).length > 100);
});

test("Node matches Python bytes for all constant built-in scatter symbols", () => {
  const figure = new Figure({ width: 760, height: 720 });
  figure.setAxisDomain("x", [-1, 19]); figure.setAxisDomain("y", [0, 1]);
  for (const [code, symbol] of BUILTIN_SYMBOLS.entries()) {
    figure.scatter([code], [0.5], {
      id: code,
      name: symbol,
      style: { color: "#3987e5", size: 8, opacity: 1, symbol },
    });
  }
  const scene = figure.toScene();
  assert.equal(
    crypto.createHash("sha256").update(scene).digest("hex"),
    figureSceneFixture.public_builtin_symbols_sha256,
  );
  const svg = sceneSvg(scene);
  assert.equal((svg.match(/role="listitem"/g) ?? []).length, 19);
  for (const symbol of BUILTIN_SYMBOLS) assert.match(svg, new RegExp(`>${symbol}</text>`));
  assert.ok((svg.match(/fill="none" stroke="rgb\(57,135,229\)" stroke-width="1"/g) ?? []).length >= 8);

  const painter = sceneBrowserPainter(scene);
  const view = new DataView(painter.buffer, painter.byteOffset, painter.byteLength);
  assert.equal(view.getUint32(20, true), 19);
  const headerBytes = view.getUint32(12, true);
  const descriptorBytes = view.getUint32(16, true);
  for (let code = 0; code < 19; code += 1) {
    const descriptor = headerBytes + code * descriptorBytes;
    assert.equal(painter[descriptor], 0);
    assert.equal(painter[descriptor + 1], code);
    assert.equal(view.getFloat32(descriptor + 40, true), code >= 15 ? 1 : 0);
  }
  assert.ok(Buffer.from(painter).includes(Buffer.from("XYLG")));
  assert.ok(sceneRasterCommands(scene).length > 100);
});

test("Node matches Python bytes for the bounded public literal triangle mesh", () => {
  const figure = new Figure({ width: 360, height: 260 });
  figure.setAxisDomain("x", [0, 2]); figure.setAxisDomain("y", [0, 2]);
  figure.triangleMesh(
    [-0.25, 1], [0.25, 0.5], [0.75, 2.25], [0.25, 0.5], [0.25, 1.5], [1.25, 1.75],
    { id: 0, name: "literal mesh", color: "#22c55e", opacity: 0.75 },
  );
  const scene = figure.toScene();
  assert.equal(
    crypto.createHash("sha256").update(scene).digest("hex"),
    figureSceneFixture.public_triangle_mesh_sha256,
  );
  const svg = sceneSvg(scene);
  assert.equal((svg.match(/<path d="M /g) ?? []).length, 2);
  assert.match(svg, /<g clip-path="url\(#xy-scene-plot\)">/);
  assert.match(svg, />literal mesh<\/text>/);
  assert.ok(svg.indexOf("</g>", svg.indexOf("clip-path")) < svg.indexOf('data-xy-chrome="legend"'));
  const raster = sceneRasterCommands(scene);
  assert.ok(raster.length > 100);
  assert.ok(Buffer.from(raster).includes(Buffer.from("literal mesh")));

  const painter = sceneBrowserPainter(scene);
  const view = new DataView(painter.buffer, painter.byteOffset, painter.byteLength);
  const headerBytes = view.getUint32(12, true);
  const descriptorBytes = view.getUint32(16, true);
  assert.equal(view.getUint32(20, true), 2);
  for (let group = 0; group < 2; group += 1) {
    const descriptor = headerBytes + group * descriptorBytes;
    assert.equal(painter[descriptor], 4);
    assert.equal(view.getUint32(descriptor + 4, true), 3);
    assert.deepEqual(Array.from(painter.subarray(descriptor + 32, descriptor + 36)), [34, 197, 94, 191]);
    assert.deepEqual(Array.from(painter.subarray(descriptor + 36, descriptor + 40)), [0, 0, 0, 0]);
    assert.equal(view.getFloat32(descriptor + 40, true), 0);
  }
  const firstXOffset = view.getUint32(headerBytes + 8, true);
  assert.ok(view.getFloat32(firstXOffset, true) < view.getFloat32(32, true));
  assert.ok(Buffer.from(painter).includes(Buffer.from("XYLG")));
});

test("Node numeric tick formats match Python bytes and every Rust Scene consumer", () => {
  const figure = new Figure({ width: 420, height: 260 });
  figure.setAxis("x", { domain: [0, 1], format: ".1%" });
  figure.setAxis("y", { domain: [-15000, 15000], format: "$,.0f USD" });
  figure.scatter([0, 1], [-10000, 10000], { id: 0 });
  const scene = figure.toScene();
  assert.equal(crypto.createHash("sha256").update(scene).digest("hex"), figureSceneFixture.numeric_tick_format_sha256);
  const consumers = [Buffer.from(sceneSvg(scene)), Buffer.from(sceneRasterCommands(scene)), Buffer.from(sceneBrowserPainter(scene))];
  for (const label of ["0.0%", "50.0%", "100.0%", "$-10,000 USD", "$0 USD", "$10,000 USD"]) {
    assert.ok(consumers.every((consumer) => consumer.includes(Buffer.from(label))), label);
  }
});

test("Node authored tick labels override the format envelope byte-for-byte", () => {
  const build = (format) => {
    const figure = new Figure({ width: 320, height: 240 });
    figure.setAxis("x", { domain: [0, 1], tick_values: [0, 1], tick_labels: ["low", "high"], format });
    figure.setAxisDomain("y", [0, 1]);
    figure.scatter([0, 1], [0, 1], { id: 0 });
    return figure.toScene();
  };
  assert.deepEqual(Buffer.from(build("$,.1f USD")), Buffer.from(build(null)));
});

test("Node numeric tick precision boundary and oversize fallback are Rust-owned", () => {
  const build = (format, width = 320) => {
    const figure = new Figure({ width, height: 240 });
    figure.setAxis("x", { domain: [0, 4], format });
    figure.setAxisDomain("y", [0, 5]);
    figure.scatter([1, 2], [2, 3], { id: 0 });
    return figure.toScene();
  };
  assert.match(sceneSvg(build(".100f", 1600)), new RegExp(`>0\\.${"0".repeat(100)}<`));
  assert.deepEqual(Buffer.from(build(".101f")), Buffer.from(build(null)));
});

test("Node forwards nonlinear axis policy exactly like Python", () => {
  const figure = new Figure({ width: 320, height: 240 });
  figure.setAxis("x", { type: "symlog", constant: 2, domain: [-10, 10] });
  figure.setAxis("y", { type: "log", nonpositive: "mask", domain: [0.1, 10] });
  figure.scatter([-1, 1], [0.5, 2], { id: 0 });
  const scene = figure.toScene();
  assert.equal(crypto.createHash("sha256").update(scene).digest("hex"), figureSceneFixture.nonlinear_axis_forwarding_sha256);
  const view = new DataView(scene.buffer, scene.byteOffset, scene.byteLength);
  assert.deepEqual([view.getUint8(96), view.getUint8(97), view.getUint8(104), view.getUint8(105)], [2, 0, 1, 1]);
  assert.equal(view.getFloat64(144, true), 2);
});

test("Node figure defaults match Python Scene bytes and canonical values", () => {
  assert.deepEqual(figureSceneFixture.wasm_typed_series_v2, {
    magic: "XYTS", scatter_diameter: 8, line_stroke_width: 1.5,
    bar_half_width: 0.4, bar_baseline: 0, area_baseline: 0,
    default_stable_id_base: 1, arbitrary_stable_ids: [91, 7], joined_series_share_stable_id: true,
    default_fill_rgba: [37, 99, 235, 255], default_line_stroke_rgba: [37, 99, 235, 255],
  });
  const scene = (kind) => {
    const figure = new Figure({ width: 200, height: 120 });
    figure.setAxisDomain("x", [0, 1]); figure.setAxisDomain("y", [0, 1]);
    if (kind === "scatter") figure.scatter([0.25], [0.5], { id: 10 });
    else figure.line([0, 1], [0, 1], { id: 11 });
    return figure.toScene();
  };
  const scatter = scene("scatter"); const line = scene("line");
  assert.equal(crypto.createHash("sha256").update(scatter).digest("hex"), figureSceneFixture.default_scatter_sha256);
  assert.equal(crypto.createHash("sha256").update(line).digest("hex"), figureSceneFixture.default_line_sha256);
  assert.equal(new DataView(scatter.buffer, scatter.byteOffset).getFloat64(168, true), 0);
  assert.equal(new DataView(scatter.buffer, scatter.byteOffset).getFloat64(224, true), 4);
  assert.equal(new DataView(line.buffer, line.byteOffset).getFloat64(168, true), 1.5);
});

test("Node constant scatter stroke matches Python bytes and public defaults", () => {
  const figure = new Figure({ width: 320, height: 240 });
  figure.setAxisDomain("x", [0, 2]); figure.setAxisDomain("y", [0, 2]);
  figure.scatter([0.25, 1.75], [0.5, 1.5], {
    id: 41, name: "outlined",
    style: { color: "#336699", opacity: 0.75, size: 12, symbol: "diamond", stroke: "#ff8800", stroke_width: 3.5 },
  });
  const scene = figure.toScene();
  assert.equal(crypto.createHash("sha256").update(scene).digest("hex"), figureSceneFixture.public_scatter_stroke_sha256);
  const svg = sceneSvg(scene);
  assert.match(svg, /stroke="rgb\(255,136,0\)" stroke-opacity="0\.75"/);
  assert.match(svg, /stroke-width="3\.5"/);
  assert.match(svg, /outlined/);
  assert.ok(sceneRasterCommands(scene).byteLength > 0);
  assert.ok(sceneBrowserPainter(scene).byteLength > 0);

  const strokeOnly = new Figure({ width: 320, height: 240 });
  strokeOnly.scatter([0.5], [0.5], { style: { color: "#336699", stroke: "#ff8800" } });
  assert.equal(strokeOnly.traces[0].style.stroke_width, 1);
  assert.equal(new DataView(strokeOnly.toScene().buffer).getFloat64(168, true), 1);

  for (const strokeWidth of [-1, Number.NaN, Number.POSITIVE_INFINITY]) {
    const invalid = new Figure({ width: 320, height: 240 });
    invalid.scatter([0.5], [0.5], { style: { stroke: "#ff8800", stroke_width: strokeWidth } });
    assert.throws(() => invalid.toScene(), /invalid canonical scene batch/);
  }
});

test("Node frames the literal Scene colorbar side before Rust reserves its lane", () => {
  for (const [side, offset, viewport] of [["right", 64, 320], ["bottom", 72, 240]]) {
    const figure = new Figure({ width: 320, height: 240 });
    figure.scatter([0, 1], [0, 1]);
    figure.colorbarOptions = {
      domain: [0, 1],
      stops: [[0, [0, 0, 0, 255]], [1, [255, 255, 255, 128]]],
      side,
    };
    const scene = figure.toScene();
    assert.ok(viewport - new DataView(scene.buffer, scene.byteOffset, scene.byteLength).getFloat64(offset, true) >= 42);
  }
});

test("Node frames bounded Scene colorbar ticks and Rust renders shared major/minor chrome", () => {
  const figure = new Figure({ width: 320, height: 240 });
  figure.scatter([0, 1], [0, 1]);
  figure.colorbarOptions = {
    domain: [0, 1], stops: [[0, [0, 0, 0, 255]], [1, [255, 255, 255, 255]]],
    ticks: [0, 0.5, 1], minor_ticks: true,
  };
  const scene = figure.toScene(), offset = Buffer.from(scene).indexOf("XYCB"), view = new DataView(scene.buffer, scene.byteOffset + offset);
  assert.equal(view.getUint32(4, true), 2);
  assert.equal(view.getUint8(8), 0b1110);
  assert.equal(view.getUint32(16, true), 3);
  assert.deepEqual([view.getFloat64(80, true), view.getFloat64(88, true), view.getFloat64(96, true)], [0, 0.5, 1]);
  const svg = sceneSvg(scene);
  assert.equal((svg.match(/data-xy-slot="colorbar_tick"/g) ?? []).length, 6);
  assert.equal((svg.match(/data-xy-slot="colorbar_minor_tick"/g) ?? []).length, 8);
  assert.ok(Buffer.from(sceneBrowserPainter(scene)).includes(Buffer.from("XYCT")));
});

test("Node explicit hidden Cartesian chrome omits invisible groups without implying polar", () => {
  const chrome = new Uint8Array(200);
  new DataView(chrome.buffer).setFloat64(16, 12, true);
  const encoded = sceneBatchEncode({
    viewport: [200, 120], margins: [40, 20, 20, 30],
    xAxis: { id: 1, kind: "linear", domain: [0, 1] },
    yAxis: { id: 2, kind: "linear", domain: [0, 1] },
    kinds: [], stableIds: [], styleRefs: [], styles: [], diameter: [], symbols: [],
    x0: [], y0: [], x1: [], y1: [], chromeStyle: chrome, title: "Cartesian title",
  });
  const svg = sceneSvg(encoded);
  assert.doesNotMatch(svg, /data-xy-chrome="grid"/);
  assert.doesNotMatch(svg, /data-xy-chrome="axes"/);
  assert.match(svg, /data-xy-chrome="title"/);
  assert.match(svg, /Cartesian title/);

  const polar = new Figure({ coords: "polar" });
  polar.scatter([0], [1]);
  assert.throws(() => polar.toScene(), /supports Cartesian coordinates only/);
});

test("Node Scene v9 primary legend matches Python bytes and rejects unsupported variants", () => {
  const figure = new Figure({ width: 200, height: 120, legend: { loc: "lower left", title: "Series" } });
  figure.setAxisDomain("x", [0, 1]); figure.setAxisDomain("y", [0, 1]);
  figure.scatter([0.25], [0.5], { id: 0, name: "observed", style: { color: "#3987e5" } });
  const scene = figure.toScene(), offset = Buffer.from(scene).indexOf("XYLG"), legend = scene.subarray(offset);
  assert.equal(crypto.createHash("sha256").update(legend).digest("hex"), figureSceneFixture.primary_legend_sha256);
  const svg = sceneSvg(scene);
  assert.match(svg, /data-xy-chrome="legend"/); assert.match(svg, /role="listitem"/); assert.match(svg, /observed/);
  const unnamed = new Figure({ width: 200, height: 120 }); unnamed.scatter([1], [1], { name: "" });
  assert.equal(Buffer.from(unnamed.toScene()).indexOf("XYLG"), -1);
  assert.ok(Buffer.from(sceneRasterCommands(scene)).includes(Buffer.from("observed")));
  const multi = new Figure({ legend: { ncols: 2 } }); multi.scatter([1], [1], { name: "x" });
  assert.throws(() => multi.toScene(), /multiple columns/);
  const anchored = new Figure({ legend: { anchor: [1, 1] } }); anchored.scatter([1], [1], { name: "x" });
  assert.throws(() => anchored.toScene(), /anchors/);
  const interactive = new Figure({ legend: { toggle: true } }); interactive.scatter([1], [1], { name: "x" });
  assert.throws(() => interactive.toScene(), /static/);
  const automatic = new Figure({ legend: { loc: "best" } }); automatic.scatter([0, 1], [0, 1], { name: "x" });
  const resolved = automatic.toScene();
  const locByte = resolved[Buffer.from(resolved).indexOf("XYLG") + 4];
  assert.equal(locByte, 1); // upper left in Scene XYLG codes
});

test("Node Scene v9 whole-scene consumers reject malformed and unsupported input", () => {
  assert.throws(() => sceneSvg(Uint8Array.of(1, 2, 3)), /invalid canonical scene/);
  const figure = new Figure().heatmap([[0, 1], [1, 0]], { colormapStops: [0, 0, 0, 255, 255, 255] });
  assert.throws(() => figure.toScene(), /heatmap colormap/);
});

test("Node Scene v13 compiles bounded primary annotations and fails closed", () => {
  const figure = new Figure({ width: 320, height: 240 });
  figure.setAxisDomain("x", [0, 1]); figure.setAxisDomain("y", [0, 1]);
  for (const annotation of figureSceneFixture.node_public_annotations) figure.annotate(annotation);
  const scene = figure.toScene(), svg = sceneSvg(scene);
  assert.equal(crypto.createHash("sha256").update(scene).digest("hex"), figureSceneFixture.node_public_annotations_sha256);
  assert.equal(new DataView(scene.buffer, scene.byteOffset).getUint32(4, true), 25);
  assert.ok(svg.indexOf("rgb(255,0,0)") < svg.indexOf("rgb(0,255,0)"));
  assert.ok(svg.indexOf("rgb(0,255,0)") < svg.indexOf("rgb(0,0,255)"));
  figure.annotations[2].text = "must not vanish";
  assert.doesNotThrow(() => figure.toScene());
  for (const style of [
    { color: "" }, { color: null }, { opacity: null }, { opacity: "" },
    { opacity: "opaque" }, { width: null }, { width: false },
  ]) {
    figure.annotations = [{ kind: "rule", axis: "x", value: 0.25, style }];
    assert.throws(() => figure.toScene(), /Scene v12 annotation/);
  }
  for (const annotation of [
    { kind: "rule", axis: "x", value: null },
    { kind: "rule", axis: "x", value: "" },
    { kind: "rule", axis: "x", value: false },
    { kind: "band", axis: "x", start: " ", end: 1 },
    { kind: "marker", x: "not-a-number", y: 1 },
    { kind: "marker", x: 0, y: 1, size: null },
    { kind: "marker", x: 0, y: 1, symbol: 2 },
  ]) {
    figure.annotations = [annotation];
    assert.throws(() => figure.toScene(), /Scene v12 annotation/);
  }
});

test("Node matches Python bytes for the full bounded public annotation family", () => {
  const figure = new Figure({ width: 320, height: 240 });
  figure.setAxisDomain("x", [0, 1]); figure.setAxisDomain("y", [0, 1]);
  figure.scatter([0, 1], [0, 1], { id: 0, style: { color: "#3987e5", size: 6, opacity: 0.8 } });
  for (const annotation of figureSceneFixture.public_annotation_family) figure.annotate(annotation);
  const scene = figure.toScene();
  assert.equal(
    crypto.createHash("sha256").update(scene).digest("hex"),
    figureSceneFixture.public_annotation_family_sha256,
  );
  const svg = sceneSvg(scene);
  for (const text of ["plain", "rule", "band", "marker", "callout", "wrapped", "text"]) {
    assert.match(svg, new RegExp(text));
  }
  assert.ok(sceneRasterCommands(scene).length > 100);
  assert.ok(Buffer.from(sceneBrowserPainter(scene)).includes(Buffer.from("wrapped")));
});

test("Node matches Python bytes for the bounded public literal geometry family", () => {
  const figure = new Figure({ width: 320, height: 240 });
  figure.setAxisDomain("x", [0, 4]); figure.setAxisDomain("y", [0, 5]);
  figure.line([0, 1, 2], [1, 3, 2], { id: 0, color: "#ef4444", width: 2 });
  figure.bar([0.5, 1.5], [2, 3], { id: 1, color: "#22c55e", opacity: 0.8 });
  const scene = figure.toScene();
  assert.equal(
    crypto.createHash("sha256").update(scene).digest("hex"),
    figureSceneFixture.public_literal_geometry_sha256,
  );
  const svg = sceneSvg(scene);
  assert.match(svg, /<polyline /);
  assert.match(svg, /<rect /);
  assert.ok(sceneRasterCommands(scene).length > 100);
  assert.ok(sceneBrowserPainter(scene).length > 300);
});

test("Node matches Python bytes for constant-style Cartesian heatmap Rects", () => {
  const figure = new Figure({ width: 320, height: 240 });
  figure.setAxisDomain("x", [0, 4]); figure.setAxisDomain("y", [0, 5]);
  figure.heatmap([[0, 1, 2], [3, 4, 5]], {
    x: [1, 2, 3], y: [1, 3], color: "#3987e5", opacity: 0.75, name: "heat", id: 0,
  });
  const scene = figure.toScene();
  assert.equal(
    crypto.createHash("sha256").update(scene).digest("hex"),
    figureSceneFixture.public_heatmap_sha256,
  );
  const svg = sceneSvg(scene);
  const clip = svg.match(/<g clip-path="url\(#xy-scene-plot\)">([\s\S]*?)<\/g>/);
  assert.equal((clip?.[1].match(/<rect /g) ?? []).length, 6);
  assert.match(svg, />heat<\/text>/);
  assert.ok(sceneRasterCommands(scene).length > 100);
  const painter = sceneBrowserPainter(scene);
  assert.equal(painter[new DataView(painter.buffer, painter.byteOffset, painter.byteLength).getUint32(12, true)], 2);
});

test("Node matches Python bytes for constant-style Cartesian hexbin PolyFill", () => {
  const x = [0.5, 1.5, 2.5, 3.5, 1, 2, 3];
  const y = [0.5, 0.5, 0.5, 0.5, 2, 2, 2];
  const C = [1, 2, 3, 4, 5, 6, 7];
  const cases = {
    count: { gridsize: [4, 4], range: [[0, 4], [0, 5]], color: "#3987e5", opacity: 0.75, name: "hex", id: 0 },
    mean: { gridsize: [4, 4], range: [[0, 4], [0, 5]], C, reduce: "mean", color: "#3987e5", opacity: 0.75, name: "hex", id: 0 },
    sum: { gridsize: [4, 4], range: [[0, 4], [0, 5]], C, reduce: "sum", color: "#3987e5", opacity: 0.75, name: "hex", id: 0 },
  };
  for (const [reduce, options] of Object.entries(cases)) {
    const figure = new Figure({ width: 320, height: 240 });
    figure.setAxisDomain("x", [0, 4]); figure.setAxisDomain("y", [0, 5]);
    figure.hexbin(x, y, options);
    const scene = figure.toScene();
    assert.equal(
      crypto.createHash("sha256").update(scene).digest("hex"),
      figureSceneFixture.public_hexbin_sha256[reduce],
    );
    const svg = sceneSvg(scene);
    assert.match(svg, /<path d="M /);
    assert.match(svg, />hex<\/text>/);
    assert.ok(sceneRasterCommands(scene).length > 100);
    const painter = sceneBrowserPainter(scene);
    assert.equal(painter[new DataView(painter.buffer, painter.byteOffset, painter.byteLength).getUint32(12, true)], 4);
    assert.ok(Buffer.from(painter).includes(Buffer.from("XYLG")));
  }
});

test("Node matches Python bytes for Rust-owned bounded violin geometry", () => {
  for (const orientation of ["vertical", "horizontal"]) {
    const figure = new Figure({ width: 320, height: 240 });
    figure.setAxisDomain("x", [-1, 5]); figure.setAxisDomain("y", [-1, 5]);
    figure.violin([[1, 2, 2, 3, 4], [2, 2.5, 3.5]], {
      bins: 8, width: 0.7, orientation, id: 0,
      color: "#7c3aed", opacity: 0.6, style: { fill: "#22c55e" },
    });
    const scene = figure.toScene();
    assert.equal(crypto.createHash("sha256").update(scene).digest("hex"), figureSceneFixture.public_violin_sha256[orientation]);
    assert.match(sceneSvg(scene), /<rect /); assert.ok(sceneRasterCommands(scene).length > 100); assert.ok(sceneBrowserPainter(scene).length > 300);
  }
});

test("Node matches Python bytes for Rust-owned bounded box geometry", () => {
  for (const orientation of ["vertical", "horizontal"]) {
    const figure = new Figure({ width: 320, height: 240 });
    figure.setAxisDomain("x", [-2, 102]); figure.setAxisDomain("y", [-2, 102]);
    figure.box([[1, 2, 3, 100], [2, 3, 4, 5]], {
      orientation, width: 0.7, color: "#7c3aed", opacity: 0.6, name: "dist",
    });
    figure.traces.forEach((trace, id) => { trace.id = id; });
    const scene = figure.toScene();
    assert.equal(crypto.createHash("sha256").update(scene).digest("hex"), figureSceneFixture.public_box_sha256[orientation]);
    assert.match(sceneSvg(scene), /<rect /); assert.match(sceneSvg(scene), /<polyline /);
    assert.ok(sceneRasterCommands(scene).length > 100); assert.ok(sceneBrowserPainter(scene).length > 300);
  }
});

test("Node preserves authored numeric box centers in both orientations", () => {
  for (const orientation of ["vertical", "horizontal"]) {
    const figure = new Figure({ width: 320, height: 240 });
    figure.setAxisDomain("x", [-2, 22]); figure.setAxisDomain("y", [-2, 22]);
    figure.box([[1, 2, 3], [4, 5, 20]], {
      x: [10, 20], orientation, width: 0.6, showOutliers: true,
    });
    figure.traces.forEach((trace, id) => { trace.id = id; });
    assert.equal(
      crypto.createHash("sha256").update(figure.toScene()).digest("hex"),
      figureSceneFixture.public_box_numeric_centers_sha256[orientation],
    );
  }
});

test("Node matches Python bytes for bounded literal geometry host transforms", () => {
  const variants = [
    ["step", (figure) => figure.step([0, 1, 2], [1, 3, 2], { id: 0, where: "mid" })],
    ["histogram", (figure) => figure.histogram([0, 1, 1, 2], { id: 0, bins: 2 })],
    // Node `bar` and Python `column` intentionally lower to the same Rect.
    ["column_bar", (figure) => figure.bar([0, 1], [1, 2], { id: 0 })],
  ];
  for (const [name, author] of variants) {
    const figure = new Figure({ width: 320, height: 240 });
    figure.setAxisDomain("x", [0, 4]); figure.setAxisDomain("y", [0, 5]);
    author(figure);
    assert.equal(
      crypto.createHash("sha256").update(figure.toScene()).digest("hex"),
      figureSceneFixture.public_literal_geometry_variants_sha256[name],
    );
  }
});

test("Node matches Python exact Rust-expanded step bytes in every mode and consumer", () => {
  for (const where of ["pre", "mid", "post"]) {
    const figure = new Figure({ width: 320, height: 240 });
    figure.setAxisDomain("x", [0, 4]); figure.setAxisDomain("y", [0, 5]);
    figure.step([0, 1, 2], [1, 3, 2], { id: 0, where });
    const scene = figure.toScene();
    assert.equal(
      crypto.createHash("sha256").update(scene).digest("hex"),
      figureSceneFixture.rust_step_modes_sha256[where],
    );
    assert.equal((sceneSvg(scene).match(/<polyline /g) ?? []).length, 1);
    assert.ok(sceneRasterCommands(scene).length > 100);
    assert.ok(sceneBrowserPainter(scene).length > 300);
  }
});

test("Node matches Python exact Rust-expanded ribbon bytes across axis scales and consumers", () => {
  const variants = [
    ["linear", { type: "linear", domain: [-10, 1000] }],
    ["log", { type: "log", domain: [1, 1000] }],
    ["symlog", { type: "symlog", domain: [-10, 1000], constant: 2 }],
  ];
  for (const [scale, yAxis] of variants) {
    const figure = new Figure({ width: 320, height: 240 });
    figure.setAxisDomain("x", [0, 10]); figure.setAxis("y", yAxis);
    figure.ribbon([1], [9], [1], [10], [100], [1000], {
      id: 7, color: "#7c3aed", opacity: 0.75, strokeWidth: 2,
      style: { fill_opacity: 0.8, stroke_opacity: 0.5 },
    });
    const scene = figure.toScene();
    assert.equal(
      crypto.createHash("sha256").update(scene).digest("hex"),
      figureSceneFixture.rust_ribbon_expansion_sha256[scale],
    );
    assert.equal(new DataView(scene.buffer, scene.byteOffset).getBigUint64(16, true), 97n);
    assert.deepEqual(scene.slice(160, 168), Uint8Array.of(124, 58, 237, 153, 124, 58, 237, 96));
    const svg = sceneSvg(scene);
    assert.equal((svg.match(/<path d="/g) ?? []).length, 1);
    assert.match(svg, /fill="rgb\(124,58,237\)" fill-opacity="0\.6"/);
    assert.match(svg, /stroke="rgb\(124,58,237\)" stroke-opacity="0\.38"/);
    assert.match(svg, /stroke-width="2"/);
    assert.ok(sceneRasterCommands(scene).length > 100);
    assert.ok(sceneBrowserPainter(scene).length > 300);
  }
});

test("Node Figure authoring accepts bounded annotations without exposing a second policy", () => {
  const source = { kind: "text", x: 0.5, y: 0.5, text: "owned by Rust", style: { color: "#ff0000" } };
  const fromConstructor = new Figure({ width: 320, height: 240, annotations: [source] });
  fromConstructor.setAxisDomain("x", [0, 1]); fromConstructor.setAxisDomain("y", [0, 1]);
  source.text = "caller mutation";
  source.style.color = "#0000ff";
  assert.match(sceneSvg(fromConstructor.toScene()), /owned by Rust/);
  assert.match(sceneSvg(fromConstructor.toScene()), /rgba\(255,0,0,1\.000000\)/);

  const fluent = new Figure({ width: 320, height: 240 });
  fluent.setAxisDomain("x", [0, 1]); fluent.setAxisDomain("y", [0, 1]);
  assert.equal(fluent.annotate({ kind: "text", x: 0.5, y: 0.5, text: "fluent" }), fluent);
  assert.match(sceneSvg(fluent.toScene()), /fluent/);
  assert.throws(() => fluent.annotate([]), /annotation must be an object/);
  assert.throws(() => new Figure({ annotations: {} }), /annotations must be an array/);
  assert.throws(() => new Figure({ annotations: [null] }), /annotation must be an object/);
});

test("Node Scene v16 frames bounded plain and attached text annotations and rejects malformed content", () => {
  const figure = new Figure({ width: 320, height: 240 });
  figure.setAxisDomain("x", [0, 1]); figure.setAxisDomain("y", [0, 1]);
  figure.annotations = [{ kind: "text", x: 0.5, y: 0.5, text: "<safe>" }];
  const scene = figure.toScene();
  assert.equal(new DataView(scene.buffer, scene.byteOffset).getUint32(4, true), 25);
  assert.match(sceneSvg(scene), /&lt;safe&gt;/);
  assert.ok(sceneRasterCommands(scene).length > 100);
  figure.annotations = [{ kind: "text", x: 0.5, y: 0.5, text: "boxed", style: { label_background: "#ffffff" } }];
  assert.match(sceneSvg(figure.toScene()), /data-xy-slot="annotation_label_box"[^>]*fill="rgba\(255,255,255,1\.000000\)"/);
  figure.annotations = [{ kind: "text", x: 2, y: 0.5, text: "outside" }];
  assert.throws(() => figure.toScene(), /invalid canonical scene batch/);
  figure.annotations = [{ kind: "text", x: 0.5, y: 0.5, text: "" }];
  assert.throws(() => figure.toScene(), /nonempty NUL-free text/);
});

test("Node frames literal attached-label paint and rejects it without a label", () => {
  const figure = new Figure({ width: 320, height: 240 });
  figure.setAxisDomain("x", [0, 1]); figure.setAxisDomain("y", [0, 1]);
  figure.annotations = [{ kind: "marker", x: 0.5, y: 0.5, text: "peak", style: { label_color: "#ff0000", label_opacity: 0.5 } }];
  assert.match(sceneSvg(figure.toScene()), /fill="rgba\(255,0,0,0\.501961\)"[^>]*>peak</);
  figure.annotations = [{ kind: "marker", x: 0.5, y: 0.5, style: { label_color: "#ff0000" } }];
  assert.throws(() => figure.toScene(), /does not encode/);
});

test("Node Scene v16 accepts both independently bounded annotation text frames", () => {
  const figure = new Figure({ width: 320, height: 240 });
  figure.setAxisDomain("x", [0, 1]); figure.setAxisDomain("y", [0, 1]);
  figure.annotations = [];
  const text = "x".repeat(4096);
  for (let index = 0; index < 1; index += 1) {
    figure.annotations.push({ kind: "text", x: 0.5, y: 0.5, text });
    figure.annotations.push({ kind: "marker", x: 0.5, y: 0.5, text });
  }
  assert.match(sceneSvg(figure.toScene()), /x{4096}/);
});

test("Node frames bounded raw-coordinate straight arrows and rejects richer forms", () => {
  const figure = new Figure({ width: 320, height: 240 });
  figure.setAxisDomain("x", [0, 1]); figure.setAxisDomain("y", [0, 1]);
  figure.annotations = [{ kind: "arrow", x0: 0.1, y0: 0.2, x1: 0.8, y1: 0.7, style: { color: "#ff0000", opacity: 0.5, width: 2 } }];
  assert.doesNotThrow(() => figure.toScene());
  figure.annotations[0].text = "no";
  assert.throws(() => figure.toScene(), /arrows do not encode text/);
  figure.annotations = [{ kind: "arrow", x0: 0, y0: 0, x1: 1, y1: 1, style: { dash: "2,2" } }];
  assert.throws(() => figure.toScene(), /arrow style does not encode/);
});

test("Node frames callout label backgrounds as XYAC v2 and retains v1 otherwise", () => {
  const plain = new Figure({ width: 320, height: 240 });
  plain.setAxisDomain("x", [0, 1]); plain.setAxisDomain("y", [0, 1]);
  plain.annotations = [{ kind: "callout", x: 0.5, y: 0.5, text: "plain" }];
  assert.doesNotThrow(() => plain.toScene());

  const mixed = new Figure({ width: 320, height: 240 });
  mixed.setAxisDomain("x", [0, 1]); mixed.setAxisDomain("y", [0, 1]);
  mixed.annotations = [
    { kind: "callout", x: 0.25, y: 0.25, text: "clear" },
    { kind: "callout", x: 0.75, y: 0.75, text: "filled", style: { label_background: "#123456" } },
  ];
  assert.doesNotThrow(() => mixed.toScene());
  mixed.annotations[1].style.label_background = 7;
  assert.throws(() => mixed.toScene(), /callout label background/);
});

test("Node Scene v20 Cartesian callout matches the Python exact-byte fixture", () => {
  const figure = new Figure({ width: 320, height: 240 });
  figure.setAxisDomain("x", [0, 1]); figure.setAxisDomain("y", [0, 1]);
  figure.scatter([0, 1], [0, 1], { id: 0 });
  figure.annotations = [{
    kind: "callout", x: 0.5, y: 0.5, text: "Rust", dx: -12, dy: -18,
    style: { color: "#344054", label_background: "#ffffff" },
  }];
  const scene = figure.toScene();
  assert.equal(crypto.createHash("sha256").update(scene).digest("hex"), figureSceneFixture.cartesian_callout_sha256);
  assert.match(sceneSvg(scene), /Rust/);
  assert.ok(sceneRasterCommands(scene).length > 0);
  assert.ok(Buffer.from(sceneBrowserPainter(scene)).includes(Buffer.from("XYLB")));
});

test("Node matches the public Python disconnected segments, errorbar caps, and stem fixture", () => {
  const figure = new Figure({ width: 320, height: 240 });
  figure.setAxisDomain("x", [0, 4]); figure.setAxisDomain("y", [0, 5]);
  figure.segments([0.25, 2.5], [0.5, 0.75], [1.25, 3.5], [1.5, 2], { color: "#ef4444" });
  figure.errorbar([1, 2], [2, 3], { yerr: [0.25, 0.5], capSize: 0.2, color: "#16a34a" });
  figure.errorbar([0.75, 1.5], [4.25, 4.5], {
    yerr: [0.15, 0.25], xerr: [0.1, 0.2], capSize: 0, color: "#9333ea",
  });
  figure.stem([3, 3.5], [3.5, 4], { base: 1, color: "#2563eb", symbol: "diamond" });
  // Bindings assign trace identities independently; fixture identity is
  // explicit so exact bytes prove the shared Rust-owned paint order.
  figure.traces.forEach((trace, index) => { trace.id = index; });
  assert.deepEqual(figure.traces.map((trace) => trace.style.role), [
    "segments", "y-errorbar", "y-errorbar", "x-errorbar", "stem", "stem-marker",
  ]);
  const scene = figure.toScene();
  assert.equal(
    crypto.createHash("sha256").update(scene).digest("hex"),
    figureSceneFixture.public_disconnected_segments_sha256,
  );
  const svg = sceneSvg(scene);
  assert.equal((svg.match(/<polyline /g) ?? []).length, 14);
  assert.ok(sceneRasterCommands(scene).length > 100);
  assert.ok(sceneBrowserPainter(scene).length > 100);
});

test("Node Scene v9 compiles ribbon and triangle_mesh", () => {
  const ribbon = new Figure({ width: 320, height: 200 });
  ribbon.setAxisDomain("x", [0, 1]); ribbon.setAxisDomain("y", [0, 1]);
  ribbon.ribbon([0.1], [0.9], [0.2], [0.5], [0.3], [0.7], { color: "#7c3aed", name: null });
  assert.match(sceneSvg(ribbon.toScene()), /<path d="M /);
  const mesh = new Figure({ width: 240, height: 160 });
  mesh.setAxisDomain("x", [0, 1]); mesh.setAxisDomain("y", [0, 1]);
  mesh.triangleMesh([0], [0], [1], [0], [0.5], [1], { color: "#22c55e", name: null });
  assert.match(sceneSvg(mesh.toScene()), /<path d="M /);
});

test("Node Scene v9 compiles area bands", () => {
  const figure = new Figure({ width: 240, height: 160 });
  figure.setAxisDomain("x", [0, 2]); figure.setAxisDomain("y", [0, 3]);
  figure.area([0, 1, 2], [1, 2, 1.5], { base: 0, color: "#3987e5", opacity: 0.5 });
  const svg = sceneSvg(figure.toScene());
  assert.match(svg, /<path d="M /);
  assert.match(svg, / Z"/);
});

test("Node Scene v4 raster rejects nonrepresentable f32 commands", () => {
  const figure = new Figure().line([0, 1], [0, 1]);
  assert.throws(() => sceneRasterCommands(figure.toScene(), Number.MAX_VALUE), /invalid canonical scene/);
  const huge = sceneBatchEncode({
    viewport: [1e100, 1e100], margins: [0, 0, 0, 0],
    xAxis: { id: 1, domain: [0, 1] }, yAxis: { id: 2, domain: [0, 1] },
    kinds: [], stableIds: [], styleRefs: [], styles: [], diameter: [], symbols: [],
    x0: [], y0: [], x1: [], y1: [],
  });
  assert.throws(() => sceneRasterCommands(huge), /invalid canonical scene/);
  const hugeWidth = sceneBatchEncode({
    viewport: [100, 80], margins: [10, 10, 10, 10],
    xAxis: { id: 1, domain: [0, 1] }, yAxis: { id: 2, domain: [0, 1] },
    kinds: [1, 1], stableIds: [1, 1], styleRefs: [0, 0],
    styles: [{ fillRgba: [0, 0, 0, 0], strokeRgba: [0, 0, 0, 255], strokeWidth: 1e100 }],
    diameter: [0, 0], symbols: [0, 0], x0: [0, 1], y0: [0, 1], x1: [0, 0], y1: [0, 0],
  });
  assert.throws(() => sceneRasterCommands(hugeWidth), /invalid canonical scene/);
});

test("Node figure Scene v5 encodes titles and still rejects incomplete customization", () => {
  const titled = new Figure({ title: "Encoded title" }).scatter([1], [1]);
  const svg = titled.toSceneSvg();
  assert.match(svg, /data-xy-chrome="title"/);
  assert.match(svg, /Encoded title/);
  for (const key of ["marker_path", "marker_glyph"]) {
    const figure = new Figure();
    figure.scatter([1], [1], { _composed: true, style: { [key]: "M0 0" } });
    assert.throws(() => figure.toScene(), /authored markers/);
  }
  const named = new Figure();
  named.scatter([1], [1], { _composed: true, name: "series" });
  const legendSvg = named.toSceneSvg();
  assert.match(legendSvg, /data-xy-chrome="legend"/);
  assert.match(legendSvg, /series/);
  const unsafeId = new Figure();
  unsafeId.scatter([1], [1], { _composed: true, id: 2 ** 53 });
  assert.throws(() => unsafeId.toScene(), /stableIds/);
  const badSymbol = new Figure();
  badSymbol.scatter([1], [1], { _composed: true, style: { symbol: "kite" } });
  assert.throws(() => badSymbol.toScene(), /does not support scatter symbol "kite"/);
});

test("Node figure Scene v4 rejects missing coordinates until break records exist", () => {
  for (const kind of ["line", "scatter"]) {
    const figure = new Figure();
    figure[kind]([0, 1, 2], [1, Number.NaN, 2]);
    assert.throws(() => figure.toScene(), /missing-data breaks/);
  }
});

test("Node Scene v4 matches shared scatter, line, bar, and axis bytes", () => {
  const encoded = sceneBatchEncode({
    viewport: sceneFixture.viewport, margins: sceneFixture.margins,
    xAxis: { id: sceneFixture.x_axis[0], kind: "linear", domain: sceneFixture.x_axis.slice(2, 4), constant: sceneFixture.x_axis[4], nonpositive: "clip" },
    yAxis: { id: sceneFixture.y_axis[0], kind: "linear", domain: sceneFixture.y_axis.slice(2, 4), constant: sceneFixture.y_axis[4], nonpositive: "clip" },
    kinds: sceneFixture.kinds, stableIds: sceneFixture.stable_ids, styleRefs: sceneFixture.style_refs,
    styles: sceneFixture.styles.map((style) => ({ fillRgba: style.fill_rgba, strokeRgba: style.stroke_rgba, strokeWidth: style.stroke_width })),
    diameter: sceneFixture.diameter, symbols: sceneFixture.symbols,
    x0: sceneFixture.x0, y0: sceneFixture.y0, x1: sceneFixture.x1, y1: sceneFixture.y1,
  });
  assert.equal(crypto.createHash("sha256").update(encoded).digest("hex"), sceneFixture.expected_sha256);
  const records = 160 + sceneFixture.styles.length * 16;
  assert.equal(encoded[records + 1], 1); // center outside, full marker overlaps
  assert.equal(encoded[records + 2], 2); // diamond
  const view = new DataView(encoded.buffer, encoded.byteOffset);
  assert.equal(view.getFloat64(records + 48, true), 16);
  const line0 = records + 56;
  const line1 = line0 + 56;
  const rect = line1 + 56;
  assert.equal(view.getBigUint64(line0 + 8, true), 201n);
  assert.equal(view.getBigUint64(line1 + 8, true), 201n);
  assert.deepEqual([view.getFloat64(line0 + 32, true), view.getFloat64(line0 + 40, true)], [0, 0]);
  assert.deepEqual(Array.from({ length: 4 }, (_, index) => view.getFloat64(rect + 16 + index * 8, true)), [156, 142, 272, 318]);
});

test("Node Scene v9 authored chrome matches Python exact bytes", () => {
  const encoded = sceneBatchEncode({
    viewport: [100, 80], margins: [10, 10, 10, 10],
    xAxis: { id: 1, domain: [0, 1] }, yAxis: { id: 2, domain: [0, 1] },
    kinds: [0], stableIds: [9], styleRefs: [0],
    styles: [{ fillRgba: [1, 2, 3, 255], strokeRgba: [0, 0, 0, 0], strokeWidth: 0 }],
    diameter: [6], symbols: [0], x0: [0.5], y0: [0.5], x1: [0], y1: [0],
    chromeStyle: Uint8Array.from(Buffer.from(sceneFixture.authored_chrome_style_hex, "hex")),
    xMajorTicks: [0, 0.5, 1], xMinorTicks: [0.25, 0.75], yMajorTicks: [], yMinorTicks: [0.5],
  });
  assert.equal(crypto.createHash("sha256").update(encoded).digest("hex"), sceneFixture.authored_chrome_sha256);
  assert.match(sceneSvg(encoded), /data-xy-chrome="chart-background"/);
  assert.match(sceneSvg(encoded), /stroke="rgba\(23,24,25,1\.000000\)"/);
});

test("Node Figure authored chrome matches the Python Figure fixture bytes", () => {
  const fixture = sceneFixture.figure_authored_chrome;
  const figure = new Figure({ width: fixture.viewport[0], height: fixture.viewport[1] });
  figure.style = fixture.style;
  figure.setAxis("x", fixture.x_axis);
  figure.setAxis("y", fixture.y_axis);
  figure.scatter(fixture.scatter.x, fixture.scatter.y, { id: fixture.scatter.id });
  const encoded = figure.toScene({ margins: fixture.margins });
  assert.equal(crypto.createHash("sha256").update(encoded).digest("hex"), fixture.sha256);
  assert.match(sceneSvg(encoded), /data-xy-chrome="chart-background"/);
  assert.match(sceneSvg(encoded), /stroke="rgba\(23,24,25,1\.000000\)"/);
});

test("Node Figure axis visibility cases match the public Python Scene fixture", () => {
  assert.equal(axisVisibilityFixture.schema, "xyg-public-axis-visibility-scene-v1");
  for (const entry of axisVisibilityFixture.cases) {
    const figure = new Figure({
      width: axisVisibilityFixture.viewport[0], height: axisVisibilityFixture.viewport[1],
    });
    figure.setAxis("x", { domain: axisVisibilityFixture.domain });
    figure.setAxis("y", { domain: axisVisibilityFixture.domain });
    figure.setAxis(entry.axis, { domain: axisVisibilityFixture.domain, style: entry.style });
    figure.scatter(axisVisibilityFixture.scatter.x, axisVisibilityFixture.scatter.y, {
      id: axisVisibilityFixture.scatter.id,
      style: axisVisibilityFixture.scatter.style,
      _composed: true,
    });
    const encoded = figure.toScene();
    assert.equal(crypto.createHash("sha256").update(encoded).digest("hex"), entry.sha256);
    const painter = sceneBrowserPainter(encoded);
    assert.ok(painter.byteLength > 300);
  }
});

test("Node public Figure matches the combined Python authored Scene v25 fixture", () => {
  const fixture = authoredSceneFixture.authoring;
  const count = authoredSceneFixture.count;
  const x = Float64Array.from({ length: count }, (_, index) => index / (count - 1));
  const y = Float64Array.from({ length: count }, (_, index) => ((index * 37) % 997) / 498 - 1);
  const figure = new Figure({
    width: fixture.viewport[0], height: fixture.viewport[1], title: fixture.title,
    style: fixture.style, legend: fixture.legend, colorbar: fixture.colorbar,
    xAxis: fixture.axes.x, yAxis: fixture.axes.y,
    annotations: [
      { kind: "callout", ...fixture.callout },
      { kind: "callout", ...fixture.wrapped_callout },
    ],
  });
  figure.scatter(x, y, {
    id: fixture.scatter.id,
    name: fixture.scatter.name,
    style: {
      color: fixture.scatter.color,
      size: fixture.scatter.size,
      opacity: fixture.scatter.opacity,
      symbol: fixture.scatter.symbol,
    },
  });
  figure.scatter(fixture.circle_scatter.x, fixture.circle_scatter.y, {
    id: fixture.circle_scatter.id,
    name: fixture.circle_scatter.name,
    style: {
      color: fixture.circle_scatter.color,
      size: fixture.circle_scatter.size,
      opacity: fixture.circle_scatter.opacity,
      symbol: fixture.circle_scatter.symbol,
    },
  });
  const scene = figure.toScene();
  assert.equal(new DataView(scene.buffer, scene.byteOffset, scene.byteLength).getUint32(4, true), 25);
  assert.equal(crypto.createHash("sha256").update(scene).digest("hex"), authoredSceneFixture.scene_sha256);
  const svg = sceneSvg(scene), raster = sceneRasterCommands(scene);
  for (const text of ["Authored Scene evidence", "Fraction", "Signal", "Series", "observations", "reference", "Intensity", "representative callout", "wrapped annotation", "evidence", "second line"]) {
    assert.match(svg, new RegExp(text));
    assert.ok(Buffer.from(raster).includes(Buffer.from(text)));
  }
  assert.ok(raster.byteLength > 100);
  assert.match(svg, /data-xy-chrome="chart-background"/);
  assert.match(svg, /data-xy-chrome="plot-background"/);
  assert.match(svg, /data-xy-chrome="legend"/);
  assert.match(svg, /data-xy-slot="colorbar_tick"/);
  assert.match(svg, /data-xy-slot="annotation_label_box"/);
  for (const [mutate, reason] of [
    [(value) => { value.chromeStyles = { title: { fontFamily: "Example Sans" } }; }, /CUSTOM_FONT/],
    [(value) => { value.className = "browser-only"; }, /BROWSER_CSS/],
    [(value) => { value.traces[0].style.fill = { type: "linear" }; }, /GRADIENT/],
  ]) {
    const rejected = new Figure({ width: fixture.viewport[0], height: fixture.viewport[1] });
    rejected.scatter(x, y, fixture.scatter); mutate(rejected);
    assert.throws(() => rejected.toScene(), reason);
  }
});

test("Node public Scene chrome setters snapshot literals and retain Rust validation", () => {
  const style = { background: "#f0f8ff", "--chart-bg": "#f8fafc" };
  const legend = { loc: "lower left", title: "Series", toggle: false, highlight: false };
  const colorbar = {
    domain: [0, 1], stops: [[0, [0, 0, 0, 255]], [1, [255, 255, 255, 255]]],
  };
  const figure = new Figure({ width: 320, height: 240 })
    .setStyle(style)
    .setLegend(legend)
    .setColorbar(colorbar)
    .setAxis("x", { domain: [0, 1], side: "top", tick_values: [0, 0.5, 1] })
    .setAxis("y", { domain: [0, 1], side: "right", minor_tick_values: [0.25, 0.75] });
  style.background = "not a color"; legend.loc = "best"; colorbar.domain[0] = 2;
  figure.scatter([0.25], [0.5], { name: "one", style: { symbol: "circle" } });
  assert.doesNotThrow(() => figure.toScene());
  assert.throws(() => figure.setColorbar({ domain: [0, 1], stops: [] }).toScene(), /UNSUPPORTED_COLORBAR/);
  figure.setColorbar({
    domain: [0, 1], stops: [[0, [0, 0, 0, 255]], [1, [255, 255, 255, 255]]],
  });
  assert.doesNotThrow(() => figure.setLegend({ loc: "best" }).toScene());
  for (const [call, value] of [[() => figure.setStyle([]), /Scene style must be an object/], [() => figure.setLegend(null), /Scene legend must be an object/], [() => figure.setAxis("x", []), /Scene x axis options must be an object/]]) {
    assert.throws(call, value);
  }
});

test("Node Scene v25 wrapped annotations reject host layout features", () => {
  for (const [field, value, reason] of [
    ["class_name", "browser-only", /BROWSER_CSS|class behavior/],
    ["style", { font_family: "Example Sans" }, /custom fonts/],
    ["style", { markup: "<b>rich<\\/b>" }, /markup/],
    ["style", { collision: "avoid" }, /collision/],
  ]) {
    const figure = new Figure({ width: 320, height: 240 });
    figure.setAxisDomain("x", [0, 1]); figure.setAxisDomain("y", [0, 1]);
    figure.annotations = [{ kind: "callout", x: 0.5, y: 0.5, text: "wrapped annotation", wrap: 96 }];
    figure.annotations[0][field] = value;
    assert.throws(() => figure.toScene(), reason);
  }
});

test("Node Scene v9 rejects non-byte chrome style input before the ABI", () => {
  const input = {
    viewport: [100, 80], margins: [10, 10, 10, 10],
    xAxis: { id: 1, domain: [0, 1] }, yAxis: { id: 2, domain: [0, 1] },
    kinds: [], stableIds: [], styleRefs: [], styles: [], diameter: [], symbols: [],
    x0: [], y0: [], x1: [], y1: [],
  };
  assert.throws(
    () => sceneBatchEncode({ ...input, chromeStyle: Array(200).fill(256) }),
    /chromeStyle values must be integers from 0 through 255/,
  );
  assert.throws(
    () => sceneBatchEncode({ ...input, title: "x".repeat(4097) }),
    /4096 UTF-8 bytes/,
  );
  assert.throws(() => sceneBatchEncode({ ...input, xFormat: "x".repeat(257) }), /256 UTF-8 bytes/);
  assert.throws(() => sceneBatchEncode({ ...input, yFormat: "$.1f\0USD" }), /NUL-free/);
  assert.doesNotThrow(() => sceneBatchEncode({ ...input, xFormat: "not-a-format" }));
});

test("Node Scene v4 rejects malformed batches", () => {
  const base = {
    viewport: [100, 80], margins: [10, 10, 10, 10],
    xAxis: { id: 1, domain: [0, 1] }, yAxis: { id: 2, domain: [0, 1] },
    kinds: [0], stableIds: [1], styleRefs: [0], x0: [0.5], y0: [0.5], x1: [0.5], y1: [0.5],
    styles: [{ fillRgba: [0, 0, 0, 255], strokeRgba: [0, 0, 0, 255], strokeWidth: 1 }],
    diameter: [8], symbols: [0],
  };
  assert.throws(() => sceneBatchEncode({ ...base, stableIds: [] }), /stableIds must have length 1/);
  assert.throws(() => sceneBatchEncode({ ...base, kinds: [9] }), /invalid canonical scene batch/);
  assert.throws(() => sceneBatchEncode({ ...base, styleRefs: [1] }), /invalid canonical scene batch/);
  assert.throws(() => sceneBatchEncode({ ...base, margins: [60, 40, 10, 10] }), /invalid canonical scene batch/);
  assert.throws(() => sceneBatchEncode({ ...base, expansionModes: [] }), /expansionModes must have length 1/);
  assert.throws(() => sceneBatchEncode({ ...base, expansionModes: [9] }), /expansionModes values must be integers from 0 through 8/);
  assert.throws(() => sceneBatchEncode({ ...base, expansionModes: [1] }), /invalid canonical scene batch/);

  const line = {
    ...base,
    kinds: [1, 1], stableIds: [2, 2], styleRefs: [0, 0],
    diameter: [0, 0], symbols: [0, 0], x0: [0, 1], y0: [0, 1], x1: [0, 0], y1: [0, 0],
  };
  assert.throws(() => sceneBatchEncode({ ...line, styles: [base.styles[0], base.styles[0]], styleRefs: [0, 1], expansionModes: [1, 1] }), /invalid canonical scene batch/);
  assert.throws(() => sceneBatchEncode({ ...line, x0: [0, Number.NaN], expansionModes: [2, 2] }), /invalid canonical scene batch/);
  assert.throws(() => sceneBatchEncode({ ...line, x1: [1, 0], expansionModes: [1, 1] }), /invalid canonical scene batch/);
  assert.throws(() => sceneBatchEncode({ ...line, y1: [0, 1], expansionModes: [1, 1] }), /invalid canonical scene batch/);

  const ribbon = {
    ...base,
    kinds: [3, 3], stableIds: [7, 7], styleRefs: [0, 0],
    diameter: [0, 0], symbols: [2, 2], x0: [0, 0], y0: [0.8, 0.2], x1: [1, 1], y1: [0.9, 0.3],
    expansionModes: [4, 4],
  };
  assert.equal(new DataView(sceneBatchEncode(ribbon).buffer).getBigUint64(16, true), 97n);
  assert.throws(() => sceneBatchEncode({ ...ribbon, stableIds: [7, 8] }), /invalid canonical scene batch/);
  assert.throws(() => sceneBatchEncode({ ...ribbon, symbols: [2, 1] }), /invalid canonical scene batch/);
  assert.throws(() => sceneBatchEncode({ ...ribbon, x0: [0, 0.1] }), /invalid canonical scene batch/);
  assert.throws(() => sceneBatchEncode({ ...ribbon, x1: [1, 0.9] }), /invalid canonical scene batch/);
});

test("Node Scene v4 validates unsigned fields before typed-array coercion", () => {
  const base = {
    viewport: [100, 80], margins: [10, 10, 10, 10],
    xAxis: { id: (1n << 64n) - 1n, domain: [0, 1] }, yAxis: { id: (1n << 64n) - 1n, domain: [0, 1] },
    kinds: [0], stableIds: [(1n << 64n) - 1n], styleRefs: [0],
    styles: [{ fillRgba: [0, 255, 0, 255], strokeRgba: [255, 0, 255, 0], strokeWidth: 0 }],
    diameter: [8], symbols: [0], x0: [0.5], y0: [0.5], x1: [0], y1: [0],
  };
  assert.ok(sceneBatchEncode(base).length > 0);
  for (const kinds of [[-1], [256], [1.5]]) {
    assert.throws(() => sceneBatchEncode({ ...base, kinds }), /kinds values must be integers from 0 through 255/);
  }
  for (const symbols of [[-1], [256], [1.5]]) {
    assert.throws(() => sceneBatchEncode({ ...base, symbols }), /symbols values must be integers from 0 through 255/);
  }
  for (const styleRefs of [[-1], [2 ** 32], [0.5]]) {
    assert.throws(() => sceneBatchEncode({ ...base, styleRefs }), /styleRefs values must be integers/);
  }
  for (const stableIds of [[-1], [-1n], [2 ** 53], [2n ** 64n], [1.5]]) {
    assert.throws(() => sceneBatchEncode({ ...base, stableIds }), /stableIds/);
  }
  for (const id of [-1, -1n, 2 ** 53, 2n ** 64n, 1.5]) {
    assert.throws(() => sceneBatchEncode({ ...base, xAxis: { ...base.xAxis, id } }), /xAxis.id/);
    assert.throws(() => sceneBatchEncode({ ...base, yAxis: { ...base.yAxis, id } }), /yAxis.id/);
  }
  for (const channel of [-1, 256, 1.5]) {
    const styles = [{ ...base.styles[0], fillRgba: [channel, 0, 0, 255] }];
    assert.throws(() => sceneBatchEncode({ ...base, styles }), /fillRgba values must be integers from 0 through 255/);
  }
});

test("Node Scene v4 log mask ignores reserved coordinates and breaks line runs", () => {
  const encoded = sceneBatchEncode({
    viewport: [100, 100], margins: [10, 10, 10, 10],
    xAxis: { id: 1, kind: "log", domain: [1, 10], nonpositive: "mask" },
    yAxis: { id: 2, kind: "log", domain: [1, 10], nonpositive: "mask" },
    kinds: [0, 1, 1, 1, 2, 2], stableIds: [1, 20, 20, 20, 30, 31], styleRefs: [0, 0, 0, 0, 0, 0],
    styles: [{ fillRgba: [0, 0, 0, 255], strokeRgba: [0, 0, 0, 255], strokeWidth: 0 }],
    diameter: [6, 0, 0, 0, 0, 0], symbols: [0, 0, 0, 0, 0, 0],
    x0: [2, 2, 0, 4, 2, 2], y0: [2, 2, 2, 2, 2, 2],
    x1: [0, 0, 0, 0, 8, 0], y1: [0, 0, 0, 0, 8, 8],
  });
  const records = 176;
  assert.deepEqual(Array.from({ length: 6 }, (_, index) => encoded[records + index * 56 + 1]), [1, 1, 0, 1, 1, 0]);
  assert.deepEqual(Array.from(encoded.slice(records + 32, records + 48)), Array(16).fill(0));
  assert.deepEqual(Array.from(encoded.slice(records + 88, records + 104)), Array(16).fill(0));
});

test("Node consumes canonical linear, log, and symlog scale records", () => {
  assert.deepEqual(Array.from(scaleMap({ values: [0, 5, 10], domain: [0, 10], range: [20, 120] })), [20, 70, 120]);
  assert.deepEqual(Array.from(scaleMap({ values: [0.1, 1, 100], kind: "log", domain: [0.1, 100], range: [0, 300] })), [0, 100, 300]);
  const coordinates = scaleMap({ values: [-4, 0, 4], kind: "symlog", operation: "coord", domain: [-10, 10], constant: 2 });
  const roundTrip = scaleMap({ values: coordinates, kind: "symlog", operation: "value", domain: [-10, 10], constant: 2 });
  assert.ok(roundTrip.every((value, index) => Math.abs(value - [-4, 0, 4][index]) < 1e-12));
  assert.ok(Number.isNaN(scaleMap({ values: [0], kind: "log", operation: "coord", domain: [0.1, 10], nonpositive: "mask" })[0]));
});

test("Node rejects malformed canonical scale options before the ABI call", () => {
  assert.throws(
    () => scaleMap({ values: [1], kind: "log", domain: [0.1, 10], nonpositive: "drop" }),
    /nonpositive must be clip or mask/,
  );
});

test("Node consumes Rust-owned canonical axis ticks", () => {
  assert.deepEqual(axisTicks({ kind: "linear", lo: -0.9, hi: 5.1, target: 6 }), {
    ticks: [0, 1, 2, 3, 4, 5], labeled: [0, 1, 2, 3, 4, 5], step: 1,
  });
  assert.deepEqual(axisTicks({ kind: "log", lo: 0.1, hi: 100, target: 6 }).labeled, [0.1, 1, 10, 100]);
  assert.deepEqual(
    axisTicks({ kind: "category", lo: -0.5, hi: 9.5, target: 5, categories: new Array(10) }),
    { ticks: [0, 2, 4, 6, 8], labeled: [0, 2, 4, 6, 8], step: 2 },
  );
  assert.deepEqual(
    axisTicks({ kind: "angular", lo: 0, hi: 360, target: 8, unit: "degrees" }).ticks,
    [0, 45, 90, 135, 180, 225, 270, 315],
  );
  const hour = 3_600_000;
  assert.deepEqual(
    axisTicks({ kind: "time", lo: 0, hi: 3 * hour, target: 6 }),
    {
      ticks: [0, 0.5 * hour, hour, 1.5 * hour, 2 * hour, 2.5 * hour, 3 * hour],
      labeled: [0, 0.5 * hour, hour, 1.5 * hour, 2 * hour, 2.5 * hour, 3 * hour],
      step: 0.5 * hour,
    },
  );
  const day = 86_400_000;
  const lo = Date.UTC(2020, 0, 1);
  const hi = Date.UTC(2022, 0, 1);
  const calendar = axisTicks({ kind: "time", lo, hi, target: 6 });
  assert.equal(calendar.step, 6 * 30 * day);
  assert.deepEqual(calendar.ticks, [
    lo,
    Date.UTC(2020, 6, 1),
    Date.UTC(2021, 0, 1),
    Date.UTC(2021, 6, 1),
    hi,
  ]);
});

test("Node consumes Rust-owned tick-label collision layout", () => {
  const labels = Array.from({ length: 9 }, (_, i) => `Category_Name_${String(i).padStart(2, "0")}`);
  const positions = Array.from({ length: 9 }, (_, i) => 100 + i * 90);
  const kept = tickLabelLayout({
    positions, labels, kind: "rotate", side: "bottom", anchor: "end",
    isX: true, category: true, fontSize: 11, minGap: 8, explicitAngle: -30,
  });
  assert.equal(kept.length, 9);
  assert.equal(kept[0].angle, -30);
  assert.deepEqual(kept.map((item) => item.index), [0, 1, 2, 3, 4, 5, 6, 7, 8]);
  const centered = tickLabelLayout({
    positions, labels, kind: "rotate", side: "bottom", anchor: "center",
    isX: true, category: true, fontSize: 11, minGap: 8, explicitAngle: -30,
  });
  assert.ok(centered.length > 0 && centered.length < 9);
  assert.deepEqual(tickLabelLayout({ positions: [0, 10], labels: ["a", "b"], kind: "none" }), []);
});

test("Node consumes Rust-owned authored tick-window filter", () => {
  assert.deepEqual(
    tickWindow({ rangeLo: 0, rangeHi: 360, thetaUnit: "degrees", sectorLo: 300, sectorHi: 420 }),
    [300, 420],
  );
  assert.deepEqual(
    tickWindowFilter({
      values: [300, 330, 0, 30, 60, 200],
      lo: 300,
      hi: 420,
      thetaUnit: "degrees",
    }),
    [300, 330, 0, 30, 60],
  );
  assert.deepEqual(
    tickWindowFilter({
      values: [0, 45, 90, 200, -10, Number.NaN],
      lo: 0,
      hi: 180,
    }),
    [0, 45, 90],
  );
  assert.deepEqual(
    tickWindow({ rangeLo: 1, rangeHi: 2, thetaUnit: "degrees", kind: "category", nCategories: 4 }),
    [0, 3],
  );
});

test("Node consumes Rust-owned static legend box packing", () => {
  const plot = { x: 0, y: 0, w: 560, h: 400 };
  const titled = legendBoxLayout({
    plot, names: ["1", "2", "3", "4"], title: "Classes", loc: "lower left",
  });
  assert.equal(titled.visibleCount, 4);
  assert.ok(String(titled.title).startsWith("Clas"), `title was ${titled.title}`);
  assert.ok(titled.boxW > 0 && titled.boxH > 0);
  const wide = legendBoxLayout({
    plot, names: ["alpha", "beta", "gamma"], title: "Classes", loc: "lower left",
  });
  assert.equal(wide.title, "Classes");
  const narrow = legendBoxLayout({
    plot: { x: 0, y: 0, w: 150, h: 400 },
    names: ["Wmmmmmmmmmmmmmmmmmmmm", "iiiiiiiiiiiiiiiiiiii"],
    loc: "upper right",
  });
  assert.ok(narrow.names.some((name) => name.endsWith("...")));
});

test("Node consumes Rust-owned text-block measure and axis rooms", () => {
  const crlf = textBlockMeasure("first\r\nsecond", 12);
  const lf = textBlockMeasure("first\nsecond", 12);
  assert.deepEqual(crlf.lines, ["first", "second"]);
  assert.deepEqual(lf.lines, crlf.lines);
  assert.equal(crlf.lineCount, 2);
  const rotated = textBlockRotatedExtent(10, 4, 90);
  assert.ok(Math.abs(rotated[0] - 4) < 1e-12);
  assert.ok(Math.abs(rotated[1] - 10) < 1e-12);
  const titled = yAxisLeftRoom(7, 23, "Y", 12, 12 * 0.4);
  const untitled = yAxisLeftRoom(0, 0, "", 12, 0);
  assert.ok(titled > 23);
  assert.equal(untitled, 0);
});

test("Node consumes Rust-owned static-export layout combination", () => {
  assert.equal(compatIsCompact(519), true);
  assert.equal(compatIsCompact(520), false);
  assert.deepEqual(compatDefaultPadding(true), [6, 8, 36, 46]);
  assert.deepEqual(compatDefaultPadding(false), [10, 14, 42, 62]);
  assert.equal(compatTitleWrapWidth(100, 40, 40), 40);
  assert.deepEqual(compatColorbarExtra("figure_vertical", false, false), [86, 0]);
  assert.equal(polarLegendRoom(400), 120);
  assert.equal(polarLegendRoom(1000), 200);
  assert.equal(polarLabelRoom(null), 30);
  const recut = recutPolarPlot(
    { x: 0, y: 0, w: 200, h: 200, topAxisRoom: 10 },
    200,
    200,
    { polarLabelRoom: 30, authoredPadding: true },
  );
  assert.equal(recut.x, 30);
  assert.equal(recut.y, 30);
  assert.equal(recut.w, 140);
  assert.equal(recut.h, 140);
  assert.equal(recut.topAxisRoom, 40);
});

test("Node consumes Rust-owned pyplot tight-layout solve", () => {
  const empty = tightLayoutSolve({
    canvasW: 800, canvasH: 600, nrows: 1, ncols: 1, compact: false, panels: [],
  });
  assert.ok(Math.abs(empty.left - 62 / 800) < 1e-12);
  assert.ok(Math.abs(empty.right - (1 - 26 / 800)) < 1e-12);
});

test("Node matches every Rust-owned axis tick family in the shared cross-host fixture", () => {
  assert.equal(axisTickFixture.schema, "xyg-axis-ticks-v1");
  for (const value of axisTickFixture.cases) {
    const args = { kind: value.kind, lo: value.lo, hi: value.hi, target: value.target };
    if (value.categories !== undefined) args.categories = new Array(value.categories);
    if (value.unit !== undefined) args.unit = value.unit;
    if (value.constant !== undefined) args.constant = value.constant;
    const actual = axisTicks(args);
    if (value.tolerance === undefined) {
      assert.deepEqual(actual, value.expected, value.name);
      continue;
    }
    for (const field of ["ticks", "labeled"]) {
      assert.equal(actual[field].length, value.expected[field].length, value.name);
      actual[field].forEach((item, index) => {
        const expected = value.expected[field][index];
        assert.ok(
          Math.abs(item - expected) <= value.tolerance * Math.max(1, Math.abs(expected)),
          `${value.name}: ${field}[${index}]`,
        );
      });
    }
    assert.ok(
      Math.abs(actual.step - value.expected.step) <= value.tolerance * Math.max(1, Math.abs(value.expected.step)),
      `${value.name}: step`,
    );
  }
});

test("Node symlog ticks fail closed at invalid arguments and honor the 200 target ceiling", () => {
  for (const args of [
    { lo: -1, hi: 1, target: 0, constant: 1 },
    { lo: -1, hi: 1, target: 201, constant: 1 },
    { lo: -1, hi: 1, target: 6, constant: 0 },
    { lo: -1, hi: 1, target: 6, constant: -1 },
    { lo: -1, hi: 1, target: 6, constant: Number.NaN },
    { lo: -1, hi: 1, target: 6, constant: Number.POSITIVE_INFINITY },
    { lo: Number.NaN, hi: 1, target: 6, constant: 1 },
    { lo: -1, hi: Number.POSITIVE_INFINITY, target: 6, constant: 1 },
  ]) {
    assert.throws(() => axisTicks({ kind: "symlog", ...args }), /invalid canonical axis tick request/);
  }
  const boundary = axisTicks({ kind: "symlog", lo: -1e12, hi: 1e12, target: 200, constant: 1 });
  assert.ok(boundary.ticks.length > 0 && boundary.ticks.length <= 200);
  assert.deepEqual(boundary.ticks, boundary.labeled);
  assert.ok(boundary.step > 0);
});

test("Node consumes the versioned Rust scatter scene", () => {
  assert.equal(sceneVersion(), 25);
  assert.equal(
    scatterSceneSvg({
      x: [10, 20],
      y: [11, 21],
      diameter: [8, 10],
      fillRgba: [37, 99, 235, 255, 239, 68, 68, 128],
      strokeRgba: [0, 0, 0, 255, 17, 24, 39, 64],
      strokeWidth: [2, 0],
      symbols: [0, 15],
    }),
    '<g><circle cx="10" cy="11" r="3" fill="rgb(37,99,235)" stroke="rgb(0,0,0)" stroke-width="2"/><path d="M 15.5 21 H 24.5 M 20 16.5 V 25.5" fill="none" stroke="rgb(17,24,39)" stroke-opacity="0.25" stroke-width="1"/></g>',
  );
});

test("Node rejects malformed scene array lengths before the ABI call", () => {
  assert.throws(
    () => scatterSceneSvg({
      x: [1], y: [], diameter: [4], fillRgba: [0, 0, 0, 255],
      strokeRgba: [0, 0, 0, 0], strokeWidth: [0], symbols: [0],
    }),
    /y must have length 1/,
  );
});

test("Node maps Rust scene validation failures to a stable host error", () => {
  assert.throws(
    () => scatterSceneSvg({
      x: [Number.NaN], y: [1], diameter: [4], fillRgba: [0, 0, 0, 255],
      strokeRgba: [0, 0, 0, 0], strokeWidth: [0], symbols: [0],
    }),
    /invalid canonical scatter scene/,
  );
});

test("Node Scene compiles column and histogram as Rect records", () => {
  const column = new Figure({ width: 240, height: 160 });
  column.setAxisDomain("x", [0, 4]);
  column.setAxisDomain("y", [0, 5]);
  column.bar([1, 2], [3, 2], { kind: "column", color: "#22c55e", opacity: 0.85, name: null });
  const columnScene = column.toScene();
  assert.equal(new DataView(columnScene.buffer, columnScene.byteOffset).getUint32(4, true), 25);
  assert.match(sceneSvg(columnScene), /<rect /);

  const hist = new Figure({ width: 240, height: 160 });
  hist.setAxisDomain("x", [0, 4]);
  hist.setAxisDomain("y", [0, 5]);
  hist.histogram([1, 1.5, 2, 2.5, 3], { bins: 4, range: [0, 4], color: "#22c55e", name: null });
  assert.match(sceneSvg(hist.toScene()), /<rect /);
});

test("Node Scene rejects corner_radius and density-tier scatter", () => {
  const rounded = new Figure({ width: 200, height: 120 });
  rounded.bar([0, 1], [1, 2], { style: { corner_radius: 4 }, name: null });
  assert.throws(() => rounded.toScene(), /corner_radius/);

  const density = new Figure({ width: 200, height: 120 });
  density.scatter(new Float64Array(200_000), new Float64Array(200_000), {
    forceDensity: true,
    name: null,
  });
  assert.throws(() => density.toScene(), /density-tier/);
});

test("Node Scene rejects hidden traces and unknown kinds", () => {
  const hidden = new Figure({ width: 200, height: 120 });
  hidden.line([0, 1], [0, 1], { name: null });
  hidden.traces[0].hidden = true;
  assert.throws(() => hidden.toScene(), /hidden or per-item/);

  const unknown = new Figure({ width: 200, height: 120 });
  unknown.line([0, 1], [0, 1], { name: null });
  unknown.traces[0].kind = "text";
  assert.throws(() => unknown.toScene(), /does not yet support text/);
});

test("Node Scene rejects missing or unequal rectangle columns", () => {
  const missing = new Figure({ width: 200, height: 120 });
  missing.traces.push({
    id: 1,
    kind: "column",
    name: null,
    x0: new Float64Array([0, 1]),
    y0: new Float64Array([0, 0]),
    x1: null,
    y1: new Float64Array([1, 2]),
    style: { color: "#22c55e" },
    x_axis: "x",
    y_axis: "y",
  });
  assert.throws(() => missing.toScene(), /four rectangle columns/);

  const unequal = new Figure({ width: 200, height: 120 });
  unequal.traces.push({
    id: 1,
    kind: "histogram",
    name: null,
    x0: new Float64Array([0, 1]),
    y0: new Float64Array([0, 0]),
    x1: new Float64Array([0.5]),
    y1: new Float64Array([1, 2]),
    style: { color: "#22c55e" },
    x_axis: "x",
    y_axis: "y",
  });
  assert.throws(() => unequal.toScene(), /equal length/);
});

test("Node Scene compiles segments, step lines, and stem", () => {
  const segments = new Figure({ width: 240, height: 160 });
  segments.setAxisDomain("x", [0, 2]);
  segments.setAxisDomain("y", [0, 2]);
  segments.segments([0, 1], [0, 0], [1, 2], [1, 1], { color: "#ef4444", name: null });
  const segmentSvg = sceneSvg(segments.toScene());
  assert.equal((segmentSvg.match(/<polyline /g) ?? []).length, 2);

  const stepped = new Figure({ width: 240, height: 160 });
  stepped.setAxisDomain("x", [0, 2]);
  stepped.setAxisDomain("y", [0, 3]);
  stepped.step([0, 1, 2], [1, 2, 1], { step: "post", color: "#3987e5", name: null });
  assert.equal((sceneSvg(stepped.toScene()).match(/<polyline /g) ?? []).length, 1);

  const stem = new Figure({ width: 240, height: 160 });
  stem.setAxisDomain("x", [-0.5, 1.5]);
  stem.setAxisDomain("y", [0, 3]);
  stem.stem([0, 1], [1, 2], { color: "#22c55e", name: null });
  const stemSvg = sceneSvg(stem.toScene());
  assert.equal((stemSvg.match(/<polyline /g) ?? []).length, 2);
});

test("Node area matches Python Scene v25 Band outline bytes and consumers", () => {
  for (const [mode, options, symbol] of [
    ["top", {}, 1],
    ["perimeter", { strokePerimeter: true }, 2],
    ["none", { lineWidth: 0 }, 0],
  ]) {
    const figure = new Figure({ width: 240, height: 160 });
    figure.setAxisDomain("x", [0, 2]); figure.setAxisDomain("y", [0, 3]);
    figure.area([0, 1, 2], [1, 2, 1.5], {
      base: 0, id: 7, color: "#3987e5", opacity: 0.5,
      lineColor: "#112233", lineWidth: options.lineWidth ?? 2,
      lineOpacity: 0.4, strokePerimeter: options.strokePerimeter ?? false,
      style: { fill_opacity: 0.8, stroke_opacity: 0.5 },
    });
    const scene = figure.toScene();
    const expected = figureSceneFixture.band_outlines[mode];
    assert.deepEqual(scene, Uint8Array.from(Buffer.from(expected.scene_base64, "base64")));
    assert.equal(crypto.createHash("sha256").update(scene).digest("hex"), expected.sha256);
    assert.deepEqual(scene.slice(160, 168), Uint8Array.of(57, 135, 229, 102, 17, 34, 51, 26));
    assert.equal(scene[178], symbol);
    const svg = sceneSvg(scene);
    assert.equal((svg.match(/<path d="/g) ?? []).length, mode === "top" ? 2 : 1);
    assert.equal(svg.includes('fill="none"'), mode === "top");
    assert.equal(svg.includes('stroke="none"'), mode !== "perimeter");
    assert.ok(sceneRasterCommands(scene).byteLength > 0);
    assert.equal(sceneBrowserPainter(scene)[301], symbol);
  }

  const band = new Figure({ width: 240, height: 160 });
  band.setAxisDomain("x", [0, 2]); band.setAxisDomain("y", [0, 3]);
  band.errorBand([0, 1, 2], [0.7, 1.2, 0.9], [1.3, 1.8, 1.5], { id: 7 });
  assert.equal(band.toScene()[178], 0);

  const inherited = new Figure({ width: 240, height: 160 });
  inherited.setAxisDomain("x", [0, 2]); inherited.setAxisDomain("y", [0, 3]);
  inherited.area([0, 1, 2], [1, 2, 1.5], { style: { color: "#aabbcc" } });
  assert.deepEqual(inherited.toScene().slice(160, 167), Uint8Array.of(170, 187, 204, 89, 170, 187, 204));

  const invalid = new Figure({ width: 240, height: 160 });
  invalid.setAxisDomain("x", [0, 1]); invalid.setAxisDomain("y", [0, 1]);
  invalid.area([0, 1], [0.25, 0.75]);
  for (const invalidValue of ["true", 1, null]) {
    invalid.traces[0].style.stroke_perimeter = invalidValue;
    assert.throws(() => invalid.toScene(), /stroke_perimeter must be a boolean/);
  }
});

test("Node frames literal v23 borders for text, attached, and callout label boxes", () => {
  const figure = new Figure({ width: 320, height: 240 });
  figure.setAxisDomain("x", [0, 1]); figure.setAxisDomain("y", [0, 1]);
  const style = { color: "#667085", label_background: "#ffffff", label_border_color: "#123456", label_border_width: 1.5 };
  figure.annotations = [
    { kind: "text", x: 0.2, y: 0.2, text: "text", style },
    { kind: "marker", x: 0.5, y: 0.5, text: "attached", size: 8, style },
    { kind: "callout", x: 0.75, y: 0.75, dx: -20, dy: -20, text: "callout", style },
  ];
  const scene = figure.toScene();
  const svg = sceneSvg(scene);
  assert.match(svg, /annotation_label_box[^>]*stroke="rgba\(18,52,86,1\.000000\)"/);
  assert.match(svg, /stroke-width="1\.5"/);
  assert.ok(sceneRasterCommands(scene).byteLength > 0);
  const painter = sceneBrowserPainter(scene);
  assert.ok(new TextDecoder().decode(painter).includes("XYLB\x04"));
  const invalid = new Figure(); invalid.annotations = [{ kind: "text", x: 0.5, y: 0.5, text: "bad", style: { color: "#667085", label_border_color: "#000" } }];
  assert.throws(() => invalid.toScene(), /requires color and width/);
});
