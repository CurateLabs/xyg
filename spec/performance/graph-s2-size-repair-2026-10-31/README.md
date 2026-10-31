# Bounded GraphSession S2 size repair

This is a separate, append-only receipt after the historical
[S2 recovery](../graph-s2-recovery-2026-10-31/README.md). No historical S1/S2
receipt is rewritten. The isolated repair branch first normally merged
`5c3f51cd2091543bea22a37368466e742d052fdb` as the second parent of
`cea8fcf9c8e7daf8f5deabf5aa3c1553f288464e` (first parent
`1440bec94202129eea25751c3d51ee7cd1620130`). All producer source hashes match
the recovered S2 receipt at that merge. Parent review and accepted-main
integration are separate work; this receipt does not establish M4 completion.

The baseline was freshly built and measured with actual Node **22.23.4**,
Rust **1.96.0**, workspace release O3/fat LTO/codegen1/strip, the existing
WASM inline threshold 100 and pinned Binaryen **132.0.0** `-O3 --all-features`.
Node's default `gzipSync` measures gzip level 6. Compiler profiles,
dependencies, optimizer, exports, ABI/Scene/painter versions and package gates
remain unchanged at **1,547,264 raw / 640,000 gzip bytes** (1,511 / 625 KiB).
The new baseline reproduces **1,547,915 / 640,615** and optimized SHA-256
`544d97c615a96e31cdca66cac0d577b954ee337e50e2e589690dc348d7c852bc` exactly;
the unmodified real packager rejects it at the gzip gate.

## Two-candidate limit

1. **Forest scratch allocation:** `validate_parent_forest` replaces its scratch
   chain vector with a second walk over the current chain's mark states.
   The first walk, self-parent/cycle checks and start order are unchanged.
   Every successful node changes `0 -> 1 -> 2` once; each walk follows a node's
   parent at most once, so the total stays O(n) with at most 2n parent-link
   visits. Shape/range admission remains at the same callers. The separate S1
   nearest-visible-ancestor implementation and its <=2n proof are untouched.
   An independent, deliberately nonmemoized oracle checks all **126,126**
   parent planes through six nodes, including exact first-error kind and cycle
   entry. These tests pass against the original and replacement validators;
   100,000-node deep-chain and shared-ancestor fixtures also pass in both.
   Measurement: **1,547,779 raw / 640,527 gzip**, saving **136 / 88** bytes,
   still exceeding the gates by **515 / 527** bytes.
2. **Shared compound flags:** measure `#[inline(never)]` on the existing
   `collapsed_node_flags` helper atop candidate 1. No flag validation or
   propagation expression changes. Authored flags stay 127; session emphasis,
   temporal atomicity, revisions, aggregate admission, relayout and #1078
   worker behavior retain their contracts. Measurement: **1,547,779 raw /
   640,527 gzip**, exactly the same sizes as candidate 1 (with a different
   artifact hash). **Rejected and reverted** because it saves no bytes. No
   third candidate was attempted. Candidate 1 is retained.

This task makes no runtime-performance, competitor, startup, UI, massive-source,
or release-readiness claim. It does not add a public API, export, feature,
validation bypass, dependency, or functionality budget. No hardware/paid
benchmark, registry installation, remote mutation, push or PR action is used.
The offline Node-host dependency setup uses the existing local npm cache.

## Reproduction

Use the pinned Rust toolchain and an actual Node 22 installation:

```bash
mkdir -p target/task-tmp
export TMPDIR="$PWD/target/task-tmp"
export PATH="/path/to/node22/bin:$HOME/.cargo/bin:$PATH"
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
cargo test -p xyg-engine --lib projection::
cargo test -p xyg-engine --lib graphforge::
cargo test -p xyg-engine --lib graph_style::
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node spec/performance/graph-s2-recovery-2026-10-31/measure.mjs target/task-tmp/s2-size-repair/reproduced
node js/build.mjs
node js/package-wasm.mjs
```

`results.json` records the exact commands, exits, source/artifact hashes and
candidate dispositions. Raw output is losslessly retained as `*.txt.gz`.
Candidate patches and complete producer source manifests allow each measured
state to be reconstructed from the normal merge. Optimized modules remain
ignored build outputs. The prior recovery's measurement script is used
unchanged; it is a measurement tool and cannot waive packaging gates.

## Final result: package FAIL

Only candidate 1 is retained. The final module remains **515 raw / 527 gzip6
bytes over the unchanged gates**. There is no successful packaged S2 asset set
or packaged foundation acceptance. A separate explicit functionality-budget
decision remains the parent's responsibility; no user clarification blocks
this bounded repair. Final independent review must include the new validator
and tests in addition to the recovered S2 diff.

The final functional checks pass: **1,878 Rust workspace tests**, **134 Python
tests** (four browser tests deselected), **136 native Node tests** with no
skips, workspace/all-target Clippy with `-D warnings`, edited-file rustfmt,
Python type checking, ownership, ABI generator/parity and **673 ABI smoke
checks**, unchanged cross-host and semantic goldens, and the actual Chromium
render/append smokes. The full Rust suite was rerun after reverting candidate 2.
The Clippy log retains its queued `candidate2-clippy` label, but its command
started after the attribute was reverted and checks the final retained source.
The native core and client bundles were rebuilt. The baseline Python/Node
consumer tests used the original S2 native release core; the final consumer
tests used the rebuilt retained core. No full multi-hour Python run or broad
Node geometry/geo cleanup was performed.

Diagnostic native/WASM parity and export checks, artifact hashes, the real
package failure, asset-verifier outcome and final hooks are recorded in
`results.json` and the raw logs. Diagnostic module copying for parity is
explicitly separate from packaging: it does not produce a manifest or inline
payload and cannot pass the paired-asset gate. Historical S1 broad Node
baseline failures remain unchanged evidence outside this repair's scope.

The final rebuild exactly reproduces candidate 1:

- Raw compiler output SHA-256:
  `cfa904e03bb11869e7a1439b1c603675f1ace9688fd43273b1092bb9a017f0e7`.
- Optimized module SHA-256:
  `27b922cb47294ebf8585a54be4d86d3fece91772a0bc7df432a34385fb26b678`.
- Engine diff from the normal merge SHA-256:
  `49cfaaa2cb0b676c069b675f451296d0db613aa4a39bffef5e614076a3e514ef`.

The real package command exits **1** at **640,527 gzip bytes > 640,000**;
independent measurement also confirms **1,547,779 raw > 1,547,264**. The paired
asset verifier exits **1** because no packaged WASM/inline/manifest set exists.
The packaged browser foundation is therefore not run or claimed. The separate
diagnostic module has zero ambient imports and exactly the manifest's **60
function exports** at WASM ABI **34** / Scene **34**. **33 native/WASM parity
tests pass**, with zero skips. The diagnostic dist copy is removed after those
tests; the measured optimized module stays under the ignored
`target/task-tmp/s2-size-repair/final/optimized.wasm` path for inspection.

Full-worktree pre-commit hooks and both required Ruff checks pass before each
local commit (merge and final repair). Their exact commands and lossless output
are retained here. The local commits use the human identity from main; there
is no remote repository mutation.
