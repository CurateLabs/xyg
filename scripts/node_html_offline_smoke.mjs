// One-off bounded browser proof, not a stress/performance gate.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright";
import { Figure, toHtml } from "../packages/xy-node/src/index.js";

const [executablePath, evidenceDirectory] = process.argv.slice(2);
assert.ok(executablePath && evidenceDirectory, "Usage: node scripts/node_html_offline_smoke.mjs <Chromium> <evidence directory>");
fs.mkdirSync(evidenceDirectory, { recursive: true });
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "xy-node-html-"));
const figure = new Figure({ width: 900, height: 600, title: '</script><script>globalThis.exportInjection=true</script>' });
figure.setAxis("x", { type: "time" });
figure.line(Float64Array.of(Date.parse("2025-01-01T00:00:00Z"), Date.parse("2025-02-01T00:00:00Z"), Date.parse("2025-03-01T00:00:00Z")), Float64Array.of(1, 4, 2));
const payload = figure.buildPayload();
const documentPath = path.join(temporary, "temporal.html");
const html = toHtml(payload, documentPath);
const browser = await chromium.launch({ executablePath, headless: true,
  args: ["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
try {
  const context = await browser.newContext({ offline: true, viewport: { width: 1000, height: 700 } });
  const page = await context.newPage();
  const requests = [], errors = [];
  page.on("request", request => { if (/^https?:/.test(request.url())) requests.push(request.resourceType()); });
  page.on("pageerror", () => errors.push("script-error"));
  await page.addInitScript(() => {
    globalThis.__xygStandaloneObserver = event => { if (event.phase === "attached") globalThis.__offlineView = event.view; };
  });
  await page.goto(pathToFileURL(documentPath).href);
  await page.waitForFunction(() => globalThis.__offlineView && !document.getElementById("xy-status"), undefined, { timeout: 15000 });
  const actual = await page.evaluate(async () => {
    const view = globalThis.__offlineView, bytes = view._payload;
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    const labels = [...view.root.querySelectorAll("*")].filter(element => !element.childElementCount).map(element => element.textContent);
    return { spec: view.spec, payloadSha256: [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2, "0")).join(""),
      timeLabelCount: labels.filter(text => /Jan|Feb|Mar/.test(text)).length,
      injectionAbsent: globalThis.exportInjection === undefined, canvasCount: view.root.querySelectorAll("canvas").length };
  });
  assert.deepEqual(actual.spec, payload.spec);
  assert.equal(actual.payloadSha256, createHash("sha256").update(Buffer.from(payload.buffers)).digest("hex"));
  assert.ok(actual.timeLabelCount > 0 && actual.injectionAbsent && actual.canvasCount > 0);
  assert.deepEqual(requests, []);
  assert.deepEqual(errors, []);
  await page.screenshot({ path: path.join(evidenceDirectory, "temporal.png"), fullPage: true });
  fs.writeFileSync(path.join(evidenceDirectory, "offline.json"), JSON.stringify({ status: "passed", browserVersion: browser.version(),
    host: { platform: process.platform, arch: process.arch, nodeVersion: process.version },
    sourceHashes: Object.fromEntries(["../packages/xy-node/src/html.js", "../js/src/wasm_worker.ts", "../js/build.mjs"].map(file =>
      [file, createHash("sha256").update(fs.readFileSync(new URL(file, import.meta.url))).digest("hex")])),
    offline: true, specMatches: true, payloadMatches: true, timeLabelCount: actual.timeLabelCount,
    injectionAbsent: actual.injectionAbsent, httpRequests: requests.length, scriptErrors: errors.length,
    artifactSha256: createHash("sha256").update(html).digest("hex") }, null, 2) + "\n");
  console.log("Node standalone temporal HTML passed offline browser acceptance.");
} finally {
  await browser.close();
  fs.rmSync(temporary, { recursive: true, force: true });
}
