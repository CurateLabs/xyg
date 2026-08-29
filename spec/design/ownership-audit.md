# Source ownership audit

<!-- xyg-ownership-schema: 1 -->

**Status:** enforced architecture contract. Machine-readable twin: [`ownership-audit.json`](ownership-audit.json). Tracking issue: [#56](https://github.com/CurateLabs/xyg/issues/56).

This ledger answers ownership file by file without treating language percentages as a quality target. Rust owns row scans and every parity-affecting decision. Python and Node own host ergonomics. TypeScript owns browser painting and interaction. Files marked for migration remain supported, but must not gain new canonical policy while their named issue is open.

The verifier inventories tracked source only. Tests, examples, benchmarks, generated bundles, dependencies, vendor trees, and untracked local files are deliberately outside this production-source ledger.

Migration status: Scene v25 now moves canonical viewport/plot bounds, numeric
axis transforms, chart/plot backgrounds, authored axis side and visibility,
explicit major/minor tick geometry and paint, bounded primary static legend
entry order/placement/frame/text/swatch policy, bounded semantic graph label
collision/truncation/final screen geometry and source identity, default numeric
tick/label/grid/spine chrome, clipping visibility, and scatter/polyline/rectangle record
encoding plus Band `None`/`Top`/`Perimeter` outline topology into
`crates/xyg-engine/src/scene.rs`. `python/xyg/_native.py` and
`packages/xy-node/src/scene.js` only coerce typed arrays and call the generated
batch ABI. Their remaining migration classification covers figure-to-record
assembly, additional mark families, and legacy static-export consumers. ABI 84
also makes Rust authoritative for the ordered, stable failure reason attached
to deferred authored Scene features; hosts only pack the versioned presence mask.
Rust also owns bounded multiline/wrapped annotation line breaking, line count,
and screen-space box/leader bounds; public hosts only pack literal inputs and
reject markup, CSS/classes, custom fonts, and collision policy. Rust also owns
whether resolved Cartesian Scene chrome produces SVG/raster
primitives. Host paint alpha is data, not an implicit polar-mode signal; polar
Scene compile is explicit XYPL v1. Scene v26 owns polar line/scatter/area/bar/column
projection and annular-sector tessellation, polar errorbar and contour polylines, polar heatmap
lattice tessellation, ABI 192 polar painted heatmap Image blit, ABI 193 heatmap/hexbin stroke_opacity, ABI 194 polar hexbin / custom reducers / categorical direct_rgba, ABI 195 triangle-mesh custom role / per-item face intern, ABI 196 scatter per-item fill/stroke/width/opacity intern, clip, rings/spokes, and rim tick labels in `scene.rs` + `polar.rs`.
Python `_PolarProjection` remains a thin packer plus wedge/ring/polygon helpers
for the compatibility exporters. ABI 143 polar density tessellates occupied
`DensityBlit` cells to PolyFill wedges. ABI 97 also makes Rust authoritative for bounded solid-ribbon Scene geometry:
Python and Node pack two adjacent compact endpoint rows, while Rust transforms
the endpoints through the selected Cartesian axes and expands the fixed
96-interval cubic into ordinary Scene v25 Band samples. Host-local ribbon
polygon helpers remain compatibility-renderer code, not canonical Scene policy.
The public constant built-in marker slice admits all 19 fixed symbol codes and
an optional literal constant CSS stroke with a finite non-negative scalar
width. Python and Node preserve the constant fill and stroke paint in the Scene
style table and normalize stroke-only authoring to 1px. Rust owns implicit 1px line-only width,
symbol paths, stroke-inclusive extent clipping, legend swatches, and
SVG/raster/browser lowering. Width-only match-fill, per-item stroke/width,
custom paths/glyphs, and density/LOD scatter remain compatibility routes.
The public literal triangle-mesh slice admits at most 1,024 unjoined faces with
constant or interned per-face fill/stroke/width (ABI 195; custom `role` is
identity metadata). Public scatter admits interned per-item fill/stroke/width/
opacity (ABI 196; per-item size/symbol stay fail-closed). Python and Node pack six authored
vertex columns as three-row PolyFill runs; Rust owns their stable-run grouping,
plot clipping, legend swatch, SVG/raster/browser lowering, and the public
PolyFill group budget (companion traces share the 1,024-group ceiling).
`joined_fill` plus per-face paint, alternate axes, polar meshes, and
larger meshes remain compatibility behavior.

ABI 98 removes composition-violin geometry policy from both hosts. They retain
coercion, group/category factorization, rollback, and literal style authoring,
then pack flat f64 samples, monotone offsets, centers, bins, width, and
orientation. Rust alone filters samples, skips empty groups, computes and
normalizes density, applies width/orientation, validates the 10,000-Rect bound,
and emits final coordinates. Public constant-style primary Cartesian violins
use the existing Scene consumers; pyplot KDE bodies and advanced variants stay
on their explicit compatibility paths.

Exact composition ECDF sorting, duplicate coalescing, and cumulative
normalization now use `xyg_weighted_ecdf` in both Python and Node. Python also
passes raw f64 values through Rust's finite filtering, while Node retains its
equivalent finite-value coercion seam.
The hosts retain validation/error wording, the right-continuous zero anchor,
and literal Step style packing; Rust expands that Step for the shared Scene
consumers. ABI 100 also moves binned ECDF finite filtering, automatic domain
(including 5% absolute-value widening for nonzero constants and a 0.5 fallback
at zero or for a non-useful pad), the 10,000-bin ceiling, uniform
counting, cumulative normalization, empty-bin compaction, right-edge placement,
and zero anchor into `xyg_binned_ecdf`. Node retains its optional authored
range and denominator contract; Python adds no public range option. Hosts keep
coercion, stable validation wording, literal style/axis/id packing, and the
existing Step Scene route.

Omitted-bin composition histogram edges now use Rust's NumPy-compatible auto
estimator in both Python and Node instead of Node silently selecting ten bins.
ABI 101 `xyg_histogram_bins` then owns authored-edge validation, closed-last-bin
assignment, density normalization, and cumulative assembly for every composition
histogram path. Hosts retain coercion, explicit integer-bin validation, literal
style packing, and the historical all-nonfinite ten-bin compatibility case;
Rust owns the ordinary adaptive edge count, irregular counting, density, and
cumulative heights. The resulting bounded Histogram Rects already route public
SVG/PNG/PDF and browser paint through the canonical Scene. Rust rejects
automatic or authored results above 10,000 bins, and each thin binding uses one
10,001-edge ABI scratch plane.
ABI 102 moves composition-hexbin finite-pair filtering, automatic domain
(including the shared 5% absolute-value widening for nonzero constants and a
0.5 fallback at zero or for a non-useful pad), and the matplotlib
`int(width / √3)` default grid height into `xyg_hexbin` /
`xyg_hexbin_ingress`. Python and Node pack raw f64 columns, an optional
authored rectangle, and either a scalar width or an explicit `(width, height)`;
they no longer scan finite pairs, pad degenerate extents, or choose the
default height (`Math.round` on Node was the host drift). Custom Python
`reduce_C_function` paths still reduce groups on the host after Rust resolves
the lattice. Public traces remain centers-only on the wire. ABI 103 moves
constant-style Cartesian hex-cell ring expansion and regular heatmap lattice
reconstruction into `expand_scene_records` (`HexCell=5`, `HeatmapLattice=6`).
Python and Node pack one compact center+pitch row per hex cell and a two-row
extent+shape heatmap lattice; Rust emits the same Scene v25 PolyFill rings and
Rects the retired host packers produced. ABI 134 adds `HeatmapPainted=9` and
XYHP paint planes (RGBA8 image-top-first or scalar values + RGB stops + domain)
on the Scene extras pointer (XYEX when polar XYPL is also present). Hosts pack
the compact lattice plus paint; Rust tessellates cells and interns unique fills.
ABI 104 moves disconnected endpoint
pairs and unjoined triangle faces into the same compact expansion
(`SegmentPair=7`, `TriangleFace=8`): hosts pack one four-coordinate Polyline
row per segment and two PolyFill rows per face. ABI 105 moves
`scene_export_support_reason` allowlists, check order, and diagnostic wording
into `crates/xyg-engine/src/scene_export.rs`. Python and Node pack `XYEF` v1
facts; ABI 152 owns `XYEP` layout and flag derivation, then the predicate
allowlists run over that envelope. They still compile the Scene
so encoder and router cannot disagree. ABI 106 moves Figure autorange, default
3% margin, log-positive extents, polar theta/radial defaults, reverse,
degenerate widening, `_auto_domain`, and zero-baseline pinning into
`crates/xyg-engine/src/autorange.rs`. Python and Node pack an `XYAR` v1 envelope
of axis options, zone extents, and rectangle zero-baseline predicates; they no
longer apply host-local padding (Node's former 5% pad). Direct-browser WASM
compile uses the same `auto_domain` degenerate pad. ABI 107 moves Scene
CSS→RGBA8 conversion and per-kind mark fill/stroke/width defaults into
`crates/xyg-engine/src/scene_style.rs` (plus `css::color_rgba8`). Python and
Node pack an `XYMS` v1 envelope of kind, opacities, authored CSS strings, and
width fields; named colors, `none`, line-only scatter stroke, band `line_color`,
and the never-invisible fallback cannot drift. ABI 108 moves the 200-byte
Scene chrome style input into the same module: Python and Node pack an
`XYCH` v1 envelope of background CSS, per-axis sides, paint flags, opacities,
widths, and CSS strings; default RGBA/widths and `grid_opacity` scaling of
the default grid color cannot drift. ABI 109 moves Figure→Scene row
packing into `crates/xyg-engine/src/scene_pack.rs`. Python and Node pass
kind, flags, step mode, style ref, trace id, diameter/symbol, extras, and
literal f64 columns; record kinds, stable-id splitting, expansion-mode
assignment, ribbon/triangle doubling, heatmap lattice framing, and
finite-coordinate rejection cannot drift. ABI 116 expands primary
rule/band/marker annotations into ordinary Scene polyline/rect/scatter
rows from packed scalars plus axis domains; hosts only coerce kind, axis,
style ref, index, and authored numbers. ABI 117 moves figure-compile
support into `crates/xyg-engine/src/scene_export.rs`. Python and Node pack
an `XYFS` v1 envelope of observations plus axis ids/keys; feature mapping,
the primary x/y axis set, and the Scene axis-key allowlist cannot drift.
ABI 118 extends that envelope to `XYFS` v2 per-trace allowlist flags so
unsupported kinds, hidden/per-item styles, density, dash/curve/markers,
rect extras, joined fills, custom hex reducers, heatmap colormaps, and
non-CSS fills cannot drift either. v1 envelopes remain accepted.
ABI 110 moves primary XYLG
legend framing into `crates/xyg-engine/src/scene_legend.rs`. Python and
Node pass loc/flags, font sizes, paints, title, and per-entry meta plus
labels; header layout, text offsets, and bounded-text rejection cannot
drift. ABI 111 moves primary XYCB colorbar framing into
`crates/xyg-engine/src/scene_colorbar.rs`. Python and Node pass domain,
stops, ticks, title, and text RGBA; header layout, stop/tick tables,
domain-span checks, and bounded-text rejection cannot drift. ABI 112
moves primary XYAD annotation framing into
`crates/xyg-engine/src/scene_annotations.rs`. Python and Node pass typed
row meta plus concatenated labels; XYAT/XYAL/XYAR/XYAC/XYAW table layout,
version selection, the XYAD envelope, and bounded-text rejection cannot
drift. ABI 113 moves closed-subset SVG→PDF into
`crates/xyg-engine/src/pdf.rs`. Python and Node pass UTF-8 SVG; path
lowering, Helvetica metrics, ExtGState/shading/image embedding, and
deterministic object numbering cannot drift. ABI 114 moves baseline JPEG
and lossless WebP encode into `crates/xyg-engine/src/jpeg.rs` and
`crates/xyg-engine/src/webp.rs`. Hosts coerce packed RGB/RGBA8 pixels;
YCbCr 4:4:4 / VP8L simple-lossless packing cannot drift. ABI 115 moves
filter-0 PNG encode into `crates/xyg-engine/src/png_encode.rs`. Hosts
coerce packed RGB/RGBA8 pixels and a compression level; indexed-palette
selection, `tRNS`, and zlib IDAT cannot drift. ABI 194 admits polar hexbin,
custom `reduce_C_function` (host-reduced after `xyg_hexbin_groups`), and
categorical / `direct_rgba` 1×N XYHP RGBA onto HexCell PolyFills. ABI 195 admits triangle-mesh custom `role` and per-item fill/stroke/width interned from packed XYHP kind 6. ABI 196 intern scatter per-item fill/stroke/width/opacity from packed XYHP kind 7. LOD over the 1,024-group painter
budget, and rich style exceptions stay on the compatibility exporters.
Scene 25 is unchanged. Polar density tessellates on Scene (ABI 143). LOD over the 10,000-Rect histogram ceiling,
and rich style exceptions stay on the compatibility exporters. Polar heatmap
Scene tessellates constant-style lattice Rects to PolyFill wedges; ABI 192
polar painted heatmap inverse-rasters to one plot-covering Image blit.
ABI 193 admits heatmap/hexbin `stroke` / `stroke_width` / `stroke_opacity`; polar
painted Image blit tessellates when stroke is visible.
ABI 194 admits polar hexbin, custom host reducers, and categorical / `direct_rgba`
hexbin as interned HexCell PolyFills.
ABI 195 admits triangle-mesh custom `role` and per-item fill/stroke/width interned
from packed XYHP kind 6 (`joined_fill` plus per-face paint stays fail-closed).
ABI 196 intern scatter per-item fill/stroke/width/opacity from packed XYHP kind 7
(per-item size/symbol stay fail-closed).
Polar contour compiles as SegmentPair polylines. ABI 134
`HeatmapPainted` moves Cartesian/polar scalar colormap and truecolor intern into
Rust: hosts pack XYHP, Rust emits per-cell Rect fills.
ABI 99 likewise removes grouped composition-box statistics and geometry policy
from both hosts. Python and Node pack canonical values, offsets, centers,
orientation, width, visibility, and literal styles; Rust owns finite filtering,
Tukey statistics, stable group ordering, body/whisker/cap/median geometry,
deterministic bounded outlier placement, and the 10,000-record cap. Supported
constant-style primary-Cartesian boxes now use the existing Rect, Polyline, and
Scatter Scene consumers for public SVG/PNG/PDF; alternate-axis, polar,
gradient, and per-item-style cases remain explicit compatibility paths.

The post-M2 retirement pass removes two obsolete Python adapter layers without
widening that compatibility boundary. `_svg.axis_ticks` now maps every
automatic linear/log/category/angular/time/symlog family directly to
`_native.scene_axis_ticks`; the former per-family wrappers are gone. Rust
`scene::{linear_ticks, log_ticks, category_ticks, angular_ticks, time_ticks}`
remains the only ladder implementation, exposed to Node by `axisTicks` and to
Python/pyplot/SVG/raster by the generated C ABI. The duplicate
`try_public_svg` / `try_public_png` / `try_public_pdf` selectors are also gone:
`public_static_export` is the only optional product-route selector, while
`figure_scene`, `figure_svg`, and `figure_raster_commands` remain explicit
Scene consumers. `_svg.py`, `_raster.py`, and `_scene_v3.py` stay in the
migration class because the compatibility and figure-to-record assembly debt
listed below still exists.

### Post-M2 Python retirement inventory

| Candidate | Rust replacement and product call path | Coverage | Disposition |
| --- | --- | --- | --- |
| `_svg._linear_ticks`, `_log_ticks`, `_category_ticks`, `_angular_ticks`, `_time_ticks` | `crates/xyg-engine/src/scene.rs` owns all ladders; `xyg_scene_axis_ticks` exposes them through `crates/xyg-core/src/lib.rs`; Python SVG/raster/pyplot call `_native.scene_axis_ticks` through `_svg.axis_ticks`, and Node calls `axisTicks` in `packages/xy-node/src/scene.js` | Rust Scene tick unit tests, `tests/test_scene_ir.py`, and `packages/xy-node/test/scene.test.mjs` | **removed** |
| `_scene_v3.try_public_svg`, `try_public_png`, `try_public_pdf` | Rust `SceneDocument` owns SVG/raster/painter lowering; `Figure.to_svg` and `export._native_image` use the one `public_static_export` selector, while Node uses `sceneSvg` / `sceneRasterCommands` | `tests/test_figure_scene_v3.py`, `tests/test_scene_export_support.py`, and `scripts/bench_public_scene_routes.py` exercise the product selector and exact Rust consumers | **removed** |
| `_svg.py`, `_raster.py`, `_scene.py` compatibility rendering | Scene static custom fonts/CSS/classes are the bounded fail-closed contract `XYG_SCENE_UNSUPPORTED_CUSTOM_FONT` / `XYG_SCENE_UNSUPPORTED_BROWSER_CSS` (#288; DejaVu Sans only; default-font figures must not fall back to `_svg.to_svg` / `_raster`). Remaining compatibility debt is unresolved/browser-only gradients (`var()` / theme CSS are the bounded fail-closed contract `XYG_SCENE_UNSUPPORTED_GRADIENT` (#289)), and the rich style/text exceptions below. ABI 137 owns Cartesian constant-style density as one Scene Image blit (`DensityBlit` + XYHP kind 3 + XYIM); ABI 142 owns cartesian mean-color density on that same blit (XYHP kind 4, LOD doc §2 physical alpha); ABI 143 polar density tessellates occupied `DensityBlit` cells to PolyFill wedges (no XYIM). ABI 138 owns constant dash polylines (XYDS extras + sidecar); ABI 139 owns constant non-round linecaps (XYLC extras + sidecar); ABI 140 owns cartesian `curve="smooth"` polyline flatten (`CurveFlatten=11`); ABI 141 owns cartesian `area(curve="smooth")` Band flatten (`BandFlatten=12`); ABI 144 owns cartesian `error_band(curve="smooth")` on that same `BandFlatten` mapping and polar `curve="smooth"` line/area/error_band as identity chords (polar-axes.md §5); ABI 145 owns constant scatter `marker_path` (XYMP extras tessellated to PolyFill/Polyline after pixel mapping); ABI 146 owns constant mark `fill` linear-gradients (XYGR extras kept on encoded Scene; SVG `<linearGradient>` / raster `OP_FILL_POLY_GRAD`); ABI 166 owns cartesian bar/column/histogram `corner_radius` tessellation (`rounded_rect_poly` after pixel mapping); ABI 167 owns polar bar/column/histogram `wedge_gap` (`polar_wedge_points` constant-px inset); ABI 168 owns polar bar/column/histogram `corner_radius` (rounded-wedge tessellation when inner > 0); ABI 169 owns polar `curve="smooth"` plus `step` as polar step expansion (identity chords); ABI 170 owns constant scatter `marker_glyph` (XYMG extras kept on encoded Scene; SVG `<text>` / raster `OP_TEXT`); ABI 191 admits multi-character UTF-8 (XYMG v2, max 64 bytes); combined `marker_path` + `marker_glyph` stays fail-closed. ABI 192 owns polar painted heatmap inverse-raster as one Scene Image blit (Image+XYPL); constant-style polar lattices still tessellate. ABI 171 owns width-only scatter `stroke_width` as match-fill (mark color at the authored width); ABI 172 owns cartesian line `curve="smooth"` plus `step` as authored step expansion; ABI 173 owns heatmap `corner_radius` tessellation (cartesian rounded Rects / polar wedges); ABI 174 owns violin/box `corner_radius` tessellation on that same Rect path; ABI 175 owns violin/box `fill_opacity` / `stroke_opacity` on XYMS; ABI 176 owns bar/column/histogram `fill_opacity` / `stroke_opacity` on that same XYMS path; ABI 177 owns heatmap `fill_opacity` on that same XYMS fill alpha; ABI 178 owns scatter `fill_opacity` / `stroke_opacity` on that same XYMS path; ABI 179 owns hexbin `fill_opacity` on that same XYMS fill alpha; ABI 180 owns triangle_mesh `fill_opacity` / constant stroke paint on that same XYMS path; ABI 181 owns cartesian area/error_band `curve="smooth"` plus `step` as authored band step expansion; ABI 182 owns triangle_mesh `joined_fill` as one identity PolyFill ring; ABI 183 owns constant ribbon `color2_ch` as XYGR mark-space `dir=right`; ABI 190 owns cartesian per-item two-ended ribbon `color2_ch` intern from packed XYHP kind 5; ABI 184 owns cartesian unwrapped text `dx`/`dy`/`anchor` as XYAW `wrap=0`; ABI 185 owns labelled cartesian marker `dx`/`dy`/`anchor` as XYAW `wrap=0`; ABI 186 owns cartesian colormap hexbin as a 1×N XYHP plane interned onto HexCell PolyFills; ABI 194 owns polar hexbin, custom host reducers, and categorical / `direct_rgba` hexbin on that same intern; ABI 187 owns cartesian unwrapped text `rotation` as XYAW `wrap=0` ABI 195 owns triangle-mesh custom `role` and per-item fill/stroke/width interned from packed XYHP kind 6; ABI 196 intern scatter per-item fill/stroke/width/opacity from packed XYHP kind 7;; ABI 188 owns labelled cartesian marker `rotation` as XYAW `wrap=0`; per-item radius channels stay compatibility. ABI 121 owns ribbon/curve/rounded-rect tessellation; ABI 123 owns tick-label collision thinning (`_axis_tick_label_layout` is a thin packer); ABI 124 owns static legend box packing (`_legend_layout` is a thin packer plus CSS/polar remap); ABI 125 owns text-block measure and cartesian axis rooms (`_textblock.measure` / `_svg._*room` are thin packers plus CSS/tick formatting); ABI 126 owns static-export padding, title-band, colorbar extra, right-y, and polar-recut formulas (`layout()` / `_recut_polar_plot` are thin packers plus CSS/tick formatting/legend reservation); ABI 127 owns the pyplot tight-layout grid solve (`Figure._apply_tight_layout` is a thin packer plus chrome/suptitle/legend measurement); ABI 128 owns authored tick-window resolve/filter (`_tick_window` / `_tick_window_filter` are thin packers); ABI 199 owns Scene product-path authored filter/pairing during chrome pack; ABI 130 owns Cartesian compatibility tick-label formatting (`xyg_tick_format`; `_tick_text` / `_fmt_axis` are thin packers plus compatibility authored `tick_labels`); ABI 131 owns polar (theta, r) → screen-pixel projection (`xyg_polar_*`; `_PolarProjection` layout/project/masks are thin packers; wedge/ring/polygon helpers remain Python for compatibility except ABI 209 `xyg_polar_wedge_points` flatten); ABI 133 owns polar Scene compile for line/scatter/area/bar/column/errorbar/heatmap/contour (XYPL + `polar_project` + `polar_wedge_points` PolyFill + polar chrome; `_PolarProjection` remains for compatibility emitters; polar heatmap tessellates lattice Rects; polar contour reuses SegmentPair polylines); ABI 134 owns painted heatmap intern (`HeatmapPainted` + XYHP; `_heatmap_paint_plane` is a thin packer); ABI 135 owns named colormap tables (`xyg_colormap_stops`, XYHP paint kind 2); ABI 132 owns first-paint density scatter emit policy (`xyg_density_*`; `_density_trace_spec` is a thin packer plus kernel invocation/shipping); ABI 129 owns Cartesian static-export grid colormap (`xyg_colormap_rgba` / `xyg_colormap_rgba_canonical` plus log-u8 `xyg_density_rgba`; `_scene.grid_rgba`, `_svg._heatmap_rgba_grid`, `_svg._heatmap_rgba_samples`, and `_svg._density_image` are thin packers) | Existing polar, SVG, raster, style, export, and pyplot suites | **keep loudly** |
| `_scene_v3.py` figure-to-record assembly | Rust owns record validation, mapping, expansion modes, layout, consumers, the ABI 105 public-export allowlists (heatmap/contour lattices autorange without an authored axis domain), ABI 107 mark fill/stroke defaults plus CSS→RGBA8, ABI 108 chrome style defaults, ABI 109 column packing, ABI 136 product-kind packing, ABI 137 Cartesian density Image blit, ABI 138 constant dash XYDS, ABI 139 constant linecap XYLC, ABI 140 cartesian smooth-polyline flatten, ABI 141 cartesian smooth-area Band flatten, ABI 142 cartesian mean-color density XYHP kind 4, ABI 143 polar density PolyFill tessellation, ABI 144 cartesian error_band BandFlatten plus polar identity-chord smooth, ABI 145 constant marker_path XYMP tessellation, ABI 146 constant mark-fill linear-gradient XYGR, ABI 147 XYPK product packing facts, ABI 148 XYAF annotation packing facts, ABI 149 XYHF heatmap/density paint-fact packing, ABI 150 XYSS extras packing, ABI 151 Scene density grid packing, ABI 152 XYEP packing from XYEF, ABI 153 XYCF figure-chrome packing, ABI 154 XYTC per-trace compile packing, ABI 155 XYTA heatmap/density attach packing, ABI 156 XYCL product-row packing, ABI 157 XYSD trace-sidecar packing, ABI 158 XYSS style-sidecar packing, ABI 159 XYAS annotation splice packing, ABI 160 XYAS/XYCC assembled encode, ABI 161 XYSD chrome/extras packing, ABI 162 XYAS/XYCF assembled encode from sidecars, ABI 163 product encode from packed facts, ABI 164 public static-export consumers, ABI 165 product-path XYFS support, ABI 166 cartesian bar/column/histogram corner_radius tessellation, ABI 167 polar bar/column/histogram wedge_gap tessellation, ABI 168 polar bar/column/histogram corner_radius tessellation, ABI 169 polar curve=smooth plus step, ABI 170 constant marker_glyph XYMG, ABI 171 width-only scatter match-fill, ABI 172 cartesian line step+smooth, ABI 173 heatmap corner_radius tessellation, ABI 174 violin/box corner_radius tessellation, ABI 175 violin/box fill/stroke opacity, ABI 176 bar/column/histogram fill/stroke opacity, ABI 177 heatmap fill_opacity, ABI 178 scatter fill/stroke opacity, ABI 179 hexbin fill_opacity, ABI 180 triangle_mesh fill/stroke opacity, ABI 181 cartesian area/error_band step+smooth, ABI 182 triangle_mesh joined_fill, ABI 183 constant ribbon color2_ch XYGR, ABI 184 cartesian unwrapped text dx/dy/anchor XYAW, ABI 185 labelled cartesian marker dx/dy/anchor XYAW, ABI 186 cartesian colormap hexbin XYHP, ABI 187 cartesian unwrapped text rotation XYAW, ABI 188 labelled cartesian marker rotation XYAW, ABI 189 heatmap/hexbin cell-fill tessellation eligibility from packed XYTA, ABI 190 cartesian per-item two-ended ribbon color2_ch intern from packed XYHP kind 5, ABI 191 constant multi-character scatter marker_glyph XYMG v2, ABI 192 polar painted heatmap inverse-raster Image blit, ABI 193 heatmap/hexbin stroke_opacity, ABI 194 polar hexbin / custom reducers / categorical direct_rgba, ABI 110 XYLG legend framing ABI 195 triangle-mesh custom role / per-item face intern, ABI 196 scatter per-item fill/stroke/width/opacity intern,, ABI 111 XYCB colorbar framing, ABI 112 XYAD annotation framing, ABI 117–118 XYFS figure-compile support including per-trace allowlists, and ABI 135 named colormap lookup; remaining host work is mark-row assembly, custom glyphs/fonts/CSS, and payload LOD | Cross-host Scene bytes, `tests/test_scene_export_support.py`, `tests/test_scene_style_native.py`, and Node `sceneExportSupportReason` pin current assembly | **keep as migration debt** |
| `_figure.py` / `marks.py` host code | Public composition, ingest coercion, validation text, category factorization, rollback, and explicit custom-reducer callables / empty-input compatibility are host responsibilities; ABI 119 owns sort, histogram/contour edge policy, and hex lattice groups; ABI 120 owns `loc="best"` occupancy; ABI 121 owns ribbon/curve/rounded-rect flattening; ABI 122 owns compile-time payload LOD/mask; ABI 204 owns line M4 emit indices; ABI 205 owns remaining emit visible/even/sample indices; ABI 123 owns tick-label collision thinning; ABI 124 owns static legend box packing; ABI 125 owns text-block measure and cartesian axis rooms; ABI 126 owns static-export padding/colorbar/polar recut combination; ABI 127 owns the pyplot tight-layout grid solve; ABI 198 owns `_svg.layout()` combination and tight-layout figure-edge extras; ABI 128 owns authored tick-window resolve/filter; ABI 199 owns Scene product-path authored filter/pairing; ABI 200 owns Scene product-path authored minor filter; ABI 201 owns Scene polar modular theta window / angular labels (secondary axes fail-closed); ABI 202 owns Scene product-path ABI 130 time/angular formats; ABI 130 owns Cartesian compatibility tick-label formatting; ABI 132 owns first-paint density scatter emit policy | Mark, composition, pyplot, and host-parity suites | **keep host seams** |
| `xyg_scene_scatter_svg` Python/Node adapters | Whole-Scene owns the bounded product route, but the version-1 Rust wrapper still serves compatibility scatter rendering and the explicit low-level Node surface | `tests/test_scene_ir.py` and `packages/xy-node/test/scene.test.mjs` | **keep compatibility ABI** |

Static-export routing status (#117): `Figure.to_svg`, native `to_png`, native
`to_image(..., "svg"|"png"|"pdf")`, `write_image`, and the native branch of
`write_images` now delegate the proven
literal Cartesian public geometry subset—constant-style built-in scatter symbols
with optional constant marker strokes and scalar widths
and polylines, bounded fill-only unjoined triangle meshes, constant-style
Cartesian hexbin PolyFill cells, constant-style Cartesian heatmap Rects, Cartesian
constant-style density Image blits, ordinary finite
fixed-domain area/error-band Bands,
ordinary bar/column/histogram Rects and Rust-expanded constant-style violins and boxes, bounded disconnected
segment/error-bar/stem endpoint pairs, and finite literal solid-color ribbons
expanded by Rust—plus the proven literal static
chrome contract (chart/plot backgrounds, title, authored axis
labels/sides/major-minor ticks, independent literal `ticks`/`text` visibility
switches, primary legend, literal colorbar), and the existing bounded primary
Cartesian annotation family: cartesian text with optional `dx`/`dy`/`anchor` (XYAW `wrap=0` when unwrapped), Rust-positioned labelled rules/bands/markers,
unlabelled straight arrows, ordinary callouts, and bounded wrapped text/callouts,
to the Rust Scene
SVG and raster consumers (PDF consumes Rust SVG). `FacetGrid.to_svg` and native grid
PDF independently route each supported panel through that same Rust SVG
consumer, namespacing its closed clip-id vocabulary only for nested-document
composition; native grid PNG/JPEG/WebP independently route each supported
no-background-override panel through the compiled Scene raster display list and
compose the RGBA frames. Panel backgrounds and unsupported panels deliberately
select compatibility before compilation. `python/xyg/_scene_v3.py` is the single
preflight/orchestration seam for that subset: `public_static_export` owns the
Scene-format selection and reuses the predicate's compiled batch, while Python
entry points only retain host options and the documented compatibility
exceptions. `FacetGrid.to_svg` and `FacetGrid._compose_rgba` reuse that compiled
panel Scene. `_svg.py` and
`_raster.py` remain compatibility owners for rich text and legend variants, every
annotation outside that bounded primary Cartesian family (including
collision/layout directives, markup, CSS/classes, and custom typography), themes, custom fonts or CSS/classes,
nonliteral/custom chrome, combined marker_path+marker_glyph, data-driven symbol channels, unmodeled marks or
segment roles/styles, LOD inputs, export background overrides, and any other
unmodeled output contract; #58/#117 must
retire each exception only with cross-host differential and performance proof.
Two-ended ribbon gradients, polar ribbons, and LOD/density ribbon policy remain
explicit compatibility exceptions. Broader direct-browser production,
including ribbon authoring, is tracked by the post-M2 follow-up **Expand direct-browser aggregate production beyond the density/Scene vertical** (related to [#54](https://github.com/CurateLabs/xyg/issues/54)).

The ABI 96 primary numeric-format slice removes one more duplicated host
decision from that compatibility boundary. For Scene-eligible linear, log, and
symlog x/y axes, `crates/xyg-engine/src/scene.rs` exclusively parses
`<prefix>(,).N[f|%]<suffix>` with precision `N` from 0 through 100, resolves
final labels (including invalid-format
fallback, log sub-unit collapse protection, and explicit-label precedence),
and measures gutters. `python/xyg/_scene_v3.py` and
`packages/xy-node/src/scene.js` only retain authoring options and pack bounded
UTF-8 through the versioned ABI envelope. `js/src/30_ticks.ts` remains
the compatibility path for unattached charts and frozen deferred tick families.
WASM ABI
23 plus `attachWasmTicks` now cut explicitly attached automatic, authored-value,
and authored-empty primary Cartesian linear/log/symlog/category/UTC-time
ChartView axes and eligible ChartView colorbars to the Rust resolver and
independent Worker lane. Polar, secondary axes, unattached charts, Blob-worker
HTML, and the srcdoc notebook iframe remain on the frozen compatibility path.
Hosted `to_html()`,
notebook widgets, and Reflex can attach when they serve the packaged
Worker/WASM files at explicit URLs; this is not the all-host ChartView cutover.

## Binding seam decision

XYG intentionally ships one versioned C ABI cdylib for all hosts. Python uses ctypes and Node uses Koffi; Koffi itself is built on Node-API, but XYG is not an N-API addon. PyO3/abi3 and napi-rs would create separate host-specific native artifacts, packaging paths, and version seams. They are not the default while the product requires one core artifact usable by CPython versions, Node, VS Code, and future adapters. Issue #57 generated both low-level bindings and the C header from one typed ABI contract; measured evidence may revisit the seam later.

## Current-tree re-audit (after leftover #283 / ABI 211)

Leftover children [#287](https://github.com/CurateLabs/xyg/issues/287)–[#313](https://github.com/CurateLabs/xyg/issues/313) and parents [#271](https://github.com/CurateLabs/xyg/issues/271)–[#283](https://github.com/CurateLabs/xyg/issues/283) are closed. Remaining `python-scene-migration` debt is not leftover-cluster titles. Do not delete `_svg.py`, `_raster.py`, `_scene.py`, `marks.py`, `_legendfit.py`, `_payload.py`, or `_textblock.py` until Rust owns the path **and** differentials are green. Do not delete `_scene_v3.py`. Do not route pyplot through Scene.

**Reclassified keep-host** (Rust already owns the decision; the Python file packs, coerces, or carries error text):

- `_sankey.py` — name resolution and diagnostic wording over `xyg_sankey_layout`
- `_textblock.py` — ABI 125 packer plus a pass-scoped measurement cache
- `_scene.py` — ABI 121 tessellation wrappers; `grid_rgba` uses ABI 129/206
- `_graph.py` — ingest / id maps; layout is `xyg_graph_layout`
- `_framing.py` — XYBF transport, not chart policy
- `_legendfit.py` — already keep-host (ABI 120 occupancy; ABI 197 Scene `loc="best"`)
- `_paint.triangle_mesh_boundary` — recorded stay-host joined-fill walk
- `_trace_paint_rgba` — host channel dispatch onto ABI 206 `effective_rgba`

**Still blocks “Python is only a host”** (compatibility modules stay until these twins move or stay-host is recorded with diffs):

1. `_payload` emit orchestration — extra-column gather and ship (index math is ABI 204/205; count budget is ABI 214; errorbar role expand is ABI 215)
2. `_scene_v3.py` / Node `scene.js` pack and figure-to-record orchestration
3. ChartView `51_annotations.ts` still copies arrow math until WASM; `_arrowgeom.py` packs style strings onto ABI 217
4. `lod.py` remaining viewport/sample/`EncodedColumn` packing — offset/scale math is ABI 208; pin_zero name mapping is ABI 216
5. `marks.py`, `facets.py`, `_figure.py`, `_annotations.py` composition and `_fontmetrics.py` generated DejaVu table used by compatibility SVG gutters

ABI 209 `xyg_polar_wedge_points` owns compatibility annular-sector flatten (optional `steps`, `0` = `polar_bar_segments`; finite `norm_lo`/`norm_hi` skip radial-range normalization). `_polar_wedge_path` still emits SVG `A` arcs for unrounded wedges. ABI 210 `xyg_hexbin_ring` owns pointy-top hexagon vertex offsets scaled by cell pitch. ChartView `_buildHexbinMark` keeps the same fractions until WASM. ABI 211 `xyg_step_arrays` owns compatibility step/stairs expand (`mode` 1/2/3 = pre/mid/post; `n < 2` identity). ChartView `_stepArrays` keeps the same vertices until WASM. ABI 212 `xyg_marker_path_scale` owns authored-marker pixel vertices (`out_x = cx + scale * unit_x`, `out_y = cy - scale * unit_y`). ChartView legend/annotation scale keeps the same formula until WASM. SVG `d=` assembly stays host. ABI 213 `xyg_css_is_functional` / `xyg_continuous_domain` / `xyg_direct_rgba_admit` owns the `resolve_color` CSS/numeric split, equal-bound domain pad, and Nx3/Nx4 admit so Python `channels.resolve_color` and Node `resolveColorChannel` cannot drift. Named colors stay categories. Hosts still factorize labels, pin palettes, and emit warning text. ABI 214 `xyg_payload_segment_budget` owns the stem/errorbar count budget (`max(1024, floor(px_width)*4)`). ABI 215 `xyg_payload_errorbar_indices` owns even-index expansion across concatenated role groups. Hosts still expand transition-key role maps, gather extra columns, and ship rows. ABI 216 `xyg_scale_pins_offset` owns log-family `pin_zero` admission (`log`/`symlog`, case-sensitive). Hosts still pack `EncodedColumn` metadata. ABI 217 `xyg_arrow_geometry` / `xyg_arrow_shaft_points` / `xyg_arrow_end_decoration` / `xyg_arrow_taper_polygon` / `xyg_arrow_trim_polyline_end` owns annotation-arrow connectionstyle geometry. ChartView `51_annotations.ts` keeps the same formula until WASM. Hosts still parse comma-separated style strings. ABI 218 `xyg_scene_dash_admit` owns Scene dash presets and 2–8 finite length patterns. Invalid comma tokens reject the whole string. ABI 219 `xyg_scene_linecap_admit` owns Scene linecap names; unknown and whitespace-only reject. ABI 220 `xyg_density_overlay_opacity` owns density overlay sample opacity (non-finite → 0.55). ABI 221 `xyg_scene_marker_path_admit` owns Scene marker-path contour bounds. ABI 222 `xyg_scene_annotation_style_admit` owns Scene annotation style-key allowlists. ABI 223 `xyg_scene_ribbon_color2_classify` owns ribbon two-ended paint class. ABI 224 `xyg_scene_tick_label_strategy` owns Scene tick-label strategy names (hyphens become underscores; unknown/empty map to auto). Hosts still pick `tick_label_strategy` vs `collision` vs camelCase keys. ABI 225 `xyg_scene_tick_anchor` owns Scene tick-label anchor names (`middle` aliases `center`; unknown/empty reject). Hosts still pick `tick_label_anchor` vs camelCase keys. ABI 123 layout enums stay a separate throw-on-unknown table. ABI 226 `xyg_scene_fill_gradient_admit` owns Scene fill-gradient stop admit (`var(` reject; empty/`currentcolor` → mark color). ABI 227 `xyg_scene_parse_linear_gradient` owns CSS `linear-gradient(...)` parse. ABI 228 `xyg_scene_rect_extra_flags` owns Scene rect extra-flag pack. ABI 229 `xyg_scene_gradient_dir` owns Scene fill-gradient direction codes. ABI 230 `xyg_scene_linear_gradient_prefix` owns the CSS `linear-gradient(` prefix check. ABI 231 `xyg_scene_gradient_space` owns Scene fill-gradient space codes. ABI 232 `xyg_scene_hexbin_reduce_admit` owns Scene hexbin reduce names. ABI 233 `xyg_scene_curve_classify` owns Scene curve names (trim then lowercase; kind checks for `smooth` stay host). ABI 234 `xyg_scene_marker_glyph_admit` owns Scene marker-glyph UTF-8 admit. ABI 235 `xyg_scene_kind_admit` owns Scene product-kind names. ABI 236 `xyg_scene_kind_class` owns Scene packing-family bits. ABI 237 `xyg_scene_hexbin_pitch_admit` owns Scene hexbin cell-pitch admit. ABI 238 `xyg_scene_heatmap_extent_admit` owns Scene heatmap cell-extent admit. ABI 239 `xyg_scene_heatmap_colormap_admit` owns Scene heatmap colormap eligibility. ABI 240 `xyg_scene_heatmap_shape_admit` owns Scene heatmap lattice-shape admit. ABI 241 `xyg_scene_scatter_paint_channel_admit` owns Scene scatter paint-plane channel names. ABI 242 `xyg_scene_hexbin_colormap_plane_admit` owns Scene hexbin colormap-plane packing. ABI 243 `xyg_scene_hexbin_rgba_plane_admit` owns Scene hexbin RGBA-plane modes. ABI 244 `xyg_scene_mesh_paint_plane_admit` owns Scene mesh paint-plane packing. ABI 245 `xyg_scene_item_apply_opacity` owns Scene per-item RGBA8 artist-alpha/opacity. ABI 246 `xyg_scene_item_widths_admit` owns Scene per-item stroke-width admit. Field picking and f64 packing stay host. Hosts still coerce fill mappings, wrap authoring error text, radius lists, and `wedge_gap`. Next kernel: remaining `_payload` emit orchestration and `_scene_v3` pack. Do not wrap Scene's RGBA-grid raster as a compat path.

## Disposition summary

| Policy | Files | Disposition | Destination |
| --- | ---: | --- | --- |
| `rust-engine` | 16 | `keep-rust` | current owner |
| `rust-c-abi` | 1 | `keep-rust` | current owner |
| `rust-wasm-abi` | 1 | `implement-rust-wasm` | [#59](https://github.com/CurateLabs/xyg/issues/59) |
| `python-host` | 66 | `keep-host` | current owner |
| `python-scene-migration` | 13 | `split-and-move-rust` | [#58](https://github.com/CurateLabs/xyg/issues/58) |
| `python-abi-generated` | 1 | `generate` | [#57](https://github.com/CurateLabs/xyg/issues/57) |
| `node-host` | 7 | `keep-host` | current owner |
| `node-scene-migration` | 29 | `split-and-move-rust` | [#58](https://github.com/CurateLabs/xyg/issues/58) |
| `node-abi-generated` | 1 | `generate` | [#57](https://github.com/CurateLabs/xyg/issues/57) |
| `browser-client` | 16 | `keep-shared-client` | current owner |
| `browser-scene-migration` | 1 | `move-rust` | [#58](https://github.com/CurateLabs/xyg/issues/58) |
| `browser-wasm-migration` | 1 | `replace-with-rust-wasm` | [#59](https://github.com/CurateLabs/xyg/issues/59) |
| `browser-wasm-adapter` | 2 | `implement-rust-wasm` | [#59](https://github.com/CurateLabs/xyg/issues/59) |
| `browser-wasm-generated` | 1 | `generate` | [#59](https://github.com/CurateLabs/xyg/issues/59) |

## Boundary policies

### `rust-engine`

Owner: Rust safe engine. Disposition: `keep-rust`.

Allowed:

- Row scans, geometry, aggregation, layout, LOD, encoding, and deterministic product policy.
- Canonical scene and static-export construction shared by every host.

Forbidden:

- Python, Node, browser DOM, or transport-specific API behavior.
- Host-specific error wording or package discovery.

### `rust-c-abi`

Owner: Rust C ABI shell. Disposition: `keep-rust`.

Allowed:

- C-compatible marshaling, panic containment, ABI versioning, and opaque-handle lifecycle.

Forbidden:

- A second implementation of algorithms or deterministic product policy that belongs in xyg-engine.
- Python- or Node-specific extension-module APIs.

### `rust-wasm-abi`

Owner: Rust WASM lifecycle adapter. Disposition: `implement-rust-wasm` under
[#59](https://github.com/CurateLabs/xyg/issues/59).

Allowed:

- Raw WebAssembly exports, bounded staging memory, instance handles, stable
  status codes, lifecycle diagnostics, and thin calls into `xyg-engine`.

Forbidden:

- A second implementation of engine policy, browser DOM/WebGL behavior,
  package asset discovery, or host-specific chart APIs.

### `python-host`

Owner: Python host. Disposition: `keep-host`.

Allowed:

- Composition and pyplot APIs, Reflex integration, ingest coercion, validation messages, transport, and notebook lifecycle.

Forbidden:

- A parallel implementation of canonical layout, LOD, encoding, aggregation, scene, or export policy.
- Hand-maintained low-level C signatures.

### `python-scene-migration`

Owner: Python host with canonical-policy debt. Disposition: `split-and-move-rust` under [#58](https://github.com/CurateLabs/xyg/issues/58).

Allowed:

- Compatibility wrappers, Python object coercion, public error text, and temporary orchestration during migration.

Forbidden:

- New canonical scene, layout, tick, geometry, colormap, or static-export behavior.
- Expanding an implementation that must match Node and direct-browser hosts.

### `python-abi-generated`

Owner: Python low-level ABI binding. Disposition: `generate` under [#57](https://github.com/CurateLabs/xyg/issues/57).

Allowed:

- Generated ctypes declarations plus a narrow handwritten ergonomic wrapper layer.

Forbidden:

- Hand-maintained symbol signatures, argument order, pointer mutability, or return types.
- Canonical engine algorithms.

### `node-host`

Owner: Node host. Disposition: `keep-host`.

Allowed:

- Idiomatic JS APIs, TypedArray coercion, errors, native-library discovery, HTML embedding, and VS Code transport.

Forbidden:

- A parallel implementation of canonical layout, LOD, encoding, aggregation, scene, or export policy.
- Hand-maintained Koffi C signatures.

### `node-scene-migration`

Owner: Node host with canonical-policy debt. Disposition: `split-and-move-rust` under [#58](https://github.com/CurateLabs/xyg/issues/58).

Allowed:

- TypedArray coercion, idiomatic composition methods, and temporary scene orchestration during migration.

Forbidden:

- New canonical scene, layout, LOD, encoding, aggregation, or static-export policy.
- Behavior that can diverge from Python or direct-browser hosts.

### `node-abi-generated`

Owner: Node low-level ABI binding. Disposition: `generate` under [#57](https://github.com/CurateLabs/xyg/issues/57).

Allowed:

- Generated Koffi declarations plus minimal loading and ABI-version validation.

Forbidden:

- Hand-maintained C signatures or canonical engine behavior.

### `browser-client`

Owner: Shared TypeScript browser client. Disposition: `keep-shared-client`.

Allowed:

- WebGL painting, picking, gestures, DOM chrome, accessibility, animation, client cache, and browser lifecycle.
- Screen-bounded presentation and transport attachment over engine-produced buffers.

Forbidden:

- Canonical layout, tick generation, data aggregation, encoding, or full-data row scans.
- Node-only modules, Koffi, filesystem access, or a second renderer.

### `browser-scene-migration`

Owner: Shared TypeScript client with canonical-policy debt. Disposition: `move-rust` under [#58](https://github.com/CurateLabs/xyg/issues/58).

Allowed:

- Temporary tick consumption and browser-specific label presentation during scene migration.
- The existing TypeScript generator stays frozen for unattached charts and the
  angular/polar/secondary compatibility paths.
  An explicitly attached automatic, authored-value, or authored-empty primary
  Cartesian linear/log/symlog/category/UTC-time axis or eligible colorbar
  consumes only Rust-produced positions and labels for each view and resize.

Forbidden:

- Expanding canonical tick generation or layout policy in TypeScript.

### `browser-wasm-migration`

Owner: Shared TypeScript fallback compute. Disposition: `replace-with-rust-wasm` under [#59](https://github.com/CurateLabs/xyg/issues/59).

Allowed:

- A bounded compatibility fallback and the future thin Worker adapter around Rust/WASM.

Forbidden:

- Expanding JavaScript row scans, binning, encoding, aggregation, layout, or other engine algorithms.

### `browser-wasm-adapter`

Owner: Shared TypeScript WASM lifecycle adapter. Disposition:
`implement-rust-wasm` under [#59](https://github.com/CurateLabs/xyg/issues/59).

Allowed:

- Explicit static Worker/WASM asset loading, bounded memory copies, stable
  status transport, cancellation, trap handling, and disposal.
- Latest-wins viewport framing and cache admission for Rust-owned automatic,
  authored-value, and authored-empty primary Cartesian
  linear/log/symlog/category/UTC-time ticks; TypeScript may
  schedule and paint but may neither generate nor format a covered attached axis.
- O(series) validation and framing for transferable typed columns. Rust owns
  per-record expansion, stable identities, and default mark/bar geometry. Exact
  per-record u64 identities remain an attached transferable column; TypeScript
  does not inspect their values.
- Generated `XYTS` offsets, flags, and kind codes from the versioned WASM
  manifest; handwritten wire-layout numbers are forbidden in the adapter.

Forbidden:

- Canonical engine algorithms, implicit CDN/path lookup, eval, Blob workers,
  or silent JavaScript fallbacks.

### `browser-wasm-generated`

Owner: Generated TypeScript WASM binding. Disposition: `generate` under
[#59](https://github.com/CurateLabs/xyg/issues/59).

Allowed:

- Generated export declarations, version checks, and status constants from
  `spec/wasm/abi.json`.

Forbidden:

- Hand-maintained raw signatures or canonical engine behavior.

## File ledger

| Path | Current owner | Policy | Disposition | Follow-up |
| --- | --- | --- | --- | ---: |
| `crates/xyg-core/src/lib.rs` | Rust C ABI shell | `rust-c-abi` | `keep-rust` | — |
| `crates/xyg-wasm/src/lib.rs` | Rust WASM lifecycle adapter | `rust-wasm-abi` | `implement-rust-wasm` | #59 |
| `crates/xyg-wasm/src/compound.rs` | Rust WASM lifecycle adapter | `rust-wasm-abi` | `implement-rust-wasm` | #59 |
| `crates/xyg-wasm/src/dashboard.rs` | Rust WASM lifecycle adapter | `rust-wasm-abi` | `implement-rust-wasm` | #59 |
| `crates/xyg-wasm/src/compile.rs` | Rust WASM lifecycle adapter | `rust-wasm-abi` | `implement-rust-wasm` | #59 |
| `crates/xyg-wasm/src/bin/xyts_conformance.rs` | Rust WASM lifecycle adapter | `rust-wasm-abi` | `implement-rust-wasm` | #59 |
| `crates/xyg-wasm/src/graph.rs` | Rust WASM lifecycle adapter | `rust-wasm-abi` | `implement-rust-wasm` | #59 |
| `crates/xyg-wasm/src/aggregate.rs` | Rust WASM lifecycle adapter | `rust-wasm-abi` | `implement-rust-wasm` | #59 |
| `crates/xyg-wasm/src/temporal.rs` | Rust WASM lifecycle adapter | `rust-wasm-abi` | `implement-rust-wasm` | #59 |
| `crates/xyg-wasm/src/ticks.rs` | Rust WASM lifecycle adapter | `rust-wasm-abi` | `implement-rust-wasm` | #59 |
| `crates/xyg-wasm/src/temporal_graph.rs` | Rust WASM lifecycle adapter | `rust-wasm-abi` | `implement-rust-wasm` | #59 |
| `crates/xyg-wasm/src/typed_series_abi_generated.rs` | Generated cross-host WASM contract binding | `browser-wasm-generated` | `generate` | #59 |
| `crates/xyg-engine/src/css.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/autorange.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/arrow_geom.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 217 annotation-arrow geometry | — |
| `crates/xyg-engine/src/dashboard.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/font.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/geo.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/chunked_columns.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/compat_layout.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 126 static-export padding/colorbar/polar recut; ABI 127 pyplot tight-layout; ABI 198 `_svg.layout()` combination + tight figure extras | — |
| `crates/xyg-engine/src/edge_route.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/geo_viewport.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/geom.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/graph.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/graph_style.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/hexbin.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/jpeg.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/colormap.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 135 named colormap tables (`xyg_colormap_stops`, XYHP paint kind 2) | — |
| `crates/xyg-engine/src/kernels.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 129 Cartesian static-export grid colormap (`colormap_rgba_into` / `colormap_rgba_canonical_into`); ABI 218 Scene dash admit; ABI 219 Scene linecap admit; ABI 220 density overlay opacity; ABI 221 Scene marker-path admit; ABI 222 Scene annotation style admit; ABI 223 Scene ribbon color2 classify; ABI 224 Scene tick-label strategy admit; ABI 225 Scene tick-label anchor admit; ABI 226 Scene fill-gradient admit; ABI 227 Scene linear-gradient CSS parse; ABI 228 Scene rect extra-flag pack; ABI 229 Scene gradient-dir pack; ABI 230 Scene linear-gradient CSS prefix; ABI 231 Scene gradient-space pack; ABI 232 Scene hexbin reduce admit; ABI 233 Scene curve-name classify; ABI 234 Scene marker-glyph admit; ABI 235 Scene product-kind admit; ABI 236 Scene packing-family classify; ABI 237 Scene hexbin pitch admit; ABI 238 Scene heatmap extent admit; ABI 239 Scene heatmap colormap admit; ABI 240 Scene heatmap shape admit; ABI 241 Scene scatter paint-channel admit; ABI 242 Scene hexbin colormap-plane admit; ABI 243 Scene hexbin RGBA-plane admit; ABI 244 Scene mesh paint-plane admit; ABI 245 Scene per-item RGBA8 artist-alpha/opacity; ABI 246 Scene per-item stroke-width admit | — |
| `crates/xyg-engine/src/layout_rooms.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 125 measured cartesian gutters. #297 routes default-font Scene-shaped specs through `xyg_scene_plot_layout` | — |
| `crates/xyg-engine/src/legend_fit.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/legend_layout.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 124 static legend box packing | — |
| `crates/xyg-engine/src/lib.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/lod_plan.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 122 compile-time payload tier + visible mask; ABI 204 line M4 emit indices; ABI 205 emit visible/even/sample indices | — |
| `crates/xyg-engine/src/density_emit.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 132 first-paint density emit policy | — |
| `crates/xyg-engine/src/pdf.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/png_encode.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/polar.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 131 polar projection; ABI 133 XYPL polar Scene compile | — |
| `crates/xyg-engine/src/projection.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/raster.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/sankey.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/scene.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/scene_annotation_splice.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 159 XYAS annotation splice packing | — |
| `crates/xyg-engine/src/scene_annotations.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/scene_colorbar.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/scene_chrome.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 153 XYCF figure-chrome packing; ABI 161 XYSD legend-paint splice | — |
| `crates/xyg-engine/src/scene_density.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 151 Scene density grid packing | — |
| `crates/xyg-engine/src/scene_encode_assembled.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 160 XYAS/XYCC assembled encode; ABI 162 XYAS/XYCF encode from sidecars; ABI 163 product encode from packed facts; ABI 165 product-path XYFS support | — |
| `crates/xyg-engine/src/scene_export.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 152 XYEP packing from XYEF | — |
| `crates/xyg-engine/src/scene_extras.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 150 XYSS extras packing; ABI 161 XYSD XYHP wrapping | — |
| `crates/xyg-engine/src/scene_heatmap.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 149 XYHF paint-fact packing | — |
| `crates/xyg-engine/src/scene_legend.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/scene_pack.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/scene_static.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 164 public static-export consumers | — |
| `crates/xyg-engine/src/scene_style.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/scene_style_sidecars.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 158 XYSS style-sidecar packing | — |
| `crates/xyg-engine/src/scene_trace_attach.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 155 XYTA heatmap/density attach packing | — |
| `crates/xyg-engine/src/scene_trace_compile.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 154 XYTC per-trace compile packing; ABI 221 Scene marker-path admit | — |
| `crates/xyg-engine/src/scene_trace_rows.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 156 XYCL product-row packing | — |
| `crates/xyg-engine/src/scene_trace_sidecars.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 157 XYSD trace-sidecar packing | — |
| `crates/xyg-engine/src/simd.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/stats.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/stream.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/svg.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/temporal.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/temporal_controller.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/temporal_graph.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/textblock.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 125 newline-delimited chrome measure | — |
| `crates/xyg-engine/src/tick_layout.rs` | Rust safe engine | `rust-engine` | `keep-rust`; ABI 123 tick-label collision thinning; ABI 128 authored tick-window; ABI 199 Scene product-path authored filter/pairing; ABI 200 Scene product-path authored minor filter; ABI 201 Scene polar modular theta window / angular labels; ABI 202 Scene product-path ABI 130 time/angular formats; ABI 203 Scene cartesian ABI 123 collision emit; ABI 130 tick-label formatting (`format_axis_tick` in `scene.rs`) | — |
| `crates/xyg-engine/src/tile_store.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/tiles.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/transition.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `crates/xyg-engine/src/webp.rs` | Rust safe engine | `rust-engine` | `keep-rust` | — |
| `js/src/00_header.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/10_colormaps.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/20_theme.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/30_ticks.ts` | Shared TypeScript client with canonical-policy debt | `browser-scene-migration` | `move-rust` | #58 |
| `js/src/40_gl.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/42_glhost.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/45_lod.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/47_wasm.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/48_wasm_scene.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_compound.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_dashboard.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_graph.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_columns.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_semantic_graph.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_ticks.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_chart.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_aggregate.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_density.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_temporal.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/49_wasm_temporal_graph.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/50_chartview.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/51_annotations.ts` | Shared TypeScript browser client | `browser-client` | `literal-projection-only`; Scene v24 owns rule/band/marker geometry, order, clipping, defaults, bounded attached-label anchors, literal Cartesian straight-arrow projection/head geometry, bounded Cartesian callout leader/label anchoring, fixed literal label backgrounds/borders, and wrapped-line/box geometry in Rust; markup, CSS/classes, custom fonts, and collision policy remain migration debt | #116 |
| `js/src/52_tooltip.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/53_interaction.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/54_kernel.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/55_marks.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/56_animation.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/57_viewstate.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/58_graph.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/60_entries.ts` | Shared TypeScript browser client | `browser-client` | `keep-shared-client` | — |
| `js/src/wasm_abi_generated.ts` | Generated cross-host WASM contract binding | `browser-wasm-generated` | `generate` | #59 |
| `js/src/wasm_inline_worker.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `js/src/wasm_worker.ts` | Shared TypeScript WASM lifecycle adapter | `browser-wasm-adapter` | `implement-rust-wasm` | #59 |
| `packages/xy-node/src/_abi_generated.js` | Node low-level ABI binding | `node-abi-generated` | `generate` | #57 |
| `packages/xy-node/src/abi.js` | Node host | `node-host` | `keep-host` | — |
| `packages/xy-node/src/chunked-columns.js` | Node host | `node-host` | `keep-host` | — |
| `packages/xy-node/src/charts.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/color.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/encode.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/figure.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust`; ABI 220 owns density overlay opacity; hosts still default omitted opacity to `0.8` and gather/ship | #58 |
| `packages/xy-node/src/force_scheduler.js` | Node host | `node-host` | `keep-host` | — |
| `packages/xy-node/src/graph.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/html.js` | Node host | `node-host` | `keep-host` | — |
| `packages/xy-node/src/index.js` | Node host | `node-host` | `keep-host` | — |
| `packages/xy-node/src/marks/area.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/bar.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/box.js` | Node host | `node-host` | `keep-host` | — |
| `packages/xy-node/src/marks/contour.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/distribution.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/ecdf.js` | Node host | `node-host` | `keep-host` | — |
| `packages/xy-node/src/marks/error_band.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/errorbar.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/heatmap.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust`; constant-style, scalar-colormap, and truecolor Cartesian/polar Scene expand a regular lattice onto Rects (polar encode tessellates to PolyFill); remaining debt is irregular-grid assembly | #58 |
| `packages/xy-node/src/marks/hexbin.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust`; ABI 102 removed finite-pair/domain/aspect policy; ABI 103 moves Cartesian Scene hex-cell ring expansion into Rust; ABI 119 moves custom-reduce lattice groups into Rust; ABI 186 interned cartesian metric colormaps onto HexCell PolyFills; ABI 194 admits polar hexbin, custom host reducers, and categorical / `direct_rgba` cell paints | #58 |
| `packages/xy-node/src/marks/histogram.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust`; ABI 119 moves integer/empty-auto edge policy into Rust | #58 |
| `packages/xy-node/src/marks/line.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/polar.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/radar.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/ribbon.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/scatter.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/segments.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust`; ABI 104 moves Cartesian Scene endpoint-pair expansion into Rust; remaining debt is role/style assembly | #58 |
| `packages/xy-node/src/marks/stem.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/marks/step.js` | Node compact authoring adapter | `node-host-authoring` | `keep-thin`; ABI 95 passes compact step mode/source columns and Rust owns canonical Scene expansion | #58 |
| `packages/xy-node/src/marks/triangle_mesh.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust`; ABI 104 moves Cartesian Scene triangle-face expansion into Rust; remaining debt is joined-fill/style assembly | #58 |
| `packages/xy-node/src/marks/violin.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/native-path.js` | Node host | `node-host` | `keep-host` | — |
| `packages/xy-node/src/native.js` | Node host | `node-host` | `keep-host` | — |
| `packages/xy-node/src/pyramid.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/sankey.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust` | #58 |
| `packages/xy-node/src/scene.js` | Node host with canonical-policy debt | `node-scene-migration` | `split-and-move-rust`; ABI 218 owns Scene dash admit; ABI 219 owns Scene linecap admit; ABI 221 owns Scene marker-path admit; ABI 222 owns Scene annotation style admit; ABI 223 owns ribbon color2 classify; ABI 224 owns tick-label strategy admit; ABI 225 owns tick-label anchor admit; ABI 226 owns fill-gradient stop admit; ABI 227 owns linear-gradient CSS parse; ABI 228 owns rect extra-flag pack; ABI 229 owns gradient-dir pack; ABI 230 owns linear-gradient CSS prefix; ABI 231 owns gradient-space pack; ABI 232 owns hexbin reduce admit; ABI 233 owns curve-name classify; ABI 234 owns marker-glyph admit; ABI 235 owns product-kind admit; ABI 236 owns packing-family classify; ABI 237 owns hexbin pitch admit; ABI 238 owns heatmap extent admit; ABI 239 owns heatmap colormap admit; ABI 240 owns heatmap shape admit; ABI 241 owns scatter paint-channel admit; ABI 242 owns hexbin colormap-plane admit; ABI 243 owns hexbin RGBA-plane admit; ABI 244 owns mesh paint-plane admit; ABI 245 owns per-item RGBA8 artist-alpha/opacity; ABI 246 owns per-item stroke-width admit; hosts still coerce channels, pack end RGBA8, skip markup/typography/rotation, raise error text, pick tick_label_strategy / tick_label_anchor vs collision vs camelCase keys, and coerce fill mappings | #58 |
| `packages/xy-node/src/temporal-graph.js` | Node host | `node-host` | `keep-host` | — |
| `packages/xy-node/src/vscode.js` | Node host | `node-host` | `keep-host` | — |
| `python/reflex_xy/__init__.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/app.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/assets/__init__.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/component.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/events.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/namespace.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/payload_asset.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/registry.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/selections.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/state_bridge.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/tokens.py` | Python host | `python-host` | `keep-host` | — |
| `python/reflex_xy/vars.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/__init__.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_abi_generated.py` | Python low-level ABI binding | `python-abi-generated` | `generate` | #57 |
| `python/xyg/_wasm_aggregate_generated.py` | Generated cross-host WASM contract binding | `browser-wasm-generated` | `generate` | #59 |
| `python/xyg/_annotations.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_arrowgeom.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust`; ABI 217 owns connectionstyle/shaft/taper/trim/end geometry; hosts still parse comma-separated style strings | #58 |
| `python/xyg/_benchmark_theme.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_chromium.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_figure.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_fontmetrics.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/_framing.py` | Python host | `python-host` | `keep-host`; XYBF transport framing, not chart policy | — |
| `python/xyg/_geoarrow.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_graph.py` | Python host | `python-host` | `keep-host`; ingest/id maps; layout is `xyg_graph_layout` | — |
| `python/xyg/_hosts.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_jpeg.py` | Python host | `python-host` | `keep-host`; ABI 114 moves baseline JPEG encode into Rust; this module only coerces a NumPy array and forwards `quality` | #274 |
| `python/xyg/_legendfit.py` | Python host | `python-host` | `keep-host`; ABI 120 occupancy scoring; ABI 197 Scene product encode settles `loc="best"` from XYCL/XYNM. This module still packs ChartView compatibility specs | — |
| `python/xyg/_native.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_ooc.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_paint.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust`; ABI 206 owns `effective_rgba`; `triangle_mesh_boundary` stays host joined-fill geometry | #58 |
| `python/xyg/_payload.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust`; ABI 122 owns compile-time payload LOD and the visible-row mask; ABI 204 owns line M4 emit indices; ABI 205 owns remaining emit visible/even/sample indices; ABI 214 owns the stem/errorbar count budget; ABI 215 owns errorbar role-block expand; ABI 220 owns density overlay opacity; emitters still gather extra columns and ship | #58 |
| `python/xyg/_pdf.py` | Python host | `python-host` | `keep-host`; ABI 113 moves closed-subset SVG→PDF into Rust; this module only coerces UTF-8 and raises the historical diagnostic wording | #274 |
| `python/xyg/_png.py` | Python host | `python-host` | `keep-host`; ABI 115 moves filter-0 PNG encode into Rust; this module only coerces host buffers and forwards `mode` / `compression` | #274 |
| `python/xyg/_raster.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust`; ABI 121 tessellation via `kernels` directly (#310); ABI 206 owns remaining `_lut` / linear density / effective rgba (#313); ABI 210 owns hexbin ring offsets; ABI 211 owns step/stairs expand; ABI 212 owns authored marker-path scale; `triangle_mesh_boundary` stays host geometry | #58 |
| `python/xyg/_sankey.py` | Python host | `python-host` | `keep-host`; ABI `xyg_sankey_layout`; this module resolves names and error text | — |
| `python/xyg/_scene.py` | Python host | `python-host` | `keep-host`; ABI 121 tessellation wrappers; `grid_rgba` uses ABI 129/206 colormap kernels | — |
| `python/xyg/_scene_v3.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust`; ABI 218 owns Scene dash admit; ABI 219 owns Scene linecap admit; ABI 221 owns Scene marker-path admit; ABI 222 owns Scene annotation style admit; ABI 223 owns ribbon color2 classify; ABI 224 owns tick-label strategy admit; ABI 225 owns tick-label anchor admit; ABI 226 owns fill-gradient stop admit; ABI 227 owns linear-gradient CSS parse; ABI 228 owns rect extra-flag pack; ABI 229 owns gradient-dir pack; ABI 230 owns linear-gradient CSS prefix; ABI 231 owns gradient-space pack; ABI 232 owns hexbin reduce admit; ABI 233 owns curve-name classify; ABI 234 owns marker-glyph admit; ABI 235 owns product-kind admit; ABI 236 owns packing-family classify; ABI 237 owns hexbin pitch admit; ABI 238 owns heatmap extent admit; ABI 239 owns heatmap colormap admit; ABI 240 owns heatmap shape admit; ABI 241 owns scatter paint-channel admit; ABI 242 owns hexbin colormap-plane admit; ABI 243 owns hexbin RGBA-plane admit; ABI 244 owns mesh paint-plane admit; ABI 245 owns per-item RGBA8 artist-alpha/opacity; ABI 246 owns per-item stroke-width admit; hosts still coerce channels, pack end RGBA8, skip markup/typography/rotation, raise error text, pick tick_label_strategy / tick_label_anchor vs collision vs camelCase keys, and coerce fill mappings | #58 |
| `python/xyg/_spatial.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_svg.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust`; ABI 207 owns polar heatmap inverse-map hits; ABI 209 owns polar wedge flatten; ABI 210 owns hexbin ring offsets; ABI 211 owns step/stairs expand; ABI 212 owns authored marker-path scale; hosts still color sampled cells and emit SVG `A` arcs / `d=` strings | #58 |
| `python/xyg/_textblock.py` | Python host | `python-host` | `keep-host`; ABI 125 packer plus a pass-scoped measurement cache | — |
| `python/xyg/_trace.py` | Python host | `python-host` | `keep-host`; ABI 122 owns the density/M4 threshold decision; this module packs kind/force/per-item onto `payload_tier` | — |
| `python/xyg/_typing.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_validate.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/_webp.py` | Python host | `python-host` | `keep-host`; ABI 114 moves lossless WebP encode into Rust; this module only coerces a NumPy array | #274 |
| `python/xyg/channel.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/channels.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust`; ABI 213 owns CSS/numeric split, domain pad, and direct RGBA admit; hosts still factorize labels and pin palettes | #58 |
| `python/xyg/columns.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/components.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/config.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/dom.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/export.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/facets.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust` | #58 |
| `python/xyg/graph_layout.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/interaction.py` | Python host | `python-host` | `keep-host`; ABI 204 owns line/area re-decimate skip, closed-window ulp, and polar skip | — |
| `python/xyg/kernels.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/lod.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust`; ABI 208 owns `geometry_offset` / `f32_safe_scale`; ABI 216 owns log-family `pin_zero` names; hosts still pack `EncodedColumn` | #58 |
| `python/xyg/marks.py` | Python host with canonical-policy debt | `python-scene-migration` | `split-and-move-rust`; ABI 221 owns Scene marker-path contour admit; hosts still coerce mappings and error text | #58 |
| `python/xyg/plugins.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/__init__.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_artists.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_axes.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_axisgrid.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_colors.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_fmt.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_grid.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_markers.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_mathtext.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_mplfig.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_plot_types.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_rc.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_state.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_ticker.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_transforms.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/_translate.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/pyplot/dates.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/styles.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/styling/__init__.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/styling/capabilities.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/temporal_controller.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/temporal_graph.py` | Python host | `python-host` | `keep-host` | — |
| `python/xyg/widget.py` | Python host | `python-host` | `keep-host` | — |

## Contributor rule

Run `python3 scripts/verify_ownership.py` after adding, removing, or renaming production source. A new file is intentionally unclassified until this ledger names its owner and boundary in the same change. Moving a file between policies requires updating both this audit and its JSON twin; do not weaken a policy to make a new host algorithm pass.
