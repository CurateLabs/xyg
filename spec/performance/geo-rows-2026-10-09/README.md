# Original geographic row companion evidence

This bounded #50/#39 slice adds Rust-issued paging over every original source row,
including null geometry, temporal exclusion and offscreen rows. It preserves
full-width IDs, duplicate IDs and signed temporal endpoints. It does not implement
linked selection, a spatial pyramid or all-host live journeys.

`browser-report.json` records the actual optimized packaged WASM artifact,
environment and strict-CSP offline test result: five shared painted views, all
original rows, offscreen DOM focus, cancellation/ACK, failed-read recovery,
63 malformed controls and complete handle cleanup. Focus is exercised through
DOM `.focus()`; this is not an exhaustive keyboard-navigation journey. The single
36.3 ms Worker startup observation ran under uncontrolled development load and
establishes no comparative latency win. Binary lease budgets do not measure OS RSS,
DOM/JS heap or GPU memory.

Reproduce from this checkout:

```bash
cargo build --release
npm ci
npm ci --prefix packages/xy-node
node js/build.mjs
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/package-wasm.mjs
XYG_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  XYG_GEO_RETAINED_REPORT=/tmp/geo-rows-report.json \
  node scripts/geo_retained_wasm_smoke.mjs
uv run pytest tests/test_geo_rows.py tests/test_geo_retained.py -q
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" node --test \
  packages/xy-node/test/geo-rows.test.mjs \
  packages/xy-node/test/geoscale.test.mjs \
  packages/xy-node/test/geo-scale-wasm-parity.test.mjs
cargo test -p xyg-engine geo_scale_protocol
```

Use the appropriate native library and Chromium path on other platforms. Native
and actual WASM row packets compare byte-for-byte after normalizing only owner
handles; raw results are beside this file. The one Node GC-lifetime test is skipped
without `--expose-gc`; the paging/parity tests pass. Existing ABI383/WASM33 command
framing carries commands15/16; this slice changes no exported ABI signatures.
