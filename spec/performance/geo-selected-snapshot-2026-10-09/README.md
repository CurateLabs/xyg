# Selected frozen snapshot correctness evidence

This is a small actual native/wasm32 correctness and offline-pixel proof, not
a performance benchmark, completed integration claim or M6/#50 closure.
[environment.json](environment.json) records the integration base, exact source
hashes and tools; [conformance.json](conformance.json) records final artifact,
output sizes/digests and replay pixels. The product contract is
[geo-selected-snapshot.md](../../design/geo-selected-snapshot.md).

Final tests:53 core +1401 engine +65 WASM +2 doctests pass under
`cargo test --workspace`; strict engine lib/tests Clippy, full hooks, Ruff and
diff checks pass. Four new engine tests cover actual direct and reduced
MultiPoint folds, exact sparse u64/i64 intent, empty/None identity, duplicate
layer/ID and malformed binding/profile/count controls, old authority disposal,
budget failure recovery and native six-format output. Two existing protocol
tests now assert successful ordinary/mixed selected freeze and preserve exact
live XYSE authority. The protocol ordinary test compares the complete frozen
footer with the actual live SceneData footer.

The actual native C ABI and packaged WASM produce identical ordinary1344-byte
and mixed36,995-byte XYGX v3 envelopes. The mixed envelope preserves original
tile provenance and complete Scene after original source/tile/coordinator
disposal. All six native output formats retain the same selected metadata;
existing no-raster WASM artifact export returns explicit Unsupported. A failed
low-budget mixed freeze leaves the original immutable frame and frozen bytes
usable for a successful retry.

Chrome155 opens the actual exported self-contained HTML with its strict CSP.
The selected point is exact green `[0,255,0,255]`, basemap background exact blue
`[0,0,255,255]`; the bounded tile footer contains8 dark and162 opaque white pixels.
Literal attribution is present, with zero scripts or external requests. Native
PNG retains the existing opaque-white RGB export: two overlapping duplicate-ID
half-opacity selected points produce exact interior `[255,63,63]` in the engine
test. Frozen export changes no background or alpha policy.

Final WASM uses the unchanged O3/fat-LTO/codegen1/inline100/Binaryen132 O3 path:
1,397,787 raw /573,961 level9 gzip bytes, SHA256
`65b61556250da8979517c41b7e4c2f8ecb1d20b658f07b2f2e7aab5ae19f19b8`.
This fits the existing1408 KiB raw /576 KiB gzip gates. Against the issue959/955
integration's1,388,710 /570,579-byte artifact, the selection extension adds9,077
raw /3,382 gzip bytes. This is a size observation, not startup/latency or a
competitor-speed conclusion. No gate, optimization profile or dependency changed.

Reproduce from the recorded base plus this reviewed patch:

```bash
uv sync --extra reflex --group dev
uv sync --project docs/app
npm ci
npm ci --prefix packages/xy-node
cargo test --workspace
cargo clippy -p xyg-engine --lib --tests -- -D warnings
cargo build -p xyg-core --release
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
node js/package-wasm.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" \
XYG_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
XYG_SELECTED_REPORT=spec/performance/geo-selected-snapshot-2026-10-09/conformance.json \
node scripts/geo_selected_snapshot_conformance.mjs
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
git diff --check
```

Other platforms use their explicit native library and Chrome paths. App/test
inputs, DOM/GPU and committed linear memory/OS RSS are outside this proof's
per-module product ownership scope. Existing unowned Rust formatting drift is
not repaired by this slice; the shared helper differs by visibility only and
the two preexisting tests differ only in their authorized selected-freeze
functions. Imported snapshot metadata remains inert and structurally validated,
with no claim to authenticate original reduced membership or recreate a live
source/query. Public linked host events, massive interactive evidence and final
milestone release gates remain separate work.
