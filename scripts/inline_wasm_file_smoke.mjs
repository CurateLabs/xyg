#!/usr/bin/env node
// Strict-CSP file: proof for the self-contained density classic worker. The
// generated artifact is embedded in the document; neither page nor Worker can
// request a module, URL, or network resource.
import { createHash } from "node:crypto";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright";

const root = new URL("..", import.meta.url);
const artifact = await readFile(new URL("packages/xy-client/dist/xyg-wasm-inline.js", root), "utf8");
const harness = `(async()=>{
${artifact}
const fail=(message)=>{throw new Error(message)};
const wait=(worker,id)=>new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error("inline worker timed out")),10000);worker.addEventListener("message",function listener(event){if(event.data?.requestId!==id)return;clearTimeout(timer);worker.removeEventListener("message",listener);resolve(event.data)})});
const xyag=()=>{const bytes=new Uint8Array(96),view=new DataView(bytes.buffer);bytes.set([88,89,65,71]);view.setUint32(4,1,true);view.setUint32(8,64,true);view.setUint32(16,2,true);view.setUint32(20,4,true);view.setUint32(24,4,true);view.setFloat64(32,0,true);view.setFloat64(40,4,true);view.setFloat64(48,0,true);view.setFloat64(56,4,true);view.setFloat64(64,.5,true);view.setFloat64(72,2.5,true);view.setFloat64(80,.5,true);view.setFloat64(88,2.5,true);return bytes.buffer};
const url=URL.createObjectURL(new Blob([globalThis.__xygInlineWasm.classicWorkerSource],{type:"application/javascript"}));
const worker=new Worker(url);
try {
  worker.postMessage({type:"init",requestId:1,base64:globalThis.__xygInlineWasm.base64,expectedAbiVersion:22,expectedSceneVersion:24,maxArenaBytes:1048576});
  const ready=await wait(worker,1);if(!ready.ok||ready.value?.abiVersion!==22)fail("classic worker init/diagnostics failed");
  const request=xyag();worker.postMessage({type:"aggregate.bin2d",requestId:2,sequence:1,request},[request]);
  const aggregate=await wait(worker,2);if(!aggregate.ok||!(aggregate.value?.aggregate instanceof ArrayBuffer))fail("classic worker aggregate failed");
  const output=new Uint8Array(aggregate.value.aggregate);if(output[0]!==88||output[1]!==89||output[2]!==65||output[3]!==79)fail("classic worker did not return XYAO");
  worker.postMessage({type:"diagnostics",requestId:3});const diagnostics=await wait(worker,3);if(!diagnostics.ok||diagnostics.value?.arenaBytes!==0)fail("classic worker diagnostics did not clear arena");
  worker.postMessage({type:"aggregate.bin2d",requestId:4,sequence:2,request:new ArrayBuffer(1)});const malformed=await wait(worker,4);if(malformed.ok||malformed.error?.code!=="XYG_WASM_INVALID_ARGUMENT")fail("malformed XYAG did not propagate Rust error: "+JSON.stringify(malformed.error));
  worker.postMessage({type:"dispose",requestId:5});const disposed=await wait(worker,5);if(!disposed.ok)fail("classic worker disposal failed");
  globalThis.__xygInlineFileSmoke={ok:true};
} catch(error) { globalThis.__xygInlineFileSmoke={ok:false,error:String(error?.message||error)}; } finally { worker.terminate();URL.revokeObjectURL(url); }
})();`;
const hash = createHash("sha256").update(harness).digest("base64");
const directory = await mkdtemp(join(tmpdir(), "xyg-inline-wasm-"));
const page = join(directory, "offline.html");
await writeFile(page, `<!doctype html><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'sha256-${hash}' 'wasm-unsafe-eval'; worker-src blob:; connect-src 'none'; object-src 'none'; base-uri 'none'"><script>${harness}</script>`);
const browser = await chromium.launch({ headless: true });
try {
  const tab = await browser.newPage();
  const errors = [];
  tab.on("pageerror", (error) => errors.push(error.message));
  tab.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  await tab.goto(pathToFileURL(page).href);
  let result;
  try { result = await tab.waitForFunction(() => globalThis.__xygInlineFileSmoke, undefined, { timeout: 15000 }).then((value) => value.jsonValue()); }
  catch (error) { throw new Error(`${error instanceof Error ? error.message : error}; page errors: ${errors.join(" | ")}`); }
  if (!result?.ok) throw new Error(result?.error ?? "strict-CSP file inline WASM smoke failed");
  console.log("strict-CSP file URL inline classic WASM aggregate smoke passed");
} finally { await browser.close(); await rm(directory, { recursive: true, force: true }); }
