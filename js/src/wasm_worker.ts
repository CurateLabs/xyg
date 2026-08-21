/// <reference lib="webworker" />

import {
  bindXygWasmExports,
  readXygWasmError,
  XYG_WASM_STATUS,
  XYG_WASM_AGGREGATE_CHECKPOINT_POINTS,
  XYG_WASM_AGGREGATE_REQUEST_COPY_FACTOR,
  type XygWasmExports,
} from "./wasm_abi_generated";

type WorkerScope = DedicatedWorkerGlobalScope;
const scope = self as unknown as WorkerScope;

let exports: XygWasmExports | null = null;
let handle = 0;
type Lifecycle = "idle" | "initializing" | "initialized" | "failed" | "disposed";
let lifecycle: Lifecycle = "idle";
let operationBudgetBytes = 0;
const queued = new Map<number, number>();
let activeAggregate: { requestId: number; sequence: number; timer: number } | null = null;

function isDisposed(): boolean {
  return lifecycle === "disposed";
}

function reply(requestId: number, value: unknown, transfer: Transferable[] = []) {
  scope.postMessage({ requestId, ok: true, value }, transfer);
}

function error(requestId: number, code: string, message: string, status: number | null = null) {
  scope.postMessage({ requestId, ok: false, error: { code, message, status } });
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

function runSceneOp(message: any) {
  queued.delete(message.requestId);
  if (!exports || !handle || lifecycle !== "initialized") {
    error(message.requestId, "XYG_WASM_NOT_READY", "worker is not initialized");
    return;
  }
  let superseded: typeof activeAggregate = null;
  try {
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
    status = aggregate
      ? exports.xyg_wasm_aggregate_bin2d(
        handle, Number(message.sequence), 0, inputLength,
      )
      : compile
      ? (paint
        ? exports.xyg_wasm_scene_compile_prepare(
          handle, Number(message.sequence), 0, inputLength,
        )
        : exports.xyg_wasm_scene_compile(
          handle, Number(message.sequence), 0, inputLength,
        ))
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
    if (!outputPtr || outputLen !== 176 || outputEnd > exports.memory.buffer.byteLength) {
      throw new Error("Rust temporal response returned an invalid range");
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

scope.onmessage = (event: MessageEvent<any>) => {
  const message = event.data;
  if (message?.type === "init") {
    void initialize(message);
    return;
  }
  if (
    message?.type === "scene.validate"
    || message?.type === "scene.paint"
    || message?.type === "scene.compile"
    || message?.type === "scene.compile_paint"
    || message?.type === "series.compile_paint"
    || message?.type === "aggregate.bin2d"
  ) {
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
  if (message?.type === "cancel") {
    const timer = queued.get(message.requestId);
    if (timer !== undefined) {
      clearTimeout(timer);
      queued.delete(message.requestId);
    }
    try {
      if (exports && handle) exports.xyg_wasm_cancel(handle, Number(message.sequence));
      if (activeAggregate?.requestId === message.requestId && exports && handle) {
        clearTimeout(activeAggregate.timer);
        exports.xyg_wasm_aggregate_step(handle, Number(message.sequence), 1);
        activeAggregate = null;
      }
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
