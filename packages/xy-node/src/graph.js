/**
 * Graph host composition — normalize ids → dense u64, layout + render-graph
 * via the shared ABI, emit node positions / edge segment endpoints / meta.
 *
 * Mirrors python/xyg/_graph.py + the segments/scatter emit in marks.graph().
 * Layout, LOD, and encode decisions stay in Rust (host-parity.md).
 */

import {
  graphBuildCsr,
  graphBuildRender,
  graphEdgeRouteEnds,
  graphForceCreate,
  graphForceDestroy,
  graphForceTick,
  graphIsProgressiveForce,
  graphLayout,
  graphProjectionCreate,
  graphProjectionDestroy,
  graphProjectionRead,
  graphCompoundBounds,
  graphLabelPlan,
  graphCompoundCollapse,
  graphCompoundFrames,
  graphSemanticPaintLayers,
  graphSemanticLegend,
  graphSemanticLegendText,
  graphOrdinalColors,
  graphDivergingDomain,
  graphSemanticStyles,
  graphVisualStates,
} from "./abi.js";
import { resolveColorChannel } from "./color.js";
import { DEFAULT_MARK_COLOR, minMax } from "./encode.js";
import { resolveSizeChannel } from "./marks/scatter.js";

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
 * @property {Array<string>} edgeIds
 * @property {Record<string, unknown>} edgeAttrs
 * @property {Uint8Array|null} nodeUuidBytes
 * @property {Uint8Array|null} edgeUuidBytes
 * @property {BigUint64Array|null} nodeProvenanceRows
 * @property {BigUint64Array|null} edgeProvenanceRows
 * @property {boolean} directed
 * @property {number} nNodes
 * @property {number} nEdges
 */

/**
 * Accept ids + edge pairs/columns (xyg-native formats) → dense u64 GraphData.
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
    edgeIds: [],
    sources,
    targets,
    x,
    y,
    nodeAttrs,
    edgeAttrs: {},
    nodeUuidBytes: null,
    edgeUuidBytes: null,
    nodeProvenanceRows: null,
    edgeProvenanceRows: null,
    directed: Boolean(directed),
    get nNodes() {
      return this.ids.length;
    },
    get nEdges() {
      return this.sources.length;
    },
  };
}

function tableColumnNames(table) {
  if (table == null || typeof table !== "object") {
    throw graphProjectionError("GF_GRAPH_TABLE", "expected an Arrow/table-like object");
  }
  if (table.schema?.fields) return table.schema.fields.map((field) => String(field.name));
  if (Array.isArray(table.columnNames)) return table.columnNames.map(String);
  return Object.keys(table).filter((key) => typeof table[key] !== "function");
}

function tableColumn(table, name) {
  let column;
  if (typeof table.getChild === "function") column = table.getChild(name);
  if (column == null && name in table) column = table[name];
  if (column == null) {
    throw graphProjectionError(
      "GF_GRAPH_FIELD_MISSING",
      `required column ${JSON.stringify(name)} is absent`,
      { field: name },
    );
  }
  if (typeof column.toArray === "function") return column.toArray();
  if (typeof column.toJSON === "function") return column.toJSON();
  if (typeof column[Symbol.iterator] === "function") return [...column];
  if (Number.isInteger(column.length)) return Array.from(column);
  throw graphProjectionError(
    "GF_GRAPH_COLUMN_SHAPE",
    `column ${JSON.stringify(name)} is not one-dimensional`,
    { field: name },
  );
}

function graphProjectionError(code, message, context = {}) {
  const error = new Error(`${code}: ${message}`);
  error.code = code;
  if (context.field != null) error.field = context.field;
  if (context.row != null) error.row = context.row;
  return error;
}

function parseUuid(value, field, row) {
  if (value == null) {
    throw graphProjectionError("GF_GRAPH_UUID_NULL", "UUID values cannot be null", { field, row });
  }
  if (ArrayBuffer.isView(value) || value instanceof ArrayBuffer) {
    const bytes = value instanceof ArrayBuffer
      ? new Uint8Array(value)
      : new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
    if (bytes.byteLength !== 16) {
      throw graphProjectionError("GF_GRAPH_UUID_INVALID", "binary UUID must contain 16 bytes", { field, row });
    }
    const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
    return {
      text: `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`,
      bytes: Uint8Array.from(bytes),
    };
  }
  const text = String(value).toLowerCase();
  const match = /^([0-9a-f]{8})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{12})$/.exec(text);
  if (!match) {
    throw graphProjectionError("GF_GRAPH_UUID_INVALID", `invalid UUID ${JSON.stringify(text)}`, { field, row });
  }
  const hex = match.slice(1).join("");
  const bytes = new Uint8Array(16);
  for (let i = 0; i < 16; i += 1) bytes[i] = Number.parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  if (bytes.every((byte) => byte === 0)) {
    throw graphProjectionError("GF_GRAPH_UUID_INVALID", "nil UUID is not a graph identity", { field, row });
  }
  return { text, bytes };
}

function uuidColumn(values, field) {
  const rows = [...values];
  const ids = new Array(rows.length);
  const bytes = new Uint8Array(rows.length * 16);
  for (let row = 0; row < rows.length; row += 1) {
    const parsed = parseUuid(rows[row], field, row);
    ids[row] = parsed.text;
    bytes.set(parsed.bytes, row * 16);
  }
  return { ids, bytes };
}

function resolveColumn(names, explicit, candidates, semantic) {
  if (explicit != null) {
    if (!names.includes(explicit)) {
      throw graphProjectionError(
        "GF_GRAPH_FIELD_MISSING",
        `configured ${semantic} column ${JSON.stringify(explicit)} is absent`,
        { field: explicit },
      );
    }
    return explicit;
  }
  const matches = candidates.filter((candidate) => names.includes(candidate));
  if (matches.length === 1) return matches[0];
  if (matches.length === 0) {
    throw graphProjectionError(
      "GF_GRAPH_FIELD_MISSING",
      `no ${semantic} column found; expected one of ${candidates.join(", ")}`,
    );
  }
  throw graphProjectionError(
    "GF_GRAPH_FIELD_AMBIGUOUS",
    `multiple ${semantic} columns are present: ${matches.join(", ")}; provide mapping`,
  );
}

function attributeColumns(table, names, excluded, expected) {
  const attrs = {};
  for (const name of names) {
    if (excluded.has(name)) continue;
    const column = tableColumn(table, name);
    if (column.length !== expected) {
      throw graphProjectionError(
        "GF_GRAPH_COLUMN_SHAPE",
        `attribute columns must contain ${expected} rows`,
        { field: name },
      );
    }
    attrs[name] = column;
  }
  return attrs;
}

/**
 * Build identity-preserving graph data from canonical GraphForge Arrow tables.
 * Arrow is a Node-host concern; the browser paint client never imports it.
 */
export function fromGraphForgeTables(nodes, edges, opts = {}) {
  const mapping = opts.mapping ?? {};
  const nodeNames = tableColumnNames(nodes);
  const edgeNames = tableColumnNames(edges);
  const nodeIdField = resolveColumn(nodeNames, mapping.node_uuid, ["node_uuid"], "node UUID");
  const edgeIdField = resolveColumn(edgeNames, mapping.edge_uuid, ["edge_uuid"], "edge UUID");
  const sourceField = resolveColumn(
    edgeNames,
    mapping.source_uuid,
    ["src_uuid", "source_uuid"],
    "edge source UUID",
  );
  const targetField = resolveColumn(
    edgeNames,
    mapping.target_uuid,
    ["dst_uuid", "target_uuid"],
    "edge target UUID",
  );
  const nodeUuid = uuidColumn(tableColumn(nodes, nodeIdField), nodeIdField);
  const edgeUuid = uuidColumn(tableColumn(edges, edgeIdField), edgeIdField);
  const sourceUuid = uuidColumn(tableColumn(edges, sourceField), sourceField);
  const targetUuid = uuidColumn(tableColumn(edges, targetField), targetField);
  if (sourceUuid.ids.length !== targetUuid.ids.length || sourceUuid.ids.length !== edgeUuid.ids.length) {
    throw graphProjectionError("GF_GRAPH_EDGE_LENGTH", "edge UUID/source/target column lengths differ");
  }
  const parentField = mapping.parent_uuid ?? "parent_uuid";
  let parentIds = null;
  let parentValidity = null;
  if (nodeNames.includes(parentField)) {
    const rawParents = [...tableColumn(nodes, parentField)];
    if (rawParents.length !== nodeUuid.ids.length) {
      throw graphProjectionError("GF_GRAPH_COLUMN_SHAPE", "parent UUID column length differs from nodes", { field: parentField });
    }
    parentIds = new Uint8Array(nodeUuid.ids.length * 16);
    parentValidity = new Uint8Array(nodeUuid.ids.length);
    for (let row = 0; row < rawParents.length; row += 1) {
      if (rawParents[row] == null) continue;
      const parsed = parseUuid(rawParents[row], parentField, row);
      parentIds.set(parsed.bytes, row * 16);
      parentValidity[row] = 1;
    }
  }
  let projection;
  try {
    const handle = graphProjectionCreate({
      nodeIds: nodeUuid.bytes, edgeIds: edgeUuid.bytes,
      sourceIds: sourceUuid.bytes, targetIds: targetUuid.bytes,
      parentIds, parentValidity, directed: opts.directed ?? true,
    });
    try {
      projection = graphProjectionRead(handle);
    } finally {
      graphProjectionDestroy(handle);
    }
  } catch (error) {
    if (error?.nativeCode === -4) throw graphProjectionError("GF_GRAPH_NODE_DUPLICATE", "node UUIDs must be unique");
    if (error?.nativeCode === -5) throw graphProjectionError("GF_GRAPH_EDGE_DUPLICATE", "edge UUIDs must be unique");
    if (error?.nativeCode === -6) throw graphProjectionError("GF_GRAPH_ENDPOINT_MISSING", "edge endpoint or parent UUID is absent from nodes");
    throw error;
  }
  const nodeProvenanceField = mapping.node_provenance_row ?? "provenance_row";
  const edgeProvenanceField = mapping.edge_provenance_row ?? "provenance_row";
  const nodeProvenanceRows = nodeNames.includes(nodeProvenanceField)
    ? BigUint64Array.from(tableColumn(nodes, nodeProvenanceField), BigInt)
    : BigUint64Array.from({ length: nodeUuid.ids.length }, (_, index) => BigInt(index));
  const edgeProvenanceRows = edgeNames.includes(edgeProvenanceField)
    ? BigUint64Array.from(tableColumn(edges, edgeProvenanceField), BigInt)
    : BigUint64Array.from({ length: edgeUuid.ids.length }, (_, index) => BigInt(index));
  if (nodeProvenanceRows.length !== nodeUuid.ids.length || edgeProvenanceRows.length !== edgeUuid.ids.length) {
    throw graphProjectionError(
      "GF_GRAPH_PROVENANCE_LENGTH",
      "provenance columns must match their table row counts",
    );
  }
  return {
    ids: nodeUuid.ids,
    edgeIds: edgeUuid.ids,
    sources: projection.sources,
    targets: projection.targets,
    x: null,
    y: null,
    nodeAttrs: attributeColumns(
      nodes,
      nodeNames,
      new Set([nodeIdField, parentField, nodeProvenanceField]),
      nodeUuid.ids.length,
    ),
    edgeAttrs: attributeColumns(
      edges,
      edgeNames,
      new Set([edgeIdField, sourceField, targetField, edgeProvenanceField]),
      edgeUuid.ids.length,
    ),
    nodeUuidBytes: nodeUuid.bytes,
    edgeUuidBytes: edgeUuid.bytes,
    nodeProvenanceRows,
    edgeProvenanceRows,
    parentIndices: projection.parents,
    parentValidity: projection.parentValidity,
    directed: projection.directed,
    get nNodes() { return this.ids.length; },
    get nEdges() { return this.sources.length; },
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

  const configuredCose = layoutName === "cose"
    && (opts.cose != null || opts.pinned != null || data.parentIndices != null);
  if (configuredCose && iterations <= 0) {
    throw new RangeError("configured CoSE requires iterations > 0");
  }

  if (graphIsProgressiveForce(layoutName) && iterations > 0) {
    const pinned = resolveEncodingValues(data, opts.pinned, "node");
    let parents = null;
    if (layoutName === "cose" && data.parentIndices != null) {
      if (data.parentIndices.length !== n || data.parentValidity?.length !== n) {
        throw new RangeError("CoSE compound parent metadata must have length nNodes");
      }
      parents = new BigUint64Array(n);
      parents.fill((1n << 64n) - 1n);
      for (let index = 0; index < n; index += 1) {
        if (data.parentValidity[index] !== 0) parents[index] = data.parentIndices[index];
      }
    }
    const handle = graphForceCreate(n, sources, targets, {
      x: data.x,
      y: data.y,
      seed,
      algorithm: layoutName,
      cose: opts.cose,
      pinned,
      parents,
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
  const edgeCurve = String(opts.edgeCurve ?? "straight").trim().toLowerCase();
  if (edgeCurve !== "straight" && edgeCurve !== "curve") {
    throw new Error(`graph edgeCurve must be "straight" or "curve", got ${JSON.stringify(opts.edgeCurve)}`);
  }
  // Border-aware ends (#33): Rust trims edges to node outlines and places
  // arrowheads in screen space from each render node's radius and shape.
  const diameters = opts.nodeDiameterPx;
  const nodeRadiusPx = diameters != null && diameters.length === rx.length
    ? Float64Array.from(diameters, (d) => Number(d) * 0.5)
    : new Float64Array(rx.length).fill(Number(opts.nodeDiameter ?? 8) * 0.5);
  const routed = graphEdgeRouteEnds(rx, ry, edgeS, edgeT, {
    directed: Boolean(data.directed),
    separation: opts.edgeSeparation ?? 0.08,
    loopRadius: opts.loopRadius ?? 0.35,
    curved: edgeCurve === "curve",
    nodeRadiusPx,
    nodeSymbol: opts.nodeShapeCodes != null && opts.nodeShapeCodes.length === rx.length
      ? opts.nodeShapeCodes
      : new Uint8Array(rx.length).fill(GRAPH_NODE_SHAPE_CODES[opts.symbol] ?? 0),
  });
  const edgeSegments = {
    x0: routed.x0,
    y0: routed.y0,
    x1: routed.x1,
    y1: routed.y1,
  };
  const renderEdgeIndex = routed.edgeIndex;

  const meta = {
    layout: layoutName,
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
    render_edge_index: Array.from(renderEdgeIndex, (v) => Number(v)),
    node_budget: nodeBudget,
    edge_budget: edgeBudget,
    directed: Boolean(data.directed),
    ids: data.ids.map(String),
  };

  if (graphIsProgressiveForce(layoutName) && iterations > 0) {
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
    edgeEnds: routed.ends,
    meta,
    // Host-side only (#33); never serialized into graphMeta.
    edgeMembership: { offsets: render.edgeMemberOffsets, members: render.edgeMembers },
  };
}

/** Scatter symbol codes with exact edge-trim outlines (circle is 0 and the
 * default; other symbols trim to their circumscribed circle), #33. */
const GRAPH_NODE_SHAPE_CODES = { circle: 0, square: 1, diamond: 2 };

/** Source edges listed per edge pick before truncation; mirrors Python
 * `GRAPH_EDGE_PICK_MEMBER_CAP` in python/xyg/_graph.py. */
export const GRAPH_EDGE_PICK_MEMBER_CAP = 256;

/**
 * Host-side identity plane for one graph's routed edge trace (#33).
 * `renderEdgeIndex[segment]` names the render edge that painted a segment;
 * render edge r represents source edges `members[offsets[r] .. offsets[r+1]]`.
 */
export function createGraphEdgeIdentity(renderEdgeIndex, offsets, members, sourceEdgeIds = null) {
  const count = (r) => Number(offsets[r + 1] - offsets[r]);
  const renderEdges = offsets.length - 1;
  return {
    renderEdges,
    count,
    /** Source edge per render edge when every render edge has one member. */
    singleMember() {
      for (let r = 0; r < renderEdges; r += 1) if (count(r) !== 1) return null;
      return Array.from({ length: renderEdges }, (_, r) => Number(members[Number(offsets[r])]));
    },
    /** Exact source edge, or deterministic aggregate membership — never a guess. */
    pick(segment) {
      const index = Number(segment);
      if (!Number.isInteger(index) || index < 0 || index >= renderEdgeIndex.length) return null;
      const renderEdge = Number(renderEdgeIndex[index]);
      const start = Number(offsets[renderEdge]);
      const total = count(renderEdge);
      const shown = Array.from(
        members.subarray(start, start + Math.min(total, GRAPH_EDGE_PICK_MEMBER_CAP)),
        Number,
      );
      const out = {
        render_edge: renderEdge,
        edge_count: total,
        source_edges: shown,
        members_truncated: total > shown.length,
      };
      if (sourceEdgeIds != null) out.edge_ids = shown.map((m) => sourceEdgeIds[m]);
      return out;
    },
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
 * True when both tables expose GraphForge UUID identity columns.
 * Honors the same `mapping` overrides as `fromGraphForgeTables`.
 * @param {unknown} nodes
 * @param {unknown} edges
 * @param {object} [mapping]
 */
export function looksLikeGraphForgeTables(nodes, edges, mapping = {}) {
  try {
    const nodeNames = new Set(tableColumnNames(nodes));
    const edgeNames = new Set(tableColumnNames(edges));
    const nodeIdField = mapping.node_uuid ?? "node_uuid";
    const edgeIdField = mapping.edge_uuid ?? "edge_uuid";
    return nodeNames.has(nodeIdField) && edgeNames.has(edgeIdField);
  } catch {
    return false;
  }
}

/**
 * Resolve xyg-native pairs, a ready GraphData object, or GraphForge tables.
 * @param {unknown} nodes
 * @param {unknown} [edges]
 * @param {object} [opts]
 */
export function resolveGraphData(nodes, edges = undefined, opts = {}) {
  if (nodes != null && typeof nodes === "object" && Array.isArray(nodes.ids) && nodes.sources != null) {
    if (edges != null) {
      throw new TypeError(
        "when nodes is GraphData, edges must be omitted (pass GraphData alone or table/sequence pairs)",
      );
    }
    return nodes;
  }
  if (edges == null) {
    throw new TypeError("graph edges are required unless nodes is GraphData");
  }
  if (looksLikeGraphForgeTables(nodes, edges, opts.mapping ?? {})) {
    const data = fromGraphForgeTables(nodes, edges, opts);
    if (opts.x != null || opts.y != null) {
      if ((opts.x == null) !== (opts.y == null)) {
        throw new Error("x and y must both be provided or both omitted");
      }
      data.x = Float64Array.from(opts.x, Number);
      data.y = Float64Array.from(opts.y, Number);
      if (data.x.length !== data.ids.length || data.y.length !== data.ids.length) {
        throw new Error("x/y must match node count");
      }
    }
    return data;
  }
  return normalizeGraphInputs(nodes, edges, opts);
}

function jsonScalar(value) {
  if (value == null) return null;
  // Keep integers beyond Number.MAX_SAFE_INTEGER as decimal strings so hover
  // / meta JSON cannot silently change provenance or typed attrs.
  if (typeof value === "bigint") return value.toString();
  if (typeof value === "number") {
    if (Number.isInteger(value) && Math.abs(value) > Number.MAX_SAFE_INTEGER) {
      return String(value);
    }
    return value;
  }
  if (typeof value === "string" || typeof value === "boolean") {
    return value;
  }
  return String(value);
}

/**
 * Build node/edge semantic hover rows from a validated projection.
 * @param {object} data
 * @returns {[object[]|null, object[]|null]}
 */
export function projectionTooltipRows(data) {
  const hasProjection =
    data.nodeUuidBytes != null ||
    data.edgeUuidBytes != null ||
    (data.nodeAttrs && Object.keys(data.nodeAttrs).length > 0) ||
    (data.edgeAttrs && Object.keys(data.edgeAttrs).length > 0) ||
    data.nodeProvenanceRows != null ||
    data.edgeProvenanceRows != null;
  if (!hasProjection) return [null, null];

  const nodeRows = [];
  for (let i = 0; i < data.ids.length; i += 1) {
    const row = { id: String(data.ids[i]) };
    if (data.nodeProvenanceRows != null) {
      row.provenance_row = Number(data.nodeProvenanceRows[i]);
    }
    for (const [key, col] of Object.entries(data.nodeAttrs ?? {})) {
      const values = Array.isArray(col) || ArrayBuffer.isView(col) ? col : [...col];
      row[key] = jsonScalar(values[i]);
    }
    nodeRows.push(row);
  }

  const edgeRows = [];
  for (let i = 0; i < data.sources.length; i += 1) {
    const src = Number(data.sources[i]);
    const tgt = Number(data.targets[i]);
    const row = {
      source: String(data.ids[src]),
      target: String(data.ids[tgt]),
    };
    if (data.edgeIds?.length) row.edge_id = String(data.edgeIds[i]);
    if (data.edgeProvenanceRows != null) {
      row.provenance_row = Number(data.edgeProvenanceRows[i]);
    }
    for (const [key, col] of Object.entries(data.edgeAttrs ?? {})) {
      const values = Array.isArray(col) || ArrayBuffer.isView(col) ? col : [...col];
      row[key] = jsonScalar(values[i]);
    }
    edgeRows.push(row);
  }
  return [nodeRows, edgeRows];
}

function resolveEncodingValues(data, values, where = "node") {
  if (typeof values !== "string") return values;
  const attrs = where === "node" ? data.nodeAttrs : data.edgeAttrs;
  if (attrs && Object.prototype.hasOwnProperty.call(attrs, values)) {
    return attrs[values];
  }
  return values;
}

/**
 * Compose a graph into figure traces + graph meta (conceptual parity with
 * Python `Figure.graph` / `marks.graph`).
 *
 * @param {Iterable|object} nodes
 * @param {Iterable|object} [edges]
 * @param {object} [opts]
 */
/** Ship Rust-lowered semantic paint layers (#34) as per-item trace channels,
 * gathering source rows through `rows` (output index -> source row). Absent
 * layers ship nothing. Mirrors Python `_add_layer_channels`. */
function graphLayerChannels(layers, rows, edge) {
  const n = rows.length;
  const out = {};
  const rgba = (source) => {
    const values = new Uint8Array(n * 4);
    rows.forEach((row, i) => values.set(source.subarray(row * 4, row * 4 + 4), i * 4));
    return values;
  };
  const floats = (source, components = 1) => {
    const values = new Float64Array(n * components);
    rows.forEach((row, i) => {
      for (let c = 0; c < components; c += 1) values[i * components + c] = source[row * components + c];
    });
    return values;
  };
  const halo = rgba(layers.haloRgba);
  if (halo.some((v) => v !== 0)) {
    out.halo_rgba = { values: halo, components: 4, dtype: "u8" };
    out[edge ? "halo_width" : "halo_size"] = { values: floats(layers.haloExtent) };
  }
  if (!edge) return out;
  const body = rgba(layers.bodyRgba);
  if (body.some((v) => v !== 0)) {
    out.body_rgba = { values: body, components: 4, dtype: "u8" };
    out.body_width = { values: floats(layers.bodyWidth) };
  }
  const dash = floats(layers.dashPx, 2);
  if (dash.some((v, i) => i % 2 === 1 && v > 0)) out.edge_dash = { values: dash, components: 2 };
  return out;
}
const GRAPH_SEMANTIC_SHAPES = ["circle", "square", "diamond", "triangle", "cross", "hexagon"];

const GRAPH_SCALE_KEYS = {
  linear: ["type", "colormap", "domain"],
  diverging: ["type", "colormap", "midpoint"],
  ordinal: ["type", "colormap", "order"],
  categorical: ["type", "palette"],
};

/** Resolve a graph color scale into a color channel (#34). Mirrors Python
 * `_color_scale`: diverging domains and ordinal colors come from Rust. */
function graphScaledColor(values, scale, n, fallback, label) {
  if (scale == null) return resolveColorChannel(values, n, fallback);
  const kind = scale?.type;
  if (!Object.hasOwn(GRAPH_SCALE_KEYS, kind)) {
    throw new RangeError(`graph ${label} must be an object with type ${Object.keys(GRAPH_SCALE_KEYS).sort().join(", ")}`);
  }
  const unknown = Object.keys(scale).filter((key) => !GRAPH_SCALE_KEYS[kind].includes(key));
  if (unknown.length) throw new RangeError(`graph ${label} ${JSON.stringify(kind)} does not accept ${JSON.stringify(unknown.sort())}`);
  const items = Array.from(values);
  if (kind === "linear" || kind === "diverging") {
    const numeric = Float64Array.from(items, Number);
    const channel = resolveColorChannel(numeric, n, fallback);
    const domain = kind === "diverging"
      ? graphDivergingDomain(numeric, Number(scale.midpoint ?? 0))
      : scale.domain != null ? [Number(scale.domain[0]), Number(scale.domain[1])] : channel.domain;
    return { ...channel, domain, colormap: scale.colormap ?? (kind === "diverging" ? "rdbu" : "viridis") };
  }
  if (kind === "ordinal") {
    const order = Array.from(scale.order ?? []).map(String);
    if (!order.length || new Set(order).size !== order.length) {
      throw new RangeError(`graph ${label} ordinal needs a nonempty, unique 'order'`);
    }
    const index = new Map(order.map((level, i) => [level, i]));
    const missing = [...new Set(items.map(String).filter((v) => !index.has(v)))].sort();
    if (missing.length) throw new RangeError(`graph ${label} values ${JSON.stringify(missing.slice(0, 4))} are not in the ordinal order`);
    return {
      mode: "categorical",
      codes: Uint8Array.from(items, (v) => index.get(String(v))),
      categories: order,
      palette: graphOrdinalColors(scale.colormap ?? "viridis", order.length),
    };
  }
  const channel = resolveColorChannel(items, n, fallback);
  if (channel.mode !== "categorical") throw new RangeError(`graph ${label} categorical needs category labels`);
  if (scale.palette != null) {
    const palette = Array.from(scale.palette, String);
    if (!palette.length) throw new RangeError(`graph ${label} categorical 'palette' must not be empty`);
    const nCategories = channel.categories?.length ?? 0;
    if (nCategories > palette.length) {
      // Allowed (colors cycle), never silent — Python warns the same (§28).
      process.emitWarning(
        `graph ${label} categorical has ${nCategories} categories but the palette has ${palette.length} colors; `
          + `colors repeat every ${palette.length} categories (category ${palette.length + 1} wears category 1's color). `
          + "Pass a longer palette.",
        "RuntimeWarning",
      );
    }
    return { ...channel, palette };
  }
  return channel;
}

/** Source-row semantic columns for one graph side, or null when unset (#34). */
function graphSemanticFields(data, where, raw) {
  if (raw.every((value) => value == null)) return null;
  const attrs = where === "node" ? data.nodeAttrs : data.edgeAttrs;
  const n = where === "node" ? data.ids.length : data.sources.length;
  const labels = ["class", "epistemic", "status", "metric"];
  return raw.map((value, index) => {
    const label = `graph ${where}_${labels[index]}`;
    if (typeof value === "string") {
      if (attrs == null || !Object.hasOwn(attrs, value)) {
        throw new RangeError(`${label} names unknown ${where} column ${JSON.stringify(value)}`);
      }
      value = attrs[value];
    }
    if (value == null) return index === 3 ? new Float64Array(n) : new Uint8Array(n);
    const rows = typeof value === "number" ? new Array(n).fill(value) : Array.from(value);
    if (rows.length !== n) throw new RangeError(`${label} must match ${where} count ${n}`);
    if (index === 3) return Float64Array.from(rows, Number);
    if (!rows.every((code) => typeof code === "number" && Number.isInteger(code))) {
      throw new RangeError(`${label} must be integer codes 0..7`);
    }
    // Validate every source row even when Aggregate LOD omits paint.
    if (rows.some((code) => code < 0 || code > 7)) {
      throw new RangeError(`${label} codes must be in 0..7`);
    }
    return rows;
  });
}

// Style keys that would override each side's resolved semantic paint.
const GRAPH_NODE_SEMANTIC_STYLE = [
  "color", "fill", "opacity", "stroke", "stroke_width", "strokeWidth", "stroke-width",
  "symbol", "marker-shape", "fill_opacity", "fill-opacity", "stroke_opacity", "stroke-opacity",
  "size",
];
const GRAPH_EDGE_SEMANTIC_STYLE = ["color", "stroke", "width", "stroke_width", "stroke-width", "opacity"];

/** label_plan channel row: threshold, offset x, offset y, width, font px
 * (#34); mirrors Python `LABEL_PLAN_COMPONENTS`. */
const GRAPH_LABEL_PLAN_COMPONENTS = 5;
/** Hidden members listed per collapsed-group pick; mirrors Python
 * `COMPOUND_PICK_MEMBER_CAP`. */
const COMPOUND_PICK_MEMBER_CAP = 256;
/** compound_frame channel row (#34): bounds deltas (4), RGBA (4), width, pad;
 * mirrors Python `COMPOUND_FRAME_COMPONENTS`. */
const COMPOUND_FRAME_COMPONENTS = 10;

function graphCollapsedMask(data, collapsed) {
  const n = data.ids.length;
  let values = collapsed;
  if (typeof values === "string") {
    if (!Object.hasOwn(data.nodeAttrs, values)) {
      throw new RangeError(`graph collapsed names unknown node column ${JSON.stringify(values)}`);
    }
    values = data.nodeAttrs[values];
  }
  const rows = Array.from(values);
  if (rows.length === n && rows.every((v) => typeof v === "boolean")) return Uint8Array.from(rows, Number);
  const wanted = new Set(rows.map(String));
  const ids = data.ids.map(String);
  const unknown = [...wanted].filter((id) => !ids.includes(id)).sort();
  if (unknown.length) throw new RangeError(`graph collapsed ids ${JSON.stringify(unknown.slice(0, 4))} are not nodes`);
  return Uint8Array.from(ids, (id) => (wanted.has(id) ? 1 : 0));
}

function takeRows(values, idx, count) {
  if (values == null) return values;
  const stride = count > 0 && values.length % count === 0 ? values.length / count : 1;
  if (ArrayBuffer.isView(values)) {
    const out = new values.constructor(idx.length * stride);
    idx.forEach((row, j) => { for (let k = 0; k < stride; k += 1) out[j * stride + k] = values[row * stride + k]; });
    return out;
  }
  return idx.map((row) => values[row]);
}

/** Lay the full graph out once, then let Rust collapse it (#34). Mirrors
 * Python `_collapse_compounds`. */
function graphCollapseCompounds(data, collapsed, opts) {
  if (data.parentIndices == null) {
    throw new RangeError("graph collapsed needs compound parents (GraphForge parent_uuid)");
  }
  const n = data.ids.length;
  const e = data.sources.length;
  const mask = graphCollapsedMask(data, collapsed);
  const { nodePositions, meta } = runLayout(data, { ...opts, includeCsr: false });
  if (Number(meta.lod_tier) !== 0 || nodePositions.x.length !== n) {
    throw new RangeError("graph compound disclosure needs Direct LOD: collapse keeps exact node identity, which Aggregate LOD does not have");
  }
  const attr = (value) => typeof value === "string" && Object.hasOwn(data.nodeAttrs, value) ? data.nodeAttrs[value] : value;
  const rawFlags = attr(opts.visualStateFlags ?? opts.visual_state_flags)
    ?? data.nodeAttrs.visual_state_flags ?? data.nodeAttrs.state_flags ?? new Uint32Array(n);
  const flags = typeof rawFlags === "number" ? new Uint32Array(n).fill(rawFlags) : Uint32Array.from(rawFlags, Number);
  const validity = data.parentValidity ?? new Uint8Array(n).fill(1);
  const out = graphCompoundCollapse(data.parentIndices, validity, mask, flags, data.sources, data.targets);
  const rows = [];
  const newIndex = new Int32Array(n).fill(-1);
  for (let i = 0; i < n; i += 1) if (out.visible[i]) { newIndex[i] = rows.length; rows.push(i); }
  const erows = [];
  for (let k = 0; k < e; k += 1) if (out.edgeKeep[k]) erows.push(k);
  const parents = new BigUint64Array(rows.length);
  const parentValidity = new Uint8Array(rows.length);
  rows.forEach((row, j) => {
    if (!validity[row]) return;
    const mapped = newIndex[Number(data.parentIndices[row])];
    if (mapped >= 0) { parents[j] = BigInt(mapped); parentValidity[j] = 1; }
  });
  const sub = {
    ids: rows.map((row) => data.ids[row]),
    edgeIds: Array.isArray(data.edgeIds) ? erows.map((k) => data.edgeIds[k]) : data.edgeIds,
    sources: BigUint64Array.from(erows, (k) => BigInt(newIndex[Number(out.edgeSource[k])])),
    targets: BigUint64Array.from(erows, (k) => BigInt(newIndex[Number(out.edgeTarget[k])])),
    x: Float64Array.from(rows, (row) => nodePositions.x[row]),
    y: Float64Array.from(rows, (row) => nodePositions.y[row]),
    nodeAttrs: Object.fromEntries(Object.entries(data.nodeAttrs).map(([k, v]) => [k, takeRows(v, rows, n)])),
    edgeAttrs: Object.fromEntries(Object.entries(data.edgeAttrs ?? {}).map(([k, v]) => [k, takeRows(v, erows, e)])),
    nodeUuidBytes: takeRows(data.nodeUuidBytes, rows, n),
    edgeUuidBytes: takeRows(data.edgeUuidBytes, erows, e),
    nodeProvenanceRows: takeRows(data.nodeProvenanceRows, rows, n),
    edgeProvenanceRows: takeRows(data.edgeProvenanceRows, erows, e),
    parentIndices: parents,
    parentValidity,
    directed: data.directed,
    get nNodes() { return this.ids.length; },
    get nEdges() { return this.sources.length; },
  };
  // One pass: hidden nodes bucketed by representative, in node order.
  const byGroup = new Map();
  for (let i = 0; i < n; i += 1) {
    if (out.visible[i]) continue;
    const rep = Number(out.representative[i]);
    if (!byGroup.has(rep)) byGroup.set(rep, []);
    byGroup.get(rep).push(String(data.ids[i]));
  }
  const members = new Map();
  for (let group = 0; group < n; group += 1) {
    if (!mask[group] || !out.visible[group]) continue;
    const hidden = byGroup.get(group) ?? [];
    members.set(newIndex[group], {
      compound_collapsed: true,
      compound_member_count: hidden.length,
      compound_members: hidden.slice(0, COMPOUND_PICK_MEMBER_CAP),
      compound_members_truncated: hidden.length > COMPOUND_PICK_MEMBER_CAP,
    });
  }
  return {
    data: sub,
    rows,
    erows,
    newIndex,
    visible: out.visible,
    mask,
    flagsVisible: Uint32Array.from(rows, (row) => out.flags[row]),
    positions: nodePositions,
    collapsedIds: data.ids.filter((_, i) => mask[i]).map(String),
    members,
  };
}

function graphSubsetOptions(opts, compound, full) {
  const n = full.ids.length;
  const e = full.sources.length;
  const subset = (value, idx, count) =>
    value != null && typeof value !== "string" && typeof value !== "number"
      && (Array.isArray(value) || ArrayBuffer.isView(value)) && value.length === count
      ? takeRows(value, idx, count)
      : value;
  const nodeKeys = ["color", "size", "nodeLabel", "node_label", "labelPriority", "label_priority",
    "nodeClass", "node_class", "nodeEpistemic", "node_epistemic", "nodeStatus", "node_status",
    "nodeMetric", "node_metric"];
  const edgeKeys = ["edgeColor", "edge_color", "edgeWidth", "edge_width", "edgeLabel", "edge_label",
    "edgeLabelPriority", "edge_label_priority", "edgeClass", "edge_class", "edgeEpistemic",
    "edge_epistemic", "edgeStatus", "edge_status", "edgeMetric", "edge_metric"];
  const out = { ...opts, layout: "preset", pinned: undefined, cose: undefined,
    visualStateFlags: compound.flagsVisible, visual_state_flags: undefined };
  for (const key of nodeKeys) out[key] = subset(opts[key], compound.rows, n);
  for (const key of edgeKeys) out[key] = subset(opts[key], compound.erows, e);
  return out;
}

/** Rust compound frames as the node trace's `compound_frame` channel (#34);
 * mirrors Python `_compound_frames` + `_add_compound_frame_channel`. */
function graphCompoundFrameChannel(full, compound, nodePositions, direct, nodeSemantic, radii, theme) {
  if (full.parentIndices == null || (compound == null && !direct)) return null;
  const n = full.ids.length;
  const positions = compound?.positions ?? nodePositions;
  const rowOf = (i) => (compound == null ? i : compound.newIndex[i]);
  const stroke = new Uint8Array(n * 4);
  const opacity = new Float32Array(n).fill(1);
  const radius = new Float64Array(n);
  for (let i = 0; i < n; i += 1) {
    const row = rowOf(i);
    if (row < 0) continue;
    radius[i] = radii[row];
    if (nodeSemantic != null) {
      stroke.set(nodeSemantic.strokeRgba.subarray(row * 4, row * 4 + 4), i * 4);
      opacity[i] = nodeSemantic.opacity[row];
    }
  }
  const validity = full.parentValidity ?? new Uint8Array(n).fill(1);
  const mask = compound?.mask ?? new Uint8Array(n);
  const frames = graphCompoundFrames(positions.x, positions.y, radius, full.parentIndices, validity, mask,
    stroke, opacity, { theme });
  const rows = nodePositions.x.length;
  const values = new Float64Array(rows * COMPOUND_FRAME_COMPONENTS);
  const ids = [];
  frames.node.forEach((node, k) => {
    const i = Number(node);
    const row = rowOf(i);
    const at = row * COMPOUND_FRAME_COMPONENTS;
    values[at] = frames.bounds[k * 4] - nodePositions.x[row];
    values[at + 1] = frames.bounds[k * 4 + 1] - nodePositions.x[row];
    values[at + 2] = frames.bounds[k * 4 + 2] - nodePositions.y[row];
    values[at + 3] = frames.bounds[k * 4 + 3] - nodePositions.y[row];
    for (let c = 0; c < 4; c += 1) values[at + 4 + c] = frames.rgba[k * 4 + c];
    values[at + 8] = frames.width[k];
    values[at + 9] = frames.pad[k];
    ids.push(String(full.ids[i]));
  });
  return { ids, channel: { values, components: COMPOUND_FRAME_COMPONENTS } };
}

/** Per render edge: label text, priority, and anchor segment (the middle
 * routed piece), for single-member render edges only. Mirrors Python
 * `_edge_label_rows`. */
function graphEdgeLabelRows(data, opts, singleMember, renderEdgeIndex) {
  const empty = { texts: [], priorities: [], anchors: [] };
  let raw = opts.edgeLabel ?? opts.edge_label;
  if (raw == null || singleMember == null) return empty;
  const nEdges = data.sources.length;
  if (typeof raw === "string" && data.edgeAttrs && Object.hasOwn(data.edgeAttrs, raw)) raw = data.edgeAttrs[raw];
  const rows = typeof raw === "string" ? new Array(nEdges).fill(raw) : Array.from(raw);
  if (rows.length !== nEdges) throw new RangeError("graph edgeLabel must match edge count");
  if (rows.some((value) => value != null && typeof value !== "string")) {
    throw new TypeError("graph edge labels must be strings or null");
  }
  let rawPriority = opts.edgeLabelPriority ?? opts.edge_label_priority ?? 0;
  if (typeof rawPriority === "string" && data.edgeAttrs && Object.hasOwn(data.edgeAttrs, rawPriority)) {
    rawPriority = data.edgeAttrs[rawPriority];
  }
  const priority = typeof rawPriority === "number"
    ? new Float64Array(nEdges).fill(rawPriority)
    : Float64Array.from(rawPriority, Number);
  if (priority.length !== nEdges) throw new RangeError("graph edgeLabelPriority must match edge count");
  const counts = new Array(singleMember.length).fill(0);
  const starts = new Array(singleMember.length).fill(-1);
  renderEdgeIndex.forEach((renderEdge, segment) => {
    const r = Number(renderEdge);
    if (segment > 0 && r < Number(renderEdgeIndex[segment - 1])) {
      throw new RangeError("graph routing must emit every render edge's segments contiguously");
    }
    if (starts[r] < 0) starts[r] = segment;
    counts[r] += 1;
  });
  if (counts.some((count) => count === 0)) {
    throw new RangeError("graph routing must emit every render edge's segments contiguously");
  }
  const texts = []; const priorities = []; const anchors = [];
  singleMember.forEach((member, r) => {
    const row = Number(member);
    texts.push(rows[row]);
    priorities.push(rows[row] == null ? Number.NaN : priority[row]);
    anchors.push(starts[r] + Math.floor(counts[r] / 2));
  });
  return { texts, priorities, anchors };
}

/**
 * Rust semantic legend rows (#34): one row per class/epistemic/status value
 * across the given node/edge field planes, in the semantic Scene's order, with
 * Rust-owned text. Returns `{ title, items }`, or null without rows. Mirrors
 * Python `_marks_graph._apply_semantic_legend`.
 */
export function graphSemanticLegendItems(planes, theme) {
  const plane = (k) => planes.flatMap((fields) => Array.from(fields[k]));
  const rows = graphSemanticLegend(plane(0), plane(1), plane(2), { theme });
  const hex = (v) => v.toString(16).padStart(2, "0");
  const items = [...rows.field].map((field, i) => ({
    kind: "scatter",
    name: graphSemanticLegendText(field, rows.value[i]),
    style: {
      color: `#${hex(rows.rgba[i * 4])}${hex(rows.rgba[i * 4 + 1])}${hex(rows.rgba[i * 4 + 2])}`,
      symbol: GRAPH_SEMANTIC_SHAPES[rows.shape[i] % GRAPH_SEMANTIC_SHAPES.length],
    },
  }));
  return items.length ? { title: graphSemanticLegendText(3), items } : null;
}

export function composeGraph(nodes, edges, opts = {}) {
  let resolvedOpts = opts;
  let resolvedEdges = edges;
  // Allow composeGraph(graphData, { layout / size / ... }) when the second arg
  // is a plain options object rather than an edges table.
  if (
    nodes != null &&
    typeof nodes === "object" &&
    Array.isArray(nodes.ids) &&
    nodes.sources != null
  ) {
    if (edges != null) {
      if (
        typeof edges !== "object" ||
        Array.isArray(edges) ||
        edges.source != null ||
        edges.target != null ||
        edges.edge_uuid != null ||
        edges.src_uuid != null ||
        edges.dst_uuid != null
      ) {
        throw new TypeError(
          "when nodes is GraphData, edges must be omitted (pass GraphData alone or table/sequence pairs)",
        );
      }
      resolvedOpts = edges;
      resolvedEdges = undefined;
    } else {
      resolvedEdges = undefined;
    }
  } else if (edges == null) {
    resolvedEdges = undefined;
  }
  let data = resolveGraphData(nodes, resolvedEdges, {
    x: resolvedOpts.x,
    y: resolvedOpts.y,
    directed: resolvedOpts.directed,
    mapping: resolvedOpts.mapping,
  });
  // Compound disclosure (#34): lay the full graph out once, let Rust collapse
  // it, then compose the visible graph at those positions.
  const full = data;
  let compound = null;
  if (resolvedOpts.collapsed != null) {
    compound = graphCollapseCompounds(data, resolvedOpts.collapsed, resolvedOpts);
    data = compound.data;
    resolvedOpts = graphSubsetOptions(resolvedOpts, compound, full);
  }
  const nodeColor = resolveEncodingValues(data, resolvedOpts.color, "node");
  const edgeColor = resolveEncodingValues(
    data,
    resolvedOpts.edgeColor ?? resolvedOpts.edge_color,
    "edge",
  );
  const semanticOpt = (camel, snake) => resolvedOpts[camel] ?? resolvedOpts[snake];
  const nodeFields = graphSemanticFields(data, "node", [
    semanticOpt("nodeClass", "node_class"),
    semanticOpt("nodeEpistemic", "node_epistemic"),
    semanticOpt("nodeStatus", "node_status"),
    semanticOpt("nodeMetric", "node_metric"),
  ]);
  const edgeFields = graphSemanticFields(data, "edge", [
    semanticOpt("edgeClass", "edge_class"),
    semanticOpt("edgeEpistemic", "edge_epistemic"),
    semanticOpt("edgeStatus", "edge_status"),
    semanticOpt("edgeMetric", "edge_metric"),
  ]);
  if (nodeFields != null && (resolvedOpts.color != null || resolvedOpts.size != null)) {
    throw new RangeError("graph node semantic fields replace color and size");
  }
  if (edgeFields != null && edgeColor != null) {
    throw new RangeError("graph edge semantic fields replace edgeColor");
  }
  for (const [fields, keys, side] of [
    [nodeFields, GRAPH_NODE_SEMANTIC_STYLE, "node"],
    [edgeFields, GRAPH_EDGE_SEMANTIC_STYLE, "edge"],
  ]) {
    const conflicts = fields == null ? [] : keys.filter((key) => resolvedOpts.style?.[key] != null);
    if (conflicts.length) {
      throw new RangeError(`graph ${side} semantic fields own paint; style must not set ${JSON.stringify(conflicts)}`);
    }
  }
  const colorScale = resolvedOpts.colorScale ?? resolvedOpts.color_scale ?? null;
  const edgeColorScale = resolvedOpts.edgeColorScale ?? resolvedOpts.edge_color_scale ?? null;
  if (nodeFields != null && colorScale != null) throw new RangeError("graph node semantic fields replace colorScale");
  if (edgeFields != null && edgeColorScale != null) throw new RangeError("graph edge semantic fields replace edgeColorScale");
  for (const [scale, label, values] of [[colorScale, "colorScale", nodeColor], [edgeColorScale, "edgeColorScale", edgeColor]]) {
    if (scale != null && (values == null || typeof values === "string")) {
      throw new RangeError(`graph ${label} needs a per-item color array or column`);
    }
  }
  const theme = resolvedOpts.theme ?? "light";
  if (theme !== "light" && theme !== "dark") {
    throw new RangeError(`graph theme must be 'light' or 'dark', got ${JSON.stringify(theme)}`);
  }
  const resolveNodeAttr = (value) =>
    typeof value === "string" && Object.hasOwn(data.nodeAttrs, value) ? data.nodeAttrs[value] : value;
  const rawFlags = resolveNodeAttr(
    resolvedOpts.visualStateFlags ?? resolvedOpts.visual_state_flags,
  ) ?? data.nodeAttrs.visual_state_flags ?? data.nodeAttrs.state_flags ?? new Uint32Array(data.ids.length);
  const nodeFlags = typeof rawFlags === "number"
    ? new Uint32Array(data.ids.length).fill(rawFlags)
    : rawFlags;
  // Semantic styling (#34): Rust resolves the v1 contract per source row; rows
  // paint only where render identity is exact (checked after layout).
  const nodeSemantic = nodeFields == null
    ? null
    : graphSemanticStyles(...nodeFields, nodeFlags, { theme });
  const sizeOpt = nodeSemantic != null
    ? nodeSemantic.size
    : resolveEncodingValues(data, resolvedOpts.size, "node");
  // Node marker diameters (px) for edge trimming, mapped exactly as the node
  // scatter ships them (array sizes span range_px [8, 22] over their domain).
  let nodeDiameterPx = null;
  if (nodeSemantic != null) {
    nodeDiameterPx = Float64Array.from(nodeSemantic.size);
  } else if (Array.isArray(sizeOpt) || ArrayBuffer.isView(sizeOpt)) {
    const values = Float64Array.from(sizeOpt, Number);
    const mm = minMax(values) ?? [0, 1];
    const lo = mm[0];
    const span = mm[0] === mm[1] ? 1 : mm[1] - mm[0];
    nodeDiameterPx = Float64Array.from(values, (v) =>
      8 + 14 * (Number.isFinite(v) ? Math.min(1, Math.max(0, (v - lo) / span)) : 0));
  }
  const nodeDiameter = sizeOpt != null && !Array.isArray(sizeOpt) && !ArrayBuffer.isView(sizeOpt)
    ? Number(sizeOpt)
    : 8;
  const { nodePositions, edgeSegments, edgeEnds, meta, edgeMembership } = runLayout(data, {
    ...resolvedOpts,
    nodeDiameterPx,
    nodeShapeCodes: nodeSemantic?.shape ?? null,
    nodeDiameter,
  });
  const name = resolvedOpts.name ?? null;
  const nNodes = nodePositions.x.length;
  const nEdges = edgeSegments.x0.length;
  let styleSize = 8.0;
  let size_ch = resolveSizeChannel(styleSize, nNodes);
  const nodesExact = nNodes === data.ids.length;
  const styleContract = nodeFields == null && edgeFields == null
    ? null
    : {
      version: 1,
      theme,
      nodes: null,
      edges: null,
      // Every v1 layer now paints on the composed mark (#34).
      pending_layers: [],
    };
  let nodePaint = null;
  if (nodeSemantic != null && !nodesExact) {
    styleContract.nodes = "omitted:aggregate";
  } else if (nodeSemantic != null) {
    styleContract.nodes = "resolved";
    styleContract.node_metric_domain = [...nodeSemantic.metricDomain];
    const mm = minMax(Float64Array.from(nodeSemantic.size)) ?? [8, 8];
    // Identity size mapping: values spanning [lo, hi] onto range [lo, hi]
    // paint exact pixels; an all-equal array collapses to one constant.
    size_ch = mm[1] > mm[0]
      ? { mode: "continuous", values: Float64Array.from(nodeSemantic.size), domain: mm, range_px: mm }
      : resolveSizeChannel(mm[0], nNodes);
    nodePaint = {
      color_ch: { mode: "direct_rgba", rgba: nodeSemantic.fillRgba },
      stroke_ch: { mode: "direct_rgba", rgba: nodeSemantic.strokeRgba },
      style_channels: {
        opacity: { values: Float64Array.from(nodeSemantic.opacity) },
        symbol: { values: Uint8Array.from(nodeSemantic.shape), dtype: "u8" },
        stroke_width: { values: Float64Array.from(nodeSemantic.width) },
        ...graphLayerChannels(
          graphSemanticPaintLayers(...nodeFields, nodeFlags, { theme }),
          Array.from({ length: nNodes }, (_, i) => i),
          false,
        ),
      },
    };
  }
  if (nodeSemantic == null && (Array.isArray(sizeOpt) || ArrayBuffer.isView(sizeOpt))) {
    const values = sizeOpt instanceof Float64Array
      ? sizeOpt
      : Float64Array.from(sizeOpt, Number);
    if (values.length !== nNodes) {
      throw new RangeError(
        `graph size length ${values.length} != render n_nodes=${nNodes} ` +
          `(encodings are render-graph indexed after nodeBudget/edgeBudget; ` +
          `source_n_nodes=${meta.source_n_nodes ?? "?"})`,
      );
    }
    const mm = minMax(values) ?? [0, 1];
    size_ch = {
      mode: "continuous",
      values,
      domain: [mm[0], mm[0] === mm[1] ? mm[0] + 1 : mm[1]],
      range_px: [8, 22],
    };
  } else if (nodeSemantic == null && sizeOpt != null) {
    styleSize = Number(sizeOpt);
    size_ch = resolveSizeChannel(styleSize, nNodes);
  }
  let [nodeTooltipRows, edgeTooltipRows] = projectionTooltipRows(data);
  const nodesOneToOne = nNodes === data.ids.length;
  const renderEdgeCount = meta.render_sources?.length ?? meta.n_edges ?? 0;
  const renderEdgeIndex = meta.render_edge_index;
  // Edge identity follows Rust's render-edge membership, not a count match
  // (#33): one-member render edges carry that source edge's row; Aggregate
  // edges carry their member count, never one invented source edge.
  const edgeIdentity = createGraphEdgeIdentity(
    renderEdgeIndex,
    edgeMembership.offsets,
    edgeMembership.members,
    data.edgeIds?.length ? data.edgeIds.map(String) : null,
  );
  const singleMember = edgeIdentity.singleMember();
  if (!(nodeTooltipRows != null && nodesOneToOne)) {
    nodeTooltipRows =
      resolvedOpts.nodeTooltipRows ?? resolvedOpts.tooltipRows ?? resolvedOpts.tooltip_rows ?? null;
  }
  if (edgeTooltipRows != null) {
    const sourceRows = edgeTooltipRows;
    const renderRows = Array.from({ length: renderEdgeCount }, (_, r) =>
      edgeIdentity.count(r) === 1
        ? sourceRows[Number(edgeMembership.members[Number(edgeMembership.offsets[r])])]
        : { edge_count: edgeIdentity.count(r) },
    );
    edgeTooltipRows = renderEdgeIndex.map((i) => renderRows[Number(i)]);
  } else {
    edgeTooltipRows =
      resolvedOpts.edgeTooltipRows ?? resolvedOpts.edge_tooltip_rows ?? null;
    // Caller rows indexed by render edge expand across routed segments.
    if (edgeTooltipRows != null && edgeTooltipRows.length === renderEdgeCount && renderEdgeCount !== nEdges) {
      const rows = edgeTooltipRows;
      edgeTooltipRows = renderEdgeIndex.map((i) => rows[Number(i)]);
    }
  }
  // Per-edge colors are render-edge indexed; expand them across routed
  // segments (loops / arrow wings / curve tessellation) like tooltips.
  let edgeColorPaint = edgeColor;
  if (
    edgeColor != null &&
    (Array.isArray(edgeColor) || ArrayBuffer.isView(edgeColor)) &&
    edgeColor.length !== nEdges &&
    edgeColor.length === renderEdgeCount &&
    Array.isArray(renderEdgeIndex) &&
    renderEdgeIndex.length === nEdges
  ) {
    edgeColorPaint = renderEdgeIndex.map((i) => edgeColor[Number(i)]);
  }
  let edgePaint = null;
  let edgeEndsPaint = null;
  if (edgeFields != null && singleMember == null) {
    styleContract.edges = "omitted:aggregate";
  } else if (edgeFields != null) {
    // Resolve every source edge so the metric domain is the source domain
    // (EdgeSample must not rescale widths), then gather routed segments.
    const resolved = graphSemanticStyles(...edgeFields, new Uint32Array(edgeFields[0].length), {
      edge: true,
      theme,
    });
    styleContract.edges = "resolved";
    styleContract.edge_metric_domain = [...resolved.metricDomain];
    const rgba = new Uint8Array(nEdges * 4);
    const width = new Float64Array(nEdges);
    const opacity = new Float64Array(nEdges);
    renderEdgeIndex.forEach((renderEdge, segment) => {
      const row = Number(singleMember[Number(renderEdge)]);
      rgba.set(resolved.strokeRgba.subarray(row * 4, row * 4 + 4), segment * 4);
      width[segment] = resolved.width[row];
      opacity[segment] = resolved.opacity[row];
    });
    const layers = graphSemanticPaintLayers(...edgeFields, new Uint32Array(edgeFields[0].length), {
      edge: true,
      theme,
    });
    const segmentRows = renderEdgeIndex.map((renderEdge) => Number(singleMember[Number(renderEdge)]));
    // Rust's arrow policy replaces the directed default: the head bit (0x40)
    // follows each segment's source-edge `head` layer.
    edgeEndsPaint = Float64Array.from(edgeEnds);
    segmentRows.forEach((row, segment) => {
      const at = segment * 7 + 6;
      edgeEndsPaint[at] = (edgeEndsPaint[at] & ~0x40) | (layers.head[row] ? 0x40 : 0);
    });
    edgePaint = {
      color_ch: { mode: "direct_rgba", rgba },
      style_channels: {
        width: { values: width },
        opacity: { values: opacity },
        ...graphLayerChannels(layers, segmentRows, true),
      },
    };
  }
  // Rust compound frames (#34) over the full graph's positions.
  const frames = graphCompoundFrameChannel(full, compound, nodePositions, nodesExact, nodeSemantic,
    nodeDiameterPx != null && nodeDiameterPx.length === nNodes
      ? Float64Array.from(nodeDiameterPx, (d) => d / 2)
      : new Float64Array(nNodes).fill(Number(nodeDiameter) / 2),
    theme);
  // Keep auto-built projection rows for meta even when Aggregate collapses edges.
  const [sourceNodeTooltips, sourceEdgeTooltips] = projectionTooltipRows(data);
  if (nodeTooltipRows != null && nodeTooltipRows.length !== nNodes) {
    throw new RangeError(
      `graph node tooltip rows must match geometry (${nodeTooltipRows.length} != ${nNodes})`,
    );
  }
  if (edgeTooltipRows != null && edgeTooltipRows.length !== nEdges) {
    throw new RangeError(
      `graph edge tooltip rows must match geometry (${edgeTooltipRows.length} != ${nEdges})`,
    );
  }  const traces = [
    {
      kind: "segments",
      name: name == null ? null : `${name}:edges`,
      x0: edgeSegments.x0,
      y0: edgeSegments.y0,
      x1: edgeSegments.x1,
      y1: edgeSegments.y1,
      // Border radii + flags per segment (#33); geometry, not per-item paint.
      style_channels: {
        edge_ends: { values: edgeEndsPaint ?? Float64Array.from(edgeEnds), components: 7, dtype: "f32" },
        ...(edgePaint?.style_channels ?? {}),
      },
      style: {
        color: typeof edgeColor === "string" ? edgeColor : "#888888",
        width: resolvedOpts.edgeWidth ?? resolvedOpts.edge_width ?? 1.2,
        ...(edgePaint != null ? { opacity: 1 } : {}),
        ...(resolvedOpts.style ?? {}),
      },
      ...(edgePaint != null
        ? { color_ch: edgePaint.color_ch }
        : edgeColorPaint != null && typeof edgeColorPaint !== "string"
          ? { color_ch: graphScaledColor(edgeColorPaint, edgeColorScale, nEdges, "#888888", "edgeColorScale") }
          : {}),
      ...(edgeTooltipRows != null ? { tooltip_rows: edgeTooltipRows } : {}),
    },
    {
      kind: "scatter",
      name: name == null ? null : `${name}:nodes`,
      x: nodePositions.x,
      y: nodePositions.y,
      style: {
        color: typeof nodeColor === "string" ? nodeColor : DEFAULT_MARK_COLOR,
        symbol: nodePaint != null ? "circle" : resolvedOpts.symbol ?? "circle",
        ...(nodePaint != null ? { opacity: 1 } : {}),
        ...(resolvedOpts.style ?? {}),
      },
      ...(nodePaint != null
        ? {
          color_ch: nodePaint.color_ch,
          stroke_ch: nodePaint.stroke_ch,
          style_channels: nodePaint.style_channels,
          // Density surfaces drop per-node paint; resolved semantic rows must
          // paint exactly as style_contract reports.
          force_direct: true,
        }
        : nodeColor != null && typeof nodeColor !== "string"
          ? { color_ch: graphScaledColor(nodeColor, colorScale, nNodes, DEFAULT_MARK_COLOR, "colorScale") }
          : {}),
      size_ch,
      ...(nodeTooltipRows != null ? { tooltip_rows: nodeTooltipRows } : {}),
    },
  ];
  if (frames != null && frames.ids.length) {
    traces[1].style_channels = { ...(traces[1].style_channels ?? {}), compound_frame: frames.channel };
  }

  const graphMeta = {
    ...Object.fromEntries(
      Object.entries(meta).filter(
        ([k]) => !["member_of", "render_sources", "render_targets", "csr_offsets", "csr_neighbors"].includes(k),
      ),
    ),
    directed: Boolean(data.directed),
    ids: meta.ids ?? data.ids.map(String),
    sources: [...meta.render_sources].map(Number),
    targets: [...meta.render_targets].map(Number),
    member_of: [...meta.member_of].map(Number),
    source_n_nodes: meta.source_n_nodes,
    source_n_edges: meta.source_n_edges,
    csr_offsets: meta.csr_offsets ? [...meta.csr_offsets].map(Number) : undefined,
    csr_neighbors: meta.csr_neighbors ? [...meta.csr_neighbors].map(Number) : undefined,
    node_symbol: typeof resolvedOpts.symbol === "string" ? resolvedOpts.symbol : "circle",
    edge_curve: String(resolvedOpts.edgeCurve ?? "straight").trim().toLowerCase(),
    ...(styleContract != null ? { style_contract: styleContract } : {}),
    ...(frames != null ? { compound_frames: frames.ids } : full.parentIndices != null ? { compound_frames: "omitted:aggregate" } : {}),
    ...(compound != null ? { compound_collapsed: compound.collapsedIds } : {}),
    tier_name: ["direct", "edge_sample", "aggregate"][Math.min(Number(meta.lod_tier), 2)],
    node_trace: 1,
    edge_trace: 0,
  };
  if (nodesOneToOne) {
    const resolveNodeOption = (value) =>
      typeof value === "string" && Object.hasOwn(data.nodeAttrs, value)
        ? data.nodeAttrs[value]
        : value;
    const rawLabels = resolveNodeOption(resolvedOpts.nodeLabel ?? resolvedOpts.node_label)
      ?? data.nodeAttrs.label ?? data.nodeAttrs.name ?? new Array(nNodes).fill(null);
    const rawLabelRows = typeof rawLabels === "string"
      ? new Array(nNodes).fill(rawLabels)
      : Array.from(rawLabels);
    const labels = rawLabelRows.map((raw, index) => {
      let value = raw;
      if (value == null && data.nodeAttrs.name != null) value = data.nodeAttrs.name[index];
      if (value == null) {
        const identity = data.ids[index];
        if (typeof identity === "string") value = identity;
        else if (typeof identity === "number" && Number.isSafeInteger(identity)) value = String(identity);
        else if (typeof identity === "bigint" && identity >= BigInt(Number.MIN_SAFE_INTEGER)
          && identity <= BigInt(Number.MAX_SAFE_INTEGER)) value = identity.toString();
        else value = null;
      }
      if (value != null && typeof value !== "string") throw new TypeError("graph labels must be strings or null");
      return value;
    });
    if (labels.length !== nNodes) throw new RangeError("graph nodeLabel must match node count");
    const rawPriorities = resolveNodeOption(
      resolvedOpts.labelPriority ?? resolvedOpts.label_priority,
    ) ?? data.nodeAttrs.label_priority ?? new Float64Array(nNodes);
    const priorities = typeof rawPriorities === "number"
      ? new Float64Array(nNodes).fill(rawPriorities)
      : Float64Array.from(rawPriorities, Number);
    if (priorities.length !== nNodes) throw new RangeError("graph labelPriority must match node count");
    for (let index = 0; index < nNodes; index += 1) {
      if (labels[index] == null) priorities[index] = Number.NaN;
    }
    const budget = resolvedOpts.labelBudget ?? resolvedOpts.label_budget ?? 64;
    if (!Number.isSafeInteger(budget) || budget < 0 || budget > 4096) {
      throw new RangeError("graph labelBudget must be a safe integer from 0 through 4096");
    }
    const states = graphVisualStates(nodeFlags);
    // Node and edge labels share one Rust plan (#34); edge labels anchor at
    // the middle routed piece of a single-member render edge.
    const edgeRows = graphEdgeLabelRows(data, resolvedOpts, singleMember, renderEdgeIndex);
    const mid = edgeRows.anchors;
    const segMid = (a, b) => mid.map((segment) => (a[segment] + b[segment]) / 2);
    const radii = nodeDiameterPx != null && nodeDiameterPx.length === nNodes
      ? Array.from(nodeDiameterPx, (d) => d / 2)
      : new Array(nNodes).fill(Number(nodeDiameter) / 2);
    const allTexts = [...labels, ...edgeRows.texts];
    const plan = graphLabelPlan(
      [...new Array(nNodes).fill(0), ...new Array(mid.length).fill(1)],
      [...nodePositions.x, ...segMid(edgeSegments.x0, edgeSegments.x1)],
      [...nodePositions.y, ...segMid(edgeSegments.y0, edgeSegments.y1)],
      [...radii, ...new Array(mid.length).fill(0)],
      allTexts.map((text) => (text == null ? 0 : Array.from(text).length)),
      [...states, ...new Array(mid.length).fill(0)],
      [...priorities, ...edgeRows.priorities],
      budget,
      { minPriority: resolvedOpts.labelPriorityFloor ?? resolvedOpts.label_priority_floor ?? Number.NaN },
    );
    const texts = allTexts.map((text, i) => {
      const keep = plan.keep[i];
      if (text == null || keep === 0) return null;
      const chars = Array.from(text);
      return keep >= chars.length ? text : `${chars.slice(0, keep).join("")}\u2026`;
    });
    const encoder = new TextEncoder();
    if (texts.some((text) => text != null && encoder.encode(text).length > 4096)) {
      throw new RangeError("accepted graph labels are limited to 4096 UTF-8 bytes each");
    }
    // Rust label plan rides the traces as placement (threshold px per data
    // unit, -1 never; baseline offset px). Mirrors Python `_marks_graph`.
    const planRow = (i) => [
      Number.isFinite(plan.threshold[i]) && plan.keep[i] > 0 ? plan.threshold[i] : -1,
      plan.offsetX[i],
      plan.offsetY[i],
      plan.width[i],
      plan.fontPx[i],
    ];
    const stride = GRAPH_LABEL_PLAN_COMPONENTS;
    const nodePlan = new Float64Array(nNodes * stride);
    for (let i = 0; i < nNodes; i += 1) nodePlan.set(planRow(i), i * stride);
    traces[1].style_channels = { ...(traces[1].style_channels ?? {}), label_plan: { values: nodePlan, components: stride } };
    const painted = mid.map((_, k) => k).filter((k) => plan.keep[nNodes + k] > 0);
    if (painted.length) {
      const edgePlan = new Float64Array(nEdges * stride);
      for (let segment = 0; segment < nEdges; segment += 1) edgePlan[segment * stride] = -1;
      for (const k of painted) edgePlan.set(planRow(nNodes + k), mid[k] * stride);
      traces[0].style_channels = { ...traces[0].style_channels, label_plan: { values: edgePlan, components: stride } };
      graphMeta.edge_label_segments = painted.map((k) => mid[k]);
      graphMeta.edge_label_text = painted.map((k) => texts[nNodes + k]);
    }
    const accepted = labels.map((_, i) => plan.keep[i] > 0);
    graphMeta.node_labels = labels.map((_, index) => accepted[index] ? texts[index] : null);
    graphMeta.label_accepted = accepted;
    graphMeta.label_budget = Number(budget);
    graphMeta.visual_states = [...states];
    if (data.parentIndices != null) {
      const validity = data.parentValidity ?? new Uint8Array(nNodes).fill(1);
      const compounds = graphCompoundBounds(
        nodePositions.x, nodePositions.y, data.parentIndices, validity,
      );
      const noCompound = (1n << 64n) - 1n;
      graphMeta.parent_of = [...compounds.parentOf].map((value) => value === noCompound ? null : Number(value));
      graphMeta.compound_nodes = [...compounds.isCompound].map(Boolean);
      graphMeta.compound_bounds = graphMeta.compound_nodes.map((isCompound, index) =>
        isCompound
          ? [compounds.xmin[index], compounds.xmax[index], compounds.ymin[index], compounds.ymax[index]]
          : null,
      );
    }
  }
  if (data.edgeIds?.length) {
    // Source-indexed identity; Aggregate LOD may collapse multi-edges/self-loops.
    graphMeta.source_edge_ids = data.edgeIds.map(String);
    if (singleMember != null) {
      // Render-edge-indexed identity when every render edge is one source edge.
      graphMeta.edge_ids = singleMember.map((m) => graphMeta.source_edge_ids[m]);
    }
  }
  if (data.nodeProvenanceRows != null) {
    graphMeta.node_provenance_rows = [...data.nodeProvenanceRows].map(Number);
  }
  if (data.edgeProvenanceRows != null) {
    graphMeta.edge_provenance_rows = [...data.edgeProvenanceRows].map(Number);
  }
  if (sourceEdgeTooltips != null && singleMember == null) {
    graphMeta.edge_tooltip_rows = sourceEdgeTooltips;
  }
  if (sourceNodeTooltips != null && !nodesOneToOne) {
    graphMeta.node_tooltip_rows = sourceNodeTooltips;
  }

  // Rust semantic legend planes (#34); the figure merges them across every
  // semantic graph it holds (`graphSemanticLegendItems`).
  const semanticLegend = (resolvedOpts.semanticLegend ?? resolvedOpts.semantic_legend ?? true) && (nodeFields || edgeFields)
    ? { planes: [nodeFields, edgeFields].filter(Boolean), theme }
    : null;
  return {
    compoundMembers: compound?.members ?? null,
    semanticLegend,
    traces,
    graphMeta,
    nodePositions,
    edgeSegments,
    meta,
    edgeIdentity,
  };
}
