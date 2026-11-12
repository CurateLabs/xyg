# Filter Tier C linked density checkpoint

This is a **bounded linked-density checkpoint of #112**, not completion of #112 or
milestones 4–7. Rust `FilterTierCSession` is called through ordinary Python
`Chart.filter_session`, Node chart `filterSession`, and browser
`createWasmFilterSession` on a dedicated ordinary Worker. They expose the same
XYFC/XYFR v1 protocol through native ABI 403 and WASM ABI 37. The opt-in
`attachFilterDashboard` binds existing composed ChartViews to the same session
and ordinary density painter. No second renderer, chart-building surface,
GPU allocator, or host-side predicate policy is added.
The reviewed ABI 401 parent is `2cb7f0a13ec0af3a00b9dcfd2b104a2c579b7ac9`;
the reviewed programmatic checkpoint is `b91b8099ff1281f3740c8f8d4fde461509c332d0`.
Required accepted M5 main `58960c7c6c814ed049209052cf66d77b5bb7ecfd` was
integrated by merge `514a2ac72a5b90ef53c8b8acc87e1afc345c9b5c`, preserving
both parents and historical receipts. Original accepted main was
`084b3c1b7c393e135476aab9610bf8334767b2ac`.

## Legacy cut-axis mode and exactness

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
remain separate from f32/u8 painter representations. Clear removes the
range predicate and uses standing exact totals, including rows with nonfinite
active values; selected totals can consequently exceed any passive bin sum.
Legacy opcode 3 has no composed predicates or 2D density grids. The linked
extension below adds those passive grids and range/mask composition;
two-dimensional active rectangles and idle prefetch remain open. Switching active dimension with an existing range is refused;
clear first. Switching/reconfiguring builds a replacement before publication.

Membership is an explicit separate bounded canonical-row page (maximum 65,536
rows, raw bitset, bit zero is the requested absolute first row). It reports
tier 2/fallback 2 and visited row count, including when the index was evicted.
There is **no prefix membership slab**. This checkpoint retains predicate
intent, not a full per-trace selection bitmask. The linked extension adds exact aggregate selected-count planes and an
explicit base mask; it does not retain a full materialized result mask.

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
exact immediately; legacy count queries fail closed until rebuild; linked queries record an
automatic rebuild, as specified below. Eviction drops
only index arrays; it preserves source, configuration, filter fingerprint, and
intent. A rebuild is deterministic for the same source/configuration. Count-producing
clear also requires a resident index in legacy mode; after eviction/append, rebuild first. Linked mode supports
immediate clear with a recorded rebuild. Schema
replacement requires a new explicitly owned source session/epoch.
Serializing/reopening filter sessions, managed spill creation and arbitrary non-range predicates remain unsupported; none may substitute a different source identity.

Request revisions are positive monotonic u64 values. A structurally valid
request consumes its revision even if product admission/publication fails;
retry with a newer revision. The visible revision advances only on success.
Cancellation preserves visible state and intent. Native cancellation has an
independent atomic watermark and scans check it every 4,096 rows and before
publication. A newer admitted native request likewise supersedes old work.
The shared state mutex prevents old work from replacing an already published
newer result. The low-level synchronous WASM compatibility path remains
serialized: cancellation queued during one synchronous operation cannot interrupt
it. The public Worker session uses the cooperative build/count/membership
continuation described below. Resident source ingress and configuration parsing
remain synchronous; cooperative shipping qualification and portable file paging
remain pending.

Source/configuration/index/intent replacements publish only after all fallible
construction, result allocation, capacity checks, and cancellation checks.
An undersized native output receives -4 plus required bytes; WASM receives
resource-limit 3 plus one raw u64 required length. Neither publishes the
candidate. The normal Worker uses its declared arena output capacity.

## Memory and work accounting

For C active cells and W = 1 + sum(passive bins), index bytes are
`4*(C+1)*W + 8*W + 16*C`: private cumulative u32 slabs, unfiltered u64 totals,
and active extrema. Linked mode also retains `8*W` bytes of u64 base totals.
Both resident and issued-paged source ingress and append already refuse more
than `u32::MAX` canonical rows. Each row contributes at most once to each
channel, so every cumulative entry is an exact count bounded by that row limit.
Range differences widen to u64 before entering the public reply. Absolute
source/row identities, selected totals and all wire count planes remain u64;
large absolute first-row values do not enlarge the canonical row count.
Expanding the supported row-count limit requires revisiting this storage proof.
Admission and retained diagnostics charge actual numeric vector capacities,
including the old and candidate slabs during a rebuild. The allocation is
independent of canonical row count. Cuts, view descriptors,
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

Canonical C clauses keep their existing64-clause cap. Restoring the active
clause orders at most64 `(view ID, dimension)` keys with a bounded in-place
insertion pass; it preserves all range bits, allocates no sorting scratch,
and retains the same pre-sort cap refusal. This replaces a general-purpose
quicksort for this private bounded list only. Arbitrary key permutations and
high-u64 IDs must produce the same canonical records, and begin/cancel edit
round trips are measured through CodSpeed separately from row scans/rendering.

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

## Issued native paged sources (continuation)

`Chart.filter_session` and Node `chart.filterSession` also accept a mapping of
issued `ChunkedColumns.column("x")` / `.column("y")` references. Every dimension
must be an issued plane; mixing arrays and issued planes refuses. Rust checks
the handles, plane ordinals and equal canonical row counts. The caller explicitly
declares correspondence between dimensions through the existing source ID,
epoch and absolute first row. Equal lengths alone do not assert that unrelated
files represent the same records. Source IDs and predicate fingerprints are
identity stamps, not a cryptographic authentication of file contents.

The native attach packet uses `XYFC` **version 2, opcode 16**, with the unchanged
96-byte header. Its arguments are dimension count, canonical row count and
absolute first row. Bytes 80–95 must be zero. The payload is one pair of u64s
per dimension: issued XYGC handle, then plane ordinal (x=0, y=1). Source revision
must be 1. There may be 1–64 dimensions; canonical row count must fit u32 and
the absolute row interval must fit u64. Attach acquires independent immutable
file/metadata leases, reads no data rows and publishes only after capacity and
cancellation checks. Repeated references to the same issued backing share a
reader within the session. Replies remain XYFR v1; subsequent operations use
the existing XYFC v1 protocol. XYFC v1's admitted operation set and all existing
complete fixture bytes remain unchanged. Unknown version/operation pairs fail
closed. WASM currently refuses this native-issued-handle version as Malformed;
it does not interpret a native handle as a browser file or fall back to arrays.

Index construction, explicit exact boundary scans and membership use the same
row kernels as resident sources, through a bounded canonical block accessor.
The reader preserves **every** row, including nonfinite pairs, NaN payload bits
and signed zero; public row identity remains `first_row + canonical_position`.
The XYGC viewport/page API deliberately omits nonfinite pairs and is not a
canonical source iterator. Numeric files must remain immutable while leased,
as with existing XYGC navigation. A source read/validation failure publishes
no replacement index, predicate, counts or revision. Indexed differences read
zero source rows. Evict/rebuild preserves intent and reopens no hidden copy.

The host-neutral `chunked_layout` decoder owns header, ordered metadata,
overview and canonical-page validation. Native positioned I/O uses this decoder;
a future Worker file reader must use it rather than reimplement XYGC policy.

An immutable lease retains the file and admitted chunk metadata, **not** the
viewport owner, its LRU/overview or generation watermark. Closing a viewport can
retire all its cached chunks without breaking a live filter. Reader cancellation
cannot cancel a viewport or another session. Filter close releases its leases;
append to a paged source refuses with Source and preserves prior state. A
changed file/schema requires a new issued source and explicit source epoch.

The session charges 128 logical bytes per paged binding, 64 per reader slot,
8 per dimension mapping, and each unique reader's immutable metadata and
128-byte file slot. Metadata storage uses allocated vector capacities. Reads
reserve a fixed-at-most-2-MiB logical workspace independent of source row count:
page length is the smaller of 65,536 and
`floor((2 MiB - 144*readers)/(32*readers))`. Each physical reader reserves
`32*page_rows + 144` bytes, conservatively covering raw paired f64 bytes,
decoded x/y columns, read slots and outer vector descriptors. The complete
workspace coexists with the accepted index, replacement index, scratch and
output under the unchanged session budget. Membership pages use their smaller
requested extent. A failed pre-read admission performs no source I/O. Exact
boundary fallback remains reported as a scan; this continuation does not turn
it into a row-independent indexed operation.

This continuation does **not** establish a process-wide resource budget,
cooperative Worker building, browser File/OPFS/HTTP transport, paged append,
materialized result masks, or the 100M/five-view performance acceptance. It is
the native source ingress for that remaining end-to-end work; no whole-issue
or milestone qualification follows from a native count-prefix test.

### Read-ticket layout acquisition

Native open now uses the transport-neutral Rust `LayoutReader`. Its first
issued ticket requests exactly the 64-byte XYGC header. After validating the
file length and header, Rust issues aligned metadata windows of at most
65,520 bytes and overview windows of at most65,536 bytes. These tickets skip
the canonical row region completely. Transport supplies the exact ticket
serial, offset, length and bytes; it cannot choose a different acquisition
interval. The same header/metadata/overview validators remain authoritative.

The reader admits512 logical control bytes, complete metadata/overview
capacity, and the larger of actual incoming buffer capacity and future read
windows before reserving layout vectors. Refused admission, a stale ticket,
a malformed late record, callback failure or cancellation leaves the current
ticket and accepted prefix unchanged. Cancellation is checked before work,
every64 records and immediately before committing a validated bounded window.
The completed immutable layout retains canonical row indices and f64 bits.
Canonical numeric-page decoding remains the separate bounded operation above.

The existing native open API has no caller budget; it uses an unlimited local
layout allowance and imposes no new default/resource policy. This allowance is
not a process-wide budget. A portable adapter must additionally account for
all external owners and transport copies before reading/staging tickets.
Browser `File` registration, instance-scoped source issuance, asynchronous
numeric-page tickets and filter attachment are still unimplemented. A tested
Rust ticket reader does not establish browser-file or100M acceptance.

## Cooperative filter transactions (development continuation)

`createWasmFilterSession` uses cooperative filter commands on its dedicated
Worker. The lower-level `worker.filterCommand(packet)` keeps the synchronous
XYFC/XYFR compatibility path; `{cooperative: true}` enables the continuation
adapter. Resident source creation/append and packet/configuration validation
remain synchronous. File-backed Worker source ingress is not yet implemented.

The WASM filter export and native `xyg_filter_session_execute` recognize a
separate XYFJ v1 control frame; native
ABI declarations, WASM function exports and XYFC v1 packets are unchanged.
All fields are little endian. A request has a 32-byte header: magic `XYFJ`,
u32 version1, u32 operation, zero u32, u64 token, zero u64. Begin (1) requires
zero token and carries one complete XYFC packet. Advance (2) and cancel (3)
require a nonzero instance-scoped token and no payload. A malformed control
frame does not consume a revision or cancel pending work. A response is either
ordinary XYFR or 32-byte progress: `XYFJ`, u32 version1, u64 token, u64 scanned
rows, u64 operation row count. Membership progress is relative to the requested
page. Completed row scanning may still have a pending cumulative-prefix phase;
only XYFR denotes completion. These control buffers contain binary integers,
not JSON numeric payloads.

The native concurrent gate validates this same control header in Rust. Only a
valid begin with an admitted inner XYFC header advances its newest-request
watermark. Advance/cancel tokens name existing work and never advance that
watermark. Malformed framing and inner headers preserve older pending work;
a newer admitted header supersedes it even when the body subsequently refuses.
Existing native pointer/capacity guards and the 256 MiB total input extent stay
unchanged, including the wrapper. Raw XYFC callers retain their synchronous
compatibility path. The wrapper's 32 live bytes are additionally charged during
each native cooperative turn.

### Native asynchronous and callback clients

The shared C ABI transport dispatcher is also compiled for Emscripten. Pyodide
retains raw XYFC compatibility and can advance/cancel in-memory XYFJ work through
the same export; this does not enable filesystem-backed XYGC sources there.
The exact-wheel Pyodide gate replays all 47 frozen raw packets, exercises real
cooperative progress, stale-token refusal and cancellation, and verifies that
the accepted index remains usable. ABI signatures, limits and source policy
are unchanged.

Node `createNativeFilterSession(columns, options)` accepts the same arrays or
issued XYGC planes as the synchronous session. It uses the existing Rust XYFJ
jobs and schedules subsequent bounded turns with `setImmediate`; no second
filter engine, C signature or thread-pool policy is introduced. Individual
native calls, local positioned reads, array ingress and validation remain
synchronous. Bounded work does not promise a hard I/O or wall-time deadline.
Malformed/stale requests leave older scheduled work intact. Supersession and
close reject pending operations, cancel their scheduled callbacks and release
the native owner. Repeated close returns the same completion promise, and
constructor failures retire their handles before rejecting.

The native adapter retains one caller-owned 2 MiB reply scratch and returns an
independent copy of every actual reply. Incoming/wrapped request storage and
caller/HTTP buffers are separate transport owners, not silently included in the
Rust session limit or a claimed global process budget.

A fresh asynchronous owner can issue `takeRegistration()` once. It returns
dimension names, a budget stamp and the genuine binary Rust source-registration
reply, without canonical arrays or native handles. Issuing it disables the
owner's programmatic request builder; the application forwards binary requests
through `executeTransport` and closes through the original owner. Registration
must precede other commands. The application owns access control and one command
stream; source IDs remain identity stamps rather than authentication.

Browser `createFilterSession(execute, close, registration)` adopts that accepted
registration through the same `FilterSessionClient`. The callback transports
unchanged XYFC/XYFR bytes; native scheduling remains on the server. The browser
retains names/source identity and bounded derived replies rather than fabricated
array-shaped columns. Invalid registration is rejected before calling either
transport callback or closing a caller-owned endpoint. The existing
`attachFilterDashboard` and ordinary density renderer consume its exact planes.
The shared client accepts source metadata monotonically by Rust's reply
watermark, so a delayed successful response cannot undo newer source metadata.

`activateDensity(active, views)` submits a changed authoring definition and
returns its genuine Rust reply. After that definition succeeds, a byte-identical
definition in the same source/epoch/revision/budget scope returns `undefined`
without submitting another command. Definition identity includes active/view
IDs, dimensions, cuts, grid bounds, resolutions and colors. Source/configuration
submissions invalidate this remembered definition before transport, since Rust
may accept them before their ACK arrives. Refused proposals are never remembered;
a later activation may resubmit accepted authoring to Rust. Delayed acknowledgements cannot overwrite a
newer accepted definition. This remembers accepted authoring metadata rather
than index residency. Rust still rebuilds invalidated or evicted indexes when
queries require them. `configureDensity` retains its explicit force-build
semantics and wire fixtures. The dashboard uses activation for repeated
gestures, falling back to explicit configuration for custom clients which do
not expose activation. Skipped activations can leave gaps in the client's
monotonic request counter; only submitted Rust commands consume wire revisions.

This explicit application callback boundary does not establish automatic widget
binding, portable Worker file registration, arbitrary-I/O responsiveness, or the
100M/five-view performance and wider host/accessibility acceptance.

An admitted job pins the immutable source through shared ownership; it never
clones the canonical columns. Its private candidate takes ownership of newly
prepared configuration/predicate replacements, the input packet and intermediate
buffers. Unchanged configuration/predicates stay in the accepted session and
are borrowed only after the continuation's revision/source checks. Suspending
a job does not make an extra copy of either accepted or replacement proposals. Each continuation
checks its token, admitted request watermark, accepted revision, source identity
and cancellation before/after work. A structurally valid newer XYFC header
retires old work even if its body refuses. Malformed/stale headers leave that
work intact. Only private completed work may finish a consumed revision; a
caller replay remains stale. Wrong continuation tokens and short output
capacity retain the candidate for retry. Cancellation, failed work and disposal
release private owners while preserving accepted source/configuration/index/
intent. A build followed by an exact fallback scan publishes as one transaction.

Rust performs at most `floor(16384/(1+views+retained clauses+base clauses))`
rows per turn (minimum1), then at most16384 cumulative additions. Prefix work
uses the same count kernels. Exact fallback and membership scans use this same
continuation discipline. TypeScript only frames control packets and schedules
actual Worker turns; it does not implement filtering, binning, admission or
predicate state. Optional capability-gated progress observations are evidence,
not product-policy inputs. Indexed queries retain their zero-row serving path. The public factory waits for Worker readiness and claims a fresh, drained
Worker before transferring ownership. A failed claim leaves foreign queued work
or an existing filter owner intact. Ordinary product lanes cannot use a claimed
filter Worker. Failed initialization after claiming waits for the owning
Worker's release acknowledgement before rejecting, preserving the original
failure if cleanup also fails.

Admission includes accepted and replacement data, saved packet capacity,
private configuration/predicate replacements, work buffers, completed intermediate index,
2048 logical control bytes, bounded page workspace and final reply. Every
continuation rechecks transient adapter staging slack. Peak diagnostics differ
from synchronous work because these private captures are real owners. The job
retains its complete admitted high-water mark across unrelated malformed/stale
packet refusals; final linked replies include that mark even after capture
copies have retired. WASM
staging charges accepted and pending filter bytes. The filter adapter also
charges all arena capacity outside the logical packet. A filter source requires
a dedicated instance: acquisition of incompatible retained authorities and the
reverse direction refuse before changing accepted state. This is an explicit
coexistence restriction, not a claim of process-wide memory accounting.

The bounded resident cooperative path passes normal-package qualification at
1,875,741 raw / 786,020 Node22 gzip-6 bytes, leaving 412 gzip bytes under the
unchanged caps. The matching-source controls cover build, prefix, exact fallback,
membership, cancellation, recovery and ownership; see the
[continuation receipt](../performance/filter-paged-cooperative-2026-11-11/README.md).
This does not establish hosted CI/queue readiness, 100M/five-rendered-view
performance, browser file paging, process-wide budgeting or whole-issue acceptance.

## Proof and remaining acceptance

`tests/fixtures/filter_tier_c/session.bin` retains complete requests/replies;
its generator verifies successful count/membership packets against an independent
full scan. Rust engine, native C/Python/Node, the native WASM adapter tests, and
the actual packaged wasm32 module replay those bytes. A bounded Chromium
Worker journey retains that original programmatic proof and now also replays
the linked fixture and paints five composed different-dimensional charts.
The original programmatic receipt remains immutable.
Run commands and exact artifact/environment bindings live in
`spec/performance/filter-tier-c-programmatic-2026-11-07/README.md`.

The bounded linked path below adds selected-count density, canonical membership,
range composition, live pointer previews/commit/cancel, keyboard creation/edit/
commit/cancel/clear, source invalidation, and atomic five-view publication.
The resident cooperative Worker path has bounded matching-package evidence;
portable file-backed Worker source/build/cancellation qualification remains open.
Other remaining requirements include spill/source reopening, persistent
materialized result masks, idle prefetch,
non-range predicates/active rectangles, log/nonlinear/nonprimary/large-offset paint
compatibility, automatic notebook-widget/native-host transport binding, actual
assistive-technology/hardware journeys, and all required scale qualification.
Distribution of the committed 100M fixture, five **rendered** linked views at
≥50 FPS, required hardware/browser traces, broader memory/payload qualification, and
reproducible competitors across all required scales remain open. No performance
lead over Falcon/Mosaic, Matplotlib, Seaborn, Plotly, Bokeh, Altair, Datashader,
HoloViews/hvPlot, or emerging libraries is claimed.

The manual native-callback walltime harness in
`benchmarks/test_codspeed_filter_dashboard.py` now separates indexed range
replies, density replies, cached painting and complete five-view updates on the
materialized 100M fixture. It uses 100×100 passive grids and one active cell per
CSS plot pixel at an explicit 256 MiB session budget. This is a bounded local
SwiftShader diagnostic, not trusted-input/RAF or ≥50 FPS qualification; see
the [baseline receipt](../performance/filter-dashboard-baseline-2026-11-11/README.md)
and [reproduction contract](../benchmarks/methodology.md#manual-native-callback-dashboard-walltime).

The [exact private-prefix continuation](../performance/filter-prefix-storage-2026-11-12/README.md)
qualifies the same346-cell/five100×100-grid materialized100M source at128MiB,
with a70,206,940-byte index and exact count/texture/membership oracles. The
private u32 storage follows the existing row bound, not a lower bin resolution.
Its bounded CodSpeed build and full-pipeline comparisons are diagnostic evidence;
they do not satisfy the open ≥50FPS, hardware, competitor or full-scale gates.
Old-plus-new replacement admission remains additive; fitting the first index at
128MiB does not guarantee a second simultaneous index fits that budget.

## Linked density extension (opcodes 10–15)

Existing v1 opcode layouts are unchanged and historical packet receipts remain
preserved. Current index/resident/peak diagnostics reflect the private storage
charged above. An earlier combined specification listed native ABI403/WASM37;
the current combined module uses native ABI405/WASM38, with no signature change
for this prefix continuation. Older v1
implementations refuse the new opcodes. Successful paint replies set u32 flags
at XYFR offset 12 to 1; older decoders reject the additional payload length.
Unknown opcode/flag combinations fail before consuming request watermarks.

Opcode 10 configures/builds a 2D passive grid list. Header arguments are active
view ID, active dimension ordinal, view count. Payload starts with active
`u64 cut_count; f64 cuts[]`, followed by 80 bytes per view:

| Offset | Field |
|---|---|
| 0, 8, 16 | u64 view ID, x dimension, y dimension |
| 24, 28 | u32 width, height |
| 32..64 | f64 x0, x1, y0, y1 |
| 64..72 | optional u8 base RGBA and selected RGBA |
| 72, 76 | u32 colors supplied (0/1), reserved=0 |

Omitted colors are resolved by Rust (base 57/135/229/255, selected
239/105/45/255). Explicit RGBA, including transparent colors, is preserved.
Hosts frame optional values; they do not choose product defaults.

Grids use finite, distinct normalized bounds and the existing count-kernel
lower-inclusive/upper-exclusive 2D semantics. Nonfinite coordinates are omitted.
Domains collapsing/nonfinite in the existing painter's f32 uniforms are refused;
full large-offset/nonlinear paint compatibility remains open. The active view
must be in the passive list and its active dimension must be one of that view's
two source dimensions. IDs are explicit, unique, nonzero u64 values. No row
correspondence is inferred from equal coordinates or arbitrary UUIDs.

The index width W is `1 + sum(width*height)` across all views, and active C is
`cut_count+1`. Storage is `4*(C+1)*W + 16*W + 16*C`: exact private u32 cumulative slabs,
unfiltered context totals, eligible-base totals (including nonfinite active
values when there is no active range), and extrema. Grid descriptors add 96
logical bytes per view; clause slots add 32 bytes each; base mask bytes and edit
snapshots are charged. Product/overflow/budget admission precedes slab
allocation. Old index, candidate index, configuration, cloned predicates/mask,
query scratch (`8*W`), paint scratch (`8*max(view cells)`), input and output all
coexist under admission. No C×canonical-row-word storage exists. No result
cache is retained, no hidden replacement-fit eviction occurs, and eviction
preserves source, predicates and source/row identity.

A∧B∧C consists of explicit base ranges (A), an optional canonical row mask (B),
and one range per edited view/dimension (C). Switching active view/dimension
retains the old range as an inactive clause and restores a matching prior active
range. Inactive/base clauses are applied while building the active index;
subsequent resolvable active-range changes read slabs only. Changing source,
base or active configuration requires a rebuild and is never a Tier C query
claim. Partial active cells still refuse by default or execute an explicitly
recorded full exact scan. Inclusive/reversed/zero-width/signed-zero semantics
are preserved. At most 64 C clauses and 64 unique base dimensions are admitted.
The active range counts toward the same 64-clause C limit. A request that would
add a 65th clause refuses with budget status before index construction or intent
publication. Previously accepted clauses, index/counts, fingerprint and accepted
revision remain unchanged; editing and switching to an existing clause remain
usable. Replacing an existing clause at the limit does not consume another slot.

Opcode 11 paints current intent, optionally with flag 1 to allow exact boundary
work. A missing index automatically rebuilds. Tier 3 means zero canonical rows
visited; tier 2 reports every visited row. Fallback bits are 1 boundary scan and
4 automatic/replacement rebuild (both may be set). Separate membership opcode
9 remains tier 2/fallback 2. Opcode 7 in linked mode clears all C clauses while
preserving A/B and rebuilding if necessary. Append advances source revision,
invalidates the index, and retains all predicates. A retained base mask excludes
new rows beyond its original bit extent until explicitly replaced or cleared;
append never invents membership. Source/schema replacement requires an explicit
new owner/epoch, never a row-position join.

Paint replies retain the standard exact selected u64 bins. They append
`XYFP; u32 version=1; u64 view_count`, then for each view a 56-byte descriptor
`u64 ID; u32 width,height; f64 x0,x1,y0,y1,maximum`, followed by exact unfiltered
`u64 totals[cells]`, derived `f32 grid[cells]`, and resolved straight-alpha
`u8 RGBA[cells*4]`. All planes are bottom-row-first to match the existing WebGL density
sampler. The shared image colormap kernel’s top-first output is lowered to
this orientation in Rust. Counts never round-trip through f32. Rust uses the existing
density colormap kernel and selected/total fractions to resolve aggregate color
and coverage; unselected context dims to 18% of base coverage; selected coverage honors the
explicit selected alpha. These grid RGBA styles are authoritative for the
aggregate plane; point-marker color/opacity is not applied a second time. The ordinary renderer
premultiplies resolved coverage once and uploads its existing RGBA texture.
There is no drilled-point-mask substitute. Output is bounded by total slab
channels (65,536) and admitted before allocation.

Opcode 12 replaces base predicates and invalidates the index. Arguments are
base range count and mask byte count. Payload contains 24 bytes per range
`u64 dimension; f64 lo,hi`, then a mask of exactly ceil(source rows/8) bytes or
zero bytes to remove it. Trailing bits must be zero. Opcode 13 begins an edit
snapshot of C, 14 cancels/restores it (invalidating the active index), and 15
commits it. A/B/source changes are not rolled back by a C edit cancel. Controls
return tier 0, and selected count is unobserved rather than an invented zero.

Linked fingerprints personalize BLAKE2s-64 with `xyfilt02`. Encoding is source
ID/epoch/source revision/absolute first/row count (five u64), then for base and C
respectively one tag byte (1/0), u64 clause count, clauses sorted by (view ID,
dimension), each `u64 ID,dimension; f64 lo,hi`, then u64 mask byte count and an eight-byte mask digest. The digest is
BLAKE2s-64 personalized `xyfmsk01` over raw mask bytes, or eight zero bytes
for no mask. Rust computes it once at base replacement with cancellation
checks; indexed queries and error replies never rehash canonical-sized masks. Base range IDs are zero. Signed zero canonicalizes to positive zero.
Active switching alone does not change the stamp of an unchanged full predicate.
`hasIntent` is true for any retained A, B or C intent, including in error and
membership replies. This is a cache identity, not a cryptographic dataset-content identity.

## Public composition and input

Python `Chart.filter_session(...).configure_density(active, views)` and Node
`chart.filterSession(...).configureDensity(active, views)` expose `paint`, base
range/mask replacement and begin/cancel/commit edit through the same packets as
`createWasmFilterSession`. See `examples/filter_tier_c.py` and
`examples/vanilla-ts/filter-linked.ts`. Browser `attachFilterDashboard(session,
bindings)` attaches existing ordinary one-scatter primary linear Cartesian ChartViews, each
with explicit source ID/epoch, view ID, dimensions/grid, active cuts and keyboard
step. It requires one compatible owner, and fails closed for source mismatches,
duplicate bindings and unsupported per-point color/nonlinear surfaces. It does not
build charts or allocate an alternative renderer/GPU ledger. Context resources
use the ordinary `_buildTrace`/density upload and trace destruction paths.

Existing range pointer capture creates, previews, replaces and commits ranges.
Unsupported box/lasso/opposite-axis tools are refused with an observable error;
Shift does not silently turn a requested box into a range. Pointer cancel/lost capture/Escape restores the same Rust edit snapshot used by
keyboard cancel. Focus a canvas: B creates an editable range over the declared
domain; Home/End choose lower/upper endpoint, arrows adjust by the authored
input step, Enter commits, Escape cancels, Delete/Backspace clears C. All finite
input endpoints remain exact; these controls explicitly allow recorded boundary
fallback, and never snap a pointer or keyboard coordinate to an index cut.
ARIA busy/live regions announce pending work, exact canonical totals, affected
view count and completion/refusal. Real screen-reader hardware qualification is
still required.

The browser serializes session mutations, suppresses obsolete paint generations,
and constructs every replacement trace before publishing any of the five.
A failed upload keeps all prior GPU records/count metadata. Context restore hides
unfiltered bootstrap paint until the authoritative planes rebuild. Out-of-band
ordinary append invalidates/hides the binding and requires a new explicit source
binding; `dashboard.append` updates the retained canonical owner through XYFC.
No old coordinate broadcast, retained sample, unfiltered pyramid or kernel reply
may overwrite bound filter density. Native concurrent cancellation uses the
existing request gate; synchronous WASM work still cannot be interrupted mid-call.

`filter_tier_c/density.bin` adds complete shared packets and an independent
full-scan/hash/paint oracle. Normal pytest, the explicit Node package test list,
Rust/WASM tests and the existing Release surfaces browser command exercise it.
Bounded build/query/paint rows in `benchmarks/test_codspeed_selection.py` run
through the existing benchmark-oracle surface. They are not CodSpeed timing or
massive-render evidence. Exact source/artifact/log/capture bindings and remaining
acceptance are recorded in the linked-product receipt.
