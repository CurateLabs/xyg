# Retained geographic scale evidence, 2026-10-08

This directory records native execution of the working-tree #50 retained-source
processor through the real shared Rust `geo_scale_protocol`. It is evidence for
the measured source/binary snapshot, before integration. It does not close #50
or establish a browser/controller, network, competitor or interactive-scale win.

Authority: dossier [§12](../../design-dossier.md#12-benchmark-harness-built-in-phase-0-run-every-phase),
[§22](../../design-dossier.md#22-chunk-statistics-zone-maps--cheap-answers-to-expensive-questions)
and [§28](../../design-dossier.md#28-lod--tiling-contract--exact-rules-per-trace-kind);
[retained source](../../design/geo-retained-source.md),
[source session](../../design/geo-source-session.md),
[LOD](../../design/geo-lod.md), [Scene lowering](../../design/geo-lod-scene.md),
[wire/lifecycle](../../design/geo-scale-protocol.md), and
[membership](../../design/geo-membership-session.md).

## Reproduction

From the repository root:

```sh
cargo build --release -p xyg-engine --bin geo_scale_bench
uv run python scripts/bench_geo_scale.py --rows 1000 100000 1000000 10000000 100000000 --no-build
cargo clippy -p xyg-engine --bin geo_scale_bench -- -D warnings
uv run ruff check scripts/bench_geo_scale.py
uv run ruff format --check scripts/bench_geo_scale.py
```

The bin is automatically discovered at
`crates/xyg-engine/src/bin/geo_scale_bench.rs`; there is no Cargo manifest change
or extra dependency. The Python wrapper performs orchestration and captures
the OS per-child maximum RSS using macOS `time -l` / Linux GNU `time -v`.
Rust performs every source decode, temporal match, camera projection, LOD
decision, cell calculation, membership predicate and Scene lowering. Native
C ABI marshal overhead is outside this Rust protocol benchmark.

`--out /tmp/geo-scale-smoke --rows 1000` can isolate a smoke run. Measured
`--rows` values above 100M fail before execution. A separate 1B **planner-only**
child invokes `GeoSourcePlan::new(1_000_000_000,65536)` and generates zero data
rows. It is never labelled measured ingest/render/interaction evidence.

## Dataset and bounded memory

Each input is a homogeneous EPSG:4326 Point source with valid canonical f64
coordinates and literal IDs `u64MAX - original_row`. Coordinates are deterministic
unordered modular sequences covering longitude [-170,170) and latitude [-60,60).
One source-order chunk of at most 65,536 rows is generated at a time. Original
coordinates/IDs are never replaced by sampled representatives. Complete source
arrays, source-sized masks, membership CSR and gigabyte source files are absent.

Chunk-aligned signed-i64 microsecond intervals are `[chunk_index % 4,
chunk_index % 4 + 1)`. The time-filter query is instant 0. This deliberately
allows authentic coarse temporal pruning; it is not an unordered-time worst
case. Scalar/per-row style/state attachments are not exercised. The uniform
style is an explicitly supplied RGBA/diameter/style payload. Aggregate lowering
uses the documented count color/area rule and drops diameter/symbol/stroke
channels (`dropped_channels=7`); these cells are not uniformly styled source
features. The hard direct limit is 32,768 vertices; the configured Cluster cap
is 32,768 cells and every `grid_capped` reduction is recorded.

Canonical chunks are regenerated on every real read ticket and passed through
shared pure command 20. Ingestion pushes them through commands 1/2/3; command 21
reads the frozen manifest. Each source session created by command 4 authenticates
all canonical chunks before its summaries can prune. Commands 5/6/7/8 drive count
and aggregate passes. External chunk/request storage is dropped before command 8
acknowledges ownership release. Commands 11/23 prepare/read immutable leased
Scene32+typed provenance packets; copies are dropped before command 10 disposes
the handle. No mutation runs twice for length discovery.

The hard global processor ledger is 128 MiB; derived/cache admission is the
separate shared 384 MiB ledger. Failure is an explicit stable `ResourceLimit`
and stops the measured case. The script records incomplete metrics and exits 3;
it does not turn an admission failure into a successful massive run. Reported
`processor_sampled_peak_bytes` is a lifecycle-boundary **reservation sample**,
not an allocation high-water mark. The OS maximum RSS measures actual child
memory, including native runtime, regeneration and export allocations. Neither
metric measures browser heaps, VRAM, unrelated processes or multiple WASM
instances. They are not interchangeable.

## Measured operations and output contracts

| Phase | Actual operation / interpretation |
| --- | --- |
| Ingest | Generate, canonical-encode and push every row; finish/read its manifest |
| Source validation | Re-read and authenticate every persisted chunk before trust |
| First Scene | Full world-covering 800×600 camera, direct or explicit bounded Cluster grid; no GPU first paint |
| Time filter | Instant0, exact half-open selection before projection, authentic chunk-summary pruning |
| Pan | Center longitude 30 at zoom 0; complete source scan/recompute, no spatial-index or warm tile reuse |
| Zoom | Same center at zoom 1; complete count/aggregate recompute |
| Revision update | Increase camera/time/layer/style/state revision identity; recompute the same uniform style/source; not incremental source append |
| Cell membership | Densest actual Rust cell, up to 3 exact 4096-row pages, opaque Rust cursor; report any remaining cursor rather than claiming full membership |
| Five views | Five separately validated retained sessions, one outstanding read ticket at a time, one serial round-robin CPU schedule, and five leased Scene packets retained together |
| Native CPU picking | 256 deterministic CSS-pixel Topmost queries against the immutable SceneData using real commands 14/23/10; raw samples and nearest-rank p50/p95 include protocol allocation, serialization, copying and disposal, with no browser/GPU or host marshal timing |
| Painter encode | Existing Rust Scene32→XYPB15 encoding; no browser upload/draw or GPU pick |
| Static SVG/PNG | Existing native Scene exporter at 800×600, actual encoded output bytes; generated local source needs no provider attribution |

The five-view source-validation phase is separate from compute+Scene generation.
It is not five hardware-parallel workers or dashboard FPS. It also exposes the
current cost of authenticating the same persisted manifest independently per
session; a future shared trusted-source coordinator must preserve admission and
source identity before claiming reuse.

Each raw run contains source/chunk/canonical byte counts, exact visible and
projected vertex counts, aggregate/grid-capped telemetry, grid shape,
Scene/provenance/packet sizes, membership work/read/page counts, painter/export
sizes, elapsed phases and actual OS RSS. Completed runs report the processor
ledger after all session/Data cleanup. No aggregate cell is named an original
feature; membership returns full-u64 IDs and source/chunk row identity.

`environment.json` records machine/toolchain, working-tree head/status, source
SHA256 fingerprints of all engine Rust sources, measured binary SHA256, and an applyable source patch. Before measurement the harness independently reconstructs every captured file byte-for-byte from the base commit plus that patch. It then runs a private immutable copy of the measured executable. Final source drift is recorded separately. Each `<rows>-r1.json` contains
raw phase objects; matching stderr files preserve OS RSS and bounded progress.
`summary.json` collects complete/failed measured runs and a separate planner
case. Numeric JSON here is **offline benchmark evidence**, never the product
paint/authoring wire.

## Conditions and remaining gates

The root results measure the frozen final command-14/immutable-SemanticData/painted-style-guard source captured in `measured-source.patch`. For exact reproduction, check out `environment.json`'s `source_patch_base` in a clean temporary clone, apply the patch with `git apply`, then run the commands above with an output directory outside the preserved evidence. The patch includes the harness and its auto-discovered Rust binary. Changes after the run must be compared with the captured source rather than inferred from the branch name.

`historical-prehit/` preserves the earlier development run. Its pre-hit/pre-guard source contents were not saved and failed exact reconstruction; it is historical evidence only, never final-policy evidence. That run overlapped Rust/WASM builds, Binaryen optimization and tests. The final run also does not establish a quiet host: other host/browser/WASM development may run, and one execution per scale supplies no confidence interval, regression tolerance or competitor comparison. The native CPU-pick p95 is an empirical percentile of the 256 specified deterministic queries, not an end-to-end interaction percentile or a randomized workload distribution.

The run reports GPU first paint, pan FPS, GPU/controller pick, browser/controller, network
tiles, VRAM, incremental append, retained per-row style/state/scalar attachment
and competitor timings as **unmeasured**. It does not exercise geographic tile
selection/cache reuse, vector/polygon simplification at 100M, frozen HTML browser
replay, provider attribution/network policy or all seven catalog families at
massive scale. The source is procedurally regenerated in memory; real filesystem
or network latency is excluded.

Bounded full-source scans remain linear in source work. A completed 100M run
establishes execution/memory/packet evidence for this specific path, not the
O(visible tiles) interactive pan/zoom requirement. Controlled repeat timing, real public host/controller paint/pick, warm indexed/pyramid
work, five-view end-to-end UX and relevant competitor baselines remain adoption
gates.

## Completed final-source measurements

All five measured scales returned status 0 and a zero processor ledger after cleanup. Exact source reconstruction passed; the end-of-run source drift map is empty. `validation.json` records checks for exact first-view visible row counts, direct/aggregate projected work, 256 hit samples, five retained views with one pending ticket, page bounds, CPU admission and cleanup. The largest child RSS was 43.25 MiB. The sampled processor reservation reaches 128 MiB during conservative export scratch admission; that reservation is not actual resident memory.

| Source rows | Ingest → first computed Scene (ms) | Pan (ms) | Five-view compute + Scenes (ms) | Native CPU pick p95 (ms) | All phases (ms) | Max RSS (MiB) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000 | 1.60 | 0.53 | 2.17 | 0.006584 | 13.27 | 6.84 |
| 100,000 | 65.21 | 34.53 | 176.89 | 0.005333 | 461.94 | 27.33 |
| 1,000,000 | 564.75 | 351.89 | 2,409.33 | 0.028750 | 5,105.40 | 42.73 |
| 10,000,000 | 7,174.23 | 4,453.32 | 22,855.01 | 0.035458 | 55,688.32 | 43.25 |
| 100,000,000 | 72,088.21 | 45,537.13 | 229,149.90 | 0.060709 | 554,725.91 | 39.28 |

Five-view source authentication is additional work: 1.57/65.93/729.08/8,429.56/90,225.98 ms at the respective scales, included in all-phases time. The 100M time filter took 11,194.01 ms, zoom 46,415.82 ms and revision recompute 45,943.98 ms. These are full source/query costs under the stated uncontrolled development conditions, not target interactive latencies.

The 100M first Scene packet is 1,195,000 bytes: 474,744 Scene bytes plus typed reduced provenance/header. Three membership pages return 12,288 exact rows of the selected cell's 19,394 rows and retain a next cursor; complete membership is not claimed. Actual final-frame SVG and PNG encoders produced 1,337,015 and 116,384 bytes respectively. Those output sizes describe the final pan/zoom/revision frame, whereas the first-packet size describes the world-view frame. The separate 1B planner generated no data and is never included in the measured table.

The measured binary SHA256 is `c4a30b7dd6637e8b4905ee0568bbd64227dc52b55e829be07f9f23ab50365434`. The independently reapplied patch SHA256 is `5101cfd07fcbfd708b7bdc1391233d7c4b423a4f36b3807c3eab73e2a382240a`, against base `4932b14cc55ad20036572459ed46f88ec583520d`. Preserve the patch bytes as captured; changing or formatting it invalidates this provenance hash.
