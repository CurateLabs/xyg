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
committed. Public selected hierarchy controllers, massive five-view
paint/interaction and1B-class admission remain separate open gates.

CI follow-up: the Python 3.11 floor exposed a Pillow-only test dependency,
and the offline selected snapshot probe failed its combined footer assertion.
The latter now includes exact pixel/DOM values in its failure output; no
assertion or product behavior is relaxed. The local repairs below preserve
these gates; Linux hosted confirmation remains pending.

The bounded [footer follow-up](selected-footer-followup.json) records the exact CI
failure and local repair proof. Frozen geographic SVG/HTML now declares its
default sans-serif face on the SVG root; other Scene exports and PDF are unchanged.
All six native formats, exact native/WASM frozen bytes and12 snapshot tests pass;
offline Chromium reads seven dark glyph pixels and162 white backplate pixels.
The dark threshold is unchanged. Linux CI confirmation remains pending.

## Final combined integration checkpoint

[Final integration](final-integration/environment.json) supersedes the earlier
artifact checkpoint for source revision `90149f0c333fc5bb3ae12d045aaf6cf192a30814`.
It includes reviewed mixed transport, selected frozen snapshots, hierarchy
protocol and typed hosts, live host recovery, and selected hierarchy commands42–44.
The freshly rebuilt ABI383 native library and ABI33 WASM artifact pass all60
selected hierarchy and34 legacy packet comparisons. The WASM artifact is
1,458,129 raw /599,346 gzip-level6 bytes, SHA-256
`d5de5c18285a18162a823fdd07ea4c8aaf7a068220e34b0b8b7e448b09cfde29`.
Runtime limits and compiler settings remain unchanged.

The directory retains the complete Rust workspace log (53 core,1435 engine,
65 WASM tests and two doctests), strict Clippy,35 Python tests,12 native Node
selected/live tests,21 native/WASM typed hierarchy tests, four package-contract
tests, type checking, source hashes, and raw conformance reports. The fresh
offline six-format snapshot replay again reports seven dark glyph pixels and
162 white pixels. The five-view browser test preserves old paint on failed
hydration and recovers lost stage/commit acknowledgments; each view has visible
red pixels. Independent combined source review found no blocker.

The native/WASM reports are bounded correctness evidence. The earlier startup
ABBA and100M trace reports remain their own checkpoints and were not rerun for
this artifact. Public selected hierarchy typed/live routing, massive five-view
performance, default-grid100M MultiPoint and1B execution remain open gates.
Linux CI confirmation is required before this combined branch integrates.
