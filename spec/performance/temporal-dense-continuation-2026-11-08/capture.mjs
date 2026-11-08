// Public native composition capture; output directory must be separate and empty.
import {mkdirSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {join} from 'node:path';
import {temporalChart,encodeTemporalScene} from '../../../packages/xy-node/src/index.js';
const directory=process.argv[2];if(!directory)throw new Error('capture output directory required');mkdirSync(directory,{recursive:false});
const captures=[];
for(const kind of ['event','interval','gantt','line','bar','scatter']){
 const rows=Array.from({length:10000},(_,i)=>[BigInt(i),BigInt(i+1),0,2n**63n+BigInt(i)]);
 const options={domain:[0n,10000n],timezone:'UTC',dense:true,width:900,height:420};
 const chart=temporalChart(kind,rows,options),metadata=chart.temporalMetadata(),v=new DataView(metadata.buffer,metadata.byteOffset,metadata.byteLength),cell=Number(v.getBigUint64(64,true));
 const outputs={request:encodeTemporalScene({kind,rows,...options}),metadata,members:chart.temporalMembers(metadata,cell),scene:chart.toScene(),svg:chart.toSvg(),png:chart.toPng(),html:chart.toHtml()};
 if(kind==='line')outputs.supports=chart.temporalSupports(metadata,cell);
 for(const [name,value] of Object.entries(outputs)){
  const bytes=typeof value==='string'?Buffer.from(value):Buffer.from(value instanceof ArrayBuffer?new Uint8Array(value):value);
  const file=`${kind}.${name}`;writeFileSync(join(directory,file),bytes);captures.push({kind,type:name,path:file,bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')});
 }
 chart.temporalDispose();
}
writeFileSync(join(directory,'captures.json'),JSON.stringify(captures,null,2)+'\n');
console.log(JSON.stringify(captures,null,2));
