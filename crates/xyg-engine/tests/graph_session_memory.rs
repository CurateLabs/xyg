//! Requested-byte allocation ledger, isolated in its own test executable.
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicUsize, Ordering::SeqCst};
use xyg_engine::graphforge::{container::Builder, interaction::wire::WireSession};
static LIVE: AtomicUsize = AtomicUsize::new(0);
static PEAK: AtomicUsize = AtomicUsize::new(0);
struct Counting;
fn add(n: usize) {
    let live = LIVE.fetch_add(n, SeqCst) + n;
    PEAK.fetch_max(live, SeqCst);
}
unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let p = System.alloc(l);
        if !p.is_null() {
            add(l.size());
        }
        p
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        System.dealloc(p, l);
        LIVE.fetch_sub(l.size(), SeqCst);
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let q = System.realloc(p, l, n);
        if !q.is_null() {
            LIVE.fetch_sub(l.size(), SeqCst);
            add(n);
        }
        q
    }
}
#[global_allocator]
static ALLOCATOR: Counting = Counting;
fn request(seq: u64, rev: u32, op: u32, document: Option<&[u8]>) -> Vec<u8> {
    let mut b = Builder::new(b"XYGI");
    b.u64s("header.u64", 0, &[7101, 0, seq]);
    b.u32s(
        "header.u32",
        0,
        &[rev, op, 0, 0, 0, 0, 0, if op == 15 { 10 } else { 0 }, 0],
    );
    if let Some(d) = document {
        b.bytes("document.bytes", 0, d);
        b.u8s("load.progressive.u8", 0, &[1]);
    }
    if op == 21 {
        b.f64s("camera.f64", 0, &[0.01, 0.01, 320., 160., 640., 320., 1.]);
    }
    b.finish()
}
#[test]
fn default_thousand_and_explicit_ten_thousand_allocation_ledger() {
    ledger(1000, false);
    ledger(1000, true);
    ledger(10000, false);
}
fn ledger(n: usize, authored: bool) {
    let ids = |offset: u32| {
        (0..n)
            .map(|i| {
                let mut id = [0; 16];
                id[..4].copy_from_slice(&(i as u32 + offset).to_le_bytes());
                id
            })
            .collect::<Vec<_>>()
    };
    let node_ids = ids(1);
    let edge_ids = ids(10001);
    let mut b = Builder::new(b"XYGF");
    b.u32s("status", 0, &[0]);
    b.utf8("kind", 0, "graph");
    b.u32s("composition.version", 0, &[2]);
    b.uuids("node.uuid", 0, &node_ids);
    b.uuids("edge.uuid", 0, &edge_ids);
    b.u8s("edge.derived", 0, &vec![0; n]);
    b.u32s("edge.layer", 0, &vec![u32::MAX; n]);
    b.i64s("edge.order", 0, &vec![-1; n]);
    b.u64s("edge.path", 0, &vec![u64::MAX; n]);
    b.u64s("edge.source", 0, &(0..n as u64).collect::<Vec<_>>());
    b.u64s(
        "edge.target",
        0,
        &(0..n as u64)
            .map(|i| (i + 1) % n as u64)
            .collect::<Vec<_>>(),
    );
    b.u8s("graph.directed", 0, &[0]);
    let document = b.finish();
    let mut open = request(1, 0, 19, Some(&document));
    if authored {
        let mut b = Builder::new(b"XYGI");
        b.extend_from(&xyg_engine::graphforge::container::Container::decode(&open,b"XYGI").unwrap());
        b.f64s("load.x.f64",0,&(0..n).map(|i| (i%40) as f64*15.-300.).collect::<Vec<_>>());
        b.f64s("load.y.f64",0,&(0..n).map(|i| (i/40) as f64*12.-150.).collect::<Vec<_>>());
        open=b.finish();
    }
    if let Ok(dir) = std::env::var("XYG_MEMORY_CAPTURE") {
        std::fs::write(format!("{dir}/open-{n}.xygi"), &open).unwrap();
    }
    let baseline = LIVE.load(SeqCst);
    PEAK.store(baseline, SeqCst);
    let mut session = WireSession::open(
        &open,
        if n == 1000 { 16 } else { 384 } * 1024 * 1024,
        open.len(),
    )
    .unwrap();
    println!(
        "OPEN document={} request={} retained_envelope={} live={} peak={}",
        document.len(),
        open.len(),
        session.retained_budget(),
        LIVE.load(SeqCst) - baseline,
        PEAK.load(SeqCst) - baseline
    );
    // OPEN has no publication or force state. A speculative clone owns only
    // collapse flags, optional authored positions and small state metadata;
    // identity, labels, topology and static style capacities are shared.
    let before_clone = LIVE.load(SeqCst);
    let candidate = session.session().clone();
    let clone_bytes = LIVE.load(SeqCst) - before_clone;
    assert!(clone_bytes <= n * (if authored { 17 } else { 1 }) + 8192);
    assert_eq!(candidate.identity().node_uuids(), node_ids);
    drop(candidate);
    assert_eq!(LIVE.load(SeqCst), before_clone);
    println!("SOURCE_SHARED_CLONE n={n} authored={authored} requested={clone_bytes}");
    let mut render = request(2, 0, 21, None);
    if n == 1000 {
        let c = xyg_engine::graphforge::container::Container::decode(&render, b"XYGI").unwrap();
        let section = c.get("camera.f64", 0).unwrap();
        let start = section.payload.as_ptr() as usize - render.as_ptr() as usize;
        render[start..start + 8].copy_from_slice(&(if authored {1.0f64} else {0.25f64}).to_le_bytes());
        render[start + 8..start + 16].copy_from_slice(&(if authored {1.0f64} else {0.25f64}).to_le_bytes());
    }
    if let Ok(dir) = std::env::var("XYG_MEMORY_CAPTURE") {
        std::fs::write(format!("{dir}/render-{n}.xygi"), &render).unwrap();
    }
    let reply = session.execute(&render, open.len(), None).unwrap();
    let c = xyg_engine::graphforge::container::Container::decode(reply, b"XYGR").unwrap();
    let rev = c
        .get("header.u32", 0)
        .unwrap()
        .as_u32("header.u32")
        .unwrap()[0];
    println!(
        "RENDER output={} live={} peak={}",
        reply.len(),
        LIVE.load(SeqCst) - baseline,
        PEAK.load(SeqCst) - baseline
    );
    if authored {
        let output_bytes=reply.len();
        let p=session.session().published().unwrap();
        assert_eq!((p.node_count(),p.edge_count(),p.paint.pieces.len()),(n,n,n));
        assert!(output_bytes <= 131072+208*n+336*n);
        assert!(PEAK.load(SeqCst)-baseline < session.max_bytes);
        println!("AUTHORED full geometry output={} peak={}",output_bytes,PEAK.load(SeqCst)-baseline);
        drop(session);drop(render);return;
    }
    let step = request(3, rev, 15, None);
    session.execute(&step, open.len(), None).unwrap();
    println!(
        "STEP retained_envelope={} live={} peak={}",
        session.retained_budget(),
        LIVE.load(SeqCst) - baseline,
        PEAK.load(SeqCst) - baseline
    );
    assert!(PEAK.load(SeqCst) - baseline < session.max_bytes);
    if n == 1000 {
        for seq in 4..=40 {
            let step = request(seq, session.session().render_revision(), 15, None);
            session.execute(&step, open.len(), None).unwrap();
            assert_eq!(session.session().identity().node_uuids(), node_ids);
            assert!(session.session().identity().persisted_edge_uuids().eq(edge_ids.iter().copied()));
            assert_eq!(session.session().positions().unwrap().0.len(), n);
            let p = session.session().published().unwrap();
            assert_eq!((p.node_count(), p.edge_count()), (n, n));
            println!(
                "PROGRESS seq={seq} live={} peak={} entries={} primitives={} degraded={}",
                LIVE.load(SeqCst) - baseline,
                PEAK.load(SeqCst) - baseline,
                p.pick.grid_entries(),
                p.pick.primitive_count(),
                p.pick.degraded
            );
        }
    }
    if n == 1000 {
        let update = request(41, session.session().render_revision(), 20, Some(&document));
        let old_reply = session.reply().to_vec();
        let old_revision = session.session().render_revision();
        assert_eq!(
            session.execute(&update, open.len(), None).unwrap_err(),
            xyg_engine::graphforge::interaction::InteractionStatus::Budget
        );
        assert_eq!(session.reply(), old_reply);
        assert_eq!(session.session().render_revision(), old_revision);
        session.max_bytes = 384 * 1024 * 1024;
        let accepted = session.execute(&update, open.len(), None).unwrap().to_vec();
        assert_eq!(
            session.execute(&update, usize::MAX, None).unwrap(),
            accepted
        );
        assert_eq!(session.session().identity().node_count(), n);
        assert_eq!(session.session().identity().edge_count(), n);
        println!(
            "UPDATE failure/retry live={} peak={} retained={}",
            LIVE.load(SeqCst) - baseline,
            PEAK.load(SeqCst) - baseline,
            session.retained_budget()
        );
        drop(old_reply);
        drop(accepted);
        session.max_bytes = 16 * 1024 * 1024;
        let after = request(42, session.session().render_revision(), 15, None);
        session.execute(&after, open.len(), None).unwrap();
    }
    let retry = session.reply().to_vec();
    if n != 1000 {
        assert_eq!(session.execute(&step, usize::MAX, None).unwrap(), retry);
    }
    drop(retry);
    let p = session.session().published().unwrap();
    println!(
        "PUBLICATION nodes={} edges={} grid_entries={} primitives={}",
        p.node_count(),
        p.edge_count(),
        p.pick.grid_entries(),
        p.pick.primitive_count()
    );
    drop(session);
    drop(render);
    drop(step);
    println!(
        "DISPOSE n={n} remaining_delta={}",
        LIVE.load(SeqCst) as isize - baseline as isize
    );
}
