/** Independent public Node authoring of every admitted/rejected arrow style (#1006).
 *
 * Reads `{cases: {name: style}}` on stdin and writes the Scene bytes and SVG (or
 * the stable error text) per case. Python authors the same cases through the
 * public composition API and asserts byte-identical Scenes. */
import { readFileSync } from "node:fs";
import { Figure, sceneSvg } from "../src/index.js";

const { cases } = JSON.parse(readFileSync(0, "utf8"));

function figure(style) {
  const fig = new Figure({
    width: 320, height: 240, title: "Panel", showLegend: false,
    xAxis: { domain: [0, 2], label: "Time" }, yAxis: { domain: [0, 4], label: "Value" },
  });
  fig.line([0, 1, 2], [1, 3, 2], { color: "#ef4444", width: 2 });
  fig.annotate({ kind: "arrow", x0: 0.4, y0: 3.4, x1: 1.5, y1: 1.2, style: { color: "#667085", width: 1.5, opacity: 1, ...style } });
  return fig;
}

const out = {};
for (const [name, style] of Object.entries(cases)) {
  try {
    const scene = figure(style).toScene();
    out[name] = { scene: Buffer.from(scene).toString("base64"), svg: sceneSvg(scene) };
  } catch (error) {
    out[name] = { error: String(error?.message ?? error) };
  }
}
process.stdout.write(JSON.stringify(out));
