# Geospatial data contract — GeoColumn and GeoArrow ingress

**Status:** foundation (issue #47). Locked ownership for geographic source
geometry. Projection/viewport (#48), MapLibre layers (#49), and
LOD/export/scale (#50) build on this contract.

## Product rule

Rust owns geographic source validation, CRS interpretation, retained f64
geometry, offsets, validity, feature identity, and resource limits. Hosts
(Python, Node, browser/WASM) decode Arrow / GeoArrow at their boundary and
forward a **typed descriptor** — never a second geometry engine, never
GeoJSON row expansion on the product path, and never an Arrow dependency
inside `xyg-engine`.

MapLibre (optional browser shell) never becomes the authority for feature
geometry, identity, styling, picking, or LOD. See #39 / #49 for the shell
boundary.

## Certified profile (v1)

| Concern | Contract |
| --- | --- |
| Geometry kinds | Homogeneous `point`, `linestring`, `polygon`, `multipoint`, `multilinestring`, `multipolygon` |
| Coordinates | Separated GeoArrow XY as interleaved host `f64` (`[x0,y0,x1,y1,…]`) |
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

## Module and follow-ons

- Implementation: `crates/xyg-engine/src/geo.rs` (`GeoColumn`,
  `GeoDescriptor`, opaque handle registry).
- C ABI (v71+): `xyg_geo_column_new` / `_free` / `_len` / `_vertex_count` /
  `_geometry` / `_crs` in `crates/xyg-core`, generated into Python/Node ABI
  modules. Hosts decode GeoArrow and pass the typed descriptor buffers.
- Next: ergonomic Python/Node wrappers over the generated ABI; WASM
  descriptor parity (#59); headless GeoViewport (#48); geographic layer
  programs (#49); LOD/export (#50).

## Related

- Parent epic: #39
- Upstream producer: GraphForge #797 (canonical GeoArrow spatial values)
- Dossier: §4/§16 (f64 vs f32), §19 (NaN never reaches GPU), §27 (rebuildable
  caches), §29 (typed buffers on the wire)
