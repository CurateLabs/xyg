// Actual browser golden migration: historical bytes remain immutable.
import assert from "node:assert/strict";
import fs from "node:fs";
import { gunzipSync } from "node:zlib";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "vite";
import { decodeContainer } from "../../packages/xy-node/src/graphforge-container.js";

const root = fileURLToPath(new URL("../../", import.meta.url));
const oldPath = "spec/performance/graph-s5b-pointer-native-input-repair-2026-11-04/captured-requests.json.gz";
const currentPath = "spec/performance/graph-picked-target-r6-2026-11-04/captured-requests.json.gz";
const sha = b => createHash("sha256").update(b).digest("hex");
const capture = p => JSON.parse(gunzipSync(fs.readFileSync(root + p)));
const bytes = b => Uint8Array.from(Buffer.from(b, "base64"));
// Decode first through the unchanged guards, then inspect original raw payloads.
function rawSections(b) {
  const decoded = decodeContainer(b, "XYGR"), view = new DataView(b.buffer, b.byteOffset, b.byteLength);
  const names = 32 + decoded.size * 40, out = new Map();
  for (let i = 0; i < decoded.size; i++) {
    const at = 32 + i * 40;
    const name = new TextDecoder().decode(b.subarray(names + view.getUint32(at, true), names + view.getUint32(at, true) + view.getUint32(at + 4, true)));
    const index = view.getUint32(at + 12, true), offset = Number(view.getBigUint64(at + 16, true)), length = Number(view.getBigUint64(at + 32, true));
    out.set(`${name}#${index}`, { dtype: view.getUint32(at + 8, true), index, count: view.getBigUint64(at + 24, true), payload: b.slice(offset, offset + length) });
  }
  assert.deepEqual([...out.keys()], [...decoded.keys()]);
  return out;
}
const built = await build({ configFile: false, logLevel: "error", build: { write: false, minify: false, lib: { entry: fileURLToPath(new URL("../src/63_graph_session_wire.ts", import.meta.url)), formats: ["es"] } } });
const chunks = (Array.isArray(built) ? built : [built]).flatMap(r => r.output).filter(x => x.type === "chunk");
assert.equal(chunks.length, 1);
const wire = await import(`data:text/javascript;base64,${Buffer.from(chunks[0].code).toString("base64")}`);
const uuid = b => Buffer.from(b).toString("hex").replace(/(.{8})(.{4})(.{4})(.{4})(.{12})/, "$1-$2-$3-$4-$5");

test("fresh actual browser goldens preserve every old raw section and add only exact query receipts", () => {
  const old = capture(oldPath), current = capture(currentPath);
  assert.equal(old.length, 19); assert.equal(current.length, 19);
  const document = decodeContainer(decodeContainer(bytes(current[0].request), "XYGI").get("document.bytes#0").value, "XYGF");
  const value = (c, n, i = 0) => c.get(`${n}#${i}`).value;
  // Independently expected source targets of the existing real mouse journey:
  // nodes/modifiers, parallel lanes, self-loop, derived head, compound frame,
  // shaft gap, interior, node, then blank Add/Toggle/Replace.
  const targets = [[1,1],[1,2],[1,1],[1,1],[1,1],[1,1],[2,0],[2,1],[2,2],[2,4],[1,0],[1,1],[0,0],[1,1],[0,0],[0,0],[0,0]];
  const allowed = ["pick.header.u32#0", "pick.query.u64#0", "pick.ref.bytes#0", "pick.layers.u32#0", "pick.rows.u64#0"].sort();
  const report = { oldPath, currentPath, oldSha256: sha(fs.readFileSync(root + oldPath)), currentSha256: sha(fs.readFileSync(root + currentPath)), requestBytesExact: 0, selectAt: 0, cases: [] };
  let previous = null;
  for (let i = 0; i < current.length; i++) {
    const a = old[i], b = current[i], request = bytes(b.request), priorReply = bytes(a.reply), reply = bytes(b.reply);
    assert.deepEqual(request, bytes(a.request), `request ${i} stays byte-exact`); report.requestBytesExact++;
    assert.equal(b.operation, a.operation);
    const oldSections = rawSections(priorReply), newSections = rawSections(reply);
    for (const [key, section] of oldSections) assert.deepEqual(newSections.get(key), section, `request ${i} exact old dtype/index/count/RAW payload ${key}`);
    const added = [...newSections.keys()].filter(k => !oldSections.has(k)).sort();
    const decoded = decodeContainer(reply, "XYGR"), q = decodeContainer(request, "XYGI");
    if (b.operation !== 1) { assert.deepEqual(reply, priorReply, `Open/Render ${i} remains fully byte-exact`); assert.deepEqual(added, []); }
    else {
      assert.equal(i, report.selectAt + 2); report.selectAt++;
      assert.deepEqual(added, allowed);
      assert.equal(b.nativeEvent.trusted, true); assert.equal(b.nativeEvent.canvas, true); assert.equal(b.nativeEvent.zoom, 1);
      assert.deepEqual(Array.from(value(q, "coordinates.f64")), b.nativeEvent.nativeCoordinates);
      const [kind, source] = targets[i - 2], header = Array.from(value(decoded, "pick.header.u32")), query = Array.from(value(decoded, "pick.query.u64"));
      const words = value(q, "header.u32"), stamp = Array.from(value(q, "header.u64"));
      assert.deepEqual(header, [1, 1, 0, words[0], kind, kind ? 1 : 0, 0, 0]);
      assert.equal(header[3], value(previous, "header.u32")[0], "pre-query publication revision");
      assert.deepEqual(query.slice(0, 2), [stamp[0],stamp[2]]);
      for (const [name,dtype,count] of [["pick.header.u32",2,8n],["pick.query.u64",3,5n],["pick.ref.bytes",6,BigInt(value(decoded,"pick.ref.bytes").length)],["pick.layers.u32",2,kind?1n:0n],["pick.rows.u64",3,kind?1n:0n]]) {
        const section=newSections.get(name+"#0"); assert.deepEqual([section.dtype,section.index,section.count],[dtype,0,count]);
      }
      let ref;
      if (!kind) {
        assert.deepEqual(query.slice(2), [0n,0n,0n]);
        assert.deepEqual(wire.decodeGraphSessionRefs(value(decoded, "pick.ref.bytes")), []);
        assert.deepEqual(Array.from(value(decoded, "pick.layers.u32")), []); assert.deepEqual(Array.from(value(decoded, "pick.rows.u64")), []);
      } else {
        const prefix = kind === 1 ? "node" : "edge", members = value(previous, `render.${prefix}_members.u64`), offsets = value(previous, `render.${prefix}_member_offsets.u64`);
        const render = Number(query[2]), start = Number(offsets[render]), end = Number(offsets[render + 1]);
        assert.deepEqual(Array.from(members.slice(start, end)), [BigInt(source)], "actual render maps to independently expected source");
        assert.deepEqual(query.slice(3), [BigInt(end - start), BigInt(source)]);
        if (kind === 2 && value(document, "edge.derived")[source]) {
          const layer = value(document,"edge.layer")[source];
          ref = {kind:2,resultId:value(document,"layer.result_id",layer),layer,path:value(document,"edge.path")[source],order:BigInt.asUintN(64,value(document,"edge.order")[source])};
        } else ref = {kind:kind-1,uuid:uuid(value(document, `${prefix}.uuid`).subarray(source*16,(source+1)*16))};
        assert.deepEqual(value(decoded, "pick.ref.bytes"), wire.encodeGraphSessionRefs([ref]), "exact canonical/derived ref bytes");
        assert.deepEqual(Array.from(value(decoded, "pick.layers.u32")), [0]);
        assert.deepEqual(Array.from(value(decoded, "pick.rows.u64")), [value(document, `layer.${prefix}_rows`)[source]]);
        assert.deepEqual(value(decoded, "selection.result_ids.texts"), [value(document,"layer.result_id")]);
        assert.deepEqual(Array.from(value(decoded,"selection.result_ids.valid.u8")),[1]);
      }
      const semantic = wire.decodeGraphSessionResult(reply);
      assert.equal(Object.hasOwn(semantic,"pick"),false); for(const key of allowed)assert.ok(semantic.sections.has(key));
    }
    report.cases.push({ index:i,operation:b.operation,requestSha256:sha(request),replySha256:sha(reply),priorReplySha256:sha(priorReply),added,oldRawSections:[...oldSections].map(([key,s])=>({key,dtype:s.dtype,index:s.index,count:String(s.count),rawSha256:sha(s.payload)})) });
    if (b.operation !== 19) previous = decoded;
  }
  assert.equal(report.selectAt,17); assert.equal(report.requestBytesExact,19);
  if(process.env.XYG_PICK_MIGRATION_REPORT)fs.writeFileSync(process.env.XYG_PICK_MIGRATION_REPORT,JSON.stringify(report,null,2)+"\n",{flag:"wx"});
});
