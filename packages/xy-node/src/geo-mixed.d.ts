export interface GeoMixedInput {
 command:1|2|3|4|5|6|20;handle?:bigint;nonce?:bigint;budget?:number;
 sourceHandle?:bigint;sourceSequence?:bigint;tileHandle?:bigint;tileEpoch?:bigint;
 tileCacheHandle?:bigint;tileViewId?:bigint;tileTime?:0|1;
 snapshot?:Uint8Array;stamps?:Uint8Array;
}
export interface GeoMixedBridge {execute(request:ArrayBuffer):Promise<ArrayBuffer>;read(request:ArrayBuffer):Promise<ArrayBuffer>}
export function encodeGeoMixedRequest(input:GeoMixedInput):ArrayBuffer;
export function decodeGeoMixedReply(packet:ArrayBuffer):{kind:number;handle:bigint;nonce:bigint;coordinator:bigint;length:number};
export function parseGeoMixedData(packet:ArrayBuffer):{
 packet:ArrayBuffer;scene:Uint8Array;tile:Uint8Array;snapshot:Uint8Array;style:Uint8Array;
 coordinator:bigint;nonce:bigint;sourceHandle:bigint;sourceSequence:bigint;tileHandle:bigint;tileEpoch:bigint;tileTime:number;
 retainedRecords:{start:number;end:number};retainedStyles:{start:number;end:number};visibleVertices:bigint;projectedVertices:bigint;
};
export function nativeGeoMixedBridge(budget:number):GeoMixedBridge;
export function prepareGeoMixedCandidate(input:GeoMixedInput&{command:2;handle:bigint;budget:number;sourceHandle:bigint;sourceSequence:bigint;tileHandle:bigint;tileEpoch:bigint;tileCacheHandle:bigint;tileViewId:bigint;tileTime:0|1;snapshot:Uint8Array;stamps:Uint8Array},{bridge}?:{bridge?:GeoMixedBridge}):Promise<{
 handle:bigint;nonce:bigint;readonly data:ReturnType<typeof parseGeoMixedData>;
 commit():Promise<void>;cancel():Promise<void>;dispose():Promise<void>;
 retainSourceAuthority():Promise<ReturnType<typeof decodeGeoMixedReply>>;
 export(format?:'svg'|'png'|'pdf'|'jpeg'|'webp'|'html',options?:{scale?:number;quality?:number;budget?:number;bridge?:import('./geo-snapshot.js').GeoSnapshotBridge}):Promise<import('./geo-snapshot.js').OwnedGeoArtifact>;
}>;

export function parseGeoMixedTileDescriptor(packet:ArrayBuffer):{packet:ArrayBuffer;handle:bigint;epoch:bigint;cache:bigint;view:bigint;stamps:Uint8Array};
