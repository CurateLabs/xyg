#!/usr/bin/env node
// Test-only offline capture with explicit page readiness and browser ownership.
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";
import { chromium } from "playwright";

const [executablePath, input, output] = process.argv.slice(2);
assert.ok(executablePath && input && output, "chromium, HTML and PNG paths are required");
const errors = [], requests = [];
const browser = await chromium.launch({ executablePath, args: [
  "--no-sandbox", "--disable-dev-shm-usage", "--no-proxy-server",
  "--host-resolver-rules=MAP * ~NOTFOUND",
] });
try {
  const page = await browser.newPage({ viewport: { width: 300, height: 250 }, deviceScaleFactor: 1 });
  page.on("pageerror", error => errors.push(error.message));
  await page.route(/^https?:/, route => { requests.push(route.request().url()); return route.abort(); });
  await page.goto(pathToFileURL(resolve(input)).href);
  await page.waitForFunction(() => document.documentElement.dataset.xyFrozenReady === "true"
    && window.__xyFrozenView?.gpuTraces?.length > 0);
  await page.screenshot({ path: resolve(output) });
  assert.deepEqual(errors, [], "offline frozen export page errors");
  assert.deepEqual(requests, [], "offline frozen export attempted network access");
  await page.evaluate(() => window.__xyFrozenView.destroy());
  await page.close();
  console.log(`Captured ready offline frozen painter with ${browser.version()}`);
} finally { await browser.close(); }
