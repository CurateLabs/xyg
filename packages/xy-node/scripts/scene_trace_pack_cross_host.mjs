#!/usr/bin/env node
/**
 * Scene XYTC/XYTA trace-pack cross-host goldens — consumed by
 * tests/test_scene_trace_pack_abi.py.
 *
 * Usage (from repo root):
 *   node packages/xy-node/scripts/scene_trace_pack_cross_host.mjs
 */
import crypto from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const { Figure, abiVersion } = await import(path.join(root, "packages/xy-node/src/index.js"));
const { packFigureXyTa, packFigureXyTc } = await import(
  path.join(root, "packages/xy-node/src/scene.js"),
);

const HEXBIN_X = [0.5, 1.5, 2.5, 3.5, 1, 2, 3];
const HEXBIN_Y = [0.5, 0.5, 0.5, 0.5, 2, 2, 2];

function sha256(bytes) {
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

function packCase(name, figure) {
  const xytc = packFigureXyTc(figure);
  const xyta = packFigureXyTa(figure);
  return {
    name,
    xytc_sha256: sha256(xytc),
    xyta_sha256: sha256(xyta),
    xytc_magic: Buffer.from(xytc.subarray(0, 4)).toString("utf8"),
    xyta_magic: Buffer.from(xyta.subarray(0, 4)).toString("utf8"),
  };
}

function scatterStrokeFigure() {
  const figure = new Figure({ width: 320, height: 240 });
  figure.setAxisDomain("x", [0, 2]);
  figure.setAxisDomain("y", [0, 2]);
  figure.scatter([0.25, 1.75], [0.5, 1.5], {
    id: 41,
    name: "outlined",
    color: "#336699",
    opacity: 0.75,
    size: 12,
    symbol: "diamond",
    stroke: "#ff8800",
    strokeWidth: 3.5,
  });
  return figure;
}

function lineFigure() {
  const figure = new Figure({ width: 320, height: 240 });
  figure.setAxisDomain("x", [0, 4]);
  figure.setAxisDomain("y", [0, 5]);
  figure.line([0, 1, 2], [1, 3, 2], { id: 0, color: "#ef4444", width: 2 });
  return figure;
}

function hexbinFigure() {
  const figure = new Figure({ width: 320, height: 240 });
  figure.setAxisDomain("x", [0, 4]);
  figure.setAxisDomain("y", [0, 5]);
  figure.hexbin(HEXBIN_X, HEXBIN_Y, {
    gridsize: [4, 4],
    range: [[0, 4], [0, 5]],
    name: "hex",
    id: 0,
  });
  return figure;
}

function heatmapFigure() {
  const figure = new Figure({ width: 320, height: 240 });
  figure.setAxisDomain("x", [0, 4]);
  figure.setAxisDomain("y", [0, 5]);
  figure.heatmap([[0, 1, 2], [3, 4, 5]], {
    x: [1, 2, 3],
    y: [1, 3],
    color: "#3987e5",
    opacity: 0.75,
    name: "heat",
    id: 0,
  });
  return figure;
}

function ribbonFigure() {
  const figure = new Figure({ width: 320, height: 240 });
  figure.setAxisDomain("x", [0, 10]);
  figure.setAxis("y", { type: "linear", domain: [-10, 1000] });
  figure.ribbon([1], [9], [1], [10], [100], [1000], {
    id: 7,
    color: "#7c3aed",
    opacity: 0.75,
    strokeWidth: 2,
    style: { "fill-opacity": 0.8, "stroke-opacity": 0.5 },
  });
  return figure;
}

function meshFigure() {
  const figure = new Figure({ width: 360, height: 260 });
  figure.setAxisDomain("x", [0, 2]);
  figure.setAxisDomain("y", [0, 2]);
  figure.triangleMesh(
    [-0.25, 1],
    [0.25, 0.5],
    [0.75, 2.25],
    [0.25, 0.5],
    [0.25, 1.5],
    [1.25, 1.75],
    { id: 0, name: "literal mesh", color: "#22c55e", opacity: 0.75 },
  );
  return figure;
}

const cases = [
  packCase("scatter", scatterStrokeFigure()),
  packCase("line", lineFigure()),
  packCase("hexbin", hexbinFigure()),
  packCase("heatmap", heatmapFigure()),
  packCase("ribbon", ribbonFigure()),
  packCase("mesh", meshFigure()),
];

const out = {
  schema: "xyg.scene-trace-pack-cross-host/v1",
  authority: "python/xyg/_scene_v3.py _pack_xytc / _pack_xyta vs packages/xy-node/src/scene.js",
  abi_version: abiVersion(),
  cases,
};

process.stdout.write(`${JSON.stringify(out, null, 2)}\n`);
