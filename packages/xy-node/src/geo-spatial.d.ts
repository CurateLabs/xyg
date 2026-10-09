import type {XygGeoReadTicket, XygGeoScaleQuery} from './geoscale.js';
import type {RetainedGeoSource, OwnedGeoFrame} from './geo-retained.js';
export interface GeoSpatialStorage {
  grid: number;
  maxVertices: bigint;
  readPage(ticket: XygGeoReadTicket, signal?: AbortSignal): Promise<ArrayBuffer | Uint8Array>;
  /** Persist exact bytes; settle and drop borrowed views before returning. */
  writePage(ticket: XygGeoReadTicket, bytes: Uint8Array, signal?: AbortSignal): Promise<void>;
  signal?: AbortSignal;
}
export declare class GeoSpatialFullScanRequired extends Error { readonly reasonCode: 1 | 2; }
export declare class GeoSpatialIndex extends RetainedGeoSource {
  readonly pageCount: bigint;
  update(query: XygGeoScaleQuery, options: {sequence: bigint;style: Uint8Array;signal?: AbortSignal}): Promise<OwnedGeoFrame<ReturnType<typeof import('./geoscale.js').parseGeoSceneData>>>;
}
