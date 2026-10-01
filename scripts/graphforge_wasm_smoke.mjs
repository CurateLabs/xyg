#!/usr/bin/env node
// Strict-CSP browser smoke for direct-browser GraphForge compositions
// (spec/design/graphforge-compositions.md §6.3): the packaged Worker and WASM
// compose real GraphForge fixtures, paint the Rust Scene through WebGL, map
// every painted row back to a GraphForge UUID, route a pick as a
// `xy:graphforge-select` event, render a table as text, and surface a stale
// generation as its stable code. Uses the system Chrome when
// XYG_CHROMIUM (or CHROMIUM) is set.
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const root = normalize(join(fileURLToPath(new URL(".", import.meta.url)), ".."));
const allowed = (path) =>
  path === "/tests/browser/graphforge_wasm_page.mjs"
  || /^\/tests\/fixtures\/graphforge\/results\/[a-z0-9_-]+\.(arrow|json)$/.test(path)
  || ["/packages/xy-client/dist/index.js", "/packages/xy-client/dist/wasm-worker.js", "/packages/xy-client/dist/xyg-wasm.wasm"].includes(path);
const csp = [
  "default-src 'none'",
  "script-src 'self' 'wasm-unsafe-eval'",
  "worker-src 'self'",
  "connect-src 'self'",
  "style-src 'unsafe-inline'",
  "object-src 'none'",
  "base-uri 'none'",
].join("; ");
const types = { ".js": "text/javascript", ".mjs": "text/javascript", ".wasm": "application/wasm", ".json": "application/json", ".arrow": "application/octet-stream" };
const served = [];
const server = createServer(async (request, response) => {
  const url = new URL(request.url, "http://127.0.0.1");
  served.push(url.pathname);
  response.setHeader("Content-Security-Policy", csp);
  if (url.pathname === "/") {
    response.setHeader("Content-Type", "text/html");
    response.end('<!doctype html><meta charset="utf-8"><script type="module" src="/tests/browser/graphforge_wasm_page.mjs"></script>');
    return;
  }
  if (!allowed(url.pathname)) { response.statusCode = 404; response.end(); return; }
  try {
    const body = await readFile(join(root, url.pathname));
    response.setHeader("Content-Type", types[extname(url.pathname)] ?? "application/octet-stream");
    response.end(body);
  } catch { response.statusCode = 404; response.end(); }
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const { port } = server.address();
const executablePath = process.env.XYG_CHROMIUM ?? process.env.CHROMIUM;
const browser = await chromium.launch({ ...(executablePath ? { executablePath } : {}), args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const violations = [];
try {
  const page = await browser.newPage();
  page.on("console", (message) => { if (/Content Security Policy|Refused to/.test(message.text())) violations.push(message.text()); });
  await page.goto(`http://127.0.0.1:${port}/`);
  await page.waitForFunction(() => window.__graphforge != null, null, { timeout: 60_000 });
  const result = await page.evaluate(() => {
    const r = window.__graphforge;
    return JSON.parse(JSON.stringify(r, (_, v) => (typeof v === "bigint" ? v.toString() : v)));
  });
  if (process.env.XYG_GRAPHFORGE_SCREENSHOT) await page.screenshot({ path: process.env.XYG_GRAPHFORGE_SCREENSHOT, clip: { x: 0, y: 0, width: 660, height: 440 } });
  const fail = (message) => { throw new Error(`graphforge WASM smoke: ${message}\n${JSON.stringify(result).slice(0, 2000)}`); };
  if (!result.ok) fail(`render failed (${result.code})`);
  const expected = new Set([...result.nodes, ...result.edges]);
  for (const id of expected) if (!result.painted.includes(id)) fail("a composed node or relationship is not painted under its identity");
  if (result.derived === 0) fail("derived similarity edges are not painted");
  if (!result.nodes.includes(result.pick?.uuid) || result.pick.kind !== "node") fail("pick did not route a node UUID");
  if (!result.pick.layers.some((l) => l.resultId === "result-rank")) fail("pick lost its result provenance");
  if (result.tableRows < 1 || /<script|<img/.test(result.tableHtml)) fail("table did not render as text");
  if (result.staleCode !== "GF_COMPOSE_GENERATION_STALE") fail("stale generation code");
  if (!result.legend) fail("Rust legend text is missing");
  if (result.cancelCode !== "XYG_WASM_CANCELLED" || result.afterCancel !== result.nodes.length) fail("cancelled composition did not leave the worker ready");
  const diagnosticsText = JSON.stringify(result.diagnostics);
  for (const id of expected) if (diagnosticsText.includes(id)) fail("diagnostics leaked an identity");
  if (violations.length) fail(`CSP violations: ${violations.join(" | ")}`);
  const unexpected = served.filter((p) => p !== "/" && !allowed(p));
  if (unexpected.length) fail(`unexpected requests: ${unexpected.join(", ")}`);
  console.log(`graphforge WASM smoke: ${result.painted.length} identities painted, ${result.derived} derived rows, pick → node, table ${result.tableRows} rows, stale → ${result.staleCode}`);
} finally {
  await browser.close();
  server.close();
}
