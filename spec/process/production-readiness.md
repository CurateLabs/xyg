# Production Readiness

This is the release bar for XYG while the core renderer is still moving.
It separates hard gates from advisory measurements so packaging promises and
API stability do not depend on memory or vibes.

## Current Contract

XYG is early alpha. The goal is Plotly-class chart breadth with a
screen-bounded performance core, but the stable commitments today are narrower:

- Python 3.11+ only.
- `import xyg` stays lightweight and does not import NumPy or load the
  native core. The public API
  gate verifies this in fresh interpreters and keeps package import under a
  200 ms budget. Chart-building APIs are the compute import boundary; notebook
  widget dependencies stay deferred until `.widget()`/display, and standalone
  HTML export reads its static bundle without importing the widget stack.
- Published wheels include only the shippable `xyg/` package,
  `.dist-info`, the render-client JavaScript bundles, `py.typed`, and, for native
  wheels, the Rust core. The JS bundles are a generated artifact (not committed to
  git): the build hook builds them into the wheel/sdist, so **end users do not need
  Rust, Node, npm, or a CDN.**
- Source distributions contain only install and build inputs: the `xyg` package,
  Rust/JS sources, and the prebuilt render
  client. Repository-only docs, tests, benchmarks, scripts, and examples are
  excluded. Installing from an sdist therefore needs no Node.
- Building from a raw source checkout (`pip install` from a clone, or the dev
  workflow) requires a Rust toolchain for the native core and Node/npm for the
  render client — the same two toolchains CI uses. The two differ in strictness:
  the native core degrades gracefully (no Rust → pure-Python wheel, and importing
  the compute layer then raises a clear, actionable error naming the supported
  platforms — there is no NumPy fallback), whereas the render client is **required
  by default** — a from-source build that can neither find nor build the bundle
  fails loudly rather than producing a client-less distribution. `XYG_SKIP_NODE=1`
  opts out for a deliberately client-less build (the widget and HTML export then
  raise a clear error on first use).
- Standalone HTML exports embed the same render client and data payloads used
  by notebooks.
- Benchmark reports must label rendering modes explicitly: `direct`,
  `decimated`, `density`, `sampled`, or `adaptive`.

The currently published alpha's composition API, chart-type set, visual styling
surface remain experimental. Reflex support is removed under #1063. The future accepted
`0.6` line uses the explicit stable/experimental/internal classification and
deprecation commitments in the [public compatibility policy](../releases/compatibility-policy.md).
Its [format and migration inventory](../releases/formats-and-migration.md)
distinguishes canonical data from rebuildable binary/GPU caches. These
preparation documents do not declare an accepted or published `0.6` candidate.

## Fork CI posture

### Main branch merge queue

`main` requires GitHub's repository-level merge queue. Its versioned policy is
`.github/merge-queue-ruleset.json`; branch protection continues to require the
single non-skippable `Release surfaces` aggregate. CI runs for both pull
requests and `merge_group` checks so the required status is produced for the
candidate commit GitHub intends to merge. The queue uses squash commits,
single-entry groups, and one active build to bound CI demand while this suite
is expensive. Concurrency cancels only superseded `pull_request` runs. Pull requests share one group per ref;
every other event (merge group, push to `main`, manual dispatch) gets a group of its own keyed by
the run id (`ci-${{ github.event_name == 'pull_request' && github.ref || github.run_id }}`). Turning
`cancel-in-progress` off is not enough: GitHub keeps one running and one pending run per group and
replaces an older pending run, so a shared group could still drop a main push or merge-group run.
Each main commit needs a complete `Release surfaces` aggregate (including the post-merge benchmark
evidence) for the evidence to be trustworthy.

Keep the ruleset, branch protection status name, and CI event wiring aligned.
GitHub does not run `merge_group` checks through the `pull_request` event, and
missing queue checks block the merge. Contributor instructions are in
`spec/process/contributing.md`.

`make check-ci` (`scripts/verify_ci_workflow.py` plus its contract tests) validates the
`push`/`pull_request`/`merge_group` triggers, the `checks_requested` type and non-canceling
merge-group concurrency, the aggregate's dependency set, per-event applicability, and
`.github/merge-queue-ruleset.json` (exactly one `merge_queue` rule with the recorded
parameters on `refs/heads/main`; the only status check any ruleset may require is the single
`Release surfaces` aggregate). `make check-release-evidence` (read-only) additionally compares
the live ruleset and branch protection with that file and applies the scheduled-evidence rule
below. Live read-back recorded 2026-10-19 (`gh api repos/CurateLabs/xyg/rulesets/24050441`
and `branches/main/protection`): ruleset `main merge queue` active on `refs/heads/main`,
`SQUASH`, one entry built/merged, `ALLGREEN`, 5-minute wait, 240-minute check timeout, identical
to the checked-in file; branch protection requires only `Release surfaces` (strict), no
approving reviews.

### Hard and advisory boundary (#1008)

`Release surfaces` is the one required status. Its inventory lives in
`scripts/verify_release_surface_results.py`; `scripts/verify_ci_workflow.py` fails the build
when `ci.yml` and that inventory disagree, when any `ci.yml` job is unclassified, when a job
uses `continue-on-error`, or when a simulated failure of any applicable job does not fail the
aggregate. Every `ci.yml` job is therefore either a hard gate or the classifier/aggregate
itself; advisory work exists only in scheduled or manual workflows. A skipped job that is
applicable is a failure; a skipped job that is inapplicable is recorded as such.

| Class | `ci.yml` jobs | Applicable when | Result required |
| --- | --- | --- | --- |
| Baseline hard | `test`, `wasm_assets`, `wasm_foundation`, `python_floor` | every event | `success` |
| Release-surface hard | `browser_conformance`, `sdist`, `wheels`, `install_without_rust`, `authored_scene`, `matplotlib_reference` | `merge_group`, `push`, `workflow_dispatch`, and a pull request the trusted-base classifier marks required | `success` when applicable; `skipped` or `success` for a prose-only pull request; never `failure`. `matplotlib_reference` is a pre-merge gate: its failure turns `Release surfaces` red and the merge queue cannot promote a classifier-positive change until the Matplotlib 3.11 reference corpus passes |
| Main evidence hard | `benchmark_vs`, `benchmark_methodology`, `benchmark` | `push` and `workflow_dispatch` only (post-merge; they cannot gate the queue; their producers and report verifier run pre-merge in `test`'s `Benchmark methodology contract` step at the smallest sizes, without timing) | `success` on main; `skipped` or `success` on pull requests and merge groups |
| Support | `release_surface_changes` (classifier), `release_surfaces` (aggregate) | every event | n/a |
| Advisory (outside `ci.yml`) | `codspeed.yml`, `density-100m.yml`, `ceiling-benchmark.yml`, `benchmark-refresh.yml`, `docs.yml`, `binder.yml`, `final-coderabbit.yml` | scheduled or manual | not an aggregate input |

Changes from run 38640943006, where `Release surfaces` passed while three jobs failed:
The packaged `python/xyg/graphforge-compatibility.json` declaration lives under
the classifier's required Python surface; a declaration-only edit requires
the release surface matrix. Compatibility scripts, tests, and checked-in Core
fixtures also require it. The Python Test job runs the complete `tests/` tree,
including the Core corpus and unsupported-version suites.

`matplotlib_reference` moved from a main-only job outside the aggregate to a classifier-gated
release-surface job; the benchmark jobs lost `continue-on-error` and became aggregate inputs
on `push`/`workflow_dispatch`, so main's own evidence failures turn the aggregate red;
`wasm_assets` joined the baseline. The `matplotlib_reference` job runs the full `tests/pyplot`
suite against `matplotlib==3.11.0` (#1035), because the `test` job installs no matplotlib and skips
those tests; a deliberately failing pyplot test therefore turns that job and the aggregate red. Duplicate required statuses and repeated-green-run
ceremony remain out of scope: the aggregate stays one job, and prose-only changes still
execute only baseline jobs.

The post-merge benchmark jobs are hard but hardened against transient infrastructure failure:
package and Playwright installs go through `scripts/ci_retry.sh 3` (linear back-off), and
`benchmark_vs` has a 25-minute (slowest group about 5 minutes when healthy) and
`benchmark_methodology` a 45-minute timeout instead of the earlier 10-minute cap and the
360-minute default. A genuine benchmark or report-verification failure still fails the job. Every `run` step that
pipes a command (for example `bench.py | tee -a docs/benchmark_ci.md`) must use `shell: bash`
(GitHub runs it as `bash -eo pipefail`) or set `pipefail` itself, because the default `bash -e`
reports the last pipe stage and would mask a crashing benchmark; `scripts/verify_ci_workflow.py`
enforces this for `ci.yml`, `codspeed.yml`, `density-100m.yml` and `publish.yaml`. The rule
fails closed on a pipe inside a folded `run: >` scalar, checks unnamed `- run:` steps, accepts only
`bash` as the effective step/job/default shell (or a `set -o pipefail` statement that no later
`set +o pipefail` undoes), and treats a pipe inside `$(...)` as a pipe. It does NOT cover the
workflows the checker does not validate: `docs.yml`, `binder.yml`, `benchmark-refresh.yml` and
`ceiling-benchmark.yml` (whose "Summarize" step pipes into `tee` without `pipefail`).

**Scheduled evidence blocks readiness through issue state.** Scheduled performance and
browser evidence (CodSpeed, the density authority) is not an aggregate input and never runs
on pull requests, but a known unresolved failure must not read as readiness. Before a release
authorization, a "main is green" claim, or closing the release tracker, run
`python3 scripts/check_scheduled_evidence.py`: it judges each scheduled workflow on `main` by
its evidence jobs' own results, not the run conclusion. The newest run that actually executed
the evidence jobs must have every one succeed; a run whose detector skipped them
(`codspeed_should_run.py` saw an earlier success on the same commit) is no evidence, so it cannot
clear an earlier failed execution (for example success on S, failed manual rerun on S, then a
skipped scheduled run that concludes `success`). The check also blocks when the newest run is older
than three days or no run ever executed the evidence jobs; while a `ci.yml` push run on
`main` is still queued or in progress (no evidence yet, never green); and unless the latest
completed `ci.yml` push run concluded `success` at run level, has at least one job (a zero-job
startup failure is no evidence), and has no failed, cancelled, or timed-out job (including the
pre-#1008 advisory jobs). Because an in-progress main run is reported as blocking ("no evidence yet"), a
readiness check run while main CI is still going will fail and must be repeated after the run
completes. Each blocking finding must be tracked by an open linked issue, which closes
only after a later scheduled run on `main` succeeds.

CurateLabs/xyg is a permanently divergent product repository, not a deployment
branch of `reflex-dev/xy`. CI therefore retains only workflows whose external
integrations are owned or explicitly controlled by CurateLabs:

- Every Actions job except the CodSpeed performance job runs on a pinned
  Blacksmith Linux, ARM, Windows, or macOS runner; the canonical Linux CI image is
  `blacksmith-4vcpu-ubuntu-2404`, and no workflow may use a GitHub-hosted
  runner alias. `ci.yml`,
  `docs.yml`, and `binder.yml` are hard verification paths.
  Binder builds locally with repo2docker. The main CI test job runs the graph,
  complete Node host, and chart-scale/pyramid checks directly with Cargo,
  pytest, and npm; see [build-ci.md](../design/build-ci.md).
- The sole runner-policy exception is `codspeed.yml`: it is the repository's
  native performance trend path and uses
  the dedicated `codspeed-macro` bare-metal runner plus GitHub OIDC to the
  CurateLabs CodSpeed project. This prevents base/head comparisons from
  crossing Blacksmith Intel and AMD generations; CodSpeed remains the hosted
  performance authority.
- `benchmark-refresh.yml` and `ceiling-benchmark.yml` are manual evidence
  workflows. The ceiling sweep uses the billed
  `blacksmith-12vcpu-macos-15` Apple Silicon M4 runner (48 GB RAM).
- `publish.yaml` is the guarded `xyg` release workflow described below.

Playwright browser artifacts are cached on Blacksmith. Chromium-only install
steps have a ten-minute bound and the three-engine install has a fifteen-minute
bound; none invokes Playwright's coupled `--with-deps` path. Blacksmith images
carry the Chromium and Firefox runner libraries. The three-engine job installs
only WebKit's additional runtime libraries in a separate twenty-minute-bounded
step. Two runner behaviors are handled there:

- apt's needrestart hook would restart runner services after the install and
  never return, so it is set to list-only in its configuration (install-deps
  runs apt through sudo, which drops the environment);
- the runner's apt mirror is slow and erratic (1 to 20+ minutes for the same
  ~250 packages), so the downloaded `.deb` files are cached. apt keeps them,
  a newest-by-prefix cache restore seeds `/var/cache/apt/archives` before
  install-deps, `apt-get autoclean` drops versions the mirror no longer
  serves, and a per-run save runs only when the package set changed, so
  updated Ubuntu packages are retained without an entry per run.

`scripts/verify_ci_workflow.py` requires each of these settings. Real browser
launches remain the dependency proof.

The inherited reflex.dev deployment workflows were removed. They built images
for upstream AWS, Harbor, and Azure registries, changed
`reflex-dev/helm-charts`, and polled the upstream `xy` PyPI project; they could
only fail or mutate infrastructure outside this repository. XYG documentation
now builds with Astro Starlight into `docs/app/dist/`,
matching the CurateLabs GraphForge documentation platform. The docs workflow
verifies static routes, Markdown assets, links, demos, the public quickstart,
and the production browser experience, then retains the verified static site.
It requires no Reflex server or docs-specific Python environment. The design
and reproduction contract is [docs-starlight.md](../design/docs-starlight.md).
Deployment must still be introduced as a new CurateLabs-owned contract rather
than reenabling the inherited workflows.

## Accessibility and Cross-Browser Conformance Status

The current conformance tier covers a parallel semantic chart region and
generated trace/axis summary, a polite live region for hover and keyboard
readouts, focusable direct-point navigation with Arrow/Home/End keys, named
toolbar controls with toggle state, visible focus styling, reduced-motion
behavior, and forced-colors affordances.

The public documentation uses Starlight navigation, theme controls, search,
and code rendering. Its Chromium smoke exercises the built static site and
interactive examples; the built-output gate validates routes, links, metadata,
and downloadable Markdown. These documentation checks are distinct from the
three-engine chart conformance gate below and do not certify every
screen-reader/OS combination.

CI runs the same focused chart in Playwright Chromium, Firefox, and WebKit. It
checks those semantics and interactions in every engine, compares WebGL output
with a coarse per-channel perceptual signature, and compares DOM chrome through
layout boxes rather than browser-font glyph pixels. The gate does **not** yet
cover aggregated-bin keyboard navigation, a view-as-table escape hatch,
screen-reader/OS combinations, every chart family, or full-page screenshot
parity. Run the focused tier locally with `make check-conformance` after
installing all three engines with
`npx playwright install chromium firefox webkit`.

## Release-Blocking Gates

These must pass before publishing.

| Area | Gate | Command or evidence |
|---|---|---|
| Python floor | `pyproject.toml`, Ruff, docs, syntax, and annotations stay on the Python 3.11+ floor | `python scripts/check_python_floor.py` |
| Public API | `__all__`, lazy exports, `__version__`, the source `py.typed` marker, focused type-surface tests, and fresh-process import-time budget stay coherent | `make check-api` |
| Import-time budget | `xyg.__init__`, `dir(xyg)`, export helpers, chart construction, and `.widget()` keep their lazy import boundaries | `make check-import` |
| CI/release workflows | Hard gates, non-blocking benchmarks, best-effort benchmark artifact upload/download, trusted publishing, and no-Rust clear-error jobs stay wired | `make check-ci` |
| GitHub Actions token scope | CI, release, and manual benchmark workflows declare an explicit least-privilege `GITHUB_TOKEN` default; privileged jobs use narrow job-level overrides | GitHub code scanning (`actions/missing-workflow-permissions`) |
| HTML export safety | Inline JSON/script escaping, atomic path writes, hostile user strings, and browser client text-node insertion stay protected | `make check-security` |
| Python tests | Native backend passes | `pytest -q` |
| Python style | Library, tests, scripts, and benchmarks lint clean | `ruff check .` and `ruff format --check .` |
| Matplotlib reference | The reviewed compatibility snapshot matches the pinned released matplotlib reference, and the `xyg.pyplot` shim passes its interoperability and dual-engine corpus suites | `python scripts/sync_matplotlib_compat.py --check` and `pytest tests/pyplot` |
| Rust core | Native kernels pass and lint clean | `cargo test --workspace` and `cargo clippy --workspace --all-targets -- -D warnings` |
| Native ABI | C ABI can be loaded from the built core | `python scripts/abi_smoke.py` |
| JavaScript | Render client builds cleanly from source | `node js/build.mjs` |
| Browser render | WebGL smoke reaches real pixels | `python scripts/render_smoke_nonumpy.py <chromium>` |
| Accessibility / cross-browser | Semantic interaction checks plus tolerant WebGL/layout comparison pass in Chromium, Firefox, and WebKit | `make check-conformance` |
| Real chart render | A real composed chart exports and paints in Chromium | `python scripts/smoke_render.py <chromium>` |
| Step tier update | A decimated `step` chart keeps its risers after a synthetic kernel `tier_update` replaces the vertex buffers | `python scripts/step_tier_smoke.py <chromium>` |
| Dashboard reliability | Attempts 10/20/50/60 charts with hosted packaged Rust/WASM ticks admitted on every created chart, hard-gates the 10-chart row as loss-free and nonblank, retains partial larger rows, and applies the production shader-cache oracle to a complete, fully nonblank, loss-free 60-chart row | `python benchmarks/bench_dashboard.py --chart-counts 10,20,50,60 --chromium <chromium> --json dashboard-smoke.json` then `python scripts/verify_benchmark_report.py dashboard-smoke.json --kind dashboard-browser` |
| sdist | Build-input-only source archive contains the `xyg` package and render-client bundles, complete JS/Rust build sources, and `PKG-INFO` version/dependencies (without Reflex dependencies or an adapter extra) matching the archive's own `xyg-<version>` root; repository-only material, duplicate/unsafe members, native binaries, and generated junk are absent | `python scripts/verify_sdist.py dist/*.tar.gz` |
| Native wheel | Platform wheel contains package-only `xyg` files, exactly one native library, no framework wrapper or duplicate render client, `METADATA` version/base dependencies and no Reflex extra matching the wheel's own filename and `.dist-info`, complete hash-checked `RECORD`, public export-surface markers, matching filename/`WHEEL` tags, and is tagged non-pure | `python scripts/verify_wheel.py dist/*.whl --expect-native` |
| Fallback wheel | No-toolchain wheel contains package-only `xyg` files, `METADATA` version/base dependencies and no Reflex extra matching the wheel's own filename and `.dist-info`, complete hash-checked `RECORD`, public export-surface markers, matching filename/`WHEEL` tags, is pure, and contains no native library | `python scripts/verify_wheel.py dist/*.whl --expect-pure` |
| Wheel size | Platform wheel remains small enough for notebook installs | CI budget: 15 MB |
| Benchmark artifact | JSON benchmark reports carry schema, environment, categories, row status, and finite non-negative metrics; native reports must declare the native backend | `python scripts/verify_benchmark_report.py benchmark.json --kind scatter-vs`; repeat for line, install, core-2D, pyplot-vs-matplotlib, native, interaction, dashboard, and workflow artifacts |

Type checking is **advisory, not release-blocking**. CI runs `ty check python`
and reports findings without failing the build, and `scripts/verify_local.py`
registers the same check with `advisory=True`, so `make check-full` prints
warnings for type findings rather than failing. Promoting it to a hard gate is
tracked in the Hardening Backlog. The full-package `py.typed` marker is a hard
gate, but it is enforced by `make check-api`
(`scripts/check_public_api.py`), not by the type checker.

## Standalone HTML Safety

`Chart.to_html()` produces one self-contained document: inline JavaScript,
inline JSON spec, and a base64 data blob. That shape is convenient for notebooks,
reports, and sharing a single file, but it has a clear security contract:

- User-controlled strings in titles, labels, legends, trace names, categories,
  and series names must be escaped before entering inline JSON or `<title>`.
- The bundled standalone client is escaped before inlining so a literal
  `</script>` inside future client source cannot terminate the script element.
- The export rejects `NaN` and infinity in JSON metadata instead of emitting
  browser-dependent invalid JavaScript.
- Path-based exports write through a same-directory temporary file and only
  replace the target after the full document is flushed, so failed writes do
  not corrupt the previous standalone artifact.
- The standalone file emits a defensive `Content-Security-Policy` meta tag that
  blocks network fetches, external worker scripts, objects, forms, and external
  images, and pins `base-uri 'none'`, while allowing the inline scripts/styles
  required by single-file export. Workers are restricted to `blob:` URLs so the
  bundled density re-bin worker can boot from its own inlined source; no
  external worker script can load.
- The browser client inserts user-facing text with `textContent` or text nodes;
  HTML parser sinks such as `innerHTML` are reserved for fixed internal icons,
  not titles, labels, legends, categories, or tooltips.
- Hosts that need nonce/hash-only strict CSP should serve the JavaScript bundle
  as a separate asset and inject data through a nonce/hash-aware wrapper.
- Static PNG export validates width, height, scale, and timeout options before
  launching Chromium so bad user input produces actionable Python errors, and
  keeps Chromium's sandbox enabled by default. Pass `sandbox=False` only for
  trusted HTML in constrained CI/container environments that cannot launch a
  sandboxed browser.
- Export tests should include weird strings with `</script>`, HTML entities,
  mixed-case tags, and Unicode line/paragraph separators.

## Local Verification Shortcut

Use the focused gates below while iterating, then run the full gate before a
production-facing push:

| Changed surface | Focused gate |
|---|---|
| Public docs, API prose, examples, public benchmark wording, Starlight build | `make check-docs` |
| `spec/api/api-examples.md`, application consumer assets | `make check-examples` |
| Public validation, error messages, builder rollback, LOD/drill mutation boundaries, chart/widget caching | `make check-errors` |
| Public exports, lazy import mappings, component factories, public annotations | `make check-api` |
| Import-time budget, `xyg.__init__`, dependency boundaries, widget/export/backend import boundaries | `make check-import` |
| `xyg.pyplot` shim behavior, matplotlib interoperability, reference corpus | `make check-pyplot` |
| Reviewed matplotlib compatibility snapshot (`spec/matplotlib/compat-matrix.md`) | `python scripts/sync_matplotlib_compat.py --check` |
| `xyg.pyplot` speed margin against matplotlib | `make check-pyplot-speed` |
| Standalone HTML export, path writes, user text, tooltips, legends, browser DOM insertion | `make check-security` |
| Benchmark harness code, environment metadata, report schema, regressions | `make check-benchmark-harness` |
| Generated benchmark JSON artifacts | `make check-benchmark-report BENCHMARK_JSON=benchmark.json BENCHMARK_KIND=scatter-vs` |
| CI/release workflows, artifact upload/download, no-Rust clear-error jobs | `make check-ci` |
| Source distributions and wheels | `make check-sdist` and `make check-wheel` |
| Existing release artifacts | `make check-artifacts SDIST=/path/to/xyg.tar.gz WHEEL=/path/to/xyg.whl` |
| Browser render/lifecycle/interaction smoke | `make check-browser CHROMIUM=/path/to/chrome` |
| Production-facing PR | `make check-full` |

Use this before pushing production-facing changes:

```bash
make check-full
```

Use this after editing public docs, API examples, benchmark wording, or the
Starlight documentation app:

```bash
make check-docs
```

This builds and validates the static documentation, runs the checkout
quickstart, and executes the canonical example gate. Install the root Python
environment, build the native core and browser client first; see
[docs-starlight.md](../design/docs-starlight.md) for the clean-checkout commands.
For documentation UI or interactive-demo changes, also run
`node docs/app/scripts/browser-smoke.mjs` against the built site with Chromium
installed. No Reflex production server is part of this docs gate.

The browser gates are split into app-facing checks that match the CI step
names: `Browser lifecycle smoke (Chromium)`, `Browser visual regression smoke
(Chromium)`, `Step tier-update smoke (Chromium)`, `Browser interaction stress
smoke (Chromium)`, and `Browser dashboard reliability smoke (Chromium)`.
`make check-browser` runs all of these except the dashboard reliability smoke,
which runs in CI only. The lifecycle and visual smokes both boot the
`examples/fastapi` app under uvicorn and drive Chromium at its live routes (no
committed HTML): the lifecycle smoke loads every gallery chart and the live
drilldown and requires each to report nonblank pixels through `initial`,
`narrow-resize`, `wide-resize`, `visibility-change`, `context-restore`, and
`restore` (and to keep its runtime DOM slots), then confirms the index page's
embedded iframes paint; the visual regression smoke screenshots every gallery
route and checks nonblank/colored/occupancy plus tick-label overlap. The
`context-restore` phase forces `WEBGL_lose_context` loss/restoration and
requires the rebuilt chart to remain nonblank. The interaction stress smoke
validates the real `ChartView` wheel zoom, pan, hover, crosshair, box zoom, and
brush-select paths with p95 budgets plus visual invariants for blank frames,
tick-label overlap, tooltip stability, crosshair visibility, view changes, box
zoom narrow/restore behavior, brush select count/clear behavior, lit-pixel
readback floors, and frame-to-frame color jumps. The visual regression smoke
also validates title, plot, x-axis, and y-axis regions plus plot-region
occupancy, and it screenshots static declarative chrome shells for the custom
legend/tooltip and annotated heatmap examples. A chart cannot collapse into a
corner, lose axis/custom chrome, or pass merely because some pixels exist
somewhere.

Use this after packaging, workflow, or source-distribution changes:

```bash
make check-sdist
make check-wheel
```

Use `make check-wheel WHEEL_EXPECT=--expect-native` when verifying a native
release wheel, or `WHEEL_EXPECT=--expect-pure` when intentionally checking the
no-native artifact (it imports but errors clearly the moment compute is needed).

Use this after editing CI/release workflows, benchmark artifact upload/download
wiring, trusted publishing, or the no-Rust clear-error install jobs:

```bash
make check-ci
```

Use this when release automation has already produced artifacts and you need to
verify those exact files rather than rebuilding locally:

```bash
make check-artifacts SDIST=/path/to/xyg.tar.gz WHEEL=/path/to/xyg.whl
```

Use this after editing `spec/api/api-examples.md` or the application example chart
registry/assets:

```bash
make check-examples
```

Use this after touching standalone HTML export, path writes, inline JSON/script
escaping, tooltips, legends, category labels, or browser client DOM text
insertion:

```bash
make check-security
```

Use this after changing public validation, error messages, builder rollback
behavior, LOD/drill mutation boundaries, or chart/widget caching:

```bash
make check-errors
```

Use this after changing public exports, lazy import mappings, component
factories, or public type annotations:

```bash
make check-api
```

Use this after changing `xyg.__init__`, lazy import boundaries,
dependency boundaries, widget/export boundaries, or backend import setup:

```bash
make check-import
```

Use this to validate generated benchmark JSON before publication or downstream
analysis:

```bash
make check-benchmark-report BENCHMARK_JSON=benchmark.json BENCHMARK_KIND=scatter-vs
```

Use this after changing benchmark harness code, report-schema validation,
environment metadata, regression comparison scripts, or benchmark methodology
tests:

```bash
make check-benchmark-harness
```

Browser smoke and package artifact verification need a built bundle, Chromium,
and wheel/sdist outputs. The interaction gate's real-wall-clock worker probe
also uses the pinned development-only Playwright driver; install it once with
`make setup-browser` (or `npm install`). These gates are required in CI and
release workflows even if they are skipped locally.

For browser checks, pass the local Chromium/Chrome binary explicitly:

```bash
make check-browser CHROMIUM=/path/to/chrome
```

The lifecycle gate runs `scripts/app_lifecycle_smoke.py`. It boots the
`examples/fastapi` app under uvicorn and, for every gallery chart route plus
`/drilldown`, injects a probe over CDP (before the chart client loads) and
requires the view to survive the `initial`, `narrow-resize`, `wide-resize`,
`visibility-change`, `context-restore`, and `restore` phases with nonblank
pixels and its runtime DOM slots intact. The `context-restore` phase forces
`WEBGL_lose_context` loss/restoration and requires the rebuilt chart to remain
nonblank. A final pass loads the index page and confirms its embedded iframes
paint. Empty canvases, destroyed views, shortened lifecycle reports, failed
context restores, or missing DOM slots fail the gate.

The visual gate runs `scripts/visual_regression_smoke.py`. It boots the same
app and screenshots every gallery chart route plus `/drilldown`, checking
nonblank, colored, unique-color, plot-occupancy, and tick-label-overlap
invariants so a blank, flat, or collapsed chart fails the gate.

The interaction gate runs `scripts/interaction_stress_smoke.py`, which is a
smaller gated version of `benchmarks/bench_interaction.py`. The smoke validates
interaction budgets for direct scatter, density scatter, line, histogram, bar,
and heatmap rows so performance regressions are not scatter-only and not
direct-scatter-only. For pickable rows, tooltip stability means every declared
repeated hover sample must remain visible, so a tooltip that appears and
immediately disappears fails the gate.

Use `make list-checks` to see the individual check names, or
`python scripts/verify_local.py --dry-run --full` to print commands without
running them. The full local gate expects Node 18+ plus a Rust toolchain with
`cargo`, `rustc`, and clippy (`rustup component add clippy`). Missing Rust,
Node, Chrome, `ruff`, `ty`, or `pytest` produce direct install/skip guidance.

## Release Checklist

For a tagged release, the tag *is* the version. `pyproject.toml` declares
`dynamic = ["version"]`, and uv-dynamic-versioning reads an exact `xyg-v*` tag.
Cutting a release is `git tag xyg-vX.Y.Z && git push origin xyg-vX.Y.Z` — there
is no number to bump in a file, and no file that can drift from the tag.
Untagged commits after a release use `<next>.devN+<commit>`; before the first
XYG tag, the `0.0.0` seed produces the `0.0.1.devN+<commit>` fork baseline.
A metadata-free source tree uses the explicit `0.0.0` fallback. Consequences:

- Every checkout that builds must be unshallow (`fetch-depth: 0`). A depth-1
  clone may omit the authoritative release tag and silently derive a different
  development baseline; `make check-ci` enforces full history.

Pre-releases are tagged the same way with the canonical semver suffix —
`xyg-vX.Y.Z-alpha.N` / `-beta.N` / `-rc.N` (e.g. `xyg-v0.6.0-rc.5`) — and publish
through the same pipeline; pip ignores them unless a pre-release is requested
explicitly. One conversion authority, `scripts/release_version.py`, drives tag
validation (`check_release_version.py`), npm staging
(`stage_node_packages.py`, `stage_browser_package.py`) and the release-cohort
check (`verify_release_cohort.py`). The same release has three spellings:

| Surface | Spelling for the fifth 0.6.0 candidate |
| --- | --- |
| Git tag | `xyg-v0.6.0-rc.5` |
| npm (`@curatelabs/xyg*`) | `0.6.0-rc.5` |
| Python/PyPI (derived from the tag by uv-dynamic-versioning) | `0.6.0rc5` |

The legacy PEP 440 tag spelling (`xyg-v0.0.1a1`, `xyg-v0.6.0rc5`) still passes
for already-cut tags and normalizes to the same npm and Python versions. Dev,
post, local, malformed, leading-zero (`-rc.05`, `rc05`, `0.06.0`), and
spelling-mixed (`-rc5`, `-RC.5`) forms fail with an actionable error. A
pre-release needs its own dated changelog entry (Python or npm spelling of the
version), exactly like a final release. Version normalization covers ecosystem
spelling only: native ABI, Scene, wire, painter, and WASM identifiers keep their
own contracts and are never derived from the release version. XYG and
GraphForge Core candidates need not share an RC number; the paired Core
declaration is owned by #936. Reproduce with
`python3 scripts/check_release_version.py --tag xyg-v0.6.0-rc.5` and
`python3 -m pytest tests/test_release_version.py tests/test_check_release_version.py`.

The repository has one release line: the `xyg` distribution ships from
`xyg-vX.Y.Z` tags through `publish.yaml`. The Python package and distribution
share the canonical `xyg` identity; no `xy` compatibility import, `reflex_xy`
namespace or `xyg[reflex]` extra ships.

### Fork release posture (CurateLabs/xyg, issue #13)

This repository is CurateLabs' permanently divergent fork of `reflex-dev/xy`.
The Python distribution is **`xyg`** — not upstream's PyPI package `xy`.
`.github/workflows/publish.yaml` (filename required by the PyPI trusted
publisher) publishes only from tagged releases, with layered guards:

- **Repository guard.** The publish job carries
  `if: github.repository == 'CurateLabs/xyg'`, so no other slug
  (including forks or mirrors) reaches the publish job at all.
- **Publish-name guard.** A step ahead of the upload fails any *real* publish
  attempt — tag push or non-dry-run dispatch — unless every artifact in
  `dist/` is named `xyg`, and it still refuses upstream's `xy`. Dry-run
  dispatches skip the check so the cross-compile matrix stays verifiable.
- **GitHub environment.** The publish job uses environment `pypi` (no
  required reviewers) so OIDC trusted publishing can mint a token bound to
  that environment name.
- **Publish opt-in.** The upload step itself additionally requires the
  `XYG_ALLOW_PYPI_PUBLISH` and `XYG_ALLOW_NPM_PUBLISH` repository variables to
  equal `'true'`. Both opt-ins certify that registry bootstrap and candidate
  acceptance are complete. A version tag with either opt-in absent builds
  and verifies artifacts but uploads to neither registry. The complete seven
  npm archives, tag-derived versions, and browser asset hashes are checked
  before PyPI uploads. Aligned uploads target the existing PyPI project `xyg`,
  whose first alpha is already available.
- **Tagged dispatch only.** A non-dry-run `workflow_dispatch` must target an
  existing `refs/tags/xyg-v*` ref and runs the same tag/CHANGELOG gate as a tag
  push. Dispatching `main` can exercise the complete dry-run matrix, but can
  never publish even when the repository opt-in is enabled.
- **GitHub Release after both registries.** Once the PyPI and npm jobs succeed,
  `github-release` creates the matching GitHub Release with generated notes
  and attaches the runtime-verified PyEmscripten wheel and browser archive.
  The shared release-version parser classifies canonical and legacy alpha,
  beta, and RC tags; these releases use `--prerelease --latest=false` so a
  candidate cannot become the stable/latest GitHub release. It has
  `contents: write`; build and PyPI jobs remain read-only except for the OIDC
  token. The docs workflow builds
  and retains a verified Astro Starlight static
  site, but there is currently no production-documentation deployment
  workflow: the inherited reflex.dev promotion path was removed because
  CurateLabs does not own its registries or Helm destination. A future docs
  deployment needs a separate CurateLabs-owned destination and release
  contract; see [docs-starlight.md](../design/docs-starlight.md).

`scripts/verify_ci_workflow.py` (`make check-ci`) pins these guards, and
`tests/test_verify_ci_workflow.py` covers their removal.

**Versioning decision.** The fork has its own `xyg-v*` tag line. Dunamai's
default `v` pattern is narrowed with `pattern-prefix = "xyg-"`; the release
workflow triggers on that prefix, and the release gate rejects bare `vX.Y.Z`.
Inherited upstream tags (`v0.0.1`–`v0.0.6a2`), docs CalVer tags, and
`reflex-xy-v0.0.1`/`v0.0.2` remain on `origin` as historical provenance, but
cannot determine an XYG version or trigger an XYG release. No destructive tag
pruning is required. The fork's published alpha is `0.0.1a2`; future production
tags use the `xyg-v*` line and the same opt-in and artifact verification gates.

**Registry snapshot (2026-10-22).** PyPI contains only `xyg` 0.0.1a2, with
`xyg-0.0.1a2-py3-none-manylinux_2_39_x86_64.whl` (Linux x86-64, glibc 2.39+)
and `xyg-0.0.1a2.tar.gz`. Neither `@curatelabs/xyg` nor
`@curatelabs/xyg-node` is published to npm. Source/release-matrix coverage,
runtime-verified build artifacts, and inherited upstream release history must
not be presented as current registry inventory. Public installation docs pin
the verified alpha and identify source-only targets. Refresh the dated snapshot
after publication rather than treating it as a permanent platform limit.
Verify inventory against `https://pypi.org/pypi/xyg/json`,
`https://registry.npmjs.org/@curatelabs%2fxyg`, and
`https://registry.npmjs.org/@curatelabs%2fxyg-node`; both npm endpoints returned
HTTP 404 in that snapshot. The PyPI sdist includes prebuilt paint bundles;
building its native core needs Rust/platform tooling, while a fresh checkout
also needs Node/npm to generate its untracked client bundles.

npm registry publication of `@curatelabs/xyg` and the complete
`@curatelabs/xyg-node` set remains tracked by the packaging milestone. The
tracked Node manifests intentionally remain `"private": true`, version
`0.0.0`, and use local `file:` optionals so a source checkout cannot publish.
The release workflow uses `scripts/stage_node_packages.py` to create separate
publishable trees from the release tag: five exact-platform packages reuse the
byte-identical cdylibs already verified inside the Python wheels and require a
valid ELF64, Mach-O 64-bit, or PE architecture header, while the
facade pins every optional to the mapped npm semver and embeds the exact built
standalone paint client for offline `toHtml()` use. The canonical tag
suffixes `-alpha.N`, `-beta.N`, and `-rc.N` map to npm unchanged (and to Python
`aN`, `bN`, `rcN`); the legacy PEP 440 tag suffixes `aN`, `bN`, and `rcN` map to
the same npm versions; stable versions are identical.

Every run packs and dry-publishes all six Node tarballs and the browser tarball.
The publisher requires exactly these seven packages at one version: five native
packages, `@curatelabs/xyg`, and `@curatelabs/xyg-node`. Browser validation rechecks
the four-asset inventory, SHA-256 digests, byte lengths, WASM header, canonical
exports, and absence of runtime dependencies or package executables. A real
npm upload is additionally gated by an `xyg-v*` ref, non-dry dispatch, repository identity,
the `npm` GitHub environment, and both `XYG_ALLOW_PYPI_PUBLISH=true` and
`XYG_ALLOW_NPM_PUBLISH=true`. The PyPI job (including the shared tag,
CHANGELOG, and package-name guards) succeeds before npm can publish.
Publication
uses npm trusted publishing on a GitHub-hosted runner (Node 24, npm >=11.5.1,
OIDC `id-token: write`) and publishes platform packages, then the browser,
then the facade, so the public facade never points at absent versioned optionals. Prerelease
versions (`-rc.N`, dry runs) publish under the `next` dist-tag, which npm
requires and which keeps them off `latest`. npm publication is retry-safe: `scripts/publish_node_packages.py` skips an immutable version only
after both its registry SHA-1 and SHA-512 Subresource Integrity value match the
local tarball, preflights every existing package before any new upload,
rejects a mismatch in either digest, and resumes the native-first sequence
before publishing the browser and facade. After each upload it polls briefly
for npm visibility and proves both registry digests before advancing to the next
native package or, last, the facade. A visibility timeout reports that the
release must be retried for verification; it never treats an accepted upload as
verified merely because the publish command returned successfully. Registry
inspection and upload subprocesses use a five-minute timeout so a
stalled npm endpoint fails promptly instead of holding a partial release until
the workflow-wide limit. This makes cross-registry recovery convergent even
though PyPI and npm cannot provide one atomic transaction. Configure this
exact `publish.yaml` workflow as the trusted publisher for all seven npm
projects; first-time project creation/ownership remains a deliberate registry
bootstrap step. npm requires each project to exist before trusted publishing
can be configured. An authenticated maintainer with package write access must
bootstrap the project and complete the interactive 2FA challenge for
`npm trust`; GitHub repository access alone does not grant npm scope ownership.
Use the accepted package bytes for the first real candidate upload if
bootstrapping with that candidate; do not manufacture a placeholder RC.
The publisher relationship is `CurateLabs/xyg` / `publish.yaml` / environment
`npm`, and must explicitly allow `npm publish` because newly created trust
relationships otherwise permit only staged publication. See the
[npm trust prerequisites](https://docs.npmjs.com/cli/v11/commands/npm-trust/)
and [trusted publishing configuration](https://docs.npmjs.com/trusted-publishers/).
The GitHub Release waits for both PyPI and npm jobs.

The release-only `browser-package` job builds the direct `xyg-engine` WASM
adapter and the ESM, standalone, and static Worker bundles from the tagged
source, then stages an exact-version `@curatelabs/xyg` tarball. Its
`ASSET-MANIFEST.json` binds every shipped filename to SHA-256 and byte length
and records the wire protocol, WASM ABI, Scene, and painter versions. Staging
leaves out the Python-only self-contained HTML inline worker
(`wasm-inline-worker.js`, `xyg-wasm-inline.js`, packaged into the wheel by
`hatch_build.py`) and rejects any other extra file (including source maps),
symlinked assets,
CDN/repository/fork-origin paths, runtime dependencies, npm lifecycle scripts
or executable bins, invalid WASM headers, and per-file or aggregate budget
overruns. The tarball is then unpacked into a clean directory and the existing
strict-CSP/local-only lifecycle harness serves only its ESM, IIFE, Worker, and
WASM assets. It rechecks every manifest SHA-256 and byte length before loading,
requires the IIFE to expose `window.xy`, and exercises the Worker ABI mismatch,
trap, and disposal negatives without a network fallback. The tarball is packed
and dry-published on every release rehearsal,
blocks the PyPI release gate if it cannot be produced, and is published to npm
with the same verified bytes and attached to the matching GitHub Release.
Registry publication and clean browser-application conformance remain the
explicit completion work for issue 53 until their actual results are recorded.

Version-tag releases also assemble a Linux x64 cross-host cohort from the
exact manylinux wheel, Node facade and native package, and host-neutral browser
tarball produced by that workflow run. `scripts/verify_release_cohort.py`
requires the Python and npm versions to match the tag, proves that Python and
Node carry byte-identical Rust cores, proves that Python, Node, and browser
carry the same standalone painter, rechecks the browser asset manifest, and
emits a SHA-256 ledger bound to the full release commit. The release-only job
then installs those four archives in a new Python virtual environment and npm
project and resolves the direct-browser WASM locally. This is the first issue
54 cohort; the remaining platform, notebook/Streamlit, VS Code local/remote,
journey, lifecycle, and leak/isolation matrix remains required before closure.

Packing is followed by native clean-install conformance on all five supported
Node targets: Linux x64/arm64, macOS x64/arm64, and Windows x64. Each job starts
with a new npm project, proves the facade's missing-package diagnostic, installs
the matching packed native package, verifies that the resolved cdylib is inside
that exact optional package, validates the generated ABI, builds a canonical
scatter payload, and emits a network-free self-contained HTML export. The
packed facade is also probed with an explicit Windows-arm64 host identity to
prove the stable unsupported-platform message and remediation before any native
discovery. These jobs gate both PyPI and npm
publication. They prove the packed artifacts themselves, not an in-repository
build or a cross-compiled executable header; VS Code local/remote application
conformance and the immutable published-version ledger remain part of #52/#54.

In-tree inventory, hashes, NOTICE/license checks, path scans, and size budgets
run via `python3 scripts/verify_node_packages.py` (CI Test job; `--require-native`
after local staging; `--sbom` emits a CycloneDX-lite document). Never publish
`@xy/node`.

Python import `xyg` / `python/xyg/`, the distribution name, and
`importlib.metadata` lookups all use `xyg`. The clean break intentionally ships
no `xy` compatibility package or framework adapter namespace. `tests/test_xyg_package_identity.py` locks this identity.

Before tagging an `xyg-v*` release:

- Add a dated `## [X.Y.Z] — YYYY-MM-DD` heading to `CHANGELOG.md` for the
  version being tagged. This is the one thing the tag cannot vouch for, and the
  release gate blocks the publish without it.
- Refresh benchmark reports or explicitly document why the previous report still
  applies.
- Run `make check-full` locally or confirm the equivalent
  CI gates passed on the release commit.
- Run `make check-ci` to confirm CI and release workflow
  gates still include artifact verification, upload/download, and trusted PyPI
  publishing.
- Before the first release after a change to the wheel matrix (new target,
  cross-compile toolchain, or tagging scheme), manually run the release
  workflow (`workflow_dispatch`, `dry_run` defaults to `true`) and confirm
  every leg of the cross-compile matrix — including the newer aarch64/armv7/
  musllinux/win-arm64 targets and the wasm job — actually builds, since a
  target added to the matrix but never exercised in CI is unverified, not
  working.
- Confirm CI built and verified native wheels for Linux glibc and musl/Alpine
  (x86-64, aarch64, armv7), macOS (x86-64, Apple Silicon), and Windows (x86, x64,
  arm64).
- Confirm the release workflow produced seven npm tarballs (five native,
  browser, and facade), each platform package contains the native bytes extracted from its exact wheel, every
  manifest carries the tag-derived npm semver and CurateLabs repository
  identity, and the facade contains the byte-identical standalone paint client.
- Before the first npm release, create/claim all seven scoped public projects,
  including `@curatelabs/xyg`, and bind their trusted publisher to `CurateLabs/xyg` / `publish.yaml` /
  environment `npm`, then enable `XYG_ALLOW_NPM_PUBLISH` alongside the PyPI
  opt-in. Keep either variable unset for build-only release rehearsals.
- Confirm the Pyodide/Emscripten wheel passes its runtime load gate, not only
  its structural wheel check. The tested toolchain is Rust 1.96.0 with
  `panic=abort`, Emscripten 5.0.3, cibuildwheel 4.1.0, the PEP 783
  `pyemscripten_2026_0` wheel ABI, and Pyodide 314.0.0. The abort strategy keeps
  Rust panics from unwinding across the Python/`ctypes` C ABI boundary.
  `scripts/pyodide_load_smoke.py` installs the exact built artifact with
  micropip, loads the C ABI through `ctypes`, verifies `xyg_abi_version`, and
  calls the native `min_max` kernel. It then disables network access and makes
  the actual Pyodide runtime consume every Rust-generated XYTS conformance
  Scene, exercising Scene v16 SVG, raster-command, and exact painter-v11
  lowering through the native `xyg_scene_browser_painter` ABI. It directly
  calls every Emscripten-only filesystem stub and verifies its fail-closed
  sentinel and generated signature. Dependency and
  wheel provisioning precede that offline boundary; browser CSP is separately
  proven by the local-only direct-WASM smoke because CSP does not apply to the
  Node-hosted Pyodide runtime. Filesystem-backed XYGC/tile-store ABI entries
  remain present but fail closed on Emscripten, where that native filesystem
  product surface is unsupported; otherwise one omitted symbol would prevent
  every supported in-memory kernel from loading. PEP 783 platform tags are accepted by
  PyPI, so the runtime-verified wheel joins the same trusted-publishing batch
  as the native wheels and sdist when publishing that target. The verified
  2026-10-14 registry snapshot has no Emscripten wheel; Pyodide 314 users must
  install a compatible built wheel by its exact URL, not by package name.
  Pull requests build and execute the exact
  wheel in the non-publishing Direct WASM job. The wasm job is release-blocking
  so an ABI or
  toolchain drift cannot silently ship a build-only, unloadable artifact.
- Confirm the no-Rust install job passed (it must build, install, and then
  raise a clear ImportError on first compute — never a silent fallback).
- Confirm the sdist verifier passed and the build-input-only source archive
  contains `xyg`, the render-client bundles, complete
  JS/Rust build sources, and the expected `PKG-INFO` package name, Python floor,
  runtime dependencies, with no Reflex extra or dependency. It must exclude repository-only
  docs, tests, scripts, benchmarks, examples, native binaries, and generated
  caches.
- Confirm each platform wheel passes `scripts/verify_wheel.py --expect-native`
  and its install smoke loads `xyg.kernels.BACKEND == "native"`. Confirm the
  fallback `py3-none-any` wheel passes `--expect-pure` and fails compute with
  the documented native-core error. Wheel
  `METADATA` must keep `Name: xyg`, `Requires-Python: >=3.11`,
  `anywidget>=0.9`, and `numpy>=1.24` as base requirements. Reflex extra/dependency
  metadata, `reflex_xy` and `XYChart.jsx` must be absent. `RECORD` must list every
  archive file exactly once with matching `sha256` and size fields. Wheels
  and the sdist remain distribution/build-input-only: docs, tests, benchmarks,
  scripts, and the `examples/` apps are repository-only.
- Confirm the wheel size budget is still below 15 MB.
- Confirm `spec/api/api-examples.md` runs against the tagged API.
### Promote accepted artifacts without rebuilding

The accepted commit, selected unused XYG tag, compatible Core candidate,
complete issue #108/#54 acceptance, and original artifact digests are release
preconditions. A historical successful build or a draft Linux-only cohort does
not satisfy them. For the final accepted source, build each target once and
reuse its archive in every consumer lane and public upload:

1. Keep both registry opt-ins disabled before creating the final tag. A tag
   push, or a tagged dispatch with `dry_run=false`, then builds and checks the
   complete versioned cohort without uploading. A run with `dry_run=true`
   remains permanently a rehearsal because reruns preserve its original inputs.
2. Retain the original run ID, full commit, tag, complete artifact inventory,
   SHA-256 ledger, and actual acceptance results. Download that run's archives
   for any additional acceptance lanes. Confirm the producer jobs completed
   once and that all archives remain available and unexpired; archive retention
   and GitHub's 30-day rerun window bound this promotion path.
3. After all acceptance, access, bootstrap, and compatibility requirements pass,
   enable both registry opt-ins. Obtain the original **Publish to PyPI** job ID
   with `gh run view RUN_ID --json jobs --jq '.jobs[] | {name, databaseId}'`.
   Request only that job's rerun with
   `gh api --method POST repos/CurateLabs/xyg/actions/jobs/JOB_ID/rerun`.
   GitHub reruns the selected job and its downstream npm/GitHub Release jobs;
   it preserves the original SHA/ref and downloads the existing producer
   artifacts. Inspect the new attempt and verify no producer was rerun and
   every downloaded archive matches the retained ledger before crediting the
   promotion as evidence. Repository opt-ins are an operational access gate;
   they do not establish npm authentication or make cross-registry uploads
   atomic.
4. Verify fresh public installs and the PyPI/npm registry archive digests
   against that exact retained ledger. Record all registry versions, evidence,
   and any partial-upload recovery. PyPI's `skip-existing` upload option alone
   does not compare existing file hashes; the public SHA-256 readback is required
   even after a successful retry. GitHub Release creation intentionally does
   not overwrite or promote an existing draft: inspect any existing release's
   exact tag, commit, visibility, and asset hashes before recovery. A retained
   integration draft is not authority to publish materially changed code under
   that candidate; choose the next unused candidate instead. A fresh dispatch
   or full-run rerun rebuilds archives and cannot promote already accepted bytes. If the originals have
   expired, preserve the acceptance gap and select a new unused candidate
   rather than silently rebuilding an accepted RC.

The [GitHub rerun contract](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)
preserves source identity; the [job-rerun endpoint](https://docs.github.com/en/rest/actions/workflow-runs#re-run-a-job-from-a-workflow-run)
limits the rerun to the chosen job and its dependents. No CI protection or
required approval policy needs to change for this process.

### Application consumers

Release artifacts exclude the removed Reflex adapter, JSX assets and dependency
extra. Repository consumers use Python/Streamlit and Node/vanilla TypeScript.
The consumer gate runs `scripts/consumer_apps_smoke.py --chromium PATH`;
Streamlit AppTest coverage lives in `tests/test_streamlit_consumer.py`. Stock
Streamlit HTML is a snapshot without a Python callback or incremental streaming
bridge. Shared selection/streaming and lifecycle gates remain required; see
[application-consumers.md](../design/application-consumers.md).

## Hardening Backlog

Keep pushing these in low-conflict increments:

- Add mutation-safety tests for every public builder: a failed call must leave
  the chart's internal figure and column store unchanged.
- Keep weird-string export tests covering every text surface added to the
  public API, including titles, labels, legends, categories, and series names.
- Styling arguments (colors, gradient stops, `style=` declarations) are gated
  by the native CSS grammar (`crates/xyg-engine/src/css.rs`; `tests/test_css_validation.py`) —
  route any new mark/chrome styling prop through `_validate.css_color` or
  `style_mapping` so no styling surface bypasses it.
- Keep benchmark environment metadata and category IDs on every new generated report.
- The release workflow's `workflow_dispatch` `dry_run` input (default `true`)
  now builds and verifies every wheel/sdist/wasm artifact without publishing;
  remaining follow-up is wiring an actual TestPyPI upload into that dry-run
  path (today it only stops short of a real publish, it doesn't yet push to a
  test index), plus tying it to version-bump/tag validation and refreshed
  benchmark reports.
- Keep application examples focused: `examples/streamlit` consumes public Python
  HTML/native export, `examples/vanilla-ts` consumes native Node/browser payloads,
  and `examples/fastapi` retains the framework-neutral live gallery. They must
  declare their distinct callback/streaming boundaries and dispose old views.

- Add first-class docs for the supported-platform matrix and the clear-error
  behavior when the native core is unavailable.
- Move advisory type checking to a hard gate once the checker and codebase agree
  on the dynamic `ctypes` and callback surfaces.


### Core result compatibility declaration (#936)

`python/xyg/graphforge-compatibility.json` is the release authority for the
exact Core versions qualified by the pinned real Core schema/descriptor and
IPC corpora. Packaging carries it in the wheel/sdist, Node facade, and
browser package. `verify_release_cohort.py` requires byte-identical copies
and records their SHA-256 plus the declared exact versions. A missing or
different declaration fails qualification. The current evidence qualifies
exact Core 0.5.2 and 0.6.0-rc.5 from real corpus evidence; this does not qualify
the planned installable 0.6.0 artifact pair. #108 must add
complete candidate evidence before claiming that pair. No editor/Hub
handshake is introduced, and native/Scene/WASM compatibility identifiers
keep their separate contracts.
