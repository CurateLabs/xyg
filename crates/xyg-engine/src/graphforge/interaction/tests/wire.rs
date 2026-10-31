//! Shared boundary proofs, including failed post-mutation publication rollback.
use super::*;
use crate::graphforge::interaction::wire::{self, Request, WireSession};

fn request(seq: u64, rev: u32, op: u32, extra: impl FnOnce(&mut Builder)) -> Vec<u8> {
    let mut b = Builder::new(wire::REQUEST_MAGIC);
    b.u64s("header.u64", 0, &[7, 9, seq]);
    b.u32s("header.u32", 0, &[rev, op, 0, 0, 0, 0, 0, 0, 0]);
    extra(&mut b);
    b.finish()
}
fn open_doc(doc: &[u8]) -> Vec<u8> {
    request(1, 0, wire::OPEN, |b| {
        b.bytes("document.bytes", 0, doc);
        b.f64s("load.x.f64", 0, &[0., 30., 60.]);
        b.f64s("load.y.f64", 0, &[0., 0., 0.]);
    })
}
fn opened() -> WireSession {
    WireSession::open(&open_doc(&standard_doc()), wire::DEFAULT_MAX_BYTES, 0).unwrap()
}
fn header_of(bytes: &[u8]) -> Vec<u32> {
    Container::decode(bytes, wire::RESULT_MAGIC)
        .unwrap()
        .get("header.u32", 0)
        .unwrap()
        .as_u32("header.u32")
        .unwrap()
}

#[test]
fn exact_refs_roundtrip_and_malformed_pools_reserved_kinds() {
    let refs = vec![
        ElementRef::Node(id(1)),
        ElementRef::Edge(id(1)),
        ElementRef::Derived(DerivedRef {
            result: ResultRef::Exact(Some("route:one".into())),
            layer: 0,
            path: 4,
            order: 5,
        }),
        ElementRef::Derived(DerivedRef {
            result: ResultRef::Exact(None),
            layer: 1,
            path: 6,
            order: 7,
        }),
        ElementRef::Aggregate(AggregateRef {
            render_revision: 9,
            index: 4,
        }),
    ];
    let bytes = wire::encode_refs(&refs).unwrap();
    assert_eq!(wire::decode_refs(&bytes).unwrap(), refs);
    for (at, value) in [(8, 4), (12, 1), (8 + 2 * 56 + 28, 1), (8 + 2 * 56 + 48, 1)] {
        let mut broken = bytes.clone();
        broken[at] = value;
        assert_eq!(wire::decode_refs(&broken), Err(InteractionStatus::Invalid));
    }
    let mut empty = bytes.clone();
    empty[8 + 2 * 56 + 52..8 + 2 * 56 + 56].fill(0);
    assert_eq!(wire::decode_refs(&empty), Err(InteractionStatus::Invalid));
    let mut tail = bytes.clone();
    tail.push(0);
    assert_eq!(wire::decode_refs(&tail), Err(InteractionStatus::Invalid));
}
#[test]
fn strict_operation_schema_rejects_extra_fields_lengths_types() {
    let good = request(2, 0, 4, |_| {});
    assert!(Request::decode(&good).is_ok());
    for bytes in [
        request(2, 0, 4, |b| b.f64s("coordinates.f64", 0, &[0., 0.])),
        request(2, 0, wire::RENDER, |b| b.u32s("camera.f64", 0, &[1])),
        request(2, 0, 17, |b| b.u32s("companion.u32", 0, &[0, 201])),
        request(2, 0, 4, |b| b.u8s("unknown", 0, &[])),
    ] {
        assert!(Request::decode(&bytes).is_err());
    }
    let mut b = Builder::new(wire::REQUEST_MAGIC);
    b.u64s("header.u64", 0, &[7, 9, 2]);
    b.u32s("header.u32", 0, &[0, 4, 1, 0, 0, 0, 0, 0, 0]);
    assert!(Request::decode(&b.finish()).is_err());
}
#[test]
fn serialized_retry_is_identical_style_refresh_and_poll_peek() {
    let mut s = opened();
    let render = request(2, 0, wire::RENDER, |_| {});
    let before = s.execute(&render, 0, None).unwrap().to_vec();
    let rev = header_of(&before)[0];
    let select = request(3, rev, 11, |b| {
        b.bytes(
            "refs.bytes",
            0,
            &wire::encode_refs(&[ElementRef::Node(id(1))]).unwrap(),
        )
    });
    let first = s.execute(&select, 0, None).unwrap().to_vec();
    assert_eq!(header_of(&first)[0], rev);
    assert_ne!(first, before);
    assert_eq!(s.execute(&select, 0, None).unwrap(), first);
    assert_eq!(s.session().pending_outbound().unwrap().revision, 1);
    assert_eq!(
        s.execute(&request(3, rev, 4, |_| {}), 0, None),
        Err(InteractionStatus::Invalid)
    );
    let poll = request(4, rev, wire::POLL, |_| {});
    let required = s.poll(&poll, 0, 0).unwrap();
    assert!(required > 0);
    assert!(s.session().pending_outbound().is_some());
    assert_eq!(s.poll(&poll, required - 1, 0).unwrap(), required);
    assert!(s.session().pending_outbound().is_some());
    assert_eq!(s.poll(&poll, required, 0).unwrap(), required);
    let bytes = s.reply().to_vec();
    assert!(s.session().pending_outbound().is_none());
    assert_eq!(s.poll(&poll, required, 0).unwrap(), required);
    assert_eq!(s.reply(), bytes);
    let focus = request(5, rev, 6, |b| {
        b.bytes(
            "refs.bytes",
            0,
            &wire::encode_refs(&[ElementRef::Node(id(2))]).unwrap(),
        )
    });
    let focused = s.execute(&focus, 0, None).unwrap().to_vec();
    let c = Container::decode(&focused, wire::RESULT_MAGIC).unwrap();
    assert_eq!(header_of(&focused)[0], rev);
    assert_eq!(c.get("render.emphasis.u8", 0).unwrap().payload, &[0, 1, 0]);
    assert!(c
        .get("summary.text.utf8", 0)
        .unwrap()
        .as_utf8("summary.text.utf8")
        .unwrap()
        .starts_with("Node "));
}
#[test]
fn update_failed_geometry_and_resource_refusals_keep_all_live_state_and_sequence() {
    let mut s = opened();
    let rendered = s
        .execute(&request(2, 0, wire::RENDER, |_| {}), 0, None)
        .unwrap()
        .to_vec();
    let rev = header_of(&rendered)[0];
    let old_positions = s.session().positions().unwrap().0.to_vec();
    let update = request(3, rev, wire::UPDATE, |b| {
        b.bytes("document.bytes", 0, &standard_doc());
        b.f64s("load.x.f64", 0, &[-1e308, 1e308, 0.]);
        b.f64s("load.y.f64", 0, &[0., 0., 0.]);
    });
    assert_eq!(s.execute(&update, 0, None), Err(InteractionStatus::Invalid));
    assert_eq!(s.session().positions().unwrap().0, old_positions);
    assert_eq!(s.reply(), rendered);
    assert_eq!(s.session().render_revision(), rev);
    let select = request(3, rev, 11, |b| {
        b.bytes(
            "refs.bytes",
            0,
            &wire::encode_refs(&[ElementRef::Node(id(1))]).unwrap(),
        )
    });
    let max = s.max_bytes;
    s.max_bytes = s.retained_budget();
    assert_eq!(s.execute(&select, 0, None), Err(InteractionStatus::Budget));
    assert!(s.session().selection().unwrap().is_empty());
    assert_eq!(s.reply(), rendered);
    s.max_bytes = max;
    s.execute(&select, 0, None).unwrap();
    assert_eq!(s.session().pending_outbound().unwrap().revision, 1);
}
#[test]
fn bound_wire_captures_one_world_and_disposal_revokes_retries_unbind_recovers() {
    let doc = handmade(
        &[id(1), id(2), id(3)],
        &[E::Persisted(id(11)), E::Persisted(id(12))],
        &[],
    );
    let projection = GraphProjection::new(
        &[id(1), id(2), id(3)],
        &[id(11), id(12)],
        &[id(1), id(2)],
        &[id(2), id(3)],
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
    let host = Arc::new(Registry {
        graph: Mutex::new(Some(graph)),
    });
    let mut s = WireSession::open(&open_doc(&doc), wire::DEFAULT_MAX_BYTES, 0).unwrap();
    let bind = request(2, 0, 18, |b| b.u64s("temporal.u64", 0, &[1]));
    s.execute(&bind, 0, Some((host.clone(), TemporalHandle(1))))
        .unwrap();
    assert!(s.session().is_bound());
    let rev = s.session().render_revision();
    let select = request(3, rev, 11, |b| {
        b.bytes(
            "refs.bytes",
            0,
            &wire::encode_refs(&[ElementRef::Node(id(1))]).unwrap(),
        )
    });
    s.execute(&select, 0, None).unwrap();
    assert!(host
        .graph
        .lock()
        .unwrap()
        .as_ref()
        .unwrap()
        .interaction_state()
        .selection()
        .nodes
        .contains(&id(1)));
    host.graph.lock().unwrap().take();
    assert_eq!(s.execute(&select, 0, None), Err(InteractionStatus::Unbound));
    let unbind = request(4, rev, 18, |b| b.u64s("temporal.u64", 0, &[0]));
    s.execute(&unbind, 0, None).unwrap();
    assert!(!s.session().is_bound());
    assert!(s.session().selection().unwrap().is_empty());
}

#[test]
fn bound_commands_validate_mutate_publish_and_serialize_in_one_owner_access() {
    use std::sync::atomic::{AtomicUsize, Ordering};
    struct Counted {
        owner: Arc<Registry>,
        count: AtomicUsize,
    }
    impl TemporalHost for Counted {
        fn with_graph(&self, h: TemporalHandle, f: &mut dyn FnMut(&mut TemporalGraph)) -> bool {
            self.count.fetch_add(1, Ordering::SeqCst);
            self.owner.with_graph(h, f)
        }
    }
    let owner = temporal(&[id(1), id(2), id(3)]);
    let host = Arc::new(Counted {
        owner,
        count: AtomicUsize::new(0),
    });
    let mut s = opened();
    for (seq, op) in [(2, 18), (3, 4), (4, wire::UPDATE), (5, wire::RENDER)] {
        let rev = s.session().render_revision();
        let request = request(seq, rev, op, |b| match op {
            18 => b.u64s("temporal.u64", 0, &[1]),
            wire::UPDATE => {
                b.bytes("document.bytes", 0, &standard_doc());
                b.f64s("load.x.f64", 0, &[0., 30., 60.]);
                b.f64s("load.y.f64", 0, &[0., 0., 0.]);
            }
            _ => {}
        });
        host.count.store(0, Ordering::SeqCst);
        s.execute(
            &request,
            0,
            if op == 18 {
                Some((host.clone(), TemporalHandle(1)))
            } else {
                None
            },
        )
        .unwrap();
        assert_eq!(host.count.load(Ordering::SeqCst), 1, "operation {op}");
    }
    let bad = request(6, s.session().render_revision(), 17, |b| {
        b.u32s("companion.u32", 0, &[u32::MAX, 200])
    });
    assert!(Request::decode(&bad).is_err());
}

#[test]
fn present_empty_update_preserves_identity_and_malformed_update_rolls_back() {
    // Reader and transport preserve present-empty independently of absence.
    let document = handmade(
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
        &[Some("")],
    );
    let mut typed = GraphSession::create(&standard_doc(), SessionLoad::default(), 7).unwrap();
    typed
        .update(header(&typed, 1), &document, SessionLoad::default())
        .unwrap();
    typed.render(None).unwrap(); // typed mutation/publication succeeds
    let mut s = opened();
    let first = s
        .execute(&request(2, 0, wire::RENDER, |_| {}), 0, None)
        .unwrap()
        .to_vec();
    let rev = s.session().render_revision();
    let select = request(3, rev, 11, |b| {
        b.bytes(
            "refs.bytes",
            0,
            &wire::encode_refs(&[ElementRef::Node(id(1))]).unwrap(),
        )
    });
    s.execute(&select, 0, None).unwrap();
    let cache = s.reply().to_vec();
    let published = s.session().published().unwrap().clone();
    let pending = s.session().pending_outbound().cloned();
    let update = request(4, rev, wire::UPDATE, |b| {
        b.bytes("document.bytes", 0, &document);
        b.f64s("load.x.f64", 0, &[0., 30., 60.]);
        b.f64s("load.y.f64", 0, &[0., 0., 0.]);
    });
    let mut malformed = update.clone();
    malformed[24] = 1; // container reserved field, truly malformed
    assert_eq!(
        s.execute(&malformed, 0, None),
        Err(InteractionStatus::Invalid)
    );
    assert_eq!(s.reply(), cache);
    assert_eq!(s.session().published(), Some(&published));
    assert_eq!(s.session().pending_outbound(), pending.as_ref());
    assert_eq!(
        s.session().selection().unwrap(),
        vec![ElementRef::Node(id(1))]
    );
    s.execute(&update, 0, None).unwrap();
    let updated = s.session().render_revision();
    assert!(wire::decode_refs(Container::decode(s.reply(),wire::RESULT_MAGIC).unwrap().get("candidates.bytes",0).unwrap().payload).unwrap().iter().any(|r|matches!(r,ElementRef::Derived(DerivedRef{result:ResultRef::Exact(Some(id)),..}) if id.is_empty())));
    s.execute(&request(5, updated, 4, |_| {}), 0, None).unwrap();
    assert!(s.session().selection().unwrap().is_empty());
    assert_ne!(s.reply(), first);
}

#[test]
fn summary_reports_aggregate_membership_from_the_publication() {
    let opening = request(1, 0, wire::OPEN, |b| {
        b.bytes("document.bytes", 0, &standard_doc());
        b.f64s("load.x.f64", 0, &[0., 30., 60.]);
        b.f64s("load.y.f64", 0, &[0., 0., 0.]);
        b.u64s("load.budgets.u64", 0, &[1, 500_000]);
    });
    let mut s = WireSession::open(&opening, wire::DEFAULT_MAX_BYTES, 0).unwrap();
    s.execute(&request(2, 0, wire::RENDER, |_| {}), 0, None)
        .unwrap();
    let rev = s.session().render_revision();
    let focused = request(3, rev, 6, |b| {
        b.bytes(
            "refs.bytes",
            0,
            &wire::encode_refs(&[ElementRef::Node(id(1))]).unwrap(),
        )
    });
    let reply = s.execute(&focused, 0, None).unwrap();
    let c = Container::decode(reply, wire::RESULT_MAGIC).unwrap();
    let summary = c
        .get("summary.text.utf8", 0)
        .unwrap()
        .as_utf8("summary.text.utf8")
        .unwrap();
    assert!(summary.starts_with("Group "), "{summary}");
    assert!(summary.contains("group of 3"), "{summary}");
}

#[test]
fn changed_plane_roundtrips_the_full_20000_symmetric_difference_but_ingress_stays_capped() {
    let nodes = (1..=20_000).map(id).collect::<Vec<_>>();
    let document = handmade(&nodes, &[], &[]);
    let opening = request(1, 0, wire::OPEN, |b| {
        b.bytes("document.bytes", 0, &document);
        b.f64s(
            "load.x.f64",
            0,
            &(0..nodes.len()).map(|i| i as f64).collect::<Vec<_>>(),
        );
        b.f64s("load.y.f64", 0, &vec![0.; nodes.len()]);
    });
    let mut s = WireSession::open(&opening, wire::DEFAULT_MAX_BYTES, 0).unwrap();
    s.execute(&request(2, 0, wire::RENDER, |_| {}), 0, None)
        .unwrap();
    let rev = s.session().render_revision();
    s.execute(
        &request(3, rev, 10, |b| b.uuids("uuids.uuid", 0, &nodes[..10_000])),
        0,
        None,
    )
    .unwrap();
    let reply = s
        .execute(
            &request(4, rev, 10, |b| b.uuids("uuids.uuid", 0, &nodes[10_000..])),
            0,
            None,
        )
        .unwrap();
    let c = Container::decode(reply, wire::RESULT_MAGIC).unwrap();
    let changed = wire::decode_refs(c.get("changed.refs.bytes", 0).unwrap().payload).unwrap();
    assert_eq!(changed.len(), 20_000);
    assert_eq!(s.session().selection().unwrap().len(), 10_000);
    let excessive = request(5, rev, 11, |b| {
        b.bytes("refs.bytes", 0, &wire::encode_refs(&changed).unwrap())
    });
    assert!(matches!(
        Request::decode(&excessive),
        Err(InteractionStatus::SelectionTooLarge)
    ));
}

#[test]
fn review_paint_reply_and_default_arena() {
    let mut s = WireSession::open(&open_doc(&standard_doc()), 16 * 1024 * 1024, 0).unwrap();
    let reply = s
        .execute(&request(2, 0, wire::RENDER, |_| {}), 0, None)
        .unwrap();
    let c = Container::decode(reply, wire::RESULT_MAGIC).unwrap();
    assert!(c.get("paint.node.center.f64", 0).is_some());
    assert_eq!(
        wire::decode_paint(reply).unwrap(),
        s.session().published().unwrap().paint
    );
    let rev = s.session().render_revision();
    s.execute(&request(3, rev, 4, |_| {}), 0, None).unwrap();
}

#[test]
fn review_exact_utf8_ids_survive_publication() {
    for result in [
        None,
        Some(""),
        Some("résumé with spaces"),
        Some("x".repeat(129).as_str()),
    ] {
        let doc = handmade(
            &[id(1), id(2), id(3)],
            &[E::Overlay {
                layer: 0,
                path: 0,
                order: 0,
            }],
            &[result],
        );
        let mut s = WireSession::open(&open_doc(&doc), wire::DEFAULT_MAX_BYTES, 0).unwrap();
        s.execute(&request(2, 0, wire::RENDER, |_| {}), 0, None)
            .unwrap();
    }
}

#[test]
fn review_resolved_paint_roundtrip_routes_frames_aggregate_and_style_refresh() {
    let base = handmade_ends(
        COMPOSITION_VERSION,
        &[id(1), id(2), id(3)],
        &[
            E::Persisted(id(11)),
            E::Persisted(id(12)),
            E::Persisted(id(13)),
            E::Persisted(id(14)),
        ],
        &[],
        Some((&[0, 0, 0], &[0, 1, 1])),
        Some(&[(0, 1), (0, 1), (1, 1), (1, 2)]),
    );
    let mut b = Builder::new(DOCUMENT_MAGIC);
    b.extend_from(&Container::decode(&base, DOCUMENT_MAGIC).unwrap());
    b.u8s("node.class", 0, &[1, 2, 3]);
    b.u8s("node.epistemic", 0, &[1, 2, 3]);
    b.u8s("graph.directed", 0, &[1]);
    let doc = b.finish();
    let mut s = WireSession::open(&open_doc(&doc), wire::DEFAULT_MAX_BYTES, 0).unwrap();
    let bytes = s
        .execute(
            &request(2, 0, wire::RENDER, |b| {
                b.f64s("camera.f64", 0, &[1., 100., 20., 100., 200., 200., 2.])
            }),
            0,
            None,
        )
        .unwrap()
        .to_vec();
    let paint = wire::decode_paint(&bytes).unwrap();
    assert_eq!(paint, s.session().published().unwrap().paint);
    assert!(paint.pieces.iter().any(|p| p.head.is_some()));
    assert!(paint.pieces.iter().filter(|p| p.edge == 2).count() > 1);
    assert!(!paint.frames.is_empty());
    assert_ne!(paint.pieces[0].start, paint.pieces[1].start);
    let rev = s.session().render_revision();
    let selected = s
        .execute(
            &request(3, rev, 11, |b| {
                b.bytes(
                    "refs.bytes",
                    0,
                    &wire::encode_refs(&[ElementRef::Node(id(2))]).unwrap(),
                )
            }),
            0,
            None,
        )
        .unwrap()
        .to_vec();
    assert_eq!(header_of(&selected)[0], rev);
    assert_eq!(
        wire::decode_paint(&selected).unwrap(),
        s.session().published().unwrap().paint
    );
    assert_ne!(wire::decode_paint(&selected).unwrap(), paint);
    let mut malformed = bytes.clone();
    let c = Container::decode(&bytes, wire::RESULT_MAGIC).unwrap();
    let section = c.get("paint.node.style.bytes", 0).unwrap();
    let off = section.payload.as_ptr() as usize - bytes.as_ptr() as usize;
    malformed[off + 57] = 1;
    assert_eq!(
        wire::decode_paint(&malformed),
        Err(InteractionStatus::Invalid)
    );
    let opening = request(1, 0, wire::OPEN, |b| {
        b.bytes("document.bytes", 0, &doc);
        b.f64s("load.x.f64", 0, &[0., 0.1, 60.]);
        b.f64s("load.y.f64", 0, &[0.; 3]);
        b.u64s("load.budgets.u64", 0, &[2, 100]);
    });
    let mut s = WireSession::open(&opening, wire::DEFAULT_MAX_BYTES, 0).unwrap();
    let reply = s
        .execute(&request(2, 0, wire::RENDER, |_| {}), 0, None)
        .unwrap()
        .to_vec();
    let render = s.session().published().unwrap();
    assert_eq!(render.tier, crate::graph::LodTier::Aggregate);
    assert!(render
        .node_member_offsets
        .windows(2)
        .any(|w| w[1] - w[0] == 1));
    assert_eq!(wire::decode_paint(&reply).unwrap(), render.paint);
    assert!(render.paint.frames.is_empty());
}

#[test]
fn review_live_owner_stamp_rebind_unbind_and_cross_owner_interleaving() {
    let host = temporal(&[id(1), id(2), id(3)]);
    let mut s = opened();
    s.execute(
        &request(2, 0, 18, |b| b.u64s("temporal.u64", 0, &[1])),
        0,
        Some((host.clone(), HANDLE)),
    )
    .unwrap();
    let old = s.reply().to_vec();
    let rev = s.session().render_revision();
    frame(&host, 1);
    for handle in [1, 0] {
        let command = request(3, rev, 18, |b| b.u64s("temporal.u64", 0, &[handle]));
        assert_eq!(
            s.execute(&command, 0, Some((host.clone(), HANDLE))),
            Err(InteractionStatus::Stale)
        );
        assert_eq!(s.reply(), old);
        assert_eq!(s.session().render_revision(), rev);
        assert!(s.session().is_bound());
    }
    s.execute(&request(3, rev, wire::RENDER, |_| {}), 0, None)
        .unwrap();
    let rev = s.session().render_revision();
    s.execute(
        &request(4, rev, 18, |b| b.u64s("temporal.u64", 0, &[1])),
        0,
        Some((host.clone(), HANDLE)),
    )
    .unwrap();
    let rev = s.session().render_revision();
    struct Interleaved {
        target: Arc<Registry>,
        old: Arc<Registry>,
    }
    impl TemporalHost for Interleaved {
        fn with_graph(&self, h: TemporalHandle, f: &mut dyn FnMut(&mut TemporalGraph)) -> bool {
            frame(&self.old, 2);
            self.target.with_graph(h, f)
        }
    }
    let target = temporal(&[id(1), id(2), id(3)]);
    let next = Arc::new(Interleaved {
        target: target.clone(),
        old: host.clone(),
    });
    let prior = s.reply().to_vec();
    let change = request(5, rev, 18, |b| b.u64s("temporal.u64", 0, &[1]));
    assert_eq!(
        s.execute(&change, 0, Some((next, HANDLE))),
        Err(InteractionStatus::Stale)
    );
    assert_eq!(s.reply(), prior);
    assert!(s.session().is_bound());
    s.execute(&request(5, rev, wire::RENDER, |_| {}), 0, None)
        .unwrap();
    let rev = s.session().render_revision();
    s.execute(
        &request(6, rev, 18, |b| b.u64s("temporal.u64", 0, &[1])),
        0,
        Some((target.clone(), HANDLE)),
    )
    .unwrap();
    frame(&target, 3);
    let rev = s.session().render_revision();
    assert_eq!(
        s.execute(
            &request(7, rev, 18, |b| b.u64s("temporal.u64", 0, &[0])),
            0,
            None
        ),
        Err(InteractionStatus::Stale)
    );
    s.execute(&request(7, rev, wire::RENDER, |_| {}), 0, None)
        .unwrap();
    let rev = s.session().render_revision();
    s.execute(
        &request(8, rev, 18, |b| b.u64s("temporal.u64", 0, &[0])),
        0,
        None,
    )
    .unwrap();
    assert!(!s.session().is_bound());
}

#[test]
fn review_long_text_pressure_is_atomic_and_counts_repeated_ids() {
    let text = "é".repeat(32_768);
    let doc = handmade(
        &[id(1), id(2), id(3)],
        &[E::Overlay {
            layer: 0,
            path: 0,
            order: 0,
        }],
        &[Some(&text)],
    );
    let bytes = open_doc(&doc);
    assert!(matches!(
        WireSession::open(&bytes, 16 * 1024 * 1024, 0),
        Err(InteractionStatus::Budget)
    ));
    let mut s = opened();
    s.execute(&request(2, 0, wire::RENDER, |_| {}), 0, None)
        .unwrap();
    let old = s.reply().to_vec();
    let rev = s.session().render_revision();
    s.max_bytes = 16 * 1024 * 1024;
    let update = request(3, rev, wire::UPDATE, |b| {
        b.bytes("document.bytes", 0, &doc);
        b.f64s("load.x.f64", 0, &[0., 30., 60.]);
        b.f64s("load.y.f64", 0, &[0.; 3]);
    });
    assert_eq!(s.execute(&update, 0, None), Err(InteractionStatus::Budget));
    assert_eq!(s.reply(), old);
    s.execute(&request(3, rev, 4, |_| {}), 0, None).unwrap();
    let mut b = Builder::new(DOCUMENT_MAGIC);
    b.extend_from(&Container::decode(&standard_doc(), DOCUMENT_MAGIC).unwrap());
    // Per-row expanded dictionary labels, charged at all three occurrences.
    b.texts("node.label", 0, &[text.as_str(); 3]);
    assert!(matches!(
        WireSession::open(&open_doc(&b.finish()), 16 * 1024 * 1024, 0),
        Err(InteractionStatus::Budget)
    ));
}
#[test]
fn review_style_publication_distinguishes_classes() {
    let mut replies = Vec::new();
    for class in [0, 1] {
        let doc = handmade(&[id(1), id(2), id(3)], &[], &[]);
        let mut b = Builder::new(DOCUMENT_MAGIC);
        b.extend_from(&Container::decode(&doc, DOCUMENT_MAGIC).unwrap());
        b.u8s("node.class", 0, &[class; 3]);
        let mut s = WireSession::open(&open_doc(&b.finish()), wire::DEFAULT_MAX_BYTES, 0).unwrap();
        replies.push(
            s.execute(&request(2, 0, wire::RENDER, |_| {}), 0, None)
                .unwrap()
                .to_vec(),
        );
    }
    assert_ne!(replies[0], replies[1]);
}

#[test]
fn review_open_charge_has_a_tight_atomic_boundary() {
    let bytes = open_doc(&standard_doc());
    let (mut low, mut high) = (0, 16 * 1024 * 1024);
    while high - low > 1 {
        let mid = (high + low) / 2;
        match WireSession::open(&bytes, mid, 0) {
            Ok(_) => high = mid,
            Err(InteractionStatus::Budget) => low = mid,
            Err(error) => panic!("unexpected {error:?}"),
        }
    }
    assert!(matches!(
        WireSession::open(&bytes, high - 1, 0),
        Err(InteractionStatus::Budget)
    ));
    assert!(WireSession::open(&bytes, high, 0).is_ok());
    println!(
        "three-node/three-edge open minimum admitted bytes={high}; browser default={}",
        16 * 1024 * 1024
    );
}

#[test]
fn review_uuid_text_preserves_all_32_lowercase_hex_bytes_including_zeros() {
    // This pins the byte contract before either authorized size experiment.
    let node = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 255];
    let doc = handmade(&[node], &[], &[]);
    let opening = request(1, 0, wire::OPEN, |b| {
        b.bytes("document.bytes", 0, &doc);
        b.f64s("load.x.f64", 0, &[0.]);
        b.f64s("load.y.f64", 0, &[0.]);
    });
    let mut s = WireSession::open(&opening, wire::DEFAULT_MAX_BYTES, 0).unwrap();
    let reply = s
        .execute(&request(2, 0, wire::RENDER, |_| {}), 0, None)
        .unwrap();
    let c = Container::decode(reply, wire::RESULT_MAGIC).unwrap();
    let text = c
        .get("companion.text.utf8", 0)
        .unwrap()
        .as_utf8("companion.text.utf8")
        .unwrap();
    assert_eq!(
        text,
        "Node\t000102030405060708090a0b0c0d0eff\t\t0 relationships\tnot selected"
    );
}

#[test]
fn review_bound_state_text_absent_from_document_is_admitted_under_owner_lock() {
    let host = temporal(&[id(1), id(2), id(3)]);
    let mut s = opened();
    s.execute(
        &request(2, 0, 18, |b| b.u64s("temporal.u64", 0, &[1])),
        0,
        Some((host.clone(), HANDLE)),
    )
    .unwrap();
    let mut foreign = ElementSet::default();
    foreign.derived.insert(DerivedKey {
        result_id: Some("λ".repeat(100_000).into_boxed_str()),
        layer: 900,
        path: 0,
        order: 0,
    });
    host.graph
        .lock()
        .unwrap()
        .as_mut()
        .unwrap()
        .interaction_state_mut()
        .select(SelectMode::Replace, &foreign)
        .unwrap();
    let rev = s.session().render_revision();
    let old = s.reply().to_vec();
    s.max_bytes = 16 * 1024 * 1024;
    let clear = request(3, rev, 4, |_| {});
    assert_eq!(s.execute(&clear, 0, None), Err(InteractionStatus::Budget));
    assert_eq!(s.reply(), old);
    assert_eq!(
        host.graph
            .lock()
            .unwrap()
            .as_ref()
            .unwrap()
            .interaction_state()
            .selection(),
        &foreign
    );
    host.graph
        .lock()
        .unwrap()
        .as_mut()
        .unwrap()
        .interaction_state_mut()
        .clear();
    s.execute(&clear, 0, None).unwrap(); // no premature sequence or delivery
    assert_eq!(s.session().pending_outbound().unwrap().revision, 1);
}
