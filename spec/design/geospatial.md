# Geospatial data contract — GeoColumn, GeoArrow ingress, GeoViewport

**Status:** GeoColumn foundation (#47) + GeoViewport camera foundation (#48).
MapLibre layers (#49) and LOD/export/scale (#50) build on these contracts.

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
| Nullability | Top-level per-feature validity (`0`/`1`); nested parts cannot be null |
| Precision | Canonical geometry stays f64; derived f32 scene buffers are rebuildable caches (§27) |
| Identity | Optional host feature IDs; otherwise dense `0..n` |
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
4. Nested `u32` offset planes by geometry depth:

| Kind | `offsets0` | `offsets1` | `offsets2` |
| --- | --- | --- | --- |
| Point | (empty; one vertex per present feature) | — | — |
| LineString / MultiPoint | feature → vertex | — | — |
| Polygon / MultiLineString | feature → ring/line | ring/line → vertex | — |
| MultiPolygon | feature → polygon | polygon → ring | ring → vertex |

Offset planes are Arrow-List compatible: length `n + 1`, monotonic,
`offsets[0] == 0`, last entry equals the child count. Polygon rings must
contain at least four vertices and close with bitwise-identical endpoints.

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

Before a `GeoColumn` is published, Rust rejects:

- unsupported CRS;
- odd-length `xy`, validity flags outside `{0,1}`, or ID length mismatch;
- offset planes that disagree with geometry depth or vertex counts;
- non-finite coordinates;
- coordinates outside CRS bounds (WGS84 lon ∈ [-180,180], lat ∈ [-90,90];
  Web Mercator ±20_037_508.342_789_244);
- open or short polygon rings;
- feature / vertex / byte budgets (`GeoLimits`, defaults 1e6 features /
  1e7 vertices / 256 MiB).

Failures are atomic: no partial column is retained.

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
  `GeoDescriptor`, opaque handle registry).
- C ABI (v72+): `xyg_geo_column_new` / `_free` / `_len` / `_vertex_count` /
  `_geometry` / `_crs` in `crates/xyg-core`, generated into Python/Node ABI
  modules. Hosts decode GeoArrow and pass the typed descriptor buffers.
- Host wrappers: `xyg._native.geo_column_*` and Node `geoColumnNew` /
  `geoColumnMeta` / `geoColumnFree` over the generated ABI.
- Python GeoArrow adapter: `xyg._geoarrow.ingest_geoarrow` (optional pyarrow
  input format) flattens extension arrays into the typed descriptor and
  publishes a Rust `GeoColumn` handle.
- Producer conformance: `tests/test_geoarrow_graphforge_fixtures.py` consumes
  GraphForge's pinned IPC and Parquet fixtures directly and proves equivalent
  descriptor/Rust publication behavior without field renaming or row-wise
  WKB, WKT, or GeoJSON reconstruction.
- GeoViewport: `crates/xyg-engine/src/geo_viewport.rs` (camera foundation;
  ABI/hosts next).
- Next: GeoViewport ABI + host ergonomics; WASM descriptor/viewport parity
  (#59); geographic layer programs (#49); LOD/export (#50).

## Related

- Parent epic: #39
- Upstream producer: GraphForge #797 (canonical GeoArrow spatial values)
- Dossier: §4/§16 (f64 vs f32), §19 (NaN never reaches GPU), §27 (rebuildable
  caches), §29 (typed buffers on the wire)
