#!/usr/bin/env node
// Node `worker_threads` rung of the CoSE progressive-layout ladder (issue #35).
// Drives packages/xy-node/src/force_scheduler.js `runForceTicks` (the shipped
// worker_threads scheduler) exactly as scripts/bench_cose_progressive.py drives
// GraphLayoutController, and prints one JSON row on stdout. Run through the
// Python orchestrator, which also records the environment.
import { performance } from "node:perf_hooks";
import { runForceTicks } from "../packages/xy-node/src/force_scheduler.js";

const arg = (name, fallback) => {
  const at = process.argv.indexOf(`--${name}`);
  return at === -1 ? fallback : process.argv[at + 1];
};
const nodes = Number(arg("nodes"));
const chunks = Number(arg("chunks"));
const chunkSteps = Number(arg("chunk-steps", 10));
const reps = Number(arg("reps", 3));
const maxWallMs = Number(arg("max-wall-ms", 300_000));
const totalSteps = 1 + chunks * chunkSteps;

// Same edge set as the Python rung: ring + one deterministic chord per node.
const sources = new BigUint64Array(2 * nodes);
const targets = new BigUint64Array(2 * nodes);
for (let i = 0; i < nodes; i += 1) {
  let chord = (i * 7 + 3) % nodes;
  if (chord === i) chord = (i + 2) % nodes;
  sources[2 * i] = BigInt(i);
  targets[2 * i] = BigInt((i + 1) % nodes);
  sources[2 * i + 1] = BigInt(i);
  targets[2 * i + 1] = BigInt(chord);
}

const rows = [];
for (let rep = 0; rep < reps; rep += 1) {
  const arrivals = [];
  let maxLagMs = 0;
  let last = performance.now();
  const ticker = setInterval(() => {
    const now = performance.now();
    maxLagMs = Math.max(maxLagMs, now - last - 5);
    last = now;
  }, 5);
  const started = performance.now();
  let result;
  try {
    result = await runForceTicks({
      nNodes: nodes, sources, targets, algorithm: "cose", seed: 7,
      totalSteps, chunkSteps, maxWallMs, mode: "worker", revision: 1,
      onTick: (state) => arrivals.push({ t: performance.now(), step: state.step, phase: state.phase }),
    });
  } finally {
    clearInterval(ticker);
  }
  const wall = performance.now() - started;
  rows.push({
    first_paint_ms: arrivals[0].t - started,
    cadence_ms: arrivals.slice(1).map((a, i) => a.t - arrivals[i].t),
    checkpoints: arrivals.length,
    steps: result.steps,
    wall_ms: wall,
    max_event_loop_lag_ms: Math.max(0, maxLagMs),
  });
}
process.stdout.write(`${JSON.stringify({
  host: "node-worker-threads", nodes, edges: 2 * nodes, chunk_steps: chunkSteps, total_steps: totalSteps,
  reps: rows, peak_rss_mb: process.resourceUsage().maxRSS / 1024,
})}\n`);
