# Hosted mapped aggregation — accepted structural evidence

**Actual hosted independent verification accepted this report: 18 successful
cells, 0 failed cells.** This is the receipt for the already-dispatched
[Actions run 40618320164](https://github.com/CurateLabs/xyg/actions/runs/40618320164),
attempt 1, clean `main` source `d005b0063d9909392786a18262ff1306e3e8f54c`
(PR #1075 merged). Creation was 2026-10-28 02:00:02 UTC. Job `122585957828`
ran 02:00:44–02:20:52 UTC (20m08s), concluding `success`. At
02:20:46.232667 UTC the actual hosted verifier printed:

```text
Valid evidence: 18 successful cells, 0 failed cells. Programmatic clocks only; no gesture, kernel-win or competitive acceptance claim.
```

This is acceptance of the hosted evidence contract, **not a competitive winner,
larger-than-RAM result, general #108 acceptance or publication permission**.
Producer `ok` alone would not have established acceptance. The original report,
complete job log, terminal API records and verifier output are retained together.
No dispatch, retry, cancellation, benchmark rerun, harness repair, resource
increase, GitHub mutation, push, PR or issue closure occurred in this task.
No local Actions/Darwin authority was emulated and the large independent
verifier was not run locally. Historical receipts remain immutable, including
both rejected 2026-10-24 hosted attempts. The parent owns specification changes,
independent review, integration and subsequent actions.

## Every configured cell and memory observation

The exact 1M/100M/1B × three arms × repetitions 0/1 matrix appears once each.
All 18 cells retain 32 warm windows (24 pans, eight zooms), a separate empty
control and a cold checkpoint: **576 warm windows, 18 empty controls, 612
cold/warm/empty checkpoints**. No cell has a failure, timeout, unavailable-cell
or RSS-limit status. Such outcomes would remain explicit cells;
none are converted to zero latency. Every empty control has zero expected
count and zero opaque nonwhite interior pixels.

| Actual rows | Arm | Rep | Status | Warm windows | Empty | Peak host RSS bytes | Peak browser RSS bytes |
| ---: | --- | ---: | --- | ---: | --- | ---: | ---: |
| 1,000,000 | `xy-density` | 0 | `ok` | 32 | ok | 125,943,808 | 1,203,224,576 |
| 1,000,000 | `xy-density` | 1 | `ok` | 32 | ok | 105,218,048 | 1,192,919,040 |
| 1,000,000 | `plotly-aggregate` | 0 | `ok` | 32 | ok | 388,841,472 | 1,361,362,944 |
| 1,000,000 | `plotly-aggregate` | 1 | `ok` | 32 | ok | 347,242,496 | 1,370,193,920 |
| 1,000,000 | `datashader-aggregate` | 0 | `ok` | 32 | ok | 447,627,264 | 1,364,230,144 |
| 1,000,000 | `datashader-aggregate` | 1 | `ok` | 32 | ok | 423,378,944 | 1,360,527,360 |
| 100,000,000 | `xy-density` | 0 | `ok` | 32 | ok | 2,393,751,552 | 1,317,699,584 |
| 100,000,000 | `xy-density` | 1 | `ok` | 32 | ok | 2,380,562,432 | 1,290,338,304 |
| 100,000,000 | `plotly-aggregate` | 0 | `ok` | 32 | ok | 1,955,151,872 | 1,323,696,128 |
| 100,000,000 | `plotly-aggregate` | 1 | `ok` | 32 | ok | 1,948,549,120 | 1,322,876,928 |
| 100,000,000 | `datashader-aggregate` | 0 | `ok` | 32 | ok | 2,007,957,504 | 1,343,569,920 |
| 100,000,000 | `datashader-aggregate` | 1 | `ok` | 32 | ok | 2,009,055,232 | 1,338,294,272 |
| 1,000,000,000 | `xy-density` | 0 | `ok` | 32 | ok | 19,826,933,760 | 1,332,690,944 |
| 1,000,000,000 | `xy-density` | 1 | `ok` | 32 | ok | 19,803,258,880 | 1,322,663,936 |
| 1,000,000,000 | `plotly-aggregate` | 0 | `ok` | 32 | ok | 16,336,896,000 | 1,263,665,152 |
| 1,000,000,000 | `plotly-aggregate` | 1 | `ok` | 32 | ok | 16,346,365,952 | 1,264,304,128 |
| 1,000,000,000 | `datashader-aggregate` | 0 | `ok` | 32 | ok | 16,421,666,816 | 1,325,006,848 |
| 1,000,000,000 | `datashader-aggregate` | 1 | `ok` | 32 | ok | 16,415,506,432 | 1,321,484,288 |

RSS is process-tree RSS sampled every 50 ms from spawn through completion,
separately for host and browser. It includes preparation/runtime costs and may
double-count shared mappings. It is not an allocation delta, GPU-memory measure
or whole-machine cap. Actual source-file size is distinct from sampled RSS.
The report preserves all cold/step/empty/terminal current and peak snapshots,
canonical admission/after-build pointer and mapping observations, and Bokeh's
actual backend-input observations. All 18 host source identities match their
shared manifest. Those observations do not exclude transient or native/backend
allocations.

## Cold, warm and transport observations

Times below are ms, rounded to one decimal. Build and preparation clocks are
separate; cold stable/confirmed clocks follow host preparation. Warm p50 is
the median of all 32 recorded `paint_stable_ms` values; p95 selects sorted index
`floor(.95*(32−1))`. Every repetition is shown, without best-of selection.
`summary.json` preserves unrounded values, maxima and original cold/empty
records; the original report preserves every warm observation.

| Rows | Arm | Rep | Host build / prepare ms | Cold stable / confirmed ms | Warm p50 / p95 ms | Warm socket body bytes |
| ---: | --- | ---: | --- | --- | --- | ---: |
| 1,000,000 | `xy-density` | 0 | 36.3 / 427.9 | 555.4 / 686.2 | 52.4 / 58.1 | 2,027,204 |
| 1,000,000 | `xy-density` | 1 | 9.2 / 330.7 | 521.6 / 664.1 | 49.3 / 53.0 | 2,027,204 |
| 1,000,000 | `plotly-aggregate` | 0 | 881.3 / 1167.6 | 394.2 / 541.3 | 136.7 / 139.5 | 4,307,415 |
| 1,000,000 | `plotly-aggregate` | 1 | 451.5 / 727.7 | 414.9 / 558.2 | 136.9 / 139.1 | 4,307,411 |
| 1,000,000 | `datashader-aggregate` | 0 | 23.3 / 2275.8 | 442.9 / 591.1 | 168.1 / 187.3 | 33,611,735 |
| 1,000,000 | `datashader-aggregate` | 1 | 10.7 / 2182.2 | 420.5 / 571.6 | 167.8 / 184.4 | 33,611,735 |
| 100,000,000 | `xy-density` | 0 | 257.4 / 5051.8 | 539.9 / 675.0 | 72.6 / 94.5 | 7,932,934 |
| 100,000,000 | `xy-density` | 1 | 258.5 / 5070.1 | 500.6 / 641.2 | 71.4 / 73.8 | 7,932,934 |
| 100,000,000 | `plotly-aggregate` | 0 | 790.5 / 1610.0 | 381.3 / 513.5 | 683.5 / 700.8 | 5,712,613 |
| 100,000,000 | `plotly-aggregate` | 1 | 788.6 / 1589.5 | 389.5 / 533.1 | 675.8 / 717.4 | 5,712,611 |
| 100,000,000 | `datashader-aggregate` | 0 | 10.8 / 2966.8 | 591.9 / 744.0 | 629.3 / 647.8 | 33,611,960 |
| 100,000,000 | `datashader-aggregate` | 1 | 10.8 / 2855.9 | 586.6 / 740.4 | 632.0 / 649.9 | 33,611,960 |
| 1,000,000,000 | `xy-density` | 0 | 2071.7 / 72949.7 | 521.0 / 660.0 | 74.8 / 85.1 | 8,415,779 |
| 1,000,000,000 | `xy-density` | 1 | 1760.3 / 71767.8 | 525.2 / 666.7 | 72.5 / 74.1 | 8,415,779 |
| 1,000,000,000 | `plotly-aggregate` | 0 | 4868.8 / 10682.3 | 376.7 / 517.8 | 5260.3 / 5502.8 | 4,935,756 |
| 1,000,000,000 | `plotly-aggregate` | 1 | 4861.4 / 10640.3 | 387.1 / 524.5 | 5251.6 / 5517.7 | 4,935,769 |
| 1,000,000,000 | `datashader-aggregate` | 0 | 10.8 / 9764.7 | 2369.0 / 2521.9 | 4259.7 / 4515.2 | 33,611,939 |
| 1,000,000,000 | `datashader-aggregate` | 1 | 10.8 / 9719.7 | 2363.4 / 2517.3 | 4240.7 / 4501.6 | 33,611,939 |

These are programmatic request-to-stable-paint observations including adapter,
validation, asynchronous hashing/metrics and readback work. They are not natural
wheel/gesture latency, FPS or pure kernel timings. OS/JIT caches were not
flushed. Plotly aggregate build includes its initial Datashader aggregation,
oracle and PNG encoding; Bokeh builds a lazy application whose first raster/JIT
can occur after its small build subclock. XYG source-derived oracle preparation
is included in host preparation and its RSS/watchdog, detailed below.

All arms used a measured 512×512 data plot area. Actual warm grids differ:
XYG 1M uses 250×250; XYG 100M uses 376×376 or 512×512; XYG 1B uses 512×512.
Competitors use 512×512. All warm outputs are density rasters; no exact-point
fallback is recorded. The exact cold/empty shapes, served pyramid levels,
requested/reply/adopted revisions, equivalent-cache reuse and output hashes
remain in the raw report. These are not identical-grid or identical-shading
aggregation microbenchmarks.

`plotly-aggregate` is **Plotly + Datashader + Tornado**, with base64 PNGs;
it is not native Plotly aggregation, raw Plotly scatter, Dash or an official
Plotly adapter. `datashader-aggregate` is one combined
**hvPlot/HoloViews/Datashader/Panel/Bokeh server** stack, not independently
measured component libraries. Unequal validation, shading, caching and adaptive
grid work prevent a normalized kernel ranking or universal speedup claim.

Transport is WebSocket application-message body bytes, including CDP-decoded
binary frames and UTF-8 text. It excludes HTTP/bootstrap assets, numerical
validation HTTP, framing, compression, TLS and network-stack costs. Cold and
terminal cumulative transport plus per-step and empty-control deltas are
retained. Numerical validation HTTP bodies are separately disclosed below.
Zero or omitted transport categories must not be read as zero total delivery cost.

## Source-derived numerical proof retained

All **204 XYG cold/32-warm/empty checkpoints** retain passing
`source-cell-compose-v1` observations. Recorded emitted visible count equals
the independently prepared expected value; expected/actual encoded hashes and
expected/adopted decoded hashes match, with source hashes bound to the shared
manifest. The hosted verifier accepted these count/grid/source bindings.
`diagnosis.json` retains every complete numerical record and no failure cells;
`numerical-summary.json` is arithmetic over retained metadata only.

Exact inclusive source count C, half-open count H, upper-boundary exclusions
C−H, emitted/expected estimate E, boundary mass B, grid mass diagnostic, native
labels, base geometry, served level, maxima and hashes remain distinct. C−H
is zero at all recorded XYG checkpoints in this dataset; this is not a general
endpoint equivalence claim. At 100M/1B, all 32 warm windows use whole-cell-center
pyramid estimates. E must equal the prepared expectation exactly, while
|E−C| must fit that checkpoint's independently prepared B; B is not a free
numerical tolerance. Cold full-source counts and empty controls are exact.
At 1M, the warm path uses exact half-open source binning.

The table's maxima summarize separate checkpoint fields; it does not replace
per-checkpoint bindings. Preparation uses 65,536-row oracle chunks, distinct
from the 1M-row source-generation chunk. Grid-storage figures are conservative
oracle upper-bound accounting, not measured allocation deltas. Validation sums
cover cold + 32 warm + empty, and remain inside the observed paint path.

| Rows | Rep | Oracle prepare ms | Grid storage upper bound bytes | max abs(E−C) | max B | Validation ms sum | Validation HTTP body bytes sum |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000,000 | 0 | 188.2 | 37,748,736 | 0 | 0 | 34.0 | 15,087,991 |
| 1,000,000 | 1 | 194.7 | 37,748,736 | 0 | 0 | 34.0 | 15,087,991 |
| 100,000,000 | 0 | 4134.9 | 306,184,188 | 9,885 | 113,492 | 121.3 | 54,126,791 |
| 100,000,000 | 1 | 4137.0 | 306,184,188 | 9,885 | 113,492 | 115.7 | 54,126,791 |
| 1,000,000,000 | 0 | 65227.3 | 1,111,490,556 | 107,116 | 601,740 | 131.4 | 57,346,851 |
| 1,000,000,000 | 1 | 64412.2 | 1,111,490,556 | 107,116 | 601,740 | 125.8 | 57,346,851 |

All competitor cold/warm/empty checkpoints retain actual aggregate mass/count,
requested domain and grid/raster bindings. Bokeh also retains its adopted actual
image-byte SHA256 and bound backend grid/revision, rather than pairing a later
host grid with an old bootstrap image. The previous hosted import/admission
failures are not observed in this run. This statement does not retroactively
accept those older receipts.

## Actual inputs, environment and source identities

The retained hosted input environment and report argv agree: experiment
`density-comparison`; sizes `1000000,100000000,1000000000`; arms
`xy-density,plotly-aggregate,datashader-aggregate`; repetitions 2; profile
`f64-memmap`; source chunk 1,000,000; timeout 300s per preparation/browser
phase; step timeout 15s; RSS cap 20GiB (21,474,836,480 bytes) per tree; source
disk cap 20GiB; `hardware_gl=false`, with no `--hardware` argument.
`requested-inputs.json` records the task constraints, not an original dispatch
API body. That original request body is not exposed in the retained REST
responses. `actual-values.json` binds actual hosted log inputs, import check,
argv, environment and source-window counts.

The existing Blacksmith macOS 15 M4 lane reports 12 CPUs, Darwin 24.6.0/arm64
and **51,539,607,552 memory bytes (48GiB)**. Actual Python is 3.12.10;
NumPy 2.4.6, Numba 0.66.0, llvmlite 0.48.0; Plotly 6.9.0, Datashader 0.19.1,
hvPlot 0.12.2, HoloViews 1.23.1, Bokeh 3.9.1, Panel 1.9.3, pandas 3.0.3,
Tornado 6.5.7, Pillow 12.3.0, psutil 7.2.2, websocket-client 1.9.2.
The hosted constrained environment import check succeeded. Chrome for Testing
is 149.0.7827.55, Node 22.23.4, Rust/Cargo 1.96.0. Numba/OpenMP/OpenBLAS
threads were each 2. Full executable paths/versions and authority facts remain
in the log/report. Local receipt-tool Python/packages are not substitutes for
this hosted environment.

**Software GL was requested; actual renderer was not measured.** The report
records `browser_renderer_requested: software-gl`,
`browser_renderer_observed: null`, and scope `launch-request; actual renderer
not measured`. There is no confirmed hardware-GPU measurement.

The source is two actual little-endian f64 columns per size, generated with
`independent-streams-f64-v1`, seed 20260713. Preparation includes file writing,
hashing and the 32 independent source-window C/H counts at each size. Column
lengths, individual column hashes, x-then-y hashes, domains and row identities
remain in the raw report and summary, with no local source regeneration.

| Actual rows | Each x/y file bytes | Total source bytes | Source creation ms | Source peak RSS bytes |
| ---: | ---: | ---: | ---: | ---: |
| 1,000,000 | 8,000,000 | 16,000,000 | 366.9 | 84,033,536 |
| 100,000,000 | 800,000,000 | 1,600,000,000 | 7583.5 | 1,676,754,944 |
| 1,000,000,000 | 8,000,000,000 | 16,000,000,000 | 74322.4 | 16,082,878,464 |

| Rows | SHA256 of x bytes then y bytes |
| ---: | --- |
| 1,000,000 | `b2018aea04e035ae4d87d6b5f21fb08f921d7736074df520d1074c8694ee5baf` |
| 100,000,000 | `ec8552f33e7a364fece94e1055e0ab85fc0c508bb2876092ecd31025e8368af4` |
| 1,000,000,000 | `080c3cc0d77c3d1d05bdfef5cdbb90c58065c8502e75b551ffcd86d7df63f7df` |

The 1B source is **16,000,000,000 bytes**, which fits within the runner's
48GiB RAM. This is not larger-than-RAM evidence. Source columns were not in
the uploaded artifact; receipt inspection cannot independently rehash those
absent bytes. It checks their retained identities and hosted bindings only.
Disk high-water, GPU memory, natural gestures, hover/selection/exact-drill
parity, colored sources, all chart families and release/candidate qualification
are not established. Whole #108 and broader competitive acceptance remain open.

## Lossless retention and source binding

Original artifact `ceiling-benchmark-12787042086.zip` (artifact `12787042086`) is **341,123 bytes**, SHA256
`4f32087bbda5cb07f99abc7658594c4bb736f9db0eb3e7448bbe7ff0ede1be25`, matching both GitHub's digest and the upload log.
Its sole member `_temp/density-comparison-d005b0063d9909392786a18262ff1306e3e8f54c.json`
is **8,329,865 bytes**, SHA256
`390b81238cc2d2649f8300c9dc014d6695ce7fce944adfc75cb276714170af2a`, CRC32 `eabc9311`.
ZIP CRC/member bytes match the retained gzip-decoded report exactly. No original
report JSON bytes were rewritten. Report/log gzip uses mtime zero and no filename.

`job-122585957828.log.gz` preserves all **97,435 original job-log bytes**,
decoded SHA256 `9b518e60f391fae239ddadb9dadb851d94d290798b647ee2a03ec4133d173497`.
It was downloaded directly from `gh api repos/CurateLabs/xyg/actions/jobs/122585957828/logs`
into the owned path, then compressed; no shared `/tmp` log cache was used.
There is one hosted job, and its full log is retained.

Run, attempt, jobs, individual job, workflow, artifacts, individual artifact
and source-commit API responses are separate retained records. Initial
in-progress observations keep distinct filenames. `retention.json` records
retrieval/endpoints/ZIP members and decoded hashes. `manifest.json` records
all retained file hashes/lengths and decoded gzip hashes/lengths; `SHA256SUMS`
covers every top-level file except itself. Transient tooling stays under the
checkout's ignored `target/task-tmp`, outside this receipt.

`source-bindings.json` matches all 16 measured harness/lock-file hashes and
three product-tree digests to immutable source `d005b006`, inventorying 149
Python, 205 Rust and 52 TypeScript files. Historical workflow, verifier,
count/grid contract, host-admission contract, report contract, producer/host
snapshots and dependency lock are retained as `.txt`, with exact Git-object
byte equality checked. Additional build/lock files are bound to historical
Git blobs. Product-tree digests:

- `python/xyg`: `ea0382296d3e020fa7826c7d927e119e3f2099c3073ebe8c2d13f9d003221b7e`
- `crates`: `77181fb49701393a0201128203b313beac77d08c8e5f3b2b1fad7172a094fc15`
- `js/src`: `2c1f8f1042cedbc702963eb66cf6bb6d7c0e4a0304389a21573d6e48daa045b5`

The producer-recorded loaded-native SHA256 is
`27425601a036c384b4d2357d700669b9a6f2f1d25381535a4cfa9bf8b65a3b3e`;
client SHA256 is
`b7bf5702e7d28647b651777c364a8ec6c82403e145d16475ef8e06484b8ddfce`.
Executable bytes were not uploaded. No local rebuild or independent executable
byte verification substitutes for their recorded identities.

From repository root:

```bash
python3 benchmarks/results/live-aggregation-2026-10-28/hosted-main-d005b006/inspect_evidence.py
(cd benchmarks/results/live-aggregation-2026-10-28/hosted-main-d005b006 && sha256sum -c SHA256SUMS)
```

The read-only, stdlib-only inspector checks file/decoded hashes, ZIP digest,
CRC/member equality, terminal run/source/artifact bindings, historical Git
objects/product trees, actual inputs/versions and exact 18-cell coverage.
It creates no source arrays and imports no numerical/native libraries.
The retained **actual hosted verifier acceptance** is the authority-context
result; this local metadata inspection does not emulate it. `commands.txt`
records retrieval and verification commands; `validation.txt` records full
repository hooks and Ruff checks. Parent independent review and integration
remain required before treating this receipt as incorporated specification
or release evidence.
