#!/usr/bin/env node
import { createServer } from "node:http";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { basename, dirname, extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const root = normalize(join(fileURLToPath(new URL(".", import.meta.url)), ".."));
const browserPackage = process.env.XYG_BROWSER_DIST ? resolve(process.env.XYG_BROWSER_DIST) : null;
const browserDist = browserPackage ? join(browserPackage, "dist") : join(root, "packages/xy-client/dist");
const reportPath = process.env.XYG_WASM_FOUNDATION_REPORT ? resolve(process.env.XYG_WASM_FOUNDATION_REPORT) : null;
const only = process.env.XYG_WASM_FOUNDATION_ONLY ?? "";
if (only && only !== "density-no-refinement") throw new Error("XYG_WASM_FOUNDATION_ONLY only accepts density-no-refinement");
const artifactCommit = process.env.XYG_RELEASE_COMMIT ?? null;
if (artifactCommit !== null && !/^[0-9a-f]{40}$/.test(artifactCommit)) throw new Error("XYG_RELEASE_COMMIT must be a complete lowercase Git SHA");
const allowed = new Set([
  "/tests/browser/wasm_foundation_page.mjs",
  "/spec/wasm/abi.json",
  "/tests/fixtures/figure_scene_v3.json",
  "/tests/fixtures/authored_scene_v20.json",
  "/tests/fixtures/xyts_cross_host.json",
  "/tests/fixtures/painter_admission_cross_host.json",
  "/tests/fixtures/packed_ticks_cross_host.json",
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
// Hold the ABI manifest until the harness observes navigation without the
// module's foundation promise. This deterministically exercises top-level-await
// startup rather than relying on network timing on one machine.
let releaseManifest;
const manifestGate = new Promise(resolve => { releaseManifest = resolve; });
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
    const bytes = await readFile(path);
    if (url.pathname === "/spec/wasm/abi.json") await manifestGate;
    response.end(bytes);
  } catch (error) {
    response.statusCode = 500;
    response.end(error instanceof Error ? error.message : String(error));
  }
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const address = server.address();
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.XYG_CHROMIUM || undefined,
});
try {
  const page = await browser.newPage();
  const external = [];
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.hostname !== "127.0.0.1") external.push(request.url());
  });
  const manifestRequested = page.waitForRequest(
    request => new URL(request.url()).pathname === "/spec/wasm/abi.json",
  );
  await page.goto(`http://127.0.0.1:${address.port}/${only ? `?only=${only}` : ""}`, { waitUntil: "commit" });
  await manifestRequested;
  if (await page.evaluate(() => globalThis.__xygWasmFoundation) !== undefined) {
    throw new Error("delayed manifest did not exercise asynchronous foundation startup");
  }
  releaseManifest();
  await page.waitForFunction(() => typeof globalThis.__xygWasmFoundation?.then === "function",
    null, { timeout: 60_000 });
  let timeout;
  let result;
  try {
    result = await Promise.race([
      page.evaluate(async () => globalThis.__xygWasmFoundation),
      new Promise((_, reject) => {
        timeout = setTimeout(() => reject(new Error("browser foundation smoke timed out")), 60_000);
      }),
    ]);
  } finally {
    clearTimeout(timeout);
  }
  if (pageErrors.length) throw new Error(`browser page errors: ${pageErrors.join(" | ")}`);
  if (!result?.ok) throw new Error(result?.error ?? "browser foundation smoke failed");
  if (!only && (!Array.isArray(result.densityPolicy) || result.densityPolicy.length !== 2)) {
    throw new Error("browser foundation smoke omitted massive density policy evidence");
  }
  if (!only) console.log(`direct-browser density policy ${JSON.stringify(result.densityPolicy)}`);
  await page.addScriptTag({ url: `http://127.0.0.1:${address.port}/packages/xy-client/dist/standalone.js` });
  if (!await page.evaluate(() => typeof globalThis.xy?.renderStandalone === "function" && typeof globalThis.xy?.decodeFrame === "function" && typeof globalThis.xy?.attachWasmTicks === "function")) throw new Error("published standalone IIFE did not expose window.xy");
  const iifeNoRefinement = await page.evaluate(async () => globalThis.__xygDensityNoRefinementIife());
  if (!Array.isArray(iifeNoRefinement) || iifeNoRefinement.length !== 3) throw new Error("standalone IIFE omitted density no-refinement evidence");
  if (external.length) throw new Error(`unexpected external requests: ${external.join(", ")}`);
  const known = new Set([
    "/", "/redirect.wasm", "/delayed.wasm", "/missing.wasm",
    "/await-delayed", "/release-delayed", ...allowed,
  ]);
  const unknown = requests.filter((path) => !known.has(path));
  if (unknown.length) throw new Error(`unexpected asset lookup: ${unknown.join(", ")}`);
  if (!Array.isArray(result.densityNoRefinement) || result.densityNoRefinement.length !== 3) {
    throw new Error("browser foundation smoke omitted density no-refinement evidence");
  }
  if (reportPath) {
    await mkdir(dirname(reportPath), { recursive: true });
    const assets = {};
    for (const name of packagedAssets.values()) {
      const bytes = await readFile(join(browserDist, name));
      assets[name] = { bytes: bytes.length, sha256: createHash("sha256").update(bytes).digest("hex") };
    }
    const harness = {};
    for (const name of ["scripts/wasm_foundation_smoke.mjs", "tests/browser/wasm_foundation_page.mjs", "spec/wasm/abi.json"]) {
      harness[name] = createHash("sha256").update(await readFile(join(root, name))).digest("hex");
    }
    const cases = [];
    for (const { pngBase64, ...scenario } of [...result.densityNoRefinement, ...iifeNoRefinement]) {
      const screenshot = `${reportPath}.${scenario.entry}-${scenario.name}.png`;
      const bytes = Buffer.from(pngBase64, "base64");
      await writeFile(screenshot, bytes);
      cases.push({ ...scenario, screenshot: { file: basename(screenshot), sha256: createHash("sha256").update(bytes).digest("hex") } });
    }
    const report = {
      schemaVersion: 1, status: "passed", scope: only || "full-foundation", recordedAt: new Date().toISOString(),
      artifactCommit, harnessCommit: execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim(),
      node: process.version, browser: browser.version(), platform: process.platform, architecture: process.arch,
      artifactSource: browserPackage ? "staged-package" : "source-dist", assets, harness,
      package: browserPackage ? JSON.parse(await readFile(join(browserPackage, "package.json"), "utf8")).version : null,
      csp, externalRequests: external, densityNoRefinement: cases,
      limitations: [
        "Three bounded generated-file cases through each packaged ESM/IIFE entry: absent inline bootstrap, malformed inline bootstrap rejected before Worker allocation, and absent retained source.",
        "Rust produces the overview through the packaged XYAG/XYAO Worker; fixture framing supplies the painter envelope.",
        "No actual packaged Reflex XYChart application, full candidate host matrix, large-scale timings, or validly framed corrupt inline WASM claim.",
      ],
    };
    await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`);
    console.log(`density no-refinement evidence retained: ${reportPath}`);
  }
  console.log(`strict-CSP local-only WASM ${only || "worker lifecycle"} smoke passed (${browserPackage ? "staged package" : "source dist"})`);
} finally {
  releaseManifest();
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
