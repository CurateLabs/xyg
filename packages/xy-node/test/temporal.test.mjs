/**
 * Canonical i64 temporal columns and interval indexes (#43).
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  TEMPORAL_DISAMBIGUATION,
  TEMPORAL_DST,
  TEMPORAL_PRECISION,
  TemporalNativeError,
  temporalColumnCreate,
  temporalColumnDestroy,
  temporalColumnRead,
  temporalEventsInRange,
  temporalIntervalIndexCreate,
  temporalIntervalIndexDestroy,
  temporalIntervalVisibilityAt,
} from "../src/abi.js";

const SUB_MS_MICROS = 1704067200000123n;

test("exact timestamp survives Node roundtrip", () => {
  const handle = temporalColumnCreate({
    values: [SUB_MS_MICROS],
    validity: [1],
    timezone: "UTC",
    unit: TEMPORAL_PRECISION.microsecond,
  });
  try {
    const { values, validity, timezone, precision } = temporalColumnRead(handle);
    assert.deepEqual(Array.from(values), [SUB_MS_MICROS]);
    assert.deepEqual(Array.from(validity), [1]);
    assert.equal(timezone, "UTC");
    assert.equal(precision, TEMPORAL_PRECISION.microsecond);
  } finally {
    temporalColumnDestroy(handle);
  }
});

test("millisecond unit normalizes to micros", () => {
  const handle = temporalColumnCreate({
    values: [1704067200000n],
    validity: [1],
    timezone: "America/New_York",
    unit: TEMPORAL_PRECISION.millisecond,
  });
  try {
    const { values, timezone, precision } = temporalColumnRead(handle);
    assert.deepEqual(Array.from(values), [1704067200000000n]);
    assert.equal(timezone, "America/New_York");
    assert.equal(precision, TEMPORAL_PRECISION.millisecond);
  } finally {
    temporalColumnDestroy(handle);
  }
});

test("DST gap and fold outcomes", () => {
  assert.throws(
    () => temporalColumnCreate({
      values: [0n],
      validity: [1],
      timezone: "America/New_York",
      naive: true,
      dstStatus: [TEMPORAL_DST.gap],
      offsetSeconds: [0],
      foldLaterOffsetSeconds: [0],
    }),
    (error) => error instanceof TemporalNativeError && error.nativeCode === -5,
  );
  assert.throws(
    () => temporalColumnCreate({
      values: [0n],
      validity: [1],
      timezone: "America/New_York",
      naive: true,
      disambiguation: TEMPORAL_DISAMBIGUATION.reject,
      dstStatus: [TEMPORAL_DST.fold],
      offsetSeconds: [-14400],
      foldLaterOffsetSeconds: [-18000],
    }),
    (error) => error instanceof TemporalNativeError && error.nativeCode === -6,
  );
});

test("interval boundaries are end-exclusive", () => {
  const handle = temporalIntervalIndexCreate({
    starts: [10n, 0n, 50n],
    startValid: [1, 0, 1],
    ends: [20n, 40n, 0n],
    endValid: [1, 1, 0],
  });
  try {
    assert.deepEqual(Array.from(temporalIntervalVisibilityAt(handle, 10n)), [1, 1, 0]);
    assert.deepEqual(Array.from(temporalIntervalVisibilityAt(handle, 20n)), [0, 1, 0]);
    assert.deepEqual(Array.from(temporalIntervalVisibilityAt(handle, 50n)), [0, 0, 1]);
  } finally {
    temporalIntervalIndexDestroy(handle);
  }
});

test("reversed interval fails before output", () => {
  assert.throws(
    () => temporalIntervalIndexCreate({
      starts: [5n],
      startValid: [1],
      ends: [5n],
      endValid: [1],
    }),
    (error) => error instanceof TemporalNativeError && error.nativeCode === -7,
  );
});

test("events in range are half-open", () => {
  const visible = temporalEventsInRange({
    eventMicros: [10n, 20n, 30n],
    eventValid: [1, 1, 1],
    rangeStart: 10n,
    rangeEnd: 30n,
  });
  assert.deepEqual(Array.from(visible), [1, 1, 0]);
});
