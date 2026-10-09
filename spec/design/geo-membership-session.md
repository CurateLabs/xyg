# Resumable exact aggregate membership

The retained geographic [source session](geo-source-session.md) and shared
[point LOD](geo-lod.md) produce immutable aggregate keys. `GeoMembershipSession`
turns one exact reduced cell into one bounded source-row membership page without
synchronous filesystem/browser callbacks. This is the engine foundation for
async picking; public transport/controller integration and massive scale evidence
remain #50 gates.

`create(validated_source, sequence, GeoLodKey, cell, optional GeoCellCursor,
QueryBudget, max_projected_vertices)` validates before copying or reading. It
uses the shared allocation-free `GeoCellQuery` constructor and exact predicate;
the synchronous membership helper uses the same policy. The key binds full source
digest/generation/row count/geometry/CRS, normalized f64 camera, signed-i64 time
predicate, layer ID, style/state revisions, reduced kind and grid dimensions.
The optional cursor additionally binds exact cell and source query cursor. A
changed key, source, cell or malformed cursor fails before allocating its clone
or issuing I/O.

The session clones only bounded, already validated manifest summaries. It never
copies the whole source or creates a source-sized mask/CSR. The original source
and LOD result remain live and globally leased while clone/page admission occurs.
One `GeoProcessorLease` covers cloned metadata/control state; another covers at
most 4096 `FeatureRef` records and page metadata. Both reserve before allocation.
A published page retains its private lease and is available by borrowed accessor;
it cannot be extracted without its accounting. Each record carries full-u64
feature ID, chunk index, original row within chunk and original full-source row
ordinal. Distinct source rows with identical IDs remain distinct records.

`step` uses the same NeedRead/AwaitRelease/Complete/Idle/Disposed vocabulary and
96-byte read tickets as the source processor. A shared monotonically increasing
session ticket namespace prevents source/member ticket collisions. The source
chunk digest, exact length, generation, row count and source-row base are bound
before reading. Temporal summary pruning precedes I/O. Each supplied chunk is
authenticated by the shared parser; per-row time filtering precedes shared exact
projected-cell testing. MultiPoint returns one membership per qualifying source
row even when several vertices hit the cell. Source order and original null-row
ordinals are retained. No geometry or bin predicate is implemented in a host.

Read admission reserves `4 * encoded_bytes + 16 KiB` before the host allocates,
within the common 96 MiB chunk ceiling, caller phase allowance and global
128 MiB processor ledger. Source clone, existing pages/results and pending/retired
reads are all included. `supply` borrows host bytes and leaves its reservation
charged; the host drops response/staging buffers before `release_read`. A consumed
read blocks publication/next read until acknowledgment. Cancel/dispose retires
outstanding reads until host abort/drop acknowledgment; stale tickets cannot
advance another session. The registry retains disposed sessions until no reads
remain outstanding. Cancelling an older sequence does not cancel a newer session.

A page completes on membership capacity, source exhaustion or a work boundary.
Chunk-count, cumulative-u64 rows/read bytes can publish a resume cursor after
progress. A first selected chunk which cannot fit row/read admission returns
`ResourceLimit` before I/O; repeated calls cannot produce an unchanged empty
cursor. Every decode charges the entire bounded chunk including a resumed prefix
and null rows. Projection work is bounded by the shared predicate. If projection
admission ends after source-row progress, the accepted prefix publishes with a
cursor at the uncompleted row; the next ephemeral page gets a fresh bounded
matcher. A first row which cannot complete within its vertex budget fails
explicitly rather than looping on the same cursor. Budget-limited async pages
therefore permit progressive recovery; the synchronous helper's strict vertex
limit still fails the whole synchronous call. Normal admitted pages match its
records/cursor/projection counts exactly.

Six focused tests prove two chunks/three pages with full-u64 IDs, null original
ordinals and duplicate IDs, MultiPoint row union, time-first read pruning,
synchronous policy parity, key/cursor revision rejection, cross-session stale
read isolation, cancel/dispose acknowledgment, retained-page global contention,
work-resume and stalled-chunk/row failure. Actual native/wasm32 protocol parity,
public async pick/brush/selection, page-data ownership and massive traversal are
remaining integration gates.
