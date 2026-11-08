import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {assertProgressiveKeyboard} from '../../scripts/verify_graph_progressive_keyboard.mjs';
const fixture=()=>JSON.parse(readFileSync(new URL('./fixtures/graph-progressive-keyboard.json',import.meta.url),'utf8'));
const primary=r=>r.views.find(v=>v.id==='7201');
const alter=(r,i,fn)=>{fn(r.actions[i].publication);fn(primary(r).publications[r.actions[i].publication.ordinal]);};
test('actual captured unfinished trusted focus/select and completed clear journey',()=>assertProgressiveKeyboard(fixture()));
for(const [name,mutate]of [
 ['no-op focus',r=>alter(r,0,p=>p.snapshot.focus=[])],
 ['no-op select',r=>alter(r,1,p=>p.snapshot.selection.refs=[])],
 ['no-op toggle',r=>alter(r,2,p=>p.snapshot.outcome.selected=1)],
 ['no-op clear',r=>alter(r,4,p=>p.snapshot.outcome.stateChanged=false)],
 ['wrong UUID',r=>alter(r,0,p=>p.snapshot.focus[0].uuid='02000000-0000-0000-0000-000000000000')],
 ['untrusted key',r=>r.actions[0].event.trusted=false],
 ['no command',r=>r.actions[0].event.commands=r.actions[0].beforeCommands],
 ['wrong native opcode',r=>r.actions[0].event.operation=7],
 ['foreign instance',r=>r.actions[0].event.instanceId='7202'],
 ['boolean progress count',r=>alter(r,0,p=>p.snapshot.relayout.steps=false)],
 ['completed only',r=>alter(r,0,p=>p.snapshot.relayout.done=true)],
 ['missing later focus progress',r=>{const a=r.actions[0],end=r.actions[1].publication.ordinal;for(const p of primary(r).publications.slice(a.publication.ordinal+1,end))p.snapshot.relayout.steps=a.publication.snapshot.relayout.steps;}],
 ['missing later select progress',r=>{const a=r.actions[1],end=r.actions[2].publication.ordinal;for(const p of primary(r).publications.slice(a.publication.ordinal+1,end))p.snapshot.relayout.steps=a.publication.snapshot.relayout.steps;}],
 ...['equal','regressed'].map(mode=>[mode+' step focus reset',r=>{const p=primary(r).publications[r.actions[0].publication.ordinal+1];p.snapshot.relayout.steps=String(BigInt(r.actions[0].publication.snapshot.relayout.steps)-(mode==='equal'?0n:1n));p.snapshot.focus=[];}]),
 ['intervening selection reset',r=>primary(r).publications[r.actions[1].publication.ordinal+1].snapshot.selection.refs=[]],
 ['peer leak',r=>r.views.find(v=>v.id==='7202').publications[0].snapshot.focus=[{kind:0,uuid:'01000000-0000-0000-0000-000000000000'}]],
 ['no focus pixels',r=>alter(r,0,p=>p.near=0)],
 ['boolean pixel count',r=>alter(r,0,p=>p.near=true)],
 ['missing native emphasis',r=>alter(r,0,p=>p.state=[0,0,0,0])],
 ['focus stolen',r=>primary(r).publications[r.actions[0].publication.ordinal+1].active=false],
 ['stale live summary',r=>alter(r,1,p=>p.live='stale')],
 ['empty escape prevented',r=>r.actions[5].event.prevented=true],
])test('reject '+name,()=>{const r=fixture();mutate(r);assert.throws(()=>assertProgressiveKeyboard(r));});

function queuedFixture(){
 const r=fixture();for(const a of r.actions){a.command={operation:a.event.operation,instanceId:a.event.instanceId,ordinal:a.event.commands,requestId:a.publication.ordinal+100};a.publication.requestId=a.command.requestId;primary(r).publications[a.publication.ordinal].requestId=a.command.requestId;}
 const a=r.actions[1];a.event.operation=15;a.event.commands=a.command.ordinal-1;return r;
}
test('queued trusted intent binds its eventual Rust command and exact publication',()=>assertProgressiveKeyboard(queuedFixture()));
for(const [name,mutate]of [
 ['wrong queued opcode',r=>r.actions[1].command.operation=15],
 ['foreign queued reply',r=>r.actions[1].command.requestId++],
 ['queued command absent',r=>r.actions[1].command.ordinal=r.actions[1].beforeCommands],
 ['queued intent bypassed',r=>r.actions[1].command.ordinal+=2],
])test('reject '+name,()=>{const r=queuedFixture();mutate(r);assert.throws(()=>assertProgressiveKeyboard(r));});
