import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import {
  executeFilterPacket,
  decodeFilterReply,
} from "../src/filter-session.js";
import { xyFilterSessionNew, xyFilterSessionFree } from "../src/native.js";
import { scatterChart } from "../src/index.js";
const root = new URL("../../../", import.meta.url);
const bytes = fs.readFileSync(
  new URL("tests/fixtures/filter_tier_c/density.bin", root),
);
function records() {
  let at = 0;
  const out = [];
  while (at < bytes.length) {
    const n = bytes.readUInt32LE(at),
      cap = bytes.readUInt32LE(at + 4),
      code = bytes.readInt32LE(at + 8),
      size = bytes.readUInt32LE(at + 12),
      needed = bytes.readBigUInt64LE(at + 16);
    at += 24;
    const input = bytes.subarray(at, at + n);
    at += n;
    const expected = bytes.subarray(at, at + size);
    at += size;
    out.push({ input, cap, code, needed, expected });
  }
  return out;
}
test("linked density complete native and actual WASM packets including capacity atomicity", async () => {
  const { instance } = await WebAssembly.instantiate(
      fs.readFileSync(new URL("packages/xy-client/dist/xyg-wasm.wasm", root)),
      {},
    ),
    x = instance.exports;
  const native = xyFilterSessionNew(1n << 20n),
    wasm = x.xyg_wasm_instance_new(1 << 20);
  try {
    for (const r of records()) {
      let actual;
      if (r.code)
        assert.throws(
          () => executeFilterPacket(native, r.input, r.cap),
          (e) => e.status === -4 && e.required === r.needed,
        );
      else {
        actual = executeFilterPacket(native, r.input, r.cap);
        assert.deepEqual(Buffer.from(actual), r.expected);
        decodeFilterReply(actual);
      }
      assert.equal(x.xyg_wasm_arena_resize(wasm, r.input.length), 0);
      new Uint8Array(
        x.memory.buffer,
        x.xyg_wasm_arena_ptr(wasm) >>> 0,
        r.input.length,
      ).set(r.input);
      const code = x.xyg_wasm_filter_execute(wasm, 0, r.input.length, r.cap);
      const reply = new Uint8Array(
        x.memory.buffer,
        x.xyg_wasm_output_ptr(wasm) >>> 0,
        x.xyg_wasm_output_len(wasm),
      ).slice();
      if (r.code) {
        assert.equal(code, 3);
        assert.equal(
          new DataView(reply.buffer).getBigUint64(0, true),
          r.needed,
        );
      } else {
        assert.equal(code, 0);
        assert.deepEqual(Buffer.from(reply), r.expected);
      }
    }
  } finally {
    xyFilterSessionFree(native);
    x.xyg_wasm_instance_dispose(wasm);
  }
});
test("public Node composed views share source identity, 2D exact planes and transaction cancellation", () => {
  const cols = {
    a: [-1, -0, 0, 0.25, 0.5, 1, NaN],
    b: [1, 0, 0, 0.5, -1, 0.25, 1],
  };
  const chart = scatterChart(cols.a, cols.b, { density: true });
  const s = chart.filterSession(cols, {
    sourceId: 112n,
    firstRow: (1n << 64n) - 100n,
  });
  const grids = [
    {
      id: 1n,
      x: "a",
      y: "b",
      width: 4,
      height: 4,
      xRange: [-2, 2],
      yRange: [-2, 2],
    },
    {
      id: 2n,
      x: "b",
      y: "a",
      width: 4,
      height: 4,
      xRange: [-2, 2],
      yRange: [2, -2],
    },
  ];
  try {
    s.configureDensity({ id: 1n, dimension: "a", cuts: [-1, 0, 1] }, grids);
    s.range(-0, 0, { exact: true });
    const original = s.paint({ exact: true });
    assert.equal(original.selectedCount, 2n);
    s.beginEdit();
    s.configureDensity({ id: 2n, dimension: "b", cuts: [-1, 0, 1] }, grids);
    s.range(0, 0, { exact: true });
    assert.equal(s.paint({ exact: true }).selectedCount, 2n);
    s.cancelEdit();
    const restored = s.paint({ exact: true });
    assert.equal(restored.filterHash, original.filterHash);
    s.clear();
    s.range(0.1, 0.6, { exact: true });
    const reply = s.paint({ exact: true });
    const selected = cols.a.map(
      (_, i) =>
        Number.isFinite(cols.b[i]) && cols.b[i] >= 0.1 && cols.b[i] <= 0.6,
    );
    assert.equal(reply.selectedCount, BigInt(selected.filter(Boolean).length));
    for (const grid of grids) {
      const plane = reply.density.find((p) => p.id === grid.id);
      const totals = Array(16).fill(0n),
        counts = Array(16).fill(0n);
      for (let row = 0; row < cols.a.length; row++) {
        const xx = cols[grid.x][row],
          yy = cols[grid.y][row];
        for (let y = 0; y < 4; y++)
          for (let x = 0; x < 4; x++)
            if (xx >= -2 + x && xx < -1 + x && yy >= -2 + y && yy < -1 + y) {
              totals[y * 4 + x]++;
              if (selected[row]) counts[y * 4 + x]++;
            }
      }
      assert.deepEqual([...plane.totals], totals);
      assert.deepEqual([...plane.selected], counts);
    }
    assert.equal(
      s.membership((1n << 64n) - 100n, 7).membership[0],
      selected.reduce((b, v, i) => b | (v ? 1 << i : 0), 0),
    );
  } finally {
    s.close();
  }
});

import { FilterSessionClient } from "../src/filter-protocol.js";
function wasmTransport(x, h) {
  return (packet) => {
    assert.equal(x.xyg_wasm_arena_resize(h, packet.length), 0);
    new Uint8Array(
      x.memory.buffer,
      x.xyg_wasm_arena_ptr(h) >>> 0,
      packet.length,
    ).set(packet);
    assert.equal(x.xyg_wasm_filter_execute(h, 0, packet.length, 1 << 20), 0);
    return new Uint8Array(
      x.memory.buffer,
      x.xyg_wasm_output_ptr(h) >>> 0,
      x.xyg_wasm_output_len(h),
    ).slice();
  };
}
test("empty/nonfinite/arbitrary f64 independent density oracles and active×passive admission in both public clients", async () => {
  const { instance } = await WebAssembly.instantiate(
      fs.readFileSync(new URL("packages/xy-client/dist/xyg-wasm.wasm", root)),
      {},
    ),
    x = instance.exports;
  for (const n of [0, 3, 129]) {
    const cols = {
      a: Array.from({ length: n }, (_, i) => ((i * 137) % 1024) / 256 - 2),
      b: Array.from({ length: n }, (_, i) => ((i * 313) % 1024) / 256 - 2),
    };
    if (n === 3) cols.a = [NaN, Infinity, -Infinity];
    if (n === 129) {
      cols.a[0] = -0;
      cols.a[1] = 0;
      cols.a[2] = NaN;
      cols.b[3] = Infinity;
    }
    const options = {
        sourceId: 112n,
        epoch: 7n,
        firstRow: (1n << 64n) - 1024n,
        budgetBytes: 1n << 20n,
      },
      h = x.xyg_wasm_instance_new(1 << 20),
      native = scatterChart([0], [0]).filterSession(cols, options);
    const wasm = new FilterSessionClient(
      wasmTransport(x, h),
      () => x.xyg_wasm_instance_dispose(h),
      cols,
      options,
    );
    wasm.initialize(cols);
    const grids = Array.from({ length: 5 }, (_, i) => ({
      id: BigInt(i + 1),
      x: i % 2 ? "b" : "a",
      y: i % 2 ? "a" : "b",
      width: i % 2 ? 8 : 4,
      height: 4,
      xRange: [2, -2],
      yRange: [-2, 2],
    }));
    const both = (method, ...args) => {
      const results = [native, wasm].map((s) => {
        try {
          return s[method](...args);
        } catch (e) {
          if (!e.reply) throw e;
          return e.reply;
        }
      });
      assert.deepEqual(
        Buffer.from(results[0].packet),
        Buffer.from(results[1].packet),
      );
      return results[0];
    };
    try {
      both(
        "configureDensity",
        { id: 1n, dimension: "a", cuts: [-1, 0, 1] },
        grids,
      );
      for (const [lo, hi] of [
        [-0, 0],
        [1, -1],
        [0.1, 0.6],
        [-3, 3],
        [4, 5],
        [Number.MIN_VALUE, 0.5],
        [-Number.MIN_VALUE, 0],
      ]) {
        const response = both("range", lo, hi, { exact: true });
        assert.equal(response.status, 0);
        const paint = both("paint", { exact: true }),
          selected = cols.a.map(
            (v) =>
              Number.isFinite(v) &&
              v >= Math.min(lo, hi) &&
              v <= Math.max(lo, hi),
          );
        assert.equal(
          paint.selectedCount,
          BigInt(selected.filter(Boolean).length),
        );
        for (const g of grids) {
          const p = paint.density.find((p) => p.id === g.id),
            counts = Array(g.width * g.height).fill(0n),
            totals = Array(g.width * g.height).fill(0n);
          for (let row = 0; row < n; row++)
            for (let y = 0; y < g.height; y++)
              for (let xx = 0; xx < g.width; xx++)
                if (
                  cols[g.x][row] >= -2 + (4 * xx) / g.width &&
                  cols[g.x][row] < -2 + (4 * (xx + 1)) / g.width &&
                  cols[g.y][row] >= -2 + y &&
                  cols[g.y][row] < -1 + y
                ) {
                  totals[y * g.width + xx]++;
                  if (selected[row]) counts[y * g.width + xx]++;
                }
          assert.deepEqual([...p.selected], counts);
          assert.deepEqual([...p.totals], totals);
        }
        const page = both("membership", options.firstRow, n);
        for (let i = 0; i < n; i++)
          assert.equal(
            Boolean(page.membership[i >> 3] & (1 << (i & 7))),
            selected[i],
          );
      }
      both(
        "configureDensity",
        { id: 1n, dimension: "a", cuts: [-1, 0, 1] },
        grids.map((g) => ({
          ...g,
          colors: [20, 30, 40, 255, 200, 100, 50, 0],
        })),
      );
      both("range", -3, 3, { exact: true });
      assert.ok(
        both("paint", { exact: true }).density.every((p) =>
          p.rgba.every((v, i) => i % 4 !== 3 || v === 0),
        ),
      );
      for (const endpoint of [NaN, Infinity, -Infinity])
        assert.equal(both("range", endpoint, 0, { exact: true }).status, 1);
      const before = both("paint", { exact: true });
      const refused = both(
        "configureDensity",
        {
          id: 1n,
          dimension: "a",
          cuts: Array.from({ length: 4096 }, (_, i) => i),
        },
        grids.map((g) => ({ ...g, width: 32, height: 32 })),
      );
      assert.equal(refused.status, 2);
      assert.equal(refused.revision, before.revision);
      assert.equal(refused.indexBytes, before.indexBytes);
      assert.equal(refused.filterHash, before.filterHash);
      assert.equal(
        both("paint", { exact: true }).selectedCount,
        before.selectedCount,
      );
      both("evict");
      const cold = both("paint", { exact: true });
      assert.equal(cold.tier, 2n);
      assert.equal(cold.fallback, 4n);
      assert.equal(cold.selectedCount, before.selectedCount);
      const cleared = both("clear");
      assert.equal(cleared.tier, 2n);
      assert.equal(cleared.selectedCount, BigInt(n));
    } finally {
      native.close();
      wasm.close();
    }
  }
});
test("300 mutated linked requests preserve complete native/WASM refusal and publication parity", async () => {
  const { instance } = await WebAssembly.instantiate(
      fs.readFileSync(new URL("packages/xy-client/dist/xyg-wasm.wasm", root)),
      {},
    ),
    x = instance.exports,
    seedRecords = records().slice(0, 2);
  let random = 112;
  const next = () => {
    random = (Math.imul(random, 1664525) + 1013904223) >>> 0;
    return random;
  };
  for (let i = 0; i < 300; i++) {
    const native = xyFilterSessionNew(1n << 20n),
      h = x.xyg_wasm_instance_new(1 << 20),
      transport = wasmTransport(x, h);
    try {
      for (const r of seedRecords) {
        assert.deepEqual(
          Buffer.from(executeFilterPacket(native, r.input, 65536)),
          r.expected,
        );
        assert.deepEqual(Buffer.from(transport(r.input)), r.expected);
      }
      const input = Uint8Array.from(
        i % 2 ? seedRecords[1].input : records()[2].input,
      );
      new DataView(input.buffer).setBigUint64(16, 3n, true);
      for (let j = 0; j < 1 + (i % 3); j++)
        input[next() % input.length] ^= 1 << next() % 8;
      const a = executeFilterPacket(native, input, 65536),
        b = transport(input);
      assert.deepEqual(Buffer.from(a), Buffer.from(b), `mutation ${i}`);
    } finally {
      xyFilterSessionFree(native);
      x.xyg_wasm_instance_dispose(h);
    }
  }
});
