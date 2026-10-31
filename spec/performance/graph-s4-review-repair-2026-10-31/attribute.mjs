// Read raw compiler function-body sizes and name map without changing any bytes.
import fs from 'node:fs';
const file=process.argv[2], b=fs.readFileSync(file);
let at=8;const names=new Map(),sizes=[];
const u=()=>{let n=0,s=0,v;do{v=b[at++];n+=(v&127)*2**s;s+=7;}while(v&128);return n;};
const str=()=>{const n=u(),s=b.toString('utf8',at,at+n);at+=n;return s;};
while(at<b.length){const id=b[at++],n=u(),end=at+n;
 if(id===0&&str()==='name'){while(at<end){const sub=b[at++],len=u(),subend=at+len;if(sub===1){const count=u();for(let i=0;i<count;i++){const index=u();names.set(index,str());}}at=subend;}}
 if(id===10){const count=u();for(let i=0;i<count;i++){const length=u();sizes.push({index:i,bytes:length});at+=length;}}
 at=end;
}
const list=sizes.map(s=>({...s,name:names.get(s.index)??null}));
console.log(JSON.stringify({scope:'raw function body byte attribution (optimizer may inline/fold boundaries)',file,nameCount:names.size,codeBytes:sizes.reduce((n,s)=>n+s.bytes,0),top:list.sort((a,b)=>b.bytes-a.bytes).slice(0,35),session:list.filter(s=>/candidate|wire.*execute|WireSession.*finish|uuid_text|GraphSession.*clone/.test(s.name??''))},null,2));
