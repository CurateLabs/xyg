import type { XygGeoScaleBridge, XygGeoQueryBudget, XygGeoScaleQuery, XygGeoReadTicket } from './geoscale.js';
declare const AUTHORITY: unique symbol;
export declare function createGeoSelectedScope(bridge: XygGeoScaleBridge, input: {
    frameHandle: bigint;
    sequence: bigint;
    namespace: bigint;
    layerId: bigint;
    budget: XygGeoQueryBudget;
}): Promise<GeoSelectedScope>;
export declare class GeoSelectedScope {
    private owner;
    private bridge;
    constructor(bridge: XygGeoScaleBridge, handle: bigint, token: typeof AUTHORITY);
    get handle(): bigint;
    dispose(): Promise<void>;
    state(input: {
        revision: bigint;
        ids: BigUint64Array;
        fill: Uint8Array;
        budget: XygGeoQueryBudget;
    }): Promise<GeoSelectedState>;
    link(state: GeoSelectedState, input: {
        revision: bigint;
        budget: XygGeoQueryBudget;
    }): Promise<GeoSelectedState>;
}
export declare class GeoSelectedState {
    private owner;
    private bridge;
    readonly scope: GeoSelectedScope;
    constructor(bridge: XygGeoScaleBridge, handle: bigint, scope: GeoSelectedScope, token: typeof AUTHORITY);
    get handle(): bigint;
    check(): void;
    belongsTo(bridge: XygGeoScaleBridge): boolean;
    dispose(): Promise<void>;
    begin(input: {
        command: 35 | 36;
        handle: bigint;
        sequence: bigint;
        query: XygGeoScaleQuery;
        budget: XygGeoQueryBudget;
    }): Promise<{
        fallback: true;
        reason: number | null;
        state: GeoSelectedState;
        operation?: undefined;
    } | {
        reason?: undefined;
        state?: undefined;
        fallback: false;
        operation: GeoSelectedOperation;
    }>;
}
export declare class GeoSelectedOperation {
    private replaced;
    private bridge;
    readonly handle: bigint;
    readonly sequence: bigint;
    readonly indexed: boolean;
    readonly budget: XygGeoQueryBudget;
    readonly scope: GeoSelectedScope;
    constructor(bridge: XygGeoScaleBridge, handle: bigint, sequence: bigint, indexed: boolean, budget: XygGeoQueryBudget, scope: GeoSelectedScope, token: typeof AUTHORITY);
    drive(input: {
        readChunk?: (ticket: XygGeoReadTicket, signal?: AbortSignal) => Promise<ArrayBuffer | Uint8Array>;
        readPage?: (ticket: XygGeoReadTicket, signal?: AbortSignal) => Promise<ArrayBuffer | Uint8Array>;
        signal?: AbortSignal;
    }): Promise<{
        code: number;
        fallbackReasonCode: number | null;
        handle: bigint;
        sequence: bigint;
        dataLength: bigint;
        sourceHandle: bigint;
        source: {
            generation: bigint;
            digest: Uint8Array<ArrayBuffer>;
            rows: bigint;
            geometry: number;
            crs: number;
        };
        ticket: XygGeoReadTicket | null;
        indexStats: {
            pagesRead: bigint;
            bytesRead: bigint;
            candidateVertices: bigint;
            passes: number;
        } | null;
    }>;
    prepare(style: Uint8Array): Promise<{
        handle: bigint;
        readonly data: {
            packet: ArrayBuffer;
            scene: Uint8Array<ArrayBuffer>;
            selection: {
                raw: Uint8Array<ArrayBufferLike>;
                namespace: bigint;
                fill: Uint8Array<ArrayBufferLike>;
                idCount: number;
                cellCount: number;
                visibleVertices: bigint | null;
                id(index: number): bigint;
                cell(index: number): bigint;
            } | null;
            aggregate: boolean;
            droppedChannels: number;
            visibleVertices: bigint;
            projectedVertices: bigint;
            columns: number;
            rows: number;
            gridCapped: boolean;
            metadata: DataView<ArrayBuffer>;
            length: number;
            identity: {
                sessionHandle: bigint;
                sequence: bigint;
                camera: {
                    crs: number;
                    worldWrap: boolean;
                    centerX: number;
                    centerY: number;
                    zoom: number;
                    width: number;
                    height: number;
                    bearing: number;
                    pitch: number;
                };
                sourceDigest: Uint8Array<ArrayBuffer>;
                generation: bigint;
                layerId: bigint;
                cameraRevision: bigint;
                timeRevision: bigint;
                layerRevision: bigint;
                styleRevision: bigint;
                stateRevision: bigint;
                time: import("./63_geo_source").XygGeoTime;
                reducedKind: number;
                sourceRows: bigint;
                geometry: number;
                sourceCrs: number;
            };
            record(index: number): {
                count: bigint;
                x: number;
                y: number;
                featureId?: undefined;
                sourceRow?: undefined;
                chunkIndex?: undefined;
                chunkRow?: undefined;
                vertex?: undefined;
            } | {
                count?: undefined;
                x?: undefined;
                y?: undefined;
                featureId: bigint;
                sourceRow: bigint;
                chunkIndex: number;
                chunkRow: number;
                vertex: number;
            };
        };
        dispose(): Promise<void>;
    }>;
    cancel(): Promise<void>;
    dispose(): Promise<void>;
}
export {};
