# Retained geographic lifecycle protocol (#50)

`geo_scale_protocol` is the shared Rust ingress for native and real WASM retained
geographic processing. Hosts frame typed little-endian bytes and fulfill bounded
read tickets. Rust owns source authentication, time selection, projection, LOD,
publication, memory admission and provenance. No coordinate, count, identity,
time or camera number travels as JSON. This protocol is a building block; it
does not by itself prove the issue's 100M execution or interaction gates.

## Framing and admission

Requests use `XYGQ` version 1 and exactly a 256-byte header followed by the
command's payload. Integer fields have the widths below; doubles are IEEE754
f64 bit patterns. A frame's length, command, presence/boolean flags and reserved
bytes must be validated before looking up or mutating a handle. Unused
command-specific fields are zero. No trailing payload bytes are accepted.

| Offset | Width | Meaning |
| --- | --- | --- |
| 0 | 4 bytes | `XYGQ` |
| 4 | u32 | Version 1 |
| 8 | u32 | Command |
| 12 | u32 | Begin camera world-wrap, exactly 0 or 1 |
| 16 | u64 | Registry handle; 0 for new builder/session |
| 24 | u64 | Expected/query sequence |
| 32 | u64 | Query processor byte allowance |
| 40 | u64 | Maximum examined source rows per pass |
| 48 | u64 | Maximum read bytes per pass |
| 56 | u32 | Maximum considered chunks per pass |
| 60 | u32 | Membership page row limit |
| 64 | u32 | Begin camera CRS: 4326 or 3857 |
| 68 | u32 | Begin reduced kind: cluster 0, density 1 |
| 72 | u32 | Begin maximum cells |
| 76 | u32 | Begin previous-direct flag, exactly 0 or 1 |
| 80–135 | seven f64 | Center x/y, zoom, CSS width/height, bearing, pitch |
| 136 | 8 bytes | Begin authenticated manifest digest |
| 144 | u64 | Source generation (finish/begin) |
| 152 | u64 | Begin layer ID |
| 160–199 | five u64 | Camera, time, layer, style and state revision counters |
| 200 | u32 | Begin time mode: all 0, instant 1, window 2 |
| 204 | u32 | Reserved zero |
| 208 | i64 | Begin instant/window start |
| 216 | i64 | Begin window end |
| 224 | u64 | Begin cumulative projected-vertex work limit |
| 232 | u64 | Exact payload byte length |
| 240–255 | 16 bytes | Reserved zero |

Signed timestamps use two's-complement i64, including negative values. All time
selection is the retained source's half-open policy. All/instant modes must not
silently retain unused window fields. Rust checks finite cameras through the
canonical viewport constructor; hosts perform no camera normalization or LOD
math. Stable errors are `SourceError`/`GeoError`, without embedding user values.

The registry holds at most sixteen live entries, including at most eight source
sessions and eight immutable data snapshots. Handles are monotonic nonzero
u64 capabilities, never reused after disposal; source generations and feature
IDs are separate full-u64 identities. Registry capacity must be checked before
candidate allocation. The source/query process ledger is 128 MiB across entries,
active candidates, published results and retired reads; an individually allowed
128 MiB query does not grant another 128 MiB outside this ledger. Builder
metadata initially reserves its bounded 32 MiB allowance. Parse scratch and
candidate manifest/output copies are admitted before allocation.

## Fixed mutation replies

Every mutation returns exactly 256 bytes (`XYGZ`, version 1), or fails. A native
caller reserves that capacity **before** calling Rust: insufficient capacity
must not invoke the operation. Native size discovery must never execute a
mutation twice. The WASM worker uses the same single-execution seam.

| Command | Operation and payload |
| --- | --- |
| 1 | New manifest builder; no payload |
| 2 | Push one canonical `XYGK` chunk to builder |
| 3 | Finish builder using nonzero source generation; no payload |
| 4 | Create source session from an untrusted persisted manifest |
| 5 | Begin camera/time/layer processing from a validated source; no payload |
| 6 | Step the session; no payload, expected sequence required |
| 7 | Supply a 96-byte exact read ticket followed by its exact chunk bytes |
| 8 | Release host ownership of one exact 96-byte read ticket |
| 9 | Cancel through sequence; no payload |
| 10 | Dispose a registry entry; no payload |
| 11 | Prepare an immutable Scene/provenance snapshot; exact uniform style payload |

Builder finish stages the candidate under a lease and replaces the builder
only after all validation, encoding and memory admission succeeds. Failed push,
finish, begin or supply cannot overwrite an already committed manifest/result.
Failed geometric work may discard its tentative job; its last published result
remains available under the original sequence. Stale/zero begin or step calls
must not advance a newer job or retire its current read. Cancellation through an
older sequence preserves newer work.

Header sequence is meaningful only for begin, step, cancel and snapshot preparation;
supply/release use zero in the header and the exact sequence within their ticket.
Reply bytes 16/24 are handle/sequence. A step uses u32 at byte 8: NeedRead 1,
AwaitRelease 2, SourceReady 3, Complete 4, Idle 5, Disposed 6. Validated source
metadata occupies generation u64 at 32, digest at 40, rows u64 at 48, geometry
u32 at 56 and CRS u32 at 60. NeedRead/AwaitRelease carries its ticket at 64–159.
Unspecified reply fields are zero.

The read ticket is an exact value capability. Its offsets are session ID u64 at
0, read ID u64 at 8, sequence u64 at 16, pass u32 at 24, reserved zero at 28,
source generation u64 at 32, chunk index u32 at 40, chunk rows u32 at 44, first
source row u64 at 48, encoded byte length u64 at 56, digest bytes at 64 and
reserved zero at 72–95. Sequence 0 means initial source validation. A positive
pass/sequence binds a particular point-LOD operation. Ticket identity, source
length and digest must match before a chunk is authenticated or folded.

Superseding, cancelling or disposing a job retires outstanding tickets rather
than freeing their host-copy charges prematurely. A retired supply is stale;
its release remains valid. Disposed sessions stay registered until all retired
read ownership is acknowledged. Release happens after the host drops or aborts
the actual I/O buffer, not when a cancellation request is merely sent.

## Pure reads and output ownership

Pure authoring command 20 accepts a 32-byte typed prefix followed by one exact
`XYGD` descriptor and optional time/value planes. Prefix fields are descriptor
length u64 at 0, flags u32 at 8 (time bit 1, scalar bit 2), zero at 12, feature
rows u64 at 16, zero at 24. Time planes are starts/ends i64 then start/end
validity u8, each length `rows`; scalar values are f64. Exact products and framing
are checked before typed-plane allocation. Output is canonical `XYGK`.

Command 21 reads a finished manifest. A published geographic Scene read binds
an exact published sequence and an explicit 48-byte uniform style: fill/stroke
RGBA8 at 0/4, stroke width/diameter/opacity f64 at 8/16/24, symbol u8 at 32 and
zero at 33–47. Direct metadata records preserve feature ID u64, source row u64,
chunk index/row/vertex u32 and reserved zeros. Reduced metadata records contain
count u64 and centroid x/y f64; cell ordinals identify aggregates, with exact
membership retrieved through the retained source.

Snapshot preparation command 11 binds the exact published sequence and style.
Its fixed reply contains the new immutable data handle u64 at 16, sequence at 24,
packet byte length u64 at 32 and originating source-session handle u64 at 40.
Pure read command 23 takes that data handle and no payload; its header sequence
is zero because the handle already names one immutable sequence. The prepared
packet remains stable when its source session publishes another result or is
disposed. There is no command 22.

The packet starts with `XYGZ` version 1 and a 256-byte header: aggregate flag
u32 at 8, dropped-channel mask u32 at 12, originating session handle u64 at 16,
published sequence u64 at 24, Scene byte length u64 at 32, metadata byte length
u64 at 40, visible/projected vertex counts u64 at 48/56, grid columns/rows u32
at 64/68 and grid-capped flag u32 at 72. Bytes 76–79 are zero. The complete
normalized snapshot follows:

| Offset | Width | Snapshot meaning |
| --- | --- | --- |
| 80/84 | u32/u32 | Camera CRS/world-wrap |
| 88–143 | seven f64 | Normalized center x/y, zoom, width/height, bearing/pitch |
| 144 | 8 bytes | Authenticated source digest |
| 152/160 | u64/u64 | Source generation/layer ID |
| 168–207 | five u64 | Camera/time/layer/style/state revisions |
| 208/212 | u32/u32 | Time mode/reduced kind |
| 216/224 | i64/i64 | Time start or instant/end; unused endpoints zero |
| 232 | u64 | Source row count |
| 240 | u32 | Source geometry kind |
| 244 | u32 | Canonical source CRS, which may differ from camera CRS |
| 248–255 | 8 bytes | Reserved zero |

Ordinary
`XYGS` Scene bytes and then the direct/reduced metadata plane follow exactly.
A direct row is 40 bytes: feature ID/source row u64 at 0/8, chunk index/row/vertex
u32 at 16/20/24, zeros at 28–39. A reduced cell is 24 bytes: count u64 at 0,
centroid x/y f64 at 8/16. Painter geometry still consumes the ordinary derived
Scene contract; metadata centroids do not replace that offset-f32 paint path.

The immutable data entry retains its derived-memory lease in the shared 384 MiB
cache/derived pool, alongside the reserved 128 MiB non-cache source/query phase.
Native size discovery calls read the same immutable handle. Native/worker hosts
must enforce the declared bounded transfer/copy ownership slots. Rust admits at
most two actual copies per snapshot lifetime; a third read returns ResourceLimit.
A size-only native call must borrow the immutable length rather than allocate or
consume an ownership slot. Releasing an individual temporary copy does not reset
the lifetime quota: dispose and prepare another snapshot to renew it.
Explicit disposal command 10 occurs after those output copies are dropped.
Calling a pure read arbitrarily many times and retaining its copies is not an
extra unmetered memory allowance. A failed native output capacity check writes
nothing and leaves the immutable handle live. The final native/WASM binding
must prove ownership through transfer failure, cancellation and disposal before
packaging claims this lifecycle complete.

## Evidence and remaining integration

`cargo test -p xyg-engine geo_scale_protocol_tests --lib` is the independent
byte-level proof: real canonical chunks, full-u64 feature IDs and generation,
source validation reads, time-first query skipping, stale published sequences,
work failure preserving prior output, retired/disposed tickets, exact reserved
bytes, registry/session/snapshot capacity and handle recovery. An actual
32,773-vertex MultiPoint executes both reduction passes and produces a typed
density snapshot with independently checked vertex counts, centroid and profile.
Repeated allocation-free length queries preserve the two-copy quota; an old
snapshot remains identical after newer publication and source disposal. These tests use the shared process
ledger test guard; they do not mock the private registry or processing policy.

Native fixed-capacity C ABI, actual WASM worker lifecycle, snapshot/transfer
leases, exact membership wire paging, public thin host/controller adapters,
100M measured execution, style/state attachment and frozen tile/export receipts
remain required integration gates. The protocol does not substitute a planner
count for ingestion or pan latency evidence.

## Exact paged aggregate membership

Commands 12/13 extend the existing lifecycle; they do not add an ABI export.
Command 12 names a source session and its published sequence. Its payload is
u32 cell at 0, u32 cursor-present (0/1) at 4 and u64 projected-vertex work limit
at 8, followed by exactly 208 cursor bytes when present. Header QueryBudget words
32–63 provide the page/work/read/memory limits. No other header fields carry
membership policy. Rust takes the currently published reduced `GeoLodKey` as
its authority; direct results reject this operation. The cursor must bind that
exact key and cell. The immutable validated manifest clone and bounded page
are globally admitted before allocation while the original result stays live.
The combined eight-session cap includes source and membership sessions.

Commands 6/7/8/9/10 step/supply/release/cancel/dispose either session type with the
same ticket/sequence rules. Membership completion emits code 4; complete-page
row count u64 appears at 160, cursor-present u32 at 168 and cell u32 at 172.
Complete-page records/cursor are read through an immutable data snapshot, not
squeezed into a fixed mutation reply. A disposed member session remains until
its retired reads are acknowledged. The host drops external response buffers
before acknowledgment. Time summaries precede reads and the shared exact Rust
cell predicate precedes membership publication; MultiPoint is a source-row union.
[Membership session](geo-membership-session.md) defines work-progress versus
stalled-row/chunk errors.

Command 13 accepts a completed member handle, expected sequence and no payload.
It prepares a durable data handle just as command 11 does for Scenes, returning
handle at 16, sequence at 24, exact data length at 32 and owner member handle at
40. Command 23 and allocation-free `data_len` read this immutable content.
The packet remains readable after member/source disposal; its own data lease
and two-copy lifetime allowance remain until explicit command 10 after CPU
copies are dropped. No Scene or reserved synthetic feature ID is invented for
membership. Data/session/total handle caps are admitted before constructing
candidates. A failed first derived reserve or failed first Scene compile drops
an empty data-cache metadata allocation, permitting recovery without a leaked
fixed charge.

Member data uses `XYGZ` v1 with packet-kind 2 at u32 offset 8. Its 256-byte header:

| Offset | Width | Meaning |
| --- | --- | --- |
| 12 | u32 | Exact reduced cell ordinal |
| 16/24 | u64/u64 | Original member owner handle / published source sequence |
| 32/40 | u64/u64 | Membership row count / shared predicate work counter |
| 48/56 | u64/u64 | Examined source rows / cumulative chunk read bytes |
| 64/68 | u32/u32 | Read chunks / considered chunks |
| 72/76 | u32/u32 | Cursor present / exact cursor length (0 or 208) |
| 80 | u64 | Original member owner handle |
| 88–247 | 160 bytes | Complete normalized LOD key below |
| 248–255 | bytes | Zero |

The optional 208-byte cursor follows, then exactly `row_count` 32-byte records:
feature ID u64 at 0, full-source row ordinal u64 at 8, chunk index u32 at 16,
original chunk row u32 at 20 and eight zero bytes at 24. Duplicate feature IDs
on distinct source rows remain distinct records, in original source order.

The 160-byte key grammar (also cursor bytes 0–159) is:

| Offset | Width | Meaning |
| --- | --- | --- |
| 0 | 8 bytes | Source digest |
| 8/16 | u64/u64 | Source generation / source row count |
| 24/28 | u32/u32 | Canonical source CRS / geometry kind |
| 32/40/48 | three u64 | Layer ID / style revision / state revision |
| 56/60 | u32/u32 | Camera CRS / exact wrap boolean |
| 64–119 | seven f64 bits | Center x/y, zoom, width/height, bearing/pitch |
| 120/124 | u32/u32 | Time mode / reduced kind |
| 128/136 | i64/i64 | Time start or instant / end; unused endpoints zero |
| 144 | u32 | Direct boolean; membership requires zero |
| 148/152 | u32/u32 | Grid columns / rows |
| 156–159 | bytes | Zero |

Cursor bytes 160–163 are the exact cell u32; 164–167 are zero; 168 is source
cursor generation u64, 176 source digest bytes, 184 shared query digest bytes,
192 chunk index u32, 196 original row u32 and 200–207 zero. Hosts transfer this
opaque typed cursor; they do not compute query digests or project geometry.

Reproduction: `cargo test -p xyg-engine geo_membership_session --lib` (six
session tests), `cargo test -p xyg-engine membership_protocol_tests --lib`
(three independent public-frame tests). The protocol tests execute actual
72,000-vertex MultiPoint reduction, two chunks/three membership pages, repeated
length queries, immutable page ownership after session disposal, third-copy
rejection, exact stale/padded cursors, time-first reads, retired-ticket recovery
and derived-pool pressure cleanup/recovery. Actual packaged native/wasm32 and
browser event/controller parity remain integration gates.

## Published LOD picking (command 14)

Command 14 takes a source-session handle and its exact published sequence.
Its 80-byte payload begins with the same uniform 48-byte style as command 11,
then CSS x/y/tolerance f64 at offsets 48/56/64, mode u32 at 72 (0 topmost,
1 all), and maximum hits u32 at 76 (1–4096). Coordinates and tolerance must be
finite; tolerance is nonnegative and f32-renderable. Rust requires the style bytes to exactly match the successful command-11
paint binding for that publication; its revision is bound in the published key. No host computes aggregate grid membership or glyph geometry.

Rust uses the shared canonical glyph SDF, outer diameter, stroke and opacity
policy. Direct results preserve each full source ID, source-row/chunk-row
identity and vertex ordinal. Hits are returned in reverse paint order; all
mode rejects atomically if more than the admitted maximum match. Topmost mode
returns the first match. Cluster hits use the same count-to-area circle channel
as Scene compilation. Density hits select the exact occupied top-first image
cell; tolerance does not extend image cells. Zero opacity, empty cells,
zero-size direct marks and coordinates outside the viewport produce no hit.
An aggregate cell is never represented by a fabricated source feature ID.
Command 12 resolves its complete paged source-row membership using the same
published key and cell ordinal.

The fixed mutation reply creates an independently owned Data handle (offset
16), publication sequence (24), byte length (32) and source-session owner (40).
Pure command 23 reads its packet with the existing two ownership-copy quota.
The packet is `XYGZ` v1, kind 3 at offset 8, count u64 at 32, mode u32 at 40,
maximum hits u32 at 44, x/y/tolerance f64 at 48/56/64, owner u64 at 80, and the
existing full 160-byte LOD key at 88–247. Other header bytes are zero.
Exactly `count * 48` bytes follow: tag u32 at 0 (direct 0, cell 1), vertex u32
at 4, feature ID/source-row u64 at 8/16, chunk/row u32 at 24/28, cell ordinal
u32 at 32, zero padding at 36, and count u64 at 40. Direct records have zero
cell/count fields; cell records have zero vertex/feature/source fields.

Before allocation the registry admits the common total/Data handle ceilings
and reserves `maximum_hits * 512 + 8192` bytes against the shared derived
ledger. This covers the bounded hit workspace, immutable packet and admitted
ownership copies. Failed picking releases the candidate lease and an otherwise
empty newly-created cache; prior Scene, membership and hit Data remain usable.

## Immutable interaction authority

Command-11 Scene Data also privately retains the validated source manifest,
exact LOD result, painted style bytes and sequence. The source/result copy is
preflighted and leased against the shared 128 MiB processor ledger before either
is cloned; Scene bytes and ownership copies retain their separate derived lease.
Commands 12 and 14 accept this Scene Data handle with its exact sequence as an
alternative to a live source-session handle. Data without a Scene semantic
snapshot (membership/hit packets) is not an interaction authority.

A host uses the accepted Scene Data handle for picking and membership until it
has staged and accepted a replacement frame. A newer source computation, failed
Scene preparation or source-session disposal cannot invalidate the old displayed
frame's interaction. The immutable semantic snapshot fixes its style and full
camera/time/source/revision key; command 14 rejects different style bytes.
Membership/hit packets report the supplied Scene Data handle as their owner.
Scene Data disposal releases its private source/result lease after those owned
copies drop. Already-created member sessions retain their separately admitted
source metadata and remain independent.
