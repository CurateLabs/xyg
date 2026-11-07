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
