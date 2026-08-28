# Canonical scene IR

Issue [#58](https://github.com/CurateLabs/xyg/issues/58) moves parity-affecting
scene and static-export decisions into `xyg-engine` in bounded vertical slices.
This document is the version contract for that migration.

## Ownership and versioning

`crates/xyg-engine/src/scene.rs` owns the canonical scene records.
`SCENE_VERSION` is 31 and is exposed as `xyg_scene_version`; hosts may
reject an unsupported scene version independently of the C `ABI_VERSION`.
Changing a record's meaning, units, ordering, bounds, or adding any newly
emitted record kind requires a scene-version bump. There is no capability
bitmap or schema negotiation in Scene v31, so additive emission is not safe.
If capability negotiation lands later, only explicitly negotiated additions
may avoid a version bump. Consumers must reject an unsupported scene version
and, once decoders land, fail closed on an unknown kind rather than guessing.
`validate_scene_batch` is the allocation-free Rust decoder used by the #59
WASM lifecycle foundation; it validates the current Scene v31 batch layout,
including the shared fixed 160-byte Cartesian header/mark widths retained
since version 4 (only the version u32 at offset 4 changes for Cartesian
scenes), bounds, reserved bytes, kinds, style references, finite coordinates,
canonical hidden-record zeroing, the optional polar XYPL sidecar after
the chrome trailer, the optional XYIM image-blit sidecar for Scene Image
records, the optional XYDS constant-dash sidecar after XYIM, and the optional
XYLC constant-linecap sidecar after XYDS rather than
duplicating offsets in TypeScript.

The IR is an in-process typed contract, not a JSON data path. Numeric arrays
cross the C ABI as bounded typed buffers and remain subject to the dossier's
§29 prohibition on JSON numbers on the browser wire.

## Version 1: built-in scatter scene and common numeric ticks

Version 1 contains a screen-space scatter scene with one record per mark:

- f64 center x/y and authored diameter;
- RGBA8 fill and stroke;
- optional validated constant CSS paint tokens, preserving authored SVG spelling;
- f64 stroke width;
- the stable built-in symbol code from the public symbol table; and
- an optional visibility byte.

Rust validates equal record counts, finite coordinates and sizes, non-negative
diameter/stroke width, and the `MAX_SCENE_MARKS` bound of 2,000,000 marks, which
mirrors the direct-render soft ceiling.
It then owns stroke-inclusive radius calculation, every built-in marker shape,
visibility, deterministic numeric formatting, and SVG fragment construction.
Unknown symbol codes fail closed to the circle shape, matching the existing
compatibility fallback.

The same schema and `xyg_scene_axis_ticks` ABI own bounded f64 tick records for
linear, base-10 log, symmetric-log, category, angular, and time/calendar axes,
plus vectorized linear, log, and symlog scale records. Each tick record carries
all positions, the labeled subset, and the canonical step. Rust applies the
existing 1/2/2.5/5/10 linear ladder and 1/2/5 log ladder, with a hard 200-tick
ceiling. Node exposes every ABI family as `axisTicks`. Python's compatibility
SVG/raster and pyplot locator paths now call `_svg.axis_ticks`, which maps each
automatic family directly to this ABI. The retired per-family Python wrappers
contained no fallback ladder; authored-value filtering, polar/secondary
placement, and rich label formatting remain compatibility presentation.
Cross-platform conformance keeps algebraic tick families bit-exact and permits
one part in 10^15 for symmetric-log values whose final inverse transform uses
the platform math library. Invalid domains and target counts fail closed at the
ABI.
Scale records own domain-to-coordinate, domain-to-pixel, and inverse-coordinate
mapping, including reversed pixel ranges, log clip/mask behavior, and symlog's
positive constant. Python's `_Scale` and Node's `scaleMap` consume the same
bounded f64 policy. Browser interaction retains its TypeScript mapping until
the direct Rust/WASM execution boundary in #59 is available.

Python calls the scatter path from `_svg._scatter_marks`; Node exposes the same record
through `scatterSceneSvg`. Python remains responsible for ingest coercion,
public validation text, channel-to-RGBA resolution, and plot layout until
those policies move in later slices. Polar (theta, r) → screen-pixel projection
is Rust-owned (ABI 131). Scene v26 / ABI 133 compiles polar `line`, `scatter`,
`area` (including step-line as line), `bar`/`column` (annular-sector PolyFill
via `polar_wedge_points`), `errorbar` (projected polylines), and `heatmap`
(lattice Rects tessellated to the same PolyFill wedges; scalar colormaps
resolve to per-cell literal styles) when hosts pass an XYPL v1 envelope into
`xyg_scene_batch_encode`. Polar density (ABI 143) tessellates occupied
`DensityBlit` cells to PolyFill wedges through the same `polar_wedge_points`
path as polar heatmap; Image+XYPL stays fail-closed. Labeled-annotation extras
still reject with `XYG_SCENE_UNSUPPORTED_POLAR`. ABI 145 admits constant
validated `marker_path` contours: hosts pack XYMP on the extras dash slot and
Rust tessellates each scatter centre to PolyFill (filled) or Polyline
(stroke-only) after pixel mapping. Encoded Scene v31 is unchanged and does
not keep XYMP. ABI 170 admits constant single-character `marker_glyph` markers:
hosts pack UTF-8 in the XYTR marker blob (`FLAG_HAS_GLYPH`) and Rust keeps XYMG
on the encoded Scene so SVG emits `<text font-family="DejaVu Sans" …>` and
raster emits `OP_TEXT`. Combined `marker_path` + `marker_glyph` and multi-character
glyphs stay fail-closed. ABI 171 admits scatter `stroke_width` without an
authored `stroke` as match-fill (mark color at the authored width). ABI 172
admits cartesian line `curve="smooth"` plus `step` as authored step expansion.
ABI 181 admits cartesian area/error_band `curve="smooth"` plus `step` as
authored band step expansion. ABI 182 admits triangle_mesh `joined_fill` as
one identity PolyFill ring from the Rust boundary walk. ABI 183 admits
constant ribbon `color2_ch` as XYGR mark-space `dir=right`. ABI 146 admits constant
validated mark `fill` linear-gradients: hosts pack XYGR on the extras dash
slot (`{space, dir, stops}` with 2–8 RGBA8 stops, axis-aligned `down|up|left|right`,
`mark` or `plot` space). Encoded Scene v31 keeps XYGR so SVG emits
`<linearGradient>` and raster emits `OP_FILL_POLY_GRAD`. Transparent stops
rewrite to the adjacent opaque hue. Per-item two-ended ribbon `color2_ch`, data-driven
`color_ch`, `var()` stops, and chart/theme CSS gradients stay fail-closed.
ABI 147 does not change Scene records; `xyg_scene_pack_product_facts` owns
flags, `step_mode`, and extra0/extra1 from packed XYPK v1 so cartesian-vs-polar
smooth and painted heatmap dispatch cannot drift. ABI 148 does not change
Scene records; `xyg_scene_pack_annotation_facts` owns wrap vs text vs arrow
vs callout vs rule/band/marker routing from packed XYAF v1. ABI 149 does not
change Scene records; `xyg_scene_pack_heatmap_facts` owns heatmap/density
XYHP kind routing from packed XYHF v1. ABI 150 does not
change Scene records; `xyg_scene_pack_scene_extras` owns XYDS/XYLC/XYMP/XYGR/XYMG
layout, concat order, omit-empty, and XYEX wrapping from packed XYSS v1 plus
framed XYPL/XYHP. ABI 151 does not
change Scene records; `xyg_scene_pack_density_grid` owns Scene density
`bin_2d` / `density_log_u8` / optional mean-color from packed columns.
ABI 152 does not change Scene records; `xyg_scene_pack_public_export` owns
XYEP layout, kind/step/annotation codes, and flag derivation from packed
XYEF v1.
ABI 153 does not change Scene records; `xyg_scene_pack_figure_chrome` owns
plot layout, chrome-style resolve, legend loc default/allowlists (empty
authored loc is fail-closed), colorbar flags/framing, XYTL tick-label
framing, and the 200-tick axis bound from packed XYCF v1. Layout errors stay
plot-layout diagnostics so the public-export predicate can remap them to
`XYG_SCENE_UNSUPPORTED_VIEWPORT`.
ABI 154 does not change Scene records; `xyg_scene_pack_trace_compile` owns
per-trace Scene compile policy from packed XYTC v1.
ABI 155 does not change Scene records; `xyg_scene_pack_trace_attach` owns
heatmap/density attach policy from packed XYTO plus XYTA v1.
ABI 156 does not change Scene records; `xyg_scene_pack_trace_rows` owns
XYPK construction, scatter-only symbol/diameter, density domain-endpoint
column rewrite, and `pack_product_facts` from packed XYTT plus XYCL v1.
ABI 157 does not change Scene records; `xyg_scene_pack_trace_sidecars` owns
legend-name gating, heatmap-vs-density plane selection, and per-trace
style/dash/marker/gradient/plane extraction from packed XYTT plus XYNM v1.
ABI 158 does not change Scene records; `xyg_scene_pack_style_sidecars` owns
XYSS dash/linecap/marker/gradient record construction from packed XYSD plus
XYAO v1.
ABI 159 does not change Scene records; `xyg_scene_splice_annotations` owns
annotation style/row splice and XYAD extract from packed product rows plus
XYSD plus XYAO v1.
ABI 160 does not change Scene records; `xyg_scene_encode_assembled` owns
assembled Scene encode from packed XYAS plus XYCC plus extras.
ABI 161 does not change Scene records; `xyg_scene_pack_figure_chrome_from_sidecars`
owns legend paints from packed XYSD and `xyg_scene_pack_scene_extras_from_sidecars`
owns XYHP wrapping from XYSD planes.
ABI 162 does not change Scene records; `xyg_scene_encode_assembled_from_sidecars`
owns XYCC packing, extras packing, and viewport/axis scalars from packed XYAS
plus XYCF plus XYSD plus polar plus XYSS.
ABI 163 does not change Scene records; `xyg_scene_encode_product` owns product-path
compile, attach, sidecar, row, annotation, style-sidecar, splice, and assembled
encode from packed XYTC plus XYTA plus XYNM plus XYCL plus XYAF plus XYCF plus
polar.
ABI 164 does not change Scene records; `xyg_scene_static_export` owns public
SVG/PNG/PDF/JPEG/WebP consumers from one encoded Scene.
ABI 165 does not change Scene records; `xyg_scene_encode_product` additionally
owns the figure-compile support probe from packed XYFS. Empty XYFS skips the
probe so stepwise ABI 163 callers keep working.
ABI 166 does not change Scene records; cartesian bar/column/histogram
`corner_radius` tessellates to PolyFill after pixel mapping through
`geom::rounded_rect_poly` (ABI 121). ABI 167 does not change Scene records;
polar bar/column/histogram `wedge_gap` insets those PolyFill wedges by a
constant pixel gap. ABI 168 does not change Scene records; polar
bar/column/histogram `corner_radius` tessellates those PolyFill wedges when
the inner radius is positive. ABI 169 does not change Scene records; polar
`curve="smooth"` plus `step` keeps authored step expansion on identity chords.
ABI 170 does not change Scene records; constant scatter `marker_glyph` is kept
as an XYMG extras sidecar so SVG/raster emit text markers. ABI 171 does not
change Scene records; width-only scatter `stroke_width` paints the mark color
at the authored width (matplotlib `edgecolors='face'`). ABI 172 does not
change Scene records; cartesian line `curve="smooth"` plus `step` keeps
authored step expansion (`step_mode` 1–3 wins over `CurveFlatten`). ABI 181
does not change Scene records; cartesian area/error_band `curve="smooth"`
plus `step` keeps authored band step expansion (`step_mode` 1–3 wins over
`BandFlatten`). ABI 182 does not change Scene records; triangle_mesh
`joined_fill` packs one identity PolyFill ring from the Rust boundary walk.
ABI 183 does not change Scene records; constant ribbon `color2_ch` packs as
XYGR mark-space `dir=right`. ABI 173
does not change Scene records; heatmap `corner_radius` tessellates cartesian
Rects to PolyFill and polar wedges when the inner radius is positive.
ABI 174 does not change Scene records; violin/box `corner_radius` tessellates
those same cartesian Rects to PolyFill. ABI 175 does not change Scene records;
violin/box `fill_opacity` / `stroke_opacity` composite through XYMS.
ABI 176 does not change Scene records; bar/column/histogram `fill_opacity` /
`stroke_opacity` composite through that same XYMS path.
ABI 177 does not change Scene records; heatmap `fill_opacity` composites through
XYMS fill alpha (lattice style fill; colormap paints already multiply by it).
ABI 178 does not change Scene records; scatter `fill_opacity` / `stroke_opacity`
composite through that same XYMS path.
ABI 179 does not change Scene records; hexbin `fill_opacity` composites through
XYMS fill alpha on HexCell PolyFills.
ABI 180 does not change Scene records; triangle_mesh `fill_opacity` / constant
stroke paint composite through that same XYMS path.
ABI 181 does not change Scene records; cartesian area/error_band
`curve="smooth"` plus `step` keeps authored band step expansion (`step_mode`
1–3 wins over `BandFlatten`).
ABI 182 does not change Scene records; triangle_mesh `joined_fill` packs one
identity PolyFill ring from the Rust boundary walk (disconnected meshes keep
per-face `TriangleFace` rows).
ABI 183 does not change Scene records; constant ribbon `color2_ch` packs as
XYGR mark-space `dir=right` (per-item two-ended paint stays fail-closed).
Per-item radius channels stay fail-closed.

## Version 3: backend-neutral core scene batch

Version 3 establishes the renderer-independent contract required before whole
static exporters or the browser Worker consume canonical scenes. One generated
`xyg_scene_batch_encode` ABI accepts bounded typed arrays and emits a stable
little-endian byte batch; it never places numeric data in JSON. The same exact
batch is accepted by `xyg_scene_svg` for a complete SVG, by
`xyg_scene_raster_commands` for the existing native raster display list, and
by `xyg_scene_browser_painter` for the exact painter-v11 byte stream. These
consumers fail closed on malformed version, widths, length, reserved fields,
kinds, styles, coordinates, or bounds. The fixed header contains `Viewport`, canonical `PlotLayout` bounds, and
two `AxisScene` records (stable u64 id, scale kind, mask policy, transformed f64
domain, and symlog constant). A bounded embedded style table (maximum 65,536
entries) makes every style reference batch-local and independently resolvable:
each 16-byte style stores fill RGBA8, stroke RGBA8, and f64 stroke width.
Each 56-byte mark record contains its kind (`ScatterScene`, `PolylineScene`
vertex, `RectScene`, or `BandScene`), visibility/clipping flag, scatter symbol, stable u64
id, u32 style-table index, four f64 screen coordinates, and scatter diameter.
Non-scatter records must set symbol and diameter to zero except that Scene v25
Band records use symbol as the versioned outline-mode descriptor below.

Rust validates finite non-negative viewport/margins, a non-empty plot region,
all scale fields, known record kinds, equal array lengths, finite input values,
and `MAX_SCENE_MARKS`. Style references must resolve inside the embedded table;
scatter symbols use the stable built-in symbol table and authored outer
diameters/stroke widths must be finite and non-negative. The canonical marker
policy shared with the version-1 SVG wrapper is:

- line-only symbols (`plus_line`, `x_line`, `horizontal_line`, `vertical_line`)
  use an implicit 1px stroke only when authored stroke width is zero; when no
  stroke paint is authored, the thin host packing seams preserve the constant
  fill paint as the stroke, while an explicitly transparent stroke stays
  transparent. The current public static-export route admits the no-authored-
  stroke case. The public bounded constant-scatter slice also admits a literal
  constant CSS stroke with a finite non-negative scalar width; an authored
  stroke with no width uses the public 1px default. Width-only match-fill and
  per-item stroke/width remain compatibility;
- path radius is `max(diameter / 2 - effective_stroke_width / 2, 0)`, with no
  hidden minimum-radius clamp;
- most symbols have path x/y extent equal to radius; diamond uses `sqrt(2) ×
  radius` on both axes, thin-diamond uses `0.6 × sqrt(2) × radius` on x and
  `sqrt(2) × radius` on y, x-line uses `0.707 × radius`, and horizontal/vertical
  line path extent is zero on its perpendicular axis; and
- clipping adds half the effective stroke width to each path-axis extent.

Both host compilers accept the exact canonical string names `circle`, `square`,
`diamond`, `triangle`, `cross`, `hexagon`, `pentagon`, `star`,
`triangle_down`, `triangle_left`, `triangle_right`, `x`, `point`, `pixel`,
`thin_diamond`, `plus_line`, `x_line`, `horizontal_line`, and `vertical_line`;
Node numeric codes remain strictly bounded to the corresponding 0–18 values.
The thin figure compilers preserve the public defaults in those records:
scatter diameter is 4px and line stroke width is 1.5px. Checked-in Python and
Node byte fixtures pin both defaults independently rather than relying on a
coincidental non-default example.

Masked/non-finite results and fully clipped
scatter or rectangle records are invisible with zeroed coordinates, enforcing
§19 before a renderer sees vertex data. Scatter clipping uses the complete
symbol-specific path extent plus half the stroke width, so a center outside the plot remains
visible when the marker overlaps it. Polyline vertices remain available outside the
plot so a backend can clip segments correctly at the canonical bounds. Python
and Node consume the same checked-in scatter/line/bar/axis byte fixture.
Raster lowering multiplies every coordinate, radius, and width by the requested
scale in f64, then requires both that product and its f32 representation to be
finite. Failure rejects the whole command stream, so NaN/Inf never reaches a
vertex buffer even for extreme finite Scene values or scales (§19).

The byte layout established by version 3 remains fixed in version 4:

| Offset | Bytes | Field |
| ---: | ---: | --- |
| 0 | 4 | ASCII `XYGS` |
| 4 | 4 | scene version u32 |
| 8 | 4 | header bytes u32 (160) |
| 12 | 4 | record bytes u32 (56) |
| 16 | 8 | record count u64 |
| 24 | 8 | style count u64 |
| 32 | 48 | viewport width/height and plot left/top/right/bottom f64 |
| 80 | 16 | x/y axis stable ids u64 |
| 96 | 16 | x/y kind u8, mask u8, six reserved zero bytes |
| 112 | 48 | x/y transformed low/high and constants f64 |
| 160 | 16 × style count | fill/stroke RGBA8 and stroke-width f64 styles |
| after styles | 56 × record count | kind/flags/symbol/style/id/four f64 coordinates/diameter |

### Fixed record semantics

All records are emitted in authored order. Record byte 3 is explicit identity
metadata: `0` is the legacy stable-ID run contract, `1..4` are bounded
annotation kinds, and `128` is literal per-row identity whose u64 value never
groups geometry or classifies annotations. `visible = 0` means all four
coordinates are zero and the consumer emits no primitive. Every record's
`style_ref` indexes the batch-local style table; out-of-range references are
invalid.

- **Scatter (kind 0):** `x0,y0` is the mapped center; `x1,y1` is reserved and
  always zero. The encoder neither finite-checks nor scale-maps the reserved
  input slots, so a log-mask policy applies only to `x0,y0`. `symbol` is the stable built-in symbol code and `diameter` is the
  authored outer diameter interpreted by the canonical marker policy above.
  Each record is an independent marker; stable ID supplies animation/picking
  identity, not grouping.
- **Polyline vertex (kind 1):** `x0,y0` is one mapped vertex; `x1,y1`, symbol,
  and diameter are zero. Reserved `x1,y1` inputs are neither finite-checked nor
  scale-mapped. Consecutive visible kind-1 records with the same stable
  ID and the same `style_ref` form one polyline in record order. A stable-ID
  change, style change, non-polyline record, or invisible vertex (including a
  log-masked `x0` or `y0`) terminates the run; a later repeated stable ID
  starts a new run and never reconnects across the break. A one-vertex run is
  valid but draws no segment.
- **Rectangle (kind 2):** coordinates are normalized screen-space
  `left,top,right,bottom` in `x0,y0,x1,y1`, independent of data order or reversed
  axes. All four input coordinates are finite-checked and scale-mapped; a
  log-masked corner hides the whole rectangle. Symbol and diameter are zero. Each record is one closed axis-aligned
  rectangle; stable ID is independent animation/picking identity.
- **Band sample (kind 3):** `x0,y0` is one top sample and `x1,y1` is the paired
  base sample (same authored x is typical for area/error bands). All four
  inputs are finite-checked and scale-mapped; a log-masked corner hides the
  sample. Diameter is zero. Scene v25 defines `symbol` as `0=None`, `1=Top`,
  or `2=Perimeter`; another value is malformed. Consecutive visible kind-3 records with
  the same stable ID, `style_ref`, and outline mode form one filled polygon: tops in record
  order, then bases in reverse order, closed. Unlike Rect, Band does not
  min/max-normalize corners — sample order is preserved so the polygon matches
  the authored series. `Top` strokes only the top samples in record order;
  `Perimeter` strokes the closed top/end/base/end polygon. Rust canonicalizes
  any requested mode to `None` when stroke width or resolved stroke alpha is
  zero, and decoders reject a noncanonical visible mode with invisible stroke.

Decoders must require the exact header/record widths for the declared version,
reject unknown kinds, and enforce the reserved-zero fields above. They must not
infer a different grouping or corner convention.

The existing `xyg_scene_scatter_svg` entry point remains a compatibility
wrapper during migration. Version 3 intentionally has no mark-specific new SVG
ABIs: whole-scene SVG/raster consumers attach to the single scene batch.
Python `Figure.to_scene()` and Node `Figure.toScene()` compile the migrated
constant-style cartesian subset plus two axes: scatter/line (with compact
`pre`/`post`/`mid` samples expanded by Rust), rect-family marks
(`bar`/`column`/`histogram`/`violin`/`box`), segment-family marks
(`segments`/`errorbar`/`stem`/`contour`/`box_whisker`/`box_median`) as
disconnected Scene Polyline runs (unique stable id per segment), and
band-family marks (`area`/`error_band`/solid `ribbon`) as Scene Band samples, and `triangle_mesh` as Scene PolyFill vertex runs. For the bounded solid-ribbon
subset, Python and Node pack two endpoint rows per ribbon and ABI 97 expands
them in Rust after axis transformation into 97 paired Band samples across 96
fixed cubic intervals. Gradient fills,
non-zero `corner_radius`, and density-tier scatter are rejected until dedicated
records exist. Their explicit Scene SVG/raster APIs exercise the Rust consumers.
Node's public `Figure` accepts an `annotations` constructor array and exposes
fluent `annotate(annotation)` authoring for the already-versioned bounded
Cartesian annotation records. Those APIs only retain authored objects; they do
not duplicate coordinate, style, resource-limit, or support-predicate policy.
For the same reason, Node exposes literal `style`, `legend`, `colorbar`,
`xAxis`, and `yAxis` constructor options plus fluent `setStyle`, `setLegend`,
`setColorbar`, and `setAxis` setters. They defensively snapshot input only;
they neither resolve CSS/defaults nor calculate gutters, ticks, legend bounds,
or colorbar geometry. `figureSceneV3` and Rust remain the sole validation and
layout authority for that already-versioned bounded contract.
`figureSceneV3` remains the Node packing seam and Rust remains the decoder,
layout, and rendering authority.
Public Python SVG/PNG/PDF route the proven literal Cartesian static contract
through Rust Scene: all 19 constant built-in scatter symbols, including bounded
constant CSS marker strokes and scalar widths; ordinary finite,
fixed-domain area/error-band Bands; constant-style
polyline (including Rust-expanded literal steps); and the ordinary Rect family
(`bar`/`column`/`histogram`); plus bounded literal disconnected endpoint pairs
for `segments`, error-bar stems/caps, and `stem` with its immediate generated
built-in constant marker; at most 1,024 finite unjoined `triangle_mesh` faces
with a constant fill and scalar overall opacity; plus finite literal solid-color
ribbons whose two-row host ingress Rust-expands after axis transformation. Each
mesh face is one three-row PolyFill group, matching the Rust browser painter's
1,024-group bound; public selection also asks that authoritative consumer to
validate the complete mixed-figure group budget before routing. Joined fills,
component alpha, authored outlines, per-face
paint/style, alternate axes, and larger meshes stay on the compatibility route.
The geometry records are
byte-identical for the shared
Python/Node line+bar, disconnected-segment, and `public_triangle_mesh_sha256`
fixtures, with separate exact cross-host fixtures for step expansion, histogram
bins, and Python
`column`/Node `bar` Rect equivalence. Newly selected line, Rect, Band,
endpoint-pair, mesh, and ribbon figures require explicit Cartesian domains on the
default axis sides
and must remain inside the bounded host-input and expanded-record budgets.
Heatmap and contour lattices carry their own cell extent, so public export
autoranges them like scatter and does not require an authored axis domain; mixed
figures that also contain literal geometry still need explicit x/y domains. For
segment-family traces, one row is
one emitted endpoint pair, so generated error-bar cap pairs count toward that
limit independently of their source observation. Chart/plot backgrounds, title, authored
axis labels/sides/major-minor ticks, the independent public
`x_axis(..., ticks=False|text=False)` and `y_axis(..., ticks=False|text=False)`
visibility switches, primary legend, literal colorbar, one bounded callout, and
its one bounded wrapped-callout companion.
`ticks=False` lowers only major tick geometry to zero and retains labels;
`text=False` lowers only tick-label/title paint to transparent and retains tick
geometry. Other public exports remain on the
established compatibility renderers until their output contract is encoded;
they must not silently select a semantically incomplete scene. Missing/nonfinite
coordinates and malformed selected literals fail closed rather than falling
back. This is a migration boundary, not a silent approximation.

ABI 95 introduced a parallel `u8 step_modes` column (`0=none`, `1=pre`,
`2=mid`, `3=post`) to the whole-Scene encoder. A nonzero mode is valid only for
one contiguous Polyline stable-id run whose style and mode are constant. Rust
requires the unused secondary endpoint columns (`x1`/`y1`) to remain zero and
rejects malformed, nonfinite, midpoint-overflowing, or over-budget expansion
before any consumer sees a Scene. Scene v25 bytes are unchanged because the
enum is an authoring ingress only. ABI 97 supersedes that parameter name with
the `expansion_modes` vocabulary below. `XYTS` v2 intentionally has no step
field and remains fail-closed.

ABI 97 generalizes the parallel authoring enum to `expansion_modes`:
`None=0`, `Pre=1`, `Mid=2`, `Post=3`, and `Ribbon=4`. A ribbon is exactly two
adjacent compact Band rows with the same stable ID, style, and outline, ordered
upper endpoint then lower endpoint. Python and Node only pack those authored
values. Rust applies the Cartesian axis transforms before evaluating the
cubics, then emits exactly 97 paired Band samples spanning
`SCENE_RIBBON_STEPS=96` intervals. It validates grouping, finite scale
projections, and the expanded-record budget before Scene encoding. The output
is ordinary Scene v25 Band geometry, so the Scene schema and its SVG, raster,
and browser-painter consumers remain unchanged. Two-ended gradients, polar
ribbons, LOD/density, and direct-browser `XYTS` authoring remain fail-closed;
broader direct-browser production is tracked by the post-M2 follow-up **Expand direct-browser aggregate production beyond the density/Scene vertical** (related to [#54](https://github.com/CurateLabs/xyg/issues/54)).

ABI 103 adds `HexCell=5` and `HeatmapLattice=6` to that same authoring enum.
A hex cell is one compact PolyFill row whose `(x0, y0)` is the cell center and
`(x1, y1)` is the finite positive `hex_dx`/`hex_dy` pitch; Rust expands it in
data space onto the canonical six-vertex pointy-top ring (`SCENE_HEXBIN_RING`)
with that cell's stable identity. A heatmap lattice is exactly two compact Rect
rows sharing the trace identity: the first carries the finite increasing extent
and `diameter=rows`, the second carries `diameter=cols` with zeroed coordinates.
Rust emits the row-major `rows×cols` Rect grid the retired host packers produced.
Scene v25 bytes are unchanged. Density, irregular grids, custom-reduce, and
over-budget cases stay on the compatibility exporters. ABI 134 adds
`HeatmapPainted=9`: the same two-row lattice plus an XYHP paint plane (RGBA8
image-top-first or scalar values + RGB stops + domain). Rust tessellates cells
and interns unique fills so Python and Node no longer expand N Rects or intern
styles in the host. Polar encode still maps those Rects to PolyFill wedges.
ABI 135 adds XYHP paint kind 2: hosts pack a colormap name (plus optional
`_r`) and Rust resolves the stop table. Custom RGB ramps still use kind 1.

ABI 104 adds `SegmentPair=7` and `TriangleFace=8` to the same authoring enum.
A disconnected endpoint pair is one compact Polyline row whose four coordinates
are the two endpoints; Rust expands it to two vertices that share a unique
stable identity so the run stays disconnected. A triangle face is exactly two
compact PolyFill rows sharing that face identity: `(x0, y0, x1, y1)` then
`(x2, y2, 0, 0)`. Rust emits the three vertices the retired host packers
produced. Scene v25 bytes are unchanged.

ABI 105 does not change Scene records. It adds the public-export support
predicate `xyg_scene_public_export_reason` so Python `scene_export_support_reason`
and Node `sceneExportSupportReason` share one Rust allowlist over packed `XYEP`
v1 metadata. ABI 107 likewise leaves Scene records unchanged and adds
`xyg_scene_resolve_mark_styles` / `xyg_css_color_rgba` so both hosts pack
`XYMS` v1 CSS literals instead of resolving fill/stroke defaults locally.
ABI 108 adds `xyg_scene_resolve_chrome_style` so both hosts pack `XYCH` v1
chrome literals instead of resolving the 200-byte default style locally.
ABI 109 adds `xyg_scene_pack_trace` so both hosts pass kind/flags/columns
and receive 56-byte Scene rows; record kinds, stable-id splitting,
expansion modes, ribbon/triangle doubling, heatmap lattice framing, and
finite-coordinate rejection cannot drift.
ABI 136 adds `xyg_scene_resolve_pack_kind` / `xyg_scene_pack_product` so
both hosts pass the authored product kind plus a canonical
`x`/`y`/`x0`/`y0`/`x1`/`y1`/`base` envelope; Rust owns the kind → pack-kind
table, heatmap painted-vs-lattice flag, and column remapping.
ABI 137 / Scene v27 adds `DensityBlit=10` and `SceneRecordKind::Image=5`.
Cartesian constant-style density scatter packs the heatmap extent lattice
plus an XYHP kind-3 log-u8 plane; Rust emits one Image record and an XYIM
RGBA sidecar. ABI 142 admits cartesian mean-color density on that same
`DensityBlit` Image path: hosts pack XYHP kind 4 (log-u8 counts plus the
row-0-bottom mean RGBA8 plane) and Rust owns LOD doc §2 physical-alpha
compositing into XYIM. ABI 143 polar density tessellates occupied cells to
Rects then PolyFill wedges (no XYIM). Custom-font/CSS exceptions stay
on the compatibility exporters. The interactive browser
painter skips Image groups; static SVG/raster/PDF consume the blit.
ABI 138 / Scene v28 admits constant dash polylines: hosts pack XYDS keyed by
host style_ref on the extras pointer (raw XYDS, or XYEX v2 when combined with
polar/paint); Rust stores dash on encoded styles and appends an XYDS sidecar
after XYIM so SVG/raster retain `stroke-dasharray`. The public-export style
allowlist includes `dash` for line, area, and polyline-like segment kinds so
`to_svg()` / `public_static_export` stay on the Scene route.
ABI 139 / Scene v29 admits constant non-round linecaps (`butt` / `square`;
`round` remains the omitted default): hosts pack XYLC keyed by host style_ref
on the same extras pointer (raw XYLC, XYDS+XYLC concat, or XYEX v2 `dash_len`
covering both); Rust stores `linecap` on encoded styles and appends XYLC after
XYDS so SVG/raster retain `stroke-linecap`. The public-export style allowlist
includes `linecap` for the same polyline-like kinds. ABI 140 / Scene v30
admits flattened `curve="smooth"` polylines: hosts pack the same compact knots
as a linear line with pack `step_mode=4`, which Rust maps to expansion
`CurveFlatten=11` and densifies through `geom::curve_flatten` (`SCENE_CURVE_STEPS=16`
samples per increasing span; `n<3` stays identity). The public-export style
allowlist includes `curve` for `KIND_LINE`. ABI 141 / Scene v31 admits flattened
cartesian `area(curve="smooth")` bands: hosts pack the same compact Band knots
with pack `step_mode=4`, which Rust maps to expansion `BandFlatten=12` and
densifies top and base through `geom::curve_flatten`. The public-export style
allowlist includes `curve` for `KIND_AREA` and `role` so Node-composed areas
match Python on the public Scene route. ABI 144 admits cartesian
`error_band(curve="smooth")` on that same `BandFlatten=12` mapping (public
allowlist includes `curve` for `KIND_ERROR_BAND`) and polar
`curve="smooth"` line/area/error_band as identity chords (polar-axes.md §5;
ABI 147 resolves `step_mode=4` from packed XYPK coords so polar smooth stays
identity). ABI 169 admits polar `curve="smooth"` plus `step` as authored
step expansion on those identity chords. ABI 170 admits constant scatter
`marker_glyph` via XYMG. ABI 171 admits width-only scatter `stroke_width` as
match-fill. ABI 172 admits cartesian line `curve="smooth"` plus `step` as
authored step expansion. ABI 181 admits cartesian area/error_band
`curve="smooth"` plus `step` as authored band step expansion.
ABI 182 admits triangle_mesh `joined_fill` as one identity PolyFill ring.
ABI 183 admits constant ribbon `color2_ch` as XYGR mark-space `dir=right`.
ABI 145 admits
constant scatter `marker_path` via an XYMP extras sidecar; Rust tessellates
centres to existing PolyFill/Polyline after pixel mapping (public allowlist
includes `marker_path` and `marker_glyph` for `KIND_SCATTER`; encoded Scene v31 is unchanged).
ABI 146 admits constant mark `fill` linear-gradients via an XYGR extras
sidecar (public allowlist already includes `fill` for area/bar/column/histogram;
encoded Scene v31 keeps XYGR). ABI 147 does not change Scene records;
`xyg_scene_pack_product_facts` owns flags, `step_mode`, and extra0/extra1 from
packed XYPK v1 so cartesian-vs-polar smooth and painted heatmap dispatch cannot
drift. ABI 148 does not change Scene records;
`xyg_scene_pack_annotation_facts` owns wrap vs text vs arrow vs callout vs
rule/band/marker routing from packed XYAF v1. ABI 149 does not change Scene
records; `xyg_scene_pack_heatmap_facts` owns heatmap/density XYHP kind routing
from packed XYHF v1.
ABI 150 does not change Scene records;
`xyg_scene_pack_scene_extras` owns XYDS/XYLC/XYMP/XYGR/XYMG layout, concat order,
omit-empty, and XYEX wrapping from packed XYSS v1 plus framed XYPL/XYHP.
ABI 151 does not change Scene records;
`xyg_scene_pack_density_grid` owns Scene density `bin_2d` / `density_log_u8`
/ optional mean-color from packed columns.
ABI 152 does not change Scene records;
`xyg_scene_pack_public_export` owns XYEP layout, kind/step/annotation codes,
and flag derivation from packed XYEF v1.
ABI 153 does not change Scene records;
`xyg_scene_pack_figure_chrome` owns plot layout, chrome-style resolve, legend
loc default/allowlists (empty authored loc is fail-closed), colorbar
flags/framing, XYTL tick-label framing, and the 200-tick axis bound from
packed XYCF v1.

ABI 154 does not change Scene records;
`xyg_scene_pack_trace_compile` owns per-trace Scene compile policy
(opacity, symbol, color, dash, linecap, marker path, diameter, legend kind,
step, curve-smooth, stroke-perimeter, hex pitch, fill-gradient admission,
and XYMS resolve) from packed XYTC v1.

ABI 155 does not change Scene records;
`xyg_scene_pack_trace_attach` owns heatmap/density attach policy
(shape/finite fail-closed checks, XYHF remainder order, density skip,
density XYHF flags, fact bits, density zeroing, and domain rewrite)
from packed XYTO plus XYTA v1.

ABI 156 does not change Scene records;
`xyg_scene_pack_trace_rows` owns XYPK construction, scatter-only
symbol/diameter, density domain-endpoint column rewrite, and
`pack_product_facts` from packed XYTT plus XYCL v1.

ABI 157 does not change Scene records;
`xyg_scene_pack_trace_sidecars` owns legend-name gating, heatmap-vs-density
plane selection, and per-trace style/dash/marker/gradient/plane extraction
from packed XYTT plus XYNM v1.

ABI 158 does not change Scene records;
`xyg_scene_pack_style_sidecars` owns XYSS dash/linecap/marker/gradient
record construction from packed XYSD plus XYAO v1.

ABI 159 does not change Scene records;
`xyg_scene_splice_annotations` owns annotation style/row splice and XYAD
extract from packed product rows plus XYSD plus XYAO v1.

ABI 160 does not change Scene records;
`xyg_scene_encode_assembled` owns assembled Scene encode from packed XYAS
plus XYCC plus extras.

ABI 161 does not change Scene records;
`xyg_scene_pack_figure_chrome_from_sidecars` owns legend paints from packed
XYSD and `xyg_scene_pack_scene_extras_from_sidecars` owns XYHP wrapping from
XYSD planes.

ABI 162 does not change Scene records;
`xyg_scene_encode_assembled_from_sidecars` owns XYCC packing, extras packing,
and viewport/axis scalars from packed XYAS plus XYCF plus XYSD plus polar plus
XYSS.

ABI 163 does not change Scene records;
`xyg_scene_encode_product` owns product-path compile, attach, sidecar, row,
annotation, style-sidecar, splice, and assembled encode from packed XYTC plus
XYTA plus XYNM plus XYCL plus XYAF plus XYCF plus polar.

ABI 110 adds `xyg_scene_pack_legend` so both hosts pass loc/flags/paints
and receive XYLG bytes; header layout, text offsets, and bounded-text
rejection cannot drift.
ABI 111 adds `xyg_scene_pack_colorbar` so both hosts pass domain/stops/ticks
and receive XYCB v2 bytes; header layout, stop/tick tables, domain-span
checks, and bounded-text rejection cannot drift.
ABI 112 adds `xyg_scene_pack_annotations` so both hosts pass typed row meta
plus concatenated labels and receive XYAD bytes; XYAT/XYAL/XYAR/XYAC/XYAW
table layout, version selection, the XYAD envelope, and bounded-text
rejection cannot drift.

## Version 4: default numeric Cartesian chrome

Version 4 keeps the version-3 byte widths but changes whole-scene rendering
semantics, so the strict contract requires a version bump. Rust now derives a
bounded default chrome layer from the two encoded axis scales in both consumers:

- linear axes use the canonical 1/2/2.5/5/10 ladder and log axes use the
  canonical 1/2/5 ladder. Symlog transforms the domain to coordinate space,
  applies the linear ladder there, inverse-maps the results, and guarantees a
  zero tick when the data domain crosses zero. Default target density is
  `max(3, floor(plot_width / 80))` for x and
  `max(3, floor(plot_height / 45))` for y, capped at 200 ticks per axis;
- grid lines render behind clipped marks, while spines, outward ticks, and
  labels render in the unclipped chrome layer;
- numeric labels use deterministic step-derived fixed/scientific formatting,
  including magnitude-derived precision for fractional log decades; and
- raster lowering checks every chrome coordinate and font size through the
  same finite f64-to-f32 gate as marks before emitting existing stroke and
  baked-font text commands.

Default paints match the established static exporter: `rgba(32,32,32,0.14)`
grid, `rgba(32,32,32,0.55)` axis, and `rgba(32,32,32,0.85)` 12px labels.
Version 4 derived default numeric chrome only. Version 5 adds authored chrome
paints and title/axis-label text in the trailer. Version 8 supersedes that
trailer with authored backgrounds, sides, and major/minor tick geometry.

## Version 5: authored chrome paints and title/axis labels

Version 5 keeps the version-4 header and mark/style byte widths. After the mark
records it appends a fixed 40-byte chrome trailer plus optional UTF-8 payloads:

| Trailer offset | Bytes | Field |
| ---: | ---: | --- |
| 0 | 4 | grid RGBA8 |
| 4 | 4 | axis/spine RGBA8 |
| 8 | 4 | label RGBA8 |
| 12 | 4 | reserved zeros |
| 16 | 8 | label font size f64 |
| 24 | 4 | title UTF-8 length u32 |
| 28 | 4 | x-label UTF-8 length u32 |
| 32 | 4 | y-label UTF-8 length u32 |
| 36 | 4 | reserved zeros |
| 40 | … | title, then x-label, then y-label UTF-8 bytes |

Default paints match the previous hard-coded chrome. Whole-scene SVG and raster
consumers paint grid/axis/labels from the trailer and place title / x-label /
y-label with deterministic margin-relative anchors. Hosts may now compile
figure titles and axis labels into the explicit Scene path; annotations,
legends, custom sides, and authored tick geometry remain rejected until later
slices. `xyg_scene_plot_layout` owns Cartesian gutters for Scene compilation.
At the version-4 boundary, the public SVG/PNG/PDF router selected these Rust
consumers only for the proven constant-style Cartesian circle-scatter subset.
Explicit Scene APIs could exercise broader migrating records, but
line/rect/band/segment/ribbon marks,
non-circle symbols, annotations, text, legends, themes/style tokens, customized
axis chrome beyond the supported literal contract, export-only backgrounds,
fluid or too-small viewports, and
screen-bounded LOD inputs remain on the compatibility renderer before
compilation. Malformed input and Rust consumer failures propagate and never
cause fallback. The public literal `ticks=False` / `text=False` switches later
ceased to be exceptions: they route through the same Rust Scene contract for
the bounded literal Cartesian static subset. `ticks=False` hides only major
tick geometry; `text=False` hides only tick-label/title paint. All other
literal chrome remains unchanged, so either switch cannot re-style the other
axis by crossing the routing boundary.

## Version 6: Band filled polygons

Version 6 keeps the version-5 header, style table, mark record width, and
chrome trailer. It adds `BandScene` (kind 3) so area and error-band hosts can
encode top/base samples without inventing a second polygon policy in Python or
Node. Whole-scene SVG emits one closed `<path>` per band run; raster emits
`OP_FILL_POLY`; the browser painter lowers bands as area geometry with a
`base` column. Version 5 consumers must reject version-6 batches.

## Version 7: PolyFill vertices and ribbon Band representation

Version 7 keeps the version-6 header, style table, mark record width, and
chrome trailer. It adds `PolyFill` (kind 4): consecutive vertices with the same
stable ID and style form one closed filled polygon (triangle-mesh hosts emit
one three-vertex run per triangle). Solid-color `ribbon` marks are represented
as Scene Band samples. ABI 97 supersedes the former host tessellation for the
bounded static subset: hosts pack two endpoint rows and Rust expands the
axis-transformed cubic into 97 samples. Two-ended gradients remain rejected
until a Scene gradient record exists. Version 6 consumers must reject
version-7 batches.

## Version 8: authored Cartesian backgrounds and axis geometry

Version 8 keeps the 160-byte header, 16-byte style table records, and 56-byte
mark records. It replaces the version-5 40-byte chrome trailer with a bounded
232-byte trailer followed by title/x-label/y-label UTF-8 and four f64 tick
lists. The first 200 bytes are also the generated C ABI's exact chrome style
input and painter-v3's exact style block:

| Trailer offset | Bytes | Field |
| ---: | ---: | --- |
| 0 | 4 | chart background RGBA8 |
| 4 | 4 | plot background RGBA8 |
| 8 | 4 | figure-title RGBA8 |
| 12 | 4 | reserved zeros |
| 16 | 8 | title/label font size f64 |
| 24 | 88 | x-axis chrome record |
| 112 | 88 | y-axis chrome record |
| 200 | 12 | title/x-label/y-label byte lengths u32 |
| 212 | 16 | x-major/x-minor/y-major/y-minor counts u32; `u32::MAX` means automatic majors |
| 228 | 4 | reserved zeros |
| 232 | … | text bytes, then the four tick lists as little-endian f64 |

Each 88-byte axis record contains side (`bottom/top` or `left/right`), two-bit
major-tick and tick-label side masks, separate major/minor direction enums
(`out`, `in`, `inout`), RGBA8 axis/grid/tick/minor-grid/minor-tick/text paints,
and seven f64 values: axis/grid/tick widths, major tick length, minor grid/tick
widths, and minor tick length. Rust rejects unknown enums, nonzero reserved
bytes, mask bits outside the two legal sides, more than 200 values per list,
more than 200 resolved major-plus-minor positions per axis, nonfinite values,
negative geometry, and geometry over 1,000px. `None`
automatic majors and an authored empty major list are distinct.

Paint order is chart background, plot background, major/minor grid, clipped
marks, then unclipped spines/ticks/text. The x and y axes independently choose
their primary spine side; major tick and label masks may mirror either side.
Minor ticks use the primary side. Explicit major positions receive labels from
Rust's deterministic formatter; explicit label strings, collision/rotation
policy, custom fonts, dashed grids, and advanced label placement remain
unsupported and fail closed at host compilation. Visibility is the existing
public resolved-style contract: zero width/length and transparent paint hide
line, tick, grid, or text independently, including `show=False` shorthands.
Rust omits fully invisible grid/axis primitives from SVG and native raster
lowering while retaining backgrounds, marks, titles, and legends. Paint alpha
is never a coordinate-system discriminator: a Cartesian Scene with hidden
chrome remains Cartesian. Polar projection and polar chrome require explicit
XYPL v1 input on `xyg_scene_batch_encode`; Scene v26 compiles polar
line/scatter/area/bar/column/errorbar/heatmap/contour plus rings, spokes, disc/sector clip, and rim tick labels.
ABI 143 polar density tessellates occupied `DensityBlit` cells to PolyFill wedges.

Python and Node mechanically pack the same 200-byte block and tick arrays;
their non-default fixture is exact-byte identical. Rust SVG and raster consume
the decoded values directly. Browser painter v4 carries the same 200 bytes in
its fixed 280-byte header, adds the three bounded authored title/axis-label
lengths, and marks every 16-byte tick descriptor as major or minor. TypeScript
validates and projects those values and texts into existing DOM/WebGL and
accessibility paint surfaces without generating tick positions, sides, or
style defaults.

Compound graph presentation follows the same one-Scene rule. Rust validates an
acyclic parent forest, computes each group's transitive descendant bounds, and
resolves collapse before encoding. Visible group bounds are ordinary `Rect`
records; visible nodes and remapped boundary edges retain their canonical
source stable IDs. Descendant nodes/labels and edges that become internal to a
collapsed representative are absent, so browser paint/pick, the `XYLB`
accessibility label plane, SVG, and native raster cannot disagree about hidden
content. Work is bounded by the direct-tier element/primitive ceilings and
malformed validity, collapse, parent, self-parent, and cycle inputs fail before
Scene output. Native ABI 89 exposes this exact compiler as
`xyg_graph_compound_scene`; Python and Node only frame typed source planes and
then feed its returned bytes to the existing browser-painter/SVG/raster seams.
All three compound planes must have exactly one value per node.

Legends, colorbars, and annotations are deliberately not part of this slice
and remain loud Scene-compile errors for later issue-#116 work. Category,
angular, time/calendar ticks, arbitrary tick-label strings, gradients, CSS
fonts, and polar chrome likewise remain explicit unsupported boundaries.

## Evidence and extension order


Rust unit tests pin schema validation and byte-deterministic SVG. Python tests
prove explicit Scene consumption; the proven public slice additionally routes
independent axis tick/text visibility through Rust while rich/customized chrome
remains on the compatibility path. Node tests consume the same scene fixture
and reject the same unsupported subset. ABI generation,
parity, and version-first loading cover both hosts.

The first browser consumer accepts the exact v8 bytes through the static WASM
Worker. Rust validates and lowers them through
`SceneDocument::to_browser_painter` into checked f32 geometry and split-u64
stable-ID columns plus authored/automatic numeric ticks and formatted UTF-8 labels.
Painter contract v4 carries fixed trace and tick descriptors, the exact chrome
style block, authored figure/axis titles, and major/minor flags with exact bounds.
Browser tick tables serialize every `AxisTicks::ticks` position (so log minor
grid lines match SVG/raster) and attach formatted labels only for
`AxisTicks::labeled`; unlabeled minor ticks carry empty UTF-8 labels.
The TypeScript adapter creates views over transferred columns and supplies the
Rust-authored ticks and labels to the existing canvas/DOM chrome surfaces. It
performs no O(record) decode/re-encode and does not reproduce mapping, grouping,
clipping, identity, tick generation, or label formatting policy.

Remaining polar marks and richer legend variants stay explicit compatibility
exceptions. Public SVG and native PNG auto-route supported figures through
Rust Scene; PDF consumes that Rust SVG. The public annotation route is the
bounded primary Cartesian family on the otherwise proven literal Cartesian
geometry slice: unoffset plain text, Rust-positioned labelled
rules/bands/markers, unlabeled straight arrows, ordinary callouts, and bounded
wrapped text/callouts. Ordinary/wrapped callouts retain literal color, opacity,
width, anchor, offsets, and literal label background/border; Rust alone
validates them and resolves leaders, label boxes, and wrapped line breaks.
Unwrapped text offsets/anchors and marker-label offsets/anchors are not Scene
fields and deliberately remain compatibility exceptions. Other annotation
combinations/kinds, themes, classes/CSS/custom fonts, nonliteral chrome,
custom marker paths/glyphs, data-driven symbol channels, unmodeled marks, and LOD remain compatibility
preflight exceptions. Literal disconnected segments, error-bar stems/caps,
and stems with their immediate generated constant built-in markers share the
selected Scene with ordinary polylines and Rects; other segment-like roles and
styles remain compatibility exceptions. `public_static_export` is the sole
optional product-route selector. Explicit Scene callers use `figure_scene`,
`figure_svg`, or `figure_raster_commands` without introducing a second support
predicate. Unlabeled cartesian annotations remain rejected rather than being
approximated as marks.

The public router has one selection seam,
``_scene_v3.public_static_export``. It consults the one support predicate,
``_scene_v3.scene_export_support_reason`` (Node: ``sceneExportSupportReason``),
which packs an ``XYEP`` v1 envelope and returns Rust's stable
``XYG_SCENE_UNSUPPORTED_*`` diagnostic (or the compiler's bounded message) for a
figure outside the migrated subset and ``None`` when the Rust Scene path
applies. Hosts do not own the allowlists or wording. ``public_static_export`` returns ``None`` only for that explicit
pre-compilation compatibility decision; every selected Scene compiler and
consumer error propagates. Figure methods and both legacy/unified Python export
entry points delegate to it rather than independently selecting a Scene consumer.
Parity with the compiler is by construction — the predicate runs
``figure_scene`` — so a router built on it can never disagree with the encoder it
guards. ``public_static_export``, ``FacetGrid.to_svg``, and
``FacetGrid._compose_rgba`` reuse that compiled
batch for SVG/PNG/PDF/JPEG/WebP consumers rather than encoding a second Scene.
The router never triggers a silent fallback: input errors (for example a
non-finite opacity) propagate rather than being reported as a routing reason.
The one non-feature routing exception is a valid viewport too small to contain
the bounded Scene chrome; it reports ``XYG_SCENE_UNSUPPORTED_VIEWPORT`` before
a batch is constructed and uses the compatibility renderer. A fluid figure
without explicit static dimensions similarly reports
``XYG_SCENE_UNSUPPORTED_FLUID_VIEWPORT``; a caller-provided width and height
permit normal Scene preflight.

The public-route evidence pins byte-identical supported SVG/PNG/PDF output to
the explicit Rust Scene consumers, repeated deterministic exports, hard
consumer failures without compatibility fallback, and the pyplot browser-CSS
compatibility exception.

## Version 9: bounded primary static legends

Version 9 keeps the fixed header, style, and mark widths from version 8 and
extends the chrome trailer from 232 to 240 bytes. Trailer offset 228 stores the
length of one optional `XYLG` legend record and offsets 232–239 are reserved
zeros. The legend follows title/axis-label UTF-8 and authored tick f64 arrays.

The host input record carries presence bits plus authored values; Rust alone
resolves the default upper-right location, 11 px text/title sizes, and default
text/frame paints. The canonical record carries that resolved nine-position
Cartesian location, optional title, bounded text/title sizes and RGBA paints,
frame fill/stroke, and 1–128 authored
entries. Each fixed 24-byte entry references the Scene style table, identifies
scatter/line/filled-swatch semantics and a built-in scatter symbol, repeats its
validated fill/stroke RGBA for zero-policy browser projection, and slices one
nonempty UTF-8 label from a canonical contiguous text table. Per-label text is
limited to 4,096 bytes and total legend text to 16,384 bytes. Rust rejects
unknown locations/kinds/symbols, unresolved or paint-mismatched style refs,
nonfinite/out-of-range sizes, NUL/invalid UTF-8, noncontiguous offsets, trailing
bytes, and every count/length overflow.

Rust owns entry order, location resolution, frame/text/swatch geometry and
paint ordering for SVG and native raster. Browser painter v12 appends the exact
validated `XYLG` record; TypeScript projects it into the existing selectable
and accessible DOM legend without deriving entries or defaults. Direct-Scene
legends are static (`toggle=false`, `highlight=false`). Python and Node only
pack the same bounded record, and exact legend bytes are pinned cross-host.

This slice supports a single primary, one-column legend for named,
constant-style Cartesian traces at an explicit supported location (defaulting
to `upper right`). Automatic `loc="best"` is resolved once by Rust occupancy
scoring (ABI 120) before packing, so Scene never sees the token `"best"`.
Python `_pack_chrome_facts` and Node `packChromeFacts` both walk traces through
`xyg_legend_normalize` / `xyg_legend_best_loc` and pack the settled location. Anchors, extra legends,
multiple columns, category rows, continuous ramps, gradients, dashes,
interactive toggles/highlight, custom content, CSS fonts, and arbitrary style
declarations fail closed.

## Version 20 bounded callout label backgrounds

Scene v20 evolved `XYAC` to v2 for an optional literal RGBA8 callout-label
background. Version 1 frames remain byte-for-byte valid; version 2 extends
each fixed callout row from 60 to 64 bytes by appending the background at
bytes 60--63. A transparent background is absence. Rust alone measures the
fixed 12px built-in label, applies the fixed 3px inset, rejects any nonfinite,
empty, or viewport-escaping rectangle, and lowers the resolved result to
`XYLB` v3. Its 84-byte records retain v2 fields, then carry a one-bit box flag,
three zero reserved bytes, f64 x/y/width/height at 48--79, and RGBA8 fill at
80--83. Records without a box have all box fields zero. SVG and raster paint
the resolved rectangle before its label; browser DOM projects the exact
geometry as an `aria-hidden` box before the `role=note` label. Borders, radius,
author padding, wrapping, collision, markup, custom fonts/CSS/classes, and
leader routing remain unsupported.

## Version 21 bounded attached-label backgrounds

Scene v21 evolved `XYAL` to v3 for an optional literal RGBA8 background on an
already-supported attached rule, band, or marker label. Each v3 row retains
the v2 stable id and label RGBA, adds the background at bytes 12--15, and moves
the UTF-8 length to bytes 16--19. A transparent fill is absence, so a mixed
batch uses v3 with transparent rows for labels without boxes. Rust alone
derives the fixed-inset built-in-font rectangle from the existing resolved
anchor and rejects a non-finite or viewport-escaping box before encoding the
existing `XYLB` v3 output. SVG, raster, and browser consume that output only.
Borders, padding, radius, wrapping, collision, custom typography, CSS/classes,
and host-resolved coordinates remain unsupported.

## Version 22 bounded text-annotation backgrounds

Scene v22 evolved `XYAT` to v2 for an optional literal RGBA8 background on a
freestanding Cartesian text annotation. Each v2 row retains its v1 Cartesian
f64 anchor and label RGBA, adds the background at bytes 20--23, and moves the
UTF-8 length to bytes 24--27. A transparent fill is absence, so a mixed batch
uses v2 with transparent rows for notes without boxes. Rust alone projects the
anchor, derives the fixed-inset built-in-font rectangle, and rejects a
non-finite or viewport-escaping box before lowering the existing `XYLB` v3
output. SVG, raster, and browser consume that output only. XYAT v1 remains
valid. Offsets, padding, borders, radius, wrapping, collision, rich markup,
custom typography, CSS/classes, and host-resolved coordinates remain
unsupported.

## Version 23 bounded label-box borders

Scene v23 adds one optional literal border to an already-supported Cartesian
label box. `XYAT` v3, `XYAL` v4, and `XYAC` v3 retain their prior fields and
append RGBA8 border paint plus a positive finite f64 width; a border requires
the existing literal label background. Rust alone derives the fixed-inset
rectangle, validates the border before allocation, and emits `XYLB` v4 with
the resolved border. SVG, raster, and browser consume those Rust-owned bounds
and paint order. Older ingress and `XYLB` v1--v3 frames remain byte-valid.
Padding, radius, wrapping, collision, markup, custom typography, CSS/classes,
and host-resolved coordinates remain unsupported.

## Version 24 bounded multiline and wrapped annotations

`XYAD` v3 adds one exact-length `XYAW` v1 section after `XYAC`.  A row carries
only Cartesian data coordinates, screen offsets, literal RGBA text/optional
box/border paint, a `label`/fixed-head `callout` kind, an anchor, a finite
nonnegative wrap width, and NUL-free literal text.  Width zero preserves only
explicit newlines; positive width uses Rust's built-in 12px metrics and ASCII
whitespace word breaking. Rust rejects blank lines, unbreakable tokens, more
than 16 resolved lines, malformed reserved bytes, and any viewport-escaping
leader or box. There is no markup, CSS/class, custom font, padding/radius,
collision policy, hyphenation, Unicode line-breaking, or browser-resolved
layout seam. Both public hosts reject each of those authored fields before the
ABI; a positive `wrap` is Rust-owned layout, not permission for host shaping.

The canonical result is `XYLB` v5: v4's fixed box/border record plus a resolved
line count. Text contains Rust-selected LF separators. SVG emits those lines as
`tspan`s, raster emits their Rust-resolved baselines, and the browser uses
`white-space: pre` plus the fixed 1.2 line height. v1--v4 label tables and
`XYAD` v1/v2 remain valid. Public Python and Node host packing now emit this
bounded v3 section; host entry points retain no wrapping or placement policy.

## ABI 96 primary numeric tick formats (Scene v25 unchanged)

ABI 96 moves the bounded primary Cartesian numeric `format` decision into
`xyg-engine` for linear, log, and symmetric-log axes. The accepted grammar is
`<prefix>(,).N[f|%]<suffix>`: an optional literal prefix, optional comma
grouping, a required decimal precision, optional `f` or percent scaling/sign,
and a literal suffix. Precision is bounded from 0 through 100, matching the
existing browser fixed-decimal ceiling; each authored format is at most 256
UTF-8 bytes and must not contain NUL. Explicit authored tick labels retain
precedence. Invalid
grammar deliberately produces the ordinary deterministic label instead of an
error, and a sub-unit log value that would collapse to formatted zero also
uses its ordinary distinguishable label without affixes.

Python and Node pack only those strings. Rust parses them, resolves the final
major positions and labels, measures their gutters, and materializes the result
as the existing explicit-major arrays plus `XYTL`; SVG, raster, and browser
painter therefore consume identical labels without a new Scene record. This is
why `SCENE_VERSION` remained 25 at ABI 96. ABI 133 extends the batch ABI by
adding one trailing `polar_input: *const u8` immediately before
`out` / `out_cap`. That pointer is null for Cartesian or else a packed
`{data: *const u8, len: usize}` view (XYPL bytes plus length) so the batch
function stays at Koffi's 64-parameter ceiling. Empty (`null` or `len==0`)
keeps the Cartesian mapping.
Polar scenes append the original 92-byte XYPL envelope after the chrome
trailer so SVG/raster/decode recover polar chrome; Cartesian trailer bytes
stay identical except the Scene version u32 at offset 4. Hosts pack authoring
only; Rust calls `polar_layout` with the finalized `PlotLayout` plot rect and
does not trust host-computed cx/cy/R. Polar encode applies `recut_polar_plot`
(ABI 126) before `polar_layout` so the inscribed disc matches compatibility
static-export gutters, including the polar legend box. Hosts still pack
legend loc/entries; Rust owns the recut and gutter placement. Remaining #275
debt is compatibility `_svg.layout()` orchestration of CSS rooms.
Optional formats still use the versioned `XYAF` v1 authoring envelope (`magic`,
version, x-format length, y-format length, legacy-annotation length, then those
exact payloads). Exact lengths are overflow-checked; malformed, trailing,
invalid UTF-8, embedded-NUL, and oversized fields fail closed. Legacy raw
`XYAD` bytes remain accepted byte-for-byte.

Polar/secondary Scene paths and broader numeric grammars remain on their
documented compatibility routes except the bounded polar
line/scatter/area/bar/column/errorbar
slice above. WASM ABI 23 plus `attachWasmTicks` cut
explicitly attached automatic, authored-value, and authored-empty primary
Cartesian linear/log/symlog/category/UTC-time ChartView
axes and eligible ChartView colorbars to that resolver; `js/src/30_ticks.ts`
stays the compatibility generator for unattached charts and the frozen
deferred polar/secondary families.

## Version 25 Band outline topology

Scene v25 gives Band record byte 2 a bounded outline descriptor: `0=None`,
`1=Top`, and `2=Perimeter`. Rust owns canonicalization, run boundaries, SVG
paths, raster display-list topology, and the browser painter descriptor. A
zero-width or transparent resolved stroke is encoded canonically as `None`;
`Top` is an open top polyline; `Perimeter` is the complete closed polygon,
including both end faces. Python and Node only resolve literal paint/default
inputs and select the authored top/perimeter request before calling the batch
encoder. Their exact ordinary Cartesian area bytes are shared fixtures.

The public static route is deliberately limited to finite equal-length
`x`/`y`/`base` columns of 2--10,000 samples on explicit primary Cartesian
domains and default axis sides. Area defaults to `Top`; error bands default to
`None`. Curves, dash, gradients, polar coordinates, missing-data breaks, LOD,
and `fill_betweenx` remain outside this increment. Ribbon expansion is a
separate ABI 97 ingress mode and does not alter the v25 outline-topology
contract. Scene v26 later admits polar area (Band) by projecting both
`(theta, r)` samples independently; polar bar/column Rects tessellate to
PolyFill annular sectors in the same version. Polar heatmap tessellates
the same way; polar contour uses SegmentPair polylines through `polar_project`.

## Version 26 polar Scene compile (ABI 133)

Scene v26 keeps the Cartesian header at **160 bytes**. Only the version u32 at
offset 4 changes (25→26) for Cartesian scenes. Polar authoring lives in a
separate **XYPL v1** envelope. Hosts pass that envelope as trailing
`polar_input: *const u8` immediately before `out` / `out_cap`. Null is
Cartesian. Non-null points at a packed `{data: *const u8, len: usize}` view
holding the 92-byte XYPL bytes (`len==0` is also Cartesian). The two logical
fields are packed as one pointer so `xyg_scene_batch_encode` stays at Koffi's
64-parameter ceiling.

XYPL v1 is exactly 92 bytes:

```
offset  size  field
0       4     magic "XYPL"
4       u32   version = 1
8       u32   theta_unit        # 0 radians, 1 degrees
12      u32   theta_direction   # 0 ccw, 1 cw
16      u32   n_categories
20      u32   r_scale_kind      # 0 linear, 1 log, 2 symlog
24      u8    grid_shape        # 0 circular, 1 linear
25      u8    r_mask_nonpositive
26      u16   pad = 0
28      f64   theta_zero        # radians ccw from East
36      f64   sector_start
44      f64   sector_end
52      f64   r_lo
60      f64   r_hi
68      f64   r_origin          # NaN means r_lo
76      f64   hole
84      f64   r_constant
```

Malformed XYPL (bad magic/version/enums/nonfinite required fields) fails at
encode time. Rust then:

1. calls `polar_layout` with the finalized `PlotLayout` plot rect (hosts must
   not supply cx/cy/R);
2. maps Scatter/Polyline/PolyFill through `polar_project` on `(x0, y0)` and
   Band through independent `(x0,y0)` / `(x1,y1)` `(theta, r)` pairs;
3. fails closed on Rect (no axis-aligned screen rects) and labeled-annotation
   extras;
4. uses `polar_position_mask` for visibility;
5. appends the original XYPL bytes after the chrome trailer **only** for polar
   scenes.

SVG clip is a circle at `(cx, cy, R)` (evenodd annulus when `hole>0`) for a
full sector, or the sector path (outer arc + inner + radii) for a partial
sector. Cartesian keeps the plot-rect clip. Polar chrome draws rings at radial
(`y`) ticks (`data-xy-grid="ring"`) and spokes at angular (`x`) ticks
(`data-xy-grid="spoke"`), plus an outer frame at `r_hi`. Linear `grid_shape`
uses polygon rings through angular ticks. Tick labels use
`polar_tick_label_layout` placement (`_POLAR_TICK_GAP=8`, quadrant anchors,
`_POLAR_RLABEL_DEG=22.5°` off the zero spoke) with Scene tick-label strings
or `xyg_tick_format`.

Eligible polar kinds: `line` (including step-line), `scatter`, `area`,
`bar`, `column`, `errorbar`, `heatmap`, and `contour`. Polar `bar`/`column` host-pack the same
`(x0,y0,x1,y1)` Rect columns as Cartesian bars; Rust tessellates
`(theta0,r0,theta1,r1)` into a PolyFill vertex run via `polar_wedge_points`
(span-proportional `polar_bar_segments`, gap=0/corner=0). Polar `errorbar`
and `contour` use existing SegmentPair polylines through `polar_project` (chords, matching
§5). Polar `heatmap` uses the same Rect→PolyFill tessellation: constant-style
lattices expand in Rust, and scalar colormaps resolve to per-cell literal
styles before encode. Scene has no image-blit record, so this is annular-sector
geometry rather than the compatibility inverse-sample `<image>`.
ABI 143 polar density uses the same occupied-cell Rect→PolyFill path
(no XYIM). `XYG_SCENE_UNSUPPORTED_POLAR` remains for other
kinds. Hidden Cartesian chrome is never inferred
as polar.

The older direct-browser `XYTS` v2 area descriptor has no outline-mode field.
To preserve its pre-v25 native Scene semantics, Rust lowers a positive-width,
nontransparent area stroke to `Perimeter` and all other strokes to canonical
`None`; TypeScript remains a framing-only host.

The combined public-host fixture is generated from
`scripts/generate_authored_scene_benchmark.py` into the legacy-named
`tests/fixtures/authored_scene_v20.json`, whose schema explicitly identifies
the v24 frame. Its declarative authoring record covers chart and plot
backgrounds, top/right Cartesian sides with deterministic major/minor ticks,
legend, literal-banded colorbar, an ordinary callout, and a wrapped callout
with literal box/border paint, plus circle and diamond scatter series. Python
generates the canonical Scene and SHA-256; the Node public `Figure` test
independently reconstructs the same authoring and requires byte identity.
`tests/fixtures/public_axis_visibility_scene.json` separately pins all eight
axis/visibility combinations (x/y × ticks/text on/off): Python and Node require
the exact Scene SHA-256, and Python feeds every record to the Rust browser
painter. Its public SVG/PNG/PDF route tests compare visible primitive counts
and native-raster pixels with the established compatibility outputs; invisible
compatibility SVG nodes are not treated as visible geometry.
The strict-CSP browser foundation page consumes only that frame through the
WASM worker and checks the resolved SVG/raster-accessible chrome. The #116
evidence job regenerates the same public workload at 100, 10k, 100k, and 1m
points from both Python and Node; it retains SHA-256 manifests plus the
SHA-keyed native/browser reports as CI artifacts. `scripts/verify_authored_scene_artifacts.py`
requires byte identity and direct Rust SVG/raster/browser-painter chrome for
every tier. The browser report additionally requires a nonblank WebGL readback
and an explicit <=1-device-pixel rounding tolerance. It also retains the
Rust-generated SVG and raster PNG for every tier, rescales the resolved Rust
plot rectangle into the browser canvas, records measured RGB-delta and
different-pixel fractions under tier-specific ceilings, and compares the
callout box in shared Scene coordinates within one device pixel. This is a
cross-renderer tolerance contract, not a pixel-identity claim: Rust raster and
WebGL have distinct compositing implementations. Custom
fonts, CSS/classes, and continuous gradients are rejected by both hosts before
they can form a Scene frame.

## Version 19 Rust-owned bounded colorbar ticks

Scene v19 evolves the optional `XYCB` colorbar decoration to v2. Its only authorable
paint is a literal, ordered table of 2–16 RGBA stops spanning a finite ordered
domain; it is always rendered as literal bands, with a bounded UTF-8 title and
the literal `right` or `bottom` side. Continuous ramps/gradients are rejected.
Hosts may supply at most 32 finite, strictly increasing in-domain major values
and a boolean minor-tick request, but never strings, formatter policy, or pixels.
Absent major values select Rust's deterministic linear ticks; Rust formats their
built-in-font labels, derives four minor positions between adjacent majors, and
emits the resolved values, labels, and screen positions in the painter `XYCT` v1
trailer. `XYCT` contains bounded major/minor record tables followed by the
major-label UTF-8 bytes: each record is a Rust-resolved f64 value, f32 screen
position, and label length (zero for minors). SVG, raster, and browser consume
exactly that result. Rust rejects
named colormaps, arbitrary CSS/fonts, axes placement, extensions, custom tick
strings, unknown flags, malformed UTF-8, unsorted values, and all size overflows
before allocation.

## Version 14 bounded authored Cartesian major labels

Scene v14 admits literal `XYTL` v1 label tables only when paired exactly with
explicit primary Cartesian major positions. Each axis table has at most 200
nonempty NUL-free UTF-8 strings and at most 4,096 total text bytes. Rust
validates the table, measures its built-in-font advances for final gutters, and
uses the same strings in SVG, native raster, and painter output. Python and
Node only forward byte-identical length-prefixed frames. Automatic ticks retain
Rust formatting. Rotation, collision/ellipsis/wrapping policies, markup, custom
fonts, and secondary/polar axis labels remain outside this slice.

## Version 15 bounded plain Cartesian text annotations

Scene v15 accepts `XYAT` v1 only as bounded host framing of Cartesian f64 data
coordinates, literal RGBA, and nonempty NUL-free UTF-8 text. Rust validates,
projects, clips, orders, and lowers the text into the canonical `XYLB` label
decoration used by SVG, raster, and browser consumers; Python and Node never
provide resolved pixels. At most 128 labels and 4,096 text bytes are accepted.
Only the fixed built-in 12px anchor is supported. Attached rule/band/marker
labels, callouts, arrows, boxes, offsets, collision, rotation, wrapping,
markup, custom fonts, and CSS remain fail-closed.

## Version 16 bounded labels attached to primary annotations

Scene v16 wraps optional `XYAT` v1 and `XYAL` v1/v2 payloads in one `XYAD` v1
decoration envelope. `XYAL` v1 carries a primary annotation stable id and
nonempty NUL-free UTF-8 text. `XYAL` v2 additionally carries one literal
RGBA8 paint resolved from the annotation's `label_color` and `label_opacity`;
it does not carry pixels, offsets, typography, CSS, or layout policy. Rust
validates that each id names exactly one supported rule,
x/y-band, or marker record run and derives the anchor deterministically: a
vertical rule anchors at its top endpoint, a horizontal rule at its right
endpoint, a band at its resolved rectangle centre, and a marker at its centre.
Labels use the fixed built-in 12px face; v1 defaults to `#667085`, while v2
uses its validated literal paint. Duplicate/unknown ids, malformed UTF-8, and
all styling beyond literal color and opacity fail closed. Callouts, arrows,
boxes, offsets, collision, rotation, wrapping, markup, custom fonts, and CSS
remain outside this slice. The `XYAT` and `XYAL` contents share one 8,192-byte
canonical text budget and a combined cap of 128 labels.

## Version 17 bounded literal Cartesian straight arrows

Scene v17 extends the `XYAD` v1 decoration envelope with an `XYAR` v1 payload.
Each of at most 128 rows contains a unique stable id, two Cartesian f64 data
endpoints, literal RGBA8 paint, opacity in `[0, 1]`, and a positive finite
stroke width. The payload is exact-length (60 bytes per row); duplicate ids,
nonfinite values, zero/too-short projected arrows, malformed frames, and ids
that collide with canonical records fail closed. Python and Node only frame
these bounded author values.

Rust projects both endpoints, derives the fixed screen-space arrowhead after
projection, applies literal alpha and clipping/paint order, and lowers the
shaft plus head into the same canonical records consumed byte-identically by
SVG, raster, and painter output. The slice has no text, label attachment,
callout placement, offsets, curved/orthogonal routes, host-resolved pixels or
head geometry, dash patterns, custom caps/joins, gradients, CSS, custom fonts,
markup, collision, rotation, wrapping, or boxes. Those forms remain loud
unsupported boundaries.

## Version 18 bounded Cartesian callouts

Scene v18 adds a Rust-owned, bounded Cartesian callout seam. `XYAD` v2 has a
24-byte header: magic `XYAD`, version `2`, then exact `u32` byte lengths for
`XYAT`, `XYAL`, `XYAR`, and `XYAC`, at offsets 8, 12, 16, and 20 respectively.
The payload order is exactly `XYAT` → `XYAL` → `XYAR` → `XYAC`; every declared
length and the final envelope length must match. `XYAD` v1 remains decodable
for existing labels and arrows, with its 20-byte header and no `XYAC` field.

`XYAC` v1 is a 12-byte header (`XYAC`, version `1`, count), followed by at
most 128 wire-order entries. Each entry is exactly 60 fixed bytes followed
immediately by its UTF-8 text: Cartesian f64 `x`, `y`, screen-space f64 `dx`,
`dy`, literal RGBA8, f64 opacity in `[0, 1]`, positive finite f64 width,
one text-anchor byte (`start=0`, `middle=1`, `end=2`), three required-zero
reserved bytes, and a u32 text length. Text is nonempty, NUL-free UTF-8 and
shares the 8,192-byte annotation-label budget. Hosts do not send a stable ID,
pixels, leader geometry, boxes, or layout decisions; Rust derives a tag-6
identity in wire order and rejects malformed, nonfinite, out-of-plot, or
too-short projected leaders before output allocation.

Rust maps the raw data anchor once, applies `dx`/`dy` in screen space, and
lowers the resulting fixed-head leader and its anchor-bearing label into
canonical Scene records. Tag `6` identifies the callout leader; the output
label travels in `XYLB` v2. `XYLB` v1 remains valid for start-anchored labels;
v2 expands each fixed record from 40 to 44 bytes with anchor byte 36, three
required-zero bytes, and the text length at byte 40. SVG, raster, and browser
consumers must use that Rust-final baseline and anchor verbatim. Callout boxes,
collision, wrapping, rich text, custom typography, CSS/classes, curves,
orthogonal routes, start/tail heads, and host-resolved geometry remain
fail-closed.

## Version 11 identity metadata for primary Cartesian annotations

Version 11 records annotation kind explicitly in byte 3 and lowers the bounded
primary annotation subset into the
existing canonical Polyline, Rect, and Scatter records. Annotation records are
always appended after data records, so Rust SVG, raster, and browser-painter
consumers share exact projection, clipping, marker geometry, style validation,
resource bounds, and paint order. Python and Node only coerce the same author
values and produce byte-identical records. Painter v11 consumes the explicit
descriptor annotation byte and projects records into the existing browser annotation layer; TypeScript
does not derive geometry or defaults. It also adds a literal, visually hidden
`role=note` description for each direct-WASM annotation. These descriptions name
the reference kind and orientation without misrepresenting Rust-projected pixel
coordinates as authored data values.

The legacy native `xyg_scene_batch_encode` ingress still derives annotation
metadata from the reserved `0x5859TT00` stable-ID prefix for compatibility;
ordinary native batch callers must not use that prefix for data identities.
The XYTS v2 direct-browser ingress has an explicit literal-identity mode and
therefore preserves every authored u64, including values inside that prefix.

The explicit Scene compiler supports the bounded primary Cartesian annotation
family: unoffset plain text, labelled axis-aligned rules/bands/built-in markers,
unlabeled straight arrows, ordinary callouts, and bounded wrapped text/callouts,
all with literal solid paint and bounded geometry. Unknown styles, classes,
dash/span overrides, coordinate-space transforms, rotation, collision policy,
and unencoded unwrapped text/marker-label offsets or anchors fail closed with a
precise migration diagnostic; a marker label never disappears silently. The
existing direct-browser smoke remains evidence only for its authored-chrome and
callout fixture, not the whole family. Existing nightly
`scene_v3_batch_encode`, SVG, raster-command, and browser-painter benchmark rows
exercise the same record paths; no per-PR CodSpeed job is added.

### Versioned authored-feature support predicate

ABI 84 adds `xyg_scene_support_reason(request_version, features, out, cap)`.
Request version 1 is a bounded u64 presence record for polar coordinates,
custom fonts, browser-only CSS/classes, gradients, colorbars, extra legends,
authored tick-label strings, labeled annotations, and callout/arrow behavior.
Rust owns both the ordered support decision and the stable actionable UTF-8
diagnostic (`XYG_SCENE_UNSUPPORTED_*`); Python and Node only project literal
feature-presence bits and relay the returned text. Zero required bytes means
the request uses none of those deferred features. Unknown request versions or
bits fail closed rather than being treated as supported. This predicate does
not make a partial Scene: callers must reject the authoring request before
encoding any records.

Both bindings validate request version 1 and the u64 feature mask before FFI
coercion: booleans, strings, fractions, negatives, unsafe JavaScript numbers,
and values outside the matching integer width are host errors rather than
wrapped native values. Their figure compilers project the same normalized authoring
representations—Cartesian versus polar coordinates, kebab/camel font keys,
root/chrome/annotation CSS classes, object-valued fills and per-item two-ended ribbon
paint—before any older host-local unsupported branch can run. Cross-host tests
pin the identical Rust diagnostic for each representable case.
## Version 12 bounded semantic graph labels

The chrome trailer uses bytes 232–235 for an appended label-block length and
keeps bytes 236–239 reserved zero. A nonempty `XYLB` block contains at most
128 records and 8,192 total UTF-8 bytes. v1 uses 40-byte records with the
final screen-space x/y baseline, font size, literal RGBA, source u64 identity,
and text length. v2 uses 44-byte records, inserting a text-anchor byte at 36
(`start=0`, `middle=1`, `end=2`) plus three required-zero bytes before the
text length at 40. The text table is contiguous and exact. Rust rejects
nonfinite or out-of-viewport geometry, invalid UTF-8/NUL, empty text,
count/byte overflow, invalid anchors/reserved bytes, and trailing data before
any consumer allocation.

For `XYGG` v3 direct semantic graphs, Rust alone resolves compound visibility,
then ranks state and stable source
identity, omits aggregate/filtered labels, truncates to the 32-character and
remaining-plot-width bound, and greedily accepts nonoverlapping boxes. SVG,
native raster, and browser painter v11 consume those final records verbatim.
The browser may expose the text as accessible DOM, but cannot reposition,
retruncate, or rerun collision policy. Aggregate LOD continues to omit all
source-indexed labels.

Authored solid chart/plot backgrounds, axis sides, and major/minor tick
geometry/styles are Scene v8.
The `xyg_scene_axis_ticks` ABI supports category, angular, time/calendar, and
symmetric-log ladders as kinds 2–6 (`aux` is the positive symlog linear-region
constant for kind 6). Node routes those families through the ABI; Python's
`_svg.axis_ticks` maps all six automatic families directly to it. Scene v5
carries authored chrome
paints plus title/axis-label UTF-8; ABI `xyg_scene_plot_layout` owns Cartesian
gutters, including the selected literal-colorbar outer lane, for Scene compilation. Cartesian rect-family hosts
(`bar`, `column`, `histogram`, `violin`, `box`) share Scene Rect records;
segment-family hosts (`segments`, `errorbar`, `stem`, `contour`,
`box_whisker`, `box_median`) and Rust-expanded stepped lines share Scene
Polyline records;
band-family hosts (`area`, `error_band`, solid `ribbon`) share Scene Band
records. ABI 97 makes Rust the sole owner of solid-ribbon cubic expansion:
native hosts supply the two compact endpoint rows, and Rust transforms then
emits the fixed 96-interval Band sequence. `triangle_mesh` shares Scene PolyFill
records. Browser DOM measurement and
WebGL paint remain environment-specific consumers with documented layout
tolerances (§7 and §21).

Exact composition ECDF canonical values and cumulative mass are resolved by
the existing `xyg_weighted_ecdf` Rust kernel in Python and Node: total-order
sorting, duplicate coalescing, and normalization are not host policy. Python
passes raw f64 values and Rust filters nonfinite observations; Node retains its
equivalent coercion/validation seam. Hosts prepend the literal `(first, 0)` anchor and submit the
result as an ordinary `post` Step, whose expansion and all three consumers are
already Rust-owned. Exact mode does not change in ABI 100.

ABI 100 makes binned composition ECDF ingress Rust-owned without changing
Scene 25. `xyg_binned_ecdf` accepts a nonempty raw f64 source column, a bin
count in `[1, 10000]`, and either automatic bounds or one finite strictly
increasing authored range. Hosts allocate exactly `bins + 1` values for each
output plane. Rust filters nonfinite samples, rejects an all-nonfinite or
nonrepresentable domain, widens a constant nonzero automatic domain by 5% of
its absolute value (falling back to plus/minus 0.5 at zero or for a non-useful pad),
includes the exact upper bound in the last bin, normalizes over every finite
source sample, omits empty bins, and emits `(lo, 0)` followed by occupied-bin
right edges. Thus automatic-range output ends at one; an authored range can end
below one or at the anchor when every finite sample is outside it. Invalid
metadata, short capacity, overlapping output planes, overflow, and over-budget requests return
`size_t::MAX` without writing either output plane. Python exposes no new range
option; Node preserves its existing optional authored range. Both submit the
result as the existing `post` Step. The authored-column preflight remains
10,000 for ordinary traces but admits 10,001 points only for compact Step lines
(the ABI100 anchor plus 10,000 occupied bins); 10,002 still fails closed, and
canonical Scene expansion budgets remain independent.

Omitted-bin composition histograms in Python and Node resolve their uniform
edges with the existing synchronous Rust `xyg_histogram_edges` auto estimator.
ABI 101 `xyg_histogram_bins` then owns counting, density, and cumulative
assembly for those edges and for finite strictly increasing authored edges.
Explicit positive integer bins and the empty/all-nonfinite ten-bin compatibility
case are unchanged. Uniform edges reuse the closed-last-bin uniform counter;
irregular edges use NumPy's array-bin assignment. Rust rejects automatic or
authored results above 10,000 bins before writing counts; each binding uses one
fixed 10,001-edge bounded scratch plane for the existing ABI 98 write call.
Density with zero in-range mass fails closed so hosts never receive non-finite
heights. The compact result remains ordinary Histogram Rects. No Scene version
change.

ABI 102 makes composition hexbin ingress Rust-owned without changing Scene 25.
`xyg_hexbin` / `xyg_hexbin_ingress` accept raw f64 x/y (optional C), a grid
width in `2..=2048`, optional height (`0` = matplotlib `int(width / √3)`,
floored at 2), and either automatic bounds or one finite strictly increasing
authored rectangle. Rust filters nonfinite pairs, rejects an all-nonfinite
source, widens a constant nonzero automatic domain by 5% of its absolute value
(falling back to plus/minus 0.5 at zero or for a non-useful pad), and bins
the same lattice both hosts already consumed. Invalid metadata, missing finite
pairs, or short capacity return `size_t::MAX` without a partial honeycomb.
Hosts keep coercion, `mincnt` defaults, log-color post-processing, and custom
Python reducers over Rust-resolved membership. The compact wire result remains
the existing centers-only hexbin trace. Constant-style Cartesian native
count/mean/sum lattices expand those centers plus `hex_dx`/`hex_dy` onto
existing Scene v25 PolyFill records (one 6-vertex `SCENE_HEXBIN_RING` group per
cell). ABI 103 makes that ring expansion and regular heatmap lattice
reconstruction Rust-owned compact authoring (`HexCell=5`, `HeatmapLattice=6`)
for `public_static_export`. ABI 104 adds `SegmentPair=7` and `TriangleFace=8`
so disconnected endpoint pairs and unjoined triangle faces use the same
compact expansion. ABI 105 adds `xyg_scene_public_export_reason` over a packed
`XYEP` v1 envelope: hosts frame literal viewport flags, chrome/legend/colorbar
keys, axis facts, annotation field names, and compact per-trace facts, while
Rust owns the public-subset allowlists, check order, and
`XYG_SCENE_UNSUPPORTED_*` wording. ABI 152 packs that envelope from `XYEF` v1
so kind/step/annotation codes and flag derivation cannot drift. ABI 153 packs
figure chrome from `XYCF` v1 so plot layout, chrome-style resolve, legend loc
default/allowlists (empty authored loc is fail-closed), colorbar flags/framing,
XYTL ticks, and the 200-tick axis bound cannot drift. ABI 154 packs
per-trace compile policy from `XYTC` v1 so opacity, symbol, color, dash,
linecap, marker path, diameter, legend kind, step, curve-smooth,
stroke-perimeter, hex pitch, fill-gradient admission, and XYMS resolve
cannot drift. ABI 155 packs heatmap/density attach policy from `XYTA` v1
so shape/finite fail-closed checks, XYHF remainder order, density skip,
density XYHF flags, fact bits, density zeroing, and domain rewrite cannot
drift. ABI 156 packs product rows from `XYCL` v1 so XYPK construction,
scatter-only symbol/diameter, density rewrite, and `pack_product_facts`
cannot drift. ABI 157 packs trace sidecars from `XYNM` v1 so legend-name
gating, heatmap-vs-density plane selection, and style/dash/marker/gradient
extraction cannot drift. ABI 158 packs XYSS from `XYSD` plus `XYAO` so
dash/linecap/marker/gradient records cannot drift. ABI 159 packs `XYAS`
from product rows plus `XYSD` plus `XYAO` so annotation style/row splice
and XYAD extract cannot drift. ABI 160 packs assembled Scene encode from
`XYAS` plus `XYCC` plus extras so XYAS/XYCC unpack, gutter widening, and
batch encode cannot drift. ABI 161 packs chrome legend paints and extras
XYHP wrapping from `XYSD` so sidecar unpack cannot drift. ABI 162 packs
assembled Scene encode from `XYAS` plus `XYCF` plus `XYSD` plus polar plus
`XYSS` so chrome/extras packing and viewport/axis scalars cannot drift.
ABI 163 packs product-path Scene encode from `XYTC` plus `XYTA` plus `XYNM`
plus `XYCL` plus `XYAF` plus `XYCF` plus polar so compile/attach/sidecar/row/
annotation/style/splice/encode orchestration cannot drift. ABI 165 additionally
packs `XYFS` on that same product call so figure-compile support cannot drift
either; empty `XYFS` skips the probe. An empty reason selects the Scene route;
hosts still compile the Scene and may still report compiler or viewport
diagnostics. Rust owns the public PolyFill group budget, including companion
traces that share the browser painter's 1,024-group ceiling; hosts do not
count meshes or probe the painter. Python
`public_static_export`, `FacetGrid.to_svg`, and `FacetGrid._compose_rgba`
reuse that compiled batch rather than encoding twice. ABI 164 owns the
SVG/PNG/PDF/JPEG/WebP consumers from that batch. ABI 106 does not
change Scene records; `xyg_figure_autorange` owns the domain the annotation
and chrome packers already pass as `figure._range`. ABI 107 does not change
Scene records either; `xyg_scene_resolve_mark_styles` owns per-kind fill/stroke
defaults and CSS→RGBA8 from packed `XYMS` v1. ABI 108 does not change Scene
records; `xyg_scene_resolve_chrome_style` owns the 200-byte chrome style input
from packed `XYCH` v1, and chrome/annotation packers call `xyg_css_color_rgba`
for the same conversion. ABI 109 does not change Scene records either;
`xyg_scene_pack_trace` owns Figure→Scene row packing (kinds, stable ids,
expansion modes, ribbon/triangle doubling, heatmap lattice framing) from
literal columns. ABI 136 does not change Scene records either;
`xyg_scene_resolve_pack_kind` / `xyg_scene_pack_product` own product-kind
mapping and the canonical host column envelope so pack-kind dispatch cannot
drift. ABI 137 / Scene v27 adds `DensityBlit=10`, `SceneRecordKind::Image=5`,
and the XYIM sidecar so Cartesian constant-style density scatter compiles
as one image blit instead of a Rect lattice. ABI 143 polar `DensityBlit`
tessellates occupied cells to PolyFill wedges. ABI 138 / Scene v28 adds the XYDS constant-dash sidecar so
dashed polylines compile on Scene. ABI 139 / Scene v29 adds the XYLC
constant-linecap sidecar so butt/square caps compile on Scene. ABI 140 /
Scene v30 adds `CurveFlatten=11` so cartesian `curve="smooth"` polylines
compile as denser Scene polylines; ABI 141 / Scene v31 adds `BandFlatten=12`
so cartesian `area(curve="smooth")` compiles as denser Scene Bands. ABI 142
admits cartesian mean-color density as XYHP kind 4 on the existing
`DensityBlit` Image blit (encoded Scene v31 is unchanged). ABI 143 polar
`DensityBlit` intern occupied cells as Rects that `with_polar` tessellates
to PolyFill wedges (encoded Scene v31 is unchanged). ABI 144 admits cartesian
`error_band(curve="smooth")` on existing `BandFlatten=12` and polar
`curve="smooth"` as identity chords (encoded Scene v31 is unchanged). ABI 145
admits constant scatter `marker_path` as XYMP extras tessellated to
PolyFill/Polyline after pixel mapping (encoded Scene v31 is unchanged). ABI 146
admits constant mark `fill` linear-gradients as XYGR extras (encoded Scene v31
keeps XYGR). ABI 147 does not change Scene records either;
`xyg_scene_pack_product_facts` owns flags/`step_mode`/extras from packed XYPK v1.
ABI 148 does not change Scene records either;
`xyg_scene_pack_annotation_facts` owns wrap/text/arrow/callout/rule routing
from packed XYAF v1.
ABI 149 does not change Scene records either;
`xyg_scene_pack_heatmap_facts` owns heatmap/density XYHP kind routing from
packed XYHF v1.
ABI 150 does not change Scene records either;
`xyg_scene_pack_scene_extras` owns XYDS/XYLC/XYMP/XYGR/XYMG layout, concat order,
and XYEX wrapping from packed XYSS v1 plus framed XYPL/XYHP.
ABI 151 does not change Scene records either;
`xyg_scene_pack_density_grid` owns Scene density `bin_2d` / `density_log_u8`
/ optional mean-color from packed columns.
ABI 152 does not change Scene records either;
`xyg_scene_pack_public_export` owns XYEP layout, kind/step/annotation codes,
and flag derivation from packed XYEF v1.
ABI 153 does not change Scene records either;
`xyg_scene_pack_figure_chrome` owns plot layout, chrome-style resolve, legend
loc default/allowlists (empty authored loc is fail-closed), colorbar
flags/framing, XYTL tick-label framing, and the 200-tick axis bound from
packed XYCF v1.
ABI 154 does not change Scene records either;
`xyg_scene_pack_trace_compile` owns per-trace Scene compile policy from
packed XYTC v1.
ABI 155 does not change Scene records either;
`xyg_scene_pack_trace_attach` owns heatmap/density attach policy from
packed XYTO plus XYTA v1.
ABI 156 does not change Scene records either;
`xyg_scene_pack_trace_rows` owns XYPK construction, scatter-only
symbol/diameter, density domain-endpoint column rewrite, and
`pack_product_facts` from packed XYTT plus XYCL v1.
ABI 157 does not change Scene records either;
`xyg_scene_pack_trace_sidecars` owns legend-name gating, heatmap-vs-density
plane selection, and per-trace style/dash/marker/gradient/plane extraction
from packed XYTT plus XYNM v1.
ABI 158 does not change Scene records either;
`xyg_scene_pack_style_sidecars` owns XYSS dash/linecap/marker/gradient
record construction from packed XYSD plus XYAO v1.
ABI 159 does not change Scene records either;
`xyg_scene_splice_annotations` owns annotation style/row splice and XYAD
extract from packed product rows plus XYSD plus XYAO v1.
ABI 160 does not change Scene records either;
`xyg_scene_encode_assembled` owns assembled Scene encode from packed XYAS
plus XYCC plus extras.
ABI 161 does not change Scene records either;
`xyg_scene_pack_figure_chrome_from_sidecars` owns legend paints from packed
XYSD and `xyg_scene_pack_scene_extras_from_sidecars` owns XYHP wrapping from
XYSD planes.
ABI 162 does not change Scene records either;
`xyg_scene_encode_assembled_from_sidecars` owns XYCC packing, extras packing,
and viewport/axis scalars from packed XYAS plus XYCF plus XYSD plus polar plus
XYSS.
ABI 163 does not change Scene records either;
`xyg_scene_encode_product` owns product-path compile, attach, sidecar, row,
annotation, style-sidecar, splice, and assembled encode from packed XYTC plus
XYTA plus XYNM plus XYCL plus XYAF plus XYCF plus polar.
ABI 164 does not change Scene records either;
`xyg_scene_static_export` owns public SVG/PNG/PDF/JPEG/WebP consumers from
one encoded Scene.
ABI 165 does not change Scene records either;
`xyg_scene_encode_product` additionally owns the figure-compile support probe
from packed XYFS.
ABI 166 does not change Scene records either;
cartesian bar/column/histogram `corner_radius` tessellates to PolyFill after
pixel mapping. ABI 167 insets polar bar/column/histogram `wedge_gap`. ABI 168
tessellates polar bar/column/histogram `corner_radius` when the inner radius
is positive. ABI 169 admits polar `curve="smooth"` plus `step` as polar step
expansion. ABI 170 admits constant scatter `marker_glyph` via XYMG. ABI 171 admits
scatter `stroke_width` without `stroke` as match-fill. ABI 172 admits cartesian
line `curve="smooth"` plus `step` as authored step expansion. ABI 173 tessellates
heatmap `corner_radius`. ABI 174 tessellates violin/box `corner_radius`. ABI 175 admits violin/box `fill_opacity` / `stroke_opacity`. ABI 176 admits bar/column/histogram `fill_opacity` / `stroke_opacity`. ABI 177 admits heatmap `fill_opacity`. ABI 178 admits scatter `fill_opacity` / `stroke_opacity`. ABI 179 admits hexbin `fill_opacity`. ABI 180 admits triangle_mesh `fill_opacity` / constant stroke paint. ABI 181 admits cartesian area/error_band `curve="smooth"` plus `step` as authored band step expansion. ABI 182 admits triangle_mesh `joined_fill` as one identity PolyFill ring from the Rust boundary walk. ABI 183 admits constant ribbon `color2_ch` as XYGR mark-space `dir=right`. ABI 116 does not change Scene records either;
`xyg_scene_pack_annotation_marks` owns rule/band/marker domain expansion
from packed scalars plus axis domains. ABI 117 does not change Scene records either;
`xyg_scene_figure_support_reason` owns figure-compile support from packed
observations plus axis ids/keys. ABI 118 does not change Scene records either;
`XYFS` v2 adds per-trace allowlist flags so kind and mark-feature diagnostics
are engine-owned. ABI 119 does not change Scene records either; composition
sort, histogram/contour edge policy, and custom-hex lattice groups are
engine-owned before Scene packing. ABI 120 does not change Scene records either;
`xyg_legend_normalize` / `xyg_legend_best_loc` own composition `loc="best"`
occupancy so hosts settle a concrete location before XYLG packing. ABI 110 does not change Scene records either;
`xyg_scene_pack_legend` owns primary XYLG legend framing from loc/flags,
paints, title, and entry meta. ABI 111 does not change Scene records either;
`xyg_scene_pack_colorbar` owns primary XYCB v2 framing from domain, stops,
ticks, title, and text RGBA. ABI 112 does not change Scene records either;
`xyg_scene_pack_annotations` owns primary XYAD framing from typed row meta
and concatenated labels. ABI 113 does not change Scene records either;
`xyg_svg_to_pdf` owns closed-subset SVG→PDF so public static PDF no longer
feeds Rust SVG through a Python converter. ABI 114 does not change Scene
records either; `xyg_encode_jpeg` and `xyg_encode_webp` own packed RGB/RGBA8
static encode so public JPEG/WebP no longer feed Scene pixels through Python
format modules. ABI 115 does not change Scene records either;
`xyg_encode_png` owns filter-0 PNG encode so remaining host PNG exports no
longer pack chunks or palettes in Python or Node. Polar
hexbin, custom reducers, metric colormaps, LOD, and rich style exceptions
fail closed and keep the compatibility exporters. Scene 25 is unchanged.

Constant-style Cartesian heatmap expands a regular rows×cols lattice onto
existing Scene v25 Rect records (one rectangle per cell) for
`public_static_export`. Hosts
reconstruct uniform cells from the stored range endpoints plus
`grid_shape`; paint uses the literal style color. Polar heatmap tessellates
those same Rects to PolyFill annular sectors (scalar colormaps become per-cell
literal styles). Cartesian scalar colormaps and truecolor RGBA planes use the
same per-cell Rect fills. Irregular spacing, LOD over the 10,000-Rect
histogram ceiling, and rich style exceptions fail closed and keep the
compatibility exporters. Scene 25 is unchanged.

ABI 98 makes the composition violin a compact Rust-owned ingress without a
Scene-version change. Hosts pack flat canonical f64 samples, monotone group
offsets, centers, bins, positive finite width, and orientation. Rust filters
nonfinite samples, skips empty groups without reordering, runs and normalizes
the shared density kernel, applies width/orientation, and emits at most 10,000
ordinary Rect rows plus group-major density metadata. Malformed offsets,
centers, bins, width/orientation, coordinate overflow, all-empty groups, and
over-budget output fail before partial writes. Constant-style primary
Cartesian violins with explicit domains route public SVG/PNG/PDF through these
Scene Rects; pyplot KDE bodies, polar, gradients, alternate axes, and per-item
styles remain compatibility paths.

ABI 99 makes composition boxes a compact Rust-owned ingress without changing
Scene 25. `xyg_box_geometry` is a bounded query/write operation over flat f64
values, monotone `size_t` offsets, f64 centers, orientation, positive finite
width, and `show_outliers`. Its fixed-stride output planes are active source
group IDs (`u32`); 25-f64 group records (five Tukey statistics, body rectangle,
three whisker/cap segments, median segment); monotone `size_t` outlier offsets;
and 3-f64 outlier records (value, x, y). Rust owns finite filtering, Tukey
statistics, stable group order, orientation/width policy, deterministic bounded
outlier jitter, and the combined 10,000-record bound. A zero-capacity query and
any short-capacity write return the required active-group and outlier counts
without writing output planes. Nonfinite source samples are filtered; malformed
offsets or orientation/visibility metadata, nonfinite centers/width, coordinate
overflow, all-empty input, and over-budget output fail atomically. Hosts retain coercion,
grouping/category packing, literal
style, and conversion to existing Rect, Polyline, and Scatter Scene families.
Constant-style primary-Cartesian boxes route public SVG/PNG/PDF through those
Scene consumers; alternate axes, polar, gradients, and per-item styles remain
explicit compatibility paths.
