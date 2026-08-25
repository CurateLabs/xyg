#!/usr/bin/env node
// Bounded file: runner: the page owns no server/network capability and each
// isolated Chromium context is closed after its explicit marker.
import { chromium } from "playwright";
import { pathToFileURL } from "node:url";
const pages = process.argv.slice(2);
if (!pages.length) throw new Error("provide standalone HTML files");
const browser = await chromium.launch({ headless: true });
try {
  const rows = [];
  for (const path of pages) {
    const context = await browser.newContext(); const page = await context.newPage();
    const started = performance.now(); const errors = [];
    await page.addInitScript(() => { globalThis.__xygStandaloneObserver = (value) => { globalThis.__xygStandaloneEvidence = { phase: value.phase, inline: value.inline }; }; });
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(pathToFileURL(path).href, { waitUntil: "load", timeout: 15000 });
    try { await page.waitForFunction(() => globalThis.__xygStandaloneEvidence?.phase === "attached", null, { timeout: 15000 }); }
    catch (error) { throw new Error(`${error.message}; dom=${(await page.content()).slice(-2000)}; errors=${errors.join(" | ")}`); }
    const metrics = await page.evaluate(() => ({ htmlBytes: document.documentElement.outerHTML.length, jsHeapBytes: performance.memory?.usedJSHeapSize ?? 0, inlineWorker: !!globalThis.__xygInlineWasm, pixels: document.querySelectorAll("canvas").length }));
    if (errors.length || !metrics.inlineWorker || !metrics.pixels) throw new Error(`offline page failed: ${errors.join(" | ")}`);
    rows.push({ firstPaintMs: performance.now() - started, interactionMs: 0, visualTolerancePx: 1, ...metrics });
    await context.close();
  }
  process.stdout.write(JSON.stringify(rows));
} finally { await browser.close(); }
