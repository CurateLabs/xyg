#!/usr/bin/env node
/**
 * Series palette cursor cross-host golden — consumed by
 * tests/test_series_palette_cross_host.py.
 *
 * Verifies that Node resolves default series colors from the figure's palette
 * cycle in the same order as Python, for every mark kind that participates
 * in the cursor (#918).
 *
 * Usage (from repo root):
 *   node packages/xy-node/scripts/series_palette_cross_host.mjs
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const { DEFAULT_PALETTE, PROTOCOL_VERSION, abiVersion, figure } = await import(
  path.join(root, "packages/xy-node/src/index.js"),
);

/**
 * Extract the resolved constant color for a trace from the built payload.
 * Returns the CSS hex string, or null if the trace uses a non-constant channel.
 *
 * Ribbon color is always null: Python ships ribbon paint as direct RGBA (not a
 * constant CSS string), so both sides return null and cursor behavior is
 * verified through the subsequent trace (#918).
 */
function resolveTracePayloadColor(specTrace) {
  if (specTrace == null) return null;
  // Ribbon color is shipped as direct RGBA in Python — return null to match.
  if (specTrace.kind === "ribbon") return null;
  const color = specTrace.color;
  if (color != null && typeof color === "object" && color.mode === "constant") {
    return color.color ?? null;
  }
  const style = specTrace.style;
  if (style != null && typeof style.color === "string") return style.color;
  return null;
}

function buildCase(name, build) {
  const result = build();
  return { name, ...result };
}

const cases = [
  buildCase("builtin_cursor_scatter_line_hist", () => {
    // Default palette: scatter → slot 0, line → slot 1, histogram → slot 2.
    const fig = figure({ width: 240, height: 160 });
    fig.scatter([0, 1], [0, 1]);
    fig.line([0, 1], [0, 1]);
    fig.histogram([1, 2, 3, 4]);
    const { spec } = fig.buildPayload();
    return {
      palette: null,
      trace_colors: spec.traces.map((t) => ({
        kind: t.kind,
        color: resolveTracePayloadColor(t),
      })),
    };
  }),

  buildCase("builtin_cursor_bar_2series", () => {
    // Default palette: bar with 2 series → slots 0 and 1.
    const fig = figure({ width: 240, height: 160 });
    fig.bar([0, 1, 2], [[1, 2, 3], [4, 5, 6]]);
    const { spec } = fig.buildPayload();
    return {
      palette: null,
      trace_colors: spec.traces.map((t) => ({
        kind: t.kind,
        color: resolveTracePayloadColor(t),
      })),
    };
  }),

  buildCase("builtin_cursor_segments_errorbar", () => {
    // Default palette: segments → slot 0, errorbar → slot 1 (one slot for all
    // errorbar sub-traces).
    const fig = figure({ width: 240, height: 160 });
    fig.segments([0, 1], [0, 1], [1, 2], [1, 2]);
    fig.errorbar([0, 1], [0.5, 1.5], { yerr: 0.1 });
    const { spec } = fig.buildPayload();
    return {
      palette: null,
      trace_colors: spec.traces.map((t) => ({
        kind: t.kind,
        color: resolveTracePayloadColor(t),
      })),
    };
  }),

  buildCase("custom_palette_cursor", () => {
    // Custom 3-color palette: scatter → #aa0000, line → #00aa00, hist → #0000aa.
    const fig = figure({ width: 240, height: 160, palette: ["#aa0000", "#00aa00", "#0000aa"] });
    fig.scatter([0, 1], [0, 1]);
    fig.line([0, 1], [0, 1]);
    fig.histogram([1, 2, 3, 4]);
    const { spec } = fig.buildPayload();
    return {
      palette: ["#aa0000", "#00aa00", "#0000aa"],
      trace_colors: spec.traces.map((t) => ({
        kind: t.kind,
        color: resolveTracePayloadColor(t),
      })),
    };
  }),

  buildCase("custom_palette_wrap", () => {
    // 2-color palette: 3rd mark wraps to slot 0 color.
    const fig = figure({ width: 240, height: 160, palette: ["#ff0000", "#00ff00"] });
    fig.scatter([0, 1], [0, 1]);
    fig.line([0, 1], [0, 1]);
    // Suppress the RuntimeWarning for wrap
    const origEmit = process.emitWarning.bind(process);
    process.emitWarning = () => {};
    fig.histogram([1, 2, 3]);
    process.emitWarning = origEmit;
    const { spec } = fig.buildPayload();
    return {
      palette: ["#ff0000", "#00ff00"],
      trace_colors: spec.traces.map((t) => ({
        kind: t.kind,
        color: resolveTracePayloadColor(t),
      })),
    };
  }),

  buildCase("explicit_color_no_cursor", () => {
    // Explicit color= skips the cursor; the next mark gets slot 0.
    const fig = figure({ width: 240, height: 160, palette: ["#aa0000", "#00aa00"] });
    fig.scatter([0, 1], [0, 1], { color: "#abcdef" });
    fig.line([0, 1], [0, 1]);
    const { spec } = fig.buildPayload();
    return {
      palette: ["#aa0000", "#00aa00"],
      trace_colors: spec.traces.map((t) => ({
        kind: t.kind,
        color: resolveTracePayloadColor(t),
      })),
    };
  }),

  buildCase("graph_node_cursor_edge_neutral", () => {
    // Graph: node scatter takes next cursor slot; edge segments use neutral
    // "#888888" and do NOT advance the cursor.
    // scatter → slot 0 = DEFAULT_PALETTE[0]; graph node → slot 1 = DEFAULT_PALETTE[1].
    const fig = figure({ width: 240, height: 160 });
    fig.scatter([0, 1], [0, 1]);
    fig.graph(["a", "b", "c"], [["a", "b"], ["b", "c"]]);
    const { spec } = fig.buildPayload();
    return {
      palette: null,
      trace_colors: spec.traces.map((t) => ({
        kind: t.kind,
        color: resolveTracePayloadColor(t),
      })),
    };
  }),

  buildCase("graph_custom_palette_node", () => {
    // Custom palette: graph node takes the first slot (#aa0000).
    const fig = figure({ width: 240, height: 160, palette: ["#aa0000", "#00aa00"] });
    fig.graph(["a", "b", "c"], [["a", "b"], ["b", "c"]]);
    const { spec } = fig.buildPayload();
    return {
      palette: ["#aa0000", "#00aa00"],
      trace_colors: spec.traces.map((t) => ({
        kind: t.kind,
        color: resolveTracePayloadColor(t),
      })),
    };
  }),

  // --- New cases for findings 1–4 and coverage of all changed marks ---

  buildCase("heatmap_string_color", () => {
    // Explicit string color= skips cursor; following line takes slot 0.
    const fig = figure({ width: 240, height: 160, palette: ["#aa0000", "#00aa00"] });
    fig.heatmap([[1, 2], [3, 4]], { rows: 2, cols: 2, color: "#ff00ff" });
    fig.line([0, 1], [0, 1]);
    const { spec } = fig.buildPayload();
    return {
      palette: ["#aa0000", "#00aa00"],
      trace_colors: spec.traces.map((t) => ({ kind: t.kind, color: resolveTracePayloadColor(t) })),
    };
  }),

  buildCase("heatmap_no_color", () => {
    // No explicit color → cursor advances; scatter gets slot 1.
    const fig = figure({ width: 240, height: 160 });
    fig.heatmap([[1, 2], [3, 4]], { rows: 2, cols: 2 });
    fig.scatter([0, 1], [0, 1]);
    const { spec } = fig.buildPayload();
    return {
      palette: null,
      trace_colors: spec.traces.map((t) => ({ kind: t.kind, color: resolveTracePayloadColor(t) })),
    };
  }),

  buildCase("heatmap_nonstring_color", () => {
    // Non-string color → cursor advances (finding 3).
    // scatter takes slot 0, heatmap takes slot 1.
    const fig = figure({ width: 240, height: 160, palette: ["#aa0000", "#00aa00"] });
    fig.scatter([0, 1], [0, 1]);
    fig.heatmap([[1, 2], [3, 4]], { rows: 2, cols: 2, color: [1.0, 0.0, 0.0] });
    const { spec } = fig.buildPayload();
    return {
      palette: ["#aa0000", "#00aa00"],
      trace_colors: spec.traces.map((t) => ({ kind: t.kind, color: resolveTracePayloadColor(t) })),
    };
  }),

  buildCase("hexbin_cursor", () => {
    // Hexbin takes one cursor slot (colormap background/fallback color).
    const fig = figure({ width: 240, height: 160 });
    fig.hexbin(
      Float64Array.from({ length: 10 }, (_, i) => i),
      Float64Array.from({ length: 10 }, (_, i) => i),
    );
    fig.scatter([0, 1], [0, 1]);
    const { spec } = fig.buildPayload();
    return {
      palette: null,
      trace_colors: spec.traces.map((t) => ({ kind: t.kind, color: resolveTracePayloadColor(t) })),
    };
  }),

  buildCase("ribbon_no_color", () => {
    // Ribbon without explicit color consumes slot 0; scatter gets slot 1.
    // Ribbon color is null in both Python and Node (direct RGBA, not CSS constant).
    const fig = figure({ width: 240, height: 160, palette: ["#aa0000", "#00aa00"] });
    const x0 = Float64Array.of(0, 1);
    const x1 = Float64Array.of(1, 2);
    const slo = Float64Array.of(0, 1);
    const shi = Float64Array.of(0.5, 1.5);
    const tlo = Float64Array.of(0, 1);
    const thi = Float64Array.of(0.5, 1.5);
    fig.ribbon(x0, x1, slo, shi, tlo, thi);
    fig.scatter([0, 1], [0, 1]);
    const { spec } = fig.buildPayload();
    return {
      palette: ["#aa0000", "#00aa00"],
      trace_colors: spec.traces.map((t) => ({ kind: t.kind, color: resolveTracePayloadColor(t) })),
    };
  }),

  buildCase("ribbon_style_color", () => {
    // style.color is explicit → cursor NOT advanced (finding 4); scatter takes slot 0.
    const fig = figure({ width: 240, height: 160, palette: ["#aa0000", "#00aa00"] });
    const x0 = Float64Array.of(0, 1);
    const x1 = Float64Array.of(1, 2);
    const slo = Float64Array.of(0, 1);
    const shi = Float64Array.of(0.5, 1.5);
    const tlo = Float64Array.of(0, 1);
    const thi = Float64Array.of(0.5, 1.5);
    fig.ribbon(x0, x1, slo, shi, tlo, thi, { style: { color: "#ff1234" } });
    fig.scatter([0, 1], [0, 1]);
    const { spec } = fig.buildPayload();
    return {
      palette: ["#aa0000", "#00aa00"],
      trace_colors: spec.traces.map((t) => ({ kind: t.kind, color: resolveTracePayloadColor(t) })),
    };
  }),

  buildCase("area_cursor", () => {
    const fig = figure({ width: 240, height: 160 });
    fig.area([0, 1, 2], [0, 1, 0]);
    fig.scatter([0, 1], [0, 1]);
    const { spec } = fig.buildPayload();
    return {
      palette: null,
      trace_colors: spec.traces.map((t) => ({ kind: t.kind, color: resolveTracePayloadColor(t) })),
    };
  }),

  buildCase("step_cursor", () => {
    // step() delegates to line(); emitted trace kind is "line".
    const fig = figure({ width: 240, height: 160 });
    fig.step([0, 1, 2], [0, 1, 0]);
    fig.scatter([0, 1], [0, 1]);
    const { spec } = fig.buildPayload();
    return {
      palette: null,
      trace_colors: spec.traces.map((t) => ({ kind: t.kind, color: resolveTracePayloadColor(t) })),
    };
  }),

  buildCase("box_cursor", () => {
    // box() takes one slot; whisker/box/median sub-traces share it.
    const fig = figure({ width: 240, height: 160 });
    fig.box([1, 2, 3, 4, 5]);
    fig.scatter([0, 1], [0, 1]);
    const { spec } = fig.buildPayload();
    return {
      palette: null,
      trace_colors: spec.traces.map((t) => ({ kind: t.kind, color: resolveTracePayloadColor(t) })),
    };
  }),

  buildCase("violin_cursor", () => {
    const fig = figure({ width: 240, height: 160 });
    fig.violin([1, 2, 3, 4, 5]);
    fig.scatter([0, 1], [0, 1]);
    const { spec } = fig.buildPayload();
    return {
      palette: null,
      trace_colors: spec.traces.map((t) => ({ kind: t.kind, color: resolveTracePayloadColor(t) })),
    };
  }),

  buildCase("stem_cursor", () => {
    // stem() takes one slot; segment trace and scatter marker share it.
    const fig = figure({ width: 240, height: 160 });
    fig.stem([0, 1, 2], [1, 2, 3]);
    fig.scatter([0, 1], [0, 1]);
    const { spec } = fig.buildPayload();
    return {
      palette: null,
      trace_colors: spec.traces.map((t) => ({ kind: t.kind, color: resolveTracePayloadColor(t) })),
    };
  }),

  buildCase("triangle_mesh_cursor", () => {
    const fig = figure({ width: 240, height: 160 });
    fig.triangleMesh(
      Float64Array.of(0), Float64Array.of(0),
      Float64Array.of(1), Float64Array.of(0),
      Float64Array.of(0.5), Float64Array.of(1),
    );
    fig.scatter([0, 1], [0, 1]);
    const { spec } = fig.buildPayload();
    return {
      palette: null,
      trace_colors: spec.traces.map((t) => ({ kind: t.kind, color: resolveTracePayloadColor(t) })),
    };
  }),

  buildCase("scatter_style_color_explicit", () => {
    // style.color is explicit → cursor NOT advanced; line takes slot 0.
    const fig = figure({ width: 240, height: 160, palette: ["#aa0000", "#00aa00"] });
    fig.scatter([0, 1], [0, 1], { style: { color: "#aabbcc" } });
    fig.line([0, 1], [0, 1]);
    const { spec } = fig.buildPayload();
    return {
      palette: ["#aa0000", "#00aa00"],
      trace_colors: spec.traces.map((t) => ({ kind: t.kind, color: resolveTracePayloadColor(t) })),
    };
  }),

  buildCase("bar_style_color_explicit", () => {
    // Bar with style.color — cursor NOT advanced (finding 2); scatter takes slot 0.
    const fig = figure({ width: 240, height: 160, palette: ["#aa0000", "#00aa00"] });
    fig.bar([0, 1, 2], [1, 2, 3], { style: { color: "#ff0000" } });
    fig.scatter([0, 1], [0, 1]);
    const { spec } = fig.buildPayload();
    return {
      palette: ["#aa0000", "#00aa00"],
      trace_colors: spec.traces.map((t) => ({ kind: t.kind, color: resolveTracePayloadColor(t) })),
    };
  }),

  buildCase("bar_flat_multi_series", () => {
    // Flat Float64Array multi-series: composeBar detects 2 series (finding 1).
    // Python uses a 2-D numpy array (shape 2×3) for the same result.
    const fig = figure({ width: 240, height: 160 });
    fig.bar([0, 1, 2], new Float64Array([1, 2, 3, 4, 5, 6]));
    const { spec } = fig.buildPayload();
    return {
      palette: null,
      trace_colors: spec.traces.map((t) => ({ kind: t.kind, color: resolveTracePayloadColor(t) })),
    };
  }),
];

const out = {
  schema: "xyg.series-palette-cross-host/v1",
  authority: "packages/xy-node/src/figure.js nextSeriesColor + Python Figure.next_series_color (#918)",
  protocol: PROTOCOL_VERSION,
  abi_version: abiVersion(),
  cases,
};

process.stdout.write(`${JSON.stringify(out, null, 2)}\n`);
