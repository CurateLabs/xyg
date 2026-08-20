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
tests embed the same coordinate cases as descriptor goldens.

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
- Screen mapping is CSS top-left origin; bearing rotates in plane around center.
- Derived f32 screen buffers are **offset-encoded** from an f64 origin so deep
  zoom never drops source precision (§4/§16); NaN never reaches the buffer (§19).
- Documented golden tolerances: lon/lat `1e-9`°, mercator `1e-6` m, screen
  `1e-6` px (`geo_viewport::tolerances`).

Follow-ons on this camera: antimeridian line/polygon split for painted
geometry, pitched frustum matching MapLibre, C ABI / host wrappers, and
native↔WASM goldens (#59).

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
- GeoViewport: `crates/xyg-engine/src/geo_viewport.rs` (camera foundation;
  ABI/hosts next).
- Next: GeoViewport ABI + host ergonomics; WASM descriptor/viewport parity
  (#59); geographic layer programs (#49); LOD/export (#50).

## Related

- Parent epic: #39
- Upstream producer: GraphForge #797 (canonical GeoArrow spatial values)
- Dossier: §4/§16 (f64 vs f32), §19 (NaN never reaches GPU), §27 (rebuildable
  caches), §29 (typed buffers on the wire)
