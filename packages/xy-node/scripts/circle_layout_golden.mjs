#!/usr/bin/env node
/**
 * Emit JSON for a fixed 4-node circle graph — consumed by
 * tests/test_graph_node_parity.py for bit-identical Python↔Node goldens.
 *
 * Usage (from repo root):
 *   node packages/xy-node/scripts/circle_layout_golden.mjs
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const xyNode = await import(path.join(root, "packages/xy-node/src/index.js"));
const { normalizeGraphInputs, runLayout, PROTOCOL_VERSION, abiVersion, encodeF32Values } = xyNode;

const nodes = ["a", "b", "c", "d"];
const edges = [
  ["a", "b"],
  ["b", "c"],
  ["c", "d"],
  ["d", "a"],
];

const data = normalizeGraphInputs(nodes, edges);
const { nodePositions, edgeSegments, meta } = runLayout(data, {
  layout: "circle",
  seed: 1,
  includeCsr: true,
});

const xEnc = encodeF32Values(nodePositions.x, 0, -4, 4);
const yEnc = encodeF32Values(nodePositions.y, 0, -4, 4);

function f64Hex(arr) {
  const buf = Buffer.from(arr.buffer, arr.byteOffset, arr.byteLength);
  return buf.toString("hex");
}

function f32Hex(arr) {
  const buf = Buffer.from(arr.buffer, arr.byteOffset, arr.byteLength);
  return buf.toString("hex");
}

const out = {
  protocol: PROTOCOL_VERSION,
  abi_version: abiVersion(),
  layout: meta.layout,
  lod_tier: meta.lod_tier,
  source_n_nodes: meta.source_n_nodes,
  source_n_edges: meta.source_n_edges,
  n_nodes: meta.n_nodes,
  n_edges: meta.n_edges,
  x: [...nodePositions.x],
  y: [...nodePositions.y],
  x_f64_hex: f64Hex(nodePositions.x),
  y_f64_hex: f64Hex(nodePositions.y),
  x_f32_hex: f32Hex(xEnc.values),
  y_f32_hex: f32Hex(yEnc.values),
  x_encode_meta: xEnc.meta,
  y_encode_meta: yEnc.meta,
  member_of: [...meta.member_of].map(Number),
  edge_x0: [...edgeSegments.x0],
  edge_y0: [...edgeSegments.y0],
  edge_x1: [...edgeSegments.x1],
  edge_y1: [...edgeSegments.y1],
};

process.stdout.write(`${JSON.stringify(out)}\n`);
