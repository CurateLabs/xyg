// CoSE cross-host parity (issue #35; spec/design/graph-mark.md, "CoSE
// cross-host parity"). One committed golden (generated from the native Python
// binding by scripts/gen_cose_parity_golden.py) holds seeded fixtures, including
// compound and disconnected graphs and both repulsion tiers, with sha256
// digests of the f64 positions + alpha at each progressive checkpoint.
//
//  - Node native (koffi -> libxyg_core) recomputes them through the C ABI;
//  - the real wasm32 artifact recomputes them through xyg_wasm_graph_begin/step
//    exactly as the browser Worker drives it.
//
// Tolerance policy (spec/design/graph-mark.md, "CoSE cross-host parity"):
//  - authored start positions: bitwise at every checkpoint (the force kernel
//    uses only + - * / sqrt, all correctly rounded on every host);
//  - Rust-seeded start: the seeded circle calls the platform libm sin/cos, so
//    wasm32 may differ from native by a few ulps at placement. The first
//    checkpoint must agree within SEEDED_FIRST_CHECKPOINT_EPS; the bitwise
//    seeded assertion is `todo` until the seed uses portable_sin_cos.
//
// Build the WASM artifact first: node js/build.mjs && npm run build:wasm.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

import { graphForceCreate, graphForceDestroy, graphForceTick } from "../src/abi.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const GOLDEN = JSON.parse(fs.readFileSync(path.join(ROOT, "tests/fixtures/graphforge/cose-parity/golden.json"), "utf8"));
const WASM = path.join(ROOT, "packages/xy-client/dist/xyg-wasm.wasm");
const BUNDLE = path.join(ROOT, "packages/xy-client/dist/index.js");
const wasmSkip = fs.existsSync(WASM) && fs.existsSync(BUNDLE)
  ? false
  : "build the WASM artifact first: node js/build.mjs && npm run build:wasm";

// Measured seeded-start first-checkpoint deltas are <= 2.3e-13 on coordinates of
// magnitude ~10 (a few ulps); the bound keeps >4 orders of margin and still
// rejects any algorithmic divergence.
const SEEDED_FIRST_CHECKPOINT_EPS = 1e-9;
const STATUS_OK = 0;
const STATUS_PENDING = 8;

function digest(x, y, alpha) {
  const h = createHash("sha256");
  h.update(Buffer.from(x.buffer, x.byteOffset, x.byteLength));
  h.update(Buffer.from(y.buffer, y.byteOffset, y.byteLength));
  const a = Buffer.alloc(8);
  a.writeDoubleLE(alpha);
  h.update(a);
  return h.digest("hex");
}

const u64 = (values) => BigUint64Array.from(values, (v) => BigInt(v));
// Golden parents use null for "no parent"; the wire sentinel is u64::MAX.
const parentsU64 = (values) => BigUint64Array.from(values, (v) => (v === null ? 0xffffffffffffffffn : BigInt(v)));

function maxDelta(x, y, expected) {
  let worst = 0;
  for (let i = 0; i < x.length; i += 1) {
    worst = Math.max(worst, Math.abs(x[i] - expected.x[i]), Math.abs(y[i] - expected.y[i]));
  }
  return worst;
}

function assertCheckpoints(name, host, got, final, expected) {
  assert.deepEqual(
    got.map(({ step, alpha }) => ({ step, alpha })),
    expected.checkpoints.map(({ step, alpha }) => ({ step, alpha })),
    `${name}: ${host} step/alpha schedule`,
  );
  got.forEach((checkpoint, i) => {
    assert.equal(
      checkpoint.sha256,
      expected.checkpoints[i].sha256,
      `${name}: ${host} checkpoint ${checkpoint.step} differs bitwise (final max |delta| = ${maxDelta(final.x, final.y, expected)})`,
    );
  });
  assert.deepEqual(Array.from(final.x), expected.x, `${name}: ${host} final x`);
  assert.deepEqual(Array.from(final.y), expected.y, `${name}: ${host} final y`);
}

function firstNativeCheckpoint(fixture) {
  const handle = graphForceCreate(fixture.nNodes, u64(fixture.sources), u64(fixture.targets), nativeOptions(fixture));
  try {
    const { x, y } = graphForceTick(handle, fixture.nNodes, GOLDEN.schedule[0]);
    return { x, y };
  } finally {
    graphForceDestroy(handle);
  }
}

function nativeOptions(fixture) {
  return {
    algorithm: "cose",
    seed: fixture.seed,
    cose: fixture.cose ?? {},
    pinned: fixture.pinned ? Uint8Array.from(fixture.pinned) : undefined,
    parents: fixture.parents ? parentsU64(fixture.parents) : undefined,
    x: fixture.x ? Float64Array.from(fixture.x) : undefined,
    y: fixture.y ? Float64Array.from(fixture.y) : undefined,
  };
}

function runNative(fixture) {
  const handle = graphForceCreate(fixture.nNodes, u64(fixture.sources), u64(fixture.targets), nativeOptions(fixture));
  const checkpoints = [];
  let last;
  let step = 0;
  try {
    for (const take of GOLDEN.schedule) {
      last = graphForceTick(handle, fixture.nNodes, take);
      step += take;
      checkpoints.push({ step, alpha: last.alpha, sha256: digest(last.x, last.y, last.alpha) });
    }
  } finally {
    graphForceDestroy(handle);
  }
  return { checkpoints, final: last };
}

async function loadWasm() {
  const { instance } = await WebAssembly.instantiate(fs.readFileSync(WASM), {});
  return instance.exports;
}

function runWasm(wasm, client, fixture) {
  const handle = wasm.xyg_wasm_instance_new(256 * 1024 * 1024);
  assert.ok(handle > 0, "WASM instance");
  try {
    const request = new Uint8Array(client.encodeWasmCose({
      nNodes: fixture.nNodes,
      sources: u64(fixture.sources),
      targets: u64(fixture.targets),
      x: fixture.x ? Float64Array.from(fixture.x) : undefined,
      y: fixture.y ? Float64Array.from(fixture.y) : undefined,
      pinned: fixture.pinned ? Uint8Array.from(fixture.pinned) : undefined,
      parents: fixture.parents ? parentsU64(fixture.parents) : undefined,
      totalSteps: GOLDEN.schedule.reduce((a, b) => a + b, 0),
      seed: BigInt(fixture.seed),
      cose: fixture.cose,
    }));
    assert.equal(wasm.xyg_wasm_arena_resize(handle, request.byteLength), 0);
    new Uint8Array(wasm.memory.buffer, wasm.xyg_wasm_arena_ptr(handle) >>> 0, request.byteLength).set(request);
    const sequence = 1;
    const revision = 1;
    assert.equal(wasm.xyg_wasm_graph_begin(handle, sequence, revision, 0, request.byteLength), STATUS_OK);
    const checkpoints = [];
    let first;
    let final;
    GOLDEN.schedule.forEach((take, i) => {
      const status = wasm.xyg_wasm_graph_step(handle, sequence, revision, take);
      assert.ok(status === STATUS_PENDING || (status === STATUS_OK && i === GOLDEN.schedule.length - 1), `step status ${status}`);
      const out = wasm.xyg_wasm_output_ptr(handle) >>> 0;
      const len = wasm.xyg_wasm_output_len(handle) >>> 0;
      const buffer = new Uint8Array(wasm.memory.buffer, out, len).slice().buffer;
      const checkpoint = client.decodeWasmGraphCheckpoint(buffer);
      checkpoints.push({ step: checkpoint.step, alpha: checkpoint.alpha, sha256: digest(checkpoint.x, checkpoint.y, checkpoint.alpha) });
      first ??= checkpoint;
      final = checkpoint;
    });
    return { checkpoints, final, first };
  } finally {
    wasm.xyg_wasm_instance_dispose(handle);
  }
}

test("the golden covers compound, disconnected, and both repulsion tiers", () => {
  const names = GOLDEN.cases.map((c) => c.name);
  for (const required of ["compound", "disconnected", "random-200-exact-tier"]) assert.ok(names.includes(required), required);
  assert.ok(names.some((n) => n.startsWith("random-700-grid-tier")));
  assert.ok(GOLDEN.cases.some((c) => c.parents) && GOLDEN.cases.some((c) => c.pinned && c.cose?.bounds));
});

for (const fixture of GOLDEN.cases) {
  test(`native Node CoSE matches the golden bitwise: ${fixture.name}`, () => {
    const { checkpoints, final } = runNative(fixture);
    assertCheckpoints(fixture.name, "native Node", checkpoints, final, fixture.expected);
  });
}

for (const fixture of GOLDEN.cases) {
  const authored = fixture.start === "authored";
  test(`direct-WASM CoSE matches native bitwise: ${fixture.name}`, {
    skip: wasmSkip,
    todo: authored ? false : "seeded start uses platform libm sin/cos; bitwise needs portable_sin_cos in ForceState::new (#35)",
  }, async () => {
    const client = await import(pathToFileURL(BUNDLE).href);
    const wasm = await loadWasm();
    const { checkpoints, final } = runWasm(wasm, client, fixture);
    assertCheckpoints(fixture.name, "WASM", checkpoints, final, fixture.expected);
  });
  if (!authored) {
    test(`direct-WASM seeded start stays within the first-checkpoint tolerance: ${fixture.name}`, { skip: wasmSkip }, async () => {
      const client = await import(pathToFileURL(BUNDLE).href);
      const wasm = await loadWasm();
      const { first } = runWasm(wasm, client, fixture);
      const native = firstNativeCheckpoint(fixture);
      let worst = 0;
      for (let i = 0; i < fixture.nNodes; i += 1) {
        worst = Math.max(worst, Math.abs(first.x[i] - native.x[i]), Math.abs(first.y[i] - native.y[i]));
      }
      assert.ok(worst <= SEEDED_FIRST_CHECKPOINT_EPS, `${fixture.name}: first-checkpoint max |delta| ${worst}`);
    });
  }
}
