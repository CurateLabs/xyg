import assert from "node:assert/strict";
import test from "node:test";

import {
  pointer,
  xyBin2dMeanColor,
  xyColormapRgba,
  xyColormapRgbaCanonical,
  xyDensityRgba,
  xyDensityRgbaLinear,
  xyHeatmapRgba,
  xyPyramidBuildColor,
  xyPyramidComposeColor,
  xyPyramidFree,
  xyPyramidSpill,
  xyRasterize,
  xyRasterizeData,
  xyRasterizePng,
  xyRasterizePngData,
  xyRasterizePngSpans,
  xyRasterizeRgb,
  xyRasterizeSpans,
  xyTileStoreComposeColor,
  xyTileStoreFree,
} from "../src/native.js";

const u8Ptr = (values) => pointer(values, "uint8_t *");
const f64Ptr = (values) => pointer(values, "double *");
const f32Ptr = (values) => pointer(values, "float *");

const CASES = [
  {
    name: "rgba",
    channels: 4,
    call: (out, capacity, w, h) => xyRasterize(null, 0n, out, capacity, w, h),
  },
  {
    name: "rgb",
    channels: 3,
    call: (out, capacity, w, h) => xyRasterizeRgb(null, 0n, out, capacity, w, h),
  },
  {
    name: "data rgba",
    channels: 4,
    call: (out, capacity, w, h) =>
      xyRasterizeData(null, 0n, null, 0n, out, capacity, w, h),
  },
  {
    name: "span rgba",
    channels: 4,
    call: (out, capacity, w, h) =>
      xyRasterizeSpans(null, 0n, null, null, 0n, out, capacity, w, h),
  },
];

for (const raster of CASES) {
  test(`${raster.name} framebuffer ABI validates capacity before writing`, () => {
    const required = 2 * 2 * raster.channels;

    const exact = new Uint8Array(required).fill(0xa5);
    assert.equal(raster.call(u8Ptr(exact), BigInt(exact.byteLength), 2n, 2n), 1);
    assert.deepEqual(
      [...exact],
      new Array(required).fill(raster.channels === 3 ? 0xff : 0),
    );

    const oversized = new Uint8Array(required + 1).fill(0xa5);
    assert.equal(raster.call(u8Ptr(oversized), BigInt(oversized.byteLength), 2n, 2n), 1);
    assert.equal(oversized[required], 0xa5);

    const short = new Uint8Array(required).fill(0xa5);
    assert.equal(raster.call(u8Ptr(short), BigInt(required - 1), 2n, 2n), 0);
    assert.deepEqual([...short], new Array(required).fill(0xa5));

    assert.equal(raster.call(null, BigInt(required), 2n, 2n), 0);
    assert.equal(raster.call(u8Ptr(short), BigInt(required), 0n, 2n), 0);
    assert.equal(raster.call(u8Ptr(short), BigInt(required), 2n, 0n), 0);
    assert.equal(raster.call(u8Ptr(short), (1n << 64n) - 1n, 1n << 63n, 2n), 0);
    const channelOverflowWidth = ((1n << 64n) - 1n) / BigInt(raster.channels) + 1n;
    assert.equal(raster.call(u8Ptr(short), (1n << 64n) - 1n, channelOverflowWidth, 1n), 0);
    const sliceLimitWidth = ((1n << 63n) - 1n) / BigInt(raster.channels) + 1n;
    assert.equal(raster.call(u8Ptr(short), 1n << 63n, sliceLimitWidth, 1n), 0);
    assert.deepEqual([...short], new Array(required).fill(0xa5));
  });
}

test("fused PNG ABIs reject impossible encoded-output slice capacities", () => {
  const canary = new Uint8Array([0xa5]);
  const impossibleCapacity = 1n << 63n;
  const sizeMax = (1n << 64n) - 1n;
  const calls = [
    (out) => xyRasterizePng(null, 0n, out, impossibleCapacity, 1n, 1n),
    (out) => xyRasterizePngData(null, 0n, null, 0n, out, impossibleCapacity, 1n, 1n),
    (out) =>
      xyRasterizePngSpans(null, 0n, null, null, 0n, out, impossibleCapacity, 1n, 1n),
  ];
  for (const call of calls) {
    assert.equal(BigInt(call(u8Ptr(canary))), sizeMax);
    assert.equal(canary[0], 0xa5);
  }
});

const RAW = new Float64Array(4);
const ENCODED = new Uint8Array(4);
const STOPS = new Uint8Array([0, 0, 0, 255, 255, 255]);
const GRID_CASES = [
  {
    name: "mean-color grid",
    call: (out, capacity, w, h) =>
      xyBin2dMeanColor(
        null,
        null,
        0n,
        null,
        null,
        null,
        0n,
        0,
        1,
        0,
        1,
        w,
        h,
        out,
        capacity,
      ),
  },
  {
    name: "colormap RGBA grid",
    call: (out, capacity, w, h) =>
      xyColormapRgba(f64Ptr(RAW), w, h, u8Ptr(STOPS), 2n, 255, out, capacity),
  },
  {
    name: "canonical colormap RGBA grid",
    call: (out, capacity, w, h) =>
      xyColormapRgbaCanonical(
        f64Ptr(RAW),
        w,
        h,
        0,
        1,
        u8Ptr(STOPS),
        2n,
        255,
        out,
        capacity,
      ),
  },
  {
    name: "heatmap RGBA grid",
    call: (out, capacity, w, h) =>
      xyHeatmapRgba(f64Ptr(RAW), w, h, u8Ptr(STOPS), 2n, 255, out, capacity),
  },
  {
    name: "density RGBA grid",
    call: (out, capacity, w, h) =>
      xyDensityRgba(u8Ptr(ENCODED), w, h, 1, u8Ptr(STOPS), 2n, 1, out, capacity),
  },
  {
    name: "linear density RGBA grid",
    call: (out, capacity, w, h) =>
      xyDensityRgbaLinear(f64Ptr(RAW), w, h, 1, u8Ptr(STOPS), 2n, 1, out, capacity),
  },
];

for (const grid of GRID_CASES) {
  test(`${grid.name} ABI validates capacity before writing`, () => {
    const required = 16;
    const exact = new Uint8Array(required).fill(0xa5);
    assert.equal(grid.call(u8Ptr(exact), BigInt(exact.byteLength), 2n, 2n), 1);

    const oversized = new Uint8Array(required + 1).fill(0xa5);
    assert.equal(grid.call(u8Ptr(oversized), BigInt(oversized.byteLength), 2n, 2n), 1);
    assert.equal(oversized[required], 0xa5);

    const short = new Uint8Array(required).fill(0xa5);
    assert.equal(grid.call(u8Ptr(short), BigInt(required - 1), 2n, 2n), 0);
    assert.deepEqual([...short], new Array(required).fill(0xa5));
    assert.equal(grid.call(null, BigInt(required), 2n, 2n), 0);
    assert.equal(grid.call(u8Ptr(short), BigInt(required), 0n, 2n), 0);
    assert.equal(grid.call(u8Ptr(short), BigInt(required), 2n, 0n), 0);
    assert.equal(grid.call(u8Ptr(short), (1n << 64n) - 1n, (1n << 64n) / 4n, 1n), 0);
    assert.equal(grid.call(u8Ptr(short), 1n << 63n, 1n << 61n, 1n), 0);
    assert.deepEqual([...short], new Array(required).fill(0xa5));
  });
}

test("colored compose ABIs validate both caller-owned outputs before writing", () => {
  const x = new Float64Array([0.25, 0.75]);
  const y = new Float64Array([0.25, 0.75]);
  const colors = new Uint8Array([255, 0, 0, 255, 0, 0, 255, 255]);
  const pyramid = BigInt(
    xyPyramidBuildColor(
      f64Ptr(x),
      f64Ptr(y),
      2n,
      null,
      u8Ptr(colors),
      null,
      0n,
      0,
      1,
      0,
      1,
      8,
    ),
  );
  assert.notEqual(pyramid, 0n);

  const exercise = (label, handle, compose) => {
    const call = (counts, countCapacity, rgba, rgbaCapacity, w = 2n, h = 2n) =>
      compose(
        handle,
        0,
        1,
        0,
        1,
        w,
        h,
        2n,
        counts,
        countCapacity,
        rgba,
        rgbaCapacity,
      );

    const exactCounts = new Float32Array(4).fill(123);
    const exactRgba = new Uint8Array(16).fill(0xa5);
    assert.ok(
      call(f32Ptr(exactCounts), 4n, u8Ptr(exactRgba), 16n) >= 0,
      `${label} accepts exact capacities`,
    );

    const oversizedCounts = new Float32Array(5).fill(123);
    const oversizedRgba = new Uint8Array(17).fill(0xa5);
    assert.ok(
      call(f32Ptr(oversizedCounts), 5n, u8Ptr(oversizedRgba), 17n) >= 0,
      `${label} accepts oversized capacities`,
    );
    assert.equal(oversizedCounts[4], 123);
    assert.equal(oversizedRgba[16], 0xa5);

    for (const [countCapacity, rgbaCapacity] of [
      [3n, 16n],
      [4n, 15n],
    ]) {
      const guardedCounts = new Float32Array(4).fill(123);
      const guardedRgba = new Uint8Array(16).fill(0xa5);
      assert.equal(
        call(
          f32Ptr(guardedCounts),
          countCapacity,
          u8Ptr(guardedRgba),
          rgbaCapacity,
        ),
        -1,
      );
      assert.deepEqual([...guardedCounts], new Array(4).fill(123));
      assert.deepEqual([...guardedRgba], new Array(16).fill(0xa5));
    }

    const guardedCounts = new Float32Array(4).fill(123);
    const guardedRgba = new Uint8Array(16).fill(0xa5);
    assert.equal(call(null, 4n, u8Ptr(guardedRgba), 16n), -1);
    assert.equal(call(f32Ptr(guardedCounts), 4n, null, 16n), -1);
    assert.equal(call(f32Ptr(guardedCounts), 4n, u8Ptr(guardedRgba), 16n, 0n, 2n), -1);
    assert.equal(
      call(
        f32Ptr(guardedCounts),
        (1n << 64n) - 1n,
        u8Ptr(guardedRgba),
        (1n << 64n) - 1n,
        1n << 62n,
        1n,
      ),
      -1,
    );
    assert.equal(
      call(
        f32Ptr(guardedCounts),
        1n << 63n,
        u8Ptr(guardedRgba),
        1n << 63n,
        1n << 61n,
        1n,
      ),
      -1,
    );
    assert.deepEqual([...guardedCounts], new Array(4).fill(123));
    assert.deepEqual([...guardedRgba], new Array(16).fill(0xa5));
  };

  try {
    exercise("in-memory colored compose", pyramid, xyPyramidComposeColor);
    const store = BigInt(xyPyramidSpill(pyramid));
    assert.notEqual(store, 0n);
    try {
      exercise("tile-store colored compose", store, xyTileStoreComposeColor);
    } finally {
      assert.equal(xyTileStoreFree(store), 1);
    }
  } finally {
    assert.equal(xyPyramidFree(pyramid), 1);
  }
});
