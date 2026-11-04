// Diagnostic component prototype only: not product paint or a passing oracle.
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
const out=path.resolve(process.argv[2]);fs.mkdirSync(out,{recursive:true});
const browser=await chromium.launch({executablePath:process.env.XYG_CHROMIUM,args:['--no-sandbox','--hide-scrollbars']});
const results={purpose:'Compatibility decision evidence only; prototype is not product proof',cases:[]};
try{
 for(const [name,css] of [
  ['solid','width:80px;height:8px;background:rgb(180,30,60)'],
  ['border','width:80px;height:8px;background:rgb(180,30,60);border:2px solid rgb(0,0,255)'],
  ['gradient','width:80px;height:8px;background:linear-gradient(90deg,rgb(255,0,0),rgb(0,0,255))'],
 ]){
  const page=await browser.newPage({viewport:{width:140,height:70},deviceScaleFactor:1});
  await page.setContent(`<style>body{margin:0;background:white}.axis{position:absolute;left:17px;top:19px;${css}}</style><div id="host"><div class="axis" data-xy-slot="axis_line"></div></div>`);
  const source=await page.evaluate(()=>{const e=document.querySelector('.axis'),s=getComputedStyle(e),r=e.getBoundingClientRect();return {box:{x:r.x,y:r.y,width:r.width,height:r.height},background:s.backgroundColor,backgroundImage:s.backgroundImage,borderWidth:s.borderWidth,borderColor:s.borderColor,css:e.getAttribute('style'),className:e.className};});
  await page.screenshot({path:path.join(out,`${name}.html.png`)});
  const prototype=await page.evaluate(source=>{
   document.getElementById('host').replaceChildren();
   const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('width','140');svg.setAttribute('height','70');
   const line=document.createElementNS(svg.namespaceURI,'line');const b=source.box;
   for(const [k,v] of Object.entries({x1:b.x,y1:b.y+b.height/2,x2:b.x+b.width,y2:b.y+b.height/2,'stroke-width':b.height,stroke:source.background,'stroke-linecap':'butt'}))line.setAttribute(k,String(v));
   svg.appendChild(line);document.getElementById('host').appendChild(svg);
   return {attributes:Object.fromEntries([...line.attributes].map(a=>[a.name,a.value])),computedBackground:getComputedStyle(line).backgroundColor};
  },source);
  await page.screenshot({path:path.join(out,`${name}.literal-svg-prototype.png`)});
  results.cases.push({name,css,source,prototype});await page.close();
 }
}finally{await browser.close();}
fs.writeFileSync(path.join(out,'observations.json'),JSON.stringify(results,null,2)+'\n');
console.log('Recorded actual HTML styles and separate literal-color SVG projection prototypes; no product intervention.');
