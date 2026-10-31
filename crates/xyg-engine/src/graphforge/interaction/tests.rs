//! Session, identity, and hierarchy proofs over real GraphForge fixtures and
//! small hand-built documents (for shapes the fixture corpus cannot express:
//! a node and an edge sharing a UUID, colliding result ids, 10,001 nodes).

use std::sync::{Arc, Mutex};

use super::*;
use crate::graph::COSE_NO_PARENT;
use crate::graph_interaction_state::{DerivedKey, GraphEntity, MAX_GRAPH_SELECTION_REFS};
use crate::graphforge::base;
use crate::graphforge::compose::{
    compose_bytes, nearest_visible_ancestors, COMPOSITION_VERSION, NONE_U32, NONE_U64,
};
use crate::graphforge::container::{Builder, Container, DOCUMENT_MAGIC, REQUEST_MAGIC};
use crate::graphforge::identity::{
    AggregateRef, DerivedRef, Fnv1a, GraphIdentity, ResolveError, ResultHash, ResultRef,
    ResultTable,
};
use crate::graphforge::NIL_UUID;
use crate::projection::GraphProjection;
use crate::temporal::CancelFlag;
use crate::temporal_graph::{TemporalBindingInput, TemporalGraphFrame};

// -- fixtures ----------------------------------------------------------------

fn read(path: &str) -> Vec<u8> {
    std::fs::read(format!(
        "{}/../../tests/fixtures/graphforge/{path}.arrow",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap_or_else(|e| panic!("{path}: {e}"))
}

fn result(name: &str) -> Vec<u8> {
    read(&format!("results/{name}"))
}

fn dag_tables() -> Vec<Vec<u8>> {
    vec![result("base-dag-nodes"), result("base-dag-edges")]
}

fn hierarchy_tables(nodes: &str) -> Vec<Vec<u8>> {
    vec![read(nodes), result("base-dag-edges")]
}

#[derive(Clone, Default)]
struct LayerSpec {
    name: &'static str,
    id: Option<&'static str>,
    rows: Option<Vec<u64>>,
    missing: Option<&'static str>,
}

fn layer(name: &'static str) -> LayerSpec {
    LayerSpec {
        name,
        ..Default::default()
    }
}

fn compose(tables: &[Vec<u8>], layers: &[LayerSpec]) -> Result<Vec<u8>, String> {
    let mut b = Builder::new(REQUEST_MAGIC);
    for (i, table) in tables.iter().enumerate() {
        b.bytes("base.table", i, table);
    }
    for (i, spec) in layers.iter().enumerate() {
        b.bytes("layer.result", i, &result(spec.name));
        b.utf8("layer.intent", i, "graph");
        if let Some(id) = spec.id {
            b.utf8("layer.result_id", i, id);
        }
        if let Some(rows) = &spec.rows {
            b.u64s("layer.rows", i, rows);
        }
        if let Some(missing) = spec.missing {
            b.utf8("layer.missing", i, missing);
        }
    }
    compose_bytes(&b.finish()).map_err(|document| {
        let c = Container::decode(&document, DOCUMENT_MAGIC).unwrap();
        c.get("error.code", 0)
            .unwrap()
            .as_utf8("error.code")
            .unwrap()
            .to_owned()
    })
}

fn composed(tables: &[Vec<u8>], layers: &[LayerSpec]) -> Vec<u8> {
    compose(tables, layers).unwrap_or_else(|code| panic!("compose failed: {code}"))
}

// -- hand-built documents ----------------------------------------------------

fn id(n: u32) -> Uuid {
    let mut out = [0u8; 16];
    out[..4].copy_from_slice(&n.to_le_bytes());
    out
}

enum E {
    Persisted(Uuid),
    Overlay { layer: u32, path: u64, order: i64 },
    Pair { layer: u32, row: u64 },
}

fn handmade_with(
    version: u32,
    nodes: &[Uuid],
    edges: &[E],
    layers: &[Option<&str>],
    parent: Option<(&[u32], &[u8])>,
) -> Vec<u8> {
    handmade_ends(version, nodes, edges, layers, parent, None)
}

/// `ends` are the dense `(source, target)` of each edge; absent, edge `i`
/// joins node `i % n` to `(i + 1) % n`.
fn handmade_ends(
    version: u32,
    nodes: &[Uuid],
    edges: &[E],
    layers: &[Option<&str>],
    parent: Option<(&[u32], &[u8])>,
    ends: Option<&[(u64, u64)]>,
) -> Vec<u8> {
    let mut b = Builder::new(DOCUMENT_MAGIC);
    b.u32s("status", 0, &[0]);
    b.utf8("kind", 0, "graph");
    b.u32s("composition.version", 0, &[version]);
    b.uuids("node.uuid", 0, nodes);
    let (mut uuid, mut derived, mut layer, mut order, mut path) =
        (vec![], vec![], vec![], vec![], vec![]);
    for edge in edges {
        match *edge {
            E::Persisted(u) => {
                uuid.push(u);
                derived.push(0u8);
                layer.push(NONE_U32);
                order.push(-1i64);
                path.push(NONE_U64);
            }
            E::Overlay {
                layer: l,
                path: p,
                order: o,
            } => {
                uuid.push(NIL_UUID);
                derived.push(1);
                layer.push(l);
                order.push(o);
                path.push(p);
            }
            E::Pair { layer: l, .. } => {
                uuid.push(NIL_UUID);
                derived.push(1);
                layer.push(l);
                order.push(-1);
                path.push(NONE_U64);
            }
        }
    }
    b.uuids("edge.uuid", 0, &uuid);
    b.u8s("edge.derived", 0, &derived);
    b.u32s("edge.layer", 0, &layer);
    b.i64s("edge.order", 0, &order);
    b.u64s("edge.path", 0, &path);
    let n = nodes.len().max(1) as u64;
    let ends: Vec<(u64, u64)> = match ends {
        Some(ends) => ends.to_vec(),
        None => (0..edges.len() as u64)
            .map(|i| (i % n, (i + 1) % n))
            .collect(),
    };
    b.u64s(
        "edge.source",
        0,
        &ends.iter().map(|e| e.0).collect::<Vec<_>>(),
    );
    b.u64s(
        "edge.target",
        0,
        &ends.iter().map(|e| e.1).collect::<Vec<_>>(),
    );
    for (i, result_id) in layers.iter().enumerate() {
        b.utf8("layer.schema", i, "test");
        if let Some(result_id) = result_id {
            b.utf8("layer.result_id", i, result_id);
        }
        let rows: Vec<u64> = edges
            .iter()
            .map(|edge| match edge {
                E::Pair { layer, row } if *layer as usize == i => *row,
                _ => NONE_U64,
            })
            .collect();
        b.u64s("layer.edge_rows", i, &rows);
    }
    if let Some((parents, valid)) = parent {
        b.u32s("node.parent", 0, parents);
        b.u8s("node.parent.valid", 0, valid);
    }
    b.finish()
}

fn handmade(nodes: &[Uuid], edges: &[E], layers: &[Option<&str>]) -> Vec<u8> {
    handmade_with(COMPOSITION_VERSION, nodes, edges, layers, None)
}

/// Nodes 1..3, persisted edges 11 (1→2) and 12 (2→3), one overlay step.
fn standard_doc() -> Vec<u8> {
    handmade(
        &[id(1), id(2), id(3)],
        &[
            E::Persisted(id(11)),
            E::Persisted(id(12)),
            E::Overlay {
                layer: 0,
                path: 0,
                order: 0,
            },
        ],
        &[Some("route")],
    )
}

fn session(document: &[u8]) -> GraphSession {
    GraphSession::create(document, SessionLoad::default(), 7).unwrap()
}

fn header(session: &GraphSession, op_seq: u64) -> OpHeader {
    OpHeader {
        stamp: Stamp {
            instance_id: session.instance_id(),
            render_revision: session.render_revision(),
        },
        op_seq,
    }
}

// -- hierarchy: composition ---------------------------------------------------

fn section_u32(document: &[u8], name: &str) -> Vec<u32> {
    let c = Container::decode(document, DOCUMENT_MAGIC).unwrap();
    c.get(name, 0).unwrap().as_u32(name).unwrap()
}

#[test]
fn the_document_carries_the_hierarchy_and_the_session_reads_only_it() {
    let document = composed(
        &hierarchy_tables("hierarchy_dag_nodes"),
        &[layer("dag_longest_path")],
    );
    assert_eq!(
        section_u32(&document, "composition.version"),
        [COMPOSITION_VERSION]
    );
    assert_eq!(
        section_u32(&document, "node.parent"),
        [NONE_U32, 0, 1, NONE_U32]
    );
    let c = Container::decode(&document, DOCUMENT_MAGIC).unwrap();
    assert_eq!(
        c.get("node.parent.valid", 0).unwrap().as_u8("v").unwrap(),
        [0, 1, 1, 0]
    );

    let s = session(&document);
    assert_eq!(
        (0..4).map(|n| s.parent_of(n)).collect::<Vec<_>>(),
        [None, Some(0), Some(1), None]
    );
    // A document composed without a parent column has no hierarchy at all.
    let flat = session(&composed(&dag_tables(), &[layer("dag_longest_path")]));
    assert!((0..4).all(|n| flat.parent_of(n).is_none()));
    assert_eq!(
        (flat.budgets(), flat.seed()),
        ((DEFAULT_NODE_BUDGET, DEFAULT_EDGE_BUDGET), 0)
    );
}

#[test]
fn invalid_hierarchies_fail_composition_with_stable_codes() {
    for (nodes, code) in [
        (
            "hierarchy_dag_nodes_unknown_parent",
            "GF_BASE_PARENT_UNKNOWN",
        ),
        ("hierarchy_dag_nodes_self_parent", "GF_BASE_PARENT_SELF"),
        ("hierarchy_dag_nodes_cycle", "GF_BASE_PARENT_CYCLE"),
    ] {
        assert_eq!(
            compose(&hierarchy_tables(nodes), &[layer("dag_longest_path")]).unwrap_err(),
            code,
            "{nodes}"
        );
    }
}

#[test]
fn a_hidden_parent_hands_its_children_to_the_nearest_visible_ancestor() {
    let tables = hierarchy_tables("hierarchy_dag_nodes");
    let (nodes, edges) = (result("base-dag-nodes"), result("base-dag-edges"));
    let tabs = [
        crate::arrow_ipc::read_table(&nodes).unwrap(),
        crate::arrow_ipc::read_table(&edges).unwrap(),
    ];
    let middle = base::build(&tabs, None, true).unwrap().node_uuid[1];
    // Keep every topological_sort row except the one for the middle node.
    let ranked = result("topological_sort");
    let table = crate::arrow_ipc::read_table(&ranked).unwrap();
    let ids =
        crate::graphforge::columns::uuids(&table.column("node_uuid").unwrap(), false).unwrap();
    let rows: Vec<u64> = (0..ids.len() as u64)
        .filter(|&row| ids[row as usize] != Some(middle))
        .collect();
    let document = composed(
        &tables,
        &[LayerSpec {
            rows: Some(rows),
            missing: Some("hide"),
            ..layer("topological_sort")
        }],
    );
    // Composed nodes are [n0, n2, n3]; n2's parent n1 is hidden, so n2 → n0.
    assert_eq!(
        section_u32(&document, "node.parent"),
        [NONE_U32, 0, NONE_U32]
    );
    let c = Container::decode(&document, DOCUMENT_MAGIC).unwrap();
    let codes = c.get("decision.code", 0).unwrap().as_texts("c").unwrap();
    let counts = c.get("decision.count", 0).unwrap().as_u64("c").unwrap();
    let at = codes
        .iter()
        .position(|c| *c == "GF_COMPOSE_PARENT_REPARENTED")
        .unwrap();
    assert_eq!(counts[at], 1);
    assert_eq!(session(&document).parent_of(1), Some(0));
}

#[test]
fn sessions_reject_documents_they_cannot_trust() {
    let nodes = [id(1), id(2), id(3)];
    let ok = |parent: Option<(&[u32], &[u8])>| {
        GraphSession::create(
            &handmade_with(COMPOSITION_VERSION, &nodes, &[], &[], parent),
            SessionLoad::default(),
            1,
        )
        .map(|_| ())
    };
    assert_eq!(ok(Some((&[0, 0, 1], &[0, 1, 1]))), Ok(()));
    let invalid = Err(InteractionStatus::Invalid);
    assert_eq!(ok(Some((&[0, 2, 1], &[0, 1, 1]))), invalid, "cycle");
    assert_eq!(ok(Some((&[0, 1, 1], &[0, 1, 1]))), invalid, "self parent");
    assert_eq!(
        ok(Some((&[0, 9, 1], &[0, 1, 1]))),
        invalid,
        "parent out of range"
    );
    assert_eq!(ok(Some((&[0, 0], &[0, 1]))), invalid, "short plane");
    assert_eq!(ok(Some((&[0, 0, 1], &[0, 2, 1]))), invalid, "validity > 1");
    // Version skew: a v1 document carries no hierarchy contract.
    assert_eq!(
        GraphSession::create(
            &handmade_with(1, &nodes, &[], &[], None),
            SessionLoad::default(),
            1
        )
        .map(|_| ()),
        invalid
    );
    assert_eq!(
        GraphSession::create(b"not a document", SessionLoad::default(), 1).map(|_| ()),
        invalid
    );
    // Session-local inputs are validated against the document's node count.
    let doc = handmade(&nodes, &[], &[]);
    let create = |load: SessionLoad| GraphSession::create(&doc, load, 1).map(|_| ());
    let short = || Some(vec![0.0, 1.0]);
    assert_eq!(
        create(SessionLoad {
            x: short(),
            y: short(),
            ..Default::default()
        }),
        invalid
    );
    assert_eq!(
        create(SessionLoad {
            x: Some(vec![0.0; 3]),
            ..Default::default()
        }),
        invalid,
        "x without y"
    );
    assert_eq!(
        create(SessionLoad {
            x: Some(vec![0.0, f64::NAN, 0.0]),
            y: Some(vec![0.0; 3]),
            ..Default::default()
        }),
        invalid
    );
    assert_eq!(
        create(SessionLoad {
            collapsed: Some(vec![0, 2, 0]),
            ..Default::default()
        }),
        invalid
    );
    assert_eq!(
        create(SessionLoad {
            budgets: Some((0, 5)),
            ..Default::default()
        }),
        invalid
    );
    assert_eq!(
        create(SessionLoad {
            x: Some(vec![0.0; 3]),
            y: Some(vec![1.0; 3]),
            collapsed: Some(vec![0, 1, 0]),
            budgets: Some((10, 20)),
            seed: 9,
            ..Default::default()
        }),
        Ok(())
    );
}

#[test]
fn load_pinned_seeds_the_uuid_keyed_pin_set() {
    let s = GraphSession::create(
        &handmade(&[id(1), id(2), id(3)], &[], &[]),
        SessionLoad {
            pinned: Some(vec![1, 0, 1]),
            ..Default::default()
        },
        1,
    )
    .unwrap();
    assert_eq!(s.pinned().unwrap(), [id(1), id(3)]);
}

/// The definition: walk up through hidden ancestors, one node at a time.
fn naive_nearest_visible(parent: &[u64], visible: &[bool]) -> Vec<u64> {
    (0..parent.len())
        .map(|node| {
            let mut up = parent[node];
            while up != COSE_NO_PARENT && !visible[up as usize] {
                up = parent[up as usize];
            }
            up
        })
        .collect()
}

#[test]
fn nearest_visible_ancestors_match_the_walking_definition_on_random_forests() {
    let mut state = 0x2545_f491_4f6c_dd1du64;
    let mut next = move |bound: u64| {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        state % bound
    };
    for round in 0..200 {
        let n = 1 + next(40) as usize;
        // Parents point backwards in rank, then ranks are relabelled so a
        // parent may have a larger index than its child.
        let mut label: Vec<usize> = (0..n).collect();
        for i in (1..n).rev() {
            label.swap(i, next(i as u64 + 1) as usize);
        }
        let mut parent = vec![COSE_NO_PARENT; n];
        for rank in 1..n {
            if next(4) != 0 {
                parent[label[rank]] = label[next(rank as u64) as usize] as u64;
            }
        }
        let visible: Vec<bool> = (0..n).map(|_| next(3) == 0).collect();
        assert_eq!(
            nearest_visible_ancestors(&parent, &visible).0,
            naive_nearest_visible(&parent, &visible),
            "round {round}"
        );
    }
}

#[test]
fn a_deep_shared_hidden_ancestry_is_resolved_in_linear_time() {
    // 100,000 hidden chain nodes, then 100,000 visible children of the bottom
    // one.
    let chain = 100_000usize;
    let n = 2 * chain;
    let mut parent = vec![COSE_NO_PARENT; n];
    for node in 1..chain {
        parent[node] = (node - 1) as u64;
    }
    for child in chain..n {
        parent[child] = (chain - 1) as u64;
    }
    // The root is visible; everything else in the chain is hidden.
    let mut visible = vec![false; n];
    visible[0] = true;
    for flag in &mut visible[chain..] {
        *flag = true;
    }
    let (ancestor, links) = nearest_visible_ancestors(&parent, &visible);
    // Deterministic work bound: every parent link is followed at most twice
    // (climb, then unwind). The walking definition follows ~10^10.
    assert!(
        links <= 2 * n as u64,
        "quadratic ancestor walk: {links} links"
    );
    assert!(ancestor[chain..].iter().all(|&a| a == 0));
    assert_eq!(ancestor[1], 0);
    assert_eq!(ancestor[0], COSE_NO_PARENT);
}

#[test]
fn a_malformed_result_id_rejects_the_session_instead_of_reading_as_absent() {
    let good = handmade(&[id(1), id(2)], &[], &[None]);
    // Same document, but layer 0 carries a result id of the wrong element type.
    let mut b = Builder::new(DOCUMENT_MAGIC);
    b.extend_from(&Container::decode(&good, DOCUMENT_MAGIC).unwrap());
    b.u32s("layer.result_id", 0, &[7]);
    let bad = b.finish();
    let doc = ComposedDocument::decode(&bad).unwrap();
    assert_eq!(doc.result_id(0).unwrap_err().code, "GF_INTERACTION_INVALID");
    assert!(GraphIdentity::<Fnv1a>::from_document(&doc).is_err());
    assert_eq!(
        GraphSession::create(&bad, SessionLoad::default(), 1).map(|_| ()),
        Err(InteractionStatus::Invalid)
    );
    // Right element type, invalid UTF-8: also an error, not "no id".
    let mut utf8 = Builder::new(DOCUMENT_MAGIC);
    utf8.extend_from(&Container::decode(&good, DOCUMENT_MAGIC).unwrap());
    utf8.utf8("layer.result_id", 0, "QQ");
    let mut broken = utf8.finish();
    let at = broken.windows(2).position(|w| w == b"QQ").unwrap();
    broken[at..at + 2].copy_from_slice(&[0xff, 0xfe]);
    assert_eq!(
        GraphSession::create(&broken, SessionLoad::default(), 1).map(|_| ()),
        Err(InteractionStatus::Invalid)
    );
    // The well-formed absent id still creates a session.
    assert!(GraphSession::create(&good, SessionLoad::default(), 1).is_ok());
}

// -- identity ----------------------------------------------------------------

fn assert_roundtrips<H: ResultHash>(identity: &GraphIdentity<H>) {
    for node in 0..identity.node_count() {
        let r = identity.node_ref(node);
        assert_eq!(identity.resolve(&r), Ok(ElementIndex::Node(node)));
    }
    for edge in 0..identity.edge_count() {
        let local = identity.edge_ref(edge);
        assert_eq!(
            identity.resolve(&local),
            Ok(ElementIndex::Edge(edge)),
            "local"
        );
        let wire = identity.to_transport(&local).unwrap();
        assert_eq!(
            identity.resolve(&wire),
            Ok(ElementIndex::Edge(edge)),
            "transport"
        );
        match &local {
            ElementRef::Edge(uuid) => assert_eq!(identity.edge_index(uuid), Some(edge)),
            ElementRef::Derived(_) => assert!(identity.derived_key(edge).is_some()),
            other => panic!("unexpected {other:?}"),
        }
    }
}

#[test]
fn a_three_step_path_has_three_distinct_stable_derived_refs() {
    let document = composed(
        &dag_tables(),
        &[LayerSpec {
            id: Some("route-a"),
            ..layer("dag_longest_path")
        }],
    );
    let s = session(&document);
    let identity = s.identity();
    assert_eq!((identity.node_count(), identity.edge_count()), (4, 7));
    assert_roundtrips(identity);
    let derived: Vec<(usize, DerivedRef)> = (0..identity.edge_count())
        .filter_map(|e| match identity.edge_ref(e) {
            ElementRef::Derived(d) => Some((e, d)),
            _ => None,
        })
        .collect();
    assert_eq!(derived.len(), 3);
    let steps: Vec<(u32, u64, u64)> = derived
        .iter()
        .map(|(_, d)| (d.layer, d.path, d.order))
        .collect();
    assert_eq!(steps, [(0, 0, 0), (0, 0, 1), (0, 0, 2)]);
    // The state key carries the exact id, not a table index.
    let key = identity.derived_key(derived[1].0).unwrap();
    assert_eq!(key.result_id.as_deref(), Some("route-a"));
    assert_eq!(identity.resolve_derived_key(&key), Some(derived[1].0));
}

#[test]
fn derived_pairs_and_overlay_steps_never_share_a_key() {
    let tables = vec![result("base-cyclic-nodes"), result("base-cyclic-edges")];
    let document = composed(&tables, &[layer("node_similarity"), layer("dijkstra")]);
    let s = session(&document);
    let identity = s.identity();
    assert_roundtrips(identity);
    let mut keys: Vec<(u32, u64, u64)> = (0..identity.edge_count())
        .filter_map(|e| identity.derived_key(e))
        .map(|k| (k.layer, k.path, k.order))
        .collect();
    let derived = keys.len();
    assert!(
        keys.iter().filter(|k| k.0 == 0).count() > 1,
        "several pairs share layer 0"
    );
    assert!(
        keys.iter().any(|k| k.0 == 1 && k.1 == 0),
        "an overlay step exists"
    );
    keys.sort_unstable();
    keys.dedup();
    assert_eq!(keys.len(), derived, "keys are unique per composition");
}

#[test]
fn a_node_and_an_edge_may_share_a_uuid_and_refs_are_kind_qualified() {
    let document = handmade(&[id(1), id(2)], &[E::Persisted(id(1))], &[]);
    let mut s = session(&document);
    let by_uuid = s
        .select_uuids(header(&s, 1), &[id(1)], SelectMode::Replace)
        .unwrap();
    assert_eq!(by_uuid.selected, 2, "a shared UUID selects both kinds");
    let node_only = s
        .select_refs(
            header(&s, 2),
            &[ElementRef::Node(id(1))],
            SelectMode::Replace,
        )
        .unwrap();
    assert_eq!(node_only.selected, 1);
    assert_eq!(s.selection().unwrap(), [ElementRef::Node(id(1))]);
    let edge_only = s
        .select_refs(
            header(&s, 3),
            &[ElementRef::Edge(id(1))],
            SelectMode::Replace,
        )
        .unwrap();
    assert_eq!(edge_only.selected, 1);
    assert_eq!(s.selection().unwrap(), [ElementRef::Edge(id(1))]);
}

#[test]
fn derived_pairs_are_keyed_by_their_result_row() {
    let pair = |row| E::Pair { layer: 0, row };
    let nodes = [id(1), id(2)];
    let document = handmade(&nodes, &[pair(4), pair(9)], &[Some("pairs")]);
    let s = session(&document);
    assert_roundtrips(s.identity());
    let keys: Vec<_> = (0..2)
        .map(|e| s.identity().derived_key(e).unwrap())
        .collect();
    assert_eq!(
        keys.iter().map(|k| (k.path, k.order)).collect::<Vec<_>>(),
        [(NONE_U64, 4), (NONE_U64, 9)]
    );
    // Two pairs from one result row would be indistinguishable: refuse.
    let clash = handmade(&nodes, &[pair(4), pair(4)], &[Some("pairs")]);
    assert_eq!(
        GraphSession::create(&clash, SessionLoad::default(), 1).map(|_| ()),
        Err(InteractionStatus::Invalid)
    );
}

/// Every id hashes alike: the strongest possible collision, injected into the
/// lookup structure itself (no production branch is test-only).
struct AllCollide;

impl ResultHash for AllCollide {
    fn hash(_: &[u8]) -> u64 {
        0
    }
}

fn overlay_doc(layers: &[Option<&str>]) -> Vec<u8> {
    let edges: Vec<E> = (0..layers.len() as u32)
        .map(|layer| E::Overlay {
            layer,
            path: u64::from(layer),
            order: 0,
        })
        .collect();
    handmade(&[id(1), id(2)], &edges, layers)
}

fn derived_ref(result: ResultRef, layer: u32) -> ElementRef {
    ElementRef::Derived(DerivedRef {
        result,
        layer,
        path: u64::from(layer),
        order: 0,
    })
}

#[test]
fn colliding_result_ids_never_cross_resolve() {
    assert_eq!(AllCollide::hash(b"aa"), AllCollide::hash(b"bb"));
    let mut table = ResultTable::<AllCollide>::default();
    let (aa, bb) = (table.intern(Some("aa")), table.intern(Some("bb")));
    assert_ne!(aa, bb);
    assert_eq!(table.find(Some("aa")), Some(aa));
    assert_eq!(table.find(Some("bb")), Some(bb));
    assert_eq!(table.find(Some("cc")), None, "absent despite an equal hash");
    assert_eq!(
        table.find(None),
        Some(crate::graphforge::identity::NO_RESULT)
    );
    assert_ne!(
        table.find(Some("")),
        table.find(None),
        "empty is not absent"
    );

    let document = overlay_doc(&[Some("aa"), Some("bb")]);
    let doc = ComposedDocument::decode(&document).unwrap();
    let identity = GraphIdentity::<AllCollide>::from_document(&doc).unwrap();
    assert_roundtrips(&identity);
    let exact = |id: &str, layer| derived_ref(ResultRef::Exact(Some(id.into())), layer);
    assert_eq!(identity.resolve(&exact("aa", 0)), Ok(ElementIndex::Edge(0)));
    assert_eq!(identity.resolve(&exact("bb", 1)), Ok(ElementIndex::Edge(1)));
    // Hash-equal, string-different: the neighbor's id must not resolve.
    assert_eq!(
        identity.resolve(&exact("bb", 0)),
        Err(ResolveError::Unresolved)
    );
    assert_eq!(
        identity.resolve(&exact("aa", 1)),
        Err(ResolveError::Unresolved)
    );
    assert_eq!(
        identity.resolve(&exact("cc", 0)),
        Err(ResolveError::Unresolved)
    );
    assert_eq!(
        identity.resolve(&derived_ref(ResultRef::Exact(None), 0)),
        Err(ResolveError::Unresolved),
        "no id is not the id \"aa\""
    );
    assert_eq!(
        identity.resolve(&derived_ref(ResultRef::Local(bb), 0)),
        Err(ResolveError::Unresolved)
    );
}

#[test]
fn replacing_a_result_id_invalidates_state_keyed_to_the_old_string() {
    let before = overlay_doc(&[Some("aa"), Some("bb")]);
    let after = overlay_doc(&[Some("zz"), Some("bb")]);
    let absent = overlay_doc(&[None, Some("bb")]);
    let build = |bytes: &[u8]| {
        let doc = ComposedDocument::decode(bytes).unwrap();
        GraphIdentity::<AllCollide>::from_document(&doc).unwrap()
    };
    let (before, after, absent) = (build(&before), build(&after), build(&absent));
    let key: DerivedKey = before.derived_key(0).unwrap();
    let kept: DerivedKey = before.derived_key(1).unwrap();
    assert_eq!(before.resolve_derived_key(&key), Some(0));
    assert_eq!(after.resolve_derived_key(&key), None, "id replaced");
    assert_eq!(absent.resolve_derived_key(&key), None, "id removed");
    assert_eq!(
        after.resolve_derived_key(&kept),
        Some(1),
        "untouched layer survives"
    );
    // A transported ref naming an id this session never saw resolves to nothing.
    let foreign = before.to_transport(&before.edge_ref(0)).unwrap();
    assert_eq!(after.resolve(&foreign), Err(ResolveError::Unresolved));
}

#[test]
fn real_fnv_keeps_many_ids_distinct() {
    let mut table = ResultTable::<Fnv1a>::default();
    let ids: Vec<String> = (0..2_000).map(|i| format!("result-{i}")).collect();
    let indices: Vec<u32> = ids.iter().map(|s| table.intern(Some(s))).collect();
    for (id, &index) in ids.iter().zip(&indices) {
        assert_eq!(table.find(Some(id)), Some(index));
        assert_eq!(table.get(index), Some(Some(id.as_str())));
    }
    assert_eq!(
        table.intern(Some("result-7")),
        indices[7],
        "interning is idempotent"
    );
}

// -- state machine -------------------------------------------------------------

#[test]
fn selection_is_atomic_over_unresolved_and_aggregate_refs() {
    let mut s = session(&standard_doc());
    let derived = s.identity().edge_ref(2);
    let out = s
        .select_refs(
            header(&s, 1),
            &[
                ElementRef::Node(id(2)),
                ElementRef::Edge(id(11)),
                derived.clone(),
            ],
            SelectMode::Replace,
        )
        .unwrap();
    assert_eq!(
        (out.selected, out.changed.len(), out.state_changed),
        (3, 3, true)
    );
    assert!(s.selection().unwrap().contains(&derived));

    let before = s.selection().unwrap();
    assert_eq!(
        s.select_refs(
            header(&s, 2),
            &[ElementRef::Node(id(1)), ElementRef::Node(id(99))],
            SelectMode::Replace
        ),
        Err(InteractionStatus::Invalid)
    );
    assert_eq!(
        s.select_refs(
            header(&s, 2),
            &[ElementRef::Aggregate(AggregateRef {
                render_revision: 0,
                index: 0
            })],
            SelectMode::Replace
        ),
        Err(InteractionStatus::Stale),
        "no render is published, so an aggregate stamp cannot match"
    );
    assert_eq!(s.selection().unwrap(), before, "failed ops change nothing");

    let toggled = s
        .select_refs(header(&s, 2), &before, SelectMode::Toggle)
        .unwrap();
    assert_eq!((toggled.selected, toggled.changed.len()), (0, 3));
}

#[test]
fn select_uuids_counts_unmatched_identities() {
    let mut s = session(&standard_doc());
    let out = s
        .select_uuids(header(&s, 1), &[id(1), id(11), id(99)], SelectMode::Add)
        .unwrap();
    assert_eq!((out.selected, out.unmatched), (2, 1));
}

#[test]
fn stale_stamps_are_rejected_without_consuming_the_op_seq() {
    let mut s = session(&standard_doc());
    let mut stale = header(&s, 1);
    stale.stamp.render_revision += 1;
    assert_eq!(
        s.select_uuids(stale, &[id(1)], SelectMode::Replace),
        Err(InteractionStatus::Stale)
    );
    stale.stamp = Stamp {
        instance_id: 8,
        render_revision: s.render_revision(),
    };
    assert_eq!(
        s.clear(stale),
        Err(InteractionStatus::Stale),
        "another instance's stamp"
    );
    assert!(s.selection().unwrap().is_empty());
    s.select_uuids(header(&s, 1), &[id(1)], SelectMode::Replace)
        .unwrap();
}

#[test]
fn a_repeated_op_seq_returns_the_retained_outcome_without_changing_state() {
    let mut s = session(&standard_doc());
    let first = s
        .select_uuids(header(&s, 1), &[id(1)], SelectMode::Replace)
        .unwrap();
    // The retry carries different arguments; it must not be applied.
    let retry = s
        .select_uuids(header(&s, 1), &[id(2)], SelectMode::Replace)
        .unwrap();
    assert_eq!(retry, first);
    assert_eq!(s.selection().unwrap(), [ElementRef::Node(id(1))]);
    // A retry is served even if the stamp moved on in the meantime.
    let mut moved = header(&s, 1);
    moved.stamp.render_revision = 99;
    assert_eq!(s.clear(moved).unwrap(), first);

    s.select_uuids(header(&s, 2), &[id(2)], SelectMode::Replace)
        .unwrap();
    assert_eq!(
        s.clear(header(&s, 1)),
        Err(InteractionStatus::Invalid),
        "an older op_seq is not a retry"
    );
    assert_eq!(
        s.clear(header(&s, 0)),
        Err(InteractionStatus::Invalid),
        "0 is not an op_seq"
    );
    assert_eq!(s.selection().unwrap(), [ElementRef::Node(id(2))]);
}

#[test]
fn focus_is_independent_of_selection_and_survives_clear() {
    let mut s = session(&standard_doc());
    assert_eq!(
        s.select_focused(header(&s, 1), SelectMode::Replace),
        Err(InteractionStatus::Invalid),
        "nothing is focused"
    );
    let derived = s.identity().edge_ref(2);
    for (seq, target) in [(2, ElementRef::Node(id(2))), (3, derived.clone())] {
        let out = s.focus_ref(header(&s, seq), Some(&target)).unwrap();
        assert!(out.state_changed);
        assert_eq!(s.focus().unwrap(), Some(target));
        assert!(s.selection().unwrap().is_empty());
    }
    assert!(
        !s.focus_ref(header(&s, 4), Some(&derived))
            .unwrap()
            .state_changed
    );
    s.select_focused(header(&s, 5), SelectMode::Replace)
        .unwrap();
    assert_eq!(s.selection().unwrap(), std::slice::from_ref(&derived));
    let cleared = s.clear(header(&s, 6)).unwrap();
    assert!(cleared.state_changed);
    assert!(
        !s.clear(header(&s, 7)).unwrap().state_changed,
        "nothing left to clear"
    );
    assert_eq!(s.focus().unwrap(), Some(derived));
    s.focus_ref(header(&s, 8), None).unwrap();
    assert_eq!(s.focus().unwrap(), None);
    assert_eq!(
        s.focus_ref(header(&s, 9), Some(&ElementRef::Edge(id(99)))),
        Err(InteractionStatus::Invalid)
    );
}

#[test]
fn the_selection_cap_rejects_atomically_at_10001() {
    let nodes: Vec<Uuid> = (1..=MAX_GRAPH_SELECTION_REFS as u32 + 1).map(id).collect();
    let mut s = session(&handmade(&nodes, &[], &[]));
    let within = &nodes[..MAX_GRAPH_SELECTION_REFS];
    let out = s
        .select_uuids(header(&s, 1), within, SelectMode::Replace)
        .unwrap();
    assert_eq!(out.selected, MAX_GRAPH_SELECTION_REFS);
    let before = s.selection().unwrap();

    assert_eq!(
        s.select_uuids(
            header(&s, 2),
            &nodes[MAX_GRAPH_SELECTION_REFS..],
            SelectMode::Add
        ),
        Err(InteractionStatus::SelectionTooLarge)
    );
    assert_eq!(
        s.select_uuids(header(&s, 2), &nodes, SelectMode::Replace),
        Err(InteractionStatus::SelectionTooLarge)
    );
    assert_eq!(s.selection().unwrap(), before, "rejection changed nothing");
    // The rejected seq was not consumed: the same seq now succeeds.
    let removed = s
        .select_uuids(header(&s, 2), &nodes[..1], SelectMode::Toggle)
        .unwrap();
    assert_eq!(removed.selected, MAX_GRAPH_SELECTION_REFS - 1);
}

// -- shared owner --------------------------------------------------------------

struct Registry {
    graph: Mutex<Option<TemporalGraph>>,
}

impl TemporalHost for Registry {
    fn with_graph(&self, handle: TemporalHandle, f: &mut dyn FnMut(&mut TemporalGraph)) -> bool {
        match (handle, self.graph.lock().unwrap().as_mut()) {
            (TemporalHandle(1), Some(graph)) => {
                f(graph);
                true
            }
            _ => false,
        }
    }
}

const HANDLE: TemporalHandle = TemporalHandle(1);

fn temporal(nodes: &[Uuid]) -> Arc<Registry> {
    let projection = GraphProjection::new(
        nodes,
        &[id(11), id(12)],
        &[nodes[0], nodes[1]],
        &[nodes[1], nodes[2]],
        None,
        true,
    )
    .unwrap();
    let graph = TemporalGraph::bind(
        &projection,
        TemporalBindingInput::default(),
        TemporalBindingInput::default(),
    )
    .unwrap();
    Arc::new(Registry {
        graph: Mutex::new(Some(graph)),
    })
}

fn frame(registry: &Registry, revision: u64) -> TemporalGraphFrame {
    let mut guard = registry.graph.lock().unwrap();
    let graph = guard.as_mut().unwrap();
    let budget = graph.required_budget().unwrap();
    graph
        .frame(revision, 5, 0, 10, &CancelFlag::new(), budget)
        .unwrap()
}

fn bound_session() -> (GraphSession, Arc<Registry>) {
    let registry = temporal(&[id(1), id(2), id(3)]);
    let mut s = session(&standard_doc());
    s.bind_temporal(registry.clone(), HANDLE).unwrap();
    (s, registry)
}

#[test]
fn a_bound_session_and_its_temporal_graph_are_one_state() {
    let (mut s, registry) = bound_session();
    assert!(s.is_bound());
    let derived = s.identity().edge_ref(2);
    s.select_refs(
        header(&s, 1),
        &[
            ElementRef::Node(id(2)),
            ElementRef::Edge(id(11)),
            derived.clone(),
        ],
        SelectMode::Replace,
    )
    .unwrap();
    s.focus_ref(header(&s, 2), Some(&ElementRef::Node(id(2))))
        .unwrap();

    // Session → temporal: the frame publishes exactly what the session wrote.
    let f = frame(&registry, 1);
    assert_eq!(f.selected_visible_node_ids(), [id(2)]);
    assert_eq!(f.selected_visible_edge_ids(), [id(11)]);
    assert_eq!(f.focused_visible(), Some(GraphEntity::Node(id(2))));

    // Temporal → session: a Replace through TemporalGraph is visible, and it
    // drops the derived selection a temporal graph cannot express.
    {
        let mut guard = registry.graph.lock().unwrap();
        let graph = guard.as_mut().unwrap();
        graph.set_selection([id(3)], [id(12)]).unwrap();
        graph.set_focus(Some(GraphEntity::Edge(id(12)))).unwrap();
    }
    let mut seen = s.selection().unwrap();
    seen.sort_by_key(|r| format!("{r:?}"));
    assert_eq!(seen, [ElementRef::Edge(id(12)), ElementRef::Node(id(3))]);
    assert_eq!(s.focus().unwrap(), Some(ElementRef::Edge(id(12))));
    let f = frame(&registry, 2);
    assert_eq!(f.selected_visible_node_ids(), [id(3)]);

    // Clearing through the session is visible to the next frame. Two frames
    // changed the temporal visibility since the host last rendered, so the
    // host republishes first (a stale stamp would be rejected).
    s.render(None).unwrap();
    s.clear(header(&s, 3)).unwrap();
    assert!(frame(&registry, 3).selected_visible_node_ids().is_empty());
}

#[test]
fn binding_discards_owned_state_and_rejects_mismatched_planes() {
    let mut s = session(&standard_doc());
    s.select_uuids(header(&s, 1), &[id(1)], SelectMode::Replace)
        .unwrap();

    let other = temporal(&[id(1), id(2), id(4)]);
    assert_eq!(
        s.bind_temporal(other, HANDLE),
        Err(InteractionStatus::Invalid)
    );
    assert!(!s.is_bound());
    assert_eq!(
        s.selection().unwrap(),
        [ElementRef::Node(id(1))],
        "owned state kept"
    );

    let registry = temporal(&[id(1), id(2), id(3)]);
    assert_eq!(
        s.bind_temporal(registry.clone(), TemporalHandle(2)),
        Err(InteractionStatus::Unbound),
        "unknown handle"
    );
    s.bind_temporal(registry.clone(), HANDLE).unwrap();
    assert!(
        s.selection().unwrap().is_empty(),
        "the pre-existing temporal state wins"
    );
}

#[test]
fn disposing_the_temporal_graph_unbinds_until_the_session_unbinds() {
    let (mut s, registry) = bound_session();
    s.select_uuids(header(&s, 1), &[id(1)], SelectMode::Replace)
        .unwrap();
    *registry.graph.lock().unwrap() = None;
    assert_eq!(s.selection(), Err(InteractionStatus::Unbound));
    assert_eq!(
        s.select_uuids(header(&s, 2), &[id(2)], SelectMode::Replace),
        Err(InteractionStatus::Unbound)
    );
    s.unbind().unwrap();
    assert!(!s.is_bound());
    assert!(
        s.selection().unwrap().is_empty(),
        "a fresh empty Owned state"
    );
    s.select_uuids(header(&s, 2), &[id(2)], SelectMode::Replace)
        .unwrap();
}

#[test]
fn destroying_a_bound_session_leaves_the_temporal_state_untouched() {
    let (mut s, registry) = bound_session();
    s.select_uuids(header(&s, 1), &[id(1), id(12)], SelectMode::Replace)
        .unwrap();
    drop(s);
    let f = frame(&registry, 1);
    assert_eq!(f.selected_visible_node_ids(), [id(1)]);
    assert_eq!(f.selected_visible_edge_ids(), [id(12)]);
}

mod session;

mod pick;

mod wire;
