#!/usr/bin/env node
// VS Code webview emulation for GraphForge compositions
// (spec/design/graphforge-compositions.md §6.4).
//
// A VS Code webview document and its resources live on different origins,
// scripts need the webview's nonce, and nothing may come from a CDN. This
// smoke reproduces that: the page is served from origin A with a nonce CSP;
// every asset (paint client, Worker source, WASM, payload, fixtures) comes
// from origin B. Two host paths render the same GraphForge result:
//
// 1. Native (extension host): Node composes with the C ABI and posts
//    `{spec, buffer}`; the webview calls `xy.renderStandalone`. A real click
//    on a node relays `{trace, index}` back and `graphforgePick` maps it to
//    the node UUID and result row.
// 2. Direct-browser WASM: the webview turns the packaged Worker source into a
//    Blob module Worker (resources are cross-origin, so `new Worker(url)`
//    cannot load them), passes the WASM bytes explicitly, and
//    `renderWasmGraphForge` dispatches `xy:graphforge-select` on a real click.
//
// Requires the native core (XYG_NATIVE_LIB) and `node js/build.mjs && npm run
// build:wasm`. Uses XYG_CHROMIUM / CHROMIUM when set.
import { randomBytes } from "node:crypto";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

import {
  composeGraphForge,
  graphforgePick,
  graphforgeWebviewPayload,
} from "../packages/xy-node/src/graphforge.js";
import { decodeTooltipRows } from "../packages/xy-node/src/tooltip-columns.js";

const root = normalize(join(fileURLToPath(new URL(".", import.meta.url)), ".."));
const results = join(root, "tests/fixtures/graphforge/results");
const manifest = JSON.parse(await readFile(join(results, "manifest.json"), "utf8"));
const generation = manifest.bases.cyclic.generation;
const arrow = (name) => readFile(join(results, `${name}.arrow`));

// Extension host: compose natively and prepare the webview payload.
const composition = composeGraphForge({
  base: { tables: [await arrow("base-cyclic-nodes"), await arrow("base-cyclic-edges")], generation },
  layers: [
    { result: await arrow("pagerank"), intent: "graph", generation, resultId: "result-rank" },
    { result: await arrow("louvain"), intent: "graph", generation, resultId: "result-community" },
  ],
});
const payload = graphforgeWebviewPayload(composition, { width: 560, height: 380, title: "Native host" });

const nonce = randomBytes(16).toString("base64");
const assets = new Map([
  ["/dist/index.js", ["packages/xy-client/dist/index.js", "text/javascript"]],
  ["/dist/wasm-worker.js", ["packages/xy-client/dist/wasm-worker.js", "text/javascript"]],
  ["/dist/xyg-wasm.wasm", ["packages/xy-client/dist/xyg-wasm.wasm", "application/wasm"]],
]);
const served = [];
const assetServer = createServer(async (request, response) => {
  const url = new URL(request.url, "http://127.0.0.1");
  served.push(url.pathname);
  // The webview resource origin answers the document origin's fetches.
  response.setHeader("Access-Control-Allow-Origin", "*");
  if (url.pathname === "/payload/spec.json") {
    response.setHeader("Content-Type", "application/json");
    response.end(JSON.stringify(payload.spec));
    return;
  }
  if (url.pathname === "/payload/buffer.bin") {
    response.end(Buffer.from(payload.buffer));
    return;
  }
  const fixture = /^\/fixtures\/([a-z0-9_-]+)\.arrow$/.exec(url.pathname);
  const asset = assets.get(url.pathname);
  try {
    if (fixture) {
      response.end(await arrow(fixture[1]));
    } else if (asset) {
      response.setHeader("Content-Type", asset[1]);
      response.end(await readFile(join(root, asset[0])));
    } else {
      response.statusCode = 404;
      response.end();
    }
  } catch {
    response.statusCode = 404;
    response.end();
  }
});
await new Promise((resolve) => assetServer.listen(0, "127.0.0.1", resolve));
const assetOrigin = `http://127.0.0.1:${assetServer.address().port}`;

// The webview CSP: VS Code's recommended shape (nonce scripts, resources only
// from the webview resource origin) plus the two additions the paint client
// needs: 'wasm-unsafe-eval' to compile WASM and blob: for the Worker.
const csp = [
  "default-src 'none'",
  `script-src 'nonce-${nonce}' ${assetOrigin} 'wasm-unsafe-eval'`,
  `style-src ${assetOrigin} 'unsafe-inline'`,
  `img-src ${assetOrigin} data: blob:`,
  `font-src ${assetOrigin}`,
  `connect-src ${assetOrigin}`,
  "worker-src blob:",
].join("; ");
const page = `<!doctype html><html><head><meta charset="utf-8"></head><body>
<div id="native"></div>
<div id="wasm"></div>
<script type="module" nonce="${nonce}">
const B = ${JSON.stringify(assetOrigin)};
window.__events = [];
for (const id of ["native", "wasm"]) Object.assign(document.getElementById(id).style, { width: "560px", height: "380px", position: "relative" });
try {
  const xy = await import(B + "/dist/index.js");
  // 1. Native host payload.
  const spec = await (await fetch(B + "/payload/spec.json")).json();
  const buffer = await (await fetch(B + "/payload/buffer.bin")).arrayBuffer();
  const native = document.getElementById("native");
  const nativeView = xy.renderStandalone(native, spec, buffer);
  native.addEventListener("xy:click", (e) => window.__events.push({ path: "native", trace: e.detail.trace, index: e.detail.index }));
  // 2. Direct-browser WASM in a Blob module Worker.
  const workerSource = await (await fetch(B + "/dist/wasm-worker.js")).text();
  const workerUrl = URL.createObjectURL(new Blob([workerSource], { type: "text/javascript" }));
  const wasm = new Uint8Array(await (await fetch(B + "/dist/xyg-wasm.wasm")).arrayBuffer());
  const worker = xy.createXygWasmWorker({ workerUrl, wasm, maxArenaBytes: 64 * 1024 * 1024 });
  await worker.ready;
  const bytes = async (name) => new Uint8Array(await (await fetch(B + "/fixtures/" + name + ".arrow")).arrayBuffer());
  const target = document.getElementById("wasm");
  const { view, composition } = await xy.renderWasmGraphForge({
    el: target, worker, width: 560, height: 380, title: "WASM host",
    input: {
      base: { tables: [await bytes("base-cyclic-nodes"), await bytes("base-cyclic-edges")], generation: ${JSON.stringify(generation)} },
      layers: [{ result: await bytes("pagerank"), intent: "graph", generation: ${JSON.stringify(generation)}, resultId: "result-rank" }],
    },
  });
  // Locate a node with the chart's own hit test (as a user would find one by
  // pointing); the smoke then clicks there with a real mouse event.
  const locate = (chart, isNode) => {
    chart._layout(); chart._drawNow();
    const rect = chart.canvas.getBoundingClientRect();
    for (let y = chart.plot.y; y < chart.plot.y + chart.plot.h; y += 2) {
      for (let x = chart.plot.x; x < chart.plot.x + chart.plot.w; x += 2) {
        // The click handler's own precedence: GPU pick, then CPU hover.
        const hit = chart._pickAt(x, y) || chart._hoverAt(x, y);
        if (hit && isNode(hit)) return { x: rect.left + x, y: rect.top + y, trace: hit.trace, index: hit.index, stableId: chart.sceneStableId?.(hit.trace, hit.index)?.toString() ?? null };
      }
    }
    return null;
  };
  window.__locateNative = (nodeTrace) => locate(nativeView, (hit) => hit.trace === nodeTrace);
  window.__locateWasm = () => locate(view, (hit) => {
    const id = view.sceneStableId(hit.trace, hit.index);
    return id != null && composition.identifyStableId(id)?.kind === "node";
  });
  view.root.addEventListener("xy:graphforge-select", (e) => window.__events.push({ path: "wasm", ...e.detail }));
  window.__wasmNodes = composition.nodeUuid;
  window.__ready = true;
} catch (error) {
  window.__failure = String(error?.code ?? "") + " " + String(error?.message ?? error);
}
</script></body></html>`;
const pageServer = createServer((request, response) => {
  response.setHeader("Content-Security-Policy", csp);
  response.setHeader("Content-Type", "text/html");
  response.end(page);
});
await new Promise((resolve) => pageServer.listen(0, "127.0.0.1", resolve));
const pageOrigin = `http://127.0.0.1:${pageServer.address().port}`;

const executablePath = process.env.XYG_CHROMIUM ?? process.env.CHROMIUM;
const browser = await chromium.launch({
  ...(executablePath ? { executablePath } : {}),
  args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
});
const violations = [];
const fail = (message) => { throw new Error(`graphforge webview smoke: ${message}`); };

/** Click a located node with real mouse events (hover, then click); returns the located hit. */
async function clickNode(tab, locate) {
  const point = await tab.evaluate(locate);
  if (!point) return null;
  await tab.mouse.move(point.x, point.y);
  await tab.waitForTimeout(100);
  await tab.mouse.click(point.x, point.y);
  return point;
}

try {
  const tab = await browser.newPage({ viewport: { width: 600, height: 820 } });
  tab.on("console", (message) => { if (/Content Security Policy|Refused to/.test(message.text())) violations.push(message.text()); });
  await tab.goto(pageOrigin);
  await tab.waitForFunction(() => window.__ready || window.__failure, null, { timeout: 60_000 });
  const failure = await tab.evaluate(() => window.__failure ?? null);
  if (failure) fail(`webview script failed: ${failure}`);
  if (process.env.XYG_GRAPHFORGE_SCREENSHOT) await tab.screenshot({ path: process.env.XYG_GRAPHFORGE_SCREENSHOT });

  // 1. Native: a real click relays {trace, index}; the host maps it.
  const nodeTrace = payload.nodeTrace;
  const nativeHit = await clickNode(tab, `window.__locateNative(${nodeTrace})`);
  if (!nativeHit) fail("no native node was located");
  await tab.waitForFunction(() => window.__events.some((e) => e.path === "native"), null, { timeout: 10_000 });
  const relayed = (await tab.evaluate(() => window.__events)).find((e) => e.path === "native");
  if (relayed.trace !== nativeHit.trace || relayed.index !== nativeHit.index) fail("the relayed click is not the located node");
  const identity = graphforgePick(payload.figure, composition, relayed);
  // Independent oracle: the tooltip row painted for that element names its UUID.
  const shown = decodeTooltipRows(payload.spec, payload.buffer, payload.spec.traces[nativeHit.trace])[nativeHit.index].id;
  if (identity?.kind !== "node" || identity.uuid !== shown) fail("native pick did not map to the clicked node's UUID");
  if (!identity.layers.some((l) => l.resultId === "result-rank") || !identity.layers.some((l) => l.resultId === "result-community")) {
    fail("native pick lost per-layer result rows");
  }

  // 2. WASM: a real click dispatches xy:graphforge-select in the webview.
  const wasmHit = await clickNode(tab, "window.__locateWasm()");
  if (!wasmHit) fail("no WASM node was located");
  await tab.waitForFunction(() => window.__events.some((e) => e.path === "wasm"), null, { timeout: 10_000 });
  const selected = (await tab.evaluate(() => window.__events)).find((e) => e.path === "wasm");
  const wasmNodes = await tab.evaluate(() => window.__wasmNodes);
  // Independent oracle: node i paints under stable ID 2^32 + i.
  const clicked = Number(BigInt(wasmHit.stableId) - (1n << 32n));
  if (selected.kind !== "node" || selected.index !== clicked || selected.uuid !== wasmNodes[clicked]) {
    fail("WASM pick did not dispatch the clicked node's UUID");
  }
  if (!selected.layers.some((l) => l.resultId === "result-rank")) fail("WASM pick lost its result row");

  if (violations.length) fail(`CSP violations: ${violations.join(" | ")}`);
  const allowed = new Set(["/dist/index.js", "/dist/wasm-worker.js", "/dist/xyg-wasm.wasm", "/payload/spec.json", "/payload/buffer.bin"]);
  const unexpected = served.filter((p) => !allowed.has(p) && !/^\/fixtures\/[a-z0-9_-]+\.arrow$/.test(p));
  if (unexpected.length) fail(`unexpected asset requests: ${unexpected.join(", ")}`);
  console.log(`graphforge webview smoke: nonce CSP, cross-origin local assets, Blob module Worker; native pick → ${identity.kind}, WASM pick → ${selected.kind}`);
} finally {
  await browser.close();
  assetServer.close();
  pageServer.close();
}
