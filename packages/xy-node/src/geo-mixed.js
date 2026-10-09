/** Native mixed-frame transport. Rust owns source/tile authority and composition. */
import { geoTileExecute, geoTileRead } from './geo-tiles.js';
import { exportGeoFrame } from './geo-snapshot.js';
import { encodeGeoMixedRequest, decodeGeoMixedReply, prepareGeoMixedData } from './geo-mixed-wire.js';
export { encodeGeoMixedRequest, decodeGeoMixedReply, parseGeoMixedData, parseGeoMixedTileDescriptor } from './geo-mixed-wire.js';
export function nativeGeoMixedBridge(budget) {
  if (!Number.isSafeInteger(budget) || budget < 65536 || budget > 128*1024*1024) throw new RangeError('invalid mixed budget');
  return {execute:geoTileExecute,read:request=>geoTileRead(request,budget)};
}
export async function prepareGeoMixedCandidate(input, {bridge=nativeGeoMixedBridge(input.budget)}={}) {
  const budget=input.budget;
  const frame=await prepareGeoMixedData(bridge,input);
  return {
    handle:frame.handle,nonce:frame.nonce,_freezeCommand:5,
    get data(){return frame.data;},commit:()=>frame.commit(),cancel:()=>frame.cancel(),dispose:()=>frame.dispose(),
    async retainSourceAuthority(){void frame.data;return decodeGeoMixedReply(await bridge.execute(encodeGeoMixedRequest({command:6,handle:frame.handle,nonce:frame.nonce,budget})));},
    export(format='png',options={}){void frame.data;if(bridge.execute!==geoTileExecute&&!options.bridge)throw new TypeError('remote mixed frame requires matching snapshot bridge');return exportGeoFrame(this,frame.nonce,format,options);},
  };
}
