#!/usr/bin/env node
// GraphForge composition scale evidence (xyg#37,
// spec/design/graphforge-compositions.md §7).
//
// For each size, publishes the deterministic bulk inputs from
// `benchmarks/gen_graphforge_scale_inputs.py` into a real in-memory GraphForge
// graph, runs the engine's own algorithms (GraphForge computes), dumps the base
// graph with `MATCH (n) RETURN n` / `MATCH ()-[r]->() RETURN r`, and then
// measures only XYG's side: request framing, native compose, document decode,
// the Node graph-mark webview payload (chart build and encode), the direct-tier Rust Scene where it fits,
// and the real wasm32 artifact composing the same request bytes (which must be
// byte-identical to native). GraphForge timings are recorded as context, not as
// XYG cost.
//
// Output is counts, bytes, and durations only: no result values, UUIDs,
// vectors, coordinates, or paths.
//
//   uv run python benchmarks/gen_graphforge_scale_inputs.py --out /tmp/gfscale --sizes 100,1000,10000,100000
//   node benchmarks/bench_graphforge_compose.mjs --inputs /tmp/gfscale --sizes 100,1000,10000,100000 \
//     --graphforge /path/to/node_modules/@curatelabs/graphforge --out spec/benchmarks/graphforge-compose-local.json
//
// `--fixture-out DIR` also keeps the 100-node engine run (base dump and
// results) as the native/WASM parity fixture `tests/fixtures/graphforge/scale-100`.
//
// Requires the native core (XYG_NATIVE_LIB or target/release) and the WASM
// artifact (`node js/build.mjs && npm run build:wasm`).
import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import fs from "node:fs";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { performance } from "node:perf_hooks";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

import {
  composeGraphForgeRequest,
  decodeGraphForgeDocument,
  encodeGraphForgeRequest,
  graphforgeChart,
  graphforgePositions,
  GRAPHFORGE_COMPOSITION_VERSION,
} from "../packages/xy-node/src/graphforge.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const WASM = path.join(ROOT, "packages/xy-client/dist/xyg-wasm.wasm");
const { values: args } = parseArgs({
  options: {
    inputs: { type: "string" },
    sizes: { type: "string", default: "100,1000,10000,100000" },
    graphforge: { type: "string", default: "@curatelabs/graphforge" },
    reps: { type: "string", default: "5" },
    out: { type: "string" },
    "fixture-out": { type: "string" },
  },
});
if (!args.inputs) throw new Error("--inputs DIR is required (see gen_graphforge_scale_inputs.py)");
const REPS = Number(args.reps);
// The parity fixture must be the direct-tier (Scene-rendering) run.
const FIXTURE_NODES = 100;
if (args["fixture-out"] && !args.sizes.split(",").map(Number).includes(FIXTURE_NODES)) {
  throw new Error(`--fixture-out needs ${FIXTURE_NODES} in --sizes`);
}
const require = createRequire(import.meta.url);
const graphforgeEntry = require.resolve(args.graphforge, { paths: [process.cwd(), ROOT] });
const { GraphForge } = require(graphforgeEntry);
const graphforgeVersion = JSON.parse(
  fs.readFileSync(path.join(path.dirname(graphforgeEntry), "package.json"), "utf8"),
).version;

/** GraphForge requires UUIDv7 bulk operation ids. */
function uuidv7() {
  const b = randomBytes(16);
  const ts = BigInt(Date.now());
  for (let i = 0; i < 6; i += 1) b[i] = Number((ts >> BigInt(8 * (5 - i))) & 0xffn);
  b[6] = (b[6] & 0x0f) | 0x70;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = b.toString("hex");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

const timed = (fn) => {
  const t = performance.now();
  const value = fn();
  return [value, performance.now() - t];
};
const median = (xs) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
};
const round = (ms) => Math.round(ms * 100) / 100;
/** Median of `REPS` runs after one warm-up; returns [lastValue, medianMs]. */
function bench(fn) {
  let value = fn();
  const samples = [];
  for (let i = 0; i < REPS; i += 1) {
    const [v, ms] = timed(fn);
    value = v;
    samples.push(ms);
  }
  return [value, round(median(samples))];
}


async function loadWasm() {
  const { instance } = await WebAssembly.instantiate(fs.readFileSync(WASM), {});
  const x = instance.exports;
  // The WASM arena ceiling (MAX_ARENA_BYTES, 384 MiB).
  const handle = x.xyg_wasm_instance_new(384 * 1024 * 1024);
  if (!(handle > 0)) throw new Error("WASM instance");
  return (request) => {
    if (x.xyg_wasm_arena_resize(handle, request.byteLength) !== 0) throw new Error("WASM arena resize");
    const ptr = x.xyg_wasm_arena_ptr(handle) >>> 0;
    new Uint8Array(x.memory.buffer, ptr, request.byteLength).set(request);
    if (x.xyg_wasm_graphforge_compose(handle, 0, request.byteLength) !== 0) throw new Error("WASM compose status");
    const out = x.xyg_wasm_output_ptr(handle) >>> 0;
    const len = x.xyg_wasm_output_len(handle) >>> 0;
    return new Uint8Array(x.memory.buffer, out, len).slice();
  };
}

const equalBytes = (a, b) => a.byteLength === b.byteLength && Buffer.compare(Buffer.from(a), Buffer.from(b)) === 0;

function engineRun(n) {
  const g = new GraphForge();
  const nodes = fs.readFileSync(path.join(args.inputs, `nodes-${n}.arrow`));
  const edges = fs.readFileSync(path.join(args.inputs, `edges-${n}.arrow`));
  const t = {};
  [, t.publish_nodes_ms] = timed(() => g.publishBulkNodes(uuidv7(), nodes));
  [, t.publish_edges_ms] = timed(() => g.publishBulkEdges(uuidv7(), edges));
  const results = {};
  [results.pagerank, t.pagerank_ms] = timed(() => g.rank("Person", "pagerank"));
  [results.louvain, t.louvain_ms] = timed(() => g.cluster("Person", "louvain"));
  [results.minimum_spanning_tree, t.minimum_spanning_tree_ms] = timed(() =>
    g.analyze("minimum_spanning_tree", "Person", null, false, "w"));
  const endpoint = (i) => ({ label: "Person", property: "name", value: `p${i}` });
  [results.dijkstra, t.dijkstra_ms] = timed(() =>
    g.paths(endpoint(0), endpoint(Math.floor(n / 2)), "dijkstra", null, null, null, "w"));
  const base = {};
  [base.nodes, t.dump_nodes_ms] = timed(() => g.execute("MATCH (n) RETURN n"));
  [base.edges, t.dump_edges_ms] = timed(() => g.execute("MATCH ()-[r]->() RETURN r"));
  for (const key of Object.keys(t)) t[key] = round(t[key]);
  return { results, base, timings: t, nodeCount: g.nodeCount() };
}

/**
 * Keep one engine run as a parity fixture: at ~100 nodes, layout seeding and
 * dash/arrow geometry exercise enough angles and lengths to expose a
 * platform-`libm` dependence the tiny contract fixtures miss.
 */
function writeFixture(dir, n, engine, generation) {
  fs.mkdirSync(dir, { recursive: true });
  const files = { nodes: "base-nodes.arrow", edges: "base-edges.arrow" };
  fs.writeFileSync(path.join(dir, files.nodes), engine.base.nodes);
  fs.writeFileSync(path.join(dir, files.edges), engine.base.edges);
  for (const [name, bytes] of Object.entries(engine.results)) fs.writeFileSync(path.join(dir, `${name}.arrow`), bytes);
  const manifest = { graphforge: graphforgeVersion, nodes: n, generation, base: files, results: Object.keys(engine.results) };
  fs.writeFileSync(path.join(dir, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
}

function measure(n, composeWasm, fixtureDir) {
  const engine = engineRun(n);
  const generation = uuidv7();
  if (fixtureDir) writeFixture(fixtureDir, n, engine, generation);
  const base = { tables: [engine.base.nodes, engine.base.edges], generation };
  const layer = (name, extra = {}) => ({ result: engine.results[name], intent: "graph", generation, resultId: `result-${name}`, ...extra });
  const requests = {
    single_pagerank: { base, layers: [layer("pagerank")] },
    multi_4_layers: {
      base,
      layers: [layer("pagerank"), layer("louvain"), layer("minimum_spanning_tree"), layer("dijkstra")],
    },
  };
  const row = {
    nodes: n,
    graphforge: {
      node_count: engine.nodeCount,
      result_bytes: Object.fromEntries(Object.entries(engine.results).map(([k, v]) => [k, v.byteLength])),
      base_bytes: engine.base.nodes.byteLength + engine.base.edges.byteLength,
      timings_ms: engine.timings,
    },
    compositions: {},
  };
  for (const [name, input] of Object.entries(requests)) {
    const [request, encodeMs] = bench(() => encodeGraphForgeRequest(input));
    const [document, composeMs] = bench(() => composeGraphForgeRequest(request));
    const [composition, decodeMs] = bench(() => decodeGraphForgeDocument(document));
    const [wasmDocument, wasmMs] = bench(() => composeWasm(request));
    // graphforgeWebviewPayload = graphforgeChart (graph mark: Rust force
    // layout, LOD, routing) + buildPayload (encode); timed apart.
    const [figure, chartMs] = bench(() => graphforgeChart(composition, { width: 960, height: 640 }));
    const [payload, payloadEncodeMs] = bench(() => figure.buildPayload());
    // A recomposition of the same base reuses the layout (preset positions).
    const positions = graphforgePositions(figure, composition);
    const [, chartReuseMs] = bench(() => graphforgeChart(composition, { width: 960, height: 640, positions }));
    const buffer = payload.buffers instanceof Uint8Array ? payload.buffers : new Uint8Array(payload.buffers);
    row.compositions[name] = {
      layers: input.layers.length,
      composed_nodes: composition.nodes.uuid.length,
      composed_edges: composition.edges.class.length,
      decisions: composition.decisions.map((d) => d.code).sort(),
      request_bytes: request.byteLength,
      document_bytes: document.byteLength,
      webview_buffer_bytes: buffer.byteLength,
      webview_spec_bytes: Buffer.byteLength(JSON.stringify(payload.spec)),
      encode_request_ms: encodeMs,
      native_compose_ms: composeMs,
      decode_document_ms: decodeMs,
      wasm_compose_ms: wasmMs,
      webview_chart_ms: chartMs,
      webview_chart_reuse_ms: positions ? chartReuseMs : null,
      webview_encode_ms: payloadEncodeMs,
      native_wasm_identical: equalBytes(document, wasmDocument),
    };
  }
  // Direct-tier Scene: Rust layout + canonical Scene, bounded at 1,024
  // primitives; larger graphs fail closed with GF_COMPOSE_SCENE_TOO_LARGE.
  const renderInput = { ...requests.multi_4_layers, render: { width: 960, height: 640, theme: "light", title: "" } };
  const [renderRequest] = bench(() => encodeGraphForgeRequest(renderInput));
  const [renderDocument, renderMs] = bench(() => composeGraphForgeRequest(renderRequest));
  let scene;
  try {
    const composition = decodeGraphForgeDocument(renderDocument);
    scene = { status: "rendered", scene_bytes: composition.scene?.bytes.byteLength ?? 0 };
  } catch (error) {
    scene = { status: error.code };
  }
  const [wasmRenderDocument, wasmRenderMs] = bench(() => composeWasm(renderRequest));
  row.direct_scene = {
    ...scene,
    native_compose_render_ms: renderMs,
    wasm_compose_render_ms: wasmRenderMs,
    native_wasm_identical: equalBytes(renderDocument, wasmRenderDocument),
  };
  return row;
}

const composeWasm = await loadWasm();
const rows = [];
for (const size of args.sizes.split(",").map(Number)) {
  const row = measure(size, composeWasm, size === FIXTURE_NODES ? args["fixture-out"] : null);
  rows.push(row);
  const single = row.compositions.single_pagerank;
  const multi = row.compositions.multi_4_layers;
  console.error(
    `n=${size}: native ${single.native_compose_ms} ms (1 layer) / ${multi.native_compose_ms} ms (4 layers), `
      + `wasm ${multi.wasm_compose_ms} ms, chart ${multi.webview_chart_ms} ms + encode ${multi.webview_encode_ms} ms, scene ${row.direct_scene.status}`,
  );
}
const git = (argv) => {
  try { return execFileSync("git", argv, { cwd: ROOT, encoding: "utf8" }).trim(); } catch { return null; }
};
const report = {
  schema: "xyg-graphforge-compose-v1",
  git_sha: git(["rev-parse", "HEAD"]),
  git_dirty: Boolean(git(["status", "--porcelain", "--", "crates", "packages/xy-node/src", "js/src"])),
  environment: {
    platform: `${process.platform}-${process.arch}`,
    node: process.version,
    cpus: os.cpus().length,
    cpu_model: os.cpus()[0]?.model ?? null,
    graphforge: graphforgeVersion,
    composition_version: GRAPHFORGE_COMPOSITION_VERSION,
    reps: REPS,
  },
  // The process high-water mark (getrusage ru_maxrss), GraphForge included.
  max_rss_mib: Math.round(process.resourceUsage().maxRSS / 1024),
  rows,
};
const text = `${JSON.stringify(report, null, 2)}\n`;
if (args.out) fs.writeFileSync(args.out, text);
else process.stdout.write(text);
if (rows.some((r) => !r.direct_scene.native_wasm_identical || Object.values(r.compositions).some((c) => !c.native_wasm_identical))) {
  console.error("native and WASM documents differ");
  process.exitCode = 1;
}
