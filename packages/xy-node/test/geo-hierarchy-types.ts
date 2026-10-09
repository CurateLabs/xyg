import {GeoHierarchy,type GeoHierarchyStorage,isHierarchyFrame} from '../src/geo-hierarchy.js';
import type {RetainedGeoSource,OwnedGeoFrame} from '../src/geo-retained.js';
import type {parseGeoSceneData} from '../src/geoscale.js';
declare const source:RetainedGeoSource;
declare const frame:OwnedGeoFrame<ReturnType<typeof parseGeoSceneData>>;
const storage:GeoHierarchyStorage={grid:1024,maxVertices:1000000n,maxWriteBytes:64n<<20n,readPage:t=>new Uint8Array(t.encodedBytes),writePage:(t,b)=>{const key:[bigint,bigint]=[t.namespace,t.page];void key;void b;}};
void GeoHierarchy.fromFrame(frame,source,storage);
void isHierarchyFrame(frame);
// @ts-expect-error cumulative external byte budget is exact u64
storage.maxWriteBytes=1024;
