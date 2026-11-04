// Evidence-only observations of the existing loader's selected, ABI-bound file.
// Hash identity never establishes whether somebody rebuilt a file before this run.
import assert from 'node:assert/strict';
import { readFileSync,realpathSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { ABI_VERSION,bindAbiVersion } from '../../../packages/xy-node/src/_abi_generated.js';
export const KNOWN_PARENT_SHA='3a9b78c81a078e13a78779add5a0e8ad5949d0483a828f483c060840e1e495c6';
const hash=b=>createHash('sha256').update(b).digest('hex');
export function attestNative(selectedPath,abi,{originRecord=process.env.XYG_NODE_NATIVE_ORIGIN_RECORD}={}){
 const resolvedSelectedPath=realpathSync(selectedPath),bytes=readFileSync(resolvedSelectedPath),sha256=hash(bytes);
 let origin={declaredKind:'unknown',meaning:'No origin declaration; byte identity alone proves neither reuse nor rebuild history.'};
 if(originRecord){
  const declaration=JSON.parse(readFileSync(originRecord));
  assert.ok(['reuse','copied','rebuilt'].includes(declaration.kind),'unsupported origin declaration');
  assert.equal(declaration.expectedSha256,sha256,'declared origin expected identity differs from actual loaded file');
  assert.equal(realpathSync(declaration.selectedPath),resolvedSelectedPath,'origin declaration must identify actual selected file');
  origin={declaredKind:declaration.kind,declaration,recordPath:realpathSync(originRecord),recordSha256:hash(readFileSync(originRecord)),meaning:'Explicit operator declaration; byte/record identity checked, operation history not independently inferred.'};
  if(declaration.kind==='rebuilt'){
   assert.ok(declaration.buildRecord,'declared rebuild requires a build record');
   origin.buildRecord={path:realpathSync(declaration.buildRecord),sha256:hash(readFileSync(declaration.buildRecord))};
  }
  if(declaration.kind==='copied'){
   assert.ok(declaration.sourcePath,'declared copy requires its source');
   assert.notEqual(realpathSync(declaration.sourcePath),resolvedSelectedPath,'copy source must be a distinct file path');
   assert.equal(hash(readFileSync(declaration.sourcePath)),sha256,'copy source bytes differ');
  }
 }
 return {selectedPath,resolvedSelectedPath,sha256,bytes:bytes.length,abi,matchesKnownParentArtifact:sha256===KNOWN_PARENT_SHA,origin};
}
export function verifyNative(record){
 assert.equal(realpathSync(record.selectedPath),record.resolvedSelectedPath);
 const bytes=readFileSync(record.resolvedSelectedPath);
 assert.equal(hash(bytes),record.sha256,'fixture-selected file must match independently read bytes');assert.equal(bytes.length,record.bytes);
 const requireHost=createRequire(new URL('../../../packages/xy-node/package.json',import.meta.url));
 const koffi=requireHost('koffi'),library=koffi.load(record.resolvedSelectedPath);
 let actualAbi;try{actualAbi=bindAbiVersion(library)();}finally{library.unload();}
 assert.equal(actualAbi,ABI_VERSION);assert.equal(actualAbi,record.abi,'fixture ABI must match independently bound selected file');
 assert.equal(record.matchesKnownParentArtifact,record.sha256===KNOWN_PARENT_SHA);
 const reproduced=attestNative(record.selectedPath,actualAbi,{originRecord:record.origin.recordPath??null});
 assert.deepEqual(reproduced,record,'origin declaration must reproduce from the same file/record');
 return {selectedPath:record.selectedPath,resolvedSelectedPath:record.resolvedSelectedPath,sha256:record.sha256,abi:actualAbi,independentFileHashAndAbiBinding:true};
}
export function verifyNativeRecords(logs,fixture,expectedJobIds=[]){
 const records=logs.split('\n').filter(l=>l.startsWith('{"audit":"NATIVE"')).map(l=>JSON.parse(l));
 for(const r of records){verifyNative(r.native);assert.equal(r.native.resolvedSelectedPath,fixture.resolvedSelectedPath);assert.equal(r.native.sha256,fixture.sha256);assert.equal(r.native.abi,fixture.abi);}
 for(const role of ['fixture-main','bridge-worker','force-worker'])assert.ok(records.some(r=>r.role===role),'missing direct native observation for '+role);
 for(const jobId of expectedJobIds)for(const role of ['bridge-worker','force-worker'])assert.ok(records.some(r=>r.jobId===jobId&&r.role===role),'missing direct native observation for '+role+' job '+jobId);
 return {expectedJobIds,scope:'Read-only --import observation in fixture and inherited real bridge/force Workers before their entry module executes; file bytes observed at attestation and independently rechecked, not a mapped-memory hash or proof against arbitrary concurrent replacement.',records};
}

export function admitKnownParentCapture(record){
 const binding=verifyNative(record);
 assert.equal(record.sha256,KNOWN_PARENT_SHA,'selected native bytes are not admitted for this bounded repair; no force capture with an alternate or checkpoint artifact');
 return binding;
}
