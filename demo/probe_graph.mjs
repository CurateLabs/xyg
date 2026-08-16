import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const here = path.dirname(fileURLToPath(import.meta.url));
const file = process.argv[2] || "python_graph_demo.html";
const url = "file://" + path.join(here, file);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
const logs = [];
page.on("console", (m) => logs.push(`[${m.type()}] ${m.text()}`));
page.on("pageerror", (e) => logs.push(`[pageerror] ${e}`));

await page.goto(url);
await page.waitForTimeout(2000);

await page.evaluate(() => {
  window.__xyProbe = { hover: [], click: [], leave: 0, errors: [] };
  const chart = document.getElementById("chart");
  chart.addEventListener("xy:hover", (e) => {
    window.__xyProbe.hover.push(e.detail?.row || null);
  });
  chart.addEventListener("xy:click", (e) => {
    window.__xyProbe.click.push(e.detail?.row || null);
  });
  chart.addEventListener("xy:leave", () => {
    window.__xyProbe.leave += 1;
  });
});

const rect = await page.evaluate(() => {
  const canvas = document.querySelector("#chart canvas");
  const r = canvas.getBoundingClientRect();
  return { left: r.left, top: r.top, width: r.width, height: r.height };
});

// Sweep the plot area.
for (let y = 0.15; y <= 0.85; y += 0.07) {
  for (let x = 0.15; x <= 0.85; x += 0.07) {
    await page.mouse.move(rect.left + rect.width * x, rect.top + rect.height * y);
    await page.waitForTimeout(15);
  }
}
await page.waitForTimeout(100);

// Click a few places that had hovers if any, else center grid.
const clickTargets = await page.evaluate(() => {
  const rows = window.__xyProbe.hover.filter(Boolean);
  return rows.length;
});

await page.mouse.click(rect.left + rect.width * 0.45, rect.top + rect.height * 0.45);
await page.waitForTimeout(100);
await page.mouse.click(rect.left + rect.width * 0.55, rect.top + rect.height * 0.4);
await page.waitForTimeout(100);
await page.mouse.click(rect.left + rect.width * 0.35, rect.top + rect.height * 0.55);
await page.waitForTimeout(200);

const result = await page.evaluate(() => {
  const p = window.__xyProbe;
  const uniqueHover = [];
  const seen = new Set();
  for (const row of p.hover) {
    if (!row) continue;
    const key = JSON.stringify(row);
    if (seen.has(key)) continue;
    seen.add(key);
    uniqueHover.push(row);
  }
  return {
    hoverCount: p.hover.length,
    leaveCount: p.leave,
    clickCount: p.click.length,
    uniqueHover: uniqueHover.slice(0, 8),
    clicks: p.click.slice(0, 8),
    propsClass: document.getElementById("props")?.className,
    propsText: document.getElementById("props")?.textContent?.slice(0, 240),
    pinText: document.getElementById("pin")?.textContent,
    canvasOk: !!document.querySelector("#chart canvas"),
    tooltipText: document.querySelector("[class*='tooltip']")?.textContent?.slice(0, 200) || null,
  };
});

console.log(JSON.stringify({ file, clickTargets, logs: logs.slice(0, 40), result }, null, 2));
await page.screenshot({ path: path.join(here, file.replace(".html", "_probe.png")) });
await browser.close();
