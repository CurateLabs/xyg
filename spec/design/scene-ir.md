# Canonical scene IR

Issue [#58](https://github.com/CurateLabs/xyg/issues/58) moves parity-affecting
scene and static-export decisions into `xyg-engine` in bounded vertical slices.
This document is the version contract for that migration.

## Ownership and versioning

`crates/xyg-engine/src/scene.rs` owns the canonical scene records.
`SCENE_VERSION` is 4 and is exposed as `xyg_scene_version`; hosts may
reject an unsupported scene version independently of the C `ABI_VERSION`.
Changing a record's meaning, units, ordering, bounds, or adding any newly
emitted record kind requires a scene-version bump. There is no capability
bitmap or schema negotiation in version 4, so additive emission is not safe.
If capability negotiation lands later, only explicitly negotiated additions
may avoid a version bump. Consumers must reject an unsupported scene version
and, once decoders land, fail closed on an unknown kind rather than guessing.
`validate_scene_batch` is the allocation-free Rust decoder used by the #59
WASM lifecycle foundation; it validates the exact version-4 layout, bounds,
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
vertex, or `RectScene`), visibility/clipping flag, scatter symbol, stable u64
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

Decoders must require the exact header/record widths for the declared version,
reject unknown kinds, and enforce the reserved-zero fields above. They must not
infer a different grouping or corner convention.

The existing `xyg_scene_scatter_svg` entry point remains a compatibility
wrapper during migration. Version 3 intentionally has no mark-specific new SVG
ABIs: whole-scene SVG/raster consumers attach to the single scene batch.
Python `Figure.to_scene()` and Node `Figure.toScene()` compile the migrated
constant-style cartesian scatter/line/bar subset plus two axes. Their explicit
Scene SVG/raster APIs exercise the Rust consumers. Public Python SVG/PNG/PDF
remain on the established compatibility renderers until Scene records encode
canonical layout and authored text/style; they must not silently select a
semantically incomplete scene. Missing/nonfinite coordinates and unsupported
customization fail closed from the explicit scene API. This is a migration
boundary, not a silent approximation.

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
Version 4 does not encode titles, axis titles, custom tick values/text, custom
sides, minor ticks, or authored chrome styles. Hosts reject those features from
explicit Scene compilation, and public exports retain compatibility routing.
Canonical layout/gutter selection and authored text/style records must land
before public SVG/PNG/PDF selection can be exact.

## Evidence and extension order

Rust unit tests pin schema validation and byte-deterministic SVG. Python tests
prove explicit Scene consumption while public exports preserve ticks, grids,
text, and customization through the compatibility path. Node tests consume the
same scene fixture and reject the same unsupported subset. ABI generation,
parity, and version-first loading cover both hosts.

The first browser consumer accepts the exact v4 bytes through the static WASM
Worker. Rust validates and lowers them through
`SceneDocument::to_browser_painter` into checked f32 geometry and split-u64
stable-ID columns plus the default numeric ticks and formatted UTF-8 labels.
Painter contract v2 carries fixed trace and tick descriptors with exact bounds.
Browser tick tables serialize every `AxisTicks::ticks` position (so log minor
grid lines match SVG/raster) and attach formatted labels only for
`AxisTicks::labeled`; unlabeled minor ticks carry empty UTF-8 labels.
The TypeScript adapter creates views over transferred columns and supplies the
Rust-authored ticks and labels to the existing canvas/DOM chrome surfaces. It
performs no O(record) decode/re-encode and does not reproduce mapping, grouping,
clipping, identity, tick generation, or label formatting policy.

Next slices add authored text/chrome styles, remaining mark families, and
legend/annotation records. Category, angular, and time/calendar tick ladders
already move through `xyg_scene_axis_ticks` kinds 2–5 so Python/Node SVG
exporters and Node `axisTicks` share the same Rust policy. Browser DOM
measurement and WebGL paint remain environment-specific consumers with
documented layout tolerances (§7 and §21).
