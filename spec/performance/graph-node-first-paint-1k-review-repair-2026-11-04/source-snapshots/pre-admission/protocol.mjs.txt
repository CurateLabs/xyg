// Evidence-only protocol guards, independent of production scheduler internals.
import assert from 'node:assert/strict';
export const same = (a, b) => ['jobId', 'revision', 'step'].every(k => a?.[k] === b?.[k]);
export function validateUnheld(browser, host) {
  assert.equal(browser.mode, 'automatic-after-frame');
  assert.equal(browser.deliberateHolds, 0);
  assert.ok(browser.frames.length >= 2);
  assert.equal(browser.frames[0].phase, 'initial');
  assert.equal(browser.frames.at(-1).phase, 'complete');
  for (const [i, f] of browser.frames.entries()) {
    assert.ok(f.coloredPixels > 0, 'actual visible canvas must contain colored geometry');
    assert.ok(f.paintedMs >= f.receivedMs && f.ackStartedMs >= f.paintedMs);
    assert.ok(f.gpuHit, 'painted frame must support a GPU node hit');
    assert.ok(same(f, host.find(h => same(h, f))), 'frame must match a host checkpoint');
    if (i) assert.ok(f.step > browser.frames[i - 1].step && f.paintedMs > browser.frames[i - 1].paintedMs);
  }
  return { firstCheckpointHostMs: host[0].ms,
    firstPaintedBrowserMs: browser.frames[0].paintedMs,
    firstGpuPickReadyBrowserMs: browser.frames[0].gpuPickReadyMs,
    unheldPaintIntervalsMs: browser.frames.slice(1).map((f, i) => f.paintedMs - browser.frames[i].paintedMs) };
}
export function validateClick(location, click) {
  assert.equal(click.trusted, true);
  assert.equal(click.pointer?.downTrusted, true);
  assert.equal(click.pointer?.upTrusted, true);
  assert.ok(same(location, click));
  assert.equal(click.detail.trace, location.hit.trace);
  assert.equal(click.detail.index, location.hit.index);
  assert.ok(click.identity.uuid);
  assert.equal(click.identity.uuid, click.detail.row.id);
}
