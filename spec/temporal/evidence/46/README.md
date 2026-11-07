# Partial temporal catalog candidate receipt

This preserves implementation evidence and failures; it is not #46 acceptance.
The [contract and remaining scope](../../../design/temporal-catalog.md) is authoritative.
`receipt.json` records exact artifacts, captures, raw/stored log hashes and reuse.

Reproduce from this checkout with Node22/Rust1.96 and TMPDIR=/var/tmp:

```sh
CARGO_BUILD_JOBS=2 cargo test -p xyg-engine temporal_scene --lib
CARGO_BUILD_JOBS=2 cargo build --release -p xyg-core
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.so"
uv run pytest tests/test_temporal_catalog.py tests/test_temporal_columns.py tests/test_temporal_controller.py tests/test_public_api.py -q
node --test packages/xy-node/test/temporal-catalog.test.mjs packages/xy-node/test/temporal.test.mjs packages/xy-node/test/temporal-controller.test.mjs
node js/build.mjs
CARGO_BUILD_JOBS=2 cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node scripts/temporal_catalog_wasm_parity.mjs target/wasm32-unknown-unknown/release/xyg_wasm.wasm
node js/package-wasm.mjs
uv run python examples/temporal/catalog.py
XYG_CHROMIUM=/home/ubuntu/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome node scripts/temporal_catalog_browser_smoke.mjs target/temporal-catalog
```

The packaging command currently fails its unchanged gzip limit. Offline HTML
uses the native-prepared shared painter; that journey does not certify packaged
WASM. Chromium proof checks paint hydration, exact IDs and disposal; it does
not certify keyboard-only operation, pixel goldens or accessibility.
The existing benchmark harness has not yet been extended for this candidate.
No startup/build/interaction/memory or competitor win is claimed.
