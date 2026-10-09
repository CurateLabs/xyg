import type {
  XygGeoScaleBridge,
  XygGeoQueryBudget,
  XygGeoScaleQuery,
  XygGeoReadTicket,
} from "./geoscale.js";
export interface OwnedGeoData<T> {
  readonly handle: bigint;
  readonly data: T;
  dispose(): Promise<void>;
}
export interface OwnedGeoFrame<T> extends OwnedGeoData<T> {
  rows(): Promise<OwnedGeoRows>;
  spatialIndex(options: import("./geo-spatial.js").GeoSpatialStorage): Promise<import("./geo-spatial.js").GeoSpatialIndex>;
  readonly indexStats?: {pagesRead: bigint;bytesRead: bigint;candidateVertices: bigint;passes: number};
  export(
    format?: import("./geo-snapshot.js").GeoFrozenFormat,
    options?: import("./geo-snapshot.js").GeoFrozenExportOptions,
  ): Promise<import("./geo-snapshot.js").OwnedGeoArtifact>;
  membership(
    cell: number,
    options: { maxProjectedVertices: bigint; cursor?: Uint8Array },
  ): Promise<OwnedGeoData<GeoMembershipData>>;
  pick(options: {
    style: Uint8Array;
    x: number;
    y: number;
    tolerance: number;
    mode: 0 | 1;
    maxHits: number;
  }): Promise<OwnedGeoData<GeoPickData>>;
}
export interface GeoMembershipData {
  packet: ArrayBuffer;
  cell: number;
  count: bigint;
  cursor?: Uint8Array;
  key: Uint8Array;
  records: Uint8Array;
  projectedVertices: bigint;
  record(index: number): {
    featureId: bigint;
    sourceRow: bigint;
    chunkIndex: number;
    row: number;
  };
}
export declare function parseGeoMembershipData(
  packet: ArrayBuffer,
  owner: bigint,
  sequence: bigint,
): GeoMembershipData;
export declare class RetainedGeoSource {
  static create(
    manifest: ArrayBuffer | Uint8Array,
    readChunk: (
      ticket: XygGeoReadTicket,
      signal?: AbortSignal,
    ) => Promise<ArrayBuffer | Uint8Array>,
    options: { budget: XygGeoQueryBudget; bridge?: XygGeoScaleBridge },
  ): Promise<RetainedGeoSource>;
  readonly handle: bigint;
  readonly info: {
    generation: bigint;
    digest: Uint8Array;
    rows: bigint;
    geometry: number;
    crs: number;
  };
  readonly current?: OwnedGeoFrame<
    ReturnType<typeof import("./geoscale.js").parseGeoSceneData>
  >;
  update(
    query: XygGeoScaleQuery,
    options: { sequence: bigint; style: Uint8Array; signal?: AbortSignal },
  ): Promise<
    OwnedGeoFrame<ReturnType<typeof import("./geoscale.js").parseGeoSceneData>>
  >;
  membership(
    cell: number,
    options: {
      sequence: bigint;
      maxProjectedVertices: bigint;
      cursor?: Uint8Array;
    },
  ): Promise<OwnedGeoData<GeoMembershipData>>;
  cancel(): Promise<void>;
  dispose(): Promise<void>;
}
export interface GeoPickData {
  packet: ArrayBuffer;
  count: bigint;
  key: Uint8Array;
  record(index: number): {
    tag: number;
    vertex: number;
    featureId: bigint;
    sourceRow: bigint;
    chunkIndex: number;
    row: number;
    cell: number;
    count: bigint;
  };
}
export declare function parseGeoPickData(
  packet: ArrayBuffer,
  owner: bigint,
  sequence: bigint,
): GeoPickData;
export interface RetainedGeoSource {
  pick(options: {
    sequence: bigint;
    style: Uint8Array;
    x: number;
    y: number;
    tolerance: number;
    mode: 0 | 1;
    maxHits: number;
  }): Promise<OwnedGeoData<GeoPickData>>;
}

export interface OwnedGeoRows extends OwnedGeoData<GeoRowsData> {
  nextPage(): Promise<OwnedGeoRows>;
}
export type GeoRowsData = ReturnType<typeof import("./geoscale.js").parseGeoRowsData> & {
  records: Uint8Array;
  stats: { rowsExamined: bigint; bytesRead: bigint; chunksRead: number; chunksConsidered: number };
};
