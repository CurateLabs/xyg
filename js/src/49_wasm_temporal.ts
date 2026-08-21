import { XygWasmWorker } from "./47_wasm";

const MAGIC = 0x43545958; // XYTC little-endian
const RESPONSE_MAGIC = 0x52545958; // XYTR
const VERSION = 1;

export interface XygTemporalEvent {
  groupId: bigint;
  sourceInstance: bigint;
  revision: bigint;
  rangeStart: bigint;
  rangeEnd: bigint;
  cursor: bigint;
  window: bigint;
}

export interface XygTemporalState {
  instanceId: bigint;
  groupId: bigint;
  domainStart: bigint;
  domainEnd: bigint;
  rangeStart: bigint;
  rangeEnd: bigint;
  cursor: bigint;
  window: bigint;
  step: bigint;
  direction: -1 | 1;
  rateMilli: number;
  loop: boolean;
  playing: boolean;
  reducedMotion: boolean;
  disposed: boolean;
  revision: bigint;
}

export interface XygTemporalResult {
  state: XygTemporalState;
  changed: boolean;
  event: XygTemporalEvent | null;
}

export interface XygTemporalControllerOptions {
  instanceId: bigint;
  groupId?: bigint;
  domain: readonly [bigint, bigint];
  cursor?: bigint;
  window?: bigint;
  step?: bigint;
  direction?: -1 | 1;
  rateMilli?: number;
  loop?: boolean;
  reducedMotion?: boolean;
  onEvent?: (event: XygTemporalEvent) => void;
}

function command(op: number, bytes = 16): DataView<ArrayBuffer> {
  const view = new DataView(new ArrayBuffer(bytes));
  view.setUint32(0, MAGIC, true);
  view.setUint32(4, VERSION, true);
  view.setUint32(8, op, true);
  return view;
}

function bool32(view: DataView, offset: number): boolean {
  const value = view.getUint32(offset, true);
  if (value > 1) throw new Error("Rust temporal response contains a non-boolean flag");
  return value === 1;
}

function decode(buffer: ArrayBuffer): XygTemporalResult {
  if (buffer.byteLength !== 176) throw new Error("Rust temporal response has the wrong length");
  const view = new DataView(buffer);
  if (view.getUint32(0, true) !== RESPONSE_MAGIC || view.getUint32(4, true) !== VERSION) {
    throw new Error("Rust temporal response has an incompatible header");
  }
  const flags = view.getUint32(8, true);
  const direction = view.getInt32(88, true);
  if (direction !== -1 && direction !== 1) throw new Error("Rust temporal direction is invalid");
  const state: XygTemporalState = {
    instanceId: view.getBigUint64(16, true), groupId: view.getBigUint64(24, true),
    domainStart: view.getBigInt64(32, true), domainEnd: view.getBigInt64(40, true),
    rangeStart: view.getBigInt64(48, true), rangeEnd: view.getBigInt64(56, true),
    cursor: view.getBigInt64(64, true), window: view.getBigInt64(72, true),
    step: view.getBigInt64(80, true), direction,
    rateMilli: view.getUint32(92, true), loop: bool32(view, 96),
    playing: bool32(view, 100), reducedMotion: bool32(view, 104),
    disposed: bool32(view, 108), revision: view.getBigUint64(112, true),
  };
  const event = (flags & 2) === 0 ? null : {
    groupId: view.getBigUint64(120, true),
    sourceInstance: view.getBigUint64(128, true),
    revision: view.getBigUint64(136, true),
    rangeStart: view.getBigInt64(144, true),
    rangeEnd: view.getBigInt64(152, true),
    cursor: view.getBigInt64(160, true),
    window: view.getBigInt64(168, true),
  };
  return { state, changed: (flags & 1) !== 0, event };
}

/**
 * Accessible browser lifecycle around the Rust/WASM TemporalController.
 * BigInt and packed buffers preserve exact i64/u64 values; this class owns
 * clocks, DOM focus, and event transport only.
 */
export class XygWasmTemporalController {
  private queue: Promise<XygTemporalResult>;
  private frame = 0;
  private lastFrame: number | null = null;
  private tickPending = false;
  private keyTarget: HTMLElement | null = null;
  private keyHandler: ((event: KeyboardEvent) => void) | null = null;
  private readonly onEvent?: (event: XygTemporalEvent) => void;
  state: XygTemporalState;

  private constructor(
    private readonly worker: XygWasmWorker,
    initial: XygTemporalResult,
    onEvent?: (event: XygTemporalEvent) => void,
  ) {
    this.state = initial.state;
    this.queue = Promise.resolve(initial);
    this.onEvent = onEvent;
  }

  static async create(worker: XygWasmWorker, options: XygTemporalControllerOptions) {
    await worker.ready;
    if (!options || typeof options.instanceId !== "bigint" || options.instanceId === 0n
        || !Array.isArray(options.domain) || options.domain.length !== 2) {
      throw new TypeError("instanceId and a two-value bigint domain are required");
    }
    const view = command(1, 88);
    const [start, end] = options.domain;
    const cursor = options.cursor ?? start;
    view.setBigUint64(16, options.instanceId, true);
    view.setBigUint64(24, options.groupId ?? 0n, true);
    view.setBigInt64(32, start, true); view.setBigInt64(40, end, true);
    view.setBigInt64(48, cursor, true); view.setBigInt64(56, options.window ?? 0n, true);
    view.setBigInt64(64, options.step ?? 1n, true);
    view.setInt32(72, options.direction ?? 1, true);
    view.setUint32(76, options.rateMilli ?? 1000, true);
    view.setUint32(80, options.loop === true ? 1 : 0, true);
    const prefersReduced = options.reducedMotion ?? (
      typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches
    );
    view.setUint32(84, prefersReduced ? 1 : 0, true);
    const initial = decode(await worker.temporalCommand(view.buffer));
    return new XygWasmTemporalController(worker, initial, options.onEvent);
  }

  private submit(view: DataView<ArrayBuffer>): Promise<XygTemporalResult> {
    const run = async () => {
      if (this.state.disposed) throw new Error("TemporalController is disposed");
      const result = decode(await this.worker.temporalCommand(view.buffer));
      this.state = result.state;
      if (result.event) this.onEvent?.(result.event);
      this.syncAccessibility();
      return result;
    };
    this.queue = this.queue.then(run, run);
    return this.queue;
  }

  private scalar(op: number, value: bigint | number): Promise<XygTemporalResult> {
    const view = command(op, typeof value === "bigint" ? 24 : 20);
    if (typeof value === "bigint") view.setBigInt64(16, value, true);
    else view.setInt32(16, value, true);
    return this.submit(view);
  }

  setRange(start: bigint, end: bigint) { const view = command(3, 32); view.setBigInt64(16, start, true); view.setBigInt64(24, end, true); return this.submit(view); }
  setCursor(cursor: bigint) { return this.scalar(4, cursor); }
  step() { return this.submit(command(5)); }
  play() { const result = this.submit(command(6)); this.startClock(); return result; }
  pause() { this.stopClock(); return this.submit(command(7)); }
  setRateMilli(rate: number) { return this.scalar(8, rate); }
  setDirection(direction: -1 | 1) { return this.scalar(9, direction); }
  setLoop(enabled: boolean) { return this.scalar(10, enabled ? 1 : 0); }
  setReducedMotion(enabled: boolean) { if (enabled) this.stopClock(); return this.scalar(11, enabled ? 1 : 0); }
  tick(dtMicros: bigint) { return this.scalar(12, dtMicros); }

  applyEvent(event: XygTemporalEvent) {
    const view = command(13, 72);
    view.setBigUint64(16, event.groupId, true); view.setBigUint64(24, event.sourceInstance, true);
    view.setBigUint64(32, event.revision, true); view.setBigInt64(40, event.rangeStart, true);
    view.setBigInt64(48, event.rangeEnd, true); view.setBigInt64(56, event.cursor, true);
    view.setBigInt64(64, event.window, true);
    return this.submit(view);
  }

  private startClock() {
    if (this.frame || this.state.reducedMotion || typeof requestAnimationFrame !== "function") return;
    const frame = (now: number) => {
      if (!this.frame) return;
      const previous = this.lastFrame;
      this.lastFrame = now;
      if (previous !== null && this.state.playing && !this.state.reducedMotion && !this.tickPending) {
        const micros = BigInt(Math.max(0, Math.round((now - previous) * 1000)));
        this.tickPending = true;
        void this.tick(micros).then(() => {
          if (!this.state.playing) this.stopClock();
        }).finally(() => { this.tickPending = false; });
      }
      if (this.frame) this.frame = requestAnimationFrame(frame);
    };
    this.frame = requestAnimationFrame(frame);
  }

  private stopClock() {
    if (this.frame && typeof cancelAnimationFrame === "function") cancelAnimationFrame(this.frame);
    this.frame = 0; this.lastFrame = null; this.tickPending = false;
  }

  bindScrubber(element: HTMLElement, format: (state: XygTemporalState) => string = (state) => `Cursor ${state.cursor}; range ${state.rangeStart} to ${state.rangeEnd}`) {
    this.unbindScrubber();
    this.keyTarget = element; element.tabIndex = 0; element.setAttribute("role", "slider");
    element.setAttribute("aria-label", "Temporal position");
    this.keyHandler = (event) => {
      if (event.key === "ArrowRight" || event.key === "ArrowUp") void this.setDirection(1).then(() => this.step());
      else if (event.key === "ArrowLeft" || event.key === "ArrowDown") void this.setDirection(-1).then(() => this.step());
      else if (event.key === "Home") void this.setCursor(this.state.domainStart);
      else if (event.key === "End") void this.setCursor(this.state.domainEnd - 1n);
      else if (event.key === " ") void (this.state.playing ? this.pause() : this.play());
      else return;
      event.preventDefault();
    };
    element.addEventListener("keydown", this.keyHandler);
    (element as any).__xygTemporalFormat = format;
    this.syncAccessibility();
    return () => this.unbindScrubber();
  }

  private syncAccessibility() {
    if (!this.keyTarget) return;
    const format = (this.keyTarget as any).__xygTemporalFormat as (state: XygTemporalState) => string;
    this.keyTarget.setAttribute("aria-valuetext", format(this.state));
    this.keyTarget.setAttribute("aria-valuemin", this.state.domainStart.toString());
    this.keyTarget.setAttribute("aria-valuemax", (this.state.domainEnd - 1n).toString());
    this.keyTarget.setAttribute("aria-valuenow", this.state.cursor.toString());
  }

  unbindScrubber() {
    if (this.keyTarget && this.keyHandler) this.keyTarget.removeEventListener("keydown", this.keyHandler);
    this.keyTarget = null; this.keyHandler = null;
  }

  async dispose() {
    if (this.state.disposed) return;
    this.stopClock(); this.unbindScrubber();
    const result = await this.submit(command(14));
    this.state = result.state;
  }
}
