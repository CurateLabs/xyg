// Native / direct-browser WASM equivalence for GraphForge compositions
// (spec/design/graphforge-compositions.md §6.3). The same XYGQ request bytes
// go through the native C ABI (koffi) and the real wasm32 artifact
// (packages/xy-client/dist/xyg-wasm.wasm); the XYGF documents — including
// error documents and rendered Scenes — must be byte-identical. The browser
// bundle's request framing must also equal the Node framing.
//
// Build the artifact with `node js/build.mjs && npm run build:wasm`.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

import {
  composeGraphForgeRequest,
  decodeGraphForgeDocument,
  encodeGraphForgeRequest,
} from "../src/graphforge.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const RESULTS = path.join(ROOT, "tests/fixtures/graphforge/results");
const DERIVED = path.join(ROOT, "tests/fixtures/graphforge/derived");
const MANIFEST = JSON.parse(fs.readFileSync(path.join(RESULTS, "manifest.json"), "utf8"));
const WASM = path.join(ROOT, "packages/xy-client/dist/xyg-wasm.wasm");
const BUNDLE = path.join(ROOT, "packages/xy-client/dist/index.js");
const skip = fs.existsSync(WASM) && fs.existsSync(BUNDLE)
  ? false
  : "build the WASM artifact first: node js/build.mjs && npm run build:wasm";

const arrow = (name) => fs.readFileSync(path.join(RESULTS, `${name}.arrow`));
function base(name) {
  const spec = MANIFEST.bases[name];
  return { tables: [arrow(spec.nodes), arrow(spec.edges)], generation: spec.generation };
}

async function loadWasm() {
  const { instance } = await WebAssembly.instantiate(fs.readFileSync(WASM), {});
  const x = instance.exports;
  const handle = x.xyg_wasm_instance_new(256 * 1024 * 1024);
  assert.ok(handle > 0, "WASM instance");
  return (request) => {
    assert.equal(x.xyg_wasm_arena_resize(handle, request.byteLength), 0);
    const ptr = x.xyg_wasm_arena_ptr(handle) >>> 0;
    new Uint8Array(x.memory.buffer, ptr, request.byteLength).set(request);
    assert.equal(x.xyg_wasm_graphforge_compose(handle, 0, request.byteLength), 0);
    const out = x.xyg_wasm_output_ptr(handle) >>> 0;
    const len = x.xyg_wasm_output_len(handle) >>> 0;
    return new Uint8Array(x.memory.buffer, out, len).slice();
  };
}

function cases() {
  const out = [];
  for (const { algorithm } of MANIFEST.contracts) {
    const baseName = MANIFEST.fixtures[algorithm].base;
    const generation = MANIFEST.bases[baseName].generation;
    const intents = {
      "is_dag": "table", "has_euler_circuit": "table", "has_euler_path": "table", "is_planar": "table",
      "chromatic_number": "table", "triangle_count": "table", "count_automorphisms": "table",
      "modularity": "table", "transitivity": "table", "conductance": "bar-chart",
      "triad_census": "table", "dyad_census": "bar-chart", "node2vec": "parallel-coordinates",
      "graphsage": "parallel-coordinates", "fast_random_projection": "parallel-coordinates",
      "hashgnn": "parallel-coordinates",
    };
    const intent = intents[algorithm] ?? "graph";
    out.push([algorithm, {
      base: base(baseName),
      layers: [{ result: arrow(algorithm), intent, generation, resultId: `result-${algorithm}` }],
    }]);
  }
  const gen = MANIFEST.bases.cyclic.generation;
  out.push(["multi-layer + render + select", {
    base: base("cyclic"),
    layers: ["pagerank", "louvain", "node_similarity", "dijkstra"].map((name) => ({ result: arrow(name), intent: "graph", generation: gen })),
    select: [],
    render: { width: 640, height: 420, theme: "dark", title: "GraphForge" },
  }]);
  out.push(["coordinates", {
    layers: [{ result: arrow("node2vec"), intent: "embedding-coordinates", coordinates: fs.readFileSync(path.join(DERIVED, "node2vec-coordinates.arrow")) }],
  }]);
  // Error documents must match too.
  out.push(["stale generation", { base: base("cyclic"), layers: [{ result: arrow("pagerank"), intent: "graph", generation: MANIFEST.bases.dag.generation }] }]);
  out.push(["incompatible base", { base: base("dag"), layers: [{ result: arrow("pagerank"), intent: "graph", generation: MANIFEST.bases.dag.generation }] }]);
  out.push(["truncated result", { base: base("cyclic"), layers: [{ result: arrow("pagerank").subarray(0, 300), intent: "graph", generation: gen }] }]);
  out.push(["coordinates required", { layers: [{ result: arrow("node2vec"), intent: "embedding-coordinates" }] }]);
  return out;
}

test("native and WASM compose byte-identical XYGF documents on every fixture", { skip }, async () => {
  const wasm = await loadWasm();
  let compared = 0;
  for (const [label, input] of cases()) {
    const request = encodeGraphForgeRequest(input);
    const native = composeGraphForgeRequest(request);
    const browser = wasm(request);
    assert.equal(Buffer.compare(Buffer.from(native), Buffer.from(browser)), 0, `${label}: documents differ`);
    compared += 1;
  }
  assert.ok(compared >= 100, `compared ${compared} requests`);
});

test("rendered Scenes are identical and carry every composed identity", { skip }, async () => {
  const wasm = await loadWasm();
  const gen = MANIFEST.bases.cyclic.generation;
  const request = encodeGraphForgeRequest({
    base: base("cyclic"),
    layers: [{ result: arrow("pagerank"), intent: "graph", generation: gen }, { result: arrow("minimum_spanning_tree"), intent: "graph", generation: gen }],
    render: { width: 480, height: 360 },
  });
  const native = decodeGraphForgeDocument(composeGraphForgeRequest(request));
  const browser = decodeGraphForgeDocument(wasm(request));
  const scene = (c) => c.sections.get("scene.canonical#0").value;
  assert.ok(scene(native).length > 0);
  assert.deepEqual(scene(native), scene(browser));
});

test("rendered Scenes stay identical on graphs large enough to exercise layout seeding", { skip }, async () => {
  // Fixture graphs are tiny; circle seeding at larger n is where a platform
  // libm and wasm32's used to disagree by an ulp, which force ticks amplify.
  const wasm = await loadWasm();
  const id = (kind, i) => `0190a000-0000-7000-8${kind}00-${i.toString(16).padStart(12, "0")}`;
  for (const n of [37, 150, 330]) {
    const nodeUuid = Array.from({ length: n }, (_, i) => id(1, i));
    const pairs = Array.from({ length: n }, (_, i) => [i, (i + 1) % n]).concat(Array.from({ length: n }, (_, i) => [i, (i * 7 + 3) % n]));
    const request = encodeGraphForgeRequest({
      base: {
        nodeUuid,
        edgeUuid: pairs.map((_, j) => id(2, j)),
        edgeSourceUuid: pairs.map(([s]) => nodeUuid[s]),
        edgeTargetUuid: pairs.map(([, t]) => nodeUuid[t]),
      },
      layers: [{ result: arrow("articulation_points"), intent: "graph", extra: "drop" }],
      render: { width: 800, height: 600 },
    });
    const native = composeGraphForgeRequest(request);
    assert.ok(decodeGraphForgeDocument(native).scene, `n=${n}: a Scene was rendered`);
    assert.equal(Buffer.compare(Buffer.from(native), Buffer.from(wasm(request))), 0, `n=${n}: documents differ`);
  }
});

test("a 100-node GraphForge run renders identical Scenes on both hosts", { skip }, async () => {
  // Real engine output (benchmarks/bench_graphforge_compose.mjs --fixture-out):
  // derived, tree, and path layers exercise dash cuts and arrowheads, where a
  // libm hypot once made the hosts differ.
  const dir = path.join(ROOT, "tests/fixtures/graphforge/scale-100");
  const manifest = JSON.parse(fs.readFileSync(path.join(dir, "manifest.json"), "utf8"));
  const read = (file) => fs.readFileSync(path.join(dir, file));
  const wasm = await loadWasm();
  const request = encodeGraphForgeRequest({
    base: { tables: [read(manifest.base.nodes), read(manifest.base.edges)], generation: manifest.generation },
    layers: manifest.results.map((name) => ({ result: read(`${name}.arrow`), intent: "graph", generation: manifest.generation })),
    render: { width: 960, height: 640, theme: "dark", title: "scale-100" },
  });
  const native = composeGraphForgeRequest(request);
  const composition = decodeGraphForgeDocument(native);
  assert.equal(composition.nodes.count, manifest.nodes);
  assert.ok(composition.scene, "a Scene was rendered");
  assert.equal(Buffer.compare(Buffer.from(native), Buffer.from(wasm(request))), 0, "documents differ");
});

test("the browser bundle frames the same request bytes and decodes the same identities", { skip }, async () => {
  const client = await import(pathToFileURL(BUNDLE).href);
  const gen = MANIFEST.bases.cyclic.generation;
  const input = {
    base: base("cyclic"),
    layers: [
      { result: arrow("pagerank"), intent: "graph", generation: gen, resultId: "r1", missing: "dim", extra: "error", rows: [0, 1, 2, 3] },
      { result: arrow("node_similarity"), intent: "graph", generation: gen },
    ],
    select: [],
    render: { width: 640, height: 400, theme: "light", title: "t" },
  };
  const toBytes = (b) => new Uint8Array(b instanceof ArrayBuffer ? b : b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength));
  const nodeRequest = encodeGraphForgeRequest(input);
  const browserRequest = toBytes(client.encodeWasmGraphForgeRequest(input));
  assert.deepEqual(browserRequest, nodeRequest, "one request framing");
  const document = composeGraphForgeRequest(nodeRequest);
  const nodeComposition = decodeGraphForgeDocument(document);
  const browserComposition = client.decodeWasmGraphForgeDocument(document);
  assert.deepEqual(browserComposition.nodeUuid, nodeComposition.nodes.uuid);
  assert.deepEqual(browserComposition.edgeUuid, nodeComposition.edges.uuid);
  for (let i = 0; i < nodeComposition.nodes.count; i += 1) {
    const stable = (1n << 32n) + BigInt(i);
    assert.deepEqual(browserComposition.identifyStableId(stable).layers, nodeComposition.identify("node", i).layers);
  }
  for (let j = 0; j < nodeComposition.edges.count; j += 1) {
    const browserEdge = browserComposition.identifyStableId(BigInt(j) + 1n);
    const nodeEdge = nodeComposition.identify("edge", j);
    assert.equal(browserEdge.uuid, nodeEdge.uuid);
    assert.equal(browserEdge.derived, nodeEdge.derived);
    assert.deepEqual(browserEdge.layers, nodeEdge.layers);
  }
  // Error documents throw the same stable code in both decoders.
  const stale = composeGraphForgeRequest(encodeGraphForgeRequest({
    base: base("cyclic"), layers: [{ result: arrow("pagerank"), intent: "graph", generation: MANIFEST.bases.dag.generation }],
  }));
  assert.throws(() => client.decodeWasmGraphForgeDocument(stale), (e) => e.code === "GF_COMPOSE_GENERATION_STALE" && e.layer === 0);
  assert.throws(() => decodeGraphForgeDocument(stale), (e) => e.code === "GF_COMPOSE_GENERATION_STALE" && e.layer === 0);
});
