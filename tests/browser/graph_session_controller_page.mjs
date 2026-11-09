// Actual shipped ESM/Worker/WASM under strict CSP. All hooks below are test-only
// transport fault injection/observations; production graph policy stays Rust.
import { attachWasmGraphSession, composeWasmGraphForge, createXygWasmWorker, renderWasmGraphForge, XygWasmTemporalController } from "/packages/xy-client/dist/index.js";
import { encodeContainer, decodeContainer, DTYPE } from "/packages/xy-node/src/graphforge-container.js";
const state = window.__graphSession = { stage: "boot", products: [], commands: [], replies: [], gl: [], errors: [], inject: null, hold: false, held: [], events: [], legacyCalls: [] };
state.json = value => JSON.stringify(value, (_, v) => typeof v === "bigint" ? v.toString() : v);
state.waitForCapture = async p => { await p.handle.whenIdle(); };
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
  if(message.type === "init") this.__actualArena = message.maxArenaBytes;
  if (state.inject === "temporal-budget" && message.type === "graph.session.temporal-frame") {
    new DataView(message.request).setBigUint64(48,0n,true); state.inject=null;
  }
  if (state.inject === "temporal-render-invalid" && message.type === "graph.session.render") {
    view(section(message.request,"camera.f64")).setFloat64(0,NaN,true); state.inject=null;
  }
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
    if (message.request instanceof ArrayBuffer && !message.type.includes("temporal-")) {
      const h = view(section(message.request, "header.u64")), words = view(section(message.request, "header.u32"));
      if (state.inject === "stale") { words.setUint32(0, words.getUint32(0, true) + 1, true); state.inject = null; }
      if (state.inject === "refuse-clear" && words.getUint32(4, true) === 4) { h.setBigUint64(0, h.getBigUint64(0, true) + 1n, true); state.inject = null; }
      if (state.inject === "wrong-instance") { h.setBigUint64(0, h.getBigUint64(0, true) + 1n, true); state.inject = null; }
      state.commands.push({ owner:this.__graphOwner, at: performance.now(), type: message.type, requestId: message.requestId, sequence: message.sequence, lifetime: message.lifetime, instanceId: h.getBigUint64(0, true), opSeq: h.getBigUint64(16, true), revision: words.getUint32(0, true), operation: words.getUint32(4, true), bytes: new Uint8Array(message.request).slice() });
    } else state.commands.push({ owner:this.__graphOwner, at: performance.now(), type: message.type, requestId: message.requestId, sequence: message.sequence, lifetime: message.lifetime });
  }
  if (["budget-reply","cap-reply"].includes(state.inject) && message.type === "graph.session.interact") {
    const code=state.inject==='cap-reply'?'GF_INTERACTION_SELECTION_TOO_LARGE':'GF_INTERACTION_BUDGET', status=state.inject==='cap-reply'?-8:-4;
    state.inject = null;
    queueMicrotask(() => this.onmessage({data:{requestId:message.requestId,ok:false,error:{code,message:"test-only pre-execution typed refusal seam",status}}}));
    return;
  }
  if (this.__temporalCapture && message.type?.startsWith("graph.session.")) {
    state.temporalWire ??= [];
    state.temporalWire.push({kind:"request",owner:this.__graphOwner,type:message.type,requestId:message.requestId,sequence:message.sequence,lifetime:message.lifetime,bytes:message.request instanceof ArrayBuffer?Array.from(new Uint8Array(message.request)):null});
  }
  if (typeof state.deferGraphRequest === "function" && message.type === "graph.session.render") {
    const deferred = state.deferGraphRequest;
    state.deferGraphRequest = null;
    deferred(() => post.call(this, message, transfer));
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
const makeWorker = (wasm = "/packages/xy-client/dist/xyg-wasm.wasm", maxArenaBytes) => {
  const worker = createXygWasmWorker({ workerUrl: "/packages/xy-client/dist/wasm-worker.js", wasm, maxArenaBytes });
  worker.__requestedArena = maxArenaBytes;
  const actual = worker.worker, deliver = actual.onmessage; actual.__graphOwner = state.nextOwner = (state.nextOwner ?? 0)+1;
  actual.onmessage = event => {
    // Test-only terminal metadata also retains refusals without an XYGR body.
    state.transportReplies ??= [];
    state.transportReplies.push({owner:actual.__graphOwner,requestId:event.data.requestId,ok:event.data.ok,error:event.data.error,at:performance.now()});
    if (actual.__temporalCapture) {
      state.temporalWire ??= [];
      const raw=event.data.value?.bytes;
      state.temporalWire.push({kind:"reply",owner:actual.__graphOwner,requestId:event.data.requestId,ok:event.data.ok,error:event.data.error,bytes:raw instanceof ArrayBuffer?Array.from(new Uint8Array(raw)):null});
    }
    const value = event.data.value;
    if (value?.bytes instanceof ArrayBuffer && value.bytes.byteLength && String.fromCharCode(...new Uint8Array(value.bytes,0,4)) === "XYGR") {
      if (state.inject === "malformed-gpu") { view(section(value.bytes, "gpu.node.coord.bytes")).setFloat32(0, NaN, true); state.inject = null; }
      if (["malformed-admission-version","malformed-admission-bound"].includes(state.inject)) {
        const words=view(section(value.bytes,"relayout.admission.u32"));
        words.setUint32(state.inject.endsWith("version")?0:4,state.inject.endsWith("version")?2:65,true);state.inject=null;
      }
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
      state.replies.push({ owner:actual.__graphOwner, requestId: event.data.requestId, bytes: new Uint8Array(value.bytes).slice(), lifetime: value.lifetime, sequence: value.sequence });
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
  el.querySelector("canvas").addEventListener("click",e=>{
    // TEST ONLY: read native offsets during dispatch, independently of the
    // controller. clientWidth/Height use the padding box (not CSS width/rect).
    const c=e.currentTarget,style=getComputedStyle(c),padding=[parseFloat(style.paddingLeft),parseFloat(style.paddingTop)],
      extent=[c.clientWidth-padding[0]-parseFloat(style.paddingRight),c.clientHeight-padding[1]-parseFloat(style.paddingBottom)],
      offsets=[e.offsetX,e.offsetY],view=p.handle.snapshot()?.camera??p.camera;
    const record={trusted:e.isTrusted,canvas:e.target===c,button:e.button,detail:e.detail,clientX:e.clientX,clientY:e.clientY,offsets,padding,extent,zoom:c.currentCSSZoom,
      nativeCoordinates:offsets.map((v,i)=>(v-padding[i])*view[i+4]/extent[i])};
    p.trusted.push(record);
    const command=state.commands.at(-1);
    if(command?.instanceId===p.id&&command.operation===1) command.nativeEvent=record;
  });
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

// A DOM-only visual-coordinate oracle for unsupported motion paths. A transparent
// sibling probe follows the same CSS motion as the canvas, or inherits the
// ancestor motion. Its point is measured by the browser, never by product code.
state.motionPoint = async target => {
  const p=state.pointer, canvas=p.el.querySelector('canvas'), surface=canvas.parentElement;
  p.el.style.cssText='position:relative;width:640px;height:320px';
  surface.style.cssText='position:relative;width:640px;height:320px';
  canvas.style.display='block'; p.el.lastElementChild.style.visibility='hidden';
  const motion='offset-path:path("M 450 150 L 700 150");offset-distance:0px;offset-rotate:30deg;offset-anchor:0px 0px';
  const element=target==='canvas'?canvas:p.el; element.style.cssText+=';'+motion;
  const probe=document.createElement('div');
  probe.style.cssText='position:absolute;left:0;top:0;width:640px;height:320px;pointer-events:none;'+(target==='canvas'?motion:'');
  const marker=document.createElement('span'),css=state.pointerPoint('node',1);
  marker.style.cssText=`position:absolute;left:${css[0]}px;top:${css[1]}px;width:0;height:0;pointer-events:none`;
  probe.append(marker);surface.append(probe);
  const link=document.createElement('a');link.href=`#motion-path-${target}`;link.style.display='block';surface.before(link);link.append(surface);
  const rect=marker.getBoundingClientRect(), style=getComputedStyle(element), client=[rect.x,rect.y];
  p.motionDelivery=null;
  p.el.addEventListener('click',event=>{p.motionDelivery={trusted:event.isTrusted,target:event.target.tagName,canvas:event.target===canvas,clientX:event.clientX,clientY:event.clientY,defaultPrevented:event.defaultPrevented};});
  return {css,client,predicate:{transform:style.transform,rotate:style.rotate,offsetPath:style.offsetPath,offsetDistance:style.offsetDistance,offsetRotate:style.offsetRotate,offsetAnchor:style.offsetAnchor},hit:document.elementFromPoint(...client)?.tagName};
};
state.canvasDigest = async () => {
  const c=state.pointer.el.querySelector('canvas'),data=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256',data))].map(b=>b.toString(16).padStart(2,'0')).join('');
};

// Test-only composed-tree fixtures: the chart remains light DOM, assigned to a
// slot whose shadow wrapper controls its actual display. A zero-size marker
// inherits that display and supplies a browser-measured visual coordinate.
state.slotPoint = (kind,nested=false) => {
  const p=state.pointer, canvas=p.el.querySelector('canvas'), surface=canvas.parentElement;
  p.el.style.cssText='position:relative;width:640px;height:320px';
  surface.style.cssText='position:relative;width:640px;height:320px';
  canvas.style.display='block';p.el.lastElementChild.style.visibility='hidden';
  const outer=document.createElement('xy-slot-fixture');
  outer.style.cssText='display:block;position:fixed;left:200px;top:50px;width:640px;height:320px;z-index:10000';
  const makeShadow=host=>{
    const root=host.attachShadow({mode:'open'}), wrapper=document.createElement('div'),slot=document.createElement('slot');
    wrapper.style.cssText='position:relative;width:640px;height:320px;transform-origin:0 0';slot.name='chart';wrapper.append(slot);root.append(wrapper);
    return {root,wrapper,slot};
  };
  const outerTree=makeShadow(outer);p.el.before(outer);p.slotHost=outer;
  let owner=outer;
  if(nested){const inner=document.createElement('xy-inner-slot-fixture');inner.style.cssText='display:block;width:640px;height:320px';inner.slot='chart';outer.append(inner);makeShadow(inner);owner=inner;}
  p.el.slot='chart';owner.append(p.el);
  if(kind==='rotate') outerTree.wrapper.style.transform='rotate(30deg)';
  if(kind==='motion') outerTree.wrapper.style.cssText+=';offset-path:path("M 450 150 L 700 150");offset-distance:0px;offset-rotate:30deg;offset-anchor:0px 0px';
  if(kind==='scale') outerTree.wrapper.style.transform='scale(0.8,0.75)';
  const probe=document.createElement('span'),css=state.pointerPoint('node',1);
  probe.style.cssText=`position:absolute;left:${css[0]}px;top:${css[1]}px;width:0;height:0;pointer-events:none`;surface.append(probe);
  const link=document.createElement('a');link.href=`#slot-${nested?'nested-':''}${kind}`;link.style.display='block';surface.before(link);link.append(surface);
  p.slotDelivery=null;p.el.addEventListener('click',event=>{p.slotDelivery={trusted:event.isTrusted,target:event.target.tagName,canvas:event.target===canvas,clientX:event.clientX,clientY:event.clientY,defaultPrevented:event.defaultPrevented};});
  const describe=element=>{const s=getComputedStyle(element);return {tag:element.tagName,transform:s.transform,rotate:s.rotate,scale:s.scale,translate:s.translate,perspective:s.perspective,offsetPath:s.offsetPath,assignedSlot:element.assignedSlot?.tagName??null};};
  const walk=composed=>{const chain=[];for(let element=canvas;element;){chain.push(describe(element));const root=element.getRootNode();element=(composed?element.assignedSlot:null)??element.parentElement??(root instanceof ShadowRoot?root.host:null);}return chain;};
  const r=probe.getBoundingClientRect(),client=[r.x,r.y];
  return {kind,nested,css,client,hit:document.elementFromPoint(...client)?.tagName,legacyWalk:walk(false),composedWalk:walk(true),wrapper:describe(outerTree.wrapper)};
};

// TEST ONLY: native DIV/BODY hosts with closed roots deliberately conceal the
// assigned slots from the controller's public ancestry walk. The marker is a
// browser display oracle; Rust geometry only chooses the intended graph point.
state.closedPoint = ({kind,tag='div',named=true,nested=false}) => {
  const p=state.pointer,c=p.el.querySelector('canvas'),surface=c.parentElement;
  p.el.style.cssText='position:relative;width:640px;height:320px';
  surface.style.cssText='position:relative;width:640px;height:320px';c.style.display='block';p.el.lastElementChild.style.visibility='hidden';
  const host=document.createElement(tag);host.style.cssText='display:block;margin:0;position:fixed;left:200px;top:50px;width:640px;height:320px;z-index:10000';
  const make=host=>{const root=host.attachShadow({mode:'closed'}),wrapper=document.createElement('div'),slot=document.createElement('slot');
    wrapper.style.cssText='position:relative;width:640px;height:320px;transform-origin:0 0';if(named)slot.name='chart';wrapper.append(slot);root.append(wrapper);return wrapper;};
  const wrapper=make(host);p.el.before(host);p.closedHost=host;let owner=host,innerWrapper;
  if(nested){const inner=document.createElement(tag==='div'?'body':'div');inner.style.cssText='display:block;margin:0;width:640px;height:320px';if(named)inner.slot='chart';host.append(inner);innerWrapper=make(inner);owner=inner;}
  p.el.slot=named?'chart':'';owner.append(p.el);
  if(kind==='rotate')wrapper.style.transform='rotate(30deg)';
  if(kind==='motion')wrapper.style.cssText+=';offset-path:path("M 450 150 L 700 150");offset-distance:0px;offset-rotate:30deg;offset-anchor:0px 0px';
  if(kind==='zoom14')wrapper.style.zoom='1.4';
  if(kind==='zoom125')wrapper.style.zoom='1.25';
  if(kind==='net2'){wrapper.style.zoom='2';innerWrapper.style.zoom='0.5';}
  if(kind==='net14'){wrapper.style.zoom='1.4';innerWrapper.style.zoom=String(1/1.4);}
  const css=state.pointerPoint('node',1),probe=document.createElement('span');probe.style.cssText=`position:absolute;left:${css[0]}px;top:${css[1]}px;width:0;height:0;pointer-events:none`;surface.append(probe);
  const link=document.createElement('a');link.href=`#closed-${tag}-${named?'named':'default'}-${kind}-${nested?'nested-':''}DPR${devicePixelRatio}`;link.style.display='block';surface.before(link);link.append(surface);
  p.closedDelivery=null;p.el.addEventListener('click',e=>{p.closedDelivery={trusted:e.isTrusted,canvas:e.target===c,target:e.target.tagName,clientX:e.clientX,clientY:e.clientY,defaultPrevented:e.defaultPrevented};});
  const chain=[];for(let el=c;el;){const st=getComputedStyle(el);chain.push({tag:el.tagName,transform:st.transform,rotate:st.rotate,offsetPath:st.offsetPath,slot:el.assignedSlot?.tagName??null});const root=el.getRootNode();el=el.assignedSlot??el.parentElement??(root instanceof ShadowRoot?root.host:null);}
  const rect=probe.getBoundingClientRect(),client=[rect.x,rect.y],st=getComputedStyle(wrapper);
  return {kind,tag,named,nested,fragment:new URL(link.href).hash,css,client,hit:document.elementFromPoint(...client)?.tagName,chain,zoom:c.currentCSSZoom,canvasStyleZoom:getComputedStyle(c).zoom,dpr:devicePixelRatio,wrapper:{transform:st.transform,rotate:st.rotate,offsetPath:st.offsetPath,zoom:st.zoom}};
};

// Real public progressive attachment; no held replies or layout callback hooks.
state.progressiveFixture = async (count, id, load = {}, arena, sourceCamera) => {
  const f = (name, dtype, values) => ({name, dtype:DTYPE[dtype], values});
  const nodes = new Uint8Array(count*16), edges = new Uint8Array(count*16);
  for (let i=0;i<count;i++) { new DataView(nodes.buffer).setUint32(i*16,i+1,true); new DataView(edges.buffer).setUint32(i*16,i+10001,true); }
  const document = encodeContainer('XYGF', [f('status','u32',[0]),f('kind','utf8','graph'),f('composition.version','u32',[2]),f('node.uuid','uuid',nodes),f('edge.uuid','uuid',edges),f('edge.derived','u8',Array(count).fill(0)),f('edge.layer','u32',Array(count).fill(0xffffffff)),f('edge.order','i64',Array(count).fill(-1n)),f('edge.path','u64',Array(count).fill(0xffffffffffffffffn)),f('edge.source','u64',Array.from({length:count},(_,i)=>BigInt(i))),f('edge.target','u64',Array.from({length:count},(_,i)=>BigInt((i+1)%count))),f('graph.directed','u8',[0])]);
  const started=performance.now();const worker=makeWorker(undefined, arena); await worker.ready;const workerReady=performance.now();
  const el=container(), p={id,count,arena:arena??16*1024*1024,defaultArena:arena===undefined,el,worker,started,workerReady,frames:[],errors:[],beats:0,document,load:{progressive:true,...load},camera:sourceCamera??[count===1000?.25:25,count===1000?.25:25,320,160,640,320,1]};
  state.progressives ??= []; state.progressives.push(p);
  el.addEventListener('xy:graph-render',e=>p.frames.push({at:performance.now(),revision:e.detail.revision,progress:e.detail.relayout,camera:[...e.detail.camera],pixels:state.pixel(el).filter((v,i)=>i%4===3&&v>0).length}));
  for(const kind of ['error','stale']) el.addEventListener(`xy:graph-${kind}`,e=>p.errors.push(e.detail));
  p.painted=[]; p.clicks=[]; p.captures={};
  el.addEventListener('xy:graph-render',()=>requestAnimationFrame(()=>{
    if(!el.isConnected||!p.handle?.snapshot())return;
    const pixels=state.pixel(el);let hash=2166136261,nonzero=0;
    for(let i=0;i<pixels.length;i++){hash=Math.imul(hash^pixels[i],16777619)>>>0;if(i%4===3&&pixels[i]>0)nonzero++;}
    const progress=p.handle.snapshot().relayout;
    p.painted.push({at:performance.now(),progress,hash,pixels:nonzero});
    const stage=progress?.done?'final':BigInt(progress?.steps??0)>=100n?'intermediate':'initial';
    if(!p.captures[stage])p.captures[stage]=el.querySelector('canvas').toDataURL('image/png');
  }));
  el.addEventListener('click',e=>{if(e.isTrusted&&e.target.tagName==='CANVAS')p.clicks.push({at:performance.now(),trusted:e.isTrusted,prevented:e.defaultPrevented,progress:p.handle.snapshot()?.relayout});});
  p.heartbeats=[]; p.trusted=[];
  el.addEventListener('keydown',e=>{if(e.isTrusted)p.trusted.push({key:e.key,trusted:e.isTrusted,at:performance.now(),progress:p.handle.snapshot()?.relayout,prevented:e.defaultPrevented});});
  p.timer=setInterval(()=>{p.beats++;p.heartbeats.push(performance.now());},5);
  p.handle=state.attach({el,worker,instanceId:id,document,load:p.load,camera:p.camera});
  try { await p.handle.ready; } catch(error) { clearInterval(p.timer); await p.handle.dispose(); await worker.dispose(); el.remove(); throw error; }
  return {revision:p.handle.snapshot().revision,progress:p.handle.snapshot().relayout};
};

// Public retained temporal fixture. XYGF is canonical authoring ingress only;
// Rust creates the retained document, computes membership, geometry and picks.
state.temporalFixture = async (progressive = false) => {
  const history = await fetch("/tests/fixtures/temporal/assertion-history.json").then(r=>r.json());
  const ids = values => Uint8Array.from(values.flatMap(v=>Array(16).fill(v)));
  const f=(name,type,values)=>({name,dtype:DTYPE[type],values});
  const binding={nodeIds:ids(history.nodes),edgeIds:ids(history.edges),sourceIds:ids(history.sources),targetIds:ids(history.targets)};
  for(const name of ["nodeValidFrom","nodeValidTo","edgeValidFrom","edgeValidTo","edgeEventAt"]) binding[name]={values:BigInt64Array.from(history[name],BigInt),validity:new Uint8Array(history[name].length).fill(1)};
  const document=encodeContainer("XYGF",[f("status","u32",[0]),f("kind","utf8","graph"),f("composition.version","u32",[2]),f("node.uuid","uuid",binding.nodeIds),f("edge.uuid","uuid",binding.edgeIds),f("edge.derived","u8",[0,0]),f("edge.layer","u32",[0xffffffff,0xffffffff]),f("edge.order","i64",[-1n,-1n]),f("edge.path","u64",[0xffffffffffffffffn,0xffffffffffffffffn]),f("edge.source","u64",[0n,0n]),f("edge.target","u64",[1n,2n]),f("graph.directed","u8",[1])]);
  const original=document.slice(), worker=makeWorker(), clockWorker=makeWorker();worker.worker.__temporalCapture=true;await Promise.all([worker.ready,clockWorker.ready]);
  const controller=await XygWasmTemporalController.create(clockWorker,{instanceId:950n,groupId:951n,domain:[0n,40n],cursor:10n,step:1n,reducedMotion:false});await controller.setRange(0n,40n);
  const el=container(), publications=[], failures=[];
  el.dataset.temporalFixture='';
  el.addEventListener('xy:graph-render',e=>publications.push(e.detail));el.addEventListener('xy:graph-error',e=>failures.push(e.detail));
  const handle=state.attach({el,worker,instanceId:950n,document,load:{x:[100,300,500],y:[160,160,160],progressive},camera:[1,1,0,0,640,320,1],temporal:{controller,binding,budget:14n}});
  await handle.ready;await handle.whenIdle();
  state.retainedTime={el,worker,clockWorker,controller,handle,document,original,history,publications,failures};
  return true;
};
