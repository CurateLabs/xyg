// Actual C ABI / wasm32 byte replay. XYG_SESSION_WASM selects a diagnostic
// module explicitly; passing that module never establishes shipping acceptance.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import test from "node:test";
import * as native from "../src/native.js";
import { graphProjectionCreate, graphProjectionDestroy, temporalGraphCreate, temporalGraphDestroy, temporalGraphFrame } from "../src/abi.js";
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

// Inspection oracle only: compare Rust's GPU buffers with its CPU publication.
// This code does not generate geometry or own rendering policy.
function assertGpuPublication(bytes, operation) {
  const sections = decodeContainer(bytes, "XYGR");
  if (operation === 19 || operation === 22) {
    assert.ok(![...sections.keys()].some((key) => /^(gpu\.|focus\.action\.|clear\.action\.|outcome\.|disclosure\.)/.test(key)), "control acknowledgements carry no invented publication/outcome");
    return;
  }
  const get = (name, dtype, index = 0) => {
    const section = sections.get(`${name}#${index}`);
    assert.ok(section, `required ${name}#${index}`);
    assert.equal(section.dtype, DTYPE[dtype], `${name} dtype`);
    return section.value;
  };
  const clear = get("clear.action.u32", "u32");
  assert.equal(clear.length, 2);
  assert.equal(clear[0], 1);
  assert.ok(clear[1] === 0 || clear[1] === 1, "Rust clear applicability is a versioned boolean fact");
  const header = get("gpu.header.u32", "u32");
  assert.equal(header.length, 8);
  const [version, flags, n, m, pieces, heads, frames, reserved] = header;
  assert.deepEqual([version, flags, reserved], [1, 0, 0]);
  const centers = get("paint.node.center.f64", "f64");
  const cpuPieces = get("paint.piece.geometry.f64", "f64");
  const cpuIndices = get("paint.piece.index.u64", "u64");
  const cpuFrames = get("paint.frame.geometry.f64", "f64");
  assert.equal(centers.length, n * 2);
  assert.equal(cpuPieces.length, pieces * 14);
  assert.equal(cpuIndices.length, pieces * 2);
  assert.equal(cpuFrames.length, frames * 5);
  const transforms = [0, 1, 2].map((index) => {
    const v = get("gpu.transform.f64", "f64", index);
    assert.equal(v.length, 2);
    assert.ok(v.every(Number.isFinite) && v[1] > 0);
    return v;
  });
  const column = (name, index, count) => {
    const bytes = get(name, "bytes", index);
    assert.equal(bytes.length, count * 4, `${name}#${index} count`);
    const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    return Array.from({ length: count }, (_, i) => v.getFloat32(i * 4, true));
  };
  const compare = (actual, expected, transform, label) => {
    const [offset, scale] = transform;
    assert.equal(actual.length, expected.length);
    actual.forEach((f, i) => {
      assert.ok(Number.isFinite(f), `${label} finite`);
      const encoded = (expected[i] - offset) * scale;
      const decoded = f / scale + offset;
      // IEEE binary32 nearest rounding plus binary64 reconstruction arithmetic.
      const bound = (Math.abs(encoded) * 2 ** -23 + 2 ** -149) / scale
        + 8 * Number.EPSILON * Math.max(1, Math.abs(offset), Math.abs(expected[i]));
      assert.ok(Math.abs(decoded - expected[i]) <= bound, `${label}[${i}]: ${decoded} vs ${expected[i]}, bound ${bound}`);
    });
  };
  for (let axis = 0; axis < 2; axis++) {
    compare(column("gpu.node.coord.bytes", axis, n), Array.from({ length: n }, (_, i) => centers[i * 2 + axis]), transforms[axis], `node axis ${axis}`);
  }
  for (let i = 0; i < 4; i++) {
    compare(column("gpu.shaft.coord.bytes", i, pieces), Array.from({ length: pieces }, (_, p) => cpuPieces[p * 14 + i]), transforms[i % 2], `shaft column ${i}`);
    compare(column("gpu.shaft.attr.bytes", i, pieces), Array.from({ length: pieces }, (_, p) => cpuPieces[p * 14 + 4 + i]), i === 3 ? transforms[2] : [0, 1], `shaft attribute ${i}`);
    compare(column("gpu.frame.coord.bytes", i, frames), Array.from({ length: frames }, (_, p) => cpuFrames[p * 5 + i]), transforms[i % 2], `frame column ${i}`);
  }
  compare(column("gpu.frame.width.bytes", 0, frames), Array.from({ length: frames }, (_, i) => cpuFrames[i * 5 + 4]), [0, 1], "frame width");
  const headPieces = get("gpu.head.piece.u32", "u32");
  assert.deepEqual([...headPieces], Array.from({ length: pieces }, (_, i) => i).filter((i) => (cpuIndices[i * 2 + 1] & 2n) !== 0n), "head order and piece identity");
  assert.equal(headPieces.length, heads);
  for (let i = 0; i < 6; i++) {
    compare(column("gpu.head.coord.bytes", i, heads), [...headPieces].map((p) => cpuPieces[p * 14 + 8 + i]), transforms[i % 2], `head column ${i}`);
  }
  assert.deepEqual([...get("gpu.shaft.edge.u32", "u32")], Array.from({ length: pieces }, (_, i) => Number(cpuIndices[i * 2])), "clipped pieces retain published edge identity/order");
  assert.deepEqual([...get("gpu.shaft.flags.u8", "u8")], Array.from({ length: pieces }, (_, i) => Number(cpuIndices[i * 2 + 1] & 1n)));
  assert.deepEqual([...get("gpu.frame.node.u32", "u32")], [...get("paint.frame.node.u64", "u64")].map(Number));
  for (const [kind, count] of [["node", n], ["edge", m]]) {
    const styles = get(`gpu.${kind}.style.bytes`, "bytes");
    assert.equal(styles.length, count * 60);
    assert.deepEqual(styles, get(`paint.${kind}.style.bytes`, "bytes"), `${kind} RGBA, shape, width, layers and ordering`);
    const state = get(`gpu.${kind}.state.u8`, "u8");
    const visuals = get(kind === "node" ? "render.visual_states.u8" : "render.edge_visual_states.u8", "u8");
    const emphasis = get(kind === "node" ? "render.emphasis.u8" : "render.edge_emphasis.u8", "u8");
    const offsets = get(`render.${kind}_member_offsets.u64`, "u64");
    const members = get(`render.${kind}_members.u64`, "u64");
    const sourceFlags = get(`${kind}.flags.u32`, "u32");
    assert.equal(state.length, count * 4);
    assert.equal(visuals.length, count);
    for (let i = 0; i < count; i++) {
      let memberFlags = 0;
      for (let j = Number(offsets[i]); j < Number(offsets[i + 1]); j++) memberFlags |= sourceFlags[Number(members[j])] & 0x17;
      assert.deepEqual([...state.subarray(i * 4, i * 4 + 4)], [visuals[i], emphasis[i], memberFlags, 0], `${kind} simultaneous emphasis/state bits`);
    }
  }
  const outcome = get("outcome.u32", "u32");
  assert.equal(outcome.length, 4);
  assert.equal(outcome[0], 1);
  assert.ok(outcome[1] <= 1 && outcome[3] <= 1);
  const disclosure = get("disclosure.ref.bytes", "bytes");
  assert.equal(new DataView(disclosure.buffer, disclosure.byteOffset).getUint32(0, true), outcome[3]);
  const collapsed = get("disclosure.collapsed.u8", "u8");
  assert.equal(collapsed.length, outcome[3]);
  assert.ok(collapsed.every((v) => v <= 1));
  const action = get("focus.action.u32", "u32");
  assert.equal(action.length, 8);
  assert.equal(action[0], 1);
  assert.ok([...action.subarray(1, 6)].every((v) => v <= 1));
  assert.deepEqual([...action.subarray(6)], [0, 0]);
  const target = get("focus.action.ref.bytes", "bytes");
  const tv = new DataView(target.buffer, target.byteOffset, target.byteLength);
  const targetCount = tv.getUint32(0, true);
  assert.ok(targetCount <= 1);
  if (!targetCount) assert.deepEqual([...action.subarray(1)], Array(7).fill(0));
  else {
    const kind = tv.getUint32(8, true);
    assert.ok(kind === 0 || kind === 3, "action identity is a node or exact aggregate stop");
    if (kind === 3) {
      assert.equal(get("render.tier.u32", "u32")[0], 2);
      assert.deepEqual([...action.subarray(1)], Array(7).fill(0), "aggregate UUID stand-ins cannot enable singular actions");
    }
  }
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
    if (element.kind === 3) {
      view.setUint32(at + 24, element.index, true);
      view.setUint32(at + 28, element.revision, true);
    }
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
    if(id===null) sections.delete(`layer.result_id#${layer}`);
    else if(sections.has(`layer.result_id#${layer}`)) sections.get(`layer.result_id#${layer}`).value = id;
    else sections.set(`layer.result_id#${layer}`,{name:"layer.result_id",index:Number(layer),dtype:DTYPE.utf8,value:id});
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

test("standalone temporal owners keep frame and replacement staging at the default arena", async () => {
  const { instance } = await WebAssembly.instantiate(fs.readFileSync(WASM), {});
  const x = instance.exports;
  const create = count => {
    const bytes = Buffer.alloc(32 + count * 16);
    bytes.write("XYTG");
    [1, 32, 1, 0, count, 0, 0].forEach((word, i) => bytes.writeUInt32LE(word, 4 + i * 4));
    for (let i = 0; i < count; i++) bytes.writeBigUInt64LE(BigInt(i + 1), 32 + i * 16);
    return bytes;
  };
  const frame = revision => {
    const bytes = Buffer.alloc(56);
    bytes.write("XYTG");
    [1, 56, 2].forEach((word, i) => bytes.writeUInt32LE(word, 4 + i * 4));
    bytes.writeBigUInt64LE(BigInt(revision), 16);
    bytes.writeBigUInt64LE(1n, 40);
    bytes.writeBigUInt64LE(16n * 1024n * 1024n, 48);
    return bytes;
  };
  for (const count of [32760, 40000]) {
    const handle = x.xyg_wasm_instance_new(16 * 1024 * 1024);
    assert.ok(handle > 0);
    try {
      const execute = bytes => wasmCall(x, handle, "xyg_wasm_temporal_graph_execute", bytes);
      assert.equal(execute(create(count)).status, 0);
      assert.equal(execute(frame(1)).status, 0);
      assert.equal(execute(create(2).subarray(0, 63)).status, 2);
      const retained = execute(frame(2));
      assert.equal(retained.status, 0);
      assert.equal(new DataView(retained.output.buffer).getUint32(48, true), count);
      assert.equal(execute(create(2)).status, 0);
      const replaced = execute(frame(3));
      assert.equal(replaced.status, 0);
      assert.equal(new DataView(replaced.output.buffer).getUint32(48, true), 2);
    } finally {
      assert.equal(x.xyg_wasm_instance_dispose(handle), 0);
    }
  }
});

function openPair(x, data, instance, group, budget = 128 * 1024 * 1024) {
  const open = request(instance, group, 1, 0, 19, data.load);
  const handle = new BigUint64Array(1);
  assert.equal(native.xyGraphforgeSessionCreate(ptr(data.document), BigInt(data.document.length), ptr(open), BigInt(open.length), instance, group, native.pointer(handle, "uint64_t *")), 0);
  const wasm = x.xyg_wasm_instance_new(budget);
  assert.ok(wasm > 0);
  const opened = wasmCall(x, wasm, "xyg_wasm_graphforge_session_open", open);
  assert.equal(opened.status, 0);
  assertGpuPublication(opened.output, 19);
  let sequence = 1;
  let revision = 0;
  return {
    handle: handle[0], wasm, instance, group, open,
    run(operation, sections = [], words = {}, nativeSections = sections) {
      const bytes = request(instance, group, ++sequence, revision, operation, sections, words);
      const fn = operation === 20 ? native.xyGraphforgeSessionUpdate
        : operation === 21 ? native.xyGraphforgeSessionRender
          : operation === 22 ? native.xyGraphforgeSessionPollEvent
            : operation === 16 ? native.xyGraphforgeCoordinateDeliver
              : operation === 18 ? native.xyGraphforgeSessionBindTemporal : native.xyGraphforgeSessionInteract;
      const name = operation === 20 ? "xyg_wasm_graphforge_session_update"
        : operation === 21 ? "xyg_wasm_graphforge_session_render" : "xyg_wasm_graphforge_session_interact";
      const nativeBytes = nativeComplete(fn, handle[0], nativeSections === sections ? bytes : request(instance, group, sequence, revision, operation, nativeSections, words));
      const wasmResult = wasmCall(x, wasm, name, bytes);
      assert.equal(wasmResult.status, 0, `operation ${operation}`);
      equalBytes(wasmResult.output, nativeBytes, `operation ${operation} native/WASM bytes`);
      assertGpuPublication(nativeBytes, operation);
      assertGpuPublication(wasmResult.output, operation);
      assert.deepEqual(wasmCall(x, wasm, name, bytes).output, nativeBytes, `operation ${operation} WASM retry bytes`);
      const header = value(nativeBytes, "header.u32");
      if (header) revision = header[0];
      return nativeBytes;
    },
    reject(operation, sections, expected, words = {}) {
      const bytes = request(instance, group, ++sequence, revision, operation, sections, words);
      assert.equal(nativeCall(native.xyGraphforgeSessionInteract, handle[0], bytes, 0).status, expected);
      assert.equal(wasmCall(x, wasm, "xyg_wasm_graphforge_session_interact", bytes).status, expected);
      sequence--; // rejection must leave this exact sequence available
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
    assert.deepEqual([...value(initial, "outcome.u32")], [1, 0, 0, 0]);
    const selected = sender.run(10, [field("uuids.uuid", "uuid", data.nodes.subarray(0, 16))]);
    assert.equal(value(initial, "header.u32")[0], value(selected, "header.u32")[0]);
    assert.deepEqual([...value(selected, "outcome.u32")], [1, 1, 2, 0]);
    assert.ok(value(selected, "node.flags.u32")[0] & 2);
    assert.ok(value(selected, "edge.flags.u32")[data.persisted] & 2, "shared UUID selects both kinds");
    assert.notDeepEqual(value(initial, "render.visual_states.u8"), value(selected, "render.visual_states.u8"));
    const node = refs([{ kind: 0, uuid: data.nodes.subarray(0, 16) }]);
    const focused = sender.run(6, [field("refs.bytes", "bytes", node)]);
    assert.equal(value(focused, "header.u32")[0], value(selected, "header.u32")[0]);
    assert.ok(value(focused, "render.emphasis.u8").some((v) => v & 1));
    const unchangedFocus = sender.run(6, [field("refs.bytes", "bytes", node)]);
    assert.equal(value(unchangedFocus, "outcome.u32")[1], 0, "actual unchanged reducer outcome is serialized");
    sender.run(0, [field("coordinates.f64", "f64", [0, 0])]);
    sender.run(12, [field("refs.bytes", "bytes", node)], { 4: 0 });
    sender.run(12, [field("refs.bytes", "bytes", node)], { 4: 1 });
    const simultaneous = sender.run(12, [field("refs.bytes", "bytes", node)], { 4: 2 });
    assert.equal(value(simultaneous, "header.u32")[0], value(initial, "header.u32")[0]);
    assert.equal(value(simultaneous, "gpu.node.state.u8")[1], 15, "focus/path/community/external coexist");
    assert.equal(value(simultaneous, "gpu.node.state.u8")[2] & 3, 3, "hover and selection coexist with all emphasis bits");
    assert.notDeepEqual(value(simultaneous, "gpu.node.state.u8"), value(initial, "gpu.node.state.u8"), "same revision republishes fresh GPU attributes");
    assert.notDeepEqual(value(simultaneous, "gpu.node.style.bytes"), value(initial, "gpu.node.style.bytes"));
    assert.deepEqual(value(simultaneous, "paint.piece.index.u64"), value(initial, "paint.piece.index.u64"), "state-only publication keeps piece identity/order");
    assert.deepEqual(value(simultaneous, "render.node_x.f64"), value(initial, "render.node_x.f64"));
    assert.deepEqual(value(simultaneous, "render.node_y.f64"), value(initial, "render.node_y.f64"));
    assert.notDeepEqual(value(simultaneous, "gpu.shaft.attr.bytes"), value(initial, "gpu.shaft.attr.bytes"), "same-revision Rust-resolved edge width is refreshed too");
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
    const invalidUtf8=refs([data.exact]); invalidUtf8[invalidUtf8.length-1]=0xff;
    sender.reject(11,[field("refs.bytes","bytes",invalidUtf8)],-3);
    sender.reject(11,[field("refs.bytes","bytes",refs([data.exact]).subarray(0,-1))],-3);
    const reserved=refs([data.exact]); reserved[12]=1;
    sender.reject(11,[field("refs.bytes","bytes",reserved)],-3);
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


test("actual boundaries retain all 20000 changed refs while requests stay capped at 10000", async () => {
  const {instance} = await WebAssembly.instantiate(fs.readFileSync(WASM), {});
  const count = 20000, nodes = new Uint8Array(count * 16);
  const view = new DataView(nodes.buffer);
  for (let i = 0; i < count; i++) view.setUint32(i * 16, i + 1, true);
  const document = encodeContainer("XYGF", [
    field("status", "u32", [0]), field("kind", "utf8", "graph"), field("composition.version", "u32", [2]),
    field("node.uuid", "uuid", nodes), field("edge.uuid", "uuid", new Uint8Array()),
    field("edge.derived", "u8", []), field("edge.layer", "u32", []), field("edge.order", "i64", []),
    field("edge.path", "u64", []), field("edge.source", "u64", []), field("edge.target", "u64", []),
  ]);
  const data = {document, load: [field("document.bytes", "bytes", document), field("load.x.f64", "f64", Array.from({length: count}, (_, i) => i)), field("load.y.f64", "f64", Array(count).fill(0))]};
  const pair = openPair(instance.exports, data, 900003n, 77n, 384 * 1024 * 1024);
  try {
    pair.run(21);
    pair.run(10, [field("uuids.uuid", "uuid", nodes.subarray(0, 10000 * 16))]);
    const reply = pair.run(10, [field("uuids.uuid", "uuid", nodes.subarray(10000 * 16))]);
    const changed = value(reply, "changed.refs.bytes");
    assert.equal(new DataView(changed.buffer, changed.byteOffset).getUint32(0, true), 20000);
    assert.equal(changed.length, 8 + 20000 * 56);
    assert.equal(value(reply, "node.flags.u32").filter(v => v & 2).length, 10000);
    pair.reject(11, [field("refs.bytes", "bytes", changed)], -8);
  } finally { pair.close(); }
});


test("real native/WASM binding shares temporal frames and revokes replaced owners", async () => {
  const { instance } = await WebAssembly.instantiate(fs.readFileSync(WASM), {});
  const x = instance.exports;
  const nodes = new Uint8Array([...Array(16).fill(1), ...Array(16).fill(2)]);
  const edge = new Uint8Array(16).fill(3);
  const document = encodeContainer("XYGF", [
    field("status", "u32", [0]), field("kind", "utf8", "graph"), field("composition.version", "u32", [2]),
    field("node.uuid", "uuid", nodes), field("edge.uuid", "uuid", edge),
    field("edge.derived", "u8", [0]), field("edge.layer", "u32", [0xffffffff]), field("edge.order", "i64", [-1n]),
    field("edge.path", "u64", [0xffffffffffffffffn]), field("edge.source", "u64", [0n]), field("edge.target", "u64", [1n]),
  ]);
  const data = { document, load: [field("document.bytes", "bytes", document), field("load.x.f64", "f64", [0, 40]), field("load.y.f64", "f64", [0, 0])] };
  const projection = graphProjectionCreate({ nodeIds: nodes, edgeIds: edge, sourceIds: nodes.subarray(0, 16), targetIds: nodes.subarray(16) });
  let owner = temporalGraphCreate({ projectionHandle: projection });
  // This test process has created no earlier native temporal owners. Native
  // handle 1 and WASM's instance-local symbolic 1 encode the identical bind.
  assert.equal(owner, 1n);
  const pair = openPair(x, data, 900004n, 78n);
  const other = x.xyg_wasm_instance_new(64 * 1024 * 1024);
  const create = new Uint8Array(112);
  create.set(Buffer.from("XYTG"));
  const cv = new DataView(create.buffer);
  [1, 32, 1, 0, 2, 1, 0].forEach((v, i) => cv.setUint32(4 + i * 4, v, true));
  create.set(nodes, 32); create.set(edge, 64); create.set(nodes.subarray(0, 16), 80); create.set(nodes.subarray(16), 96);
  try {
    assert.equal(wasmCall(x, pair.wasm, "xyg_wasm_temporal_graph_execute", create).status, 0);
    assert.equal(wasmCall(x, other, "xyg_wasm_graphforge_session_open", pair.open).status, 0);
    const bind = request(pair.instance, pair.group, 2, 0, 18, [field("temporal.u64", "u64", [1n])]);
    assert.equal(wasmCall(x, other, "xyg_wasm_graphforge_session_interact", bind).status, -10, "another instance cannot borrow the live owner");
    const bound = pair.run(18, [field("temporal.u64", "u64", [1n])]);
    assert.deepEqual([...value(bound, "outcome.u32")], [1, 0, 0, 0]);
    pair.run(10, [field("uuids.uuid", "uuid", nodes.subarray(0, 16))]);
    const detached = pair.run(18, [field("temporal.u64", "u64", [0n])]);
    assert.deepEqual([...value(detached, "outcome.u32")], [1, 0, 0, 0]);
    const adopted = pair.run(18, [field("temporal.u64", "u64", [1n])]);
    assert.deepEqual([...value(adopted, "outcome.u32")], [1, 0, 1, 0], "binding adopts the existing owner selection count");
    assert.ok(value(adopted, "node.flags.u32")[0] & 2);
    const rebound = pair.run(18, [field("temporal.u64", "u64", [1n])]);
    assert.deepEqual([...value(rebound, "outcome.u32")], [1, 0, 1, 0], "same-owner rebind reports the same authoritative selection");
    temporalGraphFrame(owner, { revision: 1n, cursor: 5n, range: [0n, 10n] });
    const frame = new Uint8Array(56); frame.set(Buffer.from("XYTG"));
    const fv = new DataView(frame.buffer);
    [1, 56, 2].forEach((v, i) => fv.setUint32(4 + i * 4, v, true));
    fv.setBigUint64(16, 1n, true); fv.setBigInt64(24, 5n, true); fv.setBigInt64(40, 10n, true); fv.setBigUint64(48, 1000000n, true);
    assert.equal(wasmCall(x, pair.wasm, "xyg_wasm_temporal_graph_execute", frame).status, 0);
    pair.reject(18, [field("temporal.u64", "u64", [1n])], -1);
    pair.reject(18, [field("temporal.u64", "u64", [0n])], -1);
    pair.reject(4, [], -1);
    const refreshed = pair.run(21);
    assert.ok(value(refreshed, "header.u32")[0] > value(bound, "header.u32")[0]);
    assert.ok(value(refreshed, "node.flags.u32")[0] & 2, "the authoritative temporal world retains selection across frames");
    const frameRebound = pair.run(18, [field("temporal.u64", "u64", [1n])]);
    assert.deepEqual([...value(frameRebound, "outcome.u32")], [1, 0, 1, 0]);
    temporalGraphFrame(owner, { revision: 2n, cursor: 6n, range: [0n, 10n] });
    fv.setBigUint64(16, 2n, true);fv.setBigInt64(24, 6n, true);
    assert.equal(wasmCall(x, pair.wasm, "xyg_wasm_temporal_graph_execute", frame).status, 0);
    pair.reject(18, [field("temporal.u64", "u64", [0n])], -1);
    pair.run(21);
    temporalGraphDestroy(owner); owner = null;
    assert.equal(wasmCall(x, pair.wasm, "xyg_wasm_temporal_graph_execute", create).status, 0);
    pair.reject(4, [], -10, {});
    pair.run(18, [field("temporal.u64", "u64", [0n])]);
    pair.run(21);
    owner=temporalGraphCreate({projectionHandle:projection});
    pair.run(18, [field("temporal.u64","u64",[1n])], {}, [field("temporal.u64","u64",[owner])]);
    pair.run(21);
    pair.run(18, [field("temporal.u64","u64",[0n])]);
  } finally {
    if (owner != null) temporalGraphDestroy(owner);
    graphProjectionDestroy(projection);
    x.xyg_wasm_instance_dispose(other);
    pair.close();
  }
});


test("exact reader UTF-8 identities and resolved paint replay at unchanged default 16MiB", async () => {
  const {instance} = await WebAssembly.instantiate(fs.readFileSync(WASM), {});
  const x=instance.exports;
  const source=fixture();
  let number=901000n;
  for(const exact of [null,"","résumé with spaces","é".repeat(100)]) {
    const parts=decodeContainer(source.document,"XYGF");
    if(exact===null) parts.delete("layer.result_id#2"); else parts.get("layer.result_id#2").value=exact;
    const document=encodeContainer("XYGF",[...parts.values()].map(s=>({...s,values:s.value})));
    const data={...source,document,load:source.load.map(s=>s.name==="document.bytes"?{...s,values:document}:s)};
    const receiverData=withResultIds(data,{1:"rank:exact"});
    const a=openPair(x,data,++number,99n),b=openPair(x,receiverData,++number,99n);
    const reference={...source.exact,result:exact};
    try {
      const initial=a.run(21);
      assert.ok(value(initial,"paint.node.style.bytes").length>0);
      assert.ok(value(initial,"paint.edge.style.bytes").length>0);
      a.run(11,[field("refs.bytes","bytes",refs([reference]))]);
      const focused=a.run(6,[field("refs.bytes","bytes",refs([reference]))]);
      const focus=value(focused,"focus.bytes");
      const fv=new DataView(focus.buffer,focus.byteOffset,focus.byteLength);
      assert.equal(fv.getUint32(8+48,true),exact===null?0xffffffff:0);
      assert.equal(fv.getUint32(8+52,true),exact===null?0:Buffer.byteLength(exact));
      const event=value(a.run(22),"outbound.bytes");
      b.run(21);
      const remote=b.run(16,[field("remote.bytes","bytes",event)]);
      assert.equal(value(remote,"header.u32")[2],0);
      assert.ok(value(remote,"edge.flags.u32")[source.exactIndex]&2);
      const updated=b.run(20,receiverData.load);
      assert.ok(value(updated,"edge.flags.u32")[source.exactIndex]&2);
      b.run(11,[field("refs.bytes","bytes",refs([reference]))]);
      const changed=withResultIds(receiverData,{2:exact===null?"":null});
      const dropped=b.run(20,changed.load);
      assert.ok(value(dropped,"header.u32")[3]>0,"None and present-empty update invalidate distinct exact identities");
      b.reject(11,[field("refs.bytes","bytes",refs([reference]))],-3);
    } finally {a.close();b.close();}
  }
  const nodes=new Uint8Array([...Array(16).fill(1),...Array(16).fill(2)]);
  const document=encodeContainer("XYGF",[
    field("status","u32",[0]),field("kind","utf8","graph"),field("composition.version","u32",[2]),
    field("node.uuid","uuid",nodes),field("node.class","u8",[0,1]),
    field("edge.uuid","uuid",new Uint8Array(16).fill(3)),field("edge.derived","u8",[0]),
    field("edge.layer","u32",[0xffffffff]),field("edge.order","i64",[-1n]),field("edge.path","u64",[0xffffffffffffffffn]),
    field("edge.source","u64",[0n]),field("edge.target","u64",[1n]),field("graph.directed","u8",[1]),
  ]);
  const data={document,load:[field("document.bytes","bytes",document),field("load.x.f64","f64",[0,40]),field("load.y.f64","f64",[0,0])]};
  const small=openPair(x,data,++number,0n,16*1024*1024);
  try {
    const before=small.run(21);
    const selected=small.run(11,[field("refs.bytes","bytes",refs([{kind:0,uuid:nodes.subarray(0,16)}]))]);
    assert.equal(value(before,"header.u32")[0],value(selected,"header.u32")[0]);
    assert.notDeepEqual(value(before,"paint.node.style.bytes"),value(selected,"paint.node.style.bytes"));
    assert.ok(value(before,"paint.piece.geometry.f64").length>0);
    small.run(6,[field("refs.bytes","bytes",refs([{kind:0,uuid:nodes.subarray(16)}]))]);
    const hugeLabel="é".repeat(65536);
    const sections=decodeContainer(document,"XYGF");
    const expanded=encodeContainer("XYGF",[...sections.values()].map(s=>({...s,values:s.value})).concat([field("node.label","texts",[hugeLabel,hugeLabel])]));
    const pressure=request(small.instance,small.group,5, value(selected,"header.u32")[0],20,[field("document.bytes","bytes",expanded),field("load.x.f64","f64",[0,40]),field("load.y.f64","f64",[0,0])]);
    assert.equal(wasmCall(x,small.wasm,"xyg_wasm_graphforge_session_update",pressure).status,-4);
    small.run(21); // same sequence 5 remains available after atomic refusal
  } finally {small.close();}
});


test("real native/WASM resolved routes, heads, frames and aggregate singleton sections", async () => {
  const {instance}=await WebAssembly.instantiate(fs.readFileSync(WASM),{});
  const nodes=new Uint8Array(48);[1,2,3].forEach((v,i)=>nodes.fill(v,i*16,(i+1)*16));
  const edges=new Uint8Array(64);[11,12,13,14].forEach((v,i)=>edges.fill(v,i*16,(i+1)*16));
  const document=encodeContainer("XYGF",[
    field("status","u32",[0]),field("kind","utf8","graph"),field("composition.version","u32",[2]),
    field("node.uuid","uuid",nodes),field("node.parent","u32",[0,0,0]),field("node.parent.valid","u8",[0,1,1]),
    field("node.class","u8",[1,2,3]),field("node.epistemic","u8",[1,2,3]),field("edge.uuid","uuid",edges),
    field("edge.epistemic","u8",[1,2,3,1]),field("edge.status","u8",[1,2,3,1]),
    field("edge.derived","u8",[0,0,0,0]),field("edge.layer","u32",Array(4).fill(0xffffffff)),
    field("edge.order","i64",Array(4).fill(-1n)),field("edge.path","u64",Array(4).fill(0xffffffffffffffffn)),
    field("edge.source","u64",[0n,0n,1n,1n]),field("edge.target","u64",[1n,1n,1n,2n]),field("graph.directed","u8",[1]),
  ]);
  const data={document,load:[field("document.bytes","bytes",document),field("load.x.f64","f64",[0,30,60]),field("load.y.f64","f64",[0,0,0])]};
  const pair=openPair(instance.exports,data,902000n,0n);
  try {
    const r=pair.run(21,[field("camera.f64","f64",[1,100,20,100,200,200,2])]);
    const idx=value(r,"paint.piece.index.u64");
    assert.ok(idx.some((v,i)=>i%2===1 && (v&2n)!==0n));
    assert.equal([...idx].filter((v,i)=>i%2===0 && v===2n).length,3);
    assert.ok(value(r,"paint.frame.node.u64").length>0);
    assert.ok(value(r,"paint.piece.geometry.f64").some((v, i) => i % 14 === 5 && v > 0), "actual dashed strokes are exercised");
    const rootRef = refs([{ kind: 0, uuid: nodes.subarray(0, 16) }]);
    const rootFocus = pair.run(6, [field("refs.bytes", "bytes", rootRef)]);
    assert.deepEqual([...value(rootFocus, "focus.action.u32")], [1, 1, 0, 1, 0, 1, 0, 0]);
    const collapsed = pair.run(9, [field("refs.bytes", "bytes", rootRef)], { 5: 1 });
    assert.deepEqual([...value(collapsed, "outcome.u32")].filter((_, i) => i !== 2), [1, 1, 1]);
    assert.deepEqual(value(collapsed, "disclosure.ref.bytes"), rootRef);
    assert.deepEqual([...value(collapsed, "disclosure.collapsed.u8")], [1]);
    assert.equal(value(collapsed, "focus.action.u32")[2], 1);
    pair.run(9, [field("refs.bytes", "bytes", rootRef)], { 5: 2 });
    const pin = pair.run(13, [field("refs.bytes", "bytes", rootRef)], { 5: 1 });
    assert.equal(value(pin, "focus.action.u32")[4], 1);
    const edgeSample = pair.run(20, [...data.load, field("load.budgets.u64", "u64", [100n, 1n])]);
    assert.equal(value(edgeSample, "render.tier.u32")[0], 1);
    const sampleFocus = pair.run(6, [field("refs.bytes", "bytes", rootRef)]);
    assert.equal(value(sampleFocus, "focus.action.u32")[1], 0, "EdgeSample disclosure is rejected by the actual reducer");
    assert.equal(value(sampleFocus, "focus.action.u32")[5], 1, "EdgeSample nodes remain source-backed");
    const load=data.load.map(s=>s.name==="load.x.f64"?{...s,values:[0,0.1,60]}:s);
    load.push(field("load.budgets.u64","u64",[2n,100n]));
    const aggregate=pair.run(20,load);
    assert.equal(value(aggregate,"render.tier.u32")[0],2);
    const offsets=value(aggregate,"render.node_member_offsets.u64");
    assert.ok([...offsets].some((v,i)=>i>0&&v-offsets[i-1]===1n));
    assert.equal(value(aggregate,"paint.frame.node.u64").length,0);
    assert.equal(value(aggregate,"paint.node.style.bytes").length,2*60);
    for (let index = 0; index < offsets.length - 1; index++) {
      const focusedAggregate = pair.run(6, [field("refs.bytes", "bytes", refs([{ kind: 3, index, revision: value(aggregate, "header.u32")[0] }]))]);
      assert.deepEqual([...value(focusedAggregate, "focus.action.u32")], [1, 0, 0, 0, 0, 0, 0, 0], "single and multiple member aggregate stops deny singular node actions");
      const target = value(focusedAggregate, "focus.action.ref.bytes");
      assert.equal(new DataView(target.buffer, target.byteOffset).getUint32(8, true), 3);
    }
  } finally {pair.close();}
});
