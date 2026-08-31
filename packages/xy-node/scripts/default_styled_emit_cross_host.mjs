#!/usr/bin/env node
/**
 * Emit default-styled payload parity goldens — consumed by
 * tests/test_default_styled_emit_cross_host.py.
 *
 * Usage (from repo root):
 *   node packages/xy-node/scripts/default_styled_emit_cross_host.mjs
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const { DEFAULT_PALETTE, PROTOCOL_VERSION, abiVersion, figure } = await import(
  path.join(root, "packages/xy-node/src/index.js"),
);

function caseEntry(name, build, pickTrace = (spec) => spec.traces[0]) {
  const fig = figure({ width: 240, height: 160 });
  build(fig);
  const { spec } = fig.buildPayload();
  const trace = pickTrace(spec);
  return {
    name,
    trace_id: trace.id,
    kind: trace.kind,
    style: trace.style ?? {},
    palette_color: DEFAULT_PALETTE[trace.id % DEFAULT_PALETTE.length],
  };
}

const cases = [
  caseEntry("line_default_styled", (fig) => {
    fig.line([0, 1], [0, 1]);
    fig.traces[0].id = 16;
    fig.traces[0].style = { opacity: 0.9 };
  }),
  caseEntry("area_default_styled", (fig) => {
    fig.area([0, 1], [0, 1]);
    fig.traces[0].id = 17;
    fig.traces[0].style = { opacity: 0.9 };
  }),
  caseEntry("hist_default_styled", (fig) => {
    fig.histogram([0, 1, 1, 2], { bins: 2, range: [0, 2] });
    fig.traces[0].id = 18;
    fig.traces[0].style = { opacity: 0.9 };
  }),
  caseEntry("mesh_default_styled", (fig) => {
    fig.triangleMesh([0], [0], [1], [0], [0.5], [1]);
    fig.traces[0].id = 19;
    fig.traces[0].style = { opacity: 0.9 };
  }),
  caseEntry("segments_default_styled", (fig) => {
    fig.segments([0, 1], [0, 1], [1, 2], [1, 2]);
    fig.traces[0].id = 20;
    fig.traces[0].style = { opacity: 0.9 };
  }),
  caseEntry("ribbon_default_styled", (fig) => {
    fig.ribbon([0], [1], [0], [1], [0], [1]);
    fig.traces[0].id = 21;
    fig.traces[0].style = { opacity: 0.9 };
  }),
  caseEntry("rect_default_styled", (fig) => {
    fig.box([1, 2, 3, 4, 5]);
    const whiskerIdx = fig.traces.findIndex((t) => t.kind === "box_whisker");
    fig.traces[whiskerIdx].id = 22;
    fig.traces[whiskerIdx].style = { opacity: 0.9 };
  }, (spec) => spec.traces.find((t) => t.kind === "box_whisker")),
  caseEntry("hexbin_default_styled", (fig) => {
    fig.hexbin([1, 2, 3, 4, 5], [1, 2, 1, 2, 1.5], { gridsize: 4 });
    fig.traces[0].id = 23;
    fig.traces[0].style = { opacity: 0.9 };
  }),
];

const out = {
  schema: "xyg.default-styled-emit-cross-host/v1",
  authority: "packages/xy-node/src/figure.js _defaultStyled emit paths",
  protocol: PROTOCOL_VERSION,
  abi_version: abiVersion(),
  cases,
};

process.stdout.write(`${JSON.stringify(out, null, 2)}\n`);
