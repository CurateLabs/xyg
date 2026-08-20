/**
 * TemporalController coordination (#44).
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  TemporalNativeError,
  temporalControllerApplyEvent,
  temporalControllerCreate,
  temporalControllerDestroy,
  temporalControllerDispose,
  temporalControllerPlay,
  temporalControllerPollEvent,
  temporalControllerSetCursor,
  temporalControllerState,
  temporalControllerStep,
  temporalCoordinateDeliver,
} from "../src/abi.js";

function make(instanceId, groupId = 0n) {
  return temporalControllerCreate({
    instanceId,
    groupId,
    domainStart: 0n,
    domainEnd: 1_000_000n,
    cursor: 100_000n,
    window: 50_000n,
    step: 10_000n,
    rateMilli: 1000,
    loopEnabled: true,
  });
}

test("linked views coordinate once", () => {
  const a = make(1n, 7n);
  const b = make(2n, 7n);
  const c = make(3n, 9n);
  try {
    temporalControllerSetCursor(a, 200_000n);
    const event = temporalControllerPollEvent(a);
    assert.ok(event);
    assert.equal(event.sourceInstance, 1n);
    assert.equal(temporalControllerApplyEvent(b, event), true);
    assert.equal(temporalControllerState(b).cursor, 200_000n);
    assert.throws(
      () => temporalControllerApplyEvent(a, event),
      (error) => error instanceof TemporalNativeError && error.nativeCode === -15,
    );
    assert.equal(temporalControllerApplyEvent(c, event), false);
    assert.equal(temporalControllerState(c).cursor, 100_000n);
  } finally {
    temporalControllerDestroy(a);
    temporalControllerDestroy(b);
    temporalControllerDestroy(c);
  }
});

test("disposal stops playback", () => {
  const handle = make(1n);
  try {
    temporalControllerPlay(handle);
    assert.equal(temporalControllerState(handle).playing, true);
    temporalControllerDispose(handle);
    const state = temporalControllerState(handle);
    assert.equal(state.playing, false);
    assert.equal(state.disposed, true);
  } finally {
    temporalControllerDestroy(handle);
  }
});

test("same-process deliver updates peers", () => {
  const a = make(1n, 5n);
  const b = make(2n, 5n);
  try {
    temporalControllerSetCursor(a, 300_000n);
    const event = temporalControllerPollEvent(a);
    assert.equal(temporalCoordinateDeliver(event), 1);
    assert.equal(temporalControllerState(b).cursor, 300_000n);
    temporalControllerStep(a);
  } finally {
    temporalControllerDestroy(a);
    temporalControllerDestroy(b);
  }
});
