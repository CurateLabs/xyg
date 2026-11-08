/** Repository-only HTTP consumer of the public native chunked lifecycle and XYBF. */
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {join, resolve, sep} from 'node:path';
import {ChunkedColumns} from '../../packages/xy-node/src/index.js';

export function frame(message, buffers = [], bound = 8 << 20) {
  const metadata = Buffer.from(JSON.stringify(message));
  const align = n => Math.ceil(n / 8) * 8;
  let length = align(24 + metadata.length);
  for (const b of buffers) length = align(length + 8 + b.byteLength);
  if (length > bound) throw new RangeError('application serialization bound exceeded');
  const out = Buffer.alloc(length); out.write('XYBF'); out[4] = 1; out.writeUInt16LE(24, 6);
  out.writeUInt32LE(metadata.length, 8); out.writeUInt32LE(buffers.length, 12); out.writeBigUInt64LE(BigInt(length), 16); metadata.copy(out, 24);
  let offset = align(24 + metadata.length);
  for (const b of buffers) {out.writeBigUInt64LE(BigInt(b.byteLength), offset); offset += 8; Buffer.from(b.buffer, b.byteOffset, b.byteLength).copy(out, offset); offset = align(offset + b.byteLength);}
  return out;
}

export async function createChunkedNativeApp({path, assets, callbacks = {}, staticDirectory}) {
  const source = new ChunkedColumns(path);
  const chart = source.chart(null, {budgetBytes: 65536, pageBytes: 16384});
  const lanes = [0, 1].map(() => ({queue: [], response: null, serializedPeak: 0, queuedPeak: 0}));
  const hosts = lanes.map(lane => chart.liveHost((msg, buffers) => {
    const body = frame(msg, buffers);
    lane.serializedPeak = Math.max(lane.serializedPeak, body.byteLength);
    if (lane.response) {lane.response.end(body); lane.response = null;}
    else {
      if (lane.queue.length >= 16) throw new Error('application reply queue is full');
      lane.queue.push(body); lane.queuedPeak = Math.max(lane.queuedPeak, lane.queue.length);
    }
  }, callbacks));
  source.close(); // mounted readers are independent of caller ownership
  const server = createServer(async (request, response) => {
    try {
      const url = new URL(request.url, 'http://localhost');
      const laneId = Number(url.searchParams.get('chart') ?? 0);
      if (!Number.isInteger(laneId) || laneId < 0 || laneId > 1) {response.writeHead(400).end(); return;}
      const lane = lanes[laneId], host = hosts[laneId];
      if (url.pathname === '/initial') {
        const {spec, buffers} = host.payload(); response.setHeader('Content-Type', 'application/octet-stream'); response.end(frame({spec}, buffers));
      } else if (url.pathname === '/events') {
        if (lane.response) {response.writeHead(409).end(); return;}
        response.setHeader('Content-Type', 'application/octet-stream');
        if (lane.queue.length) response.end(lane.queue.shift());
        else {lane.response = response; response.on('close', () => {if (lane.response === response) lane.response = null;});}
      } else if (url.pathname === '/control' && request.method === 'POST') {
        let length = 0; const chunks = [];
        for await (const chunk of request) {length += chunk.length; if (length > 65536) throw new RangeError('control exceeds 64 KiB'); chunks.push(chunk);}
        host.message(JSON.parse(Buffer.concat(chunks).toString())); response.end();
      } else if (url.pathname === '/') {
        response.setHeader('Content-Type', 'text/html'); response.end(html);
      } else {
        const directory = url.pathname.startsWith('/assets/') ? assets : staticDirectory;
        if (!directory) {response.writeHead(404).end(); return;}
        const name = url.pathname.startsWith('/assets/') ? url.pathname.slice(8) : url.pathname.slice(1);
        const file = resolve(join(directory, name));
        if (!file.startsWith(resolve(directory) + sep)) {response.writeHead(403).end(); return;}
        response.setHeader('Content-Type', name.endsWith('.js') ? 'text/javascript' : 'application/octet-stream'); response.end(await readFile(file));
      }
    } catch (error) {response.writeHead(400).end(String(error));}
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  return {server, hosts, lanes, origin: `http://127.0.0.1:${server.address().port}`, async close() {
    for (const lane of lanes) {lane.response?.end(); lane.response = null; lane.queue = [];}
    await Promise.all(hosts.map(host => host.close())); server.closeAllConnections(); await new Promise(r => server.close(r));
  }};
}

const html = `<!doctype html><meta charset="utf-8"><title>Local chunked chart</title>
<div id="chart"></div><div id="other"></div><div id="oracle"></div>
<script type="module">
import {render, decodeFrame} from '/assets/index.js';
const models=[];
async function mount(id, element) {
 const initial=decodeFrame(await (await fetch('/initial?chart='+id)).arrayBuffer());
 const listeners=new Map(); let stopped=false, posting=false;const controls=[];
 async function post(){if(posting)return;posting=true;try{while(controls.length){const message=controls.shift();const response=await fetch('/control?chart='+id,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(message)});if(!response.ok)throw Error('native control transport failed');}}finally{posting=false;}}
 const model={get:key=>key==='spec'?initial.message.spec:initial.buffers,
 on:(key,callback)=>{if(!listeners.has(key))listeners.set(key,new Set());listeners.get(key).add(callback)},
 off:(key,callback)=>listeners.get(key)?.delete(callback),
 send:message=>{
   if(message.type==='pick'||message.type==='view_change'){
     const index=controls.findIndex(old=>old.type===message.type&&old.mount===message.mount);
     if(index>=0){controls[index]=message;return;}
   }
   if(controls.length>=16)throw Error('application controls full');
   controls.push(message);void post();}
 };
 const paint=()=>render({model,el:element});let cleanup=paint();
 models.push({model,remount(){const previous=cleanup;cleanup=paint();previous();},close(){cleanup();stopped=true;}});
 while(!stopped){const response=await fetch('/events?chart='+id);if(!response.ok)throw Error('native event transport failed');const data=await response.arrayBuffer();if(!data.byteLength)break;const decoded=decodeFrame(data);for(const callback of listeners.get('msg:custom')||[])callback(decoded.message,decoded.buffers);element.dataset.packets=String(Number(element.dataset.packets||0)+1);}
}
// The ordinary application owns two independent native chart handles.
void mount(0,document.querySelector('#chart'));void mount(1,document.querySelector('#other'));
document.querySelector('#chart').remount=()=>models[0].remount();
</script>`;
