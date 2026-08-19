# Bazel + Blacksmith CI (graph dual-host)

The graphforge-xy dual-host graph MVP is gated by **Bazel + Blacksmith**,
not by converting every existing GitHub Actions workflow.

## Scope

`.github/workflows/bazel.yml` builds and tests:

| Target | Role |
| --- | --- |
| `//:xyg_core` | `cargo build --release` → `libxyg_core.so` |
| `//:rust_test` | `cargo test --workspace` |
| `//:abi_smoke` | `scripts/abi_smoke.py` with `XYG_NATIVE_LIB` |
| `//:python_graph_test` | pytest `tests/test_graph.py` (+ sankey when present) |
| `//:node_graph_test` | `packages/xy-node` tests against the same `.so` |
| `//:perf_parity_test` | dual-host graph + kernel soft ceilings (small N) |
| `//:scale_all_charts_test` | `benchmarks/bench_scale_all_charts.py --profile smoke` |
| `//:graph_mvp_tests` | suite of the graph dual-host test targets above |

Cargo.toml / Cargo.lock remain authoritative. Root Bazel targets wrap
cargo / pytest / npm so crates.io does not need to be reachable through
Bazel's fetch graph.

## Browser client smoke (not Bazel-gated)

The shared WebGL client is exercised outside the Bazel suite:

```bash
npm ci && node js/build.mjs          # regenerate @curatelabs/xyg (packages/xy-client/dist) and copy into python/xy/static
npm ci --prefix packages/xy-node     # koffi / Node host deps (root npm ci does not install them)
node scripts/browser_client_smoke.mjs
```

`browser_client_smoke` asserts `MARK_KINDS` / `render` exports (Playwright when
Chromium is available, otherwise `node --check` + ESM import). Documented here
so dual-host CI stays Bazel's cargo/pytest/npm graph path while the paint
client retains an explicit smoke entry point.

## Runners

All jobs use Blacksmith tags only (for example
`blacksmith-4vcpu-ubuntu-2404`). Never `ubuntu-latest` or other
GitHub-hosted runners. Bazel setup uses `useblacksmith/setup-bazel@v2`
(sticky disks for bazelisk / disk / repository caches). The Bazel
version pin is `.bazelversion` (currently `7.4.1`) — `setup-bazel@v2`
has no `version` input; bazelisk reads `.bazelversion`. The job sets
`UV_CACHE_DIR` to `${{ github.workspace }}/.cache/uv` because those sticky
disks own `~/.cache` and uv cannot create `~/.cache/uv` there. A job-level
environment expression cannot use the `runner` context: GitHub evaluates that
mapping before a runner exists. The workspace context is available at that
stage and gives uv a writable, run-scoped location. `XDG_CACHE_HOME` is set to
that same workspace cache root so Bazel derives its output user root as
`.cache/bazel` instead of the unwritable `~/.cache/bazel` mount.

Rust is pinned to **1.88.0** in the workflow (`dtolnay/rust-toolchain`)
and `rust-toolchain.toml`. Node graph goldens default to the current
`ABI_VERSION` in `python/xy/_abi_generated.py` (60 as of this revision);
`tools/bazel/run_node_graph_tests.sh` exports `XYG_EXPECTED_ABI` from
`python/xy/_abi_generated.py` when unset. If that generated constant is absent
or cannot be parsed, the wrapper falls back to the authoritative Rust constant
instead of exporting an empty expected version.

## Local

```bash
./bazel build //:xyg_core
./bazel test //:graph_mvp_tests
# or individually:
./bazel test //:rust_test //:abi_smoke //:python_graph_test //:node_graph_test
./bazel test //:scale_all_charts_test
node scripts/browser_client_smoke.mjs   # after js/build.mjs
```

`./bazel` prefers a committed `tools/bazelisk` when present, otherwise
`bazelisk` / `bazel` on `PATH`. Pin the version with `.bazelversion` or
`USE_BAZEL_VERSION` (bazelisk). On Blacksmith CI,
`useblacksmith/setup-bazel@v2` installs Bazel and the wrapper uses it.
