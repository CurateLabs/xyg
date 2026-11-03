// DIAGNOSTIC COMPONENT CONTROL ONLY. No product chart, supplied plot, acceptance
// comparison, native export, or producer is modified. Test both serialized
// coordinates independently to explain remaining raw reference sample deltas.
import fs from 'node:fs';
import path from 'node:path';
import {chromium} from 'playwright';
const out=path.resolve(process.argv[2]);fs.mkdirSync(out,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.XYG_CHROMIUM,args:['--no-sandbox','--hide-scrollbars','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const records=[];
try{for(const mode of ['inline','image'])for(const x of [306.62,306.625]){
 const page=await browser.newPage({viewport:{width:320,height:240},deviceScaleFactor:1.25});
 await page.setContent('<style>body{margin:0;background:#030712}</style>');
 const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240"><line x1="${x}" y1="6" x2="${x}" y2="204" stroke="rgb(229,231,235)" stroke-width="1.5" stroke-linecap="butt"/></svg>`;
 await page.evaluate(async({mode,svg})=>{if(mode==='inline')document.body.appendChild(new DOMParser().parseFromString(svg,'image/svg+xml').documentElement);else{const img=new Image(320,240);img.src=URL.createObjectURL(new Blob([svg],{type:'image/svg+xml'}));document.body.appendChild(img);await img.decode();}},{mode,svg});
 const name=`${mode}.x${x}.png`;await page.screenshot({path:path.join(out,name)});records.push({mode,x,name,devicePixelRatio:1.25});await page.close();
}}finally{await browser.close();}
fs.writeFileSync(path.join(out,'observations.json'),JSON.stringify({purpose:'Separate diagnostic SVG kernel control, never product proof',records},null,2)+'\n');
