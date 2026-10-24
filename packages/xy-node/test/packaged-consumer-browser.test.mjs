import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { EventEmitter } from 'node:events';
import test from 'node:test';
import { captureModuleResponses } from '../../../scripts/packaged_consumer_browser.mjs';

const moduleUrl = 'http://127.0.0.1/corrupt.wasm';
const bytes = Buffer.from([0, 1, 2, 3]);
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

async function fixture(status = 200) {
  const context = new EventEmitter(), body = deferred(), delivered = deferred();
  const errors = [], external = [];
  let handler, fetches = 0, aborted = 0;
  context.route = async (_, callback) => { handler = callback; };
  const collector = await captureModuleResponses(context, moduleUrl, external, errors, 100);
  const response = { url: () => moduleUrl, status: () => status,
    // The queue failure: a real Worker can already be gone at observation time.
    body: async () => { throw Error('response.body: Target page, context or browser has been closed'); } };
  const route = {
    request: () => ({ url: () => moduleUrl }),
    fetch: async options => {
      fetches++;
      assert.deepEqual(options, { timeout: 100, maxRedirects: 0, maxRetries: 0 });
      return { status: () => status, ok: () => status === 200, body: () => body.promise };
    },
    fulfill: async options => { assert.equal(options.body, bytes); delivered.resolve(); },
    abort: async () => { aborted++; },
  };
  return { context, collector, errors, external, body, delivered, route, response,
    start: () => handler(route), counts: () => ({ fetches, aborted }) };
}

test('module evidence awaits delayed body and response event without reading the terminated Worker', async () => {
  const f = await fixture();
  const transfer = f.start();
  let finished = false;
  const collected = f.collector.wait().then(() => { finished = true; });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(f.collector.assetResponses.length, 0);
  assert.equal(finished, false);
  f.body.resolve(bytes);
  await f.delivered.promise;
  await transfer;
  assert.equal(finished, false, 'a completed transfer is not browser response evidence');
  f.context.emit('response', f.response);
  await collected;
  assert.deepEqual(f.collector.assetResponses, [{ url: moduleUrl, status: 200, bytes: 4,
    sha256: createHash('sha256').update(bytes).digest('hex') }]);
  assert.deepEqual(f.counts(), { fetches: 1, aborted: 0 });
  assert.deepEqual(f.errors, []);
});

test('missing module retains HTTP failure without a Worker body read', async () => {
  const f = await fixture(404), transfer = f.start();
  f.body.resolve(bytes);
  await transfer;
  f.context.emit('response', f.response);
  await f.collector.wait();
  assert.deepEqual(f.collector.assetResponses, [{ url: moduleUrl, status: 404, bytes: null, sha256: null }]);
});

test('missing browser response fails closed instead of accepting a transfer snapshot', async () => {
  const f = await fixture();
  f.body.resolve(bytes);
  await f.start();
  await assert.rejects(f.collector.wait(), /module response collection timed out/);
});

test('body collection failure fails closed and aborts delivery', async () => {
  const f = await fixture(), transfer = f.start();
  const collected = assert.rejects(f.collector.wait(), /body unavailable/);
  f.body.reject(Error('body unavailable'));
  await transfer;
  await collected;
  assert.deepEqual(f.errors, ['body unavailable']);
  assert.deepEqual(f.counts(), { fetches: 1, aborted: 1 });
  assert.deepEqual(f.collector.assetResponses, []);
});

test('duplicate or unexpected module responses fail closed, including after the first wait', async () => {
  for (const url of [moduleUrl, 'http://127.0.0.1/unexpected.wasm']) {
    const f = await fixture();
    f.body.resolve(bytes);
    await f.start();
    f.context.emit('response', f.response);
    await f.collector.wait();
    f.context.emit('response', { ...f.response, url: () => url });
    await assert.rejects(f.collector.wait(), { code: 'ERR_ASSERTION' });
  }
  const f = await fixture();
  f.route.request = () => ({ url: () => 'http://127.0.0.1/unexpected.wasm' });
  await f.start();
  await assert.rejects(f.collector.wait(), /unexpected module request/);
  assert.deepEqual(f.counts(), { fetches: 0, aborted: 1 });
});
