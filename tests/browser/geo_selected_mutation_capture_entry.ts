// Test-only bundle: genuine Worker and selected private provenance share one module instance.
export {createXygWasmWorker,beginGeoWorkerMutationCapture,withGeoWorkerMutationOutcome} from '../../js/src/47_wasm';
export {createGeoSelectedScope,claimGeoSelectedState} from '../../js/src/68_geo_selected';
export {encodeGeoScaleRequest,decodeGeoScaleReply,encodeGeoChunkRequest,encodeGeoScaleStyle,driveGeoSession,driveGeoIndexSession,prepareGeoSceneData} from '../../js/src/63_geo_source';
