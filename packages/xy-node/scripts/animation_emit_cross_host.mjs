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

function caseEntry(name, build) {
  const fig = figure({ width: 240, height: 160 });
  build(fig);
  const { spec } = fig.buildPayload();
  const trace = spec.traces[0];
  return {
    name,
    trace_id: trace.id,
    kind: trace.kind,
    n_points: trace.n_points,
    tier: trace.tier,
    animation: trace.animation ?? null,
  };
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
];

const out = {
  schema: "xyg.animation-emit-cross-host/v1",
  authority: "packages/xy-node/src/figure.js payloadBaseEntryPlan and attachTransitionEntry attachAnimation",
  protocol: PROTOCOL_VERSION,
  abi_version: abiVersion(),
  cases,
};

process.stdout.write(`${JSON.stringify(out, null, 2)}\n`);
