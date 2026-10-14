/** Check the publishable static site, including links and native chart assets. */
import assert from 'node:assert/strict';
import { readFile, readdir, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const APP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const BASE = '/docs/xy';
const unescape = (text) => text.replace(/&amp;/g, '&').replace(/&quot;/g, '"')
  .replace(/&#39;|&apos;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>');
export const plainText = (html) => unescape(html.replace(/<[^>]*>/g, ' ')).replace(/\s+/g, ' ');

async function exists(file) {
  try { return (await stat(file)).isFile(); } catch { return false; }
}

export function outputPath(dist, pathname) {
  const decoded = decodeURIComponent(pathname);
  assert.ok(decoded === BASE || decoded.startsWith(`${BASE}/`), `outside documentation base: ${pathname}`);
  const relative = decoded.slice(BASE.length).replace(/^\/+/, '');
  const file = path.resolve(dist, relative);
  assert.ok(file === dist || file.startsWith(`${dist}${path.sep}`), `unsafe documentation link: ${pathname}`);
  return path.extname(relative) || relative === '.md' || relative.endsWith('/.md') ? file : path.join(file, 'index.html');
}

export async function checkLink(dist, route, href) {
  href = unescape(href);
  if (!href || /^(?:[a-z][a-z\d+.-]*:|\/\/)/i.test(href)) return;
  let target = new URL(href, `https://documentation.invalid${route}`);
  let file;
  let html;
  for (let hops = 0; ; hops++) {
    assert.ok(hops < 5, `${route}: redirect loop for ${href}`);
    file = outputPath(dist, target.pathname);
    assert.ok(await exists(file), `${route}: missing target ${href}`);
    if (!file.endsWith('.html')) break;
    html = await readFile(file, 'utf8');
    const refresh = html.match(/<meta\b[^>]*http-equiv=["']refresh["'][^>]*content=["'][^"']*?url=([^"']+)["']/i);
    if (!refresh) break;
    const destination = new URL(unescape(refresh[1]), target);
    if (!destination.hash) destination.hash = target.hash;
    target = destination;
  }
  if (target.hash && file.endsWith('.html')) {
    const ids = new Set([...html.matchAll(/\bid=["']([^"']+)["']/g)].map((m) => unescape(m[1])));
    const anchor = decodeURIComponent(target.hash.slice(1));
    assert.ok(ids.has(anchor), `${route}: missing anchor ${href}`);
  }
}

export async function validateSite(app = APP) {
  const dist = path.resolve(app, 'dist');
  const manifest = JSON.parse(await readFile(path.join(app, '.generated/content-manifest.json'), 'utf8'));
  const examples = JSON.parse(await readFile(path.join(app, '.generated/examples.json'), 'utf8'));
  const summary = JSON.parse(await readFile(path.join(app, '.generated/examples-summary.json'), 'utf8'));
  assert.equal(manifest.base, BASE);
  assert.ok(manifest.pages.length > 50, 'public documentation unexpectedly lost most pages');
  assert.deepEqual(summary.errors, [], 'native example compilation errors');
  const routes = new Set(manifest.pages.map((page) => page.route));
  for (const required of [BASE + '/', BASE + '/integrations/graphforge/', BASE + '/core-concepts/rust-engine-and-host-parity/', BASE + '/charts/graph/']) {
    assert.ok(routes.has(required), `missing public entry point ${required}`);
  }
  assert.ok(!routes.has(BASE + '/integrations/reflex/'), 'upstream integration is promoted as a public entry point');
  await checkLink(dist, `${BASE}/`, `${BASE}/integrations/reflex/`);
  const llmsIndex = await readFile(path.join(dist, 'llms.txt'), 'utf8');
  const llmsFull = await readFile(path.join(dist, 'llms-full.txt'), 'utf8');
  let linkCount = 0;
  let referenceCount = 0;
  let previewCount = 0;
  const framePaths = new Set();
  for (const page of manifest.pages) {
    const file = outputPath(dist, page.route);
    const html = await readFile(file, 'utf8');
    const text = plainText(html);
    assert.match(html, /<title>[^<]*XYG/, `${page.route}: missing XYG title`);
    assert.match(html, /<meta\s+[^>]*name=["']description["']/, `${page.route}: missing description`);
    assert.doesNotMatch(text, /pip install reflex|import reflex(?:_xy)?|from reflex(?:_xy)?|reflex run|Reflex XYG/, `${page.route}: upstream runtime promotion`);
    const raw = await readFile(outputPath(dist, page.markdown), 'utf8');
    const alias = await readFile(outputPath(dist, `${page.route}.md`), 'utf8');
    assert.equal(alias, raw, `${page.route}: downloadable Markdown alias differs`);
    assert.ok(llmsIndex.includes(page.markdown) || llmsIndex.includes(page.route), `${page.route}: missing llms index entry`);
    assert.ok(llmsFull.includes(raw.trim()), `${page.route}: llms full content differs from downloadable Markdown`);
    for (const component of page.components ?? []) {
      assert.ok(raw.includes(component), `${page.route}: Markdown missing API ${component}`);
      assert.ok(text.includes(component), `${page.route}: HTML missing API ${component}`);
      referenceCount++;
    }
    for (const match of html.matchAll(/\b(?:href|src)=["']([^"']+)["']/g)) {
      await checkLink(dist, page.route, match[1]);
      linkCount++;
    }
    for (const record of examples[page.source] ?? []) {
      assert.doesNotMatch(record.code, /\b(?:reflex_xy|xy_docs|rx)\./, `${page.route}: retained framework code`);
      for (const preview of record.previews) {
        assert.ok(html.includes(preview.src), `${page.route}: missing native preview ${preview.src}`);
        framePaths.add(outputPath(dist, preview.src));
        previewCount++;
      }
      if (record.note) assert.ok(text.includes(record.note), `${page.route}: missing preview limitation`);
    }
    const canonical = html.match(/<link\b[^>]*rel=["']canonical["'][^>]*href=["']([^"']+)["']/);
    if (!process.env.XY_DOCS_PUBLIC_URL) {
      assert.equal(canonical, null, `${page.route}: invented public canonical origin`);
    } else if (canonical) {
      assert.equal(new URL(unescape(canonical[1])).origin, new URL(process.env.XY_DOCS_PUBLIC_URL).origin);
    }
  }
  // Use the shipped client decoder rather than another implementation of XYBF.
  const { decodeFrame } = await import(pathToFileURL(path.resolve(app, '../../packages/xy-client/dist/index.js')));
  for (const file of framePaths) {
    const bytes = await readFile(file);
    assert.equal(bytes.subarray(0, 4).toString(), 'XYBF', `${file}: invalid binary snapshot`);
    const decoded = decodeFrame(bytes);
    assert.ok(decoded.message.traces.length > 0, `${file}: empty chart snapshot`);
    assert.equal(decoded.buffers.length, 1, `${file}: expected packed painter buffer`);
  }
  assert.equal(previewCount, summary.previews, 'some generated charts vanished from the site');
  assert.ok(previewCount > 100, 'public examples unexpectedly lost most native previews');
  assert.ok(referenceCount > 20, 'generated API reference coverage disappeared');
  const sitePackage = JSON.parse(await readFile(path.join(app, 'package.json'), 'utf8'));
  assert.ok(sitePackage.dependencies['@astrojs/starlight'], 'docs shell must use Starlight');
  assert.doesNotMatch(JSON.stringify(sitePackage), /reflex/i, 'docs runtime depends on upstream framework');
  // Retired routes are still user entry points, even without inbound links.
  // Verify each generated redirect resolves to an existing page and fragment.
  for (const name of await readdir(dist, { recursive: true })) {
    if (!name.endsWith('.html')) continue;
    const html = await readFile(path.join(dist, name), 'utf8');
    if (!/<meta\b[^>]*http-equiv=["']refresh["']/i.test(html)) continue;
    const route = `${BASE}/${name.replace(/index\.html$/, '')}`;
    await checkLink(dist, route, route);
    linkCount++;
  }
  const files = await readdir(dist);
  assert.ok(files.includes('_astro'), 'production client assets are missing');
  return { pages: manifest.pages.length, links: linkCount, references: referenceCount, previews: previewCount, uniqueSnapshots: framePaths.size };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  console.log('Verified Starlight production output:', await validateSite());
}
