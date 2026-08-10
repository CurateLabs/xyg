import assert from "node:assert/strict";
import test from "node:test";

import {
  PROTOCOL_VERSION,
  composeGraph,
  figure,
  normalizeGraphInputs,
  runForceTicks,
  runLayout,
} from "../src/index.js";

test("normalize + circle runLayout emits positions and meta", () => {
  const data = normalizeGraphInputs(
    ["a", "b", "c", "d"],
    [
      ["a", "b"],
      ["b", "c"],
      ["c", "d"],
      ["d", "a"],
    ],
  );
  assert.equal(data.nNodes, 4);
  assert.equal(data.nEdges, 4);
  assert.deepEqual([...data.sources], [0n, 1n, 2n, 3n]);
  assert.deepEqual([...data.targets], [1n, 2n, 3n, 0n]);

  const { nodePositions, edgeSegments, meta } = runLayout(data, {
    layout: "circle",
    seed: 1,
  });
  assert.equal(nodePositions.x.length, 4);
  assert.equal(edgeSegments.x0.length, 4);
  assert.equal(meta.layout, "circle");
  assert.equal(meta.source_n_nodes, 4);
  assert.equal(meta.lod_tier, 0);
  assert.ok(meta.member_of instanceof BigUint64Array);
  assert.ok(meta.csr_offsets instanceof BigUint64Array);
});

test("composeGraph + figure.buildPayload protocol subset", () => {
  const fig = figure({ width: 400, height: 300 });
  fig.graph(
    ["a", "b", "c", "d"],
    [
      ["a", "b"],
      ["b", "c"],
      ["c", "d"],
      ["d", "a"],
    ],
    { layout: "circle", seed: 1 },
  );
  const { spec, buffers } = fig.buildPayload();
  assert.equal(spec.protocol, PROTOCOL_VERSION);
  assert.deepEqual(
    spec.traces.map((t) => t.kind),
    ["segments", "scatter"],
  );
  assert.ok(Array.isArray(spec.graph));
  assert.equal(spec.graph[0].layout, "circle");
  assert.ok(Buffer.isBuffer(buffers));
  assert.ok(buffers.length > 0);
  // columns carry offset/scale from xy_encode_f32
  assert.ok(spec.columns.every((c) => typeof c.offset === "number"));
});

test("composeGraph helper returns traces ready for figure", () => {
  const composed = composeGraph(["n0", "n1"], [["n0", "n1"]], { layout: "grid" });
  assert.equal(composed.traces.length, 2);
  assert.equal(composed.traces[0].kind, "segments");
  assert.equal(composed.traces[1].kind, "scatter");
  assert.equal(composed.graphMeta.layout, "grid");
});

test("force_scheduler chunked setImmediate completes", async () => {
  const sources = new BigUint64Array([0n, 1n, 2n]);
  const targets = new BigUint64Array([1n, 2n, 0n]);
  const ticks = [];
  const result = await runForceTicks({
    nNodes: 3,
    sources,
    targets,
    seed: 7,
    totalSteps: 20,
    chunkSteps: 5,
    mode: "immediate",
    onTick: (state) => ticks.push(state.step),
  });
  assert.equal(result.steps, 20);
  assert.equal(result.x.length, 3);
  assert.deepEqual(ticks, [5, 10, 15, 20]);
});
