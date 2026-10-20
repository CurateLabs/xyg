import assert from "node:assert/strict";
import test from "node:test";

import { Figure, sceneExportSupportReason } from "../src/index.js";

// Native secondary right-hand y axis (`y2`, twinx; #1006). Rust owns admission,
// layout and painting; the Node host marshals the y2 facts and the per-trace
// selector and surfaces Rust's stable reasons. Byte identity with Python lives
// in tests/test_static_dual_axis_cross_host.py.

const WIDTH = 480;
const HEIGHT = 320;

function dual({ y2Side = "right", y2 = {}, y = {} } = {}) {
  const figure = new Figure({ width: WIDTH, height: HEIGHT });
  figure.setAxis("x", { domain: [0, 4] });
  figure.setAxis("y", { domain: [0, 4], label: "L", ...y });
  figure.setAxis("y2", { side: y2Side, label: "R", domain: [0, 400], ...y2 });
  figure.line([1, 2, 3], [1, 2, 3]);
  figure.line([1, 2, 3], [100, 200, 300], { yAxis: "y2" });
  figure.traces.forEach((trace, index) => { trace.id = index; });
  return figure;
}

const texts = (svg) => [...svg.matchAll(/<text([^>]*)>([^<]*)<\/text>/g)].map(([, attrs, body]) => ({
  attrs: Object.fromEntries([...attrs.matchAll(/([\w-]+)="([^"]*)"/g)].map(([, k, v]) => [k, v])),
  body,
}));

test("y2 marks use the secondary scale", () => {
  const svg = Buffer.from(dual().toSvg()).toString("utf8");
  const ys = [...svg.matchAll(/<polyline points="([^"]*)"/g)]
    .map(([, points]) => points.trim().split(/\s+/).map((pair) => Number(pair.split(",")[1])));
  assert.equal(ys.length, 2);
  assert.deepEqual(ys[1], ys[0]);
});

test("right gutter holds the y2 labels and title inside the canvas", () => {
  const svg = Buffer.from(dual().toSvg()).toString("utf8");
  const items = texts(svg);
  const right = items.filter(({ attrs }) => attrs["text-anchor"] === "start");
  assert.deepEqual(right.map(({ body }) => body), ["0", "100", "200", "300", "400"]);
  const plot = /data-xy-chrome="plot-background" x="([\d.]+)" y="[\d.]+" width="([\d.]+)"/.exec(svg);
  const plotRight = Number(plot[1]) + Number(plot[2]);
  assert.ok(right.every(({ attrs }) => Number(attrs.x) > plotRight));
  assert.ok(items.every(({ attrs }) => Number(attrs.x) < WIDTH));
  const title = items.find(({ body }) => body === "R");
  assert.ok(Number(title.attrs.x) > Math.max(...right.map(({ attrs }) => Number(attrs.x))));
});

test("y2 chrome style reaches the right axis only", () => {
  const svg = Buffer.from(dual({
    y2: { style: { label_color: "#d62728", tick_label_color: "#2ca02c", tick_label_size: 20, tick_padding: 12 } },
  }).toSvg()).toString("utf8");
  const items = texts(svg);
  assert.equal(items.find(({ body }) => body === "R").attrs.fill, "rgba(214,39,40,1.000000)");
  const right = items.filter(({ attrs }) => attrs["text-anchor"] === "start");
  assert.deepEqual(new Set(right.map(({ attrs }) => attrs["font-size"])), new Set(["20"]));
  assert.deepEqual(new Set(right.map(({ attrs }) => attrs.fill)), new Set(["rgba(44,160,44,1.000000)"]));
});

test("every static format exports", () => {
  const figure = dual();
  assert.equal(Buffer.from(figure.toPng()).subarray(1, 4).toString(), "PNG");
  assert.equal(Buffer.from(figure.toPdf()).subarray(0, 4).toString(), "%PDF");
});

test("Rust rejects unsupported secondary axes with stable reasons", () => {
  assert.match(sceneExportSupportReason(dual({ y2Side: "left" })), /^XYG_SCENE_UNSUPPORTED_Y2_SIDE:/);

  const x2 = new Figure({ width: WIDTH, height: HEIGHT });
  x2.setAxis("x", { domain: [0, 4] });
  x2.setAxis("y", { domain: [0, 4] });
  x2.axis_options.x2 = { side: "top" };
  x2.line([1, 2, 3], [1, 2, 3]);
  assert.match(sceneExportSupportReason(x2), /^XYG_SCENE_UNSUPPORTED_X2:/);

  const colorbar = dual();
  colorbar.colorbar_options = { title: "c" };
  assert.match(sceneExportSupportReason(colorbar), /^XYG_SCENE_UNSUPPORTED_Y2_COLORBAR:/);

  const polar = dual();
  polar.coords = "polar";
  assert.match(sceneExportSupportReason(polar), /^XYG_SCENE_UNSUPPORTED_Y2_POLAR:/);

  const tickOnly = new Figure({ width: WIDTH, height: HEIGHT });
  tickOnly.setAxis("x", { domain: [0, 4] });
  tickOnly.setAxis("y", { domain: [0, 4] });
  tickOnly.setAxis("y2", { side: "right", domain: [0, 400] });
  tickOnly.line([1, 2, 3], [1, 2, 3]);
  assert.match(sceneExportSupportReason(tickOnly), /^XYG_SCENE_UNSUPPORTED_Y2_TICK_ONLY:/);
});

test("charts without y2 carry no y2 block", () => {
  const plain = new Figure({ width: WIDTH, height: HEIGHT });
  plain.setAxis("x", { domain: [0, 4] });
  plain.setAxis("y", { domain: [0, 4] });
  plain.line([1, 2, 3], [1, 2, 3]);
  assert.equal(Buffer.from(plain.toScene()).includes("XYY2"), false);
  assert.equal(Buffer.from(dual().toScene()).includes("XYY2"), true);
});

const svgOf = (figure) => Buffer.from(figure.toSvg()).toString("utf8");
const rightLabels = (figure) => texts(svgOf(figure))
  .filter(({ attrs }) => attrs["text-anchor"] === "start" && Number(attrs.x) > 300)
  .map(({ body }) => body);

test("y2 title reads bottom to top like the left title", () => {
  const items = texts(svgOf(dual()));
  const transform = (body) => items.find((item) => item.body === body).attrs.transform.split(" ")[0];
  assert.equal(transform("L"), "rotate(-90");
  assert.equal(transform("R"), "rotate(-90");
});

test("authored y2 tick collision options reach Rust, strategy before collision", () => {
  const every = ["0", "100", "200", "300", "400"];
  assert.deepEqual(rightLabels(dual()), every);
  assert.deepEqual(rightLabels(dual({ y2: { tick_label_min_gap: 200 } })), ["0", "400"]);
  assert.deepEqual(rightLabels(dual({ y2: { tick_label_min_gap: 200, tick_label_strategy: "preserve" } })), every);
  assert.deepEqual(rightLabels(dual({ y2: { tick_label_min_gap: 200, collision: "preserve" } })), every);
  assert.deepEqual(rightLabels(dual({
    y2: { tick_label_min_gap: 200, tick_label_strategy: "preserve", collision: "hide" },
  })), every);
});

test("a symlog y2 uses the authored constant", () => {
  const figure = dual({ y2: { type: "symlog", constant: 2, domain: [-100, 100] } });
  assert.deepEqual(rightLabels(figure), ["-12.78", "0.00", "12.78"]);
});

test("invalid authored y2 values are rejected by Rust, never defaulted", () => {
  const message = (y2) => {
    try { return sceneExportSupportReason(dual({ y2 })); } catch (error) { return error.message; }
  };
  for (const y2 of [
    { type: "symlog", constant: 0 },
    { type: "symlog", constant: -2 },
    { domain: [0, Number.POSITIVE_INFINITY] },
    { tick_label_angle: Number.POSITIVE_INFINITY },
    { tick_label_angle: Number.NEGATIVE_INFINITY },
  ]) {
    assert.equal(message(y2), "invalid canonical scene batch", JSON.stringify(y2));
  }
});

test("a category y2 is rejected with Rust's reason", () => {
  assert.equal(sceneExportSupportReason(dual({ y2: { type: "category" } })), "XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS");
});

test("an authored empty tick list is automatic ticks, for y2 as for y", () => {
  const auto = svgOf(dual());
  assert.equal(svgOf(dual({ y2: { tick_values: [] } })), auto);
  assert.equal(svgOf(dual({ y: { tick_values: [] } })), auto);
  assert.notEqual(svgOf(dual({ y2: { tick_values: [0, 400] } })), auto);
});
