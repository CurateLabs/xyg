/** Controller scheduling and DOM ownership only; Rust supplies every Scene. */
import { hydrateWasmPainter } from './48_wasm_scene';
import type { XygWasmSceneView } from './48_wasm_scene';
import type { XygWasmScenePaint } from './47_wasm';
import type { XygTemporalState, XygWasmTemporalController } from './49_wasm_temporal';

type TimeState=Readonly<{rangeStart:bigint;rangeEnd:bigint;cursor:bigint}>;
export interface TemporalCompositionControllerBinding {
  readonly view:XygWasmSceneView|null;
  readonly error:unknown;
  /** Accepted temporal metadata; the binding owns the returned view's lifetime. */
  snapshot():TimeState|null;
  /** Settle the current attempt; resource refusal rejects until readmission. */
  whenIdle():Promise<void>;
  /** Retry the latest state; an admitted pending painter keeps its identity. */
  refresh():Promise<void>;
  dispose():Promise<void>;
}

export function attachTemporalControllerView(
  controller:XygWasmTemporalController,
  options:{el:HTMLElement;onError?:(error:unknown)=>unknown},
  compile:(state:TimeState)=>Promise<XygWasmScenePaint>,
  cancel:()=>void,
  released:()=>void,
):TemporalCompositionControllerBinding {
  if(!options||!(options.el instanceof HTMLElement)||options.el.ownerDocument!==document)throw new TypeError('a temporal mount element in this document is required');
  if(options.onError!==undefined&&typeof options.onError!=='function')throw new TypeError('onError must be a function');
  if(!controller||controller.state.disposed||typeof controller.subscribeState!=='function')throw new Error('a live temporal controller is required');
  const container=document.createElement('div');container.style.position='relative';container.setAttribute('role','group');container.setAttribute('aria-label','Temporal composition');
  const status=document.createElement('div');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  Object.assign(status.style,{position:'absolute',width:'1px',height:'1px',overflow:'hidden',clipPath:'inset(50%)'});container.appendChild(status);
  let attached=true,epoch=0,key:string|null=null,pending:TimeState|null=null,pumping=false;
  let running:Promise<void>=Promise.resolve(),disposal:Promise<void>|null=null;
  let current:XygWasmSceneView|null=null,currentMount:HTMLElement|null=null,last:TimeState|null=null,error:unknown=null,failed=false;
  type Candidate={view:XygWasmSceneView;mount:HTMLElement;state:TimeState;epoch:number;restored:()=>void};
  let staged:Candidate|null=null;
  const report=(cause:unknown)=>{error=cause;failed=true;const attempt=epoch;void Promise.resolve().then(()=>{if(attached&&failed&&error===cause&&epoch===attempt)options.onError?.(cause);}).catch(()=>{});};
  const dropStage=()=>{if(staged){const old=staged;staged=null;old.view.root.removeEventListener('xy:context_restored',old.restored);old.view.destroy();old.mount.remove();}};
  const publish=()=>{
    const next=staged;if(!next||!attached||next.epoch!==epoch)return false;
    const view=next.view;
    if(!view.gl||view._glLost||view.gl.isContextLost()||(view._glHost&&!view._glHost.clientAdmitted(view))||view._drawNow()===false)return false;
    view._assertContextFrameReady('temporal publication');
    if(!attached||next!==staged||next.epoch!==epoch)return false;
    view.root.removeEventListener('xy:context_restored',next.restored);
    const old=current,oldMount=currentMount;
    next.mount.removeAttribute('style');next.mount.removeAttribute('aria-hidden');next.mount.inert=false;
    current=view;currentMount=next.mount;last=Object.freeze({...next.state});staged=null;error=null;failed=false;
    old?.destroy();oldMount?.remove();container.setAttribute('aria-busy','false');
    status.textContent=`Cursor ${last.cursor}; range ${last.rangeStart} to ${last.rangeEnd}.`;
    return true;
  };
  const accept=(snapshot:XygTemporalState,force=false)=>{
    if(!attached)return;
    if(snapshot.disposed){void dispose().catch(report);return;}
    const state={rangeStart:snapshot.rangeStart,rangeEnd:snapshot.rangeEnd,cursor:snapshot.cursor};
    const next=`${state.rangeStart}/${state.rangeEnd}/${state.cursor}`;
    if(!force&&key===next)return;
    key=next;pending=state;epoch++;cancel();dropStage();container.setAttribute('aria-busy','true');
    if(pumping)return;
    pumping=true;
    running=Promise.resolve().then(async()=>{
      try{
        while(attached&&pending){
          const state=pending,attempt=epoch;pending=null;
          let candidate:XygWasmSceneView|null=null,mount:HTMLElement|null=null;
          try{
            const prepared=await compile(state);
            if(!attached||attempt!==epoch)continue;
            // A connected inert stage resolves CSS and retains its GLHost
            // identity while the existing Rust budget coordinator admits it.
            mount=document.createElement('div');mount.inert=true;mount.setAttribute('aria-hidden','true');
            Object.assign(mount.style,{position:'absolute',left:'0',top:'0',width:'100%',opacity:'0',pointerEvents:'none'});container.appendChild(mount);
            candidate=hydrateWasmPainter(mount,prepared);
            if(!attached||attempt!==epoch)continue;
            const entry:Candidate={view:candidate,mount,state,epoch:attempt,restored:()=>{
              try{publish();}catch(cause){if(attached&&staged===entry)report(cause);}
            }};
            staged=entry;candidate=null;mount=null;
            entry.view.root.addEventListener('xy:context_restored',entry.restored);
            if(!publish())throw new Error('temporal Scene awaits GPU admission or context restoration');
          }catch(cause){
            if(attached&&attempt===epoch){report(cause);container.setAttribute('aria-busy','false');status.textContent=last?'Temporal update failed; previous view retained.':'Temporal view is not ready.';}
          }finally{candidate?.destroy();mount?.remove();}
        }
      }finally{pumping=false;}
    });
  };
  let unsubscribe:()=>void=()=>{};
  const dispose=()=>{
    if(disposal)return disposal;
    attached=false;epoch++;pending=null;unsubscribe();cancel();dropStage();
    return disposal=running.finally(()=>{try{current?.destroy();current=null;currentMount=null;container.remove();}finally{released();}});
  };
  const idle=async()=>{for(;;){const observed=running;await observed;if(observed===running){if(failed)throw error;return;}}};
  try{options.el.appendChild(container);unsubscribe=controller.subscribeState(accept);accept(controller.state);}
  catch(cause){attached=false;epoch++;pending=null;unsubscribe();cancel();dropStage();container.remove();throw cause;}
  return Object.freeze({get view(){return current;},get error(){return error;},snapshot:()=>last===null?null:Object.freeze({...last}),whenIdle:idle,
    refresh:()=>{if(!attached)return Promise.reject(new Error('temporal attachment disposed'));if(staged){try{publish();}catch(cause){report(cause);}return idle();}accept(controller.state,true);return idle();},dispose});
}
