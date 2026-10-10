/** Explicit selected-state owners. Geometry, joining and count policy stay in Rust. */
import { captureGeoSceneDataIssuer } from './geoscale.js';
import type { XygGeoScaleBridge, XygGeoQueryBudget, XygGeoScaleQuery, XygGeoReadTicket } from './geoscale.js';
declare const AUTHORITY: unique symbol;
export declare function createGeoSelectedScope(bridge: XygGeoScaleBridge, input: {
    frameHandle: bigint;
    sequence: bigint;
    namespace: bigint;
    layerId: bigint;
    budget: XygGeoQueryBudget;
}): Promise<GeoSelectedScope>;
/** Retains an immutable allocation request before dispatch; recovery never issues a new nonce. */
export declare class GeoSelectedStateAttempt {
    #private;
    constructor(scope: GeoSelectedScope, bridge: XygGeoScaleBridge, request: ArrayBuffer, revision: bigint, token: typeof AUTHORITY);
    recover(): Promise<GeoSelectedState>;
    dispose(): Promise<void>;
}
export declare class GeoSelectedScope {
    #private;
    private owner;
    private bridge;
    constructor(bridge: XygGeoScaleBridge, handle: bigint, token: typeof AUTHORITY);
    get handle(): bigint;
    dispose(): Promise<void>;
    beginState(input: {
        revision: bigint;
        ids: BigUint64Array;
        fill: Uint8Array;
        budget: XygGeoQueryBudget;
    }, { nonce }?: {
        nonce?: bigint;
    }): GeoSelectedStateAttempt;
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
    constructor(bridge: XygGeoScaleBridge, handle: bigint, scope: GeoSelectedScope, token: typeof AUTHORITY, mutation?: GeoSelectedMutationAttempt, sceneIssuer?: ReturnType<typeof captureGeoSceneDataIssuer>);
    get handle(): bigint;
    check(): void;
    belongsTo(bridge: XygGeoScaleBridge): boolean;
    dispose(): Promise<void>;
    get pendingOperation(): GeoSelectedMutationAttempt | undefined;
    begin(input: {
        command: 35 | 36;
        handle: bigint;
        sequence: bigint;
        query: XygGeoScaleQuery;
        budget: XygGeoQueryBudget;
    }): Promise<SelectedMutationResult>;
}
type SelectedMutationResult = {
    fallback: true;
    reason: number;
    state: GeoSelectedState;
} | {
    fallback: false;
    operation: GeoSelectedOperation;
} | undefined;
export declare class GeoSelectedMutationAttempt {
    #private;
    constructor(state: GeoSelectedState, input: {
        command: 35 | 36;
        handle: bigint;
        sequence: bigint;
        query: XygGeoScaleQuery;
        budget: XygGeoQueryBudget;
    }, token: typeof AUTHORITY);
    recover(): Promise<SelectedMutationResult>;
    retire(): Promise<boolean>;
    dispose(): Promise<void>;
}
export declare class GeoSelectedOperation {
    #private;
    get publicationPending(): boolean;
    settleDrive(): Promise<void>;
    get handle(): bigint;
    get sequence(): bigint;
    get indexed(): boolean;
    get budget(): {
        processorBytes: number;
        maxRowsExamined: bigint;
        maxReadBytes: bigint;
        maxChunks: number;
        pageRows: number;
    };
    get scope(): GeoSelectedScope;
    constructor(bridge: XygGeoScaleBridge, handle: bigint, sequence: bigint, indexed: boolean, budget: XygGeoQueryBudget, scope: GeoSelectedScope, token: typeof AUTHORITY, mutation?: GeoSelectedMutationAttempt, sceneIssuer?: ReturnType<typeof captureGeoSceneDataIssuer>);
    drive(input: {
        readChunk?: (ticket: XygGeoReadTicket, signal?: AbortSignal) => Promise<ArrayBuffer | Uint8Array>;
        readPage?: (ticket: XygGeoReadTicket, signal?: AbortSignal) => Promise<ArrayBuffer | Uint8Array>;
        signal?: AbortSignal;
    }): Promise<unknown>;
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
                time: import("./geoscale.js").XygGeoTime;
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
/** Internal issued capability: captures original owner/transport, never public wire fields. */
export declare function claimGeoSelectedState(state: GeoSelectedState, bridge: XygGeoScaleBridge): {
    handle: bigint;
    reject(): void;
    consume(): void;
};
export {};
