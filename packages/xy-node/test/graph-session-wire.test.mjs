// Actual C ABI / wasm32 byte replay. XYG_SESSION_WASM selects a diagnostic
// module explicitly; passing that module never establishes shipping acceptance.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import test from "node:test";
import * as native from "../src/native.js";
import { composeGraphForgeRequest, encodeGraphForgeRequest } from "../src/graphforge.js";
import { DTYPE, decodeContainer, encodeContainer } from "../src/graphforge-container.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const WASM = process.env.XYG_SESSION_WASM
  ? path.resolve(process.env.XYG_SESSION_WASM)
  : path.join(ROOT, "packages/xy-client/dist/xyg-wasm.wasm");
const field = (name, dtype, values) => ({ name, dtype: DTYPE[dtype], values });
const value = (bytes, name, magic = "XYGR") => decodeContainer(bytes, magic).get(`${name}#0`)?.value;
const ptr = (bytes) => native.pointer(bytes, "uint8_t *");

function equalBytes(actual, expected, label) {
  const left = Buffer.from(actual);
  const right = Buffer.from(expected);
  let differences = "";
  if (!left.equals(right)) {
    const a = decodeContainer(actual, "XYGR");
    const b = decodeContainer(expected, "XYGR");
    const json = (v) => JSON.stringify(v, (_, x) => typeof x === "bigint" ? `${x}n` : x);
    differences = [...new Set([...a.keys(), ...b.keys()])]
      .filter((key) => json(a.get(key)?.value) !== json(b.get(key)?.value))
      .map((key) => `${key}: WASM=${json(a.get(key)?.value)} native=${json(b.get(key)?.value)}`).join("; ");
  }
  assert.equal(Buffer.compare(left, right), 0, `${label}${differences ? `: ${differences}` : ""}`);
}

function request(instance, group, sequence, revision, operation, sections = [], words = {}) {
  const header = [revision, operation, 0, 0, 0, 0, 0, 0, 0];
  for (const [index, number] of Object.entries(words)) header[Number(index)] = number;
  return encodeContainer("XYGI", [
    field("header.u64", "u64", [instance, group, BigInt(sequence)]),
    field("header.u32", "u32", header),
    ...sections,
  ]);
}

function refs(elements) {
  const pool = [];
  const out = new Uint8Array(8 + elements.length * 56 + elements.reduce((n, e) => n + (e.result == null ? 0 : Buffer.byteLength(e.result)), 0));
  const view = new DataView(out.buffer);
  view.setUint32(0, elements.length, true);
  elements.forEach((element, i) => {
    const at = 8 + i * 56;
    view.setUint32(at, element.kind, true);
    if (element.uuid) out.set(element.uuid, at + 8);
    if (element.kind === 2) {
      view.setUint32(at + 24, element.layer, true);
      view.setBigUint64(at + 32, element.path, true);
      view.setBigUint64(at + 40, element.order, true);
      view.setUint32(at + 48, element.result == null ? 0xffffffff : pool.length, true);
      if (element.result != null) {
        const bytes = Buffer.from(element.result);
        view.setUint32(at + 52, bytes.length, true);
        pool.push(...bytes);
      }
    }
  });
  view.setUint32(4, pool.length, true);
  out.set(pool, 8 + elements.length * 56);
  return out;
}

function fixture() {
  const arrow = (name) => fs.readFileSync(path.join(ROOT, `tests/fixtures/graphforge/results/${name}.arrow`));
  const input = encodeGraphForgeRequest({
    base: { tables: [arrow("base-cyclic-nodes"), arrow("base-cyclic-edges")] },
    layers: [
      { result: arrow("pagerank"), intent: "graph", resultId: "rank:exact" },
      { result: arrow("node_similarity"), intent: "graph", resultId: "pair:exact" },
      { result: arrow("dijkstra"), intent: "graph", resultId: "path:exact" },
    ],
  });
  const sections = decodeContainer(composeGraphForgeRequest(input), "XYGF");
  const nodes = sections.get("node.uuid#0").value;
  const edges = sections.get("edge.uuid#0").value;
  const persisted = sections.get("edge.derived#0").value.findIndex((v) => v === 0);
  assert.ok(persisted >= 0);
  // Kind-qualified identity is legal even when one real fixture node and
  // persisted edge have identical UUIDs. No topology or policy is rebuilt here.
  edges.set(nodes.subarray(0, 16), persisted * 16);
  const document = encodeContainer("XYGF", [...sections.values()].map((s) => ({ ...s, values: s.value })));
  const n = nodes.length / 16;
  const load = [
    field("document.bytes", "bytes", document),
    field("load.x.f64", "f64", Array.from({ length: n }, (_, i) => i * 30)),
    field("load.y.f64", "f64", Array(n).fill(0)),
  ];
  const derived = sections.get("edge.derived#0").value;
  const orders = sections.get("edge.order#0").value;
  const index = derived.findIndex((flag, i) => flag === 1 && orders[i] >= 0n);
  assert.ok(index >= 0, "real ordered derived edge");
  const layer = sections.get("edge.layer#0").value[index];
  const exact = {
    kind: 2, layer, path: sections.get("edge.path#0").value[index], order: orders[index],
    result: sections.get(`layer.result_id#${layer}`).value,
  };
  return { document, nodes, persisted, load, exact, exactIndex: index };
}

function withResultIds(data, replacements) {
  const sections = decodeContainer(data.document, "XYGF");
  for (const [layer, id] of Object.entries(replacements)) {
    sections.get(`layer.result_id#${layer}`).value = id;
  }
  const document = encodeContainer("XYGF", [...sections.values()].map((s) => ({ ...s, values: s.value })));
  return {
    ...data, document,
    load: data.load.map((s) => s.name === "document.bytes" ? { ...s, values: document } : s),
  };
}

function nativeCall(fn, handle, bytes, capacity) {
  const output = new Uint8Array(capacity).fill(0xa5);
  const length = new BigUint64Array(1);
  const status = fn(handle, ptr(bytes), BigInt(bytes.length), ptr(output), BigInt(capacity), native.pointer(length, "size_t *"));
  return { status, length: Number(length[0]), output };
}

function nativeComplete(fn, handle, bytes) {
  const zero = nativeCall(fn, handle, bytes, 0);
  assert.equal(zero.status, -5, "zero capacity applies once and reports required bytes");
  assert.ok(zero.length > 0);
  const short = nativeCall(fn, handle, bytes, zero.length - 1);
  assert.equal(short.status, -5);
  assert.equal(short.length, zero.length);
  assert.ok(short.output.every((v) => v === 0xa5), "short output is untouched");
  const exact = nativeCall(fn, handle, bytes, zero.length);
  assert.equal(exact.status, 0);
  assert.equal(exact.length, zero.length);
  assert.deepEqual(nativeCall(fn, handle, bytes, zero.length).output, exact.output, "serialized retry is byte-identical");
  return exact.output;
}

function wasmCall(x, handle, name, bytes) {
  assert.equal(x.xyg_wasm_arena_resize(handle, bytes.length), 0);
  new Uint8Array(x.memory.buffer, x.xyg_wasm_arena_ptr(handle) >>> 0, bytes.length).set(bytes);
  const status = x[name](handle, 0, bytes.length);
  const output = new Uint8Array(x.memory.buffer, x.xyg_wasm_output_ptr(handle) >>> 0, x.xyg_wasm_output_len(handle) >>> 0).slice();
  return { status, output };
}

function openPair(x, data, instance, group) {
  const open = request(instance, group, 1, 0, 19, data.load);
  const handle = new BigUint64Array(1);
  assert.equal(native.xyGraphforgeSessionCreate(ptr(data.document), BigInt(data.document.length), ptr(open), BigInt(open.length), instance, group, native.pointer(handle, "uint64_t *")), 0);
  const wasm = x.xyg_wasm_instance_new(128 * 1024 * 1024);
  assert.ok(wasm > 0);
  assert.equal(wasmCall(x, wasm, "xyg_wasm_graphforge_session_open", open).status, 0);
  let sequence = 1;
  let revision = 0;
  return {
    handle: handle[0], wasm, instance, group, open,
    run(operation, sections = [], words = {}) {
      const bytes = request(instance, group, ++sequence, revision, operation, sections, words);
      const fn = operation === 20 ? native.xyGraphforgeSessionUpdate
        : operation === 21 ? native.xyGraphforgeSessionRender
          : operation === 22 ? native.xyGraphforgeSessionPollEvent
            : operation === 16 ? native.xyGraphforgeCoordinateDeliver : native.xyGraphforgeSessionInteract;
      const name = operation === 20 ? "xyg_wasm_graphforge_session_update"
        : operation === 21 ? "xyg_wasm_graphforge_session_render" : "xyg_wasm_graphforge_session_interact";
      const nativeBytes = nativeComplete(fn, handle[0], bytes);
      const wasmResult = wasmCall(x, wasm, name, bytes);
      assert.equal(wasmResult.status, 0, `operation ${operation}`);
      equalBytes(wasmResult.output, nativeBytes, `operation ${operation} native/WASM bytes`);
      assert.deepEqual(wasmCall(x, wasm, name, bytes).output, nativeBytes, `operation ${operation} WASM retry bytes`);
      const header = value(nativeBytes, "header.u32");
      if (header) revision = header[0];
      return nativeBytes;
    },
    reject(operation, sections, expected, words = {}) {
      const bytes = request(instance, group, ++sequence, revision, operation, sections, words);
      assert.equal(nativeCall(native.xyGraphforgeSessionInteract, handle[0], bytes, 0).status, expected);
      assert.equal(wasmCall(x, wasm, "xyg_wasm_graphforge_session_interact", bytes).status, expected);
    },
    close() {
      assert.equal(native.xyGraphforgeSessionDestroy(handle[0]), 0);
      assert.equal(x.xyg_wasm_graphforge_session_close(wasm), 0);
      assert.equal(x.xyg_wasm_instance_dispose(wasm), 0);
    },
  };
}

test("actual native ABI and real WASM replay one GraphSession byte contract", async (t) => {
  const module = fs.readFileSync(WASM); // Missing artifact is a failure, never a skip.
  const { instance } = await WebAssembly.instantiate(module, {});
  const x = instance.exports;
  const data = fixture();
  assert.equal(data.exact.layer, 2, "path layer stays fixed while earlier IDs change");
  // The sender interns rank/pair/path separately. Reusing rank's ID for the
  // receiver's unrelated pair layer moves path's local table index from 3 to
  // 2 while preserving path's layer, topology, exact result ID and generation.
  const receiverData = withResultIds(data, { 1: "rank:exact" });
  assert.notEqual(value(data.document, "layer.result_id", "XYGF"), decodeContainer(data.document, "XYGF").get("layer.result_id#1").value);
  assert.equal(value(receiverData.document, "layer.result_id", "XYGF"), decodeContainer(receiverData.document, "XYGF").get("layer.result_id#1").value);
  const sender = openPair(x, data, 900001n, 77n);
  const receiver = openPair(x, receiverData, 900002n, 77n);
  try {
    const malformedContainer = request(sender.instance, sender.group, 2, 0, 21);
    new DataView(malformedContainer.buffer).setUint32(12, 0xffffffff, true);
    assert.equal(nativeCall(native.xyGraphforgeSessionRender, sender.handle, malformedContainer, 0).status, -3);
    assert.equal(wasmCall(x, sender.wasm, "xyg_wasm_graphforge_session_render", malformedContainer).status, -3, "wasm32 checked names/alignment refuses without a trap");
    const initial = sender.run(21);
    const selected = sender.run(10, [field("uuids.uuid", "uuid", data.nodes.subarray(0, 16))]);
    assert.equal(value(initial, "header.u32")[0], value(selected, "header.u32")[0]);
    assert.ok(value(selected, "node.flags.u32")[0] & 2);
    assert.ok(value(selected, "edge.flags.u32")[data.persisted] & 2, "shared UUID selects both kinds");
    assert.notDeepEqual(value(initial, "render.visual_states.u8"), value(selected, "render.visual_states.u8"));
    const node = refs([{ kind: 0, uuid: data.nodes.subarray(0, 16) }]);
    const focused = sender.run(6, [field("refs.bytes", "bytes", node)]);
    assert.equal(value(focused, "header.u32")[0], value(selected, "header.u32")[0]);
    assert.ok(value(focused, "render.emphasis.u8").some((v) => v & 1));
    sender.run(8, [], { 5: 1 });
    sender.run(0, [field("coordinates.f64", "f64", [0, 0])]);
    sender.run(2, [field("coordinates.f64", "f64", [-10, -10, 50, 10])]);
    sender.run(3, [field("coordinates.f64", "f64", [-10, -10, 50, -10, 50, 10, -10, 10])]);
    const highlighted = sender.run(12, [field("refs.bytes", "bytes", node)], { 4: 2 });
    assert.ok(value(highlighted, "node.flags.u32")[0] & 1024);
    assert.ok(value(highlighted, "render.emphasis.u8").some((v) => v & 8));
    sender.run(13, [field("refs.bytes", "bytes", node)], { 5: 1 });
    const moved = sender.run(14, [field("refs.bytes", "bytes", node), field("coordinates.f64", "f64", [2, 3])], { 6: 1 });
    assert.ok(value(moved, "positions.changed.bytes").length > 0);
    sender.run(15, [], { 7: 1 });
    sender.run(17, [field("companion.u32", "u32", [0, 2])]);
    sender.run(11, [field("refs.bytes", "bytes", refs([data.exact]))]);
    const derivedEvent = value(sender.run(22), "outbound.bytes");
    assert.ok(derivedEvent?.length > 0);
    const matched = receiver.run(16, [field("remote.bytes", "bytes", derivedEvent)]);
    assert.equal(value(matched, "header.u32")[2], 0, "exact result ID survives different local string-table indexes");
    assert.ok(value(matched, "edge.flags.u32")[data.exactIndex] & 2);
    const changedIdentity = withResultIds(receiverData, { 2: "path:changed" });
    const replaced = receiver.run(20, changedIdentity.load);
    assert.ok(value(replaced, "header.u32")[3] > 0, "replacement drops the old derived selection");
    assert.equal(value(replaced, "edge.flags.u32")[data.exactIndex] & 2, 0);
    sender.run(11, [field("refs.bytes", "bytes", refs([data.exact]))]);
    const changedEvent = value(sender.run(22), "outbound.bytes");
    assert.ok(value(changedEvent, "remote.u64", "XYGI")[2] > value(derivedEvent, "remote.u64", "XYGI")[2]);
    const unmatched = receiver.run(16, [field("remote.bytes", "bytes", changedEvent)]);
    assert.equal(value(unmatched, "header.u32")[2], 1, "a changed layer result ID stays unmatched");
    assert.equal(value(unmatched, "edge.flags.u32")[data.exactIndex] & 2, 0);
    sender.reject(11, [field("refs.bytes", "bytes", refs([{ ...data.exact, result: "other:exact" }]))], -3);
    sender.reject(11, [field("refs.bytes", "bytes", refs([{ ...data.exact, result: "bad id" }]))], -3);
    sender.reject(11, [field("refs.bytes", "bytes", refs([{ ...data.exact, result: "" }]))], -3);
    const malformed = refs([data.exact]);
    new DataView(malformed.buffer).setUint32(8 + 48, 1, true);
    sender.reject(11, [field("refs.bytes", "bytes", malformed)], -3);
    sender.run(20, data.load);
    sender.run(10, [field("uuids.uuid", "uuid", data.nodes.subarray(0, 16))]);
    const polled = sender.run(22);
    const event = value(polled, "outbound.bytes");
    assert.ok(event?.length > 0);
    assert.equal(value(sender.run(22), "outbound.bytes"), undefined, "poll consumes only once");
    const delivered = receiver.run(16, [field("remote.bytes", "bytes", event)]);
    assert.equal(value(delivered, "outbound.bytes"), undefined, "remote never rebroadcasts");
    assert.ok(value(delivered, "node.flags.u32")[0] & 2);
    receiver.reject(16, [field("remote.bytes", "bytes", event)], -7);
    const reopened = new BigUint64Array(1);
    assert.equal(native.xyGraphforgeSessionCreate(ptr(data.document), BigInt(data.document.length), ptr(sender.open), BigInt(sender.open.length), sender.instance, sender.group, native.pointer(reopened, "uint64_t *")), 0);
    assert.equal(reopened[0], sender.handle);
    const ack = wasmCall(x, sender.wasm, "xyg_wasm_graphforge_session_open", sender.open);
    assert.equal(ack.status, 0, "OPEN identity survives later commands");
    assert.deepEqual([...value(ack.output, "header.u32")], [0, 0, 0, 0]);
    t.diagnostic(JSON.stringify({
      node: process.version, module: WASM, bytes: module.length,
      sha256: createHash("sha256").update(module).digest("hex"),
      nativeLibrary: native.nativeLibraryPath,
      nativeSha256: createHash("sha256").update(fs.readFileSync(native.nativeLibraryPath)).digest("hex"),
      diagnosticModule: Boolean(process.env.XYG_SESSION_WASM),
    }));
  } finally {
    receiver.close();
    sender.close();
  }
});
