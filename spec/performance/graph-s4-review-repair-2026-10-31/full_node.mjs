// Run every existing npm test entry unchanged, with bounded concurrent files.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const host=path.join(root,'target/task-tmp/s4-review-repair-diagnostic-assets/packages/xy-node');
const [node,test,...files]=JSON.parse(fs.readFileSync(path.join(host,'package.json'))).scripts.test.split(/\s+/);
if(node!=='node'||test!=='--test'||files.some(f=>!f.startsWith('test/')))throw new Error('unexpected npm test schema');
console.log(JSON.stringify({scope:'full existing Node baseline suite; explicitly diagnostic assets',node:process.version,cwd:host,argv:['--test','--test-concurrency=2',...files]}));
execFileSync(process.execPath,['--test','--test-concurrency=2',...files],{cwd:host,stdio:'inherit'});
