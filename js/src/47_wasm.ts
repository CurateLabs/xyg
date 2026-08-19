import {
  XYG_WASM_ABI_VERSION,
  XYG_WASM_SCENE_VERSION,
} from "./wasm_abi_generated";

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
  copyCount: number;
  copyBytesLo: number;
  copyBytesHi: number;
  records: number;
  styles: number;
}

export interface XygWasmSceneValidation extends XygWasmDiagnostics {
  sequence: number;
}

export interface XygWasmTask<T> {
  requestId: number;
  sequence: number;
  result: Promise<T>;
  cancel(): void;
}

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
 * This API does not compile chart specifications yet. It proves explicit
 * static asset loading, bounded JS→WASM copies, exact Scene v3 compatibility,
 * cancellation/stale handling, traps, and deterministic disposal. Unsupported
 * browser chart work fails; it never falls back to JavaScript algorithms.
 */
export class XygWasmWorker {
  private worker: Worker;
  private pending = new Map<number, Pending>();
  private nextRequestId = 1;
  private nextSequence = 1;
  private disposed = false;
  readonly ready: Promise<XygWasmDiagnostics>;

  constructor(options: XygWasmWorkerOptions) {
    if (!options || !options.workerUrl) {
      throw new TypeError("workerUrl is required; XYG does not guess worker asset paths");
    }
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
    const requestId = this.allocateRequest();
    const loaded = sourceMessage(options.wasm);
    this.ready = this.promiseFor<XygWasmDiagnostics>(requestId);
    this.worker.postMessage(
      {
        type: "init",
        requestId,
        source: loaded.source,
        maxArenaBytes: options.maxArenaBytes ?? 16 * 1024 * 1024,
        expectedAbiVersion: XYG_WASM_ABI_VERSION,
        expectedSceneVersion: XYG_WASM_SCENE_VERSION,
      },
      loaded.transfer,
    );
  }

  validateScene(
    scene: ArrayBuffer | Uint8Array,
    options: { sequence?: number; transfer?: boolean } = {},
  ): XygWasmTask<XygWasmSceneValidation> {
    this.assertLive();
    const requestId = this.allocateRequest();
    const sequence = options.sequence ?? this.nextSequence++;
    if (!Number.isInteger(sequence) || sequence <= 0 || sequence > 0xffffffff) {
      throw new RangeError("sequence must be a nonzero u32");
    }
    this.nextSequence = Math.max(this.nextSequence, sequence + 1);
    const payload = sceneMessage(scene, options.transfer !== false);
    const result = this.promiseFor<XygWasmSceneValidation>(requestId);
    this.worker.postMessage(
      { type: "scene.validate", requestId, sequence, scene: payload.buffer },
      payload.transfer,
    );
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
    this.worker.postMessage({ type: "dispose", requestId });
    try {
      await complete;
    } finally {
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
