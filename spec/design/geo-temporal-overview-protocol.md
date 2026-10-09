# Retained temporal overview protocol

This is the typed transport for `geo-temporal-overview.md`, using the existing
`XYGQ` v1 execute/read entry points. It adds no ABI signature and no registry or
memory pool. The common eight active sessions, sixteen total handles and eight
immutable Data handles include overview objects. A validated overview is an
immutable authority, not a `GeoPointResult` and not an exact screen-bin tier.

## Commands and publication

| Command | Meaning | Payload |
|---|---|---|
| 27 | Create builder from trusted source SceneData | u64 cumulative vertex ceiling |
| 28 | Create independent temporal overview query | None; canonical command-5 camera/time/revision header |
| 29 | Prepare immutable typed count/Scene Data from completed query | None |
| 30 | Pure pending write-page length/read | Exact 128-byte ticket |
| 31 | Settle write after storage callback/owned bytes release | Exact 128-byte ticket |
| 6 | Step builder/index/query | None |
| 7 | Supply authenticated read | Exact ticket + exact bytes |
| 8 | Settle read after callback/owned bytes release | Exact ticket |
| 9 | Cancel builder/query | None |
| 10 | Dispose | None |
| 23 | Pure immutable typed Data length/read | None |

Command27 rejects privately selected SceneData with code17
(`UnsupportedSelected`) before a builder/source clone or processor lease exists.
This includes a selected profile with an empty ID plane: empty intent remains
selected authority. The current temporal index retains only the canonical source
and cannot preserve that frame's sparse intent/profile/count plane. Rust checks
its private selection/Scope authority, rather than trusting host annotations or
merely inspecting ID count. Rejection does not consume another issued State,
change Scope/source history, or invalidate prior frames. Existing common handle
and session-cap admission still applies; ordinary unselected build bytes and
count/Scene semantics are unchanged.

The raw encoder accepts numeric handles, so internal frame-aware encoding
helpers `encodeGeoOverviewBuild(frame, ...)` (shared TypeScript/Node) and
`builder_request(frame, ...)` (Python) reject selection presence before transport
dispatch. They create no operation, lease or chart-building API. A forged host
`selection=None` annotation cannot bypass the independent Rust guard. Reply
decoders admit the fixed code17 receipt without a ticket or output owner.

Commands 27–31 and builder/index/query operations 6–10 require their exact
nonzero operation sequence in the common header. Overview Data uses the shared
immutable Data disposal grammar: command 10 has sequence zero, while command 23
reads require the exact nonzero publication sequence. Command 27 binds the source SceneData publication
sequence. Queries are independent immutable operations, so their sequences are
not a mutable index-wide transition counter. Command 28 validates every source,
camera, time and revision field in the supplied snapshot. It does not claim that
another independent query's revisions form its predecessor. A mounted controller
must bind its candidate operation and reject an obsolete publication explicitly.

A builder becomes a validated overview at the same handle only after canonical
source authentication, bounded sorting/merge/tree processing and every write
ACK. Source SceneData may be disposed once construction begins. Validated
index/query/Data owners retain their own private source authority; disposing
source, index or query does not change an already issued Data frame.

Additional fixed reply codes are 13 (validated overview ready, digest at 40,
storage namespace at 48), 14 (query complete), 15 (explicit unsupported-domain
fallback), 16 (prepared typed Data, byte length at 32 and query owner at 40), and
17 (unsupported selected input, naming the unchanged source Data and sequence).
Common codes 1/2/7/9 remain NeedRead/AwaitRelease/NeedWrite/Cancelled. Overview
replies use ticket bytes 64..192, distinct from the older 96-byte ticket grammar.
A cancelled read/write prevents disposal until its exact settlement ACK. The
protocol never calls a host reader/writer and cannot infer successful storage.

## Ticket authority

The 128-byte little-endian ticket is privately generated and compared byte for
byte against the retained loan before any supply, copy or settlement:

| Offset | Type | Meaning |
|---|---|---|
| 0 | u64 | Operation owner nonce |
| 8 | u64 | Immutable storage/build namespace |
| 16 | u64 | Loan serial |
| 24 | u64 | Operation publication sequence |
| 32 | u32 | Kind: 1 canonical source read, 2 overview read, 3 overview write |
| 36 | zero4 | Reserved |
| 40 | u64 | Page ID |
| 48 | u64 | Exact authorized encoded byte length |
| 56 | bytes8 | Exact authenticated page digest |
| 64 | u64 | Source generation, for kind 1 |
| 72 | u32 | Source chunk index, for kind 1 |
| 76 | u32 | Source rows, for kind 1 |
| 80 | u64 | Original source first-row ordinal, for kind 1 |
| 88 | u64 | Canonical chunk encoded bytes, for kind 1 |
| 96 | bytes8 | Canonical chunk digest, for kind 1 |
| 104 | zero24 | Reserved |

Non-source kinds zero bytes 64..104. Hosts must capture the primitive authorized
length before invoking callbacks, admit both logical and backing buffer capacity
before copying, and settle only after the callback has finished and its buffers
are released. Cancellation does not authorize early loan disposal. Pure write
size probes consume no copy slot; successful command-30 reads have two lifetime
copy slots, matching native query/copy and actual WASM single-copy usage. Failed
capacity discovery must not consume a slot. A third read rejects. The immutable
Data path uses the same two-copy policy. Storage is addressed by namespace and
page ID, never by a global unscoped page number.

## Typed Data: XYOV v1

A 256-byte header precedes exactly 256 little-endian u64 cell counts (2,048 bytes)
and the ordinary projected XYGS Scene. The counts are unmodified, exact temporal
vertex populations over the fixed bottom-first 16×16 Mercator domain. They are
not exact camera-visible counts. MultiPoint vertices contribute separately;
null geometry contributes none. No representative feature IDs or member CSR is
invented.

| Offset | Type | Meaning |
|---|---|---|
| 0 | bytes4 | `XYOV` |
| 4 | u32 | Version 1 |
| 8 | u32 | Flags: bit 0 temporal_exact, bit 1 data_space, bit 2 final |
| 12 | u32 | Square domain resolution 16 |
| 16 | u64 | Query authority handle |
| 24 | u64 | Exact query sequence |
| 32 | u64 | Scene byte length |
| 40 | u64 | Count plane byte length, exactly 2048 |
| 48 | bytes8 | Validated overview digest |
| 56 | u64 | Source generation |
| 64 | bytes8 | Source digest |
| 72 | u32 | Source CRS |
| 76 | u32 | Source geometry |
| 80 | u64 | Layer ID |
| 88 | u64 | Source rows |
| 96 | u32 | Camera CRS |
| 100 | u32 | Camera wrap bool |
| 104 | zero8 | Reserved |
| 112 | 7 f64 | Center x/y, zoom, width/height, bearing/pitch |
| 168 | zero8 | Reserved |
| 176 | 5 u64 | Camera/time/layer/style/state revision |
| 216 | zero8 | Reserved |
| 224 | u32 | Time kind: All 0, Instant 1, Window 2 |
| 228 | zero4 | Reserved |
| 232 | i64 | Instant or window start; zero for All |
| 240 | i64 | Window end; zero otherwise |
| 248 | zero8 | Reserved |

Flags are exactly 3: temporal_exact and data_space, with final false. The rendered
label is `Exact temporal counts by data-domain cell; spatial refinement pending`.
Rust projects each nonempty canonical cell rectangle with the existing geographic
polygon clipper and shared fill tessellator, then emits ordinary Triangle Scene
records. Camera CRS conversion preserves western -180 cell edges. Literal Scene
IDs are explicitly domain-cell ordinals 0..255, not source-feature IDs. The
fixed Rust logarithmic count palette is part of this coarse-tier output contract;
there is no host-side geometry, reduction, palette or style policy.

`with_overview_data` borrows the immutable Scene, owning exact result and camera
under the shared registry lock. Its callback must not reenter that registry.
Generic source pick, member and row commands reject this distinct Data authority.
A future exact domain-cell membership predicate must be implemented before source
hover/member UX is exposed. The trusted retained painter now dispatches on this
private Data kind, and snapshot command6 preserves its inert domain counts in
XYGXv4. See [overview painter/export contract](geo-overview-painter-snapshot.md).
Command26 can duplicate overview Data with a separately admitted16MiB credit and
fresh two-copy quota. The exact nonfinal notice is an explicit viewport-local
SceneLabel; it never adds a browser title gutter. Public overview composition,
domain-cell membership and spatial refinement remain pending.

## Admission and evidence

Builder work uses the unchanged source `QueryBudget`, including rows, cumulative
canonical/merge/tree read bytes and chunks, plus the explicit vertex ceiling.
Queries traverse at most two boundary paths of twelve pages each. Command 28
conservatively requires the retained source/index credit plus 1 MiB processor
allowance, 24 read-page slots
and 24×65536 read bytes before allocating or issuing I/O. No source rows are
examined by a prefix query; the source-row work field is not a surrogate count
of histogram populations. The global 128 MiB ledger still admits every live
private loan, query, result and prior output.

Scene preparation checks the complete source/index/result/query reservation
against the caller allowance, then reserves 8 MiB processor scratch before entering the shared
geometry/Scene path and 16 MiB in the existing derived pool before output
allocation. It emits at most 12,288 Triangle records and checks four complete
copies of the typed Scene/count envelope against that derived credit. The source
and immutable result remain charged through their owning Arcs. A failed first
Data preparation releases a newly empty cache's metadata charge. Old Data is
unchanged by rejected allocations, corrupt reads, cancellation or disposal.

Five focused byte-level Rust protocol tests cover exact temporal counts, full
source/layer IDs, canonical MultiPoint population, both source/camera CRSs,
wrap and ±60-degree pitch, private ticket namespace mutation, two-copy quotas,
cancelled unsettled writes, corruption/stale snapshots, shared session/Data caps,
drop recovery, and old typed Data after source/index/query disposal. The frozen
11 engine tests retain their independent temporal goldens and 1M tracer. Actual
native/wasm32/client parity, trusted painter/snapshot integration and measured
first-density/refinement latency remain separate gates; this foundation does not
claim #50 completion or billion-row interactive performance.


Actual packaged native383/WASM33 conformance is now reproduced with
`node scripts/geo_overview_conformance.mjs` after building the native core and
packaged browser artifact. Eight All/Instant/Window cases include nullable signed
extrema and half-open boundaries; counts, complete projected Scene bytes and
full source/layer IDs match across CRSs and pitch. Already-issued typed Data
survives source/index/query disposal, exhausts exactly two read copies and
rejects ordinary source picking. This is byte-level foundation evidence. Subsequent [trusted painter/export](geo-overview-painter-snapshot.md),
[public browser publication](geo-overview-browser.md) and [domain-member transport](geo-overview-membership-protocol.md)
have their own bounded proofs; massive latency and final spatial refinement remain open.

The Worker transport reserves its cleanup lane for command31 and extended
128-byte-ticket command8 ACKs (384-byte framing). Mixed XYMX cancel4/dispose5
also use that bounded lane; ordinary XYGT supply4 retains normal admission.
Actual strict-CSP retained-browser tests fill normal input capacity and verify
these cleanup requests reach Rust without early ownership loss, while ordinary
supply rejects before transfer. Malformed authority remains rejected by Rust.

## Internal Python transport

`python/xyg/_geo_overview.py` implements the same framing and callback settlement
contract as the typed Node/browser adapter. It is an internal transport adapter;
there is no new public chart constructor, host geometry/count policy, painter
mount or domain-cell source-membership API. Commands are forwarded through the
existing native bridge. Counts remain exact u64 Python integers and signed time
retains both i64 extrema.

The async driver captures immutable128-byte ticket authority and primitive kind
and authorized length before handing a separate dictionary to a storage callback.
It checks logical and owning backing capacity before supply, drops all borrowed
views before ACK, and waits for pending callbacks even under repeated task
cancellation. Read and write loans settle with their original command8/31 ticket;
cancellation cannot forge an early ACK. An obsolete completed terminal response
also observes cancellation before publication.

`OverviewLease` owns one immutable Data handle and drops parsed views before
cleanup. Concurrent cleanup coalesces, a rejected cleanup can be retried, and
successful cleanup remains idempotent. Cancellation during Data creation or read
waits for the operation to settle, then disposes the unreturned Data owner.
Actual-native tests exercise eight temporal cases, exact independent cell counts,
malformed packets, callback ticket mutation, repeated read/write cancellation,
receipt/read cancellation, source/index/query disposal, eight-Data admission,
two-copy lifetime quotas and transient cleanup failure/recovery:

```sh
cargo build -p xyg-core --release
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" \
  uv run pytest tests/test_geo_overview.py -q
```
