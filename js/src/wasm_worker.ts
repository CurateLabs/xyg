/// <reference lib="webworker" />

import {
  bindXygWasmExports,
  readXygWasmError,
  XYG_WASM_STATUS,
  XYG_WASM_ABI_VERSION,
  XYG_WASM_SCENE_VERSION,
  XYG_WASM_AGGREGATE_CHECKPOINT_POINTS,
  XYG_WASM_AGGREGATE_REQUEST_COPY_FACTOR,
  XYG_WASM_GRAPH_DEFAULT_CHUNK_STEPS,
  XYG_WASM_GRAPH_DEFAULT_MAX_WALL_MS,
  XYG_WASM_GRAPH_FIRST_PAINT_STEPS,
  type XygWasmExports,
} from "./wasm_abi_generated";
import { decodeWasmGraphCheckpoint } from "./49_wasm_graph";

type WorkerScope = DedicatedWorkerGlobalScope;
const scope = self as unknown as WorkerScope;

let exports: XygWasmExports | null = null;
let handle = 0;
type Lifecycle = "idle" | "initializing" | "initialized" | "failed" | "disposed";
let lifecycle: Lifecycle = "idle";
let operationBudgetBytes = 0;
let initializedModule: WebAssembly.Module | null = null;
let compileLeaf = false;
let operationSequenceWatermark = 0;
const queued = new Map<number, number>();
let activeAggregate: { requestId: number; sequence: number; timer: number } | null = null;
let activeGraph: { requestId: number; sequence: number; revision: number; timer: number; chunkSteps: number; started: number; maxWallMs: number; first: boolean } | null = null;
let activeCompile: { requestId: number; sequence: number; timer: number; paint: boolean; leaf?: Worker; loweringAnnounced?: boolean } | null = null;
const COMPILE_CHECKPOINT_RECORDS = 4096;

function isDisposed(): boolean {
  return lifecycle === "disposed";
}

function reply(requestId: number, value: unknown, transfer: Transferable[] = []) {
  scope.postMessage({ requestId, ok: true, value }, transfer);
}

function error(requestId: number, code: string, message: string, status: number | null = null) {
  let snapshot = null;
  try {
    if (exports && handle) snapshot = diagnostics();
  } catch {
    // A trapped instance may reject diagnostic reads; preserve the root error.
  }
  scope.postMessage({ requestId, ok: false, error: { code, message, status, diagnostics: snapshot } });
}

function statusCode(status: number): string {
  const entry = Object.entries(XYG_WASM_STATUS).find(([, value]) => value === status);
  return entry ? `XYG_WASM_${entry[0]}` : "XYG_WASM_UNKNOWN_STATUS";
}

function disposeRust() {
  try {
    if (exports && handle) exports.xyg_wasm_instance_dispose(handle);
  } catch {
    // A trapped instance may trap again during cleanup; preserve the original error.
  } finally {
    handle = 0;
    exports = null;
  }
}

function disposeAttempt(bound: XygWasmExports | null, created: number) {
  try {
    if (bound && created) bound.xyg_wasm_instance_dispose(created);
  } catch {
    // Best-effort cleanup for a partially initialized or trapped instance.
  }
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
  if (lifecycle !== "idle") {
    error(message.requestId, "XYG_WASM_ALREADY_INITIALIZED", "worker cannot be reinitialized");
    return;
  }
  lifecycle = "initializing";
  let bound: XygWasmExports | null = null;
  let created = 0;
  try {
    const module = await loadModule(message.source);
    if (isDisposed()) return;
    if (WebAssembly.Module.imports(module).length !== 0) {
      throw new Error("XYG WASM module must not request ambient imports");
    }
    const instance = await WebAssembly.instantiate(module, {});
    if (isDisposed()) return;
    bound = bindXygWasmExports(instance);
    if (bound.xyg_wasm_abi_version() !== message.expectedAbiVersion
        || bound.xyg_wasm_scene_version() !== message.expectedSceneVersion) {
      throw new Error("XYG WASM or canonical scene version is incompatible");
    }
    const max = Number(message.maxArenaBytes);
    if (!Number.isInteger(max) || max <= 0 || max > bound.xyg_wasm_max_arena_bytes()) {
      throw new Error("maxArenaBytes exceeds the Rust adapter bound");
    }
    created = bound.xyg_wasm_instance_new(max) >>> 0;
    if (!created) throw new Error("XYG WASM instance budget is exhausted");
    if (isDisposed()) {
      disposeAttempt(bound, created);
      return;
    }
    exports = bound;
    initializedModule = module;
    compileLeaf = message.compileLeaf === true;
    handle = created;
    operationBudgetBytes = max;
    created = 0;
    lifecycle = "initialized";
    reply(message.requestId, diagnostics());
  } catch (cause) {
    disposeAttempt(bound, created);
    if (isDisposed()) return;
    lifecycle = "failed";
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
  const memoryBytes = exports.memory.buffer.byteLength;
  return {
    abiVersion: exports.xyg_wasm_abi_version() >>> 0,
    sceneVersion: exports.xyg_wasm_scene_version() >>> 0,
    arenaBytes: exports.xyg_wasm_arena_len(handle) >>> 0,
    arenaHighWaterBytes: exports.xyg_wasm_arena_high_water(handle) >>> 0,
    memoryBytes,
    memoryHighWaterBytes: memoryBytes,
    copyCount: exports.xyg_wasm_copy_count(handle) >>> 0,
    copyBytesLo: exports.xyg_wasm_copy_bytes_lo(handle) >>> 0,
    copyBytesHi: exports.xyg_wasm_copy_bytes_hi(handle) >>> 0,
    records: exports.xyg_wasm_last_scene_records(handle) >>> 0,
    styles: exports.xyg_wasm_last_scene_styles(handle) >>> 0,
  };
}

function advanceAggregate(message: any) {
  if (!exports || !handle || lifecycle !== "initialized") return;
  try {
    const status = exports.xyg_wasm_aggregate_step(handle, Number(message.sequence), XYG_WASM_AGGREGATE_CHECKPOINT_POINTS);
    if (status === XYG_WASM_STATUS.PENDING) {
      const timer = setTimeout(() => advanceAggregate(message), 0) as unknown as number;
      activeAggregate = { requestId: message.requestId, sequence: Number(message.sequence), timer };
      return;
    }
    if (activeAggregate?.requestId === message.requestId) activeAggregate = null;
    queued.delete(message.requestId);
    if (status !== XYG_WASM_STATUS.OK) {
      error(message.requestId, statusCode(status), readXygWasmError(exports, handle), status);
      return;
    }
    const outputPtr = exports.xyg_wasm_output_ptr(handle) >>> 0;
    const outputLen = exports.xyg_wasm_output_len(handle) >>> 0;
    const end = outputPtr + outputLen;
    if (!outputPtr || !outputLen || !Number.isSafeInteger(end) || end > exports.memory.buffer.byteLength) throw new Error("Rust aggregate output returned an invalid range");
    const aggregate = new Uint8Array(exports.memory.buffer, outputPtr, outputLen).slice().buffer;
    const value = { sequence: Number(message.sequence), ...diagnostics(), arenaBytes: 0, aggregate };
    reply(message.requestId, value, [aggregate]);
  } catch (cause) {
    if (activeAggregate?.requestId === message.requestId) activeAggregate = null;
    queued.delete(message.requestId);
    lifecycle = "failed";
    disposeRust();
    error(
      message.requestId,
      "XYG_WASM_TRAP",
      cause instanceof Error ? cause.message : "WASM aggregate checkpoint trapped",
    );
  }
}

function graphOutput(): ArrayBuffer {
  if (!exports || !handle) throw new Error("worker is not initialized");
  const ptr = exports.xyg_wasm_output_ptr(handle) >>> 0, len = exports.xyg_wasm_output_len(handle) >>> 0;
  if (!ptr || !len || ptr + len > exports.memory.buffer.byteLength) throw new Error("Rust graph checkpoint returned an invalid range");
  return new Uint8Array(exports.memory.buffer, ptr, len).slice().buffer;
}

function finishCompile(message: any, status: number) {
  if (!exports || !handle) return;
  activeCompile = null;
  queued.delete(message.requestId);
  if (status !== XYG_WASM_STATUS.OK) {
    error(message.requestId, statusCode(status), readXygWasmError(exports, handle), status);
    return;
  }
  const outputPtr = exports.xyg_wasm_output_ptr(handle) >>> 0;
  const outputLen = exports.xyg_wasm_output_len(handle) >>> 0;
  if (!outputPtr || !outputLen || outputPtr + outputLen > exports.memory.buffer.byteLength) {
    throw new Error("Rust compile output returned an invalid range");
  }
  const transferred = new Uint8Array(exports.memory.buffer, outputPtr, outputLen).slice().buffer;
  exports.xyg_wasm_arena_resize(handle, 0);
  const value = { sequence: Number(message.sequence), ...diagnostics(), arenaBytes: 0 };
  if (activeCompile?.paint ?? (message.type === "series.compile_paint" || message.type === "scene.compile_paint")) {
    reply(message.requestId, { ...value, painter: transferred }, [transferred]);
  } else {
    reply(message.requestId, { ...value, scene: transferred }, [transferred]);
  }
}

function advanceCompile(message: any) {
  const active = activeCompile;
  if (!active || active.requestId !== message.requestId || !exports || !handle) return;
  try {
    if ((exports.xyg_wasm_scene_compile_phase(handle) >>> 0) === 2 && !active.loweringAnnounced) {
      // Publish immediately before entering the synchronous canonical
      // expansion/Scene encode/painter lower call. A parent lifecycle Worker
      // can terminate this isolated instance while that O(N) work is running.
      scope.postMessage({ requestId: active.requestId, ok: true, progress: true, value: {
        sequence: active.sequence,
        recordsProcessed: exports.xyg_wasm_scene_compile_records_processed(handle) >>> 0,
        phase: 3,
      } });
      active.loweringAnnounced = true;
      active.timer = setTimeout(() => advanceCompile(message), 0) as unknown as number;
      queued.set(active.requestId, active.timer);
      return;
    }
    const status = exports.xyg_wasm_scene_compile_step(handle, active.sequence, COMPILE_CHECKPOINT_RECORDS);
    if (status === XYG_WASM_STATUS.PENDING) {
      scope.postMessage({ requestId: active.requestId, ok: true, progress: true, value: {
        sequence: active.sequence,
        recordsProcessed: exports.xyg_wasm_scene_compile_records_processed(handle) >>> 0,
        phase: exports.xyg_wasm_scene_compile_phase(handle) >>> 0,
      } });
      active.timer = setTimeout(() => advanceCompile(message), 0) as unknown as number;
      queued.set(active.requestId, active.timer);
      return;
    }
    finishCompile(message, status);
  } catch (cause) {
    activeCompile = null; queued.delete(message.requestId); lifecycle = "failed"; disposeRust();
    error(message.requestId, "XYG_WASM_TRAP", cause instanceof Error ? cause.message : "WASM compile checkpoint trapped");
  }
}

function terminateActiveCompile(label: string, report = true) {
  if (!activeCompile || !exports || !handle) return;
  const active = activeCompile;
  clearTimeout(active.timer);
  operationSequenceWatermark = Math.max(operationSequenceWatermark, active.sequence);
  active.leaf?.terminate();
  if (!active.leaf) exports.xyg_wasm_cancel(handle, active.sequence);
  activeCompile = null;
  if (report) error(active.requestId, "XYG_WASM_CANCELLED", `compile was superseded by ${label}`, XYG_WASM_STATUS.CANCELLED);
}

function supersedeCompile(sequence: number, label: string): boolean {
  if (!activeCompile || !exports || !handle) return true;
  if (sequence <= activeCompile.sequence) return false;
  terminateActiveCompile(label);
  return true;
}

function runIsolatedCompile(message: any) {
  queued.delete(message.requestId);
  if (!initializedModule || lifecycle !== "initialized") { error(message.requestId, "XYG_WASM_NOT_READY", "worker is not initialized"); return; }
  const sequence = Number(message.sequence);
  if (!supersedeCompile(sequence, "a newer request")) {
    error(message.requestId, "XYG_WASM_STALE_SEQUENCE", "request sequence is stale", XYG_WASM_STATUS.STALE_SEQUENCE); return;
  }
  if (activeGraph) {
    if (sequence <= activeGraph.sequence) { error(message.requestId, "XYG_WASM_STALE_SEQUENCE", "request sequence is stale", XYG_WASM_STATUS.STALE_SEQUENCE); return; }
    clearTimeout(activeGraph.timer); exports?.xyg_wasm_cancel(handle, activeGraph.sequence);
    error(activeGraph.requestId, "XYG_WASM_CANCELLED", "graph layout was superseded by compile", XYG_WASM_STATUS.CANCELLED); activeGraph = null;
  }
  if (activeAggregate) {
    if (sequence <= activeAggregate.sequence) { error(message.requestId, "XYG_WASM_STALE_SEQUENCE", "request sequence is stale", XYG_WASM_STATUS.STALE_SEQUENCE); return; }
    clearTimeout(activeAggregate.timer); exports?.xyg_wasm_cancel(handle, activeAggregate.sequence);
    exports?.xyg_wasm_aggregate_step(handle, activeAggregate.sequence, 1);
    error(activeAggregate.requestId, "XYG_WASM_CANCELLED", "aggregate was superseded by compile", XYG_WASM_STATUS.CANCELLED); activeAggregate = null;
  }
  const leaf = new Worker(import.meta.url, { type: "module", name: "xyg-wasm-compile" });
  const paint = message.type === "series.compile_paint" || message.type === "scene.compile_paint";
  activeCompile = { requestId: message.requestId, sequence, timer: 0, paint, leaf };
  leaf.onerror = (event) => {
    if (activeCompile?.leaf !== leaf) return;
    activeCompile = null; leaf.terminate();
    error(message.requestId, "XYG_WASM_WORKER_TRAP", event.message || "isolated compile worker trapped");
  };
  leaf.onmessageerror = () => {
    if (activeCompile?.leaf !== leaf) return;
    activeCompile = null; leaf.terminate();
    error(message.requestId, "XYG_WASM_MESSAGE_ERROR", "isolated compile worker returned an unreadable message");
  };
  leaf.onmessage = (event) => {
    const response = event.data;
    if (response?.requestId === 1) {
      if (activeCompile?.leaf !== leaf) { leaf.terminate(); return; }
      if (!response.ok) {
        activeCompile = null; leaf.terminate();
        error(message.requestId, response.error?.code ?? "XYG_WASM_INIT_FAILED", response.error?.message ?? "isolated compile initialization failed", response.error?.status ?? null);
        return;
      }
      const transfer = message.type === "series.compile_paint"
        ? [message.prefix, ...message.columns]
        : [message.scene];
      leaf.postMessage(message, transfer);
      return;
    }
    if (response?.requestId !== message.requestId || activeCompile?.leaf !== leaf) return;
    if (response.progress) { scope.postMessage(response); return; }
    operationSequenceWatermark = Math.max(operationSequenceWatermark, sequence);
    activeCompile = null; leaf.terminate();
    const value = response.value;
    const transfer: Transferable[] = value?.painter instanceof ArrayBuffer ? [value.painter]
      : value?.scene instanceof ArrayBuffer ? [value.scene] : [];
    scope.postMessage(response, transfer);
  };
  leaf.postMessage({
    type: "init", requestId: 1, source: { kind: "module", value: initializedModule },
    maxArenaBytes: operationBudgetBytes, expectedAbiVersion: XYG_WASM_ABI_VERSION,
    expectedSceneVersion: XYG_WASM_SCENE_VERSION, compileLeaf: true,
  });
}

function advanceGraph(message: any) {
  const active = activeGraph;
  if (!active || active.requestId !== message.requestId || !exports || !handle) return;
  try {
    if (performance.now() - active.started > active.maxWallMs) {
      exports.xyg_wasm_cancel(handle, active.sequence); activeGraph = null;
      error(active.requestId, "XYG_WASM_TIMEOUT", "graph layout exceeded maxWallMs", XYG_WASM_STATUS.RESOURCE_LIMIT); return;
    }
    const steps = active.first ? XYG_WASM_GRAPH_FIRST_PAINT_STEPS : active.chunkSteps; active.first = false;
    const status = exports.xyg_wasm_graph_step(handle, active.sequence, active.revision, steps);
    if (status !== XYG_WASM_STATUS.OK && status !== XYG_WASM_STATUS.PENDING) {
      activeGraph = null; error(active.requestId, statusCode(status), readXygWasmError(exports, handle), status); return;
    }
    const checkpoint = decodeWasmGraphCheckpoint(graphOutput());
    if (status === XYG_WASM_STATUS.OK) { activeGraph = null; reply(active.requestId, checkpoint); return; }
    scope.postMessage({ requestId: active.requestId, ok: true, progress: true, value: checkpoint });
    active.timer = setTimeout(() => advanceGraph(message), 0) as unknown as number;
  } catch (cause) {
    activeGraph = null; lifecycle = "failed"; disposeRust();
    error(message.requestId, "XYG_WASM_TRAP", cause instanceof Error ? cause.message : "WASM graph checkpoint trapped");
  }
}

function runGraph(message: any) {
  queued.delete(message.requestId);
  if (!exports || !handle || lifecycle !== "initialized") { error(message.requestId, "XYG_WASM_NOT_READY", "worker is not initialized"); return; }
  try {
    if (!supersedeCompile(Number(message.sequence), "graph layout")) { error(message.requestId, "XYG_WASM_STALE_SEQUENCE", "graph request sequence is stale", XYG_WASM_STATUS.STALE_SEQUENCE); return; }
    if (!(message.request instanceof ArrayBuffer) || message.request.byteLength > operationBudgetBytes) { error(message.requestId, "XYG_WASM_INVALID_ARGUMENT", "graph request is malformed or over budget"); return; }
    if (activeGraph) {
      if (Number(message.sequence) <= activeGraph.sequence) { error(message.requestId, "XYG_WASM_STALE_SEQUENCE", "graph request sequence is stale", XYG_WASM_STATUS.STALE_SEQUENCE); return; }
      clearTimeout(activeGraph.timer); exports.xyg_wasm_cancel(handle, activeGraph.sequence);
      error(activeGraph.requestId, "XYG_WASM_CANCELLED", "graph layout was superseded", XYG_WASM_STATUS.CANCELLED); activeGraph = null;
    }
    if (activeAggregate) {
      if (Number(message.sequence) <= activeAggregate.sequence) { error(message.requestId, "XYG_WASM_STALE_SEQUENCE", "graph request sequence is stale", XYG_WASM_STATUS.STALE_SEQUENCE); return; }
      clearTimeout(activeAggregate.timer); exports.xyg_wasm_cancel(handle, activeAggregate.sequence);
      exports.xyg_wasm_aggregate_step(handle, activeAggregate.sequence, 1);
      error(activeAggregate.requestId, "XYG_WASM_CANCELLED", "aggregate was superseded by graph layout", XYG_WASM_STATUS.CANCELLED); activeAggregate = null;
    }
    let status = exports.xyg_wasm_arena_resize(handle, message.request.byteLength);
    if (status !== XYG_WASM_STATUS.OK) { error(message.requestId, statusCode(status), readXygWasmError(exports, handle), status); return; }
    const ptr = exports.xyg_wasm_arena_ptr(handle) >>> 0;
    new Uint8Array(exports.memory.buffer, ptr, message.request.byteLength).set(new Uint8Array(message.request));
    status = exports.xyg_wasm_graph_begin(handle, Number(message.sequence), Number(message.revision), 0, message.request.byteLength);
    if (status !== XYG_WASM_STATUS.OK) { error(message.requestId, statusCode(status), readXygWasmError(exports, handle), status); return; }
    const chunkSteps = Number(message.chunkSteps ?? XYG_WASM_GRAPH_DEFAULT_CHUNK_STEPS), maxWallMs = Number(message.maxWallMs ?? XYG_WASM_GRAPH_DEFAULT_MAX_WALL_MS);
    if (!Number.isInteger(chunkSteps) || chunkSteps <= 0 || chunkSteps > 1000 || !Number.isFinite(maxWallMs) || maxWallMs <= 0 || maxWallMs > 300000) { exports.xyg_wasm_cancel(handle, Number(message.sequence)); error(message.requestId, "XYG_WASM_INVALID_ARGUMENT", "graph scheduler bounds are invalid"); return; }
    activeGraph = { requestId: message.requestId, sequence: Number(message.sequence), revision: Number(message.revision), timer: 0, chunkSteps, started: performance.now(), maxWallMs, first: true };
    advanceGraph(message);
  } catch (cause) { activeGraph = null; lifecycle = "failed"; disposeRust(); error(message.requestId, "XYG_WASM_TRAP", cause instanceof Error ? cause.message : "WASM graph start trapped"); }
}

function runSceneOp(message: any) {
  queued.delete(message.requestId);
  if (!exports || !handle || lifecycle !== "initialized") {
    error(message.requestId, "XYG_WASM_NOT_READY", "worker is not initialized");
    return;
  }
  let superseded: typeof activeAggregate = null;
  try {
    if (activeCompile && activeCompile.requestId !== message.requestId) {
      if (Number(message.sequence) <= activeCompile.sequence) {
        error(message.requestId, "XYG_WASM_STALE_SEQUENCE", "request sequence is stale", XYG_WASM_STATUS.STALE_SEQUENCE); return;
      }
      terminateActiveCompile("a newer request");
    }
    if (activeGraph && activeGraph.requestId !== message.requestId) {
      if (Number(message.sequence) <= activeGraph.sequence) { error(message.requestId, "XYG_WASM_STALE_SEQUENCE", "request sequence is stale", XYG_WASM_STATUS.STALE_SEQUENCE); return; }
      clearTimeout(activeGraph.timer); exports.xyg_wasm_cancel(handle, activeGraph.sequence);
      error(activeGraph.requestId, "XYG_WASM_CANCELLED", "graph layout was superseded", XYG_WASM_STATUS.CANCELLED); activeGraph = null;
    }
    const series = message.type === "series.compile_paint";
    if (!series && !(message.scene instanceof ArrayBuffer)) {
      error(message.requestId, "XYG_WASM_INVALID_ARGUMENT", "scene must be an ArrayBuffer");
      return;
    }
    if (series && (!(message.prefix instanceof ArrayBuffer)
        || !Array.isArray(message.columns)
        || message.columns.some((column: unknown) => !(column instanceof ArrayBuffer)))) {
      error(message.requestId, "XYG_WASM_INVALID_ARGUMENT", "typed-series buffers are malformed");
      return;
    }
    const inputLength = series ? Number(message.byteLength) : message.scene.byteLength;
    if (!Number.isSafeInteger(inputLength) || inputLength <= 0) {
      error(message.requestId, "XYG_WASM_INVALID_ARGUMENT", "scene or typed-series byte length is invalid");
      return;
    }
    if (series) {
      const total = message.columns.reduce(
        (sum: number, column: ArrayBuffer) => sum + column.byteLength,
        message.prefix.byteLength,
      );
      if (!Number.isSafeInteger(total) || total !== inputLength) {
        exports.xyg_wasm_arena_resize(handle, 0);
        error(message.requestId, "XYG_WASM_INVALID_ARGUMENT", "typed-series buffers do not match byte length");
        return;
      }
    }
    if (activeAggregate && activeAggregate.requestId !== message.requestId) {
      if (Number(message.sequence) <= activeAggregate.sequence) {
        error(
          message.requestId,
          "XYG_WASM_STALE_SEQUENCE",
          "request sequence is stale",
          XYG_WASM_STATUS.STALE_SEQUENCE,
        );
        return;
      }
      superseded = activeAggregate;
      const previous = superseded;
      clearTimeout(previous.timer);
      queued.delete(previous.requestId);
      exports.xyg_wasm_cancel(handle, previous.sequence);
      const cancelled = exports.xyg_wasm_aggregate_step(handle, previous.sequence, 1);
      if (cancelled !== XYG_WASM_STATUS.CANCELLED) {
        throw new Error("Rust aggregate cancellation cleanup returned an invalid status");
      }
      activeAggregate = null;
      error(previous.requestId, "XYG_WASM_CANCELLED", "aggregate was superseded by a newer viewport", XYG_WASM_STATUS.CANCELLED);
      superseded = null;
    }
    if (!series && !(message.scene instanceof ArrayBuffer)) {
      error(message.requestId, "XYG_WASM_INVALID_ARGUMENT", "scene must be an ArrayBuffer");
      return;
    }
    if (message.type === "aggregate.bin2d"
        && inputLength * XYG_WASM_AGGREGATE_REQUEST_COPY_FACTOR > operationBudgetBytes) {
      error(
        message.requestId,
        "XYG_WASM_RESOURCE_LIMIT",
        "aggregate request copies exceed the instance operation budget",
        XYG_WASM_STATUS.RESOURCE_LIMIT,
      );
      return;
    }
    let status = exports.xyg_wasm_arena_resize(handle, inputLength);
    if (status !== XYG_WASM_STATUS.OK) {
      error(message.requestId, statusCode(status), readXygWasmError(exports, handle), status);
      return;
    }
    const ptr = exports.xyg_wasm_arena_ptr(handle) >>> 0;
    const end = ptr + inputLength;
    if (!ptr || !Number.isSafeInteger(end) || end > exports.memory.buffer.byteLength) {
      throw new Error("Rust staging arena returned an invalid range");
    }
    // Ordinary ArrayBuffers cannot alias wasm32 linear memory. The canonical
    // source remains a JS-owned transferable; only this bounded staging slice
    // is copied into WASM. The logical arena is cleared after the operation.
    const destination = new Uint8Array(exports.memory.buffer, ptr, inputLength);
    if (series) {
      destination.set(new Uint8Array(message.prefix), 0);
      let offset = message.prefix.byteLength;
      for (const column of message.columns) {
        destination.set(new Uint8Array(column), offset);
        offset += column.byteLength;
      }
    } else {
      destination.set(new Uint8Array(message.scene));
    }
    const paint = series || message.type === "scene.paint" || message.type === "scene.compile_paint";
    const compile = series || message.type === "scene.compile" || message.type === "scene.compile_paint";
    const aggregate = message.type === "aggregate.bin2d";
    if (compile) {
      status = exports.xyg_wasm_scene_compile_begin(
        handle, Number(message.sequence), 0, inputLength, paint ? 1 : 0,
      );
      if (status === XYG_WASM_STATUS.PENDING) {
        const timer = setTimeout(() => advanceCompile(message), 0) as unknown as number;
        activeCompile = { requestId: message.requestId, sequence: Number(message.sequence), timer, paint };
        queued.set(message.requestId, timer);
        return;
      }
    } else status = aggregate
      ? exports.xyg_wasm_aggregate_bin2d(
        handle, Number(message.sequence), 0, inputLength,
      )
      : (paint
        ? exports.xyg_wasm_scene_prepare(
          handle, Number(message.sequence), 0, inputLength,
        )
        : exports.xyg_wasm_scene_validate(
          handle, Number(message.sequence), 0, inputLength,
        ));
    if (aggregate && status === XYG_WASM_STATUS.PENDING) {
      const timer = setTimeout(() => advanceAggregate(message), 0) as unknown as number;
      activeAggregate = { requestId: message.requestId, sequence: Number(message.sequence), timer };
      queued.set(message.requestId, timer);
      return;
    }
    const detail = status === XYG_WASM_STATUS.OK ? "" : readXygWasmError(exports, handle);
    const value = { sequence: Number(message.sequence), ...diagnostics() };
    if (status !== XYG_WASM_STATUS.OK) {
      exports.xyg_wasm_arena_resize(handle, 0);
      error(message.requestId, statusCode(status), detail, status);
      return;
    }
    if (paint || message.type === "scene.compile" || aggregate) {
      const outputPtr = exports.xyg_wasm_output_ptr(handle) >>> 0;
      const outputLen = exports.xyg_wasm_output_len(handle) >>> 0;
      const outputEnd = outputPtr + outputLen;
      if (!outputPtr || !outputLen || !Number.isSafeInteger(outputEnd)
          || outputEnd > exports.memory.buffer.byteLength) {
        throw new Error("Rust browser output returned an invalid range");
      }
      const transferred = new Uint8Array(exports.memory.buffer, outputPtr, outputLen).slice().buffer;
      exports.xyg_wasm_arena_resize(handle, 0);
      value.arenaBytes = 0;
      if (paint) {
        reply(message.requestId, { ...value, painter: transferred }, [transferred]);
      } else if (aggregate) {
        reply(message.requestId, { ...value, aggregate: transferred }, [transferred]);
      } else {
        reply(message.requestId, { ...value, scene: transferred }, [transferred]);
      }
    } else {
      exports.xyg_wasm_arena_resize(handle, 0);
      value.arenaBytes = 0;
      reply(message.requestId, value);
    }
  } catch (cause) {
    // A Rust trap invalidates the instance. Fail closed and require a fresh
    // worker; never continue with partially mutated engine state.
    lifecycle = "failed";
    disposeRust();
    if (superseded) {
      queued.delete(superseded.requestId);
      activeAggregate = null;
      error(
        superseded.requestId,
        "XYG_WASM_TRAP",
        cause instanceof Error ? cause.message : "WASM aggregate cancellation trapped",
      );
    }
    error(
      message.requestId,
      "XYG_WASM_TRAP",
      cause instanceof Error ? cause.message : "WASM operation trapped",
    );
  }
}

function runTemporalCommand(message: any) {
  if (!exports || !handle || lifecycle !== "initialized") {
    error(message.requestId, "XYG_WASM_NOT_READY", "worker is not initialized");
    return;
  }
  try {
    if (activeCompile) {
      terminateActiveCompile("temporal work");
    }
    // One WASM instance owns one staging/output arena. A temporal command is
    // newer work on that instance, so retire any progressive job before it
    // can publish another checkpoint into the shared output buffer.
    if (activeGraph) {
      clearTimeout(activeGraph.timer);
      exports.xyg_wasm_cancel(handle, activeGraph.sequence);
      error(activeGraph.requestId, "XYG_WASM_CANCELLED", "graph layout was superseded by temporal work", XYG_WASM_STATUS.CANCELLED);
      activeGraph = null;
    }
    if (activeAggregate) {
      clearTimeout(activeAggregate.timer);
      exports.xyg_wasm_cancel(handle, activeAggregate.sequence);
      exports.xyg_wasm_aggregate_step(handle, activeAggregate.sequence, 1);
      error(activeAggregate.requestId, "XYG_WASM_CANCELLED", "aggregate was superseded by temporal work", XYG_WASM_STATUS.CANCELLED);
      activeAggregate = null;
    }
    if (!(message.command instanceof ArrayBuffer) || message.command.byteLength < 16
        || message.command.byteLength > operationBudgetBytes) {
      error(message.requestId, "XYG_WASM_INVALID_ARGUMENT", "temporal command is malformed");
      return;
    }
    let status = exports.xyg_wasm_arena_resize(handle, message.command.byteLength);
    if (status !== XYG_WASM_STATUS.OK) {
      error(message.requestId, statusCode(status), readXygWasmError(exports, handle), status);
      return;
    }
    const ptr = exports.xyg_wasm_arena_ptr(handle) >>> 0;
    const end = ptr + message.command.byteLength;
    if (!ptr || end > exports.memory.buffer.byteLength) throw new Error("invalid temporal staging range");
    new Uint8Array(exports.memory.buffer, ptr, message.command.byteLength)
      .set(new Uint8Array(message.command));
    status = exports.xyg_wasm_temporal_execute(handle, 0, message.command.byteLength);
    if (status !== XYG_WASM_STATUS.OK) {
      const detail = readXygWasmError(exports, handle);
      exports.xyg_wasm_arena_resize(handle, 0);
      error(message.requestId, statusCode(status), detail, status);
      return;
    }
    const outputPtr = exports.xyg_wasm_output_ptr(handle) >>> 0;
    const outputLen = exports.xyg_wasm_output_len(handle) >>> 0;
    const outputEnd = outputPtr + outputLen;
    if (!outputPtr || outputLen < 176 || outputLen > operationBudgetBytes
        || outputEnd > exports.memory.buffer.byteLength) {
      throw new Error("Rust temporal response returned an invalid range");
    }
    const selectionCount = new DataView(exports.memory.buffer, outputPtr, 16).getUint32(12, true);
    if (outputLen !== 176 + selectionCount * 8) {
      throw new Error("Rust temporal response returned an invalid selection range");
    }
    const response = new Uint8Array(exports.memory.buffer, outputPtr, outputLen).slice().buffer;
    exports.xyg_wasm_arena_resize(handle, 0);
    reply(message.requestId, response, [response]);
  } catch (cause) {
    lifecycle = "failed";
    disposeRust();
    error(
      message.requestId,
      "XYG_WASM_TRAP",
      cause instanceof Error ? cause.message : "WASM temporal command trapped",
    );
  }
}

function runTemporalGraphCommand(message: any) {
  if (!exports || !handle || lifecycle !== "initialized") { error(message.requestId, "XYG_WASM_NOT_READY", "worker is not initialized"); return; }
  try {
    if (activeCompile) terminateActiveCompile("a temporal graph frame");
    if (activeGraph) {
      clearTimeout(activeGraph.timer); exports.xyg_wasm_cancel(handle, activeGraph.sequence);
      error(activeGraph.requestId, "XYG_WASM_CANCELLED", "graph layout was superseded by a temporal graph frame", XYG_WASM_STATUS.CANCELLED); activeGraph = null;
    }
    if (!(message.command instanceof ArrayBuffer) || message.command.byteLength < 32 || message.command.byteLength > operationBudgetBytes) {
      error(message.requestId, "XYG_WASM_INVALID_ARGUMENT", "temporal graph command is malformed"); return;
    }
    let status = exports.xyg_wasm_arena_resize(handle, message.command.byteLength);
    if (status !== XYG_WASM_STATUS.OK) { error(message.requestId, statusCode(status), readXygWasmError(exports, handle), status); return; }
    const ptr = exports.xyg_wasm_arena_ptr(handle) >>> 0; const end = ptr + message.command.byteLength;
    if (!ptr || end > exports.memory.buffer.byteLength) throw new Error("invalid temporal graph staging range");
    new Uint8Array(exports.memory.buffer, ptr, message.command.byteLength).set(new Uint8Array(message.command));
    status = exports.xyg_wasm_temporal_graph_execute(handle, 0, message.command.byteLength);
    if (status !== XYG_WASM_STATUS.OK) { const detail = readXygWasmError(exports, handle); exports.xyg_wasm_arena_resize(handle, 0); error(message.requestId, statusCode(status), detail, status); return; }
    const outputPtr = exports.xyg_wasm_output_ptr(handle) >>> 0; const outputLen = exports.xyg_wasm_output_len(handle) >>> 0; const outputEnd = outputPtr + outputLen;
    if (outputLen !== 0 && (!outputPtr || outputLen < 64 || outputLen > operationBudgetBytes || outputEnd > exports.memory.buffer.byteLength)) throw new Error("Rust temporal graph response returned an invalid range");
    const response = outputLen === 0 ? new ArrayBuffer(0) : new Uint8Array(exports.memory.buffer, outputPtr, outputLen).slice().buffer;
    exports.xyg_wasm_arena_resize(handle, 0); reply(message.requestId, response, [response]);
  } catch (cause) {
    lifecycle = "failed"; disposeRust(); error(message.requestId, "XYG_WASM_TRAP", cause instanceof Error ? cause.message : "WASM temporal graph command trapped");
  }
}

scope.onmessage = (event: MessageEvent<any>) => {
  const message = event.data;
  if (message?.type === "init") {
    void initialize(message);
    return;
  }
  const sequenced = message?.type === "scene.validate" || message?.type === "scene.paint"
    || message?.type === "scene.compile" || message?.type === "scene.compile_paint"
    || message?.type === "series.compile_paint" || message?.type === "aggregate.bin2d"
    || message?.type === "graph.cose";
  if (sequenced) {
    const sequence = Number(message.sequence);
    if (!Number.isInteger(sequence) || sequence <= 0 || sequence > 0xffffffff) {
      error(message.requestId, "XYG_WASM_INVALID_ARGUMENT", "sequence must be a nonzero u32", XYG_WASM_STATUS.INVALID_ARGUMENT); return;
    }
    if (sequence <= operationSequenceWatermark) {
      error(message.requestId, "XYG_WASM_STALE_SEQUENCE", "request sequence is stale", XYG_WASM_STATUS.STALE_SEQUENCE); return;
    }
    operationSequenceWatermark = sequence;
  }
  if (
    message?.type === "scene.validate"
    || message?.type === "scene.paint"
    || message?.type === "scene.compile"
    || message?.type === "scene.compile_paint"
    || message?.type === "series.compile_paint"
    || message?.type === "aggregate.bin2d"
  ) {
    const compile = message?.type === "scene.compile" || message?.type === "scene.compile_paint" || message?.type === "series.compile_paint";
    if (compile && !compileLeaf) {
      const timer = setTimeout(() => runIsolatedCompile(message), 0);
      queued.set(message.requestId, timer as unknown as number);
      return;
    }
    // Deferring one task turn gives a cancellation already queued by the main
    // thread a chance to suppress work before a synchronous WASM call starts.
    const timer = setTimeout(() => runSceneOp(message), 0);
    queued.set(message.requestId, timer as unknown as number);
    return;
  }
  if (message?.type === "temporal.command") {
    runTemporalCommand(message);
    return;
  }
  if (message?.type === "temporal_graph.command") { runTemporalGraphCommand(message); return; }
  if (message?.type === "graph.cose") { const timer = setTimeout(() => runGraph(message), 0); queued.set(message.requestId, timer as unknown as number); return; }
  if (message?.type === "cancel") {
    const timer = queued.get(message.requestId);
    if (timer !== undefined) {
      clearTimeout(timer);
      queued.delete(message.requestId);
    }
    try {
      if (activeCompile?.requestId === message.requestId && activeCompile.leaf) {
        terminateActiveCompile("cancellation", false);
      } else if (exports && handle) exports.xyg_wasm_cancel(handle, Number(message.sequence));
      if (activeAggregate?.requestId === message.requestId && exports && handle) {
        clearTimeout(activeAggregate.timer);
        exports.xyg_wasm_aggregate_step(handle, Number(message.sequence), 1);
        activeAggregate = null;
      }
      if (activeGraph?.requestId === message.requestId) { clearTimeout(activeGraph.timer); activeGraph = null; }
      if (activeCompile?.requestId === message.requestId) terminateActiveCompile("cancellation", false);
    } catch (cause) {
      activeAggregate = null;
      lifecycle = "failed";
      disposeRust();
      error(
        message.requestId,
        "XYG_WASM_TRAP",
        cause instanceof Error ? cause.message : "WASM cancellation trapped",
      );
    }
    return;
  }
  if (message?.type === "dispose") {
    lifecycle = "disposed";
    for (const timer of queued.values()) clearTimeout(timer);
    if (activeGraph) clearTimeout(activeGraph.timer);
    if (activeCompile) terminateActiveCompile("disposal", false);
    activeGraph = null;
    activeCompile = null;
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
