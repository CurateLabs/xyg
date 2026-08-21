/**
 * Low-level Node bindings over the shared `xyg_core` C ABI.
 * Composition helpers live in graph.js / figure.js / sankey.js.
 */
export {
  encodeF32,
  encodeF32Values,
  m4Points,
  m4Indices,
  minMax,
  isSorted,
  histogramUniform,
  normalizeF32,
  Column,
  PROTOCOL_VERSION,
} from "./encode.js";

import koffi from "koffi";

import {
  nativeLibraryPath,
  pointer,
  xyAbiVersion,
  xyGraphBuildCsr,
  xyGraphBuildRender,
  xyGraphEdgeRouteSegments,
  xyGraphClusterAggregate,
  xyGraphForceCreate,
  xyGraphForceCreateCose,
  xyGraphForceDestroy,
  xyGraphForceTick,
  xyGraphLayout,
  xyGraphLodDecision,
  xyGraphProjectionCopyEdgeIds,
  xyGraphProjectionCopyEndpoints,
  xyGraphProjectionCopyNodeIds,
  xyGraphProjectionCopyParents,
  xyGraphProjectionCounts,
  xyGraphProjectionCreate,
  xyGraphProjectionDestroy,
  xyGraphSampleEdges,
  xySankeyLayout,
  xyTemporalColumnCopy,
  xyTemporalColumnCreate,
  xyTemporalColumnDestroy,
  xyTemporalColumnMeta,
  xyTemporalColumnTimezone,
  xyTemporalEventsInRange,
  xyTemporalIntervalIndexCreate,
  xyTemporalIntervalIndexDestroy,
  xyTemporalIntervalIndexLen,
  xyTemporalIntervalVisibilityAt,
  xyGeoColumnCrs,
  xyGeoColumnFree,
  xyGeoColumnGeometry,
  xyGeoColumnLen,
  xyGeoColumnNew,
  xyGeoColumnVertexCount,
  xyTemporalControllerApplyEvent,
  xyTemporalControllerCreate,
  xyTemporalControllerDestroy,
  xyTemporalControllerDispose,
  xyTemporalControllerPause,
  xyTemporalControllerPlay,
  xyTemporalControllerPollEvent,
  xyTemporalControllerSetCursor,
  xyTemporalControllerSetDirection,
  xyTemporalControllerSetLoop,
  xyTemporalControllerSetRange,
  xyTemporalControllerSetRateMilli,
  xyTemporalControllerSetReducedMotion,
  xyTemporalControllerSetSelection,
  xyTemporalControllerState,
  xyTemporalControllerStep,
  xyTemporalControllerTick,
  xyTemporalCoordinateDeliver,
  xyTemporalSelectionLimit,
} from "./native.js";

export { nativeLibraryPath };

const U64_MAX = (1n << 64n) - 1n;
const I64_MIN = -(1n << 63n);
const I64_MAX = (1n << 63n) - 1n;

export const GRAPH_LAYOUT_PRESET = 0;
export const GRAPH_LAYOUT_GRID = 1;
export const GRAPH_LAYOUT_CIRCLE = 2;
export const GRAPH_LAYOUT_FORCE = 3;
export const GRAPH_LAYOUT_BREADTHFIRST = 4;
export const GRAPH_LAYOUT_AUTO = 5;
export const GRAPH_LAYOUT_RADIAL = 6;
export const GRAPH_LAYOUT_CONCENTRIC = 7;
export const GRAPH_LAYOUT_HIERARCHICAL = 8;
export const GRAPH_LAYOUT_BARNES_HUT = 9;
export const GRAPH_LAYOUT_SPRING = 10;
export const GRAPH_LAYOUT_FORCEATLAS2 = 11;
export const GRAPH_LAYOUT_KAMADA_KAWAI = 12;
export const GRAPH_LAYOUT_YIFANHU = 13;
export const GRAPH_LAYOUT_LINLOG = 14;
export const GRAPH_LAYOUT_STRESS = 15;
export const GRAPH_LAYOUT_COSE = 16;

export const GRAPH_LAYOUT_IDS = Object.freeze({
  preset: GRAPH_LAYOUT_PRESET,
  grid: GRAPH_LAYOUT_GRID,
  circle: GRAPH_LAYOUT_CIRCLE,
  force: GRAPH_LAYOUT_FORCE,
  fr: GRAPH_LAYOUT_FORCE,
  fruchterman_reingold: GRAPH_LAYOUT_FORCE,
  breadthfirst: GRAPH_LAYOUT_BREADTHFIRST,
  dagre: GRAPH_LAYOUT_HIERARCHICAL,
  hierarchical: GRAPH_LAYOUT_HIERARCHICAL,
  auto: GRAPH_LAYOUT_AUTO,
  radial: GRAPH_LAYOUT_RADIAL,
  concentric: GRAPH_LAYOUT_CONCENTRIC,
  barnes_hut: GRAPH_LAYOUT_BARNES_HUT,
  spring: GRAPH_LAYOUT_SPRING,
  forceatlas2: GRAPH_LAYOUT_FORCEATLAS2,
  fa2: GRAPH_LAYOUT_FORCEATLAS2,
  kamada_kawai: GRAPH_LAYOUT_KAMADA_KAWAI,
  kk: GRAPH_LAYOUT_KAMADA_KAWAI,
  yifanhu: GRAPH_LAYOUT_YIFANHU,
  linlog: GRAPH_LAYOUT_LINLOG,
  stress: GRAPH_LAYOUT_STRESS,
  cose: GRAPH_LAYOUT_COSE,
});

/** Progressive force families that share xyg_graph_force_create/tick. */
export const GRAPH_PROGRESSIVE_FORCE = Object.freeze(
  new Set([
    GRAPH_LAYOUT_FORCE,
    GRAPH_LAYOUT_BARNES_HUT,
    GRAPH_LAYOUT_SPRING,
    GRAPH_LAYOUT_FORCEATLAS2,
    GRAPH_LAYOUT_YIFANHU,
    GRAPH_LAYOUT_LINLOG,
    GRAPH_LAYOUT_KAMADA_KAWAI,
    GRAPH_LAYOUT_STRESS,
    GRAPH_LAYOUT_COSE,
  ]),
);

export const SANKEY_ALIGN_IDS = Object.freeze({
  justify: 0,
  left: 1,
  right: 2,
  center: 3,
});

export class SankeyLayoutError extends Error {
  constructor(code, errNodes, message) {
    super(message);
    this.name = "SankeyLayoutError";
    this.code = code;
    this.errNodes = errNodes;
  }
}

// Packed to match `XygGraphProjectionDescriptor` in crates/xyg-core. The generated
// ABI exposes create as `const void *`, so the host owns this layout.
const GraphProjectionDescriptor = koffi.struct("XygGraphProjectionDescriptor", {
  node_ids: "const void *",
  node_count: "uint64_t",
  edge_ids: "const void *",
  edge_count: "uint64_t",
  source_ids: "const void *",
  target_ids: "const void *",
  parent_ids: "const void *",
  parent_validity: "const void *",
  directed: "uint32_t",
  reserved: "uint32_t",
});

const CoseDescriptor = koffi.struct("XygCoseDescriptor", {
  in_x: "const void *",
  in_y: "const void *",
  pinned: "const void *",
  parents: "const void *",
  ideal_edge_length: "double",
  repulsion_strength: "double",
  gravity_strength: "double",
  cooling_factor: "double",
  overlap_padding: "double",
  component_spacing: "double",
  bounds: "const void *",
  has_bounds: "uint32_t",
  reserved: "uint32_t",
});

const TemporalColumnDescriptor = koffi.struct("XygTemporalColumnDescriptor", {
  values: "const void *",
  validity: "const void *",
  len: "uint64_t",
  unit: "uint32_t",
  timezone: "const void *",
  timezone_len: "uint32_t",
  naive: "uint32_t",
  disambiguation: "uint32_t",
  dst_status: "const void *",
  offset_seconds: "const void *",
  fold_later_offset_seconds: "const void *",
  reserved: "uint32_t",
});

const TemporalIntervalDescriptor = koffi.struct("XygTemporalIntervalDescriptor", {
  starts: "const void *",
  start_valid: "const void *",
  ends: "const void *",
  end_valid: "const void *",
  len: "uint64_t",
  reserved: "uint32_t",
});

const TemporalControllerDescriptor = koffi.struct("XygTemporalControllerDescriptor", {
  instance_id: "uint64_t",
  group_id: "uint64_t",
  domain_start: "int64_t",
  domain_end: "int64_t",
  cursor: "int64_t",
  window: "int64_t",
  step: "int64_t",
  direction: "int32_t",
  rate_milli: "uint32_t",
  loop_enabled: "uint32_t",
  reduced_motion: "uint32_t",
  reserved: "uint32_t",
});

export const TEMPORAL_PRECISION = Object.freeze({
  second: 0,
  millisecond: 1,
  microsecond: 2,
  nanosecond: 3,
});

export const TEMPORAL_DISAMBIGUATION = Object.freeze({
  reject: 0,
  preferEarlier: 1,
  preferLater: 2,
});

export const TEMPORAL_DST = Object.freeze({
  unique: 0,
  gap: 1,
  fold: 2,
});

export const TEMPORAL_DIRECTION = Object.freeze({
  reverse: -1,
  forward: 1,
});

export class TemporalNativeError extends Error {
  constructor(code, message) {
    super(message ?? `native temporal failed with status ${code}`);
    this.name = "TemporalNativeError";
    this.nativeCode = code;
  }
}

export const GEO_GEOMETRY = Object.freeze({
  point: 1,
  linestring: 2,
  polygon: 3,
  multipoint: 4,
  multilinestring: 5,
  multipolygon: 6,
});

export const GEO_CRS = Object.freeze({
  epsg4326: 4326,
  epsg3857: 3857,
});

const GEO_MESSAGES = Object.freeze({
  [-1]: "geographic descriptor is incomplete or inconsistent",
  [-2]: "CRS is not in the certified EPSG:4326 / EPSG:3857 profile",
  [-3]: "geometry kind does not match the supplied offset planes",
  [-4]: "offset planes are malformed or disagree with vertex counts",
  [-5]: "nested geometry parts cannot be null",
  [-6]: "coordinate is non-finite",
  [-7]: "coordinate is outside the declared CRS bounds",
  [-8]: "polygon ring is too short or not closed",
  [-9]: "geometry exceeds feature, vertex, or byte limits",
  [-10]: "geographic column handle is stale or freed",
});

export class GeoNativeError extends Error {
  constructor(code, message) {
    super(message ?? GEO_MESSAGES[code] ?? `native geo failed with status ${code}`);
    this.name = "GeoNativeError";
    this.nativeCode = code;
  }
}

export function abiVersion() {
  return xyAbiVersion();
}

/** Validate and materialize canonical GraphForge identity through Rust. */
export function graphProjectionCreate({
  nodeIds,
  edgeIds,
  sourceIds,
  targetIds,
  parentIds = null,
  parentValidity = null,
  directed = true,
}) {
  const nodeCount = nodeIds.byteLength / 16;
  const edgeCount = edgeIds.byteLength / 16;
  const outHandle = new BigUint64Array(1);
  const encoded = Buffer.alloc(koffi.sizeof(GraphProjectionDescriptor));
  koffi.encode(encoded, GraphProjectionDescriptor, {
    node_ids: pointer(nodeIds, "uint8_t *"),
    node_count: BigInt(nodeCount),
    edge_ids: pointer(edgeIds, "uint8_t *"),
    edge_count: BigInt(edgeCount),
    source_ids: pointer(sourceIds, "uint8_t *"),
    target_ids: pointer(targetIds, "uint8_t *"),
    parent_ids: pointer(parentIds, "uint8_t *"),
    parent_validity: pointer(parentValidity, "uint8_t *"),
    directed: directed ? 1 : 0,
    reserved: 0,
  });
  const code = xyGraphProjectionCreate(koffi.as(encoded, "const void *"), u64Ptr(outHandle));
  if (code !== 0 || outHandle[0] === 0n) {
    const error = new Error(`xyg_graph_projection_create failed with code ${code}`);
    error.nativeCode = code;
    throw error;
  }
  return outHandle[0];
}

export function graphProjectionRead(handle) {
  const nodeCount = new BigUint64Array(1);
  const edgeCount = new BigUint64Array(1);
  const directed = new Uint32Array(1);
  let code = xyGraphProjectionCounts(
    toU64(handle, "handle"), u64Ptr(nodeCount), u64Ptr(edgeCount), u32Ptr(directed),
  );
  if (code !== 0) throw new Error(`xyg_graph_projection_counts failed with code ${code}`);
  const nodes = toLength(nodeCount[0], "nodeCount");
  const edges = toLength(edgeCount[0], "edgeCount");
  const nodeIds = new Uint8Array(nodes * 16);
  const edgeIds = new Uint8Array(edges * 16);
  const sources = new BigUint64Array(edges);
  const targets = new BigUint64Array(edges);
  const parents = new BigUint64Array(nodes);
  const parentValidity = new Uint8Array(nodes);
  code = xyGraphProjectionCopyNodeIds(toU64(handle, "handle"), pointer(nodeIds, "uint8_t *"), BigInt(nodes));
  if (code === 0) code = xyGraphProjectionCopyEdgeIds(toU64(handle, "handle"), pointer(edgeIds, "uint8_t *"), BigInt(edges));
  if (code === 0) code = xyGraphProjectionCopyEndpoints(toU64(handle, "handle"), u64Ptr(sources), u64Ptr(targets), BigInt(edges));
  if (code === 0) code = xyGraphProjectionCopyParents(toU64(handle, "handle"), u64Ptr(parents), pointer(parentValidity, "uint8_t *"), BigInt(nodes));
  if (code !== 0) throw new Error(`xyg_graph_projection_copy failed with code ${code}`);
  return { nodeIds, edgeIds, sources, targets, parents, parentValidity, directed: directed[0] !== 0 };
}

export function graphProjectionDestroy(handle) {
  return xyGraphProjectionDestroy(toU64(handle, "handle")) === 0;
}

/** Create a Rust-owned temporal column (UTC microseconds). */
export function temporalColumnCreate({
  values,
  validity,
  timezone,
  unit = TEMPORAL_PRECISION.microsecond,
  naive = false,
  disambiguation = TEMPORAL_DISAMBIGUATION.reject,
  dstStatus = null,
  offsetSeconds = null,
  foldLaterOffsetSeconds = null,
}) {
  if (typeof timezone !== "string" || timezone.length === 0) {
    throw new TypeError("timezone is required");
  }
  const valueArray = asI64Array(values, "values");
  const validityArray = asU8Array(validity, "validity");
  if (valueArray.length !== validityArray.length) {
    throw new RangeError("values and validity must have equal length");
  }
  let dst = null;
  let offsets = null;
  let foldLater = null;
  if (naive) {
    if (dstStatus == null || offsetSeconds == null || foldLaterOffsetSeconds == null) {
      throw new TypeError("naive ingest requires dstStatus and offset planes");
    }
    dst = asU8Array(dstStatus, "dstStatus");
    offsets = asI32Array(offsetSeconds, "offsetSeconds");
    foldLater = asI32Array(foldLaterOffsetSeconds, "foldLaterOffsetSeconds");
    if (
      dst.length !== valueArray.length
      || offsets.length !== valueArray.length
      || foldLater.length !== valueArray.length
    ) {
      throw new RangeError("naive DST planes must match values length");
    }
  }
  const tz = Buffer.from(timezone, "utf8");
  const outHandle = new BigUint64Array(1);
  const encoded = Buffer.alloc(koffi.sizeof(TemporalColumnDescriptor));
  koffi.encode(encoded, TemporalColumnDescriptor, {
    values: pointer(valueArray, "int64_t *"),
    validity: pointer(validityArray, "uint8_t *"),
    len: BigInt(valueArray.length),
    unit,
    timezone: pointer(tz, "uint8_t *"),
    timezone_len: tz.byteLength,
    naive: naive ? 1 : 0,
    disambiguation,
    dst_status: pointer(dst, "uint8_t *"),
    offset_seconds: pointer(offsets, "int32_t *"),
    fold_later_offset_seconds: pointer(foldLater, "int32_t *"),
    reserved: 0,
  });
  const code = xyTemporalColumnCreate(koffi.as(encoded, "const void *"), u64Ptr(outHandle));
  if (code !== 0 || outHandle[0] === 0n) {
    throw new TemporalNativeError(code);
  }
  return outHandle[0];
}

export function temporalColumnRead(handle) {
  const length = new BigUint64Array(1);
  const precision = new Uint32Array(1);
  const tzLen = new Uint32Array(1);
  let code = xyTemporalColumnMeta(
    toU64(handle, "handle"),
    u64Ptr(length),
    u32Ptr(precision),
    u32Ptr(tzLen),
  );
  if (code !== 0) throw new TemporalNativeError(code);
  const n = toLength(length[0], "length");
  const values = new BigInt64Array(n);
  const validity = new Uint8Array(n);
  code = xyTemporalColumnCopy(
    toU64(handle, "handle"),
    pointer(values, "int64_t *"),
    pointer(validity, "uint8_t *"),
    BigInt(n),
  );
  if (code !== 0) throw new TemporalNativeError(code);
  const tz = Buffer.alloc(tzLen[0]);
  code = xyTemporalColumnTimezone(
    toU64(handle, "handle"),
    pointer(tz, "uint8_t *"),
    tzLen[0],
  );
  if (code !== 0) throw new TemporalNativeError(code);
  return {
    values,
    validity,
    timezone: tz.toString("utf8"),
    precision: precision[0],
  };
}

export function temporalColumnDestroy(handle) {
  const code = xyTemporalColumnDestroy(toU64(handle, "handle"));
  if (code !== 0) throw new TemporalNativeError(code);
  return true;
}

/** Create a Rust-owned geographic column from a typed host descriptor (#47). */
export function geoColumnNew({
  geometry,
  crs,
  xy,
  validity,
  featureIds = null,
  offsets0 = null,
  offsets1 = null,
  offsets2 = null,
}) {
  const coords = asF64Array(xy, "xy");
  const valid = asU8Array(validity, "validity");
  if (coords.length % 2 !== 0) {
    throw new RangeError("xy must be interleaved [x0,y0,…]");
  }
  const ids = featureIds == null ? null : asU64Array(featureIds, "featureIds");
  if (ids != null && ids.length !== valid.length) {
    throw new RangeError("featureIds must match validity length");
  }
  const o0 = offsets0 == null ? new Uint32Array(0) : asU32Array(offsets0, "offsets0");
  const o1 = offsets1 == null ? new Uint32Array(0) : asU32Array(offsets1, "offsets1");
  const o2 = offsets2 == null ? new Uint32Array(0) : asU32Array(offsets2, "offsets2");
  const err = new Int32Array(1);
  const handle = xyGeoColumnNew(
    geometry >>> 0,
    crs >>> 0,
    pointer(coords, "double *"),
    BigInt(coords.length),
    pointer(valid, "uint8_t *"),
    BigInt(valid.length),
    pointer(ids, "uint64_t *"),
    pointer(o0, "uint32_t *"),
    BigInt(o0.length),
    pointer(o1, "uint32_t *"),
    BigInt(o1.length),
    pointer(o2, "uint32_t *"),
    BigInt(o2.length),
    i32Ptr(err),
  );
  if (handle === 0n || handle === 0) {
    throw new GeoNativeError(err[0] || -1);
  }
  return handle;
}

export function geoColumnMeta(handle) {
  const h = toU64(handle, "handle");
  const length = Number(xyGeoColumnLen(h));
  const vertices = Number(xyGeoColumnVertexCount(h));
  if (!Number.isFinite(length) || !Number.isFinite(vertices) || length < 0 || vertices < 0) {
    throw new GeoNativeError(-10);
  }
  // Rust returns usize::MAX on stale handles; treat huge sentinels as errors.
  if (length === Number.MAX_SAFE_INTEGER || vertices === Number.MAX_SAFE_INTEGER) {
    throw new GeoNativeError(-10);
  }
  const geometry = xyGeoColumnGeometry(h) >>> 0;
  const crs = xyGeoColumnCrs(h) >>> 0;
  if (geometry === 0 || crs === 0) throw new GeoNativeError(-10);
  return { length, vertexCount: vertices, geometry, crs };
}

export function geoColumnFree(handle) {
  return xyGeoColumnFree(toU64(handle, "handle")) === 1;
}

export function temporalIntervalIndexCreate({ starts, startValid, ends, endValid }) {
  const startValues = asI64Array(starts, "starts");
  const startBits = asU8Array(startValid, "startValid");
  const endValues = asI64Array(ends, "ends");
  const endBits = asU8Array(endValid, "endValid");
  const n = startValues.length;
  if (startBits.length !== n || endValues.length !== n || endBits.length !== n) {
    throw new RangeError("interval endpoint arrays must have equal length");
  }
  const outHandle = new BigUint64Array(1);
  const encoded = Buffer.alloc(koffi.sizeof(TemporalIntervalDescriptor));
  koffi.encode(encoded, TemporalIntervalDescriptor, {
    starts: pointer(startValues, "int64_t *"),
    start_valid: pointer(startBits, "uint8_t *"),
    ends: pointer(endValues, "int64_t *"),
    end_valid: pointer(endBits, "uint8_t *"),
    len: BigInt(n),
    reserved: 0,
  });
  const code = xyTemporalIntervalIndexCreate(koffi.as(encoded, "const void *"), u64Ptr(outHandle));
  if (code !== 0 || outHandle[0] === 0n) {
    throw new TemporalNativeError(code);
  }
  return outHandle[0];
}

export function temporalIntervalVisibilityAt(handle, instantMicros, opts = {}) {
  const length = new BigUint64Array(1);
  let code = xyTemporalIntervalIndexLen(toU64(handle, "handle"), u64Ptr(length));
  if (code !== 0) throw new TemporalNativeError(code);
  const n = toLength(length[0], "length");
  const budget = opts.budget == null ? n : toLength(opts.budget, "budget");
  if (budget < n) throw new RangeError("budget must be at least index length");
  const out = new Uint8Array(n);
  const cancel = new Uint32Array([opts.cancelFlag ? 1 : 0]);
  code = xyTemporalIntervalVisibilityAt(
    toU64(handle, "handle"),
    BigInt(instantMicros),
    pointer(out, "uint8_t *"),
    BigInt(n),
    BigInt(budget),
    u32Ptr(cancel),
  );
  if (code !== 0) throw new TemporalNativeError(code);
  return out;
}

export function temporalIntervalIndexDestroy(handle) {
  const code = xyTemporalIntervalIndexDestroy(toU64(handle, "handle"));
  if (code !== 0) throw new TemporalNativeError(code);
  return true;
}

export function temporalEventsInRange({
  eventMicros,
  eventValid,
  rangeStart = null,
  rangeEnd = null,
  budget = null,
  cancelFlag = 0,
}) {
  const events = asI64Array(eventMicros, "eventMicros");
  const valid = asU8Array(eventValid, "eventValid");
  if (events.length !== valid.length) {
    throw new RangeError("eventMicros and eventValid must have equal length");
  }
  const n = events.length;
  const rowBudget = budget == null ? n : toLength(budget, "budget");
  if (rowBudget < n) throw new RangeError("budget must be at least event length");
  const out = new Uint8Array(n);
  const cancel = new Uint32Array([cancelFlag ? 1 : 0]);
  const code = xyTemporalEventsInRange(
    pointer(events, "int64_t *"),
    pointer(valid, "uint8_t *"),
    BigInt(n),
    BigInt(rangeStart == null ? 0 : rangeStart),
    rangeStart == null ? 0 : 1,
    BigInt(rangeEnd == null ? 0 : rangeEnd),
    rangeEnd == null ? 0 : 1,
    pointer(out, "uint8_t *"),
    BigInt(n),
    BigInt(rowBudget),
    u32Ptr(cancel),
  );
  if (code !== 0) throw new TemporalNativeError(code);
  return out;
}

function temporalStatus(code) {
  if (code !== 0) throw new TemporalNativeError(code);
}

function asTemporalSelection(value, name) {
  if (value == null || typeof value[Symbol.iterator] !== "function") {
    throw new TypeError(`${name} must be an iterable of u64 stable IDs`);
  }
  const limit = Number(xyTemporalSelectionLimit());
  if (value instanceof BigUint64Array) {
    if (value.length > limit) throw new RangeError(`${name} may contain at most ${limit} IDs`);
    return value;
  }
  const ids = [];
  for (const item of value) {
    if (ids.length >= limit) throw new RangeError(`${name} may contain at most ${limit} IDs`);
    ids.push(toU64(item, `${name}[${ids.length}]`));
  }
  return BigUint64Array.from(ids);
}

export function temporalControllerCreate({
  instanceId,
  domainStart,
  domainEnd,
  cursor = null,
  window: windowUs = 0,
  step = 1,
  direction = TEMPORAL_DIRECTION.forward,
  rateMilli = 1000,
  loopEnabled = false,
  reducedMotion = false,
  groupId = 0,
}) {
  const outHandle = new BigUint64Array(1);
  const encoded = Buffer.alloc(koffi.sizeof(TemporalControllerDescriptor));
  koffi.encode(encoded, TemporalControllerDescriptor, {
    instance_id: toU64(instanceId, "instanceId"),
    group_id: toU64(groupId, "groupId"),
    domain_start: toI64(domainStart, "domainStart"),
    domain_end: toI64(domainEnd, "domainEnd"),
    cursor: toI64(cursor == null ? domainStart : cursor, "cursor"),
    window: toI64(windowUs, "window"),
    step: toI64(step, "step"),
    direction: toI32(direction, "direction"),
    rate_milli: toStrictU32(rateMilli, "rateMilli"),
    loop_enabled: toStrictBool(loopEnabled, "loopEnabled") ? 1 : 0,
    reduced_motion: toStrictBool(reducedMotion, "reducedMotion") ? 1 : 0,
    reserved: 0,
  });
  temporalStatus(xyTemporalControllerCreate(koffi.as(encoded, "const void *"), u64Ptr(outHandle)));
  return outHandle[0];
}

export function temporalControllerState(handle) {
  const instanceId = new BigUint64Array(1);
  const groupId = new BigUint64Array(1);
  const domainStart = new BigInt64Array(1);
  const domainEnd = new BigInt64Array(1);
  const rangeStart = new BigInt64Array(1);
  const rangeEnd = new BigInt64Array(1);
  const cursor = new BigInt64Array(1);
  const windowUs = new BigInt64Array(1);
  const step = new BigInt64Array(1);
  const direction = new Int32Array(1);
  const rateMilli = new Uint32Array(1);
  const loopEnabled = new Uint32Array(1);
  const playing = new Uint32Array(1);
  const reducedMotion = new Uint32Array(1);
  const revision = new BigUint64Array(1);
  const disposed = new Uint32Array(1);
  const selection = new BigUint64Array(Number(xyTemporalSelectionLimit()));
  const selectionCount = new BigUint64Array(1);
  temporalStatus(xyTemporalControllerState(
    toU64(handle, "handle"),
    u64Ptr(instanceId),
    u64Ptr(groupId),
    pointer(domainStart, "int64_t *"),
    pointer(domainEnd, "int64_t *"),
    pointer(rangeStart, "int64_t *"),
    pointer(rangeEnd, "int64_t *"),
    pointer(cursor, "int64_t *"),
    pointer(windowUs, "int64_t *"),
    pointer(step, "int64_t *"),
    pointer(direction, "int32_t *"),
    u32Ptr(rateMilli),
    u32Ptr(loopEnabled),
    u32Ptr(playing),
    u32Ptr(reducedMotion),
    u64Ptr(revision),
    u32Ptr(disposed),
    u64Ptr(selection),
    BigInt(selection.length),
    u64Ptr(selectionCount),
  ));
  return {
    instanceId: instanceId[0],
    groupId: groupId[0],
    domainStart: domainStart[0],
    domainEnd: domainEnd[0],
    rangeStart: rangeStart[0],
    rangeEnd: rangeEnd[0],
    cursor: cursor[0],
    window: windowUs[0],
    step: step[0],
    direction: direction[0],
    rateMilli: rateMilli[0],
    loopEnabled: loopEnabled[0] !== 0,
    playing: playing[0] !== 0,
    reducedMotion: reducedMotion[0] !== 0,
    revision: revision[0],
    disposed: disposed[0] !== 0,
    selection: selection.slice(0, Number(selectionCount[0])),
  };
}

export function temporalControllerSetRange(handle, start, end) {
  temporalStatus(xyTemporalControllerSetRange(
    toU64(handle, "handle"), toI64(start, "start"), toI64(end, "end"),
  ));
}

export function temporalControllerSetCursor(handle, cursor) {
  temporalStatus(xyTemporalControllerSetCursor(toU64(handle, "handle"), toI64(cursor, "cursor")));
}

export function temporalControllerSetSelection(handle, ids) {
  const selection = asTemporalSelection(ids, "selection");
  temporalStatus(xyTemporalControllerSetSelection(
    toU64(handle, "handle"), u64Ptr(selection), BigInt(selection.length),
  ));
}

export function temporalControllerStep(handle) {
  temporalStatus(xyTemporalControllerStep(toU64(handle, "handle")));
}

export function temporalControllerPlay(handle) {
  temporalStatus(xyTemporalControllerPlay(toU64(handle, "handle")));
}

export function temporalControllerPause(handle) {
  temporalStatus(xyTemporalControllerPause(toU64(handle, "handle")));
}

export function temporalControllerSetRateMilli(handle, rateMilli) {
  temporalStatus(xyTemporalControllerSetRateMilli(
    toU64(handle, "handle"), toStrictU32(rateMilli, "rateMilli"),
  ));
}

export function temporalControllerSetDirection(handle, direction) {
  temporalStatus(xyTemporalControllerSetDirection(
    toU64(handle, "handle"), toI32(direction, "direction"),
  ));
}

export function temporalControllerSetLoop(handle, enabled) {
  temporalStatus(xyTemporalControllerSetLoop(
    toU64(handle, "handle"), toStrictBool(enabled, "enabled") ? 1 : 0,
  ));
}

export function temporalControllerSetReducedMotion(handle, enabled) {
  temporalStatus(xyTemporalControllerSetReducedMotion(
    toU64(handle, "handle"), toStrictBool(enabled, "enabled") ? 1 : 0,
  ));
}

export function temporalControllerTick(handle, dtMicros) {
  const advanced = new Uint32Array(1);
  temporalStatus(xyTemporalControllerTick(
    toU64(handle, "handle"), toI64(dtMicros, "dtMicros"), u32Ptr(advanced),
  ));
  return advanced[0] !== 0;
}

export function temporalControllerPollEvent(handle) {
  const hasEvent = new Uint32Array(1);
  const groupId = new BigUint64Array(1);
  const source = new BigUint64Array(1);
  const revision = new BigUint64Array(1);
  const rangeStart = new BigInt64Array(1);
  const rangeEnd = new BigInt64Array(1);
  const cursor = new BigInt64Array(1);
  const windowUs = new BigInt64Array(1);
  const selection = new BigUint64Array(Number(xyTemporalSelectionLimit()));
  const selectionCount = new BigUint64Array(1);
  temporalStatus(xyTemporalControllerPollEvent(
    toU64(handle, "handle"),
    u32Ptr(hasEvent),
    u64Ptr(groupId),
    u64Ptr(source),
    u64Ptr(revision),
    pointer(rangeStart, "int64_t *"),
    pointer(rangeEnd, "int64_t *"),
    pointer(cursor, "int64_t *"),
    pointer(windowUs, "int64_t *"),
    u64Ptr(selection),
    BigInt(selection.length),
    u64Ptr(selectionCount),
  ));
  if (hasEvent[0] === 0) return null;
  return {
    groupId: groupId[0],
    sourceInstance: source[0],
    revision: revision[0],
    rangeStart: rangeStart[0],
    rangeEnd: rangeEnd[0],
    cursor: cursor[0],
    window: windowUs[0],
    selection: selection.slice(0, Number(selectionCount[0])),
  };
}

export function temporalControllerApplyEvent(handle, event) {
  const applied = new Uint32Array(1);
  if (event?.selection == null) throw new TypeError("event.selection is required");
  const selection = asTemporalSelection(event.selection, "event.selection");
  temporalStatus(xyTemporalControllerApplyEvent(
    toU64(handle, "handle"),
    toU64(event.groupId, "groupId"),
    toU64(event.sourceInstance, "sourceInstance"),
    toU64(event.revision, "revision"),
    toI64(event.rangeStart, "rangeStart"),
    toI64(event.rangeEnd, "rangeEnd"),
    toI64(event.cursor, "cursor"),
    toI64(event.window, "window"),
    u64Ptr(selection),
    BigInt(selection.length),
    u32Ptr(applied),
  ));
  return applied[0] !== 0;
}

export function temporalCoordinateDeliver(event) {
  const applied = new Uint32Array(1);
  if (event?.selection == null) throw new TypeError("event.selection is required");
  const selection = asTemporalSelection(event.selection, "event.selection");
  temporalStatus(xyTemporalCoordinateDeliver(
    toU64(event.groupId, "groupId"),
    toU64(event.sourceInstance, "sourceInstance"),
    toU64(event.revision, "revision"),
    toI64(event.rangeStart, "rangeStart"),
    toI64(event.rangeEnd, "rangeEnd"),
    toI64(event.cursor, "cursor"),
    toI64(event.window, "window"),
    u64Ptr(selection),
    BigInt(selection.length),
    u32Ptr(applied),
  ));
  return applied[0];
}

export function temporalControllerDispose(handle) {
  temporalStatus(xyTemporalControllerDispose(toU64(handle, "handle")));
}

export function temporalControllerDestroy(handle) {
  temporalStatus(xyTemporalControllerDestroy(toU64(handle, "handle")));
}

export function graphLayout(layout, nNodes, sources, targets, opts = {}) {
  const layoutId = graphLayoutId(layout);
  const nodeCount = toLength(nNodes, "nNodes");
  const sourceArray = asU64Array(sources, "sources");
  const targetArray = asU64Array(targets, "targets");
  requireEqualLength(sourceArray, targetArray, "sources", "targets");
  const outX = new Float64Array(nodeCount);
  const outY = new Float64Array(nodeCount);
  const inX = opts.x == null ? null : asF64Array(opts.x, "opts.x");
  const inY = opts.y == null ? null : asF64Array(opts.y, "opts.y");
  if ((inX == null) !== (inY == null)) {
    throw new TypeError("graphLayout requires both opts.x and opts.y or neither");
  }
  if (inX != null && (inX.length !== nodeCount || inY.length !== nodeCount)) {
    throw new RangeError("opts.x and opts.y must have length nNodes");
  }
  const roots = opts.roots == null ? new BigUint64Array(0) : asU64Array(opts.roots, "opts.roots");
  const code = xyGraphLayout(
    layoutId,
    toU64(nNodes, "nNodes"),
    toU64(sourceArray.length, "nEdges"),
    u64Ptr(sourceArray),
    u64Ptr(targetArray),
    f64Ptr(inX),
    f64Ptr(inY),
    u64Ptr(roots),
    toU64(roots.length, "nRoots"),
    toU64(opts.seed ?? 0, "opts.seed"),
    f64Ptr(outX),
    f64Ptr(outY),
  );
  if (code !== 0) {
    throw new Error(`xyg_graph_layout failed with code ${code}`);
  }
  return { x: outX, y: outY };
}

export function graphForceCreate(nNodes, sources, targets, opts = {}) {
  const nodeCount = toLength(nNodes, "nNodes");
  const sourceArray = asU64Array(sources, "sources");
  const targetArray = asU64Array(targets, "targets");
  requireEqualLength(sourceArray, targetArray, "sources", "targets");
  const inX = opts.x == null ? null : asF64Array(opts.x, "opts.x");
  const inY = opts.y == null ? null : asF64Array(opts.y, "opts.y");
  if ((inX == null) !== (inY == null)) {
    throw new TypeError("graphForceCreate requires both opts.x and opts.y or neither");
  }
  if (inX != null && (inX.length !== nodeCount || inY.length !== nodeCount)) {
    throw new RangeError("opts.x and opts.y must have length nNodes");
  }
  const algorithm = graphLayoutId(opts.algorithm ?? opts.layout ?? "force");
  const handle = new BigUint64Array(1);
  const configuredCose = opts.cose != null || opts.pinned != null || opts.parents != null;
  let code;
  if (configuredCose) {
    if (algorithm !== GRAPH_LAYOUT_COSE) {
      throw new TypeError("CoSE options, pins, and parents require algorithm='cose'");
    }
    const cose = opts.cose ?? {};
    const allowed = new Set([
      "idealEdgeLength", "repulsionStrength", "gravityStrength", "coolingFactor",
      "overlapPadding", "componentSpacing", "bounds",
    ]);
    const unknown = Object.keys(cose).filter((key) => !allowed.has(key));
    if (unknown.length > 0) {
      throw new TypeError(`unknown CoSE option(s): ${unknown.sort().join(", ")}`);
    }
    const pinned = opts.pinned == null ? null : asU8Array(opts.pinned, "opts.pinned");
    const parents = opts.parents == null ? null : asU64Array(opts.parents, "opts.parents");
    if (pinned != null && pinned.length !== nodeCount) {
      throw new RangeError("opts.pinned must have length nNodes");
    }
    if (pinned?.some((value) => value > 1)) {
      throw new RangeError("opts.pinned must contain only booleans or 0/1 integers");
    }
    if (parents != null && parents.length !== nodeCount) {
      throw new RangeError("opts.parents must have length nNodes");
    }
    if (pinned?.some((value) => value !== 0) && inX == null) {
      throw new TypeError("pinned nodes require explicit opts.x and opts.y initial positions");
    }
    const bounds = cose.bounds == null ? null : asF64Array(cose.bounds, "opts.cose.bounds");
    if (bounds != null && bounds.length !== 4) {
      throw new RangeError("opts.cose.bounds must be [x0, y0, x1, y1]");
    }
    const coseNumber = (value, fallback, name) => {
      const number = Number(value ?? fallback);
      if (!Number.isFinite(number)) {
        throw new TypeError(`opts.cose.${name} must be a finite number`);
      }
      return number;
    };
    const encoded = Buffer.alloc(koffi.sizeof(CoseDescriptor));
    koffi.encode(encoded, CoseDescriptor, {
      in_x: pointer(inX, "double *"),
      in_y: pointer(inY, "double *"),
      pinned: pointer(pinned, "uint8_t *"),
      parents: pointer(parents, "uint64_t *"),
      ideal_edge_length: coseNumber(cose.idealEdgeLength, 1.0, "idealEdgeLength"),
      repulsion_strength: coseNumber(cose.repulsionStrength, 1.25, "repulsionStrength"),
      gravity_strength: coseNumber(cose.gravityStrength, 0.08, "gravityStrength"),
      cooling_factor: coseNumber(cose.coolingFactor, 0.985, "coolingFactor"),
      overlap_padding: coseNumber(cose.overlapPadding, 0.35, "overlapPadding"),
      component_spacing: coseNumber(cose.componentSpacing, 2.5, "componentSpacing"),
      bounds: pointer(bounds, "double *"),
      has_bounds: bounds == null ? 0 : 1,
      reserved: 0,
    });
    code = xyGraphForceCreateCose(
      koffi.as(encoded, "const void *"),
      toU64(nodeCount, "nNodes"),
      toU64(sourceArray.length, "nEdges"),
      u64Ptr(sourceArray),
      u64Ptr(targetArray),
      toU64(opts.seed ?? 0, "opts.seed"),
      u64Ptr(handle),
    );
  } else {
    code = xyGraphForceCreate(
      toU64(nodeCount, "nNodes"),
      toU64(sourceArray.length, "nEdges"),
      u64Ptr(sourceArray),
      u64Ptr(targetArray),
      f64Ptr(inX),
      f64Ptr(inY),
      toU64(opts.seed ?? 0, "opts.seed"),
      toU32(algorithm, "algorithm"),
      u64Ptr(handle),
    );
  }
  if (code !== 0 || handle[0] === 0n) {
    const symbol = configuredCose ? "xyg_graph_force_create_cose" : "xyg_graph_force_create";
    throw new Error(`${symbol} failed with code ${code}`);
  }
  return handle[0];
}

export function graphIsProgressiveForce(layout) {
  return GRAPH_PROGRESSIVE_FORCE.has(graphLayoutId(layout));
}

export function graphForceTick(handle, nNodes, steps = 1) {
  const nodeCount = toLength(nNodes, "nNodes");
  const outX = new Float64Array(nodeCount);
  const outY = new Float64Array(nodeCount);
  const alpha = new Float64Array(1);
  const code = xyGraphForceTick(
    toU64(handle, "handle"),
    toU64(nodeCount, "nNodes"),
    toU32(steps, "steps"),
    f64Ptr(outX),
    f64Ptr(outY),
    f64Ptr(alpha),
  );
  if (code !== 0) {
    throw new Error(`xyg_graph_force_tick failed with code ${code}`);
  }
  return { x: outX, y: outY, alpha: alpha[0] };
}

export function graphForceDestroy(handle) {
  return xyGraphForceDestroy(toU64(handle, "handle")) === 1;
}

export function graphLodDecision(nNodes, nEdges, opts = {}) {
  const tier = new Uint32Array(1);
  const edgesKept = new BigUint64Array(1);
  const code = xyGraphLodDecision(
    toU64(nNodes, "nNodes"),
    toU64(nEdges, "nEdges"),
    toU64(opts.nodeBudget ?? 200_000, "opts.nodeBudget"),
    toU64(opts.edgeBudget ?? 500_000, "opts.edgeBudget"),
    u32Ptr(tier),
    u64Ptr(edgesKept),
  );
  if (code !== 0) {
    throw new Error(`xyg_graph_lod_decision failed with code ${code}`);
  }
  return { tier: tier[0], edgesKept: edgesKept[0] };
}

export function graphClusterAggregate(x, y, opts = {}) {
  const xArray = asF64Array(x, "x");
  const yArray = asF64Array(y, "y");
  requireEqualLength(xArray, yArray, "x", "y");
  const nNodes = xArray.length;
  const nodeBudget = toLength(opts.nodeBudget ?? nNodes, "opts.nodeBudget");
  const edgeBudget = toLength(opts.edgeBudget ?? 500_000, "opts.edgeBudget");
  const nEdges = toLength(opts.nEdges ?? 0, "opts.nEdges");
  if (nNodes > nodeBudget && nodeBudget === 0) {
    throw new Error("nodeBudget must be positive when clustering non-empty positions");
  }
  const outCap = nNodes <= nodeBudget ? nNodes : nodeBudget;
  const outX = new Float64Array(outCap);
  const outY = new Float64Array(outCap);
  const memberOf = new BigUint64Array(nNodes);
  const outCount = new BigUint64Array(1);
  const tier = new Uint32Array(1);
  const edgesKept = new BigUint64Array(1);
  const code = xyGraphClusterAggregate(
    toU64(nNodes, "nNodes"),
    toU64(nEdges, "nEdges"),
    f64Ptr(xArray),
    f64Ptr(yArray),
    toU64(nodeBudget, "opts.nodeBudget"),
    toU64(edgeBudget, "opts.edgeBudget"),
    f64Ptr(outX),
    f64Ptr(outY),
    u64Ptr(outCount),
    u64Ptr(memberOf),
    u32Ptr(tier),
    u64Ptr(edgesKept),
  );
  if (code !== 0) {
    throw new Error(`xyg_graph_cluster_aggregate failed with code ${code}`);
  }
  const count = Number(outCount[0]);
  return {
    x: outX.subarray(0, count),
    y: outY.subarray(0, count),
    memberOf,
    tier: tier[0],
    edgesKept: edgesKept[0],
  };
}

export function graphBuildRender(x, y, sources, targets, opts = {}) {
  const xArray = asF64Array(x, "x");
  const yArray = asF64Array(y, "y");
  requireEqualLength(xArray, yArray, "x", "y");
  const sourceArray = asU64Array(sources, "sources");
  const targetArray = asU64Array(targets, "targets");
  requireEqualLength(sourceArray, targetArray, "sources", "targets");
  const nNodes = xArray.length;
  const nodeBudget = toLength(opts.nodeBudget ?? 200_000, "opts.nodeBudget");
  const edgeBudget = toLength(opts.edgeBudget ?? 500_000, "opts.edgeBudget");
  const outNodeCap = nNodes === 0 ? 0 : Math.min(nNodes, Math.max(nodeBudget, 1));
  const outX = new Float64Array(outNodeCap);
  const outY = new Float64Array(outNodeCap);
  const memberOf = new BigUint64Array(nNodes);
  const edgeS = new BigUint64Array(Math.max(edgeBudget, 1));
  const edgeT = new BigUint64Array(Math.max(edgeBudget, 1));
  const outNNodes = new BigUint64Array(1);
  const outNEdges = new BigUint64Array(1);
  const tier = new Uint32Array(1);
  const edgesKept = new BigUint64Array(1);
  const vp = opts.viewport;
  const vpEnabled = vp == null ? 0 : 1;
  const x0 = vp == null ? 0 : Number(vp.x0 ?? vp[0]);
  const y0 = vp == null ? 0 : Number(vp.y0 ?? vp[1]);
  const x1 = vp == null ? 0 : Number(vp.x1 ?? vp[2]);
  const y1 = vp == null ? 0 : Number(vp.y1 ?? vp[3]);
  const code = xyGraphBuildRender(
    toU64(nNodes, "nNodes"),
    toU64(sourceArray.length, "nEdges"),
    f64Ptr(xArray),
    f64Ptr(yArray),
    u64Ptr(sourceArray),
    u64Ptr(targetArray),
    toU64(Math.max(nodeBudget, 1), "opts.nodeBudget"),
    toU64(Math.max(edgeBudget, 1), "opts.edgeBudget"),
    vpEnabled,
    x0,
    y0,
    x1,
    y1,
    f64Ptr(outX),
    f64Ptr(outY),
    u64Ptr(memberOf),
    u64Ptr(edgeS),
    u64Ptr(edgeT),
    u64Ptr(outNNodes),
    u64Ptr(outNEdges),
    u32Ptr(tier),
    u64Ptr(edgesKept),
  );
  if (code !== 0) {
    throw new Error(`xyg_graph_build_render failed with code ${code}`);
  }
  const nOut = Number(outNNodes[0]);
  const eOut = Number(outNEdges[0]);
  return {
    x: outX.subarray(0, nOut),
    y: outY.subarray(0, nOut),
    memberOf,
    edgeSources: edgeS.subarray(0, eOut),
    edgeTargets: edgeT.subarray(0, eOut),
    tier: tier[0],
    edgesKept: edgesKept[0],
  };
}


export function graphEdgeRouteSegments(x, y, sources, targets, opts = {}) {
  const xArray = asF64Array(x, "x");
  const yArray = asF64Array(y, "y");
  requireEqualLength(xArray, yArray, "x", "y");
  const sourceArray = asU64Array(sources, "sources");
  const targetArray = asU64Array(targets, "targets");
  requireEqualLength(sourceArray, targetArray, "sources", "targets");
  const nNodes = xArray.length;
  const nEdges = sourceArray.length;
  const cap = nEdges * 5;
  const outX0 = new Float64Array(cap);
  const outY0 = new Float64Array(cap);
  const outX1 = new Float64Array(cap);
  const outY1 = new Float64Array(cap);
  const outEdgeIndex = new BigUint64Array(cap);
  const outN = new BigUint64Array(1);
  const directed = opts.directed === false ? 0 : 1;
  const separation = Number(opts.separation ?? 0.08);
  const loopRadius = Number(opts.loopRadius ?? 0.35);
  const arrowSize = Number(opts.arrowSize ?? 0.12);
  const code = xyGraphEdgeRouteSegments(
    toU64(nNodes, "nNodes"),
    toU64(nEdges, "nEdges"),
    f64Ptr(xArray),
    f64Ptr(yArray),
    u64Ptr(sourceArray),
    u64Ptr(targetArray),
    directed,
    separation,
    loopRadius,
    arrowSize,
    f64Ptr(outX0),
    f64Ptr(outY0),
    f64Ptr(outX1),
    f64Ptr(outY1),
    u64Ptr(outEdgeIndex),
    u64Ptr(outN),
  );
  if (code !== 0) {
    throw new Error(`xyg_graph_edge_route_segments failed with code ${code}`);
  }
  const nSeg = Number(outN[0]);
  return {
    x0: outX0.subarray(0, nSeg),
    y0: outY0.subarray(0, nSeg),
    x1: outX1.subarray(0, nSeg),
    y1: outY1.subarray(0, nSeg),
    edgeIndex: outEdgeIndex.subarray(0, nSeg),
  };
}

export function graphSampleEdges(nEdges, budget) {
  const requested = toLength(budget, "budget");
  const out = new BigUint64Array(requested);
  if (requested === 0) {
    return out;
  }
  const kept = xyGraphSampleEdges(toU64(nEdges, "nEdges"), toU64(requested, "budget"), u64Ptr(out));
  return out.subarray(0, Number(kept));
}

export function graphBuildCsr(nNodes, sources, targets, opts = {}) {
  const nodeCount = toLength(nNodes, "nNodes");
  const sourceArray = asU64Array(sources, "sources");
  const targetArray = asU64Array(targets, "targets");
  requireEqualLength(sourceArray, targetArray, "sources", "targets");
  const directed = opts.directed ?? true;
  const cap = Math.max(sourceArray.length * (directed ? 1 : 2), 1);
  const offsets = new BigUint64Array(nodeCount + 1);
  const neighbors = new BigUint64Array(cap);
  const neighborLen = new BigUint64Array(1);
  const code = xyGraphBuildCsr(
    toU64(nodeCount, "nNodes"),
    toU64(sourceArray.length, "nEdges"),
    u64Ptr(sourceArray),
    u64Ptr(targetArray),
    directed ? 1 : 0,
    u64Ptr(offsets),
    u64Ptr(neighbors),
    toU64(cap, "neighborsCap"),
    u64Ptr(neighborLen),
  );
  if (code !== 0) {
    throw new Error(`xyg_graph_build_csr failed with code ${code}`);
  }
  return { offsets, neighbors: neighbors.subarray(0, Number(neighborLen[0])) };
}

export function sankeyLayout(nNodes, sources, targets, values, opts = {}) {
  const nodeCount = toLength(nNodes, "nNodes");
  const sourceArray = asU64Array(sources, "sources");
  const targetArray = asU64Array(targets, "targets");
  const valueArray = asF64Array(values, "values");
  requireEqualLength(sourceArray, targetArray, "sources", "targets");
  requireEqualLength(sourceArray, valueArray, "sources", "values");
  const linkCount = sourceArray.length;
  const x0 = new Float64Array(nodeCount);
  const y0 = new Float64Array(nodeCount);
  const x1 = new Float64Array(nodeCount);
  const y1 = new Float64Array(nodeCount);
  const layer = new Uint32Array(nodeCount);
  const nodeValue = new Float64Array(nodeCount);
  const sourceY0 = new Float64Array(linkCount);
  const sourceY1 = new Float64Array(linkCount);
  const targetY0 = new Float64Array(linkCount);
  const targetY1 = new Float64Array(linkCount);
  const layers = new Uint32Array(1);
  const errNodes = new BigUint64Array(Math.max(nodeCount, 1));
  const errN = new BigUint64Array(1);
  const code = xySankeyLayout(
    toU64(nodeCount, "nNodes"),
    toU64(linkCount, "nLinks"),
    u64Ptr(sourceArray),
    u64Ptr(targetArray),
    f64Ptr(valueArray),
    Number(opts.nodeWidth ?? 0.02),
    Number(opts.nodePadding ?? 0.02),
    sankeyAlignId(opts.align ?? "justify"),
    toU32(opts.iterations ?? 6, "opts.iterations"),
    f64Ptr(x0),
    f64Ptr(y0),
    f64Ptr(x1),
    f64Ptr(y1),
    u32Ptr(layer),
    f64Ptr(nodeValue),
    f64Ptr(sourceY0),
    f64Ptr(sourceY1),
    f64Ptr(targetY0),
    f64Ptr(targetY1),
    u32Ptr(layers),
    u64Ptr(errNodes),
    u64Ptr(errN),
  );
  const detail = errNodes.slice(0, Number(errN[0]));
  if (code === -2) {
    throw new SankeyLayoutError(code, detail, "sankey links form a cycle");
  }
  if (code === -3) {
    throw new SankeyLayoutError(code, detail, "sankey nodePadding leaves no room");
  }
  if (code !== 0) {
    throw new Error(`xyg_sankey_layout failed with code ${code}`);
  }
  return {
    x0,
    y0,
    x1,
    y1,
    layer,
    value: nodeValue,
    sourceY0,
    sourceY1,
    targetY0,
    targetY1,
    layers: layers[0],
  };
}

export function graphLayoutId(layout) {
  if (typeof layout === "number") {
    return toU32(layout, "layout");
  }
  const key = String(layout).trim().toLowerCase();
  const id = GRAPH_LAYOUT_IDS[key];
  if (id == null) {
    throw new Error(`unknown graph layout ${JSON.stringify(layout)}; expected one of ${Object.keys(GRAPH_LAYOUT_IDS).join(", ")}`);
  }
  return id;
}

export function sankeyAlignId(align) {
  if (typeof align === "number") {
    return toU32(align, "align");
  }
  const key = String(align).trim().toLowerCase();
  const id = SANKEY_ALIGN_IDS[key];
  if (id == null) {
    throw new Error(`unknown sankey align ${JSON.stringify(align)}; expected one of ${Object.keys(SANKEY_ALIGN_IDS).join(", ")}`);
  }
  return id;
}

function requireEqualLength(a, b, aName, bName) {
  if (a.length !== b.length) {
    throw new RangeError(`${aName} and ${bName} must have equal length`);
  }
}

function asU64Array(value, name) {
  if (value instanceof BigUint64Array) {
    return value;
  }
  if (value == null) {
    return new BigUint64Array(0);
  }
  return BigUint64Array.from(value, (item) => toU64(item, name));
}

function asI64Array(value, name) {
  if (value instanceof BigInt64Array) {
    return value;
  }
  if (value == null) {
    return new BigInt64Array(0);
  }
  return BigInt64Array.from(value, (item) => {
    if (typeof item === "bigint") {
      return item;
    }
    if (!Number.isInteger(item) || !Number.isSafeInteger(item)) {
      throw new RangeError(`${name} must contain safe integers or bigints`);
    }
    return BigInt(item);
  });
}

function asI32Array(value, name) {
  if (value instanceof Int32Array) {
    return value;
  }
  if (value == null) {
    return new Int32Array(0);
  }
  return Int32Array.from(value, (item) => {
    const number = Number(item);
    if (!Number.isInteger(number) || number < -2147483648 || number > 2147483647) {
      throw new RangeError(`${name} must contain int32 values`);
    }
    return number;
  });
}

function asU8Array(value, name) {
  if (value instanceof Uint8Array) {
    return value;
  }
  if (value == null) {
    return new Uint8Array(0);
  }
  return Uint8Array.from(value, (item) => {
    const number = Number(item);
    if (!Number.isInteger(number) || number < 0 || number > 255) {
      throw new RangeError(`${name} must contain uint8 values`);
    }
    return number;
  });
}

function asU32Array(value, name) {
  if (value instanceof Uint32Array) {
    return value;
  }
  if (value == null) {
    return new Uint32Array(0);
  }
  return Uint32Array.from(value, (item) => {
    const number = Number(item);
    if (!Number.isInteger(number) || number < 0 || number > 0xffffffff) {
      throw new RangeError(`${name} must contain uint32 values`);
    }
    return number;
  });
}

function asF64Array(value, name) {
  if (value instanceof Float64Array) {
    return value;
  }
  if (value == null) {
    return new Float64Array(0);
  }
  return Float64Array.from(value, (item) => {
    const number = Number(item);
    if (!Number.isFinite(number)) {
      throw new TypeError(`${name} must contain only finite numbers`);
    }
    return number;
  });
}

function toU64(value, name) {
  if (typeof value === "bigint") {
    if (value < 0n || value > U64_MAX) {
      throw new RangeError(`${name} must fit in uint64`);
    }
    return value;
  }
  if (!Number.isInteger(value) || value < 0 || !Number.isSafeInteger(value)) {
    throw new RangeError(`${name} must be a non-negative safe integer or bigint`);
  }
  return BigInt(value);
}

function toI64(value, name) {
  let converted;
  if (typeof value === "bigint") {
    converted = value;
  } else {
    if (typeof value !== "number" || !Number.isSafeInteger(value)) {
      throw new RangeError(`${name} must be a safe integer or bigint fitting in int64`);
    }
    converted = BigInt(value);
  }
  if (converted < I64_MIN || converted > I64_MAX) {
    throw new RangeError(`${name} must fit in int64`);
  }
  return converted;
}

function toStrictU32(value, name) {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0 || value > 0xffff_ffff) {
    throw new RangeError(`${name} must be a uint32 number`);
  }
  return value;
}

function toI32(value, name) {
  if (
    typeof value !== "number"
    || !Number.isInteger(value)
    || value < -0x8000_0000
    || value > 0x7fff_ffff
  ) {
    throw new RangeError(`${name} must be an int32 number`);
  }
  return value;
}

function toStrictBool(value, name) {
  if (typeof value !== "boolean") {
    throw new TypeError(`${name} must be a boolean`);
  }
  return value;
}

function toLength(value, name) {
  const asBigInt = toU64(value, name);
  if (asBigInt > BigInt(Number.MAX_SAFE_INTEGER)) {
    throw new RangeError(`${name} is too large for a JavaScript TypedArray length`);
  }
  return Number(asBigInt);
}

function toU32(value, name) {
  if (!Number.isInteger(Number(value)) || Number(value) < 0 || Number(value) > 0xffff_ffff) {
    throw new RangeError(`${name} must fit in uint32`);
  }
  return Number(value);
}

function u64Ptr(view) {
  return pointer(view, "uint64_t *");
}

function u32Ptr(view) {
  return pointer(view, "uint32_t *");
}

function i32Ptr(view) {
  return pointer(view, "int32_t *");
}

function f64Ptr(view) {
  return pointer(view, "double *");
}
