# Geospatial data contract — GeoColumn, GeoArrow ingress, GeoViewport

**Status:** GeoColumn closure (#47: validation, canonical metadata, host
read-back, derived-cache seam; ABI 379) + GeoViewport camera foundation (#48).
MapLibre layers (#49) and LOD/export/scale (#50) build on these contracts.
The direct-browser WASM descriptor ingest (`XYGD` to `XYGM`) is the next slice
of #47 and is not shipped yet (see "Module and follow-ons").

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
touch its shell. Hole/hole overlap and edge crossings are not checked in v1. The
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
document every host (and, in the follow-on slice, WASM) must return
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
retained column into f32 scene inputs. It is an engine-level seam only in this
issue: no C ABI, host, or WASM projection export exists (that is #48/#49).

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
- Browser/WASM (#59): the same descriptor semantics through typed memory; the
  TypeScript painter never imports Arrow or reconstructs rows. Not shipped in
  this slice (see follow-ons).

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
Node rejects fractional, negative, or overflowing offsets before u32 packing
and rejects excess nesting planes rather than narrowing or discarding them.
Native ingress applies the shared length/byte preflight before constructing
input slices or reading any geometry buffer.

## GeoViewport (camera / projection)

`crates/xyg-engine/src/geo_viewport.rs` defines the host-neutral camera:

| Field | Contract |
| --- | --- |
| `crs` | Same certified profile: EPSG:4326 or EPSG:3857 for center/fit units |
| `center_x/y` | Lon/lat° or easting/northing m |
| `zoom` | MapLibre-style; world width = `512 * 2^zoom` CSS pixels |
| `width/height` | CSS pixels; must be > 0 |
| `bearing_deg` | Clockwise degrees; 0 = north up |
| `pitch_deg` | Degrees in `[-60, 60]`; stored for shell parity (orthographic project for now) |
| `world_wrap` | Prefer shorter longitudinal span across ±180° on fit |

Projection policy:

- Lon/lat ↔ Web Mercator uses spherical R = 6 378 137 m with polar clamp at
  ±85.0511287798066° / ±20 037 508.342789244 m.
- Screen mapping is CSS top-left origin. Bearing is a MapLibre-compatible
  clockwise camera heading, so positive bearing rotates map content by the
  opposite angle around center (`+90°` puts east at screen-top).
- Derived f32 screen buffers are **offset-encoded** from an f64 origin so deep
  zoom never drops source precision (§4/§16); NaN never reaches the buffer (§19).
- Documented golden tolerances: lon/lat `1e-9`°, mercator `1e-6` m, screen
  `1e-6` px (`geo_viewport::tolerances`).

Camera transitions are Rust-owned and transactional. `set_center`, `set_zoom`,
`resize`, `set_bearing`, and `set_pitch` validate a complete candidate before
publishing it; an error leaves the prior camera intact. Bearings normalize to
`(-180, 180]` at construction, updates, rebuild identity, and projection, so a
restored full-turn or extreme finite bearing cannot diverge from its canonical
camera or overflow trigonometric projection. `pan_by_pixels(dx, dy)` defines an ergonomic, host-neutral
gesture seam: positive X moves the camera centre toward screen-right and
positive Y toward screen-bottom, after applying the current bearing. Wrapped
EPSG:4326 cameras cross the dateline continuously; non-wrapped cameras stop at
the world boundary, and latitude/easting/northing stop at the certified Web
Mercator limits. A zero-pixel pan is bitwise inert.

`GeoViewport::rebuild_key()` freezes the complete validated camera as exact
IEEE-754 identities plus CRS and world-wrap state. It canonicalizes signed zero,
equivalent wrapped `-180/+180` centres, and full-turn bearings. Native/headless
hosts can therefore reuse or reject rebuildable painter buffers without JSON,
formatted floats, or host-local camera comparisons. Any meaningful resize,
zoom, centre, bearing, pitch, CRS, or wrap-policy change changes the key.
Projection, unprojection, painter lowering, and rebuild-key entry points
revalidate the complete camera first. A malformed restored/public-field camera
therefore fails closed before trigonometry, f32 emission, or cache identity.

The first geometry lowering slice is `GeoViewport::project_line_features`.
It accepts canonical interleaved f64 coordinates, Arrow-style offsets, and
u64 source feature IDs. Rust validates the complete descriptor before derived
output work, then splits EPSG:4326 routes at paired `+180/-180` endpoints when
world wrap is active, projects in f64, clips every segment to the CSS viewport,
and only then emits centre-offset f32 painter geometry. Output ranges are
independent two-point segments: a dateline or clipped-away interval can never
be reconnected accidentally. Each visible segment carries its original
feature ID; wholly invisible features emit neither geometry nor an ID. This
projection selects one coherent wrapped-world copy for both endpoints of each
segment, including when a `+180/-180` endpoint is opposite the camera centre;
the dateline split therefore cannot turn a short edge segment into a line
across the world. Consecutive source segments carry that selected copy across
their shared vertex. Empty and single-vertex feature ranges emit nothing.
Budget ceilings are the engine-owned `GeoLimits::default()` values in this
slice; callers cannot override them. Returned failures use
`XYG_GEO_OFFSET_MISMATCH`, `XYG_GEO_NON_FINITE_COORDINATE`,
`XYG_GEO_COORDINATE_OUT_OF_RANGE`, or `XYG_GEO_RESOURCE_LIMIT`. Each feature
is emitted in one wrapped-world copy even if a low-zoom viewport spans multiple
worlds. This is intentionally a line/route slice. Ring splitting and fill
topology remain required before polygon layers can claim the same contract.

Follow-ons on this camera: polygon antimeridian splitting and fill topology,
pitched frustum matching MapLibre, C ABI / host wrappers for the transition and
rebuild-key seams, and native↔WASM goldens (#59).

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
  `project_column` derived-cache seam; projection ABI/hosts next).
- Next: WASM descriptor ingest (packed `XYGD` request to `XYGM` output, native
  vs WASM parity; the rest of #47's Rust/WASM amendment, no TypeScript worker
  op until #49 consumes geometry); GeoViewport ABI + host ergonomics (#48
  follow-on); geographic layer programs and fill topology (#49); LOD/export
  (#50).

## Related

- Parent epic: #39
- Upstream producer: GraphForge #797 (canonical GeoArrow spatial values)
- Dossier: §4/§16 (f64 vs f32), §19 (NaN never reaches GPU), §27 (rebuildable
  caches), §29 (typed buffers on the wire)
