// Test-only bundle keeps the genuine Worker and its private capture in one module instance.
import {createXygWasmWorker,getGeoWorkerSnapshotTransport,beginGeoWorkerMutationCapture,withGeoWorkerMutationOutcome} from '../../js/src/47_wasm';
export function captureWorker(){return createXygWasmWorker({wasm:'/packages/xy-client/dist/xyg-wasm.wasm',workerUrl:'/packages/xy-client/dist/wasm-worker.js',maxArenaBytes:128<<20});}
function request(command:number,handle:bigint,sequence=0n,nonce=0n){const b=new ArrayBuffer(256),v=new DataView(b);new Uint8Array(b).set([88,89,71,74]);v.setUint32(4,1,true);v.setUint32(8,command,true);v.setBigUint64(16,handle,true);v.setBigUint64(24,sequence,true);if(command===6)v.setBigUint64(32,128n<<20n,true);v.setBigUint64(240,nonce,true);return b;}
function check(value:unknown,message:string):asserts value {if(!value)throw new Error(message);}
export async function verifyScopedSnapshotOutcomes(worker:ReturnType<typeof captureWorker>,handle:bigint,sequence:bigint){
 const bridge=getGeoWorkerSnapshotTransport(worker,worker.geoScaleBridge()).bridge,held:bigint[]=[];
 for(let i=0;i<8;i++){const reply=await bridge.execute(request(6,handle,sequence));held.push(new DataView(reply).getBigUint64(16,true));}
 const canonical=request(6,handle,sequence,1n);let oldError:unknown;
 const scopes=Array.from({length:16},()=>beginGeoWorkerMutationCapture(bridge,canonical));let limit=false;try{beginGeoWorkerMutationCapture(bridge,canonical);}catch{limit=true;}check(limit,'seventeenth capture admitted');for(const scope of scopes)scope.close();
 await withGeoWorkerMutationOutcome(bridge,canonical,async outcome=>{
  let packet:ArrayBuffer|undefined,threw=false;
  const wrapper=async()=>{try{await bridge.execute(canonical.slice(0));}catch(error){oldError=error;}check(oldError&&outcome(oldError)?.code==='XYG_GEO_RESOURCE_LIMIT','genuine current rejection unrecognized');await bridge.execute(request(3,held.pop()!));packet=await bridge.execute(canonical.slice(0));check(new DataView(packet).getBigUint64(16,true)>0n,'exact clone did not allocate');throw oldError;};
  try{await wrapper();}catch(error){threw=true;check(error===oldError&&!outcome(error),'same-call old genuine error authorized nonadmission');}
  check(threw&&packet,'wrapper did not throw earlier rejection after successful clone');check(outcome(packet)?.reply===packet,'validation allocated or lost original reply');
 });
 await withGeoWorkerMutationOutcome(bridge,canonical,async outcome=>{const replay=await bridge.execute(canonical.slice(0));check(!outcome(oldError),'previous-call genuine error authorized nonadmission');check(outcome(replay)?.reply===replay,'exact replay lacks current authority');const target=new DataView(replay).getBigUint64(16,true),confirm=request(7,handle,sequence,1n);new DataView(confirm).setBigUint64(40,target,true);await bridge.execute(confirm.slice(0));await bridge.execute(request(3,target));const retired=await bridge.execute(confirm.slice(0));check(new DataView(retired).getUint32(8,true)===2,'target retirement missing');const release=request(7,handle,sequence,1n);new DataView(release).setUint32(48,2,true);await bridge.execute(release);});
 for(const target of held)await bridge.execute(request(3,target));
 const final=beginGeoWorkerMutationCapture(bridge,canonical);final.close();check(!final.outcome(oldError),'closed capture retained authority');
 return {sameCallClone:true,previousCallError:true,originalReplyToken:true,capacity16:true,closedScopeDropsAuthority:true};
}
