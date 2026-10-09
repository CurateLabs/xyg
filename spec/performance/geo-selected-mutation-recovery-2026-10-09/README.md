# Selected mutation recovery: bounded engine proof

Commands35/36 now opt into the existing Rust allocation journal using nonzero
header240. Raw nonce0 and the shared selection/projection/LOD policy remain
unchanged. This evidence does not establish public selected-owner adoption,
lost19 publication recovery, or massive interaction performance.

`native-wasm.json` retains twelve complete native/WASM Scene/Rows packets:
legacy and opt-in, direct and reduced, canonical and indexed. Literal checks
cover u64MAX, duplicate full IDs on different original rows, null geometry,
offscreen coordinates and i64MIN time. Rows preserve source order, null/time
eligibility and sparse selected intent after Source/Index disposal.

`legacy-baseline.json` was produced in a separate process using the exact prior
retirement pair4aa35/e0f09, with opt-in tests disabled. All six nonce0 packets
match the new pair byte-for-byte after normalizing only owner16..24. Before
normalization, packet creator and operation sequence are checked against the
actual issued operation; Rows80..88 remains exact and is independently checked
against the requested RowsSession. No camera/time/style/state/count, source
identity, row provenance, selection footer, Scene or reserved bytes are masked.

The same actual native/WASM run proves successful consumed-State replay,
whole-request mismatch rejection, Confirm ACK replay,35 cancellation with exact
read ACK,36 fallback preserving State/history,36 cancel before/after completion
and disposal-start with retained loans,36→19 Data retirement, forged47 sequence
rejection and five canonical views at the unchanged sixteen-handle limit.
Ten focused Rust tests additionally prove parser failure retirement, physical
loan charge lifetime, local exact-boundary/one-byte-under, persistent per-job
read admission, fixed sixteen-stamp pressure and five indexed same-handle lanes.
Initial three TDD cases failed at the nonce whitelist before implementation.

The fresh source build uses unchanged O3/inline100 and ABI383/WASM33. Package
validation passes at1,495,349 raw bytes and613,335 gzip6/mtime0 bytes against
unchanged1,507,328/622,592 caps. Gzip9 is separately recorded. Full engine1477
and strict workspace/all-targets Clippy pass. Source and exact artifact paths,
versions and hashes are retained in the JSON manifests.

## Reproduction

Run from the checkout with its ordinary Node dependency installation:

```sh
cargo test -p xyg-engine selected_mutation --lib
cargo test -p xyg-engine --lib
cargo clippy --workspace --all-targets -- -D warnings
cargo build --release -p xyg-core
cargo build --release -p xyg-wasm --target wasm32-unknown-unknown
node js/build.mjs
node js/package-wasm.mjs target/wasm32-unknown-unknown/release/xyg_wasm.wasm
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" \
  XYG_SELECTED_MUTATION_WASM="$PWD/packages/xy-client/dist/xyg-wasm.wasm" \
  XYG_SELECTED_MUTATION_BASELINE=spec/performance/geo-selected-mutation-recovery-2026-10-09/legacy-baseline.json \
  XYG_SELECTED_MUTATION_REPORT=/tmp/selected-mutation-current.json \
  node scripts/geo_selected_mutation_recovery_conformance.mjs
```

To reproduce the pinned pre-change baseline, provide the artifact paths from
`environment.json` and add `XYG_SELECTED_MUTATION_LEGACY_ONLY=1`, omitting the
baseline comparison variable. An explicitly provided missing artifact fails;
the script has no fake native/WASM fallback. External leaf storage is a bounded
fixture Map for at most40,002 vertices, not a massive storage or latency proof.
