# PR1107 accepted-main integration

Normal merge of reviewed f6d309675943ce30d3c58e8ca64ea1f36bbf9a87 with
accepted main885330e228b6ada9bff54ef1b903e5da2f79b45c after parentPR1102
merged. The only conflict was the added publication-test file: incoming main
bytes equal independently reviewed ec58124f, and the complete approved test
file starts with those exact bytes before its additional coordinator regressions.
The conflict retains the complete reviewed superset. All five owned runtime/
test/spec paths are f6d-exact; all243 Rust/Cargo/toolchain inputs equal main.
The protection manifest binds those assertions and exact source bytes.

The public retry/coordinator code is unchanged from the approved final scope:
validation precedes supersession, latest failed revisions can retry, individual
attempt identity suppresses stale replies/callbacks, and both frame/layout
entry points capture revision once. No ABI, policy, cap, tolerance, dependency
or release gate relaxation. Historical retry/layout receipts remain unchanged.

Fresh combined native/WASM builds, client build/typecheck, actual-WASM Node
regressions, native Python tests and strict-CSP actual-Worker foundation pass.
Results:13 engine temporal tests,7 WASM-host tests,17 Node tests,20 Python tests,
package asset and API preparation inventory verification. The inventory's
13 generation-time source-hash differences are disclosed body/provenance drift,
not a new exact-byte freeze. All mandatory full-worktree hooks/Ruff run before
this merge commit and the subsequent push. Exact artifacts and unchanged
1882KiB raw/768KiB Node22 gzip6 limits are recorded in checks.json.

Reproduce with Rust1.96,Node22 and explicit freshly combined native:

```sh
cargo build --release -p xyg-core
cargo build --release --target wasm32-unknown-unknown -p xyg-wasm
node js/package-wasm.mjs
node js/build.mjs
cargo test -p xyg-engine temporal_graph --lib
cargo test -p xyg-wasm temporal_graph --lib
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" node --test packages/xy-node/test/temporal-graph-publication.test.mjs packages/xy-node/test/temporal-graph.test.mjs packages/xy-node/test/chunked-columns.test.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so" uv run pytest tests/test_temporal_graph_native.py tests/test_chunked_columns.py tests/test_graphforge_contract_corpus.py -q
XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome node scripts/wasm_foundation_smoke.mjs
uv run python scripts/verify_wasm_assets.py
uv run python scripts/check_release_inventory.py
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
```

Independent final integration review, current-head CI and merge queue remain
required. Full#45/M5 controller/composition,aggregateLOD,frozenexport/history,
scale/accessibility and #108 release acceptance remain open.
