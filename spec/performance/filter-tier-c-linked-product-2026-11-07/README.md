# #112 bounded linked-density checkpoint

This candidate adds an actual ordinary linked dashboard to the reviewed
programmatic checkpoint. **Whole #112 and milestones 4–7 remain open.**
It makes no performance or competitor-win claim.

The preserved reviewed checkpoint is `b91b8099ff1281f3740c8f8d4fde461509c332d0`
(canonical complete diff against `2cb7f0a13ec0af3a00b9dcfd2b104a2c579b7ac9`:
`4d00414b6edab26a268834fc3553b1ece824746da129f3610225c544b1a489cb`,
independent approval reported by the parent). Required accepted M5 main
`58960c7c6c814ed049209052cf66d77b5bb7ecfd` was integrated normally by
`514a2ac72a5b90ef53c8b8acc87e1afc345c9b5c`, whose parents are b91 and 589.
The fresh main fetch observed `43c35f67b95ae4e78e3e96f200a0e6be8642199c`;
this candidate keeps the requested M5 integration base. No unapproved GPU
producer, frozen graph producer, or temporal composition catalog was modified.
Base-mask digests are computed once at admission; indexed replies do not
rehash canonical-sized masks. A poisoned-backing regression checks this.
The new material diff requires the parent's independent review before delivery.

## Functional evidence

Rust owns one canonical f64 source, persistent base ranges/mask and per-view
range clauses, the active-dimension cumulative slab, exact passive 2D count
planes, checked admission, edit snapshots, cancellation and atomic publication.
Storage scales with active cells × passive bins, never active cells × row-mask
words. Source ID/epoch/revision and absolute u64 row identity survive append,
eviction, predicate changes and rebuild. All new numeric requests/replies are
binary. Exported signatures remain native ABI 402 / WASM ABI 36; generators
were run, and all predecessor packets/receipts remain immutable.

The same protocol is callable through Python `Chart.filter_session`, Node
chart `filterSession`, and the public browser factory. The 57-case linked
fixture is checked against a separate scalar count/membership/hash/paint oracle
and replayed as complete native/WASM/Python/Node packets. Worker replay covers
56 cases; the deliberate output-capacity refusal is checked at native and raw
WASM seams. New Node coverage includes 300 mutated linked requests and
independent empty/nonfinite/arbitrary-boundary count oracles.

The existing Release surfaces browser command paints **five public composed
ordinary charts with different dimensions**, using 13 canonical rows (14 after
append), 4×4 grids and real Chromium/WebGL2. Pointer capture and keyboard-only
Tab/B/Home/End/arrows/Enter/Escape/Delete use the same Rust transactions.
Pointer and keyboard final ranges have identical predicate hashes and pixels;
the resolvable range serves tier 3 with zero canonical rows read and 162 slab
scalar reads. Arbitrary-cut preview reports an exact scan. Independent oracles
check canonical membership and every total/selected bin; 400 uploaded density
texels and 19 canvas pixels at actual data coordinates are checked exactly (zero
tolerance). The journey exercises composed predicates, a base
filter, eviction/rebuild, append, newer-request suppression, context restoration,
legend visibility, unsupported tools, rejection of legacy coordinate selection,
source invalidation, and injected five-view GPU publication failure. Aggregate
selection is painted through the existing density texture path; no point-mask
substitute or second renderer/allocator is introduced.

The existing foundation command also calls the public 2D Worker session and
checks indexed counts, u64 identity, edit restoration and base-mask diagnostics.
Twelve bounded build/query/paint/masked-query rows in the existing CodSpeed selection suite cover
1k, 10k and 100k sources with fixed eight-by-eight grids. Only their assertions
were run; the CodSpeed CLI is unavailable here and no hosted job was requested.

## Inspection and reproduction

`environment.json`, `artifacts.json`, `rust-sources.json`, `results.json`, the
compressed raw logs, raw public-composition payload capture and PNGs bind the
source, exact native/WASM/client artifacts, commands and observed results.
`current-bindings.json` advances the global Core source binding append-only;
the original b91, merge, ABI401 and earlier Core receipts are historical inputs.
The ordinary real Git autocrlf/CRLF test covers these LF-pinned bindings.
`collect.py` reproduces the artifact/source/environment inventory from the
repository root. The captured browser request stream has 125 requests framed
as repeated u32 byte length plus raw XYFC; the public-composition capture has
10 entries framed as u32 name length, u32 data length, UTF-8 name and raw data.
Generated native/WASM/client binaries remain build artifacts and are not checked
in. `changed-paths.txt` lists the complete changed paths against the review base;
`feature-paths.txt` lists this slice against the M5 integration merge.

Use Node 22.23.4 and Rust 1.96, `CARGO_BUILD_JOBS=2`, a short writable TMPDIR
(`/var/tmp/xyg-f112` here), the explicit candidate native library, and the Chrome
path in `environment.json`. The primary commands are:

```sh
cargo test -p xyg-engine filter_tier_c --lib
cargo test -p xyg-wasm --lib
cargo build --release
node js/build.mjs
npm run build:wasm
uv run pytest -q tests/test_filter_tier_c.py tests/test_filter_tier_c_density.py tests/test_channel.py tests/test_selection_rows.py tests/test_canonical_drill_interaction.py tests/test_capability_registry.py tests/test_public_api.py
uv run pytest -q tests/test_*_abi.py tests/test_abi_parity.py
uv run --group codspeed pytest -q benchmarks/test_codspeed_selection.py -k filter_tier_c
npm test --prefix packages/xy-node
node scripts/filter_tier_c_conformance.mjs --chromium "$XYG_CHROMIUM" --capture linked.png
node scripts/wasm_foundation_smoke.mjs
python3 scripts/gen_abi_manifest.py --check
python3 scripts/gen_wasm_abi.py --check
python3 scripts/abi_smoke.py
uv run python scripts/check_release_inventory.py
uv run python scripts/verify_ownership.py
uv run python scripts/verify_ci_workflow.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

No workflow/gate aggregate, caps, tolerance, selection/LOD deadline or existing
check was weakened. The new Node file is in the explicit package test list.

Fresh results include seven engine tests, 76 WASM tests, 484 Python/ABI tests
(two expected xfails), 1,074 Node tests (two existing skips), 12 benchmark
assertion rows, and 109 provenance/ownership tests. The broader contract
preflight passed 758 tests and failed the human ownership ledger because the
new rows were outside its required section. Moving them into that section
resolved the failure; all nine ownership tests pass on the focused recheck.
The preflight failure is retained, not relabeled as a green aggregate.

## Preserved failures and limits

The unmodified full Node command on this eight-CPU host twice failed the native
force-worker timeout case (the first run also failed a graph-worker packing
assertion). Its trace sends cancellation before native handle creation and
reaches emergency termination without the required destroy receipt. The force scheduler and both affected test files are unchanged from b91. The isolated 31 worker tests pass.
A full two-CPU-affinity diagnostic (`taskset -c 0,1 npm test --prefix
packages/xy-node`) passes all 1,074 non-skipped tests with the same deadlines;
the two existing skips remain. The final default-concurrency replay also
passed 1,074 tests with the two existing skips. The earlier failures remain
a concurrency-sensitive finding for parent review, not proof of a baseline
execution or a repaired worker race. The raw failed
runs, successful controlled run and reproduction commands are retained.

Earlier development failures are also retained: a test targeted the chrome
canvas instead of the focusable plot canvas, and manual preview exposed stale
bootstrap “sampled” badges. The final test uses keyboard Tab navigation, and
bound views display authoritative canonical selected totals and serving status.
A separate frozen-module probe exposed a vertical density-image inversion:
at data coordinate (0.5, 0.5), a fully selected bin painted a dimmed wrong-row
color. Rust now lowers all count/paint planes to the existing sampler's
bottom-row-first layout. The retained before log binds the actually served
frozen WASM hash; the after log and PNG confirm exact selected RGBA. Final
canvas-coordinate probes prevent a matching texture/oracle orientation bug.
These development logs are not final-source qualification receipts.

The current browser binding supports ordinary one-scatter, constant-color,
primary linear-axis views. Full nonlinear/nonprimary/large-offset and per-point
channel compatibility, active rectangles and non-range predicates, automatic
native widget/application transport binding, persistent materialized result
masks, idle prefetch, cooperative mid-call Worker cancellation, and canonical
paged/spilled-source reopening remain open. Canonical residency still obeys the
unchanged 256 MiB owner limit; this slice does not admit a resident 100M×five-f64
source. That requires the retained/paged source integration and qualification,
not a budget increase or relabeling a scan as Tier C.

The committed 100M source fixture/provenance, five rendered views sustaining
≥50 FPS, actual CodSpeed timings, traces, RSS/peak/payload qualification, real
assistive hardware and cross-host/platform coverage, and reproducible
comparisons with Falcon/Mosaic, Matplotlib, Seaborn, Plotly, Bokeh, Altair,
Datashader and HoloViews/hvPlot across all required scales remain mandatory.
None is claimed from this bounded functional proof.
