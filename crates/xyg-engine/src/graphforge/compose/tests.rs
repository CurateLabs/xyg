//! Composition tests over the real GraphForge 0.5.2 fixture corpus
//! (`tests/fixtures/graphforge/results`, produced by one engine run).

use super::*;
use crate::graphforge::container::{Container, REQUEST_MAGIC};
use crate::graphforge::parse_uuid_text;
use crate::graphforge::Uuid;

fn fixture(name: &str) -> Vec<u8> {
    std::fs::read(format!(
        "{}/../../tests/fixtures/graphforge/results/{name}.arrow",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap_or_else(|e| panic!("{name}: {e}"))
}

/// `(base graph, generation)` for a fixture, from the manifest.
fn base_of(name: &str) -> (&'static str, Uuid) {
    let manifest = std::fs::read_to_string(format!(
        "{}/../../tests/fixtures/graphforge/results/manifest.json",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap();
    let fixtures = &manifest[manifest.find("\"fixtures\"").unwrap()..];
    let entry = &fixtures[fixtures.find(&format!("\"{name}\": {{")).unwrap()..];
    let base = entry.split("\"base\": \"").nth(1).unwrap();
    let base = &base[..base.find('"').unwrap()];
    let base: &'static str = match base {
        "cyclic" => "cyclic",
        "dag" => "dag",
        "flow" => "flow",
        "ring" => "ring",
        "points" => "points",
        other => panic!("unknown base {other}"),
    };
    let generation = match base {
        "cyclic" => "0190a000-0000-7000-8000-000000000001",
        "dag" => "0190a000-0000-7000-8000-000000000002",
        "flow" => "0190a000-0000-7000-8000-000000000003",
        "ring" => "0190a000-0000-7000-8000-000000000004",
        _ => "0190a000-0000-7000-8000-000000000005",
    };
    (base, parse_uuid_text(generation).unwrap())
}

#[derive(Default, Clone)]
struct LayerSpec {
    result: Vec<u8>,
    intent: &'static str,
    generation: Option<Uuid>,
    missing: Option<&'static str>,
    extra: Option<&'static str>,
    result_id: Option<&'static str>,
    rows: Option<Vec<u64>>,
    coordinates: Option<Vec<u8>>,
}

fn layer(name: &str) -> LayerSpec {
    LayerSpec {
        result: fixture(name),
        intent: "graph",
        generation: Some(base_of(name).1),
        ..Default::default()
    }
}

fn request(bases: &[&str], generation: Option<Uuid>, layers: &[LayerSpec]) -> Vec<u8> {
    let mut builder = Builder::new(REQUEST_MAGIC);
    let mut tables = Vec::new();
    for base in bases {
        tables.push(fixture(&format!("base-{base}-nodes")));
        tables.push(fixture(&format!("base-{base}-edges")));
    }
    for (i, table) in tables.iter().enumerate() {
        builder.bytes("base.table", i, table);
    }
    if let Some(generation) = generation {
        builder.uuids("base.generation", 0, &[generation]);
    }
    for (i, spec) in layers.iter().enumerate() {
        builder.bytes("layer.result", i, &spec.result);
        builder.utf8("layer.intent", i, spec.intent);
        if let Some(g) = spec.generation {
            builder.uuids("layer.generation", i, &[g]);
        }
        if let Some(m) = spec.missing {
            builder.utf8("layer.missing", i, m);
        }
        if let Some(x) = spec.extra {
            builder.utf8("layer.extra", i, x);
        }
        if let Some(id) = spec.result_id {
            builder.utf8("layer.result_id", i, id);
        }
        if let Some(rows) = &spec.rows {
            builder.u64s("layer.rows", i, rows);
        }
        if let Some(coordinates) = &spec.coordinates {
            builder.bytes("layer.coordinates", i, coordinates);
        }
    }
    builder.finish()
}

fn compose_one(name: &str) -> Vec<u8> {
    let (base, generation) = base_of(name);
    compose_bytes(&request(&[base], Some(generation), &[layer(name)]))
        .unwrap_or_else(|doc| panic!("{name}: {}", error_code(&doc)))
}

fn error_code(document: &[u8]) -> String {
    let c = Container::decode(document, DOCUMENT_MAGIC).unwrap();
    let code = c.get("error.code", 0).unwrap().as_utf8("x").unwrap();
    let message = c.get("error.message", 0).unwrap().as_utf8("x").unwrap();
    format!("{code}: {message}")
}

fn fail(bytes: Vec<u8>) -> (String, u32) {
    let document = compose_bytes(&bytes).expect_err("composition should fail");
    let c = Container::decode(&document, DOCUMENT_MAGIC).unwrap();
    assert_eq!(c.get("status", 0).unwrap().payload, &1u32.to_le_bytes());
    let layer = u32::from_le_bytes(c.get("error.layer", 0).unwrap().payload.try_into().unwrap());
    (
        c.get("error.code", 0)
            .unwrap()
            .as_utf8("x")
            .unwrap()
            .to_owned(),
        layer,
    )
}

struct Doc<'a>(Container<'a>);

impl<'a> Doc<'a> {
    fn new(bytes: &'a [u8]) -> Self {
        Doc(Container::decode(bytes, DOCUMENT_MAGIC).unwrap())
    }
    fn u8s(&self, name: &str) -> &'a [u8] {
        self.0.get(name, 0).unwrap().as_u8(name).unwrap()
    }
    fn f64s(&self, name: &str, index: u32) -> Vec<f64> {
        self.0.get(name, index).unwrap().as_f64(name).unwrap()
    }
    fn u64s(&self, name: &str, index: u32) -> Vec<u64> {
        self.0.get(name, index).unwrap().as_u64(name).unwrap()
    }
    fn u32s(&self, name: &str) -> Vec<u32> {
        self.0
            .get(name, 0)
            .unwrap()
            .payload
            .chunks_exact(4)
            .map(|c| u32::from_le_bytes(c.try_into().unwrap()))
            .collect()
    }
    fn texts(&self, name: &str, index: u32) -> Vec<&'a str> {
        self.0.get(name, index).unwrap().as_texts(name).unwrap()
    }
    fn uuids(&self, name: &str) -> Vec<Uuid> {
        self.0.get(name, 0).unwrap().as_uuids(name).unwrap()
    }
    fn decisions(&self) -> Vec<(String, u64)> {
        self.texts("decision.code", 0)
            .into_iter()
            .zip(self.u64s("decision.count", 0))
            .map(|(c, n)| (c.to_owned(), n))
            .collect()
    }
}

fn result_values(name: &str, id_field: &str, value_field: &str) -> Vec<(Uuid, f64)> {
    let bytes = fixture(name);
    let table = read_table(&bytes).unwrap();
    let ids = uuids(&table.column(id_field).unwrap(), false).unwrap();
    let values = f64s(&table.column(value_field).unwrap()).unwrap();
    ids.into_iter()
        .zip(values)
        .map(|(i, v)| (i.unwrap(), v.unwrap()))
        .collect()
}

#[test]
fn pagerank_joins_scores_by_uuid_not_row_position() {
    let document = compose_one("pagerank");
    let doc = Doc::new(&document);
    let ids = doc.uuids("node.uuid");
    let metric = doc.f64s("node.metric", 0);
    let values = doc.f64s("layer.node_values", 0);
    for (id, score) in result_values("pagerank", "node_uuid", "score") {
        let node = ids
            .iter()
            .position(|i| *i == id)
            .expect("every result node is in the base");
        assert_eq!(metric[node], score);
        assert_eq!(values[node * 2], score);
    }
    // Canonical score first, then the node properties rank results carry.
    assert_eq!(doc.texts("layer.value_names", 0), vec!["score", "prize"]);
    assert_eq!(doc.texts("layer.text_names", 0), vec!["name"]);
    let names = doc.texts("layer.node_texts", 0);
    assert_eq!(
        names,
        doc.texts("node.name", 0),
        "properties join by UUID like values"
    );
    assert!(
        doc.u32s("node.flags").iter().all(|&f| f == 0),
        "full coverage dims nothing"
    );
    assert_eq!(doc.u64s("layer.counts", 0), vec![4, 4, 4, 0, 0]);
    // Labels fall back to the base node name.
    assert!(doc.texts("node.label", 0).iter().all(|l| !l.is_empty()));
    assert!(doc.decisions().is_empty(), "{:?}", doc.decisions());
}

#[test]
fn every_graph_intent_fixture_composes_onto_its_base() {
    let manifest = std::fs::read_to_string(format!(
        "{}/../../tests/fixtures/graphforge/results/manifest.json",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap();
    let contracts = &manifest[..manifest.find("\"fixtures\"").unwrap()];
    let mut composed = 0;
    for part in contracts.split("\"algorithm\": \"").skip(1) {
        let name = &part[..part.find('"').unwrap()];
        let entry = ledger::schema_for_algorithm(name).unwrap();
        if entry.composition.intents().contains(&Intent::Graph) {
            let document = compose_one(name);
            let doc = Doc::new(&document);
            assert_eq!(doc.0.get("kind", 0).unwrap().as_utf8("k").unwrap(), "graph");
            let counts = doc.u64s("layer.counts", 0);
            assert_eq!(counts[4], 0, "{name}: no extra identities");
            composed += 1;
        }
    }
    let find = compose_one("find");
    assert!(Doc::new(&find)
        .u8s("node.status")
        .contains(&NODE_STATUS_MEMBER));
    assert_eq!(composed, 78, "graph-intent schemas in GraphForge 0.5.2");
}

fn derived_edges(doc: &Doc<'_>) -> Vec<usize> {
    doc.u8s("edge.derived")
        .iter()
        .enumerate()
        .filter(|(_, &d)| d == 1)
        .map(|(i, _)| i)
        .collect()
}

#[test]
fn similarity_pairs_are_visibly_derived_edges() {
    let document = compose_one("node_similarity");
    let doc = Doc::new(&document);
    let derived = derived_edges(&doc);
    let rows = result_values("node_similarity", "node1_uuid", "similarity");
    assert_eq!(derived.len(), rows.len());
    let uuids = doc.uuids("edge.uuid");
    let epistemic = doc.u8s("edge.epistemic");
    let status = doc.u8s("edge.status");
    let metric = doc.f64s("edge.metric", 0);
    let edge_rows = doc.u64s("layer.edge_rows", 0);
    let types = doc.texts("edge.type", 0);
    for &e in &derived {
        assert_eq!(uuids[e], [0; 16], "derived edges carry no persisted UUID");
        assert_eq!(epistemic[e], 1, "halo and dash set them apart");
        assert_eq!(status[e], 0, "similarity is symmetric: no arrowhead");
        assert_eq!(types[e], "SIMILAR");
        assert_eq!(metric[e], rows[edge_rows[e] as usize].1);
    }
    // Persisted relationships are untouched.
    let persisted: Vec<usize> = (0..uuids.len()).filter(|i| !derived.contains(i)).collect();
    assert_eq!(persisted.len(), 5);
    assert!(persisted
        .iter()
        .all(|&e| epistemic[e] == 0 && doc.u32s("edge.layer")[e] == NONE_U32));
    assert!(doc.texts("legend.text", 0).contains(&"similar (derived)"));
}

#[test]
fn reachability_and_flows_are_directed_derived_edges() {
    for (name, epistemic) in [
        ("transitive_closure", 2),
        ("max_flow", 3),
        ("min_cut", 5),
        ("min_cost_max_flow", 3),
    ] {
        let document = compose_one(name);
        let doc = Doc::new(&document);
        let derived = derived_edges(&doc);
        assert!(!derived.is_empty(), "{name}");
        for &e in &derived {
            assert_eq!(doc.u8s("edge.epistemic")[e], epistemic, "{name}");
            assert_eq!(doc.u8s("edge.status")[e], 1, "{name}: directed");
        }
    }
    let document = compose_one("gomory_hu_tree");
    let doc = Doc::new(&document);
    assert!(derived_edges(&doc)
        .iter()
        .all(|&e| doc.u8s("edge.status")[e] == 0));
}

#[test]
fn a_single_path_orders_steps_and_labels_positions() {
    let document = compose_one("dijkstra");
    let doc = Doc::new(&document);
    let offsets = doc.u64s("path.node_offsets", 0);
    assert_eq!(offsets.len(), 2, "one path");
    let path_nodes = doc.u64s("path.nodes", 0);
    let path_edges = doc.u64s("path.edges", 0);
    assert_eq!(path_edges.len() + 1, path_nodes.len());
    let order = doc.0.get("edge.order", 0).unwrap();
    let order: Vec<i64> = order
        .payload
        .chunks_exact(8)
        .map(|c| i64::from_le_bytes(c.try_into().unwrap()))
        .collect();
    let (sources, targets) = (doc.u64s("edge.source", 0), doc.u64s("edge.target", 0));
    for (k, &e) in path_edges.iter().enumerate() {
        assert_eq!(order[e as usize], k as i64);
        assert_eq!(sources[e as usize], path_nodes[k]);
        assert_eq!(targets[e as usize], path_nodes[k + 1]);
        assert_eq!(
            doc.u8s("edge.status")[e as usize],
            1,
            "steps point along the path"
        );
        assert_eq!(doc.u8s("edge.epistemic")[e as usize], 7);
    }
    let labels = doc.texts("node.label", 0);
    for (k, &n) in path_nodes.iter().enumerate() {
        assert_eq!(labels[n as usize], k.to_string());
    }
    let status = doc.u8s("node.status");
    assert_eq!(status[path_nodes[0] as usize], NODE_STATUS_PATH_END);
    assert_eq!(
        status[*path_nodes.last().unwrap() as usize],
        NODE_STATUS_PATH_END
    );
    let bytes = fixture("dijkstra");
    let table = read_table(&bytes).unwrap();
    let cost = f64s(&table.column("cost").unwrap()).unwrap()[0].unwrap();
    assert_eq!(doc.f64s("path.cost", 0), vec![cost]);
    assert!(doc.f64s("path.rank", 0)[0].is_nan());
    assert_eq!(doc.texts("layer.value_names", 0), vec!["cost"]);
}

#[test]
fn many_paths_keep_rank_and_cost_but_skip_labels() {
    let document = compose_one("yens");
    let doc = Doc::new(&document);
    let ranks = doc.f64s("path.rank", 0);
    assert_eq!(ranks.len(), 2, "k = 2 ranked paths");
    assert!(doc
        .decisions()
        .iter()
        .any(|(c, _)| c == "GF_COMPOSE_PATH_LABELS_OMITTED"));
    // A null or empty path list is one empty overlay, counted once.
    let bfs = compose_one("bfs");
    let empties: u64 = Doc::new(&bfs)
        .decisions()
        .iter()
        .filter(|(c, _)| c == "GF_COMPOSE_EMPTY_PATHS")
        .map(|(_, n)| *n)
        .sum();
    assert!(empties <= Doc::new(&bfs).f64s("path.cost", 0).len() as u64);
    let all_pairs = compose_one("dijkstra_all_pairs");
    let doc = Doc::new(&all_pairs);
    assert!(doc.f64s("path.cost", 0).len() > 2);
}

#[test]
fn cycles_close_and_walks_start() {
    let document = compose_one("find_cycles");
    let doc = Doc::new(&document);
    let nodes = doc.u64s("path.nodes", 0);
    let edges = doc.u64s("path.edges", 0);
    assert_eq!(edges.len(), nodes.len(), "the closing step is added");
    assert!(nodes
        .iter()
        .all(|&n| doc.u8s("node.status")[n as usize] == NODE_STATUS_ON_PATH));
    let walk = compose_one("random_walk");
    let doc = Doc::new(&walk);
    let nodes = doc.u64s("path.nodes", 0);
    assert_eq!(
        doc.u8s("node.status")[nodes[0] as usize],
        NODE_STATUS_PATH_END
    );
    assert!(doc.texts("legend.text", 0).contains(&"walk step (derived)"));
}

#[test]
fn euler_trails_order_persisted_edges_without_derived_ones() {
    for name in ["euler_circuit", "euler_path"] {
        let document = compose_one(name);
        let doc = Doc::new(&document);
        assert!(
            derived_edges(&doc).is_empty(),
            "{name}: trails name persisted edges"
        );
        let path_edges = doc.u64s("path.edges", 0);
        let labels = doc.texts("edge.label", 0);
        let (sources, targets) = (doc.u64s("edge.source", 0), doc.u64s("edge.target", 0));
        let path_nodes = doc.u64s("path.nodes", 0);
        for (k, &e) in path_edges.iter().enumerate() {
            assert_eq!(labels[e as usize], k.to_string(), "{name}");
            assert_eq!(doc.u8s("edge.class")[e as usize], 1);
            assert_eq!(doc.u8s("edge.status")[e as usize], 1);
            // Reoriented where the trail runs against the stored direction.
            assert_eq!(
                (sources[e as usize], targets[e as usize]),
                (path_nodes[k], path_nodes[k + 1])
            );
        }
        assert!(doc.texts("legend.text", 0).contains(&"Euler trail edge"));
    }
}

#[test]
fn derived_layers_coexist_with_node_layers_and_conflicts_fail() {
    let (base, generation) = base_of("pagerank");
    let bytes = request(
        &[base],
        Some(generation),
        &[
            layer("pagerank"),
            layer("louvain"),
            layer("node_similarity"),
            layer("dijkstra"),
        ],
    );
    let document = compose_bytes(&bytes).unwrap();
    let doc = Doc::new(&document);
    let edge_layer = doc.u32s("edge.layer");
    assert!(edge_layer.contains(&2) && edge_layer.contains(&3));
    // Layer arrays cover every composed edge, padded where a layer is absent.
    assert_eq!(
        doc.u64s("layer.edge_rows", 2).len(),
        doc.uuids("edge.uuid").len()
    );
    let (code, layer_index) = fail(request(
        &[base],
        Some(generation),
        &[layer("minimum_spanning_tree"), layer("node_similarity")],
    ));
    assert_eq!(
        (code.as_str(), layer_index),
        ("GF_COMPOSE_CHANNEL_CONFLICT", 1)
    );
}

#[test]
fn hidden_nodes_take_derived_edges_and_paths_with_them() {
    let (base, generation) = base_of("pagerank");
    let mut rank = layer("pagerank");
    rank.rows = Some(vec![0]);
    rank.missing = Some("hide");
    let bytes = request(&[base], Some(generation), &[rank, layer("dijkstra")]);
    let document = compose_bytes(&bytes).unwrap();
    let doc = Doc::new(&document);
    assert_eq!(doc.uuids("node.uuid").len(), 1);
    assert!(derived_edges(&doc).is_empty());
    assert!(doc
        .decisions()
        .iter()
        .any(|(c, _)| c == "GF_COMPOSE_PATHS_HIDDEN"));
    assert!(doc.f64s("path.cost", 0).is_empty());
}

#[test]
fn paths_through_absent_nodes_follow_the_extra_policy() {
    let (_, generation) = base_of("dag_longest_path");
    let cyclic_gen = base_of("dijkstra").1;
    let mut foreign = layer("dijkstra");
    foreign.generation = Some(generation);
    assert_eq!(
        fail(request(&["dag"], Some(generation), &[foreign.clone()])).0,
        "GF_COMPOSE_EXTRA_IDS"
    );
    foreign.extra = Some("drop");
    let document = compose_bytes(&request(&["dag"], Some(generation), &[foreign])).unwrap();
    let doc = Doc::new(&document);
    assert!(doc
        .decisions()
        .contains(&("GF_COMPOSE_EXTRA_DROPPED".into(), 1)));
    assert!(derived_edges(&doc).is_empty());
    let _ = cyclic_gen;
}

#[test]
fn communities_map_to_ranked_class_codes_with_legend() {
    let document = compose_one("louvain");
    let doc = Doc::new(&document);
    let classes = doc.u8s("node.class");
    assert!(classes.iter().all(|&c| (1..=7).contains(&c)));
    let texts = doc.texts("legend.text", 0);
    assert!(
        texts.iter().all(|t| t.starts_with("community ")),
        "{texts:?}"
    );
    assert_eq!(doc.u8s("legend.side").len(), texts.len());
    assert_eq!(doc.u8s("legend.rgba_light").len(), 4 * texts.len());
}

#[test]
fn unassigned_groups_are_class_zero_and_recorded() {
    let document = compose_one("hdbscan");
    let doc = Doc::new(&document);
    assert!(doc.u8s("node.class").iter().all(|&c| c == 0));
    assert!(doc
        .decisions()
        .contains(&("GF_COMPOSE_UNASSIGNED_GROUP".into(), 4)));
    assert!(doc.texts("legend.text", 0).contains(&"no community"));
}

#[test]
fn groups_beyond_seven_share_one_bucket() {
    let mut planes_values: Vec<(usize, Option<i64>)> =
        (0..20).map(|i| (i, Some(i as i64 % 10))).collect();
    planes_values.push((20, Some(3)));
    let base = BaseGraph {
        node_uuid: vec![[1; 16]; 21],
        node_name: vec![None; 21],
        node_type: vec![None; 21],
        ..Default::default()
    };
    let mut planes = Planes::new(&base);
    let bytes = fixture("louvain");
    let req = LayerRequest {
        result: &bytes,
        result_id: None,
        generation: None,
        intent: Intent::Graph,
        missing: None,
        extra: None,
        rows: None,
        coordinates: None,
    };
    let layer = prepare_layer(0, &req).unwrap();
    let codes = planes.group_codes(&layer, LEGEND_NODE, "community", &planes_values);
    // Group 3 is largest (3 members); ties by ascending id: 0, 1, 2, 4, 5.
    let code_of = |element: usize| codes.iter().find(|(e, _)| *e == element).unwrap().1;
    assert_eq!(code_of(3), 1);
    assert_eq!(code_of(0), 2);
    assert_eq!(code_of(5), 6);
    assert_eq!(code_of(6), 7);
    assert_eq!(code_of(9), 7);
    assert!(planes.decisions.contains(&Decision {
        code: "GF_COMPOSE_GROUPS_BUCKETED",
        layer: Some(0),
        count: 4
    }));
    assert_eq!(planes.legend[&(LEGEND_NODE, 0, 7)], "other communities (4)");
}

#[test]
fn traversal_labels_order_and_sizes_depth() {
    let document = compose_one("dfs");
    let doc = Doc::new(&document);
    let labels = doc.texts("node.label", 0);
    let mut sorted: Vec<_> = labels.clone();
    sorted.sort();
    assert_eq!(sorted, vec!["0", "1", "2", "3"]);
    let metric = doc.f64s("node.metric", 0);
    assert!(metric.iter().all(|m| m.is_finite()));
    assert_eq!(doc.texts("layer.value_names", 0)[..2], ["depth", "order"]);
}

#[test]
fn spanning_tree_overlay_marks_members_and_dims_context() {
    let document = compose_one("minimum_spanning_tree");
    let doc = Doc::new(&document);
    let class = doc.u8s("edge.class");
    let flags = doc.u32s("edge.flags");
    let members = class.iter().filter(|&&c| c == 1).count();
    assert_eq!(members, 3, "a spanning tree of 4 nodes has 3 edges");
    for (c, f) in class.iter().zip(&flags) {
        assert_eq!(*c == 1, *f & FLAG_DISABLED == 0);
    }
    assert!(
        doc.u8s("edge.status").iter().all(|&s| s == 0),
        "undirected overlays draw no arrows"
    );
    assert!(doc.texts("legend.text", 0).contains(&"spanning tree edge"));
    assert!(doc.texts("legend.text", 0).contains(&"not in result"));
    assert!(doc
        .decisions()
        .contains(&("GF_COMPOSE_MISSING_DIMMED".into(), 2)));
}

#[test]
fn flow_edges_are_directional_with_flow_metric() {
    let document = compose_one("max_flow_edges");
    let doc = Doc::new(&document);
    let status = doc.u8s("edge.status");
    let metric = doc.f64s("edge.metric", 0);
    let ids = doc.uuids("edge.uuid");
    for (id, flow) in result_values("max_flow_edges", "edge_uuid", "flow") {
        let edge = ids.iter().position(|i| *i == id).unwrap();
        assert_eq!(status[edge], 1);
        assert_eq!(metric[edge], flow);
    }
}

#[test]
fn edge_colors_compose_onto_the_base_graph() {
    let document = compose_one("edge_coloring");
    let doc = Doc::new(&document);
    let class = doc.u8s("edge.class");
    assert!(class.iter().all(|&c| c >= 1), "every edge is colored");
    assert!(doc
        .texts("legend.text", 0)
        .iter()
        .any(|t| t.starts_with("edge color ")));
}

#[test]
fn k_spanning_trees_group_by_tree_id() {
    let document = compose_one("minimum_k_spanning_tree");
    let doc = Doc::new(&document);
    assert!(doc
        .texts("legend.text", 0)
        .iter()
        .any(|t| t.starts_with("tree ")));
    assert_eq!(doc.texts("layer.value_names", 0), vec!["tree_id", "weight"]);
    // Two spanning trees of a five-edge graph share at least one edge.
    assert!(doc
        .decisions()
        .iter()
        .any(|(c, n)| c == "GF_COMPOSE_SHARED_MEMBERSHIP" && *n > 0));
}

#[test]
fn several_layers_coexist_without_mutating_the_base() {
    let (base, generation) = base_of("pagerank");
    let bytes = request(
        &[base],
        Some(generation),
        &[
            layer("pagerank"),
            layer("louvain"),
            layer("minimum_spanning_tree"),
            layer("articulation_points"),
        ],
    );
    let document = compose_bytes(&bytes).unwrap();
    let doc = Doc::new(&document);
    assert!(doc.f64s("node.metric", 0).iter().all(|m| m.is_finite()));
    assert!(doc.u8s("node.class").iter().all(|&c| c > 0));
    assert_eq!(doc.u8s("edge.class").iter().filter(|&&c| c == 1).count(), 3);
    for i in 0..4 {
        assert!(doc.0.get("layer.schema", i).is_some());
    }
    // The base graph itself is unchanged: same nodes and edges in base order.
    let alone = compose_one("pagerank");
    let alone = Doc::new(&alone);
    assert_eq!(doc.uuids("node.uuid"), alone.uuids("node.uuid"));
    assert_eq!(doc.uuids("edge.uuid"), alone.uuids("edge.uuid"));
    assert_eq!(doc.u64s("edge.source", 0), alone.u64s("edge.source", 0));
}

#[test]
fn two_writers_of_one_channel_conflict() {
    let (base, generation) = base_of("pagerank");
    let (code, layer_index) = fail(request(
        &[base],
        Some(generation),
        &[layer("pagerank"), layer("betweenness")],
    ));
    assert_eq!(
        (code.as_str(), layer_index),
        ("GF_COMPOSE_CHANNEL_CONFLICT", 1)
    );
}

#[test]
fn stale_and_missing_generations_fail_explicitly() {
    let (base, generation) = base_of("pagerank");
    let mut stale = layer("pagerank");
    stale.generation = Some(parse_uuid_text("0190a000-0000-7000-8000-0000000000ff").unwrap());
    assert_eq!(
        fail(request(&[base], Some(generation), &[stale])).0,
        "GF_COMPOSE_GENERATION_STALE"
    );

    let mut unnamed = layer("pagerank");
    unnamed.generation = None;
    assert_eq!(
        fail(request(&[base], Some(generation), &[unnamed.clone()])).0,
        "GF_COMPOSE_GENERATION_MISSING"
    );
    assert_eq!(
        fail(request(&[base], None, &[layer("pagerank")])).0,
        "GF_COMPOSE_GENERATION_MISSING"
    );

    let document = compose_bytes(&request(&[base], None, &[unnamed])).unwrap();
    assert!(Doc::new(&document)
        .decisions()
        .contains(&("GF_COMPOSE_GENERATION_UNVERIFIED".into(), 1)));
}

#[test]
fn incompatible_base_graphs_fail_on_extra_identities() {
    let (_, generation) = base_of("pagerank");
    let (code, _) = fail(request(&["dag"], Some(generation), &[layer("pagerank")]));
    assert_eq!(code, "GF_COMPOSE_EXTRA_IDS");

    let mut dropped = layer("pagerank");
    dropped.extra = Some("drop");
    let document = compose_bytes(&request(&["dag"], Some(generation), &[dropped])).unwrap();
    let doc = Doc::new(&document);
    assert!(doc
        .decisions()
        .contains(&("GF_COMPOSE_EXTRA_DROPPED".into(), 4)));
    assert!(doc
        .u32s("node.flags")
        .iter()
        .all(|&f| f & FLAG_DISABLED != 0));
}

#[test]
fn missing_identity_policies() {
    let (_, generation) = base_of("pagerank");
    // A base holding two graphs: the result covers only one of them.
    let both = &["cyclic", "flow"];
    let document = compose_bytes(&request(both, Some(generation), &[layer("pagerank")])).unwrap();
    let doc = Doc::new(&document);
    assert_eq!(
        doc.u32s("node.flags")
            .iter()
            .filter(|&&f| f & FLAG_DISABLED != 0)
            .count(),
        4
    );
    assert_eq!(doc.u64s("layer.counts", 0)[3], 4);

    let mut hide = layer("pagerank");
    hide.missing = Some("hide");
    let document = compose_bytes(&request(both, Some(generation), &[hide])).unwrap();
    let doc = Doc::new(&document);
    assert_eq!(doc.uuids("node.uuid").len(), 4);
    assert_eq!(
        doc.uuids("edge.uuid").len(),
        5,
        "flow edges leave with their nodes"
    );
    assert!(doc
        .decisions()
        .contains(&("GF_COMPOSE_EDGES_HIDDEN_WITH_NODES".into(), 4)));
    assert!(doc.u64s("edge.source", 0).iter().all(|&s| s < 4));

    let mut strict = layer("pagerank");
    strict.missing = Some("error");
    assert_eq!(
        fail(request(both, Some(generation), &[strict])).0,
        "GF_COMPOSE_MISSING_IDS"
    );
}

#[test]
fn relationship_endpoints_must_match_the_base() {
    let nodes = fixture("base-flow-nodes");
    let edges = fixture("base-flow-edges");
    let tables = [read_table(&nodes).unwrap(), read_table(&edges).unwrap()];
    let graph = base::build(&tables, None, true).unwrap();
    let mut targets: Vec<Uuid> = graph
        .edge_target
        .iter()
        .map(|&t| graph.node_uuid[t])
        .collect();
    let sources: Vec<Uuid> = graph
        .edge_source
        .iter()
        .map(|&s| graph.node_uuid[s])
        .collect();
    targets.rotate_left(1);
    let mut builder = Builder::new(REQUEST_MAGIC);
    builder.uuids("base.node_uuid", 0, &graph.node_uuid);
    builder.uuids("base.edge_uuid", 0, &graph.edge_uuid);
    builder.uuids("base.edge_source_uuid", 0, &sources);
    builder.uuids("base.edge_target_uuid", 0, &targets);
    builder.bytes("layer.result", 0, &fixture("max_flow_edges"));
    builder.utf8("layer.intent", 0, "graph");
    assert_eq!(
        fail(builder.finish()).0,
        "GF_COMPOSE_EDGE_ENDPOINT_MISMATCH"
    );
}

#[test]
fn node_results_naming_relationships_are_rejected() {
    let ids = result_values("pagerank", "node_uuid", "score");
    let mut builder = Builder::new(REQUEST_MAGIC);
    builder.uuids("base.node_uuid", 0, &[[7; 16], [8; 16]]);
    builder.uuids("base.edge_uuid", 0, &[ids[0].0]);
    builder.uuids("base.edge_source_uuid", 0, &[[7; 16]]);
    builder.uuids("base.edge_target_uuid", 0, &[[8; 16]]);
    builder.bytes("layer.result", 0, &fixture("pagerank"));
    builder.utf8("layer.intent", 0, "graph");
    assert_eq!(fail(builder.finish()).0, "GF_COMPOSE_IDENTITY_KIND");
}

#[test]
fn intents_are_explicit_and_checked_against_the_ledger() {
    let (base, generation) = base_of("pagerank");
    let mut table = layer("pagerank");
    table.intent = "table";
    assert_eq!(
        fail(request(&[base], Some(generation), &[table])).0,
        "GF_COMPOSE_INTENT_UNSUPPORTED"
    );
    let mut unknown = layer("pagerank");
    unknown.intent = "auto";
    assert_eq!(
        fail(request(&[base], Some(generation), &[unknown])).0,
        "GF_COMPOSE_INTENT_INVALID"
    );
    let mut scalar = layer("is_dag");
    scalar.intent = "graph";
    assert_eq!(
        fail(request(&["dag"], Some(base_of("is_dag").1), &[scalar])).0,
        "GF_COMPOSE_INTENT_UNSUPPORTED"
    );

    let mut builder = Builder::new(REQUEST_MAGIC);
    builder.bytes("layer.result", 0, &fixture("pagerank"));
    assert_eq!(fail(builder.finish()).0, "GF_COMPOSE_INTENT_REQUIRED");
}

#[test]
fn graph_intents_need_a_base_graph() {
    let mut builder = Builder::new(REQUEST_MAGIC);
    builder.bytes("layer.result", 0, &fixture("pagerank"));
    builder.utf8("layer.intent", 0, "graph");
    assert_eq!(fail(builder.finish()).0, "GF_COMPOSE_BASE_REQUIRED");
}

#[test]
fn malformed_requests_and_results_fail_with_codes() {
    assert_eq!(fail(b"nope".to_vec()).0, "GF_COMPOSE_REQUEST_INVALID");
    let mut builder = Builder::new(REQUEST_MAGIC);
    builder.bytes("layer.surprise", 0, b"x");
    assert_eq!(fail(builder.finish()).0, "GF_COMPOSE_REQUEST_INVALID");

    let (base, generation) = base_of("pagerank");
    let mut truncated = layer("pagerank");
    truncated.result.truncate(truncated.result.len() / 2);
    let (code, layer_index) = fail(request(&[base], Some(generation), &[truncated]));
    assert_eq!((code.as_str(), layer_index), ("GF_ARROW_MALFORMED", 0));

    let mut cypher = layer("cypher-nodes");
    cypher.intent = "graph";
    assert_eq!(
        fail(request(&[base], Some(generation), &[cypher])).0,
        "GF_RESULT_NOT_ALGORITHM"
    );
}

#[test]
fn selected_rows_restrict_a_layer() {
    let (base, generation) = base_of("pagerank");
    let mut some = layer("pagerank");
    some.rows = Some(vec![2, 0]);
    let document = compose_bytes(&request(&[base], Some(generation), &[some])).unwrap();
    let doc = Doc::new(&document);
    assert_eq!(doc.u64s("layer.counts", 0), vec![4, 2, 2, 2, 0]);
    let mut bad = layer("pagerank");
    bad.rows = Some(vec![0, 0]);
    assert_eq!(
        fail(request(&[base], Some(generation), &[bad])).0,
        "GF_COMPOSE_REQUEST_INVALID"
    );
}

#[test]
fn composition_is_deterministic_and_echoes_provenance() {
    let (base, generation) = base_of("pagerank");
    let mut spec = layer("pagerank");
    spec.result_id = Some("01961e0c-7a1b-7c3d-8e4f-a1b2c3d4e5f6");
    let bytes = request(&[base], Some(generation), &[spec, layer("louvain")]);
    let first = compose_bytes(&bytes).unwrap();
    assert_eq!(first, compose_bytes(&bytes).unwrap());
    let doc = Doc::new(&first);
    assert_eq!(
        doc.0
            .get("layer.result_id", 0)
            .unwrap()
            .as_utf8("x")
            .unwrap(),
        "01961e0c-7a1b-7c3d-8e4f-a1b2c3d4e5f6"
    );
    assert_eq!(
        doc.0
            .get("layer.algorithm", 1)
            .unwrap()
            .as_utf8("x")
            .unwrap(),
        "louvain"
    );
    assert_eq!(doc.u64s("node.base_row", 0), vec![0, 1, 2, 3]);
}

#[test]
fn diagnostics_never_carry_values_or_identities() {
    // Every error message across the negative corpus is free of UUID text
    // and of any fixture value.
    let (base, generation) = base_of("pagerank");
    let mut stale = layer("pagerank");
    stale.generation = Some([0xab; 16]);
    for bytes in [
        request(&["dag"], Some(generation), &[layer("pagerank")]),
        request(&[base], Some(generation), &[stale]),
        request(
            &[base],
            Some(generation),
            &[layer("pagerank"), layer("betweenness")],
        ),
    ] {
        let document = compose_bytes(&bytes).unwrap_err();
        let c = Container::decode(&document, DOCUMENT_MAGIC).unwrap();
        let message = c.get("error.message", 0).unwrap().as_utf8("x").unwrap();
        assert!(
            !message.contains("0190a000") && !message.contains("abab"),
            "{message}"
        );
        assert!(
            !message.chars().any(|c| c == '.' && message.contains("0.")),
            "{message}"
        );
    }
}

// -- tables, bar charts, embeddings (views) ----------------------------------------

fn derived(name: &str) -> Vec<u8> {
    std::fs::read(format!(
        "{}/../../tests/fixtures/graphforge/derived/{name}.arrow",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap()
}

fn view(name: &str, intent: &'static str, with_base: bool) -> LayerSpec {
    let mut spec = layer(name);
    spec.intent = intent;
    if !with_base {
        spec.generation = None;
    }
    spec
}

fn compose_view(spec: LayerSpec, with_base: bool) -> Result<Vec<u8>, Vec<u8>> {
    let (base, generation) = base_of("node2vec");
    if with_base {
        compose_bytes(&request(&[base], Some(generation), &[spec]))
    } else {
        compose_bytes(&request(&[], None, &[spec]))
    }
}

#[test]
fn scalar_and_category_results_compose_as_tables_not_graphs() {
    for name in [
        "is_dag",
        "has_euler_circuit",
        "has_euler_path",
        "is_planar",
        "chromatic_number",
        "triangle_count",
        "count_automorphisms",
        "modularity",
        "transitivity",
        "conductance",
        "triad_census",
        "dyad_census",
    ] {
        let spec = view(name, "table", false);
        let document =
            compose_view(spec, false).unwrap_or_else(|d| panic!("{name}: {}", error_code(&d)));
        let doc = Doc::new(&document);
        assert_eq!(doc.0.get("kind", 0).unwrap().as_utf8("k").unwrap(), "table");
        let entry = ledger::schema_for_algorithm(name).unwrap();
        let columns = doc.texts("table.columns", 0);
        assert_eq!(
            columns,
            entry.fields.iter().map(|f| f.name).collect::<Vec<_>>()
        );
        let rows = doc.u64s("table.rows", 0).len();
        assert_eq!(doc.texts("table.cells", 0).len(), rows * columns.len());
        assert!(
            doc.0.get("node.uuid", 0).is_none(),
            "{name}: never forced into a graph"
        );
    }
    let document = compose_view(view("chromatic_number", "table", false), false).unwrap();
    let doc = Doc::new(&document);
    let bytes = fixture("chromatic_number");
    let table = read_table(&bytes).unwrap();
    let want = i64s(&table.column("chromatic_number").unwrap()).unwrap()[0].unwrap();
    assert_eq!(doc.texts("table.cells", 0), vec![want.to_string()]);
    assert_eq!(doc.f64s("table.values", 0), vec![want as f64]);
    let document = compose_view(view("is_dag", "table", false), false).unwrap();
    assert!(["true", "false"].contains(&Doc::new(&document).texts("table.cells", 0)[0]));
}

#[test]
fn category_results_compose_as_bar_charts_in_result_order() {
    for name in ["conductance", "triad_census", "dyad_census"] {
        let document = compose_view(view(name, "bar-chart", false), false).unwrap();
        let doc = Doc::new(&document);
        assert_eq!(
            doc.0.get("kind", 0).unwrap().as_utf8("k").unwrap(),
            "bar-chart"
        );
        let bytes = fixture(name);
        let table = read_table(&bytes).unwrap();
        let entry = ledger::schema_for_algorithm(name).unwrap();
        let value = entry
            .fields
            .iter()
            .find(|f| f.role == Role::Metric)
            .unwrap()
            .name;
        let want: Vec<f64> = f64s(&table.column(value).unwrap())
            .unwrap()
            .into_iter()
            .map(|v| v.unwrap())
            .collect();
        assert_eq!(doc.f64s("chart.value", 0), want, "{name}");
        assert_eq!(doc.texts("chart.category", 0).len(), want.len());
        assert_eq!(
            doc.0
                .get("chart.value_name", 0)
                .unwrap()
                .as_utf8("x")
                .unwrap(),
            value
        );
    }
    let (code, _) = fail(request(&[], None, &[view("is_dag", "bar-chart", false)]));
    assert_eq!(code, "GF_COMPOSE_INTENT_UNSUPPORTED");
}

#[test]
fn non_graph_intents_take_exactly_one_layer() {
    let (code, _) = fail(request(
        &[],
        None,
        &[
            view("is_dag", "table", false),
            view("modularity", "table", false),
        ],
    ));
    assert_eq!(code, "GF_COMPOSE_INTENT_CONFLICT");
}

#[test]
fn embeddings_offer_an_honest_dimensional_view() {
    for name in ["node2vec", "graphsage", "fast_random_projection", "hashgnn"] {
        let document = compose_view(view(name, "parallel-coordinates", true), true)
            .unwrap_or_else(|d| panic!("{name}: {}", error_code(&d)));
        let doc = Doc::new(&document);
        assert_eq!(
            doc.0.get("kind", 0).unwrap().as_utf8("k").unwrap(),
            "parallel-coordinates"
        );
        let dims = doc.u32s("vector.dimensions")[0] as usize;
        assert_eq!(dims, 4);
        let ids = doc.uuids("vector.uuid");
        assert_eq!(doc.f64s("vector.values", 0).len(), ids.len() * dims);
        assert!(
            doc.texts("vector.name", 0).iter().all(|n| !n.is_empty()),
            "names from the base graph"
        );
    }
    let document = compose_view(view("node2vec", "parallel-coordinates", false), false).unwrap();
    let doc = Doc::new(&document);
    assert!(doc.texts("vector.name", 0).iter().all(|n| n.is_empty()));
    assert!(doc
        .u64s("vector.base_row", 0)
        .iter()
        .all(|&r| r == NONE_U64));
    // The vectors are the result's own values, in result order.
    let bytes = fixture("node2vec");
    let table = read_table(&bytes).unwrap();
    let vectors = crate::graphforge::columns::vectors(&table.column("embedding").unwrap()).unwrap();
    assert_eq!(doc.f64s("vector.values", 0), vectors.values);
    let domain = doc.f64s("vector.domain", 0);
    assert!(
        domain[0] < 0.0 && domain[1] > 3.0,
        "x spans dimensions 0..3"
    );
    let finite = vectors.values.iter().copied().filter(|v| v.is_finite());
    let (lo, hi) = finite.fold((f64::INFINITY, f64::NEG_INFINITY), |(a, b), v| {
        (a.min(v), b.max(v))
    });
    assert!(
        domain[2] < lo && domain[3] > hi,
        "every value is inside the y domain"
    );
}

#[test]
fn embeddings_never_plot_their_first_two_dimensions_by_default() {
    let (code, _) = fail(request(
        &[],
        None,
        &[view("node2vec", "embedding-coordinates", false)],
    ));
    assert_eq!(code, "GF_COMPOSE_COORDINATES_REQUIRED");
    // Caller coordinates place every embedded node.
    let mut spec = view("node2vec", "embedding-coordinates", true);
    spec.coordinates = Some(derived("node2vec-coordinates"));
    let document = compose_view(spec, true).unwrap();
    let doc = Doc::new(&document);
    assert_eq!(
        doc.0.get("kind", 0).unwrap().as_utf8("k").unwrap(),
        "scatter"
    );
    assert_eq!(
        doc.0.get("point.source", 0).unwrap().as_utf8("x").unwrap(),
        "caller"
    );
    let xs = doc.f64s("point.x", 0);
    let ys = doc.f64s("point.y", 0);
    let rows = doc.u64s("point.result_row", 0);
    for k in 0..xs.len() {
        // The derived coordinates are (row, row²) keyed by UUID.
        assert_eq!((xs[k], ys[k]), (rows[k] as f64, (rows[k] * rows[k]) as f64));
    }
    // A two-dimensional embedding may place itself, and says so.
    let mut two = view("node2vec", "embedding-coordinates", false);
    two.result = derived("node2vec-2d");
    let document = compose_view(two, false).unwrap();
    let doc = Doc::new(&document);
    assert_eq!(
        doc.0.get("point.source", 0).unwrap().as_utf8("x").unwrap(),
        "embedding"
    );
    assert!(doc
        .decisions()
        .contains(&("GF_COMPOSE_EMBEDDING_2D".into(), 1)));
}

#[test]
fn coordinate_joins_follow_missing_and_extra_policies() {
    let mut partial = view("node2vec", "embedding-coordinates", false);
    partial.coordinates = Some(derived("node2vec-coordinates-partial"));
    let (code, _) = fail(request(&[], None, &[partial.clone()]));
    assert_eq!(code, "GF_COMPOSE_COORDINATES_MISSING");
    partial.missing = Some("hide");
    let document = compose_view(partial, false).unwrap();
    let doc = Doc::new(&document);
    assert_eq!(doc.f64s("point.x", 0).len(), 2);
    assert!(doc
        .decisions()
        .contains(&("GF_COMPOSE_MISSING_HIDDEN".into(), 2)));

    let mut subset = view("node2vec", "embedding-coordinates", false);
    subset.coordinates = Some(derived("node2vec-coordinates"));
    subset.rows = Some(vec![0, 1]);
    assert_eq!(
        fail(request(&[], None, &[subset.clone()])).0,
        "GF_COMPOSE_EXTRA_IDS"
    );
    subset.extra = Some("drop");
    let document = compose_view(subset, false).unwrap();
    assert!(Doc::new(&document)
        .decisions()
        .contains(&("GF_COMPOSE_EXTRA_DROPPED".into(), 2)));
}

#[test]
fn embeddings_against_an_incompatible_base_fail() {
    let (_, generation) = base_of("dag_longest_path");
    let mut spec = view("node2vec", "parallel-coordinates", true);
    spec.generation = Some(generation);
    assert_eq!(
        fail(request(&["dag"], Some(generation), &[spec])).0,
        "GF_COMPOSE_EXTRA_IDS"
    );
    let mut stale = view("node2vec", "parallel-coordinates", true);
    stale.generation = Some(generation);
    assert_eq!(
        fail(request(&["cyclic"], Some(base_of("node2vec").1), &[stale])).0,
        "GF_COMPOSE_GENERATION_STALE"
    );
}

#[test]
fn integer_cells_keep_their_exact_decimal_text() {
    // Unsigned census counts may exceed i64::MAX; the text stays exact.
    let field = crate::arrow_ipc::Field {
        name: "count".into(),
        nullable: false,
        data_type: DataType::Int {
            bits: 64,
            signed: false,
        },
        children: Vec::new(),
    };
    let bytes = u64::MAX.to_le_bytes();
    let table = Table {
        schema: crate::arrow_ipc::Schema {
            fields: vec![field],
            metadata: Vec::new(),
        },
        batches: vec![crate::arrow_ipc::Batch {
            rows: 1,
            columns: vec![crate::arrow_ipc::Array::fixed_for_tests(1, 8, &bytes)],
        }],
        rows: 1,
    };
    let values = crate::graphforge::columns::int_texts(&table.column("count").unwrap()).unwrap();
    assert_eq!(values[0].as_ref().unwrap().0, "18446744073709551615");
    assert_eq!(values[0].as_ref().unwrap().1, u64::MAX as f64);
}
