// Test-only trusted input and publication recorder. No product identity policy.
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import {assertProgressiveKeyboard} from './verify_graph_progressive_keyboard.mjs';
export async function graphProgressiveKeyboardCase(page, report) {
  // Fresh document resets the browser's sequential Tab starting point after the
  // preceding case removed its focused host button. No product focus override.
  await page.reload();
  await page.waitForFunction(()=>window.__graphSession?.stage==='ready');
  await page.evaluate(async()=>{
    const s=window.__graphSession, attach=s.attach;
    s.attach=options=>{
      if(![7201n,7202n].includes(options.instanceId))return attach(options);
      const el=options.el, p={id:String(options.instanceId),publications:[],keys:[],digests:[]};
      el.dataset.keyboard=p.id;el.style.setProperty('--chart-focus','#ff00ff');
      s.keyboardViews??=[];s.keyboardViews.push(p);document.body.prepend(el);
      const owner=options.worker.worker.__graphOwner;p.owner=owner;
      for(const kind of ['render','focus','select'])el.addEventListener('xy:graph-'+kind,e=>{
        const reply=s.replies.filter(r=>r.owner===owner).at(-1), snapshot=e.detail;
        const state=Array.from(s.section(reply.bytes,'gpu.node.state.u8'));
        const centers=s.values(reply.bytes,'paint.node.center.f64');
        const pixels=el.querySelector('canvas').getContext('2d').getImageData(0,0,640,320).data;
        let magenta=0,near=0;
        for(let i=0;i<pixels.length;i+=4)if(pixels[i]>240&&pixels[i+1]<15&&pixels[i+2]>240&&pixels[i+3]>200){magenta++;const x=(i/4)%640,y=Math.floor(i/4/640);if(Math.hypot(x-centers[0],y-centers[1])<16)near++;}
        p.publications.push({ordinal:p.publications.length,kind,snapshot,state:state.slice(0,4),center:Array.from(centers.slice(0,2)),magenta,near,active:document.activeElement===el.querySelector('[role=application]'),live:el.querySelector('[aria-live=polite]').textContent});
        if(kind==='focus'||kind==='select') {p.captures??={};p.captures[`${kind}-${p.publications.length-1}`]=el.querySelector('canvas').toDataURL('image/png');}
        for(const r of s.replies.filter(r=>r.owner===owner))if(!r.digest){
          r.replyBytes=r.bytes.length;
          r.digest=crypto.subtle.digest('SHA-256',r.bytes).then(h=>{r.replySha256=Array.from(new Uint8Array(h),v=>v.toString(16).padStart(2,'0')).join('');if(s.replies.filter(x=>x.owner===owner).at(-1)!==r)delete r.bytes;return r.replySha256;});p.digests.push(r.digest);
        } else if(r!==reply&&r.replySha256)delete r.bytes;
      });
      el.addEventListener('keydown',e=>p.keys.push({key:e.key,ctrl:e.ctrlKey,trusted:e.isTrusted,prevented:e.defaultPrevented,commands:s.commands.filter(c=>c.owner===owner).length,operation:s.commands.filter(c=>c.owner===owner).at(-1)?.operation,instanceId:String(s.commands.filter(c=>c.owner===owner).at(-1)?.instanceId),ordinal:p.publications.length}));
      return attach(options);
    };
    try{await Promise.all([s.progressiveFixture(1000,7202n),s.progressiveFixture(1000,7201n)]);}finally{s.attach=attach;}
    document.body.prepend(s.progressives.find(p=>p.id===7201n).el);
  });
  // Real keyboard navigation from the host DOM start; no surface.focus().
  await page.keyboard.press('Tab');
  for(let i=0;i<12 && !await page.locator('[data-keyboard="7201"] [role=application]').evaluate(el=>el===document.activeElement);i++)await page.keyboard.press('Tab');
  assert.equal(await page.locator('[data-keyboard="7201"] [role=application]').evaluate(el=>el===document.activeElement),true,'Tab reaches application');
  const press=async(key,kind)=>{
    const eventKey=key.split('+').at(-1);
    for(let attempt=0;attempt<80;attempt++){
      const mark=await page.evaluate(()=>{const p=window.__graphSession.keyboardViews.find(p=>p.id==='7201');return {keys:p.keys.length,pubs:p.publications.length,commands:window.__graphSession.commands.filter(c=>c.owner===p.owner).length};});
      await page.keyboard.press(key);
      const event=await page.evaluate(({mark,eventKey})=>{const p=window.__graphSession.keyboardViews.find(p=>p.id==='7201');return p.keys.slice(mark.keys).find(e=>e.key===eventKey);},{mark,eventKey});
      if(event?.prevented||key==='Escape'&&kind==='empty'){
        await page.waitForFunction(({mark,kind})=>{const p=window.__graphSession.keyboardViews.find(p=>p.id==='7201');return p.publications.slice(mark.pubs).some(x=>x.kind===(kind==='focus'?'focus':'select'));},{mark,kind});
        return await page.evaluate(({mark,kind,eventKey})=>{const p=window.__graphSession.keyboardViews.find(p=>p.id==='7201'),publication=p.publications.slice(mark.pubs).find(x=>x.kind===(kind==='focus'?'focus':'select'));return {action:kind,beforeCommands:mark.commands,event:p.keys.slice(mark.keys).find(e=>e.key===eventKey),publication};},{mark,kind,eventKey});
      }
    }throw Error('no admitted trusted '+kind);
  };
  const progress=async()=>page.waitForFunction(()=>{const p=window.__graphSession.keyboardViews.find(p=>p.id==='7201'),last=p.publications.filter(x=>x.kind!=='render').at(-1);return p.publications.some(x=>x.ordinal>last.ordinal&&x.snapshot.relayout.steps>last.snapshot.relayout.steps);});
  const actions=[await press('ArrowRight','focus')];await progress();actions.push(await press('Enter','replace'));await progress();
  await page.waitForFunction(()=>[7201n,7202n].every(id=>window.__graphSession.progressives.find(p=>p.id===id).handle.snapshot()?.relayout?.done),null,{timeout:40000});
  actions.push(await press('Control+Enter','toggle'),await press('Enter','replace'),await press('Escape','clear'),await press('Escape','empty'));
  const result=await page.evaluate(async actions=>{
    const s=window.__graphSession, views=[];
    for(const p of s.keyboardViews){const f=s.progressives.find(f=>String(f.id)===p.id);await s.waitForCapture(f);await Promise.all(p.digests);
      const b64=b=>{let t='';for(let i=0;i<b.length;i+=16384)t+=String.fromCharCode(...b.subarray(i,i+16384));return btoa(t);};
      const replay=s.commands.filter(c=>c.owner===p.owner&&c.bytes).map(c=>{const r=s.replies.find(r=>r.owner===p.owner&&r.requestId===c.requestId);return {operation:c.operation,request:b64(c.bytes),replyBytes:r.replyBytes,replySha256:r.replySha256};});
      const frames=f.frames.length;clearInterval(f.timer);await f.handle.dispose();await f.worker.dispose();
      views.push({id:p.id,sourceNodes:1000,sourceEdges:1000,arena:f.arena,actualArena:f.worker.worker.__actualArena,defaultArena:f.defaultArena,requestedArena:f.worker.__requestedArena??null,publications:p.publications,keys:p.keys,replay,captures:p.captures,errors:f.errors,disposed:f.handle.snapshot()===null,children:f.el.children.length,framesAtDispose:frames});f.el.remove();
    }await new Promise(r=>setTimeout(r,25));for(const p of views)p.framesAfterDispose=s.progressives.find(f=>String(f.id)===p.id).frames.length;
    return {actions,views,held:s.held.length,focusToken:'#ff00ff',navigation:'Playwright Tab'};
  },actions);
  for(const p of result.views){for(const [kind,data]of Object.entries(p.captures??{}))if(report)await writeFile(`${report}.${p.id}.${kind}.png`,Buffer.from(data.split(',')[1],'base64'));delete p.captures;}
  if(report)await writeFile(report+'.keyboard.json',JSON.stringify(result,(_,v)=>typeof v==='bigint'?String(v):v,2)+'\n');
  for(const p of result.views){assert.equal(p.actualArena,16*1024*1024);assert.equal(p.defaultArena,true);assert.equal(p.requestedArena,null);}
  assertProgressiveKeyboard(result,16*1024*1024);
  return result;
}
