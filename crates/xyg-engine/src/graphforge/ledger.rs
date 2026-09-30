//! GraphForge result-schema coverage ledger (spec/design/graphforge-compositions.md §3).
//!
//! Source: CurateLabs/graphforge `crates/graphforge-core/src/algorithms.rs`
//! (`result_schema` / `path_schema` / `analyze_schema`) at algorithm schema
//! v1, cross-checked against the extension's ledger
//! (CurateLabs/graphforge-vscode `docs/engineering/RESULT_SCHEMAS.md`).
//! Schema ids, canonical fields, and dispositions match that ledger exactly;
//! the `composition` column is XYG's canonical rendering of the disposition.

/// Algorithm result schema version this ledger understands.
pub const ALGORITHM_SCHEMA_VERSION: u32 = 1;
/// `find` search result schema version this ledger understands.
pub const SEARCH_SCHEMA_VERSION: u32 = 1;
/// Version of this ledger's contents (bumps when an entry changes).
pub const LEDGER_VERSION: u32 = 1;

/// The extension's disposition vocabulary.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Disposition {
    EntityGraph,
    NodeLayer,
    EdgeLayer,
    DerivedEdges,
    OrderedPaths,
    TableOnly,
    CompositionRequired,
}

impl Disposition {
    pub fn name(self) -> &'static str {
        match self {
            Disposition::EntityGraph => "entity-graph",
            Disposition::NodeLayer => "node-layer",
            Disposition::EdgeLayer => "edge-layer",
            Disposition::DerivedEdges => "derived-edges",
            Disposition::OrderedPaths => "ordered-paths",
            Disposition::TableOnly => "table-only",
            Disposition::CompositionRequired => "composition-required",
        }
    }
}

/// Arrow type families a canonical field may carry.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    /// `FixedSizeBinary(16)`.
    Uuid,
    /// `List`/`LargeList` of `FixedSizeBinary(16)`.
    UuidList,
    /// Any floating-point width.
    Float,
    /// Any integer width and signedness.
    Int,
    Bool,
    /// `Utf8` or `LargeUtf8`.
    Utf8,
    /// `List`/`LargeList`/`FixedSizeList` of floating point.
    FloatVector,
}

impl Kind {
    pub fn name(self) -> &'static str {
        match self {
            Kind::Uuid => "uuid",
            Kind::UuidList => "uuid-list",
            Kind::Float => "float",
            Kind::Int => "int",
            Kind::Bool => "bool",
            Kind::Utf8 => "utf8",
            Kind::FloatVector => "float-vector",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Role {
    Node,
    Edge,
    Source,
    Target,
    NodePath,
    EdgePath,
    Metric,
    Order,
    Rank,
    Cost,
    Group,
    Vector,
    Category,
}

#[derive(Clone, Copy, Debug)]
pub struct FieldSpec {
    pub name: &'static str,
    pub kind: Kind,
    pub role: Role,
}

const fn f(name: &'static str, kind: Kind, role: Role) -> FieldSpec {
    FieldSpec { name, kind, role }
}

/// How XYG composes a schema. Each variant names the planes it writes
/// (spec §4); `DerivedPairs::directed` decides the derived arrowhead.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Composition {
    /// Node metric plane (size), keyed by `node_uuid`.
    NodeScore,
    /// Node class plane (fill/shape) from a group id.
    NodeGroup,
    /// Node labels from `order`.
    NodeOrder,
    /// Node metric from `depth`, labels from `order`.
    NodeTraversal,
    /// Node status plane for set membership.
    NodeSet,
    /// Node metric from search `score`, status for hits.
    NodeSearch,
    /// Persisted edges keyed by `edge_uuid` (+ endpoints), optional metric/group.
    EdgeOverlay { directional: bool },
    /// Persisted edges keyed by `edge_uuid` only, grouped.
    EdgeGroup,
    /// Derived node pairs drawn as distinct derived edges.
    DerivedPairs { directed: bool },
    /// Ordered node paths (derived steps).
    Paths,
    /// Ordered random walks (derived steps).
    Walks,
    /// Closed cycles (derived steps including the closing step).
    Cycles,
    /// Ordered trail over persisted edges (`edge_path`).
    EulerTrail,
    /// One scalar row: a table composition.
    Scalar,
    /// Category/value rows: a table or bar-chart composition.
    Category,
    /// Node vectors: explicit coordinates or a dimensional view.
    Embedding,
}

impl Composition {
    pub fn name(self) -> &'static str {
        match self {
            Composition::NodeScore => "node-score",
            Composition::NodeGroup => "node-group",
            Composition::NodeOrder => "node-order",
            Composition::NodeTraversal => "node-traversal",
            Composition::NodeSet => "node-set",
            Composition::NodeSearch => "node-search",
            Composition::EdgeOverlay { .. } => "edge-overlay",
            Composition::EdgeGroup => "edge-group",
            Composition::DerivedPairs { .. } => "derived-edges",
            Composition::Paths => "paths",
            Composition::Walks => "walks",
            Composition::Cycles => "cycles",
            Composition::EulerTrail => "euler-trail",
            Composition::Scalar => "table",
            Composition::Category => "category",
            Composition::Embedding => "embedding",
        }
    }

    /// Visualization intents a caller may request for this composition.
    pub fn intents(self) -> &'static [Intent] {
        match self {
            Composition::Scalar => &[Intent::Table],
            Composition::Category => &[Intent::Table, Intent::BarChart],
            Composition::Embedding => &[Intent::EmbeddingCoordinates, Intent::ParallelCoordinates],
            _ => &[Intent::Graph],
        }
    }

    /// Whether a result is expected to cover every base node/edge of its kind
    /// (`missing` defaults to `dim`) or is a subset (`missing` defaults to `keep`).
    pub fn covers_base(self) -> bool {
        matches!(
            self,
            Composition::NodeScore
                | Composition::NodeGroup
                | Composition::NodeOrder
                | Composition::NodeTraversal
        )
    }
}

/// Explicit visualization intent. XYG never picks one on the caller's behalf.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Intent {
    Graph,
    Table,
    BarChart,
    EmbeddingCoordinates,
    ParallelCoordinates,
}

impl Intent {
    pub fn name(self) -> &'static str {
        match self {
            Intent::Graph => "graph",
            Intent::Table => "table",
            Intent::BarChart => "bar-chart",
            Intent::EmbeddingCoordinates => "embedding-coordinates",
            Intent::ParallelCoordinates => "parallel-coordinates",
        }
    }

    pub fn parse(name: &str) -> Option<Self> {
        [
            Intent::Graph,
            Intent::Table,
            Intent::BarChart,
            Intent::EmbeddingCoordinates,
            Intent::ParallelCoordinates,
        ]
        .into_iter()
        .find(|intent| intent.name() == name)
    }
}

#[derive(Clone, Copy, Debug)]
pub struct SchemaEntry {
    pub id: &'static str,
    pub version: u32,
    pub disposition: Disposition,
    pub composition: Composition,
    pub fields: &'static [FieldSpec],
    pub algorithms: &'static [&'static str],
    /// Relationship type shown for derived edges / path steps.
    pub derived_type: Option<&'static str>,
    pub note: &'static str,
}

use Kind::*;
use Role::*;

const EDGE_ENDPOINTS: [FieldSpec; 3] = [
    f("edge_uuid", Uuid, Edge),
    f("source_uuid", Uuid, Source),
    f("target_uuid", Uuid, Target),
];

macro_rules! edge_fields {
    ($($extra:expr),* $(,)?) => {
        &[EDGE_ENDPOINTS[0], EDGE_ENDPOINTS[1], EDGE_ENDPOINTS[2], $($extra),*]
    };
}

const fn scalar(
    id: &'static str,
    algorithms: &'static [&'static str],
    fields: &'static [FieldSpec],
) -> SchemaEntry {
    SchemaEntry {
        id,
        version: 1,
        disposition: Disposition::TableOnly,
        composition: Composition::Scalar,
        fields,
        algorithms,
        derived_type: None,
        note: "Global structural result; shown as a table rather than forced into a graph.",
    }
}

const fn category(
    id: &'static str,
    algorithms: &'static [&'static str],
    fields: &'static [FieldSpec],
    note: &'static str,
) -> SchemaEntry {
    SchemaEntry {
        id,
        version: 1,
        disposition: Disposition::TableOnly,
        composition: Composition::Category,
        fields,
        algorithms,
        derived_type: None,
        note,
    }
}

/// Every stable GraphForge algorithm result schema, keyed by shape.
pub const ALGORITHM_SCHEMAS: &[SchemaEntry] = &[
    SchemaEntry {
        id: "node-score",
        version: 1,
        disposition: Disposition::NodeLayer,
        composition: Composition::NodeScore,
        fields: &[f("node_uuid", Uuid, Node), f("score", Float, Metric)],
        algorithms: &[
            "pagerank", "betweenness", "closeness", "harmonic_closeness", "degree",
            "eigenvector", "article_rank", "hits_hub", "hits_authority", "celf",
            "clustering_coefficient", "local_clustering_coefficient", "triangles",
            "k_core", "preferential_attachment", "adamic_adar", "common_neighbors",
            "resource_allocation", "total_neighbors",
        ],
        derived_type: None,
        note: "Node scores keyed by node_uuid.",
    },
    SchemaEntry {
        id: "node-community",
        version: 1,
        disposition: Disposition::NodeLayer,
        composition: Composition::NodeGroup,
        fields: &[f("node_uuid", Uuid, Node), f("community_id", Int, Group)],
        algorithms: &[
            "louvain", "leiden", "label_propagation", "speaker_listener",
            "girvan_newman", "modularity_optimization", "fastgreedy", "infomap",
            "leading_eigenvector", "walktrap", "spinglass", "hdbscan", "k_means",
            "approximate_max_k_cut", "components", "strongly_connected",
            "biconnected", "k_core_decomposition",
        ],
        derived_type: None,
        note: "Community membership keyed by node_uuid.",
    },
    SchemaEntry {
        id: "similarity",
        version: 1,
        disposition: Disposition::DerivedEdges,
        composition: Composition::DerivedPairs { directed: false },
        fields: &[
            f("node1_uuid", Uuid, Source),
            f("node2_uuid", Uuid, Target),
            f("similarity", Float, Metric),
        ],
        algorithms: &["node_similarity", "knn", "filtered_knn", "filtered_node_similarity", "cosine"],
        derived_type: Some("SIMILAR"),
        note: "Similarity pairs are derived edges, not persisted relationships.",
    },
    SchemaEntry {
        id: "path",
        version: 1,
        disposition: Disposition::OrderedPaths,
        composition: Composition::Paths,
        fields: &[
            f("source_uuid", Uuid, Source),
            f("target_uuid", Uuid, Target),
            f("cost", Float, Cost),
            f("path", UuidList, NodePath),
        ],
        algorithms: &[
            "bfs", "dijkstra", "dijkstra_all_pairs", "astar", "bellman_ford",
            "floyd_warshall", "delta_stepping",
        ],
        derived_type: Some("PATH_STEP"),
        note: "Ordered node paths with cost.",
    },
    SchemaEntry {
        id: "ranked-path",
        version: 1,
        disposition: Disposition::OrderedPaths,
        composition: Composition::Paths,
        fields: &[
            f("source_uuid", Uuid, Source),
            f("target_uuid", Uuid, Target),
            f("rank", Int, Rank),
            f("cost", Float, Cost),
            f("path", UuidList, NodePath),
        ],
        algorithms: &["yens"],
        derived_type: Some("PATH_STEP"),
        note: "k ranked node paths with cost.",
    },
    SchemaEntry {
        id: "traversal",
        version: 1,
        disposition: Disposition::NodeLayer,
        composition: Composition::NodeTraversal,
        fields: &[
            f("node_uuid", Uuid, Node),
            f("depth", Int, Metric),
            f("order", Int, Order),
        ],
        algorithms: &["dfs"],
        derived_type: None,
        note: "Visit order and depth keyed by node_uuid.",
    },
    SchemaEntry {
        id: "walk",
        version: 1,
        disposition: Disposition::OrderedPaths,
        composition: Composition::Walks,
        fields: &[f("start_uuid", Uuid, Source), f("walk", UuidList, NodePath)],
        algorithms: &["random_walk"],
        derived_type: Some("WALK_STEP"),
        note: "Ordered random walks.",
    },
    SchemaEntry {
        id: "pair",
        version: 1,
        disposition: Disposition::DerivedEdges,
        composition: Composition::DerivedPairs { directed: true },
        fields: &[f("source_uuid", Uuid, Source), f("target_uuid", Uuid, Target)],
        algorithms: &["transitive_closure"],
        derived_type: Some("REACHES"),
        note: "Reachability pairs are derived edges.",
    },
    SchemaEntry {
        id: "flow",
        version: 1,
        disposition: Disposition::DerivedEdges,
        composition: Composition::DerivedPairs { directed: true },
        fields: &[
            f("source_uuid", Uuid, Source),
            f("sink_uuid", Uuid, Target),
            f("flow", Float, Metric),
        ],
        algorithms: &["max_flow"],
        derived_type: Some("MAX_FLOW"),
        note: "Source/sink flow value as a derived pair.",
    },
    SchemaEntry {
        id: "costed-flow",
        version: 1,
        disposition: Disposition::DerivedEdges,
        composition: Composition::DerivedPairs { directed: true },
        fields: &[
            f("source_uuid", Uuid, Source),
            f("sink_uuid", Uuid, Target),
            f("flow", Float, Metric),
            f("cost", Float, Cost),
        ],
        algorithms: &["min_cost_max_flow"],
        derived_type: Some("MIN_COST_FLOW"),
        note: "Source/sink flow and cost as a derived pair.",
    },
    SchemaEntry {
        id: "min-cut",
        version: 1,
        disposition: Disposition::DerivedEdges,
        composition: Composition::DerivedPairs { directed: true },
        fields: &[
            f("source_uuid", Uuid, Source),
            f("sink_uuid", Uuid, Target),
            f("cut_value", Float, Metric),
        ],
        algorithms: &["min_cut"],
        derived_type: Some("MIN_CUT"),
        note: "Source/sink cut value as a derived pair.",
    },
    SchemaEntry {
        id: "cut-tree",
        version: 1,
        disposition: Disposition::DerivedEdges,
        composition: Composition::DerivedPairs { directed: false },
        fields: &[
            f("source_uuid", Uuid, Source),
            f("target_uuid", Uuid, Target),
            f("cut_value", Float, Metric),
        ],
        algorithms: &["gomory_hu_tree"],
        derived_type: Some("CUT_TREE"),
        note: "Gomory-Hu tree edges are derived (no persisted edge_uuid).",
    },
    SchemaEntry {
        id: "flow-edges",
        version: 1,
        disposition: Disposition::EdgeLayer,
        composition: Composition::EdgeOverlay { directional: true },
        fields: edge_fields![f("flow", Float, Metric)],
        algorithms: &["max_flow_edges"],
        derived_type: None,
        note: "Per-edge flow keyed by edge_uuid.",
    },
    SchemaEntry {
        id: "costed-flow-edges",
        version: 1,
        disposition: Disposition::EdgeLayer,
        composition: Composition::EdgeOverlay { directional: true },
        fields: edge_fields![
            f("flow", Float, Metric),
            f("unit_cost", Float, Cost),
            f("flow_cost", Float, Cost),
        ],
        algorithms: &["min_cost_max_flow_edges"],
        derived_type: None,
        note: "Per-edge flow and cost keyed by edge_uuid.",
    },
    SchemaEntry {
        id: "min-cut-edges",
        version: 1,
        disposition: Disposition::EdgeLayer,
        composition: Composition::EdgeOverlay { directional: true },
        fields: edge_fields![f("capacity", Float, Metric)],
        algorithms: &["min_cut_edges"],
        derived_type: None,
        note: "Cut edges keyed by edge_uuid.",
    },
    SchemaEntry {
        id: "steiner-edge-list",
        version: 1,
        disposition: Disposition::EdgeLayer,
        composition: Composition::EdgeOverlay { directional: false },
        fields: edge_fields![f("weight", Float, Metric)],
        algorithms: &["min_steiner_tree", "prize_collecting_steiner_tree"],
        derived_type: None,
        note: "Steiner tree edges keyed by edge_uuid.",
    },
    SchemaEntry {
        id: "edge-list",
        version: 1,
        disposition: Disposition::EdgeLayer,
        composition: Composition::EdgeOverlay { directional: false },
        fields: edge_fields![f("weight", Float, Metric)],
        algorithms: &["minimum_spanning_tree", "maximum_spanning_tree", "max_weight_matching"],
        derived_type: None,
        note: "Tree/matching edges keyed by edge_uuid.",
    },
    SchemaEntry {
        id: "unweighted-edge-list",
        version: 1,
        disposition: Disposition::EdgeLayer,
        composition: Composition::EdgeOverlay { directional: false },
        fields: edge_fields![],
        algorithms: &["max_cardinality_matching", "max_bipartite_matching", "bridges"],
        derived_type: None,
        note: "Matching/bridge edges keyed by edge_uuid.",
    },
    SchemaEntry {
        id: "k-edge-list",
        version: 1,
        disposition: Disposition::EdgeLayer,
        composition: Composition::EdgeOverlay { directional: false },
        fields: &[
            f("tree_id", Int, Group),
            EDGE_ENDPOINTS[0],
            EDGE_ENDPOINTS[1],
            EDGE_ENDPOINTS[2],
            f("weight", Float, Metric),
        ],
        algorithms: &["minimum_k_spanning_tree"],
        derived_type: None,
        note: "Grouped spanning-tree edges keyed by edge_uuid.",
    },
    SchemaEntry {
        id: "node-order",
        version: 1,
        disposition: Disposition::NodeLayer,
        composition: Composition::NodeOrder,
        fields: &[f("node_uuid", Uuid, Node), f("order", Int, Order)],
        algorithms: &["topological_sort"],
        derived_type: None,
        note: "Topological order keyed by node_uuid.",
    },
    SchemaEntry {
        id: "node",
        version: 1,
        disposition: Disposition::NodeLayer,
        composition: Composition::NodeSet,
        fields: &[f("node_uuid", Uuid, Node)],
        algorithms: &["articulation_points"],
        derived_type: None,
        note: "Node set keyed by node_uuid.",
    },
    SchemaEntry {
        id: "node-color",
        version: 1,
        disposition: Disposition::NodeLayer,
        composition: Composition::NodeGroup,
        fields: &[f("node_uuid", Uuid, Node), f("color", Int, Group)],
        algorithms: &["node_coloring", "k1_coloring"],
        derived_type: None,
        note: "Node coloring keyed by node_uuid.",
    },
    SchemaEntry {
        id: "edge-color",
        version: 1,
        disposition: Disposition::CompositionRequired,
        composition: Composition::EdgeGroup,
        fields: &[f("edge_uuid", Uuid, Edge), f("color", Int, Group)],
        algorithms: &["edge_coloring"],
        derived_type: None,
        note: "Edge colors carry no endpoints; compose them onto a base graph result to draw them.",
    },
    SchemaEntry {
        id: "euler-trail",
        version: 1,
        disposition: Disposition::OrderedPaths,
        composition: Composition::EulerTrail,
        fields: &[f("node_path", UuidList, NodePath), f("edge_path", UuidList, EdgePath)],
        algorithms: &["euler_circuit", "euler_path"],
        derived_type: None,
        note: "Ordered Euler trail over persisted edges.",
    },
    SchemaEntry {
        id: "cycle",
        version: 1,
        disposition: Disposition::OrderedPaths,
        composition: Composition::Cycles,
        fields: &[f("cycle", UuidList, NodePath)],
        algorithms: &["find_cycles"],
        derived_type: Some("CYCLE_STEP"),
        note: "One ordered cycle per row.",
    },
    SchemaEntry {
        id: "cost-path",
        version: 1,
        disposition: Disposition::OrderedPaths,
        composition: Composition::Paths,
        fields: &[f("cost", Float, Cost), f("path", UuidList, NodePath)],
        algorithms: &["dag_longest_path", "dag_longest_path_weighted"],
        derived_type: Some("PATH_STEP"),
        note: "Ordered longest path with cost.",
    },
    scalar("is-dag", &["is_dag"], &[f("is_dag", Bool, Metric)]),
    scalar("has-euler-circuit", &["has_euler_circuit"], &[f("has_euler_circuit", Bool, Metric)]),
    scalar("has-euler-path", &["has_euler_path"], &[f("has_euler_path", Bool, Metric)]),
    scalar("is-planar", &["is_planar"], &[f("is_planar", Bool, Metric)]),
    scalar("chromatic-number", &["chromatic_number"], &[f("chromatic_number", Int, Metric)]),
    scalar("triangle-count", &["triangle_count"], &[f("triangle_count", Int, Metric)]),
    scalar("automorphism-count", &["count_automorphisms"], &[f("count", Int, Metric)]),
    scalar("modularity", &["modularity"], &[f("modularity", Float, Metric)]),
    scalar("transitivity", &["transitivity"], &[f("transitivity", Float, Metric)]),
    category(
        "conductance",
        &["conductance"],
        &[f("partition_id", Utf8, Category), f("conductance", Float, Metric)],
        "Per-partition conductance; partition ids are property values, not node identities.",
    ),
    category(
        "triad-census",
        &["triad_census"],
        &[f("triad_type", Utf8, Category), f("count", Int, Metric)],
        "Category counts; shown as a table.",
    ),
    category(
        "dyad-census",
        &["dyad_census"],
        &[f("dyad_type", Utf8, Category), f("count", Int, Metric)],
        "Category counts; shown as a table.",
    ),
    SchemaEntry {
        id: "embedding",
        version: 1,
        disposition: Disposition::CompositionRequired,
        composition: Composition::Embedding,
        fields: &[f("node_uuid", Uuid, Node), f("embedding", FloatVector, Vector)],
        algorithms: &["node2vec", "graphsage", "fast_random_projection", "hashgnn"],
        derived_type: None,
        note: "Embeddings need caller-provided 2D coordinates or an explicit dimensional view; dimensions are never plotted as x/y.",
    },
];

/// `find` search results: node_uuid + node properties + score + matched_on.
pub const SEARCH_SCHEMA: SchemaEntry = SchemaEntry {
    id: "search",
    version: 1,
    disposition: Disposition::NodeLayer,
    composition: Composition::NodeSearch,
    fields: &[
        f("node_uuid", Uuid, Node),
        f("score", Float, Metric),
        f("matched_on", Utf8, Category),
    ],
    algorithms: &[],
    derived_type: None,
    note: "Search hits keyed by node_uuid.",
};

/// Verbs whose results carry `graphforge.algorithm`.
pub const ALGORITHM_VERBS: &[&str] = &["rank", "cluster", "similar", "paths", "analyze"];

/// Ledger entry for an algorithm name.
pub fn schema_for_algorithm(algorithm: &str) -> Option<&'static SchemaEntry> {
    ALGORITHM_SCHEMAS
        .iter()
        .find(|entry| entry.algorithms.contains(&algorithm))
}

/// Tab-separated ledger rows (header first) for docs and cross-repo checks:
/// schema id, version, disposition, composition, intents, `name:kind` fields,
/// algorithms.
pub fn ledger_tsv() -> String {
    let mut out =
        String::from("schema\tversion\tdisposition\tcomposition\tintents\tfields\talgorithms\n");
    for entry in ALGORITHM_SCHEMAS
        .iter()
        .chain(std::iter::once(&SEARCH_SCHEMA))
    {
        let intents: Vec<_> = entry
            .composition
            .intents()
            .iter()
            .map(|i| i.name())
            .collect();
        let fields: Vec<_> = entry
            .fields
            .iter()
            .map(|s| format!("{}:{}", s.name, s.kind.name()))
            .collect();
        out.push_str(&format!(
            "{}\t{}\t{}\t{}\t{}\t{}\t{}\n",
            entry.id,
            entry.version,
            entry.disposition.name(),
            entry.composition.name(),
            intents.join(","),
            fields.join(","),
            entry.algorithms.join(","),
        ));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashSet;

    #[test]
    fn algorithms_map_to_exactly_one_schema() {
        let mut seen = HashSet::new();
        for entry in ALGORITHM_SCHEMAS {
            assert_eq!(entry.version, ALGORITHM_SCHEMA_VERSION);
            for algorithm in entry.algorithms {
                assert!(seen.insert(*algorithm), "{algorithm} is registered twice");
            }
        }
        let ids: HashSet<_> = ALGORITHM_SCHEMAS.iter().map(|e| e.id).collect();
        assert_eq!(ids.len(), ALGORITHM_SCHEMAS.len(), "schema ids are unique");
    }

    #[test]
    fn every_graphforge_contract_has_a_disposition() {
        let manifest = std::fs::read_to_string(format!(
            "{}/../../tests/fixtures/graphforge/results/manifest.json",
            env!("CARGO_MANIFEST_DIR")
        ))
        .unwrap();
        // Minimal scan: every `"algorithm": "<name>"` in the contracts list.
        let contracts = &manifest[..manifest.find("\"fixtures\"").unwrap()];
        let mut count = 0;
        for part in contracts.split("\"algorithm\": \"").skip(1) {
            let name = &part[..part.find('"').unwrap()];
            assert!(
                schema_for_algorithm(name).is_some(),
                "{name} has no ledger entry"
            );
            count += 1;
        }
        assert_eq!(count, 94, "GraphForge 0.5.2 registers 94 algorithms");
    }

    fn read_repo(path: &str) -> String {
        std::fs::read_to_string(format!("{}/../../{path}", env!("CARGO_MANIFEST_DIR"))).unwrap()
    }

    fn cells(line: &str) -> Vec<String> {
        line.trim()
            .trim_matches('|')
            .split('|')
            .map(|c| c.trim().to_owned())
            .collect()
    }

    fn backticked(text: &str) -> Vec<String> {
        text.split('`')
            .skip(1)
            .step_by(2)
            .map(str::to_owned)
            .collect()
    }

    #[test]
    fn spec_ledger_table_matches_the_code() {
        let spec = read_repo("spec/design/graphforge-compositions.md");
        let start = spec.find("<!-- graphforge-ledger:begin -->").unwrap();
        let end = spec.find("<!-- graphforge-ledger:end -->").unwrap();
        let rows: Vec<Vec<String>> = spec[start..end]
            .lines()
            .filter(|l| l.starts_with("| `"))
            .map(cells)
            .collect();
        let entries: Vec<&SchemaEntry> = ALGORITHM_SCHEMAS
            .iter()
            .chain(std::iter::once(&SEARCH_SCHEMA))
            .collect();
        assert_eq!(rows.len(), entries.len(), "one spec row per schema");
        for (row, entry) in rows.iter().zip(entries) {
            let intents: Vec<_> = entry
                .composition
                .intents()
                .iter()
                .map(|i| i.name())
                .collect();
            let algorithms = if entry.algorithms.is_empty() {
                "(find)".to_owned()
            } else {
                entry.algorithms.join(", ")
            };
            assert_eq!(
                row,
                &vec![
                    format!("`{}`", entry.id),
                    entry.disposition.name().to_owned(),
                    entry.composition.name().to_owned(),
                    intents.join(", "),
                    algorithms,
                ],
                "spec row for {}",
                entry.id
            );
        }
    }

    #[test]
    fn extension_ledger_agrees_on_ids_dispositions_and_membership() {
        let doc = read_repo("tests/fixtures/graphforge/extension/RESULT_SCHEMAS.md");
        let table = &doc
            [doc.find("## Coverage ledger").unwrap()..doc.find("Non-algorithm results").unwrap()];
        let mut checked = 0;
        for line in table
            .lines()
            .filter(|l| l.starts_with("| ") && !l.starts_with("| Schema"))
        {
            let row = cells(line);
            let ids = backticked(&row[0]);
            let disposition = row[1].split_whitespace().next().unwrap();
            for algorithm in row[3].split(',') {
                let name = algorithm.split_whitespace().next().unwrap();
                let entry = schema_for_algorithm(name).unwrap_or_else(|| {
                    panic!("extension algorithm {name} is not in the XYG ledger")
                });
                assert_eq!(entry.disposition.name(), disposition, "{name}");
                if !ids.is_empty() {
                    assert!(
                        ids.contains(&entry.id.to_owned()),
                        "{name}: {} not in {ids:?}",
                        entry.id
                    );
                }
                checked += 1;
            }
            // Aliases the extension lists in parentheses are registered too.
            if let Some(alias) = row[3].split("alias ").nth(1) {
                let alias = &alias[..alias.find(')').unwrap()];
                assert!(schema_for_algorithm(alias).is_some(), "alias {alias}");
            }
        }
        assert!(
            checked >= 94,
            "checked {checked} extension ledger algorithms"
        );
        let search = doc.lines().find(|l| l.starts_with("| `search`")).unwrap();
        assert_eq!(cells(search)[1], SEARCH_SCHEMA.disposition.name());
    }

    #[test]
    fn ledger_tsv_lists_every_schema() {
        let tsv = ledger_tsv();
        assert_eq!(tsv.lines().count(), 1 + ALGORITHM_SCHEMAS.len() + 1);
        assert!(tsv.contains("embedding\t1\tcomposition-required\tembedding\tembedding-coordinates,parallel-coordinates"));
    }
}
