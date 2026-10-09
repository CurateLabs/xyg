import type {OwnedGeoFrame} from '../src/geo-retained.js';
import {GeoSpatialFullScanRequired} from '../src/geo-spatial.js';
import type {GeoSpatialIndex} from '../src/geo-spatial.js';
import type {XygGeoScaleQuery} from '../src/geoscale.js';
async function use(frame: OwnedGeoFrame<unknown>, query: XygGeoScaleQuery) {
  const index: GeoSpatialIndex = await frame.spatialIndex({grid:16,maxVertices:1000000n,
    readPage: async ticket => new ArrayBuffer(ticket.encodedBytes),
    writePage: async (ticket,bytes) => { const page: bigint=ticket.page;void page;void bytes; }});
  const next = await index.update(query,{sequence:2n,style:new Uint8Array(48)});
  const count: bigint|undefined=next.indexStats?.pagesRead;
  void count;await next.dispose();await index.dispose();
}
void use;
try { throw new Error('example'); } catch(error) { if(error instanceof GeoSpatialFullScanRequired){const reason: 1|2=error.reasonCode;void reason;} }
