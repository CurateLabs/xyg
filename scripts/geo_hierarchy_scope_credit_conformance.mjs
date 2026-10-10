#!/usr/bin/env node
// Test-only audit wrapper: execute the existing hierarchy goldens, retain complete
// native packets, and validate owner/publication bindings before any comparison.
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const original=new URL('./geo_selected_hierarchy_conformance.mjs',import.meta.url);
let text=await readFile(original,'utf8');
const evidence=[];
globalThis.__scopePacketEvidence=evidence;
const instrument=`
function auditedNativeBridge(){
 const original=nativeGeoScaleBridge(budget.processorBytes),issued=new Map();
 return {async execute(raw){const q=new DataView(raw),cmd=q.getUint32(8,true),out=await original.execute(raw),v=new DataView(out);
  if([11,13,14,16,19,26,44].includes(cmd)&&v.getUint32(8,true)===0)issued.set(v.getBigUint64(16,true),{issuer:q.getBigUint64(16,true),sequence:v.getBigUint64(24,true)});
  return out;},async read(raw){const q=new DataView(raw),out=await original.read(raw);
  if(q.getUint32(8,true)===23){const v=new DataView(out),h=q.getBigUint64(16,true);assert.ok(issued.has(h),'Data must have genuine creation receipt');assert.equal(v.getBigUint64(16,true),issued.get(h).issuer);assert.equal(v.getBigUint64(24,true),issued.get(h).sequence);
   globalThis.__scopePacketEvidence.push({magic:Buffer.from(out,0,4).toString(),bytes:out.byteLength,owner:h.toString(),issuer:issued.get(h).issuer.toString(),publication:issued.get(h).sequence.toString(),base64:Buffer.from(out).toString('base64')});}
  return out;}};
}
`;
assert.equal((text.match(/nativeGeoScaleBridge\(budget\.processorBytes\)/g)??[]).length,2);
text=text.replaceAll('nativeGeoScaleBridge(budget.processorBytes)','auditedNativeBridge()');
text=text.replace('try{const cases=[];',instrument+'\ntry{const cases=[];');
text=text.replaceAll("'../packages/", "'"+pathToFileURL(new URL('../packages/',import.meta.url).pathname).href);
text=text.replaceAll('new URL(import.meta.url)','new URL('+JSON.stringify(original.href)+')');
await import('data:text/javascript;base64,'+Buffer.from(text).toString('base64'));
assert.ok(evidence.length>=12);
if(process.env.XYG_SCOPE_PACKETS)await writeFile(process.env.XYG_SCOPE_PACKETS,JSON.stringify({normalization:'none: full native packets after exact creation owner/sequence validation',packets:evidence},null,2)+'\n');
delete globalThis.__scopePacketEvidence;
