//! Native lifetime/copy shell for the shared XYGI/XYGR contract (§3).
use std::collections::HashMap;
use std::sync::atomic::Ordering;
use std::sync::{Arc, Mutex, OnceLock};

use xyg_engine::graphforge::interaction::wire::{self, Request, WireSession};
use xyg_engine::graphforge::interaction::{InteractionStatus, TemporalHandle, TemporalHost};
use xyg_engine::temporal_graph::TemporalGraph;

pub const GRAPHFORGE_MAX_SESSIONS: usize = 256;

struct Entry {
    instance: u64,
    opening: Vec<u8>,
    session: Mutex<Option<WireSession>>,
}

#[derive(Default)]
struct Registry {
    next: u64,
    entries: HashMap<u64, Arc<Entry>>,
}

fn registry() -> &'static Mutex<Registry> {
    static REGISTRY: OnceLock<Mutex<Registry>> = OnceLock::new();
    REGISTRY.get_or_init(|| Mutex::new(Registry::default()))
}

fn entry(handle: u64) -> Option<Arc<Entry>> {
    registry()
        .lock()
        .expect("graph session registry poisoned")
        .entries
        .get(&handle)
        .cloned()
}

/// The authoritative native owner, with no copied temporal graph/state. The
/// registry lookup ends before this adapter runs. Lock order is session ->
/// temporal operation -> temporal state; cancellation remains independent.
struct NativeHost {
    handle: u64,
    entry: Arc<super::NativeTemporalGraph>,
}

impl TemporalHost for NativeHost {
    fn owner_identity(&self) -> usize { Arc::as_ptr(&self.entry) as usize }
    fn with_graph(&self, handle: TemporalHandle, f: &mut dyn FnMut(&mut TemporalGraph)) -> bool {
        if handle.0 != self.handle || self.entry.disposed.load(Ordering::Acquire) {
            return false;
        }
        let _operation = self
            .entry
            .operation
            .lock()
            .expect("temporal operation poisoned");
        let mut state = self.entry.state.lock().expect("temporal state poisoned");
        if self.entry.disposed.load(Ordering::Acquire) {
            return false;
        }
        f(&mut state.graph);
        true
    }
}

unsafe fn input<'a>(ptr: *const u8, len: usize) -> Result<&'a [u8], InteractionStatus> {
    if len > wire::DEFAULT_MAX_BYTES || len != 0 && ptr.is_null() {
        return Err(InteractionStatus::Invalid);
    }
    if len == 0 {
        return Ok(&[]);
    }
    Ok(std::slice::from_raw_parts(ptr, len))
}

unsafe fn output_valid(out: *mut u8, cap: usize, len: *mut usize) -> bool {
    if len.is_null() {
        return false;
    }
    *len = 0;
    cap == 0 || !out.is_null()
}

unsafe fn copy_reply(reply: &[u8], out: *mut u8, cap: usize, out_len: *mut usize) -> i32 {
    *out_len = reply.len();
    if cap < reply.len() {
        return InteractionStatus::Capacity.number();
    }
    if !reply.is_empty() {
        std::ptr::copy_nonoverlapping(reply.as_ptr(), out, reply.len());
    }
    0
}

type TemporalBinding = (Arc<dyn TemporalHost>, TemporalHandle);

fn bind_owner(request: &Request<'_>) -> Result<Option<TemporalBinding>, InteractionStatus> {
    if request.operation != 18 {
        return Ok(None);
    }
    let handle = request.temporal()?;
    if handle == 0 {
        return Ok(None);
    }
    let owner = super::temporal_graph_entry(handle).ok_or(InteractionStatus::Unbound)?;
    Ok(Some((
        Arc::new(NativeHost {
            handle,
            entry: owner,
        }),
        TemporalHandle(handle),
    )))
}

/// `load` is a complete OPEN XYGI request. `document` must equal its embedded
/// document and the scalar identity/group must equal its header. Byte-identical
/// active-instance OPEN retries return the same handle even after later calls.
#[no_mangle]
pub unsafe extern "C" fn xyg_graphforge_session_create(
    document_bytes: *const u8,
    document_len: usize,
    load: *const u8,
    load_len: usize,
    instance_id: u64,
    group_id: u64,
    out_handle: *mut u64,
) -> i32 {
    super::ffi_guard(InteractionStatus::Invalid.number(), || {
        if out_handle.is_null() {
            return InteractionStatus::Invalid.number();
        }
        *out_handle = 0;
        let result = (|| {
            let document = input(document_bytes, document_len)?;
            let bytes = input(load, load_len)?;
            let request = Request::decode(bytes)?;
            if request.operation != wire::OPEN
                || request.instance != instance_id
                || request.group != group_id
                || request.document()? != document
            {
                return Err(InteractionStatus::Invalid);
            }
            let existing = {
                let registry = registry().lock().expect("graph session registry poisoned");
                registry
                    .entries
                    .iter()
                    .find(|(_, e)| e.instance == instance_id)
                    .map(|(h, e)| (*h, Arc::clone(e)))
            };
            if let Some((handle, existing)) = existing {
                if existing.opening != bytes {
                    return Err(InteractionStatus::Invalid);
                }
                existing
                    .session
                    .lock()
                    .expect("graph session poisoned")
                    .as_ref()
                    .ok_or(InteractionStatus::Unbound)?
                    .check_live()?;
                return Ok(handle);
            }
            if registry()
                .lock()
                .expect("graph session registry poisoned")
                .entries
                .len()
                >= GRAPHFORGE_MAX_SESSIONS
            {
                return Err(InteractionStatus::Capacity);
            }
            let session = WireSession::open(bytes, wire::DEFAULT_MAX_BYTES, bytes.len())?;
            let candidate = Arc::new(Entry {
                instance: instance_id,
                opening: bytes.to_vec(),
                session: Mutex::new(Some(session)),
            });
            // Another creator may have won while the document was validated.
            // Only scalar/byte comparison occurs under the global registry.
            let mut registry = registry().lock().expect("graph session registry poisoned");
            if let Some((handle, existing)) = registry
                .entries
                .iter()
                .find(|(_, e)| e.instance == instance_id)
            {
                return if existing.opening == bytes {
                    Ok(*handle)
                } else {
                    Err(InteractionStatus::Invalid)
                };
            }
            if registry.entries.len() >= GRAPHFORGE_MAX_SESSIONS {
                return Err(InteractionStatus::Capacity);
            }
            let handle = registry
                .next
                .checked_add(1)
                .ok_or(InteractionStatus::Capacity)?;
            registry.next = handle;
            registry.entries.insert(handle, candidate);
            Ok(handle)
        })();
        match result {
            Ok(handle) => {
                *out_handle = handle;
                0
            }
            Err(error) => error.number(),
        }
    })
}

unsafe fn command(
    handle: u64,
    bytes: *const u8,
    length: usize,
    out: *mut u8,
    cap: usize,
    out_len: *mut usize,
    allowed: impl FnOnce(u32) -> bool,
    poll: bool,
) -> i32 {
    super::ffi_guard(InteractionStatus::Invalid.number(), || {
        if !output_valid(out, cap, out_len) {
            return InteractionStatus::Invalid.number();
        }
        let result = (|| {
            let bytes = input(bytes, length)?;
            let request = Request::decode(bytes)?;
            if !allowed(request.operation) {
                return Err(InteractionStatus::Invalid);
            }
            let entry = entry(handle).ok_or(InteractionStatus::Unbound)?;
            let mut slot = entry.session.lock().expect("graph session poisoned");
            let session = slot.as_mut().ok_or(InteractionStatus::Unbound)?;
            let external = entry.opening.len();
            if poll {
                let required = session.poll(bytes, cap, external)?;
                *out_len = required;
                if cap < required {
                    return Ok(InteractionStatus::Capacity.number());
                }
                Ok(copy_reply(session.reply(), out, cap, out_len))
            } else {
                let owner = bind_owner(&request)?;
                let reply = session.execute(bytes, external, owner)?;
                Ok(copy_reply(reply, out, cap, out_len))
            }
        })();
        result.unwrap_or_else(InteractionStatus::number)
    })
}

#[no_mangle]
pub unsafe extern "C" fn xyg_graphforge_session_update(
    handle: u64,
    request: *const u8,
    request_len: usize,
    out: *mut u8,
    out_cap: usize,
    out_len: *mut usize,
) -> i32 {
    command(
        handle,
        request,
        request_len,
        out,
        out_cap,
        out_len,
        |op| op == wire::UPDATE,
        false,
    )
}

#[no_mangle]
pub unsafe extern "C" fn xyg_graphforge_session_render(
    handle: u64,
    request: *const u8,
    request_len: usize,
    out: *mut u8,
    out_cap: usize,
    out_len: *mut usize,
) -> i32 {
    command(
        handle,
        request,
        request_len,
        out,
        out_cap,
        out_len,
        |op| op == wire::RENDER,
        false,
    )
}

#[no_mangle]
pub unsafe extern "C" fn xyg_graphforge_session_interact(
    handle: u64,
    request: *const u8,
    request_len: usize,
    out: *mut u8,
    out_cap: usize,
    out_len: *mut usize,
) -> i32 {
    command(
        handle,
        request,
        request_len,
        out,
        out_cap,
        out_len,
        |op| op <= 18,
        false,
    )
}

#[no_mangle]
pub unsafe extern "C" fn xyg_graphforge_session_bind_temporal(
    handle: u64,
    request: *const u8,
    request_len: usize,
    out: *mut u8,
    out_cap: usize,
    out_len: *mut usize,
) -> i32 {
    command(
        handle,
        request,
        request_len,
        out,
        out_cap,
        out_len,
        |op| op == 18,
        false,
    )
}

#[no_mangle]
pub unsafe extern "C" fn xyg_graphforge_session_poll_event(
    handle: u64,
    request: *const u8,
    request_len: usize,
    out: *mut u8,
    out_cap: usize,
    out_len: *mut usize,
) -> i32 {
    command(
        handle,
        request,
        request_len,
        out,
        out_cap,
        out_len,
        |op| op == wire::POLL,
        true,
    )
}

#[no_mangle]
pub unsafe extern "C" fn xyg_graphforge_coordinate_deliver(
    handle: u64,
    request: *const u8,
    request_len: usize,
    out: *mut u8,
    out_cap: usize,
    out_len: *mut usize,
) -> i32 {
    command(
        handle,
        request,
        request_len,
        out,
        out_cap,
        out_len,
        |op| op == 16,
        false,
    )
}

#[no_mangle]
pub unsafe extern "C" fn xyg_graphforge_session_destroy(handle: u64) -> i32 {
    super::ffi_guard(InteractionStatus::Invalid.number(), || {
        let entry = registry()
            .lock()
            .expect("graph session registry poisoned")
            .entries
            .remove(&handle);
        let Some(entry) = entry else {
            return InteractionStatus::Unbound.number();
        };
        // Revoke raced clones; an already-running call completes before return.
        entry.session.lock().expect("graph session poisoned").take();
        0
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};
    use xyg_engine::graphforge::compose::compose_bytes;
    use xyg_engine::graphforge::container::{Builder, Container, DOCUMENT_MAGIC, REQUEST_MAGIC};

    static TEST_LOCK: Mutex<()> = Mutex::new(());
    static NEXT_INSTANCE: AtomicU64 = AtomicU64::new(1 << 60);

    struct Session(u64);
    impl Drop for Session {
        fn drop(&mut self) {
            unsafe {
                xyg_graphforge_session_destroy(self.0);
            }
        }
    }

    fn document() -> &'static [u8] {
        static DOCUMENT: OnceLock<Vec<u8>> = OnceLock::new();
        DOCUMENT.get_or_init(|| {
            let fixture = |name| {
                std::fs::read(format!(
                    "{}/../../tests/fixtures/graphforge/results/{name}.arrow",
                    env!("CARGO_MANIFEST_DIR")
                ))
                .unwrap()
            };
            let mut b = Builder::new(REQUEST_MAGIC);
            b.bytes("base.table", 0, &fixture("base-cyclic-nodes"));
            b.bytes("base.table", 1, &fixture("base-cyclic-edges"));
            b.bytes("layer.result", 0, &fixture("pagerank"));
            b.utf8("layer.intent", 0, "graph");
            compose_bytes(&b.finish()).unwrap()
        })
    }

    fn request(
        instance: u64,
        group: u64,
        seq: u64,
        revision: u32,
        operation: u32,
        add: impl FnOnce(&mut Builder),
    ) -> Vec<u8> {
        let mut b = Builder::new(wire::REQUEST_MAGIC);
        b.u64s("header.u64", 0, &[instance, group, seq]);
        b.u32s("header.u32", 0, &[revision, operation, 0, 0, 0, 0, 0, 0, 0]);
        add(&mut b);
        b.finish()
    }

    fn opening(instance: u64, group: u64) -> Vec<u8> {
        request(instance, group, 1, 0, wire::OPEN, |b| {
            let c = Container::decode(document(), DOCUMENT_MAGIC).unwrap();
            let n = c.get("node.uuid", 0).unwrap().count;
            b.bytes("document.bytes", 0, document());
            b.f64s(
                "load.x.f64",
                0,
                &(0..n).map(|i| i as f64 * 30.0).collect::<Vec<_>>(),
            );
            b.f64s("load.y.f64", 0, &vec![0.0; n]);
        })
    }

    unsafe fn create(bytes: &[u8], instance: u64, group: u64) -> Result<Session, i32> {
        let mut handle = 0;
        let status = xyg_graphforge_session_create(
            document().as_ptr(),
            document().len(),
            bytes.as_ptr(),
            bytes.len(),
            instance,
            group,
            &mut handle,
        );
        if status == 0 {
            Ok(Session(handle))
        } else {
            assert_eq!(handle, 0);
            Err(status)
        }
    }

    fn setup(group: u64) -> (Session, u64, Vec<u8>) {
        let instance = NEXT_INSTANCE.fetch_add(1, Ordering::Relaxed);
        let open = opening(instance, group);
        let session = unsafe { create(&open, instance, group).unwrap() };
        (session, instance, open)
    }

    type Command = unsafe extern "C" fn(u64, *const u8, usize, *mut u8, usize, *mut usize) -> i32;
    unsafe fn invoke(
        command: Command,
        handle: u64,
        bytes: &[u8],
        cap: usize,
    ) -> (i32, usize, Vec<u8>) {
        let mut output = vec![0xa5; cap];
        let mut len = usize::MAX;
        let status = command(
            handle,
            bytes.as_ptr(),
            bytes.len(),
            if cap == 0 {
                std::ptr::null_mut()
            } else {
                output.as_mut_ptr()
            },
            cap,
            &mut len,
        );
        (status, len, output)
    }

    unsafe fn complete(command: Command, handle: u64, bytes: &[u8]) -> Vec<u8> {
        let (status, required, _) = invoke(command, handle, bytes, 0);
        assert_eq!(status, InteractionStatus::Capacity.number());
        let (status, len, output) = invoke(command, handle, bytes, required);
        assert_eq!(status, 0);
        assert_eq!(len, required);
        output
    }

    fn revision(bytes: &[u8]) -> u32 {
        Container::decode(bytes, wire::RESULT_MAGIC)
            .unwrap()
            .get("header.u32", 0)
            .unwrap()
            .as_u32("header.u32")
            .unwrap()[0]
    }

    #[test]
    fn zero_short_exact_retry_is_atomic_and_create_retry_survives_commands() {
        let _test = TEST_LOCK.lock().unwrap();
        let (session, instance, open) = setup(0);
        let render = request(instance, 0, 2, 0, wire::RENDER, |_| {});
        unsafe {
            let (status, required, _) =
                invoke(xyg_graphforge_session_render, session.0, &render, 0);
            assert_eq!(status, -5);
            assert!(required > 0);
            let (status, len, untouched) = invoke(
                xyg_graphforge_session_render,
                session.0,
                &render,
                required - 1,
            );
            assert_eq!(status, -5);
            assert_eq!(len, required);
            assert!(untouched.iter().all(|b| *b == 0xa5));
            let (status, len, exact) =
                invoke(xyg_graphforge_session_render, session.0, &render, required);
            assert_eq!((status, len), (0, required));
            assert_eq!(revision(&exact), 1);
            assert_eq!(
                invoke(xyg_graphforge_session_render, session.0, &render, required).2,
                exact
            );
            let repeated = create(&open, instance, 0).unwrap();
            assert_eq!(repeated.0, session.0);
            std::mem::forget(repeated);
            let conflict = request(instance, 0, 1, 0, wire::OPEN, |b| {
                b.bytes("document.bytes", 0, document())
            });
            assert_eq!(create(&conflict, instance, 0).err(), Some(-3));
        }
    }

    #[test]
    fn pointer_validation_precedes_execution_and_endpoint_types_are_strict() {
        let _test = TEST_LOCK.lock().unwrap();
        let (session, instance, _) = setup(0);
        let render = request(instance, 0, 2, 0, wire::RENDER, |_| {});
        unsafe {
            let mut len = 99;
            assert_eq!(
                xyg_graphforge_session_render(
                    session.0,
                    render.as_ptr(),
                    render.len(),
                    std::ptr::null_mut(),
                    1,
                    &mut len
                ),
                -3
            );
            assert_eq!(len, 0);
            assert_eq!(
                xyg_graphforge_session_render(
                    session.0,
                    render.as_ptr(),
                    render.len(),
                    std::ptr::null_mut(),
                    0,
                    std::ptr::null_mut()
                ),
                -3
            );
            assert_eq!(
                invoke(xyg_graphforge_session_update, session.0, &render, 0).0,
                -3
            );
            assert_eq!(
                entry(session.0)
                    .unwrap()
                    .session
                    .lock()
                    .unwrap()
                    .as_ref()
                    .unwrap()
                    .session()
                    .render_revision(),
                0
            );
            assert_eq!(
                revision(&complete(xyg_graphforge_session_render, session.0, &render)),
                1
            );
        }
    }

    #[test]
    fn poll_short_does_not_consume_or_duplicate_event_and_style_refreshes_same_revision() {
        let _test = TEST_LOCK.lock().unwrap();
        let (session, instance, _) = setup(42);
        unsafe {
            let render = complete(
                xyg_graphforge_session_render,
                session.0,
                &request(instance, 42, 2, 0, wire::RENDER, |_| {}),
            );
            let ids = Container::decode(document(), DOCUMENT_MAGIC)
                .unwrap()
                .get("node.uuid", 0)
                .unwrap()
                .as_uuids("node.uuid")
                .unwrap();
            let select = request(instance, 42, 3, revision(&render), 10, |b| {
                b.uuids("uuids.uuid", 0, &ids[..1])
            });
            let selected = complete(xyg_graphforge_session_interact, session.0, &select);
            assert_eq!(revision(&selected), revision(&render));
            let initial = Container::decode(&render, wire::RESULT_MAGIC).unwrap();
            let changed = Container::decode(&selected, wire::RESULT_MAGIC).unwrap();
            assert_ne!(
                initial.get("render.visual_states.u8", 0).unwrap().payload,
                changed.get("render.visual_states.u8", 0).unwrap().payload
            );
            let poll = request(instance, 42, 4, revision(&selected), wire::POLL, |_| {});
            let (status, required, _) =
                invoke(xyg_graphforge_session_poll_event, session.0, &poll, 0);
            assert_eq!(status, -5);
            let (status, length, untouched) = invoke(
                xyg_graphforge_session_poll_event,
                session.0,
                &poll,
                required - 1,
            );
            assert_eq!((status, length), (-5, required));
            assert!(untouched.iter().all(|b| *b == 0xa5));
            let first = invoke(
                xyg_graphforge_session_poll_event,
                session.0,
                &poll,
                required,
            );
            assert_eq!(first.0, 0);
            let c = Container::decode(&first.2, wire::RESULT_MAGIC).unwrap();
            let event = wire::decode_event(c.get("outbound.bytes", 0).unwrap().payload).unwrap();
            assert_eq!(event.revision, 1);
            assert_eq!(event.refs.len(), 1);
            assert_eq!(
                invoke(
                    xyg_graphforge_session_poll_event,
                    session.0,
                    &poll,
                    required
                )
                .2,
                first.2
            );
            let next = complete(
                xyg_graphforge_session_poll_event,
                session.0,
                &request(instance, 42, 5, revision(&selected), wire::POLL, |_| {}),
            );
            assert!(Container::decode(&next, wire::RESULT_MAGIC)
                .unwrap()
                .get("outbound.bytes", 0)
                .is_none());
        }
    }

    #[test]
    fn destroyed_handles_and_raced_entry_clones_stay_unbound() {
        let _test = TEST_LOCK.lock().unwrap();
        let (session, instance, _) = setup(0);
        let raced = entry(session.0).unwrap();
        unsafe {
            assert_eq!(xyg_graphforge_session_destroy(session.0), 0);
            assert!(raced.session.lock().unwrap().is_none());
            assert_eq!(xyg_graphforge_session_destroy(session.0), -10);
            assert_eq!(
                invoke(
                    xyg_graphforge_session_render,
                    session.0,
                    &request(instance, 0, 2, 0, wire::RENDER, |_| {}),
                    0
                )
                .0,
                -10
            );
            let (next, _, _) = setup(0);
            assert!(next.0 > session.0);
        }
    }

    #[test]
    fn registry_enforces_256_live_sessions_and_recovers_capacity_without_reuse() {
        let _test = TEST_LOCK.lock().unwrap();
        let mut sessions = Vec::new();
        for _ in 0..GRAPHFORGE_MAX_SESSIONS {
            sessions.push(setup(0).0);
        }
        let instance = NEXT_INSTANCE.fetch_add(1, Ordering::Relaxed);
        let bytes = opening(instance, 0);
        unsafe {
            assert_eq!(create(&bytes, instance, 0).err(), Some(-5));
        }
        let previous = sessions.last().unwrap().0;
        drop(sessions.pop());
        let replacement = unsafe { create(&bytes, instance, 0).unwrap() };
        assert!(replacement.0 > previous);
    }

    #[test]
    fn coordinate_delivery_uses_shared_event_codec_and_never_rebroadcasts() {
        let _test = TEST_LOCK.lock().unwrap();
        let (sender, source, _) = setup(71);
        let (receiver, destination, _) = setup(71);
        let ids = Container::decode(document(), DOCUMENT_MAGIC)
            .unwrap()
            .get("node.uuid", 0)
            .unwrap()
            .as_uuids("node.uuid")
            .unwrap();
        unsafe {
            let selected = complete(
                xyg_graphforge_session_interact,
                sender.0,
                &request(source, 71, 2, 0, 10, |b| {
                    b.uuids("uuids.uuid", 0, &ids[..1])
                }),
            );
            let c = Container::decode(&selected, wire::RESULT_MAGIC).unwrap();
            let event = c.get("outbound.bytes", 0).unwrap().payload;
            let deliver = request(destination, 71, 2, 0, 16, |b| {
                b.bytes("remote.bytes", 0, event)
            });
            let delivered = complete(xyg_graphforge_coordinate_deliver, receiver.0, &deliver);
            let output = Container::decode(&delivered, wire::RESULT_MAGIC).unwrap();
            assert!(output.get("outbound.bytes", 0).is_none());
            assert_eq!(
                output
                    .get("header.u32", 0)
                    .unwrap()
                    .as_u32("header.u32")
                    .unwrap()[2],
                0
            );
            assert_eq!(
                entry(receiver.0)
                    .unwrap()
                    .session
                    .lock()
                    .unwrap()
                    .as_ref()
                    .unwrap()
                    .session()
                    .selection()
                    .unwrap()
                    .len(),
                1
            );
            let stale = request(destination, 71, 3, revision(&delivered), 16, |b| {
                b.bytes("remote.bytes", 0, event)
            });
            assert_eq!(
                invoke(xyg_graphforge_coordinate_deliver, receiver.0, &stale, 0).0,
                -7
            );
        }
    }

    #[test]
    fn resource_and_update_refusals_do_not_consume_sequence_or_replace_document() {
        let _test = TEST_LOCK.lock().unwrap();
        let (session, instance, _) = setup(0);
        let render = request(instance, 0, 2, 0, wire::RENDER, |_| {});
        let owner = entry(session.0).unwrap();
        owner.session.lock().unwrap().as_mut().unwrap().max_bytes = 1;
        unsafe {
            assert_eq!(
                invoke(xyg_graphforge_session_render, session.0, &render, 0).0,
                -4
            );
            assert_eq!(
                owner
                    .session
                    .lock()
                    .unwrap()
                    .as_ref()
                    .unwrap()
                    .session()
                    .render_revision(),
                0
            );
            owner.session.lock().unwrap().as_mut().unwrap().max_bytes = wire::DEFAULT_MAX_BYTES;
            let rendered = complete(xyg_graphforge_session_render, session.0, &render);
            let bad = request(instance, 0, 3, revision(&rendered), wire::UPDATE, |b| {
                b.bytes("document.bytes", 0, b"invalid")
            });
            assert_eq!(
                invoke(xyg_graphforge_session_update, session.0, &bad, 0).0,
                -3
            );
            assert_eq!(
                owner.session.lock().unwrap().as_ref().unwrap().reply(),
                rendered
            );
            let update = request(instance, 0, 3, revision(&rendered), wire::UPDATE, |b| {
                b.bytes("document.bytes", 0, document())
            });
            let updated = complete(xyg_graphforge_session_update, session.0, &update);
            assert_eq!(revision(&updated), revision(&rendered) + 1);
        }
    }

    fn temporal_owner() -> (u64, Arc<super::super::NativeTemporalGraph>) {
        use xyg_engine::projection::GraphProjection;
        use xyg_engine::temporal_graph::TemporalBindingInput;
        let c = Container::decode(document(), DOCUMENT_MAGIC).unwrap();
        let uuids = |name| c.get(name, 0).unwrap().as_uuids(name).unwrap();
        let nodes = uuids("node.uuid");
        let edges = uuids("edge.uuid");
        let dense = |name| c.get(name, 0).unwrap().as_u64(name).unwrap();
        let sources: Vec<_> = dense("edge.source")
            .into_iter()
            .map(|i| nodes[i as usize])
            .collect();
        let targets: Vec<_> = dense("edge.target")
            .into_iter()
            .map(|i| nodes[i as usize])
            .collect();
        let projection =
            GraphProjection::new(&nodes, &edges, &sources, &targets, None, true).unwrap();
        let graph = TemporalGraph::bind(
            &projection,
            TemporalBindingInput::default(),
            TemporalBindingInput::default(),
        )
        .unwrap();
        let entry = Arc::new(super::super::NativeTemporalGraph {
            operation: Mutex::new(()),
            state: Mutex::new(super::super::NativeTemporalGraphState {
                graph,
                frame: None,
                frozen: None,
            }),
            active_cancel: Mutex::new(None),
            disposed: std::sync::atomic::AtomicBool::new(false),
        });
        let mut registry = super::super::temporal_graph_registry().lock().unwrap();
        registry.0 = registry.0.checked_add(1).unwrap();
        let handle = registry.0;
        registry.1.insert(handle, entry.clone());
        (handle, entry)
    }

    #[test]
    fn bound_native_owner_is_authoritative_and_disposal_blocks_cached_replies_until_unbind() {
        let _test = TEST_LOCK.lock().unwrap();
        let (session, instance, _) = setup(0);
        let (temporal, owner) = temporal_owner();
        let nodes = owner.state.lock().unwrap().graph.node_ids().to_vec();
        owner
            .state
            .lock()
            .unwrap()
            .graph
            .set_selection([nodes[0]], [])
            .unwrap();
        unsafe {
            let binding = request(instance, 0, 2, 0, 18, |b| {
                b.u64s("temporal.u64", 0, &[temporal])
            });
            let bound = complete(xyg_graphforge_session_bind_temporal, session.0, &binding);
            assert_eq!(
                entry(session.0)
                    .unwrap()
                    .session
                    .lock()
                    .unwrap()
                    .as_ref()
                    .unwrap()
                    .session()
                    .selection()
                    .unwrap()
                    .len(),
                1
            );
            let select = request(instance, 0, 3, revision(&bound), 10, |b| {
                b.uuids("uuids.uuid", 0, &nodes[1..2])
            });
            let selected = complete(xyg_graphforge_session_interact, session.0, &select);
            assert_eq!(
                owner
                    .state
                    .lock()
                    .unwrap()
                    .graph
                    .interaction_state()
                    .selection()
                    .nodes
                    .iter()
                    .copied()
                    .collect::<Vec<_>>(),
                nodes[1..2]
            );
            assert_eq!(
                super::super::xyg_temporal_graph_frame(temporal, 1, 0, 0, 1, 100_000),
                0
            );
            let stale = request(instance, 0, 4, revision(&selected), 4, |_| {});
            assert_eq!(
                invoke(xyg_graphforge_session_interact, session.0, &stale, 0).0,
                -1
            );
            let refreshed = complete(
                xyg_graphforge_session_render,
                session.0,
                &request(instance, 0, 4, revision(&selected), wire::RENDER, |_| {}),
            );
            assert_eq!(revision(&refreshed), revision(&selected) + 1);
            let select = request(instance, 0, 5, revision(&refreshed), 10, |b| {
                b.uuids("uuids.uuid", 0, &nodes[..1])
            });
            let selected = complete(xyg_graphforge_session_interact, session.0, &select);
            assert_eq!(
                owner
                    .state
                    .lock()
                    .unwrap()
                    .graph
                    .interaction_state()
                    .selection()
                    .nodes
                    .iter()
                    .copied()
                    .collect::<Vec<_>>(),
                nodes[..1]
            );
            assert_eq!(super::super::xyg_temporal_graph_destroy(temporal), 0);
            assert_eq!(
                invoke(
                    xyg_graphforge_session_interact,
                    session.0,
                    &select,
                    selected.len()
                )
                .0,
                -10
            );
            let unbind = request(instance, 0, 6, revision(&selected), 18, |b| {
                b.u64s("temporal.u64", 0, &[0])
            });
            complete(xyg_graphforge_session_bind_temporal, session.0, &unbind);
            assert!(entry(session.0)
                .unwrap()
                .session
                .lock()
                .unwrap()
                .as_ref()
                .unwrap()
                .session()
                .selection()
                .unwrap()
                .is_empty());
        }
    }

    #[test]
    fn native_temporal_adapter_rechecks_disposal_after_waiting_for_operation_lock() {
        let _test = TEST_LOCK.lock().unwrap();
        let (handle, owner) = temporal_owner();
        let guard = owner.operation.lock().unwrap();
        let host = NativeHost {
            handle,
            entry: owner.clone(),
        };
        let (started_tx, started_rx) = std::sync::mpsc::channel();
        let worker = std::thread::spawn(move || {
            started_tx.send(()).unwrap();
            host.with_graph(TemporalHandle(handle), &mut |_| {
                panic!("disposed callback invoked")
            })
        });
        started_rx.recv().unwrap();
        assert!(registry().try_lock().is_ok());
        assert_eq!(super::super::xyg_temporal_graph_destroy(handle), 0);
        drop(guard);
        assert!(!worker.join().unwrap());
    }
}
