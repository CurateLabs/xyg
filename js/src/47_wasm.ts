import {
  XYG_WASM_ABI_VERSION,
  XYG_WASM_MAX_ARENA_BYTES,
  XYG_WASM_SCENE_VERSION,
} from "./wasm_abi_generated";
import type { XygWasmTypedSeriesRequest } from "./49_wasm_chart";

export type XygWasmSource = string | URL | ArrayBuffer | Uint8Array | WebAssembly.Module;

export interface XygWasmWorkerOptions {
  /** Required static module-worker asset. XYG never guesses a path or creates a Blob URL. */
  workerUrl: string | URL;
  /** Explicit local URL, compiled Module, or bytes for the xyg-wasm artifact. */
  wasm: XygWasmSource;
  /** Logical staging bound. The Rust adapter also enforces its compile-time ceiling. */
  maxArenaBytes?: number;
}

export interface XygWasmDiagnostics {
  abiVersion: number;
  sceneVersion: number;
  arenaBytes: number;
  arenaHighWaterBytes: number;
  memoryBytes: number;
  /** Current linear memory is also its high-water because WebAssembly memory cannot shrink. */
  memoryHighWaterBytes: number;
  copyCount: number;
  copyBytesLo: number;
  copyBytesHi: number;
  records: number;
  styles: number;
}

export interface XygWasmSceneValidation extends XygWasmDiagnostics {
  sequence: number;
}

export interface XygWasmScenePaint extends XygWasmSceneValidation {
  /** Rust-authored, checked-f32 painter columns and trace descriptors. */
  painter: ArrayBuffer;
}

export interface XygWasmCompiledScene extends XygWasmSceneValidation {
  /** Canonical Scene batch bytes produced by Rust from typed columns. */
  scene: ArrayBuffer;
}

export interface XygWasmTask<T> {
  requestId: number;
  sequence: number;
  result: Promise<T>;
  cancel(): void;
}

export interface XygWasmAggregateTaskOptions {
  sequence?: number;
  /** Aggregate ownership transfer is mandatory so browser-wide peak memory stays bounded. */
  transfer?: true;
}

type AggregateTransferContract = Exclude<XygWasmAggregateTaskOptions["transfer"], undefined>;
type AssertTrue<T extends true> = T;
type AggregateTransferMustRemainTrue = AssertTrue<AggregateTransferContract>;

export class XygWasmError extends Error {
  readonly code: string;
  readonly status: number | null;

  constructor(code: string, message: string, status: number | null = null) {
    super(message);
    this.name = "XygWasmError";
    this.code = code;
    this.status = status;
  }
}

type Pending = {
  resolve(value: any): void;
  reject(reason: XygWasmError): void;
};

function workerError(value: any): XygWasmError {
  return new XygWasmError(
    typeof value?.code === "string" ? value.code : "XYG_WASM_WORKER_ERROR",
    typeof value?.message === "string" ? value.message : "XYG WASM worker failed",
    Number.isInteger(value?.status) ? value.status : null,
  );
}

function sourceMessage(source: XygWasmSource): {
  source: any;
  transfer: Transferable[];
} {
  if (typeof source === "string" || source instanceof URL) {
    return { source: { kind: "url", value: String(source) }, transfer: [] };
  }
  if (source instanceof WebAssembly.Module) {
    return { source: { kind: "module", value: source }, transfer: [] };
  }
  if (source instanceof Uint8Array) {
    if (!(source.buffer instanceof ArrayBuffer)) {
      throw new TypeError("SharedArrayBuffer WASM sources are not supported by this foundation");
    }
    const bytes = source.byteOffset === 0 && source.byteLength === source.buffer.byteLength
      ? source.buffer
      : source.slice().buffer;
    return { source: { kind: "bytes", value: bytes }, transfer: [bytes] };
  }
  if (source instanceof ArrayBuffer) {
    return { source: { kind: "bytes", value: source }, transfer: [source] };
  }
  throw new TypeError("wasm must be an explicit URL, Module, ArrayBuffer, or Uint8Array");
}

function sceneMessage(scene: ArrayBuffer | Uint8Array, transfer: boolean) {
  if (scene instanceof Uint8Array) {
    if (!(scene.buffer instanceof ArrayBuffer)) {
      throw new TypeError("SharedArrayBuffer scene inputs are not supported by this foundation");
    }
    // A sub-view cannot be transferred without also exposing unrelated bytes.
    // Copy only that bounded view; an exact full-buffer view can transfer.
    if (scene.byteOffset !== 0 || scene.byteLength !== scene.buffer.byteLength) {
      const exact = scene.slice().buffer;
      return { buffer: exact, transfer: transfer ? [exact] : [] };
    }
    return { buffer: scene.buffer, transfer: transfer ? [scene.buffer] : [] };
  }
  if (!(scene instanceof ArrayBuffer)) {
    throw new TypeError("scene must be an ArrayBuffer or Uint8Array");
  }
  return { buffer: scene, transfer: transfer ? [scene] : [] };
}

/**
 * Thin lifecycle proxy for the direct-browser Rust worker foundation.
 *
 * Callers provide explicit static assets. Scene validate/prepare and typed
 * column compile/paint run in the Worker; unsupported work fails closed with
 * no JavaScript algorithm fallback.
 */
export class XygWasmWorker {
  private worker: Worker;
  private pending = new Map<number, Pending>();
  private nextRequestId = 1;
  private nextSequence = 1;
  private disposed = false;
  private readonly maxArenaBytes: number;
  readonly ready: Promise<XygWasmDiagnostics>;

  constructor(options: XygWasmWorkerOptions) {
    if (!options || !options.workerUrl) {
      throw new TypeError("workerUrl is required; XYG does not guess worker asset paths");
    }
    // Validate and normalize the source before allocating a Worker so a bad
    // source cannot leak an otherwise unreachable worker process.
    const loaded = sourceMessage(options.wasm);
    const maxArenaBytes = options.maxArenaBytes ?? 16 * 1024 * 1024;
    if (!Number.isInteger(maxArenaBytes) || maxArenaBytes <= 0 || maxArenaBytes > XYG_WASM_MAX_ARENA_BYTES) {
      throw new RangeError(`maxArenaBytes must be an integer in 1..${XYG_WASM_MAX_ARENA_BYTES}`);
    }
    this.maxArenaBytes = maxArenaBytes;
    this.worker = new Worker(String(options.workerUrl), {
      type: "module",
      name: "xyg-wasm",
    });
    this.worker.onmessage = (event) => this.onMessage(event.data);
    this.worker.onerror = (event) => {
      this.failAll(new XygWasmError("XYG_WASM_WORKER_TRAP", event.message || "worker trapped"));
      this.worker.terminate();
      this.disposed = true;
    };
    this.worker.onmessageerror = () => {
      this.failAll(new XygWasmError(
        "XYG_WASM_MESSAGE_ERROR",
        "worker returned an unreadable message",
      ));
      this.worker.terminate();
      this.disposed = true;
    };
    const requestId = this.allocateRequest();
    this.ready = this.promiseFor<XygWasmDiagnostics>(requestId);
    try {
      this.worker.postMessage(
        {
          type: "init",
          requestId,
          source: loaded.source,
          maxArenaBytes,
          expectedAbiVersion: XYG_WASM_ABI_VERSION,
          expectedSceneVersion: XYG_WASM_SCENE_VERSION,
        },
        loaded.transfer,
      );
    } catch (cause) {
      this.pending.delete(requestId);
      this.worker.terminate();
      this.disposed = true;
      throw new XygWasmError(
        "XYG_WASM_INIT_FAILED",
        cause instanceof Error ? cause.message : "could not initialize the WASM worker",
      );
    }
  }

  validateScene(
    scene: ArrayBuffer | Uint8Array,
    options: { sequence?: number; transfer?: boolean } = {},
  ): XygWasmTask<XygWasmSceneValidation> {
    return this.sceneTask("scene.validate", scene, options);
  }

  prepareScene(
    scene: ArrayBuffer | Uint8Array,
    options: { sequence?: number; transfer?: boolean } = {},
  ): XygWasmTask<XygWasmScenePaint> {
    return this.sceneTask("scene.paint", scene, options);
  }

  /** Compile a packed `XYCC` typed-column request into canonical Scene bytes. */
  compileScene(
    request: ArrayBuffer | Uint8Array,
    options: { sequence?: number; transfer?: boolean } = {},
  ): XygWasmTask<XygWasmCompiledScene> {
    return this.sceneTask("scene.compile", request, options);
  }

  /** Compile packed typed columns and lower the Scene for browser paint. */
  compilePrepareScene(
    request: ArrayBuffer | Uint8Array,
    options: { sequence?: number; transfer?: boolean } = {},
  ): XygWasmTask<XygWasmScenePaint> {
    return this.sceneTask("scene.compile_paint", request, options);
  }

  /** Transfer typed columns without main-thread record expansion. */
  compilePrepareSeries(
    request: XygWasmTypedSeriesRequest,
    options: { sequence?: number; transfer?: boolean } = {},
  ): XygWasmTask<XygWasmScenePaint> {
    this.assertLive();
    if (!(request?.prefix instanceof ArrayBuffer) || !Array.isArray(request.columns)) {
      throw new TypeError("typed-series request is malformed");
    }
    const buffers = [request.prefix, ...request.columns];
    if (request.columns.some((column) => !(column instanceof ArrayBuffer))
        || new Set(buffers).size !== buffers.length) {
      throw new TypeError("typed-series request requires distinct ArrayBuffers");
    }
    const actualBytes = buffers.reduce((total, buffer) => total + buffer.byteLength, 0);
    if (!Number.isSafeInteger(actualBytes) || actualBytes !== request.byteLength) {
      throw new TypeError("typed-series buffers do not match byteLength");
    }
    if (!Number.isSafeInteger(request.byteLength) || request.byteLength <= 0
        || request.byteLength > this.maxArenaBytes) {
      throw new RangeError("typed-series request exceeds the worker arena byte budget");
    }
    if (!Number.isSafeInteger(request.peakBytes) || request.peakBytes < request.byteLength
        || request.peakBytes > this.maxArenaBytes) {
      throw new RangeError("typed-series request exceeds the worker peak byte budget");
    }
    const sequence = options.sequence ?? this.nextSequence++;
    if (!Number.isInteger(sequence) || sequence <= 0 || sequence > 0xffffffff) {
      throw new RangeError("sequence must be a nonzero u32");
    }
    this.nextSequence = Math.max(this.nextSequence, sequence + 1);
    const requestId = this.allocateRequest();
    const result = this.promiseFor<XygWasmScenePaint>(requestId);
    const transfer = options.transfer === true ? buffers : [];
    try {
      this.worker.postMessage(
        { type: "series.compile_paint", requestId, sequence, ...request },
        transfer,
      );
    } catch (cause) {
      this.pending.delete(requestId);
      throw new XygWasmError("XYG_WASM_INVALID_ARGUMENT", cause instanceof Error ? cause.message : "could not transfer typed series");
    }
    return {
      requestId, sequence, result,
      cancel: () => {
        const pending = this.pending.get(requestId); if (!pending) return;
        this.pending.delete(requestId);
        pending.reject(new XygWasmError("XYG_WASM_CANCELLED", "request was cancelled", 6));
        if (!this.disposed) this.worker.postMessage({ type: "cancel", requestId, sequence });
      },
    };
  }

  /**
   * Bin a packed `XYAG` aggregate request. Returns a transferable `XYAO`
   * buffer; callers decode width/height/grid via `decodeWasmAggregateOutput`.
   */
  aggregateBin2d(
    request: ArrayBuffer | Uint8Array,
    options: XygWasmAggregateTaskOptions = {},
  ): XygWasmTask<XygWasmSceneValidation & { aggregate: ArrayBuffer }> {
    return this.sceneTask("aggregate.bin2d", request, options);
  }

  private sceneTask<T extends XygWasmSceneValidation>(
    type:
      | "scene.validate"
      | "scene.paint"
      | "scene.compile"
      | "scene.compile_paint"
      | "aggregate.bin2d",
    scene: ArrayBuffer | Uint8Array,
    options: { sequence?: number; transfer?: boolean },
  ): XygWasmTask<T> {
    this.assertLive();
    if (type === "aggregate.bin2d") {
      if (options.transfer === false) {
        throw new XygWasmError(
          "XYG_WASM_INVALID_ARGUMENT",
          "aggregate requests must transfer ownership; transfer: false is not supported",
          2,
        );
      }
    }
    const transfer = options.transfer !== false;
    const requestId = this.allocateRequest();
    const sequence = options.sequence ?? this.nextSequence++;
    if (!Number.isInteger(sequence) || sequence <= 0 || sequence > 0xffffffff) {
      throw new RangeError("sequence must be a nonzero u32");
    }
    this.nextSequence = Math.max(this.nextSequence, sequence + 1);
    const payload = sceneMessage(scene, transfer);
    const result = this.promiseFor<T>(requestId);
    try {
      this.worker.postMessage(
        { type, requestId, sequence, scene: payload.buffer },
        payload.transfer,
      );
    } catch (cause) {
      this.pending.delete(requestId);
      throw new XygWasmError(
        "XYG_WASM_INVALID_ARGUMENT",
        cause instanceof Error ? cause.message : "could not post the scene to the worker",
      );
    }
    return {
      requestId,
      sequence,
      result,
      cancel: () => {
        const pending = this.pending.get(requestId);
        if (!pending) return;
        this.pending.delete(requestId);
        pending.reject(new XygWasmError("XYG_WASM_CANCELLED", "request was cancelled", 6));
        if (!this.disposed) {
          this.worker.postMessage({ type: "cancel", requestId, sequence });
        }
      },
    };
  }

  async dispose(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    const requestId = this.allocateRequest();
    const complete = this.promiseFor<void>(requestId);
    let timeout: ReturnType<typeof setTimeout> | undefined;
    try {
      this.worker.postMessage({ type: "dispose", requestId });
      // A trapped or wedged worker must not make application teardown hang.
      await Promise.race([
        complete,
        new Promise<void>((resolve) => {
          timeout = setTimeout(resolve, 1_000);
        }),
      ]);
    } catch {
      // Termination below is the bounded fallback when messaging is broken.
    } finally {
      if (timeout !== undefined) clearTimeout(timeout);
      this.worker.terminate();
      this.failAll(new XygWasmError("XYG_WASM_DISPOSED", "worker was disposed"));
    }
  }

  private allocateRequest(): number {
    const requestId = this.nextRequestId++;
    if (!Number.isSafeInteger(requestId)) throw new Error("XYG WASM request id exhausted");
    return requestId;
  }

  private promiseFor<T>(requestId: number): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      this.pending.set(requestId, { resolve, reject });
    });
  }

  private onMessage(message: any) {
    const pending = this.pending.get(message?.requestId);
    if (!pending) return;
    this.pending.delete(message.requestId);
    if (message.ok) pending.resolve(message.value);
    else pending.reject(workerError(message.error));
  }

  private failAll(error: XygWasmError) {
    for (const pending of this.pending.values()) pending.reject(error);
    this.pending.clear();
  }

  private assertLive() {
    if (this.disposed) throw new XygWasmError("XYG_WASM_DISPOSED", "worker was disposed");
  }
}

export function createXygWasmWorker(options: XygWasmWorkerOptions): XygWasmWorker {
  return new XygWasmWorker(options);
}
