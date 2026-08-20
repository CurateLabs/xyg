# Tier-3 pyramid — testing best practices

**Status:** product testing contract for the Phase-3 Tier-3 pyramid
([lod-architecture.md](lod-architecture.md) §4 / Phase 3 items 6–7).

The shippable product is the **square multi-resolution count pyramid**
(`xyg_pyramid_build` → `compose` / `count` / `append` / `free`), available on
Python and Node, with §28 `binning: "pyramid-L<l>[-upsampled]"`. Phase-4
disk-resident 256² tile spill is a separate residency milestone: Rust ABI WP1
is landed; host engagement is **not**
required to claim Phase-3 Tier-3 ready.

## What “scale” means in CI

| Claim | How to test | What not to do |
| --- | --- | --- |
| Compose is screen-bounded | Build once at N ≤ ~2M; compose many windows of ≤ screen cells | Allocate 100M–1B points |
| Cost is O(grid), not O(N) | Same pyramid, increase N only if comparing *build*; compose timing must not track N | Time a full `bin_2d` of 1B |
| LOD class 10M/100M/1B | Call `pyramid_count` / `lodPlan` / graph LOD with large **integers** | Materialize those row counts |
| Memmap / OOC | Small memmap fixture (MBs); assert `binning` starts with `pyramid-L` | Require a 100 GB dataset in CI |
| Count conservation | `sum(compose full window) == N` (±float) | Visual-only checks |

## Test layers (required)

### 1. ABI / kernel goldens (always on)

- Rust `crates/xyg-engine/src/tiles.rs` unit tests — level conservation, append atomicity, colored refuse-append, outresolve.
- `scripts/abi_smoke.py` — ctypes boundary for every `xyg_pyramid_*`.
- Python `tests/test_kernels.py` — wrapper validation; compose mass ≡ `bin_2d`.
- Node `packages/xy-node/test/pyramid.test.mjs` — same goldens via koffi.

### 2. Host product path

- **Python first paint:** `n ≥ PYRAMID_MIN_POINTS` linear scatter → density
  carries `binning: pyramid-L*` (`_payload._density_trace_spec`).
- **Python interactive:** `interaction.density_view` (existing).
- **Node:** `Figure` density emit uses `PyramidCache` + `densityViewFromPyramid`
  at/above `PYRAMID_MIN_POINTS` or `forcePyramid`.
- Assert `reduction: "pyramid-count"` and `tier: "density"`.

### 3. Out-of-core without huge data

- `tests/test_ooc.py`: memmap ingest + density; extend to assert pyramid
  binning when `n ≥ PYRAMID_MIN_POINTS` over a memmap-backed column.
- Node: force pyramid on modest TypedArrays; optional memmap via
  `fs`/`mmap` is host-specific and not required for the ABI claim.

### 4. Scale evidence harness (soft latency, hard structure)

- `benchmarks/bench_tier3_pyramid.py` / `benchmarks/bench_tier3_pyramid_node.mjs`
  - Build at CI size (default 1_000_000).
  - Compose ≥ 32 random windows at ≤ 512×384.
  - **Hard:** every reply is screen-bounded; `pyramidReportBytes ≪ 16N`.
  - **Soft / advisory:** compose p95 under a generous CI budget (e.g. 50 ms);
    never fail the suite solely on cold CI jitter.

### 5. Explicit non-goals for CI

- Do not allocate 1B points to “prove” Tier-3.
- Do not require Phase-4 tile spill/load for green CI.
- Do not require 100M pan p95 &lt; 16 ms on shared runners (dossier Phase-3
  item 9 stays a dedicated perf gate / CodSpeed job when instrumented).

## Reproduction

```bash
cargo test -p xyg-engine tiles
python3 scripts/abi_smoke.py          # includes pyramid ABI block
# Linux: libxyg_core.so; macOS: libxyg_core.dylib; Windows: xyg_core.dll
XYG_NATIVE_LIB=$PWD/target/release/libxyg_core.so \\
  npm --prefix packages/xy-node test -- test/pyramid.test.mjs
PYTHONPATH=python python3 benchmarks/bench_tier3_pyramid.py
node benchmarks/bench_tier3_pyramid_node.mjs
```

## Status mapping

| Surface | Phase-3 pyramid | Phase-4 tile spill |
| --- | --- | --- |
| Rust ABI | ready | design |
| Python | ready (interactive + first paint) | design |
| Node | ready (`pyramid.js` + figure density) | design |
| Browser paint | ready (consumes density grids) | design (tile-keyed cache pending) |
