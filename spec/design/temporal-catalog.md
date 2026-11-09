# Temporal composition catalog (#46 candidate)

Status: **partial implementation; not release ready and not issue completion**.
The accepted foundations remain [temporal columns](temporal.md) and
[controller](temporal-controller.md). This candidate introduces one Rust
`temporal_scene` compiler that lowers six families onto the existing Scene
Scatter, Polyline and Rect records. It adds no renderer.

Python authoring is `xyg.temporal_chart(kind, rows, domain=(lo, hi),
timezone="UTC")`, where kind is event, interval, gantt, line, bar or scatter,
and each row is `(start_us, end_us, value_or_lane, stable_u64_id)`.
`Chart.figure().to_scene()`, SVG/PNG and offline HTML use the normal
Figure/StaticDocument/Scene/painter consumers. Node `temporalChart` returns
an ordinary Figure; browser `encodeTemporalScene` plus
`worker.temporalSceneCompile` produces the same Scene bytes. No publication
or whole-catalog qualification is implied by these declarations.

## Exactness and framing

XYTM version 1 is a 128-byte little-endian header followed immediately by
UTF-8 timezone, title, and 40-byte source rows. Header: magic at 0, u32
version/kind/row-count at 4/8/12, f64 width/height at 16/24, i64 UTC-microsecond
range-start/range-end/cursor at 32/40/48, u32 zone/title byte counts at 56/60,
u32 retained source precision at 64; 68..72 reserved; RGBA8 fill/stroke at
72/76, f64 stroke width at 80, and 88..128 reserved zero. Row: i64 start/end
at 0/8, f64 numeric value at 16, u64 identity at 24, u8 start/end validity at
32/33, six reserved zero bytes. Source units are already normalized UTC
microseconds; precision records original units, not a request to scale again.
Python rejects timestamp floats; JavaScript requires bigint. Membership uses
exact integer comparisons. Projection subtracts an i128 origin before a
float ratio. Full-width signed extremes therefore cannot overflow subtraction.
Direct-tier Scene IDs retain literal application identities; duplicate source IDs refuse.
Numeric values remain f64 through projection. The shared Scene linear fraction
halves all terms when a finite domain's span overflows, preserving distinct
positions for opposite finite extremes instead of emitting nonfinite geometry.

Range membership is half-open. Null instants omit; null interval starts/ends
are unbounded. Reversed finite intervals refuse before publishing any output.
Direct sources are copied into immutable Python tuples/Node frozen row snapshots;
dense compositions retain packed immutable source bytes as specified below.
Line timestamps must be ascending; null rows break runs. No source sort,
decimation or identity conversion occurs in a host.

Half-open sample membership is distinct from visible line support. The line
compiler retains only the valid adjacent endpoint needed at each window edge,
including an endpoint exactly at the upper bound. It clips supporting geometry
to the window using i128 timestamp differences and interpolation between bounded
projected ordinates before Scene/f32 lowering. The support retains its authored
source ID; an interpolated boundary is not a new canonical observation. Null
rows always break the run. Other instant families continue to exclude upper-
bound observations. Crossing, duplicate-time, null-gap and signed-extreme
fixtures exercise the shared native/Worker compiler and existing painter.
The [line-window correction receipt](../performance/temporal-line-window-2026-11-07/README.md)
records failing prior artifacts, complete native/Worker Scene oracles and actual
painted crossings. The combined native405/WASM38 module remains within the fixed
caps; the earlier package and threshold50 paragraphs below are historical.

Tick policy is integer microsecond ticks below 28 days and Gregorian first-of-
month ticks above it. Month indices advance through the civil calendar, not
30-day durations. UTC labels include six fractional digits. Display timezone
capability is currently **UTC only**: every other zone refuses explicitly.
DST normalization remains the canonical column-ingress contract; this compiler
does not implement an IANA database or infer local/UTC semantics.

## Budgets and presentation limits

Request/operation cap is 64 MiB. Python, Node and browser framing check the
encoded request size before copying rows; this is a transport limit, not a
host-side row/LOD decision. Rust admits rows at most four times viewport width,
viewport 160..16384 by 120..16384 CSS pixels. Admission estimates source and
Scene scratch before variable allocation; over-budget input refuses. This is
an explicit direct tier, **not dense temporal LOD**. Interval/Gantt use authored
numeric lanes and constant 8px height; temporal bars use 6px width. Uniform
RGBA8 and stroke width plus title are supported. General CSS, category labels,
legends, authored axes/annotations and style channels are not yet integrated.
Controller snapshots supply Python compile range/cursor; exports freeze the
range and cursor in the Scene axis annotation. Browser timing, brush/group
binding, cursor marks, append/update transactions, cancellation, revisioned
membership, keyboard journeys and virtualized tables remain unimplemented.

The public Python/Node constructors apply that same 128-byte header, UTF-8
zone/title and 40-byte row envelope before retaining their immutable source
snapshot. Python unsized or understated iterables are bounded incrementally;
an over-budget row is refused before copying it. This framing check does not
replace Rust's operation/Scene admission. Node's generic HTML payload framing
continues to import without native dependencies; only a temporal Figure's
existing native Scene/painter hook prepares temporal paint bytes.

## Evidence and remaining acceptance

`tests/test_temporal_catalog.py`, Node `test/temporal-catalog.test.mjs`, and
`scripts/temporal_catalog_browser_smoke.mjs` exercise public exports.
The original candidate WASM package failed the unchanged gzip cap: 793095 bytes
versus 786432 (6663 bytes over). Optimized raw bytes are1942827 versus the
requested1927168 cap (15659 bytes over); SHA256 is
`18337bf17ea649bba23e99a8f045917cf85addc05575780f55ca7cac0b1dce4d`. The earlier candidate measured792737. Actual
native/raw-WASM six-family Scene bytes match, including LF/CRLF title inputs;
that original capture claims no packaged browser-WASM pass. The first attempt also hit errno -122 under /tmp; the retry
used TMPDIR=/var/tmp. Neither failure is counted as a pass.

The subsequent wasm32-only inlining qualification retains O3, native flags,
toolchain, optimizer, exports, request/output contracts, guards and package
limits. Threshold 50 packages at 1886204 raw / 771728 Node 22 gzip6 bytes,
below the unchanged 1927168 / 786432 limits. The original failure and bytes
remain in the historical receipt; the successor evidence is
[`46-inline50`](../temporal/evidence/46-inline50/README.md). All 69 export
names/kinds are identical. Same-source ABBA profiles retain complete byte
equality for admitted 100/10k/100k operations, and the same 100k interaction
resource refusal. Samples include slower cases and concurrent VM work; they
do not establish a latency or competitor win.

The existing full foundation CI command additionally exercises all six
families through the packaged public Worker, compares each binary request
and complete Scene against native SHA256 oracles, then uses the existing
ChartView painter. It requires actual source-colored pixels and exact u64
identity metadata before disposal. This proves bounded rendering and metadata,
not a trusted pointer pick or accessible interactive temporal controller.

The new native compile symbol uses generated ABI402. All ten current shared
fixtures are regenerated with their official producers; complete ABI401
predecessors and the earlier ABI399 chain remain preserved in
[`46-abi402`](../temporal/evidence/46-abi402/README.md). Only ABI metadata
changes; all product packet bytes and cases remain identical. Historical
transition checks use the preserved bytes, and current wrong-version checks
derive from the generated ABI rather than treating 402 as permanently wrong.

Python temporal standalone HTML uses the ordinary custom-CSS breakout rejection,
bundled-JavaScript script-data escaping, escaped title and offline CSP helpers.
It rejects unsafe CSS before writing an artifact. Native static exports compile
the Scene at the resolved export width/height in both Python and Node, then
frame that same size in the ordinary StaticDocument. Export overrides do not
mutate the authored Figure or future default-size Scenes.

All #46 acceptance remains open beyond the bounded public path: screen-bounded
LOD with complete membership/provenance, full host/WASM byte oracles, shared
controller and transport-neutral channel integration, exact live picks,
frozen state versus later updates, stale/cancel/disposal transactions,
keyboard/focus/reduced-motion/live summary/table journeys, complete
customization, DST/precision integration, competitor comparisons, small through
massive/five-view resource and latency evidence, notebooks/applications/VS Code.
No 100M-row, 50FPS, cross-platform or competitor lead is asserted.

## Shared filtering/catalog ABI integration

The combined source preserves the complete filter/catalog export union under
native ABI403 and WASM37. The original402/36 candidate and its historical
fixtures remain intact; current fixtures are officially regenerated with only
ABI metadata changed. XYTM v1/XYFC v1 and existing Scene/painter contracts,
request/operation caps, runtime limits and packaging gates remain unchanged.
No issue or milestone completion follows from this integration.

## Dense opt-in composition: XYTM v2 and XYTJ v1

The continuation integrates the root direct-line clipping repair with dense
line envelopes and cooperative native/Worker scans. Evidence belongs to
`spec/performance/temporal-dense-continuation-2026-11-08/`; the original dense
and root line-window receipts remain immutable parents. This is progress on
#46/#38 and milestones 4–7, not their completion. XYTM v1 and its six-family
and eight direct-line goldens retain their bytes and semantics. Python
`dense=True`, Node `dense:true`, and browser `TemporalComposition(worker,input)`
explicitly request v2 through the same compiler and ordinary Scene painter.

V2 retains the 128-byte header and source row layout. New u32 fields at
88/92/96/100 are operation (0 Scene, 1 observation member page, 2 metadata,
3 line support page), cell index, member offset and page capacity (1..256).
Queries copy metadata source/view fingerprints into 104..112/112..120;
120..128 remains zero. Timestamps and authored IDs stay exact i64/u64. Rust
validates all rows, including culled rows, for finite values, duplicate IDs,
endpoint validity and global line ordering before any publication.

Rust chooses `columns=max(1,floor((floor(width)-89)/4))`. Event, interval,
Gantt and scatter use 16 value bands across the full source value extent
(including zero and one); line and bar use one. Cell IDs are
`column*bands+band`, scoped to the source and viewport publication: they are
aggregate IDs, never representative source IDs. Exact member pages return
literal authored IDs once per cell in source order. Canonical IDs remain
unchanged across viewport changes. No Scene serializes an N-member list.
The composition and Rust session retain an immutable packed source until
explicit disposal. This is an admitted in-memory path, not out-of-core storage.

Instant samples use exact i128 rational time cells with half-open membership.
Interval/Gantt cells include every half-open interval intersecting the time
cell in its value band; absent endpoints are unbounded. Reversed or zero
bounded intervals refuse. Occupancy is quantized to the occupied time/value
cell and does not claim literal interval outlines. Bars include zero in their
envelopes. Dense line geometry includes each incident segment between adjacent
valid vertices, clipped to each cell using exact i128 time fractions and the
same bounded projected-y interpolation as direct lines. Nulls break runs;
repeated times retain vertical segments. Out-of-window neighbors and a vertex
exactly at hi can support geometry without becoming observations. A vertex
belongs to observation membership only at its authored time in [lo,hi).
For each cell, incident authored vertices that are not observations in that
cell form the separate exact support page. Cell-left touching endpoints count
as supports; cell-right starting segments belong to the next cell. This rule
preserves both endpoint IDs for a segment crossing the whole plot, without fake
boundary observations. Envelope geometry is a summary of projected segment
coverage, including null-separated runs sharing a cell; it is not a literal
polyline joining bins. Constant envelopes have a visible two-pixel footprint.
All six families use ordinary Scene Rects plus the existing UTC ticks, styles,
title and cursor annotation. Hosts do no grouping, projection or filtering.

XYTL replies use a 64-byte little-endian header: magic at 0; u64 version at 4,
operation at 12, source FNV-1a64 at 20, view/header FNV-1a64 at 28, admitted
peak bytes at 36, source rows at 44, lattice capacity at 52. Non-line metadata
is version 2 with stride 40 at u32 offset 60: u64 cell/count/member hash and
f64 observation min/max. Line metadata is version 3 with stride 72: the same
40 bytes followed by u64 support count/hash and f64 projected y-low/y-high.
A geometry-only line cell has count=0 and zero raw min/max; support fields and
projected envelope describe its geometry. Rows increase by occupied cell.
Member/support hashes fold exact IDs in source order. Source hash covers row
bytes; view hash covers XYTM bytes 8..88. These are reproducibility and stale
checks, not authentication. Page replies put u32 total at 60 and at most 256
u64 IDs after 64; offsets beyond total return empty pages. Changed source/view
tokens refuse atomically. Metadata records the versioned LOD rule, counts,
hashes and admission; there is no silent representative-ID fallback.

Admission uses checked arithmetic before source/index/grid allocation:
`6*request_bytes + 32*N + 4096*cells + 131072 <= operation_budget <= 64MiB`.
It conservatively reserves packed sources, old and pending Rust source owners,
host framing/transfer/staging copies, unique-ID index, grid, construction
scratch and publication buffers. Caller-owned authoring objects, constructor
transients, JS/Python runtime overhead and unrelated host allocations are not
measured by this Rust operation reservation. The canonical authoring ingress
has its own unchanged request cap. Public hosts perform a header-only Rust
preview before source-bearing operation copies. At most 64Mi cell contributions
execute per operation; exhaustion refuses atomically. The 100k fixture at
900px fits; 1M at that viewport refuses the declared working set before index
allocation. CI never allocates 100M/1B rows. WASM admission also charges retained
temporal owners and co-owned graph authorities against the instance ceiling.
Graph transactions likewise reserve already-issued temporal jobs through the
ordinary graph adapter's checked external charge. Refusing graph work leaves
those jobs and the last graph publication intact; it cannot strand subsequent
zero-byte staging. A GraphSession continues to exclude new ordinary temporal
commands until that session is closed. This is per-instance logical ownership
accounting, not proof of a global process/RSS/GPU ceiling.

XYTJ v1 is a 64-byte control header plus optional XYTM bytes. Magic at 0,
u32 version=1 at 4, u32 operation at 8, reserved 12..16 zero, u64 owner at 16,
u64 revision at 24, reserved 32..64 zero. Operations: 0 open (owner/revision 0),
1 begin (full source), 2 step, 3 read/commit, 4 cancel, 5 close, 6 preview
(owner/revision 0, header/UTF prefix only). XYJR control replies are 64 bytes:
magic/version at 0/4, u64 status at 8 (0 pending, 1 ready, 2 canceled), owner
16, revision 24, phase 32 (0 validation, 1 scan, 2 ready), source row progress
40, contribution work 48, accepted revision 56. Preview returns admission at
40 and lattice capacity at 48. Owners are opaque runtime handles, not data IDs.
The registry admits at most 64 owners; revisions increase without wrap.

Each Rust step executes at most 16,384 source/cell units and checks cancellation
before every unit. Rust owns phase/index/progress and geometry. The Worker
transfers a source once, yields between steps and carries one external request
sequence through open/begin/step/read; it does not implement scan policy.
New intent or disposal cancels private work before atomic publication. Native
cancel uses an atomic watermark visible to a concurrent step before acquiring
the state lock; asynchronous Python/Node waiters yield between the same steps.
Ready is not accepted: read builds and checks output capacity, rechecks cancel,
then commits source/output together. Native size probes and short output buffers
never commit. Failure, stale replies, old waiter cancellation and source-claim
mismatch preserve the prior accepted result. A session verifies all canonical
row bytes against its accepted source; viewport and query headers may evolve.
Cancel and teardown release private ownership; close invalidates the owner,
while in-flight native references drain safely. WASM instance disposal closes
all owners. The accepted result can be reread during or after a failed newer
operation; a session retains only its latest accepted result.

Python exposes `TemporalSession`, `temporal_begin`, `temporal_viewport`,
`temporal_metadata`, `temporal_members`, `temporal_supports`, `temporal_cancel`,
`temporal_dispose`;
Node exposes the corresponding camelCase methods and TemporalSession.
Python operation `result_async` and Node `resultAsync({signal})` cancel their own
revision on waiter cancellation. Browser `TemporalComposition` exposes scene,
metadata, members, supports, viewport and acknowledged async dispose. Metadata
ownership/revision is checked before query; canonical source bytes remain private
and immutable. One source-bearing call per composition/Worker is admitted;
canceled calls retain credit until the real Worker acknowledgment drains.
Disposal waits for source release; the shared Worker remains caller-owned.
The synchronous v2 raw compiler remains a compatibility entry, driven by the
same Rust Job; normal composition methods use the cooperative owner protocol.

Still open: independent final review, brush/controller binding, cursor marks,
coordinated tables, keyboard/reduced-motion/accessibility journeys, streaming,
richer customization, 100M+ storage/residency, competitor comparisons, five-view
budgets, and the full installed-host matrix. No FPS, massive-scale victory or
competitor lead is asserted.
