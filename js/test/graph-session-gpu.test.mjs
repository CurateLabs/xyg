// GPU-v1 is a fail-closed, raw-buffer boundary. Exercise the actual TS decoder.
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "vite";

const built = await build({ configFile: false, logLevel: "error", build: { write: false, minify: false, lib: { entry: fileURLToPath(new URL("../src/63_graph_gpu.ts", import.meta.url)), formats: ["es"] } } });
const chunks = (Array.isArray(built) ? built : [built]).flatMap((r) => r.output).filter((x) => x.type === "chunk");
assert.equal(chunks.length, 1);
const { decodeGraphGpu } = await import(`data:text/javascript;base64,${Buffer.from(chunks[0].code).toString("base64")}`);

// Two clipped pieces share one edge; its sole head refers to the second piece.
// This tests index spaces independently of the node/edge/geometry vector sizes.
function fixture() {
  const sections = new Map();
  function put(name, index, dtype, array) {
    const bytes = new Uint8Array(array.buffer, array.byteOffset, array.byteLength);
    const count = bytes.length / (dtype === 2 ? 4 : dtype === 3 || dtype === 5 ? 8 : 1);
    sections.set(`${name}#${index}`, { name, index, dtype, count, bytes });
  }
  put("gpu.header.u32", 0, 2, new Uint32Array([1, 0, 2, 1, 2, 1, 1, 0]));
  for (let i = 0; i < 3; i++) put("gpu.transform.f64", i, 5, new Float64Array([1e12, 0.5]));
  for (const [kind, columns, count] of [["node", 2, 2], ["shaft", 4, 2], ["head", 6, 1], ["frame", 4, 1]]) {
    for (let i = 0; i < columns; i++) put(`gpu.${kind}.coord.bytes`, i, 6, new Float32Array(count).fill(i + 0.5));
  }
  for (let i = 0; i < 4; i++) put("gpu.shaft.attr.bytes", i, 6, new Float32Array([1, 2]));
  put("gpu.frame.width.bytes", 0, 6, new Float32Array([1]));
  put("gpu.shaft.edge.u32", 0, 2, new Uint32Array([0, 0]));
  put("gpu.shaft.flags.u8", 0, 1, new Uint8Array([1, 0]));
  put("gpu.head.piece.u32", 0, 2, new Uint32Array([1]));
  put("gpu.frame.node.u32", 0, 2, new Uint32Array([1]));
  for (const [kind, count] of [["node", 2], ["edge", 1]]) {
    const styles = new Uint8Array(count * 60), view = new DataView(styles.buffer);
    for (let n = 0; n < count; n++) {
      for (const offset of [12, 16, 20, 40, 44, 48, 52]) view.setFloat32(n * 60 + offset, 1, true);
      styles[n * 60 + 24] = 5; styles[n * 60 + 25] = 3;
      styles[n * 60 + 26] = 1; styles[n * 60 + 27] = 7; styles[n * 60 + 56] = 1;
    }
    put(`gpu.${kind}.style.bytes`, 0, 6, styles);
    const states = new Uint8Array(count * 4);
    for (let n = 0; n < count; n++) states.set([7, 15, 0x17, 0], n * 4);
    put(`gpu.${kind}.state.u8`, 0, 1, states);
  }
  put("render.node_x.f64", 0, 5, new Float64Array(2));
  put("render.edge_source.u64", 0, 3, new BigUint64Array(1));
  return sections;
}
const section = (s, name, index = 0) => s.get(`${name}#${index}`);
const view = (s, name, index = 0) => { const b = section(s, name, index).bytes; return new DataView(b.buffer, b.byteOffset, b.byteLength); };
function refuses(mutate) {
  const sections = fixture(); mutate(sections);
  assert.throws(() => decodeGraphGpu(sections), (error) => error.code === "GF_INTERACTION_INVALID");
}

test("GPU-v1 retains original raw style, coordinate, state and reference buffers", () => {
  const sections = fixture(), gpu = decodeGraphGpu(sections);
  assert.deepEqual(gpu.counts, [2, 1, 2, 1, 1]);
  assert.deepEqual(gpu.transforms, [[1e12, 0.5], [1e12, 0.5], [1e12, 0.5]]);
  for (const [key, value] of sections) assert.equal(gpu.sections.get(key).bytes, value.bytes);
});

test("empty publication retains all zero-length planes and checked counts refuse overflow", () => {
  const sections = fixture();
  for (const [key, s] of sections) {
    if (s.name === "gpu.header.u32" || s.name === "gpu.transform.f64") continue;
    sections.set(key, { ...s, count: 0, bytes: new Uint8Array() });
  }
  const h = view(sections, "gpu.header.u32");
  for (let i = 2; i < 7; i++) h.setUint32(i * 4, 0, true);
  assert.deepEqual(decodeGraphGpu(sections).counts, [0, 0, 0, 0, 0]);
  refuses((s) => view(s, "gpu.header.u32").setUint32(8, 0xffffffff, true));
});

test("every one of the 33 planes is required with exact index, dtype and length", () => {
  const gpuKeys = [...fixture().keys()].filter((k) => k.startsWith("gpu."));
  assert.equal(gpuKeys.length, 33);
  for (const key of gpuKeys) {
    refuses((s) => s.delete(key));
    refuses((s) => { s.get(key).index++; });
    refuses((s) => { s.get(key).dtype = 99; });
    refuses((s) => { s.get(key).count++; });
    refuses((s) => { s.get(key).bytes = s.get(key).bytes.subarray(1); });
  }
  refuses((s) => s.set("gpu.future.bytes#0", { name: "gpu.future.bytes", index: 0, dtype: 6, count: 0, bytes: new Uint8Array() }));
  refuses((s) => s.set("gpu.node.coord.bytes#2", { ...section(s, "gpu.node.coord.bytes"), index: 2 }));
});

test("header, published counts and each coordinate/attribute float fail closed", () => {
  for (const offset of [0, 4, 28]) refuses((s) => view(s, "gpu.header.u32").setUint32(offset, 2, true));
  for (const name of ["render.node_x.f64", "render.edge_source.u64"]) refuses((s) => { section(s, name).count++; });
  for (const name of ["gpu.node.coord.bytes", "gpu.shaft.coord.bytes", "gpu.shaft.attr.bytes", "gpu.head.coord.bytes", "gpu.frame.coord.bytes", "gpu.frame.width.bytes"]) {
    const keys = [...fixture().values()].filter((v) => v.name === name);
    for (const { index } of keys) for (const value of [NaN, Infinity, -Infinity]) refuses((s) => view(s, name, index).setFloat32(0, value, true));
  }
  for (let index = 0; index < 3; index++) {
    for (const offset of [NaN, Infinity, -Infinity]) refuses((s) => view(s, "gpu.transform.f64", index).setFloat64(0, offset, true));
    for (const scale of [0, -1, NaN, Infinity]) refuses((s) => view(s, "gpu.transform.f64", index).setFloat64(8, scale, true));
  }
});

test("style fields, reserved bytes and independent simultaneous state bits validate", () => {
  for (const kind of ["node", "edge"]) {
    for (const [offset, bad] of [[24, 6], [25, 4], [26, 2], [27, 8], [56, 2], [57, 1], [58, 1], [59, 1]]) refuses((s) => { section(s, `gpu.${kind}.style.bytes`).bytes[offset] = bad; });
    for (const offset of [12, 16, 20, 40, 44, 48, 52]) refuses((s) => view(s, `gpu.${kind}.style.bytes`).setFloat32(offset, NaN, true));
    for (const [offset, bad] of [[0, 8], [1, 16], [2, 8], [2, 32], [3, 1]]) refuses((s) => { section(s, `gpu.${kind}.state.u8`).bytes[offset] = bad; });
  }
  refuses((s) => { section(s, "gpu.shaft.flags.u8").bytes[0] = 2; });
});

test("piece/edge and frame/node references use their own bounded index spaces", () => {
  for (const [name, limit] of [["gpu.shaft.edge.u32", 1], ["gpu.head.piece.u32", 2], ["gpu.frame.node.u32", 2]]) refuses((s) => view(s, name).setUint32(0, limit, true));
  // Grow only the head count/coordinate planes to expose a duplicate/backward
  // reference. No source graph policy is involved in this structural check.
  for (const refs of [[1, 1], [1, 0]]) refuses((s) => {
    view(s, "gpu.header.u32").setUint32(20, 2, true);
    for (let i = 0; i < 6; i++) { const b = new Uint8Array(8); s.set(`gpu.head.coord.bytes#${i}`, { name: "gpu.head.coord.bytes", index: i, dtype: 6, count: 8, bytes: b }); }
    const b = new Uint8Array(new Uint32Array(refs).buffer);
    s.set("gpu.head.piece.u32#0", { name: "gpu.head.piece.u32", index: 0, dtype: 2, count: 2, bytes: b });
  });
});
