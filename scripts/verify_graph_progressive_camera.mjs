import assert from 'node:assert/strict';

// Verify the host-button camera route, separately from canvas drag gestures.
export function assertProgressiveCameraPan(view) {
  const admitted=view.pans.filter(p=>p.trusted===true && p.after && !p.after.relayout?.done);
  assert.ok(admitted.length,'trusted unfinished host camera pan');
  for(const pan of admitted) {
    assert.equal(pan.before.camera.length,7);
    assert.ok(pan.before.camera.every(Number.isFinite));
    const expected=[...pan.before.camera];expected[2]+=12;
    assert.deepEqual(pan.after.camera,expected,'requested camera translation and unchanged components');
  }
  const pan=admitted.at(-1),expected=[...pan.before.camera];expected[2]+=12;
  const later=view.frames.filter(frame=>frame.at>pan.returned && BigInt(frame.progress.steps)>BigInt(pan.after.relayout.steps));
  assert.ok(later.length,'camera survives a later Rust continuation');
  for(const frame of later)assert.deepEqual(frame.camera,expected,'continuation preserves camera');
  assert.deepEqual(view.finalSnapshot.camera,expected,'final camera preserves translation');
}
