# Bounded live aggregation evidence — 2026-10-24 (#11)

Exploratory local evidence, **no declared winner or scale acceptance**. Base:
`71e48b67827709ed251ae05b90d010a8cef824eb`, with the source changes identified by
`bounded.json.provenance_sha256` (git dirty=true, reported honestly). This commit
retains that exact harness plus its source-matching raw report. The clean-tree
publication gate in the methodology has not been established by this run.

The [comparison specification](../../../spec/design/live-aggregation-comparison.md)
defines the integration, counters, oracles and limits. The old unarchived UX
headlines remain withdrawn; this archive does not reinstate them.

## What actually ran

One sequential run, 18 cells: 1,000 / 100,000 / 1,000,000 actual rows; six arms.
16 passed the real sentinel/domain/stable-pixel probe. Raw `plotly` at 1k is
`unsupported_svg_readback` (an oracle gap, not a Plotly capability failure).
Raw `plotly` at 1M hit this run's imposed 2 GiB browser process-tree RSS cap
(about 2.004 GiB observed before termination). No browser timing or aggregate
win is claimed from either cell. All nine density-navigation cells passed.
The adaptive `datashader` rows remain in the JSON as **one combined
hvPlot/HoloViews/Datashader/Panel/Bokeh-server stack**.

Every host/builder source hash agrees with the independently regenerated shared
workload. It is two real resident f32 x/y columns, seeded correlated Gaussian
with five planted sentinels; no color column, mmap, spill or fake row multiplier.
XYG's density overview subsequently drills to exact points. The two competitor
aggregate-only arms remain raster. The raw Plotly arm is preserved separately.

## Observations (one sample each, software GL)

This table describes density-navigation deployments, not equal-window or
pixel-equivalent output. `warm` is the complete 42-input trajectory through
final correct stable pixels, **not a single-input p95**. Different wheel
sensitivity produces final x-span fractions of about 0.0005 (XYG), 0.015
(Plotly) and 0.0001 (Bokeh); these are not equal-final-window aggregate timings.
Build clocks also differ in laziness; the raw JSON retains host preparation
and navigation separately. All times are ms and memory is MiB of process-tree
RSS, including runtime/baseline; shared mappings can be counted repeatedly.

| Rows | Arm | Build | Navigation → stable | Warm trajectory → stable | Host peak MiB | Browser peak MiB | Load WS body B | Warm WS body B |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000 | `xy-density` | 14.7 | 2288.3 | 2452.8 | 61.9 | 1435.6 | 206,736 | 1,026 |
| 1,000 | `plotly-aggregate` | 1379.1 | 2626.2 | 1593.5 | 275.7 | 1455.8 | 5,780 | 2,486 |
| 1,000 | `datashader-aggregate` | 305.5 | 5475.2 | 2314.0 | 342.5 | 1430.5 | 2,718,975 | 5,897,289 |
| 100,000 | `xy-density` | 18.8 | 1534.2 | 2202.9 | 64.8 | 1347.8 | 264,568 | 1,029 |
| 100,000 | `plotly-aggregate` | 1204.1 | 2412.7 | 1562.6 | 276.8 | 1470.2 | 90,334 | 2,498 |
| 100,000 | `datashader-aggregate` | 421.1 | 4308.3 | 2319.4 | 344.4 | 1510.6 | 2,718,997 | 5,897,282 |
| 1,000,000 | `xy-density` | 28.2 | 1791.8 | 2019.9 | 88.4 | 1423.9 | 266,464 | 1,018 |
| 1,000,000 | `plotly-aggregate` | 948.9 | 2204.9 | 1581.0 | 296.6 | 1471.3 | 158,788 | 2,502 |
| 1,000,000 | `datashader-aggregate` | 294.5 | 3628.8 | 2297.6 | 360.7 | 1435.0 | 2,719,007 | 5,897,287 |

The two socket directions, text/binary split and cumulative checkpoints are
retained in `bounded.json`, not reconstructed from this table. XYG and Plotly
aggregate have matching **CDP, page and host** body totals at all three
checkpoints in this run. Bokeh totals are CDP-only observations, including its
binary image protocol. Bytes exclude HTTP/bootstrap assets, WebSocket framing,
compression and network-stack overhead. Raw Plotly's zero WebSocket total is
not zero delivery: its separate `html_bytes` contains the source and JS.

Plotly aggregate served an initial and a final view per cell in this trajectory:
its 75 ms trailing debounce coalesces the gesture, rather than pretending that
42 wheels required 42 server aggregates. Every served frame has matching
NumPy inclusive-window count / Datashader grid mass. The final source-window
counts were 1 / 1 / 2 at 1k / 100k / 1M. PNG hashes and applied revision/domain
are retained. Bokeh aggregate bounds match the current axes before the probe
accepts settled pixels; its probe does not independently validate grid counts.
XYG checkpoints record density origin and exact drill state, without claiming
independent hover or conservation proof from this run.

## Environment and resource scope

CPython 3.12.15, Linux x86_64, 8 logical CPUs / 4 physical CPUs, 32 GiB reported
system RAM; the exact affinity and total bytes are in `runtime`. Shared local
machine, no hardware isolation, no repetitions, no confidence intervals.
Chrome for Testing 156.0.8078.4, SwiftShader, DPR=1, chart 900×420 in a 1100×600
window. Browser trees include bundled extension renderer processes observed
on this installation; there is no idle baseline subtraction or GPU-memory
claim. Build/native preparation and browser navigation are separate phases.
Fresh processes/profiles are used; OS/JIT disk caches are not flushed.
Numba/OpenMP/OpenBLAS thread settings are each 2. Numba 0.66.0 / llvmlite 0.48.0;
Plotly 6.9.0; Datashader 0.19.1; HoloViews 1.23.1; hvPlot 0.12.2; Bokeh 3.9.1;
Panel 1.9.3; Tornado 6.5.7; pandas 3.0.3; NumPy 2.4.6. Complete exact dependency
versions are retained in `runtime-requirements.txt` and the benchmark lock.

Per host or browser tree: 2 GiB RSS cap, polled every 50 ms. The cap may
overshoot between observations; it is not a hard allocation fence. Host
preparation and browser have separate 70 s timeouts; CDP calls have their own
bounded timeout. An outer `timeout 900` bounds the sweep. The run completed
in roughly 3 minutes; no limit was raised to rescue a cell. All transient data
and Chrome profiles use this isolated worktree's `.ux-tmp` via `TMPDIR` because
shared `/tmp` has an exhausted per-user quota. No other worktree was cleaned.

## Exact preparation and execution

From the repository root (Rust is installed under `~/.cargo/bin` here):

```bash
export PATH="$HOME/.cargo/bin:$PATH"
mkdir -p .ux-tmp
export TMPDIR="$PWD/.ux-tmp"
cargo build --release
npm ci && node js/build.mjs
uv sync --group dev
uv venv .venv-ux
uv pip install --python .venv-ux/bin/python -r benchmarks/requirements-ci.lock \
  websocket-client==1.9.0 pytest==9.0.2
```

Actual recorded command (for a reproduction, change `--out` to
`.ux-tmp/reproduction.json` so this immutable archive is not overwritten):

```bash
TMPDIR="$PWD/.ux-tmp" PYTHONPATH="$PWD/python" PATH="$HOME/.cargo/bin:$PATH" \
NUMBA_NUM_THREADS=2 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
timeout 900 .venv-ux/bin/python benchmarks/bench_ux.py \
  --sizes 1000,100000,1000000 \
  --arms xy-exact,plotly,xy-density,plotly-aggregate,datashader-aggregate,datashader \
  --chrome /home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome \
  --software --timeout 70 --memory-gib 2 --no-grid \
  --out benchmarks/results/live-aggregation-2026-10-24/bounded.json \
  > benchmarks/results/live-aggregation-2026-10-24/console.jsonl \
  2> benchmarks/results/live-aggregation-2026-10-24/stderr.log
```

The documented `/usr/bin/google-chrome-stable` does not exist on this machine;
the explicit installed Chrome binary above is used by the repository's CDP
harness. Uniform load screencasts remain on. `--no-grid` avoids producing a
combined promotional video; all raw JPEG frames and both verification PNGs
for successful cells are retained. Successful overview and settled screenshots
were also visually inspected for the three density arms at 100k.

Focused verification:

```bash
TMPDIR="$PWD/.ux-tmp" PYTHONPATH="$PWD/python" .venv-ux/bin/python -m pytest \
  tests/test_ux_comparison_evidence.py tests/test_ux_live_host_transport.py -q
# 40 passed, including the recorded evidence/transport/hash consistency test.
TMPDIR="$PWD/.ux-tmp" uv run --with tornado==6.5.7 --with websocket-client==1.9.0 \
  pytest tests/test_ux_comparison_evidence.py tests/test_ux_live_host_transport.py -q
# 39 passed, 1 skipped (Datashader intentionally optional in the product/dev env).
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

The unit fixtures check deterministic real-row hashes, UTF-8/binary directional
body accounting, phase deltas, and actual Datashader mass/PNG orientation.
The archive test checks actual observed cells and body counters. These tests
are not a stubbed replacement for the recorded browser sweep.

## Files and integrity

- `bounded.json`: complete raw report, phases, failures, component versions,
  source/binary/harness identities, final domains, byte counters, mass oracles.
- `console.jsonl`: one progress line per cell and the terminal output path.
- `stderr.log`: sweep stderr (empty on this completed run).
- `bounded-shots/`: exact overview/settle checkpoint screenshots for successful cells.
- `bounded-video/`: original per-arm load screencast frames; input/settle clocks
  exclude recording because recording stops at the load checkpoint.
- `runtime-requirements.txt`: optional environment freeze.
- `SHA256SUMS`: every retained file except the checksum file itself. Verify
  from this directory with `sha256sum -c SHA256SUMS`.

Source bytes SHA256 (little-endian f32 x then y):

- N=1000: `c63deced8d649438a75118fae2ea9f32f9049ae942117e4fc92268114a50a6cf`
- N=100000: `fae52f30bbd314c945ff701917d2a2675927d4f42d179f69e584fb0ef6d3ed30`
- N=1000000: `36b5431d6fee501bdf558ce4f4cdd1bb0f7755ab1e589c1806a7c3a68903d72f`

Measured artifacts SHA256:

- `python/xyg/static/index.js`: `b7bf5702e7d28647b651777c364a8ec6c82403e145d16475ef8e06484b8ddfce`
- `target/release/libxyg_core.so`: `cc59e76471dea30c864aed3e183355dd5ba675f6ab47892dbae21add8da8cb6d`
- `benchmarks/bench_ux.py`: `aeff2922914a5bfee74fe7229c4fb0bac718cae841e5f3d2f6ef014ecf0deaed`
- `bounded.json`: `9917683d0175dd026fd3e9683bcadac498b9e34d1a761388e212303370e6a083`

## Remaining #11 gaps

The maximum actually measured source here is **1M**, not a claimed product
ceiling or proof of 100M/1B behavior. No mapped three-f64 source, colored spill,
larger-than-RAM source, tile residency/reuse, disk failure, repeated adjacent
pan/zoom, equal-window competitor trajectory, hover, app dashboard or export
comparison is established. The existing host/kernel slice is separate evidence;
it does not supply this missing competitive/browser tie.

A true billion-row **three-f64** source is 24,000,000,000 bytes (22.35 GiB)
before derived state or the browser, exceeding a 12 GiB lane. Do not allocate
it there, increase paid capacity, fake the source, extrapolate this table or
close #11 from this result. Hosted actual-scale work belongs to the parent
follow-up after landing. This task did not push, open a PR, publish, merge or
close an issue.
