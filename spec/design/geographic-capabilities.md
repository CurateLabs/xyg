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
Automatic multiscale spatial tiers, disk-backed massive sources, temporal
filtering and network-tile budgets remain #50. No production speedup or billion-
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
| [HoloViews](https://holoviews.org/user_guide/Interactive_Hover_for_Big_Data.html) / [hvPlot](https://hvplot.holoviz.org/en/docs/latest/user_guide/Geographic_Data.html) | Geographic ecosystem, large-data rasterization and selector hover | XYG preserves complete direct density contributors, but persistent aggregate membership queries and massive-source paging remain #50. |
| [pydeck](https://deckgl.readthedocs.io/en/latest/layer.html) / [deck.gl](https://deck.gl/docs/api-reference/layers/polygon-layer) | Multilayer GPU geographic rendering | Compare layer breadth and customization, source identity, local operation, startup/payload and interaction at identical data scales; no performance lead claimed here. |

Reproduction paths: `tests/test_geo_components.py`,
`packages/xy-node/test/geo-catalog-wasm-parity.test.mjs`,
`scripts/geo_catalog_wasm_smoke.mjs`,
`scripts/geo_controller_wasm_smoke.mjs`,
`tests/browser/geo_painter_test.mjs`, and
`tests/browser/external_gl_test.mjs`. Browser probes use packaged local assets
under strict CSP and reject every unexpected request.
