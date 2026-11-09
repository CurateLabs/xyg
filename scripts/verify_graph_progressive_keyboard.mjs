import assert from 'node:assert/strict';
const uuid='01000000-0000-0000-0000-000000000000';
const refs=(refs,n)=>{assert.equal(refs.length,n);if(n){assert.equal(refs[0].uuid,uuid);assert.equal(refs[0].kind,0);}};
export function assertProgressiveKeyboard(r, arena = 384*1024*1024){
  assert.equal(r.views.length,2);assert.equal(r.navigation,'Playwright Tab');assert.equal(r.held,0);
  const primary=r.views.find(p=>p.id==='7201'),peer=r.views.find(p=>p.id==='7202');assert.ok(primary&&peer);
  for(const p of r.views){assert.equal(p.arena,arena);assert.equal(p.sourceNodes,1000);assert.equal(p.sourceEdges,1000);assert.deepEqual(p.errors,[]);assert.equal(p.disposed,true);assert.equal(p.children,0);assert.equal(p.framesAfterDispose,p.framesAtDispose);assert.ok(p.publications.length>3);p.publications.forEach((v,i)=>{assert.equal(v.ordinal,i);assert.ok(Number.isInteger(v.snapshot.revision)&&v.snapshot.revision>=0);const steps=v.snapshot.relayout.steps;assert.ok((typeof steps==='bigint'&&steps>=0n)||(typeof steps==='string'&&/^\d+$/.test(steps)), 'native progress is an exact count');});}
  for(const v of peer.publications){refs(v.snapshot.focus,0);refs(v.snapshot.selection.refs,0);assert.equal(v.magenta,0);assert.deepEqual(v.state,[0,0,0,0]);}
  assert.equal(peer.keys.length,0);assert.equal(primary.publications[0].magenta,0);assert.equal(primary.publications[0].near,0);refs(primary.publications[0].snapshot.focus,0);
  assert.deepEqual(r.actions.map(a=>a.action),['focus','replace','toggle','replace','clear','empty']);
  let selected=0;
  for(let i=0;i<r.actions.length;i++){
    const a=r.actions[i],v=a.publication,s=v.snapshot;
    assert.equal(a.event.trusted,true);assert.equal(a.event.key,['ArrowRight','Enter','Enter','Enter','Escape','Escape'][i]);assert.equal(a.event.ctrl,i===2);const command=a.command??a.event;assert.equal(command.operation,[5,7,7,7,4,4][i]);assert.equal(command.instanceId,'7201');
    if(a.command){
      // An accepted key may wait behind the one outstanding force command.
      // Bind its eventual opcode to the actual reply/publication, retaining
      // the dispatch-time observation without relabelling a force request.
      assert.equal(command.requestId,v.requestId);assert.ok(Number.isInteger(command.ordinal)&&command.ordinal>a.beforeCommands);
      assert.ok(a.event.commands>=a.beforeCommands&&command.ordinal-a.event.commands>=0&&command.ordinal-a.event.commands<=1);
    }else assert.equal(a.event.commands,a.beforeCommands+1);assert.equal(a.event.prevented,i!==5);assert.ok(Number.isInteger(a.beforeCommands)&&a.beforeCommands>0);assert.ok(Number.isInteger(a.event.commands)&&a.event.commands>0);assert.ok(Number.isInteger(a.event.ordinal));assert.ok(a.event.ordinal<=v.ordinal);
    assert.deepEqual(primary.publications[v.ordinal],v);assert.equal(v.kind,i===0?'focus':'select');assert.equal(s.outcome.stateChanged,i!==5);assert.equal(s.outcome.selected,[0,1,0,1,0,0][i]);assert.equal(s.clearAction.applicable,i===1||i===3);assert.deepEqual(Object.values(s.selection.indices).map(String),i===1||i===3?['0']:[]);assert.deepEqual(v.state,i===1||i===3?[5,1,2,0]:[0,1,0,0]);
    refs(s.focus,1);selected=[0,1,0,1,0,0][i];refs(s.selection.refs,selected);
    if(i===0||i===1)assert.equal(s.relayout.done,false,'focus and select must be unfinished');
    const end=r.actions[i+1]?.publication.ordinal??primary.publications.length;
    for(const p of primary.publications.slice(v.ordinal,end)){refs(p.snapshot.focus,1);refs(p.snapshot.selection.refs,selected);assert.equal(p.active,true);assert.equal(p.live,p.snapshot.summary);}
    if(i<2)assert.ok(primary.publications.slice(v.ordinal+1,end).some(p=>BigInt(p.snapshot.relayout.steps)>BigInt(s.relayout.steps)),'later progress retains each unfinished action');
    assert.ok(Number.isInteger(v.near)&&Number.isInteger(v.magenta)&&v.near>0&&v.magenta>0,'focused native center has painted host focus color');
  }
  assert.equal(primary.publications.at(-1).snapshot.relayout.done,true);
}
