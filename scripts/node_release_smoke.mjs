#!/usr/bin/env node
/** Clean-install smoke for one exact-platform @curatelabs/xyg-node release set. */

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

import {
  PROTOCOL_VERSION,
  abiVersion,
  nativeLibraryPath,
  scatterChart,
  toHtml,
} from "@curatelabs/xyg-node";

const expectedPlatform = process.env.XYG_EXPECTED_NODE_PLATFORM;
if (!expectedPlatform) {
  throw new Error("XYG_EXPECTED_NODE_PLATFORM is required (for example linux-x64)");
}
const actualPlatform = `${process.platform}-${process.arch}`;
assert.equal(actualPlatform, expectedPlatform, "release smoke ran on the wrong architecture");
const expectedAbi = Number.parseInt(process.env.XYG_EXPECTED_ABI ?? "", 10);
assert.ok(Number.isSafeInteger(expectedAbi), "XYG_EXPECTED_ABI is required");

const expectedPackage = `@curatelabs/xyg-node-${expectedPlatform}`;
const packageRoot = fs.realpathSync(
  path.join("node_modules", ...expectedPackage.split("/")),
);
const nativeRealPath = fs.realpathSync(nativeLibraryPath);
assert.equal(
  path.dirname(nativeRealPath),
  packageRoot,
  `native library must resolve only from ${expectedPackage}`,
);

assert.equal(abiVersion(), expectedAbi, "native and facade ABI versions must match");
const figure = scatterChart(
  new Float64Array([0, 1, 2]),
  new Float64Array([2, 1, 3]),
  { width: 320, height: 200, title: "XYG clean-install conformance" },
);
const payload = figure.buildPayload();
assert.equal(payload.spec.protocol, PROTOCOL_VERSION);
assert.equal(payload.spec.traces[0].kind, "scatter");
assert.ok(payload.buffers.length > 0, "Rust-owned figure payload must contain buffers");

const html = toHtml(figure);
assert.ok(html.startsWith("<!doctype html>"));
assert.ok(html.includes("xy.renderStandalone"));
assert.ok(html.includes("connect-src 'none'"));
assert.ok(html.includes("XYG clean-install conformance"));
assert.equal(
  /<(?:script|link|img)\b[^>]*(?:src|href)=["']https?:/i.test(html),
  false,
  "offline HTML must not fetch a network asset",
);

console.log(
  JSON.stringify({
    package: "@curatelabs/xyg-node",
    platformPackage: expectedPackage,
    nativeLibrary: path.basename(nativeRealPath),
    abi: expectedAbi,
    protocol: PROTOCOL_VERSION,
    payloadBytes: payload.buffers.length,
    htmlBytes: Buffer.byteLength(html),
  }),
);
