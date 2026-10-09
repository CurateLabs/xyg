# Bounded geographic spatial hierarchy

This engine foundation refines retained Point/MultiPoint sources using an
external immutable page store. It preserves the canonical source-order,
projection, time predicate and direct/cluster/density policy in `geo_lod.rs`.
It does not replace that policy with a geographic or temporal pyramid. See
`geo-retained-source.md`, `geo-spatial-index.md`, and dossier §§17, 27, 28.
The existing flat index and its public protocol remain unchanged.

## Authority and storage

`GeoHierarchyBuildSession::new` borrows a privately validated
`GeoSourceManifest`, clones bounded metadata under a processor lease, and reads
**every** canonical chunk through its exact authenticated `ReadRequest`.
Point null rows have no vertex; valid empty MultiPoint rows have no record.
Every valid vertex retains original source-row ordinal, chunk/row identity,
full u64 feature ID, chunk-global vertex ordinal, canonical f64 coordinates,
optional signed i64 half-open interval, and optional f64 scalar bits. Repeated
feature IDs remain distinct source rows; MultiPoint vertices remain distinct.

Only complete canonical construction can return `Arc<ValidatedGeoHierarchy>`.
Its source, root, namespace, checksum, and lease are private. `verify` repeats
the complete construction and compares the resulting root checksum; neither an
imported checksum nor caller-authored page summaries alone confer pruning
authority. An omitted/changed canonical source chunk fails authentication;
a regenerated directory/root mismatch fails verification. There is no public
unchecked root/manifest constructor or unleased owning-byte extraction.

The host supplies storage, without filesystem, network, or browser policy in
Rust. Page IDs are deterministic within a build and start at one; each build
has a private monotonic namespace. Temporary and final pages in different
namespaces must never alias. Storage writes are tentative until the final
private root publishes. The host must persist an immutable exact page before
ACK, and must retain final pages while any root/result references them. Rust
cannot prove physical host durability; every subsequent read authenticates
exact bytes against its private root/run authority. A dishonest ACK can cause
an explicit read failure, but cannot publish changed query output.

## Bounded external construction

The grid defaults to 1024×1024; explicit admitted power-of-two grids span
16 through 4096. Grid cells are keyed by Morton order. The page grammar defensively reserves an unconditional overflow cell
(`u32::MAX`) for out-of-domain coordinates; current canonical `GeoColumn`
ingress rejects coordinates outside its declared CRS, before construction.
Time exclusion occurs before projection. Overflow cells and conservative camera/seam bounds
can increase candidates and cause explicit fallback.

1. Fill a 262,144-record sort buffer from authenticated chunks; sort by
   `(Morton cell, source row, vertex ordinal)` and emit immutable run pages.
2. Merge at most eight runs at once. Two preallocated vectors hold at most
   8192 compact descriptors each: start page ID, number of contiguous pages,
   number of records, and rolling checksum. No per-page descriptor array grows
   with the source. A run is read completely and its rolling checksum and
   record count verified before the operation can publish. Earlier records
   may produce tentative merge/final writes, which confer no root authority.
3. Consume the final sorted stream into same-cell payload pages. Flush a
   streaming fanout-128 leaf-reference tree for each cell, wrap its root, and
   feed a second streaming fanout-128 tree over cell roots. Each tree has twelve
   fixed levels of at most 128 descriptors; no resident array of all cells or
   all leaf references is created.

Construction `new` and full-rebuild `verify` require an explicit nonzero
`max_write_bytes: u64`. This cumulative external-storage hard cap counts every
issued temporary and final page, including tentative pages later cancelled; it
is independent of `QueryBudget.max_read_bytes`. Checked addition and comparison
occur **before** write-ticket admission and page encoding/allocation, and again
before issuing the owning write. Exceeding either cumulative I/O cap is terminal
for that build and cannot produce private root authority. `written_bytes()`
reports issued bytes; an ACK does not reset this counter. External storage does
not receive an implicit per-merge-pass allowance. A caller must choose a cap
that covers its cold-build amplification and storage policy.

The cumulative vertex ceiling is 2,000,000,000 and the initial-run ceiling is
8192. Both are checked, never saturated or silently thinned. Eight-way merges
therefore require at most five passes at the admitted run ceiling. Twelve
levels bound directory construction and traversal. Existing source row,
chunk, metadata and canonical chunk limits still apply; this hierarchy removes
the flat per-leaf resident-directory ceiling, not those source limits.

## Page grammar

All integer/f64 fields are little endian. Reserved fields and unused page tails
must be zero. Bytes are raw typed frames, not JSON-number payloads.

- `XYHR` v1 temporary pages are exactly 65,536 bytes: a 64-byte header (magic,
  version, page ID, record count), followed by at most 682 96-byte records.
  Each record contains cell u32, twelve zero bytes, then the canonical 80-byte
  indexed vertex grammar. Headers and strict sort order are validated. The
  complete run uses BLAKE2s-8 with domain `xyg-hierarchy-run-v1`.
- `XYHL` v1 payload pages have a 64-byte header (magic, version, page ID, cell,
  count), followed by at most 818 80-byte vertex records. Source/vertex order
  is strict within the page. Exact length, full checksum and count/time
  summary must match private directory authority.
- `XYHN` v1 directory pages have a 64-byte header (magic, version, page ID,
  kind, child count), followed by at most 128 128-byte child descriptors.
  Kind 2 is a leaf-reference tree, kind 3 a single cell-root wrapper, and kind
  4 the outer cell-root tree. Kind 1 descriptors refer to `XYHL`. Every child
  page ID precedes its parent; kinds, ranges, counts, page totals, time unions,
  sorting, exact length and checksum are validated. Directory count sums use
  checked u64 arithmetic.

The 128-byte descriptor stores page ID/length at 0/8, digest at 16, kind/first
Morton key/last key/endpoint presence bits at 24/28/32/36, vertex count/payload
page count at 40/48, start/end i64 at 56/64, and zeros at 72..128. Missing
interval endpoints are unbounded and encoded with zero raw value. Time unions
remain conservative; they are candidates, not exact visible membership.

All final page checksums use BLAKE2s-8 with domain
`xyg-hierarchy-page-v1`. Root checksum domain `xyg-hierarchy-root-v1` binds
source digest, generation, grid and root descriptor. Namespace is separately
bound to tickets, and does not change canonical rebuild bytes/checksum.

## Exact refinement query

`GeoHierarchyQuerySession::new` borrows an owning private hierarchy and binds
canonical camera, exact time predicate, layer ID, style/state revisions and
LOD options through the ordinary `GeoLodKey`. This foundation is an immutable
query API; a future mutable publication registry must enforce nonzero/monotonic
operation sequence and revision transitions, as existing source/index
protocols do. A private hierarchy does not authorize revision regression.

The query traverses authenticated outer pages with conservative Morton-prefix
camera bounds, including perspective/frustum, seam aliases, and world-wrap
policy shared with the existing index. It prunes time-excluded summaries first.
It selects at most 256 cell streams. Selection 257 returns
`FullScanFrontier` before reading payloads. Directory/work admission can return
`FullScanWork` before refinement; the host may then explicitly invoke canonical
source LOD. Errors and corruption never select fallback silently.

Each selected stream is traversed by payload-page ordinal using authenticated
child page totals. A bounded 64-node LRU cache avoids a retained directory path
for each of 256 streams. A 256-head source-order heap merges records by
original source row and vertex ordinal before calling the single
`GeoPointLod::fold_indexed_vertex` implementation. Count/aggregate passes share
cumulative work/read limits; time is checked before geometry projection in
both. The ordinary full source and hierarchy produce identical direct
records, reduced counts/centroid f64 bits, key, visibility and XYGS Scene bytes.
Their examined/projected-work counters may differ because pruning is the
purpose of the hierarchy.

Default query limits are 65,536 directory reads, 65,536 payload reads,
200,000,000 decoded vertex records, and 16 GiB cumulative read bytes. All
cumulative counters are u64 on native and wasm32. Payload/record totals are
preflighted after cell planning; repeated-pass limits remain checked at actual
read/fold. No camera query is promised to fit these defaults. Whole-world exact
screen aggregation still needs linear eligible-vertex work and will normally
fall back; the separate temporal overview remains an explicitly non-final
**data-domain** count tier, not exact screen bins.

## Live memory and cancellation

Every session, parser, sort buffer, merge head, tree/control/cache vector and
loan is preleased from the existing **global 128 MiB processor ledger**.
There is no new pool. Caller query allowances include the retained hierarchy
lease. Other source sessions, old roots and published results remain charged
and may make a new operation return `ResourceLimit`.

Construction reserves source-clone metadata + 32 MiB sort allowance + 1 MiB
compact-run descriptors + 4 MiB heads/tree/control. Source reads reserve
6×encoded length +64 KiB before host allocation and parser access; other read
and write loans reserve 4×encoded length +64 KiB before encoding/host access.
A decoded source chunk **retains its read credit after host ACK** until fully
consumed or dropped, including during run flushes. The complete admission sums
base + retained chunk + new loan. A maximal admitted source chunk may therefore
be rejected for this sort phase even if parsing that chunk alone fits the
source processor policy. There is no extra per-phase allowance above 128 MiB.

Query reserves shared LOD worst-case output/transition allowance, 256 fixed
payload heads, 64 directory-cache nodes, twelve bounded planner levels and
control before allocation. Successful construction shrinks its lease only
**after** working buffers drop, retaining source metadata +64 KiB. Successful
query output similarly drops working buffers before shrinking to ordinary
LOD output allowance +16 KiB; the owning result retains its hierarchy Arc.

`GeoHierarchyTicket` privately binds session owner, storage namespace, serial,
kind, page ID, exact encoded length/digest and optional complete source read
request. Ticket cloning shares a single Arc credit. Supply/ACK/release require
all fields to match, not just page ID. Cancellation or failure stops publication
but keeps pending loans until exact ACK/release (and all owning ticket clones)
drop. The host drops its supplied/copied buffer before settlement. No callback
runs inside Rust or borrows an unleased owning Vec from it. Writes expose only
a borrowed slice tied to pending ticket authority. Global allocation failure
is terminal for that query/build; a caller must restart, never continue a
partially advanced prefix/tree after an error.

## Evidence and remaining gates

Focused engine tests cover canonical temporal/MultiPoint/null identity and
Scene parity, mixed CRS seam/wrap/pitch, exact two-pass reduced centroid bits,
frontier/work fallback before payload I/O, canonical rebuild verification,
corruption of tentative run/final directory data, exact external write cap /
one-byte-over rejection before loan admission, cancel/ACK at that cap,
cancellation inside folding,
exact namespace/ACK, retained chunk credit and concurrent global pressure.
A deterministic 1M-point tracer exercises external sort/merge and paged fine
cell construction, comparing a narrow result against canonical full-source
Rust LOD. This is bounded functional evidence, not a 1B interaction claim.

Native/WASM protocol/host integration, exact membership/rows dispatch,
projection/painter/export authority, final packaged wasm32 parity, disk-backed
10M/100M cold-build/warm-query timings and end-to-end interaction remain
separate gates. No 1B runtime latency, first-paint SLA, browser throughput or
massive whole-world screen-bin speedup is claimed by this engine slice.

The focused writer run (`cargo test -p xyg-engine --lib geo_spatial_hierarchy
-- --nocapture`) passed 17/17, including the exact-cap/cancellation regressions; strict `cargo clippy -p xyg-engine --lib --tests
-- -D warnings` passed. The deterministic 1M tracer recorded 965,173 external
pages totaling 457,163,072 bytes, including temporary runs and sparse-cell
wrappers; its zoom-12 narrow query read 93 directory pages and four payload
pages, examined seven candidate vertices, and matched canonical result/Scene
bytes. Retained root credit was 67,256 bytes and result credit 1,589,464 bytes.
These are functional/debug observations, not native/browser timing promises.
Many small cell payloads create real cold-build/storage amplification; later
release disk-backed measurements must report that cost, not just warm pruning.
