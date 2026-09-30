/**
 * GraphForge result compositions for Node hosts
 * (spec/design/graphforge-compositions.md).
 *
 * GraphForge Core computes; XYG composes and renders. This module only frames
 * bytes the caller already holds — GraphForge Arrow IPC results and base-graph
 * entity tables, generation UUIDs, and explicit intent — into one `XYGQ`
 * request, calls Rust, and decodes the `XYGF` document by section name. Rust
 * owns result recognition, UUID joins, missing/extra policy, generation
 * checks, and the semantic planes; nothing here re-derives them.
 *
 * Diagnostics and errors carry only stable codes, schema ids, field names,
 * and counts — never result values, UUIDs, vectors, or coordinates.
 */

import { barChart, graphChart } from "./charts.js";
import { figure } from "./figure.js";
import {
  DOCUMENT_MAGIC,
  DTYPE,
  REQUEST_MAGIC,
  decodeContainer,
  encodeContainer,
} from "./graphforge-container.js";
import {
  pointer,
  xyGraphforgeCompose,
  xyGraphforgeCompositionVersion,
  xyGraphforgeDocumentCopy,
  xyGraphforgeDocumentDestroy,
  xyGraphforgeDocumentLen,
  xyGraphforgeLedgerTsv,
} from "./native.js";

export { decodeContainer, encodeContainer } from "./graphforge-container.js";

/** `XYGF` composition semantics version reported by the loaded Rust core. */
export const GRAPHFORGE_COMPOSITION_VERSION = xyGraphforgeCompositionVersion();

export const GRAPHFORGE_INTENTS = Object.freeze([
  "graph", "table", "bar-chart", "embedding-coordinates", "parallel-coordinates",
]);
export const GRAPHFORGE_MISSING_POLICIES = Object.freeze(["dim", "hide", "keep", "error"]);
export const GRAPHFORGE_EXTRA_POLICIES = Object.freeze(["error", "drop"]);

const NONE_U32 = 0xffffffff;
const NONE_U64 = 0xffffffffffffffffn;
const UUID_TEXT = /^([0-9a-f]{8})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{12})$/;

/** A stable, value-free composition failure (`code`, optional `layer`/`field`). */
export class GraphForgeCompositionError extends Error {
  constructor(code, message, { layer = null, field = null } = {}) {
    super(`${code}: ${message}`);
    this.name = "GraphForgeCompositionError";
    this.code = code;
    this.layer = layer;
    this.field = field;
  }
}

function hostError(code, message, context) {
  return new GraphForgeCompositionError(code, message, context);
}

/** Canonical hyphenated UUID text → 16 bytes. */
export function uuidToBytes(text, label = "uuid") {
  const match = typeof text === "string" ? UUID_TEXT.exec(text.toLowerCase()) : null;
  if (!match) throw hostError("GF_COMPOSE_REQUEST_INVALID", `${label} must be a canonical UUID string`);
  const hex = match.slice(1).join("");
  const out = new Uint8Array(16);
  for (let i = 0; i < 16; i += 1) out[i] = Number.parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

/** 16 bytes → canonical hyphenated UUID text. */
export function uuidFromBytes(bytes, offset = 0) {
  let hex = "";
  for (let i = 0; i < 16; i += 1) hex += bytes[offset + i].toString(16).padStart(2, "0");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function ipcBytes(value, label) {
  if (value instanceof Uint8Array) return value;
  if (value instanceof ArrayBuffer) return new Uint8Array(value);
  if (ArrayBuffer.isView(value)) return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
  throw hostError("GF_COMPOSE_REQUEST_INVALID", `${label} must be Arrow IPC bytes`);
}

function uuidPlane(values, label) {
  if (values instanceof Uint8Array) return values;
  if (!Array.isArray(values)) throw hostError("GF_COMPOSE_REQUEST_INVALID", `${label} must be UUID strings or packed bytes`);
  const out = new Uint8Array(values.length * 16);
  values.forEach((v, i) => out.set(uuidToBytes(v, label), i * 16));
  return out;
}

/**
 * Frame a composition request. Only representation is checked here; Rust
 * validates every value, policy, and identity.
 *
 * @param {object} input
 * @param {object} [input.base] base graph: `tables` (GraphForge Arrow IPC
 *   bytes: Cypher entity results or flat node/edge tables) and/or packed
 *   planes `nodeUuid`, `edgeUuid`, `edgeSourceUuid`, `edgeTargetUuid`; plus
 *   `generation` (UUID string) and `directed` (default true).
 * @param {Array<object>} input.layers result layers: `result` (Arrow IPC
 *   bytes), `intent` (required), `resultId`, `generation`, `missing`,
 *   `extra`, `rows`, `coordinates` (Arrow IPC bytes).
 * @returns {Uint8Array} `XYGQ` request bytes
 */
export function encodeGraphForgeRequest({ base = {}, layers } = {}) {
  if (!Array.isArray(layers) || layers.length === 0) {
    throw hostError("GF_COMPOSE_REQUEST_INVALID", "layers must be a non-empty array");
  }
  const sections = [];
  (base.tables ?? []).forEach((table, index) => {
    sections.push({ name: "base.table", index, dtype: DTYPE.bytes, values: ipcBytes(table, "base.tables[]") });
  });
  for (const [key, name] of [["nodeUuid", "base.node_uuid"], ["edgeUuid", "base.edge_uuid"],
    ["edgeSourceUuid", "base.edge_source_uuid"], ["edgeTargetUuid", "base.edge_target_uuid"]]) {
    if (base[key] != null) sections.push({ name, dtype: DTYPE.uuid, values: uuidPlane(base[key], `base.${key}`) });
  }
  if (base.generation != null) {
    sections.push({ name: "base.generation", dtype: DTYPE.uuid, values: uuidToBytes(base.generation, "base.generation") });
  }
  if (base.directed != null) sections.push({ name: "base.directed", dtype: DTYPE.u8, values: [base.directed ? 1 : 0] });
  layers.forEach((layer, index) => {
    if (layer == null || typeof layer !== "object") throw hostError("GF_COMPOSE_REQUEST_INVALID", "each layer must be an object");
    sections.push({ name: "layer.result", index, dtype: DTYPE.bytes, values: ipcBytes(layer.result, `layers[${index}].result`) });
    if (layer.intent != null) sections.push({ name: "layer.intent", index, dtype: DTYPE.utf8, values: String(layer.intent) });
    if (layer.resultId != null) sections.push({ name: "layer.result_id", index, dtype: DTYPE.utf8, values: String(layer.resultId) });
    if (layer.generation != null) {
      sections.push({ name: "layer.generation", index, dtype: DTYPE.uuid, values: uuidToBytes(layer.generation, `layers[${index}].generation`) });
    }
    if (layer.missing != null) sections.push({ name: "layer.missing", index, dtype: DTYPE.utf8, values: String(layer.missing) });
    if (layer.extra != null) sections.push({ name: "layer.extra", index, dtype: DTYPE.utf8, values: String(layer.extra) });
    if (layer.rows != null) {
      const rows = [...layer.rows].map((row) => {
        if (!(Number.isSafeInteger(row) && row >= 0) && typeof row !== "bigint") {
          throw hostError("GF_COMPOSE_REQUEST_INVALID", "rows must be non-negative integers");
        }
        return BigInt(row);
      });
      sections.push({ name: "layer.rows", index, dtype: DTYPE.u64, values: rows });
    }
    if (layer.coordinates != null) {
      sections.push({ name: "layer.coordinates", index, dtype: DTYPE.bytes, values: ipcBytes(layer.coordinates, `layers[${index}].coordinates`) });
    }
  });
  return encodeContainer(REQUEST_MAGIC, sections);
}

/** Run one framed request through Rust; returns the `XYGF` document bytes. */
export function composeGraphForgeRequest(request) {
  const bytes = ipcBytes(request, "request");
  const handle = new BigUint64Array(1);
  const status = xyGraphforgeCompose(pointer(bytes, "uint8_t *"), BigInt(bytes.byteLength), pointer(handle, "uint64_t *"));
  if (status < 0 || handle[0] === 0n) {
    throw hostError("GF_COMPOSE_NATIVE", `xyg_graphforge_compose failed with status ${status}`);
  }
  try {
    const length = new BigUint64Array(1);
    if (xyGraphforgeDocumentLen(handle[0], pointer(length, "uint64_t *")) !== 0) {
      throw hostError("GF_COMPOSE_NATIVE", "composition handle is stale");
    }
    const out = new Uint8Array(Number(length[0]));
    if (xyGraphforgeDocumentCopy(handle[0], pointer(out, "uint8_t *"), BigInt(out.byteLength)) !== 0) {
      throw hostError("GF_COMPOSE_NATIVE", "composition copy failed");
    }
    return out;
  } finally {
    xyGraphforgeDocumentDestroy(handle[0]);
  }
}

/**
 * Compose GraphForge results onto a base graph (see `encodeGraphForgeRequest`
 * for the input shape). Throws `GraphForgeCompositionError` with Rust's stable
 * code when the result cannot be composed.
 *
 * @returns {GraphForgeComposition}
 */
export function composeGraphForge(input) {
  return decodeGraphForgeDocument(composeGraphForgeRequest(encodeGraphForgeRequest(input)));
}

/** Decode `XYGF` bytes (from native or WASM); throws on an error document. */
export function decodeGraphForgeDocument(bytes) {
  const xygf = ipcBytes(bytes, "XYGF bytes");
  const sections = decodeContainer(xygf, DOCUMENT_MAGIC);
  const get = (name, index = 0) => sections.get(`${name}#${index}`)?.value;
  if (get("status")?.[0] !== 0) {
    const layer = get("error.layer")?.[0];
    throw new GraphForgeCompositionError(get("error.code") ?? "GF_COMPOSE_NATIVE", get("error.message") ?? "composition failed", {
      layer: layer == null || layer === NONE_U32 ? null : layer,
      field: get("error.field") ?? null,
    });
  }
  return new GraphForgeComposition(xygf, sections);
}

function uuidList(bytes) {
  if (bytes == null) return [];
  const out = new Array(bytes.length / 16);
  for (let i = 0; i < out.length; i += 1) out[i] = uuidFromBytes(bytes, i * 16);
  return out;
}

const hex2 = (v) => v.toString(16).padStart(2, "0");
const rgbaHex = (rgba, i) => {
  const [r, g, b, a] = rgba.subarray(i * 4, i * 4 + 4);
  return `#${hex2(r)}${hex2(g)}${hex2(b)}${a === 255 ? "" : hex2(a)}`;
};
const SHAPES = ["circle", "square", "diamond", "triangle", "cross", "hexagon"];

/** A decoded composition: identity-preserving planes plus provenance. */
export class GraphForgeComposition {
  constructor(bytes, sections) {
    /** The exact `XYGF` bytes (identical from native and WASM hosts). */
    this.bytes = bytes;
    this.sections = sections;
    const get = (name, index = 0) => sections.get(`${name}#${index}`)?.value;
    this.kind = get("kind");
    this.version = get("composition.version")?.[0];
    this.ledgerVersion = get("ledger.version")?.[0];
    this.directed = get("graph.directed")?.[0] === 1;
    const generation = get("base.generation");
    this.baseGeneration = generation ? uuidFromBytes(generation) : null;
    this.layers = [];
    for (let i = 0; sections.has(`layer.schema#${i}`); i += 1) {
      const counts = get("layer.counts", i) ?? [];
      const layerGeneration = get("layer.generation", i);
      this.layers.push({
        index: i,
        schema: get("layer.schema", i),
        schemaVersion: get("layer.schema_version", i)?.[0],
        verb: get("layer.verb", i),
        algorithm: get("layer.algorithm", i),
        disposition: get("layer.disposition", i),
        composition: get("layer.composition", i),
        intent: get("layer.intent", i),
        missingPolicy: get("layer.missing_policy", i),
        extraPolicy: get("layer.extra_policy", i),
        resultId: get("layer.result_id", i) ?? null,
        generation: layerGeneration ? uuidFromBytes(layerGeneration) : null,
        derivedType: get("layer.derived_type", i) ?? null,
        counts: {
          rows: Number(counts[0] ?? 0n), selected: Number(counts[1] ?? 0n),
          matched: Number(counts[2] ?? 0n), missing: Number(counts[3] ?? 0n), extra: Number(counts[4] ?? 0n),
        },
        valueNames: get("layer.value_names", i) ?? [],
        textNames: get("layer.text_names", i) ?? [],
        nodeTexts: get("layer.node_texts", i) ?? null,
        nodeValues: get("layer.node_values", i) ?? null,
        nodeRows: get("layer.node_rows", i) ?? null,
        edgeValues: get("layer.edge_values", i) ?? null,
        edgeRows: get("layer.edge_rows", i) ?? null,
      });
    }
    if (this.kind === "graph") {
      const nodeUuid = get("node.uuid");
      const edgeUuid = get("edge.uuid");
      this.nodes = {
        count: nodeUuid.length / 16,
        uuidBytes: nodeUuid,
        uuid: uuidList(nodeUuid),
        baseRow: get("node.base_row"),
        name: get("node.name"),
        type: get("node.type"),
        class: get("node.class"),
        epistemic: get("node.epistemic"),
        status: get("node.status"),
        metric: get("node.metric"),
        flags: get("node.flags"),
        label: get("node.label"),
        labelPriority: get("node.label_priority"),
      };
      const derived = get("edge.derived");
      this.edges = {
        count: edgeUuid.length / 16,
        uuidBytes: edgeUuid,
        uuid: uuidList(edgeUuid).map((id, i) => (derived[i] ? null : id)),
        baseRow: get("edge.base_row"),
        source: get("edge.source"),
        target: get("edge.target"),
        type: get("edge.type"),
        derived,
        layer: get("edge.layer"),
        class: get("edge.class"),
        epistemic: get("edge.epistemic"),
        status: get("edge.status"),
        metric: get("edge.metric"),
        flags: get("edge.flags"),
        order: get("edge.order"),
        path: get("edge.path"),
        label: get("edge.label"),
        labelPriority: get("edge.label_priority"),
      };
      const nodeOffsets = get("path.node_offsets") ?? [0n];
      const edgeOffsets = get("path.edge_offsets") ?? [0n];
      const pathNodes = get("path.nodes") ?? [];
      const pathEdges = get("path.edges") ?? [];
      const pathLayer = get("path.layer") ?? [];
      /** Ordered overlays (paths, walks, cycles, Euler trails) as composed indices. */
      this.paths = [...pathLayer].map((layer, i) => ({
        layer,
        row: Number(get("path.row")[i]),
        rank: get("path.rank")[i],
        cost: get("path.cost")[i],
        nodes: [...pathNodes.subarray(Number(nodeOffsets[i]), Number(nodeOffsets[i + 1]))].map(Number),
        edges: [...pathEdges.subarray(Number(edgeOffsets[i]), Number(edgeOffsets[i + 1]))].map(Number),
      }));
      this._nodeIndex = new Map(this.nodes.uuid.map((id, i) => [id, i]));
      this._edgeIndex = new Map();
      this.edges.uuid.forEach((id, i) => { if (id != null) this._edgeIndex.set(id, i); });
    }
    if (this.kind === "table") {
      const columns = get("table.columns");
      const cells = get("table.cells");
      const values = get("table.values");
      const valid = get("table.valid");
      const rows = get("table.rows");
      const k = columns.length;
      /** Table composition: canonical columns, text cells, numeric values. */
      this.table = {
        columns,
        kinds: get("table.kinds"),
        resultRows: [...rows].map(Number),
        rows: [...rows].map((_, r) => cells.slice(r * k, r * k + k).map((cell, c) => (valid[r * k + c] ? cell : null))),
        values: [...rows].map((_, r) => Array.from(values.subarray(r * k, r * k + k))),
      };
    } else if (this.kind === "bar-chart") {
      this.chart = {
        categoryName: get("chart.category_name"),
        valueName: get("chart.value_name"),
        categories: get("chart.category"),
        values: get("chart.value"),
        resultRows: [...get("chart.result_row")].map(Number),
      };
    } else if (this.kind === "parallel-coordinates") {
      const dimensions = get("vector.dimensions")[0];
      this.vectors = {
        dimensions,
        uuid: uuidList(get("vector.uuid")),
        name: get("vector.name"),
        resultRows: [...get("vector.result_row")].map(Number),
        values: get("vector.values"),
        domain: Array.from(get("vector.domain")),
      };
    } else if (this.kind === "scatter") {
      this.points = {
        source: get("point.source"),
        dimensions: get("vector.dimensions")[0],
        uuid: uuidList(get("point.uuid")),
        name: get("point.name"),
        resultRows: [...get("point.result_row")].map(Number),
        x: get("point.x"),
        y: get("point.y"),
      };
    }
    const legendSide = get("legend.side") ?? new Uint8Array(0);
    const light = get("legend.rgba_light");
    const dark = get("legend.rgba_dark");
    this.legend = {
      title: get("legend.title") ?? null,
      rows: [...legendSide].map((side, i) => ({
        side: side === 0 ? "node" : "edge",
        field: get("legend.field")[i],
        value: get("legend.value")[i],
        text: get("legend.text")[i],
        shape: SHAPES[get("legend.shape")[i] % SHAPES.length],
        colorLight: rgbaHex(light, i),
        colorDark: rgbaHex(dark, i),
      })),
    };
    const codes = get("decision.code") ?? [];
    const decisionLayers = get("decision.layer") ?? [];
    const decisionCounts = get("decision.count") ?? [];
    this.decisions = codes.map((code, i) => ({
      code,
      layer: decisionLayers[i] === NONE_U32 ? null : decisionLayers[i],
      count: Number(decisionCounts[i]),
    }));
  }

  /** Dense node index for a UUID (or -1). */
  nodeIndex(uuid) { return this._nodeIndex?.get(String(uuid).toLowerCase()) ?? -1; }

  /** Dense edge index for a persisted relationship UUID (or -1). */
  edgeIndex(uuid) { return this._edgeIndex?.get(String(uuid).toLowerCase()) ?? -1; }

  /**
   * Identity of one composed element for selection routing: its UUID (null
   * for derived edges) and, per layer, the caller's result id and result row.
   */
  identify(kind, index) {
    const side = kind === "node" ? this.nodes : this.edges;
    if (side == null || !Number.isInteger(index) || index < 0 || index >= side.count) {
      throw new RangeError(`no composed ${kind} ${index}`);
    }
    const rowsKey = kind === "node" ? "nodeRows" : "edgeRows";
    const layers = [];
    for (const layer of this.layers) {
      const row = layer[rowsKey]?.[index];
      if (row != null && row !== NONE_U64) layers.push({ layer: layer.index, resultId: layer.resultId, row: Number(row) });
    }
    const out = { kind, index, uuid: side.uuid[index], layers };
    if (kind === "edge") {
      out.derived = side.derived[index] === 1;
      out.type = side.type[index] || null;
      const order = side.order?.[index];
      if (order != null && order >= 0n) {
        out.order = Number(order);
        out.path = Number(side.path[index]);
      }
      out.source = this.nodes.uuid[Number(side.source[index])];
      out.target = this.nodes.uuid[Number(side.target[index])];
    }
    return out;
  }

  /** UUIDs (nodes and/or relationships) → composed indices, for highlight. */
  select(uuids) {
    const nodes = [];
    const edges = [];
    for (const uuid of uuids) {
      const n = this.nodeIndex(uuid);
      if (n >= 0) nodes.push(n);
      const e = this.edgeIndex(uuid);
      if (e >= 0) edges.push(e);
    }
    return { nodes, edges };
  }

  /** Value-free summary for host logs: schema ids, counts, and codes only. */
  diagnostics() {
    return {
      kind: this.kind,
      compositionVersion: this.version,
      rows: this.table?.rows.length ?? this.chart?.categories.length ?? this.vectors?.uuid.length ?? this.points?.uuid.length,
      ledgerVersion: this.ledgerVersion,
      nodes: this.nodes?.count ?? 0,
      edges: this.edges?.count ?? 0,
      layers: this.layers.map((l) => ({
        schema: l.schema, schemaVersion: l.schemaVersion, disposition: l.disposition,
        composition: l.composition, intent: l.intent, counts: { ...l.counts },
      })),
      decisions: this.decisions.map((d) => ({ ...d })),
    };
  }
}

/** GraphData (graph.js) for a graph composition; identity is UUID text. */
export function graphforgeGraphData(composition) {
  if (composition?.kind !== "graph") throw new TypeError("graphforgeGraphData needs a graph composition");
  const { nodes, edges } = composition;
  const nodeAttrs = { name: [...nodes.name].map((v) => v || null), type: [...nodes.type].map((v) => v || null) };
  const edgeAttrs = { type: [...edges.type].map((v) => v || null) };
  for (const layer of composition.layers) {
    const prefix = layer.algorithm || layer.verb;
    if (layer.nodeTexts != null) {
      const t = layer.textNames.length;
      layer.textNames.forEach((name, j) => {
        nodeAttrs[`${prefix}.${name}`] = Array.from({ length: nodes.count }, (_, i) => layer.nodeTexts[i * t + j] || null);
      });
    }
    for (const [values, attrs, count] of [[layer.nodeValues, nodeAttrs, nodes.count], [layer.edgeValues, edgeAttrs, edges.count]]) {
      if (values == null) continue;
      const k = layer.valueNames.length;
      layer.valueNames.forEach((name, j) => {
        attrs[`${prefix}.${name}`] = Float64Array.from({ length: count }, (_, i) => values[i * k + j]);
      });
    }
  }
  // Derived edges have no persisted UUID: identify them by layer and result row.
  const edgeIds = edges.uuid.map((id, i) => {
    if (id != null) return id;
    // One result row may yield several steps (paths, walks, cycles): the
    // step index keeps each derived edge's id unique.
    const layer = composition.layers[edges.layer[i]];
    const step = edges.order != null && edges.order[i] >= 0n ? `:${edges.order[i]}` : "";
    return `derived:${edges.layer[i]}:${Number(layer.edgeRows[i])}${step}`;
  });
  if (edges.order != null) {
    edgeAttrs.step = Float64Array.from(edges.order, (v) => (v < 0n ? Number.NaN : Number(v)));
  }
  return {
    ids: nodes.uuid,
    edgeIds,
    sources: edges.source,
    targets: edges.target,
    x: null,
    y: null,
    nodeAttrs,
    edgeAttrs,
    nodeUuidBytes: nodes.uuidBytes,
    edgeUuidBytes: edges.uuidBytes,
    nodeProvenanceRows: nodes.baseRow,
    edgeProvenanceRows: edges.baseRow,
    directed: composition.directed,
    get nNodes() { return this.ids.length; },
    get nEdges() { return this.sources.length; },
  };
}

/** Graph mark options that paint a composition's Rust planes as given. */
export function graphforgeGraphOptions(composition, { theme = "light" } = {}) {
  const { nodes, edges } = composition;
  return {
    theme,
    nodeClass: nodes.class,
    nodeEpistemic: nodes.epistemic,
    nodeStatus: nodes.status,
    nodeMetric: nodes.metric,
    visualStateFlags: nodes.flags,
    edgeClass: edges.class,
    edgeEpistemic: edges.epistemic,
    edgeStatus: edges.status,
    edgeMetric: edges.metric,
    edgeVisualStateFlags: edges.flags,
    nodeLabel: [...nodes.label].map((v) => v || null),
    labelPriority: nodes.labelPriority,
    ...(edges.label != null && edges.label.some((v) => v)
      ? { edgeLabel: [...edges.label].map((v) => v || null), edgeLabelPriority: edges.labelPriority }
      : {}),
    semanticLegend: false,
  };
}

/**
 * Legend items (chart legend `items`) for a composition's Rust legend rows.
 * Marker swatches, like the semantic legend, so browser and static export
 * paint the same rows.
 */
export function graphforgeLegendItems(composition, { theme = "light" } = {}) {
  return composition.legend.rows.map((row) => ({
    kind: "scatter",
    name: row.text,
    style: {
      color: theme === "dark" ? row.colorDark : row.colorLight,
      symbol: row.side === "node" && row.field === 0 ? row.shape : "circle",
    },
  }));
}

/**
 * A graph chart of a composition: the base graph laid out by Rust (default
 * `layout: "force"`), painted from the composition's semantic planes, with
 * the composition's legend. Extra options pass through to `graphChart`.
 */
export function graphforgeChart(composition, opts = {}) {
  switch (composition?.kind) {
    case "graph": return graphforgeGraphChart(composition, opts);
    case "bar-chart": return graphforgeBarChart(composition, opts);
    case "parallel-coordinates": return graphforgeParallelChart(composition, opts);
    case "scatter": return graphforgeScatterChart(composition, opts);
    case "table": throw new TypeError("table compositions render as tables: use graphforgeTableHtml(composition)");
    default: throw new TypeError(`unknown composition kind ${JSON.stringify(composition?.kind)}`);
  }
}

function axisTitles(fig, x, y) {
  // Figure-level axis titles (chrome `x_label` / `y_label`), which every
  // export route admits, rather than authored axis options.
  fig.x_label = x;
  fig.y_label = y;
  return fig;
}

/** Category results as bars in result order (never re-sorted). */
function graphforgeBarChart(composition, opts) {
  const { categories, values, categoryName, valueName } = composition.chart;
  const { width, height, title } = opts;
  const fig = barChart([...categories], Float64Array.from(values), { width, height, title });
  // A real category axis (as Python bar charts have): the browser labels each
  // bar with its category; static export fails closed like Python's
  // (XYG_SCENE_UNSUPPORTED_PUBLIC_AXIS) instead of printing bare positions.
  fig._axis_categories = { ...(fig._axis_categories ?? {}), x: [...categories] };
  return axisTitles(fig, categoryName, valueName);
}

/**
 * Parallel coordinates: every node's full vector over the dimension index,
 * one polyline per node (segments carry the node identity for hover/pick).
 */
function graphforgeParallelChart(composition, opts) {
  const { dimensions, values, uuid, name } = composition.vectors;
  const n = uuid.length;
  const pieces = n * Math.max(dimensions - 1, 0);
  const x0 = new Float64Array(pieces); const y0 = new Float64Array(pieces);
  const x1 = new Float64Array(pieces); const y1 = new Float64Array(pieces);
  const rows = [];
  let at = 0;
  for (let r = 0; r < n; r += 1) {
    for (let d = 0; d + 1 < dimensions; d += 1, at += 1) {
      x0[at] = d; x1[at] = d + 1;
      y0[at] = values[r * dimensions + d]; y1[at] = values[r * dimensions + d + 1];
      rows.push({ id: uuid[r], ...(name[r] ? { name: name[r] } : {}), dimension: d });
    }
  }
  const { width, height, title } = opts;
  const fig = figure({ width, height, title });
  fig.segments(x0, y0, x1, y1, { name: "embedding", ...(pieces <= 100_000 ? { tooltip_rows: rows } : {}) });
  // Rust owns the plot domain (dimension span, padded finite value range).
  const [dx0, dx1, dy0, dy1] = composition.vectors.domain;
  fig.setAxis("x", { domain: [dx0, dx1] });
  fig.setAxis("y", { domain: [dy0, dy1] });
  return axisTitles(fig, "dimension", "value");
}

/** Embedded nodes at caller (or two-dimensional embedding) coordinates. */
function graphforgeScatterChart(composition, opts) {
  const { x, y, uuid, name, source } = composition.points;
  const { width, height, title } = opts;
  const rows = uuid.map((id, i) => ({ id, ...(name[i] ? { name: name[i] } : {}) }));
  const fig = figure({ width, height, title });
  // The composed scatter path carries per-point tooltip rows (as the graph
  // mark's nodes do); it takes the figure's next series color explicitly.
  fig.scatter(Float64Array.from(x), Float64Array.from(y), {
    name: "embedding",
    style: { color: fig.nextSeriesColor() },
    tooltip_rows: rows,
    _composed: true,
  });
  return source === "embedding" ? axisTitles(fig, "dimension 0", "dimension 1") : fig;
}

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const escapeHtml = (text) => String(text).replace(/[&<>"']/g, (c) => ESCAPES[c]);

/** A table composition as an escaped HTML `<table>` (cells are text only). */
export function graphforgeTableHtml(composition) {
  if (composition?.kind !== "table") throw new TypeError("graphforgeTableHtml needs a table composition");
  const { columns, rows } = composition.table;
  const head = columns.map((c) => `<th scope="col">${escapeHtml(c)}</th>`).join("");
  const body = rows
    .map((row) => `<tr>${row.map((cell) => `<td>${cell == null ? "" : escapeHtml(cell)}</td>`).join("")}</tr>`)
    .join("");
  const caption = composition.layers[0]?.algorithm ? `<caption>${escapeHtml(composition.layers[0].algorithm)}</caption>` : "";
  return `<table class="xyg-graphforge-table">${caption}<thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function graphforgeGraphChart(composition, opts) {
  const { theme = "light", legend, ...rest } = opts;
  const items = graphforgeLegendItems(composition, { theme });
  const chartLegend = legend === false
    ? undefined
    : { title: composition.legend.title, ...(legend ?? {}), items: legend?.items ?? items };
  return graphChart(graphforgeGraphData(composition), undefined, {
    ...graphforgeGraphOptions(composition, { theme }),
    ...rest,
    ...(chartLegend && items.length ? { legend: chartLegend } : {}),
  });
}

/** The Rust coverage ledger rows (for coverage agreement checks). */
export function graphforgeLedger() {
  const size = Number(xyGraphforgeLedgerTsv(null, 0n));
  const out = new Uint8Array(size);
  xyGraphforgeLedgerTsv(pointer(out, "uint8_t *"), BigInt(size));
  const [header, ...lines] = new TextDecoder().decode(out).trimEnd().split("\n");
  const keys = header.split("\t");
  return lines.map((line) => {
    const cells = Object.fromEntries(line.split("\t").map((v, i) => [keys[i], v]));
    return {
      schema: cells.schema,
      version: Number(cells.version),
      disposition: cells.disposition,
      composition: cells.composition,
      intents: cells.intents ? cells.intents.split(",") : [],
      fields: cells.fields ? cells.fields.split(",").map((f) => { const [name, kind] = f.split(":"); return { name, kind }; }) : [],
      algorithms: cells.algorithms ? cells.algorithms.split(",") : [],
    };
  });
}

