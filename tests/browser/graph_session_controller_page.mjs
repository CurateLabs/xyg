// Actual shipped ESM/Worker/WASM under strict CSP. All hooks below are test-only
// transport fault injection/observations; production graph policy stays Rust.
import { attachWasmGraphSession, composeWasmGraphForge, createXygWasmWorker, renderWasmGraphForge } from "/packages/xy-client/dist/index.js";
import { encodeContainer, decodeContainer, DTYPE } from "/packages/xy-node/src/graphforge-container.js";
const state = window.__graphSession = { stage: "boot", products: [], commands: [], replies: [], gl: [], errors: [], inject: null, hold: false, held: [], events: [], legacyCalls: [] };
state.json = value => JSON.stringify(value, (_, v) => typeof v === "bigint" ? v.toString() : v);
const assert = (condition, message) => { if (!condition) throw new Error(message); };
function section(bytes, name, index = 0) {
  const a = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes), v = new DataView(a.buffer, a.byteOffset, a.byteLength), start = 32 + 40 * v.getUint32(8, true), dec = new TextDecoder();
  for (let i = 0; i < v.getUint32(8, true); i++) {
    const at = 32 + i * 40, n = dec.decode(a.subarray(start + v.getUint32(at, true), start + v.getUint32(at, true) + v.getUint32(at + 4, true)));
    if (n === name && v.getUint32(at + 12, true) === index) return a.subarray(Number(v.getBigUint64(at + 16, true)), Number(v.getBigUint64(at + 16, true) + v.getBigUint64(at + 32, true)));
  }
  throw new Error(`missing ${name}`);
}
const view = (a) => new DataView(a.buffer, a.byteOffset, a.byteLength);
const post = Worker.prototype.postMessage;
Worker.prototype.postMessage = function(message, transfer) {
  state.products.push(message.type);
  if (message.type?.startsWith("graph.session.")) {
    if (state.inject === "seed-highlight" && message.request) {
      const parts = decodeContainer(message.request, "XYGI"), words = parts.get("header.u32#0").value;
      if (words[1] === 1) {
        words[1] = 12; words[4] = 2;
        parts.delete("coordinates.f64#0");
        const refs = new Uint8Array(64); new DataView(refs.buffer).setUint32(0, 1, true); refs.set(state.pointer.nodes.subarray(16,32),16);
        message.request = encodeContainer("XYGI", [...parts.values()].map(s => ({...s, values:s.value})).concat([{name:"refs.bytes",dtype:DTYPE.bytes,values:refs}])).buffer;
        state.inject = null;
      }
    }
    if (message.request instanceof ArrayBuffer) {
      const h = view(section(message.request, "header.u64")), words = view(section(message.request, "header.u32"));
      if (state.inject === "stale") { words.setUint32(0, words.getUint32(0, true) + 1, true); state.inject = null; }
      if (state.inject === "refuse-clear" && words.getUint32(4, true) === 4) { h.setBigUint64(0, h.getBigUint64(0, true) + 1n, true); state.inject = null; }
      if (state.inject === "wrong-instance") { h.setBigUint64(0, h.getBigUint64(0, true) + 1n, true); state.inject = null; }
      state.commands.push({ type: message.type, requestId: message.requestId, sequence: message.sequence, lifetime: message.lifetime, instanceId: h.getBigUint64(0, true), opSeq: h.getBigUint64(16, true), revision: words.getUint32(0, true), operation: words.getUint32(4, true), bytes: new Uint8Array(message.request).slice() });
    } else state.commands.push({ type: message.type, requestId: message.requestId, sequence: message.sequence, lifetime: message.lifetime });
  }
  if (["budget-reply","cap-reply"].includes(state.inject) && message.type === "graph.session.interact") {
    const code=state.inject==='cap-reply'?'GF_INTERACTION_SELECTION_TOO_LARGE':'GF_INTERACTION_BUDGET', status=state.inject==='cap-reply'?-8:-4;
    state.inject = null;
    queueMicrotask(() => this.onmessage({data:{requestId:message.requestId,ok:false,error:{code,message:"test-only pre-execution typed refusal seam",status}}}));
    return;
  }
  return post.call(this, message, transfer);
};
const context = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function(kind, ...args) {
  const gl = context.call(this, kind, ...args);
  if (kind === "webgl2" && gl && !state.gl.includes(gl)) state.gl.push(gl);
  return gl;
};
const bytes = async (name) => new Uint8Array(await (await fetch(`/tests/fixtures/graphforge/results/${name}.arrow`)).arrayBuffer());
const makeWorker = (wasm = "/packages/xy-client/dist/xyg-wasm.wasm") => {
  const worker = createXygWasmWorker({ workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm });
  const actual = worker.worker, deliver = actual.onmessage;
  actual.onmessage = event => {
    const value = event.data.value;
    if (value?.bytes instanceof ArrayBuffer && value.bytes.byteLength) {
      if (state.inject === "malformed-gpu") { view(section(value.bytes, "gpu.node.coord.bytes")).setFloat32(0, NaN, true); state.inject = null; }
      if (state.inject === "malformed-clear") { view(section(value.bytes, "clear.action.u32")).setUint32(4, 2, true); state.inject = null; }
      if (state.inject === "missing-clear") {
        const a = new Uint8Array(value.bytes), v = view(a), start = 32 + 40 * v.getUint32(8, true), decoder = new TextDecoder();
        for (let i = 0; i < v.getUint32(8, true); i++) {
          const at = 32 + i * 40, offset = start + v.getUint32(at, true), length = v.getUint32(at + 4, true);
          if (decoder.decode(a.subarray(offset, offset + length)) === "clear.action.u32") a.set(new TextEncoder().encode("clear.absent.u32"), offset);
        }
        state.inject = null;
      }
      if (state.inject === "wrong-lifetime") { value.lifetime++; state.inject = null; }
      state.replies.push({ requestId: event.data.requestId, bytes: new Uint8Array(value.bytes).slice(), lifetime: value.lifetime, sequence: value.sequence });
      if (state.hold) { state.held.push(() => deliver(event)); return; }
    }
    deliver(event);
  };
  return worker;
};
const container = () => { const el = document.createElement("div"); document.body.append(el); return el; };
state.raw = message => new Promise(resolve => {
  const actual = state.worker.worker, requestId = 900000 + state.commands.length;
  const receive = event => { if (event.data.requestId === requestId) { actual.removeEventListener("message", receive); resolve(event.data); } };
  actual.addEventListener("message", receive); actual.postMessage({ ...message, requestId });
});
state.makeWorker = makeWorker; state.container = container; state.section = section;
state.release = () => { state.hold = false; for (const deliver of state.held.splice(0)) deliver(); };
state.pixel = el => [...el.querySelector("canvas").getContext("2d").getImageData(0, 0, 640, 320).data];
state.waitIdle = async (el = state.el) => {
  for (let i = 0; i < 500 && el.querySelector('[role="application"]')?.getAttribute("aria-busy") === "true"; i++) await new Promise(r => setTimeout(r, 10));
  assert(el.querySelector('[role="application"]')?.getAttribute("aria-busy") !== "true", "bounded UI action did not settle");
};
state.surface = () => state.el.querySelector('[role="application"]');
state.key = async (key, extra = {}) => { const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...extra }); state.surface().dispatchEvent(event); await state.waitIdle(); return event.defaultPrevented; };
state.snapshot = () => state.handle.snapshot();
state.boot = (async () => {
  const worker = makeWorker(); await worker.ready; state.worker = worker;
  state.input = { base: { tables: [await bytes("base-cyclic-nodes"), await bytes("base-cyclic-edges")] }, layers: [{ result: await bytes("pagerank"), intent: "graph", resultId: "rank-exact" }, { result: await bytes("node_similarity"), intent: "graph", resultId: "pair-exact" }] };
  const composed = await composeWasmGraphForge(worker, state.input).result;
  state.document = composed.bytes; const n = composed.nodeUuid.length;
  state.load = { x: Array.from({ length: n }, (_, i) => 30 + i * 55), y: Array(n).fill(100) };
  state.camera = [-1, 1, 500, 20, 640, 320, 1];
  // Obtain the actual shipped ChartView prototype, then retire the control.
  const ordinary = makeWorker(); await ordinary.ready;
  const canonicalEl = container();
  const control = await renderWasmGraphForge({ el: canonicalEl, worker: ordinary, width: 640, height: 320, input: state.input });
  const proto = Object.getPrototypeOf(control.view); control.view.destroy(); canonicalEl.remove(); await ordinary.dispose();
  for (const method of ["_cacheGraphsFromSpec", "_graphMetaArray", "_syncGraphNeighborhoodHighlight", "_pickAt", "_broadcastLinkedSelection", "_renderBoxSelection", "_renderLassoSelection"]) {
    proto[method] = () => { state.legacyCalls.push(method); throw new Error(`retained path reached legacy ${method}`); };
  }
  const before = document.createElement("button"), after = document.createElement("button"); before.id = "sentinel-before"; after.id = "sentinel-after"; before.textContent = "Before"; after.textContent = "After";
  document.body.append(before); state.el = container(); document.body.append(after);
  for (const kind of ["render", "select", "focus", "stale", "error"]) state.el.addEventListener(`xy:graph-${kind}`, e => { state.events.push({ kind, detail: e.detail }); });
  state.handle = attachWasmGraphSession({ el: state.el, worker, instanceId: 9007199254740993n, document: state.document, load: state.load, camera: state.camera });
  await state.handle.ready; state.stage = "ready";
  return true;
})().catch(error => { state.stage = "failed"; state.failure = { message: error.message, stack: error.stack, code: error.code }; throw error; });
state.attach = attachWasmGraphSession; state.compose = composeWasmGraphForge;

state.createDialog = async () => {
  const dialog = document.createElement("dialog"), el = document.createElement("div");
  dialog.id = "r2-dialog"; dialog.append(el); document.body.append(dialog);
  const worker = makeWorker(); await worker.ready;
  const handle = state.attach({ el, worker, instanceId: 72n, document: state.document, load: state.load, camera: state.camera }); await handle.ready;
  const surface = el.querySelector('[role="application"]');
  const result = state.dialog = { dialog, el, worker, handle, surface, keys: [], cancels: [], errors: [] };
  dialog.addEventListener("keydown", event => { if (event.key === "Escape") result.keys.push({ trusted: event.isTrusted, prevented: event.defaultPrevented }); });
  dialog.addEventListener("cancel", event => result.cancels.push({ trusted: event.isTrusted }));
  el.addEventListener("xy:graph-error", event => result.errors.push(event.detail));
  el.addEventListener("xy:graph-stale", event => result.errors.push(event.detail));
  dialog.showModal(); surface.focus();
};

// Pointer fixtures/oracles are test-only. Coordinates come from Rust CPU paint
// sections; neither these readers nor membership interpretation ship to users.
state.values = (bytes, name, index=0) => {
  const a = section(bytes,name,index), v = view(a);
  return Array.from({length:a.length/8},(_,i)=>v.getFloat64(i*8,true));
};
state.publication = (p=state.pointer) => state.replies.filter(r => {
  const c=state.commands.find(c=>c.requestId===r.requestId && c.sequence===r.sequence && c.lifetime===r.lifetime);
  return c?.instanceId===p.id && c.operation!==19;
}).at(-1).bytes;
state.pointerFixture = async (kind="routes", id=36n) => {
  const f=(name,dtype,values,index=0)=>({name,dtype:DTYPE[dtype],values,index});
  const noEdges=["cap","pressure"].includes(kind), count=kind==="pressure"?10001:kind==="cap"?51:5, nodes=new Uint8Array(count*16);
  for(let i=0;i<count;i++) new DataView(nodes.buffer).setUint32(i*16,i+1,true);
  const edges=new Uint8Array(5*16); for(let i=0;i<4;i++) edges.fill(11+i,i*16,(i+1)*16);
  const sections=[f("status","u32",[0]),f("kind","utf8","graph"),f("composition.version","u32",[2]),f("node.uuid","uuid",nodes),
    f("edge.uuid","uuid",noEdges?new Uint8Array():edges),f("edge.derived","u8",noEdges?[]:[0,0,0,0,1]),
    f("edge.layer","u32",noEdges?[]:[0xffffffff,0xffffffff,0xffffffff,0xffffffff,0]),f("edge.order","i64",noEdges?[]:[-1n,-1n,-1n,-1n,9007199254740993n]),
    f("edge.path","u64",noEdges?[]:[-1n,-1n,-1n,-1n,9007199254740995n].map(x=>BigInt.asUintN(64,x))),
    f("edge.source","u64",noEdges?[]:[1n,1n,1n,4n,2n]),f("edge.target","u64",noEdges?[]:[2n,2n,1n,3n,3n]),f("graph.directed","u8",[1])];
  if(!noEdges) sections.push(f("node.parent","u32",[0,0,0,0,0]),f("node.parent.valid","u8",[0,1,1,0,0]),f("layer.schema","utf8","test"),f("layer.result_id","utf8","exact:雪\t"),f("layer.node_rows","u64",[10n,9007199254740997n,30n,40n,50n]),f("layer.edge_rows","u64",[70n,71n,72n,73n,9007199254740999n]));
  const worker=makeWorker(); await worker.ready;
  const el=container(); el.dataset.pointerFixture=String(id);
  const load=noEdges?{x:Array(count).fill(100),y:Array(count).fill(100),budgets:[1n,100n]}:
    {x:kind==="aggregate"?[100,100.1,100.2,500,500.1]:[50,170,350,500,-200],y:kind==="aggregate"?[1,1,1,2.5,2.5]:[0.5,1.5,1.5,2.5,2.5],...(kind==="aggregate"?{budgets:[2n,100n]}:{})};
  const camera=[1,noEdges?1:100,0,0,640,320,2], document=encodeContainer("XYGF",sections);
  const handle=state.attach({el,worker,instanceId:id,document,load,camera}); try { await handle.ready; } catch(error) { await handle.dispose(); await worker.dispose(); el.remove(); throw error; }
  const p=state.pointer={el,worker,handle,id,nodes,edges,document,load,camera,events:[],trusted:[],errors:[]};
  el.addEventListener("xy:graph-select",e=>p.events.push(e.detail));
  for(const kind of ["error","stale"]) el.addEventListener(`xy:graph-${kind}`,e=>p.errors.push(e.detail));
  el.querySelector("canvas").addEventListener("click",e=>p.trusted.push({trusted:e.isTrusted,button:e.button,detail:e.detail,clientX:e.clientX,clientY:e.clientY}));
  return true;
};
state.pointerPoint = (kind,index=0) => {
  const p=state.pointer, bytes=state.publication(p), get=name=>state.values(bytes,name);
  if(kind==="node") return get("paint.node.center.f64").slice(index*2,index*2+2);
  if(kind==="blank") return [620,300];
  if(kind==="piece"||kind==="head"||kind==="gap") {
    const parts=decodeContainer(bytes,"XYGR"), ids=parts.get("paint.piece.index.u64#0").value, geo=get("paint.piece.geometry.f64");
    const offsets=parts.get('render.edge_member_offsets.u64#0').value, members=parts.get('render.edge_members.u64#0').value;
    const renderIndex=Array.from({length:offsets.length-1},(_,i)=>i).find(i=>Array.from(members.slice(Number(offsets[i]),Number(offsets[i+1]))).includes(BigInt(index)));
    const i=Array.from({length:ids.length/2},(_,i)=>i).filter(i=>ids[i*2]===BigInt(renderIndex)&&(kind!=="head"||(ids[i*2+1]&2n))).sort((a,b)=>Math.hypot(geo[b*14+2]-geo[b*14],geo[b*14+3]-geo[b*14+1])-Math.hypot(geo[a*14+2]-geo[a*14],geo[a*14+3]-geo[a*14+1]))[0];
    assert(i!==undefined,"Rust piece not found"); const g=geo.slice(i*14,i*14+14);
    if(kind==="head") return [(g[8]+g[10]+g[12])/3,(g[9]+g[11]+g[13])/3];
    if(kind==="gap") { const center=get("paint.node.center.f64").slice(2,4); return [(center[0]+g[0])/2,(center[1]+g[1])/2]; }
    if(index===0||index===1) {
      const dx=g[2]-g[0],dy=g[3]-g[1],len=Math.hypot(dx,dy),side=index===0?-1:1;
      return [(g[0]+g[2])/2-dy/len*g[4]*0.7*side,(g[1]+g[3])/2+dx/len*g[4]*0.7*side];
    }
    return [(g[0]+g[2])/2,(g[1]+g[3])/2];
  }
  const f=get("paint.frame.geometry.f64").slice(0,5);
  if(kind==="frame") return [f[0],(f[1]+f[3])/2];
  if(kind==="interior") return [(f[0]+f[2])/2,f[1]+12];
  throw new Error("unknown oracle point");
};
state.pointerClient = ([x,y]) => {
  const c=state.pointer.el.querySelector("canvas"), r=c.getBoundingClientRect(), s=getComputedStyle(c);
  const left=parseFloat(s.borderLeftWidth)+parseFloat(s.paddingLeft), top=parseFloat(s.borderTopWidth)+parseFloat(s.paddingTop);
  const horizontal=left+parseFloat(s.borderRightWidth)+parseFloat(s.paddingRight), vertical=top+parseFloat(s.borderBottomWidth)+parseFloat(s.paddingBottom);
  const bw=parseFloat(s.width)+(s.boxSizing==="border-box"?0:horizontal), bh=parseFloat(s.height)+(s.boxSizing==="border-box"?0:vertical);
  return [r.left+(left+x/state.pointer.handle.snapshot().camera[4]*(bw-horizontal))*r.width/bw,r.top+(top+y/state.pointer.handle.snapshot().camera[5]*(bh-vertical))*r.height/bh];
};

state.pointerSnapshot = () => {
  const snapshot=state.pointer.handle.snapshot();
  if(!snapshot) return null;
  for(const key of ['indices','layerOffsets','layers','rows']) snapshot.selection[key]=Array.from(snapshot.selection[key]);
  snapshot.focusRing=Array.from(snapshot.focusRing);
  return snapshot;
};

state.geometryStamp = bytes => state.json([...decodeContainer(bytes,'XYGR').values()].filter(s=>/^(paint\..*(center|geometry|index)|gpu\..*(coord|attr)|render\..*members)/.test(s.name)).map(s=>[s.name,s.index,[...s.value]]));
