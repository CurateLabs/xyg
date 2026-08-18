/**
 * Canonical stream store (`xyg_stream_*`) + Node Figure.append.
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  Column,
  figure,
  pyramidAppendFromStream,
  pyramidBuildFromStream,
  pyramidCount,
  pyramidFree,
  xyStreamAppend,
  xyStreamCopy,
  xyStreamFree,
  xyStreamLen,
  xyStreamNew,
  xyStreamSeal,
} from "../src/index.js";
import { f64Ptr } from "../src/encode.js";

test("stream new/append/seal/copy/free and stale handle", () => {
  const seed = new Float64Array([1, 2, 3]);
  const h = xyStreamNew(f64Ptr(seed), BigInt(seed.length));
  assert.notEqual(h, 0n);
  const tail = new Float64Array([4, 5]);
  assert.equal(xyStreamAppend(h, f64Ptr(tail), BigInt(tail.length)), 1);
  assert.equal(xyStreamSeal(h), 1);
  assert.equal(Number(xyStreamLen(h)), 5);
  const out = new Float64Array(5);
  assert.equal(xyStreamCopy(h, f64Ptr(out), 5n), 1);
  assert.deepEqual([...out], [1, 2, 3, 4, 5]);
  assert.equal(xyStreamFree(h), 1);
  assert.equal(xyStreamFree(h), 0);
});

test("Column.append migrates onto the stream handle", () => {
  const col = new Column([0, 1, 2]);
  col.append([3, 4]);
  assert.notEqual(col._stream, 0n);
  assert.deepEqual([...col.values], [0, 1, 2, 3, 4]);
  assert.ok(col.capacityValues >= col.length);
  col.freeStream();
});

test("Figure.append uses the stream ABI and keeps payload prefixes", () => {
  const fig = figure({ width: 320, height: 240 });
  fig.scatter([0, 1, 2, 3, 4], [0, 1, 2, 3, 4]);
  const first = fig.buildPayload({ split: true });
  const second = fig.append(fig.traces[0].id, [5], [5]);
  assert.equal(second.type, "append");
  assert.equal(second.spec.append.seq, 1);
  assert.deepEqual(second.spec.append.affected, [fig.traces[0].id]);
  assert.equal(second.spec.append.pyramid, "none");
  assert.equal(fig.traces[0].x.length, 6);
  const x0 = first.spec.traces[0].x;
  const x1 = second.spec.traces[0].x;
  const oldBytes = first.buffers[x0];
  const newBytes = second.buffers[x1];
  assert.ok(newBytes.length > oldBytes.length);
  assert.deepEqual(newBytes.subarray(0, oldBytes.length), oldBytes);
  fig.dispose();
});

test("pyramid build/append from stream handles", () => {
  const x = new Float64Array(64);
  const y = new Float64Array(64);
  for (let i = 0; i < 64; i += 1) {
    x[i] = (i % 8) + 0.5;
    y[i] = Math.floor(i / 8) + 0.5;
  }
  const xh = xyStreamNew(f64Ptr(x), BigInt(x.length));
  const yh = xyStreamNew(f64Ptr(y), BigInt(y.length));
  const ph = pyramidBuildFromStream(xh, yh, 0, 8, 0, 8, 8);
  assert.notEqual(ph, 0n);
  assert.equal(pyramidCount(ph, 0, 8, 0, 8), 64);
  const tail = new Float64Array([1.5]);
  xyStreamAppend(xh, f64Ptr(tail), 1n);
  xyStreamAppend(yh, f64Ptr(tail), 1n);
  xyStreamSeal(xh);
  xyStreamSeal(yh);
  assert.equal(pyramidAppendFromStream(ph, xh, yh, 1), true);
  assert.equal(pyramidCount(ph, 0, 8, 0, 8), 65);
  pyramidFree(ph);
  xyStreamFree(xh);
  xyStreamFree(yh);
});
