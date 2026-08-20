import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import test from "node:test";

import { axisTicks, scaleMap, scatterSceneSvg, sceneBatchEncode, sceneVersion } from "../src/index.js";
import { Figure, sceneRasterCommands, sceneSvg } from "../src/index.js";

const sceneFixture = JSON.parse(fs.readFileSync(new URL("../../../tests/fixtures/scene_v3.json", import.meta.url), "utf8"));
const figureSceneFixture = JSON.parse(fs.readFileSync(new URL("../../../tests/fixtures/figure_scene_v3.json", import.meta.url), "utf8"));

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

test("Node figure defaults match Python Scene bytes and canonical values", () => {
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

test("Node Scene v4 whole-scene consumers reject malformed and unsupported input", () => {
  assert.throws(() => sceneSvg(Uint8Array.of(1, 2, 3)), /invalid canonical scene/);
  const figure = new Figure().area([0, 1], [1, 2]);
  assert.throws(() => figure.toScene(), /does not yet support area/);
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
    assert.throws(() => figure.toScene(), new RegExp(key));
  }
  const named = new Figure();
  named.scatter([1], [1], { _composed: true, name: "series" });
  assert.throws(() => named.toScene(), /legends/);
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
  assert.equal(Buffer.from(encoded).toString("hex"), sceneFixture.expected_hex);
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

test("Node consumes the versioned Rust scatter scene", () => {
  assert.equal(sceneVersion(), 5);
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
