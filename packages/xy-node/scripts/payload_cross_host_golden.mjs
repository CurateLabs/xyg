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
  caseEntry("scatter_style_channels", (fig) => {
    fig.scatter([0, 1], [0, 1]);
    fig.traces[0].style_channels = { stroke_width: { values: [2, 3] } };
    fig.traces[0].id = 34;
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
  caseEntry("histogram_finite_sel", (fig) => {
    fig.traces.push({
      kind: "histogram",
      id: 17,
      name: null,
      x0: new Float64Array([0, 1]),
      x1: new Float64Array([1, 2]),
      y0: new Float64Array([0, 0]),
      y1: new Float64Array([1, Number.NaN]),
      style: { color: "#3987e5", opacity: 0.85, role: "histogram" },
      count: 4,
    });
  }),
  caseEntry("histogram_style_channels", (fig) => {
    fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
    fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
    fig.traces[0].id = 21;
  }),
  caseEntry("histogram_stroke_ch", (fig) => {
    fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
    fig.traces[0].stroke_ch = {
      mode: "direct_rgba",
      rgba: Float64Array.from([1, 0, 0, 1, 0, 1, 0, 1]),
      n: 2,
    };
    fig.traces[0].id = 31;
  }),
  caseEntry("histogram_color_ch", (fig) => {
    fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
    fig.traces[0].color_ch = { mode: "constant", constant: "#112233" };
    fig.traces[0].id = 35;
  }),
  caseEntry("segments_pass_through", (fig) => {
    fig.segments([0, 1], [0, 1], [1, 2], [1, 0]);
    fig.traces[0].id = 12;
  }),
  caseEntry("segments_color_ch", (fig) => {
    fig.segments([0], [0], [1], [1], { color: "#112233" });
    fig.traces[0].color_ch = { mode: "constant", constant: "#445566" };
    fig.traces[0].id = 22;
  }),
  caseEntry("segments_style_channels", (fig) => {
    fig.segments([0, 1], [0, 1], [1, 2], [1, 0]);
    fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
    fig.traces[0].id = 33;
  }),
  caseEntry("rect_color_ch", (fig) => {
    fig.bar([0, 1], [1, 2], { color: "#112233" });
    fig.traces[0].color_ch = { mode: "constant", constant: "#445566" };
    fig.traces[0].id = 23;
  }),
  caseEntry("rect_style_channels", (fig) => {
    fig.bar([0, 1], [1, 2]);
    fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
    fig.traces[0].id = 32;
  }),
  caseEntry("mesh_style_channels", (fig) => {
    fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
    fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
    fig.traces[0].id = 24;
  }),
  caseEntry("ribbon_style_channels", (fig) => {
    fig.ribbon([0], [1], [0], [1], [0], [1], { color: "#112233" });
    fig.traces[0].style_channels = { stroke_width: { mode: "constant", constant: 2 } };
    fig.traces[0].id = 25;
  }),
  caseEntry("rect_stroke_ch", (fig) => {
    fig.bar([0, 1], [1, 2]);
    fig.traces[0].stroke_ch = {
      mode: "direct_rgba",
      rgba: Float64Array.from([1, 0, 0, 1, 0, 1, 0, 1]),
      n: 2,
    };
    fig.traces[0].id = 26;
  }),
  caseEntry("mesh_stroke_ch", (fig) => {
    fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
    fig.traces[0].stroke_ch = {
      mode: "direct_rgba",
      rgba: Float64Array.from([1, 0, 0, 1]),
      n: 1,
    };
    fig.traces[0].id = 27;
  }),
  caseEntry("ribbon_stroke_ch", (fig) => {
    fig.ribbon([0], [1], [0], [1], [0], [1], { color: "#112233" });
    fig.traces[0].stroke_ch = { mode: "constant", constant: "#445566" };
    fig.traces[0].id = 28;
  }),
  caseEntry("segments_stroke_ch", (fig) => {
    fig.segments([0, 1], [0, 1], [1, 2], [1, 0]);
    fig.traces[0].stroke_ch = {
      mode: "direct_rgba",
      rgba: Float64Array.from([1, 0, 0, 1, 0, 1, 0, 1]),
      n: 2,
    };
    fig.traces[0].id = 29;
  }),
  caseEntry("mesh_color_ch", (fig) => {
    fig.triangleMesh([0], [0], [1], [0], [0.5], [1], { color: "#112233" });
    fig.traces[0].color_ch = { mode: "constant", constant: "#445566" };
    fig.traces[0].id = 30;
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
