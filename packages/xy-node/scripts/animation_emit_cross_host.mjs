#!/usr/bin/env node
/**
 * Emit animation attach parity goldens — consumed by tests/test_animation_emit_cross_host.py.
 *
 * Usage (from repo root):
 *   node packages/xy-node/scripts/animation_emit_cross_host.mjs
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const { PROTOCOL_VERSION, abiVersion, figure } = await import(
  path.join(root, "packages/xy-node/src/index.js"),
);

const ANIM = { duration: 250, easing: "linear" };
const TRANSITION_KEYS = [
  [1, 2],
  [3, 4],
];

function caseEntry(name, build) {
  const fig = figure({ width: 240, height: 160 });
  build(fig);
  const { spec } = fig.buildPayload();
  const trace = spec.traces[0];
  const entry = {
    name,
    trace_id: trace.id,
    kind: trace.kind,
    n_points: trace.n_points,
    tier: trace.tier,
    animation: trace.animation ?? null,
  };
  if (trace.animation_fallback != null) {
    entry.animation_fallback = trace.animation_fallback;
  }
  return entry;
}

const cases = [
  caseEntry("scatter_animation", (fig) => {
    fig.scatter([1, 2, 3], [1, 2, 3]);
    fig.traces[0].id = 50;
    fig.traces[0].animation = { ...ANIM };
  }),
  caseEntry("line_animation", (fig) => {
    fig.line([0, 1, 2], [0, 1, 2]);
    fig.traces[0].id = 51;
    fig.traces[0].animation = { ...ANIM };
  }),
  caseEntry("scatter_no_animation", (fig) => {
    fig.scatter([1, 2], [1, 2]);
    fig.traces[0].id = 52;
  }),
  caseEntry("line_no_animation", (fig) => {
    fig.line([0, 1], [0, 1]);
    fig.traces[0].id = 53;
  }),
  caseEntry("scatter_log_animation", (fig) => {
    fig.setAxis("x", { type: "log" });
    fig.scatter([1, 10, 100], [1, 10, 100]);
    fig.traces[0].id = 54;
    fig.traces[0].animation = { ...ANIM };
  }),
  caseEntry("line_decimated_animation", (fig) => {
    const n = 10001;
    const xs = Array.from({ length: n }, (_, i) => i);
    const ys = Array.from({ length: n }, (_, i) => i % 7);
    fig.line(xs, ys);
    fig.traces[0].id = 55;
    fig.traces[0].animation = { ...ANIM };
  }),
  caseEntry("area_animation", (fig) => {
    fig.area([0, 1, 2], [0, 1, 2]);
    fig.traces[0].id = 56;
    fig.traces[0].animation = { ...ANIM };
  }),
  caseEntry("area_no_animation", (fig) => {
    fig.area([0, 1], [0, 1]);
    fig.traces[0].id = 57;
  }),
  caseEntry("area_decimated_animation", (fig) => {
    const n = 10001;
    const xs = Array.from({ length: n }, (_, i) => i);
    const ys = Array.from({ length: n }, (_, i) => i % 7);
    fig.area(xs, ys);
    fig.traces[0].id = 58;
    fig.traces[0].animation = { ...ANIM };
  }),
  caseEntry("density_animation", (fig) => {
    fig.scatter([1, 2, 3], [1, 2, 3], { forceDensity: true });
    fig.traces[0].id = 59;
    fig.traces[0].animation = { ...ANIM };
  }),
  caseEntry("density_no_animation", (fig) => {
    fig.scatter([1, 2], [1, 2], { forceDensity: true });
    fig.traces[0].id = 60;
  }),
  caseEntry("hist_animation", (fig) => {
    fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
    fig.traces[0].id = 61;
    fig.traces[0].animation = { ...ANIM };
  }),
  caseEntry("hist_no_animation", (fig) => {
    fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
    fig.traces[0].id = 62;
  }),
  caseEntry("bar_animation", (fig) => {
    fig.bar([0, 1], [1, 2]);
    fig.traces[0].id = 63;
    fig.traces[0].animation = { ...ANIM };
  }),
  caseEntry("bar_no_animation", (fig) => {
    fig.bar([0, 1], [1, 2]);
    fig.traces[0].id = 64;
  }),
  caseEntry("segments_animation", (fig) => {
    fig.segments([0, 1], [0, 1], [1, 2], [1, 2]);
    fig.traces[0].id = 65;
    fig.traces[0].animation = { ...ANIM };
  }),
  caseEntry("segments_no_animation", (fig) => {
    fig.segments([0, 1], [0, 1], [1, 2], [1, 2]);
    fig.traces[0].id = 66;
  }),
  caseEntry("ribbon_animation", (fig) => {
    fig.ribbon([0], [1], [0], [1], [0], [1]);
    fig.traces[0].id = 67;
    fig.traces[0].animation = { ...ANIM };
  }),
  caseEntry("ribbon_no_animation", (fig) => {
    fig.ribbon([0], [1], [0], [1], [0], [1]);
    fig.traces[0].id = 68;
  }),
  caseEntry("mesh_animation", (fig) => {
    fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
    fig.traces[0].id = 69;
    fig.traces[0].animation = { ...ANIM };
  }),
  caseEntry("mesh_no_animation", (fig) => {
    fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
    fig.traces[0].id = 70;
  }),
  caseEntry("density_transition_keys", (fig) => {
    fig.scatter([0, 1], [0, 1], { forceDensity: true });
    fig.traces[0].id = 71;
    fig.traces[0].transition_keys = TRANSITION_KEYS.map((row) => [...row]);
  }),
];

const out = {
  schema: "xyg.animation-emit-cross-host/v1",
  authority:
    "packages/xy-node/src/figure.js payloadBaseEntryPlan and attachTransitionEntry attachAnimation",
  protocol: PROTOCOL_VERSION,
  abi_version: abiVersion(),
  cases,
};

process.stdout.write(`${JSON.stringify(out, null, 2)}\n`);
