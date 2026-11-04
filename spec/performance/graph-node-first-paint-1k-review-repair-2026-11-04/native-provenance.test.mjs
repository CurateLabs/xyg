// Real native-loader/fixture tests with test-only file variants; no force timing evidence.
import {test,after} from 'node:test';
import assert from 'node:assert/strict';
import {spawn,spawnSync} from 'node:child_process';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,rmSync,existsSync,copyFileSync,cpSync,symlinkSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {attestNative,verifyNative,admitKnownParentCapture,KNOWN_PARENT_SHA} from './native-provenance.mjs';
import {resolvePlatformPackageName} from '../../../packages/xy-node/src/native-path.js';
const root=new URL('../../../',import.meta.url),directory=mkdtempSync(join(tmpdir(),'xyg-native-evidence-'));
const source=new URL('target/release/libxyg_core.so',root).pathname;
const hash=b=>createHash('sha256').update(b).digest('hex');
const bytes=readFileSync(source);assert.equal(hash(bytes),KNOWN_PARENT_SHA);
const variant=join(directory,'selected-libxyg_core.so');
const marker=Buffer.from('\nTEST-ONLY PROVENANCE TRAILER; no executable/force code changed\n');
writeFileSync(variant,Buffer.concat([bytes,marker]));
const observed=[];
async function fixture(env={}){
 const child=spawn(process.execPath,['--import',new URL('worker-audit.mjs',import.meta.url).pathname,new URL('fixture.mjs',import.meta.url).pathname],{cwd:root,env:{...process.env,XYG_NATIVE_LIB:variant,XYG_NODE_NATIVE_ORIGIN_RECORD:'',...env},stdio:['ignore','pipe','pipe']});
 let stdout='',stderr='',timer;
 child.stdout.on('data',b=>stdout+=b);child.stderr.on('data',b=>stderr+=b);
 const closed=new Promise(resolve=>child.once('close',code=>resolve(code)));
 try{
  const url=await new Promise((resolve,reject)=>{
   timer=setTimeout(()=>reject(Error('test fixture startup timeout')),15000);
   const inspect=()=>{const hit=stdout.match(/XYG_GRAPHFORGE_LIVE_URL=(\S+)/);if(hit){clearTimeout(timer);resolve(hit[1]);}};
   child.stdout.on('data',inspect);inspect();child.once('exit',()=>{clearTimeout(timer);resolve(null);});
  });
  if(!url)return {exit:await closed,stdout,stderr};
  const data=await(await fetch(url+'/evidence')).json();
  const independentlyBound=verifyNative(data.selectedNative);
  return {selectedNative:data.selectedNative,independentlyBound};
 }finally{clearTimeout(timer);if(child.exitCode===null)child.kill('SIGTERM');await closed;}
}
after(()=>{
 const output=process.env.XYG_NATIVE_CASE_OUTPUT;
 if(output){assert.equal(existsSync(output),false);writeFileSync(output,JSON.stringify({scope:'Test-only loader/provenance cases; no force callbacks, browser paint or cadence. Variant is exact known parent bytes plus the retained UTF-8 marker.',knownParentSha256:KNOWN_PARENT_SHA,variantSha256:hash(readFileSync(variant)),variantRecipe:{sourceSha256:KNOWN_PARENT_SHA,trailerUtf8:marker.toString()},cases:observed},null,2)+'\n');}
 rmSync(directory,{recursive:true,force:true});
});
test('actual override-selected fixture file differs from conventional target; default origin is unknown',async()=>{
 const result=await fixture();assert.ok(result.selectedNative,JSON.stringify(result));
 const native=result.selectedNative;
 assert.equal(native.resolvedSelectedPath,variant);assert.notEqual(native.sha256,hash(readFileSync(source)));
 assert.equal(native.origin.declaredKind,'unknown');assert.equal(native.matchesKnownParentArtifact,false);
 assert.throws(()=>admitKnownParentCapture(native),/not admitted for this bounded repair/);
 assert.equal(native.abi,399);assert.equal(result.independentlyBound.independentFileHashAndAbiBinding,true);
 assert.throws(()=>verifyNative({...native,sha256:hash(readFileSync(source))}),/independently read bytes/);
 observed.push({case:'actual-override-vs-target',...result,conventionalTarget:{path:source,sha256:hash(readFileSync(source))}});
});
test('actual exact-platform package wins over a different override without changing production resolver',async()=>{
 // Existing checkout has a platform-package symlink. Never mutate it: use an
 // isolated exact copy of host sources and the normal default package resolver.
 const sandbox=join(directory,'isolated-host');mkdirSync(join(sandbox,'node_modules'),{recursive:true});
 cpSync(new URL('packages/xy-node/src/',root),join(sandbox,'src'),{recursive:true});
 copyFileSync(new URL('packages/xy-node/package.json',root),join(sandbox,'package.json'));
 symlinkSync(new URL('packages/xy-node/node_modules/koffi/',root).pathname,join(sandbox,'node_modules','koffi'),'dir');
 const packageDir=join(sandbox,'node_modules',resolvePlatformPackageName());mkdirSync(packageDir,{recursive:true});
 writeFileSync(join(packageDir,'package.json'),JSON.stringify({name:resolvePlatformPackageName(),version:'0.0.0-test-only'}));
 copyFileSync(variant,join(packageDir,'libxyg_core.so'));
 const probe=join(sandbox,'probe.mjs');
 writeFileSync(probe,`import {nativeLibraryPath} from './src/native.js';
import {abiVersion} from './src/abi.js';
import {attestNative} from ${JSON.stringify(new URL('native-provenance.mjs',import.meta.url).href)};
console.log(JSON.stringify(attestNative(nativeLibraryPath,abiVersion())));`);
 const child=spawnSync(process.execPath,[probe],{env:{...process.env,XYG_NATIVE_LIB:source,XYG_NODE_NATIVE_ORIGIN_RECORD:''},encoding:'utf8',timeout:15000});
 assert.equal(child.status,0,child.stderr);
 const native=JSON.parse(child.stdout);verifyNative(native);
 assert.equal(native.resolvedSelectedPath,join(packageDir,'libxyg_core.so'));
 assert.equal(native.sha256,hash(readFileSync(variant)));assert.equal(native.matchesKnownParentArtifact,false);
 assert.equal(native.origin.declaredKind,'unknown');
 const identityPaths=['native.js','native-path.js','_abi_generated.js','abi.js'];
 const copiedSourceHashes=Object.fromEntries(identityPaths.map(name=>{
  const actual=hash(readFileSync(join(sandbox,'src',name)));assert.equal(actual,hash(readFileSync(new URL('packages/xy-node/src/'+name,root))));return[name,actual];
 }));
 observed.push({case:'actual-platform-over-override-in-isolated-unmodified-host',native,copiedSourceHashes,
  isolation:'Original installed platform symlink remains untouched. Default production resolver runs against copied host sources in an isolated temporary package; not a browser/force receipt.',override:{path:source,sha256:hash(readFileSync(source))}});

});
test('declared reuse of known parent fails closed when actual selected identity differs',async()=>{
 const record=join(directory,'bad-reuse.json');writeFileSync(record,JSON.stringify({kind:'reuse',selectedPath:variant,expectedSha256:KNOWN_PARENT_SHA}));
 const result=await fixture({XYG_NODE_NATIVE_ORIGIN_RECORD:record});
 assert.equal(result.exit,1);assert.match(result.stderr,/declared origin expected identity differs/);
 observed.push({case:'declared-reuse-mismatch-rejected',...result});
});
test('matching known-parent bytes never silently infer reuse or pre-run rebuild history',()=>{
 const record=attestNative(source,399,{originRecord:null});assert.equal(record.matchesKnownParentArtifact,true);assert.equal(record.origin.declaredKind,'unknown');admitKnownParentCapture(record);
 observed.push({case:'known-bytes-origin-unknown',native:record});
});
test('explicit reuse/copy/rebuild declarations remain declarations; rebuilt requires an inspectable record',()=>{
 const expectedSha256=hash(readFileSync(variant)),originFile=join(directory,'origin.json');
 for(const kind of ['reuse','copied','rebuilt']){
  const declaration={kind,selectedPath:variant,expectedSha256};
  if(kind==='copied'){declaration.sourcePath=join(directory,'copy-source.so');copyFileSync(variant,declaration.sourcePath);}
  if(kind==='rebuilt'){
   writeFileSync(originFile,JSON.stringify(declaration));assert.throws(()=>attestNative(variant,399,{originRecord:originFile}),/build record/);
   declaration.buildRecord=join(directory,'test-only-build-record.txt');
   writeFileSync(declaration.buildRecord,'TEST-ONLY SCRIPTED PROVENANCE RECORD. No build was executed by this test.\n');
  }
  writeFileSync(originFile,JSON.stringify(declaration));
  const record=attestNative(variant,399,{originRecord:originFile});assert.equal(record.origin.declaredKind,kind);verifyNative(record);
  observed.push({case:'scripted-origin-declaration-'+kind,native:record});
 }
 const actual=attestNative(variant,399,{originRecord:null});assert.throws(()=>verifyNative({...actual,abi:398}),/fixture ABI/);
});
