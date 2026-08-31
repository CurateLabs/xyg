#!/usr/bin/env node
/**
 * Emit tooltip_rows length parity goldens — consumed by tests/test_tooltip_len_emit_cross_host.py.
 *
 * Usage (from repo root):
 *   node packages/xy-node/scripts/tooltip_len_emit_cross_host.mjs
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const { PROTOCOL_VERSION, abiVersion, figure } = await import(
  path.join(root, "packages/xy-node/src/index.js"),
);

function okCase(name, traceId, build) {
  const fig = figure({ width: 240, height: 160 });
  build(fig);
  fig.traces[0].id = traceId;
  const { spec } = fig.buildPayload();
  const trace = spec.traces[0];
  return {
    name,
    trace_id: trace.id,
    kind: trace.kind,
    n_points: trace.n_points,
    tooltip_rows: trace.tooltip_rows ?? null,
    expect_error: false,
  };
}

function mismatchCase(name, traceId, build) {
  const fig = figure({ width: 240, height: 160 });
  build(fig);
  fig.traces[0].id = traceId;
  let message = null;
  try {
    fig.buildPayload();
  } catch (err) {
    message = String(err?.message ?? err);
  }
  return {
    name,
    trace_id: traceId,
    expect_error: true,
    error_match: "tooltip rows must match geometry",
    error_message: message,
  };
}

const cases = [
  okCase("scatter_tooltip_ok", 40, (fig) => {
    fig.scatter([1, 2, 3], [1, 2, 3]);
    fig.traces[0].tooltip_rows = [{ rank: 1 }, { rank: 2 }, { rank: 3 }];
  }),
  okCase("segments_tooltip_ok", 41, (fig) => {
    fig.segments([0, 1], [0, 1], [1, 2], [1, 2]);
    fig.traces[0].tooltip_rows = [{ id: "a" }, { id: "b" }];
  }),
  okCase("ribbon_tooltip_ok", 42, (fig) => {
    fig.ribbon([0, 1], [1, 2], [0, 1], [1, 2], [0.5, 1.5], [1.5, 2.5]);
    fig.traces[0].tooltip_rows = [{ id: "a" }, { id: "b" }];
  }),
  mismatchCase("scatter_tooltip_mismatch", 43, (fig) => {
    fig.scatter([0, 1], [0, 1]);
    fig.traces[0].tooltip_rows = [{ id: "a" }];
  }),
  mismatchCase("segments_tooltip_mismatch", 44, (fig) => {
    fig.segments([0, 1], [0, 1], [1, 2], [1, 2]);
    fig.traces[0].tooltip_rows = [{ id: "a" }];
  }),
  mismatchCase("ribbon_tooltip_mismatch", 45, (fig) => {
    fig.ribbon([0], [1], [0], [1], [0], [1]);
    fig.traces[0].tooltip_rows = [{ id: "a" }, { id: "b" }];
  }),
];

const out = {
  schema: "xyg.tooltip-len-emit-cross-host/v1",
  authority: "packages/xy-node/src/figure.js attachTooltipRows",
  protocol: PROTOCOL_VERSION,
  abi_version: abiVersion(),
  cases,
};

process.stdout.write(`${JSON.stringify(out, null, 2)}\n`);
