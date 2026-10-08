# Geospatial data contract — GeoColumn, GeoArrow ingress, GeoViewport

**Status:** GeoColumn native validation, canonical metadata, host read-back
and derived-cache inputs (#47; current ABI 380) + GeoViewport perspective camera (#48).
MapLibre layers (#49) and LOD/export/scale (#50) build on these contracts.
Direct-browser WASM ABI 30 shares typed descriptor ingestion (`XYGD` to `XYGM`)
and frozen point/outline scene lowering (`XYGP` to canonical `XYGS`) with native
Rust. Actual native-versus-wasm32 derived scene parity covers the bounded,
frozen camera scope. Rust now supplies perspective camera transitions, clipped
route/polygon caches and geometric visible membership (#48); layer/fill surfaces
remain #49 and LOD/export #50.
Painter hydration preserves Rust-resolved RGBA alpha without applying ordinary
mark opacity defaults again; strict-CSP pixels pin opaque and half-alpha points.

## Product rule

Rust owns geographic source validation, CRS interpretation, retained f64
geometry, offsets, validity, feature identity, and resource limits. Hosts
(Python, Node, browser/WASM) decode Arrow / GeoArrow at their boundary and
forward a **typed descriptor** — never a second geometry engine, never
GeoJSON row expansion on the product path, and never an Arrow dependency
inside `xyg-engine`.

Rust also owns the geographic **camera / projection** (`GeoViewport`):
center, zoom, size, bearing, pitch, CRS, world-wrap, fit, and lon/lat ↔
Web Mercator ↔ screen equations. MapLibre (optional browser shell) may
supply camera events and basemap chrome; it never becomes the authority for
feature geometry, identity, styling, picking, LOD, or projected feature
coordinates. See #39 / #49 for the shell boundary.

## Certified profile (v1)

| Concern | Contract |
| --- | --- |
| Geometry kinds | Homogeneous `point`, `linestring`, `polygon`, `multipoint`, `multilinestring`, `multipolygon` |
| Coordinates | Separated GeoArrow XYG as interleaved host `f64` (`[x0,y0,x1,y1,…]`) |
| CRS | Explicit only: `EPSG:4326` (lon/lat) and `EPSG:3857` (easting/northing) |
| Axis order | Always x/y; never inferred or swapped |
| Nullability | Top-level per-feature validity (`0`/`1`); nested parts cannot be null; a null feature owns no vertices or parts (`-14`) |
| Precision | Canonical geometry stays f64; derived f32 scene buffers are rebuildable caches (§27) |
| Identity | Optional host `u64` feature IDs (one per feature, nulls included); otherwise dense `0..n` |
| Ring winding | Recorded per ring (`1` CCW, `2` CW), never applied: source vertex order is retained unchanged |
| Errors | Stable `XYG_GEO_*` codes; diagnostics never include coordinate values |

Geometry collections, mixed-geometry columns, Z/M, WKB/WKT/GeoJSON as
canonical transport, CRS inference, and arbitrary reprojection are out of
scope for v1.

## Descriptor layout

Hosts supply:

1. `geometry` + `crs` enums matching the GeoArrow extension name /
   `authority_code` metadata GraphForge publishes.
2. Interleaved `xy: f64[2 * vertex_count]`.
3. `validity: u8[feature_count]` (`1` present, `0` null).
4. Optional `feature_ids: u64[feature_count]` (null pointer = dense `0..n`).
5. Nested `u32` offset planes by geometry depth:

| Kind | `offsets0` | `offsets1` | `offsets2` |
| --- | --- | --- | --- |
| Point | (empty; one vertex per present feature) | — | — |
| LineString / MultiPoint | feature → vertex | — | — |
| Polygon / MultiLineString | feature → ring/line | ring/line → vertex | — |
| MultiPolygon | feature → polygon | polygon → ring | ring → vertex |

Offset planes are Arrow-List compatible: length `n + 1`, monotonic,
`offsets[0] == 0`, last entry equals the child count. Polygon rings must
contain at least four vertices and close with bitwise-identical endpoints.
Within a polygon the first ring is the exterior (structural in GeoArrow) and
every later ring is a hole. Point columns carry one vertex per *present*
feature: a null point contributes no vertex.

## GeoArrow mapping

Field-level Arrow extension metadata (GraphForge producer profile):

| Geometry | `ARROW:extension:name` |
| --- | --- |
| Point | `geoarrow.point` |
| LineString | `geoarrow.linestring` |
| Polygon | `geoarrow.polygon` |
| MultiPoint | `geoarrow.multipoint` |
| MultiLineString | `geoarrow.multilinestring` |
| MultiPolygon | `geoarrow.multipolygon` |

CRS metadata JSON (canonical spelling):

```json
{"crs":"EPSG:4326","crs_type":"authority_code"}
```

XYG does not import Arrow in the engine. Python/Node may use Arrow only as an
ingest adapter that emits the descriptor above. Browser payloads carry typed
buffers and metadata, not imported Arrow modules or full JSON geometry rows.

Producer-neutral interchange fixtures from GraphForge
(`tests/contracts/geoarrow-interchange-v1.json` and
`tests/fixtures/geoarrow-v1/`) are the compatibility reference. XYG unit
tests read the checked-in Arrow IPC and Parquet artifacts, verify their pinned
SHA-256 digests and field metadata, and require both formats to lower into
identical typed descriptors. Every certified geometry is then published
through the Rust `GeoColumn` boundary. GraphForge's preserved-only vendor CRS
case remains transportable by GraphForge but fails closed at XYG's deliberately
narrow v1 compute boundary.

## Validation

Before a `GeoColumn` is published, Rust rejects the following. Checks run in
this order and the first failure wins, so a hostile descriptor is bounded
before any per-vertex work or owning copy:

1. feature count over `max_features`, odd-length `xy`, vertex count over
   `max_vertices`, ID length mismatch, validity flags outside `{0,1}`;
2. **byte budget**, derived from lengths only (`xy` + validity + feature IDs +
   offset planes + one orientation byte per ring) against `max_bytes`;
3. offset planes that disagree with geometry depth or vertex counts, and
   **null-part consistency**: a null feature must own an empty `offsets0` range
   (monotonic offsets make that transitively empty at every depth), else `-14`;
4. non-finite coordinates;
5. coordinates outside CRS bounds (WGS84 lon ∈ [-180,180], lat ∈ [-90,90];
   Web Mercator ±20_037_508.342_789_244);
6. **degenerate lines**: a LineString / MultiLineString part with exactly one
   vertex (`-12`); empty (0-vertex) line parts stay legal;
7. polygon rings: empty ring (`-5`), fewer than four vertices or open ring
   (`-8`), zero shoelace area (`-12`, computed relative to the first vertex);
8. **holes**: every hole must lie inside its exterior ring (`-11`).

Hole containment is deliberately not full polygon topology. Each hole's bbox
must sit inside the exterior bbox and the hole's first vertex must pass a
boundary-inclusive even-odd ray cast against the exterior (f64), so a hole may
touch its shell. If the shell crosses the world boundary, containment is checked
in a bounded, temporary short-edge unwrapped f64 copy (period 360 degrees or
the EPSG:3857 world extent), aligning each hole to that shell. The canonical
coordinates, offsets and original winding metadata remain bitwise unchanged.
An unwrapped ring spanning more than one world fails as degenerate. Hole/hole overlap and edge crossings are not checked in v1. The
work is bounded: one shell-edge sweep per hole against a total budget of
`max_vertices * 64` edge visits, exceeding which fails with `-9`.

Ring orientation is **recorded, not rewritten**: `GeoColumn::ring_orientations`
holds one byte per ring in ring-plane order (`1` counter-clockwise, positive
signed area; `2` clockwise), empty for non-polygon kinds, so later fill layers
(#49) can wind correctly without re-walking source geometry. Producers that
emit shapefile-style or GeoJSON-style winding are both accepted; the BDD
contract is that geometry enters XYG unchanged.

Budgets are `GeoLimits` (defaults 1e6 features / 1e7 vertices / 256 MiB) and are
engine-owned at the ABI: hosts cannot raise them. Failures are atomic: no
partial column is retained and no handle is returned.

## Stable ABI errors

`GeoError` discriminants are the ABI status codes; messages are value-free
(no coordinates), pinned by an engine test. Hosts map them to typed errors and
must not rewrite the code.

| Code | Name | Meaning |
|---:|---|---|
| -1 | `XYG_GEO_INVALID_ARGUMENT` | Incomplete / inconsistent descriptor (odd `xy`, flag > 1, null pointer for a non-empty plane; ID length mismatch is reported by the host adapters, since the ABI derives the ID count from validity) |
| -2 | `XYG_GEO_UNSUPPORTED_CRS` | CRS outside EPSG:4326 / EPSG:3857 |
| -3 | `XYG_GEO_TYPE_MISMATCH` | Offset planes do not match the geometry depth |
| -4 | `XYG_GEO_OFFSET_MISMATCH` | Offsets not Arrow-List shaped or disagree with child counts / Point validity |
| -5 | `XYG_GEO_NULL_CHILD` | Nested part (ring) is null / empty |
| -6 | `XYG_GEO_NON_FINITE_COORDINATE` | NaN or infinity |
| -7 | `XYG_GEO_COORDINATE_OUT_OF_RANGE` | Outside the declared CRS bounds |
| -8 | `XYG_GEO_RING_NOT_CLOSED` | Ring has fewer than four vertices or endpoints differ bitwise |
| -9 | `XYG_GEO_RESOURCE_LIMIT` | Feature, vertex, byte, or hole-containment work budget exceeded |
| -10 | `XYG_GEO_STALE_HANDLE` | Handle freed or never issued |
| -11 | `XYG_GEO_HOLE_OUTSIDE_SHELL` | Interior ring not contained by its exterior ring |
| -12 | `XYG_GEO_DEGENERATE_GEOMETRY` | One-vertex line part or zero-area ring |
| -13 | `XYG_GEO_OUTPUT_CAPACITY` | Host read-back buffer smaller than the column (nothing written) |
| -14 | `XYG_GEO_NULL_FEATURE_NOT_EMPTY` | Null feature owns vertices or parts |

## Canonical metadata (`XYGM` v1)

`GeoColumn::canonical_metadata()` is the projection-independent, host-neutral
document every host, including WASM, must return
byte-identically for the same column. It is built lazily, cached on the column,
and little-endian throughout; offsets below are from the start of the document.

| Offset | Field | Type |
|---:|---|---|
| 0 | magic `XYGM` | `u8[4]` |
| 4 | version (`1`) | `u32` |
| 8 | geometry (`1` point … `6` multipolygon) | `u32` |
| 12 | CRS authority code (`4326` / `3857`) | `u32` |
| 16 | feature count | `u64` |
| 24 | vertex count | `u64` |
| 32 | null count | `u64` |
| 40 / 48 / 56 | `offsets0` / `offsets1` / `offsets2` lengths (elements) | `u64` x3 |
| 64 | ring count (= orientation plane length) | `u64` |
| 72 | digests of `xy`, validity, feature IDs, offsets, orientations | `u8[8]` x5 |
| 112 | extension name length, then UTF-8 name (`geoarrow.*`) | `u32` + bytes |
| next | extension metadata length, then canonical CRS JSON | `u32` + bytes |
| end | zero padding to a multiple of 8 | |

Each digest is an eight-byte BLAKE2s (the engine's `Blake2s8` from `transition.rs`,
no external crate) over a domain tag (`xygm-xy`, `xygm-validity`,
`xygm-ids`, `xygm-offsets`, `xygm-orient`) and a length-prefixed plane in
little-endian element bytes; the offsets digest chains all three planes. Dense
IDs are hashed as the materialized `0..n`, so supplying `0..n` explicitly is
identical to omitting IDs. `xy` is hashed by IEEE-754 bits, so `-0.0` and `0.0`
differ. `GeoColumn::metadata_digest()` is a further BLAKE2s-8 over the tag
`xygm-doc` and the document bytes; it keys derived caches (below).

## ABI 379 surface

All exports are in `crates/xyg-core` and generated into the Python and Node ABI
modules (`spec/abi/xyg-abi.json`, `spec/abi/xyg.h`); `ABI_VERSION` is 379.

| Export | Contract |
|---|---|
| `xyg_geo_column_new` | Validate + retain a typed descriptor (unchanged; v1 limits). Returns `0` plus a negative code in `out_error` |
| `xyg_geo_column_free` / `_len` / `_vertex_count` / `_geometry` / `_crs` | Handle lifecycle and scalar facts (unchanged) |
| `xyg_geo_column_metadata(handle, out, cap) -> usize` | Returns the required document length and copies only when `cap >= required`; `NULL` + `0` is a size query. Returns `usize::MAX` for a stale handle or `NULL` with `cap > 0` |
| `xyg_geo_column_plane_lens(handle, out_lens[7]) -> i32` | Element counts: `xy` (f64 values), validity, IDs, `offsets0`, `offsets1`, `offsets2`, orientations. `-1` NULL `out_lens`, `-10` stale; untouched on failure |
| `xyg_geo_column_copy(handle, 7 x (dest, cap)) -> i32` | Read-back of `xy` f64, validity u8, IDs u64, `offsets0..2` u32, orientations u8. Capacities are element counts. All-or-nothing: `-10` stale, `-13` any capacity too small, `-1` NULL destination for a non-empty plane; nothing is written on failure |

Read-back is what makes lossless retention observable from hosts: a round trip
publishes through Rust and reads the same bits back (`xy` by IEEE-754 bits,
offsets, validity, IDs) instead of asserting preservation only inside Rust
unit tests.

## Derived caches (rebuildable, §27)

`GeoViewport::project_column(&GeoColumn) -> ProjectedGeoColumn` lowers a
retained column into f32 scene inputs. Native ABI 380 and WASM ABI 30 expose
this processor through typed XYVC/XYVR requests, with thin Python, Node and
browser adapters described in [geo-viewport-protocol.md](geo-viewport-protocol.md).

- Output is a rebuildable cache keyed by
  `GeoDerivedKey { rebuild: GeoViewportRebuildKey, metadata_digest }` (exact
  camera identity plus the column's `XYGM` digest). Equal keys produce
  bit-identical buffers, so a host may keep or drop them freely; canonical f64
  geometry is never modified.
- `Point` / `MultiPoint` columns emit `ProjectedGeoGeometry::Points`: one
  offset-encoded f32 vertex per retained point with its source feature ID
  (null points own no vertex and no ID; MultiPoint repeats the owner ID per
  vertex), relative to the f64 viewport-center origin (§4/§16). An offscreen
  first source vertex cannot shift the encode origin or erase visible detail.
- `LineString` / `MultiLineString` columns emit each line part, and
  `Polygon` / `MultiPolygon` columns emit **every ring (shell and holes) as a
  closed outline**, as `ProjectedGeoGeometry::Outlines` through
  `project_line_features` (clipped two-point segments, per-segment source
  feature ID, dateline splitting when world wrap is active). Fill topology and
  ring splitting remain #49.
- Null features are absent from the output; NaN never reaches a buffer (§19);
  an invalid camera fails before any output is built. A column whose CRS differs
  from the camera CRS fails with `XYG_GEO_INVALID_ARGUMENT` (no reprojection in
  v1). Outline output uses `GeoLimits::default()` (1e6 parts).

## Host surfaces

- Python: `xyg._native.geo_column_new` (with `feature_ids=`),
  `geo_column_metadata(handle) -> bytes`, `geo_column_plane_lens(handle)`,
  `geo_column_read(handle)` (NumPy planes: `xy` f64, `validity` u8,
  `feature_ids` u64, `offsets0/1/2` u32, `orientations` u8), plus the existing
  `geo_column_meta` / `geo_column_free`. `GeoNativeError` maps codes -1..-14.
  `xyg._geoarrow.ingest_geoarrow(column, field, feature_ids=None)` lowers a
  pyarrow GeoArrow extension array (and an optional `u64`/`i64` ID column of
  matching length) into the descriptor; GraphForge identity therefore survives
  ingest.
- Node: `packages/xy-node/src/abi.js` `geoColumnNew` / `geoColumnMeta` /
  `geoColumnFree` plus `geoColumnMetadata(handle)` (`Uint8Array`),
  `geoColumnPlaneLens`, and `geoColumnRead(handle)`
  (`{ xy: Float64Array, validity, featureIds: BigUint64Array, offsets0..2:
  Uint32Array, orientations }`). `geoDescriptorFromGeoArrow({ extensionName,
  extensionMetadata, x, y, validity, offsets, featureIds })`
  (`packages/xy-node/src/geoarrow.js`) mirrors the Python adapter decisions
  (same CRS parsing, same null-Point packing) from typed arrays; Node takes no
  Arrow dependency.
- Browser/WASM: `encodeWasmGeoDescriptor` frames typed `XYGD` v1 planes;
  `XygWasmWorker.geoColumnIngest(request)` returns the shared `XYGM` bytes
  through sequenced WASM ABI 28. Rust validates canonical geometry; no column
  survives the call. The TypeScript painter never imports Arrow or rebuilds
  rows. Framing, resource and lifecycle details are in [browser-wasm.md](browser-wasm.md).

```python
import numpy as np
import pyarrow as pa
from xyg import _native, _geoarrow

handle = _geoarrow.ingest_geoarrow(
    column, field, feature_ids=pa.array([10, 11], pa.uint64())
)
meta = _native.geo_column_metadata(handle)   # b"XYGM" + v1 document
planes = _native.geo_column_read(handle)     # bitwise-equal to the source
assert meta[:4] == b"XYGM" and planes["xy"].dtype == np.float64
_native.geo_column_free(handle)
```

```js
import { geoColumnNew, geoColumnMetadata, geoColumnRead, geoColumnFree,
  geoDescriptorFromGeoArrow } from "@curatelabs/xyg-node";

const handle = geoColumnNew(geoDescriptorFromGeoArrow({
  extensionName: "geoarrow.polygon",
  extensionMetadata: '{"crs":"EPSG:4326","crs_type":"authority_code"}',
  x, y, validity, offsets: [o0, o1], featureIds,
}));
const metadata = geoColumnMetadata(handle);  // same bytes as Python
const { xy, offsets1, orientations } = geoColumnRead(handle);
geoColumnFree(handle);
```

## Parity fixtures

`tests/fixtures/geo_cross_host.json` is authored by
`packages/xy-node/test/fixtures/write_geo_cross_host_fixtures.py` from the
pinned GraphForge IPC fixtures plus locally built cases (polygon with a hole,
multipolygon with holes, EPSG:3857 linestring, multipoint with a null, explicit
feature IDs). Each case stores the extension name and metadata JSON, the
descriptor planes (`xy` as `float.hex()` for bitwise parity), the ABI version,
and the `XYGM` bytes with their SHA-256. `tests/test_geo_cross_host.py` and
`packages/xy-node/test/geo-cross-host.test.mjs` rebuild every case through their
host, then assert identical metadata SHA-256 and read-back planes equal to the
golden. The golden is projection-independent (no viewport). Node cannot read
Arrow, so parity runs through this Python-authored golden of decoded planes.

## Fuzz boundaries

`geo::fuzz` (deterministic in-crate LCG, no new crates; bounded to run in
seconds in debug) generates valid columns of all six kinds and both CRSs, then
mutates them: offset monotonicity and end offsets, NaN / infinity / out-of-range
coordinates, opened rings, holes moved outside the shell, shrunk limits, nulled
features that keep vertices, and hole-containment work-budget exhaustion.
Invariants: `from_descriptor` never panics and returns no column on `Err`
(it never touches the handle registry; the host suites below prove no handle is
published on error); an `Ok` column reads back bitwise, has a stable `canonical_metadata`
across two constructions, and `project_column` output is finite. A Hypothesis
suite (`tests/test_geo_property.py`, skipped without `hypothesis`) drives the
Python host with the same mutation classes and requires either a handle or a
`GeoNativeError` with status in `-1..-14`, never another exception and never a
handle on error. Host-level resource proofs use cheap adversarial offsets
(claimed child count disagreeing with the buffer) rather than allocating
budget-sized inputs; engine tests use `GeoLimits` overrides.

Python Arrow ingress requires exactly separated `Struct<x: f64, y: f64>`
coordinates and 32-bit List nesting matching the geometry kind. It rebases
sliced offset planes and slices the corresponding children at each level;
unreferenced child buffers do not enter the descriptor. Nested list/coordinate
nulls fail with `XYG_GEO_NULL_CHILD`, while top-level null points discard their
masked children. Non-object CRS metadata fails with `XYG_GEO_UNSUPPORTED_CRS`.
CRS authority codes use ASCII decimal digits; leading zeros are accepted without
unbounded integer conversion. Invalid UTF-8 extension names fail with
`XYG_GEO_TYPE_MISMATCH`, and invalid UTF-8 extension metadata fails with
`XYG_GEO_INVALID_ARGUMENT`. Unrelated Arrow field metadata remains opaque bytes
and does not affect geometry ingestion.
Node rejects fractional, negative, or overflowing offsets before u32 packing
and rejects excess nesting planes rather than narrowing or discarding them.
Native ingress applies the shared length/byte preflight before constructing
input slices or reading any geometry buffer.

## GeoViewport (camera / projection)

`crates/xyg-engine/src/geo_viewport.rs` defines the host-neutral camera:

| Field | Contract |
| --- | --- |
| `crs` | EPSG:4326 or EPSG:3857 for center/fit units |
| `center_x/y` | Lon/lat degrees or easting/northing metres, with Mercator polar clamp |
| `zoom` | `[0,24]`; world width = `512 * 2^zoom` CSS pixels |
| `width/height` | Positive finite CSS pixels that remain positive and finite as f32 |
| `bearing_deg` | Clockwise degrees normalized to `(-180,180]`; 0 = north up |
| `pitch_deg` | Ground-plane perspective in `[-60,60]` degrees |
| `world_wrap` | Short longitudinal edges and one coherent visible world copy per source part |

The flat-ground perspective camera follows MapLibre's default Mercator vertical
FOV (`0.6435011087932844` radians): camera distance `d = 1.5 * height`.
The reference equations and matrix order are independently specified in
[MapLibre's Mercator transform](https://github.com/maplibre/maplibre-gl-js/blob/379b3673a4f0982472ae91d774db5bd42931583d/src/geo/projection/mercator_transform.ts)
and [transform helper](https://github.com/maplibre/maplibre-gl-js/blob/379b3673a4f0982472ae91d774db5bd42931583d/src/geo/transform_helper.ts).
This profile has zero terrain elevation, roll and padding. Negative pitch is an
explicit symmetric extension; MapLibre's usual shell configuration uses
nonnegative pitch. Tile lifecycle and elevation-aware cameras belong to #49.

Lon/lat to Mercator uses spherical radius 6,378,137 metres and clamps latitude
to ±85.0511287798066 degrees (northing ±20,037,508.342789244 metres). The
bearing-rotated, camera-relative ground coordinates `(x,y)` use CSS world pixels
with y pointing south. With `W = d - y*sin(pitch)`, projection is
`(width/2 + d*x/W, height/2 + d*y*cos(pitch)/W)`. Inversion solves this same
perspective ground plane; it fails with `XYG_GEO_INVALID_ARGUMENT` beyond the
ground horizon. A point behind the near plane receives a finite offscreen
sentinel, and has no visible membership. Such a sentinel is not an invertible
projection. Projection/inverse goldens certify front-facing ground points.

Routes are clipped against linear ground-space viewport and depth half-planes
before perspective division. Near depth is `height/50`; the far ground envelope
is `d*cos(abs(pitch))/(cos(abs(pitch))-sin(abs(pitch))/3)*1.01`. This contains the
visible flat-ground footprint with the reference precision margin; it does not
claim MapLibre's terrain-aware far-plane value. All certified pitches keep the
viewport's ground footprint in front of the horizon. `bounds()` returns its
source-CRS bounding box; wrapped longitude intervals can extend beyond ±180.

Canonical data stays f64. Projected points, independent route segments and
closed polygon rings use f32 offsets from the f64 viewport-center CSS origin
(§4/§16). An arbitrary first, offscreen source vertex never becomes the origin.
Every narrowing is checked before publishing a cache, and no NaN reaches the
painter (§19). Golden tolerances are `1e-9` degrees, `1e-6` metres and `1e-6`
CSS pixels; native/WASM f32 cache comparisons allow `1e-4` pixels.

Camera transitions are Rust-owned and transactional. Setters validate a complete
candidate before publication. Fit and pan also validate the complete restored
camera before work; transport commands validate the initial snapshot before any
operation. Errors preserve all prior fields bitwise, including zero-pixel pan on
an invalid restored camera.
An admitted zero-pixel pan is inert. Positive pan x/y moves the camera toward
screen right/bottom using the current bearing and perspective inverse. Wrapped
centres cross the dateline continuously; non-wrapped centres stop at the world
boundary. Latitude/northing remain within the Mercator clamp. Fit chooses the
short wrapped span, resets bearing to zero, retains pitch and finds the largest
zoom fitting all four bounds corners within the requested CSS padding. If no
fit exists even at zoom zero it fails atomically.

`rebuild_key()` freezes CRS, wrap and every validated camera field as exact f64
identities, canonicalizing signed zero, equivalent wrapped ±180 centres and
full-turn bearings. Camera, source metadata digest and source geometry changes
invalidate `ProjectedGeoColumn.key`; caches are rebuildable. Projection,
inversion, lowering and identity entry points revalidate the complete camera.

`project_line_features` validates the descriptor before output allocation,
splits both CRS profiles at the world boundary, selects coherent endpoint
copies, clips in f64, then emits independent two-point segments carrying full
source u64 IDs. Empty/single-vertex ranges and wholly invisible segments emit
nothing. Dateline and clipped-away intervals cannot reconnect accidentally.
One copy is emitted even when a low-zoom viewport spans multiple worlds.

For Polygon/MultiPolygon, `project_column` additionally produces a closed-ring
cache (`ProjectedGeoPolygons`): offset f32 coordinates, ring-to-vertex offsets,
polygon-to-ring offsets, one source u64 ID per fragment, explicit ring roles
(`0` shell, `1` hole), and the f64 origin. A directed boundary graph intersects
source rings with the convex ground footprint and wrapped world strips. A
concave source intersection can produce multiple independent closed shells;
synthetic clipping boundaries cannot bridge disconnected fragments. Clipped
holes remain attached to their exterior fragment, including border contacts.
A viewport wholly inside a hole emits no filled-feature membership. Geometry
with a zero-area intersection is omitted; ambiguous coincident branching at a
clipping boundary fails with `XYG_GEO_INVALID_ARGUMENT` rather than publishing
incorrect topology. Boundary nodes are reconciled within `1e-7` camera-relative
ground pixels; canonical source coordinates and winding are never rewritten.

The existing outline cache retains only clipped source edges, rather than the
synthetic closing edges intended for filling. Point/outline XYGS lowering uses
the same perspective camera; polygon fill styling/painting is #49. Visible
membership is geometric: points require a center inside the viewport, routes
require a visible source segment, and polygons require positive shell-minus-
hole intersection area. Source-order IDs are deduplicated by value. Null
features contribute nothing; CSS visible bounds and source metadata digest
accompany the membership. This does not include mark diameter or stroke width
in membership calculations.

Admission uses `GeoLimits::default()` ceilings. Before any polygon outline or
topology allocation, a conservative `4096*vertices + 512*features` byte peak
must fit the 256 MiB engine ceiling; transport adapters also check their smaller
instance budget before canonical allocation. Ring graph edge/storage bounds
are checked before graph arrays, and shell/hole association work has a shared
4,000,000 edge-visit ceiling. Exceeding a ceiling fails with
`XYG_GEO_RESOURCE_LIMIT`, leaving prior host state and canonical source intact.
The short wrapped-ring convention spans at most one world, including EPSG:3857
periodic eastings; literal full-world edges remain full-world edges.

Rust fixtures cover reference perspective values, inverse/horizon behavior,
atomic pitched fit/pan/resize, poles, dateline shell/hole association in both
CRSs, two disjoint concave fragments, holes touching the viewport border,
viewport-inside-hole invisibility, deep-zoom 2.386-pixel separation, full u64
identity and allocation admission. The independent browser reference runner
`tests/browser/geo_viewport_maplibre_reference.mjs` compares native executable
and actual wasm32 projection/inverse/resize/bearing/pitch outputs with locally
supplied MapLibre 6.13.0 (blank style, no remote tiles). It freezes the actual
reference camera after shell constraints, compares wrapped longitude modulo
360 degrees, and applies the certified Mercator latitude clamp to reference
inverse/bounds outputs. Reference shell constraints near the pole may move the
centre after resize; the shell must forward its actual camera snapshot:

```sh
XYG_MAPLIBRE_DIST=/path/to/maplibre-gl-6.13.0/package/dist \
  CHROMIUM=/path/to/chromium \
  node tests/browser/geo_viewport_maplibre_reference.mjs
```

The stateless camera transport and host adapters are specified separately in
`spec/design/geo-viewport-protocol.md`. Optional browser shell events feed this
Rust camera; the shell does not own projected geographic scene geometry.

## Module and follow-ons

- Implementation: `crates/xyg-engine/src/geo.rs` (`GeoColumn`,
  `GeoDescriptor`, `GeoLimits`, canonical metadata, opaque handle registry).
- C ABI: `xyg_geo_column_new` / `_free` / `_len` / `_vertex_count` /
  `_geometry` / `_crs` / `_metadata` / `_plane_lens` / `_copy` in
  `crates/xyg-core` (ABI 379), generated into Python/Node ABI modules. Hosts
  decode GeoArrow and pass the typed descriptor buffers.
- Host wrappers: see "Host surfaces".
- Python GeoArrow adapter: `xyg._geoarrow.ingest_geoarrow` (optional pyarrow
  input format) flattens extension arrays into the typed descriptor and
  publishes a Rust `GeoColumn` handle.
- Producer conformance: `tests/test_geoarrow_graphforge_fixtures.py` consumes
  GraphForge's pinned IPC and Parquet fixtures directly and proves equivalent
  descriptor/Rust publication behavior without field renaming or row-wise
  WKB, WKT, or GeoJSON reconstruction.
- GeoViewport: `crates/xyg-engine/src/geo_viewport.rs` (camera foundation;
  perspective camera, closed polygon topology and `project_column` cache seam).
- Browser ingress: sequenced `XYGD` → `XYGM` through WASM ABI 28 and
  `XygWasmWorker.geoColumnIngest`; actual native/WASM goldens and stable errors
  in `packages/xy-node/test/geo-wasm-parity.test.mjs`, strict-CSP transfer and
  lifecycle proof in `scripts/geo_wasm_smoke.mjs`.
- Camera ingress: ABI 380/30 XYVC → XYVR provides transitions, footprint bounds,
  visible membership and closed polygon caches; actual native/WASM and MapLibre
  reference goldens are in the camera protocol tests.
- Next: geographic layer programs and fill tessellation (#49); LOD/export (#50).

## Related

- Parent epic: #39
- Upstream producer: GraphForge #797 (canonical GeoArrow spatial values)
- Dossier: §4/§16 (f64 vs f32), §19 (NaN never reaches GPU), §27 (rebuildable
  caches), §29 (typed buffers on the wire)

### Frozen cross-target derived Scene evidence (#47)

`geo_scene::compile_geo_scene` lowers a checked XYGD source and frozen XYGP
camera/style snapshot through the same GeoViewport projected cache into existing
XYGS Scatter/Polyline records. Source identities remain literal full u64 values.
Actual wasm32 and the bounded native `geo_scene_conformance` executable share
this product processor. The native/WASM parity suite checks all six geometry
kinds, holes/nulls, CRS, source precision, deep zoom, dateline splitting, limits
and failures; the packaged strict-CSP Worker proof exercises hydration, painted
pixels and GPU picking. This closes the derived Scene proof within the frozen
flat-ground perspective point/outline scope. The complete framing and allocation contract is
in [browser-wasm.md](browser-wasm.md#frozen-geographic-scene-ingress-wasm-abi-29-47).
Live camera transitions use XYVC/XYVR; geographic fills/layers remain #49.
