import assert from "node:assert/strict";
import test from "node:test";

import {
  abiVersion,
  graphBuildCsr,
  graphBuildRender,
  graphClusterAggregate,
  graphForceCreate,
  graphForceDestroy,
  graphForceTick,
  graphLayout,
  graphLodDecision,
  graphSampleEdges,
  sankeyLayout,
} from "../src/index.js";

const EXPECTED_ABI = Number(process.env.XY_EXPECTED_ABI ?? 54);

test("abi version matches expected", () => {
  assert.equal(abiVersion(), EXPECTED_ABI);
});

test("circle layout length and values", () => {
  const sources = new BigUint64Array([0n, 1n, 2n]);
  const targets = new BigUint64Array([1n, 2n, 0n]);
  const a = graphLayout("circle", 4, sources, targets);
  assert.equal(a.x.length, 4);
  assert.equal(a.y.length, 4);
  assertFloatArrayClose(a.x, [4, 0, -4, 0]);
  assertFloatArrayClose(a.y, [0, 4, 0, -4]);
  const b = graphLayout("circle", 4, sources, targets);
  assert.deepEqual([...a.x], [...b.x]);
  assert.deepEqual([...a.y], [...b.y]);
});

test("seeded force is deterministic across two calls", () => {
  const sources = new BigUint64Array([0n, 1n, 2n]);
  const targets = new BigUint64Array([1n, 2n, 0n]);

  const oneShotA = graphLayout("force", 3, sources, targets, { seed: 7 });
  const oneShotB = graphLayout("force", 3, sources, targets, { seed: 7 });
  assert.deepEqual([...oneShotA.x], [...oneShotB.x]);
  assert.deepEqual([...oneShotA.y], [...oneShotB.y]);

  const first = graphForceCreate(3, sources, targets, { seed: 7n });
  const second = graphForceCreate(3, sources, targets, { seed: 7n });
  try {
    const a = graphForceTick(first, 3, 20);
    const b = graphForceTick(second, 3, 20);
    assert.deepEqual([...a.x], [...b.x]);
    assert.deepEqual([...a.y], [...b.y]);
    assert.equal(a.alpha, b.alpha);
  } finally {
    graphForceDestroy(first);
    graphForceDestroy(second);
  }
});

test("hierarchical/dagre differ from undirected breadthfirst on a DAG", () => {
  // Edges 0→1→2 and 3→2: BFS from 0 places 3 at layer 3; hierarchical roots 0,3 at layer 0.
  const sources = new BigUint64Array([0n, 1n, 3n]);
  const targets = new BigUint64Array([1n, 2n, 2n]);
  const breadthfirst = graphLayout("breadthfirst", 4, sources, targets);
  const hierarchical = graphLayout("hierarchical", 4, sources, targets);
  const dagre = graphLayout("dagre", 4, sources, targets);
  assert.notDeepEqual([...hierarchical.y], [...breadthfirst.y]);
  assert.deepEqual([...hierarchical.x], [...dagre.x]);
  assert.deepEqual([...hierarchical.y], [...dagre.y]);
  assert.ok(Math.abs(hierarchical.y[3]) < 1e-12);
  assert.ok(Math.abs(breadthfirst.y[3] + 3.0) < 1e-12);
});

test("LOD edge sample tier and edge sampling", () => {
  const decision = graphLodDecision(100, 10_000, {
    nodeBudget: 50_000,
    edgeBudget: 1_000,
  });
  assert.equal(decision.tier, 1); // EdgeSample
  assert.equal(decision.edgesKept, 1_000n);
  assert.deepEqual([...graphSampleEdges(10, 3)], [0n, 3n, 6n]);
});

test("cluster aggregate records Aggregate tier and centroids", () => {
  const clustered = graphClusterAggregate(
    new Float64Array([0, 1, 0, 100, 101, 100]),
    new Float64Array([0, 0, 1, 100, 100, 101]),
    { nEdges: 3, nodeBudget: 2, edgeBudget: 500 },
  );
  assert.equal(clustered.tier, 2); // Aggregate
  assert.equal(clustered.edgesKept, 3n);
  assert.equal(clustered.x.length, 2);
  assert.deepEqual([...clustered.memberOf], [0n, 0n, 0n, 1n, 1n, 1n]);
});

test("CSR build returns u64 offsets and neighbors", () => {
  const sources = new BigUint64Array([0n, 1n]);
  const targets = new BigUint64Array([1n, 2n]);
  const { offsets, neighbors } = graphBuildCsr(3, sources, targets, { directed: false });
  assert.ok(offsets instanceof BigUint64Array);
  assert.ok(neighbors instanceof BigUint64Array);
  assert.deepEqual([...offsets], [0n, 1n, 3n, 4n]);
  assert.deepEqual([...neighbors], [1n, 0n, 2n, 1n]);
});

test("simple two-node sankey layout succeeds in the unit box", () => {
  const layout = sankeyLayout(
    2,
    new BigUint64Array([0n]),
    new BigUint64Array([1n]),
    new Float64Array([1]),
  );
  assert.equal(layout.layers, 2);
  assert.deepEqual([...layout.layer], [0, 1]);
  for (const key of ["x0", "y0", "x1", "y1", "sourceY0", "sourceY1", "targetY0", "targetY1"]) {
    for (const value of layout[key]) {
      assert.ok(Number.isFinite(value), `${key} contains non-finite value ${value}`);
      assert.ok(value >= 0 && value <= 1, `${key} value ${value} outside unit box`);
    }
  }
});

function assertFloatArrayClose(actual, expected, epsilon = 1e-12) {
  assert.equal(actual.length, expected.length);
  for (let i = 0; i < actual.length; i += 1) {
    assert.ok(Math.abs(actual[i] - expected[i]) <= epsilon, `index ${i}: ${actual[i]} != ${expected[i]}`);
  }
}

test("graphBuildRender respects node/edge budgets", () => {
  const x = new Float64Array([0, 1, 0, 100, 101, 100]);
  const y = new Float64Array([0, 0, 1, 100, 100, 101]);
  const sources = [0n, 1n, 3n, 4n, 0n];
  const targets = [1n, 2n, 4n, 5n, 3n];
  const out = graphBuildRender(x, y, sources, targets, { nodeBudget: 2, edgeBudget: 4 });
  assert.equal(out.tier, 2);
  assert.ok(out.x.length <= 2);
  assert.ok(out.edgeSources.length <= 4);
  assert.deepEqual([...out.memberOf], [0n, 0n, 0n, 1n, 1n, 1n]);
});
