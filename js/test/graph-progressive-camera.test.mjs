import test from 'node:test';
import assert from 'node:assert/strict';
import {assertProgressiveCameraPan} from '../../scripts/verify_graph_progressive_camera.mjs';
const before=[.25,.25,320,160,640,320,1],after=[.25,.25,332,160,640,320,1];
const fixture=()=>({pans:[{trusted:true,returned:2,before:{camera:[...before]},after:{camera:[...after],relayout:{steps:'10',done:false}}}],frames:[{at:3,camera:[...after],progress:{steps:'20',done:false}}],finalSnapshot:{camera:[...after]}});
test('exact host pan persists through a later continuation',()=>assertProgressiveCameraPan(fixture()));
for(const [name,mutate] of [
 ['no-op camera',v=>v.pans[0].after.camera=[...before]],
 ['wrong translation',v=>v.pans[0].after.camera[2]=331],
 ['corrupt component',v=>v.pans[0].after.camera[4]=NaN],
 ['changed scale',v=>v.pans[0].after.camera[0]=1],
 ['untrusted callback',v=>v.pans[0].trusted=false],
 ['terminal callback',v=>v.pans[0].after.relayout.done=true],
 ['no later continuation',v=>v.frames[0].progress.steps='10'],
 ['late camera reset',v=>v.frames[0].camera=[...before]],
 ['final camera reset',v=>v.finalSnapshot.camera=[...before]],
])test(`reject ${name}`,()=>{const v=fixture();mutate(v);assert.throws(()=>assertProgressiveCameraPan(v));});
