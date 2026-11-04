// Browser codec trust-boundary proof and real retained WASM byte replay.
import assert from "node:assert/strict";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "vite";
import { DTYPE as D, encodeContainer, decodeContainer } from "../../packages/xy-node/src/graphforge-container.js";

const built = await build({ configFile: false, logLevel: "error", build: { write: false, minify: false, lib: { entry: fileURLToPath(new URL("../src/63_graph_session_wire.ts", import.meta.url)), formats: ["es"] } } });
const chunks = (Array.isArray(built) ? built : [built]).flatMap((r) => r.output).filter((x) => x.type === "chunk");
assert.equal(chunks.length, 1);
const wire = await import(`data:text/javascript;base64,${Buffer.from(chunks[0].code).toString("base64")}`);
const field = (name, dtype, values, index = 0) => ({ name, index, dtype: D[dtype], values });
const canonical = { kind: 0, uuid: "00000000-0000-0000-0000-000000000001" };
const derived = { kind: 2, resultId: "exact:\t雪\\\n", layer: 2, path: 0xffffffffffffffffn, order: 9007199254740993n };
const refs = (values) => wire.encodeGraphSessionRefs(values);
const clone = (sections) => sections.map((s) => ({ ...s, values: s.values instanceof Uint8Array ? s.values.slice() : Array.isArray(s.values) ? s.values.slice() : s.values }));
const fixture = () => [
  field("status.u32", "u32", [0]), field("header.u32", "u32", [17, 0, 2, 3]),
  field("gpu.header.u32", "u32", [1, 0, 2, 1, 0, 0, 0, 0]),
  field("selection.refs.bytes", "bytes", refs([canonical, derived])),
  field("selection.indices.u64", "u64", [0n, 1n]),
  field("selection.layer_offsets.u64", "u64", [0n, 2n, 3n]),
  field("selection.layers.u32", "u32", [0, 1, 2]),
  field("selection.rows.u64", "u64", [9007199254740993n, 0n, 0xfffffffffffffffen]),
  field("selection.result_ids.texts", "texts", ["", "", derived.resultId]),
  field("selection.result_ids.valid.u8", "u8", [0, 1, 1]),
  field("changed.refs.bytes", "bytes", refs([derived])),
  field("focus.bytes", "bytes", refs([derived])), field("focus.ring.u32", "u32", [0, 1, 1, 0]),
  field("focus.action.ref.bytes", "bytes", refs([])), field("focus.action.u32", "u32", [1, 0, 0, 0, 0, 0, 0, 0]),
  field("clear.action.u32", "u32", [1, 1]),
  field("outcome.u32", "u32", [1, 1, 7, 0]),
  field("disclosure.ref.bytes", "bytes", refs([])), field("disclosure.collapsed.u8", "u8", []),
  field("candidates.bytes", "bytes", refs([canonical, derived])),
  field("candidates.total.u32", "u32", [123]), field("companion.total.u32", "u32", [123]),
  field("companion.text.utf8", "utf8", "Node\tid\\tpart\tlabel\\nline\\\\tail\t2 relationships\tselected\nEdge\texact\t雪\t0 to 1\tnot selected"),
  field("summary.text.utf8", "utf8", "Rust summary: <b>text</b>"),
];
const invalid = (sections) => assert.throws(() => wire.decodeGraphSessionResult(encodeContainer("XYGR", sections)), (error) => error.code === "GF_INTERACTION_INVALID" && error.status === -3);

test("browser encoder retains exact bigint identities, negative camera scale and existing load framing", () => {
  const instanceId = 0xffffffffffffffffn, opSeq = 9007199254740993n;
  const bytes = wire.encodeGraphSessionRequest({ instanceId, opSeq, revision: 17, operation: 5, direction: -1 });
  assert.deepEqual(bytes, encodeContainer("XYGI", [field("header.u64", "u64", [instanceId, 0n, opSeq]), field("header.u32", "u32", [17, 5, 0, 0, 0, 0xffffffff, 0, 0, 0])]));
  const camera = [-2, 3, 1, -4, 640, 480, 2];
  const render = decodeContainer(wire.encodeGraphSessionRequest({ instanceId, opSeq, revision: 17, operation: 21, camera, page: 4 }), "XYGI");
  assert.deepEqual([...render.get("camera.f64#0").value], camera);
  assert.deepEqual([...render.get("companion.u32#0").value], [4, 50]);
  const opened = decodeContainer(wire.encodeGraphSessionRequest({ instanceId, opSeq, revision: 0, operation: 19, document: new Uint8Array([1, 2]), load: { x: [1], y: [2], pinned: [1], collapsed: [0], budgets: [200_000n, 500_000n], seed: opSeq, progressive: false, cose: [30, 40, 0.3, 0.9, 2, 4], coseBounds: [-1, -2, 3, 4] } }), "XYGI");
  assert.equal(opened.get("load.seed.u64#0").value[0], opSeq);
  assert.deepEqual([...opened.get("load.cose.bounds.f64#0").value], [-1, -2, 3, 4]);
  for (const bad of [0n, -1n, 0x10000000000000000n, 1, NaN]) assert.throws(() => wire.encodeGraphSessionRequest({ instanceId: bad, opSeq: 1n, revision: 0, operation: 4 }));
  assert.throws(() => wire.encodeGraphSessionRequest({ instanceId: 1n, opSeq: 1, revision: 0, operation: 4 }));
  assert.throws(() => wire.encodeGraphSessionRequest({ instanceId: 1n, opSeq: 1n, revision: 0, operation: 0 }));
  assert.throws(() => wire.encodeGraphSessionRequest({ instanceId: 1n, opSeq: 1n, revision: 0, operation: 4, refs: [] }));
  assert.throws(() => wire.encodeGraphSessionRequest({ instanceId: 1n, opSeq: 1n, revision: 0, operation: 17, page: 0xffffffff, pageSize: 200 }));
});

test("complete semantic decode preserves selection provenance and exact refs without equating projection with global selection", () => {
  const result = wire.decodeGraphSessionResult(encodeContainer("XYGR", fixture()));
  assert.deepEqual(result.selection.refs, [canonical, derived]);
  assert.deepEqual(result.changed, [derived]);
  assert.deepEqual(result.focus, [derived]);
  assert.deepEqual([...result.selection.rows], [9007199254740993n, 0n, 0xfffffffffffffffen]);
  assert.deepEqual([...result.selection.indices], [0n, 1n]);
  assert.deepEqual([...result.selection.layerOffsets], [0n, 2n, 3n]);
  assert.deepEqual(result.selection.resultIds, [null, "", derived.resultId]);
  assert.equal(result.clearAction.applicable, true);
  const falseFact = fixture(); falseFact.find(s => s.name === "clear.action.u32").values = [1, 0];
  assert.equal(wire.decodeGraphSessionResult(encodeContainer("XYGR", falseFact)).clearAction.applicable, false, "decoder never infers applicability from counts");
  assert.equal(result.outcome.selected, 7);
  assert.equal(result.selection.refs.length, 2);
  assert.deepEqual(result.companion.rows[0], ["Node", "id\tpart", "label\nline\\tail", "2 relationships", "selected"]);
  assert.deepEqual(result.companion.refs, [canonical, derived]);
  assert.equal(result.summary, "Rust summary: <b>text</b>");
  assert.equal(result.revision, 17);
  assert.equal(result.unmatched, 2);
  assert.equal(result.dropped, 3);
  assert.equal("instanceId" in result, false, "XYGR carries no echoed instance identity");
});

test("refs distinguish absent IDs from empty IDs and reject malformed reserved, UTF8, pool and unused fields", () => {
  const values = [{ ...derived, resultId: null }, { ...derived, resultId: "" }, derived, { kind: 3, index: 4, renderRevision: 17 }];
  const encoded = refs(values);
  assert.deepEqual(wire.decodeGraphSessionRefs(encoded), values);
  assert.throws(() => refs([{ ...derived, resultId: "\ud800" }]));
  for (const mutate of [
    (v) => v.setUint32(12, 1, true),
    (v) => v.setUint32(8 + 52, 1, true),
    (v) => v.setUint32(8 + 56 + 48, 1, true),
    (v) => v.setUint32(8 + 56 * 3 + 48, 1, true),
    (v) => v.setUint32(4, 0, true),
  ]) {
    const bad = encoded.slice(); mutate(new DataView(bad.buffer)); assert.throws(() => wire.decodeGraphSessionRefs(bad));
  }
  const badUtf8 = encoded.slice(); badUtf8[8 + 56 * values.length] = 0xff;
  assert.throws(() => wire.decodeGraphSessionRefs(badUtf8));
});

test("malformed semantic planes fail before an accepted picture can be replaced", () => {
  const original = fixture();
  const replace = (name, values, dtype) => {
    const sections = clone(original), s = sections.find((x) => x.name === name); s.values = values; if (dtype) s.dtype = D[dtype]; invalid(sections);
  };
  replace("selection.indices.u64", [0n]);
  replace("selection.layer_offsets.u64", [0n, 3n, 2n]);
  replace("selection.layers.u32", [1, 0, 2]);
  replace("selection.rows.u64", [1n, 2n, 0xffffffffffffffffn]);
  replace("selection.result_ids.valid.u8", [0, 2, 1]);
  replace("selection.result_ids.texts", ["not absent", "", derived.resultId]);
  replace("focus.ring.u32", [0, 2]);
  replace("focus.action.u32", [1, 0, 0, 1, 0, 0, 0, 0]);
  for (const values of [[1], [1, 0, 0], [2, 1], [1, 2]]) replace("clear.action.u32", values);
  replace("clear.action.u32", [1n, 1n], "u64");
  invalid(original.filter((s) => s.name !== "clear.action.u32"));
  invalid([...original, field("clear.action.u32", "u32", [1, 1], 1)]);
  replace("outcome.u32", [1, 2, 7, 0]);
  replace("candidates.total.u32", [1]);
  replace("companion.text.utf8", "Node\tonly two cells");
  replace("companion.text.utf8", "Node\tid\tbad\\xescape\trelation\tselected\nEdge\tid\tlabel\trelation\tselected");
  replace("summary.text.utf8", new Uint8Array([0xff]), "bytes");
  invalid(original.filter((s) => s.name !== "selection.rows.u64"));
});

function call(x, handle, name, bytes) {
  assert.equal(x.xyg_wasm_arena_resize(handle, bytes.length), 0);
  new Uint8Array(x.memory.buffer, x.xyg_wasm_arena_ptr(handle) >>> 0, bytes.length).set(bytes);
  const status = x[name](handle, 0, bytes.length);
  // A failed command must not read the instance's preceding successful output.
  return { status, output: status === 0 ? new Uint8Array(x.memory.buffer, x.xyg_wasm_output_ptr(handle) >>> 0, x.xyg_wasm_output_len(handle) >>> 0).slice() : null };
}

test("actual default-arena WASM composition/session bytes decode through focus/select/toggle/clear and companion pages", async () => {
  const wasm = process.env.XYG_SESSION_WASM || fileURLToPath(new URL("../../packages/xy-client/dist/xyg-wasm.wasm", import.meta.url));
  const { instance } = await WebAssembly.instantiate(fs.readFileSync(wasm), {}), x = instance.exports;
  const handle = x.xyg_wasm_instance_new(16 * 1024 * 1024);
  assert.ok(handle > 0);
  const instanceId = 9007199254740993n;
  let sequence = 0n, revision = 0, opened = false;
  const run = (operation, extra = {}, expected = 0) => {
    const request = wire.encodeGraphSessionRequest({ instanceId, opSeq: ++sequence, revision, operation, ...extra });
    const name = operation === 19 ? "xyg_wasm_graphforge_session_open" : operation === 21 ? "xyg_wasm_graphforge_session_render" : "xyg_wasm_graphforge_session_interact";
    const response = call(x, handle, name, request);
    assert.equal(response.status, expected);
    if (expected) { assert.equal(response.output, null); return; }
    assert.deepEqual(call(x, handle, name, request).output, response.output, "identical bytes/sequence returns exact retained result");
    const decoded = operation === 19 ? wire.decodeGraphSessionAck(response.output) : wire.decodeGraphSessionResult(response.output);
    revision = decoded.revision;
    if (operation === 19) opened = true;
    return decoded;
  };
  try {
    const arrow = (name) => fs.readFileSync(new URL(`../../tests/fixtures/graphforge/results/${name}.arrow`, import.meta.url));
    const compose = encodeContainer("XYGQ", [
      field("base.table", "bytes", arrow("base-cyclic-nodes"), 0), field("base.table", "bytes", arrow("base-cyclic-edges"), 1),
      field("layer.result", "bytes", arrow("pagerank"), 0), field("layer.intent", "utf8", "graph", 0),
      field("layer.result", "bytes", arrow("node_similarity"), 1), field("layer.intent", "utf8", "graph", 1), field("layer.result_id", "utf8", "pair:exact", 1),
      field("layer.result", "bytes", arrow("dijkstra"), 2), field("layer.intent", "utf8", "graph", 2), field("layer.result_id", "utf8", "path:exact", 2),
    ]);
    const composed = call(x, handle, "xyg_wasm_graphforge_compose", compose);
    assert.equal(composed.status, 0);
    const sections = decodeContainer(composed.output, "XYGF");
    assert.equal(sections.get("status#0").value[0], 0, `${sections.get("error.code#0")?.value}: ${sections.get("error.message#0")?.value}`);
    const n = sections.get("node.uuid#0").value.length / 16;
    // Composition authoring IDs are narrower than the session's exact-ID wire.
    // Exercise the complete XYGF/session boundary using admitted exact document IDs.
    sections.delete("layer.result_id#0");
    sections.get("layer.result_id#1").value = "";
    sections.get("layer.result_id#2").value = derived.resultId;
    const document = encodeContainer("XYGF", [...sections.values()].map((s) => ({ ...s, values: s.value })));
    run(19, { document, load: { x: Array.from({ length: n }, (_, i) => i * 30), y: Array(n).fill(0) } });
    let result = run(21, { camera: [1, -1, 10, 100, 640, 480, 1] });
    assert.equal(result.selection.refs.length, 0);
    assert.equal(result.clearAction.applicable, false);
    assert.ok(result.companion.total > 2);
    assert.deepEqual(result.selection.resultIds, [null, "", derived.resultId]);
    const sameRevision = result.revision;
    const gpuGeometry = (r) => [...r.sections.values()].filter((s) => /gpu\..*coord\.bytes/.test(s.name)).map((s) => [s.name, s.index, [...s.bytes]]);
    const geometry = gpuGeometry(result);
    result = run(5, { direction: 1 });
    assert.equal(result.focus.length, 1);
    assert.equal(result.clearAction.applicable, false, "focus alone is not clearable");
    assert.equal(result.revision, sameRevision, "focus republishes style at the same render revision");
    assert.deepEqual(gpuGeometry(result), geometry);
    const nodeState = result.sections.get("gpu.node.state.u8#0").bytes;
    assert.ok(Array.from({ length: nodeState.length / 4 }, (_, i) => nodeState[i * 4 + 1] & 1).some(Boolean));
    result = run(7);
    assert.ok(result.outcome.selected > 0);
    assert.equal(result.clearAction.applicable, true);
    assert.equal(result.selection.indices.length, result.selection.refs.length);
    result = run(7, { mode: 2 });
    assert.equal(result.outcome.selected, 0);
    result = run(17, { page: 1, pageSize: 2 });
    assert.equal(result.companion.refs.length, 2);
    assert.equal(result.companion.rows.length, 2);
    result = run(11, { refs: [result.companion.refs[0]] });
    assert.equal(result.outcome.selected, 1);
    assert.equal(result.selection.refs.length, 1);
    result = run(4);
    assert.equal(result.outcome.selected, 0);
    assert.equal(result.outcome.stateChanged, true);
    assert.equal(result.clearAction.applicable, false);
    result = run(4);
    assert.equal(result.outcome.stateChanged, false, "empty Escape outcome propagates");
    const wrong = wire.encodeGraphSessionRequest({ instanceId: instanceId + 1n, opSeq: sequence + 1n, revision, operation: 4 });
    assert.equal(call(x, handle, "xyg_wasm_graphforge_session_interact", wrong).status, -3);
    const stale = wire.encodeGraphSessionRequest({ instanceId, opSeq: sequence + 1n, revision: revision + 1, operation: 4 });
    assert.equal(call(x, handle, "xyg_wasm_graphforge_session_interact", stale).status, -1);
    run(21, { camera: [1, -1, 10, 100, 640, 480, 1] });
  } finally {
    if (opened) assert.equal(x.xyg_wasm_graphforge_session_close(handle), 0);
    assert.equal(x.xyg_wasm_instance_dispose(handle), 0);
  }
});
