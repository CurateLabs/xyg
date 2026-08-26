#!/usr/bin/env node
import { createServer } from "node:http";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const root = normalize(join(fileURLToPath(new URL(".", import.meta.url)), ".."));
const browserPackage = process.env.XYG_BROWSER_DIST ? resolve(process.env.XYG_BROWSER_DIST) : null;
const browserDist = browserPackage ? join(browserPackage, "dist") : join(root, "packages/xy-client/dist");
const allowed = new Set([
  "/tests/browser/wasm_foundation_page.mjs",
  "/tests/fixtures/figure_scene_v3.json",
  "/tests/fixtures/authored_scene_v20.json",
  "/tests/fixtures/xyts_cross_host.json",
  "/tests/fixtures/graphforge/semantic_compound.json",
  "/packages/xy-client/dist/index.js",
  "/packages/xy-client/dist/standalone.js",
  "/packages/xy-client/dist/wasm-worker.js",
  "/packages/xy-client/dist/xyg-wasm.wasm",
]);
const packagedAssets = new Map([
  ["/packages/xy-client/dist/index.js", "index.js"],
  ["/packages/xy-client/dist/standalone.js", "standalone.js"],
  ["/packages/xy-client/dist/wasm-worker.js", "wasm-worker.js"],
  ["/packages/xy-client/dist/xyg-wasm.wasm", "xyg-wasm.wasm"],
]);
const requests = [];
const delayedResponses = [];
const delayedWaiters = [];
const csp = [
  "default-src 'none'",
  "script-src 'self' 'wasm-unsafe-eval'",
  "worker-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
].join("; ");
const contentType = {
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".wasm": "application/wasm",
  ".json": "application/json",
};

if (browserPackage) {
  const manifest = JSON.parse(await readFile(join(browserPackage, "ASSET-MANIFEST.json"), "utf8"));
  if (manifest.schemaVersion !== 1 || manifest.package !== "@curatelabs/xyg" || !manifest.assets) throw new Error("published browser package has an invalid asset manifest");
  if (Object.keys(manifest.assets).sort().join(",") !== [...packagedAssets.values()].sort().join(",")) throw new Error("published browser package asset manifest does not describe the exact four artifacts");
  for (const name of packagedAssets.values()) {
    const payload = await readFile(join(browserDist, name));
    const entry = manifest.assets[name];
    if (!entry || entry.bytes !== payload.length || entry.sha256 !== createHash("sha256").update(payload).digest("hex")) throw new Error(`published browser package integrity mismatch for ${name}`);
  }
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url, "http://127.0.0.1");
  requests.push(url.pathname);
  response.setHeader("Content-Security-Policy", csp);
  response.setHeader("Cache-Control", "no-store");
  if (url.pathname === "/") {
    response.setHeader("Content-Type", "text/html");
    response.end('<!doctype html><script type="module" src="/tests/browser/wasm_foundation_page.mjs"></script>');
    return;
  }
  if (url.pathname === "/redirect.wasm") {
    response.statusCode = 302;
    response.setHeader("Location", "https://example.invalid/xyg-wasm.wasm");
    response.end();
    return;
  }
  if (url.pathname === "/delayed.wasm") {
    delayedResponses.push(response);
    for (const waiter of delayedWaiters.splice(0)) waiter.end("ready");
    return;
  }
  if (url.pathname === "/await-delayed") {
    if (delayedResponses.length) response.end("ready");
    else delayedWaiters.push(response);
    return;
  }
  if (url.pathname === "/release-delayed") {
    const bytes = await readFile(join(browserDist, "xyg-wasm.wasm"));
    for (const delayed of delayedResponses.splice(0)) {
      delayed.setHeader("Content-Type", "application/wasm");
      delayed.end(bytes);
    }
    response.end("released");
    return;
  }
  if (!allowed.has(url.pathname)) {
    response.statusCode = 404;
    response.end("not found");
    return;
  }
  try {
    const packaged = packagedAssets.get(url.pathname);
    const path = packaged ? join(browserDist, packaged) : join(root, url.pathname);
    response.setHeader("Content-Type", contentType[extname(path)] ?? "application/octet-stream");
    response.end(await readFile(path));
  } catch (error) {
    response.statusCode = 500;
    response.end(error instanceof Error ? error.message : String(error));
  }
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const address = server.address();
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const external = [];
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.hostname !== "127.0.0.1") external.push(request.url());
  });
  await page.goto(`http://127.0.0.1:${address.port}/`);
  const result = await Promise.race([
    page.evaluate(async () => globalThis.__xygWasmFoundation),
    new Promise((_, reject) => setTimeout(() => reject(new Error("browser foundation smoke timed out")), 20_000)),
  ]);
  if (pageErrors.length) throw new Error(`browser page errors: ${pageErrors.join(" | ")}`);
  if (!result?.ok) throw new Error(result?.error ?? "browser foundation smoke failed");
  await page.addScriptTag({ url: `http://127.0.0.1:${address.port}/packages/xy-client/dist/standalone.js` });
  if (!await page.evaluate(() => typeof globalThis.xy?.renderStandalone === "function" && typeof globalThis.xy?.decodeFrame === "function" && typeof globalThis.xy?.attachWasmTicks === "function")) throw new Error("published standalone IIFE did not expose window.xy");
  if (external.length) throw new Error(`unexpected external requests: ${external.join(", ")}`);
  const known = new Set([
    "/", "/redirect.wasm", "/delayed.wasm", "/missing.wasm",
    "/await-delayed", "/release-delayed", ...allowed,
  ]);
  const unknown = requests.filter((path) => !known.has(path));
  if (unknown.length) throw new Error(`unexpected asset lookup: ${unknown.join(", ")}`);
  console.log(`strict-CSP local-only WASM worker lifecycle smoke passed (${browserPackage ? "published package" : "source dist"})`);
} finally {
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
