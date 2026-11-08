import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {ChunkedColumns} from '../src/chunked-columns.js';

test('live native generation, exact identities, reuse and teardown',async()=>{
 const dir=mkdtempSync(join(tmpdir(),'xygc-live-')),path=join(dir,'source.xygc');
 const b=Buffer.alloc(64+48*4+64*16+2*24);
 b.write('XYGC');b.writeUInt32LE(2,4);b.writeBigUInt64LE(64n,8);b.writeUInt32LE(16,16);b.writeUInt32LE(4,20);b.writeBigUInt64LE(256n,24);b.writeBigUInt64LE(1280n,32);b.writeUInt32LE(2,40);
 for(let i=0;i<4;i++){let p=64+i*48;b.writeBigUInt64LE(BigInt(i*16),p);b.writeUInt32LE(16,p+8);[i*16,i*16+15,0,4].forEach((n,j)=>b.writeDoubleLE(n,p+16+j*8));}
 for(let i=0;i<64;i++){b.writeDoubleLE(i,256+i*16);b.writeDoubleLE(i%5,264+i*16);}
 for(const [j,i] of [0,63].entries()){let p=1280+j*24;b.writeBigUInt64LE(BigInt(i),p);b.writeDoubleLE(i,p+8);b.writeDoubleLE(i%5,p+16);}
 writeFileSync(path,b);
 const source=new ChunkedColumns(path),chart=source.chart(null,{maxPoints:2,budgetBytes:4096,pageBytes:4096}),messages=[];
 const host=chart.liveHost((msg,buffers)=>messages.push({msg,buffers}));source.close();
 try {
 host.message({type:'chunked_mount',mount:'A',mount_epoch:'1'});
 const nav=(intent,x)=>host.message({type:'view_change',mount:'A',chunked_intent:String(intent),ranges:{x,y:[-1,6]}});
 nav(1,[10,20]);nav(2,[30,40]);await host.whenIdle();
 assert.equal(messages.length,1);const msg=messages[0].msg;assert.equal(msg.intent,'2');assert.equal(host.chart,chart);
 host.message({type:'chunked_painted',mount:'A',intent:'2',frame:msg.spec.chunked.frame});
 assert.deepEqual([...host.chart.sourceRowIds],Array.from({length:11},(_,i)=>BigInt(i+30)));
 assert.equal(host.message({type:'click',mount:'A',chunked_frame:host.frame,trace:0,index:0}).source_row_id,'30');
 assert.equal(host.message({type:'click',mount:'A',chunked_frame:'0',trace:0,index:0}),undefined);
 const selection=host.message({type:'select',mount:'A',chunked_frame:host.frame,x0:33,x1:35,y0:-1,y1:6});
 assert.deepEqual([...selection.sourceRowIds],[33n,34n,35n]);
 nav(3,[30,40]);await host.whenIdle();assert.equal(host.staged.chart.sourceProvenance.bytesRead,0n);
 nav(4,[0,63]);await host.close();assert.equal(host.source.handle,0n);
 } finally {await host.close();rmSync(dir,{recursive:true,force:true});}
});

function smallSource() {
 const dir=mkdtempSync(join(tmpdir(),'xygc-adversarial-')),path=join(dir,'source.xygc');
 const b=Buffer.alloc(64+48*16+64*16+2*24),offset=64+48*16;
 b.write('XYGC');b.writeUInt32LE(2,4);b.writeBigUInt64LE(64n,8);b.writeUInt32LE(4,16);b.writeUInt32LE(16,20);b.writeBigUInt64LE(BigInt(offset),24);b.writeBigUInt64LE(BigInt(offset+64*16),32);b.writeUInt32LE(2,40);
 for(let i=0;i<16;i++){const p=64+i*48;b.writeBigUInt64LE(BigInt(i*4),p);b.writeUInt32LE(4,p+8);[i*4,i*4+3,Math.min(...Array.from({length:4},(_,j)=>(i*4+j)%5)),Math.max(...Array.from({length:4},(_,j)=>(i*4+j)%5))].forEach((v,j)=>b.writeDoubleLE(v,p+16+8*j));}
 for(let i=0;i<64;i++){b.writeDoubleLE(i,offset+i*16);b.writeDoubleLE(i%5,offset+i*16+8);}
 for(const [j,i] of [0,63].entries()){const p=offset+64*16+j*24;b.writeBigUInt64LE(BigInt(i),p);b.writeDoubleLE(i,p+8);b.writeDoubleLE(i%5,p+16);}
 writeFileSync(path,b);const source=new ChunkedColumns(path),chart=source.chart(null,{budgetBytes:512,pageBytes:512});source.close();
 return {dir,path,offset,chart,close:()=>rmSync(dir,{recursive:true,force:true})};
}
const mount=(host,name='A',epoch='1')=>host.message({type:'chunked_mount',mount:name,mount_epoch:epoch});
const nav=(host,intent,x=[30,40])=>host.message({type:'view_change',mount:'A',chunked_intent:String(intent),ranges:{x,y:[-1,6]}});
const ack=(host,message,type='chunked_painted',name='A')=>host.message({type,mount:name,intent:message.intent,frame:message.spec.chunked.frame});

for(const failure of ['budget','partial','corrupt'])test(`native ${failure} preserves accepted identities and rejects painted waiter`,async()=>{
 const f=smallSource(),messages=[],host=f.chart.liveHost((msg,buffers)=>messages.push({msg,buffers}));mount(host);
 try{
  nav(host,1);await host.whenIdle();ack(host,messages.at(-1).msg);await host.whenPainted();const accepted=host.chart;
  if(failure!=='budget'){
   const {openSync,closeSync,writeSync,ftruncateSync}=await import('node:fs');const fd=openSync(f.path,'r+');
   try{if(failure==='partial')ftruncateSync(fd,f.offset+3);else{const b=Buffer.alloc(8);b.writeDoubleLE(99);writeSync(fd,b,0,8,f.offset);}}finally{closeSync(fd);}
  }
  nav(host,2,failure==='budget'?[0,63]:[0,3]);const waiter=host.whenPainted();const rejected=assert.rejects(waiter);
  await assert.rejects(host.whenIdle());await rejected;
  assert.equal(messages.at(-1).msg.type,'chunked_error');assert.equal(host.chart,accepted);
  assert.deepEqual([...host.chart.sourceRowIds],Array.from({length:11},(_,i)=>BigInt(i+30)));
  const memory=host.memoryReport();assert.ok(memory.hostRetainedCapacityBytes<=memory.hostTypedCapacityBoundBytes,JSON.stringify(memory));
 }finally{await host.close();f.close();}
});

test('native lasso and callbacks carry exact u64, stale masks and old mounts fail closed',async()=>{
 const f=smallSource(),messages=[],clicks=[],selected=[],host=f.chart.liveHost((msg,buffers)=>messages.push({msg,buffers}),{onClick:r=>clicks.push(r),onSelect:r=>selected.push(r)}),other=f.chart.liveHost(()=>{});
 try{
  mount(host);mount(other,'other');nav(host,1);await host.whenIdle();ack(host,messages.at(-1).msg);await host.whenPainted();
  host.message({type:'select_polygon',mount:'A',chunked_frame:host.frame,points:[[31.5,-1],[38.5,-1],[38.5,6],[31.5,6]]});
  assert.deepEqual([...selected.at(-1).sourceRowIds],[32n,33n,34n,35n,36n,37n,38n]);
  const before=messages.length;host.message({type:'select',mount:'A',chunked_frame:'0',x0:0,x1:64,y0:0,y1:5});assert.equal(messages.length,before);
  // Codec boundary control: u64 identity is never converted to a JS Number.
  host.chart.sourceRowIds[0]=9007199254740993n;host.message({type:'click',mount:'A',chunked_frame:host.frame,trace:0,index:0});assert.equal(clicks.at(-1).source_row_id,'9007199254740993');
  host.message({type:'select',mount:'A',chunked_frame:host.frame,x0:30,x1:30,y0:0,y1:4});assert.equal(selected.at(-1).sourceRowIds[0],9007199254740993n);
  mount(host,'B','2');host.message({type:'chunked_unmount',mount:'A'});assert.equal(host.mount,'B');assert.notEqual(host.source.handle,other.source.handle);
  assert.equal(host.payload().spec.chunked.frame,host.frame);assert.deepEqual(host.chart.sourceRowIds,host.initial.sourceRowIds);
  assert.deepEqual([...other.chart.sourceRowIds],[0n,63n]);
 }finally{await host.close();await other.close();f.close();}
});

test('stage rejection, failed send, waiter abort, teardown drain and constructor rollback',async()=>{
 const f=smallSource(),messages=[],host=f.chart.liveHost(msg=>messages.push(msg));mount(host);
 try{
  assert.throws(()=>f.chart.liveHost(null),/send/);
  nav(host,1);await host.whenIdle();const frame=messages.at(-1);
  const waiter=host.whenPainted(),rejected=assert.rejects(waiter,/rejected/);ack(host,frame,'chunked_rejected');await rejected;assert.equal(host.chart,f.chart);
  nav(host,2);await host.whenIdle();const wrong=host.whenPainted();let settled=false;wrong.then(()=>settled=true,()=>settled=true);ack(host,frame);await Promise.resolve();assert.equal(settled,false);
  const controller=new AbortController();const cancelled=host.whenPainted({signal:controller.signal});const cancellation=assert.rejects(cancelled,{name:'AbortError'});controller.abort();await cancellation;
  const closing=assert.rejects(wrong,/closed/);await host.close();await closing;assert.equal(host.source.handle,0n);
  const failed=f.chart.liveHost(()=>{throw Error('transport failed')});mount(failed);nav(failed,1);await assert.rejects(failed.whenIdle(),/transport failed/);await assert.rejects(failed.whenPainted(),/transport failed/);assert.equal(failed.staged,null);await failed.close();
 }finally{await host.close();f.close();}
});

test('one actual async native read, latest intent and immediate main-thread cancellation',async()=>{
 const {xyChunkedColumnsChart}=await import('../src/native.js');
 const f=smallSource(),path=join(f.dir,'many.xygc'),count=262144,offset=64+48*count,b=Buffer.alloc(offset+16*count+48);
 b.write('XYGC');b.writeUInt32LE(2,4);b.writeBigUInt64LE(BigInt(count),8);b.writeUInt32LE(1,16);b.writeUInt32LE(count,20);b.writeBigUInt64LE(BigInt(offset),24);b.writeBigUInt64LE(BigInt(offset+16*count),32);b.writeUInt32LE(2,40);
 for(let i=0;i<count;i++){const p=64+i*48;b.writeBigUInt64LE(BigInt(i),p);b.writeUInt32LE(1,p+8);[i,i,i%5,i%5].forEach((v,j)=>b.writeDoubleLE(v,p+16+8*j));b.writeDoubleLE(i,offset+16*i);b.writeDoubleLE(i%5,offset+16*i+8);}
 for(const [j,i]of [0,count-1].entries()){const p=offset+16*count+j*24;b.writeBigUInt64LE(BigInt(i),p);b.writeDoubleLE(i,p+8);b.writeDoubleLE(i%5,p+16);}writeFileSync(path,b);
 const source=new ChunkedColumns(path),chart=source.chart(null,{budgetBytes:4<<20,pageBytes:64<<10}),messages=[],host=chart.liveHost(m=>messages.push(m));source.close();
 const original=xyChunkedColumnsChart.async;let active=0,peak=0;const returns=[];
 xyChunkedColumnsChart.async=(...args)=>{const callback=args.pop();active++;peak=Math.max(peak,active);original(...args,(error,n)=>{active--;returns.push(n);callback(error,n);});};
 try{
  mount(host);nav(host,1,[0,count-1]);await new Promise(setImmediate);assert.equal(active,1);
  const generation=host.generation;nav(host,2,[30,40]);assert.equal(host.generation,generation+1);
  for(let i=3;i<=20;i++)nav(host,i,[30,40]);assert.equal(host.pending.intent,'20');
  await host.whenIdle();assert.equal(peak,1);assert.equal(returns.length,2);assert.equal(returns[0],18446744073709551615n);
  assert.equal(messages.length,1);assert.equal(messages[0].intent,'20');ack(host,messages[0]);await host.whenPainted();assert.deepEqual([...host.chart.sourceRowIds],Array.from({length:11},(_,i)=>BigInt(30+i)));
  nav(host,21,[0,count-1]);await new Promise(setImmediate);assert.equal(active,1);
  const observer=host.whenPainted(),cancelled=assert.rejects(observer,/closed/);
  const closing=host.close();assert.notEqual(host.source.handle,0n);await closing;await cancelled;
  assert.equal(active,0);assert.equal(peak,1);assert.equal(returns.length,3);assert.equal(returns[2],18446744073709551615n);assert.equal(host.source.handle,0n);assert.equal(messages.length,1);
 }finally{xyChunkedColumnsChart.async=original;await host.close();f.close();}
});
