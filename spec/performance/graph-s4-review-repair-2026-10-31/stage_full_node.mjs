// Complete the isolated diagnostic view with unchanged checkout inputs. Existing
// diagnostic assets and copied test/source files win; shipping paths are untouched.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const stage=path.join(root,'target/task-tmp/s4-review-repair-diagnostic-assets');
function missing(source,target){
  if(!fs.existsSync(target)){fs.symlinkSync(source,target,fs.statSync(source).isDirectory()?'dir':'file');return;}
  if(fs.lstatSync(target).isSymbolicLink())return;
  if(fs.statSync(source).isDirectory()&&fs.statSync(target).isDirectory())for(const name of fs.readdirSync(source))missing(path.join(source,name),path.join(target,name));
}
for(const name of ['docs','examples','scripts','js','spec','tests','python','node_modules','Cargo.toml','pyproject.toml','uv.lock'])missing(path.join(root,name),path.join(stage,name));
console.log(JSON.stringify({scope:'diagnostic full-Node view only; no shipping acceptance',stage}));
missing(path.join(root,'packages/xy-node'),path.join(stage,'packages/xy-node'));
