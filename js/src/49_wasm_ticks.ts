import {
  XygWasmError,
  type XygWasmTask,
  type XygWasmWorker,
} from "./47_wasm";
import type { ChartView } from "./50_chartview";
import {
  XYG_WASM_MAX_ARENA_BYTES,
  XYG_WASM_TICKS_FAMILIES,
  XYG_WASM_TICKS_MAGIC,
  XYG_WASM_TICKS_MAX_AXES,
  XYG_WASM_TICKS_MAX_CATEGORIES_PER_AXIS,
  XYG_WASM_TICKS_MAX_FORMAT_BYTES,
  XYG_WASM_TICKS_MAX_LABEL_BYTES,
  XYG_WASM_TICKS_MAX_TICKS_PER_AXIS,
  XYG_WASM_TICKS_OUTPUT_DESCRIPTOR_BYTES,
  XYG_WASM_TICKS_OUTPUT_DESCRIPTOR_OFFSETS,
  XYG_WASM_TICKS_OUTPUT_HEADER_BYTES,
  XYG_WASM_TICKS_OUTPUT_HEADER_OFFSETS,
  XYG_WASM_TICKS_OUTPUT_MAGIC,
  XYG_WASM_TICKS_PROVENANCE,
  XYG_WASM_TICKS_REQUEST_DESCRIPTOR_BYTES,
  XYG_WASM_TICKS_REQUEST_DESCRIPTOR_OFFSETS,
  XYG_WASM_TICKS_REQUEST_HEADER_BYTES,
  XYG_WASM_TICKS_REQUEST_HEADER_OFFSETS,
  XYG_WASM_TICKS_VERSION,
} from "./wasm_abi_generated";

const TICK_MAGIC = XYG_WASM_TICKS_MAGIC;
const TICK_OUTPUT_MAGIC = XYG_WASM_TICKS_OUTPUT_MAGIC;
const TICK_VERSION = XYG_WASM_TICKS_VERSION;
const REQUEST_HEADER_BYTES = XYG_WASM_TICKS_REQUEST_HEADER_BYTES;
const REQUEST_DESCRIPTOR_BYTES = XYG_WASM_TICKS_REQUEST_DESCRIPTOR_BYTES;
const OUTPUT_HEADER_BYTES = XYG_WASM_TICKS_OUTPUT_HEADER_BYTES;
const OUTPUT_DESCRIPTOR_BYTES = XYG_WASM_TICKS_OUTPUT_DESCRIPTOR_BYTES;
const MAX_AXES = XYG_WASM_TICKS_MAX_AXES;
const MAX_TICKS = XYG_WASM_TICKS_MAX_TICKS_PER_AXIS;
const MAX_TEXT_BYTES = XYG_WASM_TICKS_MAX_LABEL_BYTES;
const MAX_FORMAT_BYTES = XYG_WASM_TICKS_MAX_FORMAT_BYTES;
const FAMILIES = XYG_WASM_TICKS_FAMILIES;
const PROVENANCE = XYG_WASM_TICKS_PROVENANCE;
const H = XYG_WASM_TICKS_REQUEST_HEADER_OFFSETS;
const D = XYG_WASM_TICKS_REQUEST_DESCRIPTOR_OFFSETS;
const OH = XYG_WASM_TICKS_OUTPUT_HEADER_OFFSETS;
const OD = XYG_WASM_TICKS_OUTPUT_DESCRIPTOR_OFFSETS;

export type XygWasmTickFamily = keyof typeof FAMILIES;
export type XygWasmTickProvenance = keyof typeof PROVENANCE;

export interface XygWasmTickAxisRequest {
  axisId: number;
  revision: number;
  family: XygWasmTickFamily;
  provenance: XygWasmTickProvenance;
  lo: number;
  hi: number;
  target: number;
  constant?: number;
  maskNonpositive?: boolean;
  authoredValues?: readonly number[];
  authoredLabels?: readonly string[];
  categories?: readonly string[];
  format?: string;
}

export interface XygWasmTickBatchRequest {
  sequence: number;
  axes: readonly XygWasmTickAxisRequest[];
}

export interface XygWasmTickAxisResult {
  axisId: number;
  revision: number;
  provenance: XygWasmTickProvenance;
  step: number;
  ticks: readonly number[];
  labeledValues: readonly number[];
  labels: readonly string[];
}

export interface XygWasmTickBatchResult {
  sequence: number;
  axes: readonly XygWasmTickAxisResult[];
}

const encoder = new TextEncoder();
const decoder = new TextDecoder("utf-8", { fatal: true });

function magic(bytes: Uint8Array, value: string, offset = 0) {
  bytes.set(Array.from(value, (character) => character.charCodeAt(0)), offset);
}

function matchesMagic(bytes: Uint8Array, value: string): boolean {
  return value.length === 4
    && bytes.length >= 4
    && value.split("").every((character, index) => bytes[index] === character.charCodeAt(0));
}

function u32(value: unknown, name: string, positive = false): number {
  if (!Number.isSafeInteger(value) || Number(value) < (positive ? 1 : 0)
      || Number(value) > 0xffff_ffff) {
    throw new TypeError(`${name} must be a ${positive ? "positive " : ""}u32 integer`);
  }
  return Number(value);
}

function finite(value: unknown, name: string): number {
  const result = Number(value);
  if (!Number.isFinite(result)) throw new TypeError(`${name} must be finite`);
  return result;
}

function strings(
  values: readonly string[] | undefined,
  name: string,
): { values: readonly string[]; encoded: readonly Uint8Array[]; bytes: number } {
  if (values === undefined) return { values: [], encoded: [], bytes: 0 };
  if (!Array.isArray(values) || values.some((value) => typeof value !== "string")) {
    throw new TypeError(`${name} must be an array of strings`);
  }
  const encoded = values.map((value) => {
    if (value.includes("\0")) throw new TypeError(`${name} must not contain NUL`);
    return encoder.encode(value);
  });
  const bytes = encoded.reduce((sum, value) => sum + value.byteLength, 0);
  if (!Number.isSafeInteger(bytes) || bytes > MAX_TEXT_BYTES) {
    throw new RangeError(`${name} exceeds the Rust text bound`);
  }
  return { values, encoded, bytes };
}

interface FramedAxis {
  axisId: number;
  revision: number;
  family: number;
  provenance: number;
  target: number;
  lo: number;
  hi: number;
  constant: number;
  flags: number;
  authored: readonly number[];
  authoredLabels: ReturnType<typeof strings>;
  categories: ReturnType<typeof strings>;
  format: Uint8Array;
}

function frameAxis(axis: XygWasmTickAxisRequest): FramedAxis {
  if (!axis || typeof axis !== "object" || Array.isArray(axis)) {
    throw new TypeError("tick axes must be objects");
  }
  if (!Object.hasOwn(FAMILIES, axis.family)) throw new TypeError("tick family is invalid");
  if (!Object.hasOwn(PROVENANCE, axis.provenance)) throw new TypeError("tick provenance is invalid");
  const axisId = u32(axis.axisId, "axisId", true);
  const revision = u32(axis.revision, "axis revision", true);
  const target = u32(axis.target, "tick target", true);
  if (target > MAX_TICKS) throw new RangeError(`tick target exceeds ${MAX_TICKS}`);
  const lo = finite(axis.lo, "tick lo"), hi = finite(axis.hi, "tick hi");
  const constant = axis.constant === undefined ? 1 : finite(axis.constant, "symlog constant");
  if (axis.family === "symlog" && !(constant > 0)) {
    throw new RangeError("symlog constant must be positive");
  }
  if (axis.maskNonpositive !== undefined && typeof axis.maskNonpositive !== "boolean") {
    throw new TypeError("maskNonpositive must be boolean");
  }
  if (axis.maskNonpositive && axis.family !== "log") {
    throw new TypeError("maskNonpositive is only valid for log ticks");
  }
  const authored = axis.authoredValues === undefined
    ? []
    : Array.from(axis.authoredValues, (value) => finite(value, "authored tick value"));
  if (authored.length > MAX_TICKS) throw new RangeError("authored ticks exceed the Rust bound");
  const authoredLabels = strings(axis.authoredLabels, "authored tick labels");
  if (authoredLabels.values.length !== 0 && authoredLabels.values.length !== authored.length) {
    throw new RangeError("authored labels must be empty or match authored values");
  }
  if (axis.provenance === "automatic" && (authored.length || authoredLabels.values.length)) {
    throw new TypeError("automatic tick requests cannot contain authored values or labels");
  }
  if (axis.provenance === "authored_values" && authored.length === 0) {
    throw new TypeError("authored_values provenance requires at least one authored value");
  }
  if (axis.provenance === "authored_empty" && (authored.length || authoredLabels.values.length)) {
    throw new TypeError("authored_empty provenance requires empty authored planes");
  }
  const categories = strings(axis.categories, "tick categories");
  u32(categories.values.length, "tick category count");
  if (categories.values.length > XYG_WASM_TICKS_MAX_CATEGORIES_PER_AXIS) {
    throw new RangeError("tick categories exceed the Rust bound");
  }
  if (axis.family === "category" && categories.values.length === 0) {
    throw new TypeError("category ticks require at least one category");
  }
  if (axis.family !== "category" && categories.values.length) {
    throw new TypeError("categories are only valid for category ticks");
  }
  const formatText = axis.format ?? "";
  if (typeof formatText !== "string" || formatText.includes("\0")) {
    throw new TypeError("tick format must be a NUL-free string");
  }
  const format = encoder.encode(formatText);
  if (format.byteLength > MAX_FORMAT_BYTES) throw new RangeError("tick format exceeds the Rust bound");
  if (authoredLabels.bytes + categories.bytes > MAX_TEXT_BYTES) {
    throw new RangeError("tick text exceeds the Rust batch bound");
  }
  return {
    axisId,
    revision,
    family: FAMILIES[axis.family],
    provenance: PROVENANCE[axis.provenance],
    target,
    lo,
    hi,
    constant,
    flags: axis.maskNonpositive ? 1 : 0,
    authored,
    authoredLabels,
    categories,
    format,
  };
}

/** Frame one atomic, independently sequenced XYTK v1 batch. */
export function encodeWasmTickBatch(request: XygWasmTickBatchRequest): ArrayBuffer {
  if (!request || typeof request !== "object" || Array.isArray(request)) {
    throw new TypeError("tick request must be an object");
  }
  const sequence = u32(request.sequence, "tick sequence", true);
  if (!Array.isArray(request.axes) || request.axes.length === 0 || request.axes.length > MAX_AXES) {
    throw new RangeError(`tick request must contain 1..${MAX_AXES} axes`);
  }
  const axes = request.axes.map(frameAxis);
  if (new Set(axes.map((axis) => axis.axisId)).size !== axes.length) {
    throw new TypeError("tick axis ids must be unique within a batch");
  }
  let total = REQUEST_HEADER_BYTES + axes.length * REQUEST_DESCRIPTOR_BYTES;
  for (const axis of axes) {
    total += axis.authored.length * 8;
    total += axis.authoredLabels.values.length * 4 + axis.authoredLabels.bytes;
    total += axis.categories.values.length * 4 + axis.categories.bytes;
    total += axis.format.byteLength;
  }
  if (!Number.isSafeInteger(total) || total > 0xffff_ffff || total > XYG_WASM_MAX_ARENA_BYTES) {
    throw new RangeError("tick batch byte length exceeds the Rust arena bound");
  }
  const buffer = new ArrayBuffer(total), bytes = new Uint8Array(buffer), view = new DataView(buffer);
  magic(bytes, TICK_MAGIC);
  view.setUint32(H.version, TICK_VERSION, true);
  view.setUint32(H.header_bytes, REQUEST_HEADER_BYTES, true);
  view.setUint32(H.sequence, sequence, true);
  view.setUint32(H.axis_count, axes.length, true);
  view.setUint32(H.descriptor_bytes, REQUEST_DESCRIPTOR_BYTES, true);
  view.setUint32(H.total_bytes, total, true);
  let cursor = REQUEST_HEADER_BYTES + axes.length * REQUEST_DESCRIPTOR_BYTES;
  const writePlane = (descriptor: number, slot: number, data: Uint8Array): number => {
    if (data.byteLength === 0) {
      // Rust's canonical request form parks absent planes at the final batch
      // boundary so equal-offset zero ranges cannot precede real tail bytes.
      view.setUint32(descriptor + slot, total, true);
      return cursor;
    }
    view.setUint32(descriptor + slot, cursor, true);
    bytes.set(data, cursor);
    cursor += data.byteLength;
    return cursor;
  };
  axes.forEach((axis, index) => {
    const descriptor = REQUEST_HEADER_BYTES + index * REQUEST_DESCRIPTOR_BYTES;
    view.setUint32(descriptor + D.axis_id, axis.axisId, true);
    view.setUint32(descriptor + D.revision, axis.revision, true);
    view.setUint32(descriptor + D.family, axis.family, true);
    view.setUint32(descriptor + D.flags, axis.flags, true);
    view.setUint32(descriptor + D.provenance, axis.provenance, true);
    view.setUint32(descriptor + D.target, axis.target, true);
    view.setUint32(descriptor + D.authored_count, axis.authored.length, true);
    view.setUint32(descriptor + D.authored_label_count, axis.authoredLabels.values.length, true);
    view.setUint32(descriptor + D.category_count, axis.categories.values.length, true);
    view.setUint32(descriptor + D.format_len, axis.format.byteLength, true);
    view.setUint32(descriptor + D.authored_labels_text_len, axis.authoredLabels.bytes, true);
    view.setUint32(descriptor + D.categories_text_len, axis.categories.bytes, true);
    view.setFloat64(descriptor + D.lo, axis.lo, true);
    view.setFloat64(descriptor + D.hi, axis.hi, true);
    view.setFloat64(descriptor + D.constant, axis.constant, true);

    const authored = new ArrayBuffer(axis.authored.length * 8), authoredView = new DataView(authored);
    axis.authored.forEach((value, authoredIndex) => authoredView.setFloat64(authoredIndex * 8, value, true));
    writePlane(descriptor, D.authored_values, new Uint8Array(authored));

    const authoredLengths = new ArrayBuffer(axis.authoredLabels.values.length * 4);
    const authoredLengthsView = new DataView(authoredLengths);
    axis.authoredLabels.encoded.forEach((value, labelIndex) => authoredLengthsView.setUint32(labelIndex * 4, value.byteLength, true));
    writePlane(descriptor, D.authored_label_lengths, new Uint8Array(authoredLengths));
    writePlane(descriptor, D.authored_label_text, Uint8Array.from(axis.authoredLabels.encoded.flatMap((value) => Array.from(value))));

    const categoryLengths = new ArrayBuffer(axis.categories.values.length * 4);
    const categoryLengthsView = new DataView(categoryLengths);
    axis.categories.encoded.forEach((value, categoryIndex) => categoryLengthsView.setUint32(categoryIndex * 4, value.byteLength, true));
    writePlane(descriptor, D.category_lengths, new Uint8Array(categoryLengths));
    writePlane(descriptor, D.category_text, Uint8Array.from(axis.categories.encoded.flatMap((value) => Array.from(value))));
    writePlane(descriptor, D.format, axis.format);
  });
  if (cursor !== total) throw new Error("tick request framing length mismatch");
  return buffer;
}

function provenanceName(code: number): XygWasmTickProvenance {
  const found = Object.entries(PROVENANCE).find(([, value]) => value === code)?.[0];
  if (!found) throw new TypeError("Rust tick output provenance is invalid");
  return found as XygWasmTickProvenance;
}

/** Decode one all-or-nothing XYTO v1 batch and reject every noncanonical tail. */
export function decodeWasmTickBatch(buffer: ArrayBuffer): XygWasmTickBatchResult {
  if (!(buffer instanceof ArrayBuffer) || buffer.byteLength < OUTPUT_HEADER_BYTES) {
    throw new TypeError("Rust tick output is truncated");
  }
  const bytes = new Uint8Array(buffer), view = new DataView(buffer);
  const sequence = view.getUint32(OH.sequence, true), axisCount = view.getUint32(OH.axis_count, true);
  if (!matchesMagic(bytes, TICK_OUTPUT_MAGIC)
      || view.getUint32(OH.version, true) !== TICK_VERSION
      || view.getUint32(OH.header_bytes, true) !== OUTPUT_HEADER_BYTES
      || sequence === 0 || axisCount === 0 || axisCount > MAX_AXES
      || view.getUint32(OH.descriptor_bytes, true) !== OUTPUT_DESCRIPTOR_BYTES
      || view.getUint32(OH.total_bytes, true) !== buffer.byteLength
      || view.getUint32(OH.reserved, true) !== 0
      || OUTPUT_HEADER_BYTES + axisCount * OUTPUT_DESCRIPTOR_BYTES > buffer.byteLength) {
    throw new TypeError("Rust tick output header is malformed");
  }
  let cursor = OUTPUT_HEADER_BYTES + axisCount * OUTPUT_DESCRIPTOR_BYTES;
  const axes: XygWasmTickAxisResult[] = [];
  const readOffset = (descriptor: number, slot: number, length: number): number => {
    const offset = view.getUint32(descriptor + slot, true);
    if (offset !== cursor || !Number.isSafeInteger(offset + length) || offset + length > bytes.length) {
      throw new TypeError("Rust tick output plane is noncanonical");
    }
    cursor += length;
    return offset;
  };
  for (let index = 0; index < axisCount; index++) {
    const descriptor = OUTPUT_HEADER_BYTES + index * OUTPUT_DESCRIPTOR_BYTES;
    const axisId = view.getUint32(descriptor + OD.axis_id, true), revision = view.getUint32(descriptor + OD.revision, true);
    const provenance = provenanceName(view.getUint32(descriptor + OD.provenance, true));
    const tickCount = view.getUint32(descriptor + OD.tick_count, true);
    const labeledCount = view.getUint32(descriptor + OD.labeled_count, true);
    const textLength = view.getUint32(descriptor + OD.text_len, true);
    const step = view.getFloat64(descriptor + OD.step, true);
    if (axisId === 0 || revision === 0 || tickCount > MAX_TICKS || labeledCount > tickCount
        || textLength > MAX_TEXT_BYTES || !Number.isFinite(step)
        || view.getUint32(descriptor + OD.reserved0, true) !== 0
        || view.getUint32(descriptor + OD.reserved1, true) !== 0
        || bytes.subarray(descriptor + OD.reserved_tail, descriptor + OUTPUT_DESCRIPTOR_BYTES).some(Boolean)) {
      throw new TypeError("Rust tick output descriptor is malformed");
    }
    const ticksOffset = readOffset(descriptor, OD.ticks, tickCount * 8);
    const labeledOffset = readOffset(descriptor, OD.labeled_values, labeledCount * 8);
    const lengthsOffset = readOffset(descriptor, OD.label_lengths, labeledCount * 4);
    const textOffset = readOffset(descriptor, OD.label_text, textLength);
    const ticks = Array.from({ length: tickCount }, (_, tickIndex) => view.getFloat64(ticksOffset + tickIndex * 8, true));
    const labeledValues = Array.from({ length: labeledCount }, (_, tickIndex) => view.getFloat64(labeledOffset + tickIndex * 8, true));
    if (ticks.some((value) => !Number.isFinite(value)) || labeledValues.some((value) => !Number.isFinite(value))) {
      throw new TypeError("Rust tick output contains nonfinite values");
    }
    const lengths = Array.from({ length: labeledCount }, (_, labelIndex) => view.getUint32(lengthsOffset + labelIndex * 4, true));
    if (lengths.reduce((sum, length) => sum + length, 0) !== textLength) {
      throw new TypeError("Rust tick output label lengths are malformed");
    }
    const labels: string[] = [];
    let textCursor = textOffset;
    for (const length of lengths) {
      try { labels.push(decoder.decode(bytes.subarray(textCursor, textCursor + length))); }
      catch { throw new TypeError("Rust tick output label is invalid UTF-8"); }
      textCursor += length;
    }
    const tickSet = new Set(ticks);
    if (labeledValues.some((value) => !tickSet.has(value))) {
      throw new TypeError("Rust labeled tick is absent from the full tick plane");
    }
    axes.push(Object.freeze({
      axisId,
      revision,
      provenance,
      step,
      ticks: Object.freeze(ticks),
      labeledValues: Object.freeze(labeledValues),
      labels: Object.freeze(labels),
    }));
  }
  if (cursor !== bytes.length || new Set(axes.map((axis) => axis.axisId)).size !== axes.length) {
    throw new TypeError("Rust tick output has trailing bytes or duplicate axes");
  }
  return Object.freeze({ sequence, axes: Object.freeze(axes) });
}

/** Invoke the Worker seam while preserving the Worker-owned cancellation id. */
export function resolveWasmTicks(
  worker: XygWasmWorker,
  request: XygWasmTickBatchRequest,
): XygWasmTask<XygWasmTickBatchResult> {
  const task = worker.resolveTicks(encodeWasmTickBatch(request), { sequence: request.sequence });
  return { ...task, result: task.result.then(decodeWasmTickBatch) };
}

export interface XygWasmTicksOptions {
  /** Explicitly provisioned external module Worker and Rust/WASM instance. */
  worker: XygWasmWorker;
  /** Borrow by default; only a dedicated Worker should be owned here. */
  workerOwnership?: "borrow" | "own";
}

export interface XygWasmTicksDiagnostics {
  /** Latest admitted Worker sequence. */
  sequence: number;
  /** Latest admitted ChartView tick revision. */
  revision: number;
  /** Primary Cartesian axes currently served by Rust/WASM. */
  axisIds: readonly ("x" | "y")[];
  /** Requests cancelled by a newer viewport or explicit cancellation. */
  cancellations: number;
}

type PrimaryAxisId = "x" | "y";

interface ChartTickFrame {
  key: string;
  axes: readonly Omit<XygWasmTickAxisRequest, "revision">[];
  axisIds: readonly PrimaryAxisId[];
}

interface ChartTickCache {
  identity: string;
  step: number;
  ticks: readonly number[];
  labeledValues: readonly number[];
  labels: readonly string[];
  labelByValue: ReadonlyMap<number, string>;
}

const PRIMARY_AXIS_CODES: Readonly<Record<PrimaryAxisId, number>> = Object.freeze({
  x: 1,
  y: 2,
});

function asTickError(cause: unknown, malformedOutput = false): XygWasmError {
  if (cause instanceof XygWasmError) return cause;
  return new XygWasmError(
    malformedOutput ? "XYG_WASM_MALFORMED_OUTPUT" : "XYG_WASM_INVALID_ARGUMENT",
    cause instanceof Error
      ? cause.message
      : malformedOutput
        ? "Rust tick output is malformed"
        : "WASM tick request is invalid",
  );
}

/**
 * Latest-wins ChartView adapter for the bounded primary Cartesian-axis slice.
 *
 * Rust owns generation and formatting. TypeScript only snapshots the viewport,
 * frames XYTK, admits a matching XYTO revision, and paints the last admitted
 * cache while a newer request is pending.
 */
export class XygWasmTicksHandle {
  private task: XygWasmTask<XygWasmTickBatchResult> | null = null;
  private requestedKey: string | null = null;
  private admittedKey: string | null = null;
  /** Last snapshot that already emitted wasm_ticks_error. Retries still run. */
  private lastErrorKey: string | null = null;
  private revision = 0;
  private disposed = false;
  private active = false;
  private cancellations = 0;
  private latest: XygWasmTicksDiagnostics | null = null;
  private readonly cache = new Map<PrimaryAxisId, ChartTickCache>();

  constructor(
    private readonly view: ChartView & any,
    private readonly worker: XygWasmWorker,
    private readonly ownWorker: boolean,
  ) {}

  /** Map a ChartView axis key/object onto the primary x/y slot this handle owns. */
  private primarySlot(axisId: unknown): PrimaryAxisId | null {
    if (axisId === "x" || axisId === "y") return axisId;
    const axes = this.view.axes;
    if (axisId && typeof axisId === "object") {
      if (axisId === axes?.x) return "x";
      if (axisId === axes?.y) return "y";
      return this.primarySlot((axisId as { id?: unknown }).id);
    }
    if (axes?.x && axisId === axes.x.id && (axes[axisId as string] == null || axes[axisId as string] === axes.x)) {
      return "x";
    }
    if (axes?.y && axisId === axes.y.id && (axes[axisId as string] == null || axes[axisId as string] === axes.y)) {
      return "y";
    }
    return null;
  }

  private categoryTable(axis: { categories?: unknown }): readonly string[] | null {
    const categories = axis.categories;
    if (!Array.isArray(categories) || categories.length === 0) return null;
    if (categories.some((value) => typeof value !== "string" || value.includes("\0"))) {
      return null;
    }
    return categories;
  }

  private axisFamily(axis: {
    kind?: unknown;
    scale?: unknown;
  }): XygWasmTickFamily | null {
    const kind = axis.kind ?? "linear";
    if (kind === "category") return "category";
    if (kind === "time") return "utc_time";
    if (kind !== "linear") return null;
    const scale = axis.scale ?? "linear";
    if (scale === "log" || scale === "symlog" || scale === "linear") return scale;
    return null;
  }

  /**
   * Map ChartView `tick_values` onto XYTK provenance.
   *
   * A missing array is automatic. `[]` is authored_empty. A well-formed
   * nonempty array is authored_values. Malformed planes stay ineligible so
   * this adapter never claims a cache it cannot frame.
   */
  private authoredPlane(axis: {
    tick_values?: unknown;
    tick_labels?: unknown;
  }): {
    provenance: Exclude<XygWasmTickProvenance, "automatic">;
    values: readonly number[];
    labels: readonly string[];
  } | "invalid" | null {
    if (!Array.isArray(axis.tick_values)) return null;
    if (axis.tick_values.length > MAX_TICKS) return "invalid";
    const values: number[] = [];
    for (const value of axis.tick_values) {
      const numeric = Number(value);
      if (!Number.isFinite(numeric)) return "invalid";
      values.push(numeric);
    }
    const rawLabels = axis.tick_labels;
    let labels: readonly string[] = [];
    if (rawLabels != null) {
      if (!Array.isArray(rawLabels)
          || rawLabels.some((label) => typeof label !== "string" || label.includes("\0"))) {
        return "invalid";
      }
      if (rawLabels.length === 0) {
        labels = [];
      } else if (rawLabels.length !== values.length) {
        return "invalid";
      } else {
        labels = rawLabels;
      }
    }
    if (values.length === 0) {
      return labels.length
        ? "invalid"
        : { provenance: "authored_empty", values, labels };
    }
    return { provenance: "authored_values", values, labels };
  }

  private slotIdentity(slot: PrimaryAxisId): string | null {
    if (!this.slotEligible(slot)) return null;
    const axis = this.view._axis(slot);
    const family = this.axisFamily(axis);
    if (!family) return null;
    const authored = this.authoredPlane(axis);
    if (authored === "invalid") return null;
    return JSON.stringify({
      family,
      format: typeof axis.format === "string" ? axis.format : "",
      categories: family === "category" ? [...(this.categoryTable(axis) ?? [])] : [],
      constant: family === "symlog" ? Number(this.view._axisConstant(slot)) : 0,
      mask: family === "log" && axis.nonpositive === "mask",
      provenance: authored?.provenance ?? "automatic",
      authoredValues: authored?.values ?? [],
      authoredLabels: authored?.labels ?? [],
    });
  }

  private slotEligible(slot: PrimaryAxisId): boolean {
    if (this.view.spec?.coords === "polar") return false;
    const axis = this.view._axis(slot);
    if (!axis || typeof axis !== "object" || axis.theta_unit) {
      return false;
    }
    if (this.authoredPlane(axis) === "invalid") return false;
    const family = this.axisFamily(axis);
    if (family == null) return false;
    return family !== "category" || this.categoryTable(axis) != null;
  }

  /** Policy: this slice can request this primary Cartesian axis. */
  eligible(axisId: unknown): axisId is PrimaryAxisId {
    const slot = this.primarySlot(axisId);
    return slot !== null && this.slotEligible(slot);
  }

  /** Authoritative only after an admitted Rust cache matches the current slot. */
  covers(axisId: unknown): axisId is PrimaryAxisId {
    const slot = this.primarySlot(axisId);
    return slot !== null && this.slotEligible(slot) && this.cache.has(slot)
      && this.cache.get(slot)?.identity === this.slotIdentity(slot);
  }

  /** Internal ChartView resolver. A covered axis never falls through to JS. */
  ticks(axisId: unknown): {
    ticks: readonly number[];
    labels: readonly number[];
    step: number;
    source: "wasm";
  } | null {
    const slot = this.primarySlot(axisId);
    if (!slot || !this.covers(slot)) return null;
    const cached = this.cache.get(slot);
    if (!cached) return null;
    return {
      ticks: cached.ticks,
      labels: cached.labeledValues,
      step: cached.step,
      source: "wasm",
    };
  }

  /** Internal ChartView formatter. Missing output fails closed to no text. */
  label(axisId: unknown, value: number): string | null {
    const slot = this.primarySlot(axisId);
    if (!slot || !this.covers(slot)) return null;
    return this.cache.get(slot)?.labelByValue.get(value) ?? "";
  }

  diagnostics(): XygWasmTicksDiagnostics | null {
    return this.latest
      ? { ...this.latest, axisIds: [...this.latest.axisIds] }
      : null;
  }

  private target(axisId: PrimaryAxisId, family: XygWasmTickFamily): number {
    const fallback = axisId === "x"
      ? Math.max(3, Number(this.view.plot?.w) / (family === "utc_time" ? 90 : 80))
      : Math.max(3, Number(this.view.plot?.h) / 45);
    const target = Number(this.view._axisTickTarget(axisId, fallback));
    return Math.max(1, Math.min(MAX_TICKS, Math.floor(Number.isFinite(target) ? target : 6)));
  }

  private frame(): ChartTickFrame | null {
    const axes: Omit<XygWasmTickAxisRequest, "revision">[] = [];
    const axisIds: PrimaryAxisId[] = [];
    let eligible = 0;
    for (const axisId of ["x", "y"] as const) {
      if (!this.slotEligible(axisId)) continue;
      eligible += 1;
      const axis = this.view._axis(axisId);
      const [loRaw, hiRaw] = this.view._axisRange(axisId);
      const lo = Number(loRaw), hi = Number(hiRaw);
      // A sibling axis with a torn range must not block the finite axis.
      if (!Number.isFinite(lo) || !Number.isFinite(hi)) continue;
      const family = this.axisFamily(axis);
      if (!family) continue;
      const authored = this.authoredPlane(axis);
      if (authored === "invalid") continue;
      axes.push({
        axisId: PRIMARY_AXIS_CODES[axisId],
        family,
        provenance: authored?.provenance ?? "automatic",
        lo,
        hi,
        target: this.target(axisId, family),
        ...(family === "symlog" ? { constant: this.view._axisConstant(axisId) } : {}),
        ...(family === "log" ? { maskNonpositive: axis.nonpositive === "mask" } : {}),
        ...(family === "category" ? { categories: this.categoryTable(axis) ?? [] } : {}),
        ...(authored?.values.length ? { authoredValues: authored.values } : {}),
        ...(authored?.labels.length ? { authoredLabels: authored.labels } : {}),
        ...(typeof axis.format === "string" ? { format: axis.format } : {}),
      });
      axisIds.push(axisId);
    }
    if (!axes.length) {
      if (eligible) throw new TypeError("tick range must be finite");
      return null;
    }
    return {
      // This is request identity, not policy: every field is explicit XYTK
      // ingress or the current screen-bounded target.
      key: JSON.stringify(axes),
      axes,
      axisIds,
    };
  }

  private ownsAttachment(): boolean {
    // Initialize must admit while a previous handle is still installed;
    // after activate(), only the live ChartView attachment may publish.
    return !this.active || this.view._wasmTicks === this;
  }

  private isCurrent(frame: ChartTickFrame, task: XygWasmTask<XygWasmTickBatchResult>): boolean {
    if (this.disposed || this.task !== task || this.requestedKey !== frame.key
        || this.view._destroyed || !this.ownsAttachment()) {
      return false;
    }
    try {
      return this.frame()?.key === frame.key;
    } catch {
      return false;
    }
  }

  private cancelActive() {
    if (!this.task) return;
    this.cancellations += 1;
    const task = this.task;
    this.task = null;
    this.requestedKey = null;
    task.cancel();
  }

  private report(error: XygWasmError, key: string | null = null) {
    if (this.view._destroyed) return;
    if (key != null && this.lastErrorKey === key) return;
    if (key != null) this.lastErrorKey = key;
    this.view._dispatchChartEvent?.("wasm_ticks_error", {
      code: error.code,
      message: error.message,
      diagnostics: error.diagnostics ?? null,
    });
  }

  private async request(
    frame: ChartTickFrame,
    reportFailure: boolean,
    throwFailure: boolean,
  ): Promise<boolean> {
    this.cancelActive();
    if (this.revision >= 0xffff_ffff) {
      const error = new XygWasmError(
        "XYG_WASM_RESOURCE_LIMIT",
        "ChartView tick revision space is exhausted",
        3,
      );
      if (reportFailure) this.report(error);
      if (throwFailure) throw error;
      return false;
    }
    const revision = ++this.revision;
    let task: XygWasmTask<XygWasmTickBatchResult> | null = null;
    try {
      const sequence = this.worker.allocateTickSequence();
      task = resolveWasmTicks(this.worker, {
        sequence,
        axes: frame.axes.map((axis) => ({ ...axis, revision })),
      });
      this.task = task;
      this.requestedKey = frame.key;
      const result = await task.result;
      if (!this.isCurrent(frame, task)) return false;
      if (result.sequence !== sequence || result.axes.length !== frame.axes.length) {
        throw new TypeError("Rust tick output identity does not match the current ChartView batch");
      }
      const next = new Map<PrimaryAxisId, ChartTickCache>();
      for (let index = 0; index < frame.axes.length; index++) {
        const expected = frame.axes[index];
        const axisId = frame.axisIds[index];
        const actual = result.axes[index];
        if (!actual || actual.axisId !== expected.axisId || actual.revision !== revision
            || actual.provenance !== expected.provenance
            || actual.labeledValues.length !== actual.labels.length) {
          throw new TypeError("Rust tick output axis identity is malformed");
        }
        next.set(axisId, {
          identity: this.slotIdentity(axisId) ?? "",
          step: actual.step,
          ticks: actual.ticks,
          labeledValues: actual.labeledValues,
          labels: actual.labels,
          labelByValue: new Map(
            actual.labeledValues.map((value, labelIndex) => [value, actual.labels[labelIndex]]),
          ),
        });
      }
      if (!this.isCurrent(frame, task)) return false;
      for (const [axisId, value] of next) this.cache.set(axisId, value);
      for (const axisId of [...this.cache.keys()]) {
        if (!this.covers(axisId)) this.cache.delete(axisId);
      }
      this.task = null;
      this.requestedKey = null;
      this.admittedKey = frame.key;
      this.lastErrorKey = null;
      this.latest = Object.freeze({
        sequence,
        revision,
        axisIds: Object.freeze([...frame.axisIds]),
        cancellations: this.cancellations,
      });
      if (this.active && !this.disposed && !this.view._destroyed && this.view._wasmTicks === this) {
        // Paint the admitted Rust cache only. Do not `_layout()` here: that
        // rewrites `plot` without moving the marks canvas (geometry lives in
        // `_resize`), and label-driven gutter changes can flip `target` and
        // oscillate with chrome `schedule()`. Gutter feedback is a follow-up.
        this.view.draw();
      }
      return true;
    } catch (cause) {
      if (this.disposed || this.view._destroyed || !this.ownsAttachment()
          || (task && (this.task !== task || this.requestedKey !== frame.key))) {
        return false;
      }
      if (task) {
        this.task = null;
        this.requestedKey = null;
      }
      const error = asTickError(cause, task !== null);
      if (reportFailure) this.report(error, frame.key);
      if (throwFailure) throw error;
      return false;
    }
  }

  /** Resolve a current initial cache before this adapter becomes authoritative. */
  async initialize() {
    await this.worker.ready;
    while (!this.disposed && !this.view._destroyed && this.ownsAttachment()) {
      const frame = this.frame();
      if (!frame) {
        throw new RangeError(
          "attachWasmTicks requires a primary Cartesian linear, log, symlog, category, or UTC-time axis",
        );
      }
      if (await this.request(frame, false, true)) return;
    }
    throw new XygWasmError("XYG_WASM_DISPOSED", "ChartView tick attachment was disposed");
  }

  activate() {
    if (this.disposed) throw new XygWasmError("XYG_WASM_DISPOSED", "tick attachment was disposed");
    this.active = true;
  }

  /** Schedule the latest viewport; identical view/target snapshots are deduplicated. */
  schedule(): number | null {
    if (this.disposed || !this.active || this.view._destroyed) return null;
    let frame: ChartTickFrame | null;
    try {
      frame = this.frame();
    } catch (cause) {
      // Coalesce sticky invalid-frame events. Framing is cheap; a later valid
      // snapshot retries. lastErrorKey must not block Worker retries.
      this.report(asTickError(cause), "invalid-frame");
      return null;
    }
    if (!frame) return this.revision;
    if (frame.key === this.admittedKey || (frame.key === this.requestedKey && this.task)) {
      return this.revision;
    }
    void this.request(frame, true, false);
    return this.revision;
  }

  cancel() {
    this.cancelActive();
  }

  async dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.active = false;
    this.cancelActive();
    if (this.view._wasmTicks === this) this.view._wasmTicks = null;
    if (this.ownWorker) await this.worker.dispose();
  }

  destroy() {
    void this.dispose();
  }
}

/**
 * Attach Rust-owned automatic, authored-value, and authored-empty ticks to
 * supported primary Cartesian axes.
 *
 * Eligible families are linear, log, symlog, category, and UTC-time.
 *
 * The first XYTO batch is admitted before the adapter is installed, so an
 * asset/version failure emits one stable event and rejects without a partial
 * mount. Once installed, covered axes never call the TypeScript generators.
 */
export async function attachWasmTicks(
  view: ChartView & any,
  options: XygWasmTicksOptions,
): Promise<XygWasmTicksHandle> {
  if (!view || typeof view._axisTicks !== "function" || view._destroyed) {
    throw new TypeError("attachWasmTicks requires a live ChartView");
  }
  if (!options || !options.worker) throw new TypeError("worker is required");
  if (options.workerOwnership !== undefined
      && options.workerOwnership !== "borrow"
      && options.workerOwnership !== "own") {
    throw new TypeError("workerOwnership must be borrow or own");
  }
  const handle = new XygWasmTicksHandle(
    view,
    options.worker,
    options.workerOwnership === "own",
  );
  try {
    await handle.initialize();
  } catch (cause) {
    const error = asTickError(cause);
    if (!view._destroyed) view._dispatchChartEvent?.("wasm_ticks_error", {
      code: error.code,
      message: error.message,
      diagnostics: error.diagnostics ?? null,
    });
    await handle.dispose();
    throw error;
  }
  if (view._destroyed) {
    await handle.dispose();
    throw new XygWasmError("XYG_WASM_DISPOSED", "ChartView was destroyed during tick attachment");
  }
  // Sequential re-attach: admit first, then activate, then own the slot,
  // then retire the previous handle. Initialize must be allowed to run
  // while `_wasmTicks` still names the outgoing attachment.
  const previous = view._wasmTicks;
  handle.activate();
  view._wasmTicks = handle;
  previous?.destroy?.();
  // Atomic cutover: paint the admitted Rust cache. Skip `_layout()` here so
  // gutters do not desync the marks canvas or oscillate tick targets.
  view.draw();
  return handle;
}
