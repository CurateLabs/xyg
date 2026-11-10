//! Requested-byte allocation ledger, isolated in its own test executable.
use std::alloc::{GlobalAlloc, Layout, System};
use std::io::Write;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering::SeqCst};
static STATE_TAG: AtomicBool = AtomicBool::new(false);
static STATE_MAX: AtomicUsize = AtomicUsize::new(0);
use xyg_engine::graphforge::{container::Builder, interaction::wire::WireSession};
static LIVE: AtomicUsize = AtomicUsize::new(0);
static PEAK: AtomicUsize = AtomicUsize::new(0);
// libtest's captured println buffer can grow during a measured interval and
// outlive the graph owner. Write diagnostics directly so the allocation oracle
// behaves identically under normal cargo test and --nocapture.
macro_rules! report {
    ($($args:tt)*) => {
        writeln!(std::io::stdout().lock(), $($args)*).unwrap()
    };
}
struct Counting;
fn add(n: usize) {
    if STATE_TAG.load(SeqCst) {
        STATE_MAX.fetch_max(n, SeqCst);
    }
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
    uuid_state_ledger();
    pick_tree_ledger();
    semantic_notebook_ledger();
    for sections in [1, 64, 512, 2000] {
        ledger_with_extensions(2, false, sections);
    }
    ledger(1000, false);
    ledger(1000, true);
    ledger(10000, false);
}

fn semantic_notebook_ledger() {
    use xyg_engine::graphforge::{compose::compose_bytes, container::Container};
    let n = 10_000;
    let uuid = |kind: u8, i: usize| {
        let mut id = [0; 16];
        id[0] = kind;
        id[6] = 0x70;
        id[8..].copy_from_slice(&(i as u64).to_be_bytes());
        id[8] |= 0x80;
        id
    };
    let nodes: Vec<_> = (0..n).map(|i| uuid(1, i)).collect();
    let edges: Vec<_> = (0..2 * n).map(|i| uuid(2, i)).collect();
    let mut sources = Vec::with_capacity(2 * n);
    let mut targets = Vec::with_capacity(2 * n);
    for i in 0..n {
        let chord = (7 * i + 3) % n;
        sources.extend([nodes[i]; 2]);
        targets.extend([
            nodes[(i + 1) % n],
            nodes[if chord == i { (chord + 1) % n } else { chord }],
        ]);
    }
    let mut b = Builder::new(b"XYGQ");
    b.uuids("base.node_uuid", 0, &nodes);
    b.uuids("base.edge_uuid", 0, &edges);
    b.uuids("base.edge_source_uuid", 0, &sources);
    b.uuids("base.edge_target_uuid", 0, &targets);
    b.uuids("base.generation", 0, &[uuid(3, 1)]);
    b.u8s("base.directed", 0, &[0]);
    // Exercise the real semantic composition, including labels, style planes,
    // provenance, legend and decisions; no stripped plain-document substitute.
    let document = compose_bytes(&b.finish()).unwrap();
    let c = Container::decode(&document, b"XYGF").unwrap();
    assert_eq!(c.get("node.label", 0).unwrap().count, n);
    assert_eq!(c.get("edge.status", 0).unwrap().count, 2 * n);
    let base = request(1, 0, 19, Some(&document));
    let mut b = Builder::new(b"XYGI");
    b.extend_from(&Container::decode(&base, b"XYGI").unwrap());
    b.f64s(
        "load.x.f64",
        0,
        &(0..n).map(|i| (i % 200) as f64 * 20.).collect::<Vec<_>>(),
    );
    b.f64s(
        "load.y.f64",
        0,
        &(0..n).map(|i| (i / 200) as f64 * 20.).collect::<Vec<_>>(),
    );
    let open = b.finish();
    let baseline = LIVE.load(SeqCst);
    PEAK.store(baseline, SeqCst);
    let arena = 384 << 20;
    let mut s = WireSession::open(&open, arena, open.len()).unwrap();
    assert!(LIVE.load(SeqCst) - baseline <= s.retained_budget());
    assert!(PEAK.load(SeqCst) - baseline <= arena);
    assert_eq!(
        s.ownership_bytes().unwrap().into_iter().sum::<usize>(),
        s.retained_budget()
    );
    report!(
        "SEMANTIC_OPEN nodes={n} edges={} document={} retained={} live={} peak={}",
        2 * n,
        document.len(),
        s.retained_budget(),
        LIVE.load(SeqCst) - baseline,
        PEAK.load(SeqCst) - baseline
    );
    let mut b = Builder::new(b"XYGI");
    b.extend_from(&Container::decode(&request(2, 0, 10, None), b"XYGI").unwrap());
    b.uuids("uuids.uuid", 0, &[nodes[0], edges[1]]);
    let command = b.finish();
    let admitted = s.preflight_bytes(&command, command.len()).unwrap();
    // The first gate admits source/kernel work. Paint and serialization have
    // subsequent gates against the same arena, before their own allocations.
    // Exact first-gate admission is insufficient here: require late refusal
    // within that arena, atomic state/reply, then same-sequence recovery.
    let mut old_reply = [0u8; 1024];
    let old_len = s.reply().len();
    old_reply[..old_len].copy_from_slice(s.reply());
    let old_work = s.session().work();
    s.max_bytes = admitted;
    PEAK.store(LIVE.load(SeqCst), SeqCst);
    assert_eq!(
        s.execute(&command, command.len(), None),
        Err(xyg_engine::graphforge::interaction::InteractionStatus::Budget)
    );
    assert!(PEAK.load(SeqCst) - baseline <= admitted);
    assert_eq!(s.reply(), &old_reply[..old_len]);
    assert_eq!(s.session().render_revision(), 0);
    assert_eq!(s.session().work(), old_work);
    assert!(s.session().selection().unwrap().is_empty());
    report!(
        "SEMANTIC_LATE_REFUSAL arena={admitted} peak={}",
        PEAK.load(SeqCst) - baseline
    );
    s.max_bytes = arena;
    PEAK.store(LIVE.load(SeqCst), SeqCst);
    s.execute(&command, command.len(), None).unwrap();
    assert!(PEAK.load(SeqCst) - baseline <= arena);
    assert!(LIVE.load(SeqCst) - baseline <= s.retained_budget() + command.len());
    assert_eq!(s.session().identity().node_uuids(), nodes);
    assert!(s
        .session()
        .identity()
        .persisted_edge_uuids()
        .eq(edges.iter().copied()));
    assert_eq!(s.session().selection().unwrap().len(), 2);
    let p = s.session().published().unwrap();
    assert_eq!((p.node_count(), p.edge_count()), (n, 2 * n));
    assert_eq!(
        p.source_node_flags[0] & xyg_engine::graph_style::FLAG_SELECTED,
        xyg_engine::graph_style::FLAG_SELECTED
    );
    assert_eq!(
        p.source_edge_flags[1] & xyg_engine::graph_style::FLAG_SELECTED,
        xyg_engine::graph_style::FLAG_SELECTED
    );
    report!(
        "SEMANTIC_SELECT admitted={admitted} retained={} live={} peak={}",
        s.retained_budget(),
        LIVE.load(SeqCst) - baseline,
        PEAK.load(SeqCst) - baseline
    );
    drop(s);
    drop(command);
    assert_eq!(LIVE.load(SeqCst), baseline);
}
fn ledger(n: usize, authored: bool) {
    ledger_with_extensions(n, authored, 0);
}
fn ledger_with_extensions(n: usize, authored: bool, extensions: usize) {
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
    for i in 0..extensions {
        b.bytes(&format!("extension.{i}"), 0, &[23; 16]);
    }
    let document = b.finish();
    let mut open = request(1, 0, 19, Some(&document));
    if authored {
        let mut b = Builder::new(b"XYGI");
        b.extend_from(
            &xyg_engine::graphforge::container::Container::decode(&open, b"XYGI").unwrap(),
        );
        b.f64s(
            "load.x.f64",
            0,
            &(0..n)
                .map(|i| (i % 40) as f64 * 15. - 300.)
                .collect::<Vec<_>>(),
        );
        b.f64s(
            "load.y.f64",
            0,
            &(0..n)
                .map(|i| (i / 40) as f64 * 12. - 150.)
                .collect::<Vec<_>>(),
        );
        open = b.finish();
    }
    if let Ok(dir) = std::env::var("XYG_MEMORY_CAPTURE") {
        std::fs::write(format!("{dir}/open-{n}.xygi"), &open).unwrap();
    }
    let baseline = LIVE.load(SeqCst);
    PEAK.store(baseline, SeqCst);
    let limit = if extensions == 0 {
        (if n == 1000 { 16 } else { 384 }) * 1024 * 1024
    } else {
        assert_eq!(n, 2);
        // Four UUIDs (64), two four-slot u32 indices (32), roots/masks (20),
        // endpoints/ordinals (40), complete raw retry upper bound, and the
        // descriptor allowance beyond the first64. Independent owner math.
        let section_count =
            xyg_engine::graphforge::container::Container::decode(&document, b"XYGF")
                .unwrap()
                .sections
                .len();
        102_400 + 96 + 60 + open.len() + section_count.saturating_sub(64) * 512
    };
    let external = if extensions == 0 { open.len() } else { 0 };
    if extensions != 0 {
        assert!(matches!(
            WireSession::open(&open, limit - 1, external),
            Err(xyg_engine::graphforge::interaction::InteractionStatus::Budget)
        ));
        assert!(PEAK.load(SeqCst) - baseline < limit);
    }
    let mut session = WireSession::open(&open, limit, external).unwrap();
    report!(
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
    assert_eq!(
        session
            .ownership_bytes()
            .unwrap()
            .into_iter()
            .sum::<usize>(),
        session.retained_budget()
    );
    assert!(LIVE.load(SeqCst) - baseline <= session.retained_budget());
    if extensions != 0 {
        assert!(PEAK.load(SeqCst) - baseline <= limit);
        report!(
            "DESCRIPTOR_OPEN sections={extensions} arena={limit} live={} peak={}",
            LIVE.load(SeqCst) - baseline,
            PEAK.load(SeqCst) - baseline
        );
        drop(session);
        assert_eq!(LIVE.load(SeqCst), baseline);
        return;
    }
    let before_clone = LIVE.load(SeqCst);
    let candidate = session.session().clone();
    let clone_bytes = LIVE.load(SeqCst) - before_clone;
    assert!(clone_bytes <= n * (if authored { 17 } else { 1 }) + 8192);
    assert_eq!(candidate.identity().node_uuids(), node_ids);
    drop(candidate);
    assert_eq!(LIVE.load(SeqCst), before_clone);
    report!("SOURCE_SHARED_CLONE n={n} authored={authored} requested={clone_bytes}");
    let mut render = request(2, 0, 21, None);
    if n == 1000 {
        let c = xyg_engine::graphforge::container::Container::decode(&render, b"XYGI").unwrap();
        let section = c.get("camera.f64", 0).unwrap();
        let start = section.payload.as_ptr() as usize - render.as_ptr() as usize;
        render[start..start + 8]
            .copy_from_slice(&(if authored { 1.0f64 } else { 0.25f64 }).to_le_bytes());
        render[start + 8..start + 16]
            .copy_from_slice(&(if authored { 1.0f64 } else { 0.25f64 }).to_le_bytes());
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
    report!(
        "RENDER output={} live={} peak={}",
        reply.len(),
        LIVE.load(SeqCst) - baseline,
        PEAK.load(SeqCst) - baseline
    );
    if authored {
        let output_bytes = reply.len();
        let p = session.session().published().unwrap();
        assert_eq!(
            (p.node_count(), p.edge_count(), p.paint.pieces.len()),
            (n, n, n)
        );
        assert!(output_bytes <= 131072 + 208 * n + 336 * n);
        assert!(PEAK.load(SeqCst) - baseline < session.max_bytes);
        report!(
            "AUTHORED full geometry output={} peak={}",
            output_bytes,
            PEAK.load(SeqCst) - baseline
        );
        drop(session);
        drop(render);
        return;
    }
    let candidate_baseline = LIVE.load(SeqCst);
    let candidate = session.session().clone();
    let private = LIVE.load(SeqCst) - candidate_baseline;
    assert!(
        private <= n + 16384,
        "publication/force/source must remain shared, cloned {private}"
    );
    drop(candidate);
    assert_eq!(LIVE.load(SeqCst), candidate_baseline);
    let step = request(3, rev, 15, None);
    session.execute(&step, open.len(), None).unwrap();
    report!(
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
            assert!(session
                .session()
                .identity()
                .persisted_edge_uuids()
                .eq(edge_ids.iter().copied()));
            assert_eq!(session.session().positions().unwrap().0.len(), n);
            let p = session.session().published().unwrap();
            assert_eq!((p.node_count(), p.edge_count()), (n, n));
            report!(
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
        let center = session.session().published().unwrap().paint.nodes[0].center;
        let base = request(41, session.session().render_revision(), 1, None);
        let mut b = Builder::new(b"XYGI");
        b.extend_from(
            &xyg_engine::graphforge::container::Container::decode(&base, b"XYGI").unwrap(),
        );
        b.f64s("coordinates.f64", 0, &center);
        let pick = b.finish();
        session.execute(&pick, open.len(), None).unwrap();
        assert!(PEAK.load(SeqCst) - baseline < session.max_bytes);
        report!(
            "CONVERGED_PICK n={n} live={} peak={}",
            LIVE.load(SeqCst) - baseline,
            PEAK.load(SeqCst) - baseline
        );
        let update = request(42, session.session().render_revision(), 20, Some(&document));
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
        report!(
            "UPDATE failure/retry live={} peak={} retained={}",
            LIVE.load(SeqCst) - baseline,
            PEAK.load(SeqCst) - baseline,
            session.retained_budget()
        );
        drop(old_reply);
        drop(accepted);
        session.max_bytes = 16 * 1024 * 1024;
        let after = request(43, session.session().render_revision(), 15, None);
        session.execute(&after, open.len(), None).unwrap();
    }
    assert_eq!(
        session
            .ownership_bytes()
            .unwrap()
            .into_iter()
            .sum::<usize>(),
        session.retained_budget()
    );
    assert!(LIVE.load(SeqCst) - baseline <= session.retained_budget());
    let retry = session.reply().to_vec();
    if n != 1000 {
        assert_eq!(session.execute(&step, usize::MAX, None).unwrap(), retry);
    }
    drop(retry);
    let p = session.session().published().unwrap();
    report!(
        "PUBLICATION nodes={} edges={} grid_entries={} primitives={}",
        p.node_count(),
        p.edge_count(),
        p.pick.grid_entries(),
        p.pick.primitive_count()
    );
    drop(session);
    drop(render);
    drop(step);
    report!(
        "DISPOSE n={n} remaining_delta={}",
        LIVE.load(SeqCst) as isize - baseline as isize
    );
}

// Rust 1.96 UUID B-trees allocate 192-byte leaves and 288-byte internal
// nodes on this 64-bit host. Every nonempty node owns at least one key;
// at most thirteen empty roots are covered by the fixed metadata reserve.
fn uuid_state_ledger() {
    use xyg_engine::graph_interaction_state::{
        ElementSet, GraphInteractionState, HighlightPlane, SelectMode,
    };
    for n in [0usize, 1, 5, 11, 12, 63, 1000, 5000] {
        let ids: Vec<_> = (0..n)
            .map(|i| {
                let mut id = [0u8; 16];
                id[..8].copy_from_slice(&(i as u64 + 1).to_le_bytes());
                id
            })
            .collect();
        let mut delta = ElementSet::default();
        delta.nodes.extend(ids.iter().rev());
        delta.edges.extend(ids.iter());
        STATE_MAX.store(0, SeqCst);
        STATE_TAG.store(true, SeqCst);
        let copy = delta.nodes.clone();
        STATE_TAG.store(false, SeqCst);
        let largest = STATE_MAX.load(SeqCst);
        drop(copy);
        let baseline = LIVE.load(SeqCst);
        PEAK.store(baseline, SeqCst);
        let mut state = GraphInteractionState::default();
        state.select(SelectMode::Replace, &delta).unwrap();
        for plane in [
            HighlightPlane::Path,
            HighlightPlane::Community,
            HighlightPlane::External,
        ] {
            state.highlight(plane, SelectMode::Replace, &delta).unwrap();
        }
        state.set_pinned(ids.iter().copied().collect());
        let live = LIVE.load(SeqCst) - baseline;
        let peak = PEAK.load(SeqCst) - baseline;
        assert!(largest <= 288, "UUID tree node width changed: {largest}");
        assert!(live <= 1024 + 288 * 9 * n + 8192);
        assert!(peak <= 1024 + 288 * 13 * n + 8192);
        let empty = ElementSet::default();
        state.select(SelectMode::Replace, &empty).unwrap();
        for plane in [
            HighlightPlane::Path,
            HighlightPlane::Community,
            HighlightPlane::External,
        ] {
            state.highlight(plane, SelectMode::Replace, &empty).unwrap();
        }
        state.set_pinned(Default::default());
        assert!(LIVE.load(SeqCst) - baseline <= 8192);
        report!("UUID_TREE n={n} references={} live={live} peak={peak} largest_node={largest} cleared={}",9*n,LIVE.load(SeqCst)-baseline);
        drop(state);
        drop(empty);
    }
}

// Pick candidates use full u32 primitive indices. Pinned Rust 1.96 B-tree
// internal nodes are at most160 bytes; Vec<Primitive> growth adds at most32
// bytes per entry on the widest supported host. The cap+1 refusal is charged.
fn pick_tree_ledger() {
    for n in [0u32, 1, 11, 12, 63, 1000, 65537] {
        let keys: std::collections::BTreeSet<u32> = (0..n).collect();
        STATE_MAX.store(0, SeqCst);
        STATE_TAG.store(true, SeqCst);
        let copy = keys.clone();
        STATE_TAG.store(false, SeqCst);
        let largest = STATE_MAX.load(SeqCst);
        assert!(largest <= 160, "pick B-tree node width changed: {largest}");
        drop(copy);
        report!("PICK_TREE n={n} largest_node={largest} query_width_bound=192");
    }
}
