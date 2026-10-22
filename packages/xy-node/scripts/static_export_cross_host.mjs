#!/usr/bin/env node
/** Exhaustive Rust-registry-driven public static-export parity corpus (#875). */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ecdfChart, Figure, sceneExportSupportReason, sceneStaticExport } from "../src/index.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const registry = JSON.parse(fs.readFileSync(
  path.join(root, "tests/fixtures/static_export_support_registry.json"),
  "utf8",
));

function fixedDomains(figure) {
  figure.setAxisDomain("x", [-2, 6]);
  figure.setAxisDomain("y", [-2, 6]);
  return figure;
}

function normalizeIds(figure) {
  figure.traces.forEach((trace, index) => { trace.id = index; });
  return figure;
}

function baseFigure(name) {
  if (name === "ecdf") {
    return normalizeIds(ecdfChart([3, 1, 2, 1, 3], {
      width: 320,
      height: 240,
      color: "#ef4444",
      style: { width: 2 },
    }));
  }
  const f = new Figure({ width: 320, height: 240 });
  switch (name) {
    case "scatter": f.scatter([0, 1, 2], [1, 3, 2], { style: { color: "#3987e5", size: 6, opacity: 0.8, symbol: "diamond" } }); break;
    case "line": f.line([0, 1, 2], [1, 3, 2], { color: "#ef4444", width: 2 }); break;
    case "step": f.step([0, 1, 2], [1, 3, 2], { where: "post", color: "#ef4444", width: 2 }); break;
    case "layered_line_bar": f.line([0, 1, 2], [1, 3, 2], { color: "#ef4444", width: 2 }); f.bar([0, 1, 2], [2, 1, 4], { color: "#3987e5" }); break;
    case "stairs": f.stairs([0, 1, 2, 3], [1, 3, 2], { where: "post", color: "#ef4444", width: 2 }); break;
    case "bar": f.bar([0, 1], [1, 2], { color: "#22c55e", opacity: 0.85 }); break;
    case "column_bar": f.bar([0, 1], [1, 2], { color: "#22c55e", opacity: 0.85 }); break;
    case "histogram": f.histogram([0, 1, 1, 2], { bins: 2, color: "#7c3aed", opacity: 0.85 }); break;
    case "area": f.area([0, 1, 2], [1, 3, 2], { color: "#0ea5e9", opacity: 0.65 }); break;
    case "errorbar": f.errorbar([0, 1], [1, 2], { yerr: [0.1, 0.2], color: "#ef4444", capSize: 0 }); break;
    case "box": f.box([[1, 2, 3, 4], [2, 3, 4, 5]], { color: "#7c3aed", showOutliers: true }); break;
    case "violin": f.violin([[1, 2, 2, 3, 4], [2, 2.5, 3.5]], { bins: 8, color: "#7c3aed" }); break;
    case "violin_horizontal": f.violin([[1, 2, 2, 3, 4], [2, 2.5, 3.5]], { bins: 8, color: "#7c3aed", orientation: "horizontal" }); break;
    case "hexbin": f.hexbin([0.5, 1.5, 2.5, 3.5, 1, 2, 3], [0.5, 0.5, 0.5, 0.5, 2, 2, 2], { gridsize: [4, 4], color: "#3987e5" }); break;
    case "segments": fixedDomains(f).segments([0, 1], [0, 1], [1, 2], [1, 2], { color: "#ef4444", width: 2 }); break;
    case "stem": fixedDomains(f).stem([0, 1], [1, 2], { color: "#22c55e" }); break;
    case "error_band": fixedDomains(f).errorBand([0, 1, 2], [0.5, 1.5, 1], [1.5, 2.5, 2], { color: "#0ea5e9", opacity: 0.6 }); break;
    case "ribbon": fixedDomains(f).ribbon([0], [2], [0], [1], [1], [2], { color: "#0ea5e9", opacity: 0.6 }); break;
    case "triangle_mesh": fixedDomains(f).triangleMesh([0, 2], [0, 0], [1, 3], [2, 2], [2, 4], [0, 0], { color: "#f59e0b", opacity: 0.75 }); break;
    case "heatmap": fixedDomains(f).heatmap([[0, 1], [1, 0]], { color: "#3987e5" }); break;
    case "contour": fixedDomains(f).contour([[0, 1, 0], [1, 2, 1], [0, 1, 0]], { levels: [0.5, 1.5], color: "#ef4444", cornerMask: false }); break;
    default: throw new Error(`missing Node static-export builder for Rust registry shape ${name}`);
  }
  return normalizeIds(f);
}

function edgeFigure(name) {
  const f = new Figure({ width: 320, height: 240 });
  switch (name) {
    case "line_authored_style":
      fixedDomains(f).line([0, 1, 2], [1, 3, 2], { color: "#f97316", width: 3, style: { opacity: 0.7 } });
      break;
    case "scatter_single_log":
      f.setAxis("x", { type: "log" }); f.scatter([2], [3], { style: { color: "#3987e5", size: 7 } });
      break;
    case "step_nonfinite_authored":
      f.setAxisDomain("x", [0.5, 4]); f.setAxisDomain("y", [0.5, 4]); f.setAxis("y", { type: "log" });
      f.step([1, 2, 3], [1, Number.NaN, 3], { where: "post", color: "#ef4444" });
      break;
    case "bar_categorical_style":
      f.bar(["a", "b", "a"], [1, 2, 3], { color: "#22c55e", opacity: 0.7 }); f._axis_categories = { x: ["a", "b"] };
      break;
    case "line_temporal_single":
      f.setAxis("x", { type: "time" }); f.line([1000], [2], { color: "#ef4444" });
      break;
    case "scatter_empty_linear":
      f.scatter([], [], { style: { color: "#3987e5", size: 6 } });
      break;
    case "area_nonfinite_linear":
      fixedDomains(f);
      f.area([0, 1, 2], [1, Number.NaN, 2], { color: "#0ea5e9" });
      break;
    case "histogram_empty_categorical":
      f._axis_categories = { y: ["empty"] }; f.histogram([], { bins: 2, color: "#7c3aed" });
      break;
    case "step_temporal_log":
      f.setAxis("x", { type: "time" }); f.setAxis("y", { type: "log" }); f.step([1000, 2000], [1, 10], { where: "mid", color: "#ef4444" });
      break;
    case "line_m4_decimated": {
      const x = Float64Array.from({ length: 20001 }, (_, i) => i * 0.25);
      const y = Float64Array.from({ length: 20001 }, (_, i) => ((i * 7919) % 1009) / 10 - (i % 97));
      f.line(x, y, { color: "#ef4444", width: 1 });
      break;
    }
    case "scatter_density_large": {
      const x = Float64Array.from({ length: 270000 }, (_, i) => ((i * 7919) % 1009) / 1009 * 8 - 2);
      const y = Float64Array.from({ length: 270000 }, (_, i) => ((i * 104729) % 997) / 997 * 8 - 2);
      fixedDomains(f).scatter(x, y, { style: { color: "#3987e5" } });
      break;
    }
    case "triangle_mesh_dense_fill": {
      // #1006: 51,200 stroked, per-face colored triangles on Rust autorange.
      const [x0, y0, x1, y1, x2, y2, value] = denseMeshColumns();
      f.triangleMesh(x0, y0, x1, y1, x2, y2, { color: value, stroke: "#111827", strokeWidth: 0.5 });
      break;
    }
    default: throw new Error(`missing Node static-export edge builder for Rust registry case ${name}`);
  }
  return normalizeIds(f);
}

// A 160x160 quad grid as 51,200 triangles (#1006).
function denseMeshColumns() {
  const cols = 160;
  const step = 8 / cols;
  const n = cols * cols;
  const out = Array.from({ length: 7 }, () => new Float64Array(2 * n));
  for (let i = 0; i < n; i += 1) {
    const gx = (i % cols) * step - 2;
    const gy = Math.floor(i / cols) * step - 2;
    const value = ((i * 7919) % 101) / 100;
    for (const [face, x0, y0, x1, y1, x2, y2, v] of [
      [i, gx, gy, gx + step, gy, gx, gy + step, value],
      [n + i, gx + step, gy, gx + step, gy + step, gx, gy + step, 1 - value],
    ]) {
      [out[0][face], out[1][face], out[2][face], out[3][face], out[4][face], out[5][face], out[6][face]] = [x0, y0, x1, y1, x2, y2, v];
    }
  }
  return out;
}

function failCloseFigure(name) {
  const f = new Figure({ width: 320, height: 240 });
  f.line([0, 1], [0, 1]);
  switch (name) {
    case "fluid_viewport": f.width = "100%"; break;
    case "browser_css": f.class_name = "browser-only"; break;
    case "custom_font": f.chrome_styles = { title: { "font-family": "Example Sans" } }; break;
    case "title_options": f.title_options = { text: "title" }; break;
    case "extra_legend": f.legend_options = { ncols: 2 }; break;
    case "alternate_axis": f.traces[0].x_axis = "x2"; break;
    case "unsupported_symbol": f.traces = []; f.scatter([0], [0]); f.traces[0].style.symbol = "not-a-symbol"; break;
    case "unsupported_mark": f.traces[0].kind = "unknown"; break;
    case "violin_orientation_metadata": fixedDomains(f); f.traces = []; f.violin([[1, 2, 2, 3]], { bins: 8 }); f.traces[0].style.orientation = "diagonal"; break;
    case "annotation_html": f.annotations = [{ kind: "text", x: 0.5, y: 0.5, text: "x", html: "<b>x</b>" }]; break;
    case "annotation_collision": f.annotations = [{ kind: "text", x: 0.5, y: 0.5, text: "x", collision: "avoid" }]; break;
    case "annotation_markup": f.annotations = [{ kind: "text", x: 0.5, y: 0.5, text: "x", markup: "markdown" }]; break;
    case "invalid_annotation": f.annotations = [{ kind: "bogus" }]; break;
    case "colorbar_option": f.colorbar_options = { bogus: true }; break;
    case "lod_limit": {
      // #1006: a cartesian line this size is the M4 tier; a polar line ships
      // direct in the browser, so it stays beyond the static tiers.
      const values = Float64Array.from({ length: 10001 }, (_, index) => index);
      f.traces = []; f.coords = "polar"; f.line(values.map((value) => value / 10001), values); break;
    }
    case "band_shape": f.traces = []; f.area([0], [1]); break;
    case "segment_shape": fixedDomains(f); f.traces = []; f.segments([0, 1], [0, 1], [1, 2], [1, 2]); f.traces[0].x1 = Float64Array.of(1); break;
    case "contour_custom_colormap": fixedDomains(f); f.traces = []; f.contour([[0, 1, 0], [1, 2, 1], [0, 1, 0]], { levels: [0.5, 1.5], colormap: ["#f00", "#00f"] }); break;
    case "triangle_mesh_limit": {
      // Joined fills keep the shared 1,024 PolyFill-group budget (#1006).
      const values = new Float64Array(1025); fixedDomains(f); f.traces = [];
      f.triangleMesh(values, values, values, values, values, values);
      f.traces[0].style.joined_fill = true;
      break;
    }
    default: throw new Error(`missing Node fail-close builder for Rust registry case ${name}`);
  }
  return f;
}

function encodedCase(name, figure) {
  const reason = sceneExportSupportReason(figure);
  if (reason !== null) throw new Error(`${name} unexpectedly failed public preflight: ${reason}`);
  const scene = figure.toScene();
  const png = sceneStaticExport(scene, "png", { width: 320, height: 240, scale: 1 });
  return {
    name,
    trace_kinds: figure.traces.map((trace) => trace.kind),
    scene_b64: Buffer.from(scene).toString("base64"),
    svg_b64: Buffer.from(figure.toSceneSvg(), "utf8").toString("base64"),
    raster_b64: Buffer.from(figure.toSceneRasterCommands({ scale: 1 })).toString("base64"),
    png_b64: Buffer.from(png).toString("base64"),
    document_svg_b64: Buffer.from(figure.toSvg(), "utf8").toString("base64"),
    document_png_b64: Buffer.from(figure.toPng({ scale: 1 })).toString("base64"),
  };
}

const cases = [
  ...registry.shapes.map(({ name }) => encodedCase(name, baseFigure(name))),
  ...registry.edge_cases.filter(({ reason_prefix: reason }) => !reason).map(({ name }) => encodedCase(name, edgeFigure(name))),
];
const edgeFailClose = registry.edge_cases.filter(({ reason_prefix: reason }) => reason).map(({ name, reason_prefix: expected }) => {
  const reason = sceneExportSupportReason(edgeFigure(name));
  if (reason === null || !reason.startsWith(expected)) {
    throw new Error(`${name} edge fail-close mismatch: expected ${expected}, got ${reason}`);
  }
  return { name, reason };
});
const failClose = registry.fail_close.map(({ name, reason_prefix: expected }) => {
  const reason = sceneExportSupportReason(failCloseFigure(name));
  if (reason === null || !reason.startsWith(expected)) {
    throw new Error(`${name} fail-close mismatch: expected ${expected}, got ${reason}`);
  }
  return { name, reason };
});

process.stdout.write(JSON.stringify({
  schema: "xyg.static-export-cross-host/v2",
  registry_schema: registry.schema,
  cases,
  edge_fail_close: edgeFailClose,
  fail_close: failClose,
}));
