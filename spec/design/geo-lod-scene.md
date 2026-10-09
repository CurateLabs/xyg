# Geographic point tier Scene lowering (#50)

`geo_lod_scene` lowers the authoritative Rust `GeoPointResult` to ordinary
Scatter/Image Scene32 records. It does not count, filter, choose bins, sample
members or project source geometry. Direct records keep exact full-u64 feature
IDs and projected f64 positions. Reduced Scatter IDs are explicitly cell
ordinals; they are not representative source IDs. Picking must retain the
GeoLodKey and page exact membership through the geographic source processor.

The current lowering accepts a constant `GeoStyle`. Direct points preserve that
style; opacity is resolved once for fill and stroke. Per-row scalar/size/color,
hidden and interaction overlays require the retained-source style/state
attachment path; this function does not claim those channels are preserved.
Reduced tiers report dropped_channels=7 (diameter/symbol/stroke). Clusters use
circle glyphs with explicit count area interpolation from 6 to 24 CSS pixels
across [1,maximum count]. The color is viridis sampled at
ln(1+count)/ln(1+maximum count), with the declared opacity. Empty cells emit no
cluster record. Counts stay u64; these reductions invent no source feature.

Density is one top-first RGBA image with empty cells transparent and the same
count color rule. Its shape is the exact bounded LOD grid; the existing Scene
image shader performs presentation scaling. No second geographic painter is
added. Cluster and density ceilings remain those in geo-lod.md. Compilation
preflights record/style scratch and encoded output, rejects a budget above the
128 MiB consumer ceiling, and exposes no partial output on failure.

Tests cover maximum u64 identity, once-only fill/stroke alpha, cell IDs,
billion-count bounded glyphs, top-first density, deterministic Scene bytes and
resource failure. Native/WASM session execution, source style/state overlays,
aggregate picking/controller integration and scale evidence remain gates.
