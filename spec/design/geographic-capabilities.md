# Geographic capability matrix and comparison scope

The geographic composition catalog frames explicit RGBA8, CSS-pixel dimensions,
scalar domains, source-row state and full u64 identity. It does not accept the
ordinary mark API's arbitrary CSS color vocabulary. All geometry and state
policy is shared Rust; Python, Node and browser adapters only frame inputs.

| Capability | Rust Scene representation | Browser | Native SVG/PNG | Evidence |
| --- | --- | --- | --- | --- |
| Points and bubbles | Scatter, variable diameter/fill/stroke/symbol | Batched direct style planes | Shared Scene | Catalog/interaction unit tests; native/C-ABI/WASM catalog suite; actual GPU full-u64 picks |
| Routes and arcs | Explicit two-vertex Segment, bounded sampled Mercator arcs | Batched round-cap segments | Shared Scene | Native/C-ABI/WASM route/arc bytes; real GL DPR1/2 round-cap probes |
| Polygons and choropleths | Explicit Triangle, source-edge outlines | Batched triangles | Per-feature coverage union | Hole/concavity/overlap area fixtures; opaque/half-alpha shared-edge pixels; full-u64 metadata |
| Density | Top-first RGBA Image and complete source-row CSR | Existing texture program | Shared Scene | Exact image orientation/color pixels, mean-color and membership fixtures |
| Labels and legend | Rust-resolved Scene sidecars | DOM over owned or borrowed GL | Shared Scene text/legend | Literal-ID label fixtures; local MapLibre DOM and basemap preservation; public SVG/PNG export |
| Hover, focus, selection, brush | Bounded Rust index and state transitions | Worker events | Selection paint in compiled Scene | Duplicate-ID union, overlap order, hole/glyph/segment/density hit fixtures and seven event parity cases |
| Keyboard and companion access | Full valid nonhidden source identities | Rust focus transitions; 50-row paged DOM | Not an interactive static surface | Controller strict-CSP keyboard/offscreen-focus, camera continuity and three-page companion fixture |
| Optional MapLibre shell | Application-supplied context/camera lifecycle | Borrowed WebGL2, no second canvas | No shell needed | Local MapLibre6.13 framebuffer/state/callback/restore/lifecycle proof |

This is bounded direct catalog evidence. The explicit density family records
complete membership and reports its dropped diameter/symbol/stroke channels.
Retained sources add authenticated chunk paging, time-before-reduction, bounded direct/cluster/density tiers, exact opaque-cursor membership, explicit tile budgets and frozen exports (the companion contracts below). Original source rows now have bounded opaque-cursor pages including null, time-excluded and offscreen rows, with exact keyboard-focus identities. Spatial point indexes now have bounded native/WASM/browser evidence; aggregate pyramids, linked per-row state and all-host live conformance remain #50. No production speedup or billion-
row admission is inferred from these fixtures. Existing SVG glyph contours for
some uncommon symbols differ from the native/browser analytic painter; the
19-symbol hit fixtures prove the latter's pick policy, not complete vector
contour identity.

## Competitor reference points

These primary documentation references were checked on 2026-10-08. They define
concrete comparison work; they are not timed benchmark results or absence
claims about untested extensions.

| System | Relevant documented capability | XYG comparison and remaining gap |
| --- | --- | --- |
| [Matplotlib](https://matplotlib.org/stable/gallery/subplots_axes_and_figures/geo_demo.html) | Built-in geographic projections; wider Cartopy projection ecosystem | XYG uses certified flat Mercator cameras. Broader CRS/projection coverage remains a product gap. |
| [Seaborn](https://seaborn.pydata.org/tutorial/relational) | Scatter/line semantic color and size mappings | Compare authored geographic bubble area/color semantics alongside the Matplotlib integration ecosystem; no independent geospatial-support conclusion. |
| [Plotly](https://plotly.com/python/maps/) | Tile scatter and choropleth maps, MapLibre migration | XYG has a common full-ID Rust catalog and optional shell; equivalent public map examples and static output must remain reproducible. |
| [Bokeh](https://docs.bokeh.org/en/latest/docs/user_guide/topics/geo.html) | Web Mercator tile plotting and provider attribution | XYG receives an explicitly configured app shell; integrated tile configuration/budgets belong to #50. |
| [Altair](https://altair-viz.github.io/user_guide/marks/geoshape.html) | Geoshape marks and geographic projections | XYG covers polygon/choropleth authoring; broad projection vocabulary and declarative geographic transforms remain gaps. |
| [Datashader](https://datashader.org/user_guide/index.html) | Large spatial rasterization | XYG direct density does not establish massive-scale performance parity; bounded out-of-core and scale evidence remain #50. |
| [HoloViews](https://holoviews.org/user_guide/Interactive_Hover_for_Big_Data.html) / [hvPlot](https://hvplot.holoviz.org/en/docs/latest/user_guide/Geographic_Data.html) | Geographic ecosystem, large-data rasterization and selector hover | XYG preserves complete direct density contributors, but retained exact aggregate membership and chunk paging now have native/WASM proofs; interactive massive-source latency remains #50. |
| [pydeck](https://deckgl.readthedocs.io/en/latest/layer.html) / [deck.gl](https://deck.gl/docs/api-reference/layers/polygon-layer) | Multilayer GPU geographic rendering | Compare layer breadth and customization, source identity, local operation, startup/payload and interaction at identical data scales; no performance lead claimed here. |

Reproduction paths: `tests/test_geo_components.py`,
`packages/xy-node/test/geo-catalog-wasm-parity.test.mjs`,
`scripts/geo_catalog_wasm_smoke.mjs`,
`scripts/geo_controller_wasm_smoke.mjs`,
`tests/browser/geo_painter_test.mjs`, and
`tests/browser/external_gl_test.mjs`. Browser probes use packaged local assets
under strict CSP and reject every unexpected request.


## Retained-source and tile evidence

| Capability | Implemented contract | Bounded evidence and limit |
| --- | --- | --- |
| Authenticated retained point/MultiPoint | XYGK/XYGI, signed-i64 half-open filters, source/session leases | Actual 1k/100k/1M/10M/100M ingest/query; 1B planner-only |
| Automatic cluster/density and exact membership | Rust LOD counts, immutable rendered keys, opaque paged source-row cursor | 100M max observed RSS below44MiB; first Scene72.09s/pan45.54s remains a latency gap |
| Retained browser ownership | ABI33 Worker, trusted frame preparation, admitted FIFO/framing credit | Actual five charts in one WebGL2 context, full-u64 pick, cancellation/read ACK, strict-CSP offline, context recovery |
| Explicit immutable point sidecar index | Rust XYIX/XYIP cross-chunk leaves, bounded canonical-order merge, authenticated import, explicit full-scan fallback | Exact canonical Scene parity through 1M; native/WASM frame+rows+frozen parity; browser corrupt-leaf recovery; 100M narrow grid16 0.79–1.23s, grid32 192–316ms under uncontrolled load; world latency/pyramid remains open |
| Original source-row companion | Rust-issued continuation, all original rows, explicit temporal/null eligibility | Native/WASM byte parity; Python/Node paging after frame disposal; strict-CSP browser offscreen keyboard focus and failed-read recovery |
| Explicit raster/vector tiles | Local/network locator receipts, immutable producer generation/time, atomic epoch publication | Actual native mixed raster+vector+foreground; network is opt-in through caller loader, not automatic fetch |
| Frozen spatiotemporal output | XYGXv2 bound provenance, visible attribution, owned artifacts | Native SVG/PNG/PDF/JPEG/WebP/static offline HTML; WASM freeze matches native, raster export is explicit Unsupported |

Reproduce using `scripts/bench_geo_scale.py`, `tests/test_geo_retained.py`,
`tests/test_geo_rows.py`, `tests/test_geo_tiles.py`, `tests/test_geo_snapshot.py`,
`packages/xy-node/test/geo-scale-wasm-parity.test.mjs`, and
`scripts/geo_retained_wasm_smoke.mjs`. [Raw scale outputs](../performance/geo-scale-2026-10-08/README.md)
include environment, exact source patch and reproduction commands. These tests do
not establish Reflex/VS Code live retained-source parity, linked selection or complete host accessibility journeys, GPU timing, spatial-pyramid performance, or a competitor speed win.

[Spatial index raw evidence and limits](../performance/geo-index-2026-10-09/README.md) covers separate cold build and warm native queries; no competitor speed win or temporal index performance is inferred.
