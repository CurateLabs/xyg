// Verification helper: open the generated demo pages in headless Chromium and
// screenshot them so the render path can be checked without a display.
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const here = path.dirname(fileURLToPath(import.meta.url));
const pages = [
  "python_demo.html",
  "js_demo.html",
  "python_graph_demo.html",
  "js_graph_demo.html",
];

const browser = await chromium.launch();
let failed = false;
for (const file of pages) {
  const page = await browser.newPage({ viewport: { width: 1100, height: 640 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  const target = path.join(here, file);
  await page.goto("file://" + target);
  await page.waitForTimeout(2500);
  const shot = path.join(here, file.replace(/\.html$/i, ".png"));
  await page.screenshot({ path: shot });
  if (errors.length) {
    failed = true;
    console.error(`${file}: screenshot ${shot} — ERRORS: ${errors.join(" | ")}`);
  } else {
    console.log(`${file}: screenshot ${shot} — no console errors`);
  }
  await page.close();
}
await browser.close();
if (failed) process.exit(1);
