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
export interface GeoMountedTemporalBinding {
 /** Last operation error. The accepted picture stays authoritative on failure. */
 readonly error:Error|undefined;
 whenIdle():Promise<void>;
 /** Detach and drain the exact active transaction; the mounted picture survives. */
 dispose():Promise<void>;
}
export interface GeoWebviewHost {
 readonly mounted:boolean;
 bindTemporal(handle:bigint,mode?:'cursor'|'range'):GeoMountedTemporalBinding;
 reload(html:string):Promise<void>;
 dispose():Promise<void>;
}
/** Caller supplies resource-local CSP HTML and an actual VS Code panel. */
export declare function attachGeoWebview(panel:unknown,adapter:GeoHostAdapter):GeoWebviewHost;
