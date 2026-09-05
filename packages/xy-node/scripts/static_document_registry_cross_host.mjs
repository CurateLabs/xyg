/** Independent public Node authoring; consumes registry metadata, never Python Scene/input. */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import { Figure, staticDocumentEncode, staticDocumentExport } from "../src/index.js";

const registryPath = process.env.XYG_STATIC_EXPORT_REGISTRY ?? fileURLToPath(new URL("../../../tests/fixtures/static_export_support_registry.json", import.meta.url));
const registry = JSON.parse(readFileSync(registryPath, "utf8")).document;
const formats = ["svg", "png", "pdf", "jpeg", "webp"];
const options = {
  document_title_x_center: [{}, {}],
  document_panel_colorbar_log_scale: [{ colorbarScale: "log" }, {}],
  document_panel_colorbar_extend_min: [{ colorbarExtend: "min" }, {}],
  document_panel_colorbar_extend_max: [{ colorbarExtend: "max" }, {}],
  document_panel_colorbar_pyplot_label: [{ colorbarPyplotLabel: true }, {}],
  document_colorbar_extend_both: [{ colorbarExtend: "both" }, {}],
  document_annotation_baseline: [{ annotationVerticalAlign: 0 }, {}],
  document_annotation_top: [{ annotationVerticalAlign: 1 }, {}],
  document_annotation_bottom: [{ annotationVerticalAlign: 2 }, {}],
  document_annotation_center: [{ annotationVerticalAlign: 3 }, {}],
  document_axis_sides_none: [{ axisSides: [0, 0] }, {}],
  document_axis_sides_low: [{ axisSides: [1, 1] }, {}],
  document_axis_sides_high: [{ axisSides: [2, 2] }, {}],
  document_axis_sides_both: [{ axisSides: [3, 3] }, {}],
  document_defaults: [{}, {}],
  document_background: [{}, { background: "#ddeeff80" }],
  document_optimized_png: [{}, { optimizePng: true }],
  document_tight_crop: [{}, { tightCrop: true, cropPadding: 3 }],
  document_panel_chrome: [{ chromeMetrics: [14, 16, 6, 13, 15, 5], axisSides: [3, 3] }, {}],
  document_annotation_style: [{ annotationFontSize: 15, annotationTextFlags: 3, annotationPadding: 5, annotationVerticalAlign: 3, arrowMetrics: [9, 2, 2] }, {}],
  document_panel_title: [{ titleStyle: [18, "#654321"] }, {}],
  document_title_start: [{}, { titleAnchor: 0, titleFlags: 0 }],
  document_title_middle: [{}, { titleAnchor: 1, titleFlags: 1 }],
  document_title_end: [{}, { titleAnchor: 2, titleFlags: 2 }],
  document_title_bold_italic: [{}, { titleFlags: 3 }],
  document_labels_start_top: [{}, {}],
  document_labels_middle_center: [{}, {}],
  document_labels_end_bottom: [{}, {}],
  document_labels_baseline_rotated: [{}, {}],
  document_legend: [{}, {}],
  document_signed_panels: [{}, {}],
  document_overlap: [{}, {}],
  document_colorbar_vertical: [{ colorbarLayout: [0.75, 0.5, 0.5] }, {}],
  document_colorbar_horizontal: [{}, {}],
  document_shared_colorbar: [{}, { colorbar: "viridis" }],
  document_half_scale: [{}, {}],
  document_double_scale: [{}, {}],
  document_jpeg_quality_low: [{}, {}],
  document_jpeg_quality_high: [{}, {}],
};

function figure(name) {
  const fig = new Figure({ width: 320, height: 240, title: "Panel", showLegend: false,
    xAxis: { domain: [0, 2], label: "Time" }, yAxis: { domain: [0, 4], label: "Value" } });
  if (name.includes("colorbar") && name !== "document_shared_colorbar") {
    fig.scatter([0, 1, 2], [1, 3, 2], { color: [1, 10, 100], size: 6 });
    fig.setColorbar({ domain: [1, 100], colormap: "viridis", label: "Intensity",
      orientation: name.endsWith("horizontal") ? "horizontal" : "vertical", ticks: [1, 10, 100] });
  } else fig.line([0, 1, 2], [1, 3, 2], { color: "#ef4444", width: 2 });
  if (name.includes("annotation")) {
    fig.annotate({ kind: "text", x: 1, y: 3, text: "note < & >", dx: 0, dy: -6, anchor: "start", style: { color: "#654321", label_background: "#ffffff" } });
    fig.annotate({ kind: "arrow", x0: 0.5, y0: 1, x1: 1.5, y1: 2, style: { color: "#667085", width: 1.5, opacity: 1 } });
  }
  return fig;
}

function labels(name) {
  const [anchor, vertical_align] = {
    document_labels_start_top: ["start", "top"],
    document_labels_middle_center: ["middle", "center"],
    document_labels_end_bottom: ["end", "bottom"],
    document_labels_baseline_rotated: ["middle", "baseline"],
  }[name];
  return [{ text: "Label < & >", x: 0.5, y: 0.5, size: 14, color: "#654321", anchor,
    vertical_align, rotation: name.endsWith("rotated") ? 90 : 0, opacity: 0.6, font_style: "italic", weight: "bold" }];
}

function legend() {
  return { loc: "upper right", anchor: [0.9, 0.9], ncols: 2, title: "Kinds", items: [
    { name: "line", kind: "line", style: { color: "#123456", dash: true } },
    { name: "scatter", kind: "scatter", style: { color: "#654321", size: 7 } },
    { name: "patch", kind: "bar", style: { color: "#22aa44" } },
  ] };
}

function build(name) {
  const [panel, authored] = options[name];
  const document = { ...authored };
  if (name.startsWith("document_title_")) Object.assign(document, { title: "Document < & >", titleX: 160, titleY: 20 });
  if (name === "document_title_x_center") delete document.titleX;
  if (name.startsWith("document_labels_")) document.labels = labels(name);
  if (name === "document_legend") document.legend = legend();
  const fig = figure(name);
  const scene = fig.toScene();
  let panels = [{ scene, x: 0, y: 0, width: 320, height: 240, ...panel }];
  if (["document_signed_panels", "document_overlap"].includes(name)) {
    panels = [{ scene, x: -5, y: 0, width: 320, height: 240 },
      { scene, x: name.endsWith("overlap") ? 150 : 320, y: 10, width: 320, height: 240 }];
  }
  return { document: staticDocumentEncode({ panels, width: name === "document_title_x_center" ? 321 : panels.length === 2 ? 640 : 320,
    height: panels.length === 2 ? 260 : 240, ...document }),
    scenes: panels.map(() => scene), sceneRaster: panels.map(() => fig.toSceneRasterCommands()),
    scale: name === "document_half_scale" ? 0.5 : name === "document_double_scale" ? 2 : 1,
    quality: name === "document_jpeg_quality_low" ? 1 : name === "document_jpeg_quality_high" ? 100 : 90 };
}

const rejectionNames = ["header_truncated", "version_unknown", "header_flags_unknown", "header_reserved_nonzero", "panels_empty", "dimensions_zero", "panel_flags_unknown", "panel_inactive_nonzero", "panel_ranges_overlap", "panel_scene_corrupt", "title_invalid_utf8", "title_nul", "title_anchor_unknown", "text_flags_unknown", "label_alignment_unknown", "label_opacity_invalid", "legend_kind_unknown", "legend_reserved_nonzero", "decoration_trailing_bytes", "document_trailing_bytes"];
function rejectedDocument(name) {
  const seed = name === "panel_ranges_overlap" ? "document_signed_panels" : name.startsWith("title_") ? "document_title_start" : name.startsWith("label_") || name === "decoration_trailing_bytes" ? "document_labels_start_top" : name.startsWith("legend_") ? "document_legend" : "document_defaults";
  let data = Buffer.from(build(seed).document);
  const count = data.readUInt32LE(20), titleLength = data.readUInt32LE(24);
  const decorations = 64 + count * 104 + titleLength;
  const sceneAt = decorations + data.readUInt32LE(52);
  if (name === "header_truncated") return data.subarray(0, 63);
  const offsets = { version_unknown: [4, 99], header_flags_unknown: [16, 16], header_reserved_nonzero: [60, 1], panels_empty: [20, 0], dimensions_zero: [8, 0], panel_flags_unknown: [88, 1 << 14], panel_inactive_nonzero: [96, 1], panel_ranges_overlap: [64 + 104 + 16, 0] };
  if (name in offsets) data.writeUInt32LE(offsets[name][1], offsets[name][0]);
  else if (name === "centered_title_x_nonzero") {
    data.writeUInt32LE(data.readUInt32LE(16) | 8, 16);
    data.writeFloatLE(1, 40);
  }
  else if (name === "panel_scene_corrupt") data[sceneAt] = 0;
  else if (["title_invalid_utf8", "title_nul"].includes(name)) data[64 + count * 104] = name.endsWith("utf8") ? 255 : 0;
  else if (name === "title_anchor_unknown") data[48] = 3;
  else if (name === "text_flags_unknown") data[49] = 4;
  else if (name === "label_alignment_unknown") data[decorations + 32 + 25] = 4;
  else if (name === "label_opacity_invalid") data.writeFloatLE(2, decorations + 32 + 16);
  else if (name === "legend_reserved_nonzero") data[decorations + 32 + 61] = 1;
  else if (name === "legend_kind_unknown") {
    const at = decorations + 32;
    data[at + 64 + data.readUInt32LE(at + 4) + data.readUInt32LE(at + 8)] = 3;
  } else if (name === "decoration_trailing_bytes") {
    data = Buffer.concat([data.subarray(0, sceneAt), Buffer.from([0]), data.subarray(sceneAt)]);
    data.writeUInt32LE(sceneAt - decorations + 1, 52);
  } else if (name === "document_trailing_bytes") data = Buffer.concat([data, Buffer.from([0])]);
  else throw new Error(name);
  return data;
}

assert.deepEqual(Object.keys(options).sort(), registry.cases.map(row => row.name).sort());
rejectionNames.push("centered_title_x_nonzero");
assert.deepEqual([...rejectionNames].sort(), [...registry.rejections].sort());
for (const row of registry.cases) assert.deepEqual(row.formats, formats);
const b64 = value => Buffer.from(value).toString("base64");
const cases = {};
for (const name of Object.keys(options)) {
  try {
    const built = build(name), outputs = {};
    for (const format of formats) {
      try { outputs[format] = b64(staticDocumentExport(built.document, format, { scale: built.scale, quality: built.quality })); }
      catch (error) { throw new Error(`${name}/${format}: ${error}`); }
    }
    cases[name] = { document: b64(built.document), scenes: built.scenes.map(b64), sceneRaster: built.sceneRaster.map(b64), outputs };
  } catch (error) { cases[name] = { error: String(error.stack ?? error) }; }
}
const rejections = {};
for (const name of rejectionNames) {
  const document = rejectedDocument(name), results = { document: b64(document) };
  for (const format of formats) {
    try { staticDocumentExport(document, format); results[format] = { rejected: false }; }
    catch (error) { results[format] = { rejected: true, error: String(error) }; }
  }
  rejections[name] = results;
}
process.stdout.write(JSON.stringify({ authoring: "independent-node-public-figure-explicit-xyst", cases, rejections }));
