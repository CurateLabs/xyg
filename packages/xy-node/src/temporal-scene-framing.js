/** XYTM framing only. Rust owns temporal membership, geometry and tick policy. */







function exact(v        , signed=true)         {
  if (typeof v !== 'bigint' || v < (signed ? -(1n<<63n) : 0n) || v >= (signed ? 1n<<63n : 1n<<64n)) throw new TypeError('exact timestamp/identity outside wire width');
  return v;
}
/** Exact transport envelope; shared by encoding and public source snapshots. */
export function temporalSceneSize(count, timezone, title) {
  const size=128+new TextEncoder().encode(timezone).length+new TextEncoder().encode(title??'').length+count*40;
  if(!Number.isSafeInteger(count)||count<0||!Number.isSafeInteger(size)||size>64*1024*1024)throw new RangeError('temporal source exceeds framing budget');
  return size;
}
export function encodeTemporalScene(input                    )              {
  const kind=['event','interval','gantt','line','bar','scatter'].indexOf(input.kind);
  if(kind<0)throw new TypeError('unknown temporal family');
  const zone=new TextEncoder().encode(input.timezone), title=new TextEncoder().encode(input.title??'');
  const n=input.rows.length, size=temporalSceneSize(n,input.timezone,input.title);
  const out=new ArrayBuffer(size), b=new Uint8Array(out), v=new DataView(out);
  b.set([88,89,84,77]);v.setUint32(4,1,true);v.setUint32(8,kind,true);v.setUint32(12,n,true);
  v.setFloat64(16,input.width??900,true);v.setFloat64(24,input.height??420,true);
  v.setBigInt64(32,exact(input.domain[0]),true);v.setBigInt64(40,exact(input.domain[1]),true);v.setBigInt64(48,exact(input.cursor??input.domain[0]),true);
  v.setUint32(56,zone.length,true);v.setUint32(60,title.length,true);
  const precision=input.precision??2;if(!Number.isInteger(precision)||precision<0||precision>3)throw new TypeError('invalid source precision');
  v.setUint32(64,precision,true);
  for(const [at,paint] of [[72,input.color],[76,input.stroke]]         ){const p=paint??new Uint8Array([31,119,180,255]);if(!(p instanceof Uint8Array)||p.length!==4)throw new TypeError('paint requires RGBA8');b.set(p,at);}
  v.setFloat64(80,input.strokeWidth??1,true);b.set(zone,128);b.set(title,128+zone.length);
  input.rows.forEach(([start,end,value,id],i)=>{const at=128+zone.length+title.length+i*40;
    v.setBigInt64(at,start===null?0n:exact(start),true);v.setBigInt64(at+8,end===null?0n:exact(end),true);
    v.setFloat64(at+16,value,true);v.setBigUint64(at+24,exact(id,false),true);b[at+32]=Number(start!==null);b[at+33]=Number(end!==null);
  });return out;
}
