import type {XygGeoScaleQuery} from '../src/geoscale.js';
const camera={crs:4326,centerX:0,centerY:0,zoom:0,width:800,height:600,worldWrap:true,bearing:0,pitch:0};
const explicit:XygGeoScaleQuery['camera']=camera;
// @ts-expect-error The transport requires explicit wrap, bearing and pitch.
const missing:XygGeoScaleQuery['camera']={crs:4326,centerX:0,centerY:0,zoom:0,width:800,height:600};
void explicit;void missing;
