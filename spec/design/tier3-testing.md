# Tier-3 pyramid — testing best practices

**Status:** product testing contract for the Phase-3 Tier-3 pyramid and bounded
Phase-4 spill/reuse evidence (#11). This does not establish the dedicated
100M, larger-than-RAM, or integrated Phase-4 exit gates.

The shippable product is the **square multi-resolution count pyramid**
(`xyg_pyramid_build` → `compose` / `count` / `append` / `free`), available on
Python and Node, with §28 `binning: "pyramid-L<l>[-upsampled]"`. Phase-4
disk-resident 256² tile spill is a separate residency milestone: Rust ABI WP1
and Python/Node host engagement are landed. Their existence does not establish
Phase-4 scale acceptance or the final candidate host matrix.

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
  - Compose 32 deterministic windows at ≤ 512×384.
  - **Hard:** every reply is screen-bounded; `pyramidReportBytes ≪ 16N`.
  - **Soft / advisory:** compose p95 under a generous CI budget (e.g. 50 ms);
    never fail the suite solely on cold CI jitter.

Both existing scripts also build a 1024² count pyramid from the same ≤1M
canonical rows, spill it, and enforce a 2 MiB process-wide tile-residency
budget. Thirty-two spilled compositions must match the in-memory grid and
served level exactly. The in-memory pyramid is then freed; canonical input
columns remain available and are not counted as tile-cache residency.

The subsequent 32-frame pan sequence reports actual Rust-served tile keys,
generation, exposure, missing tiles, and encoded reply bytes. Its simulated
client retains only Rust-returned keys. Every omitted payload must already be
held, and every active tile hash and exposure must match a separate uncached
fetch-all sequence. Cached transfers must be strictly fewer than uncached
transfers. The reply must remain within 256 descriptors and the eight-screen
texture budget for its actual R8/RGBA8 format; reported CPU tile residency must
return within the configured 2 MiB budget after each call. Nonzero hit and miss
counters are required. All stores and budgets are released/restored on exit.

The JSON `spill` section retains these counters, sizes, oracle disposition,
and advisory timing. The timed cached sequence precedes the separate uncached
validation; it does not compare cold and warm timings or assert the dedicated
100M latency gate. Physical GPU allocation and pixel parity belong to the
real-browser tile smoke. These MB-scale fixtures make no 100M/1B allocation
and introduce no new workflow or required status.

The bounded reports now have schema version 1, runtime/environment metadata,
measured native-library SHA256, producer/harness source hashes, all 32 raw tile
timings, maximum descriptor/GPU bytes, and the observed process-wide residency.
`scripts/verify_tier3_pyramid_report.py` independently pins the one-million-row
control, 32 oracle and painter frames, 256-square resident pyramid, 2 MiB CPU
budget, 256-descriptor cap, and eight-screen R8 GPU budget. The report cannot
raise its own limits. The existing CI graph/chart smoke and `check-graph` run
this verifier for both hosts; `--check-local` checks source identity and
`--native` checks the measured library. The bounded timing remains advisory.

Additional host regression proof lives in
`tests/test_phase4_tile_spill_hosts.py` and
`packages/xy-node/test/pyramid.test.mjs`: two stores share a one-tile process
budget and eviction forces a reload; rejected colored appends preserve both
count and mean-color output. The Python public append path invalidates the
old colored store and lazily rebuilds to match a fresh chart. A categorical
legend predicate, even with a valid XYDC request, emits the exact `-masked`
reply without tile frames or tile statistics and leaves the store's hit/miss
counters unchanged. Removing the predicate resumes the same unfiltered store.
Node has no corresponding legend-predicate host entry point; no synthetic
Node predicate capability is claimed.

`benchmarks/test_codspeed_kernels.py` adds bounded count and mean-color spill
snapshot/teardown, warm C-ABI fetch, alternating fetch misses under one-tile
eviction, and warm spilled compose against resident oracles. Source generation
and resident-pyramid construction occur outside measurement. Fetch uses
preallocated output arrays; compose measures the Python/native wrapper including
its output allocations. Snapshot includes store creation and teardown. The existing main-only
CodSpeed scheduler discovers these cases; PRs run their correctness assertions.
Simulation measures CPU work and excludes system-call wall time. These are
neither cold-disk latency measurements nor the real 100M acceptance gate.

### Negative tile I/O contracts (#11, bounded kernel proof)

`crates/xyg-engine/src/tile_store.rs` uses deterministic MB-scale spill files
(base dimensions 512/1024, 4,096 canonical rows) to enforce these failure
contracts without a large-data allocation:

- Dirty eviction writes the complete count slab before removing its resident
  source or decrementing process-wide resident bytes. A failed/partial write
  retains the dirty tile and its full charge. A read-only replacement file
  descriptor forces writeback failure even under root; repeated failures must
  preserve the source, and restoring a writable descriptor must allow eviction
  and compositions identical to a full appended rebuild.
- Count/color compose and keyed paint must release their frame pins and attempt
  ordinary budget eviction on a failed gather too. Truncation partway through a
  later count or color slab follows successful pinned loads; it must return
  `UnexpectedEof`, admit no partial tile, and leave no clean residency above the
  configured budget. Restoring the file must recover exact grid/color or paint
  bytes. Fetch into caller buffers must admit neither a partial color tile nor
  an unreadable tile; failed reads leave those buffers unchanged.
- Cleanup does not turn failure into success or replace the original operation
  error with a secondary writeback error. If cleanup also fails, retained dirty
  sources remain charged even above budget; later writable recovery can persist
  and evict them. This is an I/O failure, not a new residency/LOD policy.
- Append input refusals remain atomic as specified in D4. An I/O error after
  mutation can leave a partially applied batch across rows/levels: discard and
  rebuild from canonical columns rather than blindly replaying that batch.
  Paint generation must change before mutation even when the call later fails,
  so cached textures cannot retain the old identity for changed cells.
- The store reads its live descriptor, not a reopened pathname. On Unix,
  removing the pathname or changing its permissions does not revoke the open
  descriptor: uncached reads and dirty writeback continue to work. A write-only
  replacement descriptor tests an actual unreadable source. These tests do not
  mislabel unlink/chmod as guaranteed read failures or promise pathname reopen.
- Dropping each failed/recovered store removes its temporary spill pathname
  (if still present) and returns all remaining resident charges to zero.

Reproduce with `cargo test -p xyg-engine tile_store -- --test-threads=1`.
The fixtures cover count/color short reads, unreadable descriptors, writeback
failure, error precedence, recovery, and cleanup. They do not validate arbitrary
same-length byte corruption (the process-local cache has no checksum), OS fault
codes on every platform, or the remaining host/browser and scale gates in #11.
The unlink/permission fixture is Unix-only; the descriptor/truncation fixtures
use the platform's existing positioned-I/O implementation.

### 5. Explicit non-goals for CI

- Do not allocate 1B points to “prove” Tier-3.
- Do not substitute these bounded spill/reuse checks for complete Phase-4
  product/host acceptance or large-scale measured evidence.
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
| Rust ABI | ready | bounded spill/compose and keyed paint frames implemented (ABI 395) |
| Python | ready (interactive + first paint) | tile-store facade and live binary inventory implemented |
| Node | ready (`pyramid.js` + figure density) | tile-store facade and keyed paint-frame loader implemented |
| Browser paint | ready (consumes density grids) | keyed texture reuse and crossfade implemented; full Phase-4 acceptance remains open |

[Retained bounded results](../performance/tile-spill-bounded-2026-10-23/README.md)
record actual native build/harness hashes, raw Python/Node reports, and their
scope limits. The [tile painter contract](density-tile-painter.md) describes
the protocol and real-browser proof.

## Remaining #11 acceptance

The structural harness above is only one part of #11. Corrupt/missing tile
I/O, append refusal, predicate bypass, shared-budget pressure, and resource
boundaries also require their focused kernel/host/browser fixtures. Scheduled
or manual main performance runs must retain comparable spill/fetch/compose
measurements, the real 100M colored memmap pan/zoom gate, and competitive
Datashader/HoloViews/hvPlot/Plotly/Bokeh evidence with environment, source and
artifact hashes, raw results, and reproduction commands. Reuse #876's
resource-authorized harness and feed the accepted results into #113/#54;
neither these timings nor integer-only planner cases close that scope.
