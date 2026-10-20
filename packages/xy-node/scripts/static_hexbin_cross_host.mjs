#!/usr/bin/env node
/** Python/Node identity for static hexbin exports beyond 1,024 groups (#887). */

import { hexbinChart, sceneExportSupportReason } from "../src/index.js";

// Deterministic integer-derived cloud, identical in tests/test_static_hexbin_cross_host.py.
const N = 20000;
const X = Array.from({ length: N }, (_, i) => ((i * 7919) % 10007) / 10007);
const Y = Array.from({ length: N }, (_, i) => ((i * 104729) % 10009) / 10009);
// `color` keeps constant paint (no per-cell XYTA plane); `extra` adds a scatter
// trace so the mixed-document buffer sizing is exercised too (#887 review).
const CASES = [
  { name: "above_former_group_ceiling", gridsize: [40, 30] },
  { name: "default_gridsize_lattice", gridsize: [100, 100] },
  { name: "near_cell_ceiling", gridsize: [155, 155] },
  { name: "near_cell_ceiling_constant_color", gridsize: [155, 155], color: "#3987e5" },
  { name: "near_cell_ceiling_mixed", gridsize: [155, 155], color: "#3987e5", extra: 5000 },
  { name: "above_cell_ceiling", gridsize: [330, 330] },
];

const b64 = (bytes) => Buffer.from(bytes).toString("base64");
const cases = CASES.map(({ name, gridsize, color, extra }) => {
  const figure = hexbinChart(X, Y, { gridsize, width: 640, height: 480, ...(color ? { color } : {}) });
  if (extra) figure.setAxisDomain("x", [-0.2, 1.2]).setAxisDomain("y", [-0.2, 1.2]);
  if (extra) figure.scatter(X.slice(0, extra), Y.slice(0, extra), { color: "#ef4444", size: 3 });
  const reason = sceneExportSupportReason(figure);
  const row = { name, cells: figure.traces[0].x.length, reason: reason ?? null };
  if (reason === null || reason === undefined) {
    row.scene_svg_b64 = b64(Buffer.from(figure.toSceneSvg(), "utf8"));
    row.svg_b64 = b64(Buffer.from(figure.toSvg(), "utf8"));
    row.png_b64 = b64(figure.toPng({ scale: 1 }));
  }
  return row;
});
process.stdout.write(JSON.stringify({ schema: "xyg.static-hexbin-cross-host/v1", cases }));
