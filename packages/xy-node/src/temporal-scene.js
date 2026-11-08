/** Native temporal composition framing. All product policy lives in Rust. */
import {xyTemporalSceneCompile,pointer} from './native.js';
import {encodeTemporalScene} from './temporal-scene-framing.js';
export {encodeTemporalScene} from './temporal-scene-framing.js';
export function temporalSceneCompile(input,budget=64*1024*1024){
 const packet=new Uint8Array(input instanceof ArrayBuffer?input:encodeTemporalScene(input));
 if(!Number.isSafeInteger(budget)||budget<65536||budget>64*1024*1024||packet.length>budget)throw new RangeError('invalid temporal resource budget');
 const size=new BigUint64Array(1);
 let code=xyTemporalSceneCompile(pointer(packet,'uint8_t *'),BigInt(packet.length),BigInt(budget),null,0n,pointer(size,'size_t *'));
 if(code)throw new Error(`temporal Scene rejected (${code})`);
 const out=new Uint8Array(Number(size[0]));
 code=xyTemporalSceneCompile(pointer(packet,'uint8_t *'),BigInt(packet.length),BigInt(budget),pointer(out,'uint8_t *'),BigInt(out.length),pointer(size,'size_t *'));
 if(code)throw new Error(`temporal Scene rejected (${code})`);return out;
}

/** Public native incremental operation. Rust owns progress, source claims and commit. */
export class TemporalSession {
 constructor(budget=64*1024*1024){this.budget=budget;this.owner=0n;this.revision=0n;this.owner=new DataView(this.command(0,0n).buffer).getBigUint64(16,true);}
 command(op,revision,source){
  if(op&&!this.owner)throw new Error('temporal session disposed');
  const packet=new ArrayBuffer(64+(source?.byteLength??0)),v=new DataView(packet);
  new Uint8Array(packet).set([88,89,84,74]);v.setUint32(4,1,true);v.setUint32(8,op,true);v.setBigUint64(16,op===6?0n:this.owner,true);v.setBigUint64(24,revision,true);
  if(source)new Uint8Array(packet,64).set(new Uint8Array(source));return temporalSceneCompile(packet,this.budget);
 }
 preview(source){const v=new DataView(source);return this.command(6,0n,source.slice(0,128+v.getUint32(56,true)+v.getUint32(60,true)));}
 begin(source){this.preview(source);if(this.revision===(1n<<64n)-1n)throw new RangeError('temporal revision exhausted');const revision=++this.revision;this.command(1,revision,source);let ready=false;const operation={
  revision,step:()=>{const ack=this.command(2,revision);ready=new DataView(ack.buffer).getUint32(8,true)===1;return ack;},
  result:()=>{while(!ready)operation.step();return this.command(3,revision);},
  resultAsync:async({signal}={})=>{const stop=()=>{try{operation.cancel();}catch{}};signal?.addEventListener('abort',stop);try{while(!ready){if(signal?.aborted)throw new Error('temporal waiter cancelled');operation.step();await new Promise(resolve=>setTimeout(resolve,0));}if(signal?.aborted)throw new Error('temporal waiter cancelled');return this.command(3,revision);}catch(e){stop();throw e;}finally{signal?.removeEventListener('abort',stop);}},
  cancel:()=>this.command(4,revision),close:()=>this.command(4,revision)
 };return operation;}

 cancel(){if(this.owner&&this.revision)this.command(4,this.revision);}
 accepted(revision){return this.command(3,revision);}
 close(){if(this.owner){try{this.command(5,this.revision);}finally{this.owner=0n;}}}
}
