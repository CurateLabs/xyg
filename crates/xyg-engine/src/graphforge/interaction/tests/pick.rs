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
fn aggregate_omits_source_semantics_even_for_singleton_nodes_and_edges() {
    use crate::graph::LodTier;

    let base = handmade_ends(
        COMPOSITION_VERSION,
        &[id(1), id(2), id(3)],
        &[
            E::Persisted(id(11)),
            E::Persisted(id(12)),
            E::Persisted(id(13)),
        ],
        &[],
        None,
        Some(&[(0, 2), (1, 2), (2, 0)]),
    );
    let base = extend(&base, |b| b.u8s("graph.directed", 0, &[1]));
    let neutral = extend(&base, |b| b.u8s("edge.status", 0, &[0; 3]));
    let styled = extend(&base, |b| {
        b.u8s("node.class", 0, &[1, 2, 3]);
        b.u8s("node.epistemic", 0, &[1, 2, 3]);
        b.u8s("node.status", 0, &[1, 2, 3]);
        b.f64s("node.metric", 0, &[1., 10., 100.]);
        b.u8s("edge.class", 0, &[1, 2, 3]);
        b.u8s("edge.epistemic", 0, &[1, 2, 3]);
        b.u8s("edge.status", 0, &[1; 3]);
        b.f64s("edge.metric", 0, &[1., 10., 100.]);
    });
    for (budgets, tier) in [
        ((2, 10), LodTier::Aggregate),
        ((3, 10), LodTier::Direct),
        ((3, 1), LodTier::EdgeSample),
    ] {
        let load = SessionLoad {
            budgets: Some(budgets),
            ..at(&[0., 10., 100.], &[0.; 3])
        };
        let mut plain = GraphSession::create(&neutral, load.clone(), 7).unwrap();
        let mut authored = GraphSession::create(&styled, load, 7).unwrap();
        let expected = plain.render(None).unwrap().clone();
        let actual = authored.render(None).unwrap().clone();
        assert_eq!(actual.tier, tier);
        assert_eq!(actual.member_of, expected.member_of);
        assert_eq!(actual.edge_members, expected.edge_members);
        if tier == LodTier::Aggregate {
            assert!((0..actual.node_count()).any(|r| actual.members_of_node(r).len() == 1));
            assert!((0..actual.node_count()).any(|r| actual.members_of_node(r).len() == 2));
            assert!((0..actual.edge_count()).any(|r| actual.members_of_edge(r).len() == 1));
            assert!((0..actual.edge_count()).any(|r| actual.members_of_edge(r).len() == 2));
            // Styles, semantic layers, clipping and heads all ignore the source
            // fields for this tier, independent of membership cardinality.
            assert_eq!(actual.paint, expected.paint);
            let mut default_directed = GraphSession::create(
                &base,
                SessionLoad {
                    budgets: Some(budgets),
                    ..at(&[0., 10., 100.], &[0.; 3])
                },
                7,
            )
            .unwrap();
            let fallback = default_directed.render(None).unwrap();
            assert_eq!(fallback.paint.nodes, expected.paint.nodes);
            assert_eq!(fallback.paint.edge_styles, expected.paint.edge_styles);
            assert_eq!(fallback.paint.edge_layers, expected.paint.edge_layers);
            assert!(fallback
                .paint
                .pieces
                .iter()
                .any(|piece| piece.head.is_some()));
            assert!(actual.paint.pieces.iter().all(|piece| piece.head.is_none()));
            for node in &expected.paint.nodes {
                for (dx, dy) in [(0., 0.), (5., 5.), (10., 0.)] {
                    let (x, y) = (node.center[0] + dx, node.center[1] + dy);
                    assert_eq!(actual.pick_at(x, y), expected.pick_at(x, y));
                }
            }
            for session in [&mut plain, &mut authored] {
                session
                    .select_refs(
                        header(session, 1),
                        &[ElementRef::Node(id(3))],
                        SelectMode::Replace,
                    )
                    .unwrap();
                session
                    .focus_ref(header(session, 2), Some(&ElementRef::Node(id(3))))
                    .unwrap();
            }
            let selected_plain = plain.render(None).unwrap();
            let selected_authored = authored.render(None).unwrap();
            assert_eq!(selected_authored.revision, actual.revision);
            assert_eq!(selected_authored.paint, selected_plain.paint);
            assert_ne!(selected_authored.paint, actual.paint);
            assert!(selected_authored.emphasis.iter().any(|&bits| bits != 0));
        } else {
            // Exact-node tiers retain authored node and one-member edge styles.
            assert_ne!(actual.paint.nodes, expected.paint.nodes);
            assert_ne!(actual.paint.edge_styles, expected.paint.edge_styles);
            assert_ne!(actual.paint.edge_layers, expected.paint.edge_layers);
            let mut default_directed = GraphSession::create(
                &base,
                SessionLoad {
                    budgets: Some(budgets),
                    ..at(&[0., 10., 100.], &[0.; 3])
                },
                7,
            )
            .unwrap();
            assert!(default_directed
                .render(None)
                .unwrap()
                .paint
                .pieces
                .iter()
                .any(|piece| piece.head.is_some()));
        }
    }
}

#[test]
fn direct_collapse_and_authored_aggregate_state_keep_source_semantics() {
    let base = handmade_with(
        COMPOSITION_VERSION,
        &[id(1), id(2)],
        &[],
        &[],
        Some((&[NONE_U32, 0], &[0, 1])),
    );
    let doc = extend(&base, |b| b.u8s("node.class", 0, &[1, 2]));
    let mut s = loaded(&doc, &[0., 100.], &[0.; 2]);
    let before = s.render(None).unwrap().clone();
    s.select_refs(
        header(&s, 1),
        &[ElementRef::Node(id(2))],
        SelectMode::Replace,
    )
    .unwrap();
    s.toggle_disclosure(
        header(&s, 2),
        &ElementRef::Node(id(1)),
        DisclosureAction::Collapse,
    )
    .unwrap();
    let collapsed = s.render(None).unwrap();
    assert_eq!(collapsed.tier, crate::graph::LodTier::Direct);
    assert_eq!(collapsed.node_count(), 1);
    assert_eq!(
        collapsed.paint.nodes[0].style.fill,
        before.paint.nodes[0].style.fill
    );
    assert_eq!(
        collapsed.paint.nodes[0].style.shape,
        before.paint.nodes[0].style.shape
    );
    assert!(collapsed.paint.nodes[0].style.width > before.paint.nodes[0].style.width);

    let flags = [crate::graph_style::FLAG_AGGREGATE; 2];
    let authored = extend(&doc, |b| b.u32s("node.flags", 0, &flags));
    let plain = extend(&base, |b| b.u32s("node.flags", 0, &flags));
    let mut authored = loaded(&authored, &[0., 100.], &[0.; 2]);
    let mut plain = loaded(&plain, &[0., 100.], &[0.; 2]);
    assert_ne!(
        authored.render(None).unwrap().paint.nodes[0].style.fill,
        plain.render(None).unwrap().paint.nodes[0].style.fill
    );
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

#[test]
fn overflowing_edge_length_preserves_publication_camera_revision_and_pick_identity() {
    let doc = handmade(&[id(1), id(2)], &[E::Persisted(id(11))], &[]);
    let mut s = loaded(&doc, &[0., 100.], &[0.; 2]);
    let camera = Camera {
        scale_x: 1.,
        scale_y: 1.,
        offset_x: 0.,
        offset_y: 0.,
        viewport_width: 200.,
        viewport_height: 100.,
        dpr: 1.,
    };
    let old = s.render(Some(camera)).unwrap().clone();
    let stamp = header(&s, 1);
    assert_eq!(old.paint.pieces.len(), 1);
    // Mapped nodes and membership remain finite; only squared length overflows.
    assert_eq!(
        s.render(Some(Camera {
            scale_x: 1e154,
            viewport_width: 1e156,
            ..camera
        })),
        Err(InteractionStatus::Invalid)
    );
    assert_eq!(s.camera, Some(camera));
    assert_eq!(s.render_revision(), old.revision);
    assert_eq!(s.published_revision, old.revision);
    assert_eq!(s.published(), Some(&old));
    assert_eq!(s.render(Some(camera)).unwrap(), &old);
    assert_eq!(
        s.published().unwrap().pick_at(50., 0.).unwrap(),
        Some(PickTarget::Edge(0))
    );
    s.select_at(stamp, 50., 0., SelectMode::Replace).unwrap();
    assert_eq!(s.selection().unwrap(), vec![ElementRef::Edge(id(11))]);
}

#[test]
fn huge_loaded_edge_geometry_is_invalid_including_pre_route_overflow() {
    let doc = handmade(&[id(1), id(2)], &[E::Persisted(id(11))], &[]);
    for x in [[0., 1e155], [-f64::MAX, f64::MAX]] {
        let mut s = loaded(&doc, &x, &[0.; 2]);
        assert_eq!(s.render(None), Err(InteractionStatus::Invalid), "{x:?}");
        assert_eq!(s.render_revision(), 0);
        assert!(s.published().is_none());
        assert_eq!(s.camera, None);
        assert_eq!(s.positions().unwrap().0, &x);
    }
}

#[test]
fn pre_route_delta_overflow_is_invalid_independently_of_screen_length() {
    let doc = handmade(&[id(1), id(2)], &[E::Persisted(id(11))], &[]);
    let mut s = loaded(&doc, &[-f64::MAX, f64::MAX], &[0.; 2]);
    // A tiny camera makes the mapped chord representable, but the routing
    // kernel's data-space subtraction overflows and otherwise discards it.
    assert_eq!(
        s.render(Some(Camera {
            scale_x: 1e-308,
            scale_y: 1.,
            offset_x: 2.,
            offset_y: 0.,
            viewport_width: 4.,
            viewport_height: 100.,
            dpr: 1.,
        })),
        Err(InteractionStatus::Invalid)
    );
    assert_eq!(s.render_revision(), 0);
    assert!(s.published().is_none());
}

#[test]
fn valid_zero_length_occluded_and_culled_edges_still_publish_without_pieces() {
    let doc = handmade(&[id(1), id(2)], &[E::Persisted(id(11))], &[]);
    for x in [[0., 0.], [0., 1.], [0., 1e-200]] {
        let mut s = loaded(&doc, &x, &[0.; 2]);
        let r = s.render(None).unwrap();
        assert_eq!(r.edge_count(), 1);
        assert_eq!(r.members_of_edge(0), &[0]);
        assert!(r.paint.pieces.is_empty(), "{x:?}");
    }
    let mut s = loaded(&doc, &[1000., 1100.], &[0.; 2]);
    let r = s
        .render(Some(Camera {
            scale_x: 1.,
            scale_y: 1.,
            offset_x: 0.,
            offset_y: 0.,
            viewport_width: 100.,
            viewport_height: 100.,
            dpr: 1.,
        }))
        .unwrap();
    assert_eq!(r.node_count(), 0);
    assert_eq!(r.edge_count(), 0);
    assert!(r.paint.pieces.is_empty());
}

#[test]
fn finite_directed_circle_chord_with_overflowing_outline_must_not_lose_its_head() {
    let doc = extend(
        &handmade(&[id(1), id(2)], &[E::Persisted(id(11))], &[]),
        |b| b.u8s("edge.status", 0, &[1]),
    );
    // Squared chord length is finite; the canonical circle discriminant is not.
    for (x, y) in [([0., 1e80], [0., 0.]), ([0., 0.], [0., 1e80])] {
        let mut s = loaded(&doc, &x, &y);
        assert_eq!(s.render(None), Err(InteractionStatus::Invalid));
        assert!(s.published().is_none());
        assert_eq!(s.render_revision(), 0);
        assert_eq!(s.camera, None);
    }
    let mut s = loaded(&doc, &[0., 100.], &[0.; 2]);
    let r = s.render(None).unwrap();
    assert_eq!(r.edge_count(), 1);
    assert_eq!(r.paint.pieces.len(), 1);
    assert!(r.paint.pieces[0].head.is_some());
}

#[test]
fn invalid_outline_render_preserves_complete_publication_state_and_delivery() {
    let doc = extend(
        &handmade(&[id(1), id(2)], &[E::Persisted(id(11))], &[]),
        |b| b.u8s("edge.status", 0, &[1]),
    );
    let mut s = GraphSession::create_linked(&doc, at(&[0., 100.], &[0.; 2]), 7, 4).unwrap();
    let camera = Camera {
        scale_x: 1.,
        scale_y: 1.,
        offset_x: 0.,
        offset_y: 0.,
        viewport_width: 200.,
        viewport_height: 100.,
        dpr: 1.,
    };
    s.render(Some(camera)).unwrap();
    s.select_at(header(&s, 1), 50., 0., SelectMode::Replace)
        .unwrap();
    s.focus_ref(header(&s, 2), Some(&ElementRef::Node(id(2))))
        .unwrap();
    let old = s.render(Some(camera)).unwrap().clone();
    assert!(old.paint.pieces[0].head.is_some());
    let last_op = s.last_op.clone();
    let state = s.read_state(|state| state.clone()).unwrap();
    let pending = s.pending_outbound().cloned();
    let sequence = s.coordination.sequence;
    let stamp = header(&s, 3);
    // All mapped endpoints, deltas and computed lengths remain finite.
    assert_eq!(
        s.render(Some(Camera {
            scale_x: 1e78,
            viewport_width: 1e81,
            ..camera
        })),
        Err(InteractionStatus::Invalid)
    );
    assert_eq!(s.camera, Some(camera));
    assert_eq!(s.render_revision(), old.revision);
    assert_eq!(s.published_revision, old.revision);
    assert_eq!(s.published(), Some(&old)); // includes paint, grid, membership
    assert_eq!(s.read_state(|state| state.clone()).unwrap(), state);
    assert_eq!(s.last_op, last_op);
    assert_eq!(s.pending_outbound(), pending.as_ref());
    assert_eq!(s.coordination.sequence, sequence);
    assert_eq!(s.render(Some(camera)).unwrap(), &old);
    assert_eq!(
        s.published().unwrap().pick_at(50., 0.).unwrap(),
        Some(PickTarget::Edge(0))
    );
    s.select_at(stamp, 50., 0., SelectMode::Replace).unwrap();
    assert_eq!(s.selection().unwrap(), [ElementRef::Edge(id(11))]);
    assert_eq!(s.coordination.sequence, sequence + 1);
}

#[test]
fn canonical_outline_shapes_keep_finite_occlusion_and_directed_heads_valid() {
    for class in [0, 1, 2] {
        // circle, square, diamond
        let doc = extend(
            &handmade(&[id(1), id(2)], &[E::Persisted(id(11))], &[]),
            |b| {
                b.u8s("edge.status", 0, &[1]);
                b.u8s("node.class", 0, &[class; 2]);
            },
        );
        for end in [0., 1., 1e-13, 1e-200, 100.] {
            let mut s = loaded(&doc, &[0., end], &[0.; 2]);
            let r = s.render(None).unwrap();
            assert_eq!(r.edge_count(), 1);
            assert_eq!(r.members_of_edge(0), &[0]);
            if end == 100. {
                assert_eq!(r.paint.pieces.len(), 1);
                assert!(r.paint.pieces[0].head.is_some());
            } else {
                assert!(r.paint.pieces.is_empty(), "shape={class} end={end}");
            }
        }
    }
}
