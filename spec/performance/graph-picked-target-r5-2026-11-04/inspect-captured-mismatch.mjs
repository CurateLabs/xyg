// Read-only diagnosis of the failed existing replay; no expected bytes changed.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {gunzipSync,gzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import * as native from '../../../packages/xy-node/src/native.js';
import {decodeContainer} from '../../../packages/xy-node/src/graphforge-container.js';
import {ptr,nativeComplete} from '../../../packages/xy-node/test/graph-session-replay-helpers.mjs';
const capture='spec/performance/graph-s5b-pointer-native-input-repair-2026-11-04/captured-requests.json.gz';
const records=JSON.parse(gunzipSync(fs.readFileSync(capture)));
const sha=b=>createHash('sha256').update(b).digest('hex');
const json=v=>JSON.stringify(v,(_,x)=>typeof x==='bigint'?x.toString()+'n':x);
const handle=new BigUint64Array(1),results=[],full=[];let opened=false;
try{for(const [i,r] of records.entries()){
 const request=Uint8Array.from(Buffer.from(r.request,'base64')),expectedBuffer=Buffer.from(r.reply,'base64'),expected=Uint8Array.from(expectedBuffer);
 const q=decodeContainer(request,'XYGI'),h=q.get('header.u64#0').value,op=r.operation;
 if(op===19){const d=q.get('document.bytes#0').value;assert.equal(native.xyGraphforgeSessionCreate(ptr(d),BigInt(d.length),ptr(request),BigInt(request.length),h[0],h[1],native.pointer(handle,'uint64_t *')),0);opened=true;continue;}
 const actual=nativeComplete(op===21?native.xyGraphforgeSessionRender:native.xyGraphforgeSessionInteract,handle[0],request);
 const a=decodeContainer(actual,'XYGR'),b=decodeContainer(expected,'XYGR');
 const added=[...a.keys()].filter(k=>!b.has(k)),removed=[...b.keys()].filter(k=>!a.has(k)),changed=[...b.keys()].filter(k=>a.has(k)&&json(a.get(k))!==json(b.get(k)));
 let bufferError=null;try{decodeContainer(expectedBuffer,'XYGR');}catch(e){bufferError=e.toString();}
 const exact=Buffer.from(actual).equals(Buffer.from(expected));
 results.push({index:i,operation:op,exact,actualBytes:actual.length,expectedBytes:expected.length,actualSha256:sha(actual),expectedSha256:sha(expected),added,removed,changed,expectedBufferDecodeError:bufferError});
 full.push({index:i,request:r.request,expected:r.reply,actual:Buffer.from(actual).toString('base64')});
}}
finally{if(opened)assert.equal(native.xyGraphforgeSessionDestroy(handle[0]),0);}
const p='spec/performance/graph-picked-target-r5-2026-11-04/';
fs.writeFileSync(p+'captured-mismatch.json',JSON.stringify({capture,captureSha256:sha(fs.readFileSync(capture)),classification:'READ_ONLY_FAILURE_DIAGNOSIS_NOT_A_REPLACEMENT_TEST',results},null,2)+'\n',{flag:'wx'});
fs.writeFileSync(p+'captured-actual-replies.json.gz',gzipSync(JSON.stringify(full),{level:6}),{flag:'wx'});
console.log(JSON.stringify(results,null,2));
