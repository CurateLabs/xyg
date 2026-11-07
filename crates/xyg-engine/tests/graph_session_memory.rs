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
fn ten_thousand_open_and_paint_allocation_ledger() {
    let n = 10000;
    let ids = |offset: u32| {
        (0..n)
            .map(|i| {
                let mut id = [0; 16];
                id[..4].copy_from_slice(&(i as u32 + offset).to_le_bytes());
                id
            })
            .collect::<Vec<_>>()
    };
    let mut b = Builder::new(b"XYGF");
    b.u32s("status", 0, &[0]);
    b.utf8("kind", 0, "graph");
    b.u32s("composition.version", 0, &[2]);
    b.uuids("node.uuid", 0, &ids(1));
    b.uuids("edge.uuid", 0, &ids(10001));
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
    let open = request(1, 0, 19, Some(&document));
    let baseline = LIVE.load(SeqCst);
    PEAK.store(baseline, SeqCst);
    let mut session = WireSession::open(&open, 384 * 1024 * 1024, open.len()).unwrap();
    println!(
        "OPEN document={} request={} retained_envelope={} live={} peak={}",
        document.len(),
        open.len(),
        session.retained_budget(),
        LIVE.load(SeqCst) - baseline,
        PEAK.load(SeqCst) - baseline
    );
    let render = request(2, 0, 21, None);
    session.max_bytes = 16 * 1024 * 1024;
    assert_eq!(
        session.execute(&render, open.len(), None).unwrap_err(),
        xyg_engine::graphforge::interaction::InteractionStatus::Budget
    );
    assert_eq!(session.reply(), session.opening_reply());
    session.max_bytes = 384 * 1024 * 1024;
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
    let step = request(3, rev, 15, None);
    session.execute(&step, open.len(), None).unwrap();
    println!(
        "STEP retained_envelope={} live={} peak={}",
        session.retained_budget(),
        LIVE.load(SeqCst) - baseline,
        PEAK.load(SeqCst) - baseline
    );
    assert!(PEAK.load(SeqCst) - baseline < session.retained_budget());
}
