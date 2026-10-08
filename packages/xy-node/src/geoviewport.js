/** Byte-only adapters for the Rust-owned XYVC/XYVR camera protocol. */
export const XYVC_HEADER_BYTES = 128;
export const XYVR_HEADER_BYTES = 256;
export const GEO_VIEWPORT_OPERATIONS = Object.freeze({ normalize: 0, project: 1, inverse: 2, pan: 3, zoom: 4, resize: 5, bearing: 6, pitch: 7, center: 8, fit: 9, column: 10 });
export function encodeGeoViewportRequest(camera, operation = 0, args = [], descriptor) {
    if (camera.worldWrap !== undefined && typeof camera.worldWrap !== "boolean") throw new TypeError("worldWrap must be a boolean");
    if (!Number.isInteger(operation) || operation < 0 || operation > 10 || !Number.isInteger(camera.crs) || camera.crs < 0 || camera.crs > 0xffffffff || args.length > 5)
        throw new TypeError("invalid camera protocol framing");
    if (descriptor != null && (!(descriptor instanceof ArrayBuffer) || operation !== 10))
        throw new TypeError("only column projection accepts a descriptor");
    const length = 128 + (descriptor?.byteLength ?? 0);
    if (length > 256 * 1024 * 1024)
        throw new RangeError("camera request exceeds transport budget");
    const out = new ArrayBuffer(length), v = new DataView(out), b = new Uint8Array(out);
    b.set([88, 89, 86, 67]);
    for (const [at, n] of [[4, 1], [8, operation], [12, camera.crs], [16, camera.worldWrap ? 1 : 0]])
        v.setUint32(at, n, true);
    [camera.centerX, camera.centerY, camera.zoom, camera.width, camera.height, camera.bearing ?? 0, camera.pitch ?? 0].forEach((n, i) => v.setFloat64(24 + 8 * i, n, true));
    args.forEach((n, i) => v.setFloat64(80 + 8 * i, n, true));
    if (descriptor)
        b.set(new Uint8Array(descriptor), 128);
    return out;
}
export function decodeGeoViewportResponse(buffer) {
    const bad = () => new TypeError("malformed Rust geographic camera response");
    if (!(buffer instanceof ArrayBuffer) || buffer.byteLength < 256)
        throw bad();
    const v = new DataView(buffer), b = new Uint8Array(buffer);
    const u = (at) => v.getUint32(at, true), f = (at) => v.getFloat64(at, true);
    if (String.fromCharCode(...b.subarray(0, 4)) !== "XYVR" || u(4) !== 1 || u(8) > 10 || ![4326, 3857].includes(u(12)) || u(16) > 1 || u(20) > 2 || u(168) > 1 || b.subarray(172, 176).some(n => n !== 0) || b.subarray(232, 256).some(n => n !== 0))
        throw bad();
    const counts = Array.from({ length: 9 }, (_, i) => { const n = v.getBigUint64(96 + i * 8, true); if (n > BigInt(256 * 1024 * 1024))
        throw bad(); return Number(n); });
    const sizes = [4, 8, 4, 8, 4, 4, 4, 8, 1];
    let cursor = 256;
    const planes = counts.map((count, i) => {
        const end = cursor + count * sizes[i], padded = Math.ceil(end / 8) * 8;
        if (padded > buffer.byteLength || b.subarray(end, padded).some(n => n !== 0))
            throw bad();
        const at = cursor;
        cursor = padded;
        if (sizes[i] === 8) {
            const out = new BigUint64Array(count);
            for (let j = 0; j < count; j++)
                out[j] = v.getBigUint64(at + j * 8, true);
            return out;
        }
        if (i === 0 || i === 4) {
            const out = new Float32Array(count);
            for (let j = 0; j < count; j++) {
                out[j] = v.getFloat32(at + j * 4, true);
                if (!Number.isFinite(out[j]))
                    throw bad();
            }
            return out;
        }
        if (sizes[i] === 4) {
            const out = new Uint32Array(count);
            for (let j = 0; j < count; j++)
                out[j] = v.getUint32(at + j * 4, true);
            return out;
        }
        return b.slice(at, end);
    });
    if (cursor !== buffer.byteLength || [24, 32, 40, 48, 56, 64, 72, 80, 88, 184, 192, 200, 208, 216, 224].some(at => !Number.isFinite(f(at))))
        throw bad();
    const camera = { crs: u(12), worldWrap: !!u(16), centerX: f(24), centerY: f(32), zoom: f(40), width: f(48), height: f(56), bearing: f(64), pitch: f(72) };
    const key = new Uint8Array(64);
    key.set(b.subarray(12, 20));
    key.set(b.subarray(24, 80), 8);
    return { camera, rebuildKey: key, operation: u(8), kind: u(20), result: [f(80), f(88)], bounds: u(168) ? [f(184), f(192), f(200), f(208)] : null, metadataDigest: b.slice(176, 184), polygonOrigin: [f(216), f(224)], xy: planes[0], featureIds: planes[1], offsets: planes[2], visibleFeatureIds: planes[3], polygonXY: planes[4], ringOffsets: planes[5], polygonOffsets: planes[6], polygonFeatureIds: planes[7], ringIsHole: planes[8] };
}

/** Thin native camera adapter; same typed framing as the browser host. */
import {xyGeoViewportExecute,pointer} from "./native.js";
import {GeoNativeError} from "./abi.js";
export function geoViewportExecute(request,budget=64*1024*1024){
 if(!(request instanceof ArrayBuffer)||!Number.isSafeInteger(budget)||budget<0||budget>384*1024*1024)throw new TypeError("invalid camera request/budget");
 if(request.byteLength>budget)throw new GeoNativeError(-9);
 if(request.byteLength<128)throw new GeoNativeError(-1);
 const input=new Uint8Array(request),length=new BigUint64Array(1);
 let code=xyGeoViewportExecute(pointer(input,"uint8_t *"),BigInt(input.length),BigInt(budget),null,0n,pointer(length,"size_t *"));
 if(code!==0)throw new GeoNativeError(code);
 if(length[0]>BigInt(budget))throw new GeoNativeError(-9);
 const out=new Uint8Array(Number(length[0]));
 code=xyGeoViewportExecute(pointer(input,"uint8_t *"),BigInt(input.length),BigInt(budget),pointer(out,"uint8_t *"),BigInt(out.length),pointer(length,"size_t *"));
 if(code!==0)throw new GeoNativeError(code);return out.buffer;
}
export function geoViewport(camera,operation=0,args=[],descriptor,budget=64*1024*1024){return decodeGeoViewportResponse(geoViewportExecute(encodeGeoViewportRequest(camera,operation,args,descriptor),budget));}

/** Frame already-decoded GeoArrow planes directly into one native camera request. */
export function encodeGeoViewportColumnRequest(camera,input){
 if(camera.worldWrap!==undefined&&typeof camera.worldWrap!=="boolean")throw new TypeError("worldWrap must be a boolean");
 for(const n of[camera.crs,input.crs,input.geometry])if(!Number.isInteger(n)||n<0||n>0xffffffff)throw new TypeError("camera/descriptor codes must be u32");
 if(!(input.xy instanceof Float64Array)||input.xy.length%2||!(input.validity instanceof Uint8Array)||(input.featureIds!=null&&(!(input.featureIds instanceof BigUint64Array)||input.featureIds.length!==input.validity.length)))throw new TypeError("GeoArrow descriptor planes must retain their exact typed representation");
 const offsets=[input.offsets0,input.offsets1,input.offsets2].map(p=>p??new Uint32Array());if(offsets.some(p=>!(p instanceof Uint32Array)))throw new TypeError("offsets must be u32 typed planes");
 const planes=[input.xy,input.validity,input.featureIds??new BigUint64Array(),...offsets],padded=n=>Math.ceil(n/8)*8,length=planes.reduce((sum,p)=>sum+padded(p.byteLength),192);
 if(!Number.isSafeInteger(length)||length>256*1024*1024)throw new RangeError("camera descriptor exceeds transport budget");
 const out=new ArrayBuffer(length),b=new Uint8Array(out),v=new DataView(out);b.set([88,89,86,67]);for(const[at,n]of[[4,1],[8,10],[12,camera.crs],[16,camera.worldWrap?1:0]])v.setUint32(at,n,true);
 [camera.centerX,camera.centerY,camera.zoom,camera.width,camera.height,camera.bearing??0,camera.pitch??0].forEach((n,i)=>v.setFloat64(24+i*8,n,true));
 b.set([88,89,71,68],128);for(const[at,n]of[[132,1],[136,input.geometry],[140,input.crs],[144,input.featureIds==null?0:1]])v.setUint32(at,n,true);
 [input.validity.length,input.xy.length/2,...offsets.map(p=>p.length)].forEach((n,i)=>v.setBigUint64(152+i*8,BigInt(n),true));
 let cursor=192;for(let i=0;i<planes.length;i++){const plane=planes[i];for(let j=0;j<plane.length;j++){if(i===0)v.setFloat64(cursor+j*8,plane[j],true);else if(i===1)v.setUint8(cursor+j,plane[j]);else if(i===2)v.setBigUint64(cursor+j*8,plane[j],true);else v.setUint32(cursor+j*4,plane[j],true);}cursor+=padded(plane.byteLength);}return out;
}
