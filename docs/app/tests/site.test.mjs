import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { checkLink, outputPath, validateSite } from '../scripts/check-built.mjs';

test('published docs retain routes, readable APIs, links, and actual native charts', async () => {
  const result = await validateSite();
  assert.ok(result.pages > 50);
  assert.ok(result.previews > 100);
});

test('the link gate rejects missing pages and anchors, including encoded anchors', async () => {
  const dist = await mkdtemp(path.join(tmpdir(), 'xyg-docs-links-'));
  try {
    await mkdir(path.join(dist, 'guide'));
    await writeFile(path.join(dist, 'guide/index.html'), '<h2 id="native-parity">Native parity</h2>');
    await checkLink(dist, '/docs/xy/', '/docs/xy/guide/#native%2Dparity');
    await mkdir(path.join(dist, 'legacy'));
    await writeFile(path.join(dist, 'legacy/index.html'), '<meta http-equiv="refresh" content="0;url=/docs/xy/guide/">');
    await checkLink(dist, '/docs/xy/', '/docs/xy/legacy/#native-parity');
    await assert.rejects(checkLink(dist, '/docs/xy/', '/docs/xy/legacy/#missing'), /missing anchor/);
    await assert.rejects(checkLink(dist, '/docs/xy/', '/docs/xy/guide/#missing'), /missing anchor/);
    await assert.rejects(checkLink(dist, '/docs/xy/', '/docs/xy/missing/'), /missing target/);
    await checkLink(dist, '/docs/xy/', 'https://github.com/CurateLabs/graphforge');
  } finally {
    await rm(dist, { recursive: true, force: true });
  }
});

test('static links cannot escape the documented base or site output', () => {
  assert.throws(() => outputPath('/tmp/site', '/docs/elsewhere/'), /outside documentation base/);
  assert.throws(() => outputPath('/tmp/site', '/docs/xy/%2E%2E/secret'), /unsafe documentation link/);
});
