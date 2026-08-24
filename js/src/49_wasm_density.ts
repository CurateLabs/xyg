/**
 * Direct-WASM density refinement for a supported ChartView density trace.
 *
 * This is deliberately an adapter over the existing painter/lifecycle rather
 * than a second renderer: Rust owns the XYAG -> XYAO aggregate and ChartView
 * uploads the returned typed grid through its ordinary density texture path.
 * The legacy standalone re-bin worker remains available for unsupported
 * charts while #119 gathers parity and performance evidence.
 */
import { aggregateWasmBin2d } from "./49_wasm_aggregate";
import { XygWasmError, type XygWasmTask, type XygWasmWorker } from "./47_wasm";
import type { ChartView } from "./50_chartview";

export interface XygWasmDensityInput {
  /** The one density trace to refine. Multiple traces remain on the legacy path. */
  traceId: number;
  /** Canonical CPU-side source columns. They remain owned by the caller. */
  x: Float64Array;
  y: Float64Array;
  /** Optional resolved straight-alpha RGBA8 source channel. */
  rgba?: Uint8Array;
}

export interface XygWasmDensityOptions {
  worker: XygWasmWorker;
  input: XygWasmDensityInput;
  /** Borrow by default; only an explicitly dedicated Worker is disposed here. */
  workerOwnership?: "borrow" | "own";
  /** Debounce viewport changes; default matches the existing density path. */
  delay?: number;
}

export interface XygWasmDensityDiagnostics {
  sequence: number;
  copyCount: number;
  copyBytesLo: number;
  copyBytesHi: number;
  arenaBytes: number;
  arenaHighWaterBytes: number;
  memoryBytes: number;
  memoryHighWaterBytes: number;
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
 * Owns only request lifecycle. The ChartView continues to own WebGL textures,
 * view state, and DOM; a late XYAO result is never allowed to mutate either.
 */
export class XygWasmDensityHandle {
  private task: XygWasmTask<any> | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private sequence = 0;
  private disposed = false;
  private latest: XygWasmDensityDiagnostics | null = null;

  constructor(
    private readonly view: ChartView & any,
    private readonly worker: XygWasmWorker,
    private readonly input: XygWasmDensityInput,
    private readonly ownWorker: boolean,
    private readonly delay: number,
  ) {}

  diagnostics(): XygWasmDensityDiagnostics | null {
    return this.latest ? { ...this.latest } : null;
  }

  /** Called by ChartView's normal standalone density scheduling path. */
  schedule(viewOverride = this.view.view, options: any = {}) {
    if (this.disposed || this.view._destroyed || this.view._glLost) return;
    const g = this.trace();
    if (!g) return;
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

  private trace() {
    return this.view.gpuTraces.find((g: any) =>
      g.tier === "density" && g.trace?.id === this.input.traceId) || null;
  }

  private async start(sequence: number, snapshot: any, _options: any) {
    if (this.disposed || sequence !== this.sequence || this.view._destroyed || this.view._glLost) return;
    const g = this.trace();
    if (!g) return;
    const [x0, x1] = this.view._axisRange(g.xAxis, snapshot);
    const [y0, y1] = this.view._axisRange(g.yAxis, snapshot);
    const width = Math.max(16, Math.min(2048, Math.round(this.view.plot.w)));
    const height = Math.max(16, Math.min(2048, Math.round(this.view.plot.h)));
    let task: XygWasmTask<any> | null = null;
    try {
      task = aggregateWasmBin2d(this.worker, {
        x: this.input.x, y: this.input.y, rgba: this.input.rgba,
        x0: Math.min(x0, x1), x1: Math.max(x0, x1),
        y0: Math.min(y0, y1), y1: Math.max(y0, y1), width, height,
      }, { sequence });
      this.task = task;
      const result = await task.result;
      // The request identity includes this viewport revision. Do not let an
      // older response overwrite a newer pan/zoom, a destroyed chart, or a
      // replacement density attachment.
      if (this.disposed || sequence !== this.sequence || this.task !== task
          || this.view._destroyed || this.view._glLost || this.view._wasmDensity !== this) return;
      const current = this.trace();
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
        sequence, copyCount: result.copyCount, copyBytesLo: result.copyBytesLo, copyBytesHi: result.copyBytesHi,
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

/** Attach direct Rust/WASM refinement to one already-painted density ChartView. */
export async function attachWasmDensity(
  view: ChartView & any,
  options: XygWasmDensityOptions,
): Promise<XygWasmDensityHandle> {
  if (!view || typeof view._scheduleSampleRebin !== "function" || view._destroyed) {
    throw new TypeError("attachWasmDensity requires a live ChartView");
  }
  if (!options || !options.worker || !options.input) throw new TypeError("worker and input are required");
  validInput(options.input);
  if (options.workerOwnership !== undefined && options.workerOwnership !== "borrow" && options.workerOwnership !== "own") {
    throw new TypeError("workerOwnership must be borrow or own");
  }
  if (options.delay !== undefined && (!Number.isFinite(options.delay) || options.delay < 0)) {
    throw new TypeError("delay must be a nonnegative finite number");
  }
  await options.worker.ready;
  await view._wasmDensity?.dispose();
  const handle = new XygWasmDensityHandle(
    view, options.worker, options.input, options.workerOwnership === "own", options.delay ?? 120,
  );
  view._wasmDensity = handle;
  // Fail early for an accidental trace id instead of silently retaining the
  // JS fallback. The density grid stays painted throughout all later updates.
  if (!view.gpuTraces.some((g: any) => g.tier === "density" && g.trace?.id === options.input.traceId)) {
    await handle.dispose();
    throw new RangeError("WASM density traceId does not name a density trace in this ChartView");
  }
  return handle;
}
