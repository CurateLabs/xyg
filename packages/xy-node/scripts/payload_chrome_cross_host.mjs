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
    colorbar: spec.colorbar ?? null,
    extra_legends: spec.extra_legends ?? null,
    annotations: spec.annotations ?? null,
    padding: spec.padding ?? null,
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
  caseEntry("colorbar_right", (fig) => {
    fig.setColorbar({
      domain: [0, 1],
      stops: [
        [0, [0, 0, 0, 255]],
        [1, [255, 255, 255, 255]],
      ],
      title: "Scale",
    });
  }),
  caseEntry("colorbar_bottom_minor", (fig) => {
    fig.setColorbar({
      domain: [0, 1],
      stops: [
        [0, [0, 0, 0, 255]],
        [1, [255, 255, 255, 255]],
      ],
      side: "bottom",
      minor_ticks: true,
    });
  }),
  caseEntry("extra_legends_lower_left", (fig) => {
    fig.extra_legends = [{ loc: "lower left", title: "Extra" }];
  }),
  caseEntry("annotation_text", (fig) => {
    fig.annotations = [{ kind: "text", text: "hi", x: 0, y: 1 }];
  }),
  caseEntry("annotation_rule", (fig) => {
    fig.annotations = [
      {
        kind: "rule",
        axis: "x",
        value: 1.0,
        text: "line",
        style: { color: "#ff0000", width: 2.0 },
      },
    ];
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
  caseEntry("dom_chrome_styles", (fig) => {
    fig.chrome_styles = { title: { "font-size": "18px", color: "#333333" } };
  }),
  caseEntry("padding_explicit", (fig) => {
    fig.padding = [8, 8, 8, 8];
  }),
  caseEntry("chrome_combined", (fig) => {
    fig.show_legend = false;
    fig.class_name = "root-node";
    fig.style = { height: "320px" };
    fig.class_names = { canvas: "p" };
    fig.chrome_styles = { title: { "font-weight": "bold" } };
  }),
];

process.stdout.write(
  JSON.stringify(
    {
      schema: "xyg.payload-chrome-cross-host/v1",
      authority: "packages/xy-node/src/figure.js buildPayload show_legend, legend, title_options, colorbar, extra_legends, annotations, and domSpec",
      protocol: PROTOCOL_VERSION,
      abi_version: abiVersion(),
      cases,
    },
    null,
    2,
  ) + "\n",
);
