//! Bounded P1 projection and retained progressive checkpoint proofs.
use super::*;

fn edit_doc(doc: &[u8], omit: &[&str], extra: impl FnOnce(&mut Builder)) -> Vec<u8> {
    let mut c = Container::decode(doc, DOCUMENT_MAGIC).unwrap();
    c.sections.retain(|(name, _, _)| !omit.contains(name));
    let mut b = Builder::new(DOCUMENT_MAGIC);
    b.extend_from(&c);
    extra(&mut b);
    b.finish()
}
fn values(c: &Container<'_>, name: &str) -> Vec<u64> {
    c.get(name, 0).unwrap().as_u64(name).unwrap()
}
fn selected(c: &Container<'_>) -> Vec<ElementRef> {
    wire::decode_refs(c.get("selection.refs.bytes", 0).unwrap().payload).unwrap()
}
fn select_request(seq: u64, rev: u32, mode: u32, refs: &[ElementRef]) -> Vec<u8> {
    let mut b = Builder::new(wire::REQUEST_MAGIC);
    b.u64s("header.u64", 0, &[7, 9, seq]);
    b.u32s("header.u32", 0, &[rev, 11, mode, 0, 0, 0, 0, 0, 0]);
    b.bytes("refs.bytes", 0, &wire::encode_refs(refs).unwrap());
    b.finish()
}

#[test]
fn complete_projection_modes_noop_clear_unlinked_and_exact_rows() {
    let long = " id 空白 🦀 ".repeat(600);
    let doc = handmade_ends(
        COMPOSITION_VERSION,
        &[id(3), id(1), id(2)],
        &[
            E::Persisted(id(1)),
            E::Persisted(id(12)),
            E::Overlay {
                layer: 0,
                path: 4,
                order: 0,
            },
            E::Pair {
                layer: 3,
                row: (1u64 << 60) + 3,
            },
        ],
        &[None, Some(""), Some("λ result 🦀"), Some(&long)],
        None,
        Some(&[(0, 1), (0, 1), (1, 1), (1, 2)]),
    );
    let doc = edit_doc(&doc, &["layer.node_rows", "layer.edge_rows"], |b| {
        b.u64s("layer.node_rows", 0, &[u64::MAX, (1u64 << 62) + 1, 42]);
        b.u64s("layer.node_rows", 2, &[3, 4, u64::MAX]);
        b.u64s("layer.edge_rows", 0, &[8, 9, 123, u64::MAX]);
        b.u64s("layer.edge_rows", 1, &[15, u64::MAX, u64::MAX, u64::MAX]);
        b.u64s(
            "layer.edge_rows",
            3,
            &[u64::MAX, u64::MAX, u64::MAX, (1u64 << 60) + 3],
        );
    });
    let mut s = WireSession::open(&open_doc(&doc), wire::DEFAULT_MAX_BYTES, 0).unwrap();
    let all = (0..3)
        .map(|i| s.session().identity().node_ref(i))
        .chain((0..4).map(|i| s.session().identity().edge_ref(i)))
        .map(|r| s.session().identity().to_transport(&r).unwrap())
        .collect::<Vec<_>>();
    let render = s
        .execute(&request(2, 0, wire::RENDER, |_| {}), 0, None)
        .unwrap()
        .to_vec();
    let rev = header_of(&render)[0];
    let c = Container::decode(&render, wire::RESULT_MAGIC).unwrap();
    assert!(selected(&c).is_empty());
    assert_eq!(values(&c, "selection.layer_offsets.u64"), [0]);
    for (seq, mode, input, expected) in [
        (3, 0, all.clone(), 7),
        (4, 0, all.clone(), 7),
        (5, 2, vec![all[0].clone()], 6),
        (6, 1, vec![all[0].clone()], 7),
    ] {
        let req = select_request(seq, rev, mode, &input);
        let reply = s.execute(&req, 0, None).unwrap().to_vec();
        assert_eq!(s.execute(&req, 0, None).unwrap(), reply);
        let c = Container::decode(&reply, wire::RESULT_MAGIC).unwrap();
        let refs = selected(&c);
        assert_eq!(refs.len(), expected);
        assert!(refs
            .windows(2)
            .all(|p| super::super::super::coordination::compare(&p[0], &p[1]).is_lt()));
        assert!(refs.iter().all(|r| !matches!(
            r,
            ElementRef::Derived(DerivedRef {
                result: ResultRef::Local(_),
                ..
            }) | ElementRef::Aggregate(_)
        )));
        let indices = values(&c, "selection.indices.u64");
        for (r, index) in refs.iter().zip(indices) {
            assert_eq!(
                match s.session().identity().resolve(r).unwrap() {
                    ElementIndex::Node(i) | ElementIndex::Edge(i) => i as u64,
                },
                index
            );
        }
        let ids = c
            .get("selection.result_ids.texts", 0)
            .unwrap()
            .as_texts("ids")
            .unwrap();
        assert_eq!(ids, ["", "", "λ result 🦀", &long]);
        assert_eq!(
            c.get("selection.result_ids.valid.u8", 0).unwrap().payload,
            [0, 1, 1, 1]
        );
        let offsets = values(&c, "selection.layer_offsets.u64");
        let rows = values(&c, "selection.rows.u64");
        if seq == 3 {
            assert_eq!(offsets, [0, 2, 3, 4, 6, 7, 8, 9]);
            assert_eq!(
                rows,
                [(1u64 << 62) + 1, 4, 42, 3, 8, 15, 9, 123, (1u64 << 60) + 3]
            );
            assert_eq!(
                c.get("selection.layers.u32", 0)
                    .unwrap()
                    .as_u32("layers")
                    .unwrap(),
                [0, 2, 0, 2, 0, 1, 0, 0, 3]
            );
        }
        assert_eq!(*offsets.last().unwrap(), rows.len() as u64);
        assert!(!rows.contains(&u64::MAX));
        assert!(rows.contains(&((1u64 << 60) + 3)));
        if seq == 4 {
            assert!(
                wire::decode_refs(c.get("changed.refs.bytes", 0).unwrap().payload)
                    .unwrap()
                    .is_empty()
            );
        }
    }
    let clear = s.execute(&request(7, rev, 4, |_| {}), 0, None).unwrap();
    let c = Container::decode(clear, wire::RESULT_MAGIC).unwrap();
    assert!(selected(&c).is_empty());
    assert_eq!(values(&c, "selection.layer_offsets.u64"), [0]);
    // Group zero publishes the identical full snapshot without an outbound event.
    let mut unlinked = open_doc(&doc);
    // Header payload is located generically; no fixed container offsets.
    let c = Container::decode(&unlinked, wire::REQUEST_MAGIC).unwrap();
    let at = c.get("header.u64", 0).unwrap().payload.as_ptr() as usize - unlinked.as_ptr() as usize;
    unlinked[at + 8..at + 16].fill(0);
    let mut u = WireSession::open(&unlinked, wire::DEFAULT_MAX_BYTES, 0).unwrap();
    assert_eq!(u.session().group_id(), 0);
    let mut req = select_request(2, 0, 0, &all);
    let c = Container::decode(&req, wire::REQUEST_MAGIC).unwrap();
    let at = c.get("header.u64", 0).unwrap().payload.as_ptr() as usize - req.as_ptr() as usize;
    req[at + 8..at + 16].fill(0);
    let c = Container::decode(u.execute(&req, 0, None).unwrap(), wire::RESULT_MAGIC).unwrap();
    assert_eq!(selected(&c).len(), 7);
    assert!(c.get("outbound.bytes", 0).is_none());
}

#[test]
fn projection_update_uses_replacement_rows_and_malformed_planes_rollback() {
    let mut s = opened();
    let refs = [ElementRef::Node(id(1))];
    let reply = s
        .execute(&select_request(2, 0, 0, &refs), 0, None)
        .unwrap()
        .to_vec();
    let rev = header_of(&reply)[0];
    let replacement = edit_doc(&standard_doc(), &["layer.node_rows"], |b| {
        b.u64s("layer.node_rows", 0, &[999, u64::MAX, u64::MAX])
    });
    let update = request(3, rev, wire::UPDATE, |b| {
        b.bytes("document.bytes", 0, &replacement);
        b.f64s("load.x.f64", 0, &[0., 30., 60.]);
        b.f64s("load.y.f64", 0, &[0., 0., 0.]);
    });
    let reply = s.execute(&update, 0, None).unwrap().to_vec();
    let c = Container::decode(&reply, wire::RESULT_MAGIC).unwrap();
    assert_eq!(selected(&c), refs);
    assert_eq!(values(&c, "selection.rows.u64"), [999]);
    let rev = header_of(&reply)[0];
    for malformed in [
        edit_doc(&replacement, &["layer.node_rows"], |b| {
            b.u32s("layer.node_rows", 0, &[1, 2, 3])
        }),
        edit_doc(&replacement, &["layer.node_rows"], |b| {
            b.u64s("layer.node_rows", 0, &[1])
        }),
        edit_doc(&replacement, &[], |b| {
            b.u64s("layer.node_rows", 7, &[1, 2, 3])
        }),
    ] {
        let req = request(4, rev, wire::UPDATE, |b| {
            b.bytes("document.bytes", 0, &malformed)
        });
        assert_eq!(s.execute(&req, 0, None), Err(InteractionStatus::Invalid));
        assert_eq!(s.reply(), reply);
        assert_eq!(s.session().selection().unwrap().len(), 1);
        assert_eq!(s.session().render_revision(), rev);
    }
    let req = request(4, rev, 4, |_| {});
    let max = s.max_bytes;
    s.max_bytes = s.retained_budget();
    assert_eq!(s.execute(&req, 0, None), Err(InteractionStatus::Budget));
    assert_eq!(s.reply(), reply);
    s.max_bytes = max;
    let bytes = s.execute(&req, 0, None).unwrap().to_vec();
    assert_eq!(s.execute(&req, 0, None).unwrap(), bytes);
}

fn step_request(seq: u64, rev: u32, steps: u32) -> Vec<u8> {
    let mut b = Builder::new(wire::REQUEST_MAGIC);
    b.u64s("header.u64", 0, &[7, 9, seq]);
    b.u32s("header.u32", 0, &[rev, 15, 0, 0, 0, 0, 0, steps, 0]);
    b.finish()
}
fn assert_positions(s: &GraphSession, force: &crate::graph::ForceState) {
    let (x, y) = s.positions().unwrap();
    assert_eq!(
        x.iter().map(|v| v.to_bits()).collect::<Vec<_>>(),
        force.x.iter().map(|v| v.to_bits()).collect::<Vec<_>>()
    );
    assert_eq!(
        y.iter().map(|v| v.to_bits()).collect::<Vec<_>>(),
        force.y.iter().map(|v| v.to_bits()).collect::<Vec<_>>()
    );
}
fn progress(bytes: &[u8]) -> (u64, f64) {
    let c = Container::decode(bytes, wire::RESULT_MAGIC).unwrap();
    (
        values(&c, "relayout.steps.u64")[0],
        c.get("relayout.alpha.f64", 0)
            .unwrap()
            .as_f64("alpha")
            .unwrap()[0],
    )
}

#[test]
fn progressive_first_paint_and_chunks_share_configured_force_checkpoint_with_pins_and_parents() {
    use crate::graph::{CoseOptions, ForceState, LAYOUT_COSE};
    let doc = handmade_with(
        COMPOSITION_VERSION,
        &[id(1), id(2), id(3)],
        &[E::Persisted(id(11)), E::Persisted(id(12))],
        &[],
        Some((&[0, 0, 0], &[0, 1, 1])),
    );
    let opts = CoseOptions {
        ideal_edge_length: 2.,
        repulsion_strength: 0.7,
        gravity_strength: 0.02,
        cooling_factor: 0.97,
        overlap_padding: 0.15,
        component_spacing: 3.,
        bounds: Some([-20., -20., 20., 20.]),
    };
    for authored in [false, true] {
        for pinned in [false, true] {
            let opening = request(1, 0, wire::OPEN, |b| {
                b.bytes("document.bytes", 0, &doc);
                b.u8s("load.progressive.u8", 0, &[1]);
                b.u64s("load.seed.u64", 0, &[73]);
                b.u8s("load.pinned.u8", 0, &[0, u8::from(pinned), 0]);
                b.f64s("load.cose.f64", 0, &[2., 0.7, 0.02, 0.97, 0.15, 3.]);
                b.f64s("load.cose.bounds.f64", 0, &[-20., -20., 20., 20.]);
                if authored {
                    b.f64s("load.x.f64", 0, &[-2., 0., 2.]);
                    b.f64s("load.y.f64", 0, &[0., 1., 0.]);
                }
            });
            let mut s = WireSession::open(&opening, wire::DEFAULT_MAX_BYTES, 0).unwrap();
            assert!(s.session().positions().is_none() == !authored);
            let mut expected = ForceState::new_configured(
                3,
                &[0, 1],
                &[1, 2],
                if authored { Some(&[-2., 0., 2.]) } else { None },
                if authored { Some(&[0., 1., 0.]) } else { None },
                73,
                LAYOUT_COSE,
                opts,
                if authored && pinned { &[0, 1, 0] } else { &[] },
                &[COSE_NO_PARENT, 0, 0],
            )
            .unwrap();
            if !authored {
                expected.tick(1);
                expected.pinned[1] = pinned;
            }
            let first = s
                .execute(&request(2, 0, wire::RENDER, |_| {}), 0, None)
                .unwrap()
                .to_vec();
            if authored {
                assert_eq!(s.session().positions().unwrap().0, [-2., 0., 2.]);
                assert!(Container::decode(&first, wire::RESULT_MAGIC)
                    .unwrap()
                    .get("relayout.steps.u64", 0)
                    .is_none());
            } else {
                assert_positions(s.session(), &expected);
                assert_eq!(progress(&first), (1, expected.alpha));
            }
            // Paint geometry and pick index originate in the same publication.
            let render = s.session().published().unwrap();
            assert_eq!(render.node_x, s.session().positions().unwrap().0);
            let first_x = render.node_x[0];
            let first_y = render.node_y[0];
            let mut rev = header_of(&first)[0];
            let mut seq = 3;
            let hover = request(seq, rev, 0, |b| {
                b.f64s("coordinates.f64", 0, &[first_x, first_y])
            });
            s.execute(&hover, 0, None).unwrap();
            seq += 1;
            s.execute(
                &select_request(seq, rev, 0, &[ElementRef::Node(id(1))]),
                0,
                None,
            )
            .unwrap();
            seq += 1;
            let camera = request(seq, rev, wire::RENDER, |b| {
                b.f64s("camera.f64", 0, &[1., 1., 0., 0., 800., 600., 1.])
            });
            let reply = s.execute(&camera, 0, None).unwrap().to_vec();
            seq += 1;
            rev = header_of(&reply)[0];
            if !authored {
                assert_eq!(progress(&reply).0, 1);
                assert_positions(s.session(), &expected);
            }
            let stale = step_request(seq, rev - 1, 1);
            assert_eq!(s.execute(&stale, 0, None), Err(InteractionStatus::Stale));
            let mut ticks = if authored { 0 } else { 1 };
            for chunk in [1, 7, 16, 64] {
                let req = step_request(seq, rev, chunk);
                let max = s.max_bytes;
                s.max_bytes = s.retained_budget();
                let retained_reply = s.reply().to_vec();
                assert_eq!(s.execute(&req, 0, None), Err(InteractionStatus::Budget));
                assert_eq!(s.reply(), retained_reply);
                s.max_bytes = max;
                expected.tick(chunk);
                ticks += u64::from(chunk);
                let reply = s.execute(&req, 0, None).unwrap().to_vec();
                assert_eq!(s.execute(&req, 0, None).unwrap(), reply);
                assert_positions(s.session(), &expected);
                assert_eq!(progress(&reply), (ticks, expected.alpha));
                rev = header_of(&reply)[0];
                seq += 1;
            }
        }
    }
}

#[test]
fn progressive_load_strictness_and_legacy_zero_keeps_300_seed() {
    let doc = standard_doc();
    for extra in 0..8 {
        let req = request(1, 0, wire::OPEN, |b| {
            b.bytes("document.bytes", 0, &doc);
            match extra {
                0 => b.u8s("load.progressive.u8", 0, &[]),
                1 => b.u8s("load.progressive.u8", 0, &[2]),
                2 => b.u8s("load.progressive.u8", 0, &[1, 0]),
                3 => b.f64s("load.cose.f64", 0, &[1.; 5]),
                4 => b.f64s("load.cose.f64", 0, &[1., 1., 1., 1., 1., 1.]),
                5 => b.f64s("load.cose.f64", 0, &[f64::NAN, 1., 1., 0.9, 1., 1.]),
                6 => b.f64s("load.cose.bounds.f64", 0, &[0., 0., 0., 1.]),
                _ => b.f64s("load.cose.bounds.f64", 0, &[0.; 3]),
            }
        });
        assert!(matches!(
            WireSession::open(&req, wire::DEFAULT_MAX_BYTES, 0),
            Err(InteractionStatus::Invalid)
        ));
    }
    assert!(Request::decode(&request(2, 0, wire::RENDER, |b| b.u8s(
        "load.progressive.u8",
        0,
        &[1]
    )))
    .is_err());
    let render = |progressive: Option<u8>| {
        let req = request(1, 0, wire::OPEN, |b| {
            b.bytes("document.bytes", 0, &doc);
            if let Some(v) = progressive {
                b.u8s("load.progressive.u8", 0, &[v]);
            }
        });
        let mut s = WireSession::open(&req, wire::DEFAULT_MAX_BYTES, 0).unwrap();
        s.execute(&request(2, 0, wire::RENDER, |_| {}), 0, None)
            .unwrap()
            .to_vec()
    };
    assert_eq!(render(None), render(Some(0)));
    let mut force = crate::graph::ForceState::new_configured(
        3,
        &[0, 1, 2],
        &[1, 2, 0],
        None,
        None,
        0,
        crate::graph::LAYOUT_COSE,
        crate::graph::CoseOptions::default(),
        &[],
        &[COSE_NO_PARENT; 3],
    )
    .unwrap();
    force.tick(300);
    let bytes = render(None);
    let c = Container::decode(&bytes, wire::RESULT_MAGIC).unwrap();
    assert_eq!(
        c.get("render.node_x.f64", 0).unwrap().as_f64("x").unwrap(),
        force.x
    );
}

#[test]
fn progressive_pin_move_cancel_and_update_invalidate_checkpoint() {
    let opening = request(1, 0, wire::OPEN, |b| {
        b.bytes("document.bytes", 0, &standard_doc());
        b.u8s("load.progressive.u8", 0, &[1]);
    });
    let mut s = WireSession::open(&opening, wire::DEFAULT_MAX_BYTES, 0).unwrap();
    let first = s
        .execute(&request(2, 0, wire::RENDER, |_| {}), 0, None)
        .unwrap()
        .to_vec();
    let mut rev = header_of(&first)[0];
    let mut b = Builder::new(wire::REQUEST_MAGIC);
    b.u64s("header.u64", 0, &[7, 9, 3]);
    b.u32s("header.u32", 0, &[rev, 13, 0, 0, 0, 1, 0, 0, 0]);
    b.bytes(
        "refs.bytes",
        0,
        &wire::encode_refs(&[ElementRef::Node(id(1))]).unwrap(),
    );
    let reply = s.execute(&b.finish(), 0, None).unwrap().to_vec();
    rev = header_of(&reply)[0];
    assert!(s.session().relayout.is_none());
    let reply = s
        .execute(&step_request(4, rev, 2), 0, None)
        .unwrap()
        .to_vec();
    rev = header_of(&reply)[0];
    assert_eq!(progress(&reply).0, 2);
    let before = s.session().positions().unwrap().0.to_vec();
    for (seq, commit) in [(5, 0), (6, 2)] {
        let mut b = Builder::new(wire::REQUEST_MAGIC);
        b.u64s("header.u64", 0, &[7, 9, seq]);
        b.u32s("header.u32", 0, &[rev, 14, 0, 0, 0, 0, commit, 0, 0]);
        b.bytes(
            "refs.bytes",
            0,
            &wire::encode_refs(&[ElementRef::Node(id(2))]).unwrap(),
        );
        b.f64s("coordinates.f64", 0, &[0.1, 0.1]);
        let reply = s.execute(&b.finish(), 0, None).unwrap().to_vec();
        rev = header_of(&reply)[0];
        assert!(s.session().relayout.is_none());
    }
    assert_eq!(s.session().positions().unwrap().0, before);
    let reply = s
        .execute(&step_request(7, rev, 1), 0, None)
        .unwrap()
        .to_vec();
    rev = header_of(&reply)[0];
    assert_eq!(progress(&reply).0, 1);
    let update = request(8, rev, wire::UPDATE, |b| {
        b.bytes("document.bytes", 0, &standard_doc());
        b.u8s("load.progressive.u8", 0, &[1]);
    });
    let reply = s.execute(&update, 0, None).unwrap().to_vec();
    assert_eq!(progress(&reply).0, 1);
    let rev = header_of(&reply)[0];
    let mut b = Builder::new(wire::REQUEST_MAGIC);
    b.u64s("header.u64", 0, &[7, 9, 9]);
    b.u32s("header.u32", 0, &[rev, 14, 0, 0, 0, 0, 1, 0, 0]);
    b.bytes(
        "refs.bytes",
        0,
        &wire::encode_refs(&[ElementRef::Node(id(2))]).unwrap(),
    );
    b.f64s("coordinates.f64", 0, &[0.1, 0.1]);
    let committed = s.execute(&b.finish(), 0, None).unwrap().to_vec();
    assert!(s.session().relayout.is_none());
    let stepped = s
        .execute(&step_request(10, header_of(&committed)[0], 1), 0, None)
        .unwrap();
    assert_eq!(progress(stepped).0, 1);
}

#[test]
fn completed_steps_stops_at_native_convergence_not_requested_chunks() {
    let opening = request(1, 0, wire::OPEN, |b| {
        b.bytes("document.bytes", 0, &standard_doc());
        b.u8s("load.progressive.u8", 0, &[1]);
        b.f64s("load.cose.f64", 0, &[1., 1., 0.1, 0.1, 0.1, 1.]);
    });
    let mut s = WireSession::open(&opening, wire::DEFAULT_MAX_BYTES, 0).unwrap();
    let first = s
        .execute(&request(2, 0, wire::RENDER, |_| {}), 0, None)
        .unwrap()
        .to_vec();
    let reply = s
        .execute(&step_request(3, header_of(&first)[0], 64), 0, None)
        .unwrap()
        .to_vec();
    assert_eq!(progress(&reply).0, 4); // 0.1^3 > cutoff by binary64 rounding, tick 4 settles.
    let again = s
        .execute(&step_request(4, header_of(&reply)[0], 64), 0, None)
        .unwrap()
        .to_vec();
    assert_eq!(progress(&reply), progress(&again));
}

#[test]
fn progressive_bound_visibility_pins_and_disposal_invalidate_without_consuming_retry() {
    use crate::temporal::{TemporalColumn, TemporalPrecision};
    let ids = [id(1), id(2), id(3)];
    let projection = GraphProjection::new(
        &ids,
        &[id(11), id(12)],
        &[id(1), id(2)],
        &[id(2), id(3)],
        None,
        true,
    )
    .unwrap();
    let valid = [1; 3];
    let starts =
        TemporalColumn::from_utc_micros(&[0, 0, 0], &valid, "UTC", TemporalPrecision::Microsecond)
            .unwrap();
    let ends = TemporalColumn::from_utc_micros(
        &[100, 20, 100],
        &valid,
        "UTC",
        TemporalPrecision::Microsecond,
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
    let host = Arc::new(Registry {
        graph: Mutex::new(Some(graph)),
    });
    let doc = handmade(&ids, &[E::Persisted(id(11)), E::Persisted(id(12))], &[]);
    let opening = request(1, 0, wire::OPEN, |b| {
        b.bytes("document.bytes", 0, &doc);
        b.u8s("load.progressive.u8", 0, &[1]);
    });
    let mut s = WireSession::open(&opening, wire::DEFAULT_MAX_BYTES, 0).unwrap();
    let first = s
        .execute(
            &request(2, 0, 18, |b| b.u64s("temporal.u64", 0, &[1])),
            0,
            Some((host.clone(), TemporalHandle(1))),
        )
        .unwrap()
        .to_vec();
    assert_eq!(progress(&first).0, 1);
    let rev = header_of(&first)[0];
    let reply = s
        .execute(&step_request(3, rev, 4), 0, None)
        .unwrap()
        .to_vec();
    assert_eq!(progress(&reply).0, 5);
    let rev = header_of(&reply)[0];
    {
        let mut guard = host.graph.lock().unwrap();
        let graph = guard.as_mut().unwrap();
        graph
            .frame(
                1,
                20,
                0,
                100,
                &CancelFlag::new(),
                graph.required_budget().unwrap(),
            )
            .unwrap();
    }
    let stale = step_request(4, rev, 1);
    assert_eq!(s.execute(&stale, 0, None), Err(InteractionStatus::Stale));
    assert_eq!(s.reply(), reply);
    let changed = s
        .execute(&request(4, rev, wire::RENDER, |_| {}), 0, None)
        .unwrap()
        .to_vec();
    assert!(s.session().relayout.is_none());
    let rev = header_of(&changed)[0];
    let reply = s
        .execute(&step_request(5, rev, 2), 0, None)
        .unwrap()
        .to_vec();
    assert_eq!(progress(&reply).0, 2);
    let (x, y) = s.session().positions().unwrap();
    assert_eq!(s.session().published().unwrap().node_x, vec![x[0], x[2]]);
    assert!(y.iter().all(|v| v.is_finite()));
    host.graph.lock().unwrap().take();
    let retry = step_request(5, rev, 2);
    assert_eq!(s.execute(&retry, 0, None), Err(InteractionStatus::Unbound));
    assert_eq!(s.reply(), reply);
}

#[test]
fn persisted_parallel_and_loop_selection_keep_distinct_exact_source_rows() {
    let doc = handmade_ends(
        COMPOSITION_VERSION,
        &[id(1), id(2), id(3)],
        &[
            E::Persisted(id(1)),
            E::Persisted(id(12)),
            E::Persisted(id(13)),
        ],
        &[Some("edge rows")],
        None,
        Some(&[(0, 1), (0, 1), (1, 1)]),
    );
    let doc = edit_doc(&doc, &["layer.edge_rows"], |b| {
        b.u64s("layer.edge_rows", 0, &[(1u64 << 63) + 1, 77, 88])
    });
    let mut s = WireSession::open(&open_doc(&doc), wire::DEFAULT_MAX_BYTES, 0).unwrap();
    let req = select_request(
        2,
        0,
        0,
        &[
            ElementRef::Edge(id(13)),
            ElementRef::Edge(id(1)),
            ElementRef::Edge(id(12)),
        ],
    );
    let bytes = s.execute(&req, 0, None).unwrap();
    let c = Container::decode(bytes, wire::RESULT_MAGIC).unwrap();
    assert_eq!(
        selected(&c),
        [
            ElementRef::Edge(id(1)),
            ElementRef::Edge(id(12)),
            ElementRef::Edge(id(13))
        ]
    );
    assert_eq!(values(&c, "selection.indices.u64"), [0, 1, 2]);
    assert_eq!(values(&c, "selection.layer_offsets.u64"), [0, 1, 2, 3]);
    assert_eq!(values(&c, "selection.rows.u64"), [(1u64 << 63) + 1, 77, 88]);
}
