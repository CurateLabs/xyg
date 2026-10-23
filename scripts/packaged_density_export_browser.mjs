#!/usr/bin/env node
// Exercise an unmodified public Python HTML export. CDP changes only the
// optional inline bootstrap; CSP, client, metadata and Rust grid stay intact.
import { chromium } from "playwright";
import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { basename, dirname, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const documentPath = resolve(process.env.XYG_DENSITY_EXPORT);
const output = resolve(process.env.XYG_DENSITY_EXPORT_REPORT);
const launchArgs = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"];
const browser = await chromium.launch({ executablePath: process.env.XYG_CHROMIUM || undefined, args: launchArgs });
const cases = [];
try {
  for (const scenario of [
    { name: "missing-inline-module", code: "XYG_WASM_UNAVAILABLE", workers: 0 },
    { name: "invalid-inline-module", code: "XYG_WASM_INIT_FAILED", workers: 1 },
  ]) {
    const context = await browser.newContext({ viewport: { width: 800, height: 600 } });
    const page = await context.newPage();
    const external = [], errors = [], consoleMessages = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("console", message => {
      if (["error", "warning"].includes(message.type())) consoleMessages.push(message.text());
    });
    await context.route("**/*", route => {
      if (/^https?:/.test(route.request().url())) { external.push(route.request().url()); return route.abort(); }
      return route.continue();
    });
    await context.addInitScript(({ name }) => {
      window.__densityEvents = [];
      window.__densityWorkers = [];
      window.__densityUrls = new Set();
      const OriginalWorker = window.Worker;
      window.Worker = class extends OriginalWorker {
        constructor(...args) {
          super(...args);
          this.evidence = { url: String(args[0]), terminated: false };
          window.__densityWorkers.push(this.evidence);
        }
        terminate() { this.evidence.terminated = true; return super.terminate(); }
      };
      const create = URL.createObjectURL.bind(URL), revoke = URL.revokeObjectURL.bind(URL);
      URL.createObjectURL = blob => { const url = create(blob); window.__densityUrls.add(url); return url; };
      URL.revokeObjectURL = url => { window.__densityUrls.delete(url); return revoke(url); };
      document.addEventListener("xy:wasm_density_no_refinement", event => window.__densityEvents.push(event.detail));
      window.__xygStandaloneObserver = event => {
        if (event.phase === "attached") {
          window.__densityView = event.view;
          const trace = event.view.gpuTraces.find(trace => trace.tier === "density");
          window.__densityOriginal = { overview: trace.density, texture: trace.density.tex,
            grid: trace.density.grid.slice(), uploads: 0 };
          const upload = event.view._uploadGrid.bind(event.view);
          event.view._uploadGrid = (...args) => { window.__densityOriginal.uploads++; return upload(...args); };
        }
      };
      let inline;
      Object.defineProperty(window, "__xygInlineWasm", { configurable: true,
        get: () => inline,
        set: artifact => {
          window.__densityArtifactSha256 = artifact.sha256;
          inline = name === "missing-inline-module" ? null : { ...artifact, base64: "AAECAw==" };
        },
      });
    }, scenario);
    try {
      await page.goto(pathToFileURL(documentPath).href);
      await page.waitForFunction(code => window.__densityView && window.__densityEvents.some(event => event.code === code),
        scenario.code, { timeout: 15_000 });
      const result = await page.evaluate(async scenario => {
        const view = window.__densityView, original = window.__densityOriginal;
        const trace = view.gpuTraces.find(trace => trace.tier === "density");
        const hash = async data => [...new Uint8Array(await crypto.subtle.digest("SHA-256", data))]
          .map(value => value.toString(16).padStart(2, "0")).join("");
        const captures = [];
        const capture = async expected => {
          let presented = false, attempts = 0, rendered;
          while (attempts < 8) {
            attempts++;
            rendered = view._drawNow();
            presented = view._glHost ? rendered === true : !view._glLost && view.gl && !view.gl.isContextLost();
            if (presented) break;
            await new Promise(resolve => requestAnimationFrame(resolve));
          }
          if (!presented) throw new Error(`export never completed a live presentation: ${JSON.stringify({
            scenario: scenario.name, attempts, rendered, sharedHost: !!view._glHost,
            glLost: view._glLost, contextLost: view.gl?.isContextLost(), destroyed: view._destroyed,
            canvas: [view.canvas.width, view.canvas.height], expected, actual: view.root.xy.state().ranges,
          })}`);
          const actual = view.root.xy.state().ranges;
          if (Object.entries(expected).some(([id, range]) => actual[id]?.[0] !== range[0] || actual[id]?.[1] !== range[1])) {
            throw new Error(`export presented wrong ranges: ${JSON.stringify({ expected, actual })}`);
          }
          let pixels;
          if (view._glHost) pixels = view._present2d.getImageData(0, 0, view.canvas.width, view.canvas.height).data;
          else {
            const gl = view.gl;
            gl.finish();
            pixels = new Uint8Array(view.canvas.width * view.canvas.height * 4);
            gl.readPixels(0, 0, view.canvas.width, view.canvas.height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
            if (gl.getError() !== gl.NO_ERROR) throw new Error("export readback failed");
          }
          let alphaPixels = 0, inkPixels = 0;
          for (let i = 0; i < pixels.length; i += 4) {
            if (pixels[i + 3]) {
              alphaPixels++;
              if (Math.max(pixels[i], pixels[i + 1], pixels[i + 2]) - Math.min(pixels[i], pixels[i + 1], pixels[i + 2]) > 20) inkPixels++;
            }
          }
          if (!alphaPixels || !inkPixels) throw new Error("export blanked its Rust overview");
          captures.push(new Uint8Array(pixels));
          return { sha256: await hash(pixels), alphaPixels, inkPixels, attempts, ranges: actual,
            width: view.canvas.width, height: view.canvas.height };
        };
        const home = view._copyView(view.view0).ranges;
        const before = await capture(home);
        const zoom = { ...home, x: [0.25, 0.75], y: [0.25, 0.75] };
        if (!view.root.xy.applyState({ ranges: zoom }, { animate: false, history: false })) throw new Error("export refused zoom");
        const zoomed = await capture(zoom);
        if (before.width !== zoomed.width || before.height !== zoomed.height)
          throw new Error("export changed zoom canvas dimensions");
        let zoomMaxChannelDelta = 0;
        for (let i = 0; i < captures[0].length; i++)
          zoomMaxChannelDelta = Math.max(zoomMaxChannelDelta, Math.abs(captures[0][i] - captures[1][i]));
        if (zoomMaxChannelDelta <= 1) throw new Error("export repainted stale home pixels for zoom");
        if (!view.root.xy.applyState({ ranges: home }, { animate: false, history: false })) throw new Error("export refused home");
        const restored = await capture(home);
        // Canvas2D presentation/readback can round one color channel by one
        // integer value. Source grids, texture identity and home ranges stay exact.
        const restoration = { maxChannelDelta: 0, changedChannels: 0 };
        if (before.width !== restored.width || before.height !== restored.height)
          throw new Error("export changed home canvas dimensions");
        for (let i = 0; i < captures[0].length; i++) {
          const delta = Math.abs(captures[0][i] - captures[2][i]);
          if (delta) restoration.changedChannels++;
          restoration.maxChannelDelta = Math.max(restoration.maxChannelDelta, delta);
        }
        if (restoration.maxChannelDelta > 1 || trace.density !== original.overview
            || trace.density.tex !== original.texture || await hash(trace.density.grid) !== await hash(original.grid)
            || original.uploads || view._wasmDensity || window.__densityWorkers.length !== scenario.workers) {
          throw new Error(`export changed its overview/grid/texture, uploaded a replacement or allocated a fallback Worker: ${JSON.stringify({
            before: before.sha256, restored: restored.sha256, restoration, sameOverview: trace.density === original.overview,
            sameTexture: trace.density.tex === original.texture, grid: await hash(trace.density.grid),
            originalGrid: await hash(original.grid), uploads: original.uploads,
            attachedDensity: !!view._wasmDensity, workers: window.__densityWorkers.length,
            expectedWorkers: scenario.workers,
          })}`);
        }
        // Allow the rejected module's worker disposal to finish; no pixel retry.
        for (let i = 0; i < 8 && window.__densityWorkers.some(worker => !worker.terminated); i++) {
          await new Promise(resolve => setTimeout(resolve, 0));
        }
        if (window.__densityWorkers.some(worker => !worker.terminated) || window.__densityUrls.size) {
          throw new Error("failed inline module leaked a Worker or object URL");
        }
        return { events: window.__densityEvents, before, zoomed, restored, zoomMaxChannelDelta, restoration,
          originalModuleSha256: window.__densityArtifactSha256, gridSha256: await hash(original.grid),
          replacementUploads: original.uploads, workers: window.__densityWorkers,
          objectUrls: window.__densityUrls.size, sharedHost: !!view._glHost };
      }, scenario);
      const screenshot = `${basename(output)}.${scenario.name}.png`;
      const png = await page.screenshot({ path: resolve(dirname(output), screenshot) });
      result.disposal = await page.evaluate(async () => {
        const view = window.__densityView;
        view.destroy();
        await new Promise(resolve => setTimeout(resolve, 0));
        return { destroyed: view._destroyed, glReleased: view.gl === null,
          listeners: view._listeners.length, liveWorkers: window.__densityWorkers.filter(worker => !worker.terminated).length,
          objectUrls: window.__densityUrls.size };
      });
      if (!result.disposal.destroyed || !result.disposal.glReleased || result.disposal.listeners
          || result.disposal.liveWorkers || result.disposal.objectUrls || external.length || errors.length) {
        throw new Error(`export lifecycle failed: ${JSON.stringify({ ...result.disposal, external, errors })}`);
      }
      cases.push({ name: scenario.name, ...result, external, errors,
        screenshot: { file: screenshot, sha256: createHash("sha256").update(png).digest("hex") } });
    } catch (error) {
      const diagnostics = await page.evaluate(() => ({
        events: window.__densityEvents, workers: window.__densityWorkers,
        objectUrls: window.__densityUrls?.size,
        view: window.__densityView ? { destroyed: window.__densityView._destroyed,
          glLost: window.__densityView._glLost, contextLost: window.__densityView.gl?.isContextLost(),
          sharedHost: !!window.__densityView._glHost,
          canvas: [window.__densityView.canvas.width, window.__densityView.canvas.height],
          ranges: window.__densityView.root.xy.state().ranges } : null,
      }));
      const screenshot = `${basename(output)}.${scenario.name}.failed.png`;
      const png = await page.screenshot({ path: resolve(dirname(output), screenshot) });
      await writeFile(output, JSON.stringify({ schemaVersion: 1, status: "failed", scenario: scenario.name,
        error: error.message, browser: browser.version(), launchArgs, diagnostics, external, errors, consoleMessages, cases,
        screenshot: { file: screenshot, sha256: createHash("sha256").update(png).digest("hex") },
      }, null, 2) + "\n");
      throw error;
    } finally { await context.close(); }
  }
  const document = await readFile(documentPath);
  await writeFile(output, JSON.stringify({ schemaVersion: 1, status: "passed", browser: browser.version(), launchArgs,
    export: { file: basename(documentPath), sha256: createHash("sha256").update(document).digest("hex") },
    faultInjection: "CDP bootstrap setter: missing null; invalid preserves classicWorkerSource and replaces WASM base64 with bytes 00 01 02 03.",
    cases, limitations: ["Actual installed-wheel to_html output; only two optional inline-module failure cases.",
      "Unsupported split-source descriptors remain covered by the shared density-source tests; this public packed-HTML proof covers inline-module failures only."] }, null, 2) + "\n");
  console.log(`packaged standalone density degradation passed: ${output}`);
} finally { await browser.close(); }
