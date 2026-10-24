# Live aggregation comparison foundation (#11)

Status: bounded local evidence foundation, not competitive scale acceptance.
Extends the [benchmark methodology](../benchmarks/methodology.md) without changing
its measurement or publication gates. See dossier §§5, 12, 17, 28–29 and
[tier-3 testing](tier3-testing.md). The original real-wheel run is
[2026-10-24](../../benchmarks/results/live-aggregation-2026-10-24/README.md).
Its producer is immutable commit `51975d5d6f5c073e0a4b60a404f8349e45c6775c`:
the raw report identifies its parent `71e48b67` plus the then-dirty source hashes.
The [equal-window follow-up](../../benchmarks/results/live-aggregation-2026-10-24/equal-window-v2/README.md)
is a separate programmatic experiment with its own producer hashes. Its raw
JSON reports are losslessly gzip-compressed after measurement; decoded-byte
hashes and original producer bytes remain inspectable. Never
rewrite the original 18 cells or compare their archived harness hashes to
current source as a validation requirement.

## Arms and comparison boundaries

`benchmarks/bench_ux.py` retains the existing `xy`, `xy-exact`, `plotly`,
`matplotlib`, and `datashader` arms. `plotly` is still raw `px.scatter` HTML;
it is never relabeled as server aggregation. `datashader` is **one combined
hvPlot/HoloViews/Datashader/Panel/Bokeh-server stack**, with `resample_when=200000`,
not five independently measured competitors.

Three explicit density-navigation arms make a more relevant overview comparison:

| Arm | Actual implementation | Sparse-view behavior |
| --- | --- | --- |
| `xy-density` | `density=True`, production Rust payload, ChartView and XYBF WebSocket dispatcher | shipped client can drill to exact marks; initial forced density is not a promise of raster-only final output |
| `plotly-aggregate` | Plotly axes and wheel handling; benchmark Tornado WebSocket host runs Datashader `Canvas.points(..., count())`, log count shading and PNG encoding | stays raster; no point hover or exact drill |
| `datashader-aggregate` | same hvPlot/HoloViews/Datashader/Bokeh server as `datashader`, without `resample_when` | stays raster |

All use every actual source row for their overview aggregate, not a subsampled
raw-scatter competitor. They share an all-row count-density navigation task,
not identical pixels, grids, shading, cache policy or interaction features.
Plotly's integration is **Plotly + Datashader + Tornado**, not native Plotly
aggregation, an official Plotly benchmark adapter, Dash, or a Plotly-resampler
scatter implementation. It sends PNGs as base64 inside JSON, including that
expansion in measured socket body bytes. It is deliberately a small real
integration rather than an assumed competitor limit.

The existing 42 real wheel inputs at 33 ms cadence remain the workload.
Wheel sensitivity, event coalescing, plot margins, actual raster dimensions
and final domains differ between libraries. Checkpoint evidence retains
home/final domains, raster extents or XYG drill state where available. These
are comparable *navigation deployments*, not equal-final-window aggregation
microbenchmarks. Raw marker rows must not be ranked against density rows as a
same-output win. No winner or universal speedup follows from a single local
trajectory. The optional programmatic profile below adds bounded equal-window pans/zooms.
Real-gesture equal-window latency, hover, selection, exact drill parity,
cold disk, colored competitive sources and massive-scale evidence remain gaps.

## Source and provenance

`_ux_comparison_data.py` preserves the old workload's NumPy default_rng seed
20260713 and its exact f32 arithmetic: correlated Gaussian x/y, with five
planted tail sentinels replacing source rows. Every host and the raw Plotly
builder uses this generator. The runner independently regenerates and hashes
that workload and records whether the host's source identity matches it.

Each identity includes actual row count, dtype, column names, 8N source bytes,
sentinels, seed, generator ID and SHA256 of little-endian x bytes then y bytes.
There are **two real resident f32 source columns**, not three f64 columns,
a memmap, spill store, an integer-only planner fixture or a row multiplier.
XYG may widen its canonical columns internally; host RSS includes that cost.

Reports retain argv, viewport, limits, temp root, thread settings, CPU affinity,
system memory, Python/platform/tool versions, component versions (including
Panel, Tornado, NumPy, Numba and llvmlite), git commit/dirty state, individual
harness/lock hashes, product source tree hashes, built client hash, and the
actually loaded native library path/hash. Preparation and hashing cost is not
silently substituted for browser navigation. Dirty-tree measurements remain
identified as exploratory; methodology publication gates still apply.

## Clocks, memory and transport

- `python_build_ms`: fresh-process chart build; source generation excluded.
  XYG includes payload construction; raw Plotly includes HTML serialization;
  Plotly aggregate includes DataFrame construction, first Datashader aggregate,
  its mass oracle, shading, PNG encoding and extraction of Plotly.js. hvPlot
  creates a lazy server application; its first actual raster/JIT can fall in
  browser navigation. JIT and OS disk caches are not flushed. These build
  subclocks have different laziness; use `host_prepare_wall_ms` and navigation
  together when assessing startup and retain both.
- `host_prepare_wall_ms` for live XYG and aggregation hosts: process spawn
  through META, including imports, source generation/hash, build and server
  setup. Raw Plotly retains its separate builder duration and artifact size.
- `first_frame_ms` / `visible_complete_ms`: fresh-browser navigation through
  observed pixels / sentinel-correct stable pixels, after host preparation.
  `first_frame_ms` is the probe's first nonempty readback, not a browser FCP
  or a proven correct picture.
- `gesture_frame_p50/p95/max_ms`: warm animation-frame intervals during the
  fixed-input trajectory, **not input-to-pixel latency quantiles**.
  `zoom_to_final_ms` is warm first-input to final correct stable pixels;
  `settle_ms` is last-input to that frame. Neither is a standalone single-input
  latency percentile. The unchanged probe performs full readbacks, so these
  include probe overhead.
- `host_peak_rss_bytes` (legacy alias `python_peak_rss_bytes`) and
  `browser_peak_rss_bytes`: distinct process-tree RSS peaks sampled every
  50 ms from spawn through probe completion. These include runtime/build
  costs, are not allocation deltas, and may double-count shared mappings.
  They are not GPU memory measurements. Per-tree RSS limits terminate the
  tree at the next observation and can overshoot between samples.

Transport retains cumulative snapshots at `visible-complete`,
`settle-complete` and terminal result, plus a warm trajectory delta. CDP counts
WebSocket message bodies for live arms, including Bokeh binary payloads;
text uses UTF-8 length and binary CDP payloads are base64-decoded before
counting. Control opcodes are excluded. XYG and Plotly aggregate additionally
retain page accounting and host `/transport_metrics` snapshots. Host snapshots
are cumulative for the single fresh session. A counter is an application
body-byte measurement, **not HTTP/bootstrap assets, WebSocket framing,
compression, TLS, TCP/IP, retransmissions, export size or network-stack bytes**.
A raw Plotly HTML arm can have zero WebSocket bytes while delivering source
rows in HTML; `html_bytes` records that separate artifact, never a zero-cost
transport claim. Bokeh's page does not expose the XYG-specific accounting API;
its body bytes are CDP observations, not invented host totals.

## Correctness and failure cells

The original sentinel/domain/full-readback pixel-stability probe remains intact.
A successful run requires the target sentinel to remain painted after a
proved domain contraction and ten stable frames. The raster-specific guards
strengthen that foundation:

- Plotly aggregate rejects old sequence numbers and checks the applied raster
  domain against the actual Plotly axes. Readback reconstructs the exact PNG
  in the displayed SVG image's measured DOM rectangle; missing, pending or
  stale images return no surfaces. It does not synthesize points or infer
  visible pixels from an aggregate count. Each served PNG has a retained hash,
  grid shape, requested domain and an independent inclusive-window NumPy
  count equal to the Datashader grid mass. The oracle cost is in the measured
  request path. Requests are latest-view coalesced (75 ms trailing debounce,
  at most one pending request); no claim of 42 server computations is made.
- Bokeh aggregate readback additionally requires its actual Image glyph's
  x/y/dw/dh bounds to match the current axes before accepting pixels. Its
  archived probe is sentinel/domain/stability evidence, not independent
  per-cell count conservation or hover correctness.
- XYG retains the shipped binary bridge and production readback. These runs
  do not add independent whole-grid conservation, tile-reuse, spill, or
  exact-row hover assertions to that existing probe.

Failures are retained as cells, with stage/error data and observed transport
where available. Unsupported is not zero latency or a competitor failure:
raw `px.scatter` uses SVG at N≤1000, and the existing canvas pixel oracle cannot
validate that path. It records `unsupported_svg_readback` with build/source/HTML
metadata, without a browser timing. Missing dependencies, host construction
failure, timeout, memory limit and oracle failure likewise do not yield wins.
Hosts use finite preparation timeouts; host and browser each have separate
RSS caps. The timeout is per preparation/browser phase, not a global sweep
supervisor. Whole-run cancellation remains the caller's responsibility.

## Bounded reproduction and limits

Use the repository benchmark lock in an optional environment; no product
runtime dependencies are added. The retained README gives exact environment,
commands, browser path and artifact hashes. Put `TMPDIR` on the isolated
worktree: the shared `/tmp` per-user quota is exhausted in this environment.
The browser executable here is the installed Playwright Chromium binary,
invoked by the repository's existing CDP workflow. `/usr/bin/google-chrome-stable`
is absent; the path is explicit rather than silently using another browser.

Local measurements stop at one million actual rows. This is a measurement
scope, not a billion-row impossibility claim. Three f64 columns require 24 GB
of file data; the new optional two-f64 source requires **16,000,000,000 bytes**
at a true billion rows. Neither mapped-file size is itself RSS. The existing
manual `ceiling-benchmark.yml` lane documents Blacksmith macOS 15 M4, 48 GB RAM,
250 GB SSD and a 20 GiB per-process-tree RSS guard. Root may wire the optional
comparison into that existing lane after review. No new workflow, job, paid
capacity, cap increase or hosted dispatch is introduced here. Whether a true
1B mapped source plus each backend's derived state fits must be measured;
record strict memory/disk/timeout failures rather than promising it fits.
Do not extrapolate local timings or close #11 from these results.

## Optional programmatic equal-window profile (v2)

`benchmarks/bench_density_comparison.py` reuses the three existing hosts with
`--comparison-source`. Legacy flags still select the original 42-wheel
profile. This separate experiment directly sets browser ranges; **none of its
timings are real-gesture latency**, and it is not a cache/navigation throughput
benchmark paced at a human input rate.

For each actual source size and each arm it runs two (or explicitly three)
fresh host/browser repetitions. It retains every repetition, not best-of-N.
All arms use identical explicit source extents and a measured **512×512 data
plot area**, with axes/chrome hidden. Outer surface dimensions may differ.
The trajectory calls `_density_spill.windows(extents)` unchanged: 24
half-span overlapping/reversing pans, then eight quarter/half-span adjacent
zooms. Each step waits for correctness and ten stable readbacks before the
next request. A separate outside-source empty-window control follows the 32
steps and must have zero opaque nonwhite interior pixels. That control is not
an extra pan/zoom timing sample.

The first v2 f32 sweep is retained with its two strict-object-identity
collector failures on 1M reversal pans. It was not relabeled successful.
Exact measured producer files are archived as text under `f32-producer/`.
A bounded two-repetition XYG 1M follow-up with the bytewise grid-equivalence
check completes that cell; its original failure trace remains inspectable.
The f64 sweep uses the same final validator and releases hash-scan mappings
before reopening canonical maps, avoiding needless duplicate source mappings.

The new runner requires actual browser axes to equal each requested window.
For Plotly it also requires the currently applied PNG revision and domain;
for Bokeh it requires the actual Image glyph extent and observed data revision,
plus a matching host-observed Datashader grid count/domain. Merely transforming
an old image cannot pass. The Bokeh adapter sets the real range models and
calls the pinned Bokeh plot view's `trigger_ranges_update_event()` so the
existing HoloViews RangeXY callback receives the completed range change.

XYG calls public `ChartView.setView` and sends one exact-window `density_view`
over its existing XYBF bridge into the production dispatcher. In this opt-in
experiment only, automatic client request scheduling is disabled and the
explicit requested window is marked for adoption, so ordinary cache elision,
ladder overscan and debouncing do not substitute a different request. **Rust
and the production host still own density-versus-points decisions.** No tier
threshold, density implementation or drill policy is patched. If the reply is
a raster, its actually adopted/drawn extent must match the target. Reversal pans
may select a retained raster with an older revision; that is accepted only
when its extent, dimensions and **every grid value** equal the current reply
for this immutable source. The requested/reply and actually rendered revisions,
revision kind and verified equivalent-cache reuse are recorded independently;
a stale raster for a different extent/content still fails. If it is an
exact-points fallback, the adopted subset's real coverage may be larger than
the target: the axes must still match, that coverage must contain the target,
and the decoded actual GPU point buffers must contain exactly the independent
source count inside the clipped target window. The payload count, clipped
count, subset coverage, revision and `exact_fallback` are recorded. Such rows
are **not raster-versus-raster performance wins**, and a mixed-mode aggregate
ranking is not produced. This deliberately measures explicit dispatcher
round-trips, not unmodified automatic XYG navigation/cache behavior.

The page retains request-start/return, first observed axis adoption, first
observed output adoption, first stable-paint and stability-confirmation times
for every step in one browser `performance.now()` clock. These include full
readback/probe overhead and are observations rather than internal callback
timestamps. An opaque pixel differing from the white chart background counts
as nonblank, excluding two outer pixels to ignore frame chrome; the empty
control requires none. Full RGBA hashes test stability. Plotly readback uses
the displayed SVG PNG's exact DOM rectangle; Bokeh reads the actual canvas
cropped to its plot frame; XYG reads the actual WebGL buffer.

Every cold checkpoint and warm step retains CDP socket-body totals/deltas,
current and sampled peak host/browser process-tree RSS, actual output mode,
raster shape or subset coverage, and host observations. Cold source creation,
source hash/oracle preparation, host build/preparation and first navigation
paint are separate from the warm sequence. No disk/JIT-cache flush is claimed.
No HTTP/bootstrap bytes or physical GPU memory is inferred from body/RSS data.

Plotly retains its actual all-row Datashader count/PNG oracle, including the
independent chunked NumPy count scan in its request path. Bokeh's observer
uses the already prepared source-window counts for known trajectory windows.
These are inclusive adapter-plus-validation timings; unequal oracle work,
shading and native adaptive grid resolutions prevent pure aggregation-kernel
rankings from these results. No competitive acceptance or winner is claimed. The Bokeh host
observes its **actual** `Canvas.points` result without replacing it: its grid
sum must equal the independent source-window count and it records the raw grid
hash and dimensions. Retained DataFrame and actual Datashader backend-input
pointer/copy observations are separate. XYG exact-point output has the clipped
point-count oracle above; its quantized density grid does not gain an invented
independent per-cell conservation proof from this experiment. Revisions,
extents, mode, source count and rendered pixels are still required. Missing
oracles and exact fallbacks remain explicit limits.

## Optional chunked f64 mapped sources and allocation guards

`_ux_comparison_source.py` leaves `make_data` and the default legacy f32 values
unchanged. For the programmatic default `--profile f32`, a supervised child
writes exactly that original f32 source; each host loads resident f32 columns.
`--profile f64-memmap` instead chunk-generates two real little-endian f64 files
using independent seeded x/noise streams, then reopens read-only maps. This is
a distinct versioned generator, not a relabeling/widening of the f32 source.
Two source generation arrays, producer hash scans and count-oracle scratch use
`--chunk` (default 65,536, maximum 1M); host file validation uses fixed 1 MiB
hash buffers. There is no N-sized generation or hashing temporary in the f64 path. Chunk-size invariance is tested. Exact
file lengths, per-column SHA256, x-then-y SHA256, source extents and all 32
independent chunked window counts are retained. Every host revalidates actual
file lengths/hashes before mapping/loading. No fake N or expanded row multiplier
is admitted. Temporary source files are owned by this runner and removed only
after their cells finish; hashes and reproduction inputs remain in the report.

XYG records canonical pointer equality, shared memory, dtype, byte extent and
memmap ancestry at admission and after payload build. Plotly/Bokeh record their
retained DataFrame columns; Bokeh additionally observes the actual Datashader
input arrays. These observations expose widening/copies honestly but do not
claim the absence of all temporary, native-internal or derived allocations.
Each host's polled RSS still accounts for those costs.

The new controller never creates source arrays. It starts a source-generation
child under the same sampled RSS cap and a finite preparation timeout; failure
cells distinguish source memory limit, timeout and construction failure.
Before creating source directories, files, maps or generator arrays, source
sizes above 1M require all of: f64-memmap; actual Darwin/arm64 with at least
44 GiB system RAM; Actions workflow_dispatch on refs/heads/main; workflow name
`Interactive ceiling benchmark`; and RUNNER_OS=macOS. Hosted caps may not exceed
20 GiB RSS per tree or 200 GiB source disk; local caps may not exceed 2 GiB RSS
or 0.25 GiB source disk. Actual source file bytes must fit the chosen disk cap
and free disk must include 64 MiB reserve. Host loaders repeat the same authority
check. This is an allocation guard, not permission to dispatch that host.
The optional existing-lane integration is described below; actual-scale
measurements remain pending reviewed landing on main.

The programmatic runner records host preparation that remains alive without
`META` at its deadline as `status: timeout`, `phase: host_prepare`, with an
explicit reason. Silent exits before `META` retain `host_failed` and their
return code; a mismatching source retains its reason as well. Cleanup and
sampled RSS observations are retained, so these remain valid failed cells
rather than invalid reports or successful measurements.

Its environment renderer fields describe **requested launch flags**:
`browser_renderer_requested` and the legacy `browser_renderer` alias follow
`--hardware`, overriding any inherited `XY_BENCH_HARDWARE_GL` value. Software
requests use SwiftShader flags; hardware requests use the existing Metal flags.
Neither proves the renderer Chrome obtained. `browser_renderer_observed` is
explicitly null and `browser_renderer_scope` states that the actual renderer
was not measured. Do not publish requested hardware as confirmed acceleration.
Historical report bytes and their producer bindings remain unchanged.

The legacy `bench_ux.py` controller had regenerated both entire identity columns
before host/browser supervision. Independent review of `51975d5d` identified
that as blocking P2 (reviewed diff
`dbbbcdbcb559fed343594ba07a78007421e15b94219c0ef053e7353f44c3e40f`).
The narrow repair rejects legacy resident-source N>1M **before any controller
source generation** and likewise guards the raw Plotly build-child entry point.
Tests replace both generators/builders with failures and prove they are never
called and no output is created on rejection. Existing large ceiling work must
use its supervised harness or the guarded optional mapped experiment. The
original immutable archive is unchanged. Independent review of the follow-up
confirmed the repair, ran all 48 focused tests and a fresh two-repetition 1k
f64 browser sweep across all three density arms (192 windows and six empty
controls). Those bounded checks do not qualify an actual-scale result.

## Existing manual performance lane

The existing `ceiling-benchmark.yml` workflow has an optional
`experiment: density-comparison` choice. Its default remains the original
ceiling ladder. The optional comparison uses the same single documented
Blacksmith macOS M4 job (48 GB RAM, 250 GB SSD, 720-minute job timeout), with
no runner, job or capacity addition. It is main-only and reuses the prepared
native core, client and Chromium. The optional hvPlot dependencies use the
existing comparison lock.

The mapped profile fixes source-generation chunks at 1M rows, source disk at
20 GiB, and each step deadline at 15 seconds. The controller rejects nonfinite
or excessive phase/step deadlines before allocation (maximum 300/15 seconds);
the existing caller memory input is still bounded to at most 20 GiB per tree
by the allocation guard. Local controls remain limited to 1M rows and 2 GiB.
The separate report verifier checks the external requested sizes/arms, source,
windows, outcome coverage and unchanged resource contracts against the actual
run SHA. Honest failure cells remain failures and cannot become a winning
scale claim. Results are programmatic observations including adapter/oracle
work, with the limitations above.

After this facility is reviewed and landed on main, the narrow scale command is:

```bash
gh workflow run ceiling-benchmark.yml --repo CurateLabs/xyg --ref main \
  -f experiment=density-comparison -f sizes=1000000,100000000,1000000000 \
  -f arms=xy-density,plotly-aggregate,datashader-aggregate \
  -f repetitions=2 -f timeout=300 -f memory_gib=20 -f hardware_gl=false
```

This command has **not** been dispatched by the bounded implementation task.
Retain its exact-SHA JSON, execution metadata, environment, source identities
and complete success/failure cells before making actual 100M/1B comparisons.
File size is not RSS: 1B two-f64 rows require 16 GB of mapped source files;
source-plus-derived costs and supported outcomes must be measured rather than
inferred from machine capacity. Larger-than-RAM and whole-#11/#108 acceptance
remain separate outstanding requirements.

## Primary API references inspected

- [Plotly events](https://plotly.com/javascript/plotlyjs-events/): relayout
  notifications and axis range updates.
- [Plotly images](https://plotly.com/python/images/): data-axis raster placement.
- [Plotly performance](https://plotly.com/python/performance/): explicit
  Datashader raster integration as a distinct path.
- [Datashader pipeline](https://datashader.org/getting_started/Pipeline.html):
  count aggregation, shading and live Python re-aggregation.
- [Bokeh deployment](https://docs.bokeh.org/en/latest/docs/user_guide/server/deploy.html):
  exact origin allowlists. Pinned Bokeh 3.9.1 also inspected locally: wildcard
  ports are rejected; its default is `localhost:<actual bound port>`. The host
  binds loopback and the runner navigates to that exact hostname.

Additional primary API checks for v2: [HoloViews frame dimensions](https://holoviews.org/reference_manual/holoviews.plotting.bokeh.element.html),
[Bokeh RangesUpdate](https://docs.bokeh.org/en/latest/docs/reference/events.html)
and the pinned Bokeh 3.9.1 `PlotView.trigger_ranges_update_event` source.
