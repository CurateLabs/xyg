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
  temporalControllerSetDirection,
  temporalControllerSetLoop,
  temporalControllerSetRange,
  temporalControllerSetRateMilli,
  temporalControllerSetReducedMotion,
  temporalControllerState,
  temporalControllerStep,
  temporalControllerTick,
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

test("inbound events reject noncanonical identity and geometry", () => {
  const handle = make(2n, 7n);
  const canonical = {
    groupId: 7n,
    sourceInstance: 1n,
    revision: 1n,
    rangeStart: 100_000n,
    rangeEnd: 250_000n,
    cursor: 200_000n,
    window: 150_000n,
  };
  try {
    for (const mutation of [
      { sourceInstance: 0n },
      { revision: 0n },
      { rangeStart: -1n },
      { rangeEnd: 1_000_001n },
      { rangeStart: 250_000n, rangeEnd: 100_000n },
      { cursor: 250_001n },
      { window: -1n },
      { window: 149_999n },
      { rangeStart: 100_000n, rangeEnd: 100_001n, cursor: 100_000n, window: 1n },
    ]) {
      assert.throws(
        () => temporalControllerApplyEvent(handle, { ...canonical, ...mutation }),
        (error) => error instanceof TemporalNativeError,
      );
    }
  } finally {
    temporalControllerDestroy(handle);
  }
});

test("single-instant ranges and repeated setters are canonical no-ops", () => {
  const handle = make(20n, 17n);
  try {
    const initial = temporalControllerState(handle);
    temporalControllerSetRange(handle, initial.rangeStart, initial.rangeEnd);
    temporalControllerSetCursor(handle, initial.cursor);
    assert.equal(temporalControllerState(handle).revision, initial.revision);
    assert.equal(temporalControllerPollEvent(handle), null);
    temporalControllerSetRange(handle, 100n, 101n);
    assert.equal(temporalControllerState(handle).window, 0n);
  } finally {
    temporalControllerDestroy(handle);
  }
});

test("tick at a non-looping bound reports no movement and stops playback", () => {
  const handle = make(22n);
  try {
    temporalControllerSetLoop(handle, false);
    temporalControllerSetCursor(handle, 1_000_000n);
    temporalControllerPlay(handle);
    const revision = temporalControllerState(handle).revision;
    assert.equal(temporalControllerTick(handle, 20_000n), false);
    const state = temporalControllerState(handle);
    assert.equal(state.cursor, 999_999n);
    assert.equal(state.playing, false);
    assert.equal(state.revision, revision);
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

test("exchange groups reject duplicate live instance identities", () => {
  const first = make(31n, 23n);
  try {
    assert.throws(() => make(31n, 23n), TemporalNativeError);
    temporalControllerDispose(first);
    const replacement = make(31n, 23n);
    temporalControllerDestroy(replacement);
  } finally {
    temporalControllerDestroy(first);
  }
});

test("same-process deliver validates malformed events without peers", () => {
  assert.throws(() => temporalCoordinateDeliver({
    groupId: 24n,
    sourceInstance: 1n,
    revision: 1n,
    rangeStart: 10n,
    rangeEnd: 20n,
    cursor: 20n,
    window: 10n,
  }), TemporalNativeError);
});

test("host rejects every temporal scalar before native coercion", () => {
  const handle = make(1n, 7n);
  try {
    const invalid = [
      () => temporalControllerCreate({
        instanceId: 9n, domainStart: Number.MAX_SAFE_INTEGER + 1, domainEnd: 10n,
      }),
      () => temporalControllerCreate({
        instanceId: 9n, domainStart: 0n, domainEnd: 10n, loopEnabled: 1,
      }),
      () => temporalControllerState(-1),
      () => temporalControllerState(2n ** 64n),
      () => temporalControllerSetRange(handle, Number.MAX_SAFE_INTEGER + 1, 10n),
      () => temporalControllerSetCursor(handle, 2n ** 63n),
      () => temporalControllerTick(handle, -(2n ** 63n) - 1n),
      () => temporalControllerSetRateMilli(handle, "1000"),
      () => temporalControllerSetRateMilli(handle, 2 ** 32),
      () => temporalControllerSetDirection(handle, 1n),
      () => temporalControllerSetDirection(handle, 2 ** 31),
      () => temporalControllerSetLoop(handle, 1),
      () => temporalControllerSetReducedMotion(handle, "false"),
      () => temporalControllerApplyEvent(handle, {
        groupId: 7n,
        sourceInstance: 2n,
        revision: 1n,
        rangeStart: Number.MAX_SAFE_INTEGER + 1,
        rangeEnd: 10n,
        cursor: 1n,
        window: 9n,
      }),
    ];
    for (const call of invalid) assert.throws(call, /must/);
  } finally {
    temporalControllerDestroy(handle);
  }
});
