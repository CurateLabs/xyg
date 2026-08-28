# Dual-host parity matrix

**Status:** living matrix for Python | Node architectural and surface parity
across the **entire product** (all chart types). Anchored to the three runtime
surfaces in [host-parity.md](host-parity.md) §0, the graph **render-graph**
mental model in [graph-mark.md](graph-mark.md) §1, and the placement rule in
[host-parity.md](host-parity.md) / [rust-engine.md](rust-engine.md) §1.

**Architecture principle:** GraphForge/canonical → Rust (layout, viewport,
graph LOD, edge LOD, encode, **render-graph emission**, and all other mark
decisions) → bounded §29 buffers → shared WebGL browser client (**paint only**).
Both hosts are thin loaders over the same `libxyg_core` C ABI; neither
reimplements LOD, force, or encode. The browser client never reimplements
layout/LOD/encode for the product path.

**Status values:** `ready` | `partial` | `missing` | `design` (spec locked;
runtime may still be landing).

---

## 0. Three runtime surfaces (not graph-only)

| Id | Surface | Path / artifact | Consumers | Owns | Must not |
| --- | --- | --- | --- | --- | --- |
| `python` | Python host | `python/xyg/` (+ `reflex_xy`) | Notebooks (**anywidget** / `show()`), **HTML export** (`to_html()`), **Reflex** | ctypes → Rust ABI; idiomatic Python ingest; transport attach | Parallel layout/LOD/encode decisions |
| `node` | Node host | `packages/xy-node` | **Server-side Node** and **VS Code extensions** (VS Code consumes Node bindings — not a separate stack). HTML export via `toHtml()` inlines `@curatelabs/xyg`, not the Python tree. | koffi → same Rust ABI; TypedArray ingest; embed/webview attach | Browser-only APIs (`window` / DOM / WebGL) |
| `browser` | Browser client | `js/src` → `@curatelabs/xyg` (`packages/xy-client/dist/{index,standalone}.js`); Python copies into `python/xyg/static/` | Shared renderer for every host | WebGL2 **paint / pick / gestures** on uploaded §29 buffers | Layout / LOD / encode product path; `koffi` / `node:fs` |

**Invariants**

- Same figure spec + §29 bytes across Python and Node for the same inputs;
  browser is the shared renderer.
- Notebook `show()` / anywidget / `to_html()` remain first-class and must not
  regress.
- Machine-readable twin: [`dual-host-parity.json`](dual-host-parity.json)
  `runtimes` section.

---

## 1. Pipeline-layer parity (must match across hosts)

| Layer | Python | Node | Shared artifact | Notes |
| --- | --- | --- | --- | --- |
| GraphForge / canonical ingest helpers | design / partial | design / partial | Same mark buffers | Optional; never the only path ([graph-fork-requirements.md](graph-fork-requirements.md) REQ-API-3) |
| Dense `u64` indices + f64 columns | required | required | Host→Rust pointers | No `u32` element identity |
| Layout (preset/grid/circle/force/…) | Rust ABI | Rust ABI | `xyg_graph_layout` / force handle | Seeded FR goldens bit-identical |
| Force ticks (progressive) | Host schedules | Host schedules | `xyg_graph_force_*`; configured CoSE descriptor | **Never browser main-thread decisions**; Rust owns CoSE options, pins, compounds, bounds, and Barnes–Hut/grid approximation |
| Viewport + graph LOD + edge LOD | Rust | Rust | `xyg_graph_lod_*` / cluster / sample | Recorded §28; Rust emits render graph |
| Encode → §29 f32 | Rust | Rust | Same binary payloads | Offset-encoded; no JSON numbers |
| Shared WebGL browser paint | shared client | shared client | `GLHost` (dossier §18) | Paint / pick / gestures only; no raw V/E past direct tier |
| Direct semantic graph Scene | canonical Scene | canonical Scene | `XYGG` → Rust style/legend/label/primitives → `XYGS` | Same final labels and paint render in WebGL, SVG, and native PNG; aggregate input omitted |

Complexity budgets (both hosts inherit the same Rust costs):

| Stage | Budget |
| --- | --- |
| Ingest | O(V+E) |
| Layout | approx (exact only when small) |
| LOD plan | O(V+E) |
| Interactive | ≈ O(visible) |
| GPU | ≈ O(screen) past direct tier |

---

## 2. Zoom / LOD parity (render-graph contract)

| Zoom band | What both hosts must ship | WebGL may see |
| --- | --- | --- |
| Far | Clusters / density + aggregate edges | Aggregate layers only |
| Mid | Reps + aggregate/sampled edges | Bounded reps + edges |
| Near / direct | Exact nodes/edges under budget | Per-element V/E **only** in this tier |

**Invariant:** past the direct-render tier, neither host may upload raw
topology for the GPU to “figure out.” Divergence here is a host-parity bug.
The browser client does not invent a second LOD plan in JS.

---

## 3. Mark / composition surface matrix

Graph and Sankey lead dual-host delivery; other kinds keep equal class
([host-parity.md](host-parity.md) REQ-HOSTPARITY-2). Fill runtime cells as
ABI and Node exports land; do not claim `ready` without a shared Rust path.

| Kind | Python | Node | Rust decisions | Parity evidence |
| --- | --- | --- | --- | --- |
| graph | ready | ready (`packages/xy-node` composition) | ready: layout, force, LOD, render-graph | `tests/test_graph_node_parity.py` circle goldens + dual-host force benches |
| sankey | ready (ribbon bands) | ready (`composeSankey` → ribbon) | layout in Rust | Layout + ribbon geometry parity |
| scatter | ready | ready (density tier + direct) | `xy_bin_2d` / `xy_density_log_u8` / encode | Node `coverage.test.mjs` density + encode goldens |
| line / area / hist / bar / column | ready | ready | M4 / hist / `xy_bar_stack` | `tests/test_node_mark_parity.py` |
| contour / errorbar / error_band / stem / step / stairs / triangle_mesh | ready | ready | marching squares + segment/mesh kernels | Node composers + `coverage.test.mjs` |
| radar / polar / pie / wind_rose / facet | ready | ready | bins + bar stack; facet host-only; ABI 133 polar Scene v26 line/scatter/area/bar/column/errorbar/heatmap/contour; ABI 134 HeatmapPainted intern; ABI 135 named colormap tables; ABI 136 product-kind packing; ABI 137 Cartesian density Image blit; ABI 138 constant dash XYDS; ABI 139 constant linecap XYLC; ABI 140 cartesian smooth-polyline flatten; ABI 141 cartesian smooth-area Band flatten; ABI 142 cartesian mean-color density; ABI 143 polar density PolyFill tessellation; ABI 144 cartesian error_band smooth BandFlatten plus polar identity-chord smooth; ABI 145 constant marker_path XYMP tessellation; ABI 146 constant mark-fill linear-gradient XYGR; ABI 147 XYPK product packing facts; ABI 148 XYAF annotation packing facts; ABI 149 XYHF heatmap/density paint-fact packing; ABI 150 XYSS extras packing; ABI 151 Scene density grid packing; ABI 152 XYEP packing from XYEF; ABI 153 XYCF figure-chrome packing; ABI 154 XYTC per-trace compile packing; ABI 155 XYTA heatmap/density attach packing; ABI 156 XYCL product-row packing; ABI 157 XYSD trace-sidecar packing; ABI 158 XYSS style-sidecar packing; ABI 159 XYAS annotation splice packing; ABI 160 XYAS/XYCC assembled encode; ABI 161 XYSD chrome/extras packing; ABI 162 XYAS/XYCF assembled encode from sidecars; ABI 163 product encode from packed facts; ABI 164 public static-export consumers; ABI 165 product-path XYFS support; ABI 166 cartesian bar/column/histogram corner_radius tessellation; ABI 167 polar wedge_gap tessellation; ABI 168 polar bar/column/histogram corner_radius tessellation; ABI 169 polar curve=smooth plus step; ABI 170 constant marker_glyph XYMG; ABI 171 width-only scatter match-fill; ABI 172 cartesian line step+smooth; ABI 173 heatmap corner_radius tessellation; ABI 174 violin/box corner_radius tessellation; ABI 175 violin/box fill/stroke opacity; ABI 176 bar/column/histogram fill/stroke opacity, ABI 177 heatmap fill_opacity, ABI 178 scatter fill/stroke opacity, ABI 179 hexbin fill_opacity, ABI 180 triangle_mesh fill/stroke opacity, ABI 181 cartesian area/error_band step+smooth, ABI 182 triangle_mesh joined_fill, ABI 183 constant ribbon color2_ch XYGR; ABI 184 cartesian unwrapped text dx/dy/anchor XYAW; ABI 185 labelled cartesian marker dx/dy/anchor XYAW; ABI 186 cartesian colormap hexbin XYHP; ABI 187 cartesian unwrapped text rotation XYAW; ABI 188 labelled cartesian marker rotation XYAW | Node `marks/polar.js` / `radar.js`; coords+theta/r; `tests/test_polar_scene.py` |
| box / violin / ecdf / hexbin / heatmap / ribbon | ready | ready (heatmap categorical axes partial) | box/violin/hexbin/heatmap kernels; exact + ABI100 binned ECDF; ABI 102 hexbin ingress; ABI 103–104 Rust hex-cell/heatmap/segment/triangle Scene expansion; ABI 105 XYEP public-export predicate; ABI 106 XYAR autorange; ABI 107 XYMS mark styles; ABI 108 XYCH chrome; ABI 109 row packing; ABI 110 XYLG legend; ABI 111 XYCB colorbar; ABI 112 XYAD annotations; ABI 113 SVG→PDF; ABI 114 JPEG/WebP encode; ABI 115 PNG encode; ABI 116 annotation mark expansion; ABI 117–118 XYFS figure-compile support including per-trace allowlists; ABI 119 mark ingress (sort/edges/levels/hex groups); ABI 120 loc=best occupancy; ABI 121 ribbon/curve/rounded-rect tessellation; ABI 122 payload LOD/mask; ABI 123 tick-label collision; ABI 124 legend box packing; ABI 125 text-block measure and cartesian axis rooms; ABI 126 static-export padding/colorbar/polar recut; ABI 127 pyplot tight-layout grid solve; ABI 128 authored tick-window resolve/filter; ABI 130 tick-label formatting; ABI 131 polar projection; ABI 132 density emit policy; ABI 129 Cartesian static-export grid colormap; ABI 133 polar Scene v26 XYPL compile | Node marks + cross-host Scene goldens |

**LOD utilization (all surfaces):** Tier-1 direct + Tier-2 density/aggregate/render-graph
are ready on Python and Node. **Tier-3 Phase-3 pyramid** (build + compose) and
**Phase-4 disk tile spill** (WP1 ABI + WP2 host engagement) are ready on both
hosts with §28 `binning: pyramid-L*` / `pyramid-L*-tiles`. Optional client tile
cache (#10) and WP4 evidence (#11) remain. Testing contract:
[`tier3-testing.md`](tier3-testing.md).
Scale evidence uses screen-bounded compose + LOD decisions (10M / 100M / 1B),
not raw billion-point allocation in CI. See [`xy-coverage.md`](xy-coverage.md).

Update this table in the same change that lands a Node export or Rust
decision path. The machine-readable twin is
[`dual-host-parity.json`](dual-host-parity.json) (mark kinds with
python/node/rust status + `runtimes` + `lod_tiers`). Soft dual-host force/render benches live
under `benchmarks/bench_dual_host_graph*.{py,mjs}` and `//:perf_parity_test`.
Scale-class LOD evidence (10M / 100M / 1B) ships in
`benchmarks/bench_scale_all_charts.py` (every profile),
`benchmarks/bench_scale_all_charts_node.mjs`, and
`benchmarks/bench_graph_scale_classes_node.mjs`.
This markdown remains the authoritative architecture view; keep the JSON in
lockstep.

---

## 4. Explicit non-parity (allowed differences)

| Allowed to differ | Must not differ |
| --- | --- |
| Idiomatic ingest (NumPy/pandas vs TypedArrays) | LOD tier / render-graph for the same inputs |
| Error *message* text | §29 buffer bytes for the same figure |
| Transport attach (comm vs embed vs VS Code webview) | Force positions for the same seed/ticks |
| Public helper names’ packaging | Shared WebGL paint semantics |
| Host process model (CPython vs Node vs extension host) | Three-surface taxonomy (no fourth engine stack) |

---

## 5. References

- [host-parity.md](host-parity.md) §0 — three runtime surfaces; REQ-HOSTPARITY-*
- [graph-mark.md](graph-mark.md) §1 — pipeline, budgets, zoom, force, `GLHost`
- [rust-engine.md](rust-engine.md) §1 — Rust owns graph LOD / render-graph
- Design dossier §18 — shared WebGL host / governor fallback
- [renderer-architecture.md](renderer-architecture.md) — mark registry + paint
- `packages/xy-node/README.md` — Node host package notes
