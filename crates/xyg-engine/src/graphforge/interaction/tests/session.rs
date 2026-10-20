//! S2 proofs: render publication (F2), ingress parity with the host render
//! path, selection / focus / hover / highlight planes, disclosure, pin / move /
//! relayout, walks, bound temporal visibility (F4), identity round trips, and
//! bounded work.

use super::*;
use crate::graph::{
    build_render, force_create_cose, force_destroy, force_tick, CoseOptions, LodTier, Viewport,
};
use crate::graph_interaction_state::HighlightPlane;
use crate::graph_style::{
    FLAG_COMMUNITY, STATE_AGGREGATE, STATE_HOVERED, STATE_NEIGHBOR, STATE_NORMAL, STATE_PINNED,
    STATE_SELECTED,
};
use crate::temporal::{TemporalColumn, TemporalPrecision};

const NONE: u32 = NONE_U32;

fn loaded(document: &[u8], load: SessionLoad) -> GraphSession {
    GraphSession::create(document, load, 7).unwrap()
}

fn at(x: &[f64], y: &[f64]) -> SessionLoad {
    SessionLoad {
        x: Some(x.to_vec()),
        y: Some(y.to_vec()),
        ..SessionLoad::default()
    }
}

fn persisted(count: u32) -> Vec<E> {
    (0..count).map(|i| E::Persisted(id(11 + i))).collect()
}

fn node_ids(count: u32) -> Vec<Uuid> {
    (1..=count).map(id).collect()
}

fn select(s: &mut GraphSession, seq: u64, nodes: &[u32], mode: SelectMode) -> OpOutcome {
    let refs: Vec<ElementRef> = nodes.iter().map(|&n| ElementRef::Node(id(n))).collect();
    s.select_refs(header(s, seq), &refs, mode).unwrap()
}

fn selected_nodes(s: &GraphSession) -> Vec<Uuid> {
    let mut out: Vec<Uuid> = s
        .selection()
        .unwrap()
        .into_iter()
        .filter_map(|r| match r {
            ElementRef::Node(id) => Some(id),
            _ => None,
        })
        .collect();
    out.sort();
    out
}

fn bits(values: &[f64]) -> Vec<u64> {
    values.iter().map(|v| v.to_bits()).collect()
}

// -- ingress parity with the host render path ---------------------------------

/// What `_graph.layout_render` does after layout: `graph_build_render_with_membership`
/// with host-sized buffers.
struct HostRender {
    tier: LodTier,
    edges_kept: u64,
    x: Vec<f64>,
    y: Vec<f64>,
    member_of: Vec<u64>,
    edge_source: Vec<u64>,
    edge_target: Vec<u64>,
    offsets: Vec<u64>,
    members: Vec<u64>,
}

fn host_render(
    x: &[f64],
    y: &[f64],
    sources: &[u64],
    targets: &[u64],
    budgets: (u64, u64),
    viewport: Option<Viewport>,
) -> HostRender {
    let n = x.len();
    let (node_budget, edge_budget) = (budgets.0.max(1), budgets.1.max(1));
    let cap = n.min(node_budget as usize);
    let (mut out_x, mut out_y) = (vec![0.0; cap], vec![0.0; cap]);
    let mut member_of = vec![0u64; n];
    let (mut es, mut et) = (
        vec![0u64; edge_budget as usize],
        vec![0u64; edge_budget as usize],
    );
    let (mut nn, mut ne) = (0u64, 0u64);
    let mut offsets = vec![0u64; (edge_budget as usize).min(sources.len()) + 1];
    let mut members = vec![0u64; sources.len().max(1)];
    let decision = build_render(
        n as u64,
        x,
        y,
        sources,
        targets,
        node_budget,
        edge_budget,
        viewport,
        &mut out_x,
        &mut out_y,
        &mut member_of,
        &mut es,
        &mut et,
        &mut nn,
        &mut ne,
        Some((&mut offsets, &mut members)),
    )
    .unwrap();
    out_x.truncate(nn as usize);
    out_y.truncate(nn as usize);
    es.truncate(ne as usize);
    et.truncate(ne as usize);
    offsets.truncate(ne as usize + 1);
    members.truncate(offsets[ne as usize] as usize);
    HostRender {
        tier: decision.tier,
        edges_kept: decision.edges_kept,
        x: out_x,
        y: out_y,
        member_of,
        edge_source: es,
        edge_target: et,
        offsets,
        members,
    }
}

fn assert_same_render(out: &RenderOutput, host: &HostRender) {
    assert_eq!(out.tier, host.tier);
    assert_eq!(out.edges_kept, host.edges_kept);
    assert_eq!(bits(&out.node_x), bits(&host.x));
    assert_eq!(bits(&out.node_y), bits(&host.y));
    assert_eq!(out.member_of, host.member_of);
    assert_eq!(out.edge_source, host.edge_source);
    assert_eq!(out.edge_target, host.edge_target);
    assert_eq!(out.edge_member_offsets, host.offsets);
    assert_eq!(out.edge_members, host.members);
}

fn endpoints(document: &[u8]) -> (Vec<u64>, Vec<u64>) {
    let doc = ComposedDocument::decode(document).unwrap();
    (
        doc.u64s("edge.source").unwrap(),
        doc.u64s("edge.target").unwrap(),
    )
}

fn hierarchy_document() -> Vec<u8> {
    composed(
        &hierarchy_tables("hierarchy_dag_nodes"),
        &[layer("dag_longest_path")],
    )
}

#[test]
fn authored_positions_publish_exactly_what_the_host_render_path_builds() {
    let document = hierarchy_document();
    let (sources, targets) = endpoints(&document);
    let (x, y) = ([0.0, 1.5, 3.25, -2.0], [0.0, 2.0, -1.0, 4.5]);
    for budgets in [(200_000, 500_000), (2, 1), (4, 1)] {
        let mut s = loaded(
            &document,
            SessionLoad {
                budgets: Some(budgets),
                ..at(&x, &y)
            },
        );
        let out = s.render(None).unwrap().clone();
        assert_same_render(
            &out,
            &host_render(&x, &y, &sources, &targets, budgets, None),
        );
        if budgets == (200_000, 500_000) {
            assert_eq!(out.tier, LodTier::Direct, "the direct tier is the contract");
        }
    }
    // A camera is a viewport: the same cull the host passes as `viewport`.
    let mut s = loaded(&document, at(&x, &y));
    let camera = Camera {
        scale_x: 1.0,
        scale_y: 1.0,
        offset_x: 0.0,
        offset_y: 5.0,
        viewport_width: 2.0,
        viewport_height: 10.0,
        dpr: 1.0,
    };
    let out = s.render(Some(camera)).unwrap().clone();
    let viewport = Viewport {
        x0: 0.0,
        y0: -5.0,
        x1: 2.0,
        y1: 5.0,
    };
    assert_same_render(
        &out,
        &host_render(
            &x,
            &y,
            &sources,
            &targets,
            (200_000, 500_000),
            Some(viewport),
        ),
    );
    assert!(
        out.member_of.contains(&NOT_RENDERED),
        "something was culled"
    );
}

#[test]
fn unauthored_positions_are_cose_from_the_seed_like_the_host_path() {
    let document = hierarchy_document();
    let (sources, targets) = endpoints(&document);
    let parents = [COSE_NO_PARENT, 0, 1, COSE_NO_PARENT];
    let handle = force_create_cose(
        4,
        &sources,
        &targets,
        None,
        None,
        42,
        CoseOptions::default(),
        &[],
        &parents,
    )
    .unwrap();
    let (mut x, mut y) = ([0.0; 4], [0.0; 4]);
    force_tick(handle, INITIAL_LAYOUT_STEPS, &mut x, &mut y).unwrap();
    force_destroy(handle);

    let mut s = loaded(
        &document,
        SessionLoad {
            seed: 42,
            ..SessionLoad::default()
        },
    );
    let out = s.render(None).unwrap().clone();
    assert_same_render(
        &out,
        &host_render(&x, &y, &sources, &targets, (200_000, 500_000), None),
    );
    let (sx, sy) = s.positions().unwrap();
    assert_eq!((bits(sx), bits(sy)), (bits(&x), bits(&y)));
    // A different seed lays out differently (the seed is the only input; the
    // engine forces its low bit, so 42 and 43 are the same stream).
    let mut other = loaded(
        &document,
        SessionLoad {
            seed: 44,
            ..SessionLoad::default()
        },
    );
    other.render(None).unwrap();
    assert_ne!(bits(other.positions().unwrap().0), bits(&x));
}

// -- F2: collapse before LOD ----------------------------------------------------

/// A(0) is a compound over B(1) and C(2); D(3), E(4) are outside.
/// e0 B→D, e1 C→D, e2 B→C (internal to A), e3 D→E.
fn compound_doc() -> Vec<u8> {
    handmade_ends(
        COMPOSITION_VERSION,
        &node_ids(5),
        &persisted(4),
        &[],
        Some((&[NONE, 0, 0, NONE, NONE], &[0, 1, 1, 0, 0])),
        Some(&[(1, 3), (2, 3), (1, 2), (3, 4)]),
    )
}

fn compound_load(collapsed: bool) -> SessionLoad {
    SessionLoad {
        collapsed: Some(vec![u8::from(collapsed), 0, 0, 0, 0]),
        ..at(&[0.0, 1.0, 2.0, 10.0, 20.0], &[0.0; 5])
    }
}

#[test]
fn a_collapsed_compound_hides_members_and_reroutes_edges_to_its_representative() {
    let mut s = loaded(&compound_doc(), compound_load(true));
    let out = s.render(None).unwrap().clone();
    assert_eq!(out.node_count(), 3, "A, D, E");
    assert_eq!(
        out.member_of,
        [0, 0, 0, 1, 2],
        "B and C ride A's render node"
    );
    assert_eq!(out.edge_source, [0, 0, 1], "B→D and C→D reroute to A→D");
    assert_eq!(out.edge_target, [1, 1, 2]);
    assert_eq!(out.edge_member_offsets, [0, 1, 2, 3]);
    assert_eq!(out.edge_members, [0, 1, 3]);
    assert_eq!(
        out.edge_render,
        [0, 1, NOT_RENDERED, 2],
        "B→C became internal and is dropped"
    );
    assert_eq!(out.members_of_node(0), [0, 1, 2]);

    let mut open = loaded(&compound_doc(), compound_load(false));
    let out = open.render(None).unwrap().clone();
    assert_eq!(out.member_of, [0, 1, 2, 3, 4]);
    assert_eq!(out.edge_render, [0, 1, 2, 3]);
}

#[test]
fn collapse_runs_before_culling_so_an_off_screen_group_does_not_leak_its_child() {
    // A far outside the viewport, its child B on-screen. D, E far away too.
    let load = |collapsed: bool| SessionLoad {
        collapsed: Some(vec![u8::from(collapsed), 0, 0, 0, 0]),
        ..at(
            &[100.0, 0.0, 100.0, 200.0, 300.0],
            &[100.0, 0.0, 100.0, 200.0, 300.0],
        )
    };
    let camera = Camera {
        scale_x: 1.0,
        scale_y: 1.0,
        offset_x: 5.0,
        offset_y: 5.0,
        viewport_width: 10.0,
        viewport_height: 10.0,
        dpr: 1.0,
    };
    let mut collapsed = loaded(&compound_doc(), load(true));
    let out = collapsed.render(Some(camera)).unwrap();
    assert_eq!(
        out.node_count(),
        0,
        "the representative is culled, not the child"
    );
    assert_eq!(out.member_of[1], NOT_RENDERED);

    let mut expanded = loaded(&compound_doc(), load(false));
    let out = expanded.render(Some(camera)).unwrap();
    assert_eq!((out.node_count(), out.member_of[1]), (1, 0));
}

#[test]
fn aggregate_centroids_exclude_hidden_descendants() {
    // B (child of A) sits far away; with A collapsed it must not pull a centroid.
    let doc = handmade_ends(
        COMPOSITION_VERSION,
        &node_ids(6),
        &[],
        &[],
        Some((&[NONE, 0, NONE, NONE, NONE, NONE], &[0, 1, 0, 0, 0, 0])),
        Some(&[]),
    );
    let render = |collapsed: u8| {
        let mut s = loaded(
            &doc,
            SessionLoad {
                collapsed: Some(vec![collapsed, 0, 0, 0, 0, 0]),
                budgets: Some((2, 10)),
                ..at(
                    &[0.0, 1000.0, 1.0, 2.0, 3.0, 4.0],
                    &[0.0, 1000.0, 1.0, 2.0, 3.0, 4.0],
                )
            },
        );
        s.render(None).unwrap().clone()
    };
    let hidden = render(1);
    assert_eq!(hidden.tier, LodTier::Aggregate);
    assert!(
        hidden.node_x.iter().all(|&x| x < 500.0),
        "{:?}",
        hidden.node_x
    );
    let shown = render(0);
    assert!(
        shown.node_x.iter().any(|&x| x > 100.0),
        "{:?}",
        shown.node_x
    );
}

// -- selection, focus, hover, emphasis -----------------------------------------

#[test]
fn selection_modes_and_clear_drive_the_published_state_planes() {
    let doc = handmade_ends(COMPOSITION_VERSION, &node_ids(3), &[], &[], None, Some(&[]));
    let mut s = loaded(&doc, at(&[0.0, 1.0, 2.0], &[0.0; 3]));
    s.render(None).unwrap();
    let states = |s: &mut GraphSession| s.render(None).unwrap().visual_states.clone();

    select(&mut s, 1, &[1], SelectMode::Replace);
    assert_eq!(states(&mut s), [STATE_SELECTED, STATE_NORMAL, STATE_NORMAL]);
    select(&mut s, 2, &[2], SelectMode::Add);
    assert_eq!(
        states(&mut s),
        [STATE_SELECTED, STATE_SELECTED, STATE_NORMAL]
    );
    let out = select(&mut s, 3, &[1, 3], SelectMode::Toggle);
    assert_eq!(out.changed.len(), 2);
    assert_eq!(selected_nodes(&s), [id(2), id(3)]);
    select(&mut s, 4, &[3], SelectMode::Replace);
    assert_eq!(selected_nodes(&s), [id(3)]);

    s.focus_ref(header(&s, 5), Some(&ElementRef::Node(id(2))))
        .unwrap();
    let cleared = s.clear(header(&s, 6)).unwrap();
    assert!(cleared.state_changed);
    assert_eq!(states(&mut s), [STATE_NORMAL; 3]);
    assert_eq!(
        s.focus().unwrap(),
        Some(ElementRef::Node(id(2))),
        "Clear keeps focus"
    );
}

#[test]
fn hover_marks_the_target_and_its_neighbors_without_a_revision_bump() {
    // 0→1, 1→2, 3 isolated.
    let doc = handmade_ends(
        COMPOSITION_VERSION,
        &node_ids(4),
        &persisted(2),
        &[],
        None,
        Some(&[(0, 1), (1, 2)]),
    );
    let mut s = loaded(&doc, at(&[0.0, 1.0, 2.0, 3.0], &[0.0; 4]));
    let before = s.render(None).unwrap().revision;
    let out = s
        .hover(header(&s, 1), Some(&ElementRef::Node(id(2))))
        .unwrap();
    assert!(out.state_changed);
    assert_eq!(s.render_revision(), before, "hover is style, not structure");
    assert_eq!(
        s.render(None).unwrap().visual_states,
        [STATE_NEIGHBOR, STATE_HOVERED, STATE_NEIGHBOR, STATE_NORMAL]
    );
    let again = s
        .hover(header(&s, 2), Some(&ElementRef::Node(id(2))))
        .unwrap();
    assert!(!again.state_changed);
    s.hover(header(&s, 3), None).unwrap();
    assert_eq!(s.render(None).unwrap().visual_states, [STATE_NORMAL; 4]);
}

#[test]
fn emphasis_is_an_independent_plane_that_follows_hidden_members_to_their_representative() {
    let mut s = loaded(&compound_doc(), compound_load(true));
    s.render(None).unwrap();
    // Focus the hidden child B and highlight the path B—C (edge e2).
    s.focus_ref(header(&s, 1), Some(&ElementRef::Node(id(2))))
        .unwrap();
    s.set_highlight(
        header(&s, 2),
        HighlightPlane::Path,
        &[ElementRef::Node(id(2)), ElementRef::Node(id(3))],
        SelectMode::Replace,
    )
    .unwrap();
    s.set_highlight(
        header(&s, 3),
        HighlightPlane::External,
        &[ElementRef::Node(id(4))],
        SelectMode::Replace,
    )
    .unwrap();
    let out = s.render(None).unwrap().clone();
    // bit0 FOCUSED, bit1 PATH, bit2 COMMUNITY, bit3 EXTERNAL.
    assert_eq!(out.emphasis, [0b0011, 0b1000, 0]);
    assert_eq!(
        out.visual_states, [STATE_NORMAL; 3],
        "emphasis never competes in visual-state precedence"
    );
    assert_eq!(
        out.edge_emphasis,
        [0, 0, 0],
        "the internal edge is not drawn"
    );

    // Expanded: the planes land on the members themselves, edge e2 included.
    let mut open = loaded(&compound_doc(), compound_load(false));
    open.render(None).unwrap();
    open.set_highlight(
        header(&open, 1),
        HighlightPlane::Path,
        &[ElementRef::Node(id(2)), ElementRef::Node(id(3))],
        SelectMode::Replace,
    )
    .unwrap();
    open.set_highlight(
        header(&open, 2),
        HighlightPlane::Community,
        &[ElementRef::Node(id(4)), ElementRef::Node(id(5))],
        SelectMode::Replace,
    )
    .unwrap();
    let out = open.render(None).unwrap().clone();
    assert_eq!(out.emphasis, [0, 0b0010, 0b0010, 0b0100, 0b0100]);
    assert_eq!(
        out.edge_emphasis,
        [0, 0, 0b0010, 0b0100],
        "path edge and induced edge"
    );
    assert_eq!(FLAG_COMMUNITY >> 7, 0b100);
}

#[test]
fn a_path_highlight_must_follow_composed_edges_and_changes_nothing_otherwise() {
    let mut s = loaded(&compound_doc(), compound_load(false));
    s.render(None).unwrap();
    let before = s.render_revision();
    // B and E share no edge.
    assert_eq!(
        s.set_highlight(
            header(&s, 1),
            HighlightPlane::Path,
            &[ElementRef::Node(id(2)), ElementRef::Node(id(5))],
            SelectMode::Replace,
        ),
        Err(InteractionStatus::Invalid)
    );
    assert!(s.render(None).unwrap().emphasis.iter().all(|&e| e == 0));
    assert_eq!(s.render_revision(), before);
    // The failed op did not consume its op_seq.
    s.set_highlight(
        header(&s, 1),
        HighlightPlane::Path,
        &[ElementRef::Node(id(4)), ElementRef::Node(id(2))],
        SelectMode::Replace,
    )
    .unwrap();
}

// -- keyboard walks ---------------------------------------------------------------

/// A(0)→B(1), A→C(2), D(3)→A, B→C.
fn ring_doc() -> Vec<u8> {
    handmade_ends(
        COMPOSITION_VERSION,
        &node_ids(4),
        &persisted(4),
        &[],
        None,
        Some(&[(0, 1), (0, 2), (3, 0), (1, 2)]),
    )
}

fn ring_session() -> GraphSession {
    let mut s = loaded(&ring_doc(), at(&[0.0, 1.0, 2.0, 3.0], &[0.0; 4]));
    s.render(None).unwrap();
    s
}

fn focus_of(s: &GraphSession) -> ElementRef {
    s.focus().unwrap().unwrap()
}

#[test]
fn focus_step_walks_drawn_nodes_and_wraps() {
    let mut s = ring_session();
    let (node, edge) = (|n| ElementRef::Node(id(n)), |e| ElementRef::Edge(id(e)));
    s.focus_step(header(&s, 1), 1).unwrap();
    assert_eq!(
        focus_of(&s),
        node(1),
        "nothing focused: +1 enters at the first"
    );
    for (seq, want) in [(2, 2), (3, 3), (4, 4), (5, 1)] {
        s.focus_step(header(&s, seq), 1).unwrap();
        assert_eq!(focus_of(&s), node(want));
    }
    s.focus_step(header(&s, 6), -1).unwrap();
    assert_eq!(focus_of(&s), node(4), "-1 wraps to the last");
    // From an edge, the walk continues from the edge's source.
    s.focus_ref(header(&s, 7), Some(&edge(12))).unwrap();
    s.focus_step(header(&s, 8), 1).unwrap();
    assert_eq!(focus_of(&s), node(2));
    assert_eq!(
        s.focus_step(header(&s, 9), 2),
        Err(InteractionStatus::Invalid)
    );

    let mut fresh = ring_session();
    fresh.focus_step(header(&fresh, 1), -1).unwrap();
    assert_eq!(
        focus_of(&fresh),
        node(4),
        "nothing focused: -1 enters at the last"
    );
}

#[test]
fn the_focus_ring_walks_node_out_edges_in_edges_then_neighbors_and_stays_anchored() {
    let mut s = ring_session();
    let (node, edge) = (|n| ElementRef::Node(id(n)), |e| ElementRef::Edge(id(e)));
    s.focus_ref(header(&s, 1), Some(&node(1))).unwrap();
    // A's ring: A, out A→B (e11), A→C (e12), in D→A (e13), neighbors B, C, D.
    let want = [
        edge(11),
        edge(12),
        edge(13),
        node(2),
        node(3),
        node(4),
        node(1),
    ];
    for (i, want) in want.iter().enumerate() {
        s.focus_ring(header(&s, 2 + i as u64), 1).unwrap();
        assert_eq!(&focus_of(&s), want, "stop {i}");
    }
    s.focus_ring(header(&s, 20), -1).unwrap();
    assert_eq!(focus_of(&s), node(4), "-1 walks back, wrapping");

    // A fresh ring entered from an edge anchors on that edge's source node.
    s.focus_ref(header(&s, 21), Some(&edge(11))).unwrap();
    s.focus_ring(header(&s, 22), 1).unwrap();
    assert_eq!(focus_of(&s), edge(12));
    // Any other focus move drops the anchor: B's ring is out e14, in e11.
    s.focus_ref(header(&s, 23), Some(&node(2))).unwrap();
    s.focus_ring(header(&s, 24), 1).unwrap();
    assert_eq!(focus_of(&s), edge(14));
}

#[test]
fn walks_need_the_current_publication() {
    let mut s = loaded(&ring_doc(), at(&[0.0, 1.0, 2.0, 3.0], &[0.0; 4]));
    assert_eq!(
        s.focus_step(header(&s, 1), 1),
        Err(InteractionStatus::Stale)
    );
    s.render(None).unwrap();
    s.pin(header(&s, 1), &ElementRef::Node(id(1)), true)
        .unwrap();
    assert_eq!(
        s.focus_ring(header(&s, 2), 1),
        Err(InteractionStatus::Stale),
        "the pin advanced the revision; the host must repaint first"
    );
    assert!(s.focus().unwrap().is_none());
    s.render(None).unwrap();
    s.focus_ring(header(&s, 2), 1).unwrap();
}

// -- stamps -----------------------------------------------------------------------

#[test]
fn a_stale_revision_is_rejected_with_no_change_and_no_op_seq_consumed() {
    let mut s = ring_session();
    let old = header(&s, 2);
    s.pin(header(&s, 1), &ElementRef::Node(id(1)), true)
        .unwrap();
    assert_ne!(old.stamp.render_revision, s.render_revision());
    let before = (
        s.selection().unwrap(),
        s.pinned().unwrap(),
        s.render_revision(),
    );
    for result in [
        s.select_refs(old, &[ElementRef::Node(id(2))], SelectMode::Replace),
        s.clear(old),
        s.hover(old, Some(&ElementRef::Node(id(2)))),
        s.pin(old, &ElementRef::Node(id(2)), true),
        s.move_node(
            old,
            &ElementRef::Node(id(2)),
            (1.0, 1.0),
            MoveSpace::Data,
            MoveCommit::Preview,
        ),
        s.relayout_step(old, 1),
        s.toggle_disclosure(old, &ElementRef::Node(id(2)), DisclosureAction::Toggle),
    ] {
        assert_eq!(result, Err(InteractionStatus::Stale));
    }
    assert_eq!(
        (
            s.selection().unwrap(),
            s.pinned().unwrap(),
            s.render_revision()
        ),
        before
    );
    assert_eq!(s.positions().unwrap().0[1], 1.0, "nothing moved");

    // An aggregate ref names its render: the old revision no longer resolves.
    let stale = ElementRef::Aggregate(AggregateRef {
        render_revision: old.stamp.render_revision,
        index: 0,
    });
    s.render(None).unwrap();
    assert_eq!(
        s.select_refs(header(&s, 2), &[stale], SelectMode::Replace),
        Err(InteractionStatus::Stale)
    );
    let current = ElementRef::Aggregate(AggregateRef {
        render_revision: s.published().unwrap().revision,
        index: 0,
    });
    s.select_refs(header(&s, 2), &[current], SelectMode::Replace)
        .unwrap();
    assert_eq!(selected_nodes(&s), [id(1)]);
}

// -- disclosure -------------------------------------------------------------------

#[test]
fn disclosure_bumps_the_revision_and_propagates_between_members_and_representative() {
    let mut s = loaded(&compound_doc(), compound_load(false));
    s.render(None).unwrap();
    let a = ElementRef::Node(id(1));
    select(&mut s, 1, &[2], SelectMode::Replace); // B

    let r0 = s.render_revision();
    let out = s
        .toggle_disclosure(header(&s, 2), &a, DisclosureAction::Collapse)
        .unwrap();
    assert!(out.state_changed);
    assert_eq!(out.render_revision, r0 + 1);
    assert!(out.disclosure.as_ref().unwrap().collapsed);
    assert_eq!(s.collapsed(), [1, 0, 0, 0, 0]);
    // Member → representative: B is hidden but selected; A shows it.
    let render = s.render(None).unwrap().clone();
    assert_eq!(render.visual_states[0], STATE_SELECTED);
    assert_eq!(
        selected_nodes(&s),
        [id(2)],
        "hidden members keep their state"
    );

    // Representative → members: selecting A's render node selects all three.
    let agg = ElementRef::Aggregate(AggregateRef {
        render_revision: render.revision,
        index: 0,
    });
    s.select_refs(
        header(&s, 3),
        std::slice::from_ref(&agg),
        SelectMode::Replace,
    )
    .unwrap();
    assert_eq!(selected_nodes(&s), [id(1), id(2), id(3)]);

    // Expand: back to members, the selection intact.
    let out = s
        .toggle_disclosure(header(&s, 4), &a, DisclosureAction::Expand)
        .unwrap();
    assert_eq!(out.render_revision, r0 + 2);
    let render = s.render(None).unwrap().clone();
    assert_eq!(
        render.visual_states,
        [
            STATE_SELECTED,
            STATE_SELECTED,
            STATE_SELECTED,
            STATE_NORMAL,
            STATE_NORMAL
        ]
    );

    // Toggle is expand/collapse; a no-op neither bumps nor reports a change.
    let before = s.render_revision();
    let noop = s
        .toggle_disclosure(header(&s, 5), &a, DisclosureAction::Expand)
        .unwrap();
    assert_eq!((noop.state_changed, s.render_revision()), (false, before));
    s.toggle_disclosure(header(&s, 6), &a, DisclosureAction::Toggle)
        .unwrap();
    assert_eq!(s.collapsed()[0], 1);
    assert_eq!(s.render_revision(), before + 1);

    // A replay of the same op_seq is served from the retained outcome.
    let replay = s
        .toggle_disclosure(header(&s, 6), &a, DisclosureAction::Toggle)
        .unwrap();
    assert_eq!(replay.render_revision, before + 1);
    assert_eq!(s.collapsed()[0], 1, "not toggled twice");
}

#[test]
fn disclosure_rejects_non_compounds_aggregates_and_leaves_state_alone() {
    let mut s = loaded(&compound_doc(), compound_load(false));
    let render = s.render(None).unwrap().clone();
    let before = (s.render_revision(), s.collapsed().to_vec());
    // D is not a compound.
    assert_eq!(
        s.toggle_disclosure(
            header(&s, 1),
            &ElementRef::Node(id(4)),
            DisclosureAction::Collapse
        ),
        Err(InteractionStatus::Invalid)
    );
    // Edges and render aggregates take no action.
    assert_eq!(
        s.toggle_disclosure(
            header(&s, 1),
            &ElementRef::Edge(id(11)),
            DisclosureAction::Toggle
        ),
        Err(InteractionStatus::Invalid)
    );
    let agg = ElementRef::Aggregate(AggregateRef {
        render_revision: render.revision,
        index: 0,
    });
    assert_eq!(
        s.toggle_disclosure(header(&s, 1), &agg, DisclosureAction::Toggle),
        Err(InteractionStatus::Invalid)
    );
    assert_eq!((s.render_revision(), s.collapsed().to_vec()), before);
}

fn compound_chain(n: u32) -> GraphSession {
    let mut parents = vec![NONE; n as usize];
    let mut valid = vec![0u8; n as usize];
    parents[1] = 0;
    valid[1] = 1;
    let doc = handmade_ends(
        COMPOSITION_VERSION,
        &node_ids(n),
        &[],
        &[],
        Some((&parents, &valid)),
        Some(&[]),
    );
    let xs: Vec<f64> = (0..n).map(f64::from).collect();
    loaded(&doc, at(&xs, &xs))
}

#[test]
fn compound_disclosure_is_bounded_at_1024_source_nodes() {
    let mut s = compound_chain(1_024);
    s.render(None).unwrap();
    let a = ElementRef::Node(id(1));
    s.toggle_disclosure(header(&s, 1), &a, DisclosureAction::Collapse)
        .unwrap();
    assert_eq!(s.collapsed()[0], 1);

    let mut big = compound_chain(1_025);
    big.render(None).unwrap();
    let before = (big.render_revision(), big.collapsed().to_vec());
    assert_eq!(
        big.toggle_disclosure(header(&big, 1), &a, DisclosureAction::Collapse),
        Err(InteractionStatus::CompoundTooLarge)
    );
    assert_eq!((big.render_revision(), big.collapsed().to_vec()), before);
    // The failed op consumed nothing.
    big.pin(header(&big, 1), &a, true).unwrap();
}

// -- pin / move / relayout --------------------------------------------------------

fn line_session() -> GraphSession {
    let mut s = loaded(&standard_doc(), at(&[0.0, 10.0, 20.0], &[0.0; 3]));
    s.render(None).unwrap();
    s
}

fn pos(s: &GraphSession, node: usize) -> (u64, u64) {
    let (x, y) = s.positions().unwrap();
    (x[node].to_bits(), y[node].to_bits())
}

#[test]
fn pin_bumps_the_revision_records_the_position_and_is_idempotent() {
    let mut s = line_session();
    let n2 = ElementRef::Node(id(2));
    let r0 = s.render_revision();
    let out = s.pin(header(&s, 1), &n2, true).unwrap();
    assert_eq!(out.render_revision, r0 + 1);
    assert_eq!(
        out.positions,
        [NodePosition {
            node: n2.clone(),
            x: 10.0,
            y: 0.0,
            pinned: true
        }]
    );
    assert_eq!(s.pinned().unwrap(), [id(2)]);
    s.render(None).unwrap();
    assert_eq!(
        s.render(None).unwrap().visual_states,
        [STATE_NORMAL, STATE_PINNED, STATE_NORMAL]
    );
    let again = s.pin(header(&s, 2), &n2, true).unwrap();
    assert!(again.positions.is_empty() && !again.state_changed);
    assert_eq!(s.render_revision(), r0 + 1, "no change, no bump");
    s.pin(header(&s, 3), &n2, false).unwrap();
    assert!(s.pinned().unwrap().is_empty());
    assert_eq!(s.render_revision(), r0 + 2);
    // Only nodes pin.
    assert_eq!(
        s.pin(header(&s, 4), &ElementRef::Edge(id(11)), true),
        Err(InteractionStatus::Invalid)
    );
}

#[test]
fn move_previews_commit_and_cancel_bit_exact() {
    let mut s = line_session();
    let n2 = ElementRef::Node(id(2));
    let start = pos(&s, 1);
    let r0 = s.render_revision();
    for (seq, expect) in [(1, (11.5, 2.5)), (2, (13.0, 5.0))] {
        let out = s
            .move_node(
                header(&s, seq),
                &n2,
                (1.5, 2.5),
                MoveSpace::Data,
                MoveCommit::Preview,
            )
            .unwrap();
        assert!(out.positions.is_empty(), "previews are not persisted");
        assert_eq!(
            (f64::from_bits(pos(&s, 1).0), f64::from_bits(pos(&s, 1).1)),
            expect
        );
    }
    assert_eq!(
        s.render_revision(),
        r0 + 2,
        "each preview bumps the revision"
    );
    assert!(s.pinned().unwrap().is_empty(), "a preview does not pin");

    // Another node cannot start moving while one is in flight.
    assert_eq!(
        s.move_node(
            header(&s, 3),
            &ElementRef::Node(id(1)),
            (1.0, 0.0),
            MoveSpace::Data,
            MoveCommit::Preview
        ),
        Err(InteractionStatus::Invalid)
    );
    s.move_node(
        header(&s, 3),
        &n2,
        (0.0, 0.0),
        MoveSpace::Data,
        MoveCommit::Cancel,
    )
    .unwrap();
    assert_eq!(pos(&s, 1), start, "cancel restores the origin bit for bit");
    assert_eq!(
        s.move_node(
            header(&s, 4),
            &n2,
            (0.0, 0.0),
            MoveSpace::Data,
            MoveCommit::Cancel
        ),
        Err(InteractionStatus::Invalid),
        "nothing to cancel"
    );

    s.move_node(
        header(&s, 4),
        &n2,
        (1.0, 1.0),
        MoveSpace::Data,
        MoveCommit::Preview,
    )
    .unwrap();
    let out = s
        .move_node(
            header(&s, 5),
            &n2,
            (1.0, 1.0),
            MoveSpace::Data,
            MoveCommit::Commit,
        )
        .unwrap();
    assert_eq!(
        out.positions,
        [NodePosition {
            node: n2.clone(),
            x: 12.0,
            y: 2.0,
            pinned: true
        }]
    );
    assert_eq!(s.pinned().unwrap(), [id(2)], "commit pins");
    // The committed move ended: the next move starts a new origin.
    s.move_node(
        header(&s, 6),
        &n2,
        (5.0, 0.0),
        MoveSpace::Data,
        MoveCommit::Preview,
    )
    .unwrap();
    s.move_node(
        header(&s, 7),
        &n2,
        (0.0, 0.0),
        MoveSpace::Data,
        MoveCommit::Cancel,
    )
    .unwrap();
    assert_eq!(f64::from_bits(pos(&s, 1).0), 12.0);
}

#[test]
fn screen_deltas_convert_through_the_rendered_camera_and_bad_deltas_change_nothing() {
    let mut s = loaded(&standard_doc(), at(&[0.0, 10.0, 20.0], &[0.0; 3]));
    let n2 = ElementRef::Node(id(2));
    assert_eq!(
        s.move_node(
            header(&s, 1),
            &n2,
            (4.0, 8.0),
            MoveSpace::ScreenDelta,
            MoveCommit::Preview
        ),
        Err(InteractionStatus::Invalid),
        "no camera has been rendered"
    );
    s.render(Some(Camera {
        scale_x: 2.0,
        scale_y: -4.0,
        offset_x: 0.0,
        offset_y: 100.0,
        viewport_width: 200.0,
        viewport_height: 200.0,
        dpr: 1.0,
    }))
    .unwrap();
    s.move_node(
        header(&s, 1),
        &n2,
        (4.0, 8.0),
        MoveSpace::ScreenDelta,
        MoveCommit::Preview,
    )
    .unwrap();
    let (x, y) = s.positions().unwrap();
    assert_eq!((x[1], y[1]), (12.0, -2.0));

    let before = (pos(&s, 1), s.render_revision());
    for delta in [
        (f64::NAN, 0.0),
        (0.0, f64::INFINITY),
        (f64::NEG_INFINITY, 1.0),
    ] {
        assert_eq!(
            s.move_node(
                header(&s, 2),
                &n2,
                delta,
                MoveSpace::Data,
                MoveCommit::Preview
            ),
            Err(InteractionStatus::Invalid)
        );
        assert_eq!((pos(&s, 1), s.render_revision()), before);
    }
    // A finite delta whose sum overflows is rejected too, leaving the node at
    // its last valid position.
    s.move_node(
        header(&s, 2),
        &n2,
        (f64::MAX, 0.0),
        MoveSpace::Data,
        MoveCommit::Preview,
    )
    .unwrap();
    let last_valid = pos(&s, 1);
    assert_eq!(
        s.move_node(
            header(&s, 3),
            &n2,
            (f64::MAX, 0.0),
            MoveSpace::Data,
            MoveCommit::Preview
        ),
        Err(InteractionStatus::Invalid)
    );
    assert_eq!(pos(&s, 1), last_valid);
    let (x, y) = s.positions().unwrap();
    assert!(x.iter().chain(y).all(|v| v.is_finite()));
}

#[test]
fn relayout_holds_pins_bit_exact_over_64_steps_with_parents() {
    let document = hierarchy_document();
    let (x, y) = ([0.0, 1.5, 3.25, -2.0], [0.0, 2.0, -1.0, 4.5]);
    let mut s = loaded(
        &document,
        SessionLoad {
            pinned: Some(vec![1, 0, 0, 1]),
            ..at(&x, &y)
        },
    );
    s.render(None).unwrap();
    let r0 = s.render_revision();
    let out = s.relayout_step(header(&s, 1), 64).unwrap();
    assert_eq!(out.render_revision, r0 + 1);
    let first = out.relayout.unwrap();
    assert!(first.alpha.is_finite() && first.alpha > 0.0);
    let (px, py) = s.positions().unwrap();
    for pinned in [0, 3] {
        assert_eq!(
            (px[pinned].to_bits(), py[pinned].to_bits()),
            (x[pinned].to_bits(), y[pinned].to_bits()),
            "node {pinned} is pinned"
        );
    }
    assert!(
        (1..3).any(|i| px[i].to_bits() != x[i].to_bits() || py[i].to_bits() != y[i].to_bits()),
        "unpinned nodes moved"
    );

    // The state continues: alpha only cools.
    let second = s
        .relayout_step(header(&s, 2), 64)
        .unwrap()
        .relayout
        .unwrap();
    assert!(second.alpha <= first.alpha);
    assert_eq!(second.done, second.alpha < RELAYOUT_SETTLED_ALPHA);

    // A pin change drops the relayout state: the new pin holds on the next step.
    let held = pos(&s, 1);
    let second_node = s.identity().node_ref(1);
    s.pin(header(&s, 3), &second_node, true).unwrap();
    s.relayout_step(header(&s, 4), 64).unwrap();
    assert_eq!(pos(&s, 1), held, "node 2 was pinned where it stood");
}

#[test]
fn relayout_is_bounded_and_rejects_without_changing_anything() {
    let mut s = line_session();
    let before = (pos(&s, 1), s.render_revision());
    for steps in [0, MAX_RELAYOUT_STEPS + 1] {
        assert_eq!(
            s.relayout_step(header(&s, 1), steps),
            Err(InteractionStatus::Invalid)
        );
    }
    assert_eq!((pos(&s, 1), s.render_revision()), before);

    // 64 steps over 70,000 nodes is 4.48M units of work: over the ceiling.
    let n = 70_000u32;
    let doc = handmade_ends(COMPOSITION_VERSION, &node_ids(n), &[], &[], None, Some(&[]));
    let xs: Vec<f64> = (0..n).map(f64::from).collect();
    let mut big = loaded(&doc, at(&xs, &xs));
    assert_eq!(
        big.relayout_step(header(&big, 1), 64),
        Err(InteractionStatus::Budget)
    );
    assert_eq!(big.render_revision(), 0);
    assert!(
        big.work() <= u64::from(n),
        "rejected after one linear visibility pass, before any force work"
    );
    assert!(64 * u64::from(n) > MAX_GRAPH_INTERACTION_WORK);
}

#[test]
fn positions_and_pins_round_trip_through_a_new_session_without_relayout() {
    let document = hierarchy_document();
    let (x, y) = ([0.0, 1.5, 3.25, -2.0], [0.0, 2.0, -1.0, 4.5]);
    let mut s = loaded(
        &document,
        SessionLoad {
            pinned: Some(vec![1, 0, 0, 0]),
            ..at(&x, &y)
        },
    );
    s.render(None).unwrap();
    s.relayout_step(header(&s, 1), 16).unwrap();
    let third = s.identity().node_ref(2);
    s.move_node(
        header(&s, 2),
        &third,
        (0.5, 0.25),
        MoveSpace::Data,
        MoveCommit::Commit,
    )
    .unwrap();

    let (px, py) = s
        .positions()
        .map(|(a, b)| (a.to_vec(), b.to_vec()))
        .unwrap();
    let pinned = s.pinned().unwrap();
    let plane: Vec<u8> = s
        .identity()
        .node_uuids()
        .iter()
        .map(|id| u8::from(pinned.contains(id)))
        .collect();
    assert_eq!(plane, [1, 0, 1, 0]);
    let mut restored = loaded(
        &document,
        SessionLoad {
            pinned: Some(plane),
            ..at(&px, &py)
        },
    );
    let a = s.render(None).unwrap().clone();
    let b = restored.render(None).unwrap().clone();
    assert_eq!(bits(&a.node_x), bits(&b.node_x));
    assert_eq!(bits(&a.node_y), bits(&b.node_y));
    assert_eq!(a.visual_states, b.visual_states);
    assert_eq!(restored.pinned().unwrap(), pinned);
}

// -- F4: temporal visibility under the bound state ---------------------------------

fn temporal_registry() -> Arc<Registry> {
    let valid = [1u8; 3];
    let col = |values: &[i64]| {
        TemporalColumn::from_utc_micros(values, &valid, "UTC", TemporalPrecision::Microsecond)
            .unwrap()
    };
    let (starts, ends) = (col(&[0, 0, 0]), col(&[100, 20, 100]));
    let nodes = [id(1), id(2), id(3)];
    let projection = GraphProjection::new(
        &nodes,
        &[id(11), id(12)],
        &[nodes[0], nodes[1]],
        &[nodes[1], nodes[2]],
        None,
        true,
    )
    .unwrap();
    let graph = TemporalGraph::bind(
        &projection,
        TemporalBindingInput {
            valid_from: Some(&starts),
            valid_to: Some(&ends),
            event_at: None,
        },
        TemporalBindingInput::default(),
    )
    .unwrap();
    Arc::new(Registry {
        graph: Mutex::new(Some(graph)),
    })
}

fn frame_at(registry: &Registry, revision: u64, cursor: i64) {
    let mut guard = registry.graph.lock().unwrap();
    let graph = guard.as_mut().unwrap();
    let budget = graph.required_budget().unwrap();
    graph
        .frame(revision, cursor, 0, 30, &CancelFlag::new(), budget)
        .unwrap();
}

#[test]
fn a_bound_session_neither_draws_nor_exposes_what_the_temporal_frame_hides() {
    let positions = || at(&[0.0, 10.0, 20.0], &[0.0; 3]);
    let registry = temporal_registry();
    let mut s = loaded(&standard_doc(), positions());
    let mut owned = loaded(&standard_doc(), positions());
    s.bind_temporal(registry.clone(), HANDLE).unwrap();
    select(&mut s, 1, &[2], SelectMode::Replace);
    let all = s.render(None).unwrap().clone();
    assert_eq!(
        all.edge_render,
        [0, 1, 2],
        "no frame yet: everything is visible"
    );

    // A new frame changes the revision: the host's old stamp is stale.
    frame_at(&registry, 1, 10);
    let seen = header(&s, 2);
    assert_eq!(s.clear(seen), Err(InteractionStatus::Stale));
    assert_eq!(selected_nodes(&s), [id(2)], "a stale op changed nothing");
    let visible = s.render(None).unwrap().clone();
    assert!(visible.revision > all.revision);
    assert_eq!(
        visible.visual_states,
        [STATE_NORMAL, STATE_SELECTED, STATE_NORMAL]
    );

    // Cursor 20 expires node 2 (valid_to is half-open).
    frame_at(&registry, 2, 20);
    let hidden = s.render(None).unwrap().clone();
    assert!(hidden.revision > visible.revision);
    assert_eq!(hidden.member_of, [0, NOT_RENDERED, 1]);
    assert_eq!(
        hidden.edge_render,
        [NOT_RENDERED, NOT_RENDERED, 0],
        "both edges incident to node 2 are gone; the derived edge 3→1 stays"
    );
    assert!(
        (0..hidden.node_count()).all(|r| !hidden.members_of_node(r).contains(&1)),
        "not reachable through any group"
    );
    assert_eq!(
        hidden.visual_states, [STATE_NORMAL; 2],
        "its selection is not drawn"
    );
    assert_eq!(
        selected_nodes(&s),
        [id(2)],
        "but its identity state is kept"
    );
    assert_eq!(
        s.select_refs(
            header(&s, 2),
            &[ElementRef::Aggregate(AggregateRef {
                render_revision: hidden.revision,
                index: 2
            })],
            SelectMode::Add
        ),
        Err(InteractionStatus::Invalid),
        "no render node stands for the hidden node"
    );

    // Re-entry restores the selection without remapping.
    frame_at(&registry, 3, 10);
    let back = s.render(None).unwrap().clone();
    assert_eq!(back.member_of, [0, 1, 2]);
    assert_eq!(
        back.visual_states,
        [STATE_NORMAL, STATE_SELECTED, STATE_NORMAL]
    );

    // An Owned session has no temporal visibility.
    assert_eq!(owned.render(None).unwrap().member_of, [0, 1, 2]);

    // Disposing the temporal graph unbinds every operation, render included.
    *registry.graph.lock().unwrap() = None;
    assert!(matches!(s.render(None), Err(InteractionStatus::Unbound)));
}

// -- identity ---------------------------------------------------------------------

#[test]
fn identity_round_trips_uuid_index_and_exact_result_rows() {
    let layers = [Some("aa"), Some("bb"), Some(""), None];
    let edges = [
        E::Persisted(id(11)),
        E::Overlay {
            layer: 0,
            path: 0,
            order: 0,
        },
        E::Overlay {
            layer: 1,
            path: 1,
            order: 0,
        },
        E::Pair { layer: 2, row: 5 },
        E::Pair { layer: 3, row: 5 },
    ];
    let doc = handmade_ends(
        COMPOSITION_VERSION,
        &node_ids(2),
        &edges,
        &layers,
        None,
        Some(&[(0, 1); 5]),
    );
    let mut s = loaded(&doc, at(&[0.0, 1.0], &[0.0; 2]));
    let render = s.render(None).unwrap().clone();
    let identity = s.identity();

    for node in 0..2 {
        let element = identity.node_ref(node);
        assert_eq!(element, ElementRef::Node(id(node as u32 + 1)));
        assert_eq!(identity.resolve(&element), Ok(ElementIndex::Node(node)));
        assert_eq!(identity.node_index(&id(node as u32 + 1)), Some(node));
    }
    assert_eq!(render.edge_count(), 5);
    let mut transports = Vec::new();
    for r in 0..render.edge_count() {
        let [edge] = render.members_of_edge(r) else {
            panic!("direct tier: one source edge per render edge")
        };
        let edge = *edge as usize;
        let local = identity.edge_ref(edge);
        let transport = identity.to_transport(&local).unwrap();
        assert_eq!(identity.resolve(&local), Ok(ElementIndex::Edge(edge)));
        assert_eq!(identity.resolve(&transport), Ok(ElementIndex::Edge(edge)));
        transports.push(transport);
    }
    // Pair edges: (layer, result id, row) with the exact string; "" is not absent.
    let pair = |layer, result: Option<&str>| {
        ElementRef::Derived(DerivedRef {
            result: ResultRef::Exact(result.map(Into::into)),
            layer,
            path: NONE_U64,
            order: 5,
        })
    };
    assert_eq!(
        identity.resolve(&pair(2, Some(""))),
        Ok(ElementIndex::Edge(3))
    );
    assert_eq!(identity.resolve(&pair(3, None)), Ok(ElementIndex::Edge(4)));
    for wrong in [
        pair(2, None),
        pair(3, Some("")),
        pair(2, Some("aa")),
        pair(3, Some("bb")),
    ] {
        assert_eq!(identity.resolve(&wrong), Err(ResolveError::Unresolved));
    }

    // Transported refs select the same edges; the render shows all five.
    s.select_refs(header(&s, 1), &transports, SelectMode::Replace)
        .unwrap();
    assert_eq!(s.selection().unwrap().len(), 5);
    assert_eq!(
        s.render(None).unwrap().edge_visual_states,
        [STATE_SELECTED; 5]
    );
}

// -- bounded work -----------------------------------------------------------------

/// Chain 1→2→…→n; `deep` makes it a parent chain too, with the root collapsed.
fn ladder_session(n: u32, deep: bool) -> GraphSession {
    let ends: Vec<(u64, u64)> = (0..u64::from(n) - 1).map(|i| (i, i + 1)).collect();
    let (parents, valid): (Vec<u32>, Vec<u8>) = (0..n)
        .map(|i| if deep && i > 0 { (i - 1, 1) } else { (NONE, 0) })
        .unzip();
    let doc = handmade_ends(
        COMPOSITION_VERSION,
        &node_ids(n),
        &persisted(n - 1),
        &[],
        Some((&parents, &valid)),
        Some(&ends),
    );
    let xs: Vec<f64> = (0..n).map(f64::from).collect();
    let mut collapsed = vec![0u8; n as usize];
    collapsed[0] = u8::from(deep);
    loaded(
        &doc,
        SessionLoad {
            collapsed: Some(collapsed),
            ..at(&xs, &xs)
        },
    )
}

fn exercise(s: &mut GraphSession) -> u64 {
    let mid = ElementRef::Node(id(s.identity().node_count() as u32 / 2));
    s.render(None).unwrap();
    s.hover(header(s, 1), Some(&mid)).unwrap();
    s.focus_step(header(s, 2), 1).unwrap();
    s.focus_ring(header(s, 3), 1).unwrap();
    let root = ElementRef::Aggregate(AggregateRef {
        render_revision: s.published().unwrap().revision,
        index: 0,
    });
    // A thousand repeats of one aggregate expand it once.
    let repeated = vec![root; 1_000];
    s.select_refs(header(s, 4), &repeated, SelectMode::Replace)
        .unwrap();
    s.render(None).unwrap();
    s.work()
}

#[test]
fn render_and_walks_stay_linear_across_a_size_ladder() {
    for deep in [false, true] {
        let mut previous = None;
        for n in [1_000u32, 2_000, 4_000, 8_000] {
            let mut s = ladder_session(n, deep);
            let work = exercise(&mut s);
            let size = 2 * u64::from(n);
            assert!(
                work <= 40 * size,
                "deep={deep} n={n}: {work} units is not O(n + e)"
            );
            if let Some(previous) = previous {
                assert!(
                    work <= previous * 5 / 2,
                    "deep={deep} n={n}: {work} vs {previous}: doubling the graph more than doubled the work"
                );
            }
            previous = Some(work);
        }
    }
}

#[test]
fn a_hundred_thousand_deep_parent_chain_renders_and_collapses_without_a_quadratic_walk() {
    let mut s = ladder_session(100_000, true);
    let render = s.render(None).unwrap();
    assert_eq!(
        render.node_count(),
        1,
        "everything hides under the collapsed root"
    );
    assert_eq!(render.members_of_node(0).len(), 100_000);
    assert_eq!(
        render.edge_count(),
        0,
        "every edge is internal to the group"
    );
    assert_eq!(STATE_AGGREGATE, 1);
}

// -- review round 1: temporal masking, layout, atomicity, pins, caps ----------------

use std::sync::atomic::{AtomicUsize, Ordering};

use crate::graph::{ForceState, LAYOUT_COSE};

/// A temporal registry over `nodes` and persisted `edges` (uuid, source,
/// target); node `i` is valid until `node_end[i]` (half-open).
fn registry_for(nodes: &[Uuid], edges: &[(Uuid, usize, usize)], node_end: &[i64]) -> Arc<Registry> {
    let valid = vec![1u8; nodes.len()];
    let col = |values: &[i64]| {
        TemporalColumn::from_utc_micros(values, &valid, "UTC", TemporalPrecision::Microsecond)
            .unwrap()
    };
    let (starts, ends) = (col(&vec![0; nodes.len()]), col(node_end));
    let projection = GraphProjection::new(
        nodes,
        &edges.iter().map(|e| e.0).collect::<Vec<_>>(),
        &edges.iter().map(|e| nodes[e.1]).collect::<Vec<_>>(),
        &edges.iter().map(|e| nodes[e.2]).collect::<Vec<_>>(),
        None,
        true,
    )
    .unwrap();
    let graph = TemporalGraph::bind(
        &projection,
        TemporalBindingInput {
            valid_from: Some(&starts),
            valid_to: Some(&ends),
            event_at: None,
        },
        TemporalBindingInput::default(),
    )
    .unwrap();
    Arc::new(Registry {
        graph: Mutex::new(Some(graph)),
    })
}

fn bound(doc: &[u8], load: SessionLoad, registry: &Arc<Registry>) -> GraphSession {
    let mut s = loaded(doc, load);
    s.bind_temporal(registry.clone(), HANDLE).unwrap();
    s
}

#[test]
fn an_expired_collapsed_group_hands_its_live_members_to_the_survivors() {
    // A(0) ⊃ B(1), C(2); D(3). B→D, A→D, B→C. A is collapsed and expires.
    let doc = handmade_ends(
        COMPOSITION_VERSION,
        &node_ids(4),
        &persisted(3),
        &[],
        Some((&[NONE, 0, 0, NONE], &[0, 1, 1, 0])),
        Some(&[(1, 3), (0, 3), (1, 2)]),
    );
    let edges = [(id(11), 1, 3), (id(12), 0, 3), (id(13), 1, 2)];
    let registry = registry_for(&node_ids(4), &edges, &[20, 100, 100, 100]);
    let load = SessionLoad {
        collapsed: Some(vec![1, 0, 0, 0]),
        ..at(&[0.0, 1.0, 2.0, 10.0], &[0.0; 4])
    };
    let mut s = bound(&doc, load, &registry);

    frame_at(&registry, 1, 10);
    let live = s.render(None).unwrap().clone();
    assert_eq!(live.member_of, [0, 0, 0, 1], "A collapsed: B and C ride A");

    frame_at(&registry, 2, 20);
    let out = s.render(None).unwrap().clone();
    assert_eq!(out.node_count(), 3, "B, C and D survive the expired group");
    assert_eq!(out.member_of, [NOT_RENDERED, 0, 1, 2]);
    assert_eq!(
        out.edge_render,
        [0, NOT_RENDERED, 1],
        "B→D and B→C are drawn between the live members; A→D left with A"
    );
    assert_eq!(
        (out.edge_source.clone(), out.edge_target.clone()),
        (vec![0, 0], vec![2, 1])
    );
}

#[test]
fn an_expired_grandparent_reattaches_a_collapsed_group_to_the_root() {
    // G(0) ⊃ A(1) ⊃ B(2); D(3). B→D. A is collapsed; G expires.
    let doc = handmade_ends(
        COMPOSITION_VERSION,
        &node_ids(4),
        &persisted(1),
        &[],
        Some((&[NONE, 0, 1, NONE], &[0, 1, 1, 0])),
        Some(&[(2, 3)]),
    );
    let registry = registry_for(&node_ids(4), &[(id(11), 2, 3)], &[20, 100, 100, 100]);
    let load = SessionLoad {
        collapsed: Some(vec![0, 1, 0, 0]),
        ..at(&[0.0, 1.0, 2.0, 10.0], &[0.0; 4])
    };
    let mut s = bound(&doc, load, &registry);
    frame_at(&registry, 1, 20);
    let out = s.render(None).unwrap().clone();
    assert_eq!(out.member_of, [NOT_RENDERED, 0, 0, 1]);
    assert_eq!(
        (out.edge_source.clone(), out.edge_target.clone()),
        (vec![0], vec![1]),
        "B→D reroutes to A, which is still collapsed"
    );
}

#[test]
fn the_initial_layout_is_the_visible_subgraph_only() {
    let doc = handmade_ends(
        COMPOSITION_VERSION,
        &node_ids(4),
        &persisted(3),
        &[],
        None,
        Some(&[(0, 1), (1, 2), (2, 3)]),
    );
    let edges = [(id(11), 0, 1), (id(12), 1, 2), (id(13), 2, 3)];
    let registry = registry_for(&node_ids(4), &edges, &[100, 20, 100, 100]);
    let load = SessionLoad {
        seed: 5,
        ..SessionLoad::default()
    };
    let mut s = bound(&doc, load, &registry);
    frame_at(&registry, 1, 20); // node 2 (index 1) and its edges are gone
    s.render(None).unwrap();

    // Nodes 0, 2, 3 and the surviving edge 2→3, in compact indices.
    let layout = |nodes: u64, sources: &[u64], targets: &[u64]| {
        let mut f = ForceState::new_configured(
            nodes,
            sources,
            targets,
            None,
            None,
            5,
            LAYOUT_COSE,
            CoseOptions::default(),
            &[],
            &vec![COSE_NO_PARENT; nodes as usize],
        )
        .unwrap();
        f.tick(INITIAL_LAYOUT_STEPS);
        (f.x, f.y)
    };
    let (ex, ey) = layout(3, &[1], &[2]);
    let (x, y) = s.positions().unwrap();
    for (k, node) in [0usize, 2, 3].into_iter().enumerate() {
        assert_eq!(
            (x[node].to_bits(), y[node].to_bits()),
            (ex[k].to_bits(), ey[k].to_bits())
        );
    }
    let centroid = (ex.iter().sum::<f64>() / 3.0, ey.iter().sum::<f64>() / 3.0);
    assert_eq!(
        (x[1], y[1]),
        centroid,
        "the expired node is parked, not laid out"
    );
    let (fx, _) = layout(4, &[0, 1, 2], &[1, 2, 3]);
    assert_ne!(
        bits(&[x[0], x[2], x[3]]),
        bits(&[fx[0], fx[2], fx[3]]),
        "the expired node and edges would have moved the others"
    );
}

#[test]
fn relayout_runs_on_the_visible_subgraph_and_drops_state_when_the_frame_changes() {
    let doc = handmade_ends(
        COMPOSITION_VERSION,
        &node_ids(4),
        &persisted(3),
        &[],
        None,
        Some(&[(0, 1), (1, 2), (2, 3)]),
    );
    let edges = [(id(11), 0, 1), (id(12), 1, 2), (id(13), 2, 3)];
    let registry = registry_for(&node_ids(4), &edges, &[100, 20, 100, 100]);
    let mut s = bound(
        &doc,
        at(&[0.0, 5.0, 10.0, 15.0], &[0.0, 1.0, 0.0, 1.0]),
        &registry,
    );
    frame_at(&registry, 1, 10);
    s.render(None).unwrap();
    s.relayout_step(header(&s, 1), 8).unwrap();

    frame_at(&registry, 2, 20); // node index 1 expires
    s.render(None).unwrap();
    let (x, y) = s
        .positions()
        .map(|(a, b)| (a.to_vec(), b.to_vec()))
        .unwrap();
    s.relayout_step(header(&s, 2), 8).unwrap();

    // Fresh force state over nodes 0, 2, 3 (edge 2→3) from the positions at
    // the frame change; the retained all-nodes state must not continue.
    let pick = |p: &[f64]| vec![p[0], p[2], p[3]];
    let mut expected = ForceState::new_configured(
        3,
        &[1],
        &[2],
        Some(&pick(&x)),
        Some(&pick(&y)),
        0,
        LAYOUT_COSE,
        CoseOptions::default(),
        &[0, 0, 0],
        &[COSE_NO_PARENT; 3],
    )
    .unwrap();
    expected.tick(8);
    let (nx, ny) = s.positions().unwrap();
    for (k, node) in [0usize, 2, 3].into_iter().enumerate() {
        assert_eq!(
            (nx[node].to_bits(), ny[node].to_bits()),
            (expected.x[k].to_bits(), expected.y[k].to_bits()),
            "node {node}"
        );
    }
    assert_eq!(
        (nx[1].to_bits(), ny[1].to_bits()),
        (x[1].to_bits(), y[1].to_bits())
    );
}

// -- atomicity of the temporal check -----------------------------------------------

/// A temporal host that counts registry locks and runs injected callbacks just
/// before the Nth one: the deterministic interleaving a racing frame would
/// produce, without a production branch.
struct Hooked {
    inner: Arc<Registry>,
    calls: AtomicUsize,
    hooks: Mutex<Vec<(usize, Box<dyn FnOnce() + Send>)>>,
}

impl Hooked {
    fn new(inner: &Arc<Registry>) -> Arc<Self> {
        Arc::new(Self {
            inner: inner.clone(),
            calls: AtomicUsize::new(0),
            hooks: Mutex::new(Vec::new()),
        })
    }

    fn calls(&self) -> usize {
        self.calls.load(Ordering::SeqCst)
    }

    /// Run `hook` just before lock number `call` (1-based, absolute).
    fn before(&self, call: usize, hook: impl FnOnce() + Send + 'static) {
        self.hooks.lock().unwrap().push((call, Box::new(hook)));
    }

    fn pending(&self) -> usize {
        self.hooks.lock().unwrap().len()
    }
}

impl TemporalHost for Hooked {
    fn with_graph(&self, handle: TemporalHandle, f: &mut dyn FnMut(&mut TemporalGraph)) -> bool {
        let call = self.calls.fetch_add(1, Ordering::SeqCst) + 1;
        let due: Vec<_> = {
            let mut hooks = self.hooks.lock().unwrap();
            let (due, rest) = std::mem::take(&mut *hooks)
                .into_iter()
                .partition(|(at, _)| *at == call);
            *hooks = rest;
            due
        };
        for (_, hook) in due {
            hook();
        }
        self.inner.with_graph(handle, f)
    }
}

fn hooked_session() -> (GraphSession, Arc<Registry>, Arc<Hooked>) {
    let registry = temporal_registry();
    let host = Hooked::new(&registry);
    let mut s = loaded(&standard_doc(), at(&[0.0, 10.0, 20.0], &[0.0; 3]));
    s.bind_temporal(host.clone(), HANDLE).unwrap();
    frame_at(&registry, 1, 10);
    s.render(None).unwrap();
    (s, registry, host)
}

#[test]
fn every_operation_and_render_takes_exactly_one_registry_lock() {
    let (mut s, _registry, host) = hooked_session();
    let n2 = ElementRef::Node(id(2));
    let locks = |s: &mut GraphSession, run: &dyn Fn(&mut GraphSession)| {
        let before = host.calls();
        run(s);
        host.calls() - before
    };
    assert_eq!(
        locks(&mut s, &|s| {
            select(s, 1, &[2], SelectMode::Replace);
        }),
        1
    );
    assert_eq!(
        locks(&mut s, &|s| {
            s.hover(header(s, 2), Some(&n2)).unwrap();
        }),
        1
    );
    assert_eq!(
        locks(&mut s, &|s| {
            s.pin(header(s, 3), &n2, true).unwrap();
        }),
        1
    );
    assert_eq!(
        locks(&mut s, &|s| {
            s.clear(header(s, 4)).unwrap();
        }),
        1
    );
    assert_eq!(
        locks(&mut s, &|s| {
            s.render(None).unwrap();
        }),
        1
    );
    assert_eq!(
        locks(&mut s, &|s| {
            s.focus_step(header(s, 5), 1).unwrap();
        }),
        1
    );
}

#[test]
fn a_frame_advancing_inside_the_lock_window_is_seen_whole_or_not_at_all() {
    let (mut s, registry, host) = hooked_session();
    let before = s.selection().unwrap();

    // The frame advances just as the operation takes its lock: the op was
    // stamped against the old world, so it is rejected and changes nothing.
    let stamped = header(&s, 1);
    let next = host.calls() + 1;
    let r = registry.clone();
    host.before(next, move || frame_at(&r, 2, 20));
    assert_eq!(
        s.select_refs(stamped, &[ElementRef::Node(id(1))], SelectMode::Replace),
        Err(InteractionStatus::Stale)
    );
    assert_eq!(s.selection().unwrap(), before);

    // A render whose lock is preceded by another frame publishes that frame's
    // visibility under that frame's revision, and no second lock exists in
    // which a later frame could split the two.
    let r = registry.clone();
    let next = host.calls() + 1;
    host.before(next, move || frame_at(&r, 3, 10));
    let stale_second_phase = host.calls() + 2;
    host.before(stale_second_phase, || panic!("a second lock was taken"));
    let out = s.render(None).unwrap().clone();
    assert_eq!(out.member_of, [0, 1, 2], "cursor 10: everything visible");
    assert_eq!(s.published().unwrap().revision, out.revision);
    assert_eq!(host.pending(), 1, "the second-phase hook never ran");
}

// -- shared pins -------------------------------------------------------------------

#[test]
fn a_pin_changed_through_the_temporal_graph_reaches_the_next_relayout() {
    let registry = temporal_registry();
    let mut s = bound(
        &standard_doc(),
        at(&[0.0, 10.0, 20.0], &[0.0, 3.0, 0.0]),
        &registry,
    );
    frame_at(&registry, 1, 10);
    s.render(None).unwrap();
    s.relayout_step(header(&s, 1), 16).unwrap();
    let moved = pos(&s, 1);
    assert_ne!(
        moved,
        (10f64.to_bits(), 3f64.to_bits()),
        "the first relayout moves node 2"
    );

    // Pin it from outside the session, on the shared state.
    registry
        .graph
        .lock()
        .unwrap()
        .as_mut()
        .unwrap()
        .set_pinned_nodes([id(2)])
        .unwrap();
    s.render(None).unwrap();
    s.relayout_step(header(&s, 2), 32).unwrap();
    assert_eq!(
        pos(&s, 1),
        moved,
        "pinned where it stood; the retained state was rebuilt"
    );

    // Unpinning through the same authority releases it again.
    registry
        .graph
        .lock()
        .unwrap()
        .as_mut()
        .unwrap()
        .set_pinned_nodes([])
        .unwrap();
    s.relayout_step(header(&s, 3), 32).unwrap();
    assert_ne!(pos(&s, 1), moved);
}

#[test]
fn binding_and_unbinding_change_the_pin_authority_for_relayout() {
    let load = SessionLoad {
        pinned: Some(vec![0, 1, 0]),
        ..at(&[0.0, 10.0, 20.0], &[0.0, 3.0, 0.0])
    };
    let mut s = loaded(&standard_doc(), load);
    s.render(None).unwrap();
    let start = pos(&s, 1);
    s.relayout_step(header(&s, 1), 16).unwrap();
    assert_eq!(pos(&s, 1), start, "pinned by load.pinned");

    // The temporal graph has no pins; binding hands it the authority.
    let registry = temporal_registry();
    s.bind_temporal(registry, HANDLE).unwrap();
    s.render(None).unwrap();
    s.relayout_step(header(&s, 2), 16).unwrap();
    assert_ne!(
        pos(&s, 1),
        start,
        "no longer pinned once the shared state decides"
    );
    let free = pos(&s, 1);

    s.unbind().unwrap();
    s.render(None).unwrap();
    s.relayout_step(header(&s, 3), 16).unwrap();
    assert_ne!(pos(&s, 1), free, "an unbound session starts with no pins");
}

// -- caps before expansion ---------------------------------------------------------

fn aggregate_session(n: u32) -> GraphSession {
    let doc = handmade_ends(COMPOSITION_VERSION, &node_ids(n), &[], &[], None, Some(&[]));
    let xs: Vec<f64> = (0..n).map(f64::from).collect();
    let mut s = loaded(
        &doc,
        SessionLoad {
            budgets: Some((1, 10)),
            ..at(&xs, &xs)
        },
    );
    assert_eq!(s.render(None).unwrap().tier, LodTier::Aggregate);
    s
}

fn the_aggregate(s: &GraphSession) -> ElementRef {
    ElementRef::Aggregate(AggregateRef {
        render_revision: s.published().unwrap().revision,
        index: 0,
    })
}

#[test]
fn repeated_aggregate_refs_expand_once() {
    let mut s = aggregate_session(1_000);
    let agg = the_aggregate(&s);
    let before = s.work();
    s.select_refs(header(&s, 1), &vec![agg; 1_000], SelectMode::Replace)
        .unwrap();
    assert_eq!(s.selection().unwrap().len(), 1_000);
    let spent = s.work() - before;
    assert!(
        spent <= 3_000,
        "1,000 refs × 1,000 members would be 1,000,000; spent {spent}"
    );
}

#[test]
fn an_oversized_aggregate_is_rejected_before_it_is_expanded() {
    let mut s = aggregate_session(10_001);
    let agg = the_aggregate(&s);
    let before = s.work();
    assert_eq!(
        s.select_refs(
            header(&s, 1),
            std::slice::from_ref(&agg),
            SelectMode::Replace
        ),
        Err(InteractionStatus::SelectionTooLarge)
    );
    assert!(s.selection().unwrap().is_empty(), "atomic");
    assert!(
        s.work() - before < 100,
        "no expansion work: {}",
        s.work() - before
    );
    // The request itself is bounded too: more refs than the cap is rejected
    // without being resolved.
    let before = s.work();
    assert_eq!(
        s.select_refs(
            header(&s, 1),
            &vec![ElementRef::Node(id(1)); 10_001],
            SelectMode::Replace
        ),
        Err(InteractionStatus::SelectionTooLarge)
    );
    assert_eq!(s.work(), before);
    assert_eq!(
        s.set_highlight(
            header(&s, 1),
            HighlightPlane::External,
            &[agg],
            SelectMode::Replace
        ),
        Err(InteractionStatus::SelectionTooLarge),
        "highlights are admitted the same way"
    );
}

// -- keyboard selection keeps what the stop stands for -------------------------------

#[test]
fn keyboard_selection_of_an_aggregate_stop_selects_all_its_members() {
    let mut s = aggregate_session(2);
    s.focus_step(header(&s, 1), 1).unwrap();
    s.select_focused(header(&s, 2), SelectMode::Replace)
        .unwrap();
    let keyboard = selected_nodes(&s);
    assert_eq!(
        keyboard,
        [id(1), id(2)],
        "both members, not the stand-in alone"
    );

    // Exactly what a pointer selection of the same stop does.
    s.clear(header(&s, 3)).unwrap();
    let agg = the_aggregate(&s);
    s.select_refs(header(&s, 4), &[agg], SelectMode::Replace)
        .unwrap();
    assert_eq!(selected_nodes(&s), keyboard);
}

#[test]
fn keyboard_selection_of_a_collapsed_group_and_an_aggregate_edge_is_whole() {
    // The collapsed group selects with its hidden members.
    let mut s = loaded(&compound_doc(), compound_load(true));
    s.render(None).unwrap();
    s.focus_step(header(&s, 1), 1).unwrap();
    s.select_focused(header(&s, 2), SelectMode::Replace)
        .unwrap();
    assert_eq!(selected_nodes(&s), [id(1), id(2), id(3)]);

    // Two source edges between the same two clusters are one drawn edge.
    let doc = handmade_ends(
        COMPOSITION_VERSION,
        &node_ids(4),
        &persisted(2),
        &[],
        None,
        Some(&[(0, 2), (1, 3)]),
    );
    let mut s = loaded(
        &doc,
        SessionLoad {
            budgets: Some((2, 10)),
            ..at(&[0.0, 0.1, 100.0, 100.1], &[0.0; 4])
        },
    );
    let render = s.render(None).unwrap().clone();
    assert_eq!((render.node_count(), render.edge_count()), (2, 1));
    assert_eq!(render.members_of_edge(0), [0, 1], "an aggregate edge");
    s.focus_ref(header(&s, 1), Some(&ElementRef::Edge(id(11))))
        .unwrap();
    s.select_focused(header(&s, 2), SelectMode::Replace)
        .unwrap();
    let mut edges: Vec<_> = s.selection().unwrap();
    edges.sort_by_key(|r| format!("{r:?}"));
    assert_eq!(edges, [ElementRef::Edge(id(11)), ElementRef::Edge(id(12))]);
}

// -- revision exhaustion -----------------------------------------------------------

/// Start a rendered session `remaining` structural changes from exhaustion.
fn near_exhaustion(s: &mut GraphSession, remaining: u32) {
    let revision = u32::MAX - remaining;
    s.render_revision = revision;
    s.published_revision = revision;
    s.published.as_mut().unwrap().revision = revision;
}

#[test]
fn the_revision_never_wraps_and_exhaustion_fails_before_any_mutation() {
    let mut s = line_session();
    near_exhaustion(&mut s, 1);
    let n2 = ElementRef::Node(id(2));

    s.pin(header(&s, 1), &n2, true).unwrap();
    assert_eq!(s.render_revision(), u32::MAX, "the last revision is usable");

    let snapshot = (pos(&s, 1), s.pinned().unwrap(), s.collapsed().to_vec());
    for result in [
        s.pin(header(&s, 2), &n2, false),
        s.move_node(
            header(&s, 2),
            &n2,
            (1.0, 1.0),
            MoveSpace::Data,
            MoveCommit::Preview,
        ),
        s.relayout_step(header(&s, 2), 1),
    ] {
        assert_eq!(result, Err(InteractionStatus::RevisionExhausted));
    }
    assert_eq!(
        (pos(&s, 1), s.pinned().unwrap(), s.collapsed().to_vec()),
        snapshot
    );
    assert_eq!(s.render_revision(), u32::MAX, "no wrap");
    assert_eq!(
        InteractionStatus::RevisionExhausted.code(),
        "GF_INTERACTION_REVISION_EXHAUSTED"
    );

    // Style-only operations still work at the last revision, and a stale stamp
    // from the start of the session is not revived.
    s.render(None).unwrap();
    select(&mut s, 2, &[1], SelectMode::Replace);
    let mut ancient = header(&s, 3);
    ancient.stamp.render_revision = 1;
    assert_eq!(s.clear(ancient), Err(InteractionStatus::Stale));

    // A new camera needs a new revision.
    let camera = Camera {
        scale_x: 1.0,
        scale_y: 1.0,
        offset_x: 0.0,
        offset_y: 0.0,
        viewport_width: 5.0,
        viewport_height: 5.0,
        dpr: 1.0,
    };
    assert!(matches!(
        s.render(Some(camera)),
        Err(InteractionStatus::RevisionExhausted)
    ));
    assert_eq!(s.render_revision(), u32::MAX);
    assert_eq!(s.published().unwrap().revision, u32::MAX);
}

#[test]
fn exhaustion_blocks_disclosure_binding_and_a_changed_temporal_frame() {
    let mut s = loaded(&compound_doc(), compound_load(false));
    s.render(None).unwrap();
    near_exhaustion(&mut s, 0);
    let a = ElementRef::Node(id(1));
    assert_eq!(
        s.toggle_disclosure(header(&s, 1), &a, DisclosureAction::Collapse),
        Err(InteractionStatus::RevisionExhausted)
    );
    assert_eq!(s.collapsed(), [0; 5]);
    assert_eq!(
        s.bind_temporal(temporal_registry(), HANDLE),
        Err(InteractionStatus::RevisionExhausted)
    );
    assert!(!s.is_bound());

    // A bound session whose temporal frame moves at the last revision fails
    // every operation without applying it, and keeps failing consistently.
    let registry = temporal_registry();
    let mut b = bound(
        &standard_doc(),
        at(&[0.0, 10.0, 20.0], &[0.0; 3]),
        &registry,
    );
    frame_at(&registry, 1, 10);
    b.render(None).unwrap();
    near_exhaustion(&mut b, 0);
    frame_at(&registry, 2, 20);
    for seq in 1..=2 {
        assert_eq!(
            b.select_refs(
                header(&b, seq),
                &[ElementRef::Node(id(1))],
                SelectMode::Replace
            ),
            Err(InteractionStatus::RevisionExhausted)
        );
        assert!(b.selection().unwrap().is_empty());
    }
    assert!(matches!(
        b.render(None),
        Err(InteractionStatus::RevisionExhausted)
    ));
    assert!(b.unbind().is_err());
}
