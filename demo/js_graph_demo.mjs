// JavaScript force-directed org graph — same data/style as the Python demo.
//
//   XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.dylib node demo/js_graph_demo.mjs

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { resolveColorChannel } from "../packages/xy-node/src/color.js";
import { createEngine } from "../packages/xy-node/src/index.js";
import { writeGraphPage } from "./write_graph_page.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const DATA = JSON.parse(fs.readFileSync(path.join(here, "org_graph_data.json"), "utf8"));

const HIDDEN_AXIS = {
  axis_width: 0.0,
  axis_color: "#00000000",
  tick_length: 0.0,
  tick_width: 0.0,
  grid_opacity: 0.0,
  tick_label_color: "#00000000",
  label_color: "#00000000",
};

const nodes = DATA.nodes;
const edges = DATA.edges;
const teamColors = DATA.team_colors;
const relationColors = DATA.relation_colors;

const fig = createEngine({ width: 900, height: 640, title: null });
fig.graph(
  nodes.map((n) => n.id),
  edges.map((e) => [e.source, e.target]),
  {
    layout: DATA.layout,
    seed: DATA.seed,
    iterations: DATA.iterations,
    directed: true,
    edgeWidth: 3.2,
    size: 14,
    name: "org",
  },
);

const edgeTrace = fig.traces[fig.traces.length - 2];
const nodeTrace = fig.traces[fig.traces.length - 1];

edgeTrace.color = resolveColorChannel(
  edges.map((e) => relationColors[e.relation]),
  edges.length,
);
edgeTrace.style = { ...edgeTrace.style, width: 3.2, opacity: 0.9 };

nodeTrace.color = resolveColorChannel(
  nodes.map((n) => teamColors[n.team]),
  nodes.length,
);
nodeTrace.sizeValues = Float64Array.from(nodes, (n) => n.weight);
nodeTrace.sizeRange = [10, 24];
nodeTrace.style = {
  ...nodeTrace.style,
  opacity: 1.0,
  symbol: "circle",
  stroke: "#ffffff",
  stroke_width: 2.4,
};

nodeTrace.tooltip_rows = nodes.map((n) => ({
  label: n.label,
  id: n.id,
  role: n.role,
  team: n.team,
  weight: n.weight,
}));
edgeTrace.tooltip_rows = edges.map((e) => ({
  label: `${e.source} → ${e.target}`,
  source: e.source,
  target: e.target,
  relation: e.relation,
  weight: e.weight,
}));

const xs = nodeTrace.x;
const ys = nodeTrace.y;
let xmin = Infinity;
let xmax = -Infinity;
let ymin = Infinity;
let ymax = -Infinity;
for (let i = 0; i < xs.length; i++) {
  xmin = Math.min(xmin, xs[i]);
  xmax = Math.max(xmax, xs[i]);
  ymin = Math.min(ymin, ys[i]);
  ymax = Math.max(ymax, ys[i]);
}
const cx = (xmin + xmax) * 0.5;
const cy = (ymin + ymax) * 0.5;
const radius = Math.max(xmax - xmin, ymax - ymin) * 0.5 * 1.28;
const domain = [cx - radius, cx + radius];
fig.setAxisDomain("x", domain);
fig.setAxisDomain("y", domain);

const { spec, buffers } = fig.buildPayload();
spec.padding = [28, 28, 28, 28];
spec.title = null;
spec.x_axis = { ...(spec.x_axis || {}), range: domain, domain, style: { ...HIDDEN_AXIS } };
spec.y_axis = { ...(spec.y_axis || {}), range: domain, domain, style: { ...HIDDEN_AXIS } };
spec.axes = { x: spec.x_axis, y: spec.y_axis };
spec.interaction = { hover: true, click: true };
spec.show_legend = false;
spec.tooltip = {
  title: "{label}",
  fields: ["role", "team", "weight", "source", "target", "relation"],
  labels: {
    role: "Role",
    team: "Team",
    weight: "Weight",
    source: "From",
    target: "To",
    relation: "Relation",
  },
};
spec.annotations = nodes.map((n, i) => ({
  kind: "text",
  x: xs[i],
  y: ys[i],
  text: n.label,
  dx: 12,
  dy: 0,
  anchor: "start",
  style: { color: "#0f172a", font_size: 13, font_weight: 600 },
}));

const blob = Buffer.isBuffer(buffers)
  ? buffers
  : Buffer.concat(buffers.map((b) => Buffer.from(b.buffer, b.byteOffset, b.byteLength)));

const out = path.join(here, "js_graph_demo.html");
writeGraphPage({
  outPath: out,
  title: `${DATA.title} (JavaScript)`,
  host: "JavaScript host",
  spec,
  blob,
  meta: { team_colors: teamColors, relation_colors: relationColors },
});
console.log(`wrote ${out} (${(fs.statSync(out).size / 1024).toFixed(0)} KiB)`);
