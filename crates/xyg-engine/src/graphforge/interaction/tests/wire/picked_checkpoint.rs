//! R4 actual-query correctness and replay corpus. Product remains exact R2.
use super::*;
use crate::graph::LodTier;
use crate::graph_interaction_state::HighlightPlane;
use crate::graphforge::interaction::{pick::point_query_count, wire::projection_probe};
use std::io::Write;

#[derive(Default)]
struct Replay {
    name: String,
    budget: u32,
    steps: Vec<(Vec<u8>, i32, Vec<u8>)>,
}
fn query(seq: u64, rev: u32, op: u32, mode: u32, action: u32, p: Option<[f64; 2]>) -> Vec<u8> {
    let mut b = Builder::new(wire::REQUEST_MAGIC);
    b.u64s("header.u64", 0, &[7, 9, seq]);
    b.u32s("header.u32", 0, &[rev, op, mode, 0, 0, action, 0, 0, 0]);
    if let Some(p) = p {
        b.f64s("coordinates.f64", 0, &p);
    }
    b.finish()
}
fn capture(s: &mut WireSession, replay: &mut Replay, bytes: Vec<u8>) -> Vec<u8> {
    let out = s.execute(&bytes, 0, None).unwrap().to_vec();
    replay.steps.push((bytes.clone(), 0, out.clone()));
    let count = point_query_count();
    projection_probe::reset();
    assert_eq!(s.execute(&bytes, usize::MAX, None).unwrap(), out);
    assert_eq!(point_query_count(), count);
    assert_eq!(
        projection_probe::counts(),
        Default::default(),
        "retry must not project or query"
    );
    replay.steps.push((bytes, 0, out.clone()));
    out
}
fn refuse(
    s: &mut WireSession,
    replay: Option<&mut Replay>,
    bytes: Vec<u8>,
    status: InteractionStatus,
    queries: u64,
) {
    let before = (
        s.reply().to_vec(),
        s.session().selection().unwrap(),
        s.session().focus().unwrap(),
        s.session().hover.clone(),
        s.session().last_op.clone(),
        s.session().published().cloned(),
        s.session().pending_outbound().cloned(),
    );
    let q = point_query_count();
    projection_probe::reset();
    assert_eq!(s.execute(&bytes, 0, None), Err(status));
    assert_eq!(point_query_count() - q, queries);
    assert_eq!(projection_probe::counts(), Default::default());
    assert_eq!(
        (
            s.reply().to_vec(),
            s.session().selection().unwrap(),
            s.session().focus().unwrap(),
            s.session().hover.clone(),
            s.session().last_op.clone(),
            s.session().published().cloned(),
            s.session().pending_outbound().cloned()
        ),
        before
    );
    if let Some(r) = replay {
        r.steps.push((bytes, status.number(), Vec::new()));
    }
}
fn read32(c: &Container<'_>, name: &str) -> Vec<u32> {
    c.get(name, 0).unwrap().as_u32(name).unwrap()
}
fn read64(c: &Container<'_>, name: &str) -> Vec<u64> {
    c.get(name, 0).unwrap().as_u64(name).unwrap()
}
fn point(r: &RenderOutput, target: PickTarget) -> [f64; 2] {
    match target {
        PickTarget::Node(i) => {
            let p = r.paint.nodes[i].center;
            assert_eq!(r.pick_at(p[0], p[1]), Ok(Some(target)));
            p
        }
        PickTarget::Edge(i) => r
            .paint
            .pieces
            .iter()
            .filter(|p| p.edge == i)
            .flat_map(|p| {
                [0.2, 0.4, 0.5, 0.6, 0.8].map(|t| {
                    [
                        p.start[0] + t * (p.end[0] - p.start[0]),
                        p.start[1] + t * (p.end[1] - p.start[1]),
                    ]
                })
            })
            .find(|p| r.pick_at(p[0], p[1]) == Ok(Some(target)))
            .unwrap_or_else(|| {
                panic!(
                    "no actual point: tier={:?} target={:?} pieces={:?}",
                    r.tier, target, r.paint.pieces
                )
            }),
    }
}
fn geometry(
    r: &RenderOutput,
) -> (
    Vec<f64>,
    Vec<f64>,
    Vec<u64>,
    Vec<u64>,
    Vec<u64>,
    Vec<u64>,
    Vec<u64>,
    Vec<u64>,
) {
    (
        r.node_x.clone(),
        r.node_y.clone(),
        r.edge_source.clone(),
        r.edge_target.clone(),
        r.node_member_offsets.clone(),
        r.node_members.clone(),
        r.edge_member_offsets.clone(),
        r.edge_members.clone(),
    )
}
fn verify(
    s: &GraphSession,
    before: &RenderOutput,
    bytes: &[u8],
    target: Option<PickTarget>,
    seq: u64,
    op: u32,
    action: u32,
    collapsed: bool,
) {
    let c = Container::decode(bytes, wire::RESULT_MAGIC).unwrap();
    let (kind, index, count, source) = match target {
        None => (0, 0, 0, None),
        Some(PickTarget::Node(i)) => (
            1,
            i,
            before.members_of_node(i).len(),
            (before.tier != LodTier::Aggregate).then(|| {
                ElementIndex::Node(if collapsed && before.members_of_node(i).len() > 1 {
                    2
                } else {
                    before.members_of_node(i)[0] as usize
                })
            }),
        ),
        Some(PickTarget::Edge(i)) => (
            2,
            i,
            before.members_of_edge(i).len(),
            (before.tier != LodTier::Aggregate)
                .then(|| ElementIndex::Edge(before.members_of_edge(i)[0] as usize)),
        ),
    };
    let form = if kind == 0 {
        0
    } else if source.is_some() {
        1
    } else {
        2
    };
    assert_eq!(
        read32(&c, "pick.header.u32"),
        [1, op, action, before.revision, kind, form, 0, 0]
    );
    let source_index = source.map_or(0, |i| match i {
        ElementIndex::Node(i) | ElementIndex::Edge(i) => i as u64,
    });
    assert_eq!(
        read64(&c, "pick.query.u64"),
        [7, seq, index as u64, count as u64, source_index]
    );
    let refs = wire::decode_refs(c.get("pick.ref.bytes", 0).unwrap().payload).unwrap();
    if let Some(src) = source {
        let reference = match src {
            ElementIndex::Node(i) => s.identity.node_ref(i),
            ElementIndex::Edge(i) => s.identity.edge_ref(i),
        };
        assert_eq!(refs, [s.identity.to_transport(&reference).unwrap()]);
        if collapsed && count > 1 {
            assert_eq!(refs, [ElementRef::Node(id(3))]);
            assert_eq!(source_index, 2);
        }
        let expected = (0..3usize)
            .filter(|&layer| (source_index as usize + layer) % 3 != 1)
            .collect::<Vec<_>>();
        assert_eq!(
            read32(&c, "pick.layers.u32"),
            expected.iter().map(|&l| l as u32).collect::<Vec<_>>()
        );
        assert_eq!(
            read64(&c, "pick.rows.u64"),
            expected
                .iter()
                .map(|&l| (1u64 << 60) + source_index * 10 + l as u64)
                .collect::<Vec<_>>()
        );
    } else {
        assert!(
            refs.is_empty(),
            "Aggregate singleton must never invent a UUID or keyboard stand-in"
        );
        assert!(read32(&c, "pick.layers.u32").is_empty());
        assert!(read64(&c, "pick.rows.u64").is_empty());
    }
    assert_eq!(read32(&c, "header.u32")[0], before.revision);
    assert_eq!(geometry(s.published().unwrap()), geometry(before));
    assert_eq!(
        c.get("selection.result_ids.valid.u8", 0)
            .unwrap()
            .payload
            .len(),
        3
    );
    let selection_refs =
        wire::decode_refs(c.get("selection.refs.bytes", 0).unwrap().payload).unwrap();
    assert_eq!(
        read64(&c, "selection.indices.u64").len(),
        selection_refs.len()
    );
    assert_eq!(
        read64(&c, "selection.layer_offsets.u64").len(),
        selection_refs.len() + 1
    );
}
fn document(base: &[u8], n: usize, m: usize) -> Vec<u8> {
    let mut c = Container::decode(base, DOCUMENT_MAGIC).unwrap();
    c.sections
        .retain(|(name, _, _)| !matches!(*name, "layer.node_rows" | "layer.edge_rows"));
    let mut b = Builder::new(DOCUMENT_MAGIC);
    b.extend_from(&c);
    for layer in 0..3 {
        let rows = |count: usize| {
            (0..count)
                .map(|i| {
                    if (i + layer) % 3 == 1 {
                        u64::MAX
                    } else {
                        (1u64 << 60) + (i * 10 + layer) as u64
                    }
                })
                .collect::<Vec<_>>()
        };
        b.u64s("layer.node_rows", layer, &rows(n));
        b.u64s("layer.edge_rows", layer, &rows(m));
    }
    b.finish()
}
fn run_case(
    name: &str,
    base: Vec<u8>,
    x: &[f64],
    budgets: (u64, u64),
    collapsed: bool,
    tier: LodTier,
) -> Replay {
    println!("actual query fixture {name}");
    let n = x.len();
    let m = ComposedDocument::decode(&base)
        .unwrap()
        .uuids("edge.uuid")
        .unwrap()
        .len();
    let doc = document(&base, n, m);
    let opening = request(1, 0, wire::OPEN, |b| {
        b.bytes("document.bytes", 0, &doc);
        b.f64s("load.x.f64", 0, x);
        b.f64s("load.y.f64", 0, &vec![0.; n]);
        b.u64s("load.budgets.u64", 0, &[budgets.0, budgets.1]);
        if collapsed {
            b.u8s("load.collapsed.u8", 0, &[0, 0, 1, 0]);
        }
    });
    let mut s = WireSession::open(&opening, wire::DEFAULT_MAX_BYTES, 0).unwrap();
    let mut replay = Replay {
        name: name.into(),
        budget: 16 * 1024 * 1024,
        steps: vec![(opening, 0, s.reply().to_vec())],
    };
    let out = capture(
        &mut s,
        &mut replay,
        request(2, 0, wire::RENDER, |b| {
            b.f64s("camera.f64", 0, &[1., 100., 20., 100., 400., 300., 1.])
        }),
    );
    let rev = header_of(&out)[0];
    assert_eq!(s.session().published().unwrap().tier, tier);
    let focus = s.session().identity.node_ref(if collapsed { 2 } else { 0 });
    capture(
        &mut s,
        &mut replay,
        request(3, rev, 6, |b| {
            b.bytes(
                "refs.bytes",
                0,
                &wire::encode_refs(std::slice::from_ref(&focus)).unwrap(),
            )
        }),
    );
    let mut b = Builder::new(wire::REQUEST_MAGIC);
    b.u64s("header.u64", 0, &[7, 9, 4]);
    b.u32s("header.u32", 0, &[rev, 12, 0, 0, 2, 0, 0, 0, 0]);
    b.bytes(
        "refs.bytes",
        0,
        &wire::encode_refs(std::slice::from_ref(&focus)).unwrap(),
    );
    capture(&mut s, &mut replay, b.finish());
    let mut seq = 4;
    let r = s.session().published().unwrap();
    let targets = (0..r.node_count())
        .map(PickTarget::Node)
        .chain((0..r.edge_count()).map(PickTarget::Edge))
        .collect::<Vec<_>>();
    let mut singleton_node = false;
    let mut singleton_edge = false;
    for target in targets {
        for (op, mode) in [(0, 0), (1, 0), (1, 1), (1, 2)] {
            let before = s.session().published().unwrap().clone();
            let p = point(&before, target);
            let focus = s.session().focus().unwrap();
            let highlights = s
                .session()
                .read_state(|st| {
                    [
                        HighlightPlane::Path,
                        HighlightPlane::Community,
                        HighlightPlane::External,
                    ]
                    .map(|p| st.highlight_set(p).clone())
                })
                .unwrap();
            let selected = s.session().selection().unwrap();
            let q = point_query_count();
            projection_probe::reset();
            seq += 1;
            let bytes = query(seq, rev, op, mode, 0, Some(p));
            let out = s.execute(&bytes, 0, None).unwrap().to_vec();
            assert_eq!(point_query_count() - q, 1);
            let c = Container::decode(&out, wire::RESULT_MAGIC).unwrap();
            let selected_n = read64(&c, "selection.indices.u64").len();
            let source = usize::from(tier != LodTier::Aggregate);
            let counts = projection_probe::counts();
            assert_eq!(
                (counts.admissions, counts.borrows, counts.outputs),
                (1, 1, 1)
            );
            assert_eq!(counts.targets, selected_n + source);
            assert_eq!(counts.rows, 2 * (selected_n + source) * 3);
            replay.steps.push((bytes.clone(), 0, out.clone()));
            assert_eq!(s.execute(&bytes, usize::MAX, None).unwrap(), out);
            assert_eq!(point_query_count() - q, 1);
            replay.steps.push((bytes, 0, out.clone()));
            verify(
                s.session(),
                &before,
                &out,
                Some(target),
                seq,
                op,
                0,
                collapsed,
            );
            assert_eq!(s.session().focus().unwrap(), focus);
            assert_eq!(
                s.session()
                    .read_state(|st| [
                        HighlightPlane::Path,
                        HighlightPlane::Community,
                        HighlightPlane::External
                    ]
                    .map(|p| st.highlight_set(p).clone()))
                    .unwrap(),
                highlights
            );
            if op == 0 {
                assert_eq!(s.session().selection().unwrap(), selected);
            }
            if tier == LodTier::Aggregate {
                match target {
                    PickTarget::Node(i) => singleton_node |= before.members_of_node(i).len() == 1,
                    PickTarget::Edge(i) => singleton_edge |= before.members_of_edge(i).len() == 1,
                }
            }
        }
    }
    if tier == LodTier::Aggregate {
        assert!(singleton_node && singleton_edge);
    }
    // Clear an actually applied hover, with direct point-query instrumentation.
    let before = s.session().published().unwrap().clone();
    let p = point(&before, PickTarget::Node(0));
    seq += 1;
    capture(&mut s, &mut replay, query(seq, rev, 0, 0, 0, Some(p)));
    let before = s.session().published().unwrap().clone();
    let selected = s.session().selection().unwrap();
    let focus = s.session().focus().unwrap();
    let pins = s.session().pinned().unwrap();
    let q = point_query_count();
    seq += 1;
    let out = capture(&mut s, &mut replay, query(seq, rev, 0, 0, 1, None));
    assert_eq!(point_query_count(), q);
    verify(s.session(), &before, &out, None, seq, 0, 1, collapsed);
    assert!(s.session().hover.nodes.is_empty() && s.session().hover.edges.is_empty());
    assert_eq!(s.session().selection().unwrap(), selected);
    assert_eq!(s.session().focus().unwrap(), focus);
    assert_eq!(s.session().pinned().unwrap(), pins);
    assert!(s
        .session()
        .published()
        .unwrap()
        .source_node_flags
        .iter()
        .all(|f| f & (crate::graph_style::FLAG_HOVERED | crate::graph_style::FLAG_NEIGHBOR) == 0));
    for (op, action, p) in [
        (0, 0, Some([-9999., -9999.])),
        (1, 0, Some([-9999., -9999.])),
        (0, 1, None),
        (0, 1, None),
    ] {
        let before = s.session().published().unwrap().clone();
        let focus = s.session().focus().unwrap();
        seq += 1;
        let q = point_query_count();
        let out = capture(&mut s, &mut replay, query(seq, rev, op, 0, action, p));
        assert_eq!(point_query_count() - q, u64::from(action == 0));
        verify(s.session(), &before, &out, None, seq, op, action, collapsed);
        assert_eq!(s.session().focus().unwrap(), focus);
    }
    refuse(
        &mut s,
        Some(&mut replay),
        query(seq + 1, rev + 1, 0, 0, 1, None),
        InteractionStatus::Stale,
        0,
    );
    for bad in [
        query(seq + 1, rev, 0, 0, 2, None),
        query(seq + 1, rev, 0, 0, 1, Some([0., 0.])),
        query(seq + 1, rev, 0, 0, 0, Some([f64::NAN, 0.])),
    ] {
        refuse(
            &mut s,
            Some(&mut replay),
            bad,
            InteractionStatus::Invalid,
            0,
        );
    }
    let max = s.max_bytes;
    s.max_bytes = s.retained_budget();
    for (op, action, p) in [
        (0, 0, Some([20., 100.])),
        (1, 0, Some([20., 100.])),
        (0, 1, None),
    ] {
        refuse(
            &mut s,
            None,
            query(seq + 1, rev, op, 0, action, p),
            InteractionStatus::Budget,
            0,
        );
    }
    s.max_bytes = max;
    capture(&mut s, &mut replay, query(seq + 1, rev, 0, 0, 1, None));
    replay
}
#[test]
fn actual_tiers_collapsed_parallel_loop_provenance_and_noquery_receipts() {
    let ids = [None, Some(""), Some(" λ 空 🦀 ")];
    let mut cases = Vec::new();
    for (name, budgets, tier) in [
        ("Direct", (3, 10), LodTier::Direct),
        ("Aggregate-singletons", (2, 10), LodTier::Aggregate),
        ("EdgeSample", (3, 1), LodTier::EdgeSample),
    ] {
        let base = handmade_ends(
            COMPOSITION_VERSION,
            &[id(1), id(2), id(3)],
            &[
                E::Persisted(id(11)),
                E::Persisted(id(12)),
                E::Persisted(id(13)),
            ],
            &ids,
            None,
            Some(&[(0, 2), (1, 2), (2, 0)]),
        );
        cases.push(run_case(name, base, &[0., 10., 100.], budgets, false, tier));
    }
    let base = handmade_with(
        COMPOSITION_VERSION,
        &[id(1), id(2), id(3), id(4)],
        &[E::Persisted(id(11))],
        &ids,
        Some((&[2, 2, NONE_U32, NONE_U32], &[1, 1, 0, 0])),
    );
    cases.push(run_case(
        "collapsed-representative-source-index-2",
        base,
        &[0., 20., 10., 100.],
        (4, 10),
        true,
        LodTier::Direct,
    ));
    for (i, result_id) in ids.into_iter().enumerate() {
        let base = handmade_ends(
            COMPOSITION_VERSION,
            &[id(1), id(2)],
            &[
                E::Persisted(id(11)),
                E::Persisted(id(12)),
                E::Overlay {
                    layer: 0,
                    path: 4,
                    order: 0,
                },
                E::Persisted(id(14)),
            ],
            &[result_id, Some(""), Some(" λ 空 🦀 ")],
            None,
            Some(&[(0, 1), (0, 1), (1, 0), (1, 1)]),
        );
        let c = Container::decode(&base, DOCUMENT_MAGIC).unwrap();
        let mut b = Builder::new(DOCUMENT_MAGIC);
        b.extend_from(&c);
        b.u8s("edge.status", 0, &[1; 4]);
        cases.push(run_case(
            &format!("parallel-loop-derived-{i}"),
            b.finish(),
            &[0., 100.],
            (2, 10),
            false,
            LodTier::Direct,
        ));
    }
    cases.push(empty_case());
    cases.push(full_selection_case());
    if let Some(path) = std::env::var_os("XYG_PICK_CORPUS") {
        let mut bytes = b"XYQ2".to_vec();
        bytes.extend_from_slice(&(cases.len() as u32).to_le_bytes());
        for case in &cases {
            bytes.extend_from_slice(&(case.name.len() as u32).to_le_bytes());
            bytes.extend_from_slice(case.name.as_bytes());
            bytes.extend_from_slice(&case.budget.to_le_bytes());
            bytes.extend_from_slice(&(case.steps.len() as u32).to_le_bytes());
            for (req, status, out) in &case.steps {
                bytes.extend_from_slice(&(req.len() as u64).to_le_bytes());
                bytes.extend_from_slice(req);
                bytes.extend_from_slice(&status.to_le_bytes());
                bytes.extend_from_slice(&(out.len() as u64).to_le_bytes());
                bytes.extend_from_slice(out);
            }
        }
        std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(path)
            .unwrap()
            .write_all(&bytes)
            .unwrap();
        println!(
            "DIAGNOSTIC corpus: {} cases, {} steps, {} bytes",
            cases.len(),
            cases.iter().map(|c| c.steps.len()).sum::<usize>(),
            bytes.len()
        );
    }
}

#[test]
fn full_selection_actual_query_suffix_and_overflow_refusal_are_atomic() {
    full_selection_case();
}
fn full_selection_case() -> Replay {
    let n = MAX_GRAPH_SELECTION_REFS + 1;
    let base = handmade(
        &(0..n).map(|i| id(i as u32 + 1)).collect::<Vec<_>>(),
        &[],
        &[None, Some(""), Some("λ")],
    );
    let doc = document(&base, n, 0);
    let opening = request(1, 0, wire::OPEN, |b| {
        b.bytes("document.bytes", 0, &doc);
        b.f64s(
            "load.x.f64",
            0,
            &(0..n).map(|i| i as f64 * 30.).collect::<Vec<_>>(),
        );
        b.f64s("load.y.f64", 0, &vec![0.; n]);
    });
    let mut s = WireSession::open(&opening, wire::DEFAULT_MAX_BYTES, 0).unwrap();
    let mut replay = Replay {
        name: "full-selection-10000-existing-384MiB-max".into(),
        budget: 384 * 1024 * 1024,
        steps: vec![(opening, 0, s.reply().to_vec())],
    };
    let rendered = capture(&mut s, &mut replay, request(2, 0, wire::RENDER, |_| {}));
    let rev = header_of(&rendered)[0];
    let refs = (0..MAX_GRAPH_SELECTION_REFS)
        .map(|i| ElementRef::Node(id(i as u32 + 1)))
        .collect::<Vec<_>>();
    capture(
        &mut s,
        &mut replay,
        request(3, rev, 11, |b| {
            b.bytes("refs.bytes", 0, &wire::encode_refs(&refs).unwrap())
        }),
    );
    let p = s.session().published().unwrap().paint.nodes[0].center;
    projection_probe::reset();
    let req = query(4, rev, 0, 0, 0, Some(p));
    let out = s.execute(&req, 0, None).unwrap().to_vec();
    replay.steps.push((req.clone(), 0, out.clone()));
    assert_eq!(s.execute(&req, 0, None).unwrap(), out);
    replay.steps.push((req, 0, out.clone()));
    let c = Container::decode(&out, wire::RESULT_MAGIC).unwrap();
    assert_eq!(
        read64(&c, "selection.indices.u64").len(),
        MAX_GRAPH_SELECTION_REFS
    );
    assert_eq!(
        read64(&c, "selection.layer_offsets.u64").len(),
        MAX_GRAPH_SELECTION_REFS + 1
    );
    assert_eq!(read64(&c, "pick.rows.u64"), [1u64 << 60, (1u64 << 60) + 2]);
    assert_eq!(
        projection_probe::counts().targets,
        MAX_GRAPH_SELECTION_REFS + 1
    );
    let p = s.session().published().unwrap().paint.nodes[MAX_GRAPH_SELECTION_REFS].center;
    refuse(
        &mut s,
        Some(&mut replay),
        query(5, rev, 1, 1, 0, Some(p)),
        InteractionStatus::SelectionTooLarge,
        1,
    );
    capture(&mut s, &mut replay, query(5, rev, 0, 0, 1, None));
    assert_eq!(
        s.session().selection().unwrap().len(),
        MAX_GRAPH_SELECTION_REFS
    );
    replay
}

#[test]
fn leave_has_zero_instrumented_queries_even_without_a_publication() {
    let mut s = GraphSession::create(
        &standard_doc(),
        SessionLoad {
            x: Some(vec![0., 30., 60.]),
            y: Some(vec![0.; 3]),
            ..Default::default()
        },
        7,
    )
    .unwrap();
    assert!(s.published().is_none());
    s.hover.nodes = vec![0];
    let h = header(&s, 1);
    let before = point_query_count();
    let out = s.hover_leave(h).unwrap();
    assert_eq!(point_query_count(), before);
    assert!(s.hover.nodes.is_empty());
    assert!(s.published().is_none());
    assert!(out.state_changed);
    let p = out.pick.as_ref().unwrap();
    assert_eq!(
        (p.header, p.operation, p.action, p.target, p.member_count),
        (h, 0, 1, None, 0)
    );
    assert_eq!(s.hover_leave(h).unwrap(), out);
    assert_eq!(point_query_count(), before);
}

#[test]
fn actual_query_work_refusal_precedes_projection_allocations_and_preserves_all_state() {
    let n = 10_000;
    let doc = handmade(
        &(0..n).map(|i| id(i as u32 + 1)).collect::<Vec<_>>(),
        &[],
        &vec![None; 200],
    );
    let opening = request(1, 0, wire::OPEN, |b| {
        b.bytes("document.bytes", 0, &doc);
        b.f64s(
            "load.x.f64",
            0,
            &(0..n).map(|i| i as f64 * 30.).collect::<Vec<_>>(),
        );
        b.f64s("load.y.f64", 0, &vec![0.; n]);
    });
    let mut s = WireSession::open(&opening, wire::DEFAULT_MAX_BYTES, 0).unwrap();
    let mut replay = Replay::default();
    let out = capture(&mut s, &mut replay, request(2, 0, wire::RENDER, |_| {}));
    let rev = header_of(&out)[0];
    let selected = n - 2;
    let d = ComposedDocument::decode(&doc).unwrap();
    assert!(d.projection_work(selected).unwrap() as u64 <= MAX_GRAPH_INTERACTION_WORK);
    assert!(d.projection_work(selected + 1).unwrap() as u64 > MAX_GRAPH_INTERACTION_WORK);
    capture(
        &mut s,
        &mut replay,
        request(3, rev, 11, |b| {
            b.bytes(
                "refs.bytes",
                0,
                &wire::encode_refs(
                    &(0..selected)
                        .map(|i| ElementRef::Node(id(i as u32 + 1)))
                        .collect::<Vec<_>>(),
                )
                .unwrap(),
            )
        }),
    );
    let p = s.session().published().unwrap().paint.nodes[0].center;
    refuse(
        &mut s,
        None,
        query(4, rev, 0, 0, 0, Some(p)),
        InteractionStatus::Budget,
        1,
    );
    let out = capture(&mut s, &mut replay, query(4, rev, 0, 0, 1, None));
    let c = Container::decode(&out, wire::RESULT_MAGIC).unwrap();
    assert_eq!(read64(&c, "selection.indices.u64").len(), selected);
    assert!(s.session().hover.nodes.is_empty());
}

fn empty_case() -> Replay {
    let doc = document(&handmade(&[], &[], &[None, Some(""), Some("λ")]), 0, 0);
    let opening = request(1, 0, wire::OPEN, |b| {
        b.bytes("document.bytes", 0, &doc);
        b.f64s("load.x.f64", 0, &[]);
        b.f64s("load.y.f64", 0, &[]);
    });
    let mut s = WireSession::open(&opening, wire::DEFAULT_MAX_BYTES, 0).unwrap();
    let mut replay = Replay {
        name: "empty-miss-typed-leave".into(),
        budget: 16 * 1024 * 1024,
        steps: vec![(opening, 0, s.reply().to_vec())],
    };
    let rendered = capture(&mut s, &mut replay, request(2, 0, wire::RENDER, |_| {}));
    let rev = header_of(&rendered)[0];
    for (seq, op, action, p) in [
        (3, 0, 0, Some([0., 0.])),
        (4, 1, 0, Some([0., 0.])),
        (5, 0, 1, None),
        (6, 0, 1, None),
    ] {
        let before = s.session().published().unwrap().clone();
        let q = point_query_count();
        let out = capture(&mut s, &mut replay, query(seq, rev, op, 0, action, p));
        assert_eq!(point_query_count() - q, u64::from(action == 0));
        verify(s.session(), &before, &out, None, seq, op, action, false);
    }
    replay
}
