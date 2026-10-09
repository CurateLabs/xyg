export interface GeoSnapshotBridge {
  execute(request: ArrayBuffer): Promise<ArrayBuffer>;
  read(request: ArrayBuffer): Promise<ArrayBuffer>;
}
export interface OwnedGeoArtifact {
  readonly handle: bigint;
  readonly format: GeoFrozenFormat;
  readonly bytes: ArrayBuffer;
  readonly snapshot: ArrayBuffer;
  dispose(): Promise<void>;
}
export type GeoFrozenFormat = "svg" | "png" | "pdf" | "jpeg" | "webp" | "html";
export interface GeoFrozenExportOptions {
  scale?: number;
  quality?: number;
  budget?: number;
  bridge?: GeoSnapshotBridge;
  signal?: AbortSignal;
}
export declare class GeoSnapshotError extends Error {
  readonly status: number;
  readonly code: string;
}
export declare function encodeGeoSnapshotRequest(
  command: number,
  handle: bigint,
  options?: {
    sequence?: bigint;
    budget?: number;
    format?: GeoFrozenFormat;
    scale?: number;
    quality?: number;
  },
): ArrayBuffer;
export declare function decodeGeoSnapshotReply(packet: ArrayBuffer): {
  handle: bigint;
  sequence: bigint;
  length: number;
  companion: number;
  kind: number;
};
export declare function geoSnapshotExecute(
  request: ArrayBuffer,
): Promise<ArrayBuffer>;
export declare function geoSnapshotRead(
  request: ArrayBuffer,
  budget: number,
): Promise<ArrayBuffer>;
export declare function nativeGeoSnapshotBridge(
  budget: number,
): GeoSnapshotBridge;
export declare function exportGeoFrame(
  frame: { readonly handle: bigint; readonly data: unknown },
  sequence: bigint,
  format?: GeoFrozenFormat,
  options?: GeoFrozenExportOptions,
): Promise<OwnedGeoArtifact>;
