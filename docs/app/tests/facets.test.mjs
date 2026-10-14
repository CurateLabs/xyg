import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const app = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const examples = JSON.parse(readFileSync(path.join(app, '.generated/examples.json'), 'utf8'));
const manifest = JSON.parse(readFileSync(path.join(app, '.generated/content-manifest.json'), 'utf8'));
const full = readFileSync(path.join(app, 'public/llms-full.txt'), 'utf8');

function facetRecord(source) {
  const records = examples[source].filter((record) => record.previews.some((preview) => preview.facet));
  assert.equal(records.length, 1, `${source}: one authored facet group`);
  return records[0];
}

function assertFacet(source, expected) {
  const record = facetRecord(source);
  const facet = record.previews[0].facet;
  assert.equal(facet.cols, expected.cols);
  assert.equal(facet.gap, expected.gap);
  assert.equal(facet.title, expected.title);
  assert.equal(facet.height, expected.height);
  assert.equal(record.previews.length, expected.panels);
  assert.equal(facet.count, expected.panels);
  assert.match(facet.group, /^[a-f\d]{24}$/);
  assert.deepEqual(record.previews.map((preview) => preview.facet.panel),
    Array.from({ length: expected.panels }, (_, index) => index));
  assert.ok(record.previews.every((preview) => preview.facet.group === facet.group));

  const page = manifest.pages.find((entry) => entry.source === source);
  assert.ok(page, 'facet guide remains in the public inventory');
  const markdown = readFileSync(path.join(app, 'public', page.markdown.slice('/docs/xy/'.length)), 'utf8');
  const section = markdown.match(new RegExp(`<section[^>]*data-facet-group="${facet.group}"[^>]*>[\\s\\S]*?<\/section>`))?.[0];
  assert.ok(section, 'native panels retain a single facet section');
  assert.match(section, /class="xyg-facets not-content"/);
  assert.match(section, new RegExp(`data-facet-cols="${expected.cols}"`));
  assert.match(section, new RegExp(`--xyg-facet-gap:${expected.gap}px`));
  assert.match(section, new RegExp(`--xyg-facet-height:${expected.height}px`));
  assert.equal((section.match(/class="xyg-demo not-content"/g) ?? []).length, expected.panels);
  if (expected.title) {
    assert.ok(section.includes(`<div class="xyg-facet-title">${expected.title}</div>`), 'authored grid title is visible');
  } else {
    assert.ok(!section.includes('class="xyg-facet-title"'), 'untitled grids do not invent a heading');
  }
  for (const preview of record.previews) {
    assert.ok(section.includes(`data-payload="${preview.src}"`), 'every panel retains its native payload');
    assert.ok(section.includes(`aria-label="${preview.title}"`), 'panel labels remain distinct');
    const bytes = readFileSync(path.join(app, 'public', preview.src.slice('/docs/xy/'.length)));
    assert.ok(bytes.length > 100, 'panel is a populated native binary frame');
    assert.ok(page.previews.some((listed) => listed.src === preview.src && listed.facet?.group === facet.group),
      'public inventory keeps facet metadata on each original flat preview');
  }
  assert.ok(full.includes(markdown), 'agent content uses the identical facet markup and source');
  const slug = page.route.slice('/docs/xy/'.length);
  assert.equal(readFileSync(path.join(app, 'public', slug, '.md'), 'utf8'), markdown);
  assert.equal(readFileSync(path.join(app, 'public', slug, 'index.md'), 'utf8'), markdown);
}

test('Regional trends preserves its authored two-column native facet grid and title', () => {
  assertFacet('components/facets-and-layers.md', {
    cols: 2, gap: 12, title: 'Regional trends', height: 260, panels: 2,
  });
});

test('styled facets preserve their three panels, explicit spacing, and absent grid title', () => {
  assertFacet('styling/gallery.md', {
    cols: 3, gap: 16, title: null, height: 230, panels: 3,
  });
});

test('facet grouping retains the full flat native-preview inventory', () => {
  const summary = JSON.parse(readFileSync(path.join(app, '.generated/examples-summary.json'), 'utf8'));
  const previews = Object.values(examples).flatMap((records) => records.flatMap((record) => record.previews));
  assert.equal(previews.length, 179);
  assert.equal(summary.previews, 179);
  assert.deepEqual(summary.errors, []);
  assert.equal(previews.filter((preview) => preview.facet).length, 5);
});
