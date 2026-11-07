// Public exported HTML uses the existing ChartView and painter, offline.
import {chromium} from 'playwright';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const browser=await chromium.launch({executablePath:process.env.XYG_CHROMIUM,args:['--enable-unsafe-swiftshader','--use-gl=angle','--use-angle=swiftshader']});
try {
 for(const kind of ['event','interval','gantt','line','bar','scatter']){
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(pathToFileURL(`${process.argv[2]}/${kind}.html`).href);
  await page.waitForFunction(()=>window.temporalView?.gpuTraces?.length>0);
  assert.deepEqual(errors,[]);
  assert.equal(await page.evaluate(()=>window.temporalView.sceneStableId(0,0).toString()),'18446744073709551615');
  await page.screenshot({path:`${process.argv[2]}/${kind}.png`});
  await page.evaluate(()=>window.temporalView.destroy());await page.close();
 }
 console.log('6 offline public temporal HTML journeys painted, exact u64 picks and disposal');
}finally{await browser.close();}
