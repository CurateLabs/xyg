// Diagnostic only: unchanged two-path smoke, raw local WASM, NO package gate.
// Never stages this raw module into the product's generated distribution.
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, symlinkSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
const root = fileURLToPath(new URL('../../../', import.meta.url));
mkdirSync(join(root, 'target/task-tmp'), { recursive: true });
const sandbox = mkdtempSync(join(root, 'target/task-tmp/node35-csp-raw-diagnostic-'));
mkdirSync(join(sandbox, 'scripts'));
mkdirSync(join(sandbox, 'packages/xy-client/dist'), { recursive: true });
copyFileSync(join(root, 'scripts/graphforge_webview_smoke.mjs'), join(sandbox, 'scripts/graphforge_webview_smoke.mjs'));
for (const [source, target] of [
  ['packages/xy-node', 'packages/xy-node'], ['node_modules', 'node_modules'], ['tests', 'tests'],
  ['packages/xy-client/dist/index.js', 'packages/xy-client/dist/index.js'],
  ['packages/xy-client/dist/wasm-worker.js', 'packages/xy-client/dist/wasm-worker.js'],
  ['target/wasm32-unknown-unknown/release/xyg_wasm.wasm', 'packages/xy-client/dist/xyg-wasm.wasm'],
]) symlinkSync(join(root, source), join(sandbox, target));
const sha = name => createHash('sha256').update(readFileSync(join(root, name))).digest('hex');
console.log(JSON.stringify({ scope: 'raw-WASM diagnostic, not shipping qualification', sandbox,
  smokeSha256: sha('scripts/graphforge_webview_smoke.mjs'),
  rawWasmSha256: sha('target/wasm32-unknown-unknown/release/xyg_wasm.wasm'),
  nativeSha256: sha('target/release/libxyg_core.so'),
  clientSha256: sha('packages/xy-client/dist/index.js'),
  workerSha256: sha('packages/xy-client/dist/wasm-worker.js') }));
const result = spawnSync(process.execPath, [join(sandbox, 'scripts/graphforge_webview_smoke.mjs')], {
  cwd: sandbox, stdio: 'inherit', timeout: 90000,
  env: { ...process.env, XYG_GRAPHFORGE_SCREENSHOT: process.env.XYG_GRAPHFORGE_SCREENSHOT ?? join(sandbox, 'diagnostic.png') },
});
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
