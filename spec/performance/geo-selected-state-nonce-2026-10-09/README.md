# Selected-State allocation recovery evidence

This records bounded ownership functionality. It does not measure startup,
interaction latency, GPU paint, competitors or massive-scale performance, and
it does not close #50/#39. Live adapter integration is a dependent slice.

The exact fresh native and optimized wasm32 artifacts are pinned in
`environment.json`, alongside tested interpreter/tool versions and source
hashes. The existing O3/profile, ABI signatures, artifact budgets and engine
quotas are unchanged. `package.txt` records successful packaging under the
existing gate; compression level6 is the package gate and level9 is separately
labelled. The measured artifact is1,459,498 raw bytes /599,989 gzip-level6 bytes.

`node.txt` contains47 actual native/WASM tests:23 new allocation controls and24
legacy selected-hierarchy controls. They execute real Rust allocation, State
consumption43, same-handle Data publication44, Rows and cleanup. Controls cover
lost/corrupt33, recovery before any dispatch, failed recovery and cleanup,
lost successful10 resolved by retired20, exact same handle, cancellation/trap
status after allocation, definite allocation-free16-handle rejection, five
separate Scopes and repeated shared-Scope nonces, and two actual WASM modules
with colliding numeric handles and different Point/MultiPoint sources. A delayed
response with an edited Scope producer keeps the captured original transport.
`receipts.json` compares all256 reply bytes for five native/WASM pairs after
validating the original State handle and revision, normalizing only the
per-registry handle bytes16..24. Retired20 has handle0 and requires no masking.

`python.txt` records11 passing native cases (six new, five legacy), including
repeated task cancellation while real33's response is gated, coalesced cleanup,
weak producer binding after a delayed response, and panic-ambiguous versus
proven allocation-free status handling. `rust.txt` records14 protocol tests,
including the three new exact whole-request replay, raw ID-order/budget
mismatch, local one-byte boundary, global pressure,16-handle saturation,
handle-number exhaustion, legacy bypass rejection and tombstone lifetime
controls. `clippy.txt` records strict engine/lib/tests Clippy. Console ANSI and trailing
whitespace are removed from text logs; values and results are preserved.

Reproduce from this source tree:

```sh
cargo test -p xyg-engine linked_state_protocol_tests --lib
cargo clippy -p xyg-engine --lib --tests -- -D warnings
cargo build --release -p xyg-core
cargo build --release -p xyg-wasm --target wasm32-unknown-unknown
npm ci
npm ci --prefix packages/xy-node
node scripts/gen_geo_selected_wire.mjs --check
node js/build.mjs
node js/package-wasm.mjs
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib"
XYG_NONCE_REPORT="$PWD/spec/performance/geo-selected-state-nonce-2026-10-09/receipts.json" node --test packages/xy-node/test/geo-selected-state-nonce.test.mjs packages/xy-node/test/geo-selected-hierarchy.test.mjs
PYTHONPATH="$PWD/python:$PWD/tests" UV_NO_SYNC=1 uv run pytest tests/test_geo_selected_state_nonce.py tests/test_geo_selected_hierarchy.py -q
UV_NO_SYNC=1 uv run --with pre-commit pre-commit run --all-files
UV_NO_SYNC=1 uv run ruff check .
UV_NO_SYNC=1 uv run ruff format --check .
```

On Linux, select the corresponding native `.so` instead of `.dylib`. The WASM
fallback resolves relative to the test file, so root and Node-package CWDs use
the same packaged artifact. Host canonical inputs remain caller-owned; immutable
Rust receipt and selected authority credits use the existing global ledger.
No source-sized masks or new memory pools are introduced. Initial hook setup
needed the ignored docs codespell environment; final hooks passed after that
environment was available. No production source was changed by hook setup.
