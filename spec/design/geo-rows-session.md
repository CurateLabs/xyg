# Bounded original geographic rows

`geo_rows_session.rs` supplies the Rust full-source companion foundation required
by dossier §20/§27 and #50/#39. It pages canonical original rows independently
of painted vertices, aggregate cells, viewport bounds or visibility. It adds no
chart surface and does not itself implement keyboard navigation, selection or
linked views. The generic native/WASM protocol, Python/Node adapters and browser
companion below integrate paging; linked selection and all-host live journeys
remain separate #50 gates.

## Identity and eligibility

`GeoRowsSession::create(validated_source, nonzero_sequence, GeoRowsKey,
optional_issued_cursor, QueryBudget)` validates before cloning or issuing I/O.
The key contains exact source digest, generation, row count, geometry, CRS,
layer ID/layer revision, state revision, signed `TimePredicate` and time revision.
Camera and reduced tier are deliberately absent: offscreen rows remain reachable.
A later camera change cannot redefine original source identity; a source/time/
layer/state change requires a new traversal and invalidates its cursor.

Every original row, including null geometry and time-excluded rows, produces one
`GeoRowsRecord`: literal `FeatureRef` (chunk, local row, original source ordinal,
full-u64 feature ID), geometry-null, time-eligible and eligible booleans, interval
presence and optional signed endpoints, and optional scalar f64. `eligible` means
non-null geometry AND the shared half-open temporal predicate. It does not assert
visibility or hidden-state eligibility. Explicit selected intent is described
below; state revision binds page identity without a source-sized state plane. Missing interval attachment is
distinguished from attached unbounded endpoints; scalar bits including signed
zero/NaN/infinity are preserved CPU metadata, never GPU vertices.

`GeoChunk::all_rows()` shares canonical topology/interval/scalar extraction with
existing valid-only `rows()`. Packed Point nulls do not shift following vertices.
MultiPoint emits one row regardless of vertex count; duplicate feature IDs remain
distinct source rows. No row mask, geometry copy, spatial projection, screen
filter or temporal zone-map pruning hides excluded rows. Time eligibility is
computed without inspecting geometry coordinates.

## Issued continuation authority

`GeoRowsCursor` has private key and source position fields and no public ordinal
or decode constructor. It is issued only by a completed page; `key()` and
`position()` expose diagnostic/encoding values without creating skip authority.
A resumed session validates the complete key, source/query digest and exact chunk/
row bounds before admission. The transport must retain the issued cursor in an
owned RowsData authority and resolve continuation from that authority. It must
not reconstruct trusted cursors from arbitrary host numeric ordinals. This is
capability provenance, not a claim that an unkeyed hash provides security.

Pages preserve source order and contain at most4096 records. An exact page boundary
at a chunk end canonicalizes to the next chunk; source exhaustion has no next
cursor and needs no redundant terminal read. Work-limited pages provide a next
cursor after progress. A first chunk exceeding row/byte admission returns an
explicit ResourceLimit before I/O, rather than repeatedly emitting an unchanged
empty page. Budgets charge the complete authenticated chunk, including a resumed
prefix and null rows. Cancellation is checked for each prefix/output row.

## Read ownership and resource policy

The session reuses the shared NeedRead/AwaitRelease/Complete/Idle/Disposed steps,
monotonic session namespace and exact `GeoReadTicket`. Before host I/O it reserves
`4*encoded_bytes+16KiB` within the96MiB chunk cap, caller processor limit and
common128MiB ledger. Cloned validated manifest/control storage and the fixed-capacity
page vector are separately reserved before allocation; published pages retain
private leases and are borrowed, never extracted into unaccounted storage.
The original source/frame remains charged by its caller during clone admission.
`source()` borrows the validated clone; any independent continuation clone needs
its own prior reservation.

Supply authenticates exact bytes, digest, length and source row summary. A failure
or mid-row cancellation discards the tentative page atomically. A consumed read
blocks completion until the host drops its response/staging storage and calls
`release_read`. Cancel/dispose retains pending read credit until that ACK; stale
or cross-session tickets cannot advance or release another session. Older-sequence
cancel leaves current work intact. Disposed sessions must remain retained by the
transport while any read is outstanding. A previously owned page/frame stays
usable when another candidate fails.

`QueryBudget` keeps existing defaults and ceilings: page_rows1..4096,
processor≤128MiB, max_chunks≤65536, cumulative u64 row/read-byte work limits.
No per-session allowance bypasses the shared ledger, and no source-size mask is
allocated. These bounds certify memory/work admission, not interactive full-source
scan latency or massive keyboard traversal performance.

## Verification and remaining gates

`cargo test -p xyg-engine --offline geo_rows_session --lib` covers original null
ordinals, offscreen coordinates, packed Points, MultiPoint row deduplication,
duplicate/full-u64 IDs, signed-i64 extrema, half-open/null endpoints, scalar bit
preservation, complete paging, cursor revision rejection, stale tickets, failed
authentication, cancellation/ACK, work resumes and shared global contention.
Existing `geo_source` and membership regressions verify valid-only traversal is
unchanged. Full-source accessible DOM, keyboard focus, linked state transitions,
typed native/WASM parity and notebook/Reflex/VS Code journeys remain integration
gates; this module alone does not close #50 or #39.

## Native host ownership

The accepted retained frame exposes Python `rows()` / `rows_async()` and Node
`rows()`. The returned owned RowsData exposes Python `next_page()` /
`next_page_async()` or Node `nextPage()`. Each call returns at most the configured
`page_rows`; no cursor bytes, source ordinal, time or revision override is accepted.
Continuation captures the Rust-issued immutable RowsData handle. A frame or page
can continue using its retained reader after the original source is disposed;
closing that particular page retires its continuation capability.

The packet, key and record planes are borrowed from the owned Data snapshot.
`record(index)` extracts one row on demand; there is no source-sized host object
array. Python exposes signed times and IDs as exact integers, Node as bigint.
Callers must drop all borrowed planes before closing/disposal of the owning page.
Rust reserves the two-copy transport allowance and rejects extra reads. The hosts
settle outstanding reads before acknowledgment and settle temporary-session
cleanup before reporting cancellation; an unreturned candidate page is disposed.
The existing synchronous Python native path works inside a running notebook
asyncio loop without invoking `asyncio.run`; asynchronous readers use the separate
async methods.

`tests/test_geo_rows.py` and `packages/xy-node/test/geo-rows.test.mjs` exercise the
actual native ABI with null/offscreen/time-excluded MultiPoint rows, duplicate and
full-u64 IDs, signed-i64 extrema, detached continuation, failed authenticated-read
recovery, forbidden caller cursors and cancellation during I/O and cleanup. These
host adapters provide row data; accessible DOM/keyboard and linked-state host
journeys still require the integration gates above.

## Browser companion

The existing retained geographic controller exposes `sourceRows(next=false)`
and a separate Original geographic source rows list. Requests are explicitly
started by the user, page at most50 rows through commands15/16, and retain one
private Data continuation until replacement or disposal. Keyboard focus reports
exact row metadata through optional `onSourceRowFocus`; it does not infer a
selection mapping or mutate camera/selection policy. The painted provenance list
remains distinct. Failed reads preserve both accepted paint and the previous
source page. A successful new viewport/time publication clears the old source
page; cancelled work settles its reader and drops buffers before ACK.

The actual packaged-WASM strict-CSP/offline test pages null and time-excluded
rows plus a non-painted original row, focuses its exact full-u64 identity,
rejects malformed rows framing, and recovers from failed reads. Five shared
painted views retain one WebGL2 context. Shared quota refusal remains explicit;
this evidence does not claim every possible collection of active pages is
admitted simultaneously.

## Sparse selected original rows

`create_with_state(..., Option<Arc<GeoLinkedState>>)` validates complete source,
layer and state identity before cloning metadata or issuing a read. Legacy
`create` passes `None`. Every emitted original row has a `selected` boolean from
the sparse exact-ID set, including null, offscreen and time-excluded rows; this
is intent, not geometry/time eligibility. Duplicate IDs share intent while
retaining separate original rows. There is no viewport predicate or N-row mask.

Private issued cursors retain the immutable State Arc. Continuation compares
complete binding, canonical IDs and fill profile, never only a fingerprint.
Removing state or changing contents at the same revision rejects before I/O.
Published pages retain state ownership; shared128 MiB and local session admission
include the already leased sparse state. Selected protocol rows are explicit
XYGZ v2 with flag bit7 and a sparse-intent footer; ordinary None rows retain v1.
See [the exact selected wire](geo-linked-state-protocol.md).
