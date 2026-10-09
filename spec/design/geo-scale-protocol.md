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
ordinary source supply/release use zero in the header and the exact sequence
within their ticket. Overview supply/release/disposal and pure typed Data reads
require their exact nonzero operation sequence; their distinct 128-byte ticket
grammar is defined in [geo-temporal-overview-protocol.md](geo-temporal-overview-protocol.md).
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

## Original source-row companion paging (commands 15/16)

`15` creates a rows session from an immutable command-11 Scene Data handle, or
an owned command-16 Rows Data handle carrying a private issued continuation.
The expected nonzero sequence and complete query budget are required; payload
bytes and host-authored ordinals/cursors are rejected. Rust derives the exact
source/time/layer/state key from that authority, including layer/time revisions.
Rows remain available after the original source or Scene handle is disposed.
An exhausted Rows Data handle cannot create another page.

Commands 6/7/8/9/10 reuse the authenticated read, release-ACK, cancellation and
disposal lifecycle. Source, membership and rows sessions share the eight-session
cap and sixteen total handles. Rows pages contain every original source row,
including null, offscreen and time-ineligible rows; explicit eligibility is
metadata, not a second host filter. MultiPoint vertices do not duplicate rows.

`16` turns a completed rows page into separately owned immutable Data. It accepts
no payload and checks the complete budget before allocation. Like Scene and
membership Data, it counts against eight live Data handles, admits two actual
command-23 copies, and must be disposed after all borrowed views/copies are
dropped. It reserves `2048 * record_count + 8192` derived bytes for serialized
planes, two transfers, bounded host row extraction and framing, plus a separately
leased validated manifest/private cursor in the shared 128 MiB processor ledger.
No source-sized mask, new quota pool or silent truncation is introduced.
Simultaneous pages can be refused under the shared caps while existing frames
and pages remain usable. Application-retained page collections are outside the
engine-owned live storage contract.

Rows packets use the existing XYGZ v1 header with tag4 at8, session owner at16,
sequence24, count u64 at32, next boolean u32 at40, examined/read-byte statistics
u64 at48/56, read/considered chunks u32 at64/68, and repeated owner u64 at80.
The key is digest[8] at88, generation96, original rows104, geometry/CRS u32
at112/116, layer ID120, layer revision128, state revision136, time revision144,
time kind u32 at152 and signed-i64 start/instant/end at160/168. Unused time
endpoints and all reserved bytes are zero. The private continuation is never
serialized into this packet; the owned Data handle is its capability.

Each 64-byte record contains literal u64 feature ID at0, original ordinal8,
chunk/local row u32 at16/20, and flags u32 at24: null geometry bit0, time
eligible1, geometry-and-time eligible2, intervals attached3, start valid4, end
valid5, scalar present6. Signed-i64 endpoints at32/40 and f64 scalar bits at48
are zero when absent;28..32 and56..64 are zero. Scalar NaN/infinity/signed-zero
bits remain canonical. Ordinals increase within a page; duplicate IDs remain
distinct rows.

Proof: `cargo test -p xyg-engine geo_rows --lib`, the typed rows protocol tests,
Python/Node owned-frame tests, actual packaged native/WASM packet byte parity,
and the strict-CSP retained browser test cover full original paging, time/null
eligibility, offscreen keyboard focus, failure/cancellation/ACK, private cursor
continuation after disposal, and malformed packets. This does not implement
linked selection transitions, automatic camera focus, mixed-layer temporal
coordination or the remaining notebook/Reflex/VS Code live journeys.

## Authenticated external index lifecycle

Commands 17–19, 24 and 25 expose the point/MultiPoint sidecar described in
`geo-spatial-index.md` through the same native/WASM execute/read exports. No new
ABI signature or host geometry policy is introduced. This protocol slice does
not establish actual wasm32 indexed parity or a browser performance claim.

| Command | Authority and payload |
|---|---|
| 17 | Create index build from an immutable semantic SceneData handle and exact publication sequence. Payload is 16 bytes: grid u32 at 0, zero bytes 4..8, cumulative vertex ceiling u64 at 8. QueryBudget is required. |
| 18 | Create indexed query from completed index handle. Uses all command-5 camera, time, identity, revision, LOD and work fields, with empty payload and a new nonzero sequence. |
| 19 | Prepare indexed query output as ordinary immutable semantic SceneData. Query handle/exact sequence and existing uniform style48 payload. |
| 24 | Acknowledge exact pending leaf write after durable storage and release of all transient host copies. Build handle/sequence and ticket96 payload. |
| 25 | Pure pending leaf-wire read. Build handle/sequence and exact write ticket96; native length probes do not consume copy slots. |

Only commands 5 and 18 admit camera/option fields; only 3/5/18 admit generation
at header 144. Header sequence is meaningful on 17/18/19/24/25 as well as prior
operations. Supply/release 7/8 retain zero header sequence and bind sequence
inside the exact ticket. Unknown/reserved header fields remain rejected.

Build/query handles count toward the shared eight active-session ceiling.
Completed index handles count toward the sixteen total entries. Immutable
indexed SceneData shares the existing eight Data ceiling and private derived
leases; accepted source, index, query/result and semantic frame copies coexist
under the existing global 128 MiB processor ledger. A private 4 KiB protocol
control reservation accompanies each build/index/query owner, in addition to
core reservations. No independent index memory pool exists.

Build 6/7/8 drives authenticated canonical reads. A full or final partial leaf
uses step status 7 `NeedWrite`, with its write ticket at bytes 64..160. Pure 25
returns immutable exact bytes generated by Rust. At most two successful owned
wire copies are allowed per pending ticket; size probes are free. The caller
must retain immutable external page storage, drop transfer buffers, then ACK24.
A third read returns ResourceLimit without replacing bytes or resetting quota.
Repeated step replies do not reset the quota. Host claims of durability do not
change Rust page metadata or checksums; unavailable/changed bytes later fail the
exact query read rather than authorizing fabricated/pruned output.

Step status 8 `AwaitWriteRelease` retains the exact write loan after cancel or
failure. Status 9 is Cancelled. Dispose10 cancels a tentative operation, returns
AwaitRelease2 while any read/write loan remains, and retains its handle and
charges until the exact ACK8/24. Wrong/stale tickets cannot settle those loans.
A host must not drop or recycle buffers before acknowledging their ownership
release; the registry never assumes that cancellation released host memory.

When every canonical chunk and final write is acknowledged, step6 atomically
replaces the build entry with a private validated index authority and returns
status 11 `IndexReady`, original handle/creation sequence, page-count u64 at
32, and otherwise zero fields. Repeating step with that creation sequence
returns the same receipt. No partial build acquires index authority. Imported
sidecar publication is not exposed by this first protocol slice.

The index seeds its transition baseline from the exact immutable source frame
snapshot. Query18 requires sequence greater than that baseline and every prior
accepted indexed query; source digest/generation must match the validated
index. It reuses `GeoOperationSnapshot::precedes` from source sessions: decreasing
camera/time/layer/style/state revisions or changed camera/time/layer values
under reused corresponding revisions reject before publication. The baseline
advances only after successful query allocation/handle insertion.

A frontier exceeding 256 candidate leaf streams returns status 10
`FullScanFrontier`, original index handle and requested sequence, with reason u32 at48 (1: frontier, 2: eligible one-pass leaf count exceeds
QueryBudget.max_chunks), reserved52..160 zero and all other fields zero. It creates no query and does not advance sequence/revision baseline.
Hosts may explicitly select canonical source begin5; they must not silently
thin or change screen-bin policy. A narrower admitted query can reuse the
rejected sequence with independently valid authoring.

Indexed query 6/7/8 uses exact sidecar read tickets. Status 12
`IndexedQueryComplete` is distinct from source/member/rows Complete4. It carries
u64 pages-read, bytes-read and candidate-vertices at 160/168/176, u32 pass count
at 184, and zero bytes 32..64 and 188..256. Its repeated reply is identical.
Old query step/prepare calls become stale after a newer query is accepted on the
same index, while old exact loan release, cancellation and disposal remain
available. Already published immutable frames remain independently valid.

### Index ticket96

All fields are little endian. Header 28 is the explicit index ticket kind,
without weakening legacy source ticket28=0 validation.

| Offset | Meaning |
|---|---|
| 0 | u64 core session nonce |
| 8 | u64 canonical chunk index (kind1), or immutable page ID (kind2/3) |
| 16 | u64 exact operation sequence |
| 24 | u32 pass: zero for kinds1/3; actual core pass for kind2 |
| 28 | u32 kind: canonical build read1, indexed leaf read2, build leaf write3 |
| 32..56 | Standard generation/chunk/rows/first-row fields for kind1; zero for kinds2/3 |
| 56 | u64 exact encoded byte length |
| 64..72 | Exact eight-byte digest |
| 72..96 | Reserved zero |

Kind1 standard fields use generation u64 at 32, chunk u32 at 40, rows u32 at44,
and first source-row u64 at48. Request payload is ticket96 plus exact read bytes
for supply7, or ticket96 alone for release8/ACK24/read25. Ticket kind, nonce,
sequence, pass, length, digest and all identity fields must match; a borrowed
read cannot settle a write and vice versa.

### Immutable indexed frames

Prepare19 uses the same Scene/metadata encoder and private semantic frame
ownership as prepare11. It retains the exact source manifest, full LOD key,
result, painted style and camera/time/layer/style/state snapshot under leases.
Same-revision changed style bytes reject; a newer accepted style revision can
bind new bytes only after successful Data creation. Failed prepare leaves the
prior immutable painted frame and its picking/membership/export authority
intact. Once prepared, frame semantics remain valid after disposing the source,
index and query. Existing commands12/14/15/16 and frozen exports consume that
ordinary immutable authority; membership/rows still use canonical source reads
and do not yet gain indexed paging acceleration.

Focused native engine execute/read tests exercise byte-identical ordinary/indexed
Scene and typed identity output with half-open time, source disposal followed by
original-row paging, two-copy write quota/free probes, cancellation and exact
retired ACK, corrupt leaves preserving old frames, reused revision rejection,
new style revision acceptance, explicit frontier fallback and retry receipts.
Actual C ABI/wasm32/host storage evidence remains a separate integration gate.

For command18, QueryBudget.max_rows_examined explicitly limits cumulative decoded
leaf **vertex records**, including time-excluded records within a selected page
and all repeated aggregate passes. QueryBudget.max_chunks limits cumulative
authenticated **leaf reads**, including repeated passes; it is not a canonical
chunk count on this path. Both ceilings are checked before each read ticket is
issued. Exceeding either returns ResourceLimit and cannot publish a partial
frame; existing immutable painted frames remain valid. max_read_bytes is also
cumulative across passes. A legal source-wide budget can therefore be too small
for an indexed whole-world query; hosts must explicitly choose a suitable budget
or canonical path. No budget field is silently ignored. Core callers can admit
these same optional limits through set_work_limits before the first ticket;
the existing direct constructor retains its explicit projection/read ceilings.

Before allocating or advancing an index query, the shared allocation-free
estimate_work planner counts eligible authenticated leaf pages using the exact
same conservative camera/time candidate predicate. A one-pass leaf count above
max_chunks returns FullScanFrontier status10 with reason2 at48; frontier overflow
returns reason1. Both preserve index sequence/revision baseline. This is an
explicit recorded canonical-path fallback, independent of global OOM or corrupted
reads. The planner does not silently assume a particular LOD pass count: runtime
cumulative record/read/byte caps still apply if an admitted aggregate second pass
exceeds its allowance. Hosts must explicitly dispatch canonical begin5 on the
fallback receipt rather than changing screen-bin semantics.

## Independent immutable frame ownership

Command 26 duplicates an admitted immutable SceneData using its exact handle,
publication sequence and explicit budget, with no payload. The new Data owns a
separately admitted packet and two-read quota while sharing the existing privately
leased immutable source/result/style authority. Only packet owner bytes16–23
change to the input Data handle; all source/camera/time/revision/Scene bytes remain
identical. Source, RowsData and auxiliary handles cannot supply this authority.
The command preserves the source's current frame and works after query/source/
index disposal. See [geo-frame-leases.md](geo-frame-leases.md) for precise admission,
copy costs, disposal and thin-host methods. No C/WASM signature changes are made.


## Exact temporal overview extension

Commands 27–31 share this registry and all existing limits. The builder starts
from trusted immutable source SceneData, reauthenticates canonical chunks, and
publishes a private temporal overview only after every external write ACK.
Independent queries produce explicitly nonfinal data-domain count frames in
`XYOV` v1, with ordinary Rust-projected Scene geometry. They do not produce a
`GeoPointResult`, exact screen-bin counts, or source-feature interaction. Ticket,
command, output, admission and remaining parity gates are specified in
[geo-temporal-overview-protocol.md](geo-temporal-overview-protocol.md).


## Explicit linked-state scopes (commands32–36)

The [selected-state protocol](geo-linked-state-protocol.md) defines bounded
namespace/source/layer scopes, full sparse-u64 intent, success-only State
consumption and the selected indexed Query-to-Data replacement lifecycle.
Legacy commands5/18/19 and None packets retain their behavior and wire bytes;
5/18 reject on a lane already bound to an explicit selected scope. Selected
Scene and Rows packets use explicit XYGZ v2 with XYSE intent/count provenance,
not a silently extended v1. Scope disposal refuses while private authority
remains. Existing16 total handles,8 sessions,8 Data,128/384 MiB budgets remain.
Frozen selected export and public typed host orchestration are separate gates;
no selected-export coverage or #50 closure is claimed by this core slice.


## Paged hierarchy commands37–41

`geo-hierarchy-protocol.md` specifies the private paged hierarchy child. It shares
this registry, quotas, canonical SceneData serializer and lifecycle exports.
Commands37/38 create bounded authenticated build/query sessions,39 publishes
ordinary immutable SceneData,40 purely reads exact pending write bytes and41
ACKs their private ticket. Replies17/18/19 respectively mean explicitly unsupported
selected authority, privately completed hierarchy and exact completed query.
Selected state is never silently discarded; this first integration accepts None.
No C ABI/WASM signatures or existing command bytes change.
