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
    let doc = handmade_ends(COMPOSITION_VERSION, &[id(3), id(1), id(2)], &[
        E::Persisted(id(1)), E::Persisted(id(12)),
        E::Overlay {layer: 0, path: 4, order: 0}, E::Pair {layer: 3, row: (1u64 << 60) + 3},
    ], &[None, Some(""), Some("λ result 🦀"), Some(&long)], None,
        Some(&[(0,1),(0,1),(1,1),(1,2)]));
    let doc = edit_doc(&doc, &["layer.node_rows"], |b| {
        b.u64s("layer.node_rows", 0, &[u64::MAX, (1u64 << 62)+1, 42]);
        b.u64s("layer.node_rows", 2, &[3, 4, u64::MAX]);
    });
    let mut s = WireSession::open(&open_doc(&doc), wire::DEFAULT_MAX_BYTES, 0).unwrap();
    let all = (0..3).map(|i| s.session().identity().node_ref(i))
        .chain((0..4).map(|i| s.session().identity().edge_ref(i))).map(|r| s.session().identity().to_transport(&r).unwrap()).collect::<Vec<_>>();
    let render = s.execute(&request(2,0,wire::RENDER, |_|{}),0,None).unwrap().to_vec();
    let rev = header_of(&render)[0];
    let c = Container::decode(&render,wire::RESULT_MAGIC).unwrap();
    assert!(selected(&c).is_empty());
    assert_eq!(values(&c,"selection.layer_offsets.u64"),[0]);
    for (seq,mode,input,expected) in [
        (3,0,all.clone(),7), (4,0,all.clone(),7), (5,2,vec![all[0].clone()],6),
        (6,1,vec![all[0].clone()],7),
    ] {
        let req=select_request(seq,rev,mode,&input);
        let reply=s.execute(&req,0,None).unwrap().to_vec();
        assert_eq!(s.execute(&req,0,None).unwrap(),reply);
        let c=Container::decode(&reply,wire::RESULT_MAGIC).unwrap();
        let refs=selected(&c);
        assert_eq!(refs.len(),expected);
        assert!(refs.windows(2).all(|p| super::super::super::coordination::compare(&p[0],&p[1]).is_lt()));
        assert!(refs.iter().all(|r| !matches!(r,ElementRef::Derived(DerivedRef{result:ResultRef::Local(_),..}) | ElementRef::Aggregate(_))));
        let indices=values(&c,"selection.indices.u64");
        for (r,index) in refs.iter().zip(indices) {
            assert_eq!(match s.session().identity().resolve(r).unwrap(){ElementIndex::Node(i)|ElementIndex::Edge(i)=>i as u64},index);
        }
        let ids=c.get("selection.result_ids.texts",0).unwrap().as_texts("ids").unwrap();
        assert_eq!(ids,["","","λ result 🦀",&long]);
        assert_eq!(c.get("selection.result_ids.valid.u8",0).unwrap().payload,[0,1,1,1]);
        let offsets=values(&c,"selection.layer_offsets.u64");
        let rows=values(&c,"selection.rows.u64");
        assert_eq!(*offsets.last().unwrap(),rows.len() as u64);
        assert!(!rows.contains(&u64::MAX));
        assert!(rows.contains(&((1u64<<60)+3)));
        if seq==4 { assert!(wire::decode_refs(c.get("changed.refs.bytes",0).unwrap().payload).unwrap().is_empty()); }
    }
    let clear=s.execute(&request(7,rev,4, |_|{}),0,None).unwrap();
    let c=Container::decode(clear,wire::RESULT_MAGIC).unwrap();
    assert!(selected(&c).is_empty());
    assert_eq!(values(&c,"selection.layer_offsets.u64"),[0]);
    // Group zero publishes the identical full snapshot without an outbound event.
    let mut unlinked=open_doc(&doc);
    // Header payload is located generically; no fixed container offsets.
    let c=Container::decode(&unlinked,wire::REQUEST_MAGIC).unwrap();
    let at=c.get("header.u64",0).unwrap().payload.as_ptr() as usize-unlinked.as_ptr() as usize;
    unlinked[at+8..at+16].fill(0);
    let mut u=WireSession::open(&unlinked,wire::DEFAULT_MAX_BYTES,0).unwrap();
    assert_eq!(u.session().group_id(),0);
    let mut req=select_request(2,0,0,&all);
    let c=Container::decode(&req,wire::REQUEST_MAGIC).unwrap();
    let at=c.get("header.u64",0).unwrap().payload.as_ptr() as usize-req.as_ptr() as usize;
    req[at+8..at+16].fill(0);
    let c=Container::decode(u.execute(&req,0,None).unwrap(),wire::RESULT_MAGIC).unwrap();
    assert_eq!(selected(&c).len(),7);
    assert!(c.get("outbound.bytes",0).is_none());
}

#[test]
fn projection_update_uses_replacement_rows_and_malformed_planes_rollback() {
    let mut s=opened();
    let refs=[ElementRef::Node(id(1))];
    let reply=s.execute(&select_request(2,0,0,&refs),0,None).unwrap().to_vec();
    let rev=header_of(&reply)[0];
    let replacement=edit_doc(&standard_doc(),&["layer.node_rows"],|b| b.u64s("layer.node_rows",0,&[999, u64::MAX,u64::MAX]));
    let update=request(3,rev,wire::UPDATE,|b|{
        b.bytes("document.bytes",0,&replacement);
        b.f64s("load.x.f64",0,&[0.,30.,60.]); b.f64s("load.y.f64",0,&[0.,0.,0.]);
    });
    let reply=s.execute(&update,0,None).unwrap().to_vec();
    let c=Container::decode(&reply,wire::RESULT_MAGIC).unwrap();
    assert_eq!(selected(&c),refs);
    assert_eq!(values(&c,"selection.rows.u64"),[999]);
    let rev=header_of(&reply)[0];
    for malformed in [edit_doc(&replacement,&["layer.node_rows"],|b|b.u32s("layer.node_rows",0,&[1,2,3])),
        edit_doc(&replacement,&["layer.node_rows"],|b|b.u64s("layer.node_rows",0,&[1]))] {
        let req=request(4,rev,wire::UPDATE,|b|b.bytes("document.bytes",0,&malformed));
        assert_eq!(s.execute(&req,0,None),Err(InteractionStatus::Invalid));
        assert_eq!(s.reply(),reply);
        assert_eq!(s.session().selection().unwrap().len(),1);
        assert_eq!(s.session().render_revision(),rev);
    }
    let req=request(4,rev,4,|_|{});
    let max=s.max_bytes; s.max_bytes=s.retained_budget();
    assert_eq!(s.execute(&req,0,None),Err(InteractionStatus::Budget));
    assert_eq!(s.reply(),reply);
    s.max_bytes=max;
    let bytes=s.execute(&req,0,None).unwrap().to_vec();
    assert_eq!(s.execute(&req,0,None).unwrap(),bytes);
}
