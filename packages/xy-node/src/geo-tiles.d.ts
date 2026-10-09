import type {
  GeoSnapshotBridge,
  GeoFrozenFormat,
  GeoFrozenExportOptions,
  OwnedGeoArtifact,
} from "./geo-snapshot.js";
export interface GeoTileConfig {
  sourceId: bigint;
  generation: bigint;
  layerId: bigint;
  layerRevision: bigint;
  styleRevision: bigint;
  kind: 0 | 1;
  minZoom: number;
  maxZoom: number;
  maxBytes: bigint;
  maxFeatures: bigint;
  maxVertices: bigint;
  locator: string;
  attribution: string;
  network: boolean;
  time?: { start: bigint; end: bigint };
}
export interface GeoTileKey {
  sourceId: bigint;
  generation: bigint;
  layerId: bigint;
  layerRevision: bigint;
  styleRevision: bigint;
  kind: 0 | 1;
  z: number;
  x: number;
  y: number;
  time?: { start: bigint; end: bigint };
}
export interface GeoTileReadReceipt {
  packet: ArrayBuffer;
  handle: bigint;
  epoch: bigint;
  maxBytes: number;
  ticket: Uint8Array;
  key: GeoTileKey;
  location: number;
  locator: string;
  attribution: string;
}
export interface GeoTileFrameData {
  packet: ArrayBuffer;
  epoch: bigint;
  cache: bigint;
  view: bigint;
  catalog: ReturnType<
    typeof import("./geocatalog.js").decodeGeoCatalogResponse
  >;
  scene: ArrayBuffer;
  keys: GeoTileKey[];
  attributions: string[];
}
export interface OwnedTileFrame {
  readonly handle: bigint;
  readonly epoch: bigint;
  readonly data: GeoTileFrameData;
  commit(): Promise<void>;
  dispose(): Promise<void>;
  export(
    format?: GeoFrozenFormat,
    options?: GeoFrozenExportOptions,
  ): Promise<OwnedGeoArtifact>;
}
export declare class GeoTileSource {
  constructor(config: GeoTileConfig);
  readonly config: GeoTileConfig;
  encode(): Uint8Array;
}
export interface GeoTileBridge {
  execute(request: ArrayBuffer): Promise<ArrayBuffer>;
  read(request: ArrayBuffer): Promise<ArrayBuffer>;
}
export interface GeoTilePreparation {
  catalog: ArrayBuffer | Uint8Array;
  vectorStyles: {
    layerId: bigint;
    kind: number;
    style:
      | Uint8Array
      | Parameters<typeof import("./geoscale.js").encodeGeoScaleStyle>[0];
  }[];
  imageId: bigint;
}
export declare class GeoTileSession {
  static create(
    sources: GeoTileSource[],
    reader: (
      receipt: GeoTileReadReceipt,
      signal: AbortSignal,
    ) => Promise<ArrayBuffer | Uint8Array>,
    options: { viewId: bigint; budget: number; bridge?: GeoTileBridge },
  ): Promise<GeoTileSession>;
  readonly handle: bigint;
  readonly current?: OwnedTileFrame;
  readonly sources: readonly GeoTileSource[];
  prepare(
    camera: Parameters<
      typeof import("./geoviewport.js").encodeGeoViewportRequest
    >[0],
    options: GeoTilePreparation,
  ): Promise<OwnedTileFrame>;
  update(
    camera: Parameters<
      typeof import("./geoviewport.js").encodeGeoViewportRequest
    >[0],
    options: GeoTilePreparation & {
      stage: (frame: OwnedTileFrame, signal: AbortSignal) => Promise<void>;
    },
  ): Promise<OwnedTileFrame>;
  cancel(): Promise<void>;
  dispose(): Promise<void>;
}
export declare function encodeGeoTileRequest(
  command: number,
  handle?: bigint,
  options?: {
    epoch?: bigint;
    view?: bigint;
    budget?: number;
    payload?: ArrayBuffer | Uint8Array;
  },
): ArrayBuffer;
export declare function geoTileExecute(
  request: ArrayBuffer,
): Promise<ArrayBuffer>;
export declare function geoTileRead(
  request: ArrayBuffer,
  budget: number,
): Promise<ArrayBuffer>;
export declare function nativeGeoTileBridge(budget: number): GeoTileBridge;
export declare function decodeGeoTileReadReceipt(
  packet: ArrayBuffer,
  handle: bigint,
  epoch: bigint,
): GeoTileReadReceipt;
export declare function decodeGeoTileFrame(
  packet: ArrayBuffer,
): GeoTileFrameData;
export declare function httpTileLoader(
  receipt: GeoTileReadReceipt,
  signal?: AbortSignal,
): Promise<Uint8Array>;

export declare function encodeGeoTileBegin(camera:Parameters<typeof import('./geoviewport.js').encodeGeoViewportRequest>[0],sources:GeoTileSource[]):Uint8Array;
export declare function encodeGeoTilePrepare(catalog:ArrayBuffer|Uint8Array,styles:GeoTilePreparation['vectorStyles'],imageId:bigint):Uint8Array;
