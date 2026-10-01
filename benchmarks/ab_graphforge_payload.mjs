#!/usr/bin/env node
// Interleaved before/after evidence for the GraphForge webview payload path
// (spec/benchmarks/results.md, "GraphForge payload and layout A/B").
//
// Absolute timings move with machine load, so this runs the same GraphForge
// composition through two checkouts alternately (before, after, before, after)
// and records the load beside every sample. Byte sizes are exact.
//
//   uv run python benchmarks/gen_graphforge_scale_inputs.py --out /tmp/gfscale --sizes 10000,100000
//   node benchmarks/ab_graphforge_payload.mjs --inputs /tmp/gfscale --sizes 10000,100000 \
//     --graphforge path/to/node_modules/@curatelabs/graphforge \
//     --before /path/to/old/checkout --after . --out spec/benchmarks/graphforge-payload-ab-local.json
//
// Each checkout needs its own native core (target/release) and packages/xy-node
// dependencies. Layers: pagerank, louvain, and a dijkstra path (no MST, which
// GraphForge 0.5.2 needs minutes for at 100k; CurateLabs/graphforge#1698).
import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import fs from "node:fs";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { performance } from "node:perf_hooks";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseArgs } from "node:util";

const { values: args } = parseArgs({
  options: {
    inputs: { type: "string" },
    sizes: { type: "string", default: "10000,100000" },
    graphforge: { type: "string", default: "@curatelabs/graphforge" },
    before: { type: "string" },
    after: { type: "string", default: "." },
    rounds: { type: "string", default: "2" },
    out: { type: "string" },
    // Internal: measure one checkout on one request file and print JSON.
    measure: { type: "string" },
    request: { type: "string" },
  },
});

const median = (xs) => [...xs].sort((a, b) => a - b)[(xs.length - 1) >> 1];
function timed(fn, reps) {
  let value;
  const samples = [];
  for (let i = 0; i < reps; i += 1) {
    const t = performance.now();
    value = fn();
    samples.push(performance.now() - t);
  }
  return [value, Math.round(median(samples))];
}

if (args.measure) {
  // Child mode: one checkout, one request.
  const g = await import(pathToFileURL(path.join(path.resolve(args.measure), "packages/xy-node/src/graphforge.js")).href);
  const document = g.composeGraphForgeRequest(new Uint8Array(fs.readFileSync(args.request)));
  const [composition, decodeMs] = timed(() => g.decodeGraphForgeDocument(document), 3);
  const big = composition.nodes.count > 50_000;
  const [figure, chartMs] = timed(() => g.graphforgeChart(composition, { width: 960, height: 640 }), big ? 1 : 3);
  const [payload, encodeMs] = timed(() => figure.buildPayload(), big ? 1 : 3);
  const [specText, stringifyMs] = timed(() => JSON.stringify(payload.spec), 1);
  let reuseMs = null;
  if (g.graphforgePositions) {
    const positions = g.graphforgePositions(figure, composition);
    [, reuseMs] = timed(() => g.graphforgeChart(composition, { width: 960, height: 640, positions }), big ? 1 : 3);
  }
  const buffers = payload.buffers;
  const bufferBytes = buffers.byteLength ?? buffers.reduce((sum, b) => sum + b.byteLength, 0);
  process.stdout.write(JSON.stringify({
    nodes: composition.nodes.count,
    edges: composition.edges.count,
    decode_ms: decodeMs,
    chart_ms: chartMs,
    chart_reuse_ms: reuseMs,
    encode_ms: encodeMs,
    spec_stringify_ms: stringifyMs,
    spec_bytes: Buffer.byteLength(specText),
    buffer_bytes: bufferBytes,
  }));
  process.exit(0);
}

if (!args.inputs || !args.before) throw new Error("--inputs and --before are required");
const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const { GraphForge } = require(require.resolve(args.graphforge, { paths: [process.cwd()] }));
const after = path.resolve(args.after);
const before = path.resolve(args.before);
const { encodeGraphForgeRequest } = await import(pathToFileURL(path.join(after, "packages/xy-node/src/graphforge.js")).href);

function uuidv7() {
  const b = randomBytes(16);
  const ts = BigInt(Date.now());
  for (let i = 0; i < 6; i += 1) b[i] = Number((ts >> BigInt(8 * (5 - i))) & 0xffn);
  b[6] = (b[6] & 0x0f) | 0x70;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = b.toString("hex");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

const load = () => Math.round(os.loadavg()[0] * 10) / 10;
const git = (cwd) => {
  try { return execFileSync("git", ["rev-parse", "HEAD"], { cwd, encoding: "utf8" }).trim(); } catch { return null; }
};
const rows = [];
for (const n of args.sizes.split(",").map(Number)) {
  const g = new GraphForge();
  g.publishBulkNodes(uuidv7(), fs.readFileSync(path.join(args.inputs, `nodes-${n}.arrow`)));
  g.publishBulkEdges(uuidv7(), fs.readFileSync(path.join(args.inputs, `edges-${n}.arrow`)));
  const endpoint = (i) => ({ label: "Person", property: "name", value: `p${i}` });
  const results = [g.rank("Person", "pagerank"), g.cluster("Person", "louvain"),
    g.paths(endpoint(0), endpoint(Math.floor(n / 2)), "dijkstra", null, null, null, "w")];
  const request = encodeGraphForgeRequest({
    base: { tables: [g.execute("MATCH (n) RETURN n"), g.execute("MATCH ()-[r]->() RETURN r")] },
    layers: results.map((result) => ({ result, intent: "graph" })),
  });
  const file = path.join(os.tmpdir(), `xyg-ab-request-${n}.bin`);
  fs.writeFileSync(file, request);
  for (let round = 1; round <= Number(args.rounds); round += 1) {
    for (const [side, root] of [["before", before], ["after", after]]) {
      const loadStart = load();
      const out = execFileSync(process.execPath, [path.join(here, "ab_graphforge_payload.mjs"), "--measure", root, "--request", file], {
        encoding: "utf8",
        env: { ...process.env, XYG_NATIVE_LIB: path.join(root, "target/release/libxyg_core.so") },
        maxBuffer: 1 << 20,
      });
      rows.push({ nodes_requested: n, round, side, load_1m: loadStart, ...JSON.parse(out) });
      console.error(`n=${n} round ${round} ${side}: ${out}`);
    }
  }
  fs.rmSync(file, { force: true });
}
const report = {
  schema: "xyg-graphforge-payload-ab-v1",
  before_sha: git(before),
  after_sha: git(after),
  environment: { platform: `${process.platform}-${process.arch}`, node: process.version, cpus: os.cpus().length, cpu_model: os.cpus()[0]?.model ?? null },
  rows,
};
const text = `${JSON.stringify(report, null, 2)}\n`;
if (args.out) fs.writeFileSync(args.out, text);
else process.stdout.write(text);
