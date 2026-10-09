# Mixed-frame transport correctness evidence

This is a small actual native383/WASM33 binary-authority and browser paint
checkpoint. It supplies no massive interactive, benchmark win, full linked
selected-ID or public notebook/Reflex/VS Code mixed-controller completion claim.
Review/CI/merge integration and #50/#39 readiness remain pending.

`browser.json` records the actual packaged artifact fingerprint, strict-CSP
network receipts, exact red analysis/blue raster pixels, full-u64 picking,
visible literal provider footer and frozen whole-frame bytes. A real scheduling
callback throw during candidate upload releases all candidate GL resources and
preserves the old painter; the external framebuffer/canvas remain intact.
Removal returns to the two test-owned GL resources and then zero. Native frozen
HTML is actually reopened under its offline CSP: the same red/blue pixels and
literal attribution remain, with zero scripts/provider requests. Black and white
raster variants prove actual screenshot glyph pixels within Rust's opaque white
XYLB footer box, and native PNG/offline HTML preserve that contrast. The old
black-text-only footer failed the black-raster negative control.

The shared fixture is `tests/browser/geo_mixed_fixture.mjs`: a retained source
Point IDu64MAX/generationu64MAX, half-open window at i64MIN, opaque256² raster,
same-ID vector basemap and explicitly configured network attribution `Tiles`.
All bytes are authored locally and no provider is contacted. Tile read23 returns
Rust's exact provenance stamps; hosts perform no hashing/projection/LOD policy.
Original source/tile/cache/coordinator disposal precedes later immutable paint,
independent SourceData retain and whole-frame freeze. Native and wasm32 produce
identical complete Scene and XYGX bytes. Six native formats succeed; WASM static
artifact export retains its explicit unsupported profile.

Reproduce from this checkpoint:

```sh
cargo test --workspace
cargo clippy -p xyg-engine --all-targets --all-features -- -D warnings
cargo check -p xyg-engine --no-default-features --target wasm32-unknown-unknown
cargo build -p xyg-core --release
cargo build -p xyg-wasm --release --target wasm32-unknown-unknown
npm ci
npm ci --prefix packages/xy-node
node scripts/gen_geo_mixed_wire.mjs --check
node js/build.mjs
node js/package-wasm.mjs
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" node scripts/geo_mixed_transport_conformance.mjs
uv run pytest tests/test_geo_mixed_transport.py tests/test_geo_tiles.py -q
XYG_NATIVE_LIB="$PWD/target/release/libxyg_core.dylib" \
CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
XYG_MIXED_BROWSER_REPORT=spec/performance/geo-mixed-transport-2026-10-09/browser.json \
node scripts/geo_mixed_wasm_smoke.mjs
```

The wasm32 artifact measures1,323,023 raw/542,873 gzip bytes, SHA256
`8f0aecce9ca00c197af0370e5e80ca2948e6c7b335bb5a66e5f781bf42d0149d`.
Packaging depends on the separately approved recorded `3b11dfd4b` size decision
(1408 KiB raw/576 KiB gzip); its two constants are copied here without changing
optimization profiles. Root must integrate that authoritative decision/ancestry
before landing. The older1280/512 KiB gate correctly rejected this candidate.
Chrome155 needs `--use-angle=swiftshader` in this environment: the older
`--use-gl=swiftshader` flag lost the initial foreign GL context before any XYG
paint mutation. This was diagnosed by loss events and an empty GL-binding trace.

Validation: seven focused mixed Rust tests, three Tile protocol tests,1357 full
engine tests and the full workspace suite pass. Engine all-target/all-feature
Clippy, source/client typecheck, shared Node-wire identity, full hooks/Ruff and
no-raster wasm32 compile pass (the latter retains existing dead-code warnings).
Ten Python tests include five real-native mixed cases: original disposal
and exact PNG/HTML, parsed-view release before failed identity ACK, and retryable
owner cleanup after disposal failure. The actual Node native disposal regression fills the SourceData8 quota,
injects one pre-Rust cleanup failure, coalesces concurrent attempts, and proves
that retrying releases exactly one source-anchor slot. Rejected cleanup leaves
views dropped and successful cleanup remains idempotent. Environment/raw receipts are adjacent;
there are no quiet-host timing or comparative performance conclusions.
