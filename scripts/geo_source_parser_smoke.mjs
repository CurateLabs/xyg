#!/usr/bin/env node
// Independent source63 framing checks against a real native SceneData receipt.
// The existing cross-host fixture normalizes its process-local owner handle;
// geometry, time, provenance, literal IDs and all tested fields are untouched.
import {spawnSync} from 'node:child_process';
import {build} from 'vite';
import {fileURLToPath} from 'node:url';

const root=fileURLToPath(new URL('../',import.meta.url));
const native=spawnSync('uv',['run','python','-c',
  'import asyncio,runpy; f=runpy.run_path("tests/test_geoscale.py"); print(asyncio.run(f["native_fixture"]())["packet"])'],
  {cwd:root,encoding:'utf8'});
if(native.status!==0)throw Error(native.stderr||native.stdout||'native fixture failed');
const raw=Buffer.from(native.stdout.trim(),'hex'),packet=raw.buffer.slice(raw.byteOffset,raw.byteOffset+raw.byteLength);
// Bundle the canonical parser and its real static imports for this private probe.
const bundled=await build({configFile:false,logLevel:'error',build:{write:false,minify:true,rollupOptions:{preserveEntrySignatures:'strict',input:fileURLToPath(new URL('../js/src/63_geo_source.ts',import.meta.url)),output:{format:'es'}}}});
const source=bundled.output.find(item=>item.type==='chunk').code;
const {parseGeoSceneData}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const baseline=parseGeoSceneData(packet);
if(baseline.length!==2||baseline.record(0).featureId!==0xffffffffffffffffn||baseline.record(1).featureId!==0x20000000000001n||baseline.identity.time.instant!==-0x8000000000000000n)throw Error('actual native literal ID/time baseline failed');
const at=256+Number(new DataView(packet).getBigUint64(32,true));
const controls=[
  ['magic',(v,b)=>b[0]^=1],['version',v=>v.setUint32(4,99,true)],
  ['reserved tail',(v,b)=>b[255]=1],['oversized Scene length',v=>v.setBigUint64(32,0xffffffffffffffffn,true)],
  ['aggregate tag',v=>v.setUint32(8,4,true)],['unknown channel mask',v=>v.setUint32(12,8,true)],
  ['source geometry',v=>v.setUint32(240,99,true)],['source CRS',v=>v.setUint32(244,99,true)],
  ['camera CRS',v=>v.setUint32(80,99,true)],['wrap tag',v=>v.setUint32(84,2,true)],
  ['nonfinite camera',v=>v.setFloat64(88,NaN,true)],['time tag',v=>v.setUint32(208,99,true)],
  ['reversed window',v=>{v.setUint32(208,2,true);v.setBigInt64(216,1n,true);v.setBigInt64(224,0n,true);}],
  ['Scene version',v=>v.setUint32(260,99,true)],['provenance reserved',v=>v.setUint32(at+28,1,true)],
  ['source ordinal',v=>v.setBigUint64(at+8,v.getBigUint64(232,true),true)],
  ['chunk index',v=>v.setUint32(at+16,65536,true)],['chunk row',v=>v.setUint32(at+20,65536,true)],
  ['vertex framing',v=>v.setUint32(at+24,0xffffffff,true)],
];
const accepted=[];
for(const[label,mutate]of controls){const copy=packet.slice();mutate(new DataView(copy),new Uint8Array(copy));try{parseGeoSceneData(copy);accepted.push(label);}catch{/* Required malformed-input rejection. */}}
try{parseGeoSceneData(packet.slice(0,-1));accepted.push('truncation');}catch{/* Required framing rejection. */}
if(accepted.length)throw Error(`source63 accepted malformed actual native receipts: ${accepted.join(', ')}`);
console.log(`geographic source parser smoke: actual native SceneData, exact u64/i64, ${controls.length+1} malformed controls rejected`);
