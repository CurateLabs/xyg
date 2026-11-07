# Linked filtering, graph admission and native lifecycle integration

This normal merge preserves reviewed linked filtering parent `81c4ba55bb23a858b8f3dd8dd4ecbbf4e97377e5` and reviewed graph/native lifecycle parent `0a85b8da98ceb5dd0f2ef308f51c85a46f22460e`. The latter includes accepted main `43c35f67b95ae4e78e3e96f200a0e6be8642199c`; its newer graph and startup-cancellation changes remain dependent delivery work.

Both parent reviews approved their bounded scopes. This combined diff needs its own independent integration review and fresh hosted CI before delivery. There is no issue or milestone closure claim.

Six metadata conflicts preserve both attribute pin sets, the unique Node test union, the ownership ledger union, regenerated preparation inventory and a successor Core binding pointer. Automatic runtime merges add native geographic composition methods and state subscription exports alongside filtering methods. Historical performance and release evidence remains immutable.

Fresh native/WASM builds are required because graph admission sources differ from the filtering producer. Native ABI 402 and WASM 36 must be checked against the actual generated declarations; ABI numbers alone do not establish artifact compatibility. All gates retain their existing caps, tolerances and deadlines.

The source protection, commands, archived logs and artifact hashes accompany this receipt after qualification. Original failures and incomplete commands receive no pass credit. Prior heavy parent proofs are inherited only after exact source/artifact identity checks.

## Remaining acceptance

Filtering still lacks 100M/five-view performance qualification, paged/spilled sources, cooperative Worker interruption, full native widget transport and broader compatibility. Graph admission remains bounded to explicit 384 MiB per Worker and a 10k primary plus 1k peer; default-arena 1k, reliable two-10k completion and larger ladders remain unqualified. Native geographic bindings expose snapshots; mounted replacement, mixed tiles and indexed/hierarchy automatic bindings remain separate work. Exports, accessibility, global memory, competitor and whole-milestone requirements remain open.

## Fresh qualification

Fresh release native, wasm32 and shared-client builds passed. The explicit native
library is `347ca67b5eb09aed8b8f6d6578f1f21913c195ab197ce70a68ba6a2e1dac35f6`;
the optimized WASM is `b262993164c6b55c5c8571b209df423e1d554708440d8629e2db5a5cd3a18680`.
Node 22.23.4 measures **1,911,775 raw / 782,244 gzip6 bytes**, within the unchanged
1,927,168 / 786,432-byte caps. Official native and WASM declarations are current.

Fresh checks passed: seven engine filtering tests, 153 graph interaction tests,
one allocation regression, 76 WASM-host tests, 142 Python host tests, and the
complete 67-file Node command: **1,105 passed, two existing skips**. The Python
batch includes all four required decoded-image/oracle comparisons. All 673 ABI
checks, strict engine Clippy, workflow, Python floor, capability and packaged
asset checks passed. Core/inventory/ownership qualification passed 42 tests,
including actual Git LF/CRLF conversion; final binding checks are logged separately.

The real five-view Chromium filtering journey passed 102 oracle groups, 400
exact texture texels and 19 canvas-coordinate probes. Pointer and keyboard
produced the same fingerprint and pixels; indexed serving read zero canonical
rows. The full strict-CSP foundation passed, including 16 camera units, the
existing scheduling journey and all 14 retained temporal cases.

The first additional 10k browser run converged both views at step 458 without
reported graph errors, then **failed** at replay collection with `missing reply`.
Its exit-1 log is preserved. A diagnostic copy changed only that thrown error's
text to include the missing command metadata; all assertions and execution were
unchanged. That run passed with 60/59 painted publications, trusted unfinished
pick, host-button camera continuity, reverse Worker arrival, isolation and
cleanup. Complete replay compared all 63 primary and 60 peer replies against
native and actual WASM, retaining every one of the primary's 10,000 nodes and
edges. The original capture failure's cause was **not reproduced or repaired**;
the successful diagnostic repeat establishes bounded functionality, not reliable
completion, contention tolerance, latency or an explanation of that failure.
The exact diagnostic source is archived beside both logs and its source delta
is recorded in `checks.json`. Shipping source and the original harness remain
reviewed-parent-exact.

`parent-protection.json.gz` records 16,160 protected parent paths and nine
explicit combined paths. The user/environment-owned working `AGENTS.md`
symlink overlay remains untouched; its Git index identity is protected. All
189 top-level Python composition definitions retain an exact parent AST. All
526 ownership entries and 693 preparation-inventory gaps equal their parent
unions. These metadata counts are not acceptance qualifications.

Reproduce with Rust 1.96, Node 22.23.4, a short disk `TMPDIR=/var/tmp`, the
source-matching native library explicitly selected through `XYG_NATIVE_LIB`,
and `XYG_CHROMIUM`/`XYG_TEST_CHROMIUM` pointing to installed Chromium:

```bash
cargo build --release
npm run build:wasm
node js/build.mjs
cargo test -p xyg-engine filter_tier_c
cargo test -p xyg-engine graphforge::interaction
cargo test -p xyg-engine --test graph_session_memory
cargo test -p xyg-wasm --lib
uv run pytest -q tests/test_filter_tier_c.py tests/test_filter_tier_c_density.py tests/test_geo_temporal_binding.py tests/test_temporal_controller.py tests/test_graph_session_python_transport.py tests/test_chunked_columns.py
npm test --prefix packages/xy-node
python3 scripts/abi_smoke.py
node scripts/filter_tier_c_conformance.mjs --chromium "$XYG_CHROMIUM"
node scripts/wasm_foundation_smoke.mjs
XYG_GRAPH_SESSION_REPORT=/var/tmp/public10k.json node scripts/graph_session_public10k_smoke.mjs
node scripts/graph_session_public10k_replay.mjs /var/tmp/public10k.json
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

No current-head hosted CI, independent combined-diff approval or queue acceptance
is implied by this local receipt. Prior product approvals are inherited only
for source-identical material; original broad timing and scale results are not
relabeled as fresh measurements.

The repository naming scan also passed its complete module. An initial command
named nonexistent `tests/test_naming.py` and collected no tests (exit 4); that
setup error is preserved and receives no pass credit. The corrected command
uses `tests/test_stale_names.py`. Full-worktree hooks and both Ruff checks passed.
