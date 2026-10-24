# Repeated equal-window browser controls — v2, 2026-10-24

**Programmatic range-setting experiment; no real-gesture latency, winner,
competitive acceptance or 100M/1B claim.** The [specification](../../../../spec/design/live-aggregation-comparison.md)
describes output adoption, source, timing and allocation authority. The
[original 18-cell wheel archive](../README.md) is unchanged and is bound to
commit `51975d5d6f5c073e0a4b60a404f8349e45c6775c`, rather than to evolved harness
files. Its raw report still has SHA256
`9917683d0175dd026fd3e9683bcadac498b9e34d1a761388e212303370e6a083`.

The raw reports are stored losslessly as [f32.json.gz](f32.json.gz),
[f32-xy-cache-followup.json.gz](f32-xy-cache-followup.json.gz) and
[f64-memmap.json.gz](f64-memmap.json.gz). Logical `.json` names below and in
actual argv refer to the original produced files. Deterministic gzip
compression happened after measurement; decoded bytes and their reported
SHA256 are unchanged. `SHA256SUMS` covers the compressed files. Inspect with
`gzip -dc f64-memmap.json.gz | python3 -m json.tool`.

## Executed scope and outcomes

Both source profiles ran all three density arms at **1k / 100k / 1M actual
rows**, with **two fresh host/browser repetitions per cell**. Each successful
repetition adopted all **24 pans + eight adjacent zooms** from the unchanged
`_density_spill.windows` trajectory, then passed a separate outside-source
empty-window control. All arms had actual matching browser axes and a measured
512×512 plot area; adopted output extents/revisions and nonblank or empty
pixels were checked on real browser readbacks. No stub supplies pass status.

- `f32.json`: first complete 18-cell sweep, **16 ok, two strict-pointer
  collector failures** on XYG 1M reversal pan index 5. The requested window
  equals earlier pan index 3 and the actual full-plane pixel hash also equals
  that earlier frame. The old collector rejected a retained frame because its
  object identity differed from the new reply, rather than observing its
  actual content. These original failures have not been overwritten or
  relabeled as successes.
- `f32-xy-cache-followup.json`: narrow two-repetition XYG 1M follow-up,
  **both ok**, all 32 windows and empty controls. The final validator observes
  the actual drawn raster and accepts retained frames only after verifying
  identical extents, dimensions and **every grid value** against the current
  reply for the immutable source. Each repetition recorded 19 equivalent
  retained-raster adoptions. Actual rendered and requested/reply revisions
  remain distinct in the raw records.
- `f64-memmap.json`: **18/18 ok**, all 32 windows and empty controls for each.
  Source generation, file hashing/count oracles, host build/navigation and
  warm steps are separate phases.

Thus the completed f32 controls (16 initial + two follow-ups) and the 18 f64
controls cover **36 completed repetitions, 1,152 verified warm windows and
36 empty controls**. The two earlier diagnostic attempts remain additional
failure evidence, not extra successful repetitions. No repetition is selected
for being fastest; each configured repetition is retained.

## Descriptive warm observations

Numbers below are programmatic request-to-first-stable-paint observations
including probe/adapter/oracle overhead. Median/p95 pool the 64 windows from
two repetitions of a cell; windows overlap and repeat, so these are descriptive
quantiles, not independent trials or confidence intervals. p95 selects sorted
sample index `floor(.95*(n-1))`. All times are ms; RSS peaks are MiB. These
are local Linux **software GL** results, not reference-hardware or M4 results.

The native adaptive grid, palette, normalization, exact-point fallback and
backend validation work differ. In particular Plotly includes a chunked NumPy
source-count scan in its request path, while Bokeh uses the prepared trajectory
counts. These are inclusive integration observations, not normalized pure
kernel timings or pixel-equivalent aggregate rankings. XYG's explicit request
profile disables automatic client request scheduling/cache elision while
retaining production density-versus-points policy. It is not an ordinary
navigation throughput benchmark.

| Source | N | Arm | Complete reps | Density / point steps | Warm median | Warm p95 | Max host MiB | Max browser MiB |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| f32 | 1,000 | `xy-density` | 2 | 0 / 64 | 64.1 | 516.9 | 59.9 | 1389.4 |
| f32 | 1,000 | `plotly-aggregate` | 2 | 64 / 0 | 126.6 | 151.7 | 271.2 | 1469.1 |
| f32 | 1,000 | `datashader-aggregate` | 2 | 64 / 0 | 207.7 | 257.2 | 348.9 | 1520.3 |
| f32 | 100,000 | `xy-density` | 2 | 0 / 64 | 1124.2 | 2858.9 | 67.1 | 1395.9 |
| f32 | 100,000 | `plotly-aggregate` | 2 | 64 / 0 | 144.1 | 160.3 | 272.0 | 1489.7 |
| f32 | 100,000 | `datashader-aggregate` | 2 | 64 / 0 | 207.7 | 224.7 | 349.1 | 1517.8 |
| f32 | 1,000,000 | `xy-density` | 2 | 56 / 8 | 217.8 | 949.5 | 95.3 | 1368.1 |
| f32 | 1,000,000 | `plotly-aggregate` | 2 | 64 / 0 | 175.0 | 208.1 | 278.9 | 1539.8 |
| f32 | 1,000,000 | `datashader-aggregate` | 2 | 64 / 0 | 222.7 | 240.2 | 355.5 | 1522.4 |
| f64-memmap | 1,000 | `xy-density` | 2 | 64 / 0 | 201.6 | 309.2 | 59.9 | 1333.8 |
| f64-memmap | 1,000 | `plotly-aggregate` | 2 | 64 / 0 | 129.0 | 162.0 | 270.0 | 1458.7 |
| f64-memmap | 1,000 | `datashader-aggregate` | 2 | 64 / 0 | 205.4 | 222.0 | 348.8 | 1519.1 |
| f64-memmap | 100,000 | `xy-density` | 2 | 64 / 0 | 203.5 | 297.1 | 62.2 | 1335.3 |
| f64-memmap | 100,000 | `plotly-aggregate` | 2 | 64 / 0 | 143.2 | 162.1 | 271.8 | 1489.1 |
| f64-memmap | 100,000 | `datashader-aggregate` | 2 | 64 / 0 | 206.9 | 223.6 | 348.1 | 1521.0 |
| f64-memmap | 1,000,000 | `xy-density` | 2 | 64 / 0 | 208.2 | 358.9 | 81.1 | 1334.2 |
| f64-memmap | 1,000,000 | `plotly-aggregate` | 2 | 64 / 0 | 174.8 | 192.5 | 285.6 | 1467.5 |
| f64-memmap | 1,000,000 | `datashader-aggregate` | 2 | 64 / 0 | 222.7 | 242.8 | 359.7 | 1517.7 |

Every raw step additionally retains request start/return, first observed axis
and output adoption, stability confirmation, requested/actual domains, mode,
raster shape or exact-subset coverage/count, paint hash, socket application
body-byte delta, current/peak host and browser tree RSS, and host observations.
The cold checkpoint retains the corresponding cumulative transport/memory and
first-paint observations. Socket body bytes exclude HTTP/bootstrap assets,
WebSocket framing, compression, TLS and network-stack overhead. RSS includes
runtime/baseline and shared mappings and is not a GPU allocation measurement.
No input-to-pixel or real-wheel latency quantile is inferred from these clocks.

## Source and copy observations

The default f32 generator is byte-identical to the original workload for all
three N values. Hosts load those f32 files as resident arrays. XYG records its
f64 widening copies; these are not described as zero-copy canonical admission.
The separate f64 profile uses two independent seeded Gaussian streams and
real little-endian f64 x/y memmaps, generated in 65,536-row chunks. File lengths,
column SHA256, combined x-then-y SHA256, extents and 32 independent inclusive
window counts are in each report. All hosts validate file lengths/hashes.
There are no fake rows, N-sized f64 generation arrays or color columns.

For the f64 runs, XYG canonical admission and after-build observations show
identical starting pointers/shared memory and retained memmap ancestry for x/y
at all three sizes. The Plotly/Bokeh DataFrame observations and actual Bokeh
Datashader input observations are retained separately. These are observations
of retained arrays, not proof of no transient/native/derived copies. At 1M the
actual mapped source is 16,000,000 bytes. Temporary source files are deleted
only by this runner after the owning cells finish; deterministic hashes and
producer sources make them reproducible without committing large data files.

## Exact environment and commands

CPython 3.12.15; Chrome for Testing 156.0.8078.4 at the explicit installed path
below; SwiftShader; DPR=1; 1100×600 browser window; 512×512 actual data plot.
Linux x86_64 shared local machine, eight logical CPUs, reported 32 GiB RAM;
no CPU isolation, disk/JIT-cache flush, confidence interval or GPU-memory claim.
The browser tree includes bundled extension renderer processes on this install.
Numba/OpenMP/OpenBLAS threads are each 2. Exact component versions and git dirty
state are in every JSON; complete optional dependencies are frozen in
`runtime-requirements.txt`. Dirty-tree measurements remain exploratory and
retain their complete source hashes; methodology publication gates still apply.

Preparation reuses the prior built native/client artifacts and optional lock:

```bash
export PATH="$HOME/.cargo/bin:$PATH"
mkdir -p .ux-tmp
export TMPDIR="$PWD/.ux-tmp"
# For a fresh checkout:
cargo build --release
npm ci && node js/build.mjs
uv sync --group dev
uv venv .venv-ux
uv pip install --python .venv-ux/bin/python -r benchmarks/requirements-ci.lock \
  websocket-client==1.9.0 pytest==9.0.2
```

Executed f32 sweep:

```bash
TMPDIR="$PWD/.ux-tmp" PYTHONPATH="$PWD/python:$PWD" PATH="$HOME/.cargo/bin:$PATH" \
NUMBA_NUM_THREADS=2 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
timeout 1800 .venv-ux/bin/python benchmarks/bench_density_comparison.py \
  --sizes 1000,100000,1000000 --arms xy-density,plotly-aggregate,datashader-aggregate \
  --profile f32 --repetitions 2 --memory-gib 2 --disk-gib 0.25 \
  --timeout 180 --step-timeout 15 \
  --chrome /home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome \
  --out benchmarks/results/live-aggregation-2026-10-24/equal-window-v2/f32.json \
  > benchmarks/results/live-aggregation-2026-10-24/equal-window-v2/f32-console.jsonl \
  2> benchmarks/results/live-aggregation-2026-10-24/equal-window-v2/f32-stderr.log
```

The exact two-repetition cache-validation follow-up used the same environment
prefix/options, with `timeout 600`, `--sizes 1000000 --arms xy-density`, and
`--out .../equal-window-v2/f32-xy-cache-followup.json`; stdout/stderr are retained
as `f32-xy-cache-console.jsonl` and `f32-xy-cache-stderr.log`.

Executed f64 sweep used the f32 command with `--profile f64-memmap` and
`--out .../equal-window-v2/f64-memmap.json`; stdout/stderr are retained as
`f64-console.jsonl` and `f64-stderr.log`. Every report retains full actual argv. `commands.txt` also retains all three full shell commands and environment prefixes without path abbreviations.
For reproduction change output to a fresh `.ux-tmp/reproduction.json`; preserve
this archive. All Chrome profiles/source files use this worktree-backed
`TMPDIR` because the shared `/tmp` per-user quota is exhausted. No other
worktree or file store was cleaned. No local source exceeds 1M.

## Resource guards and review finding

Local source allocation is rejected above 1M before output/work directories or
source subprocesses are created. The legacy `bench_ux.py` resident controller
and its Plotly build-child likewise reject N>1M before generating either
column, resolving the independent blocking P2 on immutable `51975d5d` (reviewed
diff `dbbbcdbcb559fed343594ba07a78007421e15b94219c0ef053e7353f44c3e40f`).
Regression tests replace generators/builders/subprocess/temp creation with
failures and verify no call/output on rejection. No approval from that review
is claimed; the final follow-up requires independent re-review.

New source generation/hashing/count-oracle preparation runs in a child with a
2 GiB sampled RSS cap and 180 s timeout. Each host/browser has its own 2 GiB
cap and 180 s phase timeout; each window has a 15 s deadline. Peak polling is
50 ms and can overshoot; checkpoint samples supplement it. Source disk guard
is 0.25 GiB with 64 MiB free-space reserve. The shell bounds were 1,800 s per
full sweep / 600 s for the narrow follow-up. Caps were never increased to
rescue a cell. Source construction, memory and timeout failures have distinct
statuses; partial/adoption/oracle failures remain raw cells.

## Integrity and producer binding

`f32-producer/` contains exact source/lock bytes (stored as `.txt`) matching the
initial f32 report's producer hashes. `current-producer/` contains the final
producer matching the cache follow-up and f64 sweep. This makes both collector
versions inspectable without pretending old raw harness hashes match current
source after evolution. Changes after the first f32 sweep were the explicit
cached-grid equality validator and release of source hash-scan mappings before
reopening canonical maps. No first-sweep raw result was edited.

`SHA256SUMS` covers every file under this new subdirectory except itself;
verify here with `sha256sum -c SHA256SUMS`. The parent archive's original
203-file checksum manifest is unchanged and is still verified separately.
Reports and source identities SHA256:

- `f32.json`: `fe9b087e8fd20163d9b0d9f706dc9059aa7f9d73bd9f8c763849b466ff4dbed6`
  - f32 N=1000, x-then-y: `c63deced8d649438a75118fae2ea9f32f9049ae942117e4fc92268114a50a6cf`
  - f32 N=100000, x-then-y: `fae52f30bbd314c945ff701917d2a2675927d4f42d179f69e584fb0ef6d3ed30`
  - f32 N=1000000, x-then-y: `36b5431d6fee501bdf558ce4f4cdd1bb0f7755ab1e589c1806a7c3a68903d72f`
- `f32-xy-cache-followup.json`: `21965ee46178049d37001c9028e80b72259cb1109b19593920560a3e697e06ce`
  - f32 N=1000000, x-then-y: `36b5431d6fee501bdf558ce4f4cdd1bb0f7755ab1e589c1806a7c3a68903d72f`
- `f64-memmap.json`: `092c9b30ccb2fd28831d3c833ade6a3ad0d53ccfbcaf4e66dd5a80ded8810f11`
  - f64-memmap N=1000, x-then-y: `74f37a5e3b747150dba3dbff1bc7157b71ced3068118d6ae6c70fcb21152d691`
  - f64-memmap N=100000, x-then-y: `3290cbcc19d47f266cd4cd1f83609d6f2266acf0bc2f32f9a30af432303d6930`
  - f64-memmap N=1000000, x-then-y: `79d13426b37c67b408f18152ccd14aec66719a4d70e1ebea98be8abe95d09f97`

Focused verification commands:

```bash
TMPDIR="$PWD/.ux-tmp" PYTHONPATH="$PWD/python:$PWD" .venv-ux/bin/python -m pytest \
  tests/test_density_comparison.py tests/test_ux_comparison_evidence.py \
  tests/test_ux_live_host_transport.py -q
# 48 passed, including both actual archives, all producer/file hashes,
# count/mode/domain evidence and meaningful before-allocation guards.
TMPDIR="$PWD/.ux-tmp" uv run --with tornado==6.5.7 --with websocket-client==1.9.0 pytest \
  tests/test_density_comparison.py tests/test_ux_comparison_evidence.py \
  tests/test_ux_live_host_transport.py -q
# 47 passed, 1 optional Datashader skip in the product/dev environment.
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

## Remaining actual-scale and product gaps

This closes bounded source/equal-window/repetition instrumentation, not #11
competitive acceptance. No hosted run, actual 100M/1B browser comparison,
colored/three-column source, larger-than-RAM acceptance, cold-disk gate, hover,
selection, export or dashboard comparison is established. Exact fallback and
native raster resolution differences remain explicit comparison limits.

A true 1B **two-f64 mapped** source is 16,000,000,000 file bytes; mapped size is
not RSS and is not declared impossible. The existing manual-main Blacksmith
macOS M4 lane documents 48 GB RAM / 250 GB SSD / 20 GiB per-tree RSS guard.
The new allocation authority permits above-1M f64 maps only on that existing
workflow_dispatch/main/Darwin-arm64 host with sufficient RAM, never by a local
row-count override. Actual source-plus-derived costs and failures must be
measured there. No workflow/job/resource/capacity was added or raised, no
hosted work was dispatched, and no push/PR/merge/issue closure/publication was
performed. Root owns the narrow existing-lane wiring and reviewed scale run.
