# Bazel + Blacksmith CI (graph dual-host)

The graphforge-xy dual-host graph MVP is gated by **Bazel + Blacksmith**,
not by converting every existing GitHub Actions workflow.

## Scope

`.github/workflows/bazel.yml` builds and tests:

| Target | Role |
| --- | --- |
| `//:xy_core` | `cargo build --release` → `libxy_core.so` |
| `//:rust_test` | `cargo test` |
| `//:abi_smoke` | `scripts/abi_smoke.py` with `XY_NATIVE_LIB` |
| `//:python_graph_test` | pytest `tests/test_graph.py` (+ sankey when present) |
| `//:node_graph_test` | `packages/xy-node` tests against the same `.so` |

Cargo.toml / Cargo.lock remain authoritative. Root Bazel targets wrap
cargo / pytest / npm so crates.io does not need to be reachable through
Bazel's fetch graph.

## Runners

All jobs use Blacksmith tags (for example
`blacksmith-4vcpu-ubuntu-2404`). Bazel setup uses
`useblacksmith/setup-bazel@v2` so repository and disk caches ride sticky
disks. Do not add `ubuntu-latest` (or other non-Blacksmith) runners to
this workflow.

## Local

```bash
./bazel build //:xy_core
./bazel test //:graph_mvp_tests
# or individually:
./bazel test //:rust_test //:abi_smoke //:python_graph_test //:node_graph_test
```

`./bazel` prefers a committed `tools/bazelisk` when present, otherwise
`bazelisk` / `bazel` on `PATH`. Pin the version with `.bazelversion` or
`USE_BAZEL_VERSION` (bazelisk). On Blacksmith CI,
`useblacksmith/setup-bazel@v2` installs Bazel and the wrapper uses it.
