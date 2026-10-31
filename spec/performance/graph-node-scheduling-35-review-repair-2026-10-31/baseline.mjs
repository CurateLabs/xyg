// Expected-failure proof against immutable a27 sources; no worktree edits.
import { copyFileSync, cpSync, mkdirSync, mkdtempSync, symlinkSync, writeFileSync } from 'node:fs';
import { execFileSync, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
const root = fileURLToPath(new URL('../../../', import.meta.url));
mkdirSync(join(root, 'target/task-tmp'), { recursive: true });
const baseline = mkdtempSync(join(root, 'target/task-tmp/node35-a27-'));
const pkg = join(baseline, 'packages/xy-node');
mkdirSync(join(pkg, 'test'), { recursive: true });
cpSync(join(root, 'packages/xy-node/src'), join(pkg, 'src'), { recursive: true });
copyFileSync(join(root, 'packages/xy-node/package.json'), join(pkg, 'package.json'));
copyFileSync(join(root, 'packages/xy-node/test/graphforge-layout.test.mjs'), join(pkg, 'test/graphforge-layout.test.mjs'));
symlinkSync(join(root, 'packages/xy-node/node_modules'), join(pkg, 'node_modules'), 'dir');
symlinkSync(join(root, 'tests'), join(baseline, 'tests'), 'dir');
for (const name of ['graphforge.js', 'graphforge_layout.js', 'graphforge_layout_worker.js']) {
  writeFileSync(join(pkg, 'src', name), execFileSync('git', ['show', `a27ed2edb0d0c314bbf9bf86a6554f3cb86e7fbd:packages/xy-node/src/${name}`], { cwd: root }));
}
const result = spawnSync(process.execPath, ['--test',
  '--test-name-pattern=render-node|Direct, EdgeSample|collapsed groups|circle/grid|reentrant startup|non-force Aggregate source',
  join(pkg, 'test/graphforge-layout.test.mjs')], { cwd: root, stdio: 'inherit', timeout: 30000 });
if (result.error) throw result.error;
process.exitCode = result.status ?? 1; // Six failures are expected on a27.
