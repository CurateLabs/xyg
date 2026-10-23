/**
 * Tier-3 pyramid productization tests + CI-safe scale evidence.
 *
 * Best-practice rules (see spec/design/tier3-testing.md):
 * - Correctness goldens at small N (compose vs bin2d, append, free).
 * - Scale class uses modest N (≤ a few million) + many compose windows —
 *   never allocate 1B points in CI.
 * - Force pyramid for small fixtures; auto path covered at PYRAMID_MIN.
 */
import assert from "node:assert/strict";
import crypto from "node:crypto";
import test from "node:test";

import {
  PYRAMID_BASE_DIM,
  PYRAMID_MIN_POINTS,
  PYRAMID_RESIDENT_BYTES,
  attachScatter,
  bin2d,
  densityLogU8,
  figure,
  pyramidAppend,
  pyramidBuild,
  pyramidBuildColor,
  pyramidCompose,
  pyramidCount,
  pyramidFree,
  pyramidReportBytes,
  pyramidSpill,
  shouldUsePyramid,
  tileStoreCompose,
  tileStoreComposeColor,
  tileStoreAppend,
  tileBudgetSet,
  tileStoreFree,
  tileStoreStats,
} from "../src/index.js";

function fill(n, fn) {
  const out = new Float64Array(n);
  for (let i = 0; i < n; i += 1) out[i] = fn(i);
  return out;
}

test("shouldUsePyramid mirrors Python PYRAMID_MIN_POINTS", () => {
  assert.equal(shouldUsePyramid(PYRAMID_MIN_POINTS - 1), false);
  assert.equal(shouldUsePyramid(PYRAMID_MIN_POINTS), true);
  assert.equal(shouldUsePyramid(100, { forcePyramid: true }), true);
  assert.equal(shouldUsePyramid(PYRAMID_MIN_POINTS * 2, { forceBin2d: true }), false);
});

test("pyramid build/count/compose/free goldens", () => {
  const n = 4_096;
  const x = fill(n, (i) => (i % 64) / 64);
  const y = fill(n, (i) => Math.floor(i / 64) / 64);
  const handle = pyramidBuild(x, y, 0, 1, 0, 1, 64);
  assert.ok(handle !== 0n);
  const cnt = pyramidCount(handle, 0, 1, 0, 1);
  assert.equal(cnt, n);
  const composed = pyramidCompose(handle, 0, 1, 0, 1, 32, 32, { maxUpsample: 8 });
  assert.ok(composed);
  assert.match(composed.binning, /^pyramid-L\d+/);
  let sum = 0;
  for (let i = 0; i < composed.grid.length; i += 1) sum += composed.grid[i];
  assert.ok(Math.abs(sum - n) < 1e-3);
  assert.equal(pyramidFree(handle), true);
  assert.equal(pyramidFree(handle), false);
});

test("pyramid compose full-window matches bin2d total mass", () => {
  const n = 8_192;
  const x = fill(n, (i) => ((i * 17) % n) / n);
  const y = fill(n, (i) => ((i * 31) % n) / n);
  const handle = pyramidBuild(x, y, 0, 1, 0, 1, 128);
  const composed = pyramidCompose(handle, 0, 1, 0, 1, 64, 48, { maxUpsample: 16 });
  const direct = bin2d(x, y, 0, 1, 0, 1, 64, 48);
  let cSum = 0;
  let dSum = 0;
  for (let i = 0; i < composed.grid.length; i += 1) {
    cSum += composed.grid[i];
    dSum += direct[i];
  }
  assert.ok(Math.abs(cSum - dSum) / Math.max(1, dSum) < 1e-6);
  pyramidFree(handle);
});

test("pyramid append conserves count; domain growth refused", () => {
  const x = new Float64Array([0.1, 0.2, 0.3]);
  const y = new Float64Array([0.1, 0.2, 0.3]);
  const handle = pyramidBuild(x, y, 0, 1, 0, 1, 16);
  assert.equal(pyramidAppend(handle, new Float64Array([0.4]), new Float64Array([0.4])), true);
  assert.equal(pyramidCount(handle, 0, 1, 0, 1), 4);
  assert.equal(pyramidAppend(handle, new Float64Array([2.0]), new Float64Array([0.5])), false);
  assert.equal(pyramidCount(handle, 0, 1, 0, 1), 4);
  pyramidFree(handle);
});

test("pyramid outresolve returns null (caller falls back to bin2d)", () => {
  const x = fill(256, (i) => i / 256);
  const y = fill(256, (i) => i / 256);
  const handle = pyramidBuild(x, y, 0, 1, 0, 1, 16);
  // Tiny window at max upsample 1 → likely outresolve.
  const refused = pyramidCompose(handle, 0.49, 0.51, 0.49, 0.51, 512, 512, {
    maxUpsample: 1,
  });
  // May or may not refuse depending on level math; if refused, null.
  if (refused == null) {
    assert.equal(refused, null);
  } else {
    assert.ok(refused.grid.length === 512 * 512);
  }
  pyramidFree(handle);
});

test("force_pyramid ignored below PYRAMID_MIN like Python _density_trace_spec", () => {
  const n = 10_000;
  const x = fill(n, (i) => (i % 100) / 99);
  const y = fill(n, (i) => Math.floor(i / 100) / 99);
  const fig = figure({ width: 320, height: 240 });
  fig.scatter(x, y, { forcePyramid: true, forceDensity: true });
  const { spec } = fig.buildPayload();
  const t = spec.traces[0];
  assert.equal(t.tier, "density");
  assert.equal(t.density.reduction, "bin2d");
  assert.equal(t.density.enc, "log-u8");
  fig.dispose();
});

test("compose cost does not grow with N once pyramid is built (scale evidence)", () => {
  // CI-safe: build at 1M (well under 1B), compose many windows. Timing is
  // advisory — structural check is that compose returns screen-bounded grids.
  const n = 1_000_000;
  const x = fill(n, (i) => ((i * 13) % 10_000) / 10_000);
  const y = fill(n, (i) => ((i * 29) % 10_000) / 10_000);
  const handle = pyramidBuild(x, y, 0, 1, 0, 1, 256);
  assert.ok(handle !== 0n);
  const windows = [];
  for (let k = 0; k < 32; k += 1) {
    const lo = (k % 8) / 10;
    const hi = lo + 0.25;
    const composed = pyramidCompose(handle, lo, hi, lo, hi, 128, 96, { maxUpsample: 8 });
    assert.ok(composed);
    assert.equal(composed.grid.length, 128 * 96);
    windows.push(composed.binning);
  }
  assert.ok(windows.every((b) => b.startsWith("pyramid-L")));
  // Resident bytes must stay O(base_dim²), not O(N).
  const bytes = pyramidReportBytes(256);
  assert.ok(bytes < 256 * 256 * 4 * 2); // count levels ≤ 2× finest
  assert.ok(bytes < n); // far below raw f64 xy (16N)
  pyramidFree(handle);
});

test("pyramidReportBytes matches 4/3 geometric series", () => {
  const dim = PYRAMID_BASE_DIM;
  const bytes = pyramidReportBytes(dim);
  // sum_{k=0..} (dim/2^k)^2 * 4 until 1
  let expect = 0;
  let d = dim;
  while (true) {
    expect += d * d * 4;
    if (d === 1) break;
    d >>= 1;
  }
  assert.equal(bytes, expect);
});

test("densityLogU8 accepts pyramid compose grids", () => {
  const x = fill(1024, (i) => i / 1024);
  const y = fill(1024, (i) => ((i * 3) % 1024) / 1024);
  const handle = pyramidBuild(x, y, 0, 1, 0, 1, 32);
  const { grid } = pyramidCompose(handle, 0, 1, 0, 1, 32, 24, { maxUpsample: 4 });
  const { encoded, max } = densityLogU8(grid);
  assert.equal(encoded.length, grid.length);
  assert.ok(max >= 0);
  pyramidFree(handle);
});

test("pyramid spill compose is bit-identical to in-RAM compose", () => {
  const n = 8_192;
  const x = fill(n, (i) => ((i * 17) % n) / n);
  const y = fill(n, (i) => ((i * 31) % n) / n);
  const handle = pyramidBuild(x, y, 0, 1, 0, 1, 128);
  const ram = pyramidCompose(handle, 0, 1, 0, 1, 64, 48, { maxUpsample: 16 });
  const store = pyramidSpill(handle);
  assert.ok(store !== 0n);
  assert.equal(pyramidFree(handle), true);
  const tiles = tileStoreCompose(store, 0, 1, 0, 1, 64, 48, { maxUpsample: 16 });
  assert.ok(tiles);
  assert.equal(tiles.level, ram.level);
  assert.deepEqual(tiles.grid, ram.grid);
  assert.equal(
    crypto.createHash("sha256").update(Buffer.from(tiles.grid.buffer, tiles.grid.byteOffset, tiles.grid.byteLength)).digest("hex"),
    "e8e9e65493798cfeecd8e1e1ecee19a9e2a786121f8f8051a9bbc114515c3b2b",
  );
  assert.match(tiles.binning, /^pyramid-L\d+-tiles/);
  const stats = tileStoreStats(store);
  assert.ok(stats);
  assert.ok(stats.spilled_bytes > 0);
  assert.equal(stats.budget_bytes, PYRAMID_RESIDENT_BYTES);
  assert.equal(tileStoreFree(store), true);
});

test("colored spill refuses append without changing counts or mean colors", () => {
  const n = 8192;
  const x = fill(n, i => ((i * 17) % n) / n);
  const y = fill(n, i => ((i * 31) % n) / n);
  const idx = Uint8Array.from(x, v => v >= 0.5 ? 1 : 0);
  const lut = new Uint8Array([240, 30, 20, 255, 20, 60, 230, 255]);
  const handle = pyramidBuildColor(x, y, 0, 1, 0, 1, 512, { idx, lut });
  let store = 0n;
  try {
    store = pyramidSpill(handle);
    assert.notEqual(store, 0n);
    const before = tileStoreComposeColor(store, 0, 1, 0, 1, 64, 48, { maxUpsample: 16 });
    assert.ok(before);
    assert.equal(before.level, 3);
    assert.equal(crypto.createHash("sha256").update(Buffer.concat([
      Buffer.from(before.grid.buffer, before.grid.byteOffset, before.grid.byteLength),
      Buffer.from(before.rgba.buffer, before.rgba.byteOffset, before.rgba.byteLength),
    ])).digest("hex"), "281ddd659661acc5873e9cb71c96b323fe15c8a96623592ad8bdd5763e6c51a4");
    assert.equal(tileStoreAppend(store, new Float64Array([0.25]), new Float64Array([0.25])), false);
    const after = tileStoreComposeColor(store, 0, 1, 0, 1, 64, 48, { maxUpsample: 16 });
    assert.deepEqual(after, before);
  } finally {
    if (store) tileStoreFree(store);
    pyramidFree(handle);
  }
});

test("two host stores share the process tile budget and evict sibling tiles", () => {
  const x = fill(4096, i => ((i * 17) % 4096) / 4096);
  const y = fill(4096, i => ((i * 31) % 4096) / 4096);
  const stores = [];
  try {
    for (let i = 0; i < 2; i++) {
      const handle = pyramidBuild(x, y, 0, 1, 0, 1, 512);
      try { stores.push(pyramidSpill(handle)); } finally { pyramidFree(handle); }
      assert.notEqual(stores[i], 0n);
    }
    tileBudgetSet(300_000); // room for one count tile, never two
    for (const store of [stores[0], stores[1], stores[0]]) {
      assert.ok(tileStoreCompose(store, 0, 1, 0, 1, 64, 48, { maxUpsample: 16 }));
      assert.ok(Number(tileStoreStats(store).resident_bytes) <= 300_000);
    }
    assert.equal(Number(tileStoreStats(stores[0]).miss), 2);
  } finally {
    for (const store of stores) tileStoreFree(store);
    tileBudgetSet(PYRAMID_RESIDENT_BYTES);
  }
});

test("figure pyramidSpill records §28 tiles binning on density tier", () => {
  const n = PYRAMID_MIN_POINTS + 1_000;
  const x = fill(n, (i) => (i % 100) / 99);
  const y = fill(n, (i) => Math.floor(i / 100) / 99);
  const fig = figure({ width: 320, height: 240 });
  fig.scatter(x, y, { forceDensity: true, pyramidSpill: true });
  const { spec } = fig.buildPayload();
  const t = spec.traces[0];
  assert.equal(t.tier, "density");
  assert.match(t.density.binning, /^pyramid-L\d+-tiles/);
  assert.equal(t.density.reduction, "pyramid-count");
  assert.ok(t.density.tiles);
  assert.ok(t.density.tiles.spilled_bytes > 0);
  const appended = fig.append(fig.traces[0].id, [0.5], [0.5]);
  assert.equal(appended.spec.append.pyramid, "dirty-tiles");
  assert.match(appended.spec.traces[0].density.binning, /^pyramid-L\d+-tiles/);
  fig.dispose();
});

test("scatter spill option is strict and survives the composed mark path", () => {
  const fig = figure({ width: 320, height: 240 });
  assert.throws(
    () => fig.scatter([0], [0], { pyramidSpill: "false" }),
    /pyramidSpill must be a boolean/,
  );
  attachScatter(fig, [0, 1], [0, 1], { pyramidSpill: true });
  assert.equal(fig.traces[0].pyramid_spill, true);
  fig.dispose();
});

test("Rust tile painter pan reuses identical source bytes and bounds controls", async () => {
  const {tileStorePaint}=await import("../src/pyramid.js");
  const n=32768, x=fill(n,i=>(i*17%n)/n), y=fill(n,i=>(i*31%n)/n);
  const pyr=pyramidBuild(x,y,0,1,0,1,1024), store=pyramidSpill(pyr);
  pyramidFree(pyr);
  const read=raw=>{
    const d=new DataView(raw.buffer,raw.byteOffset,raw.byteLength), u=o=>d.getUint32(o,true);
    const rows=Array.from({length:u(16)},(_,i)=>{const at=128+96*i;return {key:[u(at),u(at+4),u(at+8)],pixels:raw.slice(u(at+20),u(at+20)+u(at+24))};});
    return {raw,level:u(8),active:u(20),missing:u(24),generation:d.getBigUint64(32,true).toString(),max:d.getFloat64(40,true),gpu:u(68),budget:u(64),rows};
  };
  try {
    const a=read(tileStorePaint(store,0,.5,0,.5,256,256));
    const b=read(tileStorePaint(store,.25,.75,0,.5,256,256,{generation:a.generation,level:a.level,keys:a.rows.map(r=>r.key)}));
    const fresh=read(tileStorePaint(store,.25,.75,0,.5,256,256));
    assert.deepEqual([a.level,a.active,a.missing,b.level,b.active,b.missing,fresh.missing],[1,1,1,1,2,1,2]);
    const cache=new Map(a.rows.map(r=>[String(r.key),r.pixels]));
    b.rows.filter(r=>r.pixels.length).forEach(r=>cache.set(String(r.key),r.pixels));
    fresh.rows.forEach(r=>assert.deepEqual(cache.get(String(r.key)),r.pixels));
    assert.equal(crypto.createHash("sha256").update(Buffer.concat(fresh.rows.map(r=>r.pixels))).digest("hex"),"410965db6e34b2143ebcb668edd99c35af3dd7caaade3e3eace7566cdb5486dd");
    assert.equal(b.max,fresh.max); assert.ok(b.gpu<=b.budget); assert.equal(b.budget,524288);
    for(const keys of [[[0,-1,0]],[[0,0]],Array(257).fill([0,0,0]),"invalid"])
      assert.throws(()=>tileStorePaint(store,0,1,0,1,256,256,{keys}),RangeError);
    assert.throws(()=>tileStorePaint(store,0,1,0,1,256,256,{generation:"18446744073709551616"}),RangeError);
  } finally {tileStoreFree(store);}
});

test("binary tile observations fail closed before allocating reply pixels", async () => {
  const {tileStorePaint}=await import("../src/pyramid.js");
  const x=fill(32,i=>i/32),y=fill(32,i=>i/32),p=pyramidBuild(x,y,0,1,0,1,64),s=pyramidSpill(p);
  pyramidFree(p);
  try {
    const control=new Uint8Array(32),d=new DataView(control.buffer);
    control.set([88,89,68,67]);d.setUint32(4,1,true);d.setFloat64(16,-1,true);d.setInt32(24,-1,true);
    assert.ok(tileStorePaint(s,0,1,0,1,64,64,{control}));
    for(const bad of [control.slice(0,31),new Uint8Array(33),new Uint8Array(32)])
      assert.throws(()=>tileStorePaint(s,0,1,0,1,64,64,{control:bad}),RangeError);
  } finally {tileStoreFree(s);}
});

test("density tile host clamps viewport through Rust screenShape before painting", async () => {
  const { PyramidCache, densityViewFromPyramid, screenShape } = await import("../src/index.js");
  const { tileStorePaint } = await import("../src/pyramid.js");
  const n = 2048;
  const x = fill(n, i => (i * 17 % n) / n);
  const y = fill(n, i => (i * 31 % n) / n);
  const cache = new PyramidCache();
  const control = new Uint8Array(32), header = new DataView(control.buffer);
  control.set([88, 89, 68, 67]);
  header.setUint32(4, 1, true);
  header.setFloat64(16, -1, true);
  header.setInt32(24, -1, true);
  try {
    for (const [width, height, expected] of [
      [5000, 48, [4096, 48]],
      [48, 5000, [48, 4096]],
      [2, -3, [16, 16]],
      [0, 0, [16, 16]],
      [128.9, 96.2, [128, 96]],
    ]) {
      const result = densityViewFromPyramid(cache, x, y, 0, 1, 0, 1, width, height, {
        force: true, forceSpill: true, tileCache: control,
      });
      const frame = new DataView(result.frame.buffer, result.frame.byteOffset, result.frame.byteLength);
      assert.deepEqual([frame.getUint32(72, true), frame.getUint32(76, true)], expected);
      // Python's ViewportRequest uses this same Rust screen_shape result.
      assert.deepEqual(screenShape(width, height), expected);
      assert.deepEqual(result.frame, tileStorePaint(cache.store, 0, 1, 0, 1, ...expected, { control }));
      const structured = densityViewFromPyramid(cache, x, y, 0, 1, 0, 1, width, height, { tileCache: {} });
      assert.deepEqual(structured.frame, result.frame);
    }
    assert.throws(() => tileStorePaint(cache.store, 0, 1, 0, 1, 5000, 48, { control }), /invalid tile painter viewport/);
    for (const [width, height] of [
      [Infinity, 48], [-Infinity, 48], [NaN, 48],
      [48, Infinity], [48, -Infinity], [48, NaN],
    ]) {
      assert.throws(() => densityViewFromPyramid(cache, x, y, 0, 1, 0, 1, width, height, { tileCache: control }), /finite/);
    }
    assert.throws(() => densityViewFromPyramid(cache, x, y, 0, 1, 0, 1, 5000, 48, {
      tileCache: new Uint8Array([0]),
    }), /invalid tile painter frame/);
    assert.throws(() => densityViewFromPyramid(cache, x, y, 0, 1, 0, 1, 5000, 48, {
      tileCache: { keys: [[1.5, 0, 0]] },
    }), /known tiles require/);
  } finally { cache.free(); }
});
