# Canonical scene IR

Issue [#58](https://github.com/CurateLabs/xyg/issues/58) moves parity-affecting
scene and static-export decisions into `xyg-engine` in bounded vertical slices.
This document is the version contract for that migration.

## Ownership and versioning

`crates/xyg-engine/src/scene.rs` owns the canonical scene records.
`SCENE_VERSION` is 22 and is exposed as `xyg_scene_version`; hosts may
reject an unsupported scene version independently of the C `ABI_VERSION`.
Changing a record's meaning, units, ordering, bounds, or adding any newly
emitted record kind requires a scene-version bump. There is no capability
bitmap or schema negotiation in Scene v20, so additive emission is not safe.
If capability negotiation lands later, only explicitly negotiated additions
may avoid a version bump. Consumers must reject an unsupported scene version
and, once decoders land, fail closed on an unknown kind rather than guessing.
`validate_scene_batch` is the allocation-free Rust decoder used by the #59
WASM lifecycle foundation; it validates the current Scene v20 batch layout,
including the shared fixed header/mark widths retained since version 4, bounds,
reserved bytes, kinds, style references, finite coordinates, and canonical
hidden-record zeroing rather than duplicating offsets in TypeScript.

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

The same schema owns bounded f64 tick records for linear and base-10 log axes,
plus vectorized linear, log, and symlog scale records.
Each record carries all tick positions, the labeled subset, and the canonical
step. Rust applies the existing 1/2/2.5/5/10 linear ladder and 1/2/5 log
ladder, with a hard 200-tick ceiling. Python's SVG and raster exporters call
this record through `_svg._linear_ticks` and `_svg._log_ticks`; Node exposes it
as `axisTicks`. Invalid domains and target counts fail closed at the ABI.
Scale records own domain-to-coordinate, domain-to-pixel, and inverse-coordinate
mapping, including reversed pixel ranges, log clip/mask behavior, and symlog's
positive constant. Python's `_Scale` and Node's `scaleMap` consume the same
bounded f64 policy. Browser interaction retains its TypeScript mapping until
the direct Rust/WASM execution boundary in #59 is available.

Python calls the scatter path from `_svg._scatter_marks`; Node exposes the same record
through `scatterSceneSvg`. Python remains responsible for ingest coercion,
public validation text, channel-to-RGBA resolution, plot layout, and polar projection
until those policies move in later slices. Authored arbitrary marker paths and
font glyph markers stay on the existing Python compatibility path because they
need separate bounded path/text records.

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
Non-scatter records must set symbol and diameter to zero.

Rust validates finite non-negative viewport/margins, a non-empty plot region,
all scale fields, known record kinds, equal array lengths, finite input values,
and `MAX_SCENE_MARKS`. Style references must resolve inside the embedded table;
scatter symbols use the stable built-in symbol table and authored outer
diameters/stroke widths must be finite and non-negative. The canonical marker
policy shared with the version-1 SVG wrapper is:

- line-only symbols (`plus_line`, `x_line`, `horizontal_line`, `vertical_line`)
  use an implicit 1px stroke only when authored stroke width is zero;
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
  sample. Symbol and diameter are zero. Consecutive visible kind-3 records with
  the same stable ID and `style_ref` form one filled polygon: tops in record
  order, then bases in reverse order, closed. Unlike Rect, Band does not
  min/max-normalize corners — sample order is preserved so the polygon matches
  the authored series.

Decoders must require the exact header/record widths for the declared version,
reject unknown kinds, and enforce the reserved-zero fields above. They must not
infer a different grouping or corner convention.

The existing `xyg_scene_scatter_svg` entry point remains a compatibility
wrapper during migration. Version 3 intentionally has no mark-specific new SVG
ABIs: whole-scene SVG/raster consumers attach to the single scene batch.
Python `Figure.to_scene()` and Node `Figure.toScene()` compile the migrated
constant-style cartesian subset plus two axes: scatter/line (with host-side
`step` expansion for `pre`/`post`/`mid`), rect-family marks
(`bar`/`column`/`histogram`/`violin`/`box`), segment-family marks
(`segments`/`errorbar`/`stem`/`contour`/`box_whisker`/`box_median`) as
disconnected Scene Polyline runs (unique stable id per segment), and
band-family marks (`area`/`error_band`/solid `ribbon`) as Scene Band samples, and `triangle_mesh` as Scene PolyFill vertex runs. Gradient fills,
non-zero `corner_radius`, and density-tier scatter are rejected until dedicated
records exist. Their explicit Scene SVG/raster APIs exercise the Rust consumers.
Node's public `Figure` accepts an `annotations` constructor array and exposes
fluent `annotate(annotation)` authoring for the already-versioned bounded
Cartesian annotation records. Those APIs only retain authored objects; they do
not duplicate coordinate, style, resource-limit, or support-predicate policy.
`figureSceneV3` remains the Node packing seam and Rust remains the decoder,
layout, and rendering authority.
Public Python SVG/PNG/PDF remain on the established compatibility renderers
until Scene records encode canonical layout and authored text/style; they must
not silently select a semantically incomplete scene. Missing/nonfinite
coordinates and unsupported customization fail closed from the explicit scene
API. This is a migration boundary, not a silent approximation.

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
The public SVG/PNG/PDF router now selects these Rust consumers only for the
proven constant-style Cartesian circle-scatter subset. Explicit Scene APIs may
exercise broader migrating records, but line/rect/band/segment/ribbon marks,
non-circle symbols, annotations, text, legends, themes/style tokens, customized
axis chrome (including the independent ``ticks=False`` / ``text=False``
visibility switches), export-only backgrounds, fluid or too-small viewports, and
screen-bounded LOD inputs remain on the compatibility renderer before
compilation. Malformed input and Rust consumer failures propagate and never
cause fallback. For those visibility-switch exceptions, the compatibility SVG
and raster consumers retain the otherwise-default Scene chrome (12 px labels
and 4 px major ticks) so changing one switch does not visibly re-style the
other axis merely by crossing the routing boundary.

## Version 6: Band filled polygons

Version 6 keeps the version-5 header, style table, mark record width, and
chrome trailer. It adds `BandScene` (kind 3) so area and error-band hosts can
encode top/base samples without inventing a second polygon policy in Python or
Node. Whole-scene SVG emits one closed `<path>` per band run; raster emits
`OP_FILL_POLY`; the browser painter lowers bands as area geometry with a
`base` column. Version 5 consumers must reject version-6 batches.

## Version 7: PolyFill vertices and ribbon Band tessellation

Version 7 keeps the version-6 header, style table, mark record width, and
chrome trailer. It adds `PolyFill` (kind 4): consecutive vertices with the same
stable ID and style form one closed filled polygon (triangle-mesh hosts emit
one three-vertex run per triangle). Solid-color `ribbon` marks tessellate on
the host into Scene Band samples using the shared `RIBBON_STEPS` cubic edge
contract; two-ended gradients remain rejected until a Scene gradient record
exists. Version 6 consumers must reject version-7 batches.

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
chrome remains Cartesian. Polar projection and polar chrome require an explicit
versioned Scene semantic and remain rejected by the v10 host support predicate.

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
prove explicit Scene consumption while public exports preserve ticks, grids,
text, and customization through the compatibility path. Node tests consume the
same scene fixture and reject the same unsupported subset. ABI generation,
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
Rust Scene; PDF consumes that Rust SVG. ``try_public_svg`` /
``try_public_png`` / ``try_public_pdf`` expose the same consumers to callers
that need an optional result. Unlabeled cartesian annotations remain rejected
rather than being approximated as marks.

The public router has one selection seam,
``_scene_v3.public_static_export``. It consults the one support predicate,
``_scene_v3.scene_export_support_reason``, which returns the stable
``XYG_SCENE_UNSUPPORTED_*`` diagnostic (or the compiler's bounded message) for a
figure outside the migrated subset and ``None`` when the Rust Scene path
applies. ``public_static_export`` returns ``None`` only for that explicit
pre-compilation compatibility decision; every selected Scene compiler and
consumer error propagates. Figure methods and both legacy/unified Python export
entry points delegate to it rather than independently selecting a Scene consumer.
Parity with the compiler is by construction — the predicate runs
``figure_scene`` — so a router built on it can never disagree with the encoder it
guards, and it never triggers a silent fallback: input errors (for example a
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
to `upper right`). Automatic `loc="best"` placement remains unsupported until
that occupancy policy moves into Rust. Anchors, extra legends,
multiple columns, category rows, continuous ramps, gradients, dashes,
interactive toggles/highlight, custom content, CSS fonts, and arbitrary style
declarations fail closed.

## Version 20 bounded callout label backgrounds

Scene v20 evolves `XYAC` to v2 for an optional literal RGBA8 callout-label
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

Scene v21 evolves `XYAL` to v3 for an optional literal RGBA8 background on an
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

Scene v22 evolves `XYAT` to v2 for an optional literal RGBA8 background on a
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

The supported surface is unlabeled axis-aligned rules, axis-aligned bands, and
unlabeled built-in markers with solid literal colors, opacity, and bounded
width/size. Text labels, callouts, arrows, classes, dash/span overrides,
coordinate-space transforms, and unknown styles fail closed with a precise
migration diagnostic. In particular, a marker label never disappears silently.
Those deferred kinds are the next #116 annotation slice. Existing nightly
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
root/chrome/annotation CSS classes, object-valued fills and two-ended ribbon
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
Category, angular, and time/calendar tick ladders already move
through `xyg_scene_axis_ticks` kinds 2–5; Scene v5 carries authored chrome
paints plus title/axis-label UTF-8; ABI `xyg_scene_plot_layout` owns Cartesian
gutters, including the selected literal-colorbar outer lane, for Scene compilation. Cartesian rect-family hosts
(`bar`, `column`, `histogram`, `violin`, `box`) share Scene Rect records;
segment-family hosts (`segments`, `errorbar`, `stem`, `contour`,
`box_whisker`, `box_median`) and stepped lines share Scene Polyline records;
band-family hosts (`area`, `error_band`, solid `ribbon`) share Scene Band
records; `triangle_mesh` shares Scene PolyFill records. Browser DOM measurement and
WebGL paint remain environment-specific consumers with documented layout
tolerances (§7 and §21).
