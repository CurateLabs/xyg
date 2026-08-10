#!/usr/bin/env node
/**
 * Tier-3 pyramid scale evidence (Node twin). See spec/design/tier3-testing.md.
 */
import { performance } from "node:perf_hooks";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
process.chdir(root);
if (!process.env.XY_NATIVE_LIB) {
  process.env.XY_NATIVE_LIB = path.join(root, "target/release/libxy_core.so");
}

const {
  pyramidBuild,
  pyramidCompose,
  pyramidFree,
  pyramidReportBytes,
} = await import("../packages/xy-node/src/pyramid.js");

const n = 1_000_000;
const x = new Float64Array(n);
const y = new Float64Array(n);
for (let i = 0; i < n; i += 1) {
  x[i] = ((i * 13) % 10_000) / 10_000;
  y[i] = ((i * 29) % 10_000) / 10_000;
}

const t0 = performance.now();
const handle = pyramidBuild(x, y, 0, 1, 0, 1, 256);
const buildMs = performance.now() - t0;
if (handle === 0n) {
  console.error("pyramidBuild failed");
  process.exit(1);
}

const composeMs = [];
const binnings = new Set();
for (let k = 0; k < 32; k += 1) {
  const lo = (k % 8) / 10;
  const hi = lo + 0.25;
  const t1 = performance.now();
  const composed = pyramidCompose(handle, lo, hi, lo, hi, 128, 96, { maxUpsample: 8 });
  composeMs.push(performance.now() - t1);
  if (composed == null || composed.grid.length !== 128 * 96) {
    console.error("compose failed", composed);
    process.exit(1);
  }
  binnings.add(composed.binning);
}
pyramidFree(handle);

composeMs.sort((a, b) => a - b);
const p95 = composeMs[Math.floor(composeMs.length * 0.95)];
const resident = pyramidReportBytes(256);
const rawXy = n * 16;
const report = {
  host: "node",
  family: "tier3_pyramid",
  n,
  build_ms: buildMs,
  compose_p95_ms: p95,
  compose_n: composeMs.length,
  binnings: [...binnings].sort(),
  resident_bytes: resident,
  raw_xy_bytes: rawXy,
  budget_ok: resident < rawXy && [...binnings].every((b) => b.startsWith("pyramid-L")),
  latency_advisory_ok: p95 < 50.0,
};
console.log(JSON.stringify(report, null, 2));
process.exit(report.budget_ok ? 0 : 1);
