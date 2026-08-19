#!/usr/bin/env node
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const root = normalize(join(fileURLToPath(new URL(".", import.meta.url)), ".."));
const allowed = new Set([
  "/tests/browser/wasm_foundation_page.mjs",
  "/packages/xy-client/dist/index.js",
  "/packages/xy-client/dist/wasm-worker.js",
  "/packages/xy-client/dist/xyg-wasm.wasm",
]);
const requests = [];
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
};

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
  if (!allowed.has(url.pathname)) {
    response.statusCode = 404;
    response.end("not found");
    return;
  }
  try {
    const path = join(root, url.pathname);
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
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.hostname !== "127.0.0.1") external.push(request.url());
  });
  await page.goto(`http://127.0.0.1:${address.port}/`);
  const result = await page.evaluate(async () => globalThis.__xygWasmFoundation);
  if (!result?.ok) throw new Error(result?.error ?? "browser foundation smoke failed");
  if (external.length) throw new Error(`unexpected external requests: ${external.join(", ")}`);
  const unknown = requests.filter((path) => path !== "/" && !allowed.has(path));
  if (unknown.length) throw new Error(`unexpected asset lookup: ${unknown.join(", ")}`);
  console.log("strict-CSP local-only WASM worker lifecycle smoke passed");
} finally {
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
