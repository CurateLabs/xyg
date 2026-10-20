#!/usr/bin/env node
/**
 * Emit live Node payload facts for the dual-axis cross-host parity proof —
 * consumed by tests/test_live_dual_axis_cross_host.py.
 *
 * The same public dual-axis chart is built through Python `xyg.line_chart` and
 * here; both hosts must marshal the y2 axis, per-trace view ranges, and
 * y2-bound annotations identically on the live wire (or refuse identically).
 *
 * Usage (from repo root):
 *   node packages/xy-node/scripts/live_dual_axis_cross_host.mjs
 */
import crypto from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const { PROTOCOL_VERSION, Figure } = await import(path.join(root, "packages/xy-node/src/index.js"));

function sha256(buf) {
  return crypto.createHash("sha256").update(Buffer.from(buf)).digest("hex");
}

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

const ANNOTATIONS = [
  { kind: "text", x: 2, y: 200, text: "secondary", y_axis: "y2", dx: 6, dy: -6, anchor: "start" },
  { kind: "text", x: 2, y: 2, text: "primary", dx: 6, dy: -6, anchor: "start" },
];

const figure = dual({ annotations: ANNOTATIONS });
const { spec, buffers } = figure.buildPayload();

// A range-sensitive trace kind: the tier-2 density grid is binned against the
// trace's own y2 domain, so host parity here proves per-trace ranges flow (a
// direct line column is data-relative and would not distinguish them).
function dualDensity() {
  const f = new Figure({ width: 120, height: 90 });
  f.setAxis("x", { domain: [0, 4] });
  f.setAxis("y", { domain: [0, 4] });
  f.setAxis("y2", { side: "right", domain: [0, 400] });
  f.scatter([1, 2, 3], [1, 2, 3]);
  f.scatter([1, 2, 3], [100, 200, 300], { yAxis: "y2", forceDensity: true });
  f.traces.forEach((trace, index) => { trace.id = index; });
  return f.buildPayload({ split: true });
}
const densityPayload = dualDensity();

const plain = new Figure({ width: 480, height: 320 });
plain.setAxis("x", { domain: [0, 4] });
plain.setAxis("y", { domain: [0, 4] });
plain.line([1, 2, 3], [1, 2, 3]);
plain.traces.forEach((trace, index) => { trace.id = index; });
const plainPayload = plain.buildPayload();

function rejection(build) {
  try {
    build().buildPayload();
    return null;
  } catch (error) {
    return `${error.constructor.name}: ${error.message}`;
  }
}

const out = {
  protocol: PROTOCOL_VERSION,
  axes: spec.axes,
  view_ranges: spec.view.ranges,
  traces: spec.traces.map((t) => ({ id: t.id, kind: t.kind, x_axis: t.x_axis, y_axis: t.y_axis })),
  annotations: spec.annotations,
  payload_blob_len: buffers.length,
  payload_blob_sha256: sha256(buffers),
  density_y2: {
    y_range: densityPayload.spec.traces[1].density.y_range,
    buffer_sha256s: densityPayload.buffers.map((buffer) => sha256(
      Buffer.from(buffer.buffer ?? buffer, buffer.byteOffset ?? 0, buffer.byteLength),
    )),
  },
  plain_axes: Object.keys(plainPayload.spec.axes),
  plain_view_ranges: plainPayload.spec.view.ranges,
  rejections: {
    y2_annotation_without_axis: rejection(() => {
      const f = new Figure({ width: 480, height: 320 });
      f.setAxis("x", { domain: [0, 4] });
      f.setAxis("y", { domain: [0, 4] });
      f.line([1, 2, 3], [1, 2, 3]);
      f.annotate({ kind: "text", x: 2, y: 200, text: "secondary", y_axis: "y2" });
      return f;
    }),
    y2_annotation_bad_id: rejection(() => {
      const f = new Figure({ width: 480, height: 320 });
      f.setAxis("x", { domain: [0, 4] });
      f.setAxis("y", { domain: [0, 4] });
      f.line([1, 2, 3], [1, 2, 3]);
      f.annotate({ kind: "text", x: 2, y: 200, text: "secondary", y_axis: "y3" });
      return f;
    }),
  },
};

process.stdout.write(JSON.stringify(out));
