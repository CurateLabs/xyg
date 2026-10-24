# Hosted mapped live aggregation comparison — failed evidence

**The run failed independent verification. No competitive winner or acceptance
claim follows from these observations.** This archive retains the one existing
[Actions run 40066499687](https://github.com/CurateLabs/xyg/actions/runs/40066499687),
attempt 1, clean main source `a8b3e10801fa3c1b96eddd7b244a1d64e0778bad`.
It was created at 2026-10-24 05:30:14 UTC. Job `120790765112` started at
05:30:42 and completed with `failure` at 05:35:09, after 4m27s. No dispatch,
retry, cancellation, capacity change, product repair or additional benchmark
was performed by this retention task.

## Outcomes and concrete blockers

All **18 configured cells** are present: three sizes × three arms × two
repetitions, numbered 0 and 1. No fastest repetition is selected. Producer
statuses are retained unchanged; they do not replace the hosted verifier's
rejection of the report.

| Actual rows | XYG repetitions 0 / 1 | Plotly aggregate repetitions 0 / 1 | Datashader aggregate repetitions 0 / 1 |
| ---: | --- | --- | --- |
| 1,000,000 | `ok` / `ok`; 0 / 0 visible-count mismatches | `host_failed` / `host_failed` | `host_failed` / `host_failed` |
| 100,000,000 | `ok` / `ok`; 32 / 32 visible-count mismatches | `host_failed` / `host_failed` | `host_failed` / `host_failed` |
| 1,000,000,000 | `ok` / `ok`; 32 / 32 visible-count mismatches | `host_failed` / `host_failed` | `host_failed` / `host_failed` |

The hosted independent verifier printed, at 05:35:06.434759 UTC:

```text
INVALID: XYG density visible count mismatch
```

The original line is in `hosted-verifier-output.txt` and the complete original
job log. There is **no accepted report**. The first mismatching recorded warm
window is XYG 100M, repetition 0, pan index 0: exact source-window count
36,450,230 versus reported `visible` 36,450,231. Metadata inspection finds
128 such mismatches across the four 100M/1B repetitions; maximum absolute
differences per repetition are 9,885 at 100M and 107,116 at 1B. Every mismatch
and requested domain is retained in `diagnosis.json`.

At the measured source, `crates/xyg-engine/src/tiles.rs:593` describes pyramid
count as an approximation using whole cells whose centers lie inside the
window. `python/xyg/interaction.py:1240` uses that estimate for the pyramid
route's visible count; the independent experiment verifier at
`scripts/verify_density_comparison_report.py:384` requires exact equality to
the inclusive source-window oracle. This exposes a contract disagreement
requiring reconciliation and regression proof. It does not establish a
rendered-grid mass defect, justify changing tolerance, or convert these
producer `ok` records into accepted evidence.

All **12 competitor attempts** exited with return code 1 before `META`, in
`host_prepare`. Their retained stderr ends with:

```text
ImportError: Numba needs NumPy 2.4 or less. Got NumPy 2.5.
```

The measured environment has NumPy 2.5.1 and Numba 0.66.0. The constrained
install originally logged NumPy 2.4.6; the following `uv run` native-backend
check downloaded NumPy and replaced 12 packages. The historical project
`uv.lock` selects NumPy 2.5.1 for Python ≥3.12. Project resynchronization
overriding the benchmark constraint is the evidence-supported explanation;
the log does not enumerate all replacement package versions. This is a
benchmark environment blocker, not a measured competitor capacity or speed
limit. Plotly means **Plotly + Datashader + Tornado**; the other competitor is
one **hvPlot/HoloViews/Datashader/Panel/Bokeh** stack. Neither produced browser
measurements, backend grid/copy observations, or an aggregation comparison.

## Descriptive XYG observations, subject to the rejection above

Each of the six producer-completed XYG repetitions recorded all 32 warm
windows (24 pans and eight zooms), plus a separate zero-count, zero-lit-pixel
empty control: **192 warm windows and six empty controls**. All warm outputs
were `density`, with **zero exact-point fallbacks**. Raster shapes were
250×250 at 1M, 376×376 or 512×512 at 100M, and 512×512 at 1B; the actual plot
area was 512×512. Binning labels were `bin2d-oversized` at 1M and pyramid
levels at larger sizes. Complete shapes, reductions, revisions, equivalence
checks, requested/applied domains and readback observations remain in the raw
report. XYG quantized grids have no independent per-cell conservation proof
added by this experiment.

Times below are ms, rounded to one decimal; both repetitions are shown.
Warm p50 is the median of all 32 observations in that repetition; p95 selects
sorted index `floor(.95*(32-1))`. These are programmatic request-to-first
stable-paint observations including adapter/probe work, **not natural gesture
latency or normalized kernel timings**. Cold columns record the browser
probe's first stable paint and its later ten-frame stability confirmation,
after host preparation; they are not end-to-end data-to-pixels times.

| Rows | Rep | Host build | Host preparation | Cold stable / confirmed | Warm p50 / p95 | Peak host RSS bytes | Peak browser RSS bytes | Warm 32 body bytes |
| ---: | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: |
| 1,000,000 | 0 | 40.9 | 265.9 | 522.2 / 651.3 | 37.2 / 49.3 | 118,751,232 | 1,162,330,112 | 2,027,204 |
| 1,000,000 | 1 | 9.7 | 151.9 | 489.7 / 629.8 | 36.7 / 46.0 | 97,583,104 | 1,142,587,392 | 2,027,204 |
| 100,000,000 | 0 | 289.6 | 959.9 | 485.0 / 617.0 | 38.5 / 48.9 | 2,306,490,368 | 1,151,041,536 | 7,932,934 |
| 100,000,000 | 1 | 236.2 | 922.5 | 472.4 / 597.7 | 37.8 / 51.4 | 2,306,244,608 | 1,160,757,248 | 7,932,934 |
| 1,000,000,000 | 0 | 2,155.8 | 7,736.1 | 487.9 / 627.4 | 38.3 / 50.8 | 19,395,346,432 | 1,155,284,992 | 8,415,779 |
| 1,000,000,000 | 1 | 1,742.5 | 7,306.8 | 465.3 / 599.3 | 36.2 / 47.5 | 19,398,410,240 | 1,161,117,696 | 8,415,779 |

`summary.json` retains unrounded per-repetition metrics, all 18 original
statuses and available failure RSS/stderr, cold cumulative and terminal socket
body bytes, empty-control deltas, source metadata and retained-array observations.
Initial cumulative body bytes per repetition were 267,456 / 265,592 / 265,528
at 1M / 100M / 1B. Empty controls added 63,322 / 13,379 / 13,376 respectively.
These are WebSocket application-message bodies, excluding HTTP/bootstrap,
framing, TLS and network-stack overhead. RSS is sampled process-tree RSS,
including runtime/shared mappings; it is neither an allocation delta nor GPU
memory. File size is not RSS. No recorded cell ended at a timeout or RSS
limit; competitor failures were imports, not resource limits.

## Sources, environment and measurement limits

The hosted producer created real little-endian f64 x/y files using generator
`independent-streams-f64-v1`, seed 20260713, in **1,000,000-row chunks**.
Source creation time includes generation, writing, hashing and 32 independent
chunked source-window counts; finer subclocks are unavailable. Per-column and
x-then-y SHA256, exact lengths, extents and every expected count are retained
in the original report and `summary.json`. Source bytes were removed by the
producer after measurement, and were not regenerated locally.

| Actual rows | Each x/y file bytes | Total source file bytes | Creation wall ms | Sampled source peak RSS bytes |
| ---: | ---: | ---: | ---: | ---: |
| 1,000,000 | 8,000,000 | 16,000,000 | 433.6 | 78,168,064 |
| 100,000,000 | 800,000,000 | 1,600,000,000 | 5,300.3 | 1,677,262,848 |
| 1,000,000,000 | 8,000,000,000 | 16,000,000,000 | 48,506.2 | 16,190,701,568 |

XYG's retained canonical x/y pointers matched the mapped source at admission
and after build at all three sizes, with shared-memory and memmap ancestry
true. Those observations do not exclude transient/native/derived allocations.
Competitor retained-column/backend mapping observations are unavailable because
their hosts failed before `META`. Actual temporary disk high-water, GPU memory,
HTTP/bootstrap bytes and CPU work were not measured.

The single existing Blacksmith lane is named macOS M4, 48 GB RAM / 250 GB SSD,
with a 720-minute job ceiling. Recorded platform is Darwin 24.6.0 / arm64,
12 logical CPUs and 51,539,607,552 bytes system memory (48 GiB). CPython
3.14.6, Chrome for Testing 149.0.7827.55, Node 22.23.4 and Rust/Cargo 1.96.0
were recorded. Full component versions, executable paths and clean git state
are in the raw report. Numba/OpenMP/OpenBLAS threads were each 2. Limits were
300 seconds per preparation/browser phase, 15 seconds per window, a
21,474,836,480-byte RSS cap per tree sampled every 50 ms, and 20 GiB source
disk. The producer completed the source generation and all configured cells
before independent verification failed.

`hardware_gl=false` requested the existing SwiftShader/software-GL flags.
**Actual renderer: UNMEASURED** (`browser_renderer_observed: null`). The legacy
renderer alias is only a launch-request label. No physical GPU claim is made.
OS disk/JIT caches were not flushed. The 16 GB mapped 1B source is smaller
than this machine's RAM; it is not larger-than-RAM proof.

The profile sets explicit equal windows, disables ordinary automatic XYG
request scheduling/cache elision, and includes full readback/validation work.
The intended competing adapters have unequal source-oracle work, grid
resolutions, shading and output contracts. There is no raster-only or mixed-mode
ranking, no measured competitor advantage, no simulation CPU-work result, no
candidate/release artifact proof and no #11/#108 closure evidence. Concrete
remaining comparison gaps are a functioning pinned dependency environment for
both combined competitor stacks, resolution of the XYG count contract, and a
subsequent independently accepted actual-scale comparison. Natural gesture,
hover/selection/exact-drill parity, colored competitive sources and
larger-than-RAM acceptance remain separate requirements. The parent owns spec
reconciliation and any future repair or execution decision.

## Retention and inspection

`ceiling-benchmark-12550060246.zip` is the unmodified original artifact:
67,204 bytes, SHA256
`dbb91970fdb6b80ca8cfc2be7580df7924f7402334806d4f4e614ed2df92cf47`,
matching GitHub's API digest and the upload log. Its sole member is
`_temp/density-comparison-a8b3e10801fa3c1b96eddd7b244a1d64e0778bad.json`:
1,545,409 bytes, SHA256
`0a19faac8773d6b0dc659652cd775cab872aa9f7f30250c3354c6910aaa87eb9`.
ZIP CRC and member bytes equal the gzip-decoded retained report exactly.
`job-120790765112.log.gz` preserves all 91,909 original job-log bytes,
retrieved through the job-log API rather than the broken `gh run view --log`
cache path. Gzip uses zero mtime and no filename; no JSON bytes were rewritten.

Original run, attempt, jobs and artifact API responses are retained separately.
`retention.json` identifies endpoints, archive members, CRCs and retrieval time.
`manifest.json` records compressed and decoded hashes/lengths;
`SHA256SUMS` covers every retained file including the manifest, excluding itself.
The retention script's watch output is not substituted for the complete log.

`source-bindings.json` compares all 15 measured harness/lock files and three
product-tree digests with historical `a8b3e108` Git objects: all matched.
It inventories 149 Python, 205 Rust and 52 TypeScript source files and also
pins historical workflow, verifier, project lock and build configuration files.
The actually loaded native hash is
`27425601a036c384b4d2357d700669b9a6f2f1d25381535a4cfa9bf8b65a3b3e`;
the built client hash is
`b7bf5702e7d28647b651777c364a8ec6c82403e145d16475ef8e06484b8ddfce`.
Their executable bytes were not uploaded, so these are measured producer
identities bound to the execution source, **not independently checked local
executables**. No rebuilt binary or current client substitutes for them.

From the repository root:

```bash
python3 benchmarks/results/live-aggregation-2026-10-24/hosted-main/inspect_evidence.py
```

This stdlib script checks retention hashes, GitHub ZIP digest, CRC/member
equality, exact cell coverage and historical Git-object bindings. It performs
metadata/hash inspection only. The large-report authority validator was not
run locally and no Actions environment was spoofed: the retained hosted
rejection remains the authority-context outcome. `commands.txt` records the
exact inspection/download endpoints and the historical producer/verifier
commands without authorizing another run.
