// GraphForge result compositions over the real GraphForge 0.5.2 fixture
// corpus (tests/fixtures/graphforge/results). Join values are checked against
// composition_expectations.json, decoded independently with pyarrow.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  GRAPHFORGE_COMPOSITION_VERSION,
  GraphForgeCompositionError,
  composeGraphForge,
  composeGraphForgeRequest,
  decodeGraphForgeDocument,
  encodeGraphForgeRequest,
  graphforgeChart,
  graphforgeGraphData,
  graphforgeLedger,
} from "../src/graphforge.js";
import { decodeContainer, encodeContainer, DTYPE } from "../src/graphforge-container.js";
import { graphChart } from "../src/charts.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const RESULTS = path.join(ROOT, "tests/fixtures/graphforge/results");
const EXPECT = JSON.parse(fs.readFileSync(path.join(ROOT, "tests/fixtures/graphforge/composition_expectations.json"), "utf8"));
const MANIFEST = JSON.parse(fs.readFileSync(path.join(RESULTS, "manifest.json"), "utf8"));

const arrow = (name) => fs.readFileSync(path.join(RESULTS, `${name}.arrow`));
const baseOf = (name) => MANIFEST.fixtures[name].base;
const generationOf = (base) => MANIFEST.bases[base].generation;

function base(name) {
  const spec = MANIFEST.bases[name];
  return { tables: [arrow(spec.nodes), arrow(spec.edges)], generation: spec.generation };
}

function compose(...names) {
  const b = baseOf(names[0]);
  return composeGraphForge({
    base: base(b),
    layers: names.map((name) => ({ result: arrow(name), intent: "graph", generation: generationOf(b) })),
  });
}

function assertJoins(composition, name, layerIndex = 0) {
  const expected = EXPECT.layers[name];
  const layer = composition.layers[layerIndex];
  const side = expected.identity === "node_uuid" ? "node" : "edge";
  const values = side === "node" ? layer.nodeValues : layer.edgeValues;
  const rows = side === "node" ? layer.nodeRows : layer.edgeRows;
  const k = layer.valueNames.length;
  assert.deepEqual(layer.valueNames.slice(0, expected.values.length), expected.values);
  for (const [uuid, want] of Object.entries(expected.rows)) {
    const index = side === "node" ? composition.nodeIndex(uuid) : composition.edgeIndex(uuid);
    assert.ok(index >= 0, `${name}: ${side} is in the composition`);
    assert.equal(Number(rows[index]), want.row);
    expected.values.forEach((field, j) => assert.equal(values[index * k + j], Number(want[field]), `${name}.${field}`));
  }
}

test("every node and edge layer joins by UUID, matching an independent decoder", () => {
  for (const name of Object.keys(EXPECT.layers)) {
    const composition = compose(name);
    assertJoins(composition, name);
    assert.equal(composition.version, GRAPHFORGE_COMPOSITION_VERSION);
    assert.equal(composition.baseGeneration, generationOf(baseOf(name)));
    const counts = EXPECT.bases[baseOf(name)];
    assert.equal(composition.nodes.count, counts.nodes);
    assert.equal(composition.edges.count, counts.edges);
    assert.deepEqual(composition.nodes.uuid, counts.nodeUuids, "base node order is canonical");
  }
});

test("scores become the node metric plane; communities class codes", () => {
  const c = compose("pagerank", "louvain");
  const expected = EXPECT.layers.pagerank.rows;
  for (const [uuid, want] of Object.entries(expected)) {
    assert.equal(c.nodes.metric[c.nodeIndex(uuid)], want.score);
  }
  assert.ok([...c.nodes.class].every((code) => code >= 1 && code <= 7));
  assert.ok(c.legend.rows.some((row) => row.side === "node" && row.text.startsWith("community ")));
});

test("edge overlays mark members, dim context, and keep persisted identity", () => {
  const c = compose("minimum_spanning_tree");
  const members = [...c.edges.class].filter((code) => code === 1).length;
  assert.equal(members, Object.keys(EXPECT.layers.minimum_spanning_tree.rows).length);
  c.edges.class.forEach((code, i) => assert.equal(code === 1, (c.edges.flags[i] & 64) === 0));
  assert.ok(c.edges.uuid.every((id) => typeof id === "string"), "persisted edges keep UUIDs");
  assert.ok(c.decisions.some((d) => d.code === "GF_COMPOSE_MISSING_DIMMED" && d.layer === 0));
  const flow = compose("max_flow_edges");
  for (const uuid of Object.keys(EXPECT.layers.max_flow_edges.rows)) {
    assert.equal(flow.edges.status[flow.edgeIndex(uuid)], 1, "flows draw arrowheads");
  }
});

test("identity round-trips for selection: UUID → index → UUID + result rows", () => {
  const c = composeGraphForge({
    base: base("cyclic"),
    layers: [
      { result: arrow("pagerank"), intent: "graph", generation: generationOf("cyclic"), resultId: "result-a" },
      { result: arrow("minimum_spanning_tree"), intent: "graph", generation: generationOf("cyclic"), resultId: "result-b" },
    ],
  });
  for (const [uuid, want] of Object.entries(EXPECT.layers.pagerank.rows)) {
    const { nodes } = c.select([uuid]);
    assert.equal(nodes.length, 1);
    const identity = c.identify("node", nodes[0]);
    assert.equal(identity.uuid, uuid);
    assert.deepEqual(identity.layers, [{ layer: 0, resultId: "result-a", row: want.row }]);
  }
  const [edgeUuid, edgeRow] = Object.entries(EXPECT.layers.minimum_spanning_tree.rows)[0];
  const edge = c.identify("edge", c.select([edgeUuid]).edges[0]);
  assert.equal(edge.uuid, edgeUuid);
  assert.equal(edge.derived, false);
  assert.deepEqual(edge.layers, [{ layer: 1, resultId: "result-b", row: edgeRow.row }]);
  assert.ok(typeof edge.source === "string" && typeof edge.target === "string");
});

test("failures carry stable codes and no identities or values", () => {
  const gen = generationOf("cyclic");
  const cases = [
    [{ base: base("dag"), layers: [{ result: arrow("pagerank"), intent: "graph", generation: generationOf("dag") }] }, "GF_COMPOSE_EXTRA_IDS", 0],
    [{ base: base("cyclic"), layers: [{ result: arrow("pagerank"), intent: "graph", generation: "0190a000-0000-7000-8000-0000000000ff" }] }, "GF_COMPOSE_GENERATION_STALE", 0],
    [{ base: base("cyclic"), layers: [{ result: arrow("pagerank"), intent: "graph" }] }, "GF_COMPOSE_GENERATION_MISSING", 0],
    [{ base: base("cyclic"), layers: [{ result: arrow("pagerank"), intent: "graph", generation: gen }, { result: arrow("betweenness"), intent: "graph", generation: gen }] }, "GF_COMPOSE_CHANNEL_CONFLICT", 1],
    [{ base: base("cyclic"), layers: [{ result: arrow("pagerank"), intent: "table", generation: gen }] }, "GF_COMPOSE_INTENT_UNSUPPORTED", 0],
    [{ base: base("cyclic"), layers: [{ result: arrow("pagerank"), generation: gen }] }, "GF_COMPOSE_INTENT_REQUIRED", 0],
    [{ layers: [{ result: arrow("pagerank"), intent: "graph" }] }, "GF_COMPOSE_BASE_REQUIRED", null],
    [{ base: base("cyclic"), layers: [{ result: arrow("pagerank").subarray(0, 200), intent: "graph", generation: gen }] }, "GF_ARROW_MALFORMED", 0],
    [{ base: base("cyclic"), layers: [{ result: arrow("cypher-nodes"), intent: "graph", generation: gen }] }, "GF_RESULT_NOT_ALGORITHM", 0],
  ];
  const uuids = EXPECT.bases.cyclic.nodeUuids.concat(EXPECT.bases.dag.nodeUuids);
  for (const [input, code, layer] of cases) {
    assert.throws(() => composeGraphForge(input), (error) => {
      assert.ok(error instanceof GraphForgeCompositionError);
      assert.equal(error.code, code);
      assert.equal(error.layer, layer);
      for (const uuid of uuids) assert.ok(!error.message.includes(uuid));
      assert.ok(!error.message.includes("0190a000"));
      return true;
    });
  }
  assert.throws(() => encodeGraphForgeRequest({ base: { generation: "nope" }, layers: [{ result: arrow("pagerank") }] }),
    (error) => error.code === "GF_COMPOSE_REQUEST_INVALID");
});

test("missing and extra identity policies are explicit and recorded", () => {
  const gen = generationOf("cyclic");
  const both = { tables: [...base("cyclic").tables, ...base("flow").tables], generation: gen };
  const dim = composeGraphForge({ base: both, layers: [{ result: arrow("pagerank"), intent: "graph", generation: gen }] });
  assert.equal([...dim.nodes.flags].filter((f) => f & 64).length, 4);
  const hide = composeGraphForge({ base: both, layers: [{ result: arrow("pagerank"), intent: "graph", generation: gen, missing: "hide" }] });
  assert.equal(hide.nodes.count, 4);
  assert.ok(hide.decisions.some((d) => d.code === "GF_COMPOSE_EDGES_HIDDEN_WITH_NODES"));
  const dropped = composeGraphForge({ base: base("dag"), layers: [{ result: arrow("pagerank"), intent: "graph", generation: generationOf("dag"), extra: "drop" }] });
  assert.deepEqual(dropped.decisions.find((d) => d.code === "GF_COMPOSE_EXTRA_DROPPED"), { code: "GF_COMPOSE_EXTRA_DROPPED", layer: 0, count: 4 });
});

test("diagnostics are value-free", () => {
  const c = compose("pagerank", "louvain");
  const text = JSON.stringify(c.diagnostics());
  for (const uuid of EXPECT.bases.cyclic.nodeUuids) assert.ok(!text.includes(uuid));
  for (const want of Object.values(EXPECT.layers.pagerank.rows)) assert.ok(!text.includes(String(want.score)));
  assert.match(text, /"schema":"node-score"/);
});

test("request framing is host-neutral bytes; the document decodes identically", () => {
  const input = { base: base("cyclic"), layers: [{ result: arrow("louvain"), intent: "graph", generation: generationOf("cyclic") }] };
  const request = encodeGraphForgeRequest(input);
  assert.equal(new TextDecoder().decode(request.subarray(0, 4)), "XYGQ");
  const document = composeGraphForgeRequest(request);
  assert.deepEqual(composeGraphForgeRequest(encodeGraphForgeRequest(input)), document, "deterministic bytes");
  const decoded = decodeGraphForgeDocument(document);
  assert.deepEqual([...decoded.nodes.class], [...composeGraphForge(input).nodes.class]);
});

test("container numbers are little-endian bytes regardless of host order", () => {
  const bytes = encodeContainer("XYGQ", [
    { name: "a.u32", dtype: DTYPE.u32, values: [0x01020304] },
    { name: "a.u64", dtype: DTYPE.u64, values: [0x0102030405060708n] },
    { name: "a.f64", dtype: DTYPE.f64, values: [1.5] },
  ]);
  const sections = decodeContainer(bytes, "XYGQ");
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const at = (name) => Number(view.getBigUint64(32 + [...sections.keys()].indexOf(`${name}#0`) * 40 + 16, true));
  assert.equal(view.getUint32(at("a.u32"), true), 0x01020304);
  assert.equal(view.getBigUint64(at("a.u64"), true), 0x0102030405060708n);
  assert.equal(view.getFloat64(at("a.f64"), true), 1.5);
  assert.equal(sections.get("a.u32#0").value[0], 0x01020304);
});

test("container codec round-trips and rejects corruption", () => {
  const bytes = encodeContainer("XYGF", [
    { name: "a.u8", dtype: DTYPE.u8, values: [1, 2] },
    { name: "a.u64", index: 3, dtype: DTYPE.u64, values: [7n] },
    { name: "a.f64", dtype: DTYPE.f64, values: [Number.NaN, 1.5] },
    { name: "a.texts", dtype: DTYPE.texts, values: ["", "<b>"] },
    { name: "a.utf8", dtype: DTYPE.utf8, values: "héllo" },
  ]);
  const sections = decodeContainer(bytes, "XYGF");
  assert.deepEqual([...sections.get("a.u8#0").value], [1, 2]);
  assert.deepEqual([...sections.get("a.u64#3").value], [7n]);
  assert.deepEqual(sections.get("a.texts#0").value, ["", "<b>"]);
  assert.equal(sections.get("a.utf8#0").value, "héllo");
  assert.throws(() => decodeContainer(bytes, "XYGQ"));
  assert.throws(() => decodeContainer(bytes.subarray(0, bytes.length - 8), "XYGF"));
});

test("graphforgeChart paints the Rust planes with the Rust legend and UUID tooltips", () => {
  const c = compose("pagerank", "louvain", "minimum_spanning_tree");
  const fig = graphforgeChart(c, { width: 640, height: 420, title: "GraphForge" });
  const meta = fig._graphMeta[0];
  assert.deepEqual(meta.style_contract.nodes, "resolved");
  assert.deepEqual(meta.style_contract.edges, "resolved");
  assert.equal(fig.legend.title, "GraphForge result");
  assert.deepEqual(fig.legend.items.map((i) => i.name), c.legend.rows.map((r) => r.text));
  const nodes = fig.traces[meta.node_trace];
  const row = nodes.tooltip_rows[0];
  assert.equal(row.id, c.nodes.uuid[0]);
  assert.equal(row["pagerank.score"], c.nodes.metric[0]);
  // Dimmed context edges resolve to the disabled opacity.
  const edges = fig.traces[meta.edge_trace];
  const opacity = edges.style_channels.opacity.values;
  assert.ok([...opacity].some((o) => Math.abs(o - 0.28) < 1e-6));
  assert.ok([...opacity].some((o) => o === 1));
  assert.ok(fig.toHtml().length > 0);
  const png = fig.toPng();
  assert.equal(png[1], 0x50, "PNG export");
  const dark = graphforgeChart(c, { theme: "dark" });
  assert.equal(dark.legend.items[0].style.color, c.legend.rows[0].colorDark);
  assert.equal(graphforgeGraphData(c).edgeIds[0], c.edges.uuid[0]);
});

test("graph mark accepts edge visual-state flags only with edge semantic fields", () => {
  const nodes = ["a", "b", "c"];
  const edges = [["a", "b"], ["b", "c"]];
  const fig = graphChart(nodes, edges, {
    layout: "circle", edgeClass: [1, 1], edgeVisualStateFlags: [0, 64],
  });
  const meta = fig._graphMeta[0];
  const opacity = fig.traces[meta.edge_trace].style_channels.opacity.values;
  assert.deepEqual([...opacity].map((o) => Math.round(o * 100) / 100), [1, 0.28]);
  assert.throws(() => graphChart(nodes, edges, { layout: "circle", edgeVisualStateFlags: [0, 64] }), /edge semantic fields/);
  assert.throws(() => graphChart(nodes, edges, { layout: "circle", edgeClass: [1, 1], edgeVisualStateFlags: [0] }), /edge count/);
  // A column name resolves like every other per-edge option.
  const u = (i) => `00000000-0000-4000-8000-00000000000${i}`;
  const named = graphChart(
    { node_uuid: [u(1), u(2), u(3)] },
    { edge_uuid: [u(4), u(5)], src_uuid: [u(1), u(2)], dst_uuid: [u(2), u(3)], flags: [64, 0] },
    { layout: "circle", edgeClass: [1, 1], edgeVisualStateFlags: "flags" },
  );
  const namedOpacity = named.traces[named._graphMeta[0].edge_trace].style_channels.opacity.values;
  assert.deepEqual([...namedOpacity].map((o) => Math.round(o * 100) / 100), [0.28, 1]);
  assert.throws(() => graphChart(nodes, edges, { layout: "circle", edgeClass: [1, 1], edgeVisualStateFlags: "nope" }), /unknown edge column/);
});

test("the Rust ledger covers every GraphForge 0.5.2 contract", () => {
  const ledger = graphforgeLedger();
  const registered = new Map(ledger.flatMap((row) => row.algorithms.map((a) => [a, row])));
  for (const contract of MANIFEST.contracts) {
    assert.ok(registered.has(contract.algorithm), contract.algorithm);
    assert.equal(registered.get(contract.algorithm).version, contract.resultSchemaVersion);
  }
  const embedding = ledger.find((row) => row.schema === "embedding");
  assert.deepEqual(embedding.intents, ["embedding-coordinates", "parallel-coordinates"]);
  assert.equal(ledger.find((row) => row.schema === "search").composition, "node-search");
});

test("derived pairs are identified by layer and result row, never a persisted UUID", () => {
  const c = compose("node_similarity");
  const derived = [...c.edges.derived].map((d, i) => (d ? i : -1)).filter((i) => i >= 0);
  assert.ok(derived.length > 0);
  const data = graphforgeGraphData(c);
  for (const i of derived) {
    assert.equal(c.edges.uuid[i], null);
    assert.equal(c.edges.epistemic[i], 1, "derived edges dash and halo");
    const identity = c.identify("edge", i);
    assert.equal(identity.derived, true);
    assert.equal(identity.type, "SIMILAR");
    assert.equal(identity.layers.length, 1);
    assert.equal(data.edgeIds[i], `derived:0:${identity.layers[0].row}`);
  }
  assert.ok(c.legend.rows.some((row) => row.side === "edge" && row.field === 1 && row.text === "similar (derived)"));
});

test("ordered overlays expose paths, step order, and position labels", () => {
  const c = compose("dijkstra");
  assert.equal(c.paths.length, 1);
  const [path] = c.paths;
  assert.equal(path.edges.length + 1, path.nodes.length);
  path.edges.forEach((edge, k) => {
    const identity = c.identify("edge", edge);
    assert.equal(identity.order, k);
    assert.equal(identity.path, 0);
    assert.equal(identity.source, c.nodes.uuid[path.nodes[k]]);
    assert.equal(identity.target, c.nodes.uuid[path.nodes[k + 1]]);
  });
  path.nodes.forEach((node, k) => assert.equal(c.nodes.label[node], String(k)));
  const fig = graphforgeChart(c);
  const edges = fig.traces[fig._graphMeta[0].edge_trace];
  assert.ok(edges.tooltip_rows.some((row) => row.step === 0));
  const ids = graphforgeGraphData(c).edgeIds.filter((id) => id.startsWith("derived:"));
  assert.equal(new Set(ids).size, ids.length, "every derived step has its own id");

  const euler = compose("euler_circuit");
  assert.equal(euler.paths.length, 1);
  assert.ok([...euler.edges.derived].every((d) => d === 0), "Euler trails name persisted edges");
  const trail = graphforgeChart(euler, { width: 480, height: 360 });
  assert.ok(trail._graphMeta[0].edge_label_text.includes("0"), "step labels paint on edges");
});
