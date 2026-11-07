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

// Exercise the exported browser coordinator against the actual packaged module.
const { XygWasmTemporalGraph, encodeWasmTemporalGraphCreate } = await import("../../xy-client/dist/index.js");
function retryBinding() {
  const nodeIds = new Uint8Array(4096 * 16), edgeIds = new Uint8Array(80 * 16);
  const sourceIds = new Uint8Array(80 * 16), targetIds = new Uint8Array(80 * 16);
  const nodes = new DataView(nodeIds.buffer), edges = new DataView(edgeIds.buffer);
  for (let i = 0; i < 4096; i++) nodes.setUint32(i * 16, i + 1, true);
  for (let i = 0; i < 80; i++) {
    edges.setUint32(i * 16, i + 5000, true);
    sourceIds.set(nodeIds.subarray(0, 16), i * 16);
    targetIds.set(nodeIds.subarray(16, 32), i * 16);
  }
  return { nodeIds, edgeIds, sourceIds, targetIds,
    edgeValidFrom: { values: new BigInt64Array(80).fill(10n), validity: new Uint8Array(80).fill(1) } };
}
test("public coordinator retries rejected input and packaged WASM output at the same revision", async () => {
  const binding = retryBinding();
  const { instance: { exports: x } } = await WebAssembly.instantiate(fs.readFileSync(wasmPath), {});
  const cap = encodeWasmTemporalGraphCreate(binding).byteLength;
  const handle = x.xyg_wasm_instance_new(cap);
  const worker = { async temporalGraphCommand(command) {
    const { status, output } = execute(x, handle, Buffer.from(command));
    if (status) throw Object.assign(new Error(`WASM status ${status}`), { status });
    return Uint8Array.from(output).buffer;
  } };
  try {
    const graph = await XygWasmTemporalGraph.create(worker, binding);
    const options = { revision: 1n, cursor: 10n, range: [0n, 40n], budget: 100000n };
    await assert.rejects(graph.frame({ ...options, range: [10n, 10n] }), RangeError);
    await assert.rejects(graph.frame(options), error => error.status === 3);
    const result = await graph.frame({ ...options, cursor: 0n });
    assert.equal(result.revision, 1n);
    assert.equal(result.visibleNodeIds.length, 4096 * 16);
    assert.equal(result.visibleEdgeIds.length, 0);
    await assert.rejects(graph.frame(options), RangeError);
    graph.dispose();
  } finally { assert.equal(x.xyg_wasm_instance_dispose(handle), 0); }
});

test("submitted revision is immutable while actual WASM reply delivery is delayed", async () => {
  const { instance: { exports: x } } = await WebAssembly.instantiate(fs.readFileSync(wasmPath), {});
  const handle = x.xyg_wasm_instance_new(1024);
  let release, hold = true;
  const worker = { async temporalGraphCommand(command) {
    const { status, output } = execute(x, handle, Buffer.from(command));
    if (status) throw Object.assign(new Error(`WASM status ${status}`), { status });
    const reply = Uint8Array.from(output).buffer;
    if (hold && new DataView(command).getUint32(12, true) === 2) {
      hold = false;
      return new Promise(resolve => { release = () => resolve(reply); });
    }
    return reply;
  } };
  const graph = await XygWasmTemporalGraph.create(worker, {
    nodeIds: ids(1, 2), edgeIds: ids(), sourceIds: ids(), targetIds: ids(),
  });
  try {
    const options = { revision: 1n, cursor: 0n, range: [0n, 40n], budget: 1000n };
    const pending = graph.frame(options);
    options.revision = 2n;
    assert.equal(typeof release, "function");
    release();
    assert.equal((await pending).revision, 1n);
    await assert.rejects(graph.frame({ ...options, revision: 1n }), RangeError);
    assert.equal((await graph.frame(options)).revision, 2n);
    let reads = 0;
    assert.equal((await graph.frame({ ...options, get revision() { reads++; return 3n; } })).revision, 3n);
    assert.equal(reads, 1);
    worker.layoutCose = (_command, options) => ({
      result: Promise.resolve({ revision: options.revision }), cancel() {},
    });
    let layoutReads = 0;
    const laidOut = await graph.frameAndLayout({
      ...options,
      get revision() { return ++layoutReads <= 2 ? 4n : 0x100000000n; },
    });
    assert.equal(layoutReads, 1);
    assert.equal(laidOut.frame.revision, 4n);
    assert.equal(laidOut.layout.revision, 4);
  } finally { graph.dispose(); assert.equal(x.xyg_wasm_instance_dispose(handle), 0); }
});

function controlledWorker() {
  const pending = [], layouts = [];
  const worker = {
    temporalGraphCommand(command) {
      if (new DataView(command).getUint32(12, true) === 1) return Promise.resolve(new ArrayBuffer(0));
      return new Promise((resolve, reject) => pending.push({ command, resolve, reject }));
    },
    layoutCose(_command, options) {
      let resolve, reject;
      const result = new Promise((yes, no) => { resolve = yes; reject = no; });
      const task = { result, cancel() { task.cancelled = true; }, cancelled: false, options, resolve, reject };
      layouts.push(task);
      return task;
    },
  };
  const reply = (index) => {
    const request = new DataView(pending[index].command), output = new ArrayBuffer(64), view = new DataView(output);
    new Uint8Array(output).set(Buffer.from("XYTF"));
    view.setUint32(4, 1, true); view.setUint32(8, 64, true);
    for (const offset of [16, 24, 32, 40]) view.setBigUint64(offset, request.getBigUint64(offset, true), true);
    pending[index].resolve(output);
  };
  return { worker, pending, layouts, reply };
}
const emptyBinding = { nodeIds: ids(), edgeIds: ids(), sourceIds: ids(), targetIds: ids() };
const request = revision => ({ revision, cursor: 0n, range: [0n, 1n], budget: 100n });

test("duplicates, late errors and superseded replies cannot reopen older revisions", async () => {
  const c = controlledWorker(), graph = await XygWasmTemporalGraph.create(c.worker, emptyBinding);
  const older = graph.frame(request(1n));
  const olderFailure = assert.rejects(older, /old failure/);
  await assert.rejects(graph.frame(request(1n)), RangeError);
  const newer = graph.frame(request(2n));
  const newerFailure = assert.rejects(newer, /new failure/);
  c.pending[1].reject(new Error("new failure")); await newerFailure;
  const retry = graph.frame(request(2n));
  c.pending[0].reject(new Error("old failure")); await olderFailure;
  await assert.rejects(graph.frame(request(1n)), RangeError);
  await assert.rejects(graph.frame(request(2n)), RangeError);
  c.reply(2); assert.equal((await retry).revision, 2n);
  await assert.rejects(graph.frame(request(2n)), RangeError);
  const stale = graph.frame(request(3n));
  const staleFailure = assert.rejects(stale, /stale/);
  const latest = graph.frame(request(4n));
  c.reply(3); await staleFailure;
  c.reply(4); assert.equal((await latest).revision, 4n);
  graph.dispose();
});

test("invalid requests preserve running layout and layout failure consumes the valid frame", async () => {
  const c = controlledWorker(), graph = await XygWasmTemporalGraph.create(c.worker, emptyBinding);
  let updates = 0;
  const running = graph.frameAndLayout({ ...request(1n), onUpdate: () => updates++ });
  const failed = assert.rejects(running, /layout failed/);
  c.reply(0); await new Promise(resolve => setImmediate(resolve));
  await assert.rejects(graph.frame({ ...request(2n), range: [0n, 0n] }), RangeError);
  await assert.rejects(graph.frameAndLayout(request(0x100000000n)), RangeError);
  await assert.rejects(graph.frame({ ...request(2n), cursor: 0x8000000000000000n, range: [0n, 0x8000000000000001n] }), RangeError);
  assert.equal(c.layouts[0].cancelled, false);
  c.layouts[0].options.onUpdate({ revision: 1 }); assert.equal(updates, 1);
  c.layouts[0].reject(new Error("layout failed")); await failed;
  await assert.rejects(graph.frame(request(1n)), RangeError);
  const next = graph.frame(request(2n)); c.reply(1); assert.equal((await next).revision, 2n);
  graph.dispose();
});

test("disposal rejects late frames and suppresses layout callbacks", async () => {
  const c = controlledWorker(), graph = await XygWasmTemporalGraph.create(c.worker, emptyBinding);
  let updates = 0;
  const running = graph.frameAndLayout({ ...request(1n), onUpdate: () => updates++ });
  const failed = assert.rejects(running, /stale/);
  c.reply(0); await new Promise(resolve => setImmediate(resolve));
  graph.dispose(); c.layouts[0].options.onUpdate({ revision: 1 });
  c.layouts[0].resolve({ revision: 1 }); await failed;
  assert.equal(updates, 0); assert.equal(c.layouts[0].cancelled, true);
  await assert.rejects(graph.frame(request(2n)), /disposed/);
  const d = controlledWorker(), other = await XygWasmTemporalGraph.create(d.worker, emptyBinding);
  const late = other.frame(request(1n)), rejected = assert.rejects(late, /stale/);
  other.dispose(); d.reply(0); await rejected;
});

test("failed supersession and retry never revive earlier layout callbacks", async () => {
  const c = controlledWorker(), graph = await XygWasmTemporalGraph.create(c.worker, emptyBinding);
  let updates = 0;
  const running = graph.frameAndLayout({ ...request(1n), onUpdate: () => updates++ });
  const rejectedLayout = assert.rejects(running, /stale/);
  c.reply(0); await new Promise(resolve => setImmediate(resolve));
  const failure = graph.frame(request(2n)), rejectedFrame = assert.rejects(failure, /transport failed/);
  c.pending[1].reject(new Error("transport failed")); await rejectedFrame;
  c.layouts[0].options.onUpdate({ revision: 1 });
  const retry = graph.frame(request(2n));
  c.layouts[0].options.onUpdate({ revision: 1 });
  c.layouts[0].resolve({ revision: 1 }); await rejectedLayout;
  c.reply(2); assert.equal((await retry).revision, 2n);
  assert.equal(updates, 0); assert.equal(c.layouts[0].cancelled, true);
  graph.dispose();
});
