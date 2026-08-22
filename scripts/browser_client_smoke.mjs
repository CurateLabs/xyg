#!/usr/bin/env node
/**
 * Browser-client smoke: assert the shared render client exports `render` /
 * `MARK_KINDS` (and standalone `window.xy`) with every expected wire kind.
 *
 * Prefers Playwright + Chromium when available; otherwise falls back to
 * `node --check` on the bundles plus a static parse of `MARK_KINDS` from
 * `js/src/55_marks.ts` and an ESM import of the host-neutral `index.js`.
 *
 * Usage:
 *   node scripts/browser_client_smoke.mjs
 */
import { spawnSync } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createServer } from "node:http";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const clientDir = join(root, "packages", "xy-client", "dist");
const staticDir = join(root, "python", "xyg", "static");
const standalonePath = join(clientDir, "standalone.js");
const indexPath = join(clientDir, "index.js");
const pyStandalonePath = join(staticDir, "standalone.js");
const pyIndexPath = join(staticDir, "index.js");
const marksSrcPath = join(root, "js", "src", "55_marks.ts");

/** Wire kinds Python `_emit_<kind>` can place on a trace (+ step/stairs aliases). */
const EXPECTED_MARK_KINDS = [
  "scatter",
  "line",
  "area",
  "bar",
  "column",
  "histogram",
  "box",
  "violin",
  "heatmap",
  "hexbin",
  "contour",
  "segments",
  "ribbon",
  "triangle_mesh",
  "errorbar",
  "error_band",
  "stem",
  "box_whisker",
  "box_median",
  "step",
  "stairs",
];

function fail(msg) {
  console.error(`browser_client_smoke: FAIL — ${msg}`);
  process.exit(1);
}

function ok(msg) {
  console.log(`browser_client_smoke: ok — ${msg}`);
}

function assertBundlesExist() {
  if (!existsSync(standalonePath) || !existsSync(indexPath)) {
    fail(
      `missing host-neutral bundles (run \`npm ci && node js/build.mjs\`)\n` +
        `  standalone: ${existsSync(standalonePath)}\n` +
        `  index: ${existsSync(indexPath)}`
    );
  }
  if (!existsSync(pyStandalonePath) || !existsSync(pyIndexPath)) {
    fail(
      `missing Python wheel copy of the client (js/build.mjs copies into python/xyg/static)\n` +
        `  standalone: ${existsSync(pyStandalonePath)}\n` +
        `  index: ${existsSync(pyIndexPath)}`
    );
  }
  for (const [label, a, b] of [
    ["index.js", indexPath, pyIndexPath],
    ["standalone.js", standalonePath, pyStandalonePath],
  ]) {
    const host = readFileSync(a);
    const py = readFileSync(b);
    if (Buffer.compare(host, py) !== 0) {
      fail(`python/xyg/static/${label} drifted from packages/xy-client/dist/${label}`);
    }
  }
  const nodeCheck = spawnSync(process.execPath, ["--check", standalonePath], {
    encoding: "utf8",
  });
  if (nodeCheck.status !== 0) {
    fail(`node --check standalone.js failed:\n${nodeCheck.stderr || nodeCheck.stdout}`);
  }
  ok("standalone.js parses (node --check)");
  ok("Python wheel copy matches host-neutral @curatelabs/xyg");
}

function parseMarkKindsFromSource() {
  const src = readFileSync(marksSrcPath, "utf8");
  const block = src.match(/export const MARK_KINDS\s*=\s*\{([\s\S]*?)\n\};/);
  if (!block) fail("could not locate MARK_KINDS in 55_marks.ts");
  const keys = [...block[1].matchAll(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:/gm)].map((m) => m[1]);
  return new Set(keys);
}

function assertMarkKinds(kinds, label) {
  const set = kinds instanceof Set ? kinds : new Set(kinds);
  const miss = EXPECTED_MARK_KINDS.filter((k) => !set.has(k));
  if (miss.length) fail(`${label} missing MARK_KINDS: ${miss.join(", ")}`);
  // Graph must not be a paint registry kind (geometry = segments + scatter).
  if (set.has("graph")) fail(`${label} unexpectedly registers wire kind "graph"`);
  ok(`${label} has ${EXPECTED_MARK_KINDS.length} expected mark keys`);
}

async function assertEsmImport() {
  const mod = await import(pathToFileURL(indexPath).href);
  if (typeof mod.default?.render !== "function" && typeof mod.render !== "function") {
    fail("ESM index.js missing default.render / render");
  }
  const kinds = mod.MARK_KINDS;
  if (!kinds || typeof kinds !== "object") fail("ESM index.js missing MARK_KINDS export");
  assertMarkKinds(new Set(Object.keys(kinds)), "ESM MARK_KINDS");
  ok("ESM import: render + MARK_KINDS present");
}

async function tryPlaywright() {
  const require = createRequire(import.meta.url);
  let chromium;
  try {
    ({ chromium } = require("playwright"));
  } catch {
    return false;
  }
  const standaloneJs = readFileSync(standalonePath, "utf8");
  const html = `<!doctype html><html><body>
<script>${standaloneJs}</script>
<script>
window.__xySmoke = {
  hasXy: typeof xy === "object" && xy !== null,
  hasRender: typeof xy?.render === "function" || typeof xy?.default?.render === "function",
  hasRenderStandalone: typeof xy?.renderStandalone === "function",
  markKeys: xy?.MARK_KINDS ? Object.keys(xy.MARK_KINDS) : [],
};
</script></body></html>`;

  const server = createServer((req, res) => {
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(html);
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  let browser;
  try {
    browser = await chromium.launch({
      headless: true,
      args: ["--disable-gpu", "--no-sandbox"],
    });
    const page = await browser.newPage();
    await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: "load", timeout: 30_000 });
    const result = await page.evaluate(() => window.__xySmoke);
    if (!result?.hasXy) fail("playwright: window.xy missing");
    if (!result.hasRender && !result.hasRenderStandalone) {
      fail("playwright: window.xy lacks render / renderStandalone");
    }
    assertMarkKinds(new Set(result.markKeys), "window.xy.MARK_KINDS");
    ok("playwright Chromium: window.xy + MARK_KINDS");
    return true;
  } catch (err) {
    console.warn(`browser_client_smoke: playwright path skipped (${err.message})`);
    return false;
  } finally {
    if (browser) await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

async function main() {
  assertBundlesExist();
  assertMarkKinds(parseMarkKindsFromSource(), "55_marks.ts");
  await assertEsmImport();
  const usedPw = await tryPlaywright();
  if (!usedPw) {
    // Fallback already covered by node --check + ESM; assert standalone text surface.
    const text = readFileSync(standalonePath, "utf8");
    if (!text.startsWith("var xy=")) fail("standalone.js must start with var xy=");
    for (const prop of ["renderStandalone", "MARK_KINDS", "render"]) {
      if (!text.includes(prop)) fail(`standalone.js text missing ${prop}`);
    }
    ok("standalone.js text surface (no playwright)");
  }
  console.log("browser_client_smoke: PASS");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
