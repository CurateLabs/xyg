/**
 * Independent Node public authoring for the StaticDocument corpus.
 *
 * No stdin, Python Scene bytes, or serialized Python authoring objects are read.
 * Figure and staticDocumentEncode are public exports. Explicit envelope chrome
 * facts below are literal fixture authoring, not a reproduction of Python's
 * figure-to-document projection policy.
 */
import { createHash } from "node:crypto";

import {
  Figure,
  facetChart,
  sceneExportSupportReason,
  staticDocumentEncode,
  staticDocumentExport,
} from "../src/index.js";

const formats = ["svg", "png", "pdf", "jpeg", "webp"];

function panel({ width = 320, height = 240, title = null } = {}) {
  return new Figure({
    width,
    height,
    title,
    showLegend: false,
    xAxis: { domain: [0, 2], label: "Time", format: ".1f" },
    yAxis: { domain: [0, 4], label: "Value", format: ".1f" },
  });
}

function addLine(figure, name = null) {
  return figure.line([0, 1, 2], [1, 3, 2], {
    name, color: "#ef4444", width: 2, style: { opacity: 0.75, dash: [5, 3] },
  });
}

function addScatter(figure, name = null, symbol = "diamond") {
  return figure.scatter([0, 1, 2], [2, 1, 3], {
    name,
    style: {
      color: "#3987e5", size: 6, opacity: 0.8, symbol,
      stroke: "#123456", stroke_width: 1.5,
    },
  });
}

function single(name) {
  const figure = panel();
  let legend = null;
  const facts = { chromeMetrics: [12, 12, 4, 12, 12, 4], axisSides: [1, 1] };
  if (name === "styled_scatter") addScatter(figure);
  else if (name === "continuous_colorbar") {
    figure.scatter([0, 1, 2], [1, 3, 2], {
      color: [0, 0.5, 1], style: { size: 6 },
    });
    figure.setColorbar({
      domain: [0, 1], colormap: "viridis", orientation: "vertical",
      label: "Intensity", ticks: [0, 0.5, 1],
    });
  }
  else addLine(figure, name === "anchored_legend" ? "Trend" : null);
  if (name === "text_annotation") {
    figure.annotate({
      kind: "text", x: 1, y: 3, text: "peak < & >", dx: 0, dy: -6,
      anchor: "start", style: { color: "#654321" },
    });
    Object.assign(facts, {
      annotationFontSize: 12, annotationTextFlags: 0, annotationVerticalAlign: 0,
    });
  }
  if (name === "anchored_legend") {
    addScatter(figure, "Observed", "circle");
    legend = {
      loc: "upper right", anchor: [1, 1], ncols: 1, title: "Series",
      items: [
        { name: "Trend", kind: "line", style: {
          color: "#ef4444", width: 2, opacity: 0.75, dash: [5, 3],
        } },
        { name: "Observed", kind: "scatter", style: {
          color: "#3987e5", size: 6, opacity: 0.8, symbol: "circle",
          stroke: "#123456", stroke_width: 1.5,
        } },
      ],
    };
  }
  const reason = sceneExportSupportReason(figure);
  if (reason !== null) throw new Error(`${name}: ${reason}`);
  const scene = figure.toScene();
  return {
    scenes: [scene],
    document: staticDocumentEncode({
      width: 320, height: 240, legend,
      panels: [{ scene, x: 0, y: 0, width: 320, height: 240, ...facts }],
    }),
  };
}

function facets() {
  const a = panel({ width: 160, height: 160, title: "A" });
  const b = panel({ width: 160, height: 160, title: "B" });
  a.line([0, 1], [1, 3], { color: "#ef4444", width: 2 });
  b.line([0, 1], [2, 4], { color: "#ef4444", width: 2 });
  const authored = facetChart({
    panels: [a, b], cols: 2, gap: 12, shareX: false, shareY: false,
    width: 332, height: 160, title: "Panels & grid",
  });
  const scenes = authored.panels.map((figure) => figure.toScene());
  return {
    scenes,
    document: staticDocumentEncode({
      width: 332, height: 184, title: "Panels & grid", titleX: 166, titleY: 16,
      panels: scenes.map((scene, index) => ({
        scene, x: index === 0 ? 0 : 172, y: 24, width: 160, height: 160,
        chromeMetrics: [12, 12, 4, 12, 12, 4], axisSides: [1, 1],
        titleStyle: [14, "#262626"],
      })),
    }),
  };
}

function encoded(name, authored) {
  const outputs = {};
  for (const format of formats) {
    const bytes = Buffer.from(staticDocumentExport(authored.document, format, {
      scale: 1, quality: 90,
    }));
    outputs[format] = {
      sha256: createHash("sha256").update(bytes).digest("hex"), bytes: bytes.length,
      prefix: bytes.subarray(0, 16).toString("hex"),
    };
    if (format === "svg") outputs[format].text = bytes.toString("utf8");
  }
  return {
    name,
    scenes: authored.scenes.map((scene) => Buffer.from(scene).toString("base64")),
    document: Buffer.from(authored.document).toString("base64"),
    outputs,
  };
}

const cases = ["styled_line", "styled_scatter", "text_annotation", "anchored_legend",
  "continuous_colorbar", "facet_panels"].map((name) => {
    try { return encoded(name, name === "facet_panels" ? facets() : single(name)); }
    catch (error) { return { name, error: String(error.stack ?? error) }; }
  });
process.stdout.write(JSON.stringify({
  schema: "xyg.static-document-public-authored/v1",
  authoring: "independent Node literals; no input from Python",
  cases,
}));
