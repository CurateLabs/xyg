#!/usr/bin/env node
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const root = normalize(join(fileURLToPath(new URL(".", import.meta.url)), ".."));
const allowed = new Set(["/tests/browser/wasm_scene_benchmark_page.mjs", "/packages/xy-client/dist/index.js", "/packages/xy-client/dist/wasm-worker.js", "/packages/xy-client/dist/xyg-wasm.wasm"]);
const server = createServer(async (request, response) => {
  const path = new URL(request.url, "http://127.0.0.1").pathname;
  response.setHeader("Content-Security-Policy", "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self'");
  if (path === "/") {
    response.setHeader("Content-Type", "text/html");
    response.end('<script type="module" src="/tests/browser/wasm_scene_benchmark_page.mjs"></script>');
    return;
  }
  if (!allowed.has(path)) { response.statusCode = 404; response.end("not found"); return; }
  try {
    const body = await readFile(join(root, path));
    response.setHeader("Content-Type", extname(path) === ".wasm" ? "application/wasm" : "text/javascript");
    response.end(body);
  } catch (cause) {
    response.statusCode = 500;
    response.end(`could not read ${path}: ${cause instanceof Error ? cause.message : String(cause)}`);
  }
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const browser = await chromium.launch({ headless: true, args: ["--enable-precise-memory-info"] });
const page = await browser.newPage();
try {
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  const rows = await Promise.race([
    page.evaluate(() => globalThis.__xygWasmSceneBenchmark),
    new Promise((_, reject) => setTimeout(() => reject(new Error("WASM Scene benchmark timed out")), 60_000)),
  ]);
  if (pageErrors.length) throw new Error(`benchmark page errors: ${pageErrors.join(" | ")}`);
  console.log(JSON.stringify({ schema: "xyg-wasm-scene-browser-v2", measurements: rows }, null, 2));
} finally {
  await Promise.race([
    (async () => { await page.close(); await browser.close(); })(),
    new Promise((resolve) => setTimeout(resolve, 3_000)),
  ]);
  server.closeAllConnections();
  await new Promise((resolve) => server.close(resolve));
}
process.exit(0);
