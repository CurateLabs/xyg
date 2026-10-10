import type {RetainedGeoSource,OwnedGeoFrame} from './geo-retained.js';
import type {XygGeoScaleQuery} from './geoscale.js';
export interface GeoHierarchyTicket {
 readonly raw:Uint8Array;readonly owner:bigint;readonly namespace:bigint;readonly serial:bigint;
 readonly sequence:bigint;readonly kind:1|2|3|4|5;readonly page:bigint;readonly encodedBytes:number;
 readonly digest:Uint8Array;readonly generation:bigint;readonly chunkIndex:number;readonly rows:number;readonly firstRow:bigint;
}
export interface GeoHierarchyStorage {
 grid:number;maxVertices:bigint;maxWriteBytes:bigint;signal?:AbortSignal;
 readPage(ticket:GeoHierarchyTicket,signal?:AbortSignal):Promise<ArrayBuffer|Uint8Array>|ArrayBuffer|Uint8Array;
 /** Persist an immutable exact copy; settle and drop borrowed bytes before returning. */
 writePage(ticket:GeoHierarchyTicket,bytes:Uint8Array,signal?:AbortSignal):Promise<void>|void;
}
export declare class GeoHierarchyFallback extends Error {readonly reasonCode:1|2;}
export declare class GeoHierarchyUnsupportedSelected extends Error {}
export declare function isHierarchyFrame(frame:object):boolean;
export declare class GeoHierarchy extends RetainedGeoSource {
 readonly pendingOperation:GeoSelectedHierarchyOperation|undefined;
 readonly cancelGeneration:bigint;
 static fromSelectedFrame(frame:OwnedGeoFrame<ReturnType<typeof import('./geoscale.js').parseGeoSceneData>>,source:RetainedGeoSource,options:GeoHierarchyStorage):Promise<GeoHierarchy>;
 fork():Promise<GeoHierarchy>;
 beginSelected(state:import('./geo-selected.js').GeoSelectedState,query:XygGeoScaleQuery,options:{sequence:bigint}):Promise<GeoSelectedHierarchyOperation>;
 updateSelected(state:import('./geo-selected.js').GeoSelectedState,query:XygGeoScaleQuery,options:{sequence:bigint;style:Uint8Array;signal?:AbortSignal}):Promise<OwnedGeoFrame<ReturnType<typeof import('./geoscale.js').parseGeoSceneData>>>;
 static fromFrame(frame:OwnedGeoFrame<ReturnType<typeof import('./geoscale.js').parseGeoSceneData>>,source:RetainedGeoSource,options:GeoHierarchyStorage):Promise<GeoHierarchy>;
 update(query:XygGeoScaleQuery,options:{sequence:bigint;style:Uint8Array;signal?:AbortSignal}):Promise<OwnedGeoFrame<ReturnType<typeof import('./geoscale.js').parseGeoSceneData>> & {readonly hierarchyStats:{directoryReads:bigint;leafReads:bigint;bytesRead:bigint;decodedVertices:bigint;passes:number;cells:number}|null}>;
}
/** Explicit operation retains same-handle ownership through ambiguous43/44 replies. */
export declare class GeoHierarchyPublicationUncertain extends Error {}
export declare class GeoSelectedHierarchyOperation {
 readonly handle:bigint;readonly sequence:bigint;readonly request:ArrayBuffer;readonly closed:boolean;
 readonly hierarchyStats:{directoryReads:bigint;leafReads:bigint;bytesRead:bigint;decodedVertices:bigint;passes:number;cells:number}|null;
 recover():Promise<GeoSelectedHierarchyOperation>;
 drive(options?:{signal?:AbortSignal}):Promise<unknown>;
 prepare(style:Uint8Array,options?:{signal?:AbortSignal;budget?:import('./geoscale.js').XygGeoQueryBudget}):Promise<OwnedGeoFrame<ReturnType<typeof import('./geoscale.js').parseGeoSceneData>>>;
 cancel():Promise<void>;dispose():Promise<void>;
}
export declare function hierarchyLaneAuthority(lane:object):Readonly<{source:RetainedGeoSource;bridge:import('./geoscale.js').XygGeoScaleBridge;creationSequence:bigint;selected:boolean}>|undefined;
