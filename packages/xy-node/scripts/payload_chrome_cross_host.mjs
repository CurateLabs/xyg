#!/usr/bin/env node
/**
 * Emit buildPayload top-level chrome parity goldens — consumed by
 * tests/test_payload_chrome_cross_host.py.
 *
 * Usage (from repo root):
 *   node packages/xy-node/scripts/payload_chrome_cross_host.mjs
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
  fig.scatter([0, 1, 2], [0, 1, 0.5]);
  fig.traces[0].id = 7;
  const { spec } = fig.buildPayload();
  return {
    name,
    show_legend: spec.show_legend,
    legend: spec.legend ?? null,
    title_options: spec.title_options ?? null,
    dom: spec.dom ?? null,
  };
}

const cases = [
  caseEntry("show_legend_default", () => {}),
  caseEntry("show_legend_false", (fig) => {
    fig.show_legend = false;
  }),
  caseEntry("legend_loc_upper_right", (fig) => {
    fig.setLegend({ loc: "upper right", title: "Series" });
  }),
  caseEntry("legend_loc_best", (fig) => {
    fig.setLegend({ loc: "best" });
  }),
  caseEntry("title_options_center", (fig) => {
    fig.title_options = [{ text: "T", loc: "center", y: 1.0, pad: 8.0 }];
  }),
  caseEntry("title_options_defaults", (fig) => {
    fig.title_options = [{ text: "T" }];
  }),
  caseEntry("dom_class_name", (fig) => {
    fig.class_name = "root-node";
  }),
  caseEntry("dom_style", (fig) => {
    fig.style = { width: "100%" };
  }),
  caseEntry("dom_class_names", (fig) => {
    fig.class_names = { title: "t" };
  }),
  caseEntry("chrome_combined", (fig) => {
    fig.show_legend = false;
    fig.class_name = "root-node";
    fig.style = { height: "320px" };
    fig.class_names = { canvas: "p" };
  }),
];

process.stdout.write(
  JSON.stringify(
    {
      schema: "xyg.payload-chrome-cross-host/v1",
      authority: "packages/xy-node/src/figure.js buildPayload show_legend, legend, title_options, and domSpec",
      protocol: PROTOCOL_VERSION,
      abi_version: abiVersion(),
      cases,
    },
    null,
    2,
  ) + "\n",
);
