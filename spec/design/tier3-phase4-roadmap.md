# Tier-3 Phase 4 — disk-resident tile spill roadmap

**Status:** design **locked** (WP0 complete); WP1 Rust tile store **landed**
(ABI 73: `xyg_pyramid_spill` / `xyg_tile_store_*` in `crates/xyg-engine` +
`crates/xyg-core`). Host engagement is WP2. Phase-3 square pyramid is **productized**
on Python and Node ([lod-architecture.md](lod-architecture.md) §4 /
Phase 3; [tier3-testing.md](tier3-testing.md);
[xy-coverage.md](xy-coverage.md)). Note the shipped Phase-3 pyramid is
**not tiled** — `crates/xyg-engine/src/tiles.rs` stores one contiguous grid per level — so
Phase 4 is a storage-layout change, not a residency wrapper.

**Tracking issue:** [#5](https://github.com/CurateLabs/xyg/issues/5)
(“Phase 4: Tier-3 disk-resident 256² tile spill”); sub-issues
[#7](https://github.com/CurateLabs/xyg/issues/7) (WP0) ·
[#8](https://github.com/CurateLabs/xyg/issues/8) (WP1) ·
[#9](https://github.com/CurateLabs/xyg/issues/9) (WP2) ·
[#10](https://github.com/CurateLabs/xyg/issues/10) (WP3) ·
[#11](https://github.com/CurateLabs/xyg/issues/11) (WP4). In-repo
pointer: [`issues/phase4-tile-spill.md`](issues/phase4-tile-spill.md).

**Sequencing overlay:** WP1 (#8) re-landed in `crates/xyg-engine` after the
crate split ([#18](https://github.com/CurateLabs/xyg/issues/18)); draft PR #19
is superseded. Canonical f64 columns / `stream.rs` are
[#22](https://github.com/CurateLabs/xyg/issues/22), not this spill store.
Cross-cutting host/identity/client plan:
[host-neutral-architecture.md](host-neutral-architecture.md) / #24.

## Why Phase 4

Phase 3 keeps the **whole pyramid resident in kernel RAM** (≈1.33× finest
level). That is enough for interactive compose at tens–hundreds of millions
of points when rows are memmap’d and only the density grid ships. At
**~1B colored points** (or multi-trace apps sharing RAM), the pyramid itself
must spill:

| Concern | Phase 3 (shipped) | Phase 4 (this roadmap) |
| --- | --- | --- |
| Aggregate storage | Whole square pyramid in RAM | 256² **data-space tiles** under a byte budget |
| Pan | Re-compose from resident levels | Fetch only newly exposed tiles; reuse LRU |
| Zoom | Level pick + compose | Adjacent-level tile set + optional crossfade |
| Deep zoom | Spatial index / exact re-bin | Unchanged companion (`_spatial`) |
| Hosts | Python + Node bind `xyg_pyramid_*` | Same hosts; new spill/fetch ABI |

## Goals (MUST)

1. **Rust owns spill/load** — tile residency, LRU, and compose-from-tiles live
   in `libxyg_core` (extend `tiles.rs` / new `tile_store.rs`). Hosts stay thin.
2. **Screen-bounded replies** — at most ~ceil(w/256+1)×ceil(h/256+1) tiles
   contribute to a frame; client never holds more than screen-bounded textures.
3. **§28 recording** — every reply records `binning: "pyramid-L<l>-tiles"`
   (or equivalent) plus residency stats (tiles hit / miss / bytes).
4. **Dual-host parity** — Python and Node expose the same build/fetch/compose
   surface; browser remains paint-only.
5. **Append policy** — count-only pyramids may dirty-tile rebuild; colored
   pyramids continue to refuse incremental color append (invalidate + rebuild),
   or gain an explicit color-append ABI if designed.

## Non-goals

- Replacing Phase-3 compose for traces that fit in RAM (keep hot path).
- Browser-side layout/LOD/encode.
- Allocating 1B points in CI to “prove” spill (see testing below).
- Shipping Arrow/Parquet ingest as a hard dependency of the first spill MVP
  if a simpler mmap tile format lands first — document the format choice.

## Locked decisions (WP0 — [#7](https://github.com/CurateLabs/graphforge-xy/issues/7))

Every decision below is the authoritative record (§28 culture: recorded,
never silent). Dossier-level summary: design-dossier.md §32b. WP1–WP4 build
inside this frame; changing any of it means editing this section first.

### D1 — Tile key and on-disk layout: fixed mmap slabs

- **Key:** `(level, tx, ty)` — level 0 is the coarsest (1 tile), level *l*
  has up to `ceil(dim_l/256)²` tiles over the pyramid’s square level grids.
- **Layout:** one spill file per pyramid. Fixed header (magic `XYTS`,
  format version u32, base dim, level count, plane flags), then a dense
  count region and — for colored pyramids — a dense color region, each
  ordered coarsest level first, row-major `(ty, tx)` within a level. Every
  slab is a fixed 256²-cell block (count: 256 KiB of u32; color: 512 KiB of
  `[u16; 4]`); levels smaller than 256² store one zero-padded slab. Fixed
  slabs make every offset closed-form arithmetic — no per-tile directory
  lookup on the read path — and 4 KiB pages divide the slab size, so mmap
  reads stay page-aligned. Values are native-endian: the file is a
  **per-process rebuildable cache** (§27), never an interchange format, with
  the same lifecycle as `xy._ooc` canonical memmaps (process-scoped temp,
  deleted on free/exit).
- **Why not Arrow/Parquet (MVP):** the win Arrow buys (interchange,
  schema evolution, ecosystem readers) is worth nothing for a file that
  never leaves the process and can always be discarded and rebuilt; the
  costs are real — a large crate tree in a repo that must vendor every
  crate (rust-engine.md dependency policy; crates.io is unreachable from
  the dev sandbox), plus decode work on a path whose §29 culture is
  memcpy-shaped I/O. The roadmap non-goal above already permits this.
- **Migration note:** the header’s magic + version byte is the whole
  migration story — a future Arrow/Parquet store replaces the format at a
  version bump with zero compatibility work, because no spill file ever
  outlives its process. Revisit if measurements show a need (e.g. HTTP
  range-request serving of tiles, dossier §29, where an interchange format
  starts paying for itself).

### D2 — Byte-budget knob: `PYRAMID_RESIDENT_BYTES`

- **Name/default:** `PYRAMID_RESIDENT_BYTES = 512 * 2**20` (512 MiB) in
  `python/xyg/config.py`, mirrored in the Node constants
  (`packages/xy-node/src/pyramid.js` exports, like the four existing
  `PYRAMID_*` knobs). Scope is **process-wide across all pyramids** —
  the motivating cliff is multi-trace apps sharing RAM, so a per-pyramid
  budget would multiply exactly like the problem it solves.
- **Why 512 MiB:** a default-base (2048²) colored pyramid is ~67 MB
  resident, so ordinary traces — even several — never spill and the
  Phase-3 hot path is untouched; an adaptive 16 384² base (~1.4 GB counts
  + ~2.9 GB color) must spill, which is the point.
- **Accounting (dossier §27):** `pyramid_report_bytes` — the
  `memory_report()["pyramid_bytes"]` line — reports **all** RAM-resident
  tile bytes plus tile-directory/index metadata, whether or not the
  pyramid has spilled. On-disk bytes report separately as
  `pyramid_spilled_bytes` (disk-backed, reclaimable), mirroring the
  `canonical_bytes` / `canonical_mapped_bytes` split of §27 rule 5.

### D3 — Eviction: LRU with frame pinning

- **Unit:** whole tiles — a tile’s count and color slabs evict together
  (compose-color needs both; split residency would double bookkeeping to
  save at most the color plane of a tile about to be refetched).
- **Pinning:** the ≤ ceil(w/256+1) × ceil(h/256+1) tiles of the level
  serving the current compose are pinned for the duration of the call and
  left most-recently-used afterward, so an immediate pan re-fetches only
  newly exposed edge tiles. Nothing else is pinned; the previous frame’s
  set competes in LRU order like everything else.
- **Working set > budget:** a frame never fails and never livelocks. The
  effective budget floors at the pinned working set (compose proceeds),
  the reply records the condition (`over_budget: true` in the §28 tile
  stats, below), and eviction returns residency to the configured budget
  as soon as the pins release. Degrading to a coarser level is *not* done
  implicitly — the working set is screen-bounded (~12 tiles ≈ 3–9 MB), so
  exceeding the budget with pins alone means a pathological configuration,
  and silently changing the served level would be a §28 violation.
- **§28 recording:** every tile-served reply carries
  `binning: "pyramid-L<l>-tiles[-upsampled]"` plus
  `tiles: {hit, miss, resident_bytes, spilled_bytes, budget_bytes,
  over_budget}`.

### D4 — Append and domain-growth policy

- **Count-only pyramids:** an in-domain append marks the intersecting
  tiles dirty per level (a batch touching one region dirties ~1 tile per
  level) and rebuilds them lazily on next fetch/compose; the composed
  result must equal a from-scratch rebuild bit-for-bit (WP4 golden).
- **Colored pyramids:** refuse-and-rebuild stands, spilled or not — the
  Phase-3 rationale (append colors unknown to the count path; domain
  motion re-colors already-binned points) is unchanged by residency. No
  color-append ABI in Phase 4; designing one is out of scope and would
  re-enter through this section.
- **Domain growth:** an append outside the pyramid’s original x/y domain
  invalidates the **whole store** — RAM tiles, spill file, and tile index
  — because a grown domain re-keys every `(level, tx, ty)`; partial reuse
  is impossible by construction. Rebuild is lazy (next density view), as
  today.

### D5 — Zone-map-pruned tile index (companion, not replacement)

- Dirty-tile rebuilds (D4) and below-floor re-bins locate rows through the
  **existing** §22 chunk zone maps: `xy_zone_maps_pair` per-chunk x/y
  min/max prune the candidate ~64k-row chunks intersecting a tile’s
  data-space rect, and only those chunks are scanned. No new ingest-time
  sort or bucketing pass is added for the MVP — the index is O(chunks)
  metadata that already exists and is already counted.
- Where a trace carries `_spatial.SpatialIndex` (the shipped osm-sort cell
  grid, dossier §32b), it serves as the finer row locator for the same
  queries. It remains a **companion**: position-only, gated as today
  (constant-styled traces, deep-zoom regime) — the zone-map path is the
  always-available baseline.
- Rejected for the MVP: a mandatory per-row spatial sort at ingest —
  it duplicates `SpatialIndex`, taxes every ingest to benefit only the
  spilled minority, and zone-map pruning already bounds rebuild scans to
  O(chunks touching the tile).

### D6 — Filter/legend interaction (§34): staleness impossible by construction

- The tile store holds **unfiltered** aggregates only, exactly like the
  Phase-3 in-RAM pyramid. A trace with any active predicate (legend mask,
  filter) bypasses compose-from-tiles entirely and is served by the exact
  re-bin path (`binning` tagged `-masked`), and **filtered results are
  never written to the store**. There is therefore no filter-invalidation
  bookkeeping to get wrong: a spilled tile cannot serve stale filtered
  counts because filtered counts never reach disk. WP4 must still test
  the negative path (predicate change ⇒ no tile-served reply).
- Data changes invalidate per D4; predicate changes invalidate nothing
  because they never read the store.

### D7 — Nonlinear axes: excluded, recorded

- Traces on log/symlog axes skip pyramid build/compose (dossier §28
  nonlinear-axes rules — the record now names the tile store explicitly),
  so they never engage spill: no pyramid, nothing to spill. They keep the
  exact scan path at every scale, cost accepted and recorded in §28.

## Work packages

### WP0 — Spec lock ([#7](https://github.com/CurateLabs/graphforge-xy/issues/7))

- [x] Finalize tile key `(level, tx, ty)`, on-disk layout (fixed mmap slabs;
  Arrow/Parquet deferred with a migration note), and the
  `PYRAMID_RESIDENT_BYTES` byte-budget knob for `python/xyg/config.py` /
  Node constants → locked decisions D1–D2 above.
- [x] Eviction/pinning semantics, append + domain-growth policy, zone-map
  tile index, filter/legend rule, nonlinear-axes exclusion → D3–D7 above.
- [x] Update [lod-architecture.md](lod-architecture.md) Phase 4 checklist
  items 10–12 with acceptance numbers.
- [x] Link the tracking GitHub issue and sub-issues from this doc and
  `dual-host-parity.json` `lod_tiers[2].notes`.
- [x] Fix the spec debt found in review: phantom “§32b” citations (dossier
  §32b now exists), dossier §32 “Python-only” framing, lod-architecture
  §4.1 tiled-vs-shipped ambiguity, parity-JSON Phase-4 scoping.

### WP1 — Rust tile store ABI ([#8](https://github.com/CurateLabs/xyg/issues/8))

- [x] `xyg_pyramid_spill` / `xyg_tile_store_fetch` / `xyg_tile_store_compose` /
  `_compose_color` / `_append` / `_stats` / `xyg_tile_budget_set` /
  `xyg_tile_store_free` — ABI 73 in `crates/xyg-core`; regenerate via
  `python3 scripts/gen_abi_manifest.py --write`; `scripts/abi_smoke.py` covers
  spill→fetch→compose goldens.
- [x] LRU under process-wide `PYRAMID_RESIDENT_BYTES` default (512 MiB) per D2–D3;
  frame pinning + `over_budget` recording; spill file is `XYTS` fixed slabs
  (pread/pwrite realization of D1 mmap layout — no mmap crate vendored).
- [x] Compose-from-tiles shares `LevelView` / `compose_level` with in-RAM compose
  (bit-identical). Count-only dirty-tile append; colored refuse; domain growth
  refused atomically.
- [ ] Zone-map-pruned tile index for unordered scatter (D5) — companion path;
  MVP uses closed-form slab offsets; zone-map rebuild wiring remains available
  via existing `xyg_zone_maps_*` for WP2/WP4 dirty rebuilds.

### WP2 — Hosts ([#9](https://github.com/CurateLabs/graphforge-xy/issues/9))

- Python: wire spill behind `no_rescan` / memmap / `n > PYRAMID_NO_RESCAN_ROWS`
  or an explicit `pyramid_spill=True`.
- Node: mirror in `packages/xy-node/src/pyramid.js`.
- First paint + `density_view` prefer spilled tiles when the resident pyramid
  would exceed budget.

### WP3 — Client (optional follow-on, [#10](https://github.com/CurateLabs/graphforge-xy/issues/10))

- Tile-keyed density cache in `js/src/45_lod.ts` (Phase-3 item 8) so pan
  reuses textures keyed by `(level, tx, ty)`.

### WP4 — Evidence ([#11](https://github.com/CurateLabs/graphforge-xy/issues/11))

- Extend [tier3-testing.md](tier3-testing.md) with spill cases:
  - synthetic tile directory fixture (MBs, not TBs);
  - miss/hit counters;
  - compose still screen-bounded;
  - tiled compose golden against in-RAM compose (bit-identical counts);
  - dirty-tile append equals from-scratch rebuild (D4);
  - stale-filter negative path: predicate change ⇒ no tile-served reply (D6);
  - never allocate 1B rows in CI.
- Soft latency gate on a dedicated runner / CodSpeed job (dossier item 9).

## Exit criteria

- [ ] Colored 100M–class scatter pans without blanking; mean-color tiles match
      oracle within recorded u16 quantization.
- [ ] Resident tile bytes stay under configured budget while canonical rows
      may remain memmap’d.
- [ ] Python ↔ Node golden for the same spilled figure inputs.
- [ ] Specs + `dual-host-parity.json` mark Phase-4 `ready` only when WP1–WP2
      land; client tile cache may stay `partial`.

## References

- [lod-architecture.md](lod-architecture.md) §4.1–4.4, Phase 3–4
- [tier3-testing.md](tier3-testing.md)
- [xy-coverage.md](xy-coverage.md)
- [host-parity.md](host-parity.md) — three runtime surfaces
- Dossier §27 (rebuildable caches), §28 (recorded decisions), §32 / §32b
