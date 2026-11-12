#!/usr/bin/env node
// Real Worker ownership and first publication during WebGL context replacement.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve, extname, dirname } from "node:path";
import { chromium } from "playwright";
const root = resolve(new URL("..", import.meta.url).pathname);
const reportPath = process.env.XYG_INITIAL_CONTEXT_REPORT;
const paths = new Set([
  "/tests/browser/temporal_graph_aggregate_page.mjs",
  "/packages/xy-node/src/graphforge-container.js",
  "/packages/xy-client/dist/index.js", "/packages/xy-client/dist/wasm-worker.js",
  "/packages/xy-client/dist/xyg-wasm.wasm",
]);
const server = createServer(async (request, response) => {
  const path = new URL(request.url, "http://localhost").pathname;
  response.setHeader("Content-Security-Policy", "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self'");
  if (path === "/") { response.setHeader("Content-Type", "text/html"); response.end('<!doctype html><script type="module" src="/tests/browser/temporal_graph_aggregate_page.mjs"></script>'); return; }
  if (!paths.has(path)) { response.statusCode = 404; response.end(); return; }
  try {
    const file = path === "/packages/xy-client/dist/index.js" && process.env.XYG_INITIAL_CONTEXT_CLIENT
      ? process.env.XYG_INITIAL_CONTEXT_CLIENT : resolve(root, "." + path);
    response.setHeader("Content-Type", extname(path) === ".wasm" ? "application/wasm" : "text/javascript");
    response.end(await readFile(file));
  } catch (error) { response.statusCode = 500; response.end(String(error)); }
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const browser = await chromium.launch({ headless: true, executablePath: process.env.XYG_CHROMIUM,
  args: ["--no-sandbox", "--disable-dev-shm-usage"] });
const evidence = { node: process.version, browser: browser.version(), cases: [] };
try {
  for (const mode of ["temporal", "ordinary", "repeated-loss", "mid-allocation", "newer-time", "dispose", "worker-error", "timeout", "timeout-after-restore", "ordinary-timeout-after-restore", "superseded-timeout", "malformed"]) {
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    try {
      await page.addInitScript(({ losses, malformed, midAllocation, timeoutAfterRestore, supersededTimeout }) => {
        const probe = window.__initialContext = { contexts: [], lost: 0, renderReplies: 0, workers: 0, timers: [], status: "pending", publications: 0 };
        const get = HTMLCanvasElement.prototype.getContext;
        HTMLCanvasElement.prototype.getContext = function (kind, ...args) {
          const gl = get.call(this, kind, ...args);
          if (kind === "webgl2" && gl && !probe.contexts.includes(gl)) {
            probe.contexts.push(gl);
            const parameter = gl.getParameter.bind(gl);
            gl.getParameter = name => {
              if (midAllocation && name === gl.MAX_TEXTURE_SIZE && !probe.midLoss) {
                probe.midLoss = true; gl.getExtension("WEBGL_lose_context").loseContext();
              }
              return parameter(name);
            };
            this.addEventListener("webglcontextlost", () => probe.lost++);
            if (probe.contexts.length <= losses) queueMicrotask(() => gl.getExtension("WEBGL_lose_context").loseContext());
          }
          return gl;
        };
        const Original = window.Worker;
        window.Worker = class extends Original {
          constructor(...args) {
            super(...args); probe.workers++; this.pending = new Map(); this.ended = false;
            this.addEventListener("message", event => {
              if (this.pending.get(event.data?.requestId) === "graph.session.render") {
                probe.renderReplies++;
                if (timeoutAfterRestore && probe.renderReplies === 2) {
                  if (!probe.timers.length) throw new Error("missing recovery deadline on restored render");
                  probe.deadlineFiredAtReply = probe.renderReplies; probe.timers.at(-1)();
                }
                if (malformed && event.data?.value?.bytes) {
                  const raw = new Uint8Array(event.data.value.bytes), v = new DataView(raw.buffer);
                  const names = 32 + 40 * v.getUint32(8, true), decoder = new TextDecoder();
                  for (let i = 0; i < v.getUint32(8, true); i++) {
                    const at = 32 + 40 * i;
                    const name = decoder.decode(raw.subarray(names + v.getUint32(at, true), names + v.getUint32(at, true) + v.getUint32(at + 4, true)));
                    if (name === "gpu.node.coord.bytes") { v.setFloat32(Number(v.getBigUint64(at + 16, true)), NaN, true); break; }
                  }
                }
              }
              if (this.pending.get(event.data?.requestId) === "graph.session.temporal-frame") {
                probe.frameReplies = (probe.frameReplies || 0) + 1;
                if (supersededTimeout && probe.frameReplies === 2) {
                  probe.deadlineFiredAtFrame = probe.frameReplies;
                  for (const callback of probe.timers) callback();
                }
              }
              this.pending.delete(event.data?.requestId);
            });
          }
          postMessage(message, ...args) { this.pending.set(message.requestId, message.type); return super.postMessage(message, ...args); }
          terminate() { if (!this.ended) { probe.workers--; this.ended = true; } return super.terminate(); }
        };
        // Invoke the actual generated-deadline callback in the timeout case;
        // do not change a production constant or sleep for the wall limit.
        const timeout = window.setTimeout, clear = window.clearTimeout, timers = new Map();
        window.setTimeout = (callback, delay, ...args) => {
          if (delay !== 30000 || typeof callback !== "function") return timeout(callback, delay, ...args);
          const timer = { active: true, invoke: null };
          timer.invoke = () => { if (timer.active) { timer.active = false; callback(...args); } };
          const id = timeout(timer.invoke, delay); timers.set(id, timer); probe.timers.push(timer.invoke);
          return id;
        };
        window.clearTimeout = id => { const timer = timers.get(id); if (timer) timer.active = false; return clear(id); };
        document.addEventListener("xy:graph-render", () => probe.publications++);
      }, { losses: mode === "mid-allocation" ? 0 : mode === "repeated-loss" ? 2 : 1,
        malformed: mode === "malformed", midAllocation: mode === "mid-allocation",
        timeoutAfterRestore: mode.endsWith("timeout-after-restore"), supersededTimeout: mode === "superseded-timeout" });
      await page.goto(`http://127.0.0.1:${server.address().port}`);
      await page.waitForFunction(() => typeof window.aggregateTest?.open === "function");
      await page.evaluate(ordinary => {
        window.__initialOpening = window.aggregateTest.open({ ordinary }).then(
          () => { window.__initialContext.status = "fulfilled"; },
          error => { window.__initialContext.status = "rejected"; window.__initialContext.error = { message: error.message, code: error.code }; },
        );
      }, mode.startsWith("ordinary"));
      await page.waitForFunction(() => window.__initialContext.renderReplies > 0 && window.aggregateTest.opening);
      const waiting = await page.evaluate(() => ({ status: window.__initialContext.status,
        snapshot: window.aggregateTest.opening.session.snapshot(), lost: window.__initialContext.lost,
        contexts: window.__initialContext.contexts.length }));
      if (mode !== "malformed") assert.equal(waiting.status, "pending", `${mode}: initial loss was treated as terminal`);
      assert.equal(waiting.snapshot, null);
      if (mode === "newer-time" || mode === "superseded-timeout") await page.evaluate(() => window.aggregateTest.opening.controller.setCursor(5n));
      if (mode === "dispose") await page.evaluate(() => window.aggregateTest.opening.session.dispose());
      if (mode === "worker-error") await page.evaluate(() => window.aggregateTest.opening.worker.worker.dispatchEvent(new Event("error")));
      if (mode === "timeout") await page.evaluate(() => {
        if (!window.__initialContext.timers.length) throw new Error("missing recovery deadline");
        window.__initialContext.timers.at(-1)();
      });
      await page.waitForFunction(() => window.__initialContext.status !== "pending");
      const result = await page.evaluate(() => {
        const p = window.__initialContext, current = window.aggregateTest.current;
        let snapshot = null, alpha = 0;
        if (current) {
          snapshot = current.session.snapshot();
          const canvas = current.el.querySelector("canvas"), pixels = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
          alpha = pixels.filter((value, index) => index % 4 === 3 && value > 0).length;
        }
        return { status: p.status, error: p.error, lost: p.lost, contexts: p.contexts.length,
          publications: p.publications, renderReplies: p.renderReplies, deadlineFiredAtReply: p.deadlineFiredAtReply, deadlineFiredAtFrame: p.deadlineFiredAtFrame, alpha, snapshot };
      });
      const rejected = ["dispose", "worker-error", "timeout", "timeout-after-restore", "ordinary-timeout-after-restore", "superseded-timeout", "malformed"].includes(mode);
      assert.equal(result.status, rejected ? "rejected" : "fulfilled", JSON.stringify(result, (_, value) => typeof value === "bigint" ? value.toString() : value));
      if (rejected) {
        assert.equal(result.publications, 0);
        assert.equal(result.error.code, mode === "dispose" ? "XYG_WASM_DISPOSED" : mode.includes("timeout") ? "XYG_WASM_TIMEOUT" : mode === "malformed" ? "GF_INTERACTION_INVALID" : "XYG_WASM_WORKER_TRAP");
        if (mode.includes("timeout")) assert.equal(result.error.message, "Initial graph paint did not recover");
        if (mode.endsWith("timeout-after-restore")) assert.equal(result.deadlineFiredAtReply, 2);
        if (mode === "superseded-timeout") assert.equal(result.deadlineFiredAtFrame, 2);
        if (mode === "worker-error") assert.equal(result.error.message, "worker trapped");
      } else {
        assert.ok(result.alpha > 0); assert.equal(result.publications, 1);
        assert.ok(result.contexts >= (mode === "repeated-loss" ? 3 : 2));
        if (mode !== "ordinary") {
          assert.equal(result.snapshot.temporal.cursor, mode === "newer-time" ? 5n : 20n);
          assert.deepEqual(Array.from(result.snapshot.temporal.nodeVisibility), mode === "newer-time" ? [1, 1, 1, 1] : [1, 0, 0, 1]);
        }
      }
      if (!rejected) {
        await page.evaluate(async () => {
          // A callback retained by the test after clearTimeout cannot poison
          // an initial publication that was already accepted.
          for (const callback of window.__initialContext.timers) callback();
          await window.aggregateTest.current.session.whenIdle();
          if (!window.aggregateTest.current.session.snapshot()) throw new Error("late deadline removed accepted state");
        });
      }
      if (mode === "dispose") {
        await page.evaluate(async () => {
          const p = window.aggregateTest.opening;
          const { attachWasmGraphSession } = await import("/packages/xy-client/dist/index.js");
          const el = document.createElement("div"); document.body.append(el);
          const next = attachWasmGraphSession({ el, worker: p.worker, instanceId: 952n,
            document: p.document, load: { x: [0, 1, 100, 101], y: [0, 0, 0, 0] },
            camera: [1, 1, 30, 60, 240, 180, 1] });
          try { await next.ready; if (!next.snapshot()) throw new Error("Worker reuse omitted publication"); }
          finally { await next.dispose(); el.remove(); }
        });
        result.sameWorkerReuse = true;
      }
      await page.evaluate(async () => {
        const p = window.aggregateTest.opening;
        await p.session.dispose(); await p.controller.dispose();
        await p.worker.dispose(); await p.clockWorker.dispose(); p.el.remove();
        await window.__initialOpening;
      });
      assert.equal(await page.evaluate(() => window.__initialContext.workers), 0);
      assert.equal(await page.evaluate(() => document.querySelectorAll("[data-xy-graph-gpu]").length), 0);
      assert.deepEqual(errors, []);
      evidence.cases.push({ mode, waiting, ...result, workersAfterCleanup: 0 });
      console.log(`PASS initial-context-${mode}`);
    } finally { await page.close(); }
  }
} finally {
  await browser.close(); await new Promise(resolve => server.close(resolve));
  if (reportPath) { await mkdir(dirname(reportPath), { recursive: true }); await writeFile(reportPath, JSON.stringify(evidence, (_, value) => typeof value === "bigint" ? value.toString() : value, 2) + "\n"); }
}
