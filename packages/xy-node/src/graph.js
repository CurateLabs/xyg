/**
 * Graph host composition — normalize ids → dense u64, layout + render-graph
 * via the shared ABI, emit node positions / edge segment endpoints / meta.
 *
 * Mirrors python/xy/_graph.py + the segments/scatter emit in marks.graph().
 * Layout, LOD, and encode decisions stay in Rust (host-parity.md).
 */

import {
  graphBuildCsr,
  graphBuildRender,
  graphForceCreate,
  graphForceDestroy,
  graphForceTick,
  graphLayout,
} from "./abi.js";

/** Default layout name — matches Python `_graph.DEFAULT_LAYOUT`. */
export const DEFAULT_LAYOUT = "force";

/**
 * @typedef {object} GraphData
 * @property {Array<string|number>} ids
 * @property {BigUint64Array} sources
 * @property {BigUint64Array} targets
 * @property {Float64Array|null} x
 * @property {Float64Array|null} y
 * @property {Record<string, unknown>} nodeAttrs
 * @property {boolean} directed
 * @property {number} nNodes
 * @property {number} nEdges
 */

/**
 * Accept ids + edge pairs/columns (xy-native formats) → dense u64 GraphData.
 *
 * @param {Iterable|object} nodes — id list, or `{id: [...], ...attrs}`
 * @param {Iterable|object} edges — `(source,target)` pairs or `{source,target}`
 * @param {{x?: Iterable, y?: Iterable, directed?: boolean}} [opts]
 * @returns {GraphData}
 */
export function normalizeGraphInputs(nodes, edges, opts = {}) {
  const directed = opts.directed ?? true;
  let ids;
  const nodeAttrs = {};

  if (nodes != null && typeof nodes === "object" && !Array.isArray(nodes) && "id" in nodes) {
    ids = [...nodes.id];
    for (const [key, val] of Object.entries(nodes)) {
      if (key === "id" || typeof val === "function") continue;
      nodeAttrs[key] = val;
    }
  } else {
    ids = [...(nodes ?? [])];
  }

  const idToIndex = new Map();
  for (let i = 0; i < ids.length; i += 1) {
    if (idToIndex.has(ids[i])) {
      throw new Error("graph node ids must be unique");
    }
    idToIndex.set(ids[i], i);
  }

  let srcIds;
  let tgtIds;
  if (edges != null && typeof edges === "object" && !Array.isArray(edges) && "source" in edges && "target" in edges) {
    srcIds = [...edges.source];
    tgtIds = [...edges.target];
  } else {
    const pairs = [...(edges ?? [])];
    srcIds = [];
    tgtIds = [];
    for (const pair of pairs) {
      if (pair == null || (typeof pair !== "object" && typeof pair !== "string")) {
        throw new Error(
          "edges must be (source, target) pairs, or a mapping/table with source and target columns",
        );
      }
      if (Array.isArray(pair) && pair.length >= 2) {
        srcIds.push(pair[0]);
        tgtIds.push(pair[1]);
      } else if (typeof pair === "object" && "0" in pair && "1" in pair) {
        srcIds.push(pair[0]);
        tgtIds.push(pair[1]);
      } else {
        throw new Error(
          "edges must be (source, target) pairs, or a mapping/table with source and target columns",
        );
      }
    }
  }

  if (srcIds.length !== tgtIds.length) {
    throw new Error("edge source/target lengths differ");
  }

  const sources = new BigUint64Array(srcIds.length);
  const targets = new BigUint64Array(tgtIds.length);
  for (let i = 0; i < srcIds.length; i += 1) {
    const s = srcIds[i];
    const t = tgtIds[i];
    if (!idToIndex.has(s) || !idToIndex.has(t)) {
      throw new Error(`edge endpoints (${String(s)}, ${String(t)}) are not in nodes`);
    }
    sources[i] = BigInt(idToIndex.get(s));
    targets[i] = BigInt(idToIndex.get(t));
  }

  const hasX = opts.x != null;
  const hasY = opts.y != null;
  if (hasX !== hasY) {
    throw new Error("x and y must both be provided or both omitted");
  }
  let x = null;
  let y = null;
  if (hasX) {
    x = Float64Array.from(opts.x, Number);
    y = Float64Array.from(opts.y, Number);
    if (x.length !== ids.length || y.length !== ids.length) {
      throw new Error("x/y must match node count");
    }
  }

  return {
    ids,
    sources,
    targets,
    x,
    y,
    nodeAttrs,
    directed: Boolean(directed),
    get nNodes() {
      return this.ids.length;
    },
    get nEdges() {
      return this.sources.length;
    },
  };
}

/**
 * Layout via Rust ABI, then emit a perceptually bounded render graph.
 *
 * @param {GraphData} data
 * @param {object} [opts]
 * @returns {{
 *   nodePositions: {x: Float64Array, y: Float64Array},
 *   edgeSegments: {x0: Float64Array, y0: Float64Array, x1: Float64Array, y1: Float64Array},
 *   meta: object,
 * }}
 */
export function runLayout(data, opts = {}) {
  const layoutName = String(opts.layout ?? DEFAULT_LAYOUT)
    .trim()
    .toLowerCase();
  const seed = opts.seed ?? 0;
  const iterations = opts.iterations ?? 300;
  const nodeBudget = opts.nodeBudget ?? 200_000;
  const edgeBudget = opts.edgeBudget ?? 500_000;
  const viewport = opts.viewport ?? null;
  const includeCsr = opts.includeCsr ?? true;

  const n = data.nNodes;
  const e = data.nEdges;
  const { sources, targets } = data;

  let x;
  let y;
  let alpha = null;

  if (layoutName === "force" && iterations > 0) {
    const handle = graphForceCreate(n, sources, targets, {
      x: data.x,
      y: data.y,
      seed,
    });
    try {
      const tick = graphForceTick(handle, n, Math.max(1, iterations));
      x = tick.x;
      y = tick.y;
      alpha = tick.alpha;
    } finally {
      graphForceDestroy(handle);
    }
  } else {
    if (layoutName === "preset" && (data.x == null || data.y == null)) {
      throw new Error("layout='preset' requires x and y");
    }
    const laid = graphLayout(layoutName, n, sources, targets, {
      x: data.x,
      y: data.y,
      seed,
      roots: opts.roots,
    });
    x = laid.x;
    y = laid.y;
  }

  const render = graphBuildRender(x, y, sources, targets, {
    nodeBudget,
    edgeBudget,
    viewport,
  });

  const rx = render.x;
  const ry = render.y;
  const edgeS = render.edgeSources;
  const edgeT = render.edgeTargets;
  const edgeSegments = edgeSegmentsFromPositions(rx, ry, edgeS, edgeT);

  /** @type {Record<string, unknown>} */
  const meta = {
    layout: layoutName === "force" && iterations > 0 ? "force" : layoutName,
    seed: Number(seed),
    lod_tier: render.tier,
    edges_kept: Number(render.edgesKept),
    nodes_kept: rx.length,
    n_nodes: rx.length,
    n_edges: edgeS.length,
    source_n_nodes: n,
    source_n_edges: e,
    member_of: render.memberOf,
    render_sources: edgeS,
    render_targets: edgeT,
    node_budget: nodeBudget,
    edge_budget: edgeBudget,
    directed: Boolean(data.directed),
    ids: data.ids.map(String),
  };

  if (layoutName === "force" && iterations > 0) {
    meta.iterations = Number(iterations);
    meta.alpha = alpha == null ? null : Number(alpha);
  }

  if (includeCsr) {
    const csr = graphBuildCsr(rx.length, edgeS, edgeT, { directed: data.directed });
    meta.csr_offsets = csr.offsets;
    meta.csr_neighbors = csr.neighbors;
  }

  return {
    nodePositions: { x: rx, y: ry },
    edgeSegments,
    meta,
  };
}

/**
 * Build segment endpoint columns from node positions + edge index pairs.
 *
 * @param {Float64Array} x
 * @param {Float64Array} y
 * @param {BigUint64Array|ArrayLike<bigint|number>} sources
 * @param {BigUint64Array|ArrayLike<bigint|number>} targets
 */
export function edgeSegmentsFromPositions(x, y, sources, targets) {
  const n = sources.length;
  const x0 = new Float64Array(n);
  const y0 = new Float64Array(n);
  const x1 = new Float64Array(n);
  const y1 = new Float64Array(n);
  for (let i = 0; i < n; i += 1) {
    const s = Number(sources[i]);
    const t = Number(targets[i]);
    x0[i] = x[s];
    y0[i] = y[s];
    x1[i] = x[t];
    y1[i] = y[t];
  }
  return { x0, y0, x1, y1 };
}

/**
 * Compose a graph into figure traces + graph meta (conceptual parity with
 * Python `Figure.graph` / `marks.graph`).
 *
 * @param {Iterable|object} nodes
 * @param {Iterable|object} edges
 * @param {object} [opts]
 */
export function composeGraph(nodes, edges, opts = {}) {
  const data = normalizeGraphInputs(nodes, edges, {
    x: opts.x,
    y: opts.y,
    directed: opts.directed,
  });
  const { nodePositions, edgeSegments, meta } = runLayout(data, opts);
  const name = opts.name ?? null;
  const traces = [
    {
      kind: "segments",
      name: name == null ? null : `${name}:edges`,
      x0: edgeSegments.x0,
      y0: edgeSegments.y0,
      x1: edgeSegments.x1,
      y1: edgeSegments.y1,
      style: {
        color: opts.edgeColor ?? "#888888",
        width: opts.edgeWidth ?? 1.2,
        ...(opts.style ?? {}),
      },
    },
    {
      kind: "scatter",
      name: name == null ? null : `${name}:nodes`,
      x: nodePositions.x,
      y: nodePositions.y,
      style: {
        color: opts.color ?? "#3987e5",
        size: opts.size ?? 8.0,
        symbol: opts.symbol ?? "circle",
        ...(opts.style ?? {}),
      },
    },
  ];

  const graphMeta = {
    ...Object.fromEntries(
      Object.entries(meta).filter(
        ([k]) => !["member_of", "render_sources", "render_targets", "csr_offsets", "csr_neighbors"].includes(k),
      ),
    ),
    directed: Boolean(data.directed),
    ids: meta.ids,
    sources: [...meta.render_sources].map(Number),
    targets: [...meta.render_targets].map(Number),
    member_of: [...meta.member_of].map(Number),
    source_n_nodes: meta.source_n_nodes,
    source_n_edges: meta.source_n_edges,
    csr_offsets: meta.csr_offsets ? [...meta.csr_offsets].map(Number) : undefined,
    csr_neighbors: meta.csr_neighbors ? [...meta.csr_neighbors].map(Number) : undefined,
    node_symbol: typeof opts.symbol === "string" ? opts.symbol : "circle",
    edge_curve: String(opts.edgeCurve ?? "straight").trim().toLowerCase(),
    tier_name: ["direct", "edge_sample", "aggregate"][Math.min(Number(meta.lod_tier), 2)],
    node_trace: 1,
    edge_trace: 0,
  };

  return {
    traces,
    graphMeta,
    nodePositions,
    edgeSegments,
    meta,
  };
}
