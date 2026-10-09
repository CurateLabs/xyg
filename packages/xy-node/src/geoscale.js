export const GEO_SCALE_HEADER = 256;
const MAX_PACKET = 32 * 1024 * 1024, MAX_PROCESSOR = 128 * 1024 * 1024;
function u32(n) { if (!Number.isInteger(n) || n < 0 || n > 0xffffffff)
    throw new TypeError('expected u32'); return n; }
function u64(n) { if (typeof n !== 'bigint' || n < 0n || n > 0xffffffffffffffffn)
    throw new TypeError('expected u64 bigint'); return n; }
function i64(n) { if (typeof n !== 'bigint' || n < -0x8000000000000000n || n > 0x7fffffffffffffffn)
    throw new TypeError('expected i64 bigint'); return n; }
function budgetBytes(n) { if (!Number.isSafeInteger(n) || n < 256 || n > MAX_PROCESSOR)
    throw new RangeError('invalid processor budget'); return n; }
function bytes(p) { if (p instanceof ArrayBuffer)
    return new Uint8Array(p); if (p instanceof Uint8Array)
    return p; throw new TypeError('expected raw bytes'); }
function zero(b, a, z) { if (b.subarray(a, z).some(v => v !== 0))
    throw new TypeError('nonzero reserved bytes'); }
function response(buffer) { if (!(buffer instanceof ArrayBuffer) || buffer.byteLength < 256 || buffer.byteLength > MAX_PACKET)
    throw new TypeError('invalid geographic reply size'); const b = new Uint8Array(buffer), v = new DataView(buffer); if (String.fromCharCode(...b.subarray(0, 4)) !== 'XYGZ' || v.getUint32(4, true) !== 1)
    throw new TypeError('invalid geographic reply'); return { b, v }; }
function count(v, at, max = MAX_PACKET) { const n = v.getBigUint64(at, true); if (n > BigInt(max))
    throw new RangeError('reply count exceeds framing'); return Number(n); }
export function encodeGeoScaleRequest(input) {
    const command = u32(input.command);
    if (![1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 20, 21, 23].includes(command))
        throw new TypeError('unknown geographic command');
    const payload = input.payload === undefined ? new Uint8Array() : bytes(input.payload), length = 256 + payload.byteLength;
    if (length > MAX_PACKET || input.budget && length > budgetBytes(input.budget.processorBytes))
        throw new RangeError('request exceeds framing budget');
    if (input.query !== undefined && command !== 5 || input.generation !== undefined && command !== 3 || input.sequence !== undefined && ![5, 6, 9, 11, 12, 13, 14].includes(command))
        throw new TypeError('field does not belong to command');
    const out = new ArrayBuffer(length), b = new Uint8Array(out), v = new DataView(out);
    b.set([88, 89, 71, 81]);
    v.setUint32(4, 1, true);
    v.setUint32(8, command, true);
    v.setBigUint64(16, u64(input.handle ?? 0n), true);
    v.setBigUint64(24, u64(input.sequence ?? 0n), true);
    if (input.budget) {
        const q = input.budget;
        v.setBigUint64(32, BigInt(budgetBytes(q.processorBytes)), true);
        v.setBigUint64(40, u64(q.maxRowsExamined), true);
        v.setBigUint64(48, u64(q.maxReadBytes), true);
        v.setUint32(56, u32(q.maxChunks), true);
        v.setUint32(60, u32(q.pageRows), true);
    }
    if (command === 3)
        v.setBigUint64(144, u64(input.generation ?? 0n), true);
    if (command === 5) {
        const q = input.query;
        if (!q)
            throw new TypeError('begin requires query');
        const c = q.camera;
        if (typeof c.worldWrap !== 'boolean' || typeof q.previousDirect !== 'boolean' || !(q.sourceDigest instanceof Uint8Array) || q.sourceDigest.length !== 8)
            throw new TypeError('invalid query framing');
        v.setUint32(12, c.worldWrap ? 1 : 0, true);
        v.setUint32(64, u32(c.crs), true);
        v.setUint32(68, u32(q.reducedKind), true);
        v.setUint32(72, u32(q.maxCells), true);
        v.setUint32(76, q.previousDirect ? 1 : 0, true);
        [c.centerX, c.centerY, c.zoom, c.width, c.height, c.bearing, c.pitch].forEach((n, i) => { if (typeof n !== 'number')
            throw new TypeError('camera requires explicit f64 values'); v.setFloat64(80 + i * 8, n, true); });
        b.set(q.sourceDigest, 136);
        [q.generation, q.layerId, q.cameraRevision, q.timeRevision, q.layerRevision, q.styleRevision, q.stateRevision].forEach((n, i) => v.setBigUint64(144 + i * 8, u64(n), true));
        v.setUint32(200, u32(q.time.kind), true);
        if (q.time.kind === 1)
            v.setBigInt64(208, i64(q.time.instant), true);
        else if (q.time.kind === 2) {
            v.setBigInt64(208, i64(q.time.start), true);
            v.setBigInt64(216, i64(q.time.end), true);
        }
        else if (q.time.kind !== 0)
            throw new TypeError('unknown time predicate');
        v.setBigUint64(224, u64(q.maxProjectedVertices), true);
    }
    v.setBigUint64(232, BigInt(payload.length), true);
    b.set(payload, 256);
    return out;
}
export function encodeGeoScaleStyle(style) {
    const b = new Uint8Array(48), v = new DataView(b.buffer);
    if (!(style.fill instanceof Uint8Array) || style.fill.length !== 4 || !(style.stroke instanceof Uint8Array) || style.stroke.length !== 4 || u32(style.symbol) > 255)
        throw new TypeError('invalid exact style framing');
    b.set(style.fill);
    b.set(style.stroke, 4);
    [style.strokeWidth, style.diameter, style.opacity].forEach((n, i) => { if (typeof n !== 'number')
        throw new TypeError('style requires f64'); v.setFloat64(8 + i * 8, n, true); });
    b[32] = style.symbol;
    return b;
}
function readTicket(raw) { const v = new DataView(raw.buffer, raw.byteOffset, raw.byteLength); zero(raw, 28, 32); zero(raw, 72, 96); return { raw, sessionId: v.getBigUint64(0, true), readId: v.getBigUint64(8, true), sequence: v.getBigUint64(16, true), pass: v.getUint32(24, true), generation: v.getBigUint64(32, true), chunkIndex: v.getUint32(40, true), rows: v.getUint32(44, true), firstRow: v.getBigUint64(48, true), encodedBytes: count(v, 56, 16 * 1024 * 1024), digest: raw.subarray(64, 72) }; }
export function decodeGeoScaleReply(buffer) { const { b, v } = response(buffer); if (buffer.byteLength !== 256)
    throw new TypeError('mutation reply must be fixed size'); const code = v.getUint32(8, true); if (code > 6)
    throw new TypeError('invalid step code'); zero(b, 12, 16); if(code===4){if(v.getBigUint64(160,true)>4096n||v.getUint32(168,true)>1)throw new TypeError('invalid membership reply');zero(b,176,256);}else zero(b,160,256); return { code, handle: v.getBigUint64(16, true), sequence: v.getBigUint64(24, true), dataLength: v.getBigUint64(32, true), sourceHandle: v.getBigUint64(40, true), source: { generation: v.getBigUint64(32, true), digest: b.subarray(40, 48), rows: v.getBigUint64(48, true), geometry: v.getUint32(56, true), crs: v.getUint32(60, true) }, ticket: code === 1 || code === 2 ? readTicket(b.subarray(64, 160)) : null }; }
export function encodeGeoChunkRequest(input, budget) {
    budgetBytes(budget);
    const d = bytes(input.descriptor), n = u32(input.rows), t = input.intervals, s = input.values;
    if (n > 65536 || t && (!(t.starts instanceof BigInt64Array) || !(t.ends instanceof BigInt64Array) || !(t.startValidity instanceof Uint8Array) || !(t.endValidity instanceof Uint8Array) || [t.starts, t.ends, t.startValidity, t.endValidity].some(p => p.length !== n)) || s !== undefined && (!(s instanceof Float64Array) || s.length !== n))
        throw new TypeError('chunk requires exact typed planes');
    const size = 32 + d.length + n * ((t ? 18 : 0) + (s ? 8 : 0));
    if (size > 16 * 1024 * 1024 || 6 * size + 32768 + 256 > budget)
        throw new RangeError('chunk exceeds peak framing budget');
    const payload = new Uint8Array(size), v = new DataView(payload.buffer);
    v.setBigUint64(0, BigInt(d.length), true);
    v.setUint32(8, (t ? 1 : 0) | (s ? 2 : 0), true);
    v.setBigUint64(16, BigInt(n), true);
    payload.set(d, 32);
    let at = 32 + d.length;
    if (t) {
        for (const p of [t.starts, t.ends]) {
            for (let i = 0; i < n; i++)
                v.setBigInt64(at + i * 8, p[i], true);
            at += n * 8;
        }
        payload.set(t.startValidity, at);
        at += n;
        payload.set(t.endValidity, at);
        at += n;
    }
    if (s)
        for (let i = 0; i < n; i++)
            v.setFloat64(at + i * 8, s[i], true);
    return encodeGeoScaleRequest({ command: 20, payload });
}
/** Views borrow packet storage; consumers must drop every view/copy before lease disposal. */
export function parseGeoSceneData(packet            ){
 const {b,v}=response(packet),aggregate=v.getUint32(8,true),droppedChannels=v.getUint32(12,true),sceneLength=count(v,32),metadataLength=count(v,40),columns=v.getUint32(64,true),rows=v.getUint32(68,true),gridCapped=v.getUint32(72,true),timeKind=v.getUint32(208,true),reducedKind=v.getUint32(212,true);
 if(aggregate>1||gridCapped>1||timeKind>2||reducedKind>1||droppedChannels&~7||256+sceneLength+metadataLength!==packet.byteLength||sceneLength<160)throw new TypeError('malformed SceneData framing');zero(b,76,80);zero(b,248,256);
 const scene=b.subarray(256,256+sceneLength),sv=new DataView(packet,256,sceneLength);if(String.fromCharCode(...scene.subarray(0,4))!=='XYGS'||sv.getUint32(4,true)!==32)throw new TypeError('invalid Scene32 packet');
 const stride=aggregate?24:40;if(metadataLength%stride||aggregate&&columns*rows!==metadataLength/stride)throw new TypeError('invalid provenance framing');
 const sourceRows=v.getBigUint64(232,true),geometry=v.getUint32(240,true);if(![1,4].includes(geometry))throw new TypeError('invalid retained source geometry');
 const metadata=new DataView(packet,256+sceneLength,metadataLength),length=metadataLength/stride;
 for(let i=0;i<length;i++){const at=i*stride;if(aggregate){if(!Number.isFinite(metadata.getFloat64(at+8,true))||!Number.isFinite(metadata.getFloat64(at+16,true)))throw new TypeError('invalid reduced coordinates');}else if(metadata.getBigUint64(at+8,true)>=sourceRows||metadata.getUint32(at+16,true)>=65536||metadata.getUint32(at+20,true)>=65536||metadata.getUint32(at+24,true)>=524288||metadata.getUint32(at+28,true)!==0||metadata.getBigUint64(at+32,true)!==0n)throw new TypeError('invalid direct reserved metadata');}
 const crs=v.getUint32(80,true),wrap=v.getUint32(84,true),sourceCrs=v.getUint32(244,true);if(![4326,3857].includes(crs)||![4326,3857].includes(sourceCrs)||wrap>1)throw new TypeError('invalid camera/source CRS');const cameraValues=[88,96,104,112,120,128,136].map(at=>v.getFloat64(at,true));if(cameraValues.some(n=>!Number.isFinite(n)))throw new TypeError('invalid camera values');
 if(timeKind===0){zero(b,216,232);}else if(timeKind===1)zero(b,224,232);else if(v.getBigInt64(216,true)>=v.getBigInt64(224,true))throw new TypeError('invalid time window');
 const time           =timeKind===0?{kind:0}:timeKind===1?{kind:1,instant:v.getBigInt64(216,true)}:{kind:2,start:v.getBigInt64(216,true),end:v.getBigInt64(224,true)};
 return {packet,scene,aggregate:!!aggregate,droppedChannels,visibleVertices:v.getBigUint64(48,true),projectedVertices:v.getBigUint64(56,true),columns,rows,gridCapped:!!gridCapped,metadata,length,
  identity:{sessionHandle:v.getBigUint64(16,true),sequence:v.getBigUint64(24,true),camera:{crs,worldWrap:!!wrap,centerX:cameraValues[0],centerY:cameraValues[1],zoom:cameraValues[2],width:cameraValues[3],height:cameraValues[4],bearing:cameraValues[5],pitch:cameraValues[6]},sourceDigest:b.subarray(144,152),generation:v.getBigUint64(152,true),layerId:v.getBigUint64(160,true),cameraRevision:v.getBigUint64(168,true),timeRevision:v.getBigUint64(176,true),layerRevision:v.getBigUint64(184,true),styleRevision:v.getBigUint64(192,true),stateRevision:v.getBigUint64(200,true),time,reducedKind,sourceRows:v.getBigUint64(232,true),geometry:v.getUint32(240,true),sourceCrs},
  record(index       ){if(!Number.isInteger(index)||index<0||index>=length)throw new RangeError('provenance index');const at=index*stride;return aggregate?{count:metadata.getBigUint64(at,true),x:metadata.getFloat64(at+8,true),y:metadata.getFloat64(at+16,true)}:{featureId:metadata.getBigUint64(at,true),sourceRow:metadata.getBigUint64(at+8,true),chunkIndex:metadata.getUint32(at+16,true),chunkRow:metadata.getUint32(at+20,true),vertex:metadata.getUint32(at+24,true)};}};
}
function aborted() { return new DOMException('Geographic operation cancelled', 'AbortError'); }
/** Service only Rust-issued reads. Caller begins/validates the source explicitly. */
export async function driveGeoSession(bridge, input) {
    const { handle, sequence, budget, signal } = input;
    let cancelPromise;
    const cancel = () => cancelPromise ??= bridge.execute(encodeGeoScaleRequest({ command: 9, handle, sequence }));
    const onAbort = () => { void cancel().catch(() => { }); };
    signal?.addEventListener('abort', onAbort, { once: true });
    try {
        for (;;) {
            if (signal?.aborted) {
                await cancel();
                throw aborted();
            }
            const reply = decodeGeoScaleReply(await bridge.execute(encodeGeoScaleRequest({ command: 6, handle, sequence, budget })));
            if (reply.handle !== handle || reply.sequence !== sequence)
                throw new TypeError('mismatched session reply');
            if (reply.code === 3 || reply.code === 4 || reply.code === 5 || reply.code === 6) {
                if (signal?.aborted) {
                    await cancel();
                    throw aborted();
                }
                return reply;
            }
            if (reply.code !== 1 || !reply.ticket)
                throw new TypeError('unowned outstanding read');
            const ticket = reply.ticket, authority = ticket.raw.slice();
            const callbackTicket = {...ticket, raw: authority.slice(), digest: ticket.digest.slice()};
            let borrowed, chunk, supply;
            try {
                if (signal?.aborted) {
                    await cancel();
                    throw aborted();
                }
                borrowed = await input.readChunk(callbackTicket, signal);
                chunk = bytes(borrowed);
                if (chunk.byteLength !== ticket.encodedBytes || chunk.buffer.byteLength > ticket.encodedBytes)
                    throw new RangeError('read callback must return exact bounded storage');
                if (signal?.aborted) {
                    await cancel();
                    throw aborted();
                }
                if (3 * (352 + chunk.byteLength) > budget.processorBytes)
                    throw new RangeError('read transfer exceeds peak budget');
                let payload = new Uint8Array(96 + chunk.byteLength);
                payload.set(authority);
                payload.set(chunk, 96);
                supply = encodeGeoScaleRequest({ command: 7, handle, payload });
                payload = undefined;
                await bridge.execute(supply);
            }
            catch (error) {
                try {
                    await cancel();
                }
                catch { /* Preserve the read/supply error; release is still required. */ }
                throw error;
            }
            finally {
                borrowed = undefined;
                chunk = undefined;
                supply = undefined;
                try {
                    if (cancelPromise)
                        await cancelPromise;
                }
                finally {
                    await bridge.execute(encodeGeoScaleRequest({ command: 8, handle, payload: authority }));
                }
            }
        }
    }
    finally {
        signal?.removeEventListener('abort', onAbort);
        if (cancelPromise)
            await cancelPromise;
    }
}
/** Disposal is explicit: first destroy painters and drop packet-derived copies/views. */
export async function prepareGeoSceneData(bridge, input) {
    if (!(input.style instanceof Uint8Array) || input.style.length !== 48)
        throw new TypeError('style must be exact 48-byte Rust framing');
    const reply = decodeGeoScaleReply(await bridge.execute(encodeGeoScaleRequest({ command: 11, handle: input.handle, sequence: input.sequence, budget: input.budget, payload: input.style }))), handle = reply.handle;
    let data, packet;
    try {
        if (reply.sourceHandle !== input.handle || reply.sequence !== input.sequence || reply.dataLength > BigInt(MAX_PACKET) || 4 * Number(reply.dataLength) > input.budget.processorBytes)
            throw new TypeError('invalid leased data reply');
        packet = await bridge.read(encodeGeoScaleRequest({ command: 23, handle }));
        if (BigInt(packet.byteLength) !== reply.dataLength)
            throw new TypeError('mismatched leased data size');
        data = parseGeoSceneData(packet);
        if (data.identity.sessionHandle !== input.handle || data.identity.sequence !== input.sequence)
            throw new TypeError('mismatched leased data identity');
        packet = undefined;
    }
    catch (error) {
        data = undefined;
        packet = undefined;
        await bridge.execute(encodeGeoScaleRequest({ command: 10, handle }));
        throw error;
    }
    let disposal;
    return { handle, get data() { if (!data)
            throw new Error('SceneData disposed'); return data; }, dispose() { data = undefined; return disposal ??= bridge.execute(encodeGeoScaleRequest({ command: 10, handle })).then(() => { }); } };
}

// Load generated native bindings only when requested; framing stays host-neutral.
let nativeCore;
function core() { return nativeCore ??= Promise.all([import('./native.js'), import('./abi.js')]).then(([native, abi]) => ({...native, GeoNativeError:abi.GeoNativeError})); }
export async function geoScaleExecute(request) {
 const input=bytes(request);if(input.length<256||input.length>MAX_PACKET)throw new RangeError('invalid geographic request size');
 const native=await core(),out=new Uint8Array(256);
 const status=native.xyGeoScaleExecute(native.pointer(input,'uint8_t *'),BigInt(input.length),native.pointer(out,'uint8_t *'),256n);
 if(status!==0)throw new native.GeoNativeError(status);return out.buffer;
}
export async function geoScaleRead(request,budget) {
 budgetBytes(budget);const input=bytes(request);if(input.length<256||input.length>MAX_PACKET||input.length>budget)throw new RangeError('invalid geographic read request size');
 const native=await core(),length=new BigUint64Array(1);
 let status=native.xyGeoScaleRead(native.pointer(input,'uint8_t *'),BigInt(input.length),BigInt(budget),null,0n,native.pointer(length,'size_t *'));
 if(status!==0)throw new native.GeoNativeError(status);if(length[0]>BigInt(MAX_PACKET)||4n*length[0]>BigInt(budget))throw new native.GeoNativeError(-9);
 const out=new Uint8Array(Number(length[0]));status=native.xyGeoScaleRead(native.pointer(input,'uint8_t *'),BigInt(input.length),BigInt(budget),native.pointer(out,'uint8_t *'),BigInt(out.length),native.pointer(length,'size_t *'));
 if(status!==0)throw new native.GeoNativeError(status);if(length[0]!==BigInt(out.length))throw new TypeError('read length changed');return out.buffer;
}
export function nativeGeoScaleBridge(budget) { budgetBytes(budget);return {execute:geoScaleExecute,read:request=>geoScaleRead(request,budget)}; }
