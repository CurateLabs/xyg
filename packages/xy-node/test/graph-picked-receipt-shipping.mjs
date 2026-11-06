// Fresh normal shipping-module actual C/WASM full-byte receipt replay.
// The R4 diagnostic runner remains separate; all replay/capacity guards are identical.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { gzipSync } from "node:zlib";
import test from "node:test";
import { fileURLToPath } from "node:url";
import * as native from "../src/native.js";
import { decodeContainer } from "../src/graphforge-container.js";
import { ptr, equalBytes, nativeCall, nativeComplete, wasmCall } from "./graph-session-replay-helpers.mjs";
const sha = b => createHash("sha256").update(b).digest("hex");
const required = key => { assert.ok(process.env[key], `${key} must explicitly select replay evidence`); return path.resolve(process.env[key]); };
assert.equal(process.env.XYG_SESSION_WASM, undefined, "shipping replay forbids diagnostic module override");
const modulePath = fileURLToPath(new URL("../../xy-client/dist/xyg-wasm.wasm", import.meta.url));
const corpusPath = required("XYG_PICK_CORPUS"), reportPath = required("XYG_PICK_REPORT");
const moduleBytes = fs.readFileSync(modulePath), corpus = fs.readFileSync(corpusPath), nativeBytes = fs.readFileSync(native.nativeLibraryPath);
const manifest = JSON.parse(fs.readFileSync(new URL("../../xy-client/dist/xyg-wasm.manifest.json", import.meta.url), "utf8"));
assert.equal(sha(moduleBytes), "e3ef33b58820675f4c201a2b81ad23b3665090442210aa22fcee28a269884a96", "fresh R2 shipping module identity");
assert.equal(sha(nativeBytes), "0deea9029e4a328dc15aa2d86873a203f12b8911e1c89c274f14270b31a3f880", "exact R2 native product identity");
assert.equal(manifest.bytes, moduleBytes.length);
assert.equal(manifest.sha256, sha(moduleBytes));
assert.ok(moduleBytes.length <= 1882 * 1024);
assert.ok(gzipSync(moduleBytes, {level: 6}).length <= 768 * 1024);
const view = new DataView(corpus.buffer, corpus.byteOffset, corpus.byteLength); let at = 4;
const u32 = () => {const n=view.getUint32(at,true);at+=4;return n;};
const bytes = () => {const n=Number(view.getBigUint64(at,true));at+=8;assert.ok(n<=corpus.length-at);const b=Uint8Array.from(corpus.subarray(at,at+n));at+=n;return b;};
const format=corpus.subarray(0,4).toString();assert.ok(["XYQP","XYQ2"].includes(format));
const cases = Array.from({length:u32()},()=>{const n=u32(),name=corpus.subarray(at,at+n).toString();at+=n;const budget=format==="XYQ2"?u32():16*1024*1024;assert.ok([16*1024*1024,384*1024*1024].includes(budget));const steps=Array.from({length:u32()},()=>{const request=bytes(),status=view.getInt32(at,true);at+=4;const expected=bytes();return {request,status,expected};});return {name,budget,steps};});
assert.equal(at,corpus.length);assert.ok(cases.length>=7);
const evidence={qualification:"FRESH_SHIPPING_MODULE_RECEIPT_BYTE_PARITY",integrationAccepted:false,node:process.version,modulePath,moduleSha256:sha(moduleBytes),nativePath:native.nativeLibraryPath,nativeSha256:sha(nativeBytes),corpusPath,corpusSha256:sha(corpus),cases:[]};
for (const scenario of cases) test(`shipping R2 full native/WASM receipt bytes: ${scenario.name}`,async()=>{
  const {instance}=await WebAssembly.instantiate(moduleBytes,{}),x=instance.exports;
  const wasm=x.xyg_wasm_instance_new(scenario.budget);assert.ok(wasm>0);
  const handle=new BigUint64Array(1);let opened=false,last=null;const results=[];
  try {
    for(const [index,step] of scenario.steps.entries()){
      const c=decodeContainer(step.request,"XYGI"),h=c.get("header.u64#0").value,w=c.get("header.u32#0").value,op=w[1];
      if(op===19){const document=c.get("document.bytes#0").value;assert.equal(native.xyGraphforgeSessionCreate(ptr(document),BigInt(document.length),ptr(step.request),BigInt(step.request.length),h[0],h[1],native.pointer(handle,"uint64_t *")),0);opened=true;}
      const fn=op===21?native.xyGraphforgeSessionRender:native.xyGraphforgeSessionInteract;
      const name=op===19?"xyg_wasm_graphforge_session_open":op===21?"xyg_wasm_graphforge_session_render":"xyg_wasm_graphforge_session_interact";
      const result=wasmCall(x,wasm,name,step.request);assert.equal(result.status,step.status,`step ${index}`);
      let actualNative=null;
      if(step.status===0){
        if(op!==19){actualNative=nativeComplete(fn,handle[0],step.request);equalBytes(actualNative,step.expected,`${scenario.name} ${index} complete native/engine`);equalBytes(result.output,actualNative,`${scenario.name} ${index} complete WASM/native`);}
        equalBytes(result.output,step.expected,`${scenario.name} ${index} complete WASM/engine`);
        const retry=wasmCall(x,wasm,name,step.request);assert.equal(retry.status,0);equalBytes(retry.output,result.output,"full WASM retry");
        if(op!==19)last={request:step.request,fn,reply:step.expected};
      }else{
        const refused=nativeCall(fn,handle[0],step.request,0);assert.equal(refused.status,step.status);assert.equal(refused.length,0);
        assert.ok(last);equalBytes(nativeComplete(last.fn,handle[0],last.request),last.reply,"native refusal preserved retained reply");
        assert.equal(result.output.length,0,"arena resize discards observable instance output before a new request");
        const recovered=wasmCall(x,wasm,last.fn===native.xyGraphforgeSessionRender?"xyg_wasm_graphforge_session_render":"xyg_wasm_graphforge_session_interact",last.request);
        assert.equal(recovered.status,0);equalBytes(recovered.output,last.reply,"WASM refusal preserved retained session retry bytes");
      }
      results.push({index,operation:op,status:step.status,requestBytes:step.request.length,requestSha256:sha(step.request),replyBytes:result.output.length,wasmReplySha256:sha(result.output),nativeReplySha256:actualNative?sha(actualNative):null});
    }
  }finally{if(opened){assert.equal(native.xyGraphforgeSessionDestroy(handle[0]),0);assert.equal(x.xyg_wasm_graphforge_session_close(wasm),0);}assert.equal(x.xyg_wasm_instance_dispose(wasm),0);}
  evidence.cases.push({name:scenario.name,budget:scenario.budget,steps:results});
});
// beforeExit runs after the test runner has completed all registered cases.
process.on("beforeExit",()=>{
  if(evidence.cases.length!==cases.length)return;
  evidence.cases.sort((a,b)=>a.name.localeCompare(b.name));
  if(!fs.existsSync(reportPath))fs.writeFileSync(reportPath,JSON.stringify(evidence,null,2)+"\n",{flag:"wx"});
  const archive=reportPath+".corpus.gz";if(!fs.existsSync(archive))fs.writeFileSync(archive,gzipSync(corpus,{level:6}),{flag:"wx"});
});
