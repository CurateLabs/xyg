# Native build tools and Blacksmith CI

Cargo (`Cargo.toml` / `Cargo.lock`) owns the Rust build. Python tests use
pytest in the uv environment; Node bindings use npm and the same release
`libxyg_core`. The render client builds through `node js/build.mjs`; the
packaging contract remains dossier §33. Bazel is no longer a supported build
entry point or CI dependency.

## Decision and evidence

GraphForge removed Bazel on 2026-09-30:
[ADR 0048](https://github.com/CurateLabs/graphforge/blob/be257e565/docs/adr/0048-cargo-is-the-ci-build-authority.md),
[removal PR #1661](https://github.com/CurateLabs/graphforge/pull/1661).
Its primary reason was duplicate build ownership: 46 build files plus locks,
drift/parity tooling, and another release version; 22% of Rust-touching
commits also edited Bazel descriptions. Corrected measurements compared only
three successful Rust-changing pairs (Cargo nextest median 1028 s, Bazel
1075 s). They did **not** establish a general speedup. Bazel did save roughly
16 minutes on about half of Rust merge groups by replaying tested trees.

XYG's retired layer was even narrower: it wrapped Cargo/pytest/npm in the
real checkout with local, no-sandbox, no-remote actions; the cdylib build also
disabled remote caching. It supplied no hermetic Rust dependency graph or
remotely cached Rust compile benefit. Main CI and packaging already used
native tools. Removing it eliminates the launcher binary, pinned Bazel
version, module/lock, duplicate workflow, runfiles discovery, copied library,
and wrapper-only validators. This is a build-maintenance decision; no XYG
runtime or CI latency speedup is claimed. XYG keeps `cargo test --workspace`;
GraphForge's nextest adoption does not establish a need for it here.

## Coverage contract (regime A)

Given a checkout with the release native core, generated client/WASM assets,
and locked Python/Node dependencies, when the native graph gate runs, every
check from the retired graph suite must execute and propagate failure. The
main CI `test` job runs this coverage on pull requests, merge groups, main
pushes, and manual dispatches. Its `Release surfaces` aggregate and merge-queue
concurrency policy are unchanged.

| Retired target | Native replacement in `.github/workflows/ci.yml` |
| --- | --- |
| `xyg_core` | Existing `cargo build --release` |
| `rust_test` | Existing `cargo test --workspace` |
| `abi_smoke` | Existing stdlib-only `python3 scripts/abi_smoke.py` |
| `python_graph_test` | Existing full pytest suite, including graph and sankey |
| `node_graph_test` | `Node host suite`: `npm test --prefix packages/xy-node` |
| `perf_parity_test` | Graph benchmark at 1000 nodes and kernel benchmark at 100000 points with `--no-baseline` |
| `scale_all_charts_test` | Python and Node chart-scale `--profile smoke`, plus both tier-3 pyramid smokes |
| `graph_mvp_tests` | All of the above under the main `test` job |

Both new CI steps explicitly select the just-built release library with
`XYG_NATIVE_LIB`. Node graph goldens read the generated ABI constant by default;
`XYG_EXPECTED_ABI` remains an optional test override. There is no shell ABI
parser or fallback discovery path. Workflow contract tests reject omitted,
commented, echoed, or failure-suppressed graph-suite commands.

The hard `test` job also runs every benchmark body once without timing (divan `--test` for the Rust
benches and `pytest benchmarks/test_codspeed_*.py` without `--codspeed`), so stale benchmark oracles
fail pull requests instead of the nightly CodSpeed run; see
[methodology.md](../benchmarks/methodology.md#8-codspeed-simulation-modules). The PyEmscripten wheel
build also sets `XYG_REQUIRE_WASM=1` inside `CIBW_ENVIRONMENT_PYODIDE` so the build hook fails early.
The single-producer guard parses the cargo/npm/node arguments, so reordered or abbreviated flags
cannot hide a second producer, and the `test` and `python_floor` jobs no longer install the unused
`wasm32-unknown-unknown` target.

The `matplotlib_reference` job also runs
`tests/test_named_colorbar_comparison.py` explicitly alongside its full pyplot
suite. Its dev dependencies provide Pillow and its pinned Matplotlib 3.11.0
install exercises both shared-renderer corruption witnesses. The minimal
Python-floor environment skips that module through `pytest.importorskip` when
Pillow or Matplotlib is absent.

`scripts/verify_ci_workflow.py` is a conservative static guard, not a shell parser: it
fails closed where it cannot analyze a step (folded or quoted `run` scalars with a pipe, a
heredoc left open) and accepts a few false positives rather than miss a gate.

The `Release surfaces` aggregate lists every hard job, including `wasm_assets`; see the
hard/advisory table in [production-readiness.md](../process/production-readiness.md).

Scale evidence retains its existing limits: smoke timings are advisory;
render-graph and pyramid budgets are enforced. 100M/1B LOD decision evidence
is not proof of allocating or rendering that many rows. The benchmark
implementations and thresholds are unchanged.

## Packaged WASM assets (#1005, dossier §33)

The earlier package-qualified filtering/temporal-catalog source used native ABI403 and WASM37.
Its wasm32-only Cargo configuration used `opt-level=2` with LLVM inlining
threshold 50; native release optimization remains O3. The single module keeps
the complete parent export union, optimizer passes and unchanged 1927168 raw /
786432 Node22 gzip6 byte limits. O3/50 exceeded both limits for this combined
source; O3/40 also failed gzip. Their bytes and failures remain in
[the integration evidence](../performance/filter-catalog-abi-union-2026-11-07/README.md).
Same-source ABBA diagnostics retain complete admitted-output equality and
slower cases. This compiler choice establishes package admission and the
recorded bounded functional paths, not a latency or competitor win. Historical
O3 receipts describe their historical sources and are not rewritten.

The initial combined frozen-export source declares native ABI405 (551 symbols)
and WASM38 (68 function exports). That source checkpoint was not a package pass.
Sharing only the four geographic source/snapshot header-writer bodies on wasm32
reduces the complete module to 1,936,761 raw /805,269 Node22 gzip6 bytes, still
9,593 /18,837 bytes above the unchanged limits. Native compilation, compiler
settings and shipping optimizer passes are unchanged; diagnostic extra passes
are not adopted. Matching native-host paint qualification does not certify this
unqualified WASM module. See the [follow-up evidence](../performance/indexed-temporal-hosts-header-sharing-2026-11-07/README.md).

The combined producer now keeps wasm32 at O2, uses LLVM inlining threshold 0,
and retains function names only until pinned Binaryen132 runs `-O3
--all-features --reorder-functions-by-name --strip-debug`. Native O3 and its
stripping remain unchanged. Names are absent from the final module; all 68
function exports, ABI38 and the single-module caps are preserved. The fitting
candidate measures 1,897,244 raw /784,226 Node22 gzip6 bytes. The
[combined layout evidence](../performance/combined-wasm-layout-2026-11-07/README.md)
records normal production, complete-output comparisons, slower runtime samples,
and qualification boundaries. This is a size/runtime tradeoff, not a latency or
competitor win. Historical profiles and failed artifacts remain immutable.

The full source foundation also validates the six-family temporal catalog
through the packaged Worker and existing ChartView painter. It compares
requests and complete Scenes with the native hashes in
`tests/fixtures/temporal/catalog-six-families.json`, checks actual source-color
pixels and exact u64 identity metadata, and disposes each view. The ordinary
Node catalog tests independently bind that fixture to the native compiler.
This bounded proof adds no job or timing gate and does not qualify temporal
controller interaction, accessibility, dense LOD or massive-scale behavior.

Main run 38640943006 failed `Benchmark methodology suites` with
`FileNotFoundError: packaged WASM tick assets missing: xyg-wasm.wasm`: the job built the
client but nothing in its dependency graph produced the generated WASM assets, and the
downstream `Merge and verify benchmark reports` job then failed on the absent
`workflows.json`. The assets are generated (never committed), so every consumer must obtain
them from the one producer.

| Step | Contract |
| --- | --- |
| Producer | CI job `wasm_assets` runs the fail-closed raw build and PNG-dependency check, `node js/build.mjs`, the packaging contract tests, `npm run build:wasm`, and `scripts/verify_wasm_assets.py`, then uploads `wasm-assets` (`if-no-files-found: error`). Locally: `node js/build.mjs && npm run build:wasm`. |
| Consumers | `test`, `wasm_foundation`, `python_floor`, `matplotlib_reference`, `benchmark_methodology`, `wheels`, `sdist` list `wasm_assets` in `needs`, run `node js/build.mjs` (`wasm-worker.js` is built, not part of the artifact), download `wasm-assets`, and verify before use. No consumer runs `npm run build:wasm`, `js/package-wasm.mjs`, or the wasm32 `cargo build` itself. `publish.yaml` has the same shape: producer `wasm-assets`; consumers `wheels`, `wasm` (PyEmscripten), `sdist`, `browser-package`; `XYG_REQUIRE_WASM=1` plus `--require-wasm` on the wheels and sdist, `--require-wasm` on the Pyodide wheel. |
| Verifier | `scripts/verify_wasm_assets.py` (stdlib only; "stale" means manifest-, ABI- or client-build-inconsistent, not proof of freshness against the Rust source) checks presence in both locations, WebAssembly magic, `sha256`/`bytes` against `xyg-wasm.manifest.json`, ABI/Scene/painter versions against `spec/wasm/abi.json`, inline module hash, inline classic-worker freshness, and dist/static equality. One diagnostic names the files and the producer command. |
| Artifacts | `XYG_REQUIRE_WASM=1` makes `hatch_build.py` fail without verified assets; the wheel and sdist jobs run `verify_wheel.py` / `verify_sdist.py --require-wasm`. |
| Aggregate | A failed or skipped `wasm_assets` skips its consumers; `Release surfaces` lists it and every applicable consumer, so the aggregate fails (see [production-readiness.md](../process/production-readiness.md)). |

Scheduled workflows `ceiling-benchmark.yml`, `density-100m.yml`, and `docs.yml` do not
exercise the WASM tick path (only `bench_interaction.py`, `bench_dashboard.py`, and the
workflow benchmarks use `wasm_ticks`), so they are not consumers. `codspeed.yml` carries its own
copy of the same three commands because a scheduled workflow cannot download this run's artifact.

Evidence: `tests/test_verify_wasm_assets.py` (clean checkout, each withheld asset,
stale hash/ABI/inline/worker, diverged copies), `js/test/package-wasm-manifest.test.mjs`
(deterministic regeneration, early failure with producer hint, no half-published set),
`tests/test_hatch_build.py`, `tests/test_verify_wheel.py`, `tests/test_verify_sdist.py`,
and the workflow-contract tests in `tests/test_verify_ci_workflow.py` (every consumer needs
the producer, builds the client, downloads, verifies; no second producer; weakened producer
rejected; both `ci.yml` and `publish.yaml`). `tests/test_verify_wasm_assets.py` also replays every
consumer's steps up to its verifier on a clean checkout plus exactly the uploaded paths and
runs the real checker, so a consumer that verifies before its prerequisites exist fails the test.

## Local reproduction

```bash
uv sync --locked --group dev --group codspeed
cargo test --workspace
cargo build --release
npm ci
npm ci --prefix packages/xy-node
node js/build.mjs
npm run build:wasm
python3 scripts/verify_wasm_assets.py
make check-graph
make check-ci
make check-bench-oracles
node scripts/browser_client_smoke.mjs
```

`make check-bench-oracles` is the local form of the last two `test` job steps: the three
`cargo bench ... -- --test` commands plus `pytest benchmarks/test_codspeed_*.py -q` without
`--codspeed`. It needs the `codspeed` dependency group (hence `--group codspeed` above) for the
`benchmark` fixture. The CI steps run last in the job so a stale oracle fails visibly without
hiding the other `test` results.

`make check-graph` runs the ABI smoke, scoped Python graph/sankey tests, full
Node host suite, and all six benchmark commands above. It uses the project
Python (`PYTHON=.venv/bin/python` by default) and exports the platform-specific
release library path as `XYG_NATIVE_LIB` unless already set. Node loading remains
restricted to exact-platform packages or that explicit override. Missing inputs or a
failed check must fail the target, rather than silently skip a host.

The browser client retains its independent WebGL/browser smoke coverage.
The JS/WASM builds are prerequisites because the complete Node suite checks
native/WASM equivalence and HTML exports as well as graph kernels.

## Runners and revisit triggers

The main graph checks use `blacksmith-4vcpu-ubuntu-2404`, Rust 1.96.0 from
`rust-toolchain.toml`, Node 22, and the locked uv environment. Runner exceptions
and release gates remain in
[production-readiness.md](../process/production-readiness.md).

Reconsider a second build system only if an actual hermetic publication
requirement or a same-runner measured cache benefit justifies its maintenance
cost. Preserve a complete coverage map in any future migration, including
feature-gated and cross-host tests.

### Bounded public graph notebook journey

The existing `test` job now runs `Progressive graph notebook journey` after the
native/client builds and Python environment installation. It installs pinned
JupyterLab/IPykernel test tooling (no package runtime dependency), drives
`tests/notebook_graph_progressive.ipynb` through real anywidget binary comms with
Chromium, and validates the JSON report with
`scripts/verify_graph_notebook_report.py`. Two widgets, unfinished native
progress with trusted input, kernel callbacks, screenshots, Python row selection
and disposal are required. The workflow verifier rejects a removed, conditional
or replaced command; focused tests reject missing proof and terminal-only input.
The normal source-path classifier selects these files as release surfaces, and
`test` remains an input to the existing Release surfaces aggregate. No status,
merge queue rule, blanket size ladder or release compatibility policy is added.
Local reproduction is in the
[R2 receipt](../performance/graph-widget-progressive-r2-2026-11-06/README.md).


The full source-dist `node scripts/wasm_foundation_smoke.mjs` command includes the
bounded retained temporal presentation branch of
`graph_session_controller_wasm_smoke.mjs` (`XYG_GRAPH_TEMPORAL_ONLY=1` internally).
It uses actual shipped Worker/WASM, native mouse input and the shared history
fixture. This extends the existing gate, without adding a workflow/job or
changing package/runtime budgets. Staged-package and density-only foundation
runs keep their stated scope. Complete fixture retained native/WASM byte parity
runs in the existing `graph-session-wire.test.mjs` command.
The same retained branch verifies actual dashboard GPU eviction, refusal retaining
the accepted temporal camera/revision/pixels, and recovery of camera and Rust
membership after readmission. Its document-wide budget is applied after the
other temporal fixtures so those fixtures retain their original environment.

The full source-checkout `node scripts/wasm_foundation_smoke.mjs` command also
executes the bounded public browser graph scheduling regression via
`graph_session_controller_wasm_smoke.mjs` in `XYG_GRAPH_SCHEDULING_ONLY` mode.
It uses two real 1k attachments, explicit 384 MiB arenas, unheld replies, pixel
progress, trusted pointer/host-camera input, isolation and cleanup, plus default
1k and explicit-ceiling 10k refusal observations. Failures propagate through the
existing WASM foundation / Release surfaces gate; no separate CI job or timing
gate is added. Staged-package and focused density-only runs keep their existing
scope. `XYG_GRAPH_SCHEDULING_REPORT` optionally records this sub-run's raw report
and canvas captures. The focused command uses `XYG_GRAPH_SESSION_REPORT`.

The scheduling branch also runs a separate two-1k trusted keyboard case
(7201/7202, explicit 384 MiB each), preserving both preceding cases. The same
foundation Node unit invocation runs `graph-progressive-keyboard.test.mjs`:
captured-receipt controls reject no-op actions, wrong identity, untrusted input,
terminal-only evidence, missing progress, intervening resets and peer leakage.
The live case requires Tab navigation, unfinished focus/Replace and later native
progress, then completed Toggle/Replace/Clear/empty Escape, native emphasis and
actual host-colored focus pixels. No watchdog, default scheduling or load policy
is relaxed. See the [qualified receipt](../performance/graph-keyboard-1k-2026-11-07/README.md).

The same foundation scheduling entry now qualifies neutral retained1k graphs
with the unchanged16MiB Worker default, actual init-message assertions, trusted
pointer/camera and reviewed real-Tab keyboard identity/emphasis oracles. It also
runs1k held-continuation coalescing, stale/lifetime and disposal controls. The
explicit384MiB public10k path remains a separate bounded proof. Source populations
and exact native visible membership are distinct assertions in complete reply
replay; no offscreen GPU-count requirement is imposed.


Graph replay capture waits for each public attachment's `whenIdle()` after its
completed layout publication. Layout completion alone does not prove that every
recorded transport command has received a reply. Both the default scheduling
entry and public10k harness run a shared real-Worker negative control: one render
request is recorded but withheld before posting; the old collector rejects that
in-flight state, while capture readiness stays pending until the real reply.
No commands are filtered away, and missing/corrupt replies still fail. This
stronger boundary does not uniquely explain historical missing-reply failures;
those failed runs remain preserved without pass or reliability credit.
The full source-dist WASM foundation also executes
`temporal_graph_frozen_smoke.mjs`: actual Worker session/controller capture,
computed CSS focus, six glyphs and a focused compound frame, source scrub and
disposal, native/WASM Scene/XYPB/SVG/HTML byte oracles, exact artifact recovery,
independent retained head/phase/layer/position vectors and native/offline
ChartView pixels. This is part of the existing gate, with no conditional
fallback, deadline/cap increase or separate CI job. The ordinary discovered
pytest frozen suite and explicit Node test list also cover the boundary.
The historical pre-shared-PNG run asserted refusal and supplied no PNG acceptance.
The current shared-raster continuation requires actual module and strict-CSP
offline Worker PNG output, exact prior-native PNG parity, recovery and disposal.

The source foundation step explicitly names its already-built native core in
`XYG_NATIVE_LIB` for the frozen cross-host oracle; the workflow verifier requires
that binding. The discovered pytest journey passes its actually loaded ctypes
library path to Node, so both hosts exercise the same candidate even when the
parent shell has no native override. Commands, triggers, deadlines, package caps
and the existing Release surfaces aggregate remain unchanged.
