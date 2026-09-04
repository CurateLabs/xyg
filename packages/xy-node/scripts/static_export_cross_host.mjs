import { Figure, sceneExportSupportReason } from "../src/index.js";

function lineFigure() {
  const figure = new Figure({ width: 320, height: 240 });
  figure.line([0, 1, 2], [1, 3, 2], { id: 0, color: "#ef4444", width: 2 });
  return figure;
}

function scatterFigure() {
  const figure = new Figure({ width: 320, height: 240 });
  figure.scatter([0, 1, 2], [1, 3, 2], {
    id: 0,
    style: { color: "#3987e5", size: 6, opacity: 0.8, symbol: "diamond" },
  });
  return figure;
}

function barFigure() {
  const figure = new Figure({ width: 320, height: 240 });
  figure.bar([0, 1], [1, 2], { id: 0, color: "#22c55e", opacity: 0.85 });
  return figure;
}

function histogramFigure() {
  const figure = new Figure({ width: 320, height: 240 });
  figure.histogram([0, 1, 1, 2], {
    id: 0,
    bins: 2,
    color: "#7c3aed",
    opacity: 0.85,
  });
  return figure;
}

function missFigure() {
  const figure = lineFigure();
  figure.class_name = "browser-only";
  return figure;
}

function encodedCase(name, figure) {
  const reason = sceneExportSupportReason(figure);
  if (reason !== null) throw new Error(`${name} unexpectedly failed public preflight: ${reason}`);
  const scene = figure.toScene();
  return {
    name,
    reason,
    scene_b64: Buffer.from(scene).toString("base64"),
    svg_b64: Buffer.from(figure.toSceneSvg(), "utf8").toString("base64"),
    raster_b64: Buffer.from(figure.toSceneRasterCommands({ scale: 1 })).toString("base64"),
  };
}

const miss = missFigure();
const missReason = sceneExportSupportReason(miss);
if (missReason === null) throw new Error("browser-CSS miss unexpectedly entered the public route");

process.stdout.write(JSON.stringify({
  schema: "xyg.static-export-cross-host/v1",
  cases: [
    encodedCase("line", lineFigure()),
    encodedCase("scatter", scatterFigure()),
    encodedCase("bar", barFigure()),
    encodedCase("histogram", histogramFigure()),
  ],
  miss: { name: "browser_css", reason: missReason },
}));
