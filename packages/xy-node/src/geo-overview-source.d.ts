import type { XygGeoScaleBridge, XygGeoQueryBudget, XygGeoScaleQuery } from './geoscale.js';
import type { GeoOverviewStorage } from './geo-overview.js';
export declare class GeoOverviewUncertainAllocation extends Error {
    readonly owner: GeoOverviewIndex | GeoOverviewQuery | GeoOverviewFrame;
    readonly cause: unknown;
    constructor(owner: GeoOverviewIndex | GeoOverviewQuery | GeoOverviewFrame, cause: unknown);
}
export declare class GeoOverviewCleanupPending extends Error {
    readonly owner: GeoOverviewIndex | GeoOverviewQuery | GeoOverviewFrame;
    readonly cause: unknown;
    constructor(owner: GeoOverviewIndex | GeoOverviewQuery | GeoOverviewFrame, cause: unknown);
}
export declare class GeoOverviewUnsupportedDomain extends Error {
    constructor();
}
export declare function overviewIndexAuthority(index: GeoOverviewIndex): Readonly<{
    bridge: XygGeoScaleBridge;
    budget: XygGeoQueryBudget;
    creationSequence: bigint;
    handle: bigint;
    closed: boolean;
    header: Uint8Array<ArrayBuffer>;
}> | undefined;
export declare function overviewFrameAuthority(frame: GeoOverviewFrame): Readonly<{
    bridge: XygGeoScaleBridge;
    index: GeoOverviewIndex;
    handle: bigint;
    sequence: bigint;
    query: ArrayBuffer;
    header: Uint8Array<ArrayBuffer>;
}> | undefined;
export interface GeoOverviewBuildInput extends GeoOverviewStorage {
    bridge: XygGeoScaleBridge;
    budget: XygGeoQueryBudget;
    maxVertices: bigint;
}
/** Independent immutable queries; there is no index-wide camera revision policy. */
export declare class GeoOverviewIndex {
    #private;
    private constructor();
    static fromFrame(frame: object, input: GeoOverviewBuildInput): Promise<GeoOverviewIndex>;
    get bridge(): XygGeoScaleBridge;
    get budget(): {
        processorBytes: number;
        maxRowsExamined: bigint;
        maxReadBytes: bigint;
        maxChunks: number;
        pageRows: number;
    };
    get creationSequence(): bigint;
    get current(): GeoOverviewFrame | undefined;
    get handle(): bigint;
    get closed(): boolean;
    get pendingOperation(): GeoOverviewIndex | GeoOverviewQuery | undefined;
    begin(query: XygGeoScaleQuery, { sequence }: {
        sequence: bigint;
    }): Promise<GeoOverviewQuery>;
    update(query: XygGeoScaleQuery, input: {
        sequence: bigint;
        signal?: AbortSignal;
    }, cap?: symbol): Promise<GeoOverviewFrame>;
    finished(op: GeoOverviewQuery, cap: symbol): void;
    dispose(): Promise<void>;
}
export declare class GeoOverviewQuery {
    #private;
    constructor(cap: symbol, index: GeoOverviewIndex, request: ArrayBuffer, sequence: bigint, storage: GeoOverviewStorage);
    get sequence(): bigint;
    get handle(): bigint;
    get uncertain(): boolean;
    admit(): Promise<void>;
    drive(signal?: AbortSignal): Promise<void>;
    prepare(signal?: AbortSignal): Promise<GeoOverviewFrame>;
    dispose(): Promise<void>;
}
export declare class GeoOverviewFrame {
    #private;
    constructor(cap: symbol, index: GeoOverviewIndex, sequence: bigint, query: ArrayBuffer);
    get sequence(): bigint;
    get handle(): bigint;
    get published(): boolean;
    get closed(): boolean;
    get uncertain(): boolean;
    get data(): {
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
    publish(queryHandle: bigint): Promise<void>;
    private issue;
    retain(): Promise<GeoOverviewFrame>;
    dispose(): Promise<void>;
}
/** Internal controller publication has independent ownership, without a public current alias. */
export declare function updateOverviewIndex(index: GeoOverviewIndex, query: XygGeoScaleQuery, input: {
    sequence: bigint;
    signal?: AbortSignal;
}): Promise<GeoOverviewFrame>;

import type {OwnedGeoArtifact} from './geo-snapshot.js';
export interface GeoOverviewFrame {export(format?:'svg'|'png'|'pdf'|'jpeg'|'webp'|'html',options?:{scale?:number;quality?:number;budget?:number}):Promise<OwnedGeoArtifact>;}
