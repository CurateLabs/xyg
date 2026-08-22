# Canonical scene IR

Issue [#58](https://github.com/CurateLabs/xyg/issues/58) moves parity-affecting
scene and static-export decisions into `xyg-engine` in bounded vertical slices.
This document is the version contract for that migration.

## Ownership and versioning

`crates/xyg-engine/src/scene.rs` owns the canonical scene records.
`SCENE_VERSION` is 10 and is exposed as `xyg_scene_version`; hosts may
reject an unsupported scene version independently of the C `ABI_VERSION`.
Changing a record's meaning, units, ordering, bounds, or adding any newly
emitted record kind requires a scene-version bump. There is no capability
bitmap or schema negotiation in version 10, so additive emission is not safe.
If capability negotiation lands later, only explicitly negotiated additions
may avoid a version bump. Consumers must reject an unsupported scene version
and, once decoders land, fail closed on an unknown kind rather than guessing.
`validate_scene_batch` is the allocation-free Rust decoder used by the #59
WASM lifecycle foundation; it validates the exact version-10 layout (shared fixed
header/mark widths since version 4), bounds,
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
batch is accepted by `xyg_scene_svg` for a complete SVG and by
`xyg_scene_raster_commands` for the existing native raster display list. Both
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

All records are emitted in authored order. `visible = 0` means all four
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
Public SVG/PNG/PDF still use the compatibility renderers until remaining
chrome (backgrounds, density overlays, fuller measured rooms) can select
Scene without dropping established export behavior.

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

Python and Node mechanically pack the same 200-byte block and tick arrays;
their non-default fixture is exact-byte identical. Rust SVG and raster consume
the decoded values directly. Browser painter v4 carries the same 200 bytes in
its fixed 280-byte header, adds the three bounded authored title/axis-label
lengths, and marks every 16-byte tick descriptor as major or minor. TypeScript
validates and projects those values and texts into existing DOM/WebGL and
accessibility paint surfaces without generating tick positions, sides, or
style defaults.

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

Next slices add remaining polar marks, annotation/colorbar records and richer
legend variants, then select public SVG/PNG/PDF Scene auto-routing once
chrome and CSS-spelling parity with ``_svg.py`` is covered; ``try_public_svg`` /
``try_public_png`` / ``try_public_pdf`` are the opt-in helpers. Unlabeled
cartesian annotations remain rejected rather than being approximated as marks.

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
paint ordering for SVG and native raster. Browser painter v7 appends the exact
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
declarations fail closed. Colorbars remain explicit later issue-#116 work;
Scene v10 additionally supports the bounded primary annotations below and does
not approximate richer forms.

## Version 10: primary Cartesian rule, band, and marker annotations

Version 10 reserves stable IDs with high word `0x5859TT00` (`TT` is rule,
band, or marker) and lowers the bounded primary annotation subset into the
existing canonical Polyline, Rect, and Scatter records. Annotation records are
always appended after data records, so Rust SVG, raster, and browser-painter
consumers share exact projection, clipping, marker geometry, style validation,
resource bounds, and paint order. Python and Node only coerce the same author
values and produce byte-identical records. Painter v7 recognizes the reserved
IDs and projects them into the existing browser annotation layer; TypeScript
does not derive geometry or defaults. It also adds a literal, visually hidden
`role=note` description for each direct-WASM annotation. These descriptions name
the reference kind and orientation without misrepresenting Rust-projected pixel
coordinates as authored data values.

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
Authored solid chart/plot backgrounds, axis sides, and major/minor tick
geometry/styles are Scene v8.
Category, angular, and time/calendar tick ladders already move
through `xyg_scene_axis_ticks` kinds 2–5; Scene v5 carries authored chrome
paints plus title/axis-label UTF-8; ABI `xyg_scene_plot_layout` owns Cartesian
gutters for Scene compilation. Cartesian rect-family hosts
(`bar`, `column`, `histogram`, `violin`, `box`) share Scene Rect records;
segment-family hosts (`segments`, `errorbar`, `stem`, `contour`,
`box_whisker`, `box_median`) and stepped lines share Scene Polyline records;
band-family hosts (`area`, `error_band`, solid `ribbon`) share Scene Band
records; `triangle_mesh` shares Scene PolyFill records. Browser DOM measurement and
WebGL paint remain environment-specific consumers with documented layout
tolerances (§7 and §21).
