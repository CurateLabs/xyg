/// <reference lib="webworker" />

import {
  bindXygWasmExports,
  readXygWasmError,
  XYG_WASM_STATUS,
  type XygWasmExports,
} from "./wasm_abi_generated";

type WorkerScope = DedicatedWorkerGlobalScope;
const scope = self as unknown as WorkerScope;

let exports: XygWasmExports | null = null;
let handle = 0;
let failed = false;
let disposed = false;
const queued = new Map<number, number>();

function reply(requestId: number, value: unknown) {
  scope.postMessage({ requestId, ok: true, value });
}

function error(requestId: number, code: string, message: string, status: number | null = null) {
  scope.postMessage({ requestId, ok: false, error: { code, message, status } });
}

function statusCode(status: number): string {
  const entry = Object.entries(XYG_WASM_STATUS).find(([, value]) => value === status);
  return entry ? `XYG_WASM_${entry[0]}` : "XYG_WASM_UNKNOWN_STATUS";
}

function disposeRust() {
  if (exports && handle) exports.xyg_wasm_instance_dispose(handle);
  handle = 0;
  exports = null;
}

async function loadModule(source: any): Promise<WebAssembly.Module> {
  if (source?.kind === "module" && source.value instanceof WebAssembly.Module) {
    return source.value;
  }
  if (source?.kind === "bytes" && source.value instanceof ArrayBuffer) {
    return WebAssembly.compile(source.value);
  }
  if (source?.kind === "url" && typeof source.value === "string") {
    // This is the only network-capable branch and the URL is supplied by the
    // caller. There is no default CDN, fallback URL, or path probing.
    const response = await fetch(source.value, {
      credentials: "same-origin",
      redirect: "error",
    });
    if (!response.ok) throw new Error(`WASM URL returned HTTP ${response.status}`);
    return WebAssembly.compile(await response.arrayBuffer());
  }
  throw new TypeError("unsupported explicit WASM source");
}

async function initialize(message: any) {
  if (exports || failed) {
    error(message.requestId, "XYG_WASM_ALREADY_INITIALIZED", "worker cannot be reinitialized");
    return;
  }
  try {
    const module = await loadModule(message.source);
    if (disposed) return;
    if (WebAssembly.Module.imports(module).length !== 0) {
      throw new Error("XYG WASM module must not request ambient imports");
    }
    const instance = await WebAssembly.instantiate(module, {});
    const bound = bindXygWasmExports(instance);
    if (bound.xyg_wasm_abi_version() !== message.expectedAbiVersion
        || bound.xyg_wasm_scene_version() !== message.expectedSceneVersion) {
      throw new Error("XYG WASM or canonical scene version is incompatible");
    }
    const max = Number(message.maxArenaBytes);
    if (!Number.isInteger(max) || max <= 0 || max > bound.xyg_wasm_max_arena_bytes()) {
      throw new Error("maxArenaBytes exceeds the Rust adapter bound");
    }
    const created = bound.xyg_wasm_instance_new(max) >>> 0;
    if (!created) throw new Error("XYG WASM instance budget is exhausted");
    exports = bound;
    handle = created;
    reply(message.requestId, diagnostics());
  } catch (cause) {
    failed = true;
    disposeRust();
    error(
      message.requestId,
      "XYG_WASM_INIT_FAILED",
      cause instanceof Error ? cause.message : "WASM initialization failed",
    );
  }
}

function diagnostics() {
  if (!exports || !handle) throw new Error("XYG WASM worker is not initialized");
  return {
    abiVersion: exports.xyg_wasm_abi_version() >>> 0,
    sceneVersion: exports.xyg_wasm_scene_version() >>> 0,
    arenaBytes: exports.xyg_wasm_arena_len(handle) >>> 0,
    copyCount: exports.xyg_wasm_copy_count(handle) >>> 0,
    copyBytesLo: exports.xyg_wasm_copy_bytes_lo(handle) >>> 0,
    copyBytesHi: exports.xyg_wasm_copy_bytes_hi(handle) >>> 0,
    records: exports.xyg_wasm_last_scene_records(handle) >>> 0,
    styles: exports.xyg_wasm_last_scene_styles(handle) >>> 0,
  };
}

function validateScene(message: any) {
  queued.delete(message.requestId);
  if (!exports || !handle || failed) {
    error(message.requestId, "XYG_WASM_NOT_READY", "worker is not initialized");
    return;
  }
  try {
    if (!(message.scene instanceof ArrayBuffer)) {
      error(message.requestId, "XYG_WASM_INVALID_ARGUMENT", "scene must be an ArrayBuffer");
      return;
    }
    let status = exports.xyg_wasm_arena_resize(handle, message.scene.byteLength);
    if (status !== XYG_WASM_STATUS.OK) {
      error(message.requestId, statusCode(status), readXygWasmError(exports, handle), status);
      return;
    }
    const ptr = exports.xyg_wasm_arena_ptr(handle) >>> 0;
    const end = ptr + message.scene.byteLength;
    if (!ptr || !Number.isSafeInteger(end) || end > exports.memory.buffer.byteLength) {
      throw new Error("Rust staging arena returned an invalid range");
    }
    // Ordinary ArrayBuffers cannot alias wasm32 linear memory. The canonical
    // source remains a JS-owned transferable; only this bounded staging slice
    // is copied into WASM. The logical arena is cleared after the operation.
    new Uint8Array(exports.memory.buffer, ptr, message.scene.byteLength)
      .set(new Uint8Array(message.scene));
    status = exports.xyg_wasm_scene_validate(
      handle,
      Number(message.sequence),
      0,
      message.scene.byteLength,
    );
    const detail = status === XYG_WASM_STATUS.OK ? "" : readXygWasmError(exports, handle);
    const value = { sequence: Number(message.sequence), ...diagnostics() };
    exports.xyg_wasm_arena_resize(handle, 0);
    value.arenaBytes = 0;
    if (status !== XYG_WASM_STATUS.OK) {
      error(message.requestId, statusCode(status), detail, status);
      return;
    }
    reply(message.requestId, value);
  } catch (cause) {
    // A Rust trap invalidates the instance. Fail closed and require a fresh
    // worker; never continue with partially mutated engine state.
    failed = true;
    disposeRust();
    error(
      message.requestId,
      "XYG_WASM_TRAP",
      cause instanceof Error ? cause.message : "WASM operation trapped",
    );
  }
}

scope.onmessage = (event: MessageEvent<any>) => {
  const message = event.data;
  if (message?.type === "init") {
    void initialize(message);
    return;
  }
  if (message?.type === "scene.validate") {
    // Deferring one task turn gives a cancellation already queued by the main
    // thread a chance to suppress work before a synchronous WASM call starts.
    const timer = setTimeout(() => validateScene(message), 0);
    queued.set(message.requestId, timer as unknown as number);
    return;
  }
  if (message?.type === "cancel") {
    const timer = queued.get(message.requestId);
    if (timer !== undefined) {
      clearTimeout(timer);
      queued.delete(message.requestId);
    }
    if (exports && handle) exports.xyg_wasm_cancel(handle, Number(message.sequence));
    return;
  }
  if (message?.type === "dispose") {
    disposed = true;
    for (const timer of queued.values()) clearTimeout(timer);
    queued.clear();
    disposeRust();
    reply(message.requestId, undefined);
    scope.close();
    return;
  }
  if (Number.isInteger(message?.requestId)) {
    error(message.requestId, "XYG_WASM_UNSUPPORTED", "unsupported worker operation");
  }
};
