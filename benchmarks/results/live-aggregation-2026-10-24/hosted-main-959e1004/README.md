# Hosted mapped live aggregation comparison — rejected report

**This run failed hosted independent verification. It supplies no accepted
comparison, competitive winner, #108 acceptance, or publication permission.**
This is the immutable receipt for the already dispatched [Actions run
40075049750](https://github.com/CurateLabs/xyg/actions/runs/40075049750),
attempt 1, clean main source `959e1004924774711a35df7ab1317cca30b18d68`
(PR #1072 merged). Run creation was 2026-10-24 07:40:16 UTC. Job
`120816502776` ran from 07:40:46 to 07:56:39 UTC (15m53s), concluding
`failure`. The hosted verifier printed at 07:56:35.179025 UTC:

```text
INVALID: Bokeh actual backend output mismatch
```

The prior rejected run `40066499687` and sibling `hosted-main/` receipt remain
unchanged and keep their original identities. This retention task performed
no dispatch, retry, cancellation, benchmark rerun, code repair, tolerance
change, capacity change, GitHub mutation, push, PR, issue closure or publication.
The parent owns specification reconciliation, independent review, integration,
broader readiness and any subsequent execution decision.

## All 18 configured cells

The exact 3 sizes × 3 arms × 2 repetitions (0 and 1) are present once each.
Producer labels are preserved; `ok` below does not override hosted rejection.
Failures have unavailable browser/timing fields, never zero latency.

| Actual rows | Arm | Rep | Producer status | Warm windows | Empty control | Peak host RSS bytes |
| ---: | --- | ---: | --- | ---: | --- | ---: |
| 1,000,000 | `xy-density` | 0 | `host_failed` | 0 | unavailable | 63,471,616 |
| 1,000,000 | `xy-density` | 1 | `host_failed` | 0 | unavailable | 51,265,536 |
| 1,000,000 | `plotly-aggregate` | 0 | `ok` | 32 | producer ok | 371,736,576 |
| 1,000,000 | `plotly-aggregate` | 1 | `ok` | 32 | producer ok | 374,538,240 |
| 1,000,000 | `datashader-aggregate` | 0 | `ok` | 32 | producer ok | 433,635,328 |
| 1,000,000 | `datashader-aggregate` | 1 | `ok` | 32 | producer ok | 433,504,256 |
| 100,000,000 | `xy-density` | 0 | `host_failed` | 0 | unavailable | 1,926,840,320 |
| 100,000,000 | `xy-density` | 1 | `host_failed` | 0 | unavailable | 2,010,923,008 |
| 100,000,000 | `plotly-aggregate` | 0 | `ok` | 32 | producer ok | 1,964,638,208 |
| 100,000,000 | `plotly-aggregate` | 1 | `ok` | 32 | producer ok | 1,953,906,688 |
| 100,000,000 | `datashader-aggregate` | 0 | `ok` | 32 | producer ok | 2,031,321,088 |
| 100,000,000 | `datashader-aggregate` | 1 | `ok` | 32 | producer ok | 2,027,634,688 |
| 1,000,000,000 | `xy-density` | 0 | `host_failed` | 0 | unavailable | 19,377,995,776 |
| 1,000,000,000 | `xy-density` | 1 | `host_failed` | 0 | unavailable | 19,371,212,800 |
| 1,000,000,000 | `plotly-aggregate` | 0 | `ok` | 32 | producer ok | 16,327,245,824 |
| 1,000,000,000 | `plotly-aggregate` | 1 | `ok` | 32 | producer ok | 16,342,728,704 |
| 1,000,000,000 | `datashader-aggregate` | 0 | `ok` | 32 | producer ok | 16,415,752,192 |
| 1,000,000,000 | `datashader-aggregate` | 1 | `ok` | 32 | producer ok | 16,427,057,152 |

There are six XYG `host_failed` attempts and 12 competitor producer-`ok`
attempts. Competitor attempts retain **384 warm windows** (24 pans + eight
zooms each) and **12 separate empty controls**, all producer-labeled correct.
No cell ended with a recorded timeout or RSS-limit status.

## Blocking evidence and diagnosis

All six XYG hosts exited with code 1 in `host_prepare`, before `META`:

```text
ModuleNotFoundError: No module named 'benchmarks'
```

Their retained traceback points to `benchmarks/_ux_comparison_host.py:58`,
`from benchmarks._ux_comparison_oracle import SourceOracle`, called by
`_ux_live_host.py:410`. The producer launches that host by file path
(`bench_density_comparison.py:171–185`). The surrounding source loader has a
sibling-module fallback, while this package-qualified oracle import does not.
The observed child context cannot resolve `benchmarks`; this is a harness
import failure, not an XYG aggregation, memory or speed result. No local
reproduction or fix was attempted.

The new source/grid oracle is **unmeasured for every XYG cell**: no browser
checkpoint, emitted estimate E, raw encoded grid binding, adopted decoded
hash, numerical validation clock, or source-to-grid proof exists. Source
creation retained the 96 requested-window C/H counts and upper-boundary
exclusions, but those cannot substitute for missing XYG E/grid observations.
No old report exemption or repaired metadata is applied.

The hosted verifier rejects the first 100M Bokeh cell's cold binding.
Metadata inspection finds the same shape disagreement at four cold
`visible-complete` checkpoints (100M/1B × both repetitions):

| Rows | Reps | Host last grid / backend revision | Browser adopted raster / revision | Host mass and expected count |
| ---: | --- | --- | --- | ---: |
| 100,000,000 | 0, 1 | 512×512 / 2 | 400×400 / 0 | 100,000,000 |
| 1,000,000,000 | 0, 1 | 512×512 / 2 | 400×400 / 0 | 1,000,000,000 |

The historical verifier at lines 725–731 requires backend grid shape to
match the adopted raster shape, a valid grid digest, and positive backend
revision. The count/mass fields equal N; those fields alone do not establish
that the observed backend grid is the one currently displayed. A cold
adoption/observation sequencing disagreement is a hypothesis, not a proven
root cause. This evidence does not establish wrong aggregate counts, a
Datashader capacity limit, or permission to relax the verifier.
`diagnosis.json` preserves all six original failure cells and all four
mismatched checkpoint/output records. No large-report verifier ran locally.

## Descriptive metrics, subject to hosted rejection

All 12 competitor producer-completed repetitions recorded 512×512 warm
rasters and no exact-point fallbacks. Both repetitions appear separately.
Times are ms, rounded to one decimal; p50 is the median of 32 recorded
`paint_stable_ms` observations, and p95 selects sorted index
`floor(.95*(32−1))`. These programmatic request-to-first-stable-paint clocks
include adapter, validation and readback work; they are not natural gesture
latency, FPS, pure kernel timing or normalized competitor rankings. Cold
stable/confirmed clocks follow host preparation. Datashader's lazy first
raster/JIT can occur after its small host build clock. OS/JIT caches were
not flushed.

| Rows | Arm | Rep | Host build / prepare | Cold stable / confirmed | Warm p50 / p95 | Peak browser RSS bytes | Warm body bytes |
| ---: | --- | ---: | --- | --- | --- | ---: | ---: |
| 1,000,000 | `plotly-aggregate` | 0 | 821.0 / 1085.4 | 402.1 / 549.8 | 135.6 / 138.9 | 1,361,051,648 | 4,307,412 |
| 1,000,000 | `plotly-aggregate` | 1 | 431.3 / 707.1 | 369.6 / 505.0 | 137.8 / 139.1 | 1,369,669,632 | 4,307,412 |
| 1,000,000 | `datashader-aggregate` | 0 | 21.5 / 2168.7 | 427.8 / 577.8 | 184.8 / 203.9 | 1,356,824,576 | 33,597,888 |
| 1,000,000 | `datashader-aggregate` | 1 | 10.3 / 2123.9 | 399.3 / 554.1 | 185.1 / 199.4 | 1,362,526,208 | 33,597,888 |
| 100,000,000 | `plotly-aggregate` | 0 | 775.1 / 1573.0 | 384.0 / 527.4 | 650.0 / 671.6 | 1,322,598,400 | 5,712,610 |
| 100,000,000 | `plotly-aggregate` | 1 | 771.3 / 1561.1 | 374.9 / 511.8 | 647.5 / 671.5 | 1,321,025,536 | 5,712,614 |
| 100,000,000 | `datashader-aggregate` | 0 | 10.3 / 2769.8 | 316.6 / 465.8 | 615.1 / 634.9 | 1,335,508,992 | 34,647,070 |
| 100,000,000 | `datashader-aggregate` | 1 | 10.4 / 2779.5 | 308.6 / 440.9 | 617.1 / 636.2 | 1,337,163,776 | 34,647,070 |
| 1,000,000,000 | `plotly-aggregate` | 0 | 4808.5 / 10487.4 | 393.1 / 533.6 | 4998.7 / 5304.9 | 1,286,258,688 | 4,935,761 |
| 1,000,000,000 | `plotly-aggregate` | 1 | 4737.8 / 10415.1 | 377.8 / 516.4 | 5087.1 / 5316.2 | 1,277,247,488 | 4,935,770 |
| 1,000,000,000 | `datashader-aggregate` | 0 | 10.7 / 9637.1 | 316.0 / 460.5 | 4116.0 / 4370.3 | 1,270,890,496 | 34,647,002 |
| 1,000,000,000 | `datashader-aggregate` | 1 | 10.6 / 9598.2 | 312.5 / 446.9 | 4110.1 / 4354.0 | 1,277,657,088 | 34,647,002 |

`summary.json` retains unrounded values, all cell statuses, host metadata,
cold/empty controls, cold/terminal cumulative transport, retained-column
observations, and every source manifest. The original report retains every
warm step. Body bytes measure WebSocket application-message bodies only;
HTTP/bootstrap, numerical-validation HTTP, framing, compression, TLS and
network-stack costs are excluded. Peak RSS is sampled process-tree RSS every
50 ms, can double-count shared mappings, and is neither an allocation delta
nor GPU memory. Unavailable XYG clocks/body bytes stay null.

`plotly-aggregate` is **Plotly + Datashader + Tornado**, with base64 PNGs,
not native Plotly aggregation. `datashader-aggregate` is one combined
**hvPlot/HoloViews/Datashader/Panel/Bokeh** server stack. Their preparation,
validation work, shading and integration differ. The rejected report and
absent XYG path prevent any winner or comparative acceptance claim.

## Actual inputs, versions, sources and limits

The retained step-environment lines and report argv agree: experiment
`density-comparison`; sizes `1000000,100000000,1000000000`; arms
`xy-density,plotly-aggregate,datashader-aggregate`; two repetitions; f64-memmap;
1,000,000 source-generation chunk rows; 300s per preparation/browser phase;
15s per window; 20GiB (21,474,836,480 bytes) RSS guard per process tree; 20GiB
source-disk guard; `hardware_gl=false`, with no `--hardware` argument.
`actual-values.json` separates requested values from observed hosted values.
The original workflow-dispatch request body is not exposed in the retained
REST responses; actual values are bound by log env, argv and workflow source.

The existing Blacksmith macOS 15 M4 lane records 12 CPUs and
51,539,607,552 system-memory bytes (48GiB), Darwin 24.6.0 / arm64.
Python is **3.12.10**, NumPy **2.4.6**, Numba **0.66.0**, llvmlite **0.48.0**;
the constrained environment check succeeded. Other measured versions:
Plotly 6.9.0, Datashader 0.19.1, hvPlot 0.12.2, HoloViews 1.23.1,
Bokeh 3.9.1, Panel 1.9.3, pandas 3.0.3, Tornado 6.5.7, Pillow 12.3.0,
psutil 7.2.2 and websocket-client 1.9.2. The hosted log and report preserve
full executable paths and versions: Chrome for Testing 149.0.7827.55,
Node 22.23.4, Rust/Cargo 1.96.0. Numba/OpenMP/OpenBLAS threads were each 2.
The prior NumPy 2.5 import incompatibility is not observed in this run.

Software GL is the launch request; **actual renderer is unmeasured**
(`browser_renderer_observed: null`). No hardware-GPU result follows.

Real two-column little-endian f64 files were generated under
`independent-streams-f64-v1`, seed 20260713. Source generation includes
writing, hashing and independent chunked C/H counts. Exact column hashes,
x-then-y hashes, lengths, domains and all windows remain in the report.

| Actual rows | Each x/y file bytes | Total source bytes | Source creation ms | Source peak RSS bytes |
| ---: | ---: | ---: | ---: | ---: |
| 1,000,000 | 8,000,000 | 16,000,000 | 312.8 | 76,644,352 |
| 100,000,000 | 800,000,000 | 1,600,000,000 | 7439.3 | 1,674,182,656 |
| 1,000,000,000 | 8,000,000,000 | 16,000,000,000 | 74351.4 | 16,187,277,312 |

Source files were deleted by the producer after measurement and were never
regenerated locally. The 1B source is **16,000,000,000 bytes, smaller than
48GiB RAM**: this supplies no larger-than-RAM proof. Competitor canonical
admission observations report shared pointers/mappings; Bokeh also records
actual backend DataFrame input observations. These do not exclude transient,
backend, native or derived allocations. XYG failed before admission/build
observations were reported. Actual disk high-water, GPU memory, CPU work,
HTTP/bootstrap costs, natural gestures, hover/selection/exact-drill parity,
colored competitive sources and release/candidate artifact qualification are
not established. Full #108 acceptance and publication remain blocked.

## Lossless retention and safe inspection

Original artifact `ceiling-benchmark-12552978274.zip`: **152,055 bytes**,
SHA256 `33b458b35d403af9ccb7d437688c3ec7f9822c5ca3484f7db2fd9dd3d98a9d4f`, equal to GitHub's
`sha256:33b458b35d403af9ccb7d437688c3ec7f9822c5ca3484f7db2fd9dd3d98a9d4f` and the upload log digest.
Its sole member `_temp/density-comparison-959e1004924774711a35df7ab1317cca30b18d68.json` is
**3,209,979 bytes**, SHA256
`0f75c84180113672331f3c80f1cb8f42f69782bb458cf9e1c14277be07bc5b4e`, CRC32 `e8693e8c`.
ZIP CRC and original-member bytes match the gzip-decoded retained report.
No raw JSON bytes were rewritten. Deterministic gzip uses mtime zero and no filename.

`job-120816502776.log.gz` retains **96,544 complete original job-log
bytes**, decoded SHA256
`dcc363aec594668204644a424af2320ff570caf28fbeff43b9c761d341c7f25f`. It came directly from
`gh api repos/CurateLabs/xyg/actions/jobs/120816502776/logs` into this owned
path, never `gh run view --log` or its shared `/tmp` cache.

Run, workflow, attempt, jobs, job, artifacts, artifact and source-commit API
responses are retained separately. The in-progress observations have separate
names. `retention.json` records retrieval, endpoints, ZIP members and hashes.
`manifest.json` records file and decoded gzip hashes/lengths; `SHA256SUMS`
covers every retained top-level file except itself. `task-tmp/` contains only
transient local-tool files and is excluded from the receipt and commit.

`source-bindings.json` matches all 16 measured harness/lock file hashes and
three product-tree digests to historical source `959e1004`. It inventories
149 Python, 205 Rust and 52 TypeScript files. Exact historical workflow,
verifier, oracle-contract and diagnosis-related producer snapshots are
retained as `.txt`; build/lock metadata is hash-bound to historical Git blobs.
Loaded-native hash
`27425601a036c384b4d2357d700669b9a6f2f1d25381535a4cfa9bf8b65a3b3e`
and client hash
`b7bf5702e7d28647b651777c364a8ec6c82403e145d16475ef8e06484b8ddfce`
are producer-recorded identities. Executable bytes were not uploaded, so no
independent local executable-byte check is claimed or replaced by a rebuild.

From repository root:

```bash
python3 benchmarks/results/live-aggregation-2026-10-24/hosted-main-959e1004/inspect_evidence.py
```

This checks metadata, hashes, ZIP CRC/member equality, historical Git objects,
actual argv, pinned versions and exact 18-cell coverage. It creates no source
arrays and imports no numerical/native libraries. The retained **hosted
rejection** is the authority-context verifier result; no Darwin/Actions
context was emulated locally. `commands.txt` records retrieval, inspection and
historical producer/verifier commands. `validation.txt` records repository
hooks and full-worktree Ruff checks. Parent independent review and integration
remain required before treating this receipt as incorporated evidence.
