import { sceneFigureSupportPack, sceneXyafPack } from "../src/encode.js";
import { createHash } from "node:crypto";

const xyaf = sceneXyafPack({
  index: 0,
  kindCode: 0,
  axisCode: 0,
  symbol: 0,
  anchor: 255,
  facts: (1 << 5) | (1 << 6) | (1 << 1),
  styleBits: 1,
  linecap: 255,
  dashCount: 0,
  nums: [0.5, 0.25, ...Array(16).fill(Number.NaN)],
  color: Uint8Array.from([102, 112, 133, 255]),
  stroke: new Uint8Array(4),
  labelColor: new Uint8Array(4),
  labelFill: new Uint8Array(4),
  labelBorder: new Uint8Array(4),
  dash: new Float32Array(8),
  text: new TextEncoder().encode("hi"),
});

const fs = sceneFigureSupportPack({
  flags: 0,
  axesBlob: Uint8Array.from([
    0, 0, 0, 0, 2, 0, 0, 0, 5, 0, ...new TextEncoder().encode("label"), 4, 0, ...new TextEncoder().encode("side"),
  ]),
  tracesBlob: Uint8Array.from([0, 0, 7, 0, 0, 0, 0, 0, ...new TextEncoder().encode("scatter")]),
});

const sha = (buf) => createHash("sha256").update(buf).digest("hex");

process.stdout.write(JSON.stringify({
  xyaf_sha256: sha(xyaf),
  xyfs_sha256: sha(fs),
}) + "\n");
