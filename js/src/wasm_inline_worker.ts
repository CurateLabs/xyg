/// <reference lib="webworker" />

// The self-contained HTML runtime cannot load a module Worker from file:. This
// deliberately small classic-worker entry has the same aggregate protocol as
// wasm_worker.ts, but accepts only inline base64 WASM bytes. Vite emits it as
// an IIFE and package-wasm embeds that source alongside the checked bytes.
import {
  bindXygWasmExports,
  readXygWasmError,
  XYG_WASM_AGGREGATE_CHECKPOINT_POINTS,
  XYG_WASM_AGGREGATE_REQUEST_COPY_FACTOR,
  XYG_WASM_STATUS,
  type XygWasmExports,
} from "./wasm_abi_generated";

const scope = self as unknown as DedicatedWorkerGlobalScope;
let exports: XygWasmExports | null = null;
let handle = 0;
let maxArenaBytes = 0;
let sequenceWatermark = 0;
let lifecycle: "idle" | "initializing" | "initialized" | "failed" | "disposed" = "idle";
let evidenceCapability: string | null = null;
const queued = new Map<number, number>();
let active: { requestId: number; sequence: number; timer: number } | null = null;

function snapshot() {
  if (!exports || !handle) throw new Error("XYG WASM worker is not initialized");
  const memoryBytes = exports.memory.buffer.byteLength;
  return {
    abiVersion: exports.xyg_wasm_abi_version() >>> 0,
    sceneVersion: exports.xyg_wasm_scene_version() >>> 0,
    arenaBytes: exports.xyg_wasm_arena_len(handle) >>> 0,
    arenaHighWaterBytes: exports.xyg_wasm_arena_high_water(handle) >>> 0,
    memoryBytes, memoryHighWaterBytes: memoryBytes,
    copyCount: exports.xyg_wasm_copy_count(handle) >>> 0,
    copyBytesLo: exports.xyg_wasm_copy_bytes_lo(handle) >>> 0,
    copyBytesHi: exports.xyg_wasm_copy_bytes_hi(handle) >>> 0,
    records: exports.xyg_wasm_last_scene_records(handle) >>> 0,
    styles: exports.xyg_wasm_last_scene_styles(handle) >>> 0,
  };
}
function reply(requestId: number, value: unknown, transfer: Transferable[] = []) {
  scope.postMessage({ requestId, ok: true, value }, transfer);
}
function code(status: number) {
  const entry = Object.entries(XYG_WASM_STATUS).find(([, value]) => value === status);
  return entry ? `XYG_WASM_${entry[0]}` : "XYG_WASM_UNKNOWN_STATUS";
}
function fail(requestId: number, errorCode: string, message: string, status: number | null = null) {
  let diagnostics = null;
  try { if (exports && handle) diagnostics = snapshot(); } catch { /* preserve root error */ }
  scope.postMessage({ requestId, ok: false, error: { code: errorCode, message, status, diagnostics } });
}
function disposeRust() {
  try { if (exports && handle) exports.xyg_wasm_instance_dispose(handle); } catch { /* best effort */ }
  handle = 0; exports = null;
}
function bytes(base64: unknown): Uint8Array {
  if (typeof base64 !== "string" || !base64.length) throw new TypeError("inline WASM base64 is required");
  return Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
}
async function initialize(message: any) {
  if (lifecycle !== "idle") return fail(message.requestId, "XYG_WASM_ALREADY_INITIALIZED", "worker cannot be reinitialized");
  lifecycle = "initializing";
  try {
    const module = await WebAssembly.compile(Uint8Array.from(bytes(message.base64)).buffer);
    if (WebAssembly.Module.imports(module).length) throw new Error("XYG WASM module must not request ambient imports");
    const bound = bindXygWasmExports(await WebAssembly.instantiate(module, {}));
    const budget = Number(message.maxArenaBytes);
    if (bound.xyg_wasm_abi_version() !== Number(message.expectedAbiVersion)
      || bound.xyg_wasm_scene_version() !== Number(message.expectedSceneVersion)) throw new Error("XYG WASM or canonical scene version is incompatible");
    if (!Number.isInteger(budget) || budget <= 0 || budget > bound.xyg_wasm_max_arena_bytes()) throw new Error("maxArenaBytes exceeds the Rust adapter bound");
    const created = bound.xyg_wasm_instance_new(budget) >>> 0;
    if (!created) throw new Error("XYG WASM instance budget is exhausted");
    evidenceCapability = typeof message.evidenceCapability === "string" && message.evidenceCapability.length >= 24
      ? message.evidenceCapability : null;
    exports = bound; handle = created; maxArenaBytes = budget; lifecycle = "initialized";
    reply(message.requestId, snapshot());
  } catch (cause) {
    lifecycle = "failed"; disposeRust();
    fail(message.requestId, "XYG_WASM_INIT_FAILED", cause instanceof Error ? cause.message : "WASM initialization failed");
  }
}
function finish(message: any, status: number) {
  if (!exports || !handle) return;
  active = null; queued.delete(message.requestId);
  if (status !== XYG_WASM_STATUS.OK) return fail(message.requestId, code(status), readXygWasmError(exports, handle), status);
  try {
    const pointer = exports.xyg_wasm_output_ptr(handle) >>> 0;
    const length = exports.xyg_wasm_output_len(handle) >>> 0;
    if (!pointer || !length || pointer + length > exports.memory.buffer.byteLength) throw new Error("Rust aggregate output returned an invalid range");
    const aggregate = new Uint8Array(exports.memory.buffer, pointer, length).slice().buffer;
    exports.xyg_wasm_arena_resize(handle, 0);
    reply(message.requestId, { sequence: Number(message.sequence), ...snapshot(), arenaBytes: 0, aggregate }, [aggregate]);
  } catch (cause) {
    lifecycle = "failed"; disposeRust();
    fail(message.requestId, "XYG_WASM_TRAP", cause instanceof Error ? cause.message : "WASM aggregate checkpoint trapped");
  }
}
function step(message: any) {
  if (!exports || !handle || lifecycle !== "initialized") return;
  try {
    const status = exports.xyg_wasm_aggregate_step(handle, Number(message.sequence), XYG_WASM_AGGREGATE_CHECKPOINT_POINTS);
    if (status === XYG_WASM_STATUS.PENDING) {
      const timer = setTimeout(() => step(message), 0) as unknown as number;
      active = { requestId: message.requestId, sequence: Number(message.sequence), timer }; return;
    }
    finish(message, status);
  } catch (cause) {
    active = null; queued.delete(message.requestId); lifecycle = "failed"; disposeRust();
    fail(message.requestId, "XYG_WASM_TRAP", cause instanceof Error ? cause.message : "WASM aggregate checkpoint trapped");
  }
}
function aggregate(message: any) {
  if (!exports || !handle || lifecycle !== "initialized") return fail(message.requestId, "XYG_WASM_NOT_READY", "worker is not initialized");
  const input = message.request;
  if (!(input instanceof ArrayBuffer) || !input.byteLength || input.byteLength > maxArenaBytes) return fail(message.requestId, "XYG_WASM_INVALID_ARGUMENT", "aggregate request must be a bounded ArrayBuffer", XYG_WASM_STATUS.INVALID_ARGUMENT);
  if (input.byteLength * XYG_WASM_AGGREGATE_REQUEST_COPY_FACTOR > maxArenaBytes) return fail(message.requestId, "XYG_WASM_RESOURCE_LIMIT", "aggregate request copies exceed the instance operation budget", XYG_WASM_STATUS.RESOURCE_LIMIT);
  try {
    const resized = exports.xyg_wasm_arena_resize(handle, input.byteLength);
    if (resized !== XYG_WASM_STATUS.OK) return fail(message.requestId, code(resized), readXygWasmError(exports, handle), resized);
    const pointer = exports.xyg_wasm_arena_ptr(handle) >>> 0;
    if (!pointer || pointer + input.byteLength > exports.memory.buffer.byteLength) throw new Error("Rust staging arena returned an invalid range");
    new Uint8Array(exports.memory.buffer, pointer, input.byteLength).set(new Uint8Array(input));
    const status = exports.xyg_wasm_aggregate_bin2d(handle, Number(message.sequence), 0, input.byteLength);
    if (status === XYG_WASM_STATUS.PENDING) {
      const timer = setTimeout(() => step(message), 0) as unknown as number;
      active = { requestId: message.requestId, sequence: Number(message.sequence), timer }; queued.set(message.requestId, timer); return;
    }
    finish(message, status);
  } catch (cause) { lifecycle = "failed"; disposeRust(); fail(message.requestId, "XYG_WASM_TRAP", cause instanceof Error ? cause.message : "WASM aggregate trapped"); }
}
function evidenceLifecycle(message: any) {
  if (!evidenceCapability || message.capability !== evidenceCapability) {
    return fail(message.requestId, "XYG_WASM_EVIDENCE_DISABLED", "lifecycle evidence is not enabled");
  }
  if (message.action === "malformed") {
    // Exercise Rust validation while retaining the initialized instance so the
    // following valid viewport proves malformed-input recovery.
    if (!exports || !handle) return fail(message.requestId, "XYG_WASM_NOT_READY", "worker is not initialized");
    // Sequence zero is rejected by Rust before it can advance the resumable
    // operation watermark, so the following normal viewport proves recovery.
    const status = exports.xyg_wasm_aggregate_bin2d(handle, 0, 0, 0);
    return fail(message.requestId, code(status), readXygWasmError(exports, handle), status);
  }
  if (message.action === "resource") {
    // Exercise the same stable resource-limit transport boundary without
    // changing the live instance. A subsequent viewport proves that a refused
    // request neither leaks nor poisons the bounded density lifecycle.
    return fail(message.requestId, "XYG_WASM_RESOURCE_LIMIT", "aggregate request exceeds the instance operation budget", XYG_WASM_STATUS.RESOURCE_LIMIT);
  }
  if (message.action === "trap") {
    // Deliberately take the same WebAssembly-error path as a Rust trap. This
    // capability-gated hook exists solely in the generated evidence worker.
    try { throw new WebAssembly.RuntimeError("evidence-injected Rust/WASM trap"); }
    catch (cause) {
      lifecycle = "failed"; disposeRust();
      return fail(message.requestId, "XYG_WASM_TRAP", cause instanceof Error ? cause.message : "WASM aggregate trapped");
    }
  }
  return fail(message.requestId, "XYG_WASM_INVALID_ARGUMENT", "unknown lifecycle evidence action");
}
scope.onmessage = (event: MessageEvent<any>) => {
  const message = event.data;
  if (message?.type === "init") { void initialize(message); return; }
  if (message?.type === "aggregate.bin2d") {
    const sequence = Number(message.sequence);
    if (!Number.isInteger(sequence) || sequence <= 0 || sequence > 0xffffffff) return fail(message.requestId, "XYG_WASM_INVALID_ARGUMENT", "sequence must be a nonzero u32", XYG_WASM_STATUS.INVALID_ARGUMENT);
    if (sequence <= sequenceWatermark) return fail(message.requestId, "XYG_WASM_STALE_SEQUENCE", "request sequence is stale", XYG_WASM_STATUS.STALE_SEQUENCE);
    sequenceWatermark = sequence; aggregate(message); return;
  }
  if (message?.type === "evidence.lifecycle") { evidenceLifecycle(message); return; }
  if (message?.type === "diagnostics") { try { reply(message.requestId, snapshot()); } catch (cause) { fail(message.requestId, "XYG_WASM_NOT_READY", cause instanceof Error ? cause.message : "worker is not initialized"); } return; }
  if (message?.type === "cancel") {
    const timer = queued.get(message.requestId); if (timer !== undefined) { clearTimeout(timer); queued.delete(message.requestId); }
    try {
      if (exports && handle) exports.xyg_wasm_cancel(handle, Number(message.sequence));
      if (active?.requestId === message.requestId && exports && handle) { clearTimeout(active.timer); exports.xyg_wasm_aggregate_step(handle, Number(message.sequence), 1); active = null; }
    } catch (cause) { lifecycle = "failed"; disposeRust(); fail(message.requestId, "XYG_WASM_TRAP", cause instanceof Error ? cause.message : "WASM cancellation trapped"); }
    return;
  }
  if (message?.type === "dispose") { lifecycle = "disposed"; for (const timer of queued.values()) clearTimeout(timer); if (active) clearTimeout(active.timer); queued.clear(); active = null; disposeRust(); reply(message.requestId, null); scope.close(); }
};
