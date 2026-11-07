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
