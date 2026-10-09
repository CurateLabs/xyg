# Retained geographic point LOD (#50)

`geo_lod` is the shared Rust point processor building block. It borrows validated
retained chunks and owns time-first projection, direct-tier admission, deterministic
screen-cell aggregation and exact paged membership. The shared `geo_lod_scene`, `geo_lod_hit`, `geo_source_session`, and
`geo_scale_protocol` modules publish immutable Scene receipts, implement exact
paint-order picking and resumable membership, and enforce process memory leases.
Python, Node and the browser controller frame that same protocol. Per-row authored
state/scalar overlays and a spatial pyramid are not implemented by this retained
point profile. Frozen export, configured tile integration and full host evidence
remain separate #50 gates; see their dedicated specifications.

## Two-pass processor and source identity

`GeoPointLod::new(identity,camera,time,options)` admits bounded consumer memory
before allocation. `fold_feature` is the single policy body used by synchronous
`process` (through `GeoSourceManifest::scan_chunks`) and the resumable source
session's `fold_chunk(chunk,chunk_index,first_row,cancel)` adapter. Every input
chunk must be authenticated against its manifest before folding. Feature rows
must arrive in strictly increasing canonical source-row order each pass; duplicate
or reordered rows fail. The authentic chunk index is supplied explicitly rather
than inferred from variable chunk sizes.

Count phase evaluates the canonical signed half-open/unbounded time predicate
before reading/projecting geometry. Only valid, time-eligible vertices whose
projected centers are inside `[0,width) × [0,height)` count. The right and bottom
edges are excluded consistently in both tiers, matching density bin ownership.
Only Point/MultiPoint are accepted. Different source/camera CRS values convert
through the existing Rust Mercator helpers before `GeoViewport::project`.
Canonical f64 source planes remain unchanged. Direct records retain the literal
full-u64 feature ID, source/chunk/local-row identity and original local vertex
index; multiple vertices or repeated IDs never replace source-row provenance.

`end_pass()` returns `Finished` for direct output, or `Repeat` for a second
aggregate pass. The accumulator retains at most **32,768 direct vertices**;
when the count exceeds that ceiling it releases the direct candidate. It never
allocates an entire source mask, feature table or aggregate membership CSR.
An allocation-free `binding_key()` lets the session validate source, camera,
time, layer and revision binding before I/O and compare the final output again.
The Count phase's direct/grid fields are provisional, not a tier decision.

## Tier and screen-cell policy

The hard direct limit is 32,768 vertices. The shared `lod_plan` hysteresis factor
1.15 is used with entry budget `32768 / 1.15`: an already direct view stays
direct through 32,768, while an aggregate view enters direct at/below 28,493.
Hysteresis never enlarges the hard direct allocation ceiling. This retained-source
profile is explicit and separate from the ordinary chart's 200k/2M scatter
thresholds; hosts must not infer or substitute those thresholds here.

An aggregate pass uses `lod_plan`'s screen shape/grid and default 16 vertices
per cell target. There are two explicit output profiles:

- `Cluster`: default/hard maximum **32,768 cells**, so emitting one mark per
  occupied cell fits the corresponding Scene primitive allowance.
- `Density`: explicitly selected, maximum **196,608 cells** (the 512×384 image
  cell-count allowance). Its grid dimensions remain view-aspect dependent;
  selecting Density does not silently enlarge the cell limit.

Authors may set a smaller positive cell cap. If the shared grid exceeds it,
Rust repeatedly halves the larger axis, rounding up (width wins ties), until
it fits. `grid_capped=true` records this deterministic resolution reduction.
It is not hidden sampling or a data-dependent representative selection.

Reduced output is a CSS top-row-first full grid. Each occupied cell stores exact
u64 **vertex count** and the source-order f64 centroid of its projected vertices;
empty cells have count zero and coordinates zero. No source feature is invented
for a cell, and no centroid is asserted to be an original feature location.
The aggregate pass's visible total must equal the Count pass's total or it fails
as stale source. Authenticated chunk hashes/order remain mandatory: equal counts
alone are not an integrity certificate. Cluster diameter and density color are chosen by the shared
`geo_lod_scene` compiler, with the explicit dropped-channel telemetry documented
there. Authored per-row color/size/scalars and selected/focus overlays remain
unsupported by this retained profile.

## Exact membership and cursor provenance

`membership_page` uses `GeoSourceManifest::query_page_where`, applying time first
and the same Rust projection/cell predicate. A MultiPoint row is emitted once
per queried cell even if several vertices contribute there; it may belong to
several cells. Different source rows with duplicate literal feature IDs remain
separate members. Pages preserve canonical source order and original FeatureRef
identity, not a representative or bounded sample.

The outer cursor binds source generation/digest/count/CRS/geometry, original
layer ID, style and state revisions, the exact frozen camera bits, time predicate,
Cluster/Density profile, direct/aggregate tier, grid dimensions and cell index.
The inner source cursor additionally binds the source QuerySpec and chunk/row
position. A changed time, camera, revision, source or cell rejects an old cursor.
Only reduced cells admit cell-membership queries. Paging never allocates a
source-sized membership plane. Row-page and scan/read budgets remain the retained
source's bounded contracts, including complete chunk decode charges on resumed
pages. The caller subtracts all existing live result/Scene/request memory from
the supplied query allowance before invoking a membership operation.

`GeoCellQuery` is the allocation-free membership authority shared by synchronous
`membership_page` and resumable readers. Its constructor binds the exact source,
normalized camera, time, tier/grid/cell, style/state revisions and both cursor
layers before I/O. `matches` evaluates time and validity before accessing geometry,
uses the same projection/bin predicate and returns one boolean per source row.
Projection work is cumulative across folds in a page. Any predicate failure poisons
that tentative query; readers discard its partial page. `query_spec`,
`source_cursor`, `wrap_cursor` and `projected_vertices` expose the framing/cursor
seams without a second host or session membership policy. Source authentication
and monotonic row iteration remain the source reader/session's responsibility.

## Resources, cancellation and publication

Non-cache work has a **128 MiB total live-phase ceiling**, shared with manifest,
authenticated chunk framing/parse, output, scratch and caller-held state.
`GeoPointLod::reservation_bytes(options)` validates the options and computes the
conservative accumulator/output-transition amount without allocating. `new` uses
the same helper, and `reserved_bytes()` reports that admitted amount:
`2 × (32768 × sizeof(GeoDirectPoint) + max_cells × sizeof(GeoPointCell)) + 8 KiB`.
This is a reservation, not an additional allowance outside the source budget.
The native wrapper checks the manifest reservation before accumulator allocation;
source scan admission subtracts manifest, consumer and its fixed scratch before
reading a chunk. Resumable session admission must also reserve old active/results,
source lease and worker/native transfer copies before constructing the accumulator.
The integrated source and membership sessions reserve this amount through the
private process-wide 128 MiB processor ledger before allocation. Immutable Scene
receipts retain their own semantic authority under that ledger; derived Scene
and tile storage additionally use the 384 MiB derived pool. Arbitrary callers
of this isolated algorithm must still account for their own live allocations.

Both projection passes charge `max_projected_vertices` cumulatively (default
2,000,000; explicit maximum 2,000,000,000). Raising the bound authorizes work, not
an execution-speed claim. Source QueryBudget independently caps considered
chunks, examined rows and read bytes per pass. Membership has its own explicit
projection budget and source page/read limits. Cancellation is checked before
each folded row and projected vertex, as well as by the source reader around I/O.
Any failed fold poisons the accumulator; `end_pass`/`finish` cannot publish its
partial result. Native `process` discards its local accumulator on any read/fold
error and rechecks cancellation before returning. The caller/session commits
only after complete success and matching current source/camera/time/revisions.

`end_pass` and output moves are synchronous bounded cell-array work; the session
checks cancellation/staleness before and after those transitions. Cancellation
cannot mutate canonical source planes or a previously committed Scene.

## Bounded proof and remaining gates

`cargo test -p xyg-engine geo_lod --lib` checks actual chunk-backed direct/full-u64
and authentic multi-chunk identity, time exclusion before projection/read,
independent CRS/pixel expectations, actual 32,773-vertex MultiPoint reduction,
vertex counts and exact row-deduplicated membership pages, changed cursor bindings,
explicit density/grid-cap telemetry, work/memory/cancellation failure and poisoned
output. The 1B visible-count test exercises only tier/grid planning: projected
vertices are zero and it is expressly **not** 1B ingestion or interaction evidence.

Authenticated resumable/native/WASM transport, process memory leases, immutable
Scene lowering/picking, exact paged membership and retained public composition
are implemented by the companion modules. The actual 1k/100k/1M/10M/100M native
protocol matrix and five-view results are committed under
`spec/performance/geo-scale-2026-10-08/`, with the exact measured source patch,
environment, raw samples and reproduction commands. The 1B row case remains
planner-only. This evidence does not measure browser paint, GPU picking, or
notebook/Reflex/VS Code interaction.

Remaining gates include per-row state/scalar attachments and overlays, spatial
index/pyramids, configured tile host lifecycles, frozen export and full host
conformance. A full-source count/aggregate scan on every view is bounded work
but is not O(visible tiles) pan/zoom behavior or a massive-scale win. In the
committed contended local run, 100M first Scene took 72.09 s and pan took 45.54 s;
these are an explicit latency gap, not evidence of interactive massive-scale
performance.
