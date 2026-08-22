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
- Published wheels include only the shippable `xyg/` and bundled `reflex_xy/`
  packages,
  `.dist-info`, the render-client JavaScript bundles, `py.typed`, and, for native
  wheels, the Rust core. The JS bundles are a generated artifact (not committed to
  git): the build hook builds them into the wheel/sdist, so **end users do not need
  Rust, Node, npm, or a CDN.**
- Source distributions contain only install and build inputs: the `xyg` package,
  bundled `reflex_xy` integration, Rust/JS sources, and the prebuilt render
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

The composition API, chart-type set, visual styling surface, and Reflex
integration are still experimental and may change before a 1.0 release.

## Fork CI posture

CurateLabs/xyg is a permanently divergent product repository, not a deployment
branch of `reflex-dev/xy`. CI therefore retains only workflows whose external
integrations are owned or explicitly controlled by CurateLabs:

- Every Actions job except the CodSpeed performance job runs on a pinned
  Blacksmith Linux, ARM, Windows, or macOS runner; the canonical Linux CI image is
  `blacksmith-4vcpu-ubuntu-2404`, and no workflow may use a GitHub-hosted
  runner alias. `ci.yml`,
  `docs.yml`, `binder.yml`, and `bazel.yml` are hard verification paths.
  Binder builds locally with repo2docker; Bazel keeps uv's cache inside the
  writable workspace.
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
only WebKit's additional runtime libraries in a separate ten-minute-bounded
step. Real browser launches remain the dependency proof.

The inherited reflex.dev deployment workflows were removed. They built images
for upstream AWS, Harbor, and Azure registries, changed
`reflex-dev/helm-charts`, and polled the upstream `xy` PyPI project; they could
only fail or mutate infrastructure outside this repository. XYG documentation
deployment must be introduced as a new CurateLabs-owned contract rather than
reenabling those workflows.

## Accessibility and Cross-Browser Conformance Status

The current conformance tier covers a parallel semantic chart region and
generated trace/axis summary, a polite live region for hover and keyboard
readouts, focusable direct-point navigation with Arrow/Home/End keys, named
toolbar controls with toggle state, visible focus styling, reduced-motion
behavior, and forced-colors affordances.

The public documentation keeps code-copy controls visually icon-only while
providing stable accessible names and polite copied/failed announcements. Its
production-DOM check rejects both unnamed controls and shared-theme generated
text that would replace the copy/check icon feedback.

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
| Dashboard reliability | Attempts 10/20/50/60 charts, hard-gates the 10-chart row as loss-free and nonblank, retains partial larger rows, and applies the production shader-cache oracle to a complete, fully nonblank, loss-free 60-chart row | `python benchmarks/bench_dashboard.py --chart-counts 10,20,50,60 --chromium <chromium> --json dashboard-smoke.json` then `python scripts/verify_benchmark_report.py dashboard-smoke.json --kind dashboard-browser` |
| sdist | Build-input-only source archive contains the `xyg` and bundled `reflex_xy` packages, JSX/render-client bundles, complete JS/Rust build sources, and `PKG-INFO` version/dependencies (including `Provides-Extra: reflex` and `reflex>=0.9.6` under that marker) matching the archive's own `xyg-<version>` root; repository-only material, duplicate/unsafe members, native binaries, and generated junk are absent | `python scripts/verify_sdist.py dist/*.tar.gz` |
| Native wheel | Platform wheel contains package-only `xyg` and `reflex_xy` files, exactly one native library, the JSX wrapper but no duplicate render client, `METADATA` version/base dependencies/`reflex` extra matching the wheel's own filename and `.dist-info`, complete hash-checked `RECORD`, public export-surface markers, matching filename/`WHEEL` tags, and is tagged non-pure | `python scripts/verify_wheel.py dist/*.whl --expect-native` |
| Fallback wheel | No-toolchain wheel contains package-only `xyg` and `reflex_xy` files, `METADATA` version/base dependencies/`reflex` extra matching the wheel's own filename and `.dist-info`, complete hash-checked `RECORD`, public export-surface markers, matching filename/`WHEEL` tags, is pure, and contains no native library | `python scripts/verify_wheel.py dist/*.whl --expect-pure` |
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
| API prose, examples, public benchmark wording | `make check-docs` |
| `spec/api/api-examples.md`, Reflex chart registry/assets | `make check-examples` |
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

Use this after editing API docs, example snippets, or public benchmark wording:

```bash
make check-docs
```

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
occupancy, and it screenshots static Reflex-style chrome shells for the custom
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

Use this after editing `spec/api/api-examples.md` or the Reflex dashboard chart
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

The lifecycle gate runs `scripts/reflex_lifecycle_smoke.py`. It boots the
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

Pre-releases are tagged the same way with a canonical PEP 440 suffix —
`xyg-vX.Y.ZaN` / `bN` / `rcN` (e.g. `xyg-v1.0.0rc1`) — and publish through the same
pipeline; pip ignores them unless a pre-release is requested explicitly. Only
the canonical spelling passes the release gate: `-alpha1`-style tags would be
normalized by the version derivation and could never match their own built
artifacts. Release segments and pre-release counters also reject leading zeros
because those spellings normalize to different built versions. A pre-release
needs its own dated changelog entry, exactly like a final release.

The repository has one release line: the `xyg` distribution, including its
bundled `reflex_xy` integration, ships from `xyg-vX.Y.Z` tags through
`publish.yaml`. The `xyg[reflex]` extra is dependency metadata in those same
artifacts, not another package or release. The Python package and distribution
share the canonical `xyg` identity; no `xy` compatibility import ships.

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
  `XYG_ALLOW_PYPI_PUBLISH` repository variable to equal `'true'`. The variable
  does not exist by default, so a version tag builds and verifies artifacts
  but does not upload until that opt-in is set. The first successful upload
  claims the pending PyPI project `xyg`.
- **Tagged dispatch only.** A non-dry-run `workflow_dispatch` must target an
  existing `refs/tags/xyg-v*` ref and runs the same tag/CHANGELOG gate as a tag
  push. Dispatching `main` can exercise the complete dry-run matrix, but can
  never publish even when the repository opt-in is enabled.
- **GitHub Release after PyPI.** Once the PyPI job succeeds, `github-release`
  creates the matching GitHub Release with generated notes and attaches the
  runtime-verified PyEmscripten wheel. It has `contents: write`; build and PyPI
  jobs remain read-only except for the OIDC token. There is currently no
  production-documentation deployment workflow: the inherited reflex.dev
  promotion path was removed because CurateLabs does not own its registries or
  Helm destination. A future docs deployment needs a separate
  CurateLabs-owned destination and release contract.

`scripts/verify_ci_workflow.py` (`make check-ci`) pins these guards, and
`tests/test_verify_ci_workflow.py` covers their removal.

**Versioning decision.** The fork has its own `xyg-v*` tag line. Dunamai's
default `v` pattern is narrowed with `pattern-prefix = "xyg-"`; the release
workflow triggers on that prefix, and the release gate rejects bare `vX.Y.Z`.
Inherited upstream tags (`v0.0.1`–`v0.0.6a2`), docs CalVer tags, and
`reflex-xy-v0.0.1`/`v0.0.2` remain on `origin` as historical provenance, but
cannot determine an XYG version or trigger an XYG release. No destructive tag
pruning is required. The first production tag starts the fork line at
`xyg-v0.1.0`; set `XYG_ALLOW_PYPI_PUBLISH=true` only when that release is ready
to claim the pending PyPI project.

npm registry publication of `@curatelabs/xyg` and the complete
`@curatelabs/xyg-node` set remains tracked by the packaging milestone. The
tracked Node manifests intentionally remain `"private": true`, version
`0.0.0`, and use local `file:` optionals so a source checkout cannot publish.
The release workflow uses `scripts/stage_node_packages.py` to create separate
publishable trees from the release tag: five exact-platform packages reuse the
byte-identical cdylibs already verified inside the Python wheels and require a
valid ELF64, Mach-O 64-bit, or PE architecture header, while the
facade pins every optional to the mapped npm semver and embeds the exact built
standalone paint client for offline `toHtml()` use. The PEP 440 tag suffixes
`aN`, `bN`, and `rcN` map deterministically to npm `alpha.N`, `beta.N`, and
`rc.N`; stable versions are identical.

Every run packs and dry-publishes all six Node tarballs. A real npm upload is
additionally gated by an `xyg-v*` ref, non-dry dispatch, repository identity,
the `npm` GitHub environment, and both `XYG_ALLOW_PYPI_PUBLISH=true` and
`XYG_ALLOW_NPM_PUBLISH=true`. The PyPI job (including the shared tag,
CHANGELOG, and package-name guards) succeeds before npm can publish.
Publication
uses npm trusted publishing on a GitHub-hosted runner (Node 24, npm >=11.5.1,
OIDC `id-token: write`) and publishes platform packages before the facade, so
the public facade never points at absent versioned optionals. Publication is
retry-safe: `scripts/publish_node_packages.py` skips an immutable version only
after both its registry SHA-1 and SHA-512 Subresource Integrity value match the
local tarball, rejects a mismatch in either digest, and resumes the native-first
sequence before publishing the facade. After each upload it polls briefly for
npm visibility and proves both registry digests before advancing to the next
native package or, last, the facade. A visibility timeout reports that the
release must be retried for verification; it never treats an accepted upload as
verified merely because the publish command returned successfully. Registry
inspection and upload subprocesses use a five-minute timeout so a
stalled npm endpoint fails promptly instead of holding a partial release until
the workflow-wide limit. This makes cross-registry recovery convergent even
though PyPI and npm cannot provide one atomic transaction. Configure this
exact `publish.yaml` workflow as the trusted publisher for all six npm
projects; first-time project creation/ownership remains a deliberate registry
bootstrap step. The GitHub Release waits for both PyPI and npm jobs.

The release-only `browser-package` job builds the direct `xyg-engine` WASM
adapter and the ESM, standalone, and static Worker bundles from the tagged
source, then stages an exact-version `@curatelabs/xyg` tarball. Its
`ASSET-MANIFEST.json` binds every shipped filename to SHA-256 and byte length
and records the wire protocol, WASM ABI, Scene, and painter versions. Staging
rejects extra files (including source maps), symlinked assets,
CDN/repository/fork-origin paths, runtime dependencies, npm lifecycle scripts
or executable bins, invalid WASM headers, and per-file or aggregate budget
overruns. The tarball is packed and dry-published on every release rehearsal,
blocks the PyPI release gate if it cannot be produced, and is attached to the
matching GitHub Release. Registry publication and clean browser-application
conformance remain the explicit completion work for issue 53.

Version-tag releases also assemble a Linux x64 cross-host cohort from the
exact manylinux wheel, Node facade and native package, and host-neutral browser
tarball produced by that workflow run. `scripts/verify_release_cohort.py`
requires the Python and npm versions to match the tag, proves that Python and
Node carry byte-identical Rust cores, proves that Python, Node, and browser
carry the same standalone painter, rechecks the browser asset manifest, and
emits a SHA-256 ledger bound to the full release commit. The release-only job
then installs those four archives in a new Python virtual environment and npm
project and resolves the direct-browser WASM locally. This is the first issue
54 cohort; the remaining platform, notebook/Reflex, VS Code local/remote,
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
no `xy` compatibility package; `reflex_xy` remains the separate integration
namespace. `tests/test_xyg_package_identity.py` locks this identity.

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
- Confirm the release workflow produced six npm tarballs, each platform
  package contains the native bytes extracted from its exact wheel, every
  manifest carries the tag-derived npm semver and CurateLabs repository
  identity, and the facade contains the byte-identical standalone paint client.
- Before the first npm release, create/claim all six scoped public projects,
  bind their trusted publisher to `CurateLabs/xyg` / `publish.yaml` /
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
  Scene, exercising Scene v11 SVG and raster-command lowering. Dependency and
  wheel provisioning precede that offline boundary; browser CSP is separately
  proven by the local-only direct-WASM smoke because CSP does not apply to the
  Node-hosted Pyodide runtime. Filesystem-backed XYGC/tile-store ABI entries
  remain present but fail closed on Emscripten, where that native filesystem
  product surface is unsupported; otherwise one omitted symbol would prevent
  every supported in-memory kernel from loading. PEP 783 platform tags are accepted by
  PyPI, so the runtime-verified wheel joins the same trusted-publishing batch
  as the native wheels and sdist; Pyodide 314 users can install it with
  `await micropip.install("xyg")`. The wasm job is release-blocking so an ABI or
  toolchain drift cannot silently ship a build-only, unloadable artifact.
- Confirm the no-Rust install job passed (it must build, install, and then
  raise a clear ImportError on first compute — never a silent fallback).
- Confirm the sdist verifier passed and the build-input-only source archive
  contains `xyg`, bundled `reflex_xy`, the JSX/render-client bundles, complete
  JS/Rust build sources, and the expected `PKG-INFO` package name, Python floor,
  runtime dependencies, and Reflex extra. It must exclude repository-only
  docs, tests, scripts, benchmarks, examples, native binaries, and generated
  caches.
- Confirm each platform wheel passes `scripts/verify_wheel.py --expect-native`
  and its install smoke loads `xyg.kernels.BACKEND == "native"`. Confirm the
  fallback `py3-none-any` wheel passes `--expect-pure` and fails compute with
  the documented native-core error. Wheel
  `METADATA` must keep `Name: xyg`, `Requires-Python: >=3.11`,
  `anywidget>=0.9`, and `numpy>=1.24` as base requirements, plus
  `Provides-Extra: reflex` and `reflex>=0.9.6` guarded by that extra. The wheel
  must contain `reflex_xy` and `XYChart.jsx`, and `RECORD` must list every
  archive file exactly once with matching `sha256` and size fields. Wheels
  and the sdist remain distribution/build-input-only: docs, tests, benchmarks,
  scripts, and the `examples/` apps are repository-only.
- Confirm the wheel size budget is still below 15 MB.
- Confirm `spec/api/api-examples.md` runs against the tagged API.
### Bundled Reflex integration

Every `xyg` release carries the `reflex_xy` Python package and JSX wrapper. The
wrapper links to the render client in the same installed distribution, so
client, kernel, and framework bridge share one version. Plain `xyg` must not
install Reflex; `xyg[reflex]` must install the declared supported floor.
Release smoke tests install Reflex, import `reflex_xy`, and assert that its
reported version matches the `xyg` distribution version.

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
- Keep the two example apps focused: `examples/reflex` on the bundled Reflex
  integration surfaces (figure vars, events, state-driven and streaming
  updates, `on_view_change`), and `examples/fastapi` on the framework-neutral
  gallery plus the live 100M drilldown. The one deliberate overlap is that
  drilldown chart itself: `examples/reflex` §6 serves the identical dataset
  adapter-natively (an `inline()` token, no transport code) so cross-host
  behavior can be A/B'd against fastapi's hand-rolled transport; both honor
  `XY_LIVE_POINTS`. Neither commits static chart HTML, and both surface their
  own source via `inspect.getsource`.
- Add first-class docs for the supported-platform matrix and the clear-error
  behavior when the native core is unavailable.
- Move advisory type checking to a hard gate once the checker and codebase agree
  on the dynamic `ctypes` and callback surfaces.
