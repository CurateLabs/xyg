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
Retained sources add authenticated chunk paging, time-before-reduction, bounded direct/cluster/density tiers, exact opaque-cursor membership, explicit tile budgets and frozen exports (the companion contracts below). Original source rows now have bounded opaque-cursor pages including null, time-excluded and offscreen rows, with exact keyboard-focus identities. Spatial point indexes now have bounded native/WASM/browser evidence; paged point hierarchies and exact linked selected-state now have bounded Rust/native/WASM proofs; explicit selected hierarchy live routing now has bounded native notebook, Reflex and VS Code journeys. Automatic linked-input conformance remains #50. No production speedup or billion-
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
| Native retained host presentation | Canonical/indexed points, one mount, exact binary frame/pick/membership, explicit buffer ACK | Actual JupyterLab, production Reflex reconnect and VS Code remount/dispose; native staged camera/time updates retain accepted paint until exact retirement ACK |
| Retained browser ownership | ABI33 Worker, trusted frame preparation, admitted FIFO/framing credit | Actual five charts in one WebGL2 context, full-u64 pick, cancellation/read ACK, strict-CSP offline, context recovery |
| Explicit immutable point sidecar index | Rust XYIX/XYIP cross-chunk leaves, bounded canonical-order merge, authenticated import, explicit full-scan fallback | Exact canonical Scene parity through 1M; native/WASM frame+rows+frozen parity; browser corrupt-leaf recovery; 100M narrow grid16 0.79–1.23s, grid32 192–316ms under uncontrolled load; world flat-index latency remains a gap; the separate hierarchy evidence below covers bounded directory queries |
| Original source-row companion | Rust-issued continuation, all original rows, explicit temporal/null eligibility | Native/WASM byte parity; Python/Node paging after frame disposal; strict-CSP browser offscreen keyboard focus and failed-read recovery |
| Explicit raster/vector tiles | Local/network locator receipts, immutable producer generation/time, atomic epoch publication | Actual native mixed raster+vector+foreground; network is opt-in through caller loader, not automatic fetch |
| Frozen spatiotemporal output | XYGXv2 ordinary byte identity; selected-only XYGXv3 full sparse intent, profile, exact counts and mixed provenance | Native SVG/PNG/PDF/JPEG/WebP/static offline HTML; actual native/WASM selected snapshot and XYSE parity, offline selected pixels and attribution; imported metadata remains inert, WASM raster is explicit Unsupported |

Reproduce using `scripts/bench_geo_scale.py`, `tests/test_geo_retained.py`,
`tests/test_geo_rows.py`, `tests/test_geo_tiles.py`, `tests/test_geo_snapshot.py`,
`packages/xy-node/test/geo-scale-wasm-parity.test.mjs`, and
`scripts/geo_retained_wasm_smoke.mjs`. [Raw scale outputs](../performance/geo-scale-2026-10-08/README.md)
include environment, exact source patch and reproduction commands. These tests do
not establish linked selection, complete host accessibility journeys, GPU timing, or a competitor speed win. Separate live-host and hierarchy evidence below covers its stated routes and bounded fixtures.

[Spatial index raw evidence and limits](../performance/geo-index-2026-10-09/README.md) covers separate cold build and warm native queries; no competitor speed win or temporal index performance is inferred.

Separate [native host journey evidence](geographic-hosts.md) proves immutable
retained-points presentation and ownership in notebooks, Reflex and VS Code.
The additional journey evidence below covers native live camera/time updates, indexed remounts and explicit selected hierarchy live routing.

## Additional bounded M6 evidence

| Capability | Implemented contract | Evidence and remaining gate |
| --- | --- | --- |
| Selected retained/indexed points | Private issued Scope/consumed State; full u64 intent, deterministic selected cluster/density tint and exact Rows | [Selected hosts](geo-selected-hosts.md); native/WASM parity, five-view admission and failed-page/cancellation recovery. Pointer gestures do not yet issue linked state automatically. |
| Paged point/MultiPoint hierarchy | Authenticated external append pages, independent immutable frames, exact reduced membership | [Hierarchy trace](../performance/geo-hierarchy-2026-10-09/README.md); 100M Point world queries use directories with zero leaf reads and screen-bounded reduction. Native warm query timing excludes transfer/upload/browser paint; default-grid100M, 100M MultiPoint and1B remain gates. |
| Typed hierarchy hosts | Private source/transport authority, exact read/write ACK, retryable cleanup, independent Rows and static mount | [Host evidence](../performance/geo-hierarchy-hosts-2026-10-09/README.md); actual native/WASM byte pairs and cancellation controls. Static mounting preserves its hierarchy authority; the explicit selected live route is documented separately below. |
| Live camera and signed-time updates | XYGHv2 staged hydration/CAS/retirement; selected Scope remains caller-issued | [Actual host journeys](../performance/geo-live-host-journeys-2026-10-09/README.md); JupyterLab, production Reflex, real VS Code and five small native browser views. Massive interaction, playback UI and gesture-to-state mapping remain open. |
| Native pointer drag and wheel input | Trusted primary pointer and vertical wheel use Rust camera operations;16 ordered samples, exact camera/time/state revisions | [Bounded Chromium input proof](../performance/geo-live-pointer-2026-10-09/README.md); CSS scaling, programmatic ordering, Rust zoom limits, reader failure, overflow and captured close. Touch/pen, all wheel delta modes, cursor-centered zoom and massive latency remain unverified. |
| Recoverable selected State allocation | Opt-in nonce33, one charged private receipt per Scope, same-State replay and retired code20 | [Nonce evidence](../performance/geo-selected-state-nonce-2026-10-09/README.md); actual native/WASM lost-reply and capacity controls. Legacy sequence0 behavior is unchanged; uncertain35/36 admission remains open. |
| Selected hierarchy live hosts | Explicit caller-issued Scope and lane, nonce33 State capture, same-handle44 Data publication and XYGHv2 retirement | [Live hierarchy evidence](../performance/geo-selected-hierarchy-live-2026-10-09/README.md); actual JupyterLab, production Reflex reconnect, VS Code remount and five small native views after original Source disposal. Automatic linked selection, playback and mixed hierarchy routing remain open. |
| Temporal overview painter and frozen export | XYOVv1 exact source-domain signed-time counts, trusted existing painter lowering and inert XYGXv4 freeze | [Painter/export evidence](../performance/geo-overview-painter-snapshot-2026-10-09/README.md); actual Worker and borrowed-context pixels, six native formats, offline CSP and ordinary v2/selected v3 controls. Counts remain spatially nonfinal; this does not prove public composition or interactive host routing. |
| Temporal overview domain-cell membership engine | Private result/cell-bound continuation, time-before-geometry scan, exact FeatureRef and matched-vertex counts | [Engine evidence](../performance/geo-overview-membership-engine-2026-10-09/README.md); nine new Rust cases and unchanged legacy membership packets across native/WASM. The separate transport row below covers authenticated packets; the public adapter row below covers bounded original-row paging; massive interactive latency remains open. |
| Temporal overview domain-member transport | Distinct private Query/Data kinds, same-handle46 publication, exact read cookie/ACK and XYOMv1 source-row packets | [Protocol evidence](../performance/geo-overview-domain-members-2026-10-09/README.md); 15 full native/WASM packets across five time profiles. The public adapter row below covers Python/Node paging; the public recovery row below covers45. |
| Typed temporal overview composition | Private producer-bound Index/Query/Frame, density through existing geographic composition, independent frozen native export | [Owner evidence](../performance/geo-overview-source-2026-10-09/README.md); 25 Python and24 Node/native/WASM cases, six native output formats. The native live-host row below covers explicit mounts; the public recovery row below covers26–29. |
| Public temporal overview browser controller | Existing geographic chart factory, exclusive Data ownership, ordinary/borrowed Rust painter and32-row exact-count companion | [Browser evidence](../performance/geo-overview-browser-2026-10-09/README.md); strict-CSP actual Chromium, full integer identities, cancellation/ACK and old-paint controls. Counts remain spatially nonfinal; accepted-frame binary export and domain membership have separate bounded proofs below; massive five-view latency remains open. |
| Public temporal domain-member owners | Issued immutable XYOM pages, private cell/result continuation, exact callback/loan settlement | [Adapter evidence](../performance/geo-overview-members-hosts-2026-10-09/README.md); Python and Node/native/WASM physical-row paging after source/index/frame disposal, cancellation, publication pressure and cleanup retry. The public membership recovery row below covers45; generic lost MemberData10 remains guarded, with no final spatial selection or massive latency claim. |
| Accepted browser overview binary freeze | Accepted Data pin, publication barrier, captured Snapshot producer and independent inert XYGXv4 owner | [Binary evidence](../performance/geo-overview-browser-binary-2026-10-09/README.md); actual strict-CSP ordinary/borrowed painter journey, quotas, read/close settlement and genuine termination. Browser six-format export remains Unsupported; unknown snapshot6 allocation recovery remains guarded. |
| Opt-in retained allocation recovery engine | Exact captured nonce request, confirmation before replacement, retired-phase receipt and fixed charged bank | [Recovery evidence](../performance/geo-allocation-recovery-2026-10-09/README.md); six complete native/WASM packets, five-view sixteen-handle publication and lost allocation/Confirm controls. The public recovery row below covers26–29 adoption; the selected mutation engine row below covers opt-in35/36. |
| Public overview allocation recovery | Private exact26–29 nonce attempts, historical retirement acknowledgement, whole-owner continuation and canonical host inspection | [Recovery host evidence](../performance/geo-overview-recovery-hosts-2026-10-09/README.md);74 Node/native/WASM and49 Python cases plus actual strict-CSP Worker recovery. Closing waits initial and recovered publication; public packet edits cannot alter private host Scene authority. The membership recovery row below covers45;35/36 mutation and snapshot6 recovery remain separate gates. |
| Public domain-membership allocation recovery | Exact private45 replay and47 confirmation, whole-operation continuation, callback/loan settlement and per-flight Page handoff | [Recovery evidence](../performance/geo-overview-members-recovery-2026-10-09/README.md);118 Node/native/WASM and53 Python cases plus independent54-Python reproduction controls. Cancelling one waiter cannot dispose another caller's Page; all-cancelled cleanup rejects late joins. Generic lost MemberData10, final spatial selection and massive latency remain gates. |
| Native live overview hosts | Explicit composition host/widget route, independent private Data owner, shared Rust painter and exact XYGH CAS/retirement | [Host journeys](../performance/geo-native-overview-hosts-2026-10-09/README.md);26 Python/18 Node cases, independent9-Python/8-Node checks, strict-CSP Chromium, live JupyterLab, production Reflex reconnect and real VS Code remount/disposal. Exact temporal counts have a32-row companion; public metadata/budget edits cannot retag private authority. Default overview show remains static; final spatial refinement and massive/five-view performance remain open. |
| Selected mutation allocation recovery engine | Exact nonzero264-byte35/36 requests, Source-operation/selected-Query phase births,47 confirmation and bounded historical retirement | [Mutation evidence](../performance/geo-selected-mutation-recovery-2026-10-09/README.md);1477 Rust cases, ten focused cases,12 complete paired native/WASM packets and six unchanged legacy packets. Cancellation never disposes the caller Source; fallback preserves State. Public host adoption and selected19 publication recovery remain separate gates. |
| Geographic clipping at signed zero | Derived clipping topology canonicalizes zero while canonical source coordinates remain unchanged | [Clipping evidence](../performance/geo-clip-zero-2026-10-09/README.md); signed-zero square regression, viewport/geographic Rust tests and strict Clippy. This is correctness evidence, not scale timing. |

These rows refine the earlier evidence limits rather than claiming a competitor
speed win. Full five-view ingestion, transfer, upload, paint, picking and export
measurements across small through massive inputs remain #50/#39 acceptance gates.

[Selected frozen export evidence](../performance/geo-selected-snapshot-2026-10-09/README.md)
proves ordinary/mixed full intent and exact visible-count preservation after
source disposal. The [selected snapshot contract](geo-selected-snapshot.md)
distinguishes trusted freezing from imported structural consistency; this
small proof does not establish live linked hosts or massive export latency.
