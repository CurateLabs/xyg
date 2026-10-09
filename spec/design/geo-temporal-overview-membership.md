# Exact temporal overview domain-cell membership

This engine foundation implements dossier §27/§28 drill-in over the immutable
`GeoOverviewResult`. It is separate from projected screen-bin membership and
uses no `GeoLodKey`, representative source ID, viewport culling, or host geometry
policy. The overview remains `temporal_exact=true`, `data_space=true`, and
`final_result=false`; listing its exact source members does not make its coarse
spatial rendering a final viewport result.

## Authority and API

`GeoOverviewMembershipSession::create(result, cell, sequence, previous, budget,
max_vertices)` accepts an owning `Arc<GeoOverviewResult>`, a cell in 0..256 and a
nonzero sequence. The result retains the privately canonical-validated source
manifest and overview index independently of the originating build, query,
Source, or output handles. Authentication of canonical XYGK chunks still uses
that manifest's exact generation, length, digest, chunk index, and source-row
ordinal. The external canonical chunk reader must remain available; retaining
Rust authority does not retain caller-owned external storage.

Continuation is an optional borrowed `GeoPublishedOverviewMembership` issued by
a prior session. It must retain the **same result Arc**, same cell, a nonterminal
continuation, and an older sequence. Equal snapshots or wire cursor bytes cannot
mint this capability. The private continuation includes the original source
cursor and checked cumulative matching-vertex count; its retained result binds
the entire camera/time/layer/style/state snapshot and overview/source digest.
Continuations are immutable read-only replay capabilities, not consuming state.
A terminal page cannot be resumed. No public cursor constructor or unleased Vec
extraction exists.

`step` or `step_with_cancel` returns `NeedRead`, `AwaitRelease`, `Complete`,
`Cancelled`, or `Disposed`. `supply` borrows exact bytes and a cancellation
predicate. `release_read` ACKs the exact private ticket after the host drops its
input/copies. `published` borrows an immutable page; `take_page` transfers its
owning guard. `cancel` and `dispose` cannot erase an outstanding read reservation;
its exact ACK and all ticket-copy drops settle that loan.

## Matching and paging

The source driver checks shared `TimePredicate` before touching geometry. Each
eligible canonical vertex is assigned by the existing
`geo_spatial_index::cell(source_crs, xy, grid16)` convention. Coordinates and IDs
are unchanged. Point and MultiPoint rows yield one `GeoOverviewMember` when at
least one vertex matches: the authentic `FeatureRef` and an exact u64
`matched_vertices`. MultiPoint duplicate vertices each contribute to the vertex
count, but the row occurs once. Repeated full-u64 IDs remain distinct source
rows; no reserved identity namespace or row deduplication by ID is introduced.
Null and empty geometries yield no members. Dateline/polar/CRS behavior is the
same policy used by overview construction. Camera-offscreen members are
intentionally included.

Each page contains at most the shared 4096 source records in canonical source
order. The sum of matching vertices is checked across continuations. Exceeding
the frozen cell count fails closed immediately; exhaustion requires exact equality
with `result.counts()[cell]` before publishing. There is no fabricated count or
partial-row record. An out-of-domain sentinel fails closed; a successfully built
private overview has already rejected such eligible coordinates.

`max_vertices` is a per-page cumulative geometry-work limit in 1..2 billion.
Every inspected eligible vertex counts, including vertices assigned to other
cells. A row is admitted atomically before inspection. If the next row cannot
fit and there was cursor progress, a continuation ends the page before that row;
if no progress is possible, `ResourceLimit` prevents an empty same-cursor loop.
Shared chunk/read-byte/row budgets likewise bound each page. Their counters reset
on the next issued page; the membership count and canonical cursor do not.
A page filled exactly at the last source row can require an empty terminal page
to prove complete source exhaustion and reconcile the count.

## Shared driver and memory

`geo_source_membership_driver.rs` extracts only the authenticated source scan,
page allocation, admission, cancellation, and read/ACK mechanics from the
existing projected `GeoMembershipSession`. That public API, its records, cursor
policy, `GeoCellQuery` projection matcher, and protocol bytes remain unchanged.
Both families now use one bounded lifecycle implementation. Overview matching
adds its separate typed per-row record and exhaustion reconciler.

All allocations use the existing global 128 MiB processor ledger; there is no
new pool and no raised limit. Before allocation, the complete local phase checks
retained overview/index credit, the prior continuation page's credit, the
manifest clone, 16 KiB driver/control/retired-read capacity, the page capacity
and 4 KiB page overhead. Before issuing a read it adds the canonical transfer/
parser peak `4 * encoded_bytes + 16 KiB`, bounded by the existing 96 MiB parser
peak and canonical chunk limits. The private `GeoOverviewResult::retained_bytes`
accessor counts existing credits without acquiring them again. Any other
caller-held outputs must also be deducted from the caller's local allowance;
the global ledger always includes all actual live allocations.

Each owning ticket clones an Arc to the same admitted read credit. Ticket
cloning allocates no new chunk buffer. Host copies must obey the admitted exact
request length before allocating, then settle callback work and release backing
storage before ACK. A raw session drop, cancellation, or corruption cannot
release the ticket-owned credit early. The decoded chunk is transient within
`supply` and drops before read ACK. Published records drop before their page
credit. Immutable earlier pages/results survive later cancellation, malformed
bytes, or failed admission.

## Evidence and remaining integration

Focused Rust tests cover independent temporal/CRS/domain-cell goldens, i64
extremes and null endpoints, full-u64 duplicate IDs, MultiPoint vertex-count/row
membership, private continuation rejection, source/index disposal lifetime,
three-page source order, row-atomic work limits, local one-byte admission,
global pressure and owning-ticket drop recovery, corruption, final-row and
publication cancellation, and exact count reconciliation. The six existing
projected-membership tests remain unchanged and exercise the extracted driver.

This is a bounded canonical scan, with linear source work. It makes no massive
interactive latency, browser paint, end-to-end host, selected overview, or issue
#50/#39 closure claim. Selected overview remains explicitly unsupported by the
existing command27 guard. Protocol commands45/46 are only a future integration
proposal, not implemented here; reply20 is already reserved for State nonce
retirement, and no new wire code is allocated by this engine change.
