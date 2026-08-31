#!/usr/bin/env node
/**
 * Emit live Node payload cross-host goldens — consumed by tests/test_payload_cross_host.py.
 *
 * Usage (from repo root):
 *   node packages/xy-node/scripts/payload_cross_host_golden.mjs
 */
import crypto from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const { PROTOCOL_VERSION, abiVersion, figure } = await import(
  path.join(root, "packages/xy-node/src/index.js")
);

function sha256(buf) {
  return crypto.createHash("sha256").update(Buffer.from(buf)).digest("hex");
}

function caseEntry(name, build) {
  const fig = figure({ width: 240, height: 160 });
  build(fig);
  const { spec, buffers } = fig.buildPayload();
  const trace = spec.traces[0];
  const entry = {
    name,
    width: spec.width,
    height: spec.height,
    trace_id: trace.id,
    kind: trace.kind,
    tier: trace.tier ?? null,
    n_marks: trace.n_marks ?? null,
    payload_blob_len: buffers.length,
    payload_blob_sha256: sha256(buffers),
    payload_blob_hex: Buffer.from(buffers).toString("hex"),
    trace_keys: trace.keys ?? null,
  };
  if (trace.keys != null) {
    const lo = spec.columns[trace.keys.lo];
    const hi = spec.columns[trace.keys.hi];
    entry.keys_lo_hex = Buffer.from(buffers).subarray(lo.byte_offset, lo.byte_offset + lo.len * 4).toString("hex");
    entry.keys_hi_hex = Buffer.from(buffers).subarray(hi.byte_offset, hi.byte_offset + hi.len * 4).toString("hex");
  }
  return entry;
}

const cases = [
  caseEntry("scatter_direct", (fig) => {
    fig.scatter([0, 1, 2], [0, 1, 0.5]);
    fig.traces[0].id = 7;
  }),
  caseEntry("scatter_categorical_color", (fig) => {
    fig.scatter([0, 1, 2], [0, 1, 0.5], { color: ["a", "b", "a"] });
    fig.traces[0].id = 15;
  }),
  caseEntry("line_transition_keys", (fig) => {
    fig.line([0, 1, 2], [0, 1, 0.5]);
    fig.traces[0].id = 8;
    fig.traces[0].transition_keys = [
      [1, 2],
      [3, 4],
      [5, 6],
    ];
  }),
  caseEntry("histogram_fixed_bins", (fig) => {
    fig.histogram([0, 1, 1, 2, 3], { bins: 3, range: [0, 3] });
    fig.traces[0].id = 10;
  }),
  caseEntry("segments_pass_through", (fig) => {
    fig.segments([0, 1], [0, 1], [1, 2], [1, 0]);
    fig.traces[0].id = 12;
  }),
  caseEntry("hexbin_colormap", (fig) => {
    fig.axis_options = { x: { domain: [0, 4] }, y: { domain: [0, 5] } };
    fig.hexbin(
      [0.5, 1.5, 2.5, 3.5, 1.0, 2.0, 3.0],
      [0.5, 0.5, 0.5, 0.5, 2.0, 2.0, 2.0],
      { gridsize: [4, 4], range: [[0, 4], [0, 5]], name: "hex" },
    );
    fig.traces[0].id = 14;
  }),
  caseEntry("bar_compact", (fig) => {
    fig.bar([0, 1], [1, 2]);
    fig.traces[0].id = 9;
  }),
  caseEntry("heatmap_colormap", (fig) => {
    fig.heatmap([[0, 1], [1, 0]], { colormap: "viridis" });
    fig.traces[0].id = 11;
  }),
  caseEntry("triangle_mesh_single", (fig) => {
    fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
    fig.traces[0].id = 20;
  }),
];

const out = {
  schema: "xyg.payload-cross-host/v1",
  authority: "packages/xy-node/src/figure.js buildPayload",
  protocol: PROTOCOL_VERSION,
  abi_version: abiVersion(),
  cases,
};

process.stdout.write(`${JSON.stringify(out)}\n`);
