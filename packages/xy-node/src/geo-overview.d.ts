/** Typed nonfinal data-domain counts. All temporal/geometry policy is Rust-owned. */
import { type prepareGeoSceneData } from './geoscale.js';
import type { XygGeoQueryBudget, XygGeoScaleBridge, XygGeoScaleQuery } from './geoscale.js';
export declare class GeoOverviewUnsupportedSelected extends Error {
    constructor();
}
/** Internal frame-aware ingress: the raw codec has only a numeric handle and
 * cannot detect selected authority before dispatch. Rust rechecks the owner. */
export declare function encodeGeoOverviewBuild(frame: Awaited<ReturnType<typeof prepareGeoSceneData>>, input: {
    budget: XygGeoQueryBudget;
    maxVertices: bigint;
}): ArrayBuffer;
export interface GeoOverviewRequest {
    command: number;
    handle: bigint;
    sequence: bigint;
    budget?: XygGeoQueryBudget;
    query?: XygGeoScaleQuery;
    payload?: Uint8Array;
}
export declare function encodeGeoOverviewRequest(input: GeoOverviewRequest): ArrayBuffer;
export declare function decodeGeoOverviewReply(packet: ArrayBuffer): {
    code: number;
    handle: bigint;
    sequence: bigint;
    dataLength: bigint;
    sourceHandle: bigint;
    ticket: Uint8Array<ArrayBuffer> | null;
};
/** Mutation success is a fixed terminal receipt, never a resolved transport alone. */
export declare function validateGeoOverviewMutation(packet: ArrayBuffer, handle: bigint, sequence: bigint): {
    code: number;
    handle: bigint;
    sequence: bigint;
    dataLength: bigint;
    sourceHandle: bigint;
    ticket: Uint8Array<ArrayBuffer> | null;
};
export declare function settleGeoOverviewLoan(bridge: XygGeoScaleBridge, handle: bigint, sequence: bigint): Promise<void>;
export declare function parseGeoOverviewData(packet: ArrayBuffer): {
    packet: ArrayBuffer;
    scene: Uint8Array<ArrayBuffer>;
    temporalExact: true;
    dataSpace: true;
    final: false;
    resolution: 16;
    identity: {
        queryHandle: bigint;
        sequence: bigint;
        overviewDigest: Uint8Array<ArrayBuffer>;
        generation: bigint;
        sourceDigest: Uint8Array<ArrayBuffer>;
        sourceCrs: number;
        geometry: number;
        layerId: bigint;
        sourceRows: bigint;
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
        cameraRevision: bigint;
        timeRevision: bigint;
        layerRevision: bigint;
        styleRevision: bigint;
        stateRevision: bigint;
        time: {
            kind: number;
        } | {
            kind: number;
            instant: bigint;
        } | {
            kind: number;
            start: bigint;
            end: bigint;
        };
    };
    count(cell: number): bigint;
};
export interface GeoOverviewTicket {
    raw: Uint8Array;
    owner: bigint;
    namespace: bigint;
    page: bigint;
    kind: number;
    encodedBytes: number;
    chunkIndex: number;
}
type Reader = (ticket: GeoOverviewTicket, signal?: AbortSignal) => Promise<ArrayBuffer | Uint8Array>;
export interface GeoOverviewStorage {
    readChunk: Reader;
    readPage: Reader;
    writePage: (ticket: GeoOverviewTicket, bytes: Uint8Array, signal?: AbortSignal) => Promise<void>;
}
export declare function driveGeoOverview(bridge: XygGeoScaleBridge, input: GeoOverviewStorage & {
    handle: bigint;
    sequence: bigint;
    budget: XygGeoQueryBudget;
    signal?: AbortSignal;
}): Promise<{
    code: number;
    handle: bigint;
    sequence: bigint;
    dataLength: bigint;
    sourceHandle: bigint;
    ticket: Uint8Array<ArrayBuffer> | null;
}>;
export declare function prepareGeoOverviewData(bridge: XygGeoScaleBridge, input: {
    handle: bigint;
    sequence: bigint;
    budget: XygGeoQueryBudget;
}): Promise<{
    handle: bigint;
    readonly data: {
        packet: ArrayBuffer;
        scene: Uint8Array<ArrayBuffer>;
        temporalExact: true;
        dataSpace: true;
        final: false;
        resolution: 16;
        identity: {
            queryHandle: bigint;
            sequence: bigint;
            overviewDigest: Uint8Array<ArrayBuffer>;
            generation: bigint;
            sourceDigest: Uint8Array<ArrayBuffer>;
            sourceCrs: number;
            geometry: number;
            layerId: bigint;
            sourceRows: bigint;
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
            cameraRevision: bigint;
            timeRevision: bigint;
            layerRevision: bigint;
            styleRevision: bigint;
            stateRevision: bigint;
            time: {
                kind: number;
            } | {
                kind: number;
                instant: bigint;
            } | {
                kind: number;
                start: bigint;
                end: bigint;
            };
        };
        count(cell: number): bigint;
    };
    dispose: () => Promise<void>;
}>;
export {};
