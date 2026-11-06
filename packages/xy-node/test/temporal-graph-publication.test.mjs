import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { TemporalGraph } from "../src/index.js";

const wasmPath = process.env.XYG_SESSION_WASM ?? new URL("../../xy-client/dist/xyg-wasm.wasm", import.meta.url);
const ids = (...values) => Buffer.from(values.flatMap(value => Array(16).fill(value)));
function create(binding) {
  const planes = [binding.nodeValidFrom, binding.nodeValidTo];
  const header = Buffer.alloc(32);
  header.write("XYTG");
  [1, 32, 1, planes.every(Boolean) ? 3 : 0, binding.nodeIds.length / 16, binding.edgeIds.length / 16, 0]
    .forEach((value, i) => header.writeUInt32LE(value, 4 + i * 4));
  return Buffer.concat([header, binding.nodeIds, binding.edgeIds, binding.sourceIds, binding.targetIds,
    ...planes.filter(Boolean).flatMap(plane => [Buffer.from(plane.values.buffer), plane.validity])]);
}
function frame(revision, cursor = 0n) {
  const bytes = Buffer.alloc(56); bytes.write("XYTG");
  [1, 56, 2].forEach((value, i) => bytes.writeUInt32LE(value, 4 + i * 4));
  [revision, cursor, 0n, 40n, 100000n].forEach((value, i) => bytes.writeBigInt64LE(value, 16 + i * 8));
  return bytes;
}
function execute(x, handle, bytes) {
  assert.equal(x.xyg_wasm_arena_resize(handle, bytes.length), 0);
  new Uint8Array(x.memory.buffer, x.xyg_wasm_arena_ptr(handle), bytes.length).set(bytes);
  const status = x.xyg_wasm_temporal_graph_execute(handle, 0, bytes.length);
  const output = Buffer.from(new Uint8Array(x.memory.buffer, x.xyg_wasm_output_ptr(handle), x.xyg_wasm_output_len(handle)));
  return { status, output };
}

test("real wasm32 output rejection leaves the revision retryable", async () => {
  const { instance: { exports: x } } = await WebAssembly.instantiate(fs.readFileSync(wasmPath), {});
  const nodes = Buffer.alloc(4096 * 16);
  for (let i = 0; i < 4096; i++) nodes.writeUInt32LE(i + 1, i * 16);
  const command = create({ nodeIds: nodes, edgeIds: ids(), sourceIds: ids(), targetIds: ids() });
  const handle = x.xyg_wasm_instance_new(command.length);
  assert.ok(handle);
  try {
    assert.equal(execute(x, handle, command).status, 0);
    // Repeated resource failures must remain resource failures, never stale.
    for (const revision of [1n, 1n, 2n, 1n]) {
      const result = execute(x, handle, frame(revision));
      assert.equal(result.status, 3);
      assert.equal(result.output.length, 0);
    }
  } finally { assert.equal(x.xyg_wasm_instance_dispose(handle), 0); }
});

test("real native and wasm32 half-open frames keep identical membership bytes", async () => {
  const { instance: { exports: x } } = await WebAssembly.instantiate(fs.readFileSync(wasmPath), {});
  const binding = {
    nodeIds: ids(1, 2, 3), edgeIds: ids(11, 12), sourceIds: ids(1, 2), targetIds: ids(2, 3),
    nodeValidFrom: { values: new BigInt64Array([0n, 10n, 20n]), validity: Buffer.from([1, 1, 1]) },
    nodeValidTo: { values: new BigInt64Array([30n, 20n, 40n]), validity: Buffer.from([1, 1, 1]) },
  };
  const native = new TemporalGraph(binding);
  const handle = x.xyg_wasm_instance_new(1024 * 1024);
  try {
    assert.equal(execute(x, handle, create(binding)).status, 0);
    let revision = 0n;
    for (const cursor of [0n, 9n, 10n, 19n, 20n, 29n, 30n, 39n]) {
      const expected = native.frame({ revision: ++revision, cursor, range: [0n, 40n] });
      const { status, output } = execute(x, handle, frame(revision, cursor));
      assert.equal(status, 0);
      assert.equal(output.readBigUInt64LE(16), revision);
      assert.equal(output.readBigInt64LE(24), cursor);
      const membership = Buffer.concat([expected.nodeVisibility, expected.edgeVisibility, expected.visibleNodeIds, expected.visibleEdgeIds]);
      assert.deepEqual(output.subarray(64, 64 + membership.length), membership);
      // This chain's only visible edge is always remapped to dense 0 -> 1.
      const topology = output.subarray(64 + membership.length);
      assert.deepEqual([...new BigUint64Array(Uint8Array.from(topology).buffer)], expected.visibleEdgeIds.length ? [0n, 1n] : []);
    }
  } finally { native.close(); assert.equal(x.xyg_wasm_instance_dispose(handle), 0); }
});
