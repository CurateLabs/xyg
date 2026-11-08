// Test-only stdio carrier; base64 is confined to this evidence bridge.
import {createInterface} from 'node:readline';
import {ChunkedColumns} from '../src/chunked-columns.js';
const source=new ChunkedColumns(process.argv[2]);
const chart=source.chart(null,{budgetBytes:1<<20,pageBytes:1<<20});
const write=x=>process.stdout.write(JSON.stringify(x,(_,v)=>typeof v==='bigint'?String(v):v)+'\n');
const encode=b=>Buffer.from(b.buffer??b,b.byteOffset??0,b.byteLength).toString('base64');
const host=chart.liveHost((msg,buffers)=>write({kind:'message',msg,buffers:buffers.map(encode)}));
source.close();
const {spec,buffers}=host.payload();write({kind:'initial',spec,buffers:buffers.map(encode)});
for await(const line of createInterface({input:process.stdin})){
 const msg=JSON.parse(line);if(msg.type==='close'){await host.close();break;}
 const row=host.message(msg);
 if(msg.type==='pick'&&row)write({kind:'pick',row});
 if(msg.type==='chunked_painted')write({kind:'state',ids:[...host.chart.sourceRowIds],provenance:{generation:host.chart.sourceProvenance.generation,first_chunk:host.chart.sourceProvenance.firstChunk,chunks_considered:host.chart.sourceProvenance.chunksConsidered,chunks_read:host.chart.sourceProvenance.chunksRead,bytes_read:host.chart.sourceProvenance.bytesRead}});
}
await host.close();
process.stdin.destroy();
