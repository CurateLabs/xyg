# Temporal overview trusted painter and frozen export evidence

Small correctness evidence for issue50; this is not final M6 or a massive
interactive performance result. No public overview chart composition, domain
membership, selected overview input or camera-space refinement is claimed.

`parity.json` records exact native383/WASM33/Scene32/painter15 packet and painter
hashes, source/index/query/original Data disposal, two independent Data read
slots, real packaged Worker ordinary and borrowed WebGL2 pixels, malformed
candidate preserving old paint, stale rejection, six native exports and offline
strict-CSP replay with no scripts or external requests. WASM raster export is
explicit Unsupported. Domain ordinals128/143 are not source feature IDs;
borrowed source picking remains unavailable.

The instant0 fixture uses half-open intervals and full-u64 IDs. Both WebGL paths
expect(55,155,255,255) at(160,284)/(640,284) and white at the time-excluded cell.
SVG replay expects(56,156,255,255): its alpha compositing rounds two channels one
unit higher. The raw outputs preserve this difference rather than asserting
cross-renderer byte identity. The ordinary None XYGXv2 control is exactly equal
between actual native/WASM; the legacy selected v3 regression is captured
separately. Existing ordinary v2/selected v3 encoder branches are unchanged.

The worst-case persistent profile is15133568B, within the fixed16777216B Data
credit: four XYOV copies, four XYPB bounds,4096 triangle metadata allowances,
256 style allowances and1MiB fixed storage. The32×Scene phase is temporary and
is not credited to persistent views. GPU/DOM/application memory and committed
linear-memory capacity are outside the existing live-owned CPU ledger scope.
The8MiB compiler scratch and fixed snapshot framing are admitted before
allocation; malformed oversized/trailing/zero-row/count/paint controls fail
without consuming the old owner or retained cache credit.

The dense256-cell Rust control includes bearing120°,pitch60°,worldWrap=false.
It requires the separately reviewed snapped-topology signed-zero fix54a29314a.
`environment.json` records the exact source inputs and this dependency. That
file is excluded from this slice's own implementation commit and integrated
through the parent clip branch's normal ancestry merge.

Reproduce from this tree (native and standard packaged WASM required):

```sh
cargo test -p xyg-engine --lib overview_painter -- --nocapture
cargo clippy -p xyg-engine --lib --tests -- -D warnings
cargo test --workspace
cargo build --release -p xyg-core
cargo build --release --target wasm32-unknown-unknown -p xyg-wasm
node js/build.mjs
node js/package-wasm.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" \
XYG_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
XYG_OVERVIEW_PAINT_REPORT=spec/performance/geo-overview-painter-snapshot-2026-10-09/parity.json \
node scripts/geo_overview_painter_snapshot_conformance.mjs
uv run --with pre-commit pre-commit run --all-files
uv run ruff check .
uv run ruff format --check .
python3 scripts/verify_ownership.py
```

Release packaging uses the existing O3/LLVM inline150 profile and unchanged
1472KiB raw/608KiB gzip6 caps. Artifact byte counts/hash are in`parity.json`;
no budget increase, startup win or quiet-host timing is claimed.
