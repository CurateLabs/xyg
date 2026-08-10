#!/usr/bin/env node
/**
 * Dual-host graph force + render-graph microbench (Node / @xy/node host).
 *
 * Same force + buildRender timings and node/edge budget assertions as
 * benchmarks/bench_dual_host_graph.py. Loads libxy_core via XY_NATIVE_LIB
 * (or packages/xy-node resolution). Prints a JSON summary to stdout.
 *
 * Soft ceilings (ms) — catastrophic regression only (~10–20× warm CI):
 *   n=1000:  force 500 / build_render 100
 *   n=10000: force 3000 / build_render 500
 *   n=50000: force 15000 / build_render 2000
 *
 * Usage:
 *   XY_NATIVE_LIB=target/release/libxy_core.so node benchmarks/bench_dual_host_graph_node.mjs
 *   node benchmarks/bench_dual_host_graph_node.mjs --sizes 1000
 */

import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { performance } from "node:perf_hooks";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const require = createRequire(import.meta.url);

// Resolve @xy/node from the monorepo package (no publish required).
const xyNode = await import(path.join(ROOT, "packages/xy-node/src/index.js"));
const {
  abiVersion,
  graphBuildRender,
  graphForceCreate,
  graphForceDestroy,
  graphForceTick,
  graphLayout,
} = xyNode;

const SOFT_CEILING_MS = {
  1000: { force_ms: 500.0, build_render_ms: 100.0 },
  10000: { force_ms: 3000.0, build_render_ms: 500.0 },
  50000: { force_ms: 15000.0, build_render_ms: 2000.0 },
  100000: { force_ms: 40000.0, build_render_ms: 5000.0 },
};

const DEFAULT_SIZES = [1000, 10000, 50000];
const NODE_BUDGET = 5000;
const EDGE_BUDGET = 10000;
const FORCE_TICKS = 5;
const FORCE_SEED = 7n;

function parseArgs(argv) {
  const out = {
    sizes: DEFAULT_SIZES,
    nodeBudget: NODE_BUDGET,
    edgeBudget: EDGE_BUDGET,
    ticks: FORCE_TICKS,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--sizes" && argv[i + 1]) {
      out.sizes = argv[++i].split(",").map((s) => Number(s.trim())).filter((n) => n > 0);
    } else if (arg === "--node-budget" && argv[i + 1]) {
      out.nodeBudget = Number(argv[++i]);
    } else if (arg === "--edge-budget" && argv[i + 1]) {
      out.edgeBudget = Number(argv[++i]);
    } else if (arg === "--ticks" && argv[i + 1]) {
      out.ticks = Number(argv[++i]);
    }
  }
  return out;
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

function syntheticGraph(n, seed = 0) {
  const rand = mulberry32(seed);
  const sources = [];
  const targets = [];
  for (let i = 0; i < n; i += 1) {
    sources.push(BigInt(i));
    targets.push(BigInt((i + 1) % n));
  }
  for (let i = 0; i < n; i += 1) {
    const a = Math.floor(rand() * n);
    let b = Math.floor(rand() * n);
    if (a === b) {
      b = (b + 1) % n;
    }
    sources.push(BigInt(a));
    targets.push(BigInt(b));
  }
  return {
    sources: BigUint64Array.from(sources),
    targets: BigUint64Array.from(targets),
  };
}

function bestMs(fn, repeat = 3) {
  let best = Number.POSITIVE_INFINITY;
  for (let i = 0; i < repeat; i += 1) {
    const t0 = performance.now();
    fn();
    best = Math.min(best, performance.now() - t0);
  }
  return best;
}

function benchSize(n, { nodeBudget, edgeBudget, ticks }) {
  const { sources, targets } = syntheticGraph(n);
  const circle = graphLayout("circle", n, sources, targets);

  function runForce() {
    const handle = graphForceCreate(n, sources, targets, {
      x: circle.x,
      y: circle.y,
      seed: FORCE_SEED,
    });
    try {
      return graphForceTick(handle, n, ticks);
    } finally {
      graphForceDestroy(handle);
    }
  }

  const warmed = runForce();
  const forceMs = bestMs(() => {
    runForce();
  });

  function runBuild() {
    return graphBuildRender(warmed.x, warmed.y, sources, targets, {
      nodeBudget,
      edgeBudget,
    });
  }

  const out = runBuild();
  const buildMs = bestMs(() => {
    runBuild();
  });

  const nPrime = out.x.length;
  const ePrime = out.edgeSources.length;
  if (nPrime > nodeBudget) {
    throw new Error(`|V'|=${nPrime} exceeds node_budget=${nodeBudget}`);
  }
  if (ePrime > edgeBudget) {
    throw new Error(`|E'|=${ePrime} exceeds edge_budget=${edgeBudget}`);
  }

  const ceilings = SOFT_CEILING_MS[n] ?? null;
  if (ceilings) {
    if (forceMs > ceilings.force_ms) {
      throw new Error(
        `force_ms=${forceMs.toFixed(3)} exceeds soft ceiling ${ceilings.force_ms} for n=${n}`,
      );
    }
    if (buildMs > ceilings.build_render_ms) {
      throw new Error(
        `build_render_ms=${buildMs.toFixed(3)} exceeds soft ceiling ${ceilings.build_render_ms} for n=${n}`,
      );
    }
  }

  return {
    n,
    n_edges: sources.length,
    force_ticks: ticks,
    force_ms: forceMs,
    build_render_ms: buildMs,
    node_budget: nodeBudget,
    edge_budget: edgeBudget,
    n_prime: nPrime,
    e_prime: ePrime,
    tier: out.tier,
    edges_kept: Number(out.edgesKept),
    soft_ceiling_ms: ceilings,
    abi_version: abiVersion(),
  };
}

function main() {
  // Touch require so createRequire stays used if tree-shaken tooling inspects.
  void require;
  const args = parseArgs(process.argv.slice(2));
  const results = args.sizes.map((n) =>
    benchSize(n, {
      nodeBudget: args.nodeBudget,
      edgeBudget: args.edgeBudget,
      ticks: args.ticks,
    }),
  );
  const summary = {
    host: "node",
    abi_version: abiVersion(),
    node_budget: args.nodeBudget,
    edge_budget: args.edgeBudget,
    force_ticks: args.ticks,
    results,
    ok: true,
  };
  process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
}

try {
  main();
} catch (err) {
  process.stderr.write(`${JSON.stringify({ ok: false, error: String(err?.message ?? err) }, null, 2)}\n`);
  process.exitCode = 1;
}
