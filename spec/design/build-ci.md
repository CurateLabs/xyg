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

The `Release surfaces` aggregate lists every hard job, including `wasm_assets`; see the
hard/advisory table in [production-readiness.md](../process/production-readiness.md).

Scale evidence retains its existing limits: smoke timings are advisory;
render-graph and pyramid budgets are enforced. 100M/1B LOD decision evidence
is not proof of allocating or rendering that many rows. The benchmark
implementations and thresholds are unchanged.

## Packaged WASM assets (#1005, dossier §33)

Main run 38640943006 failed `Benchmark methodology suites` with
`FileNotFoundError: packaged WASM tick assets missing: xyg-wasm.wasm`: the job built the
client but nothing in its dependency graph produced the generated WASM assets, and the
downstream `Merge and verify benchmark reports` job then failed on the absent
`workflows.json`. The assets are generated (never committed), so every consumer must obtain
them from the one producer.

| Step | Contract |
| --- | --- |
| Producer | CI job `wasm_assets` runs the fail-closed raw build and PNG-dependency check, `node js/build.mjs`, the packaging contract tests, `npm run build:wasm`, and `scripts/verify_wasm_assets.py`, then uploads `wasm-assets` (`if-no-files-found: error`). Locally: `node js/build.mjs && npm run build:wasm`. |
| Consumers | `test`, `wasm_foundation`, `python_floor`, `benchmark_methodology`, `wheels`, `sdist` list `wasm_assets` in `needs`, download `wasm-assets`, and verify before use. No consumer runs `npm run build:wasm`, `js/package-wasm.mjs`, or the wasm32 `cargo build` itself. |
| Verifier | `scripts/verify_wasm_assets.py` (stdlib only) checks presence in both locations, WebAssembly magic, `sha256`/`bytes` against `xyg-wasm.manifest.json`, ABI/Scene/painter versions against `spec/wasm/abi.json`, inline module hash, inline classic-worker freshness, and dist/static equality. One diagnostic names the files and the producer command. |
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
the producer, downloads, verifies; no second producer; weakened producer rejected).

## Local reproduction

```bash
uv sync --locked --extra reflex --group dev
cargo test --workspace
cargo build --release
npm ci
npm ci --prefix packages/xy-node
node js/build.mjs
npm run build:wasm
python3 scripts/verify_wasm_assets.py
make check-graph
make check-ci
node scripts/browser_client_smoke.mjs
```

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
