#!/usr/bin/env node
/**
 * Regenerate GraphForge-produced Arrow result fixtures for the XYG
 * composition contract (xyg#37, spec/design/graphforge-compositions.md).
 *
 * Adapted from CurateLabs/graphforge-vscode `scripts/generate-result-fixtures.cjs`
 * (issue #80, Apache-2.0): the same algorithm calls on the same synthetic
 * graphs, plus one base-graph dump per synthetic graph so every result's
 * UUIDs join against engine-produced nodes and relationships
 * (`base-<graph>-nodes.arrow` = `MATCH (n) RETURN n`,
 * `base-<graph>-edges.arrow` = `MATCH ()-[r]->() RETURN r`). GraphForge mints
 * fresh UUIDs per run, so results and bases must come from one run.
 *
 * Usage: node scripts/gen_graphforge_result_fixtures.cjs [path/to/node_modules/@curatelabs/graphforge]
 */
const fs = require("node:fs");
const path = require("node:path");

const modulePath = process.argv[2] ?? "@curatelabs/graphforge";
const { GraphForge } = require(modulePath);
const packageJson = require(path.join(path.dirname(require.resolve(modulePath)), "package.json"));

const outDir = path.join(__dirname, "..", "tests", "fixtures", "graphforge", "results");
fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(outDir, { recursive: true });

/** Weighted cyclic graph: 4 people, a triangle plus a tail, with flow/cost/prize props. */
function cyclicGraph() {
  const g = new GraphForge();
  const people = ["ada", "bo", "cy", "di"].map((name, i) =>
    g.addNode("Person", { name, prize: i + 1.5, vec: [i + 0.5, 3.5 - i], feature: i * 0.75 + 0.25 }),
  );
  const [a, b, c, d] = people;
  // Non-integral floats keep each property a single Float64 column.
  const link = (s, t, w) => g.addEdge(s, "KNOWS", t, { w, capacity: w * 3, cost: w + 0.1 });
  link(a, b, 1.5);
  link(b, c, 2.5);
  link(c, a, 1.25);
  link(c, d, 3.5);
  link(a, d, 4.25);
  g.index("Person", { kind: "text", properties: ["name"] });
  return { g, nodes: people };
}

/** DAG for topological/longest-path algorithms. */
function dagGraph() {
  const g = new GraphForge();
  const [a, b, c, d] = ["t1", "t2", "t3", "t4"].map((name) => g.addNode("Task", { name }));
  g.addEdge(a, "BEFORE", b, { w: 1.5 });
  g.addEdge(b, "BEFORE", c, { w: 2.5 });
  g.addEdge(a, "BEFORE", c, { w: 5.5 });
  g.addEdge(c, "BEFORE", d, { w: 1.25 });
  return { g, nodes: [a, b, c, d] };
}


const manifest = {
  graphforgeVersion: packageJson.version,
  contracts: new GraphForge().algorithmDescriptorContracts().map(({ verb, algorithm, resultSchemaVersion }) => ({
    verb,
    algorithm,
    resultSchemaVersion,
  })),
  fixtures: {},
  bases: {},
  failures: {},
};

function write(name, kind, produce) {
  try {
    const buf = produce();
    fs.writeFileSync(path.join(outDir, `${name}.arrow`), buf);
    manifest.fixtures[name] = kind;
  } catch (err) {
    manifest.failures[name] = String(err?.message ?? err).slice(0, 200);
  }
}

const DAG_ONLY = new Set(["topological_sort", "dag_longest_path", "dag_longest_path_weighted", "is_dag"]);
const UNDIRECTED = new Set([
  "minimum_spanning_tree", "maximum_spanning_tree", "minimum_k_spanning_tree", "node_coloring",
  "edge_coloring", "chromatic_number", "max_weight_matching", "max_cardinality_matching",
  "max_bipartite_matching", "articulation_points", "bridges", "triangle_count", "modularity",
  "conductance", "transitivity", "is_planar", "count_automorphisms", "k1_coloring",
  "euler_circuit", "euler_path", "has_euler_circuit", "has_euler_path", "max_bipartite_matching",
]);

/** Directed flow network (s → x/y → t) with capacity and cost. */
function flowGraph() {
  const g = new GraphForge();
  const [s, x, y, t] = ["s", "x", "y", "t"].map((name) => g.addNode("Hub", { name }));
  const pipe = (a, b, capacity, cost) => g.addEdge(a, "PIPE", b, { capacity, cost });
  // Balanced capacities: GraphForge 0.5.2 min-cost max-flow exceeds its
  // iteration limit when a downstream edge is the bottleneck.
  pipe(s, x, 3, 1);
  pipe(s, y, 2, 2);
  pipe(x, t, 3, 1);
  pipe(y, t, 2, 1);
  return { g, nodes: [s, x, y, t] };
}

/** Undirected 4-cycle: bipartite and Eulerian. */
function ringGraph() {
  const g = new GraphForge();
  const nodes = ["r1", "r2", "r3", "r4"].map((name) => g.addNode("Stop", { name }));
  nodes.forEach((node, i) => g.addEdge(node, "NEXT", nodes[(i + 1) % nodes.length], {}));
  return { g, nodes };
}

/** Ten vector-bearing points for k-means (which needs at least ten). */
function pointGraph() {
  const g = new GraphForge();
  const nodes = Array.from({ length: 10 }, (_, i) =>
    g.addNode("Point", { name: `p${i}`, vec: [i < 5 ? 0.25 + i * 0.1 : 5.25 + i * 0.1, 1.5] }),
  );
  return { g, nodes };
}

const cyclic = cyclicGraph();
const dag = dagGraph();
const flow = flowGraph();
const ring = ringGraph();
const points = pointGraph();
const FLOW = new Set(["max_flow", "max_flow_edges", "min_cut", "min_cut_edges", "min_cost_max_flow", "min_cost_max_flow_edges"]);
const RING = new Set(["max_bipartite_matching", "euler_circuit"]);

function graphFor(algorithm) {
  if (DAG_ONLY.has(algorithm)) return { ...dag, label: "Task", base: "dag" };
  if (FLOW.has(algorithm)) return { ...flow, label: "Hub", base: "flow" };
  if (RING.has(algorithm)) return { ...ring, label: "Stop", base: "ring" };
  if (algorithm === "k_means") return { ...points, label: "Point", base: "points" };
  return { ...cyclic, label: "Person", base: "cyclic" };
}

// One engine-produced base graph per synthetic graph. Generation UUIDs are
// fixed test identities: an in-memory GraphForge has no committed generation,
// and the composition contract only compares them.
const BASES = { cyclic, dag, flow, ring, points };
const GENERATIONS = {
  cyclic: "0190a000-0000-7000-8000-000000000001",
  dag: "0190a000-0000-7000-8000-000000000002",
  flow: "0190a000-0000-7000-8000-000000000003",
  ring: "0190a000-0000-7000-8000-000000000004",
  points: "0190a000-0000-7000-8000-000000000005",
};
for (const [name, graph] of Object.entries(BASES)) {
  const nodes = `base-${name}-nodes`;
  const edges = `base-${name}-edges`;
  write(nodes, { verb: "execute", base: name }, () => graph.g.execute("MATCH (n) RETURN n"));
  write(edges, { verb: "execute", base: name }, () => graph.g.execute("MATCH ()-[r]->() RETURN r"));
  manifest.bases[name] = { nodes, edges, generation: GENERATIONS[name] };
}

for (const { verb, algorithm } of manifest.contracts) {
  const { g, nodes, label, base } = graphFor(algorithm);
  const [a, , c, d] = nodes;
  const kind = { verb, algorithm, base };
  write(algorithm, kind, () => {
    switch (verb) {
      case "rank":
        return g.rank(label, algorithm);
      case "cluster":
        return g.cluster(
          label,
          algorithm,
          null,
          UNDIRECTED.has(algorithm) ? false : null,
          null,
          ["hdbscan", "k_means"].includes(algorithm) ? "vec" : null,
        );
      case "similar":
        return g.similar(label, algorithm, 2, ["knn", "filtered_knn", "cosine"].includes(algorithm) ? "vec" : null);
      case "paths": {
        const pairless = ["gomory_hu_tree", "transitive_closure", "min_steiner_tree", "prize_collecting_steiner_tree"];
        const directed = ["gomory_hu_tree", "min_steiner_tree", "prize_collecting_steiner_tree"].includes(algorithm)
          ? false
          : FLOW.has(algorithm) || null;
        const source = algorithm === "transitive_closure" ? a : pairless.includes(algorithm) ? null : a;
        const target =
          pairless.includes(algorithm) || ["dfs", "random_walk", "dijkstra_all_pairs", "floyd_warshall"].includes(algorithm)
            ? null
            : d;
        return g.paths(
          source,
          target,
          algorithm,
          null,
          directed,
          algorithm === "yens" ? 2 : null,
          ["dijkstra", "astar", "bellman_ford", "delta_stepping", "yens", "min_steiner_tree", "prize_collecting_steiner_tree"].includes(algorithm)
            ? "w"
            : FLOW.has(algorithm) && !algorithm.startsWith("min_cost")
              ? "capacity"
              : null,
          null,
          algorithm === "random_walk" ? 4 : null,
          algorithm === "random_walk" ? 7n : null,
          algorithm.includes("steiner") ? [a.uuid, c.uuid, d.uuid] : null,
          algorithm === "prize_collecting_steiner_tree" ? "prize" : null,
          algorithm.startsWith("min_cost") ? "capacity" : null,
          algorithm.startsWith("min_cost") ? "cost" : null,
        );
      }
      case "analyze":
        return g.analyze(
          algorithm,
          label,
          null,
          UNDIRECTED.has(algorithm) ? false : null,
          ["dag_longest_path_weighted", "minimum_spanning_tree", "maximum_spanning_tree", "minimum_k_spanning_tree", "max_weight_matching"].includes(algorithm) ? "w" : null,
          ["modularity", "conductance"].includes(algorithm) ? "name" : null,
          algorithm === "minimum_k_spanning_tree" ? 2 : null,
          ["node2vec", "graphsage", "fast_random_projection", "hashgnn"].includes(algorithm)
            ? { dimensions: 4, ...(algorithm === "graphsage" ? { feature_properties: ["feature"] } : {}) }
            : null,
        );
      default:
        throw new Error(`unknown verb ${verb}`);
    }
  });
}

const q = cyclic.g;
write("cypher-nodes", { verb: "execute", base: "cyclic" }, () => q.execute("MATCH (n:Person) RETURN n ORDER BY n.name"));
write("cypher-edges", { verb: "execute", base: "cyclic" }, () =>
  q.execute("MATCH (a:Person)-[r:KNOWS]->(b:Person) RETURN a, r, b ORDER BY a.name, b.name"),
);
write("cypher-paths", { verb: "execute", base: "cyclic" }, () =>
  q.execute("MATCH p=(a:Person)-[:KNOWS]->(b:Person)-[:KNOWS]->(c:Person) RETURN p LIMIT 3"),
);
write("cypher-scalars", { verb: "execute", base: "cyclic" }, () =>
  q.execute("MATCH (n:Person) RETURN n.name AS name, n.prize AS prize ORDER BY name"),
);
write("find", { verb: "find", base: "cyclic" }, () => q.find("ada", "Person"));
write("schema", { verb: "schema", base: "cyclic" }, () => q.schema());

fs.writeFileSync(path.join(outDir, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
const written = Object.keys(manifest.fixtures).length;
const failed = Object.keys(manifest.failures);
console.log(`graphforge ${manifest.graphforgeVersion}: wrote ${written} fixtures; ${failed.length} failed${failed.length ? `: ${failed.join(", ")}` : ""}`);
