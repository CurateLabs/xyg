import { GPUAdmissionPending } from "./41_gpu_storage";
/** GPU-v1 boundary and generic screen-space paint adapter (§29; graph-interaction S5b).
 * Rust owns all geometry, style, membership, clipping and reference decisions. */
import { makeProgram, MARKER_SDF_GLSL, uniformOf } from "./40_gl";
import { parseColor } from "./20_theme";
import { acquireGLHost, GLHost, type GLHostClient } from "./42_glhost";
import { XygWasmError } from "./47_wasm";

interface RawSection { name: string; index: number; dtype: number; count: number; bytes: Uint8Array }
export interface GraphGpuSnapshot {
  readonly sections: ReadonlyMap<string, RawSection>;
  readonly counts: readonly [number, number, number, number, number];
  readonly transforms: readonly (readonly [number, number])[];
}
const invalid = (reason: string): never => { throw new XygWasmError("GF_INTERACTION_INVALID", `malformed graph GPU-v1: ${reason}`); };
const viewOf = (b: Uint8Array) => new DataView(b.buffer, b.byteOffset, b.byteLength);

/** Validate the complete trust boundary before any GPU allocation or upload. */
export function decodeGraphGpu(sections: ReadonlyMap<string, RawSection>): GraphGpuSnapshot {
  const expected = new Set<string>();
  function get(name: string, index: number, dtype: number, count: number): Uint8Array {
    const key = `${name}#${index}`, s = sections.get(key);
    expected.add(key);
    const width = dtype === 2 ? 4 : dtype === 5 ? 8 : 1;
    if (!Number.isSafeInteger(count) || count < 0 || !Number.isSafeInteger(count * width)
        || !s || s.name !== name || s.index !== index || s.dtype !== dtype || s.count !== count
        || s.bytes.byteLength !== count * width) invalid(key);
    return s.bytes;
  }
  const h = viewOf(get("gpu.header.u32", 0, 2, 8));
  const word = (i: number) => h.getUint32(i * 4, true);
  if (word(0) !== 1 || word(1) !== 0 || word(7) !== 0) invalid("header");
  const counts = [word(2), word(3), word(4), word(5), word(6)] as const;
  const [n, m, p, heads, f] = counts;
  const transforms: Array<readonly [number, number]> = [];
  for (let i = 0; i < 3; i++) {
    const t = viewOf(get("gpu.transform.f64", i, 5, 2));
    const offset = t.getFloat64(0, true), scale = t.getFloat64(8, true);
    if (!Number.isFinite(offset) || !Number.isFinite(scale) || scale <= 0) invalid("transform");
    transforms.push(Object.freeze([offset, scale]));
  }
  for (const [name, columns, count] of [
    ["gpu.node.coord.bytes", 2, n], ["gpu.shaft.coord.bytes", 4, p],
    ["gpu.shaft.attr.bytes", 4, p], ["gpu.head.coord.bytes", 6, heads],
    ["gpu.frame.coord.bytes", 4, f], ["gpu.frame.width.bytes", 1, f],
  ] as const) {
    for (let i = 0; i < columns; i++) {
      const v = viewOf(get(name, i, 6, count * 4));
      for (let at = 0; at < v.byteLength; at += 4) if (!Number.isFinite(v.getFloat32(at, true))) invalid(name);
    }
  }
  for (const [name, count, limit] of [
    ["gpu.shaft.edge.u32", p, m], ["gpu.head.piece.u32", heads, p], ["gpu.frame.node.u32", f, n],
  ] as const) {
    const v = viewOf(get(name, 0, 2, count));
    let previous = -1;
    for (let at = 0; at < v.byteLength; at += 4) {
      const ref = v.getUint32(at, true);
      if (ref >= limit || (name === "gpu.head.piece.u32" && ref <= previous)) invalid(name);
      previous = ref;
    }
  }
  for (const flag of get("gpu.shaft.flags.u8", 0, 1, p)) if (flag > 1) invalid("shaft flags");
  for (const [kind, count] of [["node", n], ["edge", m]] as const) {
    const b = get(`gpu.${kind}.style.bytes`, 0, 6, count * 60), v = viewOf(b);
    for (let at = 0; at < b.length; at += 60) {
      if (b[at + 24]! > 5 || b[at + 25]! > 3 || b[at + 26]! > 1 || b[at + 27]! > 7
          || b[at + 56]! > 1 || b[at + 57] || b[at + 58] || b[at + 59]) invalid(`${kind} style`);
      for (const i of [12, 16, 20, 40, 44, 48, 52]) if (!Number.isFinite(v.getFloat32(at + i, true))) invalid(`${kind} style float`);
    }
    const state = get(`gpu.${kind}.state.u8`, 0, 1, count * 4);
    for (let at = 0; at < state.length; at += 4) {
      if (state[at]! > 7 || (state[at + 1]! & ~15) || (state[at + 2]! & ~0x17) || state[at + 3]) invalid(`${kind} state`);
    }
  }
  for (const [key, section] of sections) if (section.name.startsWith("gpu.") && !expected.has(key)) invalid(`unknown ${key}`);
  if (expected.size !== 33 || sections.get("render.node_x.f64#0")?.count !== n
      || sections.get("render.edge_source.u64#0")?.count !== m) invalid("published counts");
  return Object.freeze({ sections, counts, transforms: Object.freeze(transforms) });
}

// Both draw bindings feed the same geometry and fragment program. All inputs
// remain Rust's raw GPU-v1 records, with no per-piece expansion or narrowing.
const VERTEX_DECLARATIONS = `
uniform vec2 u_view; uniform vec2 u_x; uniform vec2 u_y; uniform vec2 u_dash;
uniform int u_focus; uniform vec4 u_focusColor;
flat out vec4 v_fill; flat out vec4 v_stroke; flat out vec4 v_halo; flat out vec4 v_body;
flat out vec4 v_sizes; flat out vec4 v_dash; flat out int v_shape; flat out int v_kind;
out vec2 v_local; flat out vec2 v_extent;`;

const VERTEX_TEXTURES = `
uniform highp usampler2D u_style; uniform highp usampler2D u_state; uniform highp usampler2D u_refs;
uvec4 raw(highp usampler2D tex, uint i) { uint w=uint(textureSize(tex,0).x); return texelFetch(tex,ivec2(int(i%w),int(i/w)),0); }
uvec4 style(uint i,uint field) { return raw(u_style,i*15u+field); }
float scalar(uint i,uint field) { uvec4 v=style(i,field); return uintBitsToFloat(v.x|(v.y<<8u)|(v.z<<16u)|(v.w<<24u)); }
vec4 color(uint i,uint field) { return vec4(style(i,field))/255.0; }`;

const VERTEX_STYLE_ARGUMENTS = `uint row, out uvec4 state, out int shape,
  out float size, out float width, out float opacity, out float halo, out float body,
  out vec4 fill, out vec4 stroke, out vec4 haloColor, out vec4 bodyColor`;

const VERTEX_FETCH_STYLE = `void fetchStyle(${VERTEX_STYLE_ARGUMENTS}) {
  state=raw(u_state,row); shape=int(style(row,6u).x);
  size=scalar(row,3u); width=scalar(row,4u); opacity=scalar(row,5u);
  fill=color(row,8u); stroke=color(row,9u); haloColor=color(row,7u); bodyColor=color(row,8u);
  halo=scalar(row,10u); body=scalar(row,11u);
}`;

const VERTEX_GEOMETRY = `
vec2 xy(float x,float y) { return vec2(x*u_x.y+u_x.x,y*u_y.y+u_y.x); }
void main() {
  uint row=GRAPH_ROW;
  uint corner=GRAPH_CORNER;
  if(u_kind==0) row=a_ref;
  if(u_kind==1) row=raw(u_refs,uint(gl_InstanceID)).r;
  if(u_kind==2) row=raw(u_refs,a_ref).r;
  uvec4 state; float size,width,opacity,halo,body;
  fetchStyle(row,state,v_shape,size,width,opacity,halo,body,v_fill,v_stroke,v_halo,v_body);
  v_kind=u_kind;
  v_sizes=vec4(size,width,halo,body);
  v_dash=vec4(b1,b2,b3*u_dash.y+u_dash.x,float(a_flags));
  vec2 q=vec2(float(corner&1u),float((corner>>1u)&1u));
  vec2 screen;
  if(u_kind==3) {
    float radius=max(size,v_halo.a>0.0?halo:0.0)*0.5+1.0;
    if(u_focus==1) radius=size*0.5+4.0;
    v_extent=vec2(radius); v_local=(q*2.0-1.0)*radius;
    screen=xy(a0,a1)+v_local;
  } else if(u_kind==0) {
    vec2 lo=xy(a0,a1),hi=xy(a2,a3); float width=b0+(u_focus==1?2.0:0.0);
    v_extent=(hi-lo)*0.5; v_local=(q*2.0-1.0)*(v_extent+width+1.0);
    screen=(lo+hi)*0.5+v_local; v_sizes.y=width;
    v_fill=v_stroke;
  } else if(u_kind==1) {
    vec2 start=xy(a0,a1),end=xy(a2,a3),d=end-start;
    float length=length(d); vec2 direction=length>0.0?d/length:vec2(1.0,0.0);
    float halfWidth=b0+(u_focus==1?2.0:0.0);
    v_extent=vec2(length,halfWidth); v_local=vec2(q.x*length,(q.y*2.0-1.0)*(halfWidth+1.0));
    screen=start+direction*v_local.x+vec2(-direction.y,direction.x)*v_local.y;
  } else {
    screen=gl_VertexID==0?xy(a0,a1):gl_VertexID==1?xy(a2,a3):xy(a4,a5);
    v_local=vec2(0.0); v_extent=vec2(0.0); v_fill=color(row,9u);
  }
  if(u_focus==1) {
    if((state.y&1u)==0u) screen=vec2(-1e10);
    v_fill=u_focusColor; v_stroke=v_fill; v_halo=vec4(0.0); v_body=vec4(0.0);
  }
  gl_Position=vec4(screen.x/u_view.x*2.0-1.0,1.0-screen.y/u_view.y*2.0,0.0,1.0);
}`;

const VERTEX = `#version 300 es
precision highp float; precision highp int;
#define GRAPH_ROW uint(gl_InstanceID)
#define GRAPH_CORNER uint(gl_VertexID)
layout(location=0) in float a0; layout(location=1) in float a1;
layout(location=2) in float a2; layout(location=3) in float a3;
layout(location=4) in float a4; layout(location=5) in float a5;
layout(location=6) in float b0; layout(location=7) in float b1;
layout(location=8) in float b2; layout(location=9) in float b3;
layout(location=10) in uint a_ref; layout(location=11) in uint a_flags;
uniform int u_kind;
${VERTEX_DECLARATIONS}
${VERTEX_TEXTURES}
${VERTEX_FETCH_STYLE}
${VERTEX_GEOMETRY}`;

const NODE_VERTEX = `#version 300 es
precision highp float; precision highp int;
#define GRAPH_ROW (uint(gl_VertexID)/6u)
#define GRAPH_CORNER nodeCorner(uint(gl_VertexID))
uniform highp usampler2D u_coordX; uniform highp usampler2D u_coordY;
#define a0 coordinate(u_coordX,row)
#define a1 coordinate(u_coordY,row)
// Reference-only branches are dead in this node input binding.
#define u_kind 3
const float a2=0.0,a3=0.0,a4=0.0,a5=0.0,b0=0.0,b1=0.0,b2=0.0,b3=0.0;
const uint a_ref=0u,a_flags=0u;
${VERTEX_DECLARATIONS}
${VERTEX_TEXTURES}
uint nodeCorner(uint vertex) {
  uint k=vertex%6u;
  return k<3u?k:(k==3u?2u:(k==4u?1u:3u));
}
float coordinate(highp usampler2D tex,uint row) {
  uvec4 v=raw(tex,row); return uintBitsToFloat(v.x|(v.y<<8u)|(v.z<<16u)|(v.w<<24u));
}
${VERTEX_FETCH_STYLE}
${VERTEX_GEOMETRY}`;

const FRAGMENT = `#version 300 es
precision highp float; precision highp int;
uniform int u_focus;
flat in vec4 v_fill; flat in vec4 v_stroke; flat in vec4 v_halo; flat in vec4 v_body;
flat in vec4 v_sizes; flat in vec4 v_dash; flat in int v_shape; flat in int v_kind;
in vec2 v_local; flat in vec2 v_extent;
out vec4 outColor;
${MARKER_SDF_GLSL}
float coverage(float distance) { return clamp(0.5-distance/max(fwidth(distance),0.0001),0.0,1.0); }
vec4 paint(vec4 c,float coverage) { float a=c.a*coverage; return vec4(c.rgb*a,a); }
vec4 over(vec4 a,vec4 b) { return a+b*(1.0-a.a); }
void main() {
  if(v_kind==3) {
    float size=max(v_sizes.x,0.0001);
    float sd=xyMarkerSdf(v_local/size,v_shape)*size;
    if(u_focus==1) outColor=paint(v_fill,coverage(abs(sd-2.0)-1.0));
    else {
      float outer=coverage(sd), inner=coverage(sd+v_sizes.y);
      vec4 body=over(paint(v_stroke,max(outer-inner,0.0)),paint(v_fill,inner));
      float halo=coverage(length(v_local)-v_sizes.z*0.5);
      outColor=over(body,paint(v_halo,halo));
    }
  } else if(v_kind==0) {
    float d=max(abs(v_local.x)-v_extent.x,abs(v_local.y)-v_extent.y);
    outColor=paint(v_fill,coverage(abs(d)-v_sizes.y));
  } else if(v_kind==1) {
    if(v_dash.x>0.0 && v_dash.y>=0.0 && mod(v_dash.z+v_local.x,v_dash.x+v_dash.y)>v_dash.x) discard;
    float d=abs(v_local.y);
    if(u_focus==1) outColor=paint(v_fill,coverage(abs(d-(v_extent.y-1.0))-1.0));
    else outColor=over(paint(v_stroke,coverage(d-v_sizes.y*0.5)),
         over(paint(v_body,coverage(d-v_sizes.w*0.5)),paint(v_halo,coverage(d-v_sizes.z*0.5))));
  } else outColor=paint(v_fill,1.0);
  if(outColor.a<=0.001) discard;
}`;

/** A transient lost context, distinct from admission or malformed GPU input. */
export class GraphGpuContextLost extends Error {
  constructor() { super("xy: graph GPU context unavailable"); this.name = "GraphGpuContextLost"; }
}

/** Existing GLHost lifecycle/presentation with only raw graph GPU-v1 uploads. */
export function createGraphGpuPainter(surface: HTMLElement) {
  const doc = surface.ownerDocument, canvas = doc.createElement("canvas"), stage = doc.createElement("canvas");
  canvas.dataset.xyGraphGpu = "v1";
  const present = canvas.getContext("2d"), staging = stage.getContext("2d");
  if (!present || !staging) throw new Error("xy: graph presentation canvas unavailable");
  let disposed = false, program: WebGLProgram | null = null, nodeProgram: WebGLProgram | null = null;
  let buffers: WebGLBuffer[] = [], textures: WebGLTexture[] = [], vaos: WebGLVertexArrayObject[] = [];
  let visible = true;
  let accepted: { gpu: GraphGpuSnapshot; camera: readonly number[]; focus: Float32Array } | null = null;
  const contextWaiters = new Set<(error?: unknown) => void>();
  const client: GLHostClient = {
    _dashboardResourceState() { return { derivedBytes: host.clientResourceBytes(client), visible, interacting: false }; },
    _applyDashboardResidency(retained) {
      if (!retained) { host.releaseClientStorage(client); program = null; nodeProgram = null; buffers = []; textures = []; vaos = []; }
      // An empty publication owns storage without needing a shader program.
      else if (!program && !nodeProgram && textures.length === 0 && accepted) queueMicrotask(() => { if (!disposed && accepted) {
        try { paint(accepted.gpu, accepted.camera); } catch (error) { if (!(error instanceof GPUAdmissionPending)) throw error; }
      } });
    },
    _onGlHostContextLost() { program = null; nodeProgram = null; buffers = []; textures = []; vaos = []; },
    _onGlHostContextRestored() {
      for (const resume of [...contextWaiters]) resume();
      if (!disposed && accepted) paint(accepted.gpu, accepted.camera);
    },
  };
  let host = acquireGLHost(doc, client);
  if (!host) { host = new GLHost(doc, () => {}); host._register(client); }
  const visibility = typeof IntersectionObserver === "undefined" ? null : new IntersectionObserver(entries => {
    const next = entries[entries.length - 1]?.isIntersecting === true;
    if (next !== visible) { visible = next; host.dashboardResourceChanged(client); }
  });
  visibility?.observe(surface);
  surface.appendChild(canvas);
  function releaseObjects() {
    const gl = host.clientContext(client);
    if (!gl.isContextLost()) {
      for (const buffer of buffers) gl.deleteBuffer(buffer);
      for (const texture of textures) gl.deleteTexture(texture);
      for (const vao of vaos) gl.deleteVertexArray(vao);
    }
    buffers = []; textures = []; vaos = [];
  }
  function paint(gpu: GraphGpuSnapshot, camera: readonly number[]) {
    if (disposed) return;
    if (camera.length !== 7 || !camera.every(Number.isFinite) || !camera[0] || !camera[1]
        || camera[4]! <= 0 || camera[5]! <= 0 || camera[6]! <= 0) invalid("camera");
    // Report demand even when admission currently blocks the pass. Rust alone
    // ranks the updated last-use identity when a budget watcher re-plans.
    host.markDashboardResourceUsed(client);
    const width = Math.max(1, Math.round(camera[4]! * camera[6]!)), height = Math.max(1, Math.round(camera[5]! * camera[6]!));
    stage.width = width; stage.height = height;
    const focusToken = doc.defaultView?.getComputedStyle(surface).getPropertyValue("--chart-focus").trim();
    const focus = Float32Array.from(parseColor(surface, focusToken || "#aa99ec", [170 / 255, 153 / 255, 236 / 255, 1]));
    let completed: boolean;
    try { completed = host.render(client, staging, width, height, () => {
      const gl = host.clientContext(client);
      releaseObjects();
      const bytes = (name: string, index = 0) => gpu.sections.get(`${name}#${index}`)!.bytes;
      const [n, , p, h, f] = gpu.counts;
      // Two equivalent triangles avoid per-node instancing. Keep the existing
      // reference binding for frames and counts beyond one GLsizei draw.
      const nodeTriangles = f === 0 && n <= Math.floor(0x7fff_ffff / 6);
      const max = gl.getParameter(gl.MAX_TEXTURE_SIZE) as number;
      // Lost contexts return null parameters. That is not a real zero texture
      // capacity and must not be converted into an ordinary capacity refusal.
      if (gl.isContextLost()) throw new GraphGpuContextLost();
      function texture(data: Uint8Array, unit: number, integer: boolean) {
        const tex = gl.createTexture(); if (!tex) throw new Error("xy: graph texture allocation failed");
        textures.push(tex); gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, tex);
        const total = data.byteLength / 4, w = Math.max(1, Math.min(max, total)), h = Math.max(1, Math.ceil(total / w));
        if (h > max) throw new RangeError("xy: graph GPU texture capacity exceeded");
        gl.texStorage2D(gl.TEXTURE_2D, 1, integer ? gl.R32UI : gl.RGBA8UI, w, h);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
        const rows = Math.floor(total / w), tail = total % w;
        const values = integer ? new Uint32Array(data.buffer, data.byteOffset, data.byteLength / 4) : data;
        if (rows) gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, w, rows, integer ? gl.RED_INTEGER : gl.RGBA_INTEGER, integer ? gl.UNSIGNED_INT : gl.UNSIGNED_BYTE, values.subarray(0, rows * w * (integer ? 1 : 4)));
        if (tail) gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, rows, tail, 1, integer ? gl.RED_INTEGER : gl.RGBA_INTEGER, integer ? gl.UNSIGNED_INT : gl.UNSIGNED_BYTE, values.subarray(rows * w * (integer ? 1 : 4)));
        return tex;
      }
      const styles = [texture(bytes("gpu.node.style.bytes"), 0, false), texture(bytes("gpu.edge.style.bytes"), 0, false)];
      const states = [texture(bytes("gpu.node.state.u8"), 1, false), texture(bytes("gpu.edge.state.u8"), 1, false)];
      const refs = texture(bytes("gpu.shaft.edge.u32"), 2, true);
      const nodeCoords = nodeTriangles && n ? [texture(bytes("gpu.node.coord.bytes", 0), 3, false), texture(bytes("gpu.node.coord.bytes", 1), 4, false)] : null;
      for (const focusPass of [0, 1]) for (const [kind, count, column] of [[0, f, "frame"], [1, p, "shaft"], [2, h, "head"], [3, n, "node"]] as const) {
        if (!count || (focusPass && kind === 2)) continue;
        const proceduralNode = nodeTriangles && kind === 3;
        const selected = proceduralNode
          ? (nodeProgram ??= makeProgram(gl, NODE_VERTEX, FRAGMENT, (kind, source) => host.getOrCreateShader(kind, source)))
          : (program ??= makeProgram(gl, VERTEX, FRAGMENT, (kind, source) => host.getOrCreateShader(kind, source)));
        gl.useProgram(selected);
        const uniform = (name: string) => uniformOf(gl, selected, name);
        gl.uniform2f(uniform("u_view"), camera[4]!, camera[5]!);
        gl.uniform4fv(uniform("u_focusColor"), focus);
        for (const [name, i] of [["u_x", 0], ["u_y", 1], ["u_dash", 2]] as const) {
          const t = gpu.transforms[i]!; gl.uniform2f(uniform(name), t[0], 1 / t[1]);
        }
        const vao = gl.createVertexArray(); if (!vao) throw new Error("xy: graph VAO allocation failed");
        vaos.push(vao); gl.bindVertexArray(vao);
        gl.vertexAttribI4ui(10, 0, 0, 0, 0); gl.vertexAttribI4ui(11, 0, 0, 0, 0);
        function attribute(slot: number, data: Uint8Array, type: number = gl.FLOAT) {
          const buffer = gl.createBuffer(); if (!buffer) throw new Error("xy: graph buffer allocation failed");
          buffers.push(buffer); gl.bindBuffer(gl.ARRAY_BUFFER, buffer); gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
          gl.enableVertexAttribArray(slot); gl.vertexAttribDivisor(slot, 1);
          if (type === gl.FLOAT) gl.vertexAttribPointer(slot, 1, type, false, 0, 0);
          else gl.vertexAttribIPointer(slot, 1, type, 0, 0);
        }
        if (!proceduralNode) for (let i = 0; i < (kind === 3 ? 2 : kind === 2 ? 6 : 4); i++) attribute(i, bytes(`gpu.${column}.coord.bytes`, i));
        if (kind === 0) { attribute(6, bytes("gpu.frame.width.bytes")); attribute(10, bytes("gpu.frame.node.u32"), gl.UNSIGNED_INT); }
        if (kind === 1) { for (let i = 0; i < 4; i++) attribute(6 + i, bytes("gpu.shaft.attr.bytes", i)); attribute(11, bytes("gpu.shaft.flags.u8"), gl.UNSIGNED_BYTE); }
        if (kind === 2) attribute(10, bytes("gpu.head.piece.u32"), gl.UNSIGNED_INT);
        for (const [unit, tex] of [[0, styles[kind === 0 || kind === 3 ? 0 : 1]], [1, states[kind === 0 || kind === 3 ? 0 : 1]], [2, refs]] as const) {
          gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, tex);
        }
        gl.uniform1i(uniform("u_style"), 0); gl.uniform1i(uniform("u_state"), 1); gl.uniform1i(uniform("u_refs"), 2);
        if (proceduralNode) {
          if (!nodeCoords) throw new Error("xy: graph node coordinates unavailable");
          for (let i = 0; i < 2; i++) {
            gl.activeTexture(gl.TEXTURE3 + i); gl.bindTexture(gl.TEXTURE_2D, nodeCoords[i]!);
          }
          gl.uniform1i(uniform("u_coordX"), 3); gl.uniform1i(uniform("u_coordY"), 4);
        }
        gl.uniform1i(uniform("u_kind"), kind); gl.uniform1i(uniform("u_focus"), focusPass);
        if (proceduralNode) gl.drawArrays(gl.TRIANGLES, 0, count * 6);
        else gl.drawArraysInstanced(kind === 2 ? gl.TRIANGLES : gl.TRIANGLE_STRIP, 0, kind === 2 ? 3 : 4, count);
      }
      gl.bindVertexArray(null);
      for (let unit = 0; unit < 5; unit++) { gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, null); }
      gl.activeTexture(gl.TEXTURE0);
      const error = gl.getError(); if (error !== gl.NO_ERROR) throw new Error(`xy: graph GPU paint failed (${error})`);
    }); } catch (error) {
      // WebGL may disappear during allocation/compile, before render's final
      // loss check. Never turn a capacity, protocol or admission refusal into
      // a recovery retry merely because a context was also lost.
      if (error instanceof Error && !(error instanceof RangeError)
          && !(error instanceof XygWasmError) && !(error instanceof GPUAdmissionPending)
          && host.gl.isContextLost()) throw new GraphGpuContextLost();
      throw error;
    }
    if (!completed) {
      if (host.lost || host.gl.isContextLost()) throw new GraphGpuContextLost();
      throw new Error("xy: graph GPU context unavailable");
    }
    // Presentation and accepted restore state change only after a complete pass.
    canvas.width = width; canvas.height = height;
    canvas.style.width = `${camera[4]}px`; canvas.style.height = `${camera[5]}px`;
    present.drawImage(stage, 0, 0);
    accepted = { gpu, camera: camera.slice(), focus };
  }
  return {
    canvas, paint,
    whenContextRestored(signal: AbortSignal): Promise<void> {
      return new Promise((resolve, reject) => {
        const resume = (error?: unknown) => {
          contextWaiters.delete(resume); signal.removeEventListener("abort", abort);
          if (error !== undefined) reject(error); else resolve();
        };
        const abort = () => resume(signal.reason);
        if (disposed) { reject(new XygWasmError("XYG_WASM_DISPOSED", "Graph painter was disposed")); return; }
        if (signal.aborted) { reject(signal.reason); return; }
        contextWaiters.add(resume); signal.addEventListener("abort", abort, { once: true });
        if (host.ready && !host.lost && !host.gl.isContextLost()) resume();
      });
    },
    focusRgba() { if (!accepted) throw new Error("xy: no accepted graph paint"); return accepted.focus.slice(); },
    dispose() {
      if (disposed) return;
      disposed = true; accepted = null; visibility?.disconnect();
      for (const resume of [...contextWaiters]) resume(new XygWasmError("XYG_WASM_DISPOSED", "Graph painter was disposed"));
      releaseObjects();
      if (!host.gl.isContextLost()) for (const value of [program, nodeProgram]) if (value) host.clientContext(client).deleteProgram(value);
      program = null; nodeProgram = null; host.release(client); canvas.remove();
    },
  };
}
