# Building a Faster Charting Engine — Complete Design Dossier

*A single compiled record of the design, the competitive research that validates it,
the performance estimates, and the full audit trail.*

---

## Product identity — XYG (read first)

This dossier is the historical and technical core of **XYG**, an independent,
GraphForge-oriented graph and data-visualization engine. The architecture has
evolved past the original "Python-only binding" framing recorded below: today
**Rust owns every decision** that changes shipped buffers, layouts, encodings,
LOD/aggregation choices, or recorded §28 outcomes; **Python and Node are thin
host bindings** over one native C ABI (`libxyg_core`, `crates/xyg-engine` +
`crates/xyg-core` — see [design/rust-engine.md](design/rust-engine.md) and
[design/host-parity.md](design/host-parity.md)); and browser TypeScript owns
paint/pick/gesture/accessibility/lifecycle while direct browser compute is the
same Rust engine compiled to WASM under #59. Where a section below says "Python owns"
a buffer-affecting decision, the host-parity placement rule supersedes it.
The exhaustive current file ownership and migration destinations are enforced
by [design/ownership-audit.md](design/ownership-audit.md).

The project began as a fork of `reflex-dev/xy`; XYG names in this document are
provenance and remain valid as the historical record. The canonical naming
matrix and migration order live in
[design/xyg-naming.md](design/xyg-naming.md).

---

## Thesis in one paragraph

Plotly's cost scales with **how much data you have**; this engine's cost scales with
**how many pixels are on screen**. That inversion is bought by four changes, each of
which removes a different one of Plotly's ceilings: **GPU instanced rendering** (not one
SVG node per point), **typed binary transport** (not JSON parsing), a **native
Rust core in the Python process** (not main-thread compute), and — the real unlock — a
**multi-tier level-of-detail system** that never draws or ships more primitives than the
screen can show. One Rust core runs natively inside the Python kernel doing all heavy
work; a thin JS/WebGL2 client in the browser composes screen-bounded tiles on the GPU
today, with #59 tracking the same Rust engine as a direct-browser WASM path. The result targets
**100M–1B+ points interactively** at **12–24 bytes/point** (direct) or screen-bounded
memory (aggregated) — versus Plotly's practical ~1M ceiling.

Every claim in this dossier is **mode-scoped and testable** — no universal numbers.

---

## How to read this document

1. **Part 1 — The Design** (§1–§37): the full specification. §1–§14 are the core; §15–§31
   fold in two prior audit rounds; §32–§37 add the Python-only architecture, distribution,
   filtering, theming, and the transfer protocol.
2. **Part 2 — Competitive Research**: how the fastest libraries in the field actually
   work, and where each of the six core bets is validated, corrected, or extended. All
   sourced.
3. **Part 3 — Performance Estimates**: projected standing vs standard Python **and** React
   charting libraries.
4. **Appendix A — Audit Log (round 3)**: the raw adversarial review that produced Part IV.

## Status — resolved vs outstanding

| Audit round | Findings | Disposition |
|---|---|---|
| Round 2 (self) | 15 findings | Resolved in-place → §15–§26 |
| Round 3 (external) | 10 findings | Resolved in-place → §27–§31 |
| Round 3 (deep, Appendix A) | F1–F3 (Critical/Major) | **F1–F2 resolved** → Part IV (§32–§35): distribution, filtering. **F3 specified, not implemented** — the tier decision is still count-only and vertex buffers are unchunked (§5) |
| Round 3 (deep, Appendix A) | **F4–F12** | **Outstanding** — not yet folded into the spec (see below) |
| Round 4 (styling) | F-S1–F-S3 | **Partly resolved** → §36: probe-element color resolution shipped; client-side export parity shipped, kernel-side theme snapshot and indexed series tokens still pending |

**Outstanding work (F4–F12), the honest to-do list:**
- **F4** — per-trace f32 offsets (a single viewport origin can't serve traces at wildly
  different coordinate magnitudes). *Augments §4/§16.*
- **F5** — aggregation algebra for per-point color: **shipped as mean point color**
  (Tier-2 surfaces wear the per-cell alpha-weighted mean of the resolved point
  colors, count drives only the alpha — LOD doc §2). Non-color reductions
  (mean/max of arbitrary value channels as *data*, size) remain unmodeled. *Augments §5.*
- **F6** — per-*view* colormap normalization domain (else zoom flickers brightness).
  *Augments §5.*
- **F7** — streaming into the pyramid: `+=`/`-=` across levels; min/max tiles need
  periodic rebuild under eviction. *Augments §28.*
- **F8** — scope the "logically identical across targets" guarantee to bit-identical
  *aggregate buffers*, pixels diffed per-backend. *Augments §21.*
- **F9** — pyramid storage cost is undercounted for multi-trace / multi-channel / fine
  levels. *Augments §27.*
- **F10** — the "Plotly ~40–100 B/pt × 3 copies" figure is unverified; relabel as an
  estimate pending a heap-snapshot, lead with the measured ~14× (plotly-resampler).
  *Augments §1/§2.*
- **F11** — fuzz the Arrow IPC ingest path for served/multi-user apps. *Augments §29.*
- **F12** — reframe the tile pyramid as *unifying live interaction with the pyramid +
  index*, not a novel invention (datashader's `render_tiles` + XYZ tiles are prior art).
  *Augments §5.*

---
---


# Part 1 — The Design

# High-Performance Charting Engine — Design Plan

**Goal:** A Plotly-compatible charting engine that renders *orders of magnitude* more
data, interactively, using a *fraction* of the memory — while running everywhere
Plotly runs (browser, Python/R/Julia bindings, notebooks, static export).

The whole plan is organized around two hard requirements:

1. **Data scale** — smooth interaction at 10M–1B+ points, not 10k.
2. **Memory** — a small, bounded, predictable footprint; target ≤ ~4–8 bytes per
   point resident, versus Plotly's effective ~40–100+ bytes/point.

Everything below is justified against one of those two.

---

## 1. Why Plotly is slow and memory-hungry (the things we must not repeat)

| Root cause | Effect on memory | Effect on data scale |
|---|---|---|
| **Data embedded in JSON** (`x: [1.0, 2.0, …]`) | Each number is ~15–20 bytes as a JSON string, then an 8-byte boxed JS number after parse | Parse time is linear and huge; blocks main thread |
| **Multiple copies of the data** — user `data`, `gd._fullData`, and `calcdata` are separate arrays | 2–4× duplication of every array | More GC pressure, slower updates |
| **One SVG DOM node per point** (2D default) | Each node is hundreds of bytes of DOM + style | Browser dies at ~10⁴–10⁵ nodes |
| **Calc/layout on the main thread, every update** | — | UI freezes on large data or streaming |
| **No level-of-detail** — draws every point even when 10M map to 800px | Holds all points hot | Wasteful; the screen can't show them anyway |

Our design negates each row directly.

---

## 2. Performance & memory targets (acceptance criteria)

| Dataset | Plotly today | This engine (target) |
|---|---|---|
| 100k point scatter | sluggish pan/zoom (SVG) | 60fps, <10 MB resident |
| 1M point line | often unusable | 60fps via decimation, <20 MB |
| 10M point scatter | OOM / crash | 60fps via GPU aggregation, <100 MB |
| 100M+ / out-of-core | impossible | interactive via viewport tiling, bounded RAM — **realized**: disk-backed canonical `mmap` store (§27) renders a large scatter with 0 RAM-resident canonical bytes and a screen-sized engine-resident set (the density pyramid), not data-bounded |
| Resident bytes/point | ~40–100+ | **mode-dependent — see below** |
| Streaming append | full re-serialize | O(appended), ring buffer, constant memory |

Bytes/point, honestly, by mode (a bare "4–8" was payload-only arithmetic — f32 x,y is
already 8, before validity bits, color/size/selection channels, indices, LOD cache,
staging, and GPU alignment; the full ledger is the Memory Model, §27):

| Mode | Target (all-in: canonical + derived + GPU + overheads) |
|---|---|
| Direct scatter, x/y only | **≤ 12** bytes/pt (8 payload + masks/indices/staging amortized) |
| Direct scatter, typical (color/size/selection) | **≤ 24** bytes/pt |
| Decimated line (Tier 1) | ≤ 12 bytes/pt canonical + **screen-bounded** derived |
| Aggregated / tiled (Tiers 2–3) | canonical may be out-of-core; **resident memory screen-bounded**, not data-bounded (+~1.33× pyramid on stored aggregates) |
| Streaming ring | **constant**: capacity × per-point cost, regardless of history |

"Screen-bounded" is a claim about *resident* memory in aggregated/tiled modes only —
it is **not** a universal engine property, and benchmarks report each mode separately
so the happy path can't stand in for the whole (§12).

If a milestone doesn't move one of these numbers, it's not in scope for that milestone.

---

## 3. Architecture at a glance

```
┌───────────────────────────────────────────────────────────────┐
│  Language bindings (Python / R / Julia / JS)                    │
│  - build a DATA-LESS spec  {traces, layout}                     │
│  - hand off data as Apache Arrow columns (zero-copy from pandas)│
└───────────────┬───────────────────────────────────────────────┘
                │  spec (small JSON) + typed column buffers (binary)
                ▼
┌───────────────────────────────────────────────────────────────┐
│  CORE  (Rust cdylib, C ABI — runs inside the Python process)    │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ Ingest &    │  │ LOD /        │  │ Scene graph (retained) │ │
│  │ column store│→ │ decimation / │→ │ + diff engine          │ │
│  │ (1 copy)    │  │ aggregation  │  │                        │ │
│  └─────────────┘  └──────────────┘  └────────────────────────┘ │
│         loaded via ctypes; NumPy buffers passed by pointer       │
└───────────────┬───────────────────────────────────────────────┘
                │  GPU buffers (uploaded once)   +  draw commands
                ▼
┌───────────────────────────────────────────────────────────────┐
│  RENDER  WebGPU (primary) / WebGL2 (fallback) — one <canvas>    │
│  - instanced draws for marks; density textures for aggregates   │
│  - DOM/SVG only for chrome (axes text, legend, tooltip)         │
└───────────────────────────────────────────────────────────────┘
```

An in-browser WASM core running in a Web Worker was deferred in favor of the
native-in-kernel core (§32). Issue #59 now reactivates it as an additional
direct-browser host using transferables by default and SharedArrayBuffer only
where isolation permits; it does not replace native Python/Node execution.

The two requirements live primarily in the **data pipeline (§4–§6)**. The renderer
(§7) matters, but memory and scale are won or lost in how we store and reduce data.

---

## 4. The data pipeline — single-copy, columnar, typed (this is the core of the memory story)

**Principle: one physical copy of every value, from ingest to GPU.**

- **Ingest as Apache Arrow — with an honest copy count.** "Zero-copy" is true only
  *within a process*. Polars and Arrow-backed pandas hand columns to the binding with
  zero copies; classic NumPy-backed pandas costs **one** conversion copy at ingest
  (numeric NumPy → Arrow can often alias; object/string dtypes cannot). Crossing a
  process boundary (kernel → browser, server → client) is never zero-copy for anyone —
  the achievable bound is **one binary transfer with no re-encoding**: the compact
  GPU-ready blob written once, moved as binary HTTP/websocket/comm frames (never
  base64/JSON on live paths), landing as
  a JS `ArrayBuffer` used in place. The claim we actually make: **minimum possible
  copies per boundary, and zero *format transformations* end-to-end** — the bytes that
  leave pandas are byte-layout-identical to the bytes the GPU upload reads. Per-path
  copy budgets are specified in the Transport Matrix (§29).
- **Column store is the single source of truth.** A trace's `x`/`y`/`color` are
  *references* (column id + offset + length) into immutable canonical buffers. The
  calc/LOD stages produce *derived* buffers only when they must (e.g. a decimated
  view), never a defensive clone of the raw data. Contrast Plotly's `data` +
  `_fullData` + `calcdata` triplication.
- **Struct-of-Arrays, not Array-of-Structs.** `x[]`, `y[]` as contiguous typed
  arrays — cache-friendly, and each column uploads to the GPU as one vertex buffer
  with no marshalling.
- **f32 on the GPU via offset encoding — not naive f32.** f32 has a 24-bit mantissa;
  a millisecond epoch timestamp (~1.7×10¹²) doesn't fit, so *every time series* would
  be corrupted by a naive "f32 by default" rule. The default mechanism is therefore:
  keep the column's source dtype (i64 timestamps, f64 where given) in the store,
  compute a per-column **offset + scale** at ingest, and upload *relative* f32
  (`(v − offset) × scale`). The offset/scale ride in the view transform, which stays
  f64 on the CPU. This preserves the 4-bytes/point GPU footprint *and* full precision
  for large-magnitude/small-delta domains (time, finance, geo). Deep zoom re-centers
  the offset when the visible range's relative span approaches f32 resolution
  (~1 part in 10⁷) — see §16. Most charts don't need 15 significant digits to fill
  800 pixels, but the digits they do need must be the *right* ones. Full-payload
  offsets are additionally *sticky under streaming appends*: once shipped, a
  column keeps its offset while every value stays within one span of it (at most
  one f32 mantissa bit worse than a fresh midpoint; a right-growing stream never
  exceeds that), so consecutive append payloads keep byte-identical prefixes and
  the client can upload only the appended tail (wire-protocol §4).
- **Dictionary-encode categoricals** (Arrow gives this for free): store small int
  codes + one dictionary, not repeated strings.
- **GPU residency = the CPU copy can be dropped — but WASM makes "dropped" subtle.**
  wasm32 linear memory is capped at **4 GB** and, once grown, **does not shrink back
  to the browser** — `free()` returns pages to the allocator, not the OS. Ordinary
  JS `ArrayBuffer`s cannot alias wasm32 linear memory, so a WASM core cannot operate
  on them through zero-copy Rust slices. Canonical browser columns remain in
  JS-owned buffers; the Worker transfers them without a main-thread clone and copies
  only bounded operation chunks into a fixed-budget WASM staging arena. Full-data
  scans stream chunks rather than making the whole dataset resident in linear memory.
  Rust keeps only bounded derived/scene outputs and scratch inside the arena. The
  arena is explicitly budgeted so wasm32 growth cannot ratchet up with dataset size.
  wasm64/memory64 lifts the address cap where supported but does not remove the
  JS→WASM copy boundary. On native, columns stay `mmap`'d and the OS pages them.

  **Ownership model (resolving a real contradiction):** an earlier draft said the CPU
  copy "can be dropped after GPU upload" — but Tiers 1–3 *recompute* decimations and
  bins from raw columns on zoom, and picking/export/drill also read them. Data that
  exists only in VRAM can't serve any of that (readback is slow, and WebGL2 readback
  paths are worse). So the default is: **the canonical store is CPU-side (Rust
  `xyg_stream_*` handles for in-RAM columns; mmap / host arrays for out-of-core;
  GPU buffers are a cache)** — droppable,
  rebuildable, byte-budgeted (§6). Dropping the CPU copy is a narrow, *explicit*
  opt-in for static Tier-0 traces, and it visibly downgrades the trace (no re-tier on
  zoom, bin-level hover only, no export from source). Full accounting in the Memory
  Model (§27).

**Memory accounting example — 10M point scatter:**
- Plotly: JSON payload alone is ~200–400 MB of text; post-parse, arrays + boxed
  values + SVG attempt → gigabytes / crash.
- This engine: `x` f32 (40 MB) + `y` f32 (40 MB) = **80 MB**, uploaded once to GPU,
  then the CPU copy is freed → ~0 resident CPU, 80 MB VRAM. And with aggregation
  (§6) the GPU only ever holds a screen-sized density texture (~a few MB).

---

## 5. Data-scale strategy — a multi-tier Level-of-Detail (LOD) system

The key insight: **never push the GPU more primitives than the screen has pixels.**
The engine picks a tier per trace and re-picks on zoom (operating only on the visible
window). Beyond vertex count, real GPUs impose two other ceilings (both documented by
deck.gl in production):

- **Fill-rate:** fragment work = `count × mark_pixel_area × overdraw`. 10M radius-5
  points ≈ 1B fragment invocations/frame; a 500k-point scatter with large or
  overlapping semi-transparent markers is fill-bound well below any vertex ceiling.
- **Allocation:** Chrome caps a single allocation at ~1 GB; deck.gl documents crashes
  between 10M–100M items during buffer creation for exactly this reason.

**What ships today is count-only:** `tier = f(visible_count)`, hysteresis-guarded.
`drill_decision` / `plan_view_lod` in `python/xyg/lod.py` call Rust
(`xy_drill_decision` / `xy_lod_plan`); hosts assemble wire mode strings only.
Hysteresis uses `DRILL_EXIT_FACTOR = 1.15` (`python/xyg/config.py`) so a trace that has drilled down to
real points stays drilled until the count clearly exceeds the budget again. The client
mirrors the same rule (`LOD_DIRECT_POINT_BUDGET`, `LOD_DRILL_EXIT_FACTOR` in
`js/src/45_lod.ts`). Mark pixel area and overdraw do **not** enter the decision.

*Pending (F3, not implemented):* folding `mark_pixel_area × estimated_overdraw` into the
tier decision, so a dense large-marker scatter trips Tier 2 aggregation at sub-ceiling
counts; and **chunked vertex buffers** (multi-buffer draws, ~128 MB segments) so the
allocation cliff is structurally unreachable. Both remain the intended design; neither
exists in `js/src/` today.

**Tier 0 — Direct.** Upload raw columns, draw with instancing. Simple, exact. The
budget is channel-dependent: `Trace.use_density()` (`python/xyg/_trace.py`) is a
thin packer over `xyg_payload_tier` (ABI 122). Rust picks
`DIRECT_SOFT_CEILING = 2_000_000` when the trace carries a per-point color or size
channel, and `SCATTER_DENSITY_THRESHOLD = 200_000` otherwise (both lockstep in
`python/xyg/config.py` and `crates/xyg-engine/src/lod_plan.rs`; strict `>`). A plain scatter therefore aggregates at 200k — its whole win is
not drawing 10M dots — while a scatter whose per-point color/size aggregation would
destroy stays direct up to 2M. Polar charts always ship direct. `js/src/45_lod.ts` carries the matching 200k client
budget.

**Tier 1 — Decimated lines (LTTB / min-max per pixel column):** for line/area traces
with more points than horizontal pixels, reduce to ~2–4 points per pixel column
(min+max preserves spikes). Computed incrementally in the worker; recomputed only for
the visible x-range on zoom. Turns 100M points into ~a few thousand drawn vertices
with no visible difference.

**Tier 2 — multiresolution aggregation (datashader-style, but tiled):** for massive
scatter and heatmaps, don't draw points — draw a **density texture** that wears the
data's own colors: per cell, the alpha-weighted mean of the resolved point colors,
with the log-tone-mapped count as the alpha channel (LOD doc §2). Constant-color
traces reduce to a count texture tinted with the constant.

The naive version ("bin all points into a screen-sized texture") is *not* "O(points)
once": the bin grid depends on the viewport, so every pan/zoom would re-bin the whole
dataset. The intended design is a **data-space tile pyramid** — the four bullets below
describe that target, not current behavior; see the shipped subset after them:

- At ingest (or lazily on first Tier-2 entry), build aggregation tiles in *data*
  coordinates at power-of-two zoom levels — count/sum per cell, ~256² cells per tile.
  Building level *k+1* from level *k* is a 4→1 reduction, so the whole pyramid costs
  ~1.33× one full pass and its total size is ~1.33× the finest level you keep.
- Rendering a viewport = **compose the intersecting tiles** of the nearest pyramid
  level into the screen texture and colormap. **Pan is pure tile reuse** (fetch the
  newly exposed edge tiles); **zoom steps to the adjacent level**. Per-frame cost is
  O(visible tiles) — never O(points) after the initial build.
- Only zooming *below* the finest prebuilt level triggers true re-binning — and only
  of the points in the visible window (found via the chunk index, §22/§28), with
  stale-while-revalidate + progressive refinement (§17) covering the rebuild.
- Colormapping (including perceptual/log scaling and dynamic-range normalization)
  happens at *composite* time on the aggregate values, so restyling never re-bins.

*Shipped today (`crates/xyg-engine/src/tiles.rs`, `python/xyg/interaction.py`):* a **single square count
pyramid**, not tiles. One trace-wide grid over the full data bounds whose finest level
is `PYRAMID_BASE_DIM`² (2048², `python/xyg/config.py`), each coarser level an exact 4→1
u64 sum saturating to u32 down to 1². Built lazily on the first density view at
≥ `PYRAMID_MIN_POINTS` (2,000,000). There is no per-tile fetch entry point and no tile
addressing — the C ABI is `xy_pyramid_build` / `_append` / `_count` / `_compose` /
`_free`, and composition happens kernel-side over the whole window. `_compose` takes a
`max_upsample` bound: in-RAM traces cap it at 2× so a below-floor window falls back to
the exact `range_indices` + `bin_2d` re-bin, but **out-of-core / huge traces**
(disk-backed `np.memmap`, or > `PYRAMID_NO_RESCAN_ROWS`) pass it unbounded and are
served upsampled from the finest level — an O(N) rescan of a 100 GB+ mmap is not
interactive, and past 2³²−1 rows the per-row index kernels would overflow u32 anyway.
Those traces also get a finer finest level (adaptive `~sqrt(N/target)`, capped
`PYRAMID_MAX_DIM` = 16384²) so the upsampled floor stays as sharp as memory allows.
Level and mode are recorded per update (`binning: "pyramid-L<l>[-upsampled]"`).
Channel-bearing traces build mean-color planes alongside the counts
(`xy_pyramid_build_color` / `_compose_color`, LOD doc §2/§4.1 — same level, same
`max_upsample`, both compose regimes; colored pyramids refuse `_append` and rebuild
lazily), so pyramid-served views wear the data's own colors at any zoom.

*Windowed-exact tier for out-of-core scatter (`python/xyg/_spatial.py`):* the pyramid's
upsampled floor is blocky at metro/city zoom (its finest cell is kilometres wide over a
planet-scale extent). When a trace carries a **spatial index** — points pre-sorted on
disk into a row-major grid of cells with a cumulative-offset header, built by
`osmium-rs`'s `osm-sort` — a zoomed-in window the pyramid can only upsample reads just
the cells it overlaps (one contiguous memmap slice per grid row). This is O(points in
window), not O(N), so deep zoom gets *sharper and cheaper* the further in you go; it
engages only while that count is affordable (`SPATIAL_EXACT_MAX_POINTS`, above which the
instant upsampled pyramid stands). The cheap offsets-only `window_count` (whole-cell
overhang — an upper bound) gates the read; the cells are then gathered **once** and the
tier keyed on the *actual* in-window count:
- **≤ `SCATTER_DENSITY_THRESHOLD` → real points** (`binning: "spatial-points"`), shipped
  from the index as vertices — deep zoom is *crisp individual marks*, the out-of-core
  drill-in the canonical rescan can't afford. Position-only (the index has no row ids /
  channels, §27): gated to constant-styled traces, and a pick returns nothing rather than
  a wrong row (empty drill subset → exact-or-nothing, §16/§17).
- **otherwise → exact grid** (`binning: "spatial-exact"`) via `kernels.bin_2d_f32` (an
  f32-input twin of `bin_2d` that skips the f64 widening that otherwise dominates the
  gather; bit-identical result), binned at **full screen resolution** (one cell per pixel)
  and uploaded **nearest-neighbour** — no coarser grid stretched over the viewport, so no
  upscale blur and no pixelation. The upsampled pyramid keeps `linear` (smooth aggregate);
  the choice rides the wire as `density.filter`.
- The whole windowed-exact tier is gated to traces **without a color channel**: the
  position-only index cannot bin the LOD doc §2 mean-color plane, and a count-only
  surface the shader colormaps is exactly what §2 retired. A color-channelled trace
  keeps its upsampled *colored* pyramid grid instead — blurry beats mis-colored (§28,
  recorded per update by the `binning` value).

The sorted columns are a derived **f32** cache (§27: canonical stays f64, every derived
buffer is rebuildable). *Pending:* tiling proper (per-tile build, fetch, and pan-time reuse), so
"pan is pure tile reuse" is design, not behavior. See `spec/design/lod-architecture.md`
§4 for the full design and its shipped-status ledger.

So the honest cost model of the tiled design: **O(points) once at build, O(visible tiles) per frame,
O(visible points) on deep zoom past the pyramid floor.** This is also exactly the
structure Tier 3 needs (§28) — Tier 2 and Tier 3 share the tile machinery; Tier 3
just adds not-all-tiles-resident.

*Backend reality check — three implementations of the same tier:*
- **WebGPU:** compute shader + atomic adds into a storage buffer. The clean path.
- **WebGL2 (no compute, no atomics):** render points as 1px primitives with
  **additive blending into a float render target** (`EXT_color_buffer_float` +
  `EXT_float_blend`, near-universal in WebGL2) — each fragment adds 1 to its bin.
  Same output, one extra render pass; count-based aggregations (count, sum, and
  mean via two channels) work; min/max aggregations fall back to the worker.
- **No usable float blending:** bin in the worker (SIMD Rust over columnar data,
  ~50–100M pts/s) and upload the finished density texture. Slower to *rebuild* on
  zoom, identical to render.

The tier's *capability* is universal; only its rebuild latency degrades down the
fallback chain. Progressive refinement (§17) hides most of that.

**Tier 3 — Out-of-core / viewport tiling (> RAM datasets):** store columns as chunked
Arrow (row groups / Parquet-like), and stream only the chunks the current viewport
needs. Pre-aggregate coarse "overview" tiles (the Tier-2 pyramid's upper levels) so a
zoomed-out view reads a small summary, and detail chunks page in on zoom. RAM stays
bounded regardless of total dataset size (the "1B points" case).

*Shipped local ordered-column foundation (`chunked_columns.rs`, Phase-4 #110):*
the native engine opens versioned `XYGC` artifacts containing canonical paired f64
rows, checked ordered per-chunk x/y zone maps, and a bounded precomputed overview.
Overview points retain canonical u64 row IDs, so first paint can refine to exact
viewport rows without identity replacement; the overview call records source rows,
available points, and that zero detail rows were read. Overview windows containing no
finite x/y pair are omitted. When a caller requests fewer than the available points,
XYG samples deterministic, evenly spaced overview indices; requests above one point
retain both endpoints, while a one-point request returns the first point. A viewport binary-searches the x
maps, optionally prunes by y, performs positioned reads of only candidate chunks,
and applies the exact row predicate. Every reply records generation, first chunk,
chunks considered/read, and bytes read. A hard byte budget is checked before I/O;
generation changes cancel stale work between reads. Python `ChunkedColumns` and Node
`ChunkedColumns` are thin, behavior-identical hosts. The artifact is local/offline;
no network lookup is attempted. This is the ordered/time-series half of Tier 3 and
does **not** complete this paragraph: remote HTTP range sources, direct-browser WASM
staging, unordered spatial artifacts, and chart-lifecycle overview/refinement wiring
remain tracked by #110.

*"Chunks intersecting the viewport" requires an index — arbitrary row groups don't
know what they intersect.* Two cases: **(a) ordered/1-D data** (time series — the
overwhelmingly common Tier-3 case): chunk zone maps (§22) give x-min/x-max per chunk,
so viewport→chunks is a binary search over sorted ranges. **(b) unordered 2-D scatter:**
zone maps only bound, they don't localize — points get bucketed into the Tier-2
data-space tile grid at ingest (one spatial-sort/shuffle pass, the priciest part of
Tier-3 ingest and stated as such), after which viewport→tiles is arithmetic. The full
per-trace-kind rules live in the LOD/Tiling Contract (§28).

Tier transitions are automatic and hysteresis-guarded (to avoid thrashing at the
boundary), and every downsampling decision is logged so we never *silently* hide data.

### 5.1 Tuning constants — `python/xyg/config.py`

Every tier/decimation threshold lives in one module (§28: no silent decisions). The
table is the complete contents of `python/xyg/config.py`; values are the ones shipped
today. "Read by" lists the modules that *consume* the constant — `python/xyg/_figure.py`
re-exports several of them as a historic import path and is not listed for those.

| Constant | Value | What it gates | Read by |
| --- | --- | --- | --- |
| `PROTOCOL_VERSION` | `3` | Wire-spec version stamped on every payload; the client refuses a mismatch loudly (§33). | `_payload.py` |
| `DECIMATION_THRESHOLD` | `10_000` | Line/area traces with more points than this ship M4-decimated (Tier 1); at or below, raw columns go over the wire. Also gates re-decimation on the interaction path. Strict `>`; `xyg_payload_tier` owns the compile-time choice (ABI 122); `xyg_payload_m4_indices` owns emit/re-decimate (ABI 204). | `_payload.py`, `interaction.py`; lockstep `lod_plan.rs` |
| `SCATTER_DENSITY_THRESHOLD` | `200_000` | Tier-0 → Tier-2 count budget for a scatter with **no** per-point channel (`Trace.use_density()` via `xyg_payload_tier`), and the visible-count budget for view-LOD planning and drill decisions. Strict `>`. | `_trace.py`, `interaction.py`; lockstep `lod_plan.rs`; mirrored client-side as `LOD_DIRECT_POINT_BUDGET` in `js/src/45_lod.ts` |
| `DIRECT_SOFT_CEILING` | `2_000_000` | Tier-0 → Tier-2 count budget for a scatter that **does** carry a per-point color or size channel; above it density is forced and warned about — the color channel aggregates to the surface's per-cell mean point color (LOD doc §2), every other per-item channel is dropped and named, never silently (§5 F5). Strict `>`; `xyg_payload_tier` owns the compile-time choice (ABI 122). | `_trace.py`, `marks.py`; lockstep `lod_plan.rs` |
| `DENSITY_GRID` | `(512, 384)` | Default density-grid cell dimensions for the initial spec, before the client requests a viewport-matched size via `density_view`. | `_payload.py` |
| `MAX_SCREEN_DIM` | `4096` | Upper clamp on any browser-supplied pixel dimension, so untrusted widget/comm input cannot inflate decimation buckets or density grids. | `lod.py`, `_native.py` |
| `MAX_CONTOUR_WORK` | `4_000_000` | Ceiling on contour `cells × levels`; a request over it raises instead of allocating an unbounded segment buffer. | `marks.py`, `_native.py` |
| `DRILL_EXIT_FACTOR` | `1.15` | Hysteresis multiplier on the drill boundary: a trace already drilled to real points stays drilled until the visible count exceeds `budget × 1.15`. | `lod.py` (`drill_decision`, `plan_view_lod`), `interaction.py`; mirrored as `LOD_DRILL_EXIT_FACTOR` in `js/src/45_lod.ts` |
| `DENSITY_TARGET_POINTS_PER_CELL` | `16.0` | Target points per cell when sizing an aggregation grid, so a barely-over-budget view does not get a one-point-per-pixel grid that looks like static and re-ships large. | `lod.py` |
| `DENSITY_SAMPLE_TARGET` | `8_192` | Size of the deterministic real-point sample retained with the FIRST density payload only (#225: interactive density replies ship no samples; the client draws the retained overlay solely below the T9 resolvable-count gate, and the standalone re-bin worker keeps it as its CPU source). Native **raster** exports skip it entirely (`_PayloadWriter(point_overlay=False)`): `_raster._emit_grid` draws density from the grid alone, so sampling it was O(N) work no pixel consumed — output is byte-identical either way (spec/api/export.md). | `_payload.py` |
| `DENSITY_SAMPLE_SEED` | `0` | Seed for that sample; a fixed seed makes the overlay identical across re-ships of the same view. | `_payload.py` |
| `LOD_SAMPLE_FADE_COVER_HI` / `LOD_SAMPLE_FADE_COVER_LO` | `1/4` / `1/32` | Fallback bound on the retained sample overlay (T9): overlays ride their density windows and the drawn one is the best cached window covering the view (full alpha), so the band only governs a view NO cached window covers — the best partial draws at full alpha while its window covers ≥ 1/4 of the view area, hidden below 1/32, log-eased between. The band value is a *composited* opacity target (per-point alpha solved against the expected overplot, `1−(1−band)^(1/k)`), so a partial overlay can never overplot into a false cluster. Every candidate first passes the #225 resolvability gate (estimated in-view count ≤ the direct budget). | `js/src/45_lod.ts` (`lodOverlayResolvable`, `lodSampleViewAlpha`, `lodSampleForView`) |
| `DRILL_PAD_TARGETS` | `(8, 4, 2)` | Ladder of padded-span targets (× the view span) for points-tier replies: the coarsest ALIGNED window around the view whose exact count fits the budget ships, so the client's point-window cache answers nearby pans/zooms with zero round-trips (LOD doc T13). | `interaction.py` (`_padded_drill_window`), `lod.py` (`aligned_window`) |
| `DRILL_PAD_SPAN_CAP` | `64.0` | Hard per-axis cap on a padded drill window's span (× the view span), kept well under the client's §16 re-encode bound (1/256 of window span) so deep zooms can always re-tighten the f32 offset encoding. | `interaction.py` |
| `DRILL_HISTORY_KEEP` | `8` | Recent drilled subsets kept resolvable per trace, so picks against a retired cached point window (T13) still translate exactly; older seqs drop the pick, data changes clear the history. | `lod.py` (`enter_drill`, `drill_history`), `interaction.py` (`pick`) |
| `LOD_POINT_CACHE_WINDOWS` | `3` | Retired exact point windows kept per trace client-side beyond the live drill; LRU-bounded VRAM, swept by the T11 outgrown rule. | `js/src/45_lod.ts` (`lodRetireDrill`, `lodPromoteCachedDrill`) |
| `LOD_POINTS_REQUEST_BAND` | `4` | The aggregate tier never refines per view (T13, revised): a raw-view `density_view` goes out only when the estimated in-view count sits within `budget × 4` of points territory — the LOWER of an area-scaled cached-window count and the retained sample counted in-view (`lodSampleViewCount`, distribution-true where area-scaling over-estimates sparse tails). | `js/src/45_lod.ts` (`lodAggregateStands`) |
| `LOD_AGG_STEP_FACTOR` / `LOD_AGG_STEP_MAX` / `LOD_AGG_STEP_SLACK` | `4` / `2` / `1.5` | The stepped aggregate ladder (T13): while standing, the only density request is the view snapped outward to a power-of-4 block grid over the extent (per axis), at most 2 steps below home, and only when every covering texture is coarser than the step by more than the slack. Quantized windows are pan-stable and dedupable — at most 2 smooth-to-smooth swaps before points, worst-case softness ≈ 4× stretch per axis. | `js/src/45_lod.ts` (`lodAggregateStepWindow`) |
| `DEFAULT_PALETTE` | 8 CVD-safe hex entries | Per-trace default color cycle and the fallback categorical palette, used when the chart sets no `theme(palette=...)` (§20/§36). Its ORDER is the CVD-safety mechanism — never re-order or extend without re-running the validator. | `_figure.py`, `channels.py`, `_svg.py`, `_raster.py` |
| `PYRAMID_MIN_POINTS` | `2_000_000` | Trace size at/above which a Tier-3 tile pyramid is built lazily; smaller traces never pay for one. | `interaction.py` |
| `PYRAMID_BASE_DIM` | `2048` | Edge of the pyramid's base level in cells (`dim²` u32 counts, ~1/3 overhead for the coarser levels); sets resident pyramid bytes. | `interaction.py` |

Nothing in this table folds mark pixel area or overdraw into a tier decision — that is
F3, still pending (above).

---

## 6. Memory-reduction techniques (checklist)

- ✅ Binary Arrow transport — no JSON, no parse bloat, no string numbers.
- ✅ Single physical copy — references through the pipeline, not clones.
- ✅ f64 canonical CPU-side, uploaded as window-centered offset-encoded f32 (§4/§16) —
  *not* "f32 by default", which §4 rejects outright.
- ✅ Struct-of-Arrays typed columns → direct GPU upload.
- ✅ Dictionary encoding for categoricals.
- ✅ GPU buffers are droppable caches, rebuilt from the retained canonical CPU store
  (§27 rule 1); `mmap` on native. Dropping the *canonical* copy after upload is a
  narrow, explicit opt-in for static Tier-0 traces, never the default (§4).
- ✅ Aggregation tiers so hot memory is screen-bounded, not data-bounded.
- ✅ **Ring buffers for streaming** — fixed-capacity circular GPU buffer; appends
  overwrite oldest, constant memory, no re-allocation, no re-serialize.
- ✅ No worker/main-thread data duplication: the core computes in the Python process and
  the client receives screen-bounded buffers over the comm channel (§8/§37). The
  SharedArrayBuffer/transferable-ArrayBuffer scheme belonged to the dropped in-browser
  WASM core (§8).
- ✅ Retained scene graph + buffer diffs — updating a color is a uniform write, not a
  data re-upload.
- ✅ Large canonical columns live outside WASM linear memory in JS-owned ArrayBuffers.
  Direct-browser Rust scans them through bounded copied chunks; linear memory holds
  only the current staging slice, metadata, and screen-sized derived buffers (§4).
  GPU buffers are derived, rebuildable caches rather than canonical storage.
- ✅ Arrow **validity bitmaps** carried through the pipeline — nulls cost 1 bit, not a
  sentinel column (see §19).
- ✅ **Explicit memory budgets with eviction.** VRAM is finite and not queryable in
  browsers: the LOD cache (§10) and Tier-3 tiles run under a byte budget with
  LRU-by-zoom-distance eviction, and everything evicted is recomputable from source
  columns. Includes WebGPU device-loss / WebGL context-loss recovery: the scene graph
  + column store are sufficient to rebuild all GPU state, so loss = a reupload, not
  a crash (see §18).

---

## 7. Rendering core

- **WebGPU primary, WebGL2 fallback.** One `<canvas>`, everything is GPU primitives.
- **Instanced draws** for markers/bars/lines — one draw call for millions of marks.
- **Density textures** for aggregated tiers (§5, Tier 2) — mean point color per
  cell, composited at the points' own alpha (`1−(1−a_pt)^count`, LOD doc §2);
  premultiplied RGBA8 upload for channel-bearing traces, tinted R8
  log-count-ramp texture for constant-color ones.
- **DOM/SVG only for chrome** — axis tick labels, legend, title, tooltip. Little of it,
  and it stays crisp/accessible/selectable.
- **Retained scene graph**, spec-diff → buffer-diff. Pan/zoom is a view-matrix uniform
  update, touching zero data buffers.
- **Versioned canonical scene IR** in `xyg-engine` ([scene-ir.md](design/scene-ir.md)).
  Version 8 extends the backend-neutral typed batch behind the shared Rust ABI:
  canonical viewport/plot bounds and axes; embedded bounded RGBA/stroke styles;
  and independently renderable scatter (symbol + diameter), polyline, and
  rectangle records with stable IDs and extent-aware clipping. Numeric records
  are fixed little-endian bytes, never JSON. The legacy version-1 scatter SVG
  wrapper remains only as a migration consumer. The first #58 whole-scene slice
  compiles constant-style cartesian scatter/line/bar figures in Python and Node,
  then exposes the exact same Scene v12 bytes to explicit Rust SVG and
  native-raster command consumers. Public static exports route the proven
  literal Cartesian subset through those consumers: all 19 constant built-in scatter symbols
  either without authored stroke or with an authored literal constant CSS
  stroke and optional finite non-negative scalar width (default 1px),
  constant-style polyline, ordinary area/error-band Bands,
  bar/column/histogram rectangles, at most 1,024 fill-only unjoined
  triangle-mesh faces (constant or interned per-face fill/stroke/width, ABI 195),
  interned per-item scatter fill/stroke/width/opacity (ABI 196),
  solid ribbons, and
  disconnected `segments`/error-bar/stem endpoint pairs (including the
  immediately-following generated constant built-in stem marker). Gradients,
  rounded corners, dashed or data-driven segment styles, LOD/density,
  nonliteral palettes, triangle-mesh `joined_fill` plus per-face paint,
  larger batches, polar geometry, and
  unmodeled marks retain their
  compatibility renderers. Rust
  now owns chart/plot backgrounds, authored axis side/visibility and
  major/minor tick geometry/paint, default numeric tick/label/grid/spine, and
  the bounded linear/log/symlog/category/angular/time tick ladders exposed to
  both native hosts through one ABI. Python compatibility SVG/raster and pyplot
  call that ABI through one `_svg.axis_ticks` framing function; the obsolete
  per-family Python adapters are retired. `public_static_export` is likewise
  the only optional Python selector for the bounded product route; it reuses
  the predicate's compiled Scene rather than encoding twice, then ABI 164
  `xyg_scene_static_export` owns SVG/PNG/PDF/JPEG/WebP consumers from that
  batch, then ABI 165 folds the figure-compile `XYFS` probe into
  `xyg_scene_encode_product` so product-path hosts do not call
  `xyg_scene_figure_support_reason` separately, then ABI 166 tessellates
  cartesian bar/column/histogram `corner_radius` on that same product Scene,
  then ABI 167 applies polar bar/column/histogram `wedge_gap`, then ABI 168
  tessellates polar bar/column/histogram `corner_radius`, then ABI 169 admits
  polar `curve="smooth"` plus `step` as polar step expansion, then ABI 170
  admits constant scatter `marker_glyph` as Scene `<text>` / `OP_TEXT`, then
  ABI 171 admits scatter `stroke_width` without `stroke` as match-fill, then
  ABI 172 admits cartesian line `curve="smooth"` plus `step` as authored
  step expansion, then ABI 173 tessellates heatmap `corner_radius`, then ABI 174
  tessellates violin/box `corner_radius`, then ABI 175 admits violin/box
  `fill_opacity` / `stroke_opacity`, then ABI 176 admits bar/column/histogram
  `fill_opacity` / `stroke_opacity`, then ABI 177 admits heatmap `fill_opacity`,
  then ABI 178 admits scatter `fill_opacity` / `stroke_opacity`, then ABI 179
  admits hexbin `fill_opacity`, then ABI 180 admits triangle_mesh `fill_opacity`
  / constant stroke paint, then ABI 181 admits cartesian area/error_band
  `curve="smooth"` plus `step` as authored band step expansion, then ABI 182
  admits triangle_mesh `joined_fill` as one identity PolyFill ring, then ABI 183
  admits constant ribbon `color2_ch` as XYGR mark-space `dir=right`, then ABI 184
  admits cartesian unwrapped text `dx`/`dy`/`anchor` as XYAW `wrap=0`, then ABI 185
  admits labelled cartesian marker `dx`/`dy`/`anchor` as XYAW `wrap=0`, then ABI 186
  admits cartesian colormap hexbin as a 1×N XYHP plane interned onto HexCell
  PolyFills, then ABI 187 admits cartesian unwrapped text `rotation` as XYAW
  `wrap=0` (XYAW v2 / XYLB v6), then ABI 188 admits labelled cartesian marker
  `rotation` as XYAW `wrap=0`, then ABI 189 owns heatmap/hexbin cell-fill
  tessellation eligibility from packed XYTA, then ABI 190 intern cartesian
  per-item two-ended ribbon `color2_ch` from packed XYHP kind 5, then ABI 191
  admits constant multi-character scatter `marker_glyph` via XYMG v2, then
  ABI 192 admits polar painted heatmap inverse-raster as one Scene Image blit.
  ABI 193 admits heatmap/hexbin `stroke` / `stroke_width` / `stroke_opacity`.
  ABI 194 admits polar hexbin, custom host reducers, and categorical / `direct_rgba` hexbin.
  ABI 195 admits triangle-mesh custom `role` and per-item fill/stroke/width interned from packed XYHP kind 6 (`joined_fill` plus per-face paint stays fail-closed).
  ABI 196 intern scatter per-item fill/stroke/width/opacity from packed XYHP kind 7 (per-item size/symbol stay fail-closed).
  `FacetGrid.to_svg` / native facet PNG/JPEG/WebP reuse that same compiled
  panel Scene. That predicate
  owns the public PolyFill group budget, including companion traces that share
  the browser painter's 1,024-group ceiling. Explicit
  Scene APIs retain no second fallback predicate. Rust also owns
  chrome ordering, plus bounded primary static legend entry ordering,
  placement, frame, text, and swatch policy;
  fully hidden Cartesian chrome is omitted by Rust lowering without changing
  coordinate semantics—polar Scene projection is explicit XYPL v1 input, never
  an inference from transparent paint. Scene v26 compiles polar line, scatter,
  area, bar/column (PolyFill annular sectors), errorbar, heatmap
  (tessellated lattice cells), contour (SegmentPair polylines), and hexbin
  (HexCell PolyFills); polar
  density remains an explicit unsupported boundary.
  Rust owns the
  selected endpoint-pair order, clipping, SVG, PDF, and raster output;
  nonfinite/missing breaks, custom styles, and every other segment-like mark
  remain explicit compatibility boundaries.
  ABI 95 adds one bounded parallel step-mode enum to the whole-Scene ingress.
  Python and Node pass compact finite f64 line samples for `pre`/`mid`/`post`;
  `xyg-engine` validates stable-id/style run boundaries and zero-valued unused
  endpoint columns, expands the exact ordered Polyline corners, and applies the
  expanded-record budget before Scene v25 encoding. The direct-browser `XYTS`
  v2 vocabulary has no step-mode field
  and continues to reject step authoring rather than inferring host policy.
  ABI 96 adds bounded primary Cartesian numeric-format authoring for
  linear/log/symlog. Hosts pack at most 256 NUL-free UTF-8 bytes per axis in
  the versioned `XYAF` envelope; Rust parses
  `<prefix>(,).N[f|%]<suffix>` with precision `N` from 0 through 100, resolves
  final labels and gutters, preserves
  explicit-label precedence and default-label fallback, then emits existing
  explicit-major plus `XYTL` records. Scene stays v25, legacy raw `XYAD`
  remains valid, and the envelope keeps the batch function below Koffi's
  64-parameter ceiling. WASM ABI 23 exposes the same Rust-owned f64 ladders and
  labels through an atomic, bounded Worker request. `attachWasmTicks` now
  schedules attached automatic, authored-value, and authored-empty primary
  Cartesian linear/log/symlog/category/UTC-time ChartView
  axes and eligible ChartView colorbars onto that lane. Hosted `to_html()`,
  notebook widgets, and Reflex `XYChart` attach via packaged Worker/WASM URLs;
  real-browser Reflex packaged-attach proof is tracked by
  the post-M2 follow-up **Prove Reflex packaged WASM tick auto-attach in a real browser** (related to [#54](https://github.com/CurateLabs/xyg/issues/54)). Polar/secondary families are frozen deferred
  compatibility keepers outside the claimed M2 subset, and srcdoc notebooks
  retain their documented JavaScript tick path.
  ABI 97 generalizes the parallel step-mode column to `expansion_modes` and
  removes static ribbon tessellation from the hosts. Python and Node pack two
  adjacent endpoint rows per finite literal solid ribbon; Rust applies the
  Cartesian axis transforms and expands the curve into 97 paired Band samples
  across `SCENE_RIBBON_STEPS=96` intervals before any consumer sees it. Scene
  stays v25. Gradient, polar, LOD/density, and direct-browser ribbon authoring
  remain explicit boundaries; aggregate production beyond the current
  density/Scene vertical is tracked by the post-M2 follow-up **Expand direct-browser aggregate production beyond the density/Scene vertical** (related to [#54](https://github.com/CurateLabs/xyg/issues/54)).
  Unsupported marks, missing values, and customization fail closed at the
  explicit Scene boundary while records migrate. ABI 84 adds a versioned
  authored-feature presence predicate whose ordered actionable diagnostic is
  Rust-owned and relayed verbatim by Python and Node. Browser paint and interaction lifecycle stay
  in TypeScript.
- **GPU picking** for hover/select — render IDs to an offscreen target, read back the
  pixel under the cursor. O(1) regardless of point count.

---

## 8. Compute & threading

- The Rust core runs **natively inside the Python or Node host process**, loaded as a C-ABI cdylib
  through `ctypes` (`python/xyg/_native.py`; `Cargo.toml` `crate-type = ["cdylib",
  "rlib"]`) or Koffi. The #59 foundation also compiles the same safe engine to
  WASM for a Worker so supported direct-browser paths need no
  Python/Node runtime; it does not run heavy compute on the browser main thread. Heavy
  work stays off the browser main thread, so the UI thread is never the bottleneck for
  big data.
- Heavy stages (decimation, binning, autorange, KDE, stacking) run in the kernel on the
  columnar buffers; NumPy arrays are passed to the core by pointer, without copying.
- The browser side is a **thin JS/WebGL2 client** on the main thread: it mounts,
  forwards input, uploads the screen-bounded buffers the kernel computes, and draws
  chrome. Results arrive over the comm channel (§37), not over `postMessage`, so
  neither SharedArrayBuffer nor cross-origin isolation (COOP/COEP) is required —
  which is what lets the client run in Jupyter, embedded iframes, and third-party
  contexts that cannot set those headers.
- Kernel-less standalone density refinement uses a thin Worker adapter around
  Rust/WASM. When its explicit retained typed source or Worker/WASM artifact
  is unavailable, the client retains the Rust-authored overview texture and
  dispatches `xy:wasm_density_no_refinement`; it never runs a JavaScript
  aggregation fallback.
  The foundation builds a static strict-CSP Worker plus a raw adapter over
  `xyg-engine`; it validates the current canonical Scene and compiles
  transferable scatter/line/bar/area typed series with Rust-owned identities
  and defaults. The current density/Scene vertical also uses Rust/WASM;
  broader production paths are tracked by the post-M2 follow-up **Expand direct-browser aggregate production beyond the density/Scene vertical** (related to [#54](https://github.com/CurateLabs/xyg/issues/54)).
  Transferable ArrayBuffers
  avoid a main↔Worker clone, followed by an explicit bounded copy into WASM linear
  memory. SharedArrayBuffer remains an optional isolated-context optimization.
- The direct-browser product-path successor to whole-source `XYAG` is the
  Rust-owned `XYAS` stream ABI: a fixed header declares the exact f64 domain,
  grid, and total count; only bounded 32,768-point raw x/y chunks are staged
  between cancellation checkpoints; Rust retains only the count grid and emits
  the existing `XYAO` texture payload. This is count-only until the channel
  algebra and product integration have their own bounded contracts; TypeScript
  may transfer/stage chunks but cannot scan, bin, or choose aggregation policy.
- *Historical decision, now narrowed:* the original design made Worker/WASM the
  universal engine. §32 correctly made native host compute primary. #59 restores
  Worker/WASM only for direct-browser execution; it does not force Python/Node hosts
  or notebooks through WASM.
- The *same Rust* compiled **native** does headless static export (PNG/SVG/PDF) with no
  browser — faster than Kaleido. **Consistency claim, stated honestly:** *logically*
  identical (same scales, same layout, same LOD decisions — guaranteed by sharing the
  core), *perceptually* identical within a screenshot-diff tolerance — but **not
  byte-identical**: GPU rasterization is not bit-deterministic across drivers, and
  browser text is DOM-rendered (§7) while native text is shaped by the core's own
  font stack. The native **CPU rasterizer is the deterministic reference image** that
  both targets are diffed against in CI (see §21).

---

## 9. Spec & bindings (keep Plotly's reach)

- Declarative `{traces, layout}` spec, **but data-less** — traces reference columns by
  handle; data travels as Arrow beside the spec. Spec stays tiny and diffable.
- Thin bindings per language build the spec + hand off Arrow (zero-copy from pandas).
- A **`plotly`-compatible shim** maps the common Plotly figure API onto our spec so
  existing code/docs port with minimal changes — the migration story is the moat.

---

## 10. Core data structures (sketch)

```rust
// Immutable, single-copy source of truth
struct Column { id: ColId, dtype: DType /*F32,F64,I32,Dict*/, buf: Arc<ArrowBuffer>, len: usize }

struct Trace { kind: TraceKind, x: ColRef, y: ColRef, style: StyleRef, lod: LodState }

// What actually lives on the GPU
struct GpuTrace { vbo: BufferId, count: u32, tier: Tier, view_uniforms: Mat3 }

enum Tier { Direct, DecimatedLine{px_width:u32}, Aggregated{tex:TextureId}, Tiled{loaded:Vec<ChunkId>} }

struct Viewport { x_range:(f64,f64), y_range:(f64,f64), px:(u32,u32) } // drives LOD selection

// LOD cache keyed by (trace, zoom-bucket) so re-zooming reuses work.
// Byte-accounted: this cache is exactly where "bounded memory" would otherwise
// quietly die. Every entry is recomputable from canonical columns, so eviction
// is always safe.
struct LodCache {
    entries: HashMap<(TraceId, ZoomBucket), DerivedBuffer>,
    bytes_used: usize,                  // maintained on insert/evict
    budget: MemoryBudget,               // per-chart cap + share of global cap (§27)
    lru: EvictionQueue,                 // LRU weighted by zoom-distance from viewport
}
```

---

## 11. Milestones

- **Phase 0 — Prove the memory/scale thesis (spike).** Data-less spec + Arrow ingest +
  WebGL2 direct-draw scatter/line (Tier 0). Benchmark memory bytes/point and FPS at
  100k / 1M. *Exit:* beat Plotly's memory by ≥5× at 1M points.
- **Phase 1 — LOD lines + workers.** Move core to Web Worker; add LTTB/min-max
  decimation (Tier 1) + SharedArrayBuffer. *Exit:* 10M-point line at 60fps.
- **Phase 2 — GPU aggregation.** Density-texture scatter/heatmap (Tier 2). *Exit:*
  10M-point scatter at 60fps, screen-bounded VRAM.
- **Phase 3 — WebGPU backend + native export.** Second render backend; native headless
  PNG/SVG. *Exit:* identical output browser vs native; export with no browser dep.
- **Phase 4 — Out-of-core tiling.** Chunked columns + viewport streaming + overview
  tiles (Tier 3). *Exit:* 100M+ / larger-than-RAM at bounded memory.
- **Phase 5 — Breadth + compat.** More trace types; Plotly-compatible API shim;
  `express`-style one-liners. *Exit:* drop-in for the common Plotly figures.

---

## 12. Benchmark harness (built in Phase 0, run every phase)

- **Datasets:** synthetic 100k / 1M / 10M / 100M; a real streaming feed; a categorical-heavy set.
- **Metrics:** resident memory (CPU + VRAM), bytes/point, pan/zoom FPS, time-to-first-paint,
  streaming append latency, static-export time.
- **Baseline:** the same figures in Plotly, side by side, in CI. A regression on any
  metric fails the build. Every silent cap (top-N, decimation ratio) is asserted and logged.

---

## 13. Risks & mitigations

| Risk | Mitigation |
|---|---|
| WebGPU not universal yet | WebGL2 fallback path from day one |
| Canvas text less crisp than SVG | DOM chrome for all text; native SVG-emit path for small print-quality 2D |
| Ecosystem/trace-type breadth is Plotly's real moat | Plotly-compatible spec + API shim; prioritize the 20% of trace types that are 80% of usage |
| f32 precision in geo/finance | Per-trace f64 opt-in; offset-encoding for large-magnitude small-delta data |
| Decimation hides real features | min-max (not mean) decimation preserves spikes; log every reduction |
| WASM↔JS↔GPU boundary chatter | Batch draw commands; keep the hot loop inside one worker; SAB/transferables |
| SAB unavailable (no COOP/COEP in notebooks/iframes) | Transferable-ArrayBuffer ownership-handoff path is the default design; SAB is an optimization (§8) |
| Timestamps/large magnitudes break f32 | Offset+scale encoding is the default upload path; f64 view transform on CPU (§4, §16) |
| WebGL2 can't do compute-shader binning | Additive-blend float-target binning; worker-side SIMD binning as last resort (§5) |
| Browser caps live GPU contexts (~16 in Chrome); dashboards want 30+ charts | Per-chart context under an LRU governor, budget 12 (§18) |
| VRAM exhaustion / device loss | Byte-budgeted caches with eviction; full GPU state rebuildable from scene graph (§6, §18) |
| Canvas is invisible to screen readers | Structured a11y layer: ARIA summary, keyboard nav, data-table export (§20) |
| WASM bundle bloat vs plotly.js partial bundles | Feature-gated trace modules, size budget in CI (§23) |
| Rebinning cost on every zoom frame breaks 60fps | Stale-while-revalidate + progressive refinement (§17) |

---

## 14. The one-paragraph summary

Store every value **once per boundary**, as **typed columnar Arrow** (offset-encoded
f32 on the GPU, SoA), moved with the minimum copies each boundary permits — zero
in-process, one binary transfer cross-process — and **no JSON or re-encoding anywhere**.
Never draw more primitives than there are pixels: a **multi-tier LOD system** (direct →
decimated → tile-pyramid-aggregated → out-of-core-tiled) keeps *resident* memory
screen-bounded in the aggregated tiers instead of data-bounded, which is what lets it
handle 10M–1B+ points. A **retained scene graph** with buffer-diff updates
and **ring-buffer streaming** keeps memory constant under change. A single **Rust core**
(WASM in-browser, native for export) plus a **data-less Plotly-compatible spec** preserves
Plotly's universal reach. Memory and scale are won in the data pipeline; the GPU renderer
just consumes what the pipeline has already minimized.

---
---

# Part II — Audit addendum

*A hostile review of Part I. Five claims did not survive contact with reality and have
been corrected in place (§4, §5, §6, §8, §13); the sections below add design that was
missing entirely.*

## 15. Audit findings summary

| # | Finding | Severity | Resolution |
|---|---|---|---|
| 1 | "Byte-identical" browser/native output is impossible (GPU float nondeterminism, DOM vs native text) and contradicted §7 | **Critical — false claim** | Reworded to logical + perceptual identity; CPU reference rasterizer as CI oracle (§8, §21) |
| 2 | "f32 by default" corrupts every time series (ms epoch > f32 mantissa) | **Critical — data corruption** | Offset+scale relative encoding is the default upload path (§4); deep-zoom re-centering (§16) |
| 3 | SharedArrayBuffer needs COOP/COEP — unavailable in Jupyter/iframes, i.e. exactly where Plotly-reach matters | **Critical — deployment** | Transferable-ArrayBuffer ownership handoff is the design baseline; SAB is an optimization (§8) |
| 4 | Tier-2 GPU binning assumed compute shaders + atomics; WebGL2 has neither — flagship feature silently absent on fallback | **Critical — feature gap** | Three-implementation ladder: compute / additive-blend float target / worker SIMD (§5) |
| 5 | "Free CPU buffer after upload" is a no-op for browser memory — wasm32 linear memory never shrinks, caps at 4 GB | **Major — memory claim** | Large columns never enter linear memory; screen-sized scratch arenas (§4, §6) |
| 6 | Hover/pick undefined for aggregated tiers; naive pick readback + LOD recompute breaks interaction latency | Major | Interaction latency model, stale-while-revalidate, progressive refinement (§17) |
| 7 | No multi-chart story; browsers cap live GPU contexts (~16 in Chrome), dashboards want 30+ | Major | Per-chart context under an LRU governor, budget 12 (§18) |
| 8 | No null/NaN semantics; NaN in f32 vertex data corrupts primitives | Major | Validity bitmaps end-to-end, gap semantics (§19) |
| 9 | Canvas rendering is an accessibility regression vs Plotly's SVG | Major | Structured a11y layer (§20) |
| 10 | Autorange is an O(n) full scan per update | Moderate | Chunk zone maps make it O(chunks) (§22) |
| 11 | No VRAM budget/eviction; no device-loss recovery | Moderate | Byte-budgeted caches; rebuildable GPU state (§6, §18) |
| 12 | No bundle-size budget — a fat WASM blob forfeits a real Plotly pain point (3.5 MB+) | Moderate | Feature-gated modules + CI size budget (§23) |
| 13 | Compat shim scope unquantified (~3,000 Plotly schema attributes) | Moderate | Generated conformance suite + explicit degradation contract (§24) |
| 14 | Benchmarks measured throughput but not interaction latency; "60fps" undefined | Minor | Latency budgets + p99 framing added (§17, §12) |
| 15 | No extensibility story (Plotly has custom traces) | Minor | **Shipped v0**: composition mark plugins, `xyg.register_mark` (§24). Custom shaders still deferred. |

## 16. Numeric precision & deep zoom

The offset-encoding scheme (§4) has one failure mode left: **zooming deeper than f32
relative resolution** (~1 part in 10⁷ of the current offset window — e.g. sub-second
detail inside a decade of millisecond timestamps).

- The viewport (always f64 on CPU) monitors `visible_span / offset_window_span`. When
  it crosses ~10⁻⁵, the core **re-centers**: pick a new offset at the viewport center,
  re-encode *only the visible chunks* (cheap — they're the ones paged in), and swap
  buffers. Hysteresis on the threshold prevents thrash at the boundary.
- **Axis ticks and hover labels never go through f32.** Tick positions, tick label
  values, and hover readouts are computed CPU-side in f64/i64 from source columns —
  the GPU path only ever positions pixels, so display precision is exact even when
  geometry is quantized to sub-pixel f32.
- **Linear axes stay offset-encoded through the vertex transform.** The shader's
  affine view mapping is composed directly onto the encoded values (`xyMap`,
  `js/src/40_gl.ts`); the CPU folds the offset into the affine constants in f64
  (`_map`, `js/src/50_chartview.ts`). Decoding to absolute coordinates in-shader
  first would discard the low bits whenever a deeply zoomed window is far smaller
  than the offset — after which zooming back out could never recover the point
  spread. Only log-family axes (log, symlog) decode before mapping, because their
  transforms are not affine. *Augments §4.*
- **Log-family axes pin the encode offset to 0.0** (`lod.geometry_offset`, ABI 208
  `xyg_geometry_offset`) instead of re-centering on a midpoint. A midpoint offset makes f32 error *absolute*
  (~span/10⁷), which under symlog collapses exactly the neighborhood of zero the
  scale exists to spread (x=0 and x=1 encode to the same word when the domain
  reaches 10¹²), and under log destroys the small decades. With offset 0 the f32
  error is *relative* (~2⁻²⁴·|v|), and d(coord)/dv ≈ 1/(c+|v|) (symlog) or
  1/(v·ln10) (log) maps that to a bounded ≤~2⁻²⁴ coordinate error at every
  magnitude — sub-pixel everywhere. The traded-away capability is §16 midpoint
  re-centering *along that axis*: zooming a log-family axis into a window
  narrower than ~10⁻⁵ of its center's magnitude re-hits f32 granularity. That
  zoom depth spans a sliver of a decade (invisible on any log-family display)
  and is the same class of limit matplotlib accepts; recorded here per §28's
  no-silent-decisions rule.
- **Zooming inside an exact scatter drill is request-free until re-centering is
  due.** A view contained in a drill window that shipped exactly (`reduction:
  "none"`) needs no new data — the shipped subset already holds every point of
  it — so the client elides the `density_view` round-trip entirely (LOD doc §5,
  T12). It re-requests only once the view span falls below 1/256 of the drilled
  window's span on either axis, an f32-safe margin (at 2⁻⁸ of the window the
  ~2⁻²⁴ encode quantum is still ≲0.1 px on a 4k-wide plot); that request exists
  to re-center the offset encoding per this section, and the re-centered reply
  re-arms the elision around its own window.
- **Time is i64 end-to-end** (Arrow timestamp columns), with calendar-aware tick
  generation (months are not 30×86400s). Plotly gets this right; matching it is
  table stakes and it must not be routed through any float path.

## 17. Interaction & latency model

Part I said "60fps" without defining what has to happen inside a frame. The budgets:

| Interaction | Budget | Mechanism |
|---|---|---|
| Pan / zoom (view change) | same frame (≤16 ms) | uniform update only — **never** blocks on recompute |
| Hover highlight | ≤2 frames | GPU pick readback is async (`mapAsync`); 1-frame-stale results are imperceptible |
| LOD tier rebuild after zoom | 100–300 ms, non-blocking | **stale-while-revalidate**: keep drawing the old tier, transformed by the new view matrix (slightly wrong resolution, right position), swap when the worker delivers |
| Tier-2 rebin on large data | first result <100 ms | **progressive refinement**: bin a 1-in-k sample first (coarse density appears immediately), refine with remaining data over subsequent frames. Standard datashader-at-interactive trick; also masks the slower WebGL2/worker binning fallbacks |
| Streaming append | ≤1 frame to visible | ring-buffer write + partial `writeBuffer`, no scene rebuild |

**Hover semantics per tier** (the doc previously defined hover only for direct draws):
- *Tier 0/1:* GPU pick → point ID → exact source-row readout (f64/i64, via §16).
- *Tier 2 (aggregated):* the pick target is a **bin**, not a point. Hover shows bin
  summary (count, x/y range, aggregate value). Click-to-drill spawns a worker query
  that returns the top-k underlying rows from the column store — honest about
  aggregation instead of pretending a fake "nearest point."
- *Tier 3:* same as Tier 2, but the drill query may touch unpaged chunks →
  it's async with a loading affordance.

## 18. Many charts per page (the dashboard problem)

Plotly's real-world habitat is dashboards with 10–50 figures. Browsers cap live
WebGL contexts per page (~16 in Chrome) and LRU-evict the oldest on overflow, which
permanently blanks the earliest charts of a big dashboard.

**Fallback path: one context per chart, governed.** When shared hosting is explicitly
disabled or unavailable, and by default inside child frames, `XY_CONTEXT_GOVERNOR`
(`js/src/50_chartview.ts`) keeps the page inside a budget — default **12**, overridable
via `window.XY_CONTEXT_BUDGET` — leaving headroom under Chrome's cap for host-page GL.
When a view is about to acquire a context at budget, the least-recently-visible
*off-screen* view releases its own via `WEBGL_lose_context` and re-acquires when
scrolled back into view; an over-budget panel keeps showing its last frame as a static
image. Under the budget nothing is ever released. Every decision is observable:
`data-xy-ctx` on the canvas reads `live` | `released` | `lost`. See
`spec/process/production-readiness.md` §"WebGL context cap" for the claim limits.
`destroy()` releases the context via `WEBGL_lose_context` too, so a view teardown —
including the destroy+rebuild a full-payload republish performs — frees its slot
immediately rather than leaving a destroyed context to linger until GC and count
against the browser cap.

**The fallback budget is shared across same-origin frames.** Chrome's cap is *process-wide* —
one budget for every iframe in the tab — but a per-document governor sees only its own
charts. A page that renders each chart in its own iframe (docs sites, SaaS dashboards,
and the `examples/fastapi` gallery, which needs iframes to host each standalone
`to_html` document) would otherwise defeat the governor entirely: no frame ever
releases (each is under budget alone), the browser LRU-evicts live charts, and the
evicted charts fight to recover and re-evict — a scroll-driven "Too many active WebGL
contexts" storm. The governor closes this by sharing one budget over a
`BroadcastChannel("xy-webgl-context-governor")`: each frame announces its live-context
count (`{t:"live", id, n}`, with `hello`/`bye` for join/leave), and any frame over the
shared budget sheds its own *off-screen* views — never a visible one, so a sibling
frame loading cannot blank a chart the user is looking at. `IntersectionObserver`
already reports an off-screen iframe's chart as not-intersecting (it clips to the
top-level viewport), so the visibility signal is correct across the frame boundary; the
budget accounting was the only gap.

Two subtleties the implementation must get right. **(1) Restore ordering.** A governed
release is `WEBGL_lose_context.loseContext()`; re-acquire is `restoreContext()`. Chromium
*silently drops* a `restoreContext()` issued before that context's `webglcontextlost`
event has dispatched (or synchronously inside the dispatch), stranding the canvas lost
forever — and a chart scrolled back into view in the same task it was shed hits exactly
that window. Recovery therefore defers until the loss event lands (`_ctxLostPending`)
and retries on a fresh task; a released chart that never re-acquired on scroll-in was the
first symptom. **(2) Incremental shedding.** Frames over budget release *one* off-screen
view per event-loop turn, not the whole computed excess: several frames observing the
same over-budget snapshot would each drop the full deficit and collectively over-release,
so each sheds one, announces, and re-evaluates against the fresher count — converging on
the budget instead of overshooting it (still safe either way; an off-screen over-release
just revives on demand).

Coordination is otherwise best-effort and self-healing: `BroadcastChannel` delivery is
asynchronous, so a burst of charts constructed in one synchronous tick across many frames
can briefly overshoot before the first `live` messages arrive (a handful of transient
evictions that recover); a frame frozen into the back/forward cache says `bye` on
`pagehide` and re-announces on `pageshow` (`persisted`) so peers neither count a frozen
frame nor omit a restored one; and a frame that crashes without a `bye` only lowers the
effective budget (a few extra off-screen releases, revived on demand) — it never blanks a
visible chart or evicts. Cross-origin and `sandbox`-without-`allow-same-origin` frames
(e.g. the notebook `_repr_html_` frame) get an isolated channel scope and fall back to
per-document behavior.

**Device/context loss is a first-class event:** all GPU state is derived state, rebuilt
from the scene graph + column store on a new context. The visible cost is one reupload
flicker, never lost data — and never a lost view: the settled pan/zoom is preserved across
the loss and re-requested on restore, so a backgrounded tab or a scrolled-away chart comes
back where the user left it, not at home (#156). The governor depends on this — a governed
release is a deliberate context loss put through the same restore path.

**Production design: one document-scoped `GLHost`.** A top-level document creates one
`GLHost` backed by a detached WebGL2 canvas and context. Participating `ChartView`
instances are clients of that host, while each chart keeps a Canvas2D plot surface in
its own DOM subtree. The host renders one chart into its detached target and
synchronously blits the completed pixels into that chart's Canvas2D surface. Scrolling,
clipping, z-index, and DOM interleaving therefore remain per-chart behavior.

The `GLHost` owns the WebGL context, immutable fullscreen quad, and a generation-scoped
cache of compiled shaders keyed by shader stage plus exact source. Each `ChartView`
retains its own linked programs, scene state, and render and pick resources, including
target dimensions and lazily created pick attachments. Reusing immutable compiled
shaders avoids repeating the driver compilation work for every chart; the cache is
discarded whenever the host context is lost or replaced. Linked programs stay
client-owned because uniforms are mutable WebGL state; they can move into a host cache
only after every pass is independently state-complete. Before rendering a client, the
host binds that client's target and establishes the viewport, scissor, and WebGL state
required by the chart; client switches cannot rely on state left by the previous chart.

Shared hosts may opt into automatic derived-resource admission with one bounded
Rust `XYDP` coordinator. Client registration/removal, visibility, interaction,
and measured allocation changes coalesce into serialized plans; a change during
an in-flight plan requests one fresh snapshot afterward. TypeScript only reports
measurements and applies the returned retain bits. It never duplicates Rust's
priority ordering, and stale snapshots remain non-mutating.

A loss of the shared context is host-wide. The `GLHost` restores or replaces its
detached context, fullscreen quad, and empty shader cache, then directs every client to
rebuild its programs and per-chart render and pick resources from CPU-backed scene
state. Each client preserves its settled pan/zoom and re-requests that same view after
reconstruction, matching the existing context-loss contract rather than resetting
charts to home.

The governed per-chart path remains the compatibility fallback. It is used when shared
hosting is explicitly disabled via `window.XY_SHARED_WEBGL = false`, when a document
cannot create or use the shared host, and by default inside child frames. Setting
`window.XY_SHARED_WEBGL = true` opts a child frame into shared hosting. Fallback
contexts continue to participate in the existing governor and same-origin frame budget
described above.

## 19. Nulls, NaN, and gaps

- Arrow **validity bitmaps** are the single source of null truth, carried through
  every stage (1 bit/value — no 8-byte NaN sentinel columns).
- NaN/invalid values **never reach vertex buffers** — an f32 NaN silently kills the
  primitives that share it (GL behavior is undefined-but-usually-invisible geometry,
  and it differs by driver — a determinism hole as well as a correctness one).
- Semantics preserved from Plotly: a null inside a line trace = **gap** (line break),
  implemented by splitting the draw into segments at ingest (segment index list, not
  per-frame branching). Aggregations skip nulls and expose `count_valid` vs `count`.
- Decimation (Tier 1) treats gap boundaries as hard edges — min/max buckets never
  span a gap, or decimation would invent data across a hole.

## 20. Accessibility (a regression Plotly would win otherwise)

SVG charts are imperfect but *inspectable*; a canvas is a black rectangle to assistive
tech. Ship from Phase 1, not as a retrofit:

- A parallel **semantic layer** in the DOM: chart role + generated text summary
  (trace count, ranges, extremes — derivable from the zone maps of §22 for free),
  `aria-live` region for hover readouts.
- **Keyboard navigation**: arrow keys walk points (direct tiers) or bins (aggregated
  tiers), reusing the exact hover pipeline of §17 — one code path, two input devices.
- **"View as table"** escape hatch: the column store already has the data; render the
  visible window as an HTML table on demand.
- High-contrast + `prefers-reduced-motion` respected in the theme system; colormaps
  ship with CVD-safe defaults.

## 21. Visual testing, determinism, and text

The correctness oracle for a renderer is an image, and images from GPUs are
driver-dependent. The testing architecture:

- The native build includes a **software (CPU) rasterizer path** — slow, simple,
  bit-deterministic. It is the **reference implementation**. Every backend (WebGPU,
  WebGL2, native GPU) is screenshot-diffed against it with a perceptual metric
  (per-channel tolerance + small SSIM window), not byte equality.
- **Text is the biggest determinism variable**, so it's pinned: the core bundles its
  own font shaping/rasterization (embedded default font; user fonts loaded explicitly)
  for native output *and* for the CPU reference. In the browser, chrome text is DOM
  (crisp, selectable, accessible — §7), and the conformance suite compares *layout
  boxes* (positions/extents from the shared layout engine) rather than glyph pixels
  across that boundary. Same layout, per-target rasterization.
- **LOD decisions are part of the tested contract**: given (data, viewport, tier),
  the chosen tier and the decimated/binned output are deterministic and asserted —
  so "it looked different" can always be bisected to *layout*, *LOD*, or *raster*.
- The canonical scene has its own schema version. Rust scene goldens and
  cross-host fixtures are checked before backend pixel comparisons. Version 3
  fixes layout/axis/style plus scatter/polyline/rectangle record bytes across
  Python and Node. Any new emitted kind or field semantic bumps the scene
  version until explicit capability negotiation exists; consumers fail closed
  on unsupported versions and unknown kinds. #58 grows that oracle by vertical
  slice before native and browser render consumers attach.
- CI matrix: reference images from CPU rasterizer; per-backend perceptual diffs;
  the §12 perf harness gains **interaction-latency** metrics (input-to-photon for
  pan, hover, tier-swap; p50/p99 frame time — "60fps" now means *p99 ≤ 16.7 ms
  during continuous pan*, not an average).

## 22. Chunk statistics (zone maps) — cheap answers to expensive questions

At ingest, every column chunk (~64k values) gets a one-pass statistics block:
`min, max, count, null_count, sum, sum_sq` (+ dictionary cardinality for categoricals).
Cost: one streaming pass you were already paying at f32-encode time. Buys:

- **Autorange in O(chunks)** instead of O(n) — the §1 complaint about full-scan
  autorange, actually closed.
- **Tier-3 pruning**: viewport queries skip chunks whose min/max don't intersect —
  the same trick as Parquet row-group pruning, applied to pan/zoom.
- **Instant summaries** for the a11y layer (§20) and for aggregated-hover drill
  previews (§17) without touching raw data.
- Deep zoom re-centering (§16) picks its new offset from zone maps, not a scan.

## 23. Deployment matrix & bundle budget

Where it must run, and what each environment denies us:

| Environment | Denied | Design answer |
|---|---|---|
| Jupyter / VS Code notebooks | COOP/COEP (no SAB), sometimes strict CSP | transferables path (§8); WASM served same-origin by the extension; no `eval` anywhere |
| Embedded iframes (docs, dashboards-in-SaaS) | COOP/COEP, GPU context quota shared with host | transferables; the context governor shares one budget across same-origin iframes over a `BroadcastChannel` so a chart-per-iframe page stays under the process-wide cap (§18) |
| Strict-CSP enterprise pages | `wasm-unsafe-eval` may be blocked | documented CSP requirements; **pure-JS fallback build** (same core transpiled level: Tier 0/1 only, capped point counts) so a chart *renders* rather than white-boxes |
| Old browsers / no WebGL2 | GPU entirely | same pure-JS + 2D-canvas fallback, capped; loudly reported via the §5 no-silent-caps rule |
| Server / CI (native) | no display | headless native path (§8) |

**Bundle size.** The shipped client is a single minified JS bundle —
`@curatelabs/xyg` `dist/index.js` (copied to `python/xyg/static/index.js` in the
Python wheel), ~277 KB minified / ~76 KB gzipped (vite/oxc; built from
the TypeScript sources in `js/src`) — with no WASM payload and no lazily-loaded trace
modules. It is a **generated artifact, not committed to git** (§33): the hatch build
hook runs `node js/build.mjs` at packaging time and force-includes the result into the
wheel and sdist, so a published Python distribution carries it prebuilt. The one size gate CI
enforces is on the **wheel**: `.github/workflows/ci.yml` asserts the built wheel is
≤ 15 MB (§33). CI builds the client fresh from source in every relevant job but does not
measure its bytes.

*Pending:* a gzipped-size budget on the client bundle, failing the build exactly like a
perf regression (§12), plus per-trace-family lazy feature modules (Plotly's
partial-bundle pain). Neither exists today.

## 24. Extensibility & the compatibility contract

- **Compat is a measured number.** Plotly's `plot-schema.json` (~3,000 attributes) is
  ingested to *generate* the conformance suite: each attribute is classified
  `supported | mapped-with-difference | unsupported`, the shim **warns loudly** on
  unsupported attributes (never silently drops), and the docs publish the coverage
  table per release. "Drop-in for the common 80%" becomes checkable, not vibes.

- **Custom traces without forking:** a registered *mark plugin* provides
  (a) a calc function over columns → columns (runs in the worker, gets zone maps),
  (b) either a composition of built-in GPU primitives (instanced marks, density
  textures, line strips) *or* a WGSL/GLSL snippet pair for exotic marks, and
  (c) hover/a11y descriptors so §17/§20 work uncalled-for. Plotly's moat is breadth;
  a plugin API is how breadth arrives without the core team writing all 40 traces.

  **Shipped (v0):** `xyg.register_mark` / `xyg.MarkPlugin` / `xyg.mark` in
  `python/xyg/plugins.py`. It ships (a) and the composition half of (b); the
  shader half is deferred. `build` returns built-in `Mark` objects and cannot
  reach the `Figure`, the trace list, or the column store, so a plugin cannot
  draw anything the engine could not already draw — and its output being
  ordinary traces is what lets it reuse the built-in rendering, picking, and
  export paths instead of reimplementing them. Composition is one level deep:
  plugins compose built-ins, not each other. The shader half stays deferred for
  the same reason the composition half works: a plugin carrying its own shader
  reuses none of that.

## 25. Milestone amendments (audit-driven)

- **Phase 0** additionally proves: offset-encoding precision on ms-timestamp data
  (test: 1-second span inside a 10-year series), and the transferables-only path in
  a real Jupyter notebook. *Both are thesis risks, so they move to the front.*
- **Phase 1** ships the a11y semantic layer + keyboard nav (§20) and zone maps (§22)
  — both are near-free at ingest time and brutal to retrofit.
- **Phase 2** ships all **three** Tier-2 implementations (§5) and progressive
  refinement (§17), not just the WebGPU one — the fallback ladder *is* the feature.
- **Phase 3** adds the CPU reference rasterizer + perceptual-diff CI (§21) *before*
  the second backend lands, so WebGPU-vs-WebGL2 divergence is caught from day one.
- **Phase 4** adds shared-context dashboard compositing (§18) — tiling and
  multi-chart stress the same VRAM budget and should be tuned together.
- **Phase 5** adds the generated conformance suite + coverage table (§24).

## 26. Summary of Part II in one paragraph

The audit's theme: Part I was right about *where the wins live* (data pipeline, LOD,
GPU) but optimistic about *the floor it runs on*. Browsers deny you shared memory in
notebooks, atomics in WebGL2, shrinkable WASM memory, more than a dozen GPU contexts,
and bit-determinism everywhere — and f32 quietly destroys timestamps. Each denial now
has a designed fallback that preserves the capability and degrades only latency, and
each former hand-wave (hover-on-aggregates, nulls, a11y, text, bundle size, compat
scope) is now a contract with a test attached. The plan's claims are weaker in wording
and much stronger in survivability.

---
---

# Part III — Second audit round (external review)

*An external review confirmed four Part-II fixes (offset encoding, SAB fallback,
byte-identical retraction, cache eviction) and surfaced six further findings, all
accepted: the zero-copy overclaim, payload-only memory targets, the GPU-residency ↔
LOD-recompute contradiction, the false "O(points) once" aggregation cost, the missing
Tier-3 index, and the unscoped compat surface. Those are corrected in place
(§2, §4, §5, §10, §14). The reviewer's verdict — "replace universal claims with
precise modes where they are actually true" — is the theme of this part. It adds the
three sections the review demanded before implementation.*

## 27. Memory Model — every byte class, who owns it, when it dies

The five classes of memory, per chart:

| Class | Lives in | Sized by | Freed when |
|---|---|---|---|
| **Canonical columns** | JS ArrayBuffers / mmap (native) / server (Tier 3); browser WASM reads bounded copied chunks, never whole-column residency | data | trace removed (or explicitly demoted, below) |
| **Derived buffers** (decimations, pyramid tiles, bin-color resolutions, segment indices) | worker-side buffers + LodCache | screen (per entry) × cache budget | LRU-evicted under byte budget; always recomputable |
| **Staging** (encode/upload scratch) | WASM arena + mapped GPU staging rings | screen, fixed | reused every frame — never grows with data |
| **GPU buffers/textures** | VRAM | visible working set | evicted under VRAM budget; rebuilt from canonical + derived on demand or device-loss |
| **Overheads** | everywhere | — | *counted, not ignored*: validity bitmaps (1 bit/val), dictionaries, per-buffer GPU alignment padding (256 B granularity), double-buffering during in-flight uploads |

Rules that make the mode targets in §2 real:

1. **GPU is a cache, CPU/server is the truth.** Every VRAM object has a rebuild
   recipe (column refs + transform). Nothing user-provided is *only* in VRAM.
2. **Budgets are explicit and hierarchical:** global engine budget → per-chart share
   → per-class caps (LodCache, tile residency, VRAM estimate). VRAM is unqueryable in
   browsers, so the VRAM budget is a conservative self-accounting of our own
   allocations with allocation-failure backoff (drop to a coarser tier, evict, retry).
3. **Upload overlap is bounded:** staging rings mean at most one screen-sized slice
   of data is duplicated CPU+GPU at any instant — not the whole column.
4. **Demotion is explicit:** the "drop canonical, keep GPU" mode (§4) is a per-trace
   API call that returns the freed bytes and records the trace as `degraded` —
   visible in the debug HUD and in `chart.memory_report()`, which itemizes all five
   classes per trace. If a memory number isn't in the report, it isn't real.
   Corollary for growth buffers: a streamed column's `values` is a prefix *view* of a
   capacity-doubling allocation (§5), so `values.nbytes` under-reports what the process
   holds by up to 2x. Every column therefore reports `capacity_bytes` alongside
   `bytes`, the store totals them as `canonical_capacity_bytes`, and
   `resident_array_bytes` is built from the capacity total — equal to `canonical_bytes`
   for any figure that never appended. Continuous channels already reported their own
   growth buffers this way; columns now match.
5. **Canonical may be out-of-core (native `mmap`).** The "mmap (native)" cell in the
   table above is realized: a canonical column may be backed by a disk `np.memmap`
   instead of RAM. Because a memmap is a transparent `ndarray` — same dedup key, same
   raw buffer pointer to the ctypes kernels — the store, zone maps (§22), `bin_2d`, the
   density pyramid (§5/§28) and drill-in all consume it **unchanged**; the OS pages the
   file in on demand and evicts clean pages under pressure, so resident memory stays
   screen-bounded (the pyramid + grids), never data-bounded. `memory_report()` counts
   these bytes under `canonical_mapped_bytes` (disk-backed, reclaimable), kept distinct
   from `canonical_bytes` (RAM-resident) — an all-RAM figure reports `mapped = 0`
   unchanged. Building a column too large for RAM is the one operation that needs a
   dedicated path: `xyg._ooc.MemmapF64Builder` streams canonical f64 to disk one batch
   at a time (peak RAM = one batch), and `xyg._ooc.open_f64` reopens a column from
   disk. `tests/test_ooc.py` pins the contract: a memmap column ingests with no RAM
   copy, flows through the ordinary `scatter(..., density=True)` API, and renders
   density first-paint with 0 RAM-resident canonical bytes. This is the native
   counterpart to the browser's Tier-3 tile spill (§4.4 of the LOD architecture doc /
   dossier §32); the two compose (canonical on disk, screen-bounded aggregates over
   the wire).

## 28. LOD / Tiling Contract — exact rules per trace kind

For each kind: *canonical requirement → tier ladder → what hover/select means → what
recomputes on zoom.*

| Trace kind | Canonical requirement | Tier ladder | Hover/select | On zoom |
|---|---|---|---|---|
| **Line / area / time series** | x sorted (or engine sorts once at ingest, stated) | direct → min-max per-px-column decimation → zone-map-pruned chunk streaming | exact point (binary search on x in canonical) at every tier | recompute decimation for visible x-range only; zone maps prune chunks |
| **Scatter** | none for Tiers 0–1; spatial bucketing pass at ingest for Tiers 2–3 | direct instanced → *no Tier 1 (decimating unordered points misleads)* → density pyramid → out-of-core tiles | Tier 0: GPU pick, exact row. Tiers 2–3: bin summary + async drill to top-k rows | pan = tile reuse; zoom = adjacent pyramid level; below pyramid floor = re-bin visible via tile index; inside an exact drill window = nothing recomputes and no request is sent — the client already holds every point (§16, LOD doc T12) |
| **Heatmap / image** | gridded input | direct texture → mip pyramid (same machinery, degenerate case) | cell value (exact, from canonical grid) | mip level selection; nothing recomputes |
| **Bar / histogram** | histogram: raw column; bar: categories | bars are visually bounded (≤ ~10⁴ on screen) → direct; histogram re-bins from canonical on range change (cheap: 1-D, visible range only, zone-map-pruned) | exact bar/bin | 1-D re-bin, worker, stale-while-revalidate |
| **Streaming (any kind)** | ring capacity declared up front | ring buffer + incremental decimation (Tier-1 buckets updated, not rebuilt); pyramid tiles updated incrementally for touched cells | same as base kind, within retained window | append is O(appended); eviction from ring updates affected buckets only |
| **Box / violin / stat traces** | raw column | stats computed in worker from canonical (streaming algorithms; KDE on a bounded grid) — drawn geometry is tiny | stat readout (exact) | recompute stats for visible subset if axis-linked |

For the bounded composition violin, ABI 98 is the native realization of this
ownership rule: hosts pack grouped canonical samples and parameters; Rust
filters, computes and normalizes the bounded density, applies width and
orientation, and emits no more than 10,000 final Rect rows. Browser-worker
recomputation for future axis-linked subsets reuses this same engine function.

ABI 99 applies the same ownership rule to bounded composition boxes. Hosts
pack flat canonical f64 samples, monotone group offsets, centers, orientation,
width, and the outlier-visibility flag. Rust filters nonfinite samples, computes
Tukey quartiles and 1.5-IQR whiskers, preserves source-group order, and emits
the final body, whisker, cap, median, and outlier coordinates. Outlier jitter is
deterministic SplitMix64 keyed by source-group and within-group outlier index,
bounded to +/- 0.12 of box width; hiding outliers retains statistical metadata
with zero placement coordinates. Five fixed geometry records per active group
plus all outlier records are capped at 10,000.

ABI 100 applies the rule to bounded composition ECDF approximation. Hosts pass
the raw f64 column, `1..=10000` bins, and either automatic bounds or Node's
existing finite increasing authored range. Rust filters nonfinite samples,
uses finite min/max with 5% absolute-value widening for a nonzero constant
automatic domain (falling back to 0.5 at zero or for a non-useful pad),
domain, performs uniform counting with the exact upper endpoint in the last
bin, normalizes over every finite source sample, compacts empty bins, and emits
the zero anchor plus occupied-bin right edges. Python deliberately adds no
public range option. Both hosts retain style, axis, id, and error presentation,
then author the result as the existing `post` Step. Each output plane is
bounded by `bins + 1`; invalid input, short or overlapping output planes, or nonrepresentable
arithmetic fails atomically. The public authored-column router admits 10,001
points only for compact Step lines so the maximum-bin anchor is representable;
ordinary traces stay at 10,000 and 10,002 Step points fail closed.

ABI 101 applies the same ownership rule to composition histograms. Hosts resolve
integer, automatic, or authored edges and pack the raw f64 column. Rust validates
finite strictly increasing edges, counts with the last bin closed, applies
density over in-range mass, and accumulates left-to-right when requested.
Automatic or authored results above 10,000 bins, non-increasing edges, and
density with zero in-range mass fail atomically. Public SVG/PNG/PDF and the
browser painter already consume the resulting Histogram Rects.

ABI 102 applies the same ownership rule to composition hexbin ingress. Hosts
pass raw f64 x/y (and optional C) plus either a scalar grid width or an
explicit pair. Rust filters finite pairs, pads a constant automatic domain
(5% of absolute value, falling back to 0.5), selects matplotlib
`int(width / √3)` when height is omitted, and assigns the existing
count/mean/sum lattice. Custom Python reducers still reduce groups on the
host after Rust resolves that domain and aspect. The compact wire result
remains the centers-only hexbin trace. Constant-style Cartesian native
lattices compile those centers plus cell pitch onto existing Scene PolyFill
records; polar, custom reducers, colormaps, and LOD stay compatibility.
ABI 103 moves that Cartesian hex-cell ring and regular heatmap lattice
reconstruction into Rust compact authoring so Python and Node pack centers+pitch
and extent+shape only.
ABI 104 moves disconnected endpoint pairs and unjoined triangle faces onto the
same compact expansion so hosts pack one four-coordinate row per segment and
two PolyFill rows per face.
ABI 105 moves the public static-export support predicate into Rust. Hosts pack
an `XYEF` v1 facts envelope; ABI 152 owns `XYEP` layout, kind/step/annotation
codes, and flag derivation. Allowlists, check order, and
`XYG_SCENE_UNSUPPORTED_*` wording are engine-owned and identical for Python
and Node.
ABI 106 moves Figure autorange, `_auto_domain`, and zero-baseline pinning
into Rust. Hosts pack an `XYAR` v1 envelope of axis options, column extents,
and rectangle predicates; padding, log-positive extents, polar defaults,
reverse, and the default 3% margin are engine-owned and identical for Python
and Node.
ABI 107 moves Scene CSS→RGBA8 conversion and per-kind mark fill/stroke/width
defaults into Rust. Hosts pack an `XYMS` v1 envelope of kind, opacities,
authored CSS strings, and width fields; named colors, `none`, line-only
scatter stroke, band `line_color`, default widths, and the never-invisible
fallback are engine-owned and identical for Python and Node.
ABI 108 moves Scene chrome default RGBA/widths and CSS overlay into Rust.
Hosts pack an `XYCH` v1 envelope of background CSS, per-axis sides, paint
flags, opacities, widths, and CSS strings; `grid_opacity` still scales the
default grid color when `grid_color` is unauthored, and named chrome paints
cannot drift.
ABI 109 moves Figure→Scene row packing into Rust. Hosts pass kind, flags,
step mode, style ref, trace id, diameter/symbol, extras, and literal f64
columns; record kinds, stable-id splitting, expansion-mode assignment,
ribbon/triangle doubling, heatmap lattice framing, and finite-coordinate
rejection are engine-owned and identical for Python and Node.
ABI 116 expands primary rule/band/marker annotations into ordinary Scene
rows. Hosts pass kind, axis, style ref, index, and authored scalars plus
axis domains; stable-id tags, domain spanning, and finite rejection are
engine-owned and identical for Python and Node.
ABI 117 moves figure-compile support into Rust. Hosts pass packed
observations plus axis ids/keys; feature mapping, the primary x/y axis
set, and the Scene axis-key allowlist are engine-owned and identical for
Python and Node.
ABI 118 extends that envelope to per-trace allowlist flags so kind,
hidden/per-item, density, dash, rect extras, joined fill, hex reducer,
heatmap colormap, and non-CSS fill diagnostics are engine-owned and
identical for Python and Node.
ABI 119 moves composition mark ingress into Rust. Hosts call
`xyg_argsort_stable`, `xyg_histogram_mark_edges`, `xyg_contour_levels`, and
`xyg_hexbin_groups`; stable NaN-last sort, integer/empty-auto histogram
edges, contour isoline spacing, and custom-hex lattice membership are
engine-owned and identical for Python and Node. Custom reducers stay host
callables over those groups.
ABI 120 moves composition `loc="best"` occupancy into Rust. Hosts call
`xyg_legend_normalize` and `xyg_legend_best_loc`; display-space projection,
stride/finite caps, drop-not-clamp off-plot marks, and the 0.02 tie band are
engine-owned and identical for Python and Node. ABI 197 Scene product encode
settles authored `loc="best"` from packed XYCL/XYNM plus XYCF domains
(#298). Compatibility `_legendfit.py` still packs ChartView specs.
ABI 121 moves ribbon/curve/rounded-rect tessellation into Rust. Hosts call
`xyg_ribbon_edge`, `xyg_ribbon_polygon`, `xyg_monotone_tangents`,
`xyg_curve_flatten`, and `xyg_rounded_rect_poly`; bump-X flattening,
Fritsch–Carlson tangents, Hermite polylines, and independent tip/base radii
are engine-owned and identical for Python and Node. Compatibility PNG
(`_raster.py`) calls those kernels directly (#310); `_scene.py` wrappers
remain for tests. Hosts still map affine
scales and apply colormaps (`grid_rgba`, #283 / #313).
ABI 122 moves compile-time payload LOD into Rust. Hosts call
`xyg_payload_tier`, `xyg_payload_visible_needed`, and
`xyg_payload_visible_mask`; line M4 vs direct, scatter density vs
direct (strict `>`, per-item ceiling, polar skip), and the finite/log
keep mask are engine-owned and identical for Python and Node. ABI 204
`xyg_payload_m4_indices` owns remaining line M4 emit: the closed-window
ulp, optional nonlinear `bin_x` buckets, and polar skip on first paint
and `decimate_view`. Hosts still map scale coordinates, gather extra
columns, encode, and ship the chosen rows (#282 / #311).
ABI 205 moves remaining `_emit_*` sampling into Rust. Hosts call
`xyg_payload_visible_indices`, `xyg_payload_even_indices`, and
`xyg_payload_sample_target_indices`; fused finite/log keep indices,
NumPy int64 linspace stem/errorbar sampling, and density-overlay
`min(1, target/n)` SplitMix selection are engine-owned and identical
for Python and Node. ABI 214 `xyg_payload_segment_budget` owns the
stem/errorbar count budget (`max(1024, floor(px_width)*4)`). ABI 215
`xyg_payload_errorbar_indices` owns even-index expansion across concatenated
role groups. Hosts still
gather extra columns, and ship the chosen rows (#282 / #312).
ABI 123 moves tick-label collision thinning into Rust. Hosts call
`xyg_scene_tick_label_layout`; auto / hide / rotate / stagger, the
edge-anchor rotate gap, and stride downsampling are engine-owned and
identical for Python and Node. Hosts still format `_tick_text` and map
values to pixels (#276).
ABI 124 moves static legend box packing into Rust. Hosts call
`xyg_legend_box_layout`; column fit, measured ellipsis, and loc /
bbox-to-anchor placement are engine-owned and identical for Python and
Node. Hosts still resolve CSS font-size / em paddings, pack entry
strings, and remap polar `legend_box_*` gutters (#275).
ABI 125 moves text-block measure and cartesian axis rooms into Rust.
Hosts call `xyg_text_block_measure`, `xyg_text_block_rotated_extent`,
`xyg_y_tick_label_extent`, `xyg_y_axis_left_room`,
`xyg_x_axis_title_room`, `xyg_x_tick_label_room`, and
`xyg_x_tick_label_edge_rooms`; wrap, rotated extent, and title/tick
gutter formulas are engine-owned and identical for Python and Node.
Hosts still format `_tick_text`, resolve CSS visibility / tick offsets,
and iterate axes on the compatibility `_svg.layout` path (#275). Default-font
cartesian Scene-shaped specs pack those observations into `xyg_scene_plot_layout`
(#297); custom `font-family` stays fail-closed instead of a silent DejaVu
substitute.
ABI 126 moves compatibility static-export padding, title-band, colorbar
extra, right-y, and polar-recut combination into Rust. Hosts call
`xyg_compat_is_compact`, `xyg_compat_default_padding`,
`xyg_compat_title_wrap_width`, `xyg_compat_title_room`,
`xyg_compat_x_axis_side_room`, `xyg_compat_colorbar_extra`,
`xyg_compat_right_y_room`, `xyg_polar_legend_room`,
`xyg_polar_legend_reserve`, `xyg_polar_label_room`, and
`xyg_recut_polar_plot`; compact gutters, colorbar extras, and polar disc
recut (including the too-small canvas fallback) are engine-owned and
identical for Python and Node. Hosts still iterate axes, format ticks,
measure rooms through ABI 125, resolve CSS visibility, and decide
whether a polar legend gutter is reserved (#275).
ABI 127 moves the pyplot tight-layout grid solve into Rust. Hosts call
`xyg_tight_layout_solve` with measured per-panel chrome, figure-edge
extras, and Matplotlib pad/rect; edge maxima, neighbor gaps, pad
multiples, and `subplots_adjust` fractions are engine-owned. Hosts still
measure `_panel_chrome`, suptitle, figure labels, and outside legends
(#275).
ABI 198 moves the remaining static-export padding/title/colorbar/right-y
combination and pyplot tight-layout figure-edge extras into Rust. Hosts
call `xyg_compat_combine_plot` and `xyg_tight_layout_figure_extra`;
additive vs floor gutters, second x-room pass, polar recut, and
suptitle/label/outside-legend extras are engine-owned and identical for
Python and Node. Hosts still iterate axes, format ticks, measure ABI 125
rooms, resolve CSS visibility, and decide polar legend reservation
(#299). `_svg._*room` stays for polar/extra-axis/custom-font measurement.
ABI 128 moves authored tick-window resolve and filter into Rust. Hosts
call `xyg_tick_window` and `xyg_tick_window_filter`; linear vs modular
angular containment (including seam-crossing sectors) is engine-owned
and identical for Python and Node. ABI 199 Scene product encode filters
authored cartesian majors through that window and pairs `tick_labels`
during chrome pack (#300). ABI 200 filters authored cartesian minors
through that same window (`require_finite`, #301). ABI 201 filters polar
theta majors/minors through that window's modular sector and formats
Scene polar theta labels with `format_angular_tick` (#302). ABI 202
materializes ABI 130 time strftime and polar angular numeric formats
onto `XYTL` during product encode (`format_axis_tick`, #303). Hosts pack
domain tick-kind in XYCF 154–155. Invalid ABI 96 grammar still falls
back. ABI 203 runs ABI 123 collision at Scene SVG/raster emit for
cartesian `tick_label_strategy` / `collision` (#304). Collision rooms
clamp only when compact/authored pads already fit `PlotLayout`;
overflowing compact pads stay `XYG_SCENE_UNSUPPORTED_VIEWPORT`. Polar rim
auto/hide/rotate/stagger/preserve stay refused (`polar-axes.md`).
Secondary
axes stay fail-closed (`Scene v12 figure compilation currently supports
exactly x/y axes`). Hosts still choose tick families via
`xyg_scene_axis_ticks` and map values to pixels on the compatibility
`_svg` path (#276). Polar rim collision strategies stay refused
(`polar-axes.md`).
ABI 130 moves Cartesian compatibility tick-label formatting into Rust.
Hosts call `xyg_tick_format` for linear/log/time/number-spec, category,
and angular defaults; polar tick drawing stays host-side (#276). Scene
product-path authored `tick_labels` pair during chrome pack (ABI 199).
Authored cartesian minors filter during chrome pack (ABI 200).
Polar Scene theta ticks use the ABI 128 modular sector and angular labels
(ABI 201); Scene product encode applies ABI 130 time/angular formats (ABI 202);
secondary axes stay fail-closed.
ABI 131 moves static polar (theta, r) → screen-pixel projection into Rust.
Hosts call `xyg_polar_layout`, `xyg_polar_project`, and the polar visibility-mask
helpers; wedge/ring/polygon helpers remain host-side and call native projection.
ChartView GLSL `xyPolarPos` is unchanged until WASM (#277). Scene v26 / ABI 133
compiles polar line, scatter, area, bar/column, errorbar, heatmap, and contour through XYPL v1 into `xyg_scene_batch_encode`;
ABI 143 polar density tessellates occupied `DensityBlit` cells to PolyFill
wedges. Polar heatmap constant-style lattices tessellate Rects to
PolyFill wedges; polar painted heatmap (ABI 192) inverse-rasters to one
plot-covering Image blit (Image+XYPL). Polar density still tessellates
occupied cells (no XYIM). ABI 194 admits polar hexbin as HexCell PolyFills
through the same XYPL path.
Polar contour reuses SegmentPair polylines through `polar_project`.
ABI 132 moves first-paint density scatter emit policy into Rust. Hosts call
`xyg_density_emit_meta`, `xyg_density_grid_path`, `xyg_density_format_binning`,
`xyg_density_pyramid_preflight`, and `xyg_density_wasm_eligible`; kernel
invocation, buffer shipping, and axis-scale transforms stay host-side.
ABI 129 moves Cartesian static-export grid colormap into Rust. Hosts
call `xyg_colormap_rgba`, `xyg_colormap_rgba_canonical`, and existing
`xyg_density_rgba` for log-u8 density; direct `t ∈ [0, 1]` stop
interpolation (matching `_svg._lut`) is engine-owned and distinct from
`xyg_heatmap_rgba`'s `((value * 255 - 1) / 254)` remap. ABI 206 adds
`xyg_colormap_lut` (1D `_lut`), `xyg_density_rgba_linear` (legacy f64
count grids with the `t * 1.35` alpha law), and `xyg_paint_effective_rgba`
(artist-alpha replace then xy opacity multiply) so remaining compatibility
paint/colormap policy cannot drift (#313). Hosts still
resolve colormap stop tables, CSS paint colors, and truecolor RGBA buffers.
ABI 192 owns polar painted heatmap inverse-raster sampling on Scene encode
(#292). ABI 207 `xyg_polar_heatmap_inverse_map` owns the compatibility
gather-after-inverse pixel map used by `_svg.polar_heatmap_rgba` (#283);
hosts still color the returned source indices.
ABI 208 `xyg_geometry_offset` / `xyg_f32_safe_scale` owns §4/§16 encode
offset and the §19 f32-safe scale so Python and Node cannot drift.
ABI 216 `xyg_scale_pins_offset` owns log-family `pin_zero` admission
(`log`/`symlog`, case-sensitive). Hosts still pack `EncodedColumn` metadata.
ABI 217 `xyg_arrow_geometry` / `xyg_arrow_shaft_points` /
`xyg_arrow_end_decoration` / `xyg_arrow_taper_polygon` /
`xyg_arrow_trim_polyline_end` owns annotation-arrow connectionstyle geometry
so Python `_arrowgeom.py` and Node `arrowGeometry` cannot drift. ChartView
`51_annotations.ts` keeps the same formula until WASM. Hosts still parse
comma-separated `start_offset` / `label_clear` strings.
ABI 218 `xyg_scene_dash_admit` owns Scene dash presets and 2–8 finite length
patterns so Python `_parse_scene_dash` and Node `parseSceneDash` cannot drift.
Invalid comma tokens reject the whole string. Hosts still coerce list vs
string and fail-close empty strings.
ABI 219 `xyg_scene_linecap_admit` owns Scene linecap names so Python
`_parse_scene_linecap` and Node `parseSceneLinecap` cannot drift. Unknown
names and whitespace-only strings reject. Hosts still fail-close empty
strings without calling the kernel.
ABI 220 `xyg_density_overlay_opacity` owns density overlay sample opacity
(`min(authored, 0.55)`; non-finite → `0.55`) so Python `_payload` and Node
`figure.js` cannot drift. Hosts still default omitted opacity to `0.8`.
ABI 221 `xyg_scene_marker_path_admit` owns Scene marker-path contour bounds
(1–32 contours, x/y pairs, `|v| ≤ 0.500001`, ≤ 96 vertices) so Python
`_validated_marker_path` and Node `validateMarkerPath` cannot drift. Hosts
still coerce mappings and fail-close non-numeric contours. Filled contours
shorter than 6 values stay a compile-path extra.
ABI 222 `xyg_scene_annotation_style_admit` owns Scene annotation style-key
allowlists so Python `_annotation_allowed_style` and Node
`annotationAllowedStyle` cannot drift. Hosts still skip markup/typography/
rotation and raise error text.
ABI 223 `xyg_scene_ribbon_color2_classify` owns ribbon two-ended paint class
(absent/solid/gradient/ends/fail) so Python `_classify_ribbon_color2` and
Node `classifyRibbonColor2` cannot drift. Hosts still coerce channels and
pack end RGBA8.
ABI 224 `xyg_scene_tick_label_strategy` owns Scene tick-label strategy names
so Python `_scene_tick_label_strategy` and Node `sceneTickStrategy` cannot
drift. Hyphens become underscores. Unknown names, including empty text, map
to `auto`. Hosts still pick `tick_label_strategy` vs `collision` vs camelCase
keys.
ABI 225 `xyg_scene_tick_anchor` owns Scene tick-label anchor names so Python
`_scene_tick_anchor_code` and Node `anchorCode` cannot drift. `middle` aliases
`center`. Unknown names, including empty text, reject. Hosts still pick
`tick_label_anchor` vs camelCase keys. ABI 123 layout enums stay a separate
throw-on-unknown table.
ABI 226 `xyg_scene_fill_gradient_admit` owns Scene fill-gradient stop admit
(space/dir, 2–8 monotone `t` in `[0, 1]`, `var(` reject, empty/`currentcolor`
→ mark color, RGBA8) so Python `_admitted_fill_gradient_from_fill` and Node
`admitFillGradient` cannot drift. Hosts still coerce fill mappings.
ABI 227 `xyg_scene_parse_linear_gradient` owns CSS `linear-gradient(...)`
parse (cardinal `to` directions, 2–8 resolved stops, nested function commas)
so Python `mark_fill` / `_admitted_fill_gradient_from_fill` and Node
`parseLinearGradient` cannot drift. Hosts still coerce fill mappings, wrap
authoring error text, and run `css_color` on authoring stops. Compile-path
skip-empty split stays extra.
ABI 228 `xyg_scene_rect_extra_flags` owns Scene rect extra-flag pack
(unusable-gradient bit, admitted corner-radius kinds, polar wedge-gap
exception) so Python `_rect_extra_flags` and Node `rectExtraFlags` cannot
drift. Hosts still coerce fill mappings, radius lists, and `wedge_gap`.
ABI 229 `xyg_scene_gradient_dir` owns Scene fill-gradient direction codes
(`down`/`up`/`right`/`left`; unknown/empty → 255; no lowercasing) so Python
`_pack_gradient_spec` / XYSS pack and Node `packGradientSpec` cannot drift.
Hosts still pick `dir` vs missing keys. Compile-path `to bottom` aliases stay extra.
ABI 231 `xyg_scene_gradient_space` owns Scene fill-gradient space codes
(`mark`/`plot`; unknown/empty → 255; no lowercasing) so Python
`_pack_gradient_spec` / XYSS pack and Node `packGradientSpec` cannot drift.
Hosts still pick `space` vs missing keys. XYSS plot-space is `code == 1`.
ABI 230 `xyg_scene_linear_gradient_prefix` owns the CSS `linear-gradient(`
prefix check (trim, lowercase) so Python `_fill_is_gradient_authoring` and
Node `fillIsGradientAuthoring` cannot drift. Hosts still treat dict/object
fills as authoring. Compile-path flag bits stay extra.
ABI 232 `xyg_scene_hexbin_reduce_admit` owns Scene hexbin reduce names
(`count`/`mean`/`sum`/`custom`; unknown/empty reject; no lowercasing) so
Python `_figure_trace_support_flags` and Node `figureTraceSupport` cannot
drift. Hosts still check hexbin kind. Compile-path `HEXBIN_REDUCES` in
`scene_export.rs` stays extra.
ABI 233 `xyg_scene_curve_classify` owns Scene curve names (`linear` → 0,
`smooth` → 1; unknown/empty → 255; trim then lowercase) so Python
`_figure_trace_support_flags` and Node `figureTraceSupport` cannot drift.
Hosts still check kind for `smooth`. Compile-path `curve_smooth` in
`scene_trace_compile.rs` stays extra.
ABI 234 `xyg_scene_marker_glyph_admit` owns Scene marker-glyph UTF-8 admit
(nonempty, no NUL/CR/LF, at most 64 bytes) so Python `_admitted_marker_glyph`
and Node `admittedMarkerGlyph` cannot drift. Hosts still coerce non-strings
and check scatter kind / combined `marker_path`. Compile-path `admit_glyph`
stays extra.
ABI 235 `xyg_scene_kind_admit` owns Scene product-kind names (exact
`scatter`/`line`/`bar`/`column`/`histogram`/`violin`/`box`/`segments`/
`errorbar`/`stem`/`contour`/`box_whisker`/`box_median`/`area`/`error_band`/
`ribbon`/`triangle_mesh`/`hexbin`/`heatmap`; unknown/empty reject; no
lowercasing) so Python `_figure_trace_support_flags` and Node
`figureTraceSupport` cannot drift. Packing-family bits are ABI 236.
ABI 236 `xyg_scene_kind_class` owns Scene packing-family bits (rect/segment/
band/ribbon/polyfill/hexbin/heatmap/stroke/scatter/line; unknown/empty → 0;
no lowercasing) so Python `_scene_v3` pack and Node `scene.js` pack cannot
drift. Hosts still pick channels and pack rows. Smooth-kind eligibility
uses the existing LINE|BAND bits (no new ABI).
ABI 237 `xyg_scene_hexbin_pitch_admit` owns Scene hexbin cell-pitch admit
(finite strictly-positive `dx`/`dy`) so Python `_hexbin_pitch` and Node
XYEP pack cannot drift. Field picking (`hex_dx` vs `dx`) stays host.
Compile-path `hex_pitch` in `scene_trace_compile.rs` stays extra.
ABI 238 `xyg_scene_heatmap_extent_admit` owns Scene heatmap cell-extent
admit (all four finite and `x0 < x1 && y0 < y1`) so Python `_heatmap_extent`
and Node XYEP pack cannot drift. Length==2 and field picking stay host.
Compile-path `heatmap_extent_columns` in `scene_pack.rs` stays extra.
ABI 239 `xyg_scene_heatmap_colormap_admit` owns Scene heatmap colormap
eligibility (OR of already-coerced truecolor / colormap / rgba_grid / rgba
flags) so Python `_heatmap_uses_colormap` and Node `figureTraceSupport`
cannot drift. Field picking and truthy coercion stay host. Kind checks
stay host.
ABI 240 `xyg_scene_heatmap_shape_admit` owns Scene heatmap lattice-shape
admit (finite integer-valued `rows`/`cols` `>= 1`) so Python `_heatmap_shape`
and Node XYEP pack cannot drift. Length==2 stays host. XYTA integer coerce
uses the same kernel (no new ABI). Closes Python `int()` truncation vs Node `Number.isInteger`.
ABI 241 `xyg_scene_scatter_paint_channel_admit` owns Scene scatter paint-plane
channel names (exact `color`/`stroke`/`stroke_width`/`opacity`/`artist_alpha`;
unknown/empty → 0; no lowercasing) so Python `_scatter_packs_paint_plane` and
Node `scatterPacksPaintPlane` cannot drift. Kind, density, and name gathering
stay host.
ABI 242 `xyg_scene_hexbin_colormap_plane_admit` owns Scene hexbin colormap-plane
packing (exact `continuous` plus a values-present flag; unknown/empty → 0; no
lowercasing) so Python `_hexbin_packs_colormap_plane` and Node
`hexbinPacksColormapPlane` cannot drift. Kind checks and field picking
(`color_ch` vs `colorChannel`, `values` vs `metric`) stay host.
ABI 243 `xyg_scene_hexbin_rgba_plane_admit` owns Scene hexbin RGBA-plane
modes (exact `categorical`/`direct_rgba`; unknown/empty → 0; no lowercasing)
so Python `_hexbin_packs_rgba_plane` and Node `hexbinPacksRgbaPlane` cannot
drift. Kind checks, field picking, and RGBA8 packing stay host.
ABI 244 `xyg_scene_mesh_paint_plane_admit` owns Scene mesh paint-plane packing
(exact `triangle_mesh` plus `joined_fill == 0` plus a per-item flag;
unknown/empty → 0; no lowercasing) so Python `_mesh_packs_paint_plane` and
Node `meshPacksPaintPlane` cannot drift. `joined_fill` field picking and
`has_per_item` gathering stay host.
ABI 245 `xyg_scene_item_apply_opacity` owns Scene per-item RGBA8 artist-alpha
replace then opacity multiply (ties-to-even u8 quantize) so Python
`_item_apply_opacity` and Node `itemApplyOpacity` cannot drift. Field picking
stays host.
ABI 246 `xyg_scene_item_widths_admit` owns Scene per-item stroke-width
admit (present values: `len == n` and every value finite `>= 0`; absent:
finite scalar `>= 0`) so Python `_item_widths` and Node `itemWidths` cannot
drift. Field picking and f64 packing stay host.
ABI 247 `xyg_scene_item_fill_t` owns Scene continuous per-item fill unit-t
(domain pair as-is, else finite min/max; zero/non-finite span → zeros;
clip to `[0, 1]`) so Python `_item_fill_rgba8` and Node `itemFillRgba8`
cannot drift. Field picking and colormap lookup stay host.
ABI 248 `xyg_scene_finite_all` owns Scene finite-all admit (empty → `1`)
so Python `_xyep_finite` / heatmap XYEP and Node `exportColumnFinite`
cannot drift. Field picking stays host.
ABI 249 `xyg_scene_gradient_solid_css` owns Scene gradient solid CSS
(first packed RGBA8 stop with alpha `> 0` → `rgb(r,g,b)`; else
`rgb(0,0,0)`) so Python `_gradient_solid_css` and Node `gradientSolidCss`
cannot drift. Field picking stays host.
ABI 250 `xyg_scene_arrays_equal` owns Scene f64 arrays-equal (lengths
match and every pair is IEEE `==`; empty equal; NaN never equals) so
Python companion x1/y1 match and Node `exportArraysEqual` cannot drift.
Field picking and null checks stay host.
ABI 251 `xyg_clip_quantize_u8` owns unit-f64 clip-to-`[0, 1]` × 255
ties-to-even u8 quantize (NaN → 0) so Python `_quantized_rgba8` /
`channels.ship_color_channel` and Node `clipQuantizeU8` /
`resolveColorChannel` / `channelEndRgba8` cannot drift. Field picking
stays host.
ABI 252 `xyg_scene_constant_color_admit` owns Scene constant-color admit
(`0` fail, `1` style fallback, `2` channel constant) so Python
`_constant_color` and Node `constantMarkColor` cannot drift. Ribbon-fail
and field picking stay host.
ABI 253 `xyg_scene_hidden_or_per_item_admit` owns Scene hidden-or-per-item
admit (`hidden || (has_per_item && !density_aggregates)`) so Python
`_figure_trace_support_flags` and Node `figureTraceSupport` cannot drift.
Field picking stays host.
Python `colormap_lut_rgba8` and Node `colormapLutRgba8` sample 256
unit-t texels through ABI 206 `xyg_colormap_lut` then host-pack alpha
255 so the density LUT cannot drift on half-up vs ties-to-even.
Python `quantize_unit_u8` / `_quantized_lut_idx` and Node
`quantizeUnitU8` / `resolveDensityBinColors` normalize through
`xyg_normalize_f32` (nonfinite → 0) then ABI 251 `xyg_clip_quantize_u8`.
Equal or non-finite domain stays a host zero-span short-circuit.
Python `palette_rows_rgba8` quantizes `css_check` 0-1 channels through
ABI 251 `xyg_clip_quantize_u8`. Browser-only palette status and per-index
substitute stay host.
Python `_svg._paint_rgba8` resolves CSS paints through `xyg_css_color_rgba`,
matching `_raster._parse_color` and Node `cssColorRgba8`.
Python `resolved_hex_paint` / `_resolved_rgb` quantize `css_check` 0-1
channels through ABI 251 `xyg_clip_quantize_u8`. Browser-only rejection stays host.
Python `resolve_style_channel` admits finite arrays through ABI 248
`xyg_scene_finite_all`. Bounds checks stay host.
SVG `_rgb_css` formats 0-1 RGB through ABI 251 `xyg_clip_quantize_u8`.
SVG authored-scatter marker RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster scatter RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster mesh/hexbin fill RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster rectangle style RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster segment stroke RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster mesh stroke RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster ribbon fill RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster ribbon match-fill edge RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Node `meshHasPerItem` uses `perItemChannelNames` (same as Python `has_per_item_channels`) for ABI 244.
Node `scatterPaintChannelNames` uses `perItemChannelNames` (same as Python `per_item_channel_names`) for ABI 241.
Node hexbin colormap-plane packing uses `channel.values` (same as Python); `trace.metric` is not a values fallback.
Node empty kind uses `|| "mark"` (same as Python `or "mark"`).
Node `figureTraceSupport` does not fail-close `style.smooth`; curve names stay ABI 233.
Node `itemWidths` fail-closes a present `stroke_width` channel without values (same as Python).
Node `itemApplyOpacity` fail-closes a present opacity/artist_alpha channel without values (same as Python).
Node missing scatter kind uses `|| ""` (same as Python); it is not defaulted to `"scatter"`.
Node `fillIsGradientAuthoring` rejects arrays (same as Python dict-only).
Node `rectExtraFlags` treats only mapping fills as gradient-fail (same as Python dict-only).
Node `admittedMarkerGlyph` rejects non-strings (same as Python `isinstance(..., str)`).
Node `packXyTaColormap` uses `style.colormap` only (same as Python); `trace.colormap` / `colormapStops` are not fallbacks.
Node hexbin XYTA colormap uses `channel.colormap` only (same as Python); `style.colormap` is not a fallback.
Node XYHF heatmap/density colormap uses `style.colormap` only (same as Python); `trace.colormap` / `colormapStops` are not fallbacks.
Node `constantMarkColor` uses `color_ch.constant` only (same as Python); string channels, `channel.color`, and `trace.color` are not fallbacks.
Node `channelConstantCss` uses `channel.constant` only (same as Python); string channels and `channel.color` are not fallbacks.
Node `channelEndRgba8` constant paint uses `channel.constant` only (same as Python); string channels and `channel.color` are not fallbacks.
Node `sourceColorCss` uses `color_ch` only (same as Python); `trace.color` is not a source-channel fallback.
Node `resolveColorChannel` constant CSS uses `.constant` (same as Python `ColorChannel`); `composeRibbon` writes `color_ch` / `color2_ch`.
Node `color2Channel` uses `color2_ch` only (same as Python); `color_target` / `colorTarget` are not Scene-pack fallbacks.
Node `itemFillRgba8` uses `color_ch` only (same as Python); `trace.color` is not a fill-channel fallback.
Node `scatterPaintChannelNames` uses `color_ch` only (same as Python); `trace.color` is not a per-item color channel.
Node `scatterHasNonConstantColor` uses `color_ch` only (same as Python); `trace.color` is not a non-constant-color fallback.
Node `resolveDensityBinColors` uses `color_ch` only (same as Python); `trace.color` is not a density-bin color channel.
Node `scatterHasNonConstantColor` ignores `style.color_channel` (same as Python); only `color_ch` is a non-constant-color channel.
Node `scatterPaintChannelNames` ignores `style.color_channel` / `stroke_channel` / `size_channel` (same as Python); per-item extras come from `style_channels`.
Node `resolveDensityBinColors` ignores `style.color_channel` (same as Python); only `color_ch` is a density-bin color channel.
Node XYMS mark color uses `style.color` only (same as Python `_constant_color` style fallback); `trace.color` is not a mark-color fallback.
Node XYTC style color uses `style.color` only (same as Python); `trace.color` is not a packed-color fallback.
Node XYTC constant paint uses `channel.constant` only (same as Python); `channel.color` is not a packed-constant fallback.
Node density-blit observation uses `scatterUsesDensity` (same as Python `use_density`); `style.color_channel` is not a per-item density extra.
Node XYTC color_ch packing ignores string channels (same as Python object-only); only a channel object packs COLOR_CH.
Node `scatterHasNonConstantColor` uses `channel.constant` only (same as Python); `channel.color` is not a packed-constant stand-in.
Node XYTC `COLOR_CH_CONSTANT` packs whenever `channel.constant` is set (same as Python); `mode === "constant"` is not a gate.
Node XYMS mark color uses `constantMarkColor` / ABI 252 (same as Python `_constant_color`); `style.color` is the code-1 fallback only.
Node `scatterPerItemChannels` ignores `style.color_channel` / `size_channel` / `stroke_channel` (same as Python `has_per_item_channels`); only `*_ch` presence counts.
Node `scatterPerItemChannels` is mode-based like Python `has_per_item_channels`; a constant `color_ch` is not per-item.
Node `channelEndRgba8` ignores array and typed-array channels (same as Python object-only); only `null` and mode objects pack.
Node `channelEndRgba8` categorical paint uses `DEFAULT_PALETTE` when palette is empty (same as Python); fallback CSS is not a missing-slot stand-in.
Node `packXyTaColormap` stop bytes require RGB rows like Python `_colormap_stop_bytes`; a flat or RGBA list packs empty stops.
Node `xyHfColormap` stop bytes require RGB rows like Python `_colormap_stop_bytes`; a flat or RGBA list packs empty stops.
Node `packXyTaRgbaGrid` stacks flattened planes like Python `_pack_xyta` `rgba_grid`; nested 2D index fallback is not a plane layout.
Node heatmap `trace.rgba` stores a flat uint8 buffer; `packXyTaRgba` packs that buffer like Python `_pack_xyta` and does not unwrap nested `.rgba`.
Node heatmap and density Scene packing is XYTA-only like Python `_pack_xyta`; unused XYHF paint-plane helpers are not a second plane layout.
Node `packXyTaGrid` flattens heatmap `grid` like Python `_pack_xyta` (`plane.values` or plane); nested length indexing is not a grid layout.
Node `rectFiniteSel` drops nonfinite rectangle rows through `validIndicesF64` like Python `_rect_finite_sel`; NaN never reaches vertex buffers (§19).
Node `packXyTa` density fill opacity uses `style.fill_opacity` only like Python `_pack_xyta`; `fillOpacity` is not a fill-opacity key.
Node XYTC fill opacity uses `style.fill_opacity` only like Python `_pack_xytc`; `fillOpacity` is not a fill-opacity key.
Node XYTC stroke opacity uses `style.stroke_opacity` only like Python `_pack_xytc`; `strokeOpacity` is not a stroke-opacity key.
Node XYTC line opacity uses `style.line_opacity` only like Python `_pack_xytc`; `lineOpacity` is not a line-opacity key.
Node XYTC stroke width uses `style.stroke_width` only like Python `_pack_xytc`; `strokeWidth` is not a stroke-width key.
Node XYTC line width uses `style.line_width` only like Python `_pack_xytc`; `lineWidth` is not a line-width key.
Node XYTC size uses `style.size` only like Python `_pack_xytc`; `diameter` is not a size key.
Node XYTC line color uses `style.line_color` only like Python `_pack_xytc`; `lineColor` is not a line-color key.
Node XYTC joined fill uses `style.joined_fill` only like Python `_pack_xytc`; `joinedFill` is not a joined-fill key.
Node XYTC stroke perimeter uses `style.stroke_perimeter` only like Python `_pack_xytc`; `strokePerimeter` is not a stroke-perimeter key.
Node XYTC COLOR_CH packing uses `color_ch` only like Python `_pack_xytc`; `colorChannel` is not a packed-channel fallback.
Node XYTC size_ch packing uses `size_ch` only like Python `_pack_xytc`; `sizeChannel` is not a packed-channel fallback.
Node XYEF stroke-width-only observation uses `style.stroke_width` only like Python; `strokeWidth` is not an observation key.
Node `meshJoinedFill` uses `style.joined_fill` only like Python `_mesh_joined_fill`; `joinedFill` is not a joined-fill key.
Node XYEF joined-fill observation uses `style.joined_fill` only like Python; `joinedFill` is not an observation key.
Node `constantMarkColor` uses `color_ch` only like Python `_constant_color`; `colorChannel` is not a source-channel fallback.
Node `sourceColorCss` uses `color_ch` only like Python `_trace_source_color_css`; `colorChannel` is not a source-css fallback.
Node `scatterHasNonConstantColor` uses `color_ch` only like Python; `colorChannel` is not a non-constant-color fallback.
Node `classifyRibbonColor2` source-constant CSS uses `color_ch` only like Python `_classify_ribbon_color2`; `colorChannel` is not a source-constant fallback.
Node `itemFillRgba8` uses `color_ch` only like Python `_item_fill_rgba8`; `colorChannel` is not a fill-channel fallback.
Node `resolveDensityBinColors` uses `color_ch` only like Python; `colorChannel` is not a density-bin color channel.
Node `hexbinPacksColormapPlane` uses `color_ch` only like Python `_hexbin_packs_colormap_plane`; `colorChannel` is not a colormap-plane fallback.
Node `ribbonEndRgbaPair` uses `color_ch` only like Python `_ribbon_end_rgba_pair`; `colorChannel` is not a ribbon-end source fallback.
Node `hexbinXyTaColormap` uses `color_ch` only like Python `_pack_xyta` hexbin colormap; `colorChannel` is not a colormap fallback.
Node `hexbinPacksRgbaPlane` uses `color_ch` only like Python `_hexbin_packs_rgba_plane`; `colorChannel` is not an RGBA-plane fallback.
Node `hexbinCellRgba8` uses `color_ch` only like Python `_hexbin_cell_rgba8`; `colorChannel` is not a cell-paint fallback.
Node XYTA density color_ch packing uses `color_ch` only like Python `_pack_xyta`; `colorChannel` is not a packed-constant fallback.
Node `itemStrokeRgba8` uses `stroke_ch` only like Python `_item_stroke_rgba8`; `strokeChannel` is not a stroke-channel fallback.
Node `scatterPointStrokeRgba8` uses `stroke_ch` only like Python `_scatter_point_stroke_rgba8`; `strokeChannel` is not a match-fill opacity skip.
Node `perItemChannelNames` uses `color_ch` / `stroke_ch` / `size_ch` / `style_channels` only like Python `per_item_channel_names`; camelCase channel fields are not per-item name fallbacks.
Node `itemApplyOpacity` uses `style_channels` only like Python `_item_apply_opacity`; `styleChannels` is not an opacity-channel fallback.
Node `itemWidths` uses `style_channels` only like Python `_item_widths`; `styleChannels` is not a width-channel fallback.
Node `scatterUsesDensity` uses `force_density` only like Python `use_density`; `forceDensity` is not a density-force fallback.
Node `figureTraceSupport` uses `style.linecap` only like Python `_figure_trace_support_flags`; `lineCap` is not a dashed-marker linecap fallback.
Node `packXyTcLinecap` uses `style.linecap` only like Python `_pack_xytc`; `lineCap` is not a packed-linecap fallback.
Node `packXyAfLinecap` uses `style.linecap` only like Python `_pack_xyaf`; `lineCap` is not an annotation-linecap fallback.
Node `scatterUsesDensity` does not pass `force_direct` like Python `use_density`; `forceDirect` / `force_direct` are not density-direct overrides.
Node hexbin XYTA values packing uses `color_ch` only like Python `_pack_xyta`; `colorChannel` is not a hexbin-grid values fallback.
Node `legendStyleFontSizes` uses `style.font_size` / `style.title_font_size` only like Python `_legend_input`; `fontSize` / `titleFontSize` are not legend-font fallbacks.
Node `heatmapGridShape` uses `grid_shape` only like Python `_heatmap_shape`; `gridShape` is not a heatmap-lattice fallback.
Node `hexbinStylePitch` uses `style.hex_dx` then `style.dx` like Python `_hexbin_pitch`; `hexDx` / `hexDy` are not hexbin-pitch fallbacks.
Node `polarGridShape` uses axis `grid_shape` only like Python `_pack_polar_scene_input`; `gridShape` is not a polar-grid fallback.
Node `polarAxisThetaUnit` uses axis `theta_unit` only like Python `_pack_polar_scene_input`; `thetaUnit` is not a polar-unit fallback.
Node `polarAxisThetaZero` uses axis `theta_zero` only like Python `_pack_polar_scene_input`; `thetaZero` is not a polar-zero fallback.
Node `polarAxisThetaDirection` uses axis `theta_direction` only like Python `_pack_polar_scene_input`; `thetaDirection` is not a polar-direction fallback. Node `polarAxisROrigin` uses axis `r_origin` only like Python `_pack_polar_scene_input`; `rOrigin` is not a polar-origin fallback. Node `axisTickValues` uses axis `tick_values` only like Python `_pack_figure_chrome`; `tickValues` is not a chrome-major-tick fallback. Node `axisMinorTickValues` uses axis `minor_tick_values` only like Python `_pack_figure_chrome`; `minorTickValues` is not a chrome-minor-tick fallback. Node `axisTickLabels` uses axis `tick_labels` only like Python `_pack_figure_chrome`; `tickLabels` is not a chrome-tick-label fallback. Node `figureXLabel` uses `x_label` then axis `label` like Python `_pack_figure_chrome`; `xLabel` is not a chrome-xlabel fallback. Node `figureYLabel` uses `y_label` then axis `label` like Python `_pack_figure_chrome`; `yLabel` is not a chrome-ylabel fallback. Node `plotTopAxisRoom` uses plot `top_axis_room` only like Python `recut_polar_plot`; `topAxisRoom` is not a polar-recut-room fallback. Node `axisTickLabelAnchor` uses axis `tick_label_anchor` only like Python `_scene_tick_anchor_code`; `tickLabelAnchor` is not a chrome-tick-anchor fallback. Node `axisTickLabelMinGap` uses axis `tick_label_min_gap` only like Python `_pack_tick_collision`; `tickLabelMinGap` is not a chrome-tick-gap fallback. Node `axisTickLabelAngle` uses axis `tick_label_angle` only like Python `_pack_tick_collision`; `tickLabelAngle` is not a chrome-tick-angle fallback. Node `axisTickLabelStrategy` uses `tick_label_strategy` then `collision` like Python `_scene_tick_label_strategy`; `tickLabelStrategy` is not a chrome-tick-strategy fallback. Node `polarCollisionKeys` uses snake-case keys only like Python `_POLAR_COLLISION_KEYS`; camelCase tick-label keys are not polar-collision-key extras. Node `figureChromeStyles` uses `chrome_styles` only like Python `_pack_figure_support`; `chromeStyles` is not a chrome-styles fallback. Node `chromeStyleHasFontFamily` uses `font-family` only like Python `_pack_figure_support`; `fontFamily` is not a chrome-font-family fallback. Node `figureClassName` uses `class_name` only like Python `_pack_figure_support`; `className` is not a figure-class-name fallback. Node `figureClassNames` uses `class_names` only like Python `_pack_figure_support`; `classNames` is not a figure-class-names fallback. Node `annotationClassName` uses `class_name` only like Python `_pack_figure_support`; `className` is not an annotation-class-name fallback. Node `figureExtraLegends` uses `extra_legends` only like Python `_pack_figure_support`; `extraLegends` is not an extra-legends fallback. Node `figureTitleOptions` uses `title_options` only like Python `_pack_public_export_support`; `titleOptions` is not a title-options fallback. Node `figureLegendOptions` uses `legend_options` only like Python `_legend_input`; `legend` is not a legend-options fallback. Node `figureColorbarOptions` uses `colorbar_options` only like Python `_colorbar_input`; `colorbarOptions` is not a colorbar-options fallback. Node `figureShowLegend` uses `show_legend` only like Python `_legend_input`; `showLegend` is not a show-legend fallback. Node `figureAxisOptions` uses `axis_options` only like Python `_pack_figure_chrome`; `xAxis` / `x_axis` are not axis-options fallbacks. Node `axisScaleName` uses axis `type` only like Python `_axis_scale`; `kind` is not an axis-scale fallback. Node `figureAutorangeAxisOptions` uses `axis_options` only like Python `_axis_scale`; `xAxis` is not an autorange-axis fallback. Node `_emitScatter` uses `force_density` only like Python `payload_force_density`; `style.force_density` is not a payload-density fallback. Node `_emitScatter` does not read `style.force_direct` like Python `_emit_scatter`; `style.force_direct` is not a payload-direct fallback. Node `_emitScatter` does not read `style.force_pyramid` like Python `_emit_scatter`; `style.force_pyramid` is not a payload-pyramid fallback. Node `_emitScatterDensity` does not read `style.force_bin2d` like Python `_density_trace_spec`; `style.force_bin2d` is not a payload-bin2d fallback. Node `_emitScatterDensity` does not read `style.no_rescan` like Python `_density_trace_spec`; `style.no_rescan` is not a payload-no-rescan fallback. Node `chromeAxisMinorStyle` uses `minor_style` only like Python `_pack_chrome_axis`; `minorStyle` is not a chrome-minor-style fallback. Node `chromeAxisTickSides` uses `tick_sides` only like Python `_pack_chrome_axis`; `tickSides` is not a chrome-tick-sides fallback. Node `chromeAxisTickLabelSides` uses `tick_label_sides` only like Python `_pack_chrome_axis`; `tickLabelSides` is not a chrome-tick-label-sides fallback. Node `chromeAxisStyleKeys` admits snake-case keys only like Python `_SCENE_AXIS_STYLE_KEYS`; camelCase axis style keys are not a chrome-axis-style-keys fallback. Node `chromeAxisStyleHas` / `chromeAxisStyleValue` read snake-case keys only like Python `_pack_chrome_axis`; camelCase fields are not a chrome-axis-style-read fallback. Node `legendAxisScale` uses axis `type` only like Python `_axis_scale`; `scale` / `kind` are not a legend-axis-scale fallback. Node `figureAutorangeAxisScale` uses axis `type` only like Python `_axis_scale`; `kind` is not an autorange-axis-scale fallback. Node `figureAxisKind` matches Python `_axis_kind` (forced `type` time, then category labels, then `time_ms` columns); axis `kind` is not an autorange-axis-kind fallback. Node `chromeAxisTickKind` uses `Figure._axisKind` like Python `_pack_figure_chrome` / `_pack_tick_collision`; axis `kind` is not a chrome-tick-kind fallback. Node `xyEfResolvedKind` uses `Figure._axisKind` like Python `_pack_public_export_support`; axis `kind` is not an xyef-axis-kind fallback. Node `figureAutorangeThetaUnit` uses axis `theta_unit` only like Python `_pack_autorange`; `thetaUnit` is not an autorange-theta-unit fallback. Node `figureAxisIsLog` uses axis `type` only like Python `_axis_scale` log; `scale` is not an axis-is-log fallback. Node `figureAutorangeCategories` uses `_axis_categories` only like Python `_pack_autorange`; `options.categories` is not an autorange-categories fallback. Node `figureAutorangeDomain` uses axis `domain` only like Python `_pack_autorange`; `_axisRange` is not an autorange-domain fallback. Node `setPolarMeta` writes axis `theta_unit` like Python `set_axis`; `_polarMeta.thetaUnit` is not a polar-meta-unit fallback. Node `setPolarMeta` writes axis `theta_zero` like Python `set_axis`; `_polarMeta.thetaZero` is not a polar-meta-zero fallback. Node `setPolarMeta` writes axis `theta_direction` like Python `set_axis`; `_polarMeta.thetaDirection` is not a polar-meta-direction fallback. Node `setPolarMeta` writes axis `grid_shape` like Python `set_axis`; `_polarMeta.gridShape` is not a polar-meta-grid fallback. Node `setPolarMeta` writes axis `hole` like Python `set_axis`; `_polarMeta.hole` is not a polar-meta-hole fallback. Node `setPolarMeta` writes axis `sector` like Python `set_axis`; `_polarMeta.sector` is not a polar-meta-sector fallback. Node `polarAxisHole` uses axis `hole` only like Python `_pack_polar_scene_input`; `Hole` is not a polar-hole fallback. Node `polarAxisSector` uses axis `sector` only like Python `_pack_polar_scene_input`; `Sector` is not a polar-sector fallback. Node `_polarAxisSpecs` uses axis `theta_unit` like Python `_axis_spec`; `_polarMeta.thetaUnit` is not a polar-spec-unit fallback. Node `_polarAxisSpecs` uses axis `theta_zero` like Python `_axis_spec`; `_polarMeta.thetaZero` is not a polar-spec-zero fallback. Node `_polarAxisSpecs` uses axis `theta_direction` like Python `_axis_spec`; `_polarMeta.thetaDirection` is not a polar-spec-direction fallback. Node `_polarAxisSpecs` uses axis `grid_shape` like Python `_axis_spec`; `_polarMeta.gridShape` is not a polar-spec-grid fallback. Node `_polarAxisSpecs` uses axis `sector` like Python `_axis_spec`; `_polarMeta.sector` is not a polar-spec-sector fallback. Node `_polarAxisSpecs` uses axis `hole` like Python `_axis_spec`; `_polarMeta.hole` is not a polar-spec-hole fallback. Node `_polarAxisSpecs` uses axis `r_origin` like Python `_axis_spec`; `_polarMeta.rOrigin` is not a polar-spec-origin fallback. Node `packPolarSceneInput` uses figure `_range("y")` like Python `_pack_polar_scene_input`; `rAxis.range` is not a polar-range fallback. Node `shouldUseDensity` maps Boolean `false` to auto (`-1`) unlike Python `payload_force_density` `False` to `0`; that Boolean vs tri-state mapping is a recorded density-tristate stay-host. Node `_emitScatter` still passes `forceDirect` into `shouldUseDensity` unlike Python `_emit_scatter`; that payload force-direct mapping is a recorded emit-force-direct stay-host. Node `_emitScatter` still ORs `forcePyramid` into `shouldUseDensity` unlike Python `_emit_scatter`; that payload force-pyramid mapping is a recorded emit-force-pyramid stay-host. Node `_emitScatterDensity` colormap uses `style.colormap` unlike Python `_density_trace_spec` `color_ch.colormap`; that payload density colormap mapping is a recorded density-colormap stay-host. Node `_emitScatterDensity` colorMode uses `style.color` unlike Python `_density_trace_spec` `color_ch`; that payload density colorMode mapping is a recorded density-colormode stay-host. Node `sourceColorCss` keeps empty `style.color` unlike Python `_trace_source_color_css` `or` default; that empty-string mapping is a recorded source-css-empty stay-host. Node `figureXLabel` keeps empty `x_label` unlike Python `_pack_figure_chrome` `or` fallthrough; that empty-string mapping is a recorded xlabel-empty stay-host. Node `figureYLabel` keeps empty `y_label` unlike Python `_pack_figure_chrome` `or` fallthrough; that empty-string mapping is a recorded ylabel-empty stay-host. Node `packChromeAxis` skips null-valued unsupported keys unlike Python `_pack_chrome_axis` set-difference; that null-key mapping is a recorded chrome-null-key stay-host. Node `itemFillRgba8` fallback stays `sourceColorCss` unlike Python `_item_fill_rgba8` style.get; that fallback mapping is a recorded item-fill-css stay-host. Node `hexbinCellRgba8` fallback stays `sourceColorCss` unlike Python `_hexbin_cell_rgba8` style.get; that fallback mapping is a recorded hexbin-css stay-host. Node `itemStrokeRgba8` empty style.stroke stays unlike Python `_item_stroke_rgba8` or-default; that empty-string mapping is a recorded item-stroke-empty stay-host. Node `_polarAxisSpecs` empty theta_unit stays unlike Python `_axis_spec` or-default; that empty-string mapping is a recorded polar-payload-unit-empty stay-host. Node `_polarAxisSpecs` empty theta_direction stays unlike Python `_axis_spec` or-default; that empty-string mapping is a recorded polar-payload-dir-empty stay-host. Node `_polarAxisSpecs` empty grid_shape stays unlike Python `_axis_spec` or-default; that empty-string mapping is a recorded polar-payload-grid-empty stay-host. Node `_polarAxisSpecs` empty hole stays unlike Python `_axis_spec` or-default; that empty-string mapping is a recorded polar-payload-hole-empty stay-host. Node `_polarAxisSpecs` empty sector stays unlike Python `_axis_spec` or-default; that empty-list mapping is a recorded polar-payload-sector-empty stay-host. Node `scatter()` stores f64 not `Column.kind` unlike Python time_ms columns; that authoring mapping is a recorded scatter-f64-kind stay-host. Node `_emitHexbin` ships `metric` unlike Python `_emit_hexbin` `color_ch`; that payload hexbin metric mapping is a recorded hexbin-metric stay-host. Node `_emitHeatmap` ships grid columns unlike Python `_emit_heatmap` nested heatmap; that payload heatmap grid mapping is a recorded heatmap-grid stay-host. Node `_emitScatter` ships `t.color` unlike Python `_emit_scatter` `color_ch`; that payload scatter color mapping is a recorded scatter-ship-color stay-host. Node `_emitRibbon` ships `t.color_target` unlike Python `_emit_ribbon` `color2_ch`; that payload ribbon color-target mapping is a recorded ribbon-color-target stay-host. Node `_emitRibbon` ships `t.color` unlike Python `_emit_ribbon` `color_ch`; that payload ribbon color mapping is a recorded ribbon-ship-color stay-host. Node `_emitRect` omits `color_ch` unlike Python `_emit_rect`; that payload rect color mapping is a recorded emit-rect-color stay-host. Node `_emitSegments` ships `t.color` unlike Python `_emit_segments` color_ch; that payload segments color mapping is a recorded emit-segments-color stay-host. Node `_emitTriangleMesh` omits `color_ch` unlike Python `_emit_triangle_mesh`; that payload mesh color mapping is a recorded emit-mesh-color stay-host. Node `_emitHistogram` omits `color_ch` unlike Python `_emit_histogram`; that payload histogram color mapping is a recorded emit-hist-color stay-host. Node `_emitTriangleMesh` ships `x`/`y` unlike Python `x2`/`y2`; that payload mesh vertex mapping is a recorded emit-mesh-xy stay-host. Node `_emitScatter` omits `stroke_ch` unlike Python `_ship_trace_styles`; that payload scatter stroke mapping is a recorded emit-scatter-stroke stay-host. Node `_emitRibbon` omits `stroke_ch` unlike Python `_ship_trace_styles`; that payload ribbon stroke mapping is a recorded emit-ribbon-stroke stay-host. Node `_emitRect` omits `stroke_ch` unlike Python `_ship_trace_styles`; that payload rect stroke mapping is a recorded emit-rect-stroke stay-host. Node `_emitTriangleMesh` omits `stroke_ch` unlike Python `_ship_trace_styles`; that payload mesh stroke mapping is a recorded emit-mesh-stroke stay-host. Node `_emitSegments` omits `stroke_ch` unlike Python `_ship_trace_styles`; that payload segments stroke mapping is a recorded emit-segments-stroke stay-host. Node `_emitHistogram` omits `stroke_ch` unlike Python `_ship_trace_styles`; that payload histogram stroke mapping is a recorded emit-hist-stroke stay-host. Node `_emitScatter` omits `style_channels` unlike Python `_ship_trace_styles`; that payload scatter channels mapping is a recorded emit-scatter-channels stay-host. Node `_emitRibbon` omits `style_channels` unlike Python `_ship_trace_styles`; that payload ribbon channels mapping is a recorded emit-ribbon-channels stay-host. Node `_emitRect` omits `style_channels` unlike Python `_ship_trace_styles`; that payload rect channels mapping is a recorded emit-rect-channels stay-host. Node `_emitTriangleMesh` omits `style_channels` unlike Python `_ship_trace_styles`; that payload mesh channels mapping is a recorded emit-mesh-channels stay-host. Node `_emitSegments` omits `style_channels` unlike Python `_ship_trace_styles`; that payload segments channels mapping is a recorded emit-segments-channels stay-host. Node `_emitHistogram` omits `style_channels` unlike Python `_ship_trace_styles`; that payload histogram channels mapping is a recorded emit-hist-channels stay-host. Node `_emitScatter` omits `transition_keys` unlike Python `_transition_entry`; that payload scatter transition mapping is a recorded emit-scatter-transition stay-host. Node `_emitLine` omits `transition_keys` unlike Python `_transition_entry`; that payload line transition mapping is a recorded emit-line-transition stay-host. Node `_emitArea` omits `transition_keys` unlike Python `_transition_entry`; that payload area transition mapping is a recorded emit-area-transition stay-host. Node `_emitHistogram` skips `rectFiniteSel` unlike Python `_emit_rect`; that payload histogram finite-sel mapping is a recorded emit-hist-finite-sel stay-host. Node `_emitRect` ships bar columns unlike Python nested `bar`; that payload bar compact mapping is a recorded emit-bar-compact stay-host. Node `_emitRibbon` skips `valid_indices_f64` unlike Python `_emit_ribbon`; that payload ribbon gather mapping is a recorded emit-ribbon-gather stay-host. Node `_emitTriangleMesh` skips `valid_indices_f64` unlike Python `_emit_triangle_mesh`; that payload mesh gather mapping is a recorded emit-mesh-gather stay-host. Node `_emitRect` omits `transition_keys` unlike Python `_transition_entry`; that payload rect transition mapping is a recorded emit-rect-transition stay-host. Node `_emitRibbon` omits `transition_keys` unlike Python `_transition_entry`; that payload ribbon transition mapping is a recorded emit-ribbon-transition stay-host. Node `_emitTriangleMesh` omits `transition_keys` unlike Python `_transition_entry`; that payload mesh transition mapping is a recorded emit-mesh-transition stay-host.
ABI 209 `xyg_polar_wedge_points` owns compatibility annular-sector flatten
(optional `steps`, `0` = `polar_bar_segments`; finite `norm_lo`/`norm_hi`
skip radial-range normalization) so Python and Node cannot drift. SVG still
emits exact `A` arcs for unrounded wedges.
ABI 210 `xyg_hexbin_ring` owns the pointy-top hexagon vertex offsets scaled
by cell pitch so Python `_svg.hexbin_ring` and Node `hexbinRing` cannot drift.
ChartView `_buildHexbinMark` keeps the same fractions until WASM.
ABI 211 `xyg_step_arrays` owns compatibility step/stairs expand (`mode` 1/2/3
= pre/mid/post; `n < 2` identity) so Python `_svg._step_arrays` and Node
`stepArrays` cannot drift. ChartView `_stepArrays` keeps the same vertices
until WASM.
ABI 212 `xyg_marker_path_scale` owns compatibility authored-marker pixel
vertices (`out_x = cx + scale * unit_x`, `out_y = cy - scale * unit_y`) so
Python `_svg._authored_marker_path_d` / `_raster` and Node `markerPathScale`
cannot drift. ChartView legend/annotation scale keeps the same formula until
WASM. SVG `d=` string assembly stays host.
ABI 213 `xyg_css_is_functional` / `xyg_continuous_domain` /
`xyg_direct_rgba_admit` owns the `resolve_color` CSS/numeric split, equal-bound
domain pad, and Nx3/Nx4 admit so Python `channels.resolve_color` and Node
`resolveColorChannel` cannot drift. Named colors stay categories. Hosts still
factorize labels, pin palettes, and emit warning text.
ABI 214 `xyg_payload_segment_budget` owns the stem/errorbar count budget
(`max(1024, floor(px_width)*4)`) so Python `_payload._emit_segments` and Node
`_emitSegments` cannot drift. ABI 215 `xyg_payload_errorbar_indices` owns
even-index expansion across concatenated role groups so Python and Node
cannot drift on cap-attached errorbar sampling. Hosts still expand
transition-key role maps, gather extra columns, and ship the chosen rows.
ABI 216 `xyg_scale_pins_offset` owns log-family `pin_zero` admission
(`log`/`symlog`, case-sensitive) so Python `lod.pins_offset_to_zero` and
Node `pinsOffsetToZero` cannot drift. Hosts still pack `EncodedColumn`
metadata.
ABI 217 `xyg_arrow_geometry` / `xyg_arrow_shaft_points` /
`xyg_arrow_end_decoration` / `xyg_arrow_taper_polygon` /
`xyg_arrow_trim_polyline_end` owns annotation-arrow connectionstyle geometry
so Python `_arrowgeom.py` and Node `arrowGeometry` cannot drift. ChartView
`51_annotations.ts` keeps the same formula until WASM. Hosts still parse
comma-separated `start_offset` / `label_clear` strings.
ABI 218 `xyg_scene_dash_admit` owns Scene dash presets and 2–8 finite length
patterns so Python `_parse_scene_dash` and Node `parseSceneDash` cannot drift.
Invalid comma tokens reject the whole string. Hosts still coerce list vs
string and fail-close empty strings.
ABI 219 `xyg_scene_linecap_admit` owns Scene linecap names so Python
`_parse_scene_linecap` and Node `parseSceneLinecap` cannot drift. Unknown
names and whitespace-only strings reject. Hosts still fail-close empty
strings without calling the kernel.
ABI 220 `xyg_density_overlay_opacity` owns density overlay sample opacity
(`min(authored, 0.55)`; non-finite → `0.55`) so Python `_payload` and Node
`figure.js` cannot drift. Hosts still default omitted opacity to `0.8`.
ABI 221 `xyg_scene_marker_path_admit` owns Scene marker-path contour bounds
(1–32 contours, x/y pairs, `|v| ≤ 0.500001`, ≤ 96 vertices) so Python
`_validated_marker_path` and Node `validateMarkerPath` cannot drift. Hosts
still coerce mappings and fail-close non-numeric contours. Filled contours
shorter than 6 values stay a compile-path extra.
ABI 222 `xyg_scene_annotation_style_admit` owns Scene annotation style-key
allowlists so Python `_annotation_allowed_style` and Node
`annotationAllowedStyle` cannot drift. Hosts still skip markup/typography/
rotation and raise error text.
ABI 223 `xyg_scene_ribbon_color2_classify` owns ribbon two-ended paint class
(absent/solid/gradient/ends/fail) so Python `_classify_ribbon_color2` and
Node `classifyRibbonColor2` cannot drift. Hosts still coerce channels and
pack end RGBA8.
ABI 224 `xyg_scene_tick_label_strategy` owns Scene tick-label strategy names
so Python `_scene_tick_label_strategy` and Node `sceneTickStrategy` cannot
drift. Hyphens become underscores. Unknown names, including empty text, map
to `auto`. Hosts still pick `tick_label_strategy` vs `collision` vs camelCase
keys.
ABI 225 `xyg_scene_tick_anchor` owns Scene tick-label anchor names so Python
`_scene_tick_anchor_code` and Node `anchorCode` cannot drift. `middle` aliases
`center`. Unknown names, including empty text, reject. Hosts still pick
`tick_label_anchor` vs camelCase keys. ABI 123 layout enums stay a separate
throw-on-unknown table.
ABI 226 `xyg_scene_fill_gradient_admit` owns Scene fill-gradient stop admit
(space/dir, 2–8 monotone `t` in `[0, 1]`, `var(` reject, empty/`currentcolor`
→ mark color, RGBA8) so Python `_admitted_fill_gradient_from_fill` and Node
`admitFillGradient` cannot drift. Hosts still coerce fill mappings.
ABI 227 `xyg_scene_parse_linear_gradient` owns CSS `linear-gradient(...)`
parse (cardinal `to` directions, 2–8 resolved stops, nested function commas)
so Python `mark_fill` / `_admitted_fill_gradient_from_fill` and Node
`parseLinearGradient` cannot drift. Hosts still coerce fill mappings, wrap
authoring error text, and run `css_color` on authoring stops. Compile-path
skip-empty split stays extra.
ABI 228 `xyg_scene_rect_extra_flags` owns Scene rect extra-flag pack
(unusable-gradient bit, admitted corner-radius kinds, polar wedge-gap
exception) so Python `_rect_extra_flags` and Node `rectExtraFlags` cannot
drift. Hosts still coerce fill mappings, radius lists, and `wedge_gap`.
ABI 229 `xyg_scene_gradient_dir` owns Scene fill-gradient direction codes
(`down`/`up`/`right`/`left`; unknown/empty → 255; no lowercasing) so Python
`_pack_gradient_spec` / XYSS pack and Node `packGradientSpec` cannot drift.
Hosts still pick `dir` vs missing keys. Compile-path `to bottom` aliases stay extra.
ABI 231 `xyg_scene_gradient_space` owns Scene fill-gradient space codes
(`mark`/`plot`; unknown/empty → 255; no lowercasing) so Python
`_pack_gradient_spec` / XYSS pack and Node `packGradientSpec` cannot drift.
Hosts still pick `space` vs missing keys. XYSS plot-space is `code == 1`.
ABI 230 `xyg_scene_linear_gradient_prefix` owns the CSS `linear-gradient(`
prefix check (trim, lowercase) so Python `_fill_is_gradient_authoring` and
Node `fillIsGradientAuthoring` cannot drift. Hosts still treat dict/object
fills as authoring. Compile-path flag bits stay extra.
ABI 232 `xyg_scene_hexbin_reduce_admit` owns Scene hexbin reduce names
(`count`/`mean`/`sum`/`custom`; unknown/empty reject; no lowercasing) so
Python `_figure_trace_support_flags` and Node `figureTraceSupport` cannot
drift. Hosts still check hexbin kind. Compile-path `HEXBIN_REDUCES` in
`scene_export.rs` stays extra.
ABI 233 `xyg_scene_curve_classify` owns Scene curve names (`linear` → 0,
`smooth` → 1; unknown/empty → 255; trim then lowercase) so Python
`_figure_trace_support_flags` and Node `figureTraceSupport` cannot drift.
Hosts still check kind for `smooth`. Compile-path `curve_smooth` in
`scene_trace_compile.rs` stays extra.
ABI 234 `xyg_scene_marker_glyph_admit` owns Scene marker-glyph UTF-8 admit
(nonempty, no NUL/CR/LF, at most 64 bytes) so Python `_admitted_marker_glyph`
and Node `admittedMarkerGlyph` cannot drift. Hosts still coerce non-strings
and check scatter kind / combined `marker_path`. Compile-path `admit_glyph`
stays extra.
ABI 235 `xyg_scene_kind_admit` owns Scene product-kind names (exact
`scatter`/`line`/`bar`/`column`/`histogram`/`violin`/`box`/`segments`/
`errorbar`/`stem`/`contour`/`box_whisker`/`box_median`/`area`/`error_band`/
`ribbon`/`triangle_mesh`/`hexbin`/`heatmap`; unknown/empty reject; no
lowercasing) so Python `_figure_trace_support_flags` and Node
`figureTraceSupport` cannot drift. Packing-family bits are ABI 236.
ABI 236 `xyg_scene_kind_class` owns Scene packing-family bits (rect/segment/
band/ribbon/polyfill/hexbin/heatmap/stroke/scatter/line; unknown/empty → 0;
no lowercasing) so Python `_scene_v3` pack and Node `scene.js` pack cannot
drift. Hosts still pick channels and pack rows. Smooth-kind eligibility
uses the existing LINE|BAND bits (no new ABI).
ABI 237 `xyg_scene_hexbin_pitch_admit` owns Scene hexbin cell-pitch admit
(finite strictly-positive `dx`/`dy`) so Python `_hexbin_pitch` and Node
XYEP pack cannot drift. Field picking (`hex_dx` vs `dx`) stays host.
Compile-path `hex_pitch` in `scene_trace_compile.rs` stays extra.
ABI 238 `xyg_scene_heatmap_extent_admit` owns Scene heatmap cell-extent
admit (all four finite and `x0 < x1 && y0 < y1`) so Python `_heatmap_extent`
and Node XYEP pack cannot drift. Length==2 and field picking stay host.
Compile-path `heatmap_extent_columns` in `scene_pack.rs` stays extra.
ABI 239 `xyg_scene_heatmap_colormap_admit` owns Scene heatmap colormap
eligibility (OR of already-coerced truecolor / colormap / rgba_grid / rgba
flags) so Python `_heatmap_uses_colormap` and Node `figureTraceSupport`
cannot drift. Field picking and truthy coercion stay host. Kind checks
stay host.
ABI 240 `xyg_scene_heatmap_shape_admit` owns Scene heatmap lattice-shape
admit (finite integer-valued `rows`/`cols` `>= 1`) so Python `_heatmap_shape`
and Node XYEP pack cannot drift. Length==2 stays host. XYTA integer coerce
uses the same kernel (no new ABI). Closes Python `int()` truncation vs Node `Number.isInteger`.
ABI 241 `xyg_scene_scatter_paint_channel_admit` owns Scene scatter paint-plane
channel names (exact `color`/`stroke`/`stroke_width`/`opacity`/`artist_alpha`;
unknown/empty → 0; no lowercasing) so Python `_scatter_packs_paint_plane` and
Node `scatterPacksPaintPlane` cannot drift. Kind, density, and name gathering
stay host.
ABI 242 `xyg_scene_hexbin_colormap_plane_admit` owns Scene hexbin colormap-plane
packing (exact `continuous` plus a values-present flag; unknown/empty → 0; no
lowercasing) so Python `_hexbin_packs_colormap_plane` and Node
`hexbinPacksColormapPlane` cannot drift. Kind checks and field picking
(`color_ch` vs `colorChannel`, `values` vs `metric`) stay host.
ABI 243 `xyg_scene_hexbin_rgba_plane_admit` owns Scene hexbin RGBA-plane
modes (exact `categorical`/`direct_rgba`; unknown/empty → 0; no lowercasing)
so Python `_hexbin_packs_rgba_plane` and Node `hexbinPacksRgbaPlane` cannot
drift. Kind checks, field picking, and RGBA8 packing stay host.
ABI 244 `xyg_scene_mesh_paint_plane_admit` owns Scene mesh paint-plane packing
(exact `triangle_mesh` plus `joined_fill == 0` plus a per-item flag;
unknown/empty → 0; no lowercasing) so Python `_mesh_packs_paint_plane` and
Node `meshPacksPaintPlane` cannot drift. `joined_fill` field picking and
`has_per_item` gathering stay host.
ABI 245 `xyg_scene_item_apply_opacity` owns Scene per-item RGBA8 artist-alpha
replace then opacity multiply (ties-to-even u8 quantize) so Python
`_item_apply_opacity` and Node `itemApplyOpacity` cannot drift. Field picking
stays host.
ABI 246 `xyg_scene_item_widths_admit` owns Scene per-item stroke-width
admit (present values: `len == n` and every value finite `>= 0`; absent:
finite scalar `>= 0`) so Python `_item_widths` and Node `itemWidths` cannot
drift. Field picking and f64 packing stay host.
ABI 247 `xyg_scene_item_fill_t` owns Scene continuous per-item fill unit-t
(domain pair as-is, else finite min/max; zero/non-finite span → zeros;
clip to `[0, 1]`) so Python `_item_fill_rgba8` and Node `itemFillRgba8`
cannot drift. Field picking and colormap lookup stay host.
ABI 248 `xyg_scene_finite_all` owns Scene finite-all admit (empty → `1`)
so Python `_xyep_finite` / heatmap XYEP and Node `exportColumnFinite`
cannot drift. Field picking stays host.
ABI 249 `xyg_scene_gradient_solid_css` owns Scene gradient solid CSS
(first packed RGBA8 stop with alpha `> 0` → `rgb(r,g,b)`; else
`rgb(0,0,0)`) so Python `_gradient_solid_css` and Node `gradientSolidCss`
cannot drift. Field picking stays host.
ABI 250 `xyg_scene_arrays_equal` owns Scene f64 arrays-equal (lengths
match and every pair is IEEE `==`; empty equal; NaN never equals) so
Python companion x1/y1 match and Node `exportArraysEqual` cannot drift.
Field picking and null checks stay host.
ABI 251 `xyg_clip_quantize_u8` owns unit-f64 clip-to-`[0, 1]` × 255
ties-to-even u8 quantize (NaN → 0) so Python `_quantized_rgba8` /
`channels.ship_color_channel` and Node `clipQuantizeU8` /
`resolveColorChannel` / `channelEndRgba8` cannot drift. Field picking
stays host.
ABI 252 `xyg_scene_constant_color_admit` owns Scene constant-color admit
(`0` fail, `1` style fallback, `2` channel constant) so Python
`_constant_color` and Node `constantMarkColor` cannot drift. Ribbon-fail
and field picking stay host.
ABI 253 `xyg_scene_hidden_or_per_item_admit` owns Scene hidden-or-per-item
admit (`hidden || (has_per_item && !density_aggregates)`) so Python
`_figure_trace_support_flags` and Node `figureTraceSupport` cannot drift.
Field picking stays host.
Python `colormap_lut_rgba8` and Node `colormapLutRgba8` sample 256
unit-t texels through ABI 206 `xyg_colormap_lut` then host-pack alpha
255 so the density LUT cannot drift on half-up vs ties-to-even.
Python `quantize_unit_u8` / `_quantized_lut_idx` and Node
`quantizeUnitU8` / `resolveDensityBinColors` normalize through
`xyg_normalize_f32` (nonfinite → 0) then ABI 251 `xyg_clip_quantize_u8`.
Equal or non-finite domain stays a host zero-span short-circuit.
Python `palette_rows_rgba8` quantizes `css_check` 0-1 channels through
ABI 251 `xyg_clip_quantize_u8`. Browser-only palette status and per-index
substitute stay host.
Python `_svg._paint_rgba8` resolves CSS paints through `xyg_css_color_rgba`,
matching `_raster._parse_color` and Node `cssColorRgba8`.
Python `resolved_hex_paint` / `_resolved_rgb` quantize `css_check` 0-1
channels through ABI 251 `xyg_clip_quantize_u8`. Browser-only rejection stays host.
Python `resolve_style_channel` admits finite arrays through ABI 248
`xyg_scene_finite_all`. Bounds checks stay host.
SVG `_rgb_css` formats 0-1 RGB through ABI 251 `xyg_clip_quantize_u8`.
SVG authored-scatter marker RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster scatter RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster mesh/hexbin fill RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster rectangle style RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster segment stroke RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster mesh stroke RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster ribbon fill RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Raster ribbon match-fill edge RGBA8 uses ABI 251 `xyg_clip_quantize_u8`.
Node `meshHasPerItem` uses `perItemChannelNames` (same as Python `has_per_item_channels`) for ABI 244.
Node `scatterPaintChannelNames` uses `perItemChannelNames` (same as Python `per_item_channel_names`) for ABI 241.
Node hexbin colormap-plane packing uses `channel.values` (same as Python); `trace.metric` is not a values fallback.
Node empty kind uses `|| "mark"` (same as Python `or "mark"`).
Node `figureTraceSupport` does not fail-close `style.smooth`; curve names stay ABI 233.
Node `itemWidths` fail-closes a present `stroke_width` channel without values (same as Python).
Node `itemApplyOpacity` fail-closes a present opacity/artist_alpha channel without values (same as Python).
Node missing scatter kind uses `|| ""` (same as Python); it is not defaulted to `"scatter"`.
Node `fillIsGradientAuthoring` rejects arrays (same as Python dict-only).
Node `rectExtraFlags` treats only mapping fills as gradient-fail (same as Python dict-only).
Node `admittedMarkerGlyph` rejects non-strings (same as Python `isinstance(..., str)`).
Node `packXyTaColormap` uses `style.colormap` only (same as Python); `trace.colormap` / `colormapStops` are not fallbacks.
Node hexbin XYTA colormap uses `channel.colormap` only (same as Python); `style.colormap` is not a fallback.
Node XYHF heatmap/density colormap uses `style.colormap` only (same as Python); `trace.colormap` / `colormapStops` are not fallbacks.
Node `constantMarkColor` uses `color_ch.constant` only (same as Python); string channels, `channel.color`, and `trace.color` are not fallbacks.
Node `channelConstantCss` uses `channel.constant` only (same as Python); string channels and `channel.color` are not fallbacks.
Node `channelEndRgba8` constant paint uses `channel.constant` only (same as Python); string channels and `channel.color` are not fallbacks.
Node `sourceColorCss` uses `color_ch` only (same as Python); `trace.color` is not a source-channel fallback.
Node `resolveColorChannel` constant CSS uses `.constant` (same as Python `ColorChannel`); `composeRibbon` writes `color_ch` / `color2_ch`.
Node `color2Channel` uses `color2_ch` only (same as Python); `color_target` / `colorTarget` are not Scene-pack fallbacks.
Node `itemFillRgba8` uses `color_ch` only (same as Python); `trace.color` is not a fill-channel fallback.
Node `scatterPaintChannelNames` uses `color_ch` only (same as Python); `trace.color` is not a per-item color channel.
Node `scatterHasNonConstantColor` uses `color_ch` only (same as Python); `trace.color` is not a non-constant-color fallback.
Node `resolveDensityBinColors` uses `color_ch` only (same as Python); `trace.color` is not a density-bin color channel.
Node `scatterHasNonConstantColor` ignores `style.color_channel` (same as Python); only `color_ch` is a non-constant-color channel.
Node `scatterPaintChannelNames` ignores `style.color_channel` / `stroke_channel` / `size_channel` (same as Python); per-item extras come from `style_channels`.
Node `resolveDensityBinColors` ignores `style.color_channel` (same as Python); only `color_ch` is a density-bin color channel.
Node XYMS mark color uses `style.color` only (same as Python `_constant_color` style fallback); `trace.color` is not a mark-color fallback.
Node XYTC style color uses `style.color` only (same as Python); `trace.color` is not a packed-color fallback.
Node XYTC constant paint uses `channel.constant` only (same as Python); `channel.color` is not a packed-constant fallback.
Node density-blit observation uses `scatterUsesDensity` (same as Python `use_density`); `style.color_channel` is not a per-item density extra.
Node XYTC color_ch packing ignores string channels (same as Python object-only); only a channel object packs COLOR_CH.
Node `scatterHasNonConstantColor` uses `channel.constant` only (same as Python); `channel.color` is not a packed-constant stand-in.
Node XYTC `COLOR_CH_CONSTANT` packs whenever `channel.constant` is set (same as Python); `mode === "constant"` is not a gate.
Node XYMS mark color uses `constantMarkColor` / ABI 252 (same as Python `_constant_color`); `style.color` is the code-1 fallback only.
Node `scatterPerItemChannels` ignores `style.color_channel` / `size_channel` / `stroke_channel` (same as Python `has_per_item_channels`); only `*_ch` presence counts.
Node `scatterPerItemChannels` is mode-based like Python `has_per_item_channels`; a constant `color_ch` is not per-item.
Node `channelEndRgba8` ignores array and typed-array channels (same as Python object-only); only `null` and mode objects pack.
Node `channelEndRgba8` categorical paint uses `DEFAULT_PALETTE` when palette is empty (same as Python); fallback CSS is not a missing-slot stand-in.
Node `packXyTaColormap` stop bytes require RGB rows like Python `_colormap_stop_bytes`; a flat or RGBA list packs empty stops.
Node `xyHfColormap` stop bytes require RGB rows like Python `_colormap_stop_bytes`; a flat or RGBA list packs empty stops.
Node `packXyTaRgbaGrid` stacks flattened planes like Python `_pack_xyta` `rgba_grid`; nested 2D index fallback is not a plane layout.
Node heatmap `trace.rgba` stores a flat uint8 buffer; `packXyTaRgba` packs that buffer like Python `_pack_xyta` and does not unwrap nested `.rgba`.
Node heatmap and density Scene packing is XYTA-only like Python `_pack_xyta`; unused XYHF paint-plane helpers are not a second plane layout.
Node `packXyTaGrid` flattens heatmap `grid` like Python `_pack_xyta` (`plane.values` or plane); nested length indexing is not a grid layout.
Node `rectFiniteSel` drops nonfinite rectangle rows through `validIndicesF64` like Python `_rect_finite_sel`; NaN never reaches vertex buffers (§19).
Node `packXyTa` density fill opacity uses `style.fill_opacity` only like Python `_pack_xyta`; `fillOpacity` is not a fill-opacity key.
Node XYTC fill opacity uses `style.fill_opacity` only like Python `_pack_xytc`; `fillOpacity` is not a fill-opacity key.
Node XYTC stroke opacity uses `style.stroke_opacity` only like Python `_pack_xytc`; `strokeOpacity` is not a stroke-opacity key.
Node XYTC line opacity uses `style.line_opacity` only like Python `_pack_xytc`; `lineOpacity` is not a line-opacity key.
Node XYTC stroke width uses `style.stroke_width` only like Python `_pack_xytc`; `strokeWidth` is not a stroke-width key.
Node XYTC line width uses `style.line_width` only like Python `_pack_xytc`; `lineWidth` is not a line-width key.
Node XYTC size uses `style.size` only like Python `_pack_xytc`; `diameter` is not a size key.
Node XYTC line color uses `style.line_color` only like Python `_pack_xytc`; `lineColor` is not a line-color key.
Node XYTC joined fill uses `style.joined_fill` only like Python `_pack_xytc`; `joinedFill` is not a joined-fill key.
Node XYTC stroke perimeter uses `style.stroke_perimeter` only like Python `_pack_xytc`; `strokePerimeter` is not a stroke-perimeter key.
Node XYTC COLOR_CH packing uses `color_ch` only like Python `_pack_xytc`; `colorChannel` is not a packed-channel fallback.
Node XYTC size_ch packing uses `size_ch` only like Python `_pack_xytc`; `sizeChannel` is not a packed-channel fallback.
Node XYEF stroke-width-only observation uses `style.stroke_width` only like Python; `strokeWidth` is not an observation key.
Node `meshJoinedFill` uses `style.joined_fill` only like Python `_mesh_joined_fill`; `joinedFill` is not a joined-fill key.
Node XYEF joined-fill observation uses `style.joined_fill` only like Python; `joinedFill` is not an observation key.
Node `constantMarkColor` uses `color_ch` only like Python `_constant_color`; `colorChannel` is not a source-channel fallback.
Node `sourceColorCss` uses `color_ch` only like Python `_trace_source_color_css`; `colorChannel` is not a source-css fallback.
Node `scatterHasNonConstantColor` uses `color_ch` only like Python; `colorChannel` is not a non-constant-color fallback.
Node `classifyRibbonColor2` source-constant CSS uses `color_ch` only like Python `_classify_ribbon_color2`; `colorChannel` is not a source-constant fallback.
Node `itemFillRgba8` uses `color_ch` only like Python `_item_fill_rgba8`; `colorChannel` is not a fill-channel fallback.
Node `resolveDensityBinColors` uses `color_ch` only like Python; `colorChannel` is not a density-bin color channel.
Node `hexbinPacksColormapPlane` uses `color_ch` only like Python `_hexbin_packs_colormap_plane`; `colorChannel` is not a colormap-plane fallback.
Node `ribbonEndRgbaPair` uses `color_ch` only like Python `_ribbon_end_rgba_pair`; `colorChannel` is not a ribbon-end source fallback.
Node `hexbinXyTaColormap` uses `color_ch` only like Python `_pack_xyta` hexbin colormap; `colorChannel` is not a colormap fallback.
Node `hexbinPacksRgbaPlane` uses `color_ch` only like Python `_hexbin_packs_rgba_plane`; `colorChannel` is not an RGBA-plane fallback.
Node `hexbinCellRgba8` uses `color_ch` only like Python `_hexbin_cell_rgba8`; `colorChannel` is not a cell-paint fallback.
Node XYTA density color_ch packing uses `color_ch` only like Python `_pack_xyta`; `colorChannel` is not a packed-constant fallback.
Node `itemStrokeRgba8` uses `stroke_ch` only like Python `_item_stroke_rgba8`; `strokeChannel` is not a stroke-channel fallback.
Node `scatterPointStrokeRgba8` uses `stroke_ch` only like Python `_scatter_point_stroke_rgba8`; `strokeChannel` is not a match-fill opacity skip.
Node `perItemChannelNames` uses `color_ch` / `stroke_ch` / `size_ch` / `style_channels` only like Python `per_item_channel_names`; camelCase channel fields are not per-item name fallbacks.
Node `itemApplyOpacity` uses `style_channels` only like Python `_item_apply_opacity`; `styleChannels` is not an opacity-channel fallback.
Node `itemWidths` uses `style_channels` only like Python `_item_widths`; `styleChannels` is not a width-channel fallback.
Node `scatterUsesDensity` uses `force_density` only like Python `use_density`; `forceDensity` is not a density-force fallback.
Node `figureTraceSupport` uses `style.linecap` only like Python `_figure_trace_support_flags`; `lineCap` is not a dashed-marker linecap fallback.
Node `packXyTcLinecap` uses `style.linecap` only like Python `_pack_xytc`; `lineCap` is not a packed-linecap fallback.
Node `packXyAfLinecap` uses `style.linecap` only like Python `_pack_xyaf`; `lineCap` is not an annotation-linecap fallback.
Node `scatterUsesDensity` does not pass `force_direct` like Python `use_density`; `forceDirect` / `force_direct` are not density-direct overrides.
Node hexbin XYTA values packing uses `color_ch` only like Python `_pack_xyta`; `colorChannel` is not a hexbin-grid values fallback.
Node `legendStyleFontSizes` uses `style.font_size` / `style.title_font_size` only like Python `_legend_input`; `fontSize` / `titleFontSize` are not legend-font fallbacks.
Node `heatmapGridShape` uses `grid_shape` only like Python `_heatmap_shape`; `gridShape` is not a heatmap-lattice fallback.
Node `hexbinStylePitch` uses `style.hex_dx` then `style.dx` like Python `_hexbin_pitch`; `hexDx` / `hexDy` are not hexbin-pitch fallbacks.
Node `polarGridShape` uses axis `grid_shape` only like Python `_pack_polar_scene_input`; `gridShape` is not a polar-grid fallback.
Node `polarAxisThetaUnit` uses axis `theta_unit` only like Python `_pack_polar_scene_input`; `thetaUnit` is not a polar-unit fallback.
Node `polarAxisThetaZero` uses axis `theta_zero` only like Python `_pack_polar_scene_input`; `thetaZero` is not a polar-zero fallback.
Node `polarAxisThetaDirection` uses axis `theta_direction` only like Python `_pack_polar_scene_input`; `thetaDirection` is not a polar-direction fallback. Node `polarAxisROrigin` uses axis `r_origin` only like Python `_pack_polar_scene_input`; `rOrigin` is not a polar-origin fallback. Node `axisTickValues` uses axis `tick_values` only like Python `_pack_figure_chrome`; `tickValues` is not a chrome-major-tick fallback. Node `axisMinorTickValues` uses axis `minor_tick_values` only like Python `_pack_figure_chrome`; `minorTickValues` is not a chrome-minor-tick fallback. Node `axisTickLabels` uses axis `tick_labels` only like Python `_pack_figure_chrome`; `tickLabels` is not a chrome-tick-label fallback. Node `figureXLabel` uses `x_label` then axis `label` like Python `_pack_figure_chrome`; `xLabel` is not a chrome-xlabel fallback. Node `figureYLabel` uses `y_label` then axis `label` like Python `_pack_figure_chrome`; `yLabel` is not a chrome-ylabel fallback. Node `plotTopAxisRoom` uses plot `top_axis_room` only like Python `recut_polar_plot`; `topAxisRoom` is not a polar-recut-room fallback. Node `axisTickLabelAnchor` uses axis `tick_label_anchor` only like Python `_scene_tick_anchor_code`; `tickLabelAnchor` is not a chrome-tick-anchor fallback. Node `axisTickLabelMinGap` uses axis `tick_label_min_gap` only like Python `_pack_tick_collision`; `tickLabelMinGap` is not a chrome-tick-gap fallback. Node `axisTickLabelAngle` uses axis `tick_label_angle` only like Python `_pack_tick_collision`; `tickLabelAngle` is not a chrome-tick-angle fallback. Node `axisTickLabelStrategy` uses `tick_label_strategy` then `collision` like Python `_scene_tick_label_strategy`; `tickLabelStrategy` is not a chrome-tick-strategy fallback. Node `polarCollisionKeys` uses snake-case keys only like Python `_POLAR_COLLISION_KEYS`; camelCase tick-label keys are not polar-collision-key extras. Node `figureChromeStyles` uses `chrome_styles` only like Python `_pack_figure_support`; `chromeStyles` is not a chrome-styles fallback. Node `chromeStyleHasFontFamily` uses `font-family` only like Python `_pack_figure_support`; `fontFamily` is not a chrome-font-family fallback. Node `figureClassName` uses `class_name` only like Python `_pack_figure_support`; `className` is not a figure-class-name fallback. Node `figureClassNames` uses `class_names` only like Python `_pack_figure_support`; `classNames` is not a figure-class-names fallback. Node `annotationClassName` uses `class_name` only like Python `_pack_figure_support`; `className` is not an annotation-class-name fallback. Node `figureExtraLegends` uses `extra_legends` only like Python `_pack_figure_support`; `extraLegends` is not an extra-legends fallback. Node `figureTitleOptions` uses `title_options` only like Python `_pack_public_export_support`; `titleOptions` is not a title-options fallback. Node `figureLegendOptions` uses `legend_options` only like Python `_legend_input`; `legend` is not a legend-options fallback. Node `figureColorbarOptions` uses `colorbar_options` only like Python `_colorbar_input`; `colorbarOptions` is not a colorbar-options fallback. Node `figureShowLegend` uses `show_legend` only like Python `_legend_input`; `showLegend` is not a show-legend fallback. Node `figureAxisOptions` uses `axis_options` only like Python `_pack_figure_chrome`; `xAxis` / `x_axis` are not axis-options fallbacks. Node `axisScaleName` uses axis `type` only like Python `_axis_scale`; `kind` is not an axis-scale fallback. Node `figureAutorangeAxisOptions` uses `axis_options` only like Python `_axis_scale`; `xAxis` is not an autorange-axis fallback. Node `_emitScatter` uses `force_density` only like Python `payload_force_density`; `style.force_density` is not a payload-density fallback. Node `_emitScatter` does not read `style.force_direct` like Python `_emit_scatter`; `style.force_direct` is not a payload-direct fallback. Node `_emitScatter` does not read `style.force_pyramid` like Python `_emit_scatter`; `style.force_pyramid` is not a payload-pyramid fallback. Node `_emitScatterDensity` does not read `style.force_bin2d` like Python `_density_trace_spec`; `style.force_bin2d` is not a payload-bin2d fallback. Node `_emitScatterDensity` does not read `style.no_rescan` like Python `_density_trace_spec`; `style.no_rescan` is not a payload-no-rescan fallback. Node `chromeAxisMinorStyle` uses `minor_style` only like Python `_pack_chrome_axis`; `minorStyle` is not a chrome-minor-style fallback. Node `chromeAxisTickSides` uses `tick_sides` only like Python `_pack_chrome_axis`; `tickSides` is not a chrome-tick-sides fallback. Node `chromeAxisTickLabelSides` uses `tick_label_sides` only like Python `_pack_chrome_axis`; `tickLabelSides` is not a chrome-tick-label-sides fallback. Node `chromeAxisStyleKeys` admits snake-case keys only like Python `_SCENE_AXIS_STYLE_KEYS`; camelCase axis style keys are not a chrome-axis-style-keys fallback. Node `chromeAxisStyleHas` / `chromeAxisStyleValue` read snake-case keys only like Python `_pack_chrome_axis`; camelCase fields are not a chrome-axis-style-read fallback. Node `legendAxisScale` uses axis `type` only like Python `_axis_scale`; `scale` / `kind` are not a legend-axis-scale fallback. Node `figureAutorangeAxisScale` uses axis `type` only like Python `_axis_scale`; `kind` is not an autorange-axis-scale fallback. Node `figureAxisKind` matches Python `_axis_kind` (forced `type` time, then category labels, then `time_ms` columns); axis `kind` is not an autorange-axis-kind fallback. Node `chromeAxisTickKind` uses `Figure._axisKind` like Python `_pack_figure_chrome` / `_pack_tick_collision`; axis `kind` is not a chrome-tick-kind fallback. Node `xyEfResolvedKind` uses `Figure._axisKind` like Python `_pack_public_export_support`; axis `kind` is not an xyef-axis-kind fallback. Node `figureAutorangeThetaUnit` uses axis `theta_unit` only like Python `_pack_autorange`; `thetaUnit` is not an autorange-theta-unit fallback. Node `figureAxisIsLog` uses axis `type` only like Python `_axis_scale` log; `scale` is not an axis-is-log fallback. Node `figureAutorangeCategories` uses `_axis_categories` only like Python `_pack_autorange`; `options.categories` is not an autorange-categories fallback. Node `figureAutorangeDomain` uses axis `domain` only like Python `_pack_autorange`; `_axisRange` is not an autorange-domain fallback. Node `setPolarMeta` writes axis `theta_unit` like Python `set_axis`; `_polarMeta.thetaUnit` is not a polar-meta-unit fallback. Node `setPolarMeta` writes axis `theta_zero` like Python `set_axis`; `_polarMeta.thetaZero` is not a polar-meta-zero fallback. Node `setPolarMeta` writes axis `theta_direction` like Python `set_axis`; `_polarMeta.thetaDirection` is not a polar-meta-direction fallback. Node `setPolarMeta` writes axis `grid_shape` like Python `set_axis`; `_polarMeta.gridShape` is not a polar-meta-grid fallback. Node `setPolarMeta` writes axis `hole` like Python `set_axis`; `_polarMeta.hole` is not a polar-meta-hole fallback. Node `setPolarMeta` writes axis `sector` like Python `set_axis`; `_polarMeta.sector` is not a polar-meta-sector fallback. Node `polarAxisHole` uses axis `hole` only like Python `_pack_polar_scene_input`; `Hole` is not a polar-hole fallback. Node `polarAxisSector` uses axis `sector` only like Python `_pack_polar_scene_input`; `Sector` is not a polar-sector fallback. Node `_polarAxisSpecs` uses axis `theta_unit` like Python `_axis_spec`; `_polarMeta.thetaUnit` is not a polar-spec-unit fallback. Node `_polarAxisSpecs` uses axis `theta_zero` like Python `_axis_spec`; `_polarMeta.thetaZero` is not a polar-spec-zero fallback. Node `_polarAxisSpecs` uses axis `theta_direction` like Python `_axis_spec`; `_polarMeta.thetaDirection` is not a polar-spec-direction fallback. Node `_polarAxisSpecs` uses axis `grid_shape` like Python `_axis_spec`; `_polarMeta.gridShape` is not a polar-spec-grid fallback. Node `_polarAxisSpecs` uses axis `sector` like Python `_axis_spec`; `_polarMeta.sector` is not a polar-spec-sector fallback. Node `_polarAxisSpecs` uses axis `hole` like Python `_axis_spec`; `_polarMeta.hole` is not a polar-spec-hole fallback. Node `_polarAxisSpecs` uses axis `r_origin` like Python `_axis_spec`; `_polarMeta.rOrigin` is not a polar-spec-origin fallback. Node `packPolarSceneInput` uses figure `_range("y")` like Python `_pack_polar_scene_input`; `rAxis.range` is not a polar-range fallback. Node `shouldUseDensity` maps Boolean `false` to auto (`-1`) unlike Python `payload_force_density` `False` to `0`; that Boolean vs tri-state mapping is a recorded density-tristate stay-host. Node `_emitScatter` still passes `forceDirect` into `shouldUseDensity` unlike Python `_emit_scatter`; that payload force-direct mapping is a recorded emit-force-direct stay-host. Node `_emitScatter` still ORs `forcePyramid` into `shouldUseDensity` unlike Python `_emit_scatter`; that payload force-pyramid mapping is a recorded emit-force-pyramid stay-host. Node `_emitScatterDensity` colormap uses `style.colormap` unlike Python `_density_trace_spec` `color_ch.colormap`; that payload density colormap mapping is a recorded density-colormap stay-host. Node `_emitScatterDensity` colorMode uses `style.color` unlike Python `_density_trace_spec` `color_ch`; that payload density colorMode mapping is a recorded density-colormode stay-host. Node `sourceColorCss` keeps empty `style.color` unlike Python `_trace_source_color_css` `or` default; that empty-string mapping is a recorded source-css-empty stay-host. Node `figureXLabel` keeps empty `x_label` unlike Python `_pack_figure_chrome` `or` fallthrough; that empty-string mapping is a recorded xlabel-empty stay-host. Node `figureYLabel` keeps empty `y_label` unlike Python `_pack_figure_chrome` `or` fallthrough; that empty-string mapping is a recorded ylabel-empty stay-host. Node `packChromeAxis` skips null-valued unsupported keys unlike Python `_pack_chrome_axis` set-difference; that null-key mapping is a recorded chrome-null-key stay-host. Node `itemFillRgba8` fallback stays `sourceColorCss` unlike Python `_item_fill_rgba8` style.get; that fallback mapping is a recorded item-fill-css stay-host. Node `hexbinCellRgba8` fallback stays `sourceColorCss` unlike Python `_hexbin_cell_rgba8` style.get; that fallback mapping is a recorded hexbin-css stay-host. Node `itemStrokeRgba8` empty style.stroke stays unlike Python `_item_stroke_rgba8` or-default; that empty-string mapping is a recorded item-stroke-empty stay-host. Node `_polarAxisSpecs` empty theta_unit stays unlike Python `_axis_spec` or-default; that empty-string mapping is a recorded polar-payload-unit-empty stay-host. Node `_polarAxisSpecs` empty theta_direction stays unlike Python `_axis_spec` or-default; that empty-string mapping is a recorded polar-payload-dir-empty stay-host. Node `_polarAxisSpecs` empty grid_shape stays unlike Python `_axis_spec` or-default; that empty-string mapping is a recorded polar-payload-grid-empty stay-host. Node `_polarAxisSpecs` empty hole stays unlike Python `_axis_spec` or-default; that empty-string mapping is a recorded polar-payload-hole-empty stay-host. Node `_polarAxisSpecs` empty sector stays unlike Python `_axis_spec` or-default; that empty-list mapping is a recorded polar-payload-sector-empty stay-host. Node `scatter()` stores f64 not `Column.kind` unlike Python time_ms columns; that authoring mapping is a recorded scatter-f64-kind stay-host. Node `_emitHexbin` ships `metric` unlike Python `_emit_hexbin` `color_ch`; that payload hexbin metric mapping is a recorded hexbin-metric stay-host. Node `_emitHeatmap` ships grid columns unlike Python `_emit_heatmap` nested heatmap; that payload heatmap grid mapping is a recorded heatmap-grid stay-host. Node `_emitScatter` ships `t.color` unlike Python `_emit_scatter` `color_ch`; that payload scatter color mapping is a recorded scatter-ship-color stay-host. Node `_emitRibbon` ships `t.color_target` unlike Python `_emit_ribbon` `color2_ch`; that payload ribbon color-target mapping is a recorded ribbon-color-target stay-host. Node `_emitRibbon` ships `t.color` unlike Python `_emit_ribbon` `color_ch`; that payload ribbon color mapping is a recorded ribbon-ship-color stay-host. Node `_emitRect` omits `color_ch` unlike Python `_emit_rect`; that payload rect color mapping is a recorded emit-rect-color stay-host. Node `_emitSegments` ships `t.color` unlike Python `_emit_segments` color_ch; that payload segments color mapping is a recorded emit-segments-color stay-host. Node `_emitTriangleMesh` omits `color_ch` unlike Python `_emit_triangle_mesh`; that payload mesh color mapping is a recorded emit-mesh-color stay-host. Node `_emitHistogram` omits `color_ch` unlike Python `_emit_histogram`; that payload histogram color mapping is a recorded emit-hist-color stay-host. Node `_emitTriangleMesh` ships `x`/`y` unlike Python `x2`/`y2`; that payload mesh vertex mapping is a recorded emit-mesh-xy stay-host. Node `_emitScatter` omits `stroke_ch` unlike Python `_ship_trace_styles`; that payload scatter stroke mapping is a recorded emit-scatter-stroke stay-host. Node `_emitRibbon` omits `stroke_ch` unlike Python `_ship_trace_styles`; that payload ribbon stroke mapping is a recorded emit-ribbon-stroke stay-host. Node `_emitRect` omits `stroke_ch` unlike Python `_ship_trace_styles`; that payload rect stroke mapping is a recorded emit-rect-stroke stay-host. Node `_emitTriangleMesh` omits `stroke_ch` unlike Python `_ship_trace_styles`; that payload mesh stroke mapping is a recorded emit-mesh-stroke stay-host. Node `_emitSegments` omits `stroke_ch` unlike Python `_ship_trace_styles`; that payload segments stroke mapping is a recorded emit-segments-stroke stay-host. Node `_emitHistogram` omits `stroke_ch` unlike Python `_ship_trace_styles`; that payload histogram stroke mapping is a recorded emit-hist-stroke stay-host. Node `_emitScatter` omits `style_channels` unlike Python `_ship_trace_styles`; that payload scatter channels mapping is a recorded emit-scatter-channels stay-host. Node `_emitRibbon` omits `style_channels` unlike Python `_ship_trace_styles`; that payload ribbon channels mapping is a recorded emit-ribbon-channels stay-host. Node `_emitRect` omits `style_channels` unlike Python `_ship_trace_styles`; that payload rect channels mapping is a recorded emit-rect-channels stay-host. Node `_emitTriangleMesh` omits `style_channels` unlike Python `_ship_trace_styles`; that payload mesh channels mapping is a recorded emit-mesh-channels stay-host. Node `_emitSegments` omits `style_channels` unlike Python `_ship_trace_styles`; that payload segments channels mapping is a recorded emit-segments-channels stay-host. Node `_emitHistogram` omits `style_channels` unlike Python `_ship_trace_styles`; that payload histogram channels mapping is a recorded emit-hist-channels stay-host. Node `_emitScatter` omits `transition_keys` unlike Python `_transition_entry`; that payload scatter transition mapping is a recorded emit-scatter-transition stay-host. Node `_emitLine` omits `transition_keys` unlike Python `_transition_entry`; that payload line transition mapping is a recorded emit-line-transition stay-host. Node `_emitArea` omits `transition_keys` unlike Python `_transition_entry`; that payload area transition mapping is a recorded emit-area-transition stay-host. Node `_emitHistogram` skips `rectFiniteSel` unlike Python `_emit_rect`; that payload histogram finite-sel mapping is a recorded emit-hist-finite-sel stay-host. Node `_emitRect` ships bar columns unlike Python nested `bar`; that payload bar compact mapping is a recorded emit-bar-compact stay-host. Node `_emitRibbon` skips `valid_indices_f64` unlike Python `_emit_ribbon`; that payload ribbon gather mapping is a recorded emit-ribbon-gather stay-host. Node `_emitTriangleMesh` skips `valid_indices_f64` unlike Python `_emit_triangle_mesh`; that payload mesh gather mapping is a recorded emit-mesh-gather stay-host. Node `_emitRect` omits `transition_keys` unlike Python `_transition_entry`; that payload rect transition mapping is a recorded emit-rect-transition stay-host. Node `_emitRibbon` omits `transition_keys` unlike Python `_transition_entry`; that payload ribbon transition mapping is a recorded emit-ribbon-transition stay-host. Node `_emitTriangleMesh` omits `transition_keys` unlike Python `_transition_entry`; that payload mesh transition mapping is a recorded emit-mesh-transition stay-host.
ABI 133 compiles polar Scene v26 line/scatter/area/bar/column/errorbar/heatmap: hosts pack XYPL v1
authoring; Rust owns `polar_layout`, `polar_project`, `polar_wedge_points`, clip, rings/spokes, and
rim tick-label placement. Polar heatmap constant-style lattices use the same
Rect tessellation; ABI 192 polar painted heatmap inverse-rasters to one Image.
Cartesian Scene bytes change only the version u32.
ABI 110 moves primary Scene legend framing into Rust. Hosts pass loc/flags,
font sizes, paints, title, and per-entry meta plus labels; XYLG header
layout, text offsets, and bounded-text rejection are engine-owned and
identical for Python and Node.
ABI 111 moves primary Scene colorbar framing into Rust. Hosts pass domain,
stops, ticks, title, and text RGBA; XYCB v2 header layout, stop/tick
tables, domain-span checks, and bounded-text rejection are engine-owned
and identical for Python and Node.
ABI 112 moves primary Scene annotation framing into Rust. Hosts pass typed
row meta plus concatenated labels; XYAT/XYAL/XYAR/XYAC/XYAW table layout,
version selection, the XYAD envelope, and bounded-text rejection are
engine-owned and identical for Python and Node.
ABI 113 moves closed-subset SVG→PDF into Rust. Hosts pass UTF-8 SVG;
path lowering, Helvetica metrics, ExtGState/shading/image embedding, and
deterministic object numbering are engine-owned and identical for Python
and Node.
ABI 114 moves baseline JPEG and lossless WebP encode into Rust. Hosts
pass packed RGB/RGBA8 pixels; YCbCr 4:4:4, Annex K tables, the libjpeg
quality curve, VP8L simple-lossless packing, and Huffman/prefix codes are
engine-owned and identical for Python and Node.
ABI 115 moves filter-0 PNG encode into Rust. Hosts pass packed RGB/RGBA8
pixels plus mode/compression; indexed-palette selection, `tRNS`, and zlib
IDAT are engine-owned and identical for Python and Node.
Constant-style Cartesian heatmap compiles a regular rows x cols lattice onto
existing Scene Rect records; polar Scene tessellates those Rects to PolyFill
annular sectors. ABI 134 `HeatmapPainted` moves scalar colormap and truecolor
tessellation plus style intern into Rust: hosts pack an XYHP plane, Rust emits
per-cell literal Rect fills. ABI 135 named colormap tables live in Rust
(`xyg_colormap_stops`, XYHP paint kind 2). ABI 136 product-kind packing
(`xyg_scene_resolve_pack_kind` / `xyg_scene_pack_product`) maps authored
kinds onto compact pack kinds so hosts no longer dispatch pack-kind locally.
ABI 137 / Scene v27 compiles Cartesian constant-style density scatter as one
Image blit (`DensityBlit` + XYHP kind 3 + XYIM) instead of a Rect lattice.
ABI 138 / Scene v28 compiles constant dash
polylines as an XYDS sidecar (raw XYDS extras or XYEX v2) so SVG/raster emit
`stroke-dasharray`. ABI 139 / Scene v29 compiles constant non-round linecaps as
an XYLC sidecar (raw XYLC, XYDS+XYLC concat, or XYEX v2) so SVG/raster emit
`stroke-linecap`. ABI 140 / Scene v30 compiles cartesian `curve="smooth"`
polylines as denser Scene polylines (`CurveFlatten=11`); ABI 141 / Scene v31
compiles cartesian `area(curve="smooth")` as denser Scene Bands
(`BandFlatten=12`). ABI 142 compiles cartesian mean-color density as XYHP
kind 4 on the existing `DensityBlit` Image blit. ABI 143 polar density
tessellates occupied `DensityBlit` cells to PolyFill wedges (no XYIM). ABI 144
admits cartesian `error_band(curve="smooth")` on existing `BandFlatten=12` and
polar `curve="smooth"` line/area/error_band as identity chords (polar-axes.md
§5). ABI 145 admits constant scatter `marker_path` via an XYMP extras sidecar
tessellated to PolyFill/Polyline after pixel mapping. ABI 146 admits constant
mark `fill` linear-gradients via an XYGR extras sidecar kept on encoded Scene.
ABI 147 owns product packing facts from packed XYPK v1. ABI 148 owns
annotation family routing from packed XYAF v1. ABI 149 owns heatmap/density
XYHP kind routing from packed XYHF v1. ABI 150 owns style-sidecar layout and
extras wrapping from packed XYSS v1. ABI 151 owns Scene density binning and
log-u8 encoding from packed columns. ABI 152 owns XYEP layout,
kind/step/annotation codes, and flag derivation from packed XYEF v1.
ABI 153 owns plot layout, chrome-style resolve, legend loc default/allowlists
(empty authored loc is fail-closed, not the upper-right default), colorbar
flags/framing, XYTL tick-label framing, and the 200-tick axis bound from packed
XYCF v1. Layout errors stay plot-layout diagnostics so the public-export
predicate can remap them to `XYG_SCENE_UNSUPPORTED_VIEWPORT`.
ABI 154 owns per-trace Scene compile policy from packed XYTC v1.
ABI 155 owns heatmap/density attach policy from packed XYTO plus XYTA v1.
ABI 156 owns XYPK construction, scatter-only symbol/diameter, density
domain-endpoint column rewrite, and `pack_product_facts` from packed XYTT
plus XYCL v1.
ABI 157 owns legend-name gating, heatmap-vs-density plane selection, and
per-trace style/dash/marker/gradient/plane extraction from packed XYTT plus
XYNM v1.
ABI 158 owns XYSS dash/linecap/marker/gradient record construction from
packed XYSD plus XYAO v1.
ABI 159 owns annotation style/row splice and XYAD extract from packed
product rows plus XYSD plus XYAO v1.
ABI 160 owns assembled Scene encode from packed XYAS plus XYCC plus extras.
ABI 161 owns legend paints and XYHP wrapping from packed XYSD.
ABI 162 owns XYCC packing, extras packing, and viewport/axis scalars from
packed XYAS plus XYCF plus XYSD plus polar plus XYSS.
ABI 163 owns product-path compile, attach, sidecar, row, annotation,
style-sidecar, splice, and assembled encode from packed XYTC plus XYTA plus
XYNM plus XYCL plus XYAF plus XYCF plus polar.
ABI 164 owns public SVG/PNG/PDF/JPEG/WebP consumers from one encoded Scene.
ABI 165 owns the figure-compile support probe from packed XYFS on product encode.
ABI 166 tessellates cartesian bar/column/histogram `corner_radius` after pixel
mapping. ABI 167 applies polar bar/column/histogram `wedge_gap` as a constant
pixel inset during `polar_wedge_points`. ABI 168 tessellates polar
bar/column/histogram `corner_radius` when the inner radius is positive.
ABI 169 admits polar `curve="smooth"` plus `step` as polar step expansion.
ABI 170 admits constant scatter `marker_glyph` via an XYMG extras sidecar
kept on the encoded Scene. ABI 191 admits multi-character UTF-8 (XYMG v2).
ABI 192 admits polar painted heatmap inverse-raster as one Scene Image blit.
Combined `marker_path` + `marker_glyph` stays fail-closed. ABI 171 admits scatter
`stroke_width` without an authored `stroke` as match-fill. ABI 172 admits
cartesian line `curve="smooth"` plus `step` as authored step expansion.
ABI 173 tessellates heatmap `corner_radius` (cartesian rounded Rects / polar
wedges). ABI 174 tessellates violin/box `corner_radius` on that same Rect
path. ABI 175 admits violin/box `fill_opacity` / `stroke_opacity` on XYMS.
ABI 176 admits bar/column/histogram `fill_opacity` / `stroke_opacity` on that
same path. ABI 177 admits heatmap `fill_opacity` on XYMS fill alpha.
ABI 178 admits scatter `fill_opacity` / `stroke_opacity` on that same path.
ABI 179 admits hexbin `fill_opacity` on XYMS fill alpha.
ABI 193 admits heatmap/hexbin `stroke` / `stroke_width` / `stroke_opacity` on that
same path. Polar painted Image blit tessellates when stroke is visible.
ABI 194 admits polar hexbin, custom host reducers, and categorical / `direct_rgba`
hexbin on HexCell PolyFills.
ABI 180 admits triangle_mesh `fill_opacity` / constant stroke paint on that same
path. ABI 195 admits custom `role` and per-item fill/stroke/width interned onto
those TriangleFace PolyFills from packed XYHP kind 6 (`joined_fill` plus per-face
paint stays fail-closed). ABI 196 intern scatter per-item fill/stroke/width/opacity
from packed XYHP kind 7 (per-item size/symbol stay fail-closed). ABI 181 admits cartesian area/error_band `curve="smooth"` plus `step` as
authored band step expansion (`step_mode` 1–3 wins over `BandFlatten`).
ABI 182 admits triangle_mesh `joined_fill` as one identity PolyFill ring from
the Rust boundary walk (disconnected meshes keep per-face `TriangleFace` rows).
ABI 183 admits constant ribbon `color2_ch` as XYGR mark-space `dir=right`
(hosts pack the two-stop fill, not `FLAG_COLOR2`). ABI 190 intern per-item
two-ended paint from packed XYHP kind 5. Polar ribbon and explicit `FLAG_COLOR2`
stay fail-closed. ABI 184 admits cartesian unwrapped text `dx`/`dy`/`anchor`
as XYAW `wrap=0`. ABI 185 admits labelled cartesian marker `dx`/`dy`/`anchor`
as XYAW `wrap=0`. ABI 186 admits cartesian colormap hexbin as a 1×N XYHP plane
interned onto HexCell PolyFills. ABI 194 admits polar hexbin, custom reducers,
and categorical / `direct_rgba` hexbin on that same HexCell intern. ABI 195 admits triangle-mesh custom `role` and per-item fill/stroke/width interned from packed XYHP kind 6. ABI 196 intern scatter per-item fill/stroke/width/opacity from packed XYHP kind 7. ABI 187 admits cartesian unwrapped text `rotation` as
XYAW `wrap=0`. ABI 188 admits labelled cartesian marker `rotation` as XYAW
`wrap=0`. ABI 189 owns heatmap/hexbin cell-fill tessellation eligibility from
packed XYTA. ABI 190 intern cartesian per-item two-ended ribbon `color2_ch`
from packed XYHP kind 5. Annotation `html` stays fail-closed
(`XYG_SCENE_UNSUPPORTED_ANNOTATION_HTML`). Annotation `class_name` stays
fail-closed as `XYG_SCENE_UNSUPPORTED_BROWSER_CSS` (#306). Annotation
`collision` stays fail-closed as `XYG_SCENE_UNSUPPORTED_ANNOTATION_COLLISION`
(#307). Annotation `markup` stays fail-closed as
`XYG_SCENE_UNSUPPORTED_ANNOTATION_MARKUP` (#308). Annotation custom
typography stays fail-closed as `XYG_SCENE_UNSUPPORTED_CUSTOM_FONT` (#309).
Text/marker `style.rotation` lifts onto the ABI 187/188 rotation field.
Polar stays
fail-closed. Per-item radius
channels stay compatibility. Irregular
spacing, and LOD stay compatibility.

Contract-wide invariants: every tier transition is hysteresis-guarded and logged
(no silent quality change); every aggregated visual states its aggregation in the
hover UI; every derived artifact is reproducible from (canonical, viewport, params) —
which is what makes both the §21 determinism tests and the §27 eviction rules valid.

**Nonlinear axes bin in scale coordinates.** Screen-uniform aggregation is the
point of every reduction above, and on a log/symlog axis "uniform on screen"
means uniform in the axis's scale coordinates, not in raw data. Concretely:

- **Density grids** (first paint and `density_view` re-bins) transform values
  and window bounds through the axis coordinate map (`Figure._axis_coord_fn`)
  before `bin_2d`; the wire keeps raw `x_range`/`y_range` endpoints and the
  rule "cells are uniform in scale coordinates" (wire-protocol.md §3). Without
  this, clusters at x=1 and x=1000 share one cell on a symlog axis despite
  being a third of the screen apart. The count-only drill handoff's per-point
  `local_log_density` bins in the same space so its count-alpha matches the
  grid's (mean-color surfaces need no handoff at all — they composite like
  the points themselves, LOD doc §2 rules 1/5).
- **The raw-space tile pyramid** (Tier 3) cannot compose a scale-coordinate
  grid, so traces on a nonlinear axis skip pyramid build/compose and always
  take the exact scan (`binning: "exact"`). Cost: the O(visible) rescan the
  pyramid would have skipped — accepted, recorded here. The exclusion covers
  the Phase-4 disk tile store too (§32b): no pyramid is built, so nothing
  spills — a nonlinear-axis trace never engages tile residency.
- **M4 line decimation** buckets on transformed x (first paint and
  `decimate_view`) so each bucket is one screen column; the selected rows ship
  raw. Monotone y transforms preserve per-bucket argmin/argmax, so y never
  transforms.
- **Hexbin** stays data-uniform by design — its cells are explicit data-space
  geometry whose vertices transform individually, so cells *render* warped
  and merely have data-dependent screen sizes, like matplotlib's.
- **Static exports**: density images are scale-coordinate-uniform and stretch
  linearly between transformed endpoints (exact); heatmap grids are
  *data*-uniform, so SVG/PNG resample them per pixel through the inverse
  transform (`_svg.warp_axis_indices`) and the WebGL heatmap shader inverts
  per fragment (`HEATMAP_FS`) — otherwise internal cell edges land on a
  linear stretch between the endpoints.

## 29. Transport Matrix — copies, format, and fallback per environment

The unit being counted: **physical copies of the data payload after it leaves the
user's data structure**, and whether any step re-encodes.

| Path | Transport | Copies (min/typical) | Re-encode? | Fallback / notes |
|---|---|---|---|---|
| **Pure JS live paint / interaction** | Rust-produced offset f32/u8 typed arrays → transferable painter buffer | **0–1** / 1 (transfer = move; upload may copy into GPU storage) | never | this is the live §29 paint/data wire; TypeScript does not narrow or re-encode values |
| **Pure JS canonical authoring → Rust/WASM compile** | exact f64 source columns in versioned `XYTS` → transferable main-thread-to-Worker handoff → bounded WASM arena | **1** / 1 with ownership transfer (JS→WASM is one bounded `memcpy`); preserve mode adds one structured-clone copy | **once, in Rust only:** canonical f64 → offset painter f32/u8 | `XYTS` is compile ingress, not the live paint wire or an `XYBF` envelope; ordinary JS buffers cannot alias wasm32 memory; Rust validates before lowering; SAB is optional where isolated (§8) |
| **Python (Polars / Arrow-pandas), native render** | in-process Arrow | **0** / 0 | none | — |
| **Python (NumPy-pandas), native render** | NumPy → Arrow | **0–1** / 1 (numeric can alias; strings copy) | dictionary-encode strings once | conversion cost reported at ingest |
| **Jupyter kernel → browser** | xy's GPU-ready column blob over **binary** anywidget comm frames | **2** / 3 (payload assembly; socket transit; JS ArrayBuffer landing) | **never** — the compact f32/u8 blob lands as typed views; base64/JSON is forbidden on the live path | old frontends without binary comms: explicit unsupported/error rather than silently changing the performance contract |
| **Server app (Dash-style / Reflex)** | versioned `XYBF` frame over binary HTTP/WebSocket; strict JSON metadata + aligned raw buffers | 1–2 / 2–3 depending on server scatter/gather support; JS decode returns spans into `Response.arrayBuffer()` | never | control requests stay small JSON; SSE carries invalidations only; HTTP range requests into Parquet/Arrow files remain a Tier-3 option |
| **Static HTML export (interactive)** | xy blob base64-embedded in the one-file artifact | 1 decode + stated 33% text expansion | base64, because HTML is a text container | size warning above threshold; offer aggregate-only embed (ship pyramid, not points) |
| **Native static export** | in-process | 0 | none | — |

Design consequences: (a) the live numerical paint payload **is** the browser upload
format — offset f32/u8 columns with no per-value transformation, while `XYBF` only
supplies a bounded/versioned envelope; canonical authoring ingress such as `XYTS` is
distinct and may carry exact f64 source columns only as far as Rust compile, where
Rust alone lowers them to that painter format; (b) the copies that do happen are
`memcpy`-shaped, never
number-parse-shaped; (c) every binding reports its actual copy count at ingest in debug
mode, so "zero-copy" regressions are observable rather than folklore; (d) the Jupyter
live path still has no text encoding of numbers, DOM payload, or main-thread data parse.

## 30. Compatibility subset — v1 is a list, not an aspiration

Full Plotly semantics (~40 trace types × transforms × axis quirks × hover rules) is a
multi-year tail. The shim (§24) ships against an explicit, benchmarked v1 surface —
chosen to cover the high-volume traces where this engine's advantage exists, because
compat effort on a 200-point pie chart buys nothing:

- **Traces:** `scatter`/`scattergl` (markers, lines, both; `fill` for area),
  `bar`, `histogram`, `heatmap`, `box`, `candlestick`/`ohlc`.
- **Layout:** cartesian axes (linear/log/date/category), 2-D subplot grids +
  shared/linked axes, legend (toggle behavior included), title/margins/annotations
  (text + arrow only).
- **Interaction:** default hover (`closest`/`x` modes), zoom/pan/box-select/lasso,
  `Plotly.react`-equivalent diff update, relayout/restyle events.
- **Explicitly out of v1** (warn, don't silently drop — §24): 3-D, geo/mapbox,
  ternary/polar/carpet, sankey/sunburst/treemap, animation frames, legacy
  `transforms`, custom `hovertemplate` beyond basic field substitution.

Everything in the v1 list runs in the conformance suite from Phase 5 §25, and — the
actual point — **each is benchmarked at 100×–1000× Plotly's comfortable data volume.**
The subset is the moat *plus* the differentiator; breadth beyond it arrives via the
plugin API (§24) and demand, not via a compat death-march.

## 31. Revised one-paragraph summary (supersedes §14 where they differ)

The engine's claims are now **mode-scoped**: zero-copy *in process*, one binary
never-re-encoded transfer *across* processes (§29); 12–24 bytes/point in direct modes
and screen-bounded *resident* memory in aggregated/tiled modes (§2, §27); aggregation
that costs O(points) once, O(visible tiles) per frame, O(visible points) only past the
pyramid floor (§5); a CPU/server canonical store with the GPU strictly as a
byte-budgeted cache (§27); per-trace-kind LOD rules with defined hover semantics at
every tier (§28); and a named v1 compatibility surface (§30). Nothing universal, and
therefore nothing that only survives on the happy path — every number has a mode, a
budget, and a test.

---
---

# Part IV — Third audit round: the two missing workstreams

*Audit round 3 (post-research, post-Python-only decision) found that the plan's core
thesis survives but two Critical findings are missing **workstreams**, not tweaks:
distribution (F1) and filtering (F2). A third Major finding (F3 — real GPU ceilings)
is corrected in place in §5. This part adds the two sections and records the
scope decision that reshapes them.*

## 32. Kernel-owned compute: the architecture consequence (originally "Python-only")

The original binding decision was **Python only** (R/Julia/JS bindings dropped).
The current product has thin Python and Node hosts over one C ABI, and the #59
foundation adds bounded direct-browser execution by compiling the same engine
rather than reimplementing it in JavaScript. This is not just less code — it
relocates the heavy tiers:

- **The native Rust core runs inside the Python process**, ingesting zero-copy from
  Polars/Arrow-backed pandas. Decimation (Tier 1), pyramid builds (Tier 2), Tier-3
  paging, and the filter index (§34) all run **natively, in-process, at full speed** —
  SIMD, real threads, mmap, no WASM caps, no 4 GB ceiling.
- **The browser side shrinks to a render client**: a thin WASM/JS module that receives
  screen-bounded aggregates/decimations/tiles over the comm channel, composes them on
  the GPU, and handles local pan/zoom against its resident tile cache. It re-requests
  from the kernel only when navigation crosses the pyramid floor or a filter changes.
- The **in-browser WASM core** supports bounded #59 direct-browser paths where
  the data already lives client-side. Aggregate production beyond the current
  density/Scene vertical is tracked by the post-M2 follow-up **Expand direct-browser aggregate production beyond the density/Scene vertical** (related to [#54](https://github.com/CurateLabs/xyg/issues/54)); the WASM core
  is not the primary path. The primary path is
  **native-compute-where-the-data-lives → ship pixels-worth → thin GPU client**, the
  same shape the research validated in datashader/vaex, except pan/zoom stays local
  instead of round-tripping (this is exactly the VegaFusion DAG-partition idea: heavy
  nodes native, leaf render nodes in the browser).

*Amendment (Phase 3, ABI 58):* "Python-only" was a decision about not
**reimplementing the engine** per language; it was never a cap on thin loaders
over the one cdylib. The Node host (`packages/xy-node` / `@curatelabs/xyg-node`,
koffi over the same `libxyg_core` C ABI) has since shipped and productized the
Phase-3 pyramid (`packages/xy-node/src/pyramid.js` binds every `xyg_pyramid_*`
entry point), so
this section's consequences now read "host process" where they said "Python
process": the kernel owns decimation/pyramids/paging/filtering in whichever
host process holds the data and hosts stay thin. Native-host browser sessions
remain render-client-only; supported direct-browser sessions use the #59
foundation to execute the same engine in a Worker and feed the same painter.
Host obligations and parity status are governed by
`spec/design/host-parity.md` and `spec/design/dual-host-parity.json`.

## 32b. Tier-3 out-of-core companions — spatial bucketing and budgeted tile residency

The §28 scatter row promises two things past the in-RAM pyramid: a "spatial
bucketing pass at ingest for Tiers 2–3" and "re-bin visible via tile index"
below the pyramid floor. This section names the structures that keep those
promises. Both are §27 derived, rebuildable caches over the canonical f64
columns — droppable at any time, never a second source of truth.

**Spatial bucketing (shipped — the deep-zoom companion).** Points are
pre-sorted into a row-major data-space cell grid with a cumulative-offset
header (built by `osmium-rs`'s `osm-sort`); `xyg._spatial.SpatialIndex` reads
only the cells a viewport overlaps — one contiguous memmap slice per grid row,
O(points in window). It serves the zoomed-*in* regime where the pyramid's
finest cell is blocky: crisp real points under the drill threshold, else an
exact full-screen-resolution grid. Position-only (no row ids, no channels), so
it is gated to constant-styled traces and picks resolve exact-or-nothing.
Mechanics and tier gating: LOD architecture doc §4.4.

**Budgeted tile residency (Phase 4 — decisions locked WP0 #7; WP1 kernel landed ABI 73).**
When a pyramid no longer fits in RAM (adaptive 16 384² bases cost ~1.4 GB of
counts + ~2.9 GB of color; multi-trace apps multiply that), it spills to a
disk tile store the kernel owns. The locked frame — full rationale in
`spec/design/tier3-phase4-roadmap.md` "Locked decisions (WP0)":

- **Tile key & format:** `(level, tx, ty)` addressing over fixed 256²-cell
  mmap slabs in one spill file per pyramid (magic + version header; count
  region then optional color region; arithmetic O(1) slab offsets; native
  endianness). The file is a per-process cache, never an interchange format —
  a version bump can swap in Arrow/Parquet later with zero migration burden,
  because spill files are always discardable and rebuilt (§27).
- **Budget knob:** `PYRAMID_RESIDENT_BYTES` (default 512 MiB, process-wide
  across all pyramids) in `python/xyg/config.py` and the Node constants.
  Accounting follows §27 rule 5's precedent: `pyramid_report_bytes` (the
  `memory_report()["pyramid_bytes"]` line) covers **all** RAM-resident tile
  bytes plus tile-directory metadata; on-disk bytes report separately as
  `pyramid_spilled_bytes` (disk-backed, reclaimable) — if a byte isn't in the
  report, it isn't real.
- **Eviction:** kernel-side LRU over whole tiles (count + color planes evict
  together). The ≤ ceil(w/256+1) × ceil(h/256+1) tiles serving the current
  compose are pinned for the call and left most-recently-used; a frame never
  fails for budget reasons — if the pinned working set alone exceeds the
  budget, the effective budget floors at the working set and the reply records
  the over-budget condition (§28), then eviction returns residency to budget.
- **Append:** count-only pyramids dirty-mark intersecting tiles per level and
  rebuild them lazily (composed result equals a from-scratch rebuild); colored
  pyramids keep refuse-and-rebuild; domain growth invalidates the whole store
  (a grown domain re-keys every tile — partial reuse is impossible).
- **Tile index:** dirty-tile rebuilds and below-floor re-bins locate rows via
  the existing §22 chunk zone maps (`xy_zone_maps_pair` min/max prunes
  candidate chunks per tile rect) — no new ingest sort. Where a
  `SpatialIndex` exists it is the finer row locator; companion, not
  replacement.
- **Filters (§34):** the store holds **unfiltered** aggregates only; a trace
  with any active predicate bypasses compose-from-tiles entirely (the exact
  re-bin path serves, `-masked`), and filtered results are never written to
  the store — staleness from disk is impossible by construction, not by
  invalidation bookkeeping.
- **Nonlinear axes:** log/symlog traces skip the pyramid (§28), so there is
  nothing to spill — the exclusion extends to the tile store unchanged.

## 33. Distribution — shipping the bits is a first-class workstream (F1)

**`pip install` is the Python front door; `npm install @curatelabs/xyg` is the
JS/Node front door.** They must not collapse into each other. Python exists
only when the user is using Python. Embedding the paint client in the Python
wheel for notebooks / `to_html()` / Reflex is required and stays — that copy
is how Python users stay Node-free. The bug is treating `python/xyg/static` as
the *only* ship vehicle for JS users.

For a Python user, `pip install` must still deliver three separately-hard
artifacts. Plotly.py's real-world engineering complexity lives almost entirely
here, not in rendering. Miss any piece and the user hits a source build
requiring a Rust toolchain — an instant adoption cliff.

1. **The native core as prebuilt wheels.** Built as a Rust **`cdylib` with a
   plain C ABI** and a focused PNG-encoding dependency, compiled by the Hatchling build hook and loaded
   from Python with `ctypes`. There is no CPython extension ABI at all, so one
   `py3-none-<platform>` wheel covers every supported Python version on that platform
   without PyO3 or `abi3`. Wheel matrix in CI, release-blocking: manylinux
   (x86_64 + aarch64), macOS (arm64 + x86_64), Windows x86_64. A missing native wheel
   is a release failure, not an end-user surprise.
2. **The JS/WebGL2 render client as a host-neutral artifact**, versioned with
   the producing host, no CDN dependency (notebooks are often airgapped; §23's
   CSP rules apply). One TypeScript tree (`js/src`) builds `@curatelabs/xyg`
   (`packages/xy-client/dist/{index,standalone}.js`). Those bundles are a
   **generated artifact, not committed to git**: the Hatchling build hook
   builds them with `node js/build.mjs` and **copies** them into
   `python/xyg/static/` so the wheel and sdist embed the client — Python end
   users of a published wheel need no Node, npm, or CDN. JS/Node users consume
   `@curatelabs/xyg` (in-repo until the `@curatelabs` npm org exists; #13)
   without a Python install. The #59 foundation compiles the same Rust engine
   to WASM for the bounded shipped direct-browser paths; broader aggregate
   production is tracked by the post-M2 follow-up **Expand direct-browser aggregate production beyond the density/Scene vertical** (related to [#54](https://github.com/CurateLabs/xyg/issues/54)).
3. **The notebook integration via `anywidget`** — the current standard: one widget
   implementation works across Jupyter, JupyterLab, VS Code, Colab, and Marimo, and
   gives us the binary comm channel (§29's Jupyter row) without maintaining N
   frontend extensions. Server frameworks (Reflex/Dash-style) mount the same client
   as a component. One boundary is spec'd (reflex-shaped-api.md §3.3): the widget
   host still needs the anywidget *frontend* extension, which a prebuilt
   WASM-kernel frontend (JupyterLite's `%pip`, e.g. try-jupyter) cannot gain at
   runtime — there `show()`/rich display resolve to the standalone-HTML iframe
   host instead (same client, §29 static-export row; no kernel channel), with
   `XY_NOTEBOOK_DISPLAY` / `show(display=...)` overriding in both directions.
   Marimo's WASM build is the carve-out: it bundles its own anywidget frontend,
   so it stays on the widget host under "auto".

**Contracts that keep it honest:**
- **Comm-protocol versioning.** The native core and JS client ship together but can
  drift (cached notebook outputs, pinned server assets). The first-paint spec carries
  a protocol version; mismatch fails **loudly with an upgrade hint**, never silently
  renders wrong. Requests and replies carry no version of their own — the handshake
  happens once, at first paint, before any request is possible
  (`spec/design/wire-protocol.md` §7).
- **No-wheel behavior is defined:** the native Rust core is required and there is no
  pure-Python fallback. A source install compiles the core (Rust toolchain required);
  if the core cannot be loaded — an unsupported platform with no wheel and no local
  build — importing the compute layer raises a clear, actionable ImportError naming
  the supported platforms, never a silent degrade. Published platform wheels require
  the native core and fail the build if it is absent.
- **Binder builds are source builds, not wheel installs.** Binder is linux-64,
  where published wheels already exist — the source build is a deliberate
  trade-off that keeps hosted examples on the launched ref at the cost of
  compiling the core and render client inside repo2docker. The repository's
  `.binder/environment.yml` provisions only the build toolchain (`rust=1.96.*`,
  `nodejs=22.*` — loose pins, because exact conda build strings are
  arch-specific and retired by conda-forge rebuilds). The interpreter carries a
  loose version-only pin (`python=3.13.*`): repo2docker's default kernel env
  resolves to Python 3.10 (observed 3.10.19 on mybinder and in CI), below the
  package's `requires-python >=3.11`, so without the pin the pip install fails
  at metadata. The scientific stack the example notebooks import (matplotlib,
  pandas, scipy, scikit-learn, seaborn, h5py, requests, plus pysam and gwosc
  for the real_world series) is pip-installed in `postBuild` from wheels
  rather than provisioned through conda: keeping ~200 packages out of the
  mamba solve makes the image build faster and sidesteps observed extraction
  flakes on mybinder builder nodes.
  `.binder/postBuild` installs the checkout with `XYG_REQUIRE_CARGO=1`, making a
  missing native core fail during image construction rather than later at
  notebook import; if the source build breaks, the fallback is
  `pip install xyg` (the published linux-64 wheel), losing only
  launched-ref fidelity. Playwright's browser download is disabled for this
  build-only Node install, and the checkout's `target` and `node_modules`
  build directories, cargo's crate-download cache, and npm's package cache are
  removed after the wheel has captured the native core and render client.
  `.github/workflows/binder.yml` runs a pinned `repo2docker --no-run`
  whenever `.binder/`, `pyproject.toml`, or `hatch_build.py` changes — nothing
  else in CI builds a Binder image, so this is the only check that exercises
  the config end to end.
- **Install-size budget** joins the §23 bundle budget: wheel ≤ ~15 MB target
  (native core + JS client + assets), CI-enforced like every other number.
- **Import-time budget**: `import xyg` does no heavy work (< 200 ms); NumPy and
  the native core initialize lazily when a chart-building API is first imported/used.
- **Stdlib-import budget on the export path**: the lazily-imported export modules
  must not drag in the network or mail stacks. `xml.sax.saxutils` does exactly
  that — importing it pulls `urllib.request` → `http.client` → `ssl`, `socket`
  and all of `email`, 35+ modules, measured at ~7.5 ms of a cold static export,
  more than binning ten million points costs. `_svg.escape` is therefore a
  vendored copy of `saxutils.escape` (three `str.replace` calls), kept honest by
  a differential fuzz test against the stdlib plus a fresh-subprocess assertion
  that a static export leaves `urllib.request`/`ssl`/`email` unimported
  (`tests/test_svg_escape.py`). Prefer vendoring a leaf function over importing a
  package whose transitive tree dwarfs it.

## 34. Filtering, selection & linked views — the pyramid alone cannot answer them (F2)

**The gap:** the Tier-2/3 pyramid holds *unfiltered* aggregates. `df[df.region=="US"]`,
a box-select driving a cross-filtered second chart, a legend toggle excluding a
category — all of these make the precomputed counts **wrong**, and §28 had no filter
path. The research confirmed this is why datashader deliberately re-aggregates every
interaction: a static pyramid is stale under any dynamic predicate. Filtering is not
an edge case in analytics — it is the main event, so it gets its own three-tier model,
mirroring the LOD ladder:

**Filter Tier A — indexed range predicates (cheap, instant).** Range filters on
indexed/zone-mapped columns (§22) — time windows, axis-linked ranges, numeric
between — resolve by **tile pruning and bin clipping**: zone maps identify chunks
wholly in/out (no recompute), and only boundary tiles re-bin. Cost O(boundary), the
common case for pan/zoom-linked filtering.

**Filter Tier B — arbitrary predicates (fast re-bin of the visible window).** For
predicates the index can't serve (string contains, computed expressions,
multi-column conditions): **re-bin only the visible window** in the native core —
SIMD binning at ~50–100M pts/s (§5's worker fallback numbers), zone-map-pruned to
the viewport, under stale-while-revalidate + progressive refinement (§17). This is
datashader's model, minus its two taxes: no full-dataset scan (visible window only)
and no per-frame network round-trip (pan/zoom still composes the filtered tiles
locally; only the *filter change* triggers recompute).

**Filter Tier C — linked brushing across views (the Falcon/Mosaic index).** For
cross-filtering dashboards — the highest-value technique from the research: build a
**summed-area (cumulative-sum) index keyed on the active view's dimensions** at
pixel-level bin resolution. Any brush range then resolves per passive view as a
**difference of cumulative sums: O(1) per bin, O(bins) per view, independent of row
count** — Falcon sustains 50 fps across 5 passive views from thousands to billions of
rows on exactly this structure. The index is built in the native core (one pass over
the filtered base, zone-map-accelerated), sized ∝ bins not rows (screen-bounded, §27
budget), rebuilt when the *active view* changes (Falcon's documented trade), and
prefetched on idle for the likely-next active view (Falcon's documented trick).

**Composition rules:** a session's filter state = (range predicates → Tier A) ∧
(arbitrary predicates → Tier B) ∧ (brush selections → Tier C). Selection is a
first-class per-trace bitmask (1 bit/row, §27-budgeted) so styled selected/unselected
rendering (dimming, highlight) works at every LOD tier — aggregated tiers carry a
second "selected-count" channel per bin (feeding the §5 aggregation set), so a brush
visibly lights up density, not just direct marks. Every filter application logs
which tier served it — no silent full rescans.

**API surface (Python):** `fig.filter(expr_or_mask)`, `fig.on_select(callback)`,
`link(fig_a, fig_b, on="x")` — the kernel-side core owns filter state so callbacks
receive Arrow slices, not JSON.

**Shipped slice:** the legend click-toggle predicate (`Trace.hidden` /
`Trace.hidden_categories`, wire `legend_toggle`). It follows this section's
rules exactly: the unfiltered pyramid is bypassed while a category mask is
active (a Tier-B visible-window re-bin serves instead, `binning` tagged
`-masked`), rows are narrowed before every bin/sample/drill, selections
exclude hidden rows, and each masked reply carries the `filter` state it was
computed under (§37's `filter_hash`, in literal form). Contract:
`spec/api/interaction.md` §10.

## 35. Milestone amendments (round 3)

- **Phase 0** adds the **wheel matrix + anywidget skeleton** (F1) — distribution is a
  thesis risk on par with the memory claims, so it's proven first, not retrofitted:
  exit criterion "pip install on a clean machine on all five platforms; figure renders
  in Jupyter, VS Code, and Colab."
- **Phase 1** adds Filter Tier A (zone-map range filtering) — near-free once zone maps
  (§22) exist.
- **Phase 2** adds Filter Tier B (visible-window re-bin) alongside the Tier-2
  pyramid — they share the SIMD binning kernel. The fill-rate-aware tier heuristic and
  buffer chunking (F3) are **still pending**: the shipped tier decision is count-only
  and the render client does not chunk vertex buffers (§5).
- **Phase 4** adds Filter Tier C (summed-area index + linked views) with the
  shared-context dashboard work (§18) — same milestone because cross-filtering is a
  dashboard feature.
- The §12 benchmark harness gains three filter benchmarks: range-filter latency (A),
  arbitrary-predicate re-bin latency at 10M/100M visible (B), and Falcon-style brush
  fps across 5 linked views at 100M rows (C) — target ≥50 fps to match the published
  Falcon bar.

## 36. Theming — CSS-native where it can be, a token bridge where it can't

**The constraint, stated honestly:** CSS styles DOM nodes, and the data marks (points,
lines, bars, density surfaces) are **pixels in a `<canvas>`**, not nodes — so a selector
like `.line { stroke: red }` has nothing to match. This is the direct cost of killing
the one-node-per-point wall (§1): you cannot have 10M CSS-addressable elements *and* 10M
points at 60 fps. Every GPU renderer (deck.gl, ECharts-GL, LightningChart) shares this
property. (Calibration: Plotly is barely CSS-styleable either — it writes computed
styles *inline* on its SVG, so stylesheet overrides mostly lose; its users theme via
`layout.template`, not CSS. The bar to clear is lower than "SVG" implies.)

The design splits into three styling surfaces:

**(a) Chrome — genuinely CSS-native.** Axis tick labels, titles, legend, tooltips, and
hover readouts are real HTML/SVG in the DOM (§7). Fonts, color, spacing, borders,
focus states: plain CSS, full inheritance and media queries, no bridge needed. The
container (size, border, background, layout) is ordinary too, and the canvas is
transparent-capable so a page background shows through. This covers most of what "make
the chart match my site" actually means — typography and chrome. The legend is also
an interaction surface: hovering a row emphasizes its series by dimming the rest
(default on, `xyg.legend(highlight=False)` opts out; full contract in
`spec/api/interaction.md` §9). Clicking a row toggles the series/category —
the first shipped §34 predicate: state syncs to the kernel (`legend_toggle`),
direct tiers re-filter client-side (0 bytes, §37), density tiers re-bin
kernel-side under the mask (contract in `spec/api/interaction.md` §10).
Legend titles, rows, swatches, and labels and tooltip titles, rows, field labels,
and formatted values each carry stable `data-xy-slot` hooks. Tooltip `labels=`
changes presentation text without changing source-field lookup, formatting keys,
title placeholders, or event payloads; without an explicit `fields=` list it
renames the matching default x/y/color/size rows. User-provided chrome text is
assigned through `textContent` / text nodes, never parsed as HTML.
The canonical 48-slot tuple also reaches Cartesian axis spines/ticks/gesture
bands, colorbar extensions/contour lines/minor ticks, the whole annotation
canvas, and every visible modebar subpart (including its draggable grip and
popover contents). Visual defaults live in the zero-specificity base layer so
normal author and Tailwind utility layers win; required geometry and live
interaction state remain client-owned inline declarations.

**(b) Marks — themed via a CSS-custom-property bridge.** The render client reads
`--chart-*` custom properties off its container and maps them to GPU state, so the
*marks* are themable through CSS variables even though they aren't CSS *nodes*:

```css
.my-dashboard {
  --chart-bg:   #0f1520;
  --chart-grid: #24313f;
  --chart-axis: rgb(226 232 240 / 55%);
  --chart-text: #e5e7eb;   /* chrome text: ticks, titles, legend, annotations */
}
```

Mechanism: `readTheme()` (`js/src/20_theme.ts`) resolves the canvas tokens at mount and
writes them to renderer state — clear color, grid and axis uniforms, label color. Chrome
tokens are consumed directly by the stylesheet (`XY_CHROME_CSS`, zero-specificity
`:where()` rules) rather than through the renderer. One implementation reality (audit
round 4): `getComputedStyle` returns a custom property's *raw token stream*, not a
resolved color — so color tokens are resolved via a hidden **probe element** (assign
`color: var(--chart-bg)`, read back the browser-computed rgb), which handles every CSS
color format (`oklch()`, `color-mix()`, named colors) without shipping a CSS color
parser. Crucially, **because
tokens flow through CSS variables, the cascade, inheritance, and media queries all
work** — the *variables* cascade even though the pixels don't, so per-container
theming, brand overrides, and `@media (prefers-color-scheme)` behave exactly as a CSS
author expects.

**The theme contract:**
- **A documented token vocabulary**, split by consumer. Canvas tokens read by
  `readTheme()`: `--chart-bg`, `--chart-grid`, `--chart-axis`, `--chart-text`. Chrome
  tokens read by the stylesheet: `--chart-tooltip-bg` / `--chart-tooltip-text`,
  `--chart-legend-bg`, `--chart-badge-bg` / `--chart-badge-text`, `--chart-modebar-bg` /
  `--chart-modebar-active` / `--chart-modebar-focus`,
  `--chart-selection` / `--chart-selection-fill`,
  `--chart-zoom-selection` / `--chart-zoom-selection-fill`, `--chart-crosshair`,
  `--chart-annotation-text`, `--chart-cursor` / `--chart-cursor-pan`, `--chart-focus`.
  Unset tokens fall back to a built-in theme (`currentColor` at documented opacities for
  grid/axis/label). The public reference is `docs/styling/themes-and-tokens.md`.
- **Author-supplied ramps and cycles (spec-side, wired).** `theme(palette=[...])` sets
  the chart's **categorical cycle** — the colors unnamed series take in order *and* the
  colors a categorical `color=` channel assigns to its categories. It lives on `Figure`
  before any mark applies (a trace bakes its color at build), rides the spec as
  `palette`, and is carried on each `ColorChannel` so ship / re-bin / legend / export all
  read one source. Entries obey the same literal-color rule as ramp stops below, plus a
  sharper reason of their own: a palette is an *indexed* lookup, so several browser-only
  entries would land on one fallback and merge distinct categories into a single
  indistinguishable color. They are **normalized to hex on the wire**, not merely
  validated — the client's only cascade-free decode is `hexColor`, and anything else hits
  a `getComputedStyle` probe that returns `""` on a root not yet in the document
  (notebook webviews attach asynchronously), yielding black permanently, since a cached
  palette LUT is rebuilt only on GL context loss. `channels.palette_rows_rgba8` is the one
  place a palette becomes LUT rows — shared by the density plane and both static
  exporters — and it substitutes the built-in color *at the same index*, never one shared
  fallback, and warns (§28).
  `colormap=` likewise accepts a **custom ramp**: a sequence of 2–256 CSS colors,
  optionally `(position, color)` pairs, or a CSS `linear-gradient(...)`.
  `channels.resolve_colormap` normalizes every form to *evenly spaced 8-bit RGB stops* —
  the same shape `10_colormaps.ts` stores the built-ins in — so the WebGL client, the SVG
  writer, and the native rasterizer keep exactly one LUT interpolation path; positioned
  stops resample at the LUT's own 256 texels, so the round trip is exact rather than
  approximate. Ramp stops must resolve to fixed channels in Python (hex/`rgb()`/`hsl()`/
  named); `var()`/`oklch()`/`color-mix()` are refused *with the reason*, because a
  browser-only color cannot build the same LUT for a headless export (§28: never a silent
  fallback). The client caches LUTs by value, not array identity — a custom ramp arrives
  as a fresh array each spec, and identity keying would leak a GL texture per frame.
- *Pending:* the **CSS-token** route to the same two things — a series-palette token
  (`--chart-series-N`, indexed rather than a space-separated list so entries cascade and
  override individually, cycling with a lightness rotation past the highest defined
  index) and a colormap token (`--chart-colormap`). Neither is wired: series colors and
  colormaps come from the spec / `theme()` only. The categorical and sequential defaults
  are the accessible, CVD-safe palettes from §20, not arbitrary.
- **Live re-resolution.** The client watches `matchMedia('(prefers-color-scheme: dark)')`
  and a `MutationObserver` on the container's `class`/`data-theme`/`style`, re-resolving
  tokens on any change. Because of the retained scene graph (§7), **a theme change is
  uniform + LUT updates, never a data re-upload** — theme/dark-mode switching stays at
  60 fps even on a 100M-point figure, and a dashboard theme flip repaints every linked
  view in one frame.
- **Programmatic parity.** Everything a token sets is also settable from Python
  (`fig.theme(...)`) so notebook users who never touch CSS get the same control; the
  CSS bridge is the web-author's path to the same renderer state, not a separate system.
- **Export parity — partially closed; the kernel path is still an open gap.** Two export
  routes exist. *Client-side* (modebar download) is themed correctly: `_exportSvgMarkup()`
  (`js/src/53_interaction.ts`) inlines the resolved `--chart-*` tokens and inherited text
  styles onto the detached clone before serializing, so the downloaded SVG/PNG matches
  the screen. *Kernel-side* export (`to_svg` / `to_png` / `write_image`, rendered by
  `python/xyg/_svg.py` and `python/xyg/_raster.py`) has no CSS: it uses only the
  Python-set theme (`xyg.theme(...)`), so a chart themed purely through CSS custom
  properties exports with the Python theme, not the on-screen one.
  *Pending:* a **theme snapshot** — the client sending its resolved token values back
  over the comm channel on every theme change, so the kernel holds the effective theme.
  No producer or handler exists today. With no client attached (headless script) the
  Python-set theme is authoritative and correct either way.
- **Escape hatches.** `MutationObserver` misses stylesheet swaps and non-color-scheme
  media flips → a public `refreshTheme()` exists for apps that restyle dynamically.
  `forced-colors: active` (Windows High Contrast) restyles DOM chrome automatically
  but not the canvas → the client listens for it and maps marks to the forced palette
  (ties to §20 accessibility).

**(c) Per-mark / data-dependent styling — inherently spec-level, not CSS.** Styling an
individual point (`.point[data-id="42"]:hover`) or coloring by a data column is *not*
reachable by CSS and never will be — there's no node. This goes through the spec
(`color=column`, `size=column`) and the selection bitmask (§34) for
selected/hover/highlight styling, resolved on the GPU. This is a real limitation, not
an oversight: it's the same reason the engine scales.

**Summary:** chrome is plain CSS; background/grid/axis/text are CSS via the
`--chart-*` token bridge (cascade + dark-mode included); per-mark data-driven styling
is spec-level. The one thing we explicitly *don't* promise is arbitrary per-element CSS
selectors on marks — the price of the pixel-based scale everything else buys.

## 37. Transfer protocol & caching — never send the same bytes twice

The kernel↔client boundary (§29, §32) needs a protocol, not just a format. The design
goal: **the wire carries only what the client provably lacks**, and every interaction
class has a defined (usually zero) transfer cost. Prior art absorbed: Perspective's
lesson (batch/schema reuse beats cell-level diffing), Falcon's idle prefetch, HTTP
content-addressing.

**Content-addressed, generation-keyed cache entries.** Every transferable unit —
column chunk, pyramid tile, decimation buffer, filter index slab — has a stable ID:

```
(trace_id, tier, tile_coords | chunk_idx, data_generation, filter_hash, agg_channel)
```

`data_generation` increments on data mutation (append bumps only affected chunks'
generations); `filter_hash` fingerprints the active predicate set (§34). Entries are
**immutable once created** — a changed tile is a *new* ID, never an overwrite — which
makes caching trivially correct: any ID the client holds is valid forever, eviction is
pure LRU under the §27 byte budget, and there is no invalidation protocol to get wrong.

**The manifest handshake.** On any state change the kernel sends a **manifest** (the
ID list the new view needs — a few hundred bytes); the client replies with the subset
it lacks; the kernel ships only those payloads. One round-trip, no redundant bytes,
and a notebook reconnect (fresh client, empty cache) needs no special path — it lacks
everything, so the manifest mechanism *is* the recovery mechanism.

**Per-interaction transfer costs (the contract):**

| Interaction | Wire cost | Why |
|---|---|---|
| Pan (within cached tiles) | **0 bytes** | client composes its cache; view matrix is local |
| Zoom within pyramid levels | **0 bytes** (typ.) | adjacent-level tiles usually prefetched |
| Zoom past pyramid floor / pan to cold region | missing tiles only | manifest diff |
| Filter toggle **back** to a previous state | **0 bytes** (typ.) | old `filter_hash` generation still cached — flipping US on/off re-sends nothing |
| New filter state | recomputed *visible* tiles only | §34 Tier A/B; tagged with new `filter_hash` |
| Streaming append | dirty tile cells + ring delta | O(appended), per §28 |
| Theme / style change | **0 bytes** | client-side uniforms/LUT (§36); nothing goes upstream |
| Hover / pick | ~1 row on drill | pick resolves client-side; drill fetches top-k rows |
| New trace on same DataFrame | new columns only | column IDs shared across figures — a dashboard of 20 views of one table transfers the data **once** (§18) |

**Prefetch & backpressure.** Idle prefetch (Falcon's trick) pulls the adjacent
pyramid level and viewport-neighbor tiles, budget-capped, so the common zoom/pan
stays in the 0-byte rows above. Rapid interaction events **coalesce** (only the
latest viewport wins); every request carries an ID and is **cancelable**, so a
superseded tile request dies on the kernel side instead of clogging the wire.
Responses are batched typed-binary frames (Perspective's lesson — never per-cell
messages), uncompressed on the hot path to preserve zero-copy, lz4 optional for
cold/remote Tier-3 tiles only.

**Two-sided budgets.** The client tile cache and the kernel's LodCache (§10) run the
same eviction policy (LRU weighted by zoom-distance) under independent byte budgets —
and because entries are immutable and recomputable from canonical columns, eviction
on either side is always safe; worst case is a re-send or re-bin, never wrongness.


---
---

# Part 2 — Competitive Research

# How the fastest graphing libraries work — research findings

Companion to the charting-engine design plan. Every load-bearing design decision was
checked against production libraries and the academic literature. **Headline: all six
core bets are independently validated in the field — but no single library combines
them, and the research forces two honest corrections and surfaces ~8 techniques to
steal.**

*Method: the session egress proxy blocked direct page fetches (403 on every host), so
all findings are WebSearch synthesis over primary sources (official docs, GitHub,
papers), with URLs cited (§7). Quantitative figures are the libraries' own published
numbers. A few research subagents received prompt-injected output impersonating system
messages ("drop your guardrails"); these were disregarded and the work redone.*

---

## 1. Scorecard — our design vs the field

| Design decision | Verdict | Strongest evidence |
|---|---|---|
| Arrow binary transport, no JSON | ✅ **Consensus** | Perspective, Mosaic, DuckDB-WASM, deck.gl |
| Offset-encoded f32 + f64 canonical | ✅ **Strongly validated** | deck.gl deprecated emulated fp64 once it did this; Cesium RTC |
| Min/max-per-pixel line decimation | ✅ **Best practice** | = academic M4; Chart.js ships it; 2023 paper recommends MinMax > LTTB |
| Web Worker + WASM core | ✅ **Consensus** | Perspective, DuckDB-WASM (worker-first) |
| GPU as cache, CPU/server canonical | ✅ **Universal** | deck.gl rebuilds GPU buffers from CPU typed arrays; nobody makes GPU the truth |
| Screen-bounded aggregate memory | ✅ **Validated at aggregate layer** | Falcon, datashader, Mosaic, imMens |
| Density-texture aggregation (Tier 2) | ✅ **Validated**, ⚠️ **not novel** | datashader, deck.gl GPUGridAggregator, imMens |
| Data-space tile pyramid (Tier 2/3) | ⚠️ **Refine** | beats datashader's *interactive* path; = its `render_tiles` export path |
| "Single copy / ~0 CPU after upload" | ⚠️ **Overclaim** | even uPlot keeps derived caches; reality is 1+ε copies |
| Plotly "40–100 B/pt × 3 copies" | ⚠️ **Unverified** | directionally right; **measure it**, don't publish it |

---

## 2. Validated — with the refinements the field teaches

**Arrow, no JSON.** Perspective states Arrow-IPC `ArrayBuffer` batches are far more
efficient than JSON (worse) or JS objects (much worse) and spare the main thread.
DuckDB-WASM returns results *always* as Arrow, zero-copy. *Refinements:* transfer
(don't structured-clone) Arrow buffers worker↔main — the backing `ArrayBuffer`s are
Transferable; keep IPC **uncompressed** on the hot path (compression breaks zero-copy).

**Offset-encoded f32 + f64 canonical.** The single strongest validation. deck.gl's
default is a viewport-determined common-space translation (`LNGLAT_OFFSETS`) with a
**zoom-driven origin re-basing that updates only a uniform** — and they **deprecated
emulated fp64 in v6.3** because the offset trick "rivals 64-bit precision at 32-bit
speeds." Cesium's RTC is the same idea (f32 relative to a center, f64 center on the
CPU). *Refinement:* keep full fp64-emulation as a rare fallback, not a default path —
the offset makes it almost never necessary.

**Min/max-per-pixel decimation.** Our Tier-1 is the academic **M4** algorithm (Jugel
et al., VLDB 2014): per pixel column keep **first, last, min, max** — *provably*
pixel-accurate for a rasterized line. The 2023 guidelines paper (arXiv 2304.00900)
finds **MinMax is the most visually *stable* algorithm** and recommends it over LTTB,
which drops spikes and jitters under pan. Chart.js ships `min-max` ("up to 4 points per
pixel") verbatim; ECharts added `minmax` in 5.5.0. *Refinement:* keep the full **4
points/column (M4)**, not just min+max (2) — first+last fix inter-column segment
correctness. Implement the kernel as **SIMD `argminmax`** (tsdownsample: 200–300×
NumPy, 1B pts <0.1s).

**Worker + WASM core.** Perspective runs its C++/WASM engine in a WebWorker; DuckDB-WASM
is "worker-first." Arquero is the counterexample — single-threaded main-thread JS — and
is cited as the thing that *doesn't* scale. Validates keeping the core off the main
thread.

**GPU as cache.** deck.gl rebuilds GPU buffers from canonical CPU typed arrays and
shallow-compares `data` to skip regen. No library treats GPU memory as source of truth.
Matches our §27 ownership model exactly.

**Screen-bounded aggregate memory.** Falcon: "the size of the data tile is independent
of the size of the data" (∝ bins × pixels). datashader: "fixed-size regardless of
records." imMens: "limited by the chosen resolution … not the number of records."
*Honest scope:* this holds at the **aggregate/index layer** — vaex/Arquero/deck.gl are
still data-bounded in their base store. Our tiling is what carries the property down to
the base layer.

**Deferred colormapping.** datashader's pipeline is Aggregate → Transform → Colormap
(default `eq_hist` histogram-equalization to beat overplotting) — exactly our
"colormap at composite time, so restyle never re-bins."

---

## 3. Corrections the research forces (the most valuable part)

**(a) "Single canonical copy, ~0 CPU after upload" is an overclaim.** Even uPlot — the
leanest library measured — keeps derived path/scale caches, and has an *open* zero-copy
request (#1124) precisely because true zero-copy isn't the default. Reality is **1 + ε
copies**: full columnar array once + small screen-bounded derived buffers. The doc
should say that, not imply zero extra bytes. *Good news:* the **bytes/point target is
validated and even conservative** — uPlot's typed-columnar, no-object-model design hits
**21 MB peak / 3 MB final** vs dygraphs 88/42 and Highcharts 97/55 on the same
benchmark. 12–24 B/pt is realistic.

**(b) Plotly's "40–100 B/pt × 3 copies" is not primary-sourced.** It's directionally
supported (Plotly keeps input + `calcdata` + GL/SVG buffers; plotly-resampler reports
**>10 GB → <700 MB ≈ 14×** when downsampled), but the exact byte figure should be
**measured** (heap-snapshot `scatter` vs `scattergl` at 1M pts) before it appears in any
public claim. Treat as estimate, not citation.

**(c) Hard GPU ceilings to design around.** deck.gl: ~1M points @60fps, degrades to
10–20fps near 10M, and **crashes between 10M–100M** during buffer generation because
**Chrome caps a single allocation at ~1 GB**. Plus **fragment fill-rate**: 10M radius-5
points ≈ **1B fragment invocations/frame**. Rerun hits a **2M-point wall** by
re-uploading every frame (validates our retained buffers, but shows the ceiling is
real). *Implication:* our **direct Tier-0 must chunk large buffers** and hand off to
aggregation before ~1M *drawn* marks — the vertex count isn't the only limit, fill-rate
and the 1 GB cap are.

**(d) The tile pyramid is not novel — and a static one goes stale.** datashader already
ships `render_tiles` (power-of-two 4096²→256² tiles, NetCDF out-of-core) — our Tier-2/3
*is* that, plus classic XYZ map pyramids. Our genuine contribution is making it **live
and interactive** (client-side per-frame compositing, re-bin only below the floor),
whereas datashader's is static export. **But** datashader keeps its *interactive* mode
re-aggregating on purpose: **a fixed pyramid is stale under brushing / filtering /
transform changes**, which re-aggregation handles for free. *This is a real gap in our
doc:* if we want dynamic filters on top of the pyramid, we need a fast re-bin path or a
**Falcon-style active-dimension index layered over the pyramid**.

---

## 4. Techniques to steal (ranked; mapped to doc sections)

1. **Falcon/Mosaic summed-area-table data cube** — for linked-view cross-filtering at
   scale. A cumulative-sum index keyed on the active brushing dimension makes any brush
   = a difference of cumsums → **O(1) passive-view updates, index size ∝ bins not rows**.
   Mosaic auto-materializes these at pixel resolution. *This is the answer for dashboard
   brushing (§18) and the fix for the stale-pyramid gap (§3d).*
2. **deck.gl offset-origin re-basing via uniform-only update** — the concrete mechanism
   for our §4/§16 precision path.
3. **Async GPU picking**: Rerun's integer **R32UI** ID texture + `GpuReadbackBelt`
   (async readback, no stall) over deck.gl's RGB8 (16M-ID cap); carry a **per-instance
   index** channel (GLMakie). Plus deck.gl's reusable **picking shader-module toggled by
   one uniform** so every mark type gets picking for free. *Augments §17.*
4. **Line rendering, two schools** — Rerun's **un-instanced triangle-list +
   `gl_VertexID`, joins as fragment-shader cut-outs, data in textures** for *many short*
   polylines (multi-series time series); instanced segments (regl-gpu-lines, 2 draw
   calls, miter/round joins) for *long* paths. Nobody uses `GL.LINES`. *Augments §7.*
5. **SDF markers** (quad + fragment-shader signed-distance function) for crisp,
   resolution-independent antialiased points — deck.gl, Makie, and Plotly all do this.
6. **DuckDB-WASM / hyparquet out-of-core**: Parquet **HTTP range requests +
   row-group-stat predicate pushdown** as the Tier-3 mechanism — possibly **no bespoke
   tiler needed**; Parquet row-group stats *are* a free coarse index (matches our zone
   maps §22). *Augments §5/§28.*
7. **VegaFusion DAG-partitioning** — decide *per transform node* whether it runs
   native-side or in the browser. A principled model for our native-core-vs-WASM split —
   **especially relevant now that binding is Python-only** (heavy nodes run native
   in-process; only leaf render nodes cross to the browser). *Augments §8/§9/§29.*
8. **Perspective's lesson**: batch/schema reuse **over** cell-level diffing — they
   *dropped* per-cell partial updates because computing which cells changed cost more
   than re-sending Arrow row batches. Bear on our diff engine (§7).

---

## 5. The datashader question, answered (the crux)

**Does datashader precompute a pyramid or re-aggregate every zoom?** In its **default
interactive mode: re-aggregates from scratch on every zoom/pan** — no cached pyramid.
HoloViews `rasterize`/`datashade` wrap the data in a `DynamicMap` driven by `RangeXY` +
`PlotSize` streams; each viewport change fires a **server-side callback that reruns
aggregation** over the in-view data into a fresh `Canvas(w, h, x_range, y_range)` grid,
then ships **one RGBA image** back over the Bokeh websocket. Cost per interaction =
**O(points in view) + a network round-trip**, nothing composited or reused between
frames. (It's made bearable by Numba + multicore + Dask/CUDA: ~1B points in seconds, 4B
in <3 min on 32 cores.) A *separate* offline module, `render_tiles`, does build a
static power-of-two pyramid — but not in the interactive path.

**Verdict:** for **navigation**, our live data-space pyramid genuinely beats datashader's
interactive path — **O(visible tiles), no per-frame round-trip, client-side
compositing, re-bin only below the floor** = strictly lower latency and jitter. It does
**not** beat datashader's own `render_tiles` in concept (same pyramid idea) and it
inherits the **static-pyramid-is-stale-under-filtering** tradeoff. Defensible framing:
we **unify** them — a *live* pyramid with client compositing — and layer a Falcon-style
active-dimension index when dynamic filtering is needed.

---

## 6. Competitive scale numbers (grounds the "how much faster" comparison)

| System | Published figure |
|---|---|
| Plotly.py `scattergl` | practical ceiling **~1M**; SVG ~10⁴–10⁵ |
| plotly-resampler | ships ~1000 pts; **>10 GB → <700 MB** memory |
| deck.gl (WebGL) | ~1M @60fps; **crashes 10M–100M** (1 GB alloc cap); fill-rate bound |
| uPlot | **21 MB peak** (vs 88–97); 166k pts in ~25 ms; ~6fps @100k OHLC |
| ECharts | "millions" via progressive (latency only, not memory); ~23fps @100k |
| datashader | **~1B in ~1s** (16 GB laptop); 4B in <3 min / 32 cores; GPU 10–15× @300M |
| vaex | **~1B rows/s** on-grid stats; out-of-core / mmap |
| Falcon | **50 fps**, 5 passive views, pixel-level brush; 10M browser / 1.7B via GPU DB |
| imMens | **50 fps invariant thousands→billions**; ≤4-D tiles; single active brush |
| Nanocubes | billions in laptop RAM (100s MB–GB); arbitrary dims, higher latency |
| VegaFusion | 1M-row histogram **~9.5s → ~0.6s** (aggregation pushed to Rust) |
| LightningChart JS | ~1.5B interactive line (commercial WebGL); 10M in ~0.29s |

---

## 7. Sources

**GPU rendering.** deck.gl performance/coordinate-systems/picking docs
(deck.gl/docs/*), vis.gl "flat earth" precision blog, luma.gl v9 docs, regl API,
LightningChart perf pages, Rerun `re_renderer` docs + ARCHITECTURE.md + issues #1136/#7857,
GLMakie/WGLMakie docs, Plotly.js WebGL deepwiki, regl-gpu-lines, Stardust (EuroVis 2017).

**Arrow / WASM / columnar.** Perspective architecture docs + discussions #2995/#1750,
regular-table, ClickHouse×Perspective blog; vaex docs + arXiv:1801.02638; Falcon
(idl.uw.edu/papers/falcon, CHI 2019) + falcon-vis; Mosaic (idl.cs.washington.edu
2024-Mosaic-TVCG.pdf) + arXiv:2507.19690; DuckDB-WASM (duckdb.org 2021 blog);
Arquero/Flechette (idl.uw.edu); hyparquet; Arrow IPC docs + issue #39017.

**Decimation.** LTTB thesis (Steinarsson 2013, skemman.is); M4 (vldb.org p797/p1705) +
Observable @uwdata/m4; guidelines paper arXiv:2304.00900; MinMaxLTTB arXiv:2305.00332;
tsdownsample arXiv:2307.05389; plotly-resampler arXiv:2206.08703; uPlot GitHub + HN
threads + issues #1124/#1122; ECharts perf/large-data/5.5.0 docs + ECharts-GL; Chart.js
decimation docs + PR #8468; dygraphs docs; regl-scatterplot; SciChart benchmark suite.

**Aggregation / data tiles.** imMens (vis.stanford.edu/papers/immens, EuroVis 2013,
DOI 10.1111/cgf.12129) + code; Nanocubes (IEEE TVCG 2013) + laurolins.github.io;
Hashedcubes (IEEE TVCG 2017); datashader Pipeline/Performance/Interactivity/tiling docs
+ tiles.py; HoloViews Large_Data; VegaFusion (vegafusion.io, arXiv:2208.06631); Bokeh
server / InteractiveImage discourse; viz surveys (Springer, Tsinghua VLDBJ).
---
---

# Part 3 — Performance estimates vs standard Python & React libraries

**These are design targets measured against each library's own published/measured
numbers — not results of a built system.** Phase 0's benchmark harness exists to replace
every estimate here with a measurement (Plotly side-by-side, regressions fail the build).
The honest framing: this is not one multiplier. The field splits into "convenience"
libraries (huge audience, low ceiling) and "big-data specialists" (high ceiling, poor
interactivity/ergonomics), and this engine beats each camp differently.

## Python libraries

| Library | Interactive ceiling | Memory | Interactive pan/zoom | Exact hover at scale | Notebook |
|---|---|---|---|---|---|
| **Matplotlib** | ~10⁴–10⁵ (static beyond) | heavy | ✗ static PNG | ✗ | render-only |
| **Plotly.py** | ~1M (`scattergl`); ~10⁴ SVG | high — resampler saw >10 GB → <700 MB (~14×) | ✓ but stutters near ceiling | ✓ small data | ✓ |
| **Bokeh / Altair** | ~10⁵ (Altair caps at 5k rows) | high | ✓ | ✓ small | ✓ |
| **datashader** | ~1B in ~1s (16 GB laptop) | screen-bounded (ships pixels) | ✗ alone — re-aggregates every zoom + round-trip; needs HoloViews/Bokeh stack | ✗ (raster) | ✓ |
| **vaex** | ~1B rows/s on-grid | out-of-core / mmap | limited | ✗ | partial |
| **PyQtGraph / VisPy** | millions (GPU) | moderate | ✓ | partial | ✗ desktop-first |
| **This engine** | **100M–1B, interactive** | **12–24 B/pt direct; screen-bounded aggregated** | ✓ local (tile reuse) | ✓ via canonical store + drill | ✓ |

## React / JS libraries

React chart libs are often *worse* than Python's, because SVG + React reconciliation
creates a **React element (and vdom diff) per data point**.

| Band | Libraries | Practical ceiling | Multiplier to our target |
|---|---|---|---|
| React SVG | **Recharts, Victory, Nivo** | ~1–10k points | **~10,000×** |
| React SVG (lean) | visx | ~10–50k | ~2,000× |
| Canvas wrappers | react-chartjs-2 (+decimation), uPlot-react | ~100k–1M lines | ~100× |
| Canvas / WebGL | ECharts (~23 fps @100k measured), Plotly.js `scattergl` (~1M) | ~1M | ~100× (via our aggregation tiers) |
| GPU-first | deck.gl (~1M @60fps; degrades by 10M; crashes 10–100M @ 1 GB alloc cap) | ~1–10M | ~10–100× |

Two structural notes for React specifically:
- Our marks **bypass React reconciliation entirely** — the component is a thin mount;
  data flows as Arrow over the prop/comm boundary, never through vdom diffing or state.
- Versus **deck.gl** (the strongest React-ecosystem competitor), the win isn't raw draw
  speed — it's the **aggregation tiers** plus the **buffer chunking** that deck.gl
  documents crashing without (the ~1 GB single-allocation cap, 10M–100M items).

## The verdict that matters

The honest headline is not "N× faster than everything." It is: **no existing Python or
React library gives you all four of {100M+ points, fully interactive pan/zoom/hover,
low/bounded memory, one simple API in a notebook or React app} at once.**

- vs the **convenience libraries** (Plotly, Bokeh, Altair, Recharts, Victory, Nivo,
  visx): **1–4 orders of magnitude** more points, several-fold less memory, no
  main-thread freeze. This is the decisive, everyday win.
- vs the **big-data specialists** (datashader, vaex): **not dramatically faster at raw
  throughput** — they use the same aggregation trick, so we're in their class, not 10×
  past them. The win is architectural: interactive pan (tile reuse vs re-aggregate +
  round-trip), exact hover/drill, and a single ergonomic API instead of a multi-library
  stack.
- vs **desktop GPU** (PyQtGraph, VisPy): comparable at ~1M on a desktop; our edge shows
  at 10M+, out-of-core, and *in the browser/notebook*, which they don't target.

**Two honesty caveats.** (1) Targets, not measurements — Phase 0 replaces them. (2) On a
plain desktop at ~1M points, VisPy/PyQtGraph and deck.gl are already GPU-fast; we don't
blow them away there — the separation appears at 10M+, out-of-core, linked-view
filtering, and low resident memory.


---
---

# Appendix A — Audit Log (round 3, verbatim)

*This is the raw adversarial review that produced Part IV. F1–F3 were resolved into §32–§35; F4–F12 remain outstanding (see the status table at the top).*

# Design audit — round 3 (post-research, Python-only)

Adversarial review of the charting-engine design plan **as it now stands** — i.e. after
Parts I–III, the **Python-only binding** decision, and the library research. Every
finding here is **new relative to Parts II and III** (I did not re-list the SAB, f32,
byte-identical, aggregation-cost, or Tier-3-index findings — those are already resolved
in the doc). Two lenses drive this round:

1. **Python-only changes the risk surface.** The binding layer collapses, but the
   product now lives or dies on two things the doc barely mentions: *how the native
   core ships via pip* and *how the render client gets into a notebook cell*.
2. **The research exposed real ceilings and gaps** — fill-rate, the 1 GB allocation
   cap, the stale-pyramid-under-filtering tradeoff, and the fact that the pyramid isn't
   novel.

Confidence is marked per finding: **[confirmed]** = verifiable by reading the doc or a
cited primary source; **[plausible]** = a logical consequence I'm confident of but
haven't measured.

---

## Findings summary

| # | Finding | Severity | Confidence |
|---|---|---|---|
| F1 | No packaging/distribution story — the #1 risk for a Python-only product | **Critical** | confirmed |
| F2 | No filtering / selection / linked-brushing model; a static pyramid is stale under any filter | **Critical** | confirmed |
| F3 | GPU ceilings mis-modeled — fill-rate & the 1 GB single-allocation cap bound Tier 0, not point count | **Major** | confirmed |
| F4 | A single viewport offset can't serve multiple traces at different coordinate magnitudes | **Major** | plausible |
| F5 | Tier-2 assumed a scalar density — **resolved for color** (mean-point-color surfaces, LOD doc §2); non-color value aggregations (mean/min/max-as-data, size) remain unmodeled | **Major → residual Moderate** | confirmed, largely addressed |
| F6 | Colormap normalization domain across pyramid levels is unspecified → brightness flicker on zoom | **Major** | plausible |
| F7 | Streaming into the pyramid is under-reconciled with multi-level structure + eviction | Moderate | confirmed |
| F8 | "One core, logically identical" collides with the per-backend implementation matrix | Moderate | confirmed |
| F9 | Pyramid storage cost ("~1.33×") undercounted for multi-trace / fine-level / multi-channel | Moderate | confirmed |
| F10 | "Plotly ~40–100 B/pt × 3 copies" stated as fact but unverified | Moderate (credibility) | confirmed |
| F11 | Arrow IPC deserialization robustness for served/multi-user apps | Minor (v1) | plausible |
| F12 | Positioning — the tile pyramid is framed as the differentiator but isn't novel | Minor (honesty) | confirmed |

---

## The three that actually change the plan

**F1 and F2 are not refinements — they are missing workstreams.** F1 is a whole
distribution engineering track that determines whether anyone can `pip install` this at
all; plotly.py's real-world complexity lives almost entirely here, not in rendering.
F2 is a missing *core capability* — filtering is not an edge case in analytics, it's the
main event, and the pyramid as designed cannot answer a filtered query. **F3** is the
one that most changes the *rendering* design: the tier heuristic and the "one draw call"
idealization are both wrong against real GPU limits. Everything else is correctness
detail or honesty.

---

## Detailed findings

### F1 — Packaging & distribution is unspecified. For Python-only, it's the highest risk. [Critical]
**Failure scenario.** `pip install <engine>` must deliver three separately-hard things:
(a) the **native Rust core** as prebuilt wheels across the matrix — manylinux (x86_64 +
aarch64), macOS (arm64 + x86_64), Windows — via a plain C-ABI `cdylib` built by
Hatchling, so the Python-version cross-product disappears without PyO3 or `abi3`; (b)
the compiled **JS/WebGL2 render client** as bundled static assets; (c) a **notebook
front-end integration** that injects that client
into an output cell and speaks the comm protocol. Miss one wheel and the user falls back
to a source build that needs a Rust toolchain — an instant adoption cliff, and the exact
friction that dogged early Rust-backed Python packages. The doc's §23 covers *runtime*
environments but nothing about *shipping the bits*.
**Fix.** Add a Distribution section: C-ABI platform wheels with a CI wheel matrix;
**`anywidget`** as the notebook client substrate (current standard — one implementation
works across Jupyter, Lab, VS Code, Colab, Marimo, and Reflex-style servers); explicit
asset bundling; **comm-protocol versioning** between the native core and the JS client
(they ship together but must fail loudly on mismatch); and a defined no-native-core
behavior (a clear, actionable ImportError naming the supported platforms — never a
silent quality or correctness change). This is bigger than any single rendering
decision.

### F2 — No filtering / selection / linked-brushing; the pyramid is stale under any filter. [Critical]
**Failure scenario.** The user filters (`df[df.region=="US"]`) or box-selects a region to
cross-filter a second chart. The precomputed Tier-2/3 pyramid holds *unfiltered* counts
and physically cannot answer the filtered query — it would show the wrong density.
§28's LOD contract has no filter path at all. Research (§3d of the findings) confirmed
datashader deliberately re-aggregates on every interaction precisely because a fixed
pyramid can't absorb dynamic predicates.
**Fix.** Define a filter model with three tiers of its own: (1) **indexed range
predicates** → prune/clip tiles via zone maps (§22), cheap; (2) **arbitrary predicates**
→ fast re-bin of the *visible window only* in the native SIMD core; (3) **linked brushing
across views** → adopt the **Falcon/Mosaic summed-area active-dimension cube** (research
steal #1): brush = difference of cumulative sums, **O(1) passive-view updates, index size
∝ bins not rows**. This closes both the functional gap and the stale-pyramid tradeoff,
and it's the single highest-value technique the research surfaced.

### F3 — GPU ceilings mis-modeled: fill-rate and the 1 GB cap, not vertex count. [Major]
**Failure scenario.** Two concrete ways "Tier 0 ≤ 1–2M points, one instanced draw"
breaks: (a) **allocation** — 100M f32 x/y is 800 MB in one buffer, at Chrome's documented
**~1 GB single-allocation cap**; add color/size and buffer *creation* crashes (deck.gl
documents crashes between 10M–100M for exactly this). The "one draw call for N points"
is an idealization. (b) **Fill-rate** — 10M radius-5 points ≈ **1B fragment invocations
per frame** independent of vertex count; a *500k*-point scatter with large or overlapping
semi-transparent markers is fill-bound well below the "1–2M" vertex ceiling.
**Fix.** (i) The render core must **chunk vertex buffers** (multi-buffer draw) and state
that explicitly. (ii) Tier selection must be `f(point_count, mark_pixel_area × overdraw)`
— a dense large-marker scatter trips Tier-2 aggregation even at "sub-ceiling" counts.
The doc currently selects tiers on count alone.

### F4 — One viewport offset can't serve multiple traces at different magnitudes. [Major]
**Failure scenario.** Two traces on shared axes: one with values ~0, one ~1e12 (or a
dual-axis chart, or a map overlay + local inset). deck.gl re-bases f32 by a *single*
viewport origin; a single origin leaves the far trace with catastrophic f32 error.
§4/§16 assume one offset window per plot.
**Fix.** Per-trace (or per-axis) offset+scale resolved into **per-trace model matrices**;
the shared view transform stays f64 on CPU and composes with each trace's offset at
upload. Modest bookkeeping, but the doc doesn't have it and multi-trace is the norm.

### F5 — Tier-2 assumed a scalar density; the color algebra now ships. [Major → residual Moderate]
**Original failure scenario.** `scatter(x, y, color=category)` with 12 categories over
50M points: one count texture couldn't carry the colors, so the surface wore a count
colormap that matched neither the points nor the legend — a jarring recolor at every
density⇄points transition.
**Shipped fix (LOD doc §2).** The Tier-2 surface carries the **per-cell alpha-weighted
mean of the resolved point colors** (one law for continuous, categorical, and
direct-RGBA channels; linear-light integer pipeline, deterministic), with the
log-tone-mapped count as the alpha channel. The pyramid grew matching mean-color
planes (`build_color`/`compose_color`); the drill handoff became intensity-only
because hue is continuous by construction. `color_agg: "mean"` records the transform.
**Residual gap.** Aggregating *values as data* — per-cell mean/min/max of a channel
readable from hover/legend, per-category count planes for filtered queries
(imMens's ∏-bins), std, etc. — is still unmodeled; size channels still drop. Those
need the fuller algebra (count / sum / mean(2-ch) / min / max / categorical-by with
capped planes) mirroring datashader's `ds.by`/`ds.mean`, with its memory cost
(N× the tile, feeding F9) and a category cap that logs truncation.

### F6 — Colormap normalization across pyramid levels is unspecified → zoom flicker. [Major]
**Failure scenario.** Color maps bin-count→hue. Coarse tiles have higher counts than fine
ones, and the visible max varies per viewport. Normalize per-tile → visible seams;
normalize globally → a near-black screen when zoomed in (all local counts low). Either
way, **zoom visibly flickers brightness.** datashader recomputes `eq_hist` per view for
this reason.
**Fix.** Normalization domain = **per-view**: recompute min/max (or a histogram for
`eq_hist`/log) over the *composed visible tiles* each frame — O(visible tiles), cheap.
State this, and expose linear/log/eq_hist at composite time (which, per research, is
where datashader does it too — validating "colormap at composite" but not the domain).

### F7 — Streaming into the pyramid is under-reconciled. [Moderate]
**Failure scenario.** 100k pts/s appended. §28 says "incremental tile update for touched
cells," but an appended point touches one cell at *every* pyramid level, and ring-buffer
**eviction must decrement** expired points' bins across all levels — a count/sum tile can
`+=`/`-=`, but a **min/max tile cannot be decremented** (you can't un-see the old max),
and per-view normalization (F6) drifts as totals change.
**Fix.** `+=` on append and `-=` on eviction across all levels for count/sum; **min/max
tiles need periodic rebuild** over the retained window — state that limitation; re-derive
normalization each frame per F6.

### F8 — "One core, logically identical" vs the per-backend matrix. [Moderate]
**Failure scenario.** Tier-2 now has three implementations (WebGPU compute / WebGL2
additive-blend / worker SIMD), lines have two schools, precision has fallbacks. The
"logically identical across targets" guarantee (§21) actually spans backends × tiers ×
trace-kinds × fallbacks — and the places most likely to diverge (the fallbacks) are the
least likely to be tested if the oracle only checks the primary path.
**Fix.** Scope the consistency guarantee to **tier *outputs*** — the decimated/binned
aggregate buffers, which are backend-independent and can be asserted **bit-identical**
across WebGPU/WebGL2-blend/worker-SIMD — and test *pixels* per-backend against the CPU
reference. That makes the strong claim (identical aggregates) cheaply testable and
demotes the pixel claim to per-backend perceptual diff.

### F9 — Pyramid storage "~1.33×" undercounts multi-trace / fine-level / multi-channel. [Moderate]
**Failure scenario.** "~1.33× the finest level" is *per trace, single channel*. A
dashboard of 20 traces, each with a fine level sized to a 4K viewport, × the multi-channel
tiles from F5, is 20 × 1.33 × channels — not a rounding error. imMens noted dense tiles
reach "millions of values" even at low dimensionality.
**Fix.** Put pyramid storage under the §27 byte budget with eviction: keep the cheap
coarse levels resident, **LRU-evict fine levels** (rebuildable from canonical), and state
the multi-trace × multi-channel multiplier in the memory model.

### F10 — "Plotly ~40–100 B/pt × 3 copies" is stated as fact but unverified. [Moderate — credibility]
The research could not source this figure. It's directionally supported (input +
`calcdata` + GL/SVG buffers; plotly-resampler's **>10 GB → <700 MB ≈ 14×**) but the byte
number is an estimate. In a doc whose thesis is "every number has a test," publishing an
unmeasured competitor figure is a credibility liability.
**Fix.** Relabel as an estimate pending a heap-snapshot measurement (`scatter` vs
`scattergl` at 1M pts); lead with the defensible 14× resampler figure.

### F11 — Arrow IPC deserialization robustness for served apps. [Minor — v1]
**Failure scenario.** A server app (Dash/Reflex-style) or a shared kernel receives Arrow
buffers from clients, or renders user-uploaded files; malformed IPC (bad offsets/lengths)
must not crash or read out of bounds. Rust helps, but the IPC reader is an attack surface.
**Fix.** Fuzz the Arrow ingest path; treat all cross-boundary Arrow as untrusted;
bounds-check offsets. Note under the §29 server-app row.

### F12 — The tile pyramid is framed as the differentiator but isn't novel. [Minor — honesty]
Research: datashader's `render_tiles` already builds power-of-two 256² pyramids (offline),
and XYZ map tiles are the classic form. The genuine contribution is a **live, interactive**
pyramid — client-side compositing, re-bin below the floor, and (per F2) a filter-aware
Falcon index over it.
**Fix.** Reframe the contribution as *unifying live interaction with the pyramid + index*,
not inventing the pyramid. Protects credibility and sharpens the actual claim.

---

## Corrections to fold into the main design doc

- **New section — Distribution** (F1): C-ABI platform wheels, anywidget client, static
  asset bundling, comm versioning, no-wheel fallback.
- **New section — Filtering, selection & linked views** (F2): three-tier filter model +
  Falcon summed-area index. Update §28 to reference it.
- **§2 / §5** (F3): tier heuristic = `f(count, mark_area × overdraw)`; buffer chunking;
  fill-rate + 1 GB cap named as ceilings.
- **§4 / §16** (F4): per-trace offset/scale + per-trace model matrices.
- **§5** (F5, F6): aggregation algebra (count/sum/mean/min/max/categorical-by) and
  per-view normalization domain.
- **§27** (F9): pyramid storage under budget with LRU eviction; multi-trace/channel
  multiplier.
- **§21** (F8): consistency guarantee scoped to aggregate buffers (bit-identical) +
  per-backend pixel diffs.
- **§28** (F7): streaming +=/-= across levels; min/max rebuild caveat.
- **§1 / §2** (F10): relabel the Plotly byte figure as an estimate; lead with 14×.
- **§29** (F11): fuzz Arrow ingest; untrusted-buffer handling.
- **§5 framing** (F12): pyramid = unifying live interaction, not novel invention.

## Verdict

The design survives the round — nothing here refutes the core thesis (screen-bounded
cost via LOD + Arrow + GPU), and the research independently validated all six load-bearing
bets. But two genuine gaps (**distribution**, **filtering**) are missing workstreams, not
tweaks, and the rendering model needs to trade its idealized "one draw call, count-based
tiers" for the real GPU ceilings (**F3**). Fix those three and the plan is buildable; the
rest are correctness and honesty polish.
