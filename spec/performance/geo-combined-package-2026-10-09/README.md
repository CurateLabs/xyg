# Combined hierarchy and selected snapshot package

The unchanged Rust release O3/inline100 + Binaryen132 O3 artifact combines
reviewed hierarchy commands37–41 and complete ordinary/mixed selected XYGXv3
snapshots. Native ABI383 and WASM ABI33 remain unchanged.

It is1,454,428 raw /597,662 gzip-level6 bytes, SHA-256
`ad68147eb89bbc8b4f1d6039642ee3068e3484243b48ccf6cb4d6359d9780b15`.
The previous1,441,792 raw /589,824 gzip gates reject it. The functionality
admission decision in `spec/design/browser-wasm.md` sets hard limits1,507,328
raw /622,592 gzip bytes; it does not increase runtime quotas or change compiler
settings. O3 shrink-level1 yielded identical bytes. Oz reduced raw to1,434,576
but increased gzip to598,701, so neither alternate solves the package gates.
The attempted profile timing harness produced no valid report and is not
performance evidence for Oz.

`hierarchy.json` records34 exact native/actual-WASM packets, including complete
reduced full-ID membership, exact signed time/CRS Scenes, Rows and cancellation,
forged-ticket, quota and fallback controls. `selected-snapshot.json` records
ordinary/mixed selected snapshot and live XYSE parity, six native formats,
offline strict-CSP selected/background pixels and attribution with no scripts
or network. The selected snapshot report labels its gzipBytes through the
script's level9 policy (596,811 bytes); the gate, hierarchy and environment
reports use level6 (597,662 bytes). Stdout files preserve each complete raw report. These are bounded
correctness proofs, not massive browser or competitive timing results.

`startup.json` contains four ABBA pairs,16 fresh Node processes. A is the
selected-protocol predecessor (hash in `environment.json`); B is this combined
artifact. Median process wall time is41.979ms versus42.909ms, compile2.103ms
versus2.177ms, instantiate0.372ms versus0.363ms. Initial linear memory is
1,245,184 bytes for both. Measurements use local files/warm OS cache under
uncontrolled load, exclude browser delivery/paint/interaction, and establish
no startup performance win. Environment, hashes and exact medians are committed.

Reproduce from the combined source tree:

```sh
cargo build --release -p xyg-core
cargo build --release -p xyg-wasm --target wasm32-unknown-unknown
npm ci
npm ci --prefix packages/xy-node
node js/build.mjs
node js/package-wasm.mjs target/wasm32-unknown-unknown/release/xyg_wasm.wasm
export XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" # use .so on Linux
XYG_HIERARCHY_REPORT=/tmp/hierarchy.json node scripts/geo_hierarchy_conformance.mjs
XYG_SELECTED_REPORT=/tmp/selected.json node scripts/geo_selected_snapshot_conformance.mjs
node --test js/test/package-wasm-contract.test.mjs
node benchmarks/bench_wasm_startup.mjs BASELINE.wasm packages/xy-client/dist/xyg-wasm.wasm /tmp/startup.json
node node_modules/binaryen/bin/wasm-opt target/wasm32-unknown-unknown/release/xyg_wasm.wasm -O3 --shrink-level=1 --all-features -o /tmp/shrink1.wasm
node node_modules/binaryen/bin/wasm-opt target/wasm32-unknown-unknown/release/xyg_wasm.wasm -Oz --all-features -o /tmp/oz.wasm
```

For the offline replay, install Playwright Chromium or set `CHROMIUM` to an
explicit installed browser. The packaged artifact remains generated and is not
committed. Selection on hierarchy, product hierarchy controllers, massive
five-view paint/interaction and1B-class admission remain separate open gates.

CI follow-up: the Python 3.11 floor exposed a Pillow-only test dependency,
and the offline selected snapshot probe failed its combined footer assertion.
The latter now includes exact pixel/DOM values in its failure output; no
assertion or product behavior is relaxed. These CI gates remain pending repair.
