import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { after, test } from "node:test";
import { createHash } from "node:crypto";
import { GraphForgeLayoutController, graphforgeWebviewPayload, composeGraphForge,
  graphforgeGraphData, graphforgePick, graphforgeStaticPayload } from "../src/graphforge.js";
import { decodeContainer, encodeContainer, DTYPE } from "../src/graphforge-container.js";
import { decodeGraphForgeDocument } from "../src/graphforge.js";
import { graphForceCreate, graphForceTick, graphForceDestroy, graphLayout } from "../src/abi.js";

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

test("render-node membership resolves viewport source 3 to row 0, with exact UUID and provenance", async () => {
  const c = composeGraphForge({ ...input(), layers: [{ result: read("pagerank"), intent: "graph",
    generation: base.generation, resultId: "viewport-rank" }] });
  const positions = { uuid: c.nodes.uuid, x: new Float64Array([0, 100, 200, 300]), y: new Float64Array(4) };
  const opts = { layout: "preset", positions, viewport: [299, -1, 301, 1] };
  const owner = new GraphForgeLayoutController();
  try {
    const live = await owner.render(c, opts);
    const batch = graphforgeStaticPayload(c, opts);
    assert.equal(live.spec.graph[0].tier_name, "edge_sample");
    assert.equal(live.spec.graph[0].n_nodes, 1);
    for (const payload of [live, batch]) {
      const target = payload.figure ?? payload;
      assert.deepEqual(graphforgePick(target, c, { trace: payload.nodeTrace, index: 0 }), c.identify("node", 3));
      assert.ok(graphforgePick(target, c, { trace: payload.nodeTrace, index: 0 }).layers.length > 0);
      for (const index of [1, 3, -1, 0.5]) assert.equal(graphforgePick(target, c, { trace: payload.nodeTrace, index }), null);
    }
    assert.equal(digest(live.positions), digest(positions));
    assert.equal(live.pickData.nodes[0].uuid, c.nodes.uuid[3]);
  } finally { await owner.dispose(); }
});

test("Direct, EdgeSample and Aggregate keep distinct render membership, node bounds and exact edge semantics", async () => {
  const c = composeGraphForge(input());
  const positions = { uuid: c.nodes.uuid, x: new Float64Array([0, 1, 2, 3]), y: new Float64Array([0, 1, 0, 1]) };
  const owner = new GraphForgeLayoutController();
  try {
    for (const [tier, budget] of [["direct", {}], ["edge_sample", { edgeBudget: 2 }], ["aggregate", { nodeBudget: 2 }]]) {
      const opts = { layout: "preset", positions, ...budget };
      const live = await owner.render(c, opts), batch = graphforgeStaticPayload(c, opts);
      assert.equal(live.spec.graph[0].tier_name, tier);
      assert.equal(digest(live.positions), digest(positions));
      const count = batch.figure._graphMeta[0].n_nodes;
      for (const target of [live, batch.figure]) {
        for (let i = 0; i < count; i++) assert.deepEqual(graphforgePick(target, c, { trace: live.nodeTrace, index: i }),
          tier === "aggregate" ? { kind: "aggregate", trace: live.nodeTrace, nodeCount: null } : c.identify("node", i));
        assert.equal(graphforgePick(target, c, { trace: live.nodeTrace, index: count }), null);
        for (let i = 0; i < live.pickData.edges.length; i++) {
          const pick = batch.figure.graphEdgePick(live.edgeTrace, i);
          const identity = graphforgePick(target, c, { trace: live.edgeTrace, index: i });
          assert.deepEqual(identity, pick.edge_count === 1 ? c.identify("edge", pick.source_edges[0])
            : { kind: "aggregate", trace: live.edgeTrace, edgeCount: pick.edge_count,
              edges: pick.source_edges.map(i => c.identify("edge", i)), truncated: pick.members_truncated });
        }
        assert.equal(graphforgePick(target, c, { trace: live.edgeTrace, index: live.pickData.edges.length }), null);
      }
    }
  } finally { await owner.dispose(); }
});

test("collapsed groups and hidden source rows retain UUID, group membership and remapped edge provenance", async () => {
  const original = composeGraphForge({ ...input(), layers: [
    { result: read("pagerank"), intent: "graph", generation: base.generation, resultId: "compound-rank" },
    { result: read("node_similarity"), intent: "graph", generation: base.generation, resultId: "compound-similarity" },
  ] });
  const sections = [...decodeContainer(original.bytes, "XYGF").values()]
    .filter(s => !["node.parent", "node.parent.valid"].includes(s.name)).map(s => ({ ...s, values: s.value }));
  sections.push({ name: "node.parent", dtype: DTYPE.u32, values: new Uint32Array([0, 0, 0, 0]) },
    { name: "node.parent.valid", dtype: DTYPE.u8, values: new Uint8Array([0, 1, 0, 0]) });
  const c = decodeGraphForgeDocument(encodeContainer("XYGF", sections));
  const opts = { layout: "preset", positions: { uuid: c.nodes.uuid,
    x: new Float64Array([0, 100, 200, 300]), y: new Float64Array(4) }, collapsed: [c.nodes.uuid[0]] };
  const owner = new GraphForgeLayoutController();
  try {
    const live = await owner.render(c, opts), batch = graphforgeStaticPayload(c, opts);
    const meta = batch.figure._graphMeta[0];
    assert.equal(meta.tier_name, "direct"); assert.equal(meta.n_nodes, 3);
    assert.deepEqual(graphforgePick(live, c, { trace: live.nodeTrace, index: 1 }), c.identify("node", 2));
    assert.equal(live.positions.x.length, 4);
    assert.ok(live.pickData.edges.length > 0, "disclosure must exercise retained edge provenance");
    assert.deepEqual(live.pickData.nodes.map(n => n.uuid), [c.nodes.uuid[0], c.nodes.uuid[2], c.nodes.uuid[3]]);
    const edgeIds = graphforgeGraphData(c).edgeIds;
    for (const target of [live, batch.figure]) {
      assert.deepEqual(graphforgePick(target, c, { trace: live.nodeTrace, index: 1 }), c.identify("node", 2));
      const group = graphforgePick(target, c, { trace: live.nodeTrace, index: 0 });
      assert.equal(group.uuid, c.nodes.uuid[0]);
      assert.equal(group.compound_collapsed, true); assert.equal(group.compound_member_count, 1);
      assert.deepEqual(group.compound_members, [c.nodes.uuid[1]]); assert.equal(group.compound_members_truncated, false);
      assert.equal(graphforgePick(target, c, { trace: live.nodeTrace, index: 3 }), null);
      for (let i = 0; i < live.pickData.edges.length; i++) {
        const pick = batch.figure.graphEdgePick(live.edgeTrace, i);
        assert.equal(pick.edge_count, 1);
        assert.deepEqual(graphforgePick(target, c, { trace: live.edgeTrace, index: i }), c.identify("edge", edgeIds.indexOf(pick.edge_ids[0])));
      }
    }
  } finally { await owner.dispose(); }
});

test("circle/grid retain the complete native source layout at Aggregate and seed bit-exact CoSE pins", async () => {
  const c = composeGraphForge(input()), data = graphforgeGraphData(c);
  const owner = new GraphForgeLayoutController();
  try {
    for (const layout of ["circle", "grid"]) {
      const expected = graphLayout(layout, data.nNodes, data.sources, data.targets, { seed: 17 });
      const live = await owner.render(c, { layout, seed: 17, nodeBudget: 2 });
      assert.equal(live.spec.graph[0].tier_name, "aggregate");
      assert.equal(live.phase, "complete"); assert.equal(live.step, 0);
      assert.ok(live.positions, "Aggregate live graphs must retain full source positions");
      assert.deepEqual(live.positions.uuid, c.nodes.uuid);
      assert.ok(live.positions.x instanceof Float64Array && live.positions.y instanceof Float64Array);
      assert.equal(live.positions.x.length, data.nNodes); assert.equal(digest(live.positions), digest(expected));
      const direct = await owner.render(c, { layout, seed: 17 });
      assert.equal(digest(live.positions), digest(direct.positions));
      const pinned = new Uint8Array(data.nNodes).fill(1);
      const cose = await owner.render(c, { layout: "cose", positions: live.positions, pinned, iterations: 2, nodeBudget: 2 });
      assert.equal(digest(cose.positions), digest(expected));
      // Static non-force semantics: complete supplied positions mean preset
      // reuse even with an explicit circle/grid name; pins do not run force.
      const preset = await owner.render(c, { layout, positions: live.positions, pinned, nodeBudget: 2 });
      assert.equal(preset.step, 0); assert.equal(digest(preset.positions), digest(expected));
    }
    const roots = new BigUint64Array([3n]);
    const rooted = await owner.render(c, { layout: "breadthfirst", roots, nodeBudget: 2 });
    assert.equal(digest(rooted.positions), digest(graphLayout("breadthfirst", data.nNodes, data.sources, data.targets, { roots })));
    const authored = { uuid: c.nodes.uuid.toReversed(), x: new Float64Array([30, 20, 10, -0]),
      y: new Float64Array([3, 2, 1 + 2 ** -52, 0]) };
    const preset = await owner.render(c, { layout: "preset", positions: authored, nodeBudget: 2 });
    assert.equal(preset.spec.graph[0].tier_name, "aggregate");
    assert.deepEqual([...preset.positions.x], [...authored.x].reverse());
    assert.deepEqual([...preset.positions.y], [...authored.y].reverse());
    await assert.rejects(owner.render(c, { layout: "preset" }), /requires x and y/);
    await assert.rejects(owner.render(c, { layout: "grid", positions: { uuid: [], x: [], y: [] } }), /cover every composed UUID/);
  } finally { await owner.dispose(); }
});

const temp = mkdtempSync(join(tmpdir(), "xyg-graphforge-live-"));
after(() => rmSync(temp, { recursive: true, force: true }));
const src = name => new URL(`../src/${name}`, import.meta.url).href;
writeFileSync(join(temp, "register.mjs"), `import {register} from 'node:module'; register('./loader.mjs', import.meta.url);`);
writeFileSync(join(temp, "loader.mjs"), `
export async function resolve(s,c,next) {
 if (s === './native.js' && c.parentURL === ${JSON.stringify(src("graphforge.js"))}) return {url: new URL('./native.mjs',import.meta.url).href,shortCircuit:true};
 if (s === './abi.js' && [${JSON.stringify(src("graph.js"))},${JSON.stringify(src("force_scheduler.js"))},${JSON.stringify(src("graphforge_layout_worker.js"))}].includes(c.parentURL)) return {url: new URL('./abi.mjs',import.meta.url).href,shortCircuit:true};
 if (s === 'node:worker_threads' && [${JSON.stringify(src("graphforge_layout.js"))},${JSON.stringify(src("force_scheduler.js"))}].includes(c.parentURL)) return {url: new URL('./workers.mjs',import.meta.url).href,shortCircuit:true};
 return next(s,c);
}`);
writeFileSync(join(temp, "abi.mjs"), `
export * from ${JSON.stringify(src("abi.js"))};
import * as real from ${JSON.stringify(src("abi.js"))};
import {workerData,threadId,isMainThread} from 'node:worker_threads';
import {appendFileSync} from 'node:fs';
const trace = type => appendFileSync(process.env.GF_TRACE,JSON.stringify({type,threadId})+'\\n');
export function graphLayout(...a) { if(isMainThread) throw Error('source layout ran on caller'); appendFileSync(process.env.GF_TRACE,JSON.stringify({type:'layout',layout:a[0],threadId})+'\\n'); return real.graphLayout(...a); }
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
export class Worker extends Real { constructor(...a) { super(...a); const child=this.threadId; appendFileSync(process.env.GF_TRACE,JSON.stringify({type:'worker-created',threadId,child})+'\\n'); this.on('message',msg=>{ if(threadId===0 && process.env.GF_LATE==='1' && msg.type==='payload' && msg.revision!==0) setImmediate(()=>this.emit('message',{...msg,revision:0,jobId:'retired',payload:{...msg.payload,revision:0,jobId:'retired'}})); }); this.on('exit',()=>appendFileSync(process.env.GF_TRACE,JSON.stringify({type:'exit',threadId,child})+'\\n')); } }
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


test("reentrant startup cancellation cannot strand a bridge or escape disposal", () => {
  for (const mode of ["signal-registration", "input-abort", "input-dispose", "clone-abort", "clone-dispose"]) {
    const log = join(temp, `${mode}.jsonl`), script = join(temp, `${mode}.mjs`);
    writeFileSync(log, "");
    writeFileSync(script, `
import assert from 'node:assert/strict';
import {GraphForgeLayoutController} from ${JSON.stringify(src("graphforge.js"))};
import {readFileSync,appendFileSync} from 'node:fs';
const owner=new GraphForgeLayoutController(), ac=new AbortController(), mode=${JSON.stringify(mode)};
const nodes=readFileSync(${JSON.stringify(new URL(`tests/fixtures/graphforge/results/${base.nodes}.arrow`, root).pathname)});
const edges=readFileSync(${JSON.stringify(new URL(`tests/fixtures/graphforge/results/${base.edges}.arrow`, root).pathname)});
const base={tables:[nodes,edges],generation:${JSON.stringify(base.generation)}};
let disposal, listeners=0;
const add=ac.signal.addEventListener.bind(ac.signal), remove=ac.signal.removeEventListener.bind(ac.signal);
ac.signal.addEventListener=(...a)=>{listeners++;add(...a);if(mode==='signal-registration') ac.abort();};
ac.signal.removeEventListener=(...a)=>{if(listeners) listeners--;remove(...a);};
const cancel=()=>{if(mode.endsWith('dispose')) disposal=owner.dispose();else ac.abort();};
const input=mode==='signal-registration'?{base}:mode.startsWith('input')
 ?{get bytes(){cancel();return undefined;},base}
 :{get base(){cancel();return base;}};
const run=owner.render(input,{signal:ac.signal,iterations:2,maxWallMs:10000});
const expected=mode.endsWith('dispose')?'GF_LAYOUT_DISPOSED':'GF_LAYOUT_ABORTED';
await assert.rejects(run,{code:expected});
await disposal;await owner.dispose();assert.equal(listeners,0);
await assert.rejects(owner.render({base}),{code:'GF_LAYOUT_DISPOSED'});
appendFileSync(process.env.GF_TRACE,JSON.stringify({type:'settled'})+'\\n');
`);
    const result = spawnSync(process.execPath, ["--import", join(temp, "register.mjs"), script], {
      env: { ...process.env, GF_TRACE: log }, encoding: "utf8", timeout: 8000 });
    assert.equal(result.status, 0, `${mode}: ${result.stderr} ${result.error ?? ""}`);
    const rows = readFileSync(log, "utf8").trim().split("\n").map(JSON.parse);
    assert.equal(rows.at(-1).type, "settled");
    const created = rows.filter(r => r.type === "worker-created");
    const exits = rows.filter(r => r.type === "exit");
    if (mode.startsWith("clone")) assert.ok(created.length >= 1, "test must cancel during Worker construction");
    else assert.equal(created.length, 0, "cancelled startup must never construct a Worker");
    assert.equal(exits.length, created.length, "every constructed worker exited before settlement");
    for (const row of created) assert.ok(exits.some(e => e.child === row.child && e.threadId === row.threadId));
    if (rows.some(r => r.type === "create")) assert.ok(rows.some(r => r.type === "destroy"));
  }
});


test("non-force Aggregate source layout runs once in the bridge before preset-only packing", () => {
  for (const layout of ["circle", "grid", "breadthfirst"]) {
    const log = join(temp, `${layout}.jsonl`), script = join(temp, `${layout}.mjs`);
    writeFileSync(log, "");
    writeFileSync(script, `
import assert from 'node:assert/strict';
import {GraphForgeLayoutController} from ${JSON.stringify(src("graphforge.js"))};
import {readFileSync,appendFileSync} from 'node:fs';
const owner=new GraphForgeLayoutController();
const nodes=readFileSync(${JSON.stringify(new URL(`tests/fixtures/graphforge/results/${base.nodes}.arrow`, root).pathname)});
const edges=readFileSync(${JSON.stringify(new URL(`tests/fixtures/graphforge/results/${base.edges}.arrow`, root).pathname)});
try {const p=await owner.render({base:{tables:[nodes,edges],generation:${JSON.stringify(base.generation)}}},
 {layout:${JSON.stringify(layout)},nodeBudget:2,roots:new BigUint64Array([3n])});
 assert.equal(p.positions.x.length,4);assert.equal(p.spec.graph[0].tier_name,'aggregate');
} finally {await owner.dispose();}
appendFileSync(process.env.GF_TRACE,JSON.stringify({type:'settled'})+'\\n');
`);
    const result = spawnSync(process.execPath, ["--import", join(temp, "register.mjs"), script], {
      env: { ...process.env, GF_TRACE: log }, encoding: "utf8", timeout: 8000 });
    assert.equal(result.status, 0, result.stderr);
    const rows = readFileSync(log, "utf8").trim().split("\n").map(JSON.parse);
    assert.deepEqual(rows.filter(r => r.type === "layout").map(r => r.layout), [layout, "preset"]);
    assert.equal(rows.some(r => ["create", "tick"].includes(r.type)), false, "non-force layouts must never step force");
    assert.equal(rows.filter(r => r.type === "exit").length, 1);
    assert.equal(rows.at(-1).type, "settled");
  }
});
