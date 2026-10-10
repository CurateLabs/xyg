import type {GeoOverviewFrame} from './geo-overview-source.js';
import type {OwnedGeoFrame} from './geo-retained.js';
import type {GeoSelectedScope} from './geo-selected.js';
import type {GeoHierarchy} from './geo-hierarchy.js';
import type {parseGeoSceneData} from './geoscale.js';
export interface GeoNativeHostOptions {
 /** Caller retains ownership; the adapter independently retains one private anchor. */
 frame?:OwnedGeoFrame<ReturnType<typeof parseGeoSceneData>>|GeoOverviewFrame;
 selectedScope?:GeoSelectedScope;
 /** Explicit caller-owned selected lane. Exclusively claimed until adapter cleanup. */
 hierarchyLane?:GeoHierarchy;
}
export declare class GeoHostAdapter {
 constructor(chart:unknown,options?:GeoNativeHostOptions);
 readonly mounted:boolean;
 readonly anchorReady:Promise<void>;
 open(mount:string):Promise<ArrayBuffer[]>;
 handle(message:unknown,buffers?:ArrayBuffer[]):Promise<unknown>;
 close():void;
 realmDestroyed():Promise<void>;
}
/** Caller supplies resource-local CSP HTML and an actual VS Code panel. */
export declare function attachGeoWebview(panel:unknown,adapter:GeoHostAdapter):unknown;
