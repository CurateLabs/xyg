#!/usr/bin/env node
/**
 * Dual-host graph scale-class evidence (Node / @xy/node).
 *
 * Mirrors the Python `graph_scale_class` rows in bench_scale_all_charts.py:
 * - Always records LOD decisions for 10M / 100M / 1B-class source sizes under
 *   screen-bounded node/edge budgets.
 * - Optionally runs real `graphBuildRender` for sizes listed in --build.
 *
 * Usage:
 *   node benchmarks/bench_graph_scale_classes_node.mjs
 *   node benchmarks/bench_graph_scale_classes_node.mjs --build 10000000
 */

import path from "node:path";
import { fileURLToPath } from "node:url";
import { performance } from "node:perf_hooks";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const xyNode = await import(path.join(ROOT, "packages/xy-node/src/index.js"));
const { abiVersion, graphBuildRender, graphLodDecision } = xyNode;

const CLASS_SIZES = [10_000_000, 100_000_000, 1_000_000_000];
const NODE_BUDGET = 50_000;
const EDGE_BUDGET = 100_000;

function parseArgs(argv) {
  const out = {
    classes: CLASS_SIZES,
    build: [],
    nodeBudget: NODE_BUDGET,
    edgeBudget: EDGE_BUDGET,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--classes" && argv[i + 1]) {
      out.classes = argv[++i]
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => n > 0);
    } else if (arg === "--build" && argv[i + 1]) {
      out.build = argv[++i]
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => n > 0);
    } else if (arg === "--node-budget" && argv[i + 1]) {
      out.nodeBudget = Number(argv[++i]);
    } else if (arg === "--edge-budget" && argv[i + 1]) {
      out.edgeBudget = Number(argv[++i]);
    }
  }
  return out;
}

function classLabel(n) {
  if (n >= 1_000_000_000) return "1B";
  if (n >= 100_000_000) return "100M";
  if (n >= 10_000_000) return "10M";
  if (n >= 1_000_000) return "1M";
  if (n >= 1_000) return `${Math.floor(n / 1000)}k`;
  return String(n);
}

function mulberry32(seed) {
  let t = seed >>> 0;
  return () => {
    t += 0x6d2b79f5;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

function syntheticGraph(n, avgDegree = 2.0) {
  const rng = mulberry32(n);
  const nEdges = Math.max(n, Math.floor((n * avgDegree) / 2));
  const sources = new BigUint64Array(nEdges);
  const targets = new BigUint64Array(nEdges);
  for (let i = 0; i < n; i += 1) {
    sources[i] = BigInt(i);
    targets[i] = BigInt((i + 1) % n);
  }
  for (let i = n; i < nEdges; i += 1) {
    let a = Math.floor(rng() * n);
    let b = Math.floor(rng() * n);
    if (a === b) b = (b + 1) % n;
    sources[i] = BigInt(a);
    targets[i] = BigInt(b);
  }
  const x = new Float64Array(n);
  const y = new Float64Array(n);
  for (let i = 0; i < n; i += 1) {
    x[i] = i / Math.max(1, n - 1);
    y[i] = Math.sin(i * 0.01);
  }
  return { x, y, sources, targets };
}

function benchClass(n, { nodeBudget, edgeBudget, build }) {
  const nEdges = Math.max(n, n * 2);
  const decision = graphLodDecision(n, nEdges, { nodeBudget, edgeBudget });
  const row = {
    family: "graph_scale_class",
    class: classLabel(n),
    n_nodes: n,
    n_edges: nEdges,
    node_budget: nodeBudget,
    edge_budget: edgeBudget,
    lod_tier: decision.tier,
    edges_kept: Number(decision.edgesKept),
    mode: "lod_decision",
    budget_ok: true,
  };
  if (n > nodeBudget && decision.tier < 1) {
    throw new Error(`expected non-direct LOD tier for n=${n}, got ${decision.tier}`);
  }
  if (!build) return row;

  const g = syntheticGraph(n, 2.0);
  const t0 = performance.now();
  const out = graphBuildRender(g.x, g.y, g.sources, g.targets, {
    nodeBudget,
    edgeBudget,
  });
  const ms = performance.now() - t0;
  if (out.x.length > nodeBudget) {
    throw new Error(`render nodes ${out.x.length} > budget ${nodeBudget}`);
  }
  if (out.edgeSources.length > edgeBudget) {
    throw new Error(`render edges ${out.edgeSources.length} > budget ${edgeBudget}`);
  }
  return {
    ...row,
    mode: "build_render",
    render_n_nodes: out.x.length,
    render_n_edges: out.edgeSources.length,
    lod_tier: out.tier,
    edges_kept: Number(out.edgesKept),
    render_graph_ms: ms,
    budget_ok: true,
  };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const buildSet = new Set(args.build);
  const results = args.classes.map((n) =>
    benchClass(n, {
      nodeBudget: args.nodeBudget,
      edgeBudget: args.edgeBudget,
      build: buildSet.has(n),
    }),
  );
  const ok = results.every((r) => r.budget_ok);
  const summary = {
    host: "node",
    abi_version: abiVersion(),
    results,
    ok,
  };
  process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
  if (!ok) process.exit(1);
}

main();
