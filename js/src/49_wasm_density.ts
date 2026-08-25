/**
 * Direct-WASM density refinement for supported ChartView density traces.
 *
 * This is deliberately an adapter over the existing painter/lifecycle rather
 * than a second renderer: Rust owns the XYAG -> XYAO aggregate and ChartView
 * uploads the returned typed grid through its ordinary density texture path.
 * Unsupported charts retain their Rust-authored overview and report an
 * explicit no-refinement diagnostic; they never run a second JS aggregator.
 */
import { aggregateWasmBin2d, decodeWasmAggregateOutput } from "./49_wasm_aggregate";
import {
  createXygWasmWorker,
  XygWasmError,
  type XygWasmTask,
  type XygWasmWorker,
  type XygWasmWorkerOptions,
  type XygInlineWasmWorkerOptions,
} from "./47_wasm";
import { XYG_WASM_AGGREGATE_MAX_POINTS, XYG_WASM_AGGREGATE_TOTAL_MEMORY_BYTES } from "./wasm_abi_generated";
import type { ChartView } from "./50_chartview";

export interface XygWasmDensityInput {
  /** The density trace to refine. */
  traceId: number;
  /** Canonical CPU-side source columns. They remain owned by the caller. */
  x: Float64Array;
  y: Float64Array;
  /** Optional resolved straight-alpha RGBA8 source channel. */
  rgba?: Uint8Array;
}

export interface XygWasmDensityOptions {
  worker: XygWasmWorker;
  /** One explicitly supplied density source (the original convenience form). */
  input?: XygWasmDensityInput;
  /**
   * Explicit sources for every attached density trace.  Requests run in this
   * order because one Rust/WASM instance has one resumable aggregate slot.
   */
  inputs?: readonly XygWasmDensityInput[];
  /** Borrow by default; only an explicitly dedicated Worker is disposed here. */
  workerOwnership?: "borrow" | "own";
  /** Debounce viewport changes; default matches the existing density path. */
  delay?: number;
  /** @internal Keep the standalone retained-sample zoom/home-grid policy. */
  sampleRebin?: boolean;
  /** @internal Automatic split-payload source streams without detaching it. */
  streamSource?: boolean;
}

/** Explicit local assets for one standalone retained-sample density trace. */
export interface XygStandaloneWasmDensityOptions extends XygWasmWorkerOptions {
  delay?: number;
}

/** The packaged ESM client owns these same-origin module assets. */
function packagedDensityWorkerOptions(): XygWasmWorkerOptions {
  return {
    workerUrl: new URL("./wasm-worker.js", import.meta.url),
    wasm: new URL("./xyg-wasm.wasm", import.meta.url),
    // The generated count-only preflight is defined against this full Rust
    // aggregate envelope, not the small retained-sample default.
    maxArenaBytes: XYG_WASM_AGGREGATE_TOTAL_MEMORY_BYTES,
  };
}

export interface XygWasmDensityDiagnostics {
  sequence: number;
  /** Trace whose Rust aggregate produced this snapshot. */
  traceId: number;
  copyCount: number;
  copyBytesLo: number;
  copyBytesHi: number;
  arenaBytes: number;
  arenaHighWaterBytes: number;
  memoryBytes: number;
  memoryHighWaterBytes: number;
}

function fullSourceInput(view: ChartView & any): XygWasmDensityInput | null {
  const source = view.spec?.wasm_density?.source;
  if (source?.kind !== "cartesian-count-f64-stream-v1" || source.ownership !== "retain-host-replay"
      || !Number.isSafeInteger(source.point_count) || source.point_count <= 0
      || source.point_count > XYG_WASM_AGGREGATE_MAX_POINTS || source.capacity !== XYG_WASM_AGGREGATE_MAX_POINTS
      || !Number.isInteger(source.x) || !Number.isInteger(source.y) || !Number.isInteger(source.trace_id)) return null;
  try {
    const x = view._columnView(view._payload, view.spec.columns[source.x]);
    const y = view._columnView(view._payload, view.spec.columns[source.y]);
    const xBuffer = x?.buffer, yBuffer = y?.buffer;
    if (!(x instanceof Float64Array) || !(y instanceof Float64Array) || x.length !== source.point_count || y.length !== x.length
        || !(xBuffer instanceof ArrayBuffer) || !(yBuffer instanceof ArrayBuffer)
        || x.byteOffset !== 0 || y.byteOffset !== 0 || x.byteLength !== xBuffer.byteLength || y.byteLength !== yBuffer.byteLength) return null;
    return { traceId: source.trace_id, x, y };
  } catch { return null; }
}

function validInput(input: XygWasmDensityInput) {
  if (!input || !Number.isInteger(input.traceId) || input.traceId < 0) {
    throw new TypeError("WASM density traceId must be a nonnegative integer");
  }
  if (!(input.x instanceof Float64Array) || !(input.y instanceof Float64Array)
      || input.x.length !== input.y.length || !input.x.length) {
    throw new TypeError("WASM density requires non-empty matching Float64Array x and y columns");
  }
  if (input.rgba !== undefined && (!(input.rgba instanceof Uint8Array)
      || input.rgba.length !== input.x.length * 4)) {
    throw new TypeError("WASM density rgba must contain four bytes per source point");
  }
}

/**
 * Decode the bounded retained sample into the canonical f64 values accepted by
 * XYAG. This is source provisioning, never a TypeScript aggregation path.
 */
function retainedSampleInput(view: ChartView & any, target: any): XygWasmDensityInput | null {
  const cpu = target?.sampleOverlay?._cpu;
  const count = cpu ? Math.min(cpu.x?.length || 0, cpu.y?.length || 0) : 0;
  if (!count || count > 8_000_000) return null;
  const x = new Float64Array(count), y = new Float64Array(count);
  for (let index = 0; index < count; index++) {
    x[index] = view._decodeValue(cpu.x, cpu.xMeta, index);
    y[index] = view._decodeValue(cpu.y, cpu.yMeta, index);
  }
  return {
    traceId: target.trace.id, x, y,
    rgba: view._sampleBinColors(target, count) || undefined,
  };
}

/**
 * Owns only request lifecycle. The ChartView continues to own WebGL textures,
 * view state, and DOM; a late XYAO result is never allowed to mutate either.
 */
export class XygWasmDensityHandle {
  private task: XygWasmTask<any> | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private sequence = 0;
  // Rust's resumable operation sequence identifies individual aggregate
  // requests; a viewport sequence may contain several explicitly attached
  // traces and therefore cannot be reused for every worker request.
  private aggregateSequence = 0;
  private disposed = false;
  private latest: XygWasmDensityDiagnostics | null = null;

  constructor(
    private readonly view: ChartView & any,
    private readonly worker: XygWasmWorker,
    private readonly inputs: readonly XygWasmDensityInput[],
    private readonly ownWorker: boolean,
    private readonly delay: number,
    private readonly sampleRebin: boolean,
    private readonly streamSource = false,
  ) {}

  diagnostics(): XygWasmDensityDiagnostics | null {
    return this.latest ? { ...this.latest } : null;
  }
  /** Evidence/control boundary: cancel only the currently pending viewport. */
  cancel() { this.task?.cancel(); this.task = null; }
  /** @internal Strict-CSP lifecycle evidence only; capability-gated by worker. */
  evidenceLifecycle(action: "malformed" | "resource" | "trap") {
    return this.worker.evidenceLifecycle(action).catch((cause) => {
      const error = cause instanceof XygWasmError ? cause : new XygWasmError(
        "XYG_WASM_WORKER_ERROR", cause instanceof Error ? cause.message : "WASM lifecycle failed",
      );
      this.view._dispatchChartEvent?.("wasm_density_error", {
        code: error.code, message: error.message, diagnostics: error.diagnostics ?? null,
        traceId: this.inputs[0]?.traceId,
      });
      throw error;
    });
  }

  /** Called by ChartView's normal standalone density scheduling path. */
  schedule(viewOverride = this.view.view, options: any = {}) {
    if (this.disposed || this.view._destroyed || this.view._glLost) return;
    const trace = this.inputs.length === 1 ? this.trace(this.inputs[0]) : null;
    if (!trace && !this.inputs.some((input) => this.trace(input))) return;
    if (this.sampleRebin && trace) {
      if (!trace._homeDensity) trace._homeDensity = trace.density;
      const snapshot = this.view._copyView(viewOverride);
      const [vx0, vx1] = this.view._axisRange(trace.xAxis, snapshot);
      const [vy0, vy1] = this.view._axisRange(trace.yAxis, snapshot);
      const [hx0, hx1] = this.view._axisRange(trace.xAxis, this.view.view0);
      const [hy0, hy1] = this.view._axisRange(trace.yAxis, this.view.view0);
      const atHome = Math.abs(vx1 - vx0) >= Math.max(Math.abs(hx1 - hx0), 1e-300) * (1 - 1e-6)
        && Math.abs(vy1 - vy0) >= Math.max(Math.abs(hy1 - hy0), 1e-300) * (1 - 1e-6);
      if (atHome && options.force !== true) {
        if (trace.density !== trace._homeDensity) {
          const home = trace._homeDensity;
          this.view._applySampleRebinGrid(trace, {
            ...home,
            tex: this.view._uploadGrid(home.grid, home.w, home.h, home.normMax || home.max || 1,
              home.rgba, home.filter, this.view._fillOpacity(trace.trace.style)),
          }, false);
        }
        return;
      }
    }
    const sequence = ++this.sequence;
    this.task?.cancel();
    this.task = null;
    if (this.timer !== null) clearTimeout(this.timer);
    const snapshot = this.view._copyView(viewOverride);
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.start(sequence, snapshot, options);
    }, options.delay ?? this.delay);
    return sequence;
  }

  private trace(input: XygWasmDensityInput) {
    return this.view.gpuTraces.find((g: any) =>
      g.tier === "density" && g.trace?.id === input.traceId) || null;
  }

  private async start(sequence: number, snapshot: any, _options: any) {
    if (this.disposed || sequence !== this.sequence || this.view._destroyed || this.view._glLost) return;
    // A worker has one resumable aggregate state.  Serializing independently
    // framed trace requests preserves Rust ownership and permits density
    // traces on different axis scales without a TypeScript aggregate.
    for (const input of this.inputs) {
      await this.startTrace(sequence, snapshot, input);
      if (this.disposed || sequence !== this.sequence || this.view._destroyed || this.view._glLost
          || this.view._wasmDensity !== this) return;
    }
  }

  private async startTrace(sequence: number, snapshot: any, input: XygWasmDensityInput) {
    const g = this.trace(input);
    if (!g) return;
    const [x0, x1] = this.view._axisRange(g.xAxis, snapshot);
    const [y0, y1] = this.view._axisRange(g.yAxis, snapshot);
    const width = Math.max(16, Math.min(2048, Math.round(this.view.plot.w)));
    const height = Math.max(16, Math.min(2048, Math.round(this.view.plot.h)));
    let task: XygWasmTask<any> | null = null;
    try {
      task = this.streamSource
        ? this.worker.aggregateStream(input, { x0: Math.min(x0, x1), x1: Math.max(x0, x1), y0: Math.min(y0, y1), y1: Math.max(y0, y1), width, height }, { sequence: ++this.aggregateSequence })
        : aggregateWasmBin2d(this.worker, {
          x: input.x, y: input.y, rgba: input.rgba,
          x0: Math.min(x0, x1), x1: Math.max(x0, x1),
          y0: Math.min(y0, y1), y1: Math.max(y0, y1), width, height,
        }, { sequence: ++this.aggregateSequence });
      this.task = task;
      const rawResult = await task.result;
      // The XYAS stream returns the same Worker XYAO envelope as the normal
      // adapter. Decode at the shared transport boundary; it is not a
      // JavaScript aggregation path.
      let result = rawResult;
      if (this.streamSource) {
        try {
          result = { ...rawResult, ...decodeWasmAggregateOutput(rawResult.aggregate) };
        } catch (cause) {
          throw new XygWasmError(
            "XYG_WASM_MALFORMED_OUTPUT",
            cause instanceof Error ? cause.message : "aggregate output is malformed",
            null,
            rawResult,
          );
        }
      }
      // The request identity includes this viewport revision. Do not let an
      // older response overwrite a newer pan/zoom, a destroyed chart, or a
      // replacement density attachment.
      if (this.disposed || sequence !== this.sequence || this.task !== task
          || this.view._destroyed || this.view._glLost || this.view._wasmDensity !== this) return;
      const current = this.trace(input);
      if (!current) return;
      this.view._applySampleRebinGrid(current, {
        w: result.width, h: result.height, max: result.maxCount, normMax: result.maxCount,
        colormap: current.density.colormap,
        xRange: [Math.min(x0, x1), Math.max(x0, x1)],
        yRange: [Math.min(y0, y1), Math.max(y0, y1)],
        grid: result.grid, rgba: result.rgba,
        tex: this.view._uploadGrid(result.grid, result.width, result.height,
          result.maxCount || 1, result.rgba, "linear", this.view._fillOpacity(current.trace.style)),
        lut: current.density.lut,
      }, true);
      this.latest = {
        sequence, traceId: input.traceId, copyCount: result.copyCount, copyBytesLo: result.copyBytesLo, copyBytesHi: result.copyBytesHi,
        arenaBytes: result.arenaBytes, arenaHighWaterBytes: result.arenaHighWaterBytes,
        memoryBytes: result.memoryBytes, memoryHighWaterBytes: result.memoryHighWaterBytes,
      };
      this.task = null;
    } catch (cause) {
      // A superseded request is expected and must neither blank the existing
      // density surface nor report a user-visible failure.
      if (this.disposed || sequence !== this.sequence || this.task !== task) return;
      this.task = null;
      const error = cause instanceof XygWasmError ? cause : new XygWasmError(
        "XYG_WASM_INVALID_ARGUMENT", cause instanceof Error ? cause.message : "density aggregate failed",
      );
      this.view._dispatchChartEvent?.("wasm_density_error", {
        code: error.code, message: error.message, diagnostics: error.diagnostics ?? null,
        traceId: input.traceId,
      });
    }
  }

  async dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.sequence++;
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this.task?.cancel();
    this.task = null;
    if (this.view._wasmDensity === this) this.view._wasmDensity = null;
    if (this.ownWorker) await this.worker.dispose();
  }
  destroy() { void this.dispose(); }
}

/** Attach direct Rust/WASM refinement to explicitly sourced density ChartView traces. */
export async function attachWasmDensity(
  view: ChartView & any,
  options: XygWasmDensityOptions,
): Promise<XygWasmDensityHandle> {
  if (!view || typeof view._scheduleSampleRebin !== "function" || view._destroyed) {
    throw new TypeError("attachWasmDensity requires a live ChartView");
  }
  if (!options || !options.worker) throw new TypeError("worker is required");
  const supplied = options.input === undefined ? options.inputs : options.inputs === undefined ? [options.input] : null;
  if (!supplied || !Array.isArray(supplied) || !supplied.length) {
    throw new TypeError("provide exactly one of input or non-empty inputs");
  }
  supplied.forEach(validInput);
  if (new Set(supplied.map((input) => input.traceId)).size !== supplied.length) {
    throw new TypeError("WASM density inputs must name distinct traceIds");
  }
  if (options.workerOwnership !== undefined && options.workerOwnership !== "borrow" && options.workerOwnership !== "own") {
    throw new TypeError("workerOwnership must be borrow or own");
  }
  if (options.delay !== undefined && (!Number.isFinite(options.delay) || options.delay < 0)) {
    throw new TypeError("delay must be a nonnegative finite number");
  }
  await options.worker.ready;
  await view._wasmDensity?.dispose();
  const handle = new XygWasmDensityHandle(
    view, options.worker, supplied, options.workerOwnership === "own", options.delay ?? 120,
    options.sampleRebin === true, options.streamSource === true,
  );
  view._wasmDensity = handle;
  // Fail early for an accidental trace id. The existing density grid stays
  // painted throughout all later updates.
  if (!supplied.every((input) => view.gpuTraces.some((g: any) =>
    g.tier === "density" && g.trace?.id === input.traceId))) {
    await handle.dispose();
    throw new RangeError("each WASM density traceId must name a density trace in this ChartView");
  }
  return handle;
}

/**
 * Locally create a Rust/WASM worker for supported retained-sample density traces
 * in a kernel-less ChartView. Asset URLs/bytes remain explicit: no CDN, path
 * guessing, Blob worker, or TypeScript aggregation is introduced.
 */
export async function attachStandaloneWasmDensity(
  view: ChartView & any,
  options: XygStandaloneWasmDensityOptions,
): Promise<XygWasmDensityHandle> {
  if (!view || typeof view._scheduleSampleRebin !== "function" || view._destroyed || view.comm) {
    throw new TypeError("attachStandaloneWasmDensity requires a live kernel-less ChartView");
  }
  const targets = view.gpuTraces.filter((g: any) =>
    g.tier === "density" && g.sampleOverlay && g.sampleOverlay._cpu,
  );
  if (!targets.length) throw new RangeError("attachStandaloneWasmDensity requires retained-sample density traces");
  const inputs = targets.map((trace: any) => retainedSampleInput(view, trace));
  if (inputs.some((input) => input === null)) throw new RangeError("standalone density sample is empty or unsupported");
  const worker = createXygWasmWorker(options);
  try {
    return await attachWasmDensity(view, {
      worker,
      inputs: inputs as XygWasmDensityInput[],
      workerOwnership: "own",
      delay: options.delay,
      // One trace retains the established home-grid restore policy. Multiple
      // traces keep their independent scale windows and re-aggregate in Rust.
      sampleRebin: targets.length === 1,
    });
  } catch (error) {
    await worker.dispose();
    throw error;
  }
}

/**
 * File-safe counterpart of attachStandaloneWasmDensity. The caller supplies
 * the generated inline artifact from the self-contained document; this path
 * never resolves a module URL or fetches a sibling WASM file.
 */
export async function attachInlineStandaloneWasmDensity(
  view: ChartView & any,
  options: XygInlineWasmWorkerOptions & { delay?: number },
): Promise<XygWasmDensityHandle> {
  if (!view || typeof view._scheduleSampleRebin !== "function" || view._destroyed || view.comm) {
    throw new TypeError("attachInlineStandaloneWasmDensity requires a live kernel-less ChartView");
  }
  const targets = view.gpuTraces.filter((g: any) =>
    g.tier === "density" && g.sampleOverlay && g.sampleOverlay._cpu,
  );
  if (!targets.length) throw new RangeError("inline standalone density requires retained-sample density traces");
  const inputs = targets.map((trace: any) => retainedSampleInput(view, trace));
  if (inputs.some((input) => input === null)) throw new RangeError("inline standalone density sample is empty or unsupported");
  const worker = createXygWasmWorker(options);
  try {
    return await attachWasmDensity(view, {
      worker, inputs: inputs as XygWasmDensityInput[], workerOwnership: "own", delay: options.delay,
      sampleRebin: targets.length === 1,
    });
  } catch (error) { await worker.dispose(); throw error; }
}

/**
 * Begin the normal kernel-backed ChartView migration without an application
 * attachment. Only one retained-sample Cartesian density trace is supported
 * here; other inputs keep the kernel route. The packaged worker is
 * owned by the view and all values cross into Rust through XYAG/XYAO.
 */
export function provisionKernelWasmDensity(
  view: ChartView & any, viewOverride = view?.view, options: any = {},
): Promise<XygWasmDensityHandle | null> | null {
  if (!view || !view.comm || view._destroyed || view._wasmDensity || view._wasmDensityProvision) return null;
  // Only a host that explicitly supplied the bounded retained typed source
  // contract may divert a live kernel request. Older/exported payloads can
  // still carry a sample for paint/hover, but are not a WASM source promise.
  if (view.spec?.wasm_density?.automatic !== true) return null;
  const targets = (view.gpuTraces || []).filter((g: any) =>
    g.tier === "density" && g.sampleOverlay && g.sampleOverlay._cpu,
  );
  const full = fullSourceInput(view);
  if (!full && !targets.length) return null;
  const inputs = full ? [full] : targets.map((target: any) => retainedSampleInput(view, target));
  if (inputs.some((input) => input === null)) return null;
  const typedInputs = inputs as XygWasmDensityInput[];
  const provision = (async () => {
    try {
      const worker = createXygWasmWorker(packagedDensityWorkerOptions());
      const handle = await attachWasmDensity(view, {
        worker, inputs: typedInputs, workerOwnership: "own", delay: 0,
        // attachWasmDensity performs the public Float64Array/trace validation
        // while the source is still live. Do not postMessage-transfer first:
        // that would detach the views before this validation boundary.
        streamSource: full !== null,
      });
      if (view._destroyed || view._wasmDensity !== handle) {
        await handle.dispose();
        return null;
      }
      // The triggering viewport did not wait for worker initialization.
      // Schedule its current revision once ownership is established.
      handle.schedule(viewOverride, { ...options, delay: options.delay ?? 0 });
      return handle;
    } catch (cause) {
      if (!view._destroyed) view._dispatchChartEvent?.("wasm_density_error", {
        code: cause instanceof XygWasmError ? cause.code : "XYG_WASM_WORKER_ERROR",
        message: cause instanceof Error ? cause.message : "WASM density provisioning failed",
        diagnostics: cause instanceof XygWasmError ? cause.diagnostics : null,
        traceId: typedInputs[0].traceId,
      });
      return null;
    } finally {
      view._wasmDensityProvision = null;
    }
  })();
  view._wasmDensityProvision = provision;
  return provision;
}
