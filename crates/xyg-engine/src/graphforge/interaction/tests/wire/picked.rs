//! Query-scoped picked target and typed leave checkpoint (§2.1.2).
use super::*;

fn point(seq: u64, rev: u32, op: u32, action: u32, xy: Option<[f64; 2]>) -> Vec<u8> {
    let mut b = Builder::new(wire::REQUEST_MAGIC);
    b.u64s("header.u64", 0, &[7, 9, seq]);
    b.u32s("header.u32", 0, &[rev, op, 0, 0, 0, action, 0, 0, 0]);
    if let Some(xy) = xy { b.f64s("coordinates.f64", 0, &xy); }
    b.finish()
}

#[test]
fn query_receipt_exact_target_miss_leave_retry_and_strict_frames() {
    let mut s = opened();
    let reply = s.execute(&request(2, 0, wire::RENDER, |_| {}), 0, None).unwrap().to_vec();
    let rev = header_of(&reply)[0];
    assert!(Container::decode(&reply, wire::RESULT_MAGIC).unwrap().get("pick.header.u32", 0).is_none());
    let render = s.session().published().unwrap();
    let p = render.paint.nodes[0].center;
    assert_eq!(render.pick_at(p[0], p[1]), Ok(Some(PickTarget::Node(0))));
    let reference = s.session().identity().node_ref(render.focus_node[0] as usize);
    for (seq, op) in [(3, 1), (4, 0)] {
        let req = point(seq, rev, op, 0, Some(p));
        let reply = s.execute(&req, 0, None).unwrap().to_vec();
        assert_eq!(s.execute(&req, usize::MAX, None).unwrap(), reply);
        let c = Container::decode(&reply, wire::RESULT_MAGIC).unwrap();
        assert_eq!(c.get("pick.header.u32", 0).unwrap().as_u32("pick").unwrap(), [1, op, 0, rev, 1, 1, 0, 0]);
        assert_eq!(c.get("pick.query.u64", 0).unwrap().as_u64("pick").unwrap(), [7, seq, 0, 1, 0]);
        assert_eq!(wire::decode_refs(c.get("pick.ref.bytes", 0).unwrap().payload).unwrap().as_slice(), std::slice::from_ref(&reference));
        assert_eq!(header_of(&reply)[0], rev);
    }
    let before = s.reply().to_vec();
    for req in [
        point(5, rev, 0, 1, Some(p)), // leave forbids even finite coordinates
        point(5, rev, 0, 2, None),
        point(5, rev, 0, 0, None),
        point(5, rev, 0, 0, Some([f64::NAN, 0.])),
        point(5, rev, 1, 1, Some(p)),
    ] {
        assert_eq!(s.execute(&req, 0, None), Err(InteractionStatus::Invalid));
        assert_eq!(s.reply(), before);
    }
    assert_eq!(s.execute(&point(5, rev + 1, 0, 1, None), 0, None), Err(InteractionStatus::Stale));
    let budget = s.max_bytes;
    s.max_bytes = s.retained_budget();
    assert_eq!(s.execute(&point(5, rev, 0, 1, None), 0, None), Err(InteractionStatus::Budget));
    assert_eq!(s.reply(), before);
    s.max_bytes = budget;
    for (seq, action, xy, changed) in [(5, 1, None, 1), (6, 1, None, 0), (7, 0, Some([-1000., -1000.]), 0)] {
        let req = point(seq, rev, 0, action, xy);
        let reply = s.execute(&req, 0, None).unwrap().to_vec();
        assert_eq!(s.execute(&req, 0, None).unwrap(), reply);
        let c = Container::decode(&reply, wire::RESULT_MAGIC).unwrap();
        assert_eq!(c.get("pick.header.u32", 0).unwrap().as_u32("pick").unwrap(), [1, 0, action, rev, 0, 0, 0, 0]);
        assert_eq!(c.get("pick.query.u64", 0).unwrap().as_u64("pick").unwrap(), [7, seq, 0, 0, 0]);
        assert!(wire::decode_refs(c.get("pick.ref.bytes", 0).unwrap().payload).unwrap().is_empty());
        assert_eq!(c.get("outcome.u32", 0).unwrap().as_u32("outcome").unwrap()[1], changed);
        assert!(s.session().hover.nodes.is_empty());
        assert_eq!(s.session().selection().unwrap().as_slice(), std::slice::from_ref(&reference));
    }
}
