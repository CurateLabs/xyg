// Verification helper: open the generated demo pages in headless Chromium and
// screenshot them so the render path can be checked without a display.
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const here = path.dirname(fileURLToPath(import.meta.url));
const pages = ["python_demo.html", "js_demo.html"];

const browser = await chromium.launch();
for (const file of pages) {
  const page = await browser.newPage({ viewport: { width: 1100, height: 640 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  await page.goto("file://" + path.join(here, file));
  await page.waitForTimeout(2500);
  const shot = path.join(here, file.replace(".html", ".png"));
  await page.screenshot({ path: shot });
  console.log(`${file}: screenshot ${shot}${errors.length ? ` — ERRORS: ${errors.join(" | ")}` : " — no console errors"}`);
  await page.close();
}
await browser.close();
