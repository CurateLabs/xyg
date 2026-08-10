# Tier-3 Phase 4 — disk-resident tile spill roadmap

**Status:** design / not started. Phase-3 square pyramid is **productized**
on Python and Node ([lod-architecture.md](lod-architecture.md) §4 /
Phase 3; [tier3-testing.md](tier3-testing.md);
[xy-coverage.md](xy-coverage.md)).

**Tracking issue:** [#5](https://github.com/CurateLabs/graphforge-xy/issues/5)
(“Phase 4: Tier-3 disk-resident 256² tile spill”). In-repo pointer:
[`issues/phase4-tile-spill.md`](issues/phase4-tile-spill.md).

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
| Hosts | Python + Node bind `xy_pyramid_*` | Same hosts; new spill/fetch ABI |

## Goals (MUST)

1. **Rust owns spill/load** — tile residency, LRU, and compose-from-tiles live
   in `libxy_core` (extend `tiles.rs` / new `tile_store.rs`). Hosts stay thin.
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

## Work packages

### WP0 — Spec lock

- Finalize tile key `(level, tx, ty)`, on-disk layout (Arrow/Parquet row
  groups **or** fixed mmap slabs), and byte-budget knobs in
  `python/xy/config.py` / Node constants.
- Update [lod-architecture.md](lod-architecture.md) Phase 4 checklist items
  10+ with acceptance numbers.
- Link the tracking GitHub issue from this doc and `dual-host-parity.json`
  `lod_tiers[2].notes`.

### WP1 — Rust tile store ABI

- `xy_pyramid_spill` / `xy_tile_fetch` / `xy_tiles_compose` (names TBD) —
  bump `ABI_VERSION` in `src/lib.rs` **and** `python/xy/_native.py` together.
- LRU under `PYRAMID_RESIDENT_BYTES` (new config).
- Zone-map-pruned tile index for unordered scatter (dossier §32b).

### WP2 — Hosts

- Python: wire spill behind `no_rescan` / memmap / `n > PYRAMID_NO_RESCAN_ROWS`
  or an explicit `pyramid_spill=True`.
- Node: mirror in `packages/xy-node/src/pyramid.js`.
- First paint + `density_view` prefer spilled tiles when the resident pyramid
  would exceed budget.

### WP3 — Client (optional follow-on)

- Tile-keyed density cache in `js/src/45_lod.ts` (Phase-3 item 8) so pan
  reuses textures keyed by `(level, tx, ty)`.

### WP4 — Evidence

- Extend [tier3-testing.md](tier3-testing.md) with spill cases:
  - synthetic tile directory fixture (MBs, not TBs);
  - miss/hit counters;
  - compose still screen-bounded;
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
