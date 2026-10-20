import assert from "node:assert/strict";
import test from "node:test";

import { Figure } from "../src/index.js";

// Live-wire dual-axis parity (#1006): `buildPayload` must marshal the admitted
// y2 axis, per-trace view ranges, and y2-bound annotation bindings — never
// collapse a y2 trace onto the primary scale. Cross-host byte identity with
// Python lives in tests/test_live_dual_axis_cross_host.py.

function dual({ annotations = [] } = {}) {
  const figure = new Figure({ width: 480, height: 320 });
  figure.setAxis("x", { domain: [0, 4] });
  figure.setAxis("y", { domain: [0, 4], label: "L" });
  figure.setAxis("y2", { side: "right", domain: [0, 400], label: "R" });
  figure.line([1, 2, 3], [1, 2, 3]);
  figure.line([1, 2, 3], [100, 200, 300], { yAxis: "y2" });
  for (const annotation of annotations) figure.annotate(annotation);
  figure.traces.forEach((trace, index) => { trace.id = index; });
  return figure;
}

test("the live payload carries the y2 axis and per-axis view ranges", () => {
  const { spec } = dual().buildPayload();
  assert.deepEqual(Object.keys(spec.axes), ["x", "y", "y2"]);
  assert.equal(spec.axes.y2.side, "right");
  assert.equal(spec.axes.y2.range[0], 0);
  assert.equal(spec.axes.y2.range[1], 400);
  assert.deepEqual(spec.view.ranges, { x: [0, 4], y: [0, 4], y2: [0, 400] });
  assert.deepEqual(
    spec.traces.map((t) => t.y_axis),
    ["y", "y2"],
  );
});

test("an omitted y2 side stays unobserved and the live payload still reports right", () => {
  // Rust owns the omitted-side policy (static chrome pack); the setter must
  // not duplicate it, and the live wire mirrors Rust's resolution.
  const figure = new Figure({ width: 480, height: 320 });
  figure.setAxis("x", { domain: [0, 4] });
  figure.setAxis("y", { domain: [0, 4] });
  figure.setAxis("y2", { domain: [0, 400] });
  assert.equal(figure.axis_options.y2.side, undefined);
  figure.line([1, 2, 3], [1, 2, 3]);
  figure.line([1, 2, 3], [100, 200, 300], { yAxis: "y2" });
  const { spec } = figure.buildPayload();
  assert.equal(spec.axes.y2.side, "right");
  // The static path equals the explicit-right chart (decided by Rust).
  const explicit = new Figure({ width: 480, height: 320 });
  explicit.setAxis("x", { domain: [0, 4] });
  explicit.setAxis("y", { domain: [0, 4] });
  explicit.setAxis("y2", { side: "right", domain: [0, 400] });
  explicit.line([1, 2, 3], [1, 2, 3]);
  explicit.line([1, 2, 3], [100, 200, 300], { yAxis: "y2" });
  assert.equal(Buffer.from(figure.toSvg()).toString(), Buffer.from(explicit.toSvg()).toString());
});

test("a y2 density trace bins against its own domain, not the primary y range", () => {
  const build = (y2Domain) => {
    const figure = new Figure({ width: 120, height: 90 });
    figure.setAxis("x", { domain: [0, 4] });
    figure.setAxis("y", { domain: [0, 4] });
    figure.setAxis("y2", { side: "right", domain: y2Domain });
    figure.scatter([1, 2, 3], [1, 2, 3]);
    figure.scatter([1, 2, 3], [100, 200, 300], { yAxis: "y2", forceDensity: true });
    figure.traces.forEach((trace, index) => { trace.id = index; });
    return figure.buildPayload({ split: true });
  };
  const narrow = build([0, 400]);
  const wide = build([0, 800]);
  // The tier-2 grid is domain-binned: the y2 domain reaches the density entry
  // (and the grid bytes), while the primary trace is untouched.
  assert.equal(narrow.spec.traces[1].density.y_range[1], 400);
  assert.equal(wide.spec.traces[1].density.y_range[1], 800);
  assert.deepEqual(
    narrow.spec.view.ranges.y,
    wide.spec.view.ranges.y,
  );
  const grid = (payload) => {
    const density = payload.spec.traces[1].density;
    const column = payload.spec.columns[density.buf];
    return Buffer.from(payload.buffers[density.buf].buffer ?? payload.buffers[density.buf])
      .subarray(0, column.len * 4);
  };
  assert.notDeepEqual(grid(wide), grid(narrow));
});

test("a y2-bound annotation keeps its binding on the live wire", () => {
  const { spec } = dual({
    annotations: [
      { kind: "text", x: 2, y: 200, text: "secondary", y_axis: "y2", dx: 6, dy: -6, anchor: "start" },
      { kind: "text", x: 2, y: 2, text: "primary", dx: 6, dy: -6, anchor: "start" },
    ],
  }).buildPayload();
  assert.deepEqual(
    spec.annotations.map((a) => [a.text, a.y_axis ?? null]),
    [["secondary", "y2"], ["primary", null]],
  );
});

test("charts without y2 or bindings are unchanged: no y2 axis, no annotation key", () => {
  const figure = new Figure({ width: 480, height: 320 });
  figure.setAxis("x", { domain: [0, 4] });
  figure.setAxis("y", { domain: [0, 4] });
  figure.line([1, 2, 3], [1, 2, 3]);
  figure.annotate({ kind: "text", x: 2, y: 2, text: "primary", dx: 6, dy: -6, anchor: "start" });
  const { spec } = figure.buildPayload();
  assert.deepEqual(Object.keys(spec.axes), ["x", "y"]);
  assert.deepEqual(Object.keys(spec.view.ranges), ["x", "y"]);
  assert.equal("y_axis" in spec.annotations[0], false);
});

test("a y2 binding without a declared y2 axis fails closed with a stable message", () => {
  const missing = new Figure({ width: 480, height: 320 });
  missing.setAxis("x", { domain: [0, 4] });
  missing.setAxis("y", { domain: [0, 4] });
  missing.line([1, 2, 3], [1, 2, 3]);
  missing.annotate({ kind: "text", x: 2, y: 200, text: "secondary", y_axis: "y2" });
  assert.throws(
    () => missing.buildPayload(),
    /y_axis 'y2' has no matching xyg\.y_axis\(id='y2'\)/,
  );

  const badId = new Figure({ width: 480, height: 320 });
  badId.setAxis("x", { domain: [0, 4] });
  badId.setAxis("y", { domain: [0, 4] });
  badId.line([1, 2, 3], [1, 2, 3]);
  badId.annotate({ kind: "text", x: 2, y: 2, text: "x", y_axis: "y3" });
  assert.throws(
    () => badId.buildPayload(),
    /y_axis must be 'y' or 'y2', got "y3"/,
  );
});
