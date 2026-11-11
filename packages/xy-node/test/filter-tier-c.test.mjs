import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ChunkedColumns } from "../src/chunked-columns.js";
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

test("issued XYGC planes preserve five-view native counts, source leases and canonical membership", () => {
  const dir = fs.mkdtempSync(join(tmpdir(), "xyg-filter-paged-"));
  const path = join(dir, "source.xygc"), n = 4099, chunkRows = 128;
  const xs = Float64Array.from({ length: n }, (_, i) => i === 32 ? NaN : i);
  const ys = Float64Array.from({ length: n }, (_, i) => i === 65 ? Infinity : i % 19);
  const chunks = Math.ceil(n / chunkRows), offset = 64 + 48 * chunks;
  const bytes = Buffer.alloc(offset + n * 16);
  bytes.write("XYGC"); bytes.writeUInt32LE(1, 4); bytes.writeBigUInt64LE(BigInt(n), 8);
  bytes.writeUInt32LE(chunkRows, 16); bytes.writeUInt32LE(chunks, 20); bytes.writeBigUInt64LE(BigInt(offset), 24);
  for (let c = 0; c < chunks; c++) {
    const start = c * chunkRows, end = Math.min(n, start + chunkRows), at = 64 + c * 48;
    const x = Array.from(xs.subarray(start, end)).filter(Number.isFinite);
    const y = Array.from(ys.subarray(start, end)).filter(Number.isFinite);
    bytes.writeBigUInt64LE(BigInt(start), at); bytes.writeUInt32LE(end - start, at + 8);
    [Math.min(...x), Math.max(...x), Math.min(...y), Math.max(...y)].forEach((v, i) => bytes.writeDoubleLE(v, at + 16 + i * 8));
  }
  for (let i = 0; i < n; i++) { bytes.writeDoubleLE(xs[i], offset + i * 16); bytes.writeDoubleLE(ys[i], offset + i * 16 + 8); }
  fs.writeFileSync(path, bytes);
  const source = new ChunkedColumns(path), chart = scatterChart([0], [0]);
  let paged, resident;
  const same = (a, b) => {
    const x = Buffer.from(a.packet), y = Buffer.from(b.packet);
    x.fill(0, 80, 96); y.fill(0, 80, 96); assert.deepEqual(x, y);
  };
  try {
    const options = { sourceId: 77n, firstRow: (1n << 63n) + 17n, budgetBytes: 1n << 20n };
    assert.throws(() => source.column("other"), /plane/);
    assert.throws(() => chart.filterSession({ x: source.column("x"), y: ys }, options), /all arrays or all issued/);
    paged = chart.filterSession({ x: source.column("x"), y: source.column("y") }, options);
    resident = chart.filterSession({ x: xs, y: ys }, options);
    source.close();
    const active = { id: 1n, dimension: "x", cuts: [1024, 2048, 3072] };
    const views = Array.from({ length: 5 }, (_, i) => ({ id: BigInt(i + 1), x: "x", y: "y", width: 8, height: 4, xRange: [0, 4100], yRange: [0, 20] }));
    same(paged.configureDensity(active, views), resident.configureDensity(active, views));
    same(paged.range(1024, 2047), resident.range(1024, 2047));
    const paint = paged.paint();
    assert.equal(paint.selectedCount, 1024n); assert.equal(paint.rowsRead, 0n); assert.equal(paint.tier, 3n);
    same(paint, resident.paint());
    const members = paged.membership(options.firstRow + 30n, 2050n);
    same(members, resident.membership(options.firstRow + 30n, 2050n));
    for (let i = 0; i < 2050; i++) assert.equal(!!(members.membership[i >> 3] & (1 << (i & 7))), xs[i + 30] >= 1024 && xs[i + 30] <= 2047);
    same(paged.evict(), resident.evict()); same(paged.rebuild(), resident.rebuild());
    same(paged.range(1100.25, 2090.5, { exact: true }), resident.range(1100.25, 2090.5, { exact: true }));
    assert.throws(() => paged.append({ x: [4100], y: [1] }), (e) => e.status === 7);
    assert.throws(() => chart.filterSession({ x: source.column("x") }, options), (e) => e.status === 7);
  } finally {
    paged?.close(); resident?.close(); source.close(); fs.rmSync(dir, { recursive: true, force: true });
  }
});
function records(bytes = stream) {
  const out = [];
  let at = 0;
  while (at < bytes.length) {
    const n = bytes.readUInt32LE(at),
      cap = bytes.readUInt32LE(at + 4),
      status = bytes.readInt32LE(at + 8),
      replyN = bytes.readUInt32LE(at + 12),
      required = bytes.readBigUInt64LE(at + 16);
    at += 24;
    const request = bytes.subarray(at, at + n);
    at += n;
    const reply = bytes.subarray(at, at + replyN);
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


test("Filter Tier C cooperative actual WASM preserves packets, capacity, cancellation and recovery",async()=>{
const {filterRequest,filterDensityConfig,filterColumns}=await import("../src/filter-protocol.js");
const {instance}=await WebAssembly.instantiate(fs.readFileSync(process.env.XYG_FILTER_WASM??new URL("packages/xy-client/dist/xyg-wasm.wasm",root)));const x=instance.exports;
const budget=16<<20, h=x.xyg_wasm_instance_new(budget), sync=x.xyg_wasm_instance_new(budget);
function call(handle,packet,capacity=budget){assert.equal(x.xyg_wasm_arena_resize(handle,packet.length),0);
 new Uint8Array(x.memory.buffer,x.xyg_wasm_arena_ptr(handle),packet.length).set(packet);
 const status=x.xyg_wasm_filter_execute(handle,0,packet.length,capacity);
 const output=new Uint8Array(x.memory.buffer,x.xyg_wasm_output_ptr(handle),x.xyg_wasm_output_len(handle)).slice();
 assert.equal(x.xyg_wasm_arena_resize(handle,0),0);return{status,output};}
function envelope(op,token=0n,packet=new Uint8Array()) {const b=new Uint8Array(32+packet.length),d=new DataView(b.buffer);b.set([88,89,70,74]);d.setUint32(4,1,true);d.setUint32(8,op,true);d.setBigUint64(16,token,true);b.set(packet,32);return b;}
function control(op,token){return call(h,envelope(op,token));}
function request(op,revision,args=[],range=[0,0],exact=false,payload=new Uint8Array()){
 return filterRequest(op,{revision:BigInt(revision),sourceId:1n,epoch:2n,budgetBytes:BigInt(budget),args,range,exact},payload);}
let turns=0;let semanticPackets=0;
function finish(reply){while(String.fromCharCode(...reply.output.subarray(0,4))==='XYFJ'){
 assert.equal(reply.status,0);const d=new DataView(reply.output.buffer);assert.equal(reply.output.length,32);
 const token=d.getBigUint64(8,true);assert(d.getBigUint64(16,true)<=d.getBigUint64(24,true));
 reply=control(2,token);turns++;assert(turns<3000);
}return reply;}
function same(packet){semanticPackets++;const a=call(sync,packet),b=finish(call(h,envelope(1,0n,packet)));assert.equal(a.status,b.status);
 if(a.status===0){a.output.fill(0,88,96);b.output.fill(0,88,96);}assert.deepEqual(b.output,a.output);return decodeFilterReply(a.output);}
try{
 const n=50003,columns={x:Float64Array.from({length:n},(_,i)=>i%37),y:Float64Array.from({length:n},(_,i)=>i%41-2)};
 same(request(1,1,[2n,BigInt(n),99n],[0,0],false,filterColumns(columns)));
 const names=['x','y'],active={id:1n,dimension:'x',cuts:[0,18]}, views=Array.from({length:5},(_,i)=>({id:BigInt(i+1),x:i%2?'y':'x',y:i%2?'x':'y',width:4,height:4,xRange:[-6,38],yRange:[-6,38]}));
 same(request(10,2,[1n,0n,5n],[0,0],false,filterDensityConfig(names,active,views)));
 assert.equal(same(request(5,3,[],[4,12],true)).fallback,1n);
 same(request(9,4,[1099n,40001n]));same(request(6,5));same(request(11,6,[],[0,0],true));
 // A real output-capacity refusal and wrong token retain the same job.
 same(request(6,7));const start=call(h,envelope(1,0n,request(11,8,[],[0,0],true)));
 assert.equal(String.fromCharCode(...start.output.subarray(0,4)),'XYFJ');
 const short=call(h,envelope(2,8n),1);assert.equal(short.status,3);assert.equal(short.output.length,8);
 assert.equal(decodeFilterReply(control(2,999n).output).status,3);
 assert.equal(x.xyg_wasm_arena_resize(h,budget),3);
 const bad=request(4,999);new DataView(bad.buffer).setUint32(4,99,true);
 assert.equal(decodeFilterReply(call(h,envelope(1,0n,bad)).output).newestRevision,8n);
 assert.equal(decodeFilterReply(control(3,8n).output).status,4);
 assert.equal(decodeFilterReply(control(2,8n).output).status,5);
 // The accepted filter remains usable, while the consumed old revision stays stale.
 assert.equal(decodeFilterReply(call(h,request(11,9,[],[0,0],true)).output).status,0);
 // Interleaved malformed packets cannot erase this job's initial peak.
 const wide=views.map(v=>({...v,width:32,height:32}));
 const configuration=request(10,10,[1n,0n,5n],[0,0],false,filterDensityConfig(names,active,wide));
 const pending=call(h,envelope(1,0n,configuration));
 assert.equal(String.fromCharCode(...pending.output.subarray(0,4)),'XYFJ');
 const capturePeak=decodeFilterReply(control(2,1000n).output).peakBytes;
 const malformed=request(4,1000);new DataView(malformed.buffer).setUint32(4,99,true);
 assert.equal(decodeFilterReply(call(h,envelope(1,0n,malformed)).output).status,1);
 const finished=decodeFilterReply(finish(control(2,10n)).output);
 assert.equal(finished.status,0);assert(finished.peakBytes>=capturePeak,'interleaved refusal erased captured peak');
 assert.equal(semanticPackets,7);assert(turns>50);assert.equal(x.xyg_wasm_abi_version(),38);
}finally{assert.equal(x.xyg_wasm_instance_dispose(h),0);assert.equal(x.xyg_wasm_instance_dispose(sync),0);}

});

test("cooperative actual WASM preserves complete legacy and linked edit/base-mask fixture transactions", async () => {
  const { instance } = await WebAssembly.instantiate(fs.readFileSync(
    process.env.XYG_FILTER_WASM ?? new URL("packages/xy-client/dist/xyg-wasm.wasm", root),
  ));
  const x = instance.exports;
  let packets = 0, continuations = 0;
  for (const file of ["session.bin", "density.bin"]) {
    const cases = records(fs.readFileSync(new URL(`tests/fixtures/filter_tier_c/${file}`, root)));
    const specification = JSON.parse(fs.readFileSync(new URL(
      `tests/fixtures/filter_tier_c/${file === "session.bin" ? "manifest.json" : "density.json"}`, root,
    )));
    assert.equal(cases.length, specification.cases.length);
    const native = xyFilterSessionNew(1n << 20n);
    const wasm = x.xyg_wasm_instance_new(1 << 20);
    assert(native && wasm);
    const call = (op, token, payload, capacity) => {
      const b = new Uint8Array(32 + payload.length), d = new DataView(b.buffer);
      b.set([88, 89, 70, 74]); d.setUint32(4, 1, true);
      d.setUint32(8, op, true); d.setBigUint64(16, token, true); b.set(payload, 32);
      assert.equal(x.xyg_wasm_arena_resize(wasm, b.length), 0);
      new Uint8Array(x.memory.buffer, x.xyg_wasm_arena_ptr(wasm), b.length).set(b);
      const status = x.xyg_wasm_filter_execute(wasm, 0, b.length, capacity);
      const output = new Uint8Array(x.memory.buffer, x.xyg_wasm_output_ptr(wasm), x.xyg_wasm_output_len(wasm)).slice();
      assert.equal(x.xyg_wasm_arena_resize(wasm, 0), 0);
      return { status, output };
    };
    try {
      for (const [i, r] of cases.entries()) {
        packets++;
        let result = call(1, 0n, r.request, r.cap);
        while (result.status === 0 && Buffer.from(result.output.subarray(0, 4)).toString() === "XYFJ") {
          assert.equal(result.output.length, 32);
          const d = new DataView(result.output.buffer);
          assert(d.getBigUint64(16, true) <= d.getBigUint64(24, true));
          continuations++;
          assert(continuations < 10_000, "fixture transaction did not finish");
          result = call(2, d.getBigUint64(8, true), new Uint8Array(), r.cap);
        }
        if (r.status === -4) {
          assert.throws(() => executeFilterPacket(native, r.request, r.cap),
            e => e.status === -4 && e.required === r.required);
          assert.equal(result.status, 3, `${file}:${i}`);
          assert.equal(result.output.length, 8);
          assert.equal(new DataView(result.output.buffer).getBigUint64(0, true), r.required);
        } else {
          assert.equal(result.status, 0, `${file}:${i}`);
          const expected = Buffer.from(executeFilterPacket(native, r.request, r.cap));
          assert.deepEqual(expected, r.reply, `${file}:${i}: native fixture`);
          const actual = Buffer.from(result.output);
          // Private cooperative captures have their own admitted high water.
          // Every semantic field, retained owner, count, mask and paint byte agrees.
          actual.fill(0, 88, 96); expected.fill(0, 88, 96);
          assert.deepEqual(actual, expected, `${file}:${i}: cooperative fixture`);
        }
      }
    } finally {
      xyFilterSessionFree(native);
      assert.equal(x.xyg_wasm_instance_dispose(wasm), 0);
    }
  }
  assert(packets >= 100);
  assert(continuations > 10);
});
