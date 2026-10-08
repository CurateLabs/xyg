#!/usr/bin/env node
// Strict-CSP packaged Worker GeoColumn golden/ownership/error/lifecycle proof.
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const root = normalize(join(fileURLToPath(new URL(".", import.meta.url)), ".."));
const allowed = (path) =>
  path === "/tests/browser/geo_wasm_page.mjs"
  || path === "/tests/fixtures/geo_cross_host.json"
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
    response.end('<!doctype html><meta charset="utf-8"><script type="module" src="/tests/browser/geo_wasm_page.mjs"></script>');
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
  await page.waitForFunction(() => window.__geo != null, null, { timeout: 60_000 });
  const result = await page.evaluate(() => {
    const r = window.__geo;
    return JSON.parse(JSON.stringify(r, (_, v) => (typeof v === "bigint" ? v.toString() : v)));
  });
  const fail = (message) => { throw new Error(`geo WASM smoke: ${message}\n${JSON.stringify(result).slice(0, 2000)}`); };
  if (!result.ok) fail(`ingestion failed (${result.code})`);
  if (result.compared < 16 || result.stable !== "XYG_GEO_HOLE_OUTSIDE_SHELL" || result.cancel !== "XYG_WASM_CANCELLED" || result.disposed !== "XYG_WASM_DISPOSED") fail("golden/lifecycle contract");
  if (violations.length) fail(`CSP violations: ${violations.join(" | ")}`);
  const unexpected = served.filter((p) => p !== "/" && !allowed(p));
  if (unexpected.length) fail(`unexpected requests: ${unexpected.join(", ")}`);
  console.log(`geo WASM smoke: ${result.compared} byte-identical goldens, typed source preserved, request transferred, stable error, cancel/recovery/dispose; strict CSP`);
} finally {
  await browser.close();
  server.close();
}
