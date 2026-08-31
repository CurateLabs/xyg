#!/usr/bin/env node
/**
 * Emit force-direct/pyramid emit cross-host goldens — consumed by tests/test_force_emit_cross_host.py.
 *
 * Usage (from repo root):
 *   node packages/xy-node/scripts/force_emit_cross_host.mjs
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const { PROTOCOL_VERSION, SCATTER_DENSITY_THRESHOLD, abiVersion, figure } = await import(
  path.join(root, "packages/xy-node/src/index.js"),
);

function fill(n, fn) {
  const out = new Float64Array(n);
  for (let i = 0; i < n; i += 1) out[i] = fn(i);
  return out;
}

function caseEntry(name, nPoints, nodeOpts, traceId) {
  const x = fill(nPoints, (i) => i / nPoints);
  const y = fill(nPoints, (i) => ((i * 3) % nPoints) / nPoints);
  const fig = figure({ width: 240, height: 160 });
  fig.scatter(x, y, nodeOpts ?? {});
  fig.traces[0].id = traceId;
  const { spec } = fig.buildPayload();
  const trace = spec.traces[0];
  return {
    name,
    trace_id: trace.id,
    n_points: trace.n_points,
    tier: trace.tier ?? null,
    n_marks: trace.n_marks ?? null,
    node_opts: nodeOpts ?? {},
  };
}

const cases = [
  caseEntry(
    "scatter_large_auto_density",
    SCATTER_DENSITY_THRESHOLD + 1,
    { forceDirect: true },
    31,
  ),
  caseEntry("scatter_small_auto_direct", 10_000, { forcePyramid: true }, 32),
];

const out = {
  schema: "xyg.force-emit-cross-host/v1",
  authority: "packages/xy-node/src/figure.js _emitScatter tier decisions",
  protocol: PROTOCOL_VERSION,
  abi_version: abiVersion(),
  scatter_density_threshold: SCATTER_DENSITY_THRESHOLD,
  cases,
};

process.stdout.write(`${JSON.stringify(out, null, 2)}\n`);
