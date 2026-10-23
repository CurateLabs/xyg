#!/usr/bin/env node
/**
 * Tier-3 pyramid scale evidence (Node twin). See spec/design/tier3-testing.md.
 */
import { performance } from "node:perf_hooks";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import os from "node:os";

import { nativeLibraryFileName } from "../packages/xy-node/src/native-path.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
process.chdir(root);
if (!process.env.XYG_NATIVE_LIB) {
  process.env.XYG_NATIVE_LIB = path.join(root, "target/release", nativeLibraryFileName());
}

const {
  pyramidBuild,
  pyramidCompose,
  pyramidFree,
  pyramidReportBytes,
  pyramidSpill,
  tileStoreCompose,
  tileStorePaint,
  tileStoreStats,
  tileStoreFree,
  tileBudgetSet,
} = await import("../packages/xy-node/src/pyramid.js");

function spillEvidence(x, y) {
  let handle = pyramidBuild(x, y, 0, 1, 0, 1, 1024), store = 0n;
  assert.notEqual(handle, 0n);
  const budget = 2 << 20;
  const residentSamples = [];
  const windows = Array.from({ length: 32 }, (_, index) => {
    const k = [0, 1, 2, 3, 4, 3, 2, 1][index % 8];
    return [k / 8, k / 8 + 0.5, 0, 0.5];
  });
  try {
    const started = performance.now();
    store = pyramidSpill(handle);
    const spillMs = performance.now() - started;
    assert.notEqual(store, 0n);
    assert.equal(tileBudgetSet(budget), true);
    for (const window of windows) {
      const expected = pyramidCompose(handle, ...window, 128, 96, { maxUpsample: 8 });
      const actual = tileStoreCompose(store, ...window, 128, 96, { maxUpsample: 8 });
      assert.ok(expected && actual);
      assert.equal(actual.level, expected.level);
      assert.deepEqual(actual.grid, expected.grid);
      residentSamples.push(Number(tileStoreStats(store).resident_bytes));
      assert.ok(residentSamples.at(-1) <= budget);
    }
    assert.equal(pyramidFree(handle), true);
    handle = 0n;
    function frame(packet, pool) {
      assert.equal(Buffer.from(packet.subarray(0, 8)).toString("hex"), "5859445401000000");
      const data = new DataView(packet.buffer, packet.byteOffset, packet.byteLength);
      const u32 = at => data.getUint32(at, true);
      const level = u32(8), flags = u32(12), count = u32(16), active = u32(20);
      const missing = u32(24), stride = u32(28), generation = data.getBigUint64(32, true).toString();
      assert.equal(stride, 96);
      assert.ok(active > 0 && active <= count && count <= 256);
      assert.equal(u32(64), 256 * 256 * (flags & 1 ? 4 : 1) * 8);
      assert.ok(u32(68) <= u32(64));
      const kept = new Map(), hashes = [], keys = [];
      let transferred = 0, logical = 0;
      for (let i = 0; i < count; i++) {
        const at = 128 + i * stride, lev = u32(at), tx = u32(at + 4), ty = u32(at + 8);
        const width = u32(at + 12), height = u32(at + 16), offset = u32(at + 20), length = u32(at + 24);
        const key = `${generation}/${lev}/${tx}/${ty}`;
        keys.push([lev, tx, ty]);
        logical += width * height * (flags & 1 ? 4 : 1);
        if (length) {
          assert.ok(offset >= 128 + count * stride && offset + length <= packet.length);
          assert.equal(length, width * height * (flags & 1 ? 4 : 1));
          kept.set(key, createHash("sha256").update(packet.subarray(offset, offset + length)).digest("hex"));
          transferred++;
        } else {
          assert.ok(pool.has(key), "Rust omitted a tile not held by the client");
          kept.set(key, pool.get(key));
        }
        if (i < active) {
          assert.equal(u32(at + 28), 1);
          assert.equal(lev, level);
          hashes.push([key, kept.get(key)]);
        }
      }
      assert.equal(transferred, missing);
      assert.equal(logical, u32(68));
      return { pool: kept, state: { generation, level, keys, hashes,
        normalization: Buffer.from(packet.subarray(40, 56)).toString("hex"), transferred, bytes: packet.length,
        descriptors: count, gpu_bytes: u32(68), gpu_budget: u32(64) } };
    }
    let pool = new Map(), state = null;
    const observed = [], times = [];
    for (const window of windows) {
      const started = performance.now();
      const packet = tileStorePaint(store, ...window, 256, 256, state ?? {});
      times.push(performance.now() - started);
      assert.ok(packet);
      ({ pool, state } = frame(packet, pool));
      observed.push(state);
      residentSamples.push(Number(tileStoreStats(store).resident_bytes));
      assert.ok(residentSamples.at(-1) <= budget);
    }
    let uncachedTiles = 0, uncachedBytes = 0;
    for (const [index, window] of windows.entries()) {
      const packet = tileStorePaint(store, ...window, 256, 256);
      assert.ok(packet);
      const oracle = frame(packet, new Map()).state;
      assert.deepEqual(oracle.hashes, observed[index].hashes);
      assert.equal(oracle.normalization, observed[index].normalization);
      uncachedTiles += oracle.transferred;
      uncachedBytes += oracle.bytes;
    }
    const cachedTiles = observed.reduce((sum, item) => sum + item.transferred, 0);
    assert.ok(cachedTiles > 0 && cachedTiles < uncachedTiles);
    const stats = tileStoreStats(store);
    assert.ok(Number(stats.hit) > 0 && Number(stats.miss) > 0);
    assert.ok(Number(stats.resident_bytes) <= Number(stats.budget_bytes));
    assert.equal(Number(stats.budget_bytes), budget);
    const sortedTimes = [...times].sort((a, b) => a - b);
    return { spill_ms: spillMs, compose_oracle_frames: windows.length, tile_frames: windows.length,
      tile_frame_p95_ms: sortedTimes[Math.floor(times.length * 0.95)],
      tile_frame_samples_ms: times,
      max_descriptors: Math.max(...observed.map(item => item.descriptors)),
      max_gpu_bytes: Math.max(...observed.map(item => item.gpu_bytes)),
      gpu_budget_bytes: observed[0].gpu_budget,
      resident_samples_bytes: residentSamples,
      timing_scope: "cached sequence before separate uncached validation; advisory only",
      cached_transferred_tiles: cachedTiles, uncached_transferred_tiles: uncachedTiles,
      cached_reply_bytes: observed.reduce((sum, item) => sum + item.bytes, 0), uncached_reply_bytes: uncachedBytes,
      tiles: Object.fromEntries(Object.entries(stats).map(([name, value]) => [name, typeof value === "bigint" ? Number(value) : value])),
      oracles_equal: true, budget_ok: true };
  } finally {
    if (handle) pyramidFree(handle);
    if (store) tileStoreFree(store);
    tileBudgetSet(0);
  }
}

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
  schema_version: 1,
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
  spill: spillEvidence(x, y),
  environment: {
    generated_at_utc: new Date().toISOString(),
    runtime: { node: process.version, v8: process.versions.v8 },
    platform: { system: os.platform(), release: os.release(), machine: os.arch() },
    cpu_count: os.cpus().length,
    git: { commit: execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim() },
  },
  provenance: {
    native_sha256: createHash("sha256").update(readFileSync(process.env.XYG_NATIVE_LIB)).digest("hex"),
    source_sha256: Object.fromEntries([
      "benchmarks/bench_tier3_pyramid_node.mjs", "packages/xy-node/src/pyramid.js",
      "crates/xyg-engine/src/tile_store.rs", "crates/xyg-engine/src/tile_store/paint.rs",
      "crates/xyg-engine/src/tiles.rs", "crates/xyg-core/src/lib.rs",
    ].map(file => [file, createHash("sha256").update(readFileSync(path.join(root, file))).digest("hex")])),
  },
};
console.log(JSON.stringify(report, null, 2));
process.exit(report.budget_ok ? 0 : 1);
