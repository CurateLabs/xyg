import {
  nativeLibraryPath,
  pointer,
  xyAbiVersion,
  xyGraphBuildCsr,
  xyGraphClusterAggregate,
  xyGraphForceCreate,
  xyGraphForceDestroy,
  xyGraphForceTick,
  xyGraphLayout,
  xyGraphLodDecision,
  xyGraphSampleEdges,
  xySankeyLayout,
} from "./native.js";

export { nativeLibraryPath };

const U64_MAX = (1n << 64n) - 1n;

export const GRAPH_LAYOUT_PRESET = 0;
export const GRAPH_LAYOUT_GRID = 1;
export const GRAPH_LAYOUT_CIRCLE = 2;
export const GRAPH_LAYOUT_FORCE = 3;
export const GRAPH_LAYOUT_BREADTHFIRST = 4;
export const GRAPH_LAYOUT_AUTO = 5;
export const GRAPH_LAYOUT_RADIAL = 6;
export const GRAPH_LAYOUT_CONCENTRIC = 7;

export const GRAPH_LAYOUT_IDS = Object.freeze({
  preset: GRAPH_LAYOUT_PRESET,
  grid: GRAPH_LAYOUT_GRID,
  circle: GRAPH_LAYOUT_CIRCLE,
  force: GRAPH_LAYOUT_FORCE,
  breadthfirst: GRAPH_LAYOUT_BREADTHFIRST,
  dagre: GRAPH_LAYOUT_BREADTHFIRST,
  hierarchical: GRAPH_LAYOUT_BREADTHFIRST,
  auto: GRAPH_LAYOUT_AUTO,
  radial: GRAPH_LAYOUT_RADIAL,
  concentric: GRAPH_LAYOUT_CONCENTRIC,
});

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

export function abiVersion() {
  return xyAbiVersion();
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
    throw new Error(`xy_graph_layout failed with code ${code}`);
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
  const handle = new BigUint64Array(1);
  const code = xyGraphForceCreate(
    toU64(nodeCount, "nNodes"),
    toU64(sourceArray.length, "nEdges"),
    u64Ptr(sourceArray),
    u64Ptr(targetArray),
    f64Ptr(inX),
    f64Ptr(inY),
    toU64(opts.seed ?? 0, "opts.seed"),
    u64Ptr(handle),
  );
  if (code !== 0 || handle[0] === 0n) {
    throw new Error(`xy_graph_force_create failed with code ${code}`);
  }
  return handle[0];
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
    throw new Error(`xy_graph_force_tick failed with code ${code}`);
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
    throw new Error(`xy_graph_lod_decision failed with code ${code}`);
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
    throw new Error(`xy_graph_cluster_aggregate failed with code ${code}`);
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
    throw new Error(`xy_graph_build_csr failed with code ${code}`);
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
    throw new Error(`xy_sankey_layout failed with code ${code}`);
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

function f64Ptr(view) {
  return pointer(view, "double *");
}
