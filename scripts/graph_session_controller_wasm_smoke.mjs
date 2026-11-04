#!/usr/bin/env node
// Unmasked production Worker/WASM graph session keyboard/paint/ownership journey.
import assert from "node:assert/strict";
import { gunzipSync } from "node:zlib";
import { createServer } from "node:http";
import { readFile, writeFile } from "node:fs/promises";
import { extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
const root = fileURLToPath(new URL("..", import.meta.url));
const allowed = p => p === "/old-same-abi.wasm" || p === "/tests/browser/graph_session_controller_page.mjs" || p === "/tests/fixtures/graphforge/session_companion_nodes.arrow" || /^\/tests\/fixtures\/graphforge\/results\/[a-z_-]+\.arrow$/.test(p) || ["/packages/xy-client/dist/index.js", "/packages/xy-client/dist/wasm-worker.js", "/packages/xy-client/dist/xyg-wasm.wasm"].includes(p);
const csp = "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self'; style-src 'unsafe-inline'; object-src 'none'; base-uri 'none'";
const requests = [], violations = [], errors = [];
const server = createServer(async (req, res) => {
  const p = new URL(req.url, "http://localhost").pathname; requests.push(p); res.setHeader("Content-Security-Policy", csp);
  if (p === "/") { res.setHeader("Content-Type", "text/html"); res.end('<!doctype html><meta charset="utf-8"><script type="module" src="/tests/browser/graph_session_controller_page.mjs"></script>'); return; }
  if (p === "/old-same-abi.wasm") {
    res.setHeader("Content-Type", "application/wasm");
    res.end(gunzipSync(await readFile(resolve(root, "spec/performance/graph-s5b-attachment-2026-11-04/shipping-module.wasm.gz")))); return;
  }
  if (!allowed(p)) { res.statusCode = 404; res.end(); return; }
  try { const data = await readFile(resolve(root, `.${p}`)); res.setHeader("Content-Type", ({ ".mjs": "text/javascript", ".js": "text/javascript", ".wasm": "application/wasm" })[extname(p)] ?? "application/octet-stream"); res.end(data); } catch { res.statusCode = 404; res.end(); }
});
await new Promise(r => server.listen(0, "127.0.0.1", r));
const browser = await chromium.launch({ executablePath: process.env.XYG_CHROMIUM || process.env.CHROMIUM, args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const evidence = { schema: "xyg.graph-s5b-attachment/v1", cases: [] };
try {
  const page = await browser.newPage({ reducedMotion: "reduce" }); page.on("console", m => { if (/Content Security Policy|Refused to/.test(m.text())) violations.push(m.text()); }); page.on("pageerror", e => errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.waitForFunction(() => ["ready", "failed"].includes(window.__graphSession?.stage), null, { timeout: 60_000 });
  assert.equal(await page.evaluate(() => window.__graphSession.stage), "ready", JSON.stringify(await page.evaluate(() => window.__graphSession.failure)));
  const run = async (name, fn) => { const result = await fn(); evidence.cases.push({ name, result }); console.log(`PASS ${name}`); return result; };
  const check = async fn => { const result = await page.evaluate(fn); assert.equal(result.ok, true, JSON.stringify(result, (_, v) => typeof v === "bigint" ? v.toString() : v)); return result; };
  await run("default16MiB-compose-attach-GPU-lastgood-signed-camera", () => check(() => {
    const s = window.__graphSession, pixel = s.pixel(s.el), image = pixel.some((v, i) => i % 4 === 3 && v > 0), before = s.handle.snapshot();
    s.initialPixels = pixel; s.initial = before;
    return { ok: image && before.camera[0] === -1 && before.outcome.selected === 0 && s.el.querySelectorAll("tbody tr").length > 0, revision: before.revision, nodes: s.load.x.length, pixels: pixel.filter((v, i) => i % 4 === 3 && v > 0).length };
  }));
  await run("real-Tab-in-arrows-visible-focus-same-revision-unchangedgeometry", async () => {
    await page.locator("#sentinel-before").focus(); await page.keyboard.press("Tab");
    assert.equal(await page.evaluate(() => document.activeElement === window.__graphSession.surface()), true);
    await page.keyboard.press("ArrowRight"); await page.evaluate(() => window.__graphSession.waitIdle());
    if (process.env.XYG_GRAPH_SESSION_SCREENSHOT) await page.screenshot({ path: process.env.XYG_GRAPH_SESSION_SCREENSHOT, clip: { x: 0, y: 0, width: 660, height: 560 } });
    return check(() => {
      const s = window.__graphSession, current = s.snapshot(), replies = s.replies.filter(r => { try { s.section(r.bytes, "gpu.header.u32"); return true; } catch { return false; } });
      const geometry = r => ["gpu.node.coord.bytes", "gpu.shaft.coord.bytes", "gpu.head.coord.bytes", "gpu.frame.coord.bytes"].flatMap(name => { const out = []; for (let i = 0; i < (name.includes("head") ? 6 : name.includes("node") ? 2 : 4); i++) out.push([...s.section(r.bytes, name, i)].join(",")); return out; }).join(";");
      return { ok: current.focus.length === 1 && current.revision === s.initial.revision && JSON.stringify(s.pixel(s.el)) !== JSON.stringify(s.initialPixels) && geometry(replies[0]) === geometry(replies.at(-1)), revision: current.revision, focus: current.focus, summary: current.summary };
    });
  });
  await run("Enter-replace-CtrlMetaToggle-Escape-authoritative-empty-propagates", async () => check(async () => {
    const s = window.__graphSession; await s.key("Enter"); const selected = s.snapshot(); await s.key("Enter", { ctrlKey: true }); const toggled = s.snapshot(); await s.key("Enter", { metaKey: true }); const meta = s.snapshot(); const cleared = await s.key("Escape"), empty = await s.key("Escape");
    const result = s.snapshot(); return { ok: selected.outcome.selected > 0 && selected.selection.refs.length > 0 && toggled.outcome.selected === 0 && meta.outcome.selected > 0 && cleared && !empty && result.outcome.selected === 0 && !result.outcome.stateChanged && s.el.querySelector('[aria-live="polite"]').textContent === result.summary, selected: selected.selection, globalCount: selected.outcome.selected, focusAction: selected.focusAction };
  }));
  await run("observer-exception-isolated-and-reduced-motion-static-focus", () => check(async () => {
    const s = window.__graphSession, surface = s.surface();
    let observed = false;
    const onError = event => { if (event.message.includes("test observer failure")) { observed = true; event.preventDefault(); } };
    const listener = () => { throw new Error("test observer failure"); };
    window.addEventListener("error", onError); surface.addEventListener("xy:graph-focus", listener);
    await s.key("ArrowRight"); surface.removeEventListener("xy:graph-focus", listener); window.removeEventListener("error", onError);
    const before = s.pixel(s.el); await new Promise(r => setTimeout(r, 100));
    return { ok: observed && s.snapshot().focus.length === 1 && matchMedia("(prefers-reduced-motion: reduce)").matches && JSON.stringify(before) === JSON.stringify(s.pixel(s.el)), observed };
  }));
  await run("Tab-forward-back-out-no-trap", async () => {
    await page.locator('[data-xy-graph-session]').focus(); await page.keyboard.press("Shift+Tab"); assert.equal(await page.locator("#sentinel-before").evaluate(el => el === document.activeElement), true);
    await page.locator('[data-xy-graph-session]').focus();
    for (let i = 0; i < 100 && !(await page.locator("#sentinel-after").evaluate(el => el === document.activeElement)); i++) await page.keyboard.press("Tab");
    assert.equal(await page.locator("#sentinel-after").evaluate(el => el === document.activeElement), true);
    await page.keyboard.press("Shift+Tab"); assert.equal(await page.locator("#sentinel-after").evaluate(el => el === document.activeElement), false);
    return { ok: true };
  });
  await run("duplicate-attach-and-competing-product-lanes-refuse-before-mutation", () => check(async () => {
    const s = window.__graphSession, original = s.snapshot(), rejected = [];
    for (const op of [() => s.attach({ el: s.container(), worker: s.worker, instanceId: 2n, document: s.document, camera: s.camera }), () => s.worker.acquireGeoTransport(), () => s.compose(s.worker, s.input), () => s.worker.temporalGraphCommand(new ArrayBuffer(32))]) {
      try { await op(); rejected.push(false); } catch (e) { rejected.push(e.code === "GF_INTERACTION_INVALID"); }
    }
    const raw = [];
    for (const type of ["geo.transport.acquire", "scene.compile", "temporal_graph.command"]) raw.push(await s.raw({ type }));
    await s.handle.refreshRender(); return { ok: raw.every(r => !r.ok && r.error.code === "GF_INTERACTION_INVALID" && !("value" in r)) && rejected.every(Boolean) && s.json(original.selection) === s.json(s.snapshot().selection), rejected };
  }));
  await run("wrong-instance-Rust-refusal-and-malformedGPU-retain-lastgood-stale-requires-refresh", () => check(async () => {
    const s = window.__graphSession, old = s.snapshot(), pixels = s.pixel(s.el), refusals = [];
    for (const [inject, code] of [["wrong-instance", "GF_INTERACTION_INVALID"], ["malformed-gpu", "GF_INTERACTION_INVALID"], ["stale", "GF_INTERACTION_STALE"]]) {
      s.inject = inject;
      if (inject === "stale") { await s.key("ArrowRight"); refusals.push(s.events.at(-1)?.kind === "stale"); }
      else { try { await s.handle.refreshRender(); refusals.push(false); } catch (e) { refusals.push(e.code === code); } }
      if (JSON.stringify(s.pixel(s.el)) !== JSON.stringify(pixels) || s.snapshot().revision !== old.revision) return { ok: false, inject, reason: "lastgood changed" };
      const count = s.commands.length, swallowed = await s.key("Enter");
      if (inject !== "wrong-instance" && (count !== s.commands.length || swallowed)) return { ok: false, inject, reason: "stale replay" };
      if (inject === "wrong-instance") { await s.key("Escape"); }
      await s.handle.refreshRender();
    }
    return { ok: refusals.every(Boolean) && s.events.some(e => e.kind === "stale"), refusals };
  }));
  await run("one-outstanding-action-busy-unaccepted-keys-and-queued-double-disposal-no-lateevents", () => check(async () => {
    const s = window.__graphSession, el = s.container(), worker = s.makeWorker(); await worker.ready;
    const h = s.attach({ el, worker, instanceId: 1n, document: s.document, load: s.load, camera: s.camera }); await h.ready;
    let events = 0; el.addEventListener("xy:graph-render", () => events++); const surface = el.querySelector('[role="application"]');
    s.hold = true; const render = h.refreshRender();
    for (let i = 0; i < 200 && !s.held.length; i++) await new Promise(r => setTimeout(r, 5));
    const ignored = new KeyboardEvent("keydown", { key: "Enter", cancelable: true, bubbles: true }); surface.dispatchEvent(ignored);
    let busyCode; try { await h.refreshRender(); } catch (e) { busyCode = e.code; }
    const a = h.dispose(), b = h.dispose(); const immediate = !el.children.length && !surface.hasAttribute("role"); s.release(); await Promise.allSettled([render]); await a;
    const reopened = await s.compose(worker, s.input).result; await worker.dispose();
    return { ok: busyCode === "XYG_WASM_GRAPH_BUSY" && a === b && immediate && !ignored.defaultPrevented && events === 0 && reopened.nodeUuid.length > 0, events };
  }));
  await run("constructor-render-failure-closes-session-and-borrowedWorker-survives", () => check(async () => {
    const s = window.__graphSession, worker = s.makeWorker(); await worker.ready; const el = s.container();
    const h = s.attach({ el, worker, instanceId: 2n, document: s.document, load: s.load, camera: [0, 1, 0, 0, 640, 320, 1] });
    let code; try { await h.ready; } catch (e) { code = e.code; } await h.dispose();
    const composed = await s.compose(worker, s.input).result; await worker.dispose();
    return { ok: code === "GF_INTERACTION_INVALID" && !el.children.length && composed.nodeUuid.length > 0, code };
  }));
  await run("twoWorkers-independent-lifetimes-and-wrong-envelope-terminal", () => check(async () => {
    const s = window.__graphSession, worker = s.makeWorker(); await worker.ready; const el = s.container();
    const h = s.attach({ el, worker, instanceId: 9007199254740993n, document: s.document, load: s.load, camera: s.camera }); await h.ready;
    const previous = h.snapshot(); s.inject = "wrong-lifetime"; let code; try { await h.refreshRender(); } catch (e) { code = e.code; } await h.dispose(); await worker.dispose();
    await s.handle.refreshRender(); return { ok: code === "XYG_WASM_MESSAGE_ERROR" && previous.outcome.selected === 0 && s.snapshot().outcome.selected === 0, code };
  }));
  await run("dirty-shared-sampler-unit2-preserves-exact-shipped-graph-pixels", () => check(async () => {
    const s = window.__graphSession, host = globalThis[Symbol.for("reflex-dev.xy.shared-webgl-host.v1")].get(document), gl = host.gl;
    await s.handle.refreshRender(); const before = s.pixel(s.el);
    const sampler = gl.createSampler(); gl.samplerParameteri(sampler, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.samplerParameteri(sampler, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.bindSampler(2, sampler); await s.handle.refreshRender(); const dirty = s.pixel(s.el);
    const cleanup = [];
    for (let i = 0; i < 3; i++) { gl.activeTexture(gl.TEXTURE0 + i); cleanup.push(gl.getParameter(gl.SAMPLER_BINDING) === null && gl.getParameter(gl.TEXTURE_BINDING_2D) === null); }
    gl.activeTexture(gl.TEXTURE0); gl.deleteSampler(sampler);
    await s.handle.refreshRender(); const clean = s.pixel(s.el);
    const difference = actual => actual.reduce((count, value, i) => count + Number(value !== before[i]), 0);
    return { ok: difference(dirty) === 0 && difference(clean) === 0 && cleanup.every(Boolean) && gl.getError() === gl.NO_ERROR, changedChannels: { dirty: difference(dirty), clean: difference(clean) }, cleanup };
  }));
  await run("context-loss-restore-exact-last-picture-and-legacy-path-unreachable", () => check(async () => {
    const s = window.__graphSession, gl = s.gl.findLast(gl => !gl.isContextLost()), ext = gl.getExtension("WEBGL_lose_context"), before = s.pixel(s.el); ext.loseContext();
    await new Promise(r => setTimeout(r, 30)); ext.restoreContext(); await new Promise(r => setTimeout(r, 150));
    return { ok: !gl.isContextLost() && JSON.stringify(before) === JSON.stringify(s.pixel(s.el)) && s.legacyCalls.length === 0, legacyCalls: s.legacyCalls };
  }));
  await run("Rust-paged-companion51-aligned-rowSelect-textContent-focus-preservation", () => check(async () => {
    const s = window.__graphSession, worker = s.makeWorker(); await worker.ready;
    const arrow = new Uint8Array(await (await fetch("/tests/fixtures/graphforge/session_companion_nodes.arrow")).arrayBuffer());
    const composed = await s.compose(worker, { base: { tables: [arrow] } }).result, el = s.container();
    const h = s.attach({ el, worker, instanceId: 51n, document: composed.bytes, load: { x: Array.from({ length: 51 }, (_, i) => 20 + i * 8), y: Array(51).fill(50) }, camera: [1, 1, 0, 0, 640, 320, 1] }); await h.ready;
    const textSafe = !el.querySelector("img") && el.querySelector("tbody").textContent.includes("<img>");
    const first = h.snapshot(), button = el.querySelector('button[aria-label="Next graph companion page"]'); button.focus(); button.click(); await s.waitIdle(el);
    const second = h.snapshot(), focus = document.activeElement === button, rows = el.querySelectorAll("tbody tr").length;
    const aligned = second.companion.refs[0];
    el.querySelector('button[aria-label="Previous graph companion page"]').click(); await s.waitIdle(el);
    const previousRows = h.snapshot().companion.rows.length;
    button.click(); await s.waitIdle(el);
    el.querySelector("tbody button").click(); await s.waitIdle(el); const selected = h.snapshot();
    await h.dispose(); await worker.dispose();
    return { ok: first.companion.rows.length === 50 && first.companion.total === 51 && second.companion.rows.length === 1 && rows === 1 && previousRows === 50 && focus && s.json(selected.selection.refs[0]) === s.json(aligned) && textSafe, focus, textSafe, selectedRefs: selected.selection.refs, total: first.companion.total, pageLengths: [first.companion.rows.length, second.companion.rows.length], escaped: first.companion.rows[0], aligned };
  }));
  await run("trusted-dialog-Escape-Rust-applicability-admission-and-refusal", async () => {
    const results = [];
    await page.evaluate(() => {
      const dialog = document.createElement("dialog"), button = document.createElement("button"); button.textContent = "Control"; dialog.append(button); document.body.append(dialog);
      window.__graphSession.dialogControl = { dialog, cancels: [] }; dialog.addEventListener("cancel", e => window.__graphSession.dialogControl.cancels.push(e.isTrusted)); dialog.showModal(); button.focus();
    });
    await page.keyboard.press("Escape");
    await page.waitForFunction(() => !window.__graphSession.dialogControl.dialog.open);
    assert.deepEqual(await page.evaluate(() => window.__graphSession.dialogControl.cancels), [true]);
    results.push({ case: "native-control-closes", ok: true });
    await page.evaluate(() => window.__graphSession.createDialog());
    const reopen = () => page.evaluate(() => { const d = window.__graphSession.dialog; if (!d.dialog.open) d.dialog.showModal(); d.surface.focus(); });
    const idle = () => page.evaluate(() => window.__graphSession.waitIdle(window.__graphSession.dialog.el));
    const escape = async (staysOpen, label) => {
      await page.keyboard.press("Escape"); await page.waitForTimeout(40);
      const result = await page.evaluate(() => {
        const d = window.__graphSession.dialog;
        return { open: d.dialog.open, key: d.keys.at(-1), cancels: d.cancels.length, applicable: d.handle.snapshot()?.clearAction.applicable };
      });
      assert.equal(result.open, staysOpen, `${label}: ${JSON.stringify(result)}`);
      assert.equal(result.key.trusted, true); assert.equal(result.key.prevented, staysOpen);
      results.push({ case: label, ...result });
    };
    await escape(false, "empty-native-default"); await idle();
    await reopen(); await page.keyboard.press("ArrowRight"); await idle();
    assert.equal(await page.evaluate(() => window.__graphSession.dialog.handle.snapshot().clearAction.applicable), false);
    await escape(false, "focus-only-native-default"); await idle();
    await reopen(); await page.keyboard.press("Enter"); await idle();
    assert.equal(await page.evaluate(() => window.__graphSession.dialog.handle.snapshot().clearAction.applicable), true);
    await escape(true, "selected-synchronously-cancels"); await idle();
    assert.equal(await page.evaluate(() => window.__graphSession.dialog.handle.snapshot().outcome.selected), 0);
    await escape(false, "cleared-native-default"); await idle();
    await reopen(); await page.keyboard.press("Enter"); await idle();
    await page.evaluate(() => { const s = window.__graphSession; s.hold = true; s.dialog.pending = s.dialog.handle.refreshRender(); });
    await page.waitForFunction(() => window.__graphSession.held.length > 0);
    const busyCount = await page.evaluate(() => window.__graphSession.commands.length);
    await escape(false, "busy-ignores-old-true-fact");
    assert.equal(await page.evaluate(() => window.__graphSession.commands.length), busyCount);
    await page.evaluate(async () => { const s = window.__graphSession; s.release(); await s.dialog.pending; });
    await reopen(); await page.evaluate(() => { window.__graphSession.inject = "stale"; }); await page.keyboard.press("ArrowRight"); await idle();
    const staleCount = await page.evaluate(() => window.__graphSession.commands.length);
    await escape(false, "stale-ignores-old-true-fact");
    assert.equal(await page.evaluate(() => window.__graphSession.commands.length), staleCount);
    await page.evaluate(() => window.__graphSession.dialog.handle.refreshRender());
    for (const inject of ["malformed-clear", "missing-clear"]) {
      await reopen();
      const refused = await page.evaluate(async inject => {
        const s = window.__graphSession, d = s.dialog, before = s.json(d.handle.snapshot()), pixels = s.pixel(d.el); s.inject = inject;
        let code; try { await d.handle.refreshRender(); } catch(e) { code = e.code; }
        return code === "GF_INTERACTION_INVALID" && before === s.json(d.handle.snapshot()) && JSON.stringify(pixels) === JSON.stringify(s.pixel(d.el));
      }, inject);
      assert.equal(refused, true, inject);
      const count = await page.evaluate(() => window.__graphSession.commands.length);
      await escape(false, `${inject}-ignores-old-true-fact`);
      assert.equal(await page.evaluate(() => window.__graphSession.commands.length), count);
      await page.evaluate(() => window.__graphSession.dialog.handle.refreshRender());
    }
    await reopen(); await page.evaluate(() => { window.__graphSession.inject = "refuse-clear"; });
    await escape(true, "locally-accepted-then-Rust-refused-default-already-cancelled"); await idle();
    assert.equal(await page.evaluate(() => {
      const d = window.__graphSession.dialog; return d.handle.snapshot().clearAction.applicable && d.handle.snapshot().outcome.selected > 0 && d.errors.at(-1)?.code === "GF_INTERACTION_INVALID";
    }), true);
    // Terminal state must not consume the preceding true applicability fact.
    await page.evaluate(async () => { const s = window.__graphSession; s.inject = "wrong-lifetime"; try { await s.dialog.handle.refreshRender(); } catch {} });
    await escape(false, "terminal-ignores-old-true-fact");
    await page.evaluate(async () => { const d = window.__graphSession.dialog; await d.handle.dispose(); await d.worker.dispose(); d.dialog.remove(); });
    await page.evaluate(() => window.__graphSession.createDialog());
    await page.keyboard.press("ArrowRight"); await idle(); await page.keyboard.press("Enter"); await idle();
    assert.equal(await page.evaluate(() => window.__graphSession.dialog.handle.snapshot().clearAction.applicable), true);
    // Ending the borrowed Worker's lifetime makes lane admission fail while
    // the controller still displays its preceding true fact. It must not cancel.
    await page.evaluate(() => window.__graphSession.dialog.worker.dispose());
    await escape(false, "failed-local-lane-admission-does-not-cancel");
    assert.equal(await page.evaluate(() => window.__graphSession.dialog.errors.at(-1)?.code), "XYG_WASM_DISPOSED");
    await page.evaluate(async () => {
      const d = window.__graphSession.dialog; await d.handle.dispose();
      // Deliver a trusted native key to the old surface after cleanup. No
      // controller listener/fact may survive even if an owner reuses its DOM.
      d.dialog.append(d.surface); d.surface.tabIndex = 0; d.dialog.showModal(); d.surface.focus();
    });
    await escape(false, "disposed-surface-has-no-old-fact-listener");
    await page.evaluate(() => { const s = window.__graphSession; s.dialog.dialog.remove(); s.dialogControl.dialog.remove(); });
    return { ok: true, results };
  });
  await run("old-same-ABI-module-missing-clear-fact-fails-closed", () => check(async () => {
    const s = window.__graphSession, worker = s.makeWorker("/old-same-abi.wasm"); await worker.ready; const el = s.container();
    const handle = s.attach({ el, worker, instanceId: 80n, document: s.document, load: s.load, camera: s.camera });
    let code; try { await handle.ready; } catch(e) { code = e.code; } await handle.dispose();
    const composed = await s.compose(worker, s.input).result; await worker.dispose();
    return { ok: code === "GF_INTERACTION_INVALID" && handle.snapshot() === null && el.children.length === 0 && composed.nodeUuid.length > 0, code };
  }));
  await run("ambiguous-lost-reply-watchdog-is-terminal-no-replay-or-lateevents", async () => {
    await page.clock.install();
    await page.evaluate(async () => {
      const s = window.__graphSession, worker = s.makeWorker(); await worker.ready; const el = s.container();
      const handle = s.attach({ el, worker, instanceId: 62n, document: s.document, load: s.load, camera: s.camera }); await handle.ready;
      s.timeout = { worker, el, handle, events: 0 }; el.addEventListener("xy:graph-render", () => s.timeout.events++);
      s.hold = true; s.timeout.result = handle.refreshRender().then(() => "unexpected-success", error => error.code);
    });
    await page.waitForFunction(() => window.__graphSession.held.length > 0);
    await page.clock.fastForward(60_001);
    const result = await check(async () => {
      const s = window.__graphSession, t = s.timeout, code = await t.result;
      const ignored = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }); t.el.querySelector('[role="application"]').dispatchEvent(ignored);
      await t.handle.dispose(); const count = t.events; s.release(); await t.worker.dispose();
      return { ok: code === "XYG_WASM_GRAPH_REPLY_LOST" && !ignored.defaultPrevented && !t.el.children.length && count === t.events && count === 0, code, events: t.events };
    });
    await page.clock.resume(); return result;
  });
  await run("close-drains-before-ownedWorker-disposal-and-final-no-lateevents", () => check(async () => {
    const s = window.__graphSession, count = s.events.length; await s.handle.dispose(); await s.handle.dispose(); await s.worker.dispose(); await new Promise(r => setTimeout(r, 20));
    return { ok: !s.el.children.length && count === s.events.length && s.commands.some(c => c.type === "graph.session.close"), commands: s.commands.map(({ bytes, ...c }) => c), legacyCalls: s.legacyCalls };
  }));
  assert.deepEqual(violations, []); assert.deepEqual(errors, []); assert.deepEqual(requests.filter(p => p !== "/" && !allowed(p)), []);
  evidence.status = "passed"; evidence.requests = requests; evidence.cspViolations = violations; evidence.pageErrors = errors;
  if (process.env.XYG_GRAPH_SESSION_REPORT) await writeFile(process.env.XYG_GRAPH_SESSION_REPORT, JSON.stringify(evidence, (_, v) => typeof v === "bigint" ? v.toString() : v, 2) + "\n");
  console.log(`graph session strict-CSP shipping journey: ${evidence.cases.length} cases passed, zero skips`);
} finally { await browser.close(); await new Promise(r => server.close(r)); }
