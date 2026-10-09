# Resumable geographic source processor

Dossier §27/§28; retained canonical source framing is defined in
[geo-retained-source.md](geo-retained-source.md), geographic point tiers in
[geo-lod.md](geo-lod.md). This engine module provides transport-neutral state;
it performs no filesystem, network, browser or shell I/O. Native/WASM registry,
public authoring, protocol replay caching and massive benchmark evidence remain
separate integration gates. This slice does not close #50.

`GeoSourceSession::create(XYGI, QueryBudget)` validates framing and reserves
metadata before copying it. `step()` returns `NeedRead(GeoReadTicket)` with the
exact chunk length, canonical digest, source generation, original source-row
base, row count, chunk index, session/read nonce, query sequence and pass.
Repeated steps return the same ticket until supply or cancellation. No source
capability becomes visible until every persisted chunk has been authenticated,
parsed by the shared XYGK/XYGD grammar and compared with its manifest summary.
The synchronous source validator and resumable validator share the same
`UntrustedGeoManifest` preflight, per-chunk comparison and final canonical
manifest comparison. Early mismatch may reject before reading later chunks;
no partially validated summary may prune subsequent product reads.

The host admits the exact request length before I/O. `supply(ticket, borrowed
bytes, cancelled)` authenticates and parses a single chunk; cancellation is
checked before/after parse and by the shared LOD fold. Success returns no owned
source plane to the host. `step()` then returns `AwaitRelease(ticket)`.
**The host must drop its response/fetch/staging buffers before calling
`release_read(ticket)`.** Supply does not release the reservation for borrowed
host bytes while those bytes are still live. A host may abort/drop an outstanding
read after cancellation/disposal and acknowledge the retired ticket without
supplying it. Duplicate/unknown acknowledgments fail with `StaleSource`; protocol
nonce replay idempotence belongs to the transport registry, not a second engine
lifecycle implementation.

Once `SourceReady`, `begin(sequence, snapshot, camera, query, options)` constructs
shared `GeoPointLod`. Sequence zero is reserved for source validation. Positive
sequences must increase and exceed the cancellation watermark. Transport step
commands compare their expected sequence with `current_sequence()` before
advancing the session, so an old caller cannot advance newer work and stamp an
old sequence onto its reply. Snapshot binds
source digest/generation, exact normalized camera rebuild key, signed-i64 time
predicate, camera/time/layer/style/state revisions and full-u64 layer ID. Revisions
cannot regress; equal camera/time/layer revisions cannot name different respective
values. Source, camera and time inconsistencies reject before replacing an active
job. LOD session queries currently require `bounds=None`: screen projection is
responsible for visible membership, while shared temporal summaries may prune
chunks before projection. All six source geometry kinds validate, but this
processor explicitly accepts only Point/MultiPoint; other geometry LOD is a
remaining catalog-scale gate.

Time-filtered chunks feed the exact shared `fold_chunk` implementation with
original chunk index/row base. The Count pass either finishes direct output or
requests one Aggregate pass; no global source-sized mask or membership CSR is
allocated. Work counters use u64 across native/WASM and include both passes;
row/read limits are checked before issuing the next read. The hard source chunk
count and the maximum two passes bound traversal. `Complete` publishes an
immutable `GeoPublishedResult` with snapshot, sequence, typed LOD result and
read/work statistics. `published()` borrows it; it cannot move out without its
accounting lease. The last successful result survives failed/cancelled successor
jobs. Superseding a job retires its outstanding read; stale supply cannot parse,
clear or advance the newer job. Cancelling an older sequence cannot cancel a
newer job. Cancel during source validation retires reads and discards untrusted
metadata. Dispose drops source/job/published data and retains retired read leases
until the host acknowledges that external buffers were dropped. The registry
must retain disposed sessions until `has_outstanding_reads()` becomes false.

## Shared memory admission

One atomic `GeoProcessorLease` ledger permits **128 MiB total** across every
session in one native process or WASM instance, including active jobs, retained
source metadata, old/new published outputs and active/retired read reservations.
This is not 128 MiB per view. The separate tile/derived ledger admits at most
384 MiB, yielding the agreed 512 MiB combined retained/query/cache ceiling.
Separate WASM instances require one host coordinator; independent per-instance
ledgers do not establish a process-wide limit.

Manifest creation reserves original borrowed input, its owned copy, bounded
summary-builder growth and canonical comparison scratch before allocation.
Session overhead includes fixed retired-ticket capacity (64) and control state.
LOD uses allocation-free `reservation_bytes(options)`; its complete transition
reserve is acquired globally before `new()` allocates. Existing active/published
reservations remain counted while the replacement is admitted; an otherwise
valid successor may therefore return `ResourceLimit` and leave the prior state
intact. Hosts may explicitly cancel an obsolete active job to free its scratch.

Before `NeedRead`, the session reserves the complete conservative parse promise
`4 * encoded_bytes + 16 KiB`, limited to the shared 96 MiB per-chunk ceiling and
remaining per-session/query allowance. This accounts host response/staging input,
shared descriptor decode/retained clone and temporal/scalar planes. It remains
charged through acknowledgment; no competing session can consume promised parse
scratch while asynchronous I/O is pending. Actual typed framing still undergoes
shared parser budget validation. Published vectors remain leased until replaced
or disposed, and result storage drops before its lease. `GeoProcessorLease` is
available to native/protocol serialization code for additional live reply planes;
its reservation must outlive those planes. Bare synchronous LOD helpers are
algorithm conformance paths, not globally scheduled product entrypoints.

Focused Rust evidence covers all-chunk authentication before pruning, signed
half-open temporal read pruning, second-chunk original ordinal/full-u64 identity,
actual synchronous/session direct output parity, actual 40,000-point two-pass
aggregation, resource admission before I/O, global concurrent-session contention,
stale read/cancel/dispose retirement and old-output preservation. Actual packaged
WASM/native lifecycle parity, public async readers, bounded reply serialization,
100M/1B runs, warm indexed pan and export snapshot integration remain required.

A successful command-11 Scene publication binds its canonical 48-byte uniform
style to the published style revision in the source session. Candidate framing,
style validation, admission, compilation and Data insertion must succeed before
this binding changes. Different style bytes under the same revision fail stale;
a new style requires a new begin/publication with a greater style revision.
Command-14 picking requires an exact existing painted-style binding, so it cannot
pick geometry under a style different from the accepted Scene. Independently
owned old Data packets remain immutable across newer publications.
