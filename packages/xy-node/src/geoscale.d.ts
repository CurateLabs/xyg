/** Thin XYGQ/XYGZ source-session framing. All geographic policy remains in Rust. */
export interface XygGeoCamera {crs:number;worldWrap?:boolean;centerX:number;centerY:number;zoom:number;width:number;height:number;bearing?:number;pitch?:number}
export declare const GEO_SCALE_HEADER = 256;
export interface XygGeoQueryBudget {
    processorBytes: number;
    maxRowsExamined: bigint;
    maxReadBytes: bigint;
    maxChunks: number;
    pageRows: number;
}
export type XygGeoTime = {
    kind: 0;
} | {
    kind: 1;
    instant: bigint;
} | {
    kind: 2;
    start: bigint;
    end: bigint;
};
export interface XygGeoScaleQuery {
    camera: Required<XygGeoCamera>;
    reducedKind: number;
    maxCells: number;
    previousDirect: boolean;
    sourceDigest: Uint8Array;
    generation: bigint;
    layerId: bigint;
    cameraRevision: bigint;
    timeRevision: bigint;
    layerRevision: bigint;
    styleRevision: bigint;
    stateRevision: bigint;
    time: XygGeoTime;
    maxProjectedVertices: bigint;
}
export interface XygGeoScaleRequest {
    command: number;
    handle?: bigint;
    sequence?: bigint;
    budget?: XygGeoQueryBudget;
    generation?: bigint;
    query?: XygGeoScaleQuery;
    payload?: ArrayBuffer | Uint8Array;
}
export interface XygGeoScaleBridge {
    execute(request: ArrayBuffer): Promise<ArrayBuffer>;
    read(request: ArrayBuffer): Promise<ArrayBuffer>;
}
/** Borrow full XYSE intent. Fingerprints are hints; exact typed IDs are retained. */
export declare function parseGeoSelectionFooter(packet: Uint8Array, at: number, rows: boolean): {
    raw: Uint8Array<ArrayBufferLike>;
    namespace: bigint;
    fill: Uint8Array<ArrayBufferLike>;
    idCount: number;
    cellCount: number;
    visibleVertices: bigint | null;
    id(index: number): bigint;
    cell(index: number): bigint;
} | null;
export declare function encodeGeoScaleRequest(input: XygGeoScaleRequest): ArrayBuffer;
export declare function encodeGeoScaleStyle(style: {
    fill: Uint8Array;
    stroke: Uint8Array;
    strokeWidth: number;
    diameter: number;
    opacity: number;
    symbol: number;
}): Uint8Array;
export interface XygGeoReadTicket {
    raw: Uint8Array;
    kind: number;
    page: bigint;
    sessionId: bigint;
    readId: bigint;
    sequence: bigint;
    pass: number;
    generation: bigint;
    chunkIndex: number;
    rows: number;
    firstRow: bigint;
    encodedBytes: number;
    digest: Uint8Array;
}
export declare function decodeGeoScaleReply(buffer: ArrayBuffer): {
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
};
export declare function encodeGeoChunkRequest(input: {
    descriptor: ArrayBuffer | Uint8Array;
    rows: number;
    intervals?: {
        starts: BigInt64Array;
        ends: BigInt64Array;
        startValidity: Uint8Array;
        endValidity: Uint8Array;
    };
    values?: Float64Array;
}, budget: number): ArrayBuffer;
/** Views borrow packet storage; consumers must drop every view/copy before lease disposal. */
export declare function parseGeoSceneData(packet: ArrayBuffer): {
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
        time: XygGeoTime;
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
/** Service only Rust-issued reads. Caller begins/validates the source explicitly. */
export declare function driveGeoSession(bridge: XygGeoScaleBridge, input: {
    handle: bigint;
    sequence: bigint;
    budget: XygGeoQueryBudget;
    readChunk: (ticket: XygGeoReadTicket, signal?: AbortSignal) => Promise<ArrayBuffer | Uint8Array>;
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
export declare function geoSceneDataAuthority(owner: object): Readonly<{
    bridge: XygGeoScaleBridge;
    execute: XygGeoScaleBridge["execute"];
    read: XygGeoScaleBridge["read"];
    handle: bigint;
    sequence: bigint;
    sourceHandle: bigint;
    selected: boolean;
    request: ArrayBuffer;
    header: Uint8Array<ArrayBuffer>;
}> | undefined;
export declare function prepareGeoSceneData(bridge: XygGeoScaleBridge, input: {
    handle: bigint;
    sequence: bigint;
    budget: XygGeoQueryBudget;
} & ({
    command: 26;
    style?: never;
} | {
    command?: 11 | 19;
    style: Uint8Array;
})): Promise<{
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
            time: XygGeoTime;
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
/** Raw immutable key/cursor bytes retain Rust's exact f64/i64/u64 identity. */
export declare function parseGeoMembershipData(packet: ArrayBuffer): {
    packet: ArrayBuffer;
    key: Uint8Array<ArrayBuffer>;
    cursor: Uint8Array<ArrayBuffer> | null;
    length: number;
    cell: number;
    owner: bigint;
    sequence: bigint;
    record(index: number): {
        featureId: bigint;
        sourceRow: bigint;
        chunkIndex: number;
        chunkRow: number;
    };
};
export declare function parseGeoHitData(packet: ArrayBuffer): {
    packet: ArrayBuffer;
    key: Uint8Array<ArrayBuffer>;
    length: number;
    owner: bigint;
    sequence: bigint;
    record(index: number): {
        featureId?: undefined;
        sourceRow?: undefined;
        chunkIndex?: undefined;
        chunkRow?: undefined;
        vertex?: undefined;
        kind: 'cell';
        cell: number;
        count: bigint;
    } | {
        count?: undefined;
        cell?: undefined;
        kind: 'direct';
        vertex: number;
        featureId: bigint;
        sourceRow: bigint;
        chunkIndex: number;
        chunkRow: number;
    };
};
/** Data readers bind a fixed mutation reply, never probe/re-execute mutations. */
export declare function parseGeoRowsData(packet: ArrayBuffer): {
    packet: ArrayBuffer;
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
    length: number;
    hasNext: boolean;
    owner: bigint;
    sequence: bigint;
    key: Uint8Array<ArrayBuffer>;
    record(index: number): {
        featureId: bigint;
        sourceRow: bigint;
        chunkIndex: number;
        chunkRow: number;
        selected: boolean;
        geometryNull: boolean;
        timeEligible: boolean;
        eligible: boolean;
        intervalsPresent: boolean;
        intervalStart: bigint | null;
        intervalEnd: bigint | null;
        value: number | null;
    };
};
export declare function prepareGeoAuxData<T>(bridge: XygGeoScaleBridge, input: {
    command: 13 | 14 | 16;
    handle: bigint;
    sequence: bigint;
    budget: XygGeoQueryBudget;
    payload?: Uint8Array;
}, parse: (packet: ArrayBuffer) => T): Promise<{
    handle: bigint;
    readonly data: T & ({} | null);
    dispose(): Promise<void>;
}>;
/** Drive the shared index state machine; external immutable sidecar storage is
 * explicit. Storage callbacks must bound their cache and settle before ACK. */
export declare function driveGeoIndexSession(bridge: XygGeoScaleBridge, input: {
    handle: bigint;
    sequence: bigint;
    budget: XygGeoQueryBudget;
    readChunk?: (ticket: XygGeoReadTicket, signal?: AbortSignal) => Promise<ArrayBuffer | Uint8Array>;
    readPage?: (ticket: XygGeoReadTicket, signal?: AbortSignal) => Promise<ArrayBuffer | Uint8Array>;
    writePage?: (ticket: XygGeoReadTicket, bytes: Uint8Array, signal?: AbortSignal) => Promise<void>;
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
export declare function geoScaleExecute(request:ArrayBuffer|Uint8Array):Promise<ArrayBuffer>;
export declare function geoScaleRead(request:ArrayBuffer|Uint8Array,budget:number):Promise<ArrayBuffer>;
export declare function nativeGeoScaleBridge(budget:number):XygGeoScaleBridge;
