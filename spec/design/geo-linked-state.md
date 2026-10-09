# Explicit linked selection for retained geographic points

This specification extends the Rust retained-point and indexed-query cores in
[`geo-lod.md`](geo-lod.md) and [`geo-spatial-index.md`](geo-spatial-index.md).
It follows dossier §17, §27, §28 and §34. This is an independently reviewed bounded engine slice. The [selected-state protocol](geo-linked-state-protocol.md) now carries this
authority through canonical/indexed sessions and original rows. Frozen-export,
typed host and browser integration remain part of #50.

## State identity and explicit joins

`GeoLinkedState::new(source, namespace, layer_id, state_revision, ids, style)`
returns immutable `Arc<GeoLinkedState>` authority bound to a validated
`GeoSourceManifest`. Only Point/MultiPoint sources are accepted. Its private
contents bind explicit u64 namespace and layer ID, source generation and digest,
source row count, geometry and CRS, state revision, canonical exact-u64 selected
IDs, and `GeoSelectedStyle { fill: [u8; 4] }`.

The input cap is **10,000 IDs before deduplication**. The existing temporal
controller's canonical selection helper sorts and deduplicates them. An
over-cap input fails; it is never truncated, even if its duplicate union would
be smaller. Full-width IDs, including `u64::MAX`, remain integers throughout.
There is no source-sized flag plane, inferred join or hidden source scan.

`link_to(target, namespace, layer_id, state_revision)` explicitly copies that
sparse intent and selected-fill profile into independently validated target
source/layer authority. Coincidentally equal IDs do not coordinate layers.
The caller chooses both target and namespace. Separate coordination slots may
hold explicitly linked states; one slot cannot silently change its lineage.

`GeoLinkedStateAdmission::admit(state, operation_snapshot)` is the monotonic
admission helper for one namespace/source/layer slot. It requires matching
source generation/digest, layer and state revision. Regressing revisions or
changing lineage fails. Reusing a revision with changed canonical IDs or fill
also fails, preserving the old Arc. Equal revision and identical contents is
an unchanged admission. Fingerprints are deterministic two-u64 identity hints;
equal-revision authorization compares the full canonical contents, so a hash
collision cannot authorize changed intent. Coordinating transports must use
this helper, or enforce its identical rule, before publishing a new state.

State can persist across camera and time changes. Every consuming query still
validates its source, camera, time, layer and revision identity by the existing
query contracts. New state leaves previously published state/results immutable.

## One time-first selection fold

The legacy constructors and synchronous processors delegate with `None`:

- `GeoPointLod::new_with_state(identity, camera, time, options, state)`;
- canonical `process_with_state(..., state, cancel)`;
- `GeoIndexedQuerySession::new_with_state(..., state)`;
- indexed `process_indexed_with_state(..., state, cancel)`.

State binding is validated before allocations and I/O. Canonical and indexed
inputs use the same `GeoPointLod` vertex fold; the index does not implement a
second selection policy. Existing index authentication, source order, camera
pruning and chunk/leaf loan release remain unchanged. If the indexed bounded
frontier explicitly returns a canonical-scan fallback, the caller must pass
the **same state** into the canonical processor.

Canonical half-open time eligibility is checked before projection/work and
selection counting. Only valid, time-eligible vertices with projected centers
inside the existing viewport count as selected visible output. Null, absent,
offscreen and time-excluded IDs remain in the selection intent. A duplicate
literal ID selects the union of its source rows. Each visible selected vertex
counts once: MultiPoint rows may contribute several vertices, and duplicate
IDs do not collapse source-row provenance or exact membership.

`GeoPointResult.selection` is `None` for legacy calls or immutable
`Arc<GeoPointSelection>` for explicit state. Direct output uses sparse binary
search against the state IDs and adds no per-point flag or ID copy. Reduced
Cluster/Density output retains an exact top-row-first u64 selected-vertex
count plane, including empty cells. Explicit empty state uses no selected cell
plane. `visible_selected_vertices()` is exact, and each cell's selected count
must be at most its total count. Checked u64 addition rejects overflow. The
aggregate pass's selected total must match the first pass before publication.

The private sidecar binds the exact output key, total visible count and state.
Scene lowering validates this authority against the result. Failed admission,
fold, read, cancellation or final validation cannot publish partial state or
mutate an old result. Cancellation of an issued indexed read still requires
dropping borrowed host bytes and acknowledging release before final cleanup.

## Selected appearance

Direct selected points replace the ordinary fill with the explicit straight
RGBA8 selected fill. Ordinary opacity applies exactly once. The original
diameter, stroke, scatter symbol, full-u64 paint ID and paint order remain.

Cluster/Density preserve the existing count colormap and cluster-size policy.
Each occupied cell receives an explicit selected-fraction tint. For each RGBA
channel, Rust computes the rounded integer weighted mean:

```text
(base * (total - selected) + selected_fill * selected + total / 2) / total
```

Both colors have ordinary opacity applied before tinting. Arithmetic uses
u128 intermediates; counts and IDs never enter f32. Zero selected returns
the original color exactly, and empty cells stay transparent. The tint is an
aggregate visual representation of a fraction, not a feature color or an
individual selected feature location. Exact selected counts remain separate
authority. This slice does not implement hover/focus, brush geometry, arbitrary
per-row scalar styles or a separate selected mark overlay.

Default `None` and explicit empty state produce byte-identical legacy Scene
output, including direct, Cluster and Density cases. Scene32 and painter15
framing are unchanged; this slice adds no ABI or wire contract.

## Allocation and ownership

All new allocations use the existing **128 MiB processor ledger**; they do not
create another pool or enlarge the existing processor/384 MiB derived policy.
Sparse state reserves `input_count * 8 + sizeof(GeoLinkedState) + 128` before
the canonical ID copy/sort and Arc allocation. Its private lease survives Arc
sharing and releases after its owned data drops.

Selected LOD reserves the existing conservative base/output-transition amount,
plus at most `max_cells * 8 + sizeof(GeoPointSelection) + 256` for nonempty
state. Empty state reserves only sidecar overhead. The complete-phase helper
`reservation_bytes_with_state` also includes the already retained state's
credit when validating the caller's local phase allowance. The live shared
ledger charges that state once, rather than on each Arc clone.

The completed sidecar owns a lease covering the original base output's actual
capacities, selected-count capacity, and sidecar/Arc overhead. Thus state/counts
remain charged if a trusted semantic clone outlives the original result. The
original base-output charge may remain conservatively retained after its
vectors drop; copied base vectors still require their existing independent
semantic-clone allowance. Indexed selected sessions separately reserve their
bounded frontier and release frontier buffers before shrinking that credit.

No path allocates in proportion to whole-source row count for selection.
Lookup cost is logarithmic in at most 10,000 canonical IDs per eligible visible
vertex. Selection does not reduce the existing projected-work or query budgets.
Arbitrary isolated algorithm callers must still account for their manifests,
reader buffers and other live allocations. The new leases do not convert an
unaccounted application-owned source allocation into bounded product storage.
The claimed CPU policy concerns live product-owned allocations in the existing
module/session accounting scope; it does not cap OS RSS, GPU/DOM storage or
application input.

## Evidence and remaining integration

Focused authentic-chunk tests cover input/canonicalization bounds, full-u64
IDs, source/revision/profile admission, explicit two-source namespace joins,
null/offscreen/time-excluded intent, MultiPoint duplicate-ID vertex counts,
direct and both reduced kinds, exact native half-alpha pixels, checked integer
overflow, byte-identical empty-state Scenes, canonical/indexed Scene parity,
global-pressure admission before I/O, shared lease survival/drop recovery,
failure/cancellation preserving old output, and indexed cancellation/ACK loans.

```bash
cargo test -p xyg-engine geo_linked_state --lib
cargo test -p xyg-engine --lib
cargo clippy -p xyg-engine --all-targets --all-features -- -D warnings
cargo check -p xyg-engine --no-default-features
```

Existing recorded source benchmarks are legacy-state measurements. These
tests establish bounded engine correctness, not selected-state browser parity
or measured 100M interactive selection latency. Remaining work includes
protocol admission/publication and private retained-data cloning, exact row
selection transport, frozen state provenance/export, shared host/browser
composition and paint proofs, interaction/state event coordination, and
small/medium/large/massive selected-state performance evidence. #50 remains
open until those separate gates and its other acceptance requirements pass.
