# Exact temporal geographic overview foundation

This engine slice implements an authenticated external temporal-count index for
Point/MultiPoint retained sources. It is a **data-domain overview**, separate
from the current exact geographic screen-bin/direct processor. It does not close
#50, demonstrate interactive latency, or introduce a product host/ABI surface.
Dossier §17 permits recorded progressive tiers; §27/§28 require bounded storage,
explicit decisions and truthful aggregate identity.

The domain is the shared spatial index's 16×16 Web-Mercator cell convention,
bottom-first `row * 16 + column`. Source CRS and canonical boundary conventions
remain those of `geo_spatial_index::cell`. The complete plane describes source
domain cells; it does not describe exact viewport-visible populations or
projected screen-bin centroids. Pitch, clipping and viewport projection do not
change these source-domain counts. A renderer must label this tier and project
its domain cells in Rust. The core result provides no painter or membership
policy and never approximates count scaling. The separate typed extension in
`geo-temporal-overview-protocol.md` supplies Rust Scene lowering while retaining
this data-domain/nonfinal identity.

The defensive shared-cell overflow sentinel produces explicit
`UnsupportedDomain` and no overview capability. Current canonical ingress
already rejects coordinates outside the declared CRS world bounds before a
validated source exists; this fallback does not weaken that validation.
Coordinates are never silently dropped or normalized into a different source identity. Existing exact
source/index queries remain available. No geometry family beyond Point and
MultiPoint is admitted. Empty valid MultiPoints and null geometries contribute
zero vertices; each valid vertex contributes once. Repeated source IDs do not
collapse vertex counts. IDs, original ordinals, coordinates, scalar bit patterns
and topology remain in the authenticated canonical source; no representative
feature ID is invented for an overview cell.

## Temporal policy

Each finite interval start contributes a start event and each finite end an end
event in that vertex's domain cell. Unbounded starts contribute to a baseline
plane; unbounded ends contribute no end event. Absent interval planes mean both
endpoints are unbounded. Shared canonical interval validation enforces valid
half-open intervals before events exist.

For each cell:

* All: the complete valid-vertex count.
* Instant t: baseline + starts ≤ t − ends ≤ t.
* Window [s,e): baseline + starts < e − ends ≤ s.

These formulas evaluate the exact shared `TimePredicate`; they require no i64
arithmetic at the endpoints, so MIN/MAX and half-open ties retain their meaning.
Counts and subtree sums are checked u64, never saturating u32. Subtraction fails
closed if corrupted/inconsistent data would make a negative population.

## Authentication and lifecycle

`GeoOverviewBuildSession::new` accepts only a privately validated
`GeoSourceManifest`. It re-authenticates every exact XYGK chunk using the shared
Rust parser and the manifest's digest/length/row identity. The manifest's existing
resource grammar is reused; there is no second source geometry parser.

`step`/`step_with_cancel` issues a private owning `GeoOverviewTicket`. Kind 1
requests a canonical chunk, kind 2 requests an immutable derived page, kind 3
requests persistence of a borrowed exact page. Tickets expose getters but their
authority fields cannot be authored by hosts. Source requests include the
canonical `ReadRequest`; derived storage is addressed by `storage_namespace()`
and page ID. The storage namespace is the originating build, while `owner()` is
the active build/query operation identity; queries do not alias another build's
page IDs. Exact serial/namespace/kind/length/digest matches are required on supply
and ACK. The owning ticket retains its host-copy reservation even if a raw Rust
session is dropped before the host settles its request.

After supplying a read, drop host input storage before `release_read`. For writes,
`write_bytes` returns only a borrowed slice. Persist immutable exact bytes, settle
storage work and drop borrowed/transient host copies before `ack_write`. Writes
cannot confer authority until the complete canonical build finishes. Cancellation
or failed digest validation prevents publication. Outstanding loans remain
charged until exact ACK and all owning ticket copies are dropped. Hosts must
bound their resident external-storage cache and honor the ticket reservation
before allocating; persisted storage itself is caller-owned out-of-core data.
No filesystem, network, shell or browser I/O is imported by this implementation.

The private `ValidatedGeoOverview` holds the validated source, root descriptor,
all/baseline counts and an owning shared processor lease. It cannot be constructed
from imported directory hashes. `verify(..., expected_digest)` repeats the entire
canonical build and compares the deterministic final digest before constructing
that capability. The digest binds canonical source digest/generation, the
recursively authenticated sorted tree and complete baseline/all planes. Forged or
omitted events cannot acquire query authority through an imported summary.
This first verification seam rebuilds storage; it does not cheaply reopen an
untrusted existing artifact.

`GeoOverviewQuerySession::new(index, snapshot, camera)` validates the exact
source digest/generation, shared camera rebuild key and temporal predicate. The
complete `GeoOperationSnapshot` accompanies the result, including all
camera/time/layer/style/state revisions. Each query is an independent immutable
job; a future mutable protocol/controller must enforce publication sequences and
revision transitions. No current SourceSession transition guarantee is implied.
Queries traverse at most two logarithmic temporal prefixes, authenticating each
requested page and validating its histogram/range against the trusted descriptor.

Results expose borrowed counts and immutable metadata accessors, retain validated
source authority independently, and own their processor credit. They explicitly
report `temporal_exact=true`, `data_space=true`, `final_result=false`. Cancellation
of later jobs, input corruption, index/session disposal and failed new allocations
do not change an already handed-off result. There is no unleased owned Vec export.

## External sort and tree

The builder retains at most 262,144 events in its initial sorting buffer. A sorted
run spills event pages; eight sorted runs are merged using one bounded page head
per run. Repeated passes continue until one globally sorted run remains. No full
source array, mask, CSR, or global per-feature state is retained.

A leaf event page holds at most 4,092 fixed16-byte records. Tree nodes hold up to
eight children. Each child descriptor contains its page ID/length/digest, inclusive
first/last event time, and separate 256-u64 start/end histograms. A full covered
subtree contributes its histogram without reading descendants; only a boundary
subtree is descended. At most twelve construction levels are admitted. Histograms
are integer reductions; source event ties and arbitrary source order cannot
change the result. Source IDs/ordinals remain canonical rather than being sorted
or rewritten with these derived events.

Canonical pages are little-endian, zero-reserved and at most 65,536 bytes. XYOE v1
has a64-byte header (magic/version/page ID/event count), followed by16-byte events:
i64 timestamp, u16 domain cell, u8 end flag and five zero bytes. XYON v1 has the
same header shape with child count, followed by4,144-byte children: u64 page ID,
u64 encoded length, digest8, i64 first/last time, zero8, then512 u64 counts.
Each page is authenticated with the existing Blake2s8 implementation and the
`xyg-overview-v1` domain. The final checksum has `xyg-overview-root-v1` domain.
These magics require registry ownership before a public wire protocol is added.

## Memory and work limits

There is no new pool. All engine allocations and anticipated host transfers use
`GeoProcessorLease` in the existing global128 MiB non-cache processor ledger;
other retained processor work and old outputs reduce the available allowance.
This slice does not allocate in, or enlarge, the384 MiB derived pool. Existing
transport reservations and the overall retained512 MiB policy remain unchanged.

Before cloning/allocating, the builder reserves the manifest clone, two fixed
524,288-entry page-reference vectors, two16,384-entry run vectors, the262,144-event
buffer and4 MiB for merge heads, tree levels, encoding and control scratch. The
base reservation is about40 MiB plus canonical manifest clone credit. Metadata
credits use fixed upper-bound layouts rather than platform-dependent Rust struct
sizes. Before each
read/write it checks the caller's complete processor allowance and acquires an
additional exact transfer/parser reservation (6×chunk bytes+64 KiB, or
4×derived-page bytes+64 KiB). The shared parser additionally enforces its original
96 MiB peak and16 MiB chunk ceilings. Large chunks or simultaneous jobs can
therefore reject before I/O; no per-phase budget doubling is allowed. The decoded
canonical chunk retains its read credit after ACK and host ticket release, until
processing drops that chunk. Run flushes account for both that retained credit
and the new write loan. Cancellation retains the same charge until the decoded
chunk and outstanding loans are dropped.

At most2 billion source vertices,524,288 sorted-run pages per pass,16,384 initial
runs and12 tree levels are admitted. Source row/chunk/read-work limits are the
caller's shared `QueryBudget`; cumulative read bytes are u64 and include sorting
merge and tree-build reads. Host storage capacity must be planned separately:
finite start/end events can approach32 bytes per source vertex for each sorted
pass, and old runs remain caller-owned until the host performs cleanup.

A query reserves256 KiB for its fixed two prefix accumulators, bounded node/event
decoding and control scratch, plus its exact page loans. Each published2048-byte
count plane retains16 KiB credit for counts, immutable key and ownership overhead.
Boundary-node query admission is retry atomic: a failed read-loan reservation
leaves the next node intact. Run-page capacity rejection is terminal, including
a failed ACK, and cannot publish a tree with an omitted page.

Publication drops sort/run buffers before shrinking their lease to the retained
validated manifest and16 KiB root/baseline/all-state allowance.

These explicit limits permit a1M correctness tracer without N-sized engine
arrays. They are a bounded foundation for larger external plans, not a verified
1B execution or cold-build/first-paint latency claim. Existing source row ceilings,
external storage, global admission, work limits and actual benchmarks still gate
any billion-class run.

## Evidence and remaining work

Focused tests cover independent temporal/domain-cell goldens at i64 extremes,
null endpoints, null/empty geometry, duplicate/full-u64 IDs, MultiPoint vertex
population, both CRSs/dateline, full canonical rebuild verification, malformed
source/page digests, private ticket mismatch, cancellation/retired loans, global
pressure/drop recovery and old-output survival. A generated1M fixture services
real source/read/write tickets, exercises external multi-run merge and multilevel
histogram query, compares all256 counts with an independent row oracle and
reports build I/O, external bytes, prefix reads and processor peak.

Reproduction on base `b5b1e75b3525a6849fbfde319695933f98323a74`, Darwin
25.6.0 arm64, Rust `1.96.0 (ac68faa20 2026-05-25)`:

```sh
cargo test -p xyg-engine --lib geo_temporal_overview -- --nocapture
cargo clippy -p xyg-engine --lib --tests -- -D warnings
```

The focused run passed 11 tests. Its 1,000,000-row MultiPoint tracer generated
canonical chunks on demand and exercised two eight-way merge passes. Raw
evidence: 2,792 build reads, 2,910 writes, 10 prefix reads, 66,895,528 bytes peak
processor reservation, 185,259,808 external page bytes and a 2,048-byte result.
The debug test took 26.47 seconds for all 11 cases, including source generation
and the host storage map; this is correctness evidence rather than query latency.

The tracer's external page map is test storage, not a claim that keeping all
sidecars in application RAM is bounded. No native/WASM/browser latency, Scene,
paint or competitor win is established. Following the separate typed Rust
protocol/Scene extension, remaining steps are host storage and trusted painter/
snapshot integration, domain-cell membership, a spatially finer/paged hierarchy,
full independent native/WASM counts/receipt parity, and measured first-density/
refinement/p95/five-view evidence. Exact
current screen-bin output stays on the existing processor; this tier never
silently replaces its centroid or membership semantics.


The typed command and projected Scene extension is documented separately in
[geo-temporal-overview-protocol.md](geo-temporal-overview-protocol.md). It retains
this foundation's data-space/nonfinal identity; ordinary screen-bin semantics
and source-feature membership are not substituted.

## Typed lifecycle adapter

Selected-frame input is explicitly unsupported by this source-only index.
Command27 rejects privately retained selection/Scope authority, including empty
selection intent, before construction. Internal host frame-aware encoders reject
the same presence before dispatch; numeric raw ingress still receives the Rust
guard. Ordinary unselected count/Scene bytes retain their established contract.
Proof and reproduction: [selected authority guard](../performance/geo-overview-selected-guard-2026-10-09/README.md).

`js/src/67_geo_overview.ts` owns binary framing, private ticket copies and asynchronous transport settlement. Rust remains the sole implementation of counts, source authentication, cell geometry and temporal policy. `scripts/gen_geo_overview_wire.mjs` mechanically strips types and emits declarations into the Node host; its check rejects drift. This is an internal adapter, with no second chart-building API.

The typed packet is explicitly temporal-exact, data-domain and nonfinal. It retains full u64 identities and signed i64 time, offers 256 bounded u64 counts, and never fabricates source IDs. Count and Scene views are borrowed from the immutable Data owner; dispose drops them before Rust disposal. Pending disposal coalesces; a transient bridge rejection permits an explicit retry while views stay invalid. Parsed bytes are not a substitute for the private Rust owner in trusted paint, membership or export.

Each read/write callback receives a separate ticket copy. The driver captures exact private authority, length, namespace and kind before invoking callbacks, admits transfer storage before copying, and drops borrowed payloads before exact ACK. Cancellation waits for pending callback settlement; abort during a delayed terminal reply rejects success. Callback mutation cannot change the ACK authority.

`scripts/geo_overview_conformance.mjs` exercises actual release native Rust and packaged WASM: eight temporal cases with byte-identical counts and Scene, nine malformed-packet controls, callback mutation, cancelled-read disposal while awaiting exact ACK, delayed terminal cancellation, eight retained owners, two-copy quotas, old Data after source/query/index disposal, source-pick rejection and retry after a transport disposal rejection. This foundation does not yet establish overview browser paint, typed Python hosts, exact domain membership or massive latency.
