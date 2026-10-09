# Geographic raster and vector tile composition (#50)

Rust `geo_tile_scene` borrows validated RGBA tile payloads from a complete
`GeoTileCache::prepared_frame`. It uses the exact GeoViewport inverse at each
output pixel center, including bearing, pitch, world wrap and Mercator polar
bounds. It emits the existing top-first `SceneImage`; browser/Node/Python do
not reproject or resample tile pixels.

Sampling is explicitly nearest neighbour. Output dimensions are ceil(camera
CSS width/height), at most two million pixels. Missing/outside-world cells are
transparent; sources blend in configured source order using straight RGBA8
source-over with deterministic integer rounding. XYZ keys are canonical;
duplicate tiles or mixed source/time/style/generation revisions fail. Vector
payloads use the same shared geographic catalog composition path.

`compile_raster_frame` rejects a vector payload rather than silently omitting
it. It verifies the prepared camera against the catalog, reserves the entire
catalog budget in the shared process tile/derived ledger, warps the raster
background and calls `geo_layers::compile_with_background`. The ordinary
catalog compiler preserves the existing empty-background bytes and places one
basemap image below every analysis layer. Its caller-supplied literal image ID
must not alias an analysis layer ID. Image buffers, encoding and downstream
copies add five times RGBA capacity to catalog peak admission. Catalog budgets
above the 128 MiB source/query consumer ceiling are rejected on this path.

The returned `PreparedRasterScene` retains its process charge until its Scene
storage drops. The host stages painter buffers before committing the same
cache epoch; cancellation or failed compilation leaves the previous published
frame intact. Cancellation is checked on every raster row and before return.
No network request, filesystem access, URL choice or tile decode occurs here.

Tests cover north/top orientation, bearing, perspective ground sampling,
source-over alpha, transparent missing tiles, cancellation/resource/malformed
failures, unchanged ordinary Scene bytes and inherited embedded-image SVG.
Actual native/WASM protocol execution, vector composition, host staging,
attribution/frozen exports and performance evidence remain integration gates.

## Vector composition and certified geometry

`compile_tile_frame` accepts explicit constant `GeoVectorTileStyle` entries.
Validated same-geometry/CRS tiles of one layer are concatenated in prepared
frame order, retaining every literal feature ID and all outer geometry offsets.
Repeated IDs keep the catalog union behavior. Unknown or duplicate layer style
configurations and incompatible schemas reject the candidate. Vector basemap
layers precede analysis layers; an optional raster background precedes both.
The shared catalog enforces the ordinary 64-layer bound and style/ID policy.

Before clipping/tessellation, nonpoint vector columns use certified
`simplify_column` at the shared 0.5 CSS-pixel tolerance. The camera center is
converted by Rust to the canonical source CRS; bearing/pitch/world-wrap remain
exact. Materialization retains row/style/state alignment, holes and multipart
topology. Conservative fallback retains original vertex indices.

The complete catalog budget is leased before scratch allocation. Four times
raw column storage plus the sum of allocation-free simplification admissions
and128KiB metadata is deducted before the remaining compile/raster budget is
used. A tiny image still charges8192B+2048B per raster tile for lookup scratch.
Raster inverse rays remain unclamped so outside-world/polar rays are transparent;
horizontal wrapping is explicitly selected by the camera. The public clamped
GeoViewport inverse contract remains unchanged.
