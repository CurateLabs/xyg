# XYG Rust Engine — Workspace, Module Boundaries & FFI Protocol

**Status:** design, grounded in the shipped engine. Decides what lives in Rust
vs the hosts and how the C-ABI seam evolves without rewrites. The Rust source
is a Cargo **workspace** (~27K lines at this revision) with two crates: the
safe engine `crates/xyg-engine` (algorithms + deterministic product policy;
sixteen domain modules) and the C ABI shell `crates/xyg-core` (extern "C"
marshaling, panic shielding, opaque-handle runtime; ABI v59, one shipped
cdylib `libxyg_core`; `png` is the one third-party crate, for static export).
Two host bindings consume the same artifact: Python ctypes
(`python/xyg/_native.py`, dispatch in `kernels.py`) and Node koffi
(`packages/xy-node/src/native.js`). The native core is required — the Python
`kernels.py` raises a clear ImportError when it can't load, with no
pure-Python fallback, and the Node loader throws before binding anything else.
The naming matrix decides a clean-break `import xyg` / `python/xyg/` rename;
it is staged after this crate split so Python package churn cannot block
`libxyg_core`.
The exported ABI surface is machine-checked: see §3.5 (ABI manifest and parity
gate). Naming for every surface is locked in
[xyg-naming.md](xyg-naming.md).
The exhaustive file-level placement contract is
[ownership-audit.md](ownership-audit.md); its JSON twin is enforced in CI.

## 1. The placement rule

**Rust owns row-scan loops and parity-affecting decisions; hosts own
ergonomics only.** XYG serves dual Python+Node hosts (see
[host-parity.md](host-parity.md)): any decision that changes buffers, layout,
encodings, or recorded §28 LOD/layout outcomes is implemented in Rust so both
bindings stay thin and bit-identical. (Upstream XYG's "Python owns decisions"
rule is historical; this document states the current model directly.)

Precisely:

- If work is O(N) / O(|V|+|E|) over data, or sits on an interaction path
  (build, zoom, pan, drill, layout ticks) → Rust kernel.
- If work is deterministic policy that must match across Python and Node
  (tier choice that changes geometry, layout parameter application, graph LOD
  budgets) → Rust.
- If work is host ergonomics only (API shapes, idiomatic ingest coercion,
  error *message* text, transport attach) → host. Do **not** put a second
  layout/encode path in Python or Node.
- The client (JS) owns nothing O(N): it receives screen-bounded buffers only
  (§29). This boundary is what keeps the browser safe at 1B rows and it never
  moves.

### Current placement audit

| Concern | Today | Verdict |
|---|---|---|
| zone maps, encode_f32, m4, bin_2d, bin_2d_mean_color, min_max, histogram_uniform, normalize_f32, range/validity indices, polygon (lasso) selection, local_log_density | Rust (ABI v41) | correct — new equal-length x/y columns use a paired zone-map call with bit-identical per-column reductions; lasso ray casting (`xyg_polygon_select`, §34) walks edges inside the point loop instead of one NumPy pass per edge, and buckets edges by y so a point tests only those spanning its row — the answer is the same crossing parity, without the per-edge full-length temporaries that made a 2048-vertex lasso cost ~370 ms over 160k candidates. Bucketing is declined below 16 vertices (the build outweighs the scans it saves) and for a non-finite polygon (slab bounds stop meaning anything); above 16 the slab count tracks the vertex count, capped at 256 and shed further so the CSR never exceeds 2²⁰ entries, which bounds both the allocation and its u32 cursors independently of what a caller passes; full-domain density first paint fuses binning with uniform or counted-u8 overlay sampling while retaining exact standalone outputs; mean-color binning (LOD doc §2) is an integer-only pipeline (checked-in sRGB⇄linear-u16 tables, alpha-weighted u64 sums) so grids are bitwise deterministic across thread counts and platforms; mesh/rectangle validity scans consume only columns not already proven finite by zone metadata |
| fixed-width string/bytes/bool factorization | Rust (ABI v36) | correct — compact palettes use a bounded L1-resident codebook with full-record collision checks and emit exact counts; U1 uses a direct Unicode-scalar table with endian support; ≥512k rows probe a prefix then encode disjoint chunks in parallel, merging late labels by canonical first-row order before any retry; Python sees only unique labels and retains display-label ordering policy |
| stable animation-key encoding for homogeneous fixed-width string/bytes/bool/integer/float columns | Rust (ABI v43) | correct — one borrowed row scan emits the two caller-owned u32 identity planes and reports the first duplicate pair; f16/f32 widen exactly to the f64 token contract and non-native arrays carry an explicit endian flag; Python validates shape/length, unwraps `to_numpy` columns and homogeneous object storage so a DataFrame key column routes at all, bounds padded temporaries for skewed string/bytes sequences, assembles exact public errors, and retains the reference encoder for mixed objects, trailing-NUL Python sequences, dates, and non-finite row diagnostics. Declined *data* (status 1) falls back; an out-of-contract *layout* (status 4) raises, so the two cannot be confused into a silent slow path |
| static display-list raster, row-banded polyline/point/segment paint, batched fill+stroke triangle meshes, affine scatter projection plus typed color/size resolution, density/heatmap colormap and sampling | Rust (ABI v36) | correct — commands borrow f32/u8 payload or canonical spans synchronously; compact stratified sampling reuses factorization counts; batched/banded output is byte-identical |
| signal processing: `xyg_rfft`, `xyg_welch_spectra`, `xyg_spectrogram` | Rust (ABI v36) | correct — O(N) transforms over sample columns; Hann windowing and segment traversal are native, with Matplotlib-compatible `detrend_none` defaults; explicit pyplot detrending modes fail loudly until the kernel can select them deliberately |
| geometry/triangulation: `xyg_delaunay_triangles`, `xyg_polygon_triangles`, `xyg_marching_squares`, `xyg_marching_triangles`, `xyg_streamlines`, `xyg_vector_segments`, `xyg_quad_mesh_triangles`, `xyg_sector_triangles`, `xyg_indexed_triangles`, `xyg_triangle_edges` | Rust (ABI v36) | correct — output is screen-bounded index/vertex buffers; level choice and styling stay in Python |
| statistics: `xyg_correlation`, `xyg_weighted_ecdf`, `xyg_binned_ecdf`, `xyg_histogram_bins`, `xyg_histogram2d`, `xyg_stacked_bounds` | Rust (ABI v101) | correct — row-scan reductions; 1D automatic histogram edge policy, uniform/irregular counting, density, and cumulative assembly are Rust-owned while labels remain host presentation. ABI 100 binned ECDF owns finite filtering, automatic/constant domain, bounded uniform counting, all-finite-mass normalization, empty-bin compaction, right edges, and the zero anchor. ABI 101 `xyg_histogram_bins` owns authored-edge validation, closed-last-bin assignment, density, and cumulative heights with a 10,000-bin ceiling. Unweighted `xyg_histogram2d` fans out with per-worker u64 grids (integer merge, thread-count invariant); the weighted case stays serial because f64 accumulation order must not vary with core count (§21) |
| style/text helpers: `xyg_css_check` (`css.rs`), `xyg_svg_poly_path` (`svg.rs`) | Rust (ABI v36) | correct by a different rule — not O(rows) but O(points)/per-value on the export and validation paths, where per-item Python object churn dominates; error *messages* still assembled in Python |
| ohlc_decimate (when finance returns) | was NumPy-in-kernels.py | acceptable stopgap **only** because candles decimate to ≤px buckets; promote to Rust with the pyramid work |
| tier decisions, hysteresis, drill_seq that change shipped buffers | Rust (dual-host) / thin host assembly | **promote** — hosts must not diverge; see host-parity.md |
| spec emitters, validation messages, transport | Host | correct — keep |
| graph display layouts, force ticks, graph LOD | Rust (`graph` module) | correct — [graph-mark.md](graph-mark.md) |
| sankey layout | Rust (`sankey` module / `xyg_sankey_layout`) | correct — dual-host; Python `_sankey` resolves names + error text only |

### Target Rust ownership (matches the priority list)

binning (1D/2D/channel-aware) ✅/plan · decimation (M4 ✅, OHLC plan) ·
range filtering (`xyg_range_indices` ✅) · implicit uniform and compact-u8
stratified sampling (`xyg_sample_range_indices` / `xyg_stratified_sample_range_u8` ✅) · grouping/category encoding
(`xyg_factorize_fixed` ✅ for contiguous fixed-width values; defensive Python
label canonicalization for mixed objects. Routing is decided by a bounded
4096-row probe on how *repetitive* the column is, never by how many categories
it holds: the native pass exists to keep N records out of Python, so it is
declined only for a near-unique id/key column, where Python must materialize
essentially the whole label set regardless. Wide records cross over sooner —
above 32 B they are declined once the probe is 95% distinct, at or below 32 B
only when it is entirely distinct) · histogram stats ✅ · quantiles (`xyg_quantiles` ✅, linear/NumPy-default) · box stats
(`xyg_box_stats` ✅ Tukey; `xyg_box_geometry` ✅ ABI 99 grouped,
deterministic, bounded Scene geometry; `xyg_violin_density` ✅ fixed smooth
kernel; `xyg_violin_rects` ✅ ABI 98 grouped, normalized, bounded Scene geometry;
`xyg_binned_ecdf` ✅ ABI 100 finite-filtered, normalized, compact right-edge Step
coordinates with a 10,000-bin ceiling; `xyg_histogram_bins` ✅ ABI 101
authored-edge counting plus density/cumulative assembly with the same
10,000-bin ceiling) · hexbin
reducer (`xyg_hexbin` ✅ count/mean/sum) · histogram edges (`xyg_histogram_edges`
✅ NumPy `bins="auto"` / Sturges, used by both composition hosts for omitted
bins, capped at 10,000 bins / 10,001 edges before allocation; invalid or
over-cap results fail without a partial write) · wind-rose bins (`xyg_wind_rose_bins` ✅
sector × speed-band counts; polar bar assembly stays host-side) · contourf
densify (`xyg_contourf_densify` ✅) + corner-mask bands (`xyg_contourf_bands` ✅
ContourPy-style one-masked-corner clip) · bar offsets (`xyg_bar_stack` ✅
grouped/stacked/normalized) · multi-resolution tile
generation (`tiles.rs` ✅, including stable-domain incremental updates) ·
Rust-owned streaming column buffers (`stream.rs` ✅, §5).

## 2. Module boundaries (workspace layout)

The Rust source is a Cargo workspace. `crates/xyg-core` is the only shipped
artifact (`crate-type = ["cdylib"]` product output; `lib` name `xyg_core`, so
the release library is `libxyg_core.so` / `libxyg_core.dylib` /
`xyg_core.dll`). It depends one-way on `crates/xyg-engine` by path; LTO folds
both into the single cdylib, so the crate boundary adds no runtime artifact.
Both crates are `publish = false` — distribution happens through wheels/npm,
never crates.io. `examples/osm/osmium-rs` stays outside the workspace: it is
an example ingestion CLI with its own dependencies and release profile, not
part of the product runtime.

```text
crates/
  xyg-core/src/
    lib.rs              # C ABI shell ONLY: extern "C" fns, pointer/len
                        #   validation and slice construction, ABI_VERSION,
                        #   the ffi_guard panic shield (§3.2 E4). No math.
                        #   Every fn: null/len checks → slice → call
                        #   xyg_engine::* → write out-params. The only crate
                        #   allowed unsafe (with the simd.rs exception,
                        #   §3.4 rule 3). Opaque u64 handles are minted here;
                        #   the process-wide pyramid / force-layout maps still
                        #   live beside the engine types they own (tiles.rs /
                        #   graph.rs) so this split does not retouch the
                        #   force-layout mutex (#18 non-goal).
  xyg-engine/src/
    lib.rs              # module declarations. font.rs and simd.rs stay crate-
                        #   private; every other module is a deliberate `pub
                        #   mod` consumed by xyg-core (publish = false — not a
                        #   crates.io API).
    kernels.rs          # pure safe Rust row-scan kernels (factorization, zone
                        #   maps, encode, sampling, bin_2d, histograms,
                        #   density, selection, M4, geometry, signal). One
                        #   file at this landing; a later domain split must
                        #   not change ABI or chart semantics. No unsafe, no
                        #   I/O.
    raster.rs           # the entire native rasterizer — the whole static PNG
                        #   export path below Python's geometry/scale/colormap
                        #   computation. Consumes a tagged display-list command
                        #   stream (optionally borrowing f32/u8 payload or
                        #   canonical spans) and paints into a straight-alpha
                        #   RGBA8 framebuffer the caller owns:
                        #     · scanline polygon fill, flat + linear gradient,
                        #       with a rectangle fast path
                        #     · SDF/distance-based stroke and point-symbol paint
                        #       (round caps/joins and AA fall out of the metric)
                        #     · affine scatter projection, typed per-point color/
                        #       size resolution, batched triangle meshes, segments
                        #     · image blit incl. density/heatmap colormap sampling
                        #     · text, blitted and bilinearly scaled from font.rs
                        #     · row-banded multithreaded paint (std::thread::scope,
                        #       byte-identical to the serial path) and the fused
                        #       raster→PNG encode via `png`/fdeflate.
                        #   No unsafe; owns the crate's one third-party dep.
    font.rs             # generated by scripts/gen_font.py — do not hand-edit.
                        #   Baked DejaVu Sans grayscale coverage atlas for
                        #   raster.rs: 424 glyph records (advance, w, h, left,
                        #   top, coverage offset/len) at BASE_PX=16 plus the
                        #   row-major coverage bytes, and EXTRA_CODEPOINTS, the
                        #   sorted table of the 329 non-ASCII codepoints. Data
                        #   only — no shaping, no FreeType, no unsafe. Coverage
                        #   limits are a product constraint, not a detail: §2.1.
    css.rs              # tiered CSS value/color validation behind `xyg_css_check`.
    scene.rs            # versioned, bounded canonical scene records. v1 owns
                        #   built-in scatter validation, stroke-inclusive marker
                        #   geometry/symbols, visibility, and SVG construction;
                        #   consumed identically by Python and Node (#58).
    svg.rs              # screen-space coordinate serialization for the SVG path:
                        #   `poly_path` alone, folding parallel f64 x/y arrays
                        #   into one `M`/`L` path-data string with Python-matching
                        #   2-decimal fixed-point trimming (including the `-0`
                        #   case). Rejects length-mismatched, empty, or non-finite
                        #   input by returning None. Deliberately narrow: it
                        #   exists to kill one Python string per point, and the
                        #   broader construction migrates through scene.rs in
                        #   bounded #58 slices; compatibility-only paths remain.
    simd.rs             # AVX2 twins of eligible kernels, runtime-dispatched
                        #   (§3.4). The one place besides xyg-core's marshaling
                        #   layer allowed `unsafe`.
    tiles.rs            # pyramid build/compose/incremental append, plus the
                        #   mean-color planes for channel-bearing traces
                        #   (build_color/compose_color, LOD doc §2/§4.1; colored
                        #   pyramids refuse appends and rebuild lazily). Owns tile
                        #   memory; xyg-core exposes them as opaque u64 handles
                        #   over the ABI (§3.3).
    geo.rs              # GeoColumn / GeoArrow descriptor ingest, CRS + geometry
                        #   validation (EPSG:4326/3857); opaque handles (#47)
    geo_viewport.rs     # GeoViewport camera/projection authority: Web Mercator,
                        #   fit/pan/zoom/bearing, f32 offset encode (#48)
                        #   validation, feature identity (#47; see geospatial.md).
    edge_route.rs       # directed multigraph paint routing (parallels/loops/arrows)
    graph.rs            # graph display layouts, progressive force ticks, CSR,
                        #   graph LOD/cluster/render-graph decisions
                        #   ([graph-mark.md](graph-mark.md)).
    graph_style.rs      # graph labels, v1 semantic paint/scales/legends, states, compounds
    sankey.rs           # sankey layout (`xyg_sankey_layout`), dual-host.
    transition.rs       # stable animation-key encoding (`xyg_transition_keys_fixed`).
    stats.rs            # quantiles + Tukey box/grouped geometry + violin_density +
                        #   histogram_edges (NumPy auto) + wind_rose_bins ✅
    hexbin.rs           # matplotlib-compatible hex lattice (`xyg_hexbin`) ✅
    lod_plan.rs         # view LOD drill/grid decision math ✅ (`xyg_lod_plan`).
    stream.rs           # Rust-owned canonical append buffers (`xyg_stream_*`).
                        # Capacity-doubling f64 store; zone maps on seal
                        # (ZONE_CHUNK splice, bitwise-identical to
                        # kernels::zone_maps). Pyramid build/compose reads
                        # through the handle; in-domain appends mark
                        # intersecting in-RAM tiles dirty (~1 tile/level)
                        # without a full-pyramid rebuild. Not Phase-4 disk
                        # spill. Out-of-core memmap stays host-owned.
```

Contourf corner-mask bands land in Rust as `xyg_contourf_bands` (ABI 57,
pre-rename `xy_contourf_bands`), matching `_contourf_corner_triangles` /
ContourPy one-masked-corner clips. Python `marks._contourf_corner_triangles`
is a thin loader over that entry point; densify remains
`xyg_contourf_densify`.

The size ordering (kernels > raster > core shell > font > graph > css > tiles >
simd > svg) is the stable fact — rasterization is the second-largest thing in
the workspace, and it is not a helper.

Rules: `crates/xyg-core` is the only crate with `unsafe` (except
`crates/xyg-engine/src/simd.rs`, §3.4 rule 3); engine modules are pure functions over
slices (fuzzable, testable without crossing FFI); the engine's public API is
the deliberate re-export list in its `lib.rs`, never an accident of module
visibility; **dependencies are minimized, not prohibited** (policy
2026-07-05): a crate may be added when it pays for itself — measured win,
small dependency tree, well-maintained — and the C-ABI/one-cdylib-per-platform
property is preserved. Note the dev sandbox cannot reach crates.io, so
required crates must be vendored or the sandbox loses local build/test; prefer
feature-gated optional deps (e.g. SIMD argminmax, tsdownsample-class speed)
with the lean build as default.

Release profile (workspace root `Cargo.toml`): `lto = "fat"`,
`codegen-units = 1`, `strip = true`. Fat LTO measured no runtime change over
thin on the §12 native scatter bench (run-to-run noise ±15% dominates) but
cuts the cdylib ~15% (1.51 → 1.29 MB); with the workspace split, fat LTO also
guarantees the path-dependency boundary between xyg-core and xyg-engine costs
nothing at runtime (whole-program optimization sees through it). strip removes
`.symtab`/debuginfo only — `.dynsym`, which ctypes/koffi bind against,
survives. `panic` must stay `unwind`: the C-ABI backstop in xyg-core converts
engine panics into sentinel returns via `catch_unwind`, and `panic = "abort"`
would turn them into aborts of the embedding CPython process (the wasm target
alone builds with `-C panic=abort` in `publish.yaml`, where unwinding is
unsupported anyway). PGO is a known open lever, not adopted: it needs a
per-target training workload and profdata plumbing in the release matrix;
revisit when a benchmark shows a branch-bound kernel on the hot path.

### 2.1 Native text is a bounded subset, and misses are visible

Declining FreeType bought the single-cdylib property (§3.1) and paid for it in
Unicode coverage. `font.rs` bakes exactly 424 glyphs: ASCII 32–126 (95) plus
the 329 codepoints enumerated in `font::EXTRA_CODEPOINTS` — the Latin-1
Supplement and Latin Extended-A letters (U+00C0–U+017F, which carry Western,
Central, and Northern European orthographies), non-ASCII currency symbols,
lowercase Greek (α–ω) and the eleven uppercase Greek letters that differ from
Latin forms (Γ Δ Θ Λ Ξ Π Σ Υ Φ Ψ Ω), math operators
(`∂ ∇ ∈ − ∓ √ ∝ ∞ ∫ ≈ ≠ ≤ ≥`), the left and right arrows only, super/subscript
digits and a handful of subscript letters, typographic quotes, en/em dashes,
and a few symbols (`° ± × · µ ²³¹ …`).

Still absent: Cyrillic, CJK, Arabic, emoji, and the Latin blocks beyond
Extended-A — so Vietnamese (Latin Extended Additional) and Romanian's `ș`/`ț`
(Latin Extended-B) are **not** covered. Coverage is a bounded set of blocks,
not a language guarantee.

The failure mode used to be worse than the coverage gap. `glyph_index` returned
`None` for an uncovered codepoint and the paint loop's `let … else { continue; }`
dropped that character **before** the advance was applied — the glyph was
deleted, not substituted, and the following glyphs closed up over the hole. No
tofu box, no fallback, no warning. `"Müller"` rasterized as `"Mller"`; a fully
non-Latin label rasterized as nothing. The anchoring pass summed advances
through the same filter, so a centered label was positioned on its *shortened*
width — the loss was self-consistent and therefore invisible.

That violated §28 (no silent decisions). `glyph_index`
(`crates/xyg-engine/src/raster.rs`) now
substitutes **U+FFFD** for any codepoint the atlas lacks, so the miss occupies
space and is visible in the output; the anchoring pass sums the replacement
glyph's real advance, so the label's width is honest. Two exceptions stay
invisible on purpose: control and zero-width characters (U+200B–U+200F, U+FEFF)
have nothing to show, and **whitespace maps to the ASCII space glyph** rather
than to a box — locale-aware number formatting emits NBSP (U+00A0) and narrow
NBSP (U+202F) as group separators, and those reach the rasterizer through
ordinary tick labels, where a box would be plainly wrong.

A warning surfaced at the Python export boundary (where messages belong, §4)
remains the complete fix and is not yet implemented. The documented escape for
real coverage is `engine=xyg.Engine.chromium`, and the user-facing statement of
the same limitation lives in `spec/api/styling.md` §"Native text coverage" —
these two must be amended together. The bound applies to the native raster
formats only; the SVG and PDF export paths have their own text contracts.

## 3. FFI protocol — how it evolves without rewrites

### 3.1 What's already right (keep as law)

- **C ABI, no PyO3/N-API**: no per-CPython or per-Node-ABI builds; one cdylib
  per platform serves Python (ctypes) and Node (koffi), and consumers install
  the compiled wheel/package without a Rust or crate-registry dependency.
- **Caller-allocated buffers**: hosts (NumPy / TypedArrays) allocate outputs;
  Rust writes into them and returns counts. No cross-language ownership for
  array data, no callbacks into hosts, no unwinding across FFI.
- **f64 in, f32 out** for geometry (offset-encoded, §16); **u64 for graph
  element indices**; u32 only for explicitly versioned non-graph contracts.
- **Lockstep `ABI_VERSION`** originates in `crates/xyg-core/src/lib.rs` and is
  generated into `python/xyg/_abi_generated.py`,
  `packages/xy-node/src/_abi_generated.js`, `spec/abi/xyg.h`, and the JSON
  contract. Both hosts call `xyg_abi_version()` immediately
  after loading the library, **before binding or calling any other symbol**,
  and fail with expected-vs-observed versions plus a reinstall/build
  instruction — an old wheel never mis-calls a new lib.
- **The native core is the single implementation.** There is no pure-Python
  fallback; every kernel is tested directly against the Rust core, and a
  platform that can't load the core gets a clear ImportError, not a degrade.

### 3.2 Evolution rules (the anti-rewrite discipline)

- **E1 — additive by default**: new capability = new `xyg_*` symbol. Existing
  signatures are immutable once shipped in a release; changing one means a
  new name (`xyg_bin_2d_v2`) + ABI bump, old symbol kept for one minor cycle.
- **E2 — flags-struct for growth-prone kernels**: kernels we *know* will grow
  options (tile fetch, channel binning) take a final `*const FcOpts` pointer
  to a versioned plain-C struct (`{u32 size; ...}`); size-checked so old
  callers pass smaller structs safely. This is how we avoid v2/v3 name churn
  for the pyramid API specifically.
- **E3 — no callbacks across the ABI**: Rust never calls back into Python.
  Progress/streaming = polling functions. Keeps the seam re-entrant and GIL-
  trivial (all kernels release the GIL implicitly since ctypes calls do).
- **E4 — errors are return codes, never panics across FFI.** The panic shield
  has landed: `crates/xyg-core/src/lib.rs` defines `ffi_guard(sentinel, body)`
  — `catch_unwind(AssertUnwindSafe(body)).unwrap_or(sentinel)` — and wraps
  every exported entry point that does work in it (every `extern "C" fn`
  except `xyg_abi_version` and `xyg_scene_version`, which return constants and
  need no shield),
  so any panic becomes that entry point's error sentinel instead of unwinding
  across `extern "C"`. Output buffers may be partially written on that path,
  exactly like the existing invalid-argument paths. Still outstanding:
  sentinels are per-kernel ad hoc
  (`0`, `usize::MAX`, `-1`/`-2`) rather than one documented negative error
  enum; unifying them is a work item for the next ABI bump.
- **E5 — threading stays inside**: parallel kernels use `std::thread::scope`
  inside the call; the ABI stays synchronous. General row scans cross over at
  512k values and scale to at most 18 workers. Zone maps cross earlier, at two
  complete 65,536-row chunks, because chunks are independent and require no
  merge; worker count is also capped by actual chunks. CodSpeed stays serial
  because its simulator sums thread instructions rather than wall time.
  Incremental build = handle + `xyg_pyramid_append`, which mutates a live
  pyramid in place under the registry lock. A polling entry point
  (`xyg_pyramid_poll`) for genuinely async builds is not built; if one is ever
  needed it follows E3 (poll, never call back).

### 3.3 Opaque handles (for tiles/streams)

Arrays-in/arrays-out stops working when Rust must own long-lived state
(pyramid, append buffers). Pattern:

```c
/* build: nonzero handle, or 0 on invalid arguments */
uint64_t xyg_pyramid_build(const double* x, const double* y, size_t len,
                          double x0, double x1, double y0, double y1,
                          uint32_t base_dim);
/* build with mean-color planes (LOD doc §2). The color source is exactly
   one of idx (per-point LUT index, with lut as 1..=256 RGBA8 rows) or
   rgba (per-point straight-alpha RGBA8); the other pointer is NULL */
uint64_t xyg_pyramid_build_color(const double* x, const double* y, size_t len,
                                const uint8_t* idx, const uint8_t* rgba,
                                const uint8_t* lut, size_t lut_len,
                                double x0, double x1, double y0, double y1,
                                uint32_t base_dim);
/* append: 1 applied; 0 on stale/busy handle, bad args, a point outside
   the pyramid's original domain, or a colored pyramid (its colors are
   unknown to this entry point — caller invalidates and rebuilds lazily).
   Never partially mutates. */
int32_t xyg_pyramid_append(uint64_t handle, const double* x,
                          const double* y, size_t len);
/* count over a window: 1 ok, 0 on stale handle/bad args */
int32_t xyg_pyramid_count(uint64_t handle, double lo_x, double hi_x,
                         double lo_y, double hi_y, double* out_count);
/* compose window into a w×h grid: level used (>=0), -1 stale/bad args,
   -2 window outresolves the pyramid past max_upsample (caller re-bins
   exactly and discloses) */
int32_t xyg_pyramid_compose(uint64_t handle, double lo_x, double hi_x,
                           double lo_y, double hi_y, size_t w, size_t h,
                           size_t max_upsample, float* out);
/* compose plus the mean-color plane: counts bit-identical to
   xyg_pyramid_compose; -2 also for a pyramid built without color planes */
int32_t xyg_pyramid_compose_color(uint64_t handle, double lo_x, double hi_x,
                                 double lo_y, double hi_y, size_t w, size_t h,
                                 size_t max_upsample,
                                 float* out, uint8_t* out_rgba);
/* free: 1 if it existed, 0 for stale/unknown */
int32_t xyg_pyramid_free(uint64_t handle);
/* stream store (introduced in ABI 59): Rust-owned canonical f64. 0 handle / 0 status on
   stale/busy/bad args. Pyramid fetch may read through these handles. */
uint64_t xyg_stream_new(const double* data, size_t len);
int32_t  xyg_stream_append(uint64_t handle, const double* data, size_t len);
int32_t  xyg_stream_seal(uint64_t handle);
int32_t  xyg_stream_free(uint64_t handle);
uint64_t xyg_pyramid_build_from_stream(uint64_t x, uint64_t y,
                                      double x0, double x1, double y0, double y1,
                                      uint32_t base_dim);
int32_t  xyg_pyramid_append_from_stream(uint64_t pyramid, uint64_t x, uint64_t y,
                                       size_t tail_len);
```

Note this API took explicit bounds plus `base_dim` rather than the E2
flags-struct; the option set stayed small enough that a versioned `FcOpts`
would have been ceremony. E2 still governs the channel-binning kernels.

Handles are indices into a Rust-side registry (mutex-guarded slab), not raw
pointers — a stale/double-freed handle is an error code, not UB. Python wraps
each in an object with `__del__`/weakref finalizer.

### 3.4 SIMD (contained in `crates/xyg-engine/src/simd.rs`)

The cdylib builds for baseline x86-64 (SSE2), so hot scans never see 256-bit
registers unless we ask. `simd.rs` holds branch-free clones of selected
kernels compiled under `#[target_feature(enable = "avx2")]` (LLVM
autovectorizes them — no hand-written intrinsics unless a loop demonstrably
fails to vectorize) with runtime `is_x86_feature_detected!` dispatch and a
`XYG_SIMD=0` kill switch.

Rules, in priority order:

1. **Bitwise parity is non-negotiable.** Only order-independent kernels are
   eligible: integer counts, exact comparisons, truncation casts, min/max.
   Float *accumulation* (zone-map sum/sum_sq) must stay scalar — vector
   reassociation changes the result. Parity is enforced by fuzz tests in
   `simd.rs` comparing SIMD vs scalar on hostile data.
2. **Only measured wins ship.** Every dispatch is justified by a before/after
   number (via the kill switch); a kernel where the two-phase restructure
   loses (M4's sequential bucket state machine, histogram's scatter-dominated
   loop) is documented at its scalar definition and NOT dispatched.
3. **`unsafe` containment.** This module is the one exception to "unsafe only
   in the `xyg-core` marshaling layer": the `#[target_feature]` wrappers are
   unsafe to call, and every call site sits behind a safe `try_*` fn that
   checks detection first. Kernels code never writes `unsafe` — it calls
   `simd::try_*` and falls back.
4. **aarch64 needs no twin.** NEON is part of the aarch64 baseline, so the
   scalar kernels already autovectorize at full width there.

### 3.5 ABI manifest and parity gate (machine-checkable contract)

The Rust `extern "C"` surface is the single typed signature authority. Issue
[#57](https://github.com/CurateLabs/xyg/issues/57) replaced hand-maintained
ctypes/Koffi prototypes with deterministic generated artifacts:

- `scripts/gen_abi_manifest.py` parses the `extern "C"` surface of
  `crates/xyg-core/src/lib.rs` (ordered argument names, scalar widths, pointer
  const/mutable direction and depth, return types, buffer metadata, and
  `ABI_VERSION`) and writes `spec/abi/xyg-abi.json`, `spec/abi/xyg.h`,
  `python/xyg/_abi_generated.py`, and
  `packages/xy-node/src/_abi_generated.js`.
- `python/xyg/_native.py` and `packages/xy-node/src/native.js` retain library
  discovery, version-first loading, pointer coercion, public errors, and
  ergonomic wrappers, but contain no function signatures.
- `scripts/check_abi_parity.py` regenerates all four artifacts byte-for-byte,
  validates both complete host symbol sets and the focused stdlib smoke, and
  rejects signature-hash changes without an `ABI_VERSION` bump. The drift
  comparison scans all available manifest history rather than a bounded
  revision window; missing generated consumers fail with the regeneration
  command instead of an incidental file-read traceback.
- Run `python3 scripts/gen_abi_manifest.py --write` for every ABI change. The
  generated files are never edited directly; staleness and version skew fail
  in tests and CI before either host can load another symbol. CI structurally
  verifies that this freshness command executes in its named hard-gate step.

## 4. What Python keeps forever

Composition and pyplot APIs, Reflex integration, ingest normalization
(pandas/Arrow/dtype coercion), validation and error-message text, notebook
lifecycle, and widget/comm transport. Thin wrappers may assemble Rust-produced
scene records into idiomatic Python objects, but canonical spec/scene emission,
tier/budget decisions, channel encoding, layout, and static-export construction
must not remain Python-only; [#58](https://github.com/CurateLabs/xyg/issues/58)
moves those decisions into Rust in vertical slices. This host layer is the
product's Python personality; keeping it is a feature. Node owns the same
ergonomics role for JS users
([host-parity.md](host-parity.md); [host-neutral-architecture.md](host-neutral-architecture.md)).
Python-only forever: composition API, pyplot, Reflex, and embedding a copy
of the paint client in the wheel. Canonical f64 values move to Rust
`stream.rs` (#22); they must not remain a NumPy-only store.

## 5. Streaming append (Rust `stream.rs`)

**Landed:** `crates/xyg-engine/src/stream.rs` owns chunked (capacity-doubling)
canonical f64 append buffers behind opaque `xyg_stream_*` handles. Zone maps
are computed on `xyg_stream_seal` with a ZONE_CHUNK splice bitwise-identical
to `xyg_zone_maps` over the concatenated column. `xyg_pyramid_build_from_stream`
/ `xyg_pyramid_append_from_stream` read x/y through those handles, so pyramid
fetch/compose does not require the host to pass full canonical arrays on every
call. In-domain appends increment the in-RAM count grid **and** mark
intersecting `TILE_DIM`² tiles dirty (~1 tile/level for a one-region stream);
domain growth still refuses the increment and the host invalidates for a lazy
full rebuild, recorded as `append.pyramid: "invalidate"` vs `"dirty-tiles"`
(§28 — a full-pyramid rebuild is never dressed as incremental). The append
refresh payload does not call `_ensure_pyramid` after invalidate: the next
density view is the rebuild. Colored pyramids still refuse native append and
invalidate (`tests/test_density_mean_color.py`).

Hosts stay thin: Python `Column.append` / `Figure.append` coerce ingest and
hold the handle (plus sticky encode offsets); they do not own the growable
f64 backing store. `ColumnStore` remains bookkeeping (ids, kinds, offsets,
Arrow/NumPy coercion). Node binds the same symbols. Out-of-core memmap
columns (`python/xyg/_ooc.py`) cannot sit behind this first in-RAM handle and
stay host-owned — a follow-up, not Phase-4 disk spill (#8).

**Historical (Phase-0, Python-side canonical):** `Column.append` grew an
amortized NumPy buffer and extended zone maps incrementally. `Figure.append`
validated atomically (line appends must continue the sorted series;
categorical channels and shared columns are rejected for now), updated or
freed the trace's pyramid, exited any drill, and returned an `append`
message carrying a complete fresh payload in the split layout — screen-bounded
by construction (§29). Those user-visible contracts are unchanged; only
ownership of the growable f64 store moved into Rust. Encode offsets stay sticky
across appends (`Column.suggest_offset`). The client updates only the traces
named in `affected`.

Phase-4 disk-resident tile spill (#8) consumes this dirty-tile set; it does
not own the canonical store. This is not npm packaging (#23).

### 5.1 Ordered out-of-core range reads (`chunked_columns.rs`)

The first #110 slice moves ordered Tier-3 viewport selection into Rust. A
versioned local `XYGC` artifact holds paired canonical f64 rows, per-chunk x/y
zone maps, and a fixed-size endpoint/min/max envelope built in one streaming pass. Version
2 appends `(canonical_row_id, x, y)` overview records after detail rows; version 1
remains readable and truthfully returns an empty overview. `ChunkedColumns::open`
rejects short, mis-sized, unsupported,
non-contiguous, or unordered metadata before a handle becomes visible. The
range reader binary-searches ordered x maps, prunes optional y ranges, enforces
a byte budget before positioned reads, applies the exact predicate, and checks
an atomic, monotonic viewport-generation watermark between chunks (older host
requests cannot move cancellation backwards). Reserved fields and all zone-map
bounds are validated and non-finite metadata fails closed. Its provenance
record makes chunk/byte reduction auditable; out-of-budget diagnostics report
both the required and configured bytes. ABI v79 gives Python and Node identical
thin open/overview/read/cancel/free surfaces and stable read error codes. ABI
v83 adds a Rust-owned resumable viewport cursor: Python and Node expose
pull-driven `pages` iterators whose every page is capped by canonical bytes,
advances only at checked chunk boundaries, reports progress/done provenance,
and checks the same generation watermark before and after each positioned
read and once more before publication. A generation superseded during the
final read therefore returns cancellation rather than a stale last page. This
lets a viewport larger than the resident budget refine without allocating or
reading the whole selection; a single chunk larger than the page budget fails
with the exact required byte count instead of weakening backpressure.
`overview(max_points=2048)` is caller-bounded, includes first/last coverage when
reduced, retains canonical u64 row identity, and records available points, source
rows, and zero detail rows read. Fully non-finite overview windows are omitted
without rejecting an otherwise valid detail chunk.

ABI v84 adds the versioned `xyg_scene_support_reason` authored-feature
predicate. It returns Rust's stable ordered diagnostic verbatim, so Python and
Node cannot silently diverge on polar, custom-font, browser-CSS, gradient, or
deferred chrome support policy.

This is not yet the complete issue `#110` store: remote ranges, browser/WASM bounded
staging, spatially unordered data, chart-lifecycle overview/refinement wiring,
and larger-than-RAM browser evidence remain open.

## 6. Implementation order

E4's panic shield and the `tiles.rs` pyramid handles (LOD phases 3-4) have
landed; the remainder, in order:

1. E4 error enum — unify the ad-hoc per-kernel sentinels into one documented
   negative enum (with the next ABI bump, cheap insurance).
2. `xyg_bin_2d_channels` (LOD doc phase 1) — first FcOpts-style kernel.
3. Fold drill visible-count into `xyg_range_indices` (one pass, count+idx).
4. `stats.rs`: `xyg_quantiles` + `xyg_box_stats` + `xyg_violin_density` ✅;
   `hexbin.rs`: `xyg_hexbin` (count/mean/sum) ✅; `xyg_histogram_edges`
   (NumPy `bins="auto"` = min of Sturges bandwidth and FD floored by
   `sqrt/2`) ✅.
5. `stream.rs` append ✅ (Arrow ingest already landed).
