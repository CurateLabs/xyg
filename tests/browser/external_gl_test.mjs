#!/usr/bin/env node
// Real WebGL2 ownership proof plus locally supplied MapLibre 6.13.0 shell.
// npm ci && node js/build.mjs && npm run build:wasm first.
// XYG_MAPLIBRE_DIST=/path/to/maplibre-gl-6.13.0/package/dist node tests/browser/external_gl_test.mjs
import { createServer } from "node:http";
import { readFile, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "vite";
import { chromium } from "playwright";

const root = fileURLToPath(new URL("../../", import.meta.url));
const maplibre = process.env.XYG_MAPLIBRE_DIST;
if (!maplibre) throw Error("Supply local MapLibre 6.13.0 dist with XYG_MAPLIBRE_DIST; the product has no MapLibre dependency");
const version = JSON.parse(await readFile(join(maplibre, "../package.json"), "utf8")).version;
if (version !== "6.13.0") throw Error(`Expected MapLibre 6.13.0, got ${version}`);
const output = await mkdtemp(join(tmpdir(), "xyg-external-gl-"));
await build({ configFile: false, logLevel: "error", build: { outDir: output,
  lib: { entry: join(root, "tests/browser/external_gl_entry.ts"), formats: ["es"], fileName: () => "probe.js" }, minify: false } });
const files = new Map([
  ["/probe.js", join(output, "probe.js")],
  ["/page.mjs", join(root, "tests/browser/external_gl_page.mjs")],
  ["/wasm-worker.js", join(root, "packages/xy-client/dist/wasm-worker.js")],
  ["/xyg-wasm.wasm", join(root, "packages/xy-client/dist/xyg-wasm.wasm")],
  ["/maplibre-gl.mjs", join(maplibre, "maplibre-gl.mjs")],
  ["/maplibre-gl-shared.mjs", join(maplibre, "maplibre-gl-shared.mjs")],
  ["/maplibre-gl-worker.mjs", join(maplibre, "maplibre-gl-worker.mjs")],
]);
const csp = "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self'; style-src 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'none'";
const unexpected = [], violations = [];
const server = createServer(async (request, response) => {
  const path = new URL(request.url, "http://localhost").pathname;
  response.setHeader("Content-Security-Policy", csp);
  if (path === "/") {
    response.setHeader("Content-Type", "text/html");
    response.end('<!doctype html><meta charset="utf-8"><link rel="icon" href="data:,"><script type="module" src="/page.mjs"></script>');
    return;
  }
  if (!files.has(path)) { unexpected.push(path); response.writeHead(404).end(); return; }
  try {
    response.setHeader("Content-Type", extname(path) === ".wasm" ? "application/wasm" : "text/javascript");
    response.end(await readFile(files.get(path)));
  } catch (error) { response.writeHead(500).end(error.message); }
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
let browser;
try {
  const executablePath = process.env.XYG_CHROMIUM ?? process.env.CHROMIUM;
  browser = await chromium.launch({ ...(executablePath ? { executablePath } : {}), args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  const page = await browser.newPage({ viewport: { width: 1000, height: 800 } });
  page.on("console", m => { if (/Content Security Policy|Refused to/.test(m.text())) violations.push(m.text()); });
  page.on("pageerror", error => violations.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.waitForFunction(() => window.__externalGL != null, null, { timeout: 60000 });
  const result = await page.evaluate(() => window.__externalGL);
  if (!result.ok || violations.length || unexpected.length) throw Error(JSON.stringify({result,violations,unexpected}));
  console.log(`external GL smoke: ${JSON.stringify(result)}`);
} finally {
  await browser?.close(); server.close(); await rm(output, { recursive: true, force: true });
}
