# Tracked work: Phase 4 Tier-3 disk tile spill

> **GitHub Issues are currently disabled** on `CurateLabs/graphforge-xy`.
> This file is the in-repo stand-in for the Phase-4 tracking issue until Issues
> are enabled. When Issues are on, create the GitHub issue from this body and
> replace this note with `Tracked by #N`.

**Title:** Phase 4: Tier-3 disk-resident 256² tile spill

**Labels (suggested):** `enhancement`, `performance`, `tier-3`, `roadmap`

## Summary

Track **Phase-4** of the Tier-3 pyramid: spill/load of **256² data-space tiles**
under a byte budget so billion-scale / multi-trace pyramids stay interactive
without keeping the whole aggregate resident in RAM.

Phase-3 (in-RAM square pyramid + compose) is productized on Python and Node —
see `spec/design/tier3-testing.md`.

Authoritative roadmap: **`spec/design/tier3-phase4-roadmap.md`**.

## Why

| Phase 3 (shipped) | Phase 4 (this issue) |
| --- | --- |
| Whole pyramid in kernel RAM | LRU tile residency on disk |
| Compose from resident levels | Fetch only tiles intersecting the view |
| Memmap for **canonical** rows | Spill for **aggregate** tiles |

## Acceptance

- [ ] Rust tile store ABI (`spill` / `fetch` / `compose-from-tiles`); bump `ABI_VERSION` in Rust + `_native.py` together
- [ ] Python + Node thin hosts; §28 `binning` records tile path + hit/miss
- [ ] Resident bytes stay under configured budget; replies remain screen-bounded
- [ ] CI uses small tile fixtures — **never** allocate 1B points
- [ ] Update `dual-host-parity.json` `lod_tiers` Phase-4 cell to `ready` only when hosts land
- [ ] Optional follow-on: client tile-keyed cache in `js/src/45_lod.ts`

## Non-goals

- Replacing Phase-3 for traces that fit in RAM
- Browser-owned layout/LOD/encode
- Requiring Arrow ingest if a simpler mmap tile format ships first (document choice)

## References

- `spec/design/tier3-phase4-roadmap.md`
- `spec/design/lod-architecture.md` §4 / Phase 4
- `spec/design/tier3-testing.md`
- Dossier §27 / §28 / §32 / §32b
