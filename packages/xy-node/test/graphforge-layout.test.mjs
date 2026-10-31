import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { after, test } from "node:test";
import { createHash } from "node:crypto";
import { GraphForgeLayoutController, graphforgeWebviewPayload, composeGraphForge,
  graphforgeGraphData, graphforgePick } from "../src/graphforge.js";
import { decodeContainer, encodeContainer, DTYPE } from "../src/graphforge-container.js";
import { decodeGraphForgeDocument } from "../src/graphforge.js";
import { graphForceCreate, graphForceTick, graphForceDestroy } from "../src/abi.js";

const root = new URL("../../../", import.meta.url);
const read = name => readFileSync(new URL(`tests/fixtures/graphforge/results/${name}.arrow`, root));
const manifest = JSON.parse(readFileSync(new URL("tests/fixtures/graphforge/results/manifest.json", root)));
const base = manifest.bases.cyclic;
const input = () => ({ base: { tables: [read(base.nodes), read(base.edges)], generation: base.generation } });
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const digest = p => createHash("sha256").update(Buffer.from(p.x.buffer)).update(Buffer.from(p.y.buffer)).digest("hex");

// Real native checks: scheduling changes must not introduce a second force pass.
test("default live API requires an owner, schedules revisioned native checkpoints and preserves source UUIDs", async () => {
  await assert.rejects(graphforgeWebviewPayload(composeGraphForge(input())), /requires.*owner/);
  const owner = new GraphForgeLayoutController();
  const c = composeGraphForge(input());
  const seen = [];
  const result = await graphforgeWebviewPayload(owner, input(), { iterations: 12, chunkSteps: 2,
    width: 480, height: 360, onPayload: p => { seen.push(p); } });
  assert.equal(seen[0].phase, "initial");
  assert.equal(seen.at(-1), result);
  assert.equal(result.phase, "complete");
  assert.equal(result.step, 12);
  assert.ok(seen.every(p => p.revision === 1 && p.jobId === result.jobId && p.spec.graph[0].layout === "preset"));
  assert.deepEqual(result.positions.uuid, c.nodes.uuid);
  assert.ok(result.buffer instanceof ArrayBuffer && result.buffer.byteLength > 0);
  const data = graphforgeGraphData(c);
  const h = graphForceCreate(data.nNodes, data.sources, data.targets, { algorithm: "force" });
  let expected;
  try { for (const p of seen) { const tick = graphForceTick(h, data.nNodes, p.step - (expected?.step ?? 0)); expected = { ...tick, step: p.step };
    assert.equal(digest(p.positions), digest(tick)); } } finally { graphForceDestroy(h); }
  assert.deepEqual(graphforgePick(result, c, { trace: result.nodeTrace, index: 0 }), c.identify("node", 0));
  assert.equal(graphforgePick(result, c, { trace: 999, index: 0 }), null);
  await owner.dispose();
});

test("presentation coalesces to latest source checkpoint while preserving initial/final and exact IDs", async () => {
  const owner = new GraphForgeLayoutController();
  const seen = [];
  await owner.render(input(), { iterations: 40, chunkSteps: 1, onPayload: async p => {
    seen.push(p); if (p.phase === "initial") await delay(300);
  } });
  assert.deepEqual(seen.map(p => p.phase), ["initial", "complete"]);
  assert.deepEqual(seen.map(p => p.step), [1, 40]);
  assert.equal(seen[0].jobId, seen[1].jobId);
  assert.equal(seen[0].revision, seen[1].revision);
  assert.notEqual(digest(seen[0].positions), digest(seen[1].positions));
  await owner.dispose();
});

test("concurrent owners, supersession, late callback and reload remain isolated", async () => {
  const a = new GraphForgeLayoutController(), b = new GraphForgeLayoutController();
  let release, firstSeen, oldCalls = 0;
  const atFirst = new Promise(r => { firstSeen = r; });
  const slow = a.render(input(), { iterations: 300, onPayload: () => { oldCalls++; firstSeen(); return new Promise(r => { release = r; }); } });
  const rejected = assert.rejects(slow, { code: "GF_LAYOUT_SUPERSEDED" });
  await atFirst;
  const [next, other] = await Promise.all([a.render(input(), { iterations: 3 }), b.render(input(), { iterations: 3, seed: 17 })]);
  await rejected;
  release(); await delay(20);
  assert.equal(oldCalls, 1);
  assert.notEqual(digest(next.positions), digest(other.positions));
  assert.equal(next.revision, 2); assert.equal(other.revision, 1);
  assert.notEqual(next.jobId, other.jobId);
  await Promise.all([a.dispose(), b.dispose()]);
  await assert.rejects(a.render(input()), { code: "GF_LAYOUT_DISPOSED" });
  const reload = new GraphForgeLayoutController();
  const fresh = await reload.render(input(), { iterations: 2 });
  assert.equal(fresh.revision, 1); assert.notEqual(fresh.jobId, other.jobId);
  await reload.dispose();
});

test("pre-abort, callback failure, cancellation, timeout and disposal are observable and terminal", async () => {
  for (const mode of ["pre-abort", "callback", "abort", "timeout", "dispose", "cancel"]) {
    const owner = new GraphForgeLayoutController(), ac = new AbortController();
    let calls = 0, disposal;
    const failure = new Error("consumer failed");
    if (mode === "pre-abort") ac.abort();
    const run = owner.render(input(), { iterations: 100, signal: ac.signal,
      maxWallMs: mode === "timeout" ? 1 : 10000,
      onPayload: () => { calls++; if (mode === "callback") throw failure;
        if (mode === "abort") ac.abort();
        if (mode === "dispose") disposal = owner.dispose();
        if (mode === "cancel") disposal = owner.cancel();
      } });
    await assert.rejects(run, e => mode === "callback" ? e === failure : /^GF_LAYOUT_/.test(e.code));
    await disposal;
    const terminalCalls = calls; await delay(25); assert.equal(calls, terminalCalls);
    if (mode === "pre-abort" || mode === "timeout") assert.equal(calls, 0);
    await owner.dispose();
  }
});

test("compound parent planes and bit-exact pins reach real CoSE; Aggregate retains full source positions", async () => {
  const c = composeGraphForge(input());
  const sections = [...decodeContainer(c.bytes, "XYGF").values()].map(s => ({ ...s, values: s.value }));
  const n = c.nodes.count;
  const parents = new Uint32Array(n), valid = new Uint8Array(n);
  for (let i = 1; i < n; i++) { parents[i] = 0; valid[i] = 1; }
  const patched = sections.filter(s => !["node.parent", "node.parent.valid"].includes(s.name));
  patched.push({ name: "node.parent", dtype: DTYPE.u32, values: parents }, { name: "node.parent.valid", dtype: DTYPE.u8, values: valid });
  const composed = decodeGraphForgeDocument(encodeContainer("XYGF", patched));
  assert.deepEqual(graphforgeGraphData(composed).parentIndices, BigUint64Array.from(parents, BigInt));
  const x = Float64Array.from({ length: n }, (_, i) => i + 0.125), y = Float64Array.from(x, v => v * 2);
  x[1] = -0; y[1] = 1 + 2 ** -52;
  const pinned = new Uint8Array(n); pinned[1] = 1;
  const owner = new GraphForgeLayoutController();
  const options = { layout: "cose", iterations: 10, chunkSteps: 1, pinned,
    cose: { gravityStrength: 0.02, coolingFactor: 0.98 }, positions: { uuid: c.nodes.uuid, x, y }, nodeBudget: 2 };
  const result = await owner.render(composed, options);
  assert.equal(result.positions.x[1], x[1]); assert.equal(result.positions.y[1], y[1]);
  assert.equal(result.positions.x.length, n);
  assert.equal(result.spec.graph[0].tier_name, "aggregate");
  const data = graphforgeGraphData(c);
  const h = graphForceCreate(n, data.sources, data.targets, { algorithm: "cose", x, y, pinned, cose: options.cose,
    parents: BigUint64Array.from(parents, (v, i) => valid[i] ? BigInt(v) : 0xffffffffffffffffn) });
  try { assert.equal(digest(result.positions), digest(graphForceTick(h, n, 10))); } finally { graphForceDestroy(h); }
  await owner.dispose();
});

const temp = mkdtempSync(join(tmpdir(), "xyg-graphforge-live-"));
after(() => rmSync(temp, { recursive: true, force: true }));
const src = name => new URL(`../src/${name}`, import.meta.url).href;
writeFileSync(join(temp, "register.mjs"), `import {register} from 'node:module'; register('./loader.mjs', import.meta.url);`);
writeFileSync(join(temp, "loader.mjs"), `
export async function resolve(s,c,next) {
 if (s === './native.js' && c.parentURL === ${JSON.stringify(src("graphforge.js"))}) return {url: new URL('./native.mjs',import.meta.url).href,shortCircuit:true};
 if (s === './abi.js' && [${JSON.stringify(src("graph.js"))},${JSON.stringify(src("force_scheduler.js"))}].includes(c.parentURL)) return {url: new URL('./abi.mjs',import.meta.url).href,shortCircuit:true};
 if (s === 'node:worker_threads' && [${JSON.stringify(src("graphforge_layout.js"))},${JSON.stringify(src("force_scheduler.js"))}].includes(c.parentURL)) return {url: new URL('./workers.mjs',import.meta.url).href,shortCircuit:true};
 return next(s,c);
}`);
writeFileSync(join(temp, "abi.mjs"), `
export * from ${JSON.stringify(src("abi.js"))};
import * as real from ${JSON.stringify(src("abi.js"))};
import {workerData,threadId,isMainThread} from 'node:worker_threads';
import {appendFileSync} from 'node:fs';
const trace = type => appendFileSync(process.env.GF_TRACE,JSON.stringify({type,threadId})+'\\n');
export function graphForceCreate(...a) { if(workerData?.type !== 'force_ticks') throw Error('force created outside scheduler worker'); trace('create'); return real.graphForceCreate(...a); }
export function graphBuildRender(...a) { if(isMainThread) throw Error('native packing ran on caller'); trace('pack'); return real.graphBuildRender(...a); }
export function graphForceTick(...a) { if(workerData?.type !== 'force_ticks') throw Error('force ran outside scheduler worker'); trace('tick'); return real.graphForceTick(...a); }
export function graphForceDestroy(...a) { real.graphForceDestroy(...a); trace('destroy'); }
`);
writeFileSync(join(temp, "native.mjs"), `
export * from ${JSON.stringify(src("native.js"))};
import * as real from ${JSON.stringify(src("native.js"))};
import {isMainThread} from 'node:worker_threads';
export function xyGraphforgeCompose(...a) { if(isMainThread) throw Error('composition ran on caller'); return real.xyGraphforgeCompose(...a); }
`);
writeFileSync(join(temp, "workers.mjs"), `
export * from 'node:worker_threads';
import {Worker as Real,threadId} from 'node:worker_threads';
import {appendFileSync} from 'node:fs';
export class Worker extends Real { constructor(...a) { super(...a); const child=this.threadId; this.on('message',msg=>{ if(threadId===0 && process.env.GF_LATE==='1' && msg.type==='payload' && msg.revision!==0) setImmediate(()=>this.emit('message',{...msg,revision:0,jobId:'retired',payload:{...msg.payload,revision:0,jobId:'retired'}})); }); this.on('exit',()=>appendFileSync(process.env.GF_TRACE,JSON.stringify({type:'exit',threadId,child})+'\\n')); } }
`);

test("real workers only: force trap, no second force packing, native destruction and both exits precede teardown", () => {
  for (const mode of ["complete", "dispose", "throw", "timeout", "late-reply"]) {
    const log = join(temp, `${mode}.jsonl`);
    writeFileSync(log, "");
    const script = join(temp, `${mode}.mjs`);
    writeFileSync(script, `
import {GraphForgeLayoutController} from ${JSON.stringify(src("graphforge.js"))};
import {readFileSync,appendFileSync} from 'node:fs';
const owner=new GraphForgeLayoutController(); const mode=${JSON.stringify(mode)};
const nodes=readFileSync(${JSON.stringify(new URL(`tests/fixtures/graphforge/results/${base.nodes}.arrow`, root).pathname)});
const edges=readFileSync(${JSON.stringify(new URL(`tests/fixtures/graphforge/results/${base.edges}.arrow`, root).pathname)});
try { await owner.render({base:{tables:[nodes,edges],generation:${JSON.stringify(base.generation)}}}, {iterations:40,chunkSteps:1,maxWallMs: mode==='timeout'?500:10000,
 onPayload: async p=>{ if(p.revision!==1 || p.jobId==='retired') throw Error('stale reply accepted'); if(mode==='dispose') owner.dispose(); if(mode==='throw') throw Error('callback'); if(mode==='timeout') await new Promise(()=>{}); }
}); if(!['complete','late-reply'].includes(mode)) throw Error('expected failure'); } catch(e) { if(['complete','late-reply'].includes(mode)) throw e; }
await owner.dispose(); appendFileSync(process.env.GF_TRACE,JSON.stringify({type:'settled'})+'\\n');
`);
    const result = spawnSync(process.execPath, ["--import", join(temp, "register.mjs"), script], { env: { ...process.env, GF_TRACE: log, GF_LATE: mode === "late-reply" ? "1" : "0" }, encoding: "utf8", timeout: 15000 });
    assert.equal(result.status, 0, result.stderr);
    const rows = readFileSync(log, "utf8").trim().split("\n").map(JSON.parse);
    const destroy = rows.findIndex(r => r.type === "destroy");
    const exits = rows.map((r, i) => r.type === "exit" ? i : -1).filter(i => i >= 0);
    assert.ok(destroy >= 0, JSON.stringify(rows)); assert.equal(exits.length, 2);
    assert.equal(rows.filter(r => r.type === "create").length, 1);
    assert.ok(rows.some(r => r.type === "pack"));
    assert.ok(exits.every(i => i > destroy && i < rows.length - 1));
    assert.equal(rows.at(-1).type, "settled");
    assert.equal(rows.filter(r => r.type === "tick").every(r => r.threadId !== 0), true);
  }
});

test("existing CoSE golden/options remain bit-exact in the reused real native worker", async () => {
  const { runForceTicks } = await import('../src/force_scheduler.js');
  const golden = JSON.parse(readFileSync(new URL('tests/fixtures/graphforge/cose-parity/golden.json', root)));
  for (const c of golden.cases) {
    const result = await runForceTicks({ nNodes: c.nNodes,
      sources: BigUint64Array.from(c.sources, BigInt), targets: BigUint64Array.from(c.targets, BigInt),
      algorithm: 'cose', seed: c.seed, cose: c.cose,
      x: c.x ? Float64Array.from(c.x) : undefined, y: c.y ? Float64Array.from(c.y) : undefined,
      pinned: c.pinned ? Uint8Array.from(c.pinned) : undefined,
      parents: c.parents ? BigUint64Array.from(c.parents, v => v === null ? 0xffffffffffffffffn : BigInt(v)) : undefined,
      totalSteps: 60, chunkSteps: 1 });
    assert.deepEqual([...result.x], c.expected.x, c.name);
    assert.deepEqual([...result.y], c.expected.y, c.name);
  }
});

test("explicit static layouts and analytical intents still pack off-loop without force", async () => {
  const owner = new GraphForgeLayoutController();
  const circle = await owner.render(input(), { layout: 'circle' });
  assert.equal(circle.phase, 'complete'); assert.equal(circle.step, 0);
  assert.ok(circle.positions.uuid.length > 0);
  const bars = await owner.render({ layers: [{ result: read('triad_census'), intent: 'bar-chart' }] });
  assert.equal(bars.phase, 'complete'); assert.equal(bars.nodeTrace, null);
  assert.ok(bars.buffer.byteLength > 0);
  await assert.rejects(owner.render({ ...input(), render: { width: 480, height: 360 } }), /live input must omit render/);
  await assert.rejects(owner.render(input(), { positions: { uuid: [], x: [], y: [] } }), /cover every composed UUID/);
  await owner.dispose();
});
