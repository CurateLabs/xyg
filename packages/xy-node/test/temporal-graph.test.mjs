import assert from "node:assert/strict";
import test from "node:test";

import { TemporalGraph, TemporalGraphError } from "../src/index.js";
import { _assertTemporalGraphRevision } from "../src/abi.js";

function ids(...values) {
  return Uint8Array.from(values.flatMap((value) => Array(16).fill(value)));
}

function graph() {
  return new TemporalGraph({
    nodeIds: ids(1, 2, 3),
    edgeIds: ids(11, 12),
    sourceIds: ids(1, 2),
    targetIds: ids(2, 3),
    nodeValidFrom: {
      values: new BigInt64Array([0n, 10n, 20n]),
      validity: new Uint8Array([1, 1, 1]),
    },
    nodeValidTo: {
      values: new BigInt64Array([30n, 20n, 40n]),
      validity: new Uint8Array([1, 1, 1]),
    },
  });
}

test("temporal graph preserves hidden UUID state and frozen provenance", () => {
  const temporal = graph();
  try {
    assert.equal(temporal.requiredBudget, 12n);
    temporal.setSelection({ nodes: ids(2), edges: ids(11) });
    temporal.setFocus({ kind: "node", id: ids(2) });
    temporal.setPinned(ids(2));
    const frame = temporal.frame({ revision: 1n, cursor: 20n, range: [20n, 21n] });
    assert.deepEqual([...frame.nodeVisibility], [1, 0, 1]);
    assert.deepEqual([...frame.edgeVisibility], [0, 0]);
    assert.deepEqual(frame.selectedVisibleNodeIds, new Uint8Array());
    assert.deepEqual(frame.selectedNodeIds, ids(2));
    assert.deepEqual(frame.selectedEdgeIds, ids(11));
    assert.deepEqual(frame.pinnedNodeIds, ids(2));
    assert.deepEqual(frame.focused, { kind: "node", id: ids(2) });
    assert.equal(frame.focusedVisible, null);
    assert.equal(temporal.snapshot().revision, 1n);
  } finally {
    temporal.close();
  }
});

test("temporal graph rejects budget, stale revisions, and imprecise inputs", () => {
  const temporal = graph();
  try {
    assert.throws(
      () => temporal.frame({ revision: 1n, cursor: 15n, range: [15n, 16n], budget: 11n }),
      (error) => error instanceof TemporalGraphError
        && error.nativeCode === -11
        && error.message.includes("supplied budget"),
    );
    temporal.frame({ revision: 1n, cursor: 15n, range: [15n, 16n] });
    assert.throws(
      () => temporal.frame({ revision: 1n, cursor: 15n, range: [15n, 16n] }),
      (error) => error instanceof TemporalGraphError
        && error.nativeCode === -14
        && error.message.includes("revision is stale"),
    );
    assert.throws(
      () => temporal.frame({ revision: Number.MAX_SAFE_INTEGER + 1, cursor: 15n, range: [15n, 16n] }),
      /revision/,
    );
    temporal.cancel();
  } finally {
    temporal.close();
    temporal.close();
  }
  assert.throws(() => temporal.snapshot(), /closed/);
});

test("temporal graph rejects malformed UUID topology before native reads", () => {
  assert.throws(
    () => new TemporalGraph({
      nodeIds: ids(1, 2),
      edgeIds: ids(11),
      sourceIds: new Uint8Array(),
      targetIds: ids(2),
    }),
    /equal UUID counts/,
  );
  assert.throws(
    () => new TemporalGraph({
      nodeIds: ids(1),
      edgeIds: new Uint8Array(15),
      sourceIds: new Uint8Array(),
      targetIds: new Uint8Array(),
    }),
    /multiple-of-16/,
  );
});

test("temporal graph frame rejects a newer snapshot winner", () => {
  assert.throws(
    () => _assertTemporalGraphRevision({ revision: 2n }, 1n),
    (error) => error instanceof TemporalGraphError && error.nativeCode === -14,
  );
});
