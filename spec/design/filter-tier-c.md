# Filter Tier C programmatic checkpoint

This is the **programmatic checkpoint of #112**, not completion of #112 or
milestones 4–7. Rust `FilterTierCSession` is called through ordinary Python
`Chart.filter_session`, Node chart `filterSession`, and browser
`createWasmFilterSession` on a dedicated ordinary Worker. They expose the same
XYFC/XYFR v1 protocol through native ABI 402 and WASM ABI 36. No renderer,
chart-building surface, GPU allocator, or host-side predicate policy is added.
The reviewed ABI 401 parent is `2cb7f0a13ec0af3a00b9dcfd2b104a2c579b7ac9`;
accepted main at fetch was `084b3c1b7c393e135476aab9610bf8334767b2ac`.

## Supported subset and exactness

A session owns one immutable-schema source, an inclusive finite range intent
on one active dimension, and one active-view cumulative index. Each passive
view declares a source dimension and strictly increasing finite cuts. Outer
bins extend to infinity; bins are lower-inclusive and upper-exclusive.
Nonfinite passive values are omitted from bins. The active grid has the same
cell convention. It retains each cell's observed finite minimum/maximum.
A query normalizes reversed endpoints and classifies cells against those
extrema. If any populated cell is only partly included, the default response
is `Boundary` and publishes nothing. Otherwise two cumulative entries per
output bin give exact counts, including a separate exact selected total.
Empty cells, empty sources, zero-width ranges, and inclusive endpoints require
no snapping. `exact=True` explicitly admits a full canonical boundary scan;
its response reports tier 2, fallback 1, and every row visited. That scan is
not a Tier C timing claim. Unsupported predicates fail closed.

Indexed queries inspect O(active cells) extrema and O(passive bins) cumulative
entries. They read **zero canonical rows** and never re-bin. Exact u64 counts
remain separate from future f32/u8 painter representations. Clear removes the
range predicate and uses standing exact totals, including rows with nonfinite
active values; selected totals can consequently exceed any passive bin sum.
No general A∧B∧C composition, two-dimensional active rectangle/passive
density grid, or idle prefetch
is claimed. Switching active dimension with an existing range is refused;
clear first. Switching/reconfiguring builds a replacement before publication.

Membership is an explicit separate bounded canonical-row page (maximum 65,536
rows, raw bitset, bit zero is the requested absolute first row). It reports
tier 2/fallback 2 and visited row count, including when the index was evicted.
There is **no prefix membership slab**. This checkpoint retains predicate
intent, not a full per-trace selection bitmask. Renderer-owned selected-count
planes and persistent materialized masks remain part of the next #112 slice.

## Identity and lifecycle

The source owner explicitly supplies a nonzero u64 source ID and nonzero epoch
(schema/base identity). Every subsequent command must carry that exact source,
epoch, source revision, and declared budget. There is no implicit cross-session
link by row position, generated UUID, view ID, or coordinate coincidence. All
views reference dimensions of the same retained Rust source. Absolute row
identity is `(source ID, epoch, first row + canonical position)`; u64 IDs above
2^53 are preserved in binary. Current supported residency/size quantities are
u32-bounded for native/WASM parity, while absolute source/row identities are u64.

Append must match the dimension count and next absolute first row. Rust copies
a candidate source under old-plus-new admission, advances source revision,
invalidates the disposable index, and retains range intent. Membership remains
exact immediately; count queries fail closed until rebuild. Eviction drops
only index arrays; it preserves source, configuration, filter fingerprint, and
intent. A rebuild is deterministic for the same source/configuration. Count-producing
clear also requires a resident index in this checkpoint; after eviction/append,
rebuild first. Immediate clear without rebuilding remains required for the
parent-owned live interaction slice. Schema
or base replacement requires a new explicitly owned source session/epoch;
filesystem spill/reopen and arbitrary base-filter mutation are not supported
by this checkpoint and must not substitute a different source identity.

Request revisions are positive monotonic u64 values. A structurally valid
request consumes its revision even if product admission/publication fails;
retry with a newer revision. The visible revision advances only on success.
Cancellation preserves visible state and intent. Native cancellation has an
independent atomic watermark and scans check it every 4,096 rows and before
publication. A newer admitted native request likewise supersedes old work.
The shared state mutex prevents old work from replacing an already published
newer result. WASM commands are synchronous and serialized in the dedicated
Worker: cancellation queued during a synchronous operation cannot interrupt
that operation. Cooperative Worker chunking is explicitly pending, not claimed.

Source/configuration/index/intent replacements publish only after all fallible
construction, result allocation, capacity checks, and cancellation checks.
An undersized native output receives -4 plus required bytes; WASM receives
resource-limit 3 plus one raw u64 required length. Neither publishes the
candidate. The normal Worker uses its declared arena output capacity.

## Memory and work accounting

For C active cells and W = 1 + sum(passive bins), index bytes are
`8*(C+1)*W + 8*W + 16*C`: cumulative u64 slabs, unfiltered totals, and active
extrema. This is independent of canonical row count. Cuts, view descriptors,
source columns, and reply/scratch are additional budgeted storage. There is no
C × canonical-row-word allocation. Limits are 64 dimensions, 64 passive views,
4,096 cuts per axis, 65,536 total slab channels, and 256 MiB per protocol packet.
Checked sums/products reject overflow identically on native/wasm32. No existing
LOD, selection, deadline, CI, WASM artifact, or GPU budget is enlarged.

A native handle is opened with an immutable maximum budget; a WASM session
uses the owning instance’s unchanged maximum arena budget as that ceiling.
Rust refuses a declared session budget above that ceiling or 256 MiB. The
browser factory requires an explicit `budgetBytes` within its dedicated
Worker limit. It cannot enlarge the Worker’s existing resource limit.

The declared budget governs Rust session working storage plus one incoming
packet and one Rust output. It admits old-plus-candidate canonical/config/index
storage, query scratch, and the output before allocation/publication. Session
and descriptor accounting uses conservative fixed logical slots (512 per
session, 24 per canonical column descriptor, 64 per view) so complete replies
are byte-identical across 32/64-bit hosts; numeric vectors use their allocated
capacities. These are logical accounted bytes, not RSS, allocator headers,
transport socket memory, caller-owned source arrays, or the native caller's
output buffer. No result cache is retained. Refusal preserves the old index;
there is no hidden eviction-to-make-a-replacement-fit policy.

`rows_read` counts visited canonical row positions, not individual scalar
loads or physical I/O. `prefix_cells_read` counts cumulative scalar reads;
cell-extrema inspection is additionally bounded by the configured active
cell count. Membership page work is never reported as an indexed count query.
Replies expose source identity/revision, request and visible revisions,
normalized-predicate BLAKE2s-64 fingerprint (personalization `xyfilt01`), serving
tier, index/resident/peak logical bytes, exact selected total, affected view IDs,
work, and fallback. Fingerprints include source/epoch/source revision, active
dimension, presence and normalized f64 endpoints; signed zero is canonicalized.
They are cache stamps, not security or dataset-content digests. Latency
instrumentation/qualification remains pending; deterministic packets do not
invent a measured latency.

## Binary protocol v1

All multibyte fields are little-endian. Live values are raw binary, never JSON
numeric arrays. Source f64 is canonical ingress, not a painter payload. Hosts
frame/decode; Rust validates, builds, selects tiers, and hashes.

XYFC has a 96-byte header:

| Offset | Type | Field |
|---|---|---|
| 0 | u8[4] | `XYFC` |
| 4, 8, 12 | u32 each | version=1, operation, flags (bit 0: explicit exact boundary; query only) |
| 16, 24, 32, 40, 48 | u64 each | request revision, source ID, epoch, source revision, budget bytes |
| 56, 64, 72 | u64 each | operation arguments |
| 80, 88 | f64 each | inclusive query endpoints |

Operations: 1 open, 2 append, 3 configure/build, 4 rebuild, 5 range, 6 evict,
7 clear, 8 cancel through this request revision, 9 membership page.
Open/append arguments are dimension count, incoming row count, absolute first
incoming row; payload is dimension-major f64. Open source revision is 1;
append carries the current revision and Rust advances it. Configure arguments
are active view ID, active dimension ordinal, passive view count. Payload is
`u64 active cut count; f64 cuts[]`, followed per passive view by
`u64 view ID; u64 dimension ordinal; u64 cut count; f64 cuts[]`.
Membership arguments are absolute first row and page length. Other operations
have no payload. Non-query unused header arguments are ignored; version,
operation, flags, lengths, and all accessed quantities are validated.

XYFR has a 192-byte header. Offsets 0/4/8 are magic `XYFR`, u32 version 1,
u32 status; offset 12 is reserved zero. Starting at offset 16 are 22 u64s:
requested revision, visible revision, source ID, epoch, source revision,
filter hash, tier, index bytes, resident bytes, peak bytes, rows read, prefix
cells read, fallback, active view ID, selected count, affected view count,
newest revision, absolute source first row, source row count, membership page
first row, membership byte count, and has-intent (0/1). Selected count is meaningful only for a successful
serving tier (2/3); control/error packets reserve that slot as zero and public
decoders expose it as `None`/`null`, never as an observed zero selection.
For each affected view,
the payload has `u64 ID; u64 bin count; u64 counts[]`; non-count operations
return zero bin count. Membership bytes follow. Status values are 0 success,
1 malformed, 2 budget, 3 stale, 4 cancelled, 5 missing source/config/index,
6 unresolvable boundary, 7 source mismatch, 8 allocation failure. Failed
requests retain the prior visible identity, revision, and predicate stamp.
Native handle/ABI failures are separate negative adapter status values.

## Proof and remaining acceptance

`tests/fixtures/filter_tier_c/session.bin` retains complete requests/replies;
its generator verifies successful count/membership packets against an independent
full scan. Rust engine, native C/Python/Node, the native WASM adapter tests, and
the actual packaged wasm32 module replay those bytes. A bounded Chromium
Worker journey replays the protocol and calls the public browser factory over
five passive dimensions. It does **not render five coordinated views**.
Run commands and exact artifact/environment bindings live in
`spec/performance/filter-tier-c-programmatic-2026-11-07/README.md`.

Next parent-owned slices must integrate the same session protocol with ordinary
two-dimensional passive density grids, selected-count density painting and
canonical point membership, pointer and
keyboard editing/cancel/clear, async newer-request delivery and Worker chunk
cancellation, spill/source reopening, composed predicates, and all required
compatibility. They must reuse the single existing renderer and the reviewed
logical GPU ledger, without importing the unapproved producer candidate.
The committed 100M fixture, five **rendered** linked views at ≥50 FPS, CodSpeed
build/query evidence, browser traces, accessibility journeys, memory/payload
qualification, and reproducible competitors across all required scales remain
open. No performance lead over Falcon/Mosaic, Matplotlib, Seaborn, Plotly,
Bokeh, Altair, Datashader, HoloViews/hvPlot, or emerging libraries is claimed.
