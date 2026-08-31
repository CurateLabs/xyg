#!/usr/bin/env node
/**
 * Emit density wire-metadata cross-host goldens — consumed by tests/test_density_emit_cross_host.py.
 *
 * Usage (from repo root):
 *   node packages/xy-node/scripts/density_emit_cross_host.mjs
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const { PROTOCOL_VERSION, abiVersion, figure } = await import(
  path.join(root, "packages/xy-node/src/index.js"),
);

function caseEntry(name, build) {
  const fig = figure({ width: 240, height: 160 });
  build(fig);
  const { spec } = fig.buildPayload();
  const trace = spec.traces[0];
  const density = trace.density ?? {};
  return {
    name,
    trace_id: trace.id,
    tier: trace.tier ?? null,
    density_colormap: density.colormap ?? null,
    density_dropped_channels: density.dropped_channels ?? [],
    density_channels_dropped: density.channels_dropped ?? false,
  };
}

const cases = [
  caseEntry("scatter_density_colormap", (fig) => {
    fig.scatter([0, 1, 2], [0, 1, 0.5], { forceDensity: true, colormap: "plasma" });
    fig.traces[0].id = 21;
    fig.traces[0].color_ch = { ...fig.traces[0].color_ch, colormap: "magma" };
  }),
  caseEntry("scatter_density_dropped_channels", (fig) => {
    fig.scatter([0, 1, 2], [0, 1, 0.5], { forceDensity: true, size: [1, 2, 3] });
    fig.traces[0].id = 22;
  }),
];

const out = {
  schema: "xyg.density-emit-cross-host/v1",
  authority: "packages/xy-node/src/figure.js buildPayload density wire metadata",
  protocol: PROTOCOL_VERSION,
  abi_version: abiVersion(),
  cases,
};

process.stdout.write(`${JSON.stringify(out, null, 2)}\n`);
