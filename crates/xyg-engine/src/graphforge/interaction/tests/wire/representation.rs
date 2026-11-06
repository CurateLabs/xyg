//! Frozen R2 complete-wire transcript regression; inline receipt retained.
use super::*;

fn query(seq: u64, rev: u32, op: u32, mode: u32, action: u32, xy: Option<[f64; 2]>) -> Vec<u8> {
    let mut b = Builder::new(wire::REQUEST_MAGIC);
    b.u64s("header.u64", 0, &[7, 9, seq]);
    b.u32s("header.u32", 0, &[rev, op, mode, 0, 0, action, 0, 0, 0]);
    if let Some(xy) = xy {
        b.f64s("coordinates.f64", 0, &xy);
    }
    b.finish()
}

fn record(out: &mut Vec<u8>, request: &[u8], status: i32, reply: &[u8]) {
    out.extend_from_slice(&(request.len() as u64).to_le_bytes());
    out.extend_from_slice(request);
    out.extend_from_slice(&status.to_le_bytes());
    out.extend_from_slice(&(reply.len() as u64).to_le_bytes());
    out.extend_from_slice(reply);
}

fn success(s: &mut WireSession, out: &mut Vec<u8>, request: Vec<u8>) -> Vec<u8> {
    let reply = s.execute(&request, 0, None).unwrap().to_vec();
    record(out, &request, 0, &reply);
    assert_eq!(s.execute(&request, usize::MAX, None).unwrap(), reply);
    record(out, &request, 0, s.reply());
    reply
}

fn refusal(s: &mut WireSession, out: &mut Vec<u8>, request: Vec<u8>, error: InteractionStatus) {
    let before = (
        s.reply().to_vec(),
        s.session().selection().unwrap(),
        s.session().focus().unwrap(),
        s.session().hover.clone(),
        s.session().last_op.clone(),
        s.session().published().cloned(),
        s.session().pending_outbound().cloned(),
    );
    assert_eq!(s.execute(&request, 0, None), Err(error));
    let after = (
        s.reply().to_vec(),
        s.session().selection().unwrap(),
        s.session().focus().unwrap(),
        s.session().hover.clone(),
        s.session().last_op.clone(),
        s.session().published().cloned(),
        s.session().pending_outbound().cloned(),
    );
    assert_eq!(after, before, "refusal changed authoritative state/cache");
    record(out, &request, error.number(), s.reply());
}

#[test]
fn frozen_r2_complete_receipt_selection_reply_and_refusal_transcript() {
    let mut transcript = Vec::new();
    for result_id in [None, Some(""), Some(" λ 空 🦀 ")] {
        let bytes = standard_doc();
        let mut c = Container::decode(&bytes, DOCUMENT_MAGIC).unwrap();
        c.sections.retain(|(name, _, _)| {
            !matches!(
                *name,
                "layer.result_id" | "layer.node_rows" | "layer.edge_rows"
            )
        });
        let mut b = Builder::new(DOCUMENT_MAGIC);
        b.extend_from(&c);
        if let Some(id) = result_id {
            b.utf8("layer.result_id", 0, id);
        }
        b.u64s("layer.node_rows", 0, &[42, u64::MAX, 1 << 62]);
        b.u64s("layer.edge_rows", 0, &[11, 12, 13]);
        let doc = b.finish();
        let opening = open_doc(&doc);
        let mut s = WireSession::open(&opening, wire::DEFAULT_MAX_BYTES, 0).unwrap();
        record(&mut transcript, &opening, 0, s.reply());
        let rendered = success(&mut s, &mut transcript, request(2, 0, wire::RENDER, |_| {}));
        let rev = header_of(&rendered)[0];
        let r = s.session().published().unwrap();
        let node = r.paint.nodes[0].center;
        let edge = r
            .paint
            .pieces
            .iter()
            .filter(|p| p.edge == 2)
            .flat_map(|p| {
                [0.25, 0.5, 0.75].map(|t| {
                    [
                        p.start[0] + t * (p.end[0] - p.start[0]),
                        p.start[1] + t * (p.end[1] - p.start[1]),
                    ]
                })
            })
            .find(|p| r.pick_at(p[0], p[1]) == Ok(Some(PickTarget::Edge(2))))
            .expect("actual derived-edge point hit");
        for (seq, op, mode, action, xy) in [
            (3, 0, 0, 0, Some(node)),
            (4, 1, 0, 0, Some(node)),
            (5, 0, 0, 0, Some(edge)),
            (6, 1, 1, 0, Some(edge)),
            (7, 0, 0, 0, Some([-9999., -9999.])),
            (8, 0, 0, 1, None),
            (9, 0, 0, 0, Some(node)),
            (10, 0, 0, 1, None),
            (11, 0, 0, 1, None),
        ] {
            let reply = success(
                &mut s,
                &mut transcript,
                query(seq, rev, op, mode, action, xy),
            );
            assert_eq!(header_of(&reply)[0], rev);
            let c = Container::decode(&reply, wire::RESULT_MAGIC).unwrap();
            let refs = wire::decode_refs(c.get("pick.ref.bytes", 0).unwrap().payload).unwrap();
            if seq == 5 || seq == 6 {
                assert!(
                    matches!(&refs[..], [ElementRef::Derived(DerivedRef { result: ResultRef::Exact(id), .. })] if id.as_deref() == result_id)
                );
                assert_eq!(
                    c.get("pick.rows.u64", 0).unwrap().as_u64("rows").unwrap(),
                    [13]
                );
            }
        }
        refusal(
            &mut s,
            &mut transcript,
            query(12, rev + 1, 0, 0, 1, None),
            InteractionStatus::Stale,
        );
        let max = s.max_bytes;
        s.max_bytes = s.retained_budget();
        for (op, action, xy) in [(0, 0, Some(node)), (1, 0, Some(node)), (0, 1, None)] {
            refusal(
                &mut s,
                &mut transcript,
                query(12, rev, op, 0, action, xy),
                InteractionStatus::Budget,
            );
        }
        s.max_bytes = max;
        success(&mut s, &mut transcript, query(12, rev, 0, 0, 0, Some(node)));
        refusal(
            &mut s,
            &mut transcript,
            query(13, rev, 0, 0, 1, Some(node)),
            InteractionStatus::Invalid,
        );
        success(&mut s, &mut transcript, query(13, rev, 0, 0, 1, None));
        assert!(s.session().hover.nodes.is_empty());
        assert_eq!(s.session().selection().unwrap().len(), 2);
    }
    println!(
        "native layout: OpOutcome={} PickReceipt={} align={}",
        std::mem::size_of::<OpOutcome>(),
        std::mem::size_of::<PickReceipt>(),
        std::mem::align_of::<PickReceipt>()
    );
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../spec/performance/graph-picked-target-r3-2026-11-04/r2-wire-transcript.bin");
    assert_eq!(
        transcript,
        std::fs::read(path).unwrap(),
        "changed frozen R2 full wire transcript"
    );
    println!("complete transcript bytes={}", transcript.len());
}
