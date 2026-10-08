# Geographic layer programs (#49)

Status: implementation in progress. The bounded fill processor and borrowed
WebGL surface are internal building blocks; the geographic composition API,
complete catalog and interaction contract are not yet shipped.

## Ownership and reuse

Rust consumes retained GeoColumn data and the explicit GeoViewport, resolves
styles, projects/clips/tessellates, constructs canonical Scenes, and preserves
source feature identity and reduced-tier membership. TypeScript frames typed
inputs and paints the existing Scene programs. MapLibre is an optional,
app-supplied camera/basemap shell. The default package imports no MapLibre,
provider, token, remote asset or tile service.

The intended catalog is point/bubble, route, arc, polygon/multipolygon,
choropleth, density, label and legend programs. They reuse ordinary Scene
Scatter, Polyline, PolyFill and Image records and existing label/legend
sidecars; a separate geographic painter or host projection is not permitted.
Python entry points remain in the composition surface and Node/browser hosts
must use the same Rust processor.

## Direct polygon fill admission

`crates/xyg-engine/src/geo_fill.rs` tessellates a closed screen-space shell
and its closed hole caches. Source f64 geometry and winding remain unchanged.
Horizontal slabs between vertex ordinates have constant edge order; shell
parity minus the union of hole intervals becomes bounded triangle records.
Ring orientation does not select fill semantics. Concave notches, touching
holes and overlapping hole intervals remain empty where appropriate.

An edge-order reversal inside a slab fails with `XYG_GEO_INVALID_ARGUMENT`
rather than emitting a fill for an unrecorded intersection. Open rings,
non-finite coordinates and painter-unrepresentable coordinate magnitudes
fail explicitly. A returned failure exposes no partial triangle output.

The direct processor admits at most 4,096 edges, 1,000,000 edge/slab visits
and 65,536 triangles. Exceeding a ceiling is `XYG_GEO_RESOURCE_LIMIT`. These
are direct tessellation limits, separate from GeoColumn source admission;
screen-bounded simplification and reduced spatial tiers belong to #50.
Tests independently pin filled area for holes, concavity and overlapping
hole intervals, and exercise malformed/resource/self-intersection failures.

## Shell boundary

A custom layer uses MapLibre's supplied WebGL2 context and current framebuffer.
XYG must preserve the basemap, GL state and shell scheduling through setup,
upload, paint, pick, error and disposal. It must not create another WebGL
context, clear the basemap or lose/resize the borrowed surface. Camera events
return to the Rust processor; MapLibre never draws XYG analysis features.

Reference: [MapLibre CustomLayerInterface](https://maplibre.org/maplibre-gl-js/docs/API/interfaces/CustomLayerInterface/).
The pinned shell conformance fixture uses locally packaged MapLibre 6.13.0,
with network access disabled and explicit CSP worker assets.

Complete catalog, interaction, keyboard/companion access, context recovery,
style precedence and attribution proofs remain the #49 close gate. This
document must be updated alongside their implementation.
