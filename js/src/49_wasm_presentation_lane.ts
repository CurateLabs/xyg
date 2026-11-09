/** Cooperating presentation transactions assign Worker sequences on entry.
 * Scene transactions exclude plans; bounded pure plans may overlap each other
 * so an older delayed reply cannot block a newer budget intent. */
type Job={read:boolean;run:()=>Promise<unknown>;resolve:(value:unknown)=>void;reject:(cause:unknown)=>void};
type Lane={writer:boolean;readers:number;queue:Job[]};
const lanes=new WeakMap<object,Lane>();
function enter<T>(worker:object,read:boolean,operation:()=>Promise<T>):Promise<T>{
  let lane=lanes.get(worker);if(!lane){lane={writer:false,readers:0,queue:[]};lanes.set(worker,lane);}
  const state=lane;
  const drain=()=>{
    if(state.writer)return;
    while(state.queue.length){
      const next=state.queue[0];if(!next.read&&state.readers)return;
      state.queue.shift();if(next.read)state.readers++;else state.writer=true;
      const release=()=>{if(next.read)state.readers--;else state.writer=false;drain();if(!state.writer&&!state.readers&&!state.queue.length&&lanes.get(worker)===state)lanes.delete(worker);};
      void Promise.resolve().then(next.run).then(value=>{next.resolve(value);release();},cause=>{next.reject(cause);release();});
      if(!next.read)return;
    }
  };
  return new Promise<T>((resolve,reject)=>{state.queue.push({read,run:operation,resolve:value=>resolve(value as T),reject});drain();});
}
export function withWasmPresentationLane<T>(worker:object,operation:()=>Promise<T>):Promise<T>{return enter(worker,false,operation);}
export function withWasmPresentationPlan<T>(worker:object,operation:()=>Promise<T>):Promise<T>{return enter(worker,true,operation);}
