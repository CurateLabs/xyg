# Shared geographic catalog compiler

`crates/xyg-engine/src/geo_layers.rs` is the Rust catalog processor for #49.
It borrows canonical `GeoColumn` data and a complete `GeoViewport`, resolves
styles and state, and returns ordinary XYGS Scene bytes plus typed identity,
visibility and density membership metadata. It does not mutate source planes.
The host protocol and application integration are described in
[geographic-layers.md](geographic-layers.md). Interaction, shell recovery and
native/WASM parity have local integration proofs linked from the
[capability matrix](geographic-capabilities.md); final review, CI and
pull-request integration remain release gates.

## Authoring and identity

A `GeoCatalog` supplies an ordered slice of `GeoLayer`, a camera, optional
legend configuration and a total byte budget. Layer IDs are unique u64 values;
feature IDs retain all source u64 bits, including annotation-shaped IDs and
u64::MAX. Scene records use the literal feature ID. The parallel
`style_owners` plane maps each resolved Scene style to its source layer index;
style zero is an unowned invisible separator. Thus `(layer_id, feature_id)`
is the pick identity even when source IDs repeat in different layers.
Repeated IDs within a layer retain source-row styles and ordered geometry;
interaction matching an ID selects the union of its matching source rows.

Each result layer retains source IDs, validity, state flags and source digest,
source-ordered visible feature indices, visible CSS bounds and optional density
CSR. Null and hidden rows emit no geometry, labels or density members. The
camera rebuild key identifies the projected cache; the original f64 geometry
is the authoritative source for every rebuild. Feature label coordinates use
the source CRS and Rust projection. Labels and legends reuse validated Scene
sidecars, preserving literal source IDs rather than synthesizing annotations.

## Catalog and style precedence

The catalog comprises points, bubbles, routes, arcs, polygons, choropleth and
screen density. Point and MultiPoint sources feed points/bubbles/density;
LineString and MultiLineString feed routes/arcs; Polygon and MultiPolygon feed
polygon/choropleth. Unsupported geometry/family pairs fail explicitly.
Points use Scatter, routes use explicit two-vertex Segment records, polygon tessellation uses explicit
three-vertex Triangle records, and density uses Image. Segment and triangle framing is explicit and requires no sentinel or
primitive separators. A transparent source-feature separator follows all fill
triangles of each source row, preserving source-over paint semantics when
adjacent rows repeat a feature ID.

For each source row, precedence is base style, scalar channel, feature patch,
selected patch, hovered patch, focused patch. Hidden state suppresses output.
State flags are 1 hidden, 2 selected, 4 hovered and 8 focused; unknown bits
fail. Opacity is resolved once into RGBA8. Fill triangles have transparent
stroke and zero stroke width; only original source edges receive authored
outline paint. Synthetic clipping boundaries and internal tessellation edges
receive no outline stroke. Layer/source order determines overlap paint order.

Bubbles require explicit finite increasing value bounds and diameter bounds;
area interpolates linearly between squared diameter endpoints. Choropleth
requires explicit finite increasing value bounds, uses the shared Rust color
kernel and accepts at most 256 RGB stops (default viridis). Values clamp to
the authored domain; valid source rows require finite values. No inferred
cross-layer domain or browser color policy is introduced.

Arcs are an explicit flat-ground Mercator cubic profile, not terrain or a
geodesic promise. Existing Rust Bezier math samples each canonical source
segment with 1–256 steps and bend in [-1,1]. Controls use local f64 offsets,
shortest wrapped world displacement and perpendicular bend; samples then
use the shared camera/frustum clipper. Default bend is 0.25 and steps are 16.
Polygon topology and source outlines reuse the shared camera cache; bounded
`geo_fill` tessellation subtracts hole intervals before generating triangles.

Point visibility is the projected center inside the viewport. Density uses
half-open pixel bins, excluding right/bottom boundary centers. Bounds describe
visible projected geometry, not symbol/stroke extents. These rules are
explicit; reduced spatial tiers and scalable screen-bound simplification
remain #50.

## Density and complete membership

Density reuses the shared Rust count, palette and linear-light mean-color
kernels. Bins are CSS top-row-first; the Rust compiler converts the existing
mathematical-y image convention once before publishing RGBA. Counts include
all visible point vertices; membership deduplicates source-row indices in each
bin. CSR offsets and source-row indices preserve every contributor rather
than a representative or bounded sample. Multipoint rows may belong to more
than one bin. Visible feature indices are source ordered.

Feature/state fill or opacity patches select alpha-weighted linear-light mean
color, with resolved opacity applied once. Otherwise the count palette uses
the base opacity. Selected/hovered/focused members also emit exact-ID Scatter
overlays. Density's aggregate Image identity is its layer ID; callers resolve
its complete bin membership through the sidecar. `dropped_channels` is 7 for
density: bit 1 diameter, bit 2 symbol, bit 4 stroke are absent from the
aggregate image. Other families report zero; state overlays preserve these
channels. Density defaults to 512×384 and admits at most 4096 cells per axis
and the existing Scene image-pixel ceiling.

## Admission and failures

Admission validates the complete camera, source-family/CRS pairing, source-row
plane lengths, every base/feature/state style, explicit scalar domains, arc
limits, text and density dimensions before variable compile allocation.
Finite style dimensions must remain finite after f32 narrowing. Labels admit
at most 128 entries and 8192 combined UTF-8 bytes; legend titles/entries retain
existing Scene individual and combined text ceilings. Font sizes use the
existing 1–1000 Scene chrome range. No partial Scene is published on failure.

The catalog admits at most 64 layers and a budget no larger than 384 MiB.
Checked peak accounting includes source planes, retained metadata, projected
scratch, density counts/color/CSR work, polygon topology/tessellation work,
text, growing Scene records/styles and encoded output. Every record/style
append checks the reserved peak and ordinary Scene ceilings before allocation.
Polygon fill additionally retains `geo_fill`'s 4096-edge, one-million-visit and
65536-triangle work bounds. Packed protocol parsing must admit its framing,
option/source copies and output envelope independently before materializing
these borrowed engine inputs.

Focused fixtures verify exact identities and label/legend SVG output,
source-order scalar/state precedence, independent hole/multipart filled area,
ordered choropleth overlap, dateline routes/holes, an independently calculated
Bezier midpoint, complete density membership and mean-color output, opacity,
source outline separation, deep-zoom coordinate separation and atomic malformed
or resource failures. They decode actual XYGS and exercise ordinary Scene
native raster and browser-painter conversion. Native/actual-WASM protocol,
GPU pick and application recovery are covered by the linked integration
fixtures; their local results do not claim the feature branch has landed.

Native raster Triangle runs now union coverage before blending each source
feature's resolved fill. Independent fixtures pin alpha 128 on a shared
internal diagonal at authored opacity 0.5, while two overlapping source rows
with the same u64 ID retain separate source-over groups and produce alpha 192.
Source-feature separators preserve that distinction. Polygon area/overlap
fixtures also sample pixels away from internal boundaries independently of
the dedicated antialias coverage tests.


## Rust interaction index

`geo_interaction::GeoPickIndex` borrows one immutable compiled result and retains
its decoded Scene. A fixed 64×64 CSS grid indexes finite marker, Segment,
Triangle and density primitives in paint order. The last painted hit wins a
point query. Exact marker tests reuse the native painter's shared symbol SDF;
brush tests use analytic circle/distance extrema, affine branch arrangements
and polygon-edge intersections, not extent-box selection or pixel sampling.
Segment picks use stroke distance; segment brushes use exact distance to the
rectangle. Triangle picks/brushes use actual tessellated topology, so hole-only
queries return no feature. Relative f64 positions precede local marker math.
Line-only symbols retain the Scene policy: an implicit 1px stroke uses the
authored stroke RGBA, without falling back to fill color. Transparent line
strokes do not hit. Hexagon clipping and pick bounds include the shared
painter distance field's 2r/√3 vertical tip. Zero-alpha paint and zero-size
separators do not hit. Density queries read
actual RGBA cell alpha and return complete source-row CSR contributors.

`GeoFeatureKey` is `(layer_id, feature_id)`. `GeoFeatureHit` returns that key
and all matching valid, nonhidden source-row indices; duplicate-ID selection
is a row union. Brush and density results follow layers/source order.
`GeoInteractionState` contains one byte-flag vector per layer and optional
focus key. Events are Hover, SelectAt, Brush, Clear, FocusStep, FocusFeature
and SelectFeature. Selection modes are Replace, Add and Toggle. Hover clears
prior hover; Clear preserves hidden bits and clears selection/hover/focus.
Focus is one key, expanded over its duplicate-ID rows; initial state picks
the first authored focused key and clears other focus flags. Invalid restored
focus/flag combinations, unknown/nonselectable IDs and malformed events fail
without changing caller state. FocusStep admits delta -1 or +1 and wraps.

Keyboard/companion order covers every valid, nonhidden source feature,
including offscreen rows, independently of the visible spatial index.
`companion()` returns the same exact keys and row unions. DOM hosts frame
events and present these returned rows; they do not infer membership or
reimplement geographic hit/state policy.

Admission ceilings are one million indexed source rows, 131072 primitives, 1048576
grid-duplication entries and 65536 unique event candidates. Density admits
four million total cells and one million total membership entries in an
interaction index. Complex marker brush work is charged before evaluation;
the event ceiling is four million bounded primitive-work units. Checked byte
admission precedes decoded Scene, sorted source-row lookup, primitive/grid
allocation and returned-state scratch. Metadata-only `GeoInteractionState::from_compiled()` normalizes authored focus
without a spatial index and admits up to two million rows; camera rebuilds
retain the same full-u64 focus key. `admission_floor()` exposes the fixed
reservation; each variable primitive append and complete grid allocation also
checks the supplied budget. A ceiling failure is `XYG_GEO_RESOURCE_LIMIT`,
with no partial state published. The retained compiled result belongs to the
caller; protocol admission also accounts for its source/options/result buffers.
