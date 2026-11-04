// Actual shipped ESM/Worker/WASM under strict CSP. All hooks below are test-only
// transport fault injection/observations; production graph policy stays Rust.
import { attachWasmGraphSession, composeWasmGraphForge, createXygWasmWorker, renderWasmGraphForge } from "/packages/xy-client/dist/index.js";
const state = window.__graphSession = { stage: "boot", commands: [], replies: [], gl: [], errors: [], inject: null, hold: false, held: [], events: [], legacyCalls: [] };
state.json = value => JSON.stringify(value, (_, v) => typeof v === "bigint" ? v.toString() : v);
const assert = (condition, message) => { if (!condition) throw new Error(message); };
function section(bytes, name, index = 0) {
  const a = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes), v = new DataView(a.buffer, a.byteOffset, a.byteLength), start = 32 + 40 * v.getUint32(8, true), dec = new TextDecoder();
  for (let i = 0; i < v.getUint32(8, true); i++) {
    const at = 32 + i * 40, n = dec.decode(a.subarray(start + v.getUint32(at, true), start + v.getUint32(at, true) + v.getUint32(at + 4, true)));
    if (n === name && v.getUint32(at + 12, true) === index) return a.subarray(Number(v.getBigUint64(at + 16, true)), Number(v.getBigUint64(at + 16, true) + v.getBigUint64(at + 32, true)));
  }
  throw new Error(`missing ${name}`);
}
const view = (a) => new DataView(a.buffer, a.byteOffset, a.byteLength);
const post = Worker.prototype.postMessage;
Worker.prototype.postMessage = function(message, transfer) {
  if (message.type?.startsWith("graph.session.")) {
    if (message.request instanceof ArrayBuffer) {
      const h = view(section(message.request, "header.u64")), words = view(section(message.request, "header.u32"));
      if (state.inject === "stale") { words.setUint32(0, words.getUint32(0, true) + 1, true); state.inject = null; }
      if (state.inject === "refuse-clear" && words.getUint32(4, true) === 4) { h.setBigUint64(0, h.getBigUint64(0, true) + 1n, true); state.inject = null; }
      if (state.inject === "wrong-instance") { h.setBigUint64(0, h.getBigUint64(0, true) + 1n, true); state.inject = null; }
      state.commands.push({ type: message.type, requestId: message.requestId, sequence: message.sequence, lifetime: message.lifetime, instanceId: h.getBigUint64(0, true), opSeq: h.getBigUint64(16, true), revision: words.getUint32(0, true), operation: words.getUint32(4, true), bytes: new Uint8Array(message.request).slice() });
    } else state.commands.push({ type: message.type, requestId: message.requestId, sequence: message.sequence, lifetime: message.lifetime });
  }
  return post.call(this, message, transfer);
};
const context = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function(kind, ...args) {
  const gl = context.call(this, kind, ...args);
  if (kind === "webgl2" && gl && !state.gl.includes(gl)) state.gl.push(gl);
  return gl;
};
const bytes = async (name) => new Uint8Array(await (await fetch(`/tests/fixtures/graphforge/results/${name}.arrow`)).arrayBuffer());
const makeWorker = (wasm = "/packages/xy-client/dist/xyg-wasm.wasm") => {
  const worker = createXygWasmWorker({ workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm });
  const actual = worker.worker, deliver = actual.onmessage;
  actual.onmessage = event => {
    const value = event.data.value;
    if (value?.bytes instanceof ArrayBuffer && value.bytes.byteLength) {
      if (state.inject === "malformed-gpu") { view(section(value.bytes, "gpu.node.coord.bytes")).setFloat32(0, NaN, true); state.inject = null; }
      if (state.inject === "malformed-clear") { view(section(value.bytes, "clear.action.u32")).setUint32(4, 2, true); state.inject = null; }
      if (state.inject === "missing-clear") {
        const a = new Uint8Array(value.bytes), v = view(a), start = 32 + 40 * v.getUint32(8, true), decoder = new TextDecoder();
        for (let i = 0; i < v.getUint32(8, true); i++) {
          const at = 32 + i * 40, offset = start + v.getUint32(at, true), length = v.getUint32(at + 4, true);
          if (decoder.decode(a.subarray(offset, offset + length)) === "clear.action.u32") a.set(new TextEncoder().encode("clear.absent.u32"), offset);
        }
        state.inject = null;
      }
      if (state.inject === "wrong-lifetime") { value.lifetime++; state.inject = null; }
      state.replies.push({ requestId: event.data.requestId, bytes: new Uint8Array(value.bytes).slice(), lifetime: value.lifetime, sequence: value.sequence });
      if (state.hold) { state.held.push(() => deliver(event)); return; }
    }
    deliver(event);
  };
  return worker;
};
const container = () => { const el = document.createElement("div"); document.body.append(el); return el; };
state.raw = message => new Promise(resolve => {
  const actual = state.worker.worker, requestId = 900000 + state.commands.length;
  const receive = event => { if (event.data.requestId === requestId) { actual.removeEventListener("message", receive); resolve(event.data); } };
  actual.addEventListener("message", receive); actual.postMessage({ ...message, requestId });
});
state.makeWorker = makeWorker; state.container = container; state.section = section;
state.release = () => { state.hold = false; for (const deliver of state.held.splice(0)) deliver(); };
state.pixel = el => [...el.querySelector("canvas").getContext("2d").getImageData(0, 0, 640, 320).data];
state.waitIdle = async (el = state.el) => {
  for (let i = 0; i < 500 && el.querySelector('[role="application"]')?.getAttribute("aria-busy") === "true"; i++) await new Promise(r => setTimeout(r, 10));
  assert(el.querySelector('[role="application"]')?.getAttribute("aria-busy") !== "true", "bounded UI action did not settle");
};
state.surface = () => state.el.querySelector('[role="application"]');
state.key = async (key, extra = {}) => { const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...extra }); state.surface().dispatchEvent(event); await state.waitIdle(); return event.defaultPrevented; };
state.snapshot = () => state.handle.snapshot();
state.boot = (async () => {
  const worker = makeWorker(); await worker.ready; state.worker = worker;
  state.input = { base: { tables: [await bytes("base-cyclic-nodes"), await bytes("base-cyclic-edges")] }, layers: [{ result: await bytes("pagerank"), intent: "graph", resultId: "rank-exact" }, { result: await bytes("node_similarity"), intent: "graph", resultId: "pair-exact" }] };
  const composed = await composeWasmGraphForge(worker, state.input).result;
  state.document = composed.bytes; const n = composed.nodeUuid.length;
  state.load = { x: Array.from({ length: n }, (_, i) => 30 + i * 55), y: Array(n).fill(100) };
  state.camera = [-1, 1, 500, 20, 640, 320, 1];
  // Obtain the actual shipped ChartView prototype, then retire the control.
  const ordinary = makeWorker(); await ordinary.ready;
  const canonicalEl = container();
  const control = await renderWasmGraphForge({ el: canonicalEl, worker: ordinary, width: 640, height: 320, input: state.input });
  const proto = Object.getPrototypeOf(control.view); control.view.destroy(); canonicalEl.remove(); await ordinary.dispose();
  for (const method of ["_cacheGraphsFromSpec", "_graphMetaArray", "_syncGraphNeighborhoodHighlight", "_pickAt", "_broadcastLinkedSelection", "_renderBoxSelection", "_renderLassoSelection"]) {
    proto[method] = () => { state.legacyCalls.push(method); throw new Error(`retained path reached legacy ${method}`); };
  }
  const before = document.createElement("button"), after = document.createElement("button"); before.id = "sentinel-before"; after.id = "sentinel-after"; before.textContent = "Before"; after.textContent = "After";
  document.body.append(before); state.el = container(); document.body.append(after);
  for (const kind of ["render", "select", "focus", "stale", "error"]) state.el.addEventListener(`xy:graph-${kind}`, e => { state.events.push({ kind, detail: e.detail }); });
  state.handle = attachWasmGraphSession({ el: state.el, worker, instanceId: 9007199254740993n, document: state.document, load: state.load, camera: state.camera });
  await state.handle.ready; state.stage = "ready";
  return true;
})().catch(error => { state.stage = "failed"; state.failure = { message: error.message, stack: error.stack, code: error.code }; throw error; });
state.attach = attachWasmGraphSession; state.compose = composeWasmGraphForge;

state.createDialog = async () => {
  const dialog = document.createElement("dialog"), el = document.createElement("div");
  dialog.id = "r2-dialog"; dialog.append(el); document.body.append(dialog);
  const worker = makeWorker(); await worker.ready;
  const handle = state.attach({ el, worker, instanceId: 72n, document: state.document, load: state.load, camera: state.camera }); await handle.ready;
  const surface = el.querySelector('[role="application"]');
  const result = state.dialog = { dialog, el, worker, handle, surface, keys: [], cancels: [], errors: [] };
  dialog.addEventListener("keydown", event => { if (event.key === "Escape") result.keys.push({ trusted: event.isTrusted, prevented: event.defaultPrevented }); });
  dialog.addEventListener("cancel", event => result.cancels.push({ trusted: event.isTrusted }));
  el.addEventListener("xy:graph-error", event => result.errors.push(event.detail));
  el.addEventListener("xy:graph-stale", event => result.errors.push(event.detail));
  dialog.showModal(); surface.focus();
};
