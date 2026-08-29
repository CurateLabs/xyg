# M2 leftover clusters

Post-close M2 follow-on parents [#271](https://github.com/CurateLabs/xyg/issues/271)-[#283](https://github.com/CurateLabs/xyg/issues/283)
were too large to close: each leftover ABI admit left the parent open.
This file is the closeable cluster inventory.

Inventory after draft PR https://github.com/curatelabs/xyg/pull/286 HEAD ABI 188 (`c722fa4e`). Related: #24, #58, #59, tracker #54.

In-repo pointer: [`issues/m2-leftover-clusters.md`](../design/issues/m2-leftover-clusters.md).
Create/refresh GitHub sub-issues with `python3 scripts/m2_leftover_clusters.py`.

## Landing contract

- One leftover cluster per pull request.
- Do not stack further ABI slices onto [PR #286](https://github.com/curatelabs/xyg/pull/286).
- Wait until the **current HEAD** required checks are green (Test, WASM
  foundation, Python 3.11 floor) before the next push on the same ref.
- Close the **child** when that leftover is Scene-owned with differentials,
  or when spec+tests record it as a bounded fail-closed contract.
- Close the **parent** only when every child is closed.
- **Delete Python only after** Rust owns the path **and** differential proof
  is green.

## Cluster table

| Key | Parent | Also blocks | P | Issue | Title |
| --- | --- | --- | --- | --- | --- |
| `271-predicates` | #271 | — | P0 | [#287](https://github.com/CurateLabs/xyg/issues/287) | [M2 follow-on][P0][#271] Remaining Scene eligibility predicates in `_scene_v3.py` |
| `272-css` | #272 | #273, #275 | P0 | [#288](https://github.com/CurateLabs/xyg/issues/288) | [M2 follow-on][P0][#272] Custom fonts / CSS / classes Scene contract |
| `272-var-gradients` | #272 | #273 | P0 | [#289](https://github.com/CurateLabs/xyg/issues/289) | [M2 follow-on][P0][#272] Unresolved `var()` / theme CSS gradients |
| `272-ribbon-color2` | #272 | #273 | P0 | [#290](https://github.com/CurateLabs/xyg/issues/290) | [M2 follow-on][P0][#272] Per-item two-ended ribbon `color2_ch` |
| `272-marker-glyph` | #272 | #273 | P0 | [#291](https://github.com/CurateLabs/xyg/issues/291) | [M2 follow-on][P0][#272] Multi-character `marker_glyph` |
| `272-polar-heatmap` | #272 | #273 | P0 | [#292](https://github.com/CurateLabs/xyg/issues/292) | [M2 follow-on][P0][#272] Polar heatmap inverse-raster |
| `272-heatmap-hexbin-stroke` | #272 | #273 | P0 | [#293](https://github.com/CurateLabs/xyg/issues/293) | [M2 follow-on][P0][#272] Heatmap/hexbin `stroke_opacity` |
| `272-polar-hexbin` | #272 | #273 | P0 | [#294](https://github.com/CurateLabs/xyg/issues/294) | [M2 follow-on][P0][#272] Polar hexbin / custom reducers / categorical `direct_rgba` |
| `272-mesh-role` | #272 | #273 | P0 | [#295](https://github.com/CurateLabs/xyg/issues/295) | [M2 follow-on][P0][#272] Triangle-mesh custom `role` / per-item color/stroke |
| `272-scatter-per-item` | #272 | #273 | P0 | [#296](https://github.com/CurateLabs/xyg/issues/296) | [M2 follow-on][P0][#272] Scatter per-item stroke / width / opacity arrays |
| `275-css-room` | #275 | — | P1 | [#297](https://github.com/CurateLabs/xyg/issues/297) | [M2 follow-on][P1][#275] CSS-room / custom font measurement leftovers |
| `275-legendfit` | #275 | — | P1 | [#298](https://github.com/CurateLabs/xyg/issues/298) | [M2 follow-on][P1][#275] Remaining `_legendfit.py` / legend box leftovers |
| `275-tight-layout` | #275 | — | P1 | [#299](https://github.com/CurateLabs/xyg/issues/299) | [M2 follow-on][P1][#275] Remaining tight-layout / padding / polar recut leftovers |
| `276-authored` | #276 | — | P1 | [#300](https://github.com/CurateLabs/xyg/issues/300) | [M2 follow-on][P1][#276] Authored tick filtering and authored labels |
| `276-minors` | #276 | — | P1 | [#301](https://github.com/CurateLabs/xyg/issues/301) | [M2 follow-on][P1][#276] Minor ticks |
| `276-polar-secondary` | #276 | — | P1 | [#302](https://github.com/CurateLabs/xyg/issues/302) | [M2 follow-on][P1][#276] Polar / secondary axis ticks |
| `276-rich-formats` | #276 | — | P1 | [#303](https://github.com/CurateLabs/xyg/issues/303) | [M2 follow-on][P1][#276] Rich tick formats |
| `276-collision` | #276 | — | P1 | [#304](https://github.com/CurateLabs/xyg/issues/304) | [M2 follow-on][P1][#276] Tick collision / `tick_label_strategy` |
| `278-html` | #278 | — | P1 | [#305](https://github.com/CurateLabs/xyg/issues/305) | [M2 follow-on][P1][#278] Annotation `html` |
| `278-class-name` | #278 | #272 | P1 | [#306](https://github.com/CurateLabs/xyg/issues/306) | [M2 follow-on][P1][#278] Annotation `class_name` |
| `278-collision` | #278 | — | P1 | [#307](https://github.com/CurateLabs/xyg/issues/307) | [M2 follow-on][P1][#278] Annotation collision |
| `278-markup` | #278 | — | P1 | [#308](https://github.com/CurateLabs/xyg/issues/308) | [M2 follow-on][P1][#278] Annotation markup |
| `278-typography` | #278 | #275 | P1 | [#309](https://github.com/CurateLabs/xyg/issues/309) | [M2 follow-on][P1][#278] Annotation custom typography |
| `279-compat-geometry` | #279 | — | P1 | [#310](https://github.com/CurateLabs/xyg/issues/310) | [M2 follow-on][P1][#279] Compatibility emitters still call `_scene.py` geometry |
| `282-m4` | #282 | — | P1 | [#311](https://github.com/CurateLabs/xyg/issues/311) | [M2 follow-on][P1][#282] Remaining `_m4_decimate` policy |
| `282-emit` | #282 | — | P1 | [#312](https://github.com/CurateLabs/xyg/issues/312) | [M2 follow-on][P1][#282] Remaining `_payload._emit_*` sampling / density / masks |
| `283-paint` | #283 | — | P2 | [#313](https://github.com/CurateLabs/xyg/issues/313) | [M2 follow-on][P2][#283] Remaining LUT / `_paint.py` / `_trace_paint_rgba` policy (closed via ABI 206 / PR #341). Remaining parent work: polar heatmap gather-after-inverse map (ABI 207). |

## Parents

| Parent | Role |
| --- | --- |
| #271 | Figure→Scene ingress / export predicate. Remaining product policy in `_scene_v3.py` predicates, not thin packing. |
| #272 | Scene-eligible `to_svg`. Children also block #273. |
| #273 | Scene-eligible PNG/RGBA. No unique children; closes when #272 children close with raster differentials. |
| #275 | Rust layout / `_svg._*room` / `_legendfit.py`. |
| #276 | Remaining tick/format policy after PR #284 adapter retirement. |
| #278 | Remaining annotation exceptions after ABI 184-188 (`dx`/`dy`/`anchor`/`rotation` already landed on #286). |
| #279 | Compatibility `_scene.py` geometry wrappers over ABI 121. |
| #282 | Live `_payload.py` LOD/emit leftovers over ABI 122/132. |
| #283 | P2 paint/colormap leftovers. Do not block P0/P1. |
