import { execFileSync } from 'node:child_process';
import { copyFileSync, mkdirSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const app = fileURLToPath(new URL('..', import.meta.url));
const root = path.resolve(app, '../..');
const target = path.join(app, 'public/xy');
mkdirSync(target, { recursive: true });
mkdirSync(path.join(app, 'public/fonts'), { recursive: true });
copyFileSync(path.join(app, 'assets/fonts/InstrumentSans-wdth-wght.ttf'), path.join(app, 'public/fonts/InstrumentSans-wdth-wght.ttf'));
copyFileSync(path.join(app, 'assets/fonts/OFL.txt'), path.join(app, 'public/fonts/OFL.txt'));
for (const name of readdirSync(path.join(root, 'python/xyg/static'))) {
  if (/\.(js|wasm)$/.test(name)) copyFileSync(path.join(root, 'python/xyg/static', name), path.join(target, name));
}
for (const name of ['xyg-social-card.svg', 'xyg-social-card.png']) {
  copyFileSync(path.join(app, 'assets', name), path.join(app, 'public', name));
}
copyFileSync(path.join(app, 'src/assets/xyg.svg'), path.join(app, 'public/favicon.svg'));
copyFileSync(path.join(app, 'src/scripts/chart-previews.js'), path.join(target, 'chart-previews.js'));
for (const script of ['generate_examples.py', 'prepare_content.py']) {
  execFileSync('uv', ['run', '--no-sync', 'python', `docs/app/scripts/${script}`], { cwd: root, stdio: 'inherit' });
}
