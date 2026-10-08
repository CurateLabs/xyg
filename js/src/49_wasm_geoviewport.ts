import { encodeGeoPlanes, type XygGeoDescriptor } from "./49_wasm_geo";
/** Byte-only adapters for the Rust-owned XYVC/XYVR camera protocol. */
export const XYVC_HEADER_BYTES = 128;
export const XYVR_HEADER_BYTES = 256;
export const GEO_VIEWPORT_OPERATIONS = Object.freeze({normalize:0, project:1, inverse:2, pan:3, zoom:4, resize:5, bearing:6, pitch:7, center:8, fit:9, column:10});
export interface XygGeoCamera {crs:number; centerX:number; centerY:number; zoom:number; width:number; height:number; bearing?:number; pitch?:number; worldWrap?:boolean;}
export function encodeGeoViewportRequest(camera:XygGeoCamera, operation:number=0, args:readonly number[]=[], descriptor?:ArrayBuffer):ArrayBuffer {
  if(camera.worldWrap!==undefined&&typeof camera.worldWrap!=="boolean")throw new TypeError("worldWrap must be a boolean");
  if(!Number.isInteger(operation)||operation<0||operation>10||!Number.isInteger(camera.crs)||camera.crs<0||camera.crs>0xffffffff||args.length>5)throw new TypeError("invalid camera protocol framing");
  if(descriptor!=null&&(!(descriptor instanceof ArrayBuffer)||operation!==10))throw new TypeError("only column projection accepts a descriptor");
  const length=128+(descriptor?.byteLength??0);if(length>256*1024*1024)throw new RangeError("camera request exceeds transport budget");
  const out=new ArrayBuffer(length);writeCameraHeader(out,camera,operation,args);if(descriptor)new Uint8Array(out).set(new Uint8Array(descriptor),128);return out;
}
function writeCameraHeader(out:ArrayBuffer,camera:XygGeoCamera,operation:number,args:readonly number[]=[]):void{
  const v=new DataView(out),b=new Uint8Array(out);b.set([88,89,86,67]);
  for(const[at,n]of[[4,1],[8,operation],[12,camera.crs],[16,camera.worldWrap?1:0]])v.setUint32(at,n,true);
  [camera.centerX,camera.centerY,camera.zoom,camera.width,camera.height,camera.bearing??0,camera.pitch??0].forEach((n,i)=>v.setFloat64(24+8*i,n,true));
  args.forEach((n,i)=>v.setFloat64(80+8*i,n,true));
}
/** Frame typed source planes directly into one prefixed transferable request. */
export function encodeGeoViewportColumnRequest(camera:XygGeoCamera,descriptor:XygGeoDescriptor):ArrayBuffer {
  if(camera.worldWrap!==undefined&&typeof camera.worldWrap!=="boolean")throw new TypeError("worldWrap must be a boolean");
  if(!Number.isInteger(camera.crs)||camera.crs<0||camera.crs>0xffffffff)throw new TypeError("camera CRS must be u32");
  const out=encodeGeoPlanes(descriptor,128);writeCameraHeader(out,camera,10);return out;
}
export function decodeGeoViewportResponse(buffer:ArrayBuffer) {
  const bad=()=>new TypeError("malformed Rust geographic camera response");
  if(!(buffer instanceof ArrayBuffer)||buffer.byteLength<256)throw bad();const v=new DataView(buffer),b=new Uint8Array(buffer);
  const u=(at:number)=>v.getUint32(at,true),f=(at:number)=>v.getFloat64(at,true);
  if(String.fromCharCode(...b.subarray(0,4))!=="XYVR"||u(4)!==1||u(8)>10||![4326,3857].includes(u(12))||u(16)>1||u(20)>2||u(168)>1||b.subarray(172,176).some(n=>n!==0)||b.subarray(232,256).some(n=>n!==0))throw bad();
  const counts=Array.from({length:9},(_,i)=>{const n=v.getBigUint64(96+i*8,true);if(n>BigInt(256*1024*1024))throw bad();return Number(n);});
  const sizes=[4,8,4,8,4,4,4,8,1];let cursor=256;
  const planes=counts.map((count,i)=>{const end=cursor+count*sizes[i],padded=Math.ceil(end/8)*8;if(padded>buffer.byteLength||b.subarray(end,padded).some(n=>n!==0))throw bad();const at=cursor;cursor=padded;
    if(sizes[i]===8){const out=new BigUint64Array(count);for(let j=0;j<count;j++)out[j]=v.getBigUint64(at+j*8,true);return out;}
    if(i===0||i===4){const out=new Float32Array(count);for(let j=0;j<count;j++){out[j]=v.getFloat32(at+j*4,true);if(!Number.isFinite(out[j]))throw bad();}return out;}
    if(sizes[i]===4){const out=new Uint32Array(count);for(let j=0;j<count;j++)out[j]=v.getUint32(at+j*4,true);return out;}return b.slice(at,end);
  });if(cursor!==buffer.byteLength||[24,32,40,48,56,64,72,80,88,184,192,200,208,216,224].some(at=>!Number.isFinite(f(at))))throw bad();
  const camera={crs:u(12),worldWrap:!!u(16),centerX:f(24),centerY:f(32),zoom:f(40),width:f(48),height:f(56),bearing:f(64),pitch:f(72)};
  const key=new Uint8Array(64);key.set(b.subarray(12,20));key.set(b.subarray(24,80),8);
  return{camera,rebuildKey:key,operation:u(8),kind:u(20),result:[f(80),f(88)],bounds:u(168)?[f(184),f(192),f(200),f(208)]:null,metadataDigest:b.slice(176,184),polygonOrigin:[f(216),f(224)],xy:planes[0]as Float32Array,featureIds:planes[1]as BigUint64Array,offsets:planes[2]as Uint32Array,visibleFeatureIds:planes[3]as BigUint64Array,polygonXY:planes[4]as Float32Array,ringOffsets:planes[5]as Uint32Array,polygonOffsets:planes[6]as Uint32Array,polygonFeatureIds:planes[7]as BigUint64Array,ringIsHole:planes[8]as Uint8Array};
}
