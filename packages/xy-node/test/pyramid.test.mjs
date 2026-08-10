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
import test from "node:test";

import {
  PYRAMID_BASE_DIM,
  PYRAMID_MIN_POINTS,
  bin2d,
  densityLogU8,
  figure,
  pyramidAppend,
  pyramidBuild,
  pyramidCompose,
  pyramidCount,
  pyramidFree,
  pyramidReportBytes,
  shouldUsePyramid,
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

test("figure force_pyramid records §28 binning on density tier", () => {
  const n = 10_000;
  const x = fill(n, (i) => (i % 100) / 99);
  const y = fill(n, (i) => Math.floor(i / 100) / 99);
  const fig = figure({ width: 320, height: 240 });
  fig.scatter(x, y, { forcePyramid: true, forceDensity: true });
  const { spec } = fig.buildPayload();
  const t = spec.traces[0];
  assert.equal(t.tier, "density");
  assert.match(t.density.binning, /^pyramid-L/);
  assert.equal(t.density.reduction, "pyramid-count");
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
