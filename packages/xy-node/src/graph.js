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
  graphEdgeRouteSegments,
  graphForceCreate,
  graphForceDestroy,
  graphForceTick,
  graphIsProgressiveForce,
  graphLayout,
  graphProjectionCreate,
  graphProjectionDestroy,
  graphProjectionRead,
  graphCompoundBounds,
  graphLabelAccept,
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
  const routed = graphEdgeRouteSegments(rx, ry, edgeS, edgeT, {
    directed: Boolean(data.directed),
    separation: opts.edgeSeparation ?? 0.08,
    loopRadius: opts.loopRadius ?? 0.35,
    arrowSize: opts.arrowSize ?? (data.directed ? 0.12 : 0),
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
  const data = resolveGraphData(nodes, resolvedEdges, {
    x: resolvedOpts.x,
    y: resolvedOpts.y,
    directed: resolvedOpts.directed,
    mapping: resolvedOpts.mapping,
  });
  const nodeColor = resolveEncodingValues(data, resolvedOpts.color, "node");
  const edgeColor = resolveEncodingValues(
    data,
    resolvedOpts.edgeColor ?? resolvedOpts.edge_color,
    "edge",
  );
  const sizeOpt = resolveEncodingValues(data, resolvedOpts.size, "node");
  const { nodePositions, edgeSegments, meta } = runLayout(data, resolvedOpts);
  const name = resolvedOpts.name ?? null;
  const nNodes = nodePositions.x.length;
  const nEdges = edgeSegments.x0.length;
  let styleSize = 8.0;
  let size_ch = resolveSizeChannel(styleSize, nNodes);
  if (Array.isArray(sizeOpt) || ArrayBuffer.isView(sizeOpt)) {
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
  } else if (sizeOpt != null) {
    styleSize = Number(sizeOpt);
    size_ch = resolveSizeChannel(styleSize, nNodes);
  }
  let [nodeTooltipRows, edgeTooltipRows] = projectionTooltipRows(data);
  const nodesOneToOne = nNodes === data.ids.length;
  // Identity is 1:1 against render-graph edges (before loop/arrow expansion).
  const renderEdgeCount = meta.render_sources?.length ?? meta.n_edges ?? 0;
  const edgesOneToOne = renderEdgeCount === data.sources.length;
  if (!(nodeTooltipRows != null && nodesOneToOne)) {
    nodeTooltipRows =
      resolvedOpts.nodeTooltipRows ?? resolvedOpts.tooltipRows ?? resolvedOpts.tooltip_rows ?? null;
  }
  if (!(edgeTooltipRows != null && edgesOneToOne)) {
    edgeTooltipRows =
      resolvedOpts.edgeTooltipRows ?? resolvedOpts.edge_tooltip_rows ?? null;
  }
  // Expand source-edge tooltips across routed segments (loops / arrow wings).
  const renderEdgeIndex = meta.render_edge_index;
  if (
    edgeTooltipRows != null &&
    edgesOneToOne &&
    Array.isArray(renderEdgeIndex) &&
    renderEdgeIndex.length === nEdges &&
    edgeTooltipRows.length === renderEdgeCount
  ) {
    edgeTooltipRows = renderEdgeIndex.map((i) => edgeTooltipRows[Number(i)]);
  }
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
      style: {
        color: typeof edgeColor === "string" ? edgeColor : "#888888",
        width: resolvedOpts.edgeWidth ?? resolvedOpts.edge_width ?? 1.2,
        ...(resolvedOpts.style ?? {}),
      },
      ...(edgeColor != null && typeof edgeColor !== "string"
        ? { color_ch: resolveColorChannel(edgeColor, nEdges, "#888888") }
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
        symbol: resolvedOpts.symbol ?? "circle",
        ...(resolvedOpts.style ?? {}),
      },
      ...(nodeColor != null && typeof nodeColor !== "string"
        ? { color_ch: resolveColorChannel(nodeColor, nNodes, DEFAULT_MARK_COLOR) }
        : {}),
      size_ch,
      ...(nodeTooltipRows != null ? { tooltip_rows: nodeTooltipRows } : {}),
    },
  ];

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
    const accepted = graphLabelAccept(priorities, budget, {
      minPriority: resolvedOpts.labelPriorityFloor ?? resolvedOpts.label_priority_floor ?? Number.NaN,
    }).accepted;
    const rawFlags = resolveNodeOption(
      resolvedOpts.visualStateFlags ?? resolvedOpts.visual_state_flags,
    ) ?? data.nodeAttrs.visual_state_flags ?? data.nodeAttrs.state_flags ?? new Uint32Array(nNodes);
    const flags = typeof rawFlags === "number"
      ? new Uint32Array(nNodes).fill(rawFlags)
      : rawFlags;
    const states = graphVisualStates(flags);
    const encoder = new TextEncoder();
    if (labels.some((label, index) => accepted[index] && encoder.encode(label).length > 4096)) {
      throw new RangeError("accepted graph labels are limited to 4096 UTF-8 bytes each");
    }
    graphMeta.node_labels = labels.map((label, index) => accepted[index] ? label : null);
    graphMeta.label_accepted = [...accepted].map(Boolean);
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
    if (edgesOneToOne) {
      graphMeta.edge_ids = graphMeta.source_edge_ids;
    }
  }
  if (data.nodeProvenanceRows != null) {
    graphMeta.node_provenance_rows = [...data.nodeProvenanceRows].map(Number);
  }
  if (data.edgeProvenanceRows != null) {
    graphMeta.edge_provenance_rows = [...data.edgeProvenanceRows].map(Number);
  }
  if (sourceEdgeTooltips != null && !edgesOneToOne) {
    graphMeta.edge_tooltip_rows = sourceEdgeTooltips;
  }
  if (sourceNodeTooltips != null && !nodesOneToOne) {
    graphMeta.node_tooltip_rows = sourceNodeTooltips;
  }

  return {
    traces,
    graphMeta,
    nodePositions,
    edgeSegments,
    meta,
  };
}
