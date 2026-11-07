import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import {
  FilterTierCSession,
  decodeFilterReply,
  FilterTierCError,
} from "../src/filter-session.js";
import { executeFilterPacket } from "../src/filter-session.js";
import { xyFilterSessionNew, xyFilterSessionFree } from "../src/native.js";
import { scatterChart } from "../src/index.js";
const root = new URL("../../../", import.meta.url);
const stream = fs.readFileSync(
  new URL("tests/fixtures/filter_tier_c/session.bin", root),
);
const manifest = JSON.parse(
  fs.readFileSync(new URL("tests/fixtures/filter_tier_c/manifest.json", root)),
);
function records() {
  const out = [];
  let at = 0;
  while (at < stream.length) {
    const n = stream.readUInt32LE(at),
      cap = stream.readUInt32LE(at + 4),
      status = stream.readInt32LE(at + 8),
      replyN = stream.readUInt32LE(at + 12),
      required = stream.readBigUInt64LE(at + 16);
    at += 24;
    const request = stream.subarray(at, at + n);
    at += n;
    const reply = stream.subarray(at, at + replyN);
    at += replyN;
    out.push({ request, reply, cap, status, required });
  }
  return out;
}
function oracle(result, entry) {
  if (!entry.oracle) return;
  assert.equal(result.selectedCount, BigInt(entry.oracle.selected), entry.name);
  if (entry.oracle.membership_hex !== null)
    assert.equal(
      Buffer.from(result.membership).toString("hex"),
      entry.oracle.membership_hex,
    );
  else
    assert.deepEqual(
      result.views.map((v) => ({
        id: Number(v.id),
        counts: Array.from(v.counts, Number),
      })),
      entry.oracle.views,
    );
}
// A separate full-scan implementation consumes canonical ingress and configuration.
// It never calls the production bin classifier, Rust kernels, or stored counts.
function scanOracle() {
  let columns = [],
    views = [],
    dimension = 0,
    intent = null,
    first = 0n;
  return (request, result) => {
    if (result.status) return;
    const d = new DataView(
        request.buffer,
        request.byteOffset,
        request.byteLength,
      ),
      op = d.getUint32(8, true);
    if (op === 1 || op === 2) {
      const dims = Number(d.getBigUint64(56, true)),
        n = Number(d.getBigUint64(64, true));
      if (op === 1) {
        columns = Array.from({ length: dims }, () => []);
        first = d.getBigUint64(72, true);
      }
      for (let dim = 0; dim < dims; dim++)
        for (let i = 0; i < n; i++)
          columns[dim].push(d.getFloat64(96 + (dim * n + i) * 8, true));
    }
    if (op === 3) {
      dimension = Number(d.getBigUint64(64, true));
      let at = 96;
      const n = Number(d.getBigUint64(at, true));
      at += 8 + n * 8;
      views = [];
      for (let i = 0n; i < d.getBigUint64(72, true); i++) {
        const id = d.getBigUint64(at, true),
          dim = Number(d.getBigUint64(at + 8, true)),
          n = Number(d.getBigUint64(at + 16, true));
        at += 24;
        const cuts = [];
        for (let j = 0; j < n; j++) {
          cuts.push(d.getFloat64(at, true));
          at += 8;
        }
        views.push({ id, dim, cuts });
      }
    }
    if (op === 5) {
      const a = d.getFloat64(80, true),
        b = d.getFloat64(88, true);
      intent = [Math.min(a, b), Math.max(a, b)];
    }
    if (op === 7) intent = null;
    if (![5, 7, 9].includes(op)) return;
    const selected = columns[dimension].map(
      (x) =>
        intent === null ||
        (Number.isFinite(x) && x >= intent[0] && x <= intent[1]),
    );
    if (op === 9) {
      const start = Number(result.pageFirst - first),
        n = Number(d.getBigUint64(64, true)),
        bits = new Uint8Array(Math.ceil(n / 8));
      let total = 0n;
      for (let i = 0; i < n; i++)
        if (selected[start + i]) {
          bits[i >> 3] |= 1 << (i & 7);
          total++;
        }
      assert.deepEqual(result.membership, bits);
      assert.equal(result.selectedCount, total);
      return;
    }
    assert.equal(result.selectedCount, BigInt(selected.filter(Boolean).length));
    for (let i = 0; i < views.length; i++) {
      const v = views[i],
        counts = Array(v.cuts.length + 1).fill(0n);
      for (let row = 0; row < selected.length; row++) {
        const value = columns[v.dim][row];
        if (!selected[row] || !Number.isFinite(value)) continue;
        let bin = 0;
        for (const cut of v.cuts) if (value >= cut) bin++;
        counts[bin]++;
      }
      assert.equal(result.views[i].id, v.id);
      assert.deepEqual([...result.views[i].counts], counts);
    }
  };
}
test("Filter Tier C native complete packets and independent scan-oracle counts", () => {
  const h = xyFilterSessionNew(1n << 20n),
    scan = scanOracle();
  try {
    records().forEach((r, i) => {
      if (r.status === -4) {
        assert.throws(
          () => executeFilterPacket(h, r.request, r.cap),
          (e) => e.status === -4 && e.required === r.required,
        );
        return;
      }
      const reply = executeFilterPacket(h, r.request, r.cap);
      assert.deepEqual(Buffer.from(reply), r.reply, manifest.cases[i].name);
      oracle(decodeFilterReply(reply), manifest.cases[i]);
      scan(r.request, decodeFilterReply(reply));
    });
  } finally {
    xyFilterSessionFree(h);
  }
});
test("Filter Tier C actual wasm32 complete packets and capacity atomicity", async () => {
  // Required in normal Node CI: a missing artifact fails, never silently skips.
  const { instance } = await WebAssembly.instantiate(
    fs.readFileSync(
      process.env.XYG_FILTER_WASM ??
        new URL("packages/xy-client/dist/xyg-wasm.wasm", root),
    ),
    {},
  );
  const x = instance.exports,
    h = x.xyg_wasm_instance_new(1 << 20),
    scan = scanOracle();
  try {
    records().forEach((r, i) => {
      assert.equal(x.xyg_wasm_arena_resize(h, r.request.length), 0);
      new Uint8Array(
        x.memory.buffer,
        x.xyg_wasm_arena_ptr(h) >>> 0,
        r.request.length,
      ).set(r.request);
      const status = x.xyg_wasm_filter_execute(h, 0, r.request.length, r.cap);
      const reply = new Uint8Array(
        x.memory.buffer,
        x.xyg_wasm_output_ptr(h) >>> 0,
        x.xyg_wasm_output_len(h) >>> 0,
      ).slice();
      if (r.status === -4) {
        assert.equal(status, 3);
        assert.equal(
          new DataView(reply.buffer).getBigUint64(0, true),
          r.required,
        );
        return;
      }
      assert.equal(status, 0, manifest.cases[i].name);
      assert.deepEqual(Buffer.from(reply), r.reply, manifest.cases[i].name);
      oracle(decodeFilterReply(reply), manifest.cases[i]);
      scan(r.request, decodeFilterReply(reply));
    });
  } finally {
    assert.equal(x.xyg_wasm_instance_dispose(h), 0);
  }
});
test("ordinary chart public session: counts, explicit exact boundary and persistent membership", () => {
  const chart = scatterChart([0, 1], [2, 3]);
  const s = chart.filterSession(
    { a: [0, 0.25, 0.5, 1], b: [3, 2, 1, 0] },
    { sourceId: 9n },
  );
  assert.ok(s instanceof FilterTierCSession);
  try {
    s.configure({ id: 1n, dimension: "a", cuts: [0, 1] }, [
      { id: 2n, dimension: "b", cuts: [1, 3] },
    ]);
    const r = s.range(0, 0.5);
    assert.equal(r.tier, 3n);
    assert.equal(r.rowsRead, 0n);
    assert.deepEqual([...r.views[0].counts], [0n, 2n, 1n]);
    assert.throws(
      () => s.range(0.1, 0.4),
      (e) => e instanceof FilterTierCError && e.status === 6,
    );
    assert.equal(s.range(0.1, 0.4, { exact: true }).selectedCount, 1n);
    s.append({ a: [0.2], b: [2] });
    assert.equal(s.membership(0n, 5).membership[0], 18);
    s.rebuild();
    assert.equal(s.range(0.1, 0.4, { exact: true }).selectedCount, 2n);
  } finally {
    s.close();
  }
});

test("empty/nonfinite sources: native and actual WASM public client packets match", async () => {
  const { FilterSessionClient } = await import("../src/filter-protocol.js");
  const { instance } = await WebAssembly.instantiate(
    fs.readFileSync(
      process.env.XYG_FILTER_WASM ??
        new URL("packages/xy-client/dist/xyg-wasm.wasm", root),
    ),
    {},
  );
  const x = instance.exports;
  for (const columns of [
    { a: [], b: [] },
    { a: [NaN, Infinity], b: [1, 2] },
  ]) {
    const native = xyFilterSessionNew(1n << 20n),
      wasm = x.xyg_wasm_instance_new(1 << 20);
    const nativeClient = new FilterSessionClient(
      (b) => executeFilterPacket(native, b),
      () => xyFilterSessionFree(native),
      columns,
      { sourceId: 9n, budgetBytes: 1n << 20n },
    );
    const wasmClient = new FilterSessionClient(
      (b) => {
        assert.equal(x.xyg_wasm_arena_resize(wasm, b.length), 0);
        new Uint8Array(
          x.memory.buffer,
          x.xyg_wasm_arena_ptr(wasm) >>> 0,
          b.length,
        ).set(b);
        assert.equal(x.xyg_wasm_filter_execute(wasm, 0, b.length, 1 << 20), 0);
        return new Uint8Array(
          x.memory.buffer,
          x.xyg_wasm_output_ptr(wasm) >>> 0,
          x.xyg_wasm_output_len(wasm) >>> 0,
        ).slice();
      },
      () => x.xyg_wasm_instance_dispose(wasm),
      columns,
      { sourceId: 9n, budgetBytes: 1n << 20n },
    );
    try {
      const steps = [
        (s) => s.initialize(columns),
        (s) =>
          s.configure({ id: 1n, dimension: "a", cuts: [] }, [
            { id: 2n, dimension: "b", cuts: [] },
          ]),
        (s) => s.range(0, 0),
        (s) => s.clear(),
        (s) => s.membership(0n, columns.a.length),
      ];
      for (let i = 0; i < steps.length; i++) {
        const a = steps[i](nativeClient),
          b = steps[i](wasmClient);
        assert.deepEqual(a.packet, b.packet);
        if (i === 2) assert.equal(a.selectedCount, 0n);
        if (i >= 3) assert.equal(a.selectedCount, BigInt(columns.a.length));
      }
    } finally {
      nativeClient.close();
      wasmClient.close();
    }
  }
});

test("invalid constructor input cannot exhaust the native session registry", () => {
  for (let i = 0; i < 70; i++) {
    assert.throws(() => new FilterTierCSession({ a: [0] }, { sourceId: -1n }));
    assert.throws(
      () => new FilterTierCSession({ a: [0], b: [] }, { sourceId: 9n }),
    );
  }
  const session = new FilterTierCSession({ a: [0] }, { sourceId: 9n });
  session.close();
});

test("native and WASM sessions cannot enlarge their owner resource ceiling", async () => {
  const { instance } = await WebAssembly.instantiate(
    fs.readFileSync(
      process.env.XYG_FILTER_WASM ??
        new URL("packages/xy-client/dist/xyg-wasm.wasm", root),
    ),
    {},
  );
  const x = instance.exports,
    wasm = x.xyg_wasm_instance_new(1024),
    native = xyFilterSessionNew(1024n);
  const packet = records()[0].request; // Declares a 1 MiB session, larger than either owner.
  try {
    const a = executeFilterPacket(native, packet);
    assert.equal(decodeFilterReply(a).status, 2);
    assert.equal(x.xyg_wasm_arena_resize(wasm, packet.length), 0);
    new Uint8Array(
      x.memory.buffer,
      x.xyg_wasm_arena_ptr(wasm) >>> 0,
      packet.length,
    ).set(packet);
    assert.equal(x.xyg_wasm_filter_execute(wasm, 0, packet.length, 1024), 0);
    const b = new Uint8Array(
      x.memory.buffer,
      x.xyg_wasm_output_ptr(wasm) >>> 0,
      x.xyg_wasm_output_len(wasm) >>> 0,
    );
    assert.deepEqual(a, b);
  } finally {
    xyFilterSessionFree(native);
    x.xyg_wasm_instance_dispose(wasm);
  }
});

test("malformed newer headers cannot poison native/WASM request watermarks", async () => {
  const { instance } = await WebAssembly.instantiate(
    fs.readFileSync(
      process.env.XYG_FILTER_WASM ??
        new URL("packages/xy-client/dist/xyg-wasm.wasm", root),
    ),
    {},
  );
  const x = instance.exports,
    wasm = x.xyg_wasm_instance_new(1 << 20),
    native = xyFilterSessionNew(1n << 20n);
  const source = records()[0].request,
    config = records()[1].request;
  const invalidOperation = Uint8Array.from(source.subarray(0, 96));
  const invalidFlags = invalidOperation.slice();
  const a = new DataView(invalidOperation.buffer),
    b = new DataView(invalidFlags.buffer);
  a.setUint32(8, 99, true);
  a.setBigUint64(16, 100n, true);
  b.setUint32(8, 5, true);
  b.setUint32(12, 2, true);
  b.setBigUint64(16, 101n, true);
  try {
    for (const packet of [source, invalidOperation, invalidFlags, config]) {
      const nativeReply = executeFilterPacket(native, packet);
      assert.equal(x.xyg_wasm_arena_resize(wasm, packet.length), 0);
      new Uint8Array(
        x.memory.buffer,
        x.xyg_wasm_arena_ptr(wasm) >>> 0,
        packet.length,
      ).set(packet);
      assert.equal(
        x.xyg_wasm_filter_execute(wasm, 0, packet.length, 1 << 20),
        0,
      );
      const wasmReply = new Uint8Array(
        x.memory.buffer,
        x.xyg_wasm_output_ptr(wasm) >>> 0,
        x.xyg_wasm_output_len(wasm) >>> 0,
      ).slice();
      assert.deepEqual(nativeReply, wasmReply);
    }
  } finally {
    xyFilterSessionFree(native);
    x.xyg_wasm_instance_dispose(wasm);
  }
});
