//! Requested-byte allocation ledger, isolated in its own test executable.
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicUsize, Ordering::SeqCst};
use xyg_engine::graphforge::{container::Builder, interaction::{GraphSession,SessionLoad,Camera,NodePaint,EdgePiece}};
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

fn main(){
 println!("SCOPE complete Wire requested-byte ledger including source/force/publication/serialization/retry/output; fixture/caller input baseline excluded; caller output capacity included in tick peak and admission; WASM/GPU/RSS excluded");
 println!("SIZES NodePaint={} EdgePiece={} ResolvedGraphStyle={} SemanticPaintLayers={}",std::mem::size_of::<NodePaint>(),std::mem::size_of::<EdgePiece>(),std::mem::size_of::<xyg_engine::graph_style::ResolvedGraphStyle>(),std::mem::size_of::<xyg_engine::graph_style::SemanticPaintLayers>());
 for n in [1000usize,100000,1000000]{
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

 let open=request(1,0,19,Some(&document));
 let baseline=LIVE.load(SeqCst);PEAK.store(baseline,SeqCst);
 let mut wire=match xyg_engine::graphforge::interaction::wire::WireSession::open(&open,384*1024*1024,open.len()) { Ok(s)=>s, Err(e)=>{println!("WIRE N={n} OPEN_REFUSAL={e:?} PEAK={}", PEAK.load(SeqCst)-baseline);continue;} };
 let retained=wire.retained_budget();let mut render=request(2,0,21,None);
 let c=xyg_engine::graphforge::container::Container::decode(&render,b"XYGI").unwrap();let camera=c.get("camera.f64",0).unwrap();let at=camera.payload.as_ptr() as usize-render.as_ptr() as usize;
 render[at..at+8].copy_from_slice(&(150.0/n as f64).to_le_bytes());render[at+8..at+16].copy_from_slice(&(150.0/n as f64).to_le_bytes());
 let preflight=wire.preflight_bytes(&render,0);
 let result=wire.execute(&render,0,None).map(|b|b.len());
 println!("WIRE N={n} D={} OPEN={} RETAINED={} PREFLIGHT={preflight:?} RESULT={:?} PEAK={}",document.len(),open.len(),retained,result,PEAK.load(SeqCst)-baseline);
 println!("OWNERS N={n} render={:?}",wire.ownership_bytes());
 assert!(result.is_ok());assert!(PEAK.load(SeqCst)-baseline<=384*1024*1024);
 if result.is_ok() {
   println!("POST_RENDER retained={} live={} nodes={} edges={} maxSteps={}",wire.retained_budget(),LIVE.load(SeqCst)-baseline,wire.session().published().unwrap().node_count(),wire.session().published().unwrap().edge_count(),wire.session().continuation_step_limit());
   if n==1000000 {
     let mut invalid=request(3,wire.session().render_revision(),15,None);
     let c=xyg_engine::graphforge::container::Container::decode(&invalid,b"XYGI").unwrap();let h=c.get("header.u32",0).unwrap();let at=h.payload.as_ptr() as usize-invalid.as_ptr() as usize;
     invalid[at+28..at+32].copy_from_slice(&3u32.to_le_bytes());
     let prior_peak=PEAK.load(SeqCst);let live=LIVE.load(SeqCst);PEAK.store(live,SeqCst);
     assert_eq!(wire.execute(&invalid,0,None),Err(xyg_engine::graphforge::interaction::InteractionStatus::Budget));
     let added=PEAK.load(SeqCst)-live;assert!(added<3*n+131072,"invalid work must not clone force planes");
     println!("INVALID_WORK N={n} steps=3 work=6000000 cap=4000000 added_requested_peak={added}");PEAK.fetch_max(prior_peak,SeqCst);
   }
   let mut step=request(3,wire.session().render_revision(),15,None);
   let c=xyg_engine::graphforge::container::Container::decode(&step,b"XYGI").unwrap();let h=c.get("header.u32",0).unwrap();let at=h.payload.as_ptr() as usize-step.as_ptr() as usize;
   step[at+28..at+32].copy_from_slice(&wire.session().continuation_step_limit().min(10).to_le_bytes());
   let mut caller_output=Vec::<u8>::with_capacity(wire.reply().len());
   let external=caller_output.capacity();
   println!("STEP_PREFLIGHT N={n} external={external} {:?}",wire.preflight_bytes(&step,external));
   let result=wire.execute(&step,external,None).map(|b|{caller_output.extend_from_slice(b);b.len()});
   assert_eq!(caller_output.as_slice(),wire.reply());
   println!("OWNERS N={n} step={:?}",wire.ownership_bytes());
   assert!(result.is_ok());assert!(PEAK.load(SeqCst)-baseline<=384*1024*1024);
   println!("POST_STEP N={n} result={result:?} retained={} live={} peak={}",wire.retained_budget(),LIVE.load(SeqCst)-baseline,PEAK.load(SeqCst)-baseline);
 }
 }
}
