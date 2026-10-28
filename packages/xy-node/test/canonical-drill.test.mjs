import assert from "node:assert/strict";
import test from "node:test";
import { canonicalDrillAdmit, canonicalDrillEstimate, canonicalDrillQuery, drillDecision, tilePaintControlValid } from "../src/encode.js";

function query(x, window = [0, 1, 0, 1], inDrill = false) {
  const lo = new Float64Array([0]), hi = new Float64Array([1]);
  return canonicalDrillQuery(x, x, lo, hi, lo, hi, window, { chunkSize: x.length || 1, inDrill });
}

test("capped canonical row query retains f64 identity, ascending IDs, endpoints and nulls", () => {
  const x = new Float64Array([1e12, 1e12 + 0.001, NaN, 1e12 + 0.003, 2e12, Infinity]);
  const y = new Float64Array([0, 1, 2, 3, 100, 101]);
  const xmin = new Float64Array([1e12, 1e12 + 0.003, 2e12]);
  const xmax = new Float64Array([1e12 + 0.001, 1e12 + 0.003, 2e12]);
  const ymin = new Float64Array([0, 2, 100]), ymax = new Float64Array([1, 3, 101]);
  const result = canonicalDrillQuery(x, y, xmin, xmax, ymin, ymax, [1e12, 1e12 + 0.003, 0, 3], { chunkSize: 2 });
  assert.deepEqual([...result.indices], [0, 1, 3]);
  assert.equal(result.status, "complete"); assert.equal(result.count, 3);
  assert.equal(result.candidate_rows, 4); assert.equal(result.candidate_chunks, 2);
  assert.equal(result.rows_read, 4); assert.equal(result.read_bytes, 64);
  assert.equal(result.point_cap, 200000); assert.equal(result.scan_row_budget, 80000000);
  const empty = canonicalDrillQuery(new Float64Array(), new Float64Array(), ...Array.from({length: 4}, () => new Float64Array()), [0, 1, 0, 1]);
  assert.equal(empty.count, 0); assert.equal(empty.rows_read, 0);
});

test("entry and hysteresis output overflow never publishes a partial count or prefix", () => {
  const x = new Float64Array(240000);
  for (const inDrill of [false, true]) {
    const result = query(x, [0, 1, 0, 1], inDrill);
    assert.equal(result.status, "overflow"); assert.equal(result.count, null); assert.equal(result.indices.length, 0);
    assert.equal(result.rows_read, result.point_cap + 1);
    assert.equal(drillDecision(result.point_cap, 200000, { inDrill }).exact, true);
    assert.equal(drillDecision(result.point_cap + 1, 200000, { inDrill }).exact, false);
    const complete = query(x.subarray(0, result.point_cap), [0, 1, 0, 1], inDrill);
    assert.equal(complete.count, result.point_cap);
    assert.equal(complete.indices.at(-1), result.point_cap - 1);
  }
});

test("Rust admission and clipped area estimate do not certify an exact count", () => {
  const estimate = canonicalDrillEstimate(2000000, [0, 100, 0, 100], [0, 10, 0, 10]);
  assert.equal(estimate, 20000); assert.equal(canonicalDrillAdmit(estimate), true);
  assert.equal(canonicalDrillAdmit(2000000), false);
  assert.equal(canonicalDrillAdmit(2000000, { refinement: true }), true);
  assert.equal(canonicalDrillAdmit(-1), false);
  assert.throws(() => canonicalDrillAdmit(NaN));
  assert.throws(() => query(new Float64Array([0]), [NaN, 1, 0, 1]));
});

test("XYDC malformed controls rejected without store access", () => {
  const bytes = new Uint8Array(32), view = new DataView(bytes.buffer);
  bytes.set(new TextEncoder().encode("XYDC")); view.setUint32(4, 1, true);
  view.setFloat64(16, 0.5, true); view.setInt32(24, 2, true);
  assert.equal(tilePaintControlValid(bytes), true);
  assert.equal(tilePaintControlValid(new Uint8Array()), true);
  view.setFloat64(16, NaN, true); assert.equal(tilePaintControlValid(bytes), false);
  assert.equal(tilePaintControlValid(bytes.subarray(1)), false);
});
