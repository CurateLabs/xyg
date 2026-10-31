//! Thin staging/lifetime adapter for the shared Rust session wire (§3).
use super::{fail, Instance};
use xyg_engine::graphforge::interaction::{
    wire::{self, Request, WireSession},
    InteractionStatus,
};

fn external(instance: &Instance, staging: usize) -> Option<usize> {
    // Settled foreign jobs have no retained scratch. Reject active jobs rather
    // than under-accounting opaque job allocations.
    if instance.aggregate_job.is_some()
        || instance.stream_aggregate_job.is_some()
        || instance.graph_job.is_some()
        || instance.compile_job.is_some()
        || instance.temporal.is_some()
    {
        return None;
    }
    staging
        .checked_add(instance.output.capacity())?
        .checked_add(
            instance
                .temporal_graph
                .as_ref()
                .map_or(0, |t| t.retained_bytes()),
        )
}

pub(super) fn execute(instance: &mut Instance, offset: usize, length: usize, expected: u32) -> i32 {
    let arena = std::mem::take(&mut instance.arena);
    let result = (|| {
        if instance.geo_transport.is_some() {
            return Err(InteractionStatus::Invalid);
        }
        let bytes = arena
            .get(
                offset
                    ..offset
                        .checked_add(length)
                        .ok_or(InteractionStatus::Invalid)?,
            )
            .ok_or(InteractionStatus::Invalid)?;
        let r = Request::decode(bytes)?;
        if r.operation != expected
            && !(expected == u32::MAX && (r.operation <= 18 || r.operation == wire::POLL))
        {
            return Err(InteractionStatus::Invalid);
        }
        let charge = external(instance, arena.capacity()).ok_or(InteractionStatus::Budget)?;
        if expected == wire::OPEN {
            if let Some(session) = &instance.graph_session {
                if !session.opening_matches(bytes) {
                    return Err(InteractionStatus::Invalid);
                }
                session.check_live()?;
                instance.output = session.opening_reply().to_vec();
            } else {
                let session = WireSession::open(bytes, instance.max_arena_bytes, charge)?;
                instance.output = session.reply().to_vec();
                instance.graph_session = Some(session);
            }
        } else {
            let binding = if r.operation == 18 {
                match r.temporal()? {
                    0 => None,
                    1 => Some(
                        instance
                            .temporal_graph
                            .as_ref()
                            .ok_or(InteractionStatus::Unbound)?
                            .owner(),
                    ),
                    _ => return Err(InteractionStatus::Invalid),
                }
            } else {
                None
            };
            let session = instance
                .graph_session
                .as_mut()
                .ok_or(InteractionStatus::Unbound)?;
            session.max_bytes = instance.max_arena_bytes;
            if r.operation == wire::POLL {
                session.poll(bytes, usize::MAX, charge)?;
                instance.output = session.reply().to_vec();
            } else {
                instance.output = session.execute(bytes, charge, binding)?.to_vec();
            }
        }
        Ok(())
    })();
    match result {
        Ok(()) => {
            instance.last_error.clear();
            0
        }
        Err(e) => fail(instance, e.number(), e.code()),
    }
}

#[cfg(test)]
mod tests {
    use super::super::*;
    use xyg_engine::graphforge::container::{Builder, Container, DOCUMENT_MAGIC};
    use xyg_engine::graphforge::interaction::wire;
    use xyg_engine::temporal::CancelFlag;
    fn doc() -> Vec<u8> {
        let mut b = Builder::new(DOCUMENT_MAGIC);
        b.u32s("status", 0, &[0]);
        b.utf8("kind", 0, "graph");
        b.u32s("composition.version", 0, &[2]);
        b.uuids("node.uuid", 0, &[[1; 16], [2; 16]]);
        b.uuids("edge.uuid", 0, &[[3; 16]]);
        b.u8s("edge.derived", 0, &[0]);
        b.u32s("edge.layer", 0, &[u32::MAX]);
        b.i64s("edge.order", 0, &[-1]);
        b.u64s("edge.path", 0, &[u64::MAX]);
        b.u64s("edge.source", 0, &[0]);
        b.u64s("edge.target", 0, &[1]);
        b.finish()
    }
    fn request(seq: u64, rev: u32, op: u32, extra: impl FnOnce(&mut Builder)) -> Vec<u8> {
        let mut b = Builder::new(wire::REQUEST_MAGIC);
        b.u64s("header.u64", 0, &[7, 9, seq]);
        b.u32s("header.u32", 0, &[rev, op, 0, 0, 0, 0, 0, 0, 0]);
        extra(&mut b);
        b.finish()
    }
    fn open() -> Vec<u8> {
        request(1, 0, 19, |b| {
            b.bytes("document.bytes", 0, &doc());
            b.f64s("load.x.f64", 0, &[0., 40.]);
            b.f64s("load.y.f64", 0, &[0., 0.]);
        })
    }
    fn call(handle: u32, bytes: &[u8], f: extern "C" fn(u32, usize, usize) -> i32) -> i32 {
        assert_eq!(xyg_wasm_arena_resize(handle, bytes.len()), STATUS_OK);
        with_instance_mut(handle, |i| i.arena.copy_from_slice(bytes)).unwrap();
        f(handle, 0, bytes.len())
    }
    fn output(handle: u32) -> Vec<u8> {
        with_instance_mut(handle, |i| i.output.clone()).unwrap()
    }
    fn revision(handle: u32) -> u32 {
        Container::decode(&output(handle), wire::RESULT_MAGIC)
            .unwrap()
            .get("header.u32", 0)
            .unwrap()
            .as_u32("header.u32")
            .unwrap()[0]
    }
    fn temporal_create() -> Vec<u8> {
        let mut b = Vec::new();
        b.extend_from_slice(b"XYTG");
        for v in [1u32, 32, 1, 0, 2, 1, 0] {
            b.extend_from_slice(&v.to_le_bytes());
        }
        for id in [[1; 16], [2; 16], [3; 16], [1; 16], [2; 16]] {
            b.extend_from_slice(&id);
        }
        b
    }
    #[test]
    fn wasm_open_retry_memory_refusal_close_and_transport_conflicts() {
        let h = xyg_wasm_instance_new(64 * 1024 * 1024);
        assert_eq!(call(h, &open(), xyg_wasm_graphforge_session_open), 0);
        let ack = output(h);
        assert_eq!(
            call(
                h,
                &request(2, 0, 21, |_| {}),
                xyg_wasm_graphforge_session_render
            ),
            0
        );
        assert_ne!(output(h), ack);
        assert_eq!(call(h, &open(), xyg_wasm_graphforge_session_open), 0);
        assert_eq!(output(h), ack);
        let snapshot = with_instance_mut(h, |i| {
            let s = i.graph_session.as_ref().unwrap();
            (
                s.session().render_revision(),
                s.session().positions().unwrap().0.to_vec(),
            )
        })
        .unwrap();
        let mut b = Builder::new(wire::REQUEST_MAGIC);
        b.u64s("header.u64", 0, &[7, 9, 3]);
        b.u32s("header.u32", 0, &[snapshot.0, 15, 0, 0, 0, 0, 0, 1, 0]);
        let bytes = b.finish();
        with_instance_mut(h, |i| {
            i.max_arena_bytes = i.graph_session.as_ref().unwrap().retained_budget() + bytes.len()
        })
        .unwrap();
        assert_eq!(call(h, &bytes, xyg_wasm_graphforge_session_interact), -4);
        with_instance_mut(h, |i| {
            let s = i.graph_session.as_ref().unwrap();
            assert_eq!(s.session().render_revision(), snapshot.0);
            assert_eq!(s.session().positions().unwrap().0, snapshot.1);
            i.max_arena_bytes = 64 * 1024 * 1024;
        })
        .unwrap();
        assert_eq!(xyg_wasm_graph_begin(h, 1, 1, 0, 0), STATUS_INVALID_ARGUMENT);
        assert_eq!(xyg_wasm_graphforge_session_close(h), 0);
        assert_eq!(xyg_wasm_graphforge_session_close(h), -10);
        assert_eq!(call(h, &open(), xyg_wasm_graphforge_session_open), 0);
        assert_eq!(xyg_wasm_geo_transport_acquire(h), STATUS_OK);
        with_instance_mut(h, |i| {
            assert!(i.graph_session.is_none());
            assert!(i.temporal_graph.is_none());
        })
        .unwrap();
        assert_eq!(
            call(
                h,
                &request(2, 0, 21, |_| {}),
                xyg_wasm_graphforge_session_render
            ),
            -3
        );
        assert_eq!(xyg_wasm_instance_dispose(h), STATUS_OK);
        assert_eq!(xyg_wasm_graphforge_session_close(h), -10);
        let tiny = xyg_wasm_instance_new(1024 * 1024);
        assert_eq!(call(tiny, &open(), xyg_wasm_graphforge_session_open), -4);
        with_instance_mut(tiny, |i| assert!(i.graph_session.is_none())).unwrap();
        xyg_wasm_instance_dispose(tiny);
    }
    #[test]
    fn wasm_bound_frame_refresh_replacement_disposal_and_instance_isolation() {
        let h = xyg_wasm_instance_new(64 * 1024 * 1024);
        let other = xyg_wasm_instance_new(64 * 1024 * 1024);
        assert_eq!(
            call(h, &temporal_create(), xyg_wasm_temporal_graph_execute),
            STATUS_OK
        );
        assert_eq!(call(h, &open(), xyg_wasm_graphforge_session_open), 0);
        assert_eq!(call(other, &open(), xyg_wasm_graphforge_session_open), 0);
        let bind = request(2, 0, 18, |b| b.u64s("temporal.u64", 0, &[1]));
        assert_eq!(
            call(other, &bind, xyg_wasm_graphforge_session_interact),
            -10
        );
        assert_eq!(call(h, &bind, xyg_wasm_graphforge_session_interact), 0);
        let old = revision(h);
        let (owner, handle) =
            with_instance_mut(h, |i| i.temporal_graph.as_ref().unwrap().owner()).unwrap();
        owner.with_graph(handle, &mut |g| {
            g.frame(1, 5, 0, 10, &CancelFlag::new(), 1_000_000).unwrap();
        });
        assert_eq!(
            call(
                h,
                &request(3, old, 4, |_| {}),
                xyg_wasm_graphforge_session_interact
            ),
            -1
        );
        assert_eq!(
            call(
                h,
                &request(3, old, 21, |_| {}),
                xyg_wasm_graphforge_session_render
            ),
            0
        );
        let fresh = revision(h);
        assert!(fresh > old);
        assert_eq!(
            call(h, &temporal_create(), xyg_wasm_temporal_graph_execute),
            STATUS_OK
        );
        assert!(!owner.with_graph(handle, &mut |_| panic!("replaced owner usable")));
        assert_eq!(
            call(
                h,
                &request(3, old, 21, |_| {}),
                xyg_wasm_graphforge_session_render
            ),
            -10
        );
        assert_eq!(
            call(
                h,
                &request(4, fresh, 18, |b| b.u64s("temporal.u64", 0, &[0])),
                xyg_wasm_graphforge_session_interact
            ),
            0
        );
        let current = revision(h);
        assert_eq!(
            call(
                h,
                &request(5, current, 18, |b| b.u64s("temporal.u64", 0, &[1])),
                xyg_wasm_graphforge_session_interact
            ),
            0
        );
        let (owner, handle) =
            with_instance_mut(h, |i| i.temporal_graph.as_ref().unwrap().owner()).unwrap();
        assert_eq!(xyg_wasm_instance_dispose(h), STATUS_OK);
        assert!(!owner.with_graph(handle, &mut |_| panic!("disposed instance usable")));
        assert_eq!(
            call(
                other,
                &request(2, 0, 21, |_| {}),
                xyg_wasm_graphforge_session_render
            ),
            0
        );
        xyg_wasm_instance_dispose(other);
    }
}
