import assert from "node:assert/strict";
import test from "node:test";

import {
  abiVersion,
  composeGraph,
  figure,
  fromGraphForgeTables,
  graphBuildCsr,
  graphBuildRender,
  graphEdgeRouteSegments,
  graphClusterAggregate,
  graphForceCreate,
  graphForceDestroy,
  graphForceTick,
  graphLayout,
  graphLodDecision,
  graphSampleEdges,
  looksLikeGraphForgeTables,
  projectionTooltipRows,
  resolveGraphData,
  sankeyLayout,
} from "../src/index.js";

const EXPECTED_ABI = Number(process.env.XYG_EXPECTED_ABI ?? 81);

test("abi version matches expected", () => {
  assert.equal(abiVersion(), EXPECTED_ABI);
});

test("GraphForge tables preserve UUID identity, parents, and provenance through Rust", () => {
  const a = "00000000-0000-0000-0000-000000000001";
  const b = "00000000-0000-0000-0000-000000000002";
  const edge = "00000000-0000-0000-0000-000000000003";
  const graph = fromGraphForgeTables(
    { node_uuid: [a, b], parent_uuid: [null, a], label: ["root", "child"], provenance_row: [7n, 8n] },
    { edge_uuid: [edge], source_uuid: [a], target_uuid: [b], relationship_type: ["contains"], provenance_row: [9n] },
  );
  assert.deepEqual(graph.ids, [a, b]);
  assert.deepEqual(graph.edgeIds, [edge]);
  assert.deepEqual([...graph.sources], [0n]);
  assert.deepEqual([...graph.targets], [1n]);
  assert.deepEqual([...graph.parentIndices], [0n, 0n]);
  assert.deepEqual([...graph.parentValidity], [0, 1]);
  assert.deepEqual([...graph.nodeProvenanceRows], [7n, 8n]);
  assert.deepEqual([...graph.edgeProvenanceRows], [9n]);
  assert.deepEqual(graph.nodeAttrs.label, ["root", "child"]);
  assert.deepEqual(graph.edgeAttrs.relationship_type, ["contains"]);
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

test("configurable CoSE pins and bounds stay in the Rust kernel", () => {
  const x = new Float64Array([-0.75, 0, 0.75]);
  const y = new Float64Array([0.25, 0, -0.25]);
  const handle = graphForceCreate(
    3,
    new BigUint64Array([0n, 1n]),
    new BigUint64Array([1n, 2n]),
    {
      algorithm: "cose",
      x,
      y,
      pinned: new Uint8Array([1, 0, 0]),
      parents: new BigUint64Array([(1n << 64n) - 1n, 0n, (1n << 64n) - 1n]),
      cose: {
        idealEdgeLength: 0.4,
        repulsionStrength: 2,
        gravityStrength: 0.2,
        coolingFactor: 0.9,
        overlapPadding: 0.5,
        componentSpacing: 3,
        bounds: [-1, -1, 1, 1],
      },
    },
  );
  try {
    const tick = graphForceTick(handle, 3, 20);
    assert.deepEqual([tick.x[0], tick.y[0]], [-0.75, 0.25]);
    assert.ok([...tick.x, ...tick.y].every((value) => value >= -1 && value <= 1));
    assert.ok(Math.abs(tick.alpha - 0.9 ** 20) < 1e-12);
  } finally {
    graphForceDestroy(handle);
  }
});

test("CoSE ergonomic options fail closed instead of falling back", () => {
  assert.throws(
    () => graphForceCreate(1, [], [], { algorithm: "force", cose: {} }),
    /require algorithm='cose'/,
  );
  assert.throws(
    () => graphForceCreate(1, [], [], { algorithm: "cose", cose: { hostForce: 1 } }),
    /unknown CoSE option/,
  );
  assert.throws(
    () => graphForceCreate(1, [], [], { algorithm: "cose", pinned: [1] }),
    /require explicit opts.x and opts.y/,
  );
});

test("force layout catalog names are seeded deterministic", () => {
  const sources = new BigUint64Array([0n, 1n, 2n]);
  const targets = new BigUint64Array([1n, 2n, 0n]);
  const names = [
    "force",
    "fr",
    "spring",
    "forceatlas2",
    "fa2",
    "linlog",
    "yifanhu",
    "kamada_kawai",
    "kk",
    "stress",
    "cose",
  ];
  for (const name of names) {
    const a = graphLayout(name, 3, sources, targets, { seed: 5 });
    const b = graphLayout(name, 3, sources, targets, { seed: 5 });
    assert.deepEqual([...a.x], [...b.x], name);
    assert.deepEqual([...a.y], [...b.y], name);
    const h1 = graphForceCreate(3, sources, targets, { seed: 5, algorithm: name });
    const h2 = graphForceCreate(3, sources, targets, { seed: 5, algorithm: name });
    try {
      const t1 = graphForceTick(h1, 3, 15);
      const t2 = graphForceTick(h2, 3, 15);
      assert.deepEqual([...t1.x], [...t2.x], `${name} tick`);
      assert.deepEqual([...t1.y], [...t2.y], `${name} tick`);
    } finally {
      graphForceDestroy(h1);
      graphForceDestroy(h2);
    }
  }
});

test("layout name aliases match Python map ids", async () => {
  const { GRAPH_LAYOUT_IDS, graphLayoutId } = await import("../src/index.js");
  assert.equal(graphLayoutId("fr"), GRAPH_LAYOUT_IDS.force);
  assert.equal(graphLayoutId("fa2"), GRAPH_LAYOUT_IDS.forceatlas2);
  assert.equal(graphLayoutId("kk"), GRAPH_LAYOUT_IDS.kamada_kawai);
  assert.equal(graphLayoutId("spring"), GRAPH_LAYOUT_IDS.spring);
  assert.equal(graphLayoutId("stress"), GRAPH_LAYOUT_IDS.stress);
  assert.equal(graphLayoutId("yifanhu"), GRAPH_LAYOUT_IDS.yifanhu);
  assert.equal(graphLayoutId("linlog"), GRAPH_LAYOUT_IDS.linlog);
  assert.equal(graphLayoutId("cose"), GRAPH_LAYOUT_IDS.cose);
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

test("10M / 100M / 1B-class LOD decisions stay screen-bounded", () => {
  const nodeBudget = 50_000;
  const edgeBudget = 100_000;
  for (const n of [10_000_000, 100_000_000, 1_000_000_000]) {
    const d = graphLodDecision(n, n * 2, { nodeBudget, edgeBudget });
    assert.ok(d.tier >= 1, `class n=${n} should leave Direct`);
    assert.ok(Number(d.edgesKept) <= edgeBudget);
  }
});

const AIRPORTS_NODES = {
  node_uuid: [
    "00000000-0000-0000-0000-000000000001",
    "00000000-0000-0000-0000-000000000002",
    "00000000-0000-0000-0000-000000000003",
  ],
  labels: ["Airport", "Airport", "City"],
  rank: [1, 2, 3],
  provenance_row: [10n, 11n, 12n],
};
const AIRPORTS_EDGES = {
  edge_uuid: [
    "10000000-0000-0000-0000-000000000001",
    "10000000-0000-0000-0000-000000000002",
    "10000000-0000-0000-0000-000000000003",
    "10000000-0000-0000-0000-000000000004",
  ],
  src_uuid: [
    "00000000-0000-0000-0000-000000000001",
    "00000000-0000-0000-0000-000000000001",
    "00000000-0000-0000-0000-000000000002",
    "00000000-0000-0000-0000-000000000003",
  ],
  dst_uuid: [
    "00000000-0000-0000-0000-000000000002",
    "00000000-0000-0000-0000-000000000002",
    "00000000-0000-0000-0000-000000000003",
    "00000000-0000-0000-0000-000000000003",
  ],
  relationship_type: ["ROUTE", "ROUTE", "SERVES", "SELF"],
  weight: [1.5, 2.5, 3.0, 0.1],
  provenance_row: [100n, 101n, 102n, 103n],
};

test("looksLikeGraphForgeTables detects canonical UUID columns", () => {
  assert.equal(looksLikeGraphForgeTables(AIRPORTS_NODES, AIRPORTS_EDGES), true);
  assert.equal(looksLikeGraphForgeTables(["a", "b"], [["a", "b"]]), false);
});


test("graphEdgeRouteSegments separates parallels and keeps source indices", () => {
  const x = new Float64Array([0, 2, 4]);
  const y = new Float64Array([0, 0, 0]);
  const sources = BigUint64Array.from([0n, 0n, 2n]);
  const targets = BigUint64Array.from([1n, 1n, 2n]);
  const routed = graphEdgeRouteSegments(x, y, sources, targets, {
    directed: true,
    separation: 0.2,
    loopRadius: 0.5,
    arrowSize: 0.15,
  });
  assert.equal(routed.x0.length, 9);
  assert.notEqual(routed.y0[0], routed.y0[3]);
  const loopCount = [...routed.edgeIndex].filter((v) => Number(v) === 2).length;
  assert.equal(loopCount, 3);
});

test("composeGraph GraphForge tables preserve edge identity and node tooltips", () => {
  const composed = composeGraph(AIRPORTS_NODES, AIRPORTS_EDGES, { layout: "grid", seed: 1 });
  assert.equal(composed.traces[0].kind, "segments");
  assert.equal(composed.traces[1].kind, "scatter");
  assert.equal(composed.traces[1].tooltip_rows.length, 3);
  assert.equal(composed.traces[1].tooltip_rows[0].labels, "Airport");
  assert.deepEqual(composed.graphMeta.source_edge_ids, AIRPORTS_EDGES.edge_uuid);
  assert.equal(new Set(composed.graphMeta.source_edge_ids).size, 4);
  assert.equal(composed.graphMeta.sources.length, 4);
  assert.deepEqual(composed.graphMeta.edge_ids, AIRPORTS_EDGES.edge_uuid);
  assert.deepEqual(composed.graphMeta.node_provenance_rows, [10, 11, 12]);
  assert.ok(Array.isArray(composed.graphMeta.render_edge_index));
  assert.equal(composed.traces[0].tooltip_rows.length, composed.graphMeta.render_edge_index.length);
  assert.equal(
    new Set(composed.traces[0].tooltip_rows.map((r) => r.edge_id)).size,
    4,
  );
  assert.ok(composed.traces[0].tooltip_rows.some((r) => r.relationship_type === "SELF"));
});

test("figure.graph GraphForge tables ship continuous size from column name", () => {
  const fig = figure({ width: 400, height: 300 });
  fig.graph(AIRPORTS_NODES, AIRPORTS_EDGES, { layout: "circle", seed: 2, size: "rank" });
  const { spec } = fig.buildPayload();
  assert.equal(spec.traces[1].size.mode, "continuous");
  assert.ok(Array.isArray(spec.traces[1].tooltip_rows));
});

test("fromGraphForgeTables rejects duplicate edge uuid before paint", () => {
  assert.throws(
    () =>
      fromGraphForgeTables(AIRPORTS_NODES, {
        edge_uuid: [
          "10000000-0000-0000-0000-000000000001",
          "10000000-0000-0000-0000-000000000001",
        ],
        src_uuid: [
          "00000000-0000-0000-0000-000000000001",
          "00000000-0000-0000-0000-000000000002",
        ],
        dst_uuid: [
          "00000000-0000-0000-0000-000000000002",
          "00000000-0000-0000-0000-000000000003",
        ],
      }),
    /GF_GRAPH_EDGE_DUPLICATE/,
  );
});

test("fromGraphForgeTables rejects missing endpoint before paint", () => {
  assert.throws(
    () =>
      fromGraphForgeTables(AIRPORTS_NODES, {
        edge_uuid: ["10000000-0000-0000-0000-000000000099"],
        src_uuid: ["00000000-0000-0000-0000-000000000001"],
        dst_uuid: ["00000000-0000-0000-0000-000000000099"],
      }),
    /GF_GRAPH_ENDPOINT_MISSING/,
  );
});

test("resolveGraphData accepts GraphData passthrough", () => {
  const data = fromGraphForgeTables(AIRPORTS_NODES, AIRPORTS_EDGES);
  const again = resolveGraphData(data);
  assert.equal(again.ids.length, 3);
  assert.equal(again.sources.length, 4);
});

test("looksLikeGraphForgeTables honors mapping overrides", () => {
  const nodes = {
    id: [
      "00000000-0000-0000-0000-000000000001",
      "00000000-0000-0000-0000-000000000002",
    ],
  };
  const edges = {
    eid: ["10000000-0000-0000-0000-000000000001"],
    src: ["00000000-0000-0000-0000-000000000001"],
    dst: ["00000000-0000-0000-0000-000000000002"],
  };
  const mapping = {
    node_uuid: "id",
    edge_uuid: "eid",
    source_uuid: "src",
    target_uuid: "dst",
  };
  assert.equal(looksLikeGraphForgeTables(nodes, edges, mapping), true);
  const data = resolveGraphData(nodes, edges, { mapping });
  assert.equal(data.ids.length, 2);
  assert.equal(data.sources.length, 1);
});

test("composeGraph accepts GraphData with size option object", () => {
  const data = fromGraphForgeTables(AIRPORTS_NODES, AIRPORTS_EDGES);
  const composed = composeGraph(data, { layout: "grid", seed: 1, size: "rank" });
  assert.equal(composed.traces[1].kind, "scatter");
  assert.ok(composed.traces[1].sizeValues);
});

test("resolveGraphData rejects mismatched preset y length", () => {
  assert.throws(
    () =>
      resolveGraphData(AIRPORTS_NODES, AIRPORTS_EDGES, {
        x: [0, 1, 2],
        y: [0, 1],
      }),
    /x\/y must match node count/,
  );
});

test("projectionTooltipRows preserves bigint attributes as strings", () => {
  const data = fromGraphForgeTables(
    {
      node_uuid: [
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
      ],
      big: [9007199254740993n, 1n],
    },
    {
      edge_uuid: ["10000000-0000-0000-0000-000000000001"],
      src_uuid: ["00000000-0000-0000-0000-000000000001"],
      dst_uuid: ["00000000-0000-0000-0000-000000000002"],
    },
  );
  const [nodeRows] = projectionTooltipRows(data);
  assert.equal(nodeRows[0].big, "9007199254740993");
});
