# Node #35 independent-review repair receipt

This append-only receipt repairs candidate
`a27ed2edb0d0c314bbf9bf86a6554f3cb86e7fbd`, whose canonical binary/full-index
diff against `dee3ea37540a7126c3082ae59624bb02881bb00f` has SHA-256
`8c7783d6a0e7370539a0a3d3e1e50b56b3196c86fbd8bb4e5142b3c68588b047`.
The original `graph-node-scheduling-35-2026-10-31/` receipt is unchanged.
This is focused Node correctness and bounded functional evidence, not M4,
#108, S5, scale, competitor, hardware or release qualification.

## Review findings and disposition

| Finding supplied by independent review | Repair and regression proof |
|---|---|
| P1: executable webview/release smokes still used the synchronous signature and `payload.figure` | Both now allocate an owner, await the live API, pick the live payload, and await disposal in `finally`. The packaged smoke checks root/subpath export identity and the default scheduled force path. No browser/native assertions were removed. `caller-audit.log` covers current source, tests, scripts, examples and benchmark references. The deliberate owner-rejection test is the only executable old-shape call. Historical benchmark data remains unchanged; its comment now names `graphforgeStaticPayload`. |
| P1: render node index incorrectly addressed a composed/source node | Live payloads carry render-indexed `pickData.nodes`, serializing Rust `member_of` / source IDs and existing compound membership. Static picks use the same membership authority. Canonical UUID joins recover composition provenance. Tests cover source 3 becoming render 0 in a culled EdgeSample viewport, collapsed group and hidden source remapping, Direct/EdgeSample/Aggregate, exact edge provenance including the disclosure subset, and out-of-render bounds. No source coordinates or numeric mapping planes were added to the paint wire. |
| P2: non-force Aggregate payloads lost source f64 positions | The bridge calls the existing native source layout once before preset packing. Circle/grid tests compare complete UUID-indexed f64 output bit-for-bit with the native layout, compare Direct/Aggregate, seed pinned CoSE from it, check explicit preset/reversed UUID coverage and native root semantics. A real-worker trap proves exactly one non-preset source layout then preset packing, with no force handle/ticks. |
| P2: synchronous startup cancellation could escape worker teardown | Recheck cancellation after signal registration and input extraction; hand recorded cancellation to a worker immediately after assignment. Real AbortSignal and input/structured-clone getters exercise abort and dispose. Tests require no worker creation before cancelled startup, and actual exits for every worker created during cloning before terminal settlement. Listener cleanup and terminal disposal are checked. |

Final independent review of the repaired diff belongs to the parent; the
candidate's earlier scoped review is not approval of this repair or the whole
API. Shared specifications and API inventory remain parent-owned; see
`HANDOFF.md`.

## Results

- `node-tests.log`: **132 pass, 0 fail, 0 skipped**, including 14 live-layout
  tests, the existing graph/composition/cross-host suites, force lifecycle and
  VS Code contracts. `abi-smoke.log`: **673 passed** against this worktree's
  locally built ABI 397 library.
- `a27-regression.log`: all **six** new regression tests fail against isolated
  a27 source files. The startup case is killed by its 8-second subprocess
  deadline; repaired cases settle normally. This is expected failure evidence.
- `result.json` / `run.log`: actual four-node CoSE step 1 and step 60 pixels,
  changed position digests, real pointer clicks and pan responses, no page
  errors or non-local requests, and canvas removal on disposal. Each real
  click must match the GPU-probed trace/index, and its host UUID must equal
  the actual `click.detail.row.id`.
- `wheel-build.log`, `clean-install.log`, `node-release-smoke.log`: local wheel,
  staged facade/native tarballs and an offline clean install pass the affected
  Linux x64 packaged smoke. `provenance.json` binds wheel, tarball, installed
  source and native hashes. This is one local platform pairing, not the full
  release cohort. `clean-install-initial-attempt.log` retains an initial
  scratch-directory setup failure; creating its own package manifest fixed
  the harness. Root dependency manifests were restored byte-for-byte and are
  outside the repair diff.
- `no-browser-globals.log`: **inherited failure**, generated FFI parameter
  `document` in `_abi_generated.js`. This file is byte-identical to a27 and
  dee3ea37. It is neither hand-edited nor waived. The parent's separate S4
  source/generator repair must be combined and tested independently.
- `wasm-build.log`: raw source build succeeds. `wasm-package-gate.log`:
  **FAIL**, optimized gzip **755,339 bytes > 641,024-byte budget**. No budget,
  build profile, dependency, export or gate changed. Since the gate produces
  no distribution WASM, `webview-smoke.log` records the actual shipping-path
  failure (`XYG_WASM_INIT_FAILED`, empty WASM response).
- `webview-raw-wasm-diagnostic.log`: **diagnostic PASS only** for both native
  and browser paths using an unchanged copy of the smoke, current local
  painter/Worker assets, and the raw locally compiled WASM in a separate
  temporary resource tree. It preserves nonce CSP, cross-origin local assets,
  Blob Worker, real clicks, exact UUID/result rows and request assertions.
  `csp-diagnostic.png` records that run. The raw module is never copied into
  product distribution directories. This result does **not** pass the failed
  package gate or qualify a shipping WASM artifact.
- Full repository hook and Ruff outcomes are recorded in `pre-commit.log`,
  `ruff-check.log` and `ruff-format.log` before the focused commit. An initial
  staged capture wrote into its own tracked log while hooks ran, so pre-commit
  correctly reported modified files (`pre-commit-capture-attempt.log`). Final
  capture goes to a temporary file first. Raw tool logs retain their emitted
  whitespace; any diff whitespace notices are confined to those logs.

## Retained objects and timing meaning

`initial-spec.json`, `initial-buffer.bin`, `final-spec.json` and
`final-buffer.bin` retain the actual initial/final painter payloads. Result
metadata binds their byte hashes, both screenshots, source files, executables,
client/native assets, source-position digests, exact picks and revision/job
identities. Full source coordinate arrays and intermediate render payloads
are **not** retained. `fixture.log` records the launched consumer URL.

The old immutable receipt's phrase “render payloads ... are retained” was
broader than its actual retention: final spec, byte counts, identities and
position digests. This receipt explicitly adds initial/final specs and binary
buffers; it does not rewrite that historical record.

Checkpoint delivery and actual first paint have different timestamps in
`result.json`; neither is substituted for the other. Consumer ACKs hold
frames during screenshot/click/pan inspection, so presentation intervals are
not scheduler cadence. Full ChartView replacement resets viewport; retained
updates remain S5. Software rendering, automation, cold starts, shared CPU
load and callbacks affect these observations. They are not thresholds or a
performance win. The earlier 1k/10k/100k/1M ladder remains scheduler-only.

## Reproduce in a fresh output directory

From the repository root, with root and Node-package dependencies installed:

```bash
export PATH=/home/ubuntu/.t3/worktrees/xyg/t3-1b0dd836/target/task-tmp/node-v22.23.4-linux-x64/bin:/home/ubuntu/.cargo/bin:$PATH
export TMPDIR="$PWD/target/task-tmp"
mkdir -p "$TMPDIR"
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
export XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome
cargo build --release --offline
node js/build.mjs
node --test packages/xy-node/test/graphforge-layout.test.mjs packages/xy-node/test/graphforge.test.mjs packages/xy-node/test/graphforge-cross-host.test.mjs packages/xy-node/test/graph.test.mjs packages/xy-node/test/composition.test.mjs packages/xy-node/test/force-worker-lifecycle.test.mjs packages/xy-node/test/vscode_contract.test.mjs
uv run python scripts/abi_smoke.py
node spec/performance/graph-node-scheduling-35-review-repair-2026-10-31/run.mjs
bash spec/performance/graph-node-scheduling-35-review-repair-2026-10-31/clean-install.sh
```

`run.mjs` chooses a fresh directory under `target/task-tmp` unless explicitly
overridden by `XYG_GRAPH_NODE_RECEIPT_OUTPUT`; it refuses an existing result.
The clean-install wrapper reproduces the recorded wheel/stage/pack/offline
install steps without changing repository manifests or accessing a registry.
Node 22.23.4 and Chromium 156.0.8078.4 were used; full paths, hashes, OS and
toolchain details are recorded in `result.json` and `provenance.json`.

These commands intentionally expose the inherited failures separately:

```bash
node spec/performance/graph-node-scheduling-35-review-repair-2026-10-31/baseline.mjs # expected exit 1
node --test packages/xy-node/test/no_browser_globals.test.mjs                   # inherited exit 1
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown --offline
node js/package-wasm.mjs                                                    # package gate fails
node scripts/graphforge_webview_smoke.mjs                                    # no qualified WASM asset
node spec/performance/graph-node-scheduling-35-review-repair-2026-10-31/csp-diagnostic.mjs # diagnostic only
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```
