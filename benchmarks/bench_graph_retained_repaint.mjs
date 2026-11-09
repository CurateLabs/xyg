#!/usr/bin/env node
// Whole-command CodSpeed walltime: boot, authored graph, first paint, five
// identical accepted refreshes, readback validation and teardown. No peer/FPS claim.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const root = fileURLToPath(new URL("..", import.meta.url));
const count = Number(process.env.XYG_GRAPH_SCALE ?? 100000);
assert.ok([1000, 10000, 100000].includes(count));
// Paired runs may serve an immutable archived client while sharing this exact
// harness, Worker and WASM. Record the bytes actually served in either arm.
const clientPath = process.env.XYG_GRAPH_BENCH_CLIENT && resolve(process.env.XYG_GRAPH_BENCH_CLIENT);
const assetPath = path => path === "/packages/xy-client/dist/index.js" && clientPath
  ? clientPath : resolve(root, `.${path}`);
const errors = [];
const diagnostics = [];
const allowed = new Set([
  "/packages/xy-node/src/graphforge-container.js",
  "/packages/xy-client/dist/index.js",
  "/packages/xy-client/dist/wasm-worker.js",
  "/packages/xy-client/dist/xyg-wasm.wasm",
]);
const server = createServer(async (req, res) => {
  const path = new URL(req.url, "http://localhost").pathname;
  res.setHeader("Content-Security-Policy", "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self'; style-src 'unsafe-inline'; object-src 'none'; base-uri 'none'");
  if (path === "/") {
    res.setHeader("Content-Type", "text/html");
    res.end('<!doctype html><meta charset="utf-8"><div id="chart"></div>');
    return;
  }
  if (!allowed.has(path)) { res.writeHead(404).end(); return; }
  try {
    const bytes = await readFile(assetPath(path));
    res.setHeader("Content-Type", extname(path) === ".wasm" ? "application/wasm" : "text/javascript");
    res.end(bytes);
  } catch { res.writeHead(404).end(); }
});
await new Promise(r => server.listen(0, "127.0.0.1", r));
let browser;
try {
  browser = await chromium.launch({
    executablePath: process.env.XYG_CHROMIUM || process.env.CHROMIUM,
    args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
  });
  const page = await browser.newPage({ viewport: { width: 800, height: 600 }, reducedMotion: "reduce" });
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => {
    if (["warning", "error"].includes(message.type())) diagnostics.push(message.text());
  });
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  const result = await page.evaluate(async count => {
    const { attachWasmGraphSession, createXygWasmWorker } = await import("/packages/xy-client/dist/index.js");
    const { encodeContainer, decodeContainer, DTYPE } = await import("/packages/xy-node/src/graphforge-container.js");
    const plane = (name, dtype, values) => ({ name, dtype: DTYPE[dtype], values });
    const nodes = new Uint8Array(count * 16), edges = new Uint8Array(count * 16);
    for (let i = 0; i < count; i++) {
      new DataView(nodes.buffer).setUint32(i * 16, i + 1, true);
      new DataView(edges.buffer).setUint32(i * 16, i + 10001, true);
    }
    const documentBytes = encodeContainer("XYGF", [
      plane("status", "u32", [0]), plane("kind", "utf8", "graph"), plane("composition.version", "u32", [2]),
      plane("node.uuid", "uuid", nodes), plane("edge.uuid", "uuid", edges),
      plane("edge.derived", "u8", new Uint8Array(count)), plane("edge.layer", "u32", new Uint32Array(count).fill(0xffffffff)),
      plane("edge.order", "i64", new BigInt64Array(count).fill(-1n)), plane("edge.path", "u64", new BigUint64Array(count).fill(0xffffffffffffffffn)),
      plane("edge.source", "u64", BigUint64Array.from({ length: count }, (_, i) => BigInt(i))),
      plane("edge.target", "u64", BigUint64Array.from({ length: count }, (_, i) => BigInt((i + 1) % count))), plane("graph.directed", "u8", [0]),
    ]);
    const worker = createXygWasmWorker({
      workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm: "/packages/xy-client/dist/xyg-wasm.wasm", maxArenaBytes: 384 * 1024 * 1024,
    });
    const decoded = [];
    worker.worker.addEventListener("message", event => {
      const bytes = event.data.value?.bytes;
      if (!(bytes instanceof ArrayBuffer) || bytes.byteLength < 4 || new DataView(bytes).getUint32(0, true) !== 0x52475958) return;
      const sections = decodeContainer(new Uint8Array(bytes), "XYGR");
      const gpu = sections.get("gpu.header.u32#0")?.value;
      if (gpu) decoded.push({ gpu: [...gpu], sourceNodes: sections.get("node.flags.u32#0").value.length,
        sourceEdges: sections.get("edge.flags.u32#0").value.length, tier: sections.get("render.tier.u32#0").value[0],
        membership: sections.get("render.node_members.u64#0").value.length });
    });
    const el = document.querySelector("#chart"), publications = [], failures = [];
    el.addEventListener("xy:graph-render", e => publications.push(e.detail));
    el.addEventListener("xy:graph-error", e => failures.push(e.detail));
    let handle;
    try {
      await worker.ready;
      const x = Array.from({ length: count }, (_, i) => 130 * Math.cos(i * 2 * Math.PI / count));
      const y = Array.from({ length: count }, (_, i) => 130 * Math.sin(i * 2 * Math.PI / count));
      handle = attachWasmGraphSession({ el, worker, instanceId: 9101n, document: documentBytes,
        load: { x, y }, camera: [1, 1, 320, 160, 640, 320, 1] });
      await handle.ready;
      const pictures = [];
      for (let frame = 0; frame < 6; frame++) {
        if (frame) await handle.refreshRender();
        const canvas = el.querySelector("canvas");
        const rgba = canvas.getContext("2d").getImageData(0, 0, 640, 320).data;
        let pixels = 0, hash = 2166136261;
        for (let i = 0; i < rgba.length; i++) {
          hash = Math.imul(hash ^ rgba[i], 16777619) >>> 0;
          if (i % 4 === 3 && rgba[i] > 0) pixels++;
        }
        const digest = await crypto.subtle.digest("SHA-256", rgba);
        const sha256 = [...new Uint8Array(digest)].map(v => v.toString(16).padStart(2, "0")).join("");
        pictures.push({ pixels, rgbaHash: hash, sha256 });
      }
      const snapshot = handle.snapshot();
      const report = { count, pictures, decoded, publications: publications.length,
        camera: [...snapshot.camera], relayout: snapshot.relayout, failures };
      await handle.dispose();
      if (handle.snapshot() !== null || el.querySelector("canvas")) throw Error("retained owner survived disposal");
      return report;
    } finally { await handle?.dispose(); await worker.dispose(); }
  }, count);
  assert.equal(result.count, count);
  assert.equal(result.publications, 6, "initial paint and five accepted refreshes");
  assert.equal(result.relayout, null, "authored positions require no force continuation");
  assert.equal(result.decoded.length, 6);
  for (const decoded of result.decoded) {
    assert.equal(decoded.tier, 0, "Direct rendering");
    assert.equal(decoded.gpu[2], count, "every source node is rendered");
    assert.equal(decoded.sourceNodes, count);
    assert.equal(decoded.sourceEdges, count);
    assert.equal(decoded.membership, count);
  }
  assert.equal(result.pictures.length, 6);
  for (const picture of result.pictures) {
    assert.ok(picture.pixels > 3000, "useful paint");
    assert.deepEqual(picture, result.pictures[0], "identical repeated paint");
  }
  assert.deepEqual(result.failures, []);
  assert.deepEqual(errors, []);
  if (process.env.XYG_GRAPH_BENCH_REPORT) {
    const artifacts = {};
    for (const path of [...allowed].filter(p => p.includes("xy-client"))) {
      const bytes = await readFile(assetPath(path));
      artifacts[path] = { bytes: bytes.length, sha256: createHash("sha256").update(bytes).digest("hex") };
    }
    await writeFile(process.env.XYG_GRAPH_BENCH_REPORT, JSON.stringify({ schema: "xyg.retained-repaint/v1", node: process.version, browser: browser.version(), result, artifacts }, null, 2) + "\n");
  }
  console.log(`PASS retained ${count} initial + five refreshes; rgba=${result.pictures[0].rgbaHash}; disposed`);
} catch (error) {
  console.error(JSON.stringify({ errors, diagnostics }));
  throw error;
} finally { await browser?.close(); await new Promise(r => server.close(r)); }
