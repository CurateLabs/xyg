# Distinct colored-spill evidence (#11)

This is a **host/kernel slice**, not complete #11 or Phase-4 acceptance.
It implements the colored memmap spill workload separately from #876's
`resident-count` workload. The latter keeps its existing defaults, report kind,
count-only source and resident-pyramid rejection. Existing reports are never
promoted or relabeled as colored-spill evidence.

The implementation is `benchmarks/bench_density_e2e.py --workload colored-spill`,
with helpers in `benchmarks/_density_spill.py` and an independent policy verifier
in `scripts/verify_density_spill_report.py`. It uses the existing process-group
supervisor, including process-tree RSS, worker VmHWM, temporary-tree disk samples,
timeout, cancellation, group termination and orphan checks. No workflow, job or
required status is added. The existing density workflow runs distinct colored
control and authority commands alongside the resident commands. Its CI validator
pins their exact command bodies, main/event/capability guards and exact-SHA
artifact upload.
The CLI mode itself already enforces the authority boundary independently.
No performance workflow runs on a pull request.

## Source, ownership and policy

Dossier §§5/27/28/32b remain the product contract. Sources are deterministic,
chunk-generated f64 x/y memmaps plus a third f64 color memmap. Band-dependent endpoint
values use a fixed red/blue colormap; public continuous color admission borrows
that mapping and Rust receives an explicitly measured one-byte-per-row color
index and a 1024-byte RGBA LUT. There is no N-by-four f64 RGBA source expansion.
Generation chunks cannot exceed 1M rows. All three mappings total 24N disk bytes.
The three hashes are accumulated during generation without loading whole files.

The chart is built through public composition:
`scatter_chart(scatter(x, y, color=color, color_domain=(0, 1), colormap=...,
opacity=1, density=True, pyramid_spill=True)).figure()`.
Admission, post-build and post-journey inventories assert f64 dtype, actual
memmap ancestry, shared memory and identical starting pointers for x/y/color.
The native color-build observation independently asserts borrowed x/y pointers,
index/LUT sizes and hashes, and the absence of an expanded RGBA input. The live
trace must retain no resolved row color cache. Native resident/spilled byte
counters and the host memory report are retained. Host `channel_bytes` currently
conservatively charges the mapped color input as resident; this harness does not
rewrite that product accounting. These observations prove canonical borrowing
and retained-cache bounds, **not a complete audit of every transient allocation
inside the native build or first-payload path**. Aggregate build scratch remains
covered by measured resource ceilings.

Local controls accept 1..1M rows and are structural/advisory. Because production
eligibility starts at 2M, the control temporarily lowers only the Python lazy
pyramid eligibility threshold to 1 and explicitly prewarms the store. The native
first-payload planner remains unchanged and emits its truthful `exact` / `bin2d`
mean-color payload. The resulting store drives all measured interactive requests.
The override, prewarm and first-payload distinction are required report fields.
The normal adaptive mapped-source base is 2048 for controls.

Authority accepts **exactly 100M**, with the production threshold and adaptive
4096 base, and requires a real scheduled/manual `refs/heads/main` Actions
context plus `XYG_DENSITY_100M_AUTHORITY=1`. The guard runs before any allocation
in both supervisor and internal worker entry points. The authority environment
must identify Actions, event, ref, run ID, attempt and exact SHA; the source tree
must be clean and match that SHA. The verifier requires an externally supplied
`--sha` and matching **ambient** Actions context/capability. A report cannot
authorize itself by filling in GitHub fields. These checks establish the trusted
workflow execution boundary; they are not cryptographic runner attestation and
a downloaded authority report cannot be promoted from a local shell.

RSS **12 GiB**, temporary disk **4 GiB**, and wall time **3600 seconds** are
independent hard maxima. Lower execution limits are allowed; raising them is
rejected before source allocation and again by the verifier. The same supervisor
owns the canonical files and spill directory. Workflow integration retains
the existing 90-minute aggregate timeout over sequential workloads (a
stricter shared limit than two independent hour-long runs).
A timed-out or canceled run is failed evidence, even if a partial worker report
was already written. Success requires explicit native store release, no spill
files, closed mappings, restored tile budget, removed temporary tree, zero worker
exit status and no remaining process-group members.

## Measurement and oracles

A 512-square viewport and 16 MiB process-wide native tile budget are fixed and
recorded. After an untimed seed frame, the workload records 24 deterministic
half-domain overlapping/reversing pans and eight alternating quarter/half-domain
zooms. Each zoom must **actually** change the observed served level by exactly
one; pans must retain their level. A resource-coarsened jump or unfinished adjacent
refine cannot substitute for that journey. Every response comes through the host's
`density_view(..., tile_cache=XYDC)` tile painter. The inventory sent back is only
what the preceding Rust frame retained, with its observed generation, opacity,
keys and previous level.

The raw report retains each served level, flags/target, binning/reduction,
window, generation, source/window normalization, native stats, tile geometry,
RGBA hashes, body bytes, reply hash/bytes and GPU budget/inventory. Omitted bodies
must already exist with the same hash in the observed client inventory. All active
frames must be colored and fit Rust's unchanged eight-screen texture budget.
This is simulated texture ownership, not measured GPU allocation.

The timer wraps only `kernels.tile_store_paint`, including its ABI wrapper and
native fetch/compose/encode. It excludes host dispatch, Python instrumentation,
parsing/hash/oracle work and browser work. No timed request contains an oracle.
Raw pan and zoom samples are mandatory; p95 uses linear interpolation over the
pan samples. The verifier independently pins **pan p95 <16 ms** and **every zoom
<50 ms**, hard only on authority. Control timings remain advisory, even when
slower; report-supplied limits cannot loosen authority budgets. A passing host
latency gate is not an end-to-end browser latency claim or CodSpeed result.

After the timed sequence, a separate fetch-all replay must reproduce every
active tile key, byte hash, gutter/interior geometry, served level, generation,
opacity and normalization at each window. Cached transfers must be strictly
fewer. A separate chunked NumPy 64-square histogram conserves all source counts
exactly; an independent linear-light red/blue mean oracle checks the full-domain
native overview (RGB tolerance two bytes for intermediate u16 rounding, exact
occupied alpha and empty transparency). This is independent of the cached paint
byte comparison. Counts/mean hashes and errors are retained; assertions precede
every success field. Optimized Python (`-O`) is refused so those assertions
cannot be disabled.

Reports include the full Python/Rust/TypeScript source hash manifest, harness and
lockfile hashes, exact loaded native binary hash/ABI, generated client hash,
source hashes and environment hash. `--artifact-root` verifies the retained
source/harness/native/client hashes against an available checkout. Offline
validation checks manifest consistency and digest syntax; it cannot recover
missing artifacts or authenticate arbitrary well-formed hashes.

## Reproduction and validation

```bash
cargo build --release --offline
npm ci && node js/build.mjs
uv sync --group dev
uv run python benchmarks/bench_density_e2e.py --workload colored-spill \
  --points 1000000 --chunk-points 262144 --timeout 600 \
  --max-rss-gib 8 --max-disk-gib 2 --output /tmp/density-colored-spill.json
uv run python scripts/verify_density_spill_report.py \
  /tmp/density-colored-spill.json --artifact-root "$PWD"
uv run pytest tests/test_density_spill_report.py tests/test_density_spill_harness.py \
  tests/test_density_e2e_report.py -q
```

The focused tests use a 16,384-row real native control and mutate budgets,
missing pan/zoom samples, color/spill absence, hashes, inventories, mapping
ownership, count/mean errors, authority context and cleanup. Separate boundary
tests check strict authority latency limits without allocating authority rows.
Timeout/cancellation tests exercise the existing process-group supervisor.
No local execution allocates more than 1M points. The existing
`density-100m.yml` lane runs a 1M colored-spill control daily and the distinct
100M mode only on its existing weekly/manual main trigger. Its exact-command
workflow guard pins the capability, 12 GiB/4 GiB/3600s maxima, source SHA and
artifact identity verification. PR CI runs only the 16,384-row control. Do not
spoof authority locally or dispatch it merely to validate harness changes.

## Explicit remaining acceptance

The report deliberately requires `scope: host-kernel-only` and
`browser.status: not-run`. A complete colored-spill real-browser journey at the same
source/windows, nonblank pixels, seam tests, actual adjacent crossfades,
GPU allocation and cached/fetch-all **pixel** equality remains open. The existing
`scripts/density_tile_smoke.py` provides bounded count/mean browser coverage and
its separate fixture is not evidence that this 100M source reached the browser.
The [same-source browser companion](density-spill-browser-evidence.md) borrows
this worker's actual figure, store, mappings and windows after host timing.
Its separate independently validated artifact links the finalized host bytes;
it never changes this report's scope or browser flag. A retained supervised 1M
integration control passes, but actual 100M browser execution remains pending.
Do not attach a separate fixture as a success flag for this workload.

This slice also does not establish larger-than-RAM behavior, absence of all
transient row allocations, the final candidate host matrix, Node parity, or the
competitive Datashader/HoloViews/hvPlot/Plotly/Bokeh scale evidence required by
`tier3-testing.md` and #113/#54. Whole #11 stays open.

### Retained hosted host/kernel result (2026-10-24)

The actual main-only [run 40055564684](https://github.com/CurateLabs/xyg/actions/runs/40055564684)
passed both 1M controls and both distinct 100M authority/verifier pairs on clean
source `71e48b67827709ed251ae05b90d010a8cef824eb`. The
[raw reports, environment, job log, hashes and reproduction commands](../../benchmarks/results/colored-spill-2026-10-24/hosted-main/README.md)
retain the colored result: pan p95 0.37907085 ms; slowest zoom 8.125563 ms;
maximum sampled tile residency 16,517,088 bytes under 16 MiB; canonical three-column
f64 mappings 2.4 GB; spilled tiles 274,468,864 bytes. The independent count/mean
overview oracle passed with zero observed count/RGB error and all cleanup checks
passed. This is historical **host/kernel** evidence only. The same report
explicitly records browser `not-run`; all browser, competitive, larger-than-RAM
and final candidate limitations above remain in force.
