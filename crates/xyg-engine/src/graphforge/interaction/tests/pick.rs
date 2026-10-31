//! S3 source-bound geometry, admission and transaction regressions.
use super::*;
use crate::graph_interaction_state::HighlightPlane;
use crate::graphforge::interaction::paint::SourceStyle;

fn at(x: &[f64], y: &[f64]) -> SessionLoad {
    SessionLoad {
        x: Some(x.to_vec()),
        y: Some(y.to_vec()),
        ..Default::default()
    }
}
fn loaded(doc: &[u8], x: &[f64], y: &[f64]) -> GraphSession {
    GraphSession::create(doc, at(x, y), 7).unwrap()
}
fn styles(s: &mut GraphSession, classes: &[u8], statuses: &[u8]) {
    let doc = handmade(
        s.identity.node_uuids(),
        &(0..s.identity.edge_count())
            .map(|i| E::Persisted(id(11 + i as u32)))
            .collect::<Vec<_>>(),
        &[],
    );
    let bytes = extend(&doc, |b| {
        b.u8s("node.class", 0, classes);
        b.u8s("edge.status", 0, statuses);
    });
    let d = ComposedDocument::decode(&bytes).unwrap();
    s.node_style = SourceStyle::read(&d, "node", classes.len()).unwrap();
    s.edge_style = SourceStyle::read(&d, "edge", statuses.len()).unwrap();
}
fn extend(doc: &[u8], add: impl FnOnce(&mut Builder)) -> Vec<u8> {
    let c = Container::decode(doc, DOCUMENT_MAGIC).unwrap();
    let mut b = Builder::new(DOCUMENT_MAGIC);
    b.extend_from(&c);
    add(&mut b);
    b.finish()
}

#[test]
fn pick_uses_shapes_outlines_current_publication_and_style_republish() {
    let doc = handmade(&(1..=6).map(id).collect::<Vec<_>>(), &[], &[]);
    let mut s = loaded(&doc, &[0., 40., 80., 120., 160., 200.], &[0.; 6]);
    styles(&mut s, &[0, 1, 2, 3, 4, 5], &[]);
    let before = s.render(None).unwrap().clone();
    for (i, n) in before.paint.nodes.iter().enumerate() {
        assert_eq!(
            before.pick_at(n.center[0], n.center[1]).unwrap(),
            Some(PickTarget::Node(i))
        );
        assert_eq!(before.member_of[before.focus_node[i] as usize], i as u64);
    }
    let n = &before.paint.nodes[1];
    let radius = f64::from(n.style.size) * 0.5;
    assert_eq!(
        before.pick_at(40. + radius - 0.01, radius - 0.01).unwrap(),
        Some(PickTarget::Node(1))
    );
    assert_eq!(
        before.pick_at(radius - 0.01, radius - 0.01).unwrap(),
        None,
        "circle corner must miss"
    );
    assert_eq!(
        before.pick_at(160. + radius * 0.8, radius * 0.8).unwrap(),
        None,
        "cross corner must miss"
    );
    s.select_at(header(&s, 1), 40., 0., SelectMode::Replace)
        .unwrap();
    let after = s.render(None).unwrap();
    assert_eq!(before.revision, after.revision);
    assert_ne!(
        before.paint.nodes[1].style.width,
        after.paint.nodes[1].style.width
    );
    assert_eq!(after.pick_at(40., 0.).unwrap(), Some(PickTarget::Node(1)));
}

#[test]
fn routed_gaps_heads_selfloops_and_three_parallel_lanes_are_exact() {
    let doc = handmade_ends(
        COMPOSITION_VERSION,
        &[id(1), id(2)],
        &(11..15).map(|i| E::Persisted(id(i))).collect::<Vec<_>>(),
        &[],
        None,
        Some(&[(0, 1), (0, 1), (1, 0), (1, 1)]),
    );
    let mut s = loaded(&doc, &[0., 100.], &[0., 0.]);
    styles(&mut s, &[0, 1], &[1; 4]);
    let r = s
        .render(Some(Camera {
            scale_x: 1.,
            scale_y: 100.,
            offset_x: 20.,
            offset_y: 100.,
            viewport_width: 200.,
            viewport_height: 200.,
            dpr: 2.,
        }))
        .unwrap();
    assert_eq!(r.paint.pieces.iter().filter(|p| p.edge == 3).count(), 3);
    let lanes: Vec<_> = r
        .paint
        .pieces
        .iter()
        .filter(|p| p.edge < 3)
        .map(|p| (p.edge, (p.start[1] + p.end[1]) * 0.5))
        .collect();
    assert!(lanes.windows(2).all(|p| p[0].1 != p[1].1));
    for (edge, y) in lanes {
        assert_eq!(r.pick_at(70., y).unwrap(), Some(PickTarget::Edge(edge)));
    }
    for p in &r.paint.pieces {
        if let Some(h) = p.head {
            let center = [
                (h[0][0] + h[1][0] + h[2][0]) / 3.,
                (h[0][1] + h[1][1] + h[2][1]) / 3.,
            ];
            assert_eq!(
                r.pick_at(center[0], center[1]).unwrap(),
                Some(PickTarget::Edge(p.edge))
            );
        }
    }
    assert_ne!(
        r.pick_at(20., 100.).unwrap(),
        Some(PickTarget::Edge(0)),
        "node covers its trim gap"
    );
    let loop_piece = r
        .paint
        .pieces
        .iter()
        .find(|p| p.edge == 3 && p.head.is_none())
        .unwrap();
    let mid = [
        (loop_piece.start[0] + loop_piece.end[0]) / 2.,
        (loop_piece.start[1] + loop_piece.end[1]) / 2.,
    ];
    assert_eq!(
        r.pick_at(mid[0], mid[1]).unwrap(),
        Some(PickTarget::Edge(3))
    );
}

#[test]
fn compound_band_passes_interior_and_collapse_selects_members() {
    let doc = handmade_with(
        COMPOSITION_VERSION,
        &[id(1), id(2), id(3)],
        &[],
        &[],
        Some((&[NONE_U32, 0, 0], &[0, 1, 1])),
    );
    let mut s = loaded(&doc, &[0., 100., 200.], &[0.; 3]);
    let r = s.render(None).unwrap().clone();
    let f = &r.paint.frames[0];
    assert_eq!(
        r.pick_at(100., f.bounds[1]).unwrap(),
        Some(PickTarget::Node(0))
    );
    assert_eq!(r.pick_at(150., 0.).unwrap(), None);
    s.toggle_disclosure(
        header(&s, 1),
        &ElementRef::Node(id(1)),
        DisclosureAction::Collapse,
    )
    .unwrap();
    s.render(None).unwrap();
    s.select_at(header(&s, 2), 0., 0., SelectMode::Replace)
        .unwrap();
    assert_eq!(s.selection().unwrap().len(), 3);
}

#[test]
fn region_modes_policies_and_concave_lasso_are_whole() {
    let doc = handmade(
        &[id(1), id(2), id(3)],
        &[E::Persisted(id(11)), E::Persisted(id(12))],
        &[],
    );
    let mut s = loaded(&doc, &[0., 100., 100.], &[0., 0., 100.]);
    s.render(None).unwrap();
    let box_ = [-10., -10., 110., 10.];
    s.brush(
        header(&s, 1),
        box_,
        SelectMode::Replace,
        SelectionPolicy::NodesAndInducedEdges,
    )
    .unwrap();
    assert_eq!(s.selection().unwrap().len(), 3);
    s.brush(
        header(&s, 2),
        box_,
        SelectMode::Toggle,
        SelectionPolicy::NodesAndInducedEdges,
    )
    .unwrap();
    assert!(s.selection().unwrap().is_empty());
    s.brush(header(&s, 3), box_, SelectMode::Add, SelectionPolicy::Nodes)
        .unwrap();
    assert_eq!(s.selection().unwrap().len(), 2);
    s.brush(
        header(&s, 4),
        [45., -2., 55., 2.],
        SelectMode::Replace,
        SelectionPolicy::Edges,
    )
    .unwrap();
    assert_eq!(s.selection().unwrap(), [ElementRef::Edge(id(11))]);
    // An L-shaped polygon excludes node3 although its AABB contains it.
    s.lasso(
        header(&s, 5),
        &[
            [-10., -10.],
            [110., -10.],
            [110., 10.],
            [10., 10.],
            [10., 110.],
            [-10., 110.],
        ],
        SelectMode::Replace,
        SelectionPolicy::Nodes,
    )
    .unwrap();
    assert_eq!(
        s.selection().unwrap(),
        [ElementRef::Node(id(1)), ElementRef::Node(id(2))]
    );
}

#[test]
fn oversized_selection_and_polygon_work_reject_without_consuming_operation() {
    let nodes: Vec<_> = (1..=10_001).map(id).collect();
    let doc = handmade(&nodes, &[], &[]);
    let mut s = loaded(
        &doc,
        &(0..10_001).map(|i| i as f64 * 20.).collect::<Vec<_>>(),
        &vec![0.; 10_001],
    );
    s.render(None).unwrap();
    let h = header(&s, 1);
    assert_eq!(
        s.brush(
            h,
            [-10., -10., 300_000., 10.],
            SelectMode::Replace,
            SelectionPolicy::Nodes
        ),
        Err(InteractionStatus::SelectionTooLarge)
    );
    assert!(s.selection().unwrap().is_empty());
    let corners = [[-10., -10.], [300_000., -10.], [300_000., 10.], [-10., 10.]];
    let polygon: Vec<_> = (0..401).map(|i| corners[i % 4]).collect();
    assert_eq!(
        s.lasso(h, &polygon, SelectMode::Replace, SelectionPolicy::Nodes),
        Err(InteractionStatus::Budget)
    );
    s.brush(
        h,
        [-10., -10., 199_990., 10.],
        SelectMode::Replace,
        SelectionPolicy::Nodes,
    )
    .unwrap();
    assert_eq!(s.selection().unwrap().len(), 10_000);
}

#[test]
fn nodes_alone_over_primitive_cap_use_same_publication_linear_queries() {
    let n = MAX_GRAPH_PICK_PRIMITIVES + 1;
    let nodes: Vec<_> = (1..=n as u32).map(id).collect();
    let mut s = loaded(
        &handmade(&nodes, &[], &[]),
        &(0..n).map(|i| i as f64 * 20.).collect::<Vec<_>>(),
        &vec![0.; n],
    );
    let r = s.render(None).unwrap();
    assert!(r.pick.degraded && r.pick.node_scan);
    assert!(r.pick.primitive_count() <= MAX_GRAPH_PICK_PRIMITIVES);
    assert!(r.pick.grid_entries() <= MAX_GRAPH_PICK_GRID_ENTRIES);
    assert_eq!(
        r.pick_at((n - 1) as f64 * 20., 0.).unwrap(),
        Some(PickTarget::Node(n - 1))
    );
    s.brush(
        header(&s, 1),
        [
            (n - 1) as f64 * 20. - 1.,
            -1.,
            (n - 1) as f64 * 20. + 1.,
            1.,
        ],
        SelectMode::Replace,
        SelectionPolicy::Nodes,
    )
    .unwrap();
    assert_eq!(s.selection().unwrap(), [ElementRef::Node(id(n as u32))]);
}

#[test]
fn local_identical_requests_queue_distinct_snapshots_but_retries_do_not() {
    let mut s = GraphSession::create_linked(&standard_doc(), SessionLoad::default(), 7, 4).unwrap();
    s.select_refs(
        header(&s, 1),
        &[ElementRef::Node(id(1))],
        SelectMode::Replace,
    )
    .unwrap();
    let one = s.take_outbound().unwrap();
    let h = header(&s, 2);
    s.select_refs(h, &[ElementRef::Node(id(1))], SelectMode::Replace)
        .unwrap();
    let two = s.take_outbound().unwrap();
    assert_eq!(one.revision + 1, two.revision);
    assert_eq!(s.render_revision(), 0);
    s.select_refs(h, &[], SelectMode::Replace).unwrap();
    assert!(s.take_outbound().is_none());
}

fn event(refs: Vec<ElementRef>) -> GraphCoordinationEvent {
    GraphCoordinationEvent {
        group_id: 4,
        source_instance: 8,
        revision: 1,
        generation: None,
        refs,
    }
}
#[test]
fn remote_shape_precedes_group_filter_and_failed_event_keeps_watermark() {
    let mut s = GraphSession::create_linked(&standard_doc(), SessionLoad::default(), 7, 4).unwrap();
    let h = header(&s, 1);
    for bad in [
        event(vec![ElementRef::Node(id(2)), ElementRef::Node(id(1))]),
        event(vec![ElementRef::Node(id(1)); 2]),
        event(vec![s.identity.edge_ref(2)]),
        GraphCoordinationEvent {
            source_instance: 0,
            ..event(vec![])
        },
        GraphCoordinationEvent {
            revision: 0,
            ..event(vec![])
        },
    ] {
        let bad = GraphCoordinationEvent {
            group_id: 99,
            ..bad
        };
        assert_eq!(s.apply_remote(h, &bad), Err(InteractionStatus::Invalid));
    }
    let good = event(vec![
        ElementRef::Node(id(1)),
        ElementRef::Node(id(99)),
        ElementRef::Edge(id(11)),
    ]);
    assert_eq!(s.apply_remote(h, &good).unwrap().unmatched, 1);
    assert_eq!(s.selection().unwrap().len(), 2);
    assert!(s.take_outbound().is_none());
    assert_eq!(s.render_revision(), 0);
    assert_eq!(
        s.apply_remote(header(&s, 2), &good),
        Err(InteractionStatus::StaleRemote)
    );
    assert_eq!(
        s.apply_remote(
            header(&s, 2),
            &GraphCoordinationEvent {
                source_instance: 7,
                ..good
            }
        ),
        Err(InteractionStatus::SelfEcho)
    );
}

#[test]
fn remote_cap_exact_identity_generation_and_shared_uuid() {
    let mut nodes: Vec<_> = (1..=10_000).map(id).collect();
    nodes.sort();
    let doc = handmade(
        &nodes,
        &[
            E::Persisted(id(1)),
            E::Overlay {
                layer: 0,
                path: 0,
                order: 0,
            },
        ],
        &[Some("route")],
    );
    let mut s = GraphSession::create_linked(&doc, SessionLoad::default(), 7, 4).unwrap();
    let all = event(nodes.iter().copied().map(ElementRef::Node).collect());
    s.apply_remote(header(&s, 1), &all).unwrap();
    assert_eq!(s.selection().unwrap().len(), 10_000);
    let mut over = all.clone();
    over.revision = 2;
    over.refs.push(ElementRef::Edge(id(1)));
    assert_eq!(
        s.apply_remote(header(&s, 2), &over),
        Err(InteractionStatus::SelectionTooLarge)
    );
    assert_eq!(s.selection().unwrap().len(), 10_000);
    let derived = s.identity.to_transport(&s.identity.edge_ref(1)).unwrap();
    let cross = GraphCoordinationEvent {
        revision: 2,
        generation: Some(id(100)),
        ..event(vec![
            ElementRef::Node(id(1)),
            ElementRef::Edge(id(1)),
            derived.clone(),
        ])
    };
    assert_eq!(s.apply_remote(header(&s, 2), &cross).unwrap().unmatched, 1);
    assert_eq!(s.selection().unwrap().len(), 2);
    let mut wrong = derived;
    let ElementRef::Derived(ref mut d) = wrong else {
        panic!()
    };
    d.result = ResultRef::Exact(Some("route:other".into()));
    assert_eq!(
        s.apply_remote(
            header(&s, 3),
            &GraphCoordinationEvent {
                revision: 3,
                ..event(vec![wrong])
            }
        )
        .unwrap()
        .unmatched,
        1
    );
}

#[test]
fn update_reorders_reconciles_exact_derived_and_retains_pins_without_positions() {
    let mut s = loaded(&standard_doc(), &[0., 10., 20.], &[0.; 3]);
    let derived = s.identity.edge_ref(2);
    s.select_refs(
        header(&s, 1),
        &[
            ElementRef::Node(id(1)),
            ElementRef::Node(id(2)),
            derived.clone(),
        ],
        SelectMode::Replace,
    )
    .unwrap();
    s.set_highlight(
        header(&s, 2),
        HighlightPlane::External,
        &[derived],
        SelectMode::Replace,
    )
    .unwrap();
    s.pin(header(&s, 3), &ElementRef::Node(id(2)), true)
        .unwrap();
    s.focus_ref(header(&s, 4), Some(&ElementRef::Node(id(1))))
        .unwrap();
    s.render(None).unwrap();
    let revision = s.render_revision();
    let replacement = handmade(
        &[id(3), id(2)],
        &[
            E::Persisted(id(12)),
            E::Overlay {
                layer: 0,
                path: 0,
                order: 0,
            },
        ],
        &[Some("other")],
    );
    let h = header(&s, 5);
    let result = s.update(h, &replacement, SessionLoad::default()).unwrap();
    assert_eq!(result.dropped, 4);
    assert_eq!(s.render_revision(), revision + 1);
    assert_eq!(s.selection().unwrap(), [ElementRef::Node(id(2))]);
    assert_eq!(s.pinned().unwrap(), [id(2)]);
    assert!(s.focus().unwrap().is_none());
    assert!(s.positions().is_none());
    assert!(s.published().is_none());
    assert_eq!(s.update(h, &[], SessionLoad::default()).unwrap(), result);
    s.render(None).unwrap();
    assert_eq!(s.pinned().unwrap(), [id(2)]);
}

#[test]
fn update_explicit_persistence_generation_and_atomic_invalid_load() {
    let doc = standard_doc();
    let mut s = loaded(&doc, &[0., 10., 20.], &[0.; 3]);
    let d = s.identity.edge_ref(2);
    s.select_refs(header(&s, 1), &[d], SelectMode::Replace)
        .unwrap();
    s.update(
        header(&s, 2),
        &doc,
        SessionLoad {
            pinned: Some(vec![1, 0, 0]),
            ..at(&[1., 2., 3.], &[4., 5., 6.])
        },
    )
    .unwrap();
    assert_eq!(s.selection().unwrap().len(), 1);
    assert_eq!(s.pinned().unwrap(), [id(1)]);
    let next = extend(&doc, |b| b.uuids("base.generation", 0, &[id(100)]));
    let h = header(&s, 3);
    let rev = s.render_revision();
    let positions = s.positions().map(|(x, y)| (x.to_vec(), y.to_vec()));
    assert_eq!(
        s.update(
            h,
            &next,
            SessionLoad {
                x: Some(vec![1.; 3]),
                y: None,
                ..Default::default()
            }
        ),
        Err(InteractionStatus::Invalid)
    );
    assert_eq!(s.render_revision(), rev);
    assert_eq!(
        s.positions().map(|(x, y)| (x.to_vec(), y.to_vec())),
        positions
    );
    assert_eq!(
        s.update(h, &next, SessionLoad::default()).unwrap().dropped,
        1
    );
    s.render_revision = u32::MAX;
    let before = s.generation();
    assert_eq!(
        s.update(header(&s, 4), &doc, SessionLoad::default()),
        Err(InteractionStatus::RevisionExhausted)
    );
    assert_eq!(s.generation(), before);
}

#[test]
fn bound_update_preserves_owner_and_rejects_order_endpoints_and_disposal() {
    let (mut s, registry) = bound_session();
    s.select_uuids(header(&s, 1), &[id(2)], SelectMode::Replace)
        .unwrap();
    let rev = s.render_revision();
    let reordered = handmade(
        &[id(2), id(1), id(3)],
        &[E::Persisted(id(11)), E::Persisted(id(12))],
        &[],
    );
    assert_eq!(
        s.update(header(&s, 2), &reordered, SessionLoad::default()),
        Err(InteractionStatus::Invalid)
    );
    assert!(s.is_bound());
    assert_eq!(s.render_revision(), rev);
    let wrong = handmade_ends(
        COMPOSITION_VERSION,
        &[id(1), id(2), id(3)],
        &[E::Persisted(id(11)), E::Persisted(id(12))],
        &[],
        None,
        Some(&[(0, 2), (1, 2)]),
    );
    assert_eq!(
        s.update(header(&s, 2), &wrong, SessionLoad::default()),
        Err(InteractionStatus::Invalid)
    );
    s.update(header(&s, 2), &standard_doc(), SessionLoad::default())
        .unwrap();
    assert!(s.is_bound());
    assert_eq!(s.selection().unwrap(), [ElementRef::Node(id(2))]);
    assert_eq!(frame(&registry, 1).selected_visible_node_ids(), [id(2)]);
    registry.graph.lock().unwrap().take();
    assert_eq!(
        s.update(header(&s, 3), &standard_doc(), SessionLoad::default()),
        Err(InteractionStatus::Unbound)
    );
}

#[test]
fn bound_remote_is_one_authoritative_selection_and_update_preserves_delivery_history() {
    let (mut s, registry) = bound_session();
    s.coordination.group = 4;
    s.select_uuids(header(&s, 1), &[id(1)], SelectMode::Replace)
        .unwrap();
    let pending = s.pending_outbound().cloned();
    let linked = event(vec![ElementRef::Node(id(2)), ElementRef::Edge(id(12))]);
    s.apply_remote(header(&s, 2), &linked).unwrap();
    assert_eq!(s.pending_outbound(), pending.as_ref());
    let owner = registry.graph.lock().unwrap();
    assert_eq!(
        owner
            .as_ref()
            .unwrap()
            .interaction_state()
            .selection()
            .nodes,
        [id(2)].into()
    );
    drop(owner);
    let revision = s.render_revision();
    s.update(header(&s, 3), &standard_doc(), SessionLoad::default())
        .unwrap();
    assert_eq!(s.pending_outbound(), pending.as_ref());
    assert_eq!(s.render_revision(), revision + 1);
    assert_eq!(
        s.apply_remote(header(&s, 4), &linked),
        Err(InteractionStatus::StaleRemote)
    );
    let wrong = GraphCoordinationEvent {
        group_id: 0,
        revision: 2,
        ..linked
    };
    let before = s.selection().unwrap();
    assert!(!s.apply_remote(header(&s, 4), &wrong).unwrap().state_changed);
    assert_eq!(s.selection().unwrap(), before);
}

#[test]
fn update_invalid_forest_and_style_leave_entire_candidate_uncommitted() {
    let mut s = loaded(&standard_doc(), &[0., 10., 20.], &[0.; 3]);
    s.render(None).unwrap();
    let before = s.published().cloned();
    let h = header(&s, 1);
    let invalid = handmade_with(
        COMPOSITION_VERSION,
        &[id(1), id(2), id(3)],
        &[],
        &[],
        Some((&[1, 0, NONE_U32], &[1, 1, 0])),
    );
    assert_eq!(
        s.update(h, &invalid, SessionLoad::default()),
        Err(InteractionStatus::Invalid)
    );
    assert_eq!(s.published(), before.as_ref());
    let bad = extend(&standard_doc(), |b| b.u8s("node.class", 0, &[0, 8, 0]));
    assert_eq!(
        s.update(h, &bad, SessionLoad::default()),
        Err(InteractionStatus::Invalid)
    );
    assert_eq!(s.published(), before.as_ref());
    s.update(h, &standard_doc(), at(&[1., 2., 3.], &[4., 5., 6.]))
        .unwrap();
    assert_eq!(s.positions().unwrap().0, [1., 2., 3.]);
}

#[test]
fn lod_pick_membership_and_selection_cover_only_the_published_graph() {
    let nodes: Vec<_> = (1..=12).map(id).collect();
    let doc = handmade(&nodes, &[E::Persisted(id(11)), E::Persisted(id(12))], &[]);
    let mut s = GraphSession::create(
        &doc,
        SessionLoad {
            budgets: Some((2, 2)),
            ..at(
                &(0..12).map(|i| i as f64 * 100.).collect::<Vec<_>>(),
                &[0.; 12],
            )
        },
        7,
    )
    .unwrap();
    let r = s.render(None).unwrap().clone();
    assert!(r.node_count() <= 2);
    for (i, n) in r.paint.nodes.iter().enumerate() {
        assert_eq!(
            r.pick_at(n.center[0], n.center[1]).unwrap(),
            Some(PickTarget::Node(i))
        );
        s.select_at(
            header(&s, i as u64 + 1),
            n.center[0],
            n.center[1],
            SelectMode::Replace,
        )
        .unwrap();
        assert_eq!(s.selection().unwrap().len(), r.members_of_node(i).len());
    }
}

#[test]
fn head_pass_precedes_later_shafts_and_brush_retries_retain_outcome() {
    let mut s = loaded(&standard_doc(), &[0., 100., 200.], &[0.; 3]);
    let mut r = s.render(None).unwrap().clone();
    r.paint.nodes.clear();
    r.paint.frames.clear();
    r.paint.pieces = vec![
        EdgePiece {
            edge: 0,
            single_piece: true,
            start: [-20., 0.],
            end: [-8., 0.],
            half_width: 1.,
            dash: (0., 0.),
            dash_offset: 0.,
            head: Some([[0., 0.], [-8., 4.], [-8., -4.]]),
        },
        EdgePiece {
            edge: 1,
            single_piece: true,
            start: [-4., -10.],
            end: [-4., 10.],
            half_width: 1.,
            dash: (0., 0.),
            dash_offset: 0.,
            head: None,
        },
    ];
    r.pick = PickIndex::build(&r.paint);
    assert_eq!(
        r.pick_at(-4., 0.).unwrap(),
        Some(PickTarget::Edge(0)),
        "all heads paint above all shafts"
    );
    let h = header(&s, 1);
    let first = s
        .brush(
            h,
            [-1., -1., 1., 1.],
            SelectMode::Replace,
            SelectionPolicy::Nodes,
        )
        .unwrap();
    assert_eq!(
        s.brush(
            h,
            [f64::NAN; 4],
            SelectMode::Replace,
            SelectionPolicy::Nodes
        )
        .unwrap(),
        first
    );
}

#[test]
fn nonrepresentable_screen_geometry_cannot_replace_a_valid_publication() {
    let mut s = loaded(&handmade(&[id(1)], &[], &[]), &[f64::MAX], &[0.]);
    let old = s.render(None).unwrap().clone();
    let rev = s.render_revision();
    assert_eq!(
        s.render(Some(Camera {
            scale_x: 2.,
            scale_y: 1.,
            offset_x: -f64::MAX,
            offset_y: 0.,
            viewport_width: f64::MAX,
            viewport_height: 100.,
            dpr: 1.
        })),
        Err(InteractionStatus::Invalid)
    );
    assert_eq!(s.render_revision(), rev);
    assert_eq!(s.published(), Some(&old));
}
