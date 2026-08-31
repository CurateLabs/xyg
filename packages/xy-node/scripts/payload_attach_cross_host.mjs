#!/usr/bin/env node
/**
 * Emit buildPayload ABI 303 optional attach goldens — consumed by
 * tests/test_payload_attach_cross_host.py.
 *
 * Usage (from repo root):
 *   node packages/xy-node/scripts/payload_attach_cross_host.mjs
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const { PROTOCOL_VERSION, abiVersion, figure } = await import(
  path.join(root, "packages/xy-node/src/index.js"),
);

function columnDtype(columns, colRef) {
  if (colRef == null) return null;
  if (Array.isArray(columns)) {
    if (!Number.isInteger(colRef) || colRef < 0 || colRef >= columns.length) return null;
    return columns[colRef]?.dtype ?? null;
  }
  return columns[colRef]?.dtype ?? null;
}

function wasmDensityMeta(spec) {
  const wasmDensity = spec.wasm_density ?? null;
  if (wasmDensity == null) return null;
  const source = wasmDensity.source ?? null;
  const columns = spec.columns ?? {};
  return {
    automatic: wasmDensity.automatic ?? null,
    unsupported: wasmDensity.unsupported ?? null,
    source:
      source == null
        ? null
        : {
            kind: source.kind ?? null,
            point_count: source.point_count ?? null,
            trace_id: source.trace_id ?? null,
            capacity: source.capacity ?? null,
            ownership: source.ownership ?? null,
            x_dtype: columnDtype(columns, source.x),
            y_dtype: columnDtype(columns, source.y),
          },
  };
}

function attachEntry(spec) {
  return {
    wasm_density: wasmDensityMeta(spec),
    frame_sides: spec.frame_sides ?? null,
    show_modebar: spec.show_modebar ?? null,
    export: spec.export ?? null,
    show_tooltip: spec.show_tooltip ?? null,
    tooltip: spec.tooltip ?? null,
    mark_style: spec.mark_style ?? null,
    interaction: spec.interaction ?? null,
    animation: spec.animation ?? null,
    graph: spec.graph ?? null,
    buffer_layout: spec.buffer_layout ?? null,
  };
}

function caseEntry(name, build, { split = false, skipScatter = false } = {}) {
  const fig = figure({ width: 240, height: 160 });
  build(fig);
  if (!skipScatter) {
    fig.scatter([0, 1, 2], [0, 1, 0.5]);
    fig.traces[0].id = 7;
  }
  const { spec } = fig.buildPayload(split ? { split: true } : {});
  return { name, ...attachEntry(spec) };
}

const cases = [
  caseEntry(
    "wasm_density_automatic_split",
    (fig) => {
      fig.scatter([1, 10], [1, 10], { forceDensity: true });
      fig.traces[0].id = 41;
    },
    { split: true, skipScatter: true },
  ),
  caseEntry(
    "wasm_density_unsupported_split",
    (fig) => {
      fig.scatter([0, 1, 2], [0, 1, 0.5], { forceDensity: true, color: [1, 2, 3] });
      fig.traces[0].id = 42;
    },
    { split: true, skipScatter: true },
  ),
  caseEntry("frame_sides_bottom_left", (fig) => {
    fig.frame_sides = ["bottom", "left"];
  }),
  caseEntry("show_modebar_false", (fig) => {
    fig.show_modebar = false;
  }),
  caseEntry("export_formats", (fig) => {
    fig.export_options = { formats: ["png", "svg"] };
  }),
  caseEntry("show_tooltip_false", (fig) => {
    fig.show_tooltip = false;
  }),
  caseEntry("tooltip_fields", (fig) => {
    fig.tooltip = {
      fields: ["x", "y"],
      title: "{x}",
      format: { x: ".2f" },
    };
  }),
  caseEntry("mark_style_hover", (fig) => {
    fig.mark_style = { hover: { color: "#111111", size: 10 } };
  }),
  caseEntry("interaction_select", (fig) => {
    fig.interaction = { select: true };
  }),
  caseEntry("animation_duration", (fig) => {
    fig.animation_options = { enabled: true, duration: 250.0 };
  }),
  caseEntry("graph_meta", (fig) => {
    fig._graphMeta = [{ layout: "force", node_trace: 0, edge_trace: 1 }];
  }),
];

process.stdout.write(
  JSON.stringify(
    {
      schema: "xyg.payload-attach-cross-host/v1",
      authority:
        "packages/xy-node/src/figure.js buildPayload ABI 303 attach flags (wasm_density, frame_sides, tooltip, mark_style, interaction, export, show_modebar, show_tooltip, animation, graph)",
      protocol: PROTOCOL_VERSION,
      abi_version: abiVersion(),
      cases,
    },
    null,
    2,
  ) + "\n",
);
