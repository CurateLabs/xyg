#!/usr/bin/env node
/** Real compiled XYChart proof; the application must use an installed wheel. */
import { chromium } from "playwright";
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { basename, dirname, resolve } from "node:path";

const origin = process.env.XYG_REFLEX_ORIGIN ?? "http://127.0.0.1:8179";
const output = resolve(process.env.XYG_REFLEX_REPORT ?? "packaged-reflex.json");
const nonce = "xyg-packaged-reflex-evidence";
const csp = `default-src 'self'; script-src 'self' 'nonce-${nonce}' 'wasm-unsafe-eval'; script-src-attr 'none'; worker-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' ${origin.replace(/^http/, "ws")}; img-src 'self' data:; font-src 'self' data:; object-src 'none'; base-uri 'self'`;
const launchArgs = ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"];
const browser = await chromium.launch({ executablePath: process.env.XYG_CHROMIUM || undefined, args: launchArgs });
const cases = [];
await mkdir(dirname(output), { recursive: true });
try {
  for (const scenario of [
    { name: "primary", path: "/", axes: ["x", "y"] },
    { name: "secondary", path: "/secondary", axes: ["x", "y", "y2"] },
    { name: "polar", path: "/polar", axes: ["x", "y"] },
    { name: "unsupported-density", path: "/density", chart: "density", axes: ["x", "y"], density: true },
    { name: "missing-wasm", path: "/", chart: "primary", axes: ["x", "y"], failure: "missing" },
    { name: "invalid-wasm", path: "/", chart: "primary", axes: ["x", "y"], failure: "invalid" },
  ]) {
    const context = await browser.newContext({ viewport: { width: 1000, height: 800 } });
    // Intercepted documents otherwise trigger Chromium's loopback-network
    // permission check on the app's own websocket. The route still rejects
    // every origin except this explicitly selected local application.
    await context.grantPermissions(["local-network-access"], { origin });
    const page = await context.newPage();
    const requests = [], external = [], errors = [], socketErrors = [], socketUrls = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("websocket", socket => {
      socketUrls.push(socket.url());
      if (new URL(socket.url()).origin !== origin.replace(/^http/, "ws")) external.push(socket.url());
      socket.on("socketerror", error => socketErrors.push(String(error)));
    });
    await context.addInitScript(() => {
      window.__packagedTicksEvents = [];
      window.__packagedDensityEvents = [];
      document.addEventListener("xy:wasm_density_no_refinement", event => window.__packagedDensityEvents.push(event.detail));
      window.__packagedSocketMessages = 0;
      const OriginalSocket = window.WebSocket;
      window.WebSocket = class extends OriginalSocket {
        constructor(...args) {
          super(...args);
          this.addEventListener("message", () => window.__packagedSocketMessages++);
        }
      };
      document.addEventListener("xy:wasm_ticks_error", event => window.__packagedTicksEvents.push(event.detail));
      window.__packagedWorkers = [];
      const OriginalWorker = window.Worker;
      window.Worker = class extends OriginalWorker {
        constructor(...args) {
          super(...args);
          this.evidence = { url: String(args[0]), terminated: false };
          window.__packagedWorkers.push(this.evidence);
        }
        terminate() { this.evidence.terminated = true; return super.terminate(); }
      };
    });
    await context.route("**/*", async route => {
      const request = route.request(), url = new URL(request.url());
      if (!["http:", "https:"].includes(url.protocol)) return route.continue();
      if (url.origin !== origin) { external.push(url.href); return route.abort(); }
      requests.push(url.pathname);
      if (url.pathname.endsWith("/xyg-wasm.wasm") && scenario.failure) {
        return route.fulfill(scenario.failure === "missing"
          ? { status: 404, body: "deliberately absent packaged WASM" }
          : { status: 200, contentType: "application/wasm", body: Buffer.from([0, 1, 2, 3]) });
      }
      if (request.resourceType() === "document") {
        const response = await route.fetch();
        const body = (await response.text()).replace(/<script\b/g, `<script nonce="${nonce}"`);
        return route.fulfill({ response, body, headers: { ...response.headers(), "content-security-policy": csp } });
      }
      return route.continue();
    });
    const chart = scenario.chart ?? scenario.name;
    const id = `packaged-${chart}`;
    try {
      await page.goto(origin + scenario.path);
      await page.waitForFunction(() => window.__packagedSocketMessages > 0, null, { timeout: 15_000 });
      await page.waitForFunction(id => window.__xy_views?.has(id), id, { timeout: 30_000 });
      if (scenario.failure) {
        await page.waitForFunction(() => window.__packagedTicksEvents.some(event =>
          event.code === "XYG_WASM_INIT_FAILED"), null, { timeout: 15_000 });
      } else {
        await page.waitForFunction(({ id, axes }) => axes.every(axis =>
          window.__xy_views.get(id)?._wasmTicks?.covers(axis)), { id, axes: scenario.axes }, { timeout: 15_000 });
      }
      const result = await page.evaluate(async ({ id, axes, failure, density }) => {
        const view = window.__xy_views.get(id);
        window.__packagedTicksView = view;
        const failureState = failure ? {
          state: view.root.dataset.xyTickState,
          noTickHandle: view._wasmTicks == null,
          tickHandleType: typeof view._wasmTicks,
          tickHandleIsNull: view._wasmTicks === null,
          tickHandleOwnProperty: Object.hasOwn(view, "_wasmTicks"),
          expectedCodeObserved: window.__packagedTicksEvents.some(event => event.code === "XYG_WASM_INIT_FAILED"),
        } : null;
        if (failure && (failureState.state !== "failed-closed" || !failureState.noTickHandle
            || !failureState.expectedCodeObserved)) {
          throw new Error(`tick initialization did not fail closed: ${JSON.stringify(failureState)}`);
        }
        let densityBoundary = null;
        if (density) {
          const trace = view.gpuTraces.find(trace => trace.tier === "density");
          const overview = trace?.density;
          if (!overview || view.spec.wasm_density?.unsupported?.code !== "XYG_WASM_SOURCE_UNSUPPORTED") {
            throw new Error("real Python density payload did not declare its unsupported source");
          }
          view._scheduleViewRequest(view.view, { delay: 0 });
          const reasons = window.__packagedDensityEvents;
          if (view._wasmDensity || trace.density !== overview
              || !reasons.some(event => event.code === "XYG_WASM_SOURCE_UNSUPPORTED")) {
            throw new Error("unsupported live density did not retain its overview and explicit reason");
          }
          densityBoundary = { source: view.spec.wasm_density, events: reasons,
            immediateOverviewRetained: true, wasmDensityHandle: false,
            nativeKernelRemainsAvailable: !!view.comm };
        }
        const tickRows = axes.map(axis => {
          const ticks = view._axisTicks(axis, 6);
          if (failure ? ticks.source !== "failed-closed" || ticks.ticks.length : ticks.source !== "wasm" || !ticks.ticks.length) {
            throw new Error(`${axis} unexpected tick source: ${JSON.stringify(ticks)}`);
          }
          return { axis, ...ticks, text: ticks.ticks.map(value => view._axisTickText(view._axis(axis), value, ticks.step)) };
        });
        let rendered, presentationAttempts = 0;
        while (presentationAttempts < 8) {
          presentationAttempts++;
          rendered = view._drawNow();
          if (view._glHost ? rendered === true : view.gl && !view._glLost && !view.gl.isContextLost()) break;
          await new Promise(resolve => requestAnimationFrame(resolve));
        }
        if (view._glHost ? rendered !== true : !view.gl || view._glLost || view.gl.isContextLost()) throw new Error(`packaged presentation did not complete: ${JSON.stringify({
          rendered, sharedHost: !!view._glHost, glLost: view._glLost,
          contextLost: view.gl?.isContextLost(), canvas: [view.canvas.width, view.canvas.height],
          worker: view._wasmTicks?.diagnostics(),
        })}`);
        const canvas = view.canvas;
        let pixels;
        if (view._glHost) {
          pixels = view._present2d.getImageData(0, 0, canvas.width, canvas.height).data;
        } else {
          // Same synchronous readback used by ChartView's context snapshot.
          // Dedicated WebGL canvases do not preserve their drawing buffer;
          // drawImage may observe already-discarded pixels after presentation.
          const gl = view.gl;
          gl.finish();
          pixels = new Uint8Array(canvas.width * canvas.height * 4);
          gl.readPixels(0, 0, canvas.width, canvas.height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
          if (gl.getError() !== gl.NO_ERROR) throw new Error("dedicated WebGL readback failed");
        }
        const alphaPixels = pixels.filter((value, index) => index % 4 === 3 && value > 0).length;
        if (!alphaPixels) throw new Error(`packaged chart is blank: ${JSON.stringify({
          rendered, sharedHost: !!view._glHost, glLost: view._glLost,
          contextLost: view.gl?.isContextLost(), canvas: [canvas.width, canvas.height],
          gpuTraces: view.gpuTraces.map(trace => ({ tier: trace.tier, n: trace.n, kind: trace.trace.kind })),
          view: view.view,
        })}`);
        return { ticks: tickRows, diagnostics: view._wasmTicks?.diagnostics() ?? null,
          captureMode: view._glHost ? "shared-presented-2d" : "dedicated-webgl-readback", rendered, presentationAttempts,
          events: window.__packagedTicksEvents, alphaPixels, workers: window.__packagedWorkers, densityBoundary, failureState };
      }, { id, axes: scenario.axes, failure: !!scenario.failure, density: !!scenario.density });
      if (!scenario.failure) {
        const revision = result.diagnostics.revision;
        await page.evaluate(({ id, polar }) => {
          const view = window.__xy_views.get(id);
          const ranges = polar ? { y: [0, 2] } : { x: [0.2, 0.8] };
          if (!view.root.xy.applyState({ ranges }, { animate: false, history: false })) throw new Error("public viewport refused");
        }, { id, polar: chart === "polar" });
        await page.waitForFunction(({ id, revision, axes }) => {
          const handle = window.__xy_views.get(id)?._wasmTicks;
          return handle?.diagnostics()?.revision > revision && axes.every(axis => handle.covers(axis));
        }, { id, revision, axes: scenario.axes }, { timeout: 15_000 });
        result.afterNavigation = await page.evaluate(id => window.__xy_views.get(id)._wasmTicks.diagnostics(), id);
      }
      const screenshot = `${basename(output)}.${scenario.name}.png`;
      const png = await page.screenshot({ path: resolve(dirname(output), screenshot) });
      await page.getByRole("link", { name: "Unmount chart" }).click();
      await page.locator("#empty-page").waitFor();
      await page.waitForFunction(id => !window.__xy_views?.has(id)
        && window.__packagedWorkers.every(worker => worker.terminated), id, { timeout: 10_000 });
      result.disposal = await page.evaluate(() => ({
        destroyed: window.__packagedTicksView._destroyed,
        glReleased: window.__packagedTicksView.gl === null,
        ticksReleased: window.__packagedTicksView._wasmTicks === null,
        listeners: window.__packagedTicksView._listeners.length,
        liveWorkers: window.__packagedWorkers.filter(worker => !worker.terminated).length,
      }));
      if (!result.disposal.destroyed || !result.disposal.glReleased || !result.disposal.ticksReleased
          || result.disposal.listeners || result.disposal.liveWorkers || result.workers.length !== 1
          || external.length || errors.length || socketErrors.length) {
        throw new Error(`packaged lifecycle failed: ${JSON.stringify({ ...result.disposal, external, errors, socketErrors })}`);
      }
      cases.push({ name: scenario.name, ...result, requests, socketUrls, external, errors, socketErrors,
        screenshot: { file: screenshot, sha256: createHash("sha256").update(png).digest("hex") } });
    } catch (error) {
      const diagnostics = await page.evaluate(() => ({
        registryKeys: [...(window.__xy_views?.keys() ?? [])],
        workers: window.__packagedWorkers,
        retained: window.__packagedTicksView ? {
          destroyed: window.__packagedTicksView._destroyed,
          glReleased: window.__packagedTicksView.gl === null,
          ticksReleased: window.__packagedTicksView._wasmTicks === null,
          listeners: window.__packagedTicksView._listeners?.length,
        } : null,
      }));
      const screenshot = `${basename(output)}.${scenario.name}.failed.png`;
      const png = await page.screenshot({ path: resolve(dirname(output), screenshot) });
      await writeFile(output, JSON.stringify({ schemaVersion: 1, status: "failed", scenario: scenario.name,
        error: error.message, diagnostics, cases, csp, launchArgs, socketUrls, errors, external, socketErrors,
        screenshot: { file: screenshot, sha256: createHash("sha256").update(png).digest("hex") },
      }, null, 2) + "\n");
      throw new Error(`${scenario.name}: ${error.message}; pageErrors=${JSON.stringify(errors)}; body=${(await page.locator("body").innerText()).slice(0, 1500)}`);
    } finally { await context.close(); }
  }
  await writeFile(output, JSON.stringify({ schemaVersion: 1, status: "passed", browser: browser.version(),
    origin, csp, launchArgs, permissions: ["local-network-access"], cases, limitations: ["Installed development wheel, not final RC acceptance.",
      "Three static XYChart routes, two initial tick-load failures, and one live unsupported-density route.",
      "Live unsupported density retains its initial Rust overview and uses the native kernel for later valid replies; standalone density degradation is separate evidence."] }, null, 2) + "\n");
  console.log(`packaged Reflex tick journey passed: ${output}`);
} finally { await browser.close(); }
