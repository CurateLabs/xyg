import type { XygGeoScaleBridge, XygGeoQueryBudget } from './geoscale.js';
interface Context {
    handle: bigint;
    sequence: bigint;
    transport: XygGeoScaleBridge;
    reader: (ticket: Record<string, unknown>, signal?: AbortSignal) => Promise<ArrayBuffer | Uint8Array>;
    budget: XygGeoQueryBudget;
    header: Uint8Array;
}
export declare function registerOverviewMembers(frame: object, transport: XygGeoScaleBridge, reader: Context['reader'], budget: XygGeoQueryBudget, header: Uint8Array, handle: bigint, sequence: bigint): void;
export declare function copyOverviewMembers(from: object, to: object, handle: bigint, sequence: bigint): void;
export declare function dropOverviewMembers(frame: object): void;
export declare function encodeOverviewMembersRequest(command: number, handle: bigint, sequence: bigint, budget?: XygGeoQueryBudget, payload?: Uint8Array): ArrayBuffer;
export declare function decodeOverviewMembersReply(packet: ArrayBuffer): {
    code: number;
    handle: bigint;
    sequence: bigint;
    dataLength: bigint;
    sourceHandle: bigint;
    ticket: Uint8Array<ArrayBufferLike> | null;
    raw: Uint8Array<ArrayBuffer>;
};
export declare class GeoOverviewMembershipUncertain extends Error {
    readonly owner: GeoOverviewMembershipOperation;
    readonly cause: unknown;
    constructor(owner: GeoOverviewMembershipOperation, cause: unknown);
}
export declare class GeoOverviewMembershipCleanupPending extends Error {
    readonly owner: GeoOverviewMembershipOperation | GeoOverviewMembershipPage;
    readonly cause: unknown;
    constructor(owner: GeoOverviewMembershipOperation | GeoOverviewMembershipPage, cause: unknown);
}
export declare class GeoOverviewMembershipPublicationPending extends Error {
    readonly owner: GeoOverviewMembershipOperation;
    readonly cause: unknown;
    constructor(owner: GeoOverviewMembershipOperation, cause: unknown);
}
export interface GeoOverviewMembersInput {
    sequence: bigint;
    maxVertices: bigint;
    signal?: AbortSignal;
}
export declare function overviewMembers(frame: object, cell: number, input: GeoOverviewMembersInput): Promise<GeoOverviewMembershipPage>;
export declare class GeoOverviewMembershipOperation {
    #private;
    constructor(cap: symbol, c: Context, cell: number, sequence: bigint, prior: bigint, after: bigint);
    get retryablePublication(): boolean;
    get handle(): bigint;
    get sequence(): bigint;
    get uncertain(): boolean;
    get closed(): boolean;
    admit(request: ArrayBuffer): Promise<void>;
    drive(signal?: AbortSignal): Promise<void>;
    prepare(signal?: AbortSignal): Promise<GeoOverviewMembershipPage>;
    dispose(): Promise<void>;
}
export interface GeoOverviewMemberRecord {
    featureId: bigint;
    sourceRow: bigint;
    chunkIndex: number;
    row: number;
    matchedVertices: bigint;
}
export declare class GeoOverviewMembershipPage {
    #private;
    constructor(cap: symbol, c: Context, handle: bigint, sequence: bigint, cell: number, prior: bigint, packet: ArrayBuffer, completion?: Uint8Array, after?: bigint);
    get handle(): bigint;
    get sequence(): bigint;
    get count(): number;
    get hasNext(): boolean;
    get cumulativeVertices(): bigint;
    get cell(): number;
    get temporalExact(): boolean;
    get dataSpace(): boolean;
    get final(): boolean;
    copyBytes(): Uint8Array<ArrayBuffer>;
    record(i: number): GeoOverviewMemberRecord;
    nextPage(input: GeoOverviewMembersInput): Promise<GeoOverviewMembershipPage>;
    dispose(): Promise<void>;
}
export declare function parseOverviewMembers(packet: ArrayBuffer, header: Uint8Array, handle: bigint, sequence: bigint, cell: number, prior: bigint, completion?: Uint8Array, after?: bigint): {
    count: number;
    hasNext: boolean;
    cumulative: bigint;
    lastRow: bigint;
};
export {};
