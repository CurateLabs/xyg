#!/usr/bin/env node
// Hosted to_html() tick-asset smoke: Python writes sidecar worker/wasm files,
// this process serves them under a strict same-origin CSP, and Chromium
// proves attachWasmTicks admitted Rust ticks. No CDN, no path guessing.
import { spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const root = fileURLToPath(new URL("..", import.meta.url));
const directory = await mkdtemp(join(tmpdir(), "xyg-html-ticks-"));
const python = process.env.XYG_PYTHON || join(root, ".venv/bin/python");
const exportScript = `
import sys
from pathlib import Path
import xyg
dest = Path(sys.argv[1])
chart = xyg.chart(xyg.line([0.0, 1.0, 2.0, 3.0, 4.0], [0.0, 1.0, 0.0, 1.0, 0.0]), title="wasm ticks")
html = chart.to_html(dest / "chart.html", wasm_ticks=True)
if '"./wasm-worker.js"' not in html or "connect-src 'self'" not in html:
    raise SystemExit("to_html did not emit explicit tick asset URLs")
missing = chart.to_html(
    dest / "missing.html",
    wasm_ticks={"worker_url": "./wasm-worker.js", "wasm": "./missing.wasm"},
)
if '"./missing.wasm"' not in missing:
    raise SystemExit("fail-closed export did not keep the explicit missing WASM URL")
print("exported", dest / "chart.html")
`;
const exported = spawnSync(python, ["-c", exportScript, directory], {
  cwd: root,
  encoding: "utf8",
  env: { ...process.env, PYTHONPATH: join(root, "python") },
});
if (exported.status !== 0) {
  await rm(directory, { recursive: true, force: true });
  throw new Error(`to_html export failed: ${exported.stdout}\n${exported.stderr}`);
}

const probe = "globalThis.__xygStandaloneObserver=(e)=>{globalThis.__xygTickEvent=e;if(e.phase==='ticks_ready')document.title='xyg-ticks-ready';if(e.phase==='ticks_error')document.title='xyg-ticks-error:'+e.code;};\n  const spec = ";
for (const name of ["chart.html", "missing.html"]) {
  const html = await readFile(join(directory, name), "utf8");
  await writeFile(join(directory, name), html.replace("const spec = ", probe));
}

const allowed = new Set(["/chart.html", "/missing.html", "/wasm-worker.js", "/xyg-wasm.wasm"]);
const contentType = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".wasm": "application/wasm",
};
const csp = [
  "default-src 'none'",
  "script-src 'unsafe-inline' 'wasm-unsafe-eval'",
  "style-src 'unsafe-inline'",
  "worker-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
].join("; ");
const requests = [];
const server = createServer(async (request, response) => {
  const url = new URL(request.url, "http://127.0.0.1");
  requests.push(url.pathname);
  response.setHeader("Content-Security-Policy", csp);
  response.setHeader("Cache-Control", "no-store");
  if (!allowed.has(url.pathname)) {
    response.statusCode = 404;
    response.end("not found");
    return;
  }
  try {
    const path = join(directory, url.pathname.slice(1));
    const ext = path.slice(path.lastIndexOf("."));
    response.setHeader("Content-Type", contentType[ext] ?? "application/octet-stream");
    response.end(await readFile(path));
  } catch (error) {
    response.statusCode = 500;
    response.end(error instanceof Error ? error.message : String(error));
  }
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const address = server.address();
const origin = `http://127.0.0.1:${address.port}`;

async function runPage(page, path) {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.origin !== origin) errors.push(`external request ${request.url()}`);
  });
  await page.goto(`${origin}${path}`, { waitUntil: "domcontentloaded" });
  const title = await page.waitForFunction(
    () => {
      const value = String(document.title);
      return value.startsWith("xyg-ticks-") ? value : null;
    },
    undefined,
    { timeout: 20000 },
  ).then((handle) => handle.jsonValue());
  const event = await page.evaluate(() => globalThis.__xygTickEvent || null);
  const handle = await page.evaluate(() => {
    const ticks = globalThis.__xygWasmTicks;
    return ticks ? ticks.diagnostics() : null;
  });
  return { title, event, handle, errors };
}

const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.XYG_CHROMIUM || process.env.CHROMIUM || "/usr/bin/google-chrome-stable",
});
try {
  const page = await browser.newPage();
  const ready = await runPage(page, "/chart.html");
  if (ready.errors.length) throw new Error(`page errors: ${ready.errors.join(" | ")}`);
  if (ready.title !== "xyg-ticks-ready") throw new Error(`expected ticks-ready, got ${ready.title}`);
  if (ready.event?.phase !== "ticks_ready") throw new Error(`missing ticks_ready event: ${JSON.stringify(ready.event)}`);
  const axisIds = ready.handle?.axisIds || ready.event?.diagnostics?.axisIds;
  if (!Array.isArray(axisIds) || !axisIds.includes("x") || !axisIds.includes("y")) {
    throw new Error(`Rust tick admission missing primary axes: ${JSON.stringify(ready.handle)}`);
  }
  if (!requests.includes("/wasm-worker.js") || !requests.includes("/xyg-wasm.wasm")) {
    throw new Error(`explicit tick assets were not fetched: ${requests.join(",")}`);
  }
  const failed = await runPage(await browser.newPage(), "/missing.html");
  if (!String(failed.title).startsWith("xyg-ticks-error:")) {
    throw new Error(`missing WASM must fail closed, got ${failed.title}`);
  }
  console.log("hosted to_html WASM tick asset smoke passed");
} finally {
  await browser.close();
  server.close();
  await rm(directory, { recursive: true, force: true });
}
