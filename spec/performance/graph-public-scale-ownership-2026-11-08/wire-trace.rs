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

fn main() {
 println!("SCOPE complete native Wire trace with uncached caller output loan; caller input baseline excluded; WASM/RSS/GPU separate");
 let path=std::env::args().nth(1).expect("trace path");
 let bytes=std::fs::read(path).unwrap();let mut at=0;
 let read=|at:&mut usize|{let n=u64::from_le_bytes(bytes[*at..*at+8].try_into().unwrap()) as usize;*at+=8;n};
 let views=read(&mut at);
 for _ in 0..views {
   let cap=read(&mut at);let count=read(&mut at);let baseline=LIVE.load(SeqCst);PEAK.store(baseline,SeqCst);
   let mut session=None;
   for index in 0..count {
     let expected=read(&mut at);let length=read(&mut at);let request=&bytes[at..at+length];at+=length;
     let r=xyg_engine::graphforge::interaction::wire::Request::decode(request).unwrap();
     if r.operation==19 {session=Some(xyg_engine::graphforge::interaction::wire::WireSession::open(request,cap,length).unwrap());continue;}
     let wire=session.as_mut().unwrap();let mut output=Vec::<u8>::with_capacity(expected);let external=output.capacity();
     let preflight=wire.preflight_bytes(request,external).unwrap();
     let reply=wire.execute(request,external,None).unwrap();assert_eq!(reply.len(),expected);output.extend_from_slice(reply);
     assert_eq!(output.as_slice(),wire.reply());
     assert!(PEAK.load(SeqCst)-baseline<=cap,"index {index} actual requested peak exceeds cap");
     println!("TRACE index={index} op={} cap={cap} output_capacity={external} preflight={preflight} retained={} actual_live={} peak={} owners={:?}",r.operation,wire.retained_budget(),LIVE.load(SeqCst)-baseline,PEAK.load(SeqCst)-baseline,wire.ownership_bytes().unwrap());
   }
   let peak=PEAK.load(SeqCst)-baseline;drop(session);assert_eq!(LIVE.load(SeqCst),baseline,"all trace session/caller owners released");
   println!("COMPLETE_NATIVE_WIRE_TRACE cap={cap} commands={count} actual_peak={peak} remaining={}",LIVE.load(SeqCst)-baseline);
 }
 assert_eq!(at,bytes.len());
}
