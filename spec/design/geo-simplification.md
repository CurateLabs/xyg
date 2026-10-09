# Certified geographic source-index simplification (#50)

`geo_simplify::simplify` is an independent Rust engine building block. It does
not yet change geographic catalog compilation, retained-source queries, LOD,
host packets or exports. Those integration steps remain #50 work. It must run
**before** polygon tessellation on a bounded canonical source chunk; a reduced
index cache never replaces canonical f64 coordinates (§27).

## API and identity

The function borrows a validated `GeoColumn` and frozen `GeoViewport`, accepts
`SimplifyOptions` and a cancellation callback (`true` means cancel), and returns
`SimplifiedGeo`. All six GeoArrow geometry kinds are accepted. Point and
MultiPoint vertices are retained unchanged. LineString/MultiLineString and
Polygon/MultiPolygon retain strictly increasing original global vertex indices,
feature-row indices, original part/ring and polygon indices, closure vertices,
source validity and every bit of literal u64 feature IDs. Null features retain
ID/validity and own no geometry. Compact Point coordinate indices count valid
rows, not feature rows. Empty valid parts stay empty. No IDs are synthesized.

Hidden/state flags are not inputs to this source-only module: the caller retains
those planes by original feature-row index and applies eligibility before
spatial tier selection. Simplification cannot clear, merge or rewrite state.
The result carries source metadata digest, exact camera rebuild key, tolerance,
maximum certified screen error, charged edge visits, admitted bytes and a
per-part fallback reason. Cache identity must include the tolerance as well as
source generation/digest, camera and eligibility state. Output bounds must be
recomputed from the reduced projected geometry; original source metadata and
bounds remain authoritative and unchanged.

Arcs keep the existing explicit Rust Mercator cubic sampling profile. This
module is not an arc sampler and must not simplify authored arc control/source
segments before sampling. M4 time-series reduction is not used for routes or
polygon rings.

## Error and visibility certificate

The certified tolerance is explicitly **0.5 CSS pixel** by default. Authors may
choose a finite positive smaller tolerance; values above 0.5 or nonpositive
values fail as invalid options. It is independent of DPR. Deterministic
iterative Douglas–Peucker candidates use the shared camera's f64 projection;
strict `>` comparison retains the first maximum on ties. Route endpoints remain.
Closed rings split at the first farthest source vertex from their first vertex,
reduce the two open chains, retain the original closure vertex, and require at
least three distinct corners.

Every original vertex is independently checked against the corresponding
candidate chord. The maximum Euclidean point-to-segment distance must fit the
authored tolerance. Original projected edges and candidate chords are linear:
Mercator ground edges map to lines under the flat-ground perspective camera.
Distance to a segment is convex along an original edge, so checking all original
vertices bounds its entire continuous polyline, not just a sampled subset.
This is a screen-polyline certificate, not an error bound on a geodesic or
linear latitude interpolation that the renderer does not draw.

Only geometry wholly inside the front near/far frustum and the screen rectangle
inset by the tolerance is eligible. Outside/boundary points, near-plane finite
sentinels, horizon/clip transitions, ambiguous half-world spans, source dateline
crossings and discontinuous nearest-world copies keep the original feature or
part. The usual GeoViewport clipper then handles those exact source edges.
Continuous pitched/bearing cameras are supported inside that certified region.
No simplification may manufacture or remove a clipped visibility transition.

## Polygon topology and conservative fallback

Polygon candidates are not published on error alone. Before and after reduction,
a bounded certificate checks nonzero signed area, nonzero edges, simple rings,
no nonadjacent/inter-ring crossings or touching, strict hole containment and no
nested/overlapping holes. MultiPolygon components are checked together; nested,
overlapping or touching shells fall back conservatively. Winding sign is
preserved for every ring; source vertex order is never reversed.
Every new chord is additionally tested against every original edge outside its
covered source span, including original hole boundaries and other components.
The same shortened-chord test prevents new route crossings against original
edges outside the replaced span. Existing crossings are not repaired. Numerically
uncertain orientation signs count as touching and cause fallback.

A failed topology certificate retains the **entire Polygon/MultiPolygon feature**
unchanged. Fallback is explicit: `Points`, `ProjectionBoundary`, `WorldSeam`,
`TopologyUncertified` or `TopologyWorkLimit`; ordinary unmodified/certified parts
carry `Unchanged`. Fallback error is zero because all original vertices remain.
Fallback is not a promise that unsafe/self-crossing source geometry can then be
tessellated: existing `geo_fill` admission/error handling remains mandatory.

## Resources, cancellation and atomicity

The module has a **128 MiB total non-cache phase ceiling**, including live
borrowed source coordinates/offsets/IDs/validity, source metadata, output and
simultaneously live projection/candidate/RDP scratch. The caller must reserve
other live parse/request/state memory outside the supplied remaining allowance.
Before any O(N) allocation, checked arithmetic admits
`96 * vertices + 256 * parts + 64 * features + 16 * offset_entries + 16 KiB`.
The conservative per-vertex amount includes the original index output, f64
projection, candidate indices, keep flags, iterative stack, source coordinates
and replacement/fallback overlap. Output remains index-only.

Default total edge visits are `geo_fill::MAX_FILL_WORK` (1,000,000). Allocation
and traversal of each original index, feature/projection visits, distance tests,
intersection tests and containment edges charge this limit and poll cancellation.
Polygon certification additionally uses `MAX_FILL_EDGES` (4096). If conservative
`4 * edges²` exceeds the fill work cap or remaining work allowance, the whole
polygon feature falls back before quadratic traversal. Subsequent measured work
still obeys the strict total limit; exhaustion returns `ResourceLimit` with no
published partial cache. The bounded source digest helper is polled immediately
before/after; its existing block hashing is not interruptible inside the helper.

The callback runs synchronously; native callers may read an atomic flag, while
WASM scheduling must stage bounded operations and invalidate their generation
before publication. Errors/cancellation discard the local result. Source planes
and caller state remain unchanged. Metadata digest may populate GeoColumn's
existing rebuildable metadata cache, never canonical geometry.

## Proof and remaining integration

`cargo test -p xyg-engine geo_simplify --lib` covers every-original-vertex error
for a 10,000-vertex route, sharp corners, closure, shell/hole reduction and
`tessellate` acceptance, all six geometry kinds, multipart/null/full-u64 mapping,
determinism, EPSG:3857 and zoom-24 screen error, pitched front geometry,
dateline/clip/horizon fallback, self-crossing
polygon rejection, byte admission, work exhaustion, cancellation and recovery.

The caller must consume indices through canonical source topology, preserve
style/state/identity planes, retain the original source for rebuilds and feed
reduced geometry to the same projection/clip/tessellation pipeline. Native/WASM
packed parity, actual paint/export and massive retained-source evidence are
required integration gates; these unit proofs do not close #50 or establish a
massive-scale performance claim.

## Canonical materialization

`simplify_column` calls the certified reducer and materializes only its source
indices into a validated GeoColumn consumed by the ordinary clip/tessellation
catalog. All source rows, validity and full feature IDs remain aligned; outer
polygon/multipart offsets remain unchanged and leaf offsets are rebuilt.
Its allocation-free `materialization_bytes` admission charges192B per source
vertex,128B per row,512B per offset and32768B fixed scratch, including the
simultaneous certificate, source, typed staging and canonical output. The
returned certificate reports this complete peak. Callers lease that amount
through the shared process ledger before invoking the pure Rust algorithm.
Cancellation is checked after source cloning or final validation as well as
between parts; no canceled candidate is published. Source and camera CRS must
agree; a Rust coordinator can construct the source-CRS camera through shared
viewport conversions. The certificate identifies the original source while the
derived column has rebuilt metadata.

Independent materialization tests cover actual reduction, all six geometry
schemas, null rows, holes and multipart offsets, exact selected f64 coordinates,
full-u64 IDs, unchanged source, admitted peak, and post-certificate cancellation
(including the Point clone boundary).
